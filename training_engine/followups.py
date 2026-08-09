"""Closed, deterministic operations for an existing workout blueprint."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import re
from typing import Mapping

from .construction import TrainingPlanBlueprintV2
from .models import Difficulty, MovementPattern
from .registry import ExerciseLibrary, load_exercise_library
from .runtime import TrainingRuntimeError, build_training_plan


class WorkoutFollowUpOperation(str, Enum):
    GENERATE_NEW = "generate_new"
    ALTERNATIVE = "alternative"
    INCREASE_DIFFICULTY = "increase_difficulty"
    DECREASE_DIFFICULTY = "decrease_difficulty"
    EXCLUDE_EXERCISE = "exclude_exercise"
    EXCLUDE_MOVEMENT_FAMILY = "exclude_movement_family"
    INCLUDE_EXERCISE = "include_exercise"
    CHANGE_DURATION = "change_duration"
    CHANGE_EQUIPMENT = "change_equipment"
    REPEAT_PREVIOUS = "repeat_previous"
    UNKNOWN_EXERCISE = "unknown_exercise"


@dataclass(frozen=True)
class WorkoutFollowUp:
    operation: WorkoutFollowUpOperation
    excluded_exercise_ids: frozenset[str] = frozenset()
    excluded_patterns: frozenset[MovementPattern] = frozenset()

    @property
    def requires_previous(self) -> bool:
        return self.operation not in {
            WorkoutFollowUpOperation.GENERATE_NEW,
            WorkoutFollowUpOperation.UNKNOWN_EXERCISE,
        }


@dataclass(frozen=True)
class WorkoutConversationState:
    plan: TrainingPlanBlueprintV2
    blueprint_hash: str

    @property
    def exercise_ids(self) -> tuple[str, ...]:
        return tuple(item.exercise_id for session in self.plan.sessions for item in session.prescriptions)

    @property
    def movement_patterns(self) -> tuple[MovementPattern, ...]:
        return tuple(item.movement_pattern for session in self.plan.sessions for item in session.prescriptions)


_NORMALIZE = re.compile(r"\s+")
_ALT = (
    "искам друга тренировка", "дай друга тренировка", "смени тренировката", "не тази", "друга",
    "different workout", "another workout", "give me another workout", "change the workout", "not this one",
)
_HARDER = ("направи я по-трудна", "по-тежка тренировка", "увеличи трудността",
           "make it harder", "harder workout", "increase difficulty")
_EASIER = ("направи я по-лесна", "намали трудността", "make it easier", "easier workout")
_NO_SQUATS = ("без клекове", "не искам клекове", "махни клековете",
              "no squats", "without squats", "remove squats")
_REPEAT = ("повтори тренировката", "повтори я", "repeat previous", "repeat the workout")
_WORKOUT_WORDS = ("workout", "training", "exercise", "трениров", "упражнен")


def _normalized(value: object) -> str:
    return _NORMALIZE.sub(" ", str(value or "").casefold().strip())


def parse_workout_followup(message: object) -> WorkoutFollowUp | None:
    """Resolve only closed operation phrases; ordinary chat remains untouched."""
    text = _normalized(message)
    if not text:
        return None
    if any(phrase in text for phrase in _ALT):
        return WorkoutFollowUp(WorkoutFollowUpOperation.ALTERNATIVE)
    if any(phrase in text for phrase in _HARDER):
        return WorkoutFollowUp(WorkoutFollowUpOperation.INCREASE_DIFFICULTY)
    if any(phrase in text for phrase in _EASIER):
        return WorkoutFollowUp(WorkoutFollowUpOperation.DECREASE_DIFFICULTY)
    if any(phrase in text for phrase in _NO_SQUATS):
        return WorkoutFollowUp(WorkoutFollowUpOperation.EXCLUDE_MOVEMENT_FAMILY,
                               excluded_patterns=frozenset({MovementPattern.SQUAT}))
    if any(phrase in text for phrase in _REPEAT):
        return WorkoutFollowUp(WorkoutFollowUpOperation.REPEAT_PREVIOUS)
    if any(word in text for word in _WORKOUT_WORDS) and any(marker in text for marker in ("using ", "with ", "include ", "включи ")):
        return WorkoutFollowUp(WorkoutFollowUpOperation.UNKNOWN_EXERCISE)
    return None


def blueprint_hash(plan: TrainingPlanBlueprintV2) -> str:
    payload = ";".join(
        f"{item.exercise_id}@{item.exercise_version}:{item.sets}:{item.rep_min}-{item.rep_max}:{item.target_rpe}:{item.rest_seconds}"
        for session in plan.sessions for item in session.prescriptions
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def state_for(plan: TrainingPlanBlueprintV2) -> WorkoutConversationState:
    return WorkoutConversationState(plan=plan, blueprint_hash=blueprint_hash(plan))


def _difficulty(value: object) -> Difficulty:
    key = str(value or "").strip().lower()
    return {
        "beginner": Difficulty.BEGINNER, "intermediate": Difficulty.INTERMEDIATE,
        "moderate": Difficulty.INTERMEDIATE, "advanced": Difficulty.ADVANCED,
    }[key]


def _step(level: Difficulty, direction: int) -> Difficulty | None:
    levels = (Difficulty.BEGINNER, Difficulty.INTERMEDIATE, Difficulty.ADVANCED)
    index = levels.index(level) + direction
    return levels[index] if 0 <= index < len(levels) else None


def _materially_different(previous: TrainingPlanBlueprintV2, candidate: TrainingPlanBlueprintV2) -> bool:
    before = tuple(item.exercise_id for session in previous.sessions for item in session.prescriptions)
    after = tuple(item.exercise_id for session in candidate.sessions for item in session.prescriptions)
    if not before or not after:
        return False
    changed = len(set(before).symmetric_difference(set(after)))
    return blueprint_hash(previous) != blueprint_hash(candidate) and changed / max(len(before), len(after)) >= 0.4


def apply_followup(*, followup: WorkoutFollowUp, previous: WorkoutConversationState,
                   recommendation_blueprint_id: str, facts: Mapping[str, object],
                   locked_preferences: Mapping[str, tuple[str, ...]] | None = None,
                   library: ExerciseLibrary | None = None,
                   advisory_preferred_exercise_ids: tuple[str, ...] = ()) -> TrainingPlanBlueprintV2:
    """Return a validated revised plan or fail without mutating the prior state."""
    if followup.operation is WorkoutFollowUpOperation.REPEAT_PREVIOUS:
        return previous.plan
    if followup.operation is WorkoutFollowUpOperation.UNKNOWN_EXERCISE:
        raise TrainingRuntimeError("unknown requested exercise")
    selected_library = library or load_exercise_library()
    kwargs = {
        "recommendation_blueprint_id": recommendation_blueprint_id + ":followup:" + followup.operation.value,
        "facts": facts,
        "locked_preferences": locked_preferences,
        "library": selected_library,
        "excluded_exercise_ids": followup.excluded_exercise_ids,
        "excluded_movement_patterns": followup.excluded_patterns,
        "advisory_preferred_exercise_ids": advisory_preferred_exercise_ids,
    }
    if followup.operation is WorkoutFollowUpOperation.ALTERNATIVE:
        candidate = build_training_plan(**kwargs, deprioritized_exercise_ids=frozenset(previous.exercise_ids))
        if _materially_different(previous.plan, candidate):
            return candidate
        retry_kwargs = dict(kwargs)
        retry_kwargs["excluded_exercise_ids"] = (
            frozenset(kwargs["excluded_exercise_ids"]) | frozenset(previous.exercise_ids))
        try:
            candidate = build_training_plan(**retry_kwargs)
        except TrainingRuntimeError as error:
            raise TrainingRuntimeError("no safe materially different workout is available") from error
        if _materially_different(previous.plan, candidate):
            return candidate
        raise TrainingRuntimeError("no safe materially different workout is available")
    if followup.operation in (WorkoutFollowUpOperation.INCREASE_DIFFICULTY,
                               WorkoutFollowUpOperation.DECREASE_DIFFICULTY):
        current = _difficulty(facts.get("level") or facts.get("experience_level"))
        target = _step(current, 1 if followup.operation is WorkoutFollowUpOperation.INCREASE_DIFFICULTY else -1)
        if target is None:
            raise TrainingRuntimeError("requested difficulty is outside the supported range")
        candidate = build_training_plan(**kwargs, level_override=target)
        if blueprint_hash(candidate) == previous.blueprint_hash:
            raise TrainingRuntimeError("difficulty change produced no valid prescription change")
        return candidate
    candidate = build_training_plan(**kwargs)
    if followup.operation is WorkoutFollowUpOperation.EXCLUDE_MOVEMENT_FAMILY:
        excluded = set(followup.excluded_patterns)
        if any(item.movement_pattern in excluded for session in candidate.sessions for item in session.prescriptions):
            raise TrainingRuntimeError("hard movement-family exclusion was not satisfied")
    if followup.operation is WorkoutFollowUpOperation.EXCLUDE_EXERCISE:
        if any(item.exercise_id in followup.excluded_exercise_ids for session in candidate.sessions for item in session.prescriptions):
            raise TrainingRuntimeError("hard exercise exclusion was not satisfied")
    return candidate


def followup_message(error: Exception | str, lang: str) -> str:
    reason = str(error)
    english = str(lang).lower() == "en"
    if "unknown requested exercise" in reason:
        return ("I couldn't match that exercise to the approved exercise library. Name a supported exercise or ask for a workout.") if english else ("Не мога да свържа това упражнение с одобрената библиотека. Посочи поддържано упражнение или поискай тренировка.")
    if "previous" in reason:
        return "Generate a workout first, then I can change it." if english else "Първо генерирай тренировка, после мога да я променя."
    return ("I couldn't safely make that workout change with your current profile and equipment.") if english else ("Не мога безопасно да направя тази промяна с текущия ти профил и наличното оборудване.")
