import re
from loguru import logger


class PromptInjectionError(Exception):
    """Raised when inbound text is flagged as a potential prompt injection."""
    pass


# Patterns commonly used in prompt injection attacks
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous",
    r"disregard\s+(all\s+)?(your\s+)?instructions",
    r"(?:reveal|show|output|print)\s+(?:the\s+)?system\s*prompt",
    r"you\s+are\s+now\s+(?:a|an)\s+",
    r"act\s+as\s+(?:a|an)\s+(?:different|new)",
    r"(?:new|override|replace)\s+(?:your\s+)?instructions",
    r"<\s*(?:script|img|iframe)",
    r";\s*(?:DROP|DELETE|UPDATE|INSERT|ALTER)\s",
]

_compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def scan_inbound_text(text: str) -> bool:
    """
    Scans inbound text for prompt injection attempts.
    Raises PromptInjectionError if malicious intent is detected.
    Returns True if the text passes all checks.
    """
    for pattern in _compiled_patterns:
        if pattern.search(text):
            logger.warning(
                f"Prompt injection blocked | pattern='{pattern.pattern}' | "
                f"text_preview='{text[:100]}...'"
            )
            raise PromptInjectionError(
                f"Inbound text flagged by security scan (pattern: {pattern.pattern})"
            )

    return True
