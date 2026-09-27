"""Mixed-modal format, safety, and delivery contracts over the real training engine."""
import json
from datetime import datetime, timezone
from dataclasses import replace
from types import SimpleNamespace

import pytest

import app as appmod
import db as store
from training_engine import (
    Difficulty, MixedModalPlanningError, MovementPattern, SessionFormat, TrainingRuntimeError,
    TrainingModality, build_training_plan, load_exercise_library,
    parse_mixed_modal_request, structure_mixed_modal_plan,
)
from training_engine import renderer
from training_engine.runtime import validate_training_plan_constraints
from training_engine.completion import completion_projection
from training_engine.followups import conversation_plan_from_record, serialize_conversation_plan
from training_engine.followups import apply_followup, parse_workout_followup, state_for
from training_engine.health_restrictions import knee_load_limited_patterns
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


def test_wod_harder_followup_uses_authoritative_plan_and_preserves_constraint(chat_client, monkeypatch):
    user_id = store.get_or_create_user("crossfit-harder-followup@example.com")
    store.save_profile(user_id, {**PROFILE, "equipment": "gym"})
    store.add_account_training_constraints(user_id, ["vertical_push"])
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    conversation_id = "crossfit-harder-followup"
    first = _events(chat_client.post("/chat", json={"message": "Give me a CrossFit workout", "lang": "en",
                                                   "conversation_id": conversation_id}))
    assert any("training_completion" in event for event in first)
    assert parse_workout_followup("Make the WOD harder") is not None
    monkeypatch.setattr(appmod.client.chat.completions, "create",
                        lambda **kwargs: pytest.fail("WOD follow-up must not use model exercise authority"))
    second = _events(chat_client.post("/chat", json={"message": "Make the WOD harder", "lang": "en",
                                                    "conversation_id": conversation_id}))
    assert second[-1] == {"done": True}
    assert any("training_completion" in event for event in second) or "couldn't safely" in second[0].get("t", "")
    for event in second:
        completion = event.get("training_completion")
        if completion:
            assert all(item["exercise_id"] not in {"dumbbell.overhead_press", "dumbbell.seated_press"}
                       for item in completion["sessions"][0]["exercises"])


@pytest.mark.parametrize("message", (
    "Make this WOD harder", "Make my WOD harder", "Increase the WOD intensity",
    "Make the workout more difficult", "Направи тази WOD тренировка по-трудна",
    "Увеличи интензивността на тренировката",
))
def test_contextual_wod_change_never_falls_to_unsafe_model(chat_client, monkeypatch, message):
    user_id = store.get_or_create_user("crossfit-context-followup@example.com")
    store.save_profile(user_id, {**PROFILE, "equipment": "gym"})
    store.add_account_training_constraints(user_id, ["vertical_push"])
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    conversation_id = "crossfit-context-followup"
    first = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit workout", "lang": "en", "conversation_id": conversation_id}))
    assert any("training_completion" in event for event in first)

    def unsafe_model(**kwargs):
        if kwargs.get("stream"):
            return [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                content="Do overhead presses and thrusters."))])]
        pytest.fail("mixed-modal follow-up must not ask the model for a prescription")

    monkeypatch.setattr(appmod.client.chat.completions, "create", unsafe_model)
    events = _events(chat_client.post("/chat", json={
        "message": message, "lang": "en", "conversation_id": conversation_id}))
    assert events[-1] == {"done": True}
    assert all("overhead presses and thrusters" not in event.get("t", "").lower()
               for event in events)
    for event in events:
        if "training_completion" in event:
            assert all(load_exercise_library().require(item["exercise_id"]).movement_pattern
                       is not MovementPattern.VERTICAL_PUSH
                       for session in event["training_completion"]["sessions"]
                       for item in session["exercises"])


def test_final_mixed_modal_delivery_rejects_constraint_violating_plan(chat_client, monkeypatch):
    user_id = store.get_or_create_user("crossfit-final-boundary@example.com")
    store.save_profile(user_id, {**PROFILE, "equipment": "gym"})
    store.add_account_training_constraints(user_id, ["vertical_push"])
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    conversation_id = "crossfit-final-boundary"
    first = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit workout", "lang": "en", "conversation_id": conversation_id}))
    assert any("training_completion" in event for event in first)
    original = appmod.structure_mixed_modal_plan

    def unsafe_structure(plan, **kwargs):
        structured = original(plan, **kwargs)
        session = structured.sessions[0]
        overhead = load_exercise_library().require("dumbbell.overhead_press")
        prescriptions = (replace(session.prescriptions[0], exercise_id=overhead.exercise_id,
                                 exercise_version=overhead.version,
                                 movement_pattern=MovementPattern.VERTICAL_PUSH),
                         *session.prescriptions[1:])
        return replace(structured, sessions=(replace(session, prescriptions=prescriptions),
                                             *structured.sessions[1:]))

    monkeypatch.setattr(appmod, "structure_mixed_modal_plan", unsafe_structure)
    monkeypatch.setattr(appmod.client.chat.completions, "create",
                        lambda **kwargs: pytest.fail("unsafe plan must not reach model delivery"))
    events = _events(chat_client.post("/chat", json={
        "message": "Make this WOD harder", "lang": "en", "conversation_id": conversation_id}))
    assert events[-1] == {"done": True}
    assert not any("training_completion" in event for event in events)


def test_delivery_rechecks_locked_exercise_identity_not_only_movement_family():
    plan = _plan(PROFILE)
    excluded = plan.sessions[0].prescriptions[0].exercise_id
    with pytest.raises(TrainingRuntimeError, match="active training constraint"):
        validate_training_plan_constraints(
            plan, PROFILE, {"exercise_exclusions": (excluded,)})


def test_repeat_rebuilds_current_recovery_instead_of_replaying_stale_plan():
    fresh = _plan({**PROFILE, "equipment": "gym"}, message="Give me a CrossFit For Time workout")
    followup = parse_workout_followup("repeat the workout")
    repeated = apply_followup(
        followup=followup, previous=state_for(fresh), recommendation_blueprint_id="repeat-test",
        facts={**PROFILE, "equipment": "gym", "recoveryFeel": "poor"})
    assert repeated != fresh
    assert all(item.sets <= 1 and item.target_rpe <= 6 for item in repeated.sessions[0].prescriptions)
    assert all(session.mixed_modal is None for session in repeated.sessions)


def test_real_chat_repeat_uses_current_recovery(chat_client):
    user_id = store.get_or_create_user("crossfit-repeat-recovery@example.com")
    profile = {**PROFILE, "equipment": "gym"}
    store.save_profile(user_id, profile)
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    conversation_id = "crossfit-repeat-recovery"
    first = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit For Time workout", "lang": "en",
        "conversation_id": conversation_id}))
    fresh = next(event["training_completion"] for event in first if "training_completion" in event)
    assert fresh["sessions"][0]["mixed_modal"]["format"] == "for_time"
    store.save_profile(user_id, {**profile, "recoveryFeel": "poor"})
    store.add_account_training_constraints(user_id, ["vertical_push"])
    second = _events(chat_client.post("/chat", json={
        "message": "repeat the workout", "lang": "en", "conversation_id": conversation_id}))
    assert second[-1] == {"done": True}
    recovery_plan = next(event["training_completion"] for event in second if "training_completion" in event)
    assert recovery_plan["sessions"][0]["mixed_modal"]["format"] == "intervals"
    assert sum(item["prescribed_sets"] for item in recovery_plan["sessions"][0]["exercises"]) < sum(
        item["prescribed_sets"] for item in fresh["sessions"][0]["exercises"])
    assert not any(item["exercise_id"] in {"dumbbell.overhead_press", "dumbbell.seated_press"}
                   for item in recovery_plan["sessions"][0]["exercises"])


@pytest.mark.parametrize("format_name", tuple(SessionFormat))
def test_timed_doses_fit_and_duration_has_one_authority(format_name):
    profile = {**PROFILE, "equipment": "gym"}
    plan = _plan(profile, message=f"Give me a CrossFit {format_name.value.replace('_', ' ')} workout")
    session = plan.sessions[0]
    assert session.estimated_duration_minutes == session.mixed_modal.time_cap_minutes
    delivered = renderer.render_delivery(plan, load_exercise_library(), (), "en")
    assert f"Session 1 · {session.mixed_modal.time_cap_minutes} min" in delivered
    if format_name in {SessionFormat.EMOM, SessionFormat.INTERVALS}:
        work_seconds = session.mixed_modal.work_seconds or 60
        for item in session.prescriptions:
            tempo_seconds = sum(int(part) for part in item.tempo.split("-"))
            assert item.rep_max * tempo_seconds <= work_seconds


def test_existing_impossible_timed_dose_is_rejected_before_delivery():
    plan = build_training_plan(recommendation_blueprint_id="unsafe-timing-test", facts=PROFILE,
                               mixed_modal=SessionFormat.AMRAP)
    request = parse_mixed_modal_request("Build an EMOM workout")
    with pytest.raises(MixedModalPlanningError, match="timed work window"):
        structure_mixed_modal_plan(plan, request=request, facts=PROFILE,
                                   library=load_exercise_library())


def test_knee_limitation_scales_knee_dominant_volume_without_banning_low_risk_work():
    baseline = _plan(PROFILE)
    limited_profile = {**PROFILE, "injuries": "knee limitation"}
    limited = _plan(limited_profile, message="Give me a CrossFit workout with high-rep squats")
    base_squat = next(item for item in baseline.sessions[0].prescriptions
                      if item.movement_pattern is MovementPattern.SQUAT)
    knee_squat = next(item for item in limited.sessions[0].prescriptions
                      if item.movement_pattern is MovementPattern.SQUAT)
    assert knee_squat.sets * knee_squat.rep_max < base_squat.sets * base_squat.rep_max
    assert any(item.movement_pattern is MovementPattern.MONOSTRUCTURAL
               for item in limited.sessions[0].prescriptions)
    for baseline_item, limited_item in zip(baseline.sessions[0].prescriptions,
                                           limited.sessions[0].prescriptions):
        if limited_item.movement_pattern not in {MovementPattern.SQUAT, MovementPattern.LUNGE}:
            assert limited_item.rep_max == baseline_item.rep_max


def test_negated_knee_limitation_does_not_change_squat_dose():
    baseline = _plan(PROFILE)
    clear = _plan({**PROFILE, "injuries": "no knee pain"})
    assert [item.rep_max for item in clear.sessions[0].prescriptions] == [
        item.rep_max for item in baseline.sessions[0].prescriptions]


@pytest.mark.parametrize("wording", (
    "knee limitation", "knee pain", "my knee hurts", "avoid stressing my knee",
    "проблем с коляното", "болка в коляното", "боли ме коляното", "ограничение в коляното",
))
def test_current_and_saved_knee_wording_share_bounded_movement_caution(wording):
    expected = frozenset({MovementPattern.SQUAT, MovementPattern.LUNGE})
    assert knee_load_limited_patterns(message=wording) == expected
    assert knee_load_limited_patterns(profile={"healthNotes": wording}) == expected
    assert knee_load_limited_patterns(profile={"injuries": wording}) == expected


@pytest.mark.parametrize(("message", "lang"), (
    ("Give me a CrossFit workout with high-rep squats; my knee hurts", "en"),
    ("Дай ми кросфит тренировка с много клекове; боли ме коляното", "bg"),
))
def test_current_turn_knee_limitation_scales_squat_without_banning_low_risk_work(
        chat_client, message, lang):
    events = _events(chat_client.post("/chat", json={
        "message": message, "lang": lang, "profile": PROFILE}))
    completion = next((event["training_completion"] for event in events
                       if "training_completion" in event), None)
    assert completion is not None, events
    exercises = completion["sessions"][0]["exercises"]
    assert any(load_exercise_library().require(item["exercise_id"]).movement_pattern
               is MovementPattern.SQUAT and item["rep_max"] <= 8 for item in exercises)
    assert any(load_exercise_library().require(item["exercise_id"]).movement_pattern
               is MovementPattern.MONOSTRUCTURAL for item in exercises)


def test_newly_saved_bulgarian_knee_limitation_revalidates_repeat(chat_client):
    user_id = store.get_or_create_user("crossfit-knee-repeat@example.com")
    profile = {**PROFILE, "equipment": "gym"}
    store.save_profile(user_id, profile)
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    conversation_id = "crossfit-knee-repeat"
    first = _events(chat_client.post("/chat", json={
        "message": "Дай ми кросфит тренировка", "lang": "bg", "conversation_id": conversation_id}))
    baseline = next(event["training_completion"] for event in first if "training_completion" in event)
    store.save_profile(user_id, {**profile, "healthNotes": "Болка в коляното"})
    second = _events(chat_client.post("/chat", json={
        "message": "повтори тренировката", "lang": "bg", "conversation_id": conversation_id}))
    repeated = next(event["training_completion"] for event in second if "training_completion" in event)
    def squat_dose(result):
        return max(item["rep_max"] for item in result["sessions"][0]["exercises"]
                   if load_exercise_library().require(item["exercise_id"]).movement_pattern
                   is MovementPattern.SQUAT)
    assert squat_dose(repeated) < squat_dose(baseline)


@pytest.mark.parametrize(("level", "followup"), (
    ("beginner", "Make this WOD harder"),
    ("intermediate", "Make this WOD easier"),
))
def test_newly_saved_knee_limitation_revalidates_difficulty_followup(
        chat_client, level, followup):
    user_id = store.get_or_create_user("crossfit-knee-" + level + "@example.com")
    profile = {**PROFILE, "level": level, "equipment": "gym"}
    store.save_profile(user_id, profile)
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    conversation_id = "crossfit-knee-" + level
    first = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit workout", "lang": "en", "conversation_id": conversation_id}))
    assert any("training_completion" in event for event in first)
    store.save_profile(user_id, {**profile, "injuries": "knee pain"})
    second = _events(chat_client.post("/chat", json={
        "message": followup, "lang": "en", "conversation_id": conversation_id}))
    assert second[-1] == {"done": True}
    revised = next((event["training_completion"] for event in second
                    if "training_completion" in event), None)
    assert revised is not None, second
    assert all(item["rep_max"] <= 8 for session in revised["sessions"]
               for item in session["exercises"]
               if load_exercise_library().require(item["exercise_id"]).movement_pattern
               in {MovementPattern.SQUAT, MovementPattern.LUNGE})


@pytest.mark.parametrize("message", (
    "Don't give me EMOM", "No EMOM", "without CrossFit or AMRAP",
    "Neither WOD nor EMOM", "Не искам да правя кросфит или EMOM",
    "Не искам кросфит, нито EMOM", "Без AMRAP и EMOM",
))
def test_clause_wide_negation_suppresses_mixed_modal_intent(message):
    assert parse_mixed_modal_request(message) is None


@pytest.mark.parametrize(("message", "expected"), (
    ("I don't want AMRAP; give me intervals", SessionFormat.INTERVALS),
    ("No EMOM, give me an AMRAP", SessionFormat.AMRAP),
    ("Не искам AMRAP, искам EMOM", SessionFormat.EMOM),
    ("Не искам кросфит, искам интервали", SessionFormat.INTERVALS),
))
def test_affirmative_clause_after_negation_selects_requested_format(message, expected):
    assert parse_mixed_modal_request(message).format is expected


@pytest.mark.parametrize("message", (
    "Направи ми тренировка за днес", "Направи ми хранителен план",
    "Make me a strength workout", "Build my nutrition plan",
))
def test_plain_new_requests_do_not_become_contextual_followups(message):
    assert parse_workout_followup(message) is None


def test_plan_followup_requires_training_context_and_does_not_steal_nutrition():
    previous = state_for(_plan(PROFILE))
    assert parse_workout_followup("Increase this plan's intensity", previous=previous).operation.value == (
        "increase_difficulty")
    assert parse_workout_followup("Increase the session timeout", previous=previous) is None
    assert parse_workout_followup("Increase my nutrition plan calories", previous=previous) is None
    assert parse_workout_followup("Change my meal plan", previous=previous) is None


@pytest.mark.parametrize("message", (
    "Give me a strength workout, not CrossFit or EMOM",
    "Give me strength training, no EMOM",
    "I don't want an AMRAP, give me a strength workout",
))
def test_negated_crossfit_format_does_not_activate_mixed_modal(message):
    assert parse_mixed_modal_request(message) is None


@pytest.mark.parametrize(("message", "operation"), (
    ("Push this session harder", "increase_difficulty"),
    ("Increase the volume", "increase_difficulty"),
    ("Scale this up", "increase_difficulty"),
    ("harder please", "increase_difficulty"),
    ("make it nastier", "increase_difficulty"),
    ("bump the workload", "increase_difficulty"),
    ("Увеличи обема", "increase_difficulty"),
    ("По-трудно, моля", "increase_difficulty"),
    ("Натоварването нагоре", "increase_difficulty"),
    ("Scale this down", "decrease_difficulty"),
    ("Намали обема", "decrease_difficulty"),
    ("more reps please", "increase_difficulty"),
    ("Give me more volume", "increase_difficulty"),
    ("higher workload", "increase_difficulty"),
    ("less volume please", "decrease_difficulty"),
    ("по-голям обем", "increase_difficulty"),
    ("по-малко повторения", "decrease_difficulty"),
    ("Don't increase the volume", "unsupported_change"),
    ("Change the volume", "unsupported_change"),
))
def test_active_workout_shorthand_is_typed_without_repeating_workout(message, operation):
    previous = state_for(_plan(PROFILE))
    assert parse_workout_followup(message, previous=previous).operation.value == operation
    assert parse_workout_followup(message) is None


@pytest.mark.parametrize("message", (
    "No CrossFit, EMOM or AMRAP; give me normal strength",
    "No CrossFit, EMOM nor AMRAP; give me normal strength",
    "I don't want CrossFit, EMOM or AMRAP; give me strength",
    "I don’t want EMOM; give me strength",
    "No CrossFit，EMOM or AMRAP；give me strength",
    "Without CrossFit/EMOM/AMRAP, give me strength",
    "Neither CrossFit nor EMOM, give me strength",
    "Не искам кросфит, EMOM или AMRAP; дай ми силова тренировка",
    "Не искам кросфит，EMOM или AMRAP；дай ми силова тренировка",
    "Без кросфит, EMOM или AMRAP; дай ми силова тренировка",
    "Нито кросфит, нито EMOM, нито AMRAP; дай ми силова тренировка",
    "Не кросфит или EMOM; дай ми силова тренировка",
))
def test_coordinated_negation_never_activates_mixed_modal(message):
    assert parse_mixed_modal_request(message) is None


@pytest.mark.parametrize(("message", "expected"), (
    ("I don't want AMRAP; give me EMOM", SessionFormat.EMOM),
    ("I don’t want AMRAP, give me EMOM", SessionFormat.EMOM),
    ("No CrossFit, EMOM or AMRAP; give me intervals", SessionFormat.INTERVALS),
    ("Не искам AMRAP, искам EMOM", SessionFormat.EMOM),
    ("Нито EMOM, нито AMRAP; дай ми интервали", SessionFormat.INTERVALS),
))
def test_genuine_affirmative_clause_resets_negation(message, expected):
    assert parse_mixed_modal_request(message).format is expected


@pytest.mark.parametrize("wording", (
    "knee limitation", "knee pain", "knee problem", "my knee hurts",
    "protect my knee", "avoid stressing my knee", "проблем с коляното",
    "болка в коляното", "боли ме коляното", "пази ми коляното",
    "ограничение в коляното", "не натоварвай коляното",
))
def test_explicit_knee_caution_variants_are_functional_not_hard_exclusions(wording):
    assert knee_load_limited_patterns(message=wording) == frozenset({
        MovementPattern.SQUAT, MovementPattern.LUNGE})


@pytest.mark.parametrize("message", (
    "Push this session harder", "Increase the volume", "Scale this up",
    "harder please", "make it nastier", "bump the workload",
    "Увеличи обема", "По-трудно, моля", "Промени натоварването",
))
def test_active_workout_mutation_never_streams_forbidden_model_prescription(
        chat_client, monkeypatch, message):
    user_id = store.get_or_create_user("crossfit-shorthand-adversarial@example.com")
    store.save_profile(user_id, {**PROFILE, "equipment": "gym"})
    store.add_account_training_constraints(user_id, ["vertical_push"])
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    conversation_id = "crossfit-shorthand-adversarial"
    first = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit workout", "lang": "en", "conversation_id": conversation_id}))
    assert any("training_completion" in event for event in first)

    def adversarial_model(**kwargs):
        if kwargs.get("stream"):
            return [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                content="Do overhead press, push press, thruster and HSPU."))])]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"explanations": []})))])

    monkeypatch.setattr(appmod.client.chat.completions, "create", adversarial_model)
    events = _events(chat_client.post("/chat", json={
        "message": message, "lang": "en", "conversation_id": conversation_id}))
    assert events[-1] == {"done": True}
    assert all(not any(forbidden in event.get("t", "").lower() for forbidden in (
        "overhead press", "push press", "thruster", "hspu")) for event in events)


def test_current_message_knee_caution_lifecycle_is_durable_and_retirable(chat_client):
    user_id = store.get_or_create_user("crossfit-knee-lifecycle@example.com")
    store.save_profile(user_id, {**PROFILE, "equipment": "gym"})
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    conversation_id = "crossfit-knee-lifecycle"

    def send(message):
        events = _events(chat_client.post("/chat", json={
            "message": message, "lang": "en", "conversation_id": conversation_id}))
        assert events[-1] == {"done": True}
        return events

    def squat_reps(events):
        completion = next(event["training_completion"] for event in events if "training_completion" in event)
        return max(item["rep_max"] for session in completion["sessions"]
                   for item in session["exercises"]
                   if load_exercise_library().require(item["exercise_id"]).movement_pattern
                   is MovementPattern.SQUAT)

    assert squat_reps(send("Give me a CrossFit workout; protect my knee")) <= 8
    assert squat_reps(send("repeat the workout")) <= 8
    harder = send("Push this session harder")
    if any("training_completion" in event for event in harder):
        assert squat_reps(harder) <= 8
    assert squat_reps(send("Give me a CrossFit EMOM workout")) <= 8
    assert knee_load_limited_patterns(store.get_profile(user_id))
    send("My knee is fine now; remove my knee caution")
    assert not knee_load_limited_patterns(store.get_profile(user_id))
    assert squat_reps(send("Give me a CrossFit workout")) > 8


def test_knee_caution_persistence_does_not_copy_account_exclusion_into_profile(chat_client):
    user_id = store.get_or_create_user("crossfit-knee-profile-integrity@example.com")
    store.save_profile(user_id, {**PROFILE, "equipment": "gym", "frequency": "3"})
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    first = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit workout", "lang": "en",
        "conversation_id": "crossfit-knee-profile-integrity"}))
    assert any("training_completion" in event for event in first)
    store.add_account_training_constraints(user_id, ["vertical_push"])
    assert "healthRestrictions" not in store.get_profile(user_id)
    events = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit workout; protect my knee",
        "lang": "en", "conversation_id": "crossfit-knee-profile-integrity"}))
    assert any("training_completion" in event for event in events)
    saved = store.get_profile(user_id)
    assert saved["frequency"] == "3"
    assert saved["healthRestrictions"] == ["training_load_caution:knee:active"]
    assert not any("overhead" in str(item).lower() for item in saved["healthRestrictions"])


def test_generic_stream_boundary_blocks_mutation_even_if_structured_classifier_misses(
        chat_client, monkeypatch):
    user_id = store.get_or_create_user("crossfit-generic-boundary@example.com")
    store.save_profile(user_id, {**PROFILE, "equipment": "gym"})
    store.add_account_training_constraints(user_id, ["vertical_push"])
    chat_client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    conversation_id = "crossfit-generic-boundary"
    first = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit workout", "lang": "en", "conversation_id": conversation_id}))
    assert any("training_completion" in event for event in first)
    monkeypatch.setattr(appmod, "parse_workout_followup", lambda *args, **kwargs: None)

    def forbidden_model(**kwargs):
        if kwargs.get("stream"):
            return [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                content="Overhead press, push press, thruster, HSPU."))])]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"explanations": []})))])

    monkeypatch.setattr(appmod.client.chat.completions, "create", forbidden_model)
    events = _events(chat_client.post("/chat", json={
        "message": "bump the workload", "lang": "en", "conversation_id": conversation_id}))
    assert events[-1] == {"done": True}
    assert not any("training_completion" in event for event in events)
    assert not any("overhead press" in event.get("t", "").lower() for event in events)


def test_anonymous_scoped_knee_caution_survives_new_format(chat_client):
    conversation_id = "crossfit-anonymous-knee-caution"
    first = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit workout; my knee hurts", "lang": "en",
        "profile": PROFILE, "conversation_id": conversation_id}))
    assert any("training_completion" in event for event in first)
    second = _events(chat_client.post("/chat", json={
        "message": "Give me a CrossFit EMOM workout", "lang": "en",
        "profile": PROFILE, "conversation_id": conversation_id}))
    completion = next(event["training_completion"] for event in second if "training_completion" in event)
    assert all(item["rep_max"] <= 8 for session in completion["sessions"]
               for item in session["exercises"]
               if load_exercise_library().require(item["exercise_id"]).movement_pattern
               in {MovementPattern.SQUAT, MovementPattern.LUNGE})
