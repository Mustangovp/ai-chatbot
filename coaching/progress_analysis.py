"""Bounded chat analysis over the existing verified Progress read projection."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

from training_engine.registry import load_exercise_library
from training_engine.renderer import _display_name

VERSION = "training-progress-chat-v1"
MAX_POINTS = 5


def is_request(message: str) -> bool:
    text = str(message or "").casefold()
    progress = re.search(r"\b(progress|improving|improvement)\b|напред\w*|прогрес\w*", text)
    training = re.search(r"\b(training|workouts?|exercises?|reps|strength)\b|трениров\w*|упражнен\w*|силата", text)
    analysis = re.search(r"\b(analy[sz]e|analysis|show|how|review|compare)\b|анализ\w*|покажи|как|сравни", text)
    if not training and re.search(r"\b(nutrition|diet|weight|calories)\b|хранител\w*|тегло\w*|калори\w*", text):
        return False
    return bool(progress and (training or analysis))


def _integer(value, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise ValueError("invalid observed count")
    return value


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("missing recorded timestamp")
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("ambiguous timestamp")
    return moment.astimezone(timezone.utc).isoformat()


def _load(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("invalid load")
    number = Decimal(str(value))
    if not number.is_finite() or not 0 <= number <= 1000:
        raise ValueError("invalid load")
    return float(number)


def build(projection=None, *, language="bg", unavailable=False, authenticated=True):
    """Never accept browser history. Call only with get_training_progress(owner)."""
    en = language == "en"
    result = {"version": VERSION, "language": "en" if en else "bg", "status": "empty",
              "summary": "", "evidence": "", "limitations": "", "next_step": "", "series": None}
    if not authenticated:
        result.update(status="auth_required", summary=("Sign in to analyse your saved training." if en else
                      "Влез в профила си за анализ на записаните тренировки."),
                      next_step=("Use your existing account; browser chat is not execution evidence." if en else
                                 "Използвай съществуващия си акаунт; разговорът не е доказателство за изпълнение."))
        return result
    if unavailable or not isinstance(projection, dict) or not isinstance(projection.get("record"), dict):
        result.update(status="unavailable", summary=("Saved training evidence is temporarily unavailable." if en else
                      "Записаните тренировъчни данни временно не са достъпни."),
                      next_step="Try again later." if en else "Опитай отново по-късно.")
        return result
    record = projection["record"]
    sessions = record.get("recent_sessions")
    if not isinstance(sessions, list):
        return build(language=language, unavailable=True)
    groups = defaultdict(list)
    library = load_exercise_library()
    rejected = False
    for session in sessions[:MAX_POINTS]:
        try:
            timestamp = _timestamp(session["completed_at"])
            exercises = session["exercises"]
            if not isinstance(exercises, list) or len(exercises) > 40:
                raise ValueError("invalid exercise collection")
        except (KeyError, TypeError, ValueError):
            rejected = True
            continue
        seen = set()
        for item in exercises:
            try:
                exercise = library.require(item["exercise_id"], item["exercise_version"])
                identity = (exercise.exercise_id, exercise.version)
                if identity in seen:
                    raise ValueError("duplicate observation")
                seen.add(identity)
                kind = item["prescription_type"]
                if kind not in {"repetitions", "duration"}:
                    raise ValueError("unsupported observed unit")
                value = _integer(item["completed_repetitions"] if kind == "repetitions" else
                                 item["completed_duration_seconds"], 100000)
                other = item.get("completed_duration_seconds" if kind == "repetitions" else "completed_repetitions")
                if other is not None or item.get("load_unit", "kg") != "kg":
                    raise ValueError("contradictory units")
                sets = _integer(item["completed_sets"], 100)
                load = _load(item.get("completed_load"))
                key = (*identity, kind, sets, load)
                groups[key].append({"recorded_at": timestamp, "value": value})
            except (AttributeError, KeyError, TypeError, ValueError, InvalidOperation):
                rejected = True
    # Same exercise version, dose type, completed sets and recorded load only.
    # Missing load stays unknown, never becomes zero or a claim of equal loading.
    for key, points in groups.items():
        times = [point["recorded_at"] for point in points]
        groups[key] = sorted([point for point in points if times.count(point["recorded_at"]) == 1],
                             key=lambda point: point["recorded_at"])
    groups = {key: points for key, points in groups.items() if points}
    if groups:
        key = sorted(groups, key=lambda key: (-len(groups[key]),
                     -datetime.fromisoformat(groups[key][-1]["recorded_at"]).timestamp(), str(key)))[0]
        points = groups[key]
        exercise = library.require(key[0], key[1])
        result["series"] = {"exercise_id": key[0], "exercise_version": key[1],
            "display_name": _display_name(key[0], exercise.display_name, result["language"]),
            "unit": "reps" if key[2] == "repetitions" else "seconds",
            "completed_sets": key[3], "load_kg": key[4], "points": points}
        result["status"] = "comparable" if len(points) >= 2 else "insufficient"
        if len(points) >= 2:
            first, last = points[0]["value"], points[-1]["value"]
            unit = ("reps" if en else "повторения") if key[2] == "repetitions" else ("seconds" if en else "секунди")
            result["summary"] = (f"Recorded {unit}: {first} to {last}. This alone does not establish fitness progress." if en else
                f"Записани {unit}: от {first} до {last}. Само това не доказва подобрение на формата.")
        else:
            result["summary"] = ("One usable observation is not enough for a comparison." if en else
                                  "Един използваем запис не е достатъчен за сравнение.")
    else:
        result["summary"] = ("There are no comparable recorded exercise values yet." if en else
                              "Все още няма сравними записани стойности за упражненията.")
    result["evidence"] = ("Source: verified completed workouts, within the latest five saved sessions. Times are shown in UTC. Values are user-recorded, not sensor measurements." if en else
        "Източник: проверени завършени тренировки в последните пет записани сесии. Часовете са в UTC. Стойностите са въведени от теб, не са сензорни измервания.")
    result["limitations"] = ("Comparison uses the same exercise version, dose unit and completed sets. Technique, recovery and unrecorded load may differ; this is not a causal or strength assessment." if en else
        "Сравнението е за една версия на упражнението, единица и брой завършени серии. Техника, възстановяване и незаписана тежест може да се различават; това не е оценка на сила или причинност.")
    if rejected:
        result["limitations"] += (" Incomplete or inconsistent records were excluded." if en else
                                     " Непълните или противоречиви записи са изключени.")
    result["next_step"] = ("Record actual repetitions or seconds after your next workout; retain your current training restrictions." if en else
        "Запиши реалните повторения или секунди след следващата тренировка; запази текущите си тренировъчни ограничения.")
    return result


def text_fallback(analysis):
    """Readable persisted chat history when the structured renderer is unavailable."""
    lines = [analysis["summary"]]
    series = analysis["series"]
    if series:
        en = analysis["language"] == "en"
        unit = ("Recorded count (repetitions)" if en else "Записан брой (бр.)") if series["unit"] == "reps" else ("Recorded duration (sec)" if en else "Записана продължителност (сек)")
        load = series["load_kg"]
        load_text = ("not recorded" if en else "незаписана") if load is None else f"{load} kg"
        lines += [series["display_name"], (f"Completed sets: {series['completed_sets']}; recorded load: {load_text}." if en else
                  f"Завършени серии: {series['completed_sets']}; записана тежест: {load_text}.")]
        table = [f"| UTC | {unit} |", "| --- | --- |"]
        table += [f"| {point['recorded_at']} | {point['value']} |" for point in series["points"]]
        lines.append("\n".join(table))
    lines += [analysis[key] for key in ("evidence", "limitations", "next_step") if analysis[key]]
    return "\n\n".join(lines)
