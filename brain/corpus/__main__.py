"""
The single CI command for the Brain Acceptance Gate:

    python -m brain.corpus

Executes the complete 140-persona validation corpus against the live cascade and
exits non-zero if the Brain commits any over-permissive critical fail (bolder
than the corpus). Prints the coverage report (verdict match, refusal parity,
red-flag routing) for visibility. Infrastructure only — changes no Brain code.
"""
import sys

from brain.corpus import score


def main() -> int:
    r = score()
    c = r["coverage"]
    print("=== BRAIN ACCEPTANCE GATE - 140-persona validation corpus ===")
    print(f"personas executed:          {r['total']}/140")
    print(f"over-permissive fails:      {len(r['critical_over_permissive_fails'])}  (must be 0)")
    print(f"refusal parity:             {c['refusal_parity']}  (Brain refuses wherever corpus refuses)")
    print(f"verdict exact-match:        {c['verdict_exact_match']}/140  ({c['verdict_match_pct']}%)  [coverage]")
    print(f"red-flag routing (seed):    {c['red_flag_routing']}  [coverage - M4 clinical expansion]")
    for f in r["critical_over_permissive_fails"]:
        print(f"  CRITICAL {f['id']}: {f['reason']}")
    ok = r["safe"] and r["total"] == 140
    print("RESULT:", "PASS (no over-permissive critical fail)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
