"""Versioned, source-traceable expert rule packs; intentionally not runtime-wired."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EXPERT_RULE_PACK_VERSION = "expert-rule-packs-v1"
_ROOT = Path(__file__).resolve().parents[2]
_PRIORITIES = {"safety", "high", "medium"}
_LINEAGES = ("Galpin", "Helms", "McGill", "Aragon", "Clear", "Gervais", "Winkelman")


@dataclass(frozen=True)
class ExpertRule:
    rule_id: str
    lineage: str
    domain: str
    rule_text: str
    applicability_conditions: tuple[str, ...]
    contraindications: tuple[str, ...]
    priority: str
    conflict_group: str
    evidence_reference: str
    source_document: str
    source_section: str
    version: str
    runtime_ready: bool


@dataclass(frozen=True)
class ExpertRulePack:
    lineage: str
    version: str
    rules: tuple[ExpertRule, ...]


def _rule(rule_id, lineage, domain, rule_text, conditions, contraindications, priority,
          conflict_group, evidence_reference, source_document, source_section):
    return ExpertRule(rule_id, lineage, domain, rule_text, tuple(conditions), tuple(contraindications),
                      priority, conflict_group, evidence_reference, source_document, source_section,
                      EXPERT_RULE_PACK_VERSION, "unresolved" not in conditions and "unresolved" not in contraindications)


_DOMAIN = "docs/research/sprint-002/"
_PACKS = (
    ExpertRulePack("Galpin", EXPERT_RULE_PACK_VERSION, (
        _rule("GLP-001", "Galpin", "performance_science", "Name the adaptation before prescribing anything.",
              ("open-ended programming request",), ("unresolved",), "medium", "goal_definition", "KC-GLP-001",
              _DOMAIN + "domain-1-performance-science.md", "6. Knowledge & Decision Cards / KC-GLP-001"),
        _rule("GLP-063", "Galpin", "performance_science", "Recoverable load, not planned load, is the ceiling; recovery gates progression.",
              ("elevated fatigue, stress, or sleep debt",), ("unresolved",), "high", "recovery_vs_progression", "KC-GLP-063",
              _DOMAIN + "domain-1-performance-science.md", "6. Knowledge & Decision Cards / KC-GLP-063"),
    )),
    ExpertRulePack("Helms", EXPERT_RULE_PACK_VERSION, (
        _rule("HLM-001", "Helms", "programming", "Adherence multiplies every other variable, so it is diagnosed and fixed first.",
              ("sub-target completion",), ("unresolved",), "high", "adherence_vs_optimization", "KC-HLM-001",
              _DOMAIN + "domain-2-programming-intelligence.md", "6. Knowledge & Decision Cards / KC-HLM-001"),
        _rule("HLM-012", "Helms", "programming", "Start low, add only when progress stops.",
              ("minimum effective dose decision",), ("unresolved",), "medium", "dose_progression", "KC-HLM-012",
              _DOMAIN + "domain-2-programming-intelligence.md", "6. Knowledge & Decision Cards / KC-HLM-012"),
    )),
    ExpertRulePack("McGill", EXPERT_RULE_PACK_VERSION, (
        _rule("MCG-001", "McGill", "movement_safety", "Remove the specific pain-triggering motion or posture before strengthening.",
              ("symptomatic or recently injured trainee",), ("asymptomatic well-tolerated pattern",), "safety", "pain_vs_progression", "KC-MCG-001",
              _DOMAIN + "domain-3-movement-safety.md", "6. Knowledge & Decision Cards / KC-MCG-001"),
        _rule("MCG-010", "McGill", "movement_safety", "If red flags are present, stop training and refer to medical.",
              ("red-flag symptom set",), ("unresolved",), "safety", "safety_route", "KC-MCG-010",
              _DOMAIN + "domain-3-movement-safety.md", "6. Knowledge & Decision Cards / KC-MCG-010"),
    )),
    ExpertRulePack("Aragon", EXPERT_RULE_PACK_VERSION, (
        _rule("ARG-001", "Aragon", "nutrition", "Anchor body-composition plans to total energy before macro or timing detail.",
              ("fat-loss or gain goal",), ("unresolved",), "high", "nutrition_hierarchy", "KC-ARG-001",
              _DOMAIN + "domain-4-nutrition-intelligence.md", "6. Knowledge & Decision Cards / KC-ARG-001"),
        _rule("ARG-009", "Aragon", "nutrition", "Design around what the person will eat.",
              ("individual preference or culture is known",), ("unresolved",), "high", "nutrition_adherence", "KC-ARG-009",
              _DOMAIN + "domain-4-nutrition-intelligence.md", "6. Knowledge & Decision Cards / KC-ARG-009"),
    )),
    ExpertRulePack("Clear", EXPERT_RULE_PACK_VERSION, (
        _rule("CLR-002", "Clear", "behavior_change", "Reduce an ambitious plan to a trivially small starting version.",
              ("low motivation, new habits, or overwhelmed client",), ("already-consistent capable trainee",), "medium", "habit_dose", "KC-CLR-002",
              _DOMAIN + "domain-5-behavior-change.md", "6. Knowledge & Decision Cards / KC-CLR-002"),
        _rule("CLR-004", "Clear", "behavior_change", "Restart at the next occurrence; never miss twice.",
              ("adherence dip or guilt-driven dropout",), ("repeated missed behavior",), "medium", "lapse_response", "KC-CLR-004",
              _DOMAIN + "domain-5-behavior-change.md", "6. Knowledge & Decision Cards / KC-CLR-004"),
    )),
    ExpertRulePack("Gervais", EXPERT_RULE_PACK_VERSION, (
        _rule("GRV-001", "Gervais", "performance_psychology", "Redirect attention to the controllable next action.",
              ("pressure, plateau, outcome fixation, or comparison",), ("competition where outcome data informs strategy",), "medium", "outcome_vs_process", "KC-GRV-001",
              _DOMAIN + "domain-6-performance-psychology.md", "6. Knowledge & Decision Cards / KC-GRV-001"),
        _rule("GRV-003", "Gervais", "performance_psychology", "Regulate arousal before demanding technique.",
              ("high-pressure or high-arousal performance or learning",), ("low-arousal calm state",), "high", "regulation_before_instruction", "KC-GRV-003",
              _DOMAIN + "domain-6-performance-psychology.md", "6. Knowledge & Decision Cards / KC-GRV-003"),
    )),
    ExpertRulePack("Winkelman", EXPERT_RULE_PACK_VERSION, (
        _rule("WNK-003", "Winkelman", "coaching_communication", "Deliver one short cue rather than stacking instructions.",
              ("coaching, especially novices or fatigue",), ("immediate safety correction",), "medium", "cue_complexity", "KC-WNK-003",
              _DOMAIN + "domain-7-coaching-communication.md", "6. Knowledge & Decision Cards / KC-WNK-003"),
        _rule("WNK-011", "Winkelman", "coaching_communication", "Scale cue complexity to experience.",
              ("novice-to-expert communication",), ("unresolved",), "medium", "cue_complexity", "KC-WNK-011",
              _DOMAIN + "domain-7-coaching-communication.md", "6. Knowledge & Decision Cards / KC-WNK-011"),
    )),
)


def validate_expert_rule_packs(packs: tuple[ExpertRulePack, ...]) -> None:
    if len(packs) != 7 or tuple(pack.lineage for pack in packs) != _LINEAGES:
        raise ValueError("exactly seven ordered expert lineage packs are required")
    ids = set()
    for pack in packs:
        if pack.version != EXPERT_RULE_PACK_VERSION or not pack.rules:
            raise ValueError(f"invalid pack: {pack.lineage}")
        for rule in pack.rules:
            if rule.lineage != pack.lineage or rule.version != EXPERT_RULE_PACK_VERSION:
                raise ValueError(f"orphan rule: {rule.rule_id}")
            if not rule.rule_id or rule.rule_id in ids:
                raise ValueError(f"duplicate rule ID: {rule.rule_id}")
            ids.add(rule.rule_id)
            if rule.priority not in _PRIORITIES or not rule.evidence_reference:
                raise ValueError(f"invalid rule metadata: {rule.rule_id}")
            document = _ROOT / rule.source_document
            text = document.read_text(encoding="utf-8") if document.is_file() else ""
            if (not text or rule.source_section.split(" / ")[0] not in text
                    or rule.evidence_reference not in text):
                raise ValueError(f"missing source reference: {rule.rule_id}")
            unresolved = "unresolved" in rule.applicability_conditions or "unresolved" in rule.contraindications
            if unresolved and rule.runtime_ready:
                raise ValueError(f"unresolved rule cannot be runtime-ready: {rule.rule_id}")
            if not unresolved and not rule.runtime_ready:
                raise ValueError(f"resolved rule must state runtime readiness: {rule.rule_id}")


def load_expert_rule_packs() -> tuple[ExpertRulePack, ...]:
    """Load and validate source-traceable rule packs without activating them."""
    validate_expert_rule_packs(_PACKS)
    return _PACKS
