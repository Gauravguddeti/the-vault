import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://neondb_owner:npg_NjrZC3OHYV7P@ep-blue-smoke-axw4138x-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("--- 1. Latest Document ---")
    doc = await conn.fetchrow("SELECT id, user_id, original_name, status, created_at, raw_text FROM documents ORDER BY created_at DESC LIMIT 1")
    if not doc:
        print("No documents found.")
        return
    
    doc_id = doc['id']
    user_id = doc['user_id']
    print(f"Document ID: {doc_id}")
    print(f"User ID: {user_id}")
    print(f"Name: {doc['original_name']}")
    print(f"Status: {doc['status']}")
    print(f"Created: {doc['created_at']}")
    
    print("\n--- 2. OCR Output (first 500 chars) ---")
    raw_text = doc['raw_text']
    if raw_text:
        print(raw_text[:500])
        print(f"... (total {len(raw_text)} chars)")
    else:
        print("raw_text is EMPTY or NULL")
        
    print("\n--- 3. Chunks & Embeddings ---")
    chunks = await conn.fetch("SELECT chunk_index, token_count FROM chunks WHERE document_id = ", doc_id)
    if chunks:
        print(f"Found {len(chunks)} chunks.")
        for c in chunks:
            print(f"  Chunk {c['chunk_index']}: {c['token_count']} tokens")
    else:
        print("NO chunks found for this document.")

    await conn.close()

asyncio.run(main())
