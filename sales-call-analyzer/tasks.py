"""Celery tasks for async job processing."""

import logging
import os
from datetime import datetime
from typing import Optional

from celery import Celery

from config import Config

logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery(
    "sales_call_analyzer",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes max per task
    worker_prefetch_multiplier=1,  # One task at a time for CPU-intensive work
    result_expires=86400,  # Results expire after 24 hours
)


@celery_app.task(bind=True, max_retries=2)
def process_call_task(
    self,
    job_id: str,
    file_path: str,
    filename: str,
    user_email: str,
):
    """
    Process a sales call asynchronously.
    
    This task handles the full analysis pipeline:
    1. Transcription with Whisper
    2. PII redaction with Presidio
    3. AI analysis with GPT-4o
    4. Statistics computation
    5. Conversation intelligence
    6. Keyword detection
    7. Call scoring
    8. PDF generation
    9. Email notification
    """
    from services import (
        TranscriberService,
        AnalyzerService,
        PDFGeneratorService,
        EmailSenderService,
        DatabaseService,
        AnalyticsService,
        ScoringService,
        ConversationIntelligenceService,
        KeywordTrackingService,
    )
    
    logger.info(f"[{job_id}] Starting Celery task processing...")
    
    # Initialize services
    db = DatabaseService()
    transcriber = TranscriberService(whisper_model=Config.WHISPER_MODEL)
    analyzer = AnalyzerService(api_key=Config.OPENAI_API_KEY, model=Config.OPENAI_MODEL)
    analytics = AnalyticsService()
    pdf_generator = PDFGeneratorService()
    email_sender = EmailSenderService()
    scoring = ScoringService(api_key=Config.OPENAI_API_KEY, model=Config.OPENAI_MODEL)
    conv_intel = ConversationIntelligenceService()
    keyword_tracking = KeywordTrackingService()
    
    try:
        # Update task state
        self.update_state(state="TRANSCRIBING", meta={"step": "transcribing"})
        
        # Get call record to check call_type
        call_record = db.get_call(job_id)
        call_type = call_record.get("call_type", "real") if call_record else "real"
        
        # Step 1: Transcribe (with or without redaction based on call type)
        if call_type == "ai_agent":
            logger.info(f"[{job_id}] Starting transcription (AI agent call - no redaction)...")
        else:
            logger.info(f"[{job_id}] Starting transcription (real call - with PII redaction)...")
        
        db.update_call(job_id, status="transcribing")
        
        # SECURITY: Read encrypted file if needed
        from services.secure_storage import SecureStorageService
        secure_storage = SecureStorageService()
        
        try:
            # Try to read as encrypted file first
            file_content = secure_storage.read_file_secure(file_path)
            # Write to temp file for transcription
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_path)[1]) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
        except Exception:
            # Fallback to direct file path (for unencrypted files)
            temp_file_path = file_path
        
        # Conditionally transcribe based on call type
        if call_type == "ai_agent":
            # AI agent calls: no PII redaction needed
            transcription = transcriber.transcribe_only(temp_file_path)
            # For AI agent calls, original_text and redacted_text are the same
            # No need to clear original_text since it's not sensitive
        else:
            # Real calls: transcribe with PII redaction
            transcription = transcriber.transcribe_and_redact(temp_file_path)
            
            # SECURITY: Clear original_text from memory immediately
            original_text = transcription.get("original_text")
            if original_text:
                transcription.pop("original_text", None)
                del original_text
        
        # Clean up temp file if we created one
        if temp_file_path != file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass
        
        # Step 2: Analyze with GPT-4o
        self.update_state(state="ANALYZING", meta={"step": "analyzing"})
        logger.info(f"[{job_id}] Analyzing with GPT-4o...")
        db.update_call(job_id, status="analyzing")
        
        analysis = analyzer.analyze(
            transcript=transcription["redacted_text"],
            duration_min=transcription.get("duration_min", 0),
        )
        
        # Step 3: Compute call stats
        logger.info(f"[{job_id}] Computing call stats...")
        stats = analyzer.compute_stats(transcription.get("segments", []))
        
        # Step 4: Enhanced analytics
        logger.info(f"[{job_id}] Running enhanced analytics...")
        enhanced_analytics = analytics.analyze_call(
            transcript=transcription["redacted_text"],
            segments=transcription.get("segments", []),
        )
        
        # Step 5: Conversation intelligence
        logger.info(f"[{job_id}] Running conversation intelligence...")
        conv_intel_data = conv_intel.analyze(
            segments=transcription.get("segments", []),
            transcript=transcription["redacted_text"],
        )
        
        # Step 6: Keyword tracking
        logger.info(f"[{job_id}] Running keyword tracking...")
        keywords_data = keyword_tracking.detect_keywords(
            call_id=job_id,
            transcript=transcription["redacted_text"],
            segments=transcription.get("segments", []),
            user_email=user_email,
            save_occurrences=True,
        )
        call_phases = keyword_tracking.detect_call_phases(
            segments=transcription.get("segments", []),
        )
        
        # Step 7: Generate call score
        logger.info(f"[{job_id}] Generating call score...")
        call_score = scoring.score_call(
            call_id=job_id,
            transcript=transcription["redacted_text"],
            stats=stats,
            user_email=user_email,
        )
        
        # Step 8: Generate PDFs
        self.update_state(state="GENERATING_PDF", meta={"step": "generating_pdf"})
        logger.info(f"[{job_id}] Generating PDFs...")
        db.update_call(job_id, status="generating_pdf")
        
        coaching_pdf_path = os.path.join(Config.UPLOAD_FOLDER, f"{job_id}_coaching.pdf")
        stats_pdf_path = os.path.join(Config.UPLOAD_FOLDER, f"{job_id}_stats.pdf")
        
        pdf_generator.generate_coaching_report(analysis, coaching_pdf_path)
        pdf_generator.generate_stats_report(stats, stats_pdf_path)
        
        # Step 9: Send email
        self.update_state(state="SENDING_EMAIL", meta={"step": "sending_email"})
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
        stats["conversation_intelligence"] = conv_intel_data
        stats["keywords"] = keywords_data
        stats["call_phases"] = call_phases
        
        # SECURITY: Remove original_text before storing (already removed, but double-check)
        transcription_safe = transcription.copy()
        transcription_safe.pop("original_text", None)
        
        # SECURITY: Ensure original_text is cleared from memory
        if "original_text" in transcription:
            del transcription["original_text"]
        
        db.update_call(
            job_id,
            status="complete",
            completed_at=datetime.utcnow().isoformat(),
            transcription_json=transcription_safe,
            analysis_json=analysis,
            stats_json=stats,
            coaching_pdf_path=coaching_pdf_path,
            stats_pdf_path=stats_pdf_path,
        )
        
        # SECURITY: Clean up audio file securely
        from services.secure_storage import SecureStorageService
        secure_storage = SecureStorageService()
        secure_storage.delete_file_secure(file_path)
        
        logger.info(f"[{job_id}] Analysis complete!")
        
        return {
            "job_id": job_id,
            "status": "complete",
            "score": call_score.get("overall_score") if call_score else None,
        }
        
    except Exception as e:
        # SECURITY: Use safe exception logging
        from services.logging_security import safe_log_exception, sanitize_string
        safe_log_exception(logger, f"[{job_id}] Analysis failed", exc_info=True)
        
        # Sanitize error message before storing
        error_msg = sanitize_string(str(e))
        db.update_call(job_id, status="error", error=error_msg)
        
        # SECURITY: Clean up file even on error
        try:
            from services.secure_storage import SecureStorageService
            secure_storage = SecureStorageService()
            secure_storage.delete_file_secure(file_path)
        except Exception:
            pass
        
        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)
        
        raise


@celery_app.task
def cleanup_old_files():
    """
    Periodic task to clean up old uploaded files.
    
    Run this hourly via Celery beat.
    """
    import glob
    from datetime import datetime, timedelta
    
    logger.info("Running file cleanup task...")
    
    cutoff = datetime.now() - timedelta(hours=24)
    upload_folder = Config.UPLOAD_FOLDER
    
    count = 0
    for pattern in ["*.wav", "*.mp3", "*.m4a", "*.ogg", "*.webm"]:
        for filepath in glob.glob(os.path.join(upload_folder, pattern)):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                if mtime < cutoff:
                    os.unlink(filepath)
                    count += 1
                    logger.info(f"Deleted old file: {filepath}")
            except Exception as e:
                logger.error(f"Failed to delete {filepath}: {e}")
    
    logger.info(f"Cleanup complete. Deleted {count} files.")
    return {"deleted": count}


@celery_app.task
def send_weekly_digest(user_email: str):
    """
    Send weekly digest email with call statistics.
    """
    from services import DatabaseService, BenchmarkService, ScoringService
    
    logger.info(f"Generating weekly digest for {user_email}...")
    
    db = DatabaseService()
    benchmark = BenchmarkService()
    scoring = ScoringService(api_key=Config.OPENAI_API_KEY, model=Config.OPENAI_MODEL)
    
    # Get calls from past week
    from datetime import datetime, timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    calls = db.list_calls(
        user_email=user_email,
        status="complete",
        limit=100,
    )
    
    recent_calls = [c for c in calls if c.get("created_at", "") >= week_ago.isoformat()]
    
    if not recent_calls:
        logger.info(f"No calls this week for {user_email}")
        return {"sent": False, "reason": "no_calls"}
    
    # Calculate stats
    benchmarks = benchmark.calculate_benchmarks(calls)
    leaderboard = scoring.get_leaderboard(user_email, limit=5)
    
    # TODO: Generate and send digest email
    logger.info(f"Weekly digest generated for {user_email}: {len(recent_calls)} calls")
    
    return {
        "sent": True,
        "calls_count": len(recent_calls),
    }

