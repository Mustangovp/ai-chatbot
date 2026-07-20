"""Deterministic exercise selection over the immutable Exercise Library.

This module selects a balanced set of exercise identities only. It does not
create a workout prescription, invoke an LLM, or interact with runtime code.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Difficulty, Equipment, Exercise, MovementPattern
from .registry import ExerciseLibrary


class TrainingGoal(str, Enum):
    MUSCLE_GAIN = "muscle_gain"
    FAT_LOSS = "fat_loss"
    MAINTENANCE = "maintenance"


class TrainingSplit(str, Enum):
    FULL_BODY = "full_body"
    UPPER_LOWER = "upper_lower"
    PUSH_PULL_LEGS = "push_pull_legs"


class SelectionOutcome(str, Enum):
    SELECTED = "selected"
    REJECTED = "rejected"


_DIFFICULTY_RANK = {
    Difficulty.BEGINNER: 1,
    Difficulty.INTERMEDIATE: 2,
    Difficulty.ADVANCED: 3,
}
_CORE_BALANCE = (
    MovementPattern.SQUAT,
    MovementPattern.HINGE,
    MovementPattern.HORIZONTAL_PUSH,
    MovementPattern.HORIZONTAL_PULL,
    MovementPattern.CORE_ANTI_EXTENSION,
)

_SPLIT_SESSION_PATTERNS = {
    TrainingSplit.FULL_BODY: (_CORE_BALANCE,),
    TrainingSplit.UPPER_LOWER: (
        (MovementPattern.HORIZONTAL_PUSH, MovementPattern.HORIZONTAL_PULL,
         MovementPattern.VERTICAL_PUSH),
        (MovementPattern.SQUAT, MovementPattern.HINGE, MovementPattern.LUNGE,
         MovementPattern.CORE_ANTI_EXTENSION),
    ),
    TrainingSplit.PUSH_PULL_LEGS: (
        (MovementPattern.HORIZONTAL_PUSH, MovementPattern.VERTICAL_PUSH),
        (MovementPattern.HORIZONTAL_PULL,),
        (MovementPattern.SQUAT, MovementPattern.HINGE, MovementPattern.LUNGE,
         MovementPattern.CORE_ANTI_EXTENSION),
    ),
}

_SPLIT_ALIASES = {
    "full_body": TrainingSplit.FULL_BODY,
    "full body": TrainingSplit.FULL_BODY,
    "upper_lower": TrainingSplit.UPPER_LOWER,
    "upper/lower": TrainingSplit.UPPER_LOWER,
    "upper lower": TrainingSplit.UPPER_LOWER,
    "push_pull_legs": TrainingSplit.PUSH_PULL_LEGS,
    "push/pull/legs": TrainingSplit.PUSH_PULL_LEGS,
    "push pull legs": TrainingSplit.PUSH_PULL_LEGS,
    "ppl": TrainingSplit.PUSH_PULL_LEGS,
}


def resolve_training_split(value: object) -> TrainingSplit:
    if isinstance(value, TrainingSplit):
        return value
    key = str(value or "").strip().lower()
    if not key:
        return TrainingSplit.FULL_BODY
    try:
        return _SPLIT_ALIASES[key]
    except KeyError as error:
        raise ValueError("unsupported training split") from error


@dataclass(frozen=True)
class TrainingGoalPolicy:
    version: str
    goal: TrainingGoal
    required_patterns: tuple[MovementPattern, ...]
    prefer_highest_compatible_difficulty: bool
    split: TrainingSplit = TrainingSplit.FULL_BODY
    session_patterns: tuple[tuple[MovementPattern, ...], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("training goal policy version is required")
        if not isinstance(self.goal, TrainingGoal):
            raise ValueError("training goal policy requires a training goal")
        if not isinstance(self.required_patterns, tuple) or not self.required_patterns:
            raise ValueError("training goal policy requires movement patterns")
        if len(self.required_patterns) != len(set(self.required_patterns)):
            raise ValueError("training goal policy patterns must not repeat")
        if any(not isinstance(pattern, MovementPattern) for pattern in self.required_patterns):
            raise ValueError("training goal policy uses an invalid movement pattern")
        if not isinstance(self.split, TrainingSplit):
            raise ValueError("training goal policy requires a supported split")
        sessions = self.session_patterns or (self.required_patterns,)
        if not isinstance(sessions, tuple) or not sessions:
            raise ValueError("training goal policy requires split session patterns")
        patterns = tuple(pattern for session in sessions for pattern in session)
        if not patterns or len(patterns) != len(set(patterns)) or patterns != self.required_patterns:
            raise ValueError("training goal policy patterns must not repeat across a split")
        if any(not isinstance(session, tuple) or not session for session in sessions):
            raise ValueError("training goal policy sessions must be non-empty tuples")
        if any(not isinstance(pattern, MovementPattern) for pattern in patterns):
            raise ValueError("training goal policy uses an invalid movement pattern")
        object.__setattr__(self, "session_patterns", sessions)


def training_goal_policy(goal: TrainingGoal, split: TrainingSplit = TrainingSplit.FULL_BODY) -> TrainingGoalPolicy:
    if not isinstance(goal, TrainingGoal) or not isinstance(split, TrainingSplit):
        raise ValueError("training goal policy requires typed goal and split")
    return TrainingGoalPolicy(
        version=f"training-goal-policy-v1:{split.value}",
        goal=goal,
        required_patterns=tuple(pattern for session in _SPLIT_SESSION_PATTERNS[split] for pattern in session),
        prefer_highest_compatible_difficulty=goal is TrainingGoal.MUSCLE_GAIN,
        split=split,
        session_patterns=_SPLIT_SESSION_PATTERNS[split],
    )


DEFAULT_TRAINING_GOAL_POLICIES = {
    goal: training_goal_policy(goal) for goal in TrainingGoal
}


@dataclass(frozen=True)
class TrainingSafetyConstraints:
    excluded_exercise_ids: frozenset[str] = frozenset()
    excluded_movement_patterns: frozenset[MovementPattern] = frozenset()
    excluded_training_tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.excluded_exercise_ids, frozenset) or any(
                not isinstance(item, str) or not item for item in self.excluded_exercise_ids):
            raise ValueError("excluded exercise ids must be a frozen set of identities")
        if not isinstance(self.excluded_movement_patterns, frozenset) or any(
                not isinstance(item, MovementPattern) for item in self.excluded_movement_patterns):
            raise ValueError("excluded movement patterns must use the movement taxonomy")
        if not isinstance(self.excluded_training_tags, frozenset) or any(
                not isinstance(item, str) or not item for item in self.excluded_training_tags):
            raise ValueError("excluded training tags must be a frozen set")


@dataclass(frozen=True)
class TrainingSelectionRequest:
    recommendation_blueprint_id: str
    goal: TrainingGoal
    experience_level: Difficulty
    available_equipment: frozenset[Equipment]
    muscle_priorities: tuple[str, ...]
    requested_split: TrainingSplit = TrainingSplit.FULL_BODY
    safety: TrainingSafetyConstraints = TrainingSafetyConstraints()
    policy: TrainingGoalPolicy | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.recommendation_blueprint_id, str) or not self.recommendation_blueprint_id:
            raise ValueError("recommendation_blueprint_id is required")
        if not isinstance(self.goal, TrainingGoal) or not isinstance(self.experience_level, Difficulty):
            raise ValueError("goal and experience_level must use their taxonomies")
        if not isinstance(self.available_equipment, frozenset) or not self.available_equipment or any(
                not isinstance(item, Equipment) for item in self.available_equipment):
            raise ValueError("available_equipment must be a non-empty equipment set")
        if not isinstance(self.muscle_priorities, tuple) or len(self.muscle_priorities) != len(set(self.muscle_priorities)):
            raise ValueError("muscle_priorities must be a unique tuple")
        if any(not isinstance(item, str) or not item or item != item.strip() for item in self.muscle_priorities):
            raise ValueError("muscle_priorities contain an invalid label")
        if not isinstance(self.requested_split, TrainingSplit):
            raise ValueError("requested_split must use the split taxonomy")
        if not isinstance(self.safety, TrainingSafetyConstraints):
            raise ValueError("safety must be TrainingSafetyConstraints")
        if self.policy is not None and (self.policy.goal is not self.goal
                                        or self.policy.split is not self.requested_split):
            raise ValueError("goal policy does not match requested goal and split")

    @property
    def resolved_policy(self) -> TrainingGoalPolicy:
        return self.policy or training_goal_policy(self.goal, self.requested_split)


@dataclass(frozen=True)
class ExerciseSelection:
    exercise_id: str
    exercise_version: str
    movement_pattern: MovementPattern
    selection_reason: str


@dataclass(frozen=True)
class ExerciseSelectionBlueprint:
    blueprint_id: str
    version: str
    recommendation_blueprint_id: str
    exercise_library_version: str
    policy_version: str
    goal: TrainingGoal
    experience_level: Difficulty
    training_split: TrainingSplit
    selections: tuple[ExerciseSelection, ...]

    def __post_init__(self) -> None:
        if not self.blueprint_id or not self.version or not self.recommendation_blueprint_id:
            raise ValueError("selection blueprint identity is required")
        if not self.exercise_library_version or not self.policy_version:
            raise ValueError("selection blueprint version provenance is required")
        if not isinstance(self.training_split, TrainingSplit):
            raise ValueError("selection blueprint requires a supported split")
        if not self.selections or len({item.exercise_id for item in self.selections}) != len(self.selections):
            raise ValueError("selection blueprint requires unique exercises")
        patterns = tuple(item.movement_pattern for item in self.selections)
        if len(set(patterns)) != len(patterns):
            raise ValueError("selection blueprint requires balanced unique movement patterns")


@dataclass(frozen=True)
class TrainingSelectionResult:
    outcome: SelectionOutcome
    blueprint: ExerciseSelectionBlueprint | None
    rejection_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.outcome is SelectionOutcome.SELECTED:
            if self.blueprint is None or self.rejection_reasons:
                raise ValueError("selected result requires only a blueprint")
        elif self.blueprint is not None or not self.rejection_reasons:
            raise ValueError("rejected result requires explicit rejection reasons")


class TrainingSelectionEngine:
    """Resolve exactly one compatible exercise for every required pattern."""

    @classmethod
    def select(cls, library: ExerciseLibrary, request: TrainingSelectionRequest) -> TrainingSelectionResult:
        if not isinstance(library, ExerciseLibrary):
            raise ValueError("selection requires an ExerciseLibrary")
        policy = request.resolved_policy
        selections = []
        rejected = []
        for pattern in policy.required_patterns:
            candidates = cls._eligible(library, request, pattern)
            if not candidates:
                rejected.append(f"required_pattern_unavailable:{pattern.value}")
                continue
            chosen = min(candidates, key=lambda exercise: cls._rank(exercise, request, policy))
            priority = "priority" if set(chosen.primary_muscles).intersection(request.muscle_priorities) else "balance"
            selections.append(ExerciseSelection(
                chosen.exercise_id, chosen.version, pattern,
                f"goal:{request.goal.value};{priority}:{pattern.value};equipment_compatible",
            ))
        if rejected:
            return TrainingSelectionResult(SelectionOutcome.REJECTED, None, tuple(rejected))
        blueprint = ExerciseSelectionBlueprint(
            blueprint_id=cls._blueprint_id(library, request, tuple(selections)),
            version="training-selection-blueprint-v1",
            recommendation_blueprint_id=request.recommendation_blueprint_id,
            exercise_library_version=library.version,
            policy_version=policy.version,
            goal=request.goal,
            experience_level=request.experience_level,
            training_split=policy.split,
            selections=tuple(selections),
        )
        return TrainingSelectionResult(SelectionOutcome.SELECTED, blueprint, ())

    @staticmethod
    def _eligible(library: ExerciseLibrary, request: TrainingSelectionRequest,
                  pattern: MovementPattern) -> tuple[Exercise, ...]:
        eligible = []
        for exercise in library.by_movement(pattern):
            if exercise.exercise_id in request.safety.excluded_exercise_ids:
                continue
            if pattern in request.safety.excluded_movement_patterns:
                continue
            if set(exercise.training_tags).intersection(request.safety.excluded_training_tags):
                continue
            if not exercise.equipment.issubset(request.available_equipment):
                continue
            if _DIFFICULTY_RANK[exercise.difficulty] > _DIFFICULTY_RANK[request.experience_level]:
                continue
            prerequisites = tuple(library.get(item) for item in exercise.prerequisite_exercise_ids)
            if any(item is None or not item.equipment.issubset(request.available_equipment)
                   or _DIFFICULTY_RANK[item.difficulty] > _DIFFICULTY_RANK[request.experience_level]
                   for item in prerequisites):
                continue
            eligible.append(exercise)
        return tuple(eligible)

    @staticmethod
    def _rank(exercise: Exercise, request: TrainingSelectionRequest,
              policy: TrainingGoalPolicy) -> tuple[int, int, str]:
        priority = len(set(exercise.primary_muscles).intersection(request.muscle_priorities))
        difficulty = _DIFFICULTY_RANK[exercise.difficulty]
        preferred_difficulty = -difficulty if policy.prefer_highest_compatible_difficulty else difficulty
        return (-priority, preferred_difficulty, exercise.exercise_id)

    @staticmethod
    def _blueprint_id(library: ExerciseLibrary, request: TrainingSelectionRequest,
                      selections: tuple[ExerciseSelection, ...]) -> str:
        parts = ";".join(f"{item.exercise_id}@{item.exercise_version}" for item in selections)
        return (f"selection:{request.recommendation_blueprint_id}:{library.version}:"
                f"{request.goal.value}:{request.requested_split.value}:{parts}")
