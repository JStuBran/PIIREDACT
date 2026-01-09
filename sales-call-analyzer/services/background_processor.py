"""Background job processor for async call analysis."""

import logging
import os
import tempfile
import threading
from typing import Any, Dict

from .logging_security import get_secure_logger, safe_log_exception, sanitize_string
from .secure_storage import SecureStorageService

logger = get_secure_logger(__name__)


class BackgroundProcessor:
    """Process call analysis in background threads."""

    def __init__(self):
        """Initialize the background processor."""
        self._active_jobs = set()
        logger.info("BackgroundProcessor initialized")

    def process_call_async(
        self,
        job_id: str,
        file_path: str,
        filename: str,
        user_email: str,
        services: Dict[str, Any],
        config: Any,
    ):
        """
        Process a call in a background thread.

        Args:
            job_id: Call ID
            file_path: Path to audio file
            filename: Original filename
            user_email: User email
            services: Dict with service instances
            config: Config object
        """
        if job_id in self._active_jobs:
            logger.warning(f"Job {job_id} already processing")
            return

        self._active_jobs.add(job_id)
        thread = threading.Thread(
            target=self._process_call,
            args=(job_id, file_path, filename, user_email, services, config),
            daemon=True,
        )
        thread.start()
        logger.info(f"[{job_id}] Started background processing thread")

    def _process_call(
        self,
        job_id: str,
        file_path: str,
        filename: str,
        user_email: str,
        services: Dict[str, Any],
        config: Any,
    ):
        """Internal method to process the call."""
        secure_storage = SecureStorageService()
        transcription = None
        original_text = None
        
        try:
            db = services["database"]
            transcriber = services["transcriber"]
            analyzer = services["analyzer"]
            analytics_service = services["analytics"]
            pdf_generator = services["pdf_generator"]
            email_sender = services["email_sender"]

            # Get call record to check call_type
            call_record = db.get_call(job_id)
            call_type = call_record.get("call_type", "real") if call_record else "real"
            
            # Step 1: Transcribe (with or without redaction based on call type)
            if call_type == "ai_agent":
                logger.info(f"[{job_id}] Starting transcription (AI agent call - no redaction)...")
            else:
                logger.info(f"[{job_id}] Starting transcription (real call - with PII redaction)...")
            
            db.update_call(job_id, status="transcribing")

            # Read encrypted file and decrypt for transcription
            temp_file_path = None
            
            try:
                # Read and decrypt the file
                file_content = secure_storage.read_file_secure(file_path)
                logger.debug(f"[{job_id}] Decrypted file, size: {len(file_content)} bytes")
                
                # Write decrypted content to temp file for transcription
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_path)[1]) as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name
                    
                logger.debug(f"[{job_id}] Created temp file for transcription: {temp_file_path}")
                
            except FileNotFoundError:
                logger.error(f"[{job_id}] Audio file not found: {file_path}")
                raise ValueError("Audio file not found. Please try uploading again.")
            except Exception as e:
                # Log the decryption error - don't silently fall back to encrypted file
                logger.error(f"[{job_id}] Failed to decrypt audio file: {e}")
                raise ValueError("Failed to process audio file. The file may be corrupted or there was a server error. Please try uploading again.")

            # Conditionally transcribe based on call type
            if call_type == "ai_agent":
                # AI agent calls: no PII redaction needed
                transcription = transcriber.transcribe_only(temp_file_path)
                # For AI agent calls, original_text and redacted_text are the same
                # No need to clear original_text since it's not sensitive
            else:
                # Real calls: transcribe with PII redaction
                transcription = transcriber.transcribe_and_redact(temp_file_path)
                
                # SECURITY: Extract and clear original_text from memory immediately
                original_text = transcription.get("original_text")
                if original_text:
                    # Clear from transcription dict
                    transcription.pop("original_text", None)
                    # Overwrite memory (Python doesn't guarantee this, but we try)
                    del original_text
                    original_text = None
            
            # Clean up temp file if we created one
            if temp_file_path != file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass

            # Step 2: Analyze with GPT-4o
            logger.info(f"[{job_id}] Analyzing with GPT-4o...")
            db.update_call(job_id, status="analyzing")

            analysis = analyzer.analyze(
                transcript=transcription["redacted_text"],
                duration_min=transcription.get("duration_min", 0),
            )

            # Step 3: Compute call stats
            logger.info(f"[{job_id}] Computing call stats...")
            stats = analyzer.compute_stats(transcription.get("segments", []))

            # Step 3.5: Enhanced analytics
            logger.info(f"[{job_id}] Running enhanced analytics...")
            enhanced_analytics = analytics_service.analyze_call(
                transcript=transcription["redacted_text"],
                segments=transcription.get("segments", []),
            )

            # Step 3.6: Conversation intelligence analysis
            logger.info(f"[{job_id}] Running conversation intelligence...")
            conv_intel_service = services.get("conversation_intel")
            conv_intel = None
            if conv_intel_service:
                conv_intel = conv_intel_service.analyze(
                    segments=transcription.get("segments", []),
                    transcript=transcription["redacted_text"],
                )
            
            # Step 3.7: Keyword tracking and call phase detection
            logger.info(f"[{job_id}] Running keyword tracking...")
            keyword_service = services.get("keyword_tracking")
            keywords_data = None
            call_phases = None
            if keyword_service:
                keywords_data = keyword_service.detect_keywords(
                    call_id=job_id,
                    transcript=transcription["redacted_text"],
                    segments=transcription.get("segments", []),
                    user_email=user_email,
                    save_occurrences=True,
                )
                call_phases = keyword_service.detect_call_phases(
                    segments=transcription.get("segments", []),
                )
            
            # Step 3.8: Generate call score
            logger.info(f"[{job_id}] Generating call score...")
            scoring_service = services.get("scoring")
            call_score = None
            if scoring_service:
                call_score = scoring_service.score_call(
                    call_id=job_id,
                    transcript=transcription["redacted_text"],
                    stats=stats,
                    user_email=user_email,
                )

            # Step 4: Generate PDFs
            logger.info(f"[{job_id}] Generating PDFs...")
            db.update_call(job_id, status="generating_pdf")

            coaching_pdf_path = os.path.join(config.UPLOAD_FOLDER, f"{job_id}_coaching.pdf")
            stats_pdf_path = os.path.join(config.UPLOAD_FOLDER, f"{job_id}_stats.pdf")

            pdf_generator.generate_coaching_report(
                analysis=analysis,
                output_path=coaching_pdf_path,
                score_data=call_score,
                conv_intel=conv_intel,
                keywords_data=keywords_data,
            )
            pdf_generator.generate_stats_report(
                stats=stats,
                output_path=stats_pdf_path,
                conv_intel=conv_intel,
            )

            # Step 5: Send email
            logger.info(f"[{job_id}] Sending email...")
            db.update_call(job_id, status="sending_email")

            email_sender.send_report(
                to_email=user_email,
                subject=f"Call Analysis: {filename}",
                coaching_pdf_path=coaching_pdf_path,
                stats_pdf_path=stats_pdf_path,
            )

            # Save all data to database
            stats["enhanced_analytics"] = enhanced_analytics
            stats["conversation_intelligence"] = conv_intel
            stats["keywords"] = keywords_data
            stats["call_phases"] = call_phases

            # SECURITY: Remove original_text before storing in database
            # Only redacted data should be persisted
            transcription_safe = transcription.copy()
            transcription_safe.pop("original_text", None)  # Remove unredacted text

            from datetime import datetime
            db.update_call(
                job_id,
                status="complete",
                completed_at=datetime.utcnow().isoformat(),
                transcription_json=transcription_safe,  # Safe version without original_text
                analysis_json=analysis,
                stats_json=stats,
                coaching_pdf_path=coaching_pdf_path,
                stats_pdf_path=stats_pdf_path,
            )

            # SECURITY: Clean up audio file securely
            secure_storage.delete_file_secure(file_path)

            logger.info(f"[{job_id}] Analysis complete!")

        except ValueError as e:
            # Handle known validation errors with user-friendly messages
            logger.warning(f"[{job_id}] Validation error: {e}")
            
            db = services["database"]
            # ValueError messages are already user-friendly, so use them directly
            db.update_call(job_id, status="error", error=str(e))
            
            # SECURITY: Clean up file even on error
            try:
                secure_storage.delete_file_secure(file_path)
            except Exception:
                pass
        except Exception as e:
            # SECURITY: Use safe exception logging
            safe_log_exception(logger, f"[{job_id}] Analysis failed", exc_info=True)
            
            db = services["database"]
            # Sanitize error message before storing
            error_msg = sanitize_string(str(e))
            db.update_call(job_id, status="error", error=error_msg)
            
            # SECURITY: Clean up file even on error
            try:
                secure_storage.delete_file_secure(file_path)
            except Exception:
                pass
        finally:
            # SECURITY: Ensure original_text is cleared from memory
            if original_text:
                del original_text
            if transcription and "original_text" in transcription:
                transcription.pop("original_text", None)
            
            self._active_jobs.discard(job_id)

