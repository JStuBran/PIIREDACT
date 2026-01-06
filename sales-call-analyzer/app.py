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
)
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from werkzeug.utils import secure_filename
from collections import defaultdict
import time

from config import Config

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
    TranscriberService,
    AnalyzerService,
    PDFGeneratorService,
    EmailSenderService,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Token serializer for magic links
serializer = URLSafeTimedSerializer(Config.SECRET_KEY)

# In-memory job storage (use Redis/DB in production)
jobs = {}

# Initialize services (lazy loading)
_transcriber: Optional[TranscriberService] = None
_analyzer: Optional[AnalyzerService] = None
_pdf_generator: Optional[PDFGeneratorService] = None
_email_sender: Optional[EmailSenderService] = None


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
    """Redirect to upload if logged in, otherwise login."""
    if "user_email" in session:
        return redirect(url_for("upload"))
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
    """Upload page - drag and drop audio file."""
    if request.method == "POST":
        # Check if file was uploaded
        if "audio" not in request.files:
            flash("No audio file provided.", "error")
            return render_template("upload.html")
        
        file = request.files["audio"]
        
        if file.filename == "":
            flash("No file selected.", "error")
            return render_template("upload.html")
        
        if not allowed_file(file.filename):
            flash(f"Invalid file type. Allowed: {', '.join(Config.ALLOWED_EXTENSIONS)}", "error")
            return render_template("upload.html")
        
        # Save file
        job_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        file_path = os.path.join(Config.UPLOAD_FOLDER, f"{job_id}_{filename}")
        file.save(file_path)
        
        # Create job
        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "filename": filename,
            "file_path": file_path,
            "user_email": session["user_email"],
            "created_at": datetime.utcnow().isoformat(),
            "error": None,
            "result": None,
        }
        
        # Redirect to processing page
        return redirect(url_for("process", job_id=job_id))
    
    return render_template("upload.html", user_email=session.get("user_email"))


@app.route("/process/<job_id>")
@login_required
def process(job_id):
    """Processing page - shows progress and triggers analysis."""
    job = jobs.get(job_id)
    
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
    job = jobs.get(job_id)
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    if job["user_email"] != session["user_email"]:
        return jsonify({"error": "Access denied"}), 403
    
    if job["status"] != "pending":
        return jsonify({"error": "Job already processing or complete"}), 400
    
    # Update status
    job["status"] = "transcribing"
    
    try:
        # Step 1: Transcribe and redact
        logger.info(f"[{job_id}] Starting transcription...")
        job["status"] = "transcribing"
        
        transcriber = get_transcriber()
        transcription = transcriber.transcribe_and_redact(job["file_path"])
        
        job["transcription"] = transcription
        
        # Step 2: Analyze with GPT-4o
        logger.info(f"[{job_id}] Analyzing with GPT-4o...")
        job["status"] = "analyzing"
        
        analyzer = get_analyzer()
        analysis = analyzer.analyze(
            transcript=transcription["redacted_text"],
            duration_min=transcription.get("duration_min", 0),
        )
        
        job["analysis"] = analysis
        
        # Step 3: Compute call stats
        logger.info(f"[{job_id}] Computing call stats...")
        stats = analyzer.compute_stats(transcription.get("segments", []))
        job["stats"] = stats
        
        # Step 4: Generate PDFs
        logger.info(f"[{job_id}] Generating PDFs...")
        job["status"] = "generating_pdf"
        
        pdf_generator = get_pdf_generator()
        
        coaching_pdf_path = os.path.join(
            Config.UPLOAD_FOLDER,
            f"{job_id}_coaching.pdf"
        )
        stats_pdf_path = os.path.join(
            Config.UPLOAD_FOLDER,
            f"{job_id}_stats.pdf"
        )
        
        pdf_generator.generate_coaching_report(analysis, coaching_pdf_path)
        pdf_generator.generate_stats_report(stats, stats_pdf_path)
        
        job["coaching_pdf"] = coaching_pdf_path
        job["stats_pdf"] = stats_pdf_path
        
        # Step 5: Send email
        logger.info(f"[{job_id}] Sending email...")
        job["status"] = "sending_email"
        
        email_sender = get_email_sender()
        email_sender.send_report(
            to_email=job["user_email"],
            subject=f"Call Analysis: {job['filename']}",
            coaching_pdf_path=coaching_pdf_path,
            stats_pdf_path=stats_pdf_path,
        )
        
        # Done!
        job["status"] = "complete"
        job["completed_at"] = datetime.utcnow().isoformat()
        
        # Clean up audio file
        try:
            os.unlink(job["file_path"])
        except Exception:
            pass
        
        logger.info(f"[{job_id}] Analysis complete!")
        
        return jsonify({
            "status": "complete",
            "message": "Analysis complete! Check your email.",
        })
        
    except Exception as e:
        logger.exception(f"[{job_id}] Analysis failed: {e}")
        job["status"] = "error"
        job["error"] = str(e)
        
        return jsonify({
            "status": "error",
            "error": str(e),
        }), 500


@app.route("/api/status/<job_id>")
@login_required
def api_status(job_id):
    """API endpoint to check job status."""
    job = jobs.get(job_id)
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
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
    job = jobs.get(job_id)
    
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("upload"))
    
    if job["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("upload"))
    
    if job["status"] != "complete":
        return redirect(url_for("process", job_id=job_id))
    
    return render_template(
        "report.html",
        job=job,
        analysis=job.get("analysis", {}),
        stats=job.get("stats", {}),
    )


@app.route("/download/<job_id>/<report_type>")
@login_required
def download(job_id, report_type):
    """Download PDF report."""
    job = jobs.get(job_id)
    
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("upload"))
    
    if job["user_email"] != session["user_email"]:
        flash("Access denied.", "error")
        return redirect(url_for("upload"))
    
    if report_type == "coaching":
        pdf_path = job.get("coaching_pdf")
        filename = f"coaching_report_{job['filename']}.pdf"
    elif report_type == "stats":
        pdf_path = job.get("stats_pdf")
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


@app.route("/health")
def health():
    """Health check endpoint."""
    return "OK"


# ============================================================================
# Error handlers
# ============================================================================

@app.errorhandler(413)
def too_large(e):
    flash("File too large. Maximum size is 100MB.", "error")
    return redirect(url_for("upload"))


@app.errorhandler(500)
def server_error(e):
    logger.exception("Server error")
    return render_template("error.html", error="Internal server error"), 500


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

