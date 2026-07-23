"""
Tesseract OCR fallback service.
Converts PDFs to images via PyMuPDF then runs pytesseract.
"""
import os
import tempfile
from pathlib import Path

import pytesseract
from PIL import Image

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


def ocr_file(file_path: str, mime_type: str) -> str:
    """
    Run pytesseract OCR on a file. Returns extracted text.
    PDFs are converted to images at 300 DPI before OCR.
    """
    if mime_type == "application/pdf":
        return _ocr_pdf(file_path)
    else:
        return _ocr_image(file_path)


def _ocr_image(file_path: str) -> str:
    """OCR a single image file."""
    image = Image.open(file_path)
    return pytesseract.image_to_string(image, lang="eng")


def _ocr_pdf(file_path: str) -> str:
    """Convert PDF pages to images at 300 DPI, then OCR each page."""
    if not HAS_FITZ:
        raise RuntimeError("PyMuPDF (fitz) not installed — cannot OCR PDFs with tesseract fallback")

    doc = fitz.open(file_path)
    pages_text = []

    with tempfile.TemporaryDirectory(prefix="vault_ocr_") as tmp_dir:
        mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI

        for i, page in enumerate(doc):
            img_path = os.path.join(tmp_dir, f"page_{i+1:04d}.png")
            page.get_pixmap(matrix=mat).save(img_path)
            image = Image.open(img_path)
            text = pytesseract.image_to_string(image, lang="eng")
            if text.strip():
                pages_text.append(f"--- Page {i+1} ---\n{text}")

    doc.close()
    return "\n\n".join(pages_text)
