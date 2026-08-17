"""routes/finance_routes.py -- the Finance screen: contribution per product.

Reads only. It holds no arithmetic of its own: the per-product figures come from
domain/contribution.py, which in turn defers to domain/sales_data.py for the one
rule about when a contribution may be shown at all.
"""
import datetime as _dt

from flask import request, jsonify

from domain import contribution as _contrib
from routes import scope as _scope_mod


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach the /finance/* routes to the existing Flask app."""

    def _scope():
        """Which account and which marketplace -- resolved in ONE place.

        This screen used to stop at _state["active_marketplace"], which is only
        written when a marketplace is CHOSEN, and Finance is not the screen that
        chooses one. Opening the app and clicking straight here left it "" and
        the screen said "no marketplace selected" at an account with real sales
        sitting in the database. See routes/scope.py for the order and for the
        twenty-four places that were each deciding this for themselves.
        """
        return _scope_mod.resolve(
            state=_state, account=_active_account() or {},
            asked_id=request.args.get("id"),
            asked_marketplace=request.args.get("marketplace"),
            with_data=_marketplace_with_data,
            # The record must follow the id. This screen reads its figures by
            # WORKSPACE ID, which was already right, but it takes the account's
            # LABEL and its VAT registration from the record -- so a mismatch put
            # one company's name, and possibly another's VAT rate, on a page of
            # money. See routes/scope.py.
            load_account=_load_account)

    def _load_account(aid):
        """The account record for an id the PAGE named -- credentials included."""
        try:
            from domain import accounts as _acc_mod
            return _acc_mod.get_account(
                _cfg() if callable(_cfg) else (_cfg or {}), aid, CONFIG_PATH)
        except Exception:
            return None

    def _marketplace_with_data(wsid):
        """The one marketplace this account actually has finance rows for.

        Only when there is exactly one: choosing the biggest of several would be
        right most of the time and quietly wrong the rest, and this screen is
        where money is read off.
        """
        try:
            from data import db as _db
            rows = _db.get_db(CONFIG_PATH).execute(
                "SELECT DISTINCT marketplace FROM finance_daily "
                "WHERE workspace_id=? LIMIT 2", (wsid,)).fetchall()
            return rows[0]["marketplace"] if len(rows) == 1 else ""
        except Exception:
            return ""

    def _range():
        """The window, resolved to two dates. Defaults to the last 30 days.

        Deliberately the same shape the Sales screen uses, so a figure here and a
        figure there cover the same days and can be compared without arithmetic.
        """
        today = _dt.date.today()
        start = (request.args.get("start") or "").strip()
        end = (request.args.get("end") or "").strip()
        if not start or not end:
            end = today.strftime("%Y-%m-%d")
            start = (today - _dt.timedelta(days=29)).strftime("%Y-%m-%d")
        return start, end

    @app.route("/finance/contribution")
    def finance_contribution():
        acc, wsid, mkt = _scope()
        if not wsid:
            return jsonify({"ok": False, "error": _scope_mod.NO_ACCOUNT}), 400
        if not mkt:
            # Says what to DO, and names the account it could not work it out
            # for. "no marketplace selected" named the missing thing and not the
            # fix, on a screen with no marketplace picker to select one in.
            return jsonify({"ok": False, "error": (
                "%s (account: %s)" % (_scope_mod.NO_MARKETPLACE,
                                      acc.get("label") or wsid))}), 400
        start, end = _range()
        from domain import sales_data as _sd
        rows, totals = _contrib.by_product(CONFIG_PATH, wsid, mkt, start, end,
                                           vat_rate=_sd.vat_rate_for(_cfg, wsid))
        # WHY IT IS EMPTY, WHEN IT IS EMPTY.
        #
        # "Nothing in this period yet — press Sync" was the same sentence for
        # three completely different situations, and it was wrong for two of
        # them: pressing Sync does not help if the data is simply outside the
        # window you are looking at, and it does not help if the account has
        # never had a successful finance pull. Someone presses Sync, nothing
        # changes, and there is nothing on screen to say why.
        #
        # So when there are no rows, look at what this account has AT ALL and
        # say which of the three it is.
        empty_note, have = "", {}
        if not rows:
            try:
                from data import db as _db
                r = _db.get_db(CONFIG_PATH).execute(
                    "SELECT COUNT(*) n, MIN(date) a, MAX(date) b FROM finance_daily "
                    "WHERE workspace_id=? AND marketplace=?",
                    (wsid, mkt)).fetchone()
                have = {"rows": (r["n"] if r else 0) or 0,
                        "first": (r["a"] if r else None),
                        "last": (r["b"] if r else None)}
                other = _db.get_db(CONFIG_PATH).execute(
                    "SELECT marketplace, COUNT(*) n FROM finance_daily "
                    "WHERE workspace_id=? GROUP BY marketplace",
                    (wsid,)).fetchall()
                have["other_marketplaces"] = {x["marketplace"]: x["n"]
                                              for x in other
                                              if x["marketplace"] != mkt}
            except Exception:
                have = {}
            if have.get("rows"):
                empty_note = (
                    "This account has %d days of finance data, from %s to %s — "
                    "but none between %s and %s. Change the dates above to look "
                    "at a period that has data; syncing again will not add days "
                    "Amazon has no money movements for."
                    % (have["rows"], have["first"], have["last"], start, end))
            elif have.get("other_marketplaces"):
                empty_note = (
                    "Nothing for %s, but this account does have finance data for "
                    "%s. Switch marketplace at the top of the screen."
                    % (mkt, ", ".join(have["other_marketplaces"])))
            else:
                empty_note = (
                    "No finance data has ever been pulled for %s on %s. Press "
                    "Sync on the Sales screen — and watch what it reports: "
                    "Amazon limits these reports to roughly one a minute, so a "
                    "first pull often has to be pressed several times before it "
                    "has everything."
                    % (acc.get("label") or wsid, mkt))

        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "account_label": acc.get("label") or wsid,
                        "empty_note": empty_note, "have": have,
                        "start": start, "end": end,
                        "rows": rows, "totals": totals,
                        "notes": _contrib.notes(rows, totals),
                        "ads_connected": totals.get("ad_spend") is not None,
                        "currency": totals.get("currency") or ""})
