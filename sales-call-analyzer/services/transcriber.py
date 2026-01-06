"""Transcriber service - Whisper + Presidio PII redaction."""

import logging
from typing import Any, Dict, List, Optional

from presidio_audio_redactor import AudioRedactor

logger = logging.getLogger(__name__)


class TranscriberService:
    """Transcribe audio and redact PII using Whisper + Presidio."""

    def __init__(self, whisper_model: str = "base"):
        """
        Initialize the transcriber.

        Args:
            whisper_model: Whisper model size (tiny, base, small, medium, large)
        """
        logger.info(f"Initializing TranscriberService with Whisper model: {whisper_model}")
        self.redactor = AudioRedactor(whisper_model=whisper_model)
        logger.info("TranscriberService ready")

    def transcribe_and_redact(
        self,
        audio_path: str,
        language: str = "en",
        score_threshold: float = 0.4,
    ) -> Dict[str, Any]:
        """
        Transcribe audio and redact PII.

        Args:
            audio_path: Path to the audio file
            language: Language code for PII detection
            score_threshold: Minimum confidence for PII detection

        Returns:
            Dict with:
                - original_text: Raw transcript (for internal use only)
                - redacted_text: PII-redacted transcript
                - pii_findings: List of detected PII with positions
                - segments: Timestamped segments from Whisper
                - duration_min: Duration in minutes
        """
        logger.info(f"Transcribing: {audio_path}")

        # Use presidio-audio-redactor with timestamps
        result = self.redactor.redact(
            audio_path=audio_path,
            language=language,
            score_threshold=score_threshold,
            return_timestamps=True,
        )

        # Calculate duration from segments
        segments = result.get("segments", [])
        duration_sec = 0
        if segments:
            last_segment = segments[-1]
            duration_sec = last_segment.get("end", 0)

        # Parse segments into a cleaner format with speaker diarization
        parsed_segments = self._parse_segments(segments)

        return {
            "original_text": result.get("original_text", ""),
            "redacted_text": result.get("redacted_text", ""),
            "pii_findings": result.get("pii_findings", []),
            "segments": parsed_segments,
            "duration_sec": duration_sec,
            "duration_min": round(duration_sec / 60, 1),
        }

    def _parse_segments(self, segments: List[Dict]) -> List[Dict[str, Any]]:
        """
        Parse Whisper segments into a cleaner format.

        Args:
            segments: Raw segments from Whisper

        Returns:
            List of segment dicts with id, start, end, text
        """
        parsed = []
        for i, seg in enumerate(segments):
            parsed.append({
                "id": i,
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "").strip(),
                # Whisper doesn't do diarization, so we'll estimate speaker
                # based on segment patterns (can be improved with pyannote)
                "speaker": f"spk_{i % 2}",  # Alternate speakers as estimate
            })
        return parsed

    def transcribe_only(self, audio_path: str) -> Dict[str, Any]:
        """
        Transcribe audio without PII redaction.

        Args:
            audio_path: Path to audio file

        Returns:
            Dict with text and segments
        """
        result = self.redactor.transcribe(audio_path, word_timestamps=True)
        return {
            "text": result.get("text", ""),
            "segments": result.get("segments", []),
        }

