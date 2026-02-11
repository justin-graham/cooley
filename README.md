# Corporate Governance Audit Platform

AI-powered platform that automates corporate legal document audits. Upload a .zip of 100-1,000+ documents and receive a structured audit in minutes instead of 40+ hours of manual review.

## Features

- 📄 **Document Classification**: Automatically categorizes Charter, Board Minutes, Stock Agreements, SAFEs, etc.
- 📅 **Timeline Generation**: Chronological timeline of formations, financings, stock issuances, board changes
- 📊 **Cap Table Draft**: Auto-generated capitalization table with ownership percentages
- ⚠️ **Issue Tracker**: Identifies missing documents, inconsistencies, and compliance issues
- 🎨 **Swiss Design UI**: Clean, minimal interface with precision typography and red accent

## Tech Stack

- **Backend**: FastAPI + Postgres
- **AI**: Claude 3.5 Sonnet (Anthropic)
- **Frontend**: Vanilla HTML/CSS/JavaScript (zero dependencies)
- **Deployment**: Render

## Quick Start

1. **Clone and install dependencies**:
   ```bash
   git clone <repo-url>
   cd corporate-audit-mvp
   pip install -r requirements.txt
   ```

2. **Set up environment**:
   ```bash
   cp .env.example .env.local
   # Edit .env.local with your ANTHROPIC_API_KEY and DATABASE_URL
   ```

3. **Initialize database**:
   ```bash
   psql $DATABASE_URL < schema.sql
   ```

4. **Run locally**:
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Open browser**: http://localhost:8000

## Deploy to Render

1. Push to GitHub
2. Create new Web Service on Render
3. Connect GitHub repo
4. Add Postgres database (one-click add-on)
5. Set environment variables: `ANTHROPIC_API_KEY`, `DATABASE_URL`, `ALLOWED_ORIGINS`
6. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
7. Run migration: `psql $DATABASE_URL < schema.sql`

## Supported Document Types

- PDF (.pdf)
- Word (.docx)
- Excel (.xlsx)
- PowerPoint (.pptx)

**Max upload size**: 50MB (zip file)

## Architecture

```
User uploads .zip
    ↓
FastAPI backend extracts & parses documents
    ↓
3-Pass AI Pipeline:
  1. Classify each document type
  2. Extract structured data per type
  3. Synthesize timeline, cap table, issues
    ↓
Results stored in Postgres
    ↓
Frontend polls status & displays results
```

## Output Quality Gates

- `status` now includes explicit pipeline states: `queued`, `parsing`, `classifying`, `extracting`, `reconciling`, `needs_review`, `complete`, `error`
- every `/status/{audit_id}` response includes:
  - `quality_report`: structured extraction/reconciliation quality diagnostics
  - `review_required`: fail-closed legal gate when confidence/evidence is insufficient

## License

MIT
