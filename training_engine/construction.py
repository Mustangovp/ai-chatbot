"""Deterministic execution prescription from an ExerciseSelectionBlueprint.

This construction layer has no runtime, prompt, renderer, or selection
dependency. It only turns already-selected exercise identities into a bounded,
traceable weekly execution blueprint under an explicit structure policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
import re

from .models import Difficulty, MovementPattern
from .registry import ExerciseLibrary
from .selection import ExerciseSelectionBlueprint, TrainingGoal, TrainingSplit


_TEMPO = re.compile(r"^\d-\d-\d-\d$")


class RecoveryAssumption(str, Enum):
    FRESH = "fresh"
    MODERATE = "moderate"
    LIMITED = "limited"


class TrainingConstructionError(ValueError):
    pass


@dataclass(frozen=True)
class PrescriptionRule:
    movement_pattern: MovementPattern
    sets: int
    rep_min: int
    rep_max: int
    target_rpe: Decimal
    target_rir: int
    rest_seconds: int
    tempo: str
    work_seconds_per_rep: int
    fatigue_units_per_set: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.movement_pattern, MovementPattern):
            raise ValueError("prescription rule requires a movement pattern")
        if not isinstance(self.sets, int) or self.sets < 1:
            raise ValueError("prescription sets must be positive")
        if not isinstance(self.rep_min, int) or not isinstance(self.rep_max, int) or self.rep_min < 1 or self.rep_min > self.rep_max:
            raise ValueError("prescription rep range is invalid")
        rpe = Decimal(str(self.target_rpe))
        if not Decimal("1") <= rpe <= Decimal("10"):
            raise ValueError("prescription RPE must be between one and ten")
        object.__setattr__(self, "target_rpe", rpe)
        if not isinstance(self.target_rir, int) or not 0 <= self.target_rir <= 10:
            raise ValueError("prescription RIR must be between zero and ten")
        if not isinstance(self.rest_seconds, int) or self.rest_seconds < 0:
            raise ValueError("prescription rest must be non-negative")
        if not isinstance(self.tempo, str) or not _TEMPO.fullmatch(self.tempo):
            raise ValueError("prescription tempo must use four numeric phases")
        if not isinstance(self.work_seconds_per_rep, int) or self.work_seconds_per_rep < 1:
            raise ValueError("work_seconds_per_rep must be positive")
        fatigue = Decimal(str(self.fatigue_units_per_set))
        if fatigue <= 0:
            raise ValueError("fatigue_units_per_set must be positive")
        object.__setattr__(self, "fatigue_units_per_set", fatigue)


@dataclass(frozen=True)
class TrainingStructurePolicy:
    version: str
    goal: TrainingGoal
    experience_level: Difficulty
    recovery: RecoveryAssumption
    sessions_per_week: int
    movement_order: tuple[MovementPattern, ...]
    prescription_rules: tuple[PrescriptionRule, ...]
    max_session_duration_minutes: int
    max_session_fatigue_units: Decimal
    max_weekly_sets_per_primary_muscle: int
    max_push_pull_set_difference: int
    max_lower_body_set_difference: int
    transition_seconds: int
    training_split: TrainingSplit = TrainingSplit.FULL_BODY
    session_patterns: tuple[tuple[MovementPattern, ...], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("construction policy version is required")
        if (not isinstance(self.goal, TrainingGoal) or not isinstance(self.experience_level, Difficulty)
                or not isinstance(self.training_split, TrainingSplit)):
            raise ValueError("construction policy goal, experience, and split are required")
        if not isinstance(self.recovery, RecoveryAssumption):
            raise ValueError("construction policy recovery is required")
        if not isinstance(self.sessions_per_week, int) or not 1 <= self.sessions_per_week <= 7:
            raise ValueError("sessions_per_week must be within one and seven")
        sessions = self.session_patterns or (self.movement_order,)
        if not isinstance(sessions, tuple) or not sessions:
            raise ValueError("construction policy requires split session patterns")
        flattened = tuple(pattern for session in sessions for pattern in session)
        if (any(not isinstance(session, tuple) or not session for session in self.session_patterns)
                or len(flattened) != len(set(flattened))
                or any(not isinstance(pattern, MovementPattern) for pattern in flattened)):
            raise ValueError("construction policy has invalid split session patterns")
        if self.sessions_per_week < len(sessions):
            raise ValueError("construction policy cannot omit requested split sessions")
        if not isinstance(self.movement_order, tuple) or len(self.movement_order) != len(set(self.movement_order)):
            raise ValueError("construction policy movement order must be unique")
        if not isinstance(self.prescription_rules, tuple) or not self.prescription_rules:
            raise ValueError("construction policy requires prescription rules")
        patterns = tuple(rule.movement_pattern for rule in self.prescription_rules)
        if len(patterns) != len(set(patterns)):
            raise ValueError("construction policy must provide one rule per pattern")
        if any(not isinstance(pattern, MovementPattern) for pattern in self.movement_order):
            raise ValueError("construction policy has invalid movement order")
        if not set(patterns).issubset(set(self.movement_order)):
            raise ValueError("construction policy rules must appear in movement order")
        object.__setattr__(self, "session_patterns", sessions)
        if not isinstance(self.max_session_duration_minutes, int) or self.max_session_duration_minutes < 1:
            raise ValueError("maximum session duration must be positive")
        fatigue = Decimal(str(self.max_session_fatigue_units))
        if fatigue <= 0:
            raise ValueError("maximum session fatigue must be positive")
        object.__setattr__(self, "max_session_fatigue_units", fatigue)
        for field in ("max_weekly_sets_per_primary_muscle", "max_push_pull_set_difference",
                      "max_lower_body_set_difference", "transition_seconds"):
            value = getattr(self, field)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be non-negative")

    def rule_for(self, pattern: MovementPattern) -> PrescriptionRule:
        for rule in self.prescription_rules:
            if rule.movement_pattern is pattern:
                return rule
        raise TrainingConstructionError(f"missing prescription rule:{pattern.value}")


@dataclass(frozen=True)
class ExercisePrescription:
    exercise_id: str
    exercise_version: str
    movement_pattern: MovementPattern
    sets: int
    rep_min: int
    rep_max: int
    target_rpe: Decimal
    target_rir: int
    rest_seconds: int
    tempo: str
    selection_policy_version: str
    prescription_policy_version: str
    construction_policy_version: str
    target_load_kg: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.exercise_id or not self.exercise_version:
            raise ValueError("prescription exercise traceability is required")
        if not isinstance(self.movement_pattern, MovementPattern):
            raise ValueError("prescription movement pattern is required")
        if (not self.selection_policy_version or not self.prescription_policy_version
                or not self.construction_policy_version):
            raise ValueError("prescription policy traceability is required")
        PrescriptionRule(self.movement_pattern, self.sets, self.rep_min, self.rep_max,
                         self.target_rpe, self.target_rir, self.rest_seconds, self.tempo, 1, Decimal("1"))
        if self.target_load_kg is not None:
            load = Decimal(str(self.target_load_kg))
            if load < 0:
                raise ValueError("prescription target load must be non-negative")
            object.__setattr__(self, "target_load_kg", load)


@dataclass(frozen=True)
class TrainingSessionBlueprint:
    session_id: str
    session_index: int
    selection_blueprint_id: str
    estimated_duration_minutes: int
    prescriptions: tuple[ExercisePrescription, ...]

    def __post_init__(self) -> None:
        if not self.session_id or not self.selection_blueprint_id:
            raise ValueError("session identity and selection traceability are required")
        if not isinstance(self.session_index, int) or self.session_index < 1:
            raise ValueError("session index must be positive")
        if not isinstance(self.estimated_duration_minutes, int) or self.estimated_duration_minutes < 1:
            raise ValueError("estimated session duration must be positive")
        if not isinstance(self.prescriptions, tuple) or not self.prescriptions:
            raise ValueError("session requires prescriptions")
        if len({item.exercise_id for item in self.prescriptions}) != len(self.prescriptions):
            raise ValueError("session contains duplicate exercise prescriptions")


@dataclass(frozen=True)
class MuscleGroupVolume:
    muscle_group: str
    weekly_sets: int


@dataclass(frozen=True)
class TrainingPlanBlueprintV2:
    plan_id: str
    version: str
    selection_blueprint_id: str
    exercise_library_version: str
    selection_policy_version: str
    construction_policy_version: str
    sessions: tuple[TrainingSessionBlueprint, ...]
    weekly_volume: tuple[MuscleGroupVolume, ...]
    training_split: TrainingSplit = TrainingSplit.FULL_BODY
    parent_plan_id: str | None = None
    parent_plan_version: str | None = None
    revision_id: str | None = None
    revision_reasons: tuple[str, ...] = ()
    progression_decision_ids: tuple[str, ...] = ()
    lifecycle_policy_version: str | None = None

    def __post_init__(self) -> None:
        if not self.plan_id or not self.version or not self.selection_blueprint_id:
            raise ValueError("training plan identity is required")
        if (not self.exercise_library_version or not self.selection_policy_version
                or not self.construction_policy_version):
            raise ValueError("training plan traceability is required")
        if not isinstance(self.training_split, TrainingSplit):
            raise ValueError("training plan requires a supported split")
        if not isinstance(self.sessions, tuple) or not self.sessions:
            raise ValueError("training plan requires sessions")
        if tuple(item.session_index for item in self.sessions) != tuple(range(1, len(self.sessions) + 1)):
            raise ValueError("training plan sessions must be consecutive")
        if not isinstance(self.weekly_volume, tuple) or not self.weekly_volume:
            raise ValueError("training plan requires weekly volume")
        lineage = (self.parent_plan_id, self.parent_plan_version, self.revision_id,
                   self.lifecycle_policy_version)
        if any(value is not None for value in lineage):
            if not all(isinstance(value, str) and value for value in lineage):
                raise ValueError("revised training plan requires complete immutable lineage")
            if self.parent_plan_id == self.plan_id and self.parent_plan_version == self.version:
                raise ValueError("training plan cannot be its own parent")
            if not isinstance(self.revision_reasons, tuple) or not self.revision_reasons:
                raise ValueError("revised training plan requires revision reasons")
            if (not isinstance(self.progression_decision_ids, tuple)
                    or any(not isinstance(item, str) or not item for item in self.progression_decision_ids)):
                raise ValueError("revised training plan has invalid progression decision provenance")
        elif self.revision_reasons or self.progression_decision_ids:
            raise ValueError("unrevised training plan cannot claim revision provenance")


class TrainingPlanConstructionEngine:
    """Prescribe execution for a balanced immutable selection without reselection."""

    @classmethod
    def construct(cls, selection: ExerciseSelectionBlueprint, library: ExerciseLibrary,
                  policy: TrainingStructurePolicy) -> TrainingPlanBlueprintV2:
        if not isinstance(selection, ExerciseSelectionBlueprint) or not isinstance(library, ExerciseLibrary):
            raise ValueError("construction requires selection blueprint and exercise library")
        if (selection.goal is not policy.goal or selection.experience_level is not policy.experience_level
                or selection.training_split is not policy.training_split):
            raise TrainingConstructionError("selection does not match construction policy")
        if selection.exercise_library_version != library.version:
            raise TrainingConstructionError("selection does not match exercise library version")
        sessions = tuple(cls._session(selection, policy, index, patterns)
                         for index, patterns in enumerate(cls._session_pattern_groups(policy), 1))
        volume = cls._weekly_volume(sessions, library)
        cls._validate_weekly_balance(sessions, volume, policy)
        return TrainingPlanBlueprintV2(
            plan_id=f"plan:{selection.blueprint_id}:{policy.version}",
            version="training-plan-blueprint-v2",
            selection_blueprint_id=selection.blueprint_id,
            exercise_library_version=library.version,
            selection_policy_version=selection.policy_version,
            construction_policy_version=policy.version,
            training_split=policy.training_split,
            sessions=sessions,
            weekly_volume=volume,
        )

    @classmethod
    def _session(cls, selection: ExerciseSelectionBlueprint, policy: TrainingStructurePolicy,
                 index: int, patterns: tuple[MovementPattern, ...]) -> TrainingSessionBlueprint:
        ordered = cls._ordered(selection, policy, patterns)
        prescriptions = tuple(cls._prescribe(item, policy, selection.policy_version) for item in ordered)
        duration = cls._duration_minutes(prescriptions, policy)
        fatigue = sum((policy.rule_for(item.movement_pattern).fatigue_units_per_set * item.sets
                       for item in prescriptions), Decimal("0"))
        cls._validate_session(prescriptions, duration, fatigue, policy, patterns)
        return TrainingSessionBlueprint(
            f"session:{selection.blueprint_id}:{index}", index, selection.blueprint_id, duration, prescriptions,
        )

    @staticmethod
    def _session_pattern_groups(policy: TrainingStructurePolicy) -> tuple[tuple[MovementPattern, ...], ...]:
        return tuple(policy.session_patterns[index % len(policy.session_patterns)]
                     for index in range(policy.sessions_per_week))

    @staticmethod
    def _ordered(selection: ExerciseSelectionBlueprint, policy: TrainingStructurePolicy,
                 patterns: tuple[MovementPattern, ...]):
        positions = {pattern: index for index, pattern in enumerate(policy.movement_order)}
        try:
            selected = tuple(item for item in selection.selections if item.movement_pattern in patterns)
            if {item.movement_pattern for item in selected} != set(patterns):
                raise TrainingConstructionError("split session is missing a required movement pattern")
            return tuple(sorted(selected, key=lambda item: positions[item.movement_pattern]))
        except KeyError as error:
            raise TrainingConstructionError(f"invalid movement combination:{error.args[0].value}") from error

    @staticmethod
    def _prescribe(selection, policy: TrainingStructurePolicy,
                   selection_policy_version: str) -> ExercisePrescription:
        rule = policy.rule_for(selection.movement_pattern)
        return ExercisePrescription(
            selection.exercise_id, selection.exercise_version, selection.movement_pattern,
            rule.sets, rule.rep_min, rule.rep_max, rule.target_rpe, rule.target_rir,
            rule.rest_seconds, rule.tempo, selection_policy_version, policy.version, policy.version,
        )

    @staticmethod
    def _duration_minutes(prescriptions: tuple[ExercisePrescription, ...],
                          policy: TrainingStructurePolicy) -> int:
        seconds = policy.transition_seconds * max(0, len(prescriptions) - 1)
        for item in prescriptions:
            rule = policy.rule_for(item.movement_pattern)
            average_reps = Decimal(item.rep_min + item.rep_max) / Decimal("2")
            seconds += int(Decimal(item.sets) * average_reps * rule.work_seconds_per_rep)
            seconds += max(0, item.sets - 1) * item.rest_seconds
        return max(1, int((Decimal(seconds) / Decimal("60")).to_integral_value(rounding=ROUND_HALF_UP)))

    @staticmethod
    def _validate_session(prescriptions: tuple[ExercisePrescription, ...], duration: int,
                          fatigue: Decimal, policy: TrainingStructurePolicy,
                          required_patterns: tuple[MovementPattern, ...]) -> None:
        if {item.movement_pattern for item in prescriptions} != set(required_patterns):
            raise TrainingConstructionError("construction lost selected exercises")
        if len({item.exercise_id for item in prescriptions}) != len(prescriptions):
            raise TrainingConstructionError("duplicate prescription")
        if duration > policy.max_session_duration_minutes:
            raise TrainingConstructionError("session duration limit exceeded")
        if fatigue > policy.max_session_fatigue_units:
            raise TrainingConstructionError("session fatigue limit exceeded")

    @staticmethod
    def _weekly_volume(sessions: tuple[TrainingSessionBlueprint, ...], library: ExerciseLibrary) -> tuple[MuscleGroupVolume, ...]:
        values: dict[str, int] = {}
        for session in sessions:
            for prescription in session.prescriptions:
                exercise = library.require(prescription.exercise_id, prescription.exercise_version)
                for muscle in exercise.primary_muscles:
                    values[muscle] = values.get(muscle, 0) + prescription.sets
        return tuple(MuscleGroupVolume(muscle, values[muscle]) for muscle in sorted(values))

    @staticmethod
    def _validate_weekly_balance(sessions: tuple[TrainingSessionBlueprint, ...],
                                volume: tuple[MuscleGroupVolume, ...], policy: TrainingStructurePolicy) -> None:
        if any(item.weekly_sets > policy.max_weekly_sets_per_primary_muscle for item in volume):
            raise TrainingConstructionError("weekly volume limit exceeded")
        by_pattern: dict[MovementPattern, int] = {}
        for session in sessions:
            for item in session.prescriptions:
                by_pattern[item.movement_pattern] = by_pattern.get(item.movement_pattern, 0) + item.sets
        if (MovementPattern.HORIZONTAL_PUSH in by_pattern and MovementPattern.HORIZONTAL_PULL in by_pattern
                and abs(by_pattern[MovementPattern.HORIZONTAL_PUSH] - by_pattern[MovementPattern.HORIZONTAL_PULL])
                > policy.max_push_pull_set_difference):
            raise TrainingConstructionError("push pull balance limit exceeded")
        if (MovementPattern.SQUAT in by_pattern and MovementPattern.HINGE in by_pattern
                and abs(by_pattern[MovementPattern.SQUAT] - by_pattern[MovementPattern.HINGE])
                > policy.max_lower_body_set_difference):
            raise TrainingConstructionError("lower body balance limit exceeded")
