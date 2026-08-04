"""
Structured field extractor — sends OCR text to Groq and extracts
amount, date, vendor, category, currency, and crucially ALL line items
so the chatbot can answer "what did I buy/sell" questions.

Part 5 addition: per-field confidence scores (0.0–1.0) returned alongside
extracted values. Fields with confidence < CONFIDENCE_THRESHOLD are flagged
as unconfirmed and stored in the unconfirmed_fields table by the pipeline.
"""
import json
import logging
import re
from typing import Optional

from groq import Groq
from core.config import settings

logger = logging.getLogger(__name__)

# Fields with confidence below this threshold are flagged for user confirmation.
# 0.7 = "reasonably sure" — calibrated for messy handwriting / prescription scans.
CONFIDENCE_THRESHOLD = 0.7

# Fields that are "critical" — an answer depending on them must be confirmed first.
# Non-critical fields (e.g. currency, invoice_number) are lower stakes.
CRITICAL_FIELDS = {"vendor", "amount", "date"}

# For medical documents, medication names extracted from items are also critical.
CRITICAL_MEDICAL_ITEM_FIELDS = {"name"}  # item.name in medical context


EXTRACTION_PROMPT = """You are an expert document parser. Extract ALL structured data from the document text below.

For each field, also rate your confidence (0.0 = completely uncertain, 1.0 = absolutely certain).
Low confidence (< 0.7) means: the text was unclear, handwritten, smudged, OCR might have garbled it,
or there are multiple plausible interpretations.

Return ONLY a valid JSON object with these fields (use null if not found):
{
  "amount": <total amount as a plain number or null>,
  "amount_confidence": <0.0-1.0>,
  "currency": <"USD"|"EUR"|"GBP"|"INR"|"AUD"|"CAD" or null>,
  "currency_confidence": <0.0-1.0>,
  "date": <"YYYY-MM-DD" or null>,
  "date_confidence": <0.0-1.0>,
  "vendor": <seller/supplier name as string or null>,
  "vendor_confidence": <0.0-1.0>,
  "buyer": <buyer/customer name as string or null>,
  "buyer_confidence": <0.0-1.0>,
  "category": <"medical"|"food"|"transport"|"utilities"|"electronics"|"clothing"|"repairs"|"insurance"|"taxes"|"rent"|"other" or null>,
  "document_type": <"invoice"|"receipt"|"bill"|"medical_report"|"prescription"|"statement"|"other" or null>,
  "invoice_number": <string or null>,
  "items": [
    {
      "name": <product/service/medication name>,
      "name_confidence": <0.0-1.0>,
      "quantity": <number or null>,
      "unit_price": <number or null>,
      "total": <number or null>,
      "hsn_code": <HSN/SAC code as string or null>,
      "possibly_cancelled": <true if you see a strikethrough, cross-out, or cancellation mark, else false>
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
- name_confidence for items: be especially strict for handwritten medication names.
  If a name looks garbled, OCR-misread, or phonetically strange, give it low confidence (0.2-0.5).
- possibly_cancelled: set true if you can see a strikethrough line through the text, a red X, or words like "cancelled" near the item.
- If quantities appear as fractions or decimals, keep them as numbers.
- For medical reports/prescriptions: put test names/medication names in items.
- date: ISO 8601 format YYYY-MM-DD
- Do NOT include markdown, explanation, or text outside the JSON object.

Document text:
"""


def extract_fields(raw_text: str) -> Optional[dict]:
    """
    Use Groq LLM to extract structured fields from OCR text.
    Returns a dict with amount, currency, date, vendor, category, items,
    confidence scores, and a list of low-confidence fields needing confirmation.
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

        # Clean items list — preserve confidence scores and cancellation flags
        clean_items = []
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                clean_item = {
                    "name": str(item.get("name", "")).strip(),
                    "quantity": item.get("quantity"),
                    "unit_price": item.get("unit_price"),
                    "total": item.get("total"),
                    "name_confidence": float(item.get("name_confidence", 1.0)),
                    "possibly_cancelled": bool(item.get("possibly_cancelled", False)),
                }
                if item.get("hsn_code"):
                    clean_item["hsn_code"] = str(item["hsn_code"])
                clean_items.append(clean_item)

        # ── Build confidence map ──────────────────────────────────────────────
        # Collect per-field confidence from the model's output.
        field_confidences = {
            "amount":   float(data.get("amount_confidence", 1.0)),
            "currency": float(data.get("currency_confidence", 1.0)),
            "date":     float(data.get("date_confidence", 1.0)),
            "vendor":   float(data.get("vendor_confidence", 1.0)),
        }

        # ── Identify low-confidence fields needing confirmation ───────────────
        # Returns a list of dicts ready to insert into unconfirmed_fields table.
        low_confidence_fields = []
        doc_category = data.get("category", "")
        doc_type = data.get("document_type", "")
        is_medical = doc_category == "medical" or doc_type in ("medical_report", "prescription")

        # Top-level critical fields
        for field_name in CRITICAL_FIELDS:
            raw_value = data.get(field_name)
            confidence = field_confidences.get(field_name, 1.0)
            if raw_value is not None and confidence < CONFIDENCE_THRESHOLD:
                low_confidence_fields.append({
                    "field_name": field_name,
                    "raw_value": str(raw_value),
                    "confidence": confidence,
                    "corrected_value": None,  # RxNorm resolution done later in web_search_node
                })

        # Medication names in items (for medical docs — highest risk)
        if is_medical:
            for idx, item in enumerate(clean_items):
                name_conf = item.get("name_confidence", 1.0)
                if name_conf < CONFIDENCE_THRESHOLD:
                    low_confidence_fields.append({
                        "field_name": f"item[{idx}].name",
                        "raw_value": item["name"],
                        "confidence": name_conf,
                        "corrected_value": None,
                        "item_index": idx,
                        "possibly_cancelled": item.get("possibly_cancelled", False),
                    })

        logger.info(
            "[EXTRACTION] %d fields extracted, %d low-confidence: %s",
            len(field_confidences),
            len(low_confidence_fields),
            [f["field_name"] for f in low_confidence_fields],
        )

        return {
            "amount": amount,
            "currency": data.get("currency"),
            "date": data.get("date"),
            "vendor": data.get("vendor"),
            "category": doc_category,
            "document_type": doc_type,
            "field_confidences": field_confidences,
            "low_confidence_fields": low_confidence_fields,
            "raw_json": {
                **data,
                "items": clean_items,
            },
        }

    except Exception as e:
        logger.error(f"Field extraction failed: {e}")
        return None
