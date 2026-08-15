"""routes/asin_charges_routes.py -- the extra costs per product.

The supplier's price covers the goods and their postage. These are everything
after that: sending it on, prep, an advertising figure allocated by hand.

    GET    /charges/list?asin=&sku=      what is recorded
    POST   /charges/save                 add or update one
    POST   /charges/delete               remove one
    GET    /charges/preview?asin=&on=    what a unit of this costs on a date

Deliberately no CSV upload. Asked for: "the user should not have an option to
upload cogs by sheet because it makes it useless" -- a bulk sheet of one figure
per product flattens exactly the per-order, dated detail the repricer exists to
capture.
"""
from flask import jsonify, request

import domain.asin_charges as _ac
import domain.request_account as _req_acct


def register(app, *, CONFIG_PATH, _cfg, _state, _active_account):

    def _scope():
        """Whose charges, and for which marketplace.

        The account comes from the PAGE, not from the process-wide global --
        same rule as the Sales screen, same module. See domain/request_account.
        """
        aid, _acc = _req_acct.for_read(request, _state)
        if not aid:
            try:
                aid = str((_active_account() or {}).get("id") or "")
            except Exception:
                aid = ""
        body = request.get_json(silent=True) or {}
        mkt = (request.args.get("marketplace") or body.get("marketplace")
               or _state.get("active_marketplace") or "").upper()
        return aid, mkt

    @app.route("/charges/list")
    def charges_list():
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False,
                            "error": "open an account workspace first"}), 400
        rows = _ac.list_for(CONFIG_PATH, wsid, mkt,
                            asin=(request.args.get("asin") or "").strip() or None,
                            sku=(request.args.get("sku") or "").strip() or None)
        return jsonify({"ok": True, "charges": rows,
                        "workspace": wsid, "marketplace": mkt})

    @app.route("/charges/save", methods=["POST"])
    def charges_save():
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False,
                            "error": "open an account workspace first"}), 400
        b = request.get_json(force=True) or {}
        try:
            cid = _ac.save(CONFIG_PATH, wsid, mkt,
                           asin=b.get("asin") or "",
                           sku=b.get("sku") or "",
                           label=b.get("label") or "",
                           amount=b.get("amount"),
                           effective_from=b.get("effective_from") or "",
                           note=b.get("note") or "",
                           charge_id=b.get("id"))
        except ValueError as e:
            # The user's own mistake, said plainly, not a 500.
            return jsonify({"ok": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500
        return jsonify({"ok": True, "id": cid})

    @app.route("/charges/delete", methods=["POST"])
    def charges_delete():
        wsid, mkt = _scope()
        b = request.get_json(force=True) or {}
        if not b.get("id"):
            return jsonify({"ok": False, "error": "which charge?"}), 400
        try:
            _ac.delete(CONFIG_PATH, wsid, mkt, b["id"])
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500
        return jsonify({"ok": True})

    @app.route("/charges/preview")
    def charges_preview():
        """What one unit of this product costs in charges on a given date.

        The date matters: a charge carries the day it started applying, so this
        is also how you check that raising a fee today has not moved what last
        month earned.
        """
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False,
                            "error": "open an account workspace first"}), 400
        total, parts = _ac.per_unit(
            CONFIG_PATH, wsid, mkt,
            asin=(request.args.get("asin") or "").strip(),
            sku=(request.args.get("sku") or "").strip(),
            on_date=(request.args.get("on") or "").strip() or None)
        return jsonify({"ok": True, "per_unit": total, "parts": parts})
