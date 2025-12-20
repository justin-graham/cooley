"""
Document parsing utilities for PDF, DOCX, XLSX, and PPTX files.
Gracefully handles errors - returns error message instead of crashing.
"""

import os
import logging
import zipfile
import tempfile
from typing import List, Dict, Any
import pymupdf4llm
import pymupdf as fitz
from docx import Document
import pandas as pd
from pptx import Presentation

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


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
    # Remove NULL bytes and control characters that break PostgreSQL
    markdown_text = markdown_text.replace('\x00', '').replace('\r', '\n')
    return markdown_text


def extract_from_pdf_fallback(file_path: str) -> str:
    """
    Fast fallback PDF text extraction using basic PyMuPDF.
    Used when pymupdf4llm times out on complex documents.

    Args:
        file_path: Path to PDF file

    Returns:
        Extracted plain text string

    Raises:
        Exception if extraction fails
    """
    doc = fitz.open(file_path)
    text_parts = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        # Remove NULL bytes and control characters that break PostgreSQL
        text = text.replace('\x00', '').replace('\r', '\n')
        if text.strip():
            text_parts.append(f"--- Page {page_num + 1} ---\n{text}")

    doc.close()
    return '\n\n'.join(text_parts)


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


def extract_from_image(file_path: str) -> str:
    """
    Extract basic information from image files (PNG, JPG, etc.).

    Args:
        file_path: Path to image file

    Returns:
        Basic image metadata as text

    Raises:
        Exception if extraction fails
    """
    if not PIL_AVAILABLE:
        return "Image file (PIL not available for text extraction)"

    img = Image.open(file_path)
    metadata = f"Image: {img.format} format, {img.size[0]}x{img.size[1]} pixels"

    # Try to extract any embedded text from metadata
    if hasattr(img, 'info') and img.info:
        for key, value in img.info.items():
            if isinstance(value, str) and len(value) < 200:
                metadata += f"\n{key}: {value}"

    return metadata


def parse_pdf_with_bboxes(filepath: str) -> Dict[str, Any]:
    """
    Extract text + bounding boxes for each text span from PDF.
    Used for generating document preview screenshots with highlights.

    Args:
        filepath: Path to PDF file

    Returns:
        Dictionary with keys:
        - full_text: str (complete document text for AI extraction)
        - text_spans: List[Dict] (each span has: text, page, bbox, char_offset_start, char_offset_end, font_size)

    Example text_span:
        {
            'text': '1,000,000',
            'page': 1,
            'bbox': [x0, y0, x1, y1],  # PDF coordinates
            'char_offset_start': 245,
            'char_offset_end': 254,
            'font_size': 12.0
        }
    """
    doc = fitz.open(filepath)
    text_spans = []
    full_text = ""
    char_offset = 0

    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        span_text = span['text']
                        text_spans.append({
                            'text': span_text,
                            'page': page_num,
                            'bbox': span['bbox'],  # [x0, y0, x1, y1]
                            'char_offset_start': char_offset,
                            'char_offset_end': char_offset + len(span_text),
                            'font_size': span.get('size', 12.0)
                        })
                        full_text += span_text
                        char_offset += len(span_text)

    doc.close()

    return {
        'full_text': full_text,
        'text_spans': text_spans
    }


def convert_to_pdf(filepath: str, output_dir: str) -> str:
    """
    Convert DOCX/XLSX/PPTX to PDF using LibreOffice headless.
    Required for generating document previews from non-PDF files.

    Args:
        filepath: Path to DOCX/XLSX/PPTX file
        output_dir: Directory for output PDF

    Returns:
        Path to generated PDF file

    Raises:
        RuntimeError: If LibreOffice is not installed
        subprocess.CalledProcessError: If conversion fails
    """
    import subprocess

    # Check if libreoffice is available
    try:
        subprocess.run(
            ['libreoffice', '--version'],
            capture_output=True,
            check=True,
            timeout=5
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError(
            "LibreOffice not installed. Required for DOCX/XLSX/PPTX preview generation. "
            "Install with: brew install libreoffice (macOS) or apt-get install libreoffice (Linux)"
        )

    # Convert to PDF
    logger.info(f"Converting {os.path.basename(filepath)} to PDF for preview generation")
    subprocess.run([
        'libreoffice', '--headless', '--convert-to', 'pdf',
        '--outdir', output_dir,
        filepath
    ], check=True, timeout=30)

    # Return path to generated PDF
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    output_pdf = os.path.join(output_dir, f"{base_name}.pdf")

    if not os.path.exists(output_pdf):
        raise RuntimeError(f"PDF conversion failed - output file not created: {output_pdf}")

    return output_pdf


def parse_document_with_paragraphs(file_path: str) -> Dict[str, Any]:
    """
    Parse a document file and extract text with paragraph numbering.
    Each substantive paragraph gets a sequential number for citation purposes.

    Args:
        file_path: Path to document file

    Returns:
        Dictionary with keys:
        - filename: str
        - type: str (pdf, docx, xlsx, pptx, or unknown)
        - full_text: str (complete extracted text)
        - paragraphs: List[Dict] with {number: int, text: str}
        - error: str (error message if parsing failed, otherwise absent)
    """
    # First get the basic parsed result
    basic_result = parse_document(file_path)

    result = {
        'filename': basic_result['filename'],
        'type': basic_result['type'],
        'full_text': basic_result.get('text', ''),
        'paragraphs': []
    }

    # If there was an error in basic parsing, return it
    if 'error' in basic_result:
        result['error'] = basic_result['error']
        return result

    # Split text into paragraphs and number them
    full_text = basic_result.get('text', '')
    if not full_text:
        return result

    # Split on double newlines (paragraph breaks) or single newlines for tighter docs
    raw_paragraphs = full_text.split('\n')

    paragraph_number = 1
    current_paragraph = []

    for line in raw_paragraphs:
        stripped_line = line.strip()

        # Skip truly empty lines
        if not stripped_line:
            # If we have accumulated text, save it as a paragraph
            if current_paragraph:
                para_text = ' '.join(current_paragraph)
                if len(para_text) > 20:  # Minimum 20 chars to be substantive
                    result['paragraphs'].append({
                        'number': paragraph_number,
                        'text': para_text
                    })
                    paragraph_number += 1
                current_paragraph = []
            continue

        # Accumulate non-empty lines
        current_paragraph.append(stripped_line)

    # Don't forget the last paragraph
    if current_paragraph:
        para_text = ' '.join(current_paragraph)
        if len(para_text) > 20:
            result['paragraphs'].append({
                'number': paragraph_number,
                'text': para_text
            })

    return result


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
            try:
                result['text'] = extract_from_pdf(file_path)
            except NameError as e:
                # Library bug in pymupdf4llm - use fallback extraction
                logger.warning(f"pymupdf4llm bug for {filename}, using fallback: {e}")
                result['text'] = extract_from_pdf_fallback(file_path)
        elif file_ext == '.docx':
            result['text'] = extract_from_docx(file_path)
        elif file_ext == '.xlsx':
            result['text'] = extract_from_xlsx(file_path)
        elif file_ext == '.pptx':
            result['text'] = extract_from_pptx(file_path)
        elif file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
            result['text'] = extract_from_image(file_path)
        elif not file_ext or file_ext == '.':
            # Files without extension - try to read as text
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    result['text'] = f.read(1000)  # First 1000 chars
            except:
                result['error'] = f"Unsupported file type: no extension"
                return result
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
