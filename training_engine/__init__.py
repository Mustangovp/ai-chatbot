"""Isolated deterministic Training Engine foundation."""
from .models import (
    Difficulty,
    Equipment,
    Exercise,
    MovementPattern,
    ProgressionMetadata,
    RegressionMetadata,
    RotationPolicy,
    TrainingDay,
    TrainingPlanBlueprint,
    TrainingWeek,
)
from .registry import EXERCISE_LIBRARY_VERSION, ExerciseLibrary, load_exercise_library
from .selection import (
    DEFAULT_TRAINING_GOAL_POLICIES,
    ExerciseSelection,
    ExerciseSelectionBlueprint,
    SelectionOutcome,
    TrainingGoal,
    TrainingGoalPolicy,
    TrainingSplit,
    TrainingSafetyConstraints,
    TrainingSelectionEngine,
    TrainingSelectionRequest,
    TrainingSelectionResult,
    resolve_training_split,
    training_goal_policy,
)
from .construction import (
    ExercisePrescription,
    MuscleGroupVolume,
    PrescriptionRule,
    RecoveryAssumption,
    TrainingConstructionError,
    TrainingPlanBlueprintV2,
    TrainingPlanConstructionEngine,
    TrainingSessionBlueprint,
    TrainingStructurePolicy,
)
from .runtime import TrainingRuntimeError, build_training_plan
from .progression import (
    DEFAULT_PROGRESSION_POLICY,
    ExercisePerformance,
    ProgressionBlueprint,
    ProgressionDecision,
    ProgressionDecisionType,
    ProgressionEngine,
    ProgressionPolicy,
    RecoverySnapshot,
    RecoveryState,
    WorkoutResult,
)
from .progression_state import (
    DEFAULT_PROGRESSION_STATE_POLICY,
    DeloadHistory,
    ExerciseProgressState,
    ProgressionCounters,
    ProgressionEvent,
    ProgressionHistory,
    ProgressionStateEngine,
    ProgressionStatePolicy,
)
from .lifecycle import (
    LifecycleDecision,
    PlanRevision,
    PlanRevisionReason,
    TrainingLifecycleEvent,
    TrainingLifecycleOrchestrator,
)
from .lifecycle_runtime import (
    LifecycleRuntimeResult,
    advance_training_lifecycle,
    recovery_from_payload,
    workout_result_from_payload,
)
from .completion import (
    CompletedPrescription,
    WorkoutCompletion,
    completion_projection,
    prescription_id,
    validate_workout_completion_payload,
    workout_completion_from_payload,
)

__all__ = [
    "Difficulty", "Equipment", "Exercise", "MovementPattern", "ProgressionMetadata", "RotationPolicy",
    "RegressionMetadata", "TrainingDay", "TrainingPlanBlueprint", "TrainingWeek",
    "EXERCISE_LIBRARY_VERSION", "ExerciseLibrary", "load_exercise_library",
    "DEFAULT_TRAINING_GOAL_POLICIES", "ExerciseSelection", "ExerciseSelectionBlueprint",
    "SelectionOutcome", "TrainingGoal", "TrainingGoalPolicy", "TrainingSplit", "TrainingSafetyConstraints",
    "TrainingSelectionEngine", "TrainingSelectionRequest", "TrainingSelectionResult",
    "resolve_training_split", "training_goal_policy",
    "ExercisePrescription", "MuscleGroupVolume", "PrescriptionRule", "RecoveryAssumption",
    "TrainingConstructionError", "TrainingPlanBlueprintV2", "TrainingPlanConstructionEngine",
    "TrainingSessionBlueprint", "TrainingStructurePolicy",
    "TrainingRuntimeError", "build_training_plan",
    "DEFAULT_PROGRESSION_POLICY", "ExercisePerformance", "ProgressionBlueprint",
    "ProgressionDecision", "ProgressionDecisionType", "ProgressionEngine", "ProgressionPolicy",
    "RecoverySnapshot", "RecoveryState", "WorkoutResult",
    "DEFAULT_PROGRESSION_STATE_POLICY", "DeloadHistory", "ExerciseProgressState",
    "ProgressionCounters", "ProgressionEvent", "ProgressionHistory", "ProgressionStateEngine",
    "ProgressionStatePolicy",
    "LifecycleDecision", "PlanRevision", "PlanRevisionReason", "TrainingLifecycleEvent",
    "TrainingLifecycleOrchestrator",
    "LifecycleRuntimeResult", "advance_training_lifecycle", "recovery_from_payload",
    "workout_result_from_payload",
    "CompletedPrescription", "WorkoutCompletion", "completion_projection", "prescription_id",
    "validate_workout_completion_payload", "workout_completion_from_payload",
]
