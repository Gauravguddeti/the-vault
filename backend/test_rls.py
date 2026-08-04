import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def test():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=1)
    
    async with pool.acquire() as conn:
        print("--- Outside transaction ---")
        await conn.execute("SELECT set_config('app.current_user_id', '11111111-1111-1111-1111-111111111111', true)")
        val1 = await conn.fetchval("SELECT current_setting('app.current_user_id', true)")
        print('Val 1 (outside txn):', val1)
        
    async with pool.acquire() as conn2:
        val2 = await conn2.fetchval("SELECT current_setting('app.current_user_id', true)")
        print('Val 2 (new acquire, same conn):', val2)
        
    async with pool.acquire() as conn3:
        print("--- Inside transaction ---")
        async with conn3.transaction():
            await conn3.execute("SELECT set_config('app.current_user_id', '22222222-2222-2222-2222-222222222222', true)")
            val3 = await conn3.fetchval("SELECT current_setting('app.current_user_id', true)")
            print('Val 3 (inside txn):', val3)
            
    async with pool.acquire() as conn4:
        val4 = await conn4.fetchval("SELECT current_setting('app.current_user_id', true)")
        print('Val 4 (new acquire, same conn):', val4)

asyncio.run(test())
