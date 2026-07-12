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
from dataclasses import FrozenInstanceError
import pytest

import app as appmod
import db as store
import decision_engine
from recommend import diversity as recommendation_diversity
from recommend.blueprint import NutritionBlueprint, WorkoutBlueprint, to_dict
from context_builder import LockedPreferences, Subject, build_context
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
    yield


def _events(resp):
    out = []
    for line in resp.get_data(as_text=True).splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _post(client, message, profile=None):
    return client.post("/chat", json={"message": message, "lang": "en", "profile": profile or {}})


def _set_stream(monkeypatch, captured, reply):
    def fake_create(**kwargs):
        captured["system"] = kwargs["messages"][0]["content"]
        captured["messages"] = kwargs["messages"]
        def stream():
            yield _Chunk(reply)
        return stream()

    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)


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
               "goal": "strength", "age": 34, "gender": "male"}
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


def test_first_contact_does_not_enter_a2_context_bridge(client, monkeypatch):
    calls = []
    original = appmod.context_builder.build_context

    def wrapped(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(appmod.context_builder, "build_context", wrapped)
    client.post("/chat", json={"message": "hello", "lang": "en", "first_contact": True})
    assert calls == []


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


@pytest.mark.parametrize("message,blueprint,expected_title", [
    ("build a workout", _workout_blueprint(), "**Workout**"),
    ("plan my nutrition", _nutrition_blueprint(), "**Nutrition**"),
])
def test_active_recommendation_engine_delivers_only_verified_blueprint(client, captured, monkeypatch,
                                                                         message, blueprint, expected_title):
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


def test_first_contact_does_not_compute_b2_controlled_response(client, monkeypatch):
    calls = []
    original = appmod.decision_engine.decide

    def wrapped(snapshot, intent):
        calls.append((snapshot, intent))
        return original(snapshot, intent)

    monkeypatch.setattr(appmod.decision_engine, "decide", wrapped)
    response = client.post("/chat", json={"message": "???", "lang": "en", "first_contact": True})
    assert calls == []


def _daily_plan(total=2800, meals=("Breakfast", "Lunch", "Dinner")):
    rows = ["| Meal | Quantity | Protein | Carbs | Fat | Kcal |",
            "| --- | --- | --- | --- | --- | --- |"]
    rows.extend(f"| {meal} | food | 30 | 70 | 20 | 700 |" for meal in meals)
    rows.append(f"| Total | | 120 | 280 | 80 | {total} |")
    return "\n".join(rows)


@pytest.mark.parametrize("target", [2800, 2500])
def test_daily_nutrition_contract_accepts_total_within_ten_percent(target):
    profile_block = f"Calorie target: {target} kcal"
    assert appmod._is_complete_daily_nutrition(_daily_plan(target), target)
    assert appmod._daily_nutrition_target("give me a full-day nutrition plan", profile_block) == target


@pytest.mark.parametrize("reply", [
    _daily_plan(1600),
    _daily_plan(2800, ("Breakfast", "Dinner")),
    _daily_plan(2800, ("Breakfast", "Lunch")),
    "Breakfast, lunch, and dinner are included, but no daily calories are declared.",
])
def test_daily_nutrition_contract_rejects_incomplete_or_under_target_plan(reply):
    assert not appmod._is_complete_daily_nutrition(reply, 2800)


def test_daily_nutrition_contract_delivers_controlled_clarification(client, captured, monkeypatch):
    monkeypatch.setattr(appmod, "_build_profile_block", lambda profile, lang: "Calorie target: 2800 kcal")
    _set_stream(monkeypatch, captured, _daily_plan(1600))
    response = _post(client, "Give me a full-day nutrition plan", profile=_profile())
    events = _events(response)

    assert events == [{"t": "I couldn't generate a complete nutrition plan that matches your current calorie target. I'll regenerate it."}, {"done": True}]


@pytest.mark.parametrize("message", ["give me a strength workout", "how much water should I drink?"])
def test_daily_nutrition_contract_does_not_affect_non_daily_responses(client, captured, message):
    response = _post(client, message, profile=_profile())
    assert captured["messages"][-1] == {"role": "user", "content": message}
    assert any(event.get("t") == "ok" for event in _events(response))
