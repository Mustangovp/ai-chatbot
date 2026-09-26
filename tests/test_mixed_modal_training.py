"""Mixed-modal format, safety, and delivery contracts over the real training engine."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app as appmod
import db as store
from training_engine import (
    Difficulty, MixedModalPlanningError, MovementPattern, SessionFormat,
    TrainingModality, build_training_plan, load_exercise_library,
    parse_mixed_modal_request, structure_mixed_modal_plan,
)
from training_engine import renderer
from training_engine.completion import completion_projection
from training_engine.followups import conversation_plan_from_record, serialize_conversation_plan
from training_engine.lineage import delivered_plan_lineage, plan_from_delivered_lineage
from training_engine.longitudinal import context_from_persisted_history
from training_engine.cross_session import adapt_from_persisted_history
from workout_execution import normalize_execution
from brain.types import (CapacityEnvelope, Constraint, ConstraintSet, ConstraintTier,
                         Decision, Intervention, S2State, Verdict)


PROFILE = {"goal": "strength", "level": "beginner", "equipment": "bodyweight",
           "recoveryFeel": "fresh"}


def _plan(profile=PROFILE, *, message="Give me a CrossFit AMRAP workout", exclusions=frozenset(), history=False):
    request = parse_mixed_modal_request(message)
    assert request is not None
    plan = build_training_plan(
        recommendation_blueprint_id="crossfit-test", facts=profile,
        excluded_movement_patterns=exclusions, mixed_modal=request.format)
    return structure_mixed_modal_plan(
        plan, request=request, facts=profile, library=load_exercise_library(),
        excluded_patterns=exclusions, completed_history=history)


@pytest.mark.parametrize(("message", "expected"), (
    ("Give me a CrossFit AMRAP workout", SessionFormat.AMRAP),
    ("Build an EMOM workout", SessionFormat.EMOM),
    ("Make me a CrossFit For Time workout", SessionFormat.FOR_TIME),
    ("Give me a CrossFit rounds and reps workout", SessionFormat.ROUNDS_REPS),
    ("Build a strength + metcon workout", SessionFormat.STRENGTH_METCON),
    ("Give me CrossFit intervals", SessionFormat.INTERVALS),
    ("Build a mixed-modal session", SessionFormat.ROUNDS_REPS),
    ("Make me an interval session", SessionFormat.INTERVALS),
    ("Дай ми кросфит тренировка EMOM", SessionFormat.EMOM),
    ("Направи ми кросфит тренировка за време", SessionFormat.FOR_TIME),
))
def test_closed_format_recognition_en_bg(message, expected):
    assert parse_mixed_modal_request(message).format is expected


def test_crossfit_identity_does_not_infer_advanced_skill_or_create_workout_intent():
    request = parse_mixed_modal_request("I do CrossFit")
    assert request is not None
    assert appmod._explicit_workout_request("I do CrossFit") is False
    assert not hasattr(request, "experience_level")
    advanced = {**PROFILE, "level": "advanced", "equipment": "gym"}
    plan = _plan(advanced)
    assert all(load_exercise_library().require(item.exercise_id).difficulty is not Difficulty.ADVANCED
               for session in plan.sessions for item in session.prescriptions)


@pytest.mark.parametrize("message", ("Build a mixed-modal session", "Make me an interval session"))
def test_explicit_mixed_modal_session_reaches_workout_intent(message):
    assert appmod._explicit_workout_request(message)
    assert parse_mixed_modal_request(message) is not None


@pytest.mark.parametrize("goal", ("strength", "hypertrophy", "general_fitness"))
def test_non_crossfit_plan_keeps_its_existing_patterns_and_structure(goal):
    plan = build_training_plan(recommendation_blueprint_id="ordinary-plan", facts={**PROFILE, "goal": goal})
    assert all(session.mixed_modal is None for session in plan.sessions)
    assert all(item.movement_pattern is not MovementPattern.MONOSTRUCTURAL
               for session in plan.sessions for item in session.prescriptions)
    legacy = build_training_plan(
        recommendation_blueprint_id="legacy-plan", facts={**PROFILE, "goal": goal},
        library=load_exercise_library("1.2.0"))
    assert legacy.exercise_library_version == "1.2.0"
    assert [[item.exercise_id for item in session.prescriptions] for session in legacy.sessions] == [
        [item.exercise_id for item in session.prescriptions] for session in plan.sessions]


@pytest.mark.parametrize("format_name", tuple(SessionFormat))
def test_all_structures_use_prescribed_movements_and_are_truthfully_rendered(format_name):
    profile = {**PROFILE, "equipment": "home", "level": "intermediate"}
    plan = _plan(profile, message=f"Give me a CrossFit {format_name.value.replace('_', ' ')} workout")
    first = plan.sessions[0]
    structure = first.mixed_modal
    assert structure.format is format_name
    assert TrainingModality.GYMNASTICS in structure.modalities
    assert TrainingModality.MONOSTRUCTURAL in structure.modalities
    assert 5 <= structure.time_cap_minutes <= 60
    assert all(item.target_load_kg is None for item in first.prescriptions)
    assert all(item.sets <= 2 and item.target_rpe <= 7 for item in first.prescriptions)
    delivered = renderer.render_delivery(plan, load_exercise_library(), ("Invent a new exercise",), "en")
    assert "Invent a new exercise" not in delivered
    assert structure.format.value.split("_")[0].lower() in delivered.lower() or format_name is SessionFormat.ROUNDS_REPS
    assert "**Why:**" in delivered
    projection = renderer.render_completion_projection(plan, load_exercise_library(), "en")
    assert projection["sessions"][0]["mixed_modal"]["format"] == format_name.value


def test_limited_recovery_overrides_brutal_for_time_and_reduces_dose():
    fresh = _plan({**PROFILE, "equipment": "gym"}, message="Give me a CrossFit For Time workout")
    limited = _plan({**PROFILE, "equipment": "gym", "recoveryFeel": "poor"},
                    message="Give me a brutal CrossFit For Time workout")
    assert fresh.sessions[0].mixed_modal.format is SessionFormat.FOR_TIME
    assert limited.sessions[0].mixed_modal.format is SessionFormat.INTERVALS
    assert sum(item.sets for item in limited.sessions[0].prescriptions) < sum(
        item.sets for item in fresh.sessions[0].prescriptions)
    assert all(item.target_rpe <= 6 for item in limited.sessions[0].prescriptions)
    assert "Lower recovery" in renderer.render_delivery(limited, load_exercise_library(), (), "en")


def test_persistent_overhead_exclusion_survives_harder_crossfit_request():
    profile = {**PROFILE, "level": "intermediate", "equipment": "gym",
               "healthRestrictions": ["Avoid overhead pressing."]}
    plan = _plan(profile, message="Give me a harder upper-body CrossFit workout",
                 exclusions=frozenset({MovementPattern.VERTICAL_PUSH}))
    assert all(item.movement_pattern is not MovementPattern.VERTICAL_PUSH
               for session in plan.sessions for item in session.prescriptions)
    assert "movement_constraint" in plan.sessions[0].mixed_modal.reason_codes
    assert "overhead" not in renderer.render_delivery(plan, load_exercise_library(), (), "en").lower()


def test_knee_box_jump_request_fails_closed_without_inventing_safety_substitution():
    message = "Give me a CrossFit workout with box jumps despite my knee limitation"
    with pytest.raises(MixedModalPlanningError, match="explicit movement boundary"):
        _plan(PROFILE, message=message)


def test_olympic_and_machine_requests_do_not_infer_skill_or_equipment():
    plan = _plan({**PROFILE, "equipment": "home", "level": "advanced"},
                 message="Give me a CrossFit EMOM workout with snatches and rowing")
    text = renderer.render_delivery(plan, load_exercise_library(), (), "en")
    assert "Olympic lifts are omitted" in text
    assert "not in the validated exercise catalog" in text
    assert not any("olympic" in load_exercise_library().require(item.exercise_id).training_tags
                   for session in plan.sessions for item in session.prescriptions)


def test_missing_experience_and_equipment_do_not_become_verified_rationale():
    request = parse_mixed_modal_request("Give me a CrossFit AMRAP workout")
    facts = {"goal": "general_fitness", "recoveryFeel": "fresh"}
    baseline = build_training_plan(
        recommendation_blueprint_id="crossfit-followup-locked", facts=facts,
        locked_preferences={"equipment": "home"}, level_override=Difficulty.BEGINNER,
        mixed_modal=request.format)
    plan = structure_mixed_modal_plan(
        baseline, request=request, facts=facts, library=load_exercise_library())
    structure = plan.sessions[0].mixed_modal
    assert "bounded_prescription" in structure.reason_codes
    assert "profile_experience" not in structure.reason_codes
    assert "profile_equipment" not in structure.reason_codes
    text = renderer.render_delivery(plan, load_exercise_library(), (), "en")
    assert "Saved experience" not in text
    assert "Saved equipment" not in text


def test_structure_survives_conversation_persistence_and_observed_completion_stays_truthful():
    plan = _plan()
    state = conversation_plan_from_record(serialize_conversation_plan(plan))
    assert state is not None and state.plan == plan
    assert plan_from_delivered_lineage(delivered_plan_lineage(plan)) == plan
    projection = completion_projection(plan, load_exercise_library())
    session = projection["sessions"][0]
    observations = [{
        "prescription_id": item["prescription_id"], "exercise_id": item["exercise_id"],
        "exercise_version": item["exercise_version"], "completed_sets": 0,
        "actual_repetitions": None, "execution_state": "unknown",
    } for item in session["exercises"]]
    evidence = {"plan_id": plan.plan_id, "plan_version": plan.version,
                "session_id": session["session_id"], "exercises": observations}
    result = normalize_execution({}, evidence, plan=plan)
    assert result["execution_state"] == "skipped"
    assert result["completion"] == 0
    malformed = serialize_conversation_plan(plan)
    malformed["sessions"][0]["mixed_modal"]["format"] = "unsupported"
    assert conversation_plan_from_record(malformed) is None


def test_difficult_completed_session_is_history_not_permission_to_overload():
    profile = {**PROFILE, "equipment": "gym", "level": "intermediate"}
    parent = build_training_plan(
        recommendation_blueprint_id="crossfit-history", facts=profile,
        mixed_modal=SessionFormat.AMRAP)
    session = completion_projection(parent, load_exercise_library())["sessions"][0]
    now = datetime.now(timezone.utc).isoformat()
    exercises = [{
        "prescription_id": item["prescription_id"], "exercise_id": item["exercise_id"],
        "exercise_version": item["exercise_version"],
        "completed_sets": item["prescribed_sets"], "completed_repetitions": item["rep_max"],
        "completed_rpe": 9, "completed_effort": "hard",
    } for item in session["exercises"]]
    record = {
        "completion": 100, "occurred_at": now,
        "exercises": {"workout_completion": {
            "workout_id": "completed-crossfit-test", "plan_id": parent.plan_id,
            "plan_version": parent.version, "session_id": session["session_id"],
            "completion_timestamp": now, "exercises": exercises,
        }},
    }
    history = context_from_persisted_history(
        [record], library=load_exercise_library(), split=parent.training_split)
    assert history.source_completion_count == 1
    next_plan = build_training_plan(
        recommendation_blueprint_id="crossfit-history-next", facts=profile,
        mixed_modal=SessionFormat.AMRAP,
        deprioritized_exercise_ids=history.recent_exercise_ids)
    assert {item.exercise_id for item in next_plan.sessions[0].prescriptions} != history.recent_exercise_ids
    assert all(item.target_rpe <= 7 and item.sets <= 2 for item in next_plan.sessions[0].prescriptions)
    decision = adapt_from_persisted_history(parent, [record])
    assert not decision.applied
    assert decision.plan == parent
    delivered = structure_mixed_modal_plan(
        next_plan, request=parse_mixed_modal_request("Give me a CrossFit AMRAP workout"),
        facts=profile, library=load_exercise_library(), completed_history=True)
    assert "completed_history" in delivered.sessions[0].mixed_modal.reason_codes


@pytest.fixture
def chat_client(monkeypatch):
    appmod.app.config["TESTING"] = True
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("BRAIN_ENFORCE", "false")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "false")
    def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"explanations": []})))])
    monkeypatch.setattr(appmod.client.chat.completions, "create", create)
    return appmod.app.test_client()


def _events(response):
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")]


def test_real_chat_beginner_crossfit_and_bulgarian_delivery(chat_client, monkeypatch):
    monkeypatch.setattr(appmod.client.chat.completions, "create",
                        lambda **kwargs: pytest.fail("mixed-modal programming must not use model authority"))
    events = _events(chat_client.post("/chat", json={"message": "Дай ми кросфит тренировка EMOM",
                                                   "lang": "bg", "profile": PROFILE}))
    assert events[-1] == {"done": True}
    assert "EMOM" in events[0]["t"] and "**Защо:**" in events[0]["t"]
    assert events[1]["training_completion"]["sessions"][0]["mixed_modal"]["format"] == "emom"


def test_brain_safety_withholds_crossfit_even_when_a_format_is_requested(chat_client, monkeypatch):
    monkeypatch.setenv("BRAIN_ENFORCE", "true")
    decision = Decision(
        verdict=Verdict.NO_TRAIN, intervention=Intervention("recovery", "test"),
        generate_training=False, halt=False, verdict_confidence=1.0,
        constraints=ConstraintSet([Constraint("high_impact", ConstraintTier.ABSOLUTE, "test")]),
        envelope=CapacityEnvelope(0.2, 0.2, 0.2, True, 1.0),
        s2=S2State(0.2, 1.0, [], False), need_vector=[("recovery", 1.0)],
        decision_id="crossfit-safety-test", model=None,
    )
    monkeypatch.setattr(appmod.brain_cascade, "decide", lambda *args, **kwargs: decision)
    events = _events(chat_client.post("/chat", json={
        "message": "Give me a brutal CrossFit For Time workout", "lang": "en", "profile": PROFILE,
    }))
    assert events[-1] == {"done": True}
    assert not any("training_completion" in item for item in events)
    assert not any("For Time" in item.get("t", "") for item in events)


def test_real_chat_account_constraint_survives_crossfit_delivery(chat_client):
    user_id = store.get_or_create_user("crossfit-constraint-test@example.com")
    store.save_profile(user_id, {**PROFILE, "level": "intermediate", "equipment": "gym"})
    store.add_account_training_constraints(user_id, ["vertical_push"])
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    events = _events(chat_client.post("/chat", json={"message": "Give me a harder upper-body CrossFit workout",
                                                   "lang": "en"}))
    assert events[-1] == {"done": True}
    completion = next(item["training_completion"] for item in events if "training_completion" in item)
    assert not any(item["exercise_id"] == "dumbbell.overhead_press" for item in completion["sessions"][0]["exercises"])
    assert completion["sessions"][0]["mixed_modal"]["format"] == "rounds_reps"
    assert "Active movement exclusions" in events[0]["t"]
