"""Pure deterministic selection over the immutable Nutrition Knowledge Library.

This module chooses only pre-defined, catalog-backed meal candidates. It has no
OpenAI import, no prompt construction, no persistence, and no request routing.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .meal_library import (
    MEAL_CATEGORIES,
    PREPARATION_DIFFICULTIES,
    MealCandidate,
    NutritionKnowledgeLibrary,
)


def _non_negative(name: str, value: Decimal | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class MealMacroBounds:
    """Caller-owned bounds; the library supplies no hidden nutrition policy."""

    kcal_min: Decimal | None = None
    kcal_max: Decimal | None = None
    protein_min_g: Decimal | None = None
    protein_max_g: Decimal | None = None
    carbs_min_g: Decimal | None = None
    carbs_max_g: Decimal | None = None
    fat_min_g: Decimal | None = None
    fat_max_g: Decimal | None = None

    def __post_init__(self) -> None:
        pairs = (
            ("kcal", self.kcal_min, self.kcal_max),
            ("protein_g", self.protein_min_g, self.protein_max_g),
            ("carbs_g", self.carbs_min_g, self.carbs_max_g),
            ("fat_g", self.fat_min_g, self.fat_max_g),
        )
        for name, minimum, maximum in pairs:
            _non_negative(f"{name}_min", minimum)
            _non_negative(f"{name}_max", maximum)
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{name} minimum exceeds maximum")

    def matches(self, meal: MealCandidate) -> bool:
        values = (
            (meal.macros.kcal, self.kcal_min, self.kcal_max),
            (meal.macros.protein_g, self.protein_min_g, self.protein_max_g),
            (meal.macros.carbs_g, self.carbs_min_g, self.carbs_max_g),
            (meal.macros.fat_g, self.fat_min_g, self.fat_max_g),
        )
        return all((minimum is None or value >= minimum)
                   and (maximum is None or value <= maximum)
                   for value, minimum, maximum in values)


@dataclass(frozen=True)
class MealSelectionQuery:
    category: str
    macro_bounds: MealMacroBounds = MealMacroBounds()
    dietary_restrictions: frozenset[str] = frozenset()
    ingredient_blacklist: frozenset[str] = frozenset()
    required_tags: frozenset[str] = frozenset()
    maximum_preparation_difficulty: str | None = None

    def __post_init__(self) -> None:
        if self.category not in MEAL_CATEGORIES:
            raise ValueError("unknown meal category")
        if not isinstance(self.macro_bounds, MealMacroBounds):
            raise ValueError("macro_bounds must be MealMacroBounds")
        difficulty = self.maximum_preparation_difficulty
        if difficulty is not None and difficulty not in PREPARATION_DIFFICULTIES:
            raise ValueError("unknown maximum preparation difficulty")
        for field in ("dietary_restrictions", "ingredient_blacklist", "required_tags"):
            normalized = frozenset(
                str(value).strip().lower() for value in getattr(self, field) if str(value).strip())
            object.__setattr__(self, field, normalized)


class MealSelectionEngine:
    """Select candidates deterministically; it never creates a meal or food."""

    @staticmethod
    def select(library: NutritionKnowledgeLibrary, query: MealSelectionQuery) -> tuple[MealCandidate, ...]:
        if not isinstance(library, NutritionKnowledgeLibrary):
            raise ValueError("selection requires a NutritionKnowledgeLibrary")
        difficulty_limit = (PREPARATION_DIFFICULTIES.index(query.maximum_preparation_difficulty)
                            if query.maximum_preparation_difficulty is not None else None)
        selected = []
        for meal in library.meals:
            if meal.category != query.category:
                continue
            if not query.macro_bounds.matches(meal):
                continue
            if not query.dietary_restrictions.issubset(meal.dietary_compatibility):
                continue
            if query.ingredient_blacklist.intersection(item.food_id for item in meal.ingredients):
                continue
            if not query.required_tags.issubset(meal.tags):
                continue
            if difficulty_limit is not None and PREPARATION_DIFFICULTIES.index(
                    meal.preparation_difficulty) > difficulty_limit:
                continue
            selected.append(meal)
        return tuple(sorted(selected, key=lambda meal: meal.meal_id))

    @classmethod
    def select_one(cls, library: NutritionKnowledgeLibrary,
                   query: MealSelectionQuery) -> MealCandidate | None:
        candidates = cls.select(library, query)
        return candidates[0] if candidates else None
