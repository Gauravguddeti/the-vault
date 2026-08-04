import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def run_migration():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("DATABASE_URL not found in .env")
        return
    
    print("Connecting to database...")
    conn = await asyncpg.connect(database_url)
    
    try:
        with open('db/migration_unconfirmed_fields.sql', 'r', encoding='utf-8') as f:
            sql = f.read()
        
        print("Executing migration script...")
        await conn.execute(sql)
        print("Migration applied successfully.")
    except Exception as e:
        print(f"Error applying migration: {e}")
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(run_migration())
