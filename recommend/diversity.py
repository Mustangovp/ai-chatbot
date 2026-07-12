"""
APEX M6 — Recommendation diversity (rotation).

Prevents recommending the same thing repeatedly. The Architect anchors each
blueprint to a rotated "anchor" (e.g. a breakfast protein, a workout family
emphasis); this module picks the next anchor NOT used recently and records it.
Deterministic given the recent history. No Brain logic.
"""
import db as store

# Rotation pools per recommendation kind — the anchor the LLM must build around.
POOLS = {
    "nutrition": ["eggs", "greek_yogurt", "cottage_cheese", "oats", "smoothie",
                  "tofu_scramble", "protein_pancakes", "chia_pudding"],
    "workout": ["lower_body", "upper_push", "upper_pull", "full_body", "core_stability",
                "conditioning", "mobility_flow"],
    "recovery": ["sleep_focus", "hydration_focus", "walk_focus", "breathwork_focus", "mobility_focus"],
}


def recent(subject: str, kind: str, n: int = 4) -> list:
    try:
        return store.recent_recommendations(subject, kind, n) or []
    except Exception as e:
        print(f"[diversity] recent failed: {e}")
        return []


def rotate(pool: list, recent_anchors: list, avoid: list = None) -> str:
    """Pick the first pool anchor that is neither recently used nor avoided.
    Falls back to the least-recently-used if every option is 'recent'."""
    avoid = set(a.lower() for a in (avoid or []))
    recent_set = list(recent_anchors)                     # order: most-recent first
    for a in pool:
        if a in recent_set or a.replace("_", " ") in avoid or a in avoid:
            continue
        return a
    # everything recent → choose the one used longest ago (not in the recent head)
    for a in pool:
        if a not in recent_set[:max(0, len(recent_set) - 1)]:
            return a
    return pool[0]


def next_anchor(subject: str, kind: str, avoid: list = None, *, record: bool = True) -> tuple:
    """Return (chosen_anchor, recent_anchors), optionally recording the choice."""
    pool = POOLS.get(kind, [])
    rec = recent(subject, kind)
    anchor = rotate(pool, rec, avoid) if pool else ""
    if anchor and record:
        try:
            store.log_recommendation(subject, kind, anchor)
        except Exception as e:
            print(f"[diversity] record failed: {e}")
    return anchor, rec
