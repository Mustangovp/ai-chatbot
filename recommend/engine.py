"""Deterministic recommendation planning before any prompt or renderer exists."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

from knowledge import KnowledgeDomain, KnowledgeResolver


BLUEPRINT_VERSION = "recommendation-blueprint-v1"


class RecommendationIntent(str, Enum):
    WORKOUT = "workout"
    NUTRITION = "nutrition"
    RECOVERY = "recovery"
    SUPPLEMENTATION = "supplementation"


class ProfileCompleteness(str, Enum):
    SUFFICIENT = "sufficient"
    INCOMPLETE = "incomplete"
    CONFLICTING = "conflicting"


class RecommendationOutcome(str, Enum):
    RECOMMEND = "recommend"
    CLARIFY = "clarify"
    AWAITING_PROFILE = "awaiting_profile"
    UNAVAILABLE = "unavailable"


_REQUIRED_PROFILE_FIELDS = MappingProxyType({
    RecommendationIntent.WORKOUT: ("goal", "equipment", "level"),
    RecommendationIntent.NUTRITION: ("age", "height", "weight", "goal"),
    RecommendationIntent.RECOVERY: (),
    RecommendationIntent.SUPPLEMENTATION: (),
})
_DOMAIN_FOR_INTENT = MappingProxyType({
    RecommendationIntent.WORKOUT: KnowledgeDomain.TRAINING,
    RecommendationIntent.NUTRITION: KnowledgeDomain.NUTRITION,
    RecommendationIntent.RECOVERY: KnowledgeDomain.RECOVERY,
    RecommendationIntent.SUPPLEMENTATION: KnowledgeDomain.SUPPLEMENTATION,
})
_FIELD_LABELS = MappingProxyType({
    "age": ("age", "\u0432\u044a\u0437\u0440\u0430\u0441\u0442"),
    "height": ("height", "\u0440\u044a\u0441\u0442"),
    "weight": ("weight", "\u0442\u0435\u0433\u043b\u043e"),
    "goal": ("primary goal", "\u043e\u0441\u043d\u043e\u0432\u043d\u0430 \u0446\u0435\u043b"),
    "equipment": ("equipment", "\u043e\u0431\u043e\u0440\u0443\u0434\u0432\u0430\u043d\u0435"),
    "level": ("experience level", "\u043d\u0438\u0432\u043e \u043e\u043f\u0438\u0442"),
    "experience_level": ("experience level", "\u043d\u0438\u0432\u043e \u043e\u043f\u0438\u0442"),
})


def _freeze(value: Any):
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in
                                 sorted(value.items(), key=lambda item: str(item[0]))})
    if isinstance(value, (set, frozenset)):
        return tuple(_freeze(item) for item in sorted(value, key=lambda item: repr(item)))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _canonical(value: Any):
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in
                sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _value(value: Any) -> Any:
    """Accept a ContextSnapshot fact without depending on its module type."""
    return getattr(value, "value", value)


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == () or value == [] or value == {}


def _normalized(value: Any) -> str:
    return str(value).strip().lower()


@dataclass(frozen=True)
class ImmutableUserProfile:
    """Validated request input; only verified facts and locked preferences are retained."""
    facts: Mapping[str, Any]
    locked_preferences: Mapping[str, tuple[str, ...]] = MappingProxyType({})
    clarification_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", _freeze({key: _value(value) for key, value in self.facts.items()}))
        object.__setattr__(self, "locked_preferences", _freeze(self.locked_preferences))
        object.__setattr__(self, "clarification_history", tuple(sorted({
            str(field).strip() for field in self.clarification_history if str(field).strip()
        })))

    @classmethod
    def from_verified_facts(cls, facts: Mapping[str, Any], *,
                            locked_preferences: Mapping[str, tuple[str, ...]] | None = None,
                            clarification_history: tuple[str, ...] = ()) -> "ImmutableUserProfile":
        return cls(facts=dict(facts), locked_preferences=dict(locked_preferences or {}),
                   clarification_history=clarification_history)


@dataclass(frozen=True)
class RecommendationReason:
    code: str
    source: str
    detail: str


@dataclass(frozen=True)
class RecommendationBlueprint:
    """Immutable planning output. It contains no prompt, prose, or user identifiers."""
    blueprint_id: str
    version: str
    intent: RecommendationIntent
    outcome: RecommendationOutcome
    profile_completeness: ProfileCompleteness
    knowledge_registry_version: str
    knowledge_document_ids: tuple[str, ...]
    reasons: tuple[RecommendationReason, ...]
    missing_fields: tuple[str, ...]
    conflict_fields: tuple[str, ...]
    clarification_field: str | None
    training_split: str | None = None


def clarification_message(field: str, lang: str) -> str:
    """One deterministic, field-specific question; it contains no inferred data."""
    english = str(lang).lower() == "en"
    label = _FIELD_LABELS.get(field, (field, field))[0 if english else 1]
    if english:
        return f"To prepare your plan, what is your {label}?"
    return f"\u0417\u0430 \u0434\u0430 \u043f\u043e\u0434\u0433\u043e\u0442\u0432\u044f \u043f\u043b\u0430\u043d\u0430 \u0442\u0438, \u043a\u0430\u043a\u044a\u0432 \u0435 \u0442\u0432\u043e\u044f\u0442 {label}?"


def awaiting_profile_message(lang: str) -> str:
    if str(lang).lower() == "en":
        return "I still need the profile detail I already asked for before I can prepare the plan."
    return "\u0412\u0441\u0435 \u043e\u0449\u0435 \u043c\u0438 \u0442\u0440\u044f\u0431\u0432\u0430 \u0434\u0435\u0442\u0430\u0439\u043b\u044a\u0442 \u043e\u0442 \u043f\u0440\u043e\u0444\u0438\u043b\u0430, \u0437\u0430 \u043a\u043e\u0439\u0442\u043e \u0432\u0435\u0447\u0435 \u043f\u043e\u043f\u0438\u0442\u0430\u0445."


def clarification_history(conversation: object, lang: str) -> tuple[str, ...]:
    """Recover only this planner's exact prior questions from delivered history."""
    if not isinstance(conversation, (list, tuple)):
        return ()
    asked = set()
    messages = {
        field: clarification_message(field, lang)
        for fields in _REQUIRED_PROFILE_FIELDS.values() for field in fields
    }
    for turn in conversation:
        if not isinstance(turn, Mapping) or turn.get("role") != "assistant":
            continue
        content = str(turn.get("content") or "").strip()
        for field, message in messages.items():
            if content == message:
                asked.add(field)
    return tuple(sorted(asked))


class RecommendationEngine:
    """Pure planner: profile completeness -> knowledge retrieval -> blueprint."""
    def __init__(self, knowledge_resolver: KnowledgeResolver):
        self._knowledge_resolver = knowledge_resolver

    @staticmethod
    def _conflicts(profile: ImmutableUserProfile) -> tuple[str, ...]:
        facts = profile.facts
        conflicts = []
        for field in ("goal", "level", "experience_level"):
            value = facts.get(field)
            if isinstance(value, tuple) and len({_normalized(item) for item in value if not _is_missing(item)}) > 1:
                conflicts.append(field)
        level = facts.get("level")
        experience = facts.get("experience_level")
        if not _is_missing(level) and not _is_missing(experience) and _normalized(level) != _normalized(experience):
            conflicts.append("experience_level")
        return tuple(sorted(set(conflicts)))

    @staticmethod
    def _required_fields(intent: RecommendationIntent, profile: ImmutableUserProfile) -> tuple[str, ...]:
        return _REQUIRED_PROFILE_FIELDS[intent]

    @classmethod
    def _missing(cls, intent: RecommendationIntent, profile: ImmutableUserProfile) -> tuple[str, ...]:
        return tuple(field for field in cls._required_fields(intent, profile)
                     if _is_missing(profile.facts.get(field)))

    @staticmethod
    def _id(*, intent: RecommendationIntent, profile: ImmutableUserProfile,
            outcome: RecommendationOutcome, registry_version: str,
            document_ids: tuple[str, ...], missing: tuple[str, ...], conflicts: tuple[str, ...]) -> str:
        source = {
            "intent": intent.value, "facts": _canonical(profile.facts),
            "locked_preferences": _canonical(profile.locked_preferences),
            "clarification_history": profile.clarification_history, "outcome": outcome.value,
            "registry_version": registry_version, "documents": document_ids,
            "missing": missing, "conflicts": conflicts,
        }
        return "rec_" + sha256(json.dumps(source, ensure_ascii=True, sort_keys=True, default=str,
                                            separators=(",", ":")).encode("utf-8")).hexdigest()[:24]

    def _build(self, *, intent: RecommendationIntent, profile: ImmutableUserProfile,
               outcome: RecommendationOutcome, completeness: ProfileCompleteness,
               documents: tuple[str, ...], reasons: tuple[RecommendationReason, ...],
               missing: tuple[str, ...] = (), conflicts: tuple[str, ...] = (),
               clarification: str | None = None) -> RecommendationBlueprint:
        return RecommendationBlueprint(
            blueprint_id=self._id(intent=intent, profile=profile, outcome=outcome,
                                  registry_version=self._knowledge_resolver.registry_version,
                                  document_ids=documents, missing=missing, conflicts=conflicts),
            version=BLUEPRINT_VERSION, intent=intent, outcome=outcome,
            profile_completeness=completeness,
            knowledge_registry_version=self._knowledge_resolver.registry_version,
            knowledge_document_ids=documents, reasons=reasons, missing_fields=missing,
            conflict_fields=conflicts, clarification_field=clarification,
            training_split=(str(profile.facts.get("training_split")).strip()
                            if intent is RecommendationIntent.WORKOUT
                            and not _is_missing(profile.facts.get("training_split")) else None),
        )

    def plan(self, intent: RecommendationIntent | str, profile: ImmutableUserProfile) -> RecommendationBlueprint:
        selected_intent = RecommendationIntent(intent)
        conflicts = self._conflicts(profile)
        missing = self._missing(selected_intent, profile)
        pending = conflicts or missing
        if pending:
            field = pending[0]
            already_asked = field in profile.clarification_history
            outcome = RecommendationOutcome.AWAITING_PROFILE if already_asked else RecommendationOutcome.CLARIFY
            completeness = ProfileCompleteness.CONFLICTING if conflicts else ProfileCompleteness.INCOMPLETE
            reason = RecommendationReason(
                "profile_conflict" if conflicts else "profile_incomplete", "profile", field)
            return self._build(intent=selected_intent, profile=profile, outcome=outcome,
                               completeness=completeness, documents=(), reasons=(reason,),
                               missing=missing, conflicts=conflicts,
                               clarification=None if already_asked else field)

        resolution = self._knowledge_resolver.resolve(_DOMAIN_FOR_INTENT[selected_intent])
        document_ids = tuple(document.document_id for document in resolution.documents)
        if not resolution.domain_available:
            return self._build(
                intent=selected_intent, profile=profile, outcome=RecommendationOutcome.UNAVAILABLE,
                completeness=ProfileCompleteness.SUFFICIENT, documents=(),
                reasons=(RecommendationReason("knowledge_unavailable", "knowledge", selected_intent.value),),
            )
        reasons = tuple(
            [RecommendationReason("verified_profile", "profile", field)
             for field in self._required_fields(selected_intent, profile)]
            + [RecommendationReason("knowledge_selected", "knowledge", document_id)
               for document_id in document_ids]
        )
        return self._build(intent=selected_intent, profile=profile, outcome=RecommendationOutcome.RECOMMEND,
                           completeness=ProfileCompleteness.SUFFICIENT, documents=document_ids,
                           reasons=reasons)
