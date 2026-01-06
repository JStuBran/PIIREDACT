"""Annotations service for adding notes to calls."""

import logging
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AnnotationsService:
    """Service for managing call annotations."""

    def __init__(self, db_path: str = "sales_calls.db"):
        """
        Initialize the annotations service.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        logger.info(f"AnnotationsService initialized: {db_path}")

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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO annotations (call_id, timestamp_sec, note)
            VALUES (?, ?, ?)
        """, (call_id, timestamp_sec, note))

        annotation_id = cursor.lastrowid
        conn.commit()

        cursor.execute("SELECT * FROM annotations WHERE id = ?", (annotation_id,))
        row = cursor.fetchone()
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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM annotations
            WHERE call_id = ?
            ORDER BY timestamp_sec ASC, created_at ASC
        """, (call_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        updates = []
        values = []

        if note is not None:
            updates.append("note = ?")
            values.append(note)

        if timestamp_sec is not None:
            updates.append("timestamp_sec = ?")
            values.append(timestamp_sec)

        if not updates:
            conn.close()
            return None

        values.append(annotation_id)
        query = f"UPDATE annotations SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, values)

        conn.commit()

        cursor.execute("SELECT * FROM annotations WHERE id = ?", (annotation_id,))
        row = cursor.fetchone()
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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

