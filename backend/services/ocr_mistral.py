"""
Mistral OCR service — primary OCR engine.
Uses mistral-ocr-latest which handles PDFs and images natively.
"""
import base64
import os
from pathlib import Path

from mistralai import Mistral
from core.config import settings


def _get_client() -> Mistral:
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY not set")
    return Mistral(api_key=settings.MISTRAL_API_KEY)


def ocr_file(file_path: str, mime_type: str) -> str:
    """
    Run Mistral OCR on a file. Returns extracted text.
    Supports PDFs and images directly.
    """
    client = _get_client()
    path = Path(file_path)

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    encoded = base64.standard_b64encode(file_bytes).decode("utf-8")

    if mime_type == "application/pdf":
        document = {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{encoded}",
        }
    else:
        document = {
            "type": "image_url",
            "image_url": f"data:{mime_type};base64,{encoded}",
        }

    response = client.ocr.process(
        model="mistral-ocr-latest",
        document=document,
    )

    # Combine text from all pages
    pages_text = []
    for page in response.pages:
        if page.markdown:
            pages_text.append(page.markdown)

    return "\n\n".join(pages_text)
