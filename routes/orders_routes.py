"""routes/orders_routes.py -- orders from every account, on one screen.

    GET  /orders/list     recent orders, this account or all of them
    GET  /orders/detail   one order's lines

Reads only. Nothing here changes an order, and Amazon is asked directly rather
than through a cache, because an order's status is the thing most likely to have
moved since anything was stored.

The rules and the shaping live in domain/orders_view.py, including the measured
explanation of which customer details Amazon withholds from this application.
"""
import datetime as _dt

from flask import request, jsonify

from domain import orders_view as _ov


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /orders/* to the app."""

    def _accounts_in_scope():
        """Which accounts to ask, and why that is the default.

        ALL of them by default: the whole reason this screen exists is not
        having to open each account in turn. An account with no Amazon
        credentials of its own is skipped rather than failed on -- it has no
        orders to have.
        """
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        want = (request.args.get("account") or "").strip()
        out = []
        for a in (cfg.get("accounts") or []):
            aid = str(a.get("id") or "")
            if want and want != "__all__" and aid != want:
                continue
            if not (a.get("seller_id") and (a.get("default_marketplace")
                                            or a.get("marketplaces"))):
                continue
            out.append(a)
        return out

    def _marketplace(a):
        m = str(a.get("default_marketplace") or "").strip().upper()
        if m:
            return m
        ms = a.get("marketplaces") or []
        return str(ms[0]).upper() if ms else ""

    @app.route("/orders/list")
    def orders_list():
        """Recent orders, newest first, with the account each belongs to."""
        from domain import accounts as _acc_mod
        try:
            days = max(1, min(90, int(request.args.get("days") or 30)))
        except (TypeError, ValueError):
            days = 30
        since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)

        rows, errors, asked = [], [], []
        for a in _accounts_in_scope():
            aid = str(a.get("id") or "")
            mkt = _marketplace(a)
            asked.append(aid)
            try:
                from domain import orders_live as _ol
                got, truncated = _ol.fetch_since(
                    mkt, _acc_mod.marketplace_id(mkt), _acc_mod.account_creds(a),
                    since, max_pages=int(request.args.get("pages") or 3))
            except Exception as e:
                # One account failing must not empty the whole screen -- that is
                # the difference between "Nestwell's token expired" and "you have
                # no orders", and only one of them is true.
                errors.append({"account": aid,
                               "error": str(e)[:200]})
                continue
            label = a.get("label") or aid
            for o in got:
                rows.append(_ov.to_row(o, account_id=aid, account_label=label))
            if truncated:
                errors.append({"account": aid, "error": (
                    "more orders exist than were fetched — narrow the days or "
                    "raise pages")})

        rows = _ov.sort_rows(rows)
        q = (request.args.get("q") or "").strip().lower()
        if q:
            rows = [r for r in rows
                    if q in (r["order_id"] or "").lower()
                    or q in (r["region"] or "").lower()
                    or q in (r["account"] or "").lower()
                    or q in (r["status"] or "").lower()]

        # ---- what each order EARNED, on request ------------------------
        #
        # Opt-in and capped, because it costs one Amazon call per order: the
        # order row carries no SKU, and without a SKU there is no cost, and
        # without a cost there is no profit. Doing it for 117 orders
        # unprompted would make the screen take two minutes to open.
        #
        # So the list loads instantly, and asking for profit is a deliberate
        # act with a stated ceiling -- the count is reported, never silently
        # truncated.
        profit_note = ""
        if request.args.get("with_profit") == "1":
            try:
                cap = max(1, min(200, int(request.args.get("max_profit") or 60)))
            except (TypeError, ValueError):
                cap = 60
            cost_of = _cost_fn()
            done = 0
            for r in rows:
                if done >= cap:
                    break
                items = _items_for(r["order_id"], r["account_id"])
                if items is None:
                    continue
                p, m, why = _ov.profit_for(items, r.get("total"), cost_of)
                r["profit"], r["margin_pct"], r["profit_note"] = p, m, why
                r["lines"] = len(items)
                done += 1
            if len(rows) > cap:
                profit_note = ("Worked out the profit for the newest %d of %d "
                               "orders — each one costs a separate call to "
                               "Amazon. Narrow the days, or raise max_profit."
                               % (cap, len(rows)))
            else:
                profit_note = "Profit worked out for all %d." % done

        return jsonify({"ok": True, "rows": rows, "days": days,
                        "accounts_asked": asked, "errors": errors,
                        "summary": _ov.summarise(rows),
                        "profit_note": profit_note,
                        "pii_note": _ov.PII_NOTE})

    def _cost_fn():
        """sku -> (cost, source), from the ONE resolver (domain/cogs.py)."""
        from domain import cogs as _cogs
        try:
            from dashboard import _COGS_OVERRIDE as _ov_map
        except Exception:
            _ov_map = {}
        return _cogs.lookup(_ov_map, str(_state.get("active_account_id", "") or ""))

    def _items_for(order_id, account_id):
        """One order's lines, or None if Amazon would not say."""
        from domain import accounts as _acc_mod
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        acc = next((a for a in (cfg.get("accounts") or [])
                    if str(a.get("id") or "") == str(account_id)), None)
        if not acc:
            return None
        mkt = _marketplace(acc)
        try:
            from sp_api.api import Orders
            from sp_api.base import Marketplaces
            enum = getattr(Marketplaces, mkt.upper(), Marketplaces.UK)
            oc = Orders(credentials=_acc_mod.account_creds(acc), marketplace=enum)
            r = oc.get_order_items(order_id)
            pay = r.payload if hasattr(r, "payload") else r
            return [_ov.to_item(x) for x in ((pay or {}).get("OrderItems") or [])]
        except Exception:
            return None


    @app.route("/orders/detail")
    def orders_detail():
        """One order's lines. Items are not restricted and come through whole."""
        from domain import accounts as _acc_mod
        oid = (request.args.get("order_id") or "").strip()
        aid = (request.args.get("account") or "").strip()
        if not oid:
            return jsonify({"ok": False, "error": "no order id"}), 400
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        acc = next((a for a in (cfg.get("accounts") or [])
                    if str(a.get("id") or "") == aid), None)
        if not acc:
            return jsonify({"ok": False, "error": (
                "That order's account is not configured here.")}), 404
        mkt = _marketplace(acc)
        try:
            from sp_api.api import Orders
            from sp_api.base import Marketplaces
            enum = getattr(Marketplaces, mkt.upper(), Marketplaces.UK)
            oc = Orders(credentials=_acc_mod.account_creds(acc), marketplace=enum)
            r = oc.get_order_items(oid)
            pay = r.payload if hasattr(r, "payload") else r
            items = [_ov.to_item(x) for x in ((pay or {}).get("OrderItems") or [])]
            r2 = oc.get_order(oid)
            head = r2.payload if hasattr(r2, "payload") else r2
        except Exception as e:
            return jsonify({"ok": False, "error": (
                "Amazon would not return that order: %s" % str(e)[:200])}), 502

        row = _ov.to_row(head or {}, account_id=aid,
                         account_label=acc.get("label") or aid)
        # Free here: the lines are already in hand, so what the order earned
        # costs nothing more to work out.
        p, m, why = _ov.profit_for(items, row.get("total"), _cost_fn())
        row["profit"], row["margin_pct"], row["profit_note"] = p, m, why
        return jsonify({"ok": True, "order_id": oid, "order": row,
                        "items": items,
                        "pii_note": _ov.PII_NOTE})
