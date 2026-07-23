"""
Structured field extractor — sends OCR text to Groq and extracts
amount, date, vendor, category, currency as structured JSON.
"""
import json
import logging
import re
from typing import Optional

from groq import Groq
from core.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a document parser. Extract structured financial data from the following document text.

Return ONLY a valid JSON object with these fields (use null if not found):
{
  "amount": <number or null>,
  "currency": <"USD"|"EUR"|"GBP"|"INR"|"AUD"|"CAD" or null>,
  "date": <"YYYY-MM-DD" or null>,
  "vendor": <string or null>,
  "category": <"medical"|"food"|"transport"|"utilities"|"electronics"|"clothing"|"repairs"|"insurance"|"taxes"|"rent"|"other" or null>
}

Rules:
- amount must be a plain number (no currency symbols, no commas) or null
- date must be ISO 8601 format or null
- If multiple amounts appear, use the TOTAL or GRAND TOTAL
- Do NOT include any explanation, markdown, or text outside the JSON object

Document text:
"""


def extract_fields(raw_text: str) -> Optional[dict]:
    """
    Use Groq LLM to extract structured fields from OCR text.
    Returns a dict with amount, currency, date, vendor, category.
    Returns None if extraction fails.
    """
    if not raw_text or len(raw_text.strip()) < 10:
        return None

    try:
        client = Groq(api_key=settings.GROQ_API_KEY)

        # Truncate text to avoid token limits
        truncated = raw_text[:4000]

        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "user", "content": EXTRACTION_PROMPT + truncated}
            ],
            temperature=0.0,
            max_tokens=256,
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            logger.warning("No JSON found in extraction response")
            return None

        data = json.loads(json_match.group())

        # Validate and coerce types
        amount = data.get("amount")
        if amount is not None:
            try:
                amount = float(str(amount).replace(",", ""))
            except (ValueError, TypeError):
                amount = None

        return {
            "amount": amount,
            "currency": data.get("currency"),
            "date": data.get("date"),
            "vendor": data.get("vendor"),
            "category": data.get("category"),
            "raw_json": data,
        }

    except Exception as e:
        logger.error(f"Field extraction failed: {e}")
        return None
