"""Read Male/Female from OCR without treating printed form prompts as the answer."""
from __future__ import annotations

import re
from typing import Iterable

_PROMPT = re.compile(
    r"\bSEX\b|"
    r"[\(\[]\s*MALE\s*/\s*FEMALE\s*[\)\]]|"
    r"[\(\[]\s*MALE\s+FEMALE\s*[\)\]]|"
    r"\bMALE\s*/\s*FEMALE\b|"
    r"\bMALE\s*[-–]\s*FEMALE\b|"
    r"\bMALE\s+OR\s+FEMALE\b|"
    r"\b1\s*[.)]?\s*MALE\b|"
    r"\b2\s*[.)]?\s*FEMALE\b",
    re.IGNORECASE,
)

_MARK = r"X|\[X\]|✓|✔|■|☑|√"


def _upper(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\\", "/")).upper().strip()


def _count_words(text: str) -> tuple[int, int]:
    females = len(re.findall(r"\bFEMALES?\b", text))
    males = len(re.findall(r"\bMALES?\b", text))
    return males, females


def sex_from_ocr_text(text: str) -> str:
    """
    Return 'Male', 'Female', or '' from OCR text.

    Printed prompts like '(Male/Female)' or '1 Male 2 Female' are ignored so a
    handwritten Male is not flipped to Female just because the label contains both words.
    """
    upper = _upper(text)
    if not upper:
        return ""

    male_mark = re.search(
        rf"(?:(?:^|[^\w])(?:{_MARK})\s*(?:1[.)]?\s*)?MALE\b)|(?:\bMALE\b\s*(?:{_MARK}))",
        upper,
    )
    female_mark = re.search(
        rf"(?:(?:^|[^\w])(?:{_MARK})\s*(?:2[.)]?\s*)?FEMALE\b)|(?:\bFEMALE\b\s*(?:{_MARK}))",
        upper,
    )
    if male_mark and not female_mark:
        return "Male"
    if female_mark and not male_mark:
        return "Female"

    leftover = _PROMPT.sub(" ", upper)
    leftover = re.sub(r"[\(\)\[\]:/,._-]+", " ", leftover)
    leftover = re.sub(r"\s+", " ", leftover).strip()

    males, females = _count_words(leftover)
    if males and not females:
        return "Male"
    if females and not males:
        return "Female"

    if re.fullmatch(r"F|BABAE|GIRL", leftover):
        return "Female"
    if re.fullmatch(r"M|LALAKE|BOY", leftover):
        return "Male"

    orig_males, orig_females = _count_words(upper)
    if orig_males > orig_females:
        return "Male"
    if orig_females > orig_males:
        return "Female"
    return ""


def sex_from_tokens(items: Iterable[dict]) -> str:
    parts = [str(it.get("text") or "") for it in items or [] if str(it.get("text") or "").strip()]
    return sex_from_ocr_text(" ".join(parts))
