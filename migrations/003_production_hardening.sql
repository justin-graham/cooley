-- Migration 003: Production hardening baseline
-- Run with: psql $DATABASE_URL < migrations/003_production_hardening.sql

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- AUDITS TABLE: explicit pipeline states + quality gating
-- ============================================================================

ALTER TABLE audits
    ADD COLUMN IF NOT EXISTS pipeline_state TEXT,
    ADD COLUMN IF NOT EXISTS quality_report JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS review_required BOOLEAN DEFAULT FALSE;

-- Backfill pipeline_state for existing rows
UPDATE audits
SET pipeline_state = COALESCE(pipeline_state, status, 'queued');

-- Normalize legacy statuses before enforcing new check
UPDATE audits SET status = 'parsing' WHERE status = 'processing';
UPDATE audits
SET status = 'queued'
WHERE status NOT IN ('queued', 'parsing', 'classifying', 'extracting', 'reconciling', 'needs_review', 'complete', 'error');

UPDATE audits
SET pipeline_state = 'queued'
WHERE pipeline_state NOT IN ('queued', 'parsing', 'classifying', 'extracting', 'reconciling', 'needs_review', 'complete', 'error');

ALTER TABLE audits DROP CONSTRAINT IF EXISTS audits_status_check;
ALTER TABLE audits ADD CONSTRAINT audits_status_check CHECK (
    status IN ('queued', 'parsing', 'classifying', 'extracting', 'reconciling', 'needs_review', 'complete', 'error')
);

ALTER TABLE audits DROP CONSTRAINT IF EXISTS audits_pipeline_state_check;
ALTER TABLE audits ADD CONSTRAINT audits_pipeline_state_check CHECK (
    pipeline_state IN ('queued', 'parsing', 'classifying', 'extracting', 'reconciling', 'needs_review', 'complete', 'error')
);

CREATE INDEX IF NOT EXISTS idx_audits_pipeline_state ON audits(pipeline_state);
CREATE INDEX IF NOT EXISTS idx_audits_review_required ON audits(review_required);

-- ============================================================================
-- DOCUMENTS TABLE: parser status fields
-- ============================================================================

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS parse_status TEXT DEFAULT 'success',
    ADD COLUMN IF NOT EXISTS parse_error TEXT;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_parse_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_parse_status_check CHECK (
    parse_status IN ('success', 'partial', 'error', 'skipped')
);

-- ============================================================================
-- EQUITY EVENTS TABLE: preview + summary fields used in app/db.py
-- ============================================================================

ALTER TABLE equity_events
    ADD COLUMN IF NOT EXISTS preview_image TEXT,
    ADD COLUMN IF NOT EXISTS summary TEXT;

-- ============================================================================
-- SESSIONS TABLE: durable auth sessions
-- ============================================================================

CREATE TABLE IF NOT EXISTS sessions (
    session_token TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
