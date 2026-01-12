"""Comparison service for comparing multiple calls."""

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ComparisonService:
    """Compare multiple sales calls side-by-side."""

    def __init__(self):
        """Initialize the comparison service."""
        logger.info("ComparisonService initialized")

    def compare_calls(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare multiple calls and generate comparison data.

        Args:
            calls: List of call records with analysis_json and stats_json

        Returns:
            Dict with comparison data
        """
        if len(calls) < 2:
            return {"error": "Need at least 2 calls to compare"}

        # Extract stats and analysis for each call
        call_data = []
        for call in calls:
            stats = call.get("stats_json") or {}
            analysis = call.get("analysis_json") or {}
            
            call_data.append({
                "id": call["id"],
                "filename": call.get("agent_name") or call["id"],  # Use agent_name as identifier
                "agent_name": call.get("agent_name"),
                "created_at": call.get("created_at"),
                "stats": stats,
                "analysis": analysis,
            })

        # Compare stats
        stats_comparison = self._compare_stats(call_data)
        
        # Compare analysis highlights
        analysis_comparison = self._compare_analysis(call_data)
        
        # Calculate trends (if 3+ calls, ordered by date)
        trends = None
        if len(call_data) >= 3:
            trends = self._calculate_trends(call_data)

        return {
            "calls": call_data,
            "stats_comparison": stats_comparison,
            "analysis_comparison": analysis_comparison,
            "trends": trends,
        }

    def _compare_stats(self, call_data: List[Dict]) -> Dict[str, Any]:
        """Compare statistics across calls."""
        if not call_data:
            return {}

        # Aggregate stats
        durations = []
        talk_ratios = []
        questions = []
        filler_words = []
        
        for call in call_data:
            stats = call.get("stats", {})
            
            # Duration
            duration = stats.get("duration_min", 0)
            durations.append(duration)
            
            # Talk ratio (agent share)
            agent_label = stats.get("agent_label", "spk_0")
            talk_share = stats.get("talk_share_pct", {}).get(agent_label, 0)
            talk_ratios.append(talk_share)
            
            # Questions
            q_total = stats.get("questions", {}).get("agent_total", 0)
            questions.append(q_total)
            
            # Filler words
            filler_count = stats.get("filler", {}).get("agent_count", 0)
            filler_words.append(filler_count)

        # Calculate averages
        avg_duration = sum(durations) / len(durations) if durations else 0
        avg_talk_ratio = sum(talk_ratios) / len(talk_ratios) if talk_ratios else 0
        avg_questions = sum(questions) / len(questions) if questions else 0
        avg_filler = sum(filler_words) / len(filler_words) if filler_words else 0

        # Find min/max
        max_duration_idx = durations.index(max(durations)) if durations else None
        min_duration_idx = durations.index(min(durations)) if durations else None
        max_talk_idx = talk_ratios.index(max(talk_ratios)) if talk_ratios else None
        min_talk_idx = talk_ratios.index(min(talk_ratios)) if talk_ratios else None

        return {
            "avg_duration_min": round(avg_duration, 1),
            "avg_talk_ratio_pct": round(avg_talk_ratio, 1),
            "avg_questions": round(avg_questions, 1),
            "avg_filler_words": round(avg_filler, 1),
            "durations": [round(d, 1) for d in durations],
            "talk_ratios": [round(t, 1) for t in talk_ratios],
            "questions": questions,
            "filler_words": filler_words,
            "max_duration_call": call_data[max_duration_idx]["filename"] if max_duration_idx is not None else None,
            "min_duration_call": call_data[min_duration_idx]["filename"] if min_duration_idx is not None else None,
            "max_talk_call": call_data[max_talk_idx]["filename"] if max_talk_idx is not None else None,
            "min_talk_call": call_data[min_talk_idx]["filename"] if min_talk_idx is not None else None,
        }

    def _compare_analysis(self, call_data: List[Dict]) -> Dict[str, Any]:
        """Compare analysis highlights across calls."""
        if not call_data:
            return {}

        # Collect common themes
        all_highlights = []
        all_improvements = []
        all_focus_areas = []
        objection_counts = {}

        for call in call_data:
            analysis = call.get("analysis", {})
            
            # Highlights
            highlights = analysis.get("highlights", [])
            all_highlights.extend(highlights)
            
            # Improvements
            coaching = analysis.get("coaching", {})
            improvements = coaching.get("improve", [])
            all_improvements.extend(improvements)
            
            # Focus areas
            focus = coaching.get("focus_next", "")
            if focus:
                all_focus_areas.append(focus)
            
            # Objections
            objection = analysis.get("objection_handling", {}).get("objection", "None")
            if objection and objection != "None":
                objection_counts[objection] = objection_counts.get(objection, 0) + 1

        # Find most common focus area
        focus_counter = Counter(all_focus_areas)
        most_common_focus = focus_counter.most_common(1)[0][0] if focus_counter else None

        return {
            "total_highlights": len(all_highlights),
            "total_improvements": len(all_improvements),
            "common_focus": most_common_focus,
            "objection_summary": dict(objection_counts),
            "unique_highlights": list(set(all_highlights))[:5],  # Top 5 unique
            "unique_improvements": list(set(all_improvements))[:5],  # Top 5 unique
        }

    def _calculate_trends(self, call_data: List[Dict]) -> Optional[Dict[str, Any]]:
        """
        Calculate trends over time (requires calls ordered by date).

        Args:
            call_data: List of calls, should be sorted by created_at

        Returns:
            Trends dict or None
        """
        if len(call_data) < 3:
            return None

        # Sort by date if not already sorted
        sorted_calls = sorted(
            call_data,
            key=lambda x: x.get("created_at", ""),
        )

        # Extract time series data
        durations = []
        talk_ratios = []
        questions = []
        filler_words = []
        dates = []

        for call in sorted_calls:
            stats = call.get("stats", {})
            dates.append(call.get("created_at", "")[:10])  # Just the date part
            
            durations.append(stats.get("duration_min", 0))
            
            agent_label = stats.get("agent_label", "spk_0")
            talk_share = stats.get("talk_share_pct", {}).get(agent_label, 0)
            talk_ratios.append(talk_share)
            
            questions.append(stats.get("questions", {}).get("agent_total", 0))
            filler_words.append(stats.get("filler", {}).get("agent_count", 0))

        # Calculate trend direction (improving, declining, stable)
        def trend_direction(values):
            if len(values) < 2:
                return "stable"
            
            # Simple linear trend
            first_half = sum(values[:len(values)//2]) / (len(values)//2)
            second_half = sum(values[len(values)//2:]) / (len(values) - len(values)//2)
            
            diff = second_half - first_half
            if abs(diff) < 0.1:  # Less than 10% change
                return "stable"
            elif diff > 0:
                return "improving"
            else:
                return "declining"

        return {
            "dates": dates,
            "durations": [round(d, 1) for d in durations],
            "talk_ratios": [round(t, 1) for t in talk_ratios],
            "questions": questions,
            "filler_words": filler_words,
            "duration_trend": trend_direction(durations),
            "talk_ratio_trend": trend_direction(talk_ratios),
            "questions_trend": trend_direction(questions),
            "filler_trend": trend_direction(filler_words),
        }

