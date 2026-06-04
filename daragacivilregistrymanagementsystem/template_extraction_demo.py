"""
Demo/utility for the folder-based template system.

This does NOT replace your existing extractors; it provides a modular
path you can migrate to gradually.
"""

from typing import Any, Dict, Optional

from ocr_shared import run_ocr_on_image_path
from template_engine import extract_from_ocr_text, ocr_pages_to_text


def extract_document_fields_from_image(image_path: str, doc_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Run OCR (PaddleOCR) and extract fields using JSON templates in:
      templates/<doc_type>/*.json

    If doc_type is None, the system auto-detects it from OCR text.
    """
    pages = run_ocr_on_image_path(image_path)
    text = ocr_pages_to_text(pages)
    return extract_from_ocr_text(text, doc_type=doc_type)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python template_extraction_demo.py <path-to-image> [birth|death|marriage]")
        raise SystemExit(2)

    img = sys.argv[1]
    doc = sys.argv[2] if len(sys.argv) >= 3 else None
    result = extract_document_fields_from_image(img, doc_type=doc)
    print(result)

