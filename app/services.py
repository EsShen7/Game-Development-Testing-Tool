"""Business rules for the seven schema entities; routes never touch JSON directly."""

from datetime import date, datetime
import re

from .storage import TABLES


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


KEYS = {
    "users": "user_id", "games": "game_id", "game_versions": "version_id",
    "playtest_sessions": "session_id", "bug_reports": "bug_id",
    "bug_occurrences": "occurrence_id", "feedback": "feedback_id",
}
ROLES = {"Tester", "Developer", "Admin"}
STATUSES = {"Open", "In Progress", "Fixed", "Closed"}
FIELDS = {
    "users": {"name", "email", "role"}, "games": {"title", "genre"},
    "game_versions": {"game_id", "version_name", "release_date"},
    "playtest_sessions": {"user_id", "version_id", "tested_at"},
    "bug_reports": {"version_id", "title", "category", "severity", "impact", "status"},
    "bug_occurrences": {"bug_id", "session_id", "version_id", "notes", "reported_at"},
    "feedback": {"session_id", "rating", "comments"},
}


def _find(rows, key, value):
    return next((row for row in rows if row.get(key) == value), None)


def _require(data, table, key, value, label):
    row = _find(data[table], key, value)
    if row is None:
        raise ApiError(f"{label} was not found.", 404)
    return row


def _int(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or (isinstance(value, str) and not re.fullmatch(r"[+-]?\d+", value.strip())):
        raise ApiError(f"{field} must be an integer.")
    try:
        return int(value)
    except ValueError:
        raise ApiError(f"{field} must be an integer.")


class PlaytestService:
    def __init__(self, store):
        self.store = store

    def _actor(self, data, actor_id):
        return _require(data, "users", "user_id", actor_id, "演示用户")

    def identity(self, actor_id):
        data = self.store.read()
        actor = self._actor(data, actor_id)
        return {"current": actor, "users": data["users"], "demo": True}

    def switch_identity(self, chosen_id):
        data = self.store.read()
        return _require(data, "users", "user_id", _int(chosen_id, "user_id"), "演示用户")

    def register(self, payload):
        def op(data):
            synthetic_admin = {"user_id": 0, "role": "Admin"}
            row = self._clean(data, "users", {**payload, "role": "Tester"}, None, synthetic_admin)
            row["user_id"] = self._next(data, "users")
            data["users"].append(row)
            return row
        return self.store.transact(op)

    @staticmethod
    def _role(actor, roles):
        if actor["role"] not in roles:
            raise ApiError("This demo identity is not allowed to perform this action.", 403)

    def _scope(self, data, table, actor):
        rows = data[table]
        if actor["role"] != "Tester":
            return rows
        if table == "playtest_sessions":
            return [r for r in rows if r["user_id"] == actor["user_id"]]
        if table == "feedback":
            owned = {r["session_id"] for r in data["playtest_sessions"] if r["user_id"] == actor["user_id"]}
            return [r for r in rows if r["session_id"] in owned]
        if table == "bug_occurrences":
            owned = {r["session_id"] for r in data["playtest_sessions"] if r["user_id"] == actor["user_id"]}
            return [r for r in rows if r["session_id"] in owned]
        if table == "bug_reports":
            owned_bugs = {r["bug_id"] for r in self._scope(data, "bug_occurrences", actor)}
            return [r for r in rows if r["bug_id"] in owned_bugs]
        if table == "users":
            return [actor]
        return rows

    def list(self, table, actor_id, query=None):
        if table not in TABLES:
            raise ApiError("Unknown entity type.", 404)
        data = self.store.read()
        actor = self._actor(data, actor_id)
        rows = self._scope(data, table, actor)
        query = query or {}
        if table == "bug_reports":
            for field in ("version_id", "status", "category", "severity", "impact"):
                if query.get(field):
                    expected = _int(query[field], field) if field.endswith("_id") or field in {"severity", "impact"} else query[field]
                    rows = [r for r in rows if r.get(field) == expected]
            if query.get("q"):
                term = query["q"].casefold()
                rows = [r for r in rows if term in r["title"].casefold() or term in r["category"].casefold()]
        if table == "feedback" and query.get("version_id"):
            session_ids = {s["session_id"] for s in data["playtest_sessions"] if s["version_id"] == _int(query["version_id"], "version_id")}
            rows = [r for r in rows if r["session_id"] in session_ids]
        return self._enrich(data, table, rows)

    def get(self, table, record_id, actor_id):
        data = self.store.read()
        actor = self._actor(data, actor_id)
        key = KEYS.get(table)
        if not key:
            raise ApiError("Unknown entity type.", 404)
        row = _find(self._scope(data, table, actor), key, _int(record_id, key))
        if row is None:
            raise ApiError("Record was not found or is not visible to this identity.", 404)
        return self._enrich(data, table, [row])[0]

    def create(self, table, payload, actor_id):
        if table not in TABLES:
            raise ApiError("Unknown entity type.", 404)
        payload = dict(payload or {})
        if table == "bug_reports" and payload.get("session_id"):
            return self.create_report_with_occurrence(payload, actor_id)
        if table == "bug_occurrences":
            self._role(self._actor(self.store.read(), actor_id), {"Developer", "Admin"})
        elif table == "feedback":
            self._role(self._actor(self.store.read(), actor_id), {"Tester"})
        elif table == "playtest_sessions":
            self._role(self._actor(self.store.read(), actor_id), {"Tester"})
        elif table == "users":
            self._role(self._actor(self.store.read(), actor_id), {"Admin"})
        else:
            self._role(self._actor(self.store.read(), actor_id), {"Developer", "Admin"})

        def op(data):
            actor = self._actor(data, actor_id)
            row = self._clean(data, table, payload, None, actor)
            row[KEYS[table]] = self._next(data, table)
            if table == "games":
                row["created_at"] = datetime.now().isoformat(timespec="seconds")
            if table == "playtest_sessions":
                row["tested_at"] = row.get("tested_at") or datetime.now().isoformat(timespec="seconds")
            if table == "bug_occurrences":
                row.setdefault("reported_at", datetime.now().isoformat(timespec="seconds"))
            data[table].append(row)
            return row
        return self.store.transact(op)

    def update(self, table, record_id, payload, actor_id):
        if table not in TABLES:
            raise ApiError("Unknown entity type.", 404)
        payload = dict(payload or {})
        def op(data):
            actor = self._actor(data, actor_id)
            key = KEYS[table]
            row = _find(self._scope(data, table, actor), key, _int(record_id, key))
            if row is None:
                raise ApiError("Record was not found or cannot be changed by this identity.", 404)
            if table == "users":
                self._role(actor, {"Admin"})
            elif table in {"games", "game_versions", "bug_reports"}:
                self._role(actor, {"Developer", "Admin"})
            elif table == "playtest_sessions":
                if actor["role"] != "Tester" or row["user_id"] != actor["user_id"]:
                    self._role(actor, {"Admin"})
            elif table in {"feedback", "bug_occurrences"}:
                owner_session = _find(data["playtest_sessions"], "session_id", row["session_id"])
                if actor["role"] == "Tester" and owner_session["user_id"] != actor["user_id"]:
                    raise ApiError("You can only edit your own records.", 403)
                if table == "feedback":
                    self._role(actor, {"Tester", "Admin"})
                else:
                    self._role(actor, {"Tester", "Developer", "Admin"})
                    if actor["role"] == "Tester" and payload.get("bug_id", row["bug_id"]) != row["bug_id"]:
                        raise ApiError("Only a Developer or Admin can associate a report with another bug.", 403)
            updated = {**row, **self._clean(data, table, {**row, **payload}, row, actor)}
            if table == "bug_reports" and updated["version_id"] != row["version_id"] and any(o["bug_id"] == row["bug_id"] for o in data["bug_occurrences"]):
                raise ApiError("A bug with reports cannot be moved to another version.", 409)
            if table == "playtest_sessions" and updated["version_id"] != row["version_id"] and any(o["session_id"] == row["session_id"] for o in data["bug_occurrences"]):
                raise ApiError("A session with bug reports cannot be moved to another version.", 409)
            if table == "feedback" and updated["session_id"] != row["session_id"]:
                raise ApiError("Feedback cannot be moved to another playtest session.", 409)
            row.clear(); row.update(updated)
            row[key] = _int(record_id, key)
            return row
        return self.store.transact(op)

    def delete(self, table, record_id, actor_id):
        if table not in TABLES:
            raise ApiError("Unknown entity type.", 404)
        def op(data):
            actor = self._actor(data, actor_id)
            self._role(actor, {"Admin"})
            key, rid = KEYS[table], _int(record_id, KEYS[table])
            row = _find(data[table], key, rid)
            if row is None:
                raise ApiError("Record was not found.", 404)
            if table == "users" and rid == actor["user_id"]:
                raise ApiError("The active demo identity cannot delete itself.", 409)
            refs = {
                "users": [("playtest_sessions", "user_id")],
                "games": [("game_versions", "game_id")],
                "game_versions": [("playtest_sessions", "version_id"), ("bug_reports", "version_id")],
                "playtest_sessions": [("bug_occurrences", "session_id"), ("feedback", "session_id")],
                "bug_reports": [("bug_occurrences", "bug_id")],
                "bug_occurrences": [], "feedback": [],
            }
            for ref_table, ref_key in refs[table]:
                if any(ref.get(ref_key) == rid for ref in data[ref_table]):
                    raise ApiError("This record is still referenced and cannot be deleted.", 409)
            data[table].remove(row)
            return {"id": rid, "deleted": True}
        return self.store.transact(op)

    def create_report_with_occurrence(self, payload, actor_id):
        def op(data):
            actor = self._actor(data, actor_id)
            self._role(actor, {"Tester"})
            session = _require(data, "playtest_sessions", "session_id", _int(payload["session_id"], "session_id"), "测试场次")
            if session["user_id"] != actor["user_id"]:
                raise ApiError("You can only submit reports from your own playtest sessions.", 403)
            version_id = session["version_id"]
            if payload.get("existing_bug_id"):
                raise ApiError("Only a Developer or Admin can associate a report with an existing bug.", 403)
            bug = self._clean(data, "bug_reports", {**payload, "version_id": version_id, "status": "Open"}, None, actor)
            bug["bug_id"] = self._next(data, "bug_reports")
            data["bug_reports"].append(bug)
            occurrence = {"occurrence_id": self._next(data, "bug_occurrences"), "bug_id": bug["bug_id"], "session_id": session["session_id"], "version_id": version_id, "notes": str(payload.get("notes", "")).strip(), "reported_at": datetime.now().isoformat(timespec="seconds")}
            data["bug_occurrences"].append(occurrence)
            return {"bug": bug, "occurrence": occurrence, "candidate": False}
        return self.store.transact(op)

    def candidates(self, payload, actor_id):
        data = self.store.read(); actor = self._actor(data, actor_id); self._role(actor, {"Tester"})
        session = _require(data, "playtest_sessions", "session_id", _int(payload.get("session_id"), "session_id"), "测试场次")
        if session["user_id"] != actor["user_id"]:
            raise ApiError("You can only look for duplicates in your own playtest sessions.", 403)
        category = str(payload.get("category", "")).strip().casefold()
        words = {w for w in re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(payload.get("title", "")).casefold()) if len(w) > 2}
        matches = []
        for bug in data["bug_reports"]:
            if bug["version_id"] != session["version_id"] or bug["category"].casefold() != category:
                continue
            target = {w for w in re.findall(r"[a-z0-9\u4e00-\u9fff]+", bug["title"].casefold()) if len(w) > 2}
            if words and words & target:
                matches.append(bug)
        return self._enrich(data, "bug_reports", matches)

    def merge(self, source_id, target_id, actor_id):
        def op(data):
            actor = self._actor(data, actor_id); self._role(actor, {"Developer", "Admin"})
            source = _require(data, "bug_reports", "bug_id", _int(source_id, "source_id"), "源 Bug")
            target = _require(data, "bug_reports", "bug_id", _int(target_id, "target_id"), "目标 Bug")
            if source["bug_id"] == target["bug_id"]:
                raise ApiError("Source and target bugs must be different.")
            if source["version_id"] != target["version_id"]:
                raise ApiError("Bugs can only be merged within the same game version.")
            occurrences = [r for r in data["bug_occurrences"] if r["bug_id"] == source["bug_id"]]
            # All references move together; the target's title, severity, impact and status remain authoritative.
            for occurrence in occurrences:
                occurrence["bug_id"] = target["bug_id"]
            data["bug_reports"].remove(source)
            return {"source_bug_id": source["bug_id"], "target_bug_id": target["bug_id"], "moved_occurrences": len(occurrences)}
        return self.store.transact(op)

    def associate_occurrence(self, payload, actor_id):
        def op(data):
            actor = self._actor(data, actor_id); self._role(actor, {"Developer", "Admin"})
            occurrence = _require(data, "bug_occurrences", "occurrence_id", _int(payload.get("occurrence_id"), "occurrence_id"), "Bug 报告")
            target = _require(data, "bug_reports", "bug_id", _int(payload.get("bug_id"), "bug_id"), "目标 Bug")
            if target["version_id"] != occurrence["version_id"]:
                raise ApiError("A report can only be linked to a bug from the same game version.")
            occurrence["bug_id"] = target["bug_id"]
            return occurrence
        return self.store.transact(op)

    def dashboard(self):
        data = self.store.read()
        by_game = []
        for game in data["games"]:
            versions = []
            for version in [v for v in data["game_versions"] if v["game_id"] == game["game_id"]]:
                bugs = [b for b in data["bug_reports"] if b["version_id"] == version["version_id"]]
                sessions = [s for s in data["playtest_sessions"] if s["version_id"] == version["version_id"]]
                session_ids = {s["session_id"] for s in sessions}
                ratings = [f["rating"] for f in data["feedback"] if f["session_id"] in session_ids]
                reports = sum(1 for o in data["bug_occurrences"] if o["version_id"] == version["version_id"])
                versions.append({"version": version, "bug_count": len(bugs), "unresolved_count": sum(b["status"] in {"Open", "In Progress"} for b in bugs), "report_count": reports, "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None, "feedback_count": len(ratings)})
            by_game.append({"game": game, "versions": versions})
        priority = []
        for bug in data["bug_reports"]:
            count = sum(o["bug_id"] == bug["bug_id"] for o in data["bug_occurrences"])
            bug_score = round(0.5 * bug["severity"] + 0.3 * min(count, 5) + 0.2 * bug["impact"], 2)
            if bug["status"] in {"Open", "In Progress"}:
                item = self._enrich(data, "bug_reports", [bug])[0]
                item.update({"occurrence_count": count, "priority_score": bug_score})
                priority.append(item)
        priority.sort(key=lambda x: (-x["priority_score"], x["bug_id"]))
        return {"games": by_game, "high_priority": priority[:8], "total_sessions": len(data["playtest_sessions"]), "total_reports": len(data["bug_occurrences"])}

    def _clean(self, data, table, payload, existing, actor):
        unknown = set(payload) - FIELDS[table] - set(KEYS.values()) - {"created_at", "reported_at", "existing_bug_id", "session_id", "notes"}
        if unknown:
            raise ApiError(f"Unsupported fields: {', '.join(sorted(unknown))}.")
        row = {k: payload[k] for k in FIELDS[table] if k in payload}
        missing = FIELDS[table] - set(row)
        optional = {"genre", "release_date", "tested_at", "comments"}
        missing -= optional
        if missing:
            raise ApiError(f"Required fields are missing: {', '.join(sorted(missing))}.")
        for field in ("name", "title", "email", "version_name", "category"):
            if field in row:
                if row[field] is None:
                    raise ApiError(f"{field} is required.")
                row[field] = str(row[field]).strip()
                if not row[field]:
                    raise ApiError(f"{field} cannot be empty.")
        for field in ("genre", "release_date", "tested_at", "comments", "notes"):
            if field in row and row[field] is not None:
                row[field] = str(row[field]).strip() or None
        if table == "users":
            row["email"] = row["email"].lower()
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", row["email"]):
                raise ApiError("Enter a valid email address.")
            if row.get("role") not in ROLES:
                raise ApiError("role must be Tester, Developer, or Admin.")
            if any(u["email"] == row["email"] and (not existing or u["user_id"] != existing["user_id"]) for u in data["users"]):
                raise ApiError("That email address is already in use.", 409)
        if table == "game_versions":
            row["game_id"] = _int(row["game_id"], "game_id")
            _require(data, "games", "game_id", row["game_id"], "游戏")
            if row.get("release_date"):
                try:
                    date.fromisoformat(row["release_date"])
                except ValueError:
                    raise ApiError("release_date must use YYYY-MM-DD format.")
            if any(v["game_id"] == row["game_id"] and v["version_name"].casefold() == row["version_name"].casefold() and (not existing or v["version_id"] != existing["version_id"]) for v in data["game_versions"]):
                raise ApiError("This game already has a version with that name.", 409)
        if table == "playtest_sessions":
            row["user_id"] = actor["user_id"] if actor["role"] == "Tester" else _int(row["user_id"], "user_id")
            row["version_id"] = _int(row["version_id"], "version_id")
            _require(data, "game_versions", "version_id", row["version_id"], "游戏版本")
            if row.get("tested_at"):
                try:
                    datetime.fromisoformat(row["tested_at"].replace("Z", "+00:00"))
                except ValueError:
                    raise ApiError("tested_at must use ISO date-time format.")
        if table == "bug_reports":
            row["version_id"] = _int(row["version_id"], "version_id")
            _require(data, "game_versions", "version_id", row["version_id"], "游戏版本")
            for field in ("severity", "impact"):
                row[field] = _int(row[field], field)
                if row[field] not in range(1, 6):
                    raise ApiError(f"{field} must be between 1 and 5.")
            if row.get("status") not in STATUSES:
                raise ApiError("status must be Open, In Progress, Fixed, or Closed.")
        if table == "bug_occurrences":
            for field in ("bug_id", "session_id", "version_id"):
                row[field] = _int(row[field], field)
            bug = _require(data, "bug_reports", "bug_id", row["bug_id"], "Bug")
            session = _require(data, "playtest_sessions", "session_id", row["session_id"], "测试场次")
            if bug["version_id"] != row["version_id"] or session["version_id"] != row["version_id"]:
                raise ApiError("The bug, playtest session, and version must match.")
            if actor["role"] == "Tester" and session["user_id"] != actor["user_id"]:
                raise ApiError("You can only submit records from your own playtest sessions.", 403)
        if table == "feedback":
            row["session_id"] = _int(row["session_id"], "session_id")
            session = _require(data, "playtest_sessions", "session_id", row["session_id"], "测试场次")
            if actor["role"] == "Tester" and session["user_id"] != actor["user_id"]:
                raise ApiError("You can only submit feedback for your own playtest sessions.", 403)
            row["rating"] = _int(row["rating"], "rating")
            if row["rating"] not in range(1, 6):
                raise ApiError("Rating must be between 1 and 5.")
            if any(f["session_id"] == row["session_id"] and (not existing or f["feedback_id"] != existing["feedback_id"]) for f in data["feedback"]):
                raise ApiError("Each playtest session can have only one feedback entry.", 409)
        if table == "users" and row["role"] == "Tester" and actor["role"] != "Admin":
            raise ApiError("Only an Admin can create a tester account.", 403)
        return row

    @staticmethod
    def _next(data, table):
        meta = data["_meta"]["next_ids"]
        result = meta[table]
        meta[table] += 1
        return result

    def _enrich(self, data, table, rows):
        out = []
        for original in rows:
            row = dict(original)
            if table == "game_versions":
                game = _find(data["games"], "game_id", row["game_id"]); row["game_title"] = game["title"] if game else None
            elif table == "playtest_sessions":
                user = _find(data["users"], "user_id", row["user_id"]); version = _find(data["game_versions"], "version_id", row["version_id"])
                row.update({"tester_name": user["name"] if user else None, "version_name": version["version_name"] if version else None, "game_title": next((g["title"] for g in data["games"] if version and g["game_id"] == version["game_id"]), None)})
            elif table == "bug_reports":
                version = _find(data["game_versions"], "version_id", row["version_id"])
                count = sum(o["bug_id"] == row["bug_id"] for o in data["bug_occurrences"])
                row.update({"version_name": version["version_name"] if version else None, "game_title": next((g["title"] for g in data["games"] if version and g["game_id"] == version["game_id"]), None), "occurrence_count": count, "priority_score": round(0.5 * row["severity"] + 0.3 * min(count, 5) + 0.2 * row["impact"], 2)})
            elif table == "bug_occurrences":
                bug = _find(data["bug_reports"], "bug_id", row["bug_id"]); session = _find(data["playtest_sessions"], "session_id", row["session_id"])
                user = _find(data["users"], "user_id", session["user_id"]) if session else None
                row.update({"bug_title": bug["title"] if bug else None, "tester_name": user["name"] if user else None})
            elif table == "feedback":
                session = _find(data["playtest_sessions"], "session_id", row["session_id"]); version = _find(data["game_versions"], "version_id", session["version_id"]) if session else None
                user = _find(data["users"], "user_id", session["user_id"]) if session else None
                row.update({"tester_name": user["name"] if user else None, "version_name": version["version_name"] if version else None, "game_title": next((g["title"] for g in data["games"] if version and g["game_id"] == version["game_id"]), None)})
            out.append(row)
        return out
