"""Runtime adapter and renderer contracts before `/chat` wiring."""
from __future__ import annotations

import json

import pytest

from training_engine import (
    MovementPattern,
    TrainingRuntimeError,
    TrainingSplit,
    build_training_plan,
    load_exercise_library,
)
from training_engine import renderer


_PROFILE = {
    "goal": "strength",
    "level": "intermediate",
    "equipment": "bodyweight, dumbbells, bench",
    "recoveryFeel": "fresh",
}


def test_runtime_adapter_builds_a_deterministic_traceable_training_plan():
    first = build_training_plan(recommendation_blueprint_id="rec-runtime", facts=_PROFILE)
    second = build_training_plan(recommendation_blueprint_id="rec-runtime", facts=_PROFILE)

    assert first == second
    assert first.selection_blueprint_id.startswith("selection:rec-runtime:")
    assert all(item.exercise_id and item.exercise_version
               for item in first.sessions[0].prescriptions)
    rendered = renderer.render_delivery(first, load_exercise_library(), (), "en")
    assert "Goblet Squat" in rendered
    assert "RPE" in rendered and "tempo" in rendered


def test_runtime_adapter_fails_closed_for_unsupported_or_safety_constrained_profile():
    with pytest.raises(TrainingRuntimeError, match="unsupported equipment"):
        build_training_plan(recommendation_blueprint_id="rec-runtime", facts={**_PROFILE, "equipment": "office"})
    with pytest.raises(TrainingRuntimeError, match="safety constraints"):
        build_training_plan(recommendation_blueprint_id="rec-runtime", facts={**_PROFILE, "injuries": "knee pain"})


def test_renderer_accepts_only_explanatory_llm_json_and_never_changes_plan_values():
    plan = build_training_plan(recommendation_blueprint_id="rec-runtime", facts=_PROFILE)
    prompt = renderer.render_prompt(plan, "en")
    assert "Do not add, remove, reorder, or change exercises" in prompt
    assert "one to three non-empty explanation strings" in prompt
    assert renderer.verified_explanations(json.dumps({"explanations": ["Keep each rep controlled."]})) == (
        "Keep each rep controlled.",
    )
    assert "Why this workout:" in renderer.default_explanations(plan, "en")[0]
    with pytest.raises(ValueError, match="response contract"):
        renderer.verified_explanations(json.dumps({"explanations": [], "plan": "modified"}))


@pytest.mark.parametrize(("requested_split", "expected_sessions"), (
    ("full_body", ((
        MovementPattern.SQUAT, MovementPattern.HORIZONTAL_PUSH, MovementPattern.HORIZONTAL_PULL,
        MovementPattern.HINGE, MovementPattern.CORE_ANTI_EXTENSION,
    ),) * 2),
    ("upper_lower", (
        (MovementPattern.HORIZONTAL_PUSH, MovementPattern.HORIZONTAL_PULL, MovementPattern.VERTICAL_PUSH),
        (MovementPattern.SQUAT, MovementPattern.LUNGE, MovementPattern.HINGE,
         MovementPattern.CORE_ANTI_EXTENSION),
    )),
    ("push_pull_legs", (
        (MovementPattern.HORIZONTAL_PUSH, MovementPattern.VERTICAL_PUSH),
        (MovementPattern.HORIZONTAL_PULL,),
        (MovementPattern.SQUAT, MovementPattern.LUNGE, MovementPattern.HINGE,
         MovementPattern.CORE_ANTI_EXTENSION),
    )),
))
def test_runtime_constructs_the_explicit_requested_split_deterministically(
        requested_split, expected_sessions):
    facts = {**_PROFILE, "equipment": "gym", "training_split": requested_split}
    first = build_training_plan(recommendation_blueprint_id="rec-split", facts=facts)
    second = build_training_plan(recommendation_blueprint_id="rec-split", facts=facts)

    assert first == second
    assert first.training_split is TrainingSplit(requested_split)
    assert tuple(tuple(item.movement_pattern for item in session.prescriptions)
                 for session in first.sessions) == expected_sessions
    assert all(item.exercise_id and item.exercise_version and item.selection_policy_version
               and item.construction_policy_version for session in first.sessions
               for item in session.prescriptions)


def test_home_beginner_profile_uses_the_bodyweight_push_and_horizontal_pull():
    plan = build_training_plan(
        recommendation_blueprint_id="rec-home", facts={
            "goal": "strength", "level": "beginner", "equipment": "home",
            "recoveryFeel": "fresh",
        })

    exercise_ids = {item.exercise_id for item in plan.sessions[0].prescriptions}
    assert {"bodyweight.wall_push_up", "bodyweight.table_row"}.issubset(exercise_ids)
    exercise = load_exercise_library().require("bodyweight.table_row")
    assert exercise.movement_pattern is MovementPattern.HORIZONTAL_PULL
    assert exercise.safety_notes and exercise.progression.next_exercise_ids


def test_split_support_rejects_unknown_split_without_falling_back_to_full_body():
    with pytest.raises(TrainingRuntimeError, match="unsupported training split"):
        build_training_plan(recommendation_blueprint_id="rec-split", facts={
            **_PROFILE, "training_split": "bro split",
        })
