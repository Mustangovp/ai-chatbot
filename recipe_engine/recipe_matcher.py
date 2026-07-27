"""Exact, deterministic ingredient-overlap recipe matching. No model calls."""
from __future__ import annotations

import re
from collections.abc import Iterable

from .recipe_models import Recipe, RecipeMatch


_TOKEN = re.compile(r"[^a-z0-9\u0400-\u04ff]+")
_ALIASES = {
    "пилешко": "chicken", "пилешки": "chicken", "пилешко филе": "chicken",
    "пилешки гърди": "chicken", "chicken breast": "chicken",
    "ориз": "rice", "ориз сварен": "rice", "ориз сух": "rice", "rice cooked": "rice", "brown rice": "rice",
    "овес": "oats", "овесени ядки": "oats", "овесени ядки сухи": "oats",
    "raw oats": "oats", "oats dry": "oats",
    "яйце": "eggs", "яйца": "eggs", "яйчен": "eggs", "яйце сварено": "eggs",
    "boiled whole egg": "eggs", "сьомга": "salmon",
    "риба тон": "tuna", "тон": "tuna", "кисело мляко": "greek_yogurt",
    "гръцко кисело мляко": "greek_yogurt", "извара": "cottage_cheese",
    "картофи": "potatoes", "картоф": "potatoes", "картофи сварени": "potatoes",
    "broccoli": "broccoli", "броколи": "broccoli",
    "спанак": "spinach", "банан": "banana", "ябълка": "apple",
    "леща": "lentils", "леща сварена": "lentils", "нахут": "chickpeas", "нахут сварен": "chickpeas", "кайма": "lean_beef",
    "телешко": "lean_beef", "пуешко": "turkey", "хляб": "wholegrain_bread",
    "паста": "pasta", "паста сварена": "pasta", "авокадо": "avocado", "авокадо сурово": "avocado", "almond butter": "almond_butter", "сирене": "cheese",
    "whey": "whey", "суроватъчен протеин": "whey",
}


def ingredient_key(value: str) -> str:
    """Map known display names to explicit keys; otherwise keep exact token form."""
    normalized = " ".join(part for part in _TOKEN.split(value.lower()) if part)
    return _ALIASES.get(normalized, normalized.replace(" ", "_"))


def profile_equipment(profile: object) -> frozenset[str]:
    """Cooking equipment, not fitness equipment; default is intentionally pan + oven."""
    if isinstance(profile, dict):
        supplied = profile.get("cooking_equipment", profile.get("cookingEquipment"))
        if isinstance(supplied, str):
            supplied = [part.strip() for part in supplied.split(",")]
        if isinstance(supplied, (list, tuple, set, frozenset)):
            values = frozenset(str(item).strip().lower() for item in supplied if str(item).strip())
            if values:
                return values
    return frozenset({"pan", "oven"})


def match_meal(meal: object, recipes: Iterable[Recipe], available_equipment: frozenset[str], *,
               threshold: float = 0.4) -> RecipeMatch | None:
    """Return the stable top Jaccard match, or None without affecting delivery."""
    meal_type = str(getattr(meal, "meal_type", "")).lower()
    foods = getattr(meal, "foods", ())
    food_keys = frozenset(ingredient_key(str(getattr(food, "display_name", ""))) for food in foods)
    food_keys = frozenset(key for key in food_keys if key)
    if not food_keys:
        return None
    candidates: list[RecipeMatch] = []
    for recipe in recipes:
        if recipe.meal_type != meal_type or not set(recipe.equipment).issubset(available_equipment):
            continue
        recipe_keys = frozenset(ingredient_key(item) for item in recipe.ingredients)
        union = food_keys | recipe_keys
        score = len(food_keys & recipe_keys) / len(union) if union else 0.0
        if score >= threshold:
            candidates.append(RecipeMatch(recipe, score))
    return min(candidates, key=lambda item: (-item.score, item.recipe.id), default=None)
