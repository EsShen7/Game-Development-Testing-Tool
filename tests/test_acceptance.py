"""Independent acceptance checks for the storage seam and reference integrity."""

from unittest.mock import patch

from app import create_app


def test_write_failure_preserves_original_snapshot(tmp_path):
    app = create_app({"TESTING": True, "JSON_FILE": str(tmp_path / "data.json")})
    store = app.extensions["playtest_service"].store
    before = store.read()
    with patch("app.storage.os.replace", side_effect=OSError("simulated disk failure")):
        try:
            store.transact(lambda data: data["games"].clear())
        except OSError:
            pass
        else:
            raise AssertionError("Write failure must propagate")
    assert store.read() == before


def test_new_build_has_no_ratings_and_session_timestamp(tmp_path):
    app = create_app({"TESTING": True, "JSON_FILE": str(tmp_path / "data.json")})
    client = app.test_client()
    client.post("/api/identity", json={"user_id": 3})
    response = client.post("/api/game_versions", json={"game_id": 1, "version_name": "acceptance"})
    assert response.status_code == 201
    version = response.get_json()["data"]
    client.post("/api/identity", json={"user_id": 1})
    response = client.post("/api/playtest_sessions", json={"user_id": 1, "version_id": version["version_id"]})
    assert response.status_code == 201
    assert response.get_json()["data"]["tested_at"]
    rows = client.get("/api/dashboard").get_json()["data"]["games"][0]["versions"]
    assert next(r for r in rows if r["version"]["version_id"] == version["version_id"])["average_rating"] is None


def test_referenced_bug_cannot_move_to_other_version(tmp_path):
    app = create_app({"TESTING": True, "JSON_FILE": str(tmp_path / "data.json")})
    client = app.test_client()
    client.post("/api/identity", json={"user_id": 3})
    response = client.put("/api/bug_reports/1", json={"version_id": 2})
    assert response.status_code in (400, 409)
    assert client.get("/api/bug_reports/1").get_json()["data"]["version_id"] == 1
