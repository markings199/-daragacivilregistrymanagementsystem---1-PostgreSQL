"""Dump and restore PostgreSQL data for full ZIP backups (JSON, no pg_dump required)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import inspect

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

MODELS = (
    User,
    Record,
    EditRequest,
    PrintRequest,
    AuditLog,
    PrintLog,
    BackupRun,
)

TABLE_ORDER = tuple(model.__tablename__ for model in MODELS)


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return value


def _parse_value(value: Any, column) -> Any:
    if value is None or value == "":
        if column.nullable or column.default is not None or column.server_default is not None:
            if value == "" and getattr(column.type, "python_type", None) is str:
                return value
            return None if value is None else value
        return value
    type_name = type(column.type).__name__.lower()
    if "datetime" in type_name and isinstance(value, str):
        text = value.replace("T", " ").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def dump_database_json(dest: Path) -> None:
    """Write all application tables to dest as UTF-8 JSON."""
    payload = {"format": "daraga-postgres-json", "version": 1, "tables": {}}
    for model in MODELS:
        rows = []
        for row in model.query.order_by(model.id).all():
            rows.append({col.name: _jsonable(getattr(row, col.name)) for col in model.__table__.columns})
        payload["tables"][model.__tablename__] = rows
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _reset_postgres_identity(table: str) -> None:
    db.session.execute(
        db.text(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
        )
    )


def restore_database_json(src: Path) -> int:
    """Replace current PostgreSQL rows with the dump. Returns number of rows loaded."""
    payload = json.loads(src.read_text(encoding="utf-8"))
    tables = payload.get("tables") or {}
    dialect = db.engine.dialect.name

    if dialect == "postgresql":
        joined = ", ".join(reversed(TABLE_ORDER))
        db.session.execute(db.text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))
    else:
        for table in reversed(TABLE_ORDER):
            db.session.execute(db.text(f"DELETE FROM {table}"))
    db.session.flush()

    loaded = 0
    model_by_table = {model.__tablename__: model for model in MODELS}
    for table in TABLE_ORDER:
        model = model_by_table[table]
        columns = {col.name: col for col in model.__table__.columns}
        for raw in tables.get(table) or []:
            kwargs = {}
            for name, col in columns.items():
                if name not in raw:
                    continue
                kwargs[name] = _parse_value(raw[name], col)
            db.session.add(model(**kwargs))
            loaded += 1
    db.session.flush()

    if dialect == "postgresql":
        inspector = inspect(db.engine)
        for table in TABLE_ORDER:
            col_names = {col["name"] for col in inspector.get_columns(table)}
            if "id" in col_names:
                _reset_postgres_identity(table)

    db.session.commit()
    return loaded
