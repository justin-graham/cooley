"""Pass 1: Document classification using keyword patterns + Claude fallback."""

import logging
import re
from typing import Any, Dict

from app import prompts
from app.processing.claude_client import call_claude, parse_json_response

logger = logging.getLogger(__name__)

# High-confidence keyword patterns: (regex, category, summary_template)
# Order matters — most specific patterns first.
KEYWORD_PATTERNS = [
    (r'83\s*\(\s*b\s*\)', '83(b) Election', '83(b) election form'),
    (r'simple\s+agreement\s+for\s+future\s+equity|(?:^|\s)SAFE(?:\s|$)', 'SAFE', 'SAFE investment agreement'),
    (r'stock\s+certificate|certificate\s+(no\.?|number)\s*\d+', 'Stock Certificate', 'Stock certificate'),
    (r'amended\s+and\s+restated\s+certificate\s+of\s+incorporation', 'Charter Document', 'Amended and Restated Certificate of Incorporation'),
    (r'certificate\s+of\s+(incorporation|formation)', 'Charter Document', 'Certificate of Incorporation'),
    (r'articles\s+of\s+incorporation', 'Charter Document', 'Articles of Incorporation'),
    (r'articles\s+of\s+organization', 'Charter Document', 'Articles of Organization (LLC)'),
    (r'articles\s+of\s+association', 'Charter Document', 'Articles of Association'),
    (r'amended\s+and\s+restated\s+bylaws', 'Charter Document', 'Amended and Restated Bylaws'),
    (r'bylaws', 'Charter Document', 'Corporate bylaws'),
    (r'operating\s+agreement', 'Charter Document', 'LLC Operating Agreement'),
    (r'stock\s+purchase\s+agreement|restricted\s+stock\s+purchase', 'Stock Purchase Agreement', 'Stock purchase agreement'),
    (r'subscription\s+agreement', 'Stock Purchase Agreement', 'Subscription agreement'),
    (r'(share|stock)\s+repurchase\s+agreement', 'Share Repurchase Agreement', 'Share repurchase agreement'),
    (r'consent\s+of\s+(board|directors|stockholders)|written\s+consent', 'Board/Shareholder Minutes', 'Written consent document'),
    (r'minutes\s+of.*meeting|meeting\s+of\s+the\s+(board|directors)', 'Board/Shareholder Minutes', 'Board/shareholder meeting minutes'),
    (r'investor\s+rights\s+agreement', 'Board/Shareholder Minutes', 'Investor rights agreement'),
    (r'(?:voting|stockholder|shareholder)s?\s+agreement', 'Board/Shareholder Minutes', 'Voting/shareholder agreement'),
    (r'option\s+grant\s+(agreement|notice)|stock\s+option\s+agreement', 'Option Grant Agreement', 'Stock option grant agreement'),
    (r'equity\s+incentive\s+plan|\d+\s+stock\s+plan', 'Equity Incentive Plan', 'Equity incentive plan document'),
    (r'warrant\s+(agreement|certificate)', 'Stock Purchase Agreement', 'Warrant agreement'),
    (r'convertible\s+note|promissory\s+note', 'Convertible Note', 'Convertible promissory note'),
    (r'series\s+seed\s+preferred\s+stock', 'Stock Purchase Agreement', 'Series Seed financing agreement'),
    (r'form\s+d|sec\s+form\s+d|notice\s+of\s+exempt', 'Corporate Records', 'SEC Form D filing'),
    (r'indemnification\s+agreement', 'Indemnification Agreement', 'Director/officer indemnification agreement'),
    (r'proprietary\s+information.*agreement|PIIA', 'IP/Proprietary Info Agreement', 'Proprietary information and inventions agreement'),
    (r'employment\s+agreement|offer\s+letter', 'Employment Agreement', 'Employment agreement'),
    (r'cap(?:italization)?\s+table|cap\s+table\s+summary|ownership\s+summary', 'Financial Statement', 'Capitalization table'),
]


def classify_by_keywords(text: str) -> tuple:
    sample = text[:3000].lower()
    for pattern, category, summary in KEYWORD_PATTERNS:
        if re.search(pattern, sample, re.IGNORECASE):
            logger.info(f"Keyword match: '{pattern}' -> {category}")
            return (category, summary)
    return (None, None)


def classify_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    if doc.get('error'):
        doc['category'] = 'Other'
        doc['summary'] = 'Failed to parse document'
        return doc

    try:
        category, summary = classify_by_keywords(doc['text'])
        if category:
            doc['category'] = category
            doc['summary'] = summary
            logger.info(f"Classified by keywords: {doc.get('filename', 'unknown')} -> {category}")
            return doc

        text_sample = doc['text'][:10000]
        prompt = prompts.CLASSIFICATION_PROMPT.format(text=text_sample)
        response = call_claude(prompt, max_tokens=512)
        result = parse_json_response(response)
        doc['category'] = result.get('doc_type', 'Other')
        doc['summary'] = result.get('summary', 'No summary available')
        logger.info(f"Classified by Claude: {doc.get('filename', 'unknown')} -> {doc['category']}")
    except Exception as e:
        doc['category'] = 'Other'
        doc['summary'] = f'Classification failed: {str(e)}'

    return doc
