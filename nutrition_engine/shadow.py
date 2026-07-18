"""Minimized, privacy-safe shadow records for the isolated nutrition service.

A shadow record carries only normalized, typed observability. It never contains
raw user text, identity, conversation, prompts, medical text, food names, source
ids, or solver traces. The request fingerprint is a one-way hash of normalized
typed authority, so logging it never reveals the original values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from .models import DietConstraints, NutritionPlanRequest, NutritionTargets
from .service import NutritionPlanResult


@dataclass(frozen=True)
class ShadowNutritionRecord:
    request_fingerprint: str
    service_version: str
    catalog_version: str
    outcome: str
    code: str
    calorie_deviation: Decimal | None
    protein_deviation: Decimal | None
    hard_quality_finding_count: int
    soft_quality_finding_count: int
    solve_duration_ms: Decimal | None
    selected_role_summary: tuple[tuple[str, str], ...]
    deterministic_output_hash: str | None


def _targets_fingerprint(targets: NutritionTargets | None) -> dict:
    if targets is None:
        return {"present": False}
    return {
        "present": True,
        "kcal": str(targets.calories_target),
        "tol": str(targets.calories_tolerance),
        "p_min": None if targets.protein_min_g is None else str(targets.protein_min_g),
        "p_max": None if targets.protein_max_g is None else str(targets.protein_max_g),
        "c_min": None if targets.carbs_min_g is None else str(targets.carbs_min_g),
        "c_max": None if targets.carbs_max_g is None else str(targets.carbs_max_g),
        "f_min": None if targets.fat_min_g is None else str(targets.fat_min_g),
        "f_max": None if targets.fat_max_g is None else str(targets.fat_max_g),
    }


def _constraints_fingerprint(constraints: DietConstraints) -> dict:
    return {
        "excluded_food_ids": sorted(constraints.excluded_food_ids),
        "excluded_categories": sorted(constraints.excluded_categories),
        "allergen_exclusions": sorted(constraints.allergen_exclusions),
        "no_chicken": constraints.no_chicken,
        "no_dairy": constraints.no_dairy,
        "diet_type": constraints.diet_type,
        "allowed_catalog_version": constraints.allowed_catalog_version,
    }


def fingerprint_request(request: NutritionPlanRequest) -> str:
    """Stable one-way fingerprint of the normalized typed authority only.

    Deterministic for identical typed input; independent of dict/set iteration
    order, time, environment, and locale. Reveals none of the original values.
    """
    rotation = request.rotation_context.sanitized() if request.rotation_context else None
    preferences = request.preference_weights
    document = {
        "language": request.language,
        "catalog_version": request.catalog_version,
        "catalog_mode": request.catalog_mode.value,
        "caller_route_status": request.caller_route_status.value,
        "service_version": request.service_version,
        "required_meals": sorted(request.required_meals),
        "targets": _targets_fingerprint(request.targets),
        "constraints": _constraints_fingerprint(request.diet_constraints),
        "rotation_depth": None if rotation is None else rotation.maximum_history_depth,
        "preferences": None if preferences is None else {
            "preferred": sorted(preferences.preferred_food_ids),
            "disliked": sorted(preferences.disliked_food_ids),
            "categories": sorted(preferences.preferred_categories),
            "budget": str(preferences.budget_preference),
            "prep": str(preferences.preparation_preference),
            "size": str(preferences.meal_size_preference),
        },
    }
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"),
                         sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_shadow_record(request: NutritionPlanRequest, result: NutritionPlanResult,
                        duration_ms: Decimal | float | int | None) -> ShadowNutritionRecord:
    """Assemble a minimized shadow record from a request and its result.

    Pulls only counts, deviations, and category role summaries — never food
    names, ids, source ids, or raw text.
    """
    metrics = result.internal_metrics
    duration = None if duration_ms is None else Decimal(str(duration_ms))
    return ShadowNutritionRecord(
        request_fingerprint=fingerprint_request(request),
        service_version=result.service_version,
        catalog_version=result.catalog_version,
        outcome=result.outcome.value,
        code=result.code.value,
        calorie_deviation=None if metrics is None else metrics.calorie_deviation,
        protein_deviation=None if metrics is None else metrics.protein_deviation,
        hard_quality_finding_count=0 if metrics is None else len(metrics.hard_quality_findings),
        soft_quality_finding_count=0 if metrics is None else len(metrics.soft_quality_findings),
        solve_duration_ms=duration,
        selected_role_summary=() if metrics is None else metrics.selected_role_summary,
        deterministic_output_hash=result.deterministic_output_hash,
    )
