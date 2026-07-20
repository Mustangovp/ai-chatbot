"""Pure, deterministic long-term progression for immutable training plans.

This module consumes completed workout evidence. It neither creates workouts nor
talks to the runtime, storage, renderer, or an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from typing import Iterable, TYPE_CHECKING

from .construction import ExercisePrescription, TrainingPlanBlueprintV2
from .registry import ExerciseLibrary, load_exercise_library

if TYPE_CHECKING:
    from .progression_state import ExerciseProgressState


class RecoveryState(str, Enum):
    FULLY_RECOVERED = "fully_recovered"
    NORMALLY_RECOVERED = "normally_recovered"
    FATIGUED = "fatigued"
    OVERREACHED = "overreached"


class ProgressionDecisionType(str, Enum):
    INCREASE_LOAD = "increase_load"
    INCREASE_REPETITIONS = "increase_repetitions"
    INCREASE_SETS = "increase_sets"
    MAINTAIN = "maintain"
    DELOAD = "deload"
    REPLACE_EXERCISE = "replace_exercise"


@dataclass(frozen=True)
class ExercisePerformance:
    exercise_id: str
    exercise_version: str
    completed_sets: int
    completed_repetitions: int
    achieved_rpe: Decimal | None
    achieved_rir: int | None
    load_kg: Decimal | None
    completed: bool
    pain_reported: bool = False

    def __post_init__(self) -> None:
        if not self.exercise_id or not self.exercise_version:
            raise ValueError("exercise performance requires traceable exercise identity")
        if not isinstance(self.completed_sets, int) or self.completed_sets < 0:
            raise ValueError("completed sets must be non-negative")
        if not isinstance(self.completed_repetitions, int) or self.completed_repetitions < 0:
            raise ValueError("completed repetitions must be non-negative")
        if self.achieved_rpe is not None:
            rpe = Decimal(str(self.achieved_rpe))
            if not Decimal("1") <= rpe <= Decimal("10"):
                raise ValueError("achieved RPE must be between one and ten")
            object.__setattr__(self, "achieved_rpe", rpe)
        if self.achieved_rir is not None and (not isinstance(self.achieved_rir, int)
                                              or not 0 <= self.achieved_rir <= 10):
            raise ValueError("achieved RIR must be between zero and ten")
        if self.load_kg is not None:
            load = Decimal(str(self.load_kg))
            if load < 0:
                raise ValueError("load must be non-negative")
            object.__setattr__(self, "load_kg", load)
        if not isinstance(self.completed, bool) or not isinstance(self.pain_reported, bool):
            raise ValueError("completion and pain flags must be boolean")
        if self.completed and (self.completed_sets < 1 or self.completed_repetitions < 1):
            raise ValueError("completed performance requires completed work")


@dataclass(frozen=True)
class WorkoutResult:
    workout_id: str
    plan_id: str
    plan_version: str
    completed_at: datetime
    completed: bool
    performances: tuple[ExercisePerformance, ...]

    def __post_init__(self) -> None:
        if not self.workout_id or not self.plan_id or not self.plan_version:
            raise ValueError("workout result identity is required")
        if not isinstance(self.completed_at, datetime) or self.completed_at.tzinfo is None:
            raise ValueError("workout completion time must be timezone-aware")
        if not isinstance(self.completed, bool) or not isinstance(self.performances, tuple) or not self.performances:
            raise ValueError("workout result requires completion and performances")
        identities = [(item.exercise_id, item.exercise_version) for item in self.performances]
        if len(identities) != len(set(identities)):
            raise ValueError("workout result has duplicate exercise performance")


@dataclass(frozen=True)
class RecoverySnapshot:
    state: RecoveryState
    accumulated_fatigue: Decimal
    source_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.state, RecoveryState) or not self.source_version:
            raise ValueError("recovery snapshot requires typed state and source version")
        fatigue = Decimal(str(self.accumulated_fatigue))
        if not Decimal("0") <= fatigue <= Decimal("100"):
            raise ValueError("accumulated fatigue must be between zero and one hundred")
        if self.state is RecoveryState.OVERREACHED and fatigue < Decimal("60"):
            raise ValueError("overreached recovery requires high accumulated fatigue")
        object.__setattr__(self, "accumulated_fatigue", fatigue)


@dataclass(frozen=True)
class ProgressionDecision:
    decision_id: str
    decision_type: ProgressionDecisionType
    reason: str
    policy_version: str
    exercise_id: str
    exercise_version: str
    training_plan_version: str
    load_delta_kg: Decimal | None = None
    repetition_delta: int | None = None
    set_delta: int | None = None
    replacement_exercise_id: str | None = None
    replacement_exercise_version: str | None = None

    def __post_init__(self) -> None:
        if (not self.decision_id or not self.reason or not self.policy_version or not self.exercise_id
                or not self.exercise_version or not self.training_plan_version):
            raise ValueError("progression decision traceability is required")
        if not isinstance(self.decision_type, ProgressionDecisionType):
            raise ValueError("progression decision requires a supported type")
        deltas = (self.load_delta_kg, self.repetition_delta, self.set_delta)
        if sum(value is not None for value in deltas) > 1:
            raise ValueError("a progression decision changes one variable only")
        if self.load_delta_kg is not None and Decimal(str(self.load_delta_kg)) <= 0:
            raise ValueError("load progression must be positive")
        if self.repetition_delta is not None and self.repetition_delta <= 0:
            raise ValueError("repetition progression must be positive")
        if self.set_delta is not None and self.set_delta <= 0:
            raise ValueError("set progression must be positive")
        if self.decision_type is ProgressionDecisionType.INCREASE_LOAD and self.load_delta_kg is None:
            raise ValueError("load progression requires a load delta")
        if self.decision_type is ProgressionDecisionType.INCREASE_REPETITIONS and self.repetition_delta is None:
            raise ValueError("repetition progression requires a repetition delta")
        if self.decision_type is ProgressionDecisionType.INCREASE_SETS and self.set_delta is None:
            raise ValueError("set progression requires a set delta")
        replacement = (self.replacement_exercise_id, self.replacement_exercise_version)
        if self.decision_type is ProgressionDecisionType.REPLACE_EXERCISE:
            if not all(replacement):
                raise ValueError("exercise replacement requires a traceable replacement")
        elif any(replacement):
            raise ValueError("only replacement decisions may include a replacement exercise")


@dataclass(frozen=True)
class ProgressionBlueprint:
    blueprint_id: str
    version: str
    training_plan_id: str
    training_plan_version: str
    progression_policy_version: str
    recovery: RecoverySnapshot
    decisions: tuple[ProgressionDecision, ...]

    def __post_init__(self) -> None:
        if (not self.blueprint_id or not self.version or not self.training_plan_id
                or not self.training_plan_version or not self.progression_policy_version):
            raise ValueError("progression blueprint identity is required")
        if not isinstance(self.recovery, RecoverySnapshot) or not isinstance(self.decisions, tuple) or not self.decisions:
            raise ValueError("progression blueprint requires recovery and decisions")
        identities = [(item.exercise_id, item.exercise_version) for item in self.decisions]
        if len(identities) != len(set(identities)):
            raise ValueError("progression blueprint has duplicate exercise decisions")
        if any(item.training_plan_version != self.training_plan_version
               or item.policy_version != self.progression_policy_version for item in self.decisions):
            raise ValueError("progression blueprint has inconsistent decision provenance")


@dataclass(frozen=True)
class ProgressionPolicy:
    """The sole authority for progression eligibility and progression actions."""

    version: str = "progression-policy-v2"
    repetition_increment: int = 1
    load_increment_kg: Decimal = Decimal("2.5")
    maximum_sets: int = 5
    minimum_progress_rir: int = 2
    maximum_progress_rpe: Decimal = Decimal("8")
    maximum_historical_load_jump_kg: Decimal = Decimal("20")
    required_successful_sessions_for_load: int = 1
    deload_after_progression_cycles: int = 4
    rotate_after_weeks: int = 8
    maximum_set_progression_stage: int = 2

    def __post_init__(self) -> None:
        if not self.version or self.repetition_increment < 1 or self.maximum_sets < 1:
            raise ValueError("progression policy requires positive discrete limits")
        if any(not isinstance(getattr(self, field), int) or getattr(self, field) < 1 for field in (
                "required_successful_sessions_for_load", "deload_after_progression_cycles",
                "rotate_after_weeks", "maximum_set_progression_stage")):
            raise ValueError("progression policy requires positive lifecycle limits")
        for field in ("load_increment_kg", "maximum_progress_rpe", "maximum_historical_load_jump_kg"):
            value = Decimal(str(getattr(self, field)))
            if value <= 0:
                raise ValueError(f"{field} must be positive")
            object.__setattr__(self, field, value)
        if not 0 <= self.minimum_progress_rir <= 10:
            raise ValueError("minimum progression RIR is invalid")


DEFAULT_PROGRESSION_POLICY = ProgressionPolicy()


class ProgressionEngine:
    """Choose one deterministic progression action for each prescribed exercise."""

    @classmethod
    def evaluate(cls, plan: TrainingPlanBlueprintV2, workout_history: tuple[WorkoutResult, ...],
                 recovery: RecoverySnapshot, *, progression_history: tuple[ProgressionDecision, ...] = (),
                 progress_states: tuple["ExerciseProgressState", ...] = (),
                 policy: ProgressionPolicy = DEFAULT_PROGRESSION_POLICY,
                 library: ExerciseLibrary | None = None) -> ProgressionBlueprint:
        selected_library = library or load_exercise_library()
        prescriptions = cls._validate_inputs(plan, workout_history, recovery, progression_history, progress_states, policy,
                                             selected_library)
        states = {(item.exercise_id, item.exercise_version): item for item in progress_states}
        decisions = tuple(cls._decision(
            prescription, plan, workout_history, recovery, progression_history, states.get(
                (prescription.exercise_id, prescription.exercise_version)), policy, selected_library,
        ) for prescription in prescriptions)
        return ProgressionBlueprint(
            blueprint_id=cls._blueprint_id(plan, workout_history, recovery, progression_history, policy),
            version="progression-blueprint-v1",
            training_plan_id=plan.plan_id,
            training_plan_version=plan.version,
            progression_policy_version=policy.version,
            recovery=recovery,
            decisions=decisions,
        )

    @classmethod
    def _validate_inputs(cls, plan: TrainingPlanBlueprintV2, history: tuple[WorkoutResult, ...],
                         recovery: RecoverySnapshot, progression_history: tuple[ProgressionDecision, ...],
                         progress_states: tuple["ExerciseProgressState", ...],
                         policy: ProgressionPolicy, library: ExerciseLibrary) -> tuple[ExercisePrescription, ...]:
        if not isinstance(plan, TrainingPlanBlueprintV2) or not isinstance(recovery, RecoverySnapshot):
            raise ValueError("progression requires a training blueprint and recovery snapshot")
        if not isinstance(history, tuple) or not history:
            raise ValueError("progression requires workout history")
        if not isinstance(policy, ProgressionPolicy) or not isinstance(library, ExerciseLibrary):
            raise ValueError("progression requires policy and exercise library")
        if not isinstance(progression_history, tuple) or any(not isinstance(item, ProgressionDecision)
                                                              for item in progression_history):
            raise ValueError("progression history must contain progression decisions")
        if not isinstance(progress_states, tuple):
            raise ValueError("progression states must be an immutable tuple")
        if tuple(item.completed_at for item in history) != tuple(sorted(item.completed_at for item in history)):
            raise ValueError("workout history must be chronological")
        if len({item.workout_id for item in history}) != len(history):
            raise ValueError("workout history has duplicate workout identity")
        by_identity: dict[tuple[str, str], ExercisePrescription] = {}
        for session in plan.sessions:
            for prescription in session.prescriptions:
                identity = (prescription.exercise_id, prescription.exercise_version)
                existing = by_identity.get(identity)
                if existing is not None and existing != prescription:
                    raise ValueError("training blueprint has inconsistent exercise prescriptions")
                by_identity[identity] = prescription
                library.require(*identity)
        for result in history:
            if result.plan_id != plan.plan_id or result.plan_version != plan.version:
                raise ValueError("workout history does not belong to the training blueprint")
            for performance in result.performances:
                if (performance.exercise_id, performance.exercise_version) not in by_identity:
                    raise ValueError("workout history references an invalid exercise")
        for decision in progression_history:
            if decision.training_plan_version != plan.version or decision.policy_version != policy.version:
                raise ValueError("progression history does not belong to the training blueprint")
        for state in progress_states:
            if (getattr(state, "progression_policy_version", None) != policy.version
                    or (state.exercise_id, state.exercise_version) not in by_identity):
                raise ValueError("progression state does not belong to the training blueprint")
        for identity in by_identity:
            cls._validate_load_history(identity, history, policy)
        return tuple(by_identity.values())

    @staticmethod
    def _validate_load_history(identity: tuple[str, str], history: tuple[WorkoutResult, ...],
                               policy: ProgressionPolicy) -> None:
        loads = [performance.load_kg for result in history for performance in result.performances
                 if (performance.exercise_id, performance.exercise_version) == identity
                 and performance.load_kg is not None]
        for previous, current in zip(loads, loads[1:]):
            if current - previous > policy.maximum_historical_load_jump_kg:
                raise ValueError("workout history contains an impossible progression jump")

    @classmethod
    def _decision(cls, prescription: ExercisePrescription, plan: TrainingPlanBlueprintV2,
                  history: tuple[WorkoutResult, ...], recovery: RecoverySnapshot,
                  progression_history: tuple[ProgressionDecision, ...], state: "ExerciseProgressState | None",
                  policy: ProgressionPolicy,
                  library: ExerciseLibrary) -> ProgressionDecision:
        identity = (prescription.exercise_id, prescription.exercise_version)
        performance_history = tuple((result, performance) for result in history for performance in result.performances
                                    if (performance.exercise_id, performance.exercise_version) == identity)
        if recovery.state is RecoveryState.OVERREACHED:
            return cls._build(ProgressionDecisionType.DELOAD, "recovery_overreached", prescription, plan, policy)
        if state is not None and state.deload_required:
            return cls._build(ProgressionDecisionType.DELOAD, "progression_cycle_complete", prescription, plan, policy)
        if not performance_history:
            return cls._build(ProgressionDecisionType.MAINTAIN, "insufficient_exercise_history", prescription, plan, policy)
        latest_result, latest = performance_history[-1]
        if latest.pain_reported:
            exercise = library.require(*identity)
            if exercise.regression.prior_exercise_ids:
                replacement_id = exercise.regression.prior_exercise_ids[0]
                replacement = library.require(replacement_id)
                return cls._build(ProgressionDecisionType.REPLACE_EXERCISE, "pain_reported", prescription, plan, policy,
                                  replacement=(replacement.exercise_id, replacement.version))
            return cls._build(ProgressionDecisionType.DELOAD, "pain_reported_without_regression", prescription, plan, policy)
        if recovery.state is RecoveryState.FATIGUED:
            return cls._build(ProgressionDecisionType.MAINTAIN, "recovery_fatigued", prescription, plan, policy)
        if not latest_result.completed or not latest.completed:
            return cls._build(ProgressionDecisionType.MAINTAIN, "workout_incomplete", prescription, plan, policy)
        if latest.achieved_rir is None or latest.achieved_rpe is None:
            return cls._build(ProgressionDecisionType.MAINTAIN, "effort_not_recorded", prescription, plan, policy)
        if latest.achieved_rir < policy.minimum_progress_rir or latest.achieved_rpe > policy.maximum_progress_rpe:
            return cls._build(ProgressionDecisionType.MAINTAIN, "effort_not_ready_for_progression", prescription, plan, policy)
        if latest.completed_repetitions < prescription.rep_max:
            return cls._build(ProgressionDecisionType.INCREASE_REPETITIONS, "repetition_range_not_reached",
                              prescription, plan, policy, repetitions=policy.repetition_increment)
        prior = tuple(item for item in progression_history
                      if (item.exercise_id, item.exercise_version) == identity)
        if latest.load_kg is not None and (not prior or prior[-1].decision_type is not ProgressionDecisionType.INCREASE_LOAD):
            if not cls._load_eligible(performance_history, state, policy):
                return cls._build(ProgressionDecisionType.MAINTAIN, "load_progression_not_eligible",
                                  prescription, plan, policy)
            return cls._build(ProgressionDecisionType.INCREASE_LOAD, "repetition_ceiling_reached",
                              prescription, plan, policy, load=policy.load_increment_kg)
        if prescription.sets < policy.maximum_sets:
            if state is not None and state.counters.set_progression_stage >= policy.maximum_set_progression_stage:
                return cls._build(ProgressionDecisionType.MAINTAIN, "set_progression_stage_exhausted",
                                  prescription, plan, policy)
            return cls._build(ProgressionDecisionType.INCREASE_SETS, "load_progression_already_applied",
                              prescription, plan, policy, sets=1)
        return cls._build(ProgressionDecisionType.MAINTAIN, "progression_ceiling_reached", prescription, plan, policy)

    @staticmethod
    def _load_eligible(performance_history, state: "ExerciseProgressState | None",
                       policy: ProgressionPolicy) -> bool:
        if state is not None:
            return state.load_progression_eligible
        successful = 0
        for result, performance in reversed(performance_history):
            if not (result.completed and performance.completed and not performance.pain_reported):
                break
            successful += 1
        return successful >= policy.required_successful_sessions_for_load

    @classmethod
    def _build(cls, kind: ProgressionDecisionType, reason: str, prescription: ExercisePrescription,
               plan: TrainingPlanBlueprintV2, policy: ProgressionPolicy, *, load: Decimal | None = None,
               repetitions: int | None = None, sets: int | None = None,
               replacement: tuple[str, str] | None = None) -> ProgressionDecision:
        source = {
            "kind": kind.value, "reason": reason, "exercise": [prescription.exercise_id, prescription.exercise_version],
            "plan": plan.version, "policy": policy.version, "load": str(load) if load is not None else None,
            "repetitions": repetitions, "sets": sets, "replacement": replacement,
        }
        decision_id = "progression_" + sha256(json.dumps(source, sort_keys=True).encode("utf-8")).hexdigest()[:24]
        return ProgressionDecision(
            decision_id, kind, reason, policy.version, prescription.exercise_id, prescription.exercise_version,
            plan.version, load, repetitions, sets,
            replacement[0] if replacement else None, replacement[1] if replacement else None,
        )

    @staticmethod
    def _blueprint_id(plan: TrainingPlanBlueprintV2, history: tuple[WorkoutResult, ...],
                      recovery: RecoverySnapshot, progression_history: tuple[ProgressionDecision, ...],
                      policy: ProgressionPolicy) -> str:
        source = {
            "plan_id": plan.plan_id, "plan_version": plan.version, "recovery": recovery.state.value,
            "fatigue": str(recovery.accumulated_fatigue), "policy": policy.version,
            "workouts": [result.workout_id for result in history],
            "prior": [decision.decision_id for decision in progression_history],
        }
        return "progression_blueprint_" + sha256(json.dumps(source, sort_keys=True).encode("utf-8")).hexdigest()[:24]
