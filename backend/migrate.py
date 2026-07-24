import asyncio
import asyncpg

DATABASE_URL = "postgresql://neondb_owner:npg_NjrZC3OHYV7P@ep-blue-smoke-axw4138x-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("Dropping existing constraint...")
    await conn.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_status_check")
    
    print("Adding new constraint...")
    await conn.execute("ALTER TABLE documents ADD CONSTRAINT documents_status_check CHECK (status IN ('pending', 'ocr_processing', 'awaiting_confirmation', 'embedding', 'ready', 'failed'))")
    
    print("Done!")
    await conn.close()

asyncio.run(main())
