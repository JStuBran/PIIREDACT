# Security & PII Protection

This document outlines the comprehensive security measures implemented to protect Personally Identifiable Information (PII) throughout the Sales Call Analyzer application.

## Overview

The Sales Call Analyzer processes sensitive audio recordings containing customer conversations. This document details the multi-layered security approach to ensure PII is protected at every stage of processing.

## Security Architecture

### Defense in Depth

We employ a defense-in-depth strategy with multiple security layers:

1. **Encryption at Rest** - All files encrypted before storage
2. **Access Controls** - Filesystem permissions and authentication
3. **Data Minimization** - Only redacted data persisted
4. **Secure Logging** - Automatic PII redaction in logs
5. **Memory Security** - Immediate clearing of sensitive data
6. **API Protection** - Explicit filtering of sensitive fields
7. **Secure Deletion** - Overwrite before deletion

## Implementation Details

### 1. File Encryption at Rest

**Problem**: Raw audio files containing PII were stored unencrypted on disk, accessible to anyone with filesystem access.

**Solution**: 
- All uploaded files are encrypted using Fernet (symmetric encryption) before saving
- Encryption key derived from `SECRET_KEY` or provided via `FILE_ENCRYPTION_KEY`
- Files automatically decrypted when needed for processing
- Backward compatible with existing unencrypted files

**Implementation**: `services/secure_storage.py`

**Configuration**:
```bash
# Option 1: Use dedicated encryption key (recommended)
export FILE_ENCRYPTION_KEY="<base64-encoded-fernet-key>"

# Option 2: Derive from SECRET_KEY (less secure but convenient)
# Uses SECRET_KEY automatically if FILE_ENCRYPTION_KEY not set
```

### 2. Filesystem Permission Restrictions

**Problem**: Default file permissions allowed world-readable access to sensitive files.

**Solution**:
- Files saved with `chmod 600` (read/write owner only)
- Upload directory created with `chmod 700` (owner only)
- Prevents unauthorized access even if encryption fails

**Implementation**: `services/secure_storage.py::save_file_secure()`

### 3. Secure File Cleanup

**Problem**: Files could persist indefinitely if processing failed, exposing PII.

**Solution**:
- Secure deletion: files overwritten with zeros before deletion
- Automatic cleanup of files older than 24 hours
- Files deleted even on processing errors
- Admin cleanup endpoint for manual cleanup

**Implementation**: 
- `services/secure_storage.py::delete_file_secure()`
- `services/secure_storage.py::cleanup_old_files()`
- `app.py::/admin/cleanup` route

### 4. Logging Sanitization

**Problem**: Logs could contain PII from filenames, error messages, or debug output.

**Solution**:
- Automatic PII detection and redaction in all log messages
- Patterns detected: SSN, phone numbers, emails, credit cards, IP addresses
- Sensitive keywords trigger context redaction
- Secure logger adapter for automatic sanitization
- Safe exception logging without PII exposure

**Implementation**: `services/logging_security.py`

**Features**:
- `SecureLoggerAdapter` - Automatically sanitizes all log messages
- `sanitize_string()` - Removes PII patterns from strings
- `sanitize_dict()` - Recursively sanitizes dictionaries
- `safe_log_exception()` - Logs exceptions without PII

### 5. Data Minimization & Database Security

**Problem**: Original unredacted transcripts could be stored in database.

**Solution**:
- `original_text` explicitly removed before database storage
- Only `redacted_text` persisted to database
- Explicit filtering in all database operations
- Verification that `original_text` never stored

**Implementation**:
- `services/background_processor.py` - Removes `original_text` before storage
- `services/database.py` - Only stores redacted data
- Database queries filter out sensitive fields

### 6. Memory Security

**Problem**: `original_text` could persist in memory, exposed in core dumps or memory snapshots.

**Solution**:
- `original_text` extracted and cleared immediately after redaction
- Explicit deletion from transcription dictionaries
- Memory cleared in `finally` blocks even on exceptions
- Minimize time `original_text` exists in memory

**Implementation**: 
- `services/background_processor.py` - Immediate memory clearing
- `tasks.py` - Memory clearing in Celery tasks

### 7. API Response Filtering

**Problem**: API endpoints could accidentally return `original_text` or file paths.

**Solution**:
- Explicit filtering in all API endpoints
- `original_text` removed from all responses
- File paths removed from responses
- All response data sanitized before returning
- Both list and detail endpoints protected

**Implementation**: `api_v1.py`

**Protected Endpoints**:
- `GET /api/v1/calls` - List calls
- `GET /api/v1/calls/<id>` - Get call details
- All endpoints filter `original_text` and file paths

### 8. Webhook Payload Sanitization

**Problem**: Webhook payloads could contain PII in filenames or error messages.

**Solution**:
- All webhook payloads sanitized using `sanitize_dict()`
- Filenames sanitized before inclusion
- Error messages replaced with generic `[PROCESSING_ERROR]`
- No transcript content in webhooks (metadata only)

**Implementation**: `api_v1.py::trigger_webhook()`

### 9. Exception Handling Security

**Problem**: Exception messages and stack traces could expose PII.

**Solution**:
- All exception handlers use `safe_log_exception()`
- Error messages sanitized before database storage
- Exception details redacted to prevent PII exposure
- Generic error messages for external-facing errors

**Implementation**: All exception handlers updated throughout codebase

## Security Flow

### File Upload Flow

```
1. User uploads file
   ↓
2. File read into memory
   ↓
3. File encrypted (Fernet)
   ↓
4. Encrypted file saved with chmod 600
   ↓
5. File path stored in database (no content)
```

### Processing Flow

```
1. Read encrypted file
   ↓
2. Decrypt to temporary file
   ↓
3. Transcribe (creates original_text)
   ↓
4. Redact PII (creates redacted_text)
   ↓
5. IMMEDIATELY clear original_text from memory
   ↓
6. Process using only redacted_text
   ↓
7. Store only redacted_text in database
   ↓
8. Delete temporary and original files securely
```

### API Response Flow

```
1. Query database
   ↓
2. Get call data (already redacted)
   ↓
3. Explicitly remove original_text (if present)
   ↓
4. Remove file paths
   ↓
5. Sanitize all data
   ↓
6. Return sanitized response
```

## Compliance Considerations

These security measures help meet requirements for:

### GDPR (General Data Protection Regulation)
- ✅ **Data Protection by Design** - Encryption, access controls
- ✅ **Data Minimization** - Only redacted data stored
- ✅ **Right to Erasure** - Secure file deletion
- ✅ **Breach Prevention** - Multiple security layers

### HIPAA (Health Insurance Portability and Accountability Act)
- ✅ **Encryption at Rest** - All files encrypted
- ✅ **Access Controls** - Filesystem permissions
- ✅ **Audit Logs** - Secure logging (sanitized)
- ✅ **Data Integrity** - Secure deletion

### SOC 2
- ✅ **Security Controls** - Multiple layers of protection
- ✅ **Data Protection** - Encryption and access controls
- ✅ **Monitoring** - Secure logging and audit trails

## Security Best Practices

### For Administrators

1. **Set Encryption Key**:
   ```bash
   # Generate key
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   
   # Set in environment
   export FILE_ENCRYPTION_KEY="<generated-key>"
   ```

2. **Review Logs Regularly**:
   - Check for security warnings
   - Verify PII is properly redacted
   - Monitor file access patterns

3. **Run Cleanup Jobs**:
   - Set up scheduled cleanup (cron or Celery)
   - Monitor cleanup success rates
   - Review orphaned files

4. **Monitor File Access**:
   - Review filesystem access logs
   - Check for unauthorized access attempts
   - Verify permission settings

### For Developers

1. **Never Log PII**:
   - Use `get_secure_logger()` for all loggers
   - Use `safe_log_exception()` for exceptions
   - Never log `original_text` or file contents

2. **Always Filter API Responses**:
   - Remove `original_text` explicitly
   - Remove file paths
   - Sanitize all user-facing data

3. **Clear Memory Immediately**:
   - Delete `original_text` as soon as redaction complete
   - Use `finally` blocks for cleanup
   - Minimize memory retention time

4. **Use Secure Storage**:
   - Always use `SecureStorageService` for file operations
   - Never bypass encryption
   - Use secure deletion for cleanup

## Security Testing

### Recommended Tests

1. **File Encryption**:
   - Upload file and verify encryption on disk
   - Verify decryption works correctly
   - Test with missing encryption key

2. **Permissions**:
   - Verify files are `chmod 600`
   - Verify directory is `chmod 700`
   - Test unauthorized access attempts

3. **Logging**:
   - Upload file with PII in filename
   - Verify logs are sanitized
   - Check exception logs for PII

4. **API Responses**:
   - Call all API endpoints
   - Verify `original_text` never returned
   - Verify file paths removed

5. **Memory**:
   - Process call and check memory
   - Verify `original_text` not in memory after processing
   - Test with memory profiling tools

6. **Cleanup**:
   - Create old files manually
   - Run cleanup job
   - Verify secure deletion

## Incident Response

If PII exposure is suspected:

1. **Immediate Actions**:
   - Review logs for exposure
   - Check file access logs
   - Identify scope of exposure

2. **Containment**:
   - Rotate encryption keys if compromised
   - Review and restrict access
   - Secure affected files

3. **Notification**:
   - Follow compliance requirements (GDPR, HIPAA, etc.)
   - Notify affected users if required
   - Document incident

4. **Remediation**:
   - Fix security gaps
   - Update security measures
   - Review and improve processes

## Security Updates

This security implementation was completed on **2026-01-07**.

### Version History

- **v1.0 (2026-01-07)**: Initial comprehensive security implementation
  - File encryption at rest
  - Filesystem permission restrictions
  - Secure file cleanup
  - Logging sanitization
  - API response filtering
  - Memory security
  - Webhook sanitization
  - Exception handling security

## Additional Resources

- `SECURITY_AUDIT.md` - Detailed security audit and risk analysis
- `SECURITY_IMPLEMENTATION.md` - Technical implementation details
- `services/secure_storage.py` - Secure storage implementation
- `services/logging_security.py` - Secure logging implementation

## Contact

For security concerns or questions:
- Review security documentation
- Check logs for warnings
- Verify environment configuration
- Contact security team if needed

---

**Remember**: Security is an ongoing process. Regularly review and update security measures as threats evolve.

*Last Updated: 2026-01-07*
