"""
APEX Brain — Station S2: Readiness + the Red-Flag Sentinel.

Distinguishes trait (S1: who they are) from state (how they are today) and scans
for signals that outrank the training question. Pure function — no Flask, no DB,
no OpenAI. In M2 this runs SHADOW-ONLY.

Carries the frozen refinements:
  • GAP-α — every RedFlag is urgency-typed (EMERGENCY / URGENT / ROUTINE) with a
    route_target (Brain Architecture / Addendum 01).
  • GAP-β — the psychological-crisis class is in the catalogue.
  • Addendum 02 A2-1 — the symptom scan reads the CURRENT message *and the recent
    conversation window*, so a red flag disclosed in a prior turn still fires.
  • Addendum 02 A2-0 — the SENTINEL sets `halt` structurally: EMERGENCY always
    halts; URGENT halts a prescription request. The cascade (built later) treats a
    halt as terminal — S4's GO/MODIFY branches are unreachable when halted.

Non-diagnosis (§6 / audit R7): the organ emits routing KEYS (class_key /
route_target / message_key), never user-facing prose — it cannot diagnose.
"""
from brain.types import S2State, Urgency
from brain.redflag_library import detect_flag_classes, flag_for


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _readiness(physiology):
    """Today's capacity + confidence, from the Athlete Model's somatic projection.
    Unknown physiology → mid value with ZERO confidence (biases downstream
    conservative, never an optimistic guess — §2)."""
    if not physiology:
        return 0.5, 0.0
    rec = float(physiology.get("recovery", 0.5))
    fat = float(physiology.get("fatigue", 0.3))
    stress = float(physiology.get("stress", 0.3))
    r = _clamp(rec * 0.6 + (1.0 - fat) * 0.4 - stress * 0.1)
    return round(r, 3), round(float(physiology.get("confidence", 0.0)), 3)


def assess(*, message=None, conversation=None, profile=None, physiology=None, is_prescription=True) -> S2State:
    """Scan for red flags over the message, recent conversation window, and structured Human State;
    compute readiness; set the structural halt."""
    readiness, conf = _readiness(physiology)
    flags, seen = [], set()

    def _scan(text, source):
        for cls in detect_flag_classes(text or ""):
            if cls in seen:
                continue
            seen.add(cls)
            flags.append(flag_for(cls, source))

    # 1. Scan message and conversation (for compatibility and test suite)
    _scan(message, "message")
    for m in (conversation or []):
        if isinstance(m, dict) and m.get("role") == "user":
            _scan(m.get("content"), "prior_turn")

    # 2. Scan structured profile red flags and health notes
    profile = profile or {}
    safety_classes = profile.get("red_flags") or []
    for cls in safety_classes:
        if cls not in seen:
            seen.add(cls)
            flags.append(flag_for(cls, "human_state"))

    hn = str(profile.get("healthNotes") or profile.get("injuries") or "")
    for cls in detect_flag_classes(hn):
        if cls not in seen:
            seen.add(cls)
            flags.append(flag_for(cls, "health_notes"))

    # Structural halt (Addendum 02 A2-0).
    has_emergency = any(f.urgency == Urgency.EMERGENCY for f in flags)
    has_urgent = any(f.urgency == Urgency.URGENT for f in flags)
    halt = has_emergency or (is_prescription and has_urgent)

    return S2State(readiness=readiness, readiness_conf=conf, red_flags=flags, halt=halt)
