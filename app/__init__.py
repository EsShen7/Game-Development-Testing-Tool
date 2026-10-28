"""Flask application factory for the playtest workspace."""

import os
from pathlib import Path

from flask import Flask
from dotenv import load_dotenv

from .routes import bp
from .storage import JsonStore
from .services import PlaytestService


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "local-demo-key-change-me"),
        JSON_FILE=os.getenv("JSON_FILE", str(Path(app.instance_path) / "playtest.json")),
        SEED_DATA=os.getenv("SEED_DATA", "true").lower() == "true",
    )
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    store = JsonStore(app.config["JSON_FILE"], seed=app.config["SEED_DATA"])
    app.extensions["playtest_service"] = PlaytestService(store)
    app.register_blueprint(bp)
    return app
