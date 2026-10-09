"""Authoritative structured nutrition plans for newly generated daily plans.

This module accepts only structured generation payloads. It never parses a
rendered chat response and never upgrades legacy rendered nutrition history.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from enum import Enum
import datetime as dt
import json
import re
import uuid
from typing import Mapping, Sequence

from nutrition_validation import NutritionTargets
from nutrition_constraints import (
    RestrictionSafetyError, recorded_profile_restrictions, validate_foods,
)


class NutritionPlanError(ValueError):
    pass


class NutritionRestrictionError(NutritionPlanError):
    """The existing plan authority cannot establish food suitability."""


def _validate_restrictions(meals, restrictions):
    try:
        validate_foods((food for meal in meals for food in meal.foods), restrictions)
    except RestrictionSafetyError as error:
        raise NutritionRestrictionError(str(error)) from error


def restriction_blocked_message(lang):
    return ("I can't safely deliver this nutrition plan because its foods could not be verified against your recorded restrictions. Please clarify the restriction or food identity."
            if str(lang).lower() == "en" else
            "Не мога безопасно да предоставя този хранителен план, защото храните не са проверени спрямо записаните ограничения. Моля, уточни ограничението или храната.")


class MeasurementState(str, Enum):
    RAW = "raw"
    COOKED = "cooked"
    DRAINED = "drained"
    READY_TO_EAT = "ready_to_eat"
    AS_SERVED = "as_served"
    PACKAGE_WEIGHT = "package_weight"


class PlanTargetStatus(str, Enum):
    EXACT = "EXACT"
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    OUTSIDE_TOLERANCE = "OUTSIDE_TOLERANCE"


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
    food_id: str | None = None
    measurement_state: MeasurementState | None = None


@dataclass(frozen=True)
class NutritionMeal:
    id: str
    name: str
    meal_type: str
    time: str
    foods: tuple[NutritionFood, ...]
    macros: NutritionMacros
    preparation_type: str | None = None


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
    target_status: PlanTargetStatus = PlanTargetStatus.EXACT


@dataclass(frozen=True)
class RecentNutritionContext:
    """Small, non-authoritative variety context reconstructed from saved plans."""
    recent_plan_count: int = 0
    recent_meals: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.recent_meals)


def recent_nutrition_context(records: Sequence[Mapping[str, object]] | object,
                             *, maximum_history_depth: int = 3) -> RecentNutritionContext:
    if (not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray))
            or not 0 <= maximum_history_depth <= 6):
        return RecentNutritionContext()
    meals: list[tuple[str, tuple[str, ...]]] = []
    valid_plans = 0
    for record in records[:maximum_history_depth]:
        raw = record.get("plan") if isinstance(record, Mapping) else None
        try:
            plan = from_record(raw) if isinstance(raw, Mapping) else None
        except (TypeError, ValueError, NutritionPlanError):
            continue
        if plan is None:
            continue
        valid_plans += 1
        for meal in plan.meals:
            labels = tuple(food.display_name for food in meal.foods if food.display_name)[:5]
            if labels:
                meals.append((meal.meal_type, labels))
    return RecentNutritionContext(valid_plans, tuple(meals))


# These markers record only decisions already fixed by the validated plan. They
# are intentionally not inferred later from profile text, Persona, or HSE.
_ARG_ENERGY_TARGET_PROVENANCE = "nutrition_decision.energy_target"
_ARG_MACRO_DISTRIBUTION_PROVENANCE = "nutrition_decision.macro_distribution"
_ARG_CONFIRMED = "confirmed"


_MEALS = ("breakfast", "lunch", "dinner")
_OPTIONAL_MEALS = ("snack",)
_COMPOUND_NAME = re.compile(r"\s(?:and|with)\s|\s\u0438\s|[&+/]", re.I)
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_LATIN = re.compile(r"[A-Za-z]")
_MEASUREMENT_REQUIRED_FOOD_IDS = frozenset({
    "rice", "quinoa", "pasta", "oats", "lentils", "chickpeas", "chicken",
    "turkey", "salmon", "tuna", "lean_beef", "potatoes", "prawns", "shrimp", "cod", "pork",
})
_MEASUREMENT_REQUIRED_FRAGMENTS = ("frozen", "chicken", "turkey", "beef", "pork", "lamb", "fish", "salmon", "tuna", "cod", "prawn", "shrimp")


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


def target_status(totals: NutritionMacros, targets: NutritionTargets) -> PlanTargetStatus:
    """Classify the current approved five-percent nutrition target contract."""
    tolerance = Decimal("0.05")
    checks = (
        (totals.kcal, targets.kcal, "kcal"),
        (totals.protein_g, targets.protein, "protein"),
        (totals.carbs_g, targets.carbs, "carbs"),
        (totals.fat_g, targets.fat, "fat"),
    )
    if all(target is None or actual == target for actual, target, _ in checks):
        return PlanTargetStatus.EXACT
    for actual, target, _ in checks:
        if not _within(actual, target, tolerance):
            return PlanTargetStatus.OUTSIDE_TOLERANCE
    return PlanTargetStatus.WITHIN_TOLERANCE


def _validate_totals(totals: NutritionMacros, targets: NutritionTargets) -> PlanTargetStatus:
    status = target_status(totals, targets)
    if status is PlanTargetStatus.OUTSIDE_TOLERANCE:
        checks = (
            (totals.kcal, targets.kcal, "kcal"),
            (totals.protein_g, targets.protein, "protein"),
            (totals.carbs_g, targets.carbs, "carbs"),
            (totals.fat_g, targets.fat, "fat"),
        )
        for actual, target, name in checks:
            if not _within(actual, target, Decimal("0.05")):
                raise NutritionPlanError(f"{name} is outside the confirmed target")
    return status


def _canonical_food_id(name: str, supplied: object) -> str:
    if supplied is not None:
        if not isinstance(supplied, str) or not supplied.strip():
            raise NutritionPlanError("food.food_id must be a non-empty string")
        return supplied.strip()
    # Legacy structured deliveries did not carry a food ID. Normalize once at
    # the plan boundary so recipe matching never scans rendered card text.
    from recipe_engine.recipe_matcher import ingredient_key
    return ingredient_key(name)


def _measurement_state(value: object, food_id: str, *, require_for_ambiguous: bool = True) -> MeasurementState | None:
    if value is None or str(value).strip() == "":
        requires_state = food_id in _MEASUREMENT_REQUIRED_FOOD_IDS or any(
            fragment in food_id for fragment in _MEASUREMENT_REQUIRED_FRAGMENTS
        )
        if require_for_ambiguous and requires_state:
            raise NutritionPlanError(f"food.measurement_state is required for {food_id}")
        return None
    try:
        return MeasurementState(str(value).strip())
    except ValueError as exc:
        raise NutritionPlanError("food.measurement_state is invalid") from exc


def _food_from_payload(value: Mapping[str, object], plan_id: str, meal_index: int,
                       food_index: int, language: str | None) -> NutritionFood:
    name = str(value.get("display_name") or "").strip()
    if not name:
        raise NutritionPlanError("food.display_name is required")
    if _COMPOUND_NAME.search(name):
        raise NutritionPlanError("compound food rows are not supported")
    if language == "bg" and _LATIN.search(name):
        raise NutritionPlanError("food.display_name must use Bulgarian when Bulgarian delivery is requested")
    if language == "en" and _CYRILLIC.search(name):
        raise NutritionPlanError("food.display_name must use English when English delivery is requested")
    grams = _decimal(value.get("grams"), "food.grams")
    if grams <= 0:
        raise NutritionPlanError("food.grams must be positive")
    macros = _required_macros(value, "food")
    if macros.kcal <= 0:
        raise NutritionPlanError("food.kcal must be positive")
    catalog_id = value.get("catalog_id")
    if catalog_id is not None and not isinstance(catalog_id, str):
        raise NutritionPlanError("food.catalog_id must be a string or null")
    food_id = _canonical_food_id(name, value.get("food_id"))
    return NutritionFood(
        id=f"food-{plan_id}-{meal_index}-{food_index}",
        catalog_id=catalog_id,
        display_name=name,
        grams=grams,
        macros=macros,
        food_id=food_id,
        measurement_state=_measurement_state(value.get("measurement_state"), food_id),
    )


def build_plan(payload: Mapping[str, object], targets: NutritionTargets, *,
               restrictions: tuple[str, ...], provenance: Mapping[str, str],
               now: dt.datetime | None = None, language: str | None = None) -> NutritionPlan:
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
        foods = tuple(_food_from_payload(food, plan_id, meal_index, food_index, language)
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
            preparation_type="assembly" if meal_type in _MEALS else None,
        ))
    if not set(_MEALS).issubset(seen):
        raise NutritionPlanError("breakfast, lunch, and dinner are required")
    ordering = {"breakfast": 0, "snack": 1, "lunch": 2, "dinner": 3}
    if [ordering[item] for item in expected_order] != sorted(ordering[item] for item in expected_order):
        raise NutritionPlanError("meals are not chronological")
    totals = NutritionMacros.zero()
    for meal in meals:
        totals = totals.plus(meal.macros)
    status = _validate_totals(totals, targets)
    stamp = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat()
    plan_provenance = dict(provenance)
    # The confirmed target is an authoritative input to every validated plan.
    # Record that decision once, rather than asking a presentation layer to
    # reconstruct it from profile metadata after delivery.
    plan_provenance.setdefault(_ARG_ENERGY_TARGET_PROVENANCE, _ARG_CONFIRMED)
    if all(value is not None for value in (targets.protein, targets.carbs, targets.fat)):
        plan_provenance.setdefault(_ARG_MACRO_DISTRIBUTION_PROVENANCE, _ARG_CONFIRMED)
    _validate_restrictions(meals, restrictions)
    return NutritionPlan(
        id=plan_id,
        version="nutrition-plan-v1",
        created_at_utc=stamp,
        targets=targets,
        restrictions=tuple(sorted({item.strip() for item in restrictions if item.strip()})),
        meals=tuple(meals),
        totals=totals,
        provenance=tuple(sorted((str(key), str(value)) for key, value in plan_provenance.items())),
        target_status=status,
    )


def build_source_backed_plan(targets: NutritionTargets, lang: str, *,
                              restrictions: tuple[str, ...],
                              profile: Mapping[str, object] | None = None,
                              recent_context: RecentNutritionContext | None = None) -> NutritionPlan | None:
    """Try at most thirty-four rich catalog alternatives, then the prior fallback.

    Only ingredient selection changes. Each attempt uses the same existing
    service, optimizer parameters, portion bounds, and final NutritionPlan gate.
    Restrictions retain the prior fail-closed fallback boundary.
    """
    if restrictions:
        return None
    try:
        from pathlib import Path
        from nutrition_engine.catalog import CatalogGovernance, load_catalog_file

        catalog = load_catalog_file(
            Path(__file__).parent / "nutrition_engine" / "data" / "food_catalog_v1.json",
            CatalogGovernance(True, False, Decimal("15")),
        )
        for candidate in _fallback_catalogs(catalog, _selection_goal(profile), recent_context):
            plan = _build_source_backed_candidate(targets, lang, restrictions=restrictions, catalog=candidate)
            if plan is not None:
                return plan
        return None
    except Exception:
        return None


def _fallback_catalogs(catalog, goal, recent_context):
    from nutrition_engine.catalog import Catalog

    recent_names = {name for _, names in (recent_context.recent_meals if recent_context else ()) for name in names}
    recent_ids = {food.food_id for food in catalog.foods
                  if food.display_name_en in recent_names or food.display_name_bg in recent_names
                  or _catalog_display_name(food, "bg") in recent_names}

    def rank(food):
        preference = Decimal("0")
        if goal == "fat_loss":
            preference = (-food.protein_per_100g / food.kcal_per_100g
                          if food.category == "protein" else food.kcal_per_100g)
        elif goal == "muscle_gain" and food.category in {"protein", "carbohydrate", "fruit"}:
            preference = -food.kcal_per_100g
        elif goal in {"strength", "endurance"}:
            if food.category == "protein":
                preference = -food.protein_per_100g
            elif food.category == "carbohydrate":
                preference = -food.carbs_per_100g
            elif goal == "endurance" and food.category == "fruit":
                preference = -food.carbs_per_100g
        return (food.food_id in recent_ids, preference, food.food_id)

    seen = set()
    for offset in range(6):
        selected = set()
        for meal in ("breakfast", "lunch", "dinner"):
            roles = ("protein", "carbohydrate", "fruit") if meal == "breakfast" else (
                "protein", "carbohydrate", "vegetable", "fat")
            for role in roles:
                pool = [food for food in catalog.foods if food.category == role
                        and meal in food.allowed_meals and "supplement" not in food.dietary_tags
                        and _catalog_measurement_state(food) is not None]
                pool = sorted(pool, key=rank)
                if not pool:
                    continue
                # Keep multiple compatible sources for the unchanged service
                # to choose distinct main proteins/starches and feasible doses.
                # A single low-density source per role cannot meet normal kcal.
                width = 2 if meal == "breakfast" else 4
                if role == "fat":
                    selected.update(food.food_id for food in pool)
                elif role == "fruit":
                    selected.add(pool[0].food_id)
                else:
                    start = offset % len(pool)
                    ordered = pool[start:] + pool[:start]
                    selected.update(food.food_id for food in ordered[:width])
        signature = tuple(sorted(selected))
        if signature not in seen:
            seen.add(signature)
            yield Catalog(catalog.version, tuple(food for food in catalog.foods if food.food_id in selected))
    # The service prefers the highest-protein main-meal sources. At normal
    # kcal, that can exceed the confirmed protein range. Keep all other roles
    # intact and try bounded protein-density tiers; the unchanged optimizer
    # and final target validator remain the only feasibility authority.
    main_proteins = sorted(
        (food for food in catalog.foods if food.category == "protein"
         and {"lunch", "dinner"}.intersection(food.allowed_meals)
         and "supplement" not in food.dietary_tags
         and _catalog_measurement_state(food) is not None),
        key=lambda food: (-food.protein_per_100g, food.food_id),
    )
    fruits = sorted((food for food in catalog.foods if food.category == "fruit"
                     and "breakfast" in food.allowed_meals
                     and _catalog_measurement_state(food) is not None), key=rank)
    for offset in range(1, min(len(main_proteins), 15)):
        excluded = {food.food_id for food in main_proteins[:offset]}
        preferred_exclusions = excluded | {food.food_id for food in fruits[1:]}
        for exclusions in (preferred_exclusions, excluded):
            foods = tuple(food for food in catalog.foods if food.food_id not in exclusions)
            signature = tuple(sorted(food.food_id for food in foods))
            if signature not in seen:
                seen.add(signature)
                yield Catalog(catalog.version, foods)
    # Feasibility takes precedence over novelty or goal preference.
    yield catalog


def _catalog_measurement_state(source) -> str | None:
    # Explicit projection of catalog preparation facts; no name/ID inference.
    groups = {
        "raw": {"raw", "raw_dry", "raw_frozen_pasteurized", "raw_with_peel", "raw_green",
                "unroasted", "excluding_honey_roasted"},
        "cooked": {"baked_broiled_roasted_skin_not_eaten", "cooked_roasted_trimmed_lean_only",
                   "baked_or_broiled", "boiled_or_poached", "cooked_not_further_specified",
                   "boiled_not_further_specified", "cooked_restaurant_source",
                   "roasted_light_meat_skin_not_eaten", "chop_lean_only_eaten",
                   "from_dried_no_added_fat", "cooked", "no_added_fat", "boiled_no_added_fat",
                   "fresh_cooked_no_added_fat", "boiled_drained_without_salt"},
        "drained": {"canned_in_water_drained_solids"},
        "ready_to_eat": {"plain_low_fat_milk", "plain_farmers", "baked", "plain",
                         "plain_nonfat_milk", "low_fat_1_percent",
                         "firm_calcium_sulfate_and_nigari", "canned_not_further_specified"},
    }
    return next((state for state, preparations in groups.items()
                 if source.preparation_state in preparations), None)


def _build_source_backed_candidate(targets: NutritionTargets, lang: str, *,
                                   restrictions: tuple[str, ...], catalog) -> NutritionPlan | None:
    """Build a validated fallback plan from the existing source-backed catalog.

    This path is deliberately narrow: it is used only after structured model
    delivery was rejected, and only for an unrestricted request.  It consumes
    typed catalog data and optimizer output directly; it never parses rendered
    text or estimates a food's macros.
    """
    if restrictions:
        return None
    try:
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
        # Preserve the existing base selection envelope. Higher targets are
        # resolved through the same public service, never a dinner top-up.
        optimizer_kcal_target = min(targets.kcal, Decimal("2500"))
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
                    calories_target=optimizer_kcal_target,
                    calories_tolerance=Decimal("0.05"),
                    # A calorie target is sufficient for the legacy delivery
                    # contract.  A missing protein target means no additional
                    # protein floor, not an unsupported request.
                    protein_min_g=targets.protein if targets.protein is not None else Decimal("0"),
                ),
            ),
            catalog=catalog,
        )
        if result.outcome is not NutritionPlanOutcome.SUCCESS or result.projection is None:
            return None

        if targets.kcal > optimizer_kcal_target:
            return _expand_source_backed_result(result, targets, lang, catalog, policy, restrictions)
        return _source_backed_projection_plan(result, targets, lang, catalog, restrictions)
    except Exception:
        return None


def _source_backed_projection_plan(result, targets, lang, catalog, restrictions):
    """Project a service result through the existing canonical delivery gate."""
    names = {name: food for food in catalog.foods for name in (food.display_name_bg, food.display_name_en)}
    meals = []
    labels = {"Breakfast": "breakfast", "Закуска": "breakfast",
              "Lunch": "lunch", "Обяд": "lunch",
              "Dinner": "dinner", "Вечеря": "dinner", "Snack": "snack", "Междинно хранене": "snack"}
    for meal in result.projection.meals:
        meal_type = labels.get(meal.label)
        if meal_type is None:
            return None
        foods = []
        for food in meal.foods:
            source = names.get(food.name)
            if source is None or _catalog_measurement_state(source) is None:
                return None
            grams = food.quantity
            if food.unit in {"pcs", "бр."}:
                if source.grams_per_piece is None:
                    return None
                grams *= source.grams_per_piece
            foods.append({
                "display_name": _catalog_display_name(source, lang),
                "catalog_id": source.food_id,
                "food_id": source.food_id,
                "measurement_state": _catalog_measurement_state(source),
                "grams": str(grams),
                "protein_g": str(food.macros.protein_g),
                "carbs_g": str(food.macros.carbs_g),
                "fat_g": str(food.macros.fat_g),
                "kcal": str(food.macros.kcal),
            })
        meals.append({
            "meal_type": meal_type,
            "name": meal.label,
            "time": {"breakfast": "08:00", "snack": "10:30", "lunch": "13:00", "dinner": "19:00"}[meal_type],
            "foods": foods,
        })
    return build_plan(
        {"meals": meals}, targets, restrictions=restrictions,
        provenance={"generator": "source_backed_catalog_fallback",
                    "catalog_version": catalog.version, "service_version": result.service_version},
        language="en" if str(lang).lower() == "en" else "bg",
    )


_FOOD_DISPLAY_NAMES_BG = {
    "dev_lean_pork_cooked": "Постен свински котлет",
    "dev_cottage_cheese": "Фермерска извара",
    "dev_greek_yogurt_nonfat": "Обезмаслено гръцко кисело мляко",
    "dev_greek_yogurt_2pct": "Гръцко кисело мляко с ниска масленост",
}


def _catalog_display_name(source, lang):
    return source.display_name_en if str(lang).lower() == "en" else (
        _FOOD_DISPLAY_NAMES_BG.get(source.food_id, source.display_name_bg))


def _expand_source_backed_result(base, targets, lang, catalog, policy, restrictions):
    """Re-solve selected foods through the public service, then try one snack.

    Temporary search bounds only narrow the catalog's permitted portions.
    Nutrient facts and target parameters are unchanged. The final canonical
    build_plan gate still accepts or rejects every returned result.
    """
    from nutrition_engine.catalog import Catalog
    from nutrition_engine.models import (CallerRouteStatus, CatalogMode, DietConstraints,
                                         NutritionPlanOutcome, NutritionPlanRequest, NutritionTargets as EngineTargets)
    from nutrition_engine.service import SERVICE_VERSION, build_nutrition_plan
    from nutrition_engine.quality import evaluate_quality
    from inspect import signature

    names = {name: source for source in catalog.foods for name in (source.display_name_en, source.display_name_bg)}
    selected = {}
    base_protein = sum(food.macros.protein_g for meal in base.projection.meals for food in meal.foods)
    if (targets.protein is not None and base_protein > targets.protein
            and not _within(base_protein, targets.protein, Decimal("0.05"))):
        # This search only increases doses. The existing canonical gate would
        # reject an already-excessive protein base, so do not spend a solve on it.
        return None
    for meal in base.projection.meals:
        for food in meal.foods:
            source = names.get(food.name)
            if source is None:
                return None
            grams = food.quantity * source.grams_per_piece if food.unit in {"pcs", "бр."} else food.quantity
            selected[source.food_id] = max(selected.get(source.food_id, Decimal("0")), grams)
    sources = []
    oil_slots = sum(any(names[food.name].food_id == "dev_olive_oil" for food in meal.foods)
                    for meal in base.projection.meals)
    oil_limit = signature(evaluate_quality).parameters["maximum_oil_g"].default
    if not isinstance(oil_limit, Decimal):
        return None
    for food_id, grams in selected.items():
        source = catalog.by_id(food_id)
        if not source.minimum_portion <= grams <= source.maximum_portion:
            return None
        # Preserve protein/vegetable doses; expand existing energy sources only.
        upper = source.maximum_portion if source.category in {"carbohydrate", "fruit", "fat"} else grams
        if source.food_id == "dev_olive_oil":
            # Allocate the existing quality gate's aggregate limit across its
            # actual meal slots; do not invent a new per-meal nutrition rule.
            upper = min(upper, oil_limit / max(1, oil_slots))
        sources.append(replace(source, minimum_portion=grams, maximum_portion=upper,
                               default_portion=max(grams, min(source.default_portion, upper))))
    growth_policy = replace(policy, category_portion_overrides=())
    snacks = sorted((food for food in catalog.foods if "snack" in food.allowed_meals
                     and "supplement" not in food.dietary_tags
                     and _catalog_measurement_state(food) is not None), key=lambda food: food.food_id)
    seen = set()
    canonical_rejected = False
    for snack in [None] + snacks[:8]:
        # First solve without a new meal. A snack is considered only if the
        # selected composition cannot meet the confirmed daily target.
        meal_sources = tuple(replace(source, maximum_portion=source.minimum_portion,
                                     default_portion=source.minimum_portion)
                             if canonical_rejected and source.category == "carbohydrate" else source
                             for source in sources)
        # An optional snack is an additional meal, not permission to replace
        # an already-selected main-meal food. Narrow eligibility in this view.
        addition = (replace(snack, allowed_meals=frozenset({"snack"})),) if snack and snack.food_id not in selected else ()
        view = Catalog(catalog.version, meal_sources + addition)
        signature = (bool(snack), canonical_rejected, tuple(food.food_id for food in view.foods))
        if signature in seen:
            continue
        seen.add(signature)
        result = build_nutrition_plan(NutritionPlanRequest(
            language="en" if str(lang).lower() == "en" else "bg", catalog_version=catalog.version,
            catalog_mode=CatalogMode.DEVELOPMENT, diet_constraints=DietConstraints(),
            required_meals=("breakfast", "snack", "lunch", "dinner") if snack else ("breakfast", "lunch", "dinner"),
            practicality_policy=growth_policy, caller_route_status=CallerRouteStatus.ELIGIBLE,
            service_version=SERVICE_VERSION, targets=EngineTargets(
                calories_target=targets.kcal, calories_tolerance=Decimal("0.05"),
                protein_min_g=targets.protein if targets.protein is not None else Decimal("0"))), catalog=view)
        if result.outcome is NutritionPlanOutcome.SUCCESS and result.projection is not None:
            try:
                plan = _source_backed_projection_plan(result, targets, lang, catalog, restrictions)
            except NutritionPlanError:
                # Service feasibility does not prove canonical macro validity.
                # Keep the gate unchanged and try the next bounded composition.
                canonical_rejected = True
                continue
            if plan is not None:
                return plan
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
            canonical_food_id = _canonical_food_id(name, raw_food.get("food_id"))
            food = NutritionFood(
                food_id, catalog_id, name, grams, food_macros,
                canonical_food_id, _measurement_state(
                    raw_food.get("measurement_state"), canonical_food_id, require_for_ambiguous=False,
                ),
            )
            foods.append(food)
            macros = macros.plus(food_macros)
        stored_preparation_type = raw_meal.get("preparation_type")
        if stored_preparation_type is None:
            # Older persisted plans gain the safe main-meal default without
            # parsing rendered text to reconstruct it.
            preparation_type = "assembly" if meal_type in _MEALS else None
        elif stored_preparation_type in {"assembly", "none"}:
            preparation_type = str(stored_preparation_type)
        else:
            raise NutritionPlanError("stored meal preparation_type is invalid")
        if meal_type in _MEALS and preparation_type != "assembly":
            raise NutritionPlanError("stored primary meal preparation is invalid")
        meals.append(NutritionMeal(
            meal_id, str(raw_meal.get("name") or meal_type.title()).strip(), meal_type,
            str(raw_meal.get("time") or meal_type).strip(), tuple(foods), macros, preparation_type))
    if not set(_MEALS).issubset(seen):
        raise NutritionPlanError("stored plan primary meals are incomplete")
    ordering = {"breakfast": 0, "snack": 1, "lunch": 2, "dinner": 3}
    if [ordering[meal.meal_type] for meal in meals] != sorted(ordering[meal.meal_type] for meal in meals):
        raise NutritionPlanError("stored plan meals are not chronological")
    totals = NutritionMacros.zero()
    for meal in meals:
        totals = totals.plus(meal.macros)
    status = _validate_totals(totals, targets)
    restrictions = record.get("restrictions") or []
    provenance = record.get("provenance") or {}
    if not isinstance(restrictions, list) or not isinstance(provenance, Mapping):
        raise NutritionPlanError("stored plan metadata is invalid")
    _validate_restrictions(meals, restrictions)
    return NutritionPlan(
        plan_id, version, created_at_utc, targets,
        tuple(sorted({str(item).strip() for item in restrictions if str(item).strip()})),
        tuple(meals), totals,
        tuple(sorted((str(key), str(value)) for key, value in provenance.items())),
        status,
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
    status = _validate_totals(totals, plan.targets)
    provenance = dict(plan.provenance)
    provenance.update({"parent_plan_id": plan.id, "revision": operation.kind.value})
    _validate_restrictions(meals, restrictions)
    return NutritionPlan(
        id=uuid.uuid4().hex,
        version=plan.version,
        created_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        targets=plan.targets,
        restrictions=tuple(sorted({item.strip() for item in restrictions if item.strip()})),
        meals=meals,
        totals=totals,
        provenance=tuple(sorted(provenance.items())),
        target_status=status,
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
                    foods.append(NutritionFood(
                        food.id, None, replacement, food.grams, food.macros,
                        _canonical_food_id(replacement, None), food.measurement_state,
                    ))
                    changed = True
                else:
                    foods.append(food)
            meals.append(NutritionMeal(meal.id, meal.name, meal.meal_type, meal.time, tuple(foods), meal.macros,
                                       meal.preparation_type))
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
                food.grams, food.macros, food.food_id, food.measurement_state) for food in meal.foods)
            meals.append(NutritionMeal(meal.id, "Alternative breakfast", meal.meal_type, meal.time, foods,
                                       meal.macros, meal.preparation_type))
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
                    food = NutritionFood(
                        food.id, food.catalog_id, food.display_name,
                        food.grams * factor, updated_macros, food.food_id, food.measurement_state,
                    )
                    changed = True
                foods.append(food)
                macros = macros.plus(food.macros)
            meals.append(NutritionMeal(meal.id, meal.name, meal.meal_type, meal.time, tuple(foods), macros,
                                       meal.preparation_type))
        if not changed:
            raise NutritionPlanError("ingredient is not present in the active plan")
        return _revision_plan(plan, tuple(meals), restrictions=plan.restrictions, operation=operation)

    raise NutritionPlanError("revision is unsupported")


def _preparation_ingredients(plan: NutritionPlan) -> frozenset[str]:
    from recipe_engine.recipe_matcher import ingredient_key

    return frozenset(ingredient_key(food.display_name) for meal in plan.meals for food in meal.foods)


def validate_regenerated_revision(candidate: NutritionPlan, active: NutritionPlan, *,
                                  simpler_preparation: bool) -> NutritionPlan:
    """Keep target/restriction authority and reject copy-only simplification."""
    if candidate.targets != active.targets or not set(active.restrictions).issubset(candidate.restrictions):
        raise NutritionPlanError("revision must preserve targets and recorded restrictions")
    if simpler_preparation:
        # This bounded, observable policy reduces ingredient preparation work;
        # it makes no invented cooking-time or physiological claim.
        if (any(len(meal.foods) > 3 for meal in candidate.meals)
                or len(_preparation_ingredients(candidate)) >= len(_preparation_ingredients(active))):
            raise NutritionPlanError("simpler preparation requires fewer distinct ingredients and at most three foods per meal")
    provenance = dict(candidate.provenance)
    provenance.update({"parent_plan_id": active.id, "revision": "whole_plan"})
    if simpler_preparation:
        provenance["preparation_policy"] = "fewer_distinct_ingredients"
    return replace(candidate, provenance=tuple(sorted(provenance.items())))


def revision_generation_contract(active: NutritionPlan, restrictions: tuple[str, ...], *,
                                 simpler_preparation: bool) -> str:
    """Bound regeneration to the persisted plan, not conversational arithmetic."""
    context = [{"meal_type": meal.meal_type,
                "foods": [food.display_name for food in meal.foods]} for meal in active.meals]
    return (
        "\n[AUTHORITATIVE NUTRITION PLAN REVISION]\n"
        "Regenerate ONE complete structured plan. Keep ALL confirmed targets unchanged. "
        "Recorded exclusions (must all be respected): " + json.dumps(restrictions, ensure_ascii=False)
        + ". Active meal context: " + json.dumps(context, ensure_ascii=False)
        + ". Return only canonical JSON, never a conversational meal plan, summary, ELITE STATUS footer or pain disclaimer."
        + (f" Use fewer than {len(_preparation_ingredients(active))} distinct ingredients across the day, "
           "at most three foods per meal. Reuse practical ingredients across meals to reduce preparation; "
           "do not merely rename meals or claim they are simpler."
           if simpler_preparation else "")
    )


def parse_generation_response(response: object) -> Mapping[str, object]:
    """Read a JSON generation response, never a rendered plan response."""
    try:
        content = response.choices[0].message.content
        payload = json.loads(content)
    except (AttributeError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise NutritionPlanError("structured nutrition generation was invalid") from exc
    if not isinstance(payload, Mapping):
        raise NutritionPlanError("structured nutrition generation must be an object")
    meals = payload.get("meals")
    if not isinstance(meals, list):
        raise NutritionPlanError("structured nutrition generation requires meals")
    for meal in meals:
        if not isinstance(meal, Mapping) or not isinstance(meal.get("foods"), list):
            raise NutritionPlanError("structured nutrition generation requires meal foods")
        for food in meal["foods"]:
            food_id = food.get("food_id") if isinstance(food, Mapping) else None
            if not isinstance(food_id, str) or not food_id.strip():
                raise NutritionPlanError("food.food_id must be a non-empty string")
    return payload


def _display_decimal(value: Decimal) -> str:
    result = format(value.normalize(), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def _quantity_label(food: NutritionFood, lang: str) -> str:
    amount = _display_decimal(food.grams)
    if food.measurement_state is None:
        return f"{amount} g"
    english = str(lang).lower() == "en"
    labels = {
        MeasurementState.RAW: ("raw weight", "сурово тегло"),
        MeasurementState.COOKED: ("cooked", "сготвено"),
        MeasurementState.DRAINED: ("drained", "отцедено"),
        MeasurementState.READY_TO_EAT: ("ready to eat", "готово за консумация"),
        MeasurementState.AS_SERVED: ("as served", "в готов вид"),
        MeasurementState.PACKAGE_WEIGHT: ("package weight", "тегло от опаковката"),
    }
    return f"{amount} {'g' if english else 'г'}, {labels[food.measurement_state][0 if english else 1]}"


def _meal_reason(meal: NutritionMeal, targets: NutritionTargets, lang: str) -> str:
    """Keep the legacy table column empty; explanation belongs to the whole plan."""
    return ""


def render(plan: NutritionPlan, lang: str, recipe_tokens: Mapping[str, str] | None = None) -> str:
    """Deterministically project an authoritative plan into legacy chat text."""
    _validate_restrictions(plan.meals, plan.restrictions)
    english = str(lang).lower() == "en"
    include_recipes = bool(recipe_tokens)
    labels = {
        "breakfast": ("Breakfast", "\u0417\u0430\u043a\u0443\u0441\u043a\u0430"),
        "snack": ("Snack", "\u041c\u0435\u0436\u0434\u0438\u043d\u043d\u043e"),
        "lunch": ("Lunch", "\u041e\u0431\u044f\u0434"),
        "dinner": ("Dinner", "\u0412\u0435\u0447\u0435\u0440\u044f"),
    }
    header = "| Meal | Menu title | Meal ID | Food | Quantity | Protein (g) | Carbs (g) | Fat (g) | Kcal | Why this meal |"
    if not english:
        header = "| \u0425\u0440\u0430\u043d\u0435\u043d\u0435 | \u0425\u0440\u0430\u043d\u0430 | \u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e | \u0411\u0435\u043b\u0442\u044a\u0447\u0438\u043d\u0438 (g) | \u0412\u044a\u0433\u043b\u0435\u0445\u0438\u0434\u0440\u0430\u0442\u0438 (g) | \u041c\u0430\u0437\u043d\u0438\u043d\u0438 (g) | \u041a\u043a\u0430\u043b | \u0417\u0430\u0449\u043e \u0442\u043e\u0432\u0430 \u0445\u0440\u0430\u043d\u0435\u043d\u0435 |"
    if not english:
        header = "| \u0425\u0440\u0430\u043d\u0435\u043d\u0435 | ID \u043d\u0430 \u0445\u0440\u0430\u043d\u0435\u043d\u0435 | \u0425\u0440\u0430\u043d\u0430 | \u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e | \u0411\u0435\u043b\u0442\u044a\u0447\u0438\u043d\u0438 (g) | \u0412\u044a\u0433\u043b\u0435\u0445\u0438\u0434\u0440\u0430\u0442\u0438 (g) | \u041c\u0430\u0437\u043d\u0438\u043d\u0438 (g) | \u041a\u043a\u0430\u043b | \u0417\u0430\u0449\u043e \u0442\u043e\u0432\u0430 \u0445\u0440\u0430\u043d\u0435\u043d\u0435 |"
    if not english:
        header = header.replace("| ID ", "| \u041c\u0435\u043d\u044e | ID ", 1)
    if include_recipes:
        header += " Recipe |" if english else " \u0420\u0435\u0446\u0435\u043f\u0442\u0430 |"
    lines = [header, "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |" + (" --- |" if include_recipes else "")]
    for meal in plan.meals:
        for index, food in enumerate(meal.foods):
            label = labels[meal.meal_type][0 if english else 1] if index == 0 else ""
            reason = _meal_reason(meal, plan.targets, lang) if index == 0 else ""
            recipe = (recipe_tokens or {}).get(meal.id, "") if index == 0 else ""
            row = "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                label, meal.name if index == 0 else "", meal.id if index == 0 else "",
                _FOOD_DISPLAY_NAMES_BG.get(food.food_id, food.display_name) if not english else food.display_name,
                _quantity_label(food, lang),
                _display_decimal(food.macros.protein_g), _display_decimal(food.macros.carbs_g),
                _display_decimal(food.macros.fat_g), _display_decimal(food.macros.kcal), reason,
            )
            lines.append(row[:-1] + f" | {recipe} |" if include_recipes else row)
    total_label = "Daily Total" if english else "\u041e\u0431\u0449\u043e"
    total_row = "| {} | | | | | {} | {} | {} | {} | |".format(
        total_label, _display_decimal(plan.totals.protein_g), _display_decimal(plan.totals.carbs_g),
        _display_decimal(plan.totals.fat_g), _display_decimal(plan.totals.kcal),
    )
    lines.append(total_row[:-1] + " | |" if include_recipes else total_row)
    return "\n".join(lines)


def render_delivery(plan: NutritionPlan, lang: str, profile: Mapping[str, object] | None = None,
                    nutrition_rationale: object | None = None) -> str:
    """Render the validated meal table with optional existing recipe tokens."""
    try:
        _validate_restrictions(plan.meals, plan.restrictions + recorded_profile_restrictions(profile))
    except NutritionRestrictionError:
        return restriction_blocked_message(lang)
    recipe_tokens: dict[str, str] = {}
    try:
        from recipe_engine.recipe_engine import match_plan
        from recipe_engine.recipe_renderer import recipe_token

        recipe_tokens = {meal_id: recipe_token(match, meal_id) for meal_id, match in match_plan(plan, profile).items()}
    except Exception:
        # Recipes are optional presentation. A bad local record must never block
        # a plan that has already passed the delivery contract.
        recipe_tokens = {}
    try:
        from recipe_engine.recipe_renderer import assembly_token

        for meal in plan.meals:
            if meal.preparation_type == "assembly" and meal.id not in recipe_tokens:
                recipe_tokens[meal.id] = assembly_token(meal, lang)
    except Exception:
        # Presentation enhancement must not block the validated plan contract.
        pass
    table = render(plan, lang, recipe_tokens)
    explanation = _plan_explanation(plan, lang, profile)
    return table + ("\n\n" + explanation if explanation else "")


def _plan_explanation(plan, lang, profile):
    """Explain only confirmed targets, explicit goal, and this plan's structure."""
    if plan.targets.kcal <= 0 or not plan.meals:
        return ""
    english = str(lang).lower() == "en"
    goal = _selection_goal(profile)
    goals = {"fat_loss": ("fat loss", "сваляне на мазнини"),
             "muscle_gain": ("muscle gain", "покачване на мускулна маса"),
             "strength": ("strength", "сила"), "endurance": ("endurance", "издръжливост"),
             "general": ("general fitness", "обща физическа форма")}
    target = _display_decimal(plan.targets.kcal)
    total = _display_decimal(plan.totals.kcal)
    if english:
        prefix = f"For your {goals[goal][0]} goal, " if goal in goals else ""
        sentences = [f"{prefix}the plan follows your confirmed {target} kcal target and provides {total} kcal."]
        if not prefix:
            sentences[0] = sentences[0][0].upper() + sentences[0][1:]
    else:
        prefix = f"За целта ти {goals[goal][1]}, " if goal in goals else ""
        sentences = [f"{prefix}планът следва потвърдения ти таргет от {target} kcal и осигурява {total} kcal."]
        if not prefix:
            sentences[0] = sentences[0][0].upper() + sentences[0][1:]
    if plan.targets.protein is not None:
        protein_target, protein = _display_decimal(plan.targets.protein), _display_decimal(plan.totals.protein_g)
        sentences.append(f"Your protein target is {protein_target} g; the plan provides {protein} g." if english else
                         f"Протеиновият ти таргет е {protein_target} г; планът осигурява {protein} г.")
    main = [meal for meal in plan.meals if meal.meal_type in _MEALS]
    snacks = [meal for meal in plan.meals if meal.meal_type == "snack"]
    if len(main) == 3:
        protein_in_each = all(meal.macros.protein_g > 0 for meal in main)
        if english:
            structure = "Energy is spread across breakfast, lunch and dinner"
            structure += " and a snack" if snacks else ""
            structure += ", with protein in each main meal" if protein_in_each else ""
        else:
            structure = "Енергията е разпределена между закуска, обяд и вечеря"
            structure += " и междинно хранене" if snacks else ""
            structure += ", с белтъчини във всяко основно хранене" if protein_in_each else ""
        sentences.append(structure + ".")
    title = "Why this plan" if english else "Защо този план"
    return f"**{title}:** " + " ".join(sentences[:3])


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
        "targets": targets, "restrictions": list(plan.restrictions), "target_status": plan.target_status.value,
        "totals": macros(plan.totals), "provenance": dict(plan.provenance),
        "meals": [
            {"id": meal.id, "name": meal.name, "meal_type": meal.meal_type, "time": meal.time,
             "preparation_type": meal.preparation_type,
             "macros": macros(meal.macros), "foods": [
                 {"id": food.id, "catalog_id": food.catalog_id, "food_id": food.food_id,
                  "display_name": food.display_name, "measurement_state": (
                      food.measurement_state.value if food.measurement_state is not None else None),
                  "grams": str(food.grams), "macros": macros(food.macros)}
                 for food in meal.foods]}
            for meal in plan.meals],
    }


_GOAL_SELECTION_GUIDANCE = {
    "fat_loss": "Prefer practical lean-protein, fruit/vegetable, and lower-energy-density combinations.",
    "muscle_gain": "Prefer practical energy-dense meals combining carbohydrate and protein foods.",
    "strength": "Prefer practical protein and carbohydrate meal combinations.",
    "endurance": "Prefer variety among carbohydrate-source foods and fruit alongside protein.",
    "general": "Prefer balanced variety without a specialized food-selection bias.",
}


def _selection_goal(profile: Mapping[str, object] | None) -> str:
    value = profile.get("goal") if isinstance(profile, Mapping) else None
    return value if isinstance(value, str) and value in _GOAL_SELECTION_GUIDANCE else ""


def generation_contract(targets: NutritionTargets, lang: str,
                        recent_context: RecentNutritionContext | None = None,
                        profile: Mapping[str, object] | None = None) -> str:
    """The only model contract for canonical daily-plan generation."""
    return (
        "[STRUCTURED DAILY NUTRITION PLAN]\n"
        "Return a JSON object only. Never return markdown or prose. The object has a meals array. "
        "The meals array MUST be in exactly this order: breakfast, optional snack, lunch, dinner. "
        "If snack is omitted: breakfast, lunch, dinner. Never place snack after lunch. "
        "Each meal has meal_type (breakfast, optional snack, lunch, dinner), name, time, and foods. "
        "Each food has food_id, display_name, optional catalog_id, measurement_state, grams, protein_g, carbs_g, fat_g, and kcal. "
        "food_id MUST be a non-empty canonical ingredient string, never null, empty, omitted, or a display label. "
        "measurement_state is one of raw, cooked, drained, ready_to_eat, as_served, package_weight; "
        "include the actual measurement state for every ingredient. "
        "Every food is exactly one food ingredient; never combine foods in one name. "
        + ("Every display_name must be English only. " if str(lang).lower() == "en"
           else "Every display_name must be Bulgarian only; do not mix English food names. ")
        +
        "Breakfast, lunch, and dinner are required and chronological. Grams and kcal must be positive; macros may be zero but never negative. "
        "Food nutrient fields describe the stated portion, not 100g values. Calculate each portion and sum all food fields before returning JSON. "
        "The summed food totals must meet these confirmed targets within 5%: "
        f"{targets.kcal} kcal; protein {targets.protein if targets.protein is not None else 'unspecified'}g; "
        f"carbs {targets.carbs if targets.carbs is not None else 'unspecified'}g; "
        f"fat {targets.fat if targets.fat is not None else 'unspecified'}g. "
        "Check kcal and EVERY specified macro independently. Do not invent an unspecified macro target or change the confirmed targets. "
        "Allergies, restrictions, and explicit food preferences override selection preferences."
        + ("\n[BOUNDED GOAL FOOD SELECTION]\n" + _GOAL_SELECTION_GUIDANCE[_selection_goal(profile)]
           + " This is a selection preference only, within confirmed targets; no new targets or physiological claims."
           if _selection_goal(profile) else "")
        + ("\n[RECENT STRUCTURED PLAN CONTEXT]\n"
           "Avoid unnecessary repetition of these recent meal ingredients when equivalent choices meet targets and restrictions: "
           + "; ".join(f"{meal}: {', '.join(labels)}" for meal, labels in recent_context.recent_meals)
           + ". Repetition is allowed when targets, restrictions, or practicality require it."
           if recent_context is not None and recent_context.available else "")
    )


def regeneration_contract(validation_failure: Exception, targets: NutritionTargets, lang: str,
                          recent_context: RecentNutritionContext | None = None,
                          profile: Mapping[str, object] | None = None) -> str:
    """Request one repair without ever returning the rejected structured plan."""
    reason = str(validation_failure).strip() or "structured nutrition validation failed"
    return (
        "[STRUCTURED DAILY NUTRITION PLAN REPAIR]\n"
        "The immediately previous JSON was rejected by deterministic validation. "
        f"Validation failure: {reason}.\n"
        "Return one complete corrected JSON object only. Do not include markdown, prose, "
        "or the rejected output. Keep the original request and confirmed targets. "
        "Repair missing/empty ingredient IDs and portion arithmetic; never fabricate nutrient values to make totals fit. "
        "Recalculate all meal sums and the daily kcal/protein/carbs/fat sums before returning JSON.\n"
        + generation_contract(targets, lang, recent_context, profile)
    )
