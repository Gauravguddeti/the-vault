import asyncio
import asyncpg
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def check():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=1)
    async with pool.acquire() as conn:
        # Get all users and their docs
        users = await conn.fetch('SELECT DISTINCT user_id FROM documents')
        for u in users:
            uid = str(u['user_id'])
            docs = await conn.fetch(
                "SELECT original_name FROM documents WHERE user_id = $1::uuid AND status = 'ready'",
                uid
            )
            print(f'User {uid[:8]}: {[d["original_name"] for d in docs]}')
        
        # Test load_memory_node query WITH user_id filter for each user
        for u in users:
            test_user = str(u['user_id'])
            print(f'\nTesting load_memory_node for user {test_user[:8]}...')
            docs = await conn.fetch("""
                SELECT d.original_name, d.created_at
                FROM documents d
                LEFT JOIN extracted_fields e ON d.id = e.document_id
                WHERE d.status = 'ready' AND d.user_id = $1::uuid
                ORDER BY d.created_at DESC
                LIMIT 20
            """, test_user)
            print(f'  -> Returns: {[d["original_name"] for d in docs]}')
        
        # Check chunks
        all_chunk_users = await conn.fetch('SELECT DISTINCT user_id, COUNT(*) as c FROM chunks GROUP BY user_id')
        print(f'\nChunks by user:')
        for r in all_chunk_users:
            print(f'  User {str(r["user_id"])[:8]}: {r["c"]} chunks')

asyncio.run(check())
