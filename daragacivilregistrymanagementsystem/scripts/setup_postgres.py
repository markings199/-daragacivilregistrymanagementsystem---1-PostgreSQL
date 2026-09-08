"""
Create the PostgreSQL database if it does not exist, then create tables and default users.

Run from the app folder:

    python scripts/setup_postgres.py
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv:
        load_dotenv(APP_ROOT / ".env")
        load_dotenv(APP_ROOT.parent / ".env")

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import make_url
    from sqlalchemy.exc import OperationalError, ProgrammingError

    from app import _bootstrap_users, resolve_database_uri

    uri = resolve_database_uri()
    url = make_url(uri)
    if not str(url.drivername).startswith("postgresql"):
        print("DATABASE_URL is not PostgreSQL:", url.render_as_string(hide_password=True))
        return 1

    dbname = url.database
    if not dbname:
        print("DATABASE_URL is missing a database name.")
        return 1

    admin_url = url.set(database="postgres")
    print("Connecting to:", admin_url.render_as_string(hide_password=True))
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": dbname},
            ).scalar()
            if exists:
                print(f'Database "{dbname}" already exists.')
            else:
                conn.execute(text(f'CREATE DATABASE "{dbname}"'))
                print(f'Created database "{dbname}".')
    except OperationalError as exc:
        print("Could not connect to PostgreSQL.")
        print("Install PostgreSQL, start the service, and check DATABASE_URL in .env")
        print(f"Error: {exc}")
        return 1
    finally:
        engine.dispose()

    try:
        _bootstrap_users()
    except (OperationalError, ProgrammingError) as exc:
        print("Database exists but tables could not be created:", exc)
        return 1

    print("Tables and default users are ready (admin/admin123, staff/staff123).")
    print("Start the app with: python app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
