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
        # `account` IS THE NAME, and `id` still answers.
        #
        #     "Standardize the account parameter name across all routes. Pick
        #      ONE name — use 'account' everywhere."
        #
        # This one was missed and still read `id` alone, so a caller using the
        # standard spelling fell through to whichever workspace happened to be
        # open -- silently, and on a page of money. request_account.named() is
        # the shared reader; `id` is kept behind it so nothing that already
        # works stops working.
        import domain.request_account as _req_acct
        return _scope_mod.resolve(
            state=_state, account=_active_account() or {},
            asked_id=(_req_acct.named(request) or request.args.get("id")),
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
        # TWO CALENDARS, AND THE SCREEN SAYS WHICH IS ON.
        #
        #   settlement  finance_daily -- money that has MOVED. Ties to the
        #               payout, and lags: measured on nestwell_goods for August
        #               it returns ONE product on an account where forty-five
        #               sold, which reads as "nothing sold" unless it is labelled.
        #   orders      order_lines -- everything PLACED in the window, settled
        #               or not. Fifteen products for the same month. Ties to
        #               what was sold.
        #
        # Neither is the truer figure; they answer different questions. The
        # default is orders because that is the one somebody opening a month
        # expects to see, and the reply names the basis either way.
        basis = (request.args.get("basis") or "orders").strip().lower()
        if basis not in ("orders", "settlement"):
            basis = "orders"
        vat = _sd.vat_rate_for(_cfg, wsid)
        if basis == "settlement":
            rows, totals = _contrib.by_product(CONFIG_PATH, wsid, mkt,
                                               start, end, vat_rate=vat)
            totals.setdefault("basis", "settlement")
        else:
            rows, totals = _contrib.by_product_orders(CONFIG_PATH, wsid, mkt,
                                                      start, end, vat_rate=vat)
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

        # HOW MUCH OF THE PERIOD HAS ACTUALLY SETTLED.
        #
        # This screen reads Amazon's Finances feed -- money that has MOVED --
        # and Amazon settles days later. So a table headed "contribution per
        # product" can cover a fraction of the period while looking complete.
        #
        # MEASURED 21 Aug 2026, asking for the last 30 days:
        #     jack_uk           4 products settled, 47 sold; last settled 16 Aug
        #     nestwell_goods    2 products settled, 40 sold; 5 days of 30
        #
        # The empty case has been explained carefully for a while (see above).
        # The PARTIAL case had nothing at all, and it is the commoner one. Said
        # in the same list of notes the screen already draws, so there is no
        # second place for a caveat to hide.
        notes = _contrib.notes(rows, totals)
        try:
            from data import db as _db
            _c = _db.get_db(CONFIG_PATH)
            _f = _c.execute(
                "SELECT COUNT(DISTINCT asin) a, MAX(date) last FROM finance_daily "
                "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=?",
                (wsid, mkt, start, end)).fetchone()
            _s = _c.execute(
                "SELECT COUNT(DISTINCT asin) a FROM sales_daily "
                "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
                "  AND asin<>'*'", (wsid, mkt, start, end)).fetchone()
            settled = int((_f["a"] if _f else 0) or 0)
            sold = int((_s["a"] if _s else 0) or 0)
            last = (_f["last"] if _f else None) or ""
            if rows and sold and settled < sold:
                notes.append({"level": "warn", "text": (
                    "Amazon has settled %d of the %d products that sold in this "
                    "period%s. The rest have been ordered but not paid out yet, "
                    "so they are not in the table below — this is what has "
                    "MOVED, not what was sold. The Sales screen shows the "
                    "ordered figures."
                    % (settled, sold,
                       (", and nothing after %s" % last) if last else ""))})
            elif rows and last and last < end:
                # ONLY IF SOMETHING WAS SOLD IN THE GAP. A period that ends in
                # the future, or a quiet tail, has nothing missing -- saying
                # "the last few days are not in the figures" about days with no
                # sales is a warning about nothing, and those are the ones that
                # teach a reader to skip the list.
                _gap = _c.execute(
                    "SELECT COALESCE(SUM(ordered_sales),0) s FROM sales_daily "
                    "WHERE workspace_id=? AND marketplace=? AND asin='*' "
                    "  AND date>? AND date<=?",
                    (wsid, mkt, last, end)).fetchone()
                if float((_gap["s"] if _gap else 0) or 0) > 0:
                    notes.append({"level": "info", "text": (
                        "Nothing has settled after %s yet, so the last few days "
                        "of this period are not in the figures below. Amazon "
                        "pays out in arrears; those days will fill in." % last)})
        except Exception:
            pass

        # WHAT THE ACCOUNT WAS CHARGED THAT NO PRODUCT ROW CARRIES, plus the
        # costs Amazon never sees. Together these are the gap between what the
        # products contributed and what the business actually kept.
        overhead = _finance_overhead(wsid, mkt, start, end, totals)

        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "account_label": acc.get("label") or wsid,
                        "empty_note": empty_note, "have": have,
                        "start": start, "end": end,
                        "basis": basis,
                        "rows": rows, "totals": totals,
                        "notes": notes,
                        "overhead": overhead,
                        # The window before this one, same length, for the
                        # "vs prev" figures the cards carry.
                        "previous": _finance_previous(wsid, mkt, start, end,
                                                      basis),
                        "ads_connected": totals.get("ad_spend") is not None,
                        "currency": totals.get("currency") or ""})

    def _finance_previous(wsid, mkt, start, end, basis):
        """The same window, immediately before. Totals only.

        Every "vs prev 30d" on the cards is against this. Returns None rather
        than zeros when the earlier window has nothing -- a move from no data to
        a number is not a rise, and rendering it as one invites somebody to
        celebrate a sync finishing.
        """
        import datetime as _dt
        try:
            s = _dt.date.fromisoformat(start)
            e = _dt.date.fromisoformat(end)
        except ValueError:
            return None
        span = (e - s).days + 1
        pe = s - _dt.timedelta(days=1)
        ps = pe - _dt.timedelta(days=span - 1)
        from domain import sales_data as _sd
        try:
            fn = (_contrib.by_product if basis == "settlement"
                  else _contrib.by_product_orders)
            _rows, tot = fn(CONFIG_PATH, wsid, mkt, ps.isoformat(),
                            pe.isoformat(), vat_rate=_sd.vat_rate_for(_cfg, wsid))
        except Exception:
            return None
        if not _rows:
            return None
        tot["start"] = ps.isoformat()
        tot["end"] = pe.isoformat()
        return tot

    def _finance_overhead(wsid, mkt, start, end, totals):
        """The gap between contribution and net profit, itemised as far as it can be.

        THE SPEC ASKS FOR EIGHT NAMED AMAZON FEE TYPES -- fba_inbound_transportation,
        fba_disposal, deal_participation and the rest. THOSE ARE NOT STORED.
        domain/finance_data buckets every charge into referral, FBA, promo or
        "other", and only the bucket survives; the fee TYPE Amazon sent is not
        kept. So the accordion shows the two lines that ARE knowable -- what
        Amazon charged the account outside any order, and the costs entered by
        hand -- and says plainly that the rest cannot be broken down yet rather
        than inventing eight rows of plausible names.

        That is a real limitation with a real fix (keep the fee type on the way
        in), and naming it is how it gets fixed rather than papered over.
        """
        out = {"items": [], "total": 0.0, "why": ""}

        # THE SAME CHARGE WHICHEVER CALENDAR IS ON. This read
        # totals["unattributed_fees"], which is derived by comparing Amazon's
        # settled figures against the product ROWS -- a comparison that only
        # holds when those rows came from the settlement feed. On the order
        # calendar the rows cover far more revenue than Amazon has settled, so
        # the gap came out nought and the overhead line read 65.51 on one tab
        # and 0.00 on the other, for the same month and the same subscription.
        # domain/expenses owns the figure now and neither half of it depends on
        # the basis (Rule 12).
        try:
            from domain import expenses as _exp0
            unatt = _exp0.account_level_charge(CONFIG_PATH, wsid, mkt, start, end)
        except Exception:
            unatt = float(totals.get("unattributed_fees") or 0.0)
        if unatt:
            out["items"].append({
                "label": "Amazon charges that belong to no order",
                "amount": round(unatt, 2),
                "note": ("The monthly selling subscription is the usual one. "
                         "Amazon posts these against the account rather than a "
                         "sale, so no per-product row can carry them."),
                "children": [],
            })

        try:
            from domain import expenses as _exp
            man = _exp.for_window(CONFIG_PATH, wsid, mkt, start, end)
        except Exception:
            man = {"total": 0.0, "items": [], "recorded": 0}
        out["items"].append({
            "label": "Your own costs",
            # RECORDED NONE AND SPENT NONE ARE DIFFERENT, and the accordion says
            # which: None reads "not recorded", 0.00 is a measurement.
            "amount": (round(float(man.get("total") or 0), 2)
                       if man.get("recorded") else None),
            "note": ("The accountant, the software, the packaging — Amazon "
                     "reports none of it." if man.get("recorded") else
                     "Nothing recorded, so nothing has been subtracted for it."),
            "children": [{"label": x["name"], "amount": x["in_window"]}
                         for x in (man.get("items") or [])],
        })

        out["total"] = round(unatt + float(man.get("total") or 0), 2)
        out["why"] = (
            "Amazon sends a type with every charge — storage, inbound "
            "transportation, disposal, deal participation — but this app keeps "
            "only the bucket it falls into, so those cannot be listed "
            "separately yet. The total above is right; the breakdown inside it "
            "is not available.")
        c = totals.get("contribution")
        out["contribution"] = c
        out["net_profit"] = (round(c - out["total"], 2) if c is not None else None)
        return out
