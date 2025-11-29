"""
Database connection and CRUD operations for audit records.
Uses Postgres with psycopg2 for simple, reliable connections.
"""

import os
import json
import logging
import psycopg2
from decimal import Decimal
from psycopg2.extras import Json, RealDictCursor
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_connection():
    """Get a database connection using DATABASE_URL from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url)


def create_audit(audit_id: str) -> None:
    """
    Initialize a new audit record with 'processing' status.

    Args:
        audit_id: UUID string for the audit
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audits (id, status, progress)
                VALUES (%s, %s, %s)
                """,
                (audit_id, 'processing', 'Starting document extraction...')
            )
        conn.commit()
    finally:
        conn.close()


def update_progress(audit_id: str, progress_message: str) -> None:
    """
    Update the progress message for an audit (for real-time frontend updates).
    Failures are logged but don't raise exceptions to avoid crashing the pipeline.

    Args:
        audit_id: UUID of the audit
        progress_message: Human-readable progress text (e.g., "Classifying document 12/47...")
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE audits SET progress = %s WHERE id = %s",
                    (progress_message, audit_id)
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        # Log error but don't crash - progress updates are non-critical
        logger.error(f"Failed to update progress for audit {audit_id}: {e}")
        print(f"WARNING: Failed to update progress for audit {audit_id}: {e}")


def update_audit_results(audit_id: str, results: Dict[str, Any]) -> None:
    """
    Save final audit results and mark as complete.

    Args:
        audit_id: UUID of the audit
        results: Dictionary with keys:
            - company_name: str
            - documents: list of document dicts
            - timeline: list of event dicts
            - cap_table: list of shareholder dicts
            - issues: list of issue dicts
            - failed_documents: list of failed doc dicts (optional)
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE audits
                SET status = %s,
                    progress = %s,
                    company_name = %s,
                    documents = %s,
                    timeline = %s,
                    cap_table = %s,
                    issues = %s,
                    failed_documents = %s
                WHERE id = %s
                """,
                (
                    'complete',
                    'Audit complete',
                    results.get('company_name'),
                    Json(results.get('documents', [])),
                    Json(results.get('timeline', [])),
                    Json(results.get('cap_table', [])),
                    Json(results.get('issues', [])),
                    Json(results.get('failed_documents', [])),
                    audit_id
                )
            )
        conn.commit()
    finally:
        conn.close()


def mark_error(audit_id: str, error_message: str) -> None:
    """
    Mark an audit as failed with an error message.

    Args:
        audit_id: UUID of the audit
        error_message: Description of what went wrong
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE audits
                SET status = %s,
                    progress = %s,
                    error_message = %s
                WHERE id = %s
                """,
                ('error', 'Processing failed', error_message, audit_id)
            )
        conn.commit()
    finally:
        conn.close()


def get_audit(audit_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve an audit record by ID.

    Args:
        audit_id: UUID of the audit

    Returns:
        Dictionary with audit data, or None if not found
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM audits WHERE id = %s", (audit_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


# ============================================================================
# CRUD Operations for Cap Table Tie-Out Feature
# ============================================================================

def insert_document(audit_id: str, filename: str, classification: Optional[str] = None,
                    extracted_data: Optional[Dict] = None, full_text: Optional[str] = None) -> str:
    """
    Insert a document record and return its UUID.

    Args:
        audit_id: UUID of the parent audit
        filename: Original filename
        classification: Document type (e.g., 'Stock Purchase Agreement')
        extracted_data: Structured data from Pass 2
        full_text: Parsed document text

    Returns:
        UUID string of the created document
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (audit_id, filename, classification, extracted_data, full_text)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (audit_id, filename, classification, Json(extracted_data) if extracted_data else None, full_text)
            )
            doc_id = cur.fetchone()[0]
        conn.commit()
        return str(doc_id)
    finally:
        conn.close()


def get_documents_by_audit(audit_id: str) -> list[Dict[str, Any]]:
    """
    Retrieve all documents for an audit.

    Args:
        audit_id: UUID of the audit

    Returns:
        List of document dictionaries
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM documents WHERE audit_id = %s ORDER BY created_at",
                (audit_id,)
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def insert_equity_events(audit_id: str, events: list[Dict[str, Any]]) -> None:
    """
    Bulk insert equity events for an audit.

    Args:
        audit_id: UUID of the audit
        events: List of event dictionaries with keys:
            - event_date: date
            - event_type: str
            - shareholder_name: str (optional)
            - share_class: str (optional)
            - share_delta: float
            - source_doc_id: str (UUID)
            - source_snippet: str (optional)
            - approval_doc_id: str (UUID, optional)
            - approval_snippet: str (optional)
            - compliance_status: str ('VERIFIED', 'WARNING', 'CRITICAL')
            - compliance_note: str (optional)
            - details: dict (optional)
    """
    if not events:
        return

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for event in events:
                cur.execute(
                    """
                    INSERT INTO equity_events (
                        audit_id, event_date, event_type, shareholder_name, share_class, share_delta,
                        source_doc_id, source_snippet, approval_doc_id, approval_snippet,
                        compliance_status, compliance_note, details
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        audit_id,
                        event['event_date'],
                        event['event_type'],
                        event.get('shareholder_name'),
                        event.get('share_class'),
                        event['share_delta'],
                        event.get('source_doc_id'),
                        event.get('source_snippet'),
                        event.get('approval_doc_id'),
                        event.get('approval_snippet'),
                        event.get('compliance_status', 'VERIFIED'),
                        event.get('compliance_note'),
                        Json(event.get('details', {}))
                    )
                )
        conn.commit()
    finally:
        conn.close()


def get_equity_events_by_audit(audit_id: str) -> list[Dict[str, Any]]:
    """
    Retrieve all equity events for an audit, ordered by date.

    Args:
        audit_id: UUID of the audit

    Returns:
        List of equity event dictionaries
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, event_date, event_type, shareholder_name, share_class, share_delta,
                       source_doc_id, source_snippet, approval_doc_id, approval_snippet,
                       compliance_status, compliance_note, details
                FROM equity_events
                WHERE audit_id = %s
                ORDER BY event_date ASC, created_at ASC
                """,
                (audit_id,)
            )
            # Convert Decimal to float for arithmetic compatibility
            rows = cur.fetchall()
            return [
                {
                    **dict(row),
                    'share_delta': float(row['share_delta']) if row['share_delta'] is not None else 0.0
                }
                for row in rows
            ]
    finally:
        conn.close()


def get_document_by_id(doc_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single document by its ID.

    Args:
        doc_id: UUID of the document

    Returns:
        Dictionary with document data, or None if not found
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, audit_id, filename, classification, extracted_data, full_text, created_at
                FROM documents
                WHERE id = %s
                """,
                (doc_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()
