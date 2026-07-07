"""
BUILD-001 — Human State Engine (conversation ingestion).

Conversation → memory → Human State. Turns every message into structured, confidence-
scored, TTL-bounded state, fused with the never-downgrade rule. Completely independent
of the frozen Brain: it writes only `human_state`, never `athlete_models`, and the
Brain never reads it.

  ingest(subject, message)  → extract + fuse (the write path; single writer)
  view(subject)             → freshness-adjusted read snapshot (for future consumers)
"""
from human_state import extractor, engine
from human_state.config import ingest_enabled
from human_state.schema import Reading, now_utc

__all__ = ["ingest", "view", "enabled", "Reading", "extractor", "engine"]


def enabled() -> bool:
    return ingest_enabled()


def ingest(subject, message, source="message", now=None):
    """Extract readings from a message and fuse them into the subject's state.
    Returns the apply summary. Callers gate on `enabled()`; this is failure-isolated."""
    at = now or now_utc()
    readings = extractor.extract(message, source=source, now=at)
    if not readings:
        return {"applied": [], "kept": []}
    return engine.apply(subject, readings, now=at)


def view(subject, now=None):
    """Freshness-adjusted snapshot: {key: {value, confidence(effective), fresh, source,
    observed_at, ttl_seconds}}. Below-freshness values are marked fresh=False so
    consumers can treat them as unknown (conservative)."""
    import db as store
    at = now or now_utc()
    out = {}
    for row in store.hs_get_all(subject):
        eff = engine.effective_confidence(row, at)
        out[row["key"]] = {
            "value": row.get("value"),
            "confidence": round(eff, 3),
            "stored_confidence": row.get("confidence"),
            "fresh": eff > 0.0,
            "source": row.get("source"),
            "observed_at": row.get("observed_at"),
            "ttl_seconds": row.get("ttl_seconds"),
            "note": row.get("note"),
        }
    return out
