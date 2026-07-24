"""
APScheduler cron job — retries failed/stuck documents every 15 minutes.
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.connection import get_pool, set_rls_user
from services.pipeline import run_document_pipeline
from services.scheduler import get_scheduler

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
STUCK_AFTER_MINUTES = 5


async def retry_failed_documents():
    """
    Find documents that are failed or stuck in pending/processing
    for more than STUCK_AFTER_MINUTES, and retry their pipeline.
    """
    logger.info("[CRON] Checking for documents to retry...")
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Use superuser context (no RLS) for cron — we query all users
        await conn.execute("SET LOCAL app.current_user_id = '00000000-0000-0000-0000-000000000000'")

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_AFTER_MINUTES)

        # Disable RLS for the cron query (it needs to see all users' documents)
        await conn.execute("SET LOCAL row_security = off")

        rows = await conn.fetch(
            """
            SELECT id::text, file_path, mime_type, user_id::text
            FROM documents
            WHERE (
                status IN ('failed', 'pending', 'ocr_processing', 'embedding')
                AND updated_at < $1
                AND retry_count < $2
            )
            ORDER BY updated_at ASC
            LIMIT 20
            """,
            cutoff,
            MAX_RETRIES,
        )

        if not rows:
            logger.info("[CRON] No documents to retry.")
            return

        logger.info(f"[CRON] Retrying {len(rows)} documents...")

        for row in rows:
            doc_id = row["id"]
            try:
                logger.info(f"[CRON] Retrying document {doc_id}")
                await run_document_pipeline(
                    doc_id=doc_id,
                    file_path=row["file_path"],
                    mime_type=row["mime_type"] or "application/pdf",
                    user_id=row["user_id"],
                )
            except Exception as e:
                logger.error(f"[CRON] Failed to retry {doc_id}: {e}")


def register_cron_jobs():
    """Register all cron jobs with APScheduler."""
    scheduler = get_scheduler()
    scheduler.add_job(
        retry_failed_documents,
        trigger="interval",
        minutes=15,
        id="retry_failed_documents",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info("[CRON] Jobs registered: retry_failed_documents (every 15 min)")
