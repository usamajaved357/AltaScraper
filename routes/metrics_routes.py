"""routes/metrics_routes.py -- the numbers beside a listing.

Holds no decision logic. What a figure IS comes from
domain/listing_metrics.py (the local tables), what is worth caching from
data/metrics_cache.py, and the two SP-API calls from api/amazon_metrics.py and
domain/inventory_module.py.

LOCAL FIRST, AND ALWAYS. Units, sales, page views, buy-box share and on-hand
stock are already in this database -- measured, not assumed (see
domain/listing_metrics.py). They are read on every request and returned whether
or not Amazon is reachable, so the screen is useful with SP-API down and with no
credentials at all.

AMAZON IS ONLY ASKED FOR WHAT IS MISSING, and only when asked to:

    GET /listing/live_metrics?skus=A,B,C          local only. No SP-API. Fast.
    GET /listing/live_metrics?skus=...&fetch=1    also refresh what is stale.

A page load takes the first form. The refresh button and the drawer take the
second. That is the whole rate-limit policy: a screen that fetched on every
render would spend a catalogue call per listing per visit.

THIS ACCOUNT'S SP-API ROLES HAVE BEEN PARTIAL BEFORE -- price, stock and orders
have all returned 403 while the token itself authenticated fine. So a refusal is
reported as a refusal, per group, and never stored: the row keeps saying "we do
not have this" rather than "Amazon says there is none". The two look identical
on screen once a blank has been cached, which is the failure this is built to
avoid.
"""
import time

from flask import request, jsonify

from data import metrics_cache as _cache
from domain import listing_metrics as _lm


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach the /listing/live_metrics routes to the existing Flask app."""

    def _scope():
        """(workspace_id, marketplace) for the account the server has open."""
        acc = _active_account() or {}
        wsid = str(acc.get("id") or _state.get("active_account_id") or "")
        mkt = str(request.args.get("mkt")
                  or acc.get("default_marketplace")
                  or _state.get("active_marketplace") or "UK").strip().upper()
        return wsid, mkt, acc

    def _skus():
        raw = request.args.get("skus", "") or ""
        out, seen = [], set()
        for s in raw.split(","):
            s = s.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    # ---- the SP-API half ------------------------------------------------

    def _refresh(acc, wsid, mkt, skus, asins):
        """Fetch what is stale, cache what came back, report what refused.

        Returns {"fetched": {group: n}, "errors": {group: "why"}}. Never raises:
        a metrics screen must not be able to 500 because Amazon is unhappy.
        """
        report = {"fetched": {}, "errors": {}}
        try:
            import domain.accounts as _acc
        except Exception as e:
            report["errors"]["all"] = "accounts module unavailable: %s" % e
            return report
        rt = str(acc.get("refresh_token", ""))
        if not rt or rt.startswith(("PUT_", "ROTATE")):
            report["errors"]["all"] = "this account is not connected to Amazon"
            return report
        creds = _acc.account_creds(acc)
        mid = _acc.marketplace_id(mkt) or ""

        # --- rank and price, per ASIN -----------------------------------
        # Keyed by SKU in the cache but fetched per ASIN, and two SKUs can share
        # one ASIN, so each ASIN is called once and the answer written to every
        # SKU that points at it.
        for group, fn in (("rank", _rank_for), ("pricing", _price_for)):
            due = _cache.stale_skus(CONFIG_PATH, wsid, mkt, skus, group)
            due = [s for s in due if asins.get(s)]
            if not due:
                continue
            by_asin = {}
            for s in due:
                by_asin.setdefault(asins[s], []).append(s)
            n, err = 0, ""
            for asin, owners in by_asin.items():
                got = fn(creds, mkt, mid, asin)
                if got.get("error"):
                    err = err or got["error"]
                    continue
                data = got.get("data") or {}
                if not data:
                    continue
                for s in owners:
                    if _cache.put(CONFIG_PATH, wsid, mkt, s, group, data):
                        n += 1
            if n:
                report["fetched"][group] = n
            if err and not n:
                report["errors"][group] = err

        # --- FBA stock, one call for the whole account ------------------
        # inventory_module already pulls available / reserved / inbound per SKU,
        # with a documented reason for using the Inventories API. Not rewritten
        # here (Rule 12). It is one call for every SKU, so it runs when ANY is
        # stale rather than per SKU.
        if _cache.stale_skus(CONFIG_PATH, wsid, mkt, skus, "fba"):
            try:
                from domain import inventory_module as _inv
                res = _inv.fetch_fba_inventory(creds, mkt, mid)
            except Exception as e:
                res = {"rows": [], "report_source": "error", "error": str(e)[:200]}
            if res.get("report_source") == "error":
                report["errors"]["fba"] = str(res.get("error") or "")[:200]
            else:
                n = 0
                want = set(skus)
                for row in res.get("rows") or []:
                    s = str(row.get("sku") or "")
                    if s not in want:
                        continue
                    data = {
                        "available": _num(row.get("afn_fulfillable_quantity")),
                        "reserved": _num(row.get("afn_reserved_quantity")),
                        "inbound": _num(row.get("inbound_total")),
                        # Stock Amazon holds and will not sell. Carried through
                        # because it is the figure that costs money while
                        # looking like inventory everywhere else.
                        "unfulfillable": _num(row.get("afn_unsellable_quantity")),
                    }
                    data = {k: v for k, v in data.items() if v is not None}
                    if data and _cache.put(CONFIG_PATH, wsid, mkt, s, "fba", data):
                        n += 1
                if n:
                    report["fetched"]["fba"] = n
        return report

    def _rank_for(creds, mkt, mid, asin):
        from api import amazon_metrics as _am
        got = _am.sales_rank(creds, mkt, mid, asin)
        if got["status"] != _am.OK:
            return {"error": got.get("error") or "rank lookup failed"}
        if got.get("rank") is None:
            # A real answer: no rank yet. Nothing to cache, nothing wrong.
            return {"data": {}}
        return {"data": {"rank": got["rank"], "category": got.get("category") or ""}}

    def _price_for(creds, mkt, mid, asin):
        from api import amazon_metrics as _am
        got = _am.competitive_price(creds, mkt, mid, asin)
        if got["status"] != _am.OK:
            return {"error": got.get("error") or "pricing lookup failed"}
        d = {}
        if got.get("buy_box_price") is not None:
            d["buy_box_price"] = got["buy_box_price"]
        if got.get("offer_count") is not None:
            d["offer_count"] = got["offer_count"]
        return {"data": d}

    def _num(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return int(f) if f == int(f) else f

    # ---- the route ------------------------------------------------------

    @app.route("/listing/live_metrics")
    def listing_live_metrics():
        wsid, mkt, acc = _scope()
        if not wsid:
            return jsonify({"ok": False,
                            "error": "open an account workspace first"}), 400
        skus = _skus()
        if not skus:
            return jsonify({"ok": True, "metrics": {}, "coverage": {},
                            "fetched": {}, "errors": {}, "last_updated": 0})
        # A ceiling, so one URL cannot ask for the whole catalogue and hold a
        # worker open through 300 catalogue calls.
        if len(skus) > 400:
            skus = skus[:400]

        try:
            days = int(request.args.get("days") or _lm.DEFAULT_DAYS)
        except ValueError:
            days = _lm.DEFAULT_DAYS

        local = _lm.for_skus(CONFIG_PATH, wsid, mkt, skus, days)
        asins = {s: (local.get(s) or {}).get("asin", "") for s in skus}

        report = {"fetched": {}, "errors": {}}
        if request.args.get("fetch") in ("1", "true", "yes"):
            report = _refresh(acc, wsid, mkt, skus, asins)

        # Merge the cached SP-API answers over the local ones. The local figures
        # are never overwritten by a cached copy of themselves -- the two sets
        # do not overlap, by design (see data/metrics_cache.py).
        cached = _cache.get(CONFIG_PATH, wsid, mkt, skus)
        for sku, groups in cached.items():
            m = local.setdefault(sku, {})
            for grp, entry in groups.items():
                for k, v in (entry.get("data") or {}).items():
                    m[k] = v
                if entry.get("stale"):
                    m.setdefault("stale_groups", []).append(grp)

        return jsonify({
            "ok": True,
            "metrics": local,
            "coverage": _lm.coverage(CONFIG_PATH, wsid, mkt, days),
            "last_updated": _cache.newest(CONFIG_PATH, wsid, mkt, skus),
            "now": time.time(),
            "fetched": report.get("fetched") or {},
            # Reported, never swallowed: a screen showing dashes because Amazon
            # refused must be able to say so.
            "errors": report.get("errors") or {},
        })

    @app.route("/listing/metrics_forget", methods=["POST"])
    def listing_metrics_forget():
        """Drop the cached SP-API answers so the next fetch is a real one.

        Behind a POST because it changes stored state, and it is what "Refresh
        metrics" uses when someone does not believe what is on screen.
        """
        wsid, mkt, _acc = _scope()
        if not wsid:
            return jsonify({"ok": False,
                            "error": "open an account workspace first"}), 400
        b = request.get_json(silent=True) or {}
        skus = b.get("skus") or None
        n = _cache.forget(CONFIG_PATH, wsid, mkt, skus)
        return jsonify({"ok": True, "removed": n})
