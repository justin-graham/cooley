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
from fastapi import FastAPI, UploadFile, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app import db, utils, processing


# Load environment variables
load_dotenv()

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
# BACKGROUND TASK
# ============================================================================

async def process_documents_task(audit_id: str, zip_path: str):
    """
    Background task to process uploaded documents.

    Args:
        audit_id: UUID of the audit
        zip_path: Path to the uploaded zip file
    """
    extract_dir = None

    try:
        # Update progress
        db.update_progress(audit_id, "Extracting files from archive...")

        # Unzip files
        file_paths = utils.unzip_file(zip_path)
        extract_dir = os.path.dirname(file_paths[0]) if file_paths else None

        if not file_paths:
            raise ValueError("No files found in the archive")

        db.update_progress(audit_id, f"Found {len(file_paths)} files. Parsing documents...")

        # Parse each document
        documents = []
        for i, file_path in enumerate(file_paths, start=1):
            db.update_progress(audit_id, f"Parsing document {i}/{len(file_paths)}...")
            doc = utils.parse_document(file_path)
            documents.append(doc)

        if not documents:
            raise ValueError("No parseable documents found")

        # Run AI processing pipeline
        await processing.process_audit(audit_id, documents)

    except Exception as e:
        # Mark audit as failed
        db.mark_error(audit_id, str(e))

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
    print("🚀 Corporate Governance Audit Platform API started")
    print(f"📊 Database: {os.getenv('DATABASE_URL', 'Not configured')[:50]}...")
    print(f"🤖 Claude API: {'Configured' if os.getenv('ANTHROPIC_API_KEY') else 'NOT CONFIGURED'}")
