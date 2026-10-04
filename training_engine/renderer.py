"""Pure presentation contract for immutable TrainingPlanBlueprintV2 values."""
from __future__ import annotations

import json

from .construction import TrainingPlanBlueprintV2
from .completion import completion_projection
from .registry import ExerciseLibrary
from .mixed_modal import SessionFormat, TrainingModality
from .rationale import validate_recommendation_rationale


_BULGARIAN_EXERCISE_NAMES = {
    "dumbbell.bench_press": "\u041b\u0435\u0436\u0430\u043d\u043a\u0430 \u0441 \u0434\u044a\u043c\u0431\u0435\u043b\u0438",
    "barbell.bench_press": "\u041b\u0435\u0436\u0430\u043d\u043a\u0430 \u0441 \u0449\u0430\u043d\u0433\u0430",
    "dumbbell.bent_over_row": "\u0413\u0440\u0435\u0431\u0430\u043d\u0435 \u0441 \u0434\u044a\u043c\u0431\u0435\u043b\u0438 \u043e\u0442 \u043d\u0430\u043a\u043b\u043e\u043d",
    "bodyweight.negative_pull_up": "\u041d\u0435\u0433\u0430\u0442\u0438\u0432\u043d\u043e \u043d\u0430\u0431\u0438\u0440\u0430\u043d\u0435",
    "dumbbell.reverse_lunge": "\u041d\u0430\u043f\u0430\u0434 \u043d\u0430\u0437\u0430\u0434 \u0441 \u0434\u044a\u043c\u0431\u0435\u043b\u0438",
    "dumbbell.front_squat": "\u041f\u0440\u0435\u0434\u0435\u043d \u043a\u043b\u0435\u043a \u0441 \u0434\u044a\u043c\u0431\u0435\u043b\u0438",
    "barbell.deadlift": "\u041c\u044a\u0440\u0442\u0432\u0430 \u0442\u044f\u0433\u0430 \u0441 \u0449\u0430\u043d\u0433\u0430",
    "bodyweight.hollow_hold": "\u0425\u043e\u043b\u043e\u0443 \u0437\u0430\u0434\u044a\u0440\u0436\u0430\u043d\u0435",
    "dumbbell.push_press": "\u041f\u0443\u0448 \u043f\u0440\u0435\u0441\u0430 \u0441 \u0434\u044a\u043c\u0431\u0435\u043b\u0438",
    "bodyweight.wall_push_up": "\u041b\u0438\u0446\u0435\u0432\u0430 \u043e\u043f\u043e\u0440\u0430 \u043d\u0430 \u0441\u0442\u0435\u043d\u0430",
    "bodyweight.incline_push_up": "\u041b\u0438\u0446\u0435\u0432\u0430 \u043e\u043f\u043e\u0440\u0430 \u043d\u0430 \u043d\u0430\u043a\u043b\u043e\u043d",
    "bodyweight.push_up": "\u041b\u0438\u0446\u0435\u0432\u0430 \u043e\u043f\u043e\u0440\u0430",
    "bodyweight.table_row": "\u0413\u0440\u0435\u0431\u0430\u043d\u0435 \u043f\u043e\u0434 \u043c\u0430\u0441\u0430",
    "bodyweight.squat": "\u041a\u043b\u0435\u043a \u0441\u044a\u0441 \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043e \u0442\u0435\u0433\u043b\u043e",
    "dumbbell.goblet_squat": "\u0413\u043e\u0431\u043b\u0435\u0442 \u043a\u043b\u0435\u043a",
    "bodyweight.reverse_lunge": "\u041d\u0430\u043f\u0430\u0434 \u043d\u0430\u0437\u0430\u0434",
    "bodyweight.hip_hinge": "\u0425\u0438\u043f \u0445\u0438\u043d\u0434\u0436 \u0441\u044a\u0441 \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043e \u0442\u0435\u0433\u043b\u043e",
    "dumbbell.romanian_deadlift": "\u0420\u0443\u043c\u044a\u043d\u0441\u043a\u0430 \u0442\u044f\u0433\u0430 \u0441 \u0434\u044a\u043c\u0431\u0435\u043b\u0438",
    "dumbbell.row": "\u0413\u0440\u0435\u0431\u0430\u043d\u0435 \u0441 \u0434\u044a\u043c\u0431\u0435\u043b",
    "band.row": "\u0413\u0440\u0435\u0431\u0430\u043d\u0435 \u0441 \u043b\u0430\u0441\u0442\u0438\u043a",
    "dumbbell.overhead_press": "\u0420\u0430\u043c\u0435\u043d\u043d\u0430 \u043f\u0440\u0435\u0441\u0430 \u0441 \u0434\u044a\u043c\u0431\u0435\u043b\u0438",
    "dumbbell.seated_press": "\u0421\u0435\u0434\u043d\u0430\u043b\u0430 \u0440\u0430\u043c\u0435\u043d\u043d\u0430 \u043f\u0440\u0435\u0441\u0430 \u0441 \u0434\u044a\u043c\u0431\u0435\u043b\u0438",
    "bodyweight.pull_up": "\u041d\u0430\u0431\u0438\u0440\u0430\u043d\u0435",
    "bodyweight.plank": "\u041f\u0440\u0435\u0434\u0435\u043d \u043f\u043b\u0430\u043d\u043a",
    "barbell.back_squat": "\u041a\u043b\u0435\u043a \u0441 \u0449\u0430\u043d\u0433\u0430 \u043d\u0430 \u0433\u044a\u0440\u0431\u0430",
    "bodyweight.march_in_place": "\u041c\u0430\u0440\u0448\u0438\u0440\u0430\u043d\u0435 \u043d\u0430 \u043c\u044f\u0441\u0442\u043e",
}


def _display_name(exercise_id: str, fallback: str, language: str) -> str:
    if str(language).lower() == "bg":
        return _BULGARIAN_EXERCISE_NAMES.get(exercise_id, fallback)
    return fallback


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


def render_completion_projection(plan: TrainingPlanBlueprintV2, library: ExerciseLibrary,
                                 language: str = "en",
                                 recommendation_rationale: object = None) -> dict:
    """Internal browser metadata; it is emitted outside visible workout text."""
    projection = completion_projection(plan, library)
    sessions = []
    for session_index, session in enumerate(projection["sessions"][:1]):
        exercises = []
        for item in session["exercises"]:
            exercise = library.require(item["exercise_id"], item["exercise_version"])
            exercises.append({
                **item,
                "display_name": _display_name(exercise.exercise_id, exercise.display_name, language),
            })
        sessions.append({**session, "exercises": exercises})
        if plan.sessions[session_index].mixed_modal is not None:
            sessions[-1]["mixed_modal"] = plan.sessions[session_index].mixed_modal.to_record()
    rendered = {**projection, "sessions": sessions}
    rationale = validate_recommendation_rationale(recommendation_rationale)
    if rationale is not None:
        rendered["recommendation_rationale"] = rationale
    return rendered


def render_delivery(plan: TrainingPlanBlueprintV2, library: ExerciseLibrary,
                    explanations: tuple[str, ...], language: str) -> str:
    """Render blueprint values in the existing workout-card table contract."""
    english = str(language).lower() == "en"
    title = "Workout" if english else "\u0422\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0430"
    session_label = "Session" if english else "\u0421\u0435\u0441\u0438\u044f"
    minute_label = "min" if english else "\u043c\u0438\u043d"
    header = ("| Exercise | Sets | Reps | Rest | Note |" if english else
              "| \u0423\u043f\u0440\u0430\u0436\u043d\u0435\u043d\u0438\u0435 | \u0421\u0435\u0440\u0438\u0438 | \u041f\u043e\u0432\u0442\u043e\u0440\u0435\u043d\u0438\u044f | \u041f\u043e\u0447\u0438\u0432\u043a\u0430 | \u0411\u0435\u043b\u0435\u0436\u043a\u0430 |")
    rest_unit = "s" if english else " \u0441\u0435\u043a"
    tempo_label = "tempo" if english else "\u0442\u0435\u043c\u043f\u043e"
    lines = [f"**{title}**"]
    for session in plan.sessions[:1]:
        if session.mixed_modal is not None:
            lines.extend(_mixed_modal_intro(session.mixed_modal, language))
        lines.extend((
            f"\n**{session_label} {session.session_index} · {session.estimated_duration_minutes} {minute_label}**",
            header,
            "| --- | --- | --- | --- | --- |",
        ))
        for prescription in session.prescriptions:
            exercise = library.require(prescription.exercise_id, prescription.exercise_version)
            lines.append(
                f"| {_display_name(exercise.exercise_id, exercise.display_name, language)} | {prescription.sets} | "
                f"{prescription.rep_min}-{prescription.rep_max} | {prescription.rest_seconds}{rest_unit} | "
                f"RPE {prescription.target_rpe}, RIR {prescription.target_rir}; {tempo_label} {prescription.tempo} |"
            )
    if explanations and plan.sessions[0].mixed_modal is None:
        lines.append("\n" + " ".join(explanations))
    return "\n".join(lines)


def _mixed_modal_intro(structure, language: str) -> list[str]:
    english = str(language).lower() == "en"
    cap = structure.time_cap_minutes
    if structure.format is SessionFormat.AMRAP:
        instruction = (f"AMRAP · {cap} min: cycle the listed movements, no more than each prescribed set and rep target. Stop at the cap."
                       if english else f"AMRAP · {cap} мин: редувай упражненията до посочените серии и повторения. Спри при лимита.")
    elif structure.format is SessionFormat.EMOM:
        instruction = (f"EMOM · {cap} min: start the next prescribed set at each new minute; use the remainder to rest. Stop when all sets are done."
                       if english else f"EMOM · {cap} мин: започвай следващата серия в началото на всяка минута; почивай до следващата. Спри след последната серия.")
    elif structure.format is SessionFormat.FOR_TIME:
        instruction = (f"For Time · {cap}-min cap: complete the listed sets and reps in order; stop at the cap rather than rushing technique."
                       if english else f"За време · лимит {cap} мин: изпълни посочените серии и повторения по ред; спри при лимита, без да жертваш техниката.")
    elif structure.format is SessionFormat.INTERVALS:
        instruction = (f"Intervals · {cap}-min cap: up to {structure.work_seconds}s work, then {structure.rest_seconds}s rest; rotate through the listed sets. Never exceed the listed reps."
                       if english else f"Интервали · лимит {cap} мин: до {structure.work_seconds} сек работа, после {structure.rest_seconds} сек почивка; редувай сериите. Не надвишавай повторенията.")
    elif structure.format is SessionFormat.STRENGTH_METCON:
        instruction = (f"Strength + metcon · {cap}-min cap: complete the first movement as controlled strength work, then cycle the remaining movements within their prescribed sets."
                       if english else f"Сила + меткон · лимит {cap} мин: първото упражнение е контролирана силова работа, после редувай останалите до посочените серии.")
    else:
        instruction = (f"Rounds/reps · {cap}-min cap: cycle the movements in order, never exceeding the prescribed sets or reps."
                       if english else f"Кръгове/повторения · лимит {cap} мин: редувай упражненията по ред, без да надвишаваш сериите и повторенията.")
    modalities = {
        TrainingModality.WEIGHTLIFTING: ("resistance", "силови"),
        TrainingModality.OLYMPIC_DERIVATIVE: ("Olympic-lift derivative", "олимпийски вариант"),
        TrainingModality.GYMNASTICS: ("bodyweight", "със собствено тегло"),
        TrainingModality.MONOSTRUCTURAL: ("monostructural conditioning", "моноструктурна кондиция"),
    }
    modes = ", ".join(modalities[item][0 if english else 1] for item in structure.modalities)
    reasons = set(structure.reason_codes)
    why = ("The format mixes " + modes + " within the plan's movement and work limits."
           if english else "Форматът съчетава " + modes + " в рамките на допустимите движения и натоварване.")
    if "profile_experience" in reasons:
        why += (" Saved experience bounds movement complexity."
                if english else " Запазеният опит ограничава сложността на движенията.")
    if "profile_equipment" in reasons:
        why += (" Saved equipment limits exercise selection."
                if english else " Запазеното оборудване ограничава избора на упражнения.")
    if "limited_recovery" in reasons:
        why += (" Lower recovery keeps the effort and work cap conservative."
                if english else " Ограниченото възстановяване налага по-умерено усилие и лимит.")
    if "movement_constraint" in reasons:
        why += (" Active movement exclusions remain in force."
                if english else " Активните ограничения за движения остават в сила.")
    if "completed_history" in reasons:
        why += (" Prior completed-session evidence informed the validated plan."
                if english else " Данните от предишна завършена сесия са отчетени в потвърдения план.")
    if "unverified_skill" in reasons:
        why += (" Olympic lifts are omitted because specific technique proficiency is unverified."
                if english else " Олимпийските движения са пропуснати, защото техниката не е потвърдена.")
    if "unsupported_requested_station" in reasons:
        why += (" The requested row/run/bike station is not in the validated exercise catalog; the listed low-skill conditioning takes its place."
                if english else " Поисканото гребане/бягане/колело не е във валидирания каталог; използвана е посочената проста кондиция.")
    if "unsupported_box_jump" in reasons:
        why += (" Box jumps are omitted; only listed eligible movements are prescribed."
                if english else " Скоковете на кутия са пропуснати; предписани са само посочените допустими движения.")
    return ["\n" + instruction, ("**Why:** " if english else "**Защо:** ") + why]
