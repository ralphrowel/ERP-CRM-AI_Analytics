"""Prompt-Injection Defense & Security Boundary (Roadmap §V1.7)

Enforces:
1. Delimited encapsulation of untrusted record data (notes, emails, customer comments).
2. Pattern detection for prompt-injection attacks ('ignore previous instructions', 'list all customers', etc.).
3. Strict invariant: Untrusted record content cannot trigger unauthorized tool execution.
"""

import re
from typing import Any

UNTRUSTED_START_TAG = "<<<UNTRUSTED_RECORD_DATA>>>"
UNTRUSTED_END_TAG = "<<</UNTRUSTED_RECORD_DATA>>>"

# Known adversarial prompt injection patterns per Roadmap §V1.7 Exit Criteria
INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
    r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+rules",
    r"system\s+override",
    r"list\s+all\s+(?:customers|users|accounts|leads|tables|records)",
    r"dump\s+(?:all\s+)?(?:database|customers|users|passwords|secrets|tables)",
    r"reveal\s+(?:system\s+)?prompt",
    r"you\s+are\s+now\s+(?:dan|developer\s+mode|unrestricted)",
    r"select\s+\*\s+from",
]

_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def wrap_untrusted_content(text: str | None, field_name: str = "notes") -> str:
    """
    Encapsulates raw record text inside secure boundary delimiters.
    Prevents untrusted user input from being parsed as agent instructions.
    """
    if not text:
        return f"{UNTRUSTED_START_TAG}\n[{field_name}: None]\n{UNTRUSTED_END_TAG}"

    clean = text.strip()
    return f"{UNTRUSTED_START_TAG}\n[{field_name}]:\n{clean}\n{UNTRUSTED_END_TAG}"


def detect_prompt_injection(text: str | None) -> bool:
    """
    Scans a string for prompt injection signatures.
    Returns True if an adversarial command attempt is detected.
    """
    if not text:
        return False
    return bool(_INJECTION_RE.search(text))


def sanitize_record_for_prompt(record_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitizes dictionary representations of CRM/Sales entities by wrapping
    free-text fields (notes, description, subject, body) in untrusted tags.
    """
    sanitized: dict[str, Any] = {}
    free_text_fields = {"notes", "description", "body", "subject", "message", "comments"}

    for key, value in record_dict.items():
        if key in free_text_fields and isinstance(value, str):
            sanitized[key] = wrap_untrusted_content(value, field_name=key)
        else:
            sanitized[key] = value

    return sanitized
