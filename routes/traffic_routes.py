"""routes/traffic_routes.py -- the Traffic & Conversions screen.

One endpoint. Every figure the page draws is made in domain/traffic_view.py, so
the tiles, the charts and the table cannot disagree about a number they all
describe -- which is the failure the Sales screen had to be rescued from twice.

Reading only: this screen sends nothing to Amazon and changes nothing, so it
needs no permission beyond being able to see the account's sales.
"""

import datetime as _dt

from flask import jsonify, request


def _range():
    """start, end, preset -- the window the page is asking about.

    ENDS YESTERDAY. The Sales & Traffic report never carries today, so including
    it would put a guaranteed empty column on the right of every chart and drag
    every rate on the page down with it.
    """
    preset = (request.args.get("preset") or "30d").strip()
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()
    if preset == "custom" and start and end:
        return start, end, preset
    stem = preset[:-1] if preset.endswith("d") else preset
    try:
        days = int(stem)
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 400))
    last = _dt.date.today() - _dt.timedelta(days=1)
    first = last - _dt.timedelta(days=days - 1)
    return first.isoformat(), last.isoformat(), preset


def _previous(start, end):
    """The same number of days immediately before, for the change figures."""
    try:
        s = _dt.date.fromisoformat(start)
        e = _dt.date.fromisoformat(end)
    except (TypeError, ValueError):
        return None
    span = (e - s).days + 1
    p_end = s - _dt.timedelta(days=1)
    p_start = p_end - _dt.timedelta(days=span - 1)
    return p_start.isoformat(), p_end.isoformat()


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state, **_kw):
    from domain import traffic_view as _tv

    def _scope():
        """Which account and marketplace this request is about.

        Read the same way every other sales route reads it, so a request cannot
        be answered for a different account than the one on screen -- the bug
        this app has shipped three times.
        """
        acc = _active_account() or {}
        wsid = str(acc.get("id") or "")
        mkt = (request.args.get("marketplace") or "").strip()
        if not mkt or mkt == "__all__":
            mkt = str(acc.get("default_marketplace") or "")
        return acc, wsid, mkt

    @app.route("/traffic/summary")
    def traffic_summary():
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        start, end, preset = _range()
        group = "parent" if (request.args.get("group") or "").lower() == "parent" else "asin"
        # The period immediately before, of the same length, so each tile can
        # carry an honest change rather than a bare figure.
        prev = _previous(start, end)
        try:
            out = _tv.summary(CONFIG_PATH, wsid, mkt, start, end,
                              group=group, prev=prev)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:300]}), 500
        out.update({"ok": True, "workspace": wsid, "marketplace": mkt,
                    "preset": preset,
                    "compared_to": ({"start": prev[0], "end": prev[1]} if prev else None)})
        if out.get("empty"):
            out["note"] = ("Amazon has sent no traffic figures for this period "
                           "yet. Sessions and page views come from the Sales & "
                           "Traffic report, which runs a day or two behind — "
                           "press Sync on the Sales screen to pull what it has.")
        return jsonify(out)
