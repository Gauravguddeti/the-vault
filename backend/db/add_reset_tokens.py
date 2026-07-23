"""Add password_reset_tokens table to Neon."""
import asyncio, os
from dotenv import load_dotenv
import asyncpg

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "").replace("&channel_binding=require", "")

SQL = """
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT NOT NULL,
    otp_hash    TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    used        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_prt_email ON password_reset_tokens(email);
"""

async def run():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(SQL)
    print("[OK] password_reset_tokens table created.")
    rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    print("Tables:", [r["tablename"] for r in rows])
    await conn.close()

asyncio.run(run())
