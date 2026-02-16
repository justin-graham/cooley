"""Deterministic compliance checks and AI-enhanced issue detection."""

import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

from anthropic import RateLimitError

from app import prompts
from app.processing.claude_client import call_claude, parse_json_response
from app.processing.models import normalize_issue

logger = logging.getLogger(__name__)


def check_deterministic_issues(
    documents: List[Dict[str, Any]],
    cap_table: List[Dict[str, Any]],
    timeline: List[Dict[str, Any]],
    extractions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Rule-based compliance checks — 100% reliable, no AI."""
    issues = []
    doc_categories = [d.get('category', '') for d in documents]

    # Missing Charter
    if not any('Charter' in cat for cat in doc_categories):
        issues.append({'severity': 'critical', 'category': 'Missing Document',
                       'description': 'No Certificate of Incorporation or Charter Document found.'})

    # Stock issuances without board approval
    has_stock = any('Stock Purchase' in cat or 'Stock Certificate' in cat for cat in doc_categories)
    has_consent = any('Minutes' in cat or 'Board' in cat for cat in doc_categories)
    if has_stock and not has_consent:
        issues.append({'severity': 'critical', 'category': 'Equity Compliance',
                       'description': 'Stock issuances found but no Board Minutes or Written Consents documenting approval.'})

    # Issued exceeds authorized
    authorized = _get_authorized_shares(extractions)
    if authorized and cap_table:
        total_issued = sum(float(e.get('shares', 0)) for e in cap_table if isinstance(e.get('shares'), (int, float, Decimal)))
        if total_issued > authorized:
            issues.append({'severity': 'critical', 'category': 'Cap Table Integrity',
                           'description': f'Issued shares ({total_issued:,}) exceed authorized shares ({authorized:,}).'})

    # Founder stock without 83(b)
    if any('Stock Purchase' in cat for cat in doc_categories) and not any('83(b)' in cat for cat in doc_categories):
        issues.append({'severity': 'warning', 'category': 'Equity Compliance',
                       'description': 'Stock Purchase Agreements found but no 83(b) election forms.'})

    # Sparse board governance
    if timeline:
        _check_board_governance(timeline, documents, issues)

    # Option grants without plan
    if any('Option Grant' in cat for cat in doc_categories) and not any('Equity Incentive Plan' in cat or 'Stock Plan' in cat for cat in doc_categories):
        issues.append({'severity': 'note', 'category': 'Equity Compliance',
                       'description': 'Option Grant Agreements found but no Equity Incentive Plan document.'})

    # Missing repurchase share counts
    for ext in extractions:
        if 'repurchase_data' in ext:
            rep = ext['repurchase_data']
            if not rep.get('error') and rep.get('shareholder') and rep.get('date') and rep.get('shares') is None:
                issues.append({'severity': 'critical', 'category': 'Missing Data',
                               'description': f"Repurchase from {rep['shareholder']} on {rep['date']} missing share count. Document: {ext.get('filename', 'unknown')}.",
                               'source_doc': ext.get('filename')})

    # Chronological integrity
    _check_chronological_integrity(timeline, issues)

    # Option pool validation
    _check_option_pool(extractions, issues)

    # Missing document inference from board minutes
    _check_referenced_docs(extractions, documents, issues)

    # Low confidence extractions
    _flag_low_confidence(extractions, issues)

    logger.info(f"Deterministic checks found {len(issues)} issues")
    return issues


def generate_issues(
    documents: List[Dict[str, Any]],
    cap_table: List[Dict[str, Any]],
    timeline: List[Dict[str, Any]],
    extractions: List[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Combine deterministic checks with AI analysis."""
    deterministic_issues = check_deterministic_issues(documents, cap_table, timeline, extractions) if extractions else []

    try:
        doc_summary = [{'filename': d['filename'], 'category': d.get('category', 'Other')} for d in documents]
        prompt = prompts.ISSUE_TRACKER_PROMPT.format(
            documents_json=json.dumps(doc_summary, indent=2),
            cap_table_json=json.dumps(cap_table, indent=2),
            timeline_json=json.dumps(timeline, indent=2),
        )
        response = call_claude(prompt, max_tokens=4096)
        ai_issues = parse_json_response(response)

        all_issues = [normalize_issue(i) for i in (deterministic_issues + ai_issues)]
        logger.info(f"Total issues: {len(all_issues)} ({len(deterministic_issues)} deterministic, {len(ai_issues)} AI)")
        return all_issues

    except RateLimitError as e:
        logger.warning(f"Issue generation rate limited: {e}")
        deterministic_issues.append({
            'severity': 'warning', 'category': 'System',
            'description': 'AI-enhanced issue analysis was skipped due to rate limiting. Only deterministic checks are included. Manual review recommended.',
        })
        return [normalize_issue(i) for i in deterministic_issues]
    except Exception as e:
        logger.error(f"AI issue generation failed: {e}", exc_info=True)
        deterministic_issues.append({
            'severity': 'warning', 'category': 'System',
            'description': f'AI-enhanced issue analysis failed ({type(e).__name__}). Only deterministic checks are included. Manual review recommended.',
        })
        fallback = deterministic_issues or [{'severity': 'critical', 'category': 'System Error', 'description': f'Issue analysis failed: {str(e)}'}]
        return [normalize_issue(i) for i in fallback]


# --- Private helpers ---

def _get_authorized_shares(extractions):
    for ext in extractions:
        if 'charter_data' in ext:
            charter = ext['charter_data']
            if not charter.get('error') and charter.get('authorized_shares'):
                try:
                    return int(charter['authorized_shares'])
                except (ValueError, TypeError):
                    pass
    return None


def _check_board_governance(timeline, documents, issues):
    dates = sorted([e.get('date', '') for e in timeline if e.get('date')])
    if not dates:
        return
    try:
        first = datetime.strptime(dates[0], '%Y-%m-%d')
        last = datetime.strptime(dates[-1], '%Y-%m-%d')
        years = (last - first).days / 365.25
        board_meetings = sum(1 for d in documents if 'Minutes' in d.get('category', '') or 'Board' in d.get('category', ''))
        if years >= 3 and board_meetings < 3:
            issues.append({'severity': 'warning', 'category': 'Board Governance',
                           'description': f'Company has {years:.1f} years of history but only {board_meetings} documented board meeting(s).'})
    except ValueError:
        pass


def _check_chronological_integrity(timeline, issues):
    if not timeline:
        return
    formation_date = None
    earliest_non_formation = None
    earliest_event = None

    for event in timeline:
        event_date = event.get('date', '')
        if not event_date:
            continue
        try:
            dt = datetime.strptime(event_date, '%Y-%m-%d')
            if event.get('event_type') == 'formation':
                if formation_date is None or dt < formation_date:
                    formation_date = dt
            else:
                if earliest_non_formation is None or dt < earliest_non_formation:
                    earliest_non_formation = dt
                    earliest_event = event
        except ValueError:
            continue

    if formation_date and earliest_non_formation and earliest_non_formation < formation_date:
        issues.append({
            'severity': 'critical', 'category': 'Chronological Integrity',
            'description': f"Event dated {earliest_non_formation.strftime('%Y-%m-%d')} ({earliest_event.get('event_type', 'unknown')}) predates company formation ({formation_date.strftime('%Y-%m-%d')}).",
        })


def _check_option_pool(extractions, issues):
    option_pool_size = None
    for ext in extractions:
        if 'Equity Incentive Plan' in ext.get('category', '') or 'Stock Plan' in ext.get('category', ''):
            text = ext.get('text', '').lower()
            for pattern in [
                r'(?:reserve|pool|allocated?|set aside)\s+(?:of\s+)?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:shares|options)',
                r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*shares?\s+(?:reserved|allocated|in\s+the\s+pool)',
            ]:
                match = re.search(pattern, text)
                if match:
                    try:
                        option_pool_size = int(match.group(1).replace(',', ''))
                        break
                    except (ValueError, AttributeError):
                        pass
            if option_pool_size:
                break

    total_grants = 0
    for ext in extractions:
        if 'option_data' in ext:
            option = ext['option_data']
            if not option.get('error') and option.get('shares'):
                try:
                    total_grants += int(option['shares'])
                except (ValueError, TypeError):
                    pass

    if option_pool_size and total_grants > option_pool_size:
        issues.append({'severity': 'critical', 'category': 'Option Pool Integrity',
                       'description': f"Option grants ({total_grants:,}) exceed pool size ({option_pool_size:,})."})
    elif option_pool_size and total_grants > 0:
        utilization = (total_grants / option_pool_size) * 100
        if utilization > 90:
            issues.append({'severity': 'warning', 'category': 'Option Pool Integrity',
                           'description': f"Option pool {utilization:.1f}% utilized ({total_grants:,} of {option_pool_size:,})."})


def _check_referenced_docs(extractions, documents, issues):
    referenced_docs = []
    for ext in extractions:
        if 'minutes_data' in ext:
            minutes = ext['minutes_data']
            if not minutes.get('error'):
                for decision in minutes.get('key_decisions', []):
                    dl = str(decision).lower()
                    if 'option grant' in dl and 'approved' in dl:
                        referenced_docs.append(('Option Grant Agreement', decision))
                    if 'stock issuance' in dl or 'issue shares' in dl:
                        referenced_docs.append(('Stock Purchase Agreement', decision))
                    if 'safe' in dl and 'approved' in dl:
                        referenced_docs.append(('SAFE', decision))

    for doc_type, decision in referenced_docs:
        if not any(doc_type in d.get('category', '') for d in documents):
            issues.append({'severity': 'warning', 'category': 'Missing Document',
                           'description': f"Board minutes reference '{decision[:80]}...' but no {doc_type} document found."})


def _flag_low_confidence(extractions, issues):
    for ext in extractions:
        for key, value in ext.items():
            if isinstance(value, dict) and value.get('low_confidence'):
                issues.append({'severity': 'warning', 'category': 'Extraction Quality',
                               'description': value.get('confidence_warning', f"Low confidence for {ext.get('filename', 'unknown')}.")})
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get('low_confidence'):
                        issues.append({'severity': 'warning', 'category': 'Extraction Quality',
                                       'description': item.get('confidence_warning', f"Low confidence for {ext.get('filename', 'unknown')}.")})
