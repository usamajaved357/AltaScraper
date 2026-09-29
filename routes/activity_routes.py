"""routes/activity_routes.py -- Employee Performance: record work, and read it back.

    after every request   one hook asks domain/activity_catalog whether the
                          request was meaningful work and, if so, records it in
                          domain/activity (the one activity log)
    GET /activity/summary?from=&to=&user=&account=&marketplace=&category=&ok=
                          per person: plain counts by kind of work, failures,
                          first and last action -- and every team member, so
                          someone who did nothing in the period shows as 0
    GET /activity/list?...&limit=&offset=
                          the actions themselves, newest first (a timeline)

WHO MAY READ IT. auth/guard.py RULES: /activity needs view_activity (owner and
manager presets). Rows are further limited to the accounts the VIEWER may open:
a manager limited to one account never sees work done in another, nor work that
belongs to no account (team administration) unless they may open every account.
"""
import time

from flask import jsonify, request, session


def register(app, *, CONFIG_PATH, APP_PASSWORD=""):

    def _admitted():
        """Did the doorman let a real person in? Signed in (session "authed"),
        or the local no-login setup the doorman itself allows (no password, no
        owner yet, not on a server). Anyone else -- signed out, disabled,
        another website -- did no work and is never written into the record
        (change review: an unauthenticated GET was credited to the owner)."""
        if session.get("authed"):
            return True
        from auth import guard as _g, users as _u
        return (not APP_PASSWORD and _u.is_bootstrap(CONFIG_PATH)
                and not session.get("uid") and _g.open_gate_allowed())

    @app.before_request
    def _snapshot_before_edit():
        # THE OLD VALUE, for "field: old -> new" on a listing edit. Registered
        # after the doorman, so a refused request never gets here. Only when the
        # request names exactly one account -- never the open one.
        try:
            if request.method != "POST" or request.path != "/edit":
                return None
            from flask import g
            from auth import guard as _g
            body = _g.request_body_for_check(request) or {}
            # THE SAME ACCOUNT /edit WRITES: it opens _store_for(b.get("account"))
            # (routes/listing_routes.py). Only that field, and only when it is
            # the one account the request names -- a request naming the account
            # any other way gets no old value rather than another store's.
            acct = str(body.get("account") or "").strip()
            accts = _g.named_workspaces(request.path, request.args, body)
            if not acct or accts != [acct]:
                return None
            from domain import activity_catalog as _cat
            g._activity_before = _cat.edit_before_value(
                CONFIG_PATH, acct, str(body.get("sku") or "").strip(),
                body.get("target"), str(body.get("key") or "").strip())
        except Exception:
            pass
        return None

    @app.after_request
    def _record_activity(response):
        # NEVER lets recording change the answer: every failure is swallowed.
        try:
            from domain import activity_catalog as _cat
            if not _cat.match(request.method, request.path):
                return response
            # A redirect (to sign-in), "sign in again" or "no sign-in
            # configured" means nothing ran and nobody can be named.
            if 300 <= response.status_code < 400 or response.status_code in (401, 503):
                return response
            if not _admitted():
                return response
            from auth import guard as _g
            if _g.cross_site_refusal(request.method, request.host,
                                     request.headers.get("Origin"),
                                     request.headers.get("Referer"),
                                     request.headers.get("Sec-Fetch-Site"),
                                     request.path):
                return response          # another website's request, refused
            body = _g.request_body_for_check(request) or {}
            ct = (request.content_type or "").lower()
            files = request.files if ct.startswith("multipart/form-data") else None
            from flask import g
            d = _cat.describe(request.method, request.path, body, request.args,
                              files, response, before=getattr(g, "_activity_before", None))
            if d:
                from domain import activity as _act
                # A person as the entity (team work) is named, not shown as an id.
                if d.get("entity_type") == "user" and d.get("entity_id"):
                    p = _act.person(CONFIG_PATH, d["entity_id"])
                    if p.get("label"):
                        d["summary"] = d["summary"].replace(d["entity_id"], p["label"])
                _act.record(CONFIG_PATH, d.pop("action"), method=request.method,
                            path=request.path, **d)
        except Exception:
            pass
        return response

    def _viewer_workspaces():
        """None = the viewer may open every account; else their list."""
        from auth import users as _u
        uid = session.get("uid")
        user = _u.get_user(CONFIG_PATH, uid) if uid else _u.bootstrap_user()
        ws = list((user or {}).get("workspaces") or [])
        return None if _u.ALL_WORKSPACES in ws else ws

    def _filters():
        a = request.args
        now = time.time()
        try:
            since = float(a.get("from") or (now - 86400))
            until = float(a.get("to") or (now + 60))
        except ValueError:
            raise ValueError("from/to must be epoch seconds")
        if until <= since:
            raise ValueError("the period ends before it starts")
        f = {}
        if "user" in a:
            f["user_id"] = str(a.get("user") or "")
        vw = _viewer_workspaces()
        acct = str(a.get("account") or "").strip()
        if acct in _g_sentinels():
            acct = ""                    # "__all__" etc. name no account
        if acct:
            # The guard refuses an account this viewer may not open; intersected
            # here as well so this reader never depends on that alone.
            f["workspaces"] = [acct] if (vw is None or acct in vw) else []
        elif vw is not None:
            f["workspaces"] = vw
        if a.get("marketplace"):
            f["marketplace"] = str(a.get("marketplace"))
        if a.get("category"):
            f["category"] = str(a.get("category"))
        if a.get("ok") in ("0", "1"):
            f["ok"] = a.get("ok") == "1"
        return since, until, f

    def _g_sentinels():
        from auth import guard as _g
        return _g.WORKSPACE_SENTINELS

    def _team():
        """The people the viewer may compare: everyone for a viewer of every
        account; otherwise only those who share one of the viewer's accounts
        (or work in every account). No email -- the full user list stays
        behind manage_users (/users/list)."""
        from auth import users as _u
        vw = _viewer_workspaces()
        out = []
        try:
            for u in _u.list_users(CONFIG_PATH):
                ws = list(u.get("workspaces") or [])
                if vw is not None and _u.ALL_WORKSPACES not in ws \
                        and not any(w in vw for w in ws):
                    continue
                out.append({"user_id": u.get("id"),
                            "label": u.get("name") or u.get("email"),
                            "role": u.get("role"),
                            "active": bool(u.get("active", True))})
        except Exception:
            return []
        return out

    @app.route("/activity/summary")
    def activity_summary():
        from domain import activity as _act
        try:
            since, until, f = _filters()
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify({"ok": True, "from": since, "to": until,
                        "categories": _act.CATEGORIES,
                        "people": _act.summary(CONFIG_PATH, since, until, **f),
                        "team": _team()})

    @app.route("/activity/list")
    def activity_list():
        from domain import activity as _act
        try:
            since, until, f = _filters()
            limit = int(request.args.get("limit") or 200)
            offset = int(request.args.get("offset") or 0)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        out = _act.entries(CONFIG_PATH, since, until, limit=limit, offset=offset, **f)
        return jsonify({"ok": True, "from": since, "to": until,
                        "categories": _act.CATEGORIES, **out})
