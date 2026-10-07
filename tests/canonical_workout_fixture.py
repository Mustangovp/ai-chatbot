"""Real construction/renderer fixtures for the browser delivery contract."""
from decimal import Decimal
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training_engine import (
    Equipment, PrescriptionRule, RecoveryAssumption, TrainingGoal, TrainingGoalPolicy,
    TrainingPlanConstructionEngine, TrainingSafetyConstraints, TrainingSelectionEngine,
    TrainingSelectionRequest, TrainingStructurePolicy, load_exercise_library,
)
from training_engine.renderer import render_completion_projection, render_delivery


def canonical_fixtures():
    library = load_exercise_library()
    fixtures = []
    for exercise in library.exercises:
        pattern = exercise.movement_pattern
        request = TrainingSelectionRequest(
            recommendation_blueprint_id="canonical-delivery-" + exercise.exercise_id,
            goal=TrainingGoal.MUSCLE_GAIN, experience_level=exercise.difficulty,
            available_equipment=frozenset(Equipment), muscle_priorities=(),
            safety=TrainingSafetyConstraints(excluded_exercise_ids=frozenset(
                item.exercise_id for item in library.by_movement(pattern)
                if item.exercise_id != exercise.exercise_id
            )),
            advisory_preferred_exercise_ids=(),
            policy=TrainingGoalPolicy("canonical-delivery-test", TrainingGoal.MUSCLE_GAIN, (pattern,), True),
        )
        selection = TrainingSelectionEngine.select(library, request)
        assert selection.blueprint is not None, (exercise.exercise_id, selection)
        policy = TrainingStructurePolicy(
            version="canonical-delivery-test", goal=TrainingGoal.MUSCLE_GAIN,
            experience_level=exercise.difficulty, recovery=RecoveryAssumption.MODERATE,
            sessions_per_week=1, movement_order=(pattern,),
            prescription_rules=(PrescriptionRule(pattern, 2, 8, 10, Decimal("6"), 4, 60, "2-1-2-0", 5, Decimal("2")),),
            max_session_duration_minutes=60, max_session_fatigue_units=Decimal("30"),
            max_weekly_sets_per_primary_muscle=12, max_push_pull_set_difference=0,
            max_lower_body_set_difference=0, transition_seconds=30,
            prescription_schema="exercise-prescription-v2",
        )
        plan = TrainingPlanConstructionEngine.construct(selection.blueprint, library, policy)
        fixtures.append({
            "id": exercise.exercise_id,
            "languages": {language: {
                "metadata": render_completion_projection(plan, library, language),
                "text": render_delivery(plan, library, (), language),
            } for language in ("bg", "en")},
        })
    return fixtures


if __name__ == "__main__":
    print(json.dumps(canonical_fixtures(), ensure_ascii=True))
