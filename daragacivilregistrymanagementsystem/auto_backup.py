"""Automatic full-system backup scheduler (daily / weekly / monthly / yearly)."""
from __future__ import annotations

import json
import logging
import os
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

SETTINGS_FILENAME = "auto_backup_settings.json"
AUTO_BACKUP_SUBDIR = "auto"
JOB_ID = "auto_full_backup"

DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "frequency": "daily",  # daily | weekly | monthly | yearly
    "time": "02:00",
    "weekday": 6,  # 0=Monday … 6=Sunday (APScheduler)
    "day_of_month": 1,
    "month": 1,
    "retain_count": 10,
    "last_run_at": "",
    "last_run_status": "",
    "last_run_message": "",
    "last_run_file": "",
}

VALID_FREQUENCIES = frozenset({"daily", "weekly", "monthly", "yearly"})

_scheduler = None
_scheduler_lock = threading.Lock()
_runtime: dict[str, Any] = {}


def settings_path(base_dir: Path) -> Path:
    return base_dir / "backups" / SETTINGS_FILENAME


def auto_backup_dir(base_dir: Path) -> Path:
    path = base_dir / "backups" / AUTO_BACKUP_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_settings(base_dir: Path) -> dict[str, Any]:
    path = settings_path(base_dir)
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        merged.update(data)
    return _normalize_settings(merged)


def save_settings(base_dir: Path, settings: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_settings(settings)
    path = settings_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    return normalized


def _normalize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    out.update(settings or {})
    out["enabled"] = bool(out.get("enabled"))
    freq = str(out.get("frequency") or "daily").strip().lower()
    out["frequency"] = freq if freq in VALID_FREQUENCIES else "daily"
    out["time"] = _parse_time(str(out.get("time") or "02:00"))
    try:
        out["weekday"] = max(0, min(6, int(out.get("weekday", 6))))
    except (TypeError, ValueError):
        out["weekday"] = 6
    try:
        out["day_of_month"] = max(1, min(28, int(out.get("day_of_month", 1))))
    except (TypeError, ValueError):
        out["day_of_month"] = 1
    try:
        out["month"] = max(1, min(12, int(out.get("month", 1))))
    except (TypeError, ValueError):
        out["month"] = 1
    try:
        out["retain_count"] = max(1, min(100, int(out.get("retain_count", 10))))
    except (TypeError, ValueError):
        out["retain_count"] = 10
    for key in ("last_run_at", "last_run_status", "last_run_message", "last_run_file"):
        out[key] = str(out.get(key) or "").strip()
    return out


def _parse_time(value: str) -> str:
    raw = (value or "02:00").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.strftime("%H:%M")
        except ValueError:
            continue
    return "02:00"


def _time_parts(settings: dict[str, Any]) -> tuple[int, int]:
    parsed = datetime.strptime(settings["time"], "%H:%M")
    return parsed.hour, parsed.minute


def write_full_backup_zip(
    dest_path: Path,
    *,
    base_dir: Path,
    upload_dir: Path,
    include_sqlite_db: bool = True,
) -> None:
    """Write a full backup zip (database + uploads) to dest_path."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    db_path = base_dir / "civil_registry.db"
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if include_sqlite_db and db_path.exists():
            zf.write(db_path, "civil_registry.db")
        elif not include_sqlite_db:
            zf.writestr(
                "DATABASE_NOTE.txt",
                "This zip does not include a database dump. The app is using a server database "
                "(e.g. PostgreSQL). Use pg_dump or your host's backup tools for the database; "
                "this archive contains uploads only.\n",
            )
        if upload_dir.exists():
            for root, _dirs, files in os.walk(upload_dir):
                for fname in files:
                    full = Path(root) / fname
                    arcname = full.relative_to(base_dir)
                    zf.write(full, str(arcname).replace("\\", "/"))


def resolve_auto_backup_path(base_dir: Path, filename: str) -> tuple[Optional[Path], Optional[str]]:
    """Validate backup filename and return path under backups/auto/, or an error message."""
    safe_name = Path(filename).name
    if not safe_name.lower().endswith(".zip") or safe_name != filename:
        return None, "Invalid backup file."
    folder = auto_backup_dir(base_dir).resolve()
    full_path = (folder / safe_name).resolve()
    try:
        full_path.relative_to(folder)
    except ValueError:
        return None, "Invalid backup file."
    if not full_path.is_file():
        return None, "Backup file not found."
    return full_path, None


def delete_auto_backup(base_dir: Path, filename: str) -> tuple[bool, str]:
    """Delete one automatic backup zip. Clears last_run_file in settings if it pointed at this file."""
    path, err = resolve_auto_backup_path(base_dir, filename)
    if err:
        return False, err
    try:
        path.unlink()
    except OSError as exc:
        logger.warning("Could not delete auto-backup %s: %s", path, exc)
        return False, f"Could not delete backup: {exc}"

    settings = load_settings(base_dir)
    rel = f"{AUTO_BACKUP_SUBDIR}/{path.name}"
    if settings.get("last_run_file") in (rel, path.name):
        settings["last_run_file"] = ""
        save_settings(base_dir, settings)
    return True, path.name


def list_auto_backups(base_dir: Path, limit: int = 15) -> list[dict[str, Any]]:
    folder = auto_backup_dir(base_dir)
    items: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
        )
        if len(items) >= limit:
            break
    return items


def _cleanup_old_backups(base_dir: Path, retain_count: int) -> None:
    folder = auto_backup_dir(base_dir)
    backups = sorted(folder.glob("civil_registry_full_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[retain_count:]:
        try:
            old.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete old auto-backup %s: %s", old, exc)


def run_auto_backup(
    *,
    base_dir: Path,
    upload_dir: Path,
    include_sqlite_db: bool,
    audit_callback: Optional[Callable[[str, str], None]] = None,
    trigger: str = "schedule",
) -> tuple[bool, str, str]:
    """
    Create an automatic full backup on disk.
    Returns (success, message, relative_filename).
    """
    settings = load_settings(base_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"civil_registry_full_backup_{timestamp}.zip"
    dest = auto_backup_dir(base_dir) / filename

    try:
        write_full_backup_zip(
            dest,
            base_dir=base_dir,
            upload_dir=upload_dir,
            include_sqlite_db=include_sqlite_db,
        )
        rel_file = f"{AUTO_BACKUP_SUBDIR}/{filename}"
        _cleanup_old_backups(base_dir, settings.get("retain_count", 10))
        settings["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        settings["last_run_status"] = "success"
        settings["last_run_message"] = f"Automatic backup saved ({trigger})."
        settings["last_run_file"] = rel_file
        save_settings(base_dir, settings)
        if audit_callback:
            audit_callback("AUTO_BACKUP", f"trigger={trigger} file={filename}")
        return True, settings["last_run_message"], rel_file
    except Exception as exc:
        logger.exception("Automatic backup failed")
        settings["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        settings["last_run_status"] = "error"
        settings["last_run_message"] = str(exc)
        settings["last_run_file"] = ""
        save_settings(base_dir, settings)
        if audit_callback:
            audit_callback("AUTO_BACKUP_FAILED", f"trigger={trigger} error={exc}")
        return False, str(exc), ""


def _build_cron_trigger(settings: dict[str, Any]):
    from apscheduler.triggers.cron import CronTrigger

    hour, minute = _time_parts(settings)
    freq = settings["frequency"]
    if freq == "daily":
        return CronTrigger(hour=hour, minute=minute)
    if freq == "weekly":
        return CronTrigger(day_of_week=settings["weekday"], hour=hour, minute=minute)
    if freq == "monthly":
        return CronTrigger(day=settings["day_of_month"], hour=hour, minute=minute)
    return CronTrigger(month=settings["month"], day=settings["day_of_month"], hour=hour, minute=minute)


def apply_schedule(app) -> None:
    """Reload scheduler job from saved settings."""
    global _scheduler
    if _scheduler is None:
        return

    base_dir = _runtime["base_dir"]
    settings = load_settings(base_dir)

    if _scheduler.get_job(JOB_ID):
        _scheduler.remove_job(JOB_ID)

    if not settings.get("enabled"):
        logger.info("Automatic backup is disabled.")
        return

    trigger = _build_cron_trigger(settings)

    def _job():
        with app.app_context():
            run_auto_backup(
                base_dir=_runtime["base_dir"],
                upload_dir=_runtime["upload_dir"],
                include_sqlite_db=_runtime["include_sqlite_db"](),
                audit_callback=_runtime.get("audit_callback"),
                trigger="schedule",
            )

    _scheduler.add_job(_job, trigger=trigger, id=JOB_ID, replace_existing=True)
    logger.info(
        "Automatic backup scheduled: frequency=%s time=%s",
        settings["frequency"],
        settings["time"],
    )


def init_auto_backup_scheduler(
    app,
    *,
    base_dir: Path,
    upload_dir: Path,
    include_sqlite_db: Callable[[], bool],
    audit_callback: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Start background scheduler (call once when the app starts)."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            apply_schedule(app)
            return

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            logger.warning("APScheduler is not installed; automatic backup is unavailable.")
            return

        _runtime["base_dir"] = base_dir
        _runtime["upload_dir"] = upload_dir
        _runtime["include_sqlite_db"] = include_sqlite_db
        _runtime["audit_callback"] = audit_callback

        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.start()
        apply_schedule(app)


def settings_from_form(form, base_dir: Path) -> dict[str, Any]:
    """Build settings dict from an HTML form."""
    current = load_settings(base_dir)
    current["enabled"] = (form.get("auto_backup_enabled") or "").strip().lower() in ("1", "true", "on", "yes")
    freq = (form.get("auto_backup_frequency") or "daily").strip().lower()
    current["frequency"] = freq if freq in VALID_FREQUENCIES else "daily"
    current["time"] = _parse_time(form.get("auto_backup_time") or "02:00")
    try:
        current["weekday"] = int(form.get("auto_backup_weekday") or 6)
    except ValueError:
        current["weekday"] = 6
    try:
        current["day_of_month"] = int(form.get("auto_backup_day") or 1)
    except ValueError:
        current["day_of_month"] = 1
    try:
        current["month"] = int(form.get("auto_backup_month") or 1)
    except ValueError:
        current["month"] = 1
    try:
        current["retain_count"] = int(form.get("auto_backup_retain") or 10)
    except ValueError:
        current["retain_count"] = 10
    return _normalize_settings(current)


def frequency_label(frequency: str) -> str:
    labels = {
        "daily": "Every day",
        "weekly": "Every week",
        "monthly": "Every month",
        "yearly": "Every year",
    }
    return labels.get(frequency, frequency)
