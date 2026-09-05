"""routes/cogs_mode_routes.py -- which way this account works out stock cost.

Two modes, asked for as a toggle on the Sales page:

    tracked   the repricer records each source's price every couple of hours,
              and an order is costed at THE PRICE IN FORCE WHEN IT ARRIVED
    sku       the cost written into the SKU by the generator, overridden by a
              cost typed against the product, applying to every order

    GET  /cogs/mode                which mode, and what it means
    POST /cogs/mode                switch it
    POST /cogs/order               correct ONE order's cost by hand
    GET  /cogs/orders/template.csv the same correction, for MANY orders
    POST /cogs/orders/upload       read the filled-in file back
    POST /cogs/refreeze            re-cost a window after switching mode

Its own file because it is its own feature (CLAUDE.md Rule 7), and because the
Sales routes should not grow a settings screen.
"""
from flask import jsonify, request

import domain.order_cogs as _oc
import domain.request_account as _req_acct


def register(app, *, CONFIG_PATH, _cfg, _state, _active_account,
             _save_account, _cogs_overrides):

    def _scope():
        # BOTH SPELLINGS, because the app uses both and always has.
        #
        # request_account.named() reads `account_id` only; two thirds of the
        # route files read `request.args.get("id") or request.args.get("account_id")`
        # and a page may legitimately send either. This one accepted only the
        # first, so ?id=nestwell_goods silently fell through to whichever
        # workspace happened to be open -- measured: a template downloaded for
        # nestwell_goods arrived filled with miles_lubricants' orders, named
        # correctly in the filename and wrong inside.
        #
        # Deliberately NOT fixed by teaching named() the `id` spelling: several
        # routes use ?id= to mean something else entirely (miles_routes a run
        # id, notify_routes a channel id), and widening the shared resolver
        # would make those resolve an account from an unrelated number.
        # ORDER MATTERS: what the page NAMED, in either spelling, before any
        # fallback. for_read() already falls back to the open workspace itself,
        # so asking it first and testing the answer afterwards can never reach
        # the second spelling -- which is precisely how ?id= was being ignored.
        b = request.get_json(silent=True) or {}
        aid = (_req_acct.named(request)
               or str(request.args.get("id") or b.get("id") or "").strip())
        if not aid:
            aid = str((_state or {}).get("active_account_id", "") or "")
        if not aid:
            try:
                aid = str((_active_account() or {}).get("id") or "")
            except Exception:
                aid = ""
        mkt = (request.args.get("marketplace") or b.get("marketplace")
               or _state.get("active_marketplace") or "").upper()
        return aid, mkt

    @app.route("/cogs/mode")
    def cogs_mode_get():
        wsid, _mkt = _scope()
        if not wsid:
            return jsonify({"ok": False,
                            "error": "open an account workspace first"}), 400
        mode = _oc.mode_for(_cfg, wsid)
        return jsonify({
            "ok": True, "mode": mode, "modes": list(_oc.MODES),
            "explain": {
                _oc.MODE_TRACKED:
                    "Each order costs what the supplier was charging at the "
                    "moment it arrived. Needs the repricer to be watching that "
                    "product; orders from before it started fall back to the "
                    "cost in the SKU.",
                _oc.MODE_SKU:
                    "Every order of a product costs the same: the price built "
                    "into its SKU, or a cost you have typed against it. "
                    "Changing that cost changes past orders too.",
            },
        })

    @app.route("/cogs/mode", methods=["POST"])
    def cogs_mode_set():
        wsid, _mkt = _scope()
        if not wsid:
            return jsonify({"ok": False,
                            "error": "open an account workspace first"}), 400
        b = request.get_json(force=True) or {}
        mode = str(b.get("mode") or "").strip().lower()
        if mode not in _oc.MODES:
            return jsonify({"ok": False,
                            "error": "mode must be one of %s"
                                     % ", ".join(_oc.MODES)}), 400
        try:
            # Only the one field. A full snapshot would write back whatever this
            # process last read and quietly revert anything changed since.
            _save_account(_cfg(), CONFIG_PATH, {"id": wsid, "cogs_mode": mode})
            _state["cfg"] = None
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500
        return jsonify({"ok": True, "mode": mode,
                        "note": "Existing costs stay as they were. Use "
                                "'recost' to work the window out again on the "
                                "new mode."})

    @app.route("/cogs/orders/template.csv")
    def cogs_orders_template():
        """The order-cost sheet: one row per order line, cost column empty.

        Handed out with `cost now` filled in beside the empty `cost`, so the
        sheet is corrected rather than retyped -- and so a row that is already
        right can simply be left alone, which is what makes an unedited upload
        harmless.
        """
        import csv as _csv
        import io as _io
        from flask import Response
        from domain import order_cogs_sheet as _ocs

        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "open an account and pick a marketplace first — a cost is "
                "written against one order of one account")}), 400
        start = (request.args.get("start") or "").strip() or None
        end = (request.args.get("end") or "").strip() or None
        only = str(request.args.get("uncosted") or "").lower() in ("1", "true", "yes")

        headers, rows = _ocs.template_rows(CONFIG_PATH, wsid, mkt, start, end, only)
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(headers)
        for r in rows:
            w.writerow(r)
        # utf-8-sig: Excel opens a plain UTF-8 CSV in the wrong encoding and
        # mangles every pound sign and every accented product name.
        data = buf.getvalue().encode("utf-8-sig")
        name = "order-costs-%s-%s.csv" % (wsid, mkt)
        return Response(data, mimetype="text/csv", headers={
            "Content-Disposition": 'attachment; filename="%s"' % name})

    @app.route("/cogs/orders/upload", methods=["POST"])
    def cogs_orders_upload():
        """Read a filled-in order-cost sheet and write every cost in it.

        SERVER-SIDE, like the product cost sheet and for the same reason: a
        product name such as "Grill, Large" is quoted and contains a comma, so
        splitting lines on commas in the browser shifts every column after it
        and reads the cost out of the wrong place. domain/source_bulk.read_table
        parses it properly, and spreadsheets as well.
        """
        from domain import order_cogs_sheet as _ocs
        from domain import source_bulk as _sb

        wsid, mkt = _scope()
        _missing = [n for n, v in (("account", wsid), ("marketplace", mkt)) if not v]
        if _missing:
            return jsonify({"ok": False, "error": (
                "could not read that file: no %s came with the request. A cost "
                "is written against one order of one account, so both are "
                "needed." % " or ".join(_missing))}), 400

        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "no file was sent"}), 400
        headers, rows, err = _sb.read_table(f.read(), f.filename or "")
        if err:
            return jsonify({"ok": False, "error": err}), 400
        if not headers:
            return jsonify({"ok": False,
                            "error": "there were no columns in that file"}), 400

        res = _ocs.apply_sheet(CONFIG_PATH, wsid, mkt, headers, rows)
        if not res.get("ok"):
            return jsonify(res), 400

        # SAY WHAT HAPPENED TO EVERY ROW, in the order it matters. A bulk action
        # that reports only its successes hides exactly the rows worth looking at.
        bits = []
        if res["set"]:
            bits.append("Set the cost on %d order line%s."
                        % (res["set"], "" if res["set"] == 1 else "s"))
        if res["blank"]:
            bits.append("%d row%s had no cost filled in and %s left alone."
                        % (res["blank"], "" if res["blank"] == 1 else "s",
                           "was" if res["blank"] == 1 else "were"))
        if res["unknown_order"]:
            bits.append("%d order%s in the file %s not found in this account "
                        "and marketplace."
                        % (res["unknown_order"],
                           "" if res["unknown_order"] == 1 else "s",
                           "was" if res["unknown_order"] == 1 else "were"))
        if res["bad_number"]:
            bits.append("%d cost%s could not be read as a number."
                        % (res["bad_number"],
                           "" if res["bad_number"] == 1 else "s"))
        if not bits:
            bits.append("Nothing in that file changed anything.")
        res["note"] = " ".join(bits)
        return jsonify(res)

    @app.route("/cogs/order", methods=["POST"])
    def cogs_order_set():
        """Correct ONE order's cost. That order only, for ever.

        "my typed cogs win but it should be only for that order not all time
        frames and all orders" -- so this writes onto the order line and is
        marked as a person's own figure, which nothing later overwrites.
        """
        wsid, mkt = _scope()
        b = request.get_json(force=True) or {}
        oid = str(b.get("order_id") or "").strip()
        # WHICH OF THE THREE IS MISSING, not all three names every time.
        #
        # This answered "need an account, marketplace and order" whichever one
        # was absent. The Orders page was sending the account and the order and
        # not the marketplace -- because the row did not carry one, which is now
        # fixed in domain/orders_view.to_row -- and the message named three
        # things, two of which had been sent. There was nothing in it to say
        # where to look.
        _missing = [n for n, v in (("account", wsid), ("marketplace", mkt),
                                   ("order", oid)) if not v]
        if _missing:
            return jsonify({"ok": False, "error": (
                "could not save that cost: no %s came with the request. A cost "
                "is written against one order of one account, so all three are "
                "needed." % " or ".join(_missing))}), 400
        cost = b.get("cost")
        if cost not in (None, ""):
            try:
                cost = float(cost)
            except (TypeError, ValueError):
                return jsonify({"ok": False,
                                "error": "cost must be a number"}), 400
            if cost < 0:
                return jsonify({"ok": False,
                                "error": "cost cannot be negative"}), 400
        else:
            cost = None          # clearing it puts the order back to unknown
        n = _oc.set_for_order(CONFIG_PATH, wsid, mkt, oid, cost,
                              sku=b.get("sku"))
        if not n:
            return jsonify({"ok": False,
                            "error": "no line of that order is stored yet"}), 404
        return jsonify({"ok": True, "lines_updated": n})

    @app.route("/cogs/refreeze", methods=["POST"])
    def cogs_refreeze():
        """Work costs out again for a window, on the current mode.

        Needed after switching mode, or after typing a cost for a product that
        had none -- existing orders keep whatever they were given, deliberately,
        so putting it right is an explicit act rather than a silent rewrite.
        """
        wsid, mkt = _scope()
        b = request.get_json(force=True) or {}
        start, end = str(b.get("start") or ""), str(b.get("end") or "")
        if not wsid or not mkt or not start or not end:
            return jsonify({"ok": False,
                            "error": "need an account, marketplace and a date "
                                     "range"}), 400
        try:
            res = _oc.freeze_range(CONFIG_PATH, wsid, mkt, start, end,
                                   _oc.mode_for(_cfg, wsid),
                                   _cogs_overrides(),
                                   force=bool(b.get("force")))
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500
        return jsonify({"ok": True, **res})
