"""
BUILD-001 — Conversation Extractor.

Deterministic, keyword/regex NL extraction: a message → list[Reading]. No LLM, no
Brain, no I/O. Conservative: emits a Reading only on a reasonably clear signal, with
a confidence reflecting how direct the statement is. EN-first with a little BG.

Covers: physical state / recovery / fatigue / pain / stress / sleep / nutrition /
motivation / confidence / schedule / time / equipment / environment / illness /
travel / goals / behavior / identity / habit / preference.
"""
import re

from human_state.schema import (Reading, CONF_NUMERIC, CONF_EXPLICIT, CONF_HEDGED,
                                 now_utc)

_BOUNDARY = {"to", "it", "the", "a", "an", "and", "or", "but", "now", "have", "so",
             "because", "when", "if", "really", "just", "today", "anymore", "for", "with"}


def _food(raw):
    out = []
    for w in re.split(r"[ \-]+", raw.strip().lower()):
        w = w.strip(" .,!?")
        if not w or w in _BOUNDARY:
            break
        out.append(w)
        if len(out) >= 2:
            break
    return " ".join(out).strip()


# (compiled pattern, key, value, confidence, optional note-group)
_RULES = [
    # ── sleep (numeric first = highest confidence) ──
    (re.compile(r"\bslept?\s+(?:only\s+)?(\d{1,2})\s*(?:hours?|hrs?|h)\b", re.I), "sleep", "num_hours", CONF_NUMERIC, 1),
    (re.compile(r"\b(didn'?t sleep|no sleep|couldn'?t sleep|barely slept|insomnia|poor sleep|bad sleep|slept terribly|sleep(?:ing)? badly|не спах|безсъние)\b", re.I), "sleep", "low", CONF_EXPLICIT, None),
    (re.compile(r"\b(slept (?:great|well|amazing)|well[- ]rested|good sleep|great sleep)\b", re.I), "sleep", "high", CONF_EXPLICIT, None),
    # ── fatigue / recovery ──
    (re.compile(r"\b(exhausted|wiped out|so tired|drained|knackered|no energy|running on empty|изтощен|нямам енергия)\b", re.I), "fatigue", "high", CONF_EXPLICIT, None),
    (re.compile(r"\b(tired|fatigued|worn out|sluggish|уморен)\b", re.I), "fatigue", "moderate", CONF_HEDGED, None),
    (re.compile(r"\b(fresh|recovered|full of energy|energi[sz]ed|energetic|well rested|feeling great)\b", re.I), "recovery", "high", CONF_EXPLICIT, None),
    # ── pain (with location note) ──
    (re.compile(r"\bmy?\s*(knee|back|lower back|shoulder|elbow|hip|neck|wrist|ankle|hamstring|quad|calf|foot)\b[^.]{0,20}?\b(hurts?|is sore|are sore|pain|aches?|aching|killing me)\b", re.I), "pain", "present", CONF_EXPLICIT, 1),
    (re.compile(r"\b(sharp pain|in pain|it hurts|really sore|so sore|болка|боли ме)\b", re.I), "pain", "present", CONF_EXPLICIT, None),
    # ── stress ──
    (re.compile(r"\b(stressed|overwhelmed|anxious|so much stress|under pressure|burn(?:t|ed) out|frazzled|стрес|претоварен)\b", re.I), "stress", "high", CONF_EXPLICIT, None),
    # ── nutrition ──
    (re.compile(r"\b(haven'?t eaten|skipped meals?|not eating|forgot to eat|binged|overate|ate (?:terribly|badly|junk)|too much junk)\b", re.I), "nutrition", "poor", CONF_EXPLICIT, None),
    (re.compile(r"\b(on a diet|dieting|cutting|in a deficit|eating clean|tracking macros)\b", re.I), "nutrition", "dieting", CONF_HEDGED, None),
    # ── motivation ──
    (re.compile(r"\b(no motivation|unmotivated|don'?t feel like|want to quit|feel like quitting|giving up|can'?t be bothered|losing interest|нямам мотивация|искам да се откажа)\b", re.I), "motivation", "low", CONF_EXPLICIT, None),
    (re.compile(r"\b(motivated|excited to train|pumped|fired up|ready to go|can'?t wait|мотивиран)\b", re.I), "motivation", "high", CONF_EXPLICIT, None),
    # ── confidence ──
    (re.compile(r"\b(i can'?t do (?:this|it)|not good at|i'?m terrible|no confidence|i suck|scared i'?ll fail|feel like a failure|не мога|провалих се)\b", re.I), "confidence", "low", CONF_EXPLICIT, None),
    (re.compile(r"\b(i can do this|feeling confident|nailed it|crushed it|so proud|felt strong)\b", re.I), "confidence", "high", CONF_EXPLICIT, None),
    # ── time availability (numeric) ──
    (re.compile(r"\b(?:only\s+(?:have|got)\s+)?(\d{1,3})\s*(?:min|mins|minute|minutes|минути)\b", re.I), "time_availability", "num_minutes", CONF_NUMERIC, 1),
    (re.compile(r"\b(no time|so busy|slammed|swamped|crazy busy|no free time|нямам време)\b", re.I), "time_availability", "low", CONF_EXPLICIT, None),
    # ── equipment ──
    (re.compile(r"\b(no equipment|no gym|bodyweight only|only bodyweight|just dumbbells|only (?:a )?(?:kettlebell|bands?|a barbell)|home gym|full gym|at the gym)\b", re.I), "equipment", "stated", CONF_EXPLICIT, 0),
    # ── environment ──
    (re.compile(r"\b(at home|home workout|hotel room|in a hotel|outdoors|outside|at the office|at a park|in the park)\b", re.I), "environment", "stated", CONF_EXPLICIT, 0),
    # ── illness ──
    (re.compile(r"\b(i'?m sick|have (?:the )?flu|a cold|fever|coming down with|not feeling well|under the weather|nauseous|sick today|болен съм|настинка|грип)\b", re.I), "illness", "present", CONF_EXPLICIT, None),
    # ── travel ──
    (re.compile(r"\b(travell?ing|on a trip|on the road|on vacation|on holiday|business trip|away for work|jet ?lag|пътувам|на почивка)\b", re.I), "travel", "present", CONF_EXPLICIT, None),
    # ── goals ──
    (re.compile(r"\b(?:want to|trying to|goal is to|i'?d like to)\s+(lose weight|lose fat|build muscle|gain muscle|get stronger|get fit|get lean|tone up|run a marathon)\b", re.I), "goals", "num_goal", CONF_EXPLICIT, 1),
    # ── behavior / adherence ──
    (re.compile(r"\bhaven'?t (?:trained|worked out|exercised|lifted)\s+(?:in|for)\s+(\d{1,2})\s*(days?|weeks?|months?)\b", re.I), "adherence", "gap", CONF_NUMERIC, 1),
    (re.compile(r"\b(missed|skipped)\s+(?:my|a|the|several|last|this week'?s)?\s*(?:workouts?|sessions?|training|the gym)\b", re.I), "adherence", "missed", CONF_EXPLICIT, None),
    (re.compile(r"\b(fell off|off track|been consistent|on a streak|kept it up|training regularly)\b", re.I), "adherence", "note", CONF_HEDGED, 1),
    # ── identity ──
    (re.compile(r"\bi'?m (?:a|an)\s+(runner|lifter|powerlifter|athlete|beginner|morning person|gym person)\b", re.I), "identity", "num_identity", CONF_EXPLICIT, 1),
    # ── habit ──
    (re.compile(r"\b(every (?:morning|day|evening|night)|i always|i usually|my routine is|part of my routine)\b", re.I), "habit", "note", CONF_HEDGED, 1),
]

# preference handled separately (needs the food term)
_PREF_AVOID = re.compile(r"\bi\s+(?:hate|can'?t stand|don'?t like|dislike)\s+([a-z][a-z \-]{1,30})", re.I)
_PREF_LIKE = re.compile(r"\bi\s+(?:love|really like|prefer|enjoy)\s+([a-z][a-z \-]{1,30})", re.I)


def extract(message, source="message", now=None):
    """Return a list of Readings extracted from `message`. Deterministic."""
    text = message or ""
    at = now or now_utc()
    out = []

    def add(key, value, conf, note=""):
        out.append(Reading(key=key, value=value, confidence=conf, source=source,
                           observed_at=at, note=str(note)[:120]))

    for pat, key, value, conf, note_grp in _RULES:
        m = pat.search(text)
        if not m:
            continue
        note = ""
        val = value
        if isinstance(value, str) and value.startswith("num_") and note_grp:
            val = m.group(note_grp)                    # the captured number/token becomes the value
        elif note_grp:
            try:
                note = m.group(note_grp) or ""
                if note_grp == 0:
                    note = m.group(0)
            except Exception:
                note = ""
        add(key, val, conf, note)

    for m in _PREF_AVOID.finditer(text):
        f = _food(m.group(1))
        if f:
            add("preference", {"avoid": f}, CONF_EXPLICIT, f)
    for m in _PREF_LIKE.finditer(text):
        f = _food(m.group(1))
        if f:
            add("preference", {"prefer": f}, CONF_EXPLICIT, f)

    # dedupe: keep the highest-confidence reading per key (deterministic)
    best = {}
    for r in out:
        if r.key == "preference":
            best[(r.key, r.note)] = r                   # keep each distinct preference
        else:
            cur = best.get(r.key)
            if cur is None or r.confidence > cur.confidence:
                best[r.key] = r
    return list(best.values())
