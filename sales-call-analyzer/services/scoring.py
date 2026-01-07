"""Scoring service - automated call scoring with customizable rubrics."""

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from openai import OpenAI

logger = logging.getLogger(__name__)

# Try to import PostgreSQL driver
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Default scoring rubric
DEFAULT_RUBRIC = {
    "name": "Standard Sales Call Rubric",
    "description": "Default rubric for evaluating sales calls",
    "criteria": [
        {
            "id": "opening",
            "name": "Opening & Rapport",
            "description": "Did the rep establish rapport and set a clear agenda?",
            "weight": 15,
            "max_score": 5,
        },
        {
            "id": "discovery",
            "name": "Discovery Questions",
            "description": "Did the rep ask effective open-ended questions to understand needs?",
            "weight": 25,
            "max_score": 5,
        },
        {
            "id": "active_listening",
            "name": "Active Listening",
            "description": "Did the rep demonstrate understanding and build on customer responses?",
            "weight": 15,
            "max_score": 5,
        },
        {
            "id": "value_proposition",
            "name": "Value Proposition",
            "description": "Did the rep clearly articulate value aligned to customer needs?",
            "weight": 15,
            "max_score": 5,
        },
        {
            "id": "objection_handling",
            "name": "Objection Handling",
            "description": "Did the rep address objections professionally and effectively?",
            "weight": 15,
            "max_score": 5,
        },
        {
            "id": "closing",
            "name": "Closing & Next Steps",
            "description": "Did the rep secure clear next steps or commitments?",
            "weight": 15,
            "max_score": 5,
        },
    ],
}

SCORING_PROMPT = """You are an expert sales call evaluator. Analyze this sales call transcript and score it according to the rubric provided.

TRANSCRIPT:
{transcript}

CALL METADATA:
- Duration: {duration_min} minutes
- Agent Talk Share: {agent_talk_pct}%

SCORING RUBRIC:
{rubric_json}

INSTRUCTIONS:
1. Score each criterion from 0 to {max_score} based on the evidence in the transcript
2. Provide a brief justification (1-2 sentences) for each score
3. Be objective and evidence-based
4. If there's no evidence for a criterion, score it lower
5. Consider both the presence AND quality of behaviors

OUTPUT FORMAT (JSON only, no markdown):
{{
  "scores": {{
    "<criterion_id>": {{
      "score": <number 0-{max_score}>,
      "justification": "<brief explanation>"
    }}
  }},
  "overall_score": <weighted average 0-100>,
  "summary": "<2-3 sentence overall assessment>",
  "top_strength": "<single most impressive aspect>",
  "top_improvement": "<single most important area to improve>"
}}
"""


class ScoringService:
    """Service for call scoring with customizable rubrics."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        db_path: Optional[str] = None,
        database_url: Optional[str] = None,
    ):
        """
        Initialize the scoring service.

        Args:
            api_key: OpenAI API key
            model: OpenAI model to use
            db_path: Path to SQLite database
            database_url: PostgreSQL connection URL
        """
        # Initialize OpenAI if API key provided
        if api_key:
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = None
        self.model = model

        # Database setup
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
            logger.info("ScoringService initialized: PostgreSQL")
        else:
            self.db_type = "sqlite"
            if not db_path:
                db_path = os.environ.get("DATABASE_PATH", "sales_calls.db")
            self.db_path = db_path
            logger.info(f"ScoringService initialized: SQLite at {db_path}")

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
        """Initialize database schema for scoring."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if self.db_type == "postgresql":
            id_type = "SERIAL PRIMARY KEY"
            timestamp_default = "DEFAULT CURRENT_TIMESTAMP"
        else:
            id_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
            timestamp_default = "DEFAULT CURRENT_TIMESTAMP"

        # Create rubrics table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS rubrics (
                id {id_type},
                user_email TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                criteria_json TEXT NOT NULL,
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP {timestamp_default},
                updated_at TIMESTAMP {timestamp_default}
            )
        """)

        # Create call_scores table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS call_scores (
                id {id_type},
                call_id TEXT NOT NULL,
                rubric_id INTEGER,
                overall_score REAL,
                scores_json TEXT NOT NULL,
                summary TEXT,
                top_strength TEXT,
                top_improvement TEXT,
                created_at TIMESTAMP {timestamp_default},
                FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE CASCADE,
                FOREIGN KEY (rubric_id) REFERENCES rubrics(id) ON DELETE SET NULL
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rubrics_user ON rubrics(user_email)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scores_call ON call_scores(call_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scores_rubric ON call_scores(rubric_id)
        """)

        conn.commit()
        conn.close()

    # ==================== Rubric Management ====================

    def create_rubric(
        self,
        user_email: str,
        name: str,
        criteria: List[Dict],
        description: str = "",
        is_default: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a new scoring rubric.

        Args:
            user_email: User who owns this rubric
            name: Rubric name
            criteria: List of criterion dicts
            description: Rubric description
            is_default: Whether this is the user's default rubric

        Returns:
            Created rubric record
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        # If setting as default, unset other defaults for this user
        if is_default:
            cursor.execute(
                f"UPDATE rubrics SET is_default = FALSE WHERE user_email = {param}",
                (user_email,)
            )

        if self.db_type == "postgresql":
            cursor.execute(f"""
                INSERT INTO rubrics (user_email, name, description, criteria_json, is_default)
                VALUES ({param}, {param}, {param}, {param}, {param})
                RETURNING id
            """, (user_email, name, description, json.dumps(criteria), is_default))
            rubric_id = cursor.fetchone()[0]
        else:
            cursor.execute(f"""
                INSERT INTO rubrics (user_email, name, description, criteria_json, is_default)
                VALUES ({param}, {param}, {param}, {param}, {param})
            """, (user_email, name, description, json.dumps(criteria), is_default))
            rubric_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return self.get_rubric(rubric_id)

    def get_rubric(self, rubric_id: int) -> Optional[Dict[str, Any]]:
        """Get a rubric by ID."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(f"SELECT * FROM rubrics WHERE id = {param}", (rubric_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._rubric_row_to_dict(row)

    def list_rubrics(self, user_email: str) -> List[Dict[str, Any]]:
        """List all rubrics for a user."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(
            f"SELECT * FROM rubrics WHERE user_email = {param} ORDER BY is_default DESC, name ASC",
            (user_email,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [self._rubric_row_to_dict(row) for row in rows]

    def get_default_rubric(self, user_email: str) -> Dict[str, Any]:
        """
        Get the default rubric for a user, or create one if none exists.
        """
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(
            f"SELECT * FROM rubrics WHERE user_email = {param} AND is_default = TRUE LIMIT 1",
            (user_email,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._rubric_row_to_dict(row)

        # Create default rubric
        return self.create_rubric(
            user_email=user_email,
            name=DEFAULT_RUBRIC["name"],
            description=DEFAULT_RUBRIC["description"],
            criteria=DEFAULT_RUBRIC["criteria"],
            is_default=True,
        )

    def update_rubric(
        self,
        rubric_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        criteria: Optional[List[Dict]] = None,
        is_default: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update a rubric."""
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

        if criteria is not None:
            updates.append(f"criteria_json = {param}")
            values.append(json.dumps(criteria))

        if is_default is not None:
            updates.append(f"is_default = {param}")
            values.append(is_default)

        updates.append(f"updated_at = {param}")
        values.append(datetime.utcnow())

        if not updates:
            conn.close()
            return self.get_rubric(rubric_id)

        values.append(rubric_id)
        query = f"UPDATE rubrics SET {', '.join(updates)} WHERE id = {param}"
        cursor.execute(query, values)

        conn.commit()
        conn.close()

        return self.get_rubric(rubric_id)

    def delete_rubric(self, rubric_id: int) -> bool:
        """Delete a rubric."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        cursor.execute(f"DELETE FROM rubrics WHERE id = {param}", (rubric_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

    def _rubric_row_to_dict(self, row) -> Dict[str, Any]:
        """Convert rubric row to dict."""
        d = dict(row)
        if d.get("criteria_json"):
            try:
                d["criteria"] = json.loads(d["criteria_json"])
            except json.JSONDecodeError:
                d["criteria"] = []
        else:
            d["criteria"] = []
        return d

    # ==================== Score Generation ====================

    def score_call(
        self,
        call_id: str,
        transcript: str,
        stats: Dict[str, Any],
        rubric_id: Optional[int] = None,
        user_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Score a call using AI based on a rubric.

        Args:
            call_id: Call identifier
            transcript: Redacted transcript text
            stats: Call statistics
            rubric_id: Optional specific rubric ID
            user_email: User email (to get default rubric if rubric_id not provided)

        Returns:
            Score results
        """
        if not self.client:
            logger.warning("No OpenAI client configured, skipping scoring")
            return self._empty_score()

        # Get rubric
        if rubric_id:
            rubric = self.get_rubric(rubric_id)
        elif user_email:
            rubric = self.get_default_rubric(user_email)
        else:
            # Use default criteria without database
            rubric = {
                "id": None,
                "criteria": DEFAULT_RUBRIC["criteria"],
            }

        if not rubric or not rubric.get("criteria"):
            logger.error("No rubric available for scoring")
            return self._empty_score()

        # Build prompt
        criteria = rubric["criteria"]
        max_score = criteria[0].get("max_score", 5) if criteria else 5
        
        # Get agent talk percentage from stats
        agent_label = stats.get("agent_label", "spk_0")
        agent_talk_pct = stats.get("talk_share_pct", {}).get(agent_label, 50)

        rubric_json = json.dumps([
            {
                "id": c["id"],
                "name": c["name"],
                "description": c["description"],
                "weight": c["weight"],
            }
            for c in criteria
        ], indent=2)

        prompt = SCORING_PROMPT.format(
            transcript=transcript,
            duration_min=stats.get("duration_min", 0),
            agent_talk_pct=agent_talk_pct,
            rubric_json=rubric_json,
            max_score=max_score,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            # Calculate weighted score if not provided
            if "overall_score" not in result or result["overall_score"] is None:
                result["overall_score"] = self._calculate_weighted_score(
                    result.get("scores", {}),
                    criteria,
                    max_score,
                )

            # Save score to database
            saved_score = self._save_score(
                call_id=call_id,
                rubric_id=rubric.get("id"),
                overall_score=result.get("overall_score", 0),
                scores=result.get("scores", {}),
                summary=result.get("summary", ""),
                top_strength=result.get("top_strength", ""),
                top_improvement=result.get("top_improvement", ""),
            )

            return saved_score

        except Exception as e:
            logger.exception(f"Scoring failed: {e}")
            return self._empty_score()

    def _calculate_weighted_score(
        self,
        scores: Dict[str, Dict],
        criteria: List[Dict],
        max_score: int,
    ) -> float:
        """Calculate weighted average score."""
        total_weight = sum(c.get("weight", 0) for c in criteria)
        if total_weight == 0:
            return 0

        weighted_sum = 0
        for criterion in criteria:
            cid = criterion["id"]
            weight = criterion.get("weight", 0)
            score_data = scores.get(cid, {})
            score = score_data.get("score", 0)
            
            # Normalize score to 0-100 scale
            normalized = (score / max_score) * 100 if max_score else 0
            weighted_sum += normalized * (weight / total_weight)

        return round(weighted_sum, 1)

    def _save_score(
        self,
        call_id: str,
        rubric_id: Optional[int],
        overall_score: float,
        scores: Dict,
        summary: str,
        top_strength: str,
        top_improvement: str,
    ) -> Dict[str, Any]:
        """Save score to database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        param = "%s" if self.db_type == "postgresql" else "?"

        # Check if score already exists for this call
        cursor.execute(
            f"SELECT id FROM call_scores WHERE call_id = {param}",
            (call_id,)
        )
        existing = cursor.fetchone()

        if existing:
            # Update existing score
            cursor.execute(f"""
                UPDATE call_scores SET
                    rubric_id = {param},
                    overall_score = {param},
                    scores_json = {param},
                    summary = {param},
                    top_strength = {param},
                    top_improvement = {param}
                WHERE call_id = {param}
            """, (rubric_id, overall_score, json.dumps(scores), summary, top_strength, top_improvement, call_id))
        else:
            # Insert new score
            cursor.execute(f"""
                INSERT INTO call_scores (call_id, rubric_id, overall_score, scores_json, summary, top_strength, top_improvement)
                VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param})
            """, (call_id, rubric_id, overall_score, json.dumps(scores), summary, top_strength, top_improvement))

        conn.commit()
        conn.close()

        return self.get_score(call_id)

    def _empty_score(self) -> Dict[str, Any]:
        """Return empty score structure."""
        return {
            "overall_score": None,
            "scores": {},
            "summary": "",
            "top_strength": "",
            "top_improvement": "",
        }

    # ==================== Score Retrieval ====================

    def get_score(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get score for a call."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"
        cursor.execute(f"SELECT * FROM call_scores WHERE call_id = {param}", (call_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._score_row_to_dict(row)

    def get_scores_for_rep(
        self,
        user_email: str,
        rep_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get scores for calls belonging to a user, optionally filtered by rep."""
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"

        if rep_name:
            query = f"""
                SELECT cs.*, c.rep_name, c.created_at as call_date
                FROM call_scores cs
                JOIN calls c ON cs.call_id = c.id
                WHERE c.user_email = {param} AND c.rep_name = {param}
                ORDER BY c.created_at DESC
                LIMIT {param}
            """
            cursor.execute(query, (user_email, rep_name, limit))
        else:
            query = f"""
                SELECT cs.*, c.rep_name, c.created_at as call_date
                FROM call_scores cs
                JOIN calls c ON cs.call_id = c.id
                WHERE c.user_email = {param}
                ORDER BY c.created_at DESC
                LIMIT {param}
            """
            cursor.execute(query, (user_email, limit))

        rows = cursor.fetchall()
        conn.close()

        return [self._score_row_to_dict(row) for row in rows]

    def get_score_trends(
        self,
        user_email: str,
        rep_name: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get score trends over time.

        Returns:
            Dict with trend data including averages by criterion
        """
        scores = self.get_scores_for_rep(user_email, rep_name, limit=500)

        if not scores:
            return {"trend": [], "averages": {}, "improvement": 0}

        # Group by week and calculate averages
        from collections import defaultdict
        weekly_scores = defaultdict(list)

        for score in scores:
            call_date = score.get("call_date")
            if call_date:
                # Get week number
                if isinstance(call_date, str):
                    call_date = datetime.fromisoformat(call_date.replace('Z', '+00:00'))
                week_key = call_date.strftime("%Y-W%W")
                weekly_scores[week_key].append(score.get("overall_score", 0))

        # Calculate trend line
        trend = []
        for week in sorted(weekly_scores.keys()):
            avg = sum(weekly_scores[week]) / len(weekly_scores[week])
            trend.append({"week": week, "avg_score": round(avg, 1), "count": len(weekly_scores[week])})

        # Calculate overall averages by criterion
        criterion_totals = defaultdict(lambda: {"sum": 0, "count": 0})
        for score in scores:
            scores_data = score.get("scores", {})
            for cid, cdata in scores_data.items():
                if isinstance(cdata, dict) and "score" in cdata:
                    criterion_totals[cid]["sum"] += cdata["score"]
                    criterion_totals[cid]["count"] += 1

        averages = {
            cid: round(data["sum"] / data["count"], 2) if data["count"] else 0
            for cid, data in criterion_totals.items()
        }

        # Calculate improvement (compare first 5 vs last 5)
        if len(scores) >= 10:
            recent = sum(s.get("overall_score", 0) for s in scores[:5]) / 5
            older = sum(s.get("overall_score", 0) for s in scores[-5:]) / 5
            improvement = round(recent - older, 1)
        else:
            improvement = 0

        return {
            "trend": trend,
            "averages": averages,
            "improvement": improvement,
            "total_calls": len(scores),
        }

    def get_leaderboard(
        self,
        user_email: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of reps by average score.

        Returns:
            List of reps with their average scores
        """
        conn = self._get_connection()
        
        if self.db_type == "postgresql":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        param = "%s" if self.db_type == "postgresql" else "?"

        query = f"""
            SELECT 
                c.rep_name,
                AVG(cs.overall_score) as avg_score,
                COUNT(*) as call_count,
                MAX(c.created_at) as last_call
            FROM call_scores cs
            JOIN calls c ON cs.call_id = c.id
            WHERE c.user_email = {param} AND c.rep_name IS NOT NULL
            GROUP BY c.rep_name
            HAVING COUNT(*) >= 3
            ORDER BY avg_score DESC
            LIMIT {param}
        """
        cursor.execute(query, (user_email, limit))
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "rep_name": row["rep_name"] if self.db_type == "postgresql" else row[0],
                "avg_score": round(row["avg_score"] if self.db_type == "postgresql" else row[1], 1),
                "call_count": row["call_count"] if self.db_type == "postgresql" else row[2],
                "last_call": row["last_call"] if self.db_type == "postgresql" else row[3],
            }
            for row in rows
        ]

    def _score_row_to_dict(self, row) -> Dict[str, Any]:
        """Convert score row to dict."""
        d = dict(row)
        if d.get("scores_json"):
            try:
                d["scores"] = json.loads(d["scores_json"])
            except json.JSONDecodeError:
                d["scores"] = {}
        else:
            d["scores"] = {}
        return d

