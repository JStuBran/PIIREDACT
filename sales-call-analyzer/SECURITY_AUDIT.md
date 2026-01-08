# Security Audit: PII Exposure Points

## Executive Summary

This document identifies all points where PII (Personally Identifiable Information) may be exposed **before** redaction occurs in the Sales Call Analyzer application.

## Critical Finding: PII Exposure Timeline

PII is exposed at multiple points in the processing pipeline before redaction occurs. The redaction happens during transcription, but there are several exposure windows.

---

## 1. File Upload & Storage ⚠️ **HIGH RISK**

### Location
- `app.py` lines 375-379 (web upload)
- `api_v1.py` lines 368-370 (API upload)

### Exposure
- **Raw audio file** containing PII is saved to disk **immediately** upon upload
- File path: `{UPLOAD_FOLDER}/{job_id}_{filename}`
- File remains on disk until processing completes (line 191 in `background_processor.py`)

### Risk Level: **HIGH**
- Anyone with filesystem access can access raw audio files
- Files persist even if processing fails
- No encryption at rest
- Default location: `/tmp/sales-call-analyzer` (world-readable on many systems)

### Recommendations
1. **Encrypt files at rest** before saving
2. **Restrict filesystem permissions** (chmod 600)
3. **Use secure temporary storage** (encrypted volume)
4. **Delete files immediately** after transcription (move to secure temp, then delete)
5. **Add file access logging** to detect unauthorized access

---

## 2. Transcription Process ⚠️ **MEDIUM RISK**

### Location
- `services/transcriber.py` line 50-55
- `presidio_audio_redactor/audio_redactor.py` lines 220-226

### Exposure
- **`original_text`** is created during transcription **before** redaction
- Original text exists in memory during processing
- Whisper transcription may log or cache transcriptions

### Risk Level: **MEDIUM**
- Original text exists temporarily in memory
- If process crashes, memory dump could expose PII
- Logging at debug level could expose original text (line 228 in `audio_redactor.py`)

### Current Protection
- ✅ `original_text` is removed before database storage (line 175 in `background_processor.py`)
- ✅ Only `redacted_text` is used for analysis

### Recommendations
1. **Disable debug logging** in production
2. **Clear memory** immediately after redaction
3. **Use secure memory allocation** (mlock/mprotect)
4. **Audit Whisper model** for any caching/logging

---

## 3. Logging ⚠️ **MEDIUM RISK**

### Location
- Multiple files use `logger.info()`, `logger.debug()`, `logger.exception()`

### Exposure
- Logs may contain:
  - File paths with filenames (potentially containing PII)
  - Error messages that include transcript snippets
  - Debug logs with original text length (line 228 in `audio_redactor.py`)

### Risk Level: **MEDIUM**
- Log files are typically readable by system administrators
- Log aggregation services (CloudWatch, Datadog) may store logs
- Exception traces may include sensitive data

### Current Protection
- ✅ Most logs use job_id, not actual content
- ⚠️ Exception logging may include error messages with data

### Recommendations
1. **Sanitize all log output** - never log transcript content
2. **Use structured logging** with PII redaction
3. **Restrict log file permissions**
4. **Enable log encryption** in transit and at rest
5. **Review exception handling** to avoid logging sensitive data

---

## 4. Database Storage ✅ **PROTECTED**

### Location
- `services/database.py` lines 242-244, 567-574
- `services/background_processor.py` lines 172-187

### Exposure
- **NONE** - Original text is explicitly removed before storage

### Current Protection
- ✅ `original_text` is removed before database insertion (line 175)
- ✅ Only `redacted_text` is stored in `transcription_json`
- ✅ Database stores only redacted data

### Status: **SECURE** ✅

---

## 5. API Endpoints ⚠️ **LOW-MEDIUM RISK**

### Location
- `api_v1.py` - various GET endpoints
- `app.py` - `/transcript/<job_id>`, `/report/<job_id>`

### Exposure
- API endpoints return `transcription_json` which contains `redacted_text` only
- However, if `original_text` accidentally leaks into database, it would be exposed

### Risk Level: **LOW-MEDIUM**
- Currently protected (only redacted data returned)
- Risk if code changes accidentally include `original_text`

### Current Protection
- ✅ Endpoints return only `transcription_json` from database (which is redacted)
- ✅ Access control via `@login_required` and `@require_api_key`

### Recommendations
1. **Add explicit filtering** in API responses to exclude `original_text`
2. **Add unit tests** to verify `original_text` never returned
3. **Add API response validation** to catch accidental leaks

---

## 6. Email Attachments ⚠️ **LOW RISK**

### Location
- `services/email_sender.py` lines 97-170
- `services/background_processor.py` lines 159-164

### Exposure
- PDF reports are attached to emails
- PDFs contain only redacted data (generated from `redacted_text`)

### Risk Level: **LOW**
- PDFs are generated from redacted transcripts
- Email transmission may not be encrypted (depends on SMTP/Resend config)

### Current Protection
- ✅ PDFs generated from `redacted_text` only
- ✅ No original text in PDFs

### Recommendations
1. **Ensure email encryption** (TLS for SMTP, HTTPS for Resend)
2. **Add email encryption** (PGP/S/MIME) for sensitive data
3. **Audit PDF generation** to ensure no original text leaks

---

## 7. Webhooks ⚠️ **LOW RISK**

### Location
- `api_v1.py` lines 704-800
- `services/background_processor.py` lines 198-208, 216-224

### Exposure
- Webhook payloads contain:
  - `call_id`, `filename`, `status`, `score`, `duration_min`
  - **No transcript data** is sent

### Risk Level: **LOW**
- Webhooks only send metadata, not transcript content
- Filename could potentially contain PII if user uploads file with sensitive name

### Current Protection
- ✅ No transcript content in webhooks
- ⚠️ Filename is included (could be sensitive)

### Recommendations
1. **Sanitize filenames** before including in webhooks
2. **Add option to exclude filename** from webhook payloads
3. **Document filename handling** in webhook payloads

---

## 8. File System Access ⚠️ **HIGH RISK**

### Location
- All file operations use `Config.UPLOAD_FOLDER`

### Exposure
- Raw audio files stored on filesystem
- PDF reports stored on filesystem
- Temporary files during processing

### Risk Level: **HIGH**
- Default location: `/tmp/sales-call-analyzer` (often world-readable)
- Files accessible to:
  - System administrators
  - Other processes running as same user
  - Backup systems
  - Container filesystem snapshots

### Current Protection
- ⚠️ Files deleted after processing (line 191) but only if successful
- ⚠️ Failed jobs may leave files on disk
- ⚠️ No encryption at rest

### Recommendations
1. **Use encrypted storage** (encrypted volume, encrypted files)
2. **Restrict filesystem permissions** (chmod 600, chown to dedicated user)
3. **Implement file cleanup job** for orphaned files
4. **Use secure temporary storage** with automatic cleanup
5. **Add file access monitoring** (audit logs)

---

## 9. Memory & Process Dumps ⚠️ **MEDIUM RISK**

### Exposure
- During processing, `original_text` exists in memory
- Process core dumps could expose PII
- Memory snapshots in cloud environments

### Risk Level: **MEDIUM**
- Low probability but high impact if occurs
- Cloud providers may capture memory for debugging

### Recommendations
1. **Minimize memory retention** - clear `original_text` immediately after redaction
2. **Disable core dumps** in production
3. **Use secure memory allocation** (mlock to prevent swap)
4. **Review cloud provider** memory capture policies

---

## 10. Error Handling ⚠️ **MEDIUM RISK**

### Location
- `services/background_processor.py` lines 210-224
- Exception handlers throughout codebase

### Exposure
- Exception messages may include:
  - File paths
  - Partial transcript content
  - Error details with sensitive context

### Risk Level: **MEDIUM**
- Exception logging could expose PII if not careful

### Current Protection
- ⚠️ Generic error messages in some places
- ⚠️ `logger.exception()` may include full traceback with data

### Recommendations
1. **Sanitize all exception messages** before logging
2. **Use structured error handling** that excludes sensitive data
3. **Add error message filtering** to remove PII patterns
4. **Review all exception handlers** for PII exposure

---

## Summary of Recommendations by Priority

### 🔴 **CRITICAL (Do Immediately)**
1. **Encrypt audio files at rest** before saving to disk
2. **Restrict filesystem permissions** (chmod 600, dedicated user)
3. **Implement secure file cleanup** for failed/abandoned jobs
4. **Sanitize all logging** to never include transcript content

### 🟡 **HIGH (Do Soon)**
5. **Add explicit API response filtering** to exclude `original_text`
6. **Implement file access monitoring** and audit logs
7. **Review and sanitize exception handling** throughout codebase
8. **Add unit tests** to verify `original_text` never persisted

### 🟢 **MEDIUM (Consider)**
9. **Use secure memory allocation** (mlock) for sensitive data
10. **Add email encryption** (PGP/S/MIME) for sensitive reports
11. **Sanitize filenames** in webhook payloads
12. **Disable debug logging** in production

---

## Current Security Posture

### ✅ **What's Protected**
- Database storage (original_text removed before storage)
- API responses (only redacted data returned)
- PDF generation (uses redacted text only)
- Webhook payloads (no transcript content)

### ⚠️ **What Needs Improvement**
- File storage (no encryption, world-readable location)
- Logging (potential PII in logs)
- Memory handling (original_text in memory during processing)
- Error handling (exception messages may expose data)

### 🔴 **Critical Gaps**
- Raw audio files accessible on filesystem
- No encryption at rest
- Files may persist if processing fails
- Logging may contain sensitive data

---

## Testing Recommendations

1. **Penetration Testing**
   - Attempt to access raw audio files via filesystem
   - Test API endpoints for `original_text` leakage
   - Review log files for PII exposure

2. **Code Review**
   - Audit all file I/O operations
   - Review all logging statements
   - Check exception handlers

3. **Monitoring**
   - Add alerts for file access outside normal flow
   - Monitor for `original_text` in API responses
   - Track file cleanup failures

---

## Compliance Considerations

If handling PII subject to regulations (GDPR, HIPAA, etc.):

1. **Data Minimization**: Only collect/store what's necessary
2. **Encryption**: Encrypt PII at rest and in transit
3. **Access Controls**: Restrict access to PII
4. **Audit Logs**: Log all access to PII
5. **Data Retention**: Delete PII promptly after processing
6. **Breach Notification**: Have procedures for detecting/reporting breaches

---

*Last Updated: 2026-01-07*
*Next Review: 2026-04-07*
