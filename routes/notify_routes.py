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
