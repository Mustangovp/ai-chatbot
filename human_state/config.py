"""BUILD-001 — Human State ingestion feature flag (default OFF)."""
import os

_TRUE = ("1", "true", "on", "yes")


def ingest_enabled() -> bool:
    """HSE_INGEST — when OFF (default), /chat is byte-identical and nothing is written."""
    return os.getenv("HSE_INGEST", "").strip().lower() in _TRUE
