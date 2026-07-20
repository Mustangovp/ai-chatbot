"""Deterministic runtime adapter for completed training evidence.

The adapter owns sequencing only: replay state, decide progression with the
same policy, then produce one immutable next-plan revision. It has no prompt,
storage, renderer, or HTTP dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Mapping

from .construction import TrainingPlanBlueprintV2
from .completion import workout_completion_from_payload
from .lifecycle import PlanRevision, TrainingLifecycleEvent, TrainingLifecycleOrchestrator
from .progression import (
    DEFAULT_PROGRESSION_POLICY,
    ExercisePerformance,
    ProgressionBlueprint,
    ProgressionDecision,
    ProgressionEngine,
    ProgressionPolicy,
    RecoverySnapshot,
    RecoveryState,
    WorkoutResult,
)
from .progression_state import (
    ExerciseProgressState,
    ProgressionEvent,
    ProgressionHistory,
    ProgressionStateEngine,
)


@dataclass(frozen=True)
class LifecycleRuntimeResult:
    """One replayable lifecycle result; every field is immutable evidence."""

    progression: ProgressionBlueprint
    progress_states: tuple[ExerciseProgressState, ...]
    revision: PlanRevision
    history: ProgressionHistory


def advance_training_lifecycle(*, plan: TrainingPlanBlueprintV2,
                               workouts: tuple[WorkoutResult, ...],
                               recovery: RecoverySnapshot,
                               policy: ProgressionPolicy = DEFAULT_PROGRESSION_POLICY) -> LifecycleRuntimeResult:
    """Replay completed parent-plan workouts and deterministically revise it once.

    Each historic workout is evaluated in chronological order so the decision
    emitted for it is immediately validated by the same policy in the state
    engine. A disagreement is a hard failure, never a partial revision.
    """
    if not isinstance(plan, TrainingPlanBlueprintV2) or not isinstance(recovery, RecoverySnapshot):
        raise ValueError("lifecycle runtime requires a plan and recovery snapshot")
    if not isinstance(workouts, tuple) or not workouts:
        raise ValueError("lifecycle runtime requires completed workout evidence")
    if not isinstance(policy, ProgressionPolicy):
        raise ValueError("lifecycle runtime requires the authoritative progression policy")
    if any((item.plan_id, item.plan_version) != (plan.plan_id, plan.version) for item in workouts):
        raise ValueError("workout evidence does not belong to the parent training plan")
    if any(not item.completed for item in workouts):
        raise ValueError("lifecycle runtime accepts completed workouts only")

    events: tuple[ProgressionEvent, ...] = ()
    latest_progression = None
    latest_states: tuple[ExerciseProgressState, ...] = ()
    for index, workout in enumerate(workouts):
        prior_history = ProgressionHistory(workouts[:index], events) if index else None
        prior_states = ProgressionStateEngine.derive(prior_history, policy=policy) if prior_history else ()
        prior_decisions = tuple(event.decision for event in events)
        latest_progression = ProgressionEngine.evaluate(
            plan, workouts[:index + 1], recovery,
            progression_history=prior_decisions,
            progress_states=prior_states,
            policy=policy,
        )
        events = events + tuple(ProgressionEvent(workout.workout_id, decision)
                                for decision in latest_progression.decisions)
        replay = ProgressionHistory(workouts[:index + 1], events)
        latest_states = ProgressionStateEngine.derive(replay, policy=policy)

    assert latest_progression is not None
    history = ProgressionHistory(workouts, events)
    latest_workout = workouts[-1]
    event = TrainingLifecycleEvent(
        event_id=_event_id(latest_workout, latest_progression, latest_states, policy),
        workout=latest_workout,
        progression=latest_progression,
        progress_states=latest_states,
        state_policy_version=policy.version,
    )
    revision = TrainingLifecycleOrchestrator.revise(plan, event)
    return LifecycleRuntimeResult(latest_progression, latest_states, revision, history)


def workout_result_from_payload(payload: Mapping[str, Any], *, plan: TrainingPlanBlueprintV2) -> WorkoutResult:
    """Accept only the immutable browser completion contract for lifecycle replay."""
    return workout_completion_from_payload(payload, plan=plan).to_workout_result()


def recovery_from_payload(payload: Mapping[str, Any]) -> RecoverySnapshot:
    if not isinstance(payload, Mapping):
        raise ValueError("recovery payload must be an object")
    try:
        state = RecoveryState(str(payload.get("state", "")).strip().lower())
    except ValueError as error:
        raise ValueError("recovery payload requires a supported state") from error
    return RecoverySnapshot(state, Decimal(str(payload.get("accumulated_fatigue"))),
                            _required_text(payload.get("source_version"), "source_version"))


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _event_id(workout: WorkoutResult, progression: ProgressionBlueprint,
              states: tuple[ExerciseProgressState, ...], policy: ProgressionPolicy) -> str:
    source = {
        "workout": workout.workout_id,
        "progression": progression.blueprint_id,
        "states": [(item.exercise_id, item.originating_workout_id) for item in states],
        "policy": policy.version,
    }
    return "lifecycle_event_" + sha256(json.dumps(source, sort_keys=True).encode("utf-8")).hexdigest()[:24]
