"""
APEX M6 — Preference Engine.

Persistent, per-subject user preferences that every conversation updates. Pure
parsing + a thin DB persistence layer. No Brain logic, and preferences are NEVER
fed to the Brain (they live outside the athlete model) — they only shape blueprints.

Parsing is deterministic and conservative (EN + a little BG). Examples:
  "I hate oats"        -> avoid: oats
  "I love eggs"        -> prefer: eggs
  "I only have 10 min" -> breakfast_time: 10
  "I don't cook"       -> cooking: minimal
"""
import re

import db as store

DEFAULTS = {"avoid": [], "prefer": [], "breakfast_time": None, "cooking": None, "budget": None}

# Words that END a food phrase (conjunctions, verbs, fillers) — capture stops here.
_BOUNDARY = {"to", "it", "them", "that", "the", "a", "an", "and", "or", "but", "now",
             "have", "has", "only", "i", "so", "because", "when", "if", "really", "just",
             "food", "foods", "much", "anymore", "today", "please", "also", "with", "for",
             "would", "could", "them.", "no"}
_AVOID_PAT = re.compile(r"\b(?:i\s+)?(?:hate|can't stand|cannot stand|don'?t like|dislike|avoid|no more|allergic to)\s+([a-z][a-z \-]{1,30})", re.I)
_PREFER_PAT = re.compile(r"\b(?:i\s+)?(?:love|really like|i like|prefer|enjoy|always want)\s+([a-z][a-z \-]{1,30})", re.I)
_TIME_PAT = re.compile(r"\b(?:only\s+have\s+|i\s+have\s+|got\s+|in\s+)?(\d{1,3})\s*(?:min|minute|minutes|мин|минути)\b", re.I)
_NOCOOK_PAT = re.compile(r"\b(don'?t cook|can'?t cook|no cooking|hate cooking|not cook|no time to cook|не готвя)\b", re.I)
_BUDGET_LOW = re.compile(r"\b(cheap|budget|low cost|inexpensive|евтино)\b", re.I)
_BUDGET_HIGH = re.compile(r"\b(premium|no budget|whatever it costs|money no object)\b", re.I)


def _clean_food(raw: str) -> str:
    """First 1–2 food words, truncated at the first boundary/filler word."""
    out = []
    for w in re.split(r"[ \-]+", raw.strip().lower()):
        w = w.strip(" .,!?")
        if not w or w in _BOUNDARY:
            break
        out.append(w)
        if len(out) >= 2:                       # e.g. "greek yogurt"
            break
    return " ".join(out).strip()


def parse_updates(message: str) -> dict:
    """Extract preference updates from one message. Deterministic; empty when nothing matches."""
    text = message or ""
    up = {"avoid": [], "prefer": []}
    for m in _AVOID_PAT.finditer(text):
        f = _clean_food(m.group(1))
        if f:
            up["avoid"].append(f)
    for m in _PREFER_PAT.finditer(text):
        f = _clean_food(m.group(1))
        if f:
            up["prefer"].append(f)
    if _NOCOOK_PAT.search(text):
        up["cooking"] = "minimal"
    mt = _TIME_PAT.search(text)
    if mt:
        n = int(mt.group(1))
        if 1 <= n <= 240:
            up["breakfast_time"] = n
    if _BUDGET_HIGH.search(text):
        up["budget"] = "premium"
    elif _BUDGET_LOW.search(text):
        up["budget"] = "low"
    # drop empty lists so 'no change' is truly empty
    return {k: v for k, v in up.items() if v not in ([], None)}


def merge(prefs: dict, updates: dict) -> dict:
    """Apply updates to a preference dict (conflict-resolving)."""
    p = {**DEFAULTS, **(prefs or {})}
    p["avoid"] = list(p.get("avoid") or [])
    p["prefer"] = list(p.get("prefer") or [])
    for f in updates.get("avoid", []):
        if f not in p["avoid"]:
            p["avoid"].append(f)
        if f in p["prefer"]:                      # a new dislike overrides an old like
            p["prefer"].remove(f)
    for f in updates.get("prefer", []):
        if f not in p["prefer"]:
            p["prefer"].append(f)
        if f in p["avoid"]:
            p["avoid"].remove(f)
    for k in ("cooking", "breakfast_time", "budget"):
        if updates.get(k) is not None:
            p[k] = updates[k]
    return p


def load(subject: str) -> dict:
    try:
        return {**DEFAULTS, **(store.get_preferences(subject) or {})}
    except Exception as e:
        print(f"[prefs] load failed: {e}")
        return dict(DEFAULTS)


def update_from_message(subject: str, message: str) -> dict:
    """Parse a message, merge into stored prefs, persist, and return the new prefs.
    Failure-isolated: a persistence error never breaks the caller."""
    updates = parse_updates(message)
    prefs = load(subject)
    if not updates:
        return prefs
    prefs = merge(prefs, updates)
    try:
        store.save_preferences(subject, prefs)
    except Exception as e:
        print(f"[prefs] save failed: {e}")
    return prefs
