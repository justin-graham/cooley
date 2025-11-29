# Deployment Guide: Time-Travel Cap Table Feature

## ✅ What's Been Completed

The time-travel cap table feature has been fully implemented and committed to the repository. This major update includes:

### Backend Implementation
- **Transaction Extraction System**: Automatically extracts equity events from documents into a normalized database schema
- **Batch Approval Matching**: Single Claude API call matches transactions with board approvals, identifying compliance gaps
- **3 New API Endpoints**:
  - `GET /api/audits/{id}/events` - Fetch all equity events
  - `GET /api/audits/{id}/captable?as_of_date=YYYY-MM-DD` - Calculate cap table at any point in time
  - `GET /api/audits/{id}/documents/{doc_id}` - Retrieve document details
- **Verifiable Trust System**: Each transaction links to source + approval documents with exact quotes

### Frontend Implementation
- **Interactive Timeline**: Horizontal timeline with clickable nodes for time-travel navigation
- **Split-Panel Dashboard**: Cap table (left) + chronological event stream (right)
- **Shareholder Visualization**: Color-coded shareholders with hover highlighting
- **Compliance Indicators**: Warning icons for transactions missing approvals
- **Company Header**: Stats showing document count, event count, and date range

### Database Schema
- **New Tables**:
  - `documents` - Normalized document storage with classification and full text
  - `equity_events` - Immutable ledger of equity transactions with approval references
- **Migration File**: `migrations/001_add_equity_tables.sql`

## 🚀 Next Steps: Production Deployment

### Step 1: Apply Database Migration on Render

The migration creates two new tables (`documents` and `equity_events`) without affecting existing audits.

**Option A: Via Render Dashboard (Recommended)**
1. Go to your Render dashboard: [https://dashboard.render.com/](https://dashboard.render.com/)
2. Navigate to your PostgreSQL database instance
3. Click "Connect" → "External Connection"
4. Copy the connection string (starts with `postgresql://...`)
5. Run the migration locally:
   ```bash
   psql "<your-render-database-url>" < migrations/001_add_equity_tables.sql
   ```

**Option B: Via Render Shell**
1. Go to your Render web service dashboard
2. Click "Shell" in the top right
3. Run:
   ```bash
   psql $DATABASE_URL < migrations/001_add_equity_tables.sql
   ```

**Verify Migration Success:**
```bash
psql $DATABASE_URL -c "\dt"
```
You should see 3 tables: `audits`, `documents`, `equity_events`

### Step 2: Verify Auto-Deployment

Render automatically deploys when you push to `main`. Check:
1. Go to Render dashboard → Your web service
2. Check "Events" tab for latest deployment
3. Wait for "Deploy succeeded" message
4. Check "Logs" for any errors during startup

If deployment hasn't started automatically:
- Go to "Settings" → "Build & Deploy"
- Click "Manual Deploy" → "Deploy latest commit"

### Step 3: Test the Feature

1. **Upload Test Documents**:
   - Navigate to your deployed app (e.g., `https://your-app.onrender.com`)
   - Upload a .zip file with corporate documents (at least 1 stock purchase agreement + 1 board consent)

2. **Verify Time-Travel Interface**:
   - After processing completes, you should see:
     - Company header with stats
     - Horizontal timeline with clickable date nodes
     - Split-panel layout: Cap table (left) + Event stream (right)
   - Click on different timeline nodes to "time travel" and watch the cap table update

3. **Check Compliance Indicators**:
   - Look for ⚠ warning icons next to shareholders with compliance issues
   - Hover over warnings to see issue details
   - Verify event cards show "VERIFIED", "WARNING", or "CRITICAL" status

### Step 4: Monitor and Debug

**Check Application Logs:**
```bash
# Via Render dashboard
Go to web service → Logs tab

# Look for these success messages:
"Extracted X equity transactions from documents"
"Batch approval matching complete: X matches processed"
"Inserted X equity events into database"
```

**Common Issues:**

1. **Migration Not Applied**:
   - Symptom: `relation "documents" does not exist` in logs
   - Fix: Re-run migration from Step 1

2. **API Errors (404 on /api/audits/...)**:
   - Symptom: Frontend shows "Failed to fetch events"
   - Check: Verify deployment succeeded and latest code is live
   - Fix: Clear browser cache, refresh page

3. **Empty Cap Table Despite Documents**:
   - Symptom: Timeline shows but cap table says "No shareholders"
   - Check logs for: "Extracted 0 equity transactions"
   - Likely cause: No Stock Purchase Agreements or extractable equity documents in upload

## 📊 Feature Architecture

### How It Works

1. **Pass 1: Classification** (unchanged)
   - Classify each document by type

2. **Pass 2: Extraction** (enhanced)
   - Extract structured data from each document
   - **NEW: Pass 2A** - Extract equity transactions into `equity_events` table
   - **NEW: Pass 2B** - Batch approval matching via single Claude call

3. **Pass 3: Synthesis** (unchanged)
   - Generate timeline, cap table, issues

### Database Schema

```
audits (existing)
  └── documents (NEW) ─┐
        └── equity_events (NEW)
              ├── source_doc_id → documents.id
              └── approval_doc_id → documents.id
```

### API Flow

```
User clicks timeline node (e.g., "2023-03-15")
  ↓
Frontend: GET /api/audits/{id}/captable?as_of_date=2023-03-15
  ↓
Backend: Filter equity_events WHERE event_date <= '2023-03-15'
  ↓
Backend: Aggregate by shareholder + share_class (Python code, not AI)
  ↓
Backend: Calculate ownership % and detect compliance issues
  ↓
Frontend: Render updated cap table + highlight changed shareholders
```

## 🔧 Rollback Plan

If you encounter critical issues, you can rollback:

**1. Revert to Previous Commit:**
```bash
git revert HEAD
git push origin main
```

**2. Drop New Tables (OPTIONAL - only if migration causes issues):**
```bash
psql $DATABASE_URL -c "DROP TABLE IF EXISTS equity_events CASCADE;"
psql $DATABASE_URL -c "DROP TABLE IF EXISTS documents CASCADE;"
```

Note: Existing audits in `audits` table are unaffected - the migration is backward compatible.

## 📝 Testing Checklist

- [ ] Migration applied successfully (3 tables exist)
- [ ] Deployment succeeded on Render
- [ ] Application loads without errors
- [ ] Can upload .zip file and start processing
- [ ] Processing completes successfully (status = "complete")
- [ ] Results page shows new split-panel layout
- [ ] Horizontal timeline renders with clickable nodes
- [ ] Cap table updates when clicking different timeline nodes
- [ ] Event stream shows transactions with verification status
- [ ] Compliance warnings (⚠) appear for transactions without approvals
- [ ] Shareholder highlighting works on hover

## 🎯 Success Metrics

After deployment, the platform should demonstrate:
- **Verifiable Trust**: Every equity transaction shows source + approval documents
- **Compliance Detection**: Missing board approvals flagged as "CRITICAL"
- **Time-Travel Capability**: Users can view cap table at any historical date
- **Performance**: Cap table recalculation < 200ms (cached events)

## 📞 Support

If you encounter issues:
1. Check Render logs for error details
2. Verify migration was applied: `psql $DATABASE_URL -c "\dt"`
3. Test with a simple document set (1-2 stock purchase agreements + 1 board consent)
4. Review [.claude/claude.md](/.claude/claude.md) for detailed architecture documentation

---

**Last Updated**: 2025-11-28
**Feature Version**: 1.0 (Initial Implementation)
**Deployment Target**: Render (Web Service + PostgreSQL)
