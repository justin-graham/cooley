"""Deterministic cap table calculation using Decimal arithmetic."""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from app.processing.models import normalize_share_class, normalize_shareholder_name

logger = logging.getLogger(__name__)


def build_raw_cap_table(equity_data: List[Dict[str, Any]], issues: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Aggregate equity data into cap table entries with ownership percentages."""
    aggregated = {}
    display_names = {}  # normalized_name -> first-seen display name
    for item in equity_data:
        raw_name = item.get('shareholder') or item.get('investor') or item.get('recipient') or 'Unknown'
        norm_name = normalize_shareholder_name(raw_name)
        if norm_name not in display_names:
            display_names[norm_name] = raw_name
        shares = item.get('shares', 0)
        raw_class = item.get('share_class') or item.get('type', 'Common Stock')
        share_class = normalize_share_class(raw_class)

        key = (norm_name, share_class)
        if key not in aggregated:
            aggregated[key] = Decimal('0')
        if isinstance(shares, (int, float, Decimal)):
            aggregated[key] += Decimal(str(shares))

    # Flag data integrity issues
    for (norm_name, share_class), shares in aggregated.items():
        name = display_names.get(norm_name, norm_name)
        if shares == 0:
            logger.info(f"Full repurchase: {name} ({share_class}) has 0 net shares")
            if issues is not None:
                issues.append({'severity': 'info', 'category': 'Cap Table',
                               'description': f"{name} has 0 net shares ({share_class}) after repurchase."})
        elif shares < 0:
            logger.error(f"Data integrity: {name} ({share_class}) has {shares} net shares (negative)")
            if issues is not None:
                issues.append({'severity': 'critical', 'category': 'Data Integrity',
                               'description': f"{name} has {shares} net shares ({share_class}). More repurchased than issued — possible missing document."})

    # Only include positive positions
    positive = {k: v for k, v in aggregated.items() if v > 0}
    total_shares = sum(positive.values())

    TWO_PLACES = Decimal('0.01')
    cap_table = [
        {
            'shareholder': display_names.get(norm_name, norm_name),
            'shares': float(shares),
            'share_class': share_class,
            'ownership_pct': float((shares / total_shares * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)) if total_shares > 0 else 0.0,
        }
        for (norm_name, share_class), shares in positive.items()
    ]
    cap_table.sort(key=lambda x: x['ownership_pct'], reverse=True)

    # Adjust to ensure exactly 100%
    if cap_table:
        calculated_total = sum(e['ownership_pct'] for e in cap_table)
        if calculated_total != 100.0:
            adjustment = round(100.0 - calculated_total, 2)
            cap_table[0]['ownership_pct'] = round(cap_table[0]['ownership_pct'] + adjustment, 2)

    return cap_table


def synthesize_cap_table(extractions: List[Dict[str, Any]]):
    """Collect equity data from extractions and build cap table programmatically."""
    equity_data = []

    for doc in extractions:
        if 'stock_issuances' in doc:
            equity_data.extend(doc['stock_issuances'])

        if 'safe_data' in doc:
            safe = doc['safe_data']
            if not safe.get('error'):
                equity_data.append({
                    'shareholder': safe.get('investor'), 'amount': safe.get('amount'),
                    'type': 'SAFE', 'date': safe.get('date'),
                })

        if 'convertible_note_data' in doc:
            note = doc['convertible_note_data']
            if not note.get('error'):
                equity_data.append({
                    'shareholder': note.get('investor'), 'amount': note.get('principal'),
                    'type': 'Convertible Note', 'date': note.get('date'),
                })

        if 'repurchase_data' in doc:
            repurchase = doc['repurchase_data']
            if not repurchase.get('error'):
                shares = repurchase.get('shares')
                shareholder = repurchase.get('shareholder')
                share_class = repurchase.get('share_class', 'Common Stock')

                # Infer shares from issuances if not extracted
                if shares is None and shareholder:
                    logger.info(f"Repurchase shares=None for {shareholder}, inferring from issuances...")
                    norm = normalize_shareholder_name(shareholder)
                    matching = [
                        item for item in equity_data
                        if normalize_shareholder_name(item.get('shareholder') or item.get('investor') or item.get('recipient') or '') == norm
                        and isinstance(item.get('shares'), (int, float, Decimal))
                        and item.get('shares', 0) > 0
                    ]
                    if matching:
                        shares = sum(item['shares'] for item in matching)
                        logger.info(f"Inferred {shares} shares from {len(matching)} issuances")

                if shares and isinstance(shares, (int, float, Decimal)):
                    equity_data.append({
                        'shareholder': shareholder,
                        'shares': -float(abs(shares)),
                        'share_class': share_class,
                        'date': repurchase.get('date'),
                    })

    if not equity_data:
        return [], []

    cap_table_issues = []
    cap_table = build_raw_cap_table(equity_data, issues=cap_table_issues)
    logger.info(f"Cap table: {len(cap_table)} entries, {len(cap_table_issues)} issues")
    return cap_table, cap_table_issues
