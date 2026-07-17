"""Immutable, Decimal-only nutrition foundation models.

All nutrition policy is supplied by callers. This module supplies no clinical
or production policy defaults.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


def _non_negative(name: str, value: Decimal | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class NutritionTargets:
    calories_target: Decimal
    calories_tolerance: Decimal
    protein_min_g: Decimal | None = None
    protein_max_g: Decimal | None = None
    carbs_min_g: Decimal | None = None
    carbs_max_g: Decimal | None = None
    fat_min_g: Decimal | None = None
    fat_max_g: Decimal | None = None

    def __post_init__(self) -> None:
        if self.calories_target <= 0:
            raise ValueError("calories_target must be positive")
        if not Decimal("0") <= self.calories_tolerance <= Decimal("1"):
            raise ValueError("calories_tolerance must be between zero and one")
        for name in ("protein_min_g", "protein_max_g", "carbs_min_g", "carbs_max_g", "fat_min_g", "fat_max_g"):
            _non_negative(name, getattr(self, name))
        for lower, upper in ((self.protein_min_g, self.protein_max_g),
                             (self.carbs_min_g, self.carbs_max_g),
                             (self.fat_min_g, self.fat_max_g)):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError("minimum constraint exceeds maximum constraint")


@dataclass(frozen=True)
class DietConstraints:
    excluded_food_ids: frozenset[str] = frozenset()
    excluded_categories: frozenset[str] = frozenset()
    allergen_exclusions: frozenset[str] = frozenset()
    no_chicken: bool = False
    no_dairy: bool = False
    diet_type: str = "standard_omnivore"
    allowed_catalog_version: str | None = None


@dataclass(frozen=True)
class FoodItem:
    food_id: str
    catalog_version: str
    display_name_bg: str
    display_name_en: str
    category: str
    preparation_state: str
    nutrient_reference_quantity: Decimal
    protein_per_100g: Decimal
    carbs_per_100g: Decimal
    fat_per_100g: Decimal
    kcal_per_100g: Decimal
    default_unit: str
    allowed_units: tuple[str, ...]
    grams_per_piece: Decimal | None
    minimum_portion: Decimal
    maximum_portion: Decimal
    portion_increment: Decimal
    default_portion: Decimal
    allergens: frozenset[str]
    dietary_tags: frozenset[str]
    allowed_meals: frozenset[str]
    source_name: str
    source_record_id: str
    source_version: str
    review_status: str
    reviewer_note: str
    data_basis: str


@dataclass(frozen=True)
class MealSelection:
    meal_type: str
    ordered_food_ids: tuple[str, ...]


@dataclass(frozen=True)
class PracticalityPolicy:
    maximum_foods_per_meal: int
    meal_calorie_share_ranges: tuple[tuple[str, Decimal, Decimal], ...] = ()
    protein_distribution_preference: bool = False
    maximum_portion_multiplier_from_default: Decimal | None = None
    allow_supplement_foods: bool = False
    maximum_supplement_items: int = 0
    category_portion_overrides: tuple[tuple[str, Decimal, Decimal, Decimal], ...] = ()
    max_search_nodes: int = 1_000_000
    allow_duplicate_food_ids_per_meal: bool = False

    def __post_init__(self) -> None:
        if self.maximum_foods_per_meal < 1 or self.max_search_nodes < 1:
            raise ValueError("practicality limits must be positive")
        _non_negative("maximum_portion_multiplier_from_default", self.maximum_portion_multiplier_from_default)


@dataclass(frozen=True)
class Nutrients:
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    kcal: Decimal

    @classmethod
    def zero(cls) -> "Nutrients":
        return cls(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))

    def plus(self, other: "Nutrients") -> "Nutrients":
        return Nutrients(self.protein_g + other.protein_g, self.carbs_g + other.carbs_g,
                         self.fat_g + other.fat_g, self.kcal + other.kcal)


@dataclass(frozen=True)
class OptimizedFood:
    food_id: str
    quantity: Decimal
    display_unit: str
    grams: Decimal
    nutrients: Nutrients


@dataclass(frozen=True)
class OptimizedMeal:
    meal_type: str
    foods: tuple[OptimizedFood, ...]
    totals: Nutrients


@dataclass(frozen=True)
class OptimizedNutritionDay:
    meals: tuple[OptimizedMeal, ...]
    daily_totals: Nutrients
    target_deviations: tuple[tuple[str, Decimal], ...]
    catalog_version: str
    feasibility_status: str


def localized_food_name(food: FoodItem, language: str) -> str:
    """The sole Phase-1 presentation helper: it never reveals internal IDs."""
    return food.display_name_bg if str(language).lower() == "bg" else food.display_name_en
