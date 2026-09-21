"""Identify birth, marriage, or death from the certificate title at the top of the page."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ocr.engine import detect_document_type_detail, document_type_label


TITLE_TEMPLATE_DIR = Path(__file__).resolve().parent / "title_templates"
_DOC_KEYS = ("birth", "marriage", "death")
_TITLE_REASONS = {
    "birth": "Certificate of Live Birth",
    "marriage": "Certificate of Marriage",
    "death": "Certificate of Death",
}

_TEMPLATE_CACHE: Optional[List[Tuple[str, np.ndarray]]] = None


def _pages_to_text(pages: Optional[List[dict]]) -> str:
    lines: List[str] = []
    for page in pages or []:
        for text in page.get("rec_texts") or []:
            value = str(text or "").strip()
            if value:
                lines.append(value)
    return "\n".join(lines)


def _as_gray(img) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def _resize_width(gray: np.ndarray, width: int) -> np.ndarray:
    height, current = gray.shape[:2]
    if current == width:
        return gray
    scale = width / float(current)
    return cv2.resize(
        gray,
        (width, max(20, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def _prep_band(gray: np.ndarray, width: int) -> np.ndarray:
    band = _resize_width(gray, width)
    return cv2.GaussianBlur(band, (3, 3), 0)


def _load_title_templates() -> List[Tuple[str, np.ndarray]]:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE
    loaded: List[Tuple[str, np.ndarray]] = []
    for key in _DOC_KEYS:
        path = TITLE_TEMPLATE_DIR / f"{key}.png"
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        loaded.append((key, _prep_band(img, 480)))
    _TEMPLATE_CACHE = loaded
    return loaded


def _title_search_band(img) -> np.ndarray:
    gray = _as_gray(img)
    height = gray.shape[0]
    y2 = max(80, int(height * 0.22))
    return _prep_band(gray[0:y2, :], 720)


def _template_score(search: np.ndarray, template: np.ndarray) -> float:
    th, tw = template.shape[:2]
    best = -1.0
    for scale in (0.50, 0.62, 0.74, 0.86, 0.98):
        new_w = int(search.shape[1] * scale)
        new_h = max(16, int(round(th * (new_w / float(tw)))))
        if new_h >= search.shape[0] - 1 or new_w >= search.shape[1] - 1:
            continue
        resized = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(search, resized, cv2.TM_CCOEFF_NORMED)
        best = max(best, float(result.max()))
    return best


def match_title_templates(img) -> Dict[str, Any]:
    """
    Fast visual match of the top heading against the three official
    PSA titles: Certificate of Live Birth, Marriage, and Death.
    """
    empty = {
        "doc_type": None,
        "label": "",
        "confidence": "none",
        "reason": "Title did not match a known certificate",
        "scores": {},
    }
    templates = _load_title_templates()
    if not templates:
        empty["reason"] = "Title templates are missing"
        return empty

    search = _title_search_band(img)
    scores = {key: _template_score(search, tpl) for key, tpl in templates}
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_type, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score

    if best_score >= 0.58 and margin >= 0.08:
        confidence = "high"
    elif best_score >= 0.48 and margin >= 0.05:
        confidence = "medium"
    else:
        empty["scores"] = {k: round(v, 3) for k, v in scores.items()}
        return empty

    return {
        "doc_type": best_type,
        "label": document_type_label(best_type),
        "confidence": confidence,
        "reason": _TITLE_REASONS[best_type],
        "scores": {k: round(v, 3) for k, v in scores.items()},
    }


def _ocr_title_band(img) -> Dict[str, Any]:
    from ocr.shared import run_ocr_on_image

    height, width = img.shape[:2]
    y2 = max(96, int(height * 0.20))
    crop = img[0:y2, 0:width]
    if crop.shape[1] > 720:
        scale = 720.0 / float(crop.shape[1])
        crop = cv2.resize(
            crop,
            (720, max(48, int(round(crop.shape[0] * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    pages = run_ocr_on_image(crop, max_side=720)
    header_text = _pages_to_text(pages)
    detail = detect_document_type_detail(header_text)
    if not detail.get("doc_type"):
        return {
            "doc_type": None,
            "label": "",
            "confidence": "none",
            "reason": detail.get("reason") or "Could not read the certificate heading",
            "header_text": header_text,
        }
    return {
        "doc_type": detail["doc_type"],
        "label": detail.get("label") or document_type_label(detail["doc_type"]),
        "confidence": detail.get("confidence") or "medium",
        "reason": detail.get("reason") or "",
        "header_text": header_text,
    }


def detect_from_image(path: str, ocr_fallback: bool = True) -> Dict[str, Any]:
    """
    Identify a civil-registry certificate from the printed title at the top.
    Visual title matching runs first (no OCR). Header OCR is only a fallback.
    """
    empty = {
        "doc_type": None,
        "label": "",
        "confidence": "none",
        "reason": "Could not read the certificate heading",
        "header_text": "",
    }
    img = cv2.imread(path)
    if img is None:
        empty["reason"] = "Could not open the image"
        return empty

    visual = match_title_templates(img)
    if visual.get("doc_type"):
        visual["header_text"] = visual.get("reason") or ""
        return visual

    if not ocr_fallback:
        visual["header_text"] = ""
        return visual

    return _ocr_title_band(img)
