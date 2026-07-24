"""
Database connection pool using asyncpg.
RLS user context is set on every connection via the middleware.
"""
import asyncpg
from typing import AsyncGenerator
from core.config import settings

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
    RLS setting is applied BEFORE yielding to the route handler.
    user_id must be set via set_rls_user() separately per request.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def set_rls_user(conn: asyncpg.Connection, user_id: str) -> None:
    """
    Set the Postgres session variable for Row-Level Security.
    Must be called on every connection before any data query.
    """
    await conn.execute(
        f"SET LOCAL app.current_user_id = '{user_id}'"
    )
