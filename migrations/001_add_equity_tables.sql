-- Migration: Add documents and equity_events tables for cap table tie-out feature
-- This migration is ADDITIVE - it does not break existing audits table
-- Existing audits continue to work with JSONB fields (backward compatible)

-- Enable UUID extension (idempotent)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Documents table: Stores metadata for each document in an audit
-- Replaces storing all docs in audits.documents JSONB for better querying
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    audit_id UUID NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    classification TEXT,  -- Document type (e.g., 'Stock Purchase Agreement', 'Board Consent')
    extracted_data JSONB,  -- Type-specific structured data from Pass 2
    full_text TEXT,  -- Parsed document text for AI quote extraction
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_documents_audit ON documents(audit_id);
CREATE INDEX IF NOT EXISTS idx_documents_classification ON documents(classification);

COMMENT ON TABLE documents IS 'Normalized document metadata for equity event tracking and verification';

-- Equity events table: Event ledger for time-travel cap table
-- Each row represents an atomic equity transaction (issuance, repurchase, grant)
CREATE TABLE IF NOT EXISTS equity_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    audit_id UUID NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    event_date DATE NOT NULL,  -- Date of transaction (key field for time-travel)
    event_type TEXT NOT NULL CHECK (event_type IN (
        'formation',
        'issuance',
        'repurchase',
        'option_grant',
        'safe',
        'convertible_note'
    )),

    -- Transaction details
    shareholder_name TEXT,  -- Denormalized for efficient GROUP BY
    share_class TEXT,  -- 'Common', 'Preferred', 'Option'
    share_delta NUMERIC NOT NULL,  -- Positive for grants/issuances, negative for repurchases

    -- Lean AI Bill of Materials (verifiable trust system)
    source_doc_id UUID REFERENCES documents(id),  -- Executing document (e.g., Stock Purchase Agreement)
    source_snippet TEXT,  -- Key quote from source document proving transaction
    approval_doc_id UUID REFERENCES documents(id),  -- Approving document (e.g., Board Consent)
    approval_snippet TEXT,  -- Key quote from approval document

    -- Compliance status
    compliance_status TEXT DEFAULT 'VERIFIED' CHECK (compliance_status IN ('VERIFIED', 'WARNING', 'CRITICAL')),
    compliance_note TEXT,  -- Human-readable explanation (e.g., "No board approval found")

    -- Flexible metadata field
    details JSONB,  -- Event-specific data (e.g., {price_per_share: 0.01, valuation_cap: 10000000})

    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for time-travel queries and aggregation
CREATE INDEX IF NOT EXISTS idx_equity_events_audit ON equity_events(audit_id);
CREATE INDEX IF NOT EXISTS idx_equity_events_date ON equity_events(event_date);
CREATE INDEX IF NOT EXISTS idx_equity_events_shareholder ON equity_events(shareholder_name);
CREATE INDEX IF NOT EXISTS idx_equity_events_type ON equity_events(event_type);
CREATE INDEX IF NOT EXISTS idx_equity_events_compliance ON equity_events(compliance_status);

COMMENT ON TABLE equity_events IS 'Immutable ledger of equity transactions for time-travel cap table and verifiable trust';

-- Migration complete
-- To apply: psql $DATABASE_URL < migrations/001_add_equity_tables.sql
