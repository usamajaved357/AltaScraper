"""routes/compliance_routes.py -- scan a LIVE listing for compliance.

    POST /compliance/scan    scan one ASIN now
    GET  /compliance/scans   what has been scanned, newest first

    Orbit's Compliance checker. The checks are this app's own -- every one of
    them written after a real listing was refused or taken down -- and until now
    they only ever ran at GENERATION time, on copy about to be submitted. A
    listing written before a rule existed, edited in Seller Central afterwards,
    or inherited from a supplier had never been looked at by any of them.

THE COPY IS READ FROM AMAZON, not from this app's draft. That is the whole
point: the draft is what we MEANT to publish, and the question is what is
actually live. Uses the Catalog Items lookup the ASIN research screen already
uses (CLAUDE.md Rule 12) -- read-only, no listing rights.

NOTHING IS CHANGED. This reads and reports. Editing live listing copy is a
submission to Amazon and belongs behind a person's decision.
"""
from flask import jsonify, request

from domain import compliance_scan as _cs


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /compliance/* to the app."""

    def _scope():
        aid = (request.args.get("id") or request.args.get("account_id") or "").strip()
        mkt = (request.args.get("marketplace") or "").strip().upper()
        b = request.get_json(silent=True) or {}
        aid = aid or str(b.get("id") or b.get("account_id") or "").strip()
        mkt = mkt or str(b.get("marketplace") or "").strip().upper()
        if not aid or not mkt:
            acc = {}
            try:
                acc = (_active_account() or {}) if callable(_active_account) else {}
            except Exception:
                acc = {}
            aid = aid or str(acc.get("id") or (_state or {}).get("active_account_id") or "")
            mkt = mkt or str(acc.get("default_marketplace")
                             or (_state or {}).get("active_marketplace") or "").upper()
        return aid, (mkt or "UK")

    def _ip_rules():
        try:
            import json
            import os
            p = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)),
                             "ip_rules.json")
            if not os.path.exists(p):
                p = "ip_rules.json"
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    @app.route("/compliance/scans", methods=["GET"])
    def compliance_scans():
        wsid, _mkt = _scope()
        asin = (request.args.get("asin") or "").strip().upper()
        return jsonify({"ok": True,
                        "scans": _cs.scans(CONFIG_PATH, wsid, asin),
                        "bands": _cs.BANDS})

    @app.route("/compliance/scan", methods=["POST"])
    def compliance_scan_one():
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        asin = str(b.get("asin") or "").strip().upper()
        if not asin or len(asin) < 8:
            return jsonify({"ok": False,
                            "error": "Enter an ASIN, e.g. B0XXXXXXXX."}), 400

        # THE LIVE COPY, from Amazon. Through the same Catalog Items read the
        # ASIN research screen uses -- read-only, needs no listing rights, and
        # one implementation rather than two (Rule 12).
        try:
            import accounts as _acc
            from sp_api.api import CatalogItemsV20220401 as CatalogItems
            from sp_api.base import Marketplaces
            cfg = (_cfg() or {}) if callable(_cfg) else {}
            accts = _acc.load_accounts(cfg, CONFIG_PATH) or []
            acc = next((a for a in accts if str(a.get("id")) == str(wsid)), None)
            if not acc:
                return jsonify({"ok": False,
                                "error": "That account is not connected."}), 400
            creds = _acc.account_creds(acc)
            mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
            mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.UK
            cat = CatalogItems(credentials=creds, marketplace=mkt_enum, timeout=30)
            res = cat.get_catalog_item(
                asin=asin, includedData=["summaries", "attributes", "productTypes"],
                marketplaceIds=[mid] if mid else None)
            pay = res.payload if hasattr(res, "payload") else (res or {})
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read that listing from Amazon: "
                                     "%s: %s" % (type(e).__name__, str(e)[:160])}), 502

        summaries = (pay.get("summaries") or [{}])
        summ = summaries[0] if summaries else {}
        pts = pay.get("productTypes") or [{}]
        product_type = (pts[0].get("productType", "") if pts else "") or ""
        brand = summ.get("brand") or summ.get("manufacturer") or ""

        record = {"title": summ.get("itemName") or "",
                  "attributes": pay.get("attributes") or {}}
        listing = _cs.listing_from(record)
        if not listing.get("title"):
            return jsonify({"ok": False,
                            "error": "Amazon returned no copy for that ASIN in %s "
                                     "— nothing to scan." % mkt}), 404

        result = _cs.build(asin, listing, brand=brand, product_type=product_type,
                           ip_rules=_ip_rules(),
                           # No supplier documentation is available for a LIVE
                           # listing read back from Amazon, so the grounding
                           # checks are skipped -- and the result says so rather
                           # than scoring as though they had run.
                           source_text="",
                           title=listing.get("title", ""), marketplace=mkt)
        _cs.store(CONFIG_PATH, wsid, result)
        result["ok"] = True
        result["brand"] = brand
        return jsonify(result)
