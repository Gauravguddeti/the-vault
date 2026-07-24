import asyncio
import asyncpg
from core.config import settings

async def main():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    tables = [
        "documents", "chunks", "extracted_fields", 
        "conversation_sessions", "conversation_messages", "audit_logs"
    ]
    for table in tables:
        print(f"Forcing RLS on {table}...")
        await conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    print("Done!")
    await conn.close()

asyncio.run(main())
