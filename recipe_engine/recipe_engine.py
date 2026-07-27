"""Post-validation recipe orchestrator. It is pure, synchronous, and fail-open."""
from __future__ import annotations

from collections.abc import Mapping

from .recipe_library import load_recipes
from .recipe_matcher import match_meal, profile_equipment
from .recipe_models import RecipeMatch


def match_plan(plan: object, profile: object = None) -> Mapping[str, RecipeMatch]:
    """Match immutable meals without mutating them or invoking external services."""
    available = profile_equipment(profile)
    matches: dict[str, RecipeMatch] = {}
    for meal in getattr(plan, "meals", ()):
        match = match_meal(meal, load_recipes(), available)
        if match is not None:
            matches[str(getattr(meal, "id"))] = match
    return matches
