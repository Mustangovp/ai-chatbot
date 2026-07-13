"""Pure, deterministic ContextSnapshot construction for APEX Phase A1.

This module has no runtime wiring yet. Callers provide already-read source data;
the builder performs no I/O and never calls OpenAI, Brain, Recommendation, or UI
code. It is intentionally safe to test in isolation before `/chat` adopts it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping


SCHEMA_VERSION = "context-snapshot-v1"

_AUTHORITY = {
    "explicit": 100,
    "locked": 100,
    "db_profile": 90,
    "db_history": 89,
    "recommendation_preferences": 85,
    "recommendation_history": 85,
    "human_state": 80,
    "athlete_model": 70,
    "human_learning": 60,
    "browser": 50,
}
_CONFIDENCE = {
    "explicit": 1.00,
    "locked": 1.00,
    "db_profile": 1.00,
    "db_history": 0.99,
    "recommendation_preferences": 0.95,
    "recommendation_history": 0.95,
    "human_learning": 0.80,
    "athlete_model": 0.70,
    "browser": 0.40,
    "human_state": 0.80,
}
_INTENTS = {
    "workout", "nutrition", "recovery", "progress", "question", "motivation",
    "general_conversation", "medical", "account", "unknown",
}
_PROFILE_FIELDS = (
    "goal", "equipment", "level", "experience_level", "frequency",
    "training_availability", "sleepQuality", "stressLevel", "recoveryFeel",
    "injuries", "healthNotes", "allergies", "age", "activityLevel",
)


def _utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze(v) for v in value)
    return value


def _legacy_freeze(value: Any) -> Any:
    """Freeze a legacy prompt value without canonical reordering."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _legacy_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_legacy_freeze(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_legacy_freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(_legacy_freeze(v) for v in value)
    return value


def _thaw_legacy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw_legacy(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw_legacy(v) for v in value]
    if isinstance(value, frozenset):
        return [_thaw_legacy(v) for v in sorted(value, key=str)]
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, frozenset)):
        return [_plain(v) for v in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def _canonical(value: Any) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


@dataclass(frozen=True)
class Subject:
    kind: str
    identifier: str
    authenticated: bool

    def __post_init__(self):
        if self.kind not in ("account", "anonymous_device"):
            raise ValueError("subject kind must be account or anonymous_device")
        if not self.identifier:
            raise ValueError("subject identifier is required")
        if self.authenticated != (self.kind == "account"):
            raise ValueError("subject authentication must match subject kind")


@dataclass(frozen=True)
class VerifiedFact:
    key: str
    value: Any
    source: str
    authority: int
    confidence: float
    observed_at: datetime | None = None
    expires_at: datetime | None = None
    redaction_class: str = "coaching"

    def __post_init__(self):
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        object.__setattr__(self, "value", _freeze(self.value))
        object.__setattr__(self, "observed_at", _utc(self.observed_at))
        object.__setattr__(self, "expires_at", _utc(self.expires_at))

    def is_fresh(self, now: datetime) -> bool:
        return self.expires_at is None or self.expires_at >= now

    def metadata(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "source": self.source,
            "authority": self.authority,
            "confidence": self.confidence,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "redaction_class": self.redaction_class,
        })


@dataclass(frozen=True)
class LockedPreferences:
    dietary: tuple[str, ...] = ()
    allergies: tuple[str, ...] = ()
    religious: tuple[str, ...] = ()
    permanent_injuries: tuple[str, ...] = ()
    accessibility: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    exercise_exclusions: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("dietary", "allergies", "religious", "permanent_injuries", "accessibility",
                     "equipment", "exercise_exclusions"):
            values = tuple(sorted({str(v).strip() for v in getattr(self, name) if str(v).strip()}))
            object.__setattr__(self, name, values)

    def as_dict(self) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType({
            "dietary": self.dietary,
            "allergies": self.allergies,
            "religious": self.religious,
            "permanent_injuries": self.permanent_injuries,
            "accessibility": self.accessibility,
            "equipment": self.equipment,
            "exercise_exclusions": self.exercise_exclusions,
        })


@dataclass(frozen=True)
class LegacyPromptProjection:
    """Temporary adapter reproducing the current `/chat` prompt variables exactly."""
    profile: Mapping[str, Any]
    workouts: tuple[Mapping[str, Any], ...]
    conversation: tuple[Mapping[str, Any], ...]

    def prompt_variables(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "profile": _thaw_legacy(self.profile),
            "workouts": _thaw_legacy(self.workouts),
            "history": _thaw_legacy(self.conversation),
        })


@dataclass(frozen=True)
class ContextSnapshot:
    snapshot_id: str
    schema_version: str
    created_at_utc: datetime
    subject: Subject
    intent: str
    intent_confidence: float
    access: Mapping[str, Any]
    profile: Mapping[str, VerifiedFact]
    locked_preferences: LockedPreferences
    preferences: Mapping[str, VerifiedFact]
    workouts: tuple[Mapping[str, Any], ...]
    nutrition: tuple[Mapping[str, Any], ...]
    conversation: tuple[Mapping[str, Any], ...]
    coach_events: tuple[Mapping[str, Any], ...]
    recommendation_history: tuple[Mapping[str, Any], ...]
    current_state: Mapping[str, VerifiedFact]
    provenance: Mapping[str, Mapping[str, Any]]
    omissions: tuple[str, ...]
    legacy_prompt_data: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        if self.intent not in _INTENTS:
            raise ValueError("unsupported intent")
        if not 0.0 <= float(self.intent_confidence) <= 1.0:
            raise ValueError("intent confidence must be between 0.0 and 1.0")
        object.__setattr__(self, "created_at_utc", _utc(self.created_at_utc) or datetime.now(timezone.utc))
        object.__setattr__(self, "access", _freeze(self.access))
        object.__setattr__(self, "profile", _freeze(self.profile))
        object.__setattr__(self, "preferences", _freeze(self.preferences))
        object.__setattr__(self, "workouts", tuple(_freeze(v) for v in self.workouts))
        object.__setattr__(self, "nutrition", tuple(_freeze(v) for v in self.nutrition))
        object.__setattr__(self, "conversation", tuple(_freeze(v) for v in self.conversation))
        object.__setattr__(self, "coach_events", tuple(_freeze(v) for v in self.coach_events))
        object.__setattr__(self, "recommendation_history", tuple(_freeze(v) for v in self.recommendation_history))
        object.__setattr__(self, "current_state", _freeze(self.current_state))
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        object.__setattr__(self, "omissions", tuple(sorted(set(self.omissions))) )
        object.__setattr__(self, "legacy_prompt_data", _legacy_freeze(self.legacy_prompt_data))

    def semantic_payload(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "schema_version": self.schema_version,
            "created_at_utc": self.created_at_utc.isoformat(),
            "subject": {"kind": self.subject.kind, "authenticated": self.subject.authenticated},
            "intent": self.intent,
            "intent_confidence": self.intent_confidence,
            "access": self.access,
            "profile": {k: {"value": v.value, **v.metadata()} for k, v in self.profile.items()},
            "locked_preferences": self.locked_preferences.as_dict(),
            "preferences": {k: {"value": v.value, **v.metadata()} for k, v in self.preferences.items()},
            "workouts": self.workouts,
            "nutrition": self.nutrition,
            "conversation": self.conversation,
            "coach_events": self.coach_events,
            "recommendation_history": self.recommendation_history,
            "current_state": {k: {"value": v.value, **v.metadata()} for k, v in self.current_state.items()},
            "provenance": self.provenance,
            "omissions": self.omissions,
        })

    def llm_projection(self) -> Mapping[str, Any]:
        """Minimized presentation-safe context; excludes internal IDs and access internals."""
        profile = {k: v.value for k, v in self.profile.items() if v.redaction_class == "coaching"}
        state = {k: v.value for k, v in self.current_state.items() if v.redaction_class == "coaching"}
        payload = {
            "intent": self.intent,
            "profile": profile,
            "locked_preferences": self.locked_preferences.as_dict(),
            "preferences": {k: v.value for k, v in self.preferences.items()},
            "workouts": self.workouts,
            "nutrition": self.nutrition,
            "conversation": self.conversation,
            "current_state": state,
            "omissions": self.omissions,
        }
        return _freeze(payload)

    def redacted_metadata(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "schema_version": self.schema_version,
            "intent": self.intent,
            "intent_confidence": self.intent_confidence,
            "subject_kind": self.subject.kind,
            "profile_fields": tuple(sorted(self.profile)),
            "preference_fields": tuple(sorted(self.preferences)),
            "current_state_fields": tuple(sorted(self.current_state)),
            "workout_count": len(self.workouts),
            "nutrition_count": len(self.nutrition),
            "conversation_count": len(self.conversation),
            "omissions": self.omissions,
            "provenance": self.provenance,
        })

    def legacy_prompt_projection(self, *, conversation_limit: int) -> LegacyPromptProjection:
        """Return exact legacy prompt variables without changing canonical semantics.

        The projection is intentionally isolated from `semantic_payload()`: canonical
        ordering remains deterministic, while this adapter preserves the chronological
        order and raw values that existing `/chat` prompt assembly expects.
        """
        if conversation_limit < 0:
            raise ValueError("conversation_limit must be non-negative")
        data = self.legacy_prompt_data
        conversation = tuple(data.get("conversation", ()))
        if conversation_limit:
            conversation = conversation[-conversation_limit:]
        else:
            conversation = ()
        return LegacyPromptProjection(
            profile=data.get("profile", MappingProxyType({})),
            workouts=tuple(data.get("workouts", ())),
            conversation=conversation,
        )


def _as_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(v.strip() for v in value.split(",") if v.strip())
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _locked(profile: Mapping[str, Any], supplied: LockedPreferences | Mapping[str, Any] | None) -> LockedPreferences:
    if isinstance(supplied, LockedPreferences):
        return supplied
    supplied = supplied or {}
    food = _as_values(profile.get("foodPreference") or profile.get("foodPreferences"))
    dietary = tuple(v for v in food if v.lower() in {"vegetarian", "vegan", "gluten_free", "gluten-free"})
    return LockedPreferences(
        dietary=tuple(supplied.get("dietary", dietary)),
        allergies=tuple(supplied.get("allergies", _as_values(profile.get("allergies")))),
        religious=tuple(supplied.get("religious", _as_values(profile.get("religiousRestrictions")))),
        permanent_injuries=tuple(supplied.get("permanent_injuries", _as_values(profile.get("permanentInjuries")))),
        accessibility=tuple(supplied.get("accessibility", _as_values(profile.get("accessibilityNeeds")))),
        equipment=tuple(supplied.get("equipment", _as_values(profile.get("lockedEquipment")))),
        exercise_exclusions=tuple(supplied.get("exercise_exclusions",
                                                _as_values(profile.get("lockedExerciseExclusions")))),
    )


def _record_sort(records: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(records, (list, tuple)):
        return ()
    clean = [dict(r) for r in records if isinstance(r, Mapping)]
    return tuple(_freeze(r) for r in sorted(clean, key=lambda r: _canonical(r)))


def _fact(key: str, value: Any, source: str, *, observed_at=None, expires_at=None, confidence=None,
          redaction_class="coaching") -> VerifiedFact:
    return VerifiedFact(key=key, value=value, source=source, authority=_AUTHORITY[source],
                        confidence=_CONFIDENCE[source] if confidence is None else confidence,
                        observed_at=observed_at, expires_at=expires_at, redaction_class=redaction_class)


def _fresh_state(raw: Mapping[str, Any] | None, now: datetime, source: str) -> dict[str, VerifiedFact]:
    out = {}
    for key, item in sorted((raw or {}).items()):
        if not isinstance(item, Mapping):
            continue
        observed = _utc(item.get("observed_at")) or now
        ttl = item.get("ttl_seconds")
        expires = _utc(item.get("expires_at"))
        if expires is None and ttl is not None:
            expires = observed + timedelta(seconds=int(ttl))
        fact = _fact(key, item.get("value"), source, observed_at=observed, expires_at=expires,
                     confidence=float(item.get("confidence", _CONFIDENCE[source])))
        if fact.is_fresh(now):
            out[key] = fact
    return out


def _choose(existing: VerifiedFact | None, candidate: VerifiedFact) -> VerifiedFact:
    if existing is None:
        return candidate
    if candidate.authority != existing.authority:
        return candidate if candidate.authority > existing.authority else existing
    if candidate.observed_at != existing.observed_at:
        return candidate if (candidate.observed_at or datetime.min.replace(tzinfo=timezone.utc)) > (existing.observed_at or datetime.min.replace(tzinfo=timezone.utc)) else existing
    return candidate if candidate.confidence > existing.confidence else existing


def build_context(*, intent: str, subject: Subject, request_time: datetime,
                  access: Mapping[str, Any] | None = None,
                  db_profile: Mapping[str, Any] | None = None,
                  browser_profile: Mapping[str, Any] | None = None,
                  explicit_facts: Mapping[str, Any] | None = None,
                  human_learning: Mapping[str, Any] | None = None,
                  human_state: Mapping[str, Any] | None = None,
                  athlete_projection: Mapping[str, Any] | None = None,
                  locked_preferences: LockedPreferences | Mapping[str, Any] | None = None,
                  db_conversation: Any = None, browser_conversation: Any = None,
                  db_workouts: Any = None, client_workout_context: Any = None,
                  db_nutrition: Any = None, coach_memory: Any = None,
                  recommendation_preferences: Mapping[str, Any] | None = None,
                  recommendation_history: Any = None,
                  legacy_profile: Mapping[str, Any] | None = None,
                  legacy_conversation: Any = None,
                  legacy_workouts: Any = None,
                  intent_confidence: float = 1.0) -> ContextSnapshot:
    """Build one immutable snapshot from injected sources without side effects."""
    if intent not in _INTENTS:
        intent = "unknown"
    now = _utc(request_time)
    if now is None:
        raise ValueError("request_time must be timezone-aware or ISO UTC-compatible")

    authoritative_profile = dict(db_profile or {}) if subject.authenticated else dict(browser_profile or {})
    profile_source = "db_profile" if subject.authenticated else "browser"
    facts: dict[str, VerifiedFact] = {}
    for key in _PROFILE_FIELDS:
        if authoritative_profile.get(key) not in (None, "", [], {}):
            facts[key] = _fact(key, authoritative_profile[key], profile_source, observed_at=now)
    for key, value in sorted((human_learning or {}).items()):
        if value not in (None, "", [], {}) and key not in facts:
            facts[key] = _fact(key, value, "human_learning", observed_at=now)
    for key, value in sorted((explicit_facts or {}).items()):
        if value not in (None, "", [], {}):
            facts[key] = _choose(facts.get(key), _fact(key, value, "explicit", observed_at=now))

    locked = _locked(authoritative_profile, locked_preferences)
    if locked.permanent_injuries:
        facts["injuries"] = _fact("injuries", locked.permanent_injuries, "locked", observed_at=now)
    if locked.allergies:
        facts["allergies"] = _fact("allergies", locked.allergies, "locked", observed_at=now)

    preferences = {
        key: _fact(key, value, "recommendation_preferences", observed_at=now)
        for key, value in sorted((recommendation_preferences or {}).items())
        if value not in (None, "", [], {})
    }

    state = _fresh_state(human_state, now, "human_state")
    athlete = _fresh_state(athlete_projection, now, "athlete_model")
    for key, candidate in athlete.items():
        state[key] = _choose(state.get(key), candidate)
    for state_key, profile_key in (("sleep", "sleepQuality"), ("stress", "stressLevel"), ("recovery", "recoveryFeel")):
        if state_key in state:
            # Fresh state is deliberately allowed to supersede a durable baseline
            # for this request only; it never writes back to the profile.
            facts[profile_key] = state[state_key]

    conversation = _record_sort(db_conversation if subject.authenticated else browser_conversation)
    workouts = _record_sort(db_workouts if subject.authenticated else client_workout_context)
    nutrition = _record_sort(db_nutrition)
    timeline = _record_sort(coach_memory)
    rotation = _record_sort(recommendation_history)

    # This adapter data is deliberately separate from canonical source ordering.
    # It preserves the values and chronological sequences already consumed by
    # legacy `/chat`; A2 will map it back into the old prompt variables unchanged.
    if legacy_profile is None:
        if subject.authenticated:
            legacy_profile = db_profile if db_profile else browser_profile
        else:
            legacy_profile = browser_profile
    if legacy_conversation is None:
        legacy_conversation = db_conversation if subject.authenticated else browser_conversation
    if legacy_workouts is None:
        legacy_workouts = db_workouts if subject.authenticated else ()
    legacy_data = {
        "profile": dict(legacy_profile or {}),
        "conversation": tuple(dict(v) for v in (legacy_conversation or ()) if isinstance(v, Mapping)),
        "workouts": tuple(dict(v) for v in (legacy_workouts or ()) if isinstance(v, Mapping)),
    }

    # Intent minimization is applied before immutable snapshot creation.
    if intent == "workout":
        nutrition = ()
        preferences = {}
    elif intent == "nutrition":
        workouts = ()
    elif intent == "account":
        facts, preferences, state, conversation, workouts, nutrition, timeline, rotation = {}, {}, {}, (), (), (), (), ()
    elif intent == "general_conversation":
        conversation, workouts, nutrition, timeline, rotation, state = conversation[-2:], (), (), (), (), {}
    elif intent == "medical":
        keep = {"injuries", "healthNotes", "allergies", "age", "goal"}
        facts = {k: v for k, v in facts.items() if k in keep}
        preferences, workouts, nutrition, timeline, rotation = {}, (), (), (), ()

    omissions = []
    required = {
        "workout": ("goal", "equipment", "level"),
        "nutrition": ("goal",),
        "recovery": (),
        "progress": ("goal",),
    }.get(intent, ())
    for key in required:
        if key not in facts:
            omissions.append(f"missing:{key}")
    if not subject.authenticated and not browser_profile:
        omissions.append("missing:anonymous_profile")
    if subject.authenticated and not db_profile:
        omissions.append("missing:account_profile")

    provenance = {key: fact.metadata() for key, fact in sorted(facts.items())}
    provenance.update({f"state:{key}": fact.metadata() for key, fact in sorted(state.items())})
    source_hash = sha256(_canonical({
        "subject": {"kind": subject.kind, "id": subject.identifier}, "intent": intent,
        "facts": {k: {"value": v.value, **v.metadata()} for k, v in facts.items()},
        "preferences": {k: {"value": v.value, **v.metadata()} for k, v in preferences.items()},
        "state": {k: {"value": v.value, **v.metadata()} for k, v in state.items()},
        "workouts": workouts, "nutrition": nutrition, "conversation": conversation,
        "timeline": timeline, "rotation": rotation,
        "locked": locked.as_dict(), "access": {"plan": (access or {}).get("plan")},
    }).encode("utf-8")).hexdigest()
    snapshot_id = f"ctx_{source_hash[:24]}"

    return ContextSnapshot(
        snapshot_id=snapshot_id, schema_version=SCHEMA_VERSION, created_at_utc=now,
        subject=subject, intent=intent, intent_confidence=float(intent_confidence),
        access={"plan": (access or {}).get("plan"), "quota_status": (access or {}).get("quota_status")},
        profile=facts, locked_preferences=locked, preferences=preferences,
        workouts=workouts, nutrition=nutrition, conversation=conversation,
        coach_events=timeline, recommendation_history=rotation,
        current_state=state, provenance=provenance, omissions=tuple(omissions),
        legacy_prompt_data=legacy_data,
    )
