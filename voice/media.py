"""Server-owned, bounded PCM relay. Browsers never connect to OpenAI.

Only 24 kHz mono PCM16 is accepted; provider commands are constructed here.
Transcripts still enter the existing /chat authority. No audio/content is stored.
On process death the OS closes the ONLY upstream media socket; no browser peer
or bearer credential exists that could keep feeding the provider independently.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid

import websocket


_local = {}
_lock = threading.Lock()
SAMPLE_RATE = 24000
FRAME_BYTES = 4800  # 100 ms; bounded incoming WebSocket message size.


def signal_stop(account_id, lease_id):
    with _lock:
        event = _local.get((str(account_id), lease_id))
    if event:
        event.set()


class Upstream:
    def __init__(self, config, clock=time.monotonic):
        self.clock = clock
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("credentials_missing")
        model = config["model"]
        if model not in {"gpt-realtime-2.1-mini", "gpt-realtime-2.1"}:
            raise RuntimeError("unsupported_model")
        self.socket = websocket.create_connection(
            "wss://api.openai.com/v1/realtime?model=" + model,
            header={"Authorization": "Bearer " + key}, timeout=5, enable_multithread=True,
            suppress_origin=True, redirect_limit=0,
        )
        try:
            self.socket.settimeout(.05)
            settings = dict(config)
            settings.pop("model", None)  # The immutable model was selected in the server URL.
            self.socket.send(json.dumps({"type": "session.update", "session": settings}))
            deadline = clock() + 5
            while clock() < deadline:
                event = self.receive()
                if event and event.get("type") == "error":
                    raise RuntimeError("provider_configuration_rejected")
                if event and event.get("type") == "session.updated":
                    actual = event.get("session", {})
                    if actual.get("model") != model and not str(actual.get("model", "")).startswith(model + "-"):
                        raise RuntimeError("provider_model_mismatch")
                    vad = actual.get("audio", {}).get("input", {}).get("turn_detection", {})
                    if vad.get("create_response") is not False or actual.get("tools"):
                        raise RuntimeError("provider_authority_mismatch")
                    audio = actual.get("audio", {}).get("input", {})
                    # These are provider-acknowledged limits, not prompt promises.
                    # The output cap does NOT limit separately billed transcription.
                    tokens = actual.get("max_output_tokens")
                    if (type(tokens) is not int or not 1 <= tokens <= 32
                            or actual.get("output_modalities") != ["text"]
                            or audio.get("transcription", {}).get("model") != "gpt-transcribe"
                            or audio.get("format") != {"type": "audio/pcm", "rate": SAMPLE_RATE}):
                        raise RuntimeError("provider_cost_contract_mismatch")
                    break
            else:
                raise RuntimeError("provider_configuration_timeout")
        except BaseException:
            self.socket.shutdown()
            raise

    def receive(self):
        try:
            message = self.socket.recv()
        except websocket.WebSocketTimeoutException:
            return None
        if not message:
            raise RuntimeError("provider_disconnected")
        if not isinstance(message, str) or len(message) > 65536:
            raise RuntimeError("provider_event_too_large")
        return json.loads(message)

    def audio(self, frame):
        self.socket.send(json.dumps({"type": "input_audio_buffer.append",
                                     "audio": base64.b64encode(frame).decode("ascii")}))

    def close(self):
        """Only a provider Close frame counts as acknowledged graceful shutdown."""
        confirmed = False
        try:
            self.socket.settimeout(.5)
            self.socket.send_close()
            deadline = self.clock() + 1
            while self.clock() < deadline:
                opcode, _ = self.socket.recv_data_frame(control_frame=True)
                if opcode == websocket.ABNF.OPCODE_CLOSE:
                    confirmed = True
                    break
        except Exception:
            pass
        finally:
            self.socket.shutdown()  # Always physically close, including on ACK timeout.
        return confirmed

    def abort(self):
        self.socket.shutdown()


def serve(downstream, account_id, lease, store, identity, enabled, config,
          factory=None, clock=time.monotonic, wall=time.time, safety=None):
    stop = threading.Event()
    key = (str(account_id), lease["id"])
    with _lock:
        _local[key] = stop
    upstream = None
    confirmed = False
    accepted = 0
    max_input_samples = int(lease["seconds"]) * SAMPLE_RATE
    usage = []
    connected_at = clock()
    deadline = connected_at + max(0, lease["deadline"] - wall())
    aliases = {}
    committed = set()
    reason = "closed"
    deadline_timer = None
    try:
        store.bind_media(account_id, lease["id"], uuid.uuid4().hex)
        if safety:
            safety[0].require(account_id, safety[1]["epoch"])
        upstream = (factory or Upstream)(config)
        # A blocked DB read must not keep the server's media socket alive.
        deadline_timer = threading.Timer(max(0, deadline - clock()), upstream.abort)
        deadline_timer.daemon = True
        deadline_timer.start()
        next_check = 0
        next_checkpoint = clock() + 1
        downstream.send(json.dumps({"type": "session.ready", "seconds": lease["seconds"]}))
        # Reserve the final second for a provider Close handshake; the independent
        # timer still tears down the socket at the hard deadline if it stalls.
        while not stop.is_set() and clock() < deadline - 1:
            if clock() >= next_check:
                if safety:
                    safety[0].require(account_id, safety[1]["epoch"])
                data, current = store.require_lease(account_id, lease["id"])
                user = identity(current["auth_session"])
                if (not enabled() or data.get("authorized") is not True
                        or not user or str(user["id"]) != str(account_id)
                        or current["state"] != "active"
                        or current["seconds"] > data["session_seconds"]
                        or data["used_seconds"] > data["aggregate_seconds"]):
                    break
                next_check = clock() + .25
            frame = downstream.receive(timeout=.01)
            if frame is not None:
                if not isinstance(frame, bytes) or not frame or len(frame) > FRAME_BYTES or len(frame) % 2:
                    raise RuntimeError("invalid_audio_frame")
                samples = len(frame) // 2
                # Absolute chargeable-input ceiling, independent of wall-clock
                # pacing, pending transcription, or when the worker crashes.
                if accepted + samples > max_input_samples:
                    raise RuntimeError("audio_budget_exceeded")
                # No fast-forward/flooding of chargeable audio, even from a modified client.
                if accepted + samples > (clock() - connected_at + .5) * SAMPLE_RATE:
                    raise RuntimeError("audio_rate_exceeded")
                if clock() >= deadline or stop.is_set():
                    break
                upstream.audio(frame)
                accepted += samples
                downstream.send(json.dumps({"type": "audio.accepted"}))
            if clock() >= next_checkpoint:
                store.media_checkpoint(account_id, lease["id"], accepted_samples=accepted, usage=usage)
                next_checkpoint = clock() + 1
            event = upstream.receive()
            if not event:
                continue
            kind = event.get("type", "")
            if kind == "error" or kind.startswith("response."):
                raise RuntimeError("provider_authority_error")
            if kind == "input_audio_buffer.committed":
                ident = event.get("item_id")
                if not isinstance(ident, str) or len(committed) >= 128:
                    raise RuntimeError("turn_limit")
                committed.add(ident)
            if kind == "conversation.item.input_audio_transcription.completed":
                text = event.get("transcript")
                source_id = event.get("item_id")
                if not isinstance(text, str) or not text.strip() or len(text) > 4000 or not isinstance(source_id, str):
                    raise RuntimeError("invalid_transcription")
                new_item = source_id not in aliases
                if new_item:
                    if len(aliases) >= 128:
                        raise RuntimeError("turn_limit")
                    aliases[source_id] = uuid.uuid4().hex
                projection = {"type": kind, "item_id": aliases[source_id], "transcript": text}
                if isinstance(event.get("languages"), list):
                    projection["languages"] = [{"code": item["code"]} for item in event["languages"][:4]
                        if isinstance(item, dict) and isinstance(item.get("code"), str) and len(item["code"]) <= 8]
                if isinstance(event.get("logprobs"), list):
                    projection["logprobs"] = [{"logprob": item["logprob"]} for item in event["logprobs"][:512]
                        if isinstance(item, dict) and isinstance(item.get("logprob"), (int, float))]
                downstream.send(json.dumps(projection))
                # Technical counts only. Never persist transcript/audio/provider IDs.
                if new_item and isinstance(event.get("usage"), dict) and len(usage) < 128:
                    raw = event["usage"]
                    usage.append({name: raw[name] for name in ("input_tokens", "output_tokens", "total_tokens", "seconds", "duration")
                                  if isinstance(raw.get(name), (int, float))})
            elif kind in {"input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped"}:
                downstream.send(json.dumps({"type": kind}))
    except Exception:
        reason = "test_session_ended" if safety else "media_unavailable"
        # Shared OFF/exhaustion/outage must stop the microphone, not trigger the
        # browser's ordinary transport-error fallback into another voice path.
        if not safety:
            try:
                downstream.send(json.dumps({"type": "error", "code": reason}))
            except Exception:
                pass
    finally:
        if deadline_timer:
            deadline_timer.cancel()
        if upstream:
            confirmed = upstream.close()
        else:
            # A partially failed constructor may have opened an upstream socket.
            # Absence of a usable adapter is not proof of provider shutdown.
            confirmed = False
        # Settle only complete provider-reported duration usage. Pending/missing
        # usage (including crash) retains the entire conservative reservation.
        if safety and confirmed and committed and committed == set(aliases) and len(usage) == len(committed):
            seconds = [item.get("seconds") for item in usage]
            if all(type(value) in (int, float) and 0 <= value <= lease["seconds"] + 1 for value in seconds):
                import math
                try:
                    safety[0].reconcile(safety[1], math.ceil(sum(seconds) * 75))
                except Exception:
                    pass
        try:
            store.media_finished(account_id, lease["id"], confirmed=confirmed,
                facts={"accepted_samples": accepted, "sample_rate": SAMPLE_RATE,
                       "elapsed_ms": round((clock() - connected_at) * 1000), "usage": usage})
        except Exception:
            pass  # Durable reservation stays fail-closed if commit is unavailable.
        with _lock:
            _local.pop(key, None)
        try:
            downstream.send(json.dumps({"type": "session.ended", "reason": reason}))
            downstream.close()
        except Exception:
            pass
