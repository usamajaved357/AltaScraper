"""routes/weekly_routes.py -- the weekly KPI pack.

    "i want to make a system where i upload the reports and i get this data, in
     a format like return intelligence. and also an option where i just need to
     connect an account like nestwell goods and all of this data is extracted
     without the need of reports"

TWO WAYS IN, ONE PACK OUT. Both end at domain/weekly_kpi.build(), so an
uploaded week and a pulled week are computed by the same arithmetic and cannot
disagree (CLAUDE.md Rule 12).

    /weekly/upload      one of the two reports, identified by its COLUMNS.
                        Upload both and the pack is complete; upload one and
                        the pack says which half is missing rather than showing
                        zeros for it.

    /weekly/pull        for a connected account. The Business Report half is
                        GET_SALES_AND_TRAFFIC_REPORT at CHILD granularity,
                        which domain/sales_fetch.py already knows how to ask
                        for. The campaign half needs the Advertising API, and
                        when that is not connected this says so instead of
                        returning an empty advertising section that looks like
                        a week with no ads in it.

    /weekly/list        the frozen weeks, newest first.

A WEEK IS FROZEN, NOT RECOMPUTED. See the weekly_kpi table in data/db.py for
why -- the sheet this replaces had its history computed by a different formula
from its present, and nothing on the screen said so.
"""
import datetime as _dt

from flask import jsonify, request

from domain import report_reader as _rr
from domain import weekly_kpi as _wk


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /weekly/* to the app."""

    def _scope():
        aid = (request.args.get("id") or request.args.get("account_id")
               or (request.form.get("id") if request.form else "") or "").strip()
        mkt = (request.args.get("marketplace")
               or (request.form.get("marketplace") if request.form else "")
               or "").strip().upper()
        if not aid or not mkt:
            acc = {}
            try:
                acc = (_active_account() or {}) if callable(_active_account) else {}
            except Exception:
                acc = {}
            aid = aid or str(acc.get("id")
                             or (_state or {}).get("active_account_id") or "")
            mkt = mkt or str(acc.get("default_marketplace")
                             or (_state or {}).get("active_marketplace")
                             or "").upper()
        return aid, mkt

    def _brand_terms(wsid):
        """The seller's own words, from the list the PPC screen already uses."""
        try:
            from data import db as _db
            rows = _db.get_db(CONFIG_PATH).execute(
                "SELECT term FROM ppc_brand_terms WHERE workspace_id=?",
                (wsid,)).fetchall()
            return [r["term"] for r in rows]
        except Exception:
            return []

    # The half-built pack, per account+marketplace, while both reports are being
    # uploaded. In memory on purpose: it is the two minutes between dropping the
    # first file and the second, and a restart in that window costs one re-drop.
    _PENDING = {}

    @app.route("/weekly/upload", methods=["POST"])
    def weekly_upload():
        """One of the two reports. Which one is decided by its columns."""
        wsid, mkt = _scope()
        if not wsid:
            return jsonify({"ok": False, "error": "Open an account first."}), 400
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "No file came through."}), 400

        table = _rr.read(f.read(), f.filename or "")
        if table.get("error"):
            return jsonify({"ok": False, "error": table["error"]}), 400
        family = _wk.detect(table.get("headers"))
        if not family:
            # Say what WAS in the file. "Not the right report" with no detail
            # sends someone back to Seller Central for a file they already have.
            return jsonify({"ok": False, "error": (
                "That does not look like either report. This page needs the "
                "Business Report (Detail Page Sales and Traffic by Child Item) "
                "or the Campaign Manager export. The file has these columns: "
                + ", ".join(str(h) for h in (table.get("headers") or [])[:12]))
            }), 400

        key = "%s::%s" % (wsid, mkt)
        slot = _PENDING.setdefault(key, {"business": None, "campaign": None})
        slot["business" if family == _wk.BUSINESS else "campaign"] = table

        # WHICH WEEK. Amazon's reports do not carry the window inside the file
        # in a form worth trusting, so it is asked for -- and defaults to the
        # week just gone, which is the one being reported on a Monday.
        ws = (request.form.get("week_start") or "").strip()
        if ws:
            try:
                start = _dt.date.fromisoformat(ws)
            except ValueError:
                start = _dt.date.today() - _dt.timedelta(days=7)
        else:
            start = _dt.date.today() - _dt.timedelta(days=7)
        week_start, week_end = _wk.week_bounds(start)

        pack = _wk.build(slot["business"], slot["campaign"],
                         brand_terms=_brand_terms(wsid),
                         week_start=week_start, week_end=week_end)
        # Stored as soon as either half arrives, so a half pack survives a
        # reload and the second file can be added to it later.
        _wk.store(CONFIG_PATH, wsid, mkt, pack, source="upload")
        return jsonify({"ok": True, "family": family,
                        "format": table.get("format"),
                        "rows_read": len(table.get("rows") or []), **pack})

    @app.route("/weekly/list")
    def weekly_list():
        """The frozen weeks, newest first, with movement against the one before."""
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400
        got = _wk.weeks(CONFIG_PATH, wsid, mkt)
        change = _wk.compare(got[0], got[1]) if len(got) >= 2 else {}
        return jsonify({"ok": True, "weeks": got, "change": change,
                        "brand_terms": _brand_terms(wsid),
                        "marketplace": mkt, "account": wsid})

    @app.route("/weekly/pull", methods=["POST"])
    def weekly_pull():
        """Build the week from a CONNECTED account, with no files at all.

        The Business Report half comes from SP-API. The advertising half needs
        the Advertising API, and if that is not connected this returns the half
        it has and NAMES what is missing -- an advertising section full of zeros
        would read as a week with no ads running.
        """
        from api import amazon_ads as _ads

        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400

        b = (request.get_json(silent=True) or {})
        ws = str(b.get("week_start") or "").strip()
        try:
            start = _dt.date.fromisoformat(ws) if ws else (
                _dt.date.today() - _dt.timedelta(days=7))
        except ValueError:
            start = _dt.date.today() - _dt.timedelta(days=7)
        week_start, week_end = _wk.week_bounds(start)

        notes = []

        # ---- the store half -------------------------------------------------
        biz_table = None
        try:
            biz_table = _sales_traffic_table(wsid, mkt, week_start, week_end)
            if biz_table is None:
                notes.append(
                    "No Sales & Traffic data is stored for %s to %s. The app "
                    "syncs it from Amazon in the background — open the Sales "
                    "screen to fill the gap, or upload the Business Report."
                    % (week_start, week_end))
        except Exception as e:
            notes.append("Could not read the stored Sales & Traffic data: %s"
                         % str(e)[:200])

        # ---- the advertising half -------------------------------------------
        acc = {}
        try:
            cfg = _cfg() if callable(_cfg) else (_cfg or {})
            acc = next((a for a in (cfg.get("accounts") or [])
                        if str(a.get("id")) == wsid), {})
        except Exception:
            acc = {}
        state = _ads.test(_cfg, acc, mkt)
        camp_table = None
        if not state.get("connected"):
            notes.append(
                "The advertising half needs the Amazon Advertising API, which "
                "is a separate login from SP-API and is not connected: "
                + str(state.get("error") or "") +
                " Until it is, upload the Campaign Manager export instead — "
                "the pack is identical either way.")

        pack = _wk.build(biz_table, camp_table,
                         brand_terms=_brand_terms(wsid),
                         week_start=week_start, week_end=week_end)
        pack["notes"] = notes
        if pack.get("has_business") or pack.get("has_campaigns"):
            _wk.store(CONFIG_PATH, wsid, mkt, pack, source="api")
        return jsonify({"ok": True, **pack})

    def _sales_traffic_table(wsid, mkt, week_start, week_end):
        """One week of Sales & Traffic, per child ASIN, shaped like an upload.

        NO NEW AMAZON CALL. sales_daily already holds this, per day and per
        child ASIN, because domain/sales_fetch.py syncs GET_SALES_AND_TRAFFIC_
        REPORT with asinGranularity CHILD in the background. Asking Amazon
        again for something already on disk spends quota to learn nothing.

        Returned in the SAME {headers, rows} shape a file upload produces, so
        domain/weekly_kpi.py has one parser rather than two and a pulled week
        cannot come out different from an uploaded one (Rule 12).
        """
        from data import db as _db

        conn = _db.get_db(CONFIG_PATH)
        try:
            rows = conn.execute(
                "SELECT asin, MAX(parent_asin) AS parent_asin, "
                "       SUM(COALESCE(sessions,0))      AS sessions, "
                "       SUM(COALESCE(page_views,0))    AS page_views, "
                "       SUM(COALESCE(units,0))         AS units, "
                "       SUM(COALESCE(ordered_sales,0)) AS sales, "
                "       SUM(COALESCE(order_items,0))   AS order_items "
                "FROM sales_daily "
                "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
                # asin '*' IS THE ACCOUNT TOTAL FOR THE DAY, not a product --
                # data/db.py says so where the column is defined. Left in, it is
                # summed alongside the real child ASINs and every headline
                # figure comes out roughly DOUBLE.
                #
                # MEASURED on jack_uk, week of 10 Aug: one ASIN sold 3 units and
                # the '*' row carried the same 3, so the pack reported 6 units
                # and 540 sessions against a true 3 and 284. Nine other
                # per-product queries in this app filter it (contribution.py,
                # sales_data.py, traffic_view.py, returns_routes.py, ...);
                # this one did not.
                "  AND asin IS NOT NULL AND asin<>'' AND asin<>'*' "
                "GROUP BY asin ORDER BY units DESC",
                (wsid, mkt, week_start, week_end)).fetchall()
        except Exception:
            return None
        if not rows:
            return None

        # The product's NAME. sales_daily is figures only, and a table of ASINs
        # is unreadable. Through domain/catalogue, which is the one shared
        # product-name lookup in this app.
        names = {}
        try:
            from domain import catalogue as _cat
            idx = _cat.index(CONFIG_PATH, wsid, mkt, include_drafts=True) or {}
            for k, v in idx.items():
                if isinstance(v, dict) and v.get("title"):
                    names[str(k).upper()] = v["title"]
        except Exception:
            names = {}

        headers = ["(Parent) ASIN", "(Child) ASIN", "Title", "Sessions - Total",
                   "Page Views - Total", "Units Ordered",
                   "Ordered Product Sales", "Total Order Items"]
        out = []
        for r in rows:
            asin = str(r["asin"] or "")
            out.append([r["parent_asin"] or "", asin,
                        names.get(asin.upper(), ""),
                        r["sessions"], r["page_views"], r["units"],
                        r["sales"], r["order_items"]])
        return {"headers": headers, "rows": out, "format": "api", "error": ""}
