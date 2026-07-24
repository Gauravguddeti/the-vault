"""
Document processing pipeline.
Runs: OCR → field extraction → chunking → embedding → status update.
Called as a FastAPI BackgroundTask after upload.
Also called by the cron job for retry/reprocessing.
"""
import json
import logging
from datetime import date, datetime, timezone

import asyncpg

from core.config import settings
from db.connection import get_pool, set_rls_user
from services.ocr import run_ocr
from services.field_extractor import extract_fields
from services.chunker import chunk_text
from services.embedder import embed_chunks

logger = logging.getLogger(__name__)


async def _log_event(conn: asyncpg.Connection, doc_id: str, event: str, detail: str = ""):
    """Write to processing_logs (no RLS on this table)."""
    try:
        await conn.execute(
            "INSERT INTO processing_logs (document_id, event, detail) VALUES ($1::uuid, $2, $3)",
            doc_id, event, detail,
        )
    except Exception as e:
        logger.error(f"Failed to write processing log: {e}")


async def _update_status(conn: asyncpg.Connection, doc_id: str, status: str, error: str = None):
    if error:
        await conn.execute(
            "UPDATE documents SET status=$1, error_message=$2, updated_at=NOW() WHERE id=$3::uuid",
            status, error, doc_id,
        )
    else:
        await conn.execute(
            "UPDATE documents SET status=$1, updated_at=NOW() WHERE id=$2::uuid",
            status, doc_id,
        )


async def run_document_pipeline(
    doc_id: str,
    file_path: str,
    mime_type: str,
    user_id: str,
    require_confirmation: bool = False,
):
    """
    Full async pipeline for a document.
    Must be called with the user's ID so RLS can be applied.
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        await set_rls_user(conn, user_id)

        try:
            # ── Step 1: OCR ──────────────────────────────────────────
            logger.info(f"[{doc_id}] Starting OCR...")
            await _update_status(conn, doc_id, "ocr_processing")
            await _log_event(conn, doc_id, "ocr_start")

            raw_text = run_ocr(file_path, mime_type)

            await conn.execute(
                "UPDATE documents SET raw_text=$1, updated_at=NOW() WHERE id=$2::uuid",
                raw_text, doc_id,
            )
            await _log_event(conn, doc_id, "ocr_success", f"{len(raw_text)} chars extracted")

            # ── Step 2: Field Extraction ──────────────────────────────
            logger.info(f"[{doc_id}] Extracting structured fields...")
            await _log_event(conn, doc_id, "extraction_start")

            fields = extract_fields(raw_text)
            if fields:
                # Parse date string → datetime.date (asyncpg requires a real date object)
                raw_date = fields.get("date")
                txn_date = None
                if raw_date:
                    try:
                        txn_date = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
                    except ValueError:
                        try:
                            # Try other common formats
                            for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y"):
                                try:
                                    txn_date = datetime.strptime(str(raw_date).strip(), fmt).date()
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            pass
                    if txn_date is None:
                        logger.warning(f"[{doc_id}] Could not parse date: {raw_date!r} — storing NULL")

                raw_json = fields.get("raw_json", {})
                raw_json_str = json.dumps(raw_json) if isinstance(raw_json, dict) else json.dumps({})

                await conn.execute(
                    """
                    INSERT INTO extracted_fields
                        (document_id, user_id, amount, currency, txn_date, vendor, category, raw_json)
                    VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb)
                    ON CONFLICT DO NOTHING
                    """,
                    doc_id, user_id,
                    fields.get("amount"),
                    fields.get("currency"),
                    txn_date,                  # datetime.date or None
                    fields.get("vendor"),
                    fields.get("category"),
                    raw_json_str,
                )
                await _log_event(conn, doc_id, "extraction_success")

            if require_confirmation:
                logger.info(f"[{doc_id}] Awaiting confirmation before chunking...")
                await _update_status(conn, doc_id, "awaiting_confirmation")
                return

            # Continue directly to chunking if no confirmation required
            await _run_chunking_internal(conn, doc_id, user_id)

        except Exception as e:
            logger.error(f"[{doc_id}] Pipeline failed: {e}", exc_info=True)
            # Increment retry counter
            await conn.execute(
                """
                UPDATE documents
                SET status='failed', error_message=$1,
                    retry_count=retry_count+1, updated_at=NOW()
                WHERE id=$2::uuid
                """,
                str(e), doc_id,
            )
            await _log_event(conn, doc_id, "pipeline_failed", str(e))

async def run_chunking_pipeline(doc_id: str, user_id: str):
    """Resume pipeline from awaiting_confirmation (called after user confirms)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await set_rls_user(conn, user_id)
        try:
            await _run_chunking_internal(conn, doc_id, user_id)
        except Exception as e:
            logger.error(f"[{doc_id}] Chunking pipeline failed: {e}", exc_info=True)
            await conn.execute(
                """
                UPDATE documents
                SET status='failed', error_message=$1, updated_at=NOW()
                WHERE id=$2::uuid
                """,
                str(e), doc_id,
            )
            await _log_event(conn, doc_id, "pipeline_failed", str(e))

async def _run_chunking_internal(conn: asyncpg.Connection, doc_id: str, user_id: str):
    """Internal helper to run the chunking and embedding steps."""
    logger.info(f"[{doc_id}] Chunking and embedding...")
    await _update_status(conn, doc_id, "embedding")
    await _log_event(conn, doc_id, "embedding_start")

    # Fetch raw_text since it was saved in Step 1
    row = await conn.fetchrow("SELECT raw_text FROM documents WHERE id=$1::uuid", doc_id)
    raw_text = row["raw_text"] if row else ""

    if not raw_text:
        logger.warning(f"[{doc_id}] No raw_text found for chunking")
    else:
        chunks = chunk_text(raw_text)
        if chunks:
            embeddings = await embed_chunks([c["text"] for c in chunks])

            # Delete any existing chunks for this document (re-processing case)
            await conn.execute(
                "DELETE FROM chunks WHERE document_id=$1::uuid", doc_id
            )

            # Batch insert chunks
            for chunk, embedding in zip(chunks, embeddings):
                await conn.execute(
                    """
                    INSERT INTO chunks
                        (document_id, user_id, chunk_index, text, token_count, embedding)
                    VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::vector)
                    """,
                    doc_id, user_id,
                    chunk["chunk_index"],
                    chunk["text"],
                    chunk["token_count"],
                    str(embedding),
                )

            await _log_event(conn, doc_id, "embedding_success", f"{len(chunks)} chunks")

    # ── Step 4: Mark ready ────────────────────────────────────
    await _update_status(conn, doc_id, "ready")
    await _log_event(conn, doc_id, "pipeline_complete")
    logger.info(f"[{doc_id}] Pipeline complete.")
