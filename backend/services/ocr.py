"""
OCR orchestrator — tries Mistral first, falls back to Tesseract.
Provider can be forced via OCR_PROVIDER env var.
"""
import logging
from core.config import settings

logger = logging.getLogger(__name__)


def run_ocr(file_path: str, mime_type: str) -> str:
    """
    Run OCR on a file using the configured provider chain.
    Returns extracted text string.
    Raises RuntimeError if all providers fail.
    """
    provider = settings.OCR_PROVIDER.lower()

    if provider == "mistral":
        return _try_mistral_then_tesseract(file_path, mime_type)
    elif provider == "tesseract":
        return _run_tesseract(file_path, mime_type)
    else:
        raise ValueError(f"Unknown OCR_PROVIDER: {provider}")


def _try_mistral_then_tesseract(file_path: str, mime_type: str) -> str:
    """Try Mistral OCR; fall back to tesseract on any failure."""
    try:
        from services import ocr_mistral
        logger.info("Attempting Mistral OCR...")
        text = ocr_mistral.ocr_file(file_path, mime_type)
        if text and text.strip():
            logger.info(f"Mistral OCR succeeded ({len(text)} chars)")
            return text
        logger.warning("Mistral OCR returned empty text, falling back to tesseract")
    except Exception as e:
        logger.warning(f"Mistral OCR failed: {e}. Falling back to tesseract.")

    return _run_tesseract(file_path, mime_type)


def _run_tesseract(file_path: str, mime_type: str) -> str:
    """Run pytesseract OCR."""
    from services import ocr_tesseract
    logger.info("Running tesseract OCR...")
    text = ocr_tesseract.ocr_file(file_path, mime_type)
    logger.info(f"Tesseract OCR complete ({len(text)} chars)")
    return text
