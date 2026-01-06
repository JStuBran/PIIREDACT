"""Presidio Audio Redactor - PII redaction for audio transcripts."""

import logging

from .audio_redactor import AudioRedactor

# Set up default logging (with NullHandler)
logging.getLogger("presidio-audio-redactor").addHandler(logging.NullHandler())

__all__ = ["AudioRedactor"]
