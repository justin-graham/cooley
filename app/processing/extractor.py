"""Pass 2: Type-specific data extraction with verification, transaction extraction, and approval matching."""

import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

from app import prompts
from app.processing.claude_client import call_claude, parse_json_response
from app.processing.models import (
    APPROVAL_DOC_TYPES, format_text_with_paragraphs, normalize_compliance_status,
)
from app.processing.previews import generate_and_store_preview

logger = logging.getLogger(__name__)

DATE_FIELDS = frozenset({
    'date', 'incorporation_date', 'grant_date', 'meeting_date',
    'maturity_date', 'issuance_date', 'repurchase_date',
})
NUMERIC_FIELDS = frozenset({
    'shares', 'shares_issued', 'shares_granted', 'shares_repurchased',
    'price_per_share', 'strike_price', 'amount', 'investment_amount',
    'principal', 'authorized_shares', 'valuation_cap', 'discount_rate',
    'interest_rate', 'total_amount',
})
_DATE_FORMATS = ('%Y-%m-%d', '%m/%d/%Y', '%B %d, %Y', '%b %d, %Y', '%Y/%m/%d')


def sanitize_extraction(data: dict) -> dict:
    """Validate and coerce extracted field types after Claude parsing.

    - Dates must be valid ISO (YYYY-MM-DD); common formats auto-converted.
    - Numeric fields stripped of '$', ',', whitespace and coerced to int/float.
    - Invalid values set to None with warnings recorded.
    """
    if not isinstance(data, dict):
        return data
    warnings = []

    for field in DATE_FIELDS:
        if field not in data or data[field] is None:
            continue
        val = str(data[field]).strip()
        parsed = None
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(val, fmt)
                break
            except ValueError:
                continue
        if parsed:
            data[field] = parsed.strftime('%Y-%m-%d')
        else:
            warnings.append(f"Invalid date '{val}' for '{field}' — removed")
            data[field] = None

    for field in NUMERIC_FIELDS:
        if field not in data or data[field] is None:
            continue
        val = data[field]
        if isinstance(val, (int, float)):
            continue
        if isinstance(val, str):
            cleaned = val.replace('$', '').replace(',', '').replace(' ', '').strip()
            try:
                data[field] = int(cleaned) if '.' not in cleaned else float(cleaned)
            except (ValueError, TypeError):
                warnings.append(f"Non-numeric '{val}' for '{field}' — removed")
                data[field] = None
        else:
            warnings.append(f"Unexpected type {type(val).__name__} for '{field}' — removed")
            data[field] = None

    if warnings:
        data['_validation_warnings'] = warnings
        logger.warning(f"Sanitization warnings: {warnings}")
    return data


# --- Verification ---

def verify_extraction(source_text: str, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    warnings = []
    verifications = 0
    total_checks = 0
    normalized_text = ' '.join(source_text.lower().split())

    # Numeric fields — penalize null/empty values present in extraction
    for field in ['shares', 'amount', 'principal', 'authorized_shares', 'valuation_cap']:
        if field in extracted_data:
            total_checks += 1
            if not extracted_data[field]:
                warnings.append(f"Field '{field}' present but empty/null")
                continue
            value = extracted_data[field]
            if isinstance(value, (int, float)):
                patterns = [str(int(value)), f"{int(value):,}", f"{value:.2f}"]
                if any(p.replace(',', '') in normalized_text.replace(',', '') for p in patterns):
                    verifications += 1
                else:
                    warnings.append(f"{field}={value} not found in source text")

    # Text fields — penalize null/empty values present in extraction
    for field in ['shareholder', 'investor', 'recipient', 'company_name']:
        if field in extracted_data:
            total_checks += 1
            if not extracted_data[field]:
                warnings.append(f"Field '{field}' present but empty/null")
                continue
            value = str(extracted_data[field]).lower()
            if value in normalized_text:
                verifications += 1
            else:
                name_parts = value.split()
                if len(name_parts) > 1 and all(part in normalized_text for part in name_parts):
                    verifications += 1
                else:
                    warnings.append(f"{field}='{extracted_data[field]}' not found in source text")

    # Date fields — penalize null/empty values present in extraction
    for field in ['date', 'incorporation_date', 'grant_date', 'meeting_date', 'maturity_date']:
        if field in extracted_data:
            total_checks += 1
            if not extracted_data[field]:
                warnings.append(f"Field '{field}' present but empty/null")
                continue
            try:
                dt = datetime.strptime(extracted_data[field], '%Y-%m-%d')
                year_found = str(dt.year) in normalized_text
                month_found = dt.strftime('%B').lower() in normalized_text or str(dt.month) in normalized_text
                day_found = str(dt.day) in normalized_text
                if year_found and (month_found or day_found):
                    verifications += 1
                else:
                    warnings.append(f"{field}={extracted_data[field]} not clearly found in source text")
            except ValueError:
                warnings.append(f"Field '{field}' has unparseable date: {extracted_data[field]}")

    confidence = int((verifications / total_checks * 100)) if total_checks > 0 else 0
    return {
        'confidence_score': confidence,
        'verified_fields': verifications,
        'total_checks': total_checks,
        'warnings': warnings if warnings else None,
    }


# --- Shared extraction helper ---

def _extract(doc, prompt_template, text_limit=15000, use_paragraphs=False, verify=True, max_tokens=1024):
    """Shared extraction: format text -> prompt -> Claude -> parse -> verify."""
    try:
        text = doc['text'][:text_limit]
        if use_paragraphs:
            text = format_text_with_paragraphs(text)
        prompt = prompt_template.format(text=text)
        response = call_claude(prompt, max_tokens=max_tokens)
        result = parse_json_response(response)
        result = sanitize_extraction(result)
        result['source_doc'] = doc['filename']

        if verify:
            verification = verify_extraction(doc['text'][:text_limit], result)
            result['verification'] = verification
            if verification['confidence_score'] < 70:
                logger.warning(f"Low confidence ({verification['confidence_score']}%) for {doc['filename']}")
                result['low_confidence'] = True
                result['confidence_warning'] = (
                    f"Low confidence ({verification['confidence_score']}%) for {doc['filename']}. Manual review recommended."
                )
        return result
    except Exception as e:
        return {'error': str(e), 'source_doc': doc['filename']}


def extract_charter_data(doc):
    return _extract(doc, prompts.CHARTER_EXTRACTION_PROMPT, text_limit=20000)


def extract_stock_data(doc) -> List[Dict[str, Any]]:
    """Extract equity issuances — returns a list. Verifies each issuance individually."""
    try:
        formatted_text = format_text_with_paragraphs(doc['text'][:20000])
        prompt = prompts.STOCK_EXTRACTION_PROMPT.format(text=formatted_text)
        response = call_claude(prompt, max_tokens=2048)
        issuances = parse_json_response(response)

        # Guard against Claude returning an object instead of array
        if isinstance(issuances, dict):
            issuances = [issuances]
        issuances = [sanitize_extraction(i) for i in issuances if isinstance(i, dict)]

        for issuance in issuances:
            issuance['source_doc'] = doc['filename']
            verification = verify_extraction(doc['text'][:20000], issuance)
            issuance['verification'] = verification
            if verification['confidence_score'] < 70:
                logger.warning(f"Low confidence stock ({verification['confidence_score']}%) for {doc['filename']}")
                issuance['low_confidence'] = True
                issuance['confidence_warning'] = (
                    f"Low confidence ({verification['confidence_score']}%) for {doc['filename']}. Manual review recommended."
                )
        return issuances
    except Exception as e:
        logger.error(f"Stock extraction failed for {doc.get('filename', 'unknown')}: {e}")
        return [{'error': str(e), 'source_doc': doc.get('filename', 'unknown')}]


def extract_safe_data(doc):
    return _extract(doc, prompts.SAFE_EXTRACTION_PROMPT, use_paragraphs=True)


def extract_convertible_note_data(doc):
    return _extract(doc, prompts.CONVERTIBLE_NOTE_EXTRACTION_PROMPT, verify=True)


def extract_board_minutes_data(doc):
    return _extract(doc, prompts.BOARD_MINUTES_EXTRACTION_PROMPT, verify=False)


def extract_option_grant_data(doc):
    return _extract(doc, prompts.OPTION_GRANT_EXTRACTION_PROMPT, use_paragraphs=True)


def extract_repurchase_data(doc):
    result = _extract(doc, prompts.SHARE_REPURCHASE_EXTRACTION_PROMPT, use_paragraphs=True)
    # Make shares negative for cap table subtraction
    if 'shares' in result and isinstance(result['shares'], (int, float)):
        result['shares'] = -abs(result['shares'])
    logger.info(
        f"Repurchase from {doc.get('filename', 'unknown')}: "
        f"shareholder='{result.get('shareholder')}', shares={result.get('shares')}"
    )
    return result


# --- Type router ---

def extract_by_type(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Route document to appropriate extraction function and generate preview."""
    category = doc.get('category', 'Other')

    # Route to extraction function
    if 'Charter' in category:
        result = {'charter_data': extract_charter_data(doc)}
    elif 'Stock Purchase' in category:
        result = {'stock_issuances': extract_stock_data(doc)}
    elif 'SAFE' in category:
        result = {'safe_data': extract_safe_data(doc)}
    elif 'Convertible Note' in category:
        result = {'convertible_note_data': extract_convertible_note_data(doc)}
    elif 'Minutes' in category:
        result = {'minutes_data': extract_board_minutes_data(doc)}
    elif 'Option Grant' in category:
        result = {'option_data': extract_option_grant_data(doc)}
    elif 'Repurchase' in category:
        result = {'repurchase_data': extract_repurchase_data(doc)}
    else:
        result = {}

    # Generate preview for equity documents
    if any(kw in category for kw in ['Stock Purchase', 'Option Grant', 'SAFE', 'Repurchase']):
        _attach_preview(doc, result, category)

    return result


def _attach_preview(doc: Dict[str, Any], result: Dict[str, Any], category: str):
    """Generate preview screenshot and event summary for equity documents."""
    pdf_path = doc.get('pdf_path')
    text_spans = doc.get('text_spans')
    doc_id = doc.get('id')

    # Find the right extracted data payload
    extracted_data = None
    if 'Stock Purchase' in category and result.get('stock_issuances'):
        issuances = [i for i in result['stock_issuances'] if isinstance(i, dict)]
        if issuances:
            extracted_data = next(
                (i for i in issuances if i.get('shares') or i.get('price_per_share') or i.get('shareholder')),
                issuances[0],
            )
    else:
        data_key = next((k for k in result.keys() if k.endswith('_data')), None)
        extracted_data = result.get(data_key) if data_key else None

    if not extracted_data or extracted_data.get('error'):
        return

    # Generate preview
    if pdf_path and text_spans and doc_id:
        preview_base64, focus_y = generate_and_store_preview(doc_id, pdf_path, extracted_data, text_spans)
        if preview_base64:
            result['preview_image'] = preview_base64
        if focus_y is not None:
            result['preview_focus_y'] = focus_y

    # Generate summary
    event_type_map = {
        'Stock Purchase': 'stock_issuance', 'Option Grant': 'option_grant',
        'SAFE': 'safe', 'Repurchase': 'repurchase',
    }
    event_type = next((v for k, v in event_type_map.items() if k in category), 'unknown')
    result['summary'] = generate_event_summary(extracted_data, event_type)


def generate_event_summary(extracted_data: Dict[str, Any], event_type: str) -> str:
    shareholder = extracted_data.get('shareholder') or extracted_data.get('recipient') or extracted_data.get('investor') or 'Unknown party'
    shares = extracted_data.get('shares') or extracted_data.get('shares_issued')
    share_class = extracted_data.get('share_type') or extracted_data.get('share_class') or 'Common'
    price = extracted_data.get('price_per_share')
    date = extracted_data.get('date') or extracted_data.get('issuance_date') or extracted_data.get('grant_date') or 'Unknown date'

    display_shares = abs(shares) if isinstance(shares, (int, float)) and event_type == 'repurchase' else shares
    shares_str = f"{int(display_shares):,}" if display_shares else "unspecified"
    price_str = f"${price:.4f}" if price else "unspecified price"

    if event_type == 'stock_issuance':
        return f"{shareholder} received {shares_str} {share_class} shares at {price_str} per share on {date}"
    elif event_type == 'option_grant':
        return f"{shareholder} granted {shares_str} {share_class} options at {price_str} strike price on {date}"
    elif event_type == 'safe':
        amount = extracted_data.get('amount') or extracted_data.get('investment_amount')
        amount_str = f"${amount:,}" if amount else "unspecified amount"
        return f"{shareholder} invested {amount_str} via SAFE on {date}"
    elif event_type == 'repurchase':
        return f"Company repurchased {shares_str} {share_class} shares from {shareholder} on {date}"
    return f"{shareholder} - {shares_str} shares on {date}"


# --- Transaction extraction (Pass 2A) ---

def _warn_incomplete(data_warnings, doc_type, filename, required_fields, data):
    """Record a data-loss warning when required fields are missing from an extraction."""
    missing = [f for f in required_fields if not data.get(f)]
    if not missing:
        return False
    partial = {k: v for k, v in data.items()
               if k not in ('source_doc', 'verification', 'low_confidence', 'confidence_warning', '_validation_warnings', 'error')
               and v is not None}
    data_warnings.append({
        'severity': 'warning', 'category': 'Incomplete Extraction',
        'description': (
            f"{doc_type} from '{filename}' excluded from cap table — "
            f"missing: {', '.join(missing)}. Partial data: {partial}"
        ),
        'source_doc': filename,
    })
    return True


def extract_equity_transactions(extractions: List[Dict[str, Any]]):
    """Structure extracted data into equity_events table format.

    Returns (transactions, data_warnings) where data_warnings contains issues
    for any transactions that were dropped due to incomplete extraction.
    """
    transactions = []
    data_warnings = []

    for doc in extractions:
        doc_id = doc.get('document_id')
        filename = doc.get('filename', 'unknown')

        if 'stock_issuances' in doc:
            for issuance in doc['stock_issuances']:
                if not isinstance(issuance, dict) or issuance.get('error'):
                    continue
                if _warn_incomplete(data_warnings, 'Stock issuance', filename, ('date', 'shareholder', 'shares'), issuance):
                    continue
                shares = issuance['shares']
                if not isinstance(shares, (int, float, Decimal)):
                    data_warnings.append({
                        'severity': 'warning', 'category': 'Incomplete Extraction',
                        'description': f"Stock issuance from '{filename}' has non-numeric shares ({shares!r}) — excluded.",
                        'source_doc': filename,
                    })
                    continue
                tx_details = {'price_per_share': issuance.get('price_per_share'), 'verification': issuance.get('verification')}
                if doc.get('preview_focus_y') is not None:
                    tx_details['preview_focus_y'] = doc['preview_focus_y']
                transactions.append({
                    'event_date': issuance['date'], 'event_type': 'issuance',
                    'shareholder_name': issuance['shareholder'],
                    'share_class': issuance.get('share_class', 'Common Stock'),
                    'share_delta': abs(shares),
                    'source_doc_id': doc_id,
                    'source_snippet': issuance.get('source_quote', f"{issuance['shareholder']} - {issuance['shares']} shares"),
                    'preview_image': doc.get('preview_image'),
                    'summary': doc.get('summary'), 'details': tx_details,
                })

        if 'safe_data' in doc:
            safe = doc['safe_data']
            if not safe.get('error'):
                if not _warn_incomplete(data_warnings, 'SAFE', filename, ('date', 'investor'), safe):
                    tx_details = {'amount': safe.get('amount'), 'valuation_cap': safe.get('valuation_cap'), 'discount_rate': safe.get('discount_rate')}
                    if doc.get('preview_focus_y') is not None:
                        tx_details['preview_focus_y'] = doc['preview_focus_y']
                    transactions.append({
                        'event_date': safe['date'], 'event_type': 'safe',
                        'shareholder_name': safe['investor'], 'share_class': 'SAFE', 'share_delta': 0,
                        'source_doc_id': doc_id,
                        'source_snippet': safe.get('source_quote', f"SAFE investment by {safe['investor']}"),
                        'preview_image': doc.get('preview_image'),
                        'summary': doc.get('summary'), 'details': tx_details,
                    })

        if 'convertible_note_data' in doc:
            note = doc['convertible_note_data']
            if not note.get('error'):
                if not _warn_incomplete(data_warnings, 'Convertible note', filename, ('date', 'investor'), note):
                    tx_details = {
                        'principal': note.get('principal'), 'interest_rate': note.get('interest_rate'),
                        'maturity_date': note.get('maturity_date'), 'valuation_cap': note.get('valuation_cap'),
                        'discount_rate': note.get('discount_rate'),
                    }
                    if doc.get('preview_focus_y') is not None:
                        tx_details['preview_focus_y'] = doc['preview_focus_y']
                    transactions.append({
                        'event_date': note['date'], 'event_type': 'convertible_note',
                        'shareholder_name': note['investor'], 'share_class': 'Convertible Note', 'share_delta': 0,
                        'source_doc_id': doc_id,
                        'source_snippet': note.get('source_quote', f"Convertible note from {note['investor']}"),
                        'preview_image': doc.get('preview_image'),
                        'summary': doc.get('summary'), 'details': tx_details,
                    })

        if 'option_data' in doc:
            option = doc['option_data']
            if not option.get('error'):
                if not _warn_incomplete(data_warnings, 'Option grant', filename, ('grant_date', 'recipient'), option):
                    tx_details = {'strike_price': option.get('strike_price'), 'vesting_schedule': option.get('vesting_schedule')}
                    if doc.get('preview_focus_y') is not None:
                        tx_details['preview_focus_y'] = doc['preview_focus_y']
                    transactions.append({
                        'event_date': option['grant_date'], 'event_type': 'option_grant',
                        'shareholder_name': option['recipient'], 'share_class': 'Option',
                        'share_delta': option.get('shares', 0),
                        'source_doc_id': doc_id,
                        'source_snippet': option.get('source_quote', f"Option grant to {option['recipient']}"),
                        'preview_image': doc.get('preview_image'),
                        'summary': doc.get('summary'), 'details': tx_details,
                    })

        if 'repurchase_data' in doc:
            repurchase = doc['repurchase_data']
            if not repurchase.get('error'):
                if not _warn_incomplete(data_warnings, 'Share repurchase', filename, ('date', 'shareholder'), repurchase):
                    shares = repurchase.get('shares')
                    if shares and isinstance(shares, (int, float, Decimal)):
                        rep_details = {'price_per_share': repurchase.get('price_per_share')}
                        if doc.get('preview_focus_y') is not None:
                            rep_details['preview_focus_y'] = doc['preview_focus_y']
                        transactions.append({
                            'event_date': repurchase['date'], 'event_type': 'repurchase',
                            'shareholder_name': repurchase['shareholder'],
                            'share_class': repurchase.get('share_class', 'Common Stock'),
                            'share_delta': -float(abs(shares)),
                            'source_doc_id': doc_id,
                            'source_snippet': repurchase.get('source_quote', f"Repurchase from {repurchase['shareholder']}"),
                            'preview_image': doc.get('preview_image'),
                            'summary': doc.get('summary'), 'details': rep_details,
                        })
                    else:
                        data_warnings.append({
                            'severity': 'warning', 'category': 'Incomplete Extraction',
                            'description': f"Repurchase from '{filename}' has missing/non-numeric shares ({shares!r}) — excluded from cap table.",
                            'source_doc': filename,
                        })

        if 'charter_data' in doc:
            charter = doc['charter_data']
            if not charter.get('error') and charter.get('incorporation_date'):
                transactions.append({
                    'event_date': charter['incorporation_date'], 'event_type': 'formation',
                    'shareholder_name': None, 'share_class': None, 'share_delta': 0,
                    'source_doc_id': doc_id,
                    'source_snippet': charter.get('source_quote', f"Company incorporated: {charter.get('company_name')}"),
                    'details': {
                        'company_name': charter.get('company_name'),
                        'authorized_shares': charter.get('authorized_shares'),
                        'share_classes': charter.get('share_classes'),
                    },
                })

    if data_warnings:
        logger.warning(f"Extraction data loss: {len(data_warnings)} transactions excluded due to incomplete data")
    logger.info(f"Extracted {len(transactions)} equity transactions")
    return transactions, data_warnings


# --- Approval matching (Pass 2B) ---

def match_approvals_batch(transactions: List[Dict[str, Any]], classified_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Match transactions with approving documents using a single batched Claude call."""
    if not transactions:
        return transactions

    approval_required_types = {"issuance", "repurchase", "option_grant"}

    # Set conservative defaults
    for tx in transactions:
        tx_type = (tx.get("event_type") or "").lower()
        tx["approval_doc_id"] = None
        tx["approval_snippet"] = None
        if tx_type in approval_required_types:
            tx["compliance_status"] = "WARNING"
            tx["compliance_note"] = "Approval evidence not matched automatically. Manual review required."
        elif tx_type == "formation":
            tx["compliance_status"] = "VERIFIED"
            tx["compliance_note"] = "Formation evidence sourced from charter document."
        else:
            tx["compliance_status"] = "WARNING"
            tx["compliance_note"] = "Approval linkage not required but evidence should be reviewed."

    # Filter to approval documents
    approval_docs = [d for d in classified_docs if d.get('category') in APPROVAL_DOC_TYPES and d.get('document_id')]

    if not approval_docs:
        logger.warning("No approval documents found — marking approval-required transactions as CRITICAL")
        for tx in transactions:
            tx_type = (tx.get("event_type") or "").lower()
            if tx_type in approval_required_types:
                tx['compliance_status'] = 'CRITICAL'
                tx['compliance_note'] = 'No board approval documents found in document set'
            elif tx_type == "formation":
                tx['compliance_status'] = 'VERIFIED'
                tx['compliance_note'] = 'Formation evidence sourced from charter document'
            else:
                tx['compliance_status'] = 'WARNING'
                tx['compliance_note'] = 'No approval documents found to validate this financing event'
        return transactions

    # Build manifests for Claude
    manifest = [{'doc_id': str(d['document_id']), 'filename': d.get('filename', 'unknown'),
                  'category': d.get('category'), 'excerpt': (d.get('text') or '')[:2000]} for d in approval_docs]
    tx_summary = [{'tx_index': i, 'event_date': tx['event_date'], 'event_type': tx['event_type'],
                    'shareholder': tx.get('shareholder_name'), 'shares': tx.get('share_delta'),
                    'snippet': (tx.get('source_snippet') or '')[:500]} for i, tx in enumerate(transactions)]

    try:
        prompt = prompts.BATCH_APPROVAL_MATCHING_PROMPT.format(
            transactions_json=json.dumps(tx_summary, indent=2),
            approval_docs_json=json.dumps(manifest, indent=2),
        )
        logger.info(f"Matching {len(transactions)} transactions with {len(approval_docs)} approval documents...")
        response = call_claude(prompt, max_tokens=8000)
        matches = parse_json_response(response)

        if not isinstance(matches, list):
            raise ValueError(f"Expected JSON array, got {type(matches).__name__}")
        matches = [m for m in matches if 'tx_index' in m]
        valid_ids = {str(d['document_id']) for d in approval_docs if d.get('document_id')}

        for match in matches:
            tx_idx = match.get('tx_index')
            if tx_idx is None or not (0 <= tx_idx < len(transactions)):
                continue
            returned_id = match.get('approval_doc_id')

            if returned_id and str(returned_id) not in valid_ids:
                logger.warning(f"Invalid approval_doc_id '{returned_id}' for tx_index {tx_idx}")
                transactions[tx_idx]['compliance_status'] = 'WARNING'
                transactions[tx_idx]['compliance_note'] = (
                    (match.get('compliance_note') or '') + ' [Auto-corrected: AI returned non-approval document reference]'
                ).strip()
            else:
                transactions[tx_idx]['approval_doc_id'] = returned_id
                transactions[tx_idx]['approval_snippet'] = match.get('approval_quote')
                fallback = "VERIFIED" if (transactions[tx_idx].get('event_type') or '').lower() == 'formation' else "WARNING"
                transactions[tx_idx]['compliance_status'] = normalize_compliance_status(match.get('compliance_status'), fallback=fallback)
                transactions[tx_idx]['compliance_note'] = match.get('compliance_note')

        logger.info(f"Batch approval matching complete: {len(matches)} matches processed")
        return transactions

    except Exception as e:
        logger.error(f"Batch approval matching failed: {e}", exc_info=True)
        for tx in transactions:
            tx['compliance_note'] = f'Approval matching failed: {str(e)}'
        return transactions
