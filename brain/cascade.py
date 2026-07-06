"""
APEX Brain — the Cascade (the ONE composition point).

This is the single orchestrator of the deliberation cascade. It is the ONLY
place in the entire codebase that executes the organs S1→S5; nothing else may
import or call them. It runs them exactly once each, in a fixed deterministic
order, and returns one `Decision`.

Invariants this module is designed to guarantee (proven by tests):
  • every organ executes at most once            — one straight-line call each
  • every organ executes in deterministic order  — S1, S2, S3, S4, S5
  • no organ can bypass the cascade              — organs are imported here only
  • Inspector / Replay / Regression consume the   — they all consume the Decision
    identical Decision object                       (its `trace_core`)
  • there is exactly one composition point        — this function

Addendum 02 A2-0: a red-flag halt at S2 must never yield training. The halt is
carried through S4 (defense-in-depth → NOT_YET) and S5 (route intervention), so
the cascade stays a single uniform path with no bypass branch. `generate_training`
is the sole gate on S6 and is False whenever S2 halts.

Pure: no Flask, no DB, no OpenAI. Produces a deterministic, trace-ready payload
(`trace_core`); the Inspector merely wraps it with environment metadata.
"""
import time
import uuid
import json
import hashlib

from brain import (s1_constraints, s2_sentinel, s3_needs, s4_gate, s5_selector,
                   constraint_library)
from brain.types import Decision

TRACE_SCHEMA = "brain-trace-v2"
_ALL_STATIONS = ("S1", "S2", "S3", "S4", "S5", "S6")
_ENVELOPE_FIELDS = ("age", "level", "activityLevel")
_PROFILE_FIELDS = ("age", "gender", "level", "activityLevel", "equipment",
                   "goal", "healthNotes", "injuries")


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _fingerprint(profile: dict) -> str:
    """Deterministic hash of the decision-relevant evidence."""
    relevant = {k: str(profile.get(k) or "") for k in _PROFILE_FIELDS}
    return _sha(json.dumps(relevant, sort_keys=True, ensure_ascii=False))


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 3)


def decide(profile: dict, *, message: str | None = None, conversation: list | None = None,
           physiology: dict | None = None, model: str | None = None,
           decision_id: str | None = None) -> Decision:
    """Run S1→S5 over the evidence and return the single Decision. The one and
    only orchestration path."""
    profile = profile or {}
    decision_id = str(decision_id) if decision_id else str(uuid.uuid4())
    hn = str(profile.get("healthNotes") or profile.get("injuries") or "")
    fields_present = sorted(k for k in _PROFILE_FIELDS if str(profile.get(k) or "").strip())

    stations: dict = {}
    executed: list = []
    skipped: list = []
    confidence_evolution: list = []

    # ── S1 · Somatic Constraint Model ────────────────────────────────────────
    t = time.perf_counter()
    cset, env = s1_constraints.build(profile)
    d1 = _ms(t)

    detected = sorted(constraint_library.detect_conditions(hn))
    prov: dict[str, set] = {}
    for cond in detected:
        for c in constraint_library.constraints_for(cond):
            prov.setdefault(c.movement, set()).add(cond)

    constraints_added = []
    for c in cset.items:
        sources = sorted(prov.get(c.movement, []))
        constraints_added.append({
            "movement": c.movement,
            "tier": c.tier.value,
            "reason_key": c.reason_key,
            "source_conditions": sources,
            "why": (f"detected condition(s) {sources} → constraint library"
                    if sources else "present in library mapping"),
        })

    no_constraint_reason = None
    if not cset.items:
        if not hn.strip():
            no_constraint_reason = "no health information provided (healthNotes empty)"
        elif not detected:
            no_constraint_reason = ("healthNotes present but no known condition token matched "
                                    "(library coverage gap, or genuinely unremarkable)")
        else:
            no_constraint_reason = "conditions detected but they map to no movement constraints"

    envelope_factors = sorted(k for k in _ENVELOPE_FIELDS if str(profile.get(k) or "").strip())
    stations["S1"] = {
        "executed": True,
        "duration_ms": d1,
        "inputs": {"profile_fields_present": fields_present},
        "evidence_changed_state": {
            "detected_conditions": detected,
            "envelope_factors_present": envelope_factors,
        },
        "constraints_added": constraints_added,
        "no_constraint_reason": no_constraint_reason,
        "envelope": {
            "intensity_ceiling": env.intensity_ceiling,
            "complexity_ceiling": env.complexity_ceiling,
            "volume_ceiling": env.volume_ceiling,
            "supported": env.supported,
            "confidence": env.confidence,
        },
        "confidence": env.confidence,
    }
    executed.append("S1")
    confidence_evolution.append({"station": "S1", "confidence": env.confidence})

    # ── S2 · Readiness + Red-Flag Sentinel ───────────────────────────────────
    t = time.perf_counter()
    s2 = s2_sentinel.assess(message=message, conversation=conversation,
                            profile=profile, physiology=physiology)
    d2 = _ms(t)
    stations["S2"] = {
        "executed": True,
        "duration_ms": d2,
        "readiness": s2.readiness,
        "readiness_confidence": s2.readiness_conf,
        "red_flags": [{"class_key": f.class_key, "urgency": f.urgency.value,
                       "route_target": f.route_target, "message_key": f.message_key,
                       "source": f.source} for f in s2.red_flags],
        "halt": s2.halt,
    }
    executed.append("S2")
    confidence_evolution.append({"station": "S2", "confidence": s2.readiness_conf})

    # ── S3 · Need Vector ─────────────────────────────────────────────────────
    t = time.perf_counter()
    need_vector = s3_needs.rank(envelope=env, s2=s2, profile=profile)
    d3 = _ms(t)
    stations["S3"] = {
        "executed": True,
        "duration_ms": d3,
        "need_vector": [{"need": n, "weight": w} for n, w in need_vector],
        "dominant": (need_vector[0][0] if need_vector else None),
    }
    executed.append("S3")

    # ── S4 · Appropriateness Gate ────────────────────────────────────────────
    t = time.perf_counter()
    verdict, vconf = s4_gate.decide(constraints=cset, envelope=env, s2=s2, need_vector=need_vector)
    d4 = _ms(t)
    stations["S4"] = {
        "executed": True,
        "duration_ms": d4,
        "verdict": verdict.value,
        "verdict_confidence": vconf,
    }
    executed.append("S4")
    confidence_evolution.append({"station": "S4", "confidence": vconf})

    # ── S5 · Intervention Selector ───────────────────────────────────────────
    t = time.perf_counter()
    intervention = s5_selector.select(verdict=verdict, s2=s2, need_vector=need_vector, profile=profile)
    d5 = _ms(t)
    gen = s5_selector.generate_training(verdict, intervention)
    stations["S5"] = {
        "executed": True,
        "duration_ms": d5,
        "intervention": {"kind": intervention.kind, "rationale_key": intervention.rationale_key},
        "generate_training": gen,
    }
    executed.append("S5")

    # S6 (generation) runs on the legacy path in shadow — decision only here.
    skipped.append({"station": "S6", "reason": "shadow_decision_only"})

    trace_core = {
        "decision_id": decision_id,
        "trace_schema": TRACE_SCHEMA,
        "evidence_fingerprint": _fingerprint(profile),
        "source_evidence": {
            "health_notes_present": bool(hn.strip()),
            "health_notes_hash": _sha(hn) if hn.strip() else None,
            "profile_fields_present": fields_present,
        },
        "cascade": {
            "stations_executed": executed,
            "stations_skipped": skipped,
            "confidence_evolution": confidence_evolution,
            "total_ms": round(d1 + d2 + d3 + d4 + d5, 3),
            "halt": s2.halt,
            "verdict": verdict.value,
            "verdict_confidence": vconf,
            "intervention": intervention.kind,
            "generate_training": gen,
        },
        "stations": stations,
    }

    return Decision(
        verdict=verdict,
        intervention=intervention,
        generate_training=gen,
        halt=s2.halt,
        verdict_confidence=vconf,
        constraints=cset,
        envelope=env,
        s2=s2,
        need_vector=need_vector,
        decision_id=decision_id,
        model=model,
        trace_core=trace_core,
    )
