"""routes/orders_routes.py -- orders from every account, on one screen.

    GET  /orders/list     recent orders, this account or all of them
    GET  /orders/detail   one order's lines

Reads only. Nothing here changes an order.

WHAT IS ASKED OF AMAZON, AND WHAT IS NOT.

The LIST is always fetched live: an order's status is the thing most likely to
have moved since anything was stored, and a shipped order shown as unshipped is
worth a call.

Its CONTENTS are not. What was in an order never changes once it is placed, so
they are read from order_lines and only fetched when nobody has read that order
yet -- and then kept. That is the difference between the Item column filling in
about a minute and filling at once: "the orders page takes too much long to
reflect the item name and image etc", measured at ~65s for 24 orders, one
sequential call each.

The rules and the shaping live in domain/orders_view.py, including the measured
explanation of which customer details Amazon withholds from this application.
"""
import datetime as _dt

from flask import request, jsonify

from domain import orders_view as _ov


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /orders/* to the app."""

    def _accounts_in_scope():
        """Which accounts to ask. THE OPEN ONE, unless every account is asked for.

        This used to default to ALL accounts, because the screen was built to
        answer "show me every account's orders without opening each in turn".
        That is a real use, but it cannot be the default:

            "why do i have every account's order in each account, each account
             should show its own orders ... they are different entities
             different business they dont have anything in common"

        And that is right. These are separate limited companies with separate
        sellers and separate customers. A screen opened inside Jack Reacherd
        that lists Selvora's orders -- with the customer's name and address on
        it -- is not a convenience, it is one business's customer data shown
        under another's name.

        So: the account you have open, always, unless you explicitly ask for
        every one with account=__all__. An account with no Amazon credentials
        of its own is skipped rather than failed on; it has no orders to have.
        """
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        want = (request.args.get("account") or "").strip()
        if not want:
            # No explicit ask -> the account currently open. Falling back to
            # "all" here is exactly the bug above.
            try:
                want = str((_active_account() or {}).get("id") or "").strip()
            except Exception:
                want = ""
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
            # THE PICTURE, RESOLVED HERE RATHER THAN IN THE BROWSER.
            #
            # It was matched in the page against LIVE_ITEMS -- the catalogue the
            # LISTINGS screen loads. Open Orders without going via Listings
            # first, which is the normal way to open Orders, and that array is
            # empty: every row showed the product's name and no picture, on the
            # one screen that was reworked to show pictures.
            #
            # The snapshot is already cached per workspace, so this costs a dict
            # build per request and nothing from Amazon.
            pics = _pictures()
            done = 0
            # HOW MANY COULD NOT BE READ. This loop `continue`d on a failed
            # read without counting it, so an outcome where EVERY order failed
            # -- a throttled account, an expired token -- was reported exactly
            # like success, and the screen showed a column of dashes with a note
            # saying the profit had been worked out. Silence about a total
            # failure is the one thing this file is otherwise careful about.
            unread = 0
            for r in rows:
                if done >= cap:
                    break
                items = _items_for(r["order_id"], r["account_id"], r.get("purchased") or "")
                if items is None:
                    unread += 1
                    continue
                # ROI as well as margin, and WHAT was bought. Both come out of
                # the same call that was already being made -- the items are in
                # hand here, and the row previously threw them away after
                # counting them. Asked for as: "i want to see the item picture
                # and name of the item and profit and roi and margin or each
                # order without opening the order details".
                d = _ov.profit_detail(items, r.get("total"), cost_of)
                r["profit"] = d["profit"]
                r["margin_pct"] = d["margin_pct"]
                r["roi_pct"] = d["roi_pct"]
                r["cogs"] = d["cogs"]
                r["profit_note"] = d["note"]
                it = _ov.item_summary(items)
                it["img"] = _cat_look(pics, it).get("img") or ""
                r["item"] = it
                r["lines"] = len(items)
                done += 1
            if len(rows) > cap:
                profit_note = ("Worked out the profit for the newest %d of %d "
                               "orders — each one costs a separate call to "
                               "Amazon. Narrow the days, or raise max_profit."
                               % (cap, len(rows)))
            else:
                profit_note = "Profit worked out for all %d." % done
            if unread:
                profit_note += (" %d order%s could not be read from Amazon — "
                                "usually rate limiting; try again shortly."
                                % (unread, "" if unread == 1 else "s"))

        return jsonify({"ok": True, "rows": rows, "days": days,
                        "accounts_asked": asked, "errors": errors,
                        "summary": _ov.summarise(rows),
                        "profit_note": profit_note,
                        "pii_note": _ov.PII_NOTE})

    def _cat_look(idx, it):
        """This order line's catalogue record. SKU first, then ASIN."""
        from domain import catalogue as _cat
        return _cat.look(idx, (it or {}).get("sku"), (it or {}).get("asin"))

    def _pictures():
        """{sku or asin -> {img, title, ...}} for every account in scope.

        From the cached live snapshot, the same place the Listings cards get
        theirs, so one product does not have two different pictures in one app.
        The reading itself is domain/catalogue.py, shared with Sales and Traffic
        (CLAUDE.md Rule 12). An account with no snapshot contributes nothing.
        """
        from domain import catalogue as _cat
        return _cat.merged(CONFIG_PATH,
                           [(str(a.get("id") or ""), _marketplace(a))
                            for a in _accounts_in_scope()])

    def _cost_fn():
        """sku -> (cost, source), from the ONE resolver (domain/cogs.py).

        The overrides come from domain/cogs_store.py, which owns them.

        THIS SAID `from dashboard import _COGS_OVERRIDE` AND GOT AN EMPTY DICT.
        dashboard.py is the file that is RUN, so its module name is "__main__";
        importing "dashboard" loads the file a second time and binds a separate
        module whose _COGS_OVERRIDE nothing ever fills. So every cost typed on
        the listings screen was invisible to this column, and an order whose SKU
        had been costed by hand still reported "not known" for its profit,
        margin and ROI -- with nothing to suggest the figure existed.
        """
        from domain import cogs as _cogs
        from domain import cogs_store as _cs
        return _cogs.lookup(_cs.all_overrides(CONFIG_PATH),
                            str(_state.get("active_account_id", "") or ""))

    def _items_from_store(account_id, marketplace, order_id):
        """One order's lines from order_lines, or None if it is not there.

        WHY THIS IS FIRST. An order's contents never change once it is placed, so
        reading them from Amazon a second time buys nothing and costs a call --
        and the calls are the reason the screen was slow: "the orders page takes
        too much long to reflect the item name and image etc", measured at about
        65 seconds for 24 orders, one sequential call each.

        The table is already there and already filled by the hourly-sales fetch
        (domain/hourly_week.py), which stores every order it reads for the same
        reason. This just uses it.
        """
        try:
            from data import db as _db
            rows = _db.get_db(CONFIG_PATH).execute(
                "SELECT asin, sku, title, units FROM order_lines "
                "WHERE workspace_id=? AND marketplace=? AND order_id=?",
                (str(account_id or ""), str(marketplace or ""),
                 str(order_id or ""))).fetchall()
        except Exception:
            return None
        if not rows:
            return None
        return [{"asin": str(r["asin"] or ""), "sku": str(r["sku"] or ""),
                 "title": str(r["title"] or ""),
                 "qty": int(r["units"] or 0) or 1} for r in rows]

    def _store_items(account_id, marketplace, order_id, items, purchased=""):
        """Keep what Amazon just told us, so the next visit is free."""
        try:
            from domain import hourly_week as _hw
            _hw.store_lines(CONFIG_PATH, str(account_id or ""),
                            str(marketplace or ""),
                            [{"order_id": str(order_id or ""),
                              "purchase_date": str(purchased or ""),
                              "asin": it.get("asin") or "",
                              "sku": it.get("sku") or "",
                              "title": it.get("title") or "",
                              "units": it.get("qty") or 1,
                              "revenue": it.get("price") or 0,
                              "shipping": it.get("shipping") or 0,
                              "currency": it.get("currency") or "",
                              "status": it.get("status") or ""}
                             for it in (items or [])])
        except Exception:
            pass                     # a cache must never be the reason this fails

    def _items_for(order_id, account_id, purchased=""):
        """One order's lines, or None if Amazon would not say.

        Reads the store first -- see _items_from_store. Only an order nobody has
        read yet costs a call, and what that call returns is kept.
        """
        from domain import accounts as _acc_mod
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        acc = next((a for a in (cfg.get("accounts") or [])
                    if str(a.get("id") or "") == str(account_id)), None)
        if not acc:
            return None
        mkt = _marketplace(acc)
        cached = _items_from_store(account_id, mkt, order_id)
        if cached:
            return cached
        try:
            from sp_api.api import Orders
            from sp_api.base import Marketplaces
            enum = getattr(Marketplaces, mkt.upper(), Marketplaces.UK)
            oc = Orders(credentials=_acc_mod.account_creds(acc), marketplace=enum)
            r = oc.get_order_items(order_id)
            pay = r.payload if hasattr(r, "payload") else r
            got = [_ov.to_item(x) for x in ((pay or {}).get("OrderItems") or [])]
        except Exception:
            return None
        # Kept, so the next visit to this screen does not pay for it again.
        if got:
            _store_items(account_id, mkt, order_id, got, purchased)
        return got


    @app.route("/orders/items", methods=["POST"])
    def orders_items():
        """What was in these orders, and what each earned. Nothing else.

        WHY THIS EXISTS RATHER THAN with_profit=1.

        The screen draws the list first and fills the products in behind it,
        because reading an order's lines costs one Amazon call each and nobody
        should watch an empty table for a minute. The second pass used to call
        /orders/list again with with_profit=1 -- which re-fetched the whole
        order feed to get a list it already had on screen.

        Twice the order-feed calls for one screen, and Amazon throttles: the
        second fetch came back empty and the screen reported "Profit worked out
        for all 0", which reads exactly like an account with nothing in it.
        Measured on selvora_limited, 3 days, 24 orders on screen and 0 costed.

        So this takes the orders the screen already has and answers only the
        question it cannot answer itself. Same _items_for and same
        profit_detail as the list route -- one definition of what an order
        earned, not two.
        """
        b = request.get_json(force=True, silent=True) or {}
        want = [x for x in (b.get("orders") or []) if isinstance(x, dict)][:200]
        if not want:
            return jsonify({"ok": True, "items": {}, "note": ""})
        cost_of = _cost_fn()
        pics = _pictures()
        out, unread = {}, 0
        for w in want:
            oid = str(w.get("order_id") or "").strip()
            aid = str(w.get("account_id") or "").strip()
            if not oid:
                continue
            items = _items_for(oid, aid, str(w.get("purchased") or ""))
            if items is None:
                unread += 1
                continue
            d = _ov.profit_detail(items, w.get("total"), cost_of)
            it = _ov.item_summary(items)
            it["img"] = _cat_look(pics, it).get("img") or ""
            out[oid] = {"item": it, "lines": len(items),
                        "profit": d["profit"], "margin_pct": d["margin_pct"],
                        "roi_pct": d["roi_pct"], "cogs": d["cogs"],
                        "profit_note": d["note"]}
        note = ""
        if unread:
            note = ("%d of %d could not be read from Amazon — usually rate "
                    "limiting; press Refresh to try those again."
                    % (unread, len(want)))
        return jsonify({"ok": True, "items": out, "asked": len(want),
                        "read": len(out), "unread": unread, "note": note})

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
                        # WHERE TO BUY EACH LINE FROM. Read from what the last
                        # sweep already stored, so opening an order contacts no
                        # supplier and costs nothing.
                        "sources": _sources_for_items(aid, mkt, items),
                        "pii_note": _ov.PII_NOTE})

    def _sources_for_items(account_id, marketplace, items):
        """{sku: {options, summary}} for the lines of one order.

        Reads the readings the repricer's sweep already took -- it does NOT go to
        eBay. Opening an order must not fire off a dozen supplier calls, and the
        prices from the last sweep are the prices the repricer itself is working
        from, so the two screens agree by construction.

        Never raises. A supplier lookup that failed must not stop an order being
        looked at.
        """
        out = {}
        try:
            import datetime as _dt
            from domain import order_sources as _osrc
            from domain import source_repo as _repo
            now = _dt.datetime.now()
        except Exception:
            return out
        for it in (items or []):
            sku = str((it or {}).get("sku") or "")
            if not sku or sku in out:
                continue
            try:
                # THE PRICE THIS BUYER ACTUALLY PAID, per unit -- not the current
                # listing price. The profit shown has to be the profit on the
                # order in front of you; a line sold at a coupon price does not
                # earn what the listing earns today.
                qty = int((it or {}).get("qty") or (it or {}).get("quantity") or 1) or 1
                paid = it.get("price")
                unit = (float(paid) / qty) if paid not in (None, "") else None
            except (TypeError, ValueError):
                unit = None
            try:
                # THE RULE FOR THIS SKU, which is the account default with any
                # per-SKU override laid over it -- source_repo owns that merge.
                # Per SKU and never per ASIN: one ASIN can carry several SKUs at
                # different costs with different targets.
                rule = _repo.rule_for(CONFIG_PATH, account_id, marketplace, sku)
            except Exception:
                rule = None
            try:
                opts = _osrc.options_for(CONFIG_PATH, account_id, marketplace, sku,
                                         sell_price=unit, rule=rule, now=now)
                out[sku] = {"options": opts, "summary": _osrc.summary(opts),
                            "unit_price": unit}
            except Exception as exc:
                out[sku] = {"options": [], "summary": {},
                            "error": "%s: %s" % (type(exc).__name__, str(exc)[:120])}
        return out
