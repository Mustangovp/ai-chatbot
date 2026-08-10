"""Non-medical product boundary for health-aware APEX coaching.

Existing health knowledge remains internal safety-matching data.  This module
turns a match into a product-scope outcome; it never diagnoses, names a
condition, ranks disease probability, or produces treatment guidance.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from brain.redflag_library import detect_flag_classes


class HealthSafetyScope(str, Enum):
    NORMAL_FITNESS = "normal_fitness"
    FITNESS_LIMITATION = "fitness_limitation"
    DECLARED_HEALTH_CONTEXT = "declared_health_context"
    MEDICAL_BOUNDARY = "medical_boundary"


@dataclass(frozen=True)
class HealthScopeDecision:
    """Request-scoped scope decision with no diagnosis-like payload."""

    scope: HealthSafetyScope
    source: str = "none"  # current_message | prior_turn | profile | none

    @property
    def blocks_prescription(self) -> bool:
        return self.scope is HealthSafetyScope.MEDICAL_BOUNDARY


def medical_boundary_message(lang: str) -> str:
    """Single non-diagnostic user-facing boundary for all internal matches."""
    if str(lang).lower() == "en":
        return ("I can't assess or diagnose medical symptoms, and I can't safely recommend "
                "training based on what you've described. Please speak with a qualified "
                "healthcare professional before continuing. If you believe the situation "
                "may be urgent, contact your local emergency medical service.")
    return ("APEX не може да оценява или диагностицира медицински симптоми и не може "
            "безопасно да препоръча тренировка въз основа на описаното. Обърни се към "
            "квалифициран медицински специалист, преди да продължиш. Ако смяташ, че "
            "ситуацията може да е спешна, потърси местна спешна медицинска помощ.")


def declared_context_prompt(lang: str) -> str:
    """Keep permitted coaching inside general fitness/wellness scope."""
    if str(lang).lower() == "en":
        return ("HEALTH SCOPE: The user has declared health context. Stay within general "
                "fitness/wellness only. Respect their stated or clinician-provided restrictions "
                "exactly. Do not diagnose, treat, rehabilitate, manage a disease, change medical "
                "limits, claim clearance, or give medication advice.")
    return ("ГРАНИЦА НА ЗДРАВНИЯ ОБХВАТ: Потребителят е споделил здравен контекст. "
            "Остани само в общ фитнес/уелнес обхват. Спазвай точно заявените от него или "
            "от клиницист ограничения. Не диагностицирай, не лекувай, не предписвай "
            "рехабилитация, не управлявай заболяване, не променяй медицински лимити, не "
            "твърди медицинско разрешение и не давай съвети за лекарства.")


def _text(value: object) -> str:
    return str(value or "").casefold()


def _legacy_arm_neuro_signal(text: str) -> bool:
    """Retain the established personally-reported arm/shoulder safety hold."""
    shoulder = "shoulder" in text or "рамо" in text
    arm = "arm" in text or "рък" in text
    numb = any(token in text for token in (
        "numb", "tingl", "loss of sensation", "изтръп", "мравуч"))
    weak = "arm weakness" in text or "weakness in" in text or "слабост" in text
    personal = any(token in text for token in (
        "ме", "ми", "i have", "my ", "i'm", "i am"))
    return personal and ((shoulder and arm and numb) or (arm and (numb or weak)))


def therapeutic_nutrition_request(message: object) -> bool:
    """Detect a request to use nutrition as disease treatment, not general planning."""
    text = _text(message)
    nutrition = any(token in text for token in (
        "nutrition", "diet", "meal", "food", "calories", "macros",
        "хран", "диета", "меню", "калори", "макрос",
    ))
    treatment = any(token in text for token in (
        "treat", "cure", "heal", "therapy", "therapeutic", "лекува", "излекува",
        "терап", "лечение",
    ))
    management = any(token in text for token in (
        "manage", "control", "disease", "condition", "diabetes", "hypertension",
        "управля", "контролира", "заболяв", "диабет", "хипертония",
    ))
    return nutrition and treatment or (nutrition and management and any(
        token in text for token in (
            "disease", "condition", "diabetes", "hypertension", "заболяв", "диабет", "хипертония")))


def _has_declared_context(profile: Mapping[str, object] | None) -> bool:
    if not isinstance(profile, Mapping):
        return False
    return any(str(profile.get(key) or "").strip() for key in (
        "healthNotes", "injuries", "medicalRestrictions", "clinicianRestrictions",
    ))


def _has_explicit_limitation(text: str) -> bool:
    movement = any(token in text for token in (
        "shoulder", "overhead", "press", "push-up", "squat", "рамо", "преса", "лицев",
        "клек",
    ))
    exclusion = any(token in text for token in (
        "avoid", "don't include", "do not include", "without", "no ", "избяг", "без ",
        "не включвай", "не натоварвай",
    ))
    return movement and exclusion


def assess_health_scope(*, message: object, conversation: Sequence[object] | None = None,
                        profile: Mapping[str, object] | None = None) -> HealthScopeDecision:
    """Classify product scope without exposing internal health labels downstream."""
    current = _text(message)
    if detect_flag_classes(current) or _legacy_arm_neuro_signal(current) or therapeutic_nutrition_request(current):
        return HealthScopeDecision(HealthSafetyScope.MEDICAL_BOUNDARY, "current_message")

    for turn in conversation or ():
        if isinstance(turn, Mapping) and turn.get("role") == "user":
            prior = _text(turn.get("content"))
            if detect_flag_classes(prior) or _legacy_arm_neuro_signal(prior):
                return HealthScopeDecision(HealthSafetyScope.MEDICAL_BOUNDARY, "prior_turn")

    if _has_explicit_limitation(current):
        return HealthScopeDecision(HealthSafetyScope.FITNESS_LIMITATION, "current_message")
    if _has_declared_context(profile):
        return HealthScopeDecision(HealthSafetyScope.DECLARED_HEALTH_CONTEXT, "profile")
    return HealthScopeDecision(HealthSafetyScope.NORMAL_FITNESS)
