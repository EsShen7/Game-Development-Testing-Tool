"""Atomic, single-process JSON persistence adapter."""

import copy
import json
import os
import tempfile
import threading
from pathlib import Path


TABLES = ("users", "games", "game_versions", "playtest_sessions", "bug_reports", "bug_occurrences", "feedback")
EMPTY = {"_meta": {"next_ids": {t: 1 for t in TABLES}}, **{t: [] for t in TABLES}}


def sample_data():
    data = copy.deepcopy(EMPTY)
    data["_meta"]["next_ids"] = dict(zip(TABLES, (5, 2, 3, 5, 4, 5, 4)))
    data["users"] = [
        {"user_id": 1, "name": "Avery Chen", "email": "avery@example.com", "role": "Tester"},
        {"user_id": 2, "name": "Morgan Lee", "email": "morgan@example.com", "role": "Tester"},
        {"user_id": 3, "name": "Riley Park", "email": "riley@example.com", "role": "Developer"},
        {"user_id": 4, "name": "Jordan Kim", "email": "jordan@example.com", "role": "Admin"},
    ]
    data["games"] = [{"game_id": 1, "title": "Skyward Isles", "genre": "Action adventure", "created_at": "2026-10-01T09:00:00"}]
    data["game_versions"] = [
        {"version_id": 1, "game_id": 1, "version_name": "0.9.0", "release_date": "2026-10-10"},
        {"version_id": 2, "game_id": 1, "version_name": "1.0.0", "release_date": "2026-10-24"},
    ]
    data["playtest_sessions"] = [
        {"session_id": 1, "user_id": 1, "version_id": 1, "tested_at": "2026-10-12T10:30:00"},
        {"session_id": 2, "user_id": 2, "version_id": 1, "tested_at": "2026-10-13T14:00:00"},
        {"session_id": 3, "user_id": 1, "version_id": 2, "tested_at": "2026-10-25T11:15:00"},
        {"session_id": 4, "user_id": 2, "version_id": 2, "tested_at": "2026-10-26T16:40:00"},
    ]
    data["bug_reports"] = [
        {"bug_id": 1, "version_id": 1, "title": "Camera clips through the lighthouse wall", "category": "Visual", "severity": 3, "impact": 3, "status": "In Progress"},
        {"bug_id": 2, "version_id": 1, "title": "Save slot resets after fast travel", "category": "Progression", "severity": 5, "impact": 5, "status": "Open"},
        {"bug_id": 3, "version_id": 2, "title": "Camera clips through the lighthouse wall", "category": "Visual", "severity": 2, "impact": 2, "status": "Fixed"},
    ]
    data["bug_occurrences"] = [
        {"occurrence_id": 1, "bug_id": 1, "session_id": 1, "version_id": 1, "notes": "Only when climbing the north ledge.", "reported_at": "2026-10-12T11:05:00"},
        {"occurrence_id": 2, "bug_id": 1, "session_id": 2, "version_id": 1, "notes": "Reproduced twice from the dock.", "reported_at": "2026-10-13T15:10:00"},
        {"occurrence_id": 3, "bug_id": 2, "session_id": 2, "version_id": 1, "notes": "Happened after using the map.", "reported_at": "2026-10-13T15:35:00"},
        {"occurrence_id": 4, "bug_id": 3, "session_id": 3, "version_id": 2, "notes": "Still visible in photo mode only.", "reported_at": "2026-10-25T12:00:00"},
    ]
    data["feedback"] = [
        {"feedback_id": 1, "session_id": 1, "rating": 3, "comments": "Strong atmosphere; movement could feel tighter."},
        {"feedback_id": 2, "session_id": 2, "rating": 4, "comments": "Enjoyed exploration. The save issue interrupted the run."},
        {"feedback_id": 3, "session_id": 3, "rating": 5, "comments": "The camera fix makes the route much easier to read."},
    ]
    return data


def empty_workspace():
    """Start without business examples while retaining selectable demo identities."""
    data = copy.deepcopy(EMPTY)
    data["users"] = sample_data()["users"]
    data["_meta"]["next_ids"]["users"] = 5
    return data


class JsonStore:
    """Storage seam corresponding to the seven tables in sql/schema.sql."""

    def __init__(self, path, seed=True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write(sample_data() if seed else empty_workspace())

    def read(self):
        with self._lock:
            try:
                with self.path.open(encoding="utf-8") as handle:
                    value = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Runtime data file cannot be read: {self.path}. The file was not overwritten; restore or repair it before retrying.") from exc
            valid_shape = (
                isinstance(value, dict)
                and all(isinstance(value.get(t), list) and all(isinstance(row, dict) for row in value[t]) for t in TABLES)
                and isinstance(value.get("_meta"), dict)
                and isinstance(value["_meta"].get("next_ids"), dict)
                and all(isinstance(value["_meta"]["next_ids"].get(t), int) and not isinstance(value["_meta"]["next_ids"].get(t), bool) and value["_meta"]["next_ids"][t] > 0 for t in TABLES)
            )
            if not valid_shape:
                raise RuntimeError(f"Runtime data file has an invalid structure: {self.path}. The file was not overwritten; restore or repair it before retrying.")
            return value

    def transact(self, operation):
        with self._lock:
            data = self.read()
            working = copy.deepcopy(data)
            result = operation(working)
            self._write(working)
            return result

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
