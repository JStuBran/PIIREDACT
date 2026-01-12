"""Export service for various formats."""

import csv
import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ExporterService:
    """Service for exporting call data in various formats."""

    def __init__(self):
        """Initialize the exporter service."""
        logger.info("ExporterService initialized")

    def export_csv(
        self,
        calls: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """
        Export calls to CSV.

        Args:
            calls: List of call records
            output_path: Path to save CSV

        Returns:
            Path to generated CSV
        """
        if not calls:
            raise ValueError("No calls to export")

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'ID', 'Agent Name', 'Agent ID', 'Created At', 'Status',
                'Duration (min)', 'Questions', 'Filler Words', 'Talk Ratio (%)',
            ])
            
            # Rows
            for call in calls:
                stats = call.get("stats_json", {}) or {}
                agent_label = stats.get("agent_label", "spk_0")
                
                writer.writerow([
                    call.get("id", ""),
                    call.get("agent_name", ""),
                    call.get("agent_id", ""),
                    call.get("created_at", "")[:19] if call.get("created_at") else "",
                    call.get("status", ""),
                    stats.get("duration_min", 0),
                    stats.get("questions", {}).get("agent_total", 0),
                    stats.get("filler", {}).get("agent_count", 0),
                    stats.get("talk_share_pct", {}).get(agent_label, 0),
                ])
        
        logger.info(f"Exported {len(calls)} calls to CSV: {output_path}")
        return output_path

    def export_json(
        self,
        calls: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """
        Export calls to JSON.

        Args:
            calls: List of call records
            output_path: Path to save JSON

        Returns:
            Path to generated JSON
        """
        # Prepare data for export (exclude file paths)
        export_data = []
        for call in calls:
            export_call = {
                "id": call.get("id"),
                "agent_name": call.get("agent_name"),
                "agent_id": call.get("agent_id"),
                "created_at": call.get("created_at"),
                "completed_at": call.get("completed_at"),
                "status": call.get("status"),
                "transcription": call.get("transcription_json"),
                "analysis": call.get("analysis_json"),
                "stats": call.get("stats_json"),
            }
            export_data.append(export_call)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Exported {len(calls)} calls to JSON: {output_path}")
        return output_path

    def export_srt(
        self,
        segments: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """
        Export transcript segments as SRT subtitle file.

        Args:
            segments: List of transcript segments with start, end, text
            output_path: Path to save SRT

        Returns:
            Path to generated SRT
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                start = segment.get("start", 0)
                end = segment.get("end", 0)
                text = segment.get("text", "").strip()
                
                if not text:
                    continue
                
                # Format timestamps as SRT format (HH:MM:SS,mmm)
                start_time = self._format_srt_timestamp(start)
                end_time = self._format_srt_timestamp(end)
                
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text}\n")
                f.write("\n")
        
        logger.info(f"Exported {len(segments)} segments to SRT: {output_path}")
        return output_path

    def _format_srt_timestamp(self, seconds: float) -> str:
        """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

