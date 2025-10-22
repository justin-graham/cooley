"""
AI Processing Pipeline - Orchestrates 3-pass document analysis using Claude.

Pass 1: Classify each document by type
Pass 2: Extract structured data from each document based on its type
Pass 3: Synthesize cross-document insights (timeline, cap table, issues)
"""

import os
import json
import logging
import time
from typing import List, Dict, Any
from anthropic import Anthropic, APITimeoutError, APIError, RateLimitError
from app import db, prompts

logger = logging.getLogger(__name__)


def clean_text_for_db(text: str) -> str:
    """
    Clean text to remove characters that break PostgreSQL JSONB storage.

    Args:
        text: Input text string

    Returns:
        Cleaned text safe for PostgreSQL
    """
    if not isinstance(text, str):
        return text
    # Remove NULL bytes and other control characters that break PostgreSQL
    return text.replace('\x00', '').replace('\r', '\n')


def clean_document_dict(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively clean all text fields in a document dictionary.

    Args:
        doc: Document dictionary

    Returns:
        Cleaned document dictionary
    """
    cleaned = {}
    for key, value in doc.items():
        if isinstance(value, str):
            cleaned[key] = clean_text_for_db(value)
        elif isinstance(value, dict):
            cleaned[key] = clean_document_dict(value)
        elif isinstance(value, list):
            cleaned[key] = [clean_document_dict(item) if isinstance(item, dict) else clean_text_for_db(item) if isinstance(item, str) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


# Initialize Claude client with 60 second timeout
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=60.0)


def call_claude(prompt: str, max_tokens: int = 2048) -> str:
    """
    Call Claude API with a prompt and return the response text.

    Args:
        prompt: The prompt to send
        max_tokens: Maximum tokens in response

    Returns:
        Response text from Claude

    Raises:
        APITimeoutError: If the request times out (60 seconds)
        APIError: If there's an API error
    """
    try:
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        return message.content[0].text

    except APITimeoutError as e:
        logger.error(f"Claude API timeout after 60 seconds: {e}")
        raise
    except APIError as e:
        logger.error(f"Claude API error: {e}")
        raise


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


def extract_repurchase_data(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Extract data from Share Repurchase Agreements."""
    try:
        prompt = prompts.SHARE_REPURCHASE_EXTRACTION_PROMPT.format(text=doc['text'][:15000])
        response = call_claude(prompt, max_tokens=1024)
        repurchase = parse_json_response(response)
        # Make shares negative to subtract from cap table
        if 'shares' in repurchase and isinstance(repurchase['shares'], (int, float)):
            repurchase['shares'] = -abs(repurchase['shares'])
        return repurchase
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
    elif 'Repurchase' in category:
        return {'repurchase_data': extract_repurchase_data(doc)}
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

        # Call Claude - if rate limited, immediately return fallback (no retry)
        response = call_claude(prompt, max_tokens=4096)

        timeline = parse_json_response(response)

        # Sort by date
        timeline.sort(key=lambda x: x.get('date', ''))

        return timeline

    except RateLimitError as e:
        logger.warning(f"Timeline synthesis rate limited, returning partial data: {e}")
        print(f"WARNING: Timeline synthesis rate limited, returning partial data")
        return [{'date': '', 'event_type': 'info', 'description': 'Timeline synthesis rate limited - showing partial data', 'source_docs': []}]
    except Exception as e:
        logger.error(f"Timeline synthesis failed: {e}", exc_info=True)
        print(f"ERROR: Timeline synthesis failed: {e}")
        return [{'date': '', 'event_type': 'error', 'description': f'Timeline generation failed: {str(e)}', 'source_docs': []}]


def build_raw_cap_table(equity_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build a basic cap table from raw equity data without AI synthesis.
    Used as fallback when Claude API is rate limited.

    Args:
        equity_data: List of equity issuances

    Returns:
        List of cap table entries with calculated ownership percentages
    """
    # Aggregate by shareholder and share class
    aggregated = {}
    for item in equity_data:
        shareholder = item.get('shareholder') or item.get('investor') or item.get('recipient') or 'Unknown'
        shares = item.get('shares', 0)
        share_class = item.get('share_class') or item.get('type', 'Common Stock')

        key = (shareholder, share_class)
        if key not in aggregated:
            aggregated[key] = 0

        # Add shares (handles positive issuances)
        if isinstance(shares, (int, float)):
            aggregated[key] += shares

    # Remove entries with 0 or negative shares
    aggregated = {k: v for k, v in aggregated.items() if v > 0}

    # Calculate total shares for ownership percentage
    total_shares = sum(aggregated.values())

    # Convert to cap table format with ownership %
    cap_table = [
        {
            'shareholder': shareholder,
            'shares': shares,
            'share_class': share_class,
            'ownership_pct': round((shares / total_shares * 100), 2) if total_shares > 0 else 0.0
        }
        for (shareholder, share_class), shares in aggregated.items()
    ]

    # Sort by ownership percentage descending
    cap_table.sort(key=lambda x: x['ownership_pct'], reverse=True)

    return cap_table


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
            if 'repurchase_data' in doc:
                repurchase = doc['repurchase_data']
                if not repurchase.get('error'):
                    # Add repurchase with negative shares to reduce cap table
                    equity_data.append({
                        'shareholder': repurchase.get('shareholder'),
                        'shares': repurchase.get('shares'),  # Already negative from extraction
                        'share_class': repurchase.get('share_class', 'Common Stock'),
                        'date': repurchase.get('date')
                    })

        if not equity_data:
            return []

        # Build raw cap table as fallback
        raw_cap_table = build_raw_cap_table(equity_data)

        equity_json = json.dumps(equity_data, indent=2)
        prompt = prompts.CAP_TABLE_SYNTHESIS_PROMPT.format(equity_data_json=equity_json)

        # Add small delay to spread API load
        time.sleep(2)

        # Call Claude - if rate limited, immediately return raw cap table (no retry)
        response = call_claude(prompt, max_tokens=4096)

        cap_table = parse_json_response(response)

        return cap_table

    except RateLimitError as e:
        logger.warning(f"Cap table synthesis rate limited, returning raw equity data: {e}")
        print(f"WARNING: Cap table synthesis rate limited, returning raw equity data with TBD percentages")
        return raw_cap_table  # Return raw data instead of empty array
    except Exception as e:
        logger.error(f"Cap table synthesis failed: {e}", exc_info=True)
        print(f"ERROR: Cap table synthesis failed: {e}")
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

        # Add small delay to spread API load
        time.sleep(2)

        # Call Claude - if rate limited, immediately return fallback message (no retry)
        response = call_claude(prompt, max_tokens=4096)

        issues = parse_json_response(response)

        return issues

    except RateLimitError as e:
        logger.warning(f"Issue generation rate limited, returning fallback message: {e}")
        print(f"WARNING: Issue generation rate limited - manual review recommended")
        return [{'severity': 'warning', 'category': 'Rate Limit', 'description': 'Issue analysis rate limited - manual document review recommended'}]
    except Exception as e:
        logger.error(f"Issue generation failed: {e}", exc_info=True)
        print(f"ERROR: Issue generation failed: {e}")
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
        logger.info(f"Starting 3-pass processing for {total_docs} documents")

        # ========== PASS 1: CLASSIFICATION ==========
        try:
            db.update_progress(audit_id, "Pass 1: Classifying documents...")
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
            print(f"ERROR: Failed to update progress: {e}")

        classified_docs = []
        for i, doc in enumerate(documents, start=1):
            try:
                db.update_progress(audit_id, f"Pass 1: Classifying documents... {i}/{total_docs}")
            except Exception as e:
                logger.error(f"Failed to update progress: {e}")

            # Log which document is being classified
            logger.info(f"Classifying document {i}/{total_docs}: {doc.get('filename', 'unknown')}")

            classified_doc = classify_document(doc)
            classified_docs.append(classified_doc)

        logger.info(f"Pass 1 complete: Classified {total_docs} documents")

        # ========== PASS 2: EXTRACTION ==========
        try:
            db.update_progress(audit_id, "Pass 2: Extracting structured data...")
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
            print(f"ERROR: Failed to update progress: {e}")

        extractions = []
        for i, doc in enumerate(classified_docs, start=1):
            if doc.get('error'):
                extractions.append(doc)
                continue

            try:
                db.update_progress(audit_id, f"Pass 2: Extracting data... {i}/{total_docs}")
            except Exception as e:
                logger.error(f"Failed to update progress: {e}")

            extracted_data = extract_by_type(doc)
            extractions.append({**doc, **extracted_data})

        logger.info(f"Pass 2 complete: Extracted data from {total_docs} documents")

        # ========== PASS 3: SYNTHESIS ==========
        try:
            db.update_progress(audit_id, "Pass 3: Synthesizing timeline...")
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
            print(f"ERROR: Failed to update progress: {e}")

        timeline = synthesize_timeline(extractions)

        try:
            db.update_progress(audit_id, "Pass 3: Synthesizing cap table...")
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")

        cap_table = synthesize_cap_table(extractions)

        try:
            db.update_progress(audit_id, "Pass 3: Synthesizing issues...")
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")

        issues = generate_issues(classified_docs, cap_table, timeline)

        try:
            db.update_progress(audit_id, "Pass 3: Finalizing report...")
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")

        company_name = extract_company_name(extractions)

        logger.info(f"Pass 3 complete: Generated timeline, cap table, and issues")

        # ========== SAVE RESULTS ==========
        failed_docs = [d for d in classified_docs if d.get('error')]

        # Clean all document text to remove NULL bytes and control characters
        cleaned_docs = [clean_document_dict(doc) for doc in classified_docs]
        cleaned_failed_docs = [clean_document_dict(doc) for doc in failed_docs]

        db.update_audit_results(audit_id, {
            'company_name': company_name,
            'documents': cleaned_docs,
            'timeline': timeline,
            'cap_table': cap_table,
            'issues': issues,
            'failed_documents': cleaned_failed_docs
        })

        logger.info(f"Audit {audit_id} completed successfully")

    except Exception as e:
        logger.error(f"Processing error in audit {audit_id}: {e}", exc_info=True)
        print(f"ERROR: Processing failed for audit {audit_id}: {e}")
        try:
            db.mark_error(audit_id, str(e))
        except Exception as db_error:
            logger.error(f"Failed to mark error in database: {db_error}")
            print(f"CRITICAL: Failed to mark error in database: {db_error}")
