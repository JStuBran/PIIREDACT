"""Background job processor for async call analysis."""

import logging
import os
import threading
from typing import Any, Dict

from .logging_security import get_secure_logger, safe_log_exception, sanitize_string

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
        transcription: Dict[str, Any],
        user_email: str,
        services: Dict[str, Any],
        config: Any,
    ):
        """
        Process a call in a background thread.

        Args:
            job_id: Call ID
            transcription: Pre-parsed transcript data from ElevenLabs webhook
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
            args=(job_id, transcription, user_email, services, config),
            daemon=True,
        )
        thread.start()
        logger.info(f"[{job_id}] Started background processing thread")

    def _process_call(
        self,
        job_id: str,
        transcription: Dict[str, Any],
        user_email: str,
        services: Dict[str, Any],
        config: Any,
    ):
        """Internal method to process the call."""
        try:
            db = services["database"]
            analyzer = services["analyzer"]
            analytics_service = services["analytics"]
            pdf_generator = services["pdf_generator"]
            email_sender = services["email_sender"]

            # Step 1: Analyze with GPT-4o
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
            enhanced_analytics = analytics_service.analyze_call(
                transcript=transcription["text"],
                segments=transcription.get("segments", []),
            )

            # Step 4: Conversation intelligence analysis
            logger.info(f"[{job_id}] Running conversation intelligence...")
            conv_intel_service = services.get("conversation_intel")
            conv_intel = None
            if conv_intel_service:
                conv_intel = conv_intel_service.analyze(
                    segments=transcription.get("segments", []),
                    transcript=transcription["text"],
                )
            
            # Step 5: Keyword tracking and call phase detection
            logger.info(f"[{job_id}] Running keyword tracking...")
            keyword_service = services.get("keyword_tracking")
            keywords_data = None
            call_phases = None
            if keyword_service:
                keywords_data = keyword_service.detect_keywords(
                    call_id=job_id,
                    transcript=transcription["text"],
                    segments=transcription.get("segments", []),
                    user_email=user_email,
                    save_occurrences=True,
                )
                call_phases = keyword_service.detect_call_phases(
                    segments=transcription.get("segments", []),
                )
            
            # Step 6: Generate call score
            logger.info(f"[{job_id}] Generating call score...")
            scoring_service = services.get("scoring")
            call_score = None
            if scoring_service:
                call_score = scoring_service.score_call(
                    call_id=job_id,
                    transcript=transcription["text"],
                    stats=stats,
                    user_email=user_email,
                )

            # Step 7: Generate PDFs
            logger.info(f"[{job_id}] Generating PDFs...")
            db.update_call(job_id, status="generating_pdf")

            # Ensure output directory exists
            output_dir = os.environ.get("OUTPUT_DIR", "/tmp/sales-call-analyzer")
            os.makedirs(output_dir, exist_ok=True)

            coaching_pdf_path = os.path.join(output_dir, f"{job_id}_coaching.pdf")
            stats_pdf_path = os.path.join(output_dir, f"{job_id}_stats.pdf")

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

            # Step 8: Send email
            logger.info(f"[{job_id}] Sending email...")
            db.update_call(job_id, status="sending_email")

            # Get agent name for email subject
            agent_name = transcription.get("agent_name", "AI Agent")
            
            email_sender.send_report(
                to_email=user_email,
                subject=f"Call Analysis: {agent_name} Call",
                coaching_pdf_path=coaching_pdf_path,
                stats_pdf_path=stats_pdf_path,
            )

            # Save all data to database
            stats["enhanced_analytics"] = enhanced_analytics
            stats["conversation_intelligence"] = conv_intel
            stats["keywords"] = keywords_data
            stats["call_phases"] = call_phases

            from datetime import datetime
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

        except ValueError as e:
            # Handle known validation errors with user-friendly messages
            logger.warning(f"[{job_id}] Validation error: {e}")
            
            db = services["database"]
            db.update_call(job_id, status="error", error=str(e))
            
        except Exception as e:
            # Use safe exception logging
            safe_log_exception(logger, f"[{job_id}] Analysis failed", exc_info=True)
            
            db = services["database"]
            # Sanitize error message before storing
            error_msg = sanitize_string(str(e))
            db.update_call(job_id, status="error", error=error_msg)
            
        finally:
            self._active_jobs.discard(job_id)

