"""Configuration for Sales Call Analyzer."""

import os
from typing import List


class Config:
    """Application configuration from environment variables."""

    # Flask - SECRET_KEY is required in production
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        import warnings
        warnings.warn("SECRET_KEY not set! Using insecure default for development only.")
        SECRET_KEY = "dev-secret-key-DO-NOT-USE-IN-PRODUCTION"
    
    # OpenAI - required for analysis
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
    
    @classmethod
    def validate_required_config(cls) -> list:
        """Check for required configuration and return list of missing items."""
        missing = []
        if not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if cls.SECRET_KEY and "DO-NOT-USE" in cls.SECRET_KEY:
            missing.append("SECRET_KEY (using insecure default)")
        return missing
    
    # Whisper
    # Default to 'tiny' for speed (3-5x faster than 'base')
    # Use 'base' or larger for better accuracy
    WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "tiny")
    
    # Email - SMTP
    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASS = os.environ.get("SMTP_PASS")
    SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
    
    # Email - Resend (alternative)
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
    RESEND_FROM = os.environ.get("RESEND_FROM", "noreply@yourdomain.com")
    
    # Auth
    ALLOWED_EMAILS: List[str] = []
    MAGIC_LINK_EXPIRY_MINUTES = int(os.environ.get("MAGIC_LINK_EXPIRY_MINUTES", "15"))
    
    # Upload
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max upload
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/tmp/sales-call-analyzer")
    ALLOWED_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "flac", "webm", "mp4"}
    
    # Database
    # If DATABASE_URL is set (e.g., from Railway PostgreSQL), it will be used
    # Otherwise, falls back to SQLite using DATABASE_PATH
    DATABASE_URL = os.environ.get("DATABASE_URL")  # PostgreSQL connection string
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "sales_calls.db")  # SQLite path
    
    # App URL (for magic links)
    APP_URL = os.environ.get("APP_URL", "http://localhost:5000")

    @classmethod
    def load_whitelist(cls) -> List[str]:
        """Load allowed emails from env var or whitelist.json."""
        # First try environment variable
        env_emails = os.environ.get("ALLOWED_EMAILS", "")
        if env_emails:
            cls.ALLOWED_EMAILS = [e.strip().lower() for e in env_emails.split(",") if e.strip()]
            return cls.ALLOWED_EMAILS
        
        # Fall back to whitelist.json
        import json
        whitelist_path = os.path.join(os.path.dirname(__file__), "whitelist.json")
        if os.path.exists(whitelist_path):
            with open(whitelist_path) as f:
                data = json.load(f)
                cls.ALLOWED_EMAILS = [e.lower() for e in data.get("emails", [])]
        
        return cls.ALLOWED_EMAILS

    @classmethod
    def is_email_allowed(cls, email: str) -> bool:
        """Check if email is in the whitelist."""
        if not cls.ALLOWED_EMAILS:
            cls.load_whitelist()
        
        # If no whitelist configured, deny all in production (require explicit config)
        if not cls.ALLOWED_EMAILS:
            import warnings
            warnings.warn("ALLOWED_EMAILS not configured! Set ALLOWED_EMAILS env var or whitelist.json")
            # In strict mode (production), deny all. Set ALLOW_ALL_EMAILS=true to override.
            if os.environ.get("ALLOW_ALL_EMAILS", "").lower() == "true":
                return True
            return False
        
        return email.lower().strip() in cls.ALLOWED_EMAILS

