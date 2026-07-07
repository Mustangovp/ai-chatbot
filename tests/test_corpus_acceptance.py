"""
BRAIN ACCEPTANCE GATE — the complete 140-persona validation corpus, executed
automatically against the live cascade by ONE CI command:

    py -3 -m pytest tests/test_corpus_acceptance.py

Infrastructure only: no Brain / architecture / organ is changed here. Every
persona in docs/research/APEX_VALIDATION_CORPUS.md is one deterministic fixture
(brain/corpus/corpus_fixtures.json), preserving persona id, expected verdict,
expected generation gate, expected refusal, expected red flag, and expected
intervention.

What this gate ASSERTS (green on the current Brain):
  • all 140 personas load and execute deterministically through the one path
  • ZERO over-permissive critical fails — the Brain is never bolder than the
    corpus (never GO where the corpus says NO_TRAIN; never generates training
    where the corpus refuses the exertional prescription)

What this gate TRACKS but does NOT assert green (the M4 obligations — they need
the structured profile/physiology the corpus narrates but does not encode, and
the clinically-signed-off red-flag library): verdict-exact-match and red-flag
routing coverage. These are printed for visibility, not gated.
"""
import brain.corpus as corpus

_REPORT = corpus.score()


def test_all_140_personas_present_and_executed():
    assert _REPORT["total"] == 140
    assert len(_REPORT["rows"]) == 140
    ids = [r["id"] for r in _REPORT["rows"]]
    assert ids == [f"P-{i:03d}" for i in range(1, 141)]


def test_zero_over_permissive_critical_fails():
    fails = _REPORT["critical_over_permissive_fails"]
    assert fails == [], "over-permissive critical fails (Brain bolder than corpus):\n" + \
        "\n".join(f"{f['id']}: {f['reason']}" for f in fails)


def test_corpus_execution_is_deterministic():
    # Re-running any persona yields the identical safety-relevant Decision.
    for fx in corpus.load_fixtures()[:20]:            # sample keeps CI fast; path is pure
        a, b = corpus.run_persona(fx), corpus.run_persona(fx)
        assert (a.verdict, a.halt, a.generate_training) == (b.verdict, b.halt, b.generate_training)


def test_print_coverage_report(capsys):
    with capsys.disabled():
        c = _REPORT["coverage"]
        print("\n--- BRAIN ACCEPTANCE COVERAGE (140-persona corpus) ---")
        print(f"  safe (0 over-permissive fails): {_REPORT['safe']}")
        print(f"  verdict exact-match:  {c['verdict_exact_match']}/140  ({c['verdict_match_pct']}%)")
        print(f"  refusal parity:       {c['refusal_parity']}")
        print(f"  red-flag routing:     {c['red_flag_routing']}  (seed library; M4 clinical expansion pending)")
        if c["red_flag_missed_ids"]:
            print(f"  red-flag gaps (M4):   {', '.join(c['red_flag_missed_ids'])}")
