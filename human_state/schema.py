"""
BUILD-001 — Human State schema, confidence tiers, and TTL rules.

A Reading is one signal extracted from a message (or a future sensor/check-in). The
Human State Engine fuses Readings into current state. This module is pure data — no
Brain logic, no I/O.
"""
from dataclasses import dataclass, field
import datetime as _dt

HOUR = 3600
DAY = 24 * HOUR

# TTL per state key — how long a value stays fresh before it decays/expires
# (aligned to the Human State Engine architecture ownership matrix).
KEY_TTL = {
    "physical_state": DAY,
    "recovery": DAY,
    "fatigue": DAY,
    "pain": 12 * HOUR,
    "stress": DAY,
    "sleep": DAY,
    "sleep_debt": 3 * DAY,
    "nutrition": DAY,
    "motivation": 3 * DAY,
    "confidence": 3 * DAY,
    "time_availability": 4 * HOUR,     # session-scoped
    "equipment": 30 * DAY,
    "environment": 12 * HOUR,
    "illness": 3 * DAY,
    "travel": 3 * DAY,
    "goals": 180 * DAY,                # slow fact
    "identity": 180 * DAY,
    "habit": 180 * DAY,
    "preference": 180 * DAY,
    "adherence": 7 * DAY,
}
DEFAULT_TTL = DAY

# Confidence tiers — how much we trust a signal at the moment it is observed.
CONF_NUMERIC = 0.9     # explicit + a specific number ("slept 4 hours", "15 minutes")
CONF_EXPLICIT = 0.8    # direct first-person present statement ("I'm exhausted")
CONF_HEDGED = 0.55     # softer / past / partial ("kind of tired")
CONF_INFERRED = 0.4    # weak keyword / indirect inference


def now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


@dataclass
class Reading:
    key: str
    value: object                  # scalar 0..1 or token (str/number)
    confidence: float
    source: str = "message"        # message | checkin | coach_obs
    observed_at: _dt.datetime = field(default_factory=now_utc)
    ttl_seconds: int = 0
    note: str = ""

    def __post_init__(self):
        if not self.ttl_seconds:
            self.ttl_seconds = KEY_TTL.get(self.key, DEFAULT_TTL)
