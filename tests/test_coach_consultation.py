"""Consecutive real /chat turns; only external semantic decisions are annotated.

Annotations are test evidence, not a production phrase dictionary or a claim of
live model accuracy. Every continuation reads the actual persisted HTTP history.
"""
import json

import pytest

import app as appmod
import db as store
import nutrition_intent as ni
from test_nutrition_intent import completion, runtime  # noqa: F401


CASES = {
    "bg": {
        "opening": "Обмислям да сваля 20+ кг за 1 месец. Не създавай план. Нека обсъдим по-безопасен срок.",
        "when": "какъв срок?", "both": "37г 120кг", "age": "На 37 години съм.",
        "weight": "Тежа 120 кг.", "medical": "Нямам заболявания и не приемам лекарства.",
        "again": "Този срок гарантиран ли е?", "missing": "Остава да уточним:",
    },
    "en": {
        "opening": "I am considering losing 20+ kg in 1 month. Do not create a plan. Let us discuss a safer timeline.",
        "when": "What timeframe?", "both": "37 years old, 120 kg", "age": "I am 37 years old.",
        "weight": "I weigh 120 kg.", "medical": "I have no medical conditions and take no medication.",
        "again": "Is that timeframe guaranteed?", "missing": "Still missing:",
    },
}


def annotate(runtime, monkeypatch, case, extra=None):
    labels = {
        case["opening"]: {"target_kg": 20}, case["both"]: {"age": 37, "weight_kg": 120},
        case["age"]: {"age": 37}, case["weight"]: {"weight_kg": 120},
        case["medical"]: {"medical": case["medical"]}, **(extra or {}),
    }
    received = []
    learning = []
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *args: learning.append(args))

    def provider(_client, messages):
        data = json.loads(messages[-1]["content"])
        assert "candidate" not in data, "fixed consultation must not call a prose generator/audit"
        received.append(data)
        turns = [*data["conversation"], {"role": "user", "content": data["message"]}]
        context = {}
        for index, turn in enumerate(turns):
            if turn["role"] == "user":
                for key, value in labels.get(turn["content"], {}).items():
                    context[key] = [index, value] if key == "medical" else [value, index]
        return completion({"scope": "timeline_consultation", "requested_goal": None,
                           "consultation": context})
    monkeypatch.setattr(ni, "_request", provider)
    return received, learning


def text(events):
    assert events[-1] == {"done": True}
    assert not any(event.get("training_completion") for event in events)
    return "".join(event.get("t", "") for event in events)


def unchanged(runtime, profile, restrictions):
    assert store.get_profile(runtime.uid) == profile
    assert store.list_account_training_constraints(runtime.uid) == restrictions
    assert not store.list_nutrition_plans(runtime.uid)
    assert not store.list_nutrition(runtime.uid) and not store.list_workouts(runtime.uid)
    assert runtime.calls == []


@pytest.mark.parametrize("lang", ["bg", "en"])
@pytest.mark.parametrize("enforce", [False, True])
def test_production_sequence_uses_persisted_answers_without_repeating(runtime, monkeypatch, lang, enforce):
    monkeypatch.setenv("BRAIN_ENFORCE", str(enforce).lower())
    profile = {"goal": "strength"}
    store.save_profile(runtime.uid, profile)
    store.add_account_training_constraints(runtime.uid, ("vertical_push",))
    restrictions = store.list_account_training_constraints(runtime.uid)
    case = CASES[lang]
    received, learning = annotate(runtime, monkeypatch, case)
    first = text(runtime.post(case["opening"], lang, first_contact=True))
    second = text(runtime.post(case["when"], lang))
    third = text(runtime.post(case["both"], lang, first_contact=True))
    assert "20-40" in second and ("седмици" if lang == "bg" else "weeks") in second
    assert "37" in third and "120" in third
    remaining = third.split(case["missing"])[-1]
    assert ("възраст" if lang == "bg" else "age") not in remaining
    assert ("текущо тегло" if lang == "bg" else "current weight") not in remaining
    assert ("лекарства" if lang == "bg" else "medications") in remaining
    assert ("не е медицинска" if lang == "bg" else "not a medical") in third
    assert "kcal" not in first + second + third and "|" not in third
    assert received[0]["conversation"] == []
    assert any(turn["content"] == case["opening"] for turn in received[1]["conversation"])
    assert any(turn["content"] == case["when"] for turn in received[2]["conversation"])
    assert len(store.list_conversation(runtime.uid)) == 6
    assert learning == []
    unchanged(runtime, profile, restrictions)


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_partial_answers_accumulate_and_medical_answer_is_not_clinical_clearance(runtime, monkeypatch, lang):
    profile = {"goal": "strength"}
    store.save_profile(runtime.uid, profile)
    case = CASES[lang]
    received, learning = annotate(runtime, monkeypatch, case)
    text(runtime.post(case["opening"], lang))
    after_age = text(runtime.post(case["age"], lang)).split(case["missing"])[-1]
    assert ("възраст" if lang == "bg" else "age") not in after_age
    assert ("текущо тегло" if lang == "bg" else "current weight") in after_age
    after_weight = text(runtime.post(case["weight"], lang)).split(case["missing"])[-1]
    assert ("възраст" if lang == "bg" else "age") not in after_weight
    assert ("текущо тегло" if lang == "bg" else "current weight") not in after_weight
    for message in (case["medical"], case["again"]):
        reply = text(runtime.post(message, lang))
        assert case["missing"] not in reply and "?" not in reply
        assert ("не лекарско разрешение" if lang == "bg" else "not clinical clearance") in reply
        assert ("не персонален срок" if lang == "bg" else "not a personalized deadline") in reply
    assert len(store.list_conversation(runtime.uid)) == 10
    assert len(received[-1]["conversation"]) == 8 and learning == []
    unchanged(runtime, profile, ())


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_consultation_answers_override_stale_profile_only_inside_the_conversation(runtime, monkeypatch, lang):
    profile = {"goal": "strength", "age": "28", "weight": "80"}
    store.save_profile(runtime.uid, profile)
    case = CASES[lang]
    annotate(runtime, monkeypatch, case)
    runtime.post(case["opening"], lang)
    reply = text(runtime.post(case["both"], lang))
    assert "37" in reply and "120" in reply
    assert "28" not in reply and "80" not in reply
    unchanged(runtime, profile, ())


@pytest.mark.parametrize("lang,answer", [
    ("bg", "Имам диабет и приемам лекарства."),
    ("en", "I have diabetes and take medication."),
    ("bg", "Не съм сигурен какво е важно от медицинска гледна точка."),
    ("en", "I am not sure what medical context matters."),
])
def test_medical_context_or_uncertainty_is_acknowledged_without_a_prescription(runtime, monkeypatch, lang, answer):
    profile = {"goal": "strength"}
    store.save_profile(runtime.uid, profile)
    case = CASES[lang]
    annotate(runtime, monkeypatch, case, {answer: {"medical": answer}})
    runtime.post(case["opening"], lang)
    runtime.post(case["both"], lang)
    reply = text(runtime.post(answer, lang))
    assert case["missing"] not in reply
    assert ("лекар" if lang == "bg" else "clinician") in reply
    assert ("не лекарско разрешение" if lang == "bg" else "not clinical clearance") in reply
    unchanged(runtime, profile, ())


@pytest.mark.parametrize("lang,message", [("bg", "Имам болка в гърдите."), ("en", "I have chest pain.")])
def test_medical_hold_has_priority_over_a_continuing_timeline(runtime, monkeypatch, lang, message):
    case = CASES[lang]
    annotate(runtime, monkeypatch, case, {message: {"medical": message}})
    runtime.post(case["opening"], lang)
    output = runtime.post(message, lang)
    assert any(event.get("medical_hold") for event in output)
    reply = text(output)
    assert "NHS" not in reply and "20-40" not in reply
    assert runtime.calls == [] and not store.list_nutrition_plans(runtime.uid)


def test_account_history_is_authoritative_and_never_crosses_accounts(runtime, monkeypatch):
    case = CASES["en"]
    store.save_profile(runtime.uid, {"goal": "strength"})
    received, _ = annotate(runtime, monkeypatch, case)
    runtime.post(case["opening"])
    runtime.post(case["both"])
    first_history = store.list_conversation(runtime.uid)
    other = store.get_or_create_user("consultation-other@example.test")
    store.save_profile(other, {"goal": "strength"})
    runtime.client.set_cookie(appmod.SESSION_COOKIE, store.create_session(other))
    reply = text(runtime.post(case["when"], history=first_history))
    assert received[-1]["conversation"] == []
    assert "37 years" not in reply and "120 kg" not in reply and "20-40" not in reply
    assert "age" in reply.split(case["missing"])[-1]
    assert store.list_conversation(runtime.uid) == first_history
    assert not store.list_nutrition_plans(other)


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_anonymous_continuation_uses_only_its_supplied_session_history(runtime, monkeypatch, lang):
    runtime.client.delete_cookie(appmod.SESSION_COOKIE)
    case = CASES[lang]
    annotate(runtime, monkeypatch, case)
    history = []
    for message in (case["opening"], case["when"], case["both"]):
        reply = text(runtime.post(message, lang, history=history, profile={}, conversation_id="anonymous-one"))
        history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": reply}])
    assert "37" in reply and "120" in reply
    other = appmod.app.test_client()
    response = other.post("/chat", json={"message": case["when"], "lang": lang,
                                         "conversation_id": "anonymous-two", "profile": {}})
    assert "37 years" not in response.get_data(as_text=True)
    assert not store.list_conversation(runtime.uid)


@pytest.mark.parametrize("context,history,message", [
    ({"age": [37, 0]}, [], "137"),
    ({"age": [37, 0]}, [{"role": "assistant", "content": "37"}], "Hello"),
    ({"weight_kg": [120, 9]}, [], "120 kg"),
    ({"age": [37, True]}, [], "37"),
    ({"age": [37.5, 0]}, [], "37.5"),
    ({"weight_kg": [float("nan"), 0]}, [], "120 kg"),
    ({"medical": [0, "no medication"]}, [], "Not yet answered"),
    ({"medical": [0, "no medication"]}, [{"role": "assistant", "content": "no medication"}], "Hello"),
    ({"approved_goal": "fat_loss"}, [], "Hello"),
])
def test_unsupported_consultation_facts_fail_closed(monkeypatch, context, history, message):
    monkeypatch.setattr(ni, "_request", lambda *_: completion({"scope": "timeline_consultation",
        "requested_goal": None, "consultation": context}))
    assert ni.resolve(None, message, history).scope is ni.Scope.AMBIGUOUS


def test_decimal_comma_and_latest_direct_correction_are_preserved(monkeypatch):
    monkeypatch.setattr(ni, "_request", lambda *_: completion({"scope": "timeline_consultation",
        "requested_goal": None, "consultation": {"age": [37, 0], "weight_kg": [119.5, 2]}}))
    result = ni.resolve(None, "Correction: 119,5 kg", [
        {"role": "user", "content": "37 years, 120 kg"}, {"role": "assistant", "content": "Noted"}])
    assert result.consultation == ni.TimelineContext(age=37, weight_kg=119.5)


def test_minor_is_not_given_an_adult_weight_loss_timeline():
    reply = ni.consultation_reply(ni.RequestIntent(ni.Scope.TIMELINE_CONSULTATION,
        consultation=ni.TimelineContext(age=16, weight_kg=80, target_kg=20)), {}, "en")
    assert "under 18" in reply and "0.5-1" not in reply and "20-40" not in reply


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_new_explicit_training_request_still_uses_canonical_engine(runtime, monkeypatch, lang):
    from test_nutrition_acceptance import COMPLETE
    store.save_profile(runtime.uid, {**COMPLETE, "level": "intermediate", "equipment": "home", "frequency": "3"})
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    runtime.select(ni.Scope.OTHER)
    output = runtime.post("Направи ми тренировка за днес." if lang == "bg" else "Create a workout for today.", lang)
    assert output[-1] == {"done": True}
    assert any(isinstance(event.get("training_completion"), dict) for event in output), output


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_explicit_menu_for_saved_goal_exits_consultation_without_using_hypothetical_goal(runtime, monkeypatch, lang):
    case = CASES[lang]
    annotate(runtime, monkeypatch, case)
    runtime.post(case["opening"], lang)
    runtime.select(ni.Scope.DAILY_PLAN, "strength")
    output = runtime.post("Остави хипотезата. Направи дневно меню за записаната ми цел сила." if lang == "bg" else
                          "Set the hypothetical goal aside. Make a daily menu for my saved strength goal.", lang)
    assert output[-1] == {"done": True} and len(store.list_nutrition_plans(runtime.uid)) == 1
