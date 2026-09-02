"""Immutable, renderer-free persistence projection for delivered training plans."""
from __future__ import annotations

from typing import Any

from .completion import prescription_id
from .construction import TrainingPlanBlueprintV2


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
        },
        "sessions": sessions,
    }
