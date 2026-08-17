"""routes/users_routes.py -- the user administration screen's endpoints.

Holds no permission logic of its own: every decision comes from auth/guard.py,
which runs in the doorman before any of these are reached. The one thing this
file does enforce directly is that /invite/<token> is reachable while signed
OUT -- an invited person has no account yet, so they cannot sign in to accept.
"""
import os

from flask import request, jsonify, render_template, session, current_app

from auth import users


def register(app, *, CONFIG_PATH):
    """Attach the /users/* and /invite/* routes to the existing Flask app."""

    def _me():
        """The signed-in user's full record, or the synthetic owner while no real
        accounts exist yet.

        Reaching any of these routes means the doorman in auth/guard.py has
        ALREADY authorised the request, so "no uid and still in bootstrap" means
        the caller is the owner -- whether they got here by typing the shared
        password or because the gate is switched off entirely.

        An earlier version also required session["authed"], which broke local
        development: with no APP_PASSWORD set the gate no-ops and nothing ever
        sets that flag, so /users/me answered 401 and the Users button never
        appeared on the machine where it most needed testing.
        """
        uid = session.get("uid")
        if uid:
            return users.get_user(CONFIG_PATH, uid)
        if users.is_bootstrap(CONFIG_PATH):
            return users.bootstrap_user()
        return None

    def _invite_link(token):
        """An absolute link, because it gets pasted into WhatsApp.

        BEHIND A PROXY, request.url_root LIES. On Render the app is served over
        HTTPS by a proxy that forwards plain HTTP to Flask, so url_root reports
        "http://app.altascraper.com/" -- and every invitation sent from the live
        server would carry an http:// link. Depending on the browser that either
        warns about sending a password over an insecure connection, or is
        upgraded and works by luck.

        X-Forwarded-Proto and X-Forwarded-Host are what the proxy actually says,
        so they win when present. APP_BASE_URL overrides everything for an
        unusual deployment.
        """
        base = (os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
        if not base:
            proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
            host = (request.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
            if proto and host:
                base = "%s://%s" % (proto, host)
            elif host:
                base = "https://%s" % host
            else:
                base = request.url_root.rstrip("/")
        return base + "/invite/" + token

    # The vocabulary every user screen is drawn from: the list of areas, the
    # list of permissions, the access levels, and what each role presets. Built
    # in ONE place so /users/me and /users/list cannot describe the app
    # differently -- when they did, whichever call answered last decided which
    # controls existed, and the "What may they SEE?" section disappeared.
    def _vocabulary():
        return {"all_permissions": users.PERMISSIONS,
                "all_features": users.FEATURES,
                "levels": list(users.LEVELS),
                "role_features": users.ROLE_FEATURES,
                # Which page belongs under which area, and the order to show
                # them in. Sent rather than repeated in the browser so the form
                # cannot list a feature that no longer exists, or miss one that
                # was just added.
                "feature_parent": users.FEATURE_PARENT,
                "feature_groups": [{"title": t, "features": fs}
                                   for t, fs in users.FEATURE_GROUPS],
                "roles": users.ROLES}

    # ---- who am I -------------------------------------------------------
    @app.route("/users/me")
    def users_me():
        """What the browser uses to decide which controls to draw. This is a
        convenience for the UI, NOT the security boundary -- the doorman has
        already refused anything this user may not do."""
        u = _me()
        if not u:
            return jsonify({"ok": False, "error": "not signed in"}), 401
        # Which store the app is reading. The UI uses this for wording that would
        # otherwise be wrong on one backend -- e.g. "not in your sheet" when there
        # is no sheet, which would send someone looking in a spreadsheet for a row
        # that was never going to be there.
        # What THIS app is actually using, recorded by build_app. Re-reading the
        # environment here was the bug: it reported the request, not the result,
        # so the UI could claim "db" while every route read the Google Sheet.
        _backend = current_app.config.get("DATA_BACKEND") or "sheets"
        # AND WHY. Knowing the app is on sheets is half an answer; the useful
        # half is that it fell back because no database exists at the path it
        # looked in -- which is what happens when a deploy replaces the disk the
        # database was on. Without the reason, "it is still using sheets" looks
        # like the migration failed rather than like the file being absent, and
        # those need completely different actions.
        _why = current_app.config.get("DATA_BACKEND_DECISION") or {}
        return jsonify({"ok": True, "user": users.public(u),
                        "bootstrap": bool(u.get("bootstrap")),
                        "backend": _backend,
                        "backend_source": _why.get("source") or "",
                        "backend_note": _why.get("note") or "",
                        **_vocabulary()})

    # ---- administration -------------------------------------------------
    @app.route("/users/list")
    def users_list():
        return jsonify({"ok": True, "users": users.list_users(CONFIG_PATH),
                        "bootstrap": users.is_bootstrap(CONFIG_PATH),
                        **_vocabulary()})

    @app.route("/users/create", methods=["POST"])
    def users_create():
        b = request.get_json(force=True, silent=True) or {}
        rec, res = users.create_user(
            CONFIG_PATH,
            email=b.get("email", ""),
            name=b.get("name", ""),
            role=b.get("role", "lister"),
            permissions=b.get("permissions"),
            features=b.get("features"),
            workspaces=b.get("workspaces"),
        )
        if not rec:
            return jsonify({"ok": False, "error": res}), 400
        # The token is shown exactly once, here. Only its hash is stored, so it
        # cannot be recovered later -- issue a new invitation instead.
        return jsonify({"ok": True, "user": rec, "invite_url": _invite_link(res)})

    @app.route("/users/invite", methods=["POST"])
    def users_invite():
        """Issue a fresh invitation link. Doubles as the password reset: it
        clears the old password, so the link is the only way back in."""
        b = request.get_json(force=True, silent=True) or {}
        token, err = users.new_invite(CONFIG_PATH, str(b.get("id", "")))
        if err:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True, "invite_url": _invite_link(token)})

    @app.route("/users/update", methods=["POST"])
    def users_update():
        b = request.get_json(force=True, silent=True) or {}
        uid = str(b.get("id", ""))
        fields = {k: b[k] for k in ("name", "role", "permissions", "workspaces",
                                    "features", "active")
                  if k in b}
        rec, err = users.update_user(CONFIG_PATH, uid, **fields)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True, "user": rec})

    @app.route("/users/delete", methods=["POST"])
    def users_delete():
        b = request.get_json(force=True, silent=True) or {}
        uid = str(b.get("id", ""))
        if uid and uid == session.get("uid"):
            return jsonify({"ok": False,
                            "error": "You cannot delete the account you are signed in with."}), 400
        ok, err = users.delete_user(CONFIG_PATH, uid)
        if not ok:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True})

    # ---- accepting an invitation (signed OUT) ---------------------------
    @app.route("/invite/<token>")
    def invite_page(token):
        return render_template("invite.html", token=token, error=None, done=False)

    @app.route("/invite/<token>", methods=["POST"])
    def invite_accept(token):
        pw  = request.form.get("password", "")
        pw2 = request.form.get("password2", "")
        if pw != pw2:
            return render_template("invite.html", token=token,
                                   error="Those two passwords do not match.",
                                   done=False), 400
        rec, err = users.accept_invite(CONFIG_PATH, token, pw)
        if err:
            return render_template("invite.html", token=token, error=err, done=False), 400
        # Sign them straight in -- they have just proved they hold the link and
        # chosen a password; making them type it again immediately adds nothing.
        session.permanent = True
        session["authed"] = True
        session["uid"] = rec["id"]
        return render_template("invite.html", token=token, error=None, done=True)
