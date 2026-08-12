"""routes/handling_routes.py — bulk handling-time (lead_time_to_ship_max_days) updates.

One endpoint: set a handling time on many listings at once. It can (a) write the value
into the sheet's handling column wherever that column exists (across every tab of the
active sheet), and (b) push it live to Amazon per SKU via listing/handling.py.

The frontend does the first live push as a single-SKU TEST (test_one), shows Amazon's
reply, and only then pushes the rest — honouring the "test one listing before a bulk
live write" rule. Nothing here writes to Amazon unless push=true is sent.

register(app, ...) injection pattern.
"""
from flask import request, jsonify


def register(app, *, _cfg, _active_account, _ws, _bust_records_cache, _state):
    from listing import handling as _handling

    # Header names we accept for the sheet's handling-time column (standard layout).
    _HANDLING_COLS = ("Handling Days", "Handling Time", "Handling", "Lead Time", "Handling days")
    _SKU_COLS = ("SKU", "Sku", "sku")

    def _sheet_write_handling(skus_set, days):
        """Write `days` into the handling column for every matching SKU across ALL tabs of
        the active sheet (some accounts spread listings over many tabs; Miles tabs have no
        handling column at all, so those are simply skipped). Returns (updated_skus, tabs_touched,
        had_column)."""
        from gspread.utils import rowcol_to_a1
        updated, tabs_touched, had_col = set(), [], False
        try:
            book = _ws().spreadsheet
            worksheets = book.worksheets()
        except Exception:
            return updated, tabs_touched, had_col
        # This one matches a SET of SKUs in a single pass per tab, so it does NOT
        # use repo.locate() -- that answers "where is ONE sku?" and calling it per
        # SKU would turn one column read into N, against a quota'd API. What it
        # shares with the rest of the app is the part that was actually diverging:
        # how a header row is read (read_headers), how a column is found from
        # several acceptable names (find_col), and how a SKU is compared (norm).
        from listing import repo as _repo
        for ws in worksheets:
            headers = _repo.read_headers(ws)
            if not headers:
                continue
            hcol = _repo.find_col(headers, _HANDLING_COLS)
            kcol = _repo.find_col(headers, _SKU_COLS)
            if not hcol or not kcol:
                continue                                  # tab has no handling column -> skip
            had_col = True
            try:
                col_vals = ws.col_values(kcol)
            except Exception:
                continue
            data = []
            for idx, v in enumerate(col_vals, start=1):
                s = _repo.norm(v)
                if s and s in skus_set:
                    data.append({"range": rowcol_to_a1(idx, hcol), "values": [[days]]})
                    updated.add(s)
            if data:
                try:
                    ws.batch_update(data)
                    tabs_touched.append(ws.title)
                except Exception:
                    pass
        return updated, tabs_touched, had_col

    @app.route("/handling/bulk_update", methods=["POST"])
    def handling_bulk_update():
        """Body: {skus:[...], days:N, sheet:bool=true, push:bool=false, test_one:bool=false}.
        - sheet: write the value into the handling column wherever it exists.
        - push : patch lead_time_to_ship_max_days on each live listing on Amazon.
        - test_one: push ONLY the first SKU (the single-listing safety test), no sheet write."""
        b = request.get_json(force=True) or {}
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        do_sheet = bool(b.get("sheet", True))
        do_push  = bool(b.get("push", False))
        test_one = bool(b.get("test_one", False))
        if not skus:
            return jsonify({"ok": False, "error": "no listings selected"}), 400
        # validate the handling value up front — a bad number must never reach the sheet or Amazon
        try:
            days = int(b.get("days"))
        except Exception:
            return jsonify({"ok": False, "error": "handling time must be a whole number of days"}), 400
        if days < 0 or days > 30:
            return jsonify({"ok": False, "error": "handling time must be between 0 and 30 days"}), 400

        # --- single-listing safety test: push ONE SKU, return Amazon's reply, no sheet write ---
        if test_one:
            if not do_push:
                return jsonify({"ok": False, "error": "test_one requires push"}), 400
            acc = _active_account()
            if not acc:
                return jsonify({"ok": False, "error": "no active account for the live push"}), 400
            mkt = (_state.get("active_marketplace") or acc.get("default_marketplace") or "UK")
            res = _handling.push_handling_time(_cfg(), acc, skus[0], days, mkt)
            return jsonify({"ok": bool(res.get("ok")), "test": True, "days": days, "result": res})

        out = {"ok": True, "days": days, "count": len(skus)}

        # --- 1) sheet ---
        if do_sheet:
            skus_set = set(skus)
            updated, tabs_touched, had_col = _sheet_write_handling(skus_set, days)
            if updated:
                _bust_records_cache()
            out["sheet_updated"] = sorted(updated)
            out["sheet_tabs"] = tabs_touched
            out["sheet_has_column"] = had_col
            out["sheet_note"] = ("" if had_col else
                                 "No handling-time column exists on these tabs, so nothing was "
                                 "written to the sheet (the Amazon push still applies).")

        # --- 2) push to Amazon ---
        if do_push:
            acc = _active_account()
            if not acc:
                return jsonify({"ok": False, "error": "no active account for the live push"}), 400
            mkt = (_state.get("active_marketplace") or acc.get("default_marketplace") or "UK")
            pushed, failed = [], []
            for sku in skus:
                r = _handling.push_handling_time(_cfg(), acc, sku, days, mkt)
                (pushed if r.get("ok") else failed).append(r)
            out["pushed_ok"] = len(pushed)
            out["pushed_fail"] = len(failed)
            out["push_results"] = pushed + failed
            out["ok"] = (len(failed) == 0)

        return jsonify(out)
