"""
APEX Brain — Red-Flag Library (S2 data).

Maps reported SYMPTOM patterns → an urgency-typed routing RedFlag (never a
diagnosis). Every entry is a route + tier, per Brain Architecture §2/§6 and the
verified GAP-α (urgency) / GAP-β (psychological crisis).

⚠ SEED — CLINICAL REVIEW + BILINGUAL EXPANSION REQUIRED BEFORE M4 ENFORCEMENT
(build-time obligations register, items 1–2). Conservative, deterministic,
bilingual (EN/BG) cluster matcher — like the S1 constraint library. Used
SHADOW-ONLY until then, so it never reaches a user in M2/M3. Detection biases
toward flagging on ambiguity (§3 asymmetric-loss / audit R4).

Determinism: a `class_key` fires iff any of its patterns matches; a pattern
matches iff EVERY token-group in it has ≥1 token present in the text (clusters,
not single classic tokens). No LLM in this path.
"""
from brain.types import RedFlag, Urgency

LIBRARY_VERSION = "redflag-seed-2026-07-05"
_E, _U, _R = Urgency.EMERGENCY, Urgency.URGENT, Urgency.ROUTINE

# class_key → (urgency, route_target, message_key). class_key + message_key are
# INTERNAL; only a curated non-diagnostic template is ever rendered (via G1).
REDFLAG_SPECS = {
    # ── EMERGENCY ──
    "fast_stroke":            (_E, "emergency_services", "stroke_signs_emergency"),
    "cauda_equina":           (_E, "emergency_services", "spinal_emergency"),
    "autonomic_dysreflexia":  (_E, "emergency_services", "autonomic_emergency"),
    "rhabdomyolysis":         (_E, "emergency_services", "muscle_kidney_emergency"),
    "acute_hypoglycaemia":    (_E, "stop_and_treat",     "treat_low_blood_sugar_now"),
    "psych_crisis":           (_E, "crisis_support",     "crisis_support"),
    # ── URGENT ──
    "exertional_chest":       (_U, "clinician_prompt",   "chest_needs_doctor"),
    "unilateral_calf":        (_U, "clinician_prompt",   "leg_needs_doctor"),
    "syncope":                (_U, "clinician_prompt",   "fainting_needs_doctor"),
    "arrhythmia":             (_U, "clinician_prompt",   "palpitations_need_doctor"),
    "new_neuro_deficit":      (_U, "clinician_prompt",   "numbness_weakness_needs_doctor"),
    "worsening_dyspnea":      (_U, "clinician_prompt",   "breathlessness_needs_doctor"),
    "severe_bp":              (_U, "clinician_prompt",   "high_bp_reading_needs_doctor"),
    # ── ROUTINE (soft) ──
    "persistent_low_mood":    (_R, "gp_soft",            "low_mood_worth_support"),
    "disproportionate_fatigue": (_R, "gp_soft",          "fatigue_worth_checking"),
}

# class_key → list of patterns; pattern → list of token-groups (all groups must hit).
CLUSTERS = {
    "fast_stroke": [
        [["face droop", "facial droop", "face drooping", "drooping on one side", "face has drooped",
          "изкривено лице", "провисна", "увиснало лице", "провиснало лице"]],
        [["arm weak", "weak arm", "arm's gone weak", "arm has gone weak", "arm went weak",
          "ръката ми отслабна", "слабост в ръката", "отслабна ръка"],
         ["speech", "slurred", "slur", "говор", "заваля", "неясен говор"]],
    ],
    "cauda_equina": [
        [["saddle", "groin", "perineal", "inner thigh", "слабини", "чатала", "седалищна"],
         ["numb", "numbness", "tingl", "изтръпва", "изтръпване"],
         ["bladder", "urinat", "peeing", "pee", "passing urine", "уриниране", "пикоч", "до тоалетна"]],
    ],
    "autonomic_dysreflexia": [
        [["pounding headache", "severe headache", "banging headache", "силно главоболие", "пулсиращо главоболие"],
         ["sweating", "flushed", "flushing", "sweaty above", "изпотяване", "зачервяване", "поти се"]],
    ],
    "rhabdomyolysis": [
        [["dark urine", "cola", "brown pee", "brown urine", "dark brown", "тъмна урина", "кафява урина", "цвят на кола"]],
    ],
    "acute_hypoglycaemia": [
        [["shaky", "shaking", "trembling", "треперя", "разтреперан"],
         ["sweaty", "sweating", "изпотен", "в пот", "изпотяване"],
         ["dizzy", "foggy", "confused", "light-headed", "lightheaded", "замая", "замаян", "обърканост"]],
    ],
    "psych_crisis": [
        [["don't want to be here", "do not want to be here", "not want to be here", "don't want to live",
          "don't want to be alive", "better off gone", "better off dead", "end it all", "kill myself",
          "suicid", "take my own life", "no point in living",
          "не искам да съм тук", "не искам да живея", "да сложа край", "да свърша със себе си", "самоуб"]],
    ],
    "exertional_chest": [
        [["chest", "гърди", "гръд"],
         ["tight", "pressure", "heavy", "pain", "tightness", "стяга", "натиск", "тежест", "болка"]],
    ],
    "unilateral_calf": [
        [["calf", "leg", "прасец", "крак"],
         ["swollen", "swelling", "подут", "отекъл", "оток"],
         ["warm", "hot", "red", "painful", "achy", "aching", "топъл", "зачервен", "болезнен"]],
    ],
    "syncope": [
        [["faint", "fainting", "pass out", "passed out", "black out", "blacking out", "syncope",
          "nearly fainted", "припадък", "прималя", "да припадна", "загуба на съзнание"]],
    ],
    "arrhythmia": [
        [["palpitation", "racing heart", "heart races", "heart racing", "skipping", "skip", "flutter",
          "fluttering", "pounding heart", "сърцебиене", "прескача", "ускорен пулс", "тупти"],
         ["dizzy", "light-headed", "lightheaded", "faint", "замая", "прималя", "световъртеж"]],
    ],
    "new_neuro_deficit": [
        [["numb", "numbness", "tingl", "изтръпва", "изтръпване"],
         ["weak", "weakness", "grip", "слаб", "слабост"]],
    ],
    "worsening_dyspnea": [
        [["short of breath", "shortness of breath", "breathless", "out of breath", "can't breathe",
          "задух", "недостиг на въздух", "задъхвам", "трудно дишане"]],
    ],
    "severe_bp": [
        [["blood pressure", "bp", "кръвно"],
         ["headache", "главоболие"],
         ["high", "very high", "180", "190", "200", "210", "висок", "много високо"]],
    ],
    "persistent_low_mood": [
        [["low", "empty", "flat", "tearful", "no joy", "no interest", "anhedonia", "hopeless", "depress",
          "потиснат", "празен", "без настроение", "без интерес", "без радост", "плача"],
         ["weeks", "months", "every day", "most days", "all the time",
          "седмици", "месеци", "всеки ден", "постоянно"]],
    ],
    "disproportionate_fatigue": [
        [["exhausted", "tired all the time", "drained", "no energy", "wiped out",
          "изтощен", "постоянно уморен", "без енергия"],
         ["weeks", "months", "getting worse", "worse", "седмици", "месеци", "влошава"]],
    ],
}


def _pattern_hit(text: str, pattern: list) -> bool:
    return all(any(tok in text for tok in group) for group in pattern)


def detect_flag_classes(text: str) -> list:
    """Deterministic, conservative, bilingual detection of red-flag class keys."""
    low = (text or "").lower()
    return [cls for cls, patterns in CLUSTERS.items()
            if any(_pattern_hit(low, p) for p in patterns)]


def flag_for(class_key: str, source: str = "message") -> RedFlag:
    urgency, target, mkey = REDFLAG_SPECS[class_key]
    return RedFlag(class_key=class_key, urgency=urgency, route_target=target,
                   message_key=mkey, source=source)
