"""Detached, aggregate-only runtime validation for HSE presentation V1.

This module never returns a projection to delivery code.  It is intentionally
limited to process-local counters so shadow evaluation cannot retain identity,
state, or user content.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

from coaching.presentation import build_presentation_projection


FLAG = "HSE_PRESENTATION_SHADOW"
_COUNTERS = (
    "eligible", "none", "failed", "tone_supportive", "tone_reassuring",
    "ack_brief", "encouragement_gentle", "encouragement_mastery", "latency_max_ms",
)
_lock = threading.Lock()
_telemetry = {counter: 0 for counter in _COUNTERS}
_logger = logging.getLogger("apex.hse_presentation_shadow")


def shadow_enabled(getenv: Callable[[str, str], str] = os.getenv) -> bool:
    """Fail closed: shadow evaluation requires the exact opt-in value ``true``."""
    return str(getenv(FLAG, "false")).strip().lower() == "true"


def _record(**changes: int) -> None:
    with _lock:
        for key, value in changes.items():
            if key == "latency_max_ms":
                _telemetry[key] = max(_telemetry[key], max(0, int(value)))
            elif key in _telemetry:
                _telemetry[key] += int(value)


def observe(subject: str) -> None:
    """Evaluate only the safe projection and discard it before delivery.

    ``subject`` is used solely for the in-memory HSE read and is never retained,
    logged, or included in telemetry.
    """
    if not shadow_enabled():
        return
    started = time.perf_counter()
    try:
        projection = build_presentation_projection(subject)
        if projection is None:
            _record(none=1)
            return
        changes = {"eligible": 1}
        if projection.tone == "supportive":
            changes["tone_supportive"] = 1
        elif projection.tone == "reassuring":
            changes["tone_reassuring"] = 1
        if projection.acknowledgement == "brief":
            changes["ack_brief"] = 1
        if projection.encouragement == "gentle":
            changes["encouragement_gentle"] = 1
        elif projection.encouragement == "mastery":
            changes["encouragement_mastery"] = 1
        _record(**changes)
    except Exception as error:
        _record(failed=1)
        _logger.warning("[hse-presentation-shadow] failed: %s", type(error).__name__)
    finally:
        _record(latency_max_ms=(time.perf_counter() - started) * 1000)


def snapshot_telemetry() -> dict[str, int]:
    """Return only the approved aggregate counters."""
    with _lock:
        return dict(_telemetry)


def reset_for_testing() -> None:
    """Test seam; production telemetry is intentionally process-local only."""
    with _lock:
        _telemetry.clear()
        _telemetry.update({counter: 0 for counter in _COUNTERS})
