"""Canonical delivery adapter for approved Nutrition Engine V2 results.

The adapter is deliberately strict: it accepts only the existing V2 service
result built with production-ready catalog governance, then validates the
result again through the authoritative ``nutrition_plan`` contract. It does
not parse rendered text, infer catalog identities, or provide a fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

import nutrition_plan
from nutrition_validation import NutritionTargets as DeliveryTargets

from .catalog import Catalog, CatalogGovernance, load_catalog_file
from .daily_policy import DAILY_PLAN_PRACTICALITY_POLICY
from .models import (
    CallerRouteStatus,
    CatalogMode,
    DietConstraints,
    NutritionPlanCode,
    NutritionPlanOutcome,
    NutritionPlanRequest,
    NutritionTargets,
)
from .service import SERVICE_VERSION, NutritionPlanResult, build_nutrition_plan
from .history import rotation_context_from_plan_records


_CATALOG_PATH = Path(__file__).parent / "data" / "food_catalog_v1.json"
_KCAL_TOLERANCE = Decimal("15")
_MEAL_TIMES = {"breakfast": "08:00", "snack": "10:30", "lunch": "13:00", "dinner": "19:00"}
_REQUIRED_MEALS = ("breakfast", "lunch", "dinner")


@dataclass(frozen=True)
class CanonicalV2Evaluation:
    """Result visible to the runtime, never directly to a user."""

    plan: nutrition_plan.NutritionPlan | None
    result: NutritionPlanResult


def load_production_food_catalog() -> Catalog:
    """Load the single existing V2 food catalog under strict governance."""
    return load_catalog_file(
        _CATALOG_PATH,
        CatalogGovernance(False, True, _KCAL_TOLERANCE),
    )


def _failure(code: NutritionPlanCode, *, catalog_version: str = "unavailable") -> NutritionPlanResult:
    if code is NutritionPlanCode.CATALOG_NOT_READY:
        outcome = NutritionPlanOutcome.CATALOG_NOT_READY
    elif code is NutritionPlanCode.INTERNAL_FAIL_CLOSED:
        outcome = NutritionPlanOutcome.INTERNAL_FAIL_CLOSED
    else:
        outcome = NutritionPlanOutcome.UNSUPPORTED
    return NutritionPlanResult(
        outcome=outcome,
        code=code,
        service_version=SERVICE_VERSION,
        catalog_version=catalog_version,
    )


def _request(*, language: str, targets: DeliveryTargets, catalog: Catalog,
             restrictions: tuple[str, ...], medical_route: bool,
             recent_plan_records: Sequence[Mapping[str, object]] | object = ()) -> NutritionPlanRequest:
    route = CallerRouteStatus.ELIGIBLE
    if medical_route:
        route = CallerRouteStatus.MEDICAL_ROUTING_REQUIRED
    elif restrictions:
        # Existing browser-profile restrictions are prose today. Until they are
        # represented as typed catalog constraints, an active V2 delivery must
        # not reinterpret them as an unrestricted request.
        route = CallerRouteStatus.UNSUPPORTED_PROFILE_AUTHORITY
    def lower(value: Decimal | None) -> Decimal | None:
        return None if value is None else value * Decimal("0.95")

    def upper(value: Decimal | None) -> Decimal | None:
        return None if value is None else value * Decimal("1.05")

    return NutritionPlanRequest(
        language="en" if str(language).lower() == "en" else "bg",
        catalog_version=catalog.version,
        catalog_mode=CatalogMode.PRODUCTION_READY,
        diet_constraints=DietConstraints(),
        required_meals=_REQUIRED_MEALS,
        practicality_policy=DAILY_PLAN_PRACTICALITY_POLICY,
        caller_route_status=route,
        service_version=SERVICE_VERSION,
        targets=NutritionTargets(
            calories_target=targets.kcal,
            calories_tolerance=Decimal("0.05"),
            protein_min_g=lower(targets.protein),
            protein_max_g=upper(targets.protein),
            carbs_min_g=lower(targets.carbs),
            carbs_max_g=upper(targets.carbs),
            fat_min_g=lower(targets.fat),
            fat_max_g=upper(targets.fat),
        ),
        rotation_context=rotation_context_from_plan_records(recent_plan_records),
    )


def _payload_from_result(result: NutritionPlanResult, catalog: Catalog, language: str) -> dict[str, object]:
    day = result.source_day
    if day is None:
        raise ValueError("successful V2 result has no canonical meal day")
    meals = []
    english = str(language).lower() == "en"
    for meal in day.meals:
        if meal.meal_type not in _MEAL_TIMES:
            raise ValueError("V2 meal type is not deliverable")
        foods = []
        for optimized in meal.foods:
            source = catalog.by_id(optimized.food_id)
            if source is None:
                raise ValueError("V2 output references a non-policy food")
            foods.append({
                "display_name": source.display_name_en if english else source.display_name_bg,
                "catalog_id": source.food_id,
                "food_id": source.food_id,
                # V2 quantities are the approved, delivered portions. This avoids
                # reinterpreting a catalog preparation label as raw/cooked grams.
                "measurement_state": "as_served",
                "grams": str(optimized.grams),
                "protein_g": str(optimized.macros.protein_g),
                "carbs_g": str(optimized.macros.carbs_g),
                "fat_g": str(optimized.macros.fat_g),
                "kcal": str(optimized.macros.kcal),
            })
        meals.append({
            "meal_type": meal.meal_type,
            "name": meal.meal_type.title(),
            "time": _MEAL_TIMES[meal.meal_type],
            "foods": foods,
        })
    return {"meals": meals}


def evaluate_canonical_v2(*, language: str, targets: DeliveryTargets,
                          restrictions: tuple[str, ...], medical_route: bool = False,
                          recent_plan_records: Sequence[Mapping[str, object]] | object = ()) -> CanonicalV2Evaluation:
    """Evaluate V2 and return a plan only after every production boundary passes."""
    try:
        catalog = load_production_food_catalog()
    except Exception:
        return CanonicalV2Evaluation(None, _failure(NutritionPlanCode.CATALOG_NOT_READY))

    request = _request(
        language=language,
        targets=targets,
        catalog=catalog,
        restrictions=restrictions,
        medical_route=medical_route,
        recent_plan_records=recent_plan_records,
    )
    result = build_nutrition_plan(request, catalog=catalog)
    if result.outcome is not NutritionPlanOutcome.SUCCESS:
        return CanonicalV2Evaluation(None, result)
    try:
        plan = nutrition_plan.build_plan(
            _payload_from_result(result, catalog, language),
            targets,
            restrictions=restrictions,
            provenance={
                "generator": "nutrition_engine_v2",
                "catalog_version": result.catalog_version,
                "service_version": result.service_version,
                "deterministic_output_hash": result.deterministic_output_hash or "",
            },
            language="en" if str(language).lower() == "en" else "bg",
        )
    except Exception:
        return CanonicalV2Evaluation(None, _failure(
            NutritionPlanCode.INTERNAL_FAIL_CLOSED,
            catalog_version=result.catalog_version,
        ))
    return CanonicalV2Evaluation(plan, result)
