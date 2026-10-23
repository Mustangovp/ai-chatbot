"""Next Move M1: deterministic presentation over existing account evidence.

No plans are generated, constraints changed or models called by this module.
The Brain remains the safety authority; Adaptive Coach can only soften its result.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os

import human_state
from human_state.schema import Reading, KEY_TTL
from context_builder import Subject, build_context
from brain import cascade, enforcement
from coaching import adaptive


def enabled():
    return os.getenv("APEX_NEXT_MOVE_ENABLED", "false").strip().lower() in ("true", "1", "on")


def _time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("missing evidence timestamp")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def fresh_state(owner, now):
    """Only timestamped, explicit account evidence; never re-date profile defaults."""
    result = {}
    for key, row in human_state.view("user:" + str(owner), now=now).items():
        try:
            observed = _time(row.get("observed_at"))
            ttl = int(row.get("ttl_seconds") or 0)
            if (key in KEY_TTL and row.get("fresh") and row.get("source") in ("message", "checkin")
                    and float(row.get("stored_confidence") or 0) >= .8
                    and 0 < ttl <= KEY_TTL[key] and observed <= now < observed + timedelta(seconds=ttl)):
                result[key] = {"value": row.get("value"), "confidence": row["confidence"],
                               "observed_at": observed, "ttl_seconds": ttl}
        except (TypeError, ValueError, OverflowError):
            continue
    return result


def context_state(state):
    """Translate existing HSE tokens to the existing profile contract, not scores."""
    result = {key: dict(row) for key, row in state.items()}
    maps = {"recovery": {"high": "fresh", "normal": "ok", "low": "tired"},
            "sleep": {"high": "good", "low": "poor"},
            "stress": {"high": "high", "low": "low"}}
    for key, values in maps.items():
        if key in result:
            value = result[key]["value"]
            if isinstance(value, str) and value in values:
                result[key]["value"] = values[value]
            else:
                # Unknown categories cannot overwrite canonical profile values.
                result.pop(key)
    return result


def record_checkin(owner, recovery, now):
    values = {"fresh": "high", "ok": "normal", "tired": "low"}
    if not isinstance(recovery, str) or recovery not in values:
        raise ValueError("invalid recovery choice")
    result = human_state.engine.apply("user:" + str(owner), [Reading(
        "recovery", values[recovery], 1.0, source="checkin", observed_at=now,
    )], now=now)
    if "recovery" not in result["applied"]:
        raise RuntimeError("check-in was not durably recorded")


_TEXT = {
    "en": {
        "profile": ("What goal should APEX train toward?", "I need your saved training context before choosing a session.", "Complete my profile"),
        "checkin": ("How recovered do you feel today?", "Your saved profile is not a fresh recovery check-in.", "Answer today's check-in"),
        "post_workout": ("Check in after your recorded workout.", "A completed session is recorded. Tell me how you feel before planning more work.", "Check in after training"),
        "recovery": ("Put recovery before more training.", "Your recent self-report calls for a conservative next step, not a harder session.", "Discuss recovery"),
        "safety": ("Review the safety boundary first.", "Your saved safety context needs attention before another training request.", "Review with APEX"),
        "review": ("Review your latest generated workout.", "A saved workout is available. Review it before creating another one.", "Open My Training"),
        "train": ("Create your next workout.", "Your saved context and fresh check-in can be checked by the existing Training Engine.", "Create my workout"),
        "coach": ("Review a suitable next step with APEX.", "Training is not the recommended next step with the available context. Discuss a suitable alternative first.", "Discuss my next step"),
        "history": " Your recorded completion remains available to the existing adaptation policy; no adjustment has been applied by this recommendation.",
        "recovery_seed": "Let's discuss recovery first. Do not create or make a workout harder; use my saved constraints and current recovery evidence.",
        "safety_seed": "Help me review my saved safety context before considering training. Do not prescribe a workout.",
        "train_seed": "Create a workout for today using my saved profile, current recovery and persistent training restrictions.",
        "coach_seed": "Explain a suitable next step using my saved context. Do not generate a workout yet.",
    },
    "bg": {
        "profile": ("Към каква цел да насочи APEX тренировките?", "Нужен е запазеният ти тренировъчен контекст, преди да избера сесия.", "Попълни профила ми"),
        "checkin": ("Как се чувстваш възстановен днес?", "Запазеният профил не е нова оценка на възстановяването ти днес.", "Отговори за днес"),
        "post_workout": ("Сподели как си след записаната тренировка.", "Има записана завършена сесия. Кажи как се чувстваш, преди да планираме още натоварване.", "Сподели след тренировката"),
        "recovery": ("Постави възстановяването пред още натоварване.", "Скорошната ти обратна връзка изисква по-предпазлива следваща стъпка, не по-тежка сесия.", "Обсъди възстановяването"),
        "safety": ("Първо прегледай границите за безопасност.", "Запазеният контекст за безопасност изисква внимание преди нова тренировка.", "Прегледай с APEX"),
        "review": ("Прегледай последно създадената тренировка.", "Има запазена тренировка. Прегледай я, преди да създаваш друга.", "Отвори Моите тренировки"),
        "train": ("Създай следващата си тренировка.", "Запазеният контекст и новата ти обратна връзка ще бъдат проверени от съществуващия тренировъчен механизъм.", "Създай ми тренировка"),
        "coach": ("Обсъди подходящата следваща стъпка с APEX.", "Наличният контекст не подкрепя тренировка като следващо действие. Първо обсъди подходяща алтернатива.", "Обсъди следващата стъпка"),
        "history": " Записаната завършена сесия остава достъпна за съществуващата адаптация; тази препоръка не е приложила промяна.",
        "recovery_seed": "Нека първо обсъдим възстановяването. Не създавай и не утежнявай тренировка; използвай запазените ограничения и актуалните ми данни за възстановяване.",
        "safety_seed": "Помогни ми да прегледам запазения контекст за безопасност преди тренировка. Не предписвай тренировка.",
        "train_seed": "Създай тренировка за днес според запазения ми профил, актуалното възстановяване и постоянните тренировъчни ограничения.",
        "coach_seed": "Обясни подходяща следваща стъпка според запазения ми контекст. Засега не създавай тренировка.",
    },
}

_KNOWN = {
    "goal": frozenset(("strength", "muscle_gain", "hypertrophy", "fat_loss", "general", "general_fitness", "maintenance", "endurance")),
    "level": frozenset(("beginner", "intermediate", "advanced", "moderate")),
    "equipment": frozenset(("home", "gym", "none", "bodyweight")),
}


def _known(profile):
    return {key: value if isinstance(value, str) and value in _KNOWN[key] else None
            for key in _KNOWN for value in (profile.get(key),)}


def recommend(*, owner, profile, training, state, now, language, secret, physiology=None, conversation=()):
    """Read-only recommendation using the existing Brain and Adaptive Coach."""
    lang = "en" if language == "en" else "bg"
    text = _TEXT[lang]
    known = _known(profile)
    snapshot = build_context(intent="workout", subject=Subject("account", str(owner), True),
        request_time=now, db_profile=profile, human_state=context_state(state),
        db_workouts=([training["last_completed"]] if training.get("last_completed") else []))
    decision = cascade.decide(profile, message="", conversation=list(conversation), physiology=physiology)
    directive = enforcement.render(decision)
    adaptation = adaptive.adapt("user:" + str(owner), "", decision, directive, profile=profile, now=now)
    completed = training.get("last_completed")
    completed_at = _time(completed["completed_at"]) if completed else None
    if completed_at and completed_at > now:
        raise ValueError("future completion evidence")
    recovery = state.get("recovery", {})
    recovered_at = _time(recovery["observed_at"]) if recovery else None
    kind = "coach"
    hold = profile.get("_medical_hold") or {}
    if decision.halt or hold.get("status") == "ACTIVE_MEDICAL_HOLD":
        kind = "safety"
    elif not all(known.values()) or not snapshot.profile.get("age"):
        kind = "profile"
    elif (recovery.get("value") not in ("high", "normal", "low") or
          (completed_at and (recovered_at is None or completed_at >= recovered_at))):
        kind = "post_workout" if completed_at and now - completed_at < timedelta(days=1) else "checkin"
    elif (recovery["value"] == "low" or any(item["variable"] in state and item["variable"] in
          ("sleep", "fatigue", "pain", "illness", "stress") for item in adaptation["adaptations"])):
        kind = "recovery"
    elif not directive["should_generate_workout"]:
        kind = "coach"
    elif training.get("latest_workout") and (
            not completed_at or _time(training["latest_workout"]["delivered_at"]) > completed_at):
        kind = "review"
    else:
        kind = "train"
    title, why, label = text[kind]
    if kind == "profile" and known["goal"]:
        missing = next((key for key in ("level", "equipment") if not known[key]), "age")
        questions = {
            "en": {"level": "What is your training experience?", "equipment": "What equipment can you use?", "age": "What is your age?"},
            "bg": {"level": "Какъв е тренировъчният ти опит?", "equipment": "С какво оборудване разполагаш?", "age": "На колко години си?"},
        }
        title = questions[lang][missing]
    if completed and kind in ("train", "coach", "review"):
        why += text["history"]
    # A deterministic evidence fingerprint is private/account-bound, not a user ID.
    # Confidence decays with wall time, not new evidence. It must not make every
    # approval stale; changed eligibility is still represented by kind/fresh state.
    evidence = {key: {field: row[field] for field in ("value", "observed_at", "ttl_seconds")}
                for key, row in state.items()}
    material = json.dumps({"owner": str(owner), "profile": profile, "training": training,
        "state": evidence, "kind": kind, "language": lang}, sort_keys=True, default=str, ensure_ascii=True)
    identifier = hmac.new(secret.encode(), material.encode(), hashlib.sha256).hexdigest()
    return {"decision_id": identifier, "kind": kind, "title": title, "why": why,
        "action_label": label, "known": known,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "constraints": [row["pattern"] for row in training.get("active_constraints", [])]}


def workflow(recommendation, language):
    text = _TEXT["en" if language == "en" else "bg"]
    kind = recommendation["kind"]
    if kind in ("checkin", "post_workout"):
        return {"workflow": "checkin"}
    if kind == "profile":
        return {"workflow": "profile"}
    if kind == "review":
        return {"workflow": "my_training"}
    key = {"train": "train_seed", "safety": "safety_seed", "recovery": "recovery_seed"}.get(kind, "coach_seed")
    return {"workflow": "chat", "message": text[key]}
