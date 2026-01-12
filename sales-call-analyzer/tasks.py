"""Celery tasks for async job processing."""

import logging
import os
from datetime import datetime
from typing import Any, Dict

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
def process_webhook_call_task(
    self,
    job_id: str,
    transcription: Dict[str, Any],
    user_email: str,
):
    """
    Process a call from ElevenLabs webhook asynchronously.
    
    This task handles the analysis pipeline:
    1. AI analysis with GPT-4o
    2. Statistics computation
    3. Conversation intelligence
    4. Keyword detection
    5. Call scoring
    6. PDF generation
    7. Email notification
    """
    from services import (
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
    analyzer = AnalyzerService(api_key=Config.OPENAI_API_KEY, model=Config.OPENAI_MODEL)
    analytics = AnalyticsService()
    pdf_generator = PDFGeneratorService()
    email_sender = EmailSenderService()
    scoring = ScoringService(api_key=Config.OPENAI_API_KEY, model=Config.OPENAI_MODEL)
    conv_intel = ConversationIntelligenceService()
    keyword_tracking = KeywordTrackingService()
    
    try:
        # Step 1: Analyze with GPT-4o
        self.update_state(state="ANALYZING", meta={"step": "analyzing"})
        logger.info(f"[{job_id}] Analyzing with GPT-4o...")
        db.update_call(job_id, status="analyzing")
        
        analysis = analyzer.analyze(
            transcript=transcription["text"],
            duration_min=transcription.get("duration_min", 0),
        )
        
        # Step 2: Compute call stats
        logger.info(f"[{job_id}] Computing call stats...")
        stats = analyzer.compute_stats(transcription.get("segments", []))
        
        # Step 3: Enhanced analytics
        logger.info(f"[{job_id}] Running enhanced analytics...")
        enhanced_analytics = analytics.analyze_call(
            transcript=transcription["text"],
            segments=transcription.get("segments", []),
        )
        
        # Step 4: Conversation intelligence
        logger.info(f"[{job_id}] Running conversation intelligence...")
        conv_intel_data = conv_intel.analyze(
            segments=transcription.get("segments", []),
            transcript=transcription["text"],
        )
        
        # Step 5: Keyword tracking
        logger.info(f"[{job_id}] Running keyword tracking...")
        keywords_data = keyword_tracking.detect_keywords(
            call_id=job_id,
            transcript=transcription["text"],
            segments=transcription.get("segments", []),
            user_email=user_email,
            save_occurrences=True,
        )
        call_phases = keyword_tracking.detect_call_phases(
            segments=transcription.get("segments", []),
        )
        
        # Step 6: Generate call score
        logger.info(f"[{job_id}] Generating call score...")
        call_score = scoring.score_call(
            call_id=job_id,
            transcript=transcription["text"],
            stats=stats,
            user_email=user_email,
        )
        
        # Step 7: Generate PDFs
        self.update_state(state="GENERATING_PDF", meta={"step": "generating_pdf"})
        logger.info(f"[{job_id}] Generating PDFs...")
        db.update_call(job_id, status="generating_pdf")
        
        output_dir = os.environ.get("OUTPUT_DIR", "/tmp/sales-call-analyzer")
        os.makedirs(output_dir, exist_ok=True)
        
        coaching_pdf_path = os.path.join(output_dir, f"{job_id}_coaching.pdf")
        stats_pdf_path = os.path.join(output_dir, f"{job_id}_stats.pdf")
        
        pdf_generator.generate_coaching_report(
            analysis=analysis,
            output_path=coaching_pdf_path,
            score_data=call_score,
            conv_intel=conv_intel_data,
            keywords_data=keywords_data,
        )
        pdf_generator.generate_stats_report(
            stats=stats,
            output_path=stats_pdf_path,
            conv_intel=conv_intel_data,
        )
        
        # Step 8: Send email
        self.update_state(state="SENDING_EMAIL", meta={"step": "sending_email"})
        logger.info(f"[{job_id}] Sending email...")
        db.update_call(job_id, status="sending_email")
        
        agent_name = transcription.get("agent_name", "AI Agent")
        
        email_sender.send_report(
            to_email=user_email,
            subject=f"Call Analysis: {agent_name} Call",
            coaching_pdf_path=coaching_pdf_path,
            stats_pdf_path=stats_pdf_path,
        )
        
        # Save all data to database
        stats["enhanced_analytics"] = enhanced_analytics
        stats["conversation_intelligence"] = conv_intel_data
        stats["keywords"] = keywords_data
        stats["call_phases"] = call_phases
        
        db.update_call(
            job_id,
            status="complete",
            completed_at=datetime.utcnow().isoformat(),
            transcription_json=transcription,
            analysis_json=analysis,
            stats_json=stats,
            coaching_pdf_path=coaching_pdf_path,
            stats_pdf_path=stats_pdf_path,
        )
        
        logger.info(f"[{job_id}] Analysis complete!")
        
        return {
            "job_id": job_id,
            "status": "complete",
            "score": call_score.get("overall_score") if call_score else None,
        }
        
    except Exception as e:
        from services.logging_security import safe_log_exception, sanitize_string
        safe_log_exception(logger, f"[{job_id}] Analysis failed", exc_info=True)
        
        error_msg = sanitize_string(str(e))
        db.update_call(job_id, status="error", error=error_msg)
        
        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)
        
        raise


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
    from datetime import timedelta
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

