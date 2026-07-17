"""Deterministic performance and arithmetic guard for the isolated development optimizer."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from statistics import quantiles
from time import perf_counter

from nutrition_engine import (
    CatalogGovernance, DietConstraints, MealSelection, NutritionTargets,
    PracticalityPolicy, load_catalog_file, optimize,
)
from nutrition_engine.catalog import project_user_day


CATALOG = load_catalog_file(
    Path(__file__).parents[1] / "nutrition_engine" / "data" / "food_catalog_v1.json",
    CatalogGovernance(True, False, Decimal("15")),
)
POLICY = PracticalityPolicy(
    maximum_foods_per_meal=3,
    category_portion_overrides=(
        ("protein", Decimal("200"), Decimal("250"), Decimal("50")),
        ("carbohydrate", Decimal("100"), Decimal("150"), Decimal("50")),
        ("fat", Decimal("5"), Decimal("5"), Decimal("5")),
    ),
    max_search_nodes=10_000,
)
SELECTION = (
    MealSelection("breakfast", ("dev_egg_whites", "dev_oats_dry")),
    MealSelection("lunch", ("dev_chicken_breast_cooked", "dev_rice_cooked", "dev_olive_oil")),
    MealSelection("dinner", ("dev_chicken_breast_cooked", "dev_rice_cooked", "dev_olive_oil")),
)


def _scenarios():
    scenarios = []
    for weight in range(60, 121):
        for shape, multiplier in (("fat_loss", Decimal("24")), ("maintenance", Decimal("27"))):
            if len(scenarios) == 100:
                return tuple(scenarios)
            target = Decimal(weight) * multiplier
            constraints = DietConstraints(
                no_chicken=weight % 13 == 0,
                no_dairy=weight % 17 == 0,
            )
            scenarios.append((shape, NutritionTargets(target, Decimal("0.05"),
                                                       protein_min_g=Decimal(weight) * Decimal("1.6"),
                                                       protein_max_g=Decimal(weight) * Decimal("3") if weight % 7 == 0 else None),
                              constraints, "bg" if weight % 2 else "en"))
    return tuple(scenarios)


def test_one_hundred_scenario_matrix_is_repeatable_and_has_no_arithmetic_drift():
    scenarios = _scenarios()
    assert len(scenarios) == 100
    first = [optimize(CATALOG, targets, constraints, SELECTION, POLICY)
             for _, targets, constraints, _ in scenarios]
    second = [optimize(CATALOG, targets, constraints, SELECTION, POLICY)
              for _, targets, constraints, _ in scenarios]
    assert first == second
    for (_, targets, _, language), result in zip(scenarios, first):
        if not result.feasible:
            continue
        foods = [item for meal in result.day.meals for item in meal.foods]
        assert result.day.daily_totals.kcal == sum((item.nutrients.kcal for item in foods), Decimal("0"))
        assert abs(result.day.daily_totals.kcal - targets.calories_target) <= targets.calories_target * targets.calories_tolerance
        projection = project_user_day(CATALOG, result.day, language)
        assert "food_id" not in str(projection)


def test_performance_regression_guard_for_one_hundred_deterministic_scenarios():
    scenarios = _scenarios()
    optimize(CATALOG, scenarios[0][1], scenarios[0][2], SELECTION, POLICY)  # warm-up is excluded
    samples = []
    for _, targets, constraints, _ in scenarios:
        started = perf_counter()
        optimize(CATALOG, targets, constraints, SELECTION, POLICY)
        samples.append(perf_counter() - started)
    p95 = quantiles(samples, n=100, method="inclusive")[94]
    # Local target is <250 ms. CI retains a generous 2 s ceiling to catch major
    # accidental complexity without treating transient shared-runner load as a regression.
    assert p95 < 2.0, f"optimizer P95 {p95 * 1000:.2f} ms exceeded CI guard"
