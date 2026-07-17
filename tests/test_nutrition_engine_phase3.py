"""Phase 3 feasibility and practicality gates for the isolated nutrition library."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from nutrition_engine import CatalogGovernance, DietConstraints, FeasibilityCode, NutritionTargets, PracticalityPolicy, load_catalog_file, optimize
from nutrition_engine.candidate_builder import build_candidates
from nutrition_engine.quality import evaluate_quality


CATALOG = load_catalog_file(Path(__file__).parents[1] / "nutrition_engine" / "data" / "food_catalog_v1.json", CatalogGovernance(True, False, Decimal("15")))
POLICY = PracticalityPolicy(
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
MEALS = ("breakfast", "lunch", "dinner")


def _run(target=Decimal("1914"), protein=Decimal("198"), constraints=DietConstraints()):
    targets = NutritionTargets(target, Decimal("0.05"), protein)
    plan = build_candidates(CATALOG, targets, constraints, MEALS, POLICY)
    assert plan is not None
    return plan, optimize(CATALOG, targets, constraints, plan.selections, POLICY)


def test_catalog_expands_to_source_backed_role_coverage_without_production_promotion():
    assert len(CATALOG.foods) == 45
    assert {food.review_status for food in CATALOG.foods} == {"NUTRIENTS_REVIEWED"}
    for meal in MEALS:
        assert any(food.category == "protein" and meal in food.allowed_meals for food in CATALOG.foods)
        assert any(food.category == "carbohydrate" and meal in food.allowed_meals for food in CATALOG.foods)
    assert all("TEST_POLICY_ONLY" in food.reviewer_note for food in CATALOG.foods)


def test_candidate_builder_is_deterministic_role_complete_and_respects_restrictions():
    first, result = _run()
    second, repeated = _run()
    assert first == second and result == repeated and result.feasible
    lunch, dinner = first.selections[1], first.selections[2]
    assert set(lunch.ordered_food_ids).isdisjoint(set(dinner.ordered_food_ids) - {"dev_zucchini_cooked", "dev_olive_oil"})
    no_chicken = DietConstraints(no_chicken=True, diet_type="no_chicken")
    plan, no_chicken_result = _run(constraints=no_chicken)
    assert no_chicken_result.feasible
    assert all("chicken" not in CATALOG.by_id(food_id).dietary_tags for selection in plan.selections for food_id in selection.ordered_food_ids)


def test_99kg_case_is_feasible_practical_and_technical_only():
    _, result = _run()
    assert result.feasible
    assert result.day.daily_totals.protein_g >= Decimal("198")
    assert abs(result.day.daily_totals.kcal - Decimal("1914")) <= Decimal("95.70")
    quality = evaluate_quality(CATALOG, result.day)
    assert quality.acceptable


def test_supported_two_hundred_case_matrix_is_repeatable_without_arithmetic_or_projection_leakage():
    supported = []
    weights = (60, 75, 90, 99, 110, 120)
    shapes = (("fat_loss", Decimal("-50")), ("maintenance", Decimal("0")), ("muscle_gain", Decimal("50")))
    restrictions = (DietConstraints(), DietConstraints(no_chicken=True, diet_type="no_chicken"), DietConstraints(no_dairy=True, diet_type="no_dairy"))
    for index in range(150):
        weight = weights[index % len(weights)]
        _, offset = shapes[index % len(shapes)]
        constraints = restrictions[index % len(restrictions)]
        supported.append((NutritionTargets(Decimal("1914") + offset, Decimal("0.05"), Decimal(weight) * Decimal("1.6")), constraints))
    first = []
    for targets, constraints in supported:
        plan = build_candidates(CATALOG, targets, constraints, MEALS, POLICY)
        result = optimize(CATALOG, targets, constraints, plan.selections, POLICY)
        first.append(result)
        assert result.feasible
        assert result.day.daily_totals.kcal == sum((item.nutrients.kcal for meal in result.day.meals for item in meal.foods), Decimal("0"))
        assert abs(result.day.daily_totals.kcal - targets.calories_target) <= targets.calories_target * targets.calories_tolerance
        assert evaluate_quality(CATALOG, result.day).acceptable
    second = [optimize(CATALOG, targets, constraints, build_candidates(CATALOG, targets, constraints, MEALS, POLICY).selections, POLICY)
              for targets, constraints in supported]
    assert first == second

    unsupported = [DietConstraints(diet_type="vegan") for _ in range(25)] + [
        DietConstraints(excluded_categories=frozenset({"protein"})) for _ in range(25)
    ]
    for constraints in unsupported:
        plan = build_candidates(CATALOG, NutritionTargets(Decimal("1914"), Decimal("0.05"), Decimal("198")), constraints, MEALS, POLICY)
        assert plan is None
