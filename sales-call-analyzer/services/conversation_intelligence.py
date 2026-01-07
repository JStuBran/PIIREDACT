"""Conversation Intelligence service - advanced call analysis metrics."""

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ConversationIntelligenceService:
    """
    Service for advanced conversation analysis metrics.
    
    Provides:
    - Talk-to-listen ratios
    - Monologue detection
    - Question quality analysis
    - Objection detection
    - Engagement patterns
    - Speaking pace analysis
    """

    # Open-ended question starters
    OPEN_QUESTION_STARTERS = [
        "what", "how", "why", "tell me", "describe", "explain",
        "walk me through", "help me understand", "in what way",
        "can you elaborate", "what's your", "what are your",
    ]
    
    # Closed question starters
    CLOSED_QUESTION_STARTERS = [
        "is", "are", "do", "does", "did", "can", "could", "would",
        "will", "have", "has", "was", "were", "should",
    ]
    
    # Discovery question keywords (SPIN-style)
    DISCOVERY_KEYWORDS = [
        "challenges", "problems", "issues", "pain points", "struggling",
        "goals", "objectives", "looking to achieve", "priorities",
        "currently", "today", "right now", "at the moment",
        "impact", "affect", "consequence", "result",
        "budget", "timeline", "decision", "stakeholders",
    ]
    
    # Common objection phrases
    OBJECTION_PHRASES = [
        "too expensive", "not in the budget", "can't afford",
        "need to think about", "need more time", "not ready",
        "talk to my", "check with", "get approval",
        "already have", "using another", "happy with current",
        "not interested", "not a priority", "not now",
        "send me information", "call me back", "email me",
        "too busy", "bad timing", "not the right time",
    ]
    
    # Positive sentiment indicators
    POSITIVE_INDICATORS = [
        "interested", "love", "great", "perfect", "excellent",
        "sounds good", "makes sense", "helpful", "valuable",
        "excited", "looking forward", "appreciate", "thank you",
    ]
    
    # Negative sentiment indicators
    NEGATIVE_INDICATORS = [
        "concerned", "worried", "not sure", "don't think",
        "difficult", "complicated", "confusing", "expensive",
        "problem", "issue", "frustrated", "disappointed",
    ]

    def __init__(self):
        """Initialize the conversation intelligence service."""
        logger.info("ConversationIntelligenceService initialized")

    def analyze(
        self,
        segments: List[Dict],
        transcript: str = "",
    ) -> Dict[str, Any]:
        """
        Perform comprehensive conversation analysis.
        
        Args:
            segments: List of transcript segments with speaker labels
            transcript: Full transcript text (optional, for additional analysis)
        
        Returns:
            Dict with analysis results
        """
        if not segments:
            return self._empty_analysis()
        
        # Basic speaker analysis
        speaker_analysis = self._analyze_speakers(segments)
        
        # Talk ratios and patterns
        talk_patterns = self._analyze_talk_patterns(segments, speaker_analysis)
        
        # Question analysis
        question_analysis = self._analyze_questions(segments, speaker_analysis)
        
        # Monologue detection
        monologues = self._detect_monologues(segments, speaker_analysis)
        
        # Objection analysis
        objections = self._detect_objections(segments, speaker_analysis)
        
        # Engagement analysis
        engagement = self._analyze_engagement(segments, speaker_analysis)
        
        # Sentiment timeline
        sentiment = self._analyze_sentiment_timeline(segments, speaker_analysis)
        
        # Speaking pace
        pace = self._analyze_speaking_pace(segments, speaker_analysis)
        
        return {
            "speakers": speaker_analysis,
            "talk_patterns": talk_patterns,
            "questions": question_analysis,
            "monologues": monologues,
            "objections": objections,
            "engagement": engagement,
            "sentiment": sentiment,
            "pace": pace,
        }

    def _analyze_speakers(self, segments: List[Dict]) -> Dict[str, Any]:
        """Identify and analyze speakers."""
        speaker_data = defaultdict(lambda: {
            "total_time": 0,
            "total_words": 0,
            "segments": 0,
            "texts": [],
        })
        
        for seg in segments:
            speaker = seg.get("speaker", "unknown")
            duration = seg.get("end", 0) - seg.get("start", 0)
            text = seg.get("text", "")
            words = len(text.split())
            
            speaker_data[speaker]["total_time"] += duration
            speaker_data[speaker]["total_words"] += words
            speaker_data[speaker]["segments"] += 1
            speaker_data[speaker]["texts"].append(text)
        
        # Determine agent vs customer (agent usually talks first and more)
        speakers = list(speaker_data.keys())
        if len(speakers) >= 2:
            # Heuristic: first speaker is usually the agent
            agent = speakers[0]
            customer = speakers[1]
        elif len(speakers) == 1:
            agent = speakers[0]
            customer = None
        else:
            agent = "unknown"
            customer = None
        
        return {
            "agent": agent,
            "customer": customer,
            "data": dict(speaker_data),
            "total_speakers": len(speakers),
        }

    def _analyze_talk_patterns(
        self,
        segments: List[Dict],
        speaker_analysis: Dict,
    ) -> Dict[str, Any]:
        """Analyze talk-to-listen ratios and patterns."""
        agent = speaker_analysis["agent"]
        customer = speaker_analysis["customer"]
        data = speaker_analysis["data"]
        
        # Calculate total talk time
        total_time = sum(d["total_time"] for d in data.values())
        
        agent_time = data.get(agent, {}).get("total_time", 0)
        customer_time = data.get(customer, {}).get("total_time", 0) if customer else 0
        
        # Talk ratios
        agent_ratio = round((agent_time / total_time * 100) if total_time else 0, 1)
        customer_ratio = round((customer_time / total_time * 100) if total_time else 0, 1)
        
        # Ideal talk ratio for sales is typically 40-60% agent
        talk_ratio_assessment = "balanced"
        if agent_ratio > 70:
            talk_ratio_assessment = "agent_dominated"
        elif agent_ratio < 30:
            talk_ratio_assessment = "customer_dominated"
        elif agent_ratio > 60:
            talk_ratio_assessment = "slightly_high"
        elif agent_ratio < 40:
            talk_ratio_assessment = "slightly_low"
        
        # Calculate turn-taking patterns
        turn_lengths = []
        current_speaker = None
        current_duration = 0
        
        for seg in segments:
            speaker = seg.get("speaker", "unknown")
            duration = seg.get("end", 0) - seg.get("start", 0)
            
            if speaker == current_speaker:
                current_duration += duration
            else:
                if current_speaker:
                    turn_lengths.append((current_speaker, current_duration))
                current_speaker = speaker
                current_duration = duration
        
        if current_speaker:
            turn_lengths.append((current_speaker, current_duration))
        
        # Average turn length
        agent_turns = [t[1] for t in turn_lengths if t[0] == agent]
        customer_turns = [t[1] for t in turn_lengths if t[0] == customer] if customer else []
        
        avg_agent_turn = round(sum(agent_turns) / len(agent_turns), 1) if agent_turns else 0
        avg_customer_turn = round(sum(customer_turns) / len(customer_turns), 1) if customer_turns else 0
        
        return {
            "agent_talk_ratio": agent_ratio,
            "customer_talk_ratio": customer_ratio,
            "assessment": talk_ratio_assessment,
            "agent_total_time_sec": round(agent_time, 1),
            "customer_total_time_sec": round(customer_time, 1),
            "avg_agent_turn_sec": avg_agent_turn,
            "avg_customer_turn_sec": avg_customer_turn,
            "total_turns": len(turn_lengths),
        }

    def _analyze_questions(
        self,
        segments: List[Dict],
        speaker_analysis: Dict,
    ) -> Dict[str, Any]:
        """Analyze question quality and types."""
        agent = speaker_analysis["agent"]
        agent_texts = speaker_analysis["data"].get(agent, {}).get("texts", [])
        
        open_questions = []
        closed_questions = []
        discovery_questions = []
        leading_questions = []
        
        for text in agent_texts:
            sentences = re.split(r'[.!?]+', text.lower())
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence or "?" not in text:
                    continue
                
                # Check if it's a question
                is_question = any(
                    sentence.startswith(word) or f" {word} " in sentence
                    for word in ["what", "how", "why", "when", "where", "who", "which",
                                "is", "are", "do", "does", "did", "can", "could", "would", "will"]
                )
                
                if not is_question:
                    continue
                
                # Classify question type
                is_open = any(sentence.startswith(w) for w in self.OPEN_QUESTION_STARTERS)
                is_closed = any(sentence.startswith(w) for w in self.CLOSED_QUESTION_STARTERS)
                is_discovery = any(kw in sentence for kw in self.DISCOVERY_KEYWORDS)
                is_leading = "right" in sentence or "don't you" in sentence or "wouldn't you" in sentence
                
                if is_open:
                    open_questions.append(sentence[:100])
                elif is_closed:
                    closed_questions.append(sentence[:100])
                
                if is_discovery:
                    discovery_questions.append(sentence[:100])
                
                if is_leading:
                    leading_questions.append(sentence[:100])
        
        total_questions = len(open_questions) + len(closed_questions)
        open_ratio = round((len(open_questions) / total_questions * 100) if total_questions else 0, 1)
        
        # Assessment
        question_quality = "good"
        if total_questions < 3:
            question_quality = "too_few"
        elif open_ratio < 30:
            question_quality = "too_many_closed"
        elif len(discovery_questions) < 2:
            question_quality = "needs_discovery"
        elif len(leading_questions) > total_questions * 0.3:
            question_quality = "too_many_leading"
        
        return {
            "total_questions": total_questions,
            "open_questions": len(open_questions),
            "closed_questions": len(closed_questions),
            "discovery_questions": len(discovery_questions),
            "leading_questions": len(leading_questions),
            "open_question_ratio": open_ratio,
            "quality_assessment": question_quality,
            "examples": {
                "open": open_questions[:3],
                "closed": closed_questions[:3],
                "discovery": discovery_questions[:3],
            }
        }

    def _detect_monologues(
        self,
        segments: List[Dict],
        speaker_analysis: Dict,
    ) -> Dict[str, Any]:
        """Detect long monologues (extended speaking without engagement)."""
        agent = speaker_analysis["agent"]
        monologues = []
        
        # Group consecutive segments by speaker
        current_speaker = None
        current_start = 0
        current_end = 0
        current_text = []
        
        for seg in segments:
            speaker = seg.get("speaker", "unknown")
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            text = seg.get("text", "")
            
            if speaker == current_speaker:
                current_end = end
                current_text.append(text)
            else:
                # Check if previous block was a monologue (> 60 seconds)
                if current_speaker == agent and (current_end - current_start) > 60:
                    monologues.append({
                        "start_sec": round(current_start, 1),
                        "end_sec": round(current_end, 1),
                        "duration_sec": round(current_end - current_start, 1),
                        "preview": " ".join(current_text)[:200],
                    })
                
                current_speaker = speaker
                current_start = start
                current_end = end
                current_text = [text]
        
        # Check final block
        if current_speaker == agent and (current_end - current_start) > 60:
            monologues.append({
                "start_sec": round(current_start, 1),
                "end_sec": round(current_end, 1),
                "duration_sec": round(current_end - current_start, 1),
                "preview": " ".join(current_text)[:200],
            })
        
        return {
            "count": len(monologues),
            "total_time_sec": sum(m["duration_sec"] for m in monologues),
            "instances": monologues[:5],  # Limit to 5
            "assessment": "excessive" if len(monologues) > 3 else "moderate" if monologues else "good",
        }

    def _detect_objections(
        self,
        segments: List[Dict],
        speaker_analysis: Dict,
    ) -> Dict[str, Any]:
        """Detect customer objections and how they were handled."""
        customer = speaker_analysis["customer"]
        agent = speaker_analysis["agent"]
        
        if not customer:
            return {"count": 0, "instances": [], "handling_assessment": "unknown"}
        
        objections = []
        
        for i, seg in enumerate(segments):
            if seg.get("speaker") != customer:
                continue
            
            text = seg.get("text", "").lower()
            
            for phrase in self.OBJECTION_PHRASES:
                if phrase in text:
                    # Look for agent response
                    response = ""
                    for j in range(i + 1, min(i + 4, len(segments))):
                        if segments[j].get("speaker") == agent:
                            response = segments[j].get("text", "")[:200]
                            break
                    
                    objections.append({
                        "timestamp_sec": round(seg.get("start", 0), 1),
                        "type": self._classify_objection(phrase),
                        "phrase": phrase,
                        "context": text[:150],
                        "agent_response": response,
                    })
                    break  # One objection per segment
        
        # Assess handling
        handling = "unknown"
        if objections:
            responded = sum(1 for o in objections if o["agent_response"])
            if responded == len(objections):
                handling = "addressed"
            elif responded > len(objections) / 2:
                handling = "partially_addressed"
            else:
                handling = "not_addressed"
        
        return {
            "count": len(objections),
            "instances": objections[:5],
            "handling_assessment": handling,
            "types": list(set(o["type"] for o in objections)),
        }

    def _classify_objection(self, phrase: str) -> str:
        """Classify objection type."""
        if any(w in phrase for w in ["expensive", "budget", "afford", "cost"]):
            return "price"
        elif any(w in phrase for w in ["think about", "more time", "not ready"]):
            return "timing"
        elif any(w in phrase for w in ["talk to", "check with", "approval"]):
            return "authority"
        elif any(w in phrase for w in ["already have", "using another", "happy with"]):
            return "competition"
        elif any(w in phrase for w in ["not interested", "not a priority"]):
            return "need"
        else:
            return "other"

    def _analyze_engagement(
        self,
        segments: List[Dict],
        speaker_analysis: Dict,
    ) -> Dict[str, Any]:
        """Analyze customer engagement patterns."""
        customer = speaker_analysis["customer"]
        
        if not customer:
            return {"level": "unknown", "score": 0, "indicators": []}
        
        customer_data = speaker_analysis["data"].get(customer, {})
        customer_texts = customer_data.get("texts", [])
        
        # Engagement indicators
        positive_count = 0
        negative_count = 0
        question_count = 0
        
        for text in customer_texts:
            text_lower = text.lower()
            
            # Count positive indicators
            positive_count += sum(1 for ind in self.POSITIVE_INDICATORS if ind in text_lower)
            
            # Count negative indicators
            negative_count += sum(1 for ind in self.NEGATIVE_INDICATORS if ind in text_lower)
            
            # Count customer questions (shows interest)
            question_count += text.count("?")
        
        # Calculate engagement score (0-100)
        total_segments = customer_data.get("segments", 1)
        avg_words = customer_data.get("total_words", 0) / total_segments if total_segments else 0
        
        score_components = [
            min(positive_count * 10, 30),  # Up to 30 points for positive signals
            min(question_count * 5, 20),   # Up to 20 points for questions
            min(avg_words / 2, 25),        # Up to 25 points for verbose responses
            25 - min(negative_count * 10, 25),  # Deduct for negative signals
        ]
        
        engagement_score = max(0, min(100, sum(score_components)))
        
        # Level assessment
        if engagement_score >= 70:
            level = "high"
        elif engagement_score >= 40:
            level = "medium"
        else:
            level = "low"
        
        return {
            "level": level,
            "score": round(engagement_score),
            "positive_signals": positive_count,
            "negative_signals": negative_count,
            "customer_questions": question_count,
            "avg_response_words": round(avg_words, 1),
        }

    def _analyze_sentiment_timeline(
        self,
        segments: List[Dict],
        speaker_analysis: Dict,
    ) -> Dict[str, Any]:
        """Analyze sentiment changes throughout the call."""
        customer = speaker_analysis["customer"]
        
        if not customer:
            return {"timeline": [], "trend": "unknown"}
        
        timeline = []
        window_size = 60  # 60 second windows
        current_window = 0
        window_positive = 0
        window_negative = 0
        
        for seg in segments:
            if seg.get("speaker") != customer:
                continue
            
            timestamp = seg.get("start", 0)
            text_lower = seg.get("text", "").lower()
            
            # Move to next window if needed
            while timestamp > (current_window + 1) * window_size:
                if window_positive > 0 or window_negative > 0:
                    net_sentiment = window_positive - window_negative
                    timeline.append({
                        "minute": current_window,
                        "sentiment": "positive" if net_sentiment > 0 else "negative" if net_sentiment < 0 else "neutral",
                        "score": net_sentiment,
                    })
                current_window += 1
                window_positive = 0
                window_negative = 0
            
            # Count sentiment in current segment
            for ind in self.POSITIVE_INDICATORS:
                if ind in text_lower:
                    window_positive += 1
            
            for ind in self.NEGATIVE_INDICATORS:
                if ind in text_lower:
                    window_negative += 1
        
        # Add final window
        if window_positive > 0 or window_negative > 0:
            net_sentiment = window_positive - window_negative
            timeline.append({
                "minute": current_window,
                "sentiment": "positive" if net_sentiment > 0 else "negative" if net_sentiment < 0 else "neutral",
                "score": net_sentiment,
            })
        
        # Determine overall trend
        if len(timeline) >= 2:
            first_half = sum(t["score"] for t in timeline[:len(timeline)//2])
            second_half = sum(t["score"] for t in timeline[len(timeline)//2:])
            
            if second_half > first_half + 1:
                trend = "improving"
            elif second_half < first_half - 1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
        
        return {
            "timeline": timeline,
            "trend": trend,
        }

    def _analyze_speaking_pace(
        self,
        segments: List[Dict],
        speaker_analysis: Dict,
    ) -> Dict[str, Any]:
        """Analyze speaking pace (words per minute)."""
        results = {}
        
        for speaker, data in speaker_analysis["data"].items():
            total_words = data["total_words"]
            total_time = data["total_time"]
            
            if total_time > 0:
                wpm = round((total_words / total_time) * 60)
            else:
                wpm = 0
            
            # Assess pace (ideal is 120-150 WPM)
            if wpm < 100:
                assessment = "slow"
            elif wpm < 120:
                assessment = "slightly_slow"
            elif wpm <= 150:
                assessment = "optimal"
            elif wpm <= 180:
                assessment = "slightly_fast"
            else:
                assessment = "fast"
            
            results[speaker] = {
                "wpm": wpm,
                "assessment": assessment,
                "total_words": total_words,
                "total_time_sec": round(total_time, 1),
            }
        
        return results

    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "speakers": {"agent": None, "customer": None, "data": {}, "total_speakers": 0},
            "talk_patterns": {
                "agent_talk_ratio": 0,
                "customer_talk_ratio": 0,
                "assessment": "unknown",
            },
            "questions": {"total_questions": 0, "quality_assessment": "unknown"},
            "monologues": {"count": 0, "instances": []},
            "objections": {"count": 0, "instances": []},
            "engagement": {"level": "unknown", "score": 0},
            "sentiment": {"timeline": [], "trend": "unknown"},
            "pace": {},
        }

