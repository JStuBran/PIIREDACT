"""Annotations service for adding notes to calls - supports both SQLite and PostgreSQL."""

import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Try to import PostgreSQL driver
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class AnnotationsService:
    """Service for managing call annotations - supports both SQLite and PostgreSQL."""

    def __init__(self, db_path: Optional[str] = None, database_url: Optional[str] = None):
        """
        Initialize the annotations service.

        Args:
            db_path: Path to SQLite database (for SQLite)
            database_url: PostgreSQL connection URL (for PostgreSQL)
                        If DATABASE_URL env var is set, it takes precedence
        """
        # Check for DATABASE_URL environment variable first (Railway provides this)
        database_url = database_url or os.environ.get("DATABASE_URL")
        
        if database_url:
            # Use PostgreSQL
            self.db_type = "postgresql"
            parsed = urlparse(database_url)
            self.db_config = {
                "host": parsed.hostname,
                "port": parsed.port or 5432,
                "database": parsed.path.lstrip("/"),
                "user": parsed.username,
                "password": parsed.password,
            }
            logger.info(f"AnnotationsService initialized: PostgreSQL")
        else:
            # Use SQLite
            self.db_type = "sqlite"
            if not db_path:
                db_path = os.environ.get("DATABASE_PATH", "sales_calls.db")
            self.db_path = db_path
            logger.info(f"AnnotationsService initialized: SQLite at {db_path}")

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

    def create_annotation(
        self,
        call_id: str,
        note: str,
        timestamp_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Create a new annotation.

        Args:
            call_id: Call identifier
            note: Annotation text
            timestamp_sec: Optional timestamp in seconds

        Returns:
            Annotation record
        """
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"
        
        if self.db_type == "postgresql":
            cursor.execute(f"""
                INSERT INTO annotations (call_id, timestamp_sec, note)
                VALUES ({param_style}, {param_style}, {param_style})
                RETURNING *
            """, (call_id, timestamp_sec, note))
            row = cursor.fetchone()
        else:
            cursor.execute(f"""
                INSERT INTO annotations (call_id, timestamp_sec, note)
                VALUES ({param_style}, {param_style}, {param_style})
            """, (call_id, timestamp_sec, note))
            annotation_id = cursor.lastrowid
            cursor.execute(f"SELECT * FROM annotations WHERE id = {param_style}", (annotation_id,))
            row = cursor.fetchone()

        conn.commit()
        conn.close()

        return dict(row) if row else {}

    def get_annotations(self, call_id: str) -> List[Dict[str, Any]]:
        """
        Get all annotations for a call.

        Args:
            call_id: Call identifier

        Returns:
            List of annotation records
        """
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"
        
        cursor.execute(f"""
            SELECT * FROM annotations
            WHERE call_id = {param_style}
            ORDER BY timestamp_sec ASC, created_at ASC
        """, (call_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_annotation(self, annotation_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a single annotation by ID.

        Args:
            annotation_id: Annotation ID

        Returns:
            Annotation record or None
        """
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"
        
        cursor.execute(f"SELECT * FROM annotations WHERE id = {param_style}", (annotation_id,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def update_annotation(
        self,
        annotation_id: int,
        note: Optional[str] = None,
        timestamp_sec: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Update an annotation.

        Args:
            annotation_id: Annotation ID
            note: New note text (optional)
            timestamp_sec: New timestamp (optional)

        Returns:
            Updated annotation or None
        """
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"

        updates = []
        values = []

        if note is not None:
            updates.append(f"note = {param_style}")
            values.append(note)

        if timestamp_sec is not None:
            updates.append(f"timestamp_sec = {param_style}")
            values.append(timestamp_sec)

        if not updates:
            conn.close()
            return None

        values.append(annotation_id)
        
        if self.db_type == "postgresql":
            query = f"UPDATE annotations SET {', '.join(updates)} WHERE id = {param_style} RETURNING *"
            cursor.execute(query, values)
            row = cursor.fetchone()
        else:
            query = f"UPDATE annotations SET {', '.join(updates)} WHERE id = {param_style}"
            cursor.execute(query, values)
            cursor.execute(f"SELECT * FROM annotations WHERE id = {param_style}", (annotation_id,))
            row = cursor.fetchone()

        conn.commit()
        conn.close()

        return dict(row) if row else None

    def delete_annotation(self, annotation_id: int) -> bool:
        """
        Delete an annotation.

        Args:
            annotation_id: Annotation ID

        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        param_style = "%s" if self.db_type == "postgresql" else "?"

        cursor.execute(f"DELETE FROM annotations WHERE id = {param_style}", (annotation_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted
