
import csv
import json
import logging
import os
import sys

# Quiet Paddle / oneDNN before those libraries load.
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("GLOG_v", "0")
os.environ.setdefault("FLAGS_minloglevel", "3")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("KMP_WARNINGS", "0")
os.environ.setdefault("OMP_DISPLAY_ENV", "FALSE")
os.environ.setdefault("WERKZEUG_DEBUG_PIN", "off")


class _QuietConsole:
    """Drop Windows/Paddle CLI noise such as: INFO: Could not find files for the given pattern(s)."""

    _DROP = (
        "Could not find files for the given pattern(s).",
        "No ccache found",
        "Debugger PIN",
        "Debugger is active",
        "WARNING: This is a development server",
        "Running on all addresses",
        "Running on http://",
        "Press CTRL+C to quit",
        "* Serving Flask app",
    )

    def __init__(self, wrapped):
        self._wrapped = wrapped

    def write(self, text):
        if not text:
            return 0
        if any(marker in text for marker in self._DROP):
            return len(text)
        return self._wrapped.write(text)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush(self):
        return self._wrapped.flush()

    def isatty(self):
        return bool(getattr(self._wrapped, "isatty", lambda: False)())

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


if not isinstance(sys.stdout, _QuietConsole):
    sys.stdout = _QuietConsole(sys.stdout)
if not isinstance(sys.stderr, _QuietConsole):
    sys.stderr = _QuietConsole(sys.stderr)

import random
import re
import shutil
import threading
import traceback
import uuid
import zipfile
from datetime import datetime, date, timedelta, time
from functools import wraps
from io import BytesIO, StringIO
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, send_file, jsonify
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash

from models import db, User, Record, EditRequest, AuditLog, PrintLog, PrintRequest
from services.auto_backup import (
    apply_schedule,
    delete_auto_backup,
    init_auto_backup_scheduler,
    list_auto_backups,
    load_settings as load_auto_backup_settings,
    resolve_auto_backup_path,
    run_auto_backup,
    save_settings as save_auto_backup_settings,
    settings_from_form,
    write_full_backup_zip,
)
from ocr.birth import extract_birth_data
from ocr.marriage import extract_marriage_data
from ocr.death import extract_death_data
from services.certification_print import (
    cert_field,
    cert_issue_date,
    form_meta,
    normalize_print_format,
    print_format_label,
    print_format_short_label,
    PRINT_FORMAT_CERTIFICATION,
    PRINT_FORMAT_ORIGINAL,
    PRINT_FORMAT_BOTH,
)
from services.document_annotation import (
    FORM_KEYS as ANNOTATION_FORM_KEYS,
    KINDS as ANNOTATION_KINDS,
    apply_to_data as apply_annotation_to_data,
    form_defaults as annotation_form_defaults,
    from_data as document_annotation_from_data,
    from_form as annotation_from_form,
    public_fields as public_record_fields,
)
from services.civil_registry_reports import (
    BIRTH_EXCEL_HEADERS,
    DEATH_EXCEL_HEADERS,
    MARRIAGE_EXCEL_HEADERS,
    birth_excel_row,
    birth_row,
    build_xlsx,
    collect_filter_options,
    death_excel_row,
    death_row,
    load_record_fields,
    marriage_excel_rows,
    marriage_row,
    record_is_reportable,
    row_matches_filters,
)
try:
    from services.scanner_wia import list_scanners, scan_to_file
except ImportError:
    list_scanners = lambda: []
    def scan_to_file(*args, **kwargs):
        return False, "Scanner support not available (install pywin32 on Windows)."


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "temp").mkdir(exist_ok=True)
for sub in ("birth", "marriage", "death"):
    (UPLOAD_DIR / sub).mkdir(exist_ok=True)


def _normalize_upload_relpath(rel: str) -> str:
    """Keep paths relative to uploads/ (birth/foo.jpg), never uploads/uploads/..."""
    raw = (rel or "").replace("\\", "/").strip()
    if not raw:
        return ""
    while raw.startswith("./"):
        raw = raw[2:]
    parts = [p for p in raw.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        return ""
    while parts and parts[0].lower() == "uploads":
        parts = parts[1:]
    return "/".join(parts)


def _upload_file_path(rel: str) -> Path | None:
    """Resolve a stored image path under UPLOAD_DIR, or None if unsafe/empty."""
    norm = _normalize_upload_relpath(rel)
    if not norm:
        return None
    upload_root = UPLOAD_DIR.resolve()
    full = (UPLOAD_DIR / norm).resolve()
    try:
        full.relative_to(upload_root)
    except ValueError:
        return None
    return full


def _flatten_nested_uploads() -> None:
    """Move files out of uploads/uploads/ into uploads/ and remove the duplicate folder."""
    nested = UPLOAD_DIR / "uploads"
    if not nested.is_dir():
        return
    for src in nested.rglob("*"):
        if not src.is_file():
            continue
        dest = UPLOAD_DIR / src.relative_to(nested)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            continue
        try:
            shutil.move(str(src), str(dest))
        except OSError:
            pass
    shutil.rmtree(nested, ignore_errors=True)


_flatten_nested_uploads()


def _default_sqlite_uri() -> str:
    """Local file DB — best default for a single Windows PC; zero extra setup."""
    db_file = (BASE_DIR / "civil_registry.db").resolve().as_posix()
    return f"sqlite:///{db_file}"


def resolve_database_uri() -> str:
    """DATABASE_URL for PostgreSQL, or default SQLite file. Heroku postgres:// is normalized."""
    uri = (os.environ.get("DATABASE_URL") or "").strip()
    if not uri:
        return _default_sqlite_uri()
    if uri.startswith("postgres://"):
        uri = "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def is_sqlite_database(uri: str | None = None) -> bool:
    u = resolve_database_uri() if uri is None else (uri or "")
    return u.strip().lower().startswith("sqlite")


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = resolve_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
if is_sqlite_database():
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"check_same_thread": False}}
else:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db.init_app(app)


DOCUMENT_TYPES = {
    "birth": "Birth Certificate",
    "marriage": "Marriage Certificate",
    "death": "Death Certificate",
}

# JSON keys used for mother's name across document types (stored in Record.data_json).
MOTHER_NAME_JSON_KEYS = (
    "Name of Mother",   # birth
    "Husband Mother",   # marriage
    "Wife Mother",      # marriage
)


def _parse_doc_type_filter_arg(value):
    """Return birth|marriage|death if valid, else None (show all)."""
    if not value:
        return None
    v = (value or "").strip().lower()
    return v if v in DOCUMENT_TYPES else None


def _admin_edit_requests_redirect():
    """Redirect back to edit requests tab, preserving optional doc_type filter."""
    dt = _parse_doc_type_filter_arg(request.form.get("doc_type") or request.args.get("doc_type"))
    if dt:
        return redirect(url_for("administration", tab="edit_requests", doc_type=dt))
    return redirect(url_for("administration", tab="edit_requests"))


def _admin_print_requests_redirect():
    """Redirect back to print requests tab, preserving optional doc_type filter."""
    dt = _parse_doc_type_filter_arg(request.form.get("doc_type") or request.args.get("doc_type"))
    if dt:
        return redirect(url_for("administration", tab="print_requests", doc_type=dt))
    return redirect(url_for("administration", tab="print_requests"))


def _is_admin_user(user) -> bool:
    return bool(user and (user.role or "").upper() == "ADMIN")


def _staff_active_print_approval(user_id: int, record_id: int):
    """Return an approved, unused print request for this staff member and record."""
    return (
        PrintRequest.query.filter_by(
            record_id=record_id,
            requested_by_id=user_id,
            status="APPROVED",
        )
        .filter(PrintRequest.used_at.is_(None))
        .order_by(PrintRequest.reviewed_at.desc())
        .first()
    )


def user_can_print_record(user, record_id: int) -> bool:
    if not user:
        return False
    if _is_admin_user(user):
        return True
    if (user.role or "").upper() != "STAFF":
        return False
    return _staff_active_print_approval(user.id, record_id) is not None


def user_can_print_during_review(user) -> bool:
    """OCR review forms (before save): admins only."""
    return _is_admin_user(user)


# Available in every Jinja template (context processors alone can fail to apply in some run setups).
app.jinja_env.globals["document_types"] = DOCUMENT_TYPES
app.jinja_env.globals["cert_field"] = cert_field
app.jinja_env.globals["get_form_meta"] = form_meta
app.jinja_env.globals["normalize_print_format"] = normalize_print_format
app.jinja_env.globals["print_format_label"] = print_format_label
app.jinja_env.globals["print_format_short_label"] = print_format_short_label
app.jinja_env.globals["PRINT_FORMAT_ORIGINAL"] = PRINT_FORMAT_ORIGINAL
app.jinja_env.globals["PRINT_FORMAT_CERTIFICATION"] = PRINT_FORMAT_CERTIFICATION
app.jinja_env.globals["PRINT_FORMAT_BOTH"] = PRINT_FORMAT_BOTH
app.jinja_env.globals["document_annotation"] = document_annotation_from_data
app.jinja_env.globals["public_record_fields"] = public_record_fields
app.jinja_env.globals["annotation_form_defaults"] = annotation_form_defaults
app.jinja_env.globals["annotation_kinds"] = ANNOTATION_KINDS


@app.context_processor
def inject_template_globals():
    """Expose helpers in every template (backup if jinja_env.globals are not applied)."""
    return {
        "cert_date": cert_issue_date(),
        "cert_field": cert_field,
        "get_form_meta": form_meta,
        "normalize_print_format": normalize_print_format,
        "print_format_label": print_format_label,
        "print_format_short_label": print_format_short_label,
        "PRINT_FORMAT_ORIGINAL": PRINT_FORMAT_ORIGINAL,
        "PRINT_FORMAT_CERTIFICATION": PRINT_FORMAT_CERTIFICATION,
        "PRINT_FORMAT_BOTH": PRINT_FORMAT_BOTH,
        "document_types": DOCUMENT_TYPES,
        "document_annotation": document_annotation_from_data,
        "public_record_fields": public_record_fields,
        "annotation_form_defaults": annotation_form_defaults,
        "annotation_kinds": ANNOTATION_KINDS,
    }


@app.template_global("print_format_short_label")
def _jinja_print_format_short_label(print_format, document_type="birth"):
    return print_format_short_label(print_format, document_type)

_OCR_JOBS = {}
_OCR_JOBS_LOCK = threading.Lock()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.")
            return redirect(url_for("login"))
        user = db.session.get(User, session["user_id"])
        if not user:
            session.clear()
            flash("Please log in to continue.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


def get_current_user():
    if not session.get("user_id"):
        return None
    return db.session.get(User, session["user_id"])


def _parse_ocr_input_from_request():
    doc_type = (request.form.get("document_type") or "").strip().lower()
    if doc_type not in DOCUMENT_TYPES:
        return None, None, None, "Please select a valid document type."

    file = request.files.get("image")
    image_filename_form = (request.form.get("image_filename") or "").strip()
    save_path = None
    image_filename = ""

    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in {".jpg", ".jpeg", ".png"}:
            return None, None, None, "Only JPG and PNG images are supported."
        subdir = UPLOAD_DIR / doc_type
        subdir.mkdir(exist_ok=True)
        original_name = Path(file.filename).name
        stem = _sanitize_filename_part(Path(original_name).stem, 36)
        ext = os.path.splitext(original_name)[1].lower() or ".jpg"
        save_path = subdir / f"{doc_type}_{uuid.uuid4().hex[:10]}_{stem}{ext}"
        file.save(save_path)
        image_filename = f"{doc_type}/{save_path.name}"
    elif image_filename_form:
        safe_path = Path(image_filename_form)
        if safe_path.is_absolute() or ".." in image_filename_form:
            return None, None, None, "Invalid image path."
        image_filename = _normalize_upload_relpath(image_filename_form)
        save_path = _upload_file_path(image_filename)
        if save_path is None or not save_path.exists():
            return None, None, None, "Scanned image no longer found. Please scan again."
    else:
        return None, None, None, "Please scan from printer or choose an image file first."

    return doc_type, save_path, image_filename, None


def _set_ocr_job(job_id: str, **fields):
    with _OCR_JOBS_LOCK:
        job = _OCR_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)


def _prune_ocr_jobs(max_age_hours: int = 2, max_jobs: int = 40):
    """Drop finished OCR sessions so memory does not grow during a workday."""
    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    with _OCR_JOBS_LOCK:
        stale = []
        for job_id, job in _OCR_JOBS.items():
            created = job.get("created_at") or ""
            try:
                created_dt = datetime.fromisoformat(created)
            except (TypeError, ValueError):
                created_dt = cutoff
            if created_dt < cutoff:
                stale.append(job_id)
        for job_id in stale:
            _OCR_JOBS.pop(job_id, None)
        if len(_OCR_JOBS) > max_jobs:
            ordered = sorted(
                _OCR_JOBS.items(),
                key=lambda item: item[1].get("created_at") or "",
            )
            for job_id, _job in ordered[: len(_OCR_JOBS) - max_jobs]:
                _OCR_JOBS.pop(job_id, None)


def _run_ocr_job(job_id: str, doc_type: str, save_path: Path, image_filename: str):
    try:
        _set_ocr_job(job_id, status="running", progress=20, message="OCR started...")
        if doc_type == "birth":
            _set_ocr_job(job_id, progress=45, message="Extracting birth fields...")
            data = extract_birth_data(str(save_path))
        elif doc_type == "marriage":
            _set_ocr_job(job_id, progress=45, message="Extracting marriage fields...")
            data = extract_marriage_data(str(save_path))
        else:
            _set_ocr_job(job_id, progress=45, message="Extracting death fields...")
            data = extract_death_data(str(save_path))
        _set_ocr_job(
            job_id,
            status="done",
            progress=100,
            message="OCR complete.",
            doc_type=doc_type,
            image_filename=image_filename,
            data=data,
        )
    except Exception:
        err = traceback.format_exc()
        print(err, flush=True)
        _set_ocr_job(
            job_id,
            status="error",
            progress=100,
            message="OCR failed.",
            error=err,
        )


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.")
            return redirect(url_for("login"))
        user = get_current_user()
        if not user or (user.role or "").upper() != "ADMIN":
            flash("Administration access is for admins only.")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return wrapper


def _log_audit(user_id, action: str, details: str = ""):
    try:
        log = AuditLog(user_id=user_id, action=action, details=details)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            flash("Please enter username and password.")
            return redirect(url_for("login"))

        user = User.query.filter_by(username=username).first()
        if not user:
            flash("Invalid username or password.")
            return redirect(url_for("login"))
        try:
            if not check_password_hash(user.password_hash or "", password):
                flash("Invalid username or password.")
                return redirect(url_for("login"))
        except ValueError:
            flash("Invalid username or password.")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        doc_type, save_path, image_filename, err = _parse_ocr_input_from_request()
        if err:
            flash(err)
            return redirect(url_for("index"))
        try:
            if doc_type == "birth":
                data = extract_birth_data(str(save_path))
            elif doc_type == "marriage":
                data = extract_marriage_data(str(save_path))
            else:
                data = extract_death_data(str(save_path))
        except Exception:
            traceback.print_exc()
            flash("OCR failed while reading this document. Try a clearer scan or another image.")
            return redirect(url_for("index"))
        return render_template(
            f"form_{doc_type}.html",
            doc_type=doc_type,
            doc_label=DOCUMENT_TYPES[doc_type],
            data=data,
            image_filename=image_filename,
            current_user=get_current_user(),
            nav_active="form",
            can_print=user_can_print_during_review(get_current_user()),
        )
    return render_template(
        "index.html",
        document_types=DOCUMENT_TYPES,
        current_user=get_current_user(),
        nav_active="scan",
    )


@app.route("/api/scanners", methods=["GET"])
@login_required
def api_scanners():
    """Return list of physical scanners detected (Windows WIA)."""
    scanners = list_scanners()
    return {"scanners": scanners}


@app.route("/api/scan", methods=["POST"])
@login_required
def api_scan():
    """Perform a scan from the selected physical scanner and return the image path."""
    device_index = request.form.get("device_index", type=int) or 1
    temp_dir = UPLOAD_DIR / "temp"
    ok, path_or_error = scan_to_file(device_index=device_index, output_dir=temp_dir, save_as_png=True)
    if not ok:
        return {"ok": False, "error": path_or_error}, 400
    # path_or_error is absolute; we need a path relative to UPLOAD_DIR for image_filename
    rel = os.path.relpath(path_or_error, UPLOAD_DIR)
    if rel.startswith("..") or os.path.isabs(rel):
        return {"ok": False, "error": "Invalid scan path"}, 500
    rel = _normalize_upload_relpath(rel.replace("\\", "/"))
    image_url = url_for("serve_upload", path=rel)
    return {"ok": True, "image_url": image_url, "image_filename": rel}


@app.route("/api/ocr/start", methods=["POST"])
@login_required
def api_ocr_start():
    doc_type, save_path, image_filename, err = _parse_ocr_input_from_request()
    if err:
        return {"ok": False, "error": err}, 400

    job_id = uuid.uuid4().hex
    _prune_ocr_jobs()
    with _OCR_JOBS_LOCK:
        _OCR_JOBS[job_id] = {
            "status": "queued",
            "progress": 1,
            "message": "Queued OCR job...",
            "doc_type": doc_type,
            "image_filename": image_filename,
            "data": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat(),
        }

    t = threading.Thread(
        target=_run_ocr_job,
        args=(job_id, doc_type, save_path, image_filename),
        daemon=True,
    )
    t.start()
    return {"ok": True, "job_id": job_id}


@app.route("/api/ocr/status/<job_id>", methods=["GET"])
@login_required
def api_ocr_status(job_id):
    with _OCR_JOBS_LOCK:
        job = _OCR_JOBS.get(job_id)
        if not job:
            return {"ok": False, "error": "OCR job not found."}, 404
        payload = {
            "ok": True,
            "status": job.get("status"),
            "progress": job.get("progress", 1),
            "message": job.get("message", ""),
        }
        if job.get("status") == "done":
            payload["redirect_url"] = url_for("ocr_result", job_id=job_id)
        if job.get("status") == "error":
            payload["error"] = "OCR failed while processing the document."
        return payload


def _record_notice_label(record) -> str:
    if not record:
        return "a record"
    kind = (record.document_type or "record").capitalize()
    reg = (record.registry_number or "").strip()
    if reg:
        return f"{kind} · {reg}"
    return f"{kind} record #{record.id}"


def _notice_iso(dt) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _collect_notifications(user) -> dict:
    role = (user.role or "").upper()
    items = []
    badges = {}

    if role == "ADMIN":
        pending_edits = (
            EditRequest.query.filter_by(status="PENDING")
            .order_by(EditRequest.requested_at.desc())
            .limit(12)
            .all()
        )
        pending_prints = (
            PrintRequest.query.filter_by(status="PENDING")
            .order_by(PrintRequest.requested_at.desc())
            .limit(12)
            .all()
        )
        for req in pending_edits:
            who = req.requested_by.username if req.requested_by else "Staff"
            items.append({
                "id": f"edit-{req.id}",
                "kind": "edit",
                "title": "New edit request",
                "body": f"{who} asked to edit {_record_notice_label(req.record)}",
                "url": url_for("administration", tab="edit_requests"),
                "at": _notice_iso(req.requested_at),
            })
        for req in pending_prints:
            who = req.requested_by.username if req.requested_by else "Staff"
            items.append({
                "id": f"print-{req.id}",
                "kind": "print",
                "title": "New print request",
                "body": f"{who} asked to print {_record_notice_label(req.record)}",
                "url": url_for("administration", tab="print_requests"),
                "at": _notice_iso(req.requested_at),
            })
        badges = {
            "admin_pending_edit_requests": EditRequest.query.filter_by(status="PENDING").count(),
            "admin_pending_print_requests": PrintRequest.query.filter_by(status="PENDING").count(),
        }
        badges["total"] = badges["admin_pending_edit_requests"] + badges["admin_pending_print_requests"]

    elif role == "STAFF":
        pending_edits = (
            EditRequest.query.filter_by(requested_by_id=user.id, status="PENDING")
            .order_by(EditRequest.requested_at.desc())
            .limit(8)
            .all()
        )
        ready_edits = (
            EditRequest.query.filter_by(requested_by_id=user.id, status="APPROVED")
            .filter(EditRequest.code_used_at.is_(None))
            .order_by(EditRequest.reviewed_at.desc())
            .limit(8)
            .all()
        )
        pending_prints = (
            PrintRequest.query.filter_by(requested_by_id=user.id, status="PENDING")
            .order_by(PrintRequest.requested_at.desc())
            .limit(8)
            .all()
        )
        ready_prints = (
            PrintRequest.query.filter_by(requested_by_id=user.id, status="APPROVED")
            .filter(PrintRequest.used_at.is_(None))
            .order_by(PrintRequest.reviewed_at.desc())
            .limit(8)
            .all()
        )
        for req in ready_edits:
            items.append({
                "id": f"edit-ready-{req.id}",
                "kind": "edit-ready",
                "title": "Edit approved",
                "body": f"Use your 5-digit code on {_record_notice_label(req.record)}",
                "url": url_for("record_detail", record_id=req.record_id),
                "at": _notice_iso(req.reviewed_at or req.requested_at),
            })
        for req in ready_prints:
            items.append({
                "id": f"print-ready-{req.id}",
                "kind": "print-ready",
                "title": "Print approved",
                "body": f"Ready to print {_record_notice_label(req.record)}",
                "url": url_for("record_detail", record_id=req.record_id),
                "at": _notice_iso(req.reviewed_at or req.requested_at),
            })
        for req in pending_edits:
            items.append({
                "id": f"edit-wait-{req.id}",
                "kind": "edit",
                "title": "Edit request pending",
                "body": f"Waiting for admin on {_record_notice_label(req.record)}",
                "url": url_for("my_edit_requests"),
                "at": _notice_iso(req.requested_at),
            })
        for req in pending_prints:
            items.append({
                "id": f"print-wait-{req.id}",
                "kind": "print",
                "title": "Print request pending",
                "body": f"Waiting for admin on {_record_notice_label(req.record)}",
                "url": url_for("my_print_requests"),
                "at": _notice_iso(req.requested_at),
            })
        badges = {
            "staff_my_requests_pending": EditRequest.query.filter_by(requested_by_id=user.id, status="PENDING").count(),
            "staff_my_requests_approved_ready": (
                EditRequest.query.filter_by(requested_by_id=user.id, status="APPROVED")
                .filter(EditRequest.code_used_at.is_(None))
                .count()
            ),
            "staff_print_pending": PrintRequest.query.filter_by(requested_by_id=user.id, status="PENDING").count(),
            "staff_print_requests_approved_ready": (
                PrintRequest.query.filter_by(requested_by_id=user.id, status="APPROVED")
                .filter(PrintRequest.used_at.is_(None))
                .count()
            ),
        }
        badges["total"] = (
            badges["staff_my_requests_approved_ready"]
            + badges["staff_print_requests_approved_ready"]
            + badges["staff_my_requests_pending"]
            + badges["staff_print_pending"]
        )

    items.sort(key=lambda row: row.get("at") or "", reverse=True)
    return {"items": items[:20], "badges": badges, "count": int(badges.get("total") or 0)}


@app.route("/api/notifications", methods=["GET"])
@login_required
def api_notifications():
    """Polled by the header bell (offline-safe, no websockets)."""
    user = get_current_user()
    if not user:
        return {"ok": False}, 401
    role = (user.role or "").upper()
    data = _collect_notifications(user)
    return {
        "ok": True,
        "role": role,
        "count": data["count"],
        "items": data["items"],
        "badges": data["badges"],
    }


@app.route("/workflow/autofilled-form")
@login_required
def autofilled_form_latest():
    """Sidebar link: reopen the latest completed OCR form for this session."""
    job_id = session.get("last_ocr_job_id")
    if not job_id:
        flash("Run OCR from Scan Workflow first to open the auto-filled form.")
        return redirect(url_for("index"))
    with _OCR_JOBS_LOCK:
        job = _OCR_JOBS.get(job_id)
    if not job or job.get("status") != "done":
        flash("Your last OCR session is no longer available. Run OCR again from Scan Workflow.")
        return redirect(url_for("index"))
    return redirect(url_for("ocr_result", job_id=job_id))


@app.route("/workflow/autofilled-form/cancel", methods=["POST"])
@login_required
def autofilled_form_cancel():
    """
    Cancel the current auto-filled review session without saving.
    Clears the session pointer so Auto-Filled Form no longer reopens stale data.
    """
    job_id = session.get("last_ocr_job_id")
    if job_id:
        with _OCR_JOBS_LOCK:
            _OCR_JOBS.pop(job_id, None)
    session.pop("last_ocr_job_id", None)
    session.modified = True
    flash("Auto-filled form review cancelled.")
    return redirect(url_for("index"))


@app.route("/ocr/result/<job_id>", methods=["GET"])
@login_required
def ocr_result(job_id):
    with _OCR_JOBS_LOCK:
        job = _OCR_JOBS.get(job_id)
        if not job:
            flash("OCR session not found. Please run OCR again.")
            return redirect(url_for("index"))
        if job.get("status") == "error":
            flash("OCR failed. Please try another image.")
            return redirect(url_for("index"))
        if job.get("status") != "done":
            flash("OCR is still processing. Please wait.")
            return redirect(url_for("index"))
        doc_type = job.get("doc_type")
        image_filename = job.get("image_filename")
        data = job.get("data") or {}

    if doc_type not in DOCUMENT_TYPES:
        flash("OCR session is invalid. Please run OCR again.")
        return redirect(url_for("index"))
    session["last_ocr_job_id"] = job_id
    session.modified = True

    return render_template(
        f"form_{doc_type}.html",
        doc_type=doc_type,
        doc_label=DOCUMENT_TYPES[doc_type],
        data=data,
        image_filename=image_filename,
        current_user=get_current_user(),
        nav_active="form",
        can_print=user_can_print_during_review(get_current_user()),
    )


def _full_name_from_data(doc_type: str, data: dict) -> str:
    if doc_type == "birth":
        return (data.get("Name of Child") or "").strip()
    if doc_type == "marriage":
        h = (data.get("Husband Name") or "").strip()
        w = (data.get("Wife Name") or "").strip()
        return " / ".join(x for x in (h, w) if x)
    if doc_type == "death":
        return (data.get("Name of Deceased") or "").strip()
    return ""


def _event_date_from_data(doc_type: str, data: dict) -> str:
    if doc_type == "birth":
        return (data.get("Date of Birth") or "").strip()
    if doc_type == "marriage":
        return (data.get("Date of Marriage") or "").strip()
    if doc_type == "death":
        return (data.get("Date of Death") or "").strip()
    return ""


def _is_registry_metadata_key(key: str) -> bool:
    """True if this form/JSON key is a registry-number field (OCR uses varying labels)."""
    nk = re.sub(r"[^a-zA-Z0-9]", "", (key or "")).upper()
    if nk in ("REGISTRYNUMBER", "REGISTRYNO"):
        return True
    # "Date of Registration" → DATEOFREGISTRATION contains REGISTRY as substring — exclude
    if "REGISTRATION" in nk:
        return False
    return "REGISTRY" in nk and "NUMBER" in nk


def _submitted_from_request_form():
    """Build flat dict from POST; last value wins per field (fixes duplicate keys / MultiDict quirks)."""
    skip = {"csrf_token", "submit", "clear_annotation"} | set(ANNOTATION_FORM_KEYS)
    submitted = {}
    for key in request.form:
        if key in skip:
            continue
        values = request.form.getlist(key)
        if not values:
            submitted[key] = ""
        else:
            last = values[-1]
            submitted[key] = (last or "").strip() if isinstance(last, str) else last
    return submitted


def _registry_number_from_submitted(submitted: dict) -> str:
    """Read registry number from canonical or any OCR key variant."""
    if not submitted:
        return ""
    v = submitted.get("Registry Number")
    if v is not None:
        v = v.strip() if isinstance(v, str) else str(v).strip()
    else:
        v = ""
    if v:
        return v
    best = ""
    for k, val in submitted.items():
        if _is_registry_metadata_key(k):
            if val is None:
                s = ""
            else:
                s = val.strip() if isinstance(val, str) else str(val).strip()
            if len(s) > len(best):
                best = s
    return best


def _normalize_submitted_registry_keys(submitted: dict) -> dict:
    """Keep a single 'Registry Number' key so saves update the indexed column correctly."""
    if not submitted:
        return submitted
    reg = _registry_number_from_submitted(submitted)
    out = {k: v for k, v in submitted.items() if not _is_registry_metadata_key(k)}
    out["Registry Number"] = reg
    return out


def _sync_json_data_from_record_columns(record: Record, data: dict | None) -> dict:
    """
    Merge indexed columns into the JSON field dict so UI matches Archiving / Search tables.
    Staff edits update columns; OCR may leave stale values in data_json — this aligns them.
    """
    out = dict(data) if data else {}
    reg = (record.registry_number or "").strip()
    if reg:
        for k in list(out.keys()):
            if _is_registry_metadata_key(k):
                del out[k]
        out["Registry Number"] = reg
    fn = (record.full_name or "").strip()
    ed = (record.event_date or "").strip()
    dt = record.document_type
    if dt == "birth":
        if fn:
            out["Name of Child"] = fn
        if ed:
            out["Date of Birth"] = ed
    elif dt == "death":
        if fn:
            out["Name of Deceased"] = fn
        if ed:
            out["Date of Death"] = ed
    elif dt == "marriage":
        if fn:
            if " / " in fn:
                parts = [p.strip() for p in fn.split("/", 1)]
                if len(parts) >= 2:
                    out["Husband Name"] = parts[0]
                    out["Wife Name"] = parts[1]
                else:
                    out["Husband Name"] = fn
            else:
                out["Husband Name"] = fn
        if ed:
            out["Date of Marriage"] = ed
    return out


def _repair_record_json_from_columns(record: Record) -> bool:
    """
    If stored JSON drifts from registry_number / full_name / event_date, rewrite data_json to match.
    Returns True if the database row was updated.
    """
    try:
        raw = json.loads(record.data_json) if record.data_json else {}
    except Exception:
        raw = {}
    synced = _sync_json_data_from_record_columns(record, raw)
    if json.dumps(synced, sort_keys=True, ensure_ascii=False) == json.dumps(
        raw, sort_keys=True, ensure_ascii=False
    ):
        return False
    try:
        s = json.dumps(synced, ensure_ascii=False)
        record.data_json = s
        record.extracted_json = s
        record.corrected_json = s
        record.updated_at = datetime.utcnow()
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def _load_record_data_json(record: Record) -> dict:
    """Parse data_json and align with indexed columns (may persist a repair)."""
    try:
        data = json.loads(record.data_json) if record.data_json else {}
    except Exception:
        data = {}
    _repair_record_json_from_columns(record)
    try:
        fresh = json.loads(record.data_json) if record.data_json else {}
    except Exception:
        fresh = {}
    # Always merge columns into the dict (registry/name/date) so forms and UI match Archiving
    # even if the stored JSON row was not updated by repair.
    merged = _sync_json_data_from_record_columns(record, fresh)
    # If indexed column was never set but JSON has a registry, persist it once (Archiving uses the column).
    if not (record.registry_number or "").strip():
        rn = (_registry_number_from_submitted(merged) or "").strip()
        if rn:
            record.registry_number = rn
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
    return merged


def _sanitize_filename_part(s: str, max_len: int = 40) -> str:
    """Make a string safe for use in filenames: alphanumeric, hyphen, underscore only."""
    if not s or not isinstance(s, str):
        return "Unknown"
    s = s.strip()
    s = re.sub(r"[^a-zA-Z0-9\-_.\s]", "", s)
    s = re.sub(r"[\s]+", "_", s)
    s = s.strip("_") or "Unknown"
    return s[:max_len] if len(s) > max_len else s


def _parse_last_first(full_name: str):
    """Parse full name into (last_name, first_name). Handles 'LastName, FirstName' or 'FirstName LastName'."""
    full_name = (full_name or "").strip()
    if not full_name:
        return "Unknown", "Unknown"
    if "," in full_name:
        parts = [p.strip() for p in full_name.split(",", 1)]
        if len(parts) >= 2:
            return _sanitize_filename_part(parts[0]), _sanitize_filename_part(parts[1])
        return _sanitize_filename_part(parts[0]), "Unknown"
    words = full_name.split()
    if not words:
        return "Unknown", "Unknown"
    if len(words) == 1:
        return _sanitize_filename_part(words[0]), "Unknown"
    last_name = words[-1]
    first_name = " ".join(words[:-1])
    return _sanitize_filename_part(last_name), _sanitize_filename_part(first_name)


def _archive_image_filename(doc_type: str, full_name: str, registry_number: str, current_path: str) -> str:
    """
    Build an archive filename: LastName_FirstName_RegistryNumber_birth|marriage|death.ext
    For marriage, full_name may be 'Husband / Wife'; we use the first person for the filename.
    """
    # For marriage, take first name only (e.g. husband) for the file name
    primary_name = (full_name or "").split("/")[0].strip() if full_name else ""
    last_name, first_name = _parse_last_first(primary_name)
    reg_part = _sanitize_filename_part(registry_number, max_len=30) if registry_number else "NOREG"
    ext = Path(current_path).suffix.lower() if current_path else ".jpg"
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".jpg"
    return f"{last_name}_{first_name}_{reg_part}_{doc_type}{ext}"


def _find_duplicate_record(
    doc_type: str,
    registry_number: str,
    full_name: str,
    event_date: str,
    exclude_record_id: int = None,
):
    """
    Find an existing duplicate record for the same document type.
    Priority:
    1) Same registry number (most reliable key)
    2) If no registry number, same full name + event date
    """
    q = Record.query.filter(Record.document_type == doc_type)
    if exclude_record_id:
        q = q.filter(Record.id != exclude_record_id)

    reg = (registry_number or "").strip()
    if reg:
        return q.filter(db.func.lower(db.func.trim(Record.registry_number)) == reg.lower()).first()

    name = (full_name or "").strip()
    evt = (event_date or "").strip()
    if name and evt:
        return q.filter(
            db.func.lower(db.func.trim(Record.full_name)) == name.lower(),
            db.func.lower(db.func.trim(Record.event_date)) == evt.lower(),
        ).first()
    return None


def _apply_mother_name_filter(query, mother_name: str):
    """Filter records whose stored JSON contains mother_name in a mother-related field."""
    term = (mother_name or "").strip()
    if not term:
        return query
    clauses = [
        Record.data_json.ilike(f'%"{key}"%{term}%')
        for key in MOTHER_NAME_JSON_KEYS
    ]
    return query.filter(or_(*clauses))


@app.route("/search", methods=["GET", "POST"])
@login_required
def search_records():
    results = []
    registry_number = (request.args.get("registry_number") or request.form.get("registry_number") or "").strip()
    full_name = (request.args.get("full_name") or request.form.get("full_name") or "").strip()
    mother_name = (request.args.get("mother_name") or request.form.get("mother_name") or "").strip()
    document_type = (request.args.get("document_type") or request.form.get("document_type") or "").strip().lower()
    event_date = (request.args.get("event_date") or request.form.get("event_date") or "").strip()

    if request.method == "POST" or registry_number or full_name or mother_name or document_type or event_date:
        q = Record.query
        if registry_number:
            q = q.filter(Record.registry_number.ilike(f"%{registry_number}%"))
        if full_name:
            q = q.filter(Record.full_name.ilike(f"%{full_name}%"))
        q = _apply_mother_name_filter(q, mother_name)
        if document_type and document_type in DOCUMENT_TYPES:
            q = q.filter(Record.document_type == document_type)
        if event_date:
            q = q.filter(Record.event_date.ilike(f"%{event_date}%"))
        results = q.order_by(Record.created_at.desc()).limit(100).all()

    search_performed = request.method == "POST" or bool(
        registry_number or full_name or mother_name or document_type or event_date
    )

    return render_template(
        "search.html",
        current_user=get_current_user(),
        nav_active="search",
        results=results,
        search_performed=search_performed,
        registry_number=registry_number,
        full_name=full_name,
        mother_name=mother_name,
        document_type=document_type,
        event_date=event_date,
        document_types=DOCUMENT_TYPES,
    )


@app.route("/record/<int:record_id>")
@login_required
def record_detail(record_id):
    record = db.session.get(Record, record_id)
    if not record:
        flash("Record not found.")
        return redirect(url_for("search_records"))
    data = _load_record_data_json(record)
    display_registry_number = ""
    if isinstance(data, dict):
        v = data.get("Registry Number")
        if v is not None and str(v).strip():
            display_registry_number = str(v).strip()
        if not display_registry_number:
            display_registry_number = (_registry_number_from_submitted(data) or "").strip()
    if not display_registry_number:
        display_registry_number = (record.registry_number or "").strip()
    user = get_current_user()
    role = (user.role or "").upper() if user else ""
    # Staff: unused approved edit codes (full request history is on My Edit Requests)
    my_requests = []
    can_print = False
    if role == "STAFF":
        my_requests = (
            EditRequest.query.filter_by(
                record_id=record_id, requested_by_id=user.id, status="APPROVED"
            )
            .filter(EditRequest.code_used_at.is_(None))
            .order_by(EditRequest.requested_at.desc())
            .all()
        )
        can_print = user_can_print_record(user, record_id)
    elif role == "ADMIN":
        can_print = True
    approved_print_format = None
    if role == "STAFF" and can_print:
        approval = _staff_active_print_approval(user.id, record_id)
        if approval:
            approved_print_format = normalize_print_format(getattr(approval, "print_format", None))
    return render_template(
        "record_detail.html",
        record=record,
        data=data,
        display_registry_number=display_registry_number,
        current_user=user,
        nav_active="search",
        my_requests=my_requests,
        document_types=DOCUMENT_TYPES,
        can_print=can_print,
        cert_date=cert_issue_date(),
        form_meta=form_meta(record.document_type),
        approved_print_format=approved_print_format,
        annotation_form=annotation_form_defaults(data),
    )


@app.route("/record/<int:record_id>/annotation", methods=["POST"])
@login_required
def record_save_annotation(record_id):
    record = db.session.get(Record, record_id)
    if not record:
        flash("Record not found.")
        return redirect(url_for("search_records"))
    user = get_current_user()
    if not user or (user.role or "").upper() != "ADMIN":
        flash("Only administrators can save official document annotations.")
        return redirect(url_for("record_detail", record_id=record_id))
    data = _load_record_data_json(record)
    annotation = None
    if not (request.form.get("clear_annotation") or "").strip():
        annotation = annotation_from_form(request.form)
    data = apply_annotation_to_data(data, annotation)
    payload = json.dumps(data, ensure_ascii=False)
    record.data_json = payload
    record.extracted_json = payload
    record.corrected_json = payload
    record.updated_at = datetime.utcnow()
    db.session.commit()
    _log_audit(
        user.id,
        "RECORD_ANNOTATION",
        f"record_id={record_id} {'cleared' if not annotation else 'saved'}",
    )
    flash("Annotation removed." if not annotation else "Document annotation saved.")
    return redirect(url_for("record_detail", record_id=record_id))


@app.route("/record/<int:record_id>/log-print", methods=["POST"])
@login_required
def record_log_print(record_id):
    """Log that staff printed this record's document. Requires admin approval for staff."""
    record = db.session.get(Record, record_id)
    if not record:
        return jsonify({"ok": False, "error": "Record not found"}), 404
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "Not logged in"}), 403
    if not user_can_print_record(user, record_id):
        return jsonify({"ok": False, "error": "Admin approval is required before you can print."}), 403
    payload = request.get_json(silent=True) or {}
    print_type = (payload.get("print_type") or "original").strip().lower()
    if print_type not in ("original", "certification", "both"):
        print_type = "original"
    if (user.role or "").upper() == "STAFF":
        approval = _staff_active_print_approval(user.id, record_id)
        if approval:
            allowed = normalize_print_format(getattr(approval, "print_format", None))
            if print_type != allowed:
                label = print_format_label(allowed, record.document_type)
                return jsonify({
                    "ok": False,
                    "error": f"Your approved request is for: {label}.",
                }), 403
    try:
        log = PrintLog(record_id=record_id, user_id=user.id)
        db.session.add(log)
        if (user.role or "").upper() == "STAFF":
            approval = _staff_active_print_approval(user.id, record_id)
            if approval:
                approval.used_at = datetime.utcnow()
        db.session.commit()
        _log_audit(
            user.id,
            "PRINT_DOCUMENT",
            f"record_id={record_id} print_type={print_type} registry={record.registry_number or ''}",
        )
        return jsonify({"ok": True})
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "error": "Failed to log print"}), 500


@app.route("/record/<int:record_id>/request-print", methods=["GET", "POST"])
@login_required
def request_print(record_id):
    record = db.session.get(Record, record_id)
    if not record:
        flash("Record not found.")
        return redirect(url_for("search_records"))
    user = get_current_user()
    if not user or (user.role or "").upper() != "STAFF":
        flash("Only staff can submit print requests.")
        return redirect(url_for("record_detail", record_id=record_id))
    if user_can_print_record(user, record_id):
        flash("You already have approval to print this record.")
        return redirect(url_for("record_detail", record_id=record_id))
    pending = PrintRequest.query.filter_by(
        record_id=record_id, requested_by_id=user.id, status="PENDING"
    ).first()
    if request.method == "POST":
        reason = (request.form.get("reason") or "").strip()
        print_format = normalize_print_format(request.form.get("print_format"))
        if not reason:
            flash("Please provide a reason for the print request.")
            return redirect(url_for("request_print", record_id=record_id))
        if print_format in (PRINT_FORMAT_ORIGINAL, PRINT_FORMAT_BOTH) and not (record.image_path or "").strip():
            flash("This record has no scanned image on file. Choose the certification form instead.")
            return redirect(url_for("request_print", record_id=record_id))
        if pending:
            flash("You already have a pending print request for this record.")
            return redirect(url_for("record_detail", record_id=record_id))
        req = PrintRequest(
            record_id=record_id,
            requested_by_id=user.id,
            reason=reason,
            print_format=print_format,
        )
        db.session.add(req)
        db.session.commit()
        _log_audit(
            user.id,
            "PRINT_REQUEST_SUBMIT",
            f"record_id={record_id} request_id={req.id} print_format={print_format}",
        )
        flash("Print request sent. Wait for admin approval before printing.")
        return redirect(url_for("record_detail", record_id=record_id))
    return render_template(
        "request_print.html",
        record=record,
        current_user=user,
        nav_active="search",
        document_types=DOCUMENT_TYPES,
        has_pending=pending is not None,
    )


@app.route("/record/<int:record_id>/request-edit", methods=["GET", "POST"])
@login_required
def request_edit(record_id):
    record = db.session.get(Record, record_id)
    if not record:
        flash("Record not found.")
        return redirect(url_for("search_records"))
    user = get_current_user()
    if not user or (user.role or "").upper() != "STAFF":
        flash("Only staff can submit edit requests.")
        return redirect(url_for("record_detail", record_id=record_id))
    data = _load_record_data_json(record)
    if request.method == "POST":
        reason = (request.form.get("reason") or "").strip()
        fields_requested = (request.form.get("fields_requested") or "").strip()
        if not reason:
            flash("Please provide a reason for the edit request.")
            return redirect(url_for("request_edit", record_id=record_id))
        req = EditRequest(
            record_id=record_id,
            requested_by_id=user.id,
            reason=reason,
            fields_requested=fields_requested or ", ".join(data.keys()) if data else "",
        )
        db.session.add(req)
        db.session.commit()
        _log_audit(user.id, "EDIT_REQUEST_SUBMIT", f"record_id={record_id} request_id={req.id}")
        flash("Edit request sent. Wait for admin approval and a 5-digit code to edit.")
        return redirect(url_for("record_detail", record_id=record_id))
    return render_template(
        "request_edit.html",
        record=record,
        data=data,
        current_user=user,
        nav_active="search",
    )


@app.route("/administration")
@admin_required
def administration():
    tab = (request.args.get("tab") or "dashboard").strip().lower()
    if tab not in ("dashboard", "audit", "edit_requests", "print_requests", "users", "print_logs", "backup_restore"):
        tab = "dashboard"
    request_doc_type = _parse_doc_type_filter_arg(request.args.get("doc_type"))
    edit_requests_list = []
    if tab == "edit_requests":
        edit_requests_q = EditRequest.query
        if request_doc_type:
            edit_requests_q = edit_requests_q.join(Record, EditRequest.record_id == Record.id).filter(
                Record.document_type == request_doc_type
            )
        edit_requests_list = edit_requests_q.order_by(EditRequest.requested_at.desc()).limit(200).all()
    print_requests_list = []
    if tab == "print_requests":
        print_requests_q = PrintRequest.query
        if request_doc_type:
            print_requests_q = print_requests_q.join(Record, PrintRequest.record_id == Record.id).filter(
                Record.document_type == request_doc_type
            )
        print_requests_list = print_requests_q.order_by(PrintRequest.requested_at.desc()).limit(200).all()
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all() if tab == "audit" else []
    users_list = User.query.order_by(User.username).all() if tab == "users" else []
    print_logs = []
    if tab == "print_logs":
        print_logs = (
            PrintLog.query
            .order_by(PrintLog.printed_at.desc())
            .limit(100)
            .all()
        )
    pending_count = EditRequest.query.filter_by(status="PENDING").count()
    pending_print_count = PrintRequest.query.filter_by(status="PENDING").count()
    # Dashboard stats
    birth_count = Record.query.filter_by(document_type="birth").count()
    marriage_count = Record.query.filter_by(document_type="marriage").count()
    death_count = Record.query.filter_by(document_type="death").count()
    total_records = birth_count + marriage_count + death_count
    users_count = User.query.count()
    staff_count = User.query.filter(db.func.upper(User.role) == "STAFF").count()
    admin_users_count = User.query.filter(db.func.upper(User.role) == "ADMIN").count()
    audit_recent_count = AuditLog.query.count()
    current_year = datetime.now().year
    auto_backup_settings = load_auto_backup_settings(BASE_DIR) if tab == "backup_restore" else None
    auto_backup_files = list_auto_backups(BASE_DIR) if tab == "backup_restore" else []
    return render_template(
        "administration.html",
        current_user=get_current_user(),
        nav_active="admin",
        tab=tab,
        edit_requests=edit_requests_list,
        print_requests=print_requests_list,
        audit_logs=audit_logs,
        users_list=users_list,
        pending_count=pending_count,
        pending_print_count=pending_print_count,
        birth_count=birth_count,
        marriage_count=marriage_count,
        death_count=death_count,
        total_records=total_records,
        users_count=users_count,
        staff_count=staff_count,
        admin_users_count=admin_users_count,
        audit_recent_count=audit_recent_count,
        document_types=DOCUMENT_TYPES,
        print_logs=print_logs,
        current_year=current_year,
        request_doc_type=request_doc_type,
        auto_backup_settings=auto_backup_settings,
        auto_backup_files=auto_backup_files,
    )


def _civil_registry_report_context():
    doc_type = (request.args.get("doc_type") or "birth").strip().lower()
    if doc_type not in DOCUMENT_TYPES:
        doc_type = "birth"
    year = (request.args.get("year") or "").strip()
    barangay = (request.args.get("barangay") or "").strip()
    location = ""

    q = Record.query.filter(Record.document_type == doc_type).order_by(
        Record.created_at.asc(), Record.id.asc()
    )
    builders = {"birth": birth_row, "death": death_row, "marriage": marriage_row}
    builder = builders[doc_type]
    all_rows = []
    for record in q.all():
        if not record_is_reportable(record):
            continue
        data = load_record_fields(record)
        all_rows.append(builder(record, data))
    year_options, barangay_options, location_options = collect_filter_options(all_rows)
    filtered_rows = [row for row in all_rows if row_matches_filters(row, year, barangay, location)]
    try:
        per_page = int(request.args.get("per_page") or 25)
    except ValueError:
        per_page = 25
    if per_page not in (25, 50, 100):
        per_page = 25
    try:
        page = int(request.args.get("page") or 1)
    except ValueError:
        page = 1
    total = len(filtered_rows)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    rows = filtered_rows[start:start + per_page]
    focus = (request.args.get("focus") or "").strip() in {"1", "true", "yes"}
    excel_args = {"doc_type": doc_type}
    if year:
        excel_args["year"] = year
    if barangay:
        excel_args["barangay"] = barangay
    query_args = dict(excel_args)
    if per_page != 25:
        query_args["per_page"] = per_page
    if focus:
        query_args["focus"] = "1"
    enter_focus_args = dict(query_args)
    enter_focus_args["focus"] = "1"
    exit_focus_args = {k: v for k, v in query_args.items() if k != "focus"}
    if page > 1:
        enter_focus_args["page"] = page
        exit_focus_args["page"] = page
    doc_links = {
        "birth": {**{k: v for k, v in query_args.items() if k != "doc_type"}, "doc_type": "birth"},
        "death": {**{k: v for k, v in query_args.items() if k != "doc_type"}, "doc_type": "death"},
        "marriage": {**{k: v for k, v in query_args.items() if k != "doc_type"}, "doc_type": "marriage"},
    }
    return {
        "doc_type": doc_type,
        "year": year,
        "barangay": barangay,
        "location": location,
        "year_options": year_options,
        "barangay_options": barangay_options,
        "location_options": location_options,
        "rows": rows,
        "filtered_rows": filtered_rows,
        "filtered_count": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "focus": focus,
        "query_args": query_args,
        "enter_focus_args": enter_focus_args,
        "exit_focus_args": exit_focus_args,
        "doc_links": doc_links,
        "empty_rows": 0 if total >= 8 else max(0, 8 - len(rows)),
        "page_left": 1,
        "page_right": 2,
        "excel_args": excel_args,
    }


@app.route("/administration/reports")
@admin_required
def civil_registry_reports():
    """Admin-only official Birth / Death / Marriage registers from saved archive records."""
    ctx = _civil_registry_report_context()
    return render_template(
        "reports.html",
        current_user=get_current_user(),
        nav_active="reports",
        document_types=DOCUMENT_TYPES,
        **ctx,
    )


@app.route("/administration/reports/excel")
@admin_required
def civil_registry_reports_excel():
    """Excel download of the same filtered official-register rows shown on screen."""
    ctx = _civil_registry_report_context()
    doc_type = ctx["doc_type"]
    rows = ctx["filtered_rows"]
    if doc_type == "death":
        sheets = {
            "Register of Death": (DEATH_EXCEL_HEADERS, [death_excel_row(r) for r in rows]),
        }
        filename = "register_of_death.xlsx"
    elif doc_type == "marriage":
        excel_rows = []
        for r in rows:
            excel_rows.extend(marriage_excel_rows(r))
        sheets = {
            "Register of Marriages": (MARRIAGE_EXCEL_HEADERS, excel_rows),
        }
        filename = "register_of_marriages.xlsx"
    else:
        sheets = {
            "Register of Live Births": (BIRTH_EXCEL_HEADERS, [birth_excel_row(r) for r in rows]),
        }
        filename = "register_of_live_births.xlsx"
    if year := ctx["year"]:
        filename = filename.replace(".xlsx", f"_{year}.xlsx")
    payload = build_xlsx(sheets)
    return send_file(
        BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/administration/users/create", methods=["POST"])
@admin_required
def administration_create_user():
    """Create a new system user with a chosen role (ADMIN or STAFF)."""
    admin = get_current_user()
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    role = (request.form.get("role") or "").strip().upper()

    if not username or not password:
        flash("Username and password are required.")
        return redirect(url_for("administration", tab="users"))
    if len(username) > 64:
        flash("Username must be 64 characters or fewer.")
        return redirect(url_for("administration", tab="users"))
    if len(password) < 6:
        flash("Password must be at least 6 characters.")
        return redirect(url_for("administration", tab="users"))
    if role not in ("ADMIN", "STAFF"):
        flash("Invalid role. Choose Administrator or Staff.")
        return redirect(url_for("administration", tab="users"))
    if User.query.filter_by(username=username).first():
        flash("That username is already in use.")
        return redirect(url_for("administration", tab="users"))

    user = User(
        username=username,
        password_hash=_safe_hash(password),
        role=role,
    )
    db.session.add(user)
    db.session.commit()
    _log_audit(admin.id if admin else None, "USER_CREATE", f"username={username} role={role}")
    flash(f'User "{username}" was created with role {role}.', "success")
    return redirect(url_for("administration", tab="users"))


@app.route("/administration/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def administration_delete_user(user_id):
    """Delete a user account with safety checks."""
    admin = get_current_user()
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.")
        return redirect(url_for("administration", tab="users"))

    # Prevent deleting your own account while logged in.
    if admin and user.id == admin.id:
        flash("You cannot delete your own account while logged in.")
        return redirect(url_for("administration", tab="users"))

    # Keep at least one admin in the system.
    if (user.role or "").upper() == "ADMIN":
        remaining_admins = (
            User.query.filter(db.func.upper(User.role) == "ADMIN", User.id != user.id).count()
        )
        if remaining_admins <= 0:
            flash("Cannot delete this account. At least one ADMIN account must remain.")
            return redirect(url_for("administration", tab="users"))

    # Protect data integrity for related records/logs.
    req_count = EditRequest.query.filter_by(requested_by_id=user.id).count()
    reviewed_count = EditRequest.query.filter_by(reviewed_by_id=user.id).count()
    print_count = PrintLog.query.filter_by(user_id=user.id).count()
    print_req_count = PrintRequest.query.filter(
        or_(PrintRequest.requested_by_id == user.id, PrintRequest.reviewed_by_id == user.id)
    ).count()
    if req_count or reviewed_count or print_count or print_req_count:
        flash(
            "Cannot delete this account because it has related history "
            f"(edit requests: {req_count}, reviews: {reviewed_count}, "
            f"print logs: {print_count}, print requests: {print_req_count})."
        )
        return redirect(url_for("administration", tab="users"))

    for log in AuditLog.query.filter_by(user_id=user.id).all():
        log.user_id = None

    username = user.username
    role = (user.role or "").upper()
    db.session.delete(user)
    db.session.commit()
    _log_audit(admin.id if admin else None, "USER_DELETE", f"username={username} role={role}")
    flash(f'User "{username}" was deleted.', "success")
    return redirect(url_for("administration", tab="users"))


def _iso_week_start_end(year: int, week: int):
    """Return (start_date, end_date) for the given ISO year and week (1-53)."""
    jan4 = date(year, 1, 4)
    start = jan4 - timedelta(days=jan4.weekday())
    start = start + timedelta(weeks=week - 1)
    end = start + timedelta(days=6)
    return start, end


@app.route("/administration/backup-documents")
@admin_required
def administration_backup_documents():
    """Download civil registry documents (records + certificate images) for a chosen period: by week, month, or year."""
    period = (request.args.get("period") or "month").strip().lower()
    if period not in ("week", "month", "year"):
        period = "month"
    try:
        year = int(request.args.get("year") or datetime.now().year)
    except ValueError:
        year = datetime.now().year
    year = max(2000, min(2100, year))

    start_dt = None
    end_dt = None
    filename_part = None

    if period == "year":
        start_dt = datetime(year, 1, 1, 0, 0, 0)
        end_dt = datetime(year, 12, 31, 23, 59, 59)
        filename_part = str(year)
    elif period == "month":
        try:
            month = int(request.args.get("month") or datetime.now().month)
        except ValueError:
            month = datetime.now().month
        month = max(1, min(12, month))
        start_dt = datetime(year, month, 1, 0, 0, 0)
        if month == 12:
            end_dt = datetime(year, 12, 31, 23, 59, 59)
        else:
            end_dt = datetime(year, month + 1, 1, 0, 0, 0) - timedelta(seconds=1)
        filename_part = f"{year}-{month:02d}"
    else:
        try:
            week = int(request.args.get("week") or 1)
        except ValueError:
            week = 1
        week = max(1, min(53, week))
        start_date, end_date = _iso_week_start_end(year, week)
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, time(23, 59, 59))
        filename_part = f"{year}-W{week:02d}"

    records = (
        Record.query.filter(Record.created_at >= start_dt, Record.created_at <= end_dt)
        .order_by(Record.created_at.asc())
        .all()
    )

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest_rows = []
        seen_paths = set()
        for r in records:
            manifest_rows.append({
                "id": r.id,
                "document_type": r.document_type,
                "registry_number": r.registry_number or "",
                "full_name": r.full_name or "",
                "event_date": r.event_date or "",
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
                "image_path": r.image_path or "",
            })
            for path_attr in ("image_path", "image_front_path"):
                rel = (getattr(r, path_attr) or "").strip()
                if not rel or ".." in rel or rel.startswith("/"):
                    continue
                full_path = _upload_file_path(rel)
                if full_path is not None and full_path.exists() and full_path.is_file():
                    base_name = Path(rel).name
                    arcname = f"documents/{r.id}_{base_name}"
                    if arcname in seen_paths:
                        arcname = f"documents/{r.id}_{path_attr}_{base_name}"
                    seen_paths.add(arcname)
                    zf.write(full_path, arcname)
        manifest_buf = StringIO()
        if manifest_rows:
            writer = csv.DictWriter(manifest_buf, fieldnames=["id", "document_type", "registry_number", "full_name", "event_date", "created_at", "image_path"])
            writer.writeheader()
            writer.writerows(manifest_rows)
        manifest_buf.seek(0)
        zf.writestr("manifest.csv", manifest_buf.getvalue())

    buf.seek(0)
    filename = f"civil_registry_documents_{filename_part}.zip"
    _log_audit(session.get("user_id"), "BACKUP_DOCUMENTS", f"period={period} {filename_part} records={len(records)}")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/administration/backup")
@admin_required
def administration_backup():
    """Create a full zip backup of the database and uploads folder (for full restore)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"civil_registry_full_backup_{timestamp}.zip"
    tmp_path = BASE_DIR / "backups" / f"_tmp_manual_{timestamp}.zip"
    write_full_backup_zip(
        tmp_path,
        base_dir=BASE_DIR,
        upload_dir=UPLOAD_DIR,
        include_sqlite_db=is_sqlite_database(app.config.get("SQLALCHEMY_DATABASE_URI")),
    )
    buf = BytesIO(tmp_path.read_bytes())
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:
        pass
    buf.seek(0)
    _log_audit(session.get("user_id"), "BACKUP_FULL", filename)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )


def _auto_backup_audit(action: str, details: str) -> None:
    _log_audit(None, action, details)


@app.route("/administration/auto-backup/settings", methods=["POST"])
@admin_required
def administration_auto_backup_settings():
    """Save automatic backup schedule (daily / weekly / monthly / yearly)."""
    settings = settings_from_form(request.form, BASE_DIR)
    save_auto_backup_settings(BASE_DIR, settings)
    try:
        init_auto_backup_scheduler(
            app,
            base_dir=BASE_DIR,
            upload_dir=UPLOAD_DIR,
            include_sqlite_db=lambda: is_sqlite_database(app.config.get("SQLALCHEMY_DATABASE_URI")),
            audit_callback=_auto_backup_audit,
        )
        apply_schedule(app)
    except Exception as exc:
        flash(f"Settings saved, but scheduler could not start: {exc}", "error")
        return redirect(url_for("administration", tab="backup_restore"))
    status = "enabled" if settings.get("enabled") else "disabled"
    _log_audit(session.get("user_id"), "AUTO_BACKUP_SETTINGS", f"status={status} frequency={settings.get('frequency')}")
    flash("Automatic backup settings saved.", "success")
    return redirect(url_for("administration", tab="backup_restore"))


@app.route("/administration/auto-backup/run-now", methods=["POST"])
@admin_required
def administration_auto_backup_run_now():
    """Run an automatic full backup immediately."""
    ok, message, rel_file = run_auto_backup(
        base_dir=BASE_DIR,
        upload_dir=UPLOAD_DIR,
        include_sqlite_db=is_sqlite_database(app.config.get("SQLALCHEMY_DATABASE_URI")),
        audit_callback=_auto_backup_audit,
        trigger="manual",
    )
    if ok:
        flash(f"Backup created: {rel_file}", "success")
    else:
        flash(f"Backup failed: {message}", "error")
    return redirect(url_for("administration", tab="backup_restore"))


@app.route("/administration/auto-backup/download/<path:filename>")
@admin_required
def administration_auto_backup_download(filename):
    """Download a previously saved automatic backup from backups/auto/."""
    full_path, err = resolve_auto_backup_path(BASE_DIR, filename)
    if err:
        flash(err)
        return redirect(url_for("administration", tab="backup_restore"))
    folder = BASE_DIR / "backups" / "auto"
    return send_from_directory(folder, full_path.name, as_attachment=True)


@app.route("/administration/auto-backup/delete/<path:filename>", methods=["POST"])
@admin_required
def administration_auto_backup_delete(filename):
    """Delete a previously saved automatic backup from backups/auto/."""
    ok, message = delete_auto_backup(BASE_DIR, filename)
    user = get_current_user()
    if ok:
        _auto_backup_audit("AUTO_BACKUP_DELETED", f"file={message} by={user.username if user else '—'}")
        flash(f'Backup "{message}" was deleted.', "success")
    else:
        flash(message, "error")
    return redirect(url_for("administration", tab="backup_restore"))


@app.route("/administration/restore", methods=["POST"])
@admin_required
def administration_restore():
    """Restore database and uploads from an uploaded backup zip. Current data is backed up first."""
    if "backup_file" not in request.files:
        flash("Please select a backup file (.zip) to restore.")
        return redirect(url_for("administration", tab="backup_restore"))
    file = request.files["backup_file"]
    if not file or file.filename == "":
        flash("Please select a backup file.")
        return redirect(url_for("administration", tab="backup_restore"))
    if not file.filename.lower().endswith(".zip"):
        flash("Only .zip backup files are allowed.")
        return redirect(url_for("administration", tab="backup_restore"))

    if not is_sqlite_database(app.config.get("SQLALCHEMY_DATABASE_URI")):
        flash(
            "Full restore from a backup zip is only supported when using the built-in SQLite file "
            "(civil_registry.db). For PostgreSQL, restore with pg_restore / your SQL dump and copy "
            "the uploads folder from the zip if needed.",
            "error",
        )
        return redirect(url_for("administration", tab="backup_restore"))

    db_path = BASE_DIR / "civil_registry.db"
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_db = None
    uploads_backup = None

    try:
        data = file.read()
        with zipfile.ZipFile(BytesIO(data), "r") as zf:
            names = zf.namelist()
            if "civil_registry.db" not in names:
                flash("Invalid backup: zip must contain civil_registry.db")
                return redirect(url_for("administration", tab="backup_restore"))

            # Backup current database before replace
            if db_path.exists():
                backup_db = backup_dir / f"civil_registry_pre_restore_{timestamp}.db"
                shutil.copy2(db_path, backup_db)

            # Backup current uploads folder
            uploads_backup = BASE_DIR / f"uploads_backup_{timestamp}"
            if UPLOAD_DIR.exists():
                shutil.copytree(UPLOAD_DIR, uploads_backup, dirs_exist_ok=False)

            # Close DB connections so we can replace the file
            db.session.remove()
            try:
                # Extract database
                with zf.open("civil_registry.db") as src:
                    with open(db_path, "wb") as dst:
                        dst.write(src.read())

                # Clear existing uploads then extract uploads from zip
                uploads_in_zip = [n for n in names if n.startswith("uploads/") and not n.endswith("/")]
                if uploads_in_zip:
                    for item in list(UPLOAD_DIR.iterdir()) if UPLOAD_DIR.exists() else []:
                        if item.is_file():
                            item.unlink(missing_ok=True)
                        else:
                            shutil.rmtree(item, ignore_errors=True)
                for name in names:
                    if not name.startswith("uploads/") or name.endswith("/"):
                        continue
                    rel = _normalize_upload_relpath(name)
                    dest = _upload_file_path(rel)
                    if dest is None:
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                _flatten_nested_uploads()
            except Exception as e:
                # Restore from backup on failure
                if backup_db is not None and backup_db.exists():
                    shutil.copy2(backup_db, db_path)
                if uploads_backup is not None and uploads_backup.exists():
                    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
                    shutil.copytree(uploads_backup, UPLOAD_DIR)
                flash(f"Restore failed: {e}. Previous data was restored.")
                return redirect(url_for("administration", tab="backup_restore"))

            # Remove temporary uploads backup if we have uploads in zip
            if uploads_backup is not None and uploads_backup.exists():
                try:
                    shutil.rmtree(uploads_backup, ignore_errors=True)
                except OSError:
                    pass

        _log_audit(session.get("user_id"), "RESTORE_DATA", f"from {file.filename}")
        flash("Data restored successfully. Database backup saved in backups/ folder.", "success")
    except zipfile.BadZipFile:
        flash("Invalid or corrupted zip file.")
    except Exception as e:
        flash(f"Restore failed: {e}")
    return redirect(url_for("administration", tab="backup_restore"))


@app.route("/administration/print-request/<int:request_id>/approve", methods=["POST"])
@admin_required
def print_request_approve(request_id):
    req = db.session.get(PrintRequest, request_id)
    if not req or req.status != "PENDING":
        flash("Request not found or already processed.")
        return _admin_print_requests_redirect()
    req.status = "APPROVED"
    req.reviewed_at = datetime.utcnow()
    req.reviewed_by_id = session.get("user_id")
    req.rejection_reason = ""
    req.used_at = None
    db.session.commit()
    _log_audit(session["user_id"], "PRINT_REQUEST_APPROVE", f"request_id={request_id} record_id={req.record_id}")
    flash("Print request approved. Staff can now print this document.", "success")
    return _admin_print_requests_redirect()


@app.route("/administration/print-request/<int:request_id>/reject", methods=["POST"])
@admin_required
def print_request_reject(request_id):
    req = db.session.get(PrintRequest, request_id)
    if not req or req.status != "PENDING":
        flash("Request not found or already processed.")
        return _admin_print_requests_redirect()
    req.status = "REJECTED"
    req.reviewed_at = datetime.utcnow()
    req.reviewed_by_id = session.get("user_id")
    req.rejection_reason = (request.form.get("rejection_reason") or "").strip()
    db.session.commit()
    _log_audit(session["user_id"], "PRINT_REQUEST_REJECT", f"request_id={request_id} record_id={req.record_id}")
    flash("Print request rejected.")
    return _admin_print_requests_redirect()


@app.route("/administration/edit-request/<int:request_id>/approve", methods=["POST"])
@admin_required
def edit_request_approve(request_id):
    req = db.session.get(EditRequest, request_id)
    if not req or req.status != "PENDING":
        flash("Request not found or already processed.")
        return _admin_edit_requests_redirect()
    code = "".join(random.choices("0123456789", k=5))
    req.status = "APPROVED"
    req.reviewed_at = datetime.utcnow()
    req.reviewed_by_id = session.get("user_id")
    req.approval_code = code
    # Ensure a newly approved request is always unlockable by staff.
    req.code_used_at = None
    req.rejection_reason = ""
    db.session.commit()
    _log_audit(session["user_id"], "EDIT_REQUEST_APPROVE", f"request_id={request_id} record_id={req.record_id} code={code}")
    flash(f"Approved. Give this 5-digit code to staff: {code}", "success")
    return _admin_edit_requests_redirect()


@app.route("/administration/edit-request/<int:request_id>/reject", methods=["POST"])
@admin_required
def edit_request_reject(request_id):
    req = db.session.get(EditRequest, request_id)
    if not req or req.status != "PENDING":
        flash("Request not found or already processed.")
        return _admin_edit_requests_redirect()
    req.status = "REJECTED"
    req.reviewed_at = datetime.utcnow()
    req.reviewed_by_id = session.get("user_id")
    req.rejection_reason = (request.form.get("rejection_reason") or "").strip()
    db.session.commit()
    _log_audit(session["user_id"], "EDIT_REQUEST_REJECT", f"request_id={request_id} record_id={req.record_id}")
    flash("Edit request rejected.")
    return _admin_edit_requests_redirect()


@app.route("/record/<int:record_id>/verify-code", methods=["POST"])
@login_required
def record_verify_code(record_id):
    record = db.session.get(Record, record_id)
    if not record:
        flash("Record not found.")
        return redirect(url_for("search_records"))
    user = get_current_user()
    if not user or (user.role or "").upper() != "STAFF":
        flash("Only staff can use approval codes.")
        return redirect(url_for("record_detail", record_id=record_id))
    code = (request.form.get("approval_code") or "").strip()
    if not code:
        flash("Please enter the 5-digit code from admin.")
        next_url = request.form.get("next") or url_for("record_detail", record_id=record_id)
        return redirect(next_url)
    req = EditRequest.query.filter_by(
        record_id=record_id,
        requested_by_id=user.id,
        status="APPROVED",
        approval_code=code,
    ).filter(EditRequest.code_used_at.is_(None)).first()
    if not req:
        flash("Invalid or already-used code for this record.")
        next_url = request.form.get("next") or url_for("record_detail", record_id=record_id)
        return redirect(next_url)
    session["allowed_edit_request_id"] = req.id
    session["allowed_edit_record_id"] = record_id
    flash("Code accepted. You can now edit the record.", "success")
    return redirect(url_for("record_edit", record_id=record_id))


@app.route("/record/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
def record_edit(record_id):
    record = db.session.get(Record, record_id)
    if not record:
        flash("Record not found.")
        return redirect(url_for("search_records"))
    user = get_current_user()
    if not user:
        flash("Please log in to continue.")
        return redirect(url_for("login"))
    role = (user.role or "").upper()
    is_admin = role == "ADMIN"
    is_staff = role == "STAFF"
    if not is_admin and not is_staff:
        flash("You do not have permission to edit records.")
        return redirect(url_for("record_detail", record_id=record_id))
    req = None
    if is_staff:
        allowed_request_id = session.get("allowed_edit_request_id")
        try:
            allowed_record_id = int(session.get("allowed_edit_record_id"))
        except (TypeError, ValueError):
            allowed_record_id = None
        if allowed_record_id != record_id or not allowed_request_id:
            flash("Enter the 5-digit approval code on the record page first.")
            return redirect(url_for("record_detail", record_id=record_id))
        req = db.session.get(EditRequest, allowed_request_id)
        if not req or req.record_id != record_id or req.code_used_at:
            session.pop("allowed_edit_request_id", None)
            session.pop("allowed_edit_record_id", None)
            flash("This edit link has expired. Request a new code from admin.")
            return redirect(url_for("record_detail", record_id=record_id))
    if request.method == "POST":
        existing = _load_record_data_json(record)
        submitted = _submitted_from_request_form()
        submitted = _normalize_submitted_registry_keys(submitted)
        if (request.form.get("clear_annotation") or "").strip():
            annotation = None
        elif "annotation_text" not in request.form:
            annotation = document_annotation_from_data(existing)
        else:
            annotation = annotation_from_form(request.form) or document_annotation_from_data(existing)
        submitted = apply_annotation_to_data(submitted, annotation)
        if not public_record_fields(submitted):
            flash("No data to save.")
            return redirect(url_for("record_edit", record_id=record_id))
        updated_registry_number = _registry_number_from_submitted(submitted)
        updated_full_name = _full_name_from_data(record.document_type, submitted)
        updated_event_date = _event_date_from_data(record.document_type, submitted)
        # Only enforce duplicate checks if the "identity" of the record changes.
        # This allows approved edits to update other fields even if the DB already contains
        # legacy duplicates from older entries/imports.
        prior_registry_number = (record.registry_number or "").strip()
        prior_full_name = (record.full_name or "").strip()
        prior_event_date = (record.event_date or "").strip()
        identity_changed = False
        if updated_registry_number and updated_registry_number != prior_registry_number:
            identity_changed = True
        elif (not updated_registry_number) and (updated_full_name != prior_full_name or updated_event_date != prior_event_date):
            identity_changed = True

        if identity_changed:
            duplicate = _find_duplicate_record(
                doc_type=record.document_type,
                registry_number=updated_registry_number,
                full_name=updated_full_name,
                event_date=updated_event_date,
                exclude_record_id=record.id,
            )
            if duplicate:
                flash(
                    f"Update blocked: this document already exists in archiving (Record ID: {duplicate.id}). "
                    "Please review the existing record instead."
                )
                return redirect(url_for("record_edit", record_id=record_id))
        data_json_str = json.dumps(submitted, ensure_ascii=False)
        record.data_json = data_json_str
        record.extracted_json = data_json_str
        record.corrected_json = data_json_str
        record.registry_number = updated_registry_number or None
        record.full_name = updated_full_name
        record.event_date = updated_event_date
        record.updated_at = datetime.utcnow()
        if req:
            req.code_used_at = record.updated_at
            session.pop("allowed_edit_request_id", None)
            session.pop("allowed_edit_record_id", None)
        db.session.commit()
        db.session.refresh(record)
        _log_audit(user.id, "RECORD_EDIT", f"record_id={record_id} by={role}")
        flash("Record updated successfully.")
        return redirect(url_for("record_detail", record_id=record_id))
    data = _load_record_data_json(record)
    data = _normalize_submitted_registry_keys(dict(data))
    display_registry_number = ""
    if isinstance(data, dict):
        v = data.get("Registry Number")
        if v is not None and str(v).strip():
            display_registry_number = str(v).strip()
        if not display_registry_number:
            display_registry_number = (_registry_number_from_submitted(data) or "").strip()
    if not display_registry_number:
        display_registry_number = (record.registry_number or "").strip()
    return render_template(
        "record_edit.html",
        record=record,
        data=data,
        display_registry_number=display_registry_number,
        current_user=user,
        nav_active="search",
        document_types=DOCUMENT_TYPES,
        annotation_form=annotation_form_defaults(data),
    )


def _redirect_archiving():
    """Return redirect to archiving, preserving optional ?doc_type= filter."""
    dt = _parse_doc_type_filter_arg(request.form.get("doc_type") or request.args.get("doc_type"))
    if dt:
        return redirect(url_for("archiving", doc_type=dt))
    return redirect(url_for("archiving"))


@app.route("/archiving")
@login_required
def archiving():
    """Archiving page: all saved records separated by Birth, Marriage, Death."""
    birth_records = Record.query.filter_by(document_type="birth").order_by(Record.created_at.desc()).all()
    marriage_records = Record.query.filter_by(document_type="marriage").order_by(Record.created_at.desc()).all()
    death_records = Record.query.filter_by(document_type="death").order_by(Record.created_at.desc()).all()
    archive_doc_type = _parse_doc_type_filter_arg(request.args.get("doc_type"))
    return render_template(
        "archiving.html",
        birth_records=birth_records,
        marriage_records=marriage_records,
        death_records=death_records,
        document_types=DOCUMENT_TYPES,
        archive_doc_type=archive_doc_type,
        current_user=get_current_user(),
        nav_active="archiving",
    )


@app.route("/record/<int:record_id>/delete", methods=["POST"])
@login_required
def record_delete(record_id):
    """Delete a record (admin only). Removes related edit requests and optionally the stored image."""
    user = get_current_user()
    if not user or (user.role or "").upper() != "ADMIN":
        flash("Only administrators can delete records.")
        return _redirect_archiving()
    record = db.session.get(Record, record_id)
    if not record:
        flash("Record not found.")
        return _redirect_archiving()
    doc_type = record.document_type
    # Remove related rows first. SQLite FKs are NOT NULL with no ON DELETE CASCADE,
    # so deleting the record would otherwise try to null print_logs.record_id.
    for log in PrintLog.query.filter_by(record_id=record_id).all():
        db.session.delete(log)
    for req in PrintRequest.query.filter_by(record_id=record_id).all():
        db.session.delete(req)
    for req in EditRequest.query.filter_by(record_id=record_id).all():
        db.session.delete(req)
    db.session.flush()
    # Optionally remove stored image file
    for path_attr in ("image_path", "image_front_path"):
        rel_path = getattr(record, path_attr, None) or ""
        if rel_path and not rel_path.startswith(".."):
            full_path = _upload_file_path(rel_path)
            if full_path is not None and full_path.exists():
                try:
                    full_path.unlink()
                except OSError:
                    pass
    db.session.delete(record)
    db.session.commit()
    _log_audit(user.id, "RECORD_DELETE", f"record_id={record_id} type={doc_type}")
    flash("Record deleted successfully.", "success")
    return _redirect_archiving()


@app.route("/my-edit-requests")
@login_required
def my_edit_requests():
    """Staff page: list all edit requests submitted by the current user."""
    user = get_current_user()
    if not user or (user.role or "").upper() != "STAFF":
        flash("This page is for staff only.")
        return redirect(url_for("index"))
    request_doc_type = _parse_doc_type_filter_arg(request.args.get("doc_type"))
    requests_q = EditRequest.query.filter_by(requested_by_id=user.id)
    if request_doc_type:
        requests_q = requests_q.join(Record, EditRequest.record_id == Record.id).filter(
            Record.document_type == request_doc_type
        )
    requests_list = requests_q.order_by(EditRequest.requested_at.desc()).all()
    return render_template(
        "my_edit_requests.html",
        current_user=user,
        nav_active="my_edit_requests",
        requests_list=requests_list,
        document_types=DOCUMENT_TYPES,
        request_doc_type=request_doc_type,
    )


@app.route("/my-print-requests")
@login_required
def my_print_requests():
    """Staff page: list all print requests submitted by the current user."""
    user = get_current_user()
    if not user or (user.role or "").upper() != "STAFF":
        flash("This page is for staff only.")
        return redirect(url_for("index"))
    request_doc_type = _parse_doc_type_filter_arg(request.args.get("doc_type"))
    requests_q = PrintRequest.query.filter_by(requested_by_id=user.id)
    if request_doc_type:
        requests_q = requests_q.join(Record, PrintRequest.record_id == Record.id).filter(
            Record.document_type == request_doc_type
        )
    requests_list = requests_q.order_by(PrintRequest.requested_at.desc()).all()
    return render_template(
        "my_print_requests.html",
        current_user=user,
        nav_active="my_print_requests",
        requests_list=requests_list,
        document_types=DOCUMENT_TYPES,
        request_doc_type=request_doc_type,
    )


@app.route("/uploads/<path:path>")
@login_required
def serve_upload(path):
    """Serve uploaded certificate images (e.g. birth/foo.jpg)."""
    rel = _normalize_upload_relpath(path)
    if not rel:
        return ("", 404)
    return send_from_directory(UPLOAD_DIR, rel)


@app.route("/confirm/<doc_type>", methods=["POST"])
@login_required
def confirm(doc_type):
    if doc_type not in DOCUMENT_TYPES:
        return redirect(url_for("index"))

    submitted = _submitted_from_request_form()
    image_filename = submitted.pop("image_filename", None) or request.form.get("image_filename")
    submitted = _normalize_submitted_registry_keys(submitted)
    submitted = apply_annotation_to_data(submitted, annotation_from_form(request.form))

    registry_number = _registry_number_from_submitted(submitted)
    full_name = _full_name_from_data(doc_type, submitted)
    event_date = _event_date_from_data(doc_type, submitted)
    duplicate = _find_duplicate_record(
        doc_type=doc_type,
        registry_number=registry_number,
        full_name=full_name,
        event_date=event_date,
    )
    if duplicate:
        flash(
            f"Save blocked: this document is already archived (Record ID: {duplicate.id}). "
            "Duplicate documents are not allowed."
        )
        return render_template(
            f"form_{doc_type}.html",
            doc_type=doc_type,
            doc_label=DOCUMENT_TYPES[doc_type],
            data=submitted,
            image_filename=image_filename,
            current_user=get_current_user(),
            nav_active="form",
            can_print=user_can_print_during_review(get_current_user()),
        )

    # Auto-rename file for archive: LastName_FirstName_RegistryNumber_birth|marriage|death.ext
    if image_filename and not (Path(image_filename).is_absolute() or ".." in image_filename):
        image_filename = _normalize_upload_relpath(image_filename)
        source_path = _upload_file_path(image_filename)
        if source_path is not None and source_path.exists():
            new_basename = _archive_image_filename(doc_type, full_name, registry_number, image_filename)
            subdir = UPLOAD_DIR / doc_type
            subdir.mkdir(exist_ok=True)
            target_path = subdir / new_basename
            if source_path.resolve() != target_path.resolve():
                try:
                    shutil.copy2(source_path, target_path)
                    image_filename = f"{doc_type}/{new_basename}"
                    # Remove original if it was in temp/ (scan) or a different path
                    if "temp" in str(source_path) or source_path != target_path:
                        try:
                            source_path.unlink()
                        except OSError:
                            pass
                except OSError:
                    pass  # keep original path if rename fails

    data_json_str = json.dumps(submitted, ensure_ascii=False)
    image_front = image_filename or ""
    record = Record(
        document_type=doc_type,
        registry_number=registry_number or None,
        full_name=full_name or None,
        event_date=event_date or None,
        data_json=data_json_str,
        extracted_json=data_json_str,
        corrected_json=data_json_str,
        image_path=image_filename or None,
        image_front_path=image_front,
    )
    db.session.add(record)
    db.session.commit()
    session.pop("last_ocr_job_id", None)

    flash(f"{DOCUMENT_TYPES[doc_type]} data has been saved. View it in Archiving or Search Records.")
    return render_template(
        "confirm.html",
        doc_type=doc_type,
        doc_label=DOCUMENT_TYPES[doc_type],
        data=public_record_fields(submitted),
        image_filename=image_filename or None,
        current_user=get_current_user(),
        nav_active="form",
        record_id=record.id,
    )


def _safe_hash(password: str) -> str:
    return generate_password_hash(password, method="pbkdf2:sha256")


def _migrate_records():
    """Add any missing columns to records table (for DBs created before schema updates)."""
    if not is_sqlite_database(app.config.get("SQLALCHEMY_DATABASE_URI")):
        return
    try:
        r = db.session.execute(db.text("PRAGMA table_info(records)"))
        rows = r.fetchall()
    except Exception:
        return
    existing = {row[1] for row in rows}
    adds = [
        ("event_date", "VARCHAR(32)"),
        ("data_json", "TEXT"),
        ("extracted_json", "TEXT DEFAULT '{}'"),
        ("corrected_json", "TEXT DEFAULT '{}'"),
        ("image_path", "VARCHAR(512)"),
        ("image_front_path", "VARCHAR(512) DEFAULT ''"),
        ("status", "VARCHAR(32) DEFAULT 'archived'"),
        ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
    ]
    for col, typ in adds:
        if col not in existing:
            db.session.execute(db.text(f"ALTER TABLE records ADD COLUMN {col} {typ}"))
            db.session.commit()


def _migrate_edit_requests():
    """Add any missing columns to edit_requests table (for DBs created before schema updates)."""
    if not is_sqlite_database(app.config.get("SQLALCHEMY_DATABASE_URI")):
        return
    try:
        r = db.session.execute(db.text("PRAGMA table_info(edit_requests)"))
        rows = r.fetchall()
    except Exception:
        return
    existing = {row[1] for row in rows}
    adds = [
        ("record_id", "INTEGER NOT NULL"),
        ("requested_by_id", "INTEGER NOT NULL"),
        ("status", "VARCHAR(32) DEFAULT 'PENDING'"),
        ("reason", "TEXT DEFAULT ''"),
        ("fields_requested", "VARCHAR(512) DEFAULT ''"),
        ("requested_at", "DATETIME"),
        ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ("reviewed_at", "DATETIME"),
        ("reviewed_by_id", "INTEGER"),
        ("approval_code", "VARCHAR(10) DEFAULT ''"),
        ("code_used_at", "DATETIME"),
        ("rejection_reason", "TEXT DEFAULT ''"),
        ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
    ]
    for col, typ in adds:
        if col not in existing:
            db.session.execute(db.text(f"ALTER TABLE edit_requests ADD COLUMN {col} {typ}"))
            db.session.commit()


def _migrate_print_requests():
    """Add any missing columns to print_requests table (for DBs created before schema updates)."""
    if not is_sqlite_database(app.config.get("SQLALCHEMY_DATABASE_URI")):
        return
    try:
        r = db.session.execute(db.text("PRAGMA table_info(print_requests)"))
        rows = r.fetchall()
    except Exception:
        return
    existing = {row[1] for row in rows}
    adds = [
        ("record_id", "INTEGER NOT NULL"),
        ("requested_by_id", "INTEGER NOT NULL"),
        ("status", "VARCHAR(32) DEFAULT 'PENDING'"),
        ("reason", "TEXT DEFAULT ''"),
        ("requested_at", "DATETIME"),
        ("reviewed_at", "DATETIME"),
        ("reviewed_by_id", "INTEGER"),
        ("rejection_reason", "TEXT DEFAULT ''"),
        ("used_at", "DATETIME"),
        ("print_format", "VARCHAR(32) DEFAULT 'original'"),
    ]
    for col, typ in adds:
        if col not in existing:
            db.session.execute(db.text(f"ALTER TABLE print_requests ADD COLUMN {col} {typ}"))
            db.session.commit()


def _bootstrap_users():
    with app.app_context():
        db.create_all()
        try:
            _migrate_records()
        except Exception:
            pass
        try:
            _migrate_edit_requests()
        except Exception:
            pass
        try:
            _migrate_print_requests()
        except Exception:
            pass
        default_passwords = [
            ("admin", "admin123", "ADMIN"),
            ("staff", "staff123", "STAFF"),
        ]
        for username, password, role in default_passwords:
            user = User.query.filter_by(username=username).first()
            if user:
                continue
            db.session.add(
                User(
                    username=username,
                    password_hash=_safe_hash(password),
                    role=role,
                )
            )
        db.session.commit()


def _set_console_title(title: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


def _print_startup_banner(host: str, port: int) -> None:
    local_url = f"http://127.0.0.1:{port}"
    line = "=" * 62
    print(line, flush=True)
    print("  MUNICIPALITY OF DARAGA (LOCSIN), ALBAY", flush=True)
    print("  Office of the Municipal Civil Registrar", flush=True)
    print("  Civil Registry Management System", flush=True)
    print("-" * 62, flush=True)
    print("  Status   Ready", flush=True)
    print(f"  Open     {local_url}", flush=True)
    print("  Stop     Press Ctrl+C", flush=True)
    print(line, flush=True)
    print("", flush=True)


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
    _set_console_title("Daraga Civil Registry")
    _host = "0.0.0.0"
    _port = 5001
    _use_reloader = os.environ.get("FLASK_USE_RELOADER", "").strip().lower() in ("1", "true", "yes")
    _print_startup_banner(_host, _port)
    _bootstrap_users()
    init_auto_backup_scheduler(
        app,
        base_dir=BASE_DIR,
        upload_dir=UPLOAD_DIR,
        include_sqlite_db=lambda: is_sqlite_database(app.config.get("SQLALCHEMY_DATABASE_URI")),
        audit_callback=_auto_backup_audit,
    )

    def _warmup_ocr_engine():
        try:
            from ocr.shared import warmup_ocr
            warmup_ocr()
        except Exception:
            pass

    threading.Thread(target=_warmup_ocr_engine, daemon=True, name="ocr-warmup").start()
    try:
        import flask.cli as flask_cli
        flask_cli.show_server_banner = lambda *args, **kwargs: None
    except Exception:
        pass
    try:
        app.run(host=_host, port=_port, debug=True, use_reloader=_use_reloader)
    except KeyboardInterrupt:
        print("\nDaraga Civil Registry stopped.", flush=True)
        os._exit(0)
