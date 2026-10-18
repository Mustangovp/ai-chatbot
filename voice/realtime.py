"""Restricted Realtime input scaffold. Never a second coaching authority.

The server exchanges SDP, not credentials. Automatic model responses and audio
output are disabled; transcripts still enter /chat and validated speech uses the
existing /speak adapter. Live transport/model quality is deliberately unverified.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import time
import threading
import uuid
from urllib import request as urlrequest
from urllib.parse import urlsplit

from flask import Blueprint, Response, g, jsonify, request, render_template

from voice.session_store import Denied, SessionStore
from voice import charging


blueprint = Blueprint("live_voice", __name__)
_attempts: dict[str, list[float]] = {}
_lock = threading.Lock()
_MODELS = frozenset({"gpt-realtime-2.1-mini", "gpt-realtime-2.1"})
sessions = SessionStore()

_LANGUAGE_REFERENCE = re.compile(r"\b(?:bulgarian|english|български|английски|език\w*|language)\b", re.I)
_LANGUAGE_COMMUNICATION = re.compile(
    r"\b(?:why|speak\w*|reply|respond\w*|answer\w*|language|switch|"
    r"защо|говор\w*|отгов\w*|пиш\w*|език\w*|превключи|смени)\b", re.I)
_LANGUAGE_CHOICE = re.compile(
    r"\b(?:(?:i\s+speak|my\s+language\s+is)|"
    r"(?:speak|talk|reply|respond|answer|continue|switch|use)(?:\s+to\s+me)?(?:\s+(?:in|to))?|"
    r"(?:аз\s+)?(?:говоря|пиша)\s+на|"
    r"(?:говори|отговаряй|пиши|продължи|превключи)(?:\s+ми)?\s+на)\s+"
    r"(?P<language>bulgarian|english|български|английски)\b", re.I)


def normalize_language(value: object) -> str:
    return "en" if str(value).lower() in {"en", "en-us", "en-gb"} else "bg"


def response_language(message: str, preferred: object) -> str:
    """Only an affirmative language choice changes the selected response locale."""
    selected = normalize_language(preferred)
    for clause in re.split(r"[.!?;\n]+", str(message or "")):
        if re.search(r"\b(?:why|защо)\b", clause, re.I):
            continue
        for match in _LANGUAGE_CHOICE.finditer(clause):
            prefix = clause[:match.start()].casefold()
            if re.search(r"\b(?:do\s+not|don['’]t|not|не|недей)\s*$", prefix):
                continue
            selected = "bg" if match["language"].casefold() in {"bulgarian", "български"} else "en"
    return selected


def is_language_turn(message: str) -> bool:
    text = str(message or "")
    if not (_LANGUAGE_REFERENCE.search(text) and _LANGUAGE_COMMUNICATION.search(text)):
        return False
    # A real programming request can also specify its presentation language.
    if re.search(r"\b(?:create|build|give\s+me|make\s+me|дай\s+ми|направи\s+ми|създай)\b"
                 r"[^.!?;]*\b(?:workout|training\s+plan|тренировк\w*|тренировъчен\s+план)\b", text, re.I):
        return False
    return True


def language_reply(language: str) -> str:
    return ("I'll use English. The language setting does not change exercises or workload."
            if normalize_language(language) == "en" else
            "Ще отговарям на български. Езиковата настройка не променя упражненията или натоварването.")


def response_language_instructions(language: str) -> str:
    locale = "en-US" if normalize_language(language) == "en" else "bg-BG"
    name = "English" if locale == "en-US" else "Bulgarian"
    return (f"[RESPONSE LANGUAGE: {locale}]\n"
            f"The explicitly selected response language is {name}. Use it for all user-facing prose, "
            "including explanations inside structured JSON and speech. An English exercise name, borrowed term, "
            "or a question about English does not change this preference. Only an explicit request to switch does. "
            "This presentation rule does not change canonical IDs, JSON keys, prescriptions, or safety authority.")


def explanation_language_matches(text: str, language: str) -> bool:
    """Reject wholly untranslated model prose, not canonical IDs or exercise names."""
    return normalize_language(language) != "bg" or bool(re.search(r"[А-Яа-я]", str(text)))


def enabled_for(req) -> bool:
    """A server flag AND verified account-ID policy are required everywhere."""
    if os.getenv("APEX_LIVE_VOICE_ENABLED", "false").lower() != "true":
        return False
    user = g.get("user")
    if not user:
        return False
    try:
        if not sessions.authorized(user["id"]):
            return False
        if os.getenv("APEX_LIVE_VOICE_TRANSPORT", "relay") != "mock":
            charging.control.require(user["id"])
        direct_local = (not any(name.lower().startswith(("x-forwarded-", "forwarded")) for name in req.headers.keys())
                        and urlsplit(req.host_url).hostname in {"localhost", "127.0.0.1", "::1"}
                        and ipaddress.ip_address(req.remote_addr).is_loopback)
        if direct_local:
            return True
        if os.getenv("APEX_LIVE_VOICE_TRANSPORT", "relay") == "mock":
            return False
        origin = os.getenv("APP_URL", "").rstrip("/")
        return bool(origin.startswith("https://") and req.host_url.rstrip("/") == origin)
    except Exception:
        # Shared state failure is never an authorization fallback.
        return False


def browser_config(req) -> dict:
    # No model, account data, API key or client secret is projected into HTML.
    transport = os.getenv("APEX_LIVE_VOICE_TRANSPORT", "relay")
    enabled = enabled_for(req) and transport in {"mock", "relay"}
    return {"enabled": enabled, "transport": transport if enabled else "disabled"}


def speaking_instructions(language: str) -> str:
    """Communication only: the existing GPT-6 pipeline retains all authority."""
    locale = "Bulgarian" if language == "bg" else "English"
    return (
        f"APEX Live Voice communication: speak natural {locale}. "
        "Use short, clear spoken sentences and one useful question at a time. "
        "Be warm, precise and calmly expressive, without forced theatrics, filler, "
        "flattery or pretending to be human. Disagree respectfully when evidence "
        "or safety requires it; explain the reason and offer a safe alternative. "
        "Accept corrections, acknowledge uncertainty and ask when evidence is missing. "
        "Never invent user facts or claim that memory or adaptation was saved. "
        "Training, Nutrition, Brain safety and persistent constraints remain "
        "authoritative. Do not change validated prescriptions for spoken style."
    )


def session_config(language: str) -> dict:
    model = os.getenv("APEX_REALTIME_MODEL", "gpt-realtime-2.1-mini")
    if model not in _MODELS:
        raise ValueError("unsupported_realtime_model")
    return {
        "type": "realtime", "model": model, "output_modalities": ["text"],
        "max_output_tokens": 32,
        "instructions": "Transcription transport only. Do not answer or coach. All responses come from APEX /chat.",
        "tools": [], "tracing": None,
        "audio": {"input": {
            "format": {"type": "audio/pcm", "rate": 24000},
            "transcription": {"model": "gpt-transcribe", "languages": [normalize_language(language)],
                              "prompt": ("Разговор на български с APEX за тренировки и хранене. Възможни са английски имена на упражнения."
                                         if normalize_language(language) == "bg" else
                                         "An English conversation with APEX about training and nutrition. Exercise names may be mentioned.")},
            "turn_detection": {"type": "server_vad", "create_response": False,
                               "interrupt_response": False},
        }},
    }


def exchange_sdp(sdp: str, config: dict) -> tuple[str, str]:
    """One bounded provider request, no automatic retry, no secret/error logging."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("local_credentials_missing")
    boundary = "apex-" + uuid.uuid4().hex
    fields = {"sdp": sdp, "session": json.dumps(config)}
    body = b"".join(
        (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
         f'{value}\r\n').encode("utf-8") for name, value in fields.items()
    ) + f"--{boundary}--\r\n".encode("ascii")
    req = urlrequest.Request(
        "https://api.openai.com/v1/realtime/calls", data=body, method="POST",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "multipart/form-data; boundary=" + boundary},
    )
    with urlrequest.urlopen(req, timeout=15) as result:
        answer = result.read(65537).decode("utf-8")
        if result.status not in {200, 201} or len(answer) > 65536 or not answer.startswith("v=0"):
            raise ValueError("invalid_sdp_answer")
        location = result.headers.get("Location", "")
        match = re.fullmatch(r"(?:https://api\.openai\.com)?/v1/realtime/calls/(rtc_[A-Za-z0-9_-]{1,180})", location)
        if not match:
            raise ValueError("missing_provider_call_identity")
        return answer, match[1]


def hangup_call(call_id: str) -> None:
    """A real provider ACK, not browser cleanup, is required to release a lease."""
    if not re.fullmatch(r"rtc_[A-Za-z0-9_-]{1,180}", call_id):
        raise ValueError("invalid_provider_call_identity")
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("credentials_missing")
    req = urlrequest.Request("https://api.openai.com/v1/realtime/calls/" + call_id + "/hangup",
                             data=b"", method="POST", headers={"Authorization": "Bearer " + key})
    with urlrequest.urlopen(req, timeout=5) as result:
        if result.status not in {200, 204}:
            raise ValueError("provider_hangup_unconfirmed")


class SessionGuard:
    """Server polling + provider hangup. The shared store is the sole authority.

    This is NOT a provider-native TTL: a total application outage can prevent
    scheduled hangup. An unconfirmed hangup never frees another paid API session.
    """
    def __init__(self, store, terminate, identity, enabled, clock=time.time):
        self.store, self.terminate, self.identity = store, terminate, identity
        self.enabled, self.clock = enabled, clock
        self.known = {}
        self.emergency_attempts = {}

    def stop(self, account, lease):
        if lease.get("transport") == "relay":
            from voice import media
            try:
                self.store.request_stop(account, lease["id"])
                media.signal_stop(account, lease["id"])
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    data = self.store.read(account)
                    last = data.get("last_media", {})
                    if not data.get("lease") and last.get("lease") == lease["id"] and last.get("provider_close_ack"):
                        return True
                    time.sleep(.02)
            except Exception:
                media.signal_stop(account, lease["id"])
            return False
        confirmed = False
        try:
            try:
                claimed = self.store.claim_stop(account, lease["id"])
            except Exception:
                # Closing a known provider call must not require an available DB.
                # This counter only bounds emergency hangups, never grants access.
                key = (account, lease["id"])
                count = self.emergency_attempts.get(key, 0)
                if count >= 2:
                    return False
                self.emergency_attempts[key] = count + 1
                claimed = lease
            if not claimed:
                return self.store.read(account).get("lease") is None
            if lease.get("call_id"):
                self.terminate(lease["call_id"])
                confirmed = True
        except Exception:
            pass
        try:
            self.store.finish(account, lease["id"], provider_confirmed=confirmed)
        except Exception:
            confirmed = False
        if confirmed:
            self.known.pop((account, lease["id"]), None)
        return confirmed

    def tick(self):
        try:
            current = self.store.active()
            for account, lease in current:
                key = (account, lease["id"])
                if lease.get("call_id") or key not in self.known:
                    self.known[key] = lease
        except Exception:
            # A DB outage cannot leave a known connection deliberately running.
            return all([self.stop(account, lease) for (account, _), lease in list(self.known.items())])
        success = True
        for account, lease in current:
            try:
                data, actual = self.store.require_lease(account, lease["id"])
                user = self.identity(actual["auth_session"])
                allowed = (self.enabled() and data.get("authorized") is True
                           and user and str(user["id"]) == account
                           and self.clock() < actual["deadline"]
                           and actual["seconds"] <= data["session_seconds"]
                           and data["used_seconds"] <= data["aggregate_seconds"]
                           and actual["state"] not in {"terminating", "termination_unconfirmed"})
            except Exception:
                allowed = False
            if not allowed:
                success = self.stop(account, self.known[(account, lease["id"])]) and success
        return success


_guard = None
_guard_thread = None
_guard_lock = threading.Lock()


def start_guardian():
    """Detached worker uses no Flask context and reads auth from shared storage."""
    global _guard, _guard_thread
    import db
    with _guard_lock:
        if _guard_thread and _guard_thread.is_alive():
            return _guard
        _guard = SessionGuard(sessions, hangup_call, db.get_session_user,
                              lambda: os.getenv("APEX_LIVE_VOICE_ENABLED", "false").lower() == "true")
        def run():
            while True:
                try:
                    _guard.tick()
                except Exception:
                    pass  # Stable failure state is persisted; never log private session data.
                time.sleep(1)
        _guard_thread = threading.Thread(target=run, daemon=True, name="apex-voice-guard")
        _guard_thread.start()
        return _guard


def end_authenticated_session(auth_session, account_id):
    import db
    guard = SessionGuard(sessions, hangup_call, db.get_session_user, lambda: False)
    try:
        lease = sessions.read(account_id).get("lease")
    except Denied:
        return True  # Ordinary accounts have no voice-test policy or lease.
    if not lease or lease.get("auth_session") != str(auth_session):
        return True
    return guard.stop(str(account_id), lease)


def _reply(data, status):
    return jsonify(data), status, {"Cache-Control": "no-store"}


def _authorized_post():
    return (enabled_for(request)
            and request.headers.get("Origin") == request.host_url.rstrip("/")
            and request.headers.get("Sec-Fetch-Site", "same-origin") == "same-origin")


@blueprint.before_request
def authorize_blueprint():
    # Covers UI and every present/future endpoint in this blueprint.
    if not enabled_for(request):
        return _reply({"error": "forbidden"}, 403)


@blueprint.get("/live-voice-test")
def test_ui():
    if not enabled_for(request):
        return _reply({"error": "forbidden"}, 403)
    return Response(render_template("apex.html", live_voice_config=browser_config(request)),
                    headers={"Cache-Control": "no-store"})


@blueprint.post("/api/live-voice/stop")
def stop():
    if not _authorized_post():
        return _reply({"error": "forbidden"}, 403)
    body = request.get_json(silent=True) or {}
    try:
        _, lease = sessions.require_lease(g.user["id"], str(body.get("lease", "")))
        guard = start_guardian()
        if not guard.stop(str(g.user["id"]), lease):
            return _reply({"error": "termination_unconfirmed"}, 503)
    except Denied:
        return _reply({"error": "forbidden"}, 403)
    except Exception:
        return _reply({"error": "session_state_unavailable"}, 503)
    return _reply({"stopped": True}, 200)


@blueprint.post("/api/live-voice/connect")
def connect():
    def reply(data, status):
        response = jsonify(data)
        response.status_code = status
        response.headers["Cache-Control"] = "no-store"
        return response

    if not enabled_for(request):
        return reply({"error": "forbidden"}, 403)
    if (request.headers.get("Origin") != request.host_url.rstrip("/")
            or request.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin"):
        return reply({"error": "invalid_origin"}, 403)
    if browser_config(request)["transport"] != "mock":
        # Never issue SDP or a credential for an independent browser/provider peer.
        return reply({"error": "direct_media_disabled"}, 410)
    if request.mimetype != "application/sdp" or (request.content_length or 0) > 65536:
        return reply({"error": "invalid_sdp"}, 400)
    try:
        body = request.stream.read(65537)
        sdp = body.decode("utf-8")
    except (UnicodeError, ValueError):
        return reply({"error": "invalid_sdp"}, 400)
    if not sdp.startswith("v=0") or len(body) > 65536:
        return reply({"error": "invalid_sdp"}, 400)
    language = request.args.get("lang", "bg")
    if language not in {"bg", "en"}:
        return reply({"error": "invalid_language"}, 400)
    with _lock:
        now = time.monotonic()
        # Cost guard only; no session/entitlement authority or durable identity.
        for subject in list(_attempts):
            _attempts[subject] = [t for t in _attempts[subject] if now - t < 300]
            if not _attempts[subject]:
                del _attempts[subject]
        subject = str(g.user["id"])
        stamps = _attempts.setdefault(subject, [])
        if len(stamps) >= 6:
            return reply({"error": "rate_limited"}, 429)
        stamps.append(now)
    if browser_config(request)["transport"] == "mock":
        return reply({"transport": "mock", "live_tested": False}, 200)
    return reply({"error": "direct_media_disabled"}, 410)


@blueprint.get("/api/live-voice/media")
def media_requires_websocket():
    # Keep ordinary HTTP probes behind the same 403 authorization boundary.
    # This route never reserves usage or opens a provider connection.
    return _reply({"error": "websocket_required"}, 426)


@blueprint.route("/api/live-voice/media", websocket=True)
def media_socket():
    if not _authorized_post() or browser_config(request)["transport"] != "relay":
        return _reply({"error": "forbidden"}, 403)
    language = request.args.get("lang", "bg")
    if language not in {"bg", "en"}:
        return _reply({"error": "invalid_language"}, 400)
    try:
        lease = sessions.reserve(g.user["id"], request.cookies.get("apex_session"))
    except Denied as error:
        return _reply({"error": str(error)}, 429)
    except Exception:
        return _reply({"error": "session_state_unavailable"}, 503)
    try:
        grant = charging.control.reserve(str(g.user["id"]), request.cookies.get("apex_session"),
            "transcription", (lease["seconds"] + 256) * 1000)
    except Exception:
        # No provider has been opened, so releasing this unused media lease is safe.
        sessions.finish(g.user["id"], lease["id"], provider_confirmed=True)
        return _reply({"error": "test_budget_unavailable"}, 429)
    from simple_websocket import Server
    from voice import media
    try:
        ws = Server.accept(request.environ, max_message_size=media.FRAME_BYTES, ping_interval=10)
    except Exception:
        sessions.finish(g.user["id"], lease["id"], provider_confirmed=True)
        return _reply({"error": "upgrade_failed"}, 400)
    import db
    # Capture only verified identity and immutable request values before detaching.
    media.serve(ws, str(g.user["id"]), lease, sessions, db.get_session_user,
                lambda: os.getenv("APEX_LIVE_VOICE_ENABLED", "false").lower() == "true",
                session_config(language), safety=(charging.control, grant))
    return ""
