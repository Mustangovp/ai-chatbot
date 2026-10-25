from datetime import datetime, timezone
from copy import deepcopy

import pytest

from training_engine import (
    RecoverySnapshot,
    RecoveryState,
    advance_training_lifecycle,
    build_training_plan,
    completion_projection,
    load_exercise_library,
    workout_completion_from_payload,
)
from decimal import Decimal
from training_engine import renderer


@pytest.mark.parametrize("language", ["bg", "en"])
def test_delivery_metadata_matches_the_existing_immutable_completion_authority(language):
    plan, library = _plan(), load_exercise_library()
    metadata = renderer.render_completion_projection(plan, library, language)
    renderer.validate_completion_projection(plan, library, metadata, language)
    assert len(metadata["sessions"]) == 1


@pytest.mark.parametrize("damage", ["null", "empty", "missing_plan", "wrong_plan", "wrong_session",
    "empty_session", "wrong_exercise", "wrong_version", "wrong_sets", "boolean_sets", "extra_session", "extra_field"])
def test_invalid_delivery_metadata_cannot_replace_canonical_values(damage):
    plan, library = _plan(), load_exercise_library()
    metadata = deepcopy(renderer.render_completion_projection(plan, library, "en"))
    if damage == "null": metadata = None
    elif damage == "empty": metadata = {}
    elif damage == "missing_plan": metadata.pop("plan_id")
    elif damage == "wrong_plan": metadata["plan_id"] = "another-plan"
    elif damage == "wrong_session": metadata["sessions"][0]["session_id"] = "another-session"
    elif damage == "empty_session": metadata["sessions"] = []
    elif damage == "wrong_exercise": metadata["sessions"][0]["exercises"][0]["exercise_id"] = "bodyweight.plank"
    elif damage == "wrong_version": metadata["sessions"][0]["exercises"][0]["exercise_version"] = "99.0.0"
    elif damage == "wrong_sets": metadata["sessions"][0]["exercises"][0]["prescribed_sets"] += 1
    elif damage == "boolean_sets": metadata["sessions"][0]["exercises"][0]["prescribed_sets"] = True
    elif damage == "extra_session": metadata["sessions"].append(deepcopy(metadata["sessions"][0]))
    else: metadata["fabricated"] = "not part of the canonical projection"
    with pytest.raises(ValueError):
        renderer.validate_completion_projection(plan, library, metadata, "en")


def _plan():
    return build_training_plan(recommendation_blueprint_id="completion-contract", facts={
        "goal": "strength", "level": "intermediate", "equipment": "gym", "recoveryFeel": "fresh",
    })


def _payload(plan, *, rpe=None, rir=None):
    projection = completion_projection(plan, load_exercise_library())
    session = projection["sessions"][0]
    return {
        "workout_id": "completion-001",
        "plan_id": projection["plan_id"],
        "plan_version": projection["plan_version"],
        "session_id": session["session_id"],
        "completion_timestamp": "2026-07-20T10:00:00Z",
        "exercises": [{
            "prescription_id": exercise["prescription_id"],
            "exercise_id": exercise["exercise_id"],
            "exercise_version": exercise["exercise_version"],
            "completed_sets": exercise["prescribed_sets"],
            "completed_repetitions": exercise["rep_max"],
            **({"prescription_type": "duration", "completed_duration_seconds": exercise["duration_max_seconds"]}
               if exercise["prescription_type"] == "duration" else {}),
            "completed_load": "20",
            "completed_rpe": rpe,
            "completed_rir": rir,
        } for exercise in session["exercises"]],
    }


def test_completion_projection_is_stable_and_lifecycle_accepts_only_its_identifiers():
    plan = _plan()
    assert completion_projection(plan, load_exercise_library()) == completion_projection(plan, load_exercise_library())

    result = workout_completion_from_payload(_payload(plan, rpe="7", rir=3), plan=plan).to_workout_result()

    assert result.plan_id == plan.plan_id
    assert result.plan_version == plan.version
    assert result.completed_at == datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    assert all(item.exercise_id and item.exercise_version for item in result.performances)


def test_completion_rejects_a_display_name_or_tampered_prescription_identity():
    plan = _plan()
    payload = _payload(plan)
    payload["exercises"][0]["prescription_id"] = "reconstructed-from-display-name"

    with pytest.raises(ValueError, match="rendered blueprint"):
        workout_completion_from_payload(payload, plan=plan)


def test_completion_without_optional_effort_replays_deterministically_without_claiming_progression():
    plan = _plan()
    workout = workout_completion_from_payload(_payload(plan), plan=plan).to_workout_result()
    recovery = RecoverySnapshot(RecoveryState.NORMALLY_RECOVERED, Decimal("30"), "recovery-policy-v1")

    first = advance_training_lifecycle(plan=plan, workouts=(workout,), recovery=recovery)
    second = advance_training_lifecycle(plan=plan, workouts=(workout,), recovery=recovery)

    assert first == second
    assert {item.reason for item in first.progression.decisions} == {"effort_not_recorded"}
    assert first.revision.revised_plan.parent_plan_id == plan.plan_id


@pytest.mark.parametrize(("rpe", "rir"), (("6", None), (None, 4)))
def test_standard_lifecycle_keeps_single_effort_signal_conservative(rpe, rir):
    plan = _plan()
    workout = workout_completion_from_payload(_payload(plan, rpe=rpe, rir=rir), plan=plan).to_workout_result()
    recovery = RecoverySnapshot(RecoveryState.NORMALLY_RECOVERED, Decimal("30"), "recovery-policy-v1")

    result = advance_training_lifecycle(plan=plan, workouts=(workout,), recovery=recovery)

    assert {item.reason for item in result.progression.decisions} == {"effort_not_recorded"}
