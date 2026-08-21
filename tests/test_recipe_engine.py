from decimal import Decimal
import base64
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

import nutrition_plan
from nutrition_validation import NutritionTargets
from recipe_engine.recipe_engine import match_plan
from recipe_engine.recipe_library import load_recipes
from recipe_engine.recipe_matcher import (
    match_meal,
    profile_equipment,
    validate_recipe_for_meal,
)
from recipe_engine.recipe_renderer import assembly_token, recipe_token


def _food(food_id, name, grams, protein, carbs, fat, kcal, state):
    return {
        "food_id": food_id,
        "display_name": name,
        "grams": str(grams),
        "measurement_state": state,
        "protein_g": str(protein),
        "carbs_g": str(carbs),
        "fat_g": str(fat),
        "kcal": str(kcal),
    }


def _plan():
    payload = {"meals": [
        {"meal_type": "breakfast", "foods": [
            _food("eggs", "Eggs", 200, 40, 0, 20, 340, "raw"),
            _food("oats", "Oats", 100, 15, 90, 7, 450, "raw"),
            _food("banana", "Banana", 120, 1, 28, 0, 120, "ready_to_eat"),
            _food("milk", "Milk", 250, 8, 12, 8, 150, "raw"),
        ]},
        {"meal_type": "lunch", "foods": [
            _food("chicken", "Chicken breast", 200, 60, 0, 12, 360, "raw"),
            _food("rice", "Rice", 200, 5, 55, 1, 250, "cooked"),
            _food("broccoli", "Broccoli", 100, 3, 7, 0, 35, "cooked"),
        ]},
        {"meal_type": "dinner", "foods": [
            _food("salmon", "Salmon", 180, 40, 0, 24, 380, "raw"),
            _food("quinoa", "Quinoa", 180, 8, 38, 6, 250, "cooked"),
            _food("spinach", "Spinach", 80, 2, 3, 0, 25, "ready_to_eat"),
            _food("olives", "Olives", 30, 0, 2, 5, 55, "ready_to_eat"),
        ]},
    ]}
    return nutrition_plan.build_plan(
        payload,
        NutritionTargets(Decimal("2415"), Decimal("182"), Decimal("235"), Decimal("83")),
        restrictions=(), provenance={"test": "recipe"}, language="en",
    )


def _recipe(recipe_id):
    return next(recipe for recipe in load_recipes() if recipe.id == recipe_id)


def test_recipe_library_is_small_and_curated():
    recipes = load_recipes()
    assert 20 <= len(recipes) <= 25
    assert all(recipe.food_ids for recipe in recipes)
    assert all(1 <= len(recipe.steps) <= 6 for recipe in recipes)
    assert all(1 <= len(recipe.healthy_cooking_tips) <= 3 for recipe in recipes)


def test_recipe_matching_is_deterministic_and_preserves_plan_macros():
    plan = _plan()
    before = tuple((meal.id, meal.macros, tuple((food.id, food.macros) for food in meal.foods)) for meal in plan.meals)

    first = match_plan(plan, {"cooking_equipment": ["pan", "oven"]})
    second = match_plan(plan, {"cooking_equipment": ["pan", "oven"]})

    assert {key: value.recipe.id for key, value in first.items()} == {
        key: value.recipe.id for key, value in second.items()
    }
    assert [item.recipe.id for item in first.values()] == ["breakfast-eggs-oats", "dinner-salmon-quinoa"]
    assert before == tuple((meal.id, meal.macros, tuple((food.id, food.macros) for food in meal.foods)) for meal in plan.meals)


def test_recipe_token_carries_the_immutable_meal_id_and_recipe_food_identity():
    meal_id, recipe_match = next(iter(match_plan(_plan(), {"cooking_equipment": ["pan", "oven"]}).items()))
    payload = json.loads(base64.b64decode(recipe_token(recipe_match, meal_id).removeprefix("recipe:")))
    assert payload["meal_id"] == meal_id
    assert payload["id"] == recipe_match.recipe.id
    assert payload["food_ids"] == list(recipe_match.recipe.food_ids)
    assert payload["preparation_type"] == "recipe"
    assert payload["substitutions"]


def _delivery_preparation_payloads(delivery: str):
    return [
        json.loads(base64.b64decode(token.removeprefix("recipe:")))
        for token in delivery.split()
        if token.startswith("recipe:")
    ]


def test_main_meals_receive_safe_assembly_when_no_exact_recipe_matches(monkeypatch):
    plan = _plan()
    monkeypatch.setattr("recipe_engine.recipe_engine.match_plan", lambda *_args, **_kwargs: {})
    delivery = nutrition_plan.render_delivery(plan, "en", {})
    preparations = _delivery_preparation_payloads(delivery)

    assert len(preparations) == 2
    assert {item["preparation_type"] for item in preparations} == {"assembly"}
    assert all("Serve the listed components" not in " ".join(item["steps"])
               for item in preparations)
    assert all(item["substitutions"] == [] for item in preparations)


def test_food_aware_assembly_and_raw_weight_labels_are_bounded():
    meal = SimpleNamespace(id="meal-1", name="Breakfast", foods=(
        SimpleNamespace(food_id="dev_egg_whites"), SimpleNamespace(food_id="dev_oats_dry"),
        SimpleNamespace(food_id="dev_apple"),
    ))
    payload = json.loads(base64.b64decode(assembly_token(meal, "en").removeprefix("recipe:")))
    steps = " ".join(payload["steps"])
    assert "egg whites separately" in steps and "oats separately" in steps and "fruit separately" in steps
    assert not any(word in steps.lower() for word in ("minute", "temperature", "spice", "sauce", "listed components"))
    food = nutrition_plan.NutritionFood("food", None, "Pasteurized egg whites", Decimal("300"), nutrition_plan.NutritionMacros.zero(), "dev_egg_whites", nutrition_plan.MeasurementState.RAW)
    assert nutrition_plan._quantity_label(food, "en") == "300 g, measured before preparation"
    assert nutrition_plan._quantity_label(food, "bg") == "300 г, измерени преди приготвяне"
    apple = nutrition_plan.NutritionFood("apple", None, "Apple", Decimal("150"), nutrition_plan.NutritionMacros.zero(), "apple", nutrition_plan.MeasurementState.RAW)
    assert "raw weight" in nutrition_plan._quantity_label(apple, "en")


def test_unknown_assembly_emits_no_preparation_token():
    meal = SimpleNamespace(id="unknown", name="Dinner", foods=(SimpleNamespace(food_id="unclassified"),))
    assert assembly_token(meal, "en") is None


def test_source_backed_fallback_prefers_one_starch_but_keeps_feasibility_option():
    dinner = ({"food_id": "dev_turkey_breast_cooked"}, {"food_id": "dev_pasta_cooked"})

    additions = nutrition_plan._source_backed_dinner_additions(dinner)

    # A non-starch calorie closer is considered first when dinner already has
    # pasta. The other starch remains available for a genuinely infeasible gap.
    assert additions == ("dev_olive_oil", "dev_rice_cooked")
    assert "dev_pasta_cooked" not in additions
    assert nutrition_plan._source_backed_dinner_additions(dinner) == additions


def test_recipe_matching_preserves_curated_substitutions_and_uses_recipe_presentation():
    plan = _plan()
    delivery = nutrition_plan.render_delivery(plan, "en", {"cooking_equipment": ["pan", "oven"]})
    preparations = _delivery_preparation_payloads(delivery)

    recipes = [item for item in preparations if item["preparation_type"] == "recipe"]
    assemblies = [item for item in preparations if item["preparation_type"] == "assembly"]
    assert {item["id"] for item in recipes} == {"breakfast-eggs-oats", "dinner-salmon-quinoa"}
    assert all(item["substitutions"] for item in recipes)
    assert len(assemblies) == 1


def test_meal_preparation_survives_structured_plan_persistence_and_reloads_localized(monkeypatch):
    plan = _plan()
    restored = nutrition_plan.from_record(nutrition_plan.to_record(plan))

    assert [meal.preparation_type for meal in restored.meals] == ["assembly", "assembly", "assembly"]
    assert "preparation_type" in nutrition_plan.to_record(plan)["meals"][0]
    monkeypatch.setattr("recipe_engine.recipe_engine.match_plan", lambda *_args, **_kwargs: {})
    delivery = nutrition_plan.render_delivery(restored, "bg", {})
    preparations = _delivery_preparation_payloads(delivery)
    assert all(item["preparation_type"] == "assembly" for item in preparations)
    assert all("Сервирай посочените компоненти" not in " ".join(item["steps"])
               for item in preparations)


def test_exact_meal_identity_rejects_recipe_with_an_absent_ingredient():
    meal = _plan().meals[0]
    assert validate_recipe_for_meal(_recipe("breakfast-yogurt-oats"), meal)
    assert match_meal(meal, (_recipe("breakfast-yogurt-oats"),), profile_equipment({})) is None


def test_recipe_with_missing_significant_meal_food_is_hidden():
    meal = _plan().meals[0]
    assert match_meal(meal, (_recipe("breakfast-eggs-yogurt-oats-apple"),), profile_equipment({})) is None


def test_legacy_free_prose_substitution_is_never_delivered():
    meal = _plan().meals[1]
    recipe = _recipe("lunch-chicken-rice")
    assert "substitution" in validate_recipe_for_meal(recipe, meal)
    assert match_meal(meal, (recipe,), profile_equipment({})) is None


def test_recipe_prose_cannot_introduce_a_caloric_food_not_in_the_meal():
    meal = _plan().meals[-1]
    recipe = replace(_recipe("dinner-salmon-quinoa"), steps=(
        "Cook the quinoa.", "Bake the salmon.", "Serve with spinach, olives, and avocado.",
    ))
    reason = validate_recipe_for_meal(recipe, meal)
    assert reason is not None and "absent" in reason
    assert match_meal(meal, (recipe,), profile_equipment({})) is None


def test_invalid_recipe_falls_back_to_the_valid_meal_card_without_a_recipe_token():
    plan = _plan()
    matches = match_plan(plan, {"cooking_equipment": ["pan", "oven"]})
    rendered = nutrition_plan.render(plan, "en", {meal_id: "recipe:ok" for meal_id in matches})
    assert "Chicken breast" in rendered
    assert "recipe:ok" not in next(line for line in rendered.splitlines() if "Chicken breast" in line)


def test_measurement_state_is_required_for_ambiguous_foods():
    payload = {"meals": [
        {"meal_type": "breakfast", "foods": [_food("eggs", "Eggs", 100, 20, 0, 10, 180, "raw"),
                                             {"food_id": "oats", "display_name": "Oats", "grams": "50", "protein_g": "5", "carbs_g": "30", "fat_g": "3", "kcal": "170"}]},
        {"meal_type": "lunch", "foods": [_food("chicken", "Chicken", 100, 20, 0, 5, 150, "raw")]},
        {"meal_type": "dinner", "foods": [_food("salmon", "Salmon", 100, 20, 0, 10, 200, "raw")]},
    ]}
    with pytest.raises(nutrition_plan.NutritionPlanError, match="measurement_state"):
        nutrition_plan.build_plan(payload, NutritionTargets(Decimal("700"), Decimal("65"), Decimal("30"), Decimal("28")), restrictions=(), provenance={})


def test_measurement_state_is_required_for_frozen_foods_and_unlisted_fish():
    with pytest.raises(nutrition_plan.NutritionPlanError, match="measurement_state"):
        nutrition_plan._measurement_state(None, "frozen_broccoli")
    with pytest.raises(nutrition_plan.NutritionPlanError, match="measurement_state"):
        nutrition_plan._measurement_state(None, "white_fish")


def test_measurement_state_renders_in_bulgarian_and_english_without_raw_enum_values():
    plan = _plan()
    english = nutrition_plan.render(plan, "en")
    bulgarian = nutrition_plan.render(plan, "bg")
    assert "100 g, raw weight" in english
    assert "raw" not in bulgarian.lower()
    assert "сурово тегло" in bulgarian


def test_target_status_reports_within_tolerance_not_exact():
    totals = nutrition_plan.NutritionMacros(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("2458"))
    status = nutrition_plan.target_status(totals, NutritionTargets(Decimal("2559"), None, None, None))
    assert status is nutrition_plan.PlanTargetStatus.WITHIN_TOLERANCE


def test_target_status_rejects_outside_current_approved_tolerance():
    totals = nutrition_plan.NutritionMacros(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("2400"))
    assert nutrition_plan.target_status(totals, NutritionTargets(Decimal("2559"), None, None, None)) is nutrition_plan.PlanTargetStatus.OUTSIDE_TOLERANCE


def test_delivery_rationale_does_not_expose_internal_tolerance_wording():
    targets = NutritionTargets(Decimal("2559"), None, None, None)
    totals = nutrition_plan.NutritionMacros(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("2458"))
    plan = nutrition_plan.NutritionPlan(
        id="status-plan", version="nutrition-plan-v1", created_at_utc="2026-01-01T00:00:00+00:00",
        targets=targets, restrictions=(), meals=(), totals=totals, provenance=(),
        target_status=nutrition_plan.PlanTargetStatus.WITHIN_TOLERANCE,
    )
    delivery = nutrition_plan.render_delivery(plan, "en")
    assert "approved target tolerance" not in delivery
    assert "exactly meets the confirmed target" not in delivery


def test_equipment_filter_still_applies_after_identity_validation():
    dinner = _plan().meals[-1]
    assert match_meal(dinner, (_recipe("dinner-salmon-quinoa"),), frozenset({"pan"})) is None
    assert match_meal(dinner, (_recipe("dinner-salmon-quinoa"),), frozenset({"oven", "pan"})).recipe.id == "dinner-salmon-quinoa"


def test_unknown_food_never_receives_a_recipe():
    meal = SimpleNamespace(meal_type="dinner", foods=(SimpleNamespace(food_id="prawns", display_name="Prawns"),))
    assert match_meal(meal, load_recipes(), profile_equipment({})) is None
