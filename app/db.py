"""
Database connection and CRUD operations for audit records.
Uses Postgres with psycopg2 and connection pooling for efficient access.
"""

import os
import json
import logging
from datetime import datetime
import psycopg2
import psycopg2.pool
from contextlib import contextmanager
from decimal import Decimal
from psycopg2.extras import Json, RealDictCursor
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

PIPELINE_STATES = {
    'queued',
    'parsing',
    'classifying',
    'extracting',
    'reconciling',
    'needs_review',
    'complete',
    'error'
}

# Module-level connection pool (lazy-initialized)
_pool = None


def _get_pool():
    """Get or create the connection pool (lazy initialization)."""
    global _pool
    if _pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=database_url
        )
    return _pool


def get_connection():
    """Get a database connection from the pool."""
    return _get_pool().getconn()


def _return_connection(conn):
    """Return a connection to the pool."""
    try:
        _get_pool().putconn(conn)
    except Exception:
        pass


@contextmanager
def get_db():
    """Context manager for database connections. Returns connection to pool on exit."""
    conn = get_connection()
    try:
        yield conn
    finally:
        _return_connection(conn)


def create_audit(audit_id: str, upload_filename: Optional[str] = None, user_id: Optional[str] = None) -> None:
    """
    Initialize a new audit record with 'queued' status.

    Args:
        audit_id: UUID string for the audit
        upload_filename: Optional original filename of uploaded zip
        user_id: Optional UUID string of the user who created the audit
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audits (id, status, pipeline_state, progress, upload_filename, user_id, review_required, quality_report)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    audit_id,
                    'queued',
                    'queued',
                    'Queued for processing',
                    upload_filename,
                    user_id,
                    False,
                    Json({})
                )
            )
        conn.commit()


def update_progress(audit_id: str, progress_message: str, pipeline_state: Optional[str] = None) -> None:
    """
    Update the progress message for an audit (for real-time frontend updates).
    Failures are logged but don't raise exceptions to avoid crashing the pipeline.

    Args:
        audit_id: UUID of the audit
        progress_message: Human-readable progress text (e.g., "Classifying document 12/47...")
        pipeline_state: Optional explicit pipeline state
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                if pipeline_state:
                    state = (pipeline_state or '').strip().lower()
                    if state not in PIPELINE_STATES:
                        raise ValueError(f"Invalid pipeline_state '{pipeline_state}'")
                    cur.execute(
                        "UPDATE audits SET progress = %s, pipeline_state = %s, status = %s WHERE id = %s",
                        (progress_message, state, state, audit_id)
                    )
                else:
                    cur.execute(
                        "UPDATE audits SET progress = %s WHERE id = %s",
                        (progress_message, audit_id)
                    )
            conn.commit()
    except Exception as e:
        # Log error but don't crash - progress updates are non-critical
        logger.error(f"Failed to update progress for audit {audit_id}: {e}")


def append_issues(audit_id: str, new_issues: list) -> None:
    """
    Append new issues to an existing audit's issues list.
    Used by cap table tie-out to add comparison results after the main pipeline.
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE audits
                    SET issues = COALESCE(issues, '[]'::jsonb) || %s::jsonb
                    WHERE id = %s
                    """,
                    (Json(new_issues), audit_id)
                )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to append issues for audit {audit_id}: {e}")


def update_audit_state(
    audit_id: str,
    status: str,
    progress_message: Optional[str] = None,
    review_required: Optional[bool] = None
) -> None:
    """
    Update explicit audit status/pipeline state.

    Args:
        audit_id: UUID of the audit
        status: One of PIPELINE_STATES
        progress_message: Optional human readable status text
        review_required: Optional review_required override
    """
    normalized = (status or '').strip().lower()
    if normalized not in PIPELINE_STATES:
        raise ValueError(f"Invalid status '{status}'")

    with get_db() as conn:
        with conn.cursor() as cur:
            if review_required is None:
                cur.execute(
                    """
                    UPDATE audits
                    SET status = %s,
                        pipeline_state = %s,
                        progress = COALESCE(%s, progress)
                    WHERE id = %s
                    """,
                    (normalized, normalized, progress_message, audit_id)
                )
            else:
                cur.execute(
                    """
                    UPDATE audits
                    SET status = %s,
                        pipeline_state = %s,
                        progress = COALESCE(%s, progress),
                        review_required = %s
                    WHERE id = %s
                    """,
                    (normalized, normalized, progress_message, review_required, audit_id)
                )
        conn.commit()


def update_audit_results(
    audit_id: str,
    results: Dict[str, Any],
    review_required: bool = False,
    quality_report: Optional[Dict[str, Any]] = None
) -> None:
    """
    Save final audit results and mark as complete or needs_review.

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
    final_status = 'needs_review' if review_required else 'complete'
    final_progress = 'Manual review required before finalization' if review_required else 'Audit complete'
    final_quality_report = quality_report or {}

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE audits
                SET status = %s,
                    pipeline_state = %s,
                    progress = %s,
                    company_name = %s,
                    documents = %s,
                    timeline = %s,
                    cap_table = %s,
                    issues = %s,
                    failed_documents = %s,
                    review_required = %s,
                    quality_report = %s
                WHERE id = %s
                """,
                (
                    final_status,
                    final_status,
                    final_progress,
                    results.get('company_name'),
                    Json(results.get('documents', [])),
                    Json(results.get('timeline', [])),
                    Json(results.get('cap_table', [])),
                    Json(results.get('issues', [])),
                    Json(results.get('failed_documents', [])),
                    review_required,
                    Json(final_quality_report),
                    audit_id
                )
            )
        conn.commit()


def mark_error(audit_id: str, error_message: str) -> None:
    """
    Mark an audit as failed with an error message.

    Args:
        audit_id: UUID of the audit
        error_message: Description of what went wrong
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE audits
                SET status = %s,
                    pipeline_state = %s,
                    progress = %s,
                    error_message = %s,
                    review_required = %s
                WHERE id = %s
                """,
                ('error', 'error', 'Processing failed', error_message, True, audit_id)
            )
        conn.commit()


def get_audit(audit_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve an audit record by ID.

    Args:
        audit_id: UUID of the audit

    Returns:
        Dictionary with audit data, or None if not found
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM audits WHERE id = %s", (audit_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_all_audits(user_id: Optional[str] = None) -> list[Dict[str, Any]]:
    """
    Retrieve all audits with summary metadata, sorted by most recent first.
    Returns lightweight list (not full results).

    Args:
        user_id: Optional UUID string to filter audits by user

    Returns:
        List of audit dictionaries with summary fields
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT
                        id,
                        created_at,
                        status,
                        company_name,
                        upload_filename,
                        COALESCE(jsonb_array_length(documents), 0) as document_count
                    FROM audits
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id,)
                )
            else:
                cur.execute(
                    """
                    SELECT
                        id,
                        created_at,
                        status,
                        company_name,
                        upload_filename,
                        COALESCE(jsonb_array_length(documents), 0) as document_count
                    FROM audits
                    ORDER BY created_at DESC
                    """
                )
            rows = cur.fetchall()
            return [dict(row) for row in rows]


def delete_audit(audit_id: str, user_id: str) -> bool:
    """Delete an audit owned by the given user. Returns True if a row was deleted."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM audits WHERE id = %s AND user_id = %s",
                (audit_id, user_id)
            )
        conn.commit()
        return cur.rowcount > 0


# ============================================================================
# CRUD Operations for Cap Table Tie-Out Feature
# ============================================================================

def insert_document(audit_id: str, filename: str, classification: Optional[str] = None,
                    extracted_data: Optional[Dict] = None, full_text: Optional[str] = None,
                    parse_status: str = 'success', parse_error: Optional[str] = None) -> str:
    """
    Insert a document record and return its UUID.

    Args:
        audit_id: UUID of the parent audit
        filename: Original filename
        classification: Document type (e.g., 'Stock Purchase Agreement')
        extracted_data: Structured data from Pass 2
        full_text: Parsed document text
        parse_status: Parsing status ('success', 'partial', 'error', 'skipped')
        parse_error: Error message if parse failed

    Returns:
        UUID string of the created document
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (audit_id, filename, classification, extracted_data, full_text, parse_status, parse_error)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (audit_id, filename, classification, Json(extracted_data) if extracted_data else None, full_text, parse_status, parse_error)
            )
            doc_id = cur.fetchone()[0]
        conn.commit()
        return str(doc_id)


def insert_documents_and_events(audit_id: str, documents: list, events: list) -> Dict[str, str]:
    """
    Insert all documents and equity events in a single transaction.
    If any insertion fails, the entire transaction is rolled back.

    Args:
        audit_id: UUID of the audit
        documents: List of document dicts with filename, category, text, etc.
        events: List of equity event dicts

    Returns:
        Dict mapping filename to document UUID
    """
    doc_ids: Dict[str, str] = {}
    with get_db() as conn:
        try:
            with conn.cursor() as cur:
                # Insert all documents
                for doc in documents:
                    cur.execute(
                        """
                        INSERT INTO documents (audit_id, filename, classification, extracted_data, full_text, parse_status, parse_error)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            audit_id,
                            doc.get('filename', 'unknown'),
                            doc.get('category'),
                            Json(doc.get('extracted_data')) if doc.get('extracted_data') else None,
                            doc.get('text'),
                            doc.get('parse_status', 'success'),
                            doc.get('parse_error')
                        )
                    )
                    doc_id = str(cur.fetchone()[0])
                    source_key = str(doc.get('id') or doc.get('filename') or f"row_{len(doc_ids)}")
                    doc_ids[source_key] = doc_id

                    # Backward-compatible fallback key for older callers.
                    filename_key = str(doc.get('filename') or 'unknown')
                    if filename_key not in doc_ids:
                        doc_ids[filename_key] = doc_id

                # Insert all equity events
                for event in events:
                    cur.execute(
                        """
                        INSERT INTO equity_events (
                            audit_id, event_date, event_type, shareholder_name, share_class, share_delta,
                            source_doc_id, source_snippet, approval_doc_id, approval_snippet,
                            compliance_status, compliance_note, details, preview_image, summary
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                            Json(event.get('details', {})),
                            event.get('preview_image'),
                            event.get('summary')
                        )
                    )
            conn.commit()
            logger.info(f"Transaction committed: {len(documents)} documents, {len(events)} events for audit {audit_id}")
            return doc_ids
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction rolled back for audit {audit_id}: {e}", exc_info=True)
            raise


def get_documents_by_audit(audit_id: str) -> list[Dict[str, Any]]:
    """
    Retrieve all documents for an audit.

    Args:
        audit_id: UUID of the audit

    Returns:
        List of document dictionaries
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM documents WHERE audit_id = %s ORDER BY created_at",
                (audit_id,)
            )
            return [dict(row) for row in cur.fetchall()]


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

    with get_db() as conn:
        with conn.cursor() as cur:
            for event in events:
                cur.execute(
                    """
                    INSERT INTO equity_events (
                        audit_id, event_date, event_type, shareholder_name, share_class, share_delta,
                        source_doc_id, source_snippet, approval_doc_id, approval_snippet,
                        compliance_status, compliance_note, details, preview_image, summary
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        Json(event.get('details', {})),
                        event.get('preview_image'),
                        event.get('summary')
                    )
                )
        conn.commit()


def get_equity_events_by_audit(audit_id: str) -> list[Dict[str, Any]]:
    """
    Retrieve all equity events for an audit, ordered by date.

    Args:
        audit_id: UUID of the audit

    Returns:
        List of equity event dictionaries
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, event_date, event_type, shareholder_name, share_class, share_delta,
                       source_doc_id, source_snippet, approval_doc_id, approval_snippet,
                       compliance_status, compliance_note, details, preview_image, summary
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


def get_option_grants(audit_id: str, as_of_date: Optional[str] = None) -> list[Dict[str, Any]]:
    """
    Retrieve option grants for an audit, optionally filtered by date.

    Args:
        audit_id: Audit UUID
        as_of_date: Optional date filter (YYYY-MM-DD)

    Returns:
        List of option grant dicts with recipient, shares, strike_price, etc.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if as_of_date:
                cur.execute(
                    """
                    SELECT
                        shareholder_name as recipient,
                        share_delta as shares,
                        event_date as grant_date,
                        details->>'strike_price' as strike_price,
                        details->>'vesting_schedule' as vesting_schedule,
                        source_doc_id
                    FROM equity_events
                    WHERE audit_id = %s
                      AND event_type = 'option_grant'
                      AND event_date <= %s
                    ORDER BY event_date DESC
                    """,
                    (audit_id, as_of_date)
                )
            else:
                cur.execute(
                    """
                    SELECT
                        shareholder_name as recipient,
                        share_delta as shares,
                        event_date as grant_date,
                        details->>'strike_price' as strike_price,
                        details->>'vesting_schedule' as vesting_schedule,
                        source_doc_id
                    FROM equity_events
                    WHERE audit_id = %s
                      AND event_type = 'option_grant'
                    ORDER BY event_date DESC
                    """,
                    (audit_id,)
                )

            rows = cur.fetchall()

            options = []
            for row in rows:
                options.append({
                    'recipient': row['recipient'],
                    'shares': int(row['shares']) if row['shares'] else 0,
                    'grant_date': row['grant_date'],
                    'strike_price': float(row['strike_price']) if row['strike_price'] else 0.0,
                    'vesting_schedule': row['vesting_schedule'] or 'Not specified',
                    'source_doc_id': str(row['source_doc_id']) if row['source_doc_id'] else None
                })

            return options


def get_document_by_id(doc_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single document by its ID.

    Args:
        doc_id: UUID of the document

    Returns:
        Dictionary with document data, or None if not found
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, audit_id, filename, classification, extracted_data, full_text, parse_status, parse_error, created_at
                FROM documents
                WHERE id = %s
                """,
                (doc_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None


# ============================================================================
# User Authentication CRUD Operations
# ============================================================================

def create_user(username: str, password_hash: str) -> str:
    """
    Create a new user and return their UUID.

    Args:
        username: Unique username
        password_hash: Bcrypt password hash

    Returns:
        UUID string of the created user
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (%s, %s)
                RETURNING id
                """,
                (username, password_hash)
            )
            user_id = cur.fetchone()[0]
        conn.commit()
        return str(user_id)


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """
    Get user by username.

    Args:
        username: Username to search for

    Returns:
        Dictionary with user data (id, username, password_hash, created_at), or None if not found
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, password_hash, created_at FROM users WHERE username = %s",
                (username,)
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user by ID.

    Args:
        user_id: UUID string of the user

    Returns:
        Dictionary with user data (id, username, created_at), or None if not found
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, created_at FROM users WHERE id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None


def create_access_request(email: str) -> None:
    """
    Store an access code request email.

    Args:
        email: Email address requesting access
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO access_requests (email) VALUES (%s)",
                (email,)
            )
        conn.commit()


def create_session(session_token: str, user_id: str, expires_at: datetime, csrf_token: str) -> None:
    """
    Persist a user session in the database.
    """
    params = (session_token, user_id, csrf_token, expires_at)
    with get_db() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sessions (session_token, user_id, csrf_token, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (session_token)
                    DO UPDATE SET user_id = EXCLUDED.user_id,
                                  csrf_token = EXCLUDED.csrf_token,
                                  expires_at = EXCLUDED.expires_at
                    """,
                    params
                )
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_token TEXT PRIMARY KEY,
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        csrf_token TEXT NOT NULL,
                        expires_at TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
                cur.execute(
                    """
                    INSERT INTO sessions (session_token, user_id, csrf_token, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (session_token)
                    DO UPDATE SET user_id = EXCLUDED.user_id,
                                  csrf_token = EXCLUDED.csrf_token,
                                  expires_at = EXCLUDED.expires_at
                    """,
                    params
                )
        conn.commit()


def get_session(session_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a session if present and not expired.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(
                    """
                    SELECT session_token, user_id, csrf_token, expires_at, created_at
                    FROM sessions
                    WHERE session_token = %s
                    """,
                    (session_token,)
                )
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                return None
            row = cur.fetchone()
            if not row:
                return None

            session = dict(row)
            expires_at = session.get('expires_at')
            if expires_at and expires_at <= datetime.utcnow():
                cur.execute("DELETE FROM sessions WHERE session_token = %s", (session_token,))
                conn.commit()
                return None

            return session


def delete_session(session_token: str) -> None:
    """
    Delete one session token.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE session_token = %s", (session_token,))
        conn.commit()


def cleanup_expired_sessions() -> int:
    """
    Delete expired sessions and return deleted row count.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM sessions WHERE expires_at <= NOW()")
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                return 0
            deleted = cur.rowcount or 0
        conn.commit()
        return deleted


def run_migrations() -> int:
    """
    Apply pending SQL migrations from the migrations/ directory.
    Tracks applied migrations in a schema_migrations table.
    Returns the number of newly applied migrations.
    """
    import glob

    migrations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations')
    if not os.path.isdir(migrations_dir):
        logger.info("No migrations directory found, skipping.")
        return 0

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT NOW()
                )
            """)
        conn.commit()

    migration_files = sorted(glob.glob(os.path.join(migrations_dir, '*.sql')))
    applied_count = 0

    for filepath in migration_files:
        filename = os.path.basename(filepath)

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (filename,))
                if cur.fetchone():
                    continue

        with open(filepath, 'r') as f:
            sql = f.read()

        with get_db() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (filename,))
                conn.commit()
                applied_count += 1
                logger.info(f"Applied migration: {filename}")
            except Exception as e:
                conn.rollback()
                logger.error(f"Migration {filename} failed: {e}")
                raise

    return applied_count
