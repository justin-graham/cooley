"""Claude API wrapper with retry logic and robust JSON parsing."""

import json
import logging
import os
import re
import time
from typing import Any

from anthropic import Anthropic, APITimeoutError, APIError, RateLimitError

logger = logging.getLogger(__name__)

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=60.0)


def call_claude(prompt: str, max_tokens: int = 2048, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=max_tokens,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except (RateLimitError, APITimeoutError) as e:
            wait_time = 2 ** (attempt + 1)
            if attempt < max_retries - 1:
                logger.warning(f"Claude API {type(e).__name__} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Claude API {type(e).__name__} after {max_retries} attempts: {e}")
                raise
        except APIError as e:
            logger.error(f"Claude API error: {e}")
            raise


def parse_json_response(response_text: str) -> Any:
    text = response_text.strip()

    # Strip markdown code fences
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Attempt 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Find outermost JSON structure via bracket counting
    result = _extract_outermost_json(text)
    if result is not None:
        return result

    # Attempt 3: Regex fallback (greedy, anchored to end)
    json_match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})\s*$', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Attempt 4: Repair trailing commas
    try:
        repaired = re.sub(r',(\s*[\]}])', r'\1', text)
        result = json.loads(repaired)
        logger.info("JSON repaired successfully (removed trailing commas)")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse failed after all attempts: {e}")
        logger.error(f"Problematic section: {text[max(0, e.pos-50):e.pos+50]}")
        raise


def _extract_outermost_json(text: str) -> Any:
    """Find the outermost JSON object or array using bracket counting."""
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == '\\' and in_string:
                escape_next = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == start_char:
                depth += 1
            elif c == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None
