"""
Security and Prompt Injection Defense Layer.
Ensures untrusted text within ERP exports and manual journals is treated
strictly as inert passive data, neutralizing adversarial instructions.
"""

import re
from typing import Optional, Tuple

INJECTION_PATTERNS = [
    re.compile(r"note for automated reviewers", re.IGNORECASE),
    re.compile(r"skip the (debit/credit|balance) check", re.IGNORECASE),
    re.compile(r"do not list .* in .* issues report", re.IGNORECASE),
    re.compile(r"ignore previous instructions", re.IGNORECASE),
    re.compile(r"pre-approved by the (cfo|ceo|auditor)", re.IGNORECASE),
]


def inspect_text_for_injection(text: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Scans a text field (memo, description, comment) for prompt injection patterns.
    Returns (is_suspicious, matched_pattern).
    """
    if not text:
        return False, None

    for pattern in INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, match.group(0)

    return False, None
