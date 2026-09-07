"""routes/draft_sources_routes.py -- a DRAFT's suppliers, on the drafts page.

    "on draft the sources should stay on the drafts page but should display the
     handling time, the carrier info and delivery time and source price and
     source name etc same as repricer shows it, in the same format"

ONE ROUTE:

    GET /listing/sources?sku=...&mkt=...

and it decides nothing. Every figure comes from domain/order_sources.options_for
-- the SAME function the order panel and the repricer draw their supplier lists
from -- so "the same format" is not a matter of copying a layout: it is the same
data, in the same shape, drawn by the same renderer (_ordSourcesHtml in
static/js/orders.js). A second builder here would have been a second opinion
about which link is cheapest, what it lands at, and when it would arrive
(CLAUDE.md Rule 12).

WHY DRAFTS NEED THEIR OWN ROUTE AT ALL. They are the same rows in the same
table, distinguished by `stage`. The order panel and the repricer ask for LIVE,
because a draft's suppliers belong to a listing nobody can buy yet and must not
sit beside listings that are selling. This asks for DRAFT. When the listing goes
BUYABLE, source_repo.promote_to_live flips the stage and the very same rows --
with every price check already taken -- appear on those screens instead.

NOTHING HERE TALKS TO EBAY. It reads the last stored check. The prices are as
fresh as the last sweep, and each line carries its own checked_at so the screen
can say so rather than implying they are live.

NOTHING IS WRITTEN.
"""
import datetime as _dt

from flask import request, jsonify

from domain import order_sources as _osrc
from domain import source_repo as _repo


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach GET /listing/sources."""

    def _scope():
        acc = _active_account() or {}
        wsid = str(acc.get("id") or _state.get("active_account_id") or "")
        mkt = str(request.args.get("mkt")
                  or acc.get("default_marketplace")
                  or _state.get("active_marketplace") or "UK").strip().upper()
        return wsid, mkt, acc

    @app.route("/listing/sources")
    def listing_sources():
        wsid, mkt, _acc = _scope()
        if not wsid:
            return jsonify({"ok": False,
                            "error": "open an account workspace first"}), 400
        sku = (request.args.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400

        # WHICH STAGE. Default is the draft's own, which is what this route
        # exists for; `stage=all` is accepted so a screen showing a listing
        # that has just gone live does not have to know which side of the flip
        # it is on and show nothing during the gap.
        want = (request.args.get("stage") or _repo.DRAFT).strip().lower()
        stage = None if want in ("all", "any", "") else want

        # THE PRICE THESE OPTIONS ARE JUDGED AGAINST. A draft has no order and
        # no settled price, so the profit column is answered at the price the
        # draft is going to be listed at -- sent by the browser, exactly as
        # /listing/revenue takes its price, so the number agrees with the one
        # on screen. Without it the options still list; only the profit,
        # margin and ROI are absent, which options_for already handles by
        # leaving them None rather than printing a zero.
        sell = request.args.get("price")
        try:
            sell = float(str(sell).replace(",", "").strip()) if sell else None
        except (TypeError, ValueError):
            sell = None

        try:
            rule = _repo.rule_for(CONFIG_PATH, wsid, mkt, sku)
        except Exception:
            rule = None
        try:
            opts = _osrc.options_for(CONFIG_PATH, wsid, mkt, sku,
                                     sell_price=sell, rule=rule,
                                     now=_dt.datetime.now(), stage=stage)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "%s: %s" % (type(e).__name__, str(e)[:200])}), 500

        return jsonify({
            "ok": True, "sku": sku, "marketplace": mkt, "stage": want,
            "options": opts,
            # The one-line version the order panel's compact mode draws from.
            "summary": _osrc.summary(opts),
            # SAID PLAINLY, because a supplier list on a draft is easy to read
            # as "this is being tracked". It is not, yet.
            "tracked": bool(stage != _repo.DRAFT),
            "note": ("These suppliers are attached to a draft. They start being "
                     "checked by the repricer, and appear on an order, once "
                     "Amazon confirms the listing is buyable."
                     if stage == _repo.DRAFT else ""),
        })
