# Sales Call Analyzer

A secure, self-hosted sales call analysis tool. Upload audio recordings, get PII-redacted transcripts and AI-powered coaching reports.

## Features

- 🔒 **PII Redaction** - Names, phone numbers, and sensitive data automatically redacted using Presidio
- 🎙️ **Transcription** - Local Whisper model (no audio sent to external services)
- 🤖 **AI Coaching** - GPT-4o analyzes calls and provides actionable feedback
- 📊 **Call Stats** - Talk time, questions, filler words, and more
- 📄 **PDF Reports** - Professional coaching reports delivered via email
- 🔐 **Email Auth** - Magic link login with email whitelist
- 📈 **Dashboard & History** - View all calls, search, filter, and track progress
- 👥 **Team Management** - Track multiple reps with performance summaries
- 🔍 **Interactive Transcripts** - Search, navigate, and export transcripts
- 📊 **Call Comparison** - Compare multiple calls side-by-side with trends
- 📝 **Annotations** - Add notes to specific timestamps in calls
- 📤 **Export Options** - CSV, JSON, PDF, TXT, and SRT subtitle exports
- 🎯 **Benchmarking** - Team averages and percentile rankings
- 🔬 **Enhanced Analytics** - Sentiment analysis, keyword detection, call structure

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
cd presidio/sales-call-analyzer
docker build -t sales-call-analyzer .

# Run
docker run -p 8080:8080 \
  -e SECRET_KEY=your-secret \
  -e OPENAI_API_KEY=sk-... \
  -e RESEND_API_KEY=re_... \
  sales-call-analyzer
```

### Railway

1. Create a new project on Railway
2. Connect your GitHub repo
3. Set the **Root Directory** to `sales-call-analyzer`
4. **Add PostgreSQL Database** (recommended):
   - Click `+ New` → `Database` → `PostgreSQL`
   - Railway automatically provides `DATABASE_URL` environment variable
   - The app will automatically use PostgreSQL when `DATABASE_URL` is set
5. Set environment variables:
   - `SECRET_KEY`
   - `OPENAI_API_KEY`
   - `RESEND_API_KEY` (or SMTP settings)
   - `APP_URL` (your Railway URL, e.g., `https://your-app.up.railway.app`)
   - `ALLOWED_EMAILS` (optional whitelist)
   - `DATABASE_URL` (automatically set if you added PostgreSQL)
6. Deploy!

**Note**: The app supports both PostgreSQL (recommended for production) and SQLite (for local development). If `DATABASE_URL` is set, PostgreSQL is used automatically. Otherwise, it falls back to SQLite.

### Render / Fly.io

1. Create a new project
2. Connect your repo
3. Set the root directory to `sales-call-analyzer`
4. Set environment variables
5. Deploy!

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

## Database Configuration

The app supports both **PostgreSQL** (recommended for production) and **SQLite** (for local development).

### PostgreSQL (Production - Railway, etc.)

When `DATABASE_URL` environment variable is set, the app automatically uses PostgreSQL:
- Railway: Add PostgreSQL service, `DATABASE_URL` is automatically provided
- Other platforms: Set `DATABASE_URL=postgresql://user:password@host:port/database`

**Benefits:**
- Better concurrency (handles multiple workers)
- More reliable in containerized environments
- Production-ready

### SQLite (Local Development)

If `DATABASE_URL` is not set, the app uses SQLite:
- Default path: `sales_calls.db` in current directory
- Customize with: `DATABASE_PATH=/path/to/database.db`

**Note**: For Docker deployments with SQLite, use a persistent volume:
```bash
DATABASE_PATH=/data/sales_calls.db
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | - | Flask secret key |
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o` | OpenAI model |
| `WHISPER_MODEL` | No | `tiny` | Whisper model size (tiny=fast, base=balanced) |
| `RESEND_API_KEY` | * | - | Resend API key |
| `SMTP_HOST` | * | - | SMTP server host |
| `SMTP_USER` | * | - | SMTP username |
| `SMTP_PASS` | * | - | SMTP password |
| `ALLOWED_EMAILS` | No | - | Comma-separated whitelist |
| `APP_URL` | No | `http://localhost:5000` | Public URL |
| `DATABASE_URL` | No | - | PostgreSQL connection string (auto-set by Railway) |
| `DATABASE_PATH` | No | `sales_calls.db` | SQLite database path (used if DATABASE_URL not set) |

\* Either Resend or SMTP configuration required for email

## Whisper Models

| Model | Size | Speed | Accuracy | RAM | Recommended For |
|-------|------|-------|----------|-----|----------------|
| tiny | 39M | ~10x real-time | Basic | ~1GB | **Speed priority** |
| base | 74M | ~2-3x real-time | Good | ~1GB | Balanced (default) |
| small | 244M | ~1x real-time | Better | ~2GB | Accuracy priority |
| medium | 769M | Slower | Great | ~5GB | High accuracy |
| large | 1550M | Slowest | Best | ~10GB | Maximum accuracy |

**Performance Tip**: For faster processing, use `WHISPER_MODEL=tiny`. It's 3-5x faster than `base` with slightly lower accuracy that's still excellent for sales calls.

## License

MIT - See [LICENSE](../LICENSE)

