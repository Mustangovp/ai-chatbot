"""
M3 Commit 4 — shadow verification of the full cascade against the validation
corpus. Runs a REPRESENTATIVE machine-readable subset of the 140-persona corpus
end-to-end through the ONE orchestration path (cascade → inspector trace) and
asserts the corpus-correct SAFETY outcome for each persona.

Scope note (honest): this is a representative subset (~12 personas) spanning the
Critical-Fail Index emergencies, GO/training cases, an over-caution guard, and a
depletion defer — not all 140. Extracting every persona profile from the corpus
prose is a data task; the regression harness (replay.replay_corpus) already scales
to the full set once those fixtures exist. Reported symptoms live in the MESSAGE
(where S2 scans); chronic conditions live in healthNotes (where S1 scans).
"""
from brain import cascade

_FIT = {"recovery": 0.9, "fatigue": 0.1, "stress": 0.15, "confidence": 0.7}
_DEPLETED = {"recovery": 0.2, "fatigue": 0.9, "stress": 0.6, "confidence": 0.6}
_ROUTE = {"medical_followup", "crisis_support"}

# id, profile, message, physiology, expected outcome.
CORPUS = [
    # ── Critical-Fail Index — must HALT, must NOT generate training ──
    ("P-083-stroke", {}, "the right side of my face has drooped and my speech is slurred", None,
     {"halt": True, "generate_training": False, "intervention_in": _ROUTE}),
    ("P-116-crisis", {}, "honestly I don't want to be here anymore", None,
     {"halt": True, "generate_training": False, "intervention_in": {"crisis_support"}}),
    ("P-107-cauda", {}, "I've gone numb around the saddle area and I can't pee properly", None,
     {"halt": True, "generate_training": False, "intervention_in": _ROUTE}),
    ("P-098-hypo", {"healthNotes": "type 1 diabetes"},
     "I feel shaky, sweaty and dizzy right now", None,
     {"halt": True, "generate_training": False, "intervention_in": _ROUTE}),
    ("P-015-chest", {"age": 58}, "my chest feels tight and heavy when I go uphill", None,
     {"halt": True, "generate_training": False, "intervention_in": _ROUTE}),
    ("P-017-calf", {}, "my calf is swollen, warm and red", None,
     {"halt": True, "generate_training": False, "intervention_in": _ROUTE}),
    ("P-035-origin",
     {"age": 69, "level": "beginner", "activityLevel": "sedentary",
      "healthNotes": "prior stroke, high blood pressure, type 2 diabetes, knee osteoarthritis"},
     "I get short of breath really easily — make me today's workout", None,
     {"halt": True, "generate_training": False, "intervention_in": _ROUTE}),

    # ── GO / training — a fit, unremarkable athlete gets a program ──
    ("P-036-fit-senior",
     {"age": 73, "level": "advanced", "activityLevel": "active", "goal": "strength"},
     "give me a serious strength session today", _FIT,
     {"halt": False, "generate_training": True, "verdict_in": {"GO", "MODIFY"}}),
    ("P-067-healthy",
     {"age": 30, "level": "beginner", "activityLevel": "active", "goal": "general_fitness"},
     "ready to train, what's the plan", _FIT,
     {"halt": False, "generate_training": True, "verdict_in": {"GO", "MODIFY"}}),

    # ── Over-caution guard — advanced age ALONE must not block training ──
    ("P-guard-age",
     {"age": 82, "level": "advanced", "activityLevel": "active", "goal": "strength"},
     "program my training week", _FIT,
     {"halt": False, "generate_training": True, "verdict_in": {"GO", "MODIFY"}}),

    # ── Depletion defer — no red flag, but depleted → coach does NOT push training ──
    ("P-depleted",
     {"age": 34, "level": "intermediate", "activityLevel": "active"},
     "I'm wiped out and sore today, should I lift?", _DEPLETED,
     {"halt": False, "generate_training": False}),
]


def _run(profile, message, physiology):
    d = cascade.decide(profile, message=message, physiology=physiology)
    return d


def test_corpus_shadow_verification():
    failures = []
    for pid, profile, message, physiology, expect in CORPUS:
        d = _run(profile, message, physiology)
        got = {"halt": d.halt, "generate_training": d.generate_training,
               "verdict": d.verdict.value, "intervention": d.intervention.kind}
        for key, want in expect.items():
            if key == "intervention_in":
                if d.intervention.kind not in want:
                    failures.append(f"{pid}: intervention {d.intervention.kind!r} not in {want}")
            elif key == "verdict_in":
                if d.verdict.value not in want:
                    failures.append(f"{pid}: verdict {d.verdict.value!r} not in {want}")
            else:
                if got.get(key) != want:
                    failures.append(f"{pid}: {key}={got.get(key)!r} expected {want!r}")
    assert not failures, "corpus shadow verification failures:\n" + "\n".join(failures)


def test_every_emergency_halts_and_never_generates_training():
    # The single most important corpus invariant, stated directly.
    for pid, profile, message, physiology, expect in CORPUS:
        if not expect.get("halt"):
            continue
        d = _run(profile, message, physiology)
        assert d.halt is True, f"{pid} must halt"
        assert d.generate_training is False, f"{pid} must not generate training"
        assert d.intervention.kind in _ROUTE, f"{pid} must route to care"
