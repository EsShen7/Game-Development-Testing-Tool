import json

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "JSON_FILE": str(tmp_path / "data.json"), "SEED_DATA": True})
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def ok(response, status=200):
    assert response.status_code == status
    payload = response.get_json()
    assert payload["ok"] is True
    return payload["data"]


def switch(client, user_id):
    ok(client.post("/api/identity", json={"user_id": user_id}))


def test_dashboard_comparison_and_priority(client):
    result = ok(client.get("/api/dashboard"))
    assert len(result["games"]) == 1
    builds = result["games"][0]["versions"]
    assert [row["version"]["version_name"] for row in builds] == ["0.9.0", "1.0.0"]
    assert [row["bug_count"] for row in builds] == [2, 1]
    assert builds[0]["report_count"] == 3
    assert builds[1]["average_rating"] == 5
    assert result["high_priority"][0]["bug_id"] == 2


def test_create_and_persist_game_and_version(app, client):
    switch(client, 3)
    game = ok(client.post("/api/games", json={"title": "Deep Current", "genre": "Adventure"}), 201)
    version = ok(client.post("/api/game_versions", json={"game_id": game["game_id"], "version_name": "0.1"}), 201)
    reopened = create_app({"TESTING": True, "SECRET_KEY": "test", "JSON_FILE": app.config["JSON_FILE"], "SEED_DATA": False})
    games = reopened.test_client().get("/api/games").get_json()["data"]
    assert any(g["title"] == "Deep Current" for g in games)
    assert version["game_id"] == game["game_id"]


def test_tester_cannot_impersonate_another_user_in_payload(client):
    # User 1 cannot register a session owned by user 2, even when user_id is forged.
    response = client.post("/api/playtest_sessions", json={"user_id": 2, "version_id": 2})
    session = ok(response, 201)
    assert session["user_id"] == 1
    assert client.get("/api/playtest_sessions/2").status_code == 404
    forbidden = client.post("/api/feedback", json={"session_id": 4, "rating": 3})
    assert forbidden.status_code == 403
    assert forbidden.get_json()["ok"] is False


def test_report_candidate_link_merge_and_rollup(client):
    blocked_link = client.post("/api/bug_reports", json={
        "session_id": 1, "existing_bug_id": 1, "title": "Camera clips through the lighthouse wall",
        "category": "Visual", "severity": 3, "impact": 3
    })
    assert blocked_link.status_code == 403
    created = ok(client.post("/api/bug_reports", json={
        "session_id": 1,
        "title": "Camera clips through the lighthouse wall again",
        "category": "Visual", "severity": 5, "impact": 4, "notes": "New route reproduces it."
    }), 201)
    assert created["candidate"] is False
    assert created["bug"]["bug_id"] == 4
    switch(client, 3)
    merged = ok(client.post("/api/merge", json={"source_bug_id": 4, "target_bug_id": 1}))
    assert merged["moved_occurrences"] == 1
    data = client.get("/api/bug_reports/1").get_json()["data"]
    assert data["title"] == "Camera clips through the lighthouse wall"
    assert data["severity"] == 3
    assert data["occurrence_count"] == 3
    assert client.get("/api/bug_reports/4").status_code == 404


def test_validation_conflicts_and_uniform_malformed_json(client):
    duplicate = client.post("/api/users", json={"name": "Duplicate", "email": "AVERY@example.com", "role": "Tester"})
    assert duplicate.status_code == 403  # tester role gate precedes data validation
    switch(client, 4)
    duplicate = client.post("/api/users", json={"name": "Duplicate", "email": "AVERY@example.com", "role": "Tester"})
    assert duplicate.status_code == 409
    assert duplicate.get_json()["ok"] is False
    bad_shape = client.post("/api/identity", json=[1, 2])
    assert bad_shape.status_code == 400
    assert bad_shape.get_json()["ok"] is False
    switch(client, 1)
    bad_integer = client.post("/api/playtest_sessions", json={"user_id": 2, "version_id": 1.4})
    # Floats must not be truncated to an integer ID.
    assert bad_integer.status_code == 400


def test_cross_version_reference_and_session_feedback_uniqueness(client):
    switch(client, 3)
    wrong_version = client.post("/api/bug_occurrences", json={"bug_id": 1, "session_id": 3, "version_id": 2, "notes": "bad ref"})
    assert wrong_version.status_code == 400
    switch(client, 1)
    duplicate_feedback = client.post("/api/feedback", json={"session_id": 1, "rating": 2})
    assert duplicate_feedback.status_code == 409
    invalid_rating = client.post("/api/feedback", json={"session_id": 3, "rating": 6})
    assert invalid_rating.status_code == 400


def test_developer_cannot_change_user_role_and_admin_cannot_delete_active_user(client):
    switch(client, 3)
    forbidden = client.put("/api/users/1", json={"role": "Developer"})
    assert forbidden.status_code == 403
    switch(client, 4)
    active_delete = client.delete("/api/users/4")
    assert active_delete.status_code == 409


def test_transaction_failure_does_not_partially_write(app, client):
    path = app.config["JSON_FILE"]
    before = open(path, encoding="utf-8").read()
    switch(client, 3)
    response = client.post("/api/game_versions", json={"game_id": 1, "version_name": "0.9.0"})
    assert response.status_code == 409
    assert open(path, encoding="utf-8").read() == before


def test_corrupt_storage_fails_without_overwriting(app, client):
    path = app.config["JSON_FILE"]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{broken-json")
    response = client.get("/api/games")
    assert response.status_code == 500
    assert response.get_json()["ok"] is False
    assert open(path, encoding="utf-8").read() == "{broken-json"


def test_api_unknown_path_is_json(client):
    response = client.get("/api/not-an-entity")
    assert response.status_code == 404
    assert response.get_json()["ok"] is False


def test_empty_workspace_keeps_demo_identities(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "JSON_FILE": str(tmp_path / "empty.json"), "SEED_DATA": False})
    client = app.test_client()
    identity = ok(client.get("/api/identity"))
    assert len(identity["users"]) == 4
    assert identity["current"]["role"] == "Tester"
    assert ok(client.get("/api/games")) == []
    switch(client, 3)
    ok(client.post("/api/games", json={"title": "First game"}), 201)


def test_atomic_replace_failure_returns_json_and_preserves_file(app, client, monkeypatch):
    import app.storage as storage

    path = app.config["JSON_FILE"]
    original = open(path, "rb").read()
    switch(client, 3)

    def fail_replace(source, destination):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    response = client.post("/api/games", json={"title": "Not persisted"})
    assert response.status_code == 500
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["status"] == 500
    assert open(path, "rb").read() == original
