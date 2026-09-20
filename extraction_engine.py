"""
extraction_engine.py
---------------------
Unified document extraction for HireMatrix. Every uploaded file — no
matter its format — ends up as the same shape: a list of line dicts
`{"text", "confidence", "bbox"}`, so parser.py never needs to know what
kind of file it came from.

Format-specific strategy:

  Images (PNG / JPG / JPEG / BMP / TIFF / WEBP)
      PRIMARY: Google Gemini (multimodal vision) transcribes the image
      directly — far more robust than classic OCR against skewed scans,
      photographed CVs, unusual fonts, low light, etc., because it reads
      the image the way a person would rather than matching character
      shapes pixel-by-pixel. Requires a GEMINI_API_KEY (see config.py).
      FALLBACK: if no API key is configured, or the Gemini call fails
      for any reason (network, quota, bad image), we transparently fall
      back to the original Tesseract pipeline (preprocess -> OCR) so the
      app still works with zero configuration.

  PDF
      HYBRID extraction — most CVs submitted as PDF are "born digital"
      (exported from Word/Canva/a CV builder), so the text is already
      selectable and 100% accurate; OCR would only throw accuracy away.
      For each page:
        1. Try the real text layer directly (pdfplumber).
        2. Only if a page has no usable text layer (i.e. it's a SCANNED
           image saved as PDF) does it fall back to rendering that page
           to an image and running it through the same Gemini-first /
           Tesseract-fallback image pipeline above.
      Native text lines get confidence=100 (exact, not a guess).

  DOCX
      Read directly via python-docx — paragraphs and table cells become
      lines with confidence=100. No OCR/AI call at all.

  TXT
      Read directly as plain text, one line per line, confidence=100.

Every extractor also returns:
    - a "preview" for the Review tab's left panel: a PIL Image where one
      exists (image files, rendered PDF pages), or None for text-native
      formats (DOCX/TXT), where the UI shows extracted text instead.
    - an "extraction_notice" telling the UI which path was used:
      "native" | "gemini" | "ocr" | "mixed"
"""

import io
import json
import logging
import os

import cv2
import numpy as np
import pytesseract
from PIL import Image

import config

logger = logging.getLogger(__name__)

if config.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "tiff", "tif", "webp"}


# ---------------------------------------------------------------------------
# Gemini vision OCR (primary path for images)
# ---------------------------------------------------------------------------
_GEMINI_PROMPT = (
    "You are a precise OCR engine. Read every piece of visible text in this "
    "resume/CV image exactly as written, preserving the original reading "
    "order (top to bottom, left to right within each block). "
    "Return ONLY a JSON array of strings — one entry per distinct line or "
    "short text block (e.g. a heading, a bullet point, a single field like "
    "an email or phone number). Do not merge unrelated lines into one "
    "entry. Do not translate, correct spelling, reformat, or summarize — "
    "transcribe exactly what is written, including any typos. Skip purely "
    "decorative elements (borders, icons with no text, dividers). "
    "Return nothing but the JSON array, no markdown fences, no commentary."
)


def _parse_gemini_json_lines(raw_text: str):
    """Gemini sometimes wraps JSON in ```json fences despite instructions
    not to — strip those defensively before parsing."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    text = text.strip()
    items = json.loads(text)
    if not isinstance(items, list):
        raise ValueError("Gemini did not return a JSON array")
    return [str(item).strip() for item in items if str(item).strip()]

from google import genai

# Streamlit secrets ya local .env se key uthane ka tareeqa
api_key = None
try:
    api_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    pass

if not api_key:
    api_key = os.environ.get("GEMINI_API_KEY")

# Client initialize karein
client = genai.Client(api_key=api_key)
def _gemini_ocr_lines(pil_image: Image.Image):
    """
    Sends the image to Gemini for transcription. Returns a list of line
    dicts on success, or None on ANY failure (missing key, no SDK,
    network error, bad response) so the caller can fall back to Tesseract
    without crashing the app.
    """
    
    response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[_GEMINI_PROMPT, pil_image],
        )
    lines_raw = _parse_gemini_json_lines(response.text)
      if not lines_raw:
            return None
        # Gemini doesn't expose a per-word confidence score like Tesseract;
        # GEMINI_LINE_CONFIDENCE is a flat, high value reflecting that
        # vision-model transcription is generally very reliable. It still
        # participates normally in parser.py's OCR_CONFIDENCE_THRESHOLD
        # check, it just won't usually get flagged as "low confidence".
        return [
            {"text": line, "confidence": config.GEMINI_LINE_CONFIDENCE, "bbox": (0, 0, 0, 0)}
            for line in lines_raw
        ]
    except Exception as exc:
        logger.warning("Gemini OCR failed, falling back to Tesseract: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Tesseract OCR (fallback path for images, and for scanned PDF pages)
# ---------------------------------------------------------------------------
def preprocess_image(pil_image: Image.Image) -> Image.Image:
    """Grayscale -> denoise -> adaptive threshold -> upscale small scans."""
    img = np.array(pil_image.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    h, w = gray.shape
    if max(h, w) < 1500:
        scale = 1500 / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
        blockSize=31, C=15,
    )
    return Image.fromarray(thresh)


def ocr_image_to_lines(pil_image: Image.Image, lang: str = "eng") -> list:
    """Tesseract word-level OCR grouped back into lines, with real per-line confidence."""
    data = pytesseract.image_to_data(
        pil_image, lang=lang, output_type=pytesseract.Output.DICT,
        config="--oem 3 --psm 6",
    )

    lines = {}
    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key not in lines:
            lines[key] = {"words": [], "confs": [], "x": data["left"][i], "y": data["top"][i]}
        lines[key]["words"].append(word)
        lines[key]["confs"].append(conf)
        lines[key]["x"] = min(lines[key]["x"], data["left"][i])
        lines[key]["y"] = min(lines[key]["y"], data["top"][i])

    results = []
    for entry in lines.values():
        text = " ".join(entry["words"])
        avg_conf = sum(entry["confs"]) / len(entry["confs"])
        results.append({"text": text, "confidence": round(avg_conf, 1), "bbox": (entry["x"], entry["y"], 0, 0)})
    return results


def _image_to_lines(pil_image: Image.Image):
    """Gemini-first, Tesseract-fallback pipeline shared by image uploads
    and scanned PDF pages. Returns (lines, extraction_notice)."""
    gemini_lines = _gemini_ocr_lines(pil_image)
    if gemini_lines:
        return gemini_lines, "gemini"

    cleaned = preprocess_image(pil_image)
    return ocr_image_to_lines(cleaned), "ocr"


# ---------------------------------------------------------------------------
# Format: images
# ---------------------------------------------------------------------------
def _extract_image(file_bytes: bytes):
    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    lines, notice = _image_to_lines(image)
    return lines, image, notice


# ---------------------------------------------------------------------------
# Format: PDF — hybrid text-layer + image-pipeline-fallback-per-page
# ---------------------------------------------------------------------------
def _extract_pdf(file_bytes: bytes):
    import pdfplumber

    all_lines = []
    preview_image = None
    used_ocr_notices = set()
    used_native = False

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                used_native = True
                for raw_line in text.splitlines():
                    raw_line = raw_line.strip()
                    if raw_line:
                        all_lines.append({"text": raw_line, "confidence": 100.0, "bbox": (0, 0, 0, 0)})
            else:
                # No selectable text -> scanned page. Render + run the
                # same Gemini-first/Tesseract-fallback pipeline as images.
                page_image = _render_pdf_page_to_image(file_bytes, page_num)
                if page_image is not None:
                    page_lines, page_notice = _image_to_lines(page_image)
                    all_lines.extend(page_lines)
                    used_ocr_notices.add(page_notice)
                    if preview_image is None:
                        preview_image = page_image

            if preview_image is None:
                preview_image = _render_pdf_page_to_image(file_bytes, page_num)

    if used_ocr_notices and used_native:
        notice = "mixed"
    elif "gemini" in used_ocr_notices:
        notice = "gemini"
    elif "ocr" in used_ocr_notices:
        notice = "ocr"
    else:
        notice = "native"

    return all_lines, preview_image, notice


def _render_pdf_page_to_image(file_bytes: bytes, page_index: int):
    """Renders a single PDF page to a PIL Image via pdf2image (needs poppler)."""
    try:
        from pdf2image import convert_from_bytes
        kwargs = {"dpi": 300, "first_page": page_index + 1, "last_page": page_index + 1}
        if config.POPPLER_PATH:
            kwargs["poppler_path"] = config.POPPLER_PATH
        pages = convert_from_bytes(file_bytes, **kwargs)
        return pages[0] if pages else None
    except Exception as exc:
        logger.warning("Could not render PDF page %s to an image: %s", page_index, exc)
        return None


# ---------------------------------------------------------------------------
# Format: DOCX — native text, no OCR/AI at all
# ---------------------------------------------------------------------------
def _extract_docx(file_bytes: bytes):
    import docx

    document = docx.Document(io.BytesIO(file_bytes))
    all_lines = []

    for para in document.paragraphs:
        text = para.text.strip()
        if text:
            all_lines.append({"text": text, "confidence": 100.0, "bbox": (0, 0, 0, 0)})

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    all_lines.append({"text": text, "confidence": 100.0, "bbox": (0, 0, 0, 0)})

    return all_lines, None, "native"


# ---------------------------------------------------------------------------
# Format: TXT — plain text, no OCR/AI at all
# ---------------------------------------------------------------------------
def _extract_txt(file_bytes: bytes):
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1", errors="ignore")

    all_lines = [
        {"text": line.strip(), "confidence": 100.0, "bbox": (0, 0, 0, 0)}
        for line in text.splitlines() if line.strip()
    ]
    return all_lines, None, "native"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def extract_lines_from_file(uploaded_file):
    """
    Dispatches by file extension. Returns:
        (lines, preview_image_or_None, extraction_notice)

    extraction_notice is one of:
        "native" - text came directly from the file (PDF text layer / DOCX / TXT)
        "gemini" - text came from Gemini vision OCR
        "ocr"    - text came from Tesseract OCR (Gemini unavailable/failed)
        "mixed"  - a multi-page PDF used both native text AND an image-based page
    """
    name = uploaded_file.name.lower()
    file_bytes = uploaded_file.read()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""

    if ext in IMAGE_EXTENSIONS:
        return _extract_image(file_bytes)
    if ext == "pdf":
        return _extract_pdf(file_bytes)
    if ext == "docx":
        return _extract_docx(file_bytes)
    if ext == "txt":
        return _extract_txt(file_bytes)

    raise ValueError(f"Unsupported file type: .{ext}")
