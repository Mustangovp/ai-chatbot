"""Versioned registry replay and the nine v1.4 exercise delivery contracts."""
from dataclasses import asdict
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from training_engine import (
    Difficulty, Equipment, MovementPattern, PrescriptionRule, RecoveryAssumption,
    SelectionOutcome, TrainingGoal, TrainingGoalPolicy, TrainingPlanConstructionEngine,
    TrainingSafetyConstraints, TrainingSelectionEngine, TrainingSelectionRequest,
    TrainingStructurePolicy, build_training_plan, load_exercise_library,
)
from training_engine.lineage import delivered_plan_lineage, plan_from_delivered_lineage
from training_engine.renderer import render_completion_projection, render_delivery


NEW_EXERCISES = (
    ("dumbbell.bench_press", "Dumbbell Bench Press", MovementPattern.HORIZONTAL_PUSH,
     frozenset({Equipment.DUMBBELL, Equipment.BENCH}), Difficulty.INTERMEDIATE),
    ("barbell.bench_press", "Barbell Bench Press", MovementPattern.HORIZONTAL_PUSH,
     frozenset({Equipment.BARBELL, Equipment.BENCH}), Difficulty.ADVANCED),
    ("dumbbell.bent_over_row", "Dumbbell Bent-Over Row", MovementPattern.HORIZONTAL_PULL,
     frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE),
    ("bodyweight.negative_pull_up", "Negative Pull-Up", MovementPattern.VERTICAL_PULL,
     frozenset({Equipment.PULLUP_BAR}), Difficulty.INTERMEDIATE),
    ("dumbbell.reverse_lunge", "Dumbbell Reverse Lunge", MovementPattern.LUNGE,
     frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE),
    ("dumbbell.front_squat", "Dumbbell Front Squat", MovementPattern.SQUAT,
     frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE),
    ("barbell.deadlift", "Barbell Deadlift", MovementPattern.HINGE,
     frozenset({Equipment.BARBELL}), Difficulty.ADVANCED),
    ("bodyweight.hollow_hold", "Hollow Body Hold", MovementPattern.CORE_ANTI_EXTENSION,
     frozenset({Equipment.BODYWEIGHT}), Difficulty.INTERMEDIATE),
    ("dumbbell.push_press", "Dumbbell Push Press", MovementPattern.VERTICAL_PUSH,
     frozenset({Equipment.DUMBBELL}), Difficulty.INTERMEDIATE),
)


def _encode(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(type(value).__name__)


@pytest.mark.parametrize("version,count,fingerprint", (
    ("1.2.0", 30, "1aff5810a05dfaf0a6185bf81a8cb65c71520ab3fd6a991ae23631bf4bcd4d97"),
    ("1.3.0", 31, "45741b90d47b951525498db01a7f30bdcf570c8d4718a4444ed3f08ea0687f39"),
))
def test_released_registry_definitions_match_pre_expansion_fingerprints(version, count, fingerprint):
    # Captured from 05c7543 before expansion, including order and every metadata field.
    library = load_exercise_library(version)
    payload = json.dumps([asdict(item) for item in library.exercises], default=_encode,
                         sort_keys=True, separators=(",", ":")).encode()
    assert len(library.exercises) == count
    assert hashlib.sha256(payload).hexdigest() == fingerprint


@pytest.mark.parametrize("version", ("1.2.0", "1.3.0"))
def test_recorded_plan_replays_with_its_original_library_and_prescription(version):
    library = load_exercise_library(version)
    plan = build_training_plan(
        recommendation_blueprint_id="released-plan-replay", library=library,
        facts={"goal": "strength", "level": "intermediate", "equipment": "gym",
               "recoveryFeel": "fresh"},
    )
    record = json.loads(json.dumps(delivered_plan_lineage(plan)))
    replay = plan_from_delivered_lineage(record)
    replay_library = load_exercise_library(replay.exercise_library_version)
    assert replay == plan
    assert replay_library is library
    assert not {item.exercise_id for item in replay.sessions[0].prescriptions}.intersection(
        item[0] for item in NEW_EXERCISES)
    for language in ("bg", "en"):
        assert render_delivery(replay, replay_library, (), language) == render_delivery(plan, library, (), language)
        assert render_completion_projection(replay, replay_library, language) == render_completion_projection(plan, library, language)


def test_v1_4_adds_only_requested_exercises_without_mutating_released_libraries():
    old = load_exercise_library("1.3.0")
    current = load_exercise_library()
    assert current.version == "1.4.0"
    assert current.exercises == old.exercises + tuple(current.require(item[0]) for item in NEW_EXERCISES)
    assert len(current.exercises) == 40
    assert {item.movement_pattern for item in current.exercises} == set(MovementPattern)
    assert {part for item in current.exercises for part in item.equipment} == set(Equipment)
    for exercise in old.exercises:
        assert current.require(exercise.exercise_id, exercise.version) is exercise
    with pytest.raises(ValueError, match="unknown exercise library version"):
        load_exercise_library("unsupported")


@pytest.mark.parametrize("identity,name,pattern,equipment,difficulty", NEW_EXERCISES)
def test_new_registry_metadata_is_typed_and_does_not_invent_prerequisites(identity, name, pattern, equipment, difficulty):
    exercise = load_exercise_library().require(identity, "1.0.0")
    assert (exercise.display_name, exercise.movement_pattern, exercise.equipment, exercise.difficulty) == (
        name, pattern, equipment, difficulty)
    assert exercise.primary_muscles and exercise.secondary_muscles
    assert exercise.safety_notes and exercise.training_tags
    assert exercise.prerequisite_exercise_ids == ()
    if identity == "bodyweight.negative_pull_up":
        assert exercise.progression.next_exercise_ids == ("bodyweight.pull_up",)


def _select(pattern, equipment, *, experience=Difficulty.INTERMEDIATE, safety=None, advisory=()):
    request = TrainingSelectionRequest(
        recommendation_blueprint_id="registry-expansion-selection",
        goal=TrainingGoal.MUSCLE_GAIN, experience_level=experience,
        available_equipment=equipment, muscle_priorities=(),
        safety=safety or TrainingSafetyConstraints(),
        advisory_preferred_exercise_ids=advisory,
        policy=TrainingGoalPolicy("registry-expansion-test", TrainingGoal.MUSCLE_GAIN, (pattern,), True),
    )
    return TrainingSelectionEngine.select(load_exercise_library(), request)


@pytest.mark.parametrize("pattern,equipment,expected", (
    (MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.DUMBBELL, Equipment.BENCH}), "dumbbell.bench_press"),
    (MovementPattern.HORIZONTAL_PULL, frozenset({Equipment.DUMBBELL}), "dumbbell.bent_over_row"),
    (MovementPattern.VERTICAL_PULL, frozenset({Equipment.PULLUP_BAR}), "bodyweight.negative_pull_up"),
    (MovementPattern.CORE_ANTI_EXTENSION, frozenset({Equipment.BODYWEIGHT}), "bodyweight.hollow_hold"),
))
def test_intermediate_selection_has_real_compatible_options(pattern, equipment, expected):
    result = _select(pattern, equipment)
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.blueprint.selections[0].exercise_id == expected


def test_gym_can_select_bench_press_through_existing_safe_tie_break():
    # Do not replace the existing lexical tie-break or force a new exercise into every plan.
    result = _select(MovementPattern.HORIZONTAL_PUSH, frozenset(Equipment),
                     advisory=("dumbbell.bench_press",))
    assert result.blueprint.selections[0].exercise_id == "dumbbell.bench_press"
    no_bench = _select(MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.DUMBBELL}),
                       advisory=("dumbbell.bench_press",))
    assert no_bench.blueprint.selections[0].exercise_id == "dumbbell.floor_press"


def test_equipment_exclusions_and_difficulty_still_outrank_new_exercises():
    no_bench = _select(MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.DUMBBELL}))
    assert no_bench.blueprint.selections[0].exercise_id == "dumbbell.floor_press"
    excluded = _select(MovementPattern.HORIZONTAL_PUSH, frozenset(Equipment), safety=TrainingSafetyConstraints(
        excluded_exercise_ids=frozenset({"dumbbell.bench_press"})))
    assert excluded.blueprint.selections[0].exercise_id != "dumbbell.bench_press"
    beginner = _select(MovementPattern.CORE_ANTI_EXTENSION, frozenset({Equipment.BODYWEIGHT}),
                       experience=Difficulty.BEGINNER)
    assert beginner.blueprint.selections[0].exercise_id == "bodyweight.plank"
    barbell = _select(MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.BARBELL, Equipment.BENCH}))
    assert barbell.outcome is SelectionOutcome.REJECTED
    advanced = _select(MovementPattern.HORIZONTAL_PUSH, frozenset({Equipment.BARBELL, Equipment.BENCH}),
                       experience=Difficulty.ADVANCED)
    assert advanced.blueprint.selections[0].exercise_id == "barbell.bench_press"


def test_overhead_exclusion_still_blocks_new_push_press():
    result = _select(MovementPattern.VERTICAL_PUSH, frozenset({Equipment.DUMBBELL}),
                     safety=TrainingSafetyConstraints(excluded_movement_patterns=frozenset({MovementPattern.VERTICAL_PUSH})))
    assert result.outcome is SelectionOutcome.REJECTED
    plan = build_training_plan(
        recommendation_blueprint_id="registry-expansion-overhead-restriction",
        facts={"goal": "strength", "level": "intermediate", "equipment": "gym", "recoveryFeel": "fresh"},
        excluded_movement_patterns=frozenset({MovementPattern.VERTICAL_PUSH}),
        requested_split="upper_lower",
    )
    assert all(item.movement_pattern is not MovementPattern.VERTICAL_PUSH
               for session in plan.sessions for item in session.prescriptions)


@pytest.mark.parametrize("identity,index_id", (
    ("dumbbell.bench_press", "dumbbell_bench_press"),
    ("barbell.bench_press", "bench_press"),
    ("dumbbell.bent_over_row", "dumbbell_row"),
    ("bodyweight.negative_pull_up", "assisted_pull_up"),
    ("dumbbell.reverse_lunge", "dumbbell_lunge"),
    ("dumbbell.front_squat", "goblet_squat"),
    ("barbell.deadlift", "barbell_deadlift"),
    ("bodyweight.hollow_hold", "dead_bug"),
    ("dumbbell.push_press", "push_press"),
))
def test_new_registry_identity_reuses_existing_shoulder_load_categories(identity, index_id):
    from app import _shoulder_validator_id
    from brain.shoulder_exercise_index import shoulder_load_movements_for

    assert _shoulder_validator_id(identity) == index_id
    assert shoulder_load_movements_for(index_id) != frozenset({"unknown_shoulder_load"})
    if identity == "dumbbell.reverse_lunge":
        assert "upper_limb_external_load" in shoulder_load_movements_for(index_id)
    if identity == "dumbbell.push_press":
        assert "overhead" in shoulder_load_movements_for(index_id)


def test_explicit_aliases_do_not_relax_existing_shoulder_restrictions_or_unknown_ids():
    from app import _shoulder_validator_id
    from brain.shoulder_validator import validate_blueprint
    from brain.types import Constraint, ConstraintSet, ConstraintTier

    constraints = ConstraintSet([
        Constraint("upper_limb_external_load", ConstraintTier.ABSOLUTE, "shoulder_load_forbidden"),
        Constraint("hanging", ConstraintTier.ABSOLUTE, "shoulder_load_forbidden"),
        Constraint("overhead", ConstraintTier.ABSOLUTE, "shoulder_load_forbidden"),
        Constraint("unknown_shoulder_load", ConstraintTier.ABSOLUTE, "shoulder_load_forbidden"),
    ])
    for identity in ("dumbbell.reverse_lunge", "dumbbell.front_squat", "dumbbell.bent_over_row",
                     "bodyweight.negative_pull_up", "dumbbell.push_press", "unknown.exercise"):
        result = validate_blueprint([{"canonical_id": _shoulder_validator_id(identity)}], constraints)
        assert result.passed is False, identity
    assert _shoulder_validator_id("unknown.exercise") == "unknown.exercise"


@pytest.mark.parametrize("identity,name,pattern,equipment,difficulty", NEW_EXERCISES)
def test_every_new_exercise_constructs_and_renders_without_changing_prescription(identity, name, pattern, equipment, difficulty):
    library = load_exercise_library()
    other_ids = frozenset(item.exercise_id for item in library.by_movement(pattern) if item.exercise_id != identity)
    selection = _select(pattern, equipment, experience=difficulty,
                        safety=TrainingSafetyConstraints(excluded_exercise_ids=other_ids))
    assert selection.blueprint.selections[0].exercise_id == identity
    policy = TrainingStructurePolicy(
        version="registry-expansion-construction", goal=TrainingGoal.MUSCLE_GAIN,
        experience_level=difficulty, recovery=RecoveryAssumption.MODERATE, sessions_per_week=1,
        movement_order=(pattern,),
        prescription_rules=(PrescriptionRule(pattern, 2, 8, 10, Decimal("6"), 4, 60, "2-1-2-0", 5, Decimal("2")),),
        max_session_duration_minutes=60, max_session_fatigue_units=Decimal("30"),
        max_weekly_sets_per_primary_muscle=12, max_push_pull_set_difference=0,
        max_lower_body_set_difference=0, transition_seconds=30,
    )
    plan = TrainingPlanConstructionEngine.construct(selection.blueprint, library, policy)
    before = delivered_plan_lineage(plan)
    labels = {}
    for language in ("bg", "en"):
        rendered = render_completion_projection(plan, library, language)
        exercise = rendered["sessions"][0]["exercises"][0]
        assert exercise["exercise_id"] == identity
        labels[language] = exercise["display_name"]
        assert labels[language] in render_delivery(plan, library, (), language)
        assert delivered_plan_lineage(plan) == before
    assert labels["en"] == name
    assert labels["bg"] != name


def test_all_nine_instruction_records_resolve_by_full_identity_in_bg_and_en():
    node = shutil.which("node")
    assert node, "Node is required to verify the shipped instruction library"
    root = Path(__file__).parents[1]
    expected = []
    for identity, name, *_ in NEW_EXERCISES:
        from training_engine.renderer import _display_name
        expected.append({"id": identity, "en": name, "bg": _display_name(identity, name, "bg")})
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = { window: {} };
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const api = context.window.ApexExerciseInstructions;
const expected = JSON.parse(process.argv[2]);
for (const item of expected) {
  const record = api.findByExerciseId(item.id);
  assert.equal(record.canonical_id, item.id);
  for (const language of ['bg', 'en']) {
    assert.equal(api.display(record, language), item[language]);
    assert.equal(api.find(item[language]), record);
    for (const field of ['starting', 'execution', 'breathing', 'cues', 'mistakes', 'regression', 'safety']) {
      const value = record[language][field];
      assert.ok(Array.isArray(value) ? value.length && value.every(x => typeof x === 'string' && x.trim()) : typeof value === 'string' && value.trim());
    }
  }
}
assert.notEqual(api.findByExerciseId('dumbbell.bench_press'), api.findByExerciseId('barbell.bench_press'));
assert.notEqual(api.findByExerciseId('bodyweight.reverse_lunge'), api.findByExerciseId('dumbbell.reverse_lunge'));
assert.equal(api.findByExerciseId('bodyweight.reverse_lunge').canonical_id, 'reverse_lunge');
assert.equal(api.findByExerciseId('bodyweight.march_in_place').canonical_id, 'marching_in_place');
console.log('9/9 canonical BG/EN instruction records passed');
"""
    result = subprocess.run([node, "-e", script, str(root / "static/exercise_instruction_library.js"), json.dumps(expected)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
