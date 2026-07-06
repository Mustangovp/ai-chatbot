"""
APEX Brain — Inspector (observability).

A PURE FORMATTER. It adds NO reasoning, NO safety logic, and NO decisions, and —
as of M3 Commit 4 — it no longer executes any organ. It takes the single
`Decision` produced by the one orchestrator (`cascade.decide`) and wraps its
deterministic `trace_core` with environment metadata:

  • wall-clock `created_at`
  • the feature-flag snapshot (BRAIN_SHADOW / BRAIN_ENFORCE)
  • library / model / (trace + athlete) schema versions

Everything else in the trace — decision id, evidence fingerprint, per-station
execution + timing, confidence evolution, constraint provenance, skipped
stations, verdict / intervention / generate_training — is produced by the
cascade. The Inspector merely formats. No DB, no Flask, no OpenAI here.
"""
import time

import athlete_model as am
from brain import cascade, config as brain_config, constraint_library, redflag_library

TRACE_SCHEMA = cascade.TRACE_SCHEMA


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def format_decision(decision) -> dict:
    """Wrap a Decision's deterministic `trace_core` with environment metadata.
    The ONLY thing the Inspector does — no organ is executed here."""
    trace = dict(decision.trace_core)          # shallow copy of the deterministic core
    trace["created_at"] = _now_iso()
    trace["flags"] = {
        "BRAIN_SHADOW": brain_config.brain_shadow(),
        "BRAIN_ENFORCE": brain_config.brain_enforce(),
    }
    trace["versions"] = {
        "trace_schema": TRACE_SCHEMA,
        "constraint_library": constraint_library.LIBRARY_VERSION,
        "redflag_library": redflag_library.LIBRARY_VERSION,
        "athlete_model_schema": am.SCHEMA,
        "model": decision.model,
    }
    return trace


def inspect(profile: dict, *, message: str | None = None, conversation: list | None = None,
            physiology: dict | None = None, model: str | None = None,
            decision_id: str | None = None) -> dict:
    """Run the cascade over the evidence (via the one orchestrator) and format the
    resulting Decision into a full, replayable trace. Pure and side-effect free."""
    decision = cascade.decide(profile, message=message, conversation=conversation,
                              physiology=physiology, model=model, decision_id=decision_id)
    return format_decision(decision)
