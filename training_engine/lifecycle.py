"""Pure immutable revision of a training plan from progression evidence."""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from hashlib import sha256
import json

from .construction import (
    ExercisePrescription,
    MuscleGroupVolume,
    TrainingPlanBlueprintV2,
    TrainingSessionBlueprint,
)
from .progression import ProgressionBlueprint, ProgressionDecision, ProgressionDecisionType, WorkoutResult
from .progression_state import ExerciseProgressState
from .models import RotationPolicy
from .registry import ExerciseLibrary, load_exercise_library


class PlanRevisionReason(str, Enum):
    LOAD = "load_revision"
    REPETITIONS = "repetition_revision"
    SETS = "set_revision"
    EXERCISE_REPLACEMENT = "exercise_replacement"
    DELOAD = "deload_revision"
    ROTATION = "rotation_revision"
    MAINTAIN = "maintain"


@dataclass(frozen=True)
class LifecycleDecision:
    decision_id: str
    reason: PlanRevisionReason
    exercise_id: str
    exercise_version: str
    progression_decision_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.decision_id or not self.exercise_id or not self.exercise_version:
            raise ValueError("lifecycle decision traceability is required")
        if not isinstance(self.reason, PlanRevisionReason):
            raise ValueError("lifecycle decision requires a revision reason")
        if (not isinstance(self.progression_decision_ids, tuple)
                or any(not item for item in self.progression_decision_ids)
                or len(self.progression_decision_ids) != len(set(self.progression_decision_ids))):
            raise ValueError("lifecycle decision requires unique progression provenance")


@dataclass(frozen=True)
class TrainingLifecycleEvent:
    event_id: str
    workout: WorkoutResult
    progression: ProgressionBlueprint
    progress_states: tuple[ExerciseProgressState, ...]
    state_policy_version: str

    def __post_init__(self) -> None:
        if not self.event_id or not isinstance(self.workout, WorkoutResult) or not isinstance(self.progression, ProgressionBlueprint):
            raise ValueError("lifecycle event requires workout and progression evidence")
        if (self.progression.training_plan_id != self.workout.plan_id
                or self.progression.training_plan_version != self.workout.plan_version):
            raise ValueError("lifecycle event has orphan progression evidence")
        if (not isinstance(self.progress_states, tuple)
                or any(not isinstance(item, ExerciseProgressState) for item in self.progress_states)
                or not self.state_policy_version):
            raise ValueError("lifecycle event requires immutable progression states")
        if any(item.originating_workout_id != self.workout.workout_id for item in self.progress_states):
            raise ValueError("lifecycle event states must originate from its workout")


@dataclass(frozen=True)
class PlanRevision:
    revision_id: str
    parent_plan_id: str
    parent_plan_version: str
    reasons: tuple[PlanRevisionReason, ...]
    lifecycle_decisions: tuple[LifecycleDecision, ...]
    revised_plan: TrainingPlanBlueprintV2

    def __post_init__(self) -> None:
        if not self.revision_id or not self.parent_plan_id or not self.parent_plan_version:
            raise ValueError("plan revision ancestry is required")
        if not isinstance(self.reasons, tuple) or not self.reasons or any(
                not isinstance(item, PlanRevisionReason) for item in self.reasons):
            raise ValueError("plan revision requires typed reasons")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("plan revision has duplicate reasons")
        if (not isinstance(self.lifecycle_decisions, tuple) or not self.lifecycle_decisions
                or len({item.decision_id for item in self.lifecycle_decisions}) != len(self.lifecycle_decisions)):
            raise ValueError("plan revision has duplicate lifecycle decisions")
        plan = self.revised_plan
        if not isinstance(plan, TrainingPlanBlueprintV2):
            raise ValueError("plan revision requires an immutable revised plan")
        if (plan.parent_plan_id, plan.parent_plan_version, plan.revision_id) != (
                self.parent_plan_id, self.parent_plan_version, self.revision_id):
            raise ValueError("plan revision lost blueprint ancestry")
        expected_ids = tuple(sorted({item_id for decision in self.lifecycle_decisions
                                    for item_id in decision.progression_decision_ids}))
        if plan.progression_decision_ids != expected_ids:
            raise ValueError("plan revision lost progression decision traceability")


class TrainingLifecycleOrchestrator:
    """Create a new plan revision without ever mutating a previous blueprint."""

    POLICY_VERSION = "training-lifecycle-policy-v1"

    @classmethod
    def revise(cls, parent: TrainingPlanBlueprintV2, event: TrainingLifecycleEvent, *,
               library: ExerciseLibrary | None = None) -> PlanRevision:
        selected_library = library or load_exercise_library()
        cls._validate(parent, event, selected_library)
        decisions = {(item.exercise_id, item.exercise_version): item for item in event.progression.decisions}
        states = {(item.exercise_id, item.exercise_version): item for item in event.progress_states}
        revision_id = cls._revision_id(parent, event)
        lifecycle_decisions: list[LifecycleDecision] = []
        sessions = []
        for session in parent.sessions:
            revised = []
            for prescription in session.prescriptions:
                key = (prescription.exercise_id, prescription.exercise_version)
                updated, lifecycle = cls._revise_prescription(
                    prescription, decisions.get(key), states.get(key), event.workout, selected_library,
                    revision_id, session.session_index)
                revised.append(updated)
                lifecycle_decisions.append(lifecycle)
            sessions.append(replace(
                session, session_id=f"{session.session_id}:revision:{revision_id}",
                estimated_duration_minutes=cls._duration(tuple(revised)), prescriptions=tuple(revised),
            ))
        ordered_lifecycle = tuple(lifecycle_decisions)
        reasons = tuple(sorted({item.reason for item in ordered_lifecycle}, key=lambda item: item.value))
        progression_ids = tuple(sorted({item_id for item in ordered_lifecycle
                                        for item_id in item.progression_decision_ids}))
        revised_plan = TrainingPlanBlueprintV2(
            plan_id=f"{parent.plan_id}:revision:{revision_id}",
            version=f"{parent.version}:revision:{revision_id}",
            selection_blueprint_id=parent.selection_blueprint_id,
            exercise_library_version=parent.exercise_library_version,
            selection_policy_version=parent.selection_policy_version,
            construction_policy_version=parent.construction_policy_version,
            training_split=parent.training_split,
            sessions=tuple(sessions), weekly_volume=cls._volume(tuple(sessions), selected_library),
            parent_plan_id=parent.plan_id, parent_plan_version=parent.version, revision_id=revision_id,
            revision_reasons=tuple(item.value for item in reasons), progression_decision_ids=progression_ids,
            lifecycle_policy_version=cls.POLICY_VERSION,
        )
        return PlanRevision(revision_id, parent.plan_id, parent.version, reasons, ordered_lifecycle, revised_plan)

    @staticmethod
    def _validate(parent: TrainingPlanBlueprintV2, event: TrainingLifecycleEvent,
                  library: ExerciseLibrary) -> None:
        if not isinstance(parent, TrainingPlanBlueprintV2) or not isinstance(event, TrainingLifecycleEvent):
            raise ValueError("lifecycle requires a plan and lifecycle event")
        if (event.workout.plan_id, event.workout.plan_version) != (parent.plan_id, parent.version):
            raise ValueError("lifecycle event is incompatible with blueprint ancestry")
        if parent.exercise_library_version != library.version:
            raise ValueError("lifecycle event requires the originating exercise library version")
        known = {(item.exercise_id, item.exercise_version) for session in parent.sessions for item in session.prescriptions}
        if len(event.progression.decisions) != len({(item.exercise_id, item.exercise_version)
                                                    for item in event.progression.decisions}):
            raise ValueError("lifecycle event has duplicate progression revisions")
        if any((item.exercise_id, item.exercise_version) not in known for item in event.progression.decisions):
            raise ValueError("lifecycle event has an orphan progression decision")
        if any((item.exercise_id, item.exercise_version) not in known for item in event.progress_states):
            raise ValueError("lifecycle event has an orphan progress state")

    @classmethod
    def _revise_prescription(cls, prescription: ExercisePrescription, decision: ProgressionDecision | None,
                             state: ExerciseProgressState | None, workout: WorkoutResult,
                             library: ExerciseLibrary, revision_id: str,
                             session_index: int) -> tuple[ExercisePrescription, LifecycleDecision]:
        reason = PlanRevisionReason.MAINTAIN
        updated = prescription
        ids: tuple[str, ...] = ()
        if decision is not None:
            ids = (decision.decision_id,)
            if decision.decision_type is ProgressionDecisionType.INCREASE_LOAD:
                performance = next((item for item in workout.performances
                                    if (item.exercise_id, item.exercise_version) ==
                                    (prescription.exercise_id, prescription.exercise_version)), None)
                if performance is None or performance.load_kg is None:
                    raise ValueError("load revision requires a recorded workout load")
                updated = replace(prescription, target_load_kg=performance.load_kg + decision.load_delta_kg)
                reason = PlanRevisionReason.LOAD
            elif decision.decision_type is ProgressionDecisionType.INCREASE_REPETITIONS:
                updated = replace(prescription, rep_max=prescription.rep_max + decision.repetition_delta)
                reason = PlanRevisionReason.REPETITIONS
            elif decision.decision_type is ProgressionDecisionType.INCREASE_SETS:
                updated = replace(prescription, sets=prescription.sets + decision.set_delta)
                reason = PlanRevisionReason.SETS
            elif decision.decision_type is ProgressionDecisionType.REPLACE_EXERCISE:
                replacement = library.require(decision.replacement_exercise_id, decision.replacement_exercise_version)
                if replacement.movement_pattern is not prescription.movement_pattern:
                    raise ValueError("exercise replacement is incompatible with the plan movement pattern")
                updated = replace(prescription, exercise_id=replacement.exercise_id,
                                  exercise_version=replacement.version, movement_pattern=replacement.movement_pattern,
                                  target_load_kg=None)
                reason = PlanRevisionReason.EXERCISE_REPLACEMENT
            elif decision.decision_type is ProgressionDecisionType.DELOAD:
                updated = replace(
                    prescription, sets=max(1, prescription.sets // 2),
                    target_rpe=max(Decimal("1"), prescription.target_rpe - Decimal("1")),
                )
                reason = PlanRevisionReason.DELOAD
        if reason is PlanRevisionReason.MAINTAIN and state is not None and state.rotation_recommended:
            exercise = library.require(prescription.exercise_id, prescription.exercise_version)
            if exercise.progression.rotation_policy is RotationPolicy.TERMINAL:
                # Terminal rotation is a governed library decision, not missing data.
                # The plan remains unchanged and retains explicit maintain provenance.
                pass
            elif not exercise.progression.next_exercise_ids:
                raise ValueError("successor rotation policy has no compatible successor")
            else:
                successor = library.require(exercise.progression.next_exercise_ids[0])
                if successor.movement_pattern is not prescription.movement_pattern:
                    raise ValueError("rotation successor is incompatible with the plan movement pattern")
                updated = replace(prescription, exercise_id=successor.exercise_id,
                                  exercise_version=successor.version, movement_pattern=successor.movement_pattern,
                                  target_load_kg=None)
                reason = PlanRevisionReason.ROTATION
        lifecycle_id = "lifecycle_" + sha256(json.dumps({
            "revision": revision_id, "exercise": [prescription.exercise_id, prescription.exercise_version],
            "session": session_index, "reason": reason.value, "progression": ids,
        }, sort_keys=True).encode("utf-8")).hexdigest()[:24]
        return updated, LifecycleDecision(lifecycle_id, reason, prescription.exercise_id,
                                          prescription.exercise_version, ids)

    @staticmethod
    def _duration(prescriptions: tuple[ExercisePrescription, ...]) -> int:
        seconds = 30 * max(0, len(prescriptions) - 1)
        for item in prescriptions:
            average_reps = Decimal(item.rep_min + item.rep_max) / Decimal("2")
            seconds += int(Decimal(item.sets) * average_reps * 4)
            seconds += max(0, item.sets - 1) * item.rest_seconds
        return max(1, int((Decimal(seconds) / Decimal("60")).to_integral_value(rounding=ROUND_HALF_UP)))

    @staticmethod
    def _volume(sessions: tuple[TrainingSessionBlueprint, ...], library: ExerciseLibrary) -> tuple[MuscleGroupVolume, ...]:
        values: dict[str, int] = {}
        for session in sessions:
            for prescription in session.prescriptions:
                for muscle in library.require(prescription.exercise_id, prescription.exercise_version).primary_muscles:
                    values[muscle] = values.get(muscle, 0) + prescription.sets
        return tuple(MuscleGroupVolume(muscle, values[muscle]) for muscle in sorted(values))

    @staticmethod
    def _revision_id(parent: TrainingPlanBlueprintV2, event: TrainingLifecycleEvent) -> str:
        source = {
            "parent": [parent.plan_id, parent.version], "event": event.event_id,
            "progression": event.progression.blueprint_id,
            "decisions": [item.decision_id for item in event.progression.decisions],
            "states": [item.originating_workout_id + ":" + item.exercise_id for item in event.progress_states],
        }
        return sha256(json.dumps(source, sort_keys=True).encode("utf-8")).hexdigest()[:16]
