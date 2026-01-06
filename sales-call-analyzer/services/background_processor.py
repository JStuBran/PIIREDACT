"""Background job processor for async call analysis."""

import logging
import threading
from typing import Any, Dict

logger = logging.getLogger(__name__)


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
        try:
            db = services["database"]
            transcriber = services["transcriber"]
            analyzer = services["analyzer"]
            analytics_service = services["analytics"]
            pdf_generator = services["pdf_generator"]
            email_sender = services["email_sender"]

            # Step 1: Transcribe and redact
            logger.info(f"[{job_id}] Starting transcription...")
            db.update_call(job_id, status="transcribing")

            transcription = transcriber.transcribe_and_redact(file_path)

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

            # Step 4: Generate PDFs
            logger.info(f"[{job_id}] Generating PDFs...")
            db.update_call(job_id, status="generating_pdf")

            import os
            coaching_pdf_path = os.path.join(config.UPLOAD_FOLDER, f"{job_id}_coaching.pdf")
            stats_pdf_path = os.path.join(config.UPLOAD_FOLDER, f"{job_id}_stats.pdf")

            pdf_generator.generate_coaching_report(analysis, coaching_pdf_path)
            pdf_generator.generate_stats_report(stats, stats_pdf_path)

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

            # Clean up audio file
            try:
                os.unlink(file_path)
            except Exception:
                pass

            logger.info(f"[{job_id}] Analysis complete!")

        except Exception as e:
            logger.exception(f"[{job_id}] Analysis failed: {e}")
            db = services["database"]
            db.update_call(job_id, status="error", error=str(e))
        finally:
            self._active_jobs.discard(job_id)

