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

_ALIASES.update({
    "milk": "milk", "cow milk": "milk", "прясно мляко": "milk", "краве мляко": "milk",
    "olives": "olives", "olive": "olives", "маслини": "olives",
})

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


_NEGLIGIBLE_COOKING_AIDS = frozenset({"water", "salt", "pepper", "herbs", "spices", "lemon", "seasoning", "garnish"})
_APPROVED_SUBSTITUTIONS = frozenset({
    ("banana", "apple"),
    ("spinach", "broccoli"),
})


def _meal_food_ids(meal: object) -> frozenset[str]:
    ids = []
    for food in getattr(meal, "foods", ()):
        supplied = getattr(food, "food_id", None)
        ids.append(str(supplied).strip() if isinstance(supplied, str) and supplied.strip()
                   else ingredient_key(str(getattr(food, "display_name", ""))))
    return frozenset(item for item in ids if item)


def _mentioned_food_ids(text: str) -> frozenset[str]:
    normalized = " ".join(part for part in _TOKEN.split(text.lower()) if part)
    mentions: set[str] = set()
    for alias, food_id in _ALIASES.items():
        if re.search(r"(?<!\\w)" + re.escape(alias) + r"(?!\\w)", normalized):
            mentions.add(food_id)
    return frozenset(mentions)


def mentioned_food_ids(text: str) -> frozenset[str]:
    """Return canonical food IDs explicitly mentioned in supported EN/BG food names."""
    return _mentioned_food_ids(text)


def validate_recipe_for_meal(recipe: Recipe, meal: object) -> str | None:
    """Return an integrity reason, or ``None`` for an exact safe recipe binding."""
    meal_ids = _meal_food_ids(meal)
    recipe_ids = frozenset(recipe.food_ids)
    if not meal_ids or recipe_ids != meal_ids or len(recipe.food_ids) != len(recipe_ids):
        return "recipe food IDs do not exactly match the meal food IDs"

    allowed_mentions = meal_ids | _NEGLIGIBLE_COOKING_AIDS
    for substitution in recipe.substitutions:
        pair = (substitution.source_food_id, substitution.replacement_food_id)
        if (not substitution.source_food_id or not substitution.replacement_food_id
                or not substitution.text or substitution.source_food_id not in meal_ids
                or pair not in _APPROVED_SUBSTITUTIONS):
            return "recipe substitution is not an approved mapping for a present food"
        allowed_mentions = allowed_mentions | {substitution.replacement_food_id}

    prose = " ".join((recipe.title, *recipe.steps, *recipe.healthy_cooking_tips, recipe.storage))
    absent = _mentioned_food_ids(prose) - allowed_mentions
    if absent:
        return "recipe prose mentions food IDs absent from the linked meal: " + ", ".join(sorted(absent))
    return None


def _dominant_carb(ingredients: tuple[tuple[str, Decimal, int], ...]) -> str | None:
    carbs = [item for item in ingredients if item[0] in _PRIMARY_CARBS]
    if not carbs:
        return None
    # Larger servings win; first appearance makes equal gram amounts stable.
    return max(carbs, key=lambda item: (item[1], -item[2]))[0]


def match_meal(meal: object, recipes: Iterable[Recipe], available_equipment: frozenset[str], *,
               threshold: float = 0.4) -> RecipeMatch | None:
    """Return only a recipe proven to describe this exact authoritative meal."""
    del threshold  # Retained as a source-compatible argument; identity is exact.
    meal_type = str(getattr(meal, "meal_type", "")).lower()
    if not _meal_food_ids(meal):
        return None

    candidates: list[RecipeMatch] = []
    for recipe in recipes:
        if recipe.meal_type != meal_type or not set(recipe.equipment).issubset(available_equipment):
            continue
        if validate_recipe_for_meal(recipe, meal) is None:
            candidates.append(RecipeMatch(recipe, 1.0))
    return min(candidates, key=lambda item: (-item.score, item.recipe.id), default=None)
