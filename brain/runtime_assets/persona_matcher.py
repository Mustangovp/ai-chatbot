"""Pure, shadow-only matching against the validated persona corpus."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from context_builder import ContextSnapshot

from brain.runtime_assets.personas import RuntimePersona, load_runtime_personas


PERSONA_MATCHER_VERSION = "persona-matcher-shadow-v1"
_RECOMMENDATION_INTENTS = {"workout", "nutrition"}


@dataclass(frozen=True)
class PersonaMatchResult:
    version: str
    primary_persona_id: str | None
    secondary_persona_ids: tuple[str, ...]
    matched_problem_tags: tuple[str, ...]
    matched_constraint_tags: tuple[str, ...]
    matched_goal_tags: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    confidence: float
    abstained: bool
    abstention_reason: str | None


def _value(snapshot: ContextSnapshot, key: str) -> str:
    fact = snapshot.profile.get(key)
    return str(fact.value).strip().lower() if fact else ""


def _signals(snapshot: ContextSnapshot) -> tuple[set[str], tuple[str, ...]]:
    signals: set[str] = set()
    evidence: list[str] = []
    for key in ("goal", "level", "experience_level", "equipment", "injuries", "healthNotes",
                "sleepQuality", "stressLevel", "recoveryFeel", "age", "budget"):
        value = _value(snapshot, key)
        if value:
            evidence.append(f"fact:{key}")
    level = _value(snapshot, "level") or _value(snapshot, "experience_level")
    if level in {"beginner", "intermediate", "advanced"}:
        signals.add(f"experience:{level}")
    if level == "advanced":
        signals.add("cluster:athletes_advanced")
    if level == "beginner":
        signals.add("cluster:beginners_deconditioned")
    equipment = _value(snapshot, "equipment")
    if equipment in {"home", "gym", "bodyweight"}:
        signals.add(f"equipment:{equipment}")
    goal = _value(snapshot, "goal")
    goal_map = {"strength": "strength", "muscle_gain": "muscle_gain", "fat_loss": "fat_loss",
                "endurance": "endurance"}
    if goal in goal_map:
        signals.add(f"goal:{goal_map[goal]}")
    if _value(snapshot, "injuries") or _value(snapshot, "healthNotes"):
        signals.add("problem:mentions_pain")
    if _value(snapshot, "sleepQuality") in {"poor", "bad"}:
        signals.add("problem:mentions_sleep")
    if _value(snapshot, "stressLevel") == "high":
        signals.add("problem:mentions_stress")
    if _value(snapshot, "recoveryFeel") in {"tired", "fatigued", "poor"}:
        signals.add("recovery:mentions_fatigue")
    for key, values in snapshot.locked_preferences.as_dict().items():
        if values:
            evidence.append(f"locked:{key}")
    return signals, tuple(sorted(set(evidence)))


def _score(persona: RuntimePersona, signals: set[str]) -> tuple[int, tuple[str, ...]]:
    matched: list[str] = []
    score = 0
    if f"experience:{persona.experience_level}" in signals and persona.experience_level != "unknown":
        matched.append(f"experience:{persona.experience_level}")
        score += 2
    if f"equipment:{persona.equipment_context}" in signals and persona.equipment_context != "unknown":
        matched.append(f"equipment:{persona.equipment_context}")
        score += 2
    if "cluster:athletes_advanced" in signals and "athletes_advanced" in persona.cluster:
        matched.append("cluster:athletes_advanced")
        score += 2
    if "cluster:beginners_deconditioned" in signals and "beginners_deconditioned" in persona.cluster:
        matched.append("cluster:beginners_deconditioned")
        score += 2
    matched.extend(f"problem:{tag}" for tag in persona.problem_tags if f"problem:{tag}" in signals)
    matched.extend(f"constraint:{tag}" for tag in persona.constraint_tags if f"constraint:{tag}" in signals)
    matched.extend(f"goal:{tag}" for tag in persona.goal_tags if f"goal:{tag}" in signals)
    matched.extend(f"recovery:{tag}" for tag in persona.recovery_context if f"recovery:{tag}" in signals)
    score += sum(1 for tag in matched if ":mentions_" in tag or tag.startswith("goal:"))
    return score, tuple(sorted(matched))


def match(snapshot: ContextSnapshot, intent: str, *, personas: Iterable[RuntimePersona] | None = None) -> PersonaMatchResult:
    """Return a deterministic, non-persistent archetype comparison for one request."""
    if intent not in _RECOMMENDATION_INTENTS:
        return PersonaMatchResult(PERSONA_MATCHER_VERSION, None, (), (), (), (),
                                  (f"snapshot:{snapshot.snapshot_id}",), 0.0, True,
                                  "intent is not a recommendation request")
    signals, fact_evidence = _signals(snapshot)
    if not signals:
        return PersonaMatchResult(PERSONA_MATCHER_VERSION, None, (), (), (), (),
                                  (f"snapshot:{snapshot.snapshot_id}", *fact_evidence), 0.0, True,
                                  "insufficient source-backed context")
    ranked = sorted(((score, matched, persona) for persona in (personas or load_runtime_personas())
                     for score, matched in (_score(persona, signals),)),
                    key=lambda item: (-item[0], item[2].id))
    top_score, top_matches, primary = ranked[0]
    if top_score < 2:
        return PersonaMatchResult(PERSONA_MATCHER_VERSION, None, (), (), (), (),
                                  (f"snapshot:{snapshot.snapshot_id}", *fact_evidence), 0.0, True,
                                  "no sufficiently specific source-backed match")
    peers = [persona.id for score, _, persona in ranked[1:] if score == top_score][:2]
    problems = tuple(sorted(tag.removeprefix("problem:") for tag in top_matches if tag.startswith("problem:")))
    constraints = tuple(sorted(tag.removeprefix("constraint:") for tag in top_matches if tag.startswith("constraint:")))
    goals = tuple(sorted(tag.removeprefix("goal:") for tag in top_matches if tag.startswith("goal:")))
    confidence = min(0.95, top_score / 4.0)
    return PersonaMatchResult(PERSONA_MATCHER_VERSION, primary.id, tuple(peers), problems, constraints, goals,
                              (f"snapshot:{snapshot.snapshot_id}", f"persona:{primary.id}", *fact_evidence),
                              confidence, False, None)
