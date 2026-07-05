"""
APEX Brain — Constraint Library (S1 data).

Maps stated conditions/medications/injuries → MOVEMENT constraints (never
diagnoses). The mappings are transcribed from the FROZEN canon (Brain
Architecture §2/S1 and the Validation Corpus), expressed as movements and
intensities exactly as those documents specify.

⚠ SEED — CLINICAL REVIEW REQUIRED BEFORE M4 ENFORCEMENT.
This is a conservative starter set. Per the Brain Architecture governance and
the Final Review finding M-5, the library must carry a named clinical
reviewer's sign-off and a versioned change log before it gates any real
prescription. It is used SHADOW-ONLY (BRAIN_SHADOW) until then, so it never
reaches a user in M1. Additions are data changes, hot-fixable without code.

Detection is a conservative bilingual (EN/BG) substring matcher over the free
text profile field `healthNotes` (legacy: `injuries`). Recall/precision tuning
and bilingual coverage expansion are documented pre-M4 work (Review H-2/H-3).
"""
from brain.types import Constraint, ConstraintTier as T

LIBRARY_VERSION = "seed-2026-07-05"

_A, _R, _M = T.ABSOLUTE, T.RELATIVE, T.MONITOR

# condition key → movement constraints
CONSTRAINT_LIBRARY: dict[str, list[Constraint]] = {
    "hypertension": [
        Constraint("valsalva", _A, "avoid_breath_holding"),
        Constraint("heavy_isometric", _R, "avoid_bp_spike"),
        Constraint("maximal_exertion", _R, "avoid_bp_spike"),
        Constraint("inversion", _R, "avoid_bp_spike"),
    ],
    "stroke_history": [
        Constraint("maximal_exertion", _A, "avoid_bp_spike"),
        Constraint("valsalva", _A, "avoid_breath_holding"),
        Constraint("unsupported_balance", _R, "balance_safety"),
    ],
    "cardiac_condition": [
        Constraint("maximal_exertion", _R, "cardiac_caution"),
        Constraint("valsalva", _R, "avoid_breath_holding"),
    ],
    "osteoporosis": [
        Constraint("loaded_spinal_flexion", _A, "bone_load_caution"),
        Constraint("loaded_spinal_twist", _R, "bone_load_caution"),
        Constraint("high_impact", _R, "bone_load_caution"),
    ],
    "knee_pain": [
        Constraint("high_impact", _R, "joint_pain_free_range"),
        Constraint("deep_loaded_knee_flexion", _R, "joint_pain_free_range"),
    ],
    "joint_pain": [
        Constraint("high_impact", _R, "joint_pain_free_range"),
        Constraint("heavy_loaded_end_range", _M, "joint_pain_free_range"),
    ],
    "back_pain": [
        Constraint("loaded_spinal_flexion", _R, "spine_pain_free_range"),
        Constraint("heavy_hinge", _R, "spine_pain_free_range"),
    ],
    "anticoagulant": [
        Constraint("contact_collision", _R, "bleed_fall_caution"),
        Constraint("high_fall_risk", _R, "bleed_fall_caution"),
    ],
    "pregnancy": [
        Constraint("maximal_exertion", _R, "provider_led"),
        Constraint("valsalva", _R, "provider_led"),
        Constraint("contact_fall_risk", _R, "provider_led"),
        Constraint("prolonged_supine", _M, "provider_led"),
    ],
    "diabetes_neuropathy": [
        Constraint("high_impact", _R, "foot_protection"),
    ],
    "falls_risk": [
        Constraint("unsupported_balance", _R, "balance_safety"),
    ],
}

# free-text token (lowercase) → condition key. Bilingual EN/BG. Conservative.
CONDITION_TOKENS: dict[str, str] = {
    # hypertension
    "hypertension": "hypertension", "high blood pressure": "hypertension",
    "хипертония": "hypertension", "високо кръвно": "hypertension", "кръвно налягане": "hypertension",
    # stroke
    "stroke": "stroke_history", "инсулт": "stroke_history", "мозъчен удар": "stroke_history",
    # cardiac
    "heart attack": "cardiac_condition", "heart disease": "cardiac_condition",
    "cardiac": "cardiac_condition", "angina": "cardiac_condition",
    "инфаркт": "cardiac_condition", "сърдечно": "cardiac_condition", "стенокардия": "cardiac_condition",
    # osteoporosis
    "osteoporosis": "osteoporosis", "osteopenia": "osteoporosis", "остеопороза": "osteoporosis",
    # knee
    "knee pain": "knee_pain", "knee arthritis": "knee_pain", "knee osteoarthritis": "knee_pain",
    "болка в коляно": "knee_pain", "коляно": "knee_pain", "колене": "knee_pain",
    # general joints
    "arthritis": "joint_pain", "joint pain": "joint_pain",
    "артрит": "joint_pain", "ставна болка": "joint_pain", "стави": "joint_pain",
    # back
    "back pain": "back_pain", "lower back": "back_pain",
    "болки в гърба": "back_pain", "кръст": "back_pain",
    # anticoagulant
    "blood thinner": "anticoagulant", "anticoagulant": "anticoagulant", "warfarin": "anticoagulant",
    "разредител на кръвта": "anticoagulant", "антикоагулант": "anticoagulant",
    # pregnancy
    "pregnant": "pregnancy", "pregnancy": "pregnancy", "бременна": "pregnancy", "бременност": "pregnancy",
    # diabetic neuropathy
    "neuropathy": "diabetes_neuropathy", "numb feet": "diabetes_neuropathy", "невропатия": "diabetes_neuropathy",
    # falls / balance
    "falls": "falls_risk", "fallen": "falls_risk", "падам": "falls_risk", "падания": "falls_risk",
}


def detect_conditions(text: str) -> set[str]:
    """Conservative bilingual substring detection of condition keys in free text.
    Over-matching biases toward MORE constraints (safe in shadow)."""
    low = (text or "").lower()
    found = set()
    for token, key in CONDITION_TOKENS.items():
        if token in low:
            found.add(key)
    return found


def constraints_for(key: str) -> list[Constraint]:
    return CONSTRAINT_LIBRARY.get(key, [])
