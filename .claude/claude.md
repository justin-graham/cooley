# Tieout: Corporate Governance Auditing Platform
## Claude Code Context & Development Guidelines

---

## MISSION STATEMENT

**Replace 40+ hours of manual legal review with structured, explainable AI.**

Tieout automates corporate intake audits for law firms and corporate legal teams by extracting, classifying, and reconciling governance data from large, unstructured document sets. The platform transforms chaotic document folders into auditable, exportable corporate histories.

### Core Problem
During corporate transactions (Series A financing, M&A due diligence, legal intake), associates spend 40+ hours manually reviewing 100-1,000+ documents to:
- Build cap tables from scratch
- Verify amendment approvals (did the company get the required % of investor signatures?)
- Track securities law compliance (registration exemption limits, trailing averages)
- Reconcile stock issuances with board approvals and employee agreements
- Identify missing or inconsistent documentation

### Core Solution
AI-powered 3-pass pipeline that:
1. **Classifies** documents by type (charter, board consent, SAFE, stock purchase, etc.)
2. **Extracts** structured data with verification (shareholders, shares, dates, valuations)
3. **Synthesizes** cross-document intelligence (timeline, cap table, compliance issues)

### MVP Input/Output

**Input:**
- Zip file or Google Drive folder
- 100-1,000+ corporate documents (PDF, DOCX, XLSX, PPTX)
- Unstructured, chronologically messy, potentially incomplete

**Output:**
- Classified document set (28 categories)
- Extracted event timeline (formations, issuances, board changes, financings)
- Auto-generated cap table with ownership percentages
- Issue tracker (missing docs, inconsistencies, compliance gaps)
- Structured Cooley-format data-room folder export (future)

---

## PRODUCT VISION

### Short-term (MVP)
Single-user corporate audit tool for law firm associates and corporate counsel. Upload documents, get structured output in minutes instead of days.

### Long-term (Legal Intake OS)
Unified platform that automatically organizes, validates, and visualizes a company's entire corporate history. Think: **Carta + Ironclad + Palantir Foundry for corporate governance**.

**Target users:** Law firms, investors (due diligence), CFOs (corporate secretary duties)

**Key differentiators:**
- Explainable AI (source verification, confidence scoring)
- Programmatic synthesis where deterministic logic beats AI
- Export-ready formats (Carta import, Cooley data room, JSON API)
- Compliance-first issue detection

---

## TECHNICAL ARCHITECTURE

### Tech Stack

**Backend:**
- FastAPI (web framework)
- PostgreSQL with psycopg2 (structured + JSONB storage)
- Anthropic Claude 3.5 Sonnet (`claude-sonnet-4-5-20250929`)
- Document parsing: `pymupdf4llm`, `python-docx`, `openpyxl`, `python-pptx`

**Frontend:**
- Vanilla HTML/CSS/JavaScript (zero dependencies)
- Space Grotesk (grotesk) + SF Mono (monospace)
- Single accent: `#D42B1E` (red)

**Infrastructure:**
- Deployment: Render
- File upload limit: 50MB
- No authentication (MVP scope)
- Single processing queue (no concurrency)

### Project Structure

```
corporate-audit-mvp/
├── .claude/
│   ├── settings.local.json     # Claude Code permissions
│   └── claude.md               # This file - project context
├── app/
│   ├── main.py                 # FastAPI routes, orchestration
│   ├── db.py                   # PostgreSQL CRUD operations
│   ├── processing.py           # 3-pass AI pipeline (850+ lines)
│   ├── prompts.py              # Claude prompt templates
│   └── utils.py                # Document parsing utilities
├── static/
│   ├── index.html              # Frontend UI
│   ├── style.css               # Swiss design aesthetic
│   └── script.js               # Frontend logic
├── schema.sql                  # PostgreSQL database schema
└── requirements.txt            # Python dependencies
```

### Core Pipeline: 3-Pass Architecture

#### Pass 1: Document Classification
**Goal:** Categorize each document into one of 28 types

**Approach:** Hybrid keyword + AI
1. **Keyword pre-scan** (efficiency): Check for high-confidence patterns
   - Example: "certificate of incorporation" → Charter (90%+ confidence)
   - Saves API calls, reduces latency
2. **Claude fallback**: For ambiguous documents, full AI classification
   - Multimodal input (text + images for complex PDFs)
   - Structured JSON output with confidence score

**Categories (28 types):**
- **Formation:** Charter, Bylaws, Incorporation Certificate
- **Equity:** Stock Purchase Agreement, Restricted Stock Agreement, Option Grant
- **Financing:** SAFE, Convertible Note, Series A/B/C Preferred
- **Governance:** Board Minutes/Consent, Shareholder Consent, Voting Agreement
- **Compliance:** 83(b) Election, Share Repurchase, Annual Report
- **Contracts:** Employment Agreement, Consulting Agreement, NDA
- **IP:** IP Assignment, Patent Application
- **Other:** Cap Table, Financial Statement, Due Diligence Checklist, Unknown

**Output:** `document_type`, `confidence`, `classification_method` (keyword/ai)

#### Pass 2: Structured Data Extraction
**Goal:** Extract type-specific fields with verification

**Type-Specific Extraction:**

```python
Charter → {
    company_name, incorporation_date, incorporation_state,
    authorized_common, authorized_preferred
}

Stock Purchase Agreement → {
    shareholder, share_type, shares_issued, price_per_share,
    total_amount, issuance_date
}

SAFE → {
    investor, investment_amount, valuation_cap, discount_rate,
    issuance_date
}

Board Minutes/Consent → {
    meeting_date, meeting_type, decisions: [
        {decision_type, description, approval_status}
    ]
}

Option Grant → {
    recipient, shares_granted, strike_price, vesting_schedule,
    grant_date
}

Share Repurchase → {
    shareholder, shares_repurchased, price_per_share,
    repurchase_date
}
```

**Verification System:**
- Claude provides extracted values + source text snippets
- Backend checks: Do snippets contain the extracted values?
- Confidence score: % of verified fields
- Flags hallucinations for manual review

**Output:** `extracted_data` (JSONB), `verification_score`, `verified_fields`

#### Pass 3: Cross-Document Synthesis
**Goal:** Aggregate data into corporate history view

**Timeline Generation:**
- Chronological event list (formation, issuances, board actions, financings)
- Source document references
- Event categorization (formation, equity, financing, governance, compliance)

**Cap Table Generation (Programmatic):**
```python
# NOT AI-generated - deterministic calculation
cap_table = {}
for doc in stock_issuances:
    shareholder = doc.shareholder
    shares = doc.shares_issued
    cap_table[shareholder] = cap_table.get(shareholder, 0) + shares

for doc in repurchases:
    shareholder = doc.shareholder
    shares = doc.shares_repurchased
    cap_table[shareholder] -= shares  # Negative operation

# Calculate ownership %
total_shares = sum(cap_table.values())
for shareholder in cap_table:
    ownership_pct = (cap_table[shareholder] / total_shares) * 100
```

**Issue Tracker:**
- **Deterministic rules:**
  - Missing 83(b) elections (stock issuance without 83(b) within 30 days)
  - Shares exceed authorized (issued > authorized_common/preferred)
  - Unsigned board approvals (equity issuance without board consent)
- **AI analysis:**
  - Amendment approval thresholds (did company get required % of signatures?)
  - Compliance with securities exemptions (Reg D limits, trailing averages)
  - Inconsistencies across documents

**Company Name Extraction:**
- Extract from Charter documents
- Fallback to first occurrence in any document

**Output:** `timeline`, `cap_table`, `issues`, `company_name`

---

## DEVELOPMENT PHILOSOPHY

### Principle 1: SIMPLICITY FIRST
**Minimal files. Minimal dependencies. Maximum clarity.**

- Single-file components when possible (`processing.py` = entire pipeline)
- Vanilla JS frontend (no React, no build step)
- No premature abstractions
- Delete code faster than you add it

### Principle 2: HYBRID > PURE AI
**Use deterministic logic where possible. AI where necessary.**

**Good uses of AI:**
- Document classification (nuanced, context-dependent)
- Free-text extraction (dates, names, amounts from prose)
- Issue detection (amendment compliance, securities law interpretation)

**Bad uses of AI:**
- Cap table math (use `sum()`, not Claude)
- Ownership percentage calculation (arithmetic, not inference)
- Critical compliance checks (deterministic rules, not probabilistic)

**Why:** Explainability, cost, speed, accuracy

### Principle 3: VERIFICATION OVER TRUST
**AI hallucinates. Verify everything.**

- Source text verification for extracted data
- Confidence scoring on classifications
- Programmatic cross-checks (shares vs. authorized amounts)
- Issue flagging (manual review required)

### Principle 4: GRACEFUL DEGRADATION
**Handle failures elegantly.**

- Rate limits → Queue documents, retry with backoff
- Parsing timeouts → Fallback to text extraction, log warning
- NULL bytes in JSONB → Clean strings before storage
- Missing fields → Partial extraction better than failure

### Principle 5: PROGRESS TRANSPARENCY
**Long-running operations need real-time feedback.**

- WebSocket or polling-based progress updates
- Granular status: "Parsing document 5/127...", "Extracting data from Stock Purchase Agreement..."
- Error visibility: Show failures inline, don't hide them

---

## DESIGN SYSTEM

### Aesthetic Identity
**Swiss. Docs-first clarity. Lab-like canvas with a single neon accent.**

Think: Stripe Docs meets Linear meets Figma Config. Not playful, not corporate—precise.

### Color Palette

```css
/* Primary */
--bg: #FFFFFF;              /* Canvas */
--text: #000000;            /* Ink */
--accent: #D42B1E;          /* Red (single neon accent) */

/* Neutrals */
--gray-50: #FAFAFA;         /* Subtle background */
--gray-100: #F5F5F5;        /* Card background */
--gray-200: #E5E5E5;        /* Border */
--gray-400: #A3A3A3;        /* Muted text */
--gray-600: #525252;        /* Secondary text */
--gray-900: #171717;        /* Strong text */
```

**Rules:**
- Red is reserved for CTAs, active states, critical issues
- No gradients, no drop shadows, no blur effects
- Borders do more work than shadows (1px solid #E5E5E5)

### Typography

**Primary (Grotesk):** Space Grotesk
- Headlines: 600-700 weight
- Body: 400-500 weight
- Usage: UI labels, headings, marketing copy

**Secondary (Monospace):** SF Mono / Consolas / Monaco
- Code blocks, data tables, technical values
- Usage: JSON output, cap table, document metadata

```css
/* Type scale */
--text-xs: 12px;   /* Metadata, footnotes */
--text-sm: 14px;   /* Body, descriptions */
--text-base: 16px; /* Default */
--text-lg: 18px;   /* Section headers */
--text-xl: 24px;   /* Page titles */
--text-2xl: 32px;  /* Hero */
```

**Copy tone:** Mission brief meets API reference
- Short, declarative sentences
- Active voice ("Upload documents" not "Documents can be uploaded")
- Technical precision without jargon
- Example: "3-pass pipeline extracts structured data" not "Our advanced AI solution leverages..."

### Layout Grid

**Principles:**
- Disciplined and modular
- 8px base unit (spacing, padding, margins in multiples of 8)
- Max width: 1200px (content), full-bleed for hero
- Breakpoints: 640px (mobile), 768px (tablet), 1024px (desktop)

**Patterns:**

1. **Full-bleed hero**
   ```
   [========================]
   |  Hero: Upload Zone     |
   [========================]
   ```

2. **Card rails** (3-column grid for documents)
   ```
   [Card] [Card] [Card]
   [Card] [Card] [Card]
   ```

3. **Tabbed code** (Timeline, Cap Table, Issues)
   ```
   [Tab 1] [Tab 2] [Tab 3]
   [------------------------]
   | Content area           |
   [------------------------]
   ```

4. **Icon taxonomy** (Document type icons, status indicators)
   - Minimal line icons (Heroicons style)
   - 16px / 24px sizes
   - Consistent stroke weight (1.5px)

### Motion

**Precise and sparing.**

- Transitions: 150ms ease-out (default), 300ms ease-in-out (modals)
- Hover states: Subtle (opacity 0.8, no transform unless interactive)
- Loading: Minimal spinner (red accent), no skeletons
- Page transitions: None (instant navigation)

**When to use motion:**
- Button hover (opacity shift)
- Modal open/close (fade + scale)
- Tab switch (crossfade, no slide)
- Progress indicator (continuous animation)

**When NOT to use motion:**
- Card hover (static)
- Icon appearance (instant)
- Text reveal (no typewriter effect)

### Imagery & Iconography

**Schematic motifs:**
- Document flow diagrams (boxes + arrows)
- Timeline visualizations (vertical line + nodes)
- Cap table as structured data table (no pie charts)
- Illustrated states (empty state, error state, success state)

**Rules:**
- No stock photos, no illustrations with humans
- Favor diagrams, data viz, schematic drawings
- Duotone: Black + Red only
- SVG preferred over raster

---

## DOMAIN KNOWLEDGE

### Corporate Document Types (28 Categories)

#### 1. Formation Documents
**Charter (Certificate/Articles of Incorporation)**
- Establishes company existence
- Specifies authorized shares (common, preferred)
- Filed with state (Delaware, California, etc.)
- Key fields: company name, incorporation date, state, authorized shares

**Bylaws**
- Internal governance rules
- Board structure, voting procedures, shareholder meetings
- Not filed publicly

**Incorporation Certificate**
- State-issued proof of incorporation
- Contains entity number, filing date

#### 2. Equity Documents

**Stock Purchase Agreement**
- Investor buys shares directly from company
- Key fields: shareholder, shares, price, date, share type (common/preferred)
- Often paired with board consent approval

**Restricted Stock Agreement**
- Employee receives shares subject to vesting
- Vesting schedule (e.g., 4-year, 1-year cliff)
- Key fields: recipient, shares, vesting terms, grant date

**Option Grant (Stock Option Agreement)**
- Employee receives right to buy shares at strike price
- Vesting schedule, exercise period (10 years typical)
- Key fields: recipient, shares, strike price, vesting, grant date

**83(b) Election**
- IRS form to elect taxation at grant (not vest)
- Must be filed within 30 days of stock grant
- **Compliance check:** Stock issuance without 83(b) = issue

**Share Repurchase Agreement**
- Company buys back shares from shareholder
- Key fields: shareholder, shares, price, date
- **Cap table impact:** Negative shares (reduces shareholder position)

#### 3. Financing Documents

**SAFE (Simple Agreement for Future Equity)**
- Pre-seed/seed financing instrument
- Converts to equity at next priced round
- Key fields: investor, amount, valuation cap, discount rate, date

**Convertible Note**
- Debt that converts to equity
- Interest rate, maturity date, conversion terms
- Key fields: investor, principal, interest rate, maturity, conversion terms

**Series A/B/C Preferred Stock Purchase Agreement**
- Priced equity round
- Detailed terms: liquidation preference, voting rights, protective provisions
- Key fields: investors, shares, price, valuation, rights

**Term Sheet**
- Non-binding summary of deal terms
- Often precedes definitive agreements

#### 4. Governance Documents

**Board Minutes**
- Record of board meeting
- Decisions, votes, attendees
- Key fields: date, decisions (approval of stock issuances, financings, etc.)

**Board Consent (Written Consent in Lieu of Meeting)**
- Board action without formal meeting
- Requires unanimous consent (unless bylaws specify otherwise)
- Key fields: date, decisions, signatures

**Shareholder Consent**
- Shareholder action without formal meeting
- Threshold: majority or supermajority (depends on action type)
- **Compliance check:** Amendments may require specific % approval

**Voting Agreement**
- Shareholders agree on how to vote
- Common in investor rights agreements

#### 5. Compliance & Regulatory

**Annual Report**
- State filing (Delaware franchise tax, California statement of information)
- Lists directors, officers, agent for service

**Securities Filing (Form D)**
- Federal notice of securities offering
- Filed with SEC for Reg D exemptions (Rule 506(b), 506(c))
- **Compliance check:** Aggregate limits per exemption

**Cap Table**
- Snapshot of ownership at a point in time
- May be outdated or incomplete (Tieout rebuilds from source docs)

#### 6. Employment & IP

**Employment Agreement**
- Job title, salary, equity grants
- May reference stock option plan

**Consulting Agreement**
- Similar to employment, but contractor status

**IP Assignment Agreement**
- Employee assigns inventions to company
- Standard for tech companies

**NDA (Non-Disclosure Agreement)**
- Confidentiality obligations

#### 7. Other

**Financial Statement**
- Balance sheet, income statement, cash flow
- Not governance-related, but often in data rooms

**Due Diligence Checklist**
- List of requested documents
- Useful for identifying gaps

**Unknown**
- Catch-all for unrecognizable documents

### Cap Table Mathematics

**Basic Calculation:**
```python
# Start with issuances
cap_table = {}
for issuance in stock_purchases + option_grants + restricted_stock:
    shareholder = issuance.shareholder
    shares = issuance.shares_issued
    cap_table[shareholder] = cap_table.get(shareholder, 0) + shares

# Subtract repurchases
for repurchase in share_repurchases:
    shareholder = repurchase.shareholder
    shares = repurchase.shares_repurchased
    cap_table[shareholder] -= shares

# Calculate ownership %
total_shares = sum(cap_table.values())
for shareholder, shares in cap_table.items():
    ownership_pct = (shares / total_shares) * 100
```

**Complexity:**
- Share classes (common, preferred) have different rights
- Fully diluted vs. issued-and-outstanding
- Conversion ratios (preferred → common)
- Option pool sizing (unissued but reserved)

**MVP Scope:** Issued-and-outstanding only (no fully diluted yet)

### Compliance Issues

#### 1. 83(b) Elections
**Rule:** Must be filed within 30 days of restricted stock grant

**Check:**
```python
for stock_grant in restricted_stock_agreements:
    grant_date = stock_grant.grant_date
    has_83b = any(
        election.recipient == stock_grant.recipient and
        abs((election.filing_date - grant_date).days) <= 30
        for election in elections_83b
    )
    if not has_83b:
        issues.append(f"Missing 83(b) election for {stock_grant.recipient}")
```

#### 2. Authorized Shares
**Rule:** Issued shares cannot exceed authorized shares

**Check:**
```python
total_common_issued = sum(issuance.shares for issuance in common_stock)
authorized_common = charter.authorized_common
if total_common_issued > authorized_common:
    issues.append(f"Issued common ({total_common_issued}) exceeds authorized ({authorized_common})")
```

#### 3. Board Approvals
**Rule:** Equity issuances require board approval

**Check:**
```python
for issuance in stock_purchases:
    issuance_date = issuance.issuance_date
    has_approval = any(
        consent.meeting_date <= issuance_date and
        "stock issuance" in consent.decisions
        for consent in board_consents
    )
    if not has_approval:
        issues.append(f"No board approval for issuance on {issuance_date}")
```

#### 4. Amendment Approvals
**Rule:** Charter/voting agreement amendments may require specific % of shareholders/investors

**Example:** Series A Preferred amendment requires 67% of Series A holders to approve

**Check:** AI-based analysis (parse amendment doc, identify threshold, cross-reference signatures)

#### 5. Securities Law Exemptions
**Rule:** Reg D 506(b) - $5M limit per 12-month rolling period (example)

**Check:** Aggregate SAFEs + Convertible Notes over trailing 12 months, flag if approaching limit

---

## CODE PATTERNS & BEST PRACTICES

### Database: PostgreSQL + JSONB

**Schema:**
```sql
CREATE TABLE audits (
    id SERIAL PRIMARY KEY,
    status VARCHAR(50),           -- "processing", "completed", "failed"
    progress_step VARCHAR(255),   -- "Parsing document 5/127..."
    progress_percent INTEGER,     -- 0-100
    documents JSONB,              -- Array of {filename, type, confidence, data}
    timeline JSONB,               -- Array of chronological events
    cap_table JSONB,              -- {shareholder: {shares, ownership_pct}}
    issues JSONB,                 -- Array of {type, description, severity}
    company_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Why JSONB:**
- Flexible schema (document types have different fields)
- Fast lookups with GIN indexes
- No need for JOIN-heavy normalization (single audit = single row)

**Gotcha: NULL bytes**
```python
# PostgreSQL JSONB rejects NULL bytes (\x00)
# Clean strings before storage
def clean_for_jsonb(text):
    return text.replace('\x00', '') if text else text
```

### Document Parsing

**Timeout Pattern:**
```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError

def parse_with_timeout(file_path, timeout=20):
    with ThreadPoolExecutor() as executor:
        future = executor.submit(pymupdf4llm.to_markdown, file_path)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            # Fallback: basic text extraction
            return extract_text_fallback(file_path)
```

**Why:** Large PDFs (100+ pages) can hang. Better to get partial text than fail.

### Claude API: Rate Limit Handling

```python
import anthropic
from anthropic import RateLimitError

def call_claude_with_retry(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000
            )
            return response.content[0].text
        except RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
```

**Why:** Anthropic rate limits (500 RPM typical). Graceful retry prevents total failure.

### Progress Updates

**Pattern:**
```python
# In processing.py
def update_progress(audit_id, step, percent):
    db.update_audit_progress(audit_id, step, percent)

# In main.py (endpoint)
@app.get("/api/audits/{audit_id}/progress")
def get_progress(audit_id: int):
    audit = db.get_audit(audit_id)
    return {
        "step": audit.progress_step,
        "percent": audit.progress_percent,
        "status": audit.status
    }

# In script.js (frontend)
function pollProgress(auditId) {
    const interval = setInterval(async () => {
        const res = await fetch(`/api/audits/${auditId}/progress`);
        const data = await res.json();
        updateProgressBar(data.percent);
        updateProgressText(data.step);
        if (data.status === "completed") clearInterval(interval);
    }, 1000);  // Poll every 1s
}
```

**Why:** UX transparency for 2-5 minute processing time

### Error Handling Philosophy

**Fail fast for critical errors:**
```python
if not os.path.exists(zip_path):
    raise FileNotFoundError(f"Upload file not found: {zip_path}")
```

**Graceful degradation for non-critical:**
```python
try:
    extracted_data = extract_data_with_claude(doc)
except Exception as e:
    logger.warning(f"Extraction failed for {doc.filename}: {e}")
    extracted_data = {}  # Partial failure, continue processing
```

**Log everything:**
```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Starting audit {audit_id}")
logger.warning(f"Parsing timeout for {filename}")
logger.error(f"Claude API failed: {error}")
```

---

## CURRENT STATE (as of 2025-11-13)

### MVP Status: ✅ Fully Functional

**Deployed on Render:**
- Live production environment
- PostgreSQL database configured
- 50MB upload limit enforced

**Recent Improvements:**
1. **Phase 1 Accuracy Upgrades** (~700 lines)
   - Enhanced extraction prompts
   - Better verification logic
   - Improved issue detection
2. **Repurchase Handling**
   - Negative share accounting
   - Cap table adjustments
3. **UI Progress Fixes**
   - Real-time progress updates
   - Fixed TypeError on None shares
4. **Rebrand**
   - Platform renamed: "Tieout: Corporate Governance Auditing"

### Current Capabilities

**Working:**
- End-to-end document processing (upload → classification → extraction → synthesis)
- 28 document type classification
- Structured data extraction with verification
- Timeline generation
- Cap table calculation (programmatic)
- Issue detection (deterministic + AI)
- Real-time progress tracking
- Swiss design UI with red accent

**Known Limitations:**
- 50MB upload limit (Render free tier)
- No authentication (single-user MVP)
- Single processing queue (no concurrent audits)
- No Cooley-format export yet (planned v2)
- No fully diluted cap table (issued-and-outstanding only)

### Tech Debt / Future Refactors

**None significant.** Code is clean, simple, well-structured.

**Potential improvements:**
- Split `processing.py` into separate modules (classification.py, extraction.py, synthesis.py) if it grows beyond 1,000 lines
- Add caching for repeated document parses (if re-processing same files)
- Batch Claude API calls (currently sequential)

---

## FUTURE ROADMAP

### V2 Features (Post-MVP)

**1. Multi-User Authentication**
- Login/signup flow
- Per-user audit history
- Role-based access (attorney, paralegal, viewer)

**2. Cooley-Format Export**
- Structured data room folder hierarchy
- PDF bookmarks and annotations
- Excel cap table export (Carta-compatible)

**3. Batch Processing**
- Process multiple audits concurrently
- Queue system (Redis + Celery or background workers)

**4. Advanced Compliance**
- Securities law rules engine (Reg D, Reg CF, Reg A limits)
- Amendment approval threshold checking
- Trailing average calculations (12-month rolling)

**5. Integrations**
- Carta API (cap table import/export)
- DocuSign/HelloSign (signature verification)
- Google Drive / Dropbox (direct folder import)

**6. Data Visualization**
- Interactive timeline (filterable by event type)
- Cap table waterfall charts
- Ownership dilution over time

### Scaling Considerations

**Database:**
- Current: Single PostgreSQL instance
- Scale: Read replicas for analytics, partitioning by audit_id

**File Storage:**
- Current: Local filesystem (Render ephemeral disk)
- Scale: S3 or R2 for persistent storage

**AI Costs:**
- Current: ~$0.50-2.00 per audit (100-500 docs)
- Scale: Batch API (50% cost reduction), caching, smarter keyword pre-filtering

**Performance:**
- Current: 2-5 minutes for 100 docs
- Scale: Parallel document processing (ThreadPoolExecutor), batch Claude calls

---

## DEVELOPMENT GUIDELINES FOR CLAUDE CODE

### When Adding Features

1. **Check if it's necessary.** Does it solve a real user problem, or is it speculative?
2. **Prefer editing existing files over creating new ones.** Keep the codebase compact.
3. **Use deterministic logic where possible.** AI is for nuance, not arithmetic.
4. **Verify AI outputs.** Source text checks, confidence scores, cross-document reconciliation.
5. **Update progress tracking.** Any operation >5 seconds needs progress visibility.
6. **Test with real documents.** Mock data doesn't catch edge cases (NULL bytes, Unicode, OCR errors).

### When Debugging

1. **Check logs first.** `logger.info()` and `logger.error()` are your friends.
2. **Reproduce locally.** `LOCAL_SETUP.md` has full local dev setup.
3. **Test incrementally.** Isolate the failing pass (classification, extraction, synthesis).
4. **Inspect JSONB.** Use `psql` to query `documents`, `timeline`, `issues` directly.

### When Refactoring

1. **Don't abstract prematurely.** One caller = no abstraction needed.
2. **Preserve simplicity.** If a refactor adds >50 lines, it's probably not worth it.
3. **Keep the 3-pass structure.** Classification → Extraction → Synthesis is the core architecture.

### When Writing Code

**Follow existing patterns:**
- FastAPI route → call `processing.py` function → update DB → return JSON
- Frontend: Vanilla JS, no frameworks, direct DOM manipulation
- CSS: BEM-style naming, no utility classes

**Code style:**
- Python: Black formatter, type hints for function signatures
- JavaScript: ES6+, async/await, no jQuery
- SQL: Uppercase keywords, explicit column names

**Comments:**
- Explain *why*, not *what*
- Document edge cases ("NULL byte cleaning required for PostgreSQL JSONB")
- No TODO comments (use GitHub Issues instead)

---

## EXAMPLE USE CASES

### Use Case 1: Series A Amendment Compliance

**Scenario:**
Company raised Series A in 2022. In 2024, they want to amend the voting agreement to reduce the approval threshold from 67% to 51%. Did they get the required signatures?

**Tieout Output:**
1. **Timeline:** Series A financing (2022-03-15), Amendment proposed (2024-06-01)
2. **Documents:** Series A Stock Purchase Agreement, Voting Agreement, Amendment to Voting Agreement
3. **Issue Detected:** "Amendment requires 67% of Series A holders (5 of 7 investors). Only 4 signatures found. Missing: Acme Ventures, Sequoia Capital."
4. **Action:** Flag for manual review, contact missing investors

### Use Case 2: 83(b) Election Gap

**Scenario:**
Company granted restricted stock to 3 founders on 2023-01-01. Only 2 founders filed 83(b) elections.

**Tieout Output:**
1. **Documents:** 3 Restricted Stock Agreements, 2 83(b) Elections
2. **Issue Detected:** "Founder C received 250,000 shares on 2023-01-01. No 83(b) election found within 30-day window. Potential tax liability."
3. **Action:** Advise Founder C to consult tax attorney (late 83(b) filing not accepted by IRS)

### Use Case 3: Cap Table Reconciliation

**Scenario:**
Company has conflicting cap tables from different financing rounds. Need to rebuild from source documents.

**Tieout Output:**
1. **Documents:** 15 stock purchase agreements, 3 option grants, 1 repurchase
2. **Cap Table (Rebuilt):**
   - Founder A: 500,000 shares (50%)
   - Founder B: 300,000 shares (30%)
   - Seed Investor: 150,000 shares (15%)
   - Employee 1: 50,000 shares (5%)
   - **Total: 1,000,000 shares**
3. **Issue Detected:** "Existing cap table shows Founder A with 600,000 shares. Source documents only support 500,000. Discrepancy: 100,000 shares."
4. **Action:** Investigate missing stock purchase agreement or repurchase

---

## GLOSSARY

**Cap Table:** Capitalization table - ledger of ownership (shareholders, shares, percentages)

**83(b) Election:** IRS form to elect immediate taxation on restricted stock (avoids tax on vesting)

**SAFE:** Simple Agreement for Future Equity - convertible security (popular for seed rounds)

**Charter:** Certificate/Articles of Incorporation - legal document establishing company

**Board Consent:** Written approval by board of directors (in lieu of formal meeting)

**Authorized Shares:** Maximum shares company can issue (set in charter)

**Issued Shares:** Shares actually distributed to shareholders

**Fully Diluted:** Cap table including all potential shares (options, SAFEs, convertibles)

**Vesting:** Gradual ownership over time (e.g., 4-year vesting = 25% per year)

**Liquidation Preference:** Preferred shareholders get paid first in exit (1x, 2x, etc.)

**Protective Provisions:** Veto rights for investors (board seat, approval on key actions)

**Reg D:** SEC regulation allowing private securities offerings (Rule 506(b), 506(c))

**Cooley Format:** Law firm Cooley's standard data room structure (industry standard)

---

## CONTACT & CONTRIBUTION

**Developer:** Justin (jake-sortor on GitHub)
**Project:** Tieout - Corporate Governance Auditing
**Stack:** FastAPI + PostgreSQL + Claude 3.5 Sonnet
**Repository:** corporate-audit-mvp
**License:** Not specified (proprietary/startup MVP)

**For Claude Code:**
- This file serves as your persistent context memory
- When asked about the project, reference this document
- When adding features, follow the patterns and philosophy outlined here
- When debugging, consult the "Current State" and "Code Patterns" sections
- When uncertain, ask clarifying questions (don't guess)

**Remember:** SIMPLICITY. VERIFICATION. TRANSPARENCY.

---

*Last updated: 2025-11-13*
*Version: 1.0 (Initial skill file)*
