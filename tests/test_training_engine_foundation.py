"""Training Engine V2 foundation: static knowledge only, no workout planning."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from training_engine import (
    Difficulty,
    Equipment,
    Exercise,
    ExerciseLibrary,
    MovementPattern,
    ProgressionMetadata,
    RegressionMetadata,
    RotationPolicy,
    TrainingDay,
    TrainingPlanBlueprint,
    TrainingWeek,
    load_exercise_library,
)


def test_default_registry_has_stable_versioned_exercise_taxonomy():
    library = load_exercise_library()

    assert library.version == "1.1.0"
    assert library is load_exercise_library()
    assert len(library.exercises) == 16
    assert {item.movement_pattern for item in library.exercises} == set(MovementPattern)
    assert {Equipment.BODYWEIGHT, Equipment.DUMBBELL, Equipment.BARBELL,
            Equipment.RESISTANCE_BAND, Equipment.PULLUP_BAR} <= {
                equipment for item in library.exercises for equipment in item.equipment
            }
    for item in library.exercises:
        assert item.version == "1.0.0"
        assert item.primary_muscles and item.secondary_muscles
        assert item.training_tags and item.safety_notes
        assert item.progression.strategy and item.regression.strategy


def test_registry_lookup_is_exact_and_latest_version_is_deterministic():
    default = load_exercise_library()
    base = default.require("bodyweight.squat")
    successor = replace(base, version="1.1.0", supersedes_version="1.0.0")
    library = ExerciseLibrary("1.1.0", default.exercises + (successor,))

    assert library.require("bodyweight.squat") == successor
    assert library.require("bodyweight.squat", "1.0.0") == base
    assert library.require("bodyweight.squat", "1.1.0") == successor
    assert library.get("missing.exercise") is None
    with pytest.raises(KeyError, match="unknown exercise"):
        library.require("missing.exercise")


def test_registry_rejects_duplicate_version_and_dangling_metadata_references():
    default = load_exercise_library()
    base = default.require("bodyweight.squat")
    with pytest.raises(ValueError, match="duplicate exercise identity"):
        ExerciseLibrary("1.0.0", (base, base))

    bad_metadata = replace(
        base,
        progression=ProgressionMetadata(
            "progressive overload", "controlled form", ("missing.exercise",), RotationPolicy.SUCCESSOR,
        ),
    )
    with pytest.raises(ValueError, match="unknown exercise"):
        ExerciseLibrary("1.0.0", tuple(bad_metadata if item == base else item for item in default.exercises))

    bad_successor = replace(base, version="1.1.0", supersedes_version="0.9.0")
    with pytest.raises(ValueError, match="missing prior version"):
        ExerciseLibrary("1.1.0", default.exercises + (bad_successor,))


def test_domain_models_are_immutable_and_reject_untyped_or_invalid_values():
    base = load_exercise_library().require("bodyweight.squat")
    with pytest.raises(FrozenInstanceError):
        base.display_name = "Changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="primary_muscles"):
        replace(base, primary_muscles=["quadriceps"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stable dotted lowercase"):
        replace(base, exercise_id="Squat")
    with pytest.raises(ValueError, match="movement taxonomy"):
        replace(base, movement_pattern="squat")  # type: ignore[arg-type]


def test_future_training_plan_models_are_immutable_and_reference_stable_ids():
    day = TrainingDay("day-1", ("full_body",), ("bodyweight.squat", "bodyweight.push_up"))
    week = TrainingWeek(1, (day,))
    blueprint = TrainingPlanBlueprint("training-plan-1", "1.0.0", "rec-1", "1.0.0", (week,))

    assert blueprint.weeks[0].days[0].exercise_ids == ("bodyweight.squat", "bodyweight.push_up")
    with pytest.raises(FrozenInstanceError):
        blueprint.plan_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="consecutive"):
        TrainingPlanBlueprint("training-plan-2", "1.0.0", "rec-1", "1.0.0", (TrainingWeek(2, (day,)),))


def test_training_foundation_is_isolated_from_runtime_prompt_and_network_dependencies():
    package = Path(__file__).parents[1] / "training_engine"
    forbidden = ("import app", "from app", "import db", "openai", "requests.", "flask",
                 "conversation_composer", "recommend.architect", "chat.completions")
    for source_file in package.glob("*.py"):
        source = source_file.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{source_file.name} references {token}"
