# Sales Call Analyzer - Production Dockerfile
# Self-contained build from within sales-call-analyzer directory
FROM python:3.11-slim

# Build args
ARG WHISPER_MODEL=base

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV WHISPER_MODEL=${WHISPER_MODEL}
ENV PORT=8080

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    # WeasyPrint dependencies
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    # Build tools for some Python packages
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Download Whisper model at build time (to avoid download on first request)
RUN python -c "import whisper; whisper.load_model('${WHISPER_MODEL}')"

# Download spaCy model for Presidio
RUN python -m spacy download en_core_web_lg

# Copy application code (includes local presidio_audio_redactor module)
COPY . .

# Create upload directory
RUN mkdir -p /tmp/sales-call-analyzer

# Create non-root user
RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app /tmp/sales-call-analyzer
USER appuser

# Expose port
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run with gunicorn
CMD gunicorn app:app \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --threads 4 \
    --timeout 300 \
    --access-logfile - \
    --error-logfile -
