"""routes/aiusage_routes.py -- what the AI cost, per account and per feature.

    GET  /aiusage/summary   totals plus every breakdown behind them
    GET  /aiusage/calls     the individual calls, newest first

Reads only. Nothing here spends anything or changes a listing.

THE QUESTION THIS ANSWERS: "how many credits are used in which account of the
AI and for which feature". Both halves matter. A total is not actionable -- the
useful fact is that one account's image generation is most of the bill, and that
is only visible when account and feature are crossed.

WHAT IT REFUSES TO PRETEND. Three things are shown rather than smoothed over,
because each of them makes a number too small and a too-small number is the one
nobody questions:

  unpriced calls   a model whose price is not in the table records no cost at
                   all. The screen says how many, so the total reads as "at
                   least this much" instead of "this much".
  failed calls     a call that errored still spent its input tokens.
  unattributed     a call made outside any account records workspace_id "". It
                   is shown as its own row, never folded into whichever account
                   happened to be open.
"""
import datetime as _dt

from flask import request, jsonify

from domain import ai_usage as _usage

# A month, which is how a bill arrives.
DEFAULT_DAYS = 30

# A page of calls. Enough to see what a run did, small enough to stay quick.
CALL_LIMIT = 300


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /aiusage/* to the app."""

    def _window():
        """The dates being asked about. Defaults to the last 30 days."""
        end = (request.args.get("end") or "").strip()
        start = (request.args.get("start") or "").strip()
        if not end:
            end = _dt.date.today().isoformat()
        if not start:
            try:
                days = max(1, min(365, int(request.args.get("days") or DEFAULT_DAYS)))
            except Exception:
                days = DEFAULT_DAYS
            start = (_dt.date.fromisoformat(end) -
                     _dt.timedelta(days=days - 1)).isoformat()
        return start, end

    def _names():
        """Account id -> the name shown in the header.

        The ledger stores ids because a name can be edited; the screen shows
        names because an id is not what the owner calls the account.
        """
        out = {}
        try:
            for a in ((_cfg() or {}).get("accounts") or []):
                if a.get("id"):
                    out[str(a["id"])] = str(a.get("name") or a["id"])
        except Exception:
            pass
        return out

    @app.route("/aiusage/summary")
    def aiusage_summary():
        start, end = _window()
        # ACROSS ALL ACCOUNTS BY DEFAULT, deliberately. This screen exists to
        # compare accounts; scoping it to the open one would answer a question
        # nobody asked and hide the account actually running up the bill. Pass
        # ?id=<account> to narrow it.
        only = (request.args.get("id") or "").strip()
        try:
            data = _usage.summary(CONFIG_PATH, start=start, end=end,
                                  workspace_id=(only or None))
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read the usage record: %s"
                                     % str(e)[:160]}), 200
        names = _names()
        for row in data.get("by_account") or []:
            wid = str(row.get("workspace_id") or "")
            row["name"] = names.get(wid) or (wid or "not attributed to an account")
        for row in data.get("by_account_feature") or []:
            wid = str(row.get("workspace_id") or "")
            row["name"] = names.get(wid) or (wid or "not attributed to an account")
        data["start"] = start
        data["end"] = end
        data["scoped_to"] = only
        data["ok"] = True
        # Said in words on the screen, not just implied by a gap in a chart.
        notes = []
        if data.get("unpriced_calls"):
            notes.append(
                "%d call(s) used a model with no price in the table, so the "
                "totals below are a MINIMUM -- the real spend is higher."
                % data["unpriced_calls"])
        if data.get("failed_calls"):
            notes.append(
                "%d call(s) failed. A failed call still spends its input "
                "tokens, so they are counted here."
                % data["failed_calls"])
        if any(not (r.get("workspace_id") or "")
               for r in (data.get("by_account") or [])):
            notes.append(
                "Some calls are not attributed to an account -- they ran "
                "outside any account, from a background job or the command "
                "line. They are listed separately rather than assigned to a "
                "guess.")
        data["notes"] = notes
        return jsonify(data)

    @app.route("/aiusage/calls")
    def aiusage_calls():
        """The individual calls, for when a total looks wrong and you want why."""
        start, end = _window()
        only = (request.args.get("id") or "").strip()
        feature = (request.args.get("feature") or "").strip()
        where, args = ["day>=?", "day<=?"], [start, end]
        if only:
            where.append("workspace_id=?"); args.append(only)
        if feature:
            where.append("feature=?"); args.append(feature)
        try:
            from data import db as _db
            rows = [dict(r) for r in _db.get_db(CONFIG_PATH).execute(
                "SELECT id, day, at, workspace_id, feature, provider, model, "
                "       input_tokens, output_tokens, images, cost_usd, ok, "
                "       error, sku, ms "
                "FROM ai_usage WHERE " + " AND ".join(where) +
                " ORDER BY id DESC LIMIT ?", tuple(args) + (CALL_LIMIT,))]
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read the calls: %s"
                                     % str(e)[:160]}), 200
        names = _names()
        for r in rows:
            wid = str(r.get("workspace_id") or "")
            r["name"] = names.get(wid) or (wid or "not attributed")
        return jsonify({"ok": True, "rows": rows, "start": start, "end": end,
                        # Say when the list is cut short, rather than letting a
                        # truncated page read as the whole story.
                        "limited": len(rows) >= CALL_LIMIT,
                        "limit": CALL_LIMIT})
