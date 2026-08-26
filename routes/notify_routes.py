"""routes/notify_routes.py -- where alerts get sent, other than this screen.

    GET    /notify/channels    what is set up (never the full URL)
    POST   /notify/channels    add one -- switched OFF
    POST   /notify/channel     enable/disable, rename, narrow its events
    DELETE /notify/channel     remove one
    POST   /notify/test        send one obviously-a-test message
    GET    /notify/log         what was sent, skipped or failed
    POST   /notify/send        send the CURRENT alerts now

THERE IS NO AUTOMATIC SEND ANYWHERE. /notify/send is a button. Nothing on a
timer calls it, and domain/notify sends nothing until a channel has been both
added and explicitly enabled. Posting into somebody's Slack is outward-facing
and cannot be taken back, so it happens when a person asks for it.

/notify/send builds its message from the tracker alerts that already exist --
it does not invent a new judgement about what is wrong. One definition of "off
target" (domain/trackers), read by both the screen and the message, so a
notification can never disagree with the app it came from.
"""
from flask import jsonify, request

from domain import notify as _n


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /notify/* to the app."""

    def _acct():
        aid = (request.args.get("id") or request.args.get("account_id") or "").strip()
        body = request.get_json(silent=True) or {}
        aid = aid or str(body.get("id") or body.get("account_id") or "").strip()
        if not aid:
            try:
                acc = (_active_account() or {}) if callable(_active_account) else {}
            except Exception:
                acc = {}
            aid = str(acc.get("id") or (_state or {}).get("active_account_id") or "")
        return aid

    # ---- the bell: what the app has told you, in the app ------------------
    #
    # WHY THIS EXISTS SEPARATELY FROM THE CHANNELS ABOVE. Those send outward --
    # Slack, a webhook -- and only for the handful of things worth interrupting
    # somebody about. The bell is the DURABLE record: the four-hourly run
    # happens when this page is closed, so a toast would be gone before anyone
    # could read it, and the price that changed at 3am would be a change nobody
    # was ever told about.
    #
    # Reading is open to any signed-in user, like the dry run is: being told
    # what the app did changes nothing.
    @app.route("/notify/inbox", methods=["GET"])
    def notify_inbox():
        """The bell: how many are unread, and the most recent few."""
        try:
            limit = max(1, min(50, int(request.args.get("limit") or 12)))
        except (TypeError, ValueError):
            limit = 12
        wsid = _acct()
        return jsonify({
            "ok": True,
            # Scoped to the account being looked at, for the same reason every
            # other screen is: one account's prices are not another's business.
            "unread": _n.unread_count(CONFIG_PATH, workspace_id=wsid),
            "rows": _n.recent(CONFIG_PATH, workspace_id=wsid, limit=limit)})

    @app.route("/notify/read", methods=["POST"])
    def notify_read():
        """Mark some, or all of this account's, as read."""
        b = request.get_json(silent=True) or {}
        ids = [int(x) for x in (b.get("ids") or []) if str(x).strip().isdigit()]
        wsid = _acct()
        n = _n.mark_read(CONFIG_PATH, ids=ids or None,
                         workspace_id=None if ids else wsid)
        return jsonify({"ok": True, "marked": n,
                        "unread": _n.unread_count(CONFIG_PATH, workspace_id=wsid)})

    @app.route("/notify/channels", methods=["GET"])
    def notify_channels():
        # include_secret is never passed here: the full webhook URL is a bearer
        # credential and must not travel to a browser that will render it.
        return jsonify({"ok": True, "channels": _n.channels(CONFIG_PATH),
                        "quiet_hours": _n.QUIET_HOURS, "kinds": list(_n.KINDS)})

    @app.route("/notify/channels", methods=["POST"])
    def notify_add():
        b = request.get_json(silent=True) or {}
        return jsonify(_n.add_channel(
            CONFIG_PATH,
            kind=b.get("kind"), url=b.get("url"), label=b.get("label", ""),
            account=b.get("account") or "",
            events=b.get("events") or [],
            # Adding an address and starting to broadcast to it are two
            # decisions. A screen that wants both asks for both.
            enabled=bool(b.get("enabled"))))

    @app.route("/notify/channel", methods=["POST"])
    def notify_set():
        b = request.get_json(silent=True) or {}
        cid = b.get("id")
        if cid is None:
            return jsonify({"ok": False, "error": "Which channel?"}), 400
        return jsonify(_n.set_channel(
            CONFIG_PATH, cid,
            enabled=b.get("enabled", None),
            label=b.get("label", None),
            events=b.get("events", None)))

    @app.route("/notify/channel", methods=["DELETE"])
    def notify_remove():
        cid = request.args.get("id") or (request.get_json(silent=True) or {}).get("id")
        if cid is None:
            return jsonify({"ok": False, "error": "Which channel?"}), 400
        return jsonify(_n.remove_channel(CONFIG_PATH, cid))

    @app.route("/notify/test", methods=["POST"])
    def notify_test():
        b = request.get_json(silent=True) or {}
        cid = b.get("id")
        if cid is None:
            return jsonify({"ok": False, "error": "Which channel?"}), 400
        return jsonify(_n.test(CONFIG_PATH, cid))

    @app.route("/notify/log", methods=["GET"])
    def notify_log():
        try:
            limit = int(request.args.get("limit") or 50)
        except ValueError:
            limit = 50
        return jsonify({"ok": True, "log": _n.log(CONFIG_PATH, limit)})

    @app.route("/notify/send", methods=["POST"])
    def notify_send():
        """Send whatever is currently off target.

        Deliberately NOT a fresh check of Amazon: it sends what the app already
        knows. A button that both fetched and broadcast would make a slow
        outward-facing action out of a quick one, and would let a fetch failure
        turn into a silence that looked like good news.
        """
        wsid = _acct()
        try:
            from domain import trackers as _t
            a = _t.alerts(CONFIG_PATH, wsid)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read the alerts: %s" % str(e)[:160]}), 500
        if not a["count"]:
            return jsonify({"ok": True, "sent": 0, "skipped": 0, "failed": 0,
                            "note": "Nothing is off target, so there is nothing "
                                    "to send."})
        lines = []
        for r in a["rows"][:20]:
            drift = ("%+.0f%%" % (r["drift"] * 100)) if r.get("drift") is not None else "?"
            lines.append("%s — %s is %s (target %s, %s off)"
                         % (r["asin"], r["tracker"],
                            r["value"] if r["value"] is not None else "unknown",
                            r["target"] if r["target"] is not None else "none",
                            drift))
        if a["count"] > 20:
            # Said out loud rather than silently truncated: a list that stops at
            # twenty without saying so reads as "there were twenty".
            lines.append("…and %d more." % (a["count"] - 20))
        subject = "%d tracker%s off target" % (a["count"], "" if a["count"] == 1 else "s")
        # The key is the SET of what is wrong, so an unchanged situation stays
        # quiet but a new breach sends immediately rather than waiting out the
        # window on somebody else's alert.
        key = "trackers:%s:%s" % (wsid, ",".join(sorted(
            "%s/%s" % (r["asin"], r["metric"]) for r in a["rows"])))
        res = _n.send(CONFIG_PATH, subject, lines, event="tracker",
                      account=wsid, key=key,
                      force=bool((request.get_json(silent=True) or {}).get("force")))
        return jsonify(res)
