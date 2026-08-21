"""Closed, plan-owned nutrition recipe and substitution follow-ups."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import nutrition_plan
from recipe_engine.recipe_engine import match_plan
from recipe_engine.recipe_matcher import ingredient_key, mentioned_food_ids


PENDING_RECIPE_MEAL_REQUIRED = "RECIPE_MEAL_REQUIRED"


class NutritionFollowupOutcome(str, Enum):
    NO_MATCH = "NO_MATCH"
    CURATED_RECIPE_AVAILABLE = "CURATED_RECIPE_AVAILABLE"
    CURATED_RECIPE_UNAVAILABLE = "CURATED_RECIPE_UNAVAILABLE"
    SUBSTITUTION_AVAILABLE = "SUBSTITUTION_AVAILABLE"
    SUBSTITUTION_UNAVAILABLE = "SUBSTITUTION_UNAVAILABLE"
    SOURCE_FOOD_NOT_IN_MEAL = "SOURCE_FOOD_NOT_IN_MEAL"
    AMBIGUOUS_MEAL = "AMBIGUOUS_MEAL"
    NO_ACTIVE_PLAN = "NO_ACTIVE_PLAN"
    ERROR = "ERROR"


@dataclass(frozen=True)
class NutritionFollowup:
    outcome: NutritionFollowupOutcome
    reply: str | None = None
    next_pending_state: str | None = None

    @property
    def handled(self) -> bool:
        return self.outcome is not NutritionFollowupOutcome.NO_MATCH


def _english(language: str) -> bool:
    return str(language).lower() == "en"


def _message(kind: str, language: str) -> str:
    english = _english(language)
    messages = {
        "no_plan": (
            "I need a current nutrition plan before I can show a plan-bound recipe.",
            "Нуждая се от текущ хранителен план, преди да покажа рецепта към него.",
        ),
        "recipe_unavailable": (
            "I don't have a confirmed curated recipe for that exact meal.",
            "Нямам потвърдена подбрана рецепта за това точно хранене.",
        ),
        "substitution_unavailable": (
            "I don't have a confirmed substitution for that food in the current plan.",
            "За тази храна нямам потвърдена замяна в текущия план.",
        ),
        "source_not_in_meal": (
            "That food isn't part of the selected meal.",
            "Тази храна не присъства в избраното хранене.",
        ),
        "ambiguous_meal": (
            "Which meal should I use: breakfast, lunch, or dinner?",
            "Към кое хранене: закуска, обяд или вечеря?",
        ),
        "error": (
            "I can't verify a recipe follow-up for the current plan right now.",
            "Не мога да потвърдя тази заявка за рецепта към текущия план в момента.",
        ),
    }
    return messages[kind][0 if english else 1]


def _meal_reference(message: str) -> str | None:
    text = str(message or "").casefold()
    if any(token in text for token in ("breakfast", "закуск")):
        return "breakfast"
    if any(token in text for token in ("lunch", "обяд")):
        return "lunch"
    if any(token in text for token in ("dinner", "вечер")):
        return "dinner"
    return None


def _is_substitution(message: str) -> bool:
    text = str(message or "").casefold()
    return any(token in text for token in ("swap", "replace", "instead of", "замен", "вместо"))


def _is_recipe_or_preparation(message: str) -> bool:
    text = str(message or "").casefold()
    return any(token in text for token in ("recipe", "prepare", "рецепт", "приготв"))


def _food_ids(meal: object) -> frozenset[str]:
    return frozenset(
        str(food.food_id).strip() if getattr(food, "food_id", None)
        else ingredient_key(str(getattr(food, "display_name", "")))
        for food in getattr(meal, "foods", ())
    )


def resolve(*, message: str, language: str, profile: object,
            active_plan_loader: Callable[[], object | None],
            pending_state: str | None = None) -> NutritionFollowup:
    """Resolve only a recognized plan-owned follow-up; never invoke a model."""
    substitution = _is_substitution(message)
    explicit_recipe = _is_recipe_or_preparation(message)
    meal_reference = _meal_reference(message)
    recipe_continuation = pending_state == PENDING_RECIPE_MEAL_REQUIRED and meal_reference is not None
    if not substitution and not explicit_recipe and not recipe_continuation:
        return NutritionFollowup(NutritionFollowupOutcome.NO_MATCH)

    try:
        active_plan = active_plan_loader()
    except Exception:
        return NutritionFollowup(NutritionFollowupOutcome.ERROR, _message("error", language))
    if active_plan is None:
        return NutritionFollowup(NutritionFollowupOutcome.NO_ACTIVE_PLAN, _message("no_plan", language))

    if substitution:
        requested_food_ids = mentioned_food_ids(message)
        if meal_reference is not None:
            selected_meal = next((meal for meal in active_plan.meals
                                  if meal.meal_type == meal_reference), None)
        else:
            candidates = [meal for meal in active_plan.meals if requested_food_ids & _food_ids(meal)]
            selected_meal = candidates[0] if len(candidates) == 1 else None
            if len(candidates) > 1:
                return NutritionFollowup(NutritionFollowupOutcome.AMBIGUOUS_MEAL,
                                         _message("ambiguous_meal", language))
        if selected_meal is None or not requested_food_ids & _food_ids(selected_meal):
            return NutritionFollowup(NutritionFollowupOutcome.SOURCE_FOOD_NOT_IN_MEAL,
                                     _message("source_not_in_meal", language))
        try:
            recipe_match = match_plan(active_plan, profile if isinstance(profile, dict) else {}).get(selected_meal.id)
        except Exception:
            return NutritionFollowup(NutritionFollowupOutcome.ERROR, _message("error", language))
        substitutions = (() if recipe_match is None else tuple(
            substitution for substitution in recipe_match.recipe.substitutions
            if substitution.source_food_id in requested_food_ids))
        if not substitutions:
            return NutritionFollowup(NutritionFollowupOutcome.SUBSTITUTION_UNAVAILABLE,
                                     _message("substitution_unavailable", language))
        return NutritionFollowup(NutritionFollowupOutcome.SUBSTITUTION_AVAILABLE,
                                 substitutions[0].text)

    if meal_reference is None:
        return NutritionFollowup(NutritionFollowupOutcome.AMBIGUOUS_MEAL,
                                 _message("ambiguous_meal", language),
                                 PENDING_RECIPE_MEAL_REQUIRED)
    selected_meal = next((meal for meal in active_plan.meals if meal.meal_type == meal_reference), None)
    if selected_meal is None:
        return NutritionFollowup(NutritionFollowupOutcome.CURATED_RECIPE_UNAVAILABLE,
                                 _message("recipe_unavailable", language))
    try:
        recipe_match = match_plan(active_plan, profile if isinstance(profile, dict) else {}).get(selected_meal.id)
    except Exception:
        return NutritionFollowup(NutritionFollowupOutcome.ERROR, _message("error", language))
    if recipe_match is None:
        return NutritionFollowup(NutritionFollowupOutcome.CURATED_RECIPE_UNAVAILABLE,
                                 _message("recipe_unavailable", language))
    return NutritionFollowup(NutritionFollowupOutcome.CURATED_RECIPE_AVAILABLE,
                             nutrition_plan.render_delivery(active_plan, language, profile))
