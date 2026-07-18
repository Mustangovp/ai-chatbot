"""Pure, deterministic, isolated Nutrition Engine V2 service (Phase 5).

``build_nutrition_plan`` composes the existing isolated pieces — catalog
governance, candidate builder, optimizer, feasibility, quality, canonical meal
assembly and the user-safe projection — behind one typed contract. It performs
no I/O beyond reading the packaged development catalog file, makes no network,
DB, LLM, SSE, quota or environment call, and never mutates its inputs.

The optimizer is the single source of plan numbers. Rotation and preferences are
lower-priority deterministic *ordering* signals recorded as internal findings;
they never change an optimized quantity, macro, or calorie, and never re-add an
excluded or allergen food. Any unexpected internal error fails closed with no
partial plan.

Phase 5 limitations (development-only, not production-ready):
  * This service is isolated and is NOT connected to the APEX runtime. There is
    no hook in app.py, no persistence, and no user-history integration; rotation
    context is passed in per call, never read from or written to storage.
  * The current catalog has zero PRODUCTION_READY records and portion governance
    remains TEST_POLICY_ONLY, so ``production_ready`` mode deliberately returns
    catalog_not_ready for every current record.
  * Offline-evaluation "eligible" cases sit inside the documented feasible
    envelope (roughly 1850-2010 kcal with ~160-198 g protein under the isolated
    development policy). A ``success`` outcome is a *technical* solver result, not
    nutritional, medical, or culinary approval.
  * No feature flag exists and production activation remains forbidden until a
    later phase explicitly authorizes it.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .candidate_builder import build_candidates
from .catalog import Catalog, CatalogGovernance, load_catalog_file
from .feasibility import FeasibilityCode, FeasibilityResult
from .models import (
    CatalogMode, CallerRouteStatus, DietConstraints, NutritionPlanCode,
    NutritionPlanOutcome, NutritionPlanRequest, NutritionTargets, PreferenceWeights,
    RotationContext,
)
from .projection import UserPlanProjection, canonical_bytes, project_meal_day
from .quality import evaluate_quality
from .selector import assemble_meal_day
from .optimizer import optimize

SERVICE_VERSION = "nutrition-engine-v2-phase5"
_CATALOG_PATH = Path(__file__).parent / "data" / "food_catalog_v1.json"
_KCAL_TOLERANCE = Decimal("15")


@dataclass(frozen=True)
class InternalMetrics:
    """Non-user-facing, PII-free observability. No raw text, no identity."""

    development_only: bool
    hard_quality_findings: tuple[str, ...]
    soft_quality_findings: tuple[str, ...]
    preference_findings: tuple[str, ...]
    rotation_findings: tuple[str, ...]
    calorie_deviation: Decimal | None
    protein_deviation: Decimal | None
    selected_role_summary: tuple[tuple[str, str], ...]
    solve_duration_ms: Decimal | None = None


@dataclass(frozen=True)
class NutritionPlanResult:
    outcome: NutritionPlanOutcome
    code: NutritionPlanCode
    service_version: str
    catalog_version: str
    quality_findings: tuple[str, ...] = ()
    projection: UserPlanProjection | None = None
    internal_metrics: InternalMetrics | None = None
    target_deviations: tuple[tuple[str, Decimal], ...] | None = None
    deterministic_output_hash: str | None = None

    def __post_init__(self) -> None:
        if self.outcome is not NutritionPlanOutcome.SUCCESS and self.projection is not None:
            raise ValueError("a non-success result must not carry a projection")


# ── ordering-only rotation & preference helpers (pure, deterministic) ────────

def order_alternatives_by_preference(food_ids: Sequence[str],
                                     preferences: PreferenceWeights | None) -> tuple[str, ...]:
    """Stable reordering: preferred first, disliked last. Never adds or drops.

    A disliked food is only *deprioritized*, never excluded — exclusion is the
    caller's job via DietConstraints. Deterministic (stable, index-tie-broken).
    """
    items = list(food_ids)
    if preferences is None:
        return tuple(items)

    def rank(entry):
        food_id, index = entry
        if food_id in preferences.preferred_food_ids:
            bucket = 0
        elif food_id in preferences.disliked_food_ids:
            bucket = 2
        else:
            bucket = 1
        return (bucket, index)

    return tuple(food_id for food_id, _ in sorted(
        ((food_id, index) for index, food_id in enumerate(items)), key=rank))


def rotation_choice(alternatives: Sequence[str], recent_ids: Sequence[str],
                    exclusions: frozenset[str]) -> str | None:
    """Pick one alternative, avoiding recent use, always honouring exclusions.

    Exclusions win absolutely. Among eligible foods, prefer one not in recent
    history; if all were recently used, pick the *oldest* (earliest in recent).
    Deterministic; returns None only when exclusions remove every option.
    """
    eligible = [food_id for food_id in alternatives if food_id not in exclusions]
    if not eligible:
        return None
    fresh = [food_id for food_id in eligible if food_id not in recent_ids]
    if fresh:
        return fresh[0]
    # all recently used: choose the one used longest ago (earliest recent index)
    return min(eligible, key=lambda fid: (recent_ids.index(fid), eligible.index(fid)))


# ── failure mapping ─────────────────────────────────────────────────────────

_FEASIBILITY_MAP = {
    FeasibilityCode.CALORIE_TARGET_UNREACHABLE:
        (NutritionPlanOutcome.INFEASIBLE, NutritionPlanCode.CALORIE_TARGET_UNREACHABLE),
    FeasibilityCode.PROTEIN_MINIMUM_UNREACHABLE:
        (NutritionPlanOutcome.INFEASIBLE, NutritionPlanCode.PROTEIN_MINIMUM_UNREACHABLE),
    FeasibilityCode.PROTEIN_CAP_CONFLICT:
        (NutritionPlanOutcome.INFEASIBLE, NutritionPlanCode.PROTEIN_CAP_CONFLICT),
    FeasibilityCode.MEAL_STRUCTURE_INFEASIBLE:
        (NutritionPlanOutcome.INFEASIBLE, NutritionPlanCode.MEAL_STRUCTURE_INFEASIBLE),
    FeasibilityCode.PORTION_BOUNDS_INFEASIBLE:
        (NutritionPlanOutcome.INFEASIBLE, NutritionPlanCode.MEAL_STRUCTURE_INFEASIBLE),
    FeasibilityCode.SEARCH_LIMIT_REACHED:
        (NutritionPlanOutcome.INFEASIBLE, NutritionPlanCode.SEARCH_LIMIT_REACHED),
    FeasibilityCode.QUALITY_CONSTRAINTS_INFEASIBLE:
        (NutritionPlanOutcome.INFEASIBLE, NutritionPlanCode.QUALITY_CONSTRAINTS_INFEASIBLE),
    FeasibilityCode.UNSUPPORTED_DIET:
        (NutritionPlanOutcome.UNSUPPORTED, NutritionPlanCode.UNSUPPORTED_DIET),
    FeasibilityCode.EXCLUSIONS_REMOVE_ALL_PROTEIN_SOURCES:
        (NutritionPlanOutcome.UNSUPPORTED, NutritionPlanCode.CANDIDATE_COVERAGE_INSUFFICIENT),
    FeasibilityCode.CATALOG_ROLE_COVERAGE_INSUFFICIENT:
        (NutritionPlanOutcome.UNSUPPORTED, NutritionPlanCode.CANDIDATE_COVERAGE_INSUFFICIENT),
    FeasibilityCode.CATALOG_NOT_PRODUCTION_READY:
        (NutritionPlanOutcome.CATALOG_NOT_READY, NutritionPlanCode.CATALOG_NOT_READY),
    FeasibilityCode.CATALOG_VERSION_MISMATCH:
        (NutritionPlanOutcome.INFEASIBLE, NutritionPlanCode.CATALOG_VERSION_MISMATCH),
}


def _fail(outcome, code, catalog_version, service_version, **extra) -> NutritionPlanResult:
    return NutritionPlanResult(outcome, code, service_version, catalog_version, **extra)


def _role_summary(catalog: Catalog, day) -> tuple[tuple[str, str], ...]:
    """Category composition per meal — never food ids."""
    summary = []
    for meal in day.meals:
        cats = sorted({catalog.by_id(item.food_id).category for item in meal.foods
                       if catalog.by_id(item.food_id)})
        summary.append((meal.meal_type, "+".join(cats)))
    return tuple(summary)


def _preference_findings(catalog: Catalog, preferences: PreferenceWeights | None) -> tuple[str, ...]:
    if preferences is None:
        return ()
    known = {food.food_id for food in catalog.foods}
    unknown_pref = sum(1 for fid in preferences.preferred_food_ids if fid not in known)
    unknown_dis = sum(1 for fid in preferences.disliked_food_ids if fid not in known)
    findings = []
    if unknown_pref:
        findings.append(f"unknown_preferred_ids:{unknown_pref}")
    if unknown_dis:
        findings.append(f"unknown_disliked_ids:{unknown_dis}")
    return tuple(findings)


def _rotation_findings(catalog: Catalog, day, rotation: RotationContext | None,
                       exclusions: frozenset[str]) -> tuple[str, ...]:
    """Record variety observations only. Never mutates the optimized plan."""
    if rotation is None:
        return ()
    rotation = rotation.sanitized()
    findings: list[str] = []
    meals = {meal.meal_type: meal for meal in day.meals}
    main = meals.get("lunch") or meals.get("dinner")
    if main is not None:
        proteins = [item.food_id for item in main.foods
                    if catalog.by_id(item.food_id) and catalog.by_id(item.food_id).category == "protein"]
        for protein_id in proteins:
            # rotation may never introduce an excluded food: assert invariant
            if protein_id in exclusions:
                raise AssertionError("rotation surfaced an excluded food")
            if protein_id in rotation.recent_main_protein_ids:
                findings.append("main_protein_recently_used")
                break
    return tuple(sorted(set(findings)))


# ── the pure service ────────────────────────────────────────────────────────

def build_nutrition_plan(request: NutritionPlanRequest, *,
                         catalog: Catalog | None = None) -> NutritionPlanResult:
    """Compose the isolated engine into one typed, deterministic result."""
    service_version = request.service_version
    catalog_version = request.catalog_version
    try:
        # 1 — caller route status (highest precedence; before catalog/optimizer)
        if request.caller_route_status is CallerRouteStatus.MEDICAL_ROUTING_REQUIRED:
            return _fail(NutritionPlanOutcome.UNSUPPORTED,
                         NutritionPlanCode.MEDICAL_ROUTING_REQUIRED, catalog_version, service_version)
        if request.caller_route_status is CallerRouteStatus.UNSUPPORTED_PROFILE_AUTHORITY:
            return _fail(NutritionPlanOutcome.UNSUPPORTED,
                         NutritionPlanCode.UNSUPPORTED_PROFILE_AUTHORITY, catalog_version, service_version)

        # 4 — catalog governance / readiness / version (precedence above targets)
        resolved, catalog_error = _resolve_catalog(request, catalog)
        if catalog_error is not None:
            return catalog_error
        catalog = resolved
        catalog_version = catalog.version
        development_only = request.catalog_mode is CatalogMode.DEVELOPMENT

        # 5 — calorie & protein target authority
        targets = request.targets
        if targets is None or targets.protein_min_g is None:
            return _fail(NutritionPlanOutcome.CLARIFICATION_REQUIRED,
                         NutritionPlanCode.MISSING_TARGET_AUTHORITY, catalog_version, service_version)

        constraints = request.diet_constraints
        exclusions = _hard_exclusions(catalog, constraints)

        # 4 (candidate build) — unsupported diet / allergy / coverage
        plan = build_candidates(catalog, targets, constraints,
                                tuple(request.required_meals), request.practicality_policy)
        if plan is None:
            return _classify_candidate_failure(constraints, catalog_version, service_version)

        # 5/6/7 — optimizer is the single authority for numbers
        result = optimize(catalog, targets, constraints, plan.selections, request.practicality_policy)
        if not result.feasible or result.day is None:
            outcome, code = _FEASIBILITY_MAP.get(
                result.code, (NutritionPlanOutcome.INFEASIBLE, NutritionPlanCode.MEAL_STRUCTURE_INFEASIBLE))
            return _fail(outcome, code, catalog_version, service_version)
        day = result.day

        # 9 — quality: hard failure blocks success; soft findings are recorded only
        quality = evaluate_quality(catalog, day)
        if not quality.acceptable:
            return _fail(NutritionPlanOutcome.INFEASIBLE,
                         NutritionPlanCode.QUALITY_CONSTRAINTS_INFEASIBLE,
                         catalog_version, service_version,
                         quality_findings=quality.hard_violations)

        # 8 — canonical assembly (never changes numbers)
        meal_day = assemble_meal_day(catalog, result)

        # 10 — lower-priority ordering-only signals (never alter the plan)
        preference_findings = _preference_findings(catalog, request.preference_weights)
        rotation_findings = _rotation_findings(catalog, day, request.rotation_context, exclusions)

        # 9/10 — the single user-safe projection + deterministic hash
        projection = project_meal_day(meal_day, request.language)
        output_hash = hashlib.sha256(canonical_bytes(projection)).hexdigest()

        metrics = InternalMetrics(
            development_only=development_only,
            hard_quality_findings=quality.hard_violations,
            soft_quality_findings=quality.soft_penalties,
            preference_findings=preference_findings,
            rotation_findings=rotation_findings,
            calorie_deviation=day.daily_totals.kcal - targets.calories_target,
            protein_deviation=day.daily_totals.protein_g - targets.protein_min_g,
            selected_role_summary=_role_summary(catalog, day),
        )
        return NutritionPlanResult(
            outcome=NutritionPlanOutcome.SUCCESS,
            code=NutritionPlanCode.SUCCESS,
            service_version=service_version,
            catalog_version=catalog_version,
            quality_findings=quality.soft_penalties,
            projection=projection,
            internal_metrics=metrics,
            target_deviations=day.target_deviations,
            deterministic_output_hash=output_hash,
        )
    except Exception:  # noqa: BLE001 — fail closed, expose nothing
        return NutritionPlanResult(
            outcome=NutritionPlanOutcome.INTERNAL_FAIL_CLOSED,
            code=NutritionPlanCode.INTERNAL_FAIL_CLOSED,
            service_version=service_version,
            catalog_version=catalog_version,
        )


def _resolve_catalog(request: NutritionPlanRequest, supplied: Catalog | None):
    """Return (catalog, None) or (None, failure_result) per governance + version."""
    version = request.catalog_version
    service_version = request.service_version
    if request.catalog_mode is CatalogMode.PRODUCTION_READY:
        if supplied is None:
            try:
                catalog = load_catalog_file(
                    _CATALOG_PATH, CatalogGovernance(False, True, _KCAL_TOLERANCE))
            except Exception:
                return None, _fail(NutritionPlanOutcome.CATALOG_NOT_READY,
                                   NutritionPlanCode.CATALOG_NOT_READY, version, service_version)
        else:
            catalog = supplied
        if any(food.review_status != "PRODUCTION_READY" for food in catalog.foods):
            return None, _fail(NutritionPlanOutcome.CATALOG_NOT_READY,
                               NutritionPlanCode.CATALOG_NOT_READY, catalog.version, service_version)
    else:
        if supplied is None:
            try:
                catalog = load_catalog_file(
                    _CATALOG_PATH, CatalogGovernance(True, False, _KCAL_TOLERANCE))
            except Exception:
                return None, _fail(NutritionPlanOutcome.CATALOG_NOT_READY,
                                   NutritionPlanCode.CATALOG_NOT_READY, version, service_version)
        else:
            catalog = supplied
    if version != catalog.version:
        return None, _fail(NutritionPlanOutcome.INFEASIBLE,
                           NutritionPlanCode.CATALOG_VERSION_MISMATCH, version, service_version)
    return catalog, None


def _hard_exclusions(catalog: Catalog, constraints: DietConstraints) -> frozenset[str]:
    """Every food id the caller's exclusions/allergies forbid. Preferences excluded."""
    forbidden = set(constraints.excluded_food_ids)
    for food in catalog.foods:
        if food.category in constraints.excluded_categories:
            forbidden.add(food.food_id)
        if food.allergens & constraints.allergen_exclusions:
            forbidden.add(food.food_id)
        if constraints.no_chicken and "chicken" in food.dietary_tags:
            forbidden.add(food.food_id)
        if constraints.no_dairy and "dairy" in food.dietary_tags:
            forbidden.add(food.food_id)
    return frozenset(forbidden)


def _classify_candidate_failure(constraints: DietConstraints, catalog_version, service_version):
    if constraints.diet_type not in {"standard_omnivore", "no_chicken", "no_dairy"}:
        return _fail(NutritionPlanOutcome.UNSUPPORTED, NutritionPlanCode.UNSUPPORTED_DIET,
                     catalog_version, service_version)
    if constraints.allergen_exclusions:
        return _fail(NutritionPlanOutcome.UNSUPPORTED, NutritionPlanCode.UNSUPPORTED_ALLERGY,
                     catalog_version, service_version)
    return _fail(NutritionPlanOutcome.UNSUPPORTED, NutritionPlanCode.CANDIDATE_COVERAGE_INSUFFICIENT,
                 catalog_version, service_version)
