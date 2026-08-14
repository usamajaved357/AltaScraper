"""routes/seller_routes.py -- import an eBay seller's catalogue as drafts.

    POST /seller/find     enumerate a seller. Sends nothing to Amazon.
    POST /seller/screen   ask Amazon what may be listed, BEFORE drafting.
    POST /seller/draft    write the wanted items into this app as drafts.

Drafting reaches nothing but our own store. Publishing is the approve-and-submit
path that already exists, untouched -- which is the whole point of the pipeline
over listing straight to Amazon.

The rules live in domain/seller_import.py; this file supplies the data and does
the calling. The screening checks are INJECTED there for exactly that reason, so
they can be tested against every combination without a network.
"""
from flask import request, jsonify

from domain import seller_import as _si


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /seller/* to the app."""

    def _scope():
        acc = _active_account() or {}
        body = request.get_json(silent=True) or {}
        wsid = str(body.get("id") or acc.get("id")
                   or _state.get("active_account_id") or "")
        mkt = str(body.get("marketplace") or _state.get("active_marketplace")
                  or acc.get("default_marketplace") or "").upper()
        return acc, wsid, mkt

    def _body():
        return request.get_json(force=True, silent=True) or {}

    def _ebay_creds():
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        return (str(cfg.get("ebay_app_id", "") or ""),
                str(cfg.get("ebay_cert_id", "") or ""))

    # ---- 1. find ---------------------------------------------------------
    @app.route("/seller/find", methods=["POST"])
    def seller_find():
        """Everything of this seller's we can locate. Nothing is drafted."""
        from api import ebay as _ebay
        b = _body()
        _acc, _wsid, mkt = _scope()
        seller = (b.get("seller") or "").strip()
        if not seller:
            return jsonify({"ok": False, "error": "no seller given"}), 400
        app_id, cert_id = _ebay_creds()
        if not (app_id and cert_id):
            return jsonify({"ok": False, "error": (
                "eBay credentials are not set — add them under Settings.")}), 400

        terms = b.get("terms") or None
        items, meta = _ebay.search_seller(
            seller, app_id, cert_id,
            marketplace=_ebay.site_for(mkt),
            terms=terms,
            pages_per_term=int(b.get("pages_per_term") or 3))
        rows = [_si.to_review_row(i) for i in items]
        rows.sort(key=lambda r: (r["title"] or "").lower())
        return jsonify({
            "ok": True, "seller": seller, "marketplace": mkt,
            "rows": rows, "found": len(rows), "meta": meta,
            # Said in the reply, not only in the UI: any caller of this endpoint
            # needs to know the number is a floor and not a total.
            "note": ("Found %d items. eBay has no way to list a seller's whole "
                     "inventory, so this is what %d searches turned up — treat it "
                     "as a floor, not a total."
                     % (len(rows), len(meta.get("terms") or [])))})

    # ---- 2. screen -------------------------------------------------------
    @app.route("/seller/screen", methods=["POST"])
    def seller_screen():
        """What Amazon will and will not let this account list. Sends no listing."""
        b = _body()
        acc, wsid, mkt = _scope()
        rows = b.get("rows") or []
        if not rows:
            return jsonify({"ok": False, "error": "nothing to screen"}), 400

        from domain import accounts as _acc_mod
        mkt_id = _acc_mod.marketplace_id(mkt)
        seller_id = str((acc or {}).get("seller_id") or "")
        creds = _acc_mod.account_creds(acc or {})

        def restriction_lookup(row):
            """Amazon's own answer -- authoritative, and only where it applies.

            getListingsRestrictions is keyed by ASIN. Per CLAUDE.md Rule 1 these
            become NEW products under our own brands, so most have no ASIN to ask
            about and this correctly returns "nothing to say" rather than
            inventing a verdict. Where an item DOES carry an ASIN, Amazon's
            answer beats every rule of ours.
            """
            asin = str(row.get("asin") or "").strip()
            if not asin:
                return {"blocked": False}
            if not (seller_id and mkt_id):
                return None                      # could not ask
            try:
                from sp_api.api import ListingsRestrictions
                from sp_api.base import Marketplaces
                enum_ = (Marketplaces.US if mkt == "US"
                         else getattr(Marketplaces, mkt, Marketplaces.UK))
                lr = ListingsRestrictions(credentials=creds, marketplace=enum_,
                                          timeout=30)
                res = lr.get_listings_restrictions(
                    asin=asin, sellerId=seller_id, marketplaceIds=[mkt_id],
                    conditionType="new_new")
                pay = res.payload if hasattr(res, "payload") else res
            except Exception:
                return None
            out, msgs = False, []
            for x in ((pay or {}).get("restrictions") or []):
                for rn in (x.get("reasons") or []):
                    code = str(rn.get("reasonCode") or "")
                    msg = str(rn.get("message") or "")
                    if code == "ASIN_NOT_FOUND":
                        # Not a restriction: Amazon simply does not have it in
                        # this marketplace, which is the normal case for a new
                        # product and must not read as "blocked".
                        continue
                    out = True
                    msgs.append(msg or code)
            return {"blocked": out, "reasons": msgs}

        def restricted_type(row):
            """The app's own restricted-product rules, already used at generation.

            check_restricted_type answers with overall_action BLOCK | WARN | NONE
            and the matches behind it. BLOCK is a refusal; WARN is worth seeing
            before you commit generation spend but is not a stop.
            """
            from listing.restricted import check_restricted_type
            res = check_restricted_type(
                text=" ".join(filter(None, [row.get("title"), row.get("category")])),
                marketplace=mkt or "UK",
                category_path=" > ".join(row.get("categories") or []))
            if not isinstance(res, dict) or not res.get("matched"):
                return None
            action = str(res.get("overall_action") or "").upper()
            if action not in ("BLOCK", "WARN"):
                return None
            labels = [str(m.get("label") or m.get("reason") or "")
                      for m in (res.get("matches") or [])][:3]
            return {"blocked": action == "BLOCK",
                    "message": ("%s: %s" % (
                        "Amazon restricts this" if action == "BLOCK"
                        else "Worth checking before you spend on it",
                        "; ".join([l for l in labels if l]) or "matched a rule"))}

        def compliance(row):
            """Document demand, from the rules the app already carries.

            Same question the generator asks, asked EARLIER -- before the copy
            and the images are paid for rather than after.
            """
            from listing import sourcing_viability as _sv
            res = _sv.check_sourcing_viability(
                title=row.get("title") or "",
                category=row.get("category") or "",
                marketplace=mkt or "UK")
            if not isinstance(res, dict) or not res.get("matched"):
                return None
            docs = res.get("docs") or []
            lines = []
            try:
                lines = _sv.sourcing_warning_lines(res) or []
            except Exception:
                pass
            if not docs and str(res.get("overall_action") or "").upper() == "NONE":
                return None
            return {"docs": True,
                    "message": (lines[0] if lines else
                                "Amazon is likely to ask for documents: %s"
                                % ", ".join(str(d) for d in docs[:3]))}

        screened, summary = _si.screen(
            rows, restriction_lookup=restriction_lookup,
            restricted_type=restricted_type, compliance=compliance)
        return jsonify({"ok": True, "rows": screened, "summary": summary,
                        "workspace": wsid, "marketplace": mkt})

    # ---- 3. draft --------------------------------------------------------
    @app.route("/seller/draft", methods=["POST"])
    def seller_draft():
        """Write the wanted items into THIS APP as drafts. Amazon is not touched."""
        b = _body()
        _acc, wsid, mkt = _scope()
        rows = [r for r in (b.get("rows") or []) if r.get("selected")]
        if not b.get("confirmed"):
            return jsonify({"ok": False, "error": "not confirmed"}), 400
        if not rows:
            return jsonify({"ok": False, "error": "nothing selected"}), 400
        if not (wsid and mkt):
            return jsonify({"ok": False, "error": (
                "no account or marketplace selected")}), 400

        # A blocked item cannot be published, so drafting it only spends money on
        # copy and images that can never be used. Refused here as well as hidden
        # in the browser: a checkbox is not a control.
        blocked = [r for r in rows
                   if (r.get("screen") or {}).get("verdict") == _si.BLOCKED]
        if blocked and not b.get("include_blocked"):
            return jsonify({"ok": False, "error": (
                "%d of these are blocked by Amazon and cannot be published, so "
                "drafting them would only spend generation credits. Untick them, "
                "or send include_blocked to draft them anyway."
                % len(blocked))}), 400

        drafts = [_si.to_draft(r, account_id=wsid, marketplace=mkt,
                               days=int(b.get("handling_days") or 3))
                  for r in rows]

        # ListingStore is the app's own draft store, one per workspace, and
        # upsert_row keys on SKU -- so re-importing a seller updates the rows it
        # already made instead of piling up duplicates of the same product.
        written, errors = 0, []
        try:
            from data.store import ListingStore
            store = ListingStore(wsid, config_path=CONFIG_PATH)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "could not open the draft store: %s"
                                     % str(e)[:160]}), 500
        for d in drafts:
            try:
                store.upsert_row(d)
                written += 1
            except Exception as e:
                errors.append({"sku": d["sku"], "error": str(e)[:160]})

        return jsonify({"ok": not errors, "drafted": written,
                        "errors": errors, "skus": [d["sku"] for d in drafts],
                        "note": ("Drafted into this app only — nothing has been "
                                 "sent to Amazon. Review them on the Listings "
                                 "screen and submit the ones you want.")})
