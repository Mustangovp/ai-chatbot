"""Immutable, renderer-free persistence projection for delivered training plans."""
from __future__ import annotations

from typing import Any
from decimal import Decimal

from .completion import prescription_id
from .construction import (
    ExercisePrescription, MuscleGroupVolume, TrainingPlanBlueprintV2,
    TrainingSessionBlueprint,
)
from .models import MovementPattern
from .selection import TrainingSplit


def delivered_plan_lineage(plan: TrainingPlanBlueprintV2) -> dict[str, Any]:
    """Project only immutable blueprint facts required for account lineage."""
    if not isinstance(plan, TrainingPlanBlueprintV2):
        raise ValueError("delivered training lineage requires a training blueprint")
    sessions = []
    for session in plan.sessions:
        prescriptions = []
        for item in session.prescriptions:
            prescriptions.append({
                "prescription_id": prescription_id(plan, session, item),
                "exercise_id": item.exercise_id,
                "exercise_version": item.exercise_version,
                "movement_pattern": item.movement_pattern.value,
                "sets": item.sets,
                "rep_min": item.rep_min,
                "rep_max": item.rep_max,
                "target_rpe": str(item.target_rpe),
                "target_rir": item.target_rir,
                "rest_seconds": item.rest_seconds,
                "tempo": item.tempo,
                "target_load_kg": None if item.target_load_kg is None else str(item.target_load_kg),
                "selection_policy_version": item.selection_policy_version,
                "prescription_policy_version": item.prescription_policy_version,
                "construction_policy_version": item.construction_policy_version,
            })
        sessions.append({
            "session_id": session.session_id,
            "session_index": session.session_index,
            "selection_blueprint_id": session.selection_blueprint_id,
            "estimated_duration_minutes": session.estimated_duration_minutes,
            "prescriptions": prescriptions,
        })
    return {
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "metadata": {
            "selection_blueprint_id": plan.selection_blueprint_id,
            "exercise_library_version": plan.exercise_library_version,
            "selection_policy_version": plan.selection_policy_version,
            "construction_policy_version": plan.construction_policy_version,
            "training_split": plan.training_split.value,
            "parent_plan_id": plan.parent_plan_id,
            "parent_plan_version": plan.parent_plan_version,
            "revision_id": plan.revision_id,
            "revision_reasons": list(plan.revision_reasons),
            "progression_decision_ids": list(plan.progression_decision_ids),
            "lifecycle_policy_version": plan.lifecycle_policy_version,
            "weekly_volume": [
                {"muscle_group": item.muscle_group, "weekly_sets": item.weekly_sets}
                for item in plan.weekly_volume
            ],
        },
        "sessions": sessions,
    }


def plan_from_delivered_lineage(lineage: dict[str, Any]) -> TrainingPlanBlueprintV2:
    """Rebuild a blueprint solely from its persisted immutable delivery facts."""
    if not isinstance(lineage, dict) or not isinstance(lineage.get("metadata"), dict):
        raise ValueError("delivered training lineage is invalid")
    metadata = lineage["metadata"]
    try:
        sessions = tuple(TrainingSessionBlueprint(
            session_id=str(session["session_id"]), session_index=int(session["session_index"]),
            selection_blueprint_id=str(session["selection_blueprint_id"]),
            estimated_duration_minutes=int(session["estimated_duration_minutes"]),
            prescriptions=tuple(ExercisePrescription(
                exercise_id=str(item["exercise_id"]), exercise_version=str(item["exercise_version"]),
                movement_pattern=MovementPattern(str(item["movement_pattern"])), sets=int(item["sets"]),
                rep_min=int(item["rep_min"]), rep_max=int(item["rep_max"]),
                target_rpe=Decimal(str(item["target_rpe"])), target_rir=int(item["target_rir"]),
                rest_seconds=int(item["rest_seconds"]), tempo=str(item["tempo"]),
                selection_policy_version=str(item["selection_policy_version"]),
                prescription_policy_version=str(item["prescription_policy_version"]),
                construction_policy_version=str(item["construction_policy_version"]),
                target_load_kg=(None if item.get("target_load_kg") is None
                                else Decimal(str(item["target_load_kg"]))),
            ) for item in session["prescriptions"]),
        ) for session in lineage["sessions"])
        volume = tuple(MuscleGroupVolume(str(item["muscle_group"]), int(item["weekly_sets"]))
                       for item in metadata["weekly_volume"])
        return TrainingPlanBlueprintV2(
            plan_id=str(lineage["plan_id"]), version=str(lineage["plan_version"]),
            selection_blueprint_id=str(metadata["selection_blueprint_id"]),
            exercise_library_version=str(metadata["exercise_library_version"]),
            selection_policy_version=str(metadata["selection_policy_version"]),
            construction_policy_version=str(metadata["construction_policy_version"]),
            training_split=TrainingSplit(str(metadata["training_split"])), sessions=sessions,
            weekly_volume=volume, parent_plan_id=metadata.get("parent_plan_id"),
            parent_plan_version=metadata.get("parent_plan_version"), revision_id=metadata.get("revision_id"),
            revision_reasons=tuple(metadata.get("revision_reasons", ())),
            progression_decision_ids=tuple(metadata.get("progression_decision_ids", ())),
            lifecycle_policy_version=metadata.get("lifecycle_policy_version"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("delivered training lineage cannot rebuild its blueprint") from error
