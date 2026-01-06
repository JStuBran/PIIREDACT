# Sales Call Analyzer

A secure, self-hosted sales call analysis tool. Upload audio recordings, get PII-redacted transcripts and AI-powered coaching reports.

## Features

- 🔒 **PII Redaction** - Names, phone numbers, and sensitive data automatically redacted using Presidio
- 🎙️ **Transcription** - Local Whisper model (no audio sent to external services)
- 🤖 **AI Coaching** - GPT-4o analyzes calls and provides actionable feedback
- 📊 **Call Stats** - Talk time, questions, filler words, and more
- 📄 **PDF Reports** - Professional coaching reports delivered via email
- 🔐 **Email Auth** - Magic link login with email whitelist

## Quick Start

### Prerequisites

- Python 3.10+
- ffmpeg (for audio processing)
- OpenAI API key

### Installation

```bash
# Clone the repo
cd presidio/sales-call-analyzer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Download spaCy model for Presidio
python -m spacy download en_core_web_lg

# Copy and configure environment
cp env.example .env
# Edit .env with your API keys
```

### Configuration

Edit `.env` with your settings:

```bash
# Required
SECRET_KEY=your-random-secret-key
OPENAI_API_KEY=sk-your-key

# Email (choose one)
RESEND_API_KEY=re_your-key
# OR
SMTP_HOST=smtp.gmail.com
SMTP_USER=...
SMTP_PASS=...

# Optional: restrict access
ALLOWED_EMAILS=trainer1@company.com,trainer2@company.com
```

### Run Locally

```bash
# Development mode
python app.py

# Production mode
gunicorn app:app -b 0.0.0.0:8080
```

Visit http://localhost:5000

## Deployment

### Docker

```bash
# Build
docker build -t sales-call-analyzer .

# Run
docker run -p 8080:8080 \
  -e SECRET_KEY=your-secret \
  -e OPENAI_API_KEY=sk-... \
  -e RESEND_API_KEY=re_... \
  sales-call-analyzer
```

### Railway / Render / Fly.io

1. Create a new project
2. Connect your repo
3. Set environment variables
4. Deploy!

Recommended settings:
- **Memory**: 2GB+ (Whisper needs RAM)
- **CPU**: 2+ cores
- **Timeout**: 300s (for long audio files)

## How It Works

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Upload    │───>│  Transcribe │───>│   Redact    │
│   Audio     │    │  (Whisper)  │    │ (Presidio)  │
└─────────────┘    └─────────────┘    └─────────────┘
                                             │
                                             ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Email     │<───│  Generate   │<───│   Analyze   │
│   Report    │    │    PDFs     │    │  (GPT-4o)   │
└─────────────┘    └─────────────┘    └─────────────┘
```

1. **Upload**: Trainer uploads audio file via web interface
2. **Transcribe**: Whisper converts audio to text locally
3. **Redact**: Presidio detects and redacts PII (names, numbers, etc.)
4. **Analyze**: Redacted transcript sent to GPT-4o for coaching analysis
5. **Generate**: WeasyPrint creates PDF reports
6. **Email**: Reports delivered to trainer's inbox

## Security

- **Audio stays local**: Whisper runs on your server, audio never leaves
- **PII redacted before AI**: Only anonymized transcripts go to OpenAI
- **Email whitelist**: Only authorized trainers can access
- **Magic links**: Passwordless auth, links expire in 15 minutes
- **Files deleted**: Audio files removed after processing

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | - | Flask secret key |
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o` | OpenAI model |
| `WHISPER_MODEL` | No | `base` | Whisper model size |
| `RESEND_API_KEY` | * | - | Resend API key |
| `SMTP_HOST` | * | - | SMTP server host |
| `SMTP_USER` | * | - | SMTP username |
| `SMTP_PASS` | * | - | SMTP password |
| `ALLOWED_EMAILS` | No | - | Comma-separated whitelist |
| `APP_URL` | No | `http://localhost:5000` | Public URL |

\* Either Resend or SMTP configuration required for email

## Whisper Models

| Model | Size | Speed | Accuracy | RAM |
|-------|------|-------|----------|-----|
| tiny | 39M | Fastest | Basic | ~1GB |
| base | 74M | Fast | Good | ~1GB |
| small | 244M | Medium | Better | ~2GB |
| medium | 769M | Slow | Great | ~5GB |
| large | 1550M | Slowest | Best | ~10GB |

## License

MIT - See [LICENSE](../LICENSE)

