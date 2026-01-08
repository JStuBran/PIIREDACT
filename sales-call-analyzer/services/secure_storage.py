"""Secure file storage service with encryption and access control."""

import logging
import os
import stat
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

logger = logging.getLogger(__name__)


class SecureStorageService:
    """Secure file storage with encryption and permission management."""

    def __init__(self):
        """Initialize secure storage service."""
        self.upload_folder = os.environ.get("UPLOAD_FOLDER", "/tmp/sales-call-analyzer")
        self._ensure_upload_folder()
        
        # Get encryption key from environment or generate one
        encryption_key = os.environ.get("FILE_ENCRYPTION_KEY")
        if encryption_key:
            # Use provided key (should be base64-encoded Fernet key)
            try:
                self.cipher = Fernet(encryption_key.encode())
            except Exception as e:
                logger.warning(f"Invalid encryption key format, generating new one: {e}")
                self.cipher = self._generate_key()
        else:
            # Generate key from SECRET_KEY if available
            secret_key = os.environ.get("SECRET_KEY")
            if secret_key and "DO-NOT-USE" not in secret_key:
                self.cipher = self._derive_key_from_secret(secret_key)
            else:
                logger.warning("No encryption key configured. Files will not be encrypted.")
                self.cipher = None
        
        # File permissions (read/write for owner only)
        self.file_permissions = stat.S_IRUSR | stat.S_IWUSR  # 0o600
        self.dir_permissions = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR  # 0o700

    def _ensure_upload_folder(self):
        """Ensure upload folder exists with secure permissions."""
        Path(self.upload_folder).mkdir(parents=True, exist_ok=True)
        # Set secure directory permissions
        try:
            os.chmod(self.upload_folder, 0o700)  # rwx------
        except Exception as e:
            logger.warning(f"Could not set directory permissions: {e}")

    def _generate_key(self) -> Fernet:
        """Generate a new encryption key."""
        key = Fernet.generate_key()
        logger.warning(f"Generated new encryption key. Set FILE_ENCRYPTION_KEY={key.decode()} in environment")
        return Fernet(key)

    def _derive_key_from_secret(self, secret: str) -> Fernet:
        """Derive encryption key from SECRET_KEY using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'sales_call_analyzer_salt',  # Fixed salt for consistency
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        return Fernet(key)

    def save_file_secure(
        self,
        file_content: bytes,
        job_id: str,
        filename: str,
    ) -> str:
        """
        Save file with encryption and secure permissions.
        
        Args:
            file_content: File content as bytes
            job_id: Job identifier
            filename: Original filename
            
        Returns:
            Path to saved file
        """
        # Create secure filename
        safe_filename = self._sanitize_filename(filename)
        file_path = os.path.join(self.upload_folder, f"{job_id}_{safe_filename}")
        
        try:
            # Encrypt file content if cipher is available
            if self.cipher:
                encrypted_content = self.cipher.encrypt(file_content)
                content_to_write = encrypted_content
            else:
                content_to_write = file_content
            
            # Write file
            with open(file_path, 'wb') as f:
                f.write(content_to_write)
            
            # Set secure file permissions (read/write owner only)
            os.chmod(file_path, self.file_permissions)
            
            logger.info(f"Saved secure file: {file_path} (encrypted={self.cipher is not None})")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save secure file: {e}")
            # Clean up on failure
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception:
                pass
            raise

    def read_file_secure(self, file_path: str) -> bytes:
        """
        Read and decrypt file.
        
        Args:
            file_path: Path to encrypted file
            
        Returns:
            Decrypted file content
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(file_path, 'rb') as f:
                encrypted_content = f.read()
            
            # Decrypt if cipher is available
            if self.cipher:
                decrypted_content = self.cipher.decrypt(encrypted_content)
                return decrypted_content
            else:
                return encrypted_content
                
        except Exception as e:
            logger.error(f"Failed to read secure file: {e}")
            raise

    def delete_file_secure(self, file_path: str) -> bool:
        """
        Securely delete file (overwrite before deletion if possible).
        
        Args:
            file_path: Path to file
            
        Returns:
            True if deleted successfully
        """
        if not os.path.exists(file_path):
            return True
        
        try:
            # Attempt secure deletion (overwrite with zeros)
            try:
                file_size = os.path.getsize(file_path)
                with open(file_path, 'r+b') as f:
                    f.write(b'\x00' * min(file_size, 1024 * 1024))  # Overwrite first 1MB
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                pass  # Continue with normal deletion if secure deletion fails
            
            # Delete file
            os.unlink(file_path)
            logger.info(f"Deleted file: {file_path}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to delete file {file_path}: {e}")
            return False

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to prevent path traversal and remove sensitive info.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Remove any path components
        filename = os.path.basename(filename)
        
        # Remove potentially sensitive patterns (email addresses, phone numbers)
        import re
        # Remove email-like patterns
        filename = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', 'REDACTED', filename)
        # Remove phone-like patterns
        filename = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', 'REDACTED', filename)
        # Remove SSN-like patterns
        filename = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', 'REDACTED', filename)
        
        # Keep only safe characters
        safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')
        filename = ''.join(c if c in safe_chars else '_' for c in filename)
        
        # Limit length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200-len(ext)] + ext
        
        return filename or "uploaded_file"

    def cleanup_old_files(self, max_age_hours: int = 24) -> Tuple[int, int]:
        """
        Clean up old files from upload folder.
        
        Args:
            max_age_hours: Maximum age in hours before deletion
            
        Returns:
            Tuple of (deleted_count, failed_count)
        """
        import time
        from datetime import datetime, timedelta
        
        deleted_count = 0
        failed_count = 0
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        try:
            for filename in os.listdir(self.upload_folder):
                file_path = os.path.join(self.upload_folder, filename)
                
                # Skip directories
                if os.path.isdir(file_path):
                    continue
                
                # Check file age
                try:
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime < cutoff_time:
                        if self.delete_file_secure(file_path):
                            deleted_count += 1
                        else:
                            failed_count += 1
                except Exception as e:
                    logger.warning(f"Error checking file {file_path}: {e}")
                    failed_count += 1
            
            if deleted_count > 0 or failed_count > 0:
                logger.info(f"Cleanup: deleted {deleted_count} files, {failed_count} failed")
            
            return deleted_count, failed_count
            
        except Exception as e:
            logger.error(f"Error during file cleanup: {e}")
            return deleted_count, failed_count
