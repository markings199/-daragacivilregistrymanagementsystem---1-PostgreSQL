"""Fill Municipal Form No. 103 with sample handwriting-style values for OCR testing."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BLANK = Path(
    r"C:\Users\63951\.cursor\projects\c-daragacivilregistrymanagementsystem-1"
    r"\assets\c__Users_63951_AppData_Roaming_Cursor_User_workspaceStorage_"
    r"dd289e845fb35c442ee5b07d79fd38d8_images_D_FORMAT-033bf404-8f74-400e-967a-6f7f4321b624.jpg"
)
APP = Path(__file__).resolve().parent.parent
OUT_DIR = APP / "ocr" / "templates"
OUT_JPG = OUT_DIR / "death_form103_example.jpg"
OUT_PNG = OUT_DIR / "death_form103_example.png"
BLANK_COPY = OUT_DIR / "death_form103.jpg"

INK = (18, 42, 110)
INK_DARK = (12, 22, 70)
SCALE = 4

HAND = ImageFont.truetype(r"C:\Windows\Fonts\Inkfree.ttf", 1)
PRINT = ImageFont.truetype(r"C:\Windows\Fonts\comic.ttf", 1)
SCRIPT = ImageFont.truetype(r"C:\Windows\Fonts\LHANDW.TTF", 1)


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    path = {
        "hand": r"C:\Windows\Fonts\Inkfree.ttf",
        "print": r"C:\Windows\Fonts\comic.ttf",
        "script": r"C:\Windows\Fonts\LHANDW.TTF",
    }[kind]
    return ImageFont.truetype(path, size)


def main() -> None:
    src = Image.open(BLANK).convert("RGB")
    img = src.resize((src.width * SCALE, src.height * SCALE), Image.Resampling.LANCZOS)
    w, h = img.size
    d = ImageDraw.Draw(img)

    def xy(fx: float, fy: float) -> tuple[int, int]:
        return int(w * fx), int(h * fy)

    def write(text: str, fx: float, fy: float, size: int = 36, kind: str = "hand", fill=INK) -> None:
        d.text(xy(fx, fy), text, font=font(kind, size), fill=fill)

    def mark(fx: float, fy: float, size: int = 28) -> None:
        x, y = xy(fx, fy)
        d.line([(x, y), (x + size, y + size)], fill=INK_DARK, width=3)
        d.line([(x + size, y), (x, y + size)], fill=INK_DARK, width=3)

    # Header
    write("Albay", 0.22, 0.078, 34)
    write("Daraga", 0.28, 0.098, 34)
    write("2026-000456", 0.72, 0.084, 36, "print")

    # 1. NAME  2. SEX
    write("JUAN", 0.175, 0.122, 36, "print")
    write("DELA CRUZ", 0.385, 0.122, 34, "print")
    write("SANTOS", 0.58, 0.122, 36, "print")
    write("Male", 0.815, 0.122, 34, "print")

    # 3. DATE OF DEATH  4. DATE OF BIRTH  5. AGE
    write("10", 0.125, 0.162, 32, "print")
    write("August", 0.185, 0.162, 30, "print")
    write("2026", 0.285, 0.162, 32, "print")
    write("05", 0.375, 0.162, 32, "print")
    write("June", 0.435, 0.162, 30, "print")
    write("1958", 0.515, 0.162, 32, "print")
    write("68", 0.605, 0.162, 36, "print")

    # 6. PLACE OF DEATH  7. CIVIL STATUS
    write("Daraga Community Hospital, Purok 3, Brgy. San Roque, Daraga, Albay", 0.12, 0.192, 26)
    write("Married", 0.76, 0.192, 32, "print")

    # 8-10
    write("Roman Catholic", 0.115, 0.222, 26)
    write("Filipino", 0.355, 0.222, 28)
    write("Purok 3, Brgy. San Roque, Daraga, Albay", 0.545, 0.222, 24)

    # 11-13
    write("Farmer", 0.115, 0.252, 28)
    write("Pedro Santos", 0.355, 0.252, 28)
    write("Maria Cruz", 0.655, 0.252, 28)

    # 19b Causes of death (the fields OCR must read)
    write("Cardiopulmonary arrest", 0.30, 0.326, 28)
    write("Minutes", 0.78, 0.326, 24)
    write("Acute myocardial infarction", 0.30, 0.343, 26)
    write("2 days", 0.78, 0.343, 24)
    write("Hypertensive heart disease", 0.30, 0.358, 26)
    write("10 years", 0.78, 0.358, 24)
    write("Type 2 Diabetes Mellitus", 0.48, 0.374, 24)

    # 19c maternal: not applicable (male). 19d external: none.
    write("No", 0.875, 0.418, 26, "print")

    # 21a Attendant — 3 Hospital Authority
    mark(0.305, 0.458, 22)
    write("Aug 8, 2026", 0.70, 0.468, 22)
    write("Aug 10, 2026", 0.835, 0.468, 22)

    # 22 Certification of death
    write("2:30", 0.455, 0.522, 26, "print")
    write("AM", 0.545, 0.522, 22, "print")
    mark(0.805, 0.512, 18)
    write("Elena M. Bautista", 0.18, 0.542, 28, "script")
    write("Elena M. Bautista", 0.20, 0.556, 24)
    write("Attending Physician", 0.20, 0.570, 22)
    write("Daraga Community Hospital", 0.20, 0.582, 20)
    write("August 10, 2026", 0.28, 0.582, 20)
    write("Ramon V. Reyes, MHO", 0.64, 0.548, 24, "script")
    write("August 10, 2026", 0.70, 0.582, 20)

    # 23-25
    write("Burial", 0.14, 0.608, 26)
    write("2026-0881", 0.42, 0.602, 24, "print")
    write("August 11, 2026", 0.42, 0.618, 20)
    write("Daraga Municipal Cemetery, Daraga, Albay", 0.14, 0.638, 24)

    # 26 Informant
    write("Roberto S. Cruz", 0.18, 0.702, 26, "script")
    write("Roberto S. Cruz", 0.20, 0.716, 22)
    write("Father", 0.28, 0.730, 22)
    write("Purok 3, Brgy. San Roque, Daraga, Albay", 0.20, 0.744, 20)
    write("August 10, 2026", 0.20, 0.758, 20)

    # 27 Prepared by
    write("Ana P. Rivera", 0.62, 0.702, 26, "script")
    write("Ana P. Rivera", 0.64, 0.716, 22)
    write("Municipal Civil Registry Staff", 0.64, 0.730, 18)
    write("August 10, 2026", 0.64, 0.744, 20)

    # 28 Received by
    write("Liza P. Garcia", 0.18, 0.792, 24, "script")
    write("Liza P. Garcia", 0.20, 0.806, 20)
    write("Administrative Aide", 0.20, 0.818, 18)
    write("August 10, 2026", 0.20, 0.830, 18)

    # 29 Registered
    write("Carlos M. Santos", 0.62, 0.792, 24, "script")
    write("Carlos M. Santos", 0.64, 0.806, 20)
    write("Municipal Civil Registrar", 0.64, 0.818, 18)
    write("August 10, 2026", 0.64, 0.830, 18)

    write("Sample Form 103 for OCR testing — Daraga LCR", 0.14, 0.848, 20)

    # Bottom coding boxes (age / date of death)
    write("68", 0.14, 0.888, 22, "print")
    write("10", 0.22, 0.888, 22, "print")
    write("08", 0.30, 0.888, 22, "print")
    write("2026", 0.38, 0.888, 22, "print")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PNG)
    img.save(OUT_JPG, quality=95, subsampling=0)
    if not BLANK_COPY.exists():
        src.save(BLANK_COPY, quality=95)
    print(f"saved {OUT_JPG}")
    print(f"saved {OUT_PNG}")
    print(f"size {img.size}")


if __name__ == "__main__":
    main()
