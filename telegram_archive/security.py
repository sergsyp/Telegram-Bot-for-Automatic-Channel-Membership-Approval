"""Stop archival exports containing obvious credentials; do not log matching text."""
import re

_PATTERNS = [
    re.compile(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])\d{8,12}:[A-Za-z0-9_-]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
]


def contains_credential(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PATTERNS)
