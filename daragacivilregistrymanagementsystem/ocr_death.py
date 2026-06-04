import re
import difflib
from typing import Dict, Any, List

import cv2

from ocr_shared import run_ocr_on_image
from template_engine import extract_from_ocr_text, ocr_pages_to_text

DEBUG_TEMPLATE_MATCH = False


MONTHS = {
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
}

STATUS_WORDS = {"SINGLE", "MARRIED", "WIDOWED", "DIVORCED", "SEPARATED"}

NAME_BANNED = {
    "NAME",
    "FATHER",
    "MOTHER",
    "PRINT",
    "INFORMANT",
    "REGISTRY",
    "PROVINCE",
    "CITY",
    "MUNICIPALITY",
    "SEX",
    "MALE",
    "FEMALE",
    "LAST",
    "MIDDLE",
    "FIRST",
    "FIRSAT",
    "MIDDKE",
    "HAME",
    # avoid picking the big title line as the person's name
    "CERTIFICATE",
    "CERTIFICATE OF DEATH",
}

# Location keywords to help identify place of death
LOCATION_KEYWORDS = {
    "MANILA", "CEBU", "DAVAO", "QUEZON", "RIZAL", "LAGUNA", "BATANGAS",
    "NUEVA", "ILOCOS", "VISAYAS", "METRO", "CALOOCAN", "PASAY", "MAKATI",
    "CITY", "TOWN", "MUNICIPAL", "BARANGAY", "PROVINCE", "HOSPITAL",
    "MEDICAL", "CLINIC", "HEALTH", "CENTER", "CENTRE"
}


def _clean_text(t: str) -> str:
    t = str(t).strip()
    t = t.replace("|", " ")
    t = re.sub(r"[._]{2,}", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _norm_text(t: str) -> str:
    t = _clean_text(t).upper()
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _alpha_count(t: str) -> int:
    return sum(c.isalpha() for c in t)


def _build_items(result, img_w: int, img_h: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
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


def _tokens_in_region(items, xmin, xmax, ymin, ymax, min_score=0.30):
    out = []
    for it in items:
        if it["score"] < min_score:
            continue
        if xmin <= it["cx"] <= xmax and ymin <= it["cy"] <= ymax:
            out.append(it)
    out.sort(key=lambda x: (x["cy"], x["x1"]))
    return out


def _group_rows(tokens, y_tol=12):
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


def _join_tokens(tokens):
    return " ".join(_clean_text(t["text"]) for t in sorted(tokens, key=lambda x: x["x1"])).strip()


def _find_label(
    items,
    required_all=None,
    required_any=None,
    forbidden=None,
    x_min=None,
    x_max=None,
    y_min=None,
    y_max=None,
    min_score=0.30,
):
    required_all = required_all or []
    required_any = required_any or []
    forbidden = forbidden or []

    best = None
    best_score = None

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

        nt = _norm_text(it["text"])

        if required_all and not all(w.upper() in nt for w in required_all):
            continue
        if required_any and not any(w.upper() in nt for w in required_any):
            continue
        if forbidden and any(w.upper() in nt for w in forbidden):
            continue

        score = (
            len(required_all) * 5
            + sum(1 for w in required_any if w.upper() in nt)
            + it["score"] * 2
            - len(nt) * 0.02
        )

        if best is None or score > best_score:
            best = it
            best_score = score

    return best


def _best_exact_choice(tokens, choices):
    choices = {c.upper() for c in choices}
    vals = []
    for it in tokens:
        nt = _norm_text(it["text"])
        if nt in choices:
            vals.append((it["score"], it["x1"], nt))
    if not vals:
        return ""
    vals.sort(key=lambda x: (-x[0], x[1]))
    return vals[0][2]


def _choose_best_row(tokens, banned_words=None, prefer_y=None):
    banned_words = banned_words or []
    rows = _group_rows(tokens)

    best_text = ""
    best_tuple = None

    for row in rows:
        kept = []
        for it in row:
            text = _clean_text(it["text"])
            nt = _norm_text(text)

            if not text:
                continue
            if len(nt) == 1 and not nt.isdigit():
                continue
            if any(b.upper() in nt for b in banned_words):
                continue

            kept.append(it)

        if not kept:
            continue

        text = _join_tokens(kept)
        letters = _alpha_count(text)
        avg_score = sum(x["score"] for x in kept) / len(kept)
        row_y = sum(x["cy"] for x in kept) / len(kept)

        score = letters + avg_score * 10 + len(kept) * 2
        if prefer_y is not None:
            score -= abs(row_y - prefer_y) * 0.08

        tup = (score, letters, avg_score)

        if best_text == "" or tup > best_tuple:
            best_text = text
            best_tuple = tup

    return _clean_text(best_text)


def _normalize_month_word(word: str) -> str:
    w = _norm_text(word)
    if w in MONTHS:
        return w

    match = difflib.get_close_matches(w, list(MONTHS), n=1, cutoff=0.55)
    if match:
        return match[0]
    return w


def _normalize_date_text(text: str) -> str:
    text = _norm_text(text)
    parts = text.split()

    if len(parts) == 3 and re.fullmatch(r"\d{1,2}", parts[0]) and re.fullmatch(r"\d{4}", parts[2]):
        month = _normalize_month_word(parts[1])
        return f"{parts[0]} {month} {parts[2]}"

    return text


def _is_full_date(text: str) -> bool:
    text = _normalize_date_text(text)
    return bool(
        re.fullmatch(
            r"\d{1,2}\s+(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{4}",
            text,
        )
    )


def _extract_date_candidates(tokens):
    rows = _group_rows(tokens)
    found = []

    for row in rows:
        row = sorted(row, key=lambda x: x["x1"])

        for it in row:
            nt = _normalize_date_text(it["text"])
            if _is_full_date(nt):
                found.append(
                    {
                        "text": nt,
                        "x1": it["x1"],
                        "y1": it["y1"],
                    }
                )

        for i in range(len(row) - 2):
            a = _norm_text(row[i]["text"])
            b = _normalize_month_word(row[i + 1]["text"])
            c = _norm_text(row[i + 2]["text"])

            if re.fullmatch(r"\d{1,2}", a) and b in MONTHS and re.fullmatch(r"\d{4}", c):
                found.append(
                    {
                        "text": f"{a} {b} {c}",
                        "x1": row[i]["x1"],
                        "y1": min(row[i]["y1"], row[i + 1]["y1"], row[i + 2]["y1"]),
                    }
                )

        for i in range(len(row) - 1):
            a = _norm_text(row[i]["text"])
            b = _normalize_date_text(row[i + 1]["text"])

            if re.fullmatch(r"\d{1,2}", a):
                m = re.fullmatch(
                    r"(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(\d{4})",
                    b,
                )
                if m:
                    found.append(
                        {
                            "text": f"{a} {m.group(1)} {m.group(2)}",
                            "x1": row[i]["x1"],
                            "y1": min(row[i]["y1"], row[i + 1]["y1"]),
                        }
                    )

    unique = []
    seen = set()
    for d in sorted(found, key=lambda z: (z["x1"], z["y1"], z["text"])):
        key = (d["text"], round(d["x1"] / 8), round(d["y1"] / 8))
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


def _extract_registry_number(items, img_w, img_h):
    upper_right = _tokens_in_region(items, img_w * 0.52, img_w * 0.98, 0, img_h * 0.16, min_score=0.30)

    candidates = []
    for it in upper_right:
        t = _clean_text(it["text"])
        t2 = re.sub(r"\s*-\s*", "-", t)

        if re.fullmatch(r"\d{2,4}-\d{2,6}", t2):
            candidates.append((it["score"], it["x1"], t2))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2]


def _extract_name(items, img_w, img_h):
    name_label = _find_label(
        items,
        required_any=["NAME"],
        forbidden=["FATHER", "MOTHER", "PRINT", "INFORMANT", "PREPARED"],
        x_min=0,
        x_max=img_w * 0.22,
        y_min=img_h * 0.05,
        y_max=img_h * 0.15,
    )

    sex_label = _find_label(
        items,
        required_any=["SEX"],
        x_min=img_w * 0.65,
        x_max=img_w,
        y_min=img_h * 0.06,
        y_max=img_h * 0.16,
    )

    xmin = img_w * 0.12
    xmax = sex_label["x1"] - 10 if sex_label else img_w * 0.75

    if name_label:
        ymin = name_label["y2"] + 2
        ymax = name_label["y2"] + 50
    else:
        ymin = img_h * 0.09
        ymax = img_h * 0.17

    region = _tokens_in_region(items, xmin, xmax, ymin, ymax, min_score=0.30)
    rows = _group_rows(region)

    best_name = ""
    best_tuple = None

    for row in rows:
        kept = []
        row_y = sum(x["cy"] for x in row) / len(row)

        if name_label and row_y <= name_label["cy"] + 3:
            continue

        for it in row:
            text = _clean_text(it["text"])
            nt = _norm_text(text)

            if not text:
                continue
            if "(" in text or ")" in text:
                continue
            if nt in NAME_BANNED:
                continue
            if nt in MONTHS:
                continue
            if nt in {"MALE", "FEMALE"}:
                continue
            if re.fullmatch(r"\d+", nt):
                continue
            if "CITY" in nt or "MUNICIPALITY" in nt or "REGISTRY" in nt:
                continue

            kept.append(it)

        if not kept:
            continue

        text = _join_tokens(kept)
        letters = _alpha_count(text)
        avg_score = sum(x["score"] for x in kept) / len(kept)

        tup = (letters, len(kept), avg_score, row_y)

        if best_name == "" or tup > best_tuple:
            best_name = text
            best_tuple = tup

    return best_name


def _extract_name_of_mother(items, img_w, img_h) -> str:
    """Extract mother's maiden name from the parental information section."""
    mother_label = _find_label(
        items,
        required_all=["MOTHER"],
        forbidden=["FATHER", "DECEASED", "INFORMANT", "PREPARED", "NAME OF DECEASED"],
        x_min=0,
        x_max=img_w * 0.38,
        y_min=img_h * 0.17,
        y_max=img_h * 0.34,
    )
    if not mother_label:
        mother_label = _find_label(
            items,
            required_any=["MAIDEN"],
            forbidden=["FATHER", "DECEASED", "INFORMANT"],
            x_min=0,
            x_max=img_w * 0.42,
            y_min=img_h * 0.19,
            y_max=img_h * 0.36,
        )

    father_label = _find_label(
        items,
        required_all=["FATHER"],
        forbidden=["MOTHER", "DECEASED", "INFORMANT"],
        x_min=0,
        x_max=img_w * 0.38,
        y_min=img_h * 0.17,
        y_max=img_h * 0.32,
    )

    banned = [
        "MOTHER", "MAIDEN", "FATHER", "CITIZENSHIP", "RELIGION", "RESIDENCE",
        "OCCUPATION", "PLACE", "DEATH", "BIRTH", "INFORMANT", "REGISTRY",
    ]

    if mother_label:
        xmin = max(img_w * 0.10, mother_label["x1"] - 5)
        xmax = img_w * 0.75
        ymin = mother_label["y1"] - 6
        ymax = mother_label["y2"] + 42
        if father_label and father_label["cy"] > mother_label["cy"]:
            ymax = min(ymax, father_label["y1"] - 4)

        region = _tokens_in_region(items, xmin, xmax, ymin, ymax, min_score=0.25)
        text = _choose_best_row(
            region,
            banned_words=banned,
            prefer_y=mother_label["cy"] + 10,
        )
        if text and _alpha_count(text) >= 4:
            nt = _norm_text(text)
            if nt not in STATUS_WORDS and nt not in {"FILIPINO", "MALE", "FEMALE"}:
                return _clean_text(text)

        region_below = _tokens_in_region(
            items,
            img_w * 0.10,
            img_w * 0.75,
            mother_label["y2"] + 2,
            mother_label["y2"] + 38,
            min_score=0.25,
        )
        text = _choose_best_row(
            region_below,
            banned_words=banned,
            prefer_y=mother_label["y2"] + 14,
        )
        if text and _alpha_count(text) >= 4:
            nt = _norm_text(text)
            if nt not in STATUS_WORDS and nt not in {"FILIPINO", "MALE", "FEMALE"}:
                return _clean_text(text)

    # Fallback: row below father's name when mother label OCR fails.
    if father_label:
        region = _tokens_in_region(
            items,
            img_w * 0.10,
            img_w * 0.75,
            father_label["y2"] + 8,
            father_label["y2"] + 55,
            min_score=0.25,
        )
        text = _choose_best_row(
            region,
            banned_words=banned + ["SINGLE", "MARRIED", "WIDOWED", "DIVORCED"],
            prefer_y=father_label["y2"] + 28,
        )
        if text and _alpha_count(text) >= 4:
            nt = _norm_text(text)
            if nt not in STATUS_WORDS and nt not in {"FILIPINO", "MALE", "FEMALE"}:
                return _clean_text(text)

    return ""


def _extract_sex(items, img_w, img_h):
    def _to_sex_value(text: str) -> str:
        nt = _norm_text(text)
        if not nt:
            return ""
        # Direct forms
        if nt in {"MALE", "M"}:
            return "MALE"
        if nt in {"FEMALE", "F"}:
            return "FEMALE"
        # OCR-noisy forms
        if nt in {"FENALE", "FEMAIE", "FEM ALE", "FE MALE"}:
            return "FEMALE"
        if nt in {"MAL E", "MAI E"}:
            return "MALE"
        # Fuzzy fallback
        joined = nt.replace(" ", "")
        if joined:
            m = difflib.get_close_matches(joined, ["MALE", "FEMALE"], n=1, cutoff=0.72)
            if m:
                return m[0]
        return ""

    region = _tokens_in_region(
        items,
        img_w * 0.72,
        img_w * 0.97,
        img_h * 0.09,
        img_h * 0.17,
        min_score=0.30,
    )
    # First pass: strict+fuzzy in expected sex field box
    best_local = ""
    best_local_score = -1.0
    for it in region:
        sv = _to_sex_value(it["text"])
        if sv and it["score"] > best_local_score:
            best_local = sv
            best_local_score = it["score"]
    if best_local:
        return best_local

    # Second pass: anchor on SEX label then read tokens to its right
    sex_label = _find_label(
        items,
        required_any=["SEX"],
        x_min=img_w * 0.58,
        x_max=img_w,
        y_min=img_h * 0.06,
        y_max=img_h * 0.18,
        min_score=0.20,
    )
    if sex_label:
        near = _tokens_in_region(
            items,
            sex_label["x2"] + 2,
            img_w * 0.98,
            sex_label["y1"] - 10,
            sex_label["y2"] + 18,
            min_score=0.20,
        )
        best_near = ""
        best_near_score = -1.0
        for it in near:
            sv = _to_sex_value(it["text"])
            if sv and it["score"] > best_near_score:
                best_near = sv
                best_near_score = it["score"]
        if best_near:
            return best_near

    # Fallback: look anywhere on the page for a clear MALE/FEMALE token
    best = ""
    best_score = -1.0
    for it in items:
        sv = _to_sex_value(it["text"])
        if sv and it["score"] > best_score:
            best = sv
            best_score = it["score"]
    return best


def _extract_dates_and_age(items, img_w, img_h):
    top_band = _tokens_in_region(
        items,
        img_w * 0.05,
        img_w * 0.62,
        img_h * 0.13,
        img_h * 0.20,
        min_score=0.30,
    )

    dates = _extract_date_candidates(top_band)
    dates = sorted(dates, key=lambda d: d["x1"])

    date_of_death = dates[0]["text"] if len(dates) >= 1 else ""
    date_of_birth = dates[-1]["text"] if len(dates) >= 2 else ""

    age_region = _tokens_in_region(
        items,
        img_w * 0.58,
        img_w * 0.74,
        img_h * 0.14,
        img_h * 0.20,
        min_score=0.30,
    )

    age_candidates = []
    target_x = img_w * 0.64

    for it in age_region:
        nt = _norm_text(it["text"])
        if re.fullmatch(r"\d{1,3}", nt):
            val = int(nt)
            if 0 <= val <= 130:
                age_candidates.append(
                    (
                        abs(it["cx"] - target_x),
                        -it["score"],
                        it["x1"],
                        nt,
                    )
                )

    age = ""
    if age_candidates:
        age_candidates.sort()
        age = age_candidates[0][3]

    return date_of_death, date_of_birth, age


def _extract_place_of_birth(items, img_w, img_h):
    pob_label = _find_label(
        items,
        required_all=["PLACE", "BIRTH"],
        forbidden=["DEATH", "MARRIAGE"],
        x_min=0,
        x_max=img_w * 0.38,
        y_min=img_h * 0.12,
        y_max=img_h * 0.26,
    )

    civil_label = _find_label(
        items,
        required_all=["CIVIL", "STATUS"],
        x_min=img_w * 0.60,
        x_max=img_w,
        y_min=img_h * 0.14,
        y_max=img_h * 0.24,
    )

    if pob_label:
        xmin = pob_label["x2"] + 6
        xmax = civil_label["x1"] - 10 if civil_label else img_w * 0.62
        ymin = pob_label["y1"] - 10
        ymax = pob_label["y2"] + 50
        if civil_label and civil_label["y1"] > pob_label["y1"]:
            ymax = min(ymax, civil_label["y1"] + 5)
        region = _tokens_in_region(items, xmin, xmax, ymin, ymax, min_score=0.20)
        text = _choose_best_row(
            region,
            banned_words=["PLACE", "BIRTH", "CIVIL", "STATUS", "CITIZENSHIP", "RESIDENCE", "REGISTRY"],
            prefer_y=pob_label["cy"] + 10,
        )
        if text and _alpha_count(text) >= 3:
            return text
        rows = _group_rows(region)
        for row in rows:
            candidate = _join_tokens(row)
            nt = _norm_text(candidate)
            if _alpha_count(nt) >= 4 and "PLACE" not in nt and "BIRTH" not in nt:
                return _clean_text(candidate)
    region = _tokens_in_region(
        items,
        img_w * 0.20,
        img_w * 0.58,
        img_h * 0.16,
        img_h * 0.22,
        min_score=0.20,
    )
    text = _choose_best_row(
        region,
        banned_words=["CITIZENSHIP", "RESIDENCE", "RELIGION", "MARRIED", "SINGLE", "PLACE", "DEATH"],
        prefer_y=img_h * 0.19,
    )
    return text if text and _alpha_count(text) >= 3 else ""


def _strip_place_of_death_instruction(text: str) -> str:
    """Remove the field label/instruction so only the actual place remains."""
    if not text or not text.strip():
        return ""
    # Work with normalized text (only letters/digits/spaces)
    t = _norm_text(text)

    # Drop leading item number, e.g. "6. "
    t = re.sub(r"^\d+\.?\s*", "", t)

    # Remove the "PLACE OF DEATH" label itself
    t = re.sub(r"\bPLACE\s+OF\s+DEATH\b", " ", t, flags=re.I)

    # Remove the long instruction block that often appears instead of data:
    # "NAME OF HOSPITAL INSTITUTION HOUSE NO ST BARANGAY CITY MUNICIPALITY PROVINCE"
    t = re.sub(
        r"NAME\s+OF\s+HOSPITAL\s+INSTITUTION\s+HOUSE\s+NO\s+ST(?:REET)?\s+BARANGAY\s+CITY\s+MUNICIPALITY\s+PROVINCE",
        " ",
        t,
        flags=re.I,
    )

    # Be defensive and also strip shorter variants if they appear
    t = re.sub(
        r"NAME\s+OF\s+HOSPITAL\s+INSTITUTION\s+HOUSE\s+NO\s+ST(?:REET)?",
        " ",
        t,
        flags=re.I,
    )

    t = re.sub(r"\s+", " ", t).strip(" .:-,")
    return t.strip() if _alpha_count(t) >= 2 else ""


def _is_date_text(text: str) -> bool:
    """Check if text looks like a date (contains month name and/or year)."""
    nt = _norm_text(text)
    
    # Check for month names
    if any(month in nt for month in MONTHS):
        return True
    
    # Check for year patterns
    if re.search(r"\b(19|20)\d{2}\b", nt):
        return True
    
    # Check for day numbers (1-31) followed by month or year
    if re.search(r"\b\d{1,2}\s+(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\b", nt, re.I):
        return True
    
    return False


def _find_place_of_death_fallback(items, img_w, img_h):
    """Fallback: Search for place of death in the expected area of the form."""
    # Look in the typical place of death area (left side, middle portion)
    for it in items:
        if it["score"] < 0.20:
            continue
        # Skip if too high or too low
        if it["cy"] < img_h * 0.15 or it["cy"] > img_h * 0.25:
            continue
        # Skip if too far right
        if it["cx"] > img_w * 0.55:
            continue
            
        txt = _clean_text(it["text"])
        nt = _norm_text(txt)
        
        # Skip if too short
        if len(nt) < 4:
            continue
            
        # CRITICAL: Skip if it looks like a date (this was the bug!)
        if _is_date_text(txt):
            continue
            
        # Skip if contains year (even without month)
        if re.search(r"\b(19|20)\d{2}\b", nt):
            continue
            
        if any(kw in nt for kw in ["NAME", "DATE", "DEATH", "SEX", "AGE", "TYPE", "ORDER", "CITIZEN", "CAUSE", "CIVIL", "STATUS", "BIRTH"]):
            continue
            
        # Look for location-like words
        if any(loc in nt for loc in LOCATION_KEYWORDS):
            return txt
            
        # Also accept text that's likely a place (has multiple words and no numbers)
        if " " in txt and len(txt) > 6 and not re.search(r"\d", nt):
            return txt
    
    return ""


def _extract_place_of_death(items, img_w, img_h):
    # FIXED: Improved extraction with better fallback handling
    
    # First try: Find "Place of Death" label and extract value next to it
    place_label = _find_label(
        items,
        required_all=["PLACE", "DEATH"],
        forbidden=["EXTERNAL", "CERTIFICATION"],
        x_min=0,
        x_max=img_w * 0.35,
        y_min=img_h * 0.16,
        y_max=img_h * 0.23,
    )

    civil_label = _find_label(
        items,
        required_all=["CIVIL", "STATUS"],
        x_min=img_w * 0.65,
        x_max=img_w,
        y_min=img_h * 0.16,
        y_max=img_h * 0.23,
    )

    if place_label:
        xmin = place_label["x2"] + 5
        xmax = civil_label["x1"] - 10 if civil_label else img_w * 0.60
        ymin = place_label["y1"] - 6
        ymax = place_label["y2"] + 40  # Increased from 30 to capture more area
        
        region = _tokens_in_region(items, xmin, xmax, ymin, ymax, min_score=0.25)  # Lowered from 0.30
        
        if region:
            text = _choose_best_row(
                region,
                banned_words=["PLACE", "DEATH", "CIVIL", "STATUS", "CITIZENSHIP", "RESIDENCE", "NAME", "HOSPITAL", "INSTITUTION"],
                prefer_y=place_label["cy"] + 8,
            )
            if text:
                cleaned = _strip_place_of_death_instruction(text)
                # CRITICAL: Don't return if it looks like a date
                if cleaned and _alpha_count(cleaned) >= 2 and not _is_date_text(cleaned):
                    return cleaned

    # Second try: Fallback zone - search in typical place of death area
    region = _tokens_in_region(
        items,
        img_w * 0.15,  # Slightly wider left boundary
        img_w * 0.55,
        img_h * 0.16,
        img_h * 0.24,  # Slightly expanded vertical range
        min_score=0.20,
    )
    
    if region:
        text = _choose_best_row(
            region,
            banned_words=["CITIZENSHIP", "RESIDENCE", "RELIGION", "MARRIED", "SINGLE", "PLACE", "DEATH", "CAUSE", "NAME", "HOSPITAL"],
            prefer_y=img_h * 0.19,
        )
        if text:
            cleaned = _strip_place_of_death_instruction(text)
            # CRITICAL: Don't return if it looks like a date
            if cleaned and _alpha_count(cleaned) >= 2 and not _is_date_text(cleaned):
                return cleaned

    # Third try: Search for location-like text anywhere in the form
    fallback_result = _find_place_of_death_fallback(items, img_w, img_h)
    if fallback_result:
        return fallback_result

    # Last resort: Try to find any text that looks like a place in the death section
    for it in items:
        if it["score"] < 0.25:
            continue
        # Focus on middle-left portion where place of death typically is
        if it["cx"] < img_w * 0.15 or it["cx"] > img_w * 0.50:
            continue
        if it["cy"] < img_h * 0.15 or it["cy"] > img_h * 0.26:
            continue
            
        txt = _clean_text(it["text"])
        nt = _norm_text(txt)
        
        # Skip short text and numbers
        if len(nt) < 5:
            continue
        if re.fullmatch(r"\d+", nt):
            continue
            
        # Skip form labels
        if any(kw in nt for kw in ["PLACE", "DEATH", "CAUSE", "CIVIL", "STATUS", "NAME", "DATE", "SEX", "AGE"]):
            continue
            
        return txt

    return ""


def _extract_civil_status(items, img_w, img_h):
    region = _tokens_in_region(
        items,
        img_w * 0.72,
        img_w * 0.95,
        img_h * 0.17,
        img_h * 0.22,
        min_score=0.30,
    )
    return _best_exact_choice(region, STATUS_WORDS)


def _extract_nationality(items, img_w, img_h):
    cit_label = None
    best_score = None

    for it in items:
        nt = _norm_text(it["text"])

        if not (img_w * 0.18 <= it["cx"] <= img_w * 0.46 and img_h * 0.18 <= it["cy"] <= img_h * 0.24):
            continue

        score = 0
        if "CIT" in nt:
            score += 3
        if "SHIP" in nt or "SHP" in nt or "ASIHP" in nt or "IZEN" in nt:
            score += 2
        if nt.startswith("9") or nt.startswith("8") or nt.startswith("10"):
            score += 0.5

        if score <= 0:
            continue

        tup = (score, it["score"], -abs(it["cx"] - img_w * 0.30))
        if cit_label is None or tup > best_score:
            cit_label = it
            best_score = tup

    if cit_label:
        region = _tokens_in_region(
            items,
            cit_label["x1"] - 20,
            cit_label["x2"] + 120,
            cit_label["y2"] + 1,
            cit_label["y2"] + 22,
            min_score=0.30,
        )

        rows = _group_rows(region)
        candidates = []

        for row in rows:
            text = _join_tokens(row)
            nt = _norm_text(text)

            if not nt:
                continue

            if any(
                b in nt
                for b in [
                    "FATHER",
                    "MOTHER",
                    "OCCUPATION",
                    "MAIDEN",
                    "PLACE",
                    "DEATH",
                    "RESIDENCE",
                    "RELIGION",
                    "HOUSE",
                    "BARANGAY",
                    "CITY",
                    "MUNICIPALITY",
                    "CITIZENSHIP",
                ]
            ):
                continue

            if re.search(r"\d", nt):
                continue

            words = nt.split()
            if not (1 <= len(words) <= 3):
                continue

            letters = _alpha_count(text)
            if letters < 4:
                continue

            row_y = sum(x["cy"] for x in row) / len(row)
            avg_score = sum(x["score"] for x in row) / len(row)

            candidates.append(
                (
                    -abs(row_y - (cit_label["y2"] + 8)),
                    avg_score,
                    -len(nt),
                    nt,
                )
            )

        if candidates:
            candidates.sort(reverse=True)
            best = candidates[0][3]

            fixes = {
                "FLPINO": "FILIPINO",
                "FLIPINO": "FILIPINO",
            }
            return fixes.get(best, best)

    fallback = _tokens_in_region(
        items,
        img_w * 0.23,
        img_w * 0.40,
        img_h * 0.205,
        img_h * 0.238,
        min_score=0.30,
    )

    candidates = []
    for it in fallback:
        nt = _norm_text(it["text"])

        if any(b in nt for b in ["FATHER", "MOTHER", "RELIGION", "RESIDENCE", "CITIZENSHIP"]):
            continue
        if re.search(r"\d", nt):
            continue

        words = nt.split()
        if 1 <= len(words) <= 3 and _alpha_count(nt) >= 4:
            candidates.append((it["score"], -len(nt), nt))

    if candidates:
        candidates.sort(reverse=True)
        best = candidates[0][2]
        fixes = {
            "FLPINO": "FILIPINO",
            "FLIPINO": "FILIPINO",
        }
        return fixes.get(best, best)

    return ""


def _extract_cause_of_death(items, img_w, img_h):
    immediate_label = _find_label(
        items,
        required_all=["IMMEDIATE", "CAUSE"],
        x_min=0,
        x_max=img_w * 0.30,
        y_min=img_h * 0.26,
        y_max=img_h * 0.35,
    )

    if immediate_label:
        region = _tokens_in_region(
            items,
            immediate_label["x2"] + 15,
            img_w * 0.72,
            immediate_label["y1"] - 8,
            immediate_label["y2"] + 12,
            min_score=0.30,
        )
        text = _choose_best_row(
            region,
            banned_words=["IMMEDIATE", "CAUSE", "ANTECEDENT", "UNDERLYING", "INTERVAL"],
            prefer_y=immediate_label["cy"],
        )
        text = re.sub(r"^\bA\b\s*", "", text, flags=re.I).strip(" .:-")
        if text:
            return text

    cause_label = _find_label(
        items,
        required_all=["CAUSE", "DEATH"],
        forbidden=["EXTERNAL"],
        x_min=0,
        x_max=img_w * 0.50,
        y_min=img_h * 0.26,
        y_max=img_h * 0.35,
    )

    if cause_label:
        region = _tokens_in_region(
            items,
            img_w * 0.30,
            img_w * 0.72,
            cause_label["y1"] - 5,
            cause_label["y2"] + 25,
            min_score=0.30,
        )
        text = _choose_best_row(
            region,
            banned_words=["CAUSE", "DEATH", "INTERVAL", "EXTERNAL", "PLACE OF OCCURENCE"],
            prefer_y=cause_label["cy"] + 8,
        )
        if text:
            return text

    return ""


def _extract_date_of_registration(items, img_w, img_h) -> str:
    """
    Try to read Date of Registration from the upper-right area.
    Common layout places this near the registry number.
    """
    region = _tokens_in_region(
        items,
        img_w * 0.45,
        img_w * 0.98,
        img_h * 0.02,
        img_h * 0.22,
        min_score=0.25,
    )
    dates = _extract_date_candidates(region)
    if not dates:
        return ""
    dates.sort(key=lambda d: d["x1"])
    # Usually the registration date is farther to the right in the top band.
    return dates[-1]["text"]


def _best_status_anywhere(items) -> str:
    """Fallback for civil status if the fixed region misses it."""
    best = ""
    best_score = -1.0
    for it in items:
        nt = _norm_text(it["text"])
        if nt in STATUS_WORDS and it["score"] > best_score:
            best = nt
            best_score = it["score"]
    return best


def _extract_age_anywhere(items, img_w, img_h) -> str:
    """
    Fallback age detector: look in the upper-middle section for 1-3 digit values.
    Keeps realistic human ages only.
    """
    region = _tokens_in_region(
        items,
        img_w * 0.45,
        img_w * 0.82,
        img_h * 0.10,
        img_h * 0.26,
        min_score=0.25,
    )
    candidates = []
    for it in region:
        nt = _norm_text(it["text"])
        if not re.fullmatch(r"\d{1,3}", nt):
            continue
        val = int(nt)
        if 0 <= val <= 130:
            candidates.append((it["score"], -abs(it["cx"] - (img_w * 0.64)), nt))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def _extract_nationality_anywhere(items, img_w, img_h) -> str:
    """
    Fallback nationality detection around the citizenship band.
    """
    fallback = _tokens_in_region(
        items,
        img_w * 0.20,
        img_w * 0.52,
        img_h * 0.17,
        img_h * 0.26,
        min_score=0.25,
    )
    candidates = []
    for it in fallback:
        nt = _norm_text(it["text"])
        if any(
            b in nt
            for b in [
                "FATHER",
                "MOTHER",
                "RELIGION",
                "RESIDENCE",
                "CITIZENSHIP",
                "PLACE",
                "DEATH",
                "REGISTRY",
                "STATUS",
            ]
        ):
            continue
        if re.search(r"\d", nt):
            continue
        words = nt.split()
        if 1 <= len(words) <= 3 and _alpha_count(nt) >= 4:
            candidates.append((it["score"], -len(nt), nt))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    best = candidates[0][2]
    fixes = {
        "FLPINO": "FILIPINO",
        "FLIPINO": "FILIPINO",
    }
    return fixes.get(best, best)


def _field_confidence(field_name: str, value: str, source: str = "layout") -> str:
    v = (value or "").strip()
    if not v:
        return "LOW"
    n = _norm_text(v)

    if source == "template":
        return "MEDIUM"

    if field_name == "Sex":
        return "HIGH" if n in {"MALE", "FEMALE", "M", "F"} else "MEDIUM"
    if field_name in {"Date of Death", "Date of Registration"}:
        return "HIGH" if _is_full_date(v) else "MEDIUM"
    if field_name == "Age":
        return "HIGH" if re.fullmatch(r"\d{1,3}", n) else "MEDIUM"
    if field_name == "Registry Number":
        compact = n.replace(" ", "")
        if re.fullmatch(r"[A-Z0-9]{2,10}[-/][A-Z0-9]{2,10}", compact):
            return "HIGH"
        return "MEDIUM"
    if field_name in {"Name of Deceased", "Name of Mother", "Place of Death", "Cause of Death", "Civil Status", "Nationality"}:
        return "HIGH" if _alpha_count(v) >= 4 else "MEDIUM"
    return "MEDIUM"


def extract_death_data(img_path: str) -> Dict[str, Any]:
    """
    Run OCR on a death certificate image and return structured data.
    Returns only the fields present on the death certificate form:
    Registry Number, Date of Registration, Name of Deceased, Sex, Age,
    Civil Status, Nationality, Name of Mother, Date of Death, Place of Death, Cause of Death.
    """
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {img_path}")

    img_h, img_w = img.shape[:2]
    result = run_ocr_on_image(img)

    # Template-first extraction (folder-based JSON templates).
    # Merge mode: fill blanks using templates, then keep existing extractor as primary.
    tpl_map: Dict[str, str] = {}
    try:
        ocr_text = ocr_pages_to_text(result)
        tpl = extract_from_ocr_text(ocr_text, doc_type="death", best_effort=True)
        fields = (tpl.get("fields") or {}) if isinstance(tpl, dict) else {}
        if DEBUG_TEMPLATE_MATCH:
            found = sum(1 for v in fields.values() if v)
            print(
                f"[OCR DEATH TEMPLATE] path={tpl.get('template_path')} "
                f"score={tpl.get('match_score')} fields={found}/{len(fields)}"
            )
        found = sum(1 for v in fields.values() if v)
        if tpl.get("template_path") and found >= 1:
            def _v(k: str) -> str:
                val = fields.get(k)
                return str(val).strip() if val else ""

            tpl_map = {
                "Registry Number": _v("registry_number"),
                "Name of Deceased": _v("name_of_deceased"),
                "Sex": _v("sex"),
                "Name of Mother": _v("name_of_mother"),
                "Date of Death": _v("date_of_death"),
                "Place of Death": _v("place_of_death"),
                "Cause of Death": _v("cause_of_death"),
            }
    except Exception:
        # Fall back to the existing layout-based extractor below.
        pass

    items = _build_items(result, img_w, img_h)

    registry_number = _extract_registry_number(items, img_w, img_h)
    date_of_registration = _extract_date_of_registration(items, img_w, img_h)
    name_of_deceased = _extract_name(items, img_w, img_h)
    sex = _extract_sex(items, img_w, img_h)
    date_of_death, _, age = _extract_dates_and_age(items, img_w, img_h)
    place_of_death = _extract_place_of_death(items, img_w, img_h)
    civil_status = _extract_civil_status(items, img_w, img_h)
    nationality = _extract_nationality(items, img_w, img_h)
    name_of_mother = _extract_name_of_mother(items, img_w, img_h)
    cause_of_death = _extract_cause_of_death(items, img_w, img_h)

    # Global fallbacks for fields that often become blank on noisy scans.
    if not age:
        age = _extract_age_anywhere(items, img_w, img_h)
    if not civil_status:
        civil_status = _best_status_anywhere(items)
    if not nationality:
        nationality = _extract_nationality_anywhere(items, img_w, img_h)
    if not date_of_death:
        all_dates = _extract_date_candidates(items)
        if all_dates:
            all_dates.sort(key=lambda d: (d["y1"], d["x1"]))
            date_of_death = all_dates[0]["text"]
    if not date_of_registration:
        # Final fallback: pick a top-right date if present.
        top_right = _tokens_in_region(items, img_w * 0.50, img_w * 0.98, 0, img_h * 0.25, min_score=0.25)
        top_dates = _extract_date_candidates(top_right)
        if top_dates:
            top_dates.sort(key=lambda d: d["x1"])
            date_of_registration = top_dates[-1]["text"]

    out = {
        "Registry Number": registry_number,
        "Date of Registration": date_of_registration,
        "Name of Deceased": name_of_deceased,
        "Sex": sex,
        "Age": age,
        "Civil Status": civil_status,
        "Nationality": nationality,
        "Name of Mother": name_of_mother,
        "Date of Death": date_of_death,
        "Place of Death": place_of_death,
        "Cause of Death": cause_of_death,
    }
    before_template = {k: (out.get(k) or "") for k in out.keys()}
    # Fill missing values with template results (if any).
    for k, v in (tpl_map or {}).items():
        if v and not (out.get(k) or "").strip():
            out[k] = v
    ordered_fields = [
        "Registry Number",
        "Date of Registration",
        "Name of Deceased",
        "Sex",
        "Age",
        "Civil Status",
        "Nationality",
        "Name of Mother",
        "Date of Death",
        "Place of Death",
        "Cause of Death",
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
