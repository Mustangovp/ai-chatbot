"""
M1 Commit 4 — Brain Replay & Regression Harness.
Determinism · IDENTICAL/EXPECTED_CHANGE/REGRESSION · deltas · first divergence ·
corpus report · debug-only endpoints.
"""
from copy import deepcopy
import app as app_module
from brain import replay, inspector


# ── Determinism (req 4): same evidence + library + code → same canonical trace ─
def test_deterministic_replay_is_stable():
    p = {"age": 69, "level": "beginner", "activityLevel": "sedentary",
         "healthNotes": "prior stroke, high blood pressure"}
    a = replay.deterministic_trace(p)
    b = replay.deterministic_trace(p)
    assert a == b                                   # stable
    assert "decision_id" not in a and "created_at" not in a
    assert "duration_ms" not in a["stations"]["S1"]


# ── IDENTICAL (req 3): baseline == current code on same evidence ──────────────
def test_replay_identical_against_self():
    p = {"healthNotes": "hypertension"}
    baseline = inspector.inspect(p)
    r = replay.replay(p, baseline)
    assert r["classification"] == replay.IDENTICAL
    assert r["first_divergence"] is None
    assert r["constraint_delta"]["added"] == [] and r["constraint_delta"]["removed"] == []


# ── REGRESSION (req 3): a baseline forbid that current code no longer produces ─
def test_replay_regression_when_constraint_dropped():
    evidence = {"healthNotes": "generally fine"}     # current code → no constraints
    baseline = inspector.inspect(evidence)
    # Inject a stronger baseline (a valsalva ABSOLUTE the current code won't produce).
    baseline = deepcopy(baseline)
    baseline["stations"]["S1"]["constraints_added"].append(
        {"movement": "valsalva", "tier": "absolute", "reason_key": "x", "source_conditions": ["hypertension"]})
    r = replay.replay(evidence, baseline)
    assert r["classification"] == replay.REGRESSION
    assert "valsalva" in r["constraint_delta"]["removed"]
    assert r["first_divergence"] is not None


# ── EXPECTED_CHANGE (req 3): current code stricter than a weaker baseline ──────
def test_replay_expected_change_when_constraint_added():
    evidence = {"healthNotes": "hypertension"}        # current code → valsalva absolute
    baseline = inspector.inspect(evidence)
    baseline = deepcopy(baseline)
    baseline["stations"]["S1"]["constraints_added"] = [
        c for c in baseline["stations"]["S1"]["constraints_added"] if c["movement"] != "valsalva"]
    r = replay.replay(evidence, baseline)
    assert r["classification"] == replay.EXPECTED_CHANGE
    assert "valsalva" in r["constraint_delta"]["added"]


# ── Deltas present (req 2) ────────────────────────────────────────────────────
def test_replay_reports_all_deltas():
    p = {"age": 40, "healthNotes": "osteoporosis"}
    baseline = inspector.inspect(p)
    r = replay.replay(p, baseline)
    for k in ("original_trace", "new_trace", "first_divergence",
              "confidence_delta", "constraint_delta", "duration_delta_ms"):
        assert k in r


# ── Corpus report (req 5) ─────────────────────────────────────────────────────
def _corpus_cases():
    return [
        {"id": "P-035", "evidence": {"age": 69, "level": "beginner", "activityLevel": "sedentary",
                                     "healthNotes": "prior stroke, high blood pressure, diabetes, joint pain"}},
        {"id": "P-036", "evidence": {"age": 73, "level": "advanced", "activityLevel": "active", "healthNotes": ""}},
        {"id": "P-040", "evidence": {"healthNotes": "osteoporosis"}},
        {"id": "P-079", "evidence": {"age": 31, "level": "advanced", "activityLevel": "active"}},
    ]


def test_corpus_report_all_identical_against_snapshot():
    cases = _corpus_cases()
    baselines = replay.snapshot(cases)
    report = replay.replay_corpus(cases, baselines)
    assert report["total"] == 4
    assert report["passed"] is True
    assert report["summary"]["REGRESSION"] == 0
    assert report["summary"]["IDENTICAL"] == 4


def test_corpus_report_flags_injected_regression():
    cases = _corpus_cases()
    baselines = replay.snapshot(cases)
    # Weaken P-035's baseline detection so current code looks like it lost a condition.
    baselines["P-035"]["stations"]["S1"]["constraints_added"].append(
        {"movement": "made_up_absolute", "tier": "absolute", "reason_key": "x", "source_conditions": ["foo"]})
    report = replay.replay_corpus(cases, baselines)
    assert report["passed"] is False
    assert report["summary"]["REGRESSION"] == 1
    assert report["regressions"][0]["id"] == "P-035"


# ── Debug-only endpoints (req 6) ──────────────────────────────────────────────
def test_endpoints_404_when_debug_off(monkeypatch):
    monkeypatch.delenv("BRAIN_DEBUG", raising=False)
    client = app_module.app.test_client()
    assert client.post("/debug/brain/replay-compare", json={"evidence": {}, "baseline": {}}).status_code == 404
    assert client.post("/debug/brain/regression", json={"cases": []}).status_code == 404


def test_replay_compare_endpoint_when_debug_on(monkeypatch):
    monkeypatch.setenv("BRAIN_DEBUG", "1")
    client = app_module.app.test_client()
    p = {"healthNotes": "hypertension"}
    baseline = inspector.inspect(p)
    r = client.post("/debug/brain/replay-compare", json={"evidence": p, "baseline": baseline})
    assert r.status_code == 200
    assert r.get_json()["classification"] == replay.IDENTICAL


def test_regression_endpoint_snapshot_then_compare(monkeypatch):
    monkeypatch.setenv("BRAIN_DEBUG", "1")
    client = app_module.app.test_client()
    cases = _corpus_cases()
    snap = client.post("/debug/brain/regression", json={"cases": cases})
    assert snap.status_code == 200
    baselines = snap.get_json()["baselines"]
    rep = client.post("/debug/brain/regression", json={"cases": cases, "baselines": baselines})
    assert rep.status_code == 200
    assert rep.get_json()["summary"]["REGRESSION"] == 0
