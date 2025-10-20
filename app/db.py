"""
Database connection and CRUD operations for audit records.
Uses Postgres with psycopg2 for simple, reliable connections.
"""

import os
import json
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from typing import Optional, Dict, Any


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

    Args:
        audit_id: UUID of the audit
        progress_message: Human-readable progress text (e.g., "Classifying document 12/47...")
    """
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
