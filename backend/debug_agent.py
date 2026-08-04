"""
Debug script to simulate exactly what the agent does for a given user.
Prints the document_index string that gets sent to the LLM.
"""
import asyncio
import asyncpg
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def debug_agent_for_user(user_id: str):
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=3)
    async with pool.acquire() as conn:
        print(f"\n=== Simulating load_memory_node for user {user_id[:8]} ===")
        
        # Simulate load_memory_node document fetch
        docs = await conn.fetch("""
            SELECT d.original_name, d.created_at, e.category, e.vendor, e.amount, e.currency, e.raw_json
            FROM documents d
            LEFT JOIN extracted_fields e ON d.id = e.document_id
            WHERE d.status = 'ready' AND d.user_id = $1::uuid
            ORDER BY d.created_at DESC
            LIMIT 20
        """, user_id)
        
        print(f"Documents found: {len(docs)}")
        for d in docs:
            print(f"  - {d['original_name']}")
        
        # Simulate vector search
        print(f"\n=== Simulating chunks count for user {user_id[:8]} ===")
        chunks_count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunks WHERE user_id = $1::uuid",
            user_id
        )
        print(f"Chunks owned: {chunks_count}")
        
        # Cross-check: what would a non-filtered query return?
        all_docs = await conn.fetch("SELECT original_name, user_id FROM documents WHERE status = 'ready' LIMIT 20")
        print(f"\n=== ALL documents in DB (no filter) ===")
        for d in all_docs:
            print(f"  - {d['original_name']} (user: {str(d['user_id'])[:8]})")

async def main():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=1)
    async with pool.acquire() as conn:
        users = await conn.fetch('SELECT DISTINCT user_id FROM documents')
    await pool.close()
    
    for u in users:
        pool2 = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=3)
        async with pool2.acquire() as conn:
            uid = str(u['user_id'])
            docs = await conn.fetch("""
                SELECT d.original_name, d.created_at
                FROM documents d
                WHERE d.status = 'ready' AND d.user_id = $1::uuid
                ORDER BY d.created_at DESC
            """, uid)
            print(f"\nUser {uid[:8]}: sees {len(docs)} document(s): {[d['original_name'] for d in docs]}")
        await pool2.close()

asyncio.run(main())
