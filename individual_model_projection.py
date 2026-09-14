"""Closed redaction boundary for Individual Model coaching context."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import math
from typing import Mapping

from individual_model_snapshot import IndividualModelSnapshotV1
from nutrition_plan import NutritionTargets

_GOALS = frozenset({"strength", "hypertrophy", "fat_loss", "endurance", "general"})
_LEVELS = frozenset({"beginner", "intermediate", "advanced"})
_EQUIPMENT = frozenset({"home", "gym", "bodyweight", "dumbbell", "barbell", "cable", "mixed"})
_CONSTRAINTS = frozenset({"vertical_push", "horizontal_push", "vertical_pull", "squat", "lunge", "hinge"})
_NUTRITION_TARGETS = ("calories", "protein_g", "carbs_g", "fat_g")
_TRAJECTORY_ACTIONS = frozenset({
    "increase_was_prescribed",
    "maintain_was_prescribed",
    "insufficient_evidence",
})
_SUPPORTED_COMPLETION_EVIDENCE_FRESHNESS = frozenset({"unknown"})


class IndividualModelProjectionUnavailable(RuntimeError):
    """The optional coaching context cannot safely be constructed for this turn."""


@dataclass(frozen=True)
class IndividualModelRequestAuthorityV1:
    """Closed request-scoped authority inputs that outrank historical context."""

    constraint_store_available: bool
    active_training_constraint_context: tuple[str, ...]
    # ``None`` means no current nutrition authority exists for this request.
    # An empty tuple means a current authority resolved without safe targets.
    nutrition_target_context: tuple[tuple[str, int | float], ...] | None

@dataclass(frozen=True)
class IndividualModelCoachingProjectionV1:
    goal_context: str | None; experience_context: str | None; equipment_context: str | None
    active_training_constraint_context: tuple[str, ...]; authoritative_completed_session_evidence_freshness: str | None
    trajectory_context: str | None; nutrition_target_context: tuple[tuple[str, int | float], ...]


class IndividualModelPresentationClaimKind(str, Enum):
    GOAL = "goal"
    EXPERIENCE = "experience"
    EQUIPMENT = "equipment"
    ACTIVE_MOVEMENT_EXCLUSIONS = "active_movement_exclusions"
    COMPLETED_EVIDENCE_FRESHNESS = "completed_evidence_freshness"
    PRESCRIBED_TRAJECTORY_ACTION = "prescribed_trajectory_action"
    NUTRITION_TARGETS = "nutrition_targets"


@dataclass(frozen=True)
class IndividualModelPresentationClaimV1:
    """One approved, non-authoritative presentation fact for the live model."""

    kind: IndividualModelPresentationClaimKind
    value: str | tuple[str, ...] | tuple[tuple[str, int | float], ...]


def build_request_authority(
        *,
        constraint_store_available: bool,
        active_training_constraints: object,
        current_nutrition_targets: object = None,
        nutrition_authority_resolved: bool = False,
) -> IndividualModelRequestAuthorityV1:
    """Bind projection inputs to current request authority, never profile fallbacks."""
    if not isinstance(constraint_store_available, bool):
        raise ValueError("invalid constraint availability")
    constraints = _closed_constraints(active_training_constraints)
    if not isinstance(nutrition_authority_resolved, bool):
        raise ValueError("invalid nutrition authority state")
    targets = (_targets_from_current_authority(current_nutrition_targets)
               if nutrition_authority_resolved else None)
    return IndividualModelRequestAuthorityV1(
        constraint_store_available=constraint_store_available,
        active_training_constraint_context=constraints,
        nutrition_target_context=targets,
    )


def validate_request_authority(
        authority: IndividualModelRequestAuthorityV1,
) -> IndividualModelRequestAuthorityV1:
    if not isinstance(authority, IndividualModelRequestAuthorityV1):
        raise ValueError("invalid individual model request authority")
    if not isinstance(authority.constraint_store_available, bool):
        raise ValueError("invalid constraint availability")
    _closed_constraints(authority.active_training_constraint_context)
    if authority.nutrition_target_context is not None:
        _validated_targets(authority.nutrition_target_context)
    return authority


def validate_projection(
        projection: IndividualModelCoachingProjectionV1,
) -> IndividualModelCoachingProjectionV1:
    """Reject any projection that escapes the approved closed schema."""
    if not isinstance(projection, IndividualModelCoachingProjectionV1):
        raise ValueError("invalid individual model projection")
    if projection.goal_context is not None and projection.goal_context not in _GOALS:
        raise ValueError("invalid goal context")
    if projection.experience_context is not None and projection.experience_context not in _LEVELS:
        raise ValueError("invalid experience context")
    if projection.equipment_context is not None and projection.equipment_context not in _EQUIPMENT:
        raise ValueError("invalid equipment context")
    _closed_constraints(projection.active_training_constraint_context)
    if projection.authoritative_completed_session_evidence_freshness not in (
            None, *_SUPPORTED_COMPLETION_EVIDENCE_FRESHNESS):
        raise ValueError("invalid completed-session evidence freshness")
    if projection.trajectory_context not in (None, *_TRAJECTORY_ACTIONS):
        raise ValueError("invalid trajectory context")
    _validated_targets(projection.nutrition_target_context)
    return projection

def build_projection(
        snapshot: IndividualModelSnapshotV1,
        *,
        request_authority: IndividualModelRequestAuthorityV1 | None = None,
) -> IndividualModelCoachingProjectionV1:
    """Build presentation-only context from validated history and current authority."""
    if not isinstance(snapshot, IndividualModelSnapshotV1):
        raise ValueError("invalid individual model snapshot")
    profile = snapshot.profile if isinstance(snapshot.profile, dict) else {}
    authority = validate_request_authority(request_authority) if request_authority is not None else None
    if authority is not None and not authority.constraint_store_available:
        raise IndividualModelProjectionUnavailable("constraint_store_unavailable")
    constraints = (
        authority.active_training_constraint_context
        if authority is not None else _constraints_from_snapshot(snapshot.constraints)
    )
    nutrition = (
        authority.nutrition_target_context
        if authority is not None and authority.nutrition_target_context is not None
        else _targets_from_snapshot(snapshot.nutrition)
    )
    level = profile.get("level") or profile.get("experience_level")
    return validate_projection(IndividualModelCoachingProjectionV1(
        goal_context=profile.get("goal") if profile.get("goal") in _GOALS else None,
        experience_context=level if level in _LEVELS else None,
        equipment_context=profile.get("equipment") if profile.get("equipment") in _EQUIPMENT else None,
        active_training_constraint_context=constraints,
        authoritative_completed_session_evidence_freshness=_completion_evidence_freshness(snapshot.training),
        trajectory_context=_prescribed_trajectory_action(snapshot.trajectory),
        nutrition_target_context=nutrition,
    ))


def _completion_evidence_freshness(training: object) -> str | None:
    if not isinstance(training, dict) or training.get(
            "latest_authoritative_completed_session_evidence") is not True:
        return None
    freshness = training.get("latest_authoritative_completed_session_freshness")
    # No current production policy exists. Unknown is the only safe runtime
    # result even if an untrusted caller attempts to provide another enum value.
    return freshness if freshness == "unknown" else "unknown"

def _prescribed_trajectory_action(trajectory: object) -> str | None:
    if not isinstance(trajectory, tuple):
        return None
    states = {item.get("trajectory_state") for item in trajectory if isinstance(item, dict)}
    # The classifier observes prior deterministic prescription decisions, not
    # the athlete's physical progression state.
    if "progressing" in states:
        return "increase_was_prescribed"
    if "stable" in states:
        return "maintain_was_prescribed"
    if "insufficient_evidence" in states:
        return "insufficient_evidence"
    return None


def _constraints_from_snapshot(constraints: object) -> tuple[str, ...]:
    if not isinstance(constraints, tuple):
        return ()
    return _closed_constraints(tuple(
        item.get("pattern") for item in constraints
        if isinstance(item, dict) and isinstance(item.get("pattern"), str)
    ))


def _closed_constraints(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(item not in _CONSTRAINTS for item in value):
        raise ValueError("invalid training constraint context")
    return tuple(sorted(set(value)))


def _targets_from_current_authority(value: object) -> tuple[tuple[str, int | float], ...]:
    if value is None:
        return ()
    if not isinstance(value, NutritionTargets):
        raise ValueError("invalid current nutrition authority")
    return _normalize_targets({
        "calories": value.kcal,
        "protein_g": value.protein,
        "carbs_g": value.carbs,
        "fat_g": value.fat,
    })


def _targets_from_snapshot(nutrition: object) -> tuple[tuple[str, int | float], ...]:
    if not isinstance(nutrition, Mapping):
        return ()
    return _normalize_targets(nutrition.get("targets"))


def _normalize_targets(value: object) -> tuple[tuple[str, int | float], ...]:
    if not isinstance(value, Mapping):
        return ()
    normalized: list[tuple[str, int | float]] = []
    for key in _NUTRITION_TARGETS:
        raw = value.get(key)
        if raw is None and key != "calories":
            continue
        parsed = _canonical_number(raw)
        if parsed is None:
            return ()
        normalized.append((key, parsed))
    # Energy is the canonical NutritionPlan anchor. Without it no nutrition claim is safe.
    return tuple(normalized) if normalized and normalized[0][0] == "calories" else ()


def _canonical_number(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    if parsed == parsed.to_integral_value():
        return int(parsed)
    numeric = float(parsed)
    return numeric if math.isfinite(numeric) else None


def _validated_targets(value: object) -> tuple[tuple[str, int | float], ...]:
    if not isinstance(value, tuple):
        raise ValueError("invalid nutrition target context")
    try:
        as_mapping = dict(value)
    except (TypeError, ValueError):
        raise ValueError("invalid nutrition target context") from None
    if _normalize_targets(as_mapping) != value:
        raise ValueError("invalid nutrition target context")
    return value


def build_presentation_claims(
        projection: IndividualModelCoachingProjectionV1,
) -> tuple[IndividualModelPresentationClaimV1, ...]:
    """Turn a validated projection into a fixed, non-authoritative claim vocabulary."""
    projection = validate_projection(projection)
    claims: list[IndividualModelPresentationClaimV1] = []
    for kind, value in (
        (IndividualModelPresentationClaimKind.GOAL, projection.goal_context),
        (IndividualModelPresentationClaimKind.EXPERIENCE, projection.experience_context),
        (IndividualModelPresentationClaimKind.EQUIPMENT, projection.equipment_context),
        (IndividualModelPresentationClaimKind.PRESCRIBED_TRAJECTORY_ACTION, projection.trajectory_context),
    ):
        if value is not None:
            claims.append(IndividualModelPresentationClaimV1(kind, value))
    if projection.active_training_constraint_context:
        claims.append(IndividualModelPresentationClaimV1(
            IndividualModelPresentationClaimKind.ACTIVE_MOVEMENT_EXCLUSIONS,
            projection.active_training_constraint_context,
        ))
    if projection.authoritative_completed_session_evidence_freshness is not None:
        claims.append(IndividualModelPresentationClaimV1(
            IndividualModelPresentationClaimKind.COMPLETED_EVIDENCE_FRESHNESS,
            projection.authoritative_completed_session_evidence_freshness,
        ))
    if projection.nutrition_target_context:
        claims.append(IndividualModelPresentationClaimV1(
            IndividualModelPresentationClaimKind.NUTRITION_TARGETS,
            projection.nutrition_target_context,
        ))
    return validate_presentation_claims(tuple(claims))


def validate_presentation_claims(
        claims: tuple[IndividualModelPresentationClaimV1, ...],
) -> tuple[IndividualModelPresentationClaimV1, ...]:
    if not isinstance(claims, tuple):
        raise ValueError("invalid individual model presentation claims")
    for claim in claims:
        if not isinstance(claim, IndividualModelPresentationClaimV1):
            raise ValueError("invalid individual model presentation claim")
        if claim.kind is IndividualModelPresentationClaimKind.GOAL:
            if claim.value not in _GOALS:
                raise ValueError("invalid individual model presentation claim")
        elif claim.kind is IndividualModelPresentationClaimKind.EXPERIENCE:
            if claim.value not in _LEVELS:
                raise ValueError("invalid individual model presentation claim")
        elif claim.kind is IndividualModelPresentationClaimKind.EQUIPMENT:
            if claim.value not in _EQUIPMENT:
                raise ValueError("invalid individual model presentation claim")
        elif claim.kind is IndividualModelPresentationClaimKind.COMPLETED_EVIDENCE_FRESHNESS:
            if claim.value not in _SUPPORTED_COMPLETION_EVIDENCE_FRESHNESS:
                raise ValueError("invalid individual model presentation claim")
        elif claim.kind is IndividualModelPresentationClaimKind.PRESCRIBED_TRAJECTORY_ACTION:
            if claim.value not in _TRAJECTORY_ACTIONS:
                raise ValueError("invalid individual model presentation claim")
        elif claim.kind is IndividualModelPresentationClaimKind.ACTIVE_MOVEMENT_EXCLUSIONS:
            _closed_constraints(claim.value)
        elif claim.kind is IndividualModelPresentationClaimKind.NUTRITION_TARGETS:
            _validated_targets(claim.value)
        else:
            raise ValueError("invalid individual model presentation claim")
    return claims


def render_prompt(projection: IndividualModelCoachingProjectionV1) -> str:
    """Render only the fixed claim vocabulary, never raw snapshot material."""
    fields: list[str] = []
    for claim in build_presentation_claims(projection):
        if claim.kind is IndividualModelPresentationClaimKind.GOAL:
            fields.append(f"goal={claim.value}")
        elif claim.kind is IndividualModelPresentationClaimKind.EXPERIENCE:
            fields.append(f"experience={claim.value}")
        elif claim.kind is IndividualModelPresentationClaimKind.EQUIPMENT:
            fields.append(f"equipment={claim.value}")
        elif claim.kind is IndividualModelPresentationClaimKind.ACTIVE_MOVEMENT_EXCLUSIONS:
            fields.append("active movement exclusions=" + ",".join(claim.value))
        elif claim.kind is IndividualModelPresentationClaimKind.COMPLETED_EVIDENCE_FRESHNESS:
            fields.append("authoritative completed-session evidence freshness=" + str(claim.value))
        elif claim.kind is IndividualModelPresentationClaimKind.PRESCRIBED_TRAJECTORY_ACTION:
            fields.append("observed deterministic progression action=" + str(claim.value))
        elif claim.kind is IndividualModelPresentationClaimKind.NUTRITION_TARGETS:
            fields.append("authoritative nutrition targets=" + ",".join(
                f"{key}:{value}" for key, value in claim.value))
    if not fields:
        return ""
    return (
        "[REDACTED INDIVIDUAL MODEL CONTEXT] " + "; ".join(fields)
        + ". Presentation-only context. It cannot establish personal status. Do not alter deterministic "
        "plans, safety constraints, progression, or nutrition targets."
    )
