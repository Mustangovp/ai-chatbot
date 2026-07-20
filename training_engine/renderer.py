"""Pure presentation contract for immutable TrainingPlanBlueprintV2 values."""
from __future__ import annotations

import json

from .construction import TrainingPlanBlueprintV2
from .completion import completion_projection
from .registry import ExerciseLibrary


def render_prompt(plan: TrainingPlanBlueprintV2, language: str) -> str:
    """The LLM may supply only explanatory prose; plan values stay outside its authority."""
    payload = {
        "plan_id": plan.plan_id,
        "language": "en" if str(language).lower() == "en" else "bg",
        "instruction": "Return JSON only: {\"explanations\": [string]}. Return one to three non-empty explanation strings. Explain motivation or form awareness only. Do not add, remove, reorder, or change exercises, sets, reps, tempo, rest, intensity, duration, or volume.",
    }
    return "[FIXED TRAINING PLAN]\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def verified_explanations(response: str) -> tuple[str, ...]:
    payload = json.loads(str(response or ""))
    if set(payload) != {"explanations"} or not isinstance(payload["explanations"], list):
        raise ValueError("training renderer response contract failed")
    explanations = tuple(payload["explanations"])
    if any(not isinstance(item, str) or not item.strip() for item in explanations):
        raise ValueError("training explanations must be non-empty strings")
    return explanations


def default_explanations(plan: TrainingPlanBlueprintV2, language: str) -> tuple[str, ...]:
    """Supply delivery text only when the explanation-only model returns no prose."""
    if str(language).lower() == "en":
        return (
            "**Why this workout:** this session follows the confirmed plan and keeps the prescribed exercise order, effort, and recovery boundaries intact.",
        )
    return (
        "**Защо тази тренировка:** сесията следва потвърдения план и запазва предписаните упражнения, ред, натоварване и граници за възстановяване.",
    )


def _render_text_delivery(plan: TrainingPlanBlueprintV2, library: ExerciseLibrary,
                    explanations: tuple[str, ...], language: str) -> str:
    english = str(language).lower() == "en"
    title = "Workout" if english else "Тренировка"
    sets_word = "sets" if english else "серии"
    reps_word = "reps" if english else "повторения"
    rest_word = "rest" if english else "почивка"
    lines = [f"**{title}**"]
    for session in plan.sessions:
        label = "Session" if english else "Сесия"
        duration = "min" if english else "мин"
        lines.append(f"\n**{label} {session.session_index} · {session.estimated_duration_minutes} {duration}**")
        for index, prescription in enumerate(session.prescriptions, 1):
            exercise = library.require(prescription.exercise_id, prescription.exercise_version)
            lines.append(
                f"{index}. **{exercise.display_name}** — {prescription.sets} {sets_word} × "
                f"{prescription.rep_min}–{prescription.rep_max} {reps_word}; "
                f"RPE {prescription.target_rpe}, RIR {prescription.target_rir}; "
                f"{rest_word} {prescription.rest_seconds}s; tempo {prescription.tempo}."
            )
    if explanations:
        lines.append("\n" + " ".join(explanations))
    return "\n".join(lines)


def render_completion_projection(plan: TrainingPlanBlueprintV2, library: ExerciseLibrary) -> dict:
    """Internal browser metadata; it is emitted outside visible workout text."""
    return completion_projection(plan, library)


def render_delivery(plan: TrainingPlanBlueprintV2, library: ExerciseLibrary,
                    explanations: tuple[str, ...], language: str) -> str:
    """Render blueprint values in the existing workout-card table contract."""
    english = str(language).lower() == "en"
    title = "Workout" if english else "\u0422\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0430"
    session_label = "Session" if english else "\u0421\u0435\u0441\u0438\u044f"
    minute_label = "min" if english else "\u043c\u0438\u043d"
    lines = [f"**{title}**"]
    for session in plan.sessions:
        lines.extend((
            f"\n**{session_label} {session.session_index} · {session.estimated_duration_minutes} {minute_label}**",
            "| Exercise | Sets | Reps | Rest | Note |",
            "| --- | --- | --- | --- | --- |",
        ))
        for prescription in session.prescriptions:
            exercise = library.require(prescription.exercise_id, prescription.exercise_version)
            lines.append(
                f"| {exercise.display_name} | {prescription.sets} | "
                f"{prescription.rep_min}-{prescription.rep_max} | {prescription.rest_seconds}s | "
                f"RPE {prescription.target_rpe}, RIR {prescription.target_rir}; tempo {prescription.tempo} |"
            )
    if explanations:
        lines.append("\n" + " ".join(explanations))
    return "\n".join(lines)
