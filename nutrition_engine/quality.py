"""Test-policy-only practical quality checks for isolated nutrition plans."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .catalog import Catalog
from .models import OptimizedNutritionDay


@dataclass(frozen=True)
class QualityResult:
    hard_violations: tuple[str, ...]
    soft_penalties: tuple[str, ...]

    @property
    def acceptable(self) -> bool:
        return not self.hard_violations


def evaluate_quality(catalog: Catalog, day: OptimizedNutritionDay,
                     maximum_oil_g: Decimal = Decimal("40"),
                     minimum_vegetable_g: Decimal = Decimal("75")) -> QualityResult:
    meals = {meal.meal_type: meal for meal in day.meals}
    hard, soft = [], []
    lunch, dinner = meals.get("lunch"), meals.get("dinner")
    if lunch and dinner:
        lunch_proteins = {item.food_id for item in lunch.foods if catalog.by_id(item.food_id).category == "protein"}
        dinner_proteins = {item.food_id for item in dinner.foods if catalog.by_id(item.food_id).category == "protein"}
        lunch_starches = {item.food_id for item in lunch.foods if catalog.by_id(item.food_id).category == "carbohydrate"}
        dinner_starches = {item.food_id for item in dinner.foods if catalog.by_id(item.food_id).category == "carbohydrate"}
        if lunch_proteins & dinner_proteins:
            hard.append("repeated_main_protein")
        if lunch_starches & dinner_starches:
            hard.append("repeated_starch")
    oil_g = sum((item.grams for meal in day.meals for item in meal.foods
                 if item.food_id == "dev_olive_oil"), Decimal("0"))
    if oil_g > maximum_oil_g:
        hard.append("excessive_oil")
    for meal in day.meals:
        vegetables = sum((item.grams for item in meal.foods
                          if catalog.by_id(item.food_id).category == "vegetable"), Decimal("0"))
        if meal.meal_type in {"lunch", "dinner"} and vegetables < minimum_vegetable_g:
            hard.append(f"negligible_vegetables_{meal.meal_type}")
        for item in meal.foods:
            food = catalog.by_id(item.food_id)
            if item.grams == food.maximum_portion:
                soft.append(f"maximum_portion_{food.food_id}")
    egg_white_protein = sum((item.nutrients.protein_g for meal in day.meals for item in meal.foods
                             if item.food_id == "dev_egg_whites"), Decimal("0"))
    if day.daily_totals.protein_g and egg_white_protein / day.daily_totals.protein_g > Decimal("0.5"):
        hard.append("excessive_egg_white_dependence")
    return QualityResult(tuple(sorted(set(hard))), tuple(sorted(set(soft))))
