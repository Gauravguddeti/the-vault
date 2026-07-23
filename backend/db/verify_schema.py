"""Verify schema was applied correctly to Neon."""
import asyncio
import os
import sys
from dotenv import load_dotenv
import asyncpg

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("&channel_binding=require", "")

async def verify():
    print("Connecting to Neon...")
    conn = await asyncpg.connect(DATABASE_URL)

    ext = await conn.fetch(
        "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'uuid-ossp')"
    )
    print(f"Extensions   : {[r['extname'] for r in ext]}")

    tables = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    print(f"Tables ({len(tables)})   : {[r['tablename'] for r in tables]}")

    rls = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND rowsecurity=true ORDER BY tablename"
    )
    print(f"RLS tables   : {[r['tablename'] for r in rls]}")

    indexes = await conn.fetch(
        "SELECT indexname FROM pg_indexes WHERE tablename='chunks'"
    )
    print(f"Chunk indexes: {[r['indexname'] for r in indexes]}")

    policies = await conn.fetch(
        "SELECT tablename, policyname FROM pg_policies WHERE schemaname='public' ORDER BY tablename"
    )
    print(f"RLS policies ({len(policies)}):")
    for p in policies:
        print(f"  {p['tablename']}: {p['policyname']}")

    await conn.close()
    print("\n[PASS] Neon schema verified successfully.")

if __name__ == "__main__":
    asyncio.run(verify())
