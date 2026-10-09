"""Deterministic orchestration for a single nutrition conversation outcome.

This module owns nutrition-plan intake, clarification suppression, and final
delivery validation. It has no model, storage, HTTP, renderer, or V2 imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import re
from typing import Callable, Iterable, Mapping

import nutrition_validation
import nutrition_plan


class NutritionConversationState(str, Enum):
    READY = "ready"
    NEEDS_INFORMATION = "needs_information"
    GENERATING = "generating"
    PLAN_READY = "plan_ready"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True)
class NutritionConversation:
    """Immutable, request-scoped authority for nutrition conversation handling."""

    state: NutritionConversationState
    plan_requested: bool
    response_guard: bool
    targets: nutrition_validation.NutritionTargets | None
    reason: str
    user_response: str | None = None
    failures: tuple[str, ...] = ()


_PLAN_REQUEST_PATTERNS = (
    re.compile(r"\b(?:i\s+(?:want|need|would\s+like)|make|give)\s+(?:me\s+)?(?:a\s+)?(?:nutrition|meal|diet)\s+plan\b", re.I),
    re.compile(r"\b(?:nutrition|meal|diet)\s+plan\s*(?:please|for\s+me)?\b", re.I),
    re.compile(r"\b(?:\u0438\u0441\u043a\u0430\u043c|\u043d\u0443\u0436\u0434\u0430\u044f\s+\u0441\u0435\s+\u043e\u0442)\s+(?:\u043c\u0438\s+)?\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u043f\u043b\u0430\u043d\b", re.I),
    re.compile(r"\b\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u0440\u0435\u0436\u0438\u043c\b", re.I),
    re.compile(r"\b(?:\u0440\u0435\u0436\u0438\u043c(?:\s+\u0437\u0430\s+(?:\u043c\u0430\u0441\u0430|\u0447\u0438\u0441\u0442\u0435\u043d\u0435))?|\u043c\u0435\u043d\u044e|\u0434\u043d\u0435\u0432\u043d\u043e\s+\u043c\u0435\u043d\u044e|\u0434\u0438\u0435\u0442\u0430)\b", re.I),
)


def _values(profile: Mapping[str, object] | None, *keys: str) -> str:
    if not isinstance(profile, Mapping):
        return ""
    return " ".join(str(profile.get(key) or "") for key in keys).lower()


def unsupported_diet_reason(message: str, profile: Mapping[str, object] | None) -> str | None:
    """Canonical, deliberately narrow diet policy for plan creation and edits."""
    text = f"{message} {_values(profile, 'diet', 'dietaryRestrictions', 'foodPreferences')}".lower()
    vegan = "vegan" in text or "\u0432\u0435\u0433\u0430\u043d" in text
    keto = "keto" in text or "\u043a\u0435\u0442\u043e" in text
    carnivore = "carnivore" in text or "\u043a\u0430\u0440\u043d\u0438\u0432\u043e\u0440" in text
    only_peanuts = bool(re.search(r"(?:only\s+peanuts|\u0441\u0430\u043c\u043e\s+\u0444\u044a\u0441\u0442\u044a\u0446\u0438)", text, re.I))
    allergies = _values(profile, "allergies")
    peanut_allergy = "peanut" in allergies or "\u0444\u044a\u0441\u0442\u044a\u043a" in allergies
    if (vegan and keto) or (vegan and carnivore) or (keto and carnivore):
        return "conflicting_diet"
    if keto or carnivore:
        return "unsupported_diet"
    if only_peanuts and peanut_allergy:
        return "allergy_conflict"
    return None


def unsupported_diet_message(lang: str) -> str:
    if _english(lang):
        return "I can't apply those dietary restrictions together to a nutrition plan."
    return "Не мога да приложа тези хранителни ограничения заедно към хранителен план."


def parse_revision_operation(message: str) -> nutrition_plan.RevisionOperation | None:
    """Recognize only supported typed edits; no free-form revision fallback."""
    text = str(message or "").strip().lower()
    if re.search(r"(?:\bno\s+chicken\b|\u0431\u0435\u0437\s+\u043f\u0438\u043b\u0435\u0448\u043a\u043e)", text, re.I):
        return nutrition_plan.RevisionOperation(nutrition_plan.RevisionKind.REPLACE_INGREDIENT, "chicken")
    if re.search(r"(?:\breplace\s+(?:the\s+)?breakfast\b|\u0437\u0430\u043c\u0435\u043d\u0438\s+\u0437\u0430\u043a\u0443\u0441\u043a\u0430\u0442\u0430)", text, re.I):
        return nutrition_plan.RevisionOperation(nutrition_plan.RevisionKind.REPLACE_MEAL, "breakfast")
    if re.search(r"(?:\b(?:more|increase)\s+rice\b|\u0434\u043e\u0431\u0430\u0432\u0438\s+\u043f\u043e\u0432\u0435\u0447\u0435\s+\u043e\u0440\u0438\u0437)", text, re.I):
        return nutrition_plan.RevisionOperation(nutrition_plan.RevisionKind.INCREASE_QUANTITY, "rice")
    return None


@dataclass(frozen=True)
class PlanRevisionRequest:
    operation: nutrition_plan.RevisionOperation | None = None
    restrictions: tuple[str, ...] = ()
    simpler_preparation: bool = False
    supported: bool = True


def parse_plan_revision(message: str) -> PlanRevisionRequest | None:
    """Route explicit plan edits, never turn unknown edits into model prose.

    Food exclusions are accepted only through the existing closed constraint
    vocabulary. An unrecognized exclusion is clarification, not a guessed fact.
    """
    from nutrition_constraints import ConstraintKind, canonical_constraints

    text = str(message or "").strip().casefold()
    if (re.search(r"workout|\bwod\b|exercise|трениров|упражнен", text)
            and not re.search(r"nutrition|meals?|foods?|diet|dairy|хран|млеч|меню", text)):
        return None
    operation = parse_revision_operation(text)
    simpler = bool(re.search(
        r"\b(?:simplify|easier|simpler)\b.*\b(?:plan|meals?|prepar\w*|cook\w*)\b"
        r"|\b(?:по-лес\w*|опрости)\b.*\b(?:приготв\w*|план\w*|хранения\w*)\b", text))
    plan_edit = bool(re.search(
        r"\b(?:change|modify|revise|update|simplify|replace|remove)\b.*\b(?:plan|meals?|menu)\b"
        r"|\b(?:промени|преработи|редактирай|опрости|замени|премахни)\b.*\b(?:план\w*|меню\w*|хранения\w*)\b", text))
    if not plan_edit and not simpler and (
            is_plan_request(text) or re.match(r"(?:what|which|how|какво|как|кои)\b", text)):
        return None
    restrictions = []
    unsupported = False
    # Negation is clause-local; a later clause about keeping targets is not
    # interpreted as another food exclusion.
    for clause in re.split(r"[.;!?,]|\b(?:but|но)\b", text):
        match = re.search(
            r"\b(?:no|without(?:\s+reintroducing)?|remove|exclude|avoid|"
            r"i\s+(?:do\s+not|don't)\s+want|без(?:\s+да\s+връщаш)?|"
            r"не\s+искам|премахни|изключи|избягвай|не\s+връщай)\s+(.+)", clause)
        if not match:
            continue
        food_text = re.split(r"\s+(?:from|от)\s+", match[1], maxsplit=1)[0].strip(" ,")
        food_text = re.sub(r"\b(?:products?|продукти|the)\b", "", food_text).strip()
        food_text = food_text.replace("овесените ядки", "овесени ядки")
        for food in re.split(r"\s+(?:and|or|и|или)\s+", food_text):
            food = re.sub(r"^(?:no|без)\s+", "", food)
            candidate = "no " + food
            constraints = canonical_constraints((candidate,))
            if constraints and all(item.kind is not ConstraintKind.UNSUPPORTED for item in constraints):
                restrictions.append(candidate)
            elif plan_edit or simpler or restrictions:
                unsupported = True
    if not (operation or restrictions or simpler or plan_edit or unsupported):
        return None
    # A compound request must not silently apply just the first typed operation.
    if operation and not simpler and not unsupported and len(restrictions) <= 1:
        return PlanRevisionRequest(operation=operation)
    return PlanRevisionRequest(restrictions=tuple(restrictions), simpler_preparation=simpler,
                               supported=not unsupported and bool(restrictions or simpler))


_PROFILE_FIELDS = (
    ("age", "age", "\u0432\u044a\u0437\u0440\u0430\u0441\u0442"),
    ("gender", "sex", "\u043f\u043e\u043b"),
    ("height", "height", "\u0440\u044a\u0441\u0442"),
    ("weight", "weight", "\u0442\u0435\u0433\u043b\u043e"),
    ("goal", "primary goal", "\u043e\u0441\u043d\u043e\u0432\u043d\u0430 \u0446\u0435\u043b"),
)


def _english(lang: str) -> bool:
    return str(lang).lower() == "en"


def is_plan_request(message: str, history: object = None) -> bool:
    text = str(message or "")
    return nutrition_validation.is_full_day_request(text, history) or any(
        pattern.search(text) for pattern in _PLAN_REQUEST_PATTERNS
    )


def _missing_profile_fields(profile: Mapping[str, object] | None, lang: str) -> tuple[str, ...]:
    profile = profile if isinstance(profile, Mapping) else {}
    language_index = 1 if _english(lang) else 2
    return tuple(label[language_index] for label in _PROFILE_FIELDS if not str(profile.get(label[0]) or "").strip())


def clarification_message(missing: Iterable[str], lang: str) -> str:
    fields = tuple(missing)
    joined = ", ".join(fields)
    if _english(lang):
        return f"To prepare a complete daily nutrition plan, what is your {joined}?"
    return f"За да подготвя пълен дневен хранителен план, какви са твоите {joined}?"


def unsupported_message(lang: str) -> str:
    if _english(lang):
        return "I still need the missing confirmed profile information before I can prepare a complete daily nutrition plan."
    return "Все още ми липсва потвърдена информация от профила ти, за да подготвя пълен дневен хранителен план."


def failed_message(lang: str) -> str:
    if _english(lang):
        return "I can't provide a complete daily nutrition plan that meets the confirmed targets."
    return "Не мога да предоставя пълен дневен хранителен план, който отговаря на потвърдените цели."


def revision_unavailable_message(lang: str) -> str:
    if _english(lang):
        return "I need an existing nutrition plan before I can update it."
    return "Нуждая се от съществуващ хранителен план, преди да мога да го променя."


def revision_unsupported_message(lang: str) -> str:
    if _english(lang):
        return "I can't apply that change to the current nutrition plan."
    return "Не мога да приложа тази промяна към текущия хранителен план."


def _was_already_asked(history: object, response: str) -> bool:
    if not isinstance(history, list):
        return False
    return any(
        isinstance(turn, Mapping)
        and turn.get("role") == "assistant"
        and str(turn.get("content") or "").strip() == response
        for turn in history
    )


def begin(*, message: str, history: object, profile: Mapping[str, object] | None,
          profile_block: str, intent: str, session_start: bool, medical_route: bool,
          lang: str, authoritative_targets: nutrition_validation.NutritionTargets | None = None) -> NutritionConversation:
    """Choose the sole nutrition conversation state before any model generation."""
    requested = is_plan_request(message, history)
    nutrition_intent = str(intent) == "nutrition"
    guard = requested or nutrition_intent
    if session_start or medical_route or not guard:
        return NutritionConversation(NutritionConversationState.READY, requested, guard, None, "not_a_plan_request")

    policy_reason = unsupported_diet_reason(message, profile)
    if requested and policy_reason is not None:
        return NutritionConversation(
            NutritionConversationState.UNSUPPORTED, True, True, None,
            policy_reason, unsupported_diet_message(lang),
        )

    targets = authoritative_targets or nutrition_validation.targets_from_profile_block(profile_block)
    if not requested:
        return NutritionConversation(NutritionConversationState.READY, False, True, targets, "nutrition_guidance")
    if targets is not None and targets.kcal > Decimal("0"):
        return NutritionConversation(NutritionConversationState.PLAN_READY, True, True, targets, "targets_confirmed")

    missing = _missing_profile_fields(profile, lang)
    if not missing:
        return NutritionConversation(
            NutritionConversationState.UNSUPPORTED, True, True, None,
            "target_authority_unavailable", unsupported_message(lang),
        )
    clarification = clarification_message(missing, lang)
    if _was_already_asked(history, clarification):
        return NutritionConversation(
            NutritionConversationState.UNSUPPORTED, True, True, None,
            "clarification_already_asked", unsupported_message(lang),
        )
    return NutritionConversation(
        NutritionConversationState.NEEDS_INFORMATION, True, True, None,
        "missing_profile_authority", clarification,
    )


def generating(conversation: NutritionConversation) -> NutritionConversation:
    if conversation.state is not NutritionConversationState.PLAN_READY:
        raise ValueError("only a plan-ready nutrition conversation may generate")
    return NutritionConversation(
        NutritionConversationState.GENERATING, True, True, conversation.targets,
        conversation.reason,
    )


def revised(conversation: NutritionConversation,
            targets: nutrition_validation.NutritionTargets) -> NutritionConversation:
    """Mark a typed edit of an existing canonical plan as one plan-ready turn."""
    return NutritionConversation(
        NutritionConversationState.PLAN_READY, True, True, targets,
        "structured_plan_revised",
    )


def accept_delivery(conversation: NutritionConversation, text: str, lang: str) -> NutritionConversation:
    """Validate one completed plan and return the only final delivery outcome."""
    if conversation.state is not NutritionConversationState.GENERATING or conversation.targets is None:
        raise ValueError("only a generating nutrition conversation may accept delivery")
    validation = nutrition_validation.validate_daily_nutrition(text, conversation.targets)
    if validation.valid:
        return NutritionConversation(
            NutritionConversationState.PLAN_READY, True, True, conversation.targets,
            "validated_plan", validation.delivery,
        )
    return NutritionConversation(
        NutritionConversationState.FAILED, True, True, conversation.targets,
        "validation_failed", failed_message(lang), tuple(validation.failures),
    )


def validate_observed_delivery(conversation: NutritionConversation, text: str, lang: str) -> NutritionConversation:
    """Validate a plan-shaped nutrition reply without starting another generation."""
    if conversation.targets is None:
        return fail_generation(conversation, lang, "missing_target_authority")
    generating_state = NutritionConversation(
        NutritionConversationState.GENERATING, conversation.plan_requested,
        conversation.response_guard, conversation.targets, conversation.reason,
    )
    return accept_delivery(generating_state, text, lang)


def fail_generation(conversation: NutritionConversation, lang: str, reason: str) -> NutritionConversation:
    """Fail closed without attempting another engine or model fallback."""
    return NutritionConversation(
        NutritionConversationState.FAILED, conversation.plan_requested,
        conversation.response_guard, conversation.targets, reason, failed_message(lang),
    )
