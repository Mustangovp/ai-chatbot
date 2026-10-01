"""Pure runtime adapter for the deterministic Training Engine.

It translates already-verified profile facts into typed engine inputs. Unknown,
ambiguous, or injury-constrained facts fail closed; this module never falls back
to prompt-generated planning.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from dataclasses import replace
import re
from typing import Any, Mapping

from .construction import (
    PrescriptionRule,
    RecoveryAssumption,
    TrainingPlanBlueprintV2,
    TrainingPlanConstructionEngine,
    TrainingStructurePolicy,
)
from .models import Difficulty, Equipment, MovementPattern
from .mixed_modal import SessionFormat
from .health_restrictions import (
    UnsupportedHealthRestrictionError,
    knee_load_limited_patterns,
    project_explicit_health_restrictions,
)
from .registry import ExerciseLibrary, load_exercise_library
from .renderer import _display_name
from .selection import (
    TrainingGoal,
    TrainingSafetyConstraints,
    TrainingSelectionEngine,
    TrainingSelectionRequest,
    TrainingSplit,
    TrainingGoalPolicy,
    resolve_training_split,
    training_goal_policy,
)


class TrainingRuntimeError(ValueError):
    pass


_GOALS = {
    "muscle_gain": TrainingGoal.MUSCLE_GAIN,
    "muscle gain": TrainingGoal.MUSCLE_GAIN,
    "strength": TrainingGoal.MUSCLE_GAIN,
    "hypertrophy": TrainingGoal.MUSCLE_GAIN,
    "fat_loss": TrainingGoal.FAT_LOSS,
    "fat loss": TrainingGoal.FAT_LOSS,
    "weight_loss": TrainingGoal.FAT_LOSS,
    "maintenance": TrainingGoal.MAINTENANCE,
    "general_fitness": TrainingGoal.MAINTENANCE,
}
_LEVELS = {
    "beginner": Difficulty.BEGINNER,
    "intermediate": Difficulty.INTERMEDIATE,
    "moderate": Difficulty.INTERMEDIATE,
    "advanced": Difficulty.ADVANCED,
}
_EQUIPMENT = {
    "bodyweight": Equipment.BODYWEIGHT,
    "body weight": Equipment.BODYWEIGHT,
    "dumbbell": Equipment.DUMBBELL,
    "dumbbells": Equipment.DUMBBELL,
    "resistance_band": Equipment.RESISTANCE_BAND,
    "resistance band": Equipment.RESISTANCE_BAND,
    "band": Equipment.RESISTANCE_BAND,
    "bands": Equipment.RESISTANCE_BAND,
    "bench": Equipment.BENCH,
    "barbell": Equipment.BARBELL,
    "cable": Equipment.CABLE,
    "pullup_bar": Equipment.PULLUP_BAR,
    "pull-up bar": Equipment.PULLUP_BAR,
}


def build_training_plan(*, recommendation_blueprint_id: str, facts: Mapping[str, Any],
                        locked_preferences: Mapping[str, tuple[str, ...]] | None = None,
                        requested_split: object | None = None,
                        library: ExerciseLibrary | None = None,
                        excluded_exercise_ids: frozenset[str] = frozenset(),
                        excluded_movement_patterns: frozenset[MovementPattern] = frozenset(),
                        deprioritized_exercise_ids: frozenset[str] = frozenset(),
                        session_sequence_index: int = 0,
                        advisory_preferred_exercise_ids: tuple[str, ...] = (),
                        level_override: Difficulty | None = None,
                        mixed_modal: SessionFormat | None = None,
                        load_limited_patterns: frozenset[MovementPattern] = frozenset()) -> TrainingPlanBlueprintV2:
    """Build one deterministic weekly plan or fail without producing a partial plan."""
    profile = dict(facts)
    locked = dict(locked_preferences or {})
    _reject_unreviewed_safety_constraints(profile, locked)
    goal = _goal(profile.get("goal"))
    level = level_override or _level(profile.get("level") or profile.get("experience_level"))
    if not isinstance(level, Difficulty):
        raise TrainingRuntimeError("training level override is invalid")
    if mixed_modal is not None and not isinstance(mixed_modal, SessionFormat):
        raise TrainingRuntimeError("mixed-modal format is invalid")
    if not isinstance(load_limited_patterns, frozenset) or not load_limited_patterns <= {
            MovementPattern.SQUAT, MovementPattern.LUNGE}:
        raise TrainingRuntimeError("unsupported movement load limitation")
    if mixed_modal is not None and level is Difficulty.ADVANCED:
        # General experience does not establish proficiency in complex mixed-modal skills.
        level = Difficulty.INTERMEDIATE
    split = _split(requested_split if requested_split is not None
                   else profile.get("training_split") or profile.get("split"))
    if mixed_modal is not None:
        split = TrainingSplit.FULL_BODY
    equipment = _equipment(locked.get("equipment") or profile.get("equipment"))
    recovery = _recovery(profile)
    if mixed_modal is SessionFormat.FOR_TIME and recovery is RecoveryAssumption.LIMITED:
        mixed_modal = SessionFormat.INTERVALS
    selected_library = library or load_exercise_library()
    base_safety = _safety(profile, locked, selected_library)
    safety = TrainingSafetyConstraints(
        excluded_exercise_ids=base_safety.excluded_exercise_ids | frozenset(excluded_exercise_ids),
        excluded_movement_patterns=base_safety.excluded_movement_patterns | frozenset(excluded_movement_patterns),
        excluded_training_tags=base_safety.excluded_training_tags,
    )
    policy = _policy_for_constraints(goal, split, safety, session_sequence_index)
    if mixed_modal is not None:
        groups = tuple((*session, MovementPattern.MONOSTRUCTURAL)
                       for session in policy.session_patterns)
        policy = replace(
            policy, version=policy.version + ":mixed-modal-v1",
            required_patterns=tuple(pattern for session in groups for pattern in session),
            session_patterns=groups,
        )
    selection = TrainingSelectionEngine.select(
        selected_library,
        TrainingSelectionRequest(
            recommendation_blueprint_id=recommendation_blueprint_id,
            goal=goal,
            experience_level=level,
            available_equipment=equipment,
            muscle_priorities=_priorities(profile),
            requested_split=split,
            safety=safety,
            deprioritized_exercise_ids=frozenset(deprioritized_exercise_ids),
            advisory_preferred_exercise_ids=tuple(advisory_preferred_exercise_ids),
            policy=policy,
        ),
    )
    if selection.blueprint is None:
        raise TrainingRuntimeError("training selection rejected: " + ",".join(selection.rejection_reasons))
    return TrainingPlanConstructionEngine.construct(
        selection.blueprint, selected_library, _structure_policy(
            goal, level, split, recovery, policy=policy, mixed_modal=mixed_modal,
            load_limited_patterns=knee_load_limited_patterns(profile) | load_limited_patterns),
    )


def validate_training_plan_constraints(
        plan: TrainingPlanBlueprintV2, facts: Mapping[str, Any],
        locked_preferences: Mapping[str, tuple[str, ...]] | None = None,
        external_excluded_movement_patterns: frozenset[MovementPattern] = frozenset(),
) -> None:
    """Recheck the delivered artifact against the same typed selector exclusions."""
    profile = dict(facts)
    locked = dict(locked_preferences or {})
    _reject_unreviewed_safety_constraints(profile, locked)
    library = load_exercise_library(plan.exercise_library_version)
    safety = _safety(profile, locked, library)
    load_limited_patterns = knee_load_limited_patterns(profile)
    excluded_patterns = (safety.excluded_movement_patterns
                         | frozenset(external_excluded_movement_patterns))
    for session in plan.sessions:
        for item in session.prescriptions:
            _validate_exercise_constraints(
                item.exercise_id, item.exercise_version, item.movement_pattern, item.rep_max,
                library, safety, excluded_patterns, load_limited_patterns)


def _validate_exercise_constraints(
        exercise_id: str | None, exercise_version: str | None,
        movement_pattern: MovementPattern | None, rep_max: int | None,
        library: ExerciseLibrary, safety: TrainingSafetyConstraints,
        excluded_patterns: frozenset[MovementPattern],
        load_limited_patterns: frozenset[MovementPattern],
) -> None:
    exercise = library.require(exercise_id, exercise_version) if exercise_id is not None else None
    if (movement_pattern is None
            or (exercise is not None and movement_pattern != exercise.movement_pattern)
            or exercise_id in safety.excluded_exercise_ids
            or movement_pattern in excluded_patterns
            or (exercise is not None and any(
                tag in safety.excluded_training_tags for tag in exercise.training_tags))):
        raise TrainingRuntimeError("active training constraint entered delivery")
    if movement_pattern in load_limited_patterns and (rep_max is None or rep_max > 8):
        raise TrainingRuntimeError("active movement load limitation entered delivery")


_UNSTRUCTURED_DOSE = re.compile(
    r"\b(?:\d+\s*(?:x|\u00d7|х|by|по)\s*\d+|"
    r"\d+\s*(?:sets?|reps?|rounds?|rpe|rir|серии|повторен\w*|кръг\w*))\b",
    re.IGNORECASE,
)
_UNSTRUCTURED_FORMAT = re.compile(r"\b(?:amrap|emom|metcon|wod|for\s+time)\b", re.IGNORECASE)
_UNSTRUCTURED_FORMAT_INSTRUCTION = re.compile(
    r"\b(?:do|try|start|perform|use|build)\s+(?:an?\s+)?(?:amrap|emom|metcon|wod)\b",
    re.IGNORECASE,
)
_UNSTRUCTURED_TIMED_OR_LOADED_DOSE = re.compile(
    r"\b\d+\s*(?:min(?:ute)?s?|sec(?:ond)?s?|kg|lbs|минут\w*|секунд\w*)\b",
    re.IGNORECASE,
)
_UNSTRUCTURED_MOVEMENT = re.compile(
    r"\b(?:squats?|lunges?|press(?:es|ing)?|push[- ]?ups?|pull[- ]?ups?|"
    r"rows?|planks?|deadlifts?|thrusters?|hspu|burpees?|"
    r"run(?:ning)?|bike|cycling|snatch(?:es)?|jerks?|"
    r"bells?\s+(?:above|over)\s+(?:your\s+)?head|"
    r"клек\w*|напад\w*|прес\w*|лицев\w*|набирани\w*|тяга)\b",
    re.IGNORECASE,
)
_UNSTRUCTURED_COMMAND = re.compile(
    r"\b(?:do|perform|try|use|add|replace|increase|decrease|scale|repeat|bring|"
    r"start|switch|recommend\w*|suggest\w*|"
    r"подмени|добави|направи|изпълни|увеличи|намали|"
    r"повтори|смени|натовари|опитай|използвай|включи|"
    r"препоръч\w*|предлаг\w*)\b",
    re.IGNORECASE,
)
_UNSTRUCTURED_FAILURE_DOSE = re.compile(
    r"\b(?:until|to)\s+(?:technical\s+)?failure\b|"
    r"\bдо\s+(?:технически\s+)?отказ\b", re.IGNORECASE,
)
_UNSTRUCTURED_NEXT_EXERCISE = re.compile(
    r"\bnext\s+(?:exercise|movement)\b|\bследващ(?:о|ото)?\s+(?:упражнение|движение)\b",
    re.IGNORECASE,
)
_PROHIBITIVE_CLAUSE = re.compile(
    r"^\s*(?:[-*+]\s+)?(?:please\s+)?(?:(?:i|we)\s+)?(?:do\s+not|don['’]t|never|"
    r"avoid|skip|refrain\s+from|should\s+not|must\s+not|"
    r"не\s+(?:прави|изпълнявай|включвай|опитвай|използвай|препоръч\w*)|"
    r"избягвай|не\s+бива)\b", re.IGNORECASE,
)
_NEGATED_RECOMMENDATION = re.compile(
    r"\b(?:is|are|was|were)\s+not\s+recommend\w*\b|"
    r"\bне\s+се\s+препоръчва\b", re.IGNORECASE,
)
_CLAUSE_BREAK = re.compile(
    r"(?<=[.!?;])\s+|\b(?:but|however|но|обаче)\b|"
    r"\b(?:then|afterwards|след\s+това|вместо\s+това)\s+"
    r"(?=(?:do|perform|try|use|add|recommend\w*|"
    r"направи|изпълни|опитай|включи|препоръч\w*)\b)|"
    r"[,;]\s*(?=(?:do|perform|try|use|add|recommend\w*|"
    r"направи|изпълни|опитай|включи|препоръч\w*)\b)|"
    r"\b(?:and|и)\s+(?=(?:do|perform|try|use|add|recommend\w*|"
    r"направи|изпълни|опитай|включи|препоръч\w*)\b)",
    re.IGNORECASE,
)
_UNSTRUCTURED_TRAINING_CONTEXT = re.compile(
    r"\b(?:workout|training|session|block|wod|metcon|тренировк\w*|сеси\w*)\b",
    re.IGNORECASE,
)

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "hundred": 100,
    "един": 1, "една": 1, "едно": 1, "два": 2, "две": 2,
    "три": 3, "четири": 4, "пет": 5, "шест": 6, "седем": 7,
    "осем": 8, "девет": 9, "десет": 10, "единадесет": 11,
    "дванадесет": 12, "тринадесет": 13, "четиринадесет": 14,
    "петнадесет": 15, "шестнадесет": 16, "седемнадесет": 17,
    "осемнадесет": 18, "деветнадесет": 19, "двадесет": 20,
    "тридесет": 30, "четиридесет": 40, "петдесет": 50,
    "шестдесет": 60, "сто": 100,
}
_NUMBER_WORD = re.compile(r"\b(?:" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")\b")
_COMPOUND_NUMBER = re.compile(
    r"\b(twenty|thirty|forty|fifty|sixty)[ -](one|two|three|four|five|six|seven|eight|nine)\b"
    r"|\b(двадесет|тридесет|четиридесет|петдесет|шестдесет)\s+и\s+"
    r"(един|една|едно|два|две|три|четири|пет|шест|седем|осем|девет)\b"
)
_DOSE_UNIT = (
    r"sets?|series|reps?|repetitions?|rounds?|seconds?|secs?|minutes?|mins?|"
    r"kg|lbs?|load|weight|work|rest|"
    r"сери[яи]|повторен\w*|кръг\w*|секунд\w*|минут\w*|"
    r"килограм\w*|тежест|работа|почивка"
)
_COUNT_UNIT = re.compile(rf"\b(\d+)\s*({_DOSE_UNIT})\b|\b({_DOSE_UNIT})\s*(?:of|по|:|=)?\s*(\d+)\b")
_SETS_REPS = re.compile(r"\b(\d+)\s*(?:x|×|х|by|по)\s*(\d+)\b")
_TEMPO_DOSE = re.compile(r"\b(?:tempo|темпо)\s*[:=]?\s*(\d(?:[-/]\d){3})\b")
_TABLE_EXERCISE = re.compile(r"^(?:exercise|movement|упражнен\w*|движен\w*)$", re.IGNORECASE)
_TABLE_DOSE = re.compile(
    rf"^(?:{_DOSE_UNIT}|tempo|темпо|(?:sets?|сери[яи])\s*(?:x|×|х|/|by|по)\s*"
    rf"(?:reps?|repetitions?|повторен\w*))$", re.IGNORECASE)
_UNCERTAIN_DOSE = re.compile(
    rf"\b(?:several|multiple|few|няколко|a\s+dozen|\w+\s+dozen|"
    rf"a\s+couple\s+of|дузина)\s+(?:{_DOSE_UNIT})\b", re.IGNORECASE)
_UNRESOLVED_TRAINING_DOSE = re.compile(
    r"\b(?:\d+\s*(?:sets?|reps?|repetitions?|rounds?|сери[яи]|повторен\w*|кръг\w*)|"
    r"(?:tempo|темпо|load|тежест)\s*[:=]?\s*\d+|"
    r"(?:work|rest|работа|почивка)\s*\d+\s*(?:seconds?|minutes?|секунд\w*|минут\w*))\b",
    re.IGNORECASE,
)
_PRESCRIPTION_INTRO = re.compile(r"(?m)^\s*(?:[-*+]\s+|[^:\n]{1,80}:\s+)")

# These are movement-family aliases, not new exercises or prescription authority.
# Exact catalogue names (including BG renderer names) resolve to exercise IDs first.
_MOVEMENT_FAMILIES = (
    (re.compile(r"(?<!\w)(?:overhead[- ]press(?:es|ing)?|shoulder[- ]press(?:es)?|"
                r"push[- ]press(?:es)?|thrusters?|hspu|handstand[- ]push[- ]ups?|"
                r"преса\s+над\s+глава|раменна\s+преса|военна\s+преса|"
                r"тръстър\w*|лицеви\s+опори\s+от\s+стойка\s+на\s+ръце)(?!\w)"),
     MovementPattern.VERTICAL_PUSH),
    (re.compile(r"(?<!\w)(?:squats?|клек\w*)(?!\w)"), MovementPattern.SQUAT),
    (re.compile(r"(?<!\w)(?:lunges?|напад\w*)(?!\w)"), MovementPattern.LUNGE),
    (re.compile(r"(?<!\w)(?:push[- ]ups?|лицеви\s+опори)(?!\w)"), MovementPattern.HORIZONTAL_PUSH),
    (re.compile(r"(?<!\w)(?:pull[- ]ups?|набирани\w*)(?!\w)"), MovementPattern.VERTICAL_PULL),
    (re.compile(r"(?<!\w)(?:deadlifts?|тяга)(?!\w)"), MovementPattern.HINGE),
)


@dataclass(frozen=True)
class _CandidatePrescription:
    exercise_id: str | None
    movement_pattern: MovementPattern | None
    dose: tuple[tuple[str, int | str], ...]

    @property
    def rep_max(self) -> int | None:
        reps = [value for unit, value in self.dose if unit == "reps" and isinstance(value, int)]
        return max(reps) if reps else None


def _normalize_number_words(text: str) -> str:
    text = text.casefold()
    def compound(match: re.Match[str]) -> str:
        tens, ones = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
        return str(_NUMBER_WORDS[tens] + _NUMBER_WORDS[ones])
    text = _COMPOUND_NUMBER.sub(compound, text)
    return _NUMBER_WORD.sub(lambda match: str(_NUMBER_WORDS[match.group()]), text)


def _normalize_delivery_markup(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"(?<!\w)(?:\*{1,3}|_{1,3})(?=\w)", "", line)
        line = re.sub(r"(?<=\w)(?:\*{1,3}|_{1,3})(?!\w)", "", line)
        lines.append(line)
    return "\n".join(lines)


def _actionable_delivery_text(text: str, library: ExerciseLibrary) -> str:
    movement_names = tuple(
        name.casefold() for exercise in library.exercises
        for name in (exercise.display_name,
                     _display_name(exercise.exercise_id, exercise.display_name, "bg")))
    lines = []
    for line in _normalize_delivery_markup(text).splitlines():
        clauses = _CLAUSE_BREAK.split(line)
        actionable = []
        for clause in clauses:
            prohibition = _PROHIBITIVE_CLAUSE.match(clause)
            prohibited_movement = False
            if prohibition:
                subject = clause[prohibition.end():].strip().casefold()
                subject = re.sub(
                    r"^(?:perform(?:ing)?|do(?:ing)?|try(?:ing)?|use|using|add(?:ing)?|"
                    r"recommend(?:ing)?|include|including)\s+", "", subject)
                subject = re.sub(r"^(?:any|the|these|all)\s+", "", subject)
                # Only a negation directed at a movement removes that reference.
                # "Do not skip X" and "avoid fatigue by doing X" still prescribe X.
                prohibited_movement = bool(
                    (_UNSTRUCTURED_MOVEMENT.match(subject)
                     or any(pattern.match(subject) for pattern, _ in _MOVEMENT_FAMILIES)
                     or any(re.match(re.escape(name) + r"(?!\w)", subject)
                            for name in movement_names))
                    and not _UNSTRUCTURED_COMMAND.search(subject))
            negated_recommendation = _NEGATED_RECOMMENDATION.search(clause)
            if (not clause.strip() or prohibited_movement
                    or (negated_recommendation and not _UNSTRUCTURED_COMMAND.search(
                        clause[:negated_recommendation.start()]
                        + clause[negated_recommendation.end():]))):
                continue
            actionable.append(clause)
        lines.append(" ".join(actionable))
    return "\n".join(lines)


def _prescription_segments(text: str) -> tuple[tuple[str, ...], bool, int]:
    segments = []
    headers = None
    prescription_table = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            headers = None
            continue
        if line.count("|") >= 2:
            cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            if (any(_TABLE_EXERCISE.fullmatch(cell) for cell in cells)
                    and any(_TABLE_DOSE.fullmatch(cell) for cell in cells)):
                headers = cells
                continue
            if headers is not None and len(headers) == len(cells):
                prescription_table = True
                segments.append(" ".join(f"{key} {value}" for key, value in zip(headers, cells)))
            else:
                segments.append(" ".join(cells))
        else:
            headers = None
            segments.append(line)
    return (tuple(segments + [left + " " + right for left, right in zip(segments, segments[1:])]),
            prescription_table, len(segments))


def _candidate_identity(normalized: str, exercises: tuple) -> tuple[str | None, MovementPattern | None]:
    for exercise in exercises:
        names = (exercise.display_name, _display_name(exercise.exercise_id, exercise.display_name, "bg"))
        if any(re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", normalized)
               for name in names):
            return exercise.exercise_id, exercise.movement_pattern
    for pattern, family in _MOVEMENT_FAMILIES:
        if pattern.search(normalized):
            return None, family
    return None, None


def _candidate_prescriptions(
        text: str, library: ExerciseLibrary,
) -> tuple[tuple[_CandidatePrescription, ...], bool]:
    candidates = []
    exercises = tuple(sorted(library.exercises, key=lambda item: len(item.display_name), reverse=True))
    segments, prescription_table, direct_count = _prescription_segments(_normalize_delivery_markup(text))
    for index, segment in enumerate(segments):
        normalized = _normalize_number_words(segment)
        dose = []
        for match in _SETS_REPS.finditer(normalized):
            dose.extend((("sets", int(match.group(1))), ("reps", int(match.group(2)))))
        for match in _COUNT_UNIT.finditer(normalized):
            value = int(match.group(1) or match.group(4))
            unit = (match.group(2) or match.group(3)).casefold()
            if unit.startswith(("rep", "повторен")):
                unit = "reps"
            elif unit.startswith(("set", "seri", "сери")):
                unit = "sets"
            dose.append((unit, value))
        for match in _TEMPO_DOSE.finditer(normalized):
            dose.append(("tempo", match.group(1)))
        if _UNSTRUCTURED_FAILURE_DOSE.search(normalized):
            dose.append(("failure", "technical"))
        if not dose and (index >= direct_count or not (
                _UNSTRUCTURED_COMMAND.search(normalized)
                or _UNSTRUCTURED_NEXT_EXERCISE.search(normalized))):
            continue
        exercise_id, movement_pattern = _candidate_identity(normalized, exercises)
        if movement_pattern is not None or _UNSTRUCTURED_MOVEMENT.search(normalized):
            candidates.append(_CandidatePrescription(exercise_id, movement_pattern, tuple(dose)))
    return tuple(candidates), prescription_table


def validate_training_delivery(
        *, plan: TrainingPlanBlueprintV2 | None,
        facts: Mapping[str, Any],
        locked_preferences: Mapping[str, tuple[str, ...]] | None = None,
        external_excluded_movement_patterns: frozenset[MovementPattern] = frozenset(),
        generated_text: str | None = None,
        active_workout_context: bool = False,
) -> None:
    """Only a typed plan can deliver a prescription; generic prose cannot earn that authority."""
    if plan is not None:
        validate_training_plan_constraints(
            plan, facts, locked_preferences, external_excluded_movement_patterns)
        return
    if not isinstance(generated_text, str):
        raise TrainingRuntimeError("unstructured training delivery is invalid")
    library = load_exercise_library()
    actionable_text = _actionable_delivery_text(generated_text, library)
    text = actionable_text.casefold()
    candidates, prescription_table = _candidate_prescriptions(actionable_text, library)
    if candidates:
        profile = dict(facts)
        locked = dict(locked_preferences or {})
        _reject_unreviewed_safety_constraints(profile, locked)
        safety = _safety(profile, locked, library)
        excluded_patterns = safety.excluded_movement_patterns | frozenset(external_excluded_movement_patterns)
        load_limited_patterns = knee_load_limited_patterns(profile)
        for candidate in candidates:
            if candidate.movement_pattern is None:
                raise TrainingRuntimeError("unstructured training prescription cannot be delivered")
            _validate_exercise_constraints(
                candidate.exercise_id, None, candidate.movement_pattern, candidate.rep_max,
                library, safety, excluded_patterns, load_limited_patterns)
        raise TrainingRuntimeError("unstructured training prescription cannot be delivered")
    if prescription_table:
        raise TrainingRuntimeError("unstructured training prescription cannot be delivered")
    normalized_text = _normalize_number_words(text)
    if ((_PRESCRIPTION_INTRO.search(actionable_text)
         or _UNSTRUCTURED_COMMAND.search(text)
         or _UNSTRUCTURED_TRAINING_CONTEXT.search(text))
            and (_UNRESOLVED_TRAINING_DOSE.search(normalized_text)
                 or _UNCERTAIN_DOSE.search(text))):
        raise TrainingRuntimeError("unstructured training prescription cannot be delivered")
    movements = tuple(_UNSTRUCTURED_MOVEMENT.finditer(text))
    exercises = tuple(sorted(library.exercises, key=lambda item: len(item.display_name), reverse=True))
    has_movement = bool(movements or any(pattern.search(text) for pattern, _ in _MOVEMENT_FAMILIES)
                        or _candidate_identity(text, exercises)[1] is not None)
    has_command = bool(_UNSTRUCTURED_COMMAND.search(text)
                       or _UNSTRUCTURED_NEXT_EXERCISE.search(text)
                       or _UNSTRUCTURED_FAILURE_DOSE.search(text))
    has_timed_or_loaded_dose = bool(_UNSTRUCTURED_TIMED_OR_LOADED_DOSE.search(text))
    # A format name by itself can be explanatory; a dose, instruction, or exercise list cannot.
    if (_UNSTRUCTURED_DOSE.search(text)
            or (has_movement and _UNCERTAIN_DOSE.search(text))
            or (has_movement and (has_command or has_timed_or_loaded_dose))
            or (_UNSTRUCTURED_FORMAT.search(text) and (has_movement or has_timed_or_loaded_dose))
            or _UNSTRUCTURED_FORMAT_INSTRUCTION.search(text)
            or (_UNSTRUCTURED_TRAINING_CONTEXT.search(text)
                and has_command and has_timed_or_loaded_dose)
            or any("," in text[left.end():right.start()]
                   for left, right in zip(movements, movements[1:]))):
        raise TrainingRuntimeError("unstructured training prescription cannot be delivered")


def _goal(value: object) -> TrainingGoal:
    key = str(value or "").strip().lower()
    try:
        return _GOALS[key]
    except KeyError as error:
        raise TrainingRuntimeError("verified profile needs a supported training goal") from error


def _level(value: object) -> Difficulty:
    key = str(value or "").strip().lower()
    try:
        return _LEVELS[key]
    except KeyError as error:
        raise TrainingRuntimeError("verified profile needs a supported experience level") from error


def _split(value: object) -> TrainingSplit:
    try:
        return resolve_training_split(value)
    except ValueError as error:
        raise TrainingRuntimeError("verified profile contains an unsupported training split") from error


def _tokens(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip().lower() for item in value.replace(";", ",").split(",") if item.strip())
    if isinstance(value, (tuple, list, frozenset, set)):
        return tuple(str(item).strip().lower() for item in value if str(item).strip())
    return ()


def _equipment(value: object) -> frozenset[Equipment]:
    tokens = _tokens(value)
    if not tokens:
        raise TrainingRuntimeError("verified profile needs specific equipment")
    resolved = []
    for token in tokens:
        if token == "gym":
            resolved.extend((Equipment.BODYWEIGHT, Equipment.DUMBBELL, Equipment.BARBELL,
                             Equipment.CABLE, Equipment.BENCH, Equipment.PULLUP_BAR))
            continue
        # These are the stable values submitted by the existing browser profile
        # wizard.  They are capability groups, not unsupported equipment names.
        if token == "home":
            resolved.extend((Equipment.BODYWEIGHT, Equipment.DUMBBELL, Equipment.PULLUP_BAR))
            continue
        if token == "none":
            resolved.append(Equipment.BODYWEIGHT)
            continue
        try:
            resolved.append(_EQUIPMENT[token])
        except KeyError as error:
            raise TrainingRuntimeError("verified profile contains unsupported equipment") from error
    return frozenset(resolved)


def _priorities(profile: Mapping[str, Any]) -> tuple[str, ...]:
    values = _tokens(profile.get("muscle_priorities") or profile.get("musclePriorities"))
    return tuple(dict.fromkeys(values))


def _recovery(profile: Mapping[str, Any]) -> RecoveryAssumption:
    value = str(profile.get("recoveryFeel") or profile.get("sleepQuality") or "").strip().lower()
    if value in {"fresh", "good", "high"}:
        return RecoveryAssumption.FRESH
    if value in {"poor", "low", "limited"}:
        return RecoveryAssumption.LIMITED
    return RecoveryAssumption.MODERATE


def _reject_unreviewed_safety_constraints(profile: Mapping[str, Any], locked: Mapping[str, Any]) -> None:
    # Onboarding symptoms and health notes are declared context, not typed
    # training exclusions. Only locked accessibility/injury boundaries still
    # require a controlled review here; explicit restrictions are projected by
    # _safety() below.
    values = _tokens(locked.get("permanent_injuries")) + _tokens(locked.get("accessibility"))
    if values:
        raise TrainingRuntimeError("verified safety constraints require a controlled review")


def _safety(profile: Mapping[str, Any], locked: Mapping[str, Any],
            library: ExerciseLibrary) -> TrainingSafetyConstraints:
    exercise_ids = set()
    patterns = set()
    for value in _tokens(locked.get("exercise_exclusions")):
        if library.get(value) is not None:
            exercise_ids.add(value)
            continue
        try:
            patterns.add(MovementPattern(value))
        except ValueError as error:
            raise TrainingRuntimeError("locked exercise exclusion is unsupported") from error
    try:
        restriction_projection = project_explicit_health_restrictions(profile)
    except UnsupportedHealthRestrictionError as error:
        raise TrainingRuntimeError("explicit health restriction is unsupported") from error
    patterns.update(restriction_projection.excluded_movement_patterns)
    return TrainingSafetyConstraints(frozenset(exercise_ids), frozenset(patterns))


def _policy_for_constraints(goal: TrainingGoal, split: TrainingSplit,
                            safety: TrainingSafetyConstraints,
                            session_sequence_index: int = 0) -> TrainingGoalPolicy:
    base = training_goal_policy(goal, split)
    sessions = tuple(
        tuple(pattern for pattern in session if pattern not in safety.excluded_movement_patterns)
        for session in base.session_patterns
    )
    sessions = tuple(session for session in sessions if session)
    if not isinstance(session_sequence_index, int) or session_sequence_index < 0:
        raise TrainingRuntimeError("training session sequence is invalid")
    offset = 0
    if sessions:
        offset = session_sequence_index % len(sessions)
        sessions = sessions[offset:] + sessions[:offset]
    patterns = tuple(pattern for session in sessions for pattern in session)
    if not patterns:
        raise TrainingRuntimeError("all required movement patterns are excluded")
    return TrainingGoalPolicy(
        version=(base.version + ":constraints:" + ",".join(
            sorted(pattern.value for pattern in safety.excluded_movement_patterns))
            + (f":sequence:{offset}" if offset else "")),
        goal=goal,
        required_patterns=patterns,
        prefer_highest_compatible_difficulty=base.prefer_highest_compatible_difficulty,
        split=split,
        session_patterns=sessions,
    )


def _structure_policy(goal: TrainingGoal, level: Difficulty, split: TrainingSplit,
                      recovery: RecoveryAssumption, *, policy: TrainingGoalPolicy | None = None,
                      mixed_modal: SessionFormat | None = None,
                      load_limited_patterns: frozenset[MovementPattern] = frozenset()) -> TrainingStructurePolicy:
    base_sets = 3 if goal is TrainingGoal.MUSCLE_GAIN else 2
    if mixed_modal is not None:
        base_sets = min(base_sets, 2)
    if recovery is RecoveryAssumption.LIMITED:
        base_sets = max(1, base_sets - 1)
    rep_min, rep_max = ((8, 12) if goal is TrainingGoal.MUSCLE_GAIN else (10, 15)
                        if goal is TrainingGoal.FAT_LOSS else (8, 12))
    if mixed_modal is not None:
        rep_min, rep_max = 6, 10
    rpe = Decimal("7") if recovery is RecoveryAssumption.FRESH else Decimal("6")
    rir = 10 - int(rpe)
    rest = 90 if goal is TrainingGoal.MUSCLE_GAIN else 60
    if mixed_modal is not None:
        rest = ((90 if recovery is RecoveryAssumption.LIMITED else 60)
                if mixed_modal in {SessionFormat.INTERVALS, SessionFormat.STRENGTH_METCON} else 0)
    rules = tuple(
        PrescriptionRule(pattern, base_sets if pattern not in {MovementPattern.CORE_ANTI_EXTENSION,
                                                               MovementPattern.MONOSTRUCTURAL} else
                         (base_sets if pattern is MovementPattern.MONOSTRUCTURAL else max(1, base_sets - 1)),
                         (16 if mixed_modal in {SessionFormat.EMOM, SessionFormat.INTERVALS} else 40)
                         if pattern is MovementPattern.MONOSTRUCTURAL else
                         min(rep_min, 8) if pattern in load_limited_patterns else rep_min,
                         (24 if mixed_modal in {SessionFormat.EMOM, SessionFormat.INTERVALS} else 60)
                         if pattern is MovementPattern.MONOSTRUCTURAL else
                         min(rep_max, 8) if pattern in load_limited_patterns else rep_max,
                         rpe, rir, rest if mixed_modal is not None else
                         rest if pattern not in {MovementPattern.CORE_ANTI_EXTENSION,
                                                 MovementPattern.MONOSTRUCTURAL} else 45,
                         ("2-0-1-0" if pattern is not MovementPattern.MONOSTRUCTURAL else "1-0-1-0")
                         if mixed_modal is not None else
                         "3-1-1-0" if pattern is not MovementPattern.CORE_ANTI_EXTENSION else "2-1-2-0",
                         1 if pattern is MovementPattern.MONOSTRUCTURAL else
                         3 if mixed_modal is not None else
                         4 if pattern is not MovementPattern.CORE_ANTI_EXTENSION else 3,
                         Decimal("1") if pattern in {MovementPattern.CORE_ANTI_EXTENSION,
                                                     MovementPattern.MONOSTRUCTURAL} else Decimal("2"))
        for pattern in (policy or training_goal_policy(goal, split)).required_patterns
    )
    requested_sessions = {TrainingSplit.FULL_BODY: 2, TrainingSplit.UPPER_LOWER: 2,
                          TrainingSplit.PUSH_PULL_LEGS: 3}[split]
    sessions = 1 if recovery is RecoveryAssumption.LIMITED else requested_sessions
    return TrainingStructurePolicy(
        version=f"training-structure-policy-v1:{goal.value}:{level.value}:{split.value}:{recovery.value}"
                + (f":mixed-modal:{mixed_modal.value}" if mixed_modal is not None else ""),
        goal=goal, experience_level=level, training_split=split, recovery=recovery, sessions_per_week=sessions,
        session_patterns=(policy or training_goal_policy(goal, split)).session_patterns,
        movement_order=(MovementPattern.SQUAT, MovementPattern.LUNGE,
                        MovementPattern.HORIZONTAL_PUSH, MovementPattern.HORIZONTAL_PULL,
                        MovementPattern.VERTICAL_PUSH, MovementPattern.HINGE,
                        MovementPattern.CORE_ANTI_EXTENSION,
                        MovementPattern.MONOSTRUCTURAL),
        prescription_rules=rules, max_session_duration_minutes=60,
        max_session_fatigue_units=Decimal("30"), max_weekly_sets_per_primary_muscle=12,
        max_push_pull_set_difference=0, max_lower_body_set_difference=0, transition_seconds=30,
    )
