"""Pure, shadow-only consensus over validated expert rule packs."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Iterable

from context_builder import ContextSnapshot

from brain.runtime_assets.expert_rules import ExpertRule, ExpertRulePack, load_expert_rule_packs
from brain.runtime_assets.persona_matcher import PersonaMatchResult


EXPERT_CONSENSUS_VERSION = "expert-consensus-shadow-v1"
_RECOMMENDATION_INTENTS = {"workout", "nutrition"}
_PRIORITY = {"safety": 0, "high": 1, "medium": 2}
_MOVEMENT_PATTERNS = frozenset({
    "vertical_push", "horizontal_push", "vertical_pull", "squat", "lunge", "hinge",
})
_MCG_001_EXCLUSION_AUTHORITIES = frozenset({
    "fitness_limitation", "explicit_user_restriction", "clinician_restriction",
    "shoulder_validation", "brain_enforcement",
})
_CLR_004_LAPSE_SOURCES = frozenset({
    "explicit_missed_workout", "verified_scheduled_completion_mismatch",
})
_EXPERIENCE_LEVELS = frozenset({"beginner", "intermediate", "advanced"})
_CANONICAL_EXPERIENCE_SOURCES = frozenset({"db_profile", "browser", "explicit", "locked"})
_HIGHER_AUTHORITY_MOVEMENT_KEYS = frozenset({
    "clinicianRestrictions", "medicalRestrictions", "healthRestrictions", "trainingRestrictions",
})


@dataclass(frozen=True)
class ExpertConsensusResult:
    version: str
    applicable_rule_ids: tuple[str, ...]
    rejected_rule_ids: tuple[str, ...]
    unresolved_rule_ids: tuple[str, ...]
    conflict_groups: tuple[str, ...]
    resolution_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    confidence: float
    abstained: bool


def _value(snapshot: ContextSnapshot, key: str) -> str:
    fact = snapshot.profile.get(key)
    return str(fact.value).strip().lower() if fact else ""


def _safety_override(snapshot: ContextSnapshot) -> bool:
    if snapshot.intent == "medical":
        return True
    return any(str(snapshot.profile.get(key).value).strip().lower() in {"1", "true", "yes"}
               for key in ("red_flag", "urgent_medical") if key in snapshot.profile)


def _explicit_mapping(snapshot: ContextSnapshot, key: str) -> Mapping[str, object] | None:
    """Return only an already-typed explicit fact, never free text or state inference."""
    fact = snapshot.profile.get(key)
    if fact is None or fact.source != "explicit" or not isinstance(fact.value, Mapping):
        return None
    return fact.value


def _mcg_001_evidence(snapshot: ContextSnapshot) -> tuple[str, ...]:
    """Validate a provenance chain for wording about an existing movement exclusion.

    This is deliberately not a restriction producer.  A higher-authority system
    must have already created both the typed symptom-motion link and the exact
    exclusion.  Missing, free-text, or mismatched evidence fails closed.
    """
    evidence = _explicit_mapping(snapshot, "mcg_001_provenance")
    expected = {
        "version", "evidence_source", "symptom_state", "provoking_movement_pattern",
        "excluded_movement_pattern", "exclusion_authority",
    }
    if evidence is None or set(evidence) != expected:
        return ()
    provoking = evidence.get("provoking_movement_pattern")
    excluded = evidence.get("excluded_movement_pattern")
    if (evidence.get("version") != "mcg-001-provenance-v1"
            or evidence.get("evidence_source") != "typed_fitness_limitation"
            or evidence.get("symptom_state") not in {"active", "recovering"}
            or not isinstance(provoking, str)
            or provoking not in _MOVEMENT_PATTERNS
            or excluded != provoking
            or evidence.get("exclusion_authority") not in _MCG_001_EXCLUSION_AUTHORITIES):
        return ()
    return ("fact:mcg_001_provenance",)


def _clr_004_evidence(snapshot: ContextSnapshot) -> tuple[str, ...]:
    """Validate an explicit lapse event; history alone is never lapse evidence."""
    evidence = _explicit_mapping(snapshot, "clr_004_lapse")
    expected = {"version", "evidence_source", "lapse_state"}
    if evidence is None or set(evidence) != expected:
        return ()
    if (evidence.get("version") != "clr-004-lapse-v1"
            or evidence.get("evidence_source") not in _CLR_004_LAPSE_SOURCES
            or evidence.get("lapse_state") not in {"missed", "gap"}):
        return ()
    return ("fact:clr_004_lapse",)


def _canonical_experience_level(snapshot: ContextSnapshot) -> str | None:
    """Read only the verified profile's canonical experience field.

    Persona labels, HSE state, history, and language analysis never participate.
    Conflicting duplicate fields, malformed values, and unsupported sources abstain.
    """
    values = []
    for key in ("level", "experience_level"):
        fact = snapshot.profile.get(key)
        if fact is None:
            continue
        if fact.source not in _CANONICAL_EXPERIENCE_SOURCES or not isinstance(fact.value, str):
            return None
        value = fact.value.strip().lower()
        if value not in _EXPERIENCE_LEVELS:
            return None
        values.append(value)
    if not values or len(set(values)) != 1:
        return None
    return values[0]


def _higher_authority_movement_instruction(snapshot: ContextSnapshot) -> bool:
    """Conservatively yield when a restriction owns movement instruction."""
    return any(_value(snapshot, key) for key in _HIGHER_AUTHORITY_MOVEMENT_KEYS)


def _applies(rule: ExpertRule, snapshot: ContextSnapshot, match: PersonaMatchResult) -> tuple[bool, tuple[str, ...]]:
    level = _value(snapshot, "level") or _value(snapshot, "experience_level")
    stressed = _value(snapshot, "stressLevel") == "high" or "mentions_stress" in match.matched_problem_tags
    fatigued = _value(snapshot, "recoveryFeel") in {"tired", "fatigued", "poor"} or "mentions_sleep" in match.matched_problem_tags
    if rule.rule_id == "MCG-001":
        refs = _mcg_001_evidence(snapshot)
        return bool(refs), refs
    if rule.rule_id == "CLR-002":
        return level == "beginner" or "mentions_motivation" in match.matched_problem_tags, ("fact:level",)
    if rule.rule_id == "CLR-004":
        refs = _clr_004_evidence(snapshot)
        return bool(refs), refs
    if rule.rule_id == "GRV-001":
        return stressed, ("fact:stressLevel",) if stressed else ()
    if rule.rule_id == "GRV-003":
        return stressed or fatigued, ("fact:recovery",) if (stressed or fatigued) else ()
    if rule.rule_id == "WNK-003":
        return level == "beginner" or fatigued, ("fact:level",) if level == "beginner" else ("fact:recovery",)
    if rule.rule_id == "WNK-011":
        experience = _canonical_experience_level(snapshot)
        if experience is None or _higher_authority_movement_instruction(snapshot):
            return False, ()
        return True, ("fact:experience_level",)
    return False, ()


def evaluate(snapshot: ContextSnapshot, match: PersonaMatchResult, intent: str,
             *, packs: Iterable[ExpertRulePack] | None = None) -> ExpertConsensusResult:
    """Evaluate only resolved, ready rules; this result never affects delivery."""
    rules = tuple(rule for pack in (packs or load_expert_rule_packs()) for rule in pack.rules)
    unresolved = tuple(sorted(rule.rule_id for rule in rules if not rule.runtime_ready))
    evidence = {f"snapshot:{snapshot.snapshot_id}", *match.evidence_refs}
    if intent not in _RECOMMENDATION_INTENTS or _safety_override(snapshot):
        rejected = tuple(sorted(rule.rule_id for rule in rules if rule.runtime_ready))
        return ExpertConsensusResult(EXPERT_CONSENSUS_VERSION, (), rejected, unresolved, (),
                                    ("safety or intent prevents expert evaluation",), tuple(sorted(evidence)),
                                    0.0, True)
    eligible = []
    rejected = []
    for rule in rules:
        if not rule.runtime_ready:
            continue
        if intent == "nutrition" and rule.domain != "nutrition":
            rejected.append(rule.rule_id)
            continue
        if intent == "workout" and rule.domain == "nutrition":
            rejected.append(rule.rule_id)
            continue
        applies, refs = _applies(rule, snapshot, match)
        if applies:
            eligible.append((rule, refs))
        else:
            rejected.append(rule.rule_id)
    selected = []
    conflicts = []
    reasons = []
    for group in sorted({rule.conflict_group for rule, _ in eligible}):
        candidates = sorted(((rule, refs) for rule, refs in eligible if rule.conflict_group == group),
                            key=lambda item: (_PRIORITY[item[0].priority], item[0].rule_id))
        winner, refs = candidates[0]
        selected.append(winner)
        evidence.update(refs)
        reasons.append(f"{winner.rule_id}:source conditions matched")
        if len(candidates) > 1:
            conflicts.append(group)
            rejected.extend(rule.rule_id for rule, _ in candidates[1:])
            reasons.append(f"{group}:priority then rule ID tie-break")
    applicable = tuple(sorted(rule.rule_id for rule in selected))
    return ExpertConsensusResult(EXPERT_CONSENSUS_VERSION, applicable, tuple(sorted(set(rejected))), unresolved,
                                tuple(sorted(conflicts)), tuple(reasons), tuple(sorted(evidence)),
                                min(0.95, len(applicable) / 3.0) if applicable else 0.0, not bool(applicable))
