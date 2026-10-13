from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

import app as appmod
import db as store


def account(email="profile-trust@example.test"):
    uid = store.get_or_create_user(email)
    client = appmod.app.test_client()
    response = client.get("/auth/verify?token=" + store.create_login_token(uid))
    assert response.location == "/app?auth=ok"
    return client, uid


@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.parametrize("path", ["/auth/me", "/api/profile", "/api/history", "/api/conversations"])
def test_sensitive_reads_are_private_and_not_stored(path, authenticated):
    client = account()[0] if authenticated else appmod.app.test_client()
    response = client.get(path)
    assert response.status_code == (200 if authenticated or path == "/auth/me" else 401)
    assert response.headers["Cache-Control"] == "private, no-store"


def test_partial_profile_save_preserves_unedited_account_fields_and_explicit_clear():
    client, uid = account()
    original = {"goal": "strength", "age": "33", "language": "en", "allergies": "test food",
                "foodPreferences": ["test preference"], "preferences": {"test": True},
                "injuries": "synthetic note", "healthNotes": "independent synthetic account evidence",
                "_medical_hold": {"status": "ACTIVE_MEDICAL_HOLD"}}
    store.save_profile(uid, original)
    store.add_account_training_constraints(uid, ("vertical_push",))
    response = client.put("/api/profile", json={"profile": {
        "age": "34", "injuries": "", "training_constraints": []}})
    expected = {**original, "age": "34", "injuries": ""}
    assert response.status_code == 200
    assert response.json == {"ok": True, "profile": expected}
    assert store.get_profile(uid) == expected
    assert client.get("/api/profile").json["profile"] == expected
    assert store.list_account_training_constraints(uid) == ("vertical_push",)


def test_profile_account_ownership_is_not_taken_from_client_payload():
    first, first_id = account()
    second, second_id = account("profile-other@example.test")
    store.save_profile(first_id, {"notes": "account A", "allergies": "test food"})
    second.put("/api/profile", json={"profile": {"age": "40"}, "user_id": first_id})
    assert second.get("/api/profile").json["profile"] == {"age": "40"}
    assert store.get_profile(first_id) == {"notes": "account A", "allergies": "test food"}
    assert store.get_profile(second_id) == {"age": "40"}


def test_concurrent_profile_merges_do_not_erase_omitted_fields():
    _, uid = account()
    store.save_profile(uid, {"allergies": "test food", "preferences": {"test": True}})
    barrier = Barrier(2)
    def write(changes):
        barrier.wait()
        return store.merge_profile(uid, changes)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(write, changes) for changes in ({"age": "35"}, {"equipment": "home"})]
        for result in futures:
            result.result(timeout=10)
    assert store.get_profile(uid) == {"allergies": "test food", "preferences": {"test": True},
                                     "age": "35", "equipment": "home"}


def test_profile_merge_failure_does_not_acknowledge_persistence(monkeypatch):
    client, uid = account()
    store.save_profile(uid, {"age": "33"})
    def failed(*args, **kwargs):
        raise RuntimeError("private synthetic error")
    monkeypatch.setattr(store, "merge_profile", failed)
    response = client.put("/api/profile", json={"profile": {"age": "44"}})
    assert response.status_code == 503
    assert response.json == {"error": "profile_save_unavailable"}
    assert store.get_profile(uid) == {"age": "33"}


def test_constraint_record_read_failure_is_not_confirmed_empty(monkeypatch):
    client, _ = account()
    monkeypatch.setattr(store, "list_account_training_constraints", lambda *args: ())
    def failed(*args, **kwargs):
        raise RuntimeError("private synthetic error")
    monkeypatch.setattr(store, "list_account_training_constraint_records", failed)
    response = client.get("/api/profile")
    assert response.status_code == 200
    assert response.json["training_constraint_load_state"] == "unavailable"
    assert response.json["training_constraints"] is None
    assert response.json["training_constraint_records"] is None


def test_constraint_truth_survives_reauthentication_and_does_not_cross_accounts():
    client, uid = account()
    store.add_account_training_constraints(uid, ("vertical_push",))
    assert client.get("/api/profile").json["training_constraint_records"][0]["pattern"] == "vertical_push"
    assert client.post("/auth/logout").json == {"ok": True}
    assert client.get("/api/profile").status_code == 401
    client.get("/auth/verify?token=" + store.create_login_token(uid))
    assert client.get("/api/profile").json["training_constraints"] == ["vertical_push"]
    assert account("profile-other@example.test")[0].get("/api/profile").json["training_constraints"] == []


def test_failed_logout_keeps_server_session_and_does_not_clear_cookie(monkeypatch):
    client, _ = account()
    def failed(*args):
        raise RuntimeError("private synthetic error")
    monkeypatch.setattr(store, "revoke_session", failed)
    response = client.post("/auth/logout")
    assert response.status_code == 503
    assert response.json == {"error": "logout_unavailable"}
    assert not any(appmod.SESSION_COOKIE + "=" in value for value in response.headers.getlist("Set-Cookie"))
    assert client.get("/auth/me").json["authenticated"] is True


def test_successful_logout_revokes_session_and_acknowledges():
    client, _ = account()
    assert client.post("/auth/logout").json == {"ok": True}
    assert client.get("/auth/me").json["authenticated"] is False
