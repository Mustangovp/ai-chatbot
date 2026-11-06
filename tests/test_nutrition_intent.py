"""Semantic provider contract plus real /chat delivery, with no paid API calls.

The scope labels below are independent test annotations, not a runtime phrase
dictionary. These tests prove routing/validation, not live model accuracy.
"""
import json
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

import app as appmod
import db as store
import nutrition_conversation as nc
import nutrition_intent as ni
import nutrition_plan
from test_nutrition_acceptance import VALID_PLAN, TARGET_BLOCK, COMPLETE


_REAL_REQUEST = ni._request


def completion(payload, finish="stop"):
    if isinstance(payload, dict) and "scope" in payload and "requested_goal" not in payload:
        payload = {**payload, "requested_goal": None}
    return NS(choices=[NS(finish_reason=finish, message=NS(content=json.dumps(payload)))])


def events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")]


@pytest.fixture
def runtime(monkeypatch):
    for flag in ("BRAIN_ENFORCE", "RECOMMENDATION_ENGINE_ACTIVE", "CONVERSATION_COMPOSER_ACTIVE",
                 "NUTRITION_ENGINE_V2_ACTIVE", "NUTRITION_ENGINE_V2_SHADOW"):
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "false")
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *_: TARGET_BLOCK)
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_: None)
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()
    uid = store.get_or_create_user("synthetic-intent@example.com")
    store.save_profile(uid, COMPLETE)
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(uid))
    calls = []
    selections = []
    delivery_checks = []
    delivery_language = ["en"]

    def generate(**kwargs):
        calls.append(kwargs)
        if kwargs.get("response_format"):
            payload = deepcopy(VALID_PLAN)
            if delivery_language[0] == "bg":
                names = {"eggs": "Яйца", "oats": "Овесени ядки", "chicken": "Пилешко филе",
                         "rice": "Ориз", "salmon": "Сьомга", "potatoes": "Картофи"}
                for meal in payload["meals"]:
                    for food in meal["foods"]:
                        food["display_name"] = names[food["food_id"]]
            return completion(payload)
        return iter([NS(choices=[NS(delta=NS(content="Answer to the requested question."),
                                    finish_reason="stop")])])

    monkeypatch.setattr(appmod.client.chat.completions, "create", generate)

    def select(scope, requested_goal=None):
        def classify(_client, messages):
            data = json.loads(messages[-1]["content"])
            if "candidate" in data:
                delivery_checks.append(data)
                return completion({"daily_prescription": False})
            selections.append(data)
            return completion({"scope": scope.value, "requested_goal": requested_goal})
        monkeypatch.setattr(ni, "_request", classify)

    def post(message, lang="en", **extra):
        delivery_language[0] = lang
        return events(client.post("/chat", json={"message": message, "lang": lang, **extra}))

    return NS(client=client, uid=uid, calls=calls, selections=selections,
              delivery_checks=delivery_checks, select=select, post=post)


@pytest.mark.parametrize("lang,message", [
    ("bg", "Подреди как да се храня от ставането до лягането утре, с точни порции."),
    ("bg", "Поеми избора на всичко, което ще ям през утрешния ден."),
    ("bg", "Разпредели дневния ми прием в хранения, така че да не мисля какво да готвя."),
    ("en", "Map out everything I should eat from waking up until bedtime tomorrow."),
    ("en", "Take care of all my food choices for tomorrow, with portions at each sitting."),
    ("en", "Organise my entire day's intake into practical servings."),
])
@pytest.mark.parametrize("enforce", [False, True])
def test_unseen_daily_requests_use_canonical_delivery(runtime, monkeypatch, lang, message, enforce):
    if enforce:
        monkeypatch.setenv("BRAIN_ENFORCE", "true")
    # Prove these requests are not rescued by the old phrase gate.
    assert not nc.is_plan_request(message)
    runtime.select(ni.Scope.DAILY_PLAN)
    output = runtime.post(message, lang)
    assert output[-1] == {"done": True}
    assert len(runtime.selections) == 1
    assert len(runtime.calls) == 1, runtime.calls[-1]["messages"][-1]
    assert runtime.calls[0]["response_format"] == {"type": "json_object"}
    records = store.list_nutrition_plans(runtime.uid)
    assert len(records) == 1
    plan = nutrition_plan.from_record(records[0]["plan"])
    assert plan.targets.kcal == 2800
    assert [meal.meal_type for meal in plan.meals] == ["breakfast", "lunch", "dinner"]
    text = "".join(event.get("t", "") for event in output)
    assert "|" in text and "2800" in text
    assert nc.failed_message(lang) not in text
    assert not any("training_completion" in event for event in output)


@pytest.mark.parametrize("scope,lang,message", [
    (ni.Scope.QUESTION, "en", "Why does a daily meal plan need protein at every meal?"),
    (ni.Scope.QUESTION, "bg", "Защо хранителен план без достатъчно белтъчини не е добър избор?"),
    (ni.Scope.SINGLE_MEAL, "en", "Just suggest something for tonight, not a whole meal plan."),
    (ni.Scope.SINGLE_MEAL, "bg", "Искам само закуска, а не дневно меню."),
    (ni.Scope.OTHER, "en", "How can I keep a consistent daily routine?"),
    (ni.Scope.OTHER, "bg", "Как да поддържам постоянен дневен режим?"),
])
def test_negative_scopes_do_not_generate_daily_plan(runtime, scope, lang, message):
    runtime.select(scope)
    output = runtime.post(message, lang)
    assert output[-1] == {"done": True}
    assert all(not call.get("response_format") for call in runtime.calls)
    assert not store.list_nutrition_plans(runtime.uid)
    assert "Answer to the requested question." in str(output)
    assert len(runtime.delivery_checks) == 1


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_ambiguous_scope_is_one_question_without_generation(runtime, lang):
    runtime.select(ni.Scope.AMBIGUOUS)
    output = runtime.post("Помогни ми с храненето." if lang == "bg" else "Help me with eating.", lang)
    assert output == [{"t": ni.clarification(lang)}, {"done": True}]
    assert runtime.calls == []
    assert not store.list_nutrition_plans(runtime.uid)


@pytest.mark.parametrize("lang,message", [("bg", "Без пилешко"), ("en", "No chicken")])
def test_revision_keeps_canonical_targets_and_saved_parent(runtime, lang, message):
    targets = appmod.nutrition_validation.targets_from_profile_block(TARGET_BLOCK)
    parent = nutrition_plan.build_plan(VALID_PLAN, targets, restrictions=(), provenance={})
    store.save_nutrition_plan(runtime.uid, nutrition_plan.to_record(parent))
    runtime.select(ni.Scope.REVISION)
    output = runtime.post(message, lang)
    records = store.list_nutrition_plans(runtime.uid)
    assert len(records) == 2
    revised = nutrition_plan.from_record(records[0]["plan"])
    assert revised.targets == parent.targets
    assert revised.version == parent.version
    assert dict(revised.provenance)["parent_plan_id"] == parent.id
    assert output[-1] == {"done": True}
    assert runtime.calls == []


@pytest.mark.parametrize("lang", ["bg", "en"])
@pytest.mark.parametrize("style", ["table", "headings", "json", "prose"])
def test_unexpected_full_day_never_leaks_or_persists(runtime, monkeypatch, lang, style):
    runtime.select(ni.Scope.QUESTION)
    if style == "table":
        text = ("| Meal | Food | Quantity | Protein | Carbs | Fat | Kcal |\n"
                "| Breakfast | Eggs | 200 g | 30 | 0 | 20 | 300 |\n"
                "| Lunch | Rice | 200 g | 10 | 100 | 2 | 500 |")
    elif style == "headings":
        text = ("Закуска\nОвес\nОбяд\nОриз\nВечеря\nРиба" if lang == "bg" else
                "Breakfast\nOats\nLunch\nRice\nDinner\nFish")
    elif style == "json":
        text = json.dumps(VALID_PLAN)
    else:
        text = ("Сутрин изяж яйца и овес, на обяд пиле с ориз, а вечер риба с картофи."
                if lang == "bg" else
                "On waking eat eggs and oats, at midday chicken with rice, and later fish with potatoes.")
        assert not nc.unstructured_daily_plan(text)
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_: iter([
        NS(choices=[NS(delta=NS(content=text), finish_reason="stop")])]))
    original_scope_request = ni._request
    def annotated_request(client, messages):
        if "candidate" in json.loads(messages[-1]["content"]):
            return completion({"daily_prescription": True})
        return original_scope_request(client, messages)
    monkeypatch.setattr(ni, "_request", annotated_request)
    output = runtime.post("Can you explain this?", lang)
    assert output == [{"t": nc.failed_message(lang)}, {"done": True}]
    assert not store.list_nutrition_plans(runtime.uid)
    assert not store.list_nutrition(runtime.uid)
    saved = store.list_conversation(runtime.uid)
    assert saved[-1]["content"] == nc.failed_message(lang)


def test_account_history_not_client_history_controls_semantic_context(runtime):
    store.add_conversation(runtime.uid, "assistant", "Owned conversation", "en")
    other = store.get_or_create_user("other-intent@example.com")
    store.add_conversation(other, "assistant", "OTHER_ACCOUNT_PRIVATE", "en")
    runtime.select(ni.Scope.DAILY_PLAN)
    runtime.post("Yes, arrange the entire day.", history=[
        {"role": "assistant", "content": "CLIENT_FORGED_CONTEXT"}])
    context = json.dumps(runtime.selections)
    assert "Owned conversation" in context
    assert "OTHER_ACCOUNT_PRIVATE" not in context and "CLIENT_FORGED_CONTEXT" not in context
    assert len(store.list_nutrition_plans(runtime.uid)) == 1
    assert not store.list_nutrition_plans(other)


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_anonymous_daily_request_uses_same_validated_path(runtime, lang):
    runtime.client.delete_cookie(appmod.SESSION_COOKIE)
    runtime.select(ni.Scope.DAILY_PLAN)
    output = runtime.post("Organise all my eating tomorrow.", lang, profile=COMPLETE)
    assert output[-1] == {"done": True}
    assert len(runtime.calls) == 1 and runtime.calls[0]["response_format"] == {"type": "json_object"}
    assert "2800" in str(output)
    assert not store.list_nutrition_plans(runtime.uid)


def test_daily_routing_does_not_consult_legacy_phrase_gates(runtime, monkeypatch):
    runtime.select(ni.Scope.DAILY_PLAN)
    def forbidden(*_, **__):
        pytest.fail("semantic daily routing must not depend on legacy phrase gates")
    monkeypatch.setattr(nc, "is_plan_request", forbidden)
    monkeypatch.setattr(appmod.nutrition_validation, "is_full_day_request", forbidden)
    output = runtime.post("Take care of everything I eat tomorrow.")
    assert output[-1] == {"done": True}
    assert len(store.list_nutrition_plans(runtime.uid)) == 1


@pytest.mark.parametrize("lang", ["bg", "en"])
@pytest.mark.parametrize("enforce", [False, True])
def test_daily_food_request_after_real_workout_is_not_workout_mutation(runtime, monkeypatch, lang, enforce):
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    if enforce:
        monkeypatch.setenv("BRAIN_ENFORCE", "true")
    store.save_profile(runtime.uid, {**COMPLETE, "level": "intermediate",
                                    "equipment": "bodyweight, dumbbells, bench", "recoveryFeel": "fresh"})
    runtime.select(ni.Scope.OTHER)
    first = runtime.post("Create a workout for today.", lang, conversation_id="nutrition-scope-context-01")
    assert any(event.get("training_completion") for event in first), first
    runtime.calls.clear()
    runtime.select(ni.Scope.DAILY_PLAN)
    second = runtime.post(
        "След тази тренировка подреди всичко, което да изям утре." if lang == "bg" else
        "After this workout, arrange everything I should eat tomorrow.",
        lang, conversation_id="nutrition-scope-context-01")
    assert second[-1] == {"done": True}
    assert not any("training_completion" in event for event in second)
    assert len(store.list_nutrition_plans(runtime.uid)) == 1
    assert len(runtime.calls) == 1 and runtime.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_missing_profile_clarifies_without_generating(runtime, monkeypatch, lang):
    runtime.client.delete_cookie(appmod.SESSION_COOKIE)
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *_: "")
    runtime.select(ni.Scope.DAILY_PLAN)
    output = runtime.post("Organise all my eating tomorrow.", lang, profile={"goal": "strength"})
    assert output[-1] == {"done": True}
    assert runtime.calls == []
    assert len(output) == 2 and output[0]["t"].count("?") == 1
    assert not store.list_nutrition_plans(runtime.uid)


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_account_restrictions_remain_authoritative(runtime, lang):
    store.save_profile(runtime.uid, {**COMPLETE, "foodPreferences": "no chicken"})
    runtime.select(ni.Scope.DAILY_PLAN)
    output = runtime.post("Organise all my eating tomorrow.", lang,
                          profile={**COMPLETE, "foodPreferences": ""})
    assert output[-1] == {"done": True}
    assert nutrition_plan.restriction_blocked_message(lang) in str(output)
    assert not store.list_nutrition_plans(runtime.uid)


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_invalid_generation_gets_one_repair_then_existing_failure(runtime, monkeypatch, lang):
    runtime.select(ni.Scope.DAILY_PLAN)
    calls = []
    monkeypatch.setattr(appmod.client.chat.completions, "create",
                        lambda **kwargs: calls.append(kwargs) or completion({"meals": []}))
    monkeypatch.setattr(nutrition_plan, "build_source_backed_plan", lambda *_, **__: None)
    output = runtime.post("Organise all my eating tomorrow.", lang)
    assert len(calls) == 2
    assert len(runtime.selections) == 1
    assert output == [{"t": nc.failed_message(lang)}, {"done": True}]
    assert not store.list_nutrition_plans(runtime.uid)


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_medical_boundary_is_not_overridden_by_scope(runtime, lang):
    runtime.select(ni.Scope.DAILY_PLAN)
    output = runtime.post("I have chest pain. Arrange my food for the entire day.", lang)
    assert output[-1] == {"done": True}
    assert runtime.calls == []
    assert not store.list_nutrition_plans(runtime.uid)
    assert ni.clarification(lang) not in str(output)


def test_interrupted_prose_plan_never_emits_or_persists(runtime, monkeypatch):
    runtime.select(ni.Scope.QUESTION)
    def stream():
        yield NS(choices=[NS(delta=NS(content="Breakfast\nOats\nLunch\nRice\nDinner\nFish"),
                            finish_reason=None)])
        raise ConnectionError("synthetic interruption")
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_: stream())
    output = runtime.post("Can you explain eating patterns?")
    assert not any(event.get("t") or event.get("done") for event in output)
    assert output[-1]["error"] and output[-1]["not_counted"]
    assert not store.list_conversation(runtime.uid)
    assert not store.list_nutrition_plans(runtime.uid)


def test_single_meal_and_ordinary_macro_tables_are_not_daily_plans():
    assert not nc.unstructured_daily_plan("Breakfast\nOats and yogurt")
    assert not nc.unstructured_daily_plan(
        "| Food | Protein | Carbs | Fat | Kcal |\n| Yogurt | 10 | 5 | 2 | 80 |")
    assert not nc.unstructured_daily_plan("Breakfast, lunch and dinner are meal names, not targets.")


def test_meal_comparison_is_not_rejected_merely_for_meal_headings(runtime, monkeypatch):
    runtime.select(ni.Scope.QUESTION)
    text = "Breakfast\nThe first meal.\nLunch\nA midday meal.\nDinner\nAn evening meal."
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_: iter([
        NS(choices=[NS(delta=NS(content=text), finish_reason="stop")])]))
    assert runtime.post("What do these meal names mean?") == [{"t": text}, {"done": True}]
    assert len(runtime.delivery_checks) == 1


@pytest.mark.parametrize("payload,finish", [
    ({"daily_prescription": True}, "stop"), ({"daily_prescription": 0}, "stop"),
    ({"daily_prescription": False, "extra": 1}, "stop"),
    ({"daily_prescription": False}, "length"), ([], "stop"),
])
def test_untrusted_delivery_audit_fails_closed(monkeypatch, payload, finish):
    monkeypatch.setattr(ni, "_request", lambda *_: completion(payload, finish))
    assert not ni.allows_unstructured_delivery(None, "Untrusted text")


def test_delivery_audit_outage_never_emits_candidate(runtime, monkeypatch):
    runtime.select(ni.Scope.QUESTION)
    classify = ni._request
    def request(client, messages):
        if "candidate" in json.loads(messages[-1]["content"]):
            raise TimeoutError()
        return classify(client, messages)
    monkeypatch.setattr(ni, "_request", request)
    assert runtime.post("Can you explain protein?") == [
        {"t": nc.failed_message("en")}, {"done": True}]
    assert not store.list_nutrition_plans(runtime.uid)


def test_long_or_duplicate_semantic_decisions_fail_closed(monkeypatch):
    def no_request(*_):
        pytest.fail("oversized context must not reach provider")
    monkeypatch.setattr(ni, "_request", no_request)
    assert ni.classify(None, "x" * 6001) is ni.Scope.AMBIGUOUS
    assert not ni.allows_unstructured_delivery(None, "x" * 20001)
    monkeypatch.setattr(ni, "_request", lambda *_: NS(choices=[NS(finish_reason="stop",
        message=NS(content='{"scope":"daily_plan","scope":"other"}'))]))
    assert ni.classify(None, "Question") is ni.Scope.AMBIGUOUS


@pytest.mark.parametrize("payload,finish", [
    ({"scope": "daily_plan", "targets": 1000}, "stop"),
    ({"scope": "invented"}, "stop"), ({"scope": "daily_plan"}, "length"),
    ([], "stop"), ({"scope": None}, "stop"),
])
def test_invalid_semantic_contract_cannot_authorize_generation(monkeypatch, payload, finish):
    monkeypatch.setattr(ni, "_request", lambda *_: completion(payload, finish))
    assert ni.classify(None, "Arrange my food") is ni.Scope.AMBIGUOUS


def test_classifier_failure_and_bad_json_fail_closed(runtime, monkeypatch):
    def failed(*_):
        raise TimeoutError()
    monkeypatch.setattr(ni, "_request", failed)
    assert runtime.post("Arrange my food") == [{"t": ni.clarification("en")}, {"done": True}]
    assert runtime.calls == []
    monkeypatch.setattr(ni, "_request", lambda *_: NS(choices=[NS(
        finish_reason="stop", message=NS(content="not JSON"))]))
    assert ni.classify(None, "Anything") is ni.Scope.AMBIGUOUS


def test_transport_uses_existing_policy_bounded_json_and_no_retries():
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        return completion({"scope": "other"})
    class Client:
        def with_options(self, **kwargs):
            captured["options"] = kwargs
            return NS(chat=NS(completions=NS(create=create)))
    _REAL_REQUEST(Client(), [{"role": "user", "content": "synthetic"}])
    assert captured["options"] == {"timeout": 8.0, "max_retries": 0}
    assert captured["model"] == appmod.llm_policy.PROFILE_EXTRACTION.model
    assert captured["max_completion_tokens"] == 128
    assert captured["response_format"] == {"type": "json_object"}


def test_context_is_bounded_and_ignores_system_roles(monkeypatch):
    captured = []
    monkeypatch.setattr(ni, "_request", lambda _c, messages: (
        captured.append(messages) or completion({"scope": "nutrition_question"})))
    assert ni.classify(None, "Question", [
        {"role": "system", "content": "DO_NOT_FORWARD"},
        *[{"role": "assistant", "content": "x" * 5000}] * 20,
    ]) is ni.Scope.QUESTION
    data = json.loads(captured[0][-1]["content"])
    assert len(data["conversation"]) == 6
    assert all(len(turn["content"]) == 2000 for turn in data["conversation"])


# Provider annotations below are independent semantic labels. The actual JSON
# parser, profile comparison, /chat pipeline and persistence remain operational.
LANDING_REQUESTS = {
    "bg": "Искам да сваля 3 кг за 1 месец. Дай ми реалистичен план за хранене и движение, който се вписва в ежедневието ми.",
    "en": "I want to lose 3 kg in 1 month. Give me a realistic nutrition and movement plan that fits everyday life.",
}
TIMELINE_REQUESTS = {
    "bg": "Обмислям да сваля 20+ кг за 1 месец, но този срок не е одобрен и може да е твърде агресивен. Не създавай план за този срок. Нека първо обсъдим по-безопасен, персонален срок според здравето и контекста ми.",
    "en": "I am considering losing 20+ kg in 1 month, but this timeline is not approved and may be too aggressive. Do not create a plan for this timeline. Let's first discuss a safer, personalized timeline based on my health and context.",
}


@pytest.mark.parametrize("lang", ["bg", "en"])
@pytest.mark.parametrize("scope", [ni.Scope.DAILY_PLAN, ni.Scope.COMBINED_PLANNING])
@pytest.mark.parametrize("enforce", [False, True])
def test_landing_goal_conflict_clarifies_before_any_prescription(runtime, monkeypatch, lang, scope, enforce):
    monkeypatch.setenv("BRAIN_ENFORCE", "true" if enforce else "false")
    saved = {**COMPLETE, "goal": "strength"}
    store.save_profile(runtime.uid, saved)
    store.add_account_training_constraints(runtime.uid, ("vertical_push",))
    restrictions = store.list_account_training_constraints(runtime.uid)
    runtime.select(scope, "fat_loss")
    # Even an explicitly forged browser goal cannot replace account authority.
    output = runtime.post(LANDING_REQUESTS[lang], lang, profile={**saved, "goal": "fat_loss"}, first_contact=True)
    text = "".join(event.get("t", "") for event in output)
    assert output[-1] == {"done": True}
    assert ("сила" if lang == "bg" else "strength") in text
    assert ("сваляне на мазнини" if lang == "bg" else "fat loss") in text
    assert ("Храненето и движението" if lang == "bg" else "Nutrition and movement") in text
    assert text.count("?") == 1
    assert "kcal" not in text and "2580" not in text and "|" not in text
    assert not any(event.get("training_completion") for event in output)
    assert runtime.calls == []
    assert runtime.selections[-1]["saved_goal"] == "strength"
    assert store.get_profile(runtime.uid)["goal"] == "strength"
    assert store.list_account_training_constraints(runtime.uid) == restrictions
    assert not store.list_nutrition_plans(runtime.uid)
    assert not store.list_nutrition(runtime.uid) and not store.list_workouts(runtime.uid)


@pytest.mark.parametrize("lang", ["bg", "en"])
@pytest.mark.parametrize("enforce", [False, True])
@pytest.mark.parametrize("anonymous", [False, True])
def test_negated_plan_is_a_cautious_timeline_consultation(runtime, monkeypatch, lang, enforce, anonymous):
    monkeypatch.setenv("BRAIN_ENFORCE", "true" if enforce else "false")
    if anonymous: runtime.client.delete_cookie(appmod.SESSION_COOKIE)
    runtime.select(ni.Scope.TIMELINE_CONSULTATION)
    output = runtime.post(TIMELINE_REQUESTS[lang], lang, profile=COMPLETE, first_contact=True)
    text = "".join(event.get("t", "") for event in output)
    assert output[-1] == {"done": True}
    assert ("по-безопасен срок" if lang == "bg" else "safer timeline") in text
    assert ("лекар" if lang == "bg" else "clinician") in text
    assert ("лекарства" if lang == "bg" else "medications") in text
    assert text.count("?") == 1
    assert nc.failed_message(lang) not in text and ni.clarification(lang) not in text
    assert "kcal" not in text and "|" not in text
    assert runtime.calls == [] and runtime.delivery_checks == []
    assert not any(event.get("training_completion") for event in output)
    assert not store.list_nutrition_plans(runtime.uid) and not store.list_nutrition(runtime.uid)
    assert store.get_profile(runtime.uid)["goal"] == COMPLETE["goal"]


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_combined_request_with_missing_context_explains_both_workflows(runtime, lang):
    runtime.client.delete_cookie(appmod.SESSION_COOKIE)
    runtime.select(ni.Scope.COMBINED_PLANNING, "fat_loss")
    output = runtime.post(LANDING_REQUESTS[lang], lang, profile={"goal": "fat_loss"})
    text = "".join(event.get("t", "") for event in output)
    assert ("хранене и движение" if lang == "bg" else "nutrition and movement") in text
    assert ("налично оборудване" if lang == "bg" else "available equipment") in text
    assert text.count("?") == 1 and runtime.calls == []
    assert not store.list_nutrition_plans(runtime.uid)


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_confirmed_matching_goal_keeps_canonical_daily_delivery(runtime, lang):
    store.save_profile(runtime.uid, {**COMPLETE, "goal": "fat_loss"})
    runtime.select(ni.Scope.DAILY_PLAN, "fat_loss")
    output = runtime.post("Направи ми дневен хранителен план за отслабване." if lang == "bg" else
                          "Create a full-day meal plan for fat loss.", lang)
    assert output[-1] == {"done": True}
    assert len(runtime.calls) == 1 and runtime.calls[0]["response_format"] == {"type": "json_object"}
    assert len(store.list_nutrition_plans(runtime.uid)) == 1
    plan = nutrition_plan.from_record(store.list_nutrition_plans(runtime.uid)[0]["plan"])
    assert plan.targets.kcal == 2800
    text = "".join(event.get("t", "") for event in output)
    assert ("сваляне на мазнини" if lang == "bg" else "fat loss") in text
    assert store.get_profile(runtime.uid)["goal"] == "fat_loss"


def test_goal_conflict_is_derived_not_a_model_authority(monkeypatch):
    monkeypatch.setattr(ni, "_request", lambda *_: completion({"scope": "daily_plan", "requested_goal": "fat_loss"}))
    assert ni.resolve(None, "Synthetic request", saved_goal="strength").scope is ni.Scope.GOAL_REVIEW
    assert ni.resolve(None, "Synthetic request", saved_goal="fat_loss").scope is ni.Scope.DAILY_PLAN
    monkeypatch.setattr(ni, "_request", lambda *_: completion({"scope": "goal_review", "requested_goal": "fat_loss"}))
    assert ni.resolve(None, "Synthetic request", saved_goal="strength").scope is ni.Scope.AMBIGUOUS


@pytest.mark.parametrize("goal", ["cutting_fast", "", False, [], {}])
def test_invalid_requested_goals_cannot_authorize_a_plan(monkeypatch, goal):
    monkeypatch.setattr(ni, "_request", lambda *_: completion({"scope": "daily_plan", "requested_goal": goal}))
    assert ni.resolve(None, "Synthetic request", saved_goal="strength").scope is ni.Scope.AMBIGUOUS


def test_missing_goal_field_fails_closed_without_guessing(monkeypatch):
    monkeypatch.setattr(ni, "_request", lambda *_: NS(choices=[NS(finish_reason="stop",
        message=NS(content='{"scope":"daily_plan"}'))]))
    assert ni.resolve(None, "Synthetic request", saved_goal="strength").scope is ni.Scope.AMBIGUOUS


@pytest.mark.parametrize("scope", [ni.Scope.TIMELINE_CONSULTATION, ni.Scope.COMBINED_PLANNING])
def test_consultation_never_overrides_medical_safety(runtime, scope):
    runtime.select(scope, "fat_loss")
    output = runtime.post("I have chest pain. Do not make a plan; discuss my weight-loss timeline.")
    assert output[-1] == {"done": True}
    assert any(event.get("medical_hold") for event in output)
    assert "safer timeline without creating" not in str(output)
    assert runtime.calls == [] and not store.list_nutrition_plans(runtime.uid)


def test_account_goal_comparison_cannot_cross_accounts(runtime):
    second = store.get_or_create_user("synthetic-second-goal@example.com")
    store.save_profile(second, {**COMPLETE, "goal": "fat_loss"})
    runtime.select(ni.Scope.DAILY_PLAN, "fat_loss")
    first = runtime.post(LANDING_REQUESTS["en"])
    assert "saved goal is strength" in str(first)
    assert not store.list_nutrition_plans(runtime.uid)
    runtime.client.set_cookie(appmod.SESSION_COOKIE, store.create_session(second))
    runtime.post("Create a full-day meal plan for fat loss.")
    assert len(store.list_nutrition_plans(second)) == 1
    assert not store.list_nutrition_plans(runtime.uid)
    assert [item["saved_goal"] for item in runtime.selections] == ["strength", "fat_loss"]


def test_missing_consultation_profile_asks_for_context_without_guessing():
    intent = ni.RequestIntent(ni.Scope.COMBINED_PLANNING)
    reply = ni.consultation_reply(intent, None, "en")
    assert "goal" in reply and "available equipment" in reply
    assert "kcal" not in reply and reply.count("?") == 1


def test_goal_confirmation_requires_explicit_profile_change_before_prescribing(runtime):
    runtime.select(ni.Scope.DAILY_PLAN, "fat_loss")
    runtime.post(LANDING_REQUESTS["en"])
    runtime.post("Yes, please go ahead with the fat-loss goal.")
    assert runtime.calls == [] and not store.list_nutrition_plans(runtime.uid)
    assert store.get_profile(runtime.uid)["goal"] == "strength"
    assert "saved goal is strength" in json.dumps(runtime.selections[-1]["conversation"])
    response = runtime.client.put("/api/profile", json={"profile": {"goal": "fat_loss"}})
    assert response.status_code == 200
    runtime.post("Create the full-day nutrition plan for my confirmed goal.")
    assert store.get_profile(runtime.uid)["goal"] == "fat_loss"
    assert len(store.list_nutrition_plans(runtime.uid)) == 1
