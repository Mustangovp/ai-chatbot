"""
BUILD-003 — Adaptive Coach (Coaching Intelligence, first runtime slice).

The coach becomes the first consumer of Human State. It adapts HOW a response is
delivered on top of the frozen Brain + enforcement — never overriding safety. Every
adaptation is explainable (variable · reason · rule · Constitution principle).
"""
from coaching import adaptive
from coaching.config import consumer_enabled

__all__ = ["adapt", "enabled", "adaptive"]


def enabled() -> bool:
    return consumer_enabled()


def adapt(subject, message, decision, directive, profile=None, now=None):
    return adaptive.adapt(subject, message, decision, directive, profile=profile, now=now)
