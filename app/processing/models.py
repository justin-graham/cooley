"""Shared models, normalization helpers, and text-cleaning utilities."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError


class ExtractedDataEnvelope(BaseModel):
    """Versioned schema for persisted documents.extracted_data payloads."""
    schema_version: str = "v1"
    category: str
    parse_status: str
    parse_error: Optional[str] = None
    extraction: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class IssueRecord(BaseModel):
    """Normalized issue object schema persisted in audits.issues."""
    severity: str
    category: str
    description: str
    source_doc: Optional[str] = None


# Document types that generate equity transactions
TRANSACTABLE_DOC_TYPES = [
    'Stock Purchase Agreement', 'SAFE', 'Option Grant Agreement',
    'Share Repurchase Agreement', 'Convertible Note',
]

# Document types that can approve transactions
APPROVAL_DOC_TYPES = ['Board/Shareholder Minutes', 'Charter Document']

# Canonical share class names
SHARE_CLASS_ALIASES = {
    'common': 'Common Stock', 'common stock': 'Common Stock',
    'common shares': 'Common Stock', 'class a common': 'Common Stock',
    'class a common stock': 'Common Stock', 'ordinary shares': 'Common Stock',
    'ordinary stock': 'Common Stock',
    'series seed': 'Series Seed Preferred', 'series seed preferred': 'Series Seed Preferred',
    'series seed preferred stock': 'Series Seed Preferred', 'seed preferred': 'Series Seed Preferred',
    'series a': 'Series A Preferred', 'series a preferred': 'Series A Preferred',
    'series a preferred stock': 'Series A Preferred',
    'series a-1': 'Series A Preferred', 'series a-1 preferred': 'Series A Preferred',
    'series b': 'Series B Preferred', 'series b preferred': 'Series B Preferred',
    'series b preferred stock': 'Series B Preferred',
    'safe': 'SAFE', 'simple agreement for future equity': 'SAFE',
    'convertible note': 'Convertible Note', 'convertible promissory note': 'Convertible Note',
    'option': 'Option', 'stock option': 'Option',
    'iso': 'Option', 'nso': 'Option', 'nqso': 'Option',
}


def normalize_shareholder_name(name: str) -> str:
    """Normalize shareholder name for grouping. 'Smith, John' → 'john smith'."""
    if not name:
        return ''
    name = name.strip().lower()
    # Handle "Last, First" format
    if ',' in name:
        parts = [p.strip() for p in name.split(',', 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            name = f"{parts[1]} {parts[0]}"
    # Collapse whitespace
    name = ' '.join(name.split())
    return name


def normalize_share_class(share_class: str) -> str:
    if not share_class:
        return 'Common Stock'
    normalized = share_class.lower().strip()
    return SHARE_CLASS_ALIASES.get(normalized, share_class.strip().title())


def normalize_compliance_status(value: Any, fallback: str = "WARNING") -> str:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"VERIFIED", "WARNING", "CRITICAL"} else fallback


def _severity_key(value: Any) -> str:
    sev = (value or "note").strip().lower()
    return sev if sev in {"critical", "warning", "info", "note"} else "warning"


def normalize_issue(issue: Any) -> Dict[str, Any]:
    if isinstance(issue, str):
        normalized = {"severity": "note", "category": "General", "description": issue}
    elif isinstance(issue, dict):
        normalized = {
            "severity": _severity_key(issue.get("severity")),
            "category": str(issue.get("category") or "General"),
            "description": str(issue.get("description") or issue.get("message") or "Unspecified issue"),
        }
        if issue.get("source_doc"):
            normalized["source_doc"] = str(issue["source_doc"])
    else:
        normalized = {"severity": "warning", "category": "System Error",
                       "description": f"Unsupported issue payload: {type(issue).__name__}"}
    try:
        return IssueRecord(**normalized).model_dump(exclude_none=True)
    except ValidationError:
        return {"severity": "warning", "category": "System Error",
                "description": "Issue normalization failed"}


# --- Text utilities ---

def clean_text_for_db(text: str) -> str:
    if not isinstance(text, str):
        return text
    return text.replace('\x00', '').replace('\r', '\n')


def clean_document_dict(doc: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {}
    for key, value in doc.items():
        if isinstance(value, str):
            cleaned[key] = clean_text_for_db(value)
        elif isinstance(value, dict):
            cleaned[key] = clean_document_dict(value)
        elif isinstance(value, list):
            cleaned[key] = [
                clean_document_dict(item) if isinstance(item, dict)
                else clean_text_for_db(item) if isinstance(item, str)
                else item for item in value
            ]
        elif isinstance(value, Decimal):
            cleaned[key] = float(value)
        elif isinstance(value, (date, datetime)):
            cleaned[key] = value.isoformat()
        else:
            cleaned[key] = value
    return cleaned


def format_text_with_paragraphs(text: str) -> str:
    if not text:
        return text
    lines = text.split('\n')
    formatted_lines = []
    paragraph_num = 1
    current_para = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_para:
                para_text = ' '.join(current_para)
                if len(para_text) > 20:
                    formatted_lines.append(f"[¶{paragraph_num}] {para_text}")
                    paragraph_num += 1
                current_para = []
            continue
        current_para.append(stripped)

    if current_para:
        para_text = ' '.join(current_para)
        if len(para_text) > 20:
            formatted_lines.append(f"[¶{paragraph_num}] {para_text}")

    return '\n\n'.join(formatted_lines)


# --- Document payload builders ---

_METADATA_KEYS = {
    "id", "document_id", "filename", "type", "text", "error", "category",
    "summary", "pdf_path", "text_spans", "parse_status", "parse_error", "preview_image", "preview_focus_y",
}


def extract_doc_payload(doc: Dict[str, Any]) -> Dict[str, Any]:
    extraction = {k: v for k, v in doc.items() if k not in _METADATA_KEYS}
    warnings = []
    if doc.get("error"):
        warnings.append(str(doc["error"]))
    if doc.get("parse_error") and doc.get("parse_error") not in warnings:
        warnings.append(str(doc["parse_error"]))

    envelope = ExtractedDataEnvelope(
        category=doc.get("category", "Other"),
        parse_status=doc.get("parse_status", "success"),
        parse_error=doc.get("parse_error"),
        extraction=extraction,
        warnings=warnings,
    )
    return envelope.model_dump(exclude_none=True)


def build_enriched_documents(extractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched_docs = []
    for doc in extractions:
        enriched = {
            "id": doc.get("id"),
            "filename": doc.get("filename"),
            "type": doc.get("type"),
            "category": doc.get("category", "Other"),
            "summary": doc.get("summary"),
            "text": doc.get("text", ""),
            "error": doc.get("error"),
            "parse_status": doc.get("parse_status", "error" if doc.get("error") else "success"),
            "parse_error": doc.get("parse_error") or doc.get("error"),
            "extracted_data": extract_doc_payload(doc),
        }
        if doc.get("document_id"):
            enriched["document_id"] = doc["document_id"]
        enriched_docs.append(enriched)
    return enriched_docs
