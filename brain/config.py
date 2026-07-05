"""
APEX Brain — configuration flags (M0).

Two flags, both default OFF, so M0 is invisible in production until a flag is
deliberately flipped. `BRAIN_SHADOW` = compute + log (no user-facing change);
`BRAIN_ENFORCE` = act on the decision (staged in later milestones).
"""
import os

_TRUE = ("1", "true", "on", "yes")


def flag(name: str) -> bool:
    """A single, consistent env-flag convention for the whole Brain."""
    return os.getenv(name, "").strip().lower() in _TRUE


def brain_shadow() -> bool:
    return flag("BRAIN_SHADOW")


def brain_enforce() -> bool:
    return flag("BRAIN_ENFORCE")
