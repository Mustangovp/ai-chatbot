"""
APEX Brain — Replay & Regression Harness (debug / QA only).

Pure module. Adds NO reasoning, NO Brain logic, NO safety logic — it re-runs the
existing Brain (via inspector.inspect) over known evidence and DIFFS the result
against a stored/baseline trace, so code changes can be regression-checked.

Determinism: `canonicalize()` strips the volatile fields (decision_id,
created_at, durations) so that identical (evidence + library version + code)
always yields an identical canonical trace.

Classification of a replay vs its baseline (a QA verdict about *drift between two
traces* — never a Brain decision):
  IDENTICAL        — canonical traces equal.
  EXPECTED_CHANGE  — differences are all in the SAFE direction (more/stricter
                     constraints, narrower envelope, more detections, version bump).
  REGRESSION       — any SAFETY-WEAKENING drift: a constraint dropped or weakened,
                     a lost detection, the envelope widened while constrained,
                     support lost while constrained, a halt dropped, a red flag
                     lost, the verdict made bolder, or generation newly enabled.

Every consumer here re-runs the Brain through the ONE orchestration path
(`inspector.inspect` → `cascade.decide`) and consumes the identical Decision
(via its formatted trace); no organ is executed in this module.
"""
from copy import deepcopy
from brain import inspector

IDENTICAL = "IDENTICAL"
EXPECTED_CHANGE = "EXPECTED_CHANGE"
REGRESSION = "REGRESSION"

_TIER_RANK = {"monitor": 0, "relative": 1, "absolute": 2}
# Boldness of a verdict — higher = more permissive toward training. A replay that
# moves the verdict UP this scale (safer→bolder) versus its baseline is unsafe.
_VERDICT_BOLDNESS = {"NO_TRAIN": 0, "NOT_YET": 1, "MODIFY": 2, "GO": 3}


def _run(evidence, *, model=None) -> dict:
    """Re-run the Brain over evidence through the one orchestration path.
    `evidence` is a bare profile, or a dict {profile, message, conversation,
    physiology, model} for cascades that exercise S2-S5."""
    if isinstance(evidence, dict) and ("profile" in evidence or "message" in evidence
                                       or "conversation" in evidence or "physiology" in evidence):
        return inspector.inspect(evidence.get("profile") or {},
                                 message=evidence.get("message"),
                                 conversation=evidence.get("conversation"),
                                 physiology=evidence.get("physiology"),
                                 model=evidence.get("model", model))
    return inspector.inspect(evidence or {}, model=model)


# ── Canonicalisation (deterministic core of a trace) ─────────────────────────
def canonicalize(trace: dict) -> dict:
    """Deep copy with non-deterministic fields removed."""
    t = deepcopy(trace or {})
    t.pop("decision_id", None)
    t.pop("created_at", None)
    casc = t.get("cascade")
    if isinstance(casc, dict):
        casc.pop("total_ms", None)
    for st in (t.get("stations") or {}).values():
        if isinstance(st, dict):
            st.pop("duration_ms", None)
    return t


def deterministic_trace(evidence: dict, *, model: str | None = None) -> dict:
    """The stable trace: same evidence + same library + same code → equal output."""
    return canonicalize(_run(evidence, model=model))


# ── Trace accessors ──────────────────────────────────────────────────────────
def _s1(trace: dict) -> dict:
    return ((trace or {}).get("stations") or {}).get("S1") or {}


def _s2(trace: dict) -> dict:
    return ((trace or {}).get("stations") or {}).get("S2") or {}


def _cascade(trace: dict) -> dict:
    return (trace or {}).get("cascade") or {}


def _constraint_map(trace: dict) -> dict:
    return {c["movement"]: c["tier"] for c in _s1(trace).get("constraints_added", [])}


def _envelope(trace: dict) -> dict:
    return _s1(trace).get("envelope", {})


def _detected(trace: dict) -> set:
    return set(_s1(trace).get("evidence_changed_state", {}).get("detected_conditions", []))


def _red_flag_classes(trace: dict) -> set:
    return {f.get("class_key") for f in _s2(trace).get("red_flags", [])}


def _halt(trace: dict) -> bool:
    return bool(_cascade(trace).get("halt") or _s2(trace).get("halt"))


def _verdict(trace: dict) -> str | None:
    return _cascade(trace).get("verdict")


def _generates_training(trace: dict) -> bool:
    return bool(_cascade(trace).get("generate_training"))


# ── Deltas ───────────────────────────────────────────────────────────────────
def constraint_delta(baseline: dict, new: dict) -> dict:
    b, n = _constraint_map(baseline), _constraint_map(new)
    weakened, strengthened = [], []
    for m in set(b) & set(n):
        if _TIER_RANK[n[m]] < _TIER_RANK[b[m]]:
            weakened.append({"movement": m, "from": b[m], "to": n[m]})
        elif _TIER_RANK[n[m]] > _TIER_RANK[b[m]]:
            strengthened.append({"movement": m, "from": b[m], "to": n[m]})
    return {
        "added": sorted(m for m in n if m not in b),
        "removed": sorted(m for m in b if m not in n),
        "weakened": weakened,
        "strengthened": strengthened,
    }


def confidence_delta(baseline: dict, new: dict) -> float:
    return round(_s1(new).get("confidence", 0.0) - _s1(baseline).get("confidence", 0.0), 4)


def duration_delta_ms(baseline: dict, new: dict) -> float:
    return round(_s1(new).get("duration_ms", 0.0) - _s1(baseline).get("duration_ms", 0.0), 3)


def first_divergence(baseline: dict, new: dict):
    """First dot-path where the canonical traces differ, or None if identical."""
    return _first_diff(canonicalize(baseline), canonicalize(new), "")


def _first_diff(a, b, path):
    if type(a) is not type(b):
        return path or "<root>"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                return f"{path}.{k}".lstrip(".")
            d = _first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return (f"{path}[len]").lstrip(".")
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else (path or "<root>")


# ── Classification ───────────────────────────────────────────────────────────
def classify(baseline: dict, new: dict) -> str:
    if canonicalize(baseline) == canonicalize(new):
        return IDENTICAL
    cd = constraint_delta(baseline, new)
    be, ne = _envelope(baseline), _envelope(new)

    unsafe = bool(cd["removed"]) or bool(cd["weakened"])
    if _detected(baseline) - _detected(new):                       # a condition stopped being detected
        unsafe = True
    if _constraint_map(baseline) and \
            ne.get("intensity_ceiling", 0.0) > be.get("intensity_ceiling", 0.0) + 1e-9:
        unsafe = True                                              # wider envelope while constrained
    if be.get("supported") and not ne.get("supported") and _constraint_map(new):
        unsafe = True                                              # support lost while constrained

    # C3 — cascade-level safety drift (S2-S5).
    if _halt(baseline) and not _halt(new):
        unsafe = True                                              # a halt was dropped
    if _red_flag_classes(baseline) - _red_flag_classes(new):
        unsafe = True                                              # a red flag was lost
    bv, nv = _verdict(baseline), _verdict(new)
    if bv in _VERDICT_BOLDNESS and nv in _VERDICT_BOLDNESS and \
            _VERDICT_BOLDNESS[nv] > _VERDICT_BOLDNESS[bv]:
        unsafe = True                                              # verdict made bolder (toward GO)
    if _generates_training(new) and not _generates_training(baseline):
        unsafe = True                                              # generation newly enabled

    return REGRESSION if unsafe else EXPECTED_CHANGE


# ── Replay ───────────────────────────────────────────────────────────────────
def replay(evidence: dict, baseline_trace: dict, *, model: str | None = None) -> dict:
    """Re-run the Brain over `evidence` and compare to `baseline_trace`."""
    new_trace = _run(evidence, model=model)
    return {
        "classification": classify(baseline_trace, new_trace),
        "first_divergence": first_divergence(baseline_trace, new_trace),
        "confidence_delta": confidence_delta(baseline_trace, new_trace),
        "constraint_delta": constraint_delta(baseline_trace, new_trace),
        "duration_delta_ms": duration_delta_ms(baseline_trace, new_trace),
        "original_trace": baseline_trace,
        "new_trace": new_trace,
    }


def snapshot(cases: list, *, model: str | None = None) -> dict:
    """Baseline traces for a list of cases [{id, evidence}] → {id: trace}."""
    return {c["id"]: _run(c.get("evidence") or {}, model=model) for c in cases}


def replay_corpus(cases: list, baselines: dict, *, model: str | None = None) -> dict:
    """Regression report over cases [{id, evidence}] vs baselines {id: trace}.
    Suitable for the 140-persona validation corpus: feed the personas' profiles
    as evidence and their snapshotted traces as baselines."""
    results, counts = [], {IDENTICAL: 0, EXPECTED_CHANGE: 0, REGRESSION: 0}
    for c in cases:
        base = (baselines or {}).get(c["id"])
        if base is None:
            continue
        rr = replay(c.get("evidence") or {}, base, model=model)
        counts[rr["classification"]] += 1
        results.append({
            "id": c["id"],
            "classification": rr["classification"],
            "first_divergence": rr["first_divergence"],
            "confidence_delta": rr["confidence_delta"],
            "constraint_delta": rr["constraint_delta"],
            "duration_delta_ms": rr["duration_delta_ms"],
        })
    return {
        "total": len(results),
        "summary": counts,
        "passed": counts[REGRESSION] == 0,
        "regressions": [r for r in results if r["classification"] == REGRESSION],
        "cases": results,
        "trace_schema": inspector.TRACE_SCHEMA,
    }
