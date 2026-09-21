"""
Map write-in boxes on Municipal Forms 102 / 103 / 97 after one page OCR.

Prefer passing items/pages from the main extractor so PaddleOCR runs only once.
If items are omitted, this module aligns the scan and runs a single page OCR.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from ocr.shared import run_ocr_on_image
from ocr.sex import sex_from_ocr_text

_CAUSE_JUNK = (
    "CHILDREN",
    "CHILD STILL",
    "BORN ALIVE",
    "STILL LIVING",
    "INCLUDING THIS BIRTH",
    "NOW DEAD",
    "MAIDEN NAME",
    "ATTENDANT AT BIRTH",
    "NO OF CHILD",
    "NO OF CHILDREN",
    "10A",
    "10B",
    "10C",
    "OCCUPATION",
    "HOUSEWIFE",
    "CERTIFICATION OF ATTENDANT",
    "ACCOMPLISH",
    "FOR AGES",
    "AGED 8 DAYS",
    "0 TO 7",
    "MEDICAL CERTIFICATE",
    "INTERVAL BETWEEN",
    "ONSET AND DEATH",
    "MATERNAL CONDITION",
    "EXTERNAL CAUSES",
    "IF THE DECEASED",
    "ITEMS 14",
    "AT THE BACK",
)


def is_plausible_cause_of_death(text: str) -> bool:
    """Drop mother/children form lines that are not a medical cause of death."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return False
    letters = sum(c.isalpha() for c in raw)
    if letters < 4:
        return False
    upper = re.sub(r"[^A-Z0-9 ]+", " ", raw.upper())
    upper = re.sub(r"\s+", " ", upper).strip()
    if re.search(r"\b10\s*[ABC]\b", upper):
        return False
    if any(token in upper for token in _CAUSE_JUNK):
        return False
    # Form option lines / numbered prompts, not diagnoses
    if re.search(r"\b(HOSPITAL|CLINIC|INSTITUTION|HOUSE)\b.*\b(STREET|BARANGAY)\b", upper):
        return False
    return True


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_SPEC_LOCK = threading.Lock()
_SPECS: Dict[str, Dict[str, Any]] = {}

_DOC_FILES = {
    "birth": "birth_boxes.json",
    "death": "death_boxes.json",
    "marriage": "marriage_boxes.json",
}

_NOISE = {
    "CERTIFICATE", "LIVE", "BIRTH", "DEATH", "MARRIAGE", "REPUBLIC",
    "PHILIPPINES", "MUNICIPAL", "FORM", "OFFICE", "CIVIL", "REGISTRAR",
    "GENERAL", "PROVINCE", "CITY", "MUNICIPALITY", "REGISTRY", "NUMBER",
    "NO", "NAME", "FIRST", "FIRSTNAME", "MIDDLE", "LAST", "LASTNAME",
    "SEX", "DATE", "DAY", "MONTH", "YEAR", "PLACE", "OF", "THE", "AND",
    "HOSPITAL", "CLINIC", "INSTITUTION", "HOUSE", "STREET", "BARANGAY",
    "TYPE", "IF", "MULTIPLE", "CHILD", "WAS", "ORDER", "WEIGHT",
    "GRAMS", "MAIDEN", "CITIZENSHIP", "RELIGION", "RELIGIOUS", "SECT",
    "OCCUPATION", "AGE", "TIME", "THIS", "RESIDENCE", "COUNTRY",
    "FATHER", "MOTHER", "PARENTS", "ATTENDANT", "INFORMANT",
    "CERTIFICATION", "REMARKS", "ANNOTATIONS", "LCRO", "CRG", "USE",
    "ONLY", "MALE", "FEMALE", "SINGLE", "TWIN", "TRIPLET",
    "HUSBAND", "WIFE", "CONTRACTING", "PARTIES", "SOLEMNIZE",
    "MIDDELE", "MIDDEL", "MIDLE", "FIRT", "FRST",
    "RECEIVED", "REGISTERED", "PREPARED", "SIGNATURE", "PRINT",
    "TITLE", "POSITION", "ADDRESS", "RELATIONSHIP", "DECEASED",
    "CAUSE", "IMMEDIATE", "ANTECEDENT", "UNDERLYING", "MEDICAL",
    "STATUS", "CIVIL", "NATIONALITY", "COMPLETED", "YEARS",
}

_SEX_OK = {"MALE", "FEMALE", "M", "F"}
_STATUS_OK = {
    "SINGLE", "MARRIED", "WIDOWED", "WIDOW", "WIDOWER",
    "DIVORCED", "SEPARATED", "ANNULLED",
}

_NATIONALITY_WORDS = {
    "FILIPINO": "Filipino",
    "FILIPINA": "Filipino",
    "FILIPING": "Filipino",
    "FILPINO": "Filipino",
    "FLIPINO": "Filipino",
    "AMERICAN": "American",
    "CHINESE": "Chinese",
    "JAPANESE": "Japanese",
    "KOREAN": "Korean",
    "BRITISH": "British",
    "INDIAN": "Indian",
    "AUSTRALIAN": "Australian",
    "CANADIAN": "Canadian",
}

_ADDRESS_TOKENS = {
    "BLOCK", "LOT", "PUROK", "BARANGAY", "BRGY", "STREET", "HOMES",
    "SUBDIVISION", "VILLAGE", "SITIO", "PHASE", "ROAD", "AVENUE",
    "CAMELLA", "HOUSE", "BLDG", "BUILDING",
}


def _norm_token(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _load_spec(doc_type: str) -> Optional[Dict[str, Any]]:
    key = (doc_type or "").strip().lower()
    if key not in _DOC_FILES:
        return None
    with _SPEC_LOCK:
        if key in _SPECS:
            return _SPECS[key]
        path = TEMPLATE_DIR / _DOC_FILES[key]
        if not path.exists():
            return None
        spec = json.loads(path.read_text(encoding="utf-8"))
        image_path = TEMPLATE_DIR / spec["image"]
        img = cv2.imread(str(image_path))
        if img is None:
            return None
        spec["_image"] = img
        spec["_path"] = str(image_path)
        _SPECS[key] = spec
        return spec


def _find_homography(scan, template) -> Optional[Any]:
    t_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    s_gray = cv2.cvtColor(scan, cv2.COLOR_BGR2GRAY)
    detector = cv2.ORB_create(nfeatures=1800)
    kp_t, des_t = detector.detectAndCompute(t_gray, None)
    kp_s, des_s = detector.detectAndCompute(s_gray, None)
    if des_t is None or des_s is None or len(kp_t) < 12 or len(kp_s) < 12:
        return None
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    try:
        pairs = matcher.knnMatch(des_s, des_t, k=2)
    except cv2.error:
        return None
    good = []
    for pair in pairs:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < 0.75 * n.distance:
            good.append(m)
    if len(good) < 14:
        return None
    src = np.float32([kp_s[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_t[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    homography, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if homography is None:
        return None
    inliers = int(mask.sum()) if mask is not None else 0
    if inliers < 10:
        return None
    return homography


def _items_from_pages(pages, img_w: int, img_h: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for page in pages or []:
        texts = page.get("rec_texts") or []
        scores = page.get("rec_scores") or []
        polys = page.get("dt_polys") or []
        for i, text in enumerate(texts):
            s = str(text or "").strip()
            if not s:
                continue
            poly = polys[i] if i < len(polys) else None
            if poly is None:
                continue
            arr = np.asarray(poly, dtype=np.float32)
            if arr.ndim != 2 or arr.shape[0] < 2:
                continue
            xs = arr[:, 0]
            ys = arr[:, 1]
            x1 = float(np.clip(xs.min(), 0, img_w))
            x2 = float(np.clip(xs.max(), 0, img_w))
            y1 = float(np.clip(ys.min(), 0, img_h))
            y2 = float(np.clip(ys.max(), 0, img_h))
            score = float(scores[i]) if i < len(scores) else 0.0
            items.append(
                {
                    "text": s,
                    "score": score,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "cx": (x1 + x2) / 2.0,
                    "cy": (y1 + y2) / 2.0,
                }
            )
    items.sort(key=lambda it: (it["cy"], it["x1"]))
    return items


def _project_items_to_template(
    items: List[Dict[str, Any]],
    homography,
    scan_w: int,
    scan_h: int,
    template_w: int,
    template_h: int,
) -> List[Dict[str, Any]]:
    if not items:
        return []
    if homography is None:
        sx = template_w / float(max(1, scan_w))
        sy = template_h / float(max(1, scan_h))
        out = []
        for it in items:
            cx = it["cx"] * sx
            cy = it["cy"] * sy
            out.append({**it, "cx": cx, "cy": cy})
        return out
    pts = np.float32([[[it["cx"], it["cy"]]] for it in items])
    try:
        mapped = cv2.perspectiveTransform(pts, homography)
    except cv2.error:
        return _project_items_to_template(items, None, scan_w, scan_h, template_w, template_h)
    out = []
    for it, pt in zip(items, mapped):
        cx, cy = float(pt[0][0]), float(pt[0][1])
        out.append({**it, "cx": cx, "cy": cy})
    return out


def _text_in_box(items: List[Dict[str, Any]], box: List[float], img_w: int, img_h: int) -> str:
    x1, y1, x2, y2 = box
    left = x1 * img_w
    right = x2 * img_w
    top = y1 * img_h
    bottom = y2 * img_h
    pad_x = max(4.0, (right - left) * 0.03)
    pad_y = max(3.0, (bottom - top) * 0.08)
    left -= pad_x
    right += pad_x
    top -= pad_y
    bottom += pad_y
    hits = [
        it
        for it in items
        if left <= it["cx"] <= right and top <= it["cy"] <= bottom and it.get("score", 1.0) >= 0.2
    ]
    hits.sort(key=lambda it: (it["cy"], it["x1"]))
    return " ".join(it["text"] for it in hits).strip()


def _subtract_printed(scan_text: str, printed_text: str) -> str:
    printed = {_norm_token(t) for t in re.findall(r"[A-Za-z0-9]+", printed_text or "")}
    printed.discard("")
    kept: List[str] = []
    for token in re.findall(r"[A-Za-z0-9/'\\-]+", scan_text or ""):
        n = _norm_token(token)
        if not n:
            continue
        if n in printed:
            continue
        if n in _NOISE and n not in _SEX_OK and n not in _STATUS_OK:
            continue
        kept.append(token)
    return " ".join(kept).strip()


_MONTH_NAMES = (
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
)
_DATE_WORD_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s+(" + "|".join(_MONTH_NAMES) + r")\s+(\d{4})\b"
)


def _clean_date_value(text: str) -> str:
    """Keep handwritten dates; drop Form 103 printed 'Day, Month, Year' labels."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return ""
    n = re.sub(r"[^A-Z0-9 ]+", " ", raw.upper())
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"\b(DAY|MONTH|YEAR|DATE|OF|DEATH|BIRTH)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    for month in sorted(_MONTH_NAMES, key=len, reverse=True):
        n = re.sub(rf"(?<=\d)({month})", r" \1", n)
        n = re.sub(rf"({month})(?=\d)", r"\1 ", n)
    n = re.sub(r"\s+", " ", n).strip()
    m = _DATE_WORD_RE.search(n)
    if m:
        return f"{m.group(1)} {m.group(2)} {m.group(3)}"
    m = re.search(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})\b", raw)
    if m:
        year = m.group(3)
        if len(year) == 2:
            year = ("20" if int(year) <= 30 else "19") + year
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{year}"
    return ""


def _citizenship_value(text: str) -> str:
    """Keep a real nationality. Residence lines (Block, Lot, Purok) are not citizenship."""
    upper = re.sub(r"[^A-Z ]", " ", (text or "").upper())
    upper = re.sub(r"\s+", " ", upper).strip()
    if not upper:
        return ""
    words = [w for w in upper.split() if w not in {"SEX", "MALE", "FEMALE", "CITIZENSHIP"}]
    for word in words:
        if word in _NATIONALITY_WORDS:
            return _NATIONALITY_WORDS[word]
    if any(word in _ADDRESS_TOKENS for word in words):
        return ""
    if len(words) == 1 and len(words[0]) >= 4:
        return words[0].title()
    return ""


def _clean_value(kind: str, raw: str) -> str:
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return ""
    upper = text.upper()
    if kind == "sex":
        return sex_from_ocr_text(text)
    if kind == "status":
        # Drop printed option lists: (Single/Married/Widow/Widower/...)
        stripped = re.sub(r"\([^)]*\)", " ", text)
        upper = stripped.upper()
        order = (
            "WIDOWED", "WIDOWER", "WIDOW", "MARRIED", "SINGLE",
            "DIVORCED", "SEPARATED", "ANNULLED",
        )
        hits = [w for w in order if re.search(rf"\b{w}\b", upper)]
        # More than one status word ⇒ OCR grabbed the printed checklist, not the write-in.
        if len(hits) != 1:
            return ""
        word = hits[0]
        if word in {"WIDOWER", "WIDOW"}:
            return "Widowed"
        return word.title()
    if kind == "citizenship":
        return _citizenship_value(text)
    if kind == "age":
        hits = []
        upper = text.upper()
        for m in re.finditer(r"(?<!\d)(\d{1,3})\s*(YEARS?|YRS)?\b", upper):
            val = int(m.group(1))
            unit = m.group(2) or ""
            after = upper[m.end() : m.end() + 16].strip()
            before = upper[max(0, m.start() - 16) : m.start()]
            if val == 1 and (after.startswith("OR") or "ABOVE" in after[:16] or "UNDER" in before):
                continue
            if 0 <= val <= 130:
                hits.append((1 if unit else 0, val))
        if not hits:
            return ""
        with_unit = [h for h in hits if h[0]]
        if with_unit:
            return str(with_unit[-1][1])
        adult = [h for h in hits if 18 <= h[1] <= 90]
        pool = adult or [h for h in hits if h[1] != 1]
        if not pool:
            return ""
        return str(pool[-1][1])
    if kind == "registry":
        compact = re.sub(r"[^A-Za-z0-9/\-]", "", text)
        return compact if len(compact) >= 3 else ""
    if kind == "date":
        return _clean_date_value(text)
    if kind == "cause":
        letters = re.sub(r"[^A-Za-z]", "", text)
        if len(letters) < 4 or not is_plausible_cause_of_death(text):
            return ""
        return text
    if kind == "name":
        upper = text.upper()
        if any(tip in upper for tip in (
            "TITLE OR POSITION", "TITLE OF POSITION", "NAME IN PRINT",
            "SIGNATURE", "HOUSE NO", "(HOUSE", "BARANGAY)", "MUNICIPALITY)",
        )):
            return ""
        if "(" in text and ")" in text:
            return ""
        letters = re.sub(r"[^A-Za-z ]", " ", text)
        words = [
            w for w in letters.split()
            if w.upper() not in _NATIONALITY_WORDS
            and w.upper() not in {"MALE", "FEMALE", "SEX", "FILL", "IN", "BY", "AT", "OF", "THE"}
        ]
        # Cut instruction tails that stick to handwritten names.
        cut = []
        for w in words:
            if w.upper() in {"FILL", "TYPEWRITE", "PRINT", "WRITE"}:
                break
            cut.append(w)
        letters = " ".join(cut).strip()
        return letters if len(letters) >= 5 else ""
    if kind == "place":
        return _place_of_death_value(text)
    return text


_PLACE_FORM_TOKENS = {
    "HOSPITAL", "CLINIC", "INSTITUTION", "HOUSE", "STREET", "BARANGAY",
    "CITY", "MUNICIPALITY", "PROVINCE", "NAME", "PLACE", "DEATH", "NO", "ST",
}


def _place_of_death_value(text: str) -> str:
    """Keep a real place; reject form instruction lines and date/time bleed."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return ""
    # Drop parenthetical instruction and leading item number (e.g. "6.")
    cleaned = re.sub(r"\([^)]*\)", " ", raw)
    cleaned = re.sub(r"^\d+\.?\s*", "", cleaned)
    cleaned = re.sub(
        r"(?i)\b(name of\s+)?hospital/?clinic/?institution/?house\b[^.]*",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\b(hospital|clinic|institution|house)\s*/\s*(clinic|institution|house|street)\b",
        " ",
        cleaned,
    )
    # Cut date/time that often leaks from the next marriage form row.
    months = (
        "JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
        "SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
    )
    cut = re.search(rf"(?i)\b\d{{1,2}}\s+(?:{months})\s+\d{{2,4}}\b", cleaned)
    if cut:
        cleaned = cleaned[: cut.start()]
    cut = re.search(
        r"(?i)\b\d{1,2}\s*[:.]\s*\d{2}\s*(?:AM|PM)?\b|\b\d{1,2}\s+\d{2}\s*(?:AM|PM)\b|\b(?:AM|PM)\b",
        cleaned,
    )
    if cut:
        cleaned = cleaned[: cut.start()]
    cleaned = re.sub(r"(?i)\b(?:CITY\s+)?MUNICIPALITY(?:\s+PROVINCE)?\s*$", " ", cleaned)
    cleaned = re.sub(r"[/]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .:-,")
    upper = re.sub(r"[^A-Z0-9 ]+", " ", cleaned.upper())
    upper = re.sub(r"\s+", " ", upper).strip()
    words = [w for w in upper.split() if w]
    if not words:
        return ""
    formish = sum(1 for w in words if w in _PLACE_FORM_TOKENS)
    if formish >= max(2, len(words) - 1):
        return ""
    if len(words) <= 2 and all(w in _PLACE_FORM_TOKENS or len(w) <= 2 for w in words):
        return ""
    letters = sum(c.isalpha() for c in cleaned)
    return cleaned if letters >= 4 else ""


def _fill_boxes(spec: Dict[str, Any], items_template: List[Dict[str, Any]]) -> Dict[str, str]:
    template = spec["_image"]
    th, tw = template.shape[:2]
    out: Dict[str, str] = {}
    for field in spec.get("fields") or []:
        key = field["key"]
        kind = field.get("kind") or "text"
        raw = _text_in_box(items_template, field["box"], tw, th)
        if kind == "sex":
            value = sex_from_ocr_text(raw)
        else:
            value = _subtract_printed(raw, field.get("printed") or "")
            value = _clean_value(kind, value)
        if value and key not in out:
            out[key] = value
    return _compose_party_full_names(out)


def _compose_party_full_names(out: Dict[str, str]) -> Dict[str, str]:
    """Form 97 writes First / Middle / Last — join them for Husband Name and Wife Name."""
    for who in ("Husband", "Wife"):
        parts = []
        for part in ("First", "Middle", "Last"):
            val = re.sub(r"\s+", " ", (out.get(f"{who} {part}") or "").strip())
            if val:
                parts.append(val)
        composed = _collapse_doubled_person_name(_join_name_parts(parts))
        current = _collapse_doubled_person_name(
            re.sub(r"\s+", " ", (out.get(f"{who} Name") or "").strip())
        )
        if composed and (not current or len(composed.split()) >= len(current.split())):
            out[f"{who} Name"] = composed
        elif current:
            out[f"{who} Name"] = current
        elif composed:
            out[f"{who} Name"] = composed
        out.pop(f"{who} First", None)
        out.pop(f"{who} Middle", None)
        out.pop(f"{who} Last", None)
    return out


def _name_keys(words: List[str]) -> List[str]:
    return [re.sub(r"[^A-Za-z]", "", w).upper() for w in words]


def _join_name_parts(parts: List[str]) -> str:
    """Join First/Middle/Last without concatenating overlapping OCR chunks."""
    cleaned: List[str] = []
    for raw in parts:
        piece = re.sub(r"\s+", " ", (raw or "").strip())
        if not piece:
            continue
        piece_words = piece.split()
        existing = cleaned[:]
        existing_keys = _name_keys(existing)
        piece_keys = _name_keys(piece_words)
        if not piece_keys:
            continue
        # Skip if this chunk already appears as a contiguous run.
        if any(
            existing_keys[i : i + len(piece_keys)] == piece_keys
            for i in range(0, max(1, len(existing_keys) - len(piece_keys) + 1))
        ):
            continue
        # If the new chunk already contains the whole name so far, keep the fuller one.
        if existing_keys and len(piece_keys) > len(existing_keys):
            if any(
                piece_keys[i : i + len(existing_keys)] == existing_keys
                for i in range(0, max(1, len(piece_keys) - len(existing_keys) + 1))
            ):
                cleaned = piece_words[:]
                continue
        # Strip edge overlap: ... SANTOS + SANTOS DELA → ... SANTOS DELA
        if existing_keys and piece_keys:
            max_overlap = min(len(existing_keys), len(piece_keys))
            for n in range(max_overlap, 0, -1):
                if existing_keys[-n:] == piece_keys[:n]:
                    piece_words = piece_words[n:]
                    piece_keys = piece_keys[n:]
                    break
        if not piece_words:
            continue
        cleaned.extend(piece_words)
    # Drop consecutive duplicate tokens.
    out: List[str] = []
    for w in cleaned:
        if not out or _name_keys([out[-1]]) != _name_keys([w]):
            out.append(w)
    return " ".join(out).strip()


def _collapse_doubled_person_name(name: str) -> str:
    """Remove exact/partial doubled person names from box OCR."""
    words = [w for w in re.sub(r"\s+", " ", (name or "").strip()).split() if w]
    n = len(words)
    if n < 4:
        return " ".join(words)

    keys = _name_keys(words)
    if n % 2 == 0:
        half = n // 2
        if half >= 2 and keys[:half] == keys[half:]:
            return " ".join(words[:half])
    for k in range(n // 2, 1, -1):
        if keys[:k] == keys[n - k :]:
            return " ".join(words[: n - k])
    return " ".join(words)


def extract_field_boxes(
    img,
    doc_type: str,
    items: Optional[List[Dict[str, Any]]] = None,
    pages=None,
) -> Dict[str, str]:
    """
    Fill write-in boxes from OCR tokens.

    Pass `items` or `pages` from the main extractor to avoid a second PaddleOCR call.
    Coordinates on items/pages must match `img`.
    """
    spec = _load_spec(doc_type)
    if spec is None or img is None:
        return {}
    template = spec["_image"]
    th, tw = template.shape[:2]
    sh, sw = img.shape[:2]
    homography = _find_homography(img, template)

    if items is None:
        if pages is not None:
            items = _items_from_pages(pages, sw, sh)
        else:
            # Fallback only: one page OCR on the aligned image.
            if homography is not None:
                aligned = cv2.warpPerspective(img, homography, (tw, th))
            else:
                aligned = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
            pages = run_ocr_on_image(aligned)
            items_template = _items_from_pages(pages, tw, th)
            return _fill_boxes(spec, items_template)

    items_template = _project_items_to_template(items, homography, sw, sh, tw, th)
    return _fill_boxes(spec, items_template)
