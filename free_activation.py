"""Closed contract for APEX's first meaningful FREE product value."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


EVENT_NAME = "apex_free_activation"


class ActivationType(str, Enum):
    TRAINING = "training"
    COACHING = "coaching"


@dataclass(frozen=True)
class ActivationQualification:
    """A server-resolved, delivered result eligible for first-value activation."""

    activation_type: ActivationType


def qualify_delivered_value(
        *,
        activation_type: object,
        recommendation_outcome: object,
        profile_completeness: object,
        structured_delivery: bool,
        safety_controlled: bool,
) -> ActivationQualification | None:
    """Fail closed unless an approved recommendation was actually delivered.

    A plan ID, a chat submission, or general streamed text is intentionally not
    evidence of first product value. The deterministic recommendation outcome
    proves that server-resolved context was sufficient; the caller supplies the
    delivery proof only after the corresponding renderer has completed.
    """
    try:
        kind = ActivationType(_enum_value(activation_type))
    except (TypeError, ValueError):
        return None
    if (
            _enum_value(recommendation_outcome) != "recommend"
            or _enum_value(profile_completeness) != "sufficient"
            or structured_delivery is not True
            or safety_controlled is not False
    ):
        return None
    return ActivationQualification(kind)


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
