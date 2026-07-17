"""Isolated tests for Nutrition Engine V2 Phase 1.

The development catalog is explicitly TEST_ONLY and is never a production
nutrition authority.
"""
from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from nutrition_engine import (
    CatalogGovernance, DietConstraints, FeasibilityCode, MealSelection,
    NutritionTargets, PracticalityPolicy, load_catalog_file, load_catalog_records,
    optimize,
)
from nutrition_engine.models import localized_food_name


CATALOG_PATH = Path(__file__).parents[1] / "nutrition_engine" / "data" / "food_catalog_v1.json"
# Source-backed development data remain non-production because portion bounds
# are explicitly TEST_POLICY_ONLY; the tolerance is catalog-quality policy only.
CATALOG_VERSION = "development-v2-source-backed"
GOVERNANCE = CatalogGovernance(True, False, Decimal("15"))


@pytest.fixture
def catalog():
    return load_catalog_file(CATALOG_PATH, GOVERNANCE)


def _records():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["foods"]


def _policy(**changes):
    values = dict(
        maximum_foods_per_meal=3,
        maximum_portion_multiplier_from_default=Decimal("2"),
        category_portion_overrides=(
            # TEST_ONLY search envelope, deliberately supplied by the caller.
            ("protein", Decimal("200"), Decimal("300"), Decimal("50")),
            ("carbohydrate", Decimal("100"), Decimal("200"), Decimal("50")),
            ("fat", Decimal("5"), Decimal("5"), Decimal("5")),
        ),
        max_search_nodes=50_000,
    )
    values.update(changes)
    return PracticalityPolicy(**values)


def _targets(**changes):
    values = dict(calories_target=Decimal("1930"), calories_tolerance=Decimal("0.05"),
                  protein_min_g=Decimal("198"))
    values.update(changes)
    return NutritionTargets(**values)


def _selection(chicken="dev_chicken_breast_cooked"):
    return (
        MealSelection("breakfast", ("dev_egg_whites", "dev_oats_dry")),
        MealSelection("lunch", (chicken, "dev_rice_cooked", "dev_olive_oil")),
        MealSelection("dinner", (chicken, "dev_rice_cooked", "dev_olive_oil")),
    )


def test_catalog_rejects_duplicate_food_ids():
    records = _records()
    records.append(deepcopy(records[0]))
    with pytest.raises(ValueError, match="duplicate food ID"):
        load_catalog_records(CATALOG_VERSION, records, GOVERNANCE)


@pytest.mark.parametrize("field, value, message", [
    ("source_name", "", "missing provenance"),
    ("display_name_bg", "", "BG and EN"),
    ("protein_per_100g", "-1", "negative nutrient"),
    ("maximum_portion", "0", "invalid min/max"),
    ("portion_increment", "0", "invalid min/max"),
])
def test_catalog_governance_rejects_invalid_records(field, value, message):
    records = _records()
    records[0][field] = value
    with pytest.raises(ValueError, match=message):
        load_catalog_records(CATALOG_VERSION, records, GOVERNANCE)


def test_catalog_rejects_version_mismatch_and_pending_production_records():
    records = _records()
    records[0]["catalog_version"] = "wrong"
    with pytest.raises(ValueError, match="catalog-version mismatch"):
        load_catalog_records(CATALOG_VERSION, records, GOVERNANCE)
    with pytest.raises(ValueError, match="unreviewed records"):
        load_catalog_records(CATALOG_VERSION, _records(), CatalogGovernance(False, True, Decimal("15")))


def test_raw_and_cooked_records_remain_distinct_and_names_are_localized(catalog):
    rice = catalog.by_id("dev_rice_cooked")
    oats = catalog.by_id("dev_oats_dry")
    assert rice.preparation_state == "cooked_not_further_specified"
    assert oats.preparation_state == "raw_dry"
    assert localized_food_name(rice, "bg") == "Ориз, сварен"
    assert localized_food_name(rice, "en") == "Cooked rice"
    assert "dev_rice_cooked" not in localized_food_name(rice, "en")


def test_optimizer_is_deterministic_and_food_derived(catalog):
    result_a = optimize(catalog, _targets(), DietConstraints(), _selection(), _policy())
    result_b = optimize(catalog, _targets(), DietConstraints(), _selection(), _policy())
    assert result_a == result_b
    assert result_a.feasible
    day = result_a.day
    assert day is not None
    summed = sum((food.nutrients.kcal for meal in day.meals for food in meal.foods), Decimal("0"))
    assert day.daily_totals.kcal == summed
    assert abs(day.daily_totals.kcal - Decimal("1930")) <= Decimal("1930") * Decimal("0.05")
    assert day.daily_totals.protein_g >= Decimal("198")


def test_optional_bounds_apply_only_when_supplied(catalog):
    base = optimize(catalog, _targets(), DietConstraints(), _selection(), _policy())
    assert base.feasible
    assert base.day.daily_totals.protein_g > Decimal("198")  # no implicit protein cap exists
    capped = optimize(catalog, NutritionTargets(Decimal("1930"), Decimal("0.05"), protein_max_g=Decimal("100")),
                      DietConstraints(), _selection(), _policy())
    assert not capped.feasible
    assert capped.code is FeasibilityCode.PROTEIN_CAP_CONFLICT
    carbs_and_fat = optimize(catalog, _targets(carbs_min_g=Decimal("1"), fat_max_g=Decimal("500")),
                             DietConstraints(), _selection(), _policy())
    assert carbs_and_fat.feasible


def test_exclusions_no_chicken_and_no_dairy_are_respected(catalog):
    no_chicken = optimize(catalog, _targets(protein_min_g=Decimal("160")),
                          DietConstraints(no_chicken=True, diet_type="no_chicken"),
                          _selection("dev_lean_beef_cooked"), _policy())
    assert no_chicken.feasible
    assert all(food.food_id != "dev_chicken_breast_cooked" for meal in no_chicken.day.meals for food in meal.foods)

    no_dairy = optimize(catalog, _targets(protein_min_g=Decimal("160")),
                         DietConstraints(no_dairy=True, diet_type="no_dairy"), _selection(), _policy())
    assert no_dairy.feasible
    assert all("dairy" not in catalog.by_id(food.food_id).dietary_tags
               for meal in no_dairy.day.meals for food in meal.foods)


def test_meal_structure_quantities_and_catalog_values_are_preserved(catalog):
    before = catalog.foods
    result = optimize(catalog, _targets(), DietConstraints(), _selection(), _policy())
    assert result.feasible
    assert tuple(meal.meal_type for meal in result.day.meals) == ("breakfast", "lunch", "dinner")
    assert catalog.foods == before
    for meal in result.day.meals:
        for item in meal.foods:
            food = catalog.by_id(item.food_id)
            lower, upper, step = next((a, b, c) for category, a, b, c in _policy().category_portion_overrides if category == food.category)
            assert lower <= item.grams <= upper
            assert (item.grams - lower) % step == 0
            assert isinstance(item.nutrients.kcal, Decimal)


def test_infeasible_and_exclusion_failures_are_deterministic(catalog):
    unreachable = optimize(catalog, _targets(calories_target=Decimal("10000")), DietConstraints(), _selection(), _policy())
    assert unreachable.code is FeasibilityCode.CALORIE_TARGET_UNREACHABLE
    removed = optimize(catalog, _targets(), DietConstraints(excluded_food_ids=frozenset({
        "dev_egg_whites", "dev_oats_dry", "dev_chicken_breast_cooked", "dev_rice_cooked", "dev_olive_oil"})),
                      _selection(), _policy())
    assert removed.code is FeasibilityCode.EXCLUSIONS_REMOVE_ALL_PROTEIN_SOURCES
    unsupported = optimize(catalog, _targets(), DietConstraints(diet_type="vegan"), _selection(), _policy())
    assert unsupported.code is FeasibilityCode.UNSUPPORTED_DIET
    mismatch = optimize(catalog, _targets(), DietConstraints(allowed_catalog_version="other"), _selection(), _policy())
    assert mismatch.code is FeasibilityCode.CATALOG_VERSION_MISMATCH


def test_99kg_case_is_technical_feasibility_only(catalog):
    result = optimize(catalog,
                      NutritionTargets(Decimal("1914"), Decimal("0.05"), Decimal("198")),
                      DietConstraints(), _selection(), _policy())
    assert result.feasible, result
    assert result.day.daily_totals.protein_g >= Decimal("198")
    assert abs(result.day.daily_totals.kcal - Decimal("1914")) <= Decimal("1914") * Decimal("0.05")
    assert result.day.catalog_version == CATALOG_VERSION


def test_no_production_imports_network_or_database_calls():
    package = Path(__file__).parents[1] / "nutrition_engine"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    forbidden = ("import app", "import db", "requests.", "openai", "sqlalchemy", "socket.")
    assert all(token not in source for token in forbidden)
