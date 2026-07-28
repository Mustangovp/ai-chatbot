"""Deterministic role-based recipe matching. No model calls."""
from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from .recipe_models import Recipe, RecipeMatch


_TOKEN = re.compile(r"[^a-z0-9\u0400-\u04ff]+")

# These aliases are deliberately exact after punctuation/case normalization.  They
# cover display names produced by the current Bulgarian and English food catalogs.
_ALIASES = {
    "chicken": "chicken", "chicken breast": "chicken", "chicken breast roasted": "chicken",
    "\u043f\u0438\u043b\u0435\u0448\u043a\u043e": "chicken", "\u043f\u0438\u043b\u0435\u0448\u043a\u043e \u0444\u0438\u043b\u0435": "chicken", "\u043f\u0438\u043b\u0435\u0448\u043a\u043e \u0433\u044a\u0440\u0434\u0438": "chicken", "\u043f\u0438\u043b\u0435\u0448\u043a\u0438 \u0433\u044a\u0440\u0434\u0438": "chicken",
    "\u043f\u0438\u043b\u0435\u0448\u043a\u0438 \u0433\u044a\u0440\u0434\u0438 \u043f\u0435\u0447\u0435\u043d\u0438 \u0431\u0435\u0437 \u043a\u043e\u0436\u0430": "chicken",
    "turkey": "turkey", "turkey breast": "turkey", "\u043f\u0443\u0435\u0448\u043a\u043e": "turkey", "\u043f\u0443\u0435\u0448\u043a\u043e \u0444\u0438\u043b\u0435": "turkey", "\u043f\u0443\u0435\u0448\u043a\u043e \u0444\u0438\u043b\u0435 \u043f\u0435\u0447\u0435\u043d\u043e": "turkey",
    "salmon": "salmon", "salmon grilled": "salmon", "\u0441\u044c\u043e\u043c\u0433\u0430": "salmon",
    "tuna": "tuna", "\u0442\u043e\u043d": "tuna", "\u0440\u0438\u0431\u0430 \u0442\u043e\u043d": "tuna",
    "lean beef": "lean_beef", "beef": "lean_beef", "\u0442\u0435\u043b\u0435\u0448\u043a\u043e": "lean_beef", "\u043a\u0430\u0439\u043c\u0430": "lean_beef", "\u0442\u0435\u043b\u0435\u0448\u043a\u0430 \u043a\u0430\u0439\u043c\u0430": "lean_beef",
    "eggs": "eggs", "egg": "eggs", "boiled whole egg": "eggs", "\u044f\u0439\u0446\u0430": "eggs", "\u044f\u0439\u0446\u0435": "eggs", "\u044f\u0439\u0446\u0435 \u0441\u0432\u0430\u0440\u0435\u043d\u043e": "eggs",
    "egg whites": "egg_whites", "pasteurized egg whites": "egg_whites", "\u0431\u0435\u043b\u0442\u044a\u0446\u0438": "egg_whites", "\u0431\u0435\u043b\u0442\u044a\u0446\u0438 \u043f\u0430\u0441\u0442\u044c\u043e\u0440\u0438\u0437\u0438\u0440\u0430\u043d\u0438": "egg_whites",
    "greek yogurt": "greek_yogurt", "yogurt": "greek_yogurt", "\u043a\u0438\u0441\u0435\u043b\u043e \u043c\u043b\u044f\u043a\u043e": "greek_yogurt", "\u0433\u0440\u044a\u0446\u043a\u043e \u043a\u0438\u0441\u0435\u043b\u043e \u043c\u043b\u044f\u043a\u043e": "greek_yogurt", "\u043a\u0438\u0441\u0435\u043b\u043e \u043c\u043b\u044f\u043a\u043e \u0432\u0435\u0440\u0435\u044f": "greek_yogurt", "\u043a\u0438\u0441\u0435\u043b\u043e \u043c\u043b\u044f\u043a\u043e \u0432\u0435\u0440\u0435\u044f 2": "greek_yogurt",
    "cottage cheese": "cottage_cheese", "\u0438\u0437\u0432\u0430\u0440\u0430": "cottage_cheese", "whey": "whey", "\u0441\u0443\u0440\u043e\u0432\u0430\u0442\u044a\u0447\u0435\u043d \u043f\u0440\u043e\u0442\u0435\u0438\u043d": "whey",
    "lentils": "lentils", "\u043b\u0435\u0449\u0430": "lentils", "\u043b\u0435\u0449\u0430 \u0441\u0432\u0430\u0440\u0435\u043d\u0430": "lentils", "chickpeas": "chickpeas", "\u043d\u0430\u0445\u0443\u0442": "chickpeas", "\u043d\u0430\u0445\u0443\u0442 \u0441\u0432\u0430\u0440\u0435\u043d": "chickpeas",
    "oats": "oats", "oatmeal": "oats", "raw oats": "oats", "oats dry": "oats", "\u043e\u0432\u0435\u0441\u0435\u043d\u0438 \u044f\u0434\u043a\u0438": "oats", "\u043e\u0432\u0435\u0441\u0435\u043d\u0438 \u044f\u0434\u043a\u0438 \u0441\u0443\u0445\u0438": "oats",
    "rice": "rice", "rice cooked": "rice", "brown rice": "rice", "brown rice cooked": "rice", "\u043e\u0440\u0438\u0437": "rice", "\u043e\u0440\u0438\u0437 \u0441\u0432\u0430\u0440\u0435\u043d": "rice", "\u043e\u0440\u0438\u0437 \u0431\u0430\u0441\u043c\u0430\u0442\u0438": "rice",
    "pasta": "pasta", "pasta cooked": "pasta", "\u043f\u0430\u0441\u0442\u0430": "pasta", "\u043f\u0430\u0441\u0442\u0430 \u0441\u0432\u0430\u0440\u0435\u043d\u0430": "pasta",
    "potatoes": "potatoes", "potatoes cooked": "potatoes", "\u043a\u0430\u0440\u0442\u043e\u0444\u0438": "potatoes", "\u043a\u0430\u0440\u0442\u043e\u0444\u0438 \u0441\u0432\u0430\u0440\u0435\u043d\u0438": "potatoes",
    "quinoa": "quinoa", "quinoa cooked": "quinoa", "wholegrain bread": "wholegrain_bread", "bread": "wholegrain_bread", "\u0445\u043b\u044f\u0431": "wholegrain_bread",
    "apple": "apple", "\u044f\u0431\u044a\u043b\u043a\u0430": "apple", "\u044f\u0431\u044a\u043b\u043a\u0430 \u0441\u0443\u0440\u043e\u0432\u0430": "apple", "banana": "banana", "\u0431\u0430\u043d\u0430\u043d": "banana",
    "broccoli": "broccoli", "broccoli steamed": "broccoli", "\u0431\u0440\u043e\u043a\u043e\u043b\u0438": "broccoli", "\u0437\u0430\u0434\u0443\u0448\u0435\u043d\u0438 \u0431\u0440\u043e\u043a\u043e\u043b\u0438": "broccoli", "spinach": "spinach", "spinach raw": "spinach", "\u0441\u043f\u0430\u043d\u0430\u043a": "spinach",
    "tomato": "tomato", "\u0434\u043e\u043c\u0430\u0442": "tomato", "zucchini": "zucchini", "\u0442\u0438\u043a\u0432\u0438\u0447\u043a\u0438": "zucchini", "\u0442\u0438\u043a\u0432\u0438\u0447\u043a\u0438 \u0441\u0432\u0430\u0440\u0435\u043d\u0438": "zucchini",
    "avocado": "avocado", "\u0430\u0432\u043e\u043a\u0430\u0434\u043e": "avocado", "salad": "salad", "\u0441\u0430\u043b\u0430\u0442\u0430": "salad",
    "olive oil": "olive_oil", "\u0437\u0435\u0445\u0442\u0438\u043d": "olive_oil", "almonds": "almonds", "\u0431\u0430\u0434\u0435\u043c\u0438": "almonds", "herbs": "herbs", "spices": "spices", "lemon": "lemon", "seasoning": "seasoning", "garnish": "garnish",
}

_PRIMARY_PROTEINS = frozenset({"chicken", "turkey", "salmon", "tuna", "lean_beef", "eggs", "egg_whites", "cottage_cheese", "greek_yogurt", "whey", "lentils", "chickpeas"})
_PRIMARY_CARBS = frozenset({"oats", "rice", "pasta", "potatoes", "quinoa", "wholegrain_bread"})
_VEGETABLE_OR_FRUIT = frozenset({"apple", "banana", "broccoli", "spinach", "tomato", "zucchini", "avocado", "salad"})
_AUXILIARY = frozenset({"olive_oil", "herbs", "spices", "lemon", "seasoning", "garnish"})


def ingredient_key(value: str) -> str:
    """Map a catalog display name to a stable ingredient key."""
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


def _grams(food: object) -> Decimal:
    try:
        return Decimal(str(getattr(food, "grams", 0)))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _meal_ingredients(meal: object) -> tuple[tuple[str, Decimal, int], ...]:
    return tuple(
        (ingredient_key(str(getattr(food, "display_name", ""))), _grams(food), index)
        for index, food in enumerate(getattr(meal, "foods", ()))
        if ingredient_key(str(getattr(food, "display_name", "")))
    )


def _dominant_carb(ingredients: tuple[tuple[str, Decimal, int], ...]) -> str | None:
    carbs = [item for item in ingredients if item[0] in _PRIMARY_CARBS]
    if not carbs:
        return None
    # Larger servings win; first appearance makes equal gram amounts stable.
    return max(carbs, key=lambda item: (item[1], -item[2]))[0]


def match_meal(meal: object, recipes: Iterable[Recipe], available_equipment: frozenset[str], *,
               threshold: float = 0.4) -> RecipeMatch | None:
    """Return a role-compatible recipe without altering the authoritative meal."""
    del threshold  # Kept for source compatibility; semantic eligibility is explicit.
    meal_type = str(getattr(meal, "meal_type", "")).lower()
    ingredients = _meal_ingredients(meal)
    food_keys = frozenset(item[0] for item in ingredients)
    proteins = food_keys & _PRIMARY_PROTEINS
    dominant_carb = _dominant_carb(ingredients)
    if not food_keys or not proteins:
        return None

    candidates: list[RecipeMatch] = []
    for recipe in recipes:
        if recipe.meal_type != meal_type or not set(recipe.equipment).issubset(available_equipment):
            continue
        recipe_keys = frozenset(ingredient_key(item) for item in recipe.ingredients)
        # Protein identity is the safety boundary. Do not label chicken as
        # yoghurt, salmon as tuna, or whole eggs as egg whites.
        if recipe_keys & _PRIMARY_PROTEINS != proteins:
            continue
        # When a meal has a primary carb, its largest portion determines the
        # matching carb. Vegetables and oils stay visible but never block it.
        if dominant_carb is not None and dominant_carb not in recipe_keys:
            continue
        # Supporting ingredients break otherwise equal compatible candidates,
        # but never make an eligible meal fail. This keeps almond recipes from
        # being replaced by a banana recipe while allowing vegetable swaps.
        supporting_matches = len((food_keys & recipe_keys) - _PRIMARY_PROTEINS - _PRIMARY_CARBS - _AUXILIARY)
        score = 1.0 + (0.01 * supporting_matches)
        candidates.append(RecipeMatch(recipe, score))
    return min(candidates, key=lambda item: (-item.score, item.recipe.id), default=None)
