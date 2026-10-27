"""Application factory for the game playtest project."""

import os

from dotenv import load_dotenv
from flask import Flask, render_template


def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.config.update(
        DB_HOST=os.getenv("DB_HOST", "127.0.0.1"),
        DB_PORT=int(os.getenv("DB_PORT", "3306")),
        DB_USER=os.getenv("DB_USER", "playtest"),
        DB_PASSWORD=os.getenv("DB_PASSWORD", ""),
        DB_NAME=os.getenv("DB_NAME", "game_playtest"),
    )

    @app.get("/")
    def index():
        return render_template("index.html")

    return app
