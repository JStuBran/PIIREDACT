"""Analyzer service - GPT-4o coaching analysis."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

# Coaching prompt from n8n workflow
COACHING_PROMPT = """You are a supportive but constructive sales coach for junior sales reps.
Keep feedback concise and practical. Assume the rep is new—focus on fundamentals they can apply immediately. Give direct advice when helpful. Use plain language.

Transcript (timestamped, speaker-labeled):
"{transcript}"

Metadata:
- DurationMin: {duration_min}

INSTRUCTIONS (follow strictly):
- Use SPIN Selling and basic Sales Training Best Practices as a loose guide.
- Keep each bullet under 20 words.
- Be encouraging—highlight what worked before suggesting improvements.
- Provide example phrasing where helpful.
- If no timestamps are present in the transcript, return "No timestamps available." for the timestamp section.
- OUTPUT FORMAT: Return ONE JSON object ONLY (no markdown, no code fences, no explanations). Use EXACTLY these keys and structure:

{{
  "overall_summary": "<3–4 sentences on overall performance>",
  "highlights": [
    "What the rep did well #1",
    "What the rep did well #2",
    "What the rep did well #3",
    "Optional #4"
  ],
  "objection_handling": {{
    "objection": "<what objection(s) surfaced, or 'None'>",
    "improvement": "One clear improvement with example language"
  }},
  "coaching": {{
    "done_well": [
      "Encouraging, simple statement #1",
      "Encouraging, simple statement #2"
    ],
    "improve": [
      "Specific improvement with example phrasing #1",
      "Specific improvement with example phrasing #2"
    ],
    "focus_next": "One simple skill to practice"
  }},
  "timestamp_highlights": [
    "[mm:ss] — brief moment and why it matters",
    "[mm:ss] — brief moment and why it matters",
    "[mm:ss] — brief moment and why it matters"
  ]
}}

CONSTRAINTS:
- Do not add any keys beyond those above.
- Do not include emojis in values.
- Do not include any text outside the JSON object.
- If no timestamps are in the transcript, set "timestamp_highlights" to ["No timestamps available."].
- Keep all bullets ≤ 20 words and concrete.
"""


class AnalyzerService:
    """Analyze sales calls using GPT-4o."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Initialize the analyzer.

        Args:
            api_key: OpenAI API key
            model: OpenAI model to use
        """
        if not api_key:
            raise ValueError("OpenAI API key is required")
        
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info(f"AnalyzerService initialized with model: {model}")

    def analyze(
        self,
        transcript: str,
        duration_min: float = 0,
    ) -> Dict[str, Any]:
        """
        Analyze a sales call transcript.

        Args:
            transcript: The (redacted) transcript text
            duration_min: Call duration in minutes

        Returns:
            Dict with coaching analysis
        """
        logger.info(f"Analyzing transcript ({len(transcript)} chars, {duration_min} min)")

        prompt = COACHING_PROMPT.format(
            transcript=transcript,
            duration_min=duration_min,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            
            # Parse JSON response
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                result = self._extract_json(content)

            # Normalize keys to match expected format
            return self._normalize_response(result)

        except Exception as e:
            logger.exception(f"Analysis failed: {e}")
            return self._empty_analysis(str(e))

    def _extract_json(self, content: str) -> Dict:
        """Extract JSON from response that might have extra text."""
        # Try to find JSON object in response
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}

    def _normalize_response(self, result: Dict) -> Dict[str, Any]:
        """Normalize GPT response to consistent format."""
        return {
            "overall_summary": result.get("overall_summary", ""),
            "highlights": result.get("highlights", []),
            "objection_handling": {
                "objection": result.get("objection_handling", {}).get("objection", "None"),
                "improvement": result.get("objection_handling", {}).get("improvement", ""),
            },
            "coaching": {
                "done_well": result.get("coaching", {}).get("done_well", []),
                "improve": result.get("coaching", {}).get("improve", []),
                "focus_next": result.get("coaching", {}).get("focus_next", ""),
            },
            "timestamp_highlights": result.get("timestamp_highlights", []),
        }

    def _empty_analysis(self, error: str = "") -> Dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "overall_summary": f"Analysis could not be completed. {error}" if error else "",
            "highlights": [],
            "objection_handling": {"objection": "None", "improvement": ""},
            "coaching": {"done_well": [], "improve": [], "focus_next": ""},
            "timestamp_highlights": [],
        }

    def compute_stats(self, segments: List[Dict]) -> Dict[str, Any]:
        """
        Compute call statistics from segments.

        Args:
            segments: List of transcript segments with speaker labels

        Returns:
            Dict with call statistics
        """
        if not segments:
            return self._empty_stats()

        # Aggregate by speaker
        speaker_stats = {}
        for seg in segments:
            speaker = seg.get("speaker", "unknown")
            duration = seg.get("end", 0) - seg.get("start", 0)
            text = seg.get("text", "")
            words = len(text.split())

            if speaker not in speaker_stats:
                speaker_stats[speaker] = {
                    "talk_sec": 0,
                    "words": 0,
                    "utterances": 0,
                    "texts": [],
                }

            speaker_stats[speaker]["talk_sec"] += duration
            speaker_stats[speaker]["words"] += words
            speaker_stats[speaker]["utterances"] += 1
            speaker_stats[speaker]["texts"].append(text)

        # Calculate derived metrics
        total_duration = max(seg.get("end", 0) for seg in segments) if segments else 0
        speakers = list(speaker_stats.keys())
        
        # Assume first speaker is agent, second is customer
        agent = speakers[0] if speakers else "spk_0"
        customer = speakers[1] if len(speakers) > 1 else speakers[0] if speakers else "spk_1"

        agent_stats = speaker_stats.get(agent, {"talk_sec": 0, "words": 0, "utterances": 0})
        customer_stats = speaker_stats.get(customer, {"talk_sec": 0, "words": 0, "utterances": 0})

        total_talk = agent_stats["talk_sec"] + customer_stats["talk_sec"]

        # Count questions from agent
        agent_text = " ".join(speaker_stats.get(agent, {}).get("texts", []))
        questions = agent_text.count("?")
        
        # Count filler words
        filler_words = ["um", "uh", "like", "you know", "kind of", "sort of", "basically", "actually"]
        filler_count = sum(
            agent_text.lower().count(f" {fw} ") + agent_text.lower().count(f" {fw},")
            for fw in filler_words
        )

        return {
            "duration_min": round(total_duration / 60, 1),
            "total_duration_sec": round(total_duration),
            "agent_label": agent,
            "customer_label": customer,
            "talk_time_sec": {
                agent: round(agent_stats["talk_sec"]),
                customer: round(customer_stats["talk_sec"]),
            },
            "talk_share_pct": {
                agent: round((agent_stats["talk_sec"] / total_talk * 100)) if total_talk else 0,
                customer: round((customer_stats["talk_sec"] / total_talk * 100)) if total_talk else 0,
            },
            "wpm": {
                agent: round(agent_stats["words"] / (agent_stats["talk_sec"] / 60)) if agent_stats["talk_sec"] else 0,
                customer: round(customer_stats["words"] / (customer_stats["talk_sec"] / 60)) if customer_stats["talk_sec"] else 0,
            },
            "utterances": {
                agent: agent_stats["utterances"],
                customer: customer_stats["utterances"],
            },
            "questions": {
                "agent_total": questions,
                "rate_per_min": round(questions / (total_duration / 60), 1) if total_duration else 0,
            },
            "filler": {
                "agent_count": filler_count,
                "agent_per_100_words": round(filler_count / agent_stats["words"] * 100, 1) if agent_stats["words"] else 0,
            },
            "turns": len(segments),
        }

    def _empty_stats(self) -> Dict[str, Any]:
        """Return empty stats structure."""
        return {
            "duration_min": 0,
            "total_duration_sec": 0,
            "agent_label": "spk_0",
            "customer_label": "spk_1",
            "talk_time_sec": {},
            "talk_share_pct": {},
            "wpm": {},
            "utterances": {},
            "questions": {"agent_total": 0, "rate_per_min": 0},
            "filler": {"agent_count": 0, "agent_per_100_words": 0},
            "turns": 0,
        }

