"""
REFACTOR-001 — internal admin & Brain-debug routes, extracted verbatim from app.py
into a Flask Blueprint to keep app.py as the application entry point.

Behaviour is identical to the previous inline routes: same URL paths, same gating,
same handlers. Every endpoint 404s unless its token/flag is explicitly set, so none
of this is reachable in production by default:

  • /debug/brain/*   → 404 unless BRAIN_DEBUG is set (developer-only Brain inspection)
  • /admin/brain     → 404 unless ADMIN_TOKEN matches (M5 Brain Observatory)
  • /admin/hse[...]  → 404 unless ADMIN_TOKEN matches (BUILD-002 HSE Observatory)

This module imports only downstream/observability layers (never composes the cascade),
so it introduces no new coupling and no import cycle with app.py.
"""
import os

from flask import Blueprint, jsonify, request, render_template, redirect

import db as store
import brain.config as brain_config
import brain.inspector as brain_inspector
import brain.replay as brain_replay
import brain_analytics
import human_state.observatory as human_state_observatory

bp = Blueprint("admin", __name__)


# ── Brain Inspector — developer-only inspection endpoints ─────────────────────
# 404 unless BRAIN_DEBUG is explicitly set → never exposed in production.
def _brain_debug_on():
    return brain_config.brain_debug()


@bp.route("/debug/brain/decision/<decision_id>")
def debug_brain_decision(decision_id):
    """Inspect one stored shadow decision by its stable Decision ID."""
    if not _brain_debug_on():
        return jsonify({"error": "not_found"}), 404
    row = store.get_brain_decision(decision_id)
    if not row:
        return jsonify({"error": "not_found"}), 404
    return jsonify(row)


@bp.route("/debug/brain/replay", methods=["POST"])
def debug_brain_replay():
    """Replay the Brain over supplied evidence and return the full trace.
    (Raw evidence is not persisted in the ledger by design, so replay runs on
    the profile you provide.)"""
    if not _brain_debug_on():
        return jsonify({"error": "not_found"}), 404
    data = request.get_json(silent=True) or {}
    profile = data.get("profile") or {}
    if not isinstance(profile, dict):
        return jsonify({"error": "invalid_profile"}), 400
    return jsonify(brain_inspector.inspect(profile, message=data.get("message"),
                                           conversation=data.get("conversation"),
                                           physiology=data.get("physiology"),
                                           model=data.get("model")))


@bp.route("/debug/brain/replay-compare", methods=["POST"])
def debug_brain_replay_compare():
    """Replay evidence against a baseline trace → classification + deltas."""
    if not _brain_debug_on():
        return jsonify({"error": "not_found"}), 404
    data = request.get_json(silent=True) or {}
    evidence = data.get("evidence") or {}
    baseline = data.get("baseline")
    if not isinstance(evidence, dict) or not isinstance(baseline, dict):
        return jsonify({"error": "invalid_input"}), 400
    return jsonify(brain_replay.replay(evidence, baseline, model=data.get("model")))


@bp.route("/debug/brain/regression", methods=["POST"])
def debug_brain_regression():
    """Regression report over cases vs baselines (suitable for the 140-persona
    corpus). If `baselines` is omitted, returns freshly-snapshotted baselines."""
    if not _brain_debug_on():
        return jsonify({"error": "not_found"}), 404
    data = request.get_json(silent=True) or {}
    cases = data.get("cases") or []
    if not isinstance(cases, list):
        return jsonify({"error": "invalid_cases"}), 400
    baselines = data.get("baselines")
    if not isinstance(baselines, dict):
        return jsonify({"baselines": brain_replay.snapshot(cases, model=data.get("model"))})
    return jsonify(brain_replay.replay_corpus(cases, baselines, model=data.get("model")))


# ── M5 Brain Observatory dashboard ──────────────────────────────────────────
# Gated by ADMIN_TOKEN (?key=…). 404s when the token is unset or wrong, so the
# page never reveals itself in production. Read-only analytics; no Brain logic.
@bp.route("/admin/brain")
def admin_brain():
    token = os.getenv("ADMIN_TOKEN", "")
    if not token or request.args.get("key", "") != token:
        return jsonify({"error": "not_found"}), 404
    return render_template("admin_brain.html", d=brain_analytics.observatory(), key=token)


# ── BUILD-002 Human State Observatory dashboard (admin-gated, internal) ──────
@bp.route("/admin/hse")
def admin_hse():
    token = os.getenv("ADMIN_TOKEN", "")
    if not token or request.args.get("key", "") != token:
        return jsonify({"error": "not_found"}), 404
    subject = request.args.get("subject") or None
    return render_template("admin_hse.html",
                           d=human_state_observatory.report(subject=subject),
                           key=token, subject=subject or "")


@bp.route("/admin/hse/review", methods=["POST"])
def admin_hse_review():
    token = os.getenv("ADMIN_TOKEN", "")
    if not token or request.values.get("key", "") != token:
        return jsonify({"error": "not_found"}), 404
    try:
        store.hse_add_review(request.values.get("event_id"), request.values.get("entity", ""),
                             request.values.get("verdict", ""), request.values.get("note"),
                             reviewer="admin")
    except Exception as e:
        print(f"[hse-obs] review failed: {e}")
    return redirect(f"/admin/hse?key={token}")
