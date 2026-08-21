"""Serialize matched recipe presentation only; nutrition data is never changed."""
from __future__ import annotations

import base64
import json

from .recipe_models import RecipeMatch


_PREPARATION_ROLES = {
    "egg_whites": "cook_protein", "dev_egg_whites": "cook_protein",
    "chicken": "cooked_protein", "dev_chicken_breast_cooked": "cooked_protein",
    "turkey": "cooked_protein", "dev_turkey_breast_cooked": "cooked_protein",
    "rice": "cooked_starch", "dev_rice_cooked": "cooked_starch",
    "pasta": "cooked_starch", "dev_pasta_cooked": "cooked_starch",
    "oats": "dry_starch", "dev_oats_dry": "dry_starch",
    "apple": "fruit", "dev_apple": "fruit", "banana": "fruit", "dev_banana": "fruit",
    "zucchini": "cooked_vegetable", "dev_zucchini_cooked": "cooked_vegetable",
    "olive_oil": "added_fat", "dev_olive_oil": "added_fat",
}


def _assembly_steps(meal: object, language: str) -> list[str]:
    """Return only food-identity-backed preparation guidance, or no guidance."""
    bulgarian = str(language).lower() != "en"
    roles = {_PREPARATION_ROLES.get(str(getattr(food, "food_id", ""))) for food in getattr(meal, "foods", ())}
    roles.discard(None)
    if not roles:
        return []
    steps: list[str] = []
    if "cook_protein" in roles:
        steps.append("Приготви белтъците отделно до пълна готовност." if bulgarian else "Cook the egg whites separately until fully cooked.")
    if "dry_starch" in roles:
        steps.append("Приготви овеса отделно." if bulgarian else "Prepare the oats separately.")
    if "cooked_protein" in roles or "cooked_starch" in roles or "cooked_vegetable" in roles:
        steps.append("Подреди готовите компоненти в чиния; сервирай ги заедно само ако това ти е удобно." if bulgarian else "Plate the ready-to-eat components; serve them together only if convenient.")
    if "added_fat" in roles:
        steps.append("Добави зехтина към готовото ястие или зеленчуците." if bulgarian else "Add the olive oil to the finished meal or vegetables.")
    if "fruit" in roles:
        steps.append("Сервирай плода отделно или към храненето." if bulgarian else "Serve the fruit separately or alongside the meal.")
    return steps


def recipe_token(match: RecipeMatch, meal_id: str) -> str:
    """Bind recipe presentation to one immutable NutritionPlan meal ID."""
    recipe = match.recipe
    payload = {
        "id": recipe.id, "meal_id": meal_id, "food_ids": list(recipe.food_ids),
        "preparation_type": "recipe",
        "title": recipe.title, "difficulty": recipe.difficulty,
        "minutes": recipe.cook_time_minutes, "steps": list(recipe.steps),
        "tips": list(recipe.healthy_cooking_tips),
        "substitutions": [item.text for item in recipe.substitutions],
        "storage": recipe.storage, "meal_prep": recipe.meal_prep,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # Standard Base64 avoids the renderer's Markdown-cleaning ``__`` token
    # while remaining safe inside one pipe-table cell.
    return "recipe:" + base64.b64encode(encoded).decode("ascii")


def assembly_token(meal: object, language: str) -> str | None:
    """Serialize bounded food-aware preparation when structured identities permit it."""
    bulgarian = str(language).lower() != "en"
    steps = _assembly_steps(meal, language)
    if not steps:
        return None
    payload = {
        "id": "assembly-v1",
        "meal_id": str(getattr(meal, "id")),
        "food_ids": [str(getattr(food, "food_id", "")) for food in getattr(meal, "foods", ())],
        "preparation_type": "assembly",
        "title": str(getattr(meal, "name", "")),
        "difficulty": "",
        "minutes": "",
        "steps": steps,
        "tips": [],
        "substitutions": [],
        "storage": "",
        "meal_prep": False,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "recipe:" + base64.b64encode(encoded).decode("ascii")
