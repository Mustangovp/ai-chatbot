"""Phase 2 catalog quality gates for the isolated Nutrition Engine V2 library."""
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
from nutrition_engine.catalog import project_user_day


CATALOG_PATH = Path(__file__).parents[1] / "nutrition_engine" / "data" / "food_catalog_v1.json"
VERSION = "development-v2-source-backed"
GOVERNANCE = CatalogGovernance(True, False, Decimal("15"))


def _records():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["foods"]


@pytest.fixture
def catalog():
    return load_catalog_file(CATALOG_PATH, GOVERNANCE)


def _policy(**changes):
    values = dict(
        maximum_foods_per_meal=3,
        maximum_portion_multiplier_from_default=Decimal("2"),
        category_portion_overrides=(
            ("protein", Decimal("200"), Decimal("300"), Decimal("50")),
            ("carbohydrate", Decimal("100"), Decimal("200"), Decimal("50")),
            ("fat", Decimal("5"), Decimal("5"), Decimal("5")),
        ),
        max_search_nodes=50_000,
    )
    values.update(changes)
    return PracticalityPolicy(**values)


def _selection():
    return (
        MealSelection("breakfast", ("dev_egg_whites", "dev_oats_dry")),
        MealSelection("lunch", ("dev_chicken_breast_cooked", "dev_rice_cooked", "dev_olive_oil")),
        MealSelection("dinner", ("dev_chicken_breast_cooked", "dev_rice_cooked", "dev_olive_oil")),
    )


def _result(catalog):
    return optimize(catalog, NutritionTargets(Decimal("1914"), Decimal("0.05"), Decimal("198")),
                    DietConstraints(), _selection(), _policy())


def test_source_backed_records_have_explicit_reviewable_provenance(catalog):
    assert len(catalog.foods) == 45
    assert {food.review_status for food in catalog.foods} == {"NUTRIENTS_REVIEWED"}
    assert all(food.source_name and food.source_record_id and food.source_version and food.data_basis
               for food in catalog.foods)
    assert all("TEST_POLICY_ONLY" in food.reviewer_note for food in catalog.foods)
    direct_ids = [food.source_record_id for food in catalog.foods if "+" not in food.source_record_id]
    assert len(direct_ids) == len(set(direct_ids))


def test_preparation_locale_and_raw_cooked_identity_are_explicit(catalog):
    rice = catalog.by_id("dev_rice_cooked")
    chicken = catalog.by_id("dev_chicken_breast_cooked")
    assert rice.preparation_state.startswith("cooked")
    assert chicken.preparation_state.startswith("baked")
    assert rice.food_id != "dev_rice_raw"
    assert all(food.display_name_bg and food.display_name_en for food in catalog.foods)
    assert all(food.preparation_state not in {"", "unknown", "ambiguous"} for food in catalog.foods)
    records = _records()
    raw_chicken = deepcopy(records[0])
    raw_chicken.update({
        "food_id": "test_chicken_breast_raw",
        "preparation_state": "raw",
        "source_record_id": "test-raw-chicken-source",
    })
    paired = load_catalog_records(VERSION, records + [raw_chicken], GOVERNANCE)
    assert paired.by_id("dev_chicken_breast_cooked").food_id != paired.by_id("test_chicken_breast_raw").food_id


def test_catalog_rejects_duplicate_direct_source_ids_and_unsupported_units():
    records = _records()
    records[1]["source_record_id"] = records[0]["source_record_id"]
    with pytest.raises(ValueError, match="duplicate source record ID"):
        load_catalog_records(VERSION, records, GOVERNANCE)

    records = _records()
    records[0]["allowed_units"] = ["g", "ml"]
    with pytest.raises(ValueError, match="ml is restricted"):
        load_catalog_records(VERSION, records, GOVERNANCE)

    records = _records()
    records[0]["category"] = "liquid"
    records[0]["allowed_units"] = ["g", "ml"]
    assert load_catalog_records(VERSION, records, GOVERNANCE).by_id("dev_chicken_breast_cooked").allowed_units == ("g", "ml")


def test_piece_conversion_is_deterministic_and_grams_per_piece_is_restricted(catalog):
    egg = catalog.by_id("dev_whole_egg_boiled")
    assert egg.grams_per_piece == Decimal("50")
    assert egg.default_unit == "pcs"
    records = _records()
    records[0]["grams_per_piece"] = "50"
    with pytest.raises(ValueError, match="only valid for piece"):
        load_catalog_records(VERSION, records, GOVERNANCE)
    egg_result = optimize(
        catalog, NutritionTargets(Decimal("600"), Decimal("1")), DietConstraints(),
        (MealSelection("breakfast", ("dev_whole_egg_boiled",)),
         MealSelection("lunch", ("dev_whole_egg_boiled",)),
         MealSelection("dinner", ("dev_whole_egg_boiled",))),
        _policy(),
    )
    assert egg_result.feasible
    egg_item = egg_result.day.meals[0].foods[0]
    assert egg_item.display_unit == "pcs"
    assert egg_item.quantity * egg.grams_per_piece == egg_item.grams


def test_kcal_tolerance_rejects_material_deviation_without_rewriting_source_value(catalog):
    chicken = catalog.by_id("dev_chicken_breast_cooked")
    assert chicken.kcal_per_100g == Decimal("161")
    records = _records()
    records[0]["kcal_per_100g"] = "999"
    with pytest.raises(ValueError, match="kcal is inconsistent"):
        load_catalog_records(VERSION, records, GOVERNANCE)


def test_production_ready_mode_rejects_pending_portion_governance():
    with pytest.raises(ValueError, match="unreviewed records"):
        load_catalog_file(CATALOG_PATH, CatalogGovernance(False, True, Decimal("15")))
    with pytest.raises(ValueError, match="pending records"):
        load_catalog_file(CATALOG_PATH, CatalogGovernance(False, False, Decimal("15")))


def test_projection_is_localized_and_never_leaks_internal_catalog_metadata(catalog):
    result = _result(catalog)
    assert result.feasible
    projection = project_user_day(catalog, result.day, "bg")
    serialized = json.dumps(projection, default=str, ensure_ascii=False)
    assert "Пилешки гърди" in serialized
    assert "food_id" not in serialized
    assert "source_record_id" not in serialized
    assert "catalog_version" not in serialized
    assert "review_status" not in serialized
    assert "objective" not in serialized
    assert "search" not in serialized


def test_practicality_bounds_increment_and_exclusions_remain_authoritative(catalog):
    result = _result(catalog)
    assert result.feasible
    for meal in result.day.meals:
        assert meal.foods
        assert len(meal.foods) <= 3
        for item in meal.foods:
            food = catalog.by_id(item.food_id)
            lower, upper, step = next((low, high, increment) for category, low, high, increment
                                      in _policy().category_portion_overrides if category == food.category)
            assert lower <= item.grams <= upper
            assert (item.grams - lower) % step == 0
    excluded = optimize(catalog, NutritionTargets(Decimal("1914"), Decimal("0.05"), Decimal("198")),
                         DietConstraints(excluded_food_ids=frozenset({
                             "dev_egg_whites", "dev_oats_dry", "dev_chicken_breast_cooked",
                             "dev_rice_cooked", "dev_olive_oil",
                         })),
                         _selection(), _policy())
    assert excluded.code is FeasibilityCode.EXCLUSIONS_REMOVE_ALL_PROTEIN_SOURCES


def test_duplicate_food_ids_are_rejected_unless_caller_policy_explicitly_allows_them(catalog):
    duplicate = (
        MealSelection("breakfast", ("dev_egg_whites",)),
        MealSelection("lunch", ("dev_chicken_breast_cooked", "dev_rice_cooked", "dev_rice_cooked")),
        MealSelection("dinner", ("dev_chicken_breast_cooked",)),
    )
    targets = NutritionTargets(Decimal("1500"), Decimal("0.5"))
    blocked = optimize(catalog, targets, DietConstraints(), duplicate, _policy())
    assert blocked.code is FeasibilityCode.MEAL_STRUCTURE_INFEASIBLE
    allowed = optimize(catalog, targets, DietConstraints(), duplicate,
                       _policy(allow_duplicate_food_ids_per_meal=True))
    assert allowed.code in {FeasibilityCode.FEASIBLE, FeasibilityCode.CALORIE_TARGET_UNREACHABLE,
                            FeasibilityCode.PORTION_BOUNDS_INFEASIBLE}


def test_99kg_technical_case_is_catalog_derived_not_nutritional_approval(catalog):
    result = _result(catalog)
    assert result.feasible
    assert result.day.daily_totals.protein_g >= Decimal("198")
    assert abs(result.day.daily_totals.kcal - Decimal("1914")) <= Decimal("95.70")
    used = {item.food_id for meal in result.day.meals for item in meal.foods}
    assert used <= {food.food_id for food in catalog.foods}
    assert any(item.grams in {Decimal("200"), Decimal("300")} for meal in result.day.meals for item in meal.foods)


def test_library_remains_isolated_from_runtime_network_database_and_llm_imports():
    source = "\n".join(path.read_text(encoding="utf-8")
                       for path in (Path(__file__).parents[1] / "nutrition_engine").glob("*.py"))
    forbidden = ("import app", "import db", "requests.", "openai", "sqlalchemy", "socket.", "flask")
    assert all(token not in source for token in forbidden)
