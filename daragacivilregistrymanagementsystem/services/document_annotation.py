"""Official certificate annotation (typed LCR box + registrar signature)."""

from __future__ import annotations

from typing import Any

STORAGE_KEY = "_annotation"

KINDS = (
    ("legitimation", "Legitimation by subsequent marriage"),
    ("adoption", "Adoption"),
    ("court_order", "Court order / decree"),
    ("correction", "Correction of entry"),
    ("other", "Other annotation"),
)

DEFAULT_SIGNATORY = "MICHELLE M. MARINAY"
DEFAULT_TITLE = "MGDH I / MUN. CIVIL REGISTRAR"

FORM_KEYS = frozenset(
    {
        "annotation_kind",
        "annotation_text",
        "annotation_signatory",
        "annotation_title",
        "annotation_new_name",
        "annotation_marriage_registry",
    }
)


def public_fields(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if not str(k).startswith("_")}


def from_data(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    raw = data.get(STORAGE_KEY)
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "").strip()
    if not text:
        return None
    return {
        "kind": str(raw.get("kind") or "other").strip() or "other",
        "text": text,
        "signatory": str(raw.get("signatory") or "").strip() or DEFAULT_SIGNATORY,
        "title": str(raw.get("title") or "").strip() or DEFAULT_TITLE,
        "new_name": str(raw.get("new_name") or "").strip(),
        "marriage_registry": str(raw.get("marriage_registry") or "").strip(),
    }


def form_defaults(data: dict | None) -> dict:
    ann = from_data(data) or {}
    return {
        "kind": ann.get("kind") or "legitimation",
        "text": ann.get("text") or "",
        "signatory": ann.get("signatory") or DEFAULT_SIGNATORY,
        "title": ann.get("title") or DEFAULT_TITLE,
        "new_name": ann.get("new_name") or "",
        "marriage_registry": ann.get("marriage_registry") or "",
    }


def from_form(form) -> dict | None:
    text = (form.get("annotation_text") or "").strip()
    if not text:
        return None
    return {
        "kind": (form.get("annotation_kind") or "other").strip() or "other",
        "text": text,
        "signatory": (form.get("annotation_signatory") or "").strip() or DEFAULT_SIGNATORY,
        "title": (form.get("annotation_title") or "").strip() or DEFAULT_TITLE,
        "new_name": (form.get("annotation_new_name") or "").strip(),
        "marriage_registry": (form.get("annotation_marriage_registry") or "").strip(),
    }


def apply_to_data(data: dict | None, annotation: dict | None) -> dict:
    out = dict(data or {})
    out.pop(STORAGE_KEY, None)
    for key in list(out.keys()):
        if key in FORM_KEYS or str(key).startswith("annotation_"):
            out.pop(key, None)
    if annotation:
        out[STORAGE_KEY] = annotation
    return out


def build_legitimation_text(
    data: dict | None,
    *,
    new_name: str = "",
    marriage_registry: str = "",
) -> str:
    src: dict[str, Any] = data if isinstance(data, dict) else {}
    father = str(src.get("Name of Father") or "").strip()
    mother = str(src.get("Name of Mother") or "").strip()
    marriage_date = str(
        src.get("Date of Marriage of Parents")
        or src.get("Date of marriage of Parents")
        or src.get("Date of Marriage")
        or ""
    ).strip()
    marriage_place = str(
        src.get("Place of Marriage of Parents")
        or src.get("Place of marriage of Parents")
        or src.get("Place of Marriage")
        or ""
    ).strip()
    child = str(new_name or src.get("Name of Child") or "").strip()
    registry = str(marriage_registry or "").strip()

    parts = ["LEGITIMATED BY SUBSEQUENT MARRIAGE OF PARENTS"]
    if father and mother:
        parts.append(f"{father} AND {mother}")
    elif father or mother:
        parts.append(father or mother)
    if marriage_date:
        parts.append(f"ON {marriage_date}")
    if marriage_place:
        parts.append(f"AT {marriage_place}")
    if registry:
        parts.append(f"UNDER REGISTRY NO. {registry}")
    sentence = " ".join(parts)
    if child:
        sentence += f", THE CHILD SHALL BE KNOWN AS {child}"
    sentence = sentence.strip()
    if not sentence.endswith("."):
        sentence += "."
    return sentence.upper()
