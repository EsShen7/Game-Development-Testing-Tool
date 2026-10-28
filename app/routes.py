"""HTTP adapter: consistent envelopes, identity in session, all rules in services."""

from flask import Blueprint, current_app, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException

from .services import ApiError

bp = Blueprint("main", __name__)


def json_payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("Request body must be a JSON object.")
    return payload


def service():
    return current_app.extensions["playtest_service"]


def actor_id():
    return session.get("user_id", 1)


def success(data, status=200):
    return jsonify({"ok": True, "data": data}), status


@bp.errorhandler(ApiError)
def api_error(error):
    return jsonify({"ok": False, "error": {"message": error.message, "status": error.status}}), error.status


@bp.errorhandler(RuntimeError)
def storage_error(error):
    return jsonify({"ok": False, "error": {"message": str(error), "status": 500}}), 500


@bp.errorhandler(OSError)
def storage_io_error(error):
    return jsonify({"ok": False, "error": {"message": "The local data file could not be saved. No partial update was committed.", "status": 500}}), 500


@bp.app_errorhandler(HTTPException)
def http_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": {"message": error.description, "status": error.code}}), error.code
    return error


@bp.get("/")
def index():
    return render_template("index.html", page="dashboard")


@bp.get("/<page>")
def pages(page):
    if page not in {"dashboard", "games", "bugs", "feedback"}:
        raise ApiError("Page was not found.", 404)
    return render_template("index.html", page=page)


@bp.get("/api/identity")
def identity():
    return success(service().identity(actor_id()))


@bp.post("/api/identity")
def switch_identity():
    payload = json_payload()
    chosen = service().switch_identity(payload.get("user_id"))
    session["user_id"] = chosen["user_id"]
    return success({"current": chosen, "demo": True})


@bp.post("/api/register")
def register():
    payload = json_payload()
    payload["role"] = "Tester"
    result = service().register(payload)
    session["user_id"] = result["user_id"]
    return success(result, 201)


@bp.get("/api/dashboard")
def dashboard():
    return success(service().dashboard())


@bp.get("/api/<table>")
def list_records(table):
    return success(service().list(table, actor_id(), request.args))


@bp.post("/api/candidates")
def candidates():
    return success(service().candidates(json_payload(), actor_id()))


@bp.post("/api/merge")
def merge():
    payload = json_payload()
    return success(service().merge(payload.get("source_bug_id"), payload.get("target_bug_id"), actor_id()))


@bp.post("/api/associate")
def associate():
    return success(service().associate_occurrence(json_payload(), actor_id()))


@bp.get("/api/<table>/<int:record_id>")
def get_record(table, record_id):
    return success(service().get(table, record_id, actor_id()))


@bp.post("/api/<table>")
def create_record(table):
    return success(service().create(table, json_payload(), actor_id()), 201)


@bp.put("/api/<table>/<int:record_id>")
def update_record(table, record_id):
    return success(service().update(table, record_id, json_payload(), actor_id()))


@bp.delete("/api/<table>/<int:record_id>")
def delete_record(table, record_id):
    return success(service().delete(table, record_id, actor_id()))
