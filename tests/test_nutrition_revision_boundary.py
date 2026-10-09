"""Whole-plan edits use real /chat, canonical validation and account persistence."""
from copy import deepcopy
from decimal import Decimal
import json

import pytest

import app as appmod
import db as store
import nutrition_conversation as conversation
import nutrition_plan as plans
from nutrition_validation import NutritionTargets


TARGETS = NutritionTargets(Decimal("2607"), Decimal("165"), Decimal("320"), Decimal("73"))
MESSAGES = {
    "bg": (
        "Не искам млечни продукти. Промени плана, но запази хранителните ми цели.",
        "Направи го по-лесен за приготвяне, без да връщаш млечни продукти.",
    ),
    "en": (
        "I don't want dairy products. Change the plan, but keep my nutrition targets.",
        "Make it easier to prepare without reintroducing dairy.",
    ),
}
NAMES = {"eggs": ("Whole eggs", "Яйца"), "oats": ("Oats", "Овесени ядки"),
         "chicken": ("Chicken breast", "Пилешко"), "rice": ("Rice", "Ориз"),
         "salmon": ("Salmon", "Сьомга"), "potatoes": ("Potatoes", "Картофи")}


def payload(lang, *, simpler=False, invalid=False):
    identities = (("eggs", "oats"), ("chicken", "rice"), ("salmon", "potatoes"))
    if simpler:
        identities = (("eggs", "oats"), ("chicken", "rice"), ("chicken", "rice"))
    meals = []
    for kind, time, foods in zip(("breakfast", "lunch", "dinner"), ("08:00", "13:00", "19:00"), identities):
        meals.append({"meal_type": kind, "time": time, "foods": [
            {"food_id": identity, "display_name": NAMES[identity][lang == "bg"],
             "measurement_state": "raw", "grams": "200", "protein_g": "27.5",
             "carbs_g": str(Decimal(320) / 6), "fat_g": str(Decimal(73) / 6),
             "kcal": "10" if invalid else "434.5"} for identity in foods]})
    return {"meals": meals}


@pytest.fixture
def runtime(monkeypatch):
    appmod.app.config["TESTING"] = True
    for flag in ("BRAIN_ENFORCE", "CONVERSATION_COMPOSER_ACTIVE", "NUTRITION_ENGINE_V2_ACTIVE"):
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "false")
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_args: None)
    # Deliberately conflicting live targets: revisions must use persisted targets.
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *_args: "Calorie target: 1800 kcal")
    uid = store.get_or_create_user("synthetic-revision@example.com")
    store.save_profile(uid, {"age": "30", "gender": "male", "height": "180", "weight": "80",
                             "goal": "strength", "foodPreferences": "no peanuts"})
    client = appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(uid))
    return client, uid


def seed(uid, lang):
    plan = plans.build_plan(payload(lang), TARGETS, restrictions=("no peanuts",),
                            provenance={"test": "synthetic"}, language=lang)
    store.save_nutrition_plan(uid, plans.to_record(plan))
    return plan


def model(monkeypatch, replies):
    calls = []
    queue = iter(replies)
    def create(**kwargs):
        calls.append(deepcopy(kwargs))
        reply = next(queue)
        if isinstance(reply, Exception):
            raise reply
        content = json.dumps(reply) if isinstance(reply, dict) else reply
        message = type("Message", (), {"content": content})()
        return type("Completion", (), {"choices": [type("Choice", (), {"message": message})()]})()
    monkeypatch.setattr(appmod.client.chat.completions, "create", create)
    return calls


def post(client, message, lang):
    response = client.post("/chat", json={"message": message, "lang": lang})
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
              if line.startswith("data: ")]
    assert events[-1] == {"done": True}
    return "".join(event.get("t", "") for event in events)


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_chained_revisions_preserve_targets_restrictions_and_refresh(runtime, monkeypatch, lang):
    client, uid = runtime
    active = seed(uid, lang)
    calls = model(monkeypatch, [payload(lang), payload(lang, simpler=True)])
    for index, request in enumerate(MESSAGES[lang]):
        delivered = post(client, request, lang)
        latest = plans.from_record(store.list_nutrition_plans(uid, limit=1)[0]["plan"])
        assert latest.targets == active.targets
        assert set(latest.restrictions) == {"no dairy" if lang == "en" else "no млечни", "no peanuts"}
        assert dict(latest.provenance)["parent_plan_id"] == active.id
        assert delivered == appmod._render_nutrition_delivery(latest, lang, store.get_profile(uid))
        assert "ELITE STATUS" not in delivered
        assert "Stop if you feel pain" not in delivered
        assert "Болка" not in delivered
        refreshed = client.get("/api/nutrition").json["latest_plan"]
        assert refreshed["totals"]["kcal"] == "2607.0"
        assert refreshed["restrictions"] == list(latest.restrictions)
        if index:
            assert len(plans._preparation_ingredients(latest)) < len(plans._preparation_ingredients(active))
        active = latest
    assert len(calls) == 2
    for call in calls:
        assert call["response_format"] == {"type": "json_object"}
        assert "stream" not in call
        assert "2607 kcal" in call["messages"][0]["content"]
        assert "[AUTHORITATIVE NUTRITION PLAN REVISION]" in call["messages"][0]["content"]
    assert len(store.list_nutrition_plans(uid)) == 3


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_invalid_revision_has_one_repair_and_no_rejected_text(runtime, monkeypatch, lang):
    client, uid = runtime
    seed(uid, lang)
    calls = model(monkeypatch, [payload(lang, invalid=True), payload(lang)])
    text = post(client, MESSAGES[lang][0], lang)
    assert "2607" in text and len(calls) == 2
    assert "kcal is outside" in calls[1]["messages"][-1]["content"]
    assert plans.from_record(store.list_nutrition_plans(uid)[0]["plan"]).totals.kcal == Decimal("2607")


@pytest.mark.parametrize("bad", ["ELITE STATUS: ACTIVE\nBreakfast: milk 2453 kcal", {}, RuntimeError("synthetic failure")])
def test_invalid_revision_never_falls_through_to_free_form(runtime, monkeypatch, bad):
    client, uid = runtime
    active = seed(uid, "en")
    calls = model(monkeypatch, [bad, bad])
    text = post(client, MESSAGES["en"][0], "en")
    assert text == conversation.failed_message("en")
    assert len(calls) <= 2
    assert store.list_nutrition_plans(uid)[0]["plan"]["id"] == active.id


def test_copy_only_simplification_is_rejected_and_repair_is_structured(runtime, monkeypatch):
    client, uid = runtime
    seed(uid, "en")
    unchanged = payload("en")
    unchanged["meals"][0]["name"] = "Very easy breakfast"
    calls = model(monkeypatch, [unchanged, payload("en", simpler=True)])
    assert "2607" in post(client, MESSAGES["en"][1], "en")
    assert len(calls) == 2
    assert "fewer distinct ingredients" in calls[1]["messages"][-1]["content"]


@pytest.mark.parametrize("message", ["Change the plan to an unsupported diet", "Промени плана с непозната храна"])
def test_unknown_edit_clarifies_without_model_or_plan_write(runtime, monkeypatch, message):
    client, uid = runtime
    active = seed(uid, "en")
    calls = model(monkeypatch, [])
    assert post(client, message, "en") == conversation.revision_unsupported_message("en")
    assert not calls
    assert store.list_nutrition_plans(uid)[0]["plan"]["id"] == active.id


def test_failed_revision_storage_does_not_deliver_unsaved_plan(runtime, monkeypatch):
    client, uid = runtime
    active = seed(uid, "en")
    model(monkeypatch, [payload("en")])
    monkeypatch.setattr(store, "save_nutrition_plan", lambda *_args: (_ for _ in ()).throw(RuntimeError("private")))
    assert post(client, MESSAGES["en"][0], "en") == conversation.failed_message("en")
    assert store.list_nutrition_plans(uid)[0]["plan"]["id"] == active.id


@pytest.mark.parametrize("message,restriction", [("Remove oats from the plan", "no oats"),
                                                  ("Премахни овесените ядки от плана", "no овесени ядки")])
def test_food_exclusion_is_closed_and_canonical(message, restriction):
    revision = conversation.parse_plan_revision(message)
    assert revision.supported and revision.restrictions == (restriction,)


@pytest.mark.parametrize("message", ["Change my workout plan", "Промени тренировъчния план",
                                      "How do I prepare dinner?", "Tell me about dairy",
                                      "Give me a nutrition plan without dairy",
                                      "What foods can I eat without dairy?"])
def test_non_revision_requests_keep_their_existing_routes(message):
    assert conversation.parse_plan_revision(message) is None


@pytest.mark.parametrize("brain_on", [False, True])
def test_revision_authority_survives_brain_enforcement_flag(runtime, monkeypatch, brain_on):
    client, uid = runtime
    seed(uid, "en")
    monkeypatch.setenv("BRAIN_ENFORCE", "true" if brain_on else "false")
    model(monkeypatch, [payload("en")])
    assert "2607" in post(client, MESSAGES["en"][0], "en")


def test_dairy_in_generated_revision_is_rejected_without_persistence(runtime, monkeypatch):
    client, uid = runtime
    active = seed(uid, "en")
    candidate = payload("en")
    candidate["meals"][0]["foods"][0].update(food_id="milk", display_name="Milk")
    model(monkeypatch, [candidate])
    assert post(client, MESSAGES["en"][0], "en") == plans.restriction_blocked_message("en")
    assert store.list_nutrition_plans(uid)[0]["plan"]["id"] == active.id


def test_practicality_fallback_cannot_bypass_revision_validation(runtime, monkeypatch):
    client, uid = runtime
    active = seed(uid, "en")
    model(monkeypatch, [{}, {}])
    monkeypatch.setattr(plans, "build_source_backed_plan", lambda *_args, **_kwargs: active)
    assert post(client, MESSAGES["en"][1], "en") == conversation.failed_message("en")
    assert store.list_nutrition_plans(uid)[0]["plan"]["id"] == active.id


def test_compound_exclusions_do_not_apply_only_the_first_typed_edit():
    revision = conversation.parse_plan_revision("No chicken and no dairy. Change the plan.")
    assert revision.supported and revision.operation is None
    assert set(revision.restrictions) == {"no chicken", "no dairy"}
