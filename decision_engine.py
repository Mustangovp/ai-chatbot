"""Deterministic shadow decisions for Phase B1.

The engine is intentionally pure: it reads no external state and its result is
not yet allowed to influence chat execution.  It exists solely to establish the
production decision contract alongside the existing ContextSnapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from context_builder import ContextSnapshot


Outcome = Literal["recommend", "recover", "clarify", "converse", "route"]
Intent = Literal[
    "workout", "nutrition", "recovery", "progress", "question", "motivation",
    "general_conversation", "medical", "account", "unknown",
]


@dataclass(frozen=True)
class DecisionResult:
    """Immutable, observational result of one deterministic shadow decision."""

    outcome: Outcome
    intent: Intent
    reason: str
    evidence: tuple[str, ...]
    confidence: float


_INTENT_KEYWORDS: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    ("medical", ("chest pain", "chest feels tight", "difficulty breathing", "fainting", "passed out", "suicidal",
                 "болка в гърдите", "стягане в гърдите", "затруднено дишане", "припадък", "самоубий")),
    ("recovery", ("recovery", "recover", "sore", "fatigue", "rest day")),
    ("nutrition", ("nutrition", "meal", "diet", "calories", "protein", "macros", "food")),
    ("workout", (
        "workout", "exercise", "training", "push-up", "pushup", "squat", "gym",
        "\u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a", "\u0443\u043f\u0440\u0430\u0436\u043d\u0435\u043d",
    )),
)


def classify_intent(message: str) -> Intent:
    """Return the narrow B1 shadow intent label without performing reasoning."""
    text = str(message or "").strip().lower()
    if not text or not any(char.isalnum() for char in text):
        return "unknown"
    for intent, keywords in _INTENT_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return intent
    return "general_conversation"


def decide(snapshot: ContextSnapshot, intent: Intent) -> DecisionResult:
    """Produce exactly one conservative outcome from the snapshot and intent."""
    # Reading the snapshot identity keeps the evidence subject-bound without
    # allowing the engine to inspect storage, browser state, or external APIs.
    evidence = (f"snapshot:{snapshot.snapshot_id}", f"intent:{intent}")
    if intent in ("workout", "nutrition"):
        return DecisionResult("recommend", intent, "coaching request", evidence, 1.0)
    if intent == "recovery":
        return DecisionResult("recover", intent, "recovery request", evidence, 1.0)
    if intent == "medical":
        return DecisionResult("route", intent, "medical red-flag route", evidence, 1.0)
    if intent == "unknown":
        return DecisionResult("clarify", intent, "request is empty or unknown", evidence, 1.0)
    return DecisionResult("converse", intent, "general conversation", evidence, 1.0)


def controlled_response(decision: DecisionResult, lang: str) -> str | None:
    """Return the fixed B2 delivery contract for non-generative outcomes only."""
    english = str(lang).lower() == "en"
    if decision.reason == "recommendation_integrity_contract":
        return ("I couldn't safely deliver that recommendation. Please try again." if english else
                "Не успях да доставя тази препоръка безопасно. Моля, опитай отново.")
    if decision.reason == "nutrition_delivery_contract":
        return ("I couldn't generate a complete nutrition plan that matches your current calorie target. "
                "I'll regenerate it." if english else
                "Не успях да генерирам пълен хранителен план, който съответства на текущия ти калориен таргет. Ще го генерирам отново.")
    if decision.outcome == "clarify":
        return "What would you like help with today?" if english else "С какво да помогна днес?"
    if decision.outcome == "route":
        if english:
            return ("I can't assess urgent medical symptoms here. Please contact a qualified medical "
                    "professional, or local emergency services if this feels urgent.")
        return ("Не мога да преценявам спешни медицински симптоми тук. Свържи се с квалифициран "
                "медицински специалист или със спешна помощ, ако това е неотложно.")
    return None
