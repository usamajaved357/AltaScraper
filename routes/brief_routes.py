"""routes/brief_routes.py -- the weekly brief.

    GET /brief   every account at once: what moved, what is off, what is
                 running out, and what could not be looked at

ONE ENDPOINT, because the brief is one answer. The arithmetic is in
domain/weekly_brief.py and takes a config rather than a request, so it can be
tested without a browser.

NOT SCOPED TO THE OPEN ACCOUNT, deliberately, and it is the only screen that is
not. Every other one answers for the account you chose, which is right for
working and wrong for noticing -- the account with a problem this week is the
one nobody opened.

READS ONLY. Nothing here contacts Amazon; every figure comes from data the app
has already synced.
"""
from flask import jsonify, request


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /brief to the app."""

    @app.route("/brief", methods=["GET"])
    def weekly_brief():
        from domain import weekly_brief as _wb

        day = (request.args.get("day") or "").strip() or None
        if day:
            import datetime
            try:
                datetime.date.fromisoformat(day)
            except ValueError:
                return jsonify({"ok": False, "error": "Bad date: %s" % day}), 400
        try:
            cfg = _cfg() if callable(_cfg) else (_cfg or {})
        except Exception:
            cfg = {}
        try:
            return jsonify(_wb.build(CONFIG_PATH, cfg, today=day))
        except Exception as e:
            # The brief reads five separate things across every account, and a
            # failure in one of them is reported by that section rather than
            # here. Reaching this means something broader broke, so it says so
            # instead of returning a brief with a silent hole in it.
            return jsonify({"ok": False,
                            "error": "Could not build the brief: %s"
                                     % str(e)[:200]}), 500
