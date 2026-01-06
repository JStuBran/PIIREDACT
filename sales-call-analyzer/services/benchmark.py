"""Benchmarking service for team performance comparison."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BenchmarkService:
    """Service for calculating benchmarks and percentile rankings."""

    def __init__(self):
        """Initialize the benchmark service."""
        logger.info("BenchmarkService initialized")

    def calculate_benchmarks(
        self,
        calls: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate team benchmarks from a list of calls.

        Args:
            calls: List of completed call records with stats_json

        Returns:
            Dict with benchmark metrics
        """
        if not calls:
            return self._empty_benchmarks()

        # Extract metrics
        durations = []
        talk_ratios = []
        questions = []
        filler_words = []
        questions_per_min = []

        for call in calls:
            stats = call.get("stats_json", {})
            if not stats:
                continue

            duration = stats.get("duration_min", 0)
            if duration > 0:
                durations.append(duration)

            agent_label = stats.get("agent_label", "spk_0")
            talk_share = stats.get("talk_share_pct", {}).get(agent_label, 0)
            if talk_share > 0:
                talk_ratios.append(talk_share)

            q_total = stats.get("questions", {}).get("agent_total", 0)
            if q_total > 0:
                questions.append(q_total)
                if duration > 0:
                    questions_per_min.append(q_total / duration)

            filler = stats.get("filler", {}).get("agent_count", 0)
            if filler > 0:
                filler_words.append(filler)

        # Calculate averages
        benchmarks = {
            "avg_duration": self._average(durations),
            "avg_talk_ratio": self._average(talk_ratios),
            "avg_questions": self._average(questions),
            "avg_questions_per_min": self._average(questions_per_min),
            "avg_filler_words": self._average(filler_words),
            "median_duration": self._median(durations),
            "median_talk_ratio": self._median(talk_ratios),
            "median_questions": self._median(questions),
            "total_calls": len(calls),
        }

        return benchmarks

    def calculate_percentile(
        self,
        value: float,
        all_values: List[float],
    ) -> float:
        """
        Calculate percentile rank of a value.

        Args:
            value: The value to rank
            all_values: List of all values to compare against

        Returns:
            Percentile (0-100)
        """
        if not all_values:
            return 50.0  # Default to median if no data

        sorted_values = sorted(all_values)
        count_below = sum(1 for v in sorted_values if v < value)
        count_equal = sum(1 for v in sorted_values if v == value)

        # Percentile formula: (count_below + 0.5 * count_equal) / total * 100
        percentile = (count_below + 0.5 * count_equal) / len(sorted_values) * 100
        return round(percentile, 1)

    def rank_call(
        self,
        call: Dict[str, Any],
        benchmarks: Dict[str, Any],
        all_calls: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate percentile rankings for a specific call.

        Args:
            call: Call record to rank
            benchmarks: Team benchmarks
            all_calls: All calls for comparison

        Returns:
            Dict with percentile rankings
        """
        stats = call.get("stats_json", {}) or {}
        
        # Extract values for this call
        duration = stats.get("duration_min", 0)
        agent_label = stats.get("agent_label", "spk_0")
        talk_ratio = stats.get("talk_share_pct", {}).get(agent_label, 0)
        questions = stats.get("questions", {}).get("agent_total", 0)
        filler = stats.get("filler", {}).get("agent_count", 0)

        # Collect all values for percentile calculation
        all_durations = []
        all_talk_ratios = []
        all_questions = []
        all_filler = []

        for c in all_calls:
            s = c.get("stats_json", {})
            if s:
                d = s.get("duration_min", 0)
                if d > 0:
                    all_durations.append(d)

                al = s.get("agent_label", "spk_0")
                tr = s.get("talk_share_pct", {}).get(al, 0)
                if tr > 0:
                    all_talk_ratios.append(tr)

                q = s.get("questions", {}).get("agent_total", 0)
                if q > 0:
                    all_questions.append(q)

                f = s.get("filler", {}).get("agent_count", 0)
                if f > 0:
                    all_filler.append(f)

        return {
            "duration_percentile": self.calculate_percentile(duration, all_durations) if duration > 0 else None,
            "talk_ratio_percentile": self.calculate_percentile(talk_ratio, all_talk_ratios) if talk_ratio > 0 else None,
            "questions_percentile": self.calculate_percentile(questions, all_questions) if questions > 0 else None,
            "filler_percentile": self.calculate_percentile(filler, all_filler) if filler > 0 else None,
        }

    def _average(self, values: List[float]) -> float:
        """Calculate average."""
        if not values:
            return 0.0
        return round(sum(values) / len(values), 1)

    def _median(self, values: List[float]) -> float:
        """Calculate median."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        n = len(sorted_values)
        if n % 2 == 0:
            return round((sorted_values[n//2 - 1] + sorted_values[n//2]) / 2, 1)
        else:
            return round(sorted_values[n//2], 1)

    def _empty_benchmarks(self) -> Dict[str, Any]:
        """Return empty benchmarks structure."""
        return {
            "avg_duration": 0,
            "avg_talk_ratio": 0,
            "avg_questions": 0,
            "avg_questions_per_min": 0,
            "avg_filler_words": 0,
            "median_duration": 0,
            "median_talk_ratio": 0,
            "median_questions": 0,
            "total_calls": 0,
        }

