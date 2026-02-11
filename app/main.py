"""
FastAPI backend for Corporate Governance Audit Platform.

Routes:
- GET / - Serve the main HTML interface
- POST /upload - Accept zip file upload and start processing
- GET /status/{audit_id} - Poll audit status and retrieve results
"""

import os
import uuid
import shutil
import tempfile
import logging
import multiprocessing
from queue import Empty as QueueEmpty
from threading import Lock
from collections import deque
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from collections import defaultdict
from fastapi import FastAPI, UploadFile, BackgroundTasks, HTTPException, Query, Depends, Request, Response, Form
from io import BytesIO
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables FIRST (before importing app modules that use them)
load_dotenv('.env.local')  # Load local overrides first
load_dotenv()  # Load .env as fallback

from app import db, utils, processing, auth

logger = logging.getLogger(__name__)

# Validate required env vars
if not os.getenv("ANTHROPIC_API_KEY"):
    raise ValueError("ANTHROPIC_API_KEY environment variable not set")
if not os.getenv("DATABASE_URL"):
    raise ValueError("DATABASE_URL environment variable not set")


def _env_flag(name: str, default: bool = False) -> bool:
    """
    Parse common truthy/falsey env var values.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Initialize FastAPI app
app = FastAPI(
    title="Corporate Governance Audit Platform",
    description="AI-powered document analysis for corporate governance audits",
    version="1.0.0"
)

# CORS middleware
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "https://tieout.onrender.com,http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

# Basic in-memory rate limiter (per-process)
_rate_limit_lock = Lock()
_rate_limit_buckets: Dict[str, deque] = {}


def _enforce_rate_limit(scope: str, key: str, limit: int, window_seconds: int) -> None:
    """
    Sliding-window rate limit. Raises HTTPException(429) when exceeded.
    """
    bucket_key = f"{scope}:{key}"
    now = datetime.utcnow().timestamp()
    cutoff = now - window_seconds

    with _rate_limit_lock:
        events = _rate_limit_buckets.setdefault(bucket_key, deque())
        while events and events[0] < cutoff:
            events.popleft()

        if len(events) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests for {scope}. Please wait and try again."
            )

        events.append(now)


def _client_identity(request: Request) -> str:
    """
    Get client identity for rate limiting.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Attach baseline security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

# Mount static files (CSS, JS, HTML)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.post("/api/auth/login")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...)
):
    """
    Authenticate user with username and password.
    Sets session cookie on success.

    Args:
        username: Username
        password: Plaintext password

    Returns:
        Success message with username

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    _enforce_rate_limit("login", _client_identity(request), limit=12, window_seconds=60)

    # Get user from database
    user = db.get_user_by_username(username)

    if not user or not auth.verify_password(password, user['password_hash']):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # Create session
    session_token, csrf_token = auth.create_session(str(user['id']))

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=60 * 60 * 24,  # 24 hours
        samesite="lax",
        path="/"
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        max_age=60 * 60 * 24,
        samesite="lax",
        path="/"
    )

    return {"message": "Login successful", "username": user['username'], "csrf_token": csrf_token}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """
    Logout user by deleting session.

    Returns:
        Success message
    """
    auth.validate_csrf(request)

    session_token = request.cookies.get("session_token")
    if session_token:
        auth.delete_session(session_token)

    response.delete_cookie("session_token")
    response.delete_cookie("csrf_token")
    return {"message": "Logout successful"}


@app.get("/api/auth/me")
async def get_current_user_info(user_id: str = Depends(auth.get_current_user)):
    """
    Get current authenticated user info.

    Returns:
        User information (id, username)

    Raises:
        HTTPException: 401 if not authenticated
    """
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"user_id": str(user['id']), "username": user['username']}


@app.post("/api/access-request")
async def request_access(request: Request, email: str = Form(...)):
    """
    Store access code request email.

    Args:
        email: Email address requesting access

    Returns:
        Success message

    Raises:
        HTTPException: 400 if email is invalid
    """
    _enforce_rate_limit("access_request", _client_identity(request), limit=15, window_seconds=300)

    # Basic email validation
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    db.create_access_request(email)

    return {"message": "Access request submitted"}


# ============================================================================
# MAIN APPLICATION ROUTES
# ============================================================================

@app.get("/")
async def root(user_id: Optional[str] = Depends(auth.get_current_user_optional)):
    """
    Serve landing page if not authenticated, otherwise redirect to app.

    Returns:
        Landing page HTML or redirect to /app
    """
    if user_id:
        return RedirectResponse(url="/app")
    return FileResponse("static/landing.html")


@app.get("/app")
async def app_page(user_id: str = Depends(auth.get_current_user)):
    """
    Serve main application (requires authentication).

    Returns:
        Main application HTML

    Raises:
        HTTPException: 401 if not authenticated
    """
    return FileResponse("static/index.html")


@app.post("/upload")
async def upload_audit(
    request: Request,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(auth.get_current_user),
    captable: Optional[UploadFile] = None
):
    """
    Accept a zip file upload and optional Carta cap table, then start background processing.
    Requires authentication.

    Args:
        file: UploadFile object from multipart form (.zip)
        background_tasks: FastAPI background tasks manager
        user_id: Authenticated user ID (from session)
        captable: Optional Carta cap table export (.xlsx)

    Returns:
        JSON with audit_id for status polling

    Raises:
        HTTPException: 401 if not authenticated, 400 if invalid file
    """
    auth.validate_csrf(request)
    _enforce_rate_limit("upload", f"{user_id}:{_client_identity(request)}", limit=20, window_seconds=3600)

    # Validate file type
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    # Generate unique audit ID
    audit_id = str(uuid.uuid4())

    # Save uploaded file to temp location
    temp_zip_path = os.path.join(tempfile.gettempdir(), f"{audit_id}.zip")

    try:
        with open(temp_zip_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.error(f"Failed to save upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Upload failed. Please try again.")

    # Validate zip file
    is_valid, error_msg = utils.validate_zip_file(temp_zip_path, max_size_mb=50)
    if not is_valid:
        os.remove(temp_zip_path)
        raise HTTPException(status_code=400, detail=error_msg)

    # Save cap table file if provided
    temp_captable_path = None
    if captable and captable.filename and captable.filename.endswith('.xlsx'):
        temp_captable_path = os.path.join(tempfile.gettempdir(), f"{audit_id}_captable.xlsx")
        try:
            with open(temp_captable_path, "wb") as f:
                shutil.copyfileobj(captable.file, f)
        except Exception as e:
            logger.warning(f"Failed to save cap table upload: {e}")
            temp_captable_path = None

    # Create audit record in database with user_id
    try:
        db.create_audit(audit_id, upload_filename=file.filename, user_id=user_id)
    except Exception as e:
        os.remove(temp_zip_path)
        if temp_captable_path and os.path.exists(temp_captable_path):
            os.remove(temp_captable_path)
        logger.error(f"Database error creating audit: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start audit. Please try again.")

    # Start background processing
    background_tasks.add_task(process_documents_task, audit_id, temp_zip_path, temp_captable_path)

    return {"audit_id": audit_id, "message": "Processing started"}


@app.get("/status/{audit_id}")
async def get_status(audit_id: str, user_id: str = Depends(auth.get_current_user)):
    """
    Get the status and results of an audit.
    Requires authentication and audit ownership.

    Args:
        audit_id: UUID of the audit
        user_id: Authenticated user ID (from session)

    Returns:
        JSON with status, progress, and results (if complete)

    Raises:
        HTTPException: 401 if not authenticated, 404 if audit not found, 403 if access denied
    """
    try:
        audit = db.get_audit(audit_id)
    except Exception as e:
        logger.error(f"Database error fetching audit {audit_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve audit status. Please try again.")

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    # Verify audit belongs to requesting user
    if audit.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    response = {
        "status": audit['status'],
        "pipeline_state": audit.get('pipeline_state') or audit['status'],
        "progress": audit.get('progress', ''),
        "quality_report": audit.get('quality_report') or {},
        "review_required": bool(audit.get('review_required')),
        "results": None,
        "error": None
    }

    if audit['status'] in {'complete', 'needs_review'}:
        response['results'] = {
            "company_name": audit.get('company_name'),
            "documents": audit.get('documents'),
            "timeline": audit.get('timeline'),
            "cap_table": audit.get('cap_table'),
            "issues": audit.get('issues'),
            "failed_documents": audit.get('failed_documents')
        }
    elif audit['status'] == 'error':
        response['error'] = audit.get('error_message')

    return JSONResponse(content=response)


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "corporate-audit-api"}


@app.get("/api/audits")
async def list_audits(user_id: str = Depends(auth.get_current_user)):
    """
    List all past audits with summary metadata for authenticated user.
    Requires authentication.

    Args:
        user_id: Authenticated user ID (from session)

    Returns:
        List of audit summaries: [{
            id: UUID string,
            created_at: timestamp,
            status: str,
            company_name: str | null,
            upload_filename: str | null,
            document_count: int
        }]

    Raises:
        HTTPException: 401 if not authenticated
    """
    try:
        # Get audits filtered by user_id
        audits = db.get_all_audits(user_id=user_id)

        # Convert UUIDs to strings and timestamps to ISO format
        for audit in audits:
            audit['id'] = str(audit['id'])
            if audit['created_at']:
                audit['created_at'] = audit['created_at'].isoformat()

        return JSONResponse(content=audits)
    except Exception as e:
        logger.error(f"Failed to fetch audits: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load audit history. Please try again.")


# ============================================================================
# CAP TABLE TIE-OUT ENDPOINTS
# ============================================================================

# Pydantic models for type-safe responses
class EquityEvent(BaseModel):
    """Model for a single equity transaction event."""
    id: str
    event_date: date
    event_type: str
    shareholder_name: Optional[str]
    share_class: Optional[str]
    share_delta: float
    source_doc_id: Optional[str]
    source_snippet: Optional[str]
    approval_doc_id: Optional[str]
    approval_snippet: Optional[str]
    compliance_status: str
    compliance_note: Optional[str]
    details: Dict[str, Any]
    preview_image: Optional[str]
    summary: Optional[str]


class CapTableRow(BaseModel):
    """Model for a single row in the cap table."""
    shareholder: str
    share_class: str
    shares: float
    ownership_pct: float
    compliance_issues: List[str]


class CapTableState(BaseModel):
    """Model for the full cap table at a point in time."""
    as_of_date: date
    total_shares: float
    shareholders: List[CapTableRow]


@app.get("/api/audits/{audit_id}/events", response_model=List[EquityEvent])
async def get_equity_events(audit_id: str, user_id: str = Depends(auth.get_current_user)):
    """
    Fetch all equity events for an audit (for time-travel cap table).
    Called once when the audit view loads. Requires authentication.

    Args:
        audit_id: UUID of the audit
        user_id: Authenticated user ID (from session)

    Returns:
        List of equity events ordered by date

    Raises:
        HTTPException: 401 if not authenticated, 404 if audit not found
    """
    try:
        # Check if audit exists and belongs to user
        audit = db.get_audit(audit_id)
        if not audit or str(audit.get('user_id', '')) != user_id:
            raise HTTPException(status_code=404, detail="Audit not found")

        # Fetch equity events
        events = db.get_equity_events_by_audit(audit_id)

        # Convert UUIDs to strings and dates to ISO format
        for event in events:
            event['id'] = str(event['id'])
            if event.get('source_doc_id'):
                event['source_doc_id'] = str(event['source_doc_id'])
            if event.get('approval_doc_id'):
                event['approval_doc_id'] = str(event['approval_doc_id'])

        return events

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load equity events. Please try again.")


@app.get("/api/audits/{audit_id}/captable", response_model=CapTableState)
async def get_cap_table_at_time(
    audit_id: str,
    user_id: str = Depends(auth.get_current_user),
    as_of_date: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD), defaults to today")
):
    """
    Calculate cap table at a specific point in time (time-travel feature).
    Called repeatedly as user moves the time slider. Requires authentication.

    Args:
        audit_id: UUID of the audit
        user_id: Authenticated user ID (from session)
        as_of_date: Optional ISO date string (YYYY-MM-DD). If None, uses today's date.

    Returns:
        Cap table state with shareholders and ownership percentages

    Raises:
        HTTPException: 401 if not authenticated, 404 if audit not found
    """
    try:
        # Check if audit exists and belongs to user
        audit = db.get_audit(audit_id)
        if not audit or str(audit.get('user_id', '')) != user_id:
            raise HTTPException(status_code=404, detail="Audit not found")

        # Parse date filter
        if as_of_date:
            try:
                cutoff_date = datetime.fromisoformat(as_of_date).date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        else:
            cutoff_date = date.today()

        # Get cached events (or fetch from DB)
        events = _get_equity_events(audit_id)

        if not events:
            # No events found - return empty cap table
            return CapTableState(
                as_of_date=cutoff_date,
                total_shares=0,
                shareholders=[]
            )

        # Filter events by date
        filtered_events = [
            e for e in events
            if e['event_date'] <= cutoff_date
        ]

        # Aggregate in Python (simple dict-based aggregation)
        # Key: (shareholder, share_class) -> shares
        cap_table_dict = defaultdict(lambda: defaultdict(float))
        issues_by_shareholder = defaultdict(list)

        for event in filtered_events:
            shareholder = event.get('shareholder_name')
            if not shareholder:
                continue  # Skip formation events and other non-equity events

            share_class = event.get('share_class') or 'Common Stock'
            delta = float(event.get('share_delta', 0))  # Convert Decimal to float (safety measure)

            cap_table_dict[shareholder][share_class] += delta

            # Collect compliance issues
            if event.get('compliance_status') in ['WARNING', 'CRITICAL']:
                note = event.get('compliance_note')
                if note and note not in issues_by_shareholder[shareholder]:
                    issues_by_shareholder[shareholder].append(note)

        # Calculate totals and build response
        shareholders = []
        for shareholder, classes in cap_table_dict.items():
            for share_class, shares in classes.items():
                if shares > 0:  # Only show active positions (positive shares)
                    shareholders.append({
                        'shareholder': shareholder,
                        'share_class': share_class,
                        'shares': shares,
                        'compliance_issues': issues_by_shareholder.get(shareholder, [])
                    })

        # Calculate total shares
        total_shares = float(sum(sh['shares'] for sh in shareholders))

        # Calculate ownership percentages
        for sh in shareholders:
            sh['ownership_pct'] = round((float(sh['shares']) / total_shares * 100), 2) if total_shares > 0 else 0.0

        # Sort by ownership descending
        shareholders.sort(key=lambda x: x['shares'], reverse=True)

        return CapTableState(
            as_of_date=cutoff_date,
            total_shares=total_shares,
            shareholders=[CapTableRow(**sh) for sh in shareholders]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to calculate cap table: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to calculate cap table. Please try again.")


@app.get("/api/audits/{audit_id}/options")
async def get_option_pool(
    audit_id: str,
    user_id: str = Depends(auth.get_current_user),
    as_of_date: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD)")
):
    """
    Get option pool grants as of a specific date.
    Returns list of option grants (not included in issued cap table).

    Args:
        audit_id: UUID of the audit
        user_id: Authenticated user ID (from session)
        as_of_date: Optional ISO date string (YYYY-MM-DD)

    Returns:
        List of option grants with recipient, shares, strike price, etc.
    """
    try:
        # Verify ownership
        audit = db.get_audit(audit_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        if str(audit.get('user_id', '')) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Parse date filter
        if as_of_date:
            try:
                cutoff_date = datetime.fromisoformat(as_of_date).date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        else:
            cutoff_date = None

        # Get option grants from database
        options = db.get_option_grants(audit_id, as_of_date)

        return options

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get option pool: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load option pool. Please try again.")


def _get_equity_events(audit_id: str) -> List[Dict[str, Any]]:
    """
    Fetch equity events from database.

    Args:
        audit_id: UUID of the audit

    Returns:
        List of equity events
    """
    return db.get_equity_events_by_audit(audit_id)


@app.get("/api/audits/{audit_id}/documents/{doc_id}")
async def get_document(audit_id: str, doc_id: str, user_id: str = Depends(auth.get_current_user)):
    """
    Fetch a single document by ID (for document viewer modal).
    Requires authentication.

    Args:
        audit_id: UUID of the audit (for validation)
        doc_id: UUID of the document
        user_id: Authenticated user ID (from session)

    Returns:
        Document data including full text and extracted data

    Raises:
        HTTPException: 401 if not authenticated, 404 if document not found
    """
    try:
        # Verify audit belongs to user
        audit = db.get_audit(audit_id)
        if not audit or str(audit.get('user_id', '')) != user_id:
            raise HTTPException(status_code=404, detail="Document not found")

        # Fetch document
        document = db.get_document_by_id(doc_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Verify document belongs to this audit
        if str(document['audit_id']) != audit_id:
            raise HTTPException(status_code=404, detail="Document not found")

        # Convert UUID to string for JSON serialization
        document['id'] = str(document['id'])
        document['audit_id'] = str(document['audit_id'])

        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load document. Please try again.")


# ============================================================================
# DOCUMENT DOWNLOADS & PREVIEWS
# ============================================================================

@app.get("/api/audits/{audit_id}/download/minute-book")
async def download_minute_book(audit_id: str, user_id: str = Depends(auth.get_current_user)):
    """
    Download Minute Book Index as Word document.

    Args:
        audit_id: UUID of the audit
        user_id: Authenticated user ID

    Returns:
        FileResponse with .docx file

    Raises:
        HTTPException: 403 if access denied, 500 if generation fails
    """
    from app import docgen
    import tempfile

    try:
        # Verify audit belongs to user
        audit = db.get_audit(audit_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")

        if str(audit.get('user_id')) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Generate Word document
        docx_bytes = docgen.generate_minute_book(audit_id)

        # Stream directly from memory
        company_name = audit.get('company_name', 'Company').replace(' ', '_')
        filename = f"{company_name}_Minute_Book_Index.docx"

        return StreamingResponse(
            BytesIO(docx_bytes),
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate minute book: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate minute book. Please try again.")


@app.get("/api/audits/{audit_id}/download/issues")
async def download_issues_report(audit_id: str, user_id: str = Depends(auth.get_current_user)):
    """
    Download Critical Issues Report as Word document.

    Args:
        audit_id: UUID of the audit
        user_id: Authenticated user ID

    Returns:
        FileResponse with .docx file

    Raises:
        HTTPException: 403 if access denied, 500 if generation fails
    """
    from app import docgen
    import tempfile

    try:
        # Verify audit belongs to user
        audit = db.get_audit(audit_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")

        if str(audit.get('user_id')) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Generate Word document
        docx_bytes = docgen.generate_issues_report(audit_id)

        # Stream directly from memory
        company_name = audit.get('company_name', 'Company').replace(' ', '_')
        filename = f"{company_name}_Critical_Issues_Report.docx"

        return StreamingResponse(
            BytesIO(docx_bytes),
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate issues report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate issues report. Please try again.")


@app.get("/api/audits/{audit_id}/download/minute-document")
async def download_minute_document_pdf(audit_id: str, user_id: str = Depends(auth.get_current_user)):
    """
    Download comprehensive Minute Document as PDF.
    Includes cap table, equity events with tieouts, issues, and document index.

    Args:
        audit_id: UUID of the audit
        user_id: Authenticated user ID

    Returns:
        FileResponse with .pdf file

    Raises:
        HTTPException: 403 if access denied, 500 if generation fails
    """
    from app import minute_document
    import tempfile

    try:
        # Verify audit belongs to user
        audit = db.get_audit(audit_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")

        if str(audit.get('user_id')) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Get equity events
        equity_events = db.get_equity_events_by_audit(audit_id)

        # Get documents
        documents = db.get_documents_by_audit(audit_id)

        # Generate PDF
        pdf_bytes = minute_document.generate_minute_document(
            audit_data=audit,
            equity_events=equity_events,
            documents=documents
        )

        # Stream directly from memory
        company_name = audit.get('company_name', 'Company').replace(' ', '_')
        filename = f"{company_name}_Audit_Summary.pdf"

        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate minute document PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate minute document. Please try again.")


@app.get("/api/audits/{audit_id}/preview/minute-book")
async def preview_minute_book(audit_id: str, user_id: str = Depends(auth.get_current_user)):
    """
    Get text preview of Minute Book Index.

    Args:
        audit_id: UUID of the audit
        user_id: Authenticated user ID

    Returns:
        JSON with 'preview' field containing first ~200 words

    Raises:
        HTTPException: 403 if access denied
    """
    from app import docgen

    try:
        # Verify audit belongs to user
        audit = db.get_audit(audit_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")

        if str(audit.get('user_id')) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Generate preview
        preview = docgen.generate_minute_book_preview(audit_id)

        return {"preview": preview}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate minute book preview: {e}", exc_info=True)
        return {"preview": "Preview unavailable"}


@app.get("/api/audits/{audit_id}/preview/issues")
async def preview_issues_report(audit_id: str, user_id: str = Depends(auth.get_current_user)):
    """
    Get text preview of Critical Issues Report.

    Args:
        audit_id: UUID of the audit
        user_id: Authenticated user ID

    Returns:
        JSON with 'preview' field containing first ~200 words

    Raises:
        HTTPException: 403 if access denied
    """
    from app import docgen

    try:
        # Verify audit belongs to user
        audit = db.get_audit(audit_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")

        if str(audit.get('user_id')) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Generate preview
        preview = docgen.generate_issues_preview(audit_id)

        return {"preview": preview}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate issues preview: {e}", exc_info=True)
        return {"preview": "Preview unavailable"}


# ============================================================================
# BACKGROUND TASK
# ============================================================================

def _parse_document_worker(file_path: str, result_queue) -> None:
    """Isolated parser worker for hard timeout enforcement."""
    try:
        result_queue.put({
            'ok': True,
            'result': utils.parse_document_robust(file_path)
        })
    except Exception as exc:
        result_queue.put({
            'ok': False,
            'error': str(exc)
        })


def _parse_document_isolated(file_path: str, timeout_seconds: int) -> Dict[str, Any]:
    """
    Parse a single file in its own process so hung parsers can be terminated safely.
    """
    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lstrip('.')
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue(maxsize=1)
    proc = ctx.Process(target=_parse_document_worker, args=(file_path, result_queue))
    proc.start()
    proc.join(timeout_seconds)

    if proc.is_alive():
        proc.terminate()
        proc.join(2)
        return {
            'filename': filename,
            'type': ext,
            'text': '',
            'parse_status': 'error',
            'parse_error': f'Document parsing timed out after {timeout_seconds} seconds',
            'error': f'Document parsing timed out after {timeout_seconds} seconds'
        }

    try:
        payload = result_queue.get_nowait()
    except QueueEmpty:
        return {
            'filename': filename,
            'type': ext,
            'text': '',
            'parse_status': 'error',
            'parse_error': 'Parser exited without returning a result',
            'error': 'Parser exited without returning a result'
        }

    if payload.get('ok'):
        result = payload.get('result') or {}
        if result.get('error') and not result.get('parse_error'):
            result['parse_error'] = result['error']
        return result

    error_text = payload.get('error', 'Unknown parser error')
    return {
        'filename': filename,
        'type': ext,
        'text': '',
        'parse_status': 'error',
        'parse_error': error_text,
        'error': error_text
    }


def process_documents_task(audit_id: str, zip_path: str, captable_path: str = None):
    """
    Background task to process uploaded documents.
    Sync function to avoid blocking FastAPI event loop with sync DB/file operations.

    Args:
        audit_id: UUID of the audit
        zip_path: Path to the uploaded zip file
        captable_path: Optional path to uploaded Carta cap table (.xlsx)
    """
    extract_dir = None
    temp_dir = None

    try:
        logger.info(f"Starting processing for audit {audit_id}")

        # Update progress
        try:
            db.update_progress(audit_id, "Extracting files from archive...", pipeline_state='parsing')
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")

        # Use robust unzip with pre-validation, extension filtering, and error tracking
        extracted_files, skipped_files = utils.unzip_file_robust(zip_path)
        extract_dir = os.path.dirname(extracted_files[0]['path']) if extracted_files else None

        # Temp directory for PDF conversions (preview generation)
        temp_dir = tempfile.mkdtemp(prefix=f"audit_{audit_id}_")

        if not extracted_files:
            raise ValueError("No supported documents found in the archive")

        # Log skipped files for transparency
        if skipped_files:
            logger.info(f"Skipped {len(skipped_files)} files: {[s['original_name'] for s in skipped_files]}")

        logger.info(f"Extracted {len(extracted_files)} supported files for audit {audit_id}")

        try:
            db.update_progress(audit_id, f"Found {len(extracted_files)} documents. Parsing...", pipeline_state='parsing')
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")

        parser_timeout_seconds = int(os.getenv("PARSER_TIMEOUT_SECONDS", "45"))

        # Parse each document in an isolated process with hard timeout enforcement.
        documents = []
        for i, file_info in enumerate(extracted_files, start=1):
            file_path = file_info['path']
            filename = file_info['original_name']

            # Update progress every 5 docs, on first, and on last
            if i % 5 == 1 or i == 1 or i == len(extracted_files):
                try:
                    display_name = filename[:40] + "..." if len(filename) > 40 else filename
                    db.update_progress(
                        audit_id,
                        f"Parsing document {i}/{len(extracted_files)}: {display_name}",
                        pipeline_state='parsing'
                    )
                except Exception as e:
                    logger.error(f"Failed to update progress: {e}")

            doc_id = str(uuid.uuid4())
            logger.info(f"Parsing document {i}/{len(extracted_files)}: {filename}")

            # Determine file type and convert to PDF if needed for preview generation
            file_ext = os.path.splitext(filename)[1].lower()
            pdf_path = None
            text_spans = None

            try:
                if file_ext == '.pdf':
                    pdf_path = file_path
                # Skip Office→PDF conversion if LibreOffice not available
                elif file_ext in ['.docx', '.xlsx', '.pptx']:
                    import shutil
                    if shutil.which('libreoffice'):
                        logger.info(f"Converting {filename} to PDF for preview generation")
                        pdf_path = utils.convert_to_pdf(file_path, temp_dir)

                if pdf_path:
                    bbox_result = utils.parse_pdf_with_bboxes(pdf_path)
                    text_spans = bbox_result['text_spans']
                    logger.info(f"Extracted {len(text_spans)} text spans from {filename}")
            except Exception as e:
                logger.warning(f"Failed to extract bbox for {filename}: {e}")

            # Parse document in isolated worker with hard timeout.
            doc = _parse_document_isolated(file_path, parser_timeout_seconds)
            if doc.get('parse_status') in {'success', 'partial'}:
                logger.info(f"Successfully parsed: {filename} ({doc.get('parse_status')})")
            else:
                logger.error(f"Failed to parse {filename}: {doc.get('parse_error') or doc.get('error')}")

            # Use the original filename from the zip
            doc['filename'] = filename
            doc['id'] = doc_id
            if doc.get('error') and not doc.get('parse_error'):
                doc['parse_error'] = doc.get('error')
            if not doc.get('parse_status'):
                doc['parse_status'] = 'error' if doc.get('error') else 'success'
            if pdf_path:
                doc['pdf_path'] = pdf_path
            if text_spans:
                doc['text_spans'] = text_spans

            documents.append(doc)

        if not documents:
            raise ValueError("No parseable documents found")

        logger.info(f"Parsed {len(documents)} documents for audit {audit_id}")

        # Run AI processing pipeline
        processing.process_audit(audit_id, documents)

        # Tie out uploaded Carta cap table against generated cap table
        if captable_path and os.path.exists(captable_path):
            try:
                db.update_progress(
                    audit_id,
                    "Comparing uploaded cap table with source documents...",
                    pipeline_state='reconciling'
                )
                processing.tieout_carta_captable(audit_id, captable_path)
            except Exception as e:
                logger.warning(f"Cap table tie-out failed for audit {audit_id}: {e}")

        logger.info(f"Successfully completed audit {audit_id}")

    except Exception as e:
        logger.error(f"Processing failed for audit {audit_id}: {e}", exc_info=True)
        print(f"ERROR: Processing failed for audit {audit_id}: {e}")

        # Mark audit as failed
        try:
            db.mark_error(audit_id, str(e))
        except Exception as db_error:
            logger.error(f"Failed to mark error in database: {db_error}")
            print(f"CRITICAL: Failed to mark error in database for {audit_id}: {db_error}")

    finally:
        # Cleanup: delete temp files
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            if extract_dir and os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            if captable_path and os.path.exists(captable_path):
                os.remove(captable_path)
        except Exception:
            pass  # Ignore cleanup errors


# ============================================================================
# STARTUP
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        removed = db.cleanup_expired_sessions()
        if removed:
            logger.info(f"Removed {removed} expired sessions on startup")
    except Exception as e:
        logger.warning(f"Session cleanup failed on startup: {e}")

    print("🚀 Corporate Governance Audit Platform API started")
    print(f"📊 Database: {os.getenv('DATABASE_URL', 'Not configured')[:50]}...")
    print(f"🤖 Claude API: {'Configured' if os.getenv('ANTHROPIC_API_KEY') else 'NOT CONFIGURED'}")
