"""
M4 Commit 2 — /chat enforcement wiring, gated by BRAIN_ENFORCE (OFF by default).

Proves at the /chat surface:
  • OFF  → byte-identical: no decision event, system prompt unmodified.
  • ON   → enforcement activates: leading {"decision":...} event.
  • ON + emergency → routes; generation is steered away from a workout
    (SAFETY OVERRIDE injected, should_generate=False).
  • ON + GO/MODIFY → continues through generation with S1 constraints injected.

The OpenAI stream is faked (records the exact system prompt sent). The emergency
and OFF cases use a REAL message through the REAL cascade; the MODIFY case stubs
only the Decision source (the cascade verdict is unit-tested elsewhere) so the
WIRING for a permitted-but-constrained decision is exercised end-to-end.
"""
import os
import json
import types
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import pytest

import app as appmod
from recommend import engine as recommendation_planning
import db as store
import decision_engine
import conversation_composer
import nutrition_conversation
import nutrition_plan
from training_engine import build_training_plan, load_exercise_library
from recommend import diversity as recommendation_diversity
from recommend.blueprint import NutritionBlueprint, WorkoutBlueprint, to_dict
from context_builder import LockedPreferences, Subject, build_context
from brain.runtime_assets import expert_consensus, persona_matcher
from brain.runtime_assets import persona_expert_projection
from brain.runtime_assets.expert_rules import ExpertRulePack, load_expert_rule_packs
from brain.runtime_assets.personas import load_runtime_personas
from nutrition_validation import NutritionTargets, validate_daily_nutrition
from brain.types import (Decision, Verdict, Intervention, S2State, ConstraintSet,
                         Constraint, ConstraintTier, CapacityEnvelope)
from datetime import datetime, timedelta, timezone


# ── Fake OpenAI streaming client ─────────────────────────────────────────────
class _Delta:
    def __init__(self, c): self.content = c
class _Choice:
    def __init__(self, c): self.delta = _Delta(c)
class _Chunk:
    def __init__(self, c): self.choices = [_Choice(c)]


class _StructuredCompletion:
    def __init__(self, payload):
        message = type("Message", (), {"content": json.dumps(payload)})()
        self.choices = [type("Choice", (), {"message": message})()]


@pytest.fixture
def captured(monkeypatch):
    box = {}

    def fake_create(**kwargs):
        box["system"] = kwargs["messages"][0]["content"]      # snapshot at call time
        box["messages"] = kwargs["messages"]
        box["model"] = kwargs.get("model")
        def _stream():
            yield _Chunk("ok")
        return _stream()

    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)
    return box


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


@pytest.fixture(autouse=True)
def _enforce_off_by_default(monkeypatch):
    monkeypatch.delenv("BRAIN_ENFORCE", raising=False)        # default OFF for every test
    monkeypatch.delenv("RECOMMENDATION_ENGINE_ACTIVE", raising=False)
    monkeypatch.delenv("CONVERSATION_COMPOSER_ACTIVE", raising=False)
    monkeypatch.delenv("PERSONA_MATCHER_SHADOW", raising=False)
    monkeypatch.delenv("EXPERT_CONSENSUS_SHADOW", raising=False)
    monkeypatch.delenv("PERSONA_EXPERT_COMMUNICATION_ACTIVE", raising=False)
    monkeypatch.delenv("TRAINING_ENGINE_ACTIVE", raising=False)
    yield


def _events(resp):
    out = []
    for line in resp.get_data(as_text=True).splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _post(client, message, profile=None, *, voice=False):
    payload = {"message": message, "lang": "en", "profile": profile or {}}
    if voice:
        payload["voice"] = True
    return client.post("/chat", json=payload)


def _set_stream(monkeypatch, captured, reply):
    def fake_create(**kwargs):
        captured["system"] = kwargs["messages"][0]["content"]
        captured["messages"] = kwargs["messages"]
        if kwargs.get("response_format"):
            return _StructuredCompletion(reply)
        def stream():
            yield _Chunk(reply)
        return stream()

    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)


def test_chat_applies_traceable_completed_workout_to_next_training_revision(client, captured, monkeypatch):
    profile = _profile(recoveryFeel="fresh")
    parent = build_training_plan(recommendation_blueprint_id="chat-lifecycle", facts=profile)
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod, "_active_training_plan", lambda *_args: parent)
    _set_stream(monkeypatch, captured, json.dumps({"explanations": ["Stay controlled today."]}))
    completion = appmod.training_renderer.render_completion_projection(parent, load_exercise_library())
    session = completion["sessions"][0]
    exercises = [{
        "prescription_id": item["prescription_id"],
        "exercise_id": item["exercise_id"],
        "exercise_version": item["exercise_version"],
        "completed_sets": item["prescribed_sets"],
        "completed_repetitions": item["rep_max"],
        "completed_load": "20",
        "completed_rpe": "7",
        "completed_rir": 3,
    } for item in session["exercises"]]
    response = client.post("/chat", json={
        "message": "build a workout", "lang": "en", "profile": profile,
        "completed_workout": {
            "workout_id": "chat-lifecycle-1", "plan_id": parent.plan_id,
            "plan_version": parent.version, "session_id": session["session_id"],
            "completion_timestamp": "2026-07-01T10:00:00Z", "exercises": exercises,
        },
        "recovery": {
            "state": "normally_recovered", "accumulated_fatigue": "30",
            "source_version": "recovery-policy-v1",
        },
    })

    events = _events(response)
    assert response.status_code == 200
    assert ':revision:' in captured["system"]
    assert '"plan_id": "' in captured["system"]
    assert events[0]["t"].startswith("**Workout**")
    assert events[-1] == {"done": True}


def test_api_workout_accepts_and_preserves_the_immutable_completion_contract(client, monkeypatch):
    profile = _profile(recoveryFeel="fresh")
    _login_for_chat(client, profile)
    plan = build_training_plan(recommendation_blueprint_id="api-completion", facts=profile)
    projection = appmod.training_renderer.render_completion_projection(plan, load_exercise_library())
    session = projection["sessions"][0]
    completion = {
        "workout_id": "api-completion-1", "plan_id": plan.plan_id, "plan_version": plan.version,
        "session_id": session["session_id"], "completion_timestamp": "2026-07-20T10:00:00Z",
        "exercises": [{
            "prescription_id": item["prescription_id"], "exercise_id": item["exercise_id"],
            "exercise_version": item["exercise_version"], "completed_sets": item["prescribed_sets"],
            "completed_repetitions": item["rep_max"], "completed_load": None,
            "completed_rpe": None, "completed_rir": None,
        } for item in session["exercises"]],
    }
    captured = {}
    monkeypatch.setattr(appmod.store, "log_workout", lambda _uid, payload: captured.update(session=payload) or "workout-1")

    response = client.post("/api/workout", json={"session": {"type": "full body", "exercises": []},
                                                   "workout_completion": completion})

    assert response.status_code == 200
    assert captured["session"]["workout_completion"] == completion


def test_chat_rejects_untraceable_lifecycle_evidence_without_legacy_generation(client, captured, monkeypatch):
    profile = _profile(recoveryFeel="fresh")
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    _set_stream(monkeypatch, captured, json.dumps({"explanations": ["unused"]}))
    response = client.post("/chat", json={
        "message": "build a workout", "lang": "en", "profile": profile,
        "completed_workout": {"workout_id": "missing-identity"},
    })

    events = _events(response)
    assert events[0]["t"]
    assert events[-1] == {"done": True}
    assert "messages" not in captured


def test_conversation_composer_frames_acknowledgement_and_one_question():
    decision = types.SimpleNamespace(outcome="converse", reason="general conversation")
    policy = conversation_composer.build_policy(
        decision=decision, message="Писна ми, нищо не се получава.",
        conversation=[{"role": "assistant", "content": "A prior plan"}])
    frame = conversation_composer.compose(policy, verified_memory=[{"role": "assistant", "content": "A prior plan"}])
    assert frame.mode == "acknowledge_then_ask"
    assert frame.acknowledgement is True
    assert frame.question == "obstacle"
    assert frame.closing_style == "one_question"
    assert frame.must_not_generate_plan is True


def test_conversation_composer_respects_plan_only_and_voice_summary():
    decision = types.SimpleNamespace(outcome="recommend", reason="coaching request")
    plan_only = conversation_composer.build_policy(decision=decision, message="Само плана.")
    voice = conversation_composer.build_policy(decision=decision, message="Говори накратко.", voice=True)
    assert plan_only.explain_why is False
    assert plan_only.mode == "deliver_structured_plan"
    assert voice.verbal_summary_only is True
    assert "Never read tables" in conversation_composer.render_prompt(
        conversation_composer.compose(voice), "en")


@pytest.mark.parametrize("bg,en", [
    ("омръзна ми", "I’m tired of this"),
    ("писна ми", "I’m fed up"),
    ("не ми харесва", "I don’t like this"),
    ("не това имах предвид", "that’s not what I meant"),
])
def test_conversation_composer_recognizes_equivalent_bulgarian_and_english_repair_requests(bg, en):
    decision = types.SimpleNamespace(outcome="converse", reason="general conversation")

    bg_policy = conversation_composer.build_policy(decision=decision, message=bg)
    en_policy = conversation_composer.build_policy(decision=decision, message=en)

    assert bg_policy.mode == en_policy.mode == "acknowledge_then_ask"
    assert bg_policy.question == en_policy.question in {"change", "obstacle"}


def test_conversation_composer_voice_projection_is_structured_safe_and_language_aware():
    decision = types.SimpleNamespace(outcome="recommend", reason="coaching request")
    frame = conversation_composer.compose(
        conversation_composer.build_policy(decision=decision, message="build a workout", voice=True))
    workout = conversation_composer.speech_projection(
        "**Workout**\n- **Push-up**: 3 sets\n- Why: This keeps today's effort manageable.",
        frame, "en", structured_kind="workout")
    nutrition = conversation_composer.speech_projection(
        "| Meal | Food | Kcal |\n| Breakfast | Oats | 700 |\n| Daily Total | | 2800 |",
        frame, "bg", structured_kind="nutrition")

    assert workout == "Your workout is ready. This keeps today's effort manageable. The full plan is visible on screen."
    assert nutrition == "Пълният ти хранителен план за деня е готов. Храненията и точните стойности са на екрана."
    assert not any(term in workout.lower() for term in ("push-up", "sets", "blueprint"))
    assert not any(term in nutrition.lower() for term in ("kcal", "oats", "|"))


def test_conversation_composer_voice_projection_preserves_complete_safety_message():
    safety = "I can't assess urgent medical symptoms here. Please contact a qualified medical professional."

    assert conversation_composer.speech_projection(
        safety, None, "en", safety_response=True) == safety


def test_conversation_composer_references_memory_only_when_relevant_and_never_repeats_greetings():
    decision = types.SimpleNamespace(outcome="converse", reason="general conversation")
    without_memory = conversation_composer.build_policy(
        decision=decision, message="Tell me why", conversation=[])
    with_memory = conversation_composer.build_policy(
        decision=decision, message="Tell me why", conversation=[{"role": "assistant", "content": "A plan"}])
    opening = conversation_composer.build_policy(
        decision=decision, message="continue", session_start=True)
    assert conversation_composer.compose(without_memory, verified_memory=[]).reference_memory is False
    assert conversation_composer.compose(
        with_memory, verified_memory=[{"role": "assistant", "content": "A plan"}]).reference_memory is True
    assert opening.must_not_greet is True


def test_conversation_composer_never_accepts_internal_persona_or_expert_data():
    decision = types.SimpleNamespace(outcome="recommend", reason="coaching request")
    policy = conversation_composer.build_policy(decision=decision, message="build a workout")
    frame = conversation_composer.compose(
        policy, authority_facts={"goal": "strength", "recoveryFeel": "tired"},
        persona_projection={"primary_persona_id": "P-001", "confidence": 0.99},
        expert_communication_constraints=("rule-id",),
    )
    prompt = conversation_composer.render_prompt(frame, "en")
    assert "P-001" not in prompt and "rule-id" not in prompt and "0.99" not in prompt
    assert frame.reference_fact == "recoveryFeel"


def test_conversation_composer_flag_off_preserves_legacy_prompt(client, captured, monkeypatch):
    monkeypatch.delenv("CONVERSATION_COMPOSER_ACTIVE", raising=False)
    response = _post(client, "hello", profile=_profile())
    assert response.status_code == 200
    assert "CONVERSATION COMPOSER V1" not in captured["system"]


def test_conversation_composer_flag_on_appends_without_replacing_blueprint(client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))
    response = _post(client, "build a workout", profile=_profile())
    assert response.status_code == 200
    assert appmod.recommendation_renderer.render_prompt(blueprint) in captured["system"]
    assert "CONVERSATION COMPOSER V1" in captured["system"]
    assert _events(response)[0]["t"] == appmod.recommendation_renderer.render_delivery(blueprint, [], "en")


def test_conversation_composer_preserves_nutrition_contract_and_single_delivery_write(client, captured, monkeypatch):
    uid = _login_for_chat(client, _profile())
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    profile_block = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day"
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    _set_stream(monkeypatch, captured, _structured_plan_payload())

    response = _post(client, "Give me a full-day nutrition plan")

    assert response.status_code == 200
    response.get_data()
    assert "CONVERSATION COMPOSER V1" in captured["system"]
    assert "Return a JSON object only" in captured["system"]
    saved = store.list_conversation(uid, limit=10)
    assert [(turn["role"], turn["content"]) for turn in saved] == [
        ("user", "Give me a full-day nutrition plan"), ("assistant", _structured_plan_text()),
    ]


def test_conversation_composer_active_consumes_free_quota_once(client, captured, monkeypatch):
    calls = []
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setattr(appmod.store, "free_usage_consume",
                        lambda *args: calls.append(args) or {"allowed": True})

    response = _post(client, "hello", profile=_profile())

    assert response.status_code == 200
    assert len(calls) == 1
    assert "CONVERSATION COMPOSER V1" in captured["system"]


@pytest.mark.parametrize("message", ["Спри.", "Stop."])
def test_exact_stop_command_bypasses_generation_quota_persistence_and_learning(client, captured, monkeypatch, message):
    quota_calls, persistence_calls, learning_calls = [], [], []
    monkeypatch.setattr(appmod.store, "free_usage_consume",
                        lambda *args: quota_calls.append(args) or {"allowed": True})
    monkeypatch.setattr(appmod.store, "add_conversation",
                        lambda *args: persistence_calls.append(args))
    monkeypatch.setattr(appmod, "_update_learning_engine",
                        lambda *args: learning_calls.append(args))

    response = _post(client, message, profile=_profile())

    assert _events(response) == [{"done": True}]
    assert "messages" not in captured
    assert quota_calls == []
    assert persistence_calls == []
    assert learning_calls == []


@pytest.mark.parametrize("message", [
    "Защо спря прогресът ми?", "Не искам да спирам тренировките.",
    "Stop giving me squats.", "I cannot stop eating sweets.",
])
def test_semantic_stop_phrases_remain_normal_conversation(client, captured, message):
    response = _post(client, message, profile=_profile())
    assert any(event.get("t") == "ok" for event in _events(response))
    assert "messages" in captured


def test_conversation_policy_is_built_after_active_workout_blueprint(client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    order = []
    original_policy = appmod.conversation_composer.build_policy
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod, "_active_workout_recommendation",
                        lambda *args: order.append("blueprint") or (blueprint, None, "persona_expert", None, None))
    monkeypatch.setattr(appmod.conversation_composer, "build_policy",
                        lambda **kwargs: order.append("policy") or original_policy(**kwargs))
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))

    response = _post(client, "build a workout", profile=_profile())

    assert response.status_code == 200
    assert order == ["blueprint", "policy"]


def test_blueprint_prompt_precedes_communication_projection_and_preserves_apex_tone(client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))

    response = _post(client, "build a workout", profile=_profile())

    assert response.status_code == 200
    renderer_prompt = appmod.recommendation_renderer.render_prompt(blueprint)
    assert captured["system"].startswith(renderer_prompt)
    assert captured["system"] == renderer_prompt + "\n\n" + captured["system"][len(renderer_prompt) + 2:]
    assert "CONVERSATION COMPOSER V1" in captured["system"]
    assert "APEX is calm, observant, direct" in captured["system"]
    assert "Do not change, omit, add, reorder, or reinterpret any supplied value." in captured["system"]


def test_composer_failure_after_blueprint_falls_back_to_blueprint_only_prompt(client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    monkeypatch.setattr(appmod.conversation_composer, "compose",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("composer failure")))
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))

    response = _post(client, "build a workout", profile=_profile())

    assert response.status_code == 200
    assert captured["system"] == appmod.recommendation_renderer.render_prompt(blueprint)


# ── OFF = byte-identical ─────────────────────────────────────────────────────
def test_off_is_identical_no_decision_event(client, captured):
    resp = _post(client, "I need recovery today")
    evs = _events(resp)
    assert not any("decision" in e for e in evs)              # no leading decision event
    assert "SAFETY OVERRIDE" not in captured["system"]        # system prompt untouched
    assert any(e.get("t") == "ok" for e in evs) and any(e.get("done") for e in evs)


# ── ON + emergency → route, never a workout ──────────────────────────────────
def test_on_emergency_routes_and_blocks_workout(client, captured, monkeypatch):
    monkeypatch.setenv("BRAIN_ENFORCE", "1")
    resp = _post(client, "my chest feels tight and heavy going uphill")
    evs = _events(resp)
    assert "messages" not in captured
    assert evs == [{"t": "I can't assess urgent medical symptoms here. Please contact a qualified medical professional, or local emergency services if this feels urgent."}, {"done": True}]


# ── ON + GO/MODIFY → continues to constrained generation ─────────────────────
def test_on_modify_continues_with_constraints(client, captured, monkeypatch):
    monkeypatch.setenv("BRAIN_ENFORCE", "1")

    cs = ConstraintSet()
    cs.add(Constraint("valsalva", ConstraintTier.ABSOLUTE, "k"))
    modify = Decision(
        verdict=Verdict.MODIFY, intervention=Intervention("training", "k"),
        generate_training=True, halt=False, verdict_confidence=0.6,
        constraints=cs, envelope=CapacityEnvelope(0.4, 0.4, 0.4, False, 0.6),
        s2=S2State(readiness=0.6, readiness_conf=0.6, red_flags=[], halt=False),
        need_vector=[("training", 0.9)], decision_id="d", model=None)
    monkeypatch.setattr(appmod.brain_cascade, "decide", lambda *a, **k: modify)

    resp = _post(client, "give me a strength workout", profile={"healthNotes": "high blood pressure"})
    evs = _events(resp)
    decision = next(e["decision"] for e in evs if "decision" in e)
    assert decision["verdict"] == "MODIFY" and decision["generate"] is True
    # Generation proceeded, with the constraint injected into the system prompt.
    assert "valsalva" in captured["system"]
    assert any(e.get("t") == "ok" for e in evs) and any(e.get("done") for e in evs)


# ── ON + benign/no-cascade-signal → still generates (no false refusal) ────────
def test_on_healthy_request_still_generates(client, captured, monkeypatch):
    monkeypatch.setenv("BRAIN_ENFORCE", "1")
    # Anonymous → NOT_YET by conservative default; assert it never silently drops
    # the generation call (voice always streams) and emits a decision event.
    resp = _post(client, "what should I eat after training")
    evs = _events(resp)
    assert any("decision" in e for e in evs)
    assert any(e.get("t") == "ok" for e in evs) and any(e.get("done") for e in evs)


# ── GOLDEN: the OFF path is byte-identical to the legacy prompt ───────────────
def test_offpath_golden_prompt_identity(client, captured, monkeypatch):
    """Pre-activation guard (user precondition #2): with BRAIN_ENFORCE OFF, the
    exact system prompt sent to the model MUST equal the legacy assembly —
    enforcement injects nothing. The composed voice reads the wall clock, so we
    freeze it to make the golden deterministic."""
    import datetime as _rdt
    import personality

    class _FrozenDT:                                   # freeze personality's clock
        class datetime:
            @staticmethod
            def now(tz=None):
                return _rdt.datetime(2026, 7, 6, 10, 0, 0, tzinfo=tz or _rdt.timezone.utc)
            @staticmethod
            def fromisoformat(s):
                return _rdt.datetime.fromisoformat(s)
        timezone = _rdt.timezone
    monkeypatch.setattr(personality, "_dt", _FrozenDT)

    profile = {"level": "intermediate", "activityLevel": "active",
               "goal": "strength", "age": 34, "gender": "male", "equipment": "gym"}
    msg = "plan my training week"

    resp = _post(client, msg, profile=profile)         # BRAIN_ENFORCE OFF (autouse)
    got = captured["system"]

    # Reconstruct the legacy prompt with the SAME primitives + frozen clock.
    personality_block = personality.compose(lang="en", profile=profile, workouts=[],
                                            message=msg, conversation=[])
    profile_block = appmod._build_profile_block(profile, "en")
    base = (profile_block + "\n\n" + appmod.SYSTEM_INSTRUCTIONS) if profile_block else appmod.SYSTEM_INSTRUCTIONS
    golden = (personality_block + "\n\n" + base) if personality_block else base

    assert got == golden                               # byte-identical to legacy assembly
    assert "SAFETY OVERRIDE" not in got and "AVOID/adapt" not in got
    assert not any("decision" in e for e in _events(resp))   # no leading decision event
    # Sanity: the golden is a real, non-empty APEX prompt (identity anchor present).
    assert appmod.SYSTEM_INSTRUCTIONS and appmod.SYSTEM_INSTRUCTIONS in got


# Phase A1: pure ContextSnapshot contract. These tests deliberately do not wire
# context_builder into /chat; the existing enforcement tests above remain the
# behavior-regression guard for the current runtime.
_NOW = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


def _account(identity="account-a"):
    return Subject("account", identity, True)


def _device(identity="device-a"):
    return Subject("anonymous_device", identity, False)


def _profile(**extra):
    base = {"goal": "strength", "equipment": "gym", "level": "intermediate",
            "age": "30", "height": "180", "weight": "80",
            "sleepQuality": "poor", "stressLevel": "high", "recoveryFeel": "tired"}
    base.update(extra)
    return base


def test_context_db_profile_overrides_browser_profile_for_account():
    snap = build_context(intent="workout", subject=_account(), request_time=_NOW,
                         db_profile=_profile(goal="strength"),
                         browser_profile=_profile(goal="fat_loss"))
    assert snap.profile["goal"].value == "strength"
    assert snap.profile["goal"].source == "db_profile"


def test_context_anonymous_uses_device_scoped_browser_profile():
    snap = build_context(intent="workout", subject=_device(), request_time=_NOW,
                         browser_profile=_profile(goal="endurance"))
    assert snap.profile["goal"].value == "endurance"
    assert snap.profile["goal"].source == "browser"


def test_context_account_history_prevents_browser_duplicates():
    db_turns = [{"role": "user", "content": "db only"}]
    browser_turns = [{"role": "user", "content": "browser duplicate"}]
    snap = build_context(intent="question", subject=_account(), request_time=_NOW,
                         db_profile=_profile(), db_conversation=db_turns,
                         browser_conversation=browser_turns)
    assert [m["content"] for m in snap.conversation] == ["db only"]


def test_context_account_workouts_override_client_workout_context():
    snap = build_context(intent="workout", subject=_account(), request_time=_NOW,
                         db_profile=_profile(), db_workouts=[{"id": "db", "type": "upper"}],
                         client_workout_context=[{"id": "client", "type": "lower"}])
    assert [w["id"] for w in snap.workouts] == ["db"]


def test_context_explicit_fact_overrides_human_learning_fact():
    snap = build_context(intent="workout", subject=_account(), request_time=_NOW,
                         db_profile=_profile(), human_learning={"goal": "fat_loss"},
                         explicit_facts={"goal": "strength"})
    assert snap.profile["goal"].value == "strength"
    assert snap.profile["goal"].source == "explicit"


def test_context_declared_injury_overrides_athlete_inference():
    snap = build_context(intent="workout", subject=_account(), request_time=_NOW,
                         db_profile=_profile(injuries="right knee injury"),
                         athlete_projection={"injuries": {"value": "none", "observed_at": _NOW,
                                                          "ttl_seconds": 3600, "confidence": 0.70}})
    assert snap.profile["injuries"].value == "right knee injury"
    assert snap.profile["injuries"].source == "db_profile"


def test_context_locked_preferences_win_over_lower_authority_sources():
    locked = LockedPreferences(allergies=("peanuts",), dietary=("vegan",))
    snap = build_context(intent="nutrition", subject=_account(), request_time=_NOW,
                         db_profile=_profile(allergies="dairy"), locked_preferences=locked,
                         recommendation_preferences={"prefer": ["whey"]})
    assert snap.locked_preferences.allergies == ("peanuts",)
    assert snap.locked_preferences.dietary == ("vegan",)
    assert snap.profile["allergies"].value == ("peanuts",)
    assert snap.profile["allergies"].source == "locked"
    assert "recommendation_preferences" not in snap.llm_projection()


def test_context_subjects_are_isolated():
    a = build_context(intent="workout", subject=_account("a"), request_time=_NOW,
                      db_profile=_profile(goal="strength"))
    b = build_context(intent="workout", subject=_account("b"), request_time=_NOW,
                      db_profile=_profile(goal="fat_loss"))
    anonymous = build_context(intent="workout", subject=_device("d"), request_time=_NOW,
                              browser_profile=_profile(goal="endurance"))
    assert a.profile["goal"].value == "strength"
    assert b.profile["goal"].value == "fat_loss"
    assert anonymous.profile["goal"].value == "endurance"
    assert a.snapshot_id != b.snapshot_id != anonymous.snapshot_id


def test_context_fresh_human_state_overrides_stale_profile_recovery_values():
    snap = build_context(intent="recovery", subject=_account(), request_time=_NOW,
                         db_profile=_profile(), human_state={
                             "sleep": {"value": "good", "observed_at": _NOW,
                                       "ttl_seconds": 3600, "confidence": 0.90},
                             "stress": {"value": "low", "observed_at": _NOW,
                                        "ttl_seconds": 3600, "confidence": 0.90},
                             "recovery": {"value": "fresh", "observed_at": _NOW,
                                          "ttl_seconds": 3600, "confidence": 0.90},
                         })
    assert snap.profile["sleepQuality"].value == "good"
    assert snap.profile["stressLevel"].value == "low"
    assert snap.profile["recoveryFeel"].value == "fresh"


def test_context_excludes_expired_state_and_stale_athlete_projection():
    past = _NOW - timedelta(hours=3)
    snap = build_context(intent="recovery", subject=_account(), request_time=_NOW,
                         db_profile=_profile(),
                         human_state={"sleep": {"value": "good", "observed_at": past, "ttl_seconds": 60}},
                         athlete_projection={"fatigue": {"value": "high", "observed_at": past, "ttl_seconds": 60}})
    assert "sleep" not in snap.current_state
    assert "fatigue" not in snap.current_state
    assert snap.profile["sleepQuality"].value == "poor"


def test_context_permanent_injury_is_not_expired_and_missing_requirements_are_omitted():
    snap = build_context(intent="workout", subject=_account(), request_time=_NOW,
                         db_profile={"injuries": "knee injury"},
                         locked_preferences=LockedPreferences(permanent_injuries=("knee injury",)))
    assert snap.profile["injuries"].expires_at is None
    assert {"missing:goal", "missing:equipment", "missing:level"}.issubset(set(snap.omissions))


def test_context_is_deterministic_and_source_order_independent():
    records_a = [{"id": "b", "content": "second"}, {"id": "a", "content": "first"}]
    records_b = list(reversed(records_a))
    kwargs = dict(intent="question", subject=_account(), request_time=_NOW, db_profile=_profile())
    first = build_context(**kwargs, db_conversation=records_a)
    second = build_context(**kwargs, db_conversation=records_b)
    assert first.snapshot_id == second.snapshot_id
    assert first.semantic_payload() == second.semantic_payload()
    assert first.provenance == second.provenance


def test_context_objects_are_immutable_and_expose_source_confidence():
    snap = build_context(intent="workout", subject=_account(), request_time=_NOW,
                         db_profile=_profile())
    assert snap.profile["goal"].confidence == 1.00
    with pytest.raises((FrozenInstanceError, TypeError)):
        snap.intent = "nutrition"
    with pytest.raises(TypeError):
        snap.profile["goal"] = "fat_loss"


def test_context_llm_projection_and_logging_metadata_are_redacted():
    snap = build_context(intent="account", subject=_account(), request_time=_NOW,
                         access={"plan": "pro", "session_id": "session-secret",
                                 "stripe_customer_id": "cus_secret", "feature_flags": {"x": True}},
                         db_profile=_profile(), db_conversation=[{"content": "private"}],
                         db_workouts=[{"id": "workout-secret"}], db_nutrition=[{"content": "private meal"}])
    projection = str(snap.llm_projection())
    metadata = str(snap.redacted_metadata())
    assert "session-secret" not in projection and "cus_secret" not in projection
    assert "private" not in projection and "workout-secret" not in projection
    assert "account-a" not in metadata and "session-secret" not in metadata


def test_context_intent_minimization():
    sources = dict(subject=_account(), request_time=_NOW, db_profile=_profile(),
                   db_workouts=[{"id": "workout"}], db_nutrition=[{"id": "nutrition"}],
                   db_conversation=[{"role": "user", "content": "history"}])
    workout = build_context(intent="workout", **sources)
    nutrition = build_context(intent="nutrition", **sources)
    account = build_context(intent="account", **sources)
    general = build_context(intent="general_conversation", **sources)
    medical = build_context(intent="medical", **sources)
    assert workout.workouts and not workout.nutrition
    assert nutrition.nutrition and not nutrition.workouts
    assert not account.profile and not account.workouts and not account.conversation
    assert len(general.conversation) <= 2 and not general.workouts and not general.nutrition
    assert not medical.workouts and not medical.nutrition
    assert "equipment" not in medical.profile


# Phase A1.1: legacy prompt adapter. Canonical ContextSnapshot semantics remain
# deterministic; this adapter preserves the exact prompt-variable shapes that
# app.chat currently provides until A2 is approved to wire it.
def _legacy_variables(profile, workouts, history, limit):
    return {"profile": profile, "workouts": workouts, "history": history[-limit:]}


def test_legacy_projection_preserves_db_chronological_conversation_order():
    chronological = [{"role": "user", "content": "first"},
                     {"role": "assistant", "content": "second"},
                     {"role": "user", "content": "third"}]
    snap = build_context(intent="question", subject=_account(), request_time=_NOW,
                         db_profile=_profile(), db_conversation=chronological)
    assert snap.legacy_prompt_projection(conversation_limit=60).prompt_variables()["history"] == chronological


def test_legacy_projection_preserves_db_workout_chronological_order():
    workouts = [{"occurred_at": "2026-07-01", "type": "lower"},
                {"occurred_at": "2026-07-02", "type": "upper"}]
    snap = build_context(intent="workout", subject=_account(), request_time=_NOW,
                         db_profile=_profile(), db_workouts=workouts)
    assert snap.legacy_prompt_projection(conversation_limit=60).prompt_variables()["workouts"] == workouts


def test_legacy_projection_preserves_raw_full_profile_and_current_field_coverage():
    profile = {
        **_profile(), "name": "Ava", "weight": "71.5", "height": "170", "gender": "female",
        "foodPreferences": ["vegan", "gluten_free"], "allergies": "peanuts",
        "healthNotes": "knee pain", "assessmentResults": {"pushups": {"count": 10}},
        "workoutContext": "RAW WORKOUT CONTEXT", "progressContext": "RAW PROGRESS",
        "adaptiveMemory": {"sessionDuration": {"preferredMinutes": 30}},
        "activeInsights": "keep it simple",
    }
    snap = build_context(intent="question", subject=_account(), request_time=_NOW, db_profile=profile)
    projected = snap.legacy_prompt_projection(conversation_limit=60).prompt_variables()["profile"]
    assert projected == profile
    for key in ("goal", "equipment", "level", "sleepQuality", "stressLevel", "healthNotes",
                "foodPreferences", "allergies", "assessmentResults", "workoutContext",
                "progressContext", "adaptiveMemory", "activeInsights"):
        assert projected[key] == profile[key]


def test_legacy_projection_personality_inputs_match_legacy_shapes():
    profile = _profile(workoutContext="remember this")
    workouts = [{"id": "w1", "type": "lower"}]
    history = [{"role": "user", "content": "hello"}]
    snap = build_context(intent="question", subject=_account(), request_time=_NOW,
                         db_profile=profile, db_workouts=workouts, db_conversation=history)
    projected = snap.legacy_prompt_projection(conversation_limit=60).prompt_variables()
    assert projected == _legacy_variables(profile, workouts, history, 60)
    assert isinstance(projected["profile"], dict)
    assert isinstance(projected["workouts"], list)
    assert isinstance(projected["history"], list)


def test_legacy_projection_anonymous_matches_current_browser_behavior():
    profile = _profile(goal="endurance", workoutContext="browser context")
    history = [{"role": "user", "content": "browser turn"}]
    snap = build_context(intent="question", subject=_device(), request_time=_NOW,
                         browser_profile=profile, browser_conversation=history,
                         client_workout_context=[{"id": "ignored-by-legacy-personality"}])
    projected = snap.legacy_prompt_projection(conversation_limit=12).prompt_variables()
    assert projected == _legacy_variables(profile, [], history, 12)


def test_legacy_projection_authenticated_matches_db_authoritative_behavior():
    db_profile = _profile(goal="strength")
    browser_profile = _profile(goal="fat_loss")
    db_history = [{"role": "user", "content": "db"}]
    browser_history = [{"role": "user", "content": "browser"}]
    db_workouts = [{"id": "db-workout"}]
    snap = build_context(intent="question", subject=_account(), request_time=_NOW,
                         db_profile=db_profile, browser_profile=browser_profile,
                         db_conversation=db_history, browser_conversation=browser_history,
                         db_workouts=db_workouts, client_workout_context=[{"id": "client"}])
    assert snap.legacy_prompt_projection(conversation_limit=60).prompt_variables() == \
        _legacy_variables(db_profile, db_workouts, db_history, 60)


@pytest.mark.parametrize("limit", [12, 10, 60])
def test_legacy_projection_preserves_free_core_pro_history_limits(limit):
    history = [{"role": "user", "content": str(i)} for i in range(65)]
    snap = build_context(intent="question", subject=_account(), request_time=_NOW,
                         db_profile=_profile(), db_conversation=history)
    assert snap.legacy_prompt_projection(conversation_limit=limit).prompt_variables()["history"] == history[-limit:]


def test_legacy_projection_preserves_sparse_profile_and_legacy_omissions():
    profile = {"goal": "strength"}
    snap = build_context(intent="workout", subject=_account(), request_time=_NOW, db_profile=profile)
    projected = snap.legacy_prompt_projection(conversation_limit=60).prompt_variables()
    assert projected == _legacy_variables(profile, [], [], 60)
    assert {"missing:equipment", "missing:level"}.issubset(set(snap.omissions))


@pytest.mark.parametrize("intent", ["question", "workout", "nutrition"])
def test_legacy_projection_golden_equivalence_for_representative_requests(intent):
    profile = _profile(goal="strength", workoutContext="existing memory")
    workouts = [{"id": "w1", "type": "upper"}]
    history = [{"role": "user", "content": "one"}, {"role": "assistant", "content": "two"}]
    snap = build_context(intent=intent, subject=_account(), request_time=_NOW,
                         db_profile=profile, db_workouts=workouts, db_conversation=history)
    assert snap.legacy_prompt_projection(conversation_limit=60).prompt_variables() == \
        _legacy_variables(profile, workouts, history, 60)


def test_legacy_adapter_does_not_change_canonical_snapshot_semantics():
    chronological = [{"id": "z", "content": "last"}, {"id": "a", "content": "first"}]
    snap = build_context(intent="question", subject=_account(), request_time=_NOW,
                         db_profile=_profile(), db_conversation=chronological)
    canonical = snap.semantic_payload()
    assert "legacy_prompt_data" not in canonical
    assert [m["id"] for m in canonical["conversation"]] == ["a", "z"]
    assert [m["id"] for m in snap.legacy_prompt_projection(conversation_limit=60).prompt_variables()["history"]] == ["z", "a"]


# Phase A2: /chat uses the established legacy adapter. These tests prove the
# builder is called once while the prompt variables and OpenAI message sequence
# remain byte-for-byte equivalent to the previous assembly.
def _legacy_messages(profile, workouts, history, message, cap):
    import personality
    personality_block = personality.compose(lang="en", profile=profile, workouts=workouts,
                                            message=message, conversation=history)
    profile_block = appmod._build_profile_block(profile, "en")
    base = (profile_block + "\n\n" + appmod.SYSTEM_INSTRUCTIONS) if profile_block else appmod.SYSTEM_INSTRUCTIONS
    system = (personality_block + "\n\n" + base) if personality_block else base
    messages = [{"role": "system", "content": system}]
    for turn in history[-cap:]:
        if isinstance(turn, dict) and turn.get("role") in ("user", "assistant"):
            messages.append({"role": turn["role"], "content": str(turn.get("content", ""))[:4000]})
    messages.append({"role": "user", "content": message})
    return messages


def _login_for_chat(client, profile, plan="free"):
    uid = store.get_or_create_user(f"{plan}-context@example.com")
    store.save_profile(uid, profile)
    if plan != "free":
        store.upsert_subscription(uid, plan, _NOW + timedelta(days=30), status="active")
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(uid))
    return uid


def test_chat_calls_context_builder_once_for_normal_request(client, captured, monkeypatch):
    original = appmod.context_builder.build_context
    calls = []

    def wrapped(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(appmod.context_builder, "build_context", wrapped)
    response = _post(client, "hello", profile=_profile())
    assert response.status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize("label,profile,history,message", [
    ("anonymous_general", _profile(), [{"role": "user", "content": "prior"}], "hello"),
    ("workout", _profile(workoutContext="existing workout memory"), [], "build a workout"),
    ("nutrition", _profile(foodPreferences=["vegan"]), [{"role": "assistant", "content": "prior"}], "build nutrition"),
    ("sparse", {"goal": "strength"}, [], "hello"),
    ("full", {**_profile(), "name": "Ava", "allergies": "peanuts", "healthNotes": "knee pain",
              "assessmentResults": {"pushups": {"count": 10}}}, [], "hello"),
    ("no_conversation", _profile(), [], "hello"),
])
def test_chat_context_builder_preserves_anonymous_legacy_messages(client, captured, label, profile, history, message):
    expected = _legacy_messages(profile, [], history, message, 12)
    response = client.post("/chat", json={"message": message, "lang": "en",
                                           "profile": profile, "history": history})
    assert response.status_code == 200, label
    assert captured["messages"] == expected


@pytest.mark.parametrize("plan,cap", [("free", 12), ("core", 10), ("pro", 60)])
def test_chat_context_builder_preserves_authenticated_prompt_and_history_limit(client, captured, plan, cap):
    db_profile = {**_profile(), "name": "DB User"}
    uid = _login_for_chat(client, db_profile, plan)
    for i in range(65):
        store.add_conversation(uid, "user" if i % 2 == 0 else "assistant", f"db-{i}", "en")
    for i in range(2):
        store.log_workout(uid, {"type": f"session-{i}", "exercises": [], "diff": "medium", "completion": 100})

    legacy_profile = store.get_profile(uid)
    memory = store.build_memory_context(uid, en=True)
    if memory:
        legacy_profile = dict(legacy_profile)
        legacy_profile["workoutContext"] = memory
    legacy_workouts = store.list_workouts(uid, limit=40)
    legacy_history = store.list_conversation(uid, limit=cap)
    message = "show my context"
    expected = _legacy_messages(legacy_profile, legacy_workouts, legacy_history, message, cap)

    response = client.post("/chat", json={"message": message, "lang": "en",
                                           "profile": _profile(goal="fat_loss"),
                                           "history": [{"role": "user", "content": "browser"}]})
    assert response.status_code == 200
    assert captured["messages"] == expected
    assert [m["content"] for m in captured["messages"][1:-1]] == [m["content"] for m in legacy_history]


def test_chat_context_builder_keeps_personality_and_profile_inputs_raw(client, captured, monkeypatch):
    import personality
    seen = {}
    original_compose = personality.compose
    original_profile_block = appmod._build_profile_block

    def compose(**kwargs):
        seen["personality"] = kwargs
        return original_compose(**kwargs)

    def profile_block(profile, lang):
        seen["profile"] = profile
        return original_profile_block(profile, lang)

    monkeypatch.setattr(personality, "compose", compose)
    monkeypatch.setattr(appmod, "_build_profile_block", profile_block)
    profile = {**_profile(), "foodPreferences": ["vegan"], "allergies": "peanuts"}
    history = [{"role": "user", "content": "prior"}]
    response = client.post("/chat", json={"message": "hello", "lang": "en",
                                           "profile": profile, "history": history})
    assert response.status_code == 200
    assert seen["personality"]["profile"] == profile
    assert seen["personality"]["workouts"] == []
    assert seen["personality"]["conversation"] == history
    assert seen["profile"] == profile


def test_first_contact_uses_one_authoritative_context_snapshot(client, monkeypatch):
    calls = []
    original = appmod.context_builder.build_context

    def wrapped(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(appmod.context_builder, "build_context", wrapped)
    client.post("/chat", json={"message": "hello", "lang": "en", "first_contact": True})
    assert len(calls) == 1


# Phase B1: the decision engine is shadow-only. It is computed beside the
# snapshot, but does not change messages, events, persistence, or rendering.
@pytest.mark.parametrize("message,intent,outcome", [
    ("build a workout", "workout", "recommend"),
    ("plan my nutrition", "nutrition", "recommend"),
    ("I need recovery today", "recovery", "recover"),
    ("", "unknown", "clarify"),
    ("hello", "general_conversation", "converse"),
    ("I have chest pain", "medical", "route"),
])
def test_shadow_decision_is_deterministic(message, intent, outcome):
    snapshot = build_context(intent=intent, subject=Subject("anonymous_device", "phase-b1", False),
                             request_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert decision_engine.classify_intent(message) == intent
    assert decision_engine.decide(snapshot, intent) == decision_engine.decide(snapshot, intent)
    assert decision_engine.decide(snapshot, intent).outcome == outcome


def test_chat_computes_one_shadow_decision_without_changing_stream_or_prompt(client, captured, monkeypatch):
    decisions = []
    original = decision_engine.decide

    def wrapped(snapshot, intent):
        result = original(snapshot, intent)
        decisions.append(result)
        return result

    monkeypatch.setattr(appmod.decision_engine, "decide", wrapped)
    profile = _profile()
    history = [{"role": "user", "content": "prior"}]
    expected = _legacy_messages(profile, [], history, "build a workout", 12)
    response = client.post("/chat", json={"message": "build a workout", "lang": "en",
                                           "profile": profile, "history": history})

    assert response.status_code == 200
    assert len(decisions) == 1
    assert decisions[0].outcome == "recommend"
    assert captured["messages"] == expected
    events = _events(response)
    assert not any("shadow_decision" in event or "decision" in event for event in events)
    assert any(event.get("t") == "ok" for event in events)
    assert any(event.get("done") for event in events)


def test_shadow_decision_does_not_add_memory_writes(client, captured, monkeypatch):
    uid = _login_for_chat(client, _profile())
    decisions = []
    original = decision_engine.decide

    def wrapped(snapshot, intent):
        result = original(snapshot, intent)
        decisions.append(result)
        return result

    monkeypatch.setattr(appmod.decision_engine, "decide", wrapped)
    response = _post(client, "hello")
    response.get_data()

    saved = store.list_conversation(uid, limit=10)
    assert len(decisions) == 1
    assert [(turn["role"], turn["content"]) for turn in saved] == [("user", "hello"), ("assistant", "ok")]


@pytest.mark.parametrize("message,expected_kind", [
    ("build a workout", "workout"),
    ("plan my nutrition", "nutrition"),
    ("I need recovery today", None),
    ("I have chest pain", None),
    ("???", None),
    ("hello", None),
])
def test_shadow_recommendation_runs_only_for_recommend_decisions(client, captured, monkeypatch,
                                                                  message, expected_kind):
    calls = []

    def design(kind, *, decision, profile, preferences, subject, record):
        calls.append({"kind": kind, "decision": decision, "profile": profile,
                      "preferences": preferences, "subject": subject, "record": record})
        return types.SimpleNamespace(kind=kind)

    monkeypatch.setattr(appmod.recommendation_architect, "design", design)
    response = _post(client, message, profile=_profile())

    assert response.status_code == 200
    if expected_kind is None:
        assert calls == []
    else:
        assert len(calls) == 1
        assert calls[0]["kind"] == expected_kind
        assert calls[0]["decision"].outcome == "recommend"
        assert calls[0]["profile"] == _profile()
        assert calls[0]["preferences"] == {}
        assert calls[0]["record"] is False
    events = _events(response)
    assert not any("blueprint" in event or "recommendation" in event for event in events)


def test_shadow_recommendation_keeps_blueprint_local_and_does_not_record_history(monkeypatch):
    writes = []
    monkeypatch.setattr(recommendation_diversity.store, "log_recommendation",
                        lambda *args: writes.append(args))
    snapshot = build_context(
        intent="workout",
        subject=Subject("anonymous_device", "recommendation-shadow", False),
        request_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        browser_profile=_profile(),
    )
    decision = decision_engine.decide(snapshot, "workout")

    blueprint = appmod._shadow_recommendation(snapshot, decision, _profile())

    assert blueprint.kind == "workout"
    with pytest.raises(FrozenInstanceError):
        blueprint.kind = "nutrition"
    assert writes == []


def test_shadow_recommendation_does_not_change_chat_persistence(client, captured):
    uid = _login_for_chat(client, _profile())
    response = _post(client, "build a workout")
    response.get_data()

    saved = store.list_conversation(uid, limit=10)
    assert [(turn["role"], turn["content"]) for turn in saved] == [
        ("user", "build a workout"), ("assistant", "ok"),
    ]


def _workout_blueprint():
    return WorkoutBlueprint(
        goal="strength", difficulty="moderate", mobility_requirement="standard",
        joint_impact="moderate", balance_demand="low", equipment=["dumbbells"],
        session_minutes=35, exercise_families=["squat", "hinge"], contraindications=[],
        rotation_anchor="lower_body", meal_diversity=[], explanations=[])


def _nutrition_blueprint():
    return NutritionBlueprint(
        meal="breakfast", protein_g=45, carbs_g=50, fat_g=15, fiber_g=8,
        max_prep_minutes=15, budget="moderate", preferred_foods=["eggs"],
        avoided_foods=["oats"], rotation_anchor="eggs", meal_diversity=[],
        difficulty="easy", required_equipment=["stove"], seasonality="summer",
        medical_constraints=[], explanations=[])


def test_active_recommendation_engine_delivers_only_verified_workout_blueprint(client, captured, monkeypatch):
    message, blueprint, expected_title = "build a workout", _workout_blueprint(), "**Workout**"
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    _set_stream(monkeypatch, captured, json.dumps({
        "blueprint": to_dict(blueprint), "explanations": []
    }))

    response = _post(client, message, profile=_profile())
    events = _events(response)

    assert captured["system"] == appmod.recommendation_renderer.render_prompt(blueprint)
    assert "BLUEPRINT (render exactly, do not alter values)" in captured["system"]
    assert appmod.SYSTEM_INSTRUCTIONS not in captured["system"]
    assert len(events) == 2 and events[1] == {"done": True}
    assert events[0]["t"].startswith(expected_title)
    assert '"blueprint"' not in events[0]["t"]


def test_training_engine_active_delivers_only_deterministic_training_plan(client, captured, monkeypatch):
    profile = {"goal": "strength", "level": "intermediate",
               "equipment": "bodyweight, dumbbells, bench", "recoveryFeel": "fresh"}
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    _set_stream(monkeypatch, captured, json.dumps({"explanations": ["Keep every rep controlled."]}))

    response = _post(client, "build a workout", profile=profile)
    events = _events(response)

    assert captured["system"].startswith("[FIXED TRAINING PLAN]")
    assert appmod.SYSTEM_INSTRUCTIONS not in captured["system"]
    assert len(events) == 3 and events[-1] == {"done": True}
    assert events[1]["training_completion"]["plan_id"]
    assert "Goblet Squat" in events[0]["t"]
    assert "RPE" in events[0]["t"] and "tempo" in events[0]["t"]
    assert "Keep every rep controlled." in events[0]["t"]


def test_training_engine_active_fails_closed_without_legacy_workout_generation(client, captured, monkeypatch):
    profile = {"goal": "strength", "level": "intermediate", "equipment": "office"}
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_kwargs: pytest.fail("LLM ran"))

    response = _post(client, "build a workout", profile=profile)

    assert response.status_code == 200
    assert _events(response)[-1] == {"done": True}
    assert captured == {}


def test_training_engine_active_is_deterministic_and_keeps_traceability_internal(client, captured, monkeypatch):
    profile = {"goal": "strength", "level": "intermediate",
               "equipment": "bodyweight, dumbbells, bench", "recoveryFeel": "fresh"}
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    _set_stream(monkeypatch, captured, json.dumps({"explanations": []}))

    first = _events(_post(client, "build a workout", profile=profile))
    second = _events(_post(client, "build a workout", profile=profile))

    assert first == second
    snapshot = _shadow_snapshot(intent="workout", profile=profile)
    plan = appmod._active_training_plan(
        snapshot, appmod._RECOMMENDATION_PLANNER.plan("workout", appmod.recommendation_planning.ImmutableUserProfile.from_verified_facts(profile)))
    assert all(item.exercise_id and item.exercise_version and item.selection_policy_version
               and item.prescription_policy_version
               for item in plan.sessions[0].prescriptions)


def test_training_engine_active_preserves_verified_upper_lower_split_through_chat(client, captured, monkeypatch):
    profile = {"goal": "strength", "level": "intermediate", "equipment": "gym",
               "training_split": "upper_lower", "recoveryFeel": "fresh"}
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    _set_stream(monkeypatch, captured, json.dumps({"explanations": []}))

    events = _events(_post(client, "build a workout", profile=profile))
    snapshot = _shadow_snapshot(intent="workout", profile=profile)
    planning = appmod._RECOMMENDATION_PLANNER.plan(
        "workout", appmod.recommendation_planning.ImmutableUserProfile.from_verified_facts(profile))
    plan = appmod._active_training_plan(snapshot, planning)

    assert planning.training_split == "upper_lower"
    assert plan.training_split.value == "upper_lower"
    assert [len(session.prescriptions) for session in plan.sessions] == [3, 4]
    assert "**Session 1" in events[0]["t"] and "**Session 2" in events[0]["t"]
    assert captured["system"].startswith("[FIXED TRAINING PLAN]")


def test_active_recommendation_engine_keeps_nutrition_on_the_legacy_path(client, captured, monkeypatch):
    profile = _profile()
    expected = _legacy_messages(profile, [], [], "plan my nutrition", 12)
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: pytest.fail("design ran"))

    response = _post(client, "plan my nutrition", profile=profile)

    assert captured["messages"] == expected
    assert _events(response) == [{"t": "ok"}, {"done": True}]


def _persona_expert_blueprint(profile):
    snapshot = _shadow_snapshot(profile=profile)
    decision = decision_engine.decide(snapshot, "workout")
    match = persona_matcher.match(snapshot, "workout")
    consensus = expert_consensus.evaluate(snapshot, match, "workout")
    blueprint = appmod.recommendation_architect.design(
        "workout", decision=decision, profile=profile, preferences={}, subject="persona-expert-test",
        record=False, expert_consensus=consensus,
        persona_adaptation=appmod._persona_adaptation(match))
    return blueprint, match, consensus


def _authority_blueprint(*, profile=None, locked=None, explicit=None, adaptation=None, consensus=None):
    snapshot = _shadow_snapshot(profile=profile or {}, locked=locked, explicit=explicit)
    decision = decision_engine.decide(snapshot, "workout")
    authority = appmod._workout_authority(snapshot, decision)
    assert authority is not None
    return appmod.recommendation_architect.design(
        "workout", decision=decision, profile={}, preferences={}, subject="authority-test", record=False,
        authority=authority, persona_adaptation=adaptation or {}, expert_consensus=consensus), authority


def test_workout_authority_locked_equipment_and_exclusions_override_lower_layers():
    blueprint, authority = _authority_blueprint(
        profile={"goal": "strength", "equipment": "gym"},
        locked=LockedPreferences(equipment=("home",), exercise_exclusions=("squat",)),
        adaptation={"advanced": True},
    )
    assert authority.equipment == ("home",)
    assert blueprint.equipment == ["home"]
    assert "squat" not in blueprint.exercise_families


def test_workout_authority_explicit_facts_and_safety_override_persona_and_expert():
    stale_consensus = types.SimpleNamespace(applicable_rule_ids=("GRV-001", "GRV-003", "WNK-003"))
    beginner, _ = _authority_blueprint(
        profile={"goal": "strength"}, explicit={"level": "beginner"},
        adaptation={"advanced": True}, consensus=stale_consensus)
    fresh, _ = _authority_blueprint(
        profile={"goal": "strength", "sleepQuality": "poor", "stressLevel": "high"},
        explicit={"recoveryFeel": "fresh"}, consensus=stale_consensus)
    injury, _ = _authority_blueprint(profile={"injuries": "knee pain"})
    assert beginner.difficulty == "beginner"
    assert fresh.session_minutes == 35 and fresh.mobility_requirement == "standard"
    assert not ({"squat", "hinge", "conditioning"} & set(injury.exercise_families))


def test_workout_authority_conflict_fails_closed_to_legacy():
    snapshot = _shadow_snapshot(profile={"goal": "strength"},
                                locked=LockedPreferences(equipment=("home", "gym")))
    decision = decision_engine.decide(snapshot, "workout")
    assert appmod._workout_authority(snapshot, decision) is None


def test_active_authority_conflict_falls_back_to_legacy_prompt(client, captured, monkeypatch):
    profile = {"goal": "strength", "equipment": "gym", "level": "intermediate",
               "lockedEquipment": ["home", "gym"]}
    expected = _legacy_messages(profile, [], [], "build a workout", 12)
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: pytest.fail("design ran"))
    response = _post(client, "build a workout", profile=profile)
    assert _events(response) == [{"t": "ok"}, {"done": True}]
    assert captured["messages"] == expected


def test_recommendation_flag_is_resolved_once_per_normal_request(client, captured, monkeypatch):
    calls = []
    original = appmod.os.getenv

    def getenv(name, default=None):
        if name == "RECOMMENDATION_ENGINE_ACTIVE":
            calls.append(name)
        return original(name, default)

    monkeypatch.setattr(appmod.os, "getenv", getenv)
    _post(client, "build a workout", profile=_profile())
    assert calls == ["RECOMMENDATION_ENGINE_ACTIVE"]


def test_spoken_workout_uses_the_same_single_active_chat_path(client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    calls = []
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design",
                        lambda *args, **kwargs: calls.append((args, kwargs)) or blueprint)
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))
    response = client.post("/chat", json={"message": "build a workout", "lang": "en",
                                           "profile": _profile(), "voice": True})
    assert response.status_code == 200
    assert len(calls) == 1
    assert _events(response)[-1] == {"done": True}


def test_persona_expert_workout_blueprint_is_deterministic_and_changes_structure():
    beginner, _, _ = _persona_expert_blueprint(_profile(level="beginner", equipment="gym"))
    advanced, _, _ = _persona_expert_blueprint({"goal": "strength", "level": "advanced"})

    repeat, _, _ = _persona_expert_blueprint(_profile(level="beginner", equipment="gym"))
    assert beginner == repeat
    assert beginner.difficulty == "beginner"
    assert advanced.difficulty == "advanced"
    assert beginner.session_minutes < advanced.session_minutes


def test_persona_expert_adapts_equipment_recovery_and_injury_constraints():
    home, _, _ = _persona_expert_blueprint(_profile(equipment="home", level="intermediate",
                                                    sleepQuality="good", stressLevel="low", recoveryFeel="fresh"))
    gym, _, _ = _persona_expert_blueprint(_profile(equipment="gym", level="intermediate",
                                                   sleepQuality="good", stressLevel="low", recoveryFeel="fresh"))
    recovering, _, recovery_consensus = _persona_expert_blueprint(_profile(level="intermediate"))
    fresh, _, _ = _persona_expert_blueprint({"goal": "strength", "level": "advanced"})
    injury, injury_match, injury_consensus = _persona_expert_blueprint({"injuries": "knee pain"})

    assert home.exercise_families != gym.exercise_families
    assert recovering.session_minutes < fresh.session_minutes
    assert recovery_consensus.abstained is False
    assert injury_match.abstained is True and injury_consensus.abstained is False
    assert injury.joint_impact == "low"
    assert "painful range" in injury.contraindications
    assert not ({"squat", "hinge", "conditioning"} & set(injury.exercise_families))


def _capture_shadow_traces(monkeypatch):
    traces = []
    monkeypatch.setattr(appmod, "_observe_shadow_trace_for_testing", traces.append)
    return traces


def test_active_persona_expert_path_uses_blueprint_without_changing_sse_or_persistence(
        client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    uid = _login_for_chat(client, _profile(level="beginner"))
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))
    traces = _capture_shadow_traces(monkeypatch)

    response = _post(client, "build a workout")

    assert _events(response) == [{"t": appmod.recommendation_renderer.render_delivery(blueprint, [], "en")},
                                 {"done": True}]
    assert captured["system"] == appmod.recommendation_renderer.render_prompt(blueprint)
    assert len(traces) == 1 and traces[0].production_path_used == "persona_expert"
    assert traces[0].blueprint_invoked is True
    saved = store.list_conversation(uid, limit=10)
    assert [(turn["role"], turn["content"]) for turn in saved] == [
        ("user", "build a workout"), ("assistant", _events(response)[0]["t"]),
    ]


def test_active_persona_expert_abstention_falls_back_to_byte_identical_legacy_workout(client, captured, monkeypatch):
    # Complete for recommendation planning, but intentionally too nonspecific
    # for persona/expert evidence: the active path must fail closed to legacy.
    profile = {"goal": "strength", "equipment": "office", "level": "unknown"}
    expected = _legacy_messages(profile, [], [], "build a workout", 12)
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    traces = _capture_shadow_traces(monkeypatch)
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: pytest.fail("design ran"))

    response = _post(client, "build a workout", profile=profile)

    assert captured["messages"] == expected
    assert _events(response) == [{"t": "ok"}, {"done": True}]
    assert len(traces) == 1 and traces[0].production_path_used == "legacy"
    assert traces[0].blueprint_invoked is False


def test_active_recommendation_flag_does_not_change_voice_session_start(client, captured, monkeypatch):
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: pytest.fail("design ran"))

    response = client.post("/chat", json={"session_start": True, "lang": "en", "profile": _profile()})

    events = _events(response)
    assert events[0] == {"t": "What would you like help with today?"}
    assert events[-1]["done"] is True
    assert captured == {}


def test_active_recommendation_engine_rejects_modified_blueprint(client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    modified = to_dict(blueprint)
    modified["session_minutes"] = 99
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    _set_stream(monkeypatch, captured, json.dumps({
        "blueprint": modified, "explanations": []
    }))

    response = _post(client, "build a workout", profile=_profile())

    assert _events(response) == [
        {"t": "I couldn't safely deliver that recommendation. Please try again."}, {"done": True}
    ]
    assert blueprint.session_minutes == 35


def test_recommendation_engine_flag_off_keeps_legacy_workout_prompt(client, captured, monkeypatch):
    profile = _profile()
    history = [{"role": "user", "content": "prior"}]
    expected = _legacy_messages(profile, [], history, "build a workout", 12)
    response = client.post("/chat", json={"message": "build a workout", "lang": "en",
                                           "profile": profile, "history": history})

    assert response.status_code == 200
    assert captured["messages"] == expected
    assert "BLUEPRINT (render exactly, do not alter values)" not in captured["system"]


@pytest.mark.parametrize("message", ["hello", "I need recovery today", "I have chest pain", "???"])
def test_active_recommendation_engine_does_not_run_for_non_recommend_outcomes(client, captured, monkeypatch,
                                                                                message):
    calls = []
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: calls.append(args))

    response = _post(client, message, profile=_profile())

    assert response.status_code == 200
    assert calls == []
    if "messages" in captured:
        assert "BLUEPRINT (render exactly, do not alter values)" not in captured["system"]


# Persona and expert assets are observational only. These tests exercise their
# pure contracts and prove their shadow invocation cannot influence /chat.
def _shadow_snapshot(*, intent="workout", profile=None, locked=None, explicit=None, history=None):
    return build_context(
        intent=intent,
        subject=_device("persona-shadow"),
        request_time=_NOW,
        browser_profile=profile if profile is not None else _profile(),
        locked_preferences=locked,
        explicit_facts=explicit,
        recommendation_history=history,
    )


def test_persona_matcher_is_deterministic_for_beginner_and_advanced_contexts():
    beginner = _shadow_snapshot(profile=_profile(level="beginner", goal="strength"))
    advanced = _shadow_snapshot(profile={"level": "advanced", "goal": "strength"})

    beginner_result = persona_matcher.match(beginner, "workout")
    assert beginner_result == persona_matcher.match(beginner, "workout")
    assert beginner_result.primary_persona_id == "P-067"
    assert beginner_result.abstained is False

    advanced_result = persona_matcher.match(advanced, "workout")
    assert advanced_result.abstained is False
    assert advanced_result.primary_persona_id is not None
    assert "athletes_advanced" in next(persona.cluster for persona in load_runtime_personas()
                                        if persona.id == advanced_result.primary_persona_id)


@pytest.mark.parametrize("profile,locked,expected_abstention", [
    ({"injuries": "knee pain"}, None, True),
    (_profile(equipment="home"), None, False),
    ({"age": 69}, None, True),
    ({}, LockedPreferences(dietary=("vegetarian",), allergies=("peanuts",)), True),
    ({}, None, True),
    ({"sleepQuality": "poor", "stressLevel": "high", "recoveryFeel": "tired"}, None, False),
])
def test_persona_matcher_handles_injury_home_older_locked_budget_and_recovery(profile, locked, expected_abstention):
    explicit = {"budget": "low"} if profile == {} and locked is None else None
    result = persona_matcher.match(_shadow_snapshot(profile=profile, locked=locked, explicit=explicit), "workout")
    assert result.abstained is expected_abstention
    if locked:
        assert "locked:allergies" in result.evidence_refs


def test_persona_matcher_abstains_after_a_long_break_without_source_backed_similarity():
    snapshot = _shadow_snapshot(profile={}, history=[{"date": "2024-01-01", "kind": "workout"}])
    result = persona_matcher.match(snapshot, "workout")
    assert result.abstained is True
    assert result.primary_persona_id is None


def test_explicit_facts_and_locked_preferences_never_be_overridden_by_persona_matching():
    snapshot = _shadow_snapshot(profile=_profile(level="beginner"),
                                locked=LockedPreferences(dietary=("vegan",), allergies=("soy",)),
                                explicit={"level": "advanced"})
    result = persona_matcher.match(snapshot, "workout")
    assert result.primary_persona_id != "P-067"
    assert "locked:dietary" in result.evidence_refs
    assert "locked:allergies" in result.evidence_refs


def test_locked_preferences_remain_authoritative_during_nutrition_consensus():
    locked = LockedPreferences(dietary=("vegan",), allergies=("soy",))
    snapshot = _shadow_snapshot(intent="nutrition", profile={"goal": "fat_loss"}, locked=locked)
    result = expert_consensus.evaluate(snapshot, persona_matcher.match(snapshot, "nutrition"), "nutrition")
    assert snapshot.locked_preferences == locked
    assert result.applicable_rule_ids == ()
    assert result.abstained is True


def test_expert_consensus_uses_only_ready_rules_and_never_activates_unresolved_rules():
    snapshot = _shadow_snapshot(profile=_profile(level="beginner", injuries="knee pain", stressLevel="high"))
    match = persona_matcher.match(snapshot, "workout")
    result = expert_consensus.evaluate(snapshot, match, "workout")
    packs = load_expert_rule_packs()
    unresolved = {rule.rule_id for pack in packs for rule in pack.rules if not rule.runtime_ready}

    assert set(result.unresolved_rule_ids) == unresolved
    assert not (set(result.applicable_rule_ids) & unresolved)
    assert "MCG-001" in result.applicable_rule_ids


def test_expert_consensus_conflicts_and_safety_are_resolved_deterministically():
    snapshot = _shadow_snapshot(profile=_profile(level="beginner", injuries="knee pain"))
    match = persona_matcher.match(snapshot, "workout")
    packs = list(load_expert_rule_packs())
    mcg = packs[2].rules[0]
    winkelman = replace(packs[6].rules[0], conflict_group=mcg.conflict_group)
    packs[6] = ExpertRulePack(packs[6].lineage, packs[6].version, (winkelman, *packs[6].rules[1:]))
    conflict = expert_consensus.evaluate(snapshot, match, "workout", packs=tuple(packs))
    assert mcg.rule_id in conflict.applicable_rule_ids
    assert winkelman.rule_id in conflict.rejected_rule_ids
    assert mcg.conflict_group in conflict.conflict_groups

    safety = _shadow_snapshot(profile=_profile(), explicit={"red_flag": True})
    blocked = expert_consensus.evaluate(safety, persona_matcher.match(safety, "workout"), "workout")
    assert blocked.abstained is True
    assert blocked.applicable_rule_ids == ()


def test_persona_and_expert_shadow_flags_preserve_prompt_sse_and_persistence(client, captured, monkeypatch):
    profile = _profile(level="beginner")
    expected = _legacy_messages(profile, [], [], "build a workout", 12)
    matcher_calls, consensus_calls = [], []
    original_match = appmod.persona_matcher.match
    original_consensus = appmod.expert_consensus.evaluate
    monkeypatch.setenv("PERSONA_MATCHER_SHADOW", "true")
    monkeypatch.setenv("EXPERT_CONSENSUS_SHADOW", "true")
    monkeypatch.setattr(appmod.persona_matcher, "match", lambda *args, **kwargs:
                        (matcher_calls.append(args), original_match(*args, **kwargs))[1])
    monkeypatch.setattr(appmod.expert_consensus, "evaluate", lambda *args, **kwargs:
                        (consensus_calls.append(args), original_consensus(*args, **kwargs))[1])

    response = _post(client, "build a workout", profile=profile)
    assert len(matcher_calls) == len(consensus_calls) == 1
    assert captured["messages"] == expected
    assert _events(response) == [{"t": "ok"}, {"done": True}]


def test_persona_and_expert_shadow_do_not_add_persistence_writes(client, captured, monkeypatch):
    profile = _profile(level="beginner")
    uid = _login_for_chat(client, profile)
    monkeypatch.setenv("PERSONA_MATCHER_SHADOW", "true")
    monkeypatch.setenv("EXPERT_CONSENSUS_SHADOW", "true")

    response = _post(client, "build a workout")
    response.get_data()

    saved = store.list_conversation(uid, limit=10)
    assert [(turn["role"], turn["content"]) for turn in saved] == [
        ("user", "build a workout"), ("assistant", "ok"),
    ]


@pytest.mark.parametrize("message", ["hello", "I need recovery today", "I have chest pain", "???"])
def test_persona_and_expert_shadow_do_not_run_for_non_recommend_outcomes(client, monkeypatch, message):
    monkeypatch.setenv("PERSONA_MATCHER_SHADOW", "true")
    monkeypatch.setenv("EXPERT_CONSENSUS_SHADOW", "true")
    monkeypatch.setattr(appmod.persona_matcher, "match", lambda *args, **kwargs: pytest.fail("matcher ran"))
    monkeypatch.setattr(appmod.expert_consensus, "evaluate", lambda *args, **kwargs: pytest.fail("consensus ran"))
    assert _post(client, message, profile=_profile()).status_code == 200


def test_shadow_flags_off_do_not_invoke_new_modules(client, captured, monkeypatch):
    monkeypatch.setattr(appmod.persona_matcher, "match", lambda *args, **kwargs: pytest.fail("matcher ran"))
    monkeypatch.setattr(appmod.expert_consensus, "evaluate", lambda *args, **kwargs: pytest.fail("consensus ran"))
    response = _post(client, "build a workout", profile=_profile())
    assert response.status_code == 200
    assert "BLUEPRINT (render exactly, do not alter values)" not in captured["system"]


@pytest.mark.parametrize("matcher_enabled,consensus_enabled,expected", [
    (True, False, (True, False)),
    (False, True, (False, True)),
    (True, True, (True, True)),
])
def test_shadow_flag_modes_keep_results_local(monkeypatch, matcher_enabled, consensus_enabled, expected):
    snapshot = _shadow_snapshot(profile={"level": "beginner", "goal": "strength"})
    decision = decision_engine.decide(snapshot, "workout")
    monkeypatch.setenv("PERSONA_MATCHER_SHADOW", str(matcher_enabled).lower())
    monkeypatch.setenv("EXPERT_CONSENSUS_SHADOW", str(consensus_enabled).lower())

    match, consensus, trace = appmod._shadow_persona_expert(snapshot, decision, False)

    assert (match is not None, consensus is not None) == expected
    assert trace is not None


# Phase B2: clarify and route are fixed delivery contracts. They bypass OpenAI
# while retaining the normal SSE and delivered-response persistence contract.
@pytest.mark.parametrize("message,expected", [
    ("???", "What would you like help with today?"),
    ("I have chest pain", "I can't assess urgent medical symptoms here. Please contact a qualified medical professional, or local emergency services if this feels urgent."),
])
def test_controlled_outcomes_bypass_openai_and_stream_only_safe_reply(client, captured, message, expected):
    response = _post(client, message)
    events = _events(response)

    assert "messages" not in captured
    assert events == [{"t": expected}, {"done": True}]
    reply = events[0]["t"].lower()
    assert "sets" not in reply and "reps" not in reply and "calories" not in reply


@pytest.mark.parametrize("message", [
    "build a workout", "plan my nutrition", "I need recovery today",
    "show my progress", "how much water should I drink?", "hello",
])
def test_b2_legacy_outcomes_preserve_openai_messages(client, captured, message):
    profile = _profile()
    history = [{"role": "user", "content": "prior"}]
    expected = _legacy_messages(profile, [], history, message, 12)
    response = client.post("/chat", json={"message": message, "lang": "en",
                                           "profile": profile, "history": history})

    assert response.status_code == 200
    assert captured["messages"] == expected
    events = _events(response)
    assert any(event.get("t") == "ok" for event in events)
    assert any(event.get("done") for event in events)


def test_controlled_route_persists_only_delivered_response(client, captured):
    uid = _login_for_chat(client, _profile())
    response = _post(client, "I have chest pain")
    events = _events(response)

    assert "messages" not in captured
    saved = store.list_conversation(uid, limit=10)
    assert [(turn["role"], turn["content"]) for turn in saved] == [
        ("user", "I have chest pain"), ("assistant", events[0]["t"]),
    ]


def test_voice_request_gets_one_separate_speech_projection_without_changing_persistence(client, captured, monkeypatch):
    uid = _login_for_chat(client, _profile())
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")

    response = _post(client, "hello", voice=True)
    events = _events(response)

    assert events == [{"t": "ok"}, {"speech_text": "ok"}, {"done": True}]
    saved = store.list_conversation(uid, limit=10)
    assert [(turn["role"], turn["content"]) for turn in saved] == [
        ("user", "hello"), ("assistant", "ok"),
    ]


def test_voice_medical_route_projects_the_complete_safety_reply_without_openai(client, captured, monkeypatch):
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")

    response = _post(client, "I have chest pain", voice=True)
    events = _events(response)

    assert "messages" not in captured
    assert events[1] == {"speech_text": events[0]["t"]}
    assert events[-1] == {"done": True}


def test_voice_workout_and_nutrition_keep_visible_delivery_separate_from_speech(client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))

    workout_events = _events(_post(client, "build a workout", profile=_profile(), voice=True))
    workout_visible = workout_events[0]["t"]
    workout_speech = workout_events[1]["speech_text"]
    assert "**" in workout_visible
    assert workout_speech == "Your workout is ready. The full plan is visible on screen."
    assert "**" not in workout_speech and "sets" not in workout_speech.lower()

    monkeypatch.delenv("RECOMMENDATION_ENGINE_ACTIVE", raising=False)
    monkeypatch.setattr(appmod, "_build_profile_block",
                        lambda profile, lang: "Calorie target: 2800 kcal\nProtein target: minimum 175g/day")
    _set_stream(monkeypatch, captured, _structured_plan_payload())
    nutrition_events = _events(_post(client, "Give me a full-day nutrition plan", profile=_profile(), voice=True))
    nutrition_visible = nutrition_events[0]["t"]
    nutrition_speech = nutrition_events[1]["speech_text"]
    assert "|" in nutrition_visible
    assert nutrition_speech == "Your complete daily nutrition plan is ready. The meals and exact values are visible on screen."
    assert "|" not in nutrition_speech and "kcal" not in nutrition_speech.lower()


def test_voice_stop_has_no_speech_projection_and_composer_off_uses_visible_fallback(client, captured, monkeypatch):
    stop_events = _events(_post(client, "Stop.", voice=True))
    assert stop_events == [{"done": True}]

    monkeypatch.delenv("CONVERSATION_COMPOSER_ACTIVE", raising=False)
    events = _events(_post(client, "hello", voice=True))
    assert events == [{"t": "ok"}, {"done": True}]


def test_first_contact_computes_one_observational_decision(client, monkeypatch):
    calls = []
    original = appmod.decision_engine.decide

    def wrapped(snapshot, intent):
        calls.append((snapshot, intent))
        return original(snapshot, intent)

    monkeypatch.setattr(appmod.decision_engine, "decide", wrapped)
    response = client.post("/chat", json={"message": "???", "lang": "en", "first_contact": True})
    assert len(calls) == 1


_NUTRITION_TARGETS = NutritionTargets(Decimal("2800"), Decimal("175"), Decimal("350"), Decimal("78"))
_NUTRITION_ROWS = [
    ("Breakfast", "Eggs and oats", "1 serving", "40", "100", "20", "700"),
    ("Lunch", "Chicken and rice", "1 serving", "70", "140", "30", "1100"),
    ("Dinner", "Salmon and potatoes", "1 serving", "65", "110", "28", "1000"),
]


def _daily_plan(rows=None, totals=("175", "350", "78", "2800"), include_total=True):
    rows = rows or _NUTRITION_ROWS
    output = ["| Meal | Food | Quantity | Protein (g) | Carbs (g) | Fat (g) | Kcal |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    output.extend("| " + " | ".join(row) + " |" for row in rows)
    if include_total:
        output.append("| Daily Total | | | " + " | ".join(totals) + " |")
    return "\n".join(output)


def _structured_plan_payload(*, total_kcal="2800"):
    """One-food rows prove the generated object never depends on display parsing."""
    dinner_kcal = str(400 + (int(total_kcal) - 2800))
    return {
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
                {"display_name": "Potatoes", "catalog_id": None, "grams": "300", "protein_g": "0", "carbs_g": "110", "fat_g": "0", "kcal": dinner_kcal},
            ]},
        ]
    }


def _structured_plan_text(lang="en"):
    plan = nutrition_plan.build_plan(
        _structured_plan_payload(), _NUTRITION_TARGETS,
        restrictions=(), provenance={"test": "structured"})
    return nutrition_plan.render(plan, lang)


def test_nutrition_plan_is_immutable_structured_authority_with_deterministic_rendering():
    plan = nutrition_plan.build_plan(
        _structured_plan_payload(), _NUTRITION_TARGETS,
        restrictions=("dairy", "dairy"), provenance={"generator": "test"})

    assert plan.version == "nutrition-plan-v1"
    assert plan.restrictions == ("dairy",)
    assert all(food.catalog_id is None for meal in plan.meals for food in meal.foods)
    assert len({meal.id for meal in plan.meals}) == 3
    assert len({food.id for meal in plan.meals for food in meal.foods}) == 6
    assert nutrition_plan.render(plan, "en") == nutrition_plan.render(plan, "en")
    assert plan.id not in nutrition_plan.render(plan, "en")
    assert nutrition_plan.to_record(plan)["meals"][0]["foods"][0]["catalog_id"] is None
    with pytest.raises(FrozenInstanceError):
        plan.version = "mutated"


def test_nutrition_plan_rejects_compound_food_rows_without_display_parsing():
    payload = _structured_plan_payload()
    payload["meals"][0]["foods"][0]["display_name"] = "Eggs and oats"

    with pytest.raises(nutrition_plan.NutritionPlanError, match="compound food"):
        nutrition_plan.build_plan(payload, _NUTRITION_TARGETS, restrictions=(), provenance={})


def _failures(reply):
    return validate_daily_nutrition(reply, _NUTRITION_TARGETS).failures


def test_daily_nutrition_validator_accepts_complete_target_matched_plan():
    result = validate_daily_nutrition(_daily_plan(), _NUTRITION_TARGETS)
    derived = appmod.nutrition_validation.targets_from_profile_block(
        "Calorie target: 2800 kcal\nProtein target: minimum 175g/day")

    assert result.valid is True
    assert result.failures == ()
    assert derived == NutritionTargets(Decimal("2800"), Decimal("175"), None, None)
    assert appmod._daily_nutrition_target("give me a full-day nutrition plan", "Calorie target: 2800 kcal") == 2800


@pytest.mark.parametrize("rows,totals,expected", [
    (_NUTRITION_ROWS[:-1], ("110", "240", "50", "1800"), "Missing dinner."),
    ((_NUTRITION_ROWS[0], _NUTRITION_ROWS[2]), ("105", "210", "48", "1700"), "Missing lunch."),
    ((_NUTRITION_ROWS[1], _NUTRITION_ROWS[2]), ("135", "250", "58", "2100"), "Missing breakfast."),
    ((_NUTRITION_ROWS[0], _NUTRITION_ROWS[1], ("Breakfast", "Toast", "1 serving", "5", "10", "2", "100"), _NUTRITION_ROWS[2]), ("180", "360", "80", "2900"), "Duplicate meal: breakfast."),
    ((_NUTRITION_ROWS[1], _NUTRITION_ROWS[0], _NUTRITION_ROWS[2]), ("175", "350", "78", "2800"), "Meals are not in chronological order."),
])
def test_daily_nutrition_validator_rejects_missing_duplicate_or_out_of_order_meals(rows, totals, expected):
    assert expected in _failures(_daily_plan(rows, totals))


def test_daily_nutrition_validator_accepts_chronological_snacks():
    rows = [
        ("Breakfast", "Eggs and oats", "1 serving", "40", "100", "20", "700"),
        ("Snack", "Yogurt", "1 serving", "10", "20", "5", "200"),
        ("Lunch", "Chicken and rice", "1 serving", "60", "120", "28", "1000"),
        ("Snack", "Banana", "1 serving", "5", "10", "3", "100"),
        ("Dinner", "Salmon and potatoes", "1 serving", "60", "100", "22", "800"),
    ]

    assert validate_daily_nutrition(_daily_plan(rows), _NUTRITION_TARGETS).valid is True


@pytest.mark.parametrize("rows,totals,expected", [
    ((_NUTRITION_ROWS[0], _NUTRITION_ROWS[1], ("Dinner", "Salmon and potatoes", "1 serving", "65", "110", "28", "700")), ("175", "350", "78", "2500"), "Calories outside 5% of target."),
    ((_NUTRITION_ROWS[0], _NUTRITION_ROWS[1], ("Dinner", "Salmon and potatoes", "1 serving", "65", "110", "28", "1300")), ("175", "350", "78", "3100"), "Calories outside 5% of target."),
    ((("Breakfast", "Eggs and oats", "1 serving", "20", "100", "20", "700"), ("Lunch", "Chicken and rice", "1 serving", "60", "140", "30", "1100"), ("Dinner", "Salmon and potatoes", "1 serving", "70", "110", "28", "1000")), ("150", "350", "78", "2800"), "Protein outside 5% of target."),
    ((("Breakfast", "Eggs and oats", "1 serving", "40", "80", "20", "700"), ("Lunch", "Chicken and rice", "1 serving", "70", "120", "30", "1100"), ("Dinner", "Salmon and potatoes", "1 serving", "65", "100", "28", "1000")), ("175", "300", "78", "2800"), "Carbs outside 5% of target."),
    ((("Breakfast", "Eggs and oats", "1 serving", "40", "100", "15", "700"), ("Lunch", "Chicken and rice", "1 serving", "70", "140", "25", "1100"), ("Dinner", "Salmon and potatoes", "1 serving", "65", "110", "20", "1000")), ("175", "350", "60", "2800"), "Fat outside 5% of target."),
])
def test_daily_nutrition_validator_rejects_targets_outside_five_percent(rows, totals, expected):
    assert expected in _failures(_daily_plan(rows, totals))


def test_daily_nutrition_validator_rejects_missing_or_inconsistent_totals():
    assert "Missing daily totals." in _failures(_daily_plan(include_total=False))
    assert "Daily kcal total does not equal meal totals." in _failures(_daily_plan(totals=("175", "350", "78", "2700")))


@pytest.mark.parametrize("row,expected", [
    (("Breakfast", "Eggs and oats", "", "40", "100", "20", "700"), "Breakfast has a food without quantity."),
    (("Breakfast", "Eggs and oats", "1 serving", "", "100", "20", "700"), "Breakfast has a food without protein."),
    (("Breakfast", "Eggs and oats", "1 serving", "40", "", "20", "700"), "Breakfast has a food without carbs."),
    (("Breakfast", "Eggs and oats", "1 serving", "40", "100", "", "700"), "Breakfast has a food without fat."),
    (("Breakfast", "Eggs and oats", "1 serving", "40", "100", "20", ""), "Breakfast has a food without kcal."),
    (("Breakfast", "", "1 serving", "40", "100", "20", "700"), "Breakfast has a food without a name."),
])
def test_daily_nutrition_validator_requires_complete_food_rows(row, expected):
    rows = (row, _NUTRITION_ROWS[1], _NUTRITION_ROWS[2])
    assert expected in _failures(_daily_plan(rows))


def test_daily_nutrition_validator_rejects_prohibited_completion_guidance():
    reply = _daily_plan() + "\nYou can add more food if you are hungry."

    assert "Plan includes prohibited completion guidance." in _failures(reply)


def test_daily_nutrition_validator_accepts_bulgarian_headers_and_meals():
    reply = "\n".join([
        "| Хранене | Храна | Количество | Белтъчини | Въглехидрати | Мазнини | Ккал |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| Закуска | Яйца и овес | 1 порция | 40 | 100 | 20 | 700 |",
        "| Обяд | Пиле и ориз | 1 порция | 70 | 140 | 30 | 1100 |",
        "| Вечеря | Сьомга и картофи | 1 порция | 65 | 110 | 28 | 1000 |",
        "| Общо | | | 175 | 350 | 78 | 2800 |",
    ])

    assert validate_daily_nutrition(reply, _NUTRITION_TARGETS).valid is True


def _set_sequence_stream(monkeypatch, captured, replies):
    calls = []
    queue = iter(replies)

    def fake_create(**kwargs):
        calls.append(kwargs)
        captured["system"] = kwargs["messages"][0]["content"]
        captured["messages"] = kwargs["messages"]
        reply = next(queue)
        return _StructuredCompletion(reply)

    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)
    return calls


def test_daily_nutrition_contract_fails_closed_without_a_second_generation(client, captured, monkeypatch):
    profile_block = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day"
    invalid = _structured_plan_payload(total_kcal="2500")
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    calls = _set_sequence_stream(monkeypatch, captured, [invalid])

    response = _post(client, "Give me a full-day nutrition plan", profile=_profile())

    assert _events(response) == [{"t": nutrition_conversation.failed_message("en")}, {"done": True}]
    assert len(calls) == 1


def test_daily_nutrition_contract_has_one_terminal_failure_after_invalid_delivery(client, captured, monkeypatch):
    profile_block = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day"
    invalid = _structured_plan_payload(total_kcal="2500")
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    calls = _set_sequence_stream(monkeypatch, captured, [invalid])

    response = _post(client, "Give me a full-day nutrition plan", profile=_profile())
    events = _events(response)

    assert events == [{"t": nutrition_conversation.failed_message("en")}, {"done": True}]
    assert len(calls) == 1
    assert json.dumps(invalid) not in events[0]["t"]


def test_voice_nutrition_failure_speaks_only_the_visible_failure_once(client, captured, monkeypatch):
    profile_block = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day"
    invalid = _structured_plan_payload(total_kcal="2500")
    uid = _login_for_chat(client, _profile())
    quota_calls = []
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    monkeypatch.setattr(store, "free_usage_consume",
                        lambda *args: quota_calls.append(args) or {"allowed": True})
    calls = _set_sequence_stream(monkeypatch, captured, [invalid])

    events = _events(_post(client, "Give me a full-day nutrition plan", voice=True))
    failure = nutrition_conversation.failed_message("en")

    assert events == [{"t": failure}, {"speech_text": failure}, {"done": True}]
    assert len(calls) == 1
    assert len(quota_calls) == 1
    assert "plan is ready" not in events[1]["speech_text"].lower()
    saved = store.list_conversation(uid, limit=10)
    assert [(turn["role"], turn["content"]) for turn in saved] == [
        ("user", "Give me a full-day nutrition plan"), ("assistant", failure),
    ]


def test_daily_nutrition_contract_never_persists_rejected_plan(client, captured, monkeypatch):
    profile_block = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day"
    invalid = _structured_plan_payload(total_kcal="2500")
    uid = _login_for_chat(client, _profile())
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    _set_sequence_stream(monkeypatch, captured, [invalid])

    response = _post(client, "Give me a full-day nutrition plan")
    response.get_data()

    saved = store.list_conversation(uid, limit=10)
    assert [turn["content"] for turn in saved] == [
        "Give me a full-day nutrition plan",
        nutrition_conversation.failed_message("en"),
    ]


def test_nutrition_plan_intake_asks_one_precise_question_without_generation(client, captured):
    message = "\u0418\u0441\u043a\u0430\u043c \u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d \u043f\u043b\u0430\u043d"
    response = client.post("/chat", json={"message": message, "lang": "bg", "profile": {"goal": "strength"}})
    events = _events(response)

    assert events == [{"t": recommendation_planning.clarification_message("age", "bg")}, {"done": True}]
    assert "messages" not in captured


def test_nutrition_plan_retry_after_same_clarification_becomes_one_unsupported_outcome(client, captured):
    message = "I want a nutrition plan"
    clarification = recommendation_planning.clarification_message("age", "en")
    response = client.post("/chat", json={
        "message": message,
        "lang": "en",
        "profile": {"goal": "strength"},
        "history": [{"role": "assistant", "content": clarification}],
    })

    assert _events(response) == [{"t": recommendation_planning.awaiting_profile_message("en")}, {"done": True}]
    assert "messages" not in captured


def test_nutrition_plan_with_confirmed_targets_generates_once_and_delivers_one_plan(client, captured, monkeypatch):
    profile_block = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day"
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    calls = _set_sequence_stream(monkeypatch, captured, [_structured_plan_payload()])

    response = _post(client, "I want a nutrition plan", profile=_profile())

    assert _events(response) == [{"t": _structured_plan_text()}, {"done": True}]
    assert len(calls) == 1


def test_recommendation_pipeline_uses_complete_profile_cards_before_one_nutrition_generation(
        client, captured, monkeypatch):
    profile = _profile(age="30", height="180", weight="80", goal="muscle_gain")
    monkeypatch.setattr(
        appmod, "_build_profile_block",
        lambda _profile, _lang: "Calorie target: 2800 kcal\nProtein target: minimum 175g/day",
    )
    calls = _set_sequence_stream(monkeypatch, captured, [_structured_plan_payload()])

    response = client.post("/chat", json={
        "message": "\u041d\u0430\u043f\u0440\u0430\u0432\u0438 \u043c\u0438 \u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d \u043f\u043b\u0430\u043d.",
        "lang": "bg", "profile": profile,
    })

    events = _events(response)
    assert len(calls) == 1
    assert events[-1] == {"done": True}
    assert "\u0417\u0430 \u0434\u0430 \u043f\u043e\u0434\u0433\u043e\u0442\u0432\u044f" not in events[0]["t"]


def test_recommendation_pipeline_requests_only_the_one_missing_profile_card(client, captured, monkeypatch):
    profile = _profile(age="30", height="180", goal="muscle_gain")
    profile.pop("weight")
    monkeypatch.setattr(
        appmod.client.chat.completions, "create",
        lambda **_kwargs: pytest.fail("incomplete profile must not generate"),
    )

    response = _post(client, "I want a nutrition plan", profile=profile)

    assert _events(response) == [{
        "t": recommendation_planning.clarification_message("weight", "en"),
    }, {"done": True}]
    assert "messages" not in captured


def test_recommendation_pipeline_never_repeats_the_same_profile_card_question(client, captured, monkeypatch):
    profile = _profile(age="30", height="180", goal="muscle_gain")
    profile.pop("weight")
    first_question = recommendation_planning.clarification_message("weight", "en")
    monkeypatch.setattr(
        appmod.client.chat.completions, "create",
        lambda **_kwargs: pytest.fail("repeated clarification must not generate"),
    )

    response = client.post("/chat", json={
        "message": "I want a nutrition plan", "lang": "en", "profile": profile,
        "history": [{"role": "assistant", "content": first_question}],
    })

    events = _events(response)
    assert events == [{"t": recommendation_planning.awaiting_profile_message("en")}, {"done": True}]
    assert first_question not in events[0]["t"]
    assert "messages" not in captured


def test_recommendation_pipeline_uses_authenticated_profile_cards_over_client_profile(client, captured, monkeypatch):
    verified = _profile(age="30", height="180", weight="80", goal="muscle_gain")
    _login_for_chat(client, verified)
    monkeypatch.setattr(
        appmod, "_build_profile_block",
        lambda _profile, _lang: "Calorie target: 2800 kcal\nProtein target: minimum 175g/day",
    )
    calls = _set_sequence_stream(monkeypatch, captured, [_structured_plan_payload()])

    response = _post(client, "I want a nutrition plan", profile={"goal": "fat_loss"})

    assert len(calls) == 1
    assert _events(response)[-1] == {"done": True}


def test_first_contact_coaching_uses_profile_cards_before_any_legacy_extraction(client, captured, monkeypatch):
    profile = _profile(age="30", height="180", weight="80", goal="muscle_gain")
    monkeypatch.setattr(
        appmod, "_extract_profile_silent",
        lambda *_args, **_kwargs: pytest.fail("coaching first contact must not extract before planning"),
    )
    monkeypatch.setattr(
        appmod, "_build_profile_block",
        lambda _profile, _lang: "Calorie target: 2800 kcal\nProtein target: minimum 175g/day",
    )
    calls = _set_sequence_stream(monkeypatch, captured, [_structured_plan_payload()])

    response = client.post("/chat", json={
        "message": "I want a nutrition plan", "lang": "en", "profile": profile,
        "first_contact": True,
    })

    assert len(calls) == 1
    assert _events(response)[-1] == {"done": True}


def test_structured_nutrition_generation_never_parses_display_text_and_persists_canonical_plan(
        client, captured, monkeypatch):
    uid = _login_for_chat(client, _profile())
    profile_block = (
        "Calorie target: 2800 kcal\nProtein target: minimum 175g/day\n"
        "Carbohydrate target: 350g\nFat target: 78g"
    )
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    monkeypatch.setattr(
        appmod.nutrition_validation, "parse_nutrition_day",
        lambda *_args, **_kwargs: pytest.fail("new structured plan must not parse rendered text"),
    )
    monkeypatch.setattr(
        appmod.nutrition_validation, "appears_complete_daily_plan",
        lambda *_args, **_kwargs: pytest.fail("new structured plan must not inspect rendered text"),
    )
    calls = _set_sequence_stream(monkeypatch, captured, [_structured_plan_payload()])

    events = _events(_post(client, "Give me a full-day nutrition plan", profile=_profile()))

    assert events == [{"t": _structured_plan_text()}, {"done": True}]
    assert len(calls) == 1
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "stream" not in calls[0]
    assert json.dumps(_structured_plan_payload()) not in events[0]["t"]
    records = store.list_nutrition_plans(uid)
    assert len(records) == 1
    record = records[0]["plan"]
    assert record["version"] == "nutrition-plan-v1"
    assert record["totals"] == {"protein_g": "175", "carbs_g": "350", "fat_g": "78", "kcal": "2800"}
    assert record["meals"][0]["foods"][0]["catalog_id"] is None
    assert store.list_nutrition(uid) == []
    assert store.list_conversation(uid, limit=10)[-1] == {
        "role": "assistant", "content": _structured_plan_text()}


@pytest.mark.parametrize("message", [
    "\u0440\u0435\u0436\u0438\u043c", "\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d \u0440\u0435\u0436\u0438\u043c", "\u0440\u0435\u0436\u0438\u043c \u0437\u0430 \u043c\u0430\u0441\u0430", "\u0440\u0435\u0436\u0438\u043c \u0437\u0430 \u0447\u0438\u0441\u0442\u0435\u043d\u0435",
    "\u043c\u0435\u043d\u044e", "\u0434\u043d\u0435\u0432\u043d\u043e \u043c\u0435\u043d\u044e", "\u0434\u0438\u0435\u0442\u0430", "\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d \u043f\u043b\u0430\u043d",
])
def test_bulgarian_nutrition_request_vocabulary_has_one_orchestration_entry(message):
    assert nutrition_conversation.is_plan_request(message) is True


def test_structured_nutrition_revisions_update_only_the_requested_objects_without_generation(
        client, captured, monkeypatch):
    uid = _login_for_chat(client, _profile(age="30", gender="male", height="180", weight="80"), plan="core")
    profile_block = (
        "Calorie target: 2800 kcal\nProtein target: minimum 175g/day\n"
        "Carbohydrate target: 350g\nFat target: 78g"
    )
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    calls = _set_sequence_stream(monkeypatch, captured, [_structured_plan_payload()])

    initial = _events(_post(client, "\u0418\u0441\u043a\u0430\u043c \u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d \u043f\u043b\u0430\u043d"))
    assert initial[-1] == {"done": True}
    initial_record = store.list_nutrition_plans(uid)[0]["plan"]

    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_kwargs: pytest.fail("revision invoked generation"))
    without_chicken = _events(_post(client, "\u0411\u0435\u0437 \u043f\u0438\u043b\u0435\u0448\u043a\u043e"))
    chicken_revision = store.list_nutrition_plans(uid)[0]["plan"]
    assert "Chicken" not in without_chicken[0]["t"]
    assert "Turkey breast" in without_chicken[0]["t"]
    assert chicken_revision["provenance"]["parent_plan_id"] == initial_record["id"]
    assert chicken_revision["totals"] == initial_record["totals"]

    more_rice = _events(_post(client, "\u0414\u043e\u0431\u0430\u0432\u0438 \u043f\u043e\u0432\u0435\u0447\u0435 \u043e\u0440\u0438\u0437"))
    rice_revision = store.list_nutrition_plans(uid)[0]["plan"]
    previous_rice = next(food for meal in chicken_revision["meals"] for food in meal["foods"]
                         if food["display_name"] == "Rice")
    updated_rice = next(food for meal in rice_revision["meals"] for food in meal["foods"]
                        if food["display_name"] == "Rice")
    assert previous_rice["grams"] == "200"
    assert updated_rice["grams"] == "210.00"
    assert rice_revision["totals"]["kcal"] == "2830.00"
    assert [food for meal in rice_revision["meals"] for food in meal["foods"]
            if food["id"] != updated_rice["id"]] == [
                food for meal in chicken_revision["meals"] for food in meal["foods"]
                if food["id"] != previous_rice["id"]]
    assert "210 g" in more_rice[0]["t"]

    breakfast = _events(_post(client, "\u0417\u0430\u043c\u0435\u043d\u0438 \u0437\u0430\u043a\u0443\u0441\u043a\u0430\u0442\u0430"))
    breakfast_revision = store.list_nutrition_plans(uid)[0]["plan"]
    assert "Whole eggs" not in breakfast[0]["t"]
    assert breakfast_revision["meals"][1:] == rice_revision["meals"][1:]
    assert breakfast_revision["totals"] == rice_revision["totals"]
    assert len(calls) == 1
    assert len(store.list_nutrition_plans(uid)) == 4
    assert len(store.list_conversation(uid, limit=20)) == 8


@pytest.mark.parametrize("message,profile", [
    ("I want a vegan keto nutrition plan", _profile()),
    ("I want a carnivore vegan nutrition plan", _profile()),
    ("I want a nutrition plan using only peanuts", _profile(allergies="peanuts")),
])
def test_unsupported_diet_policy_is_terminal_and_never_generates(client, captured, message, profile):
    response = _post(client, message, profile=profile)

    assert _events(response) == [{"t": nutrition_conversation.unsupported_diet_message("en")}, {"done": True}]
    assert "messages" not in captured


@pytest.mark.parametrize("profile_key,profile_value", [
    ("allergies", "peanuts"),
    ("foodPreferences", "vegetarian"),
])
def test_known_nutrition_constraints_do_not_trigger_a_duplicate_clarification_or_generation(
        client, captured, monkeypatch, profile_key, profile_value):
    profile_block = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day"
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    calls = _set_sequence_stream(monkeypatch, captured, [_structured_plan_payload()])

    response = _post(client, "I want a nutrition plan", profile=_profile(**{profile_key: profile_value}))

    assert _events(response) == [{"t": _structured_plan_text()}, {"done": True}]
    assert len(calls) == 1


def test_nutrition_plan_with_complete_profile_but_no_target_is_terminally_unsupported(client, captured, monkeypatch):
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: "")
    complete = _profile(age="30", gender="male", height="180", weight="80")

    response = _post(client, "I want a nutrition plan", profile=complete)

    assert _events(response) == [{"t": nutrition_conversation.unsupported_message("en")}, {"done": True}]
    assert "messages" not in captured


def test_nutrition_shadow_flag_does_not_change_the_orchestrated_plan_outcome(client, captured, monkeypatch):
    import nutrition_engine.shadow_hook as shadow_hook

    profile_block = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day"
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    monkeypatch.setenv("NUTRITION_ENGINE_V2_SHADOW", "true")
    dispatched = []
    monkeypatch.setattr(shadow_hook, "dispatch", lambda *args, **kwargs: dispatched.append(args) or True)
    calls = _set_sequence_stream(monkeypatch, captured, [_structured_plan_payload()])

    response = _post(client, "Give me a full-day nutrition plan", profile=_profile())

    assert _events(response) == [{"t": _structured_plan_text()}, {"done": True}]
    assert len(calls) == 1
    assert len(dispatched) == 1


@pytest.mark.parametrize("message", ["give me a strength workout", "how much water should I drink?"])
def test_daily_nutrition_contract_does_not_affect_non_daily_responses(client, captured, message):
    response = _post(client, message, profile=_profile())
    assert captured["messages"][-1] == {"role": "user", "content": message}
    assert any(event.get("t") == "ok" for event in _events(response))


def test_nutrition_targets_only_use_explicit_profile_authority():
    calorie_only = appmod.nutrition_validation.targets_from_profile_block("Calorie target: 2800 kcal")
    calorie_protein = appmod.nutrition_validation.targets_from_profile_block(
        "Calorie target: 2800 kcal\nProtein target: minimum 175g/day")
    explicit_macros = appmod.nutrition_validation.targets_from_profile_block(
        "Calorie target: 2800 kcal\nProtein target: minimum 175g/day\n"
        "Carbohydrate target: 350g\nFat target: 78g")

    assert calorie_only == NutritionTargets(Decimal("2800"), None, None, None)
    assert calorie_protein == NutritionTargets(Decimal("2800"), Decimal("175"), None, None)
    assert explicit_macros == _NUTRITION_TARGETS


def test_missing_macro_targets_do_not_create_macro_validation_requirements():
    rows = [
        ("Breakfast", "Eggs and oats", "1 serving", "40", "80", "15", "700"),
        ("Lunch", "Chicken and rice", "1 serving", "70", "90", "20", "1100"),
        ("Dinner", "Salmon and potatoes", "1 serving", "65", "70", "10", "1000"),
    ]
    plan = _daily_plan(rows, totals=("175", "240", "45", "2800"))

    assert validate_daily_nutrition(plan, NutritionTargets(Decimal("2800"))).valid is True
    assert validate_daily_nutrition(plan, NutritionTargets(Decimal("2800"), Decimal("175"))).valid is True


def test_nutrition_validator_accepts_display_rounding_and_decimal_comma():
    rounded_rows = [
        ("Breakfast", "Eggs and oats", "1 serving", "40.4", "100", "20", "700"),
        _NUTRITION_ROWS[1], _NUTRITION_ROWS[2],
    ]
    assert validate_daily_nutrition(_daily_plan(rounded_rows), _NUTRITION_TARGETS).valid is True
    assert validate_daily_nutrition(_daily_plan(totals=("175", "350", "78", "2809")), _NUTRITION_TARGETS).valid is True

    comma = _daily_plan().replace("40 | 100 | 20 | 700", "40,0 | 100,0 | 20,0 | 700,0")
    assert validate_daily_nutrition(comma, _NUTRITION_TARGETS).valid is True
    assert "Daily kcal total does not equal meal totals." in _failures(_daily_plan(totals=("175", "350", "78", "2760")))

    display_rounding = _daily_plan([
        ("Breakfast", "Food A", "100 g", "40.4", "100", "20", "700"),
        ("Lunch", "Food B", "100 g", "40", "100", "20", "800"),
        ("Dinner", "Food C", "100 g", "30", "80", "10", "759"),
    ], totals=("110", "280", "50", "2261"))
    assert validate_daily_nutrition(display_rounding, NutritionTargets(Decimal("2260"))).valid is True


@pytest.mark.parametrize("plan", [
    "\n".join([
        "**Breakfast**", "| Food | Protein | Carbs | Fat | Kcal |", "| Oats 100 g | 40 | 100 | 20 | 700 |",
        "**Lunch**", "| Chicken rice 100 g | 70 | 140 | 30 | 1100 |",
        "**Dinner**", "| Salmon potato 100 g | 65 | 110 | 28 | 1000 |",
        "| Daily Total | 175 | 350 | 78 | 2800 |",
    ]),
    "\n".join([
        "Breakfast", "| Food | Quantity | Protein | Carbs | Fat | Kcal |", "| Oats | 100 g | 40 | 100 | 20 | 700 |",
        "Lunch", "| Chicken rice | 100 g | 70 | 140 | 30 | 1100 |",
        "Dinner", "| Salmon potato | 100 g | 65 | 110 | 28 | 1000 |",
        "| Daily Total | | 175 | 350 | 78 | 2800 |",
    ]),
    "\n".join([
        "| Breakfast: | | | | Oats | 100 g | 40 | 100 | 20 | 700 |",
        "| Обяд: | | | | Chicken rice | 100 g | 70 | 140 | 30 | 1100 |",
        "| Dinner: | | | | Salmon potato | 100 g | 65 | 110 | 28 | 1000 |",
        "| Общо | | | 175 | 350 | 78 | 2800 |",
    ]),
    "\n".join([
        "**Закуска**", "Oats — 100 г, 40 g protein, 100 carbs, 20 fat, 700 kcal",
        "Lunch", "| Chicken rice | 100 g | 70 | 140 | 30 | 1100 |",
        "**Вечеря**", "Salmon potato — 100 g, 65 g protein, 110 carbs, 28 fat, 1000 kcal",
        "Общо: 175 350 78 2800",
    ]),
])
def test_nutrition_validator_parses_renderer_v4_plan_formats(plan):
    assert validate_daily_nutrition(plan, _NUTRITION_TARGETS).valid is True


def test_nutrition_validator_accepts_one_total_in_middle_and_rejects_conflicting_duplicates():
    middle = "\n".join([
        "Breakfast", "| Oats | 100 g | 40 | 100 | 20 | 700 |",
        "| Daily Total | | | 175 | 350 | 78 | 2800 |",
        "Lunch", "| Chicken rice | 100 g | 70 | 140 | 30 | 1100 |",
        "Dinner", "| Salmon potato | 100 g | 65 | 110 | 28 | 1000 |",
    ])
    duplicate = middle + "\n| Total | | | 175 | 350 | 78 | 2700 |"
    assert validate_daily_nutrition(middle, _NUTRITION_TARGETS).valid is True
    assert "Duplicate daily totals." in _failures(duplicate)


@pytest.mark.parametrize("message", [
    "хранителен план за деня", "дневен хранителен план", "дневен хранителен режим",
    "меню за днес", "хранителен режим", "искам хранителен режим",
    "друг хранителен режим", "алтернативен хранителен план", "алтернативно дневно меню",
    "пълен хранителен план", "meal plan for today", "daily meal plan", "full-day meal plan",
    "full day meal plan", "meal menu for today", "nutrition plan for today", "alternative meal plan",
    "alternative daily menu", "complete daily meal plan",
])
def test_full_day_request_detection_recognizes_required_direct_phrases(message):
    assert appmod.nutrition_validation.is_full_day_request(message) is True


@pytest.mark.parametrize("message", ["закуска", "идея за обяд", "рецепта", "breakfast only", "lunch suggestion", "dinner recipe"])
def test_single_meal_requests_bypass_full_day_validation(message):
    assert appmod.nutrition_validation.is_full_day_request(message) is False


def test_contextual_replacement_requests_require_immediate_nutrition_context():
    history = [{"role": "assistant", "content": "Your daily nutrition plan is 2800 kcal."}]
    assert appmod.nutrition_validation.is_full_day_request("искам друг хранителен режим", history) is True
    assert appmod.nutrition_validation.is_full_day_request("another meal plan", history) is True
    assert appmod.nutrition_validation.is_full_day_request("another meal plan", []) is False


@pytest.mark.parametrize("name,reason", [
    ("2 pcs", "food name is a quantity"),
    ("150 g", "food name is a quantity"),
    ("boiled", "food name is preparation only"),
    ("сварено", "food name is preparation only"),
    ("vegetables", "food name is too vague"),
    ("Зеленчуци", "food name is too vague"),
    ("protein", "food name is too vague"),
    ("По избор", "food name is too vague"),
])
def test_nutrition_validator_rejects_incomplete_or_vague_food_identity(name, reason):
    rows = [("Breakfast", name, "70 g", "40", "100", "20", "700"),
            _NUTRITION_ROWS[1], _NUTRITION_ROWS[2]]
    assert f"Breakfast has a {reason}." in _failures(_daily_plan(rows))


@pytest.mark.parametrize("fragment,reason", [
    ("| 2 pcs | 12 | 1 | 10 | 140 |", "Dangling quantity without a food name."),
    ("| 150 g | 12 | 1 | 10 | 140 |", "Dangling quantity without a food name."),
    ("| boiled | 12 | 1 | 10 | 140 |", "Dangling preparation without a food name."),
    ("| печено | 12 | 1 | 10 | 140 |", "Dangling preparation without a food name."),
])
def test_nutrition_validator_rejects_dangling_quantity_or_preparation_cards(fragment, reason):
    plan = _daily_plan() + "\n" + fragment
    assert reason in _failures(plan)


@pytest.mark.parametrize("name,quantity", [
    ("Whole eggs", "2 pcs"),
    ("Сварен ориз", "200 г"),
    ("Печено пилешко филе", "180 г"),
    ("Яйца на очи", "3 бр."),
    ("Зеленчуци: броколи, моркови и чушки", "200 г"),
    ("Mixed vegetables: broccoli, carrots and peppers", "200 g"),
])
def test_nutrition_validator_accepts_actionable_food_identities(name, quantity):
    rows = [("Breakfast", name, quantity, "40", "100", "20", "700"),
            _NUTRITION_ROWS[1], _NUTRITION_ROWS[2]]
    assert validate_daily_nutrition(_daily_plan(rows), _NUTRITION_TARGETS).valid is True


def test_nutrition_validator_deterministically_joins_a_named_food_with_its_next_quantity_row():
    plan = "\n".join([
        "Breakfast", "Whole eggs", "| 2 pcs | 12 | 1 | 10 | 140 |",
        "Lunch", "| Chicken rice | 100 g | 70 | 140 | 30 | 1100 |",
        "Dinner", "| Salmon potato | 100 g | 65 | 110 | 28 | 1000 |",
        "| Daily Total | | 147 | 251 | 68 | 2240 |",
    ])
    targets = NutritionTargets(Decimal("2240"), Decimal("147"), Decimal("251"), Decimal("68"))
    day = appmod.nutrition_validation.parse_nutrition_day(plan)

    assert day.meals[0].foods[0].name == "Whole eggs"
    assert day.meals[0].foods[0].quantity == "2 pcs"
    assert validate_daily_nutrition(plan, targets).valid is True


def test_daily_nutrition_semantic_failure_is_terminal_without_leaking_or_persisting_rejected_plan(
        client, captured, monkeypatch):
    profile_block = "Calorie target: 2800 kcal\nProtein target: minimum 175g/day"
    invalid_rows = [("Breakfast", "2 pcs", "70 g", "40", "100", "20", "700"),
                    _NUTRITION_ROWS[1], _NUTRITION_ROWS[2]]
    invalid = _daily_plan(invalid_rows)
    uid = _login_for_chat(client, _profile())
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    calls = _set_sequence_stream(monkeypatch, captured, [invalid])

    response = _post(client, "Give me a full-day nutrition plan")

    failure = nutrition_conversation.failed_message("en")
    assert _events(response) == [{"t": failure}, {"done": True}]
    assert len(calls) == 1
    saved = store.list_conversation(uid, limit=10)
    assert [turn["content"] for turn in saved] == ["Give me a full-day nutrition plan", failure]


def _communication_projections(*, adaptation=None, recovery="fresh", blueprint=None, rules=()):
    authority = types.SimpleNamespace(recovery_state=recovery)
    consensus = types.SimpleNamespace(applicable_rule_ids=tuple(rules))
    return persona_expert_projection.build_projections(
        persona_adaptation=adaptation or {}, authority=authority,
        blueprint=blueprint or _workout_blueprint(), expert_consensus=consensus)


def test_persona_expert_communication_projection_is_id_free_and_limited_to_supported_signals():
    persona, expert = _communication_projections(
        adaptation={"beginner": True, "home_equipment": True}, recovery="tired",
        blueprint=replace(_workout_blueprint(), equipment=["home"], session_minutes=25,
                          mobility_requirement="gentle_rom", contraindications=["painful range"]),
        rules=("MCG-001", "GRV-003", "WNK-003", "CLR-002", "CLR-004", "GLP-001"),
    )

    assert persona.guided_explanation and persona.equipment_reality and persona.recovery_sensitive
    assert expert.state_exclusion_reason and expert.state_recovery_reason and expert.single_actionable_cue
    rendered = repr((persona, expert))
    assert all(token not in rendered for token in ("P-", "GRV-", "MCG-", "CLR-", "confidence", "cluster", "tag"))


def test_persona_expert_communication_projection_keeps_recovery_and_exclusion_reasons_grounded():
    unchanged = replace(_workout_blueprint(), session_minutes=35, mobility_requirement="standard")
    no_exclusion = replace(_workout_blueprint(), contraindications=[])
    persona, expert = _communication_projections(recovery="tired", blueprint=unchanged,
                                                  rules=("GRV-001", "GRV-003", "WNK-003"))
    assert persona.recovery_sensitive is False and expert.state_recovery_reason is False
    _, expert = _communication_projections(blueprint=no_exclusion, rules=("MCG-001",))
    assert expert.state_exclusion_reason is False


def test_non_effective_and_unresolved_expert_rules_cannot_change_communication_projection():
    persona, expert = _communication_projections(rules=("CLR-002", "CLR-004", "GLP-001", "HLM-012"))
    assert persona.is_none is True
    assert expert.is_none is True


def test_communication_policy_explicit_short_requests_disable_optional_projection_prose():
    decision = types.SimpleNamespace(outcome="recommend")
    persona, expert = _communication_projections(adaptation={"beginner": True}, rules=("WNK-003",))
    for message in ("just the plan", "no explanation", "keep it brief", "само плана", "без обяснение", "говори накратко"):
        policy = conversation_composer.build_policy(
            decision=decision, message=message, respect_projection_preferences=True)
        frame = conversation_composer.compose(policy, validated_blueprint=_workout_blueprint(),
                                              persona_projection=persona,
                                              expert_communication_constraints=expert)
        prompt = conversation_composer.render_prompt(frame, "en")
        assert frame.optional_prose_allowed is False
        assert "ADDITIONAL PRESENTATION CONSTRAINTS" not in prompt


def test_persona_expert_communication_flag_is_resolved_once_and_off_keeps_active_prompt_identical(
        client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    calls = []
    original = appmod.os.getenv

    def getenv(name, default=None):
        if name == "PERSONA_EXPERT_COMMUNICATION_ACTIVE":
            calls.append(name)
        return original(name, default)

    monkeypatch.setattr(appmod.os, "getenv", getenv)
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))

    response = _post(client, "build a workout", profile=_profile(level="beginner"))

    assert response.status_code == 200
    assert calls == ["PERSONA_EXPERT_COMMUNICATION_ACTIVE"]
    assert "ADDITIONAL PRESENTATION CONSTRAINTS" not in captured["system"]
    assert captured["system"] == (appmod.recommendation_renderer.render_prompt(blueprint) + "\n\n" +
                                   conversation_composer.render_prompt(
                                       conversation_composer.compose(
                                           conversation_composer.build_policy(
                                               decision=types.SimpleNamespace(outcome="recommend"),
                                               message="build a workout"),
                                           validated_blueprint=blueprint,
                                           authority_facts=_profile(level="beginner")), "en"))


def test_active_persona_expert_communication_appends_id_free_wording_after_blueprint_and_frame(
        client, captured, monkeypatch):
    blueprint = replace(_workout_blueprint(), equipment=["home"])
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setenv("PERSONA_EXPERT_COMMUNICATION_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))

    response = _post(client, "build a workout", profile=_profile(level="intermediate", equipment="home"))

    assert response.status_code == 200
    system = captured["system"]
    assert system.startswith(appmod.recommendation_renderer.render_prompt(blueprint))
    assert system.index("CONVERSATION COMPOSER V1") < system.index("ADDITIONAL PRESENTATION CONSTRAINTS")
    assert "Do not assume gym access" in system
    assert all(token not in system for token in ("P-", "WNK-003", "GRV-", "MCG-", "confidence", "cluster"))


def test_persona_expert_communication_failure_preserves_existing_composer_prompt(client, captured, monkeypatch):
    blueprint = _workout_blueprint()
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setenv("PERSONA_EXPERT_COMMUNICATION_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *args, **kwargs: blueprint)
    monkeypatch.setattr(appmod.persona_expert_projection, "build_projections",
                        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("projection failure")))
    _set_stream(monkeypatch, captured, json.dumps({"blueprint": to_dict(blueprint), "explanations": []}))

    response = _post(client, "build a workout", profile=_profile(level="beginner"))

    assert response.status_code == 200
    assert "ADDITIONAL PRESENTATION CONSTRAINTS" not in captured["system"]
    assert "CONVERSATION COMPOSER V1" in captured["system"]


def test_voice_summary_uses_the_same_id_free_projection_without_reading_the_workout():
    decision = types.SimpleNamespace(outcome="recommend")
    persona, expert = _communication_projections(adaptation={"beginner": True}, rules=("WNK-003",))
    frame = conversation_composer.compose(
        conversation_composer.build_policy(decision=decision, message="build a workout", voice=True),
        validated_blueprint=_workout_blueprint(), persona_projection=persona,
        expert_communication_constraints=expert)
    prompt = conversation_composer.render_prompt(frame, "en")
    speech = conversation_composer.speech_projection(
        "**Workout**\n| Exercise | Sets |\n| Squat | 3 |\n- Why: Today stays manageable.",
        frame, "en", structured_kind="workout")

    assert "one short practical movement cue" in prompt
    assert "P-" not in prompt and "WNK-003" not in prompt
    assert speech == "Your workout is ready. Today stays manageable. The full plan is visible on screen."
    assert "Squat" not in speech and "|" not in speech


def test_daily_nutrition_contract_accounts_for_one_request_and_localizes_failure(client, captured, monkeypatch):
    invalid = _structured_plan_payload(total_kcal="2500")
    profile_block = "Калориен таргет: 2800 ккал\nПротеин таргет: минимум 175г/ден"
    free_calls, plan_calls = [], []
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: profile_block)
    monkeypatch.setattr(store, "free_usage_consume", lambda *args: free_calls.append(args) or {"allowed": True})
    monkeypatch.setattr(appmod, "_bump_plans_today", lambda: plan_calls.append(True))
    calls = _set_sequence_stream(monkeypatch, captured, [invalid])

    response = client.post("/chat", json={"message": "пълен хранителен план", "lang": "bg", "profile": _profile()})

    assert _events(response) == [{"t": nutrition_conversation.failed_message("bg")}, {"done": True}]
    assert len(calls) == 1
    assert len(free_calls) == 1
    assert len(plan_calls) == 1


_PRODUCTION_MALFORMED_NUTRITION = """При 99 кг и цел сваляне на мазнини — ето предложен хранителен план, който отговаря на твоите калорийни и протеинови нужди. Целта е да достигнеш 1914 ккал на ден с минимум 198 г протеин.

Закуска
Овесени ядки
100 г
Хранителна стойност
Белтъчини
13 г
Въглехидрати
66 г
Мазнини
7 г
Калории
389 kcal
Прясно мляко
200 мл
Хранителна стойност
Белтъчини
6 г
Въглехидрати
9 г
Мазнини
8 г
Калории
122 kcal
1 брой
0.5
Хранителна стойност
Белтъчини
0.5 г
Въглехидрати
25 г
Мазнини
0.3 г
Калории
95 kcal
Обяд
Пилешко филе
150 г
Хранителна стойност
Белтъчини
31 г
Въглехидрати
0 г
Мазнини
3.6 г
Калории
165 kcal
Зеленчуци (на пара)
200 г
Хранителна стойност
Белтъчини
5 г
Въглехидрати
10 г
Мазнини
0.5 г
Калории
50 kcal
Олио
10 мл
Хранителна стойност
Белтъчини
0 г
Въглехидрати
0 г
Мазнини
9 г
Калории
90 kcal
Закуска
Вечеря
Телешка кайма
150 г
Хранителна стойност
Белтъчини
28 г
Въглехидрати
0 г
Мазнини
10 г
Калории
210 kcal
Авокадо
100 г
Хранителна стойност
Белтъчини
2 г
Въглехидрати
9 г
Мазнини
15 г
Калории
160 kcal
Броколи
200 г
Хранителна стойност
Белтъчини
5 г
Въглехидрати
10 г
Мазнини
0.5 г
Калории
55 kcal
Дневни общо
114.0 г
Белтъчини
211 г
Въглехидрати
54.4 г
Мазнини
1914
Калории
Този план осигурява балансирано хранене с необходимите макроси."""


def test_production_multiline_fixture_is_one_rejected_canonical_day():
    targets = NutritionTargets(Decimal("1914"), Decimal("198"))
    result = validate_daily_nutrition(_PRODUCTION_MALFORMED_NUTRITION, targets)

    assert result.valid is False
    assert dict(result.day.computed_totals) == {
        "protein": Decimal("90.5"), "carbs": Decimal("129"),
        "fat": Decimal("53.9"), "kcal": Decimal("1336"),
    }
    assert [(meal.key, len(meal.foods)) for meal in result.day.meals] == [
        ("breakfast", 3), ("lunch", 3), ("breakfast", 0), ("dinner", 3)]
    for failure in (
        "Breakfast has a food name is a quantity.",
        "Breakfast has a food with an unsupported quantity unit.",
        "Duplicate meal: breakfast.",
        "Empty meal: breakfast.",
        "Malformed daily totals: expected protein label before value.",
        "Calories outside 5% of target.",
        "Protein outside 5% of target.",
    ):
        assert failure in result.failures


@pytest.mark.parametrize("message", [
    "направи ми хранителен режим", "искам хранителен режим", "дай ми меню",
    "направи ми меню", "направи ми дневно меню", "дай ми хранителен план",
    "хранителен план за мен", "искам режим за отслабване", "направи ми друг режим",
    "искам друго меню", "меню за сваляне на мазнини", "какво да ям през деня",
    "при 99 кг направи ми меню за отслабване", "make me a meal plan", "give me a diet",
    "make me a menu", "what should I eat today", "give me another diet",
    "meal plan for fat loss", "make a plan for my day",
])
def test_real_daily_plan_request_phrases_never_bypass_the_full_day_gate(message):
    assert appmod.nutrition_validation.is_full_day_request(message) is True


def test_response_side_detection_buffers_only_complete_daily_plan_evidence():
    assert appmod.nutrition_validation.appears_complete_daily_plan(_PRODUCTION_MALFORMED_NUTRITION) is True
    assert appmod.nutrition_validation.appears_complete_daily_plan(_daily_plan()) is True
    assert appmod.nutrition_validation.appears_complete_daily_plan("Закуска\nЯйца\n2 бр.") is False
    assert appmod.nutrition_validation.appears_complete_daily_plan("Chicken recipe | 200 g | 40 | 0 | 5 | 250") is False


def test_missed_menu_phrase_never_streams_or_persists_rejected_daily_plan(client, captured, monkeypatch):
    uid = _login_for_chat(client, _profile())
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang:
                        "Калориен таргет: 1914 ккал\nПротеин таргет: минимум 198г/ден")
    _set_sequence_stream(monkeypatch, captured, [_PRODUCTION_MALFORMED_NUTRITION])

    events = _events(_post(client, "дай ми меню", profile=_profile()))
    failure = nutrition_conversation.failed_message("en")

    assert events == [{"t": failure}, {"done": True}]
    assert _PRODUCTION_MALFORMED_NUTRITION not in str(events)
    saved = store.list_conversation(uid, limit=10)
    assert [turn["content"] for turn in saved] == ["дай ми меню", failure]


def test_valid_multiline_day_serializes_the_validated_canonical_model():
    multiline = """Breakfast
Eggs
2 pcs
Nutrition value
Protein
40 g
Carbs
100 g
Fat
20 g
Calories
700 kcal
Lunch
Chicken rice
1 serving
Nutrition value
Protein
70 g
Carbs
140 g
Fat
30 g
Calories
1100 kcal
Dinner
Salmon potatoes
1 serving
Nutrition value
Protein
65 g
Carbs
110 g
Fat
28 g
Calories
1000 kcal
Daily Total
Protein
175 g
Carbs
350 g
Fat
78 g
Calories
2800 kcal"""
    result = validate_daily_nutrition(multiline, _NUTRITION_TARGETS)

    assert result.valid is True
    assert result.delivery == appmod.nutrition_validation.serialize_nutrition_day(result.day)
    assert result.delivery.startswith("| Meal | Food | Quantity | Protein (g) |")
    assert "| Daily Total | | | 175 | 350 | 78 | 2800 |" in result.delivery
