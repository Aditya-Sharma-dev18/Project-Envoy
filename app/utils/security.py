import re
from fastapi import HTTPException

# Common keywords used in prompt injection attacks
INJECTION_PATTERNS = [
    r"ignore previous",
    r"disregard instructions",
    r"system prompt",
    r"output the following",
    r"bypass",
    r"drop table"
]

def scan_inbound_text(text: str) -> bool:
    """
    Scans the inbound message for basic prompt injection attempts.
    Raises an HTTP exception if malicious intent is detected.
    """
    normalized_text = text.lower()
    
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, normalized_text):
            # We silently drop the request by raising a 400 error
            # In production, you might want to log this to an admin Slack channel
            raise HTTPException(
                status_code=400, 
                detail="Message flagged by security policies."
            )
            
    return True