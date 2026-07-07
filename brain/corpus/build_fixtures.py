"""
Corpus fixture builder (infrastructure only — NOT part of the Brain).

Converts docs/research/APEX_VALIDATION_CORPUS.md (140 prose personas, each with a frozen
10-point evaluation) into ONE deterministic machine-readable fixture per persona,
written to brain/corpus/corpus_fixtures.json.

It PRESERVES the corpus's graded facts verbatim (the raw S2/S4/S5/Generate lines)
and adds parsed structured fields for automated scoring:
  id, cluster, messages (the engineered conversation),
  expected_verdict (GO/MODIFY/NOT_YET/NO_TRAIN, or N/A for dual/no-workout),
  expected_generate (does S6 emit ANY plan), expected_refuses_training (does the
  corpus refuse the *requested* exertional prescription), expected_red_flag
  (corpus marks an affirmative medical red flag that halts/routes),
  expected_intervention (S5 line text).

This is a pure text transform. Re-runnable; deterministic. Run:
    py -3 -m brain.corpus.build_fixtures
"""
import re
import json
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC = _ROOT / "docs" / "research" / "APEX_VALIDATION_CORPUS.md"
_OUT = pathlib.Path(__file__).resolve().parent / "corpus_fixtures.json"

# Cluster map from the corpus coverage table (§ "Coverage map").
_CLUSTERS = [
    (1, 8, "A·teens_students"), (9, 15, "B·office_desk"), (16, 22, "C·shift_irregular"),
    (23, 34, "D·parents_perinatal"), (35, 46, "E·elderly"), (47, 58, "F·athletes_advanced"),
    (59, 66, "G·obesity_metabolic"), (67, 72, "H·beginners_deconditioned"),
    (73, 80, "I·disability_wheelchair"), (81, 86, "J·stroke"), (87, 94, "K·cardiac_htn"),
    (95, 100, "L·diabetes_endocrine"), (101, 108, "M·chronic_pain_joints"),
    (109, 112, "N·insomnia_sleep"), (113, 122, "O·depression_anxiety_burnout"),
    (123, 126, "P·menopause_hormonal"), (127, 130, "Q·cancer_survivors"),
    (131, 140, "R·multi_condition"),
]

_VMAP = {"GO": "GO", "MODIFY": "MODIFY", "NOTYET": "NOT_YET", "NOTRAIN": "NO_TRAIN"}


def _cluster_for(n: int) -> str:
    for lo, hi, name in _CLUSTERS:
        if lo <= n <= hi:
            return name
    return "?"


def _eval_line(body: str, num: int) -> str:
    m = re.search(r'(?m)^%d\.\s+(.*(?:\n(?!\d+\.\s|\s*---|\s*\*\*).*)*)' % num, body)
    return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ""


def _messages(body: str) -> list:
    conv = re.search(r'\*\*Conversation\*\*(.*?)\*\*Evaluation\*\*', body, re.S)
    if not conv:
        return []
    msgs, cur = [], None
    for line in conv.group(1).splitlines():
        m = re.match(r'\s*>\s*\*\*User:\*\*\s*(.*)', line)
        if m:
            if cur is not None:
                msgs.append(cur.strip())
            cur = m.group(1)
        elif cur is not None and line.strip().startswith('>'):
            cur += " " + re.sub(r'^\s*>\s*', '', line)
        elif cur is not None and not line.strip():
            continue
        elif cur is not None:
            msgs.append(cur.strip())
            cur = None
    if cur is not None:
        msgs.append(cur.strip())
    return [m for m in msgs if m]


def _verdict(s4: str) -> str:
    m = re.search(r'S4\s*[—\-–]+\s*\**\(?\s*(GO|MODIFY|NOT\s*YET|NO[\s\-]*TRAIN)', s4, re.I)
    if m:
        return _VMAP[m.group(1).upper().replace(" ", "").replace("-", "")]
    return "N/A"                                   # dual-verdict / no-workout-requested


def _generate(gen_line: str) -> bool:
    low = gen_line.lower()
    # A bare refusal, or "not the/a <requested> session" with no affirmative YES.
    if re.search(r'\byes\b', low):
        return True
    if re.search(r'generate\?\s*\**\s*no\b', low):
        return False
    # "Not the heavy session" / "Not a hard session" → no plan of the requested kind.
    if re.search(r'\bnot (a|the|an|her|his|their|any)\b', low):
        return False
    return False


def _refuses_training(verdict: str, gen_line: str) -> bool:
    low = gen_line.lower()
    if verdict in ("NO_TRAIN", "NOT_YET"):
        return True
    # The requested exertional prescription is refused even if a gentler plan is offered.
    return bool(re.search(r'\b(refuse|not the|not a|not an|not her|not his|instead of|no[t]? the requested)\b', low))


def _red_flag(s2: str, s5: str) -> bool:
    blob = (s2 + " || " + s5).lower()
    if re.search(r'\bred[\s-]?flag\)', blob):                         # explicit "(RED FLAG)" marker
        return True
    if re.search(r'halt (all|any|exert|lower|mileage|restriction)|stop running|stop exert', blob):
        return True
    for m in re.finditer(r'red[\s-]?flag', blob):
        pre = blob[max(0, m.start() - 26):m.start()]
        post = blob[m.end():m.end() + 12]
        negated_before = re.search(r'\bno\b|\bnot\b|monitor|soft|state floor|isn.t|no medical', pre)
        negated_after = re.search(r'[\s-]*(negative|screen)', post)   # "red-flag-negative", "red-flag screen"
        if not negated_before and not negated_after:
            return True
    return False


def build() -> list:
    text = _SRC.read_text(encoding="utf-8")
    parts = re.split(r'(?m)^#### (P-\d{3})\b', text)
    fixtures = []
    for i in range(1, len(parts), 2):
        pid, body = parts[i], parts[i + 1]
        n = int(pid.split("-")[1])
        s2, s4, s5 = _eval_line(body, 4), _eval_line(body, 6), _eval_line(body, 8)
        s5_line = _eval_line(body, 7)
        verdict = _verdict(s4)
        fixtures.append({
            "id": pid,
            "cluster": _cluster_for(n),
            "messages": _messages(body),
            "expected_verdict": verdict,
            "expected_generate": _generate(s5),
            "expected_refuses_training": _refuses_training(verdict, s5),
            "expected_red_flag": _red_flag(s2, s5_line),
            "expected_intervention": s5_line[:200],
            "corpus_s2": s2[:240],
            "corpus_s4": s4[:200],
            "corpus_generate_line": s5[:200],
        })
    return fixtures


def main():
    fixtures = build()
    assert len(fixtures) == 140, f"expected 140 personas, parsed {len(fixtures)}"
    assert [f["id"] for f in fixtures] == [f"P-{i:03d}" for i in range(1, 141)], "persona IDs not 1..140"
    assert all(f["messages"] for f in fixtures), "every persona must carry ≥1 user message"
    _OUT.write_text(json.dumps(fixtures, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {_OUT} ({len(fixtures)} fixtures)")


if __name__ == "__main__":
    main()
