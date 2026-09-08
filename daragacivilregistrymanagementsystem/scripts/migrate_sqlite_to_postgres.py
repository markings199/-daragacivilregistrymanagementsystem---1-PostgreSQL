"""
Copy records from a SQLite civil_registry.db file into the PostgreSQL database.

Run from the app folder:

    python scripts/migrate_sqlite_to_postgres.py
    python scripts/migrate_sqlite_to_postgres.py --sqlite "C:\\path\\to\\civil_registry.db"
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

TABLE_ORDER = (
    "users",
    "records",
    "edit_requests",
    "print_requests",
    "audit_logs",
    "print_logs",
    "backup_runs",
)


def _default_sqlite_paths() -> list[Path]:
    return [
        APP_ROOT / "civil_registry.db",
        APP_ROOT.parent / "civil_registry.db",
        Path(r"c:\daragacivilregistrymanagementsystem - 1") / "civil_registry.db",
        Path(r"c:\daragacivilregistrymanagementsystem - 1") / "daragacivilregistrymanagementsystem" / "civil_registry.db",
    ]


def _parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy SQLite data into PostgreSQL.")
    parser.add_argument("--sqlite", help="Path to civil_registry.db")
    parser.add_argument("--replace", action="store_true", help="Clear PostgreSQL tables before copy")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv:
        load_dotenv(APP_ROOT / ".env")
        load_dotenv(APP_ROOT.parent / ".env")

    sqlite_path = Path(args.sqlite).expanduser() if args.sqlite else None
    if sqlite_path is None:
        sqlite_path = next((p for p in _default_sqlite_paths() if p.exists()), None)
    if sqlite_path is None or not sqlite_path.exists():
        print("SQLite file not found. Pass --sqlite path-to-civil_registry.db")
        return 1

    from app import app, resolve_database_uri
    from models import (
        AuditLog,
        BackupRun,
        EditRequest,
        PrintLog,
        PrintRequest,
        Record,
        User,
        db,
    )

    pg_uri = resolve_database_uri()
    if pg_uri.lower().startswith("sqlite"):
        print("Target DATABASE_URL is still SQLite. Set a PostgreSQL URL in .env first.")
        return 1

    sqlite_uri = "sqlite:///" + sqlite_path.resolve().as_posix()
    src_engine = create_engine(sqlite_uri)
    SrcSession = sessionmaker(bind=src_engine)
    src = SrcSession()
    src_tables = set(inspect(src_engine).get_table_names())

    model_by_table = {
        "users": User,
        "records": Record,
        "edit_requests": EditRequest,
        "print_requests": PrintRequest,
        "audit_logs": AuditLog,
        "print_logs": PrintLog,
        "backup_runs": BackupRun,
    }

    print("Source SQLite:", sqlite_path)
    print("Target PostgreSQL:", pg_uri.split("@")[-1] if "@" in pg_uri else pg_uri)

    with app.app_context():
        db.create_all()
        if args.replace:
            joined = ", ".join(reversed(TABLE_ORDER))
            db.session.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))
            db.session.commit()
            print("Cleared existing PostgreSQL rows.")

        copied = 0
        db.session.execute(text("SET session_replication_role = replica"))
        try:
            for table in TABLE_ORDER:
                if table not in src_tables:
                    print(f"Skip missing SQLite table: {table}")
                    continue
                model = model_by_table[table]
                pg_cols = {c.name for c in model.__table__.columns}
                rows = src.execute(text(f"SELECT * FROM {table}")).mappings().all()
                payload = []
                for raw in rows:
                    kwargs = {}
                    for key, value in dict(raw).items():
                        if key not in pg_cols:
                            continue
                        col = model.__table__.columns[key]
                        if "datetime" in type(col.type).__name__.lower():
                            kwargs[key] = _parse_dt(value)
                        else:
                            kwargs[key] = value
                    payload.append(kwargs)
                if payload:
                    db.session.execute(model.__table__.insert(), payload)
                    db.session.flush()
                copied += len(payload)
                print(f"  {table}: {len(payload)} row(s)")
            for table in TABLE_ORDER:
                if table not in src_tables:
                    continue
                db.session.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
                    )
                )
            db.session.commit()
        finally:
            db.session.execute(text("SET session_replication_role = DEFAULT"))
            db.session.commit()

    src.close()
    src_engine.dispose()
    print(f"Done. Copied {copied} row(s) into PostgreSQL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
