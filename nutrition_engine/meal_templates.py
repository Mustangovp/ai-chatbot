"""Deterministic meal-structure templates for the isolated nutrition engine.

A template describes the food *groups* (catalog categories) a meal of a given
type may contain. Templates carry no free text, no macros, and no portions:
they only constrain structure. All plan numbers come from the optimizer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import MEAL_TYPES

# Catalog categories are the food "groups" a template reasons about.
FOOD_GROUPS = ("protein", "carbohydrate", "vegetable", "fruit", "fat")


@dataclass(frozen=True)
class MealTemplate:
    """Immutable structural rule for one meal type."""

    meal_type: str
    required_groups: tuple[str, ...]
    optional_groups: tuple[str, ...]
    minimum_groups: int
    maximum_groups: int

    def __post_init__(self) -> None:
        if self.meal_type not in MEAL_TYPES:
            raise ValueError(f"unknown meal type: {self.meal_type}")
        allowed = set(self.required_groups) | set(self.optional_groups)
        if any(group not in FOOD_GROUPS for group in allowed):
            raise ValueError("template references an unknown food group")
        if len(set(self.required_groups)) != len(self.required_groups):
            raise ValueError("required groups must be unique")
        if set(self.required_groups) & set(self.optional_groups):
            raise ValueError("a group cannot be both required and optional")
        if not (1 <= self.minimum_groups <= self.maximum_groups):
            raise ValueError("invalid group-count bounds")
        if len(self.required_groups) > self.maximum_groups:
            raise ValueError("required groups exceed the maximum group count")
        if self.minimum_groups < len(self.required_groups):
            raise ValueError("minimum groups cannot drop a required group")

    @property
    def allowed_groups(self) -> frozenset[str]:
        return frozenset(self.required_groups) | frozenset(self.optional_groups)


_TEMPLATES: dict[str, MealTemplate] = {
    "breakfast": MealTemplate("breakfast", ("protein", "carbohydrate"), ("fruit", "fat"), 2, 4),
    "snack": MealTemplate("snack", ("protein",), ("fruit", "fat", "carbohydrate"), 1, 2),
    "lunch": MealTemplate("lunch", ("protein", "carbohydrate", "vegetable"), ("fat",), 3, 4),
    "dinner": MealTemplate("dinner", ("protein", "carbohydrate", "vegetable"), ("fat",), 3, 4),
}


def template_for(meal_type: str) -> MealTemplate:
    """Return the immutable template for a meal type."""
    try:
        return _TEMPLATES[meal_type]
    except KeyError:
        raise ValueError(f"no template for meal type: {meal_type}")


def all_templates() -> tuple[MealTemplate, ...]:
    """Templates in a stable meal order."""
    return tuple(_TEMPLATES[meal] for meal in MEAL_TYPES if meal in _TEMPLATES)


def template_violations(meal_type: str, groups: Iterable[str]) -> tuple[str, ...]:
    """Return sorted, deterministic structural violations for the given groups.

    `groups` is the set of catalog categories present in a meal. This never
    changes the meal; it only reports whether the structure fits the template.
    """
    template = template_for(meal_type)
    present = set(groups)
    violations: list[str] = []
    for group in present:
        if group not in template.allowed_groups:
            violations.append(f"disallowed_group:{group}")
    for group in template.required_groups:
        if group not in present:
            violations.append(f"missing_required_group:{group}")
    distinct = len(present)
    if distinct < template.minimum_groups:
        violations.append("below_minimum_groups")
    if distinct > template.maximum_groups:
        violations.append("above_maximum_groups")
    return tuple(sorted(violations))
