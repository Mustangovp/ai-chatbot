"""
M1 — S1 Somatic Constraint Model unit tests, derived from the Validation Corpus.
Pure organ (no DB, no app). Covers: constraint mapping, the anti-infantilization
envelope guards (P-036/P-079), bilingual detection, dedupe, and sparse profiles.
"""
from brain.s1_constraints import build
from brain.types import ConstraintTier, ConstraintSet, Constraint


# ── P-035 origin case: stroke + hypertension + diabetes + joint pain ──────────
def test_p035_multimorbid_narrow_and_supported():
    profile = {"age": 69, "level": "beginner", "activityLevel": "sedentary",
               "healthNotes": "prior stroke, high blood pressure, diabetes, joint pain"}
    cset, env = build(profile)
    assert cset.forbids("valsalva")            # hypertension + stroke
    assert cset.forbids("maximal_exertion")    # stroke history (absolute)
    assert env.supported is True               # balance-supported required
    assert env.intensity_ceiling < 0.5         # narrow envelope


# ── P-036 fit 73yo: no constraints, trained/active → WIDE (anti-infantilization)
def test_p036_fit_elderly_wide_envelope():
    profile = {"age": 73, "level": "advanced", "activityLevel": "active", "healthNotes": ""}
    cset, env = build(profile)
    assert cset.is_empty()                     # no invented constraints
    assert env.intensity_ceiling >= 0.85       # wide despite age 73
    assert env.supported is False


# ── P-079 Deaf, healthy: NO constraints invented ─────────────────────────────
def test_p079_no_invented_constraints():
    profile = {"age": 31, "level": "advanced", "activityLevel": "active"}
    cset, env = build(profile)
    assert cset.is_empty()
    assert env.intensity_ceiling >= 0.85


# ── P-040 osteoporosis: loaded spinal flexion absolutely forbidden ───────────
def test_p040_osteoporosis_forbids_loaded_flexion():
    cset, _ = build({"healthNotes": "diagnosed with osteoporosis"})
    assert cset.forbids("loaded_spinal_flexion")


# ── P-085 stroke + hypertension: Valsalva forbidden ──────────────────────────
def test_p085_stroke_htn_forbids_valsalva():
    cset, _ = build({"healthNotes": "stroke survivor, hypertension"})
    assert cset.forbids("valsalva")


# ── Bilingual: Bulgarian "инсулт" (stroke) is detected ───────────────────────
def test_bilingual_bg_stroke_detected():
    cset, env = build({"age": 66, "healthNotes": "прекаран инсулт, високо кръвно"})
    assert cset.forbids("valsalva")
    assert cset.forbids("maximal_exertion")
    assert env.supported is True


# ── Sparse profile: empty set, low confidence, never raises ──────────────────
def test_sparse_profile_low_confidence():
    cset, env = build({})
    assert cset.is_empty()
    assert env.confidence == 0.0
    assert 0.0 <= env.intensity_ceiling <= 1.0


# ── ConstraintSet keeps the STRICTEST tier per movement ──────────────────────
def test_constraintset_dedupe_keeps_strictest():
    cs = ConstraintSet()
    cs.add(Constraint("valsalva", ConstraintTier.RELATIVE, "x"))
    cs.add(Constraint("valsalva", ConstraintTier.ABSOLUTE, "y"))
    assert cs.forbids("valsalva")                       # absolute won
    assert len(cs.items) == 1                            # not duplicated


# ── Confidence rises with profile completeness ───────────────────────────────
def test_confidence_tracks_completeness():
    sparse = build({"age": 40})[1].confidence
    full = build({"age": 40, "level": "intermediate", "activityLevel": "moderate",
                  "equipment": "gym", "goal": "strength", "healthNotes": "none"})[1].confidence
    assert full > sparse
