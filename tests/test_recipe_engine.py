from decimal import Decimal
import base64
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

import nutrition_plan
import nutrition_followups
from nutrition_validation import NutritionTargets
from recipe_engine.recipe_engine import match_plan
from recipe_engine.recipe_library import load_recipes
from recipe_engine.recipe_matcher import (
    match_meal,
    profile_equipment,
    validate_recipe_for_meal,
)
from recipe_engine.recipe_renderer import recipe_token


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


def test_daily_totals_use_structured_plan_totals_not_the_last_meal_fields():
    payload = {"meals": [
        {"meal_type": "breakfast", "foods": [
            _food("egg_whites", "Egg whites", 300, 33, 2, 0, 156, "raw"),
            _food("oats", "Oats", 150, 19.5, 99.5, 10.5, 584, "raw"),
            _food("apple", "Apple", 150, 0.5, 21, 0, 80, "ready_to_eat"),
        ]},
        {"meal_type": "lunch", "foods": [
            _food("chicken", "Chicken", 300, 93, 0, 11, 495, "cooked"),
            _food("rice", "Rice", 200, 5, 56, 1, 260, "cooked"),
            _food("zucchini", "Zucchini", 75, 1, 3, 0, 15, "cooked"),
            _food("olive_oil", "Olive oil", 5, 0, 0, 5, 45, "raw"),
        ]},
        {"meal_type": "dinner", "foods": [
            _food("turkey", "Turkey", 300, 87, 0, 6, 450, "cooked"),
            _food("pasta", "Pasta", 200, 10, 60, 2, 300, "cooked"),
            _food("zucchini", "Zucchini", 75, 1, 3, 0, 15, "cooked"),
            _food("olive_oil", "Olive oil", 5, 0, 0, 5, 45, "raw"),
            _food("rice", "Rice", 100, 2.5, 28, 0.5, 130, "cooked"),
        ]},
    ]}
    plan = nutrition_plan.build_plan(
        payload, NutritionTargets(Decimal("2575"), Decimal("252.5"), Decimal("272.5"), Decimal("41")),
        restrictions=(), provenance={"test": "daily-totals"}, language="en",
    )

    total_row = nutrition_plan.render(plan, "en").splitlines()[-1]

    assert plan.totals == nutrition_plan.NutritionMacros(Decimal("252.5"), Decimal("272.5"), Decimal("41"), Decimal("2575"))
    assert "| Daily Total | | | | | 252.5 | 272.5 | 41 | 2575 | |" == total_row
    assert "| 100.5 | 91 | 13.5 | 940 |" not in total_row


def test_recent_nutrition_context_uses_only_valid_structured_records():
    record = nutrition_plan.to_record(_plan())
    context = nutrition_plan.recent_nutrition_context(({"plan": record}, {"plan": {"broken": True}}))

    assert context.recent_plan_count == 1
    assert context.available
    assert ("lunch", ("Chicken breast", "Rice", "Broccoli")) in context.recent_meals
    contract = nutrition_plan.generation_contract(_plan().targets, "en", context)
    assert "RECENT STRUCTURED PLAN CONTEXT" in contract
    assert "Chicken breast, Rice, Broccoli" in contract
    assert "Repetition is allowed" in contract


def _recipe(recipe_id):
    return next(recipe for recipe in load_recipes() if recipe.id == recipe_id)


def test_recipe_library_is_small_and_curated():
    recipes = load_recipes()
    assert 20 <= len(recipes) <= 25
    assert all(recipe.food_ids for recipe in recipes)
    assert all(1 <= len(recipe.steps) <= 6 for recipe in recipes)
    assert all(1 <= len(recipe.healthy_cooking_tips) <= 3 for recipe in recipes)


@pytest.mark.parametrize("message", [
    "имаш ли рецепта за вечерята?",
    "give me the dinner recipe",
])
def test_recipe_followup_resolver_returns_the_exact_curated_plan_delivery(message):
    result = nutrition_followups.resolve(
        message=message, language="en", profile={"cooking_equipment": ["pan", "oven"]},
        active_plan_loader=_plan,
    )
    assert result.outcome is nutrition_followups.NutritionFollowupOutcome.CURATED_RECIPE_AVAILABLE
    assert result.reply and "recipe:" in result.reply


@pytest.mark.parametrize("message", [
    "с какво мога да заменя спанака?",
    "What can I replace spinach with?",
])
def test_substitution_followup_resolver_returns_only_curated_substitution(message):
    result = nutrition_followups.resolve(
        message=message, language="bg", profile={"cooking_equipment": ["pan", "oven"]},
        active_plan_loader=_plan,
    )
    assert result.outcome is nutrition_followups.NutritionFollowupOutcome.SUBSTITUTION_AVAILABLE
    assert result.reply == "Спанакът може да се смени с броколи само в одобреното количество."


def test_meal_only_language_is_not_recipe_owned_without_pending_state():
    result = nutrition_followups.resolve(
        message="What should I eat for dinner?", language="en", profile={}, active_plan_loader=_plan,
    )
    assert result.outcome is nutrition_followups.NutritionFollowupOutcome.NO_MATCH


def test_recipe_meal_continuation_requires_and_consumes_closed_pending_state():
    pending = nutrition_followups.resolve(
        message="Имаш ли рецепта?", language="bg", profile={}, active_plan_loader=_plan,
    )
    assert pending.outcome is nutrition_followups.NutritionFollowupOutcome.AMBIGUOUS_MEAL
    assert pending.next_pending_state == nutrition_followups.PENDING_RECIPE_MEAL_REQUIRED
    resolved = nutrition_followups.resolve(
        message="за вечерята", language="bg", profile={"cooking_equipment": ["pan", "oven"]},
        active_plan_loader=_plan, pending_state=pending.next_pending_state,
    )
    assert resolved.outcome is nutrition_followups.NutritionFollowupOutcome.CURATED_RECIPE_AVAILABLE


@pytest.mark.parametrize(("message", "outcome"), [
    ("replace salmon", nutrition_followups.NutritionFollowupOutcome.SUBSTITUTION_UNAVAILABLE),
    ("replace tomato in dinner", nutrition_followups.NutritionFollowupOutcome.SOURCE_FOOD_NOT_IN_MEAL),
])
def test_substitution_unavailable_states_are_closed_and_never_recipe_delivery(message, outcome):
    result = nutrition_followups.resolve(
        message=message, language="en", profile={"cooking_equipment": ["pan", "oven"]},
        active_plan_loader=_plan,
    )
    assert result.outcome is outcome
    assert result.reply and "recipe:" not in result.reply


def test_recipe_followup_requires_an_active_plan_after_intent_is_recognized():
    result = nutrition_followups.resolve(
        message="Do you have a recipe for dinner?", language="en", profile={},
        active_plan_loader=lambda: None,
    )
    assert result.outcome is nutrition_followups.NutritionFollowupOutcome.NO_ACTIVE_PLAN


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

    assert len(preparations) == 3
    assert {item["preparation_type"] for item in preparations} == {"assembly"}
    assert all(item["steps"] == ["Serve the listed components in the stated quantities."]
               for item in preparations)
    assert all(item["substitutions"] == [] for item in preparations)


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
    assert all(item["steps"] == ["Сервирай посочените компоненти в дадените количества."]
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
