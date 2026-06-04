from paddleocr import PaddleOCR
import cv2


class OCREngineNotFoundError(Exception):
    pass


_OCR_INSTANCE = None


def get_ocr() -> PaddleOCR:
    """
    Lazily create a shared PaddleOCR instance.
    """
    global _OCR_INSTANCE
    if _OCR_INSTANCE is not None:
        return _OCR_INSTANCE

    try:
        _OCR_INSTANCE = PaddleOCR(use_textline_orientation=True, lang="en")
    except Exception as exc:
        raise OCREngineNotFoundError(
            "Failed to initialize PaddleOCR engine. Ensure PaddlePaddle is installed and compatible."
        ) from exc
    return _OCR_INSTANCE


def run_ocr_on_image(img):
    """
    Run PaddleOCR on an in-memory image (numpy array, BGR).
    Returns the same "dict per page" structure as run_ocr_on_image_path.
    """
    if img is None:
        raise ValueError("Image is None")
    ocr = get_ocr()
    if hasattr(ocr, "predict"):
        return ocr.predict(img)
    raw = ocr.ocr(img, cls=True)
    pages = []
    for page in raw:
        rec_texts, rec_scores, dt_polys = [], [], []
        for line in page:
            if not line or len(line) != 2:
                continue
            box, (text, score) = line
            rec_texts.append(str(text))
            rec_scores.append(float(score))
            dt_polys.append(box)
        pages.append({"rec_texts": rec_texts, "rec_scores": rec_scores, "dt_polys": dt_polys})
    return pages


def run_ocr_on_image_path(img_path: str):
    """
    Read an image from disk and run PaddleOCR.

    Newer PaddleOCR versions expose .predict(), older ones
    only expose .ocr(). This helper normalizes both into
    the "dict per page" structure expected by the extractors.
    """
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {img_path}")
    return run_ocr_on_image(img)


