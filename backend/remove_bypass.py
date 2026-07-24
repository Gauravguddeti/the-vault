import asyncio
import asyncpg
from core.config import settings

async def main():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        user = await conn.fetchval('SELECT current_user;')
        await conn.execute(f'ALTER ROLE "{user}" NOBYPASSRLS;')
        print(f"Removed BYPASSRLS from {user}")
    except Exception as e:
        print("Failed:", e)
    await conn.close()

asyncio.run(main())
