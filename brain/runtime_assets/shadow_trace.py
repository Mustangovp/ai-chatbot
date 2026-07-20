"""Request-local, PII-minimized observability for persona and expert evaluation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from brain.runtime_assets.expert_consensus import ExpertConsensusResult
from brain.runtime_assets.persona_matcher import PersonaMatchResult


SHADOW_TRACE_VERSION = "shadow-trace-v1"
_SAFE_EVIDENCE_PREFIXES = ("fact:", "locked:", "history:")
# Runtime delivery labels are intentionally closed: every producer below is a
# named execution path, and an unrecognized path must fail before trace output.
SUPPORTED_PRODUCTION_PATHS = frozenset({
    "legacy",
    "persona_expert",
    "deterministic_training",
})


@dataclass(frozen=True)
class ShadowTrace:
    request_id: str
    timestamp_utc: str
    persona_version: str | None
    matched_persona_ids: tuple[str, ...]
    persona_confidence: float | None
    evidence_tags: tuple[str, ...]
    abstention_reason: str | None
    expert_version: str | None
    applied_rule_ids: tuple[str, ...]
    rejected_rule_ids: tuple[str, ...]
    unresolved_rule_ids: tuple[str, ...]
    conflict_groups: tuple[str, ...]
    consensus_confidence: float | None
    matcher_ms: float | None
    consensus_ms: float | None
    blueprint_invoked: bool
    recommendation_engine_active: bool
    production_path_used: str

    def with_delivery(self, *, blueprint_invoked: bool, production_path_used: str) -> "ShadowTrace":
        if production_path_used not in SUPPORTED_PRODUCTION_PATHS:
            raise ValueError("invalid production path")
        return replace(self, blueprint_invoked=bool(blueprint_invoked),
                       production_path_used=production_path_used)


def _safe_evidence_tags(*results: PersonaMatchResult | ExpertConsensusResult | None) -> tuple[str, ...]:
    return tuple(sorted({
        ref for result in results if result is not None for ref in result.evidence_refs
        if ref.startswith(_SAFE_EVIDENCE_PREFIXES)
    }))


def build_shadow_trace(*, request_id: str, timestamp: datetime,
                       persona_match: PersonaMatchResult | None,
                       expert_consensus: ExpertConsensusResult | None,
                       matcher_ms: float | None, consensus_ms: float | None,
                       recommendation_engine_active: bool) -> ShadowTrace:
    persona_ids = ()
    if persona_match and persona_match.primary_persona_id:
        persona_ids = (persona_match.primary_persona_id, *persona_match.secondary_persona_ids)
    return ShadowTrace(
        request_id=request_id,
        timestamp_utc=timestamp.isoformat(),
        persona_version=persona_match.version if persona_match else None,
        matched_persona_ids=persona_ids,
        persona_confidence=persona_match.confidence if persona_match else None,
        evidence_tags=_safe_evidence_tags(persona_match, expert_consensus),
        abstention_reason=persona_match.abstention_reason if persona_match else None,
        expert_version=expert_consensus.version if expert_consensus else None,
        applied_rule_ids=expert_consensus.applicable_rule_ids if expert_consensus else (),
        rejected_rule_ids=expert_consensus.rejected_rule_ids if expert_consensus else (),
        unresolved_rule_ids=expert_consensus.unresolved_rule_ids if expert_consensus else (),
        conflict_groups=expert_consensus.conflict_groups if expert_consensus else (),
        consensus_confidence=expert_consensus.confidence if expert_consensus else None,
        matcher_ms=matcher_ms,
        consensus_ms=consensus_ms,
        blueprint_invoked=False,
        recommendation_engine_active=bool(recommendation_engine_active),
        production_path_used="legacy",
    )
