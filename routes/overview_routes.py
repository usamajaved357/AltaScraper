"""routes/overview_routes.py -- every account and marketplace, month by month.

    GET /overview?months=13

    Orbit's Brand Overview: a month-by-month report across every marketplace,
    with the totals over the top.

WHY THIS IS THE ONE SCREEN THAT IS NOT SCOPED TO ONE ACCOUNT. Every other screen
in this app answers a question about the account you are standing in, and that
is right -- it is what stopped one account's orders appearing on another's. But
"how is the business doing" is not a question about one account. There are six,
and the only place they have ever been visible together is by opening each in
turn and adding up by hand.

NOTHING IS RECOMPUTED HERE. The figures come from domain/sales_data.series --
the same function the Sales screen draws -- bucketed by its own bucket(), so the
overview and the Sales screen cannot disagree. Rule 12: this arranges, it does
not calculate.

CURRENCIES ARE NEVER ADDED TOGETHER.

jack_uk trades in pounds and sheelady_us in dollars. £500 + $500 is not 1000 of
anything, and a single "total revenue" across them would be a made-up number
that looks authoritative. Orbit offers a USD/EUR toggle, which means it converts
somewhere -- converting needs an exchange rate for the day of each sale, this
app has none, and inventing one would put a fabricated figure at the top of the
most-read screen. So totals are grouped BY CURRENCY and the screen says why.
"""
import datetime

from flask import jsonify, request

MAX_MONTHS = 24


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /overview to the app."""

    @app.route("/overview", methods=["GET"])
    def overview():
        try:
            months = int(request.args.get("months") or 13)
        except ValueError:
            months = 13
        months = max(1, min(months, MAX_MONTHS))

        today = datetime.date.today()
        # First day of the month `months-1` back, so the current (partial) month
        # is included and labelled as partial rather than silently short.
        y, m = today.year, today.month - (months - 1)
        while m <= 0:
            m += 12
            y -= 1
        start = datetime.date(y, m, 1).isoformat()
        end = today.isoformat()

        try:
            import accounts as _acc
            cfg = (_cfg() or {}) if callable(_cfg) else {}
            accts = _acc.load_accounts(cfg, CONFIG_PATH) or []
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read the accounts: %s"
                                     % str(e)[:160]}), 500

        try:
            from domain import sales_data as _sd
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Sales data unavailable: %s" % str(e)[:160]}), 500

        # ONLY THE ACCOUNTS THIS USER MAY SEE.
        #
        #     "why is one user able to see the information of another user ...
        #      i am concerned that when i give this tool out to random people
        #      to test and use they will be able to see other people
        #      information"
        #
        # This is the one screen that deliberately reads every account, which
        # makes it the one screen where "every account" has to mean "every
        # account THEY may open". The doorman cannot help here: no account is
        # named in the request, so there is nothing for it to refuse.
        #
        # An owner with the "*" wildcard sees everything, exactly as before. A
        # user restricted to nestwell_goods sees nestwell_goods, and the screen
        # is honest about it rather than quietly showing a smaller total.
        allowed_note = ""
        try:
            from auth import users as _users
            from flask import session as _session
            _uid = _session.get("uid")
            _me = _users.get_user(CONFIG_PATH, _uid) if _uid else None
            if _me:
                _before = len(accts)
                accts = [a for a in accts
                         if _users.can_access_workspace(_me, str(a.get("id") or ""))]
                if len(accts) < _before:
                    allowed_note = (
                        "Showing the %d account%s you have access to, of %d."
                        % (len(accts), "" if len(accts) == 1 else "s", _before))
        except Exception:
            # A failure here must not widen access. If who-you-are cannot be
            # established, no account is aggregated.
            accts = []
            allowed_note = ("Could not establish which accounts you may see, so "
                            "none are shown.")

        blocks = []
        problems = []
        for a in accts:
            aid = str(a.get("id") or "")
            if not aid:
                continue
            mkt = str(a.get("default_marketplace") or "UK").upper()
            try:
                rows = _sd.series(CONFIG_PATH, aid, mkt, start, end) or []
            except Exception as e:
                problems.append("%s/%s: %s" % (aid, mkt, str(e)[:110]))
                continue
            if not rows:
                continue
            by, order = _sd.bucket(rows, "month")
            cur = ""
            try:
                cur = _sd.currency_of(rows) or ""
            except Exception:
                cur = ""
            months_out = []
            for key in order:
                mrows = by.get(key) or []
                # NOTHING STORED IS NOT ZERO SALES.
                #
                # series() returns a row for EVERY day in the window whether or
                # not anything was ever synced for it, and an unsynced day
                # carries ordered_sales=None rather than 0. Summing gives 0
                # either way, so without this check an account that has never
                # been synced draws a flat line of zeros -- a business shown as
                # trading nothing when the truth is nobody has looked.
                stored = any(r.get("ordered_sales") is not None or
                             r.get("units") is not None for r in mrows)
                sales = _sd.aggregate(mrows, "ordered_sales")
                units = _sd.aggregate(mrows, "units")
                orders = _sd.aggregate(mrows, "orders")
                # profit_for withholds the figure entirely unless EVERY unit in
                # the bucket is costed -- a partial cost of goods only ever
                # makes profit look better than it is. Passed straight through:
                # None here means "not knowable", never zero.
                try:
                    profit = _sd.profit_for(mrows)
                except Exception:
                    profit = None
                months_out.append({
                    "month": key, "sales": sales, "units": units,
                    "orders": orders, "profit": profit,
                    "days": len(mrows), "stored": stored,
                    # The current month is not a full month, and a chart that
                    # does not say so shows every business collapsing on the 3rd.
                    "partial": key[:7] == today.strftime("%Y-%m"),
                })
            blocks.append({
                "account": aid,
                "label": a.get("label") or aid,
                "marketplace": mkt,
                "currency": cur,
                "months": months_out,
                # An account with nothing stored in the whole window is listed
                # -- so you can see it exists and has not been synced -- but it
                # is not a trading account with zero sales, and the rest of the
                # screen has to be able to tell the two apart.
                "has_data": any(m["stored"] for m in months_out),
                "sales": sum((m["sales"] or 0) for m in months_out),
                "units": sum((m["units"] or 0) for m in months_out),
            })

        # TOTALS BY CURRENCY, never one grand total. See the module docstring.
        #
        # Accounts with nothing stored are EXCLUDED rather than folded into an
        # "unknown currency" bucket: a card reading "? — 0.00, 0 units, 3
        # accounts" is not a total of anything, it is three accounts nobody has
        # synced, and putting it beside a real total invites it to be read as
        # one.
        totals = {}
        for b in blocks:
            if not b["has_data"] or not b["currency"]:
                continue
            cur = b["currency"]
            t = totals.setdefault(cur, {"currency": cur, "sales": 0.0,
                                        "units": 0.0, "accounts": 0})
            t["sales"] += b["sales"] or 0
            t["units"] += b["units"] or 0
            t["accounts"] += 1
        unsynced = [b["label"] for b in blocks if not b["has_data"]]

        # One row of month labels, so the screen can lay every account against
        # the same columns even where an account has no rows for a month.
        labels = []
        for b in blocks:
            for m in b["months"]:
                if m["month"] not in labels:
                    labels.append(m["month"])
        labels.sort()

        out = {"ok": True, "start": start, "end": end, "months": months,
               "labels": labels, "blocks": blocks,
               "totals": sorted(totals.values(), key=lambda t: -t["sales"]),
               "unsynced": unsynced,
               "problems": problems,
               # Said out loud. A restricted user seeing three accounts must not
               # be left thinking that is the whole business.
               "access_note": allowed_note}
        if unsynced:
            out["unsynced_note"] = (
                "%s ha%s no stored sales for this period at all. That is not "
                "zero sales — nothing has been synced, so there is nothing to "
                "report either way."
                % (", ".join(unsynced), "s" if len(unsynced) == 1 else "ve"))
        if len(totals) > 1:
            out["currency_note"] = (
                "These accounts trade in %d different currencies, so they are "
                "totalled separately. Adding them would need an exchange rate "
                "for the day of each sale, which this app does not have — a "
                "single combined figure would be invented."
                % len(totals))
        if not blocks:
            out["note"] = ("No account has stored daily sales for this period "
                           "yet. Sync a sales report on at least one account.")
        return jsonify(out)
