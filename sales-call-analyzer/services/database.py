"""Database service for persistent call storage."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DatabaseService:
    """SQLite database service for storing call data."""

    def __init__(self, db_path: str = "sales_calls.db"):
        """
        Initialize the database service.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()
        logger.info(f"DatabaseService initialized: {db_path}")

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create calls table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calls (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                user_email TEXT NOT NULL,
                rep_name TEXT,
                file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT,
                error TEXT,
                transcription_json TEXT,
                analysis_json TEXT,
                stats_json TEXT,
                coaching_pdf_path TEXT,
                stats_pdf_path TEXT
            )
        """)

        # Create annotations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT NOT NULL,
                timestamp_sec REAL,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (call_id) REFERENCES calls(id)
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_calls_user ON calls(user_email)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_calls_rep ON calls(rep_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_calls_created ON calls(created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status)
        """)

        conn.commit()
        conn.close()

    def create_call(
        self,
        call_id: str,
        filename: str,
        user_email: str,
        file_path: str,
        rep_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new call record.

        Args:
            call_id: Unique call identifier
            filename: Original filename
            user_email: User who uploaded the call
            file_path: Path to audio file
            rep_name: Optional rep name

        Returns:
            Call record dict
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO calls (id, filename, user_email, rep_name, file_path, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (call_id, filename, user_email, rep_name, file_path, "pending"))

        conn.commit()
        conn.close()

        return self.get_call(call_id)

    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a call by ID.

        Args:
            call_id: Call identifier

        Returns:
            Call record dict or None
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM calls WHERE id = ?", (call_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_dict(row)

    def update_call(
        self,
        call_id: str,
        **updates: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Update a call record.

        Args:
            call_id: Call identifier
            **updates: Fields to update (status, transcription_json, analysis_json, etc.)

        Returns:
            Updated call record dict or None
        """
        if not updates:
            return self.get_call(call_id)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Build update query
        set_clauses = []
        values = []

        for key, value in updates.items():
            if key in ["transcription_json", "analysis_json", "stats_json"]:
                # Serialize JSON fields
                value = json.dumps(value) if value else None
            elif key == "completed_at" and value:
                # Ensure datetime format
                if isinstance(value, str):
                    value = value
                else:
                    value = value.isoformat() if hasattr(value, "isoformat") else str(value)

            set_clauses.append(f"{key} = ?")
            values.append(value)

        values.append(call_id)

        query = f"UPDATE calls SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(query, values)

        conn.commit()
        conn.close()

        return self.get_call(call_id)

    def search_transcripts(
        self,
        query: str,
        user_email: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Full-text search across transcripts.

        Args:
            query: Search query
            user_email: Filter by user email
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of call records matching the search
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        where_clauses = ["status = 'complete'", "transcription_json IS NOT NULL"]
        params = []

        if user_email:
            where_clauses.append("user_email = ?")
            params.append(user_email)

        where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get all matching calls and search in memory (SQLite FTS would require schema changes)
        query_sql = f"SELECT * FROM calls {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit * 3, offset])  # Get more to filter

        cursor.execute(query_sql, params)
        rows = cursor.fetchall()
        conn.close()

        # Filter by search query in transcription text
        query_lower = query.lower()
        matching_calls = []

        for row in rows:
            call = self._row_to_dict(row)
            transcription = call.get("transcription_json")
            
            if transcription:
                redacted_text = transcription.get("redacted_text", "").lower()
                if query_lower in redacted_text:
                    matching_calls.append(call)
                    if len(matching_calls) >= limit:
                        break

        return matching_calls

    def list_calls(
        self,
        user_email: Optional[str] = None,
        rep_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "created_at DESC",
    ) -> List[Dict[str, Any]]:
        """
        List calls with optional filters.

        Args:
            user_email: Filter by user email
            rep_name: Filter by rep name
            status: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination
            order_by: Order by clause

        Returns:
            List of call records
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        where_clauses = []
        params = []

        if user_email:
            where_clauses.append("user_email = ?")
            params.append(user_email)

        if rep_name:
            where_clauses.append("rep_name = ?")
            params.append(rep_name)

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
            SELECT * FROM calls
            {where_sql}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def count_calls(
        self,
        user_email: Optional[str] = None,
        rep_name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """
        Count calls matching filters.

        Args:
            user_email: Filter by user email
            rep_name: Filter by rep name
            status: Filter by status

        Returns:
            Count of matching calls
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        where_clauses = []
        params = []

        if user_email:
            where_clauses.append("user_email = ?")
            params.append(user_email)

        if rep_name:
            where_clauses.append("rep_name = ?")
            params.append(rep_name)

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"SELECT COUNT(*) FROM calls {where_sql}"
        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()

        return count

    def get_summary_stats(
        self,
        user_email: Optional[str] = None,
        rep_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get summary statistics for calls.

        Args:
            user_email: Filter by user email
            rep_name: Filter by rep name

        Returns:
            Dict with summary stats
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        where_clauses = []
        params = []

        if user_email:
            where_clauses.append("user_email = ?")
            params.append(user_email)

        if rep_name:
            where_clauses.append("rep_name = ?")
            params.append(rep_name)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Get counts by status
        query = f"""
            SELECT status, COUNT(*) as count
            FROM calls
            {where_sql}
            GROUP BY status
        """
        cursor.execute(query, params)
        status_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Get total calls
        query = f"SELECT COUNT(*) FROM calls {where_sql}"
        cursor.execute(query, params)
        total_calls = cursor.fetchone()[0]

        # Get completed calls with stats
        query = f"""
            SELECT stats_json
            FROM calls
            {where_sql} AND status = 'complete' AND stats_json IS NOT NULL
        """
        cursor.execute(query, params)
        stats_rows = cursor.fetchall()

        # Calculate averages from stats
        total_duration = 0
        total_questions = 0
        total_filler = 0
        calls_with_stats = 0

        for (stats_json,) in stats_rows:
            try:
                stats = json.loads(stats_json) if isinstance(stats_json, str) else stats_json
                total_duration += stats.get("duration_min", 0)
                total_questions += stats.get("questions", {}).get("agent_total", 0)
                total_filler += stats.get("filler", {}).get("agent_count", 0)
                calls_with_stats += 1
            except (json.JSONDecodeError, TypeError):
                continue

        conn.close()

        return {
            "total_calls": total_calls,
            "status_counts": status_counts,
            "completed_calls": status_counts.get("complete", 0),
            "avg_duration_min": round(total_duration / calls_with_stats, 1) if calls_with_stats else 0,
            "avg_questions": round(total_questions / calls_with_stats, 1) if calls_with_stats else 0,
            "avg_filler_words": round(total_filler / calls_with_stats, 1) if calls_with_stats else 0,
        }

    def get_reps(self, user_email: Optional[str] = None) -> List[str]:
        """
        Get list of unique rep names.

        Args:
            user_email: Filter by user email

        Returns:
            List of rep names
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if user_email:
            query = """
                SELECT DISTINCT rep_name
                FROM calls
                WHERE rep_name IS NOT NULL AND user_email = ?
                ORDER BY rep_name
            """
            cursor.execute(query, (user_email,))
        else:
            query = """
                SELECT DISTINCT rep_name
                FROM calls
                WHERE rep_name IS NOT NULL
                ORDER BY rep_name
            """
            cursor.execute(query)

        reps = [row[0] for row in cursor.fetchall()]
        conn.close()

        return reps

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert SQLite row to dict, parsing JSON fields."""
        d = dict(row)

        # Parse JSON fields
        for json_field in ["transcription_json", "analysis_json", "stats_json"]:
            if d.get(json_field):
                try:
                    d[json_field] = json.loads(d[json_field])
                except (json.JSONDecodeError, TypeError):
                    d[json_field] = None
            else:
                d[json_field] = None

        return d

    def delete_call(self, call_id: str) -> bool:
        """
        Delete a call and its annotations.

        Args:
            call_id: Call identifier

        Returns:
            True if deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Delete annotations first
        cursor.execute("DELETE FROM annotations WHERE call_id = ?", (call_id,))

        # Delete call
        cursor.execute("DELETE FROM calls WHERE id = ?", (call_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

