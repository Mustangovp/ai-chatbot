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

import os
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Callable

from .models import (
    CallerRouteStatus, CatalogMode, DietConstraints, NutritionPlanRequest,
    NutritionTargets, PracticalityPolicy,
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


# ── bounded, non-blocking dispatcher ────────────────────────────────────────

_MAX_INFLIGHT = 2  # one executing + one queued; hard bound on admitted work
_executor: ThreadPoolExecutor | None = None
_semaphore = threading.BoundedSemaphore(_MAX_INFLIGHT)
_init_lock = threading.Lock()
_counters: Counter = Counter()
_counters_lock = threading.Lock()


def _bump(name: str) -> None:
    with _counters_lock:
        _counters[name] += 1


def _ensure_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _init_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nutri-v2-shadow")
    return _executor


def dispatch(projection: NutritionShadowTargetProjection, *,
             sink: Callable[[object], None] | None = None) -> bool:
    """Admit at most _MAX_INFLIGHT tasks without ever blocking the caller.

    Returns True if admitted, False if dropped. On drop it does NOT block, retry,
    or run inline. Any exception path releases the semaphore.
    """
    if not _semaphore.acquire(blocking=False):
        _bump("shadow_dispatch_dropped")
        return False
    try:
        _ensure_executor().submit(_run, projection, sink)
    except Exception:
        _semaphore.release()
        _bump("shadow_dispatch_dropped")
        return False
    return True


def _run(projection: NutritionShadowTargetProjection,
         sink: Callable[[object], None] | None) -> None:
    """Background task. Isolated: no Flask, no persistence, no network."""
    try:
        request = to_request(projection)
        result = build_nutrition_plan(request)  # catalog=None → loads dev catalog
        _bump("shadow_" + result.outcome.value)
        if result.internal_metrics is not None and result.internal_metrics.hard_quality_findings:
            _bump("shadow_hard_quality")
        if sink is not None:  # offline tests only; production passes sink=None
            sink(build_shadow_record(request, result, None))
    except Exception:
        _bump("shadow_exception")
    finally:
        _semaphore.release()


def snapshot_counters() -> dict:
    """Bounded, enum-keyed counters. No fingerprint/hash/identity labels."""
    with _counters_lock:
        return dict(_counters)


def record_skip(reason: ShadowSkipReason) -> None:
    _bump(reason.value)
