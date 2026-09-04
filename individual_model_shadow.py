"""Detached, aggregate-only observation for Individual Model V1."""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable

from individual_model_projection import (
    IndividualModelCoachingProjectionV1,
    validate_projection,
)


FLAG = "INDIVIDUAL_MODEL_SHADOW"
MAX_LATENCY_MS = 60_000
COUNTERS = (
    "eligible",
    "none",
    "failed",
    "goal_present",
    "experience_present",
    "equipment_present",
    "constraint_present",
    "recent_completion_present",
    "trajectory_progressing",
    "trajectory_stable",
    "nutrition_targets_present",
    "latency_max_ms",
)
_lock = threading.Lock()
_telemetry = {counter: 0 for counter in COUNTERS}
_logger = logging.getLogger("apex.individual_model_shadow")


def shadow_enabled(getenv: Callable[[str, str], str] = os.getenv) -> bool:
    """Fail closed unless the narrow shadow flag is exactly true."""
    return str(getenv(FLAG, "false")).strip().lower() == "true"


def _bounded_latency(value: int | float) -> int:
    try:
        return min(MAX_LATENCY_MS, max(0, int(value)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _record(*, latency_ms: int | float = 0, **changes: int) -> None:
    with _lock:
        for key, value in changes.items():
            if key in _telemetry and key != "latency_max_ms":
                _telemetry[key] += int(value)
        _telemetry["latency_max_ms"] = max(
            _telemetry["latency_max_ms"], _bounded_latency(latency_ms))


def observe_projection(
        projection: IndividualModelCoachingProjectionV1,
        *,
        latency_ms: int | float,
) -> None:
    """Count only closed-schema presence and immediately discard the projection."""
    if not shadow_enabled():
        return
    try:
        projection = validate_projection(projection)
        changes = {
            "goal_present": int(projection.goal_context is not None),
            "experience_present": int(projection.experience_context is not None),
            "equipment_present": int(projection.equipment_context is not None),
            "constraint_present": int(bool(projection.active_training_constraint_context)),
            "recent_completion_present": int(
                projection.completed_recent_authoritative_session),
            "trajectory_progressing": int(projection.trajectory_context == "progressing"),
            "trajectory_stable": int(projection.trajectory_context == "stable"),
            "nutrition_targets_present": int(bool(projection.nutrition_target_context)),
        }
        if any(changes.values()):
            changes["eligible"] = 1
        else:
            changes["none"] = 1
        _record(latency_ms=latency_ms, **changes)
    except Exception as error:
        _record(failed=1, latency_ms=latency_ms)
        _logger.warning("[individual-model-shadow] failed: %s", type(error).__name__)


def observe_failure(error: Exception, *, latency_ms: int | float) -> None:
    """Record a failed build without retaining its input, message, or identity."""
    if not shadow_enabled():
        return
    _record(failed=1, latency_ms=latency_ms)
    _logger.warning("[individual-model-shadow] failed: %s", type(error).__name__)


def snapshot_telemetry() -> dict[str, int]:
    """Return the exact approved process-local aggregate schema."""
    with _lock:
        return dict(_telemetry)


def reset_for_testing() -> None:
    """Test seam; production telemetry has no reset endpoint."""
    with _lock:
        _telemetry.clear()
        _telemetry.update({counter: 0 for counter in COUNTERS})
