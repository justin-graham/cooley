"""Pass 3: Timeline synthesis and company name extraction."""

import json
import logging
from typing import Any, Dict, List

from anthropic import RateLimitError

from app import prompts
from app.processing.claude_client import call_claude, parse_json_response

logger = logging.getLogger(__name__)


def build_timeline_programmatically(extractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build timeline from structured data — deterministic, no AI."""
    events = []

    for doc in extractions:
        filename = doc.get('filename', 'unknown')

        if 'charter_data' in doc:
            charter = doc['charter_data']
            if not charter.get('error') and charter.get('incorporation_date'):
                events.append({
                    'date': charter['incorporation_date'],
                    'event_type': 'formation',
                    'description': f"Company incorporated: {charter.get('company_name', 'Unknown Company')}",
                    'source_docs': [filename],
                })

        if 'stock_issuances' in doc:
            for issuance in doc['stock_issuances']:
                if issuance.get('date') and issuance.get('shareholder') and issuance.get('shares'):
                    events.append({
                        'date': issuance['date'],
                        'event_type': 'stock_issuance',
                        'description': f"{issuance['shareholder']} received {issuance['shares']:,} shares of {issuance.get('share_class', 'stock')}",
                        'source_docs': [filename],
                    })

        if 'safe_data' in doc:
            safe = doc['safe_data']
            if not safe.get('error') and safe.get('date') and safe.get('investor'):
                events.append({
                    'date': safe['date'],
                    'event_type': 'financing',
                    'description': f"SAFE investment by {safe['investor']} for ${safe.get('amount', 0):,}",
                    'source_docs': [filename],
                })

        if 'convertible_note_data' in doc:
            note = doc['convertible_note_data']
            if not note.get('error') and note.get('date') and note.get('investor'):
                events.append({
                    'date': note['date'],
                    'event_type': 'financing',
                    'description': f"Convertible note from {note['investor']} for ${note.get('principal', 0):,} at {note.get('interest_rate', 0)}% interest (maturity: {note.get('maturity_date', 'unspecified')})",
                    'source_docs': [filename],
                })

        if 'minutes_data' in doc:
            minutes = doc['minutes_data']
            if not minutes.get('error') and minutes.get('meeting_date'):
                decisions = minutes.get('key_decisions', [])
                decisions_str = '; '.join(decisions[:2]) if decisions else 'corporate actions discussed'
                events.append({
                    'date': minutes['meeting_date'],
                    'event_type': 'board_action',
                    'description': f"{minutes.get('meeting_type', 'Meeting')}: {decisions_str}",
                    'source_docs': [filename],
                })

        if 'option_data' in doc:
            option = doc['option_data']
            if not option.get('error') and option.get('grant_date') and option.get('recipient'):
                events.append({
                    'date': option['grant_date'],
                    'event_type': 'option_grant',
                    'description': f"Option grant to {option['recipient']} for {option.get('shares', 0):,} shares",
                    'source_docs': [filename],
                })

        if 'repurchase_data' in doc:
            repurchase = doc['repurchase_data']
            if not repurchase.get('error') and repurchase.get('date') and repurchase.get('shareholder'):
                shares = repurchase.get('shares') or 0
                shares = abs(shares) if isinstance(shares, (int, float)) else 0
                desc = (f"Company repurchased {shares:,} shares from {repurchase['shareholder']}"
                        if shares > 0 else f"Share repurchase transaction with {repurchase['shareholder']}")
                events.append({
                    'date': repurchase['date'],
                    'event_type': 'repurchase',
                    'description': desc,
                    'source_docs': [filename],
                })

    events.sort(key=lambda x: x.get('date', ''))
    logger.info(f"Built timeline programmatically: {len(events)} events")
    return events


def synthesize_timeline(extractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic timeline first; Claude fallback only for very sparse data."""
    programmatic_timeline = build_timeline_programmatically(extractions)

    if len(programmatic_timeline) >= 3:
        return programmatic_timeline

    try:
        extractions_json = json.dumps(extractions, indent=2)
        prompt = prompts.TIMELINE_SYNTHESIS_PROMPT.format(extractions_json=extractions_json)
        response = call_claude(prompt, max_tokens=4096)
        ai_timeline = parse_json_response(response)
        ai_timeline.sort(key=lambda x: x.get('date', ''))
        logger.info(f"Using AI-enhanced timeline ({len(ai_timeline)} events)")
        return ai_timeline
    except (RateLimitError, Exception) as e:
        logger.warning(f"Timeline AI enhancement failed, using programmatic: {e}")
        return programmatic_timeline


def extract_company_name(extractions: List[Dict[str, Any]]) -> str:
    """Extract company name from charter documents — deterministic first, Claude fallback."""
    try:
        for doc in extractions:
            if 'charter_data' in doc:
                name = doc['charter_data'].get('company_name')
                if name:
                    return name

        charter_docs = [doc for doc in extractions if 'charter_data' in doc]
        if not charter_docs:
            return "Unknown Company"

        charter_texts = '\n\n---\n\n'.join([doc['text'][:5000] for doc in charter_docs if 'text' in doc])
        prompt = prompts.COMPANY_NAME_EXTRACTION_PROMPT.format(charter_texts=charter_texts)
        response = call_claude(prompt, max_tokens=256)
        return response.strip() or "Unknown Company"
    except Exception:
        return "Unknown Company"
