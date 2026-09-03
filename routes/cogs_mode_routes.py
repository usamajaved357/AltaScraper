"""routes/cogs_mode_routes.py -- which way this account works out stock cost.

Two modes, asked for as a toggle on the Sales page:

    tracked   the repricer records each source's price every couple of hours,
              and an order is costed at THE PRICE IN FORCE WHEN IT ARRIVED
    sku       the cost written into the SKU by the generator, overridden by a
              cost typed against the product, applying to every order

    GET  /cogs/mode                which mode, and what it means
    POST /cogs/mode                switch it
    POST /cogs/order               correct ONE order's cost by hand
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
        aid, _acc = _req_acct.for_read(request, _state)
        if not aid:
            try:
                aid = str((_active_account() or {}).get("id") or "")
            except Exception:
                aid = ""
        b = request.get_json(silent=True) or {}
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
