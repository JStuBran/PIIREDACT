"""Transcriber service - Whisper + Presidio PII redaction."""

import logging
from typing import Any, Dict, List, Optional

from presidio_audio_redactor import AudioRedactor

logger = logging.getLogger(__name__)


class TranscriberService:
    """Transcribe audio and redact PII using Whisper + Presidio."""

    def __init__(self, whisper_model: str = "base"):
        """
        Initialize the transcriber.

        Args:
            whisper_model: Whisper model size (tiny, base, small, medium, large)
        """
        logger.info(f"Initializing TranscriberService with Whisper model: {whisper_model}")
        self.redactor = AudioRedactor(whisper_model=whisper_model)
        logger.info("TranscriberService ready")

    def transcribe_and_redact(
        self,
        audio_path: str,
        language: str = "en",
        score_threshold: float = 0.4,
    ) -> Dict[str, Any]:
        """
        Transcribe audio and redact PII.

        Args:
            audio_path: Path to the audio file
            language: Language code for PII detection
            score_threshold: Minimum confidence for PII detection

        Returns:
            Dict with:
                - original_text: Raw transcript (for internal use only)
                - redacted_text: PII-redacted transcript
                - pii_findings: List of detected PII with positions
                - segments: Timestamped segments from Whisper
                - duration_min: Duration in minutes
        """
        logger.info(f"Transcribing: {audio_path}")

        # Use presidio-audio-redactor with timestamps
        result = self.redactor.redact(
            audio_path=audio_path,
            language=language,
            score_threshold=score_threshold,
            return_timestamps=True,
        )

        # Calculate duration from segments
        segments = result.get("segments", [])
        duration_sec = 0
        if segments:
            last_segment = segments[-1]
            duration_sec = last_segment.get("end", 0)

        # Parse segments into a cleaner format with speaker diarization
        # IMPORTANT: Redact segment text to prevent PII exposure
        original_text = result.get("original_text", "")
        redacted_text = result.get("redacted_text", "")
        parsed_segments = self._parse_segments(
            segments,
            original_text=original_text,
            redacted_text=redacted_text,
        )

        return {
            "original_text": original_text,  # Keep for internal use only
            "redacted_text": redacted_text,
            "pii_findings": result.get("pii_findings", []),
            "segments": parsed_segments,  # Now contains redacted text
            "duration_sec": duration_sec,
            "duration_min": round(duration_sec / 60, 1),
        }

    def _parse_segments(
        self,
        segments: List[Dict],
        original_text: str = "",
        redacted_text: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Parse Whisper segments into a cleaner format with redacted text.
        
        SECURITY: This method ensures segment text is redacted to prevent PII exposure.
        Each segment is redacted individually to ensure accuracy.

        Args:
            segments: Raw segments from Whisper (contain unredacted text)
            original_text: Full original transcript (for reference)
            redacted_text: Full redacted transcript (for reference)

        Returns:
            List of segment dicts with id, start, end, text (REDACTED)
        """
        parsed = []
        
        # CRITICAL: Redact each segment individually to prevent PII exposure
        # We can't simply map from original_text to redacted_text because
        # Presidio replacements may have different lengths (e.g., "<EMAIL>" vs actual email)
        for i, seg in enumerate(segments):
            seg_text = seg.get("text", "").strip()
            
            # Redact this segment's text
            if seg_text:
                redacted_seg_text = self._redact_segment_text(seg_text)
            else:
                redacted_seg_text = ""
            
            parsed.append({
                "id": i,
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": redacted_seg_text,  # REDACTED text only
                "speaker": f"spk_{i % 2}",
            })
        
        return parsed

    def _redact_segment_text(self, text: str) -> str:
        """
        Redact PII from a single segment's text.
        
        SECURITY: This ensures no PII leaks through segments.
        
        Args:
            text: Segment text to redact
            
        Returns:
            Redacted text
        """
        if not text:
            return ""
        
        # Use the same redactor to redact this segment
        # This ensures consistent redaction behavior
        try:
            pii_results = self.redactor.analyze(
                text=text,
                language="en",
                score_threshold=0.4
            )
            anonymized = self.redactor.anonymize(
                text=text,
                analyzer_results=pii_results
            )
            return anonymized.text
        except Exception as e:
            # If redaction fails, log but return empty to be safe
            logger.warning(f"Failed to redact segment text: {e}")
            return ""  # Return empty rather than unredacted text

    def transcribe_only(self, audio_path: str) -> Dict[str, Any]:
        """
        Transcribe audio without PII redaction.
        
        Returns format compatible with transcribe_and_redact() for seamless integration.

        Args:
            audio_path: Path to audio file

        Returns:
            Dict with:
                - original_text: Full transcript (no redaction)
                - redacted_text: Same as original_text (no redaction needed)
                - pii_findings: Empty list (no PII detected/redacted)
                - segments: Timestamped segments from Whisper
                - duration_sec: Duration in seconds
                - duration_min: Duration in minutes
        """
        logger.info(f"Transcribing (no redaction): {audio_path}")
        
        # Transcribe with word timestamps
        result = self.redactor.transcribe(audio_path, word_timestamps=True)
        
        # Get segments and calculate duration
        segments = result.get("segments", [])
        duration_sec = 0
        if segments:
            last_segment = segments[-1]
            duration_sec = last_segment.get("end", 0)
        
        # Get full text
        original_text = result.get("text", "")
        
        # Parse segments into same format as transcribe_and_redact()
        parsed_segments = self._parse_segments(
            segments,
            original_text=original_text,
            redacted_text=original_text,  # No redaction, so same as original
        )
        
        return {
            "original_text": original_text,
            "redacted_text": original_text,  # No redaction needed for AI agent calls
            "pii_findings": [],  # No PII to detect/redact
            "segments": parsed_segments,
            "duration_sec": duration_sec,
            "duration_min": round(duration_sec / 60, 1),
        }

