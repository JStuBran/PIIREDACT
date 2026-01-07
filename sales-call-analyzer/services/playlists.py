"""Coaching Playlists service - curated collections of calls for training."""

import json
import logging
import os
import sqlite3
from datetime import datetime
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


class PlaylistService:
    """Service for managing coaching playlists."""

    def __init__(self, db_path: Optional[str] = None, database_url: Optional[str] = None):
        """Initialize the playlist service."""
        database_url = database_url or os.environ.get("DATABASE_URL")

        if database_url:
            self.db_type = "postgresql"
            parsed = urlparse(database_url)
            self.db_config = {
                "host": parsed.hostname,
                "port": parsed.port or 5432,
                "database": parsed.path.lstrip("/"),
                "user": parsed.username,
                "password": parsed.password,
            }
            logger.info("PlaylistService initialized: PostgreSQL")
        else:
            self.db_type = "sqlite"
            if not db_path:
                db_path = os.environ.get("DATABASE_PATH", "sales_calls.db")
            self.db_path = db_path
            logger.info(f"PlaylistService initialized: SQLite at {db_path}")

        self._init_db()

    def _get_connection(self):
        """Get a database connection."""
        if self.db_type == "postgresql":
            if not PSYCOPG2_AVAILABLE:
                raise RuntimeError("PostgreSQL requires psycopg2")
            return psycopg2.connect(**self.db_config)
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if self.db_type == "postgresql":
            id_type = "SERIAL PRIMARY KEY"
            timestamp_default = "DEFAULT CURRENT_TIMESTAMP"
        else:
            id_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
            timestamp_default = "DEFAULT CURRENT_TIMESTAMP"

        # Create playlists table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS playlists (
                id {id_type},
                user_email TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                category TEXT,
                is_public BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP {timestamp_default},
                updated_at TIMESTAMP {timestamp_default}
            )
        """)

        # Create playlist_items table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS playlist_items (
                id {id_type},
                playlist_id INTEGER NOT NULL,
                call_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                notes TEXT,
                highlight_start_sec REAL,
                highlight_end_sec REAL,
                created_at TIMESTAMP {timestamp_default},
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE CASCADE
            )
        """)

        # Create training_progress table (tracks rep progress through playlists)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS training_progress (
                id {id_type},
                playlist_id INTEGER NOT NULL,
                rep_email TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                completed_at TIMESTAMP,
                notes TEXT,
                self_score INTEGER,
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES playlist_items(id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_playlists_user ON playlists(user_email)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_playlist_items_playlist ON playlist_items(playlist_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_training_progress_rep ON training_progress(rep_email)
        """)

        conn.commit()
        conn.close()

    # ==================== Playlist Management ====================

    def create_playlist(
        self,
        user_email: str,
        name: str,
        description: str = "",
        category: str = "training",
        is_public: bool = False,
    ) -> Dict[str, Any]:
        """Create a new playlist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        if self.db_type == "postgresql":
            cursor.execute(f"""
                INSERT INTO playlists (user_email, name, description, category, is_public)
                VALUES ({param}, {param}, {param}, {param}, {param})
                RETURNING id
            """, (user_email, name, description, category, is_public))
            playlist_id = cursor.fetchone()[0]
        else:
            cursor.execute(f"""
                INSERT INTO playlists (user_email, name, description, category, is_public)
                VALUES ({param}, {param}, {param}, {param}, {param})
            """, (user_email, name, description, category, is_public))
            playlist_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return self.get_playlist(playlist_id)

    def get_playlist(self, playlist_id: int) -> Optional[Dict[str, Any]]:
        """Get a playlist by ID with its items."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(f"SELECT * FROM playlists WHERE id = {param}", (playlist_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None

        playlist = dict(row)
        
        # Get items
        cursor.execute(f"""
            SELECT pi.*, c.filename, c.rep_name, c.created_at as call_date
            FROM playlist_items pi
            JOIN calls c ON pi.call_id = c.id
            WHERE pi.playlist_id = {param}
            ORDER BY pi.position
        """, (playlist_id,))
        
        playlist["items"] = [dict(item) for item in cursor.fetchall()]
        playlist["item_count"] = len(playlist["items"])
        
        conn.close()
        return playlist

    def list_playlists(
        self,
        user_email: str,
        include_public: bool = True,
    ) -> List[Dict[str, Any]]:
        """List all playlists accessible to a user."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        
        if include_public:
            query = f"""
                SELECT p.*, COUNT(pi.id) as item_count
                FROM playlists p
                LEFT JOIN playlist_items pi ON p.id = pi.playlist_id
                WHERE p.user_email = {param} OR p.is_public = TRUE
                GROUP BY p.id
                ORDER BY p.updated_at DESC
            """
            cursor.execute(query, (user_email,))
        else:
            query = f"""
                SELECT p.*, COUNT(pi.id) as item_count
                FROM playlists p
                LEFT JOIN playlist_items pi ON p.id = pi.playlist_id
                WHERE p.user_email = {param}
                GROUP BY p.id
                ORDER BY p.updated_at DESC
            """
            cursor.execute(query, (user_email,))
        
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def update_playlist(
        self,
        playlist_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_public: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update a playlist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        updates = []
        values = []

        if name is not None:
            updates.append(f"name = {param}")
            values.append(name)

        if description is not None:
            updates.append(f"description = {param}")
            values.append(description)

        if category is not None:
            updates.append(f"category = {param}")
            values.append(category)

        if is_public is not None:
            updates.append(f"is_public = {param}")
            values.append(is_public)

        updates.append(f"updated_at = {param}")
        values.append(datetime.utcnow())

        if not updates:
            conn.close()
            return self.get_playlist(playlist_id)

        values.append(playlist_id)
        query = f"UPDATE playlists SET {', '.join(updates)} WHERE id = {param}"
        cursor.execute(query, values)

        conn.commit()
        conn.close()

        return self.get_playlist(playlist_id)

    def delete_playlist(self, playlist_id: int) -> bool:
        """Delete a playlist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        cursor.execute(f"DELETE FROM playlists WHERE id = {param}", (playlist_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

    # ==================== Playlist Items ====================

    def add_item(
        self,
        playlist_id: int,
        call_id: str,
        notes: str = "",
        highlight_start_sec: Optional[float] = None,
        highlight_end_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Add a call to a playlist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        # Get next position
        cursor.execute(
            f"SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_items WHERE playlist_id = {param}",
            (playlist_id,)
        )
        position = cursor.fetchone()[0]

        if self.db_type == "postgresql":
            cursor.execute(f"""
                INSERT INTO playlist_items 
                (playlist_id, call_id, position, notes, highlight_start_sec, highlight_end_sec)
                VALUES ({param}, {param}, {param}, {param}, {param}, {param})
                RETURNING id
            """, (playlist_id, call_id, position, notes, highlight_start_sec, highlight_end_sec))
            item_id = cursor.fetchone()[0]
        else:
            cursor.execute(f"""
                INSERT INTO playlist_items 
                (playlist_id, call_id, position, notes, highlight_start_sec, highlight_end_sec)
                VALUES ({param}, {param}, {param}, {param}, {param}, {param})
            """, (playlist_id, call_id, position, notes, highlight_start_sec, highlight_end_sec))
            item_id = cursor.lastrowid

        # Update playlist timestamp
        cursor.execute(
            f"UPDATE playlists SET updated_at = {param} WHERE id = {param}",
            (datetime.utcnow(), playlist_id)
        )

        conn.commit()
        conn.close()

        return self.get_item(item_id)

    def get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Get a playlist item by ID."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(f"""
            SELECT pi.*, c.filename, c.rep_name
            FROM playlist_items pi
            JOIN calls c ON pi.call_id = c.id
            WHERE pi.id = {param}
        """, (item_id,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def update_item(
        self,
        item_id: int,
        notes: Optional[str] = None,
        highlight_start_sec: Optional[float] = None,
        highlight_end_sec: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update a playlist item."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        updates = []
        values = []

        if notes is not None:
            updates.append(f"notes = {param}")
            values.append(notes)

        if highlight_start_sec is not None:
            updates.append(f"highlight_start_sec = {param}")
            values.append(highlight_start_sec)

        if highlight_end_sec is not None:
            updates.append(f"highlight_end_sec = {param}")
            values.append(highlight_end_sec)

        if not updates:
            conn.close()
            return self.get_item(item_id)

        values.append(item_id)
        query = f"UPDATE playlist_items SET {', '.join(updates)} WHERE id = {param}"
        cursor.execute(query, values)

        conn.commit()
        conn.close()

        return self.get_item(item_id)

    def remove_item(self, item_id: int) -> bool:
        """Remove an item from a playlist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        cursor.execute(f"DELETE FROM playlist_items WHERE id = {param}", (item_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

    def reorder_items(self, playlist_id: int, item_ids: List[int]) -> bool:
        """Reorder items in a playlist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        for position, item_id in enumerate(item_ids, 1):
            cursor.execute(
                f"UPDATE playlist_items SET position = {param} WHERE id = {param} AND playlist_id = {param}",
                (position, item_id, playlist_id)
            )

        conn.commit()
        conn.close()

        return True

    # ==================== Training Progress ====================

    def mark_item_complete(
        self,
        playlist_id: int,
        item_id: int,
        rep_email: str,
        notes: str = "",
        self_score: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Mark a playlist item as completed by a rep."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        # Check if already exists
        cursor.execute(f"""
            SELECT id FROM training_progress 
            WHERE playlist_id = {param} AND item_id = {param} AND rep_email = {param}
        """, (playlist_id, item_id, rep_email))
        existing = cursor.fetchone()

        if existing:
            # Update existing
            cursor.execute(f"""
                UPDATE training_progress 
                SET completed_at = {param}, notes = {param}, self_score = {param}
                WHERE playlist_id = {param} AND item_id = {param} AND rep_email = {param}
            """, (datetime.utcnow(), notes, self_score, playlist_id, item_id, rep_email))
        else:
            # Insert new
            cursor.execute(f"""
                INSERT INTO training_progress (playlist_id, rep_email, item_id, completed_at, notes, self_score)
                VALUES ({param}, {param}, {param}, {param}, {param}, {param})
            """, (playlist_id, rep_email, item_id, datetime.utcnow(), notes, self_score))

        conn.commit()
        conn.close()

        return self.get_rep_progress(playlist_id, rep_email)

    def get_rep_progress(self, playlist_id: int, rep_email: str) -> Dict[str, Any]:
        """Get a rep's progress through a playlist."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"

        # Get playlist item count
        cursor.execute(
            f"SELECT COUNT(*) FROM playlist_items WHERE playlist_id = {param}",
            (playlist_id,)
        )
        total_items = cursor.fetchone()[0]

        # Get completed items
        cursor.execute(f"""
            SELECT tp.*, pi.call_id
            FROM training_progress tp
            JOIN playlist_items pi ON tp.item_id = pi.id
            WHERE tp.playlist_id = {param} AND tp.rep_email = {param}
            ORDER BY tp.completed_at
        """, (playlist_id, rep_email))
        completed = [dict(row) for row in cursor.fetchall()]

        # Calculate average self-score
        scores = [c["self_score"] for c in completed if c.get("self_score")]
        avg_score = sum(scores) / len(scores) if scores else None

        conn.close()

        return {
            "playlist_id": playlist_id,
            "rep_email": rep_email,
            "total_items": total_items,
            "completed_count": len(completed),
            "completion_pct": round(len(completed) / total_items * 100) if total_items else 0,
            "avg_self_score": round(avg_score, 1) if avg_score else None,
            "completed_items": completed,
        }

    def get_playlist_completion_stats(self, playlist_id: int) -> Dict[str, Any]:
        """Get completion statistics for a playlist across all reps."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"

        # Get unique reps who started this playlist
        cursor.execute(f"""
            SELECT DISTINCT rep_email FROM training_progress WHERE playlist_id = {param}
        """, (playlist_id,))
        reps = [row[0] if self.db_type == "sqlite" else row["rep_email"] for row in cursor.fetchall()]

        # Get item count
        cursor.execute(
            f"SELECT COUNT(*) FROM playlist_items WHERE playlist_id = {param}",
            (playlist_id,)
        )
        total_items = cursor.fetchone()[0]

        # Get completion stats per rep
        rep_stats = []
        for rep_email in reps:
            progress = self.get_rep_progress(playlist_id, rep_email)
            rep_stats.append({
                "rep_email": rep_email,
                "completed": progress["completed_count"],
                "completion_pct": progress["completion_pct"],
                "avg_self_score": progress["avg_self_score"],
            })

        conn.close()

        return {
            "playlist_id": playlist_id,
            "total_items": total_items,
            "reps_started": len(reps),
            "reps_completed": sum(1 for r in rep_stats if r["completion_pct"] == 100),
            "rep_stats": sorted(rep_stats, key=lambda x: -x["completion_pct"]),
        }

