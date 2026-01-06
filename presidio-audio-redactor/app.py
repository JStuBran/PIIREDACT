"""REST API server for audio redactor."""

import base64
import logging
import os
import tempfile
from typing import Optional

from flask import Flask, jsonify, request

from presidio_audio_redactor import AudioRedactor

DEFAULT_PORT = "3000"

WELCOME_MESSAGE = r"""
 _______  _______  _______  _______ _________ ______  _________ _______
(  ____ )(  ____ )(  ____ \(  ____ \\__   __/(  __  \ \__   __/(  ___  )
| (    )|| (    )|| (    \/| (    \/   ) (   | (  \  )   ) (   | (   ) |
| (____)|| (____)|| (__    | (_____    | |   | |   ) |   | |   | |   | |
|  _____)|     __)|  __)   (_____  )   | |   | |   | |   | |   | |   | |
| (      | (\ (   | (            ) |   | |   | |   ) |   | |   | |   | |
| )      | ) \ \__| (____/\/\____) |___) (___| (__/  )___) (___| (___) |
|/       |/   \__/(_______/\_______)\_______/(______/ \_______/(_______)

                        AUDIO REDACTOR
"""


class InvalidParamError(Exception):
    """Exception for invalid API parameters."""

    def __init__(self, err_msg: str):
        self.err_msg = err_msg
        super().__init__(err_msg)


class Server:
    """Flask server for audio redactor."""

    def __init__(self, whisper_model: str = "base"):
        """
        Initialize the server.

        Args:
            whisper_model: Whisper model size to use
        """
        self.logger = logging.getLogger("presidio-audio-redactor")
        self.app = Flask(__name__)
        self.logger.info("Starting audio redactor engine")
        self.engine = AudioRedactor(whisper_model=whisper_model)
        self.logger.info(WELCOME_MESSAGE)

        @self.app.route("/health")
        def health() -> str:
            """Return basic health probe result."""
            return "Presidio Audio Redactor service is up"

        @self.app.route("/redact", methods=["POST"])
        def redact():
            """
            Redact PII from audio.

            Accepts audio file via:
            - multipart/form-data with 'audio' file
            - JSON with base64-encoded 'audio' field

            Optional parameters:
            - language: Language code (default: 'en')
            - entities: Comma-separated entity types to detect
            - score_threshold: Minimum confidence score (0.0-1.0)
            - return_timestamps: Include audio timestamps for PII (true/false)

            Returns:
                JSON with original_text, redacted_text, pii_findings
            """
            # Parse parameters
            language = request.form.get("language") or request.args.get("language", "en")
            entities_str = request.form.get("entities") or request.args.get("entities")
            entities = entities_str.split(",") if entities_str else None
            
            score_threshold = float(
                request.form.get("score_threshold")
                or request.args.get("score_threshold", "0.0")
            )
            
            return_timestamps = (
                request.form.get("return_timestamps", "").lower() == "true"
                or request.args.get("return_timestamps", "").lower() == "true"
            )

            # Get audio data
            audio_path = self._get_audio_from_request()
            
            if not audio_path:
                raise InvalidParamError(
                    "Invalid parameter. Please provide audio via file upload "
                    "or base64-encoded JSON."
                )

            try:
                result = self.engine.redact(
                    audio_path=audio_path,
                    language=language,
                    entities=entities,
                    score_threshold=score_threshold,
                    return_timestamps=return_timestamps,
                )
                
                # Remove segments from response to keep it smaller
                result.pop("segments", None)
                
                return jsonify(result)
            finally:
                # Clean up temp file if created
                if audio_path.startswith(tempfile.gettempdir()):
                    try:
                        os.unlink(audio_path)
                    except Exception:
                        pass

        @self.app.route("/transcribe", methods=["POST"])
        def transcribe():
            """
            Transcribe audio to text without PII redaction.

            Accepts audio file via:
            - multipart/form-data with 'audio' file
            - JSON with base64-encoded 'audio' field

            Returns:
                JSON with text and segments
            """
            audio_path = self._get_audio_from_request()
            
            if not audio_path:
                raise InvalidParamError(
                    "Invalid parameter. Please provide audio via file upload "
                    "or base64-encoded JSON."
                )

            try:
                result = self.engine.transcribe(audio_path)
                return jsonify({
                    "text": result.get("text", ""),
                    "segments": result.get("segments", []),
                })
            finally:
                if audio_path.startswith(tempfile.gettempdir()):
                    try:
                        os.unlink(audio_path)
                    except Exception:
                        pass

        @self.app.errorhandler(InvalidParamError)
        def invalid_param(err):
            self.logger.warning(
                f"Failed to process audio with validation error: {err.err_msg}"
            )
            return jsonify(error=err.err_msg), 422

        @self.app.errorhandler(Exception)
        def server_error(e):
            self.logger.error(f"A fatal error occurred during execution: {e}")
            return jsonify(error="Internal server error"), 500

    def _get_audio_from_request(self) -> Optional[str]:
        """
        Extract audio from request and save to temp file.

        Returns:
            Path to audio file, or None if no valid audio provided
        """
        # Try multipart form upload
        if request.files and "audio" in request.files:
            audio_file = request.files["audio"]
            # Determine extension from filename
            ext = os.path.splitext(audio_file.filename)[1] or ".wav"
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                audio_file.save(f)
                return f.name

        # Try base64 JSON
        json_data = request.get_json(silent=True)
        if json_data and "audio" in json_data:
            audio_data = base64.b64decode(json_data["audio"])
            ext = json_data.get("format", ".wav")
            if not ext.startswith("."):
                ext = f".{ext}"
            
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(audio_data)
                return f.name

        return None


def create_app(whisper_model: str = None) -> Flask:
    """
    Create Flask application.

    Args:
        whisper_model: Whisper model to use (default from env or 'base')

    Returns:
        Flask application instance
    """
    model = whisper_model or os.environ.get("WHISPER_MODEL", "base")
    server = Server(whisper_model=model)
    return server.app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    app.run(host="0.0.0.0", port=port)

