"""
Emergency pre-filter.

This runs BEFORE the agent, BEFORE intent routing, BEFORE any LLM call.
It is intentionally dumb (keyword matching) rather than model-based:
a life-safety check should not depend on a probabilistic model call
that could fail, time out, or reason its way past the check.

The LLM system prompt also carries an instruction to escalate on
emergency-sounding input as a backstop for phrasing this filter misses —
this is the fast, deterministic first line of defense.
"""

import re

# Keep this list reviewed with clinical staff, not just engineers.
# Deliberately broad — false positives (escalating a non-emergency)
# are cheap; false negatives are not.
EMERGENCY_PATTERNS = [
    r"\bchest pain\b",
    r"\bcan'?t breathe\b",
    r"\bdifficulty breathing\b",
    r"\bunconscious\b",
    r"\bnot breathing\b",
    r"\bsevere bleeding\b",
    r"\bbleeding heavily\b",
    r"\bheart attack\b",
    r"\bstroke\b",
    r"\bseizure\b",
    r"\bsuicid\w*\b",
    r"\bkill myself\b",
    r"\boverdose\b",
    r"\banaphyla\w*\b",
    r"\ballergic reaction\b",
    r"\bemergency\b",
    r"\burgent\b.*\bhelp\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in EMERGENCY_PATTERNS]


def is_emergency(message_text: str) -> bool:
    """Returns True if the inbound message matches an emergency pattern.
    Callers MUST check this before invoking the agent/intent router."""
    return any(pattern.search(message_text) for pattern in _COMPILED)


def emergency_response_text(clinic_emergency_contact: str) -> str:
    return (
        "This sounds like it could be urgent. Please call "
        f"{clinic_emergency_contact} right away or go to the nearest "
        "emergency room. I'm alerting our staff now so someone can "
        "follow up with you immediately."
    )
