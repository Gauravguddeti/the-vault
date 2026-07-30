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

async def extract_all_user_memories():
    """
    Find recent conversations and extract memory.
    """
    logger.info("[CRON] Checking for conversations to extract memory...")
    from services.memory_extractor import run_memory_extraction
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Superuser context
        await conn.execute("SET LOCAL app.current_user_id = '00000000-0000-0000-0000-000000000000'")
        await conn.execute("SET LOCAL row_security = off")
        
        # We only want to process sessions that have been updated recently, 
        # and we can use updated_at to track if we need to process them.
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        
        # Get up to 10 recently active sessions
        sessions = await conn.fetch(
            """
            SELECT id::text, user_id::text
            FROM conversation_sessions
            WHERE updated_at > $1 AND message_count > 0
            ORDER BY updated_at DESC
            LIMIT 10
            """,
            cutoff
        )
        
        for sess in sessions:
            # Fetch conversation text
            messages = await conn.fetch(
                "SELECT role, content FROM conversation_messages WHERE session_id = $1::uuid ORDER BY created_at ASC",
                sess["id"]
            )
            conv_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
            if conv_text:
                await run_memory_extraction(sess["user_id"], sess["id"], conv_text)

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
    scheduler.add_job(
        extract_all_user_memories,
        trigger="interval",
        minutes=30,
        id="extract_user_memories",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info("[CRON] Jobs registered: retry_failed_documents (15m), extract_user_memories (30m)")
