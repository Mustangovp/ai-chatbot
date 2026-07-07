"""
BUILD-001 — State Update Engine.

Fuses incoming Readings into the stored current state with:
  • TTL + linear confidence decay (stale data yields to fresh),
  • the hard rule: NEVER overwrite higher-confidence live data with lower-confidence
    inference,
  • conflict resolution = higher *effective* confidence wins; ties → the newer reading.

Pure decision logic + thin persistence calls. No Brain, no LLM.
"""
import datetime as _dt

import db as store
from human_state.schema import now_utc


def _aware(dt):
    """Coerce to timezone-aware UTC (SQLite round-trips can drop tzinfo)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=_dt.timezone.utc)
    return dt


def effective_confidence(stored, now):
    """Stored confidence decayed linearly across its TTL; 0 once expired."""
    observed = _aware(stored.get("observed_at"))
    ttl = stored.get("ttl_seconds") or 1
    if observed is None:
        return 0.0
    age = (_aware(now) - observed).total_seconds()
    if age >= ttl:
        return 0.0
    return float(stored.get("confidence") or 0.0) * max(0.0, 1.0 - age / ttl)


def decide(stored, reading, now):
    """Return 'insert' | 'replace' | 'keep' for one reading vs the stored value."""
    if stored is None:
        return "insert"
    eff = effective_confidence(stored, now)
    # equal-or-higher confidence (and newer) wins; lower-confidence inference is kept out
    return "replace" if reading.confidence >= eff else "keep"


def apply(subject, readings, now=None):
    """Apply readings for a subject. Returns {applied, kept, transitions}. The
    `transitions` list is a full, per-reading audit (prev → action → final) for the
    Observatory — additive; it does NOT change the update behavior. Failure-isolated
    per reading so one bad write can't lose the rest."""
    at = now or now_utc()
    applied, kept, transitions = [], [], []
    for r in readings:
        try:
            # preferences are multi-valued; key them by their note so likes/dislikes coexist
            skey = f"preference:{r.note}" if r.key == "preference" else r.key
            stored = store.hs_get(subject, skey)
            prev_eff = effective_confidence(stored, at) if stored else 0.0
            action = decide(stored, r, at)
            if action in ("insert", "replace"):
                store.hs_upsert(subject, skey, value=r.value, confidence=r.confidence,
                                source=r.source, observed_at=r.observed_at,
                                ttl_seconds=r.ttl_seconds, note=r.note)
                applied.append(skey)
                final = r.value
            else:
                kept.append(skey)
                final = stored["value"] if stored else None
            transitions.append({
                "key": skey, "extracted_value": r.value, "confidence": r.confidence,
                "ttl_seconds": r.ttl_seconds, "source": r.source,
                "prev_value": stored["value"] if stored else None,
                "prev_confidence": (stored.get("confidence") if stored else None),
                "prev_effective": round(prev_eff, 3),
                "action": action, "final_value": final,
            })
        except Exception as e:
            print(f"[hse] apply failed for {getattr(r, 'key', '?')}: {e}")
    return {"applied": applied, "kept": kept, "transitions": transitions}
