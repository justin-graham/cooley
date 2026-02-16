"""
AI Processing Pipeline — 3-pass document analysis.

Pass 1: Classify documents by type
Pass 2: Extract structured data + match approvals
Pass 3: Synthesize timeline, cap table, and issues
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from app import db

MAX_WORKERS = int(os.getenv("PIPELINE_MAX_WORKERS", "5"))
PIPELINE_TIMEOUT = int(os.getenv("PIPELINE_TIMEOUT_SECONDS", "600"))


class PipelineTimeoutError(Exception):
    pass


from app.processing.models import (
    normalize_issue, clean_document_dict, build_enriched_documents,
)
from app.processing.classifier import classify_document
from app.processing.extractor import extract_by_type, extract_equity_transactions, match_approvals_batch
from app.processing.synthesizer import synthesize_timeline, extract_company_name
from app.processing.captable import synthesize_cap_table
from app.processing.issues import generate_issues
from app.processing.quality import build_quality_report
from app.processing.carta import tieout_carta_captable, compare_cap_tables

# Re-export for backwards compatibility with tests
from app.processing.claude_client import call_claude

logger = logging.getLogger(__name__)


def process_audit(audit_id: str, documents: List[Dict[str, Any]]):
    """Main orchestrator for the 3-pass AI audit pipeline."""
    _pipeline_start = time.monotonic()

    try:
        total_docs = len(documents)
        logger.info(f"Starting 3-pass processing for {total_docs} documents (timeout: {PIPELINE_TIMEOUT}s)")

        _p = _pipeline_start  # shorthand for timeout checks

        # ========== PASS 1: CLASSIFICATION (concurrent) ==========
        _update_progress(audit_id, "Pass 1: Classifying documents...", 'classifying', _p)

        classified_docs = [None] * total_docs
        completed = [0]

        def _classify_one(idx, doc):
            result = classify_document(doc)
            result['parse_status'] = doc.get('parse_status', 'error' if doc.get('error') else 'success')
            result['parse_error'] = doc.get('parse_error') or doc.get('error')
            return idx, result

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_classify_one, i, doc): i for i, doc in enumerate(documents)}
            for future in as_completed(futures):
                idx, result = future.result()
                classified_docs[idx] = result
                completed[0] += 1
                _update_progress(audit_id, f"Pass 1: Classifying documents... {completed[0]}/{total_docs}", 'classifying', _p)

        logger.info(f"Pass 1 complete: {total_docs} documents classified")

        # ========== PASS 2: EXTRACTION (concurrent) ==========
        _update_progress(audit_id, "Pass 2: Extracting structured data...", 'extracting', _p)

        extractions = [None] * total_docs
        completed[0] = 0

        def _extract_one(idx, doc):
            if doc.get('error') or doc.get('parse_status') == 'error':
                return idx, doc
            extracted_data = extract_by_type(doc)
            return idx, {**doc, **extracted_data}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_extract_one, i, doc): i for i, doc in enumerate(classified_docs)}
            for future in as_completed(futures):
                idx, result = future.result()
                extractions[idx] = result
                completed[0] += 1
                _update_progress(audit_id, f"Pass 2: Extracting data... {completed[0]}/{total_docs}", 'extracting', _p)

        logger.info(f"Pass 2 complete: {total_docs} documents extracted")

        # Persist normalized documents
        enriched_docs = build_enriched_documents(extractions)
        _update_progress(audit_id, "Pass 2: Saving normalized documents...", 'extracting', _p)
        doc_ids = db.insert_documents_and_events(audit_id, enriched_docs, [])
        for doc_list in [extractions, enriched_docs]:
            for doc in doc_list:
                doc_key = str(doc.get('id') or doc.get('filename') or 'unknown')
                if doc_key in doc_ids:
                    doc['document_id'] = doc_ids[doc_key]
        logger.info(f"Inserted {len(enriched_docs)} documents")

        # ========== PASS 2 TIE-OUT: Transaction Extraction & Approval Matching ==========
        _update_progress(audit_id, "Pass 2: Matching transactions with approvals...", 'reconciling', _p)

        transactions, data_warnings = extract_equity_transactions(extractions)
        if transactions:
            transactions = match_approvals_batch(transactions, extractions)
            for tx in transactions:
                details = tx.get('details') if isinstance(tx.get('details'), dict) else {}
                tx['details'] = {'schema_version': 'v1', **details}
            db.insert_equity_events(audit_id, transactions)
            logger.info(f"Inserted {len(transactions)} equity events")

        # ========== PASS 3: SYNTHESIS ==========
        _update_progress(audit_id, "Pass 3: Synthesizing timeline...", 'reconciling', _p)
        timeline = synthesize_timeline(extractions)

        _update_progress(audit_id, "Pass 3: Synthesizing cap table...", 'reconciling', _p)
        cap_table, cap_table_issues = synthesize_cap_table(extractions)

        _update_progress(audit_id, "Pass 3: Synthesizing issues...", 'reconciling', _p)
        issues = generate_issues(enriched_docs, cap_table, timeline, extractions)
        issues.extend([normalize_issue(i) for i in cap_table_issues])
        issues.extend([normalize_issue(i) for i in data_warnings])
        issues = [normalize_issue(i) for i in issues]

        company_name = extract_company_name(extractions)
        logger.info("Pass 3 complete")

        # ========== SAVE RESULTS ==========
        failed_docs = [d for d in enriched_docs if d.get('parse_status') == 'error' or d.get('error')]
        cleaned_docs = [clean_document_dict(doc) for doc in enriched_docs]
        cleaned_failed = [clean_document_dict(doc) for doc in failed_docs]
        quality_report = build_quality_report(cleaned_docs, transactions, issues)
        review_required = bool(quality_report.get('review_required'))

        _update_progress(
            audit_id,
            "Manual review required before finalization." if review_required else "Pass 3: Finalizing report...",
            'needs_review' if review_required else 'complete',
            _p,
        )

        db.update_audit_results(
            audit_id,
            {
                'company_name': company_name,
                'documents': cleaned_docs,
                'timeline': timeline,
                'cap_table': cap_table,
                'issues': issues,
                'failed_documents': cleaned_failed,
            },
            review_required=review_required,
            quality_report=quality_report,
        )

        logger.info(f"Audit {audit_id} completed: {'needs_review' if review_required else 'complete'}")

    except Exception as e:
        logger.error(f"Processing error in audit {audit_id}: {e}", exc_info=True)
        try:
            db.mark_error(audit_id, str(e))
        except Exception as db_error:
            logger.error(f"Failed to mark error in database: {db_error}")


def _update_progress(audit_id: str, step: str, pipeline_state: str, start_time: float = None):
    if start_time is not None:
        elapsed = time.monotonic() - start_time
        if elapsed > PIPELINE_TIMEOUT:
            raise PipelineTimeoutError(f"Pipeline exceeded {PIPELINE_TIMEOUT}s timeout ({elapsed:.0f}s elapsed at: {step})")
    try:
        db.update_progress(audit_id, step, pipeline_state=pipeline_state)
    except Exception as e:
        logger.error(f"Failed to update progress: {e}")
