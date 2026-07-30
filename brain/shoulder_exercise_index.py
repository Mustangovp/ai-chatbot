"""
APEX Brain — Shoulder Load Exercise Index.

Deterministic, canonical metadata for every exercise used by the planner.
Each entry specifies which shoulder-load movement constraints it violates.
An exercise with NO entry is treated as UNKNOWN_SHOULDER_LOAD → fail closed.

Classification criteria (not display-name based):
  - direct_shoulder_load: the shoulder joint is the primary or secondary
    mover/stabiliser under meaningful load.
  - shoulder_stabilisation: shoulder must stabilise the torso or limb under
    bodyweight or external resistance (e.g. plank, push-up, row).
  - upper_limb_external_load: a dumbbell, barbell, or weight is held in the
    hands/arms (any grip), transmitting force through the shoulder.
  - hand_supported_bodyweight: body weight passes through hands/wrists/elbows
    (plank, push-up, table pose, inverted row).
  - push: any horizontal or vertical pushing movement (push-up, press, dip).
  - pull: any pulling movement (row, pull-up, cable pull-down).
  - goblet_hold: dumbbell/kettlebell held in front of the chest with both hands.
  - dumbbell_hinge: Romanian deadlift, good morning or similar with dumbbells.
  - safe_lower_body_only: the exercise is safe for the shoulder when performed
    with arms relaxed and no external upper-limb load.

Canonical IDs must match those used by the training planner / exercise catalogue.
Add new exercises here as the catalogue expands.

IMPORTANT: any exercise NOT listed here must be treated as
  unknown_shoulder_load → ABSOLUTE exclusion (fail-closed).
"""

# Each value is a frozenset of constraint movements this exercise violates.
# If a movement is in the active ConstraintSet as ABSOLUTE,
# the exercise must be excluded deterministically.

_PUSH_UP_CONSTRAINTS = frozenset({
    "push_up", "push", "shoulder_direct_load", "shoulder_stabilisation",
    "hand_supported_bodyweight",
})
_PLANK_CONSTRAINTS = frozenset({
    "plank", "shoulder_stabilisation", "hand_supported_bodyweight",
    "elbow_supported_bodyweight", "forearm_supported_bodyweight",
})
_ROW_CONSTRAINTS = frozenset({
    "row", "pull", "shoulder_direct_load", "upper_limb_external_load",
})
_GOBLET_CONSTRAINTS = frozenset({
    "goblet_hold", "upper_limb_external_load", "shoulder_stabilisation",
})
_DUMBBELL_HINGE_CONSTRAINTS = frozenset({
    "dumbbell_hinge", "dumbbell_deadlift", "upper_limb_external_load",
})
_PRESS_CONSTRAINTS = frozenset({
    "press", "push", "shoulder_direct_load", "upper_limb_external_load",
})
_PULL_UP_CONSTRAINTS = frozenset({
    "pull_up", "pull", "shoulder_direct_load", "hanging",
})
_CARRY_CONSTRAINTS = frozenset({
    "loaded_carry", "farmers_carry", "upper_limb_external_load",
})
_DUMBBELL_HELD_CONSTRAINTS = frozenset({
    "upper_limb_external_load",
})
# Safe: lower body only, no upper limb participation
_SAFE_LOWER_BODY = frozenset()

EXERCISE_SHOULDER_LOAD: dict[str, frozenset] = {
    # ── Push-up family ─────────────────────────────────────────────────────────
    "push_up":               _PUSH_UP_CONSTRAINTS,
    "incline_push_up":       _PUSH_UP_CONSTRAINTS,
    "decline_push_up":       _PUSH_UP_CONSTRAINTS,
    "knee_push_up":          _PUSH_UP_CONSTRAINTS,
    "wide_push_up":          _PUSH_UP_CONSTRAINTS,
    "narrow_push_up":        _PUSH_UP_CONSTRAINTS,
    "diamond_push_up":       _PUSH_UP_CONSTRAINTS,
    "archer_push_up":        _PUSH_UP_CONSTRAINTS,
    "pike_push_up":          _PUSH_UP_CONSTRAINTS,
    "pseudo_planche_push_up": _PUSH_UP_CONSTRAINTS,

    # ── Plank family ───────────────────────────────────────────────────────────
    "front_plank":           _PLANK_CONSTRAINTS,
    "plank":                 _PLANK_CONSTRAINTS,
    "side_plank":            _PLANK_CONSTRAINTS,
    "forearm_plank":         _PLANK_CONSTRAINTS,
    "rkg_plank":             _PLANK_CONSTRAINTS,
    "plank_shoulder_tap":    _PLANK_CONSTRAINTS,
    "plank_with_reach":      _PLANK_CONSTRAINTS,

    # ── Row family ─────────────────────────────────────────────────────────────
    "table_row":             _ROW_CONSTRAINTS,
    "inverted_row":          _ROW_CONSTRAINTS | frozenset({"hand_supported_bodyweight"}),
    "one_arm_dumbbell_row":  _ROW_CONSTRAINTS,
    "dumbbell_row":          _ROW_CONSTRAINTS,
    "barbell_row":           _ROW_CONSTRAINTS,
    "cable_row":             _ROW_CONSTRAINTS,
    "t_bar_row":             _ROW_CONSTRAINTS,
    "chest_supported_row":   _ROW_CONSTRAINTS,
    "face_pull":             _ROW_CONSTRAINTS | frozenset({"shoulder_direct_load"}),

    # ── Pull-up / hanging ──────────────────────────────────────────────────────
    "pull_up":               _PULL_UP_CONSTRAINTS,
    "chin_up":               _PULL_UP_CONSTRAINTS,
    "lat_pulldown":          _PULL_UP_CONSTRAINTS | frozenset({"upper_limb_external_load"}),
    "assisted_pull_up":      _PULL_UP_CONSTRAINTS,
    "band_pull_up":          _PULL_UP_CONSTRAINTS,
    "dead_hang":             frozenset({"hanging", "shoulder_direct_load"}),

    # ── Press / overhead ───────────────────────────────────────────────────────
    "overhead_press":        _PRESS_CONSTRAINTS | frozenset({"overhead"}),
    "dumbbell_overhead_press": _PRESS_CONSTRAINTS | frozenset({"overhead"}),
    "shoulder_press":        _PRESS_CONSTRAINTS | frozenset({"overhead"}),
    "push_press":            _PRESS_CONSTRAINTS | frozenset({"overhead"}),
    "arnold_press":          _PRESS_CONSTRAINTS | frozenset({"overhead"}),
    "bench_press":           _PRESS_CONSTRAINTS,
    "dumbbell_bench_press":  _PRESS_CONSTRAINTS,
    "incline_bench_press":   _PRESS_CONSTRAINTS,
    "incline_dumbbell_press": _PRESS_CONSTRAINTS,
    "chest_fly":             _PRESS_CONSTRAINTS | frozenset({"shoulder_direct_load"}),
    "cable_fly":             _PRESS_CONSTRAINTS | frozenset({"shoulder_direct_load"}),
    "dip":                   frozenset({"dip", "push", "shoulder_direct_load",
                                        "hand_supported_bodyweight"}),

    # ── Goblet squat ───────────────────────────────────────────────────────────
    "goblet_squat":          _GOBLET_CONSTRAINTS,

    # ── Dumbbell hinge / deadlift ──────────────────────────────────────────────
    "dumbbell_romanian_deadlift": _DUMBBELL_HINGE_CONSTRAINTS,
    "romanian_deadlift":     _DUMBBELL_HINGE_CONSTRAINTS,
    "dumbbell_deadlift":     _DUMBBELL_HINGE_CONSTRAINTS,
    "barbell_deadlift":      _DUMBBELL_HINGE_CONSTRAINTS,
    "trap_bar_deadlift":     _DUMBBELL_HINGE_CONSTRAINTS,
    "sumo_deadlift":         _DUMBBELL_HINGE_CONSTRAINTS,
    "good_morning":          _DUMBBELL_HINGE_CONSTRAINTS,
    "kettebell_swing":       _DUMBBELL_HINGE_CONSTRAINTS | frozenset({"shoulder_direct_load"}),
    "kettlebell_swing":      _DUMBBELL_HINGE_CONSTRAINTS | frozenset({"shoulder_direct_load"}),

    # ── Carries ────────────────────────────────────────────────────────────────
    "farmers_carry":         _CARRY_CONSTRAINTS,
    "suitcase_carry":        _CARRY_CONSTRAINTS,
    "goblet_carry":          _CARRY_CONSTRAINTS | _GOBLET_CONSTRAINTS,
    "waiter_carry":          _CARRY_CONSTRAINTS | frozenset({"overhead"}),

    # ── Shoulder isolation ─────────────────────────────────────────────────────
    "lateral_raise":         _PRESS_CONSTRAINTS | frozenset({"shoulder_direct_load", "overhead"}),
    "front_raise":           _PRESS_CONSTRAINTS | frozenset({"shoulder_direct_load", "overhead"}),
    "rear_delt_fly":         frozenset({"shoulder_direct_load", "upper_limb_external_load"}),
    "external_rotation":     frozenset({"shoulder_direct_load"}),
    "internal_rotation":     frozenset({"shoulder_direct_load"}),

    # ── Bodyweight upper-body ──────────────────────────────────────────────────
    "tricep_dip":            frozenset({"dip", "push", "hand_supported_bodyweight",
                                        "shoulder_direct_load"}),
    "l_sit":                 frozenset({"hand_supported_bodyweight", "shoulder_stabilisation",
                                        "shoulder_direct_load"}),
    "handstand":             frozenset({"hand_supported_bodyweight", "overhead",
                                        "shoulder_direct_load"}),
    "bear_crawl":            frozenset({"hand_supported_bodyweight", "shoulder_stabilisation"}),

    # ── Dumbbell-held exercises (external load in hands) ───────────────────────
    # Any exercise where the dumbbell is held in the hands transmits load
    # through the wrist → elbow → shoulder chain.
    "dumbbell_curl":         _DUMBBELL_HELD_CONSTRAINTS | frozenset({"shoulder_stabilisation"}),
    "hammer_curl":           _DUMBBELL_HELD_CONSTRAINTS | frozenset({"shoulder_stabilisation"}),
    "dumbbell_tricep_kickback": _DUMBBELL_HELD_CONSTRAINTS | frozenset({"shoulder_direct_load"}),
    "dumbbell_squat":        _DUMBBELL_HELD_CONSTRAINTS,
    "dumbbell_lunge":        _DUMBBELL_HELD_CONSTRAINTS,
    "dumbbell_step_up":      _DUMBBELL_HELD_CONSTRAINTS,

    # ── Safe lower body (no upper-limb load) ───────────────────────────────────
    # Only valid when performed with arms relaxed and absolutely no external load.
    "bodyweight_squat":      _SAFE_LOWER_BODY,
    "squat":                 _SAFE_LOWER_BODY,
    "bodyweight_lunge":      _SAFE_LOWER_BODY,
    "lunge":                 _SAFE_LOWER_BODY,
    "reverse_lunge":         _SAFE_LOWER_BODY,
    "walking_lunge":         _SAFE_LOWER_BODY,
    "split_squat":           _SAFE_LOWER_BODY,
    "bulgarian_split_squat": _SAFE_LOWER_BODY,
    "step_up":               _SAFE_LOWER_BODY,
    "box_step_up":           _SAFE_LOWER_BODY,
    "glute_bridge":          _SAFE_LOWER_BODY,
    "hip_thrust":            _SAFE_LOWER_BODY,
    "single_leg_glute_bridge": _SAFE_LOWER_BODY,
    "donkey_kick":           _SAFE_LOWER_BODY,
    "fire_hydrant":          _SAFE_LOWER_BODY,
    "clamshell":             _SAFE_LOWER_BODY,
    "lying_hip_abduction":   _SAFE_LOWER_BODY,
    "seated_leg_extension":  _SAFE_LOWER_BODY,
    "seated_leg_curl":       _SAFE_LOWER_BODY,
    "leg_press":             _SAFE_LOWER_BODY,
    "calf_raise":            _SAFE_LOWER_BODY,
    "seated_calf_raise":     _SAFE_LOWER_BODY,
    "wall_sit":              _SAFE_LOWER_BODY,
    "bodyweight_hip_hinge":  _SAFE_LOWER_BODY,
    "hip_hinge":             _SAFE_LOWER_BODY,
    "rdl_bodyweight":        _SAFE_LOWER_BODY,
    "nordic_curl":           _SAFE_LOWER_BODY,
    "lying_leg_curl":        _SAFE_LOWER_BODY,
    "standing_hip_flexion":  _SAFE_LOWER_BODY,
    "standing_hip_extension": _SAFE_LOWER_BODY,
    "lateral_band_walk":     _SAFE_LOWER_BODY,
    "monster_walk":          _SAFE_LOWER_BODY,
    "wall_squat":            _SAFE_LOWER_BODY,
    "box_squat":             _SAFE_LOWER_BODY,
    "sumo_squat":            _SAFE_LOWER_BODY,
    "jumping_squat":         _SAFE_LOWER_BODY,
    "jump":                  _SAFE_LOWER_BODY,
    "jumping_jack":          _SAFE_LOWER_BODY,
    "high_knee":             _SAFE_LOWER_BODY,
    "running":               _SAFE_LOWER_BODY,
    "walking":               _SAFE_LOWER_BODY,
    "cycling":               _SAFE_LOWER_BODY,
    "stationary_bike":       _SAFE_LOWER_BODY,
    "elliptical":            _SAFE_LOWER_BODY,
}

# Movement constraint names that indicate any level of shoulder loading.
# If an exercise's EXERCISE_SHOULDER_LOAD entry intersects with any of
# these, and the corresponding ConstraintSet has an ABSOLUTE constraint,
# the exercise is excluded.
SHOULDER_LOAD_MOVEMENTS = frozenset({
    "shoulder_direct_load",
    "shoulder_stabilisation",
    "upper_limb_external_load",
    "push",
    "pull",
    "press",
    "overhead",
    "loaded_carry",
    "plank",
    "row",
    "push_up",
    "dip",
    "pull_up",
    "hanging",
    "hand_supported_bodyweight",
    "elbow_supported_bodyweight",
    "forearm_supported_bodyweight",
    "goblet_hold",
    "dumbbell_hinge",
    "dumbbell_deadlift",
    "farmers_carry",
    "unknown_shoulder_load",
    "left_upper_limb_load",
    "right_upper_limb_load",
})


def shoulder_load_movements_for(exercise_canonical_id: str) -> frozenset:
    """Return the set of shoulder-load movement-constraint names for an exercise.

    If the exercise is not in the index, returns frozenset({'unknown_shoulder_load'})
    which fails closed against any shoulder constraint.
    """
    cid = (exercise_canonical_id or "").lower().replace(" ", "_").replace("-", "_")
    if cid in EXERCISE_SHOULDER_LOAD:
        return EXERCISE_SHOULDER_LOAD[cid]
    # Unknown exercise: fail closed
    return frozenset({"unknown_shoulder_load"})


def exercise_violates_shoulder_constraint(
    exercise_canonical_id: str,
    forbidden_movements: frozenset,
) -> bool:
    """Return True iff this exercise violates at least one forbidden movement constraint."""
    load = shoulder_load_movements_for(exercise_canonical_id)
    return bool(load & forbidden_movements)
