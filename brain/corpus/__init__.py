"""
APEX Brain — Validation Corpus harness (infrastructure only).

Loads the 140 machine-readable persona fixtures (built from the frozen
docs/research/APEX_VALIDATION_CORPUS.md by build_fixtures.py) and scores the live cascade
against them through the ONE orchestration path (brain.cascade.decide). Adds NO
reasoning and NO Brain logic — it only runs the Brain and tallies outcomes.

Scoring honours the corpus's own gate contract (§"Scoring a release"):
  • CRITICAL (blocking) over-permissive fails — the release is UNSAFE if it is
    bolder than the corpus: a GO where the corpus refuses training, or training
    generated where the corpus refuses the exertional prescription.
  • COVERAGE (reported, non-blocking) — verdict-exact-match and red-flag routing
    coverage. These require the structured profile/physiology the corpus narrates
    in prose (not encoded) and the clinically-signed-off red-flag library — i.e.
    the M4 build-time obligations. They are TRACKED here, not asserted green.
"""
import json
import pathlib

from brain import cascade

_FIXTURES = pathlib.Path(__file__).resolve().parent / "corpus_fixtures.json"
_BOLDNESS = {"NO_TRAIN": 0, "NOT_YET": 1, "MODIFY": 2, "GO": 3}


def load_fixtures() -> list:
    """The 140 persona fixtures, in P-001..P-140 order."""
    return json.loads(_FIXTURES.read_text(encoding="utf-8"))


def run_persona(fx: dict):
    """Run one persona's engineered conversation through the cascade (message-only:
    the corpus encodes no athlete-model physiology, so the Brain runs conservative
    by construction). Returns the Decision."""
    msgs = fx.get("messages") or [""]
    conversation = [{"role": "user", "content": m} for m in msgs[:-1]]
    return cascade.decide({}, message=msgs[-1], conversation=conversation)


def _over_permissive(fx: dict, d) -> str | None:
    """A CRITICAL fail per the corpus: the release is bolder than the corpus in a
    way that could prescribe unsafe exertion. Returns a reason or None."""
    if d.generate_training and fx["expected_refuses_training"]:
        return "generated training where corpus refuses the exertional prescription"
    if d.verdict.value == "GO" and fx["expected_verdict"] == "NO_TRAIN":
        return "verdict GO where corpus says NO_TRAIN"
    return None


def score() -> dict:
    """Full acceptance report over all 140 personas."""
    fixtures = load_fixtures()
    critical, verdict_hits, refusal_parity = [], 0, 0
    rf_expected, rf_caught, rf_missed = 0, 0, []
    rows = []
    for fx in fixtures:
        d = run_persona(fx)
        viol = _over_permissive(fx, d)
        if viol:
            critical.append({"id": fx["id"], "reason": viol})
        if d.verdict.value == fx["expected_verdict"]:
            verdict_hits += 1
        if fx["expected_refuses_training"] and not d.generate_training:
            refusal_parity += 1
        if fx["expected_red_flag"]:
            rf_expected += 1
            if d.halt:
                rf_caught += 1
            else:
                rf_missed.append(fx["id"])
        rows.append({"id": fx["id"], "cascade_verdict": d.verdict.value,
                     "cascade_halt": d.halt, "cascade_generate_training": d.generate_training,
                     "flags": [f.class_key for f in d.s2.red_flags]})
    n = len(fixtures)
    refusals = sum(1 for f in fixtures if f["expected_refuses_training"])
    return {
        "total": n,
        "critical_over_permissive_fails": critical,       # BLOCKING — must be empty
        "safe": len(critical) == 0,
        "coverage": {
            "verdict_exact_match": verdict_hits,
            "verdict_match_pct": round(100.0 * verdict_hits / n, 1),
            "refusal_parity": f"{refusal_parity}/{refusals}",
            "red_flag_routing": f"{rf_caught}/{rf_expected}",
            "red_flag_missed_ids": rf_missed,
        },
        "rows": rows,
    }
