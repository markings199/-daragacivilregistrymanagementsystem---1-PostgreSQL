"""
Birth certificate OCR extraction.
Fixed implementation - addresses extraction issues with better field detection.
"""
import os
import re
import tempfile
import difflib
from typing import Dict, Any, List

import cv2
from ocr_shared import run_ocr_on_image_path


# =========================================================
# CONFIG
# =========================================================
CROP_LEFT = 60
CROP_RIGHT = 60
DEBUG_OCR_RAW = False
DEBUG_LABELS = False


# =========================================================
# PREPROCESS: CROP
# =========================================================
def create_temp_cropped_image(image_path, crop_left, crop_right):
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    h, w = img.shape[:2]

    if crop_left < 0 or crop_right < 0:
        raise ValueError("Crop values must be 0 or greater.")

    if crop_left + crop_right >= w:
        raise ValueError("Left + right crop is too large for the image width.")

    cropped = img[:, crop_left:w - crop_right]

    ext = os.path.splitext(image_path)[1]
    if not ext:
        ext = ".jpg"

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    temp_path = temp_file.name
    temp_file.close()

    ok = cv2.imwrite(temp_path, cropped)
    if not ok:
        raise RuntimeError("Failed to write temporary cropped image.")

    return temp_path


# =========================================================
# CONSTANTS / FIXES
# =========================================================
MONTHS = {
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"
}

MONTH_FIXES = {
    "MABCK": "MARCH",
    "MARCK": "MARCH",
    "MARCHK": "MARCH",
    "JAMUARY": "JANUARY",
    "JANUARYY": "JANUARY",
}

OCR_WORD_FIXES = {
    "FILIFIRO": "FILIPINO",
    "PILIPINO": "FILIPINO",
    "FOMUTE": "FEMALE",
    "FOMALE": "FEMALE",
    "RELIBION": "RELIGION",
    "CETIZENSHIP": "CITIZENSHIP",
    "REGIATRY": "REGISTRY",
    "ROPUTFIC": "REPUBLIC",
    "PHLPPINS": "PHILIPPINES",
}

BAD_VALUE_KEYWORDS = {
    "DATE", "SIGNATURE", "NAME IN PRINT", "TITLE OF POSITION",
    "CITIZENSHIP", "RELIGION", "OCCUPATION", "AGE", "YEARS",
    "TOTAL NUMBER", "NO OF", "NO.", "PREPARED BY", "INFORMANT",
    "ATTENDANT", "CERTIFICATION", "RESIDENCE", "TYPE OF BIRTH",
    "BIRTH ORDER", "MULTIPLE", "BIRTHCHILD", "IF MULTIPLE",
    "FOR OCRG USE ONLY", "TO BE FILLED", "CIVIL REGISTRAR",
    "POPULATION REFERENCES", "REMARKS", "ANNOTATION"
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


def apply_word_fixes(text: str) -> str:
    out = str(text)
    for bad, good in OCR_WORD_FIXES.items():
        out = re.sub(rf"\b{re.escape(bad)}\b", good, out, flags=re.I)
    return out


def norm_text(t: str) -> str:
    t = clean_text(t).upper()
    t = apply_word_fixes(t)
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def compact_text(t: str) -> str:
    return re.sub(r"\s+", "", norm_text(t))


def alpha_count(t: str) -> int:
    return sum(ch.isalpha() for ch in str(t))


def tokens_in_region(items, xmin, xmax, ymin, ymax, min_score=0.20):
    out = []
    for it in items:
        if it["score"] < min_score:
            continue
        if xmin <= it["cx"] <= xmax and ymin <= it["cy"] <= ymax:
            out.append(it)
    out.sort(key=lambda x: (x["cy"], x["x1"]))
    return out


def group_rows(tokens, y_tol=12):
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


def pattern_score(text: str, patterns):
    nt = norm_text(text)
    ct = compact_text(text)

    best = 0.0
    for pat in patterns:
        p = norm_text(pat)
        pc = compact_text(pat)

        if all(tok in nt for tok in p.split()):
            best = max(best, 10.0 + len(p.split()))
            continue

        ratio = difflib.SequenceMatcher(None, ct, pc).ratio()
        if ratio >= 0.60:
            best = max(best, ratio * 10.0)

    return best


def find_best_label(items, patterns, x_min=None, x_max=None, y_min=None, y_max=None, min_score=0.20, min_match_score=5.8):
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

        ps = pattern_score(it["text"], patterns)
        if ps < min_match_score:
            continue

        tup = (ps, it["score"], -len(norm_text(it["text"])))
        if best is None or tup > best_tuple:
            best = it
            best_tuple = tup

    return best


def find_child_name_label(items, img_w, img_h):
    candidates = []

    for it in items:
        if it["score"] < 0.20:
            continue

        nt = norm_text(it["text"])
        ct = compact_text(it["text"])

        if it["cx"] > img_w * 0.22:
            continue
        if it["cy"] < img_h * 0.08 or it["cy"] > img_h * 0.20:
            continue

        if nt in {"1 NAME", "1NAME", "I NAME"} or ct in {"1NAME", "INAME"}:
            candidates.append(it)
            continue

        if re.fullmatch(r"[1I][ .]*NAME", nt):
            candidates.append(it)
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x["cy"], x["x1"]))
    return candidates[0]


def find_label_below(items, anchor_label, patterns, y_min_offset=2, y_max_offset=95, x_max=None, min_match_score=5.8):
    if not anchor_label:
        return None

    return find_best_label(
        items,
        patterns=patterns,
        x_min=0,
        x_max=x_max,
        y_min=anchor_label["y2"] + y_min_offset,
        y_max=anchor_label["y2"] + y_max_offset,
        min_score=0.20,
        min_match_score=min_match_score
    )


def normalize_month_word(word: str) -> str:
    w = norm_text(word)
    if w in MONTH_FIXES:
        return MONTH_FIXES[w]
    if w in MONTHS:
        return w
    match = difflib.get_close_matches(w, list(MONTHS), n=1, cutoff=0.55)
    if match:
        return match[0]
    return w


def normalize_simple_text(text: str) -> str:
    text = apply_word_fixes(clean_text(text))

    # Filter out bad keywords
    for bad in BAD_VALUE_KEYWORDS:
        text = re.sub(rf"\b{re.escape(bad)}\b", " ", text, flags=re.I)

    text = re.sub(r"\b\d+[A-Z]?\.\s*", " ", text, flags=re.I)
    
    # Remove form noise patterns
    text = re.sub(r"\[.*?\]", " ", text)  # Remove bracketed content
    text = re.sub(r"TYPE\s*OF\s*BIRTH.*", " ", text, flags=re.I)
    text = re.sub(r"IF\s*MULTIPLE.*", " ", text, flags=re.I)
    text = re.sub(r"BIRTHCHILD.*", " ", text, flags=re.I)

    words = []
    for w in text.split():
        wn = norm_text(w)
        if len(wn) <= 1:
            continue
        if re.fullmatch(r"[A-Z]{1,2}", wn):
            continue
        words.append(w)

    text = " ".join(words)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text


def parse_date_from_string(text: str) -> str:
    raw = apply_word_fixes(clean_text(text)).upper()
    raw = raw.replace(",", " ").replace("/", " ").replace("-", " ")
    raw = re.sub(r"\s+", " ", raw).strip()

    month_pattern = (
        r"JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
        r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|MABCK|MARCK|MARCHK|JAMUARY|"
        r"JAN|FEB|MARC?H?|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC"
    )

    # DD MONTH YYYY
    m = re.search(rf"\b(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}})\b", raw)
    if m:
        try:
            day = str(int(m.group(1)))
        except ValueError:
            return ""
        month = normalize_month_word(m.group(2))
        year = m.group(3)
        return f"{day} {month} {year}"

    # MONTH DD YYYY
    m = re.search(rf"\b({month_pattern})\s+(\d{{1,2}})\s+(\d{{4}})\b", raw)
    if m:
        month = normalize_month_word(m.group(1))
        try:
            day = str(int(m.group(2)))
        except ValueError:
            return ""
        year = m.group(3)
        return f"{day} {month} {year}"

    # DD-MM-YYYY or DD/MM/YYYY normalized to spaces
    m = re.search(r"\b(\d{1,2})\s+(\d{1,2})\s+(\d{4})\b", raw)
    if m:
        try:
            day, mon, year = int(m.group(1)), int(m.group(2)), m.group(3)
        except ValueError:
            return ""
        if 1 <= mon <= 12:
            month_names = ["", "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
                          "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
            month = month_names[mon]
            return f"{day} {month} {year}"

    return ""


def normalize_date_text(tokens) -> str:
    rows = group_rows(tokens, y_tol=14)

    found = []
    for row in rows:
        row_text = join_tokens(row)
        parsed = parse_date_from_string(row_text)
        if parsed:
            found.append((sum(t["cy"] for t in row) / len(row), parsed))

        for it in row:
            parsed_single = parse_date_from_string(it["text"])
            if parsed_single:
                found.append((it["cy"], parsed_single))

    if not found:
        return ""

    found.sort(key=lambda x: x[0])
    return found[-1][1]


def extract_registry_number(tokens) -> str:
    """Extract registry number from tokens; accepts multiple formats."""
    vals = []
    for it in tokens:
        t = clean_text(it["text"])
        t2 = re.sub(r"\s*-\s*", "-", t)
        t_compact = re.sub(r"\s+", "", t)

        # 1234 56789 or 1234-56789
        if re.fullmatch(r"\d{4}\s\d{3,}", t):
            vals.append((it["score"], t))
        if re.fullmatch(r"\d{4}\s*-\s*\d{3,}", t2) or re.fullmatch(r"\d{4}-\d{3,}", t_compact):
            normalized = re.sub(r"\s*-\s*", "-", t).strip()
            if normalized not in [v[1] for v in vals]:
                vals.append((it["score"], normalized))
        # NN-NNNNNN style
        if re.fullmatch(r"\d{2,8}-\d{2,8}", t2):
            vals.append((it["score"], t2))
        # digits only
        if re.fullmatch(r"\d{4,12}", t_compact):
            if len(t_compact) >= 9:
                formatted = f"{t_compact[:5]}-{t_compact[5:]}" if len(t_compact) > 5 else t_compact
                vals.append((it["score"] * 0.9, formatted))
            else:
                vals.append((it["score"] * 0.85, t))

    if not vals:
        return ""

    vals.sort(key=lambda x: -x[0])
    return vals[0][1]


def infer_working_xmax(items, img_w, img_h):
    blockers = [
        find_best_label(items, ["FOR OCRG USE ONLY"], x_min=img_w * 0.55, y_min=0, y_max=img_h * 0.30, min_match_score=6.5),
        find_best_label(items, ["POPULATION REFERENCES NO"], x_min=img_w * 0.55, y_min=0, y_max=img_h * 0.30, min_match_score=6.0),
        find_best_label(items, ["TO BE FILLED UP AT THE OFFICE OF THE CIVIL REGISTRAR"], x_min=img_w * 0.55, y_min=0, y_max=img_h * 0.35, min_match_score=6.0),
        find_best_label(items, ["REMARKS ANNOTATION"], x_min=img_w * 0.55, y_min=0, y_max=img_h * 0.20, min_match_score=6.0),
    ]
    xs = [b["x1"] for b in blockers if b is not None]
    if xs:
        return min(xs) - 10
    return int(img_w * 0.95)


def helper_like_token(it):
    txt = clean_text(it["text"])
    nt = norm_text(txt)

    if "(" in txt or ")" in txt:
        return True
    if nt in {"FIRST", "MIDDLE", "LAST"}:
        return True
    if len(nt) <= 6 and alpha_count(nt) >= 2:
        return True
    return False


def infer_slot_centers(items, name_label, max_x):
    helper_tokens = tokens_in_region(
        items,
        name_label["x1"] + 35,
        max_x,
        name_label["y1"] - 8,
        name_label["y2"] + 14,
        min_score=0.20
    )

    candidates = [it for it in helper_tokens if helper_like_token(it)]
    candidates = sorted(candidates, key=lambda x: x["cx"])

    if len(candidates) >= 3:
        candidates = candidates[:3]
        return [c["cx"] for c in candidates]

    left = name_label["x1"] + 90
    right = max_x - 30
    width = max(90, right - left)
    return [
        left + width * 0.18,
        left + width * 0.46,
        left + width * 0.74,
    ]


def assign_tokens_to_slots(tokens, centers):
    first_parts, middle_parts, last_parts = [], [], []

    for it in sorted(tokens, key=lambda x: x["x1"]):
        t = clean_text(it["text"])
        nt = norm_text(t)

        if not t:
            continue
        if "(" in t or ")" in t:
            continue
        if re.fullmatch(r"\d+", nt):
            continue
        if alpha_count(t) < 2:
            continue
        if nt in {"NAME", "FIRST", "MIDDLE", "LAST"}:
            continue

        if any(k in nt for k in [
            "DATE OF BIRTH", "PLACE OF", "CITIZENSHIP", "RELIGION",
            "TYPE OF BIRTH", "BIRTH ORDER", "OCCUPATION",
            "PROVINCE", "CITY MUNICIPALITY", "FOR OCRG", "REGISTRY"
        ]):
            continue

        d = [abs(it["cx"] - c) for c in centers]
        slot = d.index(min(d))

        if slot == 0:
            first_parts.append(t)
        elif slot == 1:
            middle_parts.append(t)
        else:
            last_parts.append(t)

    parts = []
    if first_parts:
        parts.append(" ".join(first_parts))
    if middle_parts:
        parts.append(" ".join(middle_parts))
    if last_parts:
        parts.append(" ".join(last_parts))

    return normalize_simple_text(" ".join(parts))


def row_has_field_keywords(row):
    nt = norm_text(join_tokens(row))
    bad_parts = [
        "FIRST", "MIDDLE", "LAST",
        "DATE OF BIRTH", "SEX", "PLACE OF", "CITIZENSHIP", "RELIGION",
        "TYPE OF BIRTH", "BIRTH ORDER", "OCCUPATION", "RESIDENCE",
        "REGISTRY", "PROVINCE", "CITY MUNICIPALITY",
        "FOR OCRG", "POPULATION REFERENCES"
    ]

    if nt == "NAME":
        return True

    return any(bp in nt for bp in bad_parts)


def extract_name_field_v2(items, label, stop_y, max_x, exclude_keywords=None):
    """
    Improved name extraction - looks for name tokens below the label.
    Uses position-based approach with better filtering.
    """
    if exclude_keywords is None:
        exclude_keywords = []
    
    if not label:
        return ""
    
    # Search in the region below the label
    search_top = label["y2"] + 5
    search_bottom = min(stop_y + 15, label["y2"] + 80)
    
    region = tokens_in_region(
        items,
        label["x1"] - 10,
        max_x,
        search_top,
        search_bottom,
        min_score=0.15  # Lower threshold to catch more tokens
    )
    
    if not region:
        return ""
    
    # Filter out non-name tokens
    name_tokens = []
    for it in region:
        txt = clean_text(it["text"])
        nt = norm_text(txt)
        
        # Skip tokens that are:
        # - Too short
        # - Numbers only
        # - Form labels/keywords
        # - Contains date patterns
        if len(txt) < 2:
            continue
        if re.fullmatch(r"\d+", nt):
            continue
        if re.search(r"\d{4}", nt):  # Contains year
            continue
        if any(kw in nt for kw in exclude_keywords):
            continue
        if any(kw in nt for kw in BAD_VALUE_KEYWORDS):
            continue
        
        name_tokens.append(it)
    
    if not name_tokens:
        return ""
    
    # Group into rows and get the row with the most name-like content
    rows = group_rows(name_tokens, y_tol=10)
    
    # Find the best row (has alpha characters, looks like a name)
    best_row = None
    best_score = 0
    
    for row in rows:
        row_text = join_tokens(row)
        row_nt = norm_text(row_text)
        
        # Score based on alpha content and length
        alpha = alpha_count(row_text)
        if alpha < 3:
            continue
        
        score = alpha * len(row_text) / 100
        if score > best_score:
            best_score = score
            best_row = row
    
    if best_row:
        return normalize_simple_text(join_tokens(best_row))
    
    return ""


def extract_bottom_row_text(tokens):
    rows = group_rows(tokens, y_tol=12)
    if not rows:
        return ""
    return join_tokens(rows[-1])


def extract_value_near_label(items, label, max_x, x_span=150, y_up=8, y_down=48):
    if not label:
        return ""

    region = tokens_in_region(
        items,
        label["x1"] + 20,
        min(max_x, label["x2"] + x_span),
        label["y1"] - y_up,
        label["y2"] + y_down,
        min_score=0.20
    )

    rows = group_rows(region, y_tol=10)
    best_text = ""
    best_penalty = None

    for row in rows:
        row_y = sum(t["cy"] for t in row) / len(row)
        dy = row_y - label["cy"]

        if dy < -12 or dy > y_down + 8:
            continue

        kept = []
        for it in row:
            nt = norm_text(it["text"])

            if nt in {"CITIZENSHIP", "RELIGION", "7", "8", "14", "15", "7.", "8.", "14.", "15."}:
                continue
            if any(bad in nt for bad in BAD_VALUE_KEYWORDS):
                continue
            if alpha_count(it["text"]) < 2:
                continue

            kept.append(it)

        txt = normalize_simple_text(join_tokens(kept))
        if not txt:
            continue

        penalty = abs(max(dy, 0))
        if best_penalty is None or penalty < best_penalty:
            best_penalty = penalty
            best_text = txt

    return best_text


def extract_date_field(items, dob_label, max_x):
    """Extract date of birth with improved logic."""
    if not dob_label:
        return ""

    # First try the immediate area below the label
    region = tokens_in_region(
        items,
        dob_label["x1"] + 40,
        min(max_x, dob_label["x2"] + 280),
        dob_label["y1"] - 6,
        dob_label["y2"] + 44,
        min_score=0.15
    )

    parsed = normalize_date_text(region)
    if parsed:
        return parsed

    # Try with expanded region
    region = tokens_in_region(
        items,
        dob_label["x1"] + 10,
        min(max_x, dob_label["x2"] + 350),
        dob_label["y1"] - 10,
        dob_label["y2"] + 60,
        min_score=0.12
    )
    return normalize_date_text(region)


def extract_date_field_direct(items, label_y, label_x_start, max_x, img_h):
    """
    Direct date extraction - searches in a broader area below the label position.
    """
    # Search in a vertical band starting from label position
    search_top = label_y - 10
    search_bottom = label_y + 110
    
    region = tokens_in_region(
        items,
        0,  # Full width for DOB
        max_x,
        search_top,
        search_bottom,
        min_score=0.10  # Lower threshold
    )
    
    if DEBUG_OCR_RAW:
        print("DOB region tokens:")
        print(f"Region bounds: x=0 to {max_x}, y={search_top} to {search_bottom}")
        for it in region:
            print(f"  {it['text']} (score: {it['score']:.2f}) at ({it['cx']:.0f},{it['cy']:.0f})")
    
    if not region:
        return ""
    
    # Look for date patterns in the region
    parsed = normalize_date_text(region)
    if parsed:
        return parsed
    
    # Try parsing each token individually
    for it in region:
        parsed = parse_date_from_string(it["text"])
        if parsed:
            return parsed
    
    # Last resort: look at all text in the region
    all_text = join_tokens(region)
    return parse_date_from_string(all_text)


def detect_sex(items, sex_label, dob_label=None):
    if not sex_label:
        return "Unknown"

    xmax = dob_label["x1"] - 5 if dob_label else sex_label["x2"] + 320

    region = tokens_in_region(
        items,
        sex_label["x1"] - 20,
        xmax,
        sex_label["y1"] - 6,
        sex_label["y2"] + 40,
        min_score=0.20
    )

    if not region:
        return "Unknown"

    male_score = 0
    female_score = 0

    for it in region:
        raw = clean_text(it["text"])
        nt = norm_text(raw)

        if "MALE" in nt:
            male_score += 2
            if re.search(r"^[^A-Z0-9]*[IXL/\\_]+", raw.upper()):
                male_score += 4
            if re.search(r"\bX\b", raw.upper()):
                male_score += 5

        if "FEMALE" in nt:
            female_score += 2
            if re.search(r"^[^A-Z0-9]*[IXL/\\_]+", raw.upper()):
                female_score += 4
            if re.search(r"\bX\b", raw.upper()):
                female_score += 5

    raw_joined = (" ".join(clean_text(it["text"]) for it in region)).upper()
    raw_joined = re.sub(r"\s+", " ", raw_joined).strip()

    if re.search(r"[IXL/\\_]+\s*1\s*MALE", raw_joined):
        male_score += 4
    if re.search(r"[IXL/\\_]+\s*2\s*FEMALE", raw_joined):
        female_score += 4
    if re.search(r"\bX\s*1\s*MALE", raw_joined):
        male_score += 5
    if re.search(r"\bX\s*2\s*FEMALE", raw_joined):
        female_score += 5

    if male_score > female_score and male_score >= 4:
        return "Male"
    if female_score > male_score and female_score >= 4:
        return "Female"

    return "Unknown"


def extract_place_of_birth(items, pob_label, type_birth_label, working_xmax):
    """Extract place of birth - look to the RIGHT of the label (like the guide)."""
    if not pob_label:
        return ""
    
    # Look to the RIGHT of the label (not below)
    next_y = type_birth_label["y1"] - 3 if type_birth_label else pob_label["y2"] + 45
    
    pob_region = tokens_in_region(
        items,
        pob_label["x2"] + 5,  # Right side of label
        working_xmax,
        pob_label["y1"] - 2,
        next_y,
        min_score=0.20
    )
    
    if not pob_region:
        return ""
    
    # Get the bottom row text
    place_text = normalize_simple_text(extract_bottom_row_text(pob_region))
    
    # Validate: reject garbage values
    if place_text:
        nt = norm_text(place_text)
        # Reject if contains numbers
        if re.search(r"\d+", nt):
            return ""
        # Reject if it's a citizenship/religion word (not a place)
        if any(kw in nt for kw in ["FILIPINO", "CITIZENSHIP", "RELIGION", "CATHOLIC", "CHRISTIAN"]):
            return ""
        # Reject if too short
        if len(nt) < 3:
            return ""
    
    return place_text


def extract_marriage_of_parents(items, marriage_label, working_xmax):
    """Extract both date and place of marriage of parents - look to the RIGHT of label."""
    if not marriage_label:
        return "", ""
    
    # Look to the RIGHT of the label (like the guide shows)
    marriage_region = tokens_in_region(
        items,
        marriage_label["x2"] + 5,  # Right side of label
        working_xmax,
        marriage_label["y1"] - 4,
        marriage_label["y2"] + 28,
        min_score=0.20
    )
    
    if not marriage_region:
        return "", ""
    
    # Get the date from the region
    date_text = normalize_date_text(marriage_region)
    
    # For place, we need to look in a broader region below
    # Since we're having issues, let's return empty for place when date is extracted from right
    # and let the fallback handle it
    return date_text, ""


def find_date_in_form(items, img_h):
    """Fallback: Search entire form for date patterns."""
    dates = []
    for it in items:
        if it["score"] < 0.12:
            continue
        # DOB typically upper-middle
        if it["cy"] > img_h * 0.65:
            continue
        parsed = parse_date_from_string(it["text"])
        if parsed:
            dates.append((it["cy"], parsed))
    
    if dates:
        dates.sort(key=lambda x: x[0])
        return dates[1][1] if len(dates) > 1 else dates[0][1]  # Prefer 2nd (DOB after reg)
    return ""


def find_place_in_form(items, img_h, working_xmax):
    """Fallback: Search for place-like text in expected areas."""
    location_keywords = [
        "MANILA", "CEBU", "DAVAO", "QUEZON", "CITY", "PROVINCE", "TOWN", "MUNICIPAL",
        "BARANGAY", "RIZAL", "LAGUNA", "BATANGAS", "NUEVA", "ILOCOS", "VISAYAS",
        "METRO", "CALOOCAN", "PASAY", "MAKATI", "QC", "HOSPITAL", "CLINIC",
        "MEDICAL", "HEALTH", "CENTER", "ST.", "SAINT", "METROPOLITAN"
    ]
    
    candidates = []
    for it in items:
        if it["score"] < 0.12:
            continue
        # Look in middle portion
        if it["cy"] < img_h * 0.15 or it["cy"] > img_h * 0.55:
            continue
            
        txt = clean_text(it["text"])
        nt = norm_text(txt)
        
        # Skip if too short
        if len(nt) < 4:
            continue
        # Skip if contains year
        if re.search(r"\d{4}", nt):
            continue
        # Skip form labels
        if any(kw in nt for kw in BAD_VALUE_KEYWORDS):
            continue
            
        # Check for location keywords
        if any(loc in nt for loc in location_keywords):
            candidates.append((it["cy"], txt))
    
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    
    return ""


def find_marriage_in_form(items, img_h, img_w):
    """Fallback: Search for marriage date/place in the lower portion of form."""
    dates = []
    places = []
    
    for it in items:
        if it["score"] < 0.12:
            continue
        # Focus on middle-lower portion
        if it["cy"] < img_h * 0.35 or it["cy"] > img_h * 0.75:
            continue
            
        txt = clean_text(it["text"])
        nt = norm_text(txt)
        
        # Skip form labels
        if any(kw in nt for kw in ["NAME", "FATHER", "MOTHER", "CITIZEN", "RELIGION", "CATHOLIC"]):
            continue
            
        # Try to parse as date
        parsed = parse_date_from_string(txt)
        if parsed:
            dates.append((it["cy"], parsed))
            continue
            
        # Look for place-like text
        if len(nt) > 5 and not re.search(r"\d{4}", nt):
            places.append((it["cy"], txt))
    
    date_result = ""
    place_result = ""
    
    if dates:
        dates.sort(key=lambda x: x[0])
        date_result = dates[0][1]
    
    if places:
        places.sort(key=lambda x: x[0])
        place_result = places[0][1]
    
    # Filter out religion as place
    if place_result:
        nt = norm_text(place_result)
        religions = ["CATHOLIC", "CHRISTIAN", "MUSLIM", "IGLESIA"]
        if any(rel in nt for rel in religions):
            place_result = ""
    
    return date_result, place_result


def find_remarks_label(items, img_w, img_h):
    """Find the REMARKS/ANNOTATION label."""
    return find_best_label(
        items,
        patterns=["REMARKS", "ANNOTATION", "REMARKS ANNOTATION"],
        x_min=img_w * 0.50,
        x_max=img_w * 0.98,
        y_min=img_h * 0.60,
        y_max=img_h * 0.95,
        min_match_score=5.5
    )


def extract_remarks(items, remarks_label, working_xmax):
    """Extract remarks from the form."""
    if not remarks_label:
        return ""
    
    # Search in the region below the label
    remarks_region = tokens_in_region(
        items,
        remarks_label["x1"] - 20,
        working_xmax,
        remarks_label["y2"] + 5,
        remarks_label["y2"] + 320,
        min_score=0.08
    )
    
    if not remarks_region:
        return ""
    
    # Get text from the region
    rows = group_rows(remarks_region, y_tol=12)
    
    # Get multi-row text, join first few substantial rows
    remark_rows = []
    for row in rows[:3]:  # First 3 rows
        text = normalize_simple_text(join_tokens(row))
        if text and len(text) > 3:
            nt = norm_text(text)
            if not any(kw in nt for kw in ["REMARKS", "ANNOTATION", "FOR OCR", "OFFICE", "REGISTRAR"]):
                remark_rows.append(text)
    
    return " ".join(remark_rows)
    
    return ""


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
                "x1": int(min(xs)),
                "y1": int(min(ys)),
                "x2": int(max(xs)),
                "y2": int(max(ys)),
            }
            item["cx"] = (item["x1"] + item["x2"]) / 2.0
            item["cy"] = (item["y1"] + item["y2"]) / 2.0
            item["w"] = item["x2"] - item["x1"]
            item["h"] = item["y2"] - item["y1"]
            items.append(item)

    items.sort(key=lambda x: (x["cy"], x["x1"]))
    return items


# =========================================================
# MAIN: extract_birth_data
# =========================================================
def extract_birth_data(img_path: str) -> Dict[str, Any]:
    temp_cropped = None
    try:
        temp_cropped = create_temp_cropped_image(img_path, CROP_LEFT, CROP_RIGHT)

        result = run_ocr_on_image_path(temp_cropped)
        img = cv2.imread(temp_cropped)
        if img is None:
            raise FileNotFoundError(f"Could not read temp cropped image: {temp_cropped}")

        img_h, img_w = img.shape[:2]
        items = build_items(result)

        if DEBUG_OCR_RAW:
            for it in items:
                print(f'{it["text"]} | ({it["x1"]},{it["y1"]})-({it["x2"]},{it["y2"]})')

        working_xmax = infer_working_xmax(items, img_w, img_h)

        # LABELS
        reg_label = find_best_label(
            items,
            patterns=["REGISTRY NO", "REGIATRY NO", "REGISTRY NO.", "REGISTRY", "REGIATRY", "REGISTRY NUMBER"],
            x_min=img_w * 0.25,
            y_min=0,
            y_max=img_h * 0.28,
            min_match_score=5.5
        )

        reg_date_label = find_best_label(
            items,
            patterns=["DATE REGISTRATION", "REGISTRATION DATE", "DATE OF REG", "REG DATE", "DATE REG"],
            x_min=img_w * 0.25,
            y_min=img_h * 0.02,
            y_max=img_h * 0.32,
            min_match_score=5.0
        )

        name_label = find_child_name_label(items, img_w, img_h)

        dob_label = find_best_label(
            items,
            patterns=["DATE OF BIRTH", "OATE OF BIRTH", "DATEOBIRTH", "DATE OFBIRTH", "3 DATE OF BIRTH", "3.DATE OF BIRTH", "3DATE OF BIRTH"],
            x_min=img_w * 0.15,
            x_max=img_w * 0.75,
            y_min=img_h * 0.08,
            y_max=img_h * 0.35,
            min_match_score=5.5
        )

        sex_label = find_best_label(
            items,
            patterns=["2 SEX", "2. SEX", "SEX"],
            x_min=0,
            x_max=img_w * 0.30,
            y_min=img_h * 0.10,
            y_max=img_h * 0.30,
            min_match_score=6.0
        )

        pob_label = find_best_label(
            items,
            patterns=["PLACE OF BIRTH", "PLACE OF", "4 PLACE OF BIRTH", "4. PLACE OF BIRTH"],
            x_min=0,
            x_max=img_w * 0.38,
            y_min=img_h * 0.12,
            y_max=img_h * 0.42,
            min_match_score=5.5
        )

        type_birth_label = find_best_label(
            items,
            patterns=["TYPE OF BIRTH", "5A TYPE OF BIRTH", "5a TYPE OF BIRTH"],
            x_min=0,
            x_max=img_w * 0.50,
            y_min=img_h * 0.18,
            y_max=img_h * 0.42,
            min_match_score=6.0
        )

        mother_label = find_best_label(
            items,
            patterns=["MAIDEN NAME OF MOTHER", "NAME OF MOTHER", "MAIDEN"],
            x_min=0,
            x_max=img_w * 0.35,
            y_min=img_h * 0.22,
            y_max=img_h * 0.44,
            min_match_score=6.0
        )

        mother_cit_label = find_label_below(
            items, mother_label,
            patterns=["CITIZENSHIP", "7 CITIZENSHIP", "7. CITIZENSHIP"],
            y_min_offset=2,
            y_max_offset=60,
            x_max=img_w * 0.45,
            min_match_score=6.0
        )

        mother_rel_label = find_best_label(
            items,
            patterns=["RELIGION", "8 RELIGION", "8. RELIGION"],
            x_min=img_w * 0.20,
            x_max=img_w * 0.75,
            y_min=mother_label["y1"] if mother_label else img_h * 0.20,
            y_max=(mother_label["y1"] + 100) if mother_label else img_h * 0.45,
            min_match_score=6.0
        )

        father_label = find_best_label(
            items,
            patterns=["13 NAME", "13. NAME", "12 NAME", "12. NAME", "NAME OF FATHER", "FATHER"],
            x_min=0,
            x_max=img_w * 0.35,
            y_min=img_h * 0.34,
            y_max=img_h * 0.60,
            min_match_score=6.0
        )

        father_cit_label = find_label_below(
            items, father_label,
            patterns=["CITIZENSHIP", "14 CITIZENSHIP", "14. CITIZENSHIP", "14. CETIZENSHIP"],
            y_min_offset=2,
            y_max_offset=70,
            x_max=img_w * 0.45,
            min_match_score=6.0
        )

        father_rel_label = find_best_label(
            items,
            patterns=["RELIGION", "15 RELIGION", "15. RELIGION", "15RELIBION"],
            x_min=img_w * 0.20,
            x_max=img_w * 0.75,
            y_min=father_label["y1"] if father_label else img_h * 0.34,
            y_max=(father_label["y1"] + 110) if father_label else img_h * 0.62,
            min_match_score=6.0
        )

        marriage_label = find_best_label(
            items,
            patterns=[
                "DATE AND PLACE OF MARRIAGE OF PARENTS",
                "MARRIAGE OF PARENTS",
                "DATE AND PLACE OF MARRIAGE",
                "PLACE OF MARRIAGE OF PARENTS",
            ],
            x_min=0,
            x_max=img_w * 0.85,
            y_min=img_h * 0.44,
            y_max=img_h * 0.78,
            min_match_score=6.0
        )

        remarks_label = find_remarks_label(items, img_w, img_h)

        # Initialize data dictionary
        data = {
            "Registry Number": "",
            "Name of Child": "",
            "Date of Birth": "",
            "Sex": "Unknown",
            "Place of Birth": "",
            "Name of Mother": "",
            "Citizenship of Mother": "",
            "Religion of Mother": "",
            "Name of Father": "",
            "Citizenship of Father": "",
            "Religion of Father": "",
            "Date of Marriage of Parents": "",
            "Place of Marriage of Parents": "",
            "Remarks": "",
        }

        # Registry Number and Date of Registration
        if reg_label:
            reg_tokens = tokens_in_region(
                items,
                reg_label["x1"],
                working_xmax,
                reg_label["y1"] - 12,
                reg_label["y2"] + 45,
                min_score=0.18
            )
            data["Registry Number"] = extract_registry_number(reg_tokens)
        
        if not data["Registry Number"] and items:
            header = tokens_in_region(items, 0, working_xmax, 0, int(img_h * 0.22), min_score=0.18)
            data["Registry Number"] = extract_registry_number(header)

        # Date of Registration
        reg_date = ""
        if reg_date_label:
            reg_date_region = tokens_in_region(
                items,
                reg_date_label["x1"],
                working_xmax,
                reg_date_label["y1"] - 10,
                reg_date_label["y2"] + 80,
                min_score=0.10
            )
            reg_date = normalize_date_text(reg_date_region)
        
        # Also check near registry number
        if reg_label and not reg_date:
            reg_date_region = tokens_in_region(
                items,
                reg_label["x1"],
                working_xmax,
                reg_label["y1"] - 40,
                reg_label["y2"] + 80,
                min_score=0.10
            )
            reg_date = normalize_date_text(reg_date_region)
        
        data["Date of Registration"] = reg_date

        # Name of Child - improved extraction
        if name_label:
            next_y = min(
                [y for y in [
                    dob_label["y1"] if dob_label else None,
                    sex_label["y1"] if sex_label else None
                ] if y is not None] or [name_label["y2"] + 45]
            )
            data["Name of Child"] = extract_name_field_v2(
                items, name_label, next_y, working_xmax,
                exclude_keywords=["DATE OF BIRTH", "SEX", "PLACE OF BIRTH"]
            )

        # Date of Birth - improved extraction
        if dob_label:
            # Try direct extraction below the label
            dob_date = extract_date_field_direct(
                items, dob_label["y2"], dob_label["x1"], working_xmax, img_h
            )
            if dob_date:
                data["Date of Birth"] = dob_date
            else:
                data["Date of Birth"] = extract_date_field(items, dob_label, working_xmax)
        
        # Fallback: search entire form for date
        if not data["Date of Birth"]:
            data["Date of Birth"] = find_date_in_form(items, img_h)

        # Sex - should be correct from original
        data["Sex"] = detect_sex(items, sex_label, dob_label)

        # Place of Birth - improved extraction
        if pob_label:
            data["Place of Birth"] = extract_place_of_birth(items, pob_label, type_birth_label, working_xmax)
        
        # Fallback: search for place
        if not data["Place of Birth"]:
            data["Place of Birth"] = find_place_in_form(items, img_h, working_xmax)

        # Mother
        if mother_label:
            next_y = min(
                [y for y in [
                    mother_cit_label["y1"] if mother_cit_label else None,
                    mother_rel_label["y1"] if mother_rel_label else None
                ] if y is not None] or [mother_label["y2"] + 45]
            )
            data["Name of Mother"] = extract_name_field_v2(
                items, mother_label, next_y, working_xmax,
                exclude_keywords=["CITIZENSHIP", "RELIGION", "NAME OF FATHER"]
            )

        if mother_cit_label:
            data["Citizenship of Mother"] = extract_value_near_label(
                items, mother_cit_label,
                working_xmax,
                x_span=140,
                y_up=6,
                y_down=55
            )

        if mother_rel_label:
            data["Religion of Mother"] = extract_value_near_label(
                items, mother_rel_label,
                working_xmax,
                x_span=140,
                y_up=6,
                y_down=50
            )

        # Father
        if father_label:
            next_y = min(
                [y for y in [
                    father_cit_label["y1"] if father_cit_label else None,
                    father_rel_label["y1"] if father_rel_label else None
                ] if y is not None] or [father_label["y2"] + 45]
            )
            data["Name of Father"] = extract_name_field_v2(
                items, father_label, next_y, working_xmax,
                exclude_keywords=["CITIZENSHIP", "RELIGION", "MARRIAGE"]
            )

        if father_cit_label:
            data["Citizenship of Father"] = extract_value_near_label(
                items, father_cit_label,
                working_xmax,
                x_span=140,
                y_up=6,
                y_down=50
            )

        if father_rel_label:
            data["Religion of Father"] = extract_value_near_label(
                items, father_rel_label,
                working_xmax,
                x_span=140,
                y_up=6,
                y_down=50
            )

        # Marriage of Parents
        if marriage_label:
            date_mar, place_mar = extract_marriage_of_parents(items, marriage_label, working_xmax)
            data["Date of Marriage of Parents"] = date_mar
            data["Place of Marriage of Parents"] = place_mar
        
        # Fallback: search for marriage info
        if not data["Date of Marriage of Parents"] or not data["Place of Marriage of Parents"]:
            date_fb, place_fb = find_marriage_in_form(items, img_h, img_w)
            if not data["Date of Marriage of Parents"] and date_fb:
                data["Date of Marriage of Parents"] = date_fb
            if not data["Place of Marriage of Parents"] and place_fb:
                data["Place of Marriage of Parents"] = place_fb

        # Remarks
        data["Remarks"] = extract_remarks(items, remarks_label, working_xmax)

        return {
            "Registry Number": data.get("Registry Number", ""),
            "Date of Registration": data.get("Date of Registration", ""),
            "Name of Child": data.get("Name of Child", ""),
            "Sex": data.get("Sex", ""),
            "Date of Birth": data.get("Date of Birth", ""),
            "Place of Birth": data.get("Place of Birth", ""),
            "Type of Birth": data.get("Type of Birth", ""),
            "Birth Order": data.get("Birth Order", ""),
            "Name of Mother": data.get("Name of Mother", ""),
            "Citizenship of Mother": data.get("Citizenship of Mother", ""),
            "Religion of Mother": data.get("Religion of Mother", ""),
            "Name of Father": data.get("Name of Father", ""),
            "Citizenship of Father": data.get("Citizenship of Father", ""),
            "Religion of Father": data.get("Religion of Father", ""),
            "Date of Marriage of Parents": data.get("Date of Marriage of Parents", ""),
            "Place of Marriage of Parents": data.get("Place of Marriage of Parents", ""),
            "Remarks": data.get("Remarks", ""),
        }
    finally:
        if temp_cropped and os.path.exists(temp_cropped):
            try:
                os.remove(temp_cropped)
            except Exception:
                pass

