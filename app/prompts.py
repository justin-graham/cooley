"""
Claude prompt templates for document analysis.
All prompts are designed to return valid JSON for easy parsing.
"""

# Document type categories for classification
DOC_CATEGORIES = [
    "Charter Document",
    "Board/Shareholder Minutes",
    "Stock Purchase Agreement",
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

CATEGORIES:
- Charter Document (Certificate of Incorporation, Articles of Incorporation, Bylaws)
- Board/Shareholder Minutes (Meeting Minutes, Written Consent, Board Resolutions)
- Stock Purchase Agreement (Stock issuance agreements, subscription agreements)
- SAFE (Simple Agreement for Future Equity)
- Convertible Note (Convertible debt instruments)
- Option Grant Agreement (Stock option grants, RSU agreements)
- Equity Incentive Plan (Stock option plans, equity compensation plans)
- Financial Statement (Balance sheets, income statements, cap tables)
- Employment Agreement (Employment contracts, offer letters)
- Other (anything that doesn't fit above)

INSTRUCTIONS:
1. Classify the document into ONE category from the list above
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


ISSUE_TRACKER_PROMPT = """You are auditing corporate governance records for issues and inconsistencies.

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

Identify potential issues such as:
1. Missing foundational documents (Charter, Bylaws if no Charter found, Board Minutes)
2. Issued shares exceeding authorized shares
3. Stock classes in agreements not mentioned in Charter
4. Board meetings without proper documentation
5. SAFEs without clear conversion terms
6. Inconsistent or conflicting information

For each issue:
- severity: "critical", "warning", or "note"
- category: Brief category label (e.g., "Missing Document", "Share Count Mismatch")
- description: Clear description of the issue

Respond ONLY with valid JSON (array of issues):
[{{"severity": "...", "category": "...", "description": "..."}}]

If no issues found, return empty array: []"""


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
