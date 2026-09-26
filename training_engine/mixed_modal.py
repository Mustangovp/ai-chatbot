"""Bounded mixed-modal session structure over an authoritative training plan.

The existing selector and construction engine own exercises, sets, reps, effort,
and safety. This layer schedules those exact prescriptions; it cannot create a
movement, load, or completion observation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import re
from typing import Mapping, TYPE_CHECKING

from .models import Difficulty, Equipment, MovementPattern
from .registry import ExerciseLibrary

if TYPE_CHECKING:
    from .construction import TrainingPlanBlueprintV2


class SessionFormat(str, Enum):
    AMRAP = "amrap"
    EMOM = "emom"
    FOR_TIME = "for_time"
    ROUNDS_REPS = "rounds_reps"
    STRENGTH_METCON = "strength_metcon"
    INTERVALS = "intervals"


class TrainingModality(str, Enum):
    WEIGHTLIFTING = "weightlifting"
    OLYMPIC_DERIVATIVE = "olympic_derivative"
    GYMNASTICS = "gymnastics"
    MONOSTRUCTURAL = "monostructural"


class MixedModalPlanningError(ValueError):
    pass


@dataclass(frozen=True)
class MixedModalRequest:
    format: SessionFormat
    requested_olympic: bool = False
    requested_box_jumps: bool = False
    requested_monostructural: bool = False
    knee_concern: bool = False


@dataclass(frozen=True)
class MixedModalStructure:
    version: str
    format: SessionFormat
    time_cap_minutes: int
    modalities: tuple[TrainingModality, ...]
    reason_codes: tuple[str, ...]
    work_seconds: int | None = None
    rest_seconds: int | None = None
    strength_exercise_id: str | None = None

    def __post_init__(self) -> None:
        allowed_reasons = {"bounded_prescription", "profile_experience", "profile_equipment", "limited_recovery",
                           "movement_constraint", "completed_history", "unverified_skill",
                           "unsupported_requested_station", "unsupported_box_jump"}
        if (self.version != "mixed-modal-session-v1" or not isinstance(self.format, SessionFormat)
                or type(self.time_cap_minutes) is not int or not 5 <= self.time_cap_minutes <= 60
                or not isinstance(self.modalities, tuple) or not self.modalities
                or any(not isinstance(item, TrainingModality) for item in self.modalities)
                or len(set(self.modalities)) != len(self.modalities)
                or not isinstance(self.reason_codes, tuple)
                or any(item not in allowed_reasons for item in self.reason_codes)
                or len(set(self.reason_codes)) != len(self.reason_codes)):
            raise ValueError("invalid mixed-modal session structure")
        timed = self.format is SessionFormat.INTERVALS
        if timed != (self.work_seconds is not None and self.rest_seconds is not None):
            raise ValueError("interval timing must be complete")
        if timed and (type(self.work_seconds) is not int or type(self.rest_seconds) is not int
                      or not 30 <= self.work_seconds <= 90 or not 30 <= self.rest_seconds <= 120):
            raise ValueError("invalid interval timing")
        if (self.format is SessionFormat.STRENGTH_METCON) != (self.strength_exercise_id is not None):
            raise ValueError("strength block identity is required only for strength plus metcon")

    def to_record(self) -> dict[str, object]:
        return {
            "version": self.version, "format": self.format.value,
            "time_cap_minutes": self.time_cap_minutes,
            "modalities": [item.value for item in self.modalities],
            "reason_codes": list(self.reason_codes),
            "work_seconds": self.work_seconds, "rest_seconds": self.rest_seconds,
            "strength_exercise_id": self.strength_exercise_id,
        }

    @classmethod
    def from_record(cls, value: object) -> MixedModalStructure | None:
        if not isinstance(value, Mapping) or set(value) != {
                "version", "format", "time_cap_minutes", "modalities", "reason_codes",
                "work_seconds", "rest_seconds", "strength_exercise_id"}:
            return None
        try:
            return cls(
                version=value["version"], format=SessionFormat(value["format"]),
                time_cap_minutes=value["time_cap_minutes"],
                modalities=tuple(TrainingModality(item) for item in value["modalities"]),
                reason_codes=tuple(value["reason_codes"]),
                work_seconds=value["work_seconds"], rest_seconds=value["rest_seconds"],
                strength_exercise_id=value["strength_exercise_id"],
            )
        except (TypeError, ValueError, KeyError):
            return None


_FORMAT_TERMS = (
    (SessionFormat.STRENGTH_METCON, ("strength + metcon", "strength and metcon", "strength metcon",
                                     "skill + metcon", "skill and metcon",
                                     "сила и меткон", "сила + меткон", "техника и меткон")),
    (SessionFormat.AMRAP, ("amrap", "амрап", "максимум кръгове")),
    (SessionFormat.EMOM, ("emom", "емом", "всяка минута")),
    (SessionFormat.FOR_TIME, ("for time", "за време")),
    (SessionFormat.INTERVALS, ("intervals", "interval", "интервали", "интервална")),
    (SessionFormat.ROUNDS_REPS, ("rounds", "rounds and reps", "кръгове", "кръгове и повторения")),
)
_STYLE_TERMS = ("crossfit", "cross-fit", "кросфит", "metcon", "меткон",
                "mixed-modal", "mixed modal", "wod")


def parse_mixed_modal_request(message: object) -> MixedModalRequest | None:
    """Classify an explicit training format, never a user's claimed skill level."""
    text = re.sub(r"\s+", " ", str(message or "").casefold()).strip()
    if not text:
        return None
    style = any(term in text for term in _STYLE_TERMS)
    explicit_format = next((kind for kind, terms in _FORMAT_TERMS
                            if any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text)
                                   for term in terms)), None)
    if not style and explicit_format is None:
        return None
    return MixedModalRequest(
        explicit_format or SessionFormat.ROUNDS_REPS,
        requested_olympic=bool(re.search(r"\b(?:snatch(?:es)?|clean(?:s|\s+and\s+jerk)?|jerk|олимпийск\w*|изхвърляне|изтласкване)\b", text)),
        requested_box_jumps=bool(re.search(r"\b(?:box jumps?|скокове? на кутия)\b", text)),
        requested_monostructural=bool(re.search(r"\b(?:row(?:ing|er)?|run(?:ning)?|bike|cycling|гребане|бягане|колело)\b", text)),
        knee_concern=bool(re.search(r"\b(?:knee|knees|колян\w*)\b", text)),
    )


def structure_mixed_modal_plan(
        plan: TrainingPlanBlueprintV2, *, request: MixedModalRequest,
        facts: Mapping[str, object], library: ExerciseLibrary,
        excluded_patterns: frozenset[MovementPattern] = frozenset(),
        completed_history: bool = False) -> TrainingPlanBlueprintV2:
    """Attach a traceable schedule without changing any exercise prescription."""
    if not isinstance(request, MixedModalRequest) or not plan.sessions:
        raise MixedModalPlanningError("mixed-modal request and training plan are required")
    # An explicit knee/box-jump concern cannot be translated into a safe movement
    # exclusion by this layer. Let the user/medical boundary establish one first.
    health = " ".join(str(facts.get(key) or "") for key in
                      ("injuries", "healthNotes", "trainingRestrictions", "medicalRestrictions"))
    if request.requested_box_jumps and (request.knee_concern or re.search(r"\b(?:knee|knees|колян\w*)\b", health.casefold())):
        raise MixedModalPlanningError("box-jump request with a knee limitation needs an explicit movement boundary")
    if all(session.mixed_modal is not None for session in plan.sessions):
        if (any(session.mixed_modal.format is not request.format for session in plan.sessions)
                or any(item.movement_pattern in excluded_patterns
                       for session in plan.sessions for item in session.prescriptions)):
            raise MixedModalPlanningError("existing mixed-modal plan is not safe to repeat")
        return plan

    reasons = ["bounded_prescription"]
    if str(facts.get("level") or facts.get("experience_level") or "").strip().casefold() in {
            "beginner", "intermediate", "advanced"}:
        reasons.append("profile_experience")
    if facts.get("equipment"):
        reasons.append("profile_equipment")
    if excluded_patterns:
        reasons.append("movement_constraint")
    if completed_history:
        reasons.append("completed_history")
    if request.requested_olympic:
        reasons.append("unverified_skill")
    if request.requested_monostructural:
        reasons.append("unsupported_requested_station")
    if request.requested_box_jumps:
        reasons.append("unsupported_box_jump")

    recovery = str(facts.get("recoveryFeel") or facts.get("sleepQuality") or "").casefold()
    limited = recovery in {"poor", "low", "limited"}
    kind = SessionFormat.INTERVALS if limited and request.format is SessionFormat.FOR_TIME else request.format
    if limited:
        reasons.append("limited_recovery")

    sessions = []
    for session in plan.sessions:
        modalities = []
        for prescription in session.prescriptions:
            exercise = library.require(prescription.exercise_id, prescription.exercise_version)
            if prescription.movement_pattern in excluded_patterns:
                raise MixedModalPlanningError("excluded movement entered mixed-modal plan")
            if exercise.difficulty is Difficulty.ADVANCED or "olympic" in exercise.training_tags:
                raise MixedModalPlanningError("unverified high-skill movement entered mixed-modal plan")
            modality = (TrainingModality.MONOSTRUCTURAL if "monostructural" in exercise.training_tags else
                        TrainingModality.OLYMPIC_DERIVATIVE if "olympic" in exercise.training_tags else
                        TrainingModality.GYMNASTICS if exercise.equipment == frozenset({Equipment.BODYWEIGHT}) else
                        TrainingModality.WEIGHTLIFTING)
            if modality not in modalities:
                modalities.append(modality)
        if len(modalities) < 2:
            raise MixedModalPlanningError("mixed-modal plan requires two supported modalities")
        if request.format is SessionFormat.STRENGTH_METCON and len(session.prescriptions) < 3:
            raise MixedModalPlanningError("strength plus metcon requires a separate strength movement")
        prescribed_sets = sum(item.sets for item in session.prescriptions)
        if kind is SessionFormat.EMOM:
            cap = prescribed_sets
        elif kind is SessionFormat.INTERVALS:
            rest = 90 if limited else 60
            cap = (prescribed_sets * (60 + rest) + 59) // 60
        else:
            cap = session.estimated_duration_minutes + (2 if kind is SessionFormat.FOR_TIME else 0)
        cap = max(5, min(60, cap))
        structure = MixedModalStructure(
            version="mixed-modal-session-v1", format=kind, time_cap_minutes=cap,
            modalities=tuple(modalities), reason_codes=tuple(reasons),
            work_seconds=60 if kind is SessionFormat.INTERVALS else None,
            rest_seconds=90 if limited and kind is SessionFormat.INTERVALS else
                         60 if kind is SessionFormat.INTERVALS else None,
            strength_exercise_id=(session.prescriptions[0].exercise_id
                                  if kind is SessionFormat.STRENGTH_METCON else None),
        )
        sessions.append(replace(session, mixed_modal=structure))
    signature = ";".join(
        f"{s.mixed_modal.format.value}:{s.mixed_modal.time_cap_minutes}:"
        f"{','.join(s.mixed_modal.reason_codes)}" for s in sessions)
    suffix = sha256(signature.encode("ascii")).hexdigest()[:10]
    return replace(plan, plan_id=f"{plan.plan_id}:mixed-modal:{suffix}", sessions=tuple(sessions))
