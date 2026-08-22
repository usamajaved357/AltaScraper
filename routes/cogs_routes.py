"""routes/cogs_routes.py — COGS (cost-of-goods) endpoints, extracted from dashboard.py (Phase 3).

Same register(app, ...) injection pattern. _COGS_OVERRIDE (a shared mutable dict),
_save_cogs_overrides and _estimate_profit are used across the app, so they are
injected (the same objects), and the route bodies move VERBATIM (CLAUDE.md §10).

Routes:
  GET  /cogs/template.csv -> the cost sheet, listing this account's SKUs
  POST /cogs/set          -> set/override COGS for one SKU
  POST /cogs/upload       -> bulk COGS upload {rows:[{sku,cost}]}
"""
from flask import request, jsonify, Response


def register(app, *, _state, _COGS_OVERRIDE, _save_cogs_overrides, _estimate_profit,
             CONFIG_PATH=None, _active_account=None):
    """Attach the /cogs/* routes to the existing Flask app."""

    @app.route("/cogs/template.csv")
    def cogs_template():
        """The cost sheet to fill in, listing every SKU on the account.

        There was an upload and no template, so the columns had to be guessed and
        every SKU typed by hand -- and a hand-typed SKU is one that silently
        matches nothing. The upload's own error for that is "No matchable rows",
        which is the app telling you it cannot read what it asked you to write.

        The `cost` column arrives EMPTY on purpose, even where a cost is known.
        See domain/cogs.template_rows: a cost is a manual override, and
        pre-filling it would turn every SKU-derived cost into a typed-in one on
        a single upload of a file nobody edited. What the app uses now is in
        `cost now`, to read.
        """
        from domain import cogs as _cogs
        from domain import catalogue as _cat
        from domain import sheets as _sheets
        acc = (_active_account() or {}) if callable(_active_account) else {}
        aid = str(acc.get("id") or _state.get("active_account_id", "") or "")
        mkt = str(acc.get("default_marketplace")
                  or _state.get("active_marketplace") or "").upper()
        rows = _cogs.template_rows(CONFIG_PATH, aid, mkt,
                                   overrides=_COGS_OVERRIDE,
                                   catalogue=_cat.index(CONFIG_PATH, aid, mkt))
        body = _sheets.to_csv(_cogs.TEMPLATE_HEADERS, rows)
        name = "costs-%s-%s.csv" % (aid or "account", mkt or "")
        return Response(body, # Flask appends the charset itself; naming it here too produced
                        # "text/csv; charset=utf-8; charset=utf-8", which a strict parser
                        # is entitled to reject.
                        mimetype="text/csv",
                        headers={"Content-Disposition":
                                 'attachment; filename="%s"' % name})

    @app.route("/cogs/upload_sheet", methods=["POST"])
    def cogs_upload_sheet():
        """A cost sheet, parsed HERE rather than in the browser.

        The browser version split each line on commas, which is not what a CSV
        is: a product name like "Grill, Large" is quoted and contains one, so
        every column after it shifted and the cost was read from the wrong
        place. The sheet this app hands out is full of such names, so that was
        about to become the normal case. It also could not read a spreadsheet at
        all; this can.

        dry_run READS THE FILE AND WRITES NOTHING, so the confirmation can name
        real numbers -- how many costs this file would set, how many rows have
        no cost, how many match nothing on the account -- instead of the
        browser's own guess at them. A bulk overwrite of what things cost moves
        every profit figure in the app, and "Set the cost on 412 SKUs?" is only
        worth asking if the 412 came from the same reader that will do the work.
        """
        from domain import cogs as _cogs
        from domain import source_bulk as _sb
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "no file"}), 400
        acc = (_active_account() or {}) if callable(_active_account) else {}
        aid = str(request.form.get("id") or acc.get("id")
                  or _state.get("active_account_id", "") or "")
        mkt = str(acc.get("default_marketplace")
                  or _state.get("active_marketplace") or "").upper()
        headers, rows, err = _sb.read_table(f.read(), f.filename or "")
        if err:
            return jsonify({"ok": False, "error": err}), 400
        rep = _cogs.apply_sheet(CONFIG_PATH, aid, mkt, headers, rows)
        if not rep.get("ok"):
            return jsonify(rep), 400
        dry = str(request.form.get("dry_run") or "").lower() in ("1", "true", "yes")
        if dry:
            rep.pop("updates", None)
            rep["dry_run"] = True
            rep["note"] = ("%d cost%s would be set. %d row%s have no cost filled "
                           "in and would be left alone."
                           % (rep["set"], "" if rep["set"] == 1 else "s",
                              rep["skipped"], "" if rep["skipped"] == 1 else "s"))
            return jsonify(rep)
        # Written only after the whole file has been read without complaint, so
        # a sheet that fails halfway does not leave half the catalogue changed.
        # Through the store, same as /cogs/set -- one way in, so a cost set by
        # sheet and a cost typed on a row cannot end up in different dicts.
        from domain import cogs_store as _cs
        for sku, cost in (rep.pop("updates", None) or {}).items():
            _cs.set_cost(CONFIG_PATH, aid, sku, cost)
        rep["note"] = ("%d cost%s set. %d row%s had no cost filled in and were "
                       "left alone." % (rep["set"], "" if rep["set"] == 1 else "s",
                                        rep["skipped"],
                                        "" if rep["skipped"] == 1 else "s"))
        return jsonify(rep)

    @app.route("/cogs/set", methods=["POST"])
    def cogs_set():
        """Manually set/override COGS for a SKU in the active account."""
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        sku = (b.get("sku", "") or "").strip()
        cost = b.get("cost", None)
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        # THROUGH THE STORE, which owns the dict and the file together. Writing
        # the dict here and saving separately is how the two came apart before:
        # see domain/cogs_store.py for the module-identity bug that made a typed
        # cost invisible to the Sales and Orders screens.
        from domain import cogs_store as _cs
        stored, ok = _cs.set_cost(CONFIG_PATH, aid, sku, cost)
        if not ok and cost not in (None, "", "null"):
            return jsonify({"ok": False, "error": (
                "cost must be a number, and not a negative one")}), 400
        # return the recomputed profit for immediate UI update
        prof = (_estimate_profit(b.get("price", ""), stored)
                if stored is not None else None)
        return jsonify({"ok": True, "profit": prof, "cost": stored,
                        "cogs_source": ("manual" if stored is not None else "")})

    @app.route("/cogs/count")
    def cogs_count():
        """How many costs this account has stored. Reads only; changes nothing.

        Exists so the confirmation can name a real figure before anything is
        deleted. The browser could count the costs it happens to have drawn, but
        that is only the rows currently on screen -- a filtered view, or a second
        page of listings, and it would understate what is about to go.
        """
        from domain import cogs_store as _cs
        from domain import cogs as _cogs
        aid = str(request.args.get("id") or _state.get("active_account_id") or "")
        if not aid:
            return jsonify({"ok": False, "error": "no account is open"}), 400
        out = {"ok": True, "id": aid, "count": _cs.count_for(CONFIG_PATH, aid)}
        # WHERE THIS ACCOUNT'S COSTS ACTUALLY COME FROM, so the explainer can
        # show figures rather than only describing rules. A page that says "a
        # typed cost beats one read from the SKU" is a rule; the same page saying
        # "47 read from the SKU, 3 you typed, 12 not known" is something you can
        # check against what you believe.
        try:
            acc = (_active_account() or {}) if callable(_active_account) else {}
            mkt = str(request.args.get("marketplace")
                      or acc.get("default_marketplace")
                      or _state.get("active_marketplace") or "").upper()
            cov = _cogs.coverage(CONFIG_PATH, aid, mkt,
                                 _cs.all_overrides(CONFIG_PATH))
            manual = out["count"]
            out["breakdown"] = {
                "marketplace": mkt,
                "known": cov.get("known", 0),
                "unknown": cov.get("unknown", 0),
                "total": cov.get("total", 0),
                "manual": manual,
                # Everything with a cost that is not a manual override was read
                # out of the SKU's own name. Never negative: an override can sit
                # on a SKU the snapshot has not got, so manual can exceed known.
                "from_sku": max(0, cov.get("known", 0) - manual),
            }
        except Exception:
            pass                    # the count is the answer; the extra is a bonus
        return jsonify(out)

    @app.route("/cogs/clear", methods=["POST"])
    def cogs_clear():
        """Delete every manually-set cost for the account that is open.

        WHAT THIS DOES NOT TOUCH, because the difference decides whether this is
        recoverable: a cost carried in a SKU's own name (8.00_3Days_B0G1K5B7QS)
        is not stored here and is not affected -- those rows simply go back to
        reading their cost off the SKU. What goes is every figure TYPED on the
        listings screen or brought in from a cost sheet, and there is no undo:
        cogs_overrides.json is rewritten without them.

        Scoped to one account by the store (see cogs_store.clear_account). The
        keys of every workspace share one file, so this must never become a
        clear().

        THE COUNT IS RETURNED, not assumed. The browser asks /cogs/count first
        to word the warning; this answers with what actually went, so a
        disagreement between the two is visible rather than silent.
        """
        from domain import cogs_store as _cs
        b = request.get_json(force=True) or {}
        aid = str(b.get("id") or _state.get("active_account_id") or "")
        if not aid:
            return jsonify({"ok": False, "error": "no account is open"}), 400
        # The browser sends back the number it warned about. If the two disagree
        # the data changed under the dialog -- another tab, or a sheet upload
        # that finished while it was open -- and deleting a different amount from
        # the one that was agreed to is exactly the thing not to do.
        expected = b.get("expect", None)
        have = _cs.count_for(CONFIG_PATH, aid)
        if expected is not None and int(expected) != have:
            return jsonify({"ok": False, "changed": True, "count": have,
                            "error": ("This account now has %d saved cost%s, not "
                                      "the %s the warning said. Nothing was "
                                      "deleted -- close this and try again so "
                                      "you are agreeing to the right number."
                                      % (have, "" if have == 1 else "s",
                                         expected))}), 409
        gone = _cs.clear_account(CONFIG_PATH, aid)
        return jsonify({"ok": True, "deleted": gone,
                        "note": ("%d saved cost%s deleted. Listings whose SKU "
                                 "carries a price still show that price."
                                 % (gone, "" if gone == 1 else "s"))})

    @app.route("/cogs/upload", methods=["POST"])
    def cogs_upload():
        """Bulk COGS upload: accepts {rows:[{sku,cost}]}, already parsed.

        THE SCREEN NO LONGER USES THIS -- it posts the file itself to
        /cogs/upload_sheet, where the one reader lives. This stays for anything
        that already sends rows, and it now writes THE SAME WAY as every other
        cost in the app.

        It used to put the value straight into _COGS_OVERRIDE and save the file
        separately. That is the exact shape of the bug domain/cogs_store.py was
        written to end -- see the note over /cogs/set: two modules each holding
        their own dict, and a typed cost that the Sales and Orders screens could
        not see. It also disagreed about what a cost IS: float("-3") is a fine
        float, so a negative cost went in here and was refused everywhere else.
        One way in (Rule 12), and the refusals are the store's.

        Rows that were refused are RETURNED rather than silently dropped, so a
        file of 400 costs that stored 380 does not report success.
        """
        from domain import cogs_store as _cs
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        rows = b.get("rows", []) or []
        n = 0
        refused = []
        for r in rows:
            sku = (r.get("sku", "") or "").strip()
            cost = r.get("cost", None)
            if not sku or cost in (None, ""):
                continue
            stored, ok = _cs.set_cost(CONFIG_PATH, aid, sku, cost)
            if ok and stored is not None:
                n += 1
            else:
                refused.append(sku)
        return jsonify({"ok": True, "count": n, "set": n,
                        "refused": refused[:50],
                        "refused_count": len(refused)})
