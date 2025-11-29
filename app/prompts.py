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

CLASSIFICATION_PROMPT = """You are a corporate paralegal classifying legal documents for a startup.

EXAMPLES OF CORRECT CLASSIFICATIONS:
- "CERTIFICATE OF INCORPORATION OF ACME, INC." → Charter Document
- "Common Stock Certificate No. 001 - Jake Sortor - 9,000,000 shares" → Stock Certificate
- "Acme Pitch Deck - Series A Fundraising" → Marketing Materials
- "Restricted Stock Purchase Agreement between Acme, Inc. and John Smith" → Stock Purchase Agreement
- "Employee Proprietary Information and Inventions Agreement" → IP/Proprietary Info Agreement

AVAILABLE CATEGORIES:
Charter Document, Board/Shareholder Minutes, Stock Purchase Agreement, Stock Certificate, Assignment Agreement, Share Repurchase Agreement, 83(b) Election, Indemnification Agreement, IP/Proprietary Info Agreement, Corporate Records, Tax Document, Marketing Materials, License Agreement, SAFE, Convertible Note, Option Grant Agreement, Equity Incentive Plan, Financial Statement, Employment Agreement, Other

DOCUMENT TO CLASSIFY:
---
{text}
---

INSTRUCTIONS:
1. Read the document title and first few paragraphs
2. Match to the MOST SPECIFIC category that fits
3. Use "Other" only if document truly doesn't fit any category

Respond with ONLY valid JSON:
{{"doc_type": "Category Name", "summary": "One sentence summary"}}"""


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
- source_quote: Exact text from document showing the authorized shares (for verification)

If any field cannot be found, use null.

EXAMPLE INPUT:
"CERTIFICATE OF INCORPORATION OF ACME, INC. Filed on January 15, 2020. ARTICLE IV: The total number of shares which the Corporation is authorized to issue is 10,000,000 shares of Common Stock."

EXAMPLE OUTPUT:
{{"company_name": "Acme, Inc.", "incorporation_date": "2020-01-15", "authorized_shares": 10000000, "share_classes": ["Common Stock"], "source_quote": "The total number of shares which the Corporation is authorized to issue is 10,000,000 shares of Common Stock."}}

RESPONSE FORMAT (JSON Schema):
{{
  "company_name": string or null,
  "incorporation_date": string (YYYY-MM-DD) or null,
  "authorized_shares": integer or null,
  "share_classes": array of strings,
  "source_quote": string or null
}}

Respond ONLY with valid JSON matching this schema."""


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
- source_quote: Exact text from document showing this issuance (for verification)

EXAMPLE INPUT:
"STOCK PURCHASE AGREEMENT dated March 1, 2021 between Acme, Inc. and John Smith. Purchaser agrees to purchase 1,000,000 shares of Common Stock at $0.001 per share."

EXAMPLE OUTPUT:
[{{"shareholder": "John Smith", "shares": 1000000, "share_class": "Common Stock", "price_per_share": 0.001, "date": "2021-03-01", "source_quote": "Purchaser agrees to purchase 1,000,000 shares of Common Stock at $0.001 per share."}}]

RESPONSE FORMAT (JSON Schema):
[
  {{
    "shareholder": string,
    "shares": integer,
    "share_class": string,
    "price_per_share": float or null,
    "date": string (YYYY-MM-DD),
    "source_quote": string
  }}
]

If no issuances found, return an empty array: []

Respond ONLY with valid JSON array matching this schema:"""


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
- source_quote: Exact text from document showing the investment amount and terms (for verification)

EXAMPLE INPUT:
"SAFE dated June 15, 2022 between Acme, Inc. and XYZ Ventures. Investor agrees to invest $500,000 with a valuation cap of $5,000,000 and 20% discount."

EXAMPLE OUTPUT:
{{"investor": "XYZ Ventures", "amount": 500000, "valuation_cap": 5000000, "discount_rate": 20.0, "date": "2022-06-15", "source_quote": "Investor agrees to invest $500,000 with a valuation cap of $5,000,000 and 20% discount."}}

RESPONSE FORMAT (JSON Schema):
{{
  "investor": string,
  "amount": integer,
  "valuation_cap": integer or null,
  "discount_rate": float or null,
  "date": string (YYYY-MM-DD),
  "source_quote": string
}}

Respond ONLY with valid JSON matching this schema:"""


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
- source_quote: Exact text from document showing the grant details (for verification)

Respond ONLY with valid JSON:
{{"recipient": "...", "shares": 0, "strike_price": null, "vesting_schedule": "...", "grant_date": "...", "source_quote": "..."}}"""


SHARE_REPURCHASE_EXTRACTION_PROMPT = """You are analyzing a Share Repurchase Agreement or repurchase documentation.

DOCUMENT TEXT:
---
{text}
---

Extract:
- shareholder: Name of the person/entity whose shares were repurchased by the company
- shares: Number of shares repurchased (integer - use POSITIVE number, we'll subtract it later)
- share_class: Type of stock repurchased (e.g., "Common Stock")
- price_per_share: Price per share paid (float, or null if not mentioned)
- date: Date of repurchase transaction (YYYY-MM-DD format)
- source_quote: Exact text from document showing the repurchase details (for verification)

EXAMPLE INPUT:
"STOCK REPURCHASE AGREEMENT dated September 10, 2023. Acme, Inc. agrees to repurchase 500,000 shares of Common Stock from Jane Doe at $1.50 per share."

EXAMPLE OUTPUT:
{{"shareholder": "Jane Doe", "shares": 500000, "share_class": "Common Stock", "price_per_share": 1.50, "date": "2023-09-10", "source_quote": "Acme, Inc. agrees to repurchase 500,000 shares of Common Stock from Jane Doe at $1.50 per share."}}

RESPONSE FORMAT (JSON Schema):
{{
  "shareholder": string,
  "shares": integer (positive),
  "share_class": string,
  "price_per_share": float or null,
  "date": string (YYYY-MM-DD),
  "source_quote": string
}}

Respond ONLY with valid JSON matching this schema:"""


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
# CAP TABLE TIE-OUT: Batch Approval Matching
# ============================================================================

BATCH_APPROVAL_MATCHING_PROMPT = """You are a corporate attorney matching equity transactions to their board approval documents.

TRANSACTIONS TO VERIFY:
---
{transactions_json}
---

APPROVAL DOCUMENTS AVAILABLE:
---
{approval_docs_json}
---

TASK:
For EACH transaction in the list, identify:
1. The approval_doc_id from the manifest that authorizes this transaction (if any)
2. A specific quote from that approval document proving the approval
3. Compliance status based on these rules:
   - VERIFIED: Approval found with date on or before transaction date
   - WARNING: Approval found but date inconsistency (approval after transaction, or vague wording)
   - CRITICAL: No approval found, or approval clearly insufficient
4. Brief compliance_note explaining your determination

MATCHING GUIDELINES:
- Board Minutes/Consents that say "approve issuance of X shares to Y" match stock issuances
- Board Minutes discussing "equity incentive plan" match option grants
- Formation transactions (incorporations) are self-authorizing via Charter Document
- If transaction date is BEFORE approval date, that's a WARNING (backdated approval concern)
- If no approval document mentions the transaction at all, that's CRITICAL

RESPONSE FORMAT:
Return a JSON array with one entry per transaction. Each entry must have:
- tx_index: integer (from input transactions list)
- approval_doc_id: string UUID or null
- approval_quote: string or null (exact text from approval document)
- compliance_status: "VERIFIED", "WARNING", or "CRITICAL"
- compliance_note: string explaining the status

EXAMPLE OUTPUT:
[
  {{
    "tx_index": 0,
    "approval_doc_id": "abc-123-uuid",
    "approval_quote": "RESOLVED: to approve the issuance of 1,000,000 shares of Common Stock to John Doe...",
    "compliance_status": "VERIFIED",
    "compliance_note": "Transaction approved by board consent dated 2021-02-28 (before issuance date 2021-03-01)"
  }},
  {{
    "tx_index": 1,
    "approval_doc_id": null,
    "approval_quote": null,
    "compliance_status": "CRITICAL",
    "compliance_note": "No board approval found for this option grant. Options should be approved by board under equity incentive plan."
  }}
]

CRITICAL FORMATTING REQUIREMENTS:
1. Output ONLY the JSON array - no explanatory text before or after
2. Escape all quotes within string values using backslash: \\"
3. NO trailing commas before ] or }}
4. Keep approval_quote field under 400 characters to avoid truncation
5. Use null for missing values (not empty strings)

Respond ONLY with valid JSON array matching this format:"""


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
