"""routes/order_ship_routes.py -- tell Amazon an order was posted, with its tracking.

    POST /orders/ship/preview   what Amazon WOULD be sent. Reads the order's
                                lines from Amazon; sends nothing.
    POST /orders/ship/confirm   send it. REFUSED while the owner's switch is off
                                (domain/ship_confirm.is_on_now -- read fresh from
                                the settings file), before Amazon is contacted.

The rules, the switch and the request shape live in domain/ship_confirm.py; the
two Amazon calls in api/amazon_orders_ship.py. The account must be named
(domain/order_scope.py, Rule 14) and allowed to write to Amazon
(domain/accounts.can_publish, the same gate as submitting a listing).

ONE CONFIRMATION PER ORDER FROM HERE. Amazon's own shipped count can lag, so
this app's own record of having sent one is what stops a second
(ship_confirm.already_sent). An answer that is neither an acceptance nor a
refusal -- a timeout, a reply with no status -- is recorded as UNSURE and also
blocks a resend: the person checks Seller Central and removes that tracking
number to allow another try.

Amazon's refusal is shown in Amazon's own words and nothing is changed or
retried because of it (CLAUDE.md Rule 4).
"""
from flask import jsonify, request

from domain import order_scope as _osc
from domain import request_account as _req_acct
from domain import ship_confirm as _sc


def register(app, *, CONFIG_PATH, _cfg):
    """Attach /orders/ship/* to the app."""

    def _prepare(b, what):
        """(ctx dict, None) or (None, refusal). Reads Amazon; writes nothing."""
        from domain import accounts as _acc_mod
        from domain import orders_live as _ol
        from api import amazon_orders_ship as _aos
        try:
            acc, mkt, oid = _osc.resolve(_cfg, _req_acct.named_now(),
                                         b.get("marketplace"), b.get("order_id"), what)
        except _osc.ScopeError as e:
            return None, (jsonify({"ok": False, "error": str(e)}), e.status)
        label = acc.get("label") or acc.get("id")
        # Seller-scoped calls with the account's OWN credentials only, and only
        # for an account allowed to write to Amazon at all.
        if not _acc_mod.can_publish(acc):
            return None, (jsonify({"ok": False, "error": (
                "%s is not allowed to write to Amazon from this app (it has no "
                "Amazon account of its own, or publishing is turned off for it)."
                % label)}), 400)
        try:
            enum = _ol.orders_marketplace(mkt, label)
        except _ol.NoMarketplace as e:
            return None, (jsonify({"ok": False, "error": str(e)}), 400)
        aid = str(acc.get("id"))
        prior = _sc.already_sent(CONFIG_PATH, aid, mkt, oid)
        if prior:
            return None, (jsonify({"ok": False, "already_sent": True, "error": (
                "This app already told Amazon about this order (tracking %s%s). "
                "Check it in Seller Central. To send again, remove that tracking "
                "number on this order first."
                % (prior.get("tracking_number"),
                   ", result not known" if prior.get("source") == _sc.UNSURE else ""))}), 409)
        creds = _acc_mod.account_creds(acc)
        try:
            raw = _aos.order_items(creds, enum, oid)
        except Exception as e:
            return None, (jsonify({"ok": False, "error": (
                "Amazon would not return that order's lines: %s" % str(e)[:300])}), 502)
        payload, problems = _sc.build_payload(
            getattr(enum, "marketplace_id", ""), raw, b.get("tracking_number"),
            b.get("carrier"), b.get("ship_date"))
        return {"acc": acc, "aid": aid, "mkt": mkt, "oid": oid, "enum": enum,
                "creds": creds, "payload": payload, "problems": problems}, None

    def _remember(ctx, source):
        """Record the number sent; a failure here must not hide that it was sent."""
        from domain import tracking as _tr
        d = ctx["payload"]["packageDetail"]
        try:
            _tr.add(CONFIG_PATH, ctx["aid"], ctx["mkt"], ctx["oid"], d["trackingNumber"],
                    carrier=d.get("carrierName") or d.get("carrierCode"), source=source)
            return ""
        except Exception as e:
            return (" The tracking number could not be saved in this app (%s); add it "
                    "by hand so it is not sent again." % str(e)[:120])

    @app.route("/orders/ship/preview", methods=["POST"])
    def orders_ship_preview():
        b = request.get_json(silent=True) or {}
        ctx, bad = _prepare(b, "checked")
        if bad:
            return bad
        on = _sc.is_on_now(CONFIG_PATH)
        return jsonify({"ok": not ctx["problems"], "problems": ctx["problems"],
                        "error": " ".join(ctx["problems"]),
                        "payload": ctx["payload"],
                        "summary": _sc.describe(ctx["payload"]) if ctx["payload"] else "",
                        "switched_on": on, "why_off": "" if on else _sc.OFF_REASON})

    @app.route("/orders/ship/confirm", methods=["POST"])
    def orders_ship_confirm():
        # THE SWITCH FIRST: while it is off, not even the read happens.
        if not _sc.is_on_now(CONFIG_PATH):
            return jsonify({"ok": False, "switched_on": False,
                            "error": _sc.OFF_REASON}), 409
        from api import amazon_orders_ship as _aos
        b = request.get_json(silent=True) or {}
        ctx, bad = _prepare(b, "sent")
        if bad:
            return bad
        if ctx["problems"]:
            return jsonify({"ok": False, "problems": ctx["problems"],
                            "error": " ".join(ctx["problems"])}), 400
        try:
            from sp_api.base import SellingApiException as _Refused
        except Exception:                                  # pragma: no cover
            _Refused = ()
        try:
            _aos.confirm_shipment(ctx["creds"], ctx["enum"], ctx["oid"], ctx["payload"])
        except _Refused as e:
            # Amazon answered with its errors: a refusal, in its own words
            # (Rule 4). Nothing is recorded, so it can be corrected and sent.
            return jsonify({"ok": False, "error": (
                "Amazon refused the dispatch confirmation: %s" % str(e)[:500])}), 502
        except Exception as e:
            # No clear answer (timeout, dropped connection, a reply with no
            # status). It may have landed, so it is recorded as UNSURE, which
            # blocks a second send until someone has looked.
            note = _remember(ctx, _sc.UNSURE)
            return jsonify({"ok": False, "uncertain": True, "error": (
                "It is not known whether Amazon received this (%s). Check the order "
                "in Seller Central before trying again.%s" % (str(e)[:200], note))}), 502
        note = _remember(ctx, _sc.SENT)
        return jsonify({"ok": True, "sent": True, "summary": _sc.describe(ctx["payload"]),
                        "note": "Amazon now shows this order as dispatched." + note})
