"""Phase 10 real-user nutrition acceptance scenarios.

These tests exercise the production /chat boundary with a deterministic model
stream. They record the request-scoped NutritionConversation transitions without
adding a user-visible debug surface.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import pytest

import app as appmod
import db as store
import nutrition_conversation as nc


class _Chunk:
    def __init__(self, content):
        delta = type("Delta", (), {"content": content})()
        self.choices = [type("Choice", (), {"delta": delta})()]


class _StructuredCompletion:
    def __init__(self, payload):
        message = type("Message", (), {"content": json.dumps(payload)})()
        self.choices = [type("Choice", (), {"message": message})()]


TARGET_BLOCK = (
    "Calorie target: 2800 kcal\n"
    "Protein target: minimum 175g/day\n"
    "Carbohydrate target: 350g\n"
    "Fat target: 78g"
)

VALID_PLAN = {
    "meals": [
        {"meal_type": "breakfast", "name": "Breakfast", "time": "08:00", "foods": [
            {"display_name": "Whole eggs", "catalog_id": None, "grams": "200", "protein_g": "40", "carbs_g": "0", "fat_g": "20", "kcal": "340"},
            {"display_name": "Oats", "catalog_id": None, "grams": "100", "protein_g": "0", "carbs_g": "100", "fat_g": "0", "kcal": "360"},
        ]},
        {"meal_type": "lunch", "name": "Lunch", "time": "13:00", "foods": [
            {"display_name": "Chicken breast", "catalog_id": None, "grams": "200", "protein_g": "70", "carbs_g": "0", "fat_g": "15", "kcal": "500"},
            {"display_name": "Rice", "catalog_id": None, "grams": "200", "protein_g": "0", "carbs_g": "140", "fat_g": "15", "kcal": "600"},
        ]},
        {"meal_type": "dinner", "name": "Dinner", "time": "19:00", "foods": [
            {"display_name": "Salmon", "catalog_id": None, "grams": "200", "protein_g": "65", "carbs_g": "0", "fat_g": "28", "kcal": "600"},
            {"display_name": "Potatoes", "catalog_id": None, "grams": "300", "protein_g": "0", "carbs_g": "110", "fat_g": "0", "kcal": "400"},
        ]},
    ]
}

INVALID_PLAN = {
    **VALID_PLAN,
    "meals": [*VALID_PLAN["meals"][:-1], {
        **VALID_PLAN["meals"][-1],
        "foods": [*VALID_PLAN["meals"][-1]["foods"][:-1], {
            **VALID_PLAN["meals"][-1]["foods"][-1], "kcal": "100"}]
    }]
}


def _rendered_plan(payload=VALID_PLAN):
    targets = appmod.nutrition_validation.targets_from_profile_block(TARGET_BLOCK)
    plan = appmod.nutrition_plan.build_plan(payload, targets, restrictions=(), provenance={"test": "acceptance"})
    return appmod.nutrition_plan.render(plan, "en")

PLAN_HISTORY = (
    {"role": "user", "content": "I want a nutrition plan"},
    {"role": "assistant", "content": _rendered_plan()},
)


@dataclass(frozen=True)
class Scenario:
    name: str
    message: str
    profile: dict
    target_known: bool
    expected_initial: nc.NutritionConversationState
    expected_terminal: nc.NutritionConversationState
    model_reply: object | None = None
    history: tuple[dict, ...] = ()
    voice: bool = False
    session_start: bool = False


INCOMPLETE = {"goal": "strength"}
COMPLETE = {"goal": "strength", "age": "30", "gender": "male", "height": "180", "weight": "80"}


SCENARIOS = (
    Scenario("basic_bg_plan", "\u0418\u0441\u043a\u0430\u043c \u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d \u043f\u043b\u0430\u043d", INCOMPLETE, False, nc.NutritionConversationState.NEEDS_INFORMATION, nc.NutritionConversationState.NEEDS_INFORMATION),
    Scenario("basic_bg_menu", "\u041d\u0430\u043f\u0440\u0430\u0432\u0438 \u043c\u0438 \u043c\u0435\u043d\u044e", INCOMPLETE, False, nc.NutritionConversationState.NEEDS_INFORMATION, nc.NutritionConversationState.NEEDS_INFORMATION),
    Scenario("basic_bg_regime", "\u0418\u0441\u043a\u0430\u043c \u0440\u0435\u0436\u0438\u043c", INCOMPLETE, False, nc.NutritionConversationState.NEEDS_INFORMATION, nc.NutritionConversationState.NEEDS_INFORMATION),
    Scenario("muscle_gain_plan", "\u0418\u0441\u043a\u0430\u043c \u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d \u043f\u043b\u0430\u043d \u0437\u0430 \u043c\u0443\u0441\u043a\u0443\u043b\u0438", COMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("fat_loss_plan", "\u0418\u0441\u043a\u0430\u043c \u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d \u043f\u043b\u0430\u043d \u0437\u0430 \u043e\u0442\u0441\u043b\u0430\u0431\u0432\u0430\u043d\u0435", COMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("complete_profile", "I want a nutrition plan", COMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("incomplete_profile", "I want a nutrition plan", INCOMPLETE, False, nc.NutritionConversationState.NEEDS_INFORMATION, nc.NutritionConversationState.NEEDS_INFORMATION),
    Scenario("calorie_target", "Give me a full-day nutrition plan", INCOMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("macro_target", "Give me a full-day nutrition plan", COMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("clarification_repeat", "I want a nutrition plan", INCOMPLETE, False, nc.NutritionConversationState.UNSUPPORTED, nc.NutritionConversationState.UNSUPPORTED,
             history=({"role": "assistant", "content": nc.clarification_message(("age", "sex", "height", "weight"), "en")},)),
    Scenario("allergy_peanuts", "I want a nutrition plan", {**COMPLETE, "allergies": "peanuts"}, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("allergy_dairy", "I want a nutrition plan", {**COMPLETE, "allergies": "dairy"}, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("allergy_eggs", "I want a nutrition plan", {**COMPLETE, "allergies": "eggs"}, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("allergy_gluten", "I want a nutrition plan", {**COMPLETE, "allergies": "gluten"}, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("preference_vegetarian", "I want a nutrition plan", {**COMPLETE, "foodPreferences": "vegetarian"}, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("preference_vegan", "I want a nutrition plan", {**COMPLETE, "foodPreferences": "vegan"}, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("preference_no_chicken", "I want a nutrition plan", {**COMPLETE, "foodPreferences": "no chicken"}, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("preference_no_fish", "I want a nutrition plan", {**COMPLETE, "foodPreferences": "no fish"}, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("continuation_no_chicken", "\u0411\u0435\u0437 \u043f\u0438\u043b\u0435\u0448\u043a\u043e", COMPLETE, True, nc.NutritionConversationState.READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("continuation_more_rice", "\u0414\u043e\u0431\u0430\u0432\u0438 \u043f\u043e\u0432\u0435\u0447\u0435 \u043e\u0440\u0438\u0437", COMPLETE, True, nc.NutritionConversationState.READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("continuation_replace_breakfast", "\u0417\u0430\u043c\u0435\u043d\u0438 \u0437\u0430\u043a\u0443\u0441\u043a\u0430\u0442\u0430", COMPLETE, True, nc.NutritionConversationState.READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("repeat_identical", "I want a nutrition plan", COMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("repeat_failed", "I want a nutrition plan", COMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.FAILED, model_reply=INVALID_PLAN),
    Scenario("repeat_clarified", "I want a nutrition plan", INCOMPLETE, False, nc.NutritionConversationState.NEEDS_INFORMATION, nc.NutritionConversationState.NEEDS_INFORMATION),
    Scenario("unsupported_impossible_diet", "I want a vegan keto nutrition plan", COMPLETE, True, nc.NutritionConversationState.UNSUPPORTED, nc.NutritionConversationState.UNSUPPORTED),
    Scenario("unsupported_contradictory", "I want a nutrition plan using only peanuts", {**COMPLETE, "allergies": "peanuts"}, True, nc.NutritionConversationState.UNSUPPORTED, nc.NutritionConversationState.UNSUPPORTED),
    Scenario("medical_route", "I have chest pain. Make me a nutrition plan", COMPLETE, True, nc.NutritionConversationState.READY, nc.NutritionConversationState.READY),
    Scenario("shadow_off", "Give me a full-day nutrition plan", COMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("shadow_on", "Give me a full-day nutrition plan", COMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY),
    Scenario("voice_plan", "Give me a full-day nutrition plan", COMPLETE, True, nc.NutritionConversationState.PLAN_READY, nc.NutritionConversationState.PLAN_READY, voice=True),
    Scenario("session_start", "", COMPLETE, True, nc.NutritionConversationState.READY, nc.NutritionConversationState.READY, session_start=True, model_reply="Hello."),
)


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    monkeypatch.delenv("NUTRITION_ENGINE_V2_SHADOW", raising=False)
    monkeypatch.delenv("CONVERSATION_COMPOSER_ACTIVE", raising=False)


def _events(response):
    import json
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")]


def _seed_active_plan(client, profile):
    uid = store.get_or_create_user("nutrition-acceptance@example.com")
    store.save_profile(uid, profile)
    targets = appmod.nutrition_validation.targets_from_profile_block(TARGET_BLOCK)
    plan = appmod.nutrition_plan.build_plan(
        VALID_PLAN, targets, restrictions=(), provenance={"test": "acceptance"})
    store.save_nutrition_plan(uid, appmod.nutrition_plan.to_record(plan))
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(uid))
    return uid


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.name)
def test_real_user_nutrition_acceptance(scenario, monkeypatch):
    appmod.app.config["TESTING"] = True
    states = []
    calls = []
    begin = nc.begin
    generating = nc.generating
    accept = nc.accept_delivery
    fail = nc.fail_generation
    revised = nc.revised

    def capture_begin(**kwargs):
        result = begin(**kwargs)
        states.append(result.state)
        return result

    def capture_accept(*args, **kwargs):
        result = accept(*args, **kwargs)
        states.append(result.state)
        return result

    def capture_generating(*args, **kwargs):
        result = generating(*args, **kwargs)
        states.append(result.state)
        return result

    def capture_failure(*args, **kwargs):
        result = fail(*args, **kwargs)
        states.append(result.state)
        return result

    def capture_revised(*args, **kwargs):
        result = revised(*args, **kwargs)
        states.append(result.state)
        return result

    def fake_create(**kwargs):
        calls.append(kwargs)
        reply = VALID_PLAN if scenario.model_reply is None else scenario.model_reply
        if kwargs.get("response_format"):
            return _StructuredCompletion(reply)
        return iter((_Chunk(reply if isinstance(reply, str) else "ok"),))

    monkeypatch.setattr(appmod.nutrition_conversation, "begin", capture_begin)
    monkeypatch.setattr(appmod.nutrition_conversation, "generating", capture_generating)
    monkeypatch.setattr(appmod.nutrition_conversation, "accept_delivery", capture_accept)
    monkeypatch.setattr(appmod.nutrition_conversation, "fail_generation", capture_failure)
    monkeypatch.setattr(appmod.nutrition_conversation, "revised", capture_revised)
    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)
    monkeypatch.setattr(appmod, "_build_profile_block",
                        lambda _profile, _lang: TARGET_BLOCK if scenario.target_known else "")
    if scenario.name == "shadow_on":
        import nutrition_engine.shadow_hook as shadow_hook
        monkeypatch.setenv("NUTRITION_ENGINE_V2_SHADOW", "true")
        monkeypatch.setattr(shadow_hook, "dispatch", lambda *args, **kwargs: True)

    payload = {"message": scenario.message, "lang": "en", "profile": scenario.profile,
               "history": list(scenario.history)}
    if scenario.voice:
        payload["voice"] = True
    if scenario.session_start:
        payload["session_start"] = True
    client = appmod.app.test_client()
    if scenario.name.startswith("continuation_"):
        _seed_active_plan(client, scenario.profile)
    response = client.post("/chat", json=payload)
    events = _events(response)

    actual_initial = states[0]
    actual_terminal = states[-1]
    assert response.status_code == 200
    assert (actual_initial, actual_terminal) == (scenario.expected_initial, scenario.expected_terminal)
    assert events[-1] == {"done": True}
    assert len(calls) <= 1
    assert all("\u041e\u043f\u0438\u0442\u0430\u0439 \u043f\u0430\u043a" not in str(event) and "Please try again" not in str(event) for event in events)
    if actual_initial is nc.NutritionConversationState.NEEDS_INFORMATION:
        assert len(calls) == 0 and len(events) == 2
    if actual_terminal is nc.NutritionConversationState.FAILED:
        assert events[0]["t"] == nc.failed_message("en")


def test_shadow_on_and_off_have_identical_canonical_acceptance_output(monkeypatch):
    """Critical daily-plan scenario: V2 shadow must not alter canonical SSE."""
    appmod.app.config["TESTING"] = True
    def fake_create(**_kwargs):
        return _StructuredCompletion(VALID_PLAN)
    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *_args: TARGET_BLOCK)
    payload = {"message": "Give me a full-day nutrition plan", "lang": "en", "profile": COMPLETE}
    off = _events(appmod.app.test_client().post("/chat", json=payload))

    import nutrition_engine.shadow_hook as shadow_hook
    monkeypatch.setenv("NUTRITION_ENGINE_V2_SHADOW", "true")
    monkeypatch.setattr(shadow_hook, "dispatch", lambda *args, **kwargs: True)
    on = _events(appmod.app.test_client().post("/chat", json=payload))

    assert on == off == [{"t": _rendered_plan()}, {"done": True}]
