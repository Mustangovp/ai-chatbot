"""Phase 4 deterministic meal selector, templates, library, substitution, rotation.

Isolated: no production imports, no network, no DB, no LLM. Every assertion is
about the nutrition_engine library in isolation.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from nutrition_engine import (
    CatalogGovernance, DietConstraints, NutritionTargets, PracticalityPolicy,
    MealMacroBounds, MealSelectionEngine, MealSelectionQuery,
    MealDistribution, NutritionConstructionError, NutritionConstructionRequest,
    NutritionPlanConstructionEngine, NutritionTargetPolicy,
    build_nutrition_knowledge_library, calculate_target_macros, load_catalog_file, optimize,
)
from nutrition_engine.candidate_builder import build_candidates
from nutrition_engine.models import Nutrients, OptimizedFood, OptimizedMeal, OptimizedNutritionDay
from nutrition_engine.feasibility import FeasibilityCode, FeasibilityResult
from nutrition_engine import selector, rotation, substitutions
from nutrition_engine import meal_templates, meal_library
from recommend.engine import (
    ImmutableUserProfile, ProfileCompleteness, RecommendationBlueprint,
    RecommendationIntent, RecommendationOutcome,
)


CATALOG = load_catalog_file(
    Path(__file__).parents[1] / "nutrition_engine" / "data" / "food_catalog_v1.json",
    CatalogGovernance(True, False, Decimal("15")),
)
POLICY = PracticalityPolicy(
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
MEALS = ("breakfast", "lunch", "dinner")


TARGET_POLICY = NutritionTargetPolicy(
    activity_factors=(("moderate", Decimal("1.55")),),
    goal_calorie_adjustments=(("muscle_gain", Decimal("250")),),
    protein_g_per_kg=(("muscle_gain", Decimal("1.8")),),
    fat_calorie_fractions=(("muscle_gain", Decimal("0.25")),),
)


def _nutrition_recommendation():
    return RecommendationBlueprint(
        blueprint_id="rec_nutrition_phase19",
        version="recommendation-blueprint-v1",
        intent=RecommendationIntent.NUTRITION,
        outcome=RecommendationOutcome.RECOMMEND,
        profile_completeness=ProfileCompleteness.SUFFICIENT,
        knowledge_registry_version="knowledge-registry-v1",
        knowledge_document_ids=("nutrition-foundation",),
        reasons=(),
        missing_fields=(),
        conflict_fields=(),
        clarification_field=None,
    )


def _phase19_profile():
    return ImmutableUserProfile.from_verified_facts({
        "age": "30", "height": "180", "weight": "80", "gender": "male",
        "activityLevel": "moderate", "goal": "muscle_gain",
    })


def _construction_request(*, distribution=None, restrictions=frozenset(), blacklist=frozenset()):
    return NutritionConstructionRequest(
        recommendation=_nutrition_recommendation(),
        profile=_phase19_profile(),
        library=build_nutrition_knowledge_library(CATALOG),
        target_policy=TARGET_POLICY,
        meal_distribution=distribution or (
            MealDistribution("breakfast", Decimal("0.20")),
            MealDistribution("snack", Decimal("0.10")),
            MealDistribution("lunch", Decimal("0.25")),
            MealDistribution("snack", Decimal("0.10")),
            MealDistribution("dinner", Decimal("0.35")),
        ),
        dietary_restrictions=restrictions,
        ingredient_blacklist=blacklist,
    )


def _feasible():
    targets = NutritionTargets(Decimal("1914"), Decimal("0.05"), Decimal("198"))
    plan = build_candidates(CATALOG, targets, DietConstraints(), MEALS, POLICY)
    assert plan is not None
    return optimize(CATALOG, targets, DietConstraints(), plan.selections, POLICY)


# ── meal templates ──────────────────────────────────────────────────────────

def test_meal_templates_are_defined_for_every_meal_type_with_valid_bounds():
    for meal_type in ("breakfast", "snack", "lunch", "dinner"):
        template = meal_templates.template_for(meal_type)
        assert 1 <= template.minimum_groups <= template.maximum_groups
        assert set(template.required_groups) <= template.allowed_groups
        assert len(template.required_groups) <= template.maximum_groups
    with pytest.raises(ValueError):
        meal_templates.template_for("brunch")


def test_template_violations_detect_missing_disallowed_and_out_of_bounds_groups():
    assert meal_templates.template_violations("lunch", ["protein", "carbohydrate", "vegetable"]) == ()
    assert "missing_required_group:vegetable" in meal_templates.template_violations("lunch", ["protein", "carbohydrate"])
    assert "below_minimum_groups" in meal_templates.template_violations("lunch", ["protein"])
    assert any(v.startswith("disallowed_group") for v in meal_templates.template_violations("snack", ["vegetable"]))


# ── meal library ────────────────────────────────────────────────────────────

def test_meal_library_is_catalog_only_with_in_bounds_portions():
    for meal in meal_library.all_library_meals():
        assert meal.meal_type in meal_library.MEAL_CATEGORIES
        assert len(meal.food_ids) == len(meal.default_portions_g)
        for food_id, portion in zip(meal.food_ids, meal.default_portions_g):
            food = CATALOG.by_id(food_id)
            assert food is not None, food_id
            if meal.meal_type in ("breakfast", "snack", "lunch", "dinner"):
                assert meal.meal_type in food.allowed_meals
            assert food.minimum_portion <= portion <= food.maximum_portion
    ids = [m.meal_id for m in meal_library.all_library_meals()]
    assert len(ids) == len(set(ids))
    assert all(len(meal_library.library_meals_for(mt)) >= 2 for mt in MEALS)
    assert meal_library.library_meals_for("pre_workout")
    assert meal_library.library_meals_for("post_workout")


# ── substitutions ───────────────────────────────────────────────────────────

def test_substitution_chain_is_ordered_deterministic_and_symmetric_within_a_chain():
    subs = substitutions.approved_substitutes("dev_chicken_breast_cooked")
    assert subs == substitutions.approved_substitutes("dev_chicken_breast_cooked")  # deterministic
    assert "dev_chicken_breast_cooked" not in subs
    assert "dev_tofu_firm" in subs and "dev_turkey_breast_cooked" in subs
    assert substitutions.is_supported_substitution("dev_chicken_breast_cooked", "dev_tofu_firm")
    assert substitutions.is_supported_substitution("dev_tofu_firm", "dev_chicken_breast_cooked")


def test_unsupported_substitutions_are_rejected():
    # cross-role swap is never approved
    assert not substitutions.is_supported_substitution("dev_chicken_breast_cooked", "dev_rice_cooked")
    # a food outside every chain has no substitutes
    assert substitutions.approved_substitutes("dev_wholegrain_bread") == ()
    assert substitutions.chain_for("dev_wholegrain_bread") == ()
    # identity is not a substitution
    assert not substitutions.is_supported_substitution("dev_tofu_firm", "dev_tofu_firm")
    # next_substitute honours exclusions and can run out
    full = frozenset(substitutions.approved_substitutes("dev_tuna_water_drained"))
    assert substitutions.next_substitute("dev_tuna_water_drained", exclude=full) is None


# ── selector: projection + preservation + immutability ──────────────────────

def test_selector_projects_optimizer_result_preserving_macros_and_calories():
    result = _feasible()
    day = selector.assemble_meal_day(CATALOG, result)
    # calorie + macro preservation at day level
    assert day.daily_macros == result.day.daily_totals
    # per-food and per-meal preservation, and food-sum reconciliation
    for projected, optimized in zip(day.meals, result.day.meals):
        assert projected.macros == optimized.totals
        assert len(projected.foods) == len(optimized.foods)
        for pf, of in zip(projected.foods, optimized.foods):
            assert pf.food_id == of.food_id
            assert pf.quantity == of.quantity
            assert pf.grams == of.grams
            assert pf.macros == of.nutrients  # no macro change
            assert pf.display_unit == of.display_unit
            assert pf.display_name_bg and pf.display_name_en
        summed = sum((f.macros.kcal for f in projected.foods), Decimal("0"))
        assert summed == optimized.totals.kcal


def test_selector_output_is_immutable_and_never_invents_foods():
    result = _feasible()
    day = selector.assemble_meal_day(CATALOG, result)
    catalog_ids = {f.food_id for f in CATALOG.foods}
    for meal in day.meals:
        for food in meal.foods:
            assert food.food_id in catalog_ids  # never invents a food
            with pytest.raises(dataclasses.FrozenInstanceError):
                food.grams = Decimal("999")  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            meal.meal_type = "brunch"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        day.daily_macros = Nutrients.zero()  # type: ignore[misc]


def test_selector_is_deterministic_identical_input_identical_output():
    result = _feasible()
    assert selector.assemble_meal_day(CATALOG, result) == selector.assemble_meal_day(CATALOG, result)


def test_selector_refuses_an_infeasible_result():
    infeasible = FeasibilityResult(FeasibilityCode.CALORIE_TARGET_UNREACHABLE, None)
    with pytest.raises(ValueError):
        selector.assemble_meal_day(CATALOG, infeasible)


def test_selector_matches_a_library_meal_by_exact_food_set():
    lib = meal_library.library_meal("lnch_chicken_rice")
    assert selector._match_library_meal("lunch", frozenset(lib.food_ids)) == "lnch_chicken_rice"
    assert selector._match_library_meal("lunch", frozenset({"dev_chicken_breast_cooked"})) is None


# ── Phase 18: Nutrition Knowledge Library + deterministic selection ─────────
def test_nutrition_knowledge_library_is_catalog_backed_complete_and_immutable():
    library = build_nutrition_knowledge_library(CATALOG)

    assert {meal.category for meal in library.meals} == set(meal_library.MEAL_CATEGORIES)
    assert library.catalog_version == CATALOG.version
    assert len({meal.meal_id for meal in library.meals}) == len(library.meals)
    catalog_ids = {food.food_id for food in CATALOG.foods}
    for meal in library.meals:
        assert meal.version == "nutrition-meal-v1"
        assert meal.ingredients and meal.macros.kcal > 0 and meal.tags
        assert all(ingredient.food_id in catalog_ids and ingredient.grams > 0
                   for ingredient in meal.ingredients)
        assert sum((ingredient.macros.kcal for ingredient in meal.ingredients), Decimal("0")) == meal.macros.kcal
    with pytest.raises(dataclasses.FrozenInstanceError):
        library.meals = ()  # type: ignore[misc]


def test_nutrition_knowledge_selection_is_category_scoped_and_deterministic():
    library = build_nutrition_knowledge_library(CATALOG)
    query = MealSelectionQuery("breakfast")

    first = MealSelectionEngine.select(library, query)
    second = MealSelectionEngine.select(library, query)

    assert first == second
    assert [meal.meal_id for meal in first] == sorted(meal.meal_id for meal in first)
    assert all(meal.category == "breakfast" and meal in library.meals for meal in first)


def test_nutrition_knowledge_selection_uses_catalog_macros_and_dietary_constraints():
    library = build_nutrition_knowledge_library(CATALOG)
    post_workout = MealSelectionEngine.select(
        library, MealSelectionQuery(
            "post_workout",
            macro_bounds=MealMacroBounds(protein_min_g=Decimal("58"), kcal_max=Decimal("600")),
        ))
    vegan_lunches = MealSelectionEngine.select(
        library, MealSelectionQuery("lunch", dietary_restrictions=frozenset({"vegan"})))

    assert [meal.meal_id for meal in post_workout] == ["post_chicken_rice"]
    assert post_workout[0].macros.protein_g >= Decimal("58")
    assert [meal.meal_id for meal in vegan_lunches] == ["lnch_tofu_quinoa"]


def test_nutrition_knowledge_selection_honors_blacklists_tags_and_preparation_limits():
    library = build_nutrition_knowledge_library(CATALOG)
    lunch = MealSelectionEngine.select(
        library, MealSelectionQuery("lunch", ingredient_blacklist=frozenset({"dev_chicken_breast_cooked"})))
    pre_workout = MealSelectionEngine.select_one(
        library, MealSelectionQuery(
            "pre_workout",
            required_tags=frozenset({"pre_workout", "carbohydrate_focused"}),
            maximum_preparation_difficulty="no_cook",
        ))

    assert "lnch_chicken_rice" not in {meal.meal_id for meal in lunch}
    assert all("dev_chicken_breast_cooked" not in {item.food_id for item in meal.ingredients}
               for meal in lunch)
    assert pre_workout is not None and pre_workout.meal_id == "pre_banana_oats"
    assert MealSelectionEngine.select(
        library, MealSelectionQuery("dinner", dietary_restrictions=frozenset({"vegan"}))) == ()


# ── practicality: soft penalties only, totals never changed ─────────────────

def _food(food_id, grams):
    f = CATALOG.by_id(food_id)
    factor = Decimal(grams) / Decimal("100")
    n = Nutrients(f.protein_per_100g * factor, f.carbs_per_100g * factor,
                  f.fat_per_100g * factor, f.kcal_per_100g * factor)
    return OptimizedFood(food_id, Decimal(grams), "g", Decimal(grams), n), n


def _meal(meal_type, items):
    foods, nuts = [], Nutrients.zero()
    for fid, g in items:
        of, n = _food(fid, g)
        foods.append(of); nuts = nuts.plus(n)
    return OptimizedMeal(meal_type, tuple(foods), nuts), nuts


def _day(meals):
    total = Nutrients.zero()
    for _, n in meals:
        total = total.plus(n)
    return OptimizedNutritionDay(tuple(m for m, _ in meals), total, (), CATALOG.version, "feasible")


def test_practicality_flags_repeated_protein_and_starch_only_when_avoidable():
    repeated = _day([
        _meal("lunch", [("dev_chicken_breast_cooked", 150), ("dev_rice_cooked", 200), ("dev_broccoli_cooked", 100)]),
        _meal("dinner", [("dev_chicken_breast_cooked", 150), ("dev_rice_cooked", 200), ("dev_broccoli_cooked", 100)]),
    ])
    day = selector.assemble_meal_day(CATALOG, FeasibilityResult(FeasibilityCode.FEASIBLE, repeated))
    assert "repeated_main_protein:dev_chicken_breast_cooked" in day.soft_penalties
    assert "repeated_starch:dev_rice_cooked" in day.soft_penalties
    # penalties are SOFT: totals are still exactly preserved
    assert day.daily_macros == repeated.daily_totals

    distinct = _day([
        _meal("lunch", [("dev_chicken_breast_cooked", 150), ("dev_rice_cooked", 200), ("dev_broccoli_cooked", 100)]),
        _meal("dinner", [("dev_turkey_breast_cooked", 150), ("dev_pasta_cooked", 200), ("dev_broccoli_cooked", 100)]),
    ])
    day2 = selector.assemble_meal_day(CATALOG, FeasibilityResult(FeasibilityCode.FEASIBLE, distinct))
    assert day2.soft_penalties == ()


# ── rotation ────────────────────────────────────────────────────────────────

def test_rotation_is_deterministic_and_avoids_consecutive_repeats():
    first = rotation.rotate_library_days(6)
    second = rotation.rotate_library_days(6)
    assert first == second  # deterministic
    for slot in MEALS:
        picks = [dict(day.meals_by_slot)[slot] for day in first]
        assert rotation.has_no_immediate_repeat(picks)  # alternatives exist -> no repeat


def test_rotate_round_robin_and_single_candidate_behaviour():
    assert rotation.rotate(("a", "b", "c"), 5) == ("a", "b", "c", "a", "b")
    assert rotation.rotate(("a", "b", "c"), 4, start=1) == ("b", "c", "a", "b")
    # a single candidate is allowed to repeat (no alternative to rotate to)
    assert rotation.rotate(("only",), 3) == ("only", "only", "only")
    assert rotation.rotate((), 0) == ()
    with pytest.raises(ValueError):
        rotation.rotate((), 2)


def test_rotation_single_candidate_slot_does_not_raise():
    single = {slot: (meal_library.library_meals_for(slot)[0],) for slot in MEALS}
    days = rotation.rotate_library_days(4, candidates_by_slot=single)
    for slot in MEALS:
        picks = [dict(day.meals_by_slot)[slot] for day in days]
        assert len(set(picks)) == 1  # unavoidable repeat, reported honestly, no crash


# ── isolation / acceptance ──────────────────────────────────────────────────

def test_phase4_modules_have_no_production_network_or_llm_imports():
    package = Path(__file__).parents[1] / "nutrition_engine"
    forbidden = ("import app", "import db", "requests.", "openai", "sqlalchemy",
                 "socket.", "flask", "conversation_composer", "nutrition_validation",
                 "urllib", "httpx")
    for name in ("selector.py", "meal_templates.py", "meal_library.py",
                 "meal_selection.py", "plan_construction.py", "substitutions.py",
                 "rotation.py"):
        source = (package / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{name} references {token}"


# -- Phase 19: deterministic Nutrition Plan Construction Engine ----------------

def test_plan_construction_is_deterministic_and_uses_only_library_candidates():
    request = _construction_request()

    first = NutritionPlanConstructionEngine.construct(request)
    second = NutritionPlanConstructionEngine.construct(request)

    assert first == second
    assert first.plan_id == second.plan_id
    library_ids = {candidate.meal_id for candidate in request.library.meals}
    assert all(meal.candidate.meal_id in library_ids for meal in first.meals)
    assert all(meal.candidate in request.library.meals for meal in first.meals)


def test_plan_construction_calculates_and_allocates_explicit_macro_targets_exactly():
    request = _construction_request()
    targets = calculate_target_macros(request.profile, request.target_policy)
    plan = NutritionPlanConstructionEngine.construct(request)

    assert targets.kcal == Decimal("3009.00")
    assert targets.protein_g == Decimal("144.0")
    assert targets.fat_g == Decimal("83.58333333333333333333333333")
    assert targets.carbs_g == Decimal("420.187500000000000000000000")
    assert plan.target_macros == targets
    assert plan.allocated_macros == targets
    assert sum((meal.target_macros.kcal for meal in plan.meals), Decimal("0")) == targets.kcal
    assert sum((meal.target_macros.protein_g for meal in plan.meals), Decimal("0")) == targets.protein_g
    assert sum((meal.target_macros.carbs_g for meal in plan.meals), Decimal("0")) == targets.carbs_g
    assert sum((meal.target_macros.fat_g for meal in plan.meals), Decimal("0")) == targets.fat_g


def test_plan_construction_prevents_duplicate_meals_and_prefers_variety_when_available():
    plan = NutritionPlanConstructionEngine.construct(_construction_request())

    ids = [meal.candidate.meal_id for meal in plan.meals]
    assert len(ids) == len(set(ids))
    assert all(meal.selection_mode != "duplicate_required" for meal in plan.meals)
    snack_meals = [meal.candidate.meal_id for meal in plan.meals if meal.category == "snack"]
    assert len(snack_meals) == 2 and len(set(snack_meals)) == 2


def test_plan_construction_supports_all_six_meal_categories():
    distribution = (
        MealDistribution("breakfast", Decimal("0.20")),
        MealDistribution("pre_workout", Decimal("0.10")),
        MealDistribution("lunch", Decimal("0.25")),
        MealDistribution("post_workout", Decimal("0.10")),
        MealDistribution("snack", Decimal("0.10")),
        MealDistribution("dinner", Decimal("0.25")),
    )

    plan = NutritionPlanConstructionEngine.construct(_construction_request(distribution=distribution))

    assert tuple(meal.category for meal in plan.meals) == tuple(slot.category for slot in distribution)


def test_plan_construction_uses_selection_fallback_without_inventing_a_meal():
    distribution = (
        MealDistribution("breakfast", Decimal("0.24")),
        MealDistribution("snack", Decimal("0.01")),
        MealDistribution("lunch", Decimal("0.25")),
        MealDistribution("pre_workout", Decimal("0.10")),
        MealDistribution("post_workout", Decimal("0.15")),
        MealDistribution("dinner", Decimal("0.25")),
    )
    request = _construction_request(distribution=distribution)

    plan = NutritionPlanConstructionEngine.construct(request)

    fallback = next(meal for meal in plan.meals if meal.category == "snack")
    assert fallback.selection_mode == "fallback"
    assert fallback.candidate in request.library.meals


def test_plan_construction_rejects_missing_verified_facts_and_unsuitable_blueprints():
    with pytest.raises(NutritionConstructionError, match="gender"):
        calculate_target_macros(
            ImmutableUserProfile.from_verified_facts({
                "age": "30", "height": "180", "weight": "80", "goal": "muscle_gain",
                "activityLevel": "moderate",
            }),
            TARGET_POLICY,
        )

    workout = dataclasses.replace(_nutrition_recommendation(), intent=RecommendationIntent.WORKOUT)
    with pytest.raises(NutritionConstructionError, match="nutrition recommendation"):
        NutritionConstructionRequest(
            recommendation=workout,
            profile=_phase19_profile(),
            library=build_nutrition_knowledge_library(CATALOG),
            target_policy=TARGET_POLICY,
            meal_distribution=(
                MealDistribution("breakfast", Decimal("0.30")),
                MealDistribution("lunch", Decimal("0.35")),
                MealDistribution("dinner", Decimal("0.35")),
            ),
        )
