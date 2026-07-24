import asyncio
import asyncpg

DATABASE_URL = "postgresql://neondb_owner:npg_NjrZC3OHYV7P@ep-blue-smoke-axw4138x-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("--- 3. Chunks & Embeddings ---")
    # use a hardcoded string or proper $1 since no ps interpolation here
    doc = await conn.fetchrow("SELECT id FROM documents ORDER BY created_at DESC LIMIT 1")
    doc_id = doc['id']
    chunks = await conn.fetch("SELECT chunk_index, token_count FROM chunks WHERE document_id = $1", doc_id)
    if chunks:
        print(f"Found {len(chunks)} chunks.")
        for c in chunks:
            print(f"  Chunk {c['chunk_index']}: {c['token_count']} tokens")
    else:
        print("NO chunks found for this document.")

    await conn.close()

asyncio.run(main())
