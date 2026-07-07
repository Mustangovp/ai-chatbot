"""
BUILD-004 — Human Trajectory Engine.

Trend analysis over EXISTING Human State history (the human_state_events audit log
from BUILD-002). Computes, per state variable and overall: trend / velocity /
volatility / trajectory / risk, and the recovery / adherence / confidence directions.
Pure analysis — no Brain, no new tables, no writes. Provided to the Adaptive Coach.
"""
import datetime as _dt

import db as store
from human_state.config import trajectory_enabled

# token → scalar per variable (numeric values handled separately). Absent keys are skipped.
_MAP = {
    "fatigue": {"high": 1.0, "moderate": 0.5, "low": 0.0},
    "stress": {"high": 1.0, "moderate": 0.5, "low": 0.0},
    "pain": {"present": 1.0},
    "recovery": {"high": 1.0, "low": 0.0},
    "motivation": {"high": 1.0, "moderate": 0.5, "low": 0.0},
    "confidence": {"high": 1.0, "low": 0.0},
    "adherence": {"note": 1.0, "missed": 0.0, "gap": 0.0},
    "sleep": {"high": 0.9, "low": 0.3},
    "sleep_debt": {"present": 1.0},
}
# +1 = higher is better (wellbeing), -1 = higher is worse.
_POLARITY = {"fatigue": -1, "stress": -1, "pain": -1, "sleep_debt": -1,
             "recovery": 1, "motivation": 1, "confidence": 1, "sleep": 1, "adherence": 1}
_EPS = 0.02          # velocity threshold (per day) for a direction call
_MIN_POINTS = 3


def enabled() -> bool:
    return trajectory_enabled()


def _scalar(key, value):
    try:
        n = float(value)
        return min(n / 8.0, 1.25) if key == "sleep" else None   # only numeric sleep is a trend var
    except (TypeError, ValueError):
        pass
    m = _MAP.get(key)
    return m.get(value) if m else None


def _aware(ts):
    if ts is None:
        return None
    if isinstance(ts, str):                       # hse_recent_events serializes datetimes to ISO
        try:
            ts = _dt.datetime.fromisoformat(ts)
        except ValueError:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_dt.timezone.utc)
    return ts


def series(subject, window_days=30, now=None):
    """Per-key time series {key: [(day_offset, scalar)]} from the audit history."""
    at = now or _dt.datetime.now(_dt.timezone.utc)
    cutoff = at - _dt.timedelta(days=window_days)
    events = store.hse_recent_events(limit=500, subject=subject)   # ascending by created_at
    out = {}
    for e in events:
        ts = _aware(e.get("created_at"))
        if ts is None or ts < cutoff:
            continue
        day = (ts - cutoff).total_seconds() / 86400.0
        for tr in (e.get("transitions") or []):
            k = tr.get("key")
            s = _scalar(k, tr.get("extracted_value"))
            if s is not None:
                out.setdefault(k, []).append((day, s))
    return out


def _slope(points):
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    denom = sum((p[0] - mx) ** 2 for p in points)
    if denom == 0:
        return 0.0
    return sum((p[0] - mx) * (p[1] - my) for p in points) / denom


def _stdev(points):
    n = len(points)
    m = sum(p[1] for p in points) / n
    return (sum((p[1] - m) ** 2 for p in points) / n) ** 0.5


def _direction(key, velocity):
    well = velocity * _POLARITY.get(key, 1)
    if well > _EPS:
        return "improving"
    if well < -_EPS:
        return "declining"
    return "stable"


def compute(subject, window_days=30, now=None):
    """Full trajectory. Deterministic; read-only."""
    try:
        ser = series(subject, window_days=window_days, now=now)
        per_key, well_vals = {}, []
        for k, pts in ser.items():
            if len(pts) < _MIN_POINTS:
                continue
            v = round(_slope(pts), 4)
            per_key[k] = {"points": len(pts), "velocity": v,
                          "volatility": round(_stdev(pts), 3), "direction": _direction(k, v)}
            well_vals.append(v * _POLARITY.get(k, 1))
        if not per_key:
            return {"ok": True, "sufficient": False, "per_key": {}, "trajectory": "unknown",
                    "recovery_direction": "unknown", "adherence_direction": "unknown",
                    "confidence_direction": "unknown", "risk": {"level": "unknown", "reasons": []}}

        def d(key):
            return per_key.get(key, {}).get("direction", "unknown")

        # per_key directions are already wellbeing-normalized (polarity applied), so
        # recovery direction mirrors fatigue's wellbeing direction (rising fatigue = declining).
        rec_dir = d("recovery") if "recovery" in per_key else (
            d("fatigue") if "fatigue" in per_key else "unknown")
        adh_dir, conf_dir = d("adherence"), d("confidence")

        avg_well = sum(well_vals) / len(well_vals)
        improving = sum(1 for w in well_vals if w > _EPS)
        declining = sum(1 for w in well_vals if w < -_EPS)
        if improving and declining:
            traj = "mixed"
        elif avg_well > _EPS:
            traj = "improving"
        elif avg_well < -_EPS:
            traj = "declining"
        else:
            traj = "stable"

        reasons = []
        if adh_dir == "declining":
            reasons.append("adherence declining")
        if rec_dir == "declining":
            reasons.append("recovery declining")
        if per_key.get("fatigue", {}).get("direction") == "declining":  # fatigue rising = wellbeing declining
            reasons.append("fatigue rising")
        if per_key.get("stress", {}).get("direction") == "declining":
            reasons.append("stress rising")
        if any(pk["volatility"] > 0.4 for pk in per_key.values()):
            reasons.append("high volatility")
        level = "elevated" if len(reasons) >= 2 else ("moderate" if reasons else "low")

        return {"ok": True, "sufficient": True, "per_key": per_key, "trajectory": traj,
                "recovery_direction": rec_dir, "adherence_direction": adh_dir,
                "confidence_direction": conf_dir, "risk": {"level": level, "reasons": reasons}}
    except Exception as e:
        print(f"[trajectory] compute failed: {e}")
        return {"ok": False, "error": str(e)}
