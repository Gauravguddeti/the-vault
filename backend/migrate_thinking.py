import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def main():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not found in environment.")
        return

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("""
            ALTER TABLE conversation_messages 
            ADD COLUMN IF NOT EXISTS thinking TEXT;
        """)
        print("Successfully added 'thinking' column to 'conversation_messages'.")
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
