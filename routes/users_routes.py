"""routes/users_routes.py -- the user administration screen's endpoints.

Holds no permission logic of its own: every decision comes from auth/guard.py,
which runs in the doorman before any of these are reached. The one thing this
file does enforce directly is that /invite/<token> is reachable while signed
OUT -- an invited person has no account yet, so they cannot sign in to accept.
"""
from flask import request, jsonify, render_template, session

from auth import users


def register(app, *, CONFIG_PATH):
    """Attach the /users/* and /invite/* routes to the existing Flask app."""

    def _me():
        """The signed-in user's full record, or the synthetic shared-password
        owner while no real accounts exist yet."""
        uid = session.get("uid")
        if uid:
            return users.get_user(CONFIG_PATH, uid)
        if users.is_bootstrap(CONFIG_PATH) and session.get("authed"):
            return users.bootstrap_user()
        return None

    def _invite_link(token):
        """An absolute link, because it gets pasted into WhatsApp. request.url_root
        already reflects the real host, so this works on both 127.0.0.1 and
        app.altascraper.com without anything to configure."""
        return request.url_root.rstrip("/") + "/invite/" + token

    # ---- who am I -------------------------------------------------------
    @app.route("/users/me")
    def users_me():
        """What the browser uses to decide which controls to draw. This is a
        convenience for the UI, NOT the security boundary -- the doorman has
        already refused anything this user may not do."""
        u = _me()
        if not u:
            return jsonify({"ok": False, "error": "not signed in"}), 401
        return jsonify({"ok": True, "user": users.public(u),
                        "bootstrap": bool(u.get("bootstrap")),
                        "all_permissions": users.PERMISSIONS,
                        "roles": users.ROLES})

    # ---- administration -------------------------------------------------
    @app.route("/users/list")
    def users_list():
        return jsonify({"ok": True, "users": users.list_users(CONFIG_PATH),
                        "all_permissions": users.PERMISSIONS,
                        "roles": users.ROLES,
                        "bootstrap": users.is_bootstrap(CONFIG_PATH)})

    @app.route("/users/create", methods=["POST"])
    def users_create():
        b = request.get_json(force=True, silent=True) or {}
        rec, res = users.create_user(
            CONFIG_PATH,
            email=b.get("email", ""),
            name=b.get("name", ""),
            role=b.get("role", "lister"),
            permissions=b.get("permissions"),
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
        fields = {k: b[k] for k in ("name", "role", "permissions", "workspaces", "active")
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
