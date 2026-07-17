"""Deterministic meal selector and plan assembler for the isolated engine.

The selector is a faithful projection layer. It takes an optimizer result and
re-expresses it as canonical, immutable ``MealDay -> Meal -> Food`` objects with
BG/EN food labels, template structure checks, and soft practicality penalties.

It never invents foods, never changes a quantity, macro, or calorie, and never
alters the optimizer totals. Every number it emits is copied verbatim from the
optimizer output; the selector only *organizes and annotates*.

Phase 4 scope and limitations (development-only, not production-ready):
  * This layer assembles and labels an already-optimized result. It does not
    replace the Phase 3 candidate builder and never autonomously re-selects
    foods or re-optimizes.
  * ``substitutions`` is metadata only: it names approved swaps but does not
    mutate an optimized plan (applying a swap would require re-running the
    optimizer, which is out of scope here).
  * ``rotation`` rotates over approved meal-library candidates, not user
    history; there is no persistence and no historical meal rotation yet.
  * Meal-library default portions are isolated development values, and no meal
    definition is production-approved.
  * No production runtime consumes this code, and none may until a later phase.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .catalog import Catalog
from .feasibility import FeasibilityResult
from .meal_library import LibraryMeal, library_meals_for
from .meal_templates import template_violations
from .models import Nutrients, OptimizedNutritionDay
from . import substitutions


@dataclass(frozen=True)
class Food:
    """One canonical food line, copied verbatim from the optimizer."""

    food_id: str
    display_name_bg: str
    display_name_en: str
    category: str
    quantity: Decimal
    display_unit: str
    grams: Decimal
    macros: Nutrients

    @property
    def kcal(self) -> Decimal:
        return self.macros.kcal


@dataclass(frozen=True)
class Meal:
    """One canonical meal: template-checked, penalty-annotated, numbers intact."""

    meal_type: str
    foods: tuple[Food, ...]
    macros: Nutrients
    matched_library_meal_id: str | None
    template_violations: tuple[str, ...]
    soft_penalties: tuple[str, ...]


@dataclass(frozen=True)
class MealDay:
    """A full day of canonical meals with the optimizer's totals preserved."""

    meals: tuple[Meal, ...]
    daily_macros: Nutrients
    catalog_version: str
    soft_penalties: tuple[str, ...]


def _match_library_meal(meal_type: str, food_ids: frozenset[str]) -> str | None:
    """Deterministically match a meal to a library entry by exact food set."""
    for candidate in library_meals_for(meal_type):
        if frozenset(candidate.food_ids) == food_ids:
            return candidate.meal_id
    return None


def _practicality_penalties(catalog: Catalog, day: OptimizedNutritionDay) -> tuple[str, ...]:
    """Soft penalties only. Never mutates the plan or its totals.

    Flags a repeated main protein or starch across lunch and dinner *only when
    an approved substitute exists* — i.e. when the repetition was avoidable.
    """
    meals = {meal.meal_type: meal for meal in day.meals}
    lunch, dinner = meals.get("lunch"), meals.get("dinner")
    penalties: list[str] = []
    if lunch and dinner:
        def by_category(meal, category):
            return {item.food_id for item in meal.foods
                    if catalog.by_id(item.food_id) and catalog.by_id(item.food_id).category == category}

        for category, label in (("protein", "repeated_main_protein"), ("carbohydrate", "repeated_starch")):
            shared = by_category(lunch, category) & by_category(dinner, category)
            for food_id in shared:
                if substitutions.approved_substitutes(food_id):
                    penalties.append(f"{label}:{food_id}")
    return tuple(sorted(set(penalties)))


def assemble_meal_day(catalog: Catalog, result: FeasibilityResult) -> MealDay:
    """Project a feasible optimizer result into canonical meal objects.

    Raises ValueError on an infeasible result: the selector never fabricates a
    plan. The returned day's totals equal the optimizer's totals exactly.
    """
    if not result.feasible or result.day is None:
        raise ValueError("selector requires a feasible optimizer result")
    day = result.day
    meals: list[Meal] = []
    for optimized in day.meals:
        foods: list[Food] = []
        categories: list[str] = []
        for item in optimized.foods:
            food = catalog.by_id(item.food_id)
            if food is None:
                raise ValueError(f"optimizer referenced unknown food: {item.food_id}")
            categories.append(food.category)
            foods.append(Food(
                food_id=item.food_id,
                display_name_bg=food.display_name_bg,
                display_name_en=food.display_name_en,
                category=food.category,
                quantity=item.quantity,
                display_unit=item.display_unit,
                grams=item.grams,
                macros=item.nutrients,
            ))
        meals.append(Meal(
            meal_type=optimized.meal_type,
            foods=tuple(foods),
            macros=optimized.totals,
            matched_library_meal_id=_match_library_meal(
                optimized.meal_type, frozenset(f.food_id for f in foods)),
            template_violations=template_violations(optimized.meal_type, categories),
            soft_penalties=(),
        ))
    day_penalties = _practicality_penalties(catalog, day)
    assembled = MealDay(
        meals=tuple(meals),
        daily_macros=day.daily_totals,
        catalog_version=day.catalog_version,
        soft_penalties=day_penalties,
    )
    _assert_totals_preserved(day, assembled)
    return assembled


def _sum_nutrients(items) -> Nutrients:
    total = Nutrients.zero()
    for nutrients in items:
        total = total.plus(nutrients)
    return total


def _assert_totals_preserved(day: OptimizedNutritionDay, assembled: MealDay) -> None:
    """Invariant guard: assembly copies totals, it never recomputes or shifts them."""
    if assembled.daily_macros != day.daily_totals:
        raise AssertionError("selector altered the daily totals")
    for optimized, projected in zip(day.meals, assembled.meals):
        if projected.macros != optimized.totals:
            raise AssertionError("selector altered a meal total")
        derived = _sum_nutrients(food.macros for food in projected.foods)
        if derived != optimized.totals:
            raise AssertionError("projected foods do not reconcile with the optimizer meal total")
