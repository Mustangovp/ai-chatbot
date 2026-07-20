"""Deterministic daily nutrition-plan construction from verified inputs only.

The construction engine has no LLM, prompt, renderer, database, or routing
dependency. It turns a recommendation decision, verified profile, caller-owned
target policy, and Nutrition Knowledge Library candidates into an immutable
nutrition blueprint.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any, Mapping

from recommend.engine import ImmutableUserProfile, RecommendationBlueprint, RecommendationIntent, RecommendationOutcome

from .meal_library import MEAL_CATEGORIES, MealCandidate, NutritionKnowledgeLibrary
from .meal_selection import MealMacroBounds, MealSelectionEngine, MealSelectionQuery
from .models import Nutrients


PLAN_CONSTRUCTION_VERSION = "nutrition-plan-construction-v1"


class NutritionConstructionError(ValueError):
    pass


def _pairs(values: tuple[tuple[str, Decimal], ...], name: str) -> tuple[tuple[str, Decimal], ...]:
    normalized = tuple(sorted((str(key).strip().lower(), Decimal(str(value)))
                              for key, value in values if str(key).strip()))
    if not normalized or len({key for key, _ in normalized}) != len(normalized):
        raise ValueError(f"{name} must have unique entries")
    if any(value < 0 for _, value in normalized):
        raise ValueError(f"{name} values must be non-negative")
    return normalized


@dataclass(frozen=True)
class NutritionTargetPolicy:
    """Explicit target policy. The engine supplies no hidden nutrition defaults."""

    activity_factors: tuple[tuple[str, Decimal], ...]
    goal_calorie_adjustments: tuple[tuple[str, Decimal], ...]
    protein_g_per_kg: tuple[tuple[str, Decimal], ...]
    fat_calorie_fractions: tuple[tuple[str, Decimal], ...]

    def __post_init__(self) -> None:
        for field in ("activity_factors", "goal_calorie_adjustments", "protein_g_per_kg", "fat_calorie_fractions"):
            object.__setattr__(self, field, _pairs(getattr(self, field), field))
        for _, factor in self.activity_factors:
            if factor <= 0:
                raise ValueError("activity factors must be positive")
        for _, fraction in self.fat_calorie_fractions:
            if not Decimal("0") < fraction < Decimal("1"):
                raise ValueError("fat calorie fractions must be between zero and one")

    def value(self, field: str, key: str) -> Decimal:
        values = dict(getattr(self, field))
        try:
            return values[str(key).strip().lower()]
        except KeyError as error:
            raise NutritionConstructionError(f"missing target policy for {field}:{key}") from error


@dataclass(frozen=True)
class MealDistribution:
    category: str
    calorie_share: Decimal

    def __post_init__(self) -> None:
        if self.category not in MEAL_CATEGORIES:
            raise ValueError("unknown meal distribution category")
        if not Decimal("0") < self.calorie_share <= Decimal("1"):
            raise ValueError("meal calorie share must be within (0, 1]")


@dataclass(frozen=True)
class NutritionConstructionRequest:
    recommendation: RecommendationBlueprint
    profile: ImmutableUserProfile
    library: NutritionKnowledgeLibrary
    target_policy: NutritionTargetPolicy
    meal_distribution: tuple[MealDistribution, ...]
    dietary_restrictions: frozenset[str] = frozenset()
    ingredient_blacklist: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.recommendation.intent is not RecommendationIntent.NUTRITION:
            raise NutritionConstructionError("nutrition construction requires a nutrition recommendation")
        if self.recommendation.outcome is not RecommendationOutcome.RECOMMEND:
            raise NutritionConstructionError("nutrition recommendation is not approved")
        if not self.meal_distribution:
            raise NutritionConstructionError("meal distribution is required")
        categories = {slot.category for slot in self.meal_distribution}
        if not {"breakfast", "lunch", "dinner"}.issubset(categories):
            raise NutritionConstructionError("complete plans require breakfast, lunch, and dinner")
        if sum((slot.calorie_share for slot in self.meal_distribution), Decimal("0")) != Decimal("1"):
            raise NutritionConstructionError("meal calorie shares must total one")
        for field in ("dietary_restrictions", "ingredient_blacklist"):
            normalized = frozenset(str(value).strip().lower()
                                   for value in getattr(self, field) if str(value).strip())
            object.__setattr__(self, field, normalized)


@dataclass(frozen=True)
class ConstructedMeal:
    slot_index: int
    category: str
    target_macros: Nutrients
    candidate: MealCandidate
    selection_mode: str


@dataclass(frozen=True)
class NutritionPlanBlueprint:
    plan_id: str
    version: str
    recommendation_blueprint_id: str
    library_version: str
    catalog_version: str
    target_macros: Nutrients
    allocated_macros: Nutrients
    selected_macros: Nutrients
    meals: tuple[ConstructedMeal, ...]


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise NutritionConstructionError(f"verified profile {field} must be numeric") from error
    if result <= 0:
        raise NutritionConstructionError(f"verified profile {field} must be positive")
    return result


def _fact(profile: ImmutableUserProfile, field: str) -> Any:
    value = profile.facts.get(field)
    if value is None or str(value).strip() == "":
        raise NutritionConstructionError(f"verified profile {field} is required")
    return value


def calculate_target_macros(profile: ImmutableUserProfile, policy: NutritionTargetPolicy) -> Nutrients:
    """Calculate daily energy and macros from verified facts and explicit policy."""
    age = _decimal(_fact(profile, "age"), "age")
    height = _decimal(_fact(profile, "height"), "height")
    weight = _decimal(_fact(profile, "weight"), "weight")
    gender = str(_fact(profile, "gender")).strip().lower()
    activity = str(_fact(profile, "activityLevel")).strip().lower()
    goal = str(_fact(profile, "goal")).strip().lower()
    if gender not in {"male", "female", "m", "f"}:
        raise NutritionConstructionError("verified profile gender is unsupported")
    bmr_offset = Decimal("5") if gender in {"male", "m"} else Decimal("-161")
    bmr = Decimal("10") * weight + Decimal("6.25") * height - Decimal("5") * age + bmr_offset
    calories = bmr * policy.value("activity_factors", activity)
    calories += policy.value("goal_calorie_adjustments", goal)
    if calories <= 0:
        raise NutritionConstructionError("calorie target must be positive")
    protein = weight * policy.value("protein_g_per_kg", goal)
    fat = calories * policy.value("fat_calorie_fractions", goal) / Decimal("9")
    carbs = (calories - protein * Decimal("4") - fat * Decimal("9")) / Decimal("4")
    if protein <= 0 or fat <= 0 or carbs <= 0:
        raise NutritionConstructionError("target policy produces invalid macros")
    return Nutrients(protein, carbs, fat, calories)


def _allocate(targets: Nutrients, share: Decimal) -> Nutrients:
    return Nutrients(
        targets.protein_g * share,
        targets.carbs_g * share,
        targets.fat_g * share,
        targets.kcal * share,
    )


def _distance(candidate: MealCandidate, target: Nutrients) -> Decimal:
    return (abs(candidate.macros.kcal - target.kcal)
            + abs(candidate.macros.protein_g - target.protein_g) * Decimal("4")
            + abs(candidate.macros.carbs_g - target.carbs_g) * Decimal("4")
            + abs(candidate.macros.fat_g - target.fat_g) * Decimal("9"))


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list, frozenset, set)):
        return [_canonical(item) for item in sorted(value, key=repr)]
    if isinstance(value, Decimal):
        return str(value)
    return value


def _plan_id(request: NutritionConstructionRequest, targets: Nutrients,
             meals: tuple[ConstructedMeal, ...]) -> str:
    source = {
        "version": PLAN_CONSTRUCTION_VERSION,
        "recommendation": request.recommendation.blueprint_id,
        "library": request.library.version,
        "catalog": request.library.catalog_version,
        "profile": request.profile.facts,
        "targets": targets,
        "distribution": request.meal_distribution,
        "dietary": request.dietary_restrictions,
        "blacklist": request.ingredient_blacklist,
        "meals": tuple((meal.category, meal.candidate.meal_id, meal.selection_mode) for meal in meals),
    }
    payload = json.dumps(_canonical(source), sort_keys=True, separators=(",", ":"), default=str)
    return "nutrition_" + sha256(payload.encode("utf-8")).hexdigest()[:24]


class NutritionPlanConstructionEngine:
    """Construct complete, deterministic plans entirely from library candidates."""

    @staticmethod
    def construct(request: NutritionConstructionRequest) -> NutritionPlanBlueprint:
        targets = calculate_target_macros(request.profile, request.target_policy)
        used_meal_ids: set[str] = set()
        used_food_ids: set[str] = set()
        selected: list[ConstructedMeal] = []
        allocated = Nutrients.zero()
        delivered = Nutrients.zero()
        for index, slot in enumerate(request.meal_distribution):
            allocation = _allocate(targets, slot.calorie_share)
            allocated = allocated.plus(allocation)
            strict = MealSelectionQuery(
                slot.category,
                macro_bounds=MealMacroBounds(
                    kcal_min=allocation.kcal * Decimal("0.70"),
                    kcal_max=allocation.kcal * Decimal("1.30"),
                ),
                dietary_restrictions=request.dietary_restrictions,
                ingredient_blacklist=request.ingredient_blacklist,
            )
            candidates = MealSelectionEngine.select(request.library, strict)
            mode = "strict"
            if not candidates:
                candidates = MealSelectionEngine.select(
                    request.library,
                    MealSelectionQuery(
                        slot.category,
                        dietary_restrictions=request.dietary_restrictions,
                        ingredient_blacklist=request.ingredient_blacklist,
                    ))
                mode = "fallback"
            if not candidates:
                raise NutritionConstructionError(f"no library meal is available for {slot.category}")

            def rank(candidate: MealCandidate) -> tuple[int, int, Decimal, str]:
                foods = {ingredient.food_id for ingredient in candidate.ingredients}
                return (
                    1 if candidate.meal_id in used_meal_ids else 0,
                    len(foods & used_food_ids),
                    _distance(candidate, allocation),
                    candidate.meal_id,
                )

            chosen = min(candidates, key=rank)
            if chosen.meal_id in used_meal_ids:
                mode = "duplicate_required"
            used_meal_ids.add(chosen.meal_id)
            used_food_ids.update(item.food_id for item in chosen.ingredients)
            delivered = delivered.plus(chosen.macros)
            selected.append(ConstructedMeal(index, slot.category, allocation, chosen, mode))
        resolved = tuple(selected)
        return NutritionPlanBlueprint(
            plan_id=_plan_id(request, targets, resolved),
            version=PLAN_CONSTRUCTION_VERSION,
            recommendation_blueprint_id=request.recommendation.blueprint_id,
            library_version=request.library.version,
            catalog_version=request.library.catalog_version,
            target_macros=targets,
            allocated_macros=allocated,
            selected_macros=delivered,
            meals=resolved,
        )
