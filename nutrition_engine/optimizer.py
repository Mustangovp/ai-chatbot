"""Small-catalog deterministic bounded integer optimizer for Phase 1 only."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from time import monotonic
from typing import Callable

from .catalog import Catalog
from .feasibility import FeasibilityCode, FeasibilityResult
from .models import (DietConstraints, FoodItem, MealSelection, Nutrients, NutritionTargets,
                     OptimizedFood, OptimizedMeal, OptimizedNutritionDay, PracticalityPolicy)


@dataclass(frozen=True)
class _Candidate:
    meal_type: str
    food: FoodItem
    grams: Decimal
    nutrients: Nutrients
    is_extreme: bool


def _nutrients(food: FoodItem, grams: Decimal) -> Nutrients:
    factor = grams / Decimal("100")
    return Nutrients(food.protein_per_100g * factor, food.carbs_per_100g * factor,
                     food.fat_per_100g * factor, food.kcal_per_100g * factor)


def _allowed(food: FoodItem, constraints: DietConstraints, policy: PracticalityPolicy) -> bool:
    if food.food_id in constraints.excluded_food_ids or food.category in constraints.excluded_categories:
        return False
    if food.allergens & constraints.allergen_exclusions:
        return False
    if constraints.no_chicken and "chicken" in food.dietary_tags:
        return False
    if constraints.no_dairy and "dairy" in food.dietary_tags:
        return False
    if "supplement" in food.dietary_tags and not policy.allow_supplement_foods:
        return False
    return True


def _bounds(food: FoodItem, policy: PracticalityPolicy) -> tuple[Decimal, Decimal, Decimal]:
    lower, upper, step = food.minimum_portion, food.maximum_portion, food.portion_increment
    for category, configured_min, configured_max, configured_step in policy.category_portion_overrides:
        if category == food.category:
            # Caller policy can narrow a catalog range; it can never expand one.
            lower, upper, step = max(lower, configured_min), min(upper, configured_max), configured_step
    if policy.maximum_portion_multiplier_from_default is not None:
        upper = min(upper, food.default_portion * policy.maximum_portion_multiplier_from_default)
    return lower, upper, step


def _portions(food: FoodItem, policy: PracticalityPolicy) -> tuple[Decimal, ...]:
    lower, upper, step = _bounds(food, policy)
    if lower <= 0 or upper < lower or step <= 0:
        return ()
    count = int((upper - lower) // step)
    return tuple(lower + step * index for index in range(count + 1))


def _check_targets(totals: Nutrients, targets: NutritionTargets) -> FeasibilityCode | None:
    if abs(totals.kcal - targets.calories_target) > targets.calories_target * targets.calories_tolerance:
        return FeasibilityCode.CALORIE_TARGET_UNREACHABLE
    checks = ((totals.protein_g, targets.protein_min_g, targets.protein_max_g, FeasibilityCode.PROTEIN_MINIMUM_UNREACHABLE, FeasibilityCode.PROTEIN_CAP_CONFLICT),
              (totals.carbs_g, targets.carbs_min_g, targets.carbs_max_g, FeasibilityCode.PORTION_BOUNDS_INFEASIBLE, FeasibilityCode.PORTION_BOUNDS_INFEASIBLE),
              (totals.fat_g, targets.fat_min_g, targets.fat_max_g, FeasibilityCode.PORTION_BOUNDS_INFEASIBLE, FeasibilityCode.PORTION_BOUNDS_INFEASIBLE))
    for value, minimum, maximum, below, above in checks:
        if minimum is not None and value < minimum:
            return below
        if maximum is not None and value > maximum:
            return above
    return None


def _score(candidates: tuple[_Candidate, ...], totals: Nutrients, targets: NutritionTargets,
           meal_totals: dict[str, Nutrients], policy: PracticalityPolicy) -> tuple:
    protein_excess = max(Decimal("0"), totals.protein_g - targets.protein_min_g) if targets.protein_min_g is not None else Decimal("0")
    default_deviation = sum(abs(candidate.grams - candidate.food.default_portion) for candidate in candidates)
    extreme_count = sum(candidate.is_extreme for candidate in candidates)
    distribution_penalty = Decimal("0")
    for meal, low, high in policy.meal_calorie_share_ranges:
        share = meal_totals.get(meal, Nutrients.zero()).kcal / totals.kcal if totals.kcal else Decimal("0")
        distribution_penalty += max(Decimal("0"), low - share, share - high)
    tie = tuple(sorted((candidate.food.food_id, candidate.grams) for candidate in candidates))
    return (abs(totals.kcal - targets.calories_target), protein_excess, default_deviation,
            extreme_count, distribution_penalty, tie)


def optimize(catalog: Catalog, targets: NutritionTargets, constraints: DietConstraints,
             selections: tuple[MealSelection, ...], policy: PracticalityPolicy,
             *, deadline_monotonic: float | None = None,
             clock: Callable[[], float] = monotonic) -> FeasibilityResult:
    """Solve only caller-selected food IDs; performs no I/O, LLM, DB, or network work."""
    if constraints.allowed_catalog_version and constraints.allowed_catalog_version != catalog.version:
        return FeasibilityResult(FeasibilityCode.CATALOG_VERSION_MISMATCH)
    if constraints.diet_type not in {"standard_omnivore", "no_chicken", "no_dairy"}:
        return FeasibilityResult(FeasibilityCode.UNSUPPORTED_DIET)
    meal_types = tuple(selection.meal_type for selection in selections)
    if any(meal not in {"breakfast", "lunch", "dinner", "snack"} for meal in meal_types) or not all(meal in meal_types for meal in ("breakfast", "lunch", "dinner")):
        return FeasibilityResult(FeasibilityCode.MEAL_STRUCTURE_INFEASIBLE)
    if len(set(meal_types)) != len(meal_types):
        return FeasibilityResult(FeasibilityCode.MEAL_STRUCTURE_INFEASIBLE)

    candidates: list[tuple[str, FoodItem, tuple[Decimal, ...]]] = []
    selected_protein_source = False
    for selection in selections:
        if (len(selection.ordered_food_ids) > policy.maximum_foods_per_meal or not selection.ordered_food_ids or
                (not policy.allow_duplicate_food_ids_per_meal and
                 len(set(selection.ordered_food_ids)) != len(selection.ordered_food_ids))):
            return FeasibilityResult(FeasibilityCode.MEAL_STRUCTURE_INFEASIBLE)
        for food_id in selection.ordered_food_ids:
            food = catalog.by_id(food_id)
            if food is None or selection.meal_type not in food.allowed_meals or not _allowed(food, constraints, policy):
                continue
            selected_protein_source = selected_protein_source or food.protein_per_100g > 0
            portions = _portions(food, policy)
            if not portions:
                return FeasibilityResult(FeasibilityCode.PORTION_BOUNDS_INFEASIBLE)
            candidates.append((selection.meal_type, food, portions))
    expected_count = sum(len(selection.ordered_food_ids) for selection in selections)
    if len(candidates) != expected_count:
        return FeasibilityResult(FeasibilityCode.EXCLUSIONS_REMOVE_ALL_PROTEIN_SOURCES if not selected_protein_source else FeasibilityCode.MEAL_STRUCTURE_INFEASIBLE)
    if targets.protein_min_g is not None and not selected_protein_source:
        return FeasibilityResult(FeasibilityCode.EXCLUSIONS_REMOVE_ALL_PROTEIN_SOURCES)

    supplement_count = sum("supplement" in food.dietary_tags for _, food, _ in candidates)
    if supplement_count > policy.maximum_supplement_items:
        return FeasibilityResult(FeasibilityCode.MEAL_STRUCTURE_INFEASIBLE)
    minimums = [_nutrients(food, min(portions)) for _, food, portions in candidates]
    maximums = [_nutrients(food, max(portions)) for _, food, portions in candidates]
    remaining_min = [Nutrients.zero()] * (len(candidates) + 1)
    remaining_max = [Nutrients.zero()] * (len(candidates) + 1)
    for index in range(len(candidates) - 1, -1, -1):
        remaining_min[index] = minimums[index].plus(remaining_min[index + 1])
        remaining_max[index] = maximums[index].plus(remaining_max[index + 1])

    floor, ceiling = remaining_min[0], remaining_max[0]
    calorie_low = targets.calories_target * (Decimal("1") - targets.calories_tolerance)
    calorie_high = targets.calories_target * (Decimal("1") + targets.calories_tolerance)
    if ceiling.kcal < calorie_low or floor.kcal > calorie_high:
        return FeasibilityResult(FeasibilityCode.CALORIE_TARGET_UNREACHABLE)
    if targets.protein_min_g is not None and ceiling.protein_g < targets.protein_min_g:
        return FeasibilityResult(FeasibilityCode.PROTEIN_MINIMUM_UNREACHABLE)
    if targets.protein_max_g is not None and floor.protein_g > targets.protein_max_g:
        return FeasibilityResult(FeasibilityCode.PROTEIN_CAP_CONFLICT)

    def cannot_reach(index: int, totals: Nutrients) -> FeasibilityCode | None:
        low_kcal = targets.calories_target * (Decimal("1") - targets.calories_tolerance)
        high_kcal = targets.calories_target * (Decimal("1") + targets.calories_tolerance)
        floor, ceiling = remaining_min[index], remaining_max[index]
        if totals.kcal + ceiling.kcal < low_kcal or totals.kcal + floor.kcal > high_kcal:
            return FeasibilityCode.CALORIE_TARGET_UNREACHABLE
        checks = ((totals.protein_g, floor.protein_g, ceiling.protein_g, targets.protein_min_g, targets.protein_max_g),
                  (totals.carbs_g, floor.carbs_g, ceiling.carbs_g, targets.carbs_min_g, targets.carbs_max_g),
                  (totals.fat_g, floor.fat_g, ceiling.fat_g, targets.fat_min_g, targets.fat_max_g))
        for position, (current, minimum_value, maximum, minimum, maximum_allowed) in enumerate(checks):
            if minimum is not None and current + maximum < minimum:
                return FeasibilityCode.PROTEIN_MINIMUM_UNREACHABLE if position == 0 else FeasibilityCode.PORTION_BOUNDS_INFEASIBLE
            if maximum_allowed is not None and current + minimum_value > maximum_allowed:
                return FeasibilityCode.PROTEIN_CAP_CONFLICT if position == 0 else FeasibilityCode.PORTION_BOUNDS_INFEASIBLE
        return None

    searched = 0
    timed_out = False
    best: tuple[tuple, tuple[_Candidate, ...], Nutrients, dict[str, Nutrients]] | None = None
    last_failure: FeasibilityCode | None = None
    initial_meals = {selection.meal_type: Nutrients.zero() for selection in selections}

    def search(index: int, resolved: tuple[_Candidate, ...], totals: Nutrients,
               meal_totals: dict[str, Nutrients]) -> None:
        nonlocal searched, best, last_failure, timed_out
        if deadline_monotonic is not None and clock() >= deadline_monotonic:
            timed_out = True
            return
        pruned = cannot_reach(index, totals)
        if pruned is not None:
            last_failure = pruned
            return
        if index == len(candidates):
            searched += 1
            if searched > policy.max_search_nodes:
                return
            failure = _check_targets(totals, targets)
            if failure is not None:
                last_failure = failure
                return
            score = _score(resolved, totals, targets, meal_totals, policy)
            if best is None or score < best[0]:
                best = (score, resolved, totals, meal_totals)
            return
        meal, food, portions = candidates[index]
        lower, upper, _ = _bounds(food, policy)
        for grams in portions:
            if deadline_monotonic is not None and clock() >= deadline_monotonic:
                timed_out = True
                return
            if searched > policy.max_search_nodes:
                return
            nutrients = _nutrients(food, grams)
            next_meals = dict(meal_totals)
            next_meals[meal] = next_meals[meal].plus(nutrients)
            search(index + 1, resolved + (_Candidate(meal, food, grams, nutrients,
                                                       grams in {lower, upper}),),
                   totals.plus(nutrients), next_meals)

    search(0, (), Nutrients.zero(), initial_meals)
    if timed_out:
        return FeasibilityResult(FeasibilityCode.SHADOW_TIMEOUT)
    if searched > policy.max_search_nodes:
        return FeasibilityResult(FeasibilityCode.SEARCH_LIMIT_REACHED)
    if best is None:
        return FeasibilityResult(last_failure or FeasibilityCode.PORTION_BOUNDS_INFEASIBLE)

    _, resolved, totals, meal_totals = best
    meals = []
    for selection in selections:
        foods = tuple(OptimizedFood(
            item.food.food_id,
            item.grams / item.food.grams_per_piece if item.food.default_unit == "pcs" else item.grams,
            item.food.default_unit, item.grams, item.nutrients,
        ) for item in resolved if item.meal_type == selection.meal_type)
        meals.append(OptimizedMeal(selection.meal_type, foods, meal_totals[selection.meal_type]))
    deviations = (("calories", totals.kcal - targets.calories_target),)
    if targets.protein_min_g is not None:
        deviations += (("protein_minimum", totals.protein_g - targets.protein_min_g),)
    return FeasibilityResult(FeasibilityCode.FEASIBLE, OptimizedNutritionDay(
        tuple(meals), totals, deviations, catalog.version, FeasibilityCode.FEASIBLE.value))
