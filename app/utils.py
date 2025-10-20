"""
Document parsing utilities for PDF, DOCX, XLSX, and PPTX files.
Gracefully handles errors - returns error message instead of crashing.
"""

import os
import zipfile
import tempfile
from typing import List, Dict, Any
import pymupdf4llm
from docx import Document
import pandas as pd
from pptx import Presentation


def unzip_file(zip_path: str) -> List[str]:
    """
    Extract a zip file to a temporary directory.

    Args:
        zip_path: Path to the .zip file

    Returns:
        List of extracted file paths
    """
    extract_dir = tempfile.mkdtemp()

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    # Recursively find all files (not directories)
    file_paths = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            # Skip hidden files and system files
            if not file.startswith('.') and not file.startswith('__MACOSX'):
                file_paths.append(os.path.join(root, file))

    return file_paths


def extract_from_pdf(file_path: str) -> str:
    """
    Extract text from PDF using pymupdf4llm (outputs Markdown for structure).

    Args:
        file_path: Path to PDF file

    Returns:
        Extracted text as Markdown string

    Raises:
        Exception if extraction fails
    """
    # pymupdf4llm returns markdown-formatted text, preserving tables and structure
    markdown_text = pymupdf4llm.to_markdown(file_path)
    return markdown_text


def extract_from_docx(file_path: str) -> str:
    """
    Extract text from DOCX file.

    Args:
        file_path: Path to DOCX file

    Returns:
        Extracted text string

    Raises:
        Exception if extraction fails
    """
    doc = Document(file_path)

    # Extract all paragraphs
    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]

    # Also extract text from tables
    tables_text = []
    for table in doc.tables:
        for row in table.rows:
            row_text = [cell.text.strip() for cell in row.cells]
            tables_text.append(' | '.join(row_text))

    # Combine paragraphs and tables
    full_text = '\n'.join(paragraphs)
    if tables_text:
        full_text += '\n\n--- Tables ---\n' + '\n'.join(tables_text)

    return full_text


def extract_from_xlsx(file_path: str) -> str:
    """
    Extract text and data from Excel file.

    Args:
        file_path: Path to XLSX file

    Returns:
        Extracted text (sheet names + cell values as string)

    Raises:
        Exception if extraction fails
    """
    # Read all sheets
    excel_file = pd.ExcelFile(file_path)

    all_text = []
    for sheet_name in excel_file.sheet_names:
        df = pd.read_excel(excel_file, sheet_name=sheet_name)

        # Convert dataframe to text representation
        sheet_text = f"Sheet: {sheet_name}\n"
        sheet_text += df.to_string(index=False)
        all_text.append(sheet_text)

    return '\n\n'.join(all_text)


def extract_from_pptx(file_path: str) -> str:
    """
    Extract text from PowerPoint file.

    Args:
        file_path: Path to PPTX file

    Returns:
        Extracted text from all slides

    Raises:
        Exception if extraction fails
    """
    prs = Presentation(file_path)

    all_text = []
    for i, slide in enumerate(prs.slides, start=1):
        slide_text = [f"--- Slide {i} ---"]

        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                slide_text.append(shape.text)

        all_text.append('\n'.join(slide_text))

    return '\n\n'.join(all_text)


def parse_document(file_path: str) -> Dict[str, Any]:
    """
    Parse a document file and extract text content.
    Gracefully handles errors - returns error dict instead of raising.

    Args:
        file_path: Path to document file

    Returns:
        Dictionary with keys:
        - filename: str
        - type: str (pdf, docx, xlsx, pptx, or unknown)
        - text: str (extracted text, or empty if error)
        - error: str (error message if parsing failed, otherwise absent)
    """
    filename = os.path.basename(file_path)
    file_ext = os.path.splitext(filename)[1].lower()

    result = {
        'filename': filename,
        'type': file_ext.lstrip('.'),
        'text': ''
    }

    try:
        # Route to appropriate parser based on extension
        if file_ext == '.pdf':
            result['text'] = extract_from_pdf(file_path)
        elif file_ext == '.docx':
            result['text'] = extract_from_docx(file_path)
        elif file_ext == '.xlsx':
            result['text'] = extract_from_xlsx(file_path)
        elif file_ext == '.pptx':
            result['text'] = extract_from_pptx(file_path)
        else:
            # Unsupported file type
            result['error'] = f"Unsupported file type: {file_ext}"
            return result

        # Check if extraction yielded any content
        if not result['text'] or len(result['text'].strip()) < 10:
            result['error'] = "Document appears to be empty or unreadable"

    except Exception as e:
        result['error'] = f"Failed to parse: {str(e)}"

    return result


def validate_zip_file(file_path: str, max_size_mb: int = 50) -> tuple[bool, str]:
    """
    Validate that a file is a valid zip and within size limits.

    Args:
        file_path: Path to the file
        max_size_mb: Maximum allowed size in megabytes

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check if file exists
    if not os.path.exists(file_path):
        return False, "File does not exist"

    # Check file size
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > max_size_mb:
        return False, f"File too large ({file_size_mb:.1f}MB). Maximum is {max_size_mb}MB"

    # Check if it's a valid zip
    if not zipfile.is_zipfile(file_path):
        return False, "File is not a valid ZIP archive"

    return True, ""
