"""The single user-safe projection boundary for the isolated nutrition engine.

This is the only place that produces user-facing output. It exposes localized
labels and the exact optimizer numbers, and never exposes any identifier or
internal detail: no food_id, source ids, catalog version, review status,
TEST_POLICY_ONLY, meal-library id, solver internals, weights, or result codes.

Projections are immutable and canonically serializable: identical input yields
byte-identical output. ``catalog.project_user_day`` is a legacy helper and is
deliberately not used here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from .selector import MealDay

_MEAL_LABELS = {
    "breakfast": ("Закуска", "Breakfast"),
    "snack": ("Междинно хранене", "Snack"),
    "lunch": ("Обяд", "Lunch"),
    "dinner": ("Вечеря", "Dinner"),
}
_UNIT_LABELS = {
    "g": ("г", "g"), "ml": ("мл", "ml"), "pcs": ("бр.", "pcs"),
    "serving": ("порция", "serving"), "portion": ("порция", "portion"),
}


def _label(mapping, key: str, english: bool) -> str:
    pair = mapping.get(key)
    if pair is None:
        return key
    return pair[1] if english else pair[0]


@dataclass(frozen=True)
class ProjectedMacros:
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    kcal: Decimal


@dataclass(frozen=True)
class ProjectedFood:
    name: str
    quantity: Decimal
    unit: str
    macros: ProjectedMacros


@dataclass(frozen=True)
class ProjectedMeal:
    label: str
    foods: tuple[ProjectedFood, ...]
    totals: ProjectedMacros


@dataclass(frozen=True)
class UserPlanProjection:
    """Immutable, ID-free, localized plan. The only user-facing output shape."""

    language: str
    success: bool
    meals: tuple[ProjectedMeal, ...]
    daily_totals: ProjectedMacros


def _macros(source) -> ProjectedMacros:
    return ProjectedMacros(source.protein_g, source.carbs_g, source.fat_g, source.kcal)


def project_meal_day(meal_day: MealDay, language: str) -> UserPlanProjection:
    """Project an assembled MealDay into the user-safe localized shape.

    Copies every number verbatim (no rounding, no recomputation) and attaches
    only localized labels. Emits no identifier of any kind.
    """
    english = str(language).lower() == "en"
    meals = []
    for meal in meal_day.meals:
        foods = tuple(
            ProjectedFood(
                name=(food.display_name_en if english else food.display_name_bg),
                quantity=food.quantity,
                unit=_label(_UNIT_LABELS, food.display_unit, english),
                macros=_macros(food.macros),
            )
            for food in meal.foods
        )
        meals.append(ProjectedMeal(
            label=_label(_MEAL_LABELS, meal.meal_type, english),
            foods=foods,
            totals=_macros(meal.macros),
        ))
    return UserPlanProjection(
        language="en" if english else "bg",
        success=True,
        meals=tuple(meals),
        daily_totals=_macros(meal_day.daily_macros),
    )


def _macros_dict(m: ProjectedMacros) -> dict:
    return {"protein_g": str(m.protein_g), "carbs_g": str(m.carbs_g),
            "fat_g": str(m.fat_g), "kcal": str(m.kcal)}


def canonical_bytes(projection: UserPlanProjection) -> bytes:
    """Deterministic canonical serialization for equality/hash checks.

    Decimals become their exact string form; key order is fixed; encoding is
    UTF-8. No identifier is ever included because the projection has none.
    """
    document = {
        "language": projection.language,
        "success": projection.success,
        "daily_totals": _macros_dict(projection.daily_totals),
        "meals": [
            {
                "label": meal.label,
                "totals": _macros_dict(meal.totals),
                "foods": [
                    {"name": food.name, "quantity": str(food.quantity),
                     "unit": food.unit, "macros": _macros_dict(food.macros)}
                    for food in meal.foods
                ],
            }
            for meal in projection.meals
        ],
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=False).encode("utf-8")
