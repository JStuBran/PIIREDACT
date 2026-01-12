"""REST API v1 - Programmatic access to Sales Call Analyzer."""

import hmac
import hashlib
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from flask import Blueprint, request, jsonify, current_app

from config import Config
from services.logging_security import get_secure_logger, sanitize_string, sanitize_dict
from services.secure_storage import SecureStorageService

logger = get_secure_logger(__name__)

# Create API blueprint
api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# Try to import PostgreSQL driver
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


# ============================================================================
# API Key Authentication
# ============================================================================

def _get_db_connection():
    """Get database connection."""
    database_url = os.environ.get("DATABASE_URL")
    
    if database_url:
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("PostgreSQL requires psycopg2")
        parsed = urlparse(database_url)
        return psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/"),
            user=parsed.username,
            password=parsed.password,
        )
    else:
        db_path = os.environ.get("DATABASE_PATH", "sales_calls.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _init_api_tables():
    """Initialize API-related tables."""
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        id_type = "SERIAL PRIMARY KEY"
        timestamp_default = "DEFAULT CURRENT_TIMESTAMP"
    else:
        id_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
        timestamp_default = "DEFAULT CURRENT_TIMESTAMP"
    
    # API keys table
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS api_keys (
            id {id_type},
            user_email TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            name TEXT,
            permissions TEXT,
            last_used TIMESTAMP,
            created_at TIMESTAMP {timestamp_default},
            is_active BOOLEAN DEFAULT TRUE
        )
    """)
    
    # Webhooks table
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS webhooks (
            id {id_type},
            user_email TEXT NOT NULL,
            url TEXT NOT NULL,
            events TEXT NOT NULL,
            secret TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            last_triggered TIMESTAMP,
            created_at TIMESTAMP {timestamp_default}
        )
    """)
    
    # Webhook delivery log
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id {id_type},
            webhook_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            payload TEXT NOT NULL,
            status_code INTEGER,
            response TEXT,
            delivered_at TIMESTAMP {timestamp_default},
            FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    conn.close()


# Initialize tables on module load
try:
    _init_api_tables()
except Exception as e:
    logger.warning(f"Could not initialize API tables: {e}")


def require_api_key(f):
    """Decorator to require API key authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not api_key:
            return jsonify({"error": "API key required", "code": "missing_api_key"}), 401
        
        # Hash the provided key and look it up
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        conn = _get_db_connection()
        database_url = os.environ.get("DATABASE_URL")
        
        if database_url:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            param = "%s"
        else:
            cursor = conn.cursor()
            param = "?"
        
        cursor.execute(
            f"SELECT * FROM api_keys WHERE key_hash = {param} AND is_active = TRUE",
            (key_hash,)
        )
        key_record = cursor.fetchone()
        
        if not key_record:
            conn.close()
            return jsonify({"error": "Invalid API key", "code": "invalid_api_key"}), 401
        
        # Update last used
        cursor.execute(
            f"UPDATE api_keys SET last_used = {param} WHERE key_hash = {param}",
            (datetime.utcnow(), key_hash)
        )
        conn.commit()
        conn.close()
        
        # Store user context
        request.api_user_email = dict(key_record)["user_email"]
        request.api_permissions = dict(key_record).get("permissions", "read,write")
        
        return f(*args, **kwargs)
    return decorated_function


def has_permission(permission: str) -> bool:
    """Check if current API key has a specific permission."""
    permissions = getattr(request, "api_permissions", "").split(",")
    return permission in permissions or "admin" in permissions


# ============================================================================
# API Key Management
# ============================================================================

@api_v1.route("/keys", methods=["GET"])
@require_api_key
def list_api_keys():
    """List API keys for the authenticated user."""
    if not has_permission("admin"):
        return jsonify({"error": "Admin permission required"}), 403
    
    conn = _get_db_connection()
    database_url = os.environ.get("DATABASE_URL")
    
    if database_url:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        param = "%s"
    else:
        cursor = conn.cursor()
        param = "?"
    
    cursor.execute(
        f"SELECT id, name, permissions, last_used, created_at, is_active FROM api_keys WHERE user_email = {param}",
        (request.api_user_email,)
    )
    keys = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"keys": keys})


@api_v1.route("/keys", methods=["POST"])
@require_api_key
def create_api_key():
    """Create a new API key."""
    if not has_permission("admin"):
        return jsonify({"error": "Admin permission required"}), 403
    
    data = request.get_json() or {}
    name = data.get("name", "API Key")
    permissions = data.get("permissions", "read,write")
    
    # Generate new key
    raw_key = f"sk_{uuid.uuid4().hex}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    conn = _get_db_connection()
    cursor = conn.cursor()
    database_url = os.environ.get("DATABASE_URL")
    param = "%s" if database_url else "?"
    
    cursor.execute(f"""
        INSERT INTO api_keys (user_email, key_hash, name, permissions)
        VALUES ({param}, {param}, {param}, {param})
    """, (request.api_user_email, key_hash, name, permissions))
    
    conn.commit()
    conn.close()
    
    # Return the raw key only once - it cannot be retrieved later
    return jsonify({
        "key": raw_key,
        "name": name,
        "permissions": permissions,
        "warning": "Save this key securely. It cannot be retrieved again.",
    }), 201


@api_v1.route("/keys/<int:key_id>", methods=["DELETE"])
@require_api_key
def delete_api_key(key_id):
    """Delete an API key."""
    if not has_permission("admin"):
        return jsonify({"error": "Admin permission required"}), 403
    
    conn = _get_db_connection()
    cursor = conn.cursor()
    database_url = os.environ.get("DATABASE_URL")
    param = "%s" if database_url else "?"
    
    cursor.execute(
        f"DELETE FROM api_keys WHERE id = {param} AND user_email = {param}",
        (key_id, request.api_user_email)
    )
    deleted = cursor.rowcount > 0
    
    conn.commit()
    conn.close()
    
    if deleted:
        return jsonify({"message": "API key deleted"})
    return jsonify({"error": "Key not found"}), 404


# ============================================================================
# Calls API
# ============================================================================

@api_v1.route("/calls", methods=["GET"])
@require_api_key
def list_calls():
    """List calls for the authenticated user."""
    if not has_permission("read"):
        return jsonify({"error": "Read permission required"}), 403
    
    from services import DatabaseService
    db = DatabaseService()
    
    # Parse query parameters
    limit = min(int(request.args.get("limit", 50)), 100)
    offset = int(request.args.get("offset", 0))
    status = request.args.get("status")
    agent_name = request.args.get("agent") or request.args.get("rep")  # Support both params
    
    calls = db.list_calls(
        user_email=request.api_user_email,
        status=status,
        agent_name=agent_name,
        limit=limit,
        offset=offset,
    )
    
    # SECURITY: Strip sensitive data and ensure original_text is never returned
    for call in calls:
        call.pop("file_path", None)
        
        # Remove original_text from transcription_json
        if "transcription_json" in call and call["transcription_json"]:
            transcription = call["transcription_json"]
            if isinstance(transcription, str):
                try:
                    transcription = json.loads(transcription)
                except (json.JSONDecodeError, TypeError):
                    transcription = {}
            if isinstance(transcription, dict):
                transcription.pop("original_text", None)
                call["transcription_json"] = transcription
        
        # Sanitize call data
        call = sanitize_dict(call)
        call.pop("transcription_json", None)  # Large, use /calls/:id for full data
        call.pop("file_path", None)
    
    total = db.count_calls(user_email=request.api_user_email, status=status, agent_name=agent_name)
    
    return jsonify({
        "calls": calls,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
        }
    })


@api_v1.route("/calls/<call_id>", methods=["GET"])
@require_api_key
def get_call(call_id):
    """Get a specific call with full details."""
    if not has_permission("read"):
        return jsonify({"error": "Read permission required"}), 403
    
    from services import DatabaseService
    db = DatabaseService()
    
    call = db.get_call(call_id)
    
    if not call:
        return jsonify({"error": "Call not found"}), 404
    
    if call["user_email"] != request.api_user_email:
        return jsonify({"error": "Access denied"}), 403
    
    # SECURITY: Remove sensitive data before returning
    call.pop("file_path", None)
    
    # SECURITY: Ensure original_text is never returned via API
    if "transcription_json" in call and call["transcription_json"]:
        transcription = call["transcription_json"]
        if isinstance(transcription, str):
            try:
                transcription = json.loads(transcription)
            except (json.JSONDecodeError, TypeError):
                transcription = {}
        if isinstance(transcription, dict):
            transcription.pop("original_text", None)
            call["transcription_json"] = transcription
    
    # Sanitize call data
    call = sanitize_dict(call)
    
    return jsonify({"call": call})


@api_v1.route("/calls", methods=["POST"])
@require_api_key
def upload_call():
    """Upload a new call for analysis."""
    if not has_permission("write"):
        return jsonify({"error": "Write permission required"}), 403
    
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400
    
    # Validate file type
    allowed = {"wav", "mp3", "m4a", "ogg", "webm", "mp4"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        return jsonify({"error": f"Invalid file type. Allowed: {', '.join(allowed)}"}), 400
    
    from werkzeug.utils import secure_filename
    from services import DatabaseService
    
    db = DatabaseService()
    secure_storage = SecureStorageService()
    
    job_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    
    # Read file content and save securely
    file_content = file.read()
    file_path = secure_storage.save_file_secure(
        file_content=file_content,
        job_id=job_id,
        filename=filename,
    )
    
    # Create call record
    rep_name = request.form.get("rep_name", "")
    
    db.create_call(
        call_id=job_id,
        filename=filename,
        user_email=request.api_user_email,
        file_path=file_path,
        rep_name=rep_name,
    )
    
    # Start processing if requested
    start_processing = request.form.get("process", "true").lower() == "true"
    
    if start_processing:
        if Config.USE_CELERY:
            from tasks import process_call_task
            task = process_call_task.delay(
                job_id=job_id,
                file_path=file_path,
                filename=filename,
                user_email=request.api_user_email,
            )
            db.update_call(job_id, status="queued")
        else:
            from services.background_processor import BackgroundProcessor
            from services import (
                TranscriberService, AnalyzerService, PDFGeneratorService,
                EmailSenderService, AnalyticsService, ScoringService,
                ConversationIntelligenceService, KeywordTrackingService,
            )
            
            processor = BackgroundProcessor()
            services = {
                "database": db,
                "transcriber": TranscriberService(whisper_model=Config.WHISPER_MODEL),
                "analyzer": AnalyzerService(api_key=Config.OPENAI_API_KEY, model=Config.OPENAI_MODEL),
                "analytics": AnalyticsService(),
                "pdf_generator": PDFGeneratorService(),
                "email_sender": EmailSenderService(),
                "scoring": ScoringService(api_key=Config.OPENAI_API_KEY, model=Config.OPENAI_MODEL),
                "conversation_intel": ConversationIntelligenceService(),
                "keyword_tracking": KeywordTrackingService(),
                "user_email": request.api_user_email,
            }
            
            processor.process_call_async(
                job_id=job_id,
                file_path=file_path,
                filename=filename,
                user_email=request.api_user_email,
                services=services,
                config=Config,
            )
    
    return jsonify({
        "id": job_id,
        "filename": filename,
        "status": "queued" if start_processing else "pending",
        "message": "Call uploaded successfully",
    }), 201


@api_v1.route("/calls/<call_id>/score", methods=["GET"])
@require_api_key
def get_call_score(call_id):
    """Get the score for a specific call."""
    if not has_permission("read"):
        return jsonify({"error": "Read permission required"}), 403
    
    from services import DatabaseService, ScoringService
    
    db = DatabaseService()
    call = db.get_call(call_id)
    
    if not call:
        return jsonify({"error": "Call not found"}), 404
    
    if call["user_email"] != request.api_user_email:
        return jsonify({"error": "Access denied"}), 403
    
    scoring = ScoringService()
    score = scoring.get_score(call_id)
    
    if not score:
        return jsonify({"error": "Score not available"}), 404
    
    return jsonify({"score": score})


@api_v1.route("/calls/<call_id>/keywords", methods=["GET"])
@require_api_key
def get_call_keywords(call_id):
    """Get detected keywords for a specific call."""
    if not has_permission("read"):
        return jsonify({"error": "Read permission required"}), 403
    
    from services import DatabaseService, KeywordTrackingService
    
    db = DatabaseService()
    call = db.get_call(call_id)
    
    if not call:
        return jsonify({"error": "Call not found"}), 404
    
    if call["user_email"] != request.api_user_email:
        return jsonify({"error": "Access denied"}), 403
    
    kw_service = KeywordTrackingService()
    keywords = kw_service.get_call_keywords(call_id)
    
    return jsonify({"keywords": keywords})


# ============================================================================
# Analytics API
# ============================================================================

@api_v1.route("/analytics/summary", methods=["GET"])
@require_api_key
def get_analytics_summary():
    """Get summary analytics for the authenticated user."""
    if not has_permission("read"):
        return jsonify({"error": "Read permission required"}), 403
    
    from services import DatabaseService, BenchmarkService, ScoringService
    
    db = DatabaseService()
    benchmark = BenchmarkService()
    scoring = ScoringService()
    
    # Get completed calls
    calls = db.list_calls(
        user_email=request.api_user_email,
        status="complete",
        limit=1000,
    )
    
    benchmarks = benchmark.calculate_benchmarks(calls)
    leaderboard = scoring.get_leaderboard(request.api_user_email)
    score_trends = scoring.get_score_trends(request.api_user_email)
    
    return jsonify({
        "total_calls": len(calls),
        "benchmarks": benchmarks,
        "leaderboard": leaderboard,
        "score_trends": score_trends,
    })


@api_v1.route("/analytics/reps", methods=["GET"])
@require_api_key
def get_rep_analytics():
    """Get analytics broken down by rep."""
    if not has_permission("read"):
        return jsonify({"error": "Read permission required"}), 403
    
    from services import DatabaseService
    
    db = DatabaseService()
    agents = db.get_agents(user_email=request.api_user_email)
    
    agent_data = []
    for agent in agents:
        agent_calls = db.list_calls(
            user_email=request.api_user_email,
            agent_name=agent.get("agent_name"),
            status="complete",
            limit=100,
        )
        
        if agent_calls:
            avg_duration = sum(c.get("stats_json", {}).get("duration_min", 0) for c in agent_calls) / len(agent_calls)
            avg_questions = sum(c.get("stats_json", {}).get("questions", {}).get("agent_total", 0) for c in agent_calls) / len(agent_calls)
            
            agent_data.append({
                "agent_name": agent.get("agent_name"),
                "agent_id": agent.get("agent_id"),
                "call_count": len(agent_calls),
                "avg_duration_min": round(avg_duration, 1),
                "avg_questions": round(avg_questions, 1),
            })
    
    return jsonify({"agents": agent_data})


# ============================================================================
# Webhook Management
# ============================================================================

WEBHOOK_EVENTS = [
    "call.uploaded",
    "call.processing",
    "call.completed",
    "call.failed",
    "score.generated",
]


@api_v1.route("/webhooks", methods=["GET"])
@require_api_key
def list_webhooks():
    """List webhooks for the authenticated user."""
    if not has_permission("admin"):
        return jsonify({"error": "Admin permission required"}), 403
    
    conn = _get_db_connection()
    database_url = os.environ.get("DATABASE_URL")
    
    if database_url:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        param = "%s"
    else:
        cursor = conn.cursor()
        param = "?"
    
    cursor.execute(
        f"SELECT id, url, events, is_active, last_triggered, created_at FROM webhooks WHERE user_email = {param}",
        (request.api_user_email,)
    )
    webhooks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"webhooks": webhooks, "available_events": WEBHOOK_EVENTS})


@api_v1.route("/webhooks", methods=["POST"])
@require_api_key
def create_webhook():
    """Create a new webhook."""
    if not has_permission("admin"):
        return jsonify({"error": "Admin permission required"}), 403
    
    data = request.get_json() or {}
    url = data.get("url")
    events = data.get("events", ["call.completed"])
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    # Validate events
    invalid_events = [e for e in events if e not in WEBHOOK_EVENTS]
    if invalid_events:
        return jsonify({"error": f"Invalid events: {invalid_events}", "valid_events": WEBHOOK_EVENTS}), 400
    
    # Generate secret for signature verification
    secret = f"whsec_{uuid.uuid4().hex}"
    
    conn = _get_db_connection()
    cursor = conn.cursor()
    database_url = os.environ.get("DATABASE_URL")
    param = "%s" if database_url else "?"
    
    if database_url:
        cursor.execute(f"""
            INSERT INTO webhooks (user_email, url, events, secret)
            VALUES ({param}, {param}, {param}, {param})
            RETURNING id
        """, (request.api_user_email, url, json.dumps(events), secret))
        webhook_id = cursor.fetchone()[0]
    else:
        cursor.execute(f"""
            INSERT INTO webhooks (user_email, url, events, secret)
            VALUES ({param}, {param}, {param}, {param})
        """, (request.api_user_email, url, json.dumps(events), secret))
        webhook_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "id": webhook_id,
        "url": url,
        "events": events,
        "secret": secret,
        "warning": "Save this secret. It's used to verify webhook signatures.",
    }), 201


@api_v1.route("/webhooks/<int:webhook_id>", methods=["DELETE"])
@require_api_key
def delete_webhook(webhook_id):
    """Delete a webhook."""
    if not has_permission("admin"):
        return jsonify({"error": "Admin permission required"}), 403
    
    conn = _get_db_connection()
    cursor = conn.cursor()
    database_url = os.environ.get("DATABASE_URL")
    param = "%s" if database_url else "?"
    
    cursor.execute(
        f"DELETE FROM webhooks WHERE id = {param} AND user_email = {param}",
        (webhook_id, request.api_user_email)
    )
    deleted = cursor.rowcount > 0
    
    conn.commit()
    conn.close()
    
    if deleted:
        return jsonify({"message": "Webhook deleted"})
    return jsonify({"error": "Webhook not found"}), 404


@api_v1.route("/webhooks/test", methods=["POST"])
@require_api_key
def test_webhook():
    """Send a test webhook to verify configuration."""
    if not has_permission("admin"):
        return jsonify({"error": "Admin permission required"}), 403
    
    data = request.get_json() or {}
    webhook_id = data.get("webhook_id")
    
    if not webhook_id:
        return jsonify({"error": "webhook_id is required"}), 400
    
    # Trigger test event
    result = trigger_webhook(
        user_email=request.api_user_email,
        event="test",
        payload={"message": "This is a test webhook"},
        webhook_id=webhook_id,
    )
    
    return jsonify(result)


# ============================================================================
# Webhook Delivery
# ============================================================================

def trigger_webhook(
    user_email: str,
    event: str,
    payload: Dict[str, Any],
    webhook_id: Optional[int] = None,
):
    """
    Trigger webhooks for an event.
    
    Args:
        user_email: User who owns the webhooks
        event: Event type (e.g., "call.completed")
        payload: Event payload
        webhook_id: Optional specific webhook to trigger
    
    Returns:
        List of delivery results
    """
    import requests
    
    conn = _get_db_connection()
    database_url = os.environ.get("DATABASE_URL")
    
    if database_url:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        param = "%s"
    else:
        cursor = conn.cursor()
        param = "?"
    
    # Get matching webhooks
    if webhook_id:
        cursor.execute(
            f"SELECT * FROM webhooks WHERE id = {param} AND user_email = {param} AND is_active = TRUE",
            (webhook_id, user_email)
        )
    else:
        cursor.execute(
            f"SELECT * FROM webhooks WHERE user_email = {param} AND is_active = TRUE",
            (user_email,)
        )
    
    webhooks = [dict(row) for row in cursor.fetchall()]
    
    results = []
    
    for webhook in webhooks:
        # Check if webhook is subscribed to this event
        subscribed_events = json.loads(webhook.get("events", "[]"))
        if event not in subscribed_events and event != "test":
            continue
        
        # SECURITY: Sanitize payload before sending
        safe_payload = sanitize_dict(payload.copy())
        
        # Prepare payload with sanitized data
        full_payload = {
            "event": event,
            "timestamp": datetime.utcnow().isoformat(),
            "data": safe_payload,
        }
        payload_json = json.dumps(full_payload)
        
        # Generate signature
        signature = hmac.new(
            webhook["secret"].encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Event": event,
        }
        
        # Send webhook
        try:
            response = requests.post(
                webhook["url"],
                data=payload_json,
                headers=headers,
                timeout=10,
            )
            status_code = response.status_code
            response_text = response.text[:500]
            success = 200 <= status_code < 300
        except Exception as e:
            status_code = 0
            response_text = str(e)
            success = False
        
        # Log delivery
        cursor.execute(f"""
            INSERT INTO webhook_deliveries (webhook_id, event, payload, status_code, response)
            VALUES ({param}, {param}, {param}, {param}, {param})
        """, (webhook["id"], event, payload_json, status_code, response_text))
        
        # Update last triggered
        cursor.execute(
            f"UPDATE webhooks SET last_triggered = {param} WHERE id = {param}",
            (datetime.utcnow(), webhook["id"])
        )
        
        results.append({
            "webhook_id": webhook["id"],
            "url": webhook["url"],
            "success": success,
            "status_code": status_code,
            "response": response_text if not success else None,
        })
    
    conn.commit()
    conn.close()
    
    return {"deliveries": results}


# ============================================================================
# Health Check
# ============================================================================

@api_v1.route("/health", methods=["GET"])
def api_health():
    """API health check - no authentication required."""
    return jsonify({
        "status": "ok",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    })

