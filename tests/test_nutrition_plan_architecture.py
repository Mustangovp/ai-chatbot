"""08B: real catalog/optimizer composition and factual delivery contracts."""
from decimal import Decimal

import pytest

import nutrition_plan as plans
from nutrition_validation import NutritionTargets
from tests.test_nutrition_fallback_production import _catalog, _identity, LEGACY_IDENTITY
from tests.test_nutrition_reliability import GOALS, _payload
from tests.test_chat_enforcement import _NUTRITION_TARGETS


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_observed_3212_plan_does_not_append_a_second_starch_or_fifth_food(lang):
    # Production supplied this kcal boundary, not a known protein target.
    plan = plans.build_source_backed_plan(NutritionTargets(Decimal("3212")), lang,
                                          restrictions=(), profile={"goal": "muscle_gain"})
    assert plan is not None
    catalog = _catalog()
    for meal in plan.meals:
        assert len(meal.foods) <= 4
        assert sum(catalog.by_id(food.food_id).category == "carbohydrate" for food in meal.foods) <= 1
        for food in meal.foods:
            source = catalog.by_id(food.food_id)
            assert source.minimum_portion <= food.grams <= source.maximum_portion
            assert meal.meal_type in source.allowed_meals
            factor = food.grams / Decimal("100")
            assert food.macros.protein_g == source.protein_per_100g * factor
            assert food.macros.carbs_g == source.carbs_per_100g * factor
            assert food.macros.fat_g == source.fat_per_100g * factor
            assert food.macros.kcal == source.kcal_per_100g * factor
    assert plans.from_record(plans.to_record(plan)) is not None


def test_high_target_grows_multiple_meals_without_changing_food_identity(monkeypatch):
    from nutrition_engine import service

    original, results = service.build_nutrition_plan, []

    def observe(request, **kwargs):
        result = original(request, **kwargs)
        if result.projection is not None:
            results.append((request, result.projection))
        return result

    monkeypatch.setattr(service, "build_nutrition_plan", observe)
    catalog = _catalog()
    plan = plans._build_source_backed_candidate(NutritionTargets(Decimal("3212")), "en",
                                              restrictions=(), catalog=catalog)
    assert plan is not None
    base_request, base = results[0]
    assert base_request.targets.calories_target == Decimal("2500")
    labels = {"Breakfast": "breakfast", "Lunch": "lunch", "Dinner": "dinner"}
    names = {food.display_name_en: food for food in catalog.foods}
    increased_meals = set()
    for meal in base.meals:
        delivered = next(item for item in plan.meals if item.meal_type == labels[meal.label])
        assert {food.food_id for food in delivered.foods} == {names[food.name].food_id for food in meal.foods}
        for food in meal.foods:
            source = names[food.name]
            grams = food.quantity * source.grams_per_piece if food.unit == "pcs" else food.quantity
            actual = next(item for item in delivered.foods if item.food_id == source.food_id)
            assert grams <= actual.grams <= source.maximum_portion
            if actual.grams > grams:
                increased_meals.add(delivered.meal_type)
    assert len(increased_meals) >= 2
    assert increased_meals != {"dinner"}
    assert all(request.targets.protein_max_g is None for request, _ in results)


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_optional_snack_is_used_when_main_meal_catalog_capacity_is_insufficient(monkeypatch, lang):
    from nutrition_engine import catalog as catalogs
    from nutrition_engine.catalog import Catalog

    catalog = _catalog()
    ids = {food_id for meal in LEGACY_IDENTITY for food_id in meal}
    limited = Catalog(catalog.version, tuple(food for food in catalog.foods if food.food_id in ids))
    monkeypatch.setattr(catalogs, "load_catalog_file", lambda *_args: limited)
    target = NutritionTargets(Decimal("3600"))
    plan = plans.build_source_backed_plan(target, lang, restrictions=(), profile={"goal": "muscle_gain"})
    assert plan is not None
    assert [meal.meal_type for meal in plan.meals] == ["breakfast", "snack", "lunch", "dinner"]
    snack = plan.meals[1]
    assert all("snack" in limited.by_id(food.food_id).allowed_meals for food in snack.foods)
    assert all(len(meal.foods) <= 4 for meal in plan.meals)
    main_capacity = Decimal("0")
    for meal in (item for item in plan.meals if item.meal_type != "snack"):
        for food in meal.foods:
            source = limited.by_id(food.food_id)
            grams = source.maximum_portion if source.category in {"carbohydrate", "fruit", "fat"} else food.grams
            if source.food_id == "dev_olive_oil":
                grams = Decimal("20")  # Existing aggregate quality limit 40g / two main meals.
            main_capacity += source.kcal_per_100g * grams / Decimal("100")
    assert main_capacity < target.kcal * Decimal("0.95")
    assert plans.from_record(plans.to_record(plan)) is not None


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_high_target_with_confirmed_protein_is_feasible(monkeypatch, lang):
    from nutrition_engine import service
    from nutrition_engine.models import PracticalityPolicy

    original, results = service.build_nutrition_plan, []

    def observe(request, **kwargs):
        result = original(request, **kwargs)
        results.append((request, result))
        return result

    monkeypatch.setattr(service, "build_nutrition_plan", observe)
    targets = NutritionTargets(Decimal("3212"), Decimal("180"))
    plan = plans.build_source_backed_plan(targets, lang, restrictions=(), profile={"goal": "muscle_gain"})
    assert plan is not None
    assert plan.targets == targets
    assert plans.from_record(plans.to_record(plan)) is not None
    expansions = [(request, result) for request, result in results if request.targets.calories_target == targets.kcal]
    assert len(expansions) >= 2
    # Reproduce the actual boundary: service success is not canonical success.
    assert expansions[0][1].projection.daily_totals.protein_g > targets.protein * Decimal("1.05")
    assert abs(plan.totals.protein_g - targets.protein) <= targets.protein * Decimal("0.05")
    assert abs(plan.totals.kcal - targets.kcal) <= targets.kcal * Decimal("0.05")
    assert all(request.targets.protein_min_g == targets.protein for request, _ in results)
    assert all(request.targets.protein_max_g is None for request, _ in results)
    assert all(request.targets.calories_tolerance == Decimal("0.05") for request, _ in results)
    assert all(request.practicality_policy.max_search_nodes == 200_000 for request, _ in results)
    assert PracticalityPolicy(maximum_foods_per_meal=4).max_search_nodes == 1_000_000
    catalog = _catalog()
    base = next(result for request, result in results if request.targets.calories_target == Decimal("2500")
                and result.projection is not None and result.projection.daily_totals.protein_g <= Decimal("189"))
    for meal, original_meal in zip((meal for meal in plan.meals if meal.meal_type != "snack"), base.source_day.meals):
        assert {food.food_id for food in meal.foods} == {food.food_id for food in original_meal.foods}
    assert any(meal.meal_type == "snack" for meal in plan.meals)
    for meal in plan.meals:
        assert len(meal.foods) <= 4
        assert sum(catalog.by_id(food.food_id).category == "carbohydrate" for food in meal.foods) <= 1
        for food in meal.foods:
            source = catalog.by_id(food.food_id)
            assert source.minimum_portion <= food.grams <= source.maximum_portion
            assert meal.meal_type in source.allowed_meals
            assert food.macros.kcal == source.kcal_per_100g * food.grams / Decimal("100")
            assert food.macros.protein_g == source.protein_per_100g * food.grams / Decimal("100")


@pytest.mark.parametrize("goal", GOALS)
@pytest.mark.parametrize("lang", ["bg", "en"])
def test_explanation_uses_only_actual_goal_targets_and_plan_facts(goal, lang):
    plan = plans.build_plan(_payload(lang), _NUTRITION_TARGETS, restrictions=(), provenance={})
    before = plans.to_record(plan)
    delivered = plans.render_delivery(plan, lang, profile={"goal": goal, "healthNotes": "private unused context"})
    title = "**Why this plan:**" if lang == "en" else "**Защо този план:**"
    explanation = delivered.split(title, 1)[1]
    assert plans._selection_goal({"goal": goal}) == goal
    assert "2800 kcal" in explanation and "175" in explanation
    assert "private unused context" not in delivered
    assert "APEX rationale" not in delivered and "APEX логика" not in delivered
    for term in ("tolerance", "validation", "provenance", "optimal", "perfect", "burns fat", "boosts metabolism",
                 "guarantees", "clinically", "improves recovery", "допуск", "оптимал", "перфект", "изгаря мазнини"):
        assert term not in explanation.lower()
    assert 2 <= explanation.count(".") <= 3
    assert all(plans._meal_reason(meal, plan.targets, lang) == "" for meal in plan.meals)
    assert plans.to_record(plan) == before


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_missing_goal_or_protein_does_not_invent_them_in_explanation(lang):
    plan = plans.build_plan(_payload(lang), NutritionTargets(Decimal("2800")), restrictions=(), provenance={})
    explanation = plans._plan_explanation(plan, lang, {})
    assert "2800" in explanation
    assert "175" not in explanation and "180" not in explanation
    assert "fat loss" not in explanation and "muscle gain" not in explanation
    assert "сваляне" not in explanation and "покачване" not in explanation


def test_pork_label_is_presentation_only_and_keeps_source_identity():
    catalog = _catalog()
    pork = catalog.by_id("dev_lean_pork_cooked")
    assert plans._catalog_display_name(pork, "bg") == "Постен свински котлет"
    assert plans._catalog_display_name(pork, "en") == pork.display_name_en
    targets = NutritionTargets(Decimal("2000"), Decimal("160"))
    plan = plans.build_source_backed_plan(targets, "bg", restrictions=(), profile={"goal": "muscle_gain"})
    assert plan is not None
    food = next(food for meal in plan.meals for food in meal.foods if food.food_id == pork.food_id)
    assert food.catalog_id == pork.food_id and food.measurement_state.value == plans._catalog_measurement_state(pork)
    assert food.macros.kcal == pork.kcal_per_100g * food.grams / Decimal("100")
    assert food.display_name == "Постен свински котлет"
    assert "Свинска пържола, постна" not in plans.render_delivery(plan, "bg")
    assert dict(plan.provenance)["catalog_version"] == catalog.version
    assert catalog.by_id(pork.food_id) == pork
    context = plans.recent_nutrition_context([{"plan": plans.to_record(plan)}])
    candidates = list(plans._fallback_catalogs(catalog, "muscle_gain", context))
    assert candidates and all(food == catalog.by_id(food.food_id) for item in candidates for food in item.foods)


@pytest.mark.parametrize("goal", GOALS)
def test_confirmed_high_calorie_only_targets_remain_deterministic(goal):
    targets = NutritionTargets(Decimal("3212"))
    first = plans.build_source_backed_plan(targets, "en", restrictions=(), profile={"goal": goal})
    second = plans.build_source_backed_plan(targets, "en", restrictions=(), profile={"goal": goal})
    assert first is not None and second is not None
    assert _identity(first) == _identity(second)
    assert tuple(food.grams for meal in first.meals for food in meal.foods) == tuple(
        food.grams for meal in second.meals for food in meal.foods)
    assert first.targets == targets
    assert all(len(meal.foods) <= 4 for meal in first.meals)
