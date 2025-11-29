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
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from collections import defaultdict
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from fastapi import FastAPI, UploadFile, BackgroundTasks, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables FIRST (before importing app modules that use them)
load_dotenv('.env.local')  # Load local overrides first
load_dotenv()  # Load .env as fallback

from app import db, utils, processing

# Validate required env vars
if not os.getenv("ANTHROPIC_API_KEY"):
    raise ValueError("ANTHROPIC_API_KEY environment variable not set")
if not os.getenv("DATABASE_URL"):
    raise ValueError("DATABASE_URL environment variable not set")


# Initialize FastAPI app
app = FastAPI(
    title="Corporate Governance Audit Platform",
    description="AI-powered document analysis for corporate governance audits",
    version="1.0.0"
)

# CORS middleware (allow all origins for MVP)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (CSS, JS, HTML)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ============================================================================
# ROUTES
# ============================================================================

@app.get("/")
async def root():
    """Serve the main HTML interface."""
    return FileResponse("static/index.html")


@app.post("/upload")
async def upload_audit(
    file: UploadFile,
    background_tasks: BackgroundTasks
):
    """
    Accept a zip file upload and start background processing.

    Args:
        file: UploadFile object from multipart form
        background_tasks: FastAPI background tasks manager

    Returns:
        JSON with audit_id for status polling
    """
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
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

    # Validate zip file
    is_valid, error_msg = utils.validate_zip_file(temp_zip_path, max_size_mb=50)
    if not is_valid:
        os.remove(temp_zip_path)
        raise HTTPException(status_code=400, detail=error_msg)

    # Create audit record in database
    try:
        db.create_audit(audit_id)
    except Exception as e:
        os.remove(temp_zip_path)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Start background processing
    background_tasks.add_task(process_documents_task, audit_id, temp_zip_path)

    return {"audit_id": audit_id, "message": "Processing started"}


@app.get("/status/{audit_id}")
async def get_status(audit_id: str):
    """
    Get the status and results of an audit.

    Args:
        audit_id: UUID of the audit

    Returns:
        JSON with status, progress, and results (if complete)
    """
    try:
        audit = db.get_audit(audit_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    response = {
        "status": audit['status'],
        "progress": audit.get('progress', ''),
        "results": None,
        "error": None
    }

    if audit['status'] == 'complete':
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
async def get_equity_events(audit_id: str):
    """
    Fetch all equity events for an audit (for time-travel cap table).
    Called once when the audit view loads.

    Args:
        audit_id: UUID of the audit

    Returns:
        List of equity events ordered by date
    """
    try:
        # Check if audit exists
        audit = db.get_audit(audit_id)
        if not audit:
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
        raise HTTPException(status_code=500, detail=f"Failed to fetch events: {str(e)}")


@app.get("/api/audits/{audit_id}/captable", response_model=CapTableState)
async def get_cap_table_at_time(
    audit_id: str,
    as_of_date: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD), defaults to today")
):
    """
    Calculate cap table at a specific point in time (time-travel feature).
    Called repeatedly as user moves the time slider.

    Args:
        audit_id: UUID of the audit
        as_of_date: Optional ISO date string (YYYY-MM-DD). If None, uses today's date.

    Returns:
        Cap table state with shareholders and ownership percentages
    """
    try:
        # Check if audit exists
        audit = db.get_audit(audit_id)
        if not audit:
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
        events = _get_cached_equity_events(audit_id)

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
        raise HTTPException(status_code=500, detail=f"Failed to calculate cap table: {str(e)}")


@lru_cache(maxsize=128)
def _get_cached_equity_events(audit_id: str) -> List[Dict[str, Any]]:
    """
    Cache equity events in memory to avoid repeated DB queries.
    LRU cache automatically evicts old entries when full.

    Args:
        audit_id: UUID of the audit

    Returns:
        List of equity events
    """
    return db.get_equity_events_by_audit(audit_id)


@app.get("/api/audits/{audit_id}/documents/{doc_id}")
async def get_document(audit_id: str, doc_id: str):
    """
    Fetch a single document by ID (for document viewer modal).

    Args:
        audit_id: UUID of the audit (for validation)
        doc_id: UUID of the document

    Returns:
        Document data including full text and extracted data
    """
    try:
        # Fetch document
        document = db.get_document_by_id(doc_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Verify document belongs to this audit
        if str(document['audit_id']) != audit_id:
            raise HTTPException(status_code=403, detail="Document does not belong to this audit")

        # Convert UUID to string for JSON serialization
        document['id'] = str(document['id'])
        document['audit_id'] = str(document['audit_id'])

        return document

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch document: {str(e)}")


# ============================================================================
# BACKGROUND TASK
# ============================================================================

def process_documents_task(audit_id: str, zip_path: str):
    """
    Background task to process uploaded documents.
    Changed to sync to avoid blocking FastAPI event loop with sync DB/file operations.

    Args:
        audit_id: UUID of the audit
        zip_path: Path to the uploaded zip file
    """
    import asyncio
    extract_dir = None
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Starting processing for audit {audit_id}")

        # Update progress
        try:
            db.update_progress(audit_id, "Extracting files from archive...")
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
            print(f"ERROR: Failed to update progress for {audit_id}: {e}")

        # Unzip files
        file_paths = utils.unzip_file(zip_path)
        extract_dir = os.path.dirname(file_paths[0]) if file_paths else None

        if not file_paths:
            raise ValueError("No files found in the archive")

        logger.info(f"Extracted {len(file_paths)} files for audit {audit_id}")

        try:
            db.update_progress(audit_id, f"Found {len(file_paths)} files. Parsing documents...")
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
            print(f"ERROR: Failed to update progress: {e}")

        # Parse each document
        documents = []
        for i, file_path in enumerate(file_paths, start=1):
            filename = os.path.basename(file_path)

            # Update progress every 5 docs, on first, and on last for better UX
            if i % 5 == 1 or i == 1 or i == len(file_paths):
                try:
                    # Truncate filename to 40 chars for clean display
                    display_name = filename[:40] + "..." if len(filename) > 40 else filename
                    db.update_progress(audit_id, f"Parsing document {i}/{len(file_paths)}: {display_name}")
                except Exception as e:
                    logger.error(f"Failed to update progress: {e}")

            # Parse with timeout to prevent hanging
            logger.info(f"Parsing document {i}/{len(file_paths)}: {filename}")

            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(utils.parse_document, file_path)
            try:
                doc = future.result(timeout=20)  # 20 second timeout per document
                logger.info(f"Successfully parsed: {filename}")
            except TimeoutError:
                logger.error(f"Timeout parsing {filename} after 20 seconds")

                # Try fallback extraction for PDFs
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext == '.pdf':
                    logger.info(f"Attempting fallback extraction for {filename}")
                    try:
                        text = utils.extract_from_pdf_fallback(file_path)
                        doc = {
                            'filename': filename,
                            'type': 'pdf',
                            'text': text,
                            'summary': 'Parsed with fast fallback method (markdown structure not preserved)'
                        }
                        logger.info(f"Fallback extraction succeeded for {filename}")
                    except Exception as fallback_error:
                        logger.error(f"Fallback extraction also failed for {filename}: {fallback_error}")
                        doc = {
                            'filename': filename,
                            'type': 'pdf',
                            'text': '',
                            'error': f'Timeout after 20s, fallback also failed: {str(fallback_error)}'
                        }
                else:
                    doc = {
                        'filename': filename,
                        'type': file_ext.lstrip('.'),
                        'text': '',
                        'error': 'Document parsing timed out after 20 seconds'
                    }
            except Exception as e:
                logger.error(f"Error parsing {filename}: {e}")
                doc = {
                    'filename': filename,
                    'type': os.path.splitext(filename)[1].lstrip('.'),
                    'text': '',
                    'error': f'Parsing failed: {str(e)}'
                }
            finally:
                # Force garbage collection to clean up PyMuPDF references
                import gc
                gc.collect()
                # Don't wait for stuck threads to finish
                executor.shutdown(wait=False, cancel_futures=True)

            documents.append(doc)

        if not documents:
            raise ValueError("No parseable documents found")

        logger.info(f"Parsed {len(documents)} documents for audit {audit_id}")

        # Run AI processing pipeline (async function called from sync context)
        asyncio.run(processing.process_audit(audit_id, documents))

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

    print("🚀 Corporate Governance Audit Platform API started")
    print(f"📊 Database: {os.getenv('DATABASE_URL', 'Not configured')[:50]}...")
    print(f"🤖 Claude API: {'Configured' if os.getenv('ANTHROPIC_API_KEY') else 'NOT CONFIGURED'}")
