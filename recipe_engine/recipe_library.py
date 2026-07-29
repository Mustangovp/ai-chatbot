"""Read-only loader for the small, curated Bulgarian-market recipe library."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .recipe_matcher import ingredient_key
from .recipe_models import Recipe, RecipeSubstitution


_LIBRARY_PATH = Path(__file__).resolve().parent.parent / "data" / "recipes" / "recipes_v1.json"
_MEAL_TYPES = frozenset({"breakfast", "lunch", "dinner", "snack"})


def _as_strings(value: object, field: str, recipe_id: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"recipe {recipe_id}: {field} must be a non-empty string list")
    return tuple(item.strip() for item in value)


def _substitutions(value: object, recipe_id: str) -> tuple[RecipeSubstitution, ...]:
    if not isinstance(value, list):
        raise ValueError(f"recipe {recipe_id}: substitutions must be a list")
    result: list[RecipeSubstitution] = []
    for item in value:
        if isinstance(item, dict):
            source = item.get("source_food_id")
            replacement = item.get("replacement_food_id")
            text = item.get("text")
            if not all(isinstance(part, str) and part.strip() for part in (source, replacement, text)):
                raise ValueError(f"recipe {recipe_id}: substitution metadata is incomplete")
            result.append(RecipeSubstitution(source.strip(), replacement.strip(), text.strip()))
        elif isinstance(item, str) and item.strip():
            # Legacy prose remains readable by the loader, but the integrity
            # validator refuses to deliver it because it cannot prove source
            # and replacement identity.
            result.append(RecipeSubstitution("", "", item.strip()))
        else:
            raise ValueError(f"recipe {recipe_id}: substitution is invalid")
    return tuple(result)


def _recipe(value: object) -> Recipe:
    if not isinstance(value, dict):
        raise ValueError("recipe must be an object")
    recipe_id = value.get("id")
    if not isinstance(recipe_id, str) or not recipe_id.strip():
        raise ValueError("recipe id is required")
    meal_type = value.get("meal_type")
    if meal_type not in _MEAL_TYPES:
        raise ValueError(f"recipe {recipe_id}: unsupported meal type")
    cook_time = value.get("cook_time_minutes")
    if not isinstance(cook_time, int) or cook_time <= 0:
        raise ValueError(f"recipe {recipe_id}: cook_time_minutes must be positive")
    steps = _as_strings(value.get("steps"), "steps", recipe_id)
    if len(steps) > 6:
        raise ValueError(f"recipe {recipe_id}: at most six steps are allowed")
    tips = _as_strings(value.get("healthy_cooking_tips"), "healthy_cooking_tips", recipe_id)
    if len(tips) > 3:
        raise ValueError(f"recipe {recipe_id}: at most three healthy cooking tips are allowed")
    title = value.get("title")
    difficulty = value.get("difficulty")
    storage = value.get("storage")
    meal_prep = value.get("meal_prep")
    if not all(isinstance(item, str) and item.strip() for item in (title, difficulty, storage)):
        raise ValueError(f"recipe {recipe_id}: title, difficulty, and storage are required")
    if not isinstance(meal_prep, bool):
        raise ValueError(f"recipe {recipe_id}: meal_prep must be boolean")
    ingredients = _as_strings(value.get("ingredients"), "ingredients", recipe_id)
    return Recipe(
        id=recipe_id.strip(), title=title.strip(), meal_type=meal_type,
        difficulty=difficulty.strip(), cook_time_minutes=cook_time,
        equipment=_as_strings(value.get("equipment"), "equipment", recipe_id),
        ingredients=ingredients,
        food_ids=tuple(ingredient_key(item) for item in ingredients),
        steps=steps, healthy_cooking_tips=tips,
        substitutions=_substitutions(value.get("substitutions"), recipe_id),
        storage=storage.strip(), meal_prep=meal_prep,
    )


@lru_cache(maxsize=1)
def load_recipes() -> tuple[Recipe, ...]:
    raw = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("recipe library must be a list")
    recipes = tuple(_recipe(item) for item in raw)
    ids = [recipe.id for recipe in recipes]
    if not 20 <= len(recipes) <= 25 or len(ids) != len(set(ids)):
        raise ValueError("recipe library must contain 20-25 unique records")
    return recipes
