"""
Database connection pool using asyncpg.

CRITICAL SECURITY NOTE:
  RLS user context is set per-request via SET LOCAL inside a transaction.
  SET LOCAL is ONLY effective inside a transaction — outside a transaction it
  is a no-op. This means get_db_with_rls MUST wrap every connection in an
  explicit transaction so:
    1. SET LOCAL app.current_user_id = '...' is scoped to that transaction
    2. On COMMIT the variable is reset, so no leakage to the next pool reuse
    3. The connection is returned to the pool in a clean state

  Without this transaction wrap, a SET LOCAL on a pooled connection would be
  reset on the next transaction boundary — meaning it might not be set at all
  if there's no transaction, producing a NULL current_user_id and serving
  every user's data or no data at all.
"""
import asyncpg
import logging
from typing import AsyncGenerator
from core.config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Initialize the connection pool on startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def get_pool() -> asyncpg.Pool:
    """Return the global pool (raises if not initialized)."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db() first.")
    return _pool


async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """
    FastAPI dependency that yields a single connection.
    RLS setting must be applied separately via get_db_with_rls.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def set_rls_user(conn: asyncpg.Connection, user_id: str) -> None:
    """
    Set the Postgres session variable for Row-Level Security.

    MUST be called inside an active transaction — SET LOCAL is transaction-scoped.
    If called outside a transaction, it silently has no effect (and the next
    query will run with whatever user_id was left from the previous request
    on this pooled connection, which is a cross-account data leak).

    This is enforced by get_db_with_rls which always wraps in a transaction.
    """
    if not user_id:
        raise ValueError("user_id must be non-empty before setting RLS context")

    # Sanitize: user_id is a UUID, only allow UUID characters
    import re
    if not re.match(r'^[0-9a-f-]{36}$', user_id.lower()):
        raise ValueError(f"Invalid user_id format: {user_id!r}")

    await conn.execute(
        "SELECT set_config('app.current_user_id', $1, true)",  # true = LOCAL (transaction-scoped)
        user_id,
    )
    logger.debug("[RLS] Set app.current_user_id = %s", user_id)
