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
