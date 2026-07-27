"""Immutable recipe-library records and deterministic match results."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    meal_type: str
    difficulty: str
    cook_time_minutes: int
    equipment: tuple[str, ...]
    ingredients: tuple[str, ...]
    steps: tuple[str, ...]
    healthy_cooking_tips: tuple[str, ...]
    substitutions: tuple[str, ...]
    storage: str
    meal_prep: bool


@dataclass(frozen=True)
class RecipeMatch:
    recipe: Recipe
    score: float
