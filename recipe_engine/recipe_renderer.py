"""Serialize matched recipe presentation only; nutrition data is never changed."""
from __future__ import annotations

import base64
import json

from .recipe_models import RecipeMatch


def recipe_token(match: RecipeMatch) -> str:
    recipe = match.recipe
    payload = {
        "id": recipe.id, "title": recipe.title, "difficulty": recipe.difficulty,
        "minutes": recipe.cook_time_minutes, "steps": list(recipe.steps),
        "tips": list(recipe.healthy_cooking_tips), "substitutions": list(recipe.substitutions),
        "storage": recipe.storage, "meal_prep": recipe.meal_prep,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # Standard Base64 avoids the renderer's Markdown-cleaning ``__`` token
    # while remaining safe inside one pipe-table cell.
    return "recipe:" + base64.b64encode(encoded).decode("ascii")
