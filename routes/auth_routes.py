"""routes/auth_routes.py — authentication endpoints only: /login, /logout, /healthz.

Plain English: this file draws the login screen, checks the team password, and
lets people sign out. It also acts as a doorman — any request that is not signed
in gets sent back to the login screen. It holds no product or listing logic.

It mirrors the original login behaviour from dashboard.py (lines 106-119): if no
password is configured the gate is disabled (local dev); otherwise a correct
password sets the session and a wrong one is rejected.
"""
from __future__ import annotations

from flask import (Blueprint, current_app, redirect, render_template, request,
                   session, url_for)

bp = Blueprint("auth", __name__)

# Endpoints reachable without being signed in.
_PUBLIC_ENDPOINTS = {"auth.login", "auth.healthz", "static"}


def _password() -> str | None:
    """The configured team password (from config.json / env), or None if unset."""
    return current_app.config["SETTINGS"].app_password


@bp.route("/healthz")
def healthz():
    """Liveness check for hosting/monitoring. No auth required."""
    return "ok", 200


@bp.route("/")
def index():
    """Temporary Phase-1 landing: send everyone to the login screen.
    The real dashboard route moves here (into ui_routes) in a later phase."""
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Show the login screen and check the submitted password."""
    password = _password()
    if request.method == "POST":
        if not password:
            return render_template("login.html", configured=False), 503
        if request.form.get("password") == password:
            session.permanent = True
            session["authed"] = True
            return redirect(url_for("auth.index"))
        return render_template("login.html", error="Incorrect password."), 401
    return render_template(
        "login.html", configured=bool(password), authed=session.get("authed", False)
    )


@bp.route("/logout")
def logout():
    """Sign out and return to the login screen."""
    session.clear()
    return redirect(url_for("auth.login"))


@bp.before_app_request
def require_login():
    """Doorman: redirect not-signed-in visitors to /login.

    Skipped entirely when no password is configured (local dev), matching the
    original dashboard behaviour so the local workflow is unchanged.
    """
    if not _password():
        return  # no password configured -> gate disabled
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    if not session.get("authed"):
        return redirect(url_for("auth.login"))
