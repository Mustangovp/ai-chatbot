"""Progression State Engine replay and transition coverage."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from training_engine import (
    ExercisePerformance,
    ProgressionDecision,
    ProgressionDecisionType,
    ProgressionEvent,
    ProgressionHistory,
    ProgressionStateEngine,
    ProgressionStatePolicy,
    WorkoutResult,
    build_training_plan,
)


def _plan():
    return build_training_plan(recommendation_blueprint_id="rec-state", facts={
        "goal": "strength", "level": "intermediate", "equipment": "gym", "recoveryFeel": "fresh",
    })


def _workout(plan, *, index, completed=True, pain=False):
    performance = plan.sessions[0].prescriptions[0]
    return WorkoutResult(
        workout_id=f"workout-{index}", plan_id=plan.plan_id, plan_version=plan.version,
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index * 7),
        completed=completed,
        performances=(ExercisePerformance(
            performance.exercise_id, performance.exercise_version,
            performance.sets if completed else 0, performance.rep_max if completed else 0,
            Decimal("7"), 3, Decimal("20"), completed, pain,
        ),),
    )


def _decision(plan, workout, kind, *, replacement=False):
    performance = workout.performances[0]
    replacement_id = "bodyweight.incline_push_up" if replacement else None
    return ProgressionDecision(
        decision_id=f"decision-{workout.workout_id}-{kind.value}", decision_type=kind,
        reason="test", policy_version="progression-policy-v2",
        exercise_id=performance.exercise_id, exercise_version=performance.exercise_version,
        training_plan_version=plan.version,
        load_delta_kg=Decimal("2.5") if kind is ProgressionDecisionType.INCREASE_LOAD else None,
        repetition_delta=1 if kind is ProgressionDecisionType.INCREASE_REPETITIONS else None,
        set_delta=1 if kind is ProgressionDecisionType.INCREASE_SETS else None,
        replacement_exercise_id=replacement_id,
        replacement_exercise_version="1.0.0" if replacement else None,
    )


def test_state_replay_tracks_consecutive_success_and_failure_with_traceability():
    plan = _plan()
    first, second, failed = _workout(plan, index=0), _workout(plan, index=1), _workout(plan, index=2, completed=False)
    state = ProgressionStateEngine.derive(ProgressionHistory((first, second, failed)))[0]

    assert state.originating_workout_id == failed.workout_id
    assert state.exercise_id == failed.performances[0].exercise_id
    assert state.counters.consecutive_successful_sessions == 0
    assert state.counters.consecutive_failed_sessions == 1
    assert state.progression_policy_version == "progression-policy-v2"


def test_load_progression_requires_configured_consecutive_successes():
    plan = _plan()
    first, second = _workout(plan, index=0), _workout(plan, index=1)
    event = ProgressionEvent(second.workout_id, _decision(plan, second, ProgressionDecisionType.INCREASE_LOAD))
    state = ProgressionStateEngine.derive(ProgressionHistory((first, second), (event,)))[0]

    assert state.counters.load_progression_stage == 1
    assert state.load_progression_eligible is True
    with pytest.raises(ValueError, match="consecutive successful"):
        ProgressionStateEngine.derive(ProgressionHistory((first,), (
            ProgressionEvent(first.workout_id, _decision(plan, first, ProgressionDecisionType.INCREASE_LOAD)),)),
            policy=ProgressionStatePolicy(required_successful_sessions_for_load=2))


def test_deload_cycles_and_rotation_are_deterministically_reported():
    plan = _plan()
    first, second, third = _workout(plan, index=0), _workout(plan, index=1), _workout(plan, index=8)
    events = (
        ProgressionEvent(second.workout_id, _decision(plan, second, ProgressionDecisionType.INCREASE_LOAD)),
        ProgressionEvent(third.workout_id, _decision(plan, third, ProgressionDecisionType.INCREASE_REPETITIONS)),
    )
    policy = ProgressionStatePolicy(required_successful_sessions_for_load=1,
                                    deload_after_progression_cycles=2, rotate_after_weeks=8)
    state = ProgressionStateEngine.derive(ProgressionHistory((first, second, third), events), policy=policy)[0]

    assert state.deload_required is True
    assert state.rotation_recommended is True
    deload = ProgressionEvent(third.workout_id, _decision(plan, third, ProgressionDecisionType.DELOAD))
    state_after_deload = ProgressionStateEngine.derive(ProgressionHistory((first, second, third), (events[0], deload)), policy=policy)[0]
    assert state_after_deload.deload_history.last_deload_workout_id == third.workout_id
    assert state_after_deload.deload_history.progression_cycles_since_deload == 0


def test_replacement_resets_progression_counters():
    plan = _plan()
    first, second = _workout(plan, index=0), _workout(plan, index=1, pain=True)
    history = ProgressionHistory((first, second), (
        ProgressionEvent(first.workout_id, _decision(plan, first, ProgressionDecisionType.INCREASE_REPETITIONS)),
        ProgressionEvent(second.workout_id, _decision(plan, second, ProgressionDecisionType.REPLACE_EXERCISE, replacement=True)),
    ))
    state = ProgressionStateEngine.derive(history, policy=ProgressionStatePolicy(required_successful_sessions_for_load=1))[0]

    assert state.counters.accumulated_progression_count == 0
    assert state.counters.consecutive_successful_sessions == 0
    assert state.counters.consecutive_failed_sessions == 0


def test_state_history_rejects_duplicate_events_and_non_sequential_workouts():
    plan = _plan()
    first, second = _workout(plan, index=0), _workout(plan, index=1)
    event = ProgressionEvent(first.workout_id, _decision(plan, first, ProgressionDecisionType.INCREASE_REPETITIONS))
    with pytest.raises(ValueError, match="duplicate progression event"):
        ProgressionHistory((first,), (event, event))
    with pytest.raises(ValueError, match="strictly chronological"):
        ProgressionHistory((second, first))
