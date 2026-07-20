"""Immutable domain objects for the isolated Training Engine foundation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_EXERCISE_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class MovementPattern(str, Enum):
    SQUAT = "squat"
    HINGE = "hinge"
    LUNGE = "lunge"
    HORIZONTAL_PUSH = "horizontal_push"
    HORIZONTAL_PULL = "horizontal_pull"
    VERTICAL_PUSH = "vertical_push"
    VERTICAL_PULL = "vertical_pull"
    CORE_ANTI_EXTENSION = "core_anti_extension"


class Equipment(str, Enum):
    BODYWEIGHT = "bodyweight"
    DUMBBELL = "dumbbell"
    BARBELL = "barbell"
    CABLE = "cable"
    RESISTANCE_BAND = "resistance_band"
    BENCH = "bench"
    PULLUP_BAR = "pullup_bar"


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class RotationPolicy(str, Enum):
    """Whether a supported exercise may rotate after its configured cycle."""

    SUCCESSOR = "successor"
    TERMINAL = "terminal"


def _version(value: str, field: str = "version") -> tuple[int, int, int]:
    if not isinstance(value, str) or not _SEMVER.fullmatch(value):
        raise ValueError(f"{field} must use major.minor.patch")
    return tuple(int(part) for part in value.split("."))


def _labels(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values or any(not isinstance(value, str) or not value or value != value.strip()
                         for value in values):
        raise ValueError(f"{field} must contain non-empty labels")
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must not contain duplicates")
    return values


@dataclass(frozen=True)
class ProgressionMetadata:
    strategy: str
    criteria: str
    next_exercise_ids: tuple[str, ...] = ()
    rotation_policy: RotationPolicy = RotationPolicy.TERMINAL

    def __post_init__(self) -> None:
        if not self.strategy or not self.criteria:
            raise ValueError("progression strategy and criteria are required")
        if not isinstance(self.rotation_policy, RotationPolicy):
            raise ValueError("progression requires an explicit rotation policy")
        if self.rotation_policy is RotationPolicy.SUCCESSOR and not self.next_exercise_ids:
            raise ValueError("successor rotation policy requires a successor")
        if self.rotation_policy is RotationPolicy.TERMINAL and self.next_exercise_ids:
            raise ValueError("terminal rotation policy cannot declare successors")
        for exercise_id in self.next_exercise_ids:
            if not _EXERCISE_ID.fullmatch(exercise_id):
                raise ValueError("progression reference has invalid exercise_id")


@dataclass(frozen=True)
class RegressionMetadata:
    strategy: str
    criteria: str
    prior_exercise_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.strategy or not self.criteria:
            raise ValueError("regression strategy and criteria are required")
        for exercise_id in self.prior_exercise_ids:
            if not _EXERCISE_ID.fullmatch(exercise_id):
                raise ValueError("regression reference has invalid exercise_id")


@dataclass(frozen=True)
class Exercise:
    """A versioned exercise definition; it does not prescribe a workout."""

    exercise_id: str
    version: str
    display_name: str
    primary_muscles: tuple[str, ...]
    secondary_muscles: tuple[str, ...]
    movement_pattern: MovementPattern
    equipment: frozenset[Equipment]
    difficulty: Difficulty
    training_tags: tuple[str, ...]
    safety_notes: tuple[str, ...]
    progression: ProgressionMetadata
    regression: RegressionMetadata
    prerequisite_exercise_ids: tuple[str, ...] = ()
    supersedes_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.exercise_id, str) or not _EXERCISE_ID.fullmatch(self.exercise_id):
            raise ValueError("exercise_id must be stable dotted lowercase identity")
        _version(self.version)
        if not isinstance(self.display_name, str) or not self.display_name or self.display_name != self.display_name.strip():
            raise ValueError("display_name is required")
        object.__setattr__(self, "primary_muscles", _labels(self.primary_muscles, "primary_muscles"))
        object.__setattr__(self, "secondary_muscles", _labels(self.secondary_muscles, "secondary_muscles"))
        object.__setattr__(self, "training_tags", _labels(self.training_tags, "training_tags"))
        object.__setattr__(self, "safety_notes", _labels(self.safety_notes, "safety_notes"))
        if not isinstance(self.movement_pattern, MovementPattern):
            raise ValueError("movement_pattern must use the movement taxonomy")
        if not isinstance(self.equipment, frozenset) or not self.equipment or any(not isinstance(item, Equipment) for item in self.equipment):
            raise ValueError("equipment must use the equipment taxonomy")
        if not isinstance(self.difficulty, Difficulty):
            raise ValueError("difficulty must use the difficulty taxonomy")
        if not isinstance(self.progression, ProgressionMetadata) or not isinstance(self.regression, RegressionMetadata):
            raise ValueError("exercise progression and regression metadata are required")
        if not isinstance(self.prerequisite_exercise_ids, tuple) or any(
                not _EXERCISE_ID.fullmatch(exercise_id) for exercise_id in self.prerequisite_exercise_ids):
            raise ValueError("exercise prerequisites have invalid exercise_id")
        if len(self.prerequisite_exercise_ids) != len(set(self.prerequisite_exercise_ids)):
            raise ValueError("exercise prerequisites must not contain duplicates")
        if self.supersedes_version is not None:
            if _version(self.supersedes_version, "supersedes_version") >= _version(self.version):
                raise ValueError("successor version must increase")


@dataclass(frozen=True)
class TrainingDay:
    day_id: str
    focus_tags: tuple[str, ...]
    exercise_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.day_id, str) or not self.day_id or self.day_id != self.day_id.strip():
            raise ValueError("training day identity is required")
        object.__setattr__(self, "focus_tags", _labels(self.focus_tags, "focus_tags"))
        if not isinstance(self.exercise_ids, tuple) or not self.exercise_ids or len(self.exercise_ids) != len(set(self.exercise_ids)):
            raise ValueError("training day requires unique exercise references")
        if any(not _EXERCISE_ID.fullmatch(item) for item in self.exercise_ids):
            raise ValueError("training day has invalid exercise reference")


@dataclass(frozen=True)
class TrainingWeek:
    week_number: int
    days: tuple[TrainingDay, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.week_number, int) or self.week_number < 1:
            raise ValueError("week_number must be positive")
        if not isinstance(self.days, tuple) or not self.days or len({day.day_id for day in self.days}) != len(self.days):
            raise ValueError("training week requires unique days")
        if any(not isinstance(day, TrainingDay) for day in self.days):
            raise ValueError("training week contains an invalid day")


@dataclass(frozen=True)
class TrainingPlanBlueprint:
    plan_id: str
    version: str
    recommendation_blueprint_id: str
    exercise_library_version: str
    weeks: tuple[TrainingWeek, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, str) or not self.plan_id or self.plan_id != self.plan_id.strip():
            raise ValueError("plan_id is required")
        _version(self.version)
        if not isinstance(self.recommendation_blueprint_id, str) or not self.recommendation_blueprint_id:
            raise ValueError("recommendation_blueprint_id is required")
        _version(self.exercise_library_version, "exercise_library_version")
        if not isinstance(self.weeks, tuple) or not self.weeks or tuple(week.week_number for week in self.weeks) != tuple(range(1, len(self.weeks) + 1)):
            raise ValueError("training plan weeks must be consecutive")
        if any(not isinstance(week, TrainingWeek) for week in self.weeks):
            raise ValueError("training plan contains an invalid week")
