import asyncio
import asyncpg
from core.config import settings

async def main():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    result = await conn.fetchval('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user;')
    print("BYPASS RLS:", result)
    await conn.close()

asyncio.run(main())
