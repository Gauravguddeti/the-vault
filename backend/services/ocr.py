"""
OCR orchestrator — uses Mistral as the sole OCR engine on Render.
Tesseract is NOT available on Render's free tier, so we don't fall back to it.
"""
import logging
from core.config import settings

logger = logging.getLogger(__name__)


def run_ocr(file_path: str, mime_type: str) -> str:
    """
    Run OCR on a file using the configured provider.
    Returns extracted text string.
    Raises RuntimeError if OCR fails.
    """
    provider = settings.OCR_PROVIDER.lower()

    if provider == "mistral":
        return _run_mistral(file_path, mime_type)
    elif provider == "tesseract":
        return _run_tesseract(file_path, mime_type)
    else:
        raise ValueError(f"Unknown OCR_PROVIDER: {provider}")


def _run_mistral(file_path: str, mime_type: str) -> str:
    """Run Mistral OCR (primary engine)."""
    from services import ocr_mistral
    logger.info("Running Mistral OCR...")
    text = ocr_mistral.ocr_file(file_path, mime_type)
    if not text or not text.strip():
        raise RuntimeError("Mistral OCR returned empty text")
    return text


def _run_tesseract(file_path: str, mime_type: str) -> str:
    """Run pytesseract OCR (local only — not available on Render free tier)."""
    from services import ocr_tesseract
    logger.info("Running Tesseract OCR...")
    text = ocr_tesseract.ocr_file(file_path, mime_type)
    logger.info(f"Tesseract OCR complete ({len(text)} chars)")
    return text
