"""Civil Registry certification form (CR Form 1A / 2A / 3A) print metadata and helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any


FORM_META: dict[str, dict[str, str]] = {
    "birth": {
        "form_no": "1 A",
        "availability": "(Birth-Available)",
        "register": "Births",
        "intro": (
            "We certify that among others, the following facts of birth appear "
            "in the Register of Births on page <strong>xx</strong> of book number <strong>xx</strong>."
        ),
    },
    "death": {
        "form_no": "2A",
        "availability": "(Death Available)",
        "register": "Deaths",
        "intro": (
            "We certify that among others, the following facts of death appear "
            "in the Register of Deaths on page <strong>xx</strong> of book number <strong>xx</strong>."
        ),
    },
    "marriage": {
        "form_no": "3A",
        "availability": "(Marriage Available)",
        "register": "Marriages",
        "intro": (
            "We certify that, among others, the following facts of marriage appear "
            "in the Register of Marriages on Page <strong>xx</strong> Book <strong>xx</strong>."
        ),
    },
}


def cert_issue_date(when: datetime | None = None) -> str:
    """e.g. June 2, 2026"""
    dt = when or datetime.now()
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def cert_field(data: dict[str, Any] | None, key: str, default: str = "") -> str:
    if not isinstance(data, dict):
        return default
    val = data.get(key)
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def form_meta(document_type: str) -> dict[str, str]:
    return FORM_META.get(document_type, FORM_META["birth"])


PRINT_FORMAT_ORIGINAL = "original"
PRINT_FORMAT_CERTIFICATION = "certification"
PRINT_FORMATS = (PRINT_FORMAT_ORIGINAL, PRINT_FORMAT_CERTIFICATION)


def normalize_print_format(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if v in PRINT_FORMATS else PRINT_FORMAT_ORIGINAL


def certification_form_label(document_type: str) -> str:
    meta = form_meta(document_type)
    return f"Certification form (CR Form No. {meta['form_no']} — {meta['availability'].strip('()')})"


def print_format_label(print_format: str, document_type: str = "birth") -> str:
    if normalize_print_format(print_format) == PRINT_FORMAT_CERTIFICATION:
        return certification_form_label(document_type)
    return "Original document (scanned certificate)"


def print_format_short_label(print_format: str, document_type: str = "birth") -> str:
    """Compact label for admin/staff tables."""
    if normalize_print_format(print_format) == PRINT_FORMAT_CERTIFICATION:
        meta = form_meta(document_type)
        return f"CR Form {meta['form_no']}"
    return "Original scan"
