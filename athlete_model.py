"""
APEX — The Athlete Model.

Computational physiology and behavioral state estimation for ONE human.
Not memory, not prompts, not chat history: a continuously evolving internal
model that is the single source of truth for the entire application. The
coach reads it (workout, nutrition, recovery, conversation), the organism
reads it (presence), the UI reads it (readout). Nothing else re-derives
what lives here.

Design laws (from the frozen blueprint):
  • Every variable evolves continuously and decays naturally — implemented as
    analytic exponential relaxation toward a resting baseline, integrated
    lazily over elapsed time on every read (no daemon required, no ticks lost).
  • Values increase only from evidence, and evidence steps are BOUNDED
    (MAX_STEP): no single observation — and therefore no UI event — can ever
    make a variable jump.
  • Every variable exposes confidence, and confidence is CEILINGED by the
    provenance tier of its evidence (reported < observed < measured): the
    model cannot become more certain than its instruments allow.
  • Confidence decays independently of value: knowledge goes stale even when
    the world doesn't change.
  • Pure functions over a JSON-serializable state dict. No I/O in this module;
    persistence and transport belong to the caller.
"""
import math
import datetime as _dt

SCHEMA = "athlete-model-v1"

# A single observation may move a variable at most this fraction of the way
# to its evidence target. This is the "never jump" law, mechanized.
MAX_STEP = 0.25

# Provenance tiers → confidence ceilings (blueprint law L3).
TIERS = {"measured": 0.98, "observed": 0.90, "reported": 0.65, "inferred": 0.50}

# ── The 13 estimated variables ────────────────────────────────────────────────
# base: resting point the value relaxes toward.
# tau:  value relaxation time constant, hours.
# ctau: confidence staleness time constant, hours.
VARS = {
    "physical_fatigue":    dict(base=0.20, tau=36.0,    ctau=72.0),
    "mental_fatigue":      dict(base=0.25, tau=24.0,    ctau=72.0),
    "motivation":          dict(base=0.50, tau=120.0,   ctau=168.0),
    "confidence":          dict(base=0.45, tau=336.0,   ctau=336.0),   # self-efficacy
    "consistency":         dict(base=0.35, tau=240.0,   ctau=240.0),
    "recovery_capacity":   dict(base=0.55, tau=720.0,   ctau=504.0),
    "stress":              dict(base=0.35, tau=72.0,    ctau=96.0),
    "adaptation":          dict(base=0.40, tau=720.0,   ctau=504.0),
    "adherence":           dict(base=0.40, tau=240.0,   ctau=240.0),
    "sleep_quality":       dict(base=0.55, tau=96.0,    ctau=120.0),
    "nutrition_quality":   dict(base=0.50, tau=168.0,   ctau=168.0),
    # Meta-estimates: how well the model knows this athlete, and how boldly the
    # coach may prescribe. Recomputed from the evidence ledger, never observed.
    "learning_confidence": dict(base=0.05, tau=None,    ctau=None),
    "coaching_confidence": dict(base=0.10, tau=None,    ctau=None),
}

_META = ("learning_confidence", "coaching_confidence")

# Self-report value maps (tier: reported — ceiling 0.65 by construction).
_SLEEP_MAP = {"good": 0.85, "average": 0.50, "ok": 0.50, "poor": 0.20}
_STRESS_MAP = {"low": 0.20, "moderate": 0.45, "high": 0.80}
_RECOVERY_MAP = {"fresh": 0.80, "ok": 0.55, "tired": 0.30}


# ── Time helpers ──────────────────────────────────────────────────────────────
def _now():
    return _dt.datetime.now(_dt.timezone.utc)

def _iso(t):
    return t.isoformat()

def _parse(s):
    try:
        d = _dt.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
    except Exception:
        return None

def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


# ── State construction ────────────────────────────────────────────────────────
def fresh_state(now=None):
    now = now or _now()
    return {
        "schema": SCHEMA,
        "updated_at": _iso(now),
        "vars": {
            name: {"value": spec["base"], "confidence": 0.0, "provenance": {}}
            for name, spec in VARS.items()
        },
        # Slow context the update laws need (not estimates — bookkeeping).
        "context": {
            "planned_frequency": None,     # sessions/week the athlete committed to
            "last_workout_at": None,
            "rate_ema": None,              # observed sessions/week, EMA
            "last_weights": {},            # exercise → last seen working weight
        },
        # Evidence ledger for the meta-estimates.
        "evidence": {"count": 0, "sources": {}, "last_at": None},
    }


# ── Continuous evolution: analytic decay, integrated lazily ──────────────────
def integrate(state, now=None):
    """Advance the model to `now`. Values relax toward baseline; confidence
    goes stale. Closed-form exponentials, so arbitrary gaps integrate exactly."""
    now = now or _now()
    then = _parse(state.get("updated_at")) or now
    dt_h = max(0.0, (now - then).total_seconds() / 3600.0)
    if dt_h > 0:
        for name, spec in VARS.items():
            if name in _META:
                continue
            v = state["vars"][name]
            if spec["tau"]:
                k = math.exp(-dt_h / spec["tau"])
                v["value"] = spec["base"] + (v["value"] - spec["base"]) * k
            if spec["ctau"]:
                v["confidence"] *= math.exp(-dt_h / spec["ctau"])
        state["updated_at"] = _iso(now)
    _recompute_meta(state, now)
    return state


# ── Evidence application (bounded, provenance-ceilinged) ─────────────────────
def _nudge(state, name, target, weight, tier, source, now):
    """Move `name` toward `target` by a BOUNDED step; raise confidence toward
    the provenance ceiling; record provenance. The only way values change."""
    v = state["vars"][name]
    w = _clamp(weight, 0.0, MAX_STEP)
    v["value"] = _clamp(v["value"] + (target - v["value"]) * w)
    ceil = TIERS.get(tier, TIERS["inferred"])
    v["confidence"] = min(ceil, v["confidence"] + (ceil - v["confidence"]) * w * 0.6)
    prov = v.setdefault("provenance", {})
    p = prov.setdefault(source, {"count": 0, "tier": tier})
    p["count"] += 1
    p["tier"] = tier
    p["last"] = _iso(now)

def _evidence(state, source, now):
    ev = state["evidence"]
    ev["count"] += 1
    ev["sources"][source] = ev["sources"].get(source, 0) + 1
    ev["last_at"] = _iso(now)


def observe(state, fact, payload=None, now=None):
    """Apply one server-verified fact. Vocabulary is the world's:
       workout_completed · self_report · exchange · nutrition_plan_issued.
    Integrates time first, so evidence lands on a current model."""
    payload = payload or {}
    now = now or _now()
    # No time travel: backfilled history may not rewind the clock, but its
    # evidence still counts (applied at the model's current time).
    cur = _parse(state.get("updated_at"))
    if cur and now < cur:
        now = cur
    integrate(state, now)
    ctx = state["context"]

    if fact == "workout_completed":
        exercises = payload.get("exercises") or []
        sets = 0
        for ex in exercises:
            try:
                sets += int(str(ex.get("sets", "0")).strip() or 0)
            except (ValueError, TypeError):
                sets += 3
        load = _clamp(0.15 + sets * 0.05, 0.0, 0.9)
        # Effort costs — fatigue rises with load (observed: the session is real data).
        _nudge(state, "physical_fatigue", 1.0, load * 0.4, "observed", "workout", now)
        # Showing up is motivation evidence; finishing is self-efficacy evidence.
        _nudge(state, "motivation", 0.90, 0.12, "observed", "workout", now)
        _nudge(state, "confidence", 0.85, 0.10, "observed", "workout", now)
        # Behavioral rhythm: observed rate vs committed frequency.
        last = _parse(ctx.get("last_workout_at"))
        if last:
            gap_d = max((now - last).total_seconds() / 86400.0, 0.05)
            inst_rate = min(7.0 / gap_d, 7.0)
            ctx["rate_ema"] = inst_rate if ctx.get("rate_ema") is None \
                else 0.70 * ctx["rate_ema"] + 0.30 * inst_rate
        ctx["last_workout_at"] = _iso(now)
        planned = ctx.get("planned_frequency")
        if planned and ctx.get("rate_ema") is not None:
            ratio = _clamp(ctx["rate_ema"] / max(planned, 0.5))
            _nudge(state, "consistency", ratio, 0.20, "observed", "workout", now)
            _nudge(state, "adherence",   ratio, 0.18, "observed", "workout", now)
            # Chronic over-rate is mental-load evidence (inferred, low ceiling).
            if ctx["rate_ema"] > planned * 1.25:
                _nudge(state, "mental_fatigue", 0.75, 0.08, "inferred", "overrate", now)
        # Adaptation: progression on a lift the model has seen before.
        progressed = False
        for ex in exercises:
            name = (ex.get("name") or "").strip().lower()
            try:
                w = float(str(ex.get("weight", "")).replace(",", "."))
            except (ValueError, TypeError):
                continue
            if not name or w <= 0:
                continue
            prev = ctx["last_weights"].get(name)
            if prev is not None and w > prev:
                progressed = True
            ctx["last_weights"][name] = w
        if len(ctx["last_weights"]) > 40:                      # bounded context
            for k in list(ctx["last_weights"])[:-40]:
                del ctx["last_weights"][k]
        if progressed:
            _nudge(state, "adaptation", 0.80, 0.15, "observed", "progression", now)
            _nudge(state, "confidence", 0.90, 0.10, "observed", "progression", now)
        _evidence(state, "workout", now)

    elif fact == "self_report":
        sleep = _SLEEP_MAP.get(str(payload.get("sleepQuality", "")).lower())
        stress = _STRESS_MAP.get(str(payload.get("stressLevel", "")).lower())
        recov = _RECOVERY_MAP.get(str(payload.get("recoveryFeel", "")).lower())
        if sleep is not None:
            _nudge(state, "sleep_quality", sleep, 0.22, "reported", "self_report", now)
        if stress is not None:
            _nudge(state, "stress", stress, 0.22, "reported", "self_report", now)
            _nudge(state, "mental_fatigue", stress, 0.10, "reported", "self_report", now)
        if sleep is not None or recov is not None:
            # Recovery capacity is a trait: it moves slowly, from repeated reports.
            parts, tot = [], 0.0
            if sleep is not None:
                parts.append(sleep * 0.6); tot += 0.6
            if recov is not None:
                parts.append(recov * 0.4); tot += 0.4
            _nudge(state, "recovery_capacity", sum(parts) / tot, 0.08,
                   "reported", "self_report", now)
        try:
            freq = int(str(payload.get("frequency", "")).strip())
            if 1 <= freq <= 7:
                ctx["planned_frequency"] = freq
        except (ValueError, TypeError):
            pass
        _evidence(state, "self_report", now)

    elif fact == "exchange":
        # Engagement is weak motivation evidence — deliberately tiny weight.
        _nudge(state, "motivation", 0.70, 0.03, "observed", "exchange", now)
        _evidence(state, "exchange", now)

    elif fact == "nutrition_plan_issued":
        # HONEST: a plan existing is not intake data. Inferred tier (ceiling
        # 0.50) — nutrition confidence stays low until real intake evidence exists.
        _nudge(state, "nutrition_quality", 0.60, 0.08, "inferred", "plan_issued", now)
        _evidence(state, "nutrition", now)

    _recompute_meta(state, now)
    return state


# ── Meta-estimates: the model's knowledge of its own knowledge ────────────────
def _recompute_meta(state, now):
    ev = state["evidence"]
    n = ev["count"]
    diversity = len(ev["sources"])
    last = _parse(ev.get("last_at"))
    fresh = math.exp(-((now - last).total_seconds() / 3600.0) / 336.0) if last else 0.0
    learning = (1 - math.exp(-n / 40.0)) * (0.4 + 0.6 * min(diversity, 4) / 4.0) * (0.3 + 0.7 * fresh)
    lv = state["vars"]["learning_confidence"]
    lv["value"] = round(_clamp(learning), 4)
    lv["confidence"] = lv["value"]          # a confidence IS its own confidence
    # Coaching confidence: knowing the athlete × trusting the actionable estimates.
    act = [state["vars"][k]["confidence"] for k in
           ("physical_fatigue", "consistency", "adherence", "sleep_quality")]
    cv = state["vars"]["coaching_confidence"]
    cv["value"] = round(_clamp(learning * (0.4 + 0.6 * (sum(act) / len(act)))), 4)
    cv["confidence"] = cv["value"]


# ── Projections: single source of truth, many readers ────────────────────────
def project_physiology(state):
    """The organism's somatic picture {recovery, fatigue, stress} — the ONE
    mapping, computed server-side so no client re-derives it."""
    V = state["vars"]
    fatigue = V["physical_fatigue"]["value"]
    stress = V["stress"]["value"]
    recovery = _clamp(V["recovery_capacity"]["value"] * 0.45
                      + (1 - fatigue) * 0.35
                      + V["sleep_quality"]["value"] * 0.20)
    conf = (V["physical_fatigue"]["confidence"] + V["stress"]["confidence"]
            + V["sleep_quality"]["confidence"]) / 3.0
    return {"recovery": round(recovery, 3), "fatigue": round(fatigue, 3),
            "stress": round(stress, 3), "confidence": round(conf, 3)}


def public_view(state):
    """The API shape: every variable with value, confidence and dominant provenance."""
    out = {}
    for name, v in state["vars"].items():
        dom = None
        if v.get("provenance"):
            dom = max(v["provenance"].items(), key=lambda kv: kv[1]["count"])[0]
        out[name] = {"value": round(v["value"], 3),
                     "confidence": round(v["confidence"], 3),
                     "source": dom}
    return out


def coach_signals(state):
    """Confidence-gated signals for the Personality Engine — replaces its own
    re-derivation from raw workouts (one model, no duplicated logic).
    Low-confidence estimates are withheld: unknown, not guessed."""
    V = state["vars"]
    sig = {}
    c = V["consistency"]
    if c["confidence"] >= 0.35:
        sig["consistency"] = ("disciplined" if c["value"] >= 0.65
                              else "inconsistent" if c["value"] < 0.40 else "steady")
    f, s, m = V["physical_fatigue"], V["sleep_quality"], V["mental_fatigue"]
    if (f["confidence"] >= 0.40 and f["value"] > 0.70) or \
       (s["confidence"] >= 0.40 and s["value"] < 0.30) or \
       (m["confidence"] >= 0.40 and m["value"] > 0.75):
        sig["exhausted"] = True
    sig["coaching_confidence"] = V["coaching_confidence"]["value"]
    return sig


_LABELS_EN = {
    "physical_fatigue": "Physical fatigue", "mental_fatigue": "Mental fatigue",
    "motivation": "Motivation", "confidence": "Self-efficacy",
    "consistency": "Consistency", "recovery_capacity": "Recovery capacity",
    "stress": "Stress", "adaptation": "Training adaptation",
    "adherence": "Adherence", "sleep_quality": "Sleep quality",
    "nutrition_quality": "Nutrition quality",
    "learning_confidence": "Model knowledge of athlete",
    "coaching_confidence": "Coaching confidence",
}

def prompt_block(state, lang="en"):
    """The [ATHLETE MODEL] block the coach reads before every reply. Estimates
    below the confidence floor are rendered as UNKNOWN — the coach must ask,
    never assume (honesty law)."""
    en = str(lang).lower() == "en"
    head = ("[ATHLETE MODEL — live estimates. LOW-CONFIDENCE = UNKNOWN: ask, never assume.]"
            if en else
            "[МОДЕЛ НА АТЛЕТА — живи оценки. НИСКА УВЕРЕНОСТ = НЕИЗВЕСТНО: питай, не предполагай.]")
    lines = [head]
    for name in VARS:
        v = state["vars"][name]
        label = _LABELS_EN[name]
        if v["confidence"] < 0.25 and name not in _META:
            lines.append(f"  {label}: UNKNOWN (insufficient evidence)")
        else:
            dom = None
            if v.get("provenance"):
                dom = max(v["provenance"].items(), key=lambda kv: kv[1]["count"])[1]["tier"]
            src = f", {dom}" if dom else ""
            lines.append(f"  {label}: {v['value']:.2f} (confidence {v['confidence']:.2f}{src})")
    rule = ("  RULE: scale prescription boldness to Coaching confidence. Never state an "
            "UNKNOWN as fact." if en else
            "  ПРАВИЛО: мащабирай смелостта на предписанията според увереността. Никога не "
            "твърди НЕИЗВЕСТНО като факт.")
    lines.append(rule)
    return "\n".join(lines)
