"""08A.1 production-sized fallback regression; no external model or DB."""
from decimal import Decimal
from pathlib import Path

import pytest

import app as appmod
import db as store
import nutrition_plan as plans
from nutrition_validation import NutritionTargets
from nutrition_engine.catalog import Catalog, CatalogGovernance, load_catalog_file
from tests.test_chat_enforcement import (
    client, captured, _enforce_off_by_default, _isolated_learning_worker,
    _events, _login_for_chat, _post, _profile, _set_sequence_stream,
    _structured_plan_payload,
)


LEGACY_IDENTITY = (
    ("dev_egg_whites", "dev_oats_dry", "dev_apple"),
    ("dev_chicken_breast_cooked", "dev_rice_cooked", "dev_zucchini_cooked", "dev_olive_oil"),
    ("dev_turkey_breast_cooked", "dev_pasta_cooked", "dev_zucchini_cooked", "dev_olive_oil"),
)
GOALS = ("fat_loss", "muscle_gain", "strength", "endurance", "general")


def _catalog():
    return load_catalog_file(Path(__file__).parents[1] / "nutrition_engine/data/food_catalog_v1.json",
                             CatalogGovernance(True, False, Decimal("15")))


def _identity(plan):
    return tuple(tuple(food.food_id for food in meal.foods) for meal in plan.meals)


def test_observed_2489_fat_loss_rejected_generation_path_does_not_collapse(
        client, captured, monkeypatch):
    profile = _profile(goal="fat_loss")
    uid = _login_for_chat(client, profile)
    # The observed calorie target is known; no production protein value was
    # provided. A separate test below uses the real complete-profile contract.
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *_args: "Calorie target: 2489 kcal")
    rejected = _structured_plan_payload(total_kcal="2800")
    model_calls = _set_sequence_stream(monkeypatch, captured, [rejected, rejected])
    original, attempts = plans._build_source_backed_candidate, []

    def observe(*args, **kwargs):
        plan = original(*args, **kwargs)
        attempts.append((len(kwargs["catalog"].foods), _identity(plan) if plan else None))
        return plan

    monkeypatch.setattr(plans, "_build_source_backed_candidate", observe)
    events = _events(_post(client, "Give me a full-day nutrition plan"))
    assert events[-1] == {"done": True} and len(model_calls) == 2
    assert "kcal is outside the confirmed target" in model_calls[1]["messages"][-1]["content"]
    records = store.list_nutrition_plans(uid)
    assert len(records) == 1
    plan = plans.from_record(records[0]["plan"])
    assert abs(plan.totals.kcal - Decimal("2489")) <= Decimal("2489") * Decimal("0.05")
    assert _identity(plan) != LEGACY_IDENTITY
    assert attempts[-1][0] < len(_catalog().foods)


def test_complete_profile_2489_fat_loss_keeps_real_protein_target():
    profile = _profile(goal="fat_loss", gender="male", age="33", height="185", weight="90", activityLevel="active")
    targets = appmod.nutrition_validation.targets_from_profile_block(appmod._build_profile_block(profile, "en"))
    assert targets == NutritionTargets(Decimal("2489"), Decimal("180"))
    plan = plans.build_source_backed_plan(targets, "en", restrictions=(), profile=profile)
    assert plan is not None
    assert plan.targets == targets
    assert _identity(plan) != LEGACY_IDENTITY


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_real_complete_profile_rejected_model_and_repair_use_feasible_fallback(
        client, captured, monkeypatch, lang):
    profile = _profile(goal="fat_loss", gender="male", age="33", height="185", weight="90",
                       activityLevel="active", language=lang)
    uid = _login_for_chat(client, profile)
    rejected = _structured_plan_payload()
    if lang == "bg":
        from tests.test_nutrition_reliability import _payload
        rejected = _payload("bg")
    calls = _set_sequence_stream(monkeypatch, captured, [rejected] * 2)
    events = _events(_post(client, "Give me a full-day nutrition plan", lang=lang))
    assert events[-1] == {"done": True} and len(calls) == 2
    records = store.list_nutrition_plans(uid)
    assert len(records) == 1
    plan = plans.from_record(records[0]["plan"])
    expected = appmod.nutrition_validation.targets_from_profile_block(appmod._build_profile_block(profile, lang))
    # Preserve the actual language-specific target parser; this hotfix must
    # neither invent an absent target nor change existing target arithmetic.
    assert expected.kcal == Decimal("2489")
    assert plan.targets == expected
    if lang == "en":
        assert expected.protein == Decimal("180")
    assert _identity(plan) != LEGACY_IDENTITY
    assert "APEX rationale" not in events[0]["t"] and "APEX логика" not in events[0]["t"]


@pytest.mark.parametrize("goal", GOALS)
@pytest.mark.parametrize("kcal,protein", [("2000", "160"), ("2250", "112")])
@pytest.mark.parametrize("lang", ["bg", "en"])
def test_realistic_confirmed_targets_remain_valid_source_backed_and_reproducible(goal, kcal, protein, lang):
    targets = NutritionTargets(Decimal(kcal), Decimal(protein))
    kwargs = {"restrictions": (), "profile": {"goal": goal}}
    plan = plans.build_source_backed_plan(targets, lang, **kwargs)
    replay = plans.build_source_backed_plan(targets, lang, **kwargs)
    assert plan is not None and replay is not None
    assert plan.targets == targets
    assert plans.to_record(plan)["totals"] == plans.to_record(replay)["totals"]
    assert _identity(plan) == _identity(replay)
    assert tuple(f.grams for m in plan.meals for f in m.foods) == tuple(
        f.grams for m in replay.meals for f in m.foods)
    assert abs(plan.totals.kcal - targets.kcal) <= targets.kcal * Decimal("0.05")
    assert abs(plan.totals.protein_g - targets.protein) <= targets.protein * Decimal("0.05")
    catalog = _catalog()
    for meal in plan.meals:
        for food in meal.foods:
            source = catalog.by_id(food.food_id)
            assert source is not None and meal.meal_type in source.allowed_meals
            factor = food.grams / Decimal("100")
            assert food.macros.protein_g == source.protein_per_100g * factor
            assert food.macros.carbs_g == source.carbs_per_100g * factor
            assert food.macros.fat_g == source.fat_per_100g * factor
            assert food.macros.kcal == source.kcal_per_100g * factor
    assert plans.from_record(plans.to_record(plan)) is not None


def test_goal_identities_differ_in_real_food_choices_where_feasible():
    target = NutritionTargets(Decimal("2000"), Decimal("160"))
    menus = {goal: plans.build_source_backed_plan(target, "en", restrictions=(), profile={"goal": goal})
             for goal in GOALS}
    assert all(menus.values())
    assert len({_identity(plan) for plan in menus.values()}) >= 4
    assert _identity(menus["fat_loss"]) != _identity(menus["muscle_gain"])
    assert _identity(menus["fat_loss"]) != _identity(menus["endurance"])
    catalog = _catalog()
    fat_loss_protein = catalog.by_id(menus["fat_loss"].meals[0].foods[0].food_id)
    gain_protein = catalog.by_id(menus["muscle_gain"].meals[0].foods[0].food_id)
    assert fat_loss_protein.protein_per_100g / fat_loss_protein.kcal_per_100g > (
        gain_protein.protein_per_100g / gain_protein.kcal_per_100g)
    assert gain_protein.kcal_per_100g > fat_loss_protein.kcal_per_100g
    endurance_fruit = catalog.by_id(menus["endurance"].meals[0].foods[-1].food_id)
    strength_fruit = catalog.by_id(menus["strength"].meals[0].foods[-1].food_id)
    assert endurance_fruit.carbs_per_100g > strength_fruit.carbs_per_100g
    for meal in menus["strength"].meals[1:]:
        categories = {catalog.by_id(food.food_id).category for food in meal.foods}
        assert {"protein", "carbohydrate"} <= categories
    neutral = plans.build_source_backed_plan(target, "en", restrictions=(), profile={})
    assert _identity(menus["general"]) == _identity(neutral)


def test_recent_validated_identity_influences_feasible_real_macro_fallback():
    targets = NutritionTargets(Decimal("2000"), Decimal("160"))
    kwargs = {"restrictions": (), "profile": {"goal": "general"}}
    first = plans.build_source_backed_plan(targets, "en", **kwargs)
    context = plans.recent_nutrition_context([{"plan": plans.to_record(first)}])
    second = plans.build_source_backed_plan(targets, "en", recent_context=context, **kwargs)
    replay = plans.build_source_backed_plan(targets, "en", recent_context=context, **kwargs)
    assert second is not None and replay is not None
    assert _identity(second) != _identity(first)
    assert _identity(second) == _identity(replay)
    assert second.targets == targets


def test_feasibility_can_repeat_recent_identity_instead_of_inventing_foods():
    target = NutritionTargets(Decimal("2489"), Decimal("180"))
    catalog = _catalog()
    all_recent = plans.RecentNutritionContext(1, (("lunch", tuple(f.display_name_en for f in catalog.foods)),))
    kwargs = {"restrictions": (), "profile": {"goal": "fat_loss"}}
    first = plans.build_source_backed_plan(target, "en", **kwargs)
    repeated = plans.build_source_backed_plan(target, "en", recent_context=all_recent, **kwargs)
    assert first is not None and repeated is not None
    assert _identity(first) == _identity(repeated)


def test_legacy_identity_remains_possible_when_only_its_sources_are_available(monkeypatch):
    import nutrition_engine.catalog as catalogs

    catalog = _catalog()
    available_ids = {food_id for meal in LEGACY_IDENTITY for food_id in meal}
    limited = Catalog(catalog.version, tuple(f for f in catalog.foods if f.food_id in available_ids))
    monkeypatch.setattr(catalogs, "load_catalog_file", lambda *_args: limited)
    target = NutritionTargets(Decimal("2489"), Decimal("245"))
    plan = plans.build_source_backed_plan(target, "en", restrictions=(), profile={"goal": "general"})
    assert plan is not None and _identity(plan) == LEGACY_IDENTITY
    assert plan.targets == target
    assert plans.from_record(plans.to_record(plan)) is not None
