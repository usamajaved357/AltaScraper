"""routes/dash_auth_routes.py — signing in and out.

PLAIN ENGLISH
This draws the sign-in screen and checks who is trying to get in. It now handles
two situations:

  * You have added users -> people sign in with their own email and password.
  * You have not (yet)   -> the old single shared password still works, exactly
                            as it always did, and is treated as the owner.

The second case is what makes it impossible to lock yourself out by adding the
user system. It stops applying the moment the first person accepts an invitation.

It also remembers where someone was heading. Now that every screen has its own
address, a bookmarked link followed after the session expired used to dump you on
the workspace list; the "next" parameter carries the destination through the
sign-in and puts you back where you meant to go.
"""
from urllib.parse import urlparse

from flask import (request, jsonify, Response, send_from_directory, redirect,
                   session, url_for, render_template)

from auth import users


def _safe_next(raw):
    """A destination we are willing to send someone to after signing in.

    Only same-site paths. Without this check an attacker could send you a link
    like /login?next=https://evil.example and the app would bounce you there
    after you had typed your password -- a classic open redirect.
    """
    raw = str(raw or "").strip()
    if not raw.startswith("/") or raw.startswith("//"):
        return ""
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return ""
    return raw


def register(app, *, _APP_PASSWORD, CONFIG_PATH=None):
    """Attach the /healthz, /login and /logout routes to the existing Flask app."""

    @app.route("/healthz")
    def _healthz():
        return "ok", 200

    @app.route("/login", methods=["GET", "POST"])
    def _login():
        bootstrap = users.is_bootstrap(CONFIG_PATH) if CONFIG_PATH else True
        # With no users AND no shared password there is nothing to check against.
        if bootstrap and not _APP_PASSWORD:
            return "Login is not configured.", 404

        nxt = _safe_next(request.values.get("next", ""))
        error = None

        if request.method == "POST":
            email = request.form.get("email", "")
            pw    = request.form.get("password", "")

            user = None if bootstrap else users.authenticate(CONFIG_PATH, email, pw)
            if user:
                # permanent -> the cookie carries an explicit 30-day expiry
                # instead of dying with the browser process, so a screen lock,
                # sleep or browser restore no longer forces a fresh sign-in.
                session.permanent = True
                session["authed"] = True
                session["uid"] = user["id"]
                return redirect(nxt or url_for("index"))

            if bootstrap and _APP_PASSWORD and pw == _APP_PASSWORD:
                session.permanent = True
                session["authed"] = True
                session.pop("uid", None)          # the shared password is nobody
                return redirect(nxt or url_for("index"))

            error = ("Wrong password." if bootstrap
                     else "That email and password do not match an account.")

        return render_template("dash_login.html", error=error, bootstrap=bootstrap,
                               next=nxt)

    @app.route("/logout")
    def _logout():
        session.clear()
        return redirect(url_for("_login"))
