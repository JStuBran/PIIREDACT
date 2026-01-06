"""Enhanced analytics service for sales calls."""

import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Enhanced analytics for sales calls."""

    def __init__(self):
        """Initialize the analytics service."""
        logger.info("AnalyticsService initialized")

    def analyze_call(
        self,
        transcript: str,
        segments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Perform enhanced analysis on a call.

        Args:
            transcript: The redacted transcript text
            segments: List of transcript segments with timestamps

        Returns:
            Dict with enhanced analytics
        """
        results = {
            "sentiment": self._analyze_sentiment(transcript),
            "keywords": self._detect_keywords(transcript),
            "silences": self._detect_silences(segments),
            "interruptions": self._detect_interruptions(segments),
            "call_structure": self._analyze_structure(transcript, segments),
        }
        
        return results

    def _analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment throughout the call.
        
        Simple keyword-based sentiment (can be enhanced with ML).
        """
        positive_words = [
            "great", "excellent", "perfect", "wonderful", "amazing", "love", "happy",
            "pleased", "satisfied", "good", "yes", "absolutely", "definitely", "sure",
            "excited", "interested", "sounds good", "perfect", "ideal"
        ]
        
        negative_words = [
            "bad", "terrible", "awful", "hate", "disappointed", "frustrated", "worried",
            "concerned", "problem", "issue", "no", "not", "don't", "can't", "won't",
            "unhappy", "unsatisfied", "disappointed"
        ]
        
        text_lower = text.lower()
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        total_sentiment_words = positive_count + negative_count
        
        if total_sentiment_words == 0:
            sentiment_score = 0.5  # Neutral
        else:
            sentiment_score = positive_count / total_sentiment_words
        
        # Classify sentiment
        if sentiment_score >= 0.7:
            sentiment_label = "positive"
        elif sentiment_score <= 0.3:
            sentiment_label = "negative"
        else:
            sentiment_label = "neutral"
        
        return {
            "score": round(sentiment_score, 2),
            "label": sentiment_label,
            "positive_words": positive_count,
            "negative_words": negative_count,
        }

    def _detect_keywords(self, text: str) -> Dict[str, Any]:
        """
        Detect important sales keywords and phrases.
        """
        keyword_patterns = {
            "value_proposition": [
                r"value", r"benefit", r"advantage", r"solution", r"help",
                r"improve", r"increase", r"reduce", r"save"
            ],
            "next_steps": [
                r"next step", r"follow up", r"schedule", r"meeting", r"call",
                r"send", r"email", r"proposal", r"quote"
            ],
            "objection_handling": [
                r"concern", r"worry", r"issue", r"problem", r"but", r"however",
                r"although", r"price", r"cost", r"expensive"
            ],
            "closing": [
                r"close", r"deal", r"agreement", r"contract", r"sign", r"commit",
                r"decision", r"approve", r"purchase", r"buy"
            ],
            "discovery": [
                r"tell me", r"what", r"how", r"why", r"when", r"where",
                r"understand", r"learn", r"explore"
            ],
        }
        
        text_lower = text.lower()
        keyword_counts = {}
        keyword_mentions = {}
        
        for category, patterns in keyword_patterns.items():
            count = 0
            mentions = []
            
            for pattern in patterns:
                matches = re.finditer(pattern, text_lower, re.IGNORECASE)
                for match in matches:
                    count += 1
                    # Get context around match
                    start = max(0, match.start() - 20)
                    end = min(len(text), match.end() + 20)
                    context = text[start:end].strip()
                    mentions.append(context)
            
            keyword_counts[category] = count
            keyword_mentions[category] = mentions[:5]  # Top 5 mentions
        
        return {
            "counts": keyword_counts,
            "mentions": keyword_mentions,
        }

    def _detect_silences(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detect long silences/pauses between segments.
        """
        if len(segments) < 2:
            return {
                "total_silences": 0,
                "long_silences": 0,
                "avg_gap": 0,
            }
        
        gaps = []
        long_silences = []
        
        for i in range(len(segments) - 1):
            current_end = segments[i].get("end", 0)
            next_start = segments[i + 1].get("start", 0)
            gap = next_start - current_end
            
            if gap > 0:
                gaps.append(gap)
                
                # Consider > 3 seconds as a long silence
                if gap > 3.0:
                    long_silences.append({
                        "start": current_end,
                        "end": next_start,
                        "duration": gap,
                    })
        
        avg_gap = sum(gaps) / len(gaps) if gaps else 0
        
        return {
            "total_silences": len(gaps),
            "long_silences": len(long_silences),
            "avg_gap": round(avg_gap, 2),
            "silence_details": long_silences[:10],  # Top 10 longest
        }

    def _detect_interruptions(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detect potential interruptions (overlapping speech or very short gaps).
        """
        if len(segments) < 2:
            return {
                "total_interruptions": 0,
                "interruption_details": [],
            }
        
        interruptions = []
        
        for i in range(len(segments) - 1):
            current_end = segments[i].get("end", 0)
            next_start = segments[i + 1].get("start", 0)
            gap = next_start - current_end
            
            # Very short gap (< 0.5s) might indicate interruption
            if gap < 0.5 and gap >= 0:
                interruptions.append({
                    "timestamp": current_end,
                    "gap": gap,
                })
        
        return {
            "total_interruptions": len(interruptions),
            "interruption_details": interruptions[:10],
        }

    def _analyze_structure(
        self,
        transcript: str,
        segments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyze call structure (opening, discovery, presentation, closing).
        """
        if not segments:
            return {
                "phases": {},
                "phase_distribution": {},
            }
        
        total_duration = segments[-1].get("end", 0) if segments else 0
        if total_duration == 0:
            return {
                "phases": {},
                "phase_distribution": {},
            }
        
        # Divide call into quarters
        quarter1_end = total_duration * 0.25
        quarter2_end = total_duration * 0.50
        quarter3_end = total_duration * 0.75
        
        phases = {
            "opening": {"start": 0, "end": quarter1_end, "text": "", "duration": quarter1_end},
            "discovery": {"start": quarter1_end, "end": quarter2_end, "text": "", "duration": quarter2_end - quarter1_end},
            "presentation": {"start": quarter2_end, "end": quarter3_end, "text": "", "duration": quarter3_end - quarter2_end},
            "closing": {"start": quarter3_end, "end": total_duration, "text": "", "duration": total_duration - quarter3_end},
        }
        
        # Assign segments to phases
        for segment in segments:
            seg_start = segment.get("start", 0)
            seg_text = segment.get("text", "")
            
            for phase_name, phase_data in phases.items():
                if phase_data["start"] <= seg_start < phase_data["end"]:
                    phases[phase_name]["text"] += " " + seg_text
        
        # Calculate phase distribution
        phase_distribution = {}
        for phase_name, phase_data in phases.items():
            pct = (phase_data["duration"] / total_duration * 100) if total_duration > 0 else 0
            phase_distribution[phase_name] = round(pct, 1)
        
        return {
            "phases": phases,
            "phase_distribution": phase_distribution,
            "total_duration": total_duration,
        }

