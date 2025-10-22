"""
Claude prompt templates for document analysis.
All prompts are designed to return valid JSON for easy parsing.
"""

# Document type categories for classification
DOC_CATEGORIES = [
    "Charter Document",
    "Board/Shareholder Minutes",
    "Stock Purchase Agreement",
    "Stock Certificate",
    "Assignment Agreement",
    "Share Repurchase Agreement",
    "83(b) Election",
    "Indemnification Agreement",
    "IP/Proprietary Info Agreement",
    "Corporate Records",
    "Tax Document",
    "Marketing Materials",
    "License Agreement",
    "SAFE",
    "Convertible Note",
    "Option Grant Agreement",
    "Equity Incentive Plan",
    "Financial Statement",
    "Employment Agreement",
    "Other"
]


# ============================================================================
# PASS 1: CLASSIFICATION
# ============================================================================

CLASSIFICATION_PROMPT = """You are an expert paralegal AI specializing in corporate governance for startups.

Your task is to analyze the following document excerpt and classify it into ONE category.

DOCUMENT EXCERPT:
---
{text}
---

CATEGORIES (with examples):
- Charter Document: Certificate of Incorporation, Amended Certificate, Articles of Incorporation, Bylaws, Certificate of Secretary
- Board/Shareholder Minutes: Meeting Minutes, Written Consent, Board Resolutions, Action by Written Consent
- Stock Purchase Agreement: Restricted Stock Purchase Agreement, Stock Subscription Agreement, Joint Escrow Instructions, Stock Purchase Verification
- Stock Certificate: Common Stock Certificate, Preferred Stock Certificate
- Assignment Agreement: Stock Assignment Separate from Certificate, IP Assignment Agreement, Technology Assignment
- Share Repurchase Agreement: Share Repurchase Agreement, Buyback Receipt, Repurchase Email Confirmation
- 83(b) Election: IRS Section 83(b) Election forms
- Indemnification Agreement: Director Indemnification Agreement, Officer Indemnification Agreement
- IP/Proprietary Info Agreement: Employee Proprietary Information Agreement, Invention Assignment Agreement, Confidentiality Agreement
- Corporate Records: EIN Assignment, Bank Account Verification, Good Standing Certificate
- Tax Document: Franchise Tax Report, Tax Payment Receipt, Annual Report Confirmation
- Marketing Materials: Pitch Deck, Technology Sheet, Product Presentation, Sales Materials
- License Agreement: Technology License, Patent License, Research License Agreement
- SAFE: Simple Agreement for Future Equity
- Convertible Note: Convertible Promissory Note, Convertible Debt Agreement
- Option Grant Agreement: Stock Option Grant, RSU Agreement, Vesting Schedule
- Equity Incentive Plan: Stock Option Plan, Equity Compensation Plan, 2023 Equity Incentive Plan
- Financial Statement: Balance Sheet, Income Statement, Cap Table Spreadsheet, Financial Projections
- Employment Agreement: Employment Contract, Offer Letter, Consulting Agreement, Advisor Agreement
- Other: Use ONLY if document truly doesn't fit any category above

CRITICAL CLASSIFICATION RULES:
1. "Certificate of Incorporation" → Charter Document (NOT Other or Corporate Records)
2. "Bylaws" or "Certificate of Secretary" → Charter Document
3. Pitch decks, tech sheets → Marketing Materials (NOT Other)
4. License agreements from universities/government → License Agreement (NOT Other)
5. 83(b) tax elections → 83(b) Election (NOT Tax Document or Other)
6. Advisor agreements → Employment Agreement
7. Only use "Other" if document absolutely doesn't fit any specific category

INSTRUCTIONS:
1. Read the document carefully and match to the MOST SPECIFIC category
2. Provide a one-sentence summary of the document's purpose
3. Respond ONLY with valid JSON in this exact format:

{{"doc_type": "Category Name", "summary": "One sentence summary"}}

Do not include any markdown formatting, code blocks, or explanatory text. Only return the JSON object."""


# ============================================================================
# PASS 2: EXTRACTION (per document type)
# ============================================================================

CHARTER_EXTRACTION_PROMPT = """You are analyzing a Charter Document (Certificate of Incorporation or Bylaws).

DOCUMENT TEXT:
---
{text}
---

Extract the following information:
- company_name: The full legal name of the company
- incorporation_date: Date of incorporation (YYYY-MM-DD format)
- authorized_shares: Total authorized shares (common + all preferred classes)
- share_classes: List of all authorized share classes (e.g., ["Common Stock", "Series A Preferred"])

If any field cannot be found, use null.

Respond ONLY with valid JSON:
{{"company_name": "...", "incorporation_date": "...", "authorized_shares": 0, "share_classes": []}}"""


STOCK_EXTRACTION_PROMPT = """You are analyzing a Stock Purchase Agreement or stock issuance document.

DOCUMENT TEXT:
---
{text}
---

Extract ALL equity issuances mentioned in this document. For each issuance:
- shareholder: Full name of the person or entity receiving shares
- shares: Number of shares issued (integer)
- share_class: Type of stock (e.g., "Common Stock", "Series A Preferred")
- price_per_share: Price per share (float, or null if not mentioned)
- date: Effective date of issuance (YYYY-MM-DD format)

Respond ONLY with valid JSON (array of issuances):
[{{"shareholder": "...", "shares": 0, "share_class": "...", "price_per_share": 0.0, "date": "..."}}]

If no issuances found, return an empty array: []"""


SAFE_EXTRACTION_PROMPT = """You are analyzing a SAFE (Simple Agreement for Future Equity) document.

DOCUMENT TEXT:
---
{text}
---

Extract the following:
- investor: Name of the investor
- amount: Investment amount in dollars (integer)
- valuation_cap: Valuation cap in dollars (integer, or null)
- discount_rate: Discount rate as a percentage (float, or null)
- date: Effective date of the SAFE (YYYY-MM-DD format)

Respond ONLY with valid JSON:
{{"investor": "...", "amount": 0, "valuation_cap": null, "discount_rate": null, "date": "..."}}"""


BOARD_MINUTES_EXTRACTION_PROMPT = """You are analyzing Board or Shareholder Minutes/Consents.

DOCUMENT TEXT:
---
{text}
---

Extract:
- meeting_date: Date of the meeting or consent (YYYY-MM-DD format)
- meeting_type: "Board Meeting", "Shareholder Meeting", or "Written Consent"
- key_decisions: List of key decisions made (array of strings, max 3-5 items)

Respond ONLY with valid JSON:
{{"meeting_date": "...", "meeting_type": "...", "key_decisions": []}}"""


OPTION_GRANT_EXTRACTION_PROMPT = """You are analyzing an Option Grant Agreement or RSU Agreement.

DOCUMENT TEXT:
---
{text}
---

Extract:
- recipient: Name of the person receiving the options/RSUs
- shares: Number of shares subject to the grant (integer)
- strike_price: Exercise/strike price per share (float, or null for RSUs)
- vesting_schedule: Brief description of vesting (e.g., "4 years, 1 year cliff")
- grant_date: Date of the grant (YYYY-MM-DD format)

Respond ONLY with valid JSON:
{{"recipient": "...", "shares": 0, "strike_price": null, "vesting_schedule": "...", "grant_date": "..."}}"""


# ============================================================================
# PASS 3: SYNTHESIS
# ============================================================================

TIMELINE_SYNTHESIS_PROMPT = """You are synthesizing a corporate event timeline from extracted data.

EXTRACTED DATA (from all documents):
---
{extractions_json}
---

Create a chronological timeline of major corporate events. Include:
- Formation/incorporation
- Financing rounds (SAFE, stock issuances)
- Board/shareholder meetings
- Option grants
- Any other significant corporate actions

For each event, provide:
- date: YYYY-MM-DD format
- event_type: "formation", "financing", "stock_issuance", "board_action", "option_grant", or "other"
- description: Brief description (one sentence)
- source_docs: Array of source document filenames

Respond ONLY with valid JSON (array of events sorted by date):
[{{"date": "...", "event_type": "...", "description": "...", "source_docs": []}}]"""


CAP_TABLE_SYNTHESIS_PROMPT = """You are building a capitalization table from equity issuance data.

EXTRACTED EQUITY DATA:
---
{equity_data_json}
---

Aggregate all equity issuances by shareholder and share class. Calculate:
- Total shares per shareholder per class
- Ownership percentage (shares / total outstanding shares * 100)

For SAFEs and convertible notes, list them separately as "SAFE" or "Convertible Note" in the share_class field.

Respond ONLY with valid JSON (array of cap table entries):
[{{"shareholder": "...", "shares": 0, "share_class": "...", "ownership_pct": 0.0}}]

Sort by ownership percentage descending."""


ISSUE_TRACKER_PROMPT = """You are a corporate attorney auditing governance records for a startup. Identify concrete issues and missing documents.

DOCUMENTS PROVIDED:
---
{documents_json}
---

CAP TABLE DATA:
---
{cap_table_json}
---

TIMELINE DATA:
---
{timeline_json}
---

CHECK FOR THESE SPECIFIC ISSUES:

1. FOUNDATIONAL DOCUMENTS (critical if missing):
   - Certificate of Incorporation or Articles of Incorporation
   - Bylaws (required for all corporations)
   - Initial board consent or organizational meeting minutes
   - Stock ledger or capitalization table spreadsheet

2. EQUITY ISSUANCE COMPLIANCE (critical):
   - Stock issued after incorporation without board approval/consent
   - Founders receiving stock without 83(b) elections filed (for vested stock)
   - Stock options granted without an adopted Equity Incentive Plan
   - Stock certificates issued without underlying purchase agreements

3. BOARD GOVERNANCE (warning):
   - No board minutes/consents for major corporate actions (financing, officer appointments, etc.)
   - Annual shareholder meetings not documented (if required by bylaws)
   - Director/officer indemnification agreements missing

4. CAP TABLE INTEGRITY (warning):
   - Issued shares appear to exceed authorized shares (check charter authorized amount)
   - Repurchase transactions in timeline not reflected in current cap table
   - Discrepancies between stock certificates and purchase agreements

5. CORPORATE COMPLIANCE (note):
   - Missing annual reports/franchise tax filings for any year since incorporation
   - IP assignments missing for founders (if company owns technology)
   - Employment agreements missing for executives

SEVERITY DEFINITIONS:
- "critical": Legal compliance issue that could invalidate equity or create liability
- "warning": Missing best practice document or governance gap that should be fixed
- "note": Recommended document to have but not strictly required

For EACH issue found:
- severity: "critical", "warning", or "note"
- category: e.g., "Missing Document", "Equity Compliance", "Board Governance"
- description: Specific issue with relevant document names if applicable

ONLY REPORT REAL ISSUES. If documents appear complete and proper, return empty array.

Respond ONLY with valid JSON (array of issues):
[{{"severity": "...", "category": "...", "description": "..."}}]"""


# ============================================================================
# HELPER: COMPANY NAME EXTRACTION
# ============================================================================

COMPANY_NAME_EXTRACTION_PROMPT = """Extract the company's legal name from these charter documents.

CHARTER DOCUMENTS:
---
{charter_texts}
---

Look for phrases like:
- "The name of the corporation is..."
- "Certificate of Incorporation of..."
- As used in header/footer

Respond with ONLY the company name (no JSON, just the text):"""
