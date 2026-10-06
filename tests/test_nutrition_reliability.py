"""Task 08A: real generation/repair boundary and bounded catalog recovery."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

import app as appmod
import db as store
import nutrition_plan as plans
from nutrition_engine.catalog import CatalogGovernance, load_catalog_file
from nutrition_validation import NutritionTargets
from tests.test_chat_enforcement import (
    client, captured, _enforce_off_by_default, _isolated_learning_worker,
    _events, _login_for_chat, _post, _profile, _set_sequence_stream,
    _structured_plan_payload, _StructuredCompletion, _NUTRITION_TARGETS,
)


GOALS = ("fat_loss", "muscle_gain", "strength", "endurance", "general")
TARGET_BLOCK = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day\nCarbohydrate target: 350g\nFat target: 78g"
CATALOG_PATH = Path(__file__).parents[1] / "nutrition_engine/data/food_catalog_v1.json"


def _payload(lang="en"):
    payload = _structured_plan_payload()
    if lang == "bg":
        names = {"eggs": "Яйца", "oats": "Овесени ядки", "chicken": "Пилешки гърди",
                 "rice": "Ориз", "salmon": "Сьомга", "potatoes": "Картофи"}
        for meal in payload["meals"]:
            for food in meal["foods"]:
                food["display_name"] = names[food["food_id"]]
    return payload


@pytest.mark.parametrize("bad_id", [None, "", "   ", 17])
def test_generated_food_id_is_required_without_breaking_legacy_records(bad_id):
    payload = _payload()
    payload["meals"][0]["foods"][0]["food_id"] = bad_id
    with pytest.raises(plans.NutritionPlanError, match="food.food_id must be a non-empty string"):
        plans.parse_generation_response(_StructuredCompletion(payload))
    legacy = _payload()
    for meal in legacy["meals"]:
        for food in meal["foods"]:
            food.pop("food_id")
    with pytest.raises(plans.NutritionPlanError, match="food.food_id"):
        plans.parse_generation_response(_StructuredCompletion(legacy))
    plan = plans.build_plan(legacy, _NUTRITION_TARGETS, restrictions=(), provenance={})
    assert plans.from_record(plans.to_record(plan)) is not None


@pytest.mark.parametrize("failure", ["missing_id", "empty_id", "outside_target"])
@pytest.mark.parametrize("lang", ["bg", "en"])
def test_chat_repairs_production_failures_and_persists_only_valid_plan(
        client, captured, monkeypatch, failure, lang):
    profile = {**_profile(), "goal": "fat_loss", "language": lang}
    uid = _login_for_chat(client, profile)
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *_args: TARGET_BLOCK)
    valid = _payload(lang)
    invalid = deepcopy(valid)
    if failure == "missing_id":
        invalid["meals"][0]["foods"][0].pop("food_id")
    elif failure == "empty_id":
        invalid["meals"][0]["foods"][0]["food_id"] = ""
    else:
        invalid["meals"][-1]["foods"][-1]["kcal"] = "100"
    calls = _set_sequence_stream(monkeypatch, captured, [invalid, valid])
    events = _events(_post(client, "Give me a full-day nutrition plan", lang=lang))
    assert events[-1] == {"done": True}
    assert len(calls) == 2
    repair = calls[1]["messages"][-1]["content"]
    assert ("kcal is outside" if failure == "outside_target" else "food.food_id") in repair
    assert "food_id MUST be a non-empty" in repair
    assert "Check kcal and EVERY specified macro independently" in repair
    assert "protein 175g; carbs 350g; fat 78g" in repair
    assert "lower-energy-density" in repair
    records = store.list_nutrition_plans(uid)
    assert len(records) == 1
    assert records[0]["plan"]["totals"]["kcal"] == "2800"
    assert all(food["food_id"] for meal in records[0]["plan"]["meals"] for food in meal["foods"])
    assert "APEX rationale" not in events[0]["t"] and "APEX логика" not in events[0]["t"]


@pytest.mark.parametrize("field", ["kcal", "protein_g", "carbs_g", "fat_g"])
@pytest.mark.parametrize("factor,accepted", [("0.95", True), ("1.05", True), ("0.9499", False), ("1.0501", False)])
def test_existing_five_percent_authority_is_unchanged(field, factor, accepted):
    payload = _payload()
    for meal in payload["meals"]:
        for food in meal["foods"]:
            food[field] = str(Decimal(food[field]) * Decimal(factor))
    if accepted:
        assert plans.build_plan(payload, _NUTRITION_TARGETS, restrictions=(), provenance={})
    else:
        with pytest.raises(plans.NutritionPlanError, match="outside the confirmed target"):
            plans.build_plan(payload, _NUTRITION_TARGETS, restrictions=(), provenance={})


@pytest.mark.parametrize("goal", GOALS)
def test_goal_guidance_reaches_real_chat_without_new_targets(client, captured, monkeypatch, goal):
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *_args: TARGET_BLOCK)
    calls = _set_sequence_stream(monkeypatch, captured, [_payload()])
    events = _events(_post(client, "Give me a full-day nutrition plan", profile={**_profile(), "goal": goal}))
    assert events[-1] == {"done": True}
    contract = calls[0]["messages"][0]["content"].split("[STRUCTURED DAILY NUTRITION PLAN]", 1)[1]
    assert plans._GOAL_SELECTION_GUIDANCE[goal] in contract
    assert "Allergies, restrictions, and explicit food preferences override" in contract
    assert "2800 kcal; protein 175g; carbs 350g; fat 78g" in contract
    assert "oats" not in contract.lower() and "chicken" not in contract.lower() and "rice" not in contract.lower()


def test_unspecified_targets_are_not_invented_in_generation_or_repair():
    targets = NutritionTargets(Decimal("2000"))
    for contract in (plans.generation_contract(targets, "en"),
                     plans.regeneration_contract(plans.NutritionPlanError("missing food_id"), targets, "en")):
        assert "protein unspecifiedg; carbs unspecifiedg; fat unspecifiedg" in contract
        assert "Do not invent an unspecified macro target" in contract
        assert "meal budgets" not in contract


@pytest.mark.parametrize("restriction", ["peanut allergy", "no chicken", "vegetarian"])
@pytest.mark.parametrize("goal", GOALS)
def test_restrictions_remain_stronger_than_fallback_goal(restriction, goal):
    assert plans.build_source_backed_plan(NutritionTargets(Decimal("2000")), "en",
                                          restrictions=(restriction,), profile={"goal": goal}) is None


def test_allergies_still_reject_generated_plan_even_with_goal_guidance():
    payload = _payload()
    payload["meals"][0]["foods"][0].update(food_id="peanuts", display_name="Peanuts")
    generated = plans.parse_generation_response(_StructuredCompletion(payload))
    with pytest.raises(plans.NutritionRestrictionError):
        plans.build_plan(generated, _NUTRITION_TARGETS, restrictions=("peanut allergy",), provenance={})


def _identity(plan):
    return tuple((meal.meal_type, tuple((food.food_id, food.grams) for food in meal.foods)) for meal in plan.meals)


@pytest.mark.parametrize("lang", ["bg", "en"])
@pytest.mark.parametrize("goal", GOALS)
def test_real_catalog_fallback_is_deterministic_and_source_backed(lang, goal):
    catalog = load_catalog_file(CATALOG_PATH, CatalogGovernance(True, False, Decimal("15")))
    targets = NutritionTargets(Decimal("2000"))
    kwargs = {"restrictions": (), "profile": {"goal": goal}}
    first = plans.build_source_backed_plan(targets, lang, **kwargs)
    second = plans.build_source_backed_plan(targets, lang, **kwargs)
    assert first is not None and second is not None
    assert _identity(first) == _identity(second)
    assert abs(first.totals.kcal - targets.kcal) <= targets.kcal * Decimal("0.05")
    for meal in first.meals:
        for food in meal.foods:
            source = catalog.by_id(food.food_id)
            assert source is not None and meal.meal_type in source.allowed_meals
            factor = food.grams / Decimal("100")
            assert food.macros.protein_g == source.protein_per_100g * factor
            assert food.macros.carbs_g == source.carbs_per_100g * factor
            assert food.macros.fat_g == source.fat_per_100g * factor
            assert food.macros.kcal == source.kcal_per_100g * factor
            assert food.measurement_state.value == plans._catalog_measurement_state(source)
    assert plans.from_record(plans.to_record(first)) is not None


def test_recent_structured_context_changes_feasible_menu_without_randomness():
    targets = NutritionTargets(Decimal("2000"))
    kwargs = {"restrictions": (), "profile": {"goal": "general"}}
    first = plans.build_source_backed_plan(targets, "en", **kwargs)
    context = plans.recent_nutrition_context([{"plan": plans.to_record(first)}])
    second = plans.build_source_backed_plan(targets, "en", recent_context=context, **kwargs)
    replay = plans.build_source_backed_plan(targets, "en", recent_context=context, **kwargs)
    assert second is not None
    assert _identity(first) != _identity(second)
    assert _identity(second) == _identity(replay)
    old_lunch = {food.food_id for food in first.meals[1].foods}
    assert any(food.food_id not in old_lunch for food in second.meals[1].foods)


def test_repetition_is_permitted_when_all_catalog_choices_are_in_recent_context():
    catalog = load_catalog_file(CATALOG_PATH, CatalogGovernance(True, False, Decimal("15")))
    context = plans.RecentNutritionContext(1, (("lunch", tuple(food.display_name_en for food in catalog.foods)),))
    kwargs = {"restrictions": (), "profile": {"goal": "general"}}
    target = NutritionTargets(Decimal("2000"))
    first = plans.build_source_backed_plan(target, "en", **kwargs)
    repeated = plans.build_source_backed_plan(target, "en", recent_context=context, **kwargs)
    assert repeated is not None and _identity(first) == _identity(repeated)


@pytest.mark.parametrize("authenticated", [False, True])
def test_recent_food_context_is_account_only_and_uses_existing_persistence(
        client, captured, monkeypatch, authenticated):
    profile = {**_profile(), "goal": "general"}
    uid = _login_for_chat(client, profile) if authenticated else None
    if uid:
        plan = plans.build_plan(_payload(), _NUTRITION_TARGETS, restrictions=(), provenance={})
        store.save_nutrition_plan(uid, plans.to_record(plan))
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *_args: TARGET_BLOCK)
    calls = _set_sequence_stream(monkeypatch, captured, [_payload()])
    events = _events(_post(client, "Give me a full-day nutrition plan", profile=profile))
    assert events[-1] == {"done": True}
    prompt = calls[0]["messages"][0]["content"]
    assert ("[RECENT STRUCTURED PLAN CONTEXT]" in prompt) == authenticated
    if uid:
        assert "Whole eggs, Oats" in prompt
        assert len(store.list_nutrition_plans(uid)) == 2
    assert appmod._nutrition_engine_v2_active() is False


@pytest.mark.parametrize("lang", ["bg", "en"])
@pytest.mark.parametrize("goal", GOALS)
@pytest.mark.parametrize("protein", [None, Decimal("175")])
def test_delivery_has_no_generic_footer_or_replacement_and_preserves_plan(lang, goal, protein):
    targets = NutritionTargets(Decimal("2800"), protein)
    plan = plans.build_plan(_payload(lang), targets, restrictions=(), provenance={"internal": "not-for-ui"})
    before = plans.to_record(plan)
    delivered = plans.render_delivery(plan, lang, profile={"goal": goal})
    assert "APEX rationale" not in delivered and "APEX логика" not in delivered
    assert all(line.startswith("|") and line.endswith("|") for line in delivered.splitlines())
    assert plans.to_record(plan) == before
    assert "Why this plan" not in delivered and "Защо този режим" not in delivered
    for word in ("tolerance", "provenance", "validation", "policy", "optimized", "perfect", "одобрения допуск", "not-for-ui"):
        assert word not in delivered


def test_unknown_catalog_preparation_fails_closed():
    source = type("Food", (), {"preparation_state": "unverified"})()
    assert plans._catalog_measurement_state(source) is None


@pytest.mark.parametrize("authenticated", [False, True])
def test_chat_fallback_receives_bounded_goal_and_account_only_recent_context(
        client, captured, monkeypatch, authenticated):
    targets = NutritionTargets(Decimal("2000"))
    profile = {**_profile(), "goal": "general"}
    uid = _login_for_chat(client, profile) if authenticated else None
    if uid:
        prior = plans.build_source_backed_plan(targets, "en", restrictions=(), profile=profile)
        store.save_nutrition_plan(uid, plans.to_record(prior))
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *_args: "Calorie target: 2000 kcal")
    _set_sequence_stream(monkeypatch, captured, [_payload(), _payload()])
    original, calls = plans.build_source_backed_plan, []

    def capture(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(plans, "build_source_backed_plan", capture)
    events = _events(_post(client, "Give me a full-day nutrition plan", profile=profile))
    assert events[-1] == {"done": True}
    assert len(calls) == 1 and calls[0]["profile"]["goal"] == "general"
    assert calls[0]["recent_context"].available == authenticated
    assert events[0]["t"].startswith("| Meal | Menu title | Meal ID | Food")
    if uid:
        records = store.list_nutrition_plans(uid)
        assert len(records) == 2
        recovered = plans.from_record(records[0]["plan"])
        assert dict(recovered.provenance)["generator"] == "source_backed_catalog_fallback"
        assert _identity(recovered) != _identity(prior)


def test_fallback_attempts_are_bounded_and_preserve_catalog_facts(monkeypatch):
    catalog = load_catalog_file(CATALOG_PATH, CatalogGovernance(True, False, Decimal("15")))
    calls = []

    def reject(*_args, **kwargs):
        candidate = kwargs["catalog"]
        assert all(food == catalog.by_id(food.food_id) for food in candidate.foods)
        calls.append(candidate)
        return None

    monkeypatch.setattr(plans, "_build_source_backed_candidate", reject)
    assert plans.build_source_backed_plan(NutritionTargets(Decimal("2000")), "en",
                                          restrictions=(), profile={"goal": "general"}) is None
    assert 1 <= len(calls) <= 35
    assert calls[-1] == catalog


def test_fallback_optimizer_parameters_and_targets_are_not_changed(monkeypatch):
    from nutrition_engine import service
    original, requests = service.build_nutrition_plan, []

    def capture(request, **kwargs):
        requests.append(request)
        return original(request, **kwargs)

    monkeypatch.setattr(service, "build_nutrition_plan", capture)
    target = NutritionTargets(Decimal("2000"), Decimal("175"))
    assert plans.build_source_backed_plan(target, "en", restrictions=(), profile={"goal": "strength"})
    assert 1 <= len(requests) <= 35
    for request in requests:
        assert request.targets.calories_target == target.kcal
        assert request.targets.calories_tolerance == Decimal("0.05")
        assert request.targets.protein_min_g == target.protein
        assert request.targets.protein_max_g is None
        assert request.targets.carbs_min_g is None and request.targets.carbs_max_g is None
        assert request.targets.fat_min_g is None and request.targets.fat_max_g is None
        assert request.practicality_policy.max_search_nodes == 200_000
        assert request.practicality_policy.maximum_foods_per_meal == 4
