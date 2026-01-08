"""Database service for persistent call storage - supports both SQLite and PostgreSQL."""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Try to import PostgreSQL driver
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available. PostgreSQL support disabled.")


class DatabaseService:
    """Database service supporting both SQLite and PostgreSQL."""

    def __init__(self, db_path: Optional[str] = None, database_url: Optional[str] = None):
        """
        Initialize the database service.

        Args:
            db_path: Path to SQLite database file (for SQLite)
            database_url: PostgreSQL connection URL (for PostgreSQL)
                        If DATABASE_URL env var is set, it takes precedence
        """
        # Check for DATABASE_URL environment variable first (Railway provides this)
        database_url = database_url or os.environ.get("DATABASE_URL")
        
        if database_url:
            # Use PostgreSQL
            self.db_type = "postgresql"
            self.database_url = database_url
            # Parse connection string
            parsed = urlparse(database_url)
            self.db_config = {
                "host": parsed.hostname,
                "port": parsed.port or 5432,
                "database": parsed.path.lstrip("/"),
                "user": parsed.username,
                "password": parsed.password,
            }
            logger.info(f"DatabaseService initialized: PostgreSQL at {self.db_config['host']}")
        else:
            # Use SQLite
            self.db_type = "sqlite"
            if not db_path:
                db_path = os.environ.get("DATABASE_PATH", "sales_calls.db")
            
            # Ensure the directory exists for the database file
            db_dir = Path(db_path).parent
            if db_dir and not db_dir.exists():
                db_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created database directory: {db_dir}")
            
            self.db_path = db_path
            logger.info(f"DatabaseService initialized: SQLite at {db_path}")
        
        self._init_db()

    def _get_connection(self):
        """Get a database connection."""
        if self.db_type == "postgresql":
            if not PSYCOPG2_AVAILABLE:
                raise RuntimeError("PostgreSQL requires psycopg2. Install with: pip install psycopg2-binary")
            return psycopg2.connect(**self.db_config)
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # SQL differences between SQLite and PostgreSQL
        if self.db_type == "postgresql":
            # PostgreSQL uses SERIAL for auto-increment
            id_type = "SERIAL PRIMARY KEY"
            timestamp_default = "DEFAULT CURRENT_TIMESTAMP"
            text_type = "TEXT"
        else:
            # SQLite uses INTEGER PRIMARY KEY AUTOINCREMENT
            id_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
            timestamp_default = "DEFAULT CURRENT_TIMESTAMP"
            text_type = "TEXT"

        # Create calls table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS calls (
                id {text_type} PRIMARY KEY,
                filename {text_type} NOT NULL,
                user_email {text_type} NOT NULL,
                rep_name {text_type},
                file_path {text_type},
                call_type {text_type} DEFAULT 'real',
                created_at TIMESTAMP {timestamp_default},
                completed_at TIMESTAMP,
                status {text_type},
                error {text_type},
                transcription_json {text_type},
                analysis_json {text_type},
                stats_json {text_type},
                coaching_pdf_path {text_type},
                stats_pdf_path {text_type}
            )
        """)
        
        # Migration: Add call_type column if it doesn't exist (for existing databases)
        # Check if column exists first to avoid slow ALTER TABLE on large tables
        if self.db_type == "postgresql":
            # PostgreSQL: Check if column exists in information_schema
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='calls' AND column_name='call_type'
            """)
            column_exists = cursor.fetchone() is not None
            if not column_exists:
                # Column doesn't exist, add it
                # Use ALTER TABLE without DEFAULT to avoid updating all rows immediately
                # Then set default for new rows only
                cursor.execute(f"""
                    ALTER TABLE calls ADD COLUMN call_type {text_type}
                """)
                cursor.execute("""
                    ALTER TABLE calls ALTER COLUMN call_type SET DEFAULT 'real'
                """)
                # Update existing rows in batches (optional, can be done async)
                # For now, just set default for new rows
                logger.info("Added call_type column to calls table")
        else:
            # SQLite: Check if column exists by querying table info
            cursor.execute("PRAGMA table_info(calls)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'call_type' not in columns:
                cursor.execute(f"""
                    ALTER TABLE calls ADD COLUMN call_type {text_type} DEFAULT 'real'
                """)
                logger.info("Added call_type column to calls table")

        # Create annotations table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS annotations (
                id {id_type},
                call_id {text_type} NOT NULL,
                timestamp_sec REAL,
                note {text_type},
                created_at TIMESTAMP {timestamp_default},
                FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE CASCADE
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
        call_type: str = "real",
    ) -> Dict[str, Any]:
        """
        Create a new call record.

        Args:
            call_id: Unique call identifier
            filename: Original filename
            user_email: User who uploaded the call
            file_path: Path to audio file
            rep_name: Optional rep name
            call_type: Type of call - "real" (with PII redaction) or "ai_agent" (no redaction)

        Returns:
            Call record dict
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(f"""
            INSERT INTO calls (id, filename, user_email, rep_name, file_path, call_type, status)
            VALUES ({param_style}, {param_style}, {param_style}, {param_style}, {param_style}, {param_style}, {param_style})
        """, (call_id, filename, user_email, rep_name, file_path, call_type, "pending"))

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
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(f"SELECT * FROM calls WHERE id = {param_style}", (call_id,))
        
        if self.db_type == "postgresql":
            row = cursor.fetchone()
        else:
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

        conn = self._get_connection()
        cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"

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

            set_clauses.append(f"{key} = {param_style}")
            values.append(value)

        values.append(call_id)

        query = f"UPDATE calls SET {', '.join(set_clauses)} WHERE id = {param_style}"
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
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"

        where_clauses = ["status = 'complete'", "transcription_json IS NOT NULL"]
        params = []

        if user_email:
            where_clauses.append(f"user_email = {param_style}")
            params.append(user_email)

        where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get all matching calls and search in memory
        query_sql = f"SELECT * FROM calls {where_sql} ORDER BY created_at DESC LIMIT {param_style} OFFSET {param_style}"
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
        call_type: Optional[str] = None,
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
            call_type: Filter by call type ("real" or "ai_agent")
            limit: Maximum number of results
            offset: Offset for pagination
            order_by: Order by clause

        Returns:
            List of call records
        """
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"

        where_clauses = []
        params = []

        if user_email:
            where_clauses.append(f"user_email = {param_style}")
            params.append(user_email)

        if rep_name:
            where_clauses.append(f"rep_name = {param_style}")
            params.append(rep_name)

        if status:
            where_clauses.append(f"status = {param_style}")
            params.append(status)
        
        if call_type:
            where_clauses.append(f"call_type = {param_style}")
            params.append(call_type)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
            SELECT * FROM calls
            {where_sql}
            ORDER BY {order_by}
            LIMIT {param_style} OFFSET {param_style}
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
        call_type: Optional[str] = None,
    ) -> int:
        """
        Count calls matching filters.

        Args:
            user_email: Filter by user email
            rep_name: Filter by rep name
            status: Filter by status
            call_type: Filter by call type ("real" or "ai_agent")

        Returns:
            Count of matching calls
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"

        where_clauses = []
        params = []

        if user_email:
            where_clauses.append(f"user_email = {param_style}")
            params.append(user_email)

        if rep_name:
            where_clauses.append(f"rep_name = {param_style}")
            params.append(rep_name)

        if status:
            where_clauses.append(f"status = {param_style}")
            params.append(status)
        
        if call_type:
            where_clauses.append(f"call_type = {param_style}")
            params.append(call_type)

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
        conn = self._get_connection()
        cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"

        where_clauses = []
        params = []

        if user_email:
            where_clauses.append(f"user_email = {param_style}")
            params.append(user_email)

        if rep_name:
            where_clauses.append(f"rep_name = {param_style}")
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
        conn = self._get_connection()
        cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"

        if user_email:
            query = f"""
                SELECT DISTINCT rep_name
                FROM calls
                WHERE rep_name IS NOT NULL AND user_email = {param_style}
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

    def _row_to_dict(self, row: Union[sqlite3.Row, Dict]) -> Dict[str, Any]:
        """Convert database row to dict, parsing JSON fields."""
        if self.db_type == "postgresql":
            # psycopg2 RealDictCursor returns a dict-like object
            d = dict(row)
        else:
            # SQLite Row is already dict-like
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
        conn = self._get_connection()
        cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"

        # Delete annotations first (CASCADE should handle this, but being explicit)
        cursor.execute(f"DELETE FROM annotations WHERE call_id = {param_style}", (call_id,))

        # Delete call
        cursor.execute(f"DELETE FROM calls WHERE id = {param_style}", (call_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

    # Additional methods for compatibility with existing code
    def get_dashboard_stats(self, user_email: Optional[str] = None) -> Dict[str, Any]:
        """Alias for get_summary_stats for backward compatibility."""
        return self.get_summary_stats(user_email=user_email)

    def get_call_data_for_export(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get call data formatted for export."""
        return self.get_call(call_id)

    def get_calls_for_comparison(self, call_ids: List[str]) -> List[Dict[str, Any]]:
        """Get multiple calls for comparison."""
        calls = []
        for call_id in call_ids:
            call = self.get_call(call_id)
            if call:
                calls.append(call)
        return calls

    def get_all_call_stats(self, user_email: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get stats for all completed calls."""
        calls = self.list_calls(user_email=user_email, status="complete", limit=1000)
        return [call.get("stats_json", {}) for call in calls if call.get("stats_json")]

    def get_call_transcription_for_export(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get transcription data for export."""
        call = self.get_call(call_id)
        if call:
            return call.get("transcription_json")
        return None
