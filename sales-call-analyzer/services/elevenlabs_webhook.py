"""ElevenLabs webhook service for handling post-call webhooks."""

import hashlib
import hmac
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ElevenLabsWebhookService:
    """Handle incoming ElevenLabs post-call webhooks."""

    def __init__(self, webhook_secret: Optional[str] = None):
        """
        Initialize the webhook service.

        Args:
            webhook_secret: Secret for verifying webhook signatures
        """
        self.webhook_secret = webhook_secret
        logger.info("ElevenLabsWebhookService initialized")

    def verify_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        """
        Verify the webhook signature.

        Args:
            payload: Raw request body as bytes
            signature: Signature from X-ElevenLabs-Signature header

        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            # If no secret configured, skip verification (not recommended for production)
            logger.warning("No webhook secret configured, skipping signature verification")
            return True

        if not signature:
            logger.warning("No signature provided in webhook request")
            return False

        # ElevenLabs uses HMAC-SHA256 for webhook signatures
        expected_signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Compare signatures in constant time to prevent timing attacks
        is_valid = hmac.compare_digest(signature, expected_signature)
        
        if not is_valid:
            logger.warning("Invalid webhook signature")
        
        return is_valid

    def parse_transcript(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse ElevenLabs webhook payload into our transcript format.

        Args:
            payload: Webhook payload from ElevenLabs

        Returns:
            Dict with transcript data in our format:
                - text: Full transcript text
                - segments: List of segments with timestamps and speakers
                - duration_sec: Total call duration in seconds
                - duration_min: Total call duration in minutes
                - agent_id: ElevenLabs agent ID
                - agent_name: Agent name
                - elevenlabs_call_id: Original call ID from ElevenLabs
                - caller_id: Caller identifier (if available)
                - metadata: Additional call metadata
        """
        # Extract call metadata
        call_data = payload.get("data", payload)
        
        # Get agent info
        agent_info = call_data.get("agent", {})
        agent_id = agent_info.get("agent_id") or call_data.get("agent_id", "")
        agent_name = agent_info.get("name") or call_data.get("agent_name", "AI Agent")
        
        # Get call identifiers
        elevenlabs_call_id = call_data.get("call_id") or call_data.get("conversation_id", "")
        caller_id = call_data.get("caller_id") or call_data.get("user_id", "")
        
        # Extract transcript
        transcript_data = call_data.get("transcript", [])
        
        # If transcript is a string, convert to simple format
        if isinstance(transcript_data, str):
            segments = [{
                "id": 0,
                "start": 0.0,
                "end": 0.0,
                "text": transcript_data,
                "speaker": "agent",
            }]
            full_text = transcript_data
        else:
            # Parse structured transcript with timestamps
            segments = self._map_to_segments(transcript_data)
            full_text = self._build_full_text(segments)
        
        # Calculate duration
        duration_sec = 0.0
        if segments:
            # Get end time of last segment
            last_segment = segments[-1]
            duration_sec = last_segment.get("end", 0.0)
        
        # Also check for explicit duration in payload
        if call_data.get("duration"):
            duration_sec = float(call_data["duration"])
        elif call_data.get("duration_seconds"):
            duration_sec = float(call_data["duration_seconds"])
        
        # Extract additional metadata
        metadata = {
            "started_at": call_data.get("started_at") or call_data.get("start_time"),
            "ended_at": call_data.get("ended_at") or call_data.get("end_time"),
            "call_status": call_data.get("status", "completed"),
            "phone_number": call_data.get("phone_number"),
            "call_type": call_data.get("call_type", "inbound"),
        }
        
        return {
            "text": full_text,
            "segments": segments,
            "duration_sec": duration_sec,
            "duration_min": round(duration_sec / 60, 1),
            "agent_id": agent_id,
            "agent_name": agent_name,
            "elevenlabs_call_id": elevenlabs_call_id,
            "caller_id": caller_id,
            "metadata": metadata,
        }

    def _map_to_segments(self, transcript_data: List[Dict]) -> List[Dict[str, Any]]:
        """
        Map ElevenLabs transcript format to our segment format.

        Args:
            transcript_data: List of transcript entries from ElevenLabs

        Returns:
            List of segment dicts with:
                - id: Segment index
                - start: Start time in seconds
                - end: End time in seconds
                - text: Segment text
                - speaker: Speaker label ("agent" or "user")
        """
        segments = []
        
        for idx, entry in enumerate(transcript_data):
            # Handle different possible field names from ElevenLabs
            text = entry.get("text") or entry.get("message") or entry.get("content", "")
            
            # Get timestamps
            start = entry.get("start") or entry.get("start_time") or entry.get("timestamp", 0.0)
            end = entry.get("end") or entry.get("end_time", start)
            
            # Get speaker - normalize to "agent" or "user"
            speaker = entry.get("speaker") or entry.get("role") or entry.get("participant", "")
            speaker = self._normalize_speaker(speaker)
            
            segments.append({
                "id": idx,
                "start": float(start),
                "end": float(end),
                "text": text.strip(),
                "speaker": speaker,
            })
        
        return segments

    def _normalize_speaker(self, speaker: str) -> str:
        """
        Normalize speaker label to "agent" or "user".

        Args:
            speaker: Raw speaker label from ElevenLabs

        Returns:
            Normalized speaker label
        """
        speaker_lower = speaker.lower() if speaker else ""
        
        # Map various agent labels
        agent_labels = ["agent", "assistant", "ai", "bot", "system"]
        if any(label in speaker_lower for label in agent_labels):
            return "agent"
        
        # Map various user labels
        user_labels = ["user", "customer", "caller", "human", "client"]
        if any(label in speaker_lower for label in user_labels):
            return "user"
        
        # Default to "user" for unknown speakers
        return "user" if speaker_lower else "agent"

    def _build_full_text(self, segments: List[Dict]) -> str:
        """
        Build full transcript text from segments.

        Args:
            segments: List of segment dicts

        Returns:
            Full transcript text with speaker labels
        """
        lines = []
        for segment in segments:
            speaker = segment.get("speaker", "")
            text = segment.get("text", "")
            if speaker and text:
                # Format: [Speaker]: Text
                speaker_display = "Agent" if speaker == "agent" else "User"
                lines.append(f"[{speaker_display}]: {text}")
            elif text:
                lines.append(text)
        
        return "\n".join(lines)

    def extract_call_summary(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract call summary data if available in the webhook.

        Args:
            payload: Webhook payload from ElevenLabs

        Returns:
            Summary dict or None if not available
        """
        call_data = payload.get("data", payload)
        summary = call_data.get("summary") or call_data.get("call_summary")
        
        if not summary:
            return None
        
        if isinstance(summary, str):
            return {"summary": summary}
        
        return summary

