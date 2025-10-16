import re
INJECTION_PATTERNS = [
    r"(?i)ignore\s+previous\s+instructions",
    r"(?i)disregard\s+all\s+prior",
    r"(?i)you\s+are\s+now\s+.*system",
    r"(?i)pretend\s+to\s+be",
    r"(?i)execute\s+shell\s+command",
    r"(?i)call\s+tool",
]
def sanitize_user_text(text: str) -> str:
    sanitized = text
    for pat in INJECTION_PATTERNS:
        sanitized = re.sub(pat, "[filtered]", sanitized)
    sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", sanitized)
    return sanitized.strip()
