-- ══════════════════════════════════════════════════════════════════════
--  The Vault — Migration: unconfirmed_fields table
--  Part 2 (Confidence-Gated Confirmation Loop) + Part 5 (OCR Confidence)
--
--  Apply with: psql $DATABASE_URL -f migration_unconfirmed_fields.sql
-- ══════════════════════════════════════════════════════════════════════

-- ── unconfirmed_fields ────────────────────────────────────────────────
-- Stores per-field OCR extractions that had low confidence (< 0.7).
-- Before the assistant answers any question that depends on a pending field,
-- it asks the user to confirm or correct it first.
--
-- Status lifecycle:
--   pending   → user hasn't confirmed yet
--   confirmed → user said "yes" / accepted the auto-corrected value
--   corrected → user provided a different correct value
CREATE TABLE IF NOT EXISTS unconfirmed_fields (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id          UUID NOT NULL,
    field_name       TEXT NOT NULL,         -- e.g. 'vendor', 'amount', 'item[0].name'
    raw_value        TEXT NOT NULL,         -- original OCR text (always preserved)
    corrected_value  TEXT,                  -- auto-corrected (from RxNorm etc.) or null
    confirmed_value  TEXT,                  -- final trusted value after user says yes/corrects
    confidence       FLOAT NOT NULL,        -- 0.0-1.0 from extractor
    status           TEXT NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'confirmed', 'corrected')),
    item_index       INT,                   -- for item-level fields (e.g. medication names)
    possibly_cancelled BOOLEAN DEFAULT FALSE, -- detected visual strikethrough
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE unconfirmed_fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE unconfirmed_fields FORCE ROW LEVEL SECURITY;

CREATE POLICY unconfirmed_fields_isolation ON unconfirmed_fields
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

CREATE INDEX IF NOT EXISTS idx_unconfirmed_document_id ON unconfirmed_fields(document_id);
CREATE INDEX IF NOT EXISTS idx_unconfirmed_user_status ON unconfirmed_fields(user_id, status);

-- ── conversation_sessions: add confirmation_pending column ────────────
-- Stores a JSON blob of the question that's waiting for field confirmation,
-- so the agent can resume answering it after the user confirms.
ALTER TABLE conversation_sessions
    ADD COLUMN IF NOT EXISTS confirmation_pending JSONB DEFAULT NULL;

-- ══════════════════════════════════════════════════════════════════════
--  Verification:
--  SELECT tablename FROM pg_tables WHERE tablename='unconfirmed_fields';
--  SELECT column_name FROM information_schema.columns
--    WHERE table_name='conversation_sessions' AND column_name='confirmation_pending';
-- ══════════════════════════════════════════════════════════════════════
