import asyncio
import asyncpg
from core.config import settings

async def main():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    
    print("Creating audit_logs table...")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
            action      TEXT NOT NULL,
            resource_id UUID,
            details     TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

        DROP POLICY IF EXISTS audit_logs_user_isolation ON audit_logs;
        CREATE POLICY audit_logs_user_isolation ON audit_logs
            USING (user_id = current_setting('app.current_user_id', true)::uuid);

        CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
    """)
    print("Done!")
    await conn.close()

asyncio.run(main())
