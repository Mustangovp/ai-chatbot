"""Typed, bounded HSE presentation projection.

This module is intentionally not wired into runtime delivery.  A future consumer
may call :func:`build_presentation_projection` only after its own flag gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

import human_state


ProjectionTone = Literal["unchanged", "supportive", "reassuring"]
Acknowledgement = Literal["none", "brief"]
Encouragement = Literal["none", "gentle", "mastery"]
ExplanationDepth = Literal["unchanged", "concise"]


@dataclass(frozen=True)
class PresentationProjectionV1:
    """ID-free presentation controls derived from approved persisted HSE state."""

    schema_version: Literal["hse_presentation_v1"] = "hse_presentation_v1"
    tone: ProjectionTone = "unchanged"
    acknowledgement: Acknowledgement = "none"
    encouragement: Encouragement = "none"
    explanation_depth: ExplanationDepth = "unchanged"


_SCHEMA_VERSION = "hse_presentation_v1"
_TONES = frozenset(("unchanged", "supportive", "reassuring"))
_ACKNOWLEDGEMENTS = frozenset(("none", "brief"))
_ENCOURAGEMENTS = frozenset(("none", "gentle", "mastery"))
_EXPLANATION_DEPTHS = frozenset(("unchanged", "concise"))
_ADHERENCE_VALUES = frozenset(("missed", "gap"))


def validate_presentation_projection(value: object) -> PresentationProjectionV1 | None:
    """Accept exactly the closed V1 schema; malformed projections are inert."""
    if type(value) is not PresentationProjectionV1:
        return None
    if value.schema_version != _SCHEMA_VERSION:
        return None
    if value.tone not in _TONES:
        return None
    if value.acknowledgement not in _ACKNOWLEDGEMENTS:
        return None
    if value.encouragement not in _ENCOURAGEMENTS:
        return None
    if value.explanation_depth not in _EXPLANATION_DEPTHS:
        return None
    return value


def _fresh_value(state: Mapping[str, object], key: str) -> object | None:
    info = state.get(key)
    if not isinstance(info, Mapping) or info.get("fresh") is not True:
        return None
    return info.get("value")


def build_presentation_projection(subject: str) -> PresentationProjectionV1 | None:
    """Build a no-op or bounded projection from fresh persisted fused state only.

    This deliberately reads neither the current message nor profile, extraction, or
    trajectory systems.  Any malformed state or read failure is ignored.
    """
    try:
        state = human_state.view(subject)
    except Exception:
        return None
    if not isinstance(state, Mapping):
        return None

    motivation_low = _fresh_value(state, "motivation") == "low"
    confidence_low = _fresh_value(state, "confidence") == "low"
    adherence_gap = _fresh_value(state, "adherence") in _ADHERENCE_VALUES
    if not (motivation_low or confidence_low or adherence_gap):
        return None

    projection = PresentationProjectionV1(
        tone="reassuring" if confidence_low else "supportive" if motivation_low else "unchanged",
        acknowledgement="brief" if adherence_gap else "none",
        encouragement="mastery" if confidence_low else "gentle",
    )
    return validate_presentation_projection(projection)
