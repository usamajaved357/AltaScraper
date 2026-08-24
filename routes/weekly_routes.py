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

    @app.route("/weekly/count")
    def weekly_count():
        """How many weeks are stored for this account and marketplace.

        Read-only. It exists so the confirmation can name a real figure before
        anything is deleted -- the browser knows only the weeks it has drawn,
        and the list is capped, so counting those would understate what is
        about to go.
        """
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400
        return jsonify({"ok": True, "account": wsid, "marketplace": mkt,
                        "count": _wk.count_weeks(CONFIG_PATH, wsid, mkt)})

    @app.route("/weekly/clear", methods=["POST"])
    def weekly_clear():
        """Delete the frozen weeks for this account and marketplace.

            "give me an option to delete or clear all data which is already
             UPLOADED IN THE weekly kpi's page, i want to upload my new data
             when the old one is deleted to avoid any confusion"

        `week_start` in the body deletes exactly that one week instead of all of
        them, which is the ordinary case of replacing a single bad upload.

        SCOPED BY THE STORE, not here. Every workspace's weeks share one table
        and this page shows one account at a time, so domain/weekly_kpi.clear
        refuses a blank account or marketplace outright -- deleting none is the
        safe direction and it is enforced in one place rather than trusted to
        each caller.

        THE COUNT AGREED TO TRAVELS WITH THE REQUEST. If it has moved since the
        dialog opened -- another tab, an upload finishing -- deleting a
        different number from the one shown is exactly the thing not to do.
        """
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400
        b = request.get_json(silent=True) or {}
        week = str(b.get("week_start") or "").strip()
        have = _wk.count_weeks(CONFIG_PATH, wsid, mkt)
        expected = b.get("expect", None)
        if not week and expected is not None and int(expected) != have:
            return jsonify({"ok": False, "changed": True, "count": have,
                            "error": ("This account now has %d stored week%s, not "
                                      "the %s the warning said. Nothing was "
                                      "deleted -- close this and try again so you "
                                      "are agreeing to the right number."
                                      % (have, "" if have == 1 else "s",
                                         expected))}), 409
        gone = _wk.clear(CONFIG_PATH, wsid, mkt, week_start=week or None)
        return jsonify({"ok": True, "deleted": gone, "account": wsid,
                        "marketplace": mkt,
                        "note": ("Week %s deleted." % week) if week else
                                ("%d stored week%s deleted for %s %s. Upload the "
                                 "new reports when you are ready."
                                 % (gone, "" if gone == 1 else "s", wsid, mkt))})

    # ---- the KPI sheet's own layout ----------------------------------------
    #
    # Every saved week as a COLUMN, metrics down the side, newest first -- the
    # shape of the Google Sheet this replaces. The layout itself lives in
    # domain/weekly_grid.py so the CSV and the Sheets sync are the same grid and
    # cannot drift apart (rule 12).

    def _col_letter(n):
        """1 -> A, 27 -> AA. Needed for the format ranges, and gspread's own
        helper is not importable from here without dragging the client in."""
        s = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return s or "A"

    def _grid(wsid, mkt, group):
        from domain import weekly_grid as _wg
        got = _wk.weeks(CONFIG_PATH, wsid, mkt)
        label = ""
        try:
            acc = (_active_account() or {}) if callable(_active_account) else {}
            label = str(acc.get("label") or wsid)
        except Exception:
            label = wsid
        return got, _wg.build(got, group=group, account_label=label)

    @app.route("/weekly/grid")
    def weekly_grid_preview():
        """The grid as JSON, so the screen can show what will be exported."""
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400
        group = "child" if request.args.get("group") == "child" else "parent"
        got, g = _grid(wsid, mkt, group)
        if not got:
            return jsonify({"ok": False, "error": (
                "No weeks have been saved for this account yet. Upload a week "
                "or press Pull, and it becomes a column here.")}), 400
        return jsonify({"ok": True, **g})

    @app.route("/weekly/export.csv")
    def weekly_export_csv():
        """Every saved week, in the sheet's layout, as a CSV."""
        from flask import Response
        from domain import weekly_grid as _wg
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400
        group = "child" if request.args.get("group") == "child" else "parent"
        got, g = _grid(wsid, mkt, group)
        if not got:
            return jsonify({"ok": False, "error": (
                "There are no saved weeks to export. Upload a week or press "
                "Pull first.")}), 400
        name = "weekly-kpis-%s-%s-%s.csv" % (wsid, mkt,
                                             (got[0].get("week_start") or "")[:10])
        return Response(
            # The byte-order mark makes Excel read this as UTF-8 rather than
            # mangling every pound sign. Written as the ESCAPE, never as the
            # character: a literal BOM sitting in source is invisible and gets
            # copied into the middle of files by the next edit. static/js has a
            # test for exactly this, and it has caught it before.
            "\ufeff" + _wg.to_csv(g),
            # "text/csv" alone: Flask appends the charset itself, and giving it
            # one produced "text/csv; charset=utf-8; charset=utf-8".
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="%s"' % name,
                     "Cache-Control": "no-store"})

    def _sheet_target(wsid):
        """Which Google Sheet and tab this account's weekly pack belongs in.

        ITS OWN SETTING, not the listing generator's output sheet. That one is
        where generated listings are written and it has a listings tab with its
        own header row -- writing a KPI grid over it would destroy real work.
        Falls back to nothing rather than to that sheet: refusing is the correct
        answer when nobody has said where to write.
        """
        try:
            from domain import accounts as _acc
            acc = _acc.get_account(_cfg() if callable(_cfg) else (_cfg or {}),
                                   wsid, CONFIG_PATH) or {}
        except Exception:
            acc = {}
        url = str(acc.get("weekly_sheet_url") or "").strip()
        tab = str(acc.get("weekly_sheet_tab") or "").strip() or "Weekly KPIs"
        sid = ""
        if url:
            import re as _re
            m = _re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url)
            sid = m.group(1) if m else ""
        return sid, tab, url

    @app.route("/weekly/sheet", methods=["POST"])
    def weekly_sheet():
        """Write the grid to this account's weekly Google Sheet.

        A DRY RUN UNLESS TOLD OTHERWISE. `{"confirm": true}` is what actually
        writes; without it this reports exactly what it WOULD do -- which sheet,
        which tab, how many rows and columns, and whether the tab already
        exists. Writing to somebody's live sheet is not undoable from in here,
        and a button that does it on the first click is a button that eventually
        does it by accident.

        THE TAB IS THE APP'S OWN. It writes a whole tab, cleared and rewritten,
        rather than trying to patch week columns into a hand-maintained sheet:
        that sheet has formulas, merged headers and a column C that is already a
        duplicate of column G, and a script that edits it in place would have to
        understand all of that to avoid destroying it. A separate tab in the
        same workbook gives the same numbers in the same place with nothing at
        risk, and it can be referenced from the hand-made tab by formula.
        """
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400
        b = request.get_json(silent=True) or {}
        group = "child" if b.get("group") == "child" else "parent"
        sid, tab, url = _sheet_target(wsid)
        if not sid:
            return jsonify({"ok": False, "error": (
                "This account has no weekly KPI sheet set. Put the Google "
                "Sheet URL in Account settings (Weekly KPI sheet) first — it is "
                "deliberately separate from the listing output sheet, so a KPI "
                "grid can never be written over your listings.")}), 400
        got, g = _grid(wsid, mkt, group)
        if not got:
            return jsonify({"ok": False, "error": (
                "There are no saved weeks to write.")}), 400

        plan = {"ok": True, "spreadsheet_id": sid, "tab": tab, "url": url,
                "rows": len(g["rows"]), "columns": g["meta"]["columns"],
                "weeks": g["meta"]["weeks"], "products": g["meta"]["products"],
                "group": group, "br_means": g["meta"]["br_means"]}
        if not b.get("confirm"):
            plan["dry_run"] = True
            plan["note"] = ("Nothing has been written. This would replace the "
                            "contents of the '%s' tab with %d rows by %d "
                            "columns — %d weeks, newest on the left. Press it "
                            "again to confirm." % (tab, len(g["rows"]),
                                                   g["meta"]["columns"],
                                                   g["meta"]["weeks"]))
            return jsonify(plan)

        try:
            import dashboard as _dash
            from domain import weekly_grid as _wg
            from listing import repo as _repo
            gc = _dash._client()
            book = gc.open_by_key(sid)
            # ensure_tab returns (worksheet, created) -- unpacked, because
            # calling .clear() on the tuple is a TypeError at the one moment
            # this code runs.
            ws, _created = _repo.ensure_tab(
                book, tab, rows=max(200, len(g["rows"]) + 40),
                cols=max(30, g["meta"]["columns"] + 6))
            ws.clear()
            # USER_ENTERED so Sheets reads the numbers as numbers rather than as
            # text -- a column of strings cannot be charted or summed, which is
            # the whole reason for exporting into a sheet at all.
            _repo.write_range(ws, _wg.sheet_rows(g), "A1",
                              value_input_option="USER_ENTERED")
            # Money, counts and ratios get their pattern; percentages already
            # arrived as percentages. Contiguous runs, so this is a handful of
            # calls rather than one per row.
            cur = ""
            for w in got:
                cur = str(w.get("currency") or "") or cur
            last_col = _col_letter(g["meta"]["columns"])
            for a, b2, pat in _wg.sheet_number_formats(g, cur):
                try:
                    ws.format("C%d:%s%d" % (a, last_col, b2),
                              {"numberFormat": {"type": "NUMBER",
                                                "pattern": pat}})
                except Exception:
                    pass      # formatting is presentation; the values are in
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not write the sheet: %s"
                                     % str(e)[:240]}), 502
        plan["dry_run"] = False
        plan["note"] = ("Written to the '%s' tab: %d weeks, newest on the left."
                        % (tab, g["meta"]["weeks"]))
        return jsonify(plan)

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
