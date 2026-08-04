-- Add 'thinking' column to conversation_messages
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS thinking TEXT;
