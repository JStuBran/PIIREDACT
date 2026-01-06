# Presidio Audio Redactor

PII redaction for audio transcripts using Microsoft Presidio and OpenAI Whisper.

## Features

- **Transcription**: Convert audio to text using OpenAI Whisper
- **PII Detection**: Identify sensitive data using Presidio Analyzer
- **Anonymization**: Redact PII with configurable operators
- **Timestamps**: Map PII locations to audio timestamps
- **REST API**: Deploy as a microservice

## Installation

```bash
pip install presidio-audio-redactor
```

For REST API support:
```bash
pip install presidio-audio-redactor[server]
```

## Quick Start

```python
from presidio_audio_redactor import AudioRedactor

# Initialize with default settings
redactor = AudioRedactor(whisper_model="base")

# Redact PII from audio
result = redactor.redact("call_recording.wav")
print(result["redacted_text"])
print(result["pii_findings"])
```

## Usage Examples

### Basic Redaction

```python
from presidio_audio_redactor import AudioRedactor

redactor = AudioRedactor(whisper_model="base")
result = redactor.redact("audio.mp3")

print("Original:", result["original_text"])
print("Redacted:", result["redacted_text"])
print("PII Found:", len(result["pii_findings"]))
```

### With Score Threshold

```python
# Only detect high-confidence PII (score >= 0.7)
result = redactor.redact(
    "audio.mp3",
    score_threshold=0.7,
)
```

### Specific Entity Types

```python
# Only detect names and locations
result = redactor.redact(
    "audio.mp3",
    entities=["PERSON", "LOCATION"],
)
```

### With Audio Timestamps

```python
# Get timestamps for where PII appears in audio
result = redactor.redact(
    "audio.mp3",
    return_timestamps=True,
)

for finding in result["pii_findings"]:
    print(f"{finding['entity_type']}: {finding['text']}")
    if "audio_start" in finding:
        print(f"  Audio: {finding['audio_start']:.2f}s - {finding['audio_end']:.2f}s")
```

### Save Redacted Text

```python
# Transcribe, redact, and save to file
output_path = redactor.redact_and_save(
    "audio.mp3",
    output_path="redacted_transcript.txt",
)
```

## REST API

### Start the Server

```bash
# Using Python
python app.py

# Using gunicorn (production)
gunicorn --bind 0.0.0.0:3000 app:create_app

# With Docker
docker build -t presidio-audio-redactor .
docker run -p 3000:3000 presidio-audio-redactor
```

### API Endpoints

#### Health Check
```bash
GET /health
```

#### Redact Audio
```bash
POST /redact

# With file upload
curl -X POST http://localhost:3000/redact \
  -F "audio=@recording.wav"

# With base64 JSON
curl -X POST http://localhost:3000/redact \
  -H "Content-Type: application/json" \
  -d '{"audio": "<base64-encoded-audio>", "format": "wav"}'

# With parameters
curl -X POST "http://localhost:3000/redact?language=en&score_threshold=0.5" \
  -F "audio=@recording.wav"
```

Query parameters:
- `language`: Language code (default: "en")
- `entities`: Comma-separated entity types (e.g., "PERSON,LOCATION")
- `score_threshold`: Minimum confidence score 0.0-1.0 (default: 0.0)
- `return_timestamps`: Include audio timestamps (true/false)

#### Transcribe Only
```bash
POST /transcribe
```

## Whisper Models

Available models (trade-off between speed and accuracy):

| Model | Parameters | English-only | Multilingual | Required VRAM |
|-------|------------|--------------|--------------|---------------|
| tiny | 39 M | ✓ | ✓ | ~1 GB |
| base | 74 M | ✓ | ✓ | ~1 GB |
| small | 244 M | ✓ | ✓ | ~2 GB |
| medium | 769 M | ✓ | ✓ | ~5 GB |
| large | 1550 M | | ✓ | ~10 GB |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WHISPER_MODEL` | Whisper model to use | `base` |
| `PORT` | Server port | `3000` |
| `WORKERS` | Gunicorn workers | `1` |
| `TIMEOUT` | Request timeout (seconds) | `120` |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=presidio_audio_redactor
```

## License

MIT License - see [LICENSE](../LICENSE) for details.
