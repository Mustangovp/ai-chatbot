"""
M3 Commit 4 — the composition layer. These tests PROVE the invariants the
cascade is designed to guarantee:

  1. every organ executes at most once
  2. every organ executes in a deterministic order (S1..S5)
  3. no organ can bypass the cascade
  4. Inspector, Replay, and Regression consume the identical Decision
  5. there is exactly one composition point in the codebase
"""
import ast
import pathlib

import brain.cascade as cascade
from brain import (s1_constraints, s2_sentinel, s3_needs, s4_gate, s5_selector,
                   inspector, replay)

_ORGANS = {"s1_constraints", "s2_sentinel", "s3_needs", "s4_gate", "s5_selector"}


# ── Invariants 1 + 2 — each organ once, in deterministic order ───────────────
def test_each_organ_runs_exactly_once_in_deterministic_order(monkeypatch):
    calls = []

    def _wrap(name, fn):
        def inner(*a, **k):
            calls.append(name)
            return fn(*a, **k)
        return inner

    monkeypatch.setattr(cascade.s1_constraints, "build", _wrap("S1", s1_constraints.build))
    monkeypatch.setattr(cascade.s2_sentinel, "assess", _wrap("S2", s2_sentinel.assess))
    monkeypatch.setattr(cascade.s3_needs, "rank", _wrap("S3", s3_needs.rank))
    monkeypatch.setattr(cascade.s4_gate, "decide", _wrap("S4", s4_gate.decide))
    monkeypatch.setattr(cascade.s5_selector, "select", _wrap("S5", s5_selector.select))

    cascade.decide({"healthNotes": "high blood pressure"}, message="let's train")
    assert calls == ["S1", "S2", "S3", "S4", "S5"]      # order + exactly one each


def test_halt_still_runs_each_organ_once_no_bypass_branch(monkeypatch):
    # A halt must NOT create a second path: the cascade stays uniform S1..S5.
    calls = []
    for mod, attr, name in [(cascade.s1_constraints, "build", "S1"),
                            (cascade.s2_sentinel, "assess", "S2"),
                            (cascade.s3_needs, "rank", "S3"),
                            (cascade.s4_gate, "decide", "S4"),
                            (cascade.s5_selector, "select", "S5")]:
        real = getattr(mod, attr)
        monkeypatch.setattr(mod, attr, (lambda n, f: (lambda *a, **k: (calls.append(n), f(*a, **k))[1]))(name, real))

    d = cascade.decide({}, message="my chest is tight and heavy going uphill")
    assert d.halt is True and d.generate_training is False
    assert calls == ["S1", "S2", "S3", "S4", "S5"]


# ── Invariant 4 — one Decision, consumed identically everywhere ──────────────
def test_inspector_formats_the_cascade_decision(monkeypatch):
    seen = {}
    real = cascade.decide

    def _spy(profile, **k):
        d = real(profile, **k)
        seen["d"] = d
        return d

    monkeypatch.setattr(inspector.cascade, "decide", _spy)
    tr = inspector.inspect({"healthNotes": "high blood pressure"}, message="chest is tight and heavy")
    # The trace is exactly the formatted Decision that cascade.decide returned.
    assert seen["d"].trace_core["decision_id"] == tr["decision_id"]
    assert seen["d"].verdict.value == tr["cascade"]["verdict"]
    assert seen["d"].generate_training == tr["cascade"]["generate_training"]


def test_inspector_and_replay_consume_the_identical_decision():
    ev = {"profile": {"healthNotes": "high blood pressure"}, "message": "chest is tight and heavy"}
    base = inspector.inspect(ev["profile"], message=ev["message"])
    rr = replay.replay(ev, base)
    # Replay re-runs through the SAME one path; canonical Decisions match.
    assert rr["classification"] == replay.IDENTICAL
    assert rr["first_divergence"] is None


# ── Invariants 3 + 5 — no bypass; exactly one composition point ──────────────
def _organs_imported_by(path: pathlib.Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("brain"):
            imported.update(n.name for n in node.names)
        elif isinstance(node, ast.Import):
            imported.update(n.name.split(".")[-1] for n in node.names)
    return imported & _ORGANS


def test_single_composition_point_no_organ_bypass():
    brain_dir = pathlib.Path(cascade.__file__).parent
    repo = brain_dir.parent
    candidates = list(brain_dir.glob("*.py")) + [repo / "app.py", repo / "athlete_store.py"]
    importers = sorted(p.name for p in candidates if p.exists() and _organs_imported_by(p))
    # The organs are reachable through exactly one module: the cascade.
    assert importers == ["cascade.py"]
