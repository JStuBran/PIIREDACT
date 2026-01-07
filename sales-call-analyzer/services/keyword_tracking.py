"""Keyword and Topic Tracking service - track custom keywords and call phases."""

import json
import logging
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Try to import PostgreSQL driver
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


# Default keyword libraries
DEFAULT_KEYWORD_LIBRARIES = {
    "objections": {
        "name": "Common Objections",
        "keywords": [
            "too expensive", "not in budget", "too much",
            "need to think", "not ready", "bad timing",
            "already using", "happy with current", "not interested",
            "send information", "call back later", "busy",
        ]
    },
    "buying_signals": {
        "name": "Buying Signals",
        "keywords": [
            "how much", "pricing", "discount", "contract",
            "when can we start", "implementation", "onboarding",
            "next steps", "timeline", "decision", "sign up",
            "sounds good", "interested", "tell me more",
        ]
    },
    "pain_points": {
        "name": "Pain Points",
        "keywords": [
            "struggling", "challenge", "problem", "issue",
            "frustrated", "difficult", "inefficient", "time consuming",
            "manual", "error", "mistake", "losing", "missing",
        ]
    },
    "competitors": {
        "name": "Competitor Mentions",
        "keywords": []  # Users should customize this
    },
}

# Call phase patterns
CALL_PHASE_PATTERNS = {
    "introduction": {
        "keywords": ["hi", "hello", "how are you", "thanks for taking", "appreciate your time"],
        "typical_position": "start",  # start, middle, end
    },
    "rapport_building": {
        "keywords": ["how's your day", "how's business", "hope you're well", "good to connect"],
        "typical_position": "start",
    },
    "discovery": {
        "keywords": ["tell me about", "what's your", "how do you currently", "challenges", "goals"],
        "typical_position": "start",
    },
    "presentation": {
        "keywords": ["let me show", "what we do", "our solution", "feature", "benefit", "how it works"],
        "typical_position": "middle",
    },
    "objection_handling": {
        "keywords": ["understand your concern", "that's a good point", "let me address", "i hear you"],
        "typical_position": "middle",
    },
    "closing": {
        "keywords": ["next steps", "move forward", "start", "sign up", "get started", "decision"],
        "typical_position": "end",
    },
    "wrap_up": {
        "keywords": ["thank you for your time", "appreciate", "follow up", "send over", "goodbye", "take care"],
        "typical_position": "end",
    },
}


class KeywordTrackingService:
    """Service for keyword tracking and topic detection."""

    def __init__(self, db_path: Optional[str] = None, database_url: Optional[str] = None):
        """Initialize the keyword tracking service."""
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
            logger.info("KeywordTrackingService initialized: PostgreSQL")
        else:
            self.db_type = "sqlite"
            if not db_path:
                db_path = os.environ.get("DATABASE_PATH", "sales_calls.db")
            self.db_path = db_path
            logger.info(f"KeywordTrackingService initialized: SQLite at {db_path}")

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

        # Create keyword libraries table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS keyword_libraries (
                id {id_type},
                user_email TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                keywords_json TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP {timestamp_default}
            )
        """)

        # Create keyword occurrences table (for tracking across calls)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS keyword_occurrences (
                id {id_type},
                call_id TEXT NOT NULL,
                library_id INTEGER,
                keyword TEXT NOT NULL,
                speaker TEXT,
                timestamp_sec REAL,
                context TEXT,
                created_at TIMESTAMP {timestamp_default},
                FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_kw_lib_user ON keyword_libraries(user_email)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_kw_occ_call ON keyword_occurrences(call_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_kw_occ_keyword ON keyword_occurrences(keyword)
        """)

        conn.commit()
        conn.close()

    # ==================== Keyword Library Management ====================

    def create_library(
        self,
        user_email: str,
        name: str,
        keywords: List[str],
        category: str = "custom",
    ) -> Dict[str, Any]:
        """Create a new keyword library."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        if self.db_type == "postgresql":
            cursor.execute(f"""
                INSERT INTO keyword_libraries (user_email, name, category, keywords_json)
                VALUES ({param}, {param}, {param}, {param})
                RETURNING id
            """, (user_email, name, category, json.dumps(keywords)))
            lib_id = cursor.fetchone()[0]
        else:
            cursor.execute(f"""
                INSERT INTO keyword_libraries (user_email, name, category, keywords_json)
                VALUES ({param}, {param}, {param}, {param})
            """, (user_email, name, category, json.dumps(keywords)))
            lib_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return self.get_library(lib_id)

    def get_library(self, library_id: int) -> Optional[Dict[str, Any]]:
        """Get a keyword library by ID."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(f"SELECT * FROM keyword_libraries WHERE id = {param}", (library_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._library_row_to_dict(row)

    def list_libraries(self, user_email: str) -> List[Dict[str, Any]]:
        """List all keyword libraries for a user."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(
            f"SELECT * FROM keyword_libraries WHERE user_email = {param} ORDER BY name",
            (user_email,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [self._library_row_to_dict(row) for row in rows]

    def get_or_create_default_libraries(self, user_email: str) -> List[Dict[str, Any]]:
        """Get user's libraries, creating defaults if none exist."""
        libraries = self.list_libraries(user_email)
        
        if not libraries:
            # Create default libraries
            for category, lib_data in DEFAULT_KEYWORD_LIBRARIES.items():
                if lib_data["keywords"]:  # Only create if has keywords
                    self.create_library(
                        user_email=user_email,
                        name=lib_data["name"],
                        keywords=lib_data["keywords"],
                        category=category,
                    )
            libraries = self.list_libraries(user_email)
        
        return libraries

    def update_library(
        self,
        library_id: int,
        name: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update a keyword library."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        updates = []
        values = []

        if name is not None:
            updates.append(f"name = {param}")
            values.append(name)

        if keywords is not None:
            updates.append(f"keywords_json = {param}")
            values.append(json.dumps(keywords))

        if is_active is not None:
            updates.append(f"is_active = {param}")
            values.append(is_active)

        if not updates:
            conn.close()
            return self.get_library(library_id)

        values.append(library_id)
        query = f"UPDATE keyword_libraries SET {', '.join(updates)} WHERE id = {param}"
        cursor.execute(query, values)

        conn.commit()
        conn.close()

        return self.get_library(library_id)

    def delete_library(self, library_id: int) -> bool:
        """Delete a keyword library."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        cursor.execute(f"DELETE FROM keyword_libraries WHERE id = {param}", (library_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

    def _library_row_to_dict(self, row) -> Dict[str, Any]:
        """Convert library row to dict."""
        d = dict(row)
        if d.get("keywords_json"):
            try:
                d["keywords"] = json.loads(d["keywords_json"])
            except json.JSONDecodeError:
                d["keywords"] = []
        else:
            d["keywords"] = []
        return d

    # ==================== Keyword Detection ====================

    def detect_keywords(
        self,
        call_id: str,
        transcript: str,
        segments: List[Dict],
        user_email: str,
        save_occurrences: bool = True,
    ) -> Dict[str, Any]:
        """
        Detect keywords in a transcript.
        
        Args:
            call_id: Call identifier
            transcript: Full transcript text
            segments: Transcript segments
            user_email: User email for library lookup
            save_occurrences: Whether to save to database
        
        Returns:
            Dict with detected keywords and statistics
        """
        libraries = self.get_or_create_default_libraries(user_email)
        active_libraries = [lib for lib in libraries if lib.get("is_active", True)]
        
        results = {
            "by_library": {},
            "by_speaker": {},
            "timeline": [],
            "summary": {
                "total_keywords_found": 0,
                "libraries_with_matches": 0,
            }
        }
        
        # Track all occurrences
        all_occurrences = []
        
        for library in active_libraries:
            lib_name = library["name"]
            lib_id = library["id"]
            keywords = library.get("keywords", [])
            
            if not keywords:
                continue
            
            lib_results = {
                "matches": [],
                "total_count": 0,
                "unique_keywords": set(),
            }
            
            # Search in segments for precise timestamps
            for seg in segments:
                text_lower = seg.get("text", "").lower()
                speaker = seg.get("speaker", "unknown")
                start_time = seg.get("start", 0)
                
                for keyword in keywords:
                    keyword_lower = keyword.lower()
                    
                    # Find all occurrences in this segment
                    index = text_lower.find(keyword_lower)
                    while index != -1:
                        # Get context (surrounding words)
                        context_start = max(0, index - 30)
                        context_end = min(len(seg.get("text", "")), index + len(keyword) + 30)
                        context = seg.get("text", "")[context_start:context_end]
                        if context_start > 0:
                            context = "..." + context
                        if context_end < len(seg.get("text", "")):
                            context = context + "..."
                        
                        occurrence = {
                            "keyword": keyword,
                            "speaker": speaker,
                            "timestamp_sec": start_time,
                            "context": context,
                            "library_id": lib_id,
                            "library_name": lib_name,
                        }
                        
                        lib_results["matches"].append(occurrence)
                        lib_results["total_count"] += 1
                        lib_results["unique_keywords"].add(keyword)
                        all_occurrences.append(occurrence)
                        
                        # Track by speaker
                        if speaker not in results["by_speaker"]:
                            results["by_speaker"][speaker] = []
                        results["by_speaker"][speaker].append(occurrence)
                        
                        # Find next occurrence
                        index = text_lower.find(keyword_lower, index + 1)
            
            if lib_results["total_count"] > 0:
                lib_results["unique_keywords"] = list(lib_results["unique_keywords"])
                results["by_library"][lib_name] = lib_results
                results["summary"]["libraries_with_matches"] += 1
        
        # Sort timeline by timestamp
        all_occurrences.sort(key=lambda x: x["timestamp_sec"])
        results["timeline"] = all_occurrences[:50]  # Limit timeline entries
        results["summary"]["total_keywords_found"] = len(all_occurrences)
        
        # Save occurrences to database if requested
        if save_occurrences and all_occurrences:
            self._save_occurrences(call_id, all_occurrences)
        
        return results

    def _save_occurrences(self, call_id: str, occurrences: List[Dict]):
        """Save keyword occurrences to database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        # Clear existing occurrences for this call
        cursor.execute(
            f"DELETE FROM keyword_occurrences WHERE call_id = {param}",
            (call_id,)
        )

        # Insert new occurrences
        for occ in occurrences[:100]:  # Limit to 100 per call
            cursor.execute(f"""
                INSERT INTO keyword_occurrences 
                (call_id, library_id, keyword, speaker, timestamp_sec, context)
                VALUES ({param}, {param}, {param}, {param}, {param}, {param})
            """, (
                call_id,
                occ.get("library_id"),
                occ["keyword"],
                occ.get("speaker"),
                occ.get("timestamp_sec"),
                occ.get("context"),
            ))

        conn.commit()
        conn.close()

    # ==================== Call Phase Detection ====================

    def detect_call_phases(
        self,
        segments: List[Dict],
    ) -> Dict[str, Any]:
        """
        Detect call phases/structure from transcript segments.
        
        Returns phases with their timing and content.
        """
        if not segments:
            return {"phases": [], "structure_score": 0}
        
        total_duration = segments[-1].get("end", 0) if segments else 0
        if total_duration == 0:
            return {"phases": [], "structure_score": 0}
        
        # Divide call into thirds
        third_duration = total_duration / 3
        
        detected_phases = []
        phase_evidence = defaultdict(list)
        
        # Scan segments for phase indicators
        for seg in segments:
            text_lower = seg.get("text", "").lower()
            start_time = seg.get("start", 0)
            
            # Determine position in call
            if start_time < third_duration:
                position = "start"
            elif start_time < 2 * third_duration:
                position = "middle"
            else:
                position = "end"
            
            # Check against each phase pattern
            for phase_name, phase_info in CALL_PHASE_PATTERNS.items():
                for keyword in phase_info["keywords"]:
                    if keyword in text_lower:
                        phase_evidence[phase_name].append({
                            "timestamp": start_time,
                            "position": position,
                            "expected_position": phase_info["typical_position"],
                            "context": seg.get("text", "")[:100],
                        })
                        break
        
        # Build phase timeline
        phase_order = [
            "introduction", "rapport_building", "discovery",
            "presentation", "objection_handling", "closing", "wrap_up"
        ]
        
        for phase_name in phase_order:
            evidence = phase_evidence.get(phase_name, [])
            if evidence:
                # Get earliest occurrence
                earliest = min(evidence, key=lambda x: x["timestamp"])
                detected_phases.append({
                    "phase": phase_name,
                    "timestamp_sec": earliest["timestamp"],
                    "evidence_count": len(evidence),
                    "position_match": earliest["position"] == earliest["expected_position"],
                    "context": earliest["context"],
                })
        
        # Calculate structure score (0-100)
        # Points for having key phases in right order and position
        structure_score = 0
        has_intro = "introduction" in [p["phase"] for p in detected_phases]
        has_discovery = "discovery" in [p["phase"] for p in detected_phases]
        has_closing = "closing" in [p["phase"] for p in detected_phases]
        
        if has_intro:
            structure_score += 20
        if has_discovery:
            structure_score += 30
        if has_closing:
            structure_score += 30
        
        # Bonus for correct ordering
        correct_order = all(
            detected_phases[i]["timestamp_sec"] <= detected_phases[i+1]["timestamp_sec"]
            for i in range(len(detected_phases) - 1)
        )
        if correct_order and len(detected_phases) >= 3:
            structure_score += 20
        
        return {
            "phases": detected_phases,
            "structure_score": structure_score,
            "has_introduction": has_intro,
            "has_discovery": has_discovery,
            "has_closing": has_closing,
            "assessment": "good" if structure_score >= 70 else "needs_improvement" if structure_score >= 40 else "poor",
        }

    # ==================== Analytics ====================

    def get_keyword_trends(
        self,
        user_email: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get keyword frequency trends over time."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"

        # Get keyword counts by library
        query = f"""
            SELECT kl.name as library_name, ko.keyword, COUNT(*) as count
            FROM keyword_occurrences ko
            JOIN keyword_libraries kl ON ko.library_id = kl.id
            JOIN calls c ON ko.call_id = c.id
            WHERE c.user_email = {param}
            GROUP BY kl.name, ko.keyword
            ORDER BY count DESC
            LIMIT 50
        """
        cursor.execute(query, (user_email,))
        
        keyword_counts = defaultdict(list)
        for row in cursor.fetchall():
            if self.db_type == "postgresql":
                keyword_counts[row["library_name"]].append({
                    "keyword": row["keyword"],
                    "count": row["count"],
                })
            else:
                keyword_counts[row[0]].append({
                    "keyword": row[1],
                    "count": row[2],
                })

        conn.close()

        return {
            "by_library": dict(keyword_counts),
            "period_days": days,
        }

    def get_call_keywords(self, call_id: str) -> List[Dict[str, Any]]:
        """Get all keyword occurrences for a specific call."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        
        cursor.execute(f"""
            SELECT ko.*, kl.name as library_name
            FROM keyword_occurrences ko
            LEFT JOIN keyword_libraries kl ON ko.library_id = kl.id
            WHERE ko.call_id = {param}
            ORDER BY ko.timestamp_sec
        """, (call_id,))
        
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

