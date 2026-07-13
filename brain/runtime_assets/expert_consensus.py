"""Pure, shadow-only consensus over validated expert rule packs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from context_builder import ContextSnapshot

from brain.runtime_assets.expert_rules import ExpertRule, ExpertRulePack, load_expert_rule_packs
from brain.runtime_assets.persona_matcher import PersonaMatchResult


EXPERT_CONSENSUS_VERSION = "expert-consensus-shadow-v1"
_RECOMMENDATION_INTENTS = {"workout", "nutrition"}
_PRIORITY = {"safety": 0, "high": 1, "medium": 2}


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


def _applies(rule: ExpertRule, snapshot: ContextSnapshot, match: PersonaMatchResult) -> tuple[bool, tuple[str, ...]]:
    injury = bool(_value(snapshot, "injuries") or _value(snapshot, "healthNotes"))
    level = _value(snapshot, "level") or _value(snapshot, "experience_level")
    stressed = _value(snapshot, "stressLevel") == "high" or "mentions_stress" in match.matched_problem_tags
    fatigued = _value(snapshot, "recoveryFeel") in {"tired", "fatigued", "poor"} or "mentions_sleep" in match.matched_problem_tags
    if rule.rule_id == "MCG-001":
        return injury, ("fact:injuries",) if injury else ()
    if rule.rule_id == "CLR-002":
        return level == "beginner" or "mentions_motivation" in match.matched_problem_tags, ("fact:level",)
    if rule.rule_id == "CLR-004":
        return bool(snapshot.recommendation_history), ("history:recommendations",)
    if rule.rule_id == "GRV-001":
        return stressed, ("fact:stressLevel",) if stressed else ()
    if rule.rule_id == "GRV-003":
        return stressed or fatigued, ("fact:recovery",) if (stressed or fatigued) else ()
    if rule.rule_id == "WNK-003":
        return level == "beginner" or fatigued, ("fact:level",) if level == "beginner" else ("fact:recovery",)
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
