"""Isolated, read-only Nutrition Engine V2 shadow hook.

Flag-off by default. This module is the ONLY place a future production request
touches V2. It never imports app, Flask, `g`, persistence, a database, an HTTP
client, or an LLM client. The background worker receives only an immutable typed
projection — never raw text, identity, or any Flask context.

Design (approved Phase 6B):
  * eligibility is decided from already-typed canonical authority;
  * a skipped request never calls ``build_nutrition_plan``;
  * allergy/exclusion prose forces a skip, never an omnivore default;
  * dispatch is non-blocking and bounded; the request thread never waits;
  * all V2 output is discarded; only bounded, privacy-safe counters remain.
"""
from __future__ import annotations

import atexit
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from time import monotonic
from typing import Callable

from .models import (
    CallerRouteStatus, CatalogMode, DietConstraints, NutritionPlanCode,
    NutritionPlanOutcome, NutritionPlanRequest, NutritionTargets, PracticalityPolicy,
)
from .service import SERVICE_VERSION, build_nutrition_plan
from .shadow import build_shadow_record

FLAG = "NUTRITION_ENGINE_V2_SHADOW"
_SHADOW_CATALOG_VERSION = "development-v2-source-backed"
_REQUIRED_MEALS = ("breakfast", "lunch", "dinner")
# Fixed, shadow-only development policy. Bounded search via max_search_nodes.
_SHADOW_POLICY = PracticalityPolicy(
    maximum_foods_per_meal=4,
    category_portion_overrides=(
        ("protein", Decimal("200"), Decimal("300"), Decimal("50")),
        ("carbohydrate", Decimal("100"), Decimal("200"), Decimal("50")),
        ("vegetable", Decimal("75"), Decimal("75"), Decimal("25")),
        ("fruit", Decimal("100"), Decimal("150"), Decimal("50")),
        ("fat", Decimal("5"), Decimal("5"), Decimal("5")),
    ),
    max_search_nodes=200_000,
)
_MAX_WORKERS = 1
_MAX_INFLIGHT = 2  # one executing + one queued; hard bound on admitted work
_SEMAPHORE_CAPACITY = _MAX_INFLIGHT
_SHADOW_TIMEOUT_SECONDS = 0.75
_STALL_THRESHOLD_SECONDS = 0.50
_LOGGER = logging.getLogger("apex.nutrition_v2_shadow")


# ── flag ────────────────────────────────────────────────────────────────────

def shadow_flag_enabled(getenv: Callable[[str, str], str] = os.getenv) -> bool:
    """Fail-closed: only the exact value 'true' (case/space-insensitive) enables."""
    return str(getenv(FLAG, "false")).strip().lower() == "true"


# ── eligibility ─────────────────────────────────────────────────────────────

class ShadowSkipReason(str, Enum):
    SHADOW_DISABLED = "skip_shadow_disabled"
    NOT_NUTRITION = "skip_not_nutrition"
    NOT_FULL_DAY = "skip_not_full_day"
    MISSING_AUTHORITATIVE_TARGETS = "skip_missing_authoritative_targets"
    MEDICAL_ROUTE = "skip_medical_route"
    DUPLICATE_EXECUTION = "skip_duplicate_execution"
    PROJECTION_UNAVAILABLE = "skip_projection_unavailable"
    CONSTRAINTS_NOT_STRUCTURED = "skip_constraints_not_structured"
    UNSUPPORTED_TYPED_CONSTRAINT = "skip_unsupported_typed_constraint"
    ALLERGY_AUTHORITY_UNAVAILABLE = "skip_allergy_authority_unavailable"
    SESSION_START = "skip_session_start"
    DISPATCH_SATURATED = "skip_dispatch_saturated"


@dataclass(frozen=True)
class ShadowEligibilityDecision:
    eligible: bool
    reason: ShadowSkipReason | None = None


def classify_eligibility(*, flag_enabled: bool, is_nutrition: bool, is_full_day: bool,
                         calorie_target, protein_target, route_is_medical: bool,
                         session_start: bool, already_attempted: bool,
                         allergy_prose: str, preference_tokens: str) -> ShadowEligibilityDecision:
    """Pure function of typed authority. Never reparses raw text or calls an LLM."""
    def skip(reason: ShadowSkipReason) -> ShadowEligibilityDecision:
        return ShadowEligibilityDecision(False, reason)

    if already_attempted:
        return skip(ShadowSkipReason.DUPLICATE_EXECUTION)
    if not flag_enabled:
        return skip(ShadowSkipReason.SHADOW_DISABLED)
    if session_start:
        return skip(ShadowSkipReason.SESSION_START)
    if route_is_medical:
        return skip(ShadowSkipReason.MEDICAL_ROUTE)
    if not is_nutrition:
        return skip(ShadowSkipReason.NOT_NUTRITION)
    if not is_full_day:
        return skip(ShadowSkipReason.NOT_FULL_DAY)
    if calorie_target is None or protein_target is None:
        return skip(ShadowSkipReason.MISSING_AUTHORITATIVE_TARGETS)
    # Constraint safety: production stores allergies as prose and preferences as
    # tokens. Neither is typed for V2, so ANY restriction data forces a skip.
    if allergy_prose is not None and str(allergy_prose).strip():
        return skip(ShadowSkipReason.ALLERGY_AUTHORITY_UNAVAILABLE)
    if preference_tokens is not None and str(preference_tokens).strip():
        return skip(ShadowSkipReason.UNSUPPORTED_TYPED_CONSTRAINT)
    return ShadowEligibilityDecision(True, None)


# ── immutable projection ────────────────────────────────────────────────────

@dataclass(frozen=True)
class NutritionShadowTargetProjection:
    language: str
    catalog_version: str
    catalog_mode: CatalogMode
    calorie_target: Decimal
    protein_target: Decimal
    diet_constraints: DietConstraints
    required_meals: tuple[str, ...]
    practicality_policy: PracticalityPolicy
    route_status: CallerRouteStatus
    service_version: str
    carbs_target: Decimal | None = None
    fat_target: Decimal | None = None


def build_projection(*, language: str, calorie_target: Decimal, protein_target: Decimal,
                     carbs_target: Decimal | None = None,
                     fat_target: Decimal | None = None) -> NutritionShadowTargetProjection:
    """Build the projection from typed authority only. No prose, no identity.

    Only reached for eligible requests, so the constraint set is a plain
    standard-omnivore set (restriction data would already have caused a skip).
    """
    return NutritionShadowTargetProjection(
        language="en" if str(language).lower() == "en" else "bg",
        catalog_version=_SHADOW_CATALOG_VERSION,
        catalog_mode=CatalogMode.DEVELOPMENT,
        calorie_target=calorie_target,
        protein_target=protein_target,
        carbs_target=carbs_target,
        fat_target=fat_target,
        diet_constraints=DietConstraints(),
        required_meals=_REQUIRED_MEALS,
        practicality_policy=_SHADOW_POLICY,
        route_status=CallerRouteStatus.ELIGIBLE,
        service_version=SERVICE_VERSION,
    )


def to_request(projection: NutritionShadowTargetProjection) -> NutritionPlanRequest:
    targets = NutritionTargets(
        projection.calorie_target, Decimal("0.05"), projection.protein_target,
        None, projection.carbs_target, None, projection.fat_target, None)
    return NutritionPlanRequest(
        language=projection.language,
        catalog_version=projection.catalog_version,
        catalog_mode=projection.catalog_mode,
        diet_constraints=projection.diet_constraints,
        required_meals=projection.required_meals,
        practicality_policy=projection.practicality_policy,
        caller_route_status=projection.route_status,
        service_version=projection.service_version,
        targets=targets,
    )


# ── bounded runtime lifecycle and telemetry ─────────────────────────────────

_TELEMETRY_COUNTERS = (
    "eligible", "skipped", "dispatched", "dropped", "completed", "timeout",
    "exception", "internal_fail_closed", "optimizer_failure", "catalog_failure",
    "quality_failure", "stalled", "initialization_failure", "shutdown_cancelled",
)


def _new_telemetry() -> dict[str, int | float]:
    telemetry: dict[str, int | float] = {name: 0 for name in _TELEMETRY_COUNTERS}
    telemetry.update({
        "current_inflight": 0,
        "current_queue_depth": 0,
        "maximum_inflight": 0,
        "maximum_queue_depth": 0,
        "longest_execution_ms": 0.0,
    })
    return telemetry


@dataclass
class _TaskState:
    released: bool = False
    started: bool = False
    queued: bool = True
    future: object | None = None


_executor: ThreadPoolExecutor | None = None
_semaphore = threading.BoundedSemaphore(_SEMAPHORE_CAPACITY)
_runtime_lock = threading.RLock()
_telemetry_lock = threading.Lock()
_telemetry = _new_telemetry()
_task_states: dict[int, _TaskState] = {}
_runtime_closed = False


def _record(**changes: int | float) -> None:
    with _telemetry_lock:
        for key, amount in changes.items():
            _telemetry[key] = _telemetry.get(key, 0) + amount


def _validate_runtime_configuration() -> None:
    if _MAX_WORKERS != 1:
        raise RuntimeError("shadow runtime requires exactly one worker")
    if _MAX_INFLIGHT < _MAX_WORKERS or _SEMAPHORE_CAPACITY != _MAX_INFLIGHT:
        raise RuntimeError("shadow runtime admission capacity is invalid")
    if _SHADOW_TIMEOUT_SECONDS <= 0 or _STALL_THRESHOLD_SECONDS <= 0:
        raise RuntimeError("shadow runtime timeout configuration is invalid")
    with _telemetry_lock:
        if any(name not in _telemetry for name in _TELEMETRY_COUNTERS):
            raise RuntimeError("shadow telemetry is not initialized")


def _ensure_executor() -> ThreadPoolExecutor:
    """Create exactly one process-local executor after validating runtime state."""
    global _executor
    with _runtime_lock:
        if _runtime_closed:
            raise RuntimeError("shadow runtime is shut down")
        _validate_runtime_configuration()
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=_MAX_WORKERS,
                thread_name_prefix="nutri-v2-shadow",
            )
        return _executor


def _release_task(task_id: int, state: _TaskState) -> None:
    with _runtime_lock:
        if state.released:
            return
        state.released = True
        _task_states.pop(task_id, None)
    _semaphore.release()


def _mark_started(task_id: int, state: _TaskState) -> None:
    with _runtime_lock:
        if state.released or state.started:
            return
        state.started = True
        state.queued = False
    with _telemetry_lock:
        _telemetry["current_queue_depth"] = max(0, _telemetry["current_queue_depth"] - 1)
        _telemetry["current_inflight"] += 1
        _telemetry["maximum_inflight"] = max(
            _telemetry["maximum_inflight"], _telemetry["current_inflight"])


def _mark_finished(state: _TaskState, duration_ms: float) -> None:
    if state.started:
        with _telemetry_lock:
            _telemetry["current_inflight"] = max(0, _telemetry["current_inflight"] - 1)
            _telemetry["longest_execution_ms"] = max(_telemetry["longest_execution_ms"], duration_ms)
    if duration_ms >= _STALL_THRESHOLD_SECONDS * 1000:
        _record(stalled=1)


def log_runtime_error(event: str, error: BaseException | None = None,
                      *, reason: str = "runtime_error") -> None:
    """Emit a compact, PII-free diagnostic only for unexpected runtime failures."""
    exception_type = type(error).__name__ if error is not None else "none"
    _LOGGER.warning(
        "[nutrition-v2-shadow] event=%s reason=%s exception=%s worker_id=%s",
        event, reason, exception_type, os.getpid(),
    )


def record_eligible() -> None:
    _record(eligible=1)


def dispatch(projection: NutritionShadowTargetProjection, *,
             sink: Callable[[object], None] | None = None) -> bool:
    """Admit bounded work without blocking the request thread or retrying inline."""
    if not _semaphore.acquire(blocking=False):
        _record(dropped=1)
        return False
    state = _TaskState()
    task_id = id(state)
    try:
        executor = _ensure_executor()
        with _runtime_lock:
            _task_states[task_id] = state
        with _telemetry_lock:
            _telemetry["dispatched"] += 1
            _telemetry["current_queue_depth"] += 1
            _telemetry["maximum_queue_depth"] = max(
                _telemetry["maximum_queue_depth"], _telemetry["current_queue_depth"])
        state.future = executor.submit(_run, task_id, state, projection, sink)
        return True
    except Exception as error:
        _record(dropped=1, initialization_failure=1)
        log_runtime_error("dispatch_failed", error)
        if state.queued:
            with _telemetry_lock:
                _telemetry["current_queue_depth"] = max(0, _telemetry["current_queue_depth"] - 1)
        _release_task(task_id, state)
        return False


def _record_result(result) -> None:
    _record(completed=1)
    if result.outcome is NutritionPlanOutcome.TIMEOUT:
        _record(timeout=1)
    elif result.outcome is NutritionPlanOutcome.INTERNAL_FAIL_CLOSED:
        _record(internal_fail_closed=1)
    elif result.code is NutritionPlanCode.CATALOG_NOT_READY:
        _record(catalog_failure=1)
    elif result.code is NutritionPlanCode.QUALITY_CONSTRAINTS_INFEASIBLE:
        _record(quality_failure=1)
    elif result.outcome is NutritionPlanOutcome.INFEASIBLE:
        _record(optimizer_failure=1)


def _run(task_id: int, state: _TaskState, projection: NutritionShadowTargetProjection,
         sink: Callable[[object], None] | None) -> None:
    """Run one deadline-bound, isolated task with guaranteed cleanup."""
    started = monotonic()
    _mark_started(task_id, state)
    try:
        request = to_request(projection)
        result = build_nutrition_plan(
            request,
            deadline_monotonic=started + _SHADOW_TIMEOUT_SECONDS,
        )
        duration_ms = (monotonic() - started) * 1000
        _record_result(result)
        if sink is not None:  # offline tests only; production passes sink=None
            sink(build_shadow_record(request, result, duration_ms))
    except Exception as error:
        duration_ms = (monotonic() - started) * 1000
        _record(exception=1)
        log_runtime_error("worker_failed", error)
    finally:
        _mark_finished(state, duration_ms)
        _release_task(task_id, state)


def shutdown_runtime(*, wait: bool = True) -> None:
    """Stop admission, cancel queued work, and join the sole executor deterministically."""
    global _executor, _runtime_closed
    with _runtime_lock:
        _runtime_closed = True
        executor = _executor
        states = tuple((task_id, state) for task_id, state in _task_states.items())
    for task_id, state in states:
        future = state.future
        if future is not None and getattr(future, "cancel")():
            if state.queued:
                with _telemetry_lock:
                    _telemetry["current_queue_depth"] = max(0, _telemetry["current_queue_depth"] - 1)
            _record(shutdown_cancelled=1)
            _release_task(task_id, state)
    if executor is not None:
        executor.shutdown(wait=wait, cancel_futures=True)
    with _runtime_lock:
        if _executor is executor:
            _executor = None


def _reset_runtime_for_testing() -> None:
    """Test-only reset; production lifecycle is process ownership plus atexit cleanup."""
    global _runtime_closed, _semaphore, _telemetry
    shutdown_runtime(wait=True)
    with _runtime_lock:
        _runtime_closed = False
        _semaphore = threading.BoundedSemaphore(_SEMAPHORE_CAPACITY)
        _task_states.clear()
    with _telemetry_lock:
        _telemetry = _new_telemetry()


def snapshot_telemetry() -> dict[str, int | float]:
    """Return PII-free process-local telemetry; no values are persisted or exposed."""
    with _telemetry_lock:
        return dict(_telemetry)


def snapshot_counters() -> dict[str, int | float]:
    """Backward-compatible alias for Phase 6 test-only telemetry access."""
    return snapshot_telemetry()


def record_skip(reason: ShadowSkipReason) -> None:
    _record(skipped=1)
    with _telemetry_lock:
        _telemetry[reason.value] = _telemetry.get(reason.value, 0) + 1


atexit.register(shutdown_runtime)
