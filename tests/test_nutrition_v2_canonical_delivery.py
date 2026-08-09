from dataclasses import replace
from decimal import Decimal

import pytest

import nutrition_plan
from nutrition_engine.catalog import Catalog
from nutrition_engine.models import NutritionPlanCode, NutritionPlanOutcome
from nutrition_engine.service import build_nutrition_plan
from nutrition_engine import canonical_delivery as delivery
from nutrition_validation import NutritionTargets
from tests.test_nutrition_engine_phase5 import CATALOG


TARGETS = NutritionTargets(Decimal("1914"), Decimal("198"))


@pytest.fixture
def ready_catalog():
    return Catalog(
        CATALOG.version,
        tuple(replace(food, review_status="PRODUCTION_READY") for food in CATALOG.foods),
    )


def _service_result(catalog):
    request = delivery._request(
        language="en", targets=TARGETS, catalog=catalog,
        restrictions=(), medical_route=False,
    )
    result = build_nutrition_plan(request, catalog=catalog)
    assert result.outcome is NutritionPlanOutcome.SUCCESS
    return result


def test_current_development_catalog_cannot_become_canonical_delivery():
    evaluated = delivery.evaluate_canonical_v2(
        language="en", targets=TARGETS, restrictions=())

    assert evaluated.plan is None
    assert evaluated.result.code is NutritionPlanCode.CATALOG_NOT_READY


def test_production_ready_v2_result_becomes_validated_authoritative_plan(monkeypatch, ready_catalog):
    monkeypatch.setattr(delivery, "load_production_food_catalog", lambda: ready_catalog)

    evaluated = delivery.evaluate_canonical_v2(
        language="en", targets=TARGETS, restrictions=())

    assert evaluated.result.outcome is NutritionPlanOutcome.SUCCESS
    assert evaluated.plan is not None
    assert evaluated.plan.totals.kcal == Decimal("1914.00")
    assert all(food.catalog_id == food.food_id for meal in evaluated.plan.meals for food in meal.foods)
    assert all(ready_catalog.by_id(food.catalog_id) is not None
               for meal in evaluated.plan.meals for food in meal.foods)


def test_restrictions_and_medical_routes_are_rejected_before_delivery(monkeypatch, ready_catalog):
    monkeypatch.setattr(delivery, "load_production_food_catalog", lambda: ready_catalog)

    restricted = delivery.evaluate_canonical_v2(
        language="en", targets=TARGETS, restrictions=("peanuts",))
    medical = delivery.evaluate_canonical_v2(
        language="en", targets=TARGETS, restrictions=(), medical_route=True)

    assert restricted.plan is None
    assert restricted.result.code is NutritionPlanCode.UNSUPPORTED_PROFILE_AUTHORITY
    assert medical.plan is None
    assert medical.result.code is NutritionPlanCode.MEDICAL_ROUTING_REQUIRED


@pytest.mark.parametrize("mutation", ("unknown_food", "invalid_macro", "invalid_structure"))
def test_invalid_v2_delivery_source_fails_closed(monkeypatch, ready_catalog, mutation):
    result = _service_result(ready_catalog)
    first_meal = result.source_day.meals[0]
    first_food = first_meal.foods[0]
    if mutation == "unknown_food":
        mutated_food = replace(first_food, food_id="not-in-production-catalog")
        mutated_meal = replace(first_meal, foods=(mutated_food,) + first_meal.foods[1:])
    elif mutation == "invalid_macro":
        mutated_food = replace(first_food, macros=replace(first_food.macros, kcal=Decimal("1")))
        mutated_meal = replace(first_meal, foods=(mutated_food,) + first_meal.foods[1:])
    else:
        mutated_meal = replace(first_meal, meal_type="invalid")
    mutated_day = replace(result.source_day, meals=(mutated_meal,) + result.source_day.meals[1:])
    monkeypatch.setattr(delivery, "load_production_food_catalog", lambda: ready_catalog)
    monkeypatch.setattr(delivery, "build_nutrition_plan",
                        lambda *_args, **_kwargs: replace(result, source_day=mutated_day))

    evaluated = delivery.evaluate_canonical_v2(
        language="en", targets=TARGETS, restrictions=())

    assert evaluated.plan is None
    assert evaluated.result.outcome is NutritionPlanOutcome.INTERNAL_FAIL_CLOSED
