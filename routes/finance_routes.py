"""routes/finance_routes.py -- the Finance screen: contribution per product.

Reads only. It holds no arithmetic of its own: the per-product figures come from
domain/contribution.py, which in turn defers to domain/sales_data.py for the one
rule about when a contribution may be shown at all.
"""
import datetime as _dt

from flask import request, jsonify

from domain import contribution as _contrib
from domain import finance_coverage as _fcov   # its SQL (architecture batch A6)
from domain import finance_view as _fview     # its panels (architecture batch A8)
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
            rows = _fcov.marketplaces_with_data(CONFIG_PATH, wsid)
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
                r = _fcov.span(CONFIG_PATH, wsid, mkt)
                have = {"rows": (r["n"] if r else 0) or 0,
                        "first": (r["a"] if r else None),
                        "last": (r["b"] if r else None)}
                other = _fcov.rows_per_marketplace(CONFIG_PATH, wsid)
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
            _c, _f, _s = _fcov.settled_and_sold(CONFIG_PATH, wsid, mkt, start, end)
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
                _gap = _fcov.sales_after(_c, wsid, mkt, last, end)
                if float((_gap["s"] if _gap else 0) or 0) > 0:
                    notes.append({"level": "info", "text": (
                        "Nothing has settled after %s yet, so the last few days "
                        "of this period are not in the figures below. Amazon "
                        "pays out in arrears; those days will fill in." % last)})
        except Exception:
            pass
        # ACCOUNT-WIDE MONEY FILED UNDER THE WRONG MARKETPLACE, said first and
        # in red: the figures below then include money that is not this
        # marketplace's. Reported, never deleted (domain/finance_coverage).
        try:
            _mis = _fcov.misfiled(CONFIG_PATH, wsid, mkt)
        except Exception as _e:
            _mis = {"level": "warn", "text": (
                "Could not check whether this marketplace holds account-wide "
                "money filed here by mistake (%s)." % str(_e)[:120])}
        if _mis:
            notes.insert(0, _mis)

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

    @app.route("/finance/resync", methods=["POST"])
    def finance_resync():
        """Re-read the last 95 days of this account's money from Amazon.

        The Sales screen's Sync pulls 30 days, and the background refresher's
        95-day pull stops after a small page budget. After a fix to how the
        money is filed, the owner needs one complete re-read per account: this
        is it. Always under the account's HOME marketplace, because the feed is
        account-wide (domain/finance_fetch.sync decides and refuses to guess).

        The account is the one the PAGE named (acctBody, Rule 14) -- never the
        server's open account -- and the guard checks it like any write.
        """
        import domain.request_account as _req_acct
        from domain import accounts as _acc_mod
        from domain import finance_fetch as _ff
        aid = _req_acct.named(request)
        if not aid:
            return jsonify({"ok": False, "error": (
                "Which account? The request did not name one, so nothing was "
                "pulled. Reload the Finance screen and try again.")}), 400
        acc = _load_account(aid)
        if not acc:
            return jsonify({"ok": False, "error":
                            "There is no account called %r in this app." % aid}), 404
        if not _acc_mod.seller_scope_allowed(acc):
            return jsonify({"ok": False, "error": (
                "%s has no Amazon connection of its own, so it has no finances "
                "to read." % (acc.get("label") or aid))}), 400
        home, why = _acc_mod.home_marketplace(CONFIG_PATH, aid)
        if not home:
            return jsonify({"ok": False, "error": (
                "Nothing was pulled: %s. Set the account's default marketplace "
                "first." % why)}), 400
        try:
            from domain import cogs_store as _cs
            overrides = _cs.all_overrides(CONFIG_PATH)
        except Exception:
            overrides = None
        # A PERSON'S SYNC: the background refresher stands aside for this
        # account while it runs (and briefly after), as it does for a forced
        # catalogue sync -- two finance pulls of one account at once compete
        # for the same Amazon quota.
        #
        # RUN AS A BACKGROUND JOB (review, 30 Sep 2026): at one Finances call
        # every two seconds a 95-day re-read outlives a proxied web request.
        # This returns at once; GET /finance/resync/status reports progress.
        import domain.live_refresher as _refresher
        from domain import finance_resync_job as _job
        _key = "%s::%s" % (aid, home)
        creds = _acc_mod.account_creds(acc)

        def _run(log):
            _refresher.user_sync_started(_key)
            try:
                res = _ff.sync(CONFIG_PATH, aid, home, creds, account_id=aid,
                               days_back=_ff.RESYNC_DAYS, max_pages=_ff.RESYNC_PAGES,
                               cogs_overrides=overrides, log=log)
            finally:
                _refresher.user_sync_finished(_key)
            res["marketplace"] = home
            res["account"] = aid
            return res

        job, started = _job.start(aid, _run)
        return jsonify({"ok": True, "started": started, "running": True,
                        "account": aid, "marketplace": home, "job": job})

    @app.route("/finance/resync/status")
    def finance_resync_status():
        """The named account's Re-read job: running (pages read so far), or
        finished with the sync's result. Reads only; names its account."""
        import domain.request_account as _req_acct
        from domain import finance_resync_job as _job
        aid = _req_acct.named(request)
        if not aid:
            return jsonify({"ok": False, "error": "Which account?"}), 400
        return jsonify({"ok": True, "account": aid, "job": _job.get(aid)})

    # Both panels live in domain/finance_view.py (architecture batch A8).
    def _finance_previous(wsid, mkt, start, end, basis):
        return _fview.previous_window(CONFIG_PATH, _cfg, wsid, mkt, start, end, basis)

    def _finance_overhead(wsid, mkt, start, end, totals):
        return _fview.overhead(CONFIG_PATH, wsid, mkt, start, end, totals)
