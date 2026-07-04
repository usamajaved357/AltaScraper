"""routes/dash_auth_routes.py — extracted from dashboard.py (Phase 3). Bodies VERBATIM.

Auto-extracted @app.route("paths:/healthz,/login,/logout...") funcs; shared helpers injected. Verified with
verify_free_vars.py.
"""
from flask import request, jsonify, Response, send_from_directory, redirect, session, url_for


def register(app, *, _APP_PASSWORD, _LOGIN_HTML):
    """Attach the paths:/healthz,/login,/logout routes to the existing Flask app."""

    @app.route("/healthz")
    def _healthz():
        return "ok", 200

    @app.route("/login", methods=["GET", "POST"])
    def _login():
        if not _APP_PASSWORD:
            return "Login is not configured.", 404
        err = ""
        if request.method == "POST":
            if request.form.get("password") == _APP_PASSWORD:
                session["authed"] = True
                return redirect(url_for("index"))
            err = '<div class="err">Wrong password.</div>'
        return Response(_LOGIN_HTML.replace("{err}", err), mimetype="text/html")

    @app.route("/logout")
    def _logout():
        session.clear()
        return redirect(url_for("_login"))

