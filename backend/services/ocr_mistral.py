"""
Mistral OCR service — primary OCR engine.

Uses mistral-ocr-latest via the Mistral Files API:
  1. Upload the file to Mistral Files API to get a signed URL
  2. Pass the signed URL to ocr.process()
  3. Collect markdown from all pages

This avoids base64 encoding huge files inline and works with mistralai>=1.5.0.
"""
import logging
import os
from pathlib import Path

from mistralai import Mistral
from core.config import settings

logger = logging.getLogger(__name__)


def _get_client() -> Mistral:
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY not set")
    return Mistral(api_key=settings.MISTRAL_API_KEY)


def ocr_file(file_path: str, mime_type: str) -> str:
    """
    Run Mistral OCR on a file. Returns extracted text as markdown.
    Supports PDFs and images.

    Strategy:
      - Upload file to Mistral Files API → get a file_id + signed URL
      - Call ocr.process() with the signed URL
      - Delete the uploaded file afterwards (cleanup)
    """
    client = _get_client()
    path = Path(file_path)
    file_name = path.name

    logger.info(f"Uploading {file_name} to Mistral Files API for OCR...")

    # ── Step 1: Upload file ──────────────────────────────────────────
    with open(file_path, "rb") as f:
        upload_response = client.files.upload(
            file={
                "file_name": file_name,
                "content": f,
                "content_type": mime_type,
            },
            purpose="ocr",
        )

    file_id = upload_response.id
    logger.info(f"File uploaded: {file_id}")

    try:
        # ── Step 2: Get signed URL ───────────────────────────────────
        signed = client.files.get_signed_url(file_id=file_id)
        signed_url = signed.url

        # ── Step 3: Run OCR ──────────────────────────────────────────
        logger.info(f"Running mistral-ocr-latest on {file_name}...")

        if mime_type == "application/pdf":
            document = {
                "type": "document_url",
                "document_url": signed_url,
            }
        else:
            document = {
                "type": "image_url",
                "image_url": signed_url,
            }

        ocr_response = client.ocr.process(
            model="mistral-ocr-latest",
            document=document,
            include_image_base64=False,
        )

        # ── Step 4: Combine pages ────────────────────────────────────
        pages_text = []
        for page in ocr_response.pages:
            if page.markdown:
                pages_text.append(page.markdown)

        result = "\n\n".join(pages_text)
        logger.info(f"Mistral OCR complete: {len(result)} chars from {len(ocr_response.pages)} page(s)")
        return result

    finally:
        # ── Cleanup: delete uploaded file ────────────────────────────
        try:
            client.files.delete(file_id=file_id)
            logger.info(f"Deleted temp file {file_id} from Mistral Files API")
        except Exception as e:
            logger.warning(f"Could not delete Mistral file {file_id}: {e}")
