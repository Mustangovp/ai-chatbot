"""BUILD-003 — Adaptive Coach feature flag (default OFF)."""
import os

_TRUE = ("1", "true", "on", "yes")


def consumer_enabled() -> bool:
    """HSE_CONSUMER — when OFF (default), the coach does not read Human State and the
    response is exactly the enforcement output (byte-identical)."""
    return os.getenv("HSE_CONSUMER", "").strip().lower() in _TRUE
