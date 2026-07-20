"""Replayable, deterministic progression state derived from workout evidence.

The module is intentionally isolated from runtime delivery. It does not persist
state or alter progression decisions; it validates and derives the state a later
policy-aware progression stage can consume.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .progression import (
    DEFAULT_PROGRESSION_POLICY,
    ProgressionDecision,
    ProgressionDecisionType,
    ProgressionPolicy,
    WorkoutResult,
)


STATE_VERSION = "exercise-progress-state-v1"


@dataclass(frozen=True)
class ProgressionCounters:
    consecutive_successful_sessions: int = 0
    consecutive_failed_sessions: int = 0
    load_progression_stage: int = 0
    repetition_progression_stage: int = 0
    set_progression_stage: int = 0
    accumulated_progression_count: int = 0

    def __post_init__(self) -> None:
        if any(not isinstance(getattr(self, field), int) or getattr(self, field) < 0 for field in (
                "consecutive_successful_sessions", "consecutive_failed_sessions",
                "load_progression_stage", "repetition_progression_stage",
                "set_progression_stage", "accumulated_progression_count")):
            raise ValueError("progression counters must be non-negative integers")
        if self.consecutive_successful_sessions and self.consecutive_failed_sessions:
            raise ValueError("success and failure counters cannot both be active")


@dataclass(frozen=True)
class DeloadHistory:
    last_deload_workout_id: str | None = None
    last_deload_at: datetime | None = None
    progression_cycles_since_deload: int = 0

    def __post_init__(self) -> None:
        if (self.last_deload_workout_id is None) != (self.last_deload_at is None):
            raise ValueError("deload identity and timestamp must be recorded together")
        if self.last_deload_at is not None and self.last_deload_at.tzinfo is None:
            raise ValueError("deload timestamp must be timezone-aware")
        if not isinstance(self.progression_cycles_since_deload, int) or self.progression_cycles_since_deload < 0:
            raise ValueError("deload cycles must be non-negative")


@dataclass(frozen=True)
class ExerciseProgressState:
    state_version: str
    progression_policy_version: str
    originating_workout_id: str
    exercise_id: str
    exercise_version: str
    first_workout_at: datetime
    counters: ProgressionCounters
    deload_history: DeloadHistory
    weeks_on_current_exercise: int
    load_progression_eligible: bool
    deload_required: bool
    rotation_recommended: bool

    def __post_init__(self) -> None:
        if (not self.state_version or not self.progression_policy_version or not self.originating_workout_id
                or not self.exercise_id or not self.exercise_version):
            raise ValueError("exercise progress state traceability is required")
        if not isinstance(self.first_workout_at, datetime) or self.first_workout_at.tzinfo is None:
            raise ValueError("exercise progress state requires an aware first workout timestamp")
        if not isinstance(self.counters, ProgressionCounters) or not isinstance(self.deload_history, DeloadHistory):
            raise ValueError("exercise progress state requires immutable counters and deload history")
        if not isinstance(self.weeks_on_current_exercise, int) or self.weeks_on_current_exercise < 1:
            raise ValueError("weeks on current exercise must be positive")
        if not all(isinstance(value, bool) for value in (
                self.load_progression_eligible, self.deload_required, self.rotation_recommended)):
            raise ValueError("progress state flags must be boolean")


@dataclass(frozen=True)
class ProgressionEvent:
    workout_id: str
    decision: ProgressionDecision

    def __post_init__(self) -> None:
        if not self.workout_id or not isinstance(self.decision, ProgressionDecision):
            raise ValueError("progression event requires a workout and decision")


@dataclass(frozen=True)
class ProgressionHistory:
    workouts: tuple[WorkoutResult, ...]
    events: tuple[ProgressionEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.workouts, tuple) or not self.workouts:
            raise ValueError("progression history requires workout results")
        if any(not isinstance(item, WorkoutResult) for item in self.workouts):
            raise ValueError("progression history contains an invalid workout")
        times = tuple(item.completed_at for item in self.workouts)
        if any(previous >= current for previous, current in zip(times, times[1:])):
            raise ValueError("workout history must be strictly chronological")
        workout_ids = tuple(item.workout_id for item in self.workouts)
        if len(workout_ids) != len(set(workout_ids)):
            raise ValueError("progression history has duplicate workout identity")
        if not isinstance(self.events, tuple) or any(not isinstance(item, ProgressionEvent) for item in self.events):
            raise ValueError("progression history contains an invalid event")
        identities = tuple((item.workout_id, item.decision.exercise_id, item.decision.exercise_version)
                           for item in self.events)
        if len(identities) != len(set(identities)):
            raise ValueError("progression history has duplicate progression event")
        if any(item.workout_id not in workout_ids for item in self.events):
            raise ValueError("progression event references an unknown workout")


# Compatibility names point to the shared policy object; there is no second
# authority for state eligibility.
ProgressionStatePolicy = ProgressionPolicy
DEFAULT_PROGRESSION_STATE_POLICY = DEFAULT_PROGRESSION_POLICY


class ProgressionStateEngine:
    """Replay workout and progression evidence into one immutable state per exercise."""

    @classmethod
    def derive(cls, history: ProgressionHistory, *,
               policy: ProgressionPolicy = DEFAULT_PROGRESSION_STATE_POLICY) -> tuple[ExerciseProgressState, ...]:
        if not isinstance(history, ProgressionHistory) or not isinstance(policy, ProgressionPolicy):
            raise ValueError("progression state requires history and policy")
        events = {(item.workout_id, item.decision.exercise_id, item.decision.exercise_version): item.decision
                  for item in history.events}
        states: dict[tuple[str, str], ExerciseProgressState] = {}
        for workout in history.workouts:
            for performance in workout.performances:
                identity = (performance.exercise_id, performance.exercise_version)
                decision = events.get((workout.workout_id, *identity))
                states[identity] = cls._transition(
                    states.get(identity), workout, performance, decision, policy)
        return tuple(states[key] for key in sorted(states))

    @classmethod
    def _transition(cls, previous: ExerciseProgressState | None, workout: WorkoutResult, performance,
                    decision: ProgressionDecision | None,
                    policy: ProgressionPolicy) -> ExerciseProgressState:
        if decision is not None:
            cls._validate_event(decision, workout, performance, previous, policy)
        first_at = previous.first_workout_at if previous else workout.completed_at
        prior = previous.counters if previous else ProgressionCounters()
        successful = workout.completed and performance.completed and not performance.pain_reported
        counters = ProgressionCounters(
            consecutive_successful_sessions=prior.consecutive_successful_sessions + 1 if successful else 0,
            consecutive_failed_sessions=0 if successful else prior.consecutive_failed_sessions + 1,
            load_progression_stage=prior.load_progression_stage,
            repetition_progression_stage=prior.repetition_progression_stage,
            set_progression_stage=prior.set_progression_stage,
            accumulated_progression_count=prior.accumulated_progression_count,
        )
        deload = previous.deload_history if previous else DeloadHistory()
        if decision is not None:
            counters, deload = cls._apply_decision(counters, deload, decision, workout)
        elapsed_days = (workout.completed_at.date() - first_at.date()).days
        weeks = elapsed_days // 7 + 1
        return ExerciseProgressState(
            state_version=STATE_VERSION,
            progression_policy_version=policy.version,
            originating_workout_id=workout.workout_id,
            exercise_id=performance.exercise_id,
            exercise_version=performance.exercise_version,
            first_workout_at=first_at,
            counters=counters,
            deload_history=deload,
            weeks_on_current_exercise=weeks,
            load_progression_eligible=counters.consecutive_successful_sessions >= policy.required_successful_sessions_for_load,
            deload_required=deload.progression_cycles_since_deload >= policy.deload_after_progression_cycles,
            rotation_recommended=weeks >= policy.rotate_after_weeks,
        )

    @staticmethod
    def _validate_event(decision: ProgressionDecision, workout: WorkoutResult, performance,
                        previous: ExerciseProgressState | None, policy: ProgressionPolicy) -> None:
        if (decision.exercise_id, decision.exercise_version) != (performance.exercise_id, performance.exercise_version):
            raise ValueError("progression decision does not match workout performance")
        if decision.training_plan_version != workout.plan_version:
            raise ValueError("progression decision does not match workout plan version")
        if decision.policy_version != policy.version:
            raise ValueError("progression decision does not use the authoritative policy")
        if decision.decision_type in {
                ProgressionDecisionType.INCREASE_LOAD,
                ProgressionDecisionType.INCREASE_REPETITIONS,
                ProgressionDecisionType.INCREASE_SETS} and not (workout.completed and performance.completed):
            raise ValueError("progression cannot follow an incomplete workout")
        successes = (previous.counters.consecutive_successful_sessions if previous else 0) + 1
        if (decision.decision_type is ProgressionDecisionType.INCREASE_LOAD
                and successes < policy.required_successful_sessions_for_load):
            raise ValueError("load progression requires consecutive successful sessions")
        if (decision.decision_type is ProgressionDecisionType.INCREASE_SETS and previous is not None
                and previous.counters.set_progression_stage >= policy.maximum_set_progression_stage):
            raise ValueError("set progression stage is exhausted")

    @staticmethod
    def _apply_decision(counters: ProgressionCounters, deload: DeloadHistory,
                        decision: ProgressionDecision, workout: WorkoutResult) -> tuple[ProgressionCounters, DeloadHistory]:
        kind = decision.decision_type
        if kind is ProgressionDecisionType.REPLACE_EXERCISE:
            return ProgressionCounters(), deload
        if kind is ProgressionDecisionType.DELOAD:
            return ProgressionCounters(), DeloadHistory(workout.workout_id, workout.completed_at, 0)
        if kind in {ProgressionDecisionType.INCREASE_LOAD, ProgressionDecisionType.INCREASE_REPETITIONS,
                    ProgressionDecisionType.INCREASE_SETS}:
            return ProgressionCounters(
                counters.consecutive_successful_sessions,
                counters.consecutive_failed_sessions,
                counters.load_progression_stage + (kind is ProgressionDecisionType.INCREASE_LOAD),
                counters.repetition_progression_stage + (kind is ProgressionDecisionType.INCREASE_REPETITIONS),
                counters.set_progression_stage + (kind is ProgressionDecisionType.INCREASE_SETS),
                counters.accumulated_progression_count + 1,
            ), DeloadHistory(deload.last_deload_workout_id, deload.last_deload_at,
                              deload.progression_cycles_since_deload + 1)
        return counters, deload
