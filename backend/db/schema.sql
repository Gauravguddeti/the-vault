-- ══════════════════════════════════════════════════════════════════════
--  The Vault — Full Database Schema
--  Apply with: psql $DATABASE_URL -f schema.sql
--  Requires: Neon Postgres with pgvector extension
-- ══════════════════════════════════════════════════════════════════════

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Users ─────────────────────────────────────────────────────────────
-- Managed primarily by NextAuth adapter; bcrypt hash stored here.
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT,
    name            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- NextAuth required tables (used by @auth/pg-adapter)
CREATE TABLE IF NOT EXISTS accounts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type                TEXT NOT NULL,
    provider            TEXT NOT NULL,
    provider_account_id TEXT NOT NULL,
    refresh_token       TEXT,
    access_token        TEXT,
    expires_at          BIGINT,
    token_type          TEXT,
    scope               TEXT,
    id_token            TEXT,
    session_state       TEXT,
    UNIQUE(provider, provider_account_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_token TEXT UNIQUE NOT NULL,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires       TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_tokens (
    identifier TEXT NOT NULL,
    token      TEXT NOT NULL,
    expires    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (identifier, token)
);

-- ── Documents ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,         -- stored filename (UUID-prefixed)
    original_name TEXT NOT NULL,         -- original upload filename
    file_path     TEXT NOT NULL,         -- absolute path on disk
    mime_type     TEXT,
    file_size     BIGINT,
    status        TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','ocr_processing','embedding','ready','failed')),
    raw_text      TEXT,                  -- full OCR output
    retry_count   INT NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY docs_user_isolation ON documents
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);

-- ── Chunks + Vector Embeddings ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL,          -- denormalized for RLS efficiency
    chunk_index  INT NOT NULL,
    text         TEXT NOT NULL,
    token_count  INT,
    embedding    vector(768),            -- matches nomic-embed-text; change to 1536 for OpenAI
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY chunks_user_isolation ON chunks
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

CREATE INDEX IF NOT EXISTS idx_chunks_user_id ON chunks(user_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);

-- IVFFlat index for approximate nearest-neighbour search
-- lists=100 is a good starting point; tune based on dataset size
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ── Extracted Structured Fields ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS extracted_fields (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL,          -- denormalized for RLS
    amount       NUMERIC(15, 4),         -- stored as number, not string, for SQL aggregation
    currency     TEXT,
    txn_date     DATE,
    vendor       TEXT,
    category     TEXT,
    raw_json     JSONB,                  -- full LLM extraction output for debugging
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE extracted_fields ENABLE ROW LEVEL SECURITY;

CREATE POLICY fields_user_isolation ON extracted_fields
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_user_id ON extracted_fields(user_id);
CREATE INDEX IF NOT EXISTS idx_extracted_fields_document_id ON extracted_fields(document_id);
CREATE INDEX IF NOT EXISTS idx_extracted_fields_category ON extracted_fields(user_id, category);
CREATE INDEX IF NOT EXISTS idx_extracted_fields_date ON extracted_fields(user_id, txn_date);

-- ── Processing Logs ───────────────────────────────────────────────────
-- No RLS — admin/cron visibility across all users (no user data stored)
CREATE TABLE IF NOT EXISTS processing_logs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    event       TEXT NOT NULL,   -- e.g. 'ocr_start', 'ocr_success', 'ocr_failed', 'retry'
    detail      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processing_logs_document_id ON processing_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_logs_created_at ON processing_logs(created_at);

-- ── Conversation Sessions ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT,           -- auto-generated from first user message
    summary       TEXT,           -- compressed summary of old messages (> 7 days)
    message_count INT NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE conversation_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY sessions_user_isolation ON conversation_sessions
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

CREATE INDEX IF NOT EXISTS idx_conv_sessions_user_id ON conversation_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_sessions_updated_at ON conversation_sessions(user_id, updated_at DESC);

-- ── Conversation Messages ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_messages (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  UUID NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL,           -- denormalized for RLS
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    sources     JSONB,                   -- [{document_name, chunk_index, similarity_score}]
    query_type  TEXT CHECK (query_type IN ('lookup', 'aggregation', 'chitchat', NULL)),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY messages_user_isolation ON conversation_messages
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

CREATE INDEX IF NOT EXISTS idx_conv_messages_session_id ON conversation_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_messages_user_id ON conversation_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_messages_created_at ON conversation_messages(session_id, created_at ASC);

-- ── Helper: auto-update updated_at ───────────────────────────────────
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER set_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE OR REPLACE TRIGGER set_conv_sessions_updated_at
    BEFORE UPDATE ON conversation_sessions
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ══════════════════════════════════════════════════════════════════════
--  Verification queries (run manually after applying schema):
--
--  SELECT extname FROM pg_extension;                    -- should include 'vector'
--  SELECT tablename FROM pg_tables WHERE schemaname='public';  -- all 9 tables
--  SELECT tablename, rowsecurity FROM pg_tables
--    WHERE schemaname='public' AND rowsecurity=true;    -- 5 RLS tables
--  SELECT indexname FROM pg_indexes WHERE tablename='chunks'; -- includes ivfflat
-- ══════════════════════════════════════════════════════════════════════
