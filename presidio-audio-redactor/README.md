# Presidio Audio Redactor

PII redaction for audio transcripts using Microsoft Presidio and OpenAI Whisper.

## Installation

```bash
pip install -e presidio-audio-redactor
```

## Usage

```python
from presidio_audio_redactor import AudioRedactor

redactor = AudioRedactor(whisper_model="base")
result = redactor.redact("call_recording.wav")

print(result["redacted_text"])
print(result["pii_findings"])
```

## Whisper Models

Available models (trade-off between speed and accuracy):
- `tiny` - Fastest, least accurate
- `base` - Good balance (default)
- `small` - Better accuracy
- `medium` - High accuracy
- `large` - Best accuracy, slowest
