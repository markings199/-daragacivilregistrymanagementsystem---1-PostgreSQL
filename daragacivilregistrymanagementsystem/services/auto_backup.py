"""Automatic full-system backup scheduler (daily / weekly / monthly / yearly)."""
from __future__ import annotations

import json
import logging
import os
import csv
import shutil
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

SETTINGS_FILENAME = "auto_backup_settings.json"
AUTO_BACKUP_SUBDIR = "auto"
JOB_ID = "auto_full_backup"

DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "daily_enabled": True,
    "monthly_enabled": True,
    "yearly_enabled": True,
    "full_enabled": True,
    "daily_time": "20:00",
    "monthly_time": "20:00",
    "yearly_time": "20:00",
    "full_time": "20:05",
    "frequency": "daily",
    "time": "20:00",
    "weekday": 6,
    "day_of_month": 28,
    "month": 12,
    "retain_count": 10,
    "destination_path": "",
    "last_run_at": "",
    "last_run_status": "",
    "last_run_message": "",
    "last_run_file": "",
}

VALID_FREQUENCIES = frozenset({"daily", "weekly", "monthly", "yearly"})
PERIOD_KINDS = frozenset({"daily", "monthly", "yearly"})
MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
JOB_DAILY = "auto_period_backup_daily"
JOB_MONTHLY = "auto_period_backup_monthly"
JOB_YEARLY = "auto_period_backup_yearly"


def daily_backup_stamp(when: Optional[datetime] = None) -> str:
    """Calendar day used in backup filenames, e.g. 2026-09-01."""
    return (when or datetime.now()).strftime("%Y-%m-%d")


def daily_full_backup_filename(when: Optional[datetime] = None) -> str:
    return f"civil_registry_full_backup_{daily_backup_stamp(when)}.zip"

_scheduler = None
_scheduler_lock = threading.Lock()
_runtime: dict[str, Any] = {}


def settings_path(base_dir: Path) -> Path:
    return base_dir / "backups" / SETTINGS_FILENAME


def env_backup_root() -> str:
    return (os.environ.get("DARAGA_BACKUP_ROOT") or os.environ.get("BACKUP_ROOT") or "").strip().strip('"').strip("'")


def local_backup_root(base_dir: Path) -> Path:
    """Always-on copy on this system: backups/Year/Month/Day."""
    path = base_dir / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def auto_backup_dir(base_dir: Path) -> Path:
    """Local folder for optional full-system zip downloads."""
    path = local_backup_root(base_dir) / "Full"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_server_backup_root(
    base_dir: Path, settings: Optional[dict[str, Any]] = None
) -> tuple[Optional[Path], Optional[str]]:
    """Optional second copy on the Daraga Civil Registry server. Empty path means 'not set yet'."""
    settings = settings if settings is not None else load_settings(base_dir)
    raw = env_backup_root() or str(settings.get("destination_path") or "").strip().strip('"').strip("'")
    if not raw:
        return None, None
    if raw.startswith("//"):
        raw = "\\\\" + raw[2:].replace("/", "\\")
    path = Path(raw)
    if not (raw.startswith("\\\\") or path.is_absolute()):
        return None, (
            "Use a full server path such as \\\\SERVERNAME\\CivilRegistryBackups."
        )
    app_root = base_dir.resolve()
    try:
        candidate = path if raw.startswith("\\\\") else path.resolve()
        candidate.relative_to(app_root)
        return None, (
            "That folder is already this system. Enter the LGU server share to keep a second copy at Daraga Civil Registry."
        )
    except (ValueError, OSError):
        pass
    return path, None


def _norm_dest_text(value: str) -> str:
    return (value or "").strip().strip('"').strip("'").replace("/", "\\").rstrip("\\").lower()


def _is_backup_tree_folder(name: str) -> bool:
    n = (name or "").lower()
    if n in {"backups", "full", "monthly", "yearly"}:
        return True
    if n in {m.lower() for m in MONTH_NAMES}:
        return True
    return n.isdigit() and len(n) == 4


def relative_path_on_server(server_root: Path, relative: str) -> Path:
    """Map a local backup relative path onto the server without nesting duplicate folders."""
    parts = [p for p in Path(str(relative).replace("\\", "/")).parts if p not in ("", ".")]
    while len(parts) >= 2 and parts[0].lower() == "backups" and parts[1].lower() == "backups":
        parts = parts[1:]
    if parts and parts[0].lower() == "backups" and server_root.name.lower() == "backups":
        parts = parts[1:]
    if parts and _is_backup_tree_folder(parts[0]) and parts[0].lower() == server_root.name.lower():
        parts = parts[1:]
    return Path(*parts) if parts else Path(Path(str(relative).replace("\\", "/")).name)


def backup_storage_dir(base_dir: Path, settings: Optional[dict[str, Any]] = None) -> Path:
    """Primary automatic archive root on this system."""
    return local_backup_root(base_dir)


def backup_storage_display(base_dir: Path, settings: Optional[dict[str, Any]] = None) -> str:
    return str(local_backup_root(base_dir))


def server_backup_display(base_dir: Path, settings: Optional[dict[str, Any]] = None) -> str:
    path, err = resolve_server_backup_root(base_dir, settings)
    if err:
        return err
    if path is None:
        return "Not set"
    return str(path)


def ensure_backup_dir_writable(folder: Path) -> Optional[str]:
    """Create the folder and confirm this computer can write to it. Returns an error string or None."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".civil_registry_backup_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return (
            f"Cannot save the second copy to {folder}. "
            "Check that the Daraga Civil Registry server is on, the folder is shared, "
            f"and this computer can reach it. Backups will still be saved on this system. ({exc})"
        )
    return None


def copy_zip_to_server(
    source: Path,
    relative: str,
    base_dir: Path,
    *,
    force: bool = False,
    settings: Optional[dict[str, Any]] = None,
) -> str:
    """Copy a local zip to the same relative path on the LGU server, if configured."""
    server_root, server_err = resolve_server_backup_root(base_dir, settings)
    if server_err:
        return f" Server copy was not made: {server_err}"
    if server_root is None:
        return ""
    try:
        server_dest = server_root / relative_path_on_server(server_root, relative)
        if server_dest.exists() and server_dest.is_dir():
            return f" Server copy was not made: a folder already exists at {server_dest}."
        server_dest.parent.mkdir(parents=True, exist_ok=True)
        if server_dest.exists() and not force:
            return f" Also kept on the LGU server at {server_dest}."
        shutil.copy2(source, server_dest)
        return f" Also saved on the LGU server at {server_dest}."
    except OSError as exc:
        logger.warning("Could not copy backup to LGU server: %s", exc)
        return f" Saved on this system, but the LGU server copy failed: {exc}"


def sync_local_backups_to_server(base_dir: Path) -> tuple[int, int, Optional[str]]:
    """Copy existing local backup zips to the LGU server. Returns (copied, failed, error)."""
    server_root, err = resolve_server_backup_root(base_dir)
    if err:
        return 0, 0, err
    if server_root is None:
        return 0, 0, None
    local = local_backup_root(base_dir)
    copied = 0
    failed = 0
    for path in local.rglob("*.zip"):
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(local)).replace("\\", "/")
        except ValueError:
            continue
        extra = copy_zip_to_server(path, rel, base_dir, force=False)
        if "failed" in extra.lower() or "was not made" in extra.lower():
            failed += 1
        elif "Also saved" in extra:
            copied += 1
    return copied, failed, None


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
    dest = str(out.get("destination_path") or "").strip().strip('"').strip("'")
    if "\x00" in dest:
        dest = ""
    out["destination_path"] = dest[:1024]
    out["daily_enabled"] = bool(out.get("daily_enabled", True))
    out["monthly_enabled"] = bool(out.get("monthly_enabled", True))
    out["yearly_enabled"] = bool(out.get("yearly_enabled", True))
    out["full_enabled"] = bool(out.get("full_enabled", True))
    out["daily_time"] = _parse_time(str(out.get("daily_time") or out.get("time") or "20:00"))
    out["monthly_time"] = _parse_time(str(out.get("monthly_time") or "20:00"))
    out["yearly_time"] = _parse_time(str(out.get("yearly_time") or "20:00"))
    out["full_time"] = _parse_time(str(out.get("full_time") or "20:05"))
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


def _time_parts_value(value: str) -> tuple[int, int]:
    parsed = datetime.strptime(_parse_time(value), "%H:%M")
    return parsed.hour, parsed.minute


def _time_parts(settings: dict[str, Any]) -> tuple[int, int]:
    return _time_parts_value(str(settings.get("time") or "20:00"))


def _local_tz():
    return datetime.now().astimezone().tzinfo


def _naive_local_to_utc_naive(dt: datetime) -> datetime:
    aware = dt.replace(tzinfo=_local_tz())
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def period_bounds(kind: str, when: Optional[datetime] = None) -> tuple[datetime, datetime, str]:
    """Return UTC-naive [start, end) and a period key for local office dates."""
    now = when or datetime.now()
    kind = (kind or "daily").strip().lower()
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "monthly":
        start_local = start_local.replace(day=1)
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
        period_key = start_local.strftime("%Y-%m")
    elif kind == "yearly":
        start_local = start_local.replace(month=1, day=1)
        end_local = start_local.replace(year=start_local.year + 1)
        period_key = start_local.strftime("%Y")
    else:
        end_local = start_local + timedelta(days=1)
        period_key = start_local.strftime("%Y-%m-%d")
    return _naive_local_to_utc_naive(start_local), _naive_local_to_utc_naive(end_local), period_key


def period_folder(root: Path, kind: str, when: datetime) -> Path:
    year = str(when.year)
    month_name = MONTH_NAMES[when.month - 1]
    if kind == "monthly":
        return root / year / "Monthly" / month_name
    if kind == "yearly":
        return root / year / "Yearly"
    return root / year / month_name / f"{month_name}-{when.strftime('%d')}"


def period_filename(kind: str, period_key: str) -> str:
    return f"civil_registry_{kind}_{period_key}.zip"


def _record_to_manifest(record) -> dict[str, Any]:
    created = getattr(record, "created_at", None)
    return {
        "id": record.id,
        "document_type": record.document_type or "",
        "registry_number": record.registry_number or "",
        "full_name": record.full_name or "",
        "event_date": record.event_date or "",
        "created_at": created.strftime("%Y-%m-%d %H:%M") if created else "",
        "image_path": record.image_path or "",
    }


def write_period_documents_zip(dest_path: Path, records: list[Any], resolve_upload: Callable[[str], Optional[Path]]) -> int:
    """Copy scanned files for the given records into a zip. Does not change originals."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    copied = 0
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest_rows = []
        seen = set()
        for record in records:
            manifest_rows.append(_record_to_manifest(record))
            for attr in ("image_path", "image_front_path"):
                rel = (getattr(record, attr, None) or "").strip()
                if not rel:
                    continue
                full = resolve_upload(rel)
                if full is None or not full.is_file():
                    continue
                arcname = f"documents/{record.id}_{full.name}"
                if arcname in seen:
                    arcname = f"documents/{record.id}_{attr}_{full.name}"
                seen.add(arcname)
                zf.write(full, arcname)
                copied += 1
        buf = StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=["id", "document_type", "registry_number", "full_name", "event_date", "created_at", "image_path"],
        )
        writer.writeheader()
        writer.writerows(manifest_rows)
        zf.writestr("manifest.csv", buf.getvalue())
        zf.writestr(
            "README.txt",
            "Date-based document backup. Original records in the system were not changed.\n",
        )
    return copied


def _save_backup_run(*, kind: str, period_key: str, status: str, file_rel: str, record_count: int, message: str) -> None:
    from models import BackupRun, db

    row = BackupRun(
        kind=kind,
        period_key=period_key,
        status=status,
        file_rel=file_rel or "",
        record_count=int(record_count or 0),
        message=message or "",
        created_at=datetime.utcnow(),
    )
    db.session.add(row)
    db.session.commit()


def list_backup_history(limit: int = 40) -> list[dict[str, Any]]:
    from models import BackupRun

    rows = BackupRun.query.order_by(BackupRun.created_at.desc()).limit(limit).all()
    items = []
    for row in rows:
        items.append(
            {
                "id": row.id,
                "kind": row.kind,
                "period_key": row.period_key,
                "status": row.status,
                "file_rel": row.file_rel or "",
                "record_count": row.record_count or 0,
                "message": row.message or "",
                "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "",
            }
        )
    return items


def delete_backup_run(base_dir: Path, run_id: int) -> tuple[bool, str]:
    """Delete a history row and its zip on this system and the LGU server. Original records are not changed."""
    from models import BackupRun, db

    row = db.session.get(BackupRun, run_id)
    if row is None:
        return False, "Backup history entry not found."
    rel = (row.file_rel or "").replace("\\", "/").strip().lstrip("/")
    kind = (row.kind or "backup").strip()
    period = row.period_key or ""
    file_errors: list[str] = []
    if rel and ".." not in rel.split("/") and rel.lower().endswith(".zip"):
        roots = [local_backup_root(base_dir)]
        server_root, _ = resolve_server_backup_root(base_dir)
        if server_root is not None:
            roots.append(server_root)
        for root in roots:
            full = root / Path(rel)
            try:
                full.relative_to(root)
            except ValueError:
                continue
            if not full.is_file():
                continue
            try:
                full.unlink()
            except OSError as exc:
                logger.warning("Could not delete backup file %s: %s", full, exc)
                file_errors.append(str(full))
    db.session.delete(row)
    db.session.commit()
    settings = load_settings(base_dir)
    if rel and settings.get("last_run_file") == rel:
        settings["last_run_file"] = ""
        save_settings(base_dir, settings)
    label = f"{kind} {period}".strip()
    if file_errors:
        return True, f'History "{label}" was removed, but some zip files could not be deleted.'
    return True, f'Backup "{label}" was deleted.'


def resolve_period_backup_path(base_dir: Path, file_rel: str) -> tuple[Optional[Path], Optional[str]]:
    rel = (file_rel or "").replace("\\", "/").strip().lstrip("/")
    if not rel or ".." in rel.split("/") or not rel.lower().endswith(".zip"):
        return None, "Invalid backup file."
    roots = [local_backup_root(base_dir)]
    server_root, _ = resolve_server_backup_root(base_dir)
    if server_root is not None:
        roots.append(server_root)
    for root in roots:
        full = root / Path(rel)
        try:
            full.relative_to(root)
        except ValueError:
            continue
        if full.is_file():
            return full, None
    return None, "Backup file not found on this system or the LGU server folder."


def run_period_backup(
    *,
    kind: str,
    base_dir: Path,
    force: bool = False,
    trigger: str = "schedule",
    when: Optional[datetime] = None,
    audit_callback: Optional[Callable[[str, str], None]] = None,
) -> tuple[bool, str, str]:
    """Back up only documents added in the local daily/monthly/yearly window. Never edits records."""
    kind = (kind or "daily").strip().lower()
    if kind not in PERIOD_KINDS:
        kind = "daily"
    now = when or datetime.now()
    start_utc, end_utc, period_key = period_bounds(kind, now)
    local_root = local_backup_root(base_dir)
    filename = period_filename(kind, period_key)
    folder = period_folder(local_root, kind, now)
    dest = folder / filename
    try:
        rel = str(dest.relative_to(local_root)).replace("\\", "/")
    except ValueError:
        rel = filename

    try:
        if dest.exists() and not force:
            extra = copy_zip_to_server(dest, rel, base_dir, force=force)
            msg = (
                f"{kind.title()} backup for {period_key} already exists on this system."
                f"{extra} Original documents were left unchanged."
            )
            from models import BackupRun
            last = (
                BackupRun.query.filter_by(kind=kind, period_key=period_key)
                .order_by(BackupRun.created_at.desc())
                .first()
            )
            if last is None or last.status == "error":
                _save_backup_run(kind=kind, period_key=period_key, status="skipped", file_rel=rel, record_count=0, message=msg)
            return True, msg, rel

        from models import Record

        records = (
            Record.query.filter(Record.created_at >= start_utc, Record.created_at < end_utc)
            .order_by(Record.created_at.asc())
            .all()
        )
        resolve_upload = _runtime.get("resolve_upload")
        if not callable(resolve_upload):
            raise RuntimeError("Backup file resolver is not ready. Restart the application.")

        write_period_documents_zip(dest, records, resolve_upload)
        extra = copy_zip_to_server(dest, rel, base_dir, force=force)
        msg = (
            f"{kind.title()} backup saved on this system ({trigger}): "
            f"{len(records)} document(s) for {period_key} at {dest}.{extra}"
        )
        _save_backup_run(
            kind=kind,
            period_key=period_key,
            status="success",
            file_rel=rel,
            record_count=len(records),
            message=msg,
        )
        settings = load_settings(base_dir)
        settings["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        settings["last_run_status"] = "success"
        settings["last_run_message"] = msg
        settings["last_run_file"] = rel
        save_settings(base_dir, settings)
        if audit_callback:
            audit_callback("AUTO_BACKUP", f"kind={kind} period={period_key} records={len(records)} file={rel}")
        return True, msg, rel
    except Exception as exc:
        logger.exception("Date-based backup failed")
        settings = load_settings(base_dir)
        settings["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        settings["last_run_status"] = "error"
        settings["last_run_message"] = str(exc)
        settings["last_run_file"] = ""
        save_settings(base_dir, settings)
        try:
            _save_backup_run(kind=kind, period_key=period_key, status="error", file_rel="", record_count=0, message=str(exc))
        except Exception:
            logger.exception("Could not write backup history")
        if audit_callback:
            audit_callback("AUTO_BACKUP_FAILED", f"kind={kind} period={period_key} error={exc}")
        return False, str(exc), ""


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
            nested_uploads = (upload_dir / "uploads").resolve()
            for root, dirs, files in os.walk(upload_dir):
                root_path = Path(root).resolve()
                dirs[:] = [d for d in dirs if (root_path / d).resolve() != nested_uploads]
                if root_path == nested_uploads:
                    continue
                for fname in files:
                    full = Path(root) / fname
                    try:
                        arcname = full.relative_to(base_dir)
                    except ValueError:
                        continue
                    parts = Path(str(arcname)).parts
                    if len(parts) >= 2 and parts[0] == "uploads" and parts[1] == "uploads":
                        continue
                    zf.write(full, str(arcname).replace("\\", "/"))


def run_full_backup(
    *,
    base_dir: Path,
    force: bool = False,
    trigger: str = "schedule",
    when: Optional[datetime] = None,
    audit_callback: Optional[Callable[[str, str], None]] = None,
) -> tuple[bool, str, str]:
    """Save a full system zip (database + scans) on this computer and copy it to the LGU server."""
    now = when or datetime.now()
    period_key = daily_backup_stamp(now)
    local_root = local_backup_root(base_dir)
    dest = auto_backup_dir(base_dir) / daily_full_backup_filename(now)
    try:
        rel = str(dest.relative_to(local_root)).replace("\\", "/")
    except ValueError:
        rel = f"Full/{dest.name}"
    include_fn = _runtime.get("include_sqlite_db")
    include_sqlite_db = bool(include_fn()) if callable(include_fn) else True
    upload_dir = _runtime.get("upload_dir") or (base_dir / "uploads")

    try:
        if dest.exists() and not force:
            extra = copy_zip_to_server(dest, rel, base_dir, force=force)
            msg = f"Full backup for {period_key} already exists on this system.{extra}"
            from models import BackupRun
            last = (
                BackupRun.query.filter_by(kind="full", period_key=period_key)
                .order_by(BackupRun.created_at.desc())
                .first()
            )
            if last is None or last.status == "error":
                _save_backup_run(kind="full", period_key=period_key, status="skipped", file_rel=rel, record_count=0, message=msg)
            return True, msg, rel

        from models import Record

        write_full_backup_zip(
            dest,
            base_dir=base_dir,
            upload_dir=Path(upload_dir),
            include_sqlite_db=include_sqlite_db,
        )
        extra = copy_zip_to_server(dest, rel, base_dir, force=True)
        count = Record.query.count()
        msg = f"Full backup saved on this system ({trigger}) at {dest}.{extra}"
        _save_backup_run(
            kind="full",
            period_key=period_key,
            status="success",
            file_rel=rel,
            record_count=count,
            message=msg,
        )
        settings = load_settings(base_dir)
        settings["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        settings["last_run_status"] = "success"
        settings["last_run_message"] = msg
        settings["last_run_file"] = rel
        save_settings(base_dir, settings)
        _cleanup_old_backups(base_dir, int(settings.get("retain_count") or 10))
        if audit_callback:
            audit_callback("AUTO_BACKUP", f"kind=full period={period_key} file={rel}")
        return True, msg, rel
    except Exception as exc:
        logger.exception("Full backup failed")
        settings = load_settings(base_dir)
        settings["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        settings["last_run_status"] = "error"
        settings["last_run_message"] = str(exc)
        settings["last_run_file"] = ""
        save_settings(base_dir, settings)
        try:
            _save_backup_run(kind="full", period_key=period_key, status="error", file_rel="", record_count=0, message=str(exc))
        except Exception:
            logger.exception("Could not record full backup failure")
        if audit_callback:
            audit_callback("AUTO_BACKUP_FAILED", f"kind=full error={exc}")
        return False, str(exc), ""


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
    kind: str = "daily",
    force: bool = False,
) -> tuple[bool, str, str]:
    """Run a date-based document backup or a full system zip. Original records are never changed."""
    if (kind or "").strip().lower() == "full":
        return run_full_backup(
            base_dir=base_dir,
            force=force,
            trigger=trigger,
            audit_callback=audit_callback,
        )
    return run_period_backup(
        kind=kind,
        base_dir=base_dir,
        force=force,
        trigger=trigger,
        audit_callback=audit_callback,
    )


def apply_schedule(app) -> None:
    """Reload daily, monthly, and yearly jobs from saved settings."""
    global _scheduler
    if _scheduler is None:
        return

    from apscheduler.triggers.cron import CronTrigger

    base_dir = _runtime["base_dir"]
    settings = load_settings(base_dir)

    for job_id in (JOB_ID, JOB_DAILY, JOB_MONTHLY, JOB_YEARLY):
        if _scheduler.get_job(job_id):
            _scheduler.remove_job(job_id)

    if not settings.get("enabled"):
        logger.info("Automatic backup is disabled.")
        return

    def _make_job(kind: str):
        def _job():
            with app.app_context():
                run_auto_backup(
                    base_dir=_runtime["base_dir"],
                    upload_dir=_runtime["upload_dir"],
                    include_sqlite_db=bool(_runtime["include_sqlite_db"]()) if callable(_runtime.get("include_sqlite_db")) else True,
                    audit_callback=_runtime.get("audit_callback"),
                    trigger="schedule",
                    kind=kind,
                )
        return _job

    if settings.get("daily_enabled", True):
        hour, minute = _time_parts_value(str(settings.get("daily_time") or "20:00"))
        _scheduler.add_job(_make_job("daily"), CronTrigger(hour=hour, minute=minute), id=JOB_DAILY, replace_existing=True)
    if settings.get("monthly_enabled", True):
        hour, minute = _time_parts_value(str(settings.get("monthly_time") or "20:00"))
        day = int(settings.get("day_of_month") or 28)
        _scheduler.add_job(
            _make_job("monthly"),
            CronTrigger(day=day, hour=hour, minute=minute),
            id=JOB_MONTHLY,
            replace_existing=True,
        )
    if settings.get("yearly_enabled", True):
        hour, minute = _time_parts_value(str(settings.get("yearly_time") or "20:00"))
        month = int(settings.get("month") or 12)
        day = int(settings.get("day_of_month") or 28)
        _scheduler.add_job(
            _make_job("yearly"),
            CronTrigger(month=month, day=day, hour=hour, minute=minute),
            id=JOB_YEARLY,
            replace_existing=True,
        )
    if settings.get("full_enabled", True):
        hour, minute = _time_parts_value(str(settings.get("full_time") or "20:05"))
        _scheduler.add_job(_make_job("full"), CronTrigger(hour=hour, minute=minute), id=JOB_ID, replace_existing=True)
    logger.info(
        "Automatic backup scheduled: daily=%s monthly=%s yearly=%s full=%s",
        settings.get("daily_enabled"),
        settings.get("monthly_enabled"),
        settings.get("yearly_enabled"),
        settings.get("full_enabled"),
    )


def init_auto_backup_scheduler(
    app,
    *,
    base_dir: Path,
    upload_dir: Path,
    include_sqlite_db: Callable[[], bool],
    audit_callback: Optional[Callable[[str, str], None]] = None,
    resolve_upload: Optional[Callable[[str], Optional[Path]]] = None,
) -> None:
    """Start background scheduler (call once when the app starts)."""
    global _scheduler
    with _scheduler_lock:
        _runtime["base_dir"] = base_dir
        _runtime["upload_dir"] = upload_dir
        _runtime["include_sqlite_db"] = include_sqlite_db
        _runtime["audit_callback"] = audit_callback
        if resolve_upload is not None:
            _runtime["resolve_upload"] = resolve_upload

        if _scheduler is not None:
            apply_schedule(app)
            return

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            logger.warning("APScheduler is not installed; automatic backup is unavailable.")
            return

        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.start()
        apply_schedule(app)


def settings_from_form(form, base_dir: Path) -> dict[str, Any]:
    """Build settings dict from an HTML form."""
    current = load_settings(base_dir)
    current["enabled"] = (form.get("auto_backup_enabled") or "").strip().lower() in ("1", "true", "on", "yes")
    current["daily_enabled"] = (form.get("auto_backup_daily_enabled") or "").strip().lower() in ("1", "true", "on", "yes")
    current["monthly_enabled"] = (form.get("auto_backup_monthly_enabled") or "").strip().lower() in ("1", "true", "on", "yes")
    current["yearly_enabled"] = (form.get("auto_backup_yearly_enabled") or "").strip().lower() in ("1", "true", "on", "yes")
    current["full_enabled"] = (form.get("auto_backup_full_enabled") or "").strip().lower() in ("1", "true", "on", "yes")
    current["daily_time"] = _parse_time(form.get("auto_backup_daily_time") or form.get("auto_backup_time") or "20:00")
    current["monthly_time"] = _parse_time(form.get("auto_backup_monthly_time") or "20:00")
    current["yearly_time"] = _parse_time(form.get("auto_backup_yearly_time") or "20:00")
    current["full_time"] = _parse_time(form.get("auto_backup_full_time") or "20:05")
    current["time"] = current["daily_time"]
    current["frequency"] = "daily"
    try:
        current["day_of_month"] = int(form.get("auto_backup_day") or 28)
    except ValueError:
        current["day_of_month"] = 28
    try:
        current["month"] = int(form.get("auto_backup_month") or 12)
    except ValueError:
        current["month"] = 12
    current["destination_path"] = (form.get("auto_backup_destination") or "").strip().strip('"').strip("'")
    return _normalize_settings(current)


def frequency_label(frequency: str) -> str:
    labels = {
        "daily": "Every day",
        "weekly": "Every week",
        "monthly": "Every month",
        "yearly": "Every year",
    }
    return labels.get(frequency, frequency)
