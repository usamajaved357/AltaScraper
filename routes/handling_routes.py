"""routes/handling_routes.py — bulk handling-time (lead_time_to_ship_max_days) updates.

One endpoint: set a handling time on many listings at once. It can (a) record the value
in the handling column wherever that column exists, and (b) push it live to Amazon per
SKU via listing/handling.py.

EVERY SELECTED LISTING GOES IN ONE RUN. There used to be a test_one mode: the frontend
pushed the FIRST selected SKU on its own, showed Amazon's reply, and asked a second time
before sending the rest. It was removed on request ("Remove the test-then-apply pattern.
One confirmation only"), and the mode went with it because nothing called it any more.

It is worth saying why it was not a safety net. The "test" was a real push, so by the
time the second dialog appeared the change was already on Amazon; stopping there left
the catalogue half-changed, with the first selected SKU changed and the rest not. The
protection that actually holds is below and unchanged: each SKU is pushed and reported
separately, so one refusal never stops the others. Nothing here writes to Amazon unless
push=true is sent.

register(app, ...) injection pattern.
"""
from flask import request, jsonify

from routes import scope as _scope_mod


def register(app, *, _cfg, _active_account, _ws, _bust_records_cache, _state,
             CONFIG_PATH=None):
    from listing import handling as _handling

    def _load_account(aid):
        """The account record for an id the PAGE named -- credentials included."""
        try:
            import accounts as _acc_mod
            return _acc_mod.get_account(_cfg(), aid, CONFIG_PATH)
        except Exception:
            return None

    def _scope():
        """WHOSE listings these are, and in which country.

        THE PAGE SAYS, NOT THE SERVER'S GLOBAL.

        All three live pushes in this file used to read _active_account() and
        _state["active_marketplace"], which is one variable for the whole server
        process, written when an account is CHOSEN. The owner routinely has four
        browser tabs open (they are in the screenshot this was found from), so
        whichever tab last switched account owns that variable and every other
        tab pushes to it. SKUs are price_days_ASIN -- listing_routes already
        records that "two accounts sourcing the same product at the same price
        collide" -- so a collision is a stock or handling change landing on the
        wrong company's live listing.

        The price endpoints next door were already right: the browser names its
        account and routes/scope.resolve follows it. This is the same call, so
        there is one answer to the question in the app (CLAUDE.md Rule 12) rather
        than a second one here that disagrees.

        The marketplace default of "UK" went with it. That is the exact fault
        routes/scope.py was written to end -- "defaulting to UK gives a US
        account a confident answer about the wrong country" -- and here it aimed
        a WRITE: sheelady_us, a US account, would have had its handling time
        pushed to the United Kingdom. A marketplace that cannot be worked out is
        now refused, not guessed.
        """
        b = request.get_json(silent=True) or {}
        return _scope_mod.resolve(
            state=_state, account=_active_account() or {},
            asked_id=b.get("id") or b.get("account_id"),
            asked_marketplace=b.get("marketplace"),
            load_account=_load_account)

    def _push_target():
        """(account, marketplace, refusal-or-None) for a live push."""
        acc, _wsid, mkt = _scope()
        if not acc or not acc.get("id"):
            return None, "", (jsonify({"ok": False, "error": _scope_mod.NO_ACCOUNT}), 400)
        if not mkt:
            return None, "", (jsonify({"ok": False, "error": _scope_mod.NO_MARKETPLACE}), 400)
        return acc, mkt, None

    # Header names we accept for the sheet's handling-time column (standard layout).
    _HANDLING_COLS = ("Handling Days", "Handling Time", "Handling", "Lead Time", "Handling days")
    _SKU_COLS = ("SKU", "Sku", "sku")

    def _sheet_write_handling(skus_set, days):
        """Write `days` into the handling column for every matching SKU across ALL tabs of
        the active sheet (some accounts spread listings over many tabs; Miles tabs have no
        handling column at all, so those are simply skipped). Returns (updated_skus, tabs_touched,
        had_column)."""
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
            col_vals = _repo.column_values(ws, kcol)
            if not col_vals:
                continue
            data = []
            for idx, v in enumerate(col_vals, start=1):
                s = _repo.norm(v)
                if s and s in skus_set:
                    data.append({"range": _repo.a1(idx, hcol), "values": [[days]]})
                    updated.add(s)
            if data:
                try:
                    _repo.batch_write(ws, data)
                    tabs_touched.append(ws.title)
                except Exception:
                    pass
        return updated, tabs_touched, had_col

    @app.route("/stock/bulk_update", methods=["POST"])
    def stock_bulk_update():
        """Set the stock quantity on many live listings at once.

        Body: {skus:[...], qty:N}.

        NOTHING IS RECORDED HERE, deliberately. Handling time has a column of
        its own because it is a decision the owner makes and keeps; stock is a
        fact about the warehouse that Amazon is the authority on, and writing a
        number here would create a second, immediately-stale copy of it for
        every other screen to read. The Inventory screen already reads stock
        from Amazon.

        Every selected listing goes in one run, each reported separately. See
        the note at the top of this file for why the single-SKU test that used
        to precede it was not the safety net it appeared to be.
        """
        b = request.get_json(force=True) or {}
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        if not skus:
            return jsonify({"ok": False, "error": "no listings selected"}), 400
        # Validated up front -- a bad number must never reach Amazon.
        try:
            qty = int(b.get("qty"))
        except Exception:
            return jsonify({"ok": False, "error": (
                "Stock must be a whole number of units.")}), 400
        if qty < 0:
            return jsonify({"ok": False, "error": (
                "Stock cannot be negative. Set it to 0 to stop selling.")}), 400
        # A CEILING, because a typo here is not a small mistake: an extra digit
        # promises stock that does not exist and the orders arrive anyway.
        if qty > 100000:
            return jsonify({"ok": False, "error": (
                "That is over 100,000 units. If that is really right, set it on "
                "the listing itself — a bulk change that large is more likely a "
                "typed extra digit.")}), 400

        acc, mkt, refuse = _push_target()
        if refuse:
            return refuse

        pushed, failed = [], []
        for sku in skus:
            r = _handling.push_quantity(_cfg(), acc, sku, qty, mkt)
            (pushed if r.get("ok") else failed).append(r)
        return jsonify({"ok": len(failed) == 0, "qty": qty, "count": len(skus),
                        "pushed_ok": len(pushed), "pushed_fail": len(failed),
                        "push_results": pushed + failed})

    @app.route("/handling/bulk_update", methods=["POST"])
    def handling_bulk_update():
        """Body: {skus:[...], days:N, sheet:bool=true, push:bool=false}.
        - sheet: record the value in the handling column wherever it exists.
        - push : patch lead_time_to_ship_max_days on each live listing on Amazon."""
        b = request.get_json(force=True) or {}
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        do_sheet = bool(b.get("sheet", True))
        do_push  = bool(b.get("push", False))
        if not skus:
            return jsonify({"ok": False, "error": "no listings selected"}), 400
        # validate the handling value up front — a bad number must never be recorded or sent
        try:
            days = int(b.get("days"))
        except Exception:
            return jsonify({"ok": False, "error": "handling time must be a whole number of days"}), 400
        if days < 0 or days > 30:
            return jsonify({"ok": False, "error": "handling time must be between 0 and 30 days"}), 400

        out = {"ok": True, "days": days, "count": len(skus)}

        # --- 1) record it here ---
        if do_sheet:
            skus_set = set(skus)
            updated, tabs_touched, had_col = _sheet_write_handling(skus_set, days)
            if updated:
                _bust_records_cache()
            out["sheet_updated"] = sorted(updated)
            out["sheet_tabs"] = tabs_touched
            out["sheet_has_column"] = had_col
            out["sheet_note"] = ("" if had_col else
                                 "There is no handling-time column on these listings, so nothing "
                                 "was recorded here (the Amazon push still applies).")

        # --- 2) push to Amazon ---
        if do_push:
            acc, mkt, refuse = _push_target()
            if refuse:
                return refuse
            pushed, failed = [], []
            for sku in skus:
                r = _handling.push_handling_time(_cfg(), acc, sku, days, mkt)
                (pushed if r.get("ok") else failed).append(r)
            out["pushed_ok"] = len(pushed)
            out["pushed_fail"] = len(failed)
            out["push_results"] = pushed + failed
            out["ok"] = (len(failed) == 0)

        return jsonify(out)
