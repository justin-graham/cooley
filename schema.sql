-- Corporate Governance Audit Platform Database Schema

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Main audits table
CREATE TABLE IF NOT EXISTS audits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP DEFAULT NOW(),
    status TEXT NOT NULL CHECK (status IN ('processing', 'complete', 'error')),
    progress TEXT,  -- Current processing step for real-time updates

    -- Final results (stored as JSONB for flexibility)
    company_name TEXT,
    documents JSONB,  -- Array of {filename, type, category, text, summary, error}
    timeline JSONB,   -- Array of {date, event_type, description, source_docs}
    cap_table JSONB,  -- Array of {shareholder, shares, share_class, ownership_pct}
    issues JSONB,     -- Array of {severity, category, description}

    -- Error tracking
    error_message TEXT,
    failed_documents JSONB  -- Array of {filename, error}
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_audits_status ON audits(status);
CREATE INDEX IF NOT EXISTS idx_audits_created_at ON audits(created_at DESC);

-- Optional: Add a comment to document the table
COMMENT ON TABLE audits IS 'Stores corporate governance audit results with AI-extracted structured data';


-- ============================================================================
-- DOCUMENTS TABLE (for cap table tie-out feature)
-- ============================================================================

-- Individual document records with parsed text and classification
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    audit_id UUID NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    classification TEXT,  -- Document type (e.g., 'Stock Purchase Agreement')
    extracted_data JSONB,  -- Structured data from Pass 2 extraction
    full_text TEXT,  -- Complete parsed document text
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_documents_audit_id ON documents(audit_id);

COMMENT ON TABLE documents IS 'Individual documents with parsed text and AI classification';


-- ============================================================================
-- EQUITY EVENTS TABLE (for time-travel cap table)
-- ============================================================================

-- Transaction-level equity events with approval matching
CREATE TABLE IF NOT EXISTS equity_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    audit_id UUID NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    event_date DATE NOT NULL,  -- Transaction date
    event_type TEXT NOT NULL,  -- 'issuance', 'safe', 'option_grant', 'repurchase', 'formation'
    shareholder_name TEXT,  -- Person/entity involved (null for formation events)
    share_class TEXT,  -- 'Common Stock', 'Series A Preferred', 'SAFE', 'Option', etc.
    share_delta NUMERIC NOT NULL,  -- Positive for issuances, negative for repurchases

    -- Source document reference
    source_doc_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    source_snippet TEXT,  -- Quote from source document

    -- Approval matching
    approval_doc_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    approval_snippet TEXT,  -- Quote from approval document
    compliance_status TEXT NOT NULL DEFAULT 'VERIFIED',  -- 'VERIFIED', 'WARNING', 'CRITICAL'
    compliance_note TEXT,  -- Explanation of compliance status

    -- Additional metadata
    details JSONB,  -- Extra fields (price_per_share, valuation_cap, etc.)
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_equity_events_audit_id ON equity_events(audit_id);
CREATE INDEX IF NOT EXISTS idx_equity_events_date ON equity_events(event_date);
CREATE INDEX IF NOT EXISTS idx_equity_events_audit_date ON equity_events(audit_id, event_date);

COMMENT ON TABLE equity_events IS 'Transaction-level equity events with approval matching for time-travel cap table';
