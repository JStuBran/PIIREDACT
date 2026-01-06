"""Tests for the REST API."""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def app():
    """Create Flask test application."""
    with patch("presidio_audio_redactor.audio_redactor.whisper.load_model") as mock_load:
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": " Hello, my name is John Smith.",
            "segments": [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 2.0,
                    "text": " Hello, my name is John Smith.",
                }
            ],
        }
        mock_load.return_value = mock_model
        
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, client):
        """Test health endpoint returns success message."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert b"Presidio Audio Redactor service is up" in response.data


class TestRedactEndpoint:
    """Tests for /redact endpoint."""

    def test_redact_with_file_upload(self, client, tmp_path):
        """Test redaction with file upload."""
        # Create a minimal WAV file header (44 bytes)
        wav_header = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt "
        wav_header += (16).to_bytes(4, "little")  # Subchunk1Size
        wav_header += (1).to_bytes(2, "little")   # AudioFormat (PCM)
        wav_header += (1).to_bytes(2, "little")   # NumChannels
        wav_header += (16000).to_bytes(4, "little")  # SampleRate
        wav_header += (32000).to_bytes(4, "little")  # ByteRate
        wav_header += (2).to_bytes(2, "little")   # BlockAlign
        wav_header += (16).to_bytes(2, "little")  # BitsPerSample
        wav_header += b"data" + (0).to_bytes(4, "little")  # Subchunk2
        
        from io import BytesIO
        audio_file = BytesIO(wav_header)
        
        response = client.post(
            "/redact",
            data={"audio": (audio_file, "test.wav")},
            content_type="multipart/form-data",
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "original_text" in data
        assert "redacted_text" in data
        assert "pii_findings" in data

    def test_redact_with_base64(self, client):
        """Test redaction with base64-encoded audio."""
        # Create a minimal WAV-like data
        wav_data = b"RIFF" + b"\x00" * 40
        encoded = base64.b64encode(wav_data).decode("utf-8")
        
        response = client.post(
            "/redact",
            json={"audio": encoded, "format": "wav"},
            content_type="application/json",
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "original_text" in data
        assert "redacted_text" in data

    def test_redact_with_parameters(self, client):
        """Test redaction with optional parameters."""
        wav_data = b"RIFF" + b"\x00" * 40
        encoded = base64.b64encode(wav_data).decode("utf-8")
        
        response = client.post(
            "/redact?language=en&score_threshold=0.5&return_timestamps=true",
            json={"audio": encoded, "format": "wav"},
        )
        
        assert response.status_code == 200

    def test_redact_with_entities_filter(self, client):
        """Test redaction filtering specific entities."""
        wav_data = b"RIFF" + b"\x00" * 40
        encoded = base64.b64encode(wav_data).decode("utf-8")
        
        response = client.post(
            "/redact?entities=PERSON,LOCATION",
            json={"audio": encoded, "format": "wav"},
        )
        
        assert response.status_code == 200

    def test_redact_no_audio_returns_error(self, client):
        """Test that missing audio returns validation error."""
        response = client.post("/redact")
        
        assert response.status_code == 422
        data = json.loads(response.data)
        assert "error" in data


class TestTranscribeEndpoint:
    """Tests for /transcribe endpoint."""

    def test_transcribe_with_file(self, client):
        """Test transcription with file upload."""
        wav_header = b"RIFF" + b"\x00" * 40
        
        from io import BytesIO
        audio_file = BytesIO(wav_header)
        
        response = client.post(
            "/transcribe",
            data={"audio": (audio_file, "test.wav")},
            content_type="multipart/form-data",
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "text" in data
        assert "segments" in data

    def test_transcribe_no_audio_returns_error(self, client):
        """Test that missing audio returns validation error."""
        response = client.post("/transcribe")
        
        assert response.status_code == 422
        data = json.loads(response.data)
        assert "error" in data

