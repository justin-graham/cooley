"""
AI Processing Pipeline - Orchestrates 3-pass document analysis using Claude.

Pass 1: Classify each document by type
Pass 2: Extract structured data from each document based on its type
Pass 3: Synthesize cross-document insights (timeline, cap table, issues)
"""

import os
import json
from typing import List, Dict, Any
from anthropic import Anthropic
from app import db, prompts


# Initialize Claude client
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def call_claude(prompt: str, max_tokens: int = 2048) -> str:
    """
    Call Claude API with a prompt and return the response text.

    Args:
        prompt: The prompt to send
        max_tokens: Maximum tokens in response

    Returns:
        Response text from Claude
    """
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    return message.content[0].text


def parse_json_response(response_text: str) -> Any:
    """
    Parse JSON from Claude's response, handling potential markdown wrapping.

    Args:
        response_text: Raw response from Claude

    Returns:
        Parsed JSON object (dict or list)
    """
    # Remove markdown code block formatting if present
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]  # Remove ```json
    if text.startswith("```"):
        text = text[3:]  # Remove ```
    if text.endswith("```"):
        text = text[:-3]  # Remove closing ```

    return json.loads(text.strip())


# ============================================================================
# PASS 1: CLASSIFICATION
# ============================================================================

def classify_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify a document into a type category.

    Args:
        doc: Document dict with 'text' field

    Returns:
        Updated doc dict with 'category' and 'summary' fields
    """
    if doc.get('error'):
        # Skip documents that failed to parse
        doc['category'] = 'Other'
        doc['summary'] = 'Failed to parse document'
        return doc

    try:
        # Use first 10,000 chars for classification (enough for most docs)
        text_sample = doc['text'][:10000]

        prompt = prompts.CLASSIFICATION_PROMPT.format(text=text_sample)
        response = call_claude(prompt, max_tokens=512)

        result = parse_json_response(response)
        doc['category'] = result.get('doc_type', 'Other')
        doc['summary'] = result.get('summary', 'No summary available')

    except Exception as e:
        # If classification fails, default to "Other"
        doc['category'] = 'Other'
        doc['summary'] = f'Classification failed: {str(e)}'

    return doc


# ============================================================================
# PASS 2: EXTRACTION (by document type)
# ============================================================================

def extract_charter_data(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Extract data from Charter documents."""
    try:
        prompt = prompts.CHARTER_EXTRACTION_PROMPT.format(text=doc['text'][:20000])
        response = call_claude(prompt, max_tokens=1024)
        return parse_json_response(response)
    except Exception as e:
        return {'error': str(e)}


def extract_stock_data(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract equity issuances from Stock Purchase Agreements."""
    try:
        prompt = prompts.STOCK_EXTRACTION_PROMPT.format(text=doc['text'][:20000])
        response = call_claude(prompt, max_tokens=2048)
        return parse_json_response(response)
    except Exception as e:
        return []


def extract_safe_data(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Extract data from SAFE documents."""
    try:
        prompt = prompts.SAFE_EXTRACTION_PROMPT.format(text=doc['text'][:15000])
        response = call_claude(prompt, max_tokens=1024)
        return parse_json_response(response)
    except Exception as e:
        return {'error': str(e)}


def extract_board_minutes_data(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Extract data from Board/Shareholder Minutes."""
    try:
        prompt = prompts.BOARD_MINUTES_EXTRACTION_PROMPT.format(text=doc['text'][:15000])
        response = call_claude(prompt, max_tokens=1024)
        return parse_json_response(response)
    except Exception as e:
        return {'error': str(e)}


def extract_option_grant_data(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Extract data from Option Grant Agreements."""
    try:
        prompt = prompts.OPTION_GRANT_EXTRACTION_PROMPT.format(text=doc['text'][:15000])
        response = call_claude(prompt, max_tokens=1024)
        return parse_json_response(response)
    except Exception as e:
        return {'error': str(e)}


def extract_by_type(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route document to appropriate extraction function based on category.

    Args:
        doc: Document with 'category' field

    Returns:
        Dictionary with extracted data
    """
    category = doc.get('category', 'Other')

    if 'Charter' in category:
        return {'charter_data': extract_charter_data(doc)}
    elif 'Stock Purchase' in category:
        return {'stock_issuances': extract_stock_data(doc)}
    elif 'SAFE' in category:
        return {'safe_data': extract_safe_data(doc)}
    elif 'Minutes' in category:
        return {'minutes_data': extract_board_minutes_data(doc)}
    elif 'Option Grant' in category:
        return {'option_data': extract_option_grant_data(doc)}
    else:
        return {}


# ============================================================================
# PASS 3: SYNTHESIS
# ============================================================================

def synthesize_timeline(extractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate a chronological timeline from all extracted data.

    Args:
        extractions: List of documents with extracted data

    Returns:
        Sorted list of timeline events
    """
    try:
        extractions_json = json.dumps(extractions, indent=2)
        prompt = prompts.TIMELINE_SYNTHESIS_PROMPT.format(extractions_json=extractions_json)
        response = call_claude(prompt, max_tokens=4096)

        timeline = parse_json_response(response)

        # Sort by date
        timeline.sort(key=lambda x: x.get('date', ''))

        return timeline

    except Exception as e:
        return [{'date': '', 'event_type': 'error', 'description': f'Timeline generation failed: {str(e)}', 'source_docs': []}]


def synthesize_cap_table(extractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate a cap table from equity issuance data.

    Args:
        extractions: List of documents with extracted data

    Returns:
        List of cap table entries with ownership percentages
    """
    try:
        # Collect all equity-related extractions
        equity_data = []

        for doc in extractions:
            if 'stock_issuances' in doc:
                equity_data.extend(doc['stock_issuances'])
            if 'safe_data' in doc:
                safe = doc['safe_data']
                if not safe.get('error'):
                    equity_data.append({
                        'shareholder': safe.get('investor'),
                        'amount': safe.get('amount'),
                        'type': 'SAFE',
                        'date': safe.get('date')
                    })
            if 'option_data' in doc:
                option = doc['option_data']
                if not option.get('error'):
                    equity_data.append({
                        'shareholder': option.get('recipient'),
                        'shares': option.get('shares'),
                        'type': 'Option',
                        'date': option.get('grant_date')
                    })

        if not equity_data:
            return []

        equity_json = json.dumps(equity_data, indent=2)
        prompt = prompts.CAP_TABLE_SYNTHESIS_PROMPT.format(equity_data_json=equity_json)
        response = call_claude(prompt, max_tokens=4096)

        cap_table = parse_json_response(response)

        return cap_table

    except Exception as e:
        return [{'shareholder': 'Error', 'shares': 0, 'share_class': 'N/A', 'ownership_pct': 0.0}]


def generate_issues(documents: List[Dict[str, Any]], cap_table: List[Dict[str, Any]], timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate an issue tracker by analyzing documents for gaps and inconsistencies.

    Args:
        documents: List of classified documents
        cap_table: Generated cap table
        timeline: Generated timeline

    Returns:
        List of issues with severity and descriptions
    """
    try:
        # Prepare summaries for Claude
        doc_summary = [{'filename': d['filename'], 'category': d.get('category', 'Other')} for d in documents]

        documents_json = json.dumps(doc_summary, indent=2)
        cap_table_json = json.dumps(cap_table, indent=2)
        timeline_json = json.dumps(timeline, indent=2)

        prompt = prompts.ISSUE_TRACKER_PROMPT.format(
            documents_json=documents_json,
            cap_table_json=cap_table_json,
            timeline_json=timeline_json
        )

        response = call_claude(prompt, max_tokens=4096)
        issues = parse_json_response(response)

        return issues

    except Exception as e:
        return [{'severity': 'critical', 'category': 'System Error', 'description': f'Issue analysis failed: {str(e)}'}]


def extract_company_name(extractions: List[Dict[str, Any]]) -> str:
    """
    Extract company name from charter documents.

    Args:
        extractions: List of documents with extracted data

    Returns:
        Company name string, or "Unknown Company" if not found
    """
    try:
        # Find charter documents
        charter_docs = [doc for doc in extractions if 'charter_data' in doc]

        if not charter_docs:
            return "Unknown Company"

        # Try to get company name from charter data
        for doc in charter_docs:
            charter_data = doc.get('charter_data', {})
            company_name = charter_data.get('company_name')
            if company_name:
                return company_name

        # If not found in structured data, ask Claude to extract it
        charter_texts = '\n\n---\n\n'.join([doc['text'][:5000] for doc in charter_docs if 'text' in doc])
        prompt = prompts.COMPANY_NAME_EXTRACTION_PROMPT.format(charter_texts=charter_texts)
        response = call_claude(prompt, max_tokens=256)

        return response.strip() or "Unknown Company"

    except Exception:
        return "Unknown Company"


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

async def process_audit(audit_id: str, documents: List[Dict[str, Any]]):
    """
    Main orchestrator for the 3-pass AI audit pipeline.

    Args:
        audit_id: UUID of the audit
        documents: List of parsed documents with 'filename', 'type', 'text' fields
    """
    try:
        total_docs = len(documents)

        # ========== PASS 1: CLASSIFICATION ==========
        db.update_progress(audit_id, "Pass 1: Classifying documents...")

        classified_docs = []
        for i, doc in enumerate(documents, start=1):
            db.update_progress(audit_id, f"Classifying document {i}/{total_docs}: {doc['filename']}")
            classified_doc = classify_document(doc)
            classified_docs.append(classified_doc)

        # ========== PASS 2: EXTRACTION ==========
        db.update_progress(audit_id, "Pass 2: Extracting structured data...")

        extractions = []
        for i, doc in enumerate(classified_docs, start=1):
            if doc.get('error'):
                extractions.append(doc)
                continue

            db.update_progress(audit_id, f"Extracting data from document {i}/{total_docs}: {doc['filename']}")

            extracted_data = extract_by_type(doc)
            extractions.append({**doc, **extracted_data})

        # ========== PASS 3: SYNTHESIS ==========
        db.update_progress(audit_id, "Pass 3: Building timeline...")
        timeline = synthesize_timeline(extractions)

        db.update_progress(audit_id, "Pass 3: Generating cap table...")
        cap_table = synthesize_cap_table(extractions)

        db.update_progress(audit_id, "Pass 3: Analyzing for issues...")
        issues = generate_issues(classified_docs, cap_table, timeline)

        db.update_progress(audit_id, "Extracting company name...")
        company_name = extract_company_name(extractions)

        # ========== SAVE RESULTS ==========
        failed_docs = [d for d in classified_docs if d.get('error')]

        db.update_audit_results(audit_id, {
            'company_name': company_name,
            'documents': classified_docs,
            'timeline': timeline,
            'cap_table': cap_table,
            'issues': issues,
            'failed_documents': failed_docs
        })

    except Exception as e:
        db.mark_error(audit_id, str(e))
