"""Deterministic communication framing for APEX chat delivery.

The composer is deliberately presentation-only.  It never creates or changes a
decision, recommendation, nutrition contract, memory record, or renderer value.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Literal, Mapping


Mode = Literal[
    "answer_directly", "ask_one_question", "acknowledge_then_answer",
    "acknowledge_then_ask", "explain_decision", "deliver_structured_plan",
    "verbal_summary", "refuse_or_route",
]
Tone = Literal["direct", "supportive", "protective", "calm", "motivating"]
Depth = Literal["brief", "standard", "structured"]


@dataclass(frozen=True)
class ConversationPolicy:
    """Communication choices made before language generation."""

    mode: Mode
    tone: Tone
    acknowledge_context: bool
    ask_question: bool
    question: str | None
    answer_depth: Depth
    reference_memory: bool
    explain_why: bool
    verbal_summary_only: bool
    preserve_blueprint: bool
    must_not_generate_plan: bool
    must_not_repeat: bool
    must_not_greet: bool
    safety_boundary: bool
    fallback_to_legacy: bool


@dataclass(frozen=True)
class ConversationFrame:
    """Immutable LLM communication contract derived from a policy and safe inputs."""

    mode: Mode
    tone: Tone
    acknowledgement: bool
    reference_memory: bool
    reference_fact: str | None
    question: str | None
    answer_depth: Depth
    reason_style: Literal["none", "one_short_reason"]
    closing_style: Literal["no_question", "one_question", "natural_close"]
    spoken_summary: bool
    must_not_generate_plan: bool
    must_not_repeat: bool
    must_not_greet: bool
    preserve_blueprint: bool
    nutrition_contract_present: bool


_FRUSTRATION = (
    "frustrat", "giving up", "fed up", "sick of", "not working", "hopeless",
    "i'm tired of", "i’m tired of", "i am tired of", "i don't like this", "i don’t like this",
    "писна ми", "омръзна", "омръзна ми", "не ми харесва", "не се получава", "разочарован", "демотивир",
)
_MISUNDERSTOOD = (
    "not what i meant", "that’s not what i meant", "that's not what i meant", "not what i had in mind", "not this", "не това имах предвид",
    "не това", "не така",
)
_WHY = ("why", "tell me why", "кажи ми защо", "защо")
_PLAN_ONLY = ("just the plan", "only the plan", "само плана", "само план")
_BRIEF = ("briefly", "short", "talk briefly", "говори накратко", "накратко")
_TABLE_AVOIDANCE = ("don't read the table", "do not read the table", "не ми чети таблицата")
_ALTERNATIVE = ("another plan", "another regime", "different plan", "друг режим", "друг вариант")
_STOP_COMMANDS = frozenset({
    "спри", "стоп", "млъкни", "спри да говориш",
    "stop", "stop talking", "be quiet", "silence",
})


def _contains(text: str, phrases: Iterable[str]) -> bool:
    normalized = str(text or "").strip().lower()
    return any(phrase in normalized for phrase in phrases)


def is_exact_stop_command(message: str) -> bool:
    """Recognize transport stop commands without intercepting semantic uses."""
    normalized = str(message or "").strip().casefold().rstrip(".!?…").strip()
    return normalized in _STOP_COMMANDS


def _has_relevant_memory(conversation: Iterable[Mapping[str, object]] | None) -> bool:
    if not conversation:
        return False
    return any(
        isinstance(turn, Mapping)
        and str(turn.get("role") or "") in {"user", "assistant"}
        and bool(str(turn.get("content") or "").strip())
        for turn in conversation
    )


def build_policy(*, decision, message: str, conversation: Iterable[Mapping[str, object]] | None = None,
                 voice: bool = False, session_start: bool = False,
                 blueprint_present: bool = False, recommendation_kind: str | None = None,
                 structured_delivery: bool = False) -> ConversationPolicy:
    """Classify communication needs without changing the existing decision result."""
    outcome = str(getattr(decision, "outcome", "converse"))
    has_memory = _has_relevant_memory(conversation)
    frustration = _contains(message, _FRUSTRATION)
    misunderstood = _contains(message, _MISUNDERSTOOD)
    wants_why = _contains(message, _WHY)
    plan_only = _contains(message, _PLAN_ONLY)
    brief = _contains(message, _BRIEF)
    table_avoidance = _contains(message, _TABLE_AVOIDANCE)
    alternative = _contains(message, _ALTERNATIVE)
    del blueprint_present, recommendation_kind, structured_delivery

    if outcome == "route":
        return ConversationPolicy("refuse_or_route", "protective", False, False, None, "brief", False,
                                  False, False, True, True, True, True, True, False)
    if outcome == "clarify":
        return ConversationPolicy("ask_one_question", "calm", False, True, "request", "brief", False,
                                  False, False, True, True, True, True, False, False)
    if wants_why:
        return ConversationPolicy("explain_decision", "calm", False, False, None, "brief", has_memory,
                                  True, bool(voice), True, True, True, True, False, False)
    if plan_only:
        return ConversationPolicy("deliver_structured_plan", "direct", False, False, None, "structured",
                                  False, False, bool(voice), True, False, True, True, False, False)
    if table_avoidance or brief:
        return ConversationPolicy("verbal_summary" if voice else "answer_directly", "calm", False, False,
                                  None, "brief", has_memory and wants_why, wants_why, True, True, True,
                                  True, True, False, False)
    if misunderstood or alternative:
        return ConversationPolicy("acknowledge_then_ask", "supportive", True, True, "change", "brief",
                                  has_memory, False, bool(voice), True, True, True, True, False, False)
    if frustration:
        return ConversationPolicy("acknowledge_then_ask", "supportive", True, True, "obstacle", "brief",
                                  has_memory, False, bool(voice), True, True, True, True, False, False)
    if outcome == "recommend":
        return ConversationPolicy("deliver_structured_plan", "direct", False, False, None, "structured",
                                  False, not plan_only, bool(voice), True, False, True, True, False, False)
    if outcome == "recover":
        return ConversationPolicy("answer_directly", "protective", False, False, None, "standard", has_memory,
                                  True, bool(voice), True, False, True, True, False, False)
    return ConversationPolicy("answer_directly", "calm", False, False, None, "standard", False, False,
                              bool(voice), True, False, True, bool(session_start), False, False)


def compose(policy: ConversationPolicy, *, verified_memory: Iterable[Mapping[str, object]] | None = None,
            validated_blueprint=None, validated_nutrition_contract: bool = False,
            authority_facts: Mapping[str, object] | None = None,
            persona_projection: Mapping[str, object] | None = None,
            expert_communication_constraints: Iterable[str] | None = None) -> ConversationFrame:
    """Create a safe communication frame from approved, non-internal inputs only."""
    del persona_projection, expert_communication_constraints
    facts = authority_facts or {}
    reference_fact = next((key for key in ("recoveryFeel", "sleepQuality", "stressLevel", "goal")
                           if facts.get(key) not in (None, "", (), [])), None)
    has_memory = policy.reference_memory and _has_relevant_memory(verified_memory)
    blueprint_present = validated_blueprint is not None
    explain_why = policy.explain_why and not policy.must_not_generate_plan
    return ConversationFrame(
        mode=policy.mode,
        tone=policy.tone,
        acknowledgement=policy.acknowledge_context,
        reference_memory=has_memory,
        reference_fact=reference_fact if has_memory or explain_why else None,
        question=policy.question if policy.ask_question else None,
        answer_depth=policy.answer_depth,
        reason_style="one_short_reason" if explain_why else "none",
        closing_style="one_question" if policy.ask_question else "no_question" if policy.must_not_generate_plan else "natural_close",
        spoken_summary=policy.verbal_summary_only,
        must_not_generate_plan=policy.must_not_generate_plan,
        must_not_repeat=policy.must_not_repeat,
        must_not_greet=policy.must_not_greet,
        preserve_blueprint=policy.preserve_blueprint and blueprint_present,
        nutrition_contract_present=bool(validated_nutrition_contract),
    )


def render_prompt(frame: ConversationFrame, lang: str) -> str:
    """Render a communication-only system addendum; facts and plans stay elsewhere."""
    english = str(lang).lower() == "en"
    lines = [
        "[CONVERSATION COMPOSER V1 — COMMUNICATION ONLY]",
        "APEX is calm, observant, direct, and never theatrical, overly familiar, or hype-driven.",
        "Do not change the agreed coaching direction, verified fact, safety boundary, validated nutrition requirement, or structured plan.",
        f"Use a {frame.tone} coaching tone. Change language only, never facts.",
        f"Response depth: {frame.answer_depth}.",
    ]
    if frame.acknowledgement:
        lines.append("Begin with one brief acknowledgement of the user's stated experience. Do not invent context or diagnose.")
    if frame.reference_memory:
        lines.append("You may reference one relevant prior turn naturally; do not claim memory that is not present.")
    if frame.reason_style == "one_short_reason":
        lines.append("Give exactly one short reason using only verified facts or the existing recommendation explanation.")
    if frame.reference_fact:
        lines.append(f"When relevant, use only the already supplied verified {frame.reference_fact} context.")
    if frame.question:
        topic = "what they want changed" if frame.question == "change" else (
            "the immediate obstacle" if frame.question == "obstacle" else "what they need help with")
        if not english:
            topic = "какво иска да бъде променено" if frame.question == "change" else (
                "какво е непосредственото затруднение" if frame.question == "obstacle" else "с какво има нужда от помощ")
        lines.append(f"Ask exactly one short question about {topic}. Ask no other question.")
    if frame.must_not_generate_plan:
        lines.append("Do not generate, regenerate, extend, or alter a workout or nutrition plan in this reply.")
    if frame.must_not_repeat:
        lines.append("Do not repeat a previously delivered plan or greeting.")
    if frame.must_not_greet:
        lines.append("Do not greet or restart the relationship.")
    if frame.spoken_summary:
        lines.append("For spoken delivery, give one conclusion and at most one reason. Never read tables, lists, macros, sets, reps, or full plan contents aloud; the complete plan remains visual.")
    if frame.preserve_blueprint:
        lines.append("The supplied structured plan remains authoritative. Do not change, omit, add, reorder, or reinterpret any supplied value. These communication instructions affect wording only; the supplied plan wins if they conflict.")
    if frame.nutrition_contract_present:
        lines.append("The existing nutrition delivery contract remains authoritative. Never present an incomplete nutrition plan as complete.")
    return "\n".join(lines)


_MARKDOWN = re.compile(r"[*_`#>|]+")
_SPACE = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_INTERNAL_LANGUAGE = re.compile(
    r"\b(?:verdict|confidence|rule|intervention|decision layer|engine)\b",
    re.IGNORECASE,
)


def _plain_text(text: str) -> str:
    """Turn delivered text into a single safe spoken sentence stream."""
    lines = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or "|" in line:
            continue
        line = _MARKDOWN.sub("", line).strip(" -:")
        if line:
            lines.append(line)
    plain = _SPACE.sub(" ", " ".join(lines)).strip()
    return _INTERNAL_LANGUAGE.sub("", plain).strip(" ,:-")


def _visible_reason(reply: str, frame: ConversationFrame | None) -> str | None:
    """Use one reason only when the delivered wording already contains one."""
    if frame is None or frame.reason_style != "one_short_reason":
        return None
    for raw in str(reply or "").splitlines():
        line = raw.strip()
        if not line.startswith("-") or "|" in line or "**" in line or ":" not in line:
            continue
        _, reason = line.split(":", 1)
        reason = _plain_text(reason)
        if reason and len(reason) <= 180:
            return reason.rstrip(".") + "."
    return None


def speech_projection(reply: str, frame: ConversationFrame | None, lang: str, *,
                      structured_kind: str | None = None, safety_response: bool = False) -> str | None:
    """Create a deterministic, non-persisted voice delivery projection.

    The visible reply remains the record.  This projection never asks the model
    for another response and deliberately abstains if a safe short delivery is
    not available.
    """
    if not str(reply or "").strip():
        return None
    if safety_response:
        return str(reply).strip()
    if frame is None or not frame.spoken_summary:
        return None

    english = str(lang).lower() == "en"
    kind = str(structured_kind or "").lower()
    if kind == "workout":
        intro = "Your workout is ready." if english else "Тренировката ти е готова."
        ending = ("The full plan is visible on screen." if english
                  else "Пълният план е на екрана.")
        reason = _visible_reason(reply, frame)
        return " ".join(part for part in (intro, reason, ending) if part)
    if kind == "nutrition":
        intro = ("Your complete daily nutrition plan is ready." if english
                 else "Пълният ти хранителен план за деня е готов.")
        ending = ("The meals and exact values are visible on screen." if english
                  else "Храненията и точните стойности са на екрана.")
        return f"{intro} {ending}"

    visible = _plain_text(reply)
    if not visible:
        return None
    sentences = _SENTENCE.split(visible)
    short_reply = " ".join(sentences[:2]).strip()
    return short_reply[:420].rstrip()
