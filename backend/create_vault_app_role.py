"""
Create a low-privilege 'vault_app' role for FastAPI to connect with.
This role does NOT have BYPASSRLS, so RLS policies are fully enforced.

Run this once against your Neon DB as the superuser/owner.
"""
import asyncio
import asyncpg
from core.config import settings


VAULT_APP_PASSWORD = "CHANGE_THIS_IN_PRODUCTION"

SQL = """
-- Create a low-privilege application role (no BYPASSRLS)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vault_app') THEN
    CREATE ROLE vault_app LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO vault_app;

-- Grant table-level permissions (SELECT, INSERT, UPDATE, DELETE)
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  users, documents, chunks, extracted_fields,
  conversation_sessions, conversation_messages,
  processing_logs, audit_logs
TO vault_app;

-- Grant sequence usage (for uuid generation functions if needed)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO vault_app;

-- Grant execute on functions
GRANT EXECUTE ON FUNCTION uuid_generate_v4() TO vault_app;
GRANT EXECUTE ON FUNCTION trigger_set_updated_at() TO vault_app;
"""


async def main():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    sql = SQL.replace('{password}', VAULT_APP_PASSWORD)
    await conn.execute(sql)
    print("vault_app role created and permissions granted.")
    print(
        "\nNEXT STEP: Update DATABASE_URL in your environment to connect as vault_app, not neondb_owner.\n"
        "This ensures RLS is fully enforced in production."
    )
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
