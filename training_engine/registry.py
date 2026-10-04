"""Static, deterministic Exercise Knowledge Registry.

The registry only defines and resolves versioned exercises. It deliberately has
no selection, scheduling, prompt, renderer, persistence, or runtime behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .models import (
    Difficulty,
    Equipment,
    Exercise,
    MovementPattern,
    ProgressionMetadata,
    RegressionMetadata,
    RotationPolicy,
)


EXERCISE_LIBRARY_VERSION = "1.4.0"


@dataclass(frozen=True)
class ExerciseLibrary:
    version: str
    exercises: tuple[Exercise, ...]
    _by_identity: Mapping[tuple[str, str], Exercise] = field(init=False, repr=False, compare=False)
    _latest: Mapping[str, Exercise] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        try:
            _version_key(self.version)
        except (AttributeError, ValueError) as error:
            raise ValueError("exercise library version must use major.minor.patch") from error
        if not isinstance(self.exercises, tuple) or not self.exercises:
            raise ValueError("exercise library requires exercises")
        identities = [(item.exercise_id, item.version) for item in self.exercises]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate exercise identity")
        by_identity = {(item.exercise_id, item.version): item for item in self.exercises}
        latest = {}
        for item in self.exercises:
            current = latest.get(item.exercise_id)
            if current is None or _version_key(item.version) > _version_key(current.version):
                latest[item.exercise_id] = item
        for item in self.exercises:
            if item.supersedes_version is not None and (item.exercise_id, item.supersedes_version) not in by_identity:
                raise ValueError("exercise successor references a missing prior version")
            references = (item.progression.next_exercise_ids + item.regression.prior_exercise_ids
                          + item.prerequisite_exercise_ids)
            if any(reference not in latest for reference in references):
                raise ValueError("exercise metadata references an unknown exercise")
        object.__setattr__(self, "_by_identity", MappingProxyType(by_identity))
        object.__setattr__(self, "_latest", MappingProxyType(latest))

    def get(self, exercise_id: str, version: str | None = None) -> Exercise | None:
        return self._latest.get(exercise_id) if version is None else self._by_identity.get((exercise_id, version))

    def require(self, exercise_id: str, version: str | None = None) -> Exercise:
        exercise = self.get(exercise_id, version)
        if exercise is None:
            detail = exercise_id if version is None else f"{exercise_id}@{version}"
            raise KeyError(f"unknown exercise: {detail}")
        return exercise

    def by_movement(self, movement_pattern: MovementPattern) -> tuple[Exercise, ...]:
        return tuple(item for item in self.exercises if item.movement_pattern is movement_pattern)


def _version_key(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise ValueError("version must be a string")
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError("version must use major.minor.patch")
    return tuple(int(part) for part in parts)


def _exercise(exercise_id: str, name: str, primary: tuple[str, ...], secondary: tuple[str, ...],
              pattern: MovementPattern, equipment: frozenset[Equipment], difficulty: Difficulty,
              tags: tuple[str, ...], safety: tuple[str, ...], *, progression: tuple[str, ...] = (),
              regression: tuple[str, ...] = (), prerequisites: tuple[str, ...] = ()) -> Exercise:
    return Exercise(
        exercise_id=exercise_id, version="1.0.0", display_name=name,
        primary_muscles=primary, secondary_muscles=secondary,
        movement_pattern=pattern, equipment=equipment, difficulty=difficulty,
        training_tags=tags, safety_notes=safety,
        progression=ProgressionMetadata(
            "progressive overload", "maintain controlled form", progression,
            RotationPolicy.SUCCESSOR if progression else RotationPolicy.TERMINAL,
        ),
        regression=RegressionMetadata("reduce complexity", "maintain pain-free range", regression),
        prerequisite_exercise_ids=prerequisites,
    )


# Released tuples are append-only catalog boundaries, never slices of the current catalog.
_EXERCISES_V1_2 = (
    _exercise("bodyweight.wall_push_up", "Wall Push-Up", ("chest",), ("triceps", "anterior_deltoid"),
              MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.BODYWEIGHT}), Difficulty.BEGINNER,
              ("upper_body", "push", "home"),
              ("Keep the body in one line and use a pain-free range.",),
              progression=("bodyweight.incline_push_up",)),
    _exercise("bodyweight.incline_push_up", "Incline Push-Up", ("chest",), ("triceps", "anterior_deltoid"),
              MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.BODYWEIGHT, Equipment.BENCH}), Difficulty.BEGINNER,
              ("upper_body", "push", "home"), ("Use a stable elevated surface.",),
              progression=("bodyweight.push_up",), regression=("bodyweight.wall_push_up",)),
    _exercise("bodyweight.push_up", "Push-Up", ("chest",), ("triceps", "anterior_deltoid"),
              MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.BODYWEIGHT}), Difficulty.INTERMEDIATE,
              ("upper_body", "push", "home"), ("Maintain a neutral trunk.",),
              regression=("bodyweight.incline_push_up",)),
    _exercise("bodyweight.table_row", "Table Row", ("lats",), ("biceps", "mid_back"),
              MovementPattern.HORIZONTAL_PULL, frozenset({Equipment.BODYWEIGHT}), Difficulty.BEGINNER,
              ("upper_body", "pull", "home"),
              ("Use only a stable, load-bearing table and keep the body rigid.",),
              progression=("dumbbell.row",)),
    _exercise("bodyweight.squat", "Bodyweight Squat", ("quadriceps", "glutes"), ("hamstrings",),
              MovementPattern.SQUAT, frozenset({Equipment.BODYWEIGHT}), Difficulty.BEGINNER,
              ("lower_body", "squat", "home"), ("Use a comfortable depth with controlled knees.",),
              progression=("dumbbell.goblet_squat",)),
    _exercise("dumbbell.goblet_squat", "Goblet Squat", ("quadriceps", "glutes"), ("hamstrings", "core"),
              MovementPattern.SQUAT, frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE,
              ("lower_body", "squat"), ("Keep the load close to the chest.",),
              regression=("bodyweight.squat",)),
    _exercise("bodyweight.reverse_lunge", "Reverse Lunge", ("quadriceps", "glutes"), ("hamstrings", "calves"),
              MovementPattern.LUNGE, frozenset({Equipment.BODYWEIGHT}), Difficulty.BEGINNER,
              ("lower_body", "unilateral", "home"), ("Use a stable range and controlled balance.",)),
    _exercise("bodyweight.hip_hinge", "Bodyweight Hip Hinge", ("hamstrings", "glutes"), ("erectors",),
              MovementPattern.HINGE, frozenset({Equipment.BODYWEIGHT}), Difficulty.BEGINNER,
              ("lower_body", "hinge", "home"), ("Keep the spine neutral through the movement.",),
              progression=("dumbbell.romanian_deadlift",)),
    _exercise("dumbbell.romanian_deadlift", "Dumbbell Romanian Deadlift", ("hamstrings", "glutes"), ("erectors", "forearms"),
              MovementPattern.HINGE, frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE,
              ("lower_body", "hinge"), ("Keep the load close and spine neutral.",)),
    _exercise("dumbbell.row", "Dumbbell Row", ("lats",), ("biceps", "mid_back"),
              MovementPattern.HORIZONTAL_PULL, frozenset({Equipment.DUMBBELL}), Difficulty.BEGINNER,
              ("upper_body", "pull"), ("Avoid twisting through the torso.",)),
    _exercise("band.row", "Resistance-Band Row", ("lats",), ("biceps", "mid_back"),
              MovementPattern.HORIZONTAL_PULL, frozenset({Equipment.RESISTANCE_BAND}), Difficulty.BEGINNER,
              ("upper_body", "pull", "home"), ("Anchor the band securely before pulling.",)),
    _exercise("dumbbell.overhead_press", "Dumbbell Overhead Press", ("deltoids",), ("triceps", "upper_chest"),
              MovementPattern.VERTICAL_PUSH, frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE,
              ("upper_body", "push"), ("Use a pain-free overhead range.",)),
    _exercise("dumbbell.seated_press", "Seated Dumbbell Press", ("deltoids",), ("triceps", "upper_chest"),
              MovementPattern.VERTICAL_PUSH, frozenset({Equipment.DUMBBELL, Equipment.BENCH}), Difficulty.BEGINNER,
              ("upper_body", "push"), ("Keep the back supported and use a pain-free range.",),
              progression=("dumbbell.overhead_press",)),
    _exercise("bodyweight.pull_up", "Pull-Up", ("lats",), ("biceps", "mid_back"),
              MovementPattern.VERTICAL_PULL, frozenset({Equipment.PULLUP_BAR}), Difficulty.ADVANCED,
              ("upper_body", "pull"), ("Use a stable bar and controlled shoulder position.",),
              prerequisites=("band.row",)),
    _exercise("bodyweight.plank", "Front Plank", ("core",), ("shoulders", "glutes"),
              MovementPattern.CORE_ANTI_EXTENSION, frozenset({Equipment.BODYWEIGHT}), Difficulty.BEGINNER,
              ("core", "home"), ("Stop before the lower back loses neutral position.",)),
    _exercise("barbell.back_squat", "Barbell Back Squat", ("quadriceps", "glutes"), ("hamstrings", "core"),
              MovementPattern.SQUAT, frozenset({Equipment.BARBELL}), Difficulty.ADVANCED,
              ("lower_body", "squat", "barbell"), ("Use safety supports and controlled depth.",),
              regression=("dumbbell.goblet_squat",)),
    _exercise("dumbbell.floor_press", "Dumbbell Floor Press", ("chest",), ("triceps", "anterior_deltoid"),
              MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE,
              ("upper_body", "push", "home"), ("Keep the upper arm controlled against the floor range.",)),
    _exercise("band.chest_press", "Resistance-Band Chest Press", ("chest",), ("triceps", "anterior_deltoid"),
              MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.RESISTANCE_BAND}), Difficulty.BEGINNER,
              ("upper_body", "push", "home"), ("Secure the anchor before each set.",)),
    _exercise("cable.chest_press", "Cable Chest Press", ("chest",), ("triceps", "anterior_deltoid"),
              MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.CABLE}), Difficulty.INTERMEDIATE,
              ("upper_body", "push", "gym"), ("Set both handles evenly and keep the torso stable.",)),
    _exercise("dumbbell.chest_supported_row", "Chest-Supported Dumbbell Row", ("lats",), ("biceps", "mid_back"),
              MovementPattern.HORIZONTAL_PULL, frozenset({Equipment.DUMBBELL, Equipment.BENCH}), Difficulty.ADVANCED,
              ("upper_body", "pull"), ("Keep the chest supported and avoid shrugging.",)),
    _exercise("cable.seated_row", "Cable Seated Row", ("lats",), ("biceps", "mid_back"),
              MovementPattern.HORIZONTAL_PULL, frozenset({Equipment.CABLE}), Difficulty.ADVANCED,
              ("upper_body", "pull", "gym"), ("Keep the torso still as the handle travels to the ribs.",)),
    _exercise("band.lat_pulldown", "Resistance-Band Lat Pulldown", ("lats",), ("biceps", "mid_back"),
              MovementPattern.VERTICAL_PULL, frozenset({Equipment.RESISTANCE_BAND}), Difficulty.BEGINNER,
              ("upper_body", "pull", "home"), ("Use a secure high anchor and a controlled path.",)),
    _exercise("cable.lat_pulldown", "Cable Lat Pulldown", ("lats",), ("biceps", "mid_back"),
              MovementPattern.VERTICAL_PULL, frozenset({Equipment.CABLE}), Difficulty.INTERMEDIATE,
              ("upper_body", "pull", "gym"), ("Pull to a comfortable upper-chest position without leaning back.",)),
    _exercise("dumbbell.split_squat", "Dumbbell Split Squat", ("quadriceps", "glutes"), ("hamstrings", "core"),
              MovementPattern.LUNGE, frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE,
              ("lower_body", "unilateral"), ("Use a stable stance and a controlled range.",)),
    _exercise("dumbbell.step_up", "Dumbbell Step-Up", ("quadriceps", "glutes"), ("calves", "core"),
              MovementPattern.LUNGE, frozenset({Equipment.DUMBBELL, Equipment.BENCH}), Difficulty.BEGINNER,
              ("lower_body", "unilateral"), ("Use a stable step and control the descent.",)),
    _exercise("bodyweight.glute_bridge", "Glute Bridge", ("glutes",), ("hamstrings", "core"),
              MovementPattern.HINGE, frozenset({Equipment.BODYWEIGHT}), Difficulty.BEGINNER,
              ("lower_body", "hinge", "home"), ("Keep ribs down and drive through the feet.",)),
    _exercise("cable.pull_through", "Cable Pull-Through", ("glutes", "hamstrings"), ("erectors",),
              MovementPattern.HINGE, frozenset({Equipment.CABLE}), Difficulty.INTERMEDIATE,
              ("lower_body", "hinge", "gym"), ("Keep the cable close and finish with the hips, not the back.",)),
    _exercise("barbell.romanian_deadlift", "Barbell Romanian Deadlift", ("hamstrings", "glutes"), ("erectors", "forearms"),
              MovementPattern.HINGE, frozenset({Equipment.BARBELL}), Difficulty.ADVANCED,
              ("lower_body", "hinge", "barbell"), ("Keep the bar close and stop before spinal position changes.",),
              regression=("dumbbell.romanian_deadlift",)),
    _exercise("bodyweight.dead_bug", "Dead Bug", ("core",), ("hip_flexors",),
              MovementPattern.CORE_ANTI_EXTENSION, frozenset({Equipment.BODYWEIGHT}), Difficulty.ADVANCED,
              ("core", "home"), ("Keep the lower back gently controlled against the floor.",)),
    _exercise("band.pallof_press", "Resistance-Band Pallof Press", ("core",), ("obliques", "shoulders"),
              MovementPattern.CORE_ANTI_EXTENSION, frozenset({Equipment.RESISTANCE_BAND}), Difficulty.BEGINNER,
              ("core", "home"), ("Use a secure anchor and resist rotation without holding your breath.",)),
)

_EXERCISES_V1_3 = _EXERCISES_V1_2 + (
    _exercise("bodyweight.march_in_place", "March in Place", ("calves",), ("glutes", "core"),
              MovementPattern.MONOSTRUCTURAL, frozenset({Equipment.BODYWEIGHT}), Difficulty.BEGINNER,
              ("monostructural", "conditioning", "home"),
              ("Use a comfortable pace; stop if the movement is painful.",)),
)


_EXERCISES_V1_4 = _EXERCISES_V1_3 + (
    _exercise("dumbbell.bench_press", "Dumbbell Bench Press", ("chest",), ("triceps", "anterior_deltoid"),
              MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.DUMBBELL, Equipment.BENCH}), Difficulty.INTERMEDIATE,
              ("upper_body", "push"), ("Use a stable bench and a controlled, pain-free shoulder range.",),
              regression=("dumbbell.floor_press",)),
    _exercise("barbell.bench_press", "Barbell Bench Press", ("chest",), ("triceps", "anterior_deltoid"),
              MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.BARBELL, Equipment.BENCH}), Difficulty.ADVANCED,
              ("upper_body", "push", "barbell"),
              ("Use a stable bench, rack and correctly set safety arms or a competent spotter; never bounce the bar.",),
              regression=("dumbbell.bench_press",)),
    _exercise("dumbbell.bent_over_row", "Dumbbell Bent-Over Row", ("lats", "mid_back"),
              ("biceps", "posterior_deltoid", "erectors"),
              MovementPattern.HORIZONTAL_PULL, frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE,
              ("upper_body", "pull"), ("Maintain a stable hip hinge and avoid using trunk momentum.",),
              regression=("dumbbell.row",)),
    _exercise("bodyweight.negative_pull_up", "Negative Pull-Up", ("lats",), ("biceps", "mid_back"),
              MovementPattern.VERTICAL_PULL, frozenset({Equipment.PULLUP_BAR}), Difficulty.INTERMEDIATE,
              ("upper_body", "pull"),
              ("Use a secure bar and a stable way to reach the top; lower under control without dropping or swinging.",),
              progression=("bodyweight.pull_up",), regression=("band.lat_pulldown",)),
    _exercise("dumbbell.reverse_lunge", "Dumbbell Reverse Lunge", ("quadriceps", "glutes"),
              ("hamstrings", "calves", "core"),
              MovementPattern.LUNGE, frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE,
              ("lower_body", "unilateral"), ("Keep the front knee aligned with the foot and control balance and depth.",),
              regression=("bodyweight.reverse_lunge",)),
    _exercise("dumbbell.front_squat", "Dumbbell Front Squat", ("quadriceps", "glutes"),
              ("hamstrings", "core", "upper_back"),
              MovementPattern.SQUAT, frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE,
              ("lower_body", "squat"), ("Keep the dumbbells supported at shoulder height; do not press them overhead.",),
              regression=("dumbbell.goblet_squat",)),
    _exercise("barbell.deadlift", "Barbell Deadlift", ("glutes", "hamstrings", "quadriceps"),
              ("erectors", "forearms", "upper_back"),
              MovementPattern.HINGE, frozenset({Equipment.BARBELL}), Difficulty.ADVANCED,
              ("lower_body", "hinge", "barbell"),
              ("Brace before lifting, keep the bar close and stop if a neutral spine cannot be maintained.",),
              regression=("dumbbell.romanian_deadlift",)),
    _exercise("bodyweight.hollow_hold", "Hollow Body Hold", ("core",), ("hip_flexors",),
              MovementPattern.CORE_ANTI_EXTENSION, frozenset({Equipment.BODYWEIGHT}), Difficulty.INTERMEDIATE,
              ("core", "home"), ("Keep arms beside the trunk, the low back on the floor and breathe; shorten the lever if it arches.",),
              regression=("bodyweight.plank",)),
    _exercise("dumbbell.push_press", "Dumbbell Push Press", ("deltoids",),
              ("triceps", "quadriceps", "glutes", "core"),
              MovementPattern.VERTICAL_PUSH, frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE,
              ("upper_body", "push"),
              ("Use controlled leg drive and a pain-free overhead range without lumbar extension; avoid under overhead restrictions.",),
              regression=("dumbbell.overhead_press",)),
)

_LIBRARIES = MappingProxyType({
    "1.2.0": ExerciseLibrary("1.2.0", _EXERCISES_V1_2),
    "1.3.0": ExerciseLibrary("1.3.0", _EXERCISES_V1_3),
    "1.4.0": ExerciseLibrary("1.4.0", _EXERCISES_V1_4),
})


def load_exercise_library(version: str | None = None) -> ExerciseLibrary:
    """Resolve the recorded catalog version for immutable plan replay."""
    try:
        return _LIBRARIES[EXERCISE_LIBRARY_VERSION if version is None else version]
    except KeyError as error:
        raise ValueError("unknown exercise library version") from error
