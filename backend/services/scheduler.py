"""
APScheduler cron job for retrying failed/stuck document processing.
Implemented fully in Task 4.7 — this is the startup/shutdown wrapper.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

_scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    """Start the scheduler (called on app startup)."""
    # Jobs registered in Task 4.7
    if not _scheduler.running:
        _scheduler.start()


def stop_scheduler() -> None:
    """Gracefully stop the scheduler (called on app shutdown)."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


def get_scheduler() -> AsyncIOScheduler:
    return _scheduler
