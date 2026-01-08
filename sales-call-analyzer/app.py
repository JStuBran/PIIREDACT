"""Sales Call Analyzer - Flask Application."""

import os
import uuid
import logging
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Optional

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    send_file,
    Response,
)
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from werkzeug.utils import secure_filename
from collections import defaultdict
import time

from config import Config

# API v1 and webhooks removed - no longer offering developer features

# Simple in-memory rate limiter (use Redis in production)
_rate_limit_store = defaultdict(list)
RATE_LIMIT_WINDOW = 300  # 5 minutes
RATE_LIMIT_MAX_REQUESTS = 5  # Max requests per window


def check_rate_limit(key: str) -> bool:
    """Check if rate limit exceeded. Returns True if OK, False if limited."""
    now = time.time()
    # Clean old entries
    _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < RATE_LIMIT_WINDOW]
    
    if len(_rate_limit_store[key]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    
    _rate_limit_store[key].append(now)
    return True
from services import (
    SecureStorageService,
    get_secure_logger,
    sanitize_string,
    safe_log_exception,
    TranscriberService,
    AnalyzerService,
    PDFGeneratorService,
    EmailSenderService,
    DatabaseService,
    ComparisonService,
    AnalyticsService,
    AnnotationsService,
    ExporterService,
    BenchmarkService,
    ScoringService,
    ConversationIntelligenceService,
    KeywordTrackingService,
    PlaylistService,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = get_secure_logger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# Security settings
app.config["SESSION_COOKIE_SECURE"] = True  # Only send cookies over HTTPS
app.config["SESSION_COOKIE_HTTPONLY"] = True  # Prevent JS access to cookies
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # CSRF protection


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Ensure upload folder exists
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

# Register API blueprint
# API v1 blueprint registration removed

# Token serializer for magic links
serializer = URLSafeTimedSerializer(Config.SECRET_KEY)

# Initialize services (lazy loading)
_transcriber: Optional[TranscriberService] = None
_analyzer: Optional[AnalyzerService] = None
_pdf_generator: Optional[PDFGeneratorService] = None
_email_sender: Optional[EmailSenderService] = None
_database: Optional[DatabaseService] = None
_comparison: Optional[ComparisonService] = None
_analytics: Optional[AnalyticsService] = None
_annotations: Optional[AnnotationsService] = None
_exporter: Optional[ExporterService] = None
_benchmark: Optional[BenchmarkService] = None
_scoring: Optional[ScoringService] = None
_conversation_intel: Optional[ConversationIntelligenceService] = None
_keyword_tracking: Optional[KeywordTrackingService] = None
_playlists: Optional[PlaylistService] = None


def get_transcriber() -> TranscriberService:
    """Get or create transcriber service."""
    global _transcriber
    if _transcriber is None:
        _transcriber = TranscriberService(whisper_model=Config.WHISPER_MODEL)
    return _transcriber


def get_analyzer() -> AnalyzerService:
    """Get or create analyzer service."""
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerService(
            api_key=Config.OPENAI_API_KEY,
            model=Config.OPENAI_MODEL,
        )
    return _analyzer


def get_pdf_generator() -> PDFGeneratorService:
    """Get or create PDF generator service."""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = PDFGeneratorService()
    return _pdf_generator


def get_email_sender() -> EmailSenderService:
    """Get or create email sender service."""
    global _email_sender
    if _email_sender is None:
        _email_sender = EmailSenderService()
    return _email_sender


def get_database() -> DatabaseService:
    """Get or create database service."""
    global _database
    if _database is None:
        # DatabaseService auto-detects DATABASE_URL (for PostgreSQL) or falls back to SQLite
        # Pass db_path only as fallback for SQLite (DatabaseService checks DATABASE_URL first)
        _database = DatabaseService(db_path=Config.DATABASE_PATH)
    return _database


def get_comparison() -> ComparisonService:
    """Get or create comparison service."""
    global _comparison
    if _comparison is None:
        _comparison = ComparisonService()
    return _comparison


def get_analytics() -> AnalyticsService:
    """Get or create analytics service."""
    global _analytics
    if _analytics is None:
        _analytics = AnalyticsService()
    return _analytics


def get_annotations() -> AnnotationsService:
    """Get or create annotations service."""
    global _annotations
    if _annotations is None:
        # AnnotationsService auto-detects DATABASE_URL (for PostgreSQL) or falls back to SQLite
        # Pass db_path only as fallback for SQLite (AnnotationsService checks DATABASE_URL first)
        _annotations = AnnotationsService(db_path=Config.DATABASE_PATH)
    return _annotations


def get_exporter() -> ExporterService:
    """Get or create exporter service."""
    global _exporter
    if _exporter is None:
        _exporter = ExporterService()
    return _exporter


def get_benchmark() -> BenchmarkService:
    """Get or create benchmark service."""
    global _benchmark
    if _benchmark is None:
        _benchmark = BenchmarkService()
    return _benchmark


def get_scoring() -> ScoringService:
    """Get or create scoring service."""
    global _scoring
    if _scoring is None:
        _scoring = ScoringService(
            api_key=Config.OPENAI_API_KEY,
            model=Config.OPENAI_MODEL,
        )
    return _scoring


def get_conversation_intel() -> ConversationIntelligenceService:
    """Get or create conversation intelligence service."""
    global _conversation_intel
    if _conversation_intel is None:
        _conversation_intel = ConversationIntelligenceService()
    return _conversation_intel


def get_keyword_tracking() -> KeywordTrackingService:
    """Get or create keyword tracking service."""
    global _keyword_tracking
    if _keyword_tracking is None:
        _keyword_tracking = KeywordTrackingService()
    return _keyword_tracking


def get_playlists() -> PlaylistService:
    """Get or create playlist service."""
    global _playlists
    if _playlists is None:
        _playlists = PlaylistService()
    return _playlists


def login_required(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_email" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS


# ============================================================================
# Routes
# ============================================================================

@app.route("/")
def index():
    """Redirect to dashboard if logged in, otherwise login."""
    if "user_email" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page - enter email to receive magic link."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        
        if not email:
            flash("Please enter your email address.", "error")
            return render_template("login.html")
        
        # Rate limit by IP to prevent enumeration/spam
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if not check_rate_limit(f"login:{client_ip}"):
            flash("Too many login attempts. Please try again in a few minutes.", "error")
            return render_template("login.html")
        
        # Check whitelist
        if not Config.is_email_allowed(email):
            flash("This email is not authorized. Contact your administrator.", "error")
            return render_template("login.html")
        
        # Generate magic link token
        token = serializer.dumps(email, salt="magic-link")
        magic_link = f"{Config.APP_URL}/auth/{token}"
        
        # Send email with magic link
        try:
            email_sender = get_email_sender()
            email_sender.send_magic_link(email, magic_link)
            flash("Check your email for a login link!", "success")
            return render_template("login.html", email_sent=True)
        except Exception as e:
            logger.error(f"Failed to send magic link: {e}")
            # In dev mode, show the link directly
            if app.debug:
                flash(f"Dev mode - Magic link: {magic_link}", "info")
            else:
                flash("Failed to send email. Please try again.", "error")
    
    return render_template("login.html")


@app.route("/auth/<token>")
def auth(token):
    """Verify magic link and create session."""
    try:
        # Token expires after configured minutes
        email = serializer.loads(
            token,
            salt="magic-link",
            max_age=Config.MAGIC_LINK_EXPIRY_MINUTES * 60,
        )
        
        # Regenerate session to prevent session fixation
        session.clear()
        
        # Create new session
        session["user_email"] = email
        session.permanent = True
        app.permanent_session_lifetime = timedelta(hours=24)
        
        flash(f"Welcome, {email}!", "success")
        return redirect(url_for("upload"))
        
    except SignatureExpired:
        flash("This link has expired. Please request a new one.", "error")
        return redirect(url_for("login"))
    except BadSignature:
        flash("Invalid link. Please request a new one.", "error")
        return redirect(url_for("login"))


@app.route("/logout")
def logout():
    """Log out and clear session."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    """Upload page - drag and drop audio file(s)."""
    if request.method == "POST":
        # Support both single file and multiple files
        files = request.files.getlist("audio")
        
        if not files or all(f.filename == "" for f in files):
            flash("No audio file provided.", "error")
            return render_template("upload.html")
        
        # Get optional rep name and call type from form
        rep_name = request.form.get("rep_name", "").strip() or None
        call_type = request.form.get("call_type", "real").strip()
        
        # Validate call_type
        if call_type not in ["real", "ai_agent"]:
            call_type = "real"
        
        # Validate and save files
        db = get_database()
        secure_storage = SecureStorageService()
        job_ids = []
        
        for file in files:
            if file.filename == "":
                continue
            
            if not allowed_file(file.filename):
                safe_filename = sanitize_string(file.filename)
                flash(f"Invalid file type. Allowed: {', '.join(Config.ALLOWED_EXTENSIONS)}", "error")
                continue
            
            try:
                # Read file content
                file_content = file.read()
                
                # Save file securely (encrypted, with proper permissions)
                job_id = str(uuid.uuid4())
                filename = secure_filename(file.filename)
                file_path = secure_storage.save_file_secure(
                    file_content=file_content,
                    job_id=job_id,
                    filename=filename,
                )
                
                # Create call record in database
                db.create_call(
                    call_id=job_id,
                    filename=filename,
                    user_email=session["user_email"],
                    file_path=file_path,
                    rep_name=rep_name,
                    call_type=call_type,
                )
                
                job_ids.append(job_id)
                
            except Exception as e:
                logger = get_secure_logger(__name__)
                safe_log_exception(logger, f"Failed to upload file: {e}", exc_info=True)
                flash("Failed to upload file. Please try again.", "error")
                continue
        
        if not job_ids:
            flash("No valid files uploaded.", "error")
            return render_template("upload.html")
        
        # If single file, redirect to processing. If multiple, redirect to batch view
        if len(job_ids) == 1:
            return redirect(url_for("process", job_id=job_ids[0]))
        else:
            flash(f"Uploaded {len(job_ids)} files. Processing will begin shortly.", "success")
            return redirect(url_for("history"))
    
    return render_template("upload.html", user_email=session.get("user_email"))


@app.route("/process/<job_id>")
@login_required
def process(job_id):
    """Processing page - shows progress and triggers analysis."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("upload"))
    
    # Verify ownership
    if job["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("upload"))
    
    return render_template("processing.html", job=job)


@app.route("/api/analyze/<job_id>", methods=["POST"])
@login_required
def api_analyze(job_id):
    """API endpoint to start analysis (called from processing page)."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    if job["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    if job["status"] != "pending":
        return jsonify({"error": "Job already processing or complete"}), 400
    
    # Check if Celery is enabled
    if Config.USE_CELERY:
        # Use Celery for distributed processing
        from tasks import process_call_task
        
        task = process_call_task.delay(
            job_id=job_id,
            file_path=job["file_path"],
            filename=job["filename"],
            user_email=job["user_email"],
        )
        
        # Store task ID for status tracking
        db.update_call(job_id, status="queued")
        
        return jsonify({
            "status": "queued",
            "task_id": task.id,
            "message": "Job queued for processing.",
        })
    
    else:
        # Use in-process background threading (default)
        from services.background_processor import BackgroundProcessor
        
        processor = BackgroundProcessor()
        services = {
            "database": db,
            "transcriber": get_transcriber(),
            "analyzer": get_analyzer(),
            "analytics": get_analytics(),
            "pdf_generator": get_pdf_generator(),
            "email_sender": get_email_sender(),
            "scoring": get_scoring(),
            "conversation_intel": get_conversation_intel(),
            "keyword_tracking": get_keyword_tracking(),
            "user_email": job["user_email"],
        }
        
        processor.process_call_async(
            job_id=job_id,
            file_path=job["file_path"],
            filename=job["filename"],
            user_email=job["user_email"],
            services=services,
            config=Config,
        )
        
        # Return immediately - processing happens in background
        return jsonify({
            "status": "processing",
            "message": "Analysis started. This page will update automatically.",
        })


@app.route("/api/status/<job_id>")
@login_required
def api_status(job_id):
    """API endpoint to check job status."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        logger.warning(f"Job not found: {job_id} (user: {session.get('user_email')})")
        return jsonify({"error": "Job not found. This job may have been from a previous session or deployment."}), 404
    
    if job["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    return jsonify({
        "id": job["id"],
        "status": job["status"],
        "error": job.get("error"),
    })


@app.route("/report/<job_id>")
@login_required
def report(job_id):
    """View report in browser."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("upload"))
    
    if job["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("upload"))
    
    if job["status"] != "complete":
        return redirect(url_for("process", job_id=job_id))
    
    # Calculate benchmarks and percentile rankings
    benchmark_service = get_benchmark()
    all_calls = db.list_calls(
        user_email=session["user_email"],
        status="complete",
        limit=1000,
    )
    benchmarks = benchmark_service.calculate_benchmarks(all_calls)
    rankings = benchmark_service.rank_call(job, benchmarks, all_calls)
    
    # Get call score
    scoring = get_scoring()
    call_score = scoring.get_score(job_id)
    
    # Get rubric criteria names for display
    score_criteria = []
    if call_score and call_score.get("rubric_id"):
        rubric = scoring.get_rubric(call_score["rubric_id"])
        if rubric:
            for criterion in rubric.get("criteria", []):
                cid = criterion["id"]
                score_data = call_score.get("scores", {}).get(cid, {})
                score_criteria.append({
                    "name": criterion["name"],
                    "score": score_data.get("score", 0),
                    "max_score": criterion.get("max_score", 5),
                    "justification": score_data.get("justification", ""),
                    "weight": criterion.get("weight", 0),
                })
    
    return render_template(
        "report.html",
        job=job,
        analysis=job.get("analysis_json", {}),
        stats=job.get("stats_json", {}),
        benchmarks=benchmarks,
        rankings=rankings,
        call_score=call_score,
        score_criteria=score_criteria,
    )


@app.route("/download/<job_id>/<report_type>")
@login_required
def download(job_id, report_type):
    """Download PDF report."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("upload"))
    
    if job["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("upload"))
    
    if report_type == "coaching":
        pdf_path = job.get("coaching_pdf_path")
        filename = f"coaching_report_{job['filename']}.pdf"
    elif report_type == "stats":
        pdf_path = job.get("stats_pdf_path")
        filename = f"call_stats_{job['filename']}.pdf"
    else:
        flash("Invalid report type.", "error")
        return redirect(url_for("report", job_id=job_id))
    
    if not pdf_path or not os.path.exists(pdf_path):
        flash("Report not found.", "error")
        return redirect(url_for("report", job_id=job_id))
    
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


@app.route("/dashboard")
@login_required
def dashboard():
    """Dashboard showing recent calls and summary stats."""
    db = get_database()
    
    # Get recent calls
    recent_calls = db.list_calls(
        user_email=session["user_email"],
        limit=10,
        order_by="created_at DESC",
    )
    
    # Get summary stats
    stats = db.get_summary_stats(user_email=session["user_email"])
    
    # Get list of reps
    reps = db.get_reps(user_email=session["user_email"])
    
    # Calculate team benchmarks
    benchmark_service = get_benchmark()
    all_completed = db.list_calls(
        user_email=session["user_email"],
        status="complete",
        limit=1000,
    )
    benchmarks = benchmark_service.calculate_benchmarks(all_completed)
    
    # Get leaderboard and score trends
    scoring = get_scoring()
    leaderboard = scoring.get_leaderboard(session["user_email"])
    score_trends = scoring.get_score_trends(session["user_email"])
    
    return render_template(
        "dashboard.html",
        recent_calls=recent_calls,
        stats=stats,
        reps=reps,
        benchmarks=benchmarks,
        leaderboard=leaderboard,
        score_trends=score_trends,
    )


@app.route("/history")
@login_required
def history():
    """Call history with pagination and filtering."""
    db = get_database()
    
    # Get filters from query params
    page = int(request.args.get("page", 1))
    per_page = 20
    rep_filter = request.args.get("rep", "")
    status_filter = request.args.get("status", "")
    call_type_filter = request.args.get("call_type", "")
    search_query = request.args.get("search", "").strip()
    
    # Build filters
    filters = {"user_email": session["user_email"]}
    if rep_filter:
        filters["rep_name"] = rep_filter
    if status_filter:
        filters["status"] = status_filter
    if call_type_filter:
        filters["call_type"] = call_type_filter
    
    # Get calls
    offset = (page - 1) * per_page
    calls = db.list_calls(
        limit=per_page,
        offset=offset,
        order_by="created_at DESC",
        **filters,
    )
    
    # Filter by search query if provided (full-text search in transcripts)
    if search_query:
        calls = db.search_transcripts(
            query=search_query,
            user_email=session["user_email"],
            limit=per_page,
            offset=offset,
        )
        # Re-apply other filters
        if rep_filter:
            calls = [c for c in calls if c.get("rep_name") == rep_filter]
        if status_filter:
            calls = [c for c in calls if c.get("status") == status_filter]
        if call_type_filter:
            calls = [c for c in calls if c.get("call_type") == call_type_filter]
    
    # Get total count
    total_count = db.count_calls(**filters)
    if search_query:
        total_count = len(calls)  # Adjust for search filtering
    
    total_pages = (total_count + per_page - 1) // per_page
    
    # Get reps for filter dropdown
    reps = db.get_reps(user_email=session["user_email"])
    
    return render_template(
        "history.html",
        calls=calls,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        rep_filter=rep_filter,
        status_filter=status_filter,
        call_type_filter=call_type_filter,
        search_query=search_query,
        reps=reps,
    )


@app.route("/transcript/<job_id>")
@login_required
def transcript(job_id):
    """View interactive transcript."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        flash("Call not found.", "error")
        return redirect(url_for("history"))
    
    if job["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("history"))
    
    if job["status"] != "complete":
        flash("Transcript not available yet.", "warning")
        return redirect(url_for("process", job_id=job_id))
    
    transcription = job.get("transcription_json", {})
    analysis = job.get("analysis_json", {})
    
    if not transcription:
        flash("Transcript not found.", "error")
        return redirect(url_for("report", job_id=job_id))
    
    # Extract timestamp highlights from analysis
    timestamp_highlights = analysis.get("timestamp_highlights", [])
    
    return render_template(
        "transcript.html",
        job=job,
        transcription=transcription,
        segments=transcription.get("segments", []),
        redacted_text=transcription.get("redacted_text", ""),
        pii_findings=transcription.get("pii_findings", []),
        timestamp_highlights=timestamp_highlights,
    )


@app.route("/api/transcript/export/<job_id>")
@login_required
def export_transcript(job_id):
    """Export transcript as text file."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        return jsonify({"error": "Call not found"}), 404
    
    if job["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    transcription = job.get("transcription_json", {})
    if not transcription:
        return jsonify({"error": "Transcript not found"}), 404
    
    redacted_text = transcription.get("redacted_text", "")
    export_type = request.args.get("type", "text")  # text or pdf
    
    if export_type == "text":
        response = Response(
            redacted_text,
            mimetype="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename=transcript_{job['filename']}.txt"
            }
        )
        return response
    elif export_type == "pdf":
        # Use PDF generator to create transcript PDF
        pdf_generator = get_pdf_generator()
        pdf_path = os.path.join(
            Config.UPLOAD_FOLDER,
            f"{job_id}_transcript.pdf"
        )
        
        # Generate transcript PDF
        pdf_generator.generate_transcript_pdf(
            job=job,
            transcription=transcription,
            output_path=pdf_path,
        )
        
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"transcript_{job['filename']}.pdf",
            mimetype="application/pdf",
        )
    
    return jsonify({"error": "Invalid export type"}), 400


@app.route("/team")
@login_required
def team():
    """Team dashboard showing all reps and their performance."""
    db = get_database()
    
    # Get all reps for this user
    reps = db.get_reps(user_email=session["user_email"])
    
    if not reps:
        flash("No reps found. Assign rep names when uploading calls.", "info")
        return redirect(url_for("upload"))
    
    # Get stats for each rep
    rep_stats = []
    for rep in reps:
        calls = db.list_calls(
            user_email=session["user_email"],
            rep_name=rep,
            status="complete",
        )
        
        if not calls:
            continue
        
        # Calculate rep metrics
        total_calls = len(calls)
        total_duration = 0
        total_questions = 0
        total_filler = 0
        avg_talk_ratio = 0
        
        for call in calls:
            stats = call.get("stats_json", {})
            if stats:
                total_duration += stats.get("duration_min", 0)
                total_questions += stats.get("questions", {}).get("agent_total", 0)
                total_filler += stats.get("filler", {}).get("agent_count", 0)
                
                agent_label = stats.get("agent_label", "spk_0")
                talk_share = stats.get("talk_share_pct", {}).get(agent_label, 0)
                avg_talk_ratio += talk_share
        
        rep_stats.append({
            "name": rep,
            "total_calls": total_calls,
            "avg_duration": round(total_duration / total_calls, 1) if total_calls else 0,
            "avg_questions": round(total_questions / total_calls, 1) if total_calls else 0,
            "avg_filler": round(total_filler / total_calls, 1) if total_calls else 0,
            "avg_talk_ratio": round(avg_talk_ratio / total_calls, 1) if total_calls else 0,
            "recent_calls": calls[:5],  # Last 5 calls
        })
    
    # Sort by total calls
    rep_stats.sort(key=lambda x: x["total_calls"], reverse=True)
    
    return render_template("team.html", rep_stats=rep_stats)


@app.route("/compare")
@login_required
def compare():
    """Compare multiple calls side-by-side."""
    db = get_database()
    
    # Get call IDs from query params
    call_ids = request.args.getlist("call_id")
    
    if not call_ids:
        flash("Please select at least 2 calls to compare.", "warning")
        return redirect(url_for("history"))
    
    if len(call_ids) < 2:
        flash("Please select at least 2 calls to compare.", "warning")
        return redirect(url_for("history"))
    
    # Fetch calls
    calls = []
    for call_id in call_ids:
        call = db.get_call(call_id)
        if not call:
            continue
        
        # Verify ownership
        if call["user_email"] != session["user_email"]:
            continue
        
        # Only include completed calls
        if call["status"] != "complete":
            continue
        
        calls.append(call)
    
    if len(calls) < 2:
        flash("Need at least 2 completed calls to compare.", "error")
        return redirect(url_for("history"))
    
    # Compare calls
    comparison_service = get_comparison()
    comparison = comparison_service.compare_calls(calls)
    
    return render_template("compare.html", comparison=comparison)


@app.route("/api/annotations/<job_id>", methods=["GET"])
@login_required
def get_annotations_api(job_id):
    """Get annotations for a call."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        return jsonify({"error": "Call not found"}), 404
    
    if job["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    annotations_service = get_annotations()
    annotations = annotations_service.get_annotations(job_id)
    
    return jsonify({"annotations": annotations})


@app.route("/api/annotations/<job_id>", methods=["POST"])
@login_required
def create_annotation_api(job_id):
    """Create a new annotation."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        return jsonify({"error": "Call not found"}), 404
    
    if job["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    data = request.get_json()
    note = data.get("note", "").strip()
    timestamp_sec = data.get("timestamp_sec")
    
    if not note:
        return jsonify({"error": "Note is required"}), 400
    
    if timestamp_sec is not None:
        try:
            timestamp_sec = float(timestamp_sec)
        except (ValueError, TypeError):
            timestamp_sec = None
    
    annotations_service = get_annotations()
    annotation = annotations_service.create_annotation(
        call_id=job_id,
        note=note,
        timestamp_sec=timestamp_sec,
    )
    
    return jsonify({"annotation": annotation}), 201


@app.route("/api/annotations/<int:annotation_id>", methods=["PUT", "DELETE"])
@login_required
def update_annotation_api(annotation_id):
    """Update or delete an annotation."""
    annotations_service = get_annotations()
    
    # Get annotation to verify ownership
    annotation_row = annotations_service.get_annotation(annotation_id)
    
    if not annotation_row:
        return jsonify({"error": "Annotation not found"}), 404
    
    # Verify call ownership
    db = get_database()
    call = db.get_call(annotation_row["call_id"])
    if not call or call["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    if request.method == "PUT":
        data = request.get_json()
        note = data.get("note")
        timestamp_sec = data.get("timestamp_sec")
        
        if timestamp_sec is not None:
            try:
                timestamp_sec = float(timestamp_sec)
            except (ValueError, TypeError):
                timestamp_sec = None
        
        updated = annotations_service.update_annotation(
            annotation_id=annotation_id,
            note=note,
            timestamp_sec=timestamp_sec,
        )
        
        if updated:
            return jsonify({"annotation": updated})
        return jsonify({"error": "Update failed"}), 400
    
    else:  # DELETE
        deleted = annotations_service.delete_annotation(annotation_id)
        if deleted:
            return jsonify({"message": "Annotation deleted"}), 200
        return jsonify({"error": "Delete failed"}), 400


@app.route("/api/export/<export_type>")
@login_required
def export_calls(export_type):
    """Export calls in various formats."""
    db = get_database()
    
    # Get filters
    rep_filter = request.args.get("rep", "")
    status_filter = request.args.get("status", "complete")
    
    filters = {"user_email": session["user_email"], "status": status_filter}
    if rep_filter:
        filters["rep_name"] = rep_filter
    
    # Get all matching calls
    calls = db.list_calls(limit=1000, **filters)
    
    if not calls:
        flash("No calls found to export.", "warning")
        return redirect(url_for("history"))
    
    exporter = get_exporter()
    
    if export_type == "csv":
        output_path = os.path.join(Config.UPLOAD_FOLDER, f"export_{uuid.uuid4().hex[:8]}.csv")
        exporter.export_csv(calls, output_path)
        return send_file(
            output_path,
            as_attachment=True,
            download_name="calls_export.csv",
            mimetype="text/csv",
        )
    
    elif export_type == "json":
        output_path = os.path.join(Config.UPLOAD_FOLDER, f"export_{uuid.uuid4().hex[:8]}.json")
        exporter.export_json(calls, output_path)
        return send_file(
            output_path,
            as_attachment=True,
            download_name="calls_export.json",
            mimetype="application/json",
        )
    
    else:
        flash("Invalid export type.", "error")
        return redirect(url_for("history"))


@app.route("/api/export/srt/<job_id>")
@login_required
def export_srt(job_id):
    """Export transcript as SRT subtitle file."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        flash("Call not found.", "error")
        return redirect(url_for("history"))
    
    if job["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("history"))
    
    transcription = job.get("transcription_json", {})
    segments = transcription.get("segments", [])
    
    if not segments:
        flash("No transcript segments found.", "error")
        return redirect(url_for("transcript", job_id=job_id))
    
    exporter = get_exporter()
    output_path = os.path.join(Config.UPLOAD_FOLDER, f"{job_id}_transcript.srt")
    exporter.export_srt(segments, output_path)
    
    return send_file(
        output_path,
        as_attachment=True,
        download_name=f"transcript_{job['filename']}.srt",
        mimetype="text/srt",
    )


# ============================================================================
# Scoring and Rubrics Routes
# ============================================================================

@app.route("/rubrics")
@login_required
def rubrics():
    """View and manage scoring rubrics."""
    scoring = get_scoring()
    user_rubrics = scoring.list_rubrics(session["user_email"])
    
    # Ensure user has at least one rubric
    if not user_rubrics:
        scoring.get_default_rubric(session["user_email"])
        user_rubrics = scoring.list_rubrics(session["user_email"])
    
    return render_template("rubrics.html", rubrics=user_rubrics)


@app.route("/rubrics/new", methods=["GET", "POST"])
@login_required
def create_rubric():
    """Create a new scoring rubric."""
    if request.method == "POST":
        scoring = get_scoring()
        
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        is_default = request.form.get("is_default") == "on"
        
        # Parse criteria from form
        criteria = []
        i = 0
        while f"criteria_{i}_name" in request.form:
            criteria.append({
                "id": request.form.get(f"criteria_{i}_id", f"criterion_{i}").strip().lower().replace(" ", "_"),
                "name": request.form.get(f"criteria_{i}_name", "").strip(),
                "description": request.form.get(f"criteria_{i}_description", "").strip(),
                "weight": int(request.form.get(f"criteria_{i}_weight", 10)),
                "max_score": int(request.form.get(f"criteria_{i}_max_score", 5)),
            })
            i += 1
        
        if not name:
            flash("Rubric name is required.", "error")
            return render_template("rubric_form.html", rubric=None, criteria=criteria)
        
        if not criteria:
            flash("At least one criterion is required.", "error")
            return render_template("rubric_form.html", rubric=None, criteria=criteria)
        
        rubric = scoring.create_rubric(
            user_email=session["user_email"],
            name=name,
            description=description,
            criteria=criteria,
            is_default=is_default,
        )
        
        flash("Rubric created successfully!", "success")
        return redirect(url_for("rubrics"))
    
    # GET - show form with default criteria as template
    from services.scoring import DEFAULT_RUBRIC
    return render_template("rubric_form.html", rubric=None, criteria=DEFAULT_RUBRIC["criteria"])


@app.route("/rubrics/<int:rubric_id>/edit", methods=["GET", "POST"])
@login_required
def edit_rubric(rubric_id):
    """Edit an existing rubric."""
    scoring = get_scoring()
    rubric = scoring.get_rubric(rubric_id)
    
    if not rubric:
        flash("Rubric not found.", "error")
        return redirect(url_for("rubrics"))
    
    if rubric["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("rubrics"))
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        is_default = request.form.get("is_default") == "on"
        
        # Parse criteria from form
        criteria = []
        i = 0
        while f"criteria_{i}_name" in request.form:
            criteria.append({
                "id": request.form.get(f"criteria_{i}_id", f"criterion_{i}").strip().lower().replace(" ", "_"),
                "name": request.form.get(f"criteria_{i}_name", "").strip(),
                "description": request.form.get(f"criteria_{i}_description", "").strip(),
                "weight": int(request.form.get(f"criteria_{i}_weight", 10)),
                "max_score": int(request.form.get(f"criteria_{i}_max_score", 5)),
            })
            i += 1
        
        scoring.update_rubric(
            rubric_id=rubric_id,
            name=name,
            description=description,
            criteria=criteria,
            is_default=is_default,
        )
        
        flash("Rubric updated successfully!", "success")
        return redirect(url_for("rubrics"))
    
    return render_template("rubric_form.html", rubric=rubric, criteria=rubric.get("criteria", []))


@app.route("/rubrics/<int:rubric_id>/delete", methods=["POST"])
@login_required
def delete_rubric(rubric_id):
    """Delete a rubric."""
    scoring = get_scoring()
    rubric = scoring.get_rubric(rubric_id)
    
    if not rubric:
        flash("Rubric not found.", "error")
        return redirect(url_for("rubrics"))
    
    if rubric["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("rubrics"))
    
    scoring.delete_rubric(rubric_id)
    flash("Rubric deleted.", "success")
    return redirect(url_for("rubrics"))


@app.route("/api/scores/<job_id>")
@login_required
def api_get_score(job_id):
    """Get score for a call."""
    db = get_database()
    job = db.get_call(job_id)
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    if job["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    scoring = get_scoring()
    score = scoring.get_score(job_id)
    
    if not score:
        return jsonify({"error": "Score not found"}), 404
    
    return jsonify({"score": score})


@app.route("/api/leaderboard")
@login_required
def api_leaderboard():
    """Get rep leaderboard."""
    scoring = get_scoring()
    leaderboard = scoring.get_leaderboard(session["user_email"])
    return jsonify({"leaderboard": leaderboard})


@app.route("/api/score-trends")
@login_required
def api_score_trends():
    """Get score trends."""
    rep_name = request.args.get("rep")
    days = int(request.args.get("days", 30))
    
    scoring = get_scoring()
    trends = scoring.get_score_trends(
        user_email=session["user_email"],
        rep_name=rep_name if rep_name else None,
        days=days,
    )
    return jsonify(trends)


# ============================================================================
# Keyword Library Routes
# ============================================================================

@app.route("/keywords")
@login_required
def keywords():
    """View and manage keyword libraries."""
    kw_service = get_keyword_tracking()
    libraries = kw_service.get_or_create_default_libraries(session["user_email"])
    trends = kw_service.get_keyword_trends(session["user_email"])
    
    return render_template(
        "keywords.html",
        libraries=libraries,
        trends=trends,
    )


@app.route("/keywords/library/new", methods=["GET", "POST"])
@login_required
def create_keyword_library():
    """Create a new keyword library."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        keywords_text = request.form.get("keywords", "").strip()
        category = request.form.get("category", "custom")
        
        if not name:
            flash("Library name is required.", "error")
            return render_template("keyword_library_form.html", library=None)
        
        # Parse keywords (one per line or comma-separated)
        keywords = []
        for line in keywords_text.split("\n"):
            for kw in line.split(","):
                kw = kw.strip()
                if kw:
                    keywords.append(kw)
        
        if not keywords:
            flash("At least one keyword is required.", "error")
            return render_template("keyword_library_form.html", library=None)
        
        kw_service = get_keyword_tracking()
        kw_service.create_library(
            user_email=session["user_email"],
            name=name,
            keywords=keywords,
            category=category,
        )
        
        flash("Keyword library created!", "success")
        return redirect(url_for("keywords"))
    
    return render_template("keyword_library_form.html", library=None)


@app.route("/keywords/library/<int:library_id>/edit", methods=["GET", "POST"])
@login_required
def edit_keyword_library(library_id):
    """Edit a keyword library."""
    kw_service = get_keyword_tracking()
    library = kw_service.get_library(library_id)
    
    if not library:
        flash("Library not found.", "error")
        return redirect(url_for("keywords"))
    
    if library["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("keywords"))
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        keywords_text = request.form.get("keywords", "").strip()
        is_active = request.form.get("is_active") == "on"
        
        # Parse keywords
        keywords = []
        for line in keywords_text.split("\n"):
            for kw in line.split(","):
                kw = kw.strip()
                if kw:
                    keywords.append(kw)
        
        kw_service.update_library(
            library_id=library_id,
            name=name,
            keywords=keywords,
            is_active=is_active,
        )
        
        flash("Library updated!", "success")
        return redirect(url_for("keywords"))
    
    return render_template("keyword_library_form.html", library=library)


@app.route("/keywords/library/<int:library_id>/delete", methods=["POST"])
@login_required
def delete_keyword_library(library_id):
    """Delete a keyword library."""
    kw_service = get_keyword_tracking()
    library = kw_service.get_library(library_id)
    
    if not library:
        flash("Library not found.", "error")
        return redirect(url_for("keywords"))
    
    if library["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("keywords"))
    
    kw_service.delete_library(library_id)
    flash("Library deleted.", "success")
    return redirect(url_for("keywords"))


@app.route("/api/keywords/trends")
@login_required
def api_keyword_trends():
    """Get keyword frequency trends."""
    kw_service = get_keyword_tracking()
    trends = kw_service.get_keyword_trends(session["user_email"])
    return jsonify(trends)


# ============================================================================
# Playlist Routes
# ============================================================================

@app.route("/playlists")
@login_required
def playlists():
    """View all playlists."""
    playlist_service = get_playlists()
    user_playlists = playlist_service.list_playlists(session["user_email"])
    
    return render_template("playlists.html", playlists=user_playlists)


@app.route("/playlists/new", methods=["GET", "POST"])
@login_required
def create_playlist():
    """Create a new playlist."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "training")
        is_public = request.form.get("is_public") == "on"
        
        if not name:
            flash("Playlist name is required.", "error")
            return render_template("playlist_form.html", playlist=None)
        
        playlist_service = get_playlists()
        playlist = playlist_service.create_playlist(
            user_email=session["user_email"],
            name=name,
            description=description,
            category=category,
            is_public=is_public,
        )
        
        flash("Playlist created!", "success")
        return redirect(url_for("view_playlist", playlist_id=playlist["id"]))
    
    return render_template("playlist_form.html", playlist=None)


@app.route("/playlists/<int:playlist_id>")
@login_required
def view_playlist(playlist_id):
    """View a playlist with its items."""
    playlist_service = get_playlists()
    playlist = playlist_service.get_playlist(playlist_id)
    
    if not playlist:
        flash("Playlist not found.", "error")
        return redirect(url_for("playlists"))
    
    # Check access
    if not playlist["is_public"] and playlist["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("playlists"))
    
    # Get completion stats if user owns the playlist
    completion_stats = None
    if playlist["user_email"] == session["user_email"]:
        completion_stats = playlist_service.get_playlist_completion_stats(playlist_id)
    
    # Get current user's progress
    user_progress = playlist_service.get_rep_progress(playlist_id, session["user_email"])
    
    return render_template(
        "playlist_view.html",
        playlist=playlist,
        completion_stats=completion_stats,
        user_progress=user_progress,
    )


@app.route("/playlists/<int:playlist_id>/edit", methods=["GET", "POST"])
@login_required
def edit_playlist(playlist_id):
    """Edit a playlist."""
    playlist_service = get_playlists()
    playlist = playlist_service.get_playlist(playlist_id)
    
    if not playlist:
        flash("Playlist not found.", "error")
        return redirect(url_for("playlists"))
    
    if playlist["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("playlists"))
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "training")
        is_public = request.form.get("is_public") == "on"
        
        playlist_service.update_playlist(
            playlist_id=playlist_id,
            name=name,
            description=description,
            category=category,
            is_public=is_public,
        )
        
        flash("Playlist updated!", "success")
        return redirect(url_for("view_playlist", playlist_id=playlist_id))
    
    return render_template("playlist_form.html", playlist=playlist)


@app.route("/playlists/<int:playlist_id>/delete", methods=["POST"])
@login_required
def delete_playlist(playlist_id):
    """Delete a playlist."""
    playlist_service = get_playlists()
    playlist = playlist_service.get_playlist(playlist_id)
    
    if not playlist:
        flash("Playlist not found.", "error")
        return redirect(url_for("playlists"))
    
    if playlist["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("playlists"))
    
    playlist_service.delete_playlist(playlist_id)
    flash("Playlist deleted.", "success")
    return redirect(url_for("playlists"))


@app.route("/playlists/<int:playlist_id>/add/<job_id>", methods=["POST"])
@login_required
def add_to_playlist(playlist_id, job_id):
    """Add a call to a playlist."""
    playlist_service = get_playlists()
    playlist = playlist_service.get_playlist(playlist_id)
    
    if not playlist:
        return jsonify({"error": "Playlist not found"}), 404
    
    if playlist["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    notes = request.form.get("notes", "")
    
    playlist_service.add_item(
        playlist_id=playlist_id,
        call_id=job_id,
        notes=notes,
    )
    
    if request.headers.get("Accept") == "application/json":
        return jsonify({"message": "Added to playlist"})
    
    flash("Call added to playlist!", "success")
    return redirect(request.referrer or url_for("view_playlist", playlist_id=playlist_id))


@app.route("/playlists/<int:playlist_id>/remove/<int:item_id>", methods=["POST"])
@login_required
def remove_from_playlist(playlist_id, item_id):
    """Remove an item from a playlist."""
    playlist_service = get_playlists()
    playlist = playlist_service.get_playlist(playlist_id)
    
    if not playlist:
        return jsonify({"error": "Playlist not found"}), 404
    
    if playlist["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    playlist_service.remove_item(item_id)
    
    if request.headers.get("Accept") == "application/json":
        return jsonify({"message": "Removed from playlist"})
    
    flash("Item removed.", "success")
    return redirect(url_for("view_playlist", playlist_id=playlist_id))


@app.route("/playlists/<int:playlist_id>/complete/<int:item_id>", methods=["POST"])
@login_required
def mark_playlist_item_complete(playlist_id, item_id):
    """Mark a playlist item as completed."""
    playlist_service = get_playlists()
    
    notes = request.form.get("notes", "")
    self_score = request.form.get("self_score")
    if self_score:
        try:
            self_score = int(self_score)
        except ValueError:
            self_score = None
    
    playlist_service.mark_item_complete(
        playlist_id=playlist_id,
        item_id=item_id,
        rep_email=session["user_email"],
        notes=notes,
        self_score=self_score,
    )
    
    if request.headers.get("Accept") == "application/json":
        return jsonify({"message": "Marked complete"})
    
    flash("Progress saved!", "success")
    return redirect(url_for("view_playlist", playlist_id=playlist_id))


@app.route("/health")
def health():
    """Health check endpoint."""
    return "OK"


# API Keys and Webhooks management removed - no longer offering developer features


# ============================================================================
# Error handlers
# ============================================================================

@app.errorhandler(413)
def too_large(e):
    flash("File too large. Maximum size is 100MB.", "error")
    return redirect(url_for("upload"))


@app.errorhandler(500)
def server_error(e):
    # SECURITY: Use safe exception logging
    safe_log_exception(logger, "Server error", exc_info=True)
    return render_template("error.html", error="Internal server error"), 500


@app.route("/admin/cleanup", methods=["POST"])
@login_required
def cleanup_old_files():
    """Clean up old files from upload folder (admin only)."""
    # SECURITY: Only allow cleanup by authenticated users
    # In production, you might want to add admin role check
    
    secure_storage = SecureStorageService()
    max_age_hours = int(request.form.get("max_age_hours", 24))
    
    deleted, failed = secure_storage.cleanup_old_files(max_age_hours=max_age_hours)
    
    flash(f"Cleanup complete: {deleted} files deleted, {failed} failed", "success")
    return redirect(url_for("dashboard"))


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    # Load whitelist on startup
    Config.load_whitelist()
    logger.info(f"Loaded {len(Config.ALLOWED_EMAILS)} whitelisted emails")
    
    # Validate required configuration
    missing = Config.validate_required_config()
    if missing:
        logger.warning(f"⚠️  Missing configuration: {', '.join(missing)}")
        logger.warning("The app may not function correctly without these settings.")
    
    # Run in debug mode for development (DISABLE in production!)
    app.run(debug=True, host="0.0.0.0", port=5000)

