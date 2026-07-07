"""BUILD-001 — Human State ingestion feature flag (default OFF)."""
import os

_TRUE = ("1", "true", "on", "yes")


def ingest_enabled() -> bool:
    """HSE_INGEST — when OFF (default), /chat is byte-identical and nothing is written."""
    return os.getenv("HSE_INGEST", "").strip().lower() in _TRUE


def audit_enabled() -> bool:
    """HSE_AUDIT — BUILD-002 Observatory capture (extract + ingest + record the full
    transition for review). Default OFF. Implies ingestion when on."""
    return os.getenv("HSE_AUDIT", "").strip().lower() in _TRUE


def trajectory_enabled() -> bool:
    """HSE_TRAJECTORY — BUILD-004 trend analysis over Human State history. Default OFF.
    Reads the existing human_state_events history; computes nothing new when off."""
    return os.getenv("HSE_TRAJECTORY", "").strip().lower() in _TRUE
