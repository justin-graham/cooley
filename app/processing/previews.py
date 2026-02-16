"""PDF preview screenshot generation with highlighted extraction locations."""

import base64
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Shareholder color palette — synced with frontend cap table colors
SHAREHOLDER_COLORS = [
    '#3B82F6', '#8B5CF6', '#EC4899', '#10B981',
    '#F59E0B', '#EF4444', '#06B6D4', '#6366F1',
]


def get_shareholder_color(shareholder: str) -> str:
    hash_value = sum(ord(c) for c in shareholder)
    return SHAREHOLDER_COLORS[hash_value % len(SHAREHOLDER_COLORS)]


def find_number_locations(extracted_data: Dict[str, Any], text_spans: List[Dict], doc_id: str) -> List[Dict]:
    """Match extracted share counts and prices to their bounding boxes."""
    locations = []
    shares = extracted_data.get('shares') or extracted_data.get('shares_issued')
    price = extracted_data.get('price_per_share')
    shareholder = extracted_data.get('shareholder') or extracted_data.get('recipient') or extracted_data.get('investor')

    if not shareholder:
        return locations

    color = get_shareholder_color(shareholder)

    # Search for shares value
    if isinstance(shares, (int, float)):
        shares = abs(shares)
    if shares:
        _find_value_in_spans(shares, text_spans, doc_id, 'shares', shareholder, color, locations)

    # Search for price value
    if price:
        patterns = [f"{price:.4f}", f"{price:.2f}", f"${price:.4f}", f"${price:.2f}"]
        for pattern in patterns:
            for span in text_spans:
                if pattern in span['text']:
                    locations.append({
                        'doc_id': doc_id, 'page': span['page'], 'bbox': span['bbox'],
                        'text_value': span['text'], 'data_type': 'price',
                        'shareholder': shareholder, 'color': color,
                    })
                    break
            if any(loc['data_type'] == 'price' for loc in locations):
                break

    return locations


def _find_value_in_spans(shares, text_spans, doc_id, data_type, shareholder, color, locations):
    patterns = [str(int(shares)), f"{int(shares):,}", f"{shares:.0f}"]
    for pattern in patterns:
        for span in text_spans:
            if pattern in span['text'].replace(' ', ''):
                locations.append({
                    'doc_id': doc_id, 'page': span['page'], 'bbox': span['bbox'],
                    'text_value': span['text'], 'data_type': data_type,
                    'shareholder': shareholder, 'color': color,
                })
                break
        if any(loc['data_type'] == data_type for loc in locations):
            break


def generate_preview_screenshot(pdf_path: str, locations: List[Dict], output_path: str, scale: float = 2.0) -> Tuple[Optional[str], Optional[float]]:
    """Generate PNG screenshot of PDF page with highlighted numbers."""
    import fitz
    from PIL import Image, ImageDraw

    if not locations:
        return None, None

    doc = fitz.open(pdf_path)
    target_page = locations[0]['page']
    page = doc.load_page(target_page - 1)
    page_height = page.rect.height

    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    draw = ImageDraw.Draw(img, 'RGBA')

    for loc in locations:
        if loc['page'] == target_page:
            bbox = loc['bbox']
            x0, y0, x1, y1 = [coord * scale for coord in bbox]
            fill_rgb = tuple(int(loc['color'].lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
            draw.rectangle([x0, y0, x1, y1], fill=fill_rgb + (50,))
            draw.rectangle([x0, y0, x1, y1], outline=fill_rgb + (180,), width=2)

    img.save(output_path, 'PNG')
    doc.close()

    # Compute focus_y
    page_locs = [loc for loc in locations if loc['page'] == target_page]
    focus_y = None
    if page_locs:
        y0s = [loc['bbox'][1] for loc in page_locs]
        y1s = [loc['bbox'][3] for loc in page_locs]
        union_center = (min(y0s) + max(y1s)) / 2.0
        focus_y = union_center / page_height if page_height else None

    return output_path, focus_y


def generate_and_store_preview(doc_id: str, pdf_path: str, extracted_data: Dict, text_spans: List[Dict]) -> Tuple[Optional[str], Optional[float]]:
    """Generate preview screenshot and return base64 string."""
    locations = find_number_locations(extracted_data, text_spans, doc_id)
    if not locations:
        return None, None

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        screenshot_path = tmp.name

    try:
        result_path, focus_y = generate_preview_screenshot(pdf_path, locations, screenshot_path)
        if not result_path:
            return None, None

        with open(result_path, 'rb') as img_file:
            base64_data = base64.b64encode(img_file.read()).decode('utf-8')

        logger.info(f"Preview for doc {doc_id}: {len(locations)} highlights, {len(base64_data)} bytes")
        return f"data:image/png;base64,{base64_data}", focus_y

    except Exception as e:
        logger.error(f"Preview generation failed for doc {doc_id}: {e}")
        return None, None
    finally:
        if os.path.exists(screenshot_path):
            os.unlink(screenshot_path)
