"""Quality report builder — decides if manual review is required."""

import logging
from typing import Any, Dict, List

from app.processing.models import normalize_issue, normalize_compliance_status

logger = logging.getLogger(__name__)


def build_quality_report(
    documents: List[Dict[str, Any]],
    transactions: List[Dict[str, Any]],
    issues: List[Dict[str, Any]],
) -> Dict[str, Any]:
    report = {
        "schema_version": "v1",
        "document_count": len(documents),
        "parsed_successfully": 0,
        "parse_failures": 0,
        "extraction_failures": 0,
        "low_confidence_count": 0,
        "missing_approvals": 0,
        "critical_compliance_event_count": 0,
        "critical_issue_count": 0,
        "blocking_reasons": [],
        "warnings": [],
    }

    for doc in documents:
        if doc.get("parse_status") in {"success", "partial"}:
            report["parsed_successfully"] += 1
        else:
            report["parse_failures"] += 1
            report["blocking_reasons"].append(f"Document parsing failed: {doc.get('filename', 'unknown')}")

        for warning in _scan_low_confidence(doc):
            report["low_confidence_count"] += 1
            report["warnings"].append(warning)
            report["blocking_reasons"].append(f"Low-confidence extraction requires review: {doc.get('filename', 'unknown')}")

        for failure in _scan_extraction_errors(doc):
            report["extraction_failures"] += 1
            report["warnings"].append(failure)
            report["blocking_reasons"].append(f"Extraction failed: {doc.get('filename', 'unknown')}")

    for tx in transactions:
        tx_type = (tx.get("event_type") or "").lower()
        requires_approval = tx_type in {"issuance", "repurchase", "option_grant"}
        if requires_approval and not tx.get("approval_doc_id"):
            report["missing_approvals"] += 1
            report["blocking_reasons"].append(f"Missing approval for {tx.get('event_type')} on {tx.get('event_date')}")

        summary = str(tx.get("summary") or "").strip().lower()
        if summary and any(token in summary for token in ["n/a", "none", "unknown", "null"]):
            report["blocking_reasons"].append(f"Unresolved summary placeholders for event on {tx.get('event_date')}")

        status = normalize_compliance_status(tx.get("compliance_status"), fallback="WARNING")
        if status == "CRITICAL":
            report["critical_compliance_event_count"] += 1
            report["blocking_reasons"].append(f"Critical compliance gap for {tx.get('event_type')} on {tx.get('event_date')}")

    normalized_issues = [normalize_issue(i) for i in issues]
    report["critical_issue_count"] = sum(1 for i in normalized_issues if i.get("severity") == "critical")
    if report["critical_issue_count"] > 0:
        report["blocking_reasons"].append(f"{report['critical_issue_count']} critical compliance issue(s)")

    report["warnings"] = list(dict.fromkeys(report["warnings"]))
    report["blocking_reasons"] = list(dict.fromkeys(report["blocking_reasons"]))
    report["review_required"] = bool(report["blocking_reasons"])
    return report


def _scan_low_confidence(doc: Dict[str, Any]) -> List[str]:
    warnings = []
    extracted = doc.get("extracted_data", {}).get("extraction", {})
    if not isinstance(extracted, dict):
        return warnings
    for value in extracted.values():
        if isinstance(value, dict) and value.get("low_confidence"):
            warnings.append(value.get("confidence_warning") or "Low confidence extraction")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("low_confidence"):
                    warnings.append(item.get("confidence_warning") or "Low confidence extraction")
    return warnings


def _scan_extraction_errors(doc: Dict[str, Any]) -> List[str]:
    failures = []
    extracted = doc.get("extracted_data", {}).get("extraction", {})
    if not isinstance(extracted, dict):
        return failures
    for key, value in extracted.items():
        if isinstance(value, dict) and value.get("error"):
            failures.append(f"{key}: {value['error']}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("error"):
                    failures.append(f"{key}: {item['error']}")
    return failures
