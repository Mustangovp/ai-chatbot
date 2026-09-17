"""Closed contract for APEX's first meaningful FREE product value.

The server decides whether a result is eligible. A separately issued, opaque
candidate is later confirmed by the browser only after that result has been
presented. Eligibility is deliberately not product activation truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


EVENT_NAME = "apex_free_activation"


class ActivationType(str, Enum):
    TRAINING = "training"
    COACHING = "coaching"


class DeliveryClass(str, Enum):
    """Closed delivery outcomes relevant to first-value measurement."""

    NORMAL = "normal_verified"
    CONTROLLED_SAFETY = "controlled_safety"
    RENDER_REJECTED = "render_rejected"
    GENERATION_FALLBACK = "generation_fallback"
    EXPLANATION_FALLBACK = "explanation_fallback"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class ActivationQualification:
    """A server-resolved result eligible for a presentation candidate."""

    activation_type: ActivationType


def qualify_server_eligibility(
        *,
        activation_type: object,
        recommendation_outcome: object,
        profile_completeness: object,
        delivery_class: object,
        safety_controlled: bool,
        training_delivery_verified: bool = False,
        coaching_value_verified: bool = False,
) -> ActivationQualification | None:
    """Fail closed unless an approved result is eligible for presentation.

    A plan ID, chat submission, completion metadata, or streamed text is not
    first-value evidence. This function authorizes only a server-issued
    candidate. Product activation is created later by the server after a
    browser confirms its verified presentation.
    """
    try:
        kind = ActivationType(_enum_value(activation_type))
        delivery = DeliveryClass(_enum_value(delivery_class))
    except (TypeError, ValueError):
        return None
    if (
            _enum_value(recommendation_outcome) != "recommend"
            or _enum_value(profile_completeness) != "sufficient"
            or delivery is not DeliveryClass.NORMAL
            or safety_controlled is not False
    ):
        return None
    if kind is ActivationType.TRAINING and training_delivery_verified is not True:
        return None
    if kind is ActivationType.COACHING and coaching_value_verified is not True:
        return None
    return ActivationQualification(kind)


def verified_training_delivery(value: object) -> bool:
    """Validate a structured exercise contract before issuing a candidate.

    This deliberately proves only server eligibility. The browser still has to
    render and verify matching exercise cards before activation is recorded.
    """
    if not isinstance(value, dict):
        return False
    sessions = value.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        return False
    for session in sessions:
        exercises = session.get("exercises") if isinstance(session, dict) else None
        if not isinstance(exercises, list) or not exercises:
            return False
        for exercise in exercises:
            if not isinstance(exercise, dict):
                return False
            if not all(isinstance(exercise.get(key), str) and exercise[key].strip()
                       for key in ("prescription_id", "exercise_id", "exercise_version", "display_name")):
                return False
    return True


def verified_coaching_value(explanations: object) -> bool:
    """Require actual authoritative explanatory value, not blueprint metadata."""
    if not isinstance(explanations, (list, tuple)):
        return False
    for explanation in explanations:
        if not isinstance(explanation, dict):
            continue
        claim = explanation.get("claim")
        because = explanation.get("because")
        if (isinstance(claim, str) and claim.strip()
                and isinstance(because, str) and because.strip()):
            return True
    return False


def analytics_payload(
        qualification: ActivationQualification,
        *,
        authenticated: bool,
        locale: object,
) -> dict[str, object]:
    """Return the only browser-safe confirmation payload for the GA4 event."""
    if not isinstance(qualification, ActivationQualification):
        raise ValueError("invalid activation qualification")
    if type(authenticated) is not bool:
        raise ValueError("invalid activation authentication state")
    language = "en" if locale == "en" else "bg"
    return {
        "event": EVENT_NAME,
        "activation_type": qualification.activation_type.value,
        "authenticated": authenticated,
        "locale": language,
    }


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)
