"""
Apply schema.sql to Neon database.
Run: python db/apply_schema.py
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def apply_schema():
    print(f"Connecting to Neon...")
    # asyncpg doesn't support channel_binding param — strip it
    url = DATABASE_URL.replace("&channel_binding=require", "").replace("?channel_binding=require", "")

    conn = await asyncpg.connect(url)
    try:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        print("Applying schema...")
        await conn.execute(schema_sql)
        print("[OK] Schema applied successfully!\n")

        # Verification queries
        print("── Verification ─────────────────────────────────")

        extensions = await conn.fetch("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'uuid-ossp')")
        print(f"Extensions: {[r['extname'] for r in extensions]}")

        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        print(f"Tables ({len(tables)}): {[r['tablename'] for r in tables]}")

        rls_tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND rowsecurity=true ORDER BY tablename"
        )
        print(f"RLS-enabled tables ({len(rls_tables)}): {[r['tablename'] for r in rls_tables]}")

        indexes = await conn.fetch(
            "SELECT indexname FROM pg_indexes WHERE tablename='chunks'"
        )
        print(f"Indexes on chunks: {[r['indexname'] for r in indexes]}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(apply_schema())
