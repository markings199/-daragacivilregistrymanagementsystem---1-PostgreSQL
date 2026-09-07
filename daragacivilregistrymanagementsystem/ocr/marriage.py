"""
Marriage certificate OCR extraction.
Fixed implementation v2 - addresses name extraction issues.
"""
import re
import difflib
from datetime import datetime
from typing import Dict, Any, List

import cv2
import numpy as np
from ocr.shared import run_ocr_on_image
from ocr.engine import extract_from_ocr_text, ocr_pages_to_text


# =========================================================
# CONFIG
# =========================================================
DEBUG_OCR_RAW = False
DEBUG_LABELS = False
DEBUG_PREPROCESS = False
DEBUG_NAME_BAND = False
DEBUG_DRAW_BOXES = False
DEBUG_TEMPLATE_MATCH = False


# =========================================================
# PREPROCESS
# =========================================================
def preprocess_image(img):
    """Makes pre-cropped inputs more OCR-friendly."""
    h, w = img.shape[:2]

    target_w = 1700
    if w < target_w:
        scale = target_w / float(w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    h, w = img.shape[:2]
    pad_x = max(30, int(w * 0.03))
    pad_y = max(30, int(h * 0.03))
    img = cv2.copyMakeBorder(
        img, pad_y, pad_y, pad_x, pad_x,
        borderType=cv2.BORDER_CONSTANT,
        value=(255, 255, 255)
    )

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.convertScaleAbs(gray, alpha=1.10, beta=6)

    out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return out


# =========================================================
# OCR DEBUG VISUALIZER
# =========================================================
def draw_debug_boxes(img, items):
    """Draw OCR bounding boxes and text."""
    debug_img = img.copy()
    for it in items:
        x1, y1, x2, y2 = it["x1"], it["y1"], it["x2"], it["y2"]
        cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(debug_img, it["text"], (x1, max(15, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.imwrite("debug_ocr_boxes.jpg", debug_img)
    print("\n✔ Debug OCR image saved: debug_ocr_boxes.jpg\n")


# =========================================================
# CONSTANTS
# =========================================================
MONTHS = {
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"
}

HELPER_WORDS = {
    "FIRST", "LAST", "MIDDLE", "INITIAL", "DAY", "MONTH", "YEAR",
    "AGE", "HUSBAND", "WIFE", "PARTIES", "PARTIEN", "PARTY",
    "MIDDLE INITIAL", "MIDDIE INITIAL", "MIDDLE INITLAL", "MIDDLE INLTIAL"
}

NAME_BANNED_WORDS = {
    "CITIZENSHIP", "PROVINCE", "PROVINCEO", "RELIGION", "RESIDENCE",
    "MALE", "FEMALE", "FILIPINO", "FILIPING", "OFFICE", "CIVIL",
    "REGISTRY", "REGISTRAR", "REGIS", "MUNICIPALITY", "MUNIEIPALITY",
    "CITY", "FORMNO", "FORM", "QUADRUPLICAIE", "ACCOMPLISHED",
    "AUGUST", "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
    "PLACE", "BIRTH", "DEATH", "MARRIAGE", "NO", "NUMBER",
    "REPUBLIC", "PHILIPPINES", "PHILIPPINE", "STATISTICS",
    "AUTHORITY", "GENERAL", "MANILA", "CERTIFICATE", "REGISTRATION",
    "COPY", "OFFICIAL", "LOCAL", "REGISTRATION", "CONTRACTING",
    "PARTIES", "HUSBAND", "WIFE", "AGE", "SEX", "STATUS",
}

NAME_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}
NAME_PARTICLES = {"DE", "DEL", "DELA", "DA", "VAN", "VON", "SAN", "SANTA", "LA", "LAS", "LOS", "Y", "DI"}

CITIZENSHIP_CANON = {
    "FILIPINO": "FILIPINO",
    "FILPINO": "FILIPINO",
    "FLIPINO": "FILIPINO",
    "FILIPINA": "FILIPINO",
    "AMERICAN": "AMERICAN",
    "CHINESE": "CHINESE",
    "JAPANESE": "JAPANESE",
    "KOREAN": "KOREAN",
    "BRITISH": "BRITISH",
    "INDIAN": "INDIAN",
    "AUSTRALIAN": "AUSTRALIAN",
    "CANADIAN": "CANADIAN",
}

PLACE_LANDMARKS = (
    "QUEZON CITY", "CITY HALL", "MUNICIPAL HALL", "BARANGAY", "MANILA",
    "QUEZON", "MAKATI", "PASIG", "TAGUIG", "CALOOCAN", "PASAY", "MUNTINLUPA",
    "PARANAQUE", "PARAÑAQUE", "LAS PINAS", "LAS PIÑAS", "ERMITA", "CUBAO",
    "ALABANG", "CEBU", "DAVAO", "ALBAY", "CAMALIG", "DARAGA", "LEGAZPI",
    "STREET", "AVENUE", "ROAD", "CHURCH", "CATHEDRAL", "HALL",
)

COMMON_WORD_FIXES = {
    "FILPINO": "FILIPINO", "FLPINO": "FILIPINO", "FLIPINO": "FILIPINO",
    "FILIPING": "FILIPINO", "F ILIPINO": "FILIPINO",
    "MALEL": "MALE", "FEMALEL": "FEMALE",
    "ROMAN CATHOLIG": "ROMAN CATHOLIC", "CATHOLIG": "CATHOLIC",
}


# =========================================================
# HELPERS
# =========================================================
def clean_text(t: str) -> str:
    t = str(t).strip()
    t = t.replace("|", " ")
    t = re.sub(r"[._]{2,}", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def norm_text(t: str) -> str:
    t = clean_text(t).upper()
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def compact_text(t: str) -> str:
    return re.sub(r"\s+", "", norm_text(t))


def alpha_count(t: str) -> int:
    return sum(ch.isalpha() for ch in t)


def tokens_in_region(items, xmin, xmax, ymin, ymax, min_score=0.20):
    out = []
    for it in items:
        if it["score"] < min_score:
            continue
        if xmin <= it["cx"] <= xmax and ymin <= it["cy"] <= ymax:
            out.append(it)
    out.sort(key=lambda x: (x["cy"], x["x1"]))
    return out


def group_rows(tokens, y_tol=16):
    if not tokens:
        return []
    tokens = sorted(tokens, key=lambda x: (x["cy"], x["x1"]))
    rows = [[tokens[0]]]
    for it in tokens[1:]:
        row_y = sum(x["cy"] for x in rows[-1]) / len(rows[-1])
        if abs(it["cy"] - row_y) <= y_tol:
            rows[-1].append(it)
        else:
            rows.append([it])
    for row in rows:
        row.sort(key=lambda x: x["x1"])
    return rows


def join_tokens(tokens):
    return " ".join(clean_text(t["text"]) for t in sorted(tokens, key=lambda x: x["x1"])).strip()


def apply_common_word_fix(text: str) -> str:
    nt = norm_text(text)
    return COMMON_WORD_FIXES.get(nt, nt)


def is_date_noise_token(nt: str) -> bool:
    if not nt:
        return False
    if re.search(r"\d", nt) and any(month[:3] in nt for month in MONTHS):
        return True
    if re.fullmatch(r"\d{1,2}[A-Z]{3,9}\d{0,4}", nt):
        return True
    if re.fullmatch(r"\d{1,2}:\d{2}(AM|PM)?", nt):
        return True
    if re.fullmatch(r"\d{4}", nt) and 1900 <= int(nt) <= 2100:
        return True
    return False


def sanitize_person_name(name: str) -> str:
    """Drop OCR junk, dates, and form words so only a person name remains."""
    parts = []
    for raw in clean_text(name).split():
        nt = norm_text(raw)
        if not nt or is_helper_token(raw) or is_form_metadata(raw):
            continue
        if is_date_noise_token(nt) or nt in NAME_BANNED_WORDS:
            continue
        if re.fullmatch(r"\d+", nt):
            continue
        mixed = raw != raw.upper() and raw != raw.lower() and raw != raw.title()
        if mixed and alpha_count(raw) <= 3:
            continue
        if re.fullmatch(r"[A-Z]\.?", nt) or nt in NAME_SUFFIXES or nt in NAME_PARTICLES:
            parts.append(nt if nt in NAME_SUFFIXES or nt in NAME_PARTICLES else raw.upper().rstrip("."))
            continue
        if alpha_count(raw) < 3:
            continue
        parts.append(raw.upper())
    while parts and norm_text(parts[0]) not in NAME_PARTICLES and alpha_count(parts[0]) < 3:
        parts.pop(0)
    while parts and norm_text(parts[-1]) not in NAME_SUFFIXES | NAME_PARTICLES and alpha_count(parts[-1]) < 3:
        parts.pop()
    return " ".join(parts).strip()


def normalize_citizenship_value(text: str) -> str:
    nt = compact_text(text)
    if not nt:
        return ""
    for key, canon in CITIZENSHIP_CANON.items():
        if compact_text(key) in nt or nt in compact_text(key):
            return canon
    match = difflib.get_close_matches(nt, [compact_text(k) for k in CITIZENSHIP_CANON], n=1, cutoff=0.78)
    if match:
        for key, canon in CITIZENSHIP_CANON.items():
            if compact_text(key) == match[0]:
                return canon
    cleaned = apply_common_word_fix(text)
    return cleaned if alpha_count(cleaned) >= 4 else ""


def normalize_month_word(word: str) -> str:
    w = norm_text(word)
    if w in MONTHS:
        return w
    if len(w) < 3:
        return w
    if len(w) >= 2 and w[0] == w[1]:
        if w[1:] in MONTHS:
            return w[1:]
    squashed = re.sub(r"(.)\1+", r"\1", w)
    if squashed in MONTHS:
        return squashed
    match = difflib.get_close_matches(w, list(MONTHS), n=1, cutoff=0.70)
    if match:
        return match[0]
    match = difflib.get_close_matches(squashed, list(MONTHS), n=1, cutoff=0.70)
    if match:
        return match[0]
    return w


def normalize_sex_value(text: str) -> str:
    nt = norm_text(text)
    if "FEMALE" in nt:
        return "FEMALE"
    if re.search(r"\bMALE\b", nt):
        return "MALE"
    return apply_common_word_fix(text)


def pattern_score(text: str, patterns):
    nt = norm_text(text)
    ct = compact_text(text)
    best = 0.0
    for pat in patterns:
        p = norm_text(pat)
        pc = compact_text(pat)
        if all(tok in nt for tok in p.split()):
            score = 10.0 + len(p.split())
            best = max(best, score)
            continue
        ratio = difflib.SequenceMatcher(None, ct, pc).ratio()
        if ratio >= 0.62:
            best = max(best, ratio * 10.0)
    return best


def find_best_label(items, patterns, x_min=None, x_max=None, y_min=None, y_max=None,
                    forbidden=None, min_score=0.20):
    forbidden = forbidden or []
    best = None
    best_tuple = None
    for it in items:
        if it["score"] < min_score:
            continue
        if x_min is not None and it["cx"] < x_min:
            continue
        if x_max is not None and it["cx"] > x_max:
            continue
        if y_min is not None and it["cy"] < y_min:
            continue
        if y_max is not None and it["cy"] > y_max:
            continue
        nt = norm_text(it["text"])
        if any(f.upper() in nt for f in forbidden):
            continue
        ps = pattern_score(it["text"], patterns)
        if ps <= 0:
            continue
        tup = (ps, it["score"], -len(nt))
        if best is None or tup > best_tuple:
            best = it
            best_tuple = tup
    return best


def find_label_below(items, anchor_label, patterns, y_min_offset=2, y_max_offset=70, x_max=None):
    if not anchor_label:
        return None
    return find_best_label(
        items, patterns=patterns,
        x_min=0, x_max=x_max,
        y_min=anchor_label["y2"] + y_min_offset,
        y_max=anchor_label["y2"] + y_max_offset,
        min_score=0.20
    )


def infer_working_xmax(items, img_w, img_h):
    blockers = [
        find_best_label(items, ["FOR OCRG USE ONLY"], x_min=img_w * 0.55, y_min=0, y_max=img_h * 0.30),
        find_best_label(items, ["REMARKS ANNOTATION"], x_min=img_w * 0.55, y_min=0, y_max=img_h * 0.15),
        find_best_label(items, ["POPULATION REFERENCE NO"], x_min=img_w * 0.55, y_min=0, y_max=img_h * 0.20),
    ]
    xs = [b["x1"] for b in blockers if b is not None]
    if xs:
        return min(xs) - 20
    return int(img_w * 0.70)


def is_helper_token(text: str) -> bool:
    raw = clean_text(text)
    nt = norm_text(raw)
    if "(" in raw or ")" in raw:
        return True
    for hw in HELPER_WORDS:
        if hw in nt:
            return True
    junk = {"RNSTIAL", "INLTIAL", "INITLAL", "INTAL", "ISITAL",
            "RUTAL", "AWUT", "AMTL", "TRAT", "FORE", "LAMT", "TRL"}
    if any(j in nt for j in junk):
        return True
    return False


def is_form_metadata(text: str) -> bool:
    """Check if text appears to be form metadata/boilerplate"""
    raw = clean_text(text)
    nt = norm_text(raw)
    form_patterns = [
        r"^FORM\s*NO\.?\d+", r"^FORMNO\.?\d+", r"FORMNO\d+",
        r"CERTIFICATE\s*NO", r"REGISTRATION\s*NO", r"MUNICIPAL\s*FORM",
        r"MANILA", r"OFFICE\s*OF\s*THE", r"REPUBLIC\s*OF", r"PHILIPPINE",
        r"STATISTICS", r"CIVIL\s*REGISTRAR",
    ]
    for pattern in form_patterns:
        if re.search(pattern, nt, re.IGNORECASE):
            return True
    if len(nt) <= 2 and not re.match(r"^[A-Z]\.?$", nt):
        return True
    return False


def infer_column_split_from_headers(items, name_label, working_xmax, img_w, img_h):
    husband_marker = find_best_label(
        items, ["HUSBAND"],
        x_min=name_label["x2"] if name_label else img_w * 0.15,
        x_max=working_xmax, y_min=img_h * 0.06, y_max=img_h * 0.18
    )
    wife_marker = find_best_label(
        items, ["WIFE"],
        x_min=name_label["x2"] if name_label else img_w * 0.30,
        x_max=working_xmax, y_min=img_h * 0.06, y_max=img_h * 0.18
    )
    if husband_marker and wife_marker and husband_marker["cx"] < wife_marker["cx"]:
        return (husband_marker["cx"] + wife_marker["cx"]) / 2.0
    return None


def infer_column_split_from_name(items, name_label, working_xmax, img_w):
    if not name_label:
        return img_w * 0.48
    row_tokens = tokens_in_region(
        items, name_label["x2"] + 5, working_xmax,
        name_label["y1"] - 18, name_label["y2"] + 50, min_score=0.15
    )
    xs = []
    for it in row_tokens:
        if is_helper_token(it["text"]):
            continue
        if alpha_count(it["text"]) < 2:
            continue
        xs.append(it["cx"])
    if len(xs) < 2:
        return (name_label["x2"] + working_xmax) / 2.0
    c1, c2 = min(xs), max(xs)
    for _ in range(12):
        g1, g2 = [], []
        for x in xs:
            if abs(x - c1) <= abs(x - c2):
                g1.append(x)
            else:
                g2.append(x)
        if not g1 or not g2:
            break
        new_c1, new_c2 = sum(g1) / len(g1), sum(g2) / len(g2)
        if abs(new_c1 - c1) < 0.5 and abs(new_c2 - c2) < 0.5:
            c1, c2 = new_c1, new_c2
            break
        c1, c2 = new_c1, new_c2
    if c1 > c2:
        c1, c2 = c2, c1
    return (c1 + c2) / 2.0


def split_left_right(tokens, split_x, label_x2=0):
    left, right = [], []
    for it in tokens:
        if it["x2"] <= label_x2:
            continue
        if is_helper_token(it["text"]):
            continue
        if it["cx"] < split_x:
            left.append(it)
        else:
            right.append(it)
    left.sort(key=lambda x: x["x1"])
    right.sort(key=lambda x: x["x1"])
    return left, right


def normalize_name(tokens):
    parts = []
    for it in sorted(tokens, key=lambda x: x["x1"]):
        t = clean_text(it["text"])
        nt = norm_text(t)
        if not t or is_helper_token(t) or is_form_metadata(t):
            continue
        if re.fullmatch(r"\d+", nt):
            continue
        if alpha_count(t) < 2 and not re.fullmatch(r"[A-Z]\.?", t, re.I):
            continue
        if nt in NAME_BANNED_WORDS:
            continue
        if any(re.search(r"\b" + re.escape(b) + r"\b", nt) for b in NAME_BANNED_WORDS):
            continue
        parts.append(t)

    name = " ".join(parts).strip()
    header_phrases = [
        "OFFICE OF THE CIVIL REGISTRAR GENERAL", "OFFICE OF THE CIVIL REGISTRAR",
        "REPUBLIC OF THE PHILIPPINES", "PHILIPPINE STATISTICS AUTHORITY",
        "PHILIPPINE STATISTICAL AUTHORITY", "REPUBLIC OF PHILIPPINES",
        "CITIZENSHIP", "PROVINCE", "RELIGION", "RESIDENCE", "MALE", "FEMALE",
        "FILIPINO", "MUNICIPALITY", "PLACE OF BIRTH",
    ]
    for banned in header_phrases:
        name = re.sub(r"\b" + re.escape(banned) + r"\b", " ", name, flags=re.I)
    name = re.sub(r"\bFORM\s*NO\.?\s*\d+\b", " ", name, flags=re.I)
    name = re.sub(r"\bMUNICIPAL\s+FORM\s*NO\.?\s*\d+\b", " ", name, flags=re.I)
    name = re.sub(r"\bREGISTRY\s*NO\.?\s*\d+\b", " ", name, flags=re.I)
    name = re.sub(r"\bFORMNO\.?\s*\d+\b", " ", name, flags=re.I)
    name = re.sub(r"\bSAN\s+N\s+ANDRES\b", "SAN ANDRES", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip()
    return sanitize_person_name(name)


def normalize_simple_row(tokens, banned=None):
    banned = banned or set()
    parts = []
    for it in sorted(tokens, key=lambda x: x["x1"]):
        t = clean_text(it["text"])
        nt = norm_text(t)
        if not t or is_helper_token(t) or nt in banned:
            continue
        parts.append(t)
    out = " ".join(parts).strip()
    return apply_common_word_fix(out)


def extract_band_tokens(items, label_item, working_xmax, next_label=None, extra_bottom=26, extra_top=8, min_score=0.20):
    if not label_item:
        return []
    ymin = label_item["y1"] - extra_top
    if next_label:
        ymax = min(label_item["y2"] + extra_bottom, next_label["y1"] - 6)
    else:
        ymax = label_item["y2"] + extra_bottom
    return tokens_in_region(
        items, label_item["x2"] + 6, working_xmax,
        ymin, ymax, min_score=min_score
    )


def extract_two_side_band(items, label_item, working_xmax, split_x, next_label=None, normalizer="simple", banned=None, extra_bottom=26):
    if not label_item:
        return "", ""
    band_tokens = extract_band_tokens(items, label_item, working_xmax, next_label=next_label, extra_bottom=extra_bottom)
    left, right = split_left_right(band_tokens, split_x, label_item["x2"])
    banned = banned or set()
    if normalizer == "name":
        return normalize_name(left), normalize_name(right)
    return normalize_simple_row(left, banned=banned), normalize_simple_row(right, banned=banned)


def parse_day_number(token: str):
    digits = re.sub(r"\D", "", token)
    if not digits:
        return None
    candidates = []
    if 1 <= int(digits) <= 31:
        candidates.append(int(digits))
    if len(digits) >= 2:
        first2 = int(digits[:2])
        if 1 <= first2 <= 31:
            candidates.append(first2)
    if len(digits) >= 2:
        last2 = int(digits[-2:])
        if 1 <= last2 <= 31:
            candidates.append(last2)
    first1 = int(digits[0])
    if 1 <= first1 <= 9:
        candidates.append(first1)
    if not candidates:
        return None
    for val in candidates:
        if val >= 10:
            return val
    return candidates[0]


def parse_date_from_string(text: str) -> str:
    nt = norm_text(text)
    if not nt:
        return ""
    tokens = re.findall(r"\d+|[A-Z]+", nt)
    if not tokens:
        return ""
    month_idx, month_val = None, None
    for i, tok in enumerate(tokens):
        m = normalize_month_word(tok)
        if m in MONTHS:
            month_idx, month_val = i, m
            break
    if month_idx is None:
        return ""
    year = None
    for tok in tokens[month_idx + 1:]:
        if re.fullmatch(r"\d{4}", tok):
            year = tok
            break
    if year is None:
        for tok in tokens:
            if re.fullmatch(r"\d{4}", tok):
                year = tok
                break
    if year is None:
        return ""
    day = None
    for tok in reversed(tokens[:month_idx]):
        parsed = parse_day_number(tok)
        if parsed is not None:
            day = parsed
            break
    if day is None:
        for tok in tokens[month_idx + 1:]:
            if tok == year:
                continue
            parsed = parse_day_number(tok)
            if parsed is not None:
                day = parsed
                break
    if day is None:
        return ""
    return f"{day:02d} {month_val} {year}"


def extract_date_candidates(tokens):
    rows = group_rows(tokens, y_tol=18)
    found = []
    for row in rows:
        row = sorted(row, key=lambda x: x["x1"])
        for it in row:
            parsed = parse_date_from_string(it["text"])
            if parsed:
                found.append({"text": parsed, "x1": it["x1"], "y1": it["y1"]})
        for window in range(2, 6):
            for i in range(len(row) - window + 1):
                combined = " ".join(clean_text(row[j]["text"]) for j in range(i, i + window))
                parsed = parse_date_from_string(combined)
                if parsed:
                    found.append({"text": parsed, "x1": row[i]["x1"],
                                  "y1": min(row[j]["y1"] for j in range(i, i + window))})
    unique, seen = [], set()
    for d in sorted(found, key=lambda z: (z["x1"], z["y1"], z["text"])):
        key = (d["text"], round(d["x1"] / 8), round(d["y1"] / 8))
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def parse_named_date(date_str):
    if not date_str:
        return None
    text = norm_text(date_str)
    parts = text.split()
    if len(parts) >= 3:
        day, month, year = parts[0], normalize_month_word(parts[1]), parts[2]
        if re.fullmatch(r"\d{1,2}", day) and month in MONTHS and re.fullmatch(r"\d{4}", year):
            try:
                return datetime.strptime(f"{int(day):02d} {month} {year}", "%d %B %Y")
            except Exception:
                return None
    return None


def compute_age_from_dates(dob_str, marriage_date_str):
    dob_dt = parse_named_date(dob_str)
    mar_dt = parse_named_date(marriage_date_str)
    if not dob_dt or not mar_dt:
        return ""
    age = mar_dt.year - dob_dt.year
    if (mar_dt.month, mar_dt.day) < (dob_dt.month, dob_dt.day):
        age -= 1
    if 0 <= age <= 120:
        return str(age)
    return ""


def extract_dob_and_age(side_tokens, marriage_date_text=""):
    side_tokens = sorted(side_tokens, key=lambda x: (x["cy"], x["x1"]))
    date_candidates = extract_date_candidates(side_tokens)
    dob = date_candidates[0]["text"] if date_candidates else ""
    computed_age = compute_age_from_dates(dob, marriage_date_text)
    if computed_age:
        return dob, computed_age
    used_parts = set(dob.split()) if dob else set()
    age_candidates = []
    for it in side_tokens:
        nt = norm_text(it["text"])
        if re.fullmatch(r"\d{1,3}", nt):
            val = int(nt)
            if 0 <= val <= 120 and nt not in used_parts:
                age_candidates.append((it["score"], it["x1"], val))
    if not age_candidates:
        return dob, ""
    age_candidates.sort(key=lambda x: (-(18 <= x[2] <= 80), -x[0], -x[1]))
    return dob, str(age_candidates[0][2])


def normalize_place(text: str) -> str:
    text = re.sub(r"\bPLACE OF MARRIAGE\b", " ", text, flags=re.I)
    text = re.sub(r"\bADDRESS\b", " ", text, flags=re.I)
    text = re.sub(r"\bMANILA CITY HALL\b", " ", text, flags=re.I)
    text = re.sub(r"\(.*?OFFICE OF THE.*?\)", " ", text, flags=re.I)
    text = re.sub(r"\.{2,}", " ", text)
    text = re.sub(r"(?<=\w)\.(?=\w)", "", text)
    text = re.sub(r"\bEBMITA\b", "ERMITA", text, flags=re.I)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    spaced = text
    for landmark in sorted(PLACE_LANDMARKS, key=len, reverse=True):
        spaced = re.sub(
            rf"(?i)(?<=[A-Za-z0-9])({re.escape(landmark)})",
            r" \1",
            spaced,
        )
    text = re.sub(r"\s+", " ", spaced).strip(" .:-,")
    return text


def normalize_marriage_date_text(tokens):
    rows = group_rows(tokens, y_tol=18)
    best_text, best_score = "", -1
    for row in rows:
        row = sorted(row, key=lambda x: x["x1"])
        row_text = join_tokens(row)
        nt = norm_text(row_text)
        date_val = parse_date_from_string(row_text)
        time_val = ""
        for t in row:
            s = clean_text(t["text"])
            m = re.search(r"(\d{1,2}:\d{2}\s?(AM|PM)?)", s, re.I)
            if m:
                time_val = m.group(1).upper().replace(" ", "")
                break
        score = 0
        if date_val:
            score += 4
        if time_val:
            score += 2
        if any(mon in nt for mon in MONTHS):
            score += 2
        if re.search(r"\d{4}", nt):
            score += 1
        if score > best_score:
            best_score = score
            if date_val and time_val:
                best_text = f"{date_val} {time_val}"
            elif date_val:
                best_text = date_val
            elif time_val:
                best_text = time_val
    return best_text


def find_marriage_date_fallback(items, place_mar_label, working_xmax):
    if not place_mar_label:
        return ""
    region = tokens_in_region(
        items, 0, working_xmax,
        place_mar_label["y2"] + 10, place_mar_label["y2"] + 110, min_score=0.20
    )
    if not region:
        return ""
    return normalize_marriage_date_text(region)


def extract_registry_number(items, img_w, img_h, working_xmax):
    """Read municipal/PSA registry numbers from the header, including split OCR tokens."""
    region = tokens_in_region(items, img_w * 0.28, img_w * 0.99, 0, img_h * 0.24, min_score=0.12)
    label = find_best_label(
        items,
        patterns=["REGISTRY NO", "REGISTRY NUMBER", "REGISTR Y NO", "REG. NO", "REG NO"],
        x_min=img_w * 0.20, x_max=img_w * 0.99,
        y_min=0, y_max=img_h * 0.28,
        min_score=0.12,
    )
    if label:
        near = tokens_in_region(
            items, label["x1"] - 20, img_w * 0.99,
            label["y1"] - 18, label["y2"] + 55, min_score=0.12
        )
        region = near + region

    vals = []
    ordered = sorted(region, key=lambda x: (x["cy"], x["x1"]))

    def consider(raw: str, score: float):
        t = re.sub(r"\s*-\s*", "-", clean_text(raw))
        compact = re.sub(r"\s+", "", t)
        if re.fullmatch(r"\d{4}-\d{3,8}", compact):
            vals.append((score + 0.35, compact))
        elif re.fullmatch(r"\d{2,8}-\d{2,8}", compact):
            vals.append((score + 0.2, compact))
        elif re.fullmatch(r"[A-Z0-9]{2,8}-\d{2,4}-[A-Z0-9]{2,10}", compact, flags=re.I):
            vals.append((score + 0.25, compact.upper()))
        elif re.fullmatch(r"\d{6,12}", compact):
            vals.append((score * 0.4, compact))

    for it in ordered:
        consider(it["text"], it["score"])

    for i, it in enumerate(ordered[:-1]):
        nxt = ordered[i + 1]
        if abs(it["cy"] - nxt["cy"]) > 22:
            continue
        if nxt["x1"] - it["x2"] > img_w * 0.12:
            continue
        a = re.sub(r"\D", "", it["text"])
        b = re.sub(r"\D", "", nxt["text"])
        if 2 <= len(a) <= 6 and 3 <= len(b) <= 8:
            consider(f"{a}-{b}", (it["score"] + nxt["score"]) / 2)

    if not vals:
        return ""
    vals.sort(key=lambda x: -x[0])
    return vals[0][1]


def extract_date_of_registration(items, img_w, img_h, marriage_date_text=""):
    """Header date, usually to the right of the registry number."""
    label = find_best_label(
        items,
        patterns=["DATE OF REGISTRATION", "DATE RECEIVED", "RECEIVED IN THIS OFFICE", "RECEIVED"],
        x_min=img_w * 0.20, x_max=img_w * 0.99,
        y_min=0, y_max=img_h * 0.30,
        min_score=0.12,
        forbidden=["DATE OF MARRIAGE", "DATE OF BIRTH"],
    )
    regions = []
    if label:
        regions.append(tokens_in_region(
            items, label["x1"] - 10, img_w * 0.99,
            label["y1"] - 16, label["y2"] + 70, min_score=0.12
        ))
    regions.append(tokens_in_region(items, img_w * 0.42, img_w * 0.99, 0, img_h * 0.22, min_score=0.18))
    found = []
    seen = set()
    marriage_norm = parse_date_from_string(marriage_date_text)
    for region in regions:
        for cand in extract_date_candidates(region):
            parsed = parse_date_from_string(cand["text"])
            if not parsed or parsed in seen:
                continue
            seen.add(parsed)
            found.append(parsed)
    if not found:
        return ""
    if marriage_norm:
        others = [d for d in found if d != marriage_norm]
        if others:
            return others[0]
    return found[0]


def extract_parent_pair(items, label, working_xmax, split_x, stop_label=None):
    if not label:
        return "", ""
    ymax = label["y2"] + 32
    if stop_label and stop_label["y1"] > label["y1"] + 4:
        ymax = min(ymax, stop_label["y1"] - 4)
    tokens = tokens_in_region(
        items, label["x2"] + 4, working_xmax,
        label["y1"] - 8, ymax, min_score=0.16
    )
    left, right = split_left_right(tokens, split_x, label["x2"])
    return normalize_name(left), normalize_name(right)


def resolve_duplicate_parents(items, father_label, mother_label, working_xmax, split_x, h_f, h_m, w_f, w_m):
    same_h = bool(h_f and h_m and norm_text(h_f) == norm_text(h_m))
    same_w = bool(w_f and w_m and norm_text(w_f) == norm_text(w_m))
    if not (same_h or same_w) or not father_label:
        return h_f, h_m, w_f, w_m
    y1 = mother_label["y2"] + 40 if mother_label else father_label["y2"] + 90
    tokens = tokens_in_region(
        items, father_label["x2"] + 4, working_xmax,
        father_label["y1"] - 6, y1, min_score=0.14
    )
    name_rows = []
    for row in group_rows(tokens, y_tol=13):
        left, right = split_left_right(row, split_x, father_label["x2"])
        ln, rn = normalize_name(left), normalize_name(right)
        if ln or rn:
            name_rows.append((ln, rn))
    if len(name_rows) >= 2:
        return (
            name_rows[0][0] or h_f,
            name_rows[1][0],
            name_rows[0][1] or w_f,
            name_rows[1][1],
        )
    if same_h:
        h_m = ""
    if same_w:
        w_m = ""
    return h_f, h_m, w_f, w_m


def extract_citizenship_pair(items, label, working_xmax, split_x, next_label, img_w, img_h):
    h, w = "", ""
    if label:
        h, w = extract_two_side_band(
            items, label, working_xmax, split_x,
            next_label=next_label, banned={"CITIZENSHIP", "CITIZENAHIP"}, extra_bottom=36
        )
    h = normalize_citizenship_value(h)
    w = normalize_citizenship_value(w)
    if h and w:
        return h, w
    y_min = label["y1"] - 10 if label else img_h * 0.16
    y_max = (next_label["y1"] - 4) if next_label else (label["y2"] + 50 if label else img_h * 0.34)
    band = tokens_in_region(items, img_w * 0.12, working_xmax, y_min, y_max, min_score=0.12)
    left, right = split_left_right(band, split_x, label["x2"] if label else img_w * 0.12)
    if not h:
        h = normalize_citizenship_value(join_tokens(left))
    if not w:
        w = normalize_citizenship_value(join_tokens(right))
    return h, w


def _field_confidence(field_name: str, value: str, source: str = "layout") -> str:
    v = (value or "").strip()
    if not v:
        return "LOW"
    n = norm_text(v)

    if source == "template":
        return "MEDIUM"

    if field_name in {"Date of Marriage", "Date of Registration"}:
        return "HIGH" if parse_date_from_string(v) else "MEDIUM"
    if field_name in {"Husband Age", "Wife Age"}:
        return "HIGH" if re.fullmatch(r"\d{1,3}", n) else "MEDIUM"
    if field_name == "Registry Number":
        compact = n.replace(" ", "")
        if re.fullmatch(r"[A-Z0-9]{2,10}[-/][A-Z0-9]{2,10}", compact):
            return "HIGH"
        return "MEDIUM"
    if field_name in {
        "Husband Name", "Wife Name", "Place of Marriage", "Husband Citizenship",
        "Wife Citizenship", "Husband Civil Status", "Wife Civil Status",
        "Husband Father", "Husband Mother", "Wife Father", "Wife Mother"
    }:
        return "HIGH" if alpha_count(v) >= 4 else "MEDIUM"
    return "MEDIUM"


# =========================================================
# MAIN NAME EXTRACTION FUNCTION (FIXED)
# =========================================================
def extract_names_from_band(items, name_label, dob_label, working_xmax, split_x, img_w=None, img_h=None):
    """
    Extract husband and wife names from the name band.
    
    Strategy: Use image proportions to find the region between top of form
    and the DOB label, then identify name tokens and split by column.
    """
    # Get image dimensions
    if img_w is None and items:
        img_w = max(it["x2"] for it in items)
    if img_h is None and items:
        img_h = max(it["y2"] for it in items)
    img_w = img_w or 600
    img_h = img_h or 800
    
    # Define search region - names are typically in upper portion of form
    # From ~8% to ~25% of image height
    y_start = int(img_h * 0.08)
    y_end = int(img_h * 0.25)
    
    # If we have DOB label, use its position as upper bound
    if dob_label:
        y_end = min(y_end, dob_label["y1"] - 5)
    
    # If we have name label, use its position as lower bound
    if name_label:
        y_start = max(y_start, name_label["y2"])
    
    # Search from left side of form content to right side
    x_start = int(img_w * 0.12)
    x_end = working_xmax
    
    # Get all tokens in the name region with low threshold
    tokens = tokens_in_region(
        items, x_start, x_end, y_start, y_end, min_score=0.08
    )
    
    if DEBUG_NAME_BAND:
        print("\n========== NAME REGION SEARCH ==========")
        print(f"Search region: x={x_start}-{x_end}, y={y_start}-{y_end}")
        print(f"Found {len(tokens)} tokens in region:")
        for t in sorted(tokens, key=lambda x: (x["cy"], x["x1"])):
            print(f'  "{t["text"]}" | cx={t["cx"]:.1f} cy={t["cy"]:.1f} score={t["score"]:.2f}')
        print(f"Column split x: {split_x}")
        print("======================================\n")
    
    if not tokens:
        return "", ""
    
    # Filter tokens to keep only potential name parts
    filtered = []
    for t in tokens:
        txt = clean_text(t["text"])
        nt = norm_text(txt)
        
        # Skip form metadata
        if is_form_metadata(txt):
            continue
        # Skip pure numbers
        if re.fullmatch(r"\d+", nt):
            continue
        if is_date_noise_token(nt):
            continue
        # Skip very short tokens
        if len(nt) < 2:
            continue
        # Skip common label words
        if nt in {"HUSBAND", "WIFE", "NAME", "OF", "PARTIES", "DATE", "BIRTH", 
                     "AGE", "PLACE", "SEX", "CIVIL", "STATUS", "RELIGION", 
                     "CITIZENSHIP", "FATHER", "MOTHER", "MARRIAGE", "FORM", 
                     "NO", "REPUBLIC", "PHILIPPINES", "MANILA", "OFFICE", 
                     "REGISTRAR", "LOCAL", "THE", "AND", "FOR", "COPY"}:
            continue
        # Must have at least 2 alphabetic characters
        if alpha_count(txt) < 2:
            continue
        filtered.append(t)
    
    if DEBUG_NAME_BAND:
        print("\n========== FILTERED NAME TOKENS ==========")
        for t in sorted(filtered, key=lambda x: (x["cy"], x["x1"])):
            print(f'  "{t["text"]}" | cx={t["cx"]:.1f} cy={t["cy"]:.1f}')
        print("==========================================\n")
    
    # Try to split into left/right columns and extract names
    if filtered:
        # Use the column split position
        left, right = split_left_right(filtered, split_x, x_start)
        
        h = normalize_name(left)
        w = normalize_name(right)
        
        if DEBUG_NAME_BAND:
            print(f"Initial split: husband='{h}', wife='{w}'")
        
        if h or w:
            return h, w
    
    # Fallback: try with all tokens minus form metadata
    all_filtered = [t for t in tokens if not is_form_metadata(t["text"])]
    if all_filtered:
        left, right = split_left_right(all_filtered, split_x, x_start)
        h = normalize_name(left)
        w = normalize_name(right)
        
        if DEBUG_NAME_BAND:
            print(f"Fallback split: husband='{h}', wife='{w}'")
        
        if h or w:
            return h, w
    
    # Final fallback: try different split positions
    for try_ratio in [0.5, 0.45, 0.55, 0.4, 0.6, 0.35, 0.65]:
        try_split = x_start + (x_end - x_start) * try_ratio
        left_test, right_test = split_left_right(all_filtered, try_split, x_start)
        h_test = normalize_name(left_test)
        w_test = normalize_name(right_test)
        if h_test or w_test:
            if DEBUG_NAME_BAND:
                print(f"Found with split ratio {try_ratio}: husband='{h_test}', wife='{w_test}'")
            return h_test, w_test

    return "", ""


# =========================================================
# BUILD ITEMS FROM OCR RESULT
# =========================================================
def build_items(result):
    items = []
    for page in result:
        texts = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])
        polys = page.get("dt_polys", [])
        for text, score, box in zip(texts, scores, polys):
            text = str(text).strip()
            if not text:
                continue
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            item = {
                "text": text,
                "score": float(score),
                "x1": int(min(xs)), "y1": int(min(ys)),
                "x2": int(max(xs)), "y2": int(max(ys)),
            }
            item["cx"] = (item["x1"] + item["x2"]) / 2.0
            item["cy"] = (item["y1"] + item["y2"]) / 2.0
            item["w"] = item["x2"] - item["x1"]
            item["h"] = item["y2"] - item["y1"]
            items.append(item)
    items.sort(key=lambda x: (x["cy"], x["x1"]))
    return items


# =========================================================
# MAIN: extract_marriage_data
# =========================================================
def extract_marriage_data(img_path: str) -> Dict[str, Any]:
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {img_path}")

    img = preprocess_image(img)

    if DEBUG_PREPROCESS:
        cv2.imwrite("debug_preprocessed_marriage.jpg", img)

    img_h, img_w = img.shape[:2]
    result = run_ocr_on_image(img)

    # Template-first extraction (folder-based JSON templates).
    tpl_map: Dict[str, str] = {}
    try:
        ocr_text = ocr_pages_to_text(result)
        tpl = extract_from_ocr_text(ocr_text, doc_type="marriage", best_effort=True)
        fields = (tpl.get("fields") or {}) if isinstance(tpl, dict) else {}
        if DEBUG_TEMPLATE_MATCH:
            found = sum(1 for v in fields.values() if v)
            print(
                f"[OCR MARRIAGE TEMPLATE] path={tpl.get('template_path')} "
                f"score={tpl.get('match_score')} fields={found}/{len(fields)}"
            )
        found = sum(1 for v in fields.values() if v)
        if tpl.get("template_path") and found >= 1:
            def _v(k: str) -> str:
                val = fields.get(k)
                return str(val).strip() if val else ""

            tpl_map = {
                "Registry Number": _v("registry_number"),
                "Date of Registration": _v("date_of_registration"),
                "Husband Name": sanitize_person_name(_v("husband_name")),
                "Wife Name": sanitize_person_name(_v("wife_name")),
                "Date of Marriage": _v("date_of_marriage"),
                "Place of Marriage": normalize_place(_v("place_of_marriage")),
            }
    except Exception:
        pass

    items = build_items(result)

    if DEBUG_DRAW_BOXES:
        draw_debug_boxes(img, items)

    if DEBUG_OCR_RAW:
        print("\n========== RAW OCR ITEMS ==========")
        for it in items:
            print(f'{it["text"]} | ({it["x1"]},{it["y1"]})-({it["x2"]},{it["y2"]}) score={it["score"]:.2f}')
        print("===================================\n")

    # LABELS / LAYOUT
    working_xmax = infer_working_xmax(items, img_w, img_h)

    name_label = find_best_label(
        items,
        patterns=["NAME OF CONTRACTING PARTIES", "NAME OF CONTRACTING",
                  "CONTRACTING PARTIES", "CONTRACTING PARTIEN", "NAME OF PARTIES", "CONTRACTING"],
        x_min=0, x_max=img_w * 0.40,
        y_min=img_h * 0.04, y_max=img_h * 0.28,
        min_score=0.15,
    )

    dob_label = find_best_label(
        items,
        patterns=["DATE OF BIRTH AGE", "DATE OF BIRTH/AGE", "DATE OF BIRTH", "BIRTH AGE"],
        x_min=0, x_max=img_w * 0.32,
        y_min=img_h * 0.10, y_max=img_h * 0.32
    )

    pob_label = find_best_label(
        items,
        patterns=["PLACE OF BIRTH"],
        x_min=0, x_max=img_w * 0.30,
        y_min=img_h * 0.14, y_max=img_h * 0.32
    )

    sex_label = find_best_label(
        items,
        patterns=["SEX MALE OR FEMALE", "SEX"],
        x_min=0, x_max=img_w * 0.30,
        y_min=img_h * 0.16, y_max=img_h * 0.36
    )

    religion_label = find_best_label(
        items,
        patterns=["RELIGION"],
        x_min=0, x_max=img_w * 0.30,
        y_min=img_h * 0.20, y_max=img_h * 0.45
    )

    cit_top_label = None
    if sex_label and religion_label:
        cit_top_label = find_best_label(
            items,
            patterns=["CITIZENSHIP", "CITIZENAHIP"],
            x_min=0, x_max=img_w * 0.30,
            y_min=sex_label["y2"] + 2,
            y_max=religion_label["y1"] - 2,
            min_score=0.20
        )

    if cit_top_label is None:
        cit_top_label = find_best_label(
            items,
            patterns=["CITIZENSHIP", "CITIZENAHIP"],
            x_min=0, x_max=img_w * 0.30,
            y_min=img_h * 0.18, y_max=img_h * 0.30
        )

    civil_label = find_best_label(
        items,
        patterns=["CIVIL STATUS"],
        x_min=0, x_max=img_w * 0.30,
        y_min=img_h * 0.22, y_max=img_h * 0.48
    )

    father_label = find_best_label(
        items,
        patterns=["NAME OF FATHER", "FATHER"],
        x_min=0, x_max=img_w * 0.32,
        y_min=img_h * 0.24, y_max=img_h * 0.56
    )

    mother_min_y = (father_label["y2"] + 8) if father_label else img_h * 0.30
    mother_label = find_best_label(
        items,
        patterns=["NAME OF MOTHER", "MOTHER"],
        x_min=0, x_max=img_w * 0.32,
        y_min=mother_min_y, y_max=img_h * 0.66
    )
    if father_label and mother_label and mother_label["cy"] <= father_label["cy"] + 10:
        mother_label = find_best_label(
            items,
            patterns=["NAME OF MOTHER", "MOTHER"],
            x_min=0, x_max=img_w * 0.32,
            y_min=father_label["y2"] + 12, y_max=img_h * 0.66
        )

    father_cit_label = find_label_below(
        items, father_label,
        patterns=["CITIZENSHIP", "CITIZENAHIP"],
        y_min_offset=2, y_max_offset=80,
        x_max=img_w * 0.30
    )

    mother_cit_label = find_label_below(
        items, mother_label,
        patterns=["CITIZENSHIP", "CITIZENAHIP"],
        y_min_offset=2, y_max_offset=80,
        x_max=img_w * 0.30
    )

    place_mar_label = find_best_label(
        items,
        patterns=["PLACE OF MARRIAGE"],
        x_min=0, x_max=img_w * 0.30,
        y_min=img_h * 0.42, y_max=img_h * 0.72
    )

    date_mar_label = find_best_label(
        items,
        patterns=["DATE OF MARRIAGE", "TIME OF MARRIAGE", "DATE AND TIME OF MARRIAGE", "DATE", "DATE:"],
        x_min=0, x_max=img_w * 0.45,
        y_min=img_h * 0.40, y_max=img_h * 0.78,
        forbidden=["DATE OF BIRTH", "DATE OF REGISTRATION"]
    )

    if DEBUG_LABELS:
        print("\n========= DETECTED LABELS =========")
        def show(label, name):
            if label:
                print(f"{name}: {label['text']}  (y={label['cy']:.1f})")
            else:
                print(f"{name}: NOT FOUND")
        show(name_label, "NAME LABEL")
        show(dob_label, "DOB LABEL")
        show(pob_label, "PLACE OF BIRTH")
        show(sex_label, "SEX")
        show(cit_top_label, "CITIZENSHIP")
        show(civil_label, "CIVIL STATUS")
        show(father_label, "FATHER")
        show(mother_label, "MOTHER")
        show(place_mar_label, "PLACE OF MARRIAGE")
        show(date_mar_label, "DATE OF MARRIAGE")
        print("===================================\n")

    split_x = infer_column_split_from_headers(items, name_label, working_xmax, img_w, img_h)
    if split_x is None:
        split_x = infer_column_split_from_name(items, name_label, working_xmax, img_w)

    if DEBUG_LABELS:
        print("COLUMN SPLIT POSITION:", split_x)

    # EXTRACTION
    data = {"husband": {}, "wife": {}, "shared": {}}

    data["shared"]["Registry Number"] = extract_registry_number(items, img_w, img_h, working_xmax)

    if place_mar_label:
        lower_y = date_mar_label["y1"] - 6 if date_mar_label and date_mar_label["y1"] > place_mar_label["y2"] else place_mar_label["y2"] + 55
        if lower_y <= place_mar_label["y2"]:
            lower_y = place_mar_label["y2"] + 55
        region = tokens_in_region(
            items, min(place_mar_label["x2"], img_w * 0.18), working_xmax,
            place_mar_label["y1"] - 4, lower_y, min_score=0.12
        )
        place_text = normalize_place(join_tokens([
            it for it in region
            if "PLACE" not in norm_text(it["text"]) or "MARRIAGE" not in norm_text(it["text"])
        ]))
        if place_text:
            data["shared"]["Place of Marriage"] = place_text

    marriage_date_text = ""
    if date_mar_label:
        region = tokens_in_region(
            items, date_mar_label["x1"], working_xmax,
            date_mar_label["y1"] - 14, date_mar_label["y2"] + 34, min_score=0.20
        )
        marriage_date_text = normalize_marriage_date_text(region)

    if not marriage_date_text:
        marriage_date_text = find_marriage_date_fallback(items, place_mar_label, working_xmax)

    if marriage_date_text:
        data["shared"]["Date of Marriage"] = marriage_date_text

    data["shared"]["Date of Registration"] = extract_date_of_registration(
        items, img_w, img_h, marriage_date_text
    )

    # Extract husband/wife NAMES - using improved function
    h, w = extract_names_from_band(items, name_label, dob_label, working_xmax, split_x, img_w, img_h)
    h, w = sanitize_person_name(h), sanitize_person_name(w)
    if h:
        data["husband"]["Name"] = h
    if w:
        data["wife"]["Name"] = w

    if dob_label:
        band_tokens = extract_band_tokens(
            items, dob_label, working_xmax,
            next_label=pob_label, extra_bottom=48, extra_top=10, min_score=0.15
        )
        left, right = split_left_right(band_tokens, split_x, dob_label["x2"])
        h_dob, h_age = extract_dob_and_age(left, marriage_date_text)
        w_dob, w_age = extract_dob_and_age(right, marriage_date_text)
        if h_dob:
            data["husband"]["Date of Birth"] = h_dob
        if h_age:
            data["husband"]["Age"] = h_age
        if w_dob:
            data["wife"]["Date of Birth"] = w_dob
        if w_age:
            data["wife"]["Age"] = w_age

    h, w = extract_two_side_band(items, pob_label, working_xmax, split_x, next_label=sex_label, banned={"PLACE OF BIRTH"}, extra_bottom=28)
    if h:
        data["husband"]["Place of Birth"] = h
    if w:
        data["wife"]["Place of Birth"] = w

    h, w = extract_two_side_band(items, sex_label, working_xmax, split_x, next_label=cit_top_label, banned={"SEX", "MALE OR FEMALE"}, extra_bottom=20)
    if h:
        data["husband"]["Sex"] = normalize_sex_value(h)
    if w:
        data["wife"]["Sex"] = normalize_sex_value(w)

    h, w = extract_citizenship_pair(
        items, cit_top_label, working_xmax, split_x, religion_label, img_w, img_h
    )
    if h:
        data["husband"]["Citizenship"] = h
    if w:
        data["wife"]["Citizenship"] = w

    h, w = extract_two_side_band(items, religion_label, working_xmax, split_x, next_label=civil_label, banned={"RELIGION"}, extra_bottom=24)
    if h:
        data["husband"]["Religion"] = apply_common_word_fix(h)
    if w:
        data["wife"]["Religion"] = apply_common_word_fix(w)

    h, w = extract_two_side_band(items, civil_label, working_xmax, split_x, next_label=father_label, banned={"CIVIL STATUS"}, extra_bottom=24)
    if h:
        data["husband"]["Civil Status"] = h
    if w:
        data["wife"]["Civil Status"] = w

    h_f, w_f = extract_parent_pair(
        items, father_label, working_xmax, split_x,
        stop_label=father_cit_label or mother_label,
    )
    h_m, w_m = extract_parent_pair(
        items, mother_label, working_xmax, split_x,
        stop_label=mother_cit_label or place_mar_label,
    )
    h_f, h_m, w_f, w_m = resolve_duplicate_parents(
        items, father_label, mother_label, working_xmax, split_x, h_f, h_m, w_f, w_m
    )
    if h_f:
        data["husband"]["Father"] = h_f
    if w_f:
        data["wife"]["Father"] = w_f
    if h_m:
        data["husband"]["Mother"] = h_m
    if w_m:
        data["wife"]["Mother"] = w_m

    h, w = extract_two_side_band(items, father_cit_label, working_xmax, split_x, next_label=mother_label, banned={"CITIZENSHIP", "CITIZENAHIP"}, extra_bottom=24)
    if h:
        data["husband"]["Father Citizenship"] = apply_common_word_fix(h)
    if w:
        data["wife"]["Father Citizenship"] = apply_common_word_fix(w)

    h, w = extract_two_side_band(items, mother_cit_label, working_xmax, split_x, next_label=place_mar_label, banned={"CITIZENSHIP", "CITIZENAHIP"}, extra_bottom=24)
    if h:
        data["husband"]["Mother Citizenship"] = apply_common_word_fix(h)
    if w:
        data["wife"]["Mother Citizenship"] = apply_common_word_fix(w)

    out = {
        "Registry Number": data["shared"].get("Registry Number", ""),
        "Date of Registration": data["shared"].get("Date of Registration", ""),
        "Date of Marriage": data["shared"].get("Date of Marriage", ""),
        "Place of Marriage": data["shared"].get("Place of Marriage", ""),
        "Husband Name": data["husband"].get("Name", ""),
        "Husband Age": data["husband"].get("Age", ""),
        "Husband Citizenship": data["husband"].get("Citizenship", ""),
        "Husband Civil Status": data["husband"].get("Civil Status", ""),
        "Husband Father": data["husband"].get("Father", ""),
        "Husband Mother": data["husband"].get("Mother", ""),
        "Wife Name": data["wife"].get("Name", ""),
        "Wife Age": data["wife"].get("Age", ""),
        "Wife Citizenship": data["wife"].get("Citizenship", ""),
        "Wife Civil Status": data["wife"].get("Civil Status", ""),
        "Wife Father": data["wife"].get("Father", ""),
        "Wife Mother": data["wife"].get("Mother", ""),
    }
    before_template = {k: (out.get(k) or "") for k in out.keys()}
    # Fill missing values with template results (if any).
    for k, v in (tpl_map or {}).items():
        if v and not (out.get(k) or "").strip():
            out[k] = v
    ordered_fields = [
        "Registry Number",
        "Date of Registration",
        "Date of Marriage",
        "Place of Marriage",
        "Husband Name",
        "Husband Age",
        "Husband Citizenship",
        "Husband Civil Status",
        "Husband Father",
        "Husband Mother",
        "Wife Name",
        "Wife Age",
        "Wife Citizenship",
        "Wife Civil Status",
        "Wife Father",
        "Wife Mother",
    ]
    confidence_map: Dict[str, str] = {}
    source_map: Dict[str, str] = {}
    for key in ordered_fields:
        val = (out.get(key) or "").strip()
        is_template_fill = (
            not (before_template.get(key) or "").strip()
            and bool(val)
            and bool((tpl_map or {}).get(key))
        )
        source = "template" if is_template_fill else "layout"
        source_map[key] = source
        confidence_map[key] = _field_confidence(key, val, source=source)
    out["__confidence__"] = confidence_map
    out["__source__"] = source_map
    return out

