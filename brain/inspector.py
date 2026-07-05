"""
APEX Brain — Inspector (observability).

A PURE tracing layer. It adds NO reasoning, NO safety logic, and NO decisions —
it only makes an existing Brain decision completely inspectable:

  • a stable Decision ID and a deterministic evidence fingerprint
  • per-station execution + timing
  • confidence evolution through the cascade
  • which evidence changed the state
  • why each constraint was added — and why none was, when the set is empty
  • explicitly-recorded skipped stations
  • feature-flag state, and library / model / (trace + athlete) schema versions

It produces the canonical trace dict stored in `brain_decisions.trace` and
returned by the debug inspection endpoint. No DB, no Flask, no OpenAI here.
"""
import time
import uuid
import json
import hashlib

import athlete_model as am
from brain import s1_constraints, config as brain_config, constraint_library

TRACE_SCHEMA = "brain-trace-v2"
_ALL_STATIONS = ("S1", "S2", "S3", "S4", "S5", "S6")
_ENVELOPE_FIELDS = ("age", "level", "activityLevel")
_PROFILE_FIELDS = ("age", "gender", "level", "activityLevel", "equipment",
                   "goal", "healthNotes", "injuries")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _fingerprint(profile: dict) -> str:
    """Deterministic hash of the decision-relevant evidence — identical inputs
    correlate across decisions (same evidence → same fingerprint)."""
    relevant = {k: str(profile.get(k) or "") for k in _PROFILE_FIELDS}
    return _sha(json.dumps(relevant, sort_keys=True, ensure_ascii=False))


def inspect(profile: dict, *, model: str | None = None, decision_id: str | None = None) -> dict:
    """Run the (currently S1-only) cascade over `profile` and return a full,
    replayable trace. Pure and side-effect free. `decision_id` is a stable id
    (generated if not supplied)."""
    profile = profile or {}
    decision_id = str(decision_id) if decision_id else str(uuid.uuid4())
    hn = str(profile.get("healthNotes") or profile.get("injuries") or "")
    fields_present = sorted(k for k in _PROFILE_FIELDS if str(profile.get(k) or "").strip())

    trace = {
        "decision_id": decision_id,
        "trace_schema": TRACE_SCHEMA,
        "created_at": _now_iso(),
        "evidence_fingerprint": _fingerprint(profile),
        "flags": {
            "BRAIN_SHADOW": brain_config.brain_shadow(),
            "BRAIN_ENFORCE": brain_config.brain_enforce(),
        },
        "versions": {
            "trace_schema": TRACE_SCHEMA,
            "constraint_library": constraint_library.LIBRARY_VERSION,
            "athlete_model_schema": am.SCHEMA,
            "model": model,
        },
        "source_evidence": {
            "health_notes_present": bool(hn.strip()),
            "health_notes_hash": _sha(hn) if hn.strip() else None,
            "profile_fields_present": fields_present,
        },
        "cascade": {
            "stations_executed": [],
            "stations_skipped": [],
            "confidence_evolution": [],
            "total_ms": 0.0,
        },
        "stations": {},
    }

    # ── Station S1 · Somatic Constraint Model ─────────────────────────────────
    t0 = time.perf_counter()
    cset, env = s1_constraints.build(profile)
    dur_ms = round((time.perf_counter() - t0) * 1000, 3)

    detected = sorted(constraint_library.detect_conditions(hn))
    # movement → source condition(s), re-derived from the public library
    # (attribution only; the S1 organ's build() is unchanged).
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

    trace["stations"]["S1"] = {
        "executed": True,
        "duration_ms": dur_ms,
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
    trace["cascade"]["stations_executed"].append("S1")
    trace["cascade"]["confidence_evolution"].append({"station": "S1", "confidence": env.confidence})

    # Stations not yet implemented are recorded explicitly as skipped.
    for s in _ALL_STATIONS[1:]:
        trace["cascade"]["stations_skipped"].append({"station": s, "reason": "not_yet_implemented"})

    trace["cascade"]["total_ms"] = round(dur_ms, 3)
    return trace
