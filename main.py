#!/usr/bin/env python3
"""main.py — application entry point.

Plain English: this is the file you run to start the app. It builds the web
server, loads the settings, plugs in the login screen, and starts listening for
browser requests. It is intentionally tiny and holds no product logic of its own.
"""
from datetime import timedelta

from flask import Flask

from config.constants import HOST, PORT, SESSION_HOURS
from config.settings import load_settings
from routes import register_blueprints


def create_app() -> Flask:
    """Build and configure the Flask application."""
    app = Flask(__name__)
    settings = load_settings()                       # reads + validates config.json
    app.config["SETTINGS"] = settings
    app.secret_key = settings.secret_key
    app.permanent_session_lifetime = timedelta(hours=SESSION_HOURS)
    register_blueprints(app)                          # attaches the auth routes
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=True)
