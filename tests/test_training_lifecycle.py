"""Pure Training Lifecycle Orchestrator revision tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from training_engine import (
    ExercisePerformance,
    PlanRevisionReason,
    ProgressionBlueprint,
    ProgressionDecision,
    ProgressionDecisionType,
    ProgressionHistory,
    ProgressionStateEngine,
    RecoverySnapshot,
    RecoveryState,
    TrainingLifecycleEvent,
    TrainingLifecycleOrchestrator,
    WorkoutResult,
    build_training_plan,
)


def _plan(*, beginner=False):
    return build_training_plan(recommendation_blueprint_id="rec-lifecycle", facts={
        "goal": "strength", "level": "beginner" if beginner else "intermediate",
        "equipment": "bodyweight, bench" if beginner else "gym", "recoveryFeel": "fresh",
    })


def _workout(plan):
    return WorkoutResult(
        "workout-lifecycle", plan.plan_id, plan.version, datetime(2026, 7, 1, tzinfo=timezone.utc), True,
        tuple(ExercisePerformance(
            item.exercise_id, item.exercise_version, item.sets, item.rep_max,
            Decimal("7"), 3, Decimal("20"), True,
        ) for item in plan.sessions[0].prescriptions),
    )


def _decision(plan, prescription, kind, *, replacement=False):
    return ProgressionDecision(
        f"decision-{prescription.exercise_id}-{kind.value}", kind, "test", "progression-policy-v2",
        prescription.exercise_id, prescription.exercise_version, plan.version,
        load_delta_kg=Decimal("2.5") if kind is ProgressionDecisionType.INCREASE_LOAD else None,
        repetition_delta=1 if kind is ProgressionDecisionType.INCREASE_REPETITIONS else None,
        set_delta=1 if kind is ProgressionDecisionType.INCREASE_SETS else None,
        replacement_exercise_id="bodyweight.push_up" if replacement else None,
        replacement_exercise_version="1.0.0" if replacement else None,
    )


def _event(plan, workout, decisions, *, states=None):
    states = states if states is not None else ProgressionStateEngine.derive(ProgressionHistory((workout,)))
    blueprint = ProgressionBlueprint(
        "progression-lifecycle", "progression-blueprint-v1", plan.plan_id, plan.version,
        "progression-policy-v2", RecoverySnapshot(RecoveryState.NORMALLY_RECOVERED, Decimal("30"), "recovery-v1"),
        tuple(decisions),
    )
    return TrainingLifecycleEvent("lifecycle-event", workout, blueprint, tuple(states), "progression-policy-v2")


def test_lifecycle_applies_load_rep_and_set_revisions_without_mutating_parent_plan():
    plan = _plan()
    workout = _workout(plan)
    prescriptions = plan.sessions[0].prescriptions
    decisions = (
        _decision(plan, prescriptions[0], ProgressionDecisionType.INCREASE_LOAD),
        _decision(plan, prescriptions[1], ProgressionDecisionType.INCREASE_REPETITIONS),
        _decision(plan, prescriptions[2], ProgressionDecisionType.INCREASE_SETS),
    )
    revision = TrainingLifecycleOrchestrator.revise(plan, _event(plan, workout, decisions))
    revised = revision.revised_plan.sessions[0].prescriptions

    assert plan.sessions[0].prescriptions[0].target_load_kg is None
    assert revised[0].target_load_kg == Decimal("22.5")
    assert revised[1].rep_max == prescriptions[1].rep_max + 1
    assert revised[2].sets == prescriptions[2].sets + 1
    assert {PlanRevisionReason.LOAD, PlanRevisionReason.REPETITIONS, PlanRevisionReason.SETS,
            PlanRevisionReason.MAINTAIN} == set(revision.reasons)


def test_lifecycle_applies_deload_to_every_affected_prescription():
    plan = _plan()
    workout = _workout(plan)
    decisions = tuple(_decision(plan, item, ProgressionDecisionType.DELOAD)
                      for item in plan.sessions[0].prescriptions)
    revision = TrainingLifecycleOrchestrator.revise(plan, _event(plan, workout, decisions))

    assert revision.reasons == (PlanRevisionReason.DELOAD,)
    assert all(item.sets == max(1, original.sets // 2)
               for item, original in zip(revision.revised_plan.sessions[0].prescriptions,
                                         plan.sessions[0].prescriptions))


def test_lifecycle_replaces_exercise_and_rotates_only_when_a_traceable_successor_exists():
    plan = _plan(beginner=True)
    workout = _workout(plan)
    incline = next(item for item in plan.sessions[0].prescriptions if item.exercise_id == "bodyweight.incline_push_up")
    replacement = _decision(plan, incline, ProgressionDecisionType.REPLACE_EXERCISE, replacement=True)
    revised = TrainingLifecycleOrchestrator.revise(plan, _event(plan, workout, (replacement,))).revised_plan
    assert "bodyweight.push_up" in {item.exercise_id for item in revised.sessions[0].prescriptions}

    states = tuple(replace(item, rotation_recommended=True) if item.exercise_id == incline.exercise_id else item
                   for item in ProgressionStateEngine.derive(ProgressionHistory((workout,))))
    maintain = _decision(plan, incline, ProgressionDecisionType.MAINTAIN)
    rotated = TrainingLifecycleOrchestrator.revise(plan, _event(plan, workout, (maintain,), states=states))
    assert PlanRevisionReason.ROTATION in rotated.reasons
    assert "bodyweight.push_up" in {item.exercise_id for item in rotated.revised_plan.sessions[0].prescriptions}


def test_lifecycle_preserves_blueprint_ancestry_and_progression_traceability():
    plan = _plan()
    workout = _workout(plan)
    decision = _decision(plan, plan.sessions[0].prescriptions[0], ProgressionDecisionType.INCREASE_LOAD)
    revision = TrainingLifecycleOrchestrator.revise(plan, _event(plan, workout, (decision,)))
    revised = revision.revised_plan

    assert (revised.parent_plan_id, revised.parent_plan_version) == (plan.plan_id, plan.version)
    assert revised.revision_id == revision.revision_id
    assert revised.progression_decision_ids == (decision.decision_id,)
    assert revised.lifecycle_policy_version == "training-lifecycle-policy-v1"


def test_lifecycle_keeps_an_explicit_terminal_rotation_unchanged():
    plan = _plan()
    workout = _workout(plan)
    states = tuple(replace(item, rotation_recommended=True) if item.exercise_id == "bodyweight.plank" else item
                   for item in ProgressionStateEngine.derive(ProgressionHistory((workout,))))
    maintain = _decision(plan, plan.sessions[0].prescriptions[0], ProgressionDecisionType.MAINTAIN)

    revision = TrainingLifecycleOrchestrator.revise(plan, _event(plan, workout, (maintain,), states=states))
    assert PlanRevisionReason.ROTATION not in revision.reasons
    assert "bodyweight.plank" in {item.exercise_id for item in revision.revised_plan.sessions[0].prescriptions}


def test_lifecycle_rejects_orphan_and_incompatible_events():
    plan = _plan()
    workout = _workout(plan)
    known = _decision(plan, plan.sessions[0].prescriptions[0], ProgressionDecisionType.MAINTAIN)
    orphan = _event(plan, workout, (known,))
    with pytest.raises(ValueError, match="orphan progression"):
        replace(orphan, workout=replace(workout, plan_id="other-plan"))
    unknown = ProgressionDecision("orphan", ProgressionDecisionType.MAINTAIN, "test", "progression-policy-v2",
                                  "missing.exercise", "1.0.0", plan.version)
    with pytest.raises(ValueError, match="orphan"):
        TrainingLifecycleOrchestrator.revise(plan, _event(plan, workout, (unknown,)))
