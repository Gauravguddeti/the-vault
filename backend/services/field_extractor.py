"""
Structured field extractor — sends OCR text to Groq and extracts
amount, date, vendor, category, currency, and crucially ALL line items
so the chatbot can answer "what did I buy/sell" questions.
"""
import json
import logging
import re
from typing import Optional

from groq import Groq
from core.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are an expert document parser. Extract ALL structured data from the document text below.

Return ONLY a valid JSON object with these fields (use null if not found):
{
  "amount": <total amount as a plain number or null>,
  "currency": <"USD"|"EUR"|"GBP"|"INR"|"AUD"|"CAD" or null>,
  "date": <"YYYY-MM-DD" or null>,
  "vendor": <seller/supplier name as string or null>,
  "buyer": <buyer/customer name as string or null>,
  "category": <"medical"|"food"|"transport"|"utilities"|"electronics"|"clothing"|"repairs"|"insurance"|"taxes"|"rent"|"other" or null>,
  "document_type": <"invoice"|"receipt"|"bill"|"medical_report"|"statement"|"other" or null>,
  "invoice_number": <string or null>,
  "items": [
    {
      "name": <product/service name>,
      "quantity": <number or null>,
      "unit_price": <number or null>,
      "total": <number or null>,
      "hsn_code": <HSN/SAC code as string or null>
    }
  ],
  "tax_details": {
    "sgst": <number or null>,
    "cgst": <number or null>,
    "igst": <number or null>,
    "total_tax": <number or null>
  },
  "subtotal": <pre-tax amount as number or null>,
  "discount": <discount amount as number or null>,
  "net_amount": <final payable amount as number or null>,
  "notes": <any additional important notes as string or null>
}

Rules:
- amount: the GRAND TOTAL or final payable amount (plain number, no commas or symbols)
- items: extract EVERY line item present — this is critical. Even if items appear in a table, extract all rows.
- If quantities appear as fractions or decimals, keep them as numbers.
- For medical reports: put test names/results in items (name=test name, total=result value, unit_price=null).
- date: ISO 8601 format YYYY-MM-DD
- Do NOT include markdown, explanation, or text outside the JSON object.

Document text:
"""


def extract_fields(raw_text: str) -> Optional[dict]:
    """
    Use Groq LLM to extract structured fields from OCR text.
    Returns a dict with amount, currency, date, vendor, category, items, etc.
    Returns None if extraction fails.
    """
    if not raw_text or len(raw_text.strip()) < 10:
        return None

    try:
        client = Groq(api_key=settings.GROQ_API_KEY)

        # Use more text for complex invoices with many line items
        truncated = raw_text[:6000]

        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "user", "content": EXTRACTION_PROMPT + truncated}
            ],
            temperature=0.0,
            max_tokens=2048,
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            logger.warning("No JSON found in extraction response")
            return None

        data = json.loads(json_match.group())

        # Validate and coerce types
        amount = data.get("amount") or data.get("net_amount")
        if amount is not None:
            try:
                amount = float(str(amount).replace(",", ""))
            except (ValueError, TypeError):
                amount = None

        # Ensure items is a list
        items = data.get("items", [])
        if not isinstance(items, list):
            items = []

        # Clean items list
        clean_items = []
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                clean_item = {
                    "name": str(item.get("name", "")).strip(),
                    "quantity": item.get("quantity"),
                    "unit_price": item.get("unit_price"),
                    "total": item.get("total"),
                }
                if item.get("hsn_code"):
                    clean_item["hsn_code"] = str(item["hsn_code"])
                clean_items.append(clean_item)

        return {
            "amount": amount,
            "currency": data.get("currency"),
            "date": data.get("date"),
            "vendor": data.get("vendor"),
            "category": data.get("category"),
            "raw_json": {
                **data,
                "items": clean_items,
            },
        }

    except Exception as e:
        logger.error(f"Field extraction failed: {e}")
        return None
