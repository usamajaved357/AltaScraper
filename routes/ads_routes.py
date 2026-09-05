"""routes/ads_routes.py -- advertising figures for screens that are not Sales.

WHY A FILE OF ITS OWN
The Sales page's advertising panels live in sales_routes.py because they belong
to that screen's period and its scope. This is the other shape: "for these
products, what did advertising cost", asked by the Listings page and by anything
else that shows a product rather than a period.

WHAT IT DOES NOT DO
It does not compute ACOS twice. domain/sales_data.py already defines ACOS as
spend over ad_sales and the Sales page reads it from there; this returns the same
ratio built the same way, from the same table, and adds no second definition of
what a rate means (CLAUDE.md Rule 12).

IT READS. Nothing here asks Amazon for anything -- it queries ads_daily, which
domain/ads_sync.py fills. A screen that renders a hundred rows must not be able
to make a hundred API calls.

THE ASIN IS OURS, NOT THE COMPETITOR'S
Every row on the Listings page carries two ASINs: the one in its SKU, which is a
COMPETITOR reference used to pull product data during generation, and the account's
own live ASIN. Advertising is bought against OURS. The browser decides which is
which -- static/js/listings.js rowAsin() already owns that rule -- and sends only
the ones it has resolved, so this endpoint never has to guess and can never
report a competitor's ASIN as having cost us money.
"""
from flask import jsonify, request

from routes import scope as _scope_mod


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /ads/* to the app."""
    import domain.request_account as _req_acct

    def _account_by_id(aid):
        try:
            import accounts as _acc_mod
            return _acc_mod.get_account(_cfg(), aid, CONFIG_PATH)
        except Exception:
            return None

    def _scope():
        """Which workspace and marketplace this request is about.

        The SAME resolver sales_routes uses, in the same order -- the account
        the PAGE named first, the global only as a fallback. routes/scope.py
        exists precisely so this is not decided a fifteenth way (Rule 12).
        """
        aid, acc = _req_acct.for_read(request, _state, get_account=_account_by_id)
        if acc is None:
            try:
                acc = _active_account()
            except Exception:
                acc = None
        wsid = str(aid or (acc or {}).get("id")
                   or _state.get("active_account_id", "") or "") or "_no_account"
        mkt = _scope_mod.marketplace(
            state=_state, account=(acc or {}),
            asked=(request.args.get("marketplace")
                   or (request.get_json(silent=True) or {}).get("marketplace")))
        return acc, wsid, mkt

    def _window(default_days=30):
        """The period to sum over. Defaults to 30 days ending yesterday.

        Same rule as domain/ads_sync.window(): today is always partial, and a
        part-day counted as a whole one makes the most recent figure dip.
        """
        import datetime as dt
        start = (request.args.get("start") or "").strip()
        end = (request.args.get("end") or "").strip()
        if start and end:
            return start, end
        try:
            days = max(1, min(400, int(request.args.get("days") or default_days)))
        except (TypeError, ValueError):
            days = default_days
        e = dt.date.today() - dt.timedelta(days=1)
        return (e - dt.timedelta(days=days - 1)).isoformat(), e.isoformat()

    @app.route("/ads/by-asin")
    def ads_by_asin():
        """Advertising cost and return, per ASIN, for this workspace.

        Optional ?asins=B0...,B0... narrows it to the products a screen is
        actually showing. Without it, every advertised ASIN in the window comes
        back -- which is what a page wants when it is about to render all of
        them anyway, and is one query either way.

        An ASIN with no advertising is ABSENT from the reply rather than present
        with zeros. A product that was never advertised and a product that was
        advertised and sold nothing are different facts, and the screen has to
        be able to tell them apart.
        """
        from data import db as _db
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        start, end = _window()

        want = [a.strip().upper() for a in
                (request.args.get("asins") or "").split(",") if a.strip()]
        sql = ("SELECT asin, SUM(impressions) impressions, SUM(clicks) clicks, "
               "SUM(spend) spend, SUM(ad_orders) ad_orders, SUM(ad_sales) ad_sales "
               "FROM ads_daily WHERE workspace_id=? AND marketplace=? "
               "AND date>=? AND date<=? AND asin<>'*'")
        args = [wsid, mkt, start, end]
        if want:
            # Chunked into the placeholders SQLite will accept rather than
            # interpolated -- a screen can legitimately ask about hundreds.
            want = want[:900]
            sql += " AND asin IN (%s)" % ",".join("?" * len(want))
            args += want
        sql += " GROUP BY asin"

        out = {}
        conn = _db.get_db(CONFIG_PATH)
        for r in conn.execute(sql, args):
            spend, sales, clicks = r["spend"], r["ad_sales"], r["clicks"]
            out[r["asin"]] = {
                "impressions": r["impressions"], "clicks": clicks,
                "spend": spend, "ad_orders": r["ad_orders"], "ad_sales": sales,
                # None, never 0, when there is no ratio to state: spend with no
                # sales has no ACOS, and 0% would read as perfect efficiency.
                "acos": (100.0 * spend / sales) if (spend is not None and sales) else None,
                "roas": (sales / spend) if (sales is not None and spend) else None,
                "cpc": (spend / clicks) if (spend is not None and clicks) else None,
            }

        # Whether the account is connected at all, so a screen can tell "no ad
        # spend on this product" from "this app cannot see your advertising".
        try:
            from domain import sales_data as _sd
            av = _sd.availability(CONFIG_PATH, wsid, mkt).get("ads") or {}
        except Exception:
            av = {}
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "start": start, "end": end,
                        "connected": bool(av.get("connected")),
                        "note": av.get("note") or "",
                        "asins": out, "count": len(out)})

    @app.route("/listings/where")
    def listings_where():
        """WHICH ACCOUNT HOLDS THE DRAFT OF THIS SKU. Reads only.

            "i see an error savedfailed no listing with this sku in this
             workspace ... many of the listings dont hold the information we
             have in amazon ... it dont have anything bullet points,
             description, backend search terms"

        One cause, four symptoms. A listing that is LIVE under one account can
        have its draft filed under ANOTHER -- measured on this database, 26 of
        nestwell_goods' 39 live UK listings have their draft under jack_uk. From
        the nestwell workspace the app then has no draft to read, so:

            editing says there is no listing with that SKU -- literally true
            bullets, description and search terms are blank -- the live
              catalogue pull is a SUMMARY (sku, asin, title, price, qty, status,
              brand, fulfillment, image) and carries none of the three
            fields fall back to defaults, which is where "number of items 1"
              comes from while Amazon shows 2 -- the draft says 2, and it is in
              the other account

        A SKU does not identify an account: the owner deliberately runs the same
        SKU on more than one. So this answers WHERE, and the screen can say it
        instead of showing blanks that read as missing data.

        It does not move anything. Which account a listing belongs to is the
        owner's decision, not a thing to infer and act on.
        """
        from data import db as _db
        sku = (request.args.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no sku given"}), 400
        _acc, wsid, _mkt = _scope()
        conn = _db.get_db(CONFIG_PATH)

        rows = [dict(r) for r in conn.execute(
            "SELECT workspace_id, status, "
            "LENGTH(COALESCE(bullet_1,'')) bullets, "
            "LENGTH(COALESCE(description_html,'')) description, "
            "LENGTH(COALESCE(search_terms,'')) search_terms, "
            "number_of_items, updated_at "
            "FROM listings WHERE sku=?", (sku,))]

        labels = {}
        try:
            cfg = _cfg() if callable(_cfg) else (_cfg or {})
            for a in (cfg.get("accounts") or []):
                labels[str(a.get("id"))] = str(a.get("label") or a.get("id"))
        except Exception:
            pass
        for r in rows:
            r["label"] = labels.get(r["workspace_id"], r["workspace_id"])

        here = [r for r in rows if r["workspace_id"] == wsid]
        elsewhere = [r for r in rows if r["workspace_id"] != wsid]
        return jsonify({
            "ok": True, "sku": sku, "workspace": wsid,
            "here": bool(here), "drafts": rows,
            "elsewhere": elsewhere,
            "note": ("" if here else
                     ("This workspace holds no draft of %s, so its bullets, "
                      "description and search terms cannot be shown and editing "
                      "it will fail. The draft is under %s. Amazon's own "
                      "catalogue carries only the summary — price, quantity, "
                      "status, title and image — never the copy."
                      % (sku, ", ".join(r["label"] for r in elsewhere))
                      if elsewhere else
                      "No account holds a draft of %s. It exists on Amazon but "
                      "this app has never generated or imported it, so there is "
                      "nothing to edit and no copy to show." % sku)),
        })

    @app.route("/ads/diag")
    def ads_diag():
        """WHY IS THE CHART STILL A PLACEHOLDER? -- answered from the tables.

        The Organic vs PPC chart switches on ONE thing: whether the sales series
        carries a non-zero ad_sales cell. That series reads ads_daily, filtered
        by workspace, marketplace, date range and asin='*'. Four separate ways
        for data to exist and still not reach the chart:

            stored under a different MARKETPLACE than the screen is showing
            stored outside the DATE RANGE the screen is showing
            stored per-ASIN but with no '*' account-wide row
            stored, and reaching the chart, but every ad_sales is zero

        The campaign table reads a DIFFERENT table (ads_campaign_daily), so
        "the campaigns are there but the chart is not" is a real and specific
        state -- and none of the screens could say which of the four it was.
        This reports all of them at once, reads nothing from Amazon, and writes
        nothing.
        """
        from data import db as _db
        _acc, wsid, mkt = _scope()
        start, end = _window()
        conn = _db.get_db(CONFIG_PATH)
        q = lambda s, *a: [dict(r) for r in conn.execute(s, a)]

        # SPLIT BY GRAIN, or the totals read as double.
        #
        # ads_daily holds the same money twice on purpose: one account-wide row
        # per day (asin='*') and one row per advertised ASIN per day. Summing
        # the table adds them together -- 256.93 of real spend reports as
        # 513.86, which on a page whose job is to explain a confusing number is
        # the worst possible thing to print. Readers ask for one grain or the
        # other and nothing ever adds them, so neither does this.
        everything = q(
            "SELECT marketplace, ad_product, "
            "CASE WHEN asin='*' THEN 'account total' ELSE 'per ASIN' END grain, "
            "COUNT(*) rows, COUNT(DISTINCT date) days, "
            "MIN(date) first_date, MAX(date) last_date, "
            "ROUND(SUM(spend),2) spend, ROUND(SUM(ad_sales),2) ad_sales, "
            "MAX(fetched_at) fetched_at "
            "FROM ads_daily WHERE workspace_id=? "
            "GROUP BY marketplace, ad_product, grain "
            "ORDER BY marketplace, ad_product, grain",
            wsid)
        # The account-wide rows are the ones the chart reads, so "is there any
        # data for this marketplace" is asked of those alone.
        acct_rows = [r for r in everything if r["grain"] == "account total"]

        # Exactly what the chart's series query returns, same filters.
        in_view = q(
            "SELECT COUNT(*) rows, ROUND(SUM(spend),2) spend, "
            "ROUND(SUM(ad_sales),2) ad_sales, "
            "SUM(CASE WHEN COALESCE(ad_sales,0) <> 0 THEN 1 ELSE 0 END) nonzero "
            "FROM ads_daily WHERE workspace_id=? AND marketplace=? "
            "AND date>=? AND date<=? AND asin='*'",
            wsid, mkt, start, end)[0]

        camps = q("SELECT COUNT(*) rows, COUNT(DISTINCT campaign_id) campaigns, "
                  "MIN(date) first_date, MAX(date) last_date "
                  "FROM ads_campaign_daily WHERE workspace_id=? AND marketplace=?",
                  wsid, mkt)[0]

        avail = q("SELECT * FROM data_availability WHERE workspace_id=? AND "
                  "marketplace=? AND source='ads'", wsid, mkt)
        jobs = q("SELECT kind, status, attempts, start_date, end_date, "
                 "requested_at, SUBSTR(COALESCE(error,''),1,200) error "
                 "FROM ads_report_jobs WHERE workspace_id=? "
                 "ORDER BY id DESC LIMIT 10", wsid)

        would_draw = (in_view.get("nonzero") or 0) > 0
        if would_draw:
            why = "The chart HAS data and should not be showing the placeholder."
        elif not everything:
            why = ("Nothing has ever been stored for this account. No report has "
                   "been collected yet — press Refresh PPC data, wait about ten "
                   "minutes, then press it again.")
        elif not any(r["marketplace"] == mkt for r in everything):
            why = ("Data exists, but not for %s. It is stored under: %s. The "
                   "chart only reads the marketplace on screen."
                   % (mkt, ", ".join(sorted({r["marketplace"] for r in everything}))))
        elif not any(r["marketplace"] == mkt for r in acct_rows):
            why = ("Per-ASIN rows exist for %s but there is no account-wide "
                   "('*') row, which is the only thing the chart reads. That "
                   "row is written by the CAMPAIGN report, so only the "
                   "advertised-product one has been collected. Press Refresh "
                   "PPC data again and give it ten minutes." % mkt)
        elif not in_view.get("rows"):
            got = [r for r in acct_rows if r["marketplace"] == mkt]
            why = ("Data exists for %s but none of it falls in %s..%s. Stored "
                   "range is %s..%s — change the date range on the Sales page "
                   "to cover it."
                   % (mkt, start, end,
                      min(r["first_date"] for r in got),
                      max(r["last_date"] for r in got)))
        else:
            why = ("Rows are in view but every ad_sales is zero, so there is "
                   "genuinely no advertising-attributed revenue to draw.")

        return jsonify({
            "ok": True, "workspace": wsid, "marketplace": mkt,
            "date_range_checked": [start, end],
            "chart_would_draw_real_data": would_draw,
            "why": why,
            "what_the_chart_sees": in_view,
            "everything_stored": everything,
            "campaign_table": camps,
            "availability": (avail[0] if avail else None),
            "recent_report_jobs": jobs,
        })
