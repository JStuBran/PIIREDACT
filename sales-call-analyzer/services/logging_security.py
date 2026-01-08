"""Secure logging utilities to prevent PII exposure."""

import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Patterns that might indicate PII
PII_PATTERNS = [
    r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
    r'\b\d{3}\.\d{2}\.\d{4}\b',  # SSN with dots
    r'\b\d{10,}\b',  # Long numbers (credit cards, etc.)
    r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone numbers
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
    r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Credit card
    r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',  # IP address
]

# Keywords that might indicate sensitive data
SENSITIVE_KEYWORDS = [
    'password', 'passwd', 'secret', 'token', 'api_key', 'apikey',
    'credit_card', 'creditcard', 'ssn', 'social_security',
    'original_text', 'unredacted', 'pii', 'personally_identifiable',
]


def sanitize_string(text: str, replacement: str = "[REDACTED]") -> str:
    """
    Sanitize a string to remove potential PII.
    
    Args:
        text: String to sanitize
        replacement: Replacement string for PII
        
    Returns:
        Sanitized string
    """
    if not text or not isinstance(text, str):
        return str(text) if text is not None else ""
    
    sanitized = text
    
    # Replace PII patterns
    for pattern in PII_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    
    # Check for sensitive keywords and redact surrounding context
    for keyword in SENSITIVE_KEYWORDS:
        if keyword.lower() in sanitized.lower():
            # Redact a window around the keyword
            pattern = rf'.{{0,20}}{re.escape(keyword)}.{{0,20}}'
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    
    return sanitized


def sanitize_dict(data: Dict[str, Any], max_depth: int = 10) -> Dict[str, Any]:
    """
    Recursively sanitize a dictionary to remove PII.
    
    Args:
        data: Dictionary to sanitize
        max_depth: Maximum recursion depth
        
    Returns:
        Sanitized dictionary
    """
    if max_depth <= 0:
        return {"error": "[MAX_DEPTH_REACHED]"}
    
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    for key, value in data.items():
        # Skip known PII fields
        if key in ['original_text', 'unredacted_text', 'pii_findings']:
            sanitized[key] = "[REDACTED]"
            continue
        
        # Sanitize string values
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, max_depth - 1)
        elif isinstance(value, list):
            sanitized[key] = [sanitize_dict(item, max_depth - 1) if isinstance(item, dict) 
                            else sanitize_string(item) if isinstance(item, str) 
                            else item for item in value]
        else:
            sanitized[key] = value
    
    return sanitized


class SecureLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that automatically sanitizes log messages."""
    
    def process(self, msg, kwargs):
        """Process log message to sanitize PII."""
        # Sanitize the message
        if isinstance(msg, str):
            msg = sanitize_string(msg)
        elif isinstance(msg, dict):
            msg = sanitize_dict(msg)
        
        # Sanitize extra kwargs
        if 'extra' in kwargs:
            kwargs['extra'] = sanitize_dict(kwargs['extra'])
        
        return msg, kwargs


def get_secure_logger(name: str) -> logging.Logger:
    """
    Get a logger that automatically sanitizes PII.
    
    Args:
        name: Logger name
        
    Returns:
        Secure logger instance
    """
    base_logger = logging.getLogger(name)
    return SecureLoggerAdapter(base_logger, {})


def safe_log_exception(logger_instance: logging.Logger, message: str, exc_info: Any = None):
    """
    Safely log an exception without exposing PII.
    
    Args:
        logger_instance: Logger to use
        message: Log message
        exc_info: Exception info (from sys.exc_info())
    """
    # Sanitize message
    safe_message = sanitize_string(message)
    
    # Get exception info safely
    if exc_info:
        try:
            # Only log exception type and message, not full traceback with data
            exc_type, exc_value, _ = exc_info
            safe_message += f" | Exception: {exc_type.__name__}: {sanitize_string(str(exc_value))}"
        except Exception:
            pass
    
    logger_instance.error(safe_message, exc_info=False)


def sanitize_file_path(file_path: str) -> str:
    """
    Sanitize file path to remove potentially sensitive information.
    
    Args:
        file_path: File path to sanitize
        
    Returns:
        Sanitized file path
    """
    if not file_path:
        return ""
    
    # Extract just the filename, not full path
    filename = os.path.basename(file_path)
    
    # Remove any PII from filename
    sanitized = sanitize_string(filename)
    
    # Keep directory structure but sanitize
    dir_path = os.path.dirname(file_path)
    if dir_path:
        # Just show the directory name, not full path
        dir_name = os.path.basename(dir_path)
        return os.path.join(dir_name, sanitized)
    
    return sanitized
