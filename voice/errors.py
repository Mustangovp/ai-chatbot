"""Public voice errors contain categories, never provider or account details."""


def public_error(error, *, media=False):
    reason = str(error)
    if reason == "test_disabled":
        reason = "pilot_disabled"
    if reason in {"tts_pilot_exhausted", "tts_operation_limit"}:
        return {"error": "tts_quota_exhausted", "terminal": True}, 429
    if reason == "usage_exhausted":
        return {"error": "media_quota_exhausted", "terminal": True}, 429
    if reason == "test_budget_exhausted":
        return {"error": "pilot_limit_reached", "terminal": True}, 429
    if reason in {"pilot_expired", "pilot_disabled"}:
        return {"error": reason, "terminal": True}, 403
    if reason in {"unauthenticated", "tester_not_authorized", "tester_mismatch"}:
        return {"error": "forbidden", "terminal": True}, 403
    if reason in {"tts_already_active", "session_already_reserved"}:
        code = "media_session_active" if media else "tts_busy"
        return {"error": code, "terminal": False}, 429
    if reason == "tts_estimate_unavailable":
        return {"error": "tts_input_unavailable", "terminal": False}, 400
    return {"error": "pilot_unavailable", "terminal": True}, 503
