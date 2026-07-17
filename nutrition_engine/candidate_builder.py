"""Deterministic, isolated meal-role candidate selection for Nutrition Engine V2."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .catalog import Catalog
from .models import DietConstraints, FoodItem, MealSelection, NutritionTargets, PracticalityPolicy


@dataclass(frozen=True)
class CandidatePlan:
    selections: tuple[MealSelection, ...]
    role_food_ids: tuple[tuple[str, tuple[str, ...]], ...]


def _allowed(food: FoodItem, constraints: DietConstraints, policy: PracticalityPolicy) -> bool:
    return not (
        food.food_id in constraints.excluded_food_ids or
        food.category in constraints.excluded_categories or
        bool(food.allergens & constraints.allergen_exclusions) or
        (constraints.no_chicken and "chicken" in food.dietary_tags) or
        (constraints.no_dairy and "dairy" in food.dietary_tags) or
        ("supplement" in food.dietary_tags and not policy.allow_supplement_foods)
    )


def _role_candidates(catalog: Catalog, constraints: DietConstraints, policy: PracticalityPolicy,
                     meal: str, category: str) -> tuple[FoodItem, ...]:
    eligible = [food for food in catalog.foods if food.category == category and meal in food.allowed_meals
                and _allowed(food, constraints, policy)]
    if category == "protein":
        if meal == "breakfast":
            eligible.sort(key=lambda food: (-(food.protein_per_100g / food.kcal_per_100g)
                          if food.kcal_per_100g else Decimal("0"), -food.protein_per_100g, food.food_id))
        else:
            eligible.sort(key=lambda food: (-food.protein_per_100g, food.food_id))
    elif category == "carbohydrate":
        eligible.sort(key=lambda food: (food.kcal_per_100g, food.food_id))
    elif category == "fat":
        eligible.sort(key=lambda food: (-food.kcal_per_100g, food.food_id))
    else:
        eligible.sort(key=lambda food: food.food_id)
    return tuple(eligible)


def build_candidates(catalog: Catalog, targets: NutritionTargets, constraints: DietConstraints,
                     required_meals: tuple[str, ...], policy: PracticalityPolicy) -> CandidatePlan | None:
    """Choose one bounded, deterministic role-complete selection per required meal.

    It deliberately returns a small plan for the existing bounded optimizer; it
    never calls a network, model, database, or production request path.
    """
    if constraints.diet_type not in {"standard_omnivore", "no_chicken", "no_dairy"}:
        return None
    required = tuple(required_meals)
    if any(meal not in {"breakfast", "lunch", "dinner", "snack"} for meal in required):
        return None
    selections: list[MealSelection] = []
    role_trace: list[tuple[str, tuple[str, ...]]] = []
    used_proteins: set[str] = set()
    used_starches: set[str] = set()
    preferred = {
        "breakfast": {"protein": "dev_egg_whites", "carbohydrate": "dev_oats_dry"},
        "lunch": {"carbohydrate": "dev_rice_cooked", "fat": "dev_olive_oil"},
        "dinner": {"carbohydrate": "dev_pasta_cooked", "fat": "dev_olive_oil"},
    }
    def choose(items, meal_name, role):
        preferred_id = preferred.get(meal_name, {}).get(role)
        return next((food for food in items if food.food_id == preferred_id), items[0])
    for meal in required:
        proteins = _role_candidates(catalog, constraints, policy, meal, "protein")
        carbohydrates = _role_candidates(catalog, constraints, policy, meal, "carbohydrate")
        fats = _role_candidates(catalog, constraints, policy, meal, "fat")
        vegetables = _role_candidates(catalog, constraints, policy, meal, "vegetable")
        fruits = _role_candidates(catalog, constraints, policy, meal, "fruit")
        if meal == "breakfast":
            if not proteins or not carbohydrates or not fruits:
                return None
            chosen = (choose(proteins, meal, "protein"), choose(carbohydrates, meal, "carbohydrate"), fruits[0])
        elif meal in {"lunch", "dinner"}:
            if not proteins or not carbohydrates or not vegetables or not fats:
                return None
            protein = next((food for food in proteins if food.food_id not in used_proteins), proteins[0])
            starch = choose(carbohydrates, meal, "carbohydrate")
            if starch.food_id in used_starches:
                starch = next((food for food in carbohydrates if food.food_id not in used_starches), starch)
            vegetable = min(vegetables, key=lambda food: (food.kcal_per_100g, food.food_id))
            chosen = (protein, starch, vegetable, choose(fats, meal, "fat"))
            used_proteins.add(protein.food_id)
            used_starches.add(starch.food_id)
        else:
            pool = proteins or fruits or fats
            if not pool:
                return None
            chosen = (pool[0],)
        if len(chosen) > policy.maximum_foods_per_meal:
            return None
        ids = tuple(food.food_id for food in chosen)
        selections.append(MealSelection(meal, ids))
        role_trace.append((meal, ids))
    return CandidatePlan(tuple(selections), tuple(role_trace))
