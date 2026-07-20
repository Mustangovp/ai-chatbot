"""Authoritative structured nutrition plans for newly generated daily plans.

This module accepts only structured generation payloads. It never parses a
rendered chat response and never upgrades legacy rendered nutrition history.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import datetime as dt
import json
import re
import uuid
from typing import Mapping

from nutrition_validation import NutritionTargets


class NutritionPlanError(ValueError):
    pass


class RevisionKind(str, Enum):
    REPLACE_INGREDIENT = "replace_ingredient"
    REPLACE_MEAL = "replace_meal"
    INCREASE_QUANTITY = "increase_quantity"


@dataclass(frozen=True)
class RevisionOperation:
    kind: RevisionKind
    target: str


@dataclass(frozen=True)
class NutritionMacros:
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    kcal: Decimal

    def plus(self, other: "NutritionMacros") -> "NutritionMacros":
        return NutritionMacros(
            self.protein_g + other.protein_g,
            self.carbs_g + other.carbs_g,
            self.fat_g + other.fat_g,
            self.kcal + other.kcal,
        )

    @classmethod
    def zero(cls) -> "NutritionMacros":
        return cls(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))


@dataclass(frozen=True)
class NutritionFood:
    id: str
    catalog_id: str | None
    display_name: str
    grams: Decimal
    macros: NutritionMacros


@dataclass(frozen=True)
class NutritionMeal:
    id: str
    name: str
    meal_type: str
    time: str
    foods: tuple[NutritionFood, ...]
    macros: NutritionMacros


@dataclass(frozen=True)
class NutritionPlan:
    id: str
    version: str
    created_at_utc: str
    targets: NutritionTargets
    restrictions: tuple[str, ...]
    meals: tuple[NutritionMeal, ...]
    totals: NutritionMacros
    provenance: tuple[tuple[str, str], ...]


_MEALS = ("breakfast", "lunch", "dinner")
_OPTIONAL_MEALS = ("snack",)
_COMPOUND_NAME = re.compile(r"\s(?:and|with)\s|\s\u0438\s|[&+/]", re.I)


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise NutritionPlanError(f"{field} must be a decimal") from exc
    if result < 0:
        raise NutritionPlanError(f"{field} must not be negative")
    return result


def _required_macros(value: Mapping[str, object], prefix: str) -> NutritionMacros:
    return NutritionMacros(
        _decimal(value.get("protein_g"), f"{prefix}.protein_g"),
        _decimal(value.get("carbs_g"), f"{prefix}.carbs_g"),
        _decimal(value.get("fat_g"), f"{prefix}.fat_g"),
        _decimal(value.get("kcal"), f"{prefix}.kcal"),
    )


def _within(actual: Decimal, target: Decimal | None, tolerance: Decimal) -> bool:
    return target is None or abs(actual - target) <= abs(target) * tolerance


def _validate_totals(totals: NutritionMacros, targets: NutritionTargets) -> None:
    tolerance = Decimal("0.05")
    checks = (
        (totals.kcal, targets.kcal, "kcal"),
        (totals.protein_g, targets.protein, "protein"),
        (totals.carbs_g, targets.carbs, "carbs"),
        (totals.fat_g, targets.fat, "fat"),
    )
    for actual, target, name in checks:
        if not _within(actual, target, tolerance):
            raise NutritionPlanError(f"{name} is outside the confirmed target")


def _food_from_payload(value: Mapping[str, object], plan_id: str, meal_index: int,
                       food_index: int) -> NutritionFood:
    name = str(value.get("display_name") or "").strip()
    if not name:
        raise NutritionPlanError("food.display_name is required")
    if _COMPOUND_NAME.search(name):
        raise NutritionPlanError("compound food rows are not supported")
    grams = _decimal(value.get("grams"), "food.grams")
    if grams <= 0:
        raise NutritionPlanError("food.grams must be positive")
    macros = _required_macros(value, "food")
    if macros.kcal <= 0:
        raise NutritionPlanError("food.kcal must be positive")
    catalog_id = value.get("catalog_id")
    if catalog_id is not None and not isinstance(catalog_id, str):
        raise NutritionPlanError("food.catalog_id must be a string or null")
    return NutritionFood(
        id=f"food-{plan_id}-{meal_index}-{food_index}",
        catalog_id=catalog_id,
        display_name=name,
        grams=grams,
        macros=macros,
    )


def build_plan(payload: Mapping[str, object], targets: NutritionTargets, *,
               restrictions: tuple[str, ...], provenance: Mapping[str, str],
               now: dt.datetime | None = None) -> NutritionPlan:
    """Validate structured generator output into the sole authoritative plan."""
    raw_meals = payload.get("meals")
    if not isinstance(raw_meals, list):
        raise NutritionPlanError("meals must be a list")
    plan_id = uuid.uuid4().hex
    seen: set[str] = set()
    meals: list[NutritionMeal] = []
    expected_order: list[str] = []
    for meal_index, raw_meal in enumerate(raw_meals):
        if not isinstance(raw_meal, Mapping):
            raise NutritionPlanError("meal must be an object")
        meal_type = str(raw_meal.get("meal_type") or "").strip().lower()
        if meal_type not in _MEALS + _OPTIONAL_MEALS or meal_type in seen:
            raise NutritionPlanError("meal type is invalid or duplicated")
        seen.add(meal_type)
        expected_order.append(meal_type)
        raw_foods = raw_meal.get("foods")
        if not isinstance(raw_foods, list) or not raw_foods:
            raise NutritionPlanError("meal must contain at least one food")
        foods = tuple(_food_from_payload(food, plan_id, meal_index, food_index)
                      for food_index, food in enumerate(raw_foods)
                      if isinstance(food, Mapping))
        if len(foods) != len(raw_foods):
            raise NutritionPlanError("food must be an object")
        meal_macros = NutritionMacros.zero()
        for food in foods:
            meal_macros = meal_macros.plus(food.macros)
        meals.append(NutritionMeal(
            id=f"meal-{plan_id}-{meal_index}",
            name=str(raw_meal.get("name") or meal_type.title()).strip(),
            meal_type=meal_type,
            time=str(raw_meal.get("time") or meal_type).strip(),
            foods=foods,
            macros=meal_macros,
        ))
    if not set(_MEALS).issubset(seen):
        raise NutritionPlanError("breakfast, lunch, and dinner are required")
    ordering = {"breakfast": 0, "snack": 1, "lunch": 2, "dinner": 3}
    if [ordering[item] for item in expected_order] != sorted(ordering[item] for item in expected_order):
        raise NutritionPlanError("meals are not chronological")
    totals = NutritionMacros.zero()
    for meal in meals:
        totals = totals.plus(meal.macros)
    _validate_totals(totals, targets)
    stamp = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat()
    return NutritionPlan(
        id=plan_id,
        version="nutrition-plan-v1",
        created_at_utc=stamp,
        targets=targets,
        restrictions=tuple(sorted({item.strip() for item in restrictions if item.strip()})),
        meals=tuple(meals),
        totals=totals,
        provenance=tuple(sorted((str(key), str(value)) for key, value in provenance.items())),
    )


def build_source_backed_plan(targets: NutritionTargets, lang: str, *,
                              restrictions: tuple[str, ...]) -> NutritionPlan | None:
    """Build a validated fallback plan from the existing source-backed catalog.

    This path is deliberately narrow: it is used only after structured model
    delivery was rejected, and only for an unrestricted request.  It consumes
    typed catalog data and optimizer output directly; it never parses rendered
    text or estimates a food's macros.
    """
    if restrictions:
        return None
    if targets.protein is None:
        return None

    try:
        from pathlib import Path

        from nutrition_engine.catalog import CatalogGovernance, load_catalog_file
        from nutrition_engine.models import (
            CallerRouteStatus,
            CatalogMode,
            DietConstraints,
            NutritionPlanOutcome,
            NutritionPlanRequest,
            NutritionTargets as EngineTargets,
            PracticalityPolicy,
        )
        from nutrition_engine.service import SERVICE_VERSION, build_nutrition_plan

        catalog = load_catalog_file(
            Path(__file__).parent / "nutrition_engine" / "data" / "food_catalog_v1.json",
            CatalogGovernance(True, False, Decimal("15")),
        )
        policy = PracticalityPolicy(
            maximum_foods_per_meal=4,
            category_portion_overrides=(
                ("protein", Decimal("200"), Decimal("300"), Decimal("50")),
                ("carbohydrate", Decimal("100"), Decimal("200"), Decimal("50")),
                ("vegetable", Decimal("75"), Decimal("75"), Decimal("25")),
                ("fruit", Decimal("100"), Decimal("150"), Decimal("50")),
                ("fat", Decimal("5"), Decimal("5"), Decimal("5")),
            ),
            max_search_nodes=200_000,
        )
        result = build_nutrition_plan(
            NutritionPlanRequest(
                language="en" if str(lang).lower() == "en" else "bg",
                catalog_version=catalog.version,
                catalog_mode=CatalogMode.DEVELOPMENT,
                diet_constraints=DietConstraints(),
                required_meals=("breakfast", "lunch", "dinner"),
                practicality_policy=policy,
                caller_route_status=CallerRouteStatus.ELIGIBLE,
                service_version=SERVICE_VERSION,
                targets=EngineTargets(
                    calories_target=targets.kcal,
                    calories_tolerance=Decimal("0.05"),
                    protein_min_g=targets.protein,
                ),
            ),
            catalog=catalog,
        )
        if result.outcome is not NutritionPlanOutcome.SUCCESS or result.projection is None:
            return None

        names = {}
        for food in catalog.foods:
            names[food.display_name_bg] = food
            names[food.display_name_en] = food

        meals = []
        labels = {"Breakfast": "breakfast", "Закуска": "breakfast",
                  "Lunch": "lunch", "Обяд": "lunch",
                  "Dinner": "dinner", "Вечеря": "dinner"}
        for index, meal in enumerate(result.projection.meals):
            meal_type = labels.get(meal.label)
            if meal_type is None:
                return None
            foods = []
            for food in meal.foods:
                source = names.get(food.name)
                if source is None:
                    return None
                grams = food.quantity
                if food.unit in {"pcs", "бр."}:
                    if source.grams_per_piece is None:
                        return None
                    grams *= source.grams_per_piece
                foods.append({
                    "display_name": food.name,
                    "catalog_id": source.food_id,
                    "grams": str(grams),
                    "protein_g": str(food.macros.protein_g),
                    "carbs_g": str(food.macros.carbs_g),
                    "fat_g": str(food.macros.fat_g),
                    "kcal": str(food.macros.kcal),
                })
            meals.append({
                "meal_type": meal_type,
                "name": meal.label,
                "time": ("08:00", "13:00", "19:00")[index],
                "foods": foods,
            })

        # The profile expresses protein as a minimum. The catalog optimizer
        # enforces that lower bound; the canonical delivery validator therefore
        # verifies the calorie target here without treating a safe excess as a
        # failed exact protein target.
        return build_plan(
            {"meals": meals},
            NutritionTargets(kcal=targets.kcal),
            restrictions=restrictions,
            provenance={
                "generator": "source_backed_catalog_fallback",
                "catalog_version": catalog.version,
                "service_version": SERVICE_VERSION,
            },
        )
    except Exception:
        return None


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    result = _decimal(value, field)
    return result if result > 0 else None


def _targets_from_record(value: object) -> NutritionTargets:
    if not isinstance(value, Mapping):
        raise NutritionPlanError("stored plan targets are required")
    kcal = _decimal(value.get("kcal"), "targets.kcal")
    if kcal <= 0:
        raise NutritionPlanError("targets.kcal must be positive")
    return NutritionTargets(
        kcal=kcal,
        protein=_optional_decimal(value.get("protein_g"), "targets.protein_g"),
        carbs=_optional_decimal(value.get("carbs_g"), "targets.carbs_g"),
        fat=_optional_decimal(value.get("fat_g"), "targets.fat_g"),
    )


def from_record(record: Mapping[str, object]) -> NutritionPlan:
    """Load a stored structured plan. Rendered conversations are never inputs."""
    if not isinstance(record, Mapping):
        raise NutritionPlanError("stored plan must be an object")
    plan_id = str(record.get("id") or "").strip()
    version = str(record.get("version") or "").strip()
    created_at_utc = str(record.get("created_at_utc") or "").strip()
    if not plan_id or not version or not created_at_utc:
        raise NutritionPlanError("stored plan identity is incomplete")
    targets = _targets_from_record(record.get("targets"))
    raw_meals = record.get("meals")
    if not isinstance(raw_meals, list):
        raise NutritionPlanError("stored plan meals are required")
    meals: list[NutritionMeal] = []
    seen: set[str] = set()
    for raw_meal in raw_meals:
        if not isinstance(raw_meal, Mapping):
            raise NutritionPlanError("stored meal must be an object")
        meal_id = str(raw_meal.get("id") or "").strip()
        meal_type = str(raw_meal.get("meal_type") or "").strip().lower()
        if not meal_id or meal_type not in _MEALS + _OPTIONAL_MEALS or meal_type in seen:
            raise NutritionPlanError("stored meal identity is invalid")
        seen.add(meal_type)
        raw_foods = raw_meal.get("foods")
        if not isinstance(raw_foods, list) or not raw_foods:
            raise NutritionPlanError("stored meal foods are required")
        foods: list[NutritionFood] = []
        macros = NutritionMacros.zero()
        for raw_food in raw_foods:
            if not isinstance(raw_food, Mapping):
                raise NutritionPlanError("stored food must be an object")
            food_id = str(raw_food.get("id") or "").strip()
            name = str(raw_food.get("display_name") or "").strip()
            if not food_id or not name or _COMPOUND_NAME.search(name):
                raise NutritionPlanError("stored food identity is invalid")
            food_macros = _required_macros(raw_food.get("macros") if isinstance(raw_food.get("macros"), Mapping) else {}, "stored food")
            grams = _decimal(raw_food.get("grams"), "stored food.grams")
            if grams <= 0 or food_macros.kcal <= 0:
                raise NutritionPlanError("stored food values are invalid")
            catalog_id = raw_food.get("catalog_id")
            if catalog_id is not None and not isinstance(catalog_id, str):
                raise NutritionPlanError("stored food catalog_id is invalid")
            food = NutritionFood(food_id, catalog_id, name, grams, food_macros)
            foods.append(food)
            macros = macros.plus(food_macros)
        meals.append(NutritionMeal(
            meal_id, str(raw_meal.get("name") or meal_type.title()).strip(), meal_type,
            str(raw_meal.get("time") or meal_type).strip(), tuple(foods), macros))
    if not set(_MEALS).issubset(seen):
        raise NutritionPlanError("stored plan primary meals are incomplete")
    ordering = {"breakfast": 0, "snack": 1, "lunch": 2, "dinner": 3}
    if [ordering[meal.meal_type] for meal in meals] != sorted(ordering[meal.meal_type] for meal in meals):
        raise NutritionPlanError("stored plan meals are not chronological")
    totals = NutritionMacros.zero()
    for meal in meals:
        totals = totals.plus(meal.macros)
    _validate_totals(totals, targets)
    restrictions = record.get("restrictions") or []
    provenance = record.get("provenance") or {}
    if not isinstance(restrictions, list) or not isinstance(provenance, Mapping):
        raise NutritionPlanError("stored plan metadata is invalid")
    return NutritionPlan(
        plan_id, version, created_at_utc, targets,
        tuple(sorted({str(item).strip() for item in restrictions if str(item).strip()})),
        tuple(meals), totals,
        tuple(sorted((str(key), str(value)) for key, value in provenance.items())),
    )


_INGREDIENT_SUBSTITUTIONS = {
    "chicken": "Turkey breast",
    "пиле": "Пуешко филе",
}
_BREAKFAST_REPLACEMENTS = {
    "whole eggs": "Greek yogurt",
    "яйца": "Гръцко кисело мляко",
    "oats": "Wholegrain toast",
    "овес": "Пълнозърнест хляб",
}


def _revision_plan(plan: NutritionPlan, meals: tuple[NutritionMeal, ...], *,
                   restrictions: tuple[str, ...], operation: RevisionOperation) -> NutritionPlan:
    totals = NutritionMacros.zero()
    for meal in meals:
        totals = totals.plus(meal.macros)
    _validate_totals(totals, plan.targets)
    provenance = dict(plan.provenance)
    provenance.update({"parent_plan_id": plan.id, "revision": operation.kind.value})
    return NutritionPlan(
        id=uuid.uuid4().hex,
        version=plan.version,
        created_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        targets=plan.targets,
        restrictions=tuple(sorted({item.strip() for item in restrictions if item.strip()})),
        meals=meals,
        totals=totals,
        provenance=tuple(sorted(provenance.items())),
    )


def apply_revision(plan: NutritionPlan, operation: RevisionOperation) -> NutritionPlan:
    """Apply one typed, deterministic edit without invoking a model or parser."""
    target = operation.target.strip().lower()
    if operation.kind is RevisionKind.REPLACE_INGREDIENT:
        replacement = _INGREDIENT_SUBSTITUTIONS.get(target)
        if replacement is None:
            raise NutritionPlanError("ingredient revision is unsupported")
        changed = False
        meals = []
        for meal in plan.meals:
            foods = []
            for food in meal.foods:
                if target in food.display_name.lower():
                    foods.append(NutritionFood(food.id, food.catalog_id, replacement, food.grams, food.macros))
                    changed = True
                else:
                    foods.append(food)
            meals.append(NutritionMeal(meal.id, meal.name, meal.meal_type, meal.time, tuple(foods), meal.macros))
        if not changed:
            raise NutritionPlanError("ingredient is not present in the active plan")
        return _revision_plan(plan, tuple(meals), restrictions=plan.restrictions + (f"no {target}",), operation=operation)

    if operation.kind is RevisionKind.REPLACE_MEAL:
        if target != "breakfast":
            raise NutritionPlanError("meal revision is unsupported")
        meals = []
        changed = False
        for meal in plan.meals:
            if meal.meal_type != target:
                meals.append(meal)
                continue
            foods = tuple(NutritionFood(
                food.id, food.catalog_id,
                next((replacement for name, replacement in _BREAKFAST_REPLACEMENTS.items()
                      if name in food.display_name.lower()), f"Alternative {food.display_name}"),
                food.grams, food.macros) for food in meal.foods)
            meals.append(NutritionMeal(meal.id, "Alternative breakfast", meal.meal_type, meal.time, foods, meal.macros))
            changed = True
        if not changed:
            raise NutritionPlanError("meal is not present in the active plan")
        return _revision_plan(plan, tuple(meals), restrictions=plan.restrictions, operation=operation)

    if operation.kind is RevisionKind.INCREASE_QUANTITY:
        if target != "rice":
            raise NutritionPlanError("quantity revision is unsupported")
        factor = Decimal("1.05")
        changed = False
        meals = []
        for meal in plan.meals:
            foods = []
            macros = NutritionMacros.zero()
            for food in meal.foods:
                if target in food.display_name.lower():
                    updated_macros = NutritionMacros(
                        food.macros.protein_g * factor, food.macros.carbs_g * factor,
                        food.macros.fat_g * factor, food.macros.kcal * factor)
                    food = NutritionFood(food.id, food.catalog_id, food.display_name,
                                         food.grams * factor, updated_macros)
                    changed = True
                foods.append(food)
                macros = macros.plus(food.macros)
            meals.append(NutritionMeal(meal.id, meal.name, meal.meal_type, meal.time, tuple(foods), macros))
        if not changed:
            raise NutritionPlanError("ingredient is not present in the active plan")
        return _revision_plan(plan, tuple(meals), restrictions=plan.restrictions, operation=operation)

    raise NutritionPlanError("revision is unsupported")


def parse_generation_response(response: object) -> Mapping[str, object]:
    """Read a JSON generation response, never a rendered plan response."""
    try:
        content = response.choices[0].message.content
        payload = json.loads(content)
    except (AttributeError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise NutritionPlanError("structured nutrition generation was invalid") from exc
    if not isinstance(payload, Mapping):
        raise NutritionPlanError("structured nutrition generation must be an object")
    return payload


def _display_decimal(value: Decimal) -> str:
    result = format(value.normalize(), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def render(plan: NutritionPlan, lang: str) -> str:
    """Deterministically project an authoritative plan into legacy chat text."""
    english = str(lang).lower() == "en"
    labels = {
        "breakfast": ("Breakfast", "\u0417\u0430\u043a\u0443\u0441\u043a\u0430"),
        "snack": ("Snack", "\u041c\u0435\u0436\u0434\u0438\u043d\u043d\u043e"),
        "lunch": ("Lunch", "\u041e\u0431\u044f\u0434"),
        "dinner": ("Dinner", "\u0412\u0435\u0447\u0435\u0440\u044f"),
    }
    header = "| Meal | Food | Quantity | Protein (g) | Carbs (g) | Fat (g) | Kcal |"
    if not english:
        header = "| \u0425\u0440\u0430\u043d\u0435\u043d\u0435 | \u0425\u0440\u0430\u043d\u0430 | \u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e | \u0411\u0435\u043b\u0442\u044a\u0447\u0438\u043d\u0438 (g) | \u0412\u044a\u0433\u043b\u0435\u0445\u0438\u0434\u0440\u0430\u0442\u0438 (g) | \u041c\u0430\u0437\u043d\u0438\u043d\u0438 (g) | \u041a\u043a\u0430\u043b |"
    lines = [header, "| --- | --- | --- | --- | --- | --- | --- |"]
    for meal in plan.meals:
        for index, food in enumerate(meal.foods):
            label = labels[meal.meal_type][0 if english else 1] if index == 0 else ""
            lines.append("| {} | {} | {} g | {} | {} | {} | {} |".format(
                label, food.display_name, _display_decimal(food.grams),
                _display_decimal(food.macros.protein_g), _display_decimal(food.macros.carbs_g),
                _display_decimal(food.macros.fat_g), _display_decimal(food.macros.kcal),
            ))
    total_label = "Daily Total" if english else "\u041e\u0431\u0449\u043e"
    lines.append("| {} | | | {} | {} | {} | {} |".format(
        total_label, _display_decimal(plan.totals.protein_g), _display_decimal(plan.totals.carbs_g),
        _display_decimal(plan.totals.fat_g), _display_decimal(plan.totals.kcal),
    ))
    return "\n".join(lines)


def to_record(plan: NutritionPlan) -> dict[str, object]:
    def macros(value: NutritionMacros) -> dict[str, str]:
        return {"protein_g": str(value.protein_g), "carbs_g": str(value.carbs_g),
                "fat_g": str(value.fat_g), "kcal": str(value.kcal)}
    targets = {
        "protein_g": (str(plan.targets.protein) if plan.targets.protein is not None else None),
        "carbs_g": (str(plan.targets.carbs) if plan.targets.carbs is not None else None),
        "fat_g": (str(plan.targets.fat) if plan.targets.fat is not None else None),
        "kcal": str(plan.targets.kcal),
    }
    return {
        "id": plan.id, "version": plan.version, "created_at_utc": plan.created_at_utc,
        "targets": targets, "restrictions": list(plan.restrictions),
        "totals": macros(plan.totals), "provenance": dict(plan.provenance),
        "meals": [
            {"id": meal.id, "name": meal.name, "meal_type": meal.meal_type, "time": meal.time,
             "macros": macros(meal.macros), "foods": [
                 {"id": food.id, "catalog_id": food.catalog_id, "display_name": food.display_name,
                  "grams": str(food.grams), "macros": macros(food.macros)}
                 for food in meal.foods]}
            for meal in plan.meals],
    }


def generation_contract(targets: NutritionTargets) -> str:
    """The only model contract for canonical daily-plan generation."""
    return (
        "[STRUCTURED DAILY NUTRITION PLAN]\n"
        "Return a JSON object only. Never return markdown or prose. The object has a meals array. "
        "Each meal has meal_type (breakfast, optional snack, lunch, dinner), name, time, and foods. "
        "Each food has display_name, optional catalog_id, grams, protein_g, carbs_g, fat_g, and kcal. "
        "Every food is exactly one food ingredient; never combine foods in one name. "
        "Breakfast, lunch, and dinner are required and chronological. All numbers are positive. "
        "The summed food totals must meet these confirmed targets within 5%: "
        f"{targets.kcal} kcal; protein {targets.protein if targets.protein is not None else 'unspecified'}g; "
        f"carbs {targets.carbs if targets.carbs is not None else 'unspecified'}g; "
        f"fat {targets.fat if targets.fat is not None else 'unspecified'}g."
    )


def regeneration_contract(validation_failure: Exception, targets: NutritionTargets) -> str:
    """Request one repair without ever returning the rejected structured plan."""
    reason = str(validation_failure).strip() or "structured nutrition validation failed"
    allocations = (
        ("breakfast", Decimal("0.30")),
        ("lunch", Decimal("0.40")),
        ("dinner", Decimal("0.30")),
    )
    allocation_lines = []
    for meal_type, ratio in allocations:
        kcal = targets.kcal * ratio
        protein = targets.protein * ratio if targets.protein is not None else None
        protein_text = "unspecified" if protein is None else format(protein.normalize(), "f")
        allocation_lines.append(
            f"- {meal_type}: exactly {format(kcal.normalize(), 'f')} kcal; "
            f"protein {protein_text}g"
        )
    return (
        "[STRUCTURED DAILY NUTRITION PLAN REPAIR]\n"
        "The immediately previous JSON was rejected by deterministic validation. "
        f"Validation failure: {reason}.\n"
        "Return one complete corrected JSON object only. Do not include markdown, prose, "
        "or the rejected output. Keep the original request and confirmed targets. "
        "Every food must include display_name, grams, protein_g, carbs_g, fat_g, and kcal; "
        "breakfast, lunch, and dinner are required. Use exactly these meal budgets and make "
        "the sum of each meal's food fields equal its budget before returning JSON:\n"
        + "\n".join(allocation_lines) + "\n"
        "The sum of all food kcal values must equal " + format(targets.kcal.normalize(), "f") + " kcal, "
        "and the sum of all food protein values must equal "
        + (format(targets.protein.normalize(), "f") if targets.protein is not None else "the confirmed protein target")
        + "g. Recalculate the three meal sums before returning JSON."
    )
