"""Detached, aggregate-only observation for Individual Model V1."""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable, TypeVar

from individual_model_projection import (
    IndividualModelCoachingProjectionV1,
    validate_projection,
)


FLAG = "INDIVIDUAL_MODEL_SHADOW"
MAX_LATENCY_MS = 60_000
# Optional context cannot delay the established chat path indefinitely. A timed-out
# worker retains the one-slot gate until it exits, making later requests fail closed.
OPTIONAL_CONTEXT_TIMEOUT_MS = 250
_Result = TypeVar("_Result")


class OptionalContextTimeout(RuntimeError):
    pass


class OptionalContextBusy(RuntimeError):
    pass


COUNTERS = (
    "eligible",
    "none",
    "failed",
    "goal_present",
    "experience_present",
    "equipment_present",
    "constraint_present",
    "completed_session_evidence_present",
    "prescribed_increase_observed",
    "prescribed_maintain_observed",
    "trajectory_insufficient_evidence",
    "nutrition_targets_present",
    "latency_max_ms",
)
_lock = threading.Lock()
_optional_work_gate = threading.BoundedSemaphore(value=1)
_telemetry = {counter: 0 for counter in COUNTERS}
_logger = logging.getLogger("apex.individual_model_shadow")


def shadow_enabled(getenv: Callable[[str, str], str] = os.getenv) -> bool:
    """Fail closed unless the narrow shadow flag is exactly true."""
    return str(getenv(FLAG, "false")).strip().lower() == "true"


def run_optional_context(
        work: Callable[[], _Result],
        *,
        timeout_ms: int | float | None = None,
) -> _Result:
    """Run optional snapshot work with a real request-path wait budget.

    The worker is daemonized because it is non-authoritative. A timed-out task
    may finish later, but it cannot block SSE and it holds the single gate so
    no request fan-out or competing stale context can accumulate.
    """
    if not callable(work):
        raise ValueError("invalid optional context work")
    try:
        timeout_seconds = max(0, float(
            OPTIONAL_CONTEXT_TIMEOUT_MS if timeout_ms is None else timeout_ms)) / 1000
    except (TypeError, ValueError, OverflowError):
        raise ValueError("invalid optional context timeout") from None
    if not _optional_work_gate.acquire(blocking=False):
        raise OptionalContextBusy("optional_context_busy")
    completed = threading.Event()
    outcome: dict[str, object] = {}

    def _run():
        try:
            outcome["result"] = work()
        except Exception as error:
            outcome["error"] = error
        finally:
            completed.set()
            _optional_work_gate.release()

    threading.Thread(target=_run, name="individual-model-context", daemon=True).start()
    if not completed.wait(timeout_seconds):
        raise OptionalContextTimeout("optional_context_timeout")
    error = outcome.get("error")
    if isinstance(error, Exception):
        raise error
    if "result" not in outcome:
        raise RuntimeError("optional_context_missing_result")
    return outcome["result"]  # type: ignore[return-value]


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
            "completed_session_evidence_present": int(
                projection.authoritative_completed_session_evidence_freshness is not None),
            "prescribed_increase_observed": int(
                projection.trajectory_context == "increase_was_prescribed"),
            "prescribed_maintain_observed": int(
                projection.trajectory_context == "maintain_was_prescribed"),
            "trajectory_insufficient_evidence": int(
                projection.trajectory_context == "insufficient_evidence"),
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
