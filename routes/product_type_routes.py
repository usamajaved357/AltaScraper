"""routes/product_type_routes.py -- Amazon's product types, asked for directly.

    GET|POST /product_types/drafts  the drafts to ask about (ticked, or the account),
                                    and every listing left out with its reason
    POST /product_types/lookup    Amazon's type for a few of those: by competitor
                                  ASIN, or by title when a draft has no ASIN
    GET  /product_types/search    Amazon's product types for a title, or for words
    POST /product_types/recheck   work the warnings out again after types changed

WHY IT EXISTS

    "why am i seeing that error on almost all of my listings"
    "i see a very limited products type to select from the pdp in the app"
    "fix the product types from amazon, and build the search"

The drawer's product-type box offered the 21 names in valid_values.json -- a
file from the flat-file template days -- and Amazon UK has well over a thousand.
And from 29 Aug 2026 queued drafts generated without their competitor ASIN, so
their type was guessed from the title and came out HOME.

WHAT IT DOES NOT DO

  * Write a listing. A corrected type is saved by the browser through /edit, the
    one path that writes a field (Rule 12). This file only asks Amazon.
  * Borrow access the owner did not set up. Credentials come from
    accounts.resolve_catalog_creds, the app's existing catalogue-scope rule; an
    account Amazon refuses is reported as refused ("couldn't check"), never
    quietly answered with another account's app.
  * Ask about many ASINs in one request. The browser sends a few at a time:
    getCatalogItem allows about two calls a second, and one long request over a
    whole workspace is one that times out half way with nothing to show.
"""
import re
import time

from flask import request, jsonify

# Per request, for /lookup. Measured at ~1.8s a call from Pakistan, so a full
# batch is under half a minute and the screen shows progress between batches.
MAX_LOOKUP = 15
PACE = 0.55          # seconds between the STARTS of two catalogue calls
_ASIN = re.compile(r"^[A-Z0-9]{10}$")


def register(app, *, CONFIG_PATH, _cfg, _state):

    def _wrong_account(asked):
        """The same guard the rest of the app uses (domain/account_scope.py)."""
        from domain import account_scope as _acctscope
        open_id = (_state or {}).get("active_account_id")
        if _acctscope.is_mismatch(asked, open_id):
            return jsonify(_acctscope.refusal(asked, open_id, "listing")), 409
        return None

    def _scope(aid, marketplace):
        """(account_id, marketplace_code, marketplace_id, creds, error_response)."""
        import accounts as _acc
        aid = str(aid or (_state or {}).get("active_account_id") or "").strip()
        if not aid:
            return None, None, None, None, (jsonify({
                "ok": False, "error": "Open an account first."}), 400)
        cfg = (_cfg() or {}) if callable(_cfg) else {}
        acc = _acc.get_account(cfg, aid, CONFIG_PATH)
        if not acc:
            return None, None, None, None, (jsonify({
                "ok": False, "error": "No account called %s." % aid}), 404)
        mkt = str(marketplace or acc.get("default_marketplace") or "UK").strip().upper()
        if mkt == "GB":
            mkt = "UK"
        mid = _acc.marketplace_id(mkt)
        if not mid:
            return None, None, None, None, (jsonify({
                "ok": False, "error": "Unknown marketplace %s." % mkt}), 400)
        try:
            creds, _lender = _acc.resolve_catalog_creds(cfg, acc, CONFIG_PATH)
        except LookupError as e:
            return None, None, None, None, (jsonify({
                "ok": False, "denied": True, "error": str(e)}), 200)
        return aid, mkt, mid, creds, None

    def _truthy(v):
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @app.route("/product_types/drafts", methods=["GET", "POST"])
    def product_types_drafts():
        """What Fix product types will check, and every listing it leaves out.

        POST {"account", "skus": [...ticked], "include_submitted"}; GET still
        works with ?account= for the whole account. `drafts` now includes drafts
        with no competitor ASIN (method "title"); `skipped` says why each other
        listing was left out -- see listing/product_type.candidates.
        """
        b = (request.get_json(silent=True) or {}) if request.method == "POST" else {}
        aid = b.get("account") or request.args.get("account")
        bad = _wrong_account(aid)
        if bad:
            return bad
        aid = str(aid or (_state or {}).get("active_account_id") or "").strip()
        if not aid:
            return jsonify({"ok": False, "error": "Open an account first."}), 400
        skus = b.get("skus")
        if skus is None:
            skus = [s for s in (request.args.get("skus") or "").split(",") if s.strip()]
        include = _truthy(b.get("include_submitted",
                                request.args.get("include_submitted", "")))
        from listing import product_type as _pt
        got = _pt.candidates(CONFIG_PATH, aid, skus=(skus or None),
                             include_submitted=include)
        return jsonify({"ok": True, "account": aid, "selected": len(skus or []),
                        "drafts": got["check"], "skipped": got["skipped"]})

    @app.route("/product_types/lookup", methods=["POST"])
    def product_types_lookup():
        b = request.get_json(force=True) or {}
        bad = _wrong_account(b.get("account"))
        if bad:
            return bad
        aid, mkt, mid, creds, err = _scope(b.get("account"), b.get("marketplace"))
        if err:
            return err
        from listing import product_type as _pt
        want = {str(s) for s in (b.get("skus") or [])}
        include = _truthy(b.get("include_submitted", ""))
        # Re-read from the store rather than trusting what the browser says a
        # row's ASIN, title and type are: the verdict is about what is saved.
        drafts = [d for d in _pt.candidates(CONFIG_PATH, aid, skus=(list(want) or None),
                                            include_submitted=include)["check"]
                  if d["sku"] in want]
        asins, titled = [], []
        for d in drafts:
            if d["method"] == _pt.BY_TITLE:
                titled.append(d)
            elif _ASIN.match(d["asin"]) and d["asin"] not in asins:
                asins.append(d["asin"])
        if len(asins) + len(titled) > MAX_LOOKUP:
            return jsonify({"ok": False,
                            "error": "At most %d lookups per request." % MAX_LOOKUP}), 400

        from api import amazon_catalog as _cat
        answers = {}
        # Refused once is refused for the rest OF THAT KIND: same account, same
        # app. Kept per kind because the catalogue and the product-type search
        # are separate Amazon permissions.
        refused = {}
        jobs = [(_pt.BY_ASIN, a) for a in asins] + [(_pt.BY_TITLE, d) for d in titled]
        last = 0.0
        for i, (kind, what) in enumerate(jobs):
            key = what if kind == _pt.BY_ASIN else _pt.answer_key(what)
            if kind in refused:
                answers[key] = dict(refused[kind])
                continue
            # About two calls a second is Amazon's allowance -- but a call
            # measured 1.6-3.3s end to end from here, so only wait for whatever
            # is left of the gap since the previous one STARTED.
            gap = PACE - (time.time() - last)
            if i and gap > 0:
                time.sleep(gap)
            last = time.time()
            if kind == _pt.BY_ASIN:
                answers[key] = _cat.product_type_of(creds, mkt, mid, what)
            else:
                # NO COMPETITOR ASIN: Amazon's own ranking of what a product with
                # this TITLE is -- the same search the listing's product-type box
                # uses, and structured data rather than a reading of prose.
                got = _cat.search_product_types(creds, mkt, mid, item_name=what["title"])
                names = [t.get("name") for t in (got.get("types") or []) if t.get("name")]
                status = got.get("status") or _cat.FAILED
                answers[key] = {
                    "status": _cat.OK if (status == _cat.OK and names) else status,
                    "product_type": names[0] if names else "",
                    "options": names[:10],
                    "error": (got.get("error")
                              or ("" if names else "Amazon suggested no product type for this title")),
                }
            if answers[key].get("status") == _cat.DENIED:
                refused[kind] = dict(answers[key])
        denied = any(v.get("status") == _cat.DENIED for v in answers.values())
        return jsonify({"ok": True, "marketplace": mkt, "denied": denied,
                        "rows": _pt.compare(drafts, answers)})

    @app.route("/product_types/search", methods=["GET"])
    def product_types_search():
        aid = request.args.get("account")
        bad = _wrong_account(aid)
        if bad:
            return bad
        aid, mkt, mid, creds, err = _scope(aid, request.args.get("marketplace"))
        if err:
            return err
        from api import amazon_catalog as _cat
        got = _cat.search_product_types(
            creds, mkt, mid,
            item_name=request.args.get("title", ""),
            keywords=request.args.get("q", ""))
        return jsonify({"ok": got["status"] in (_cat.OK, _cat.NONE),
                        "status": got["status"], "types": got["types"],
                        "error": got["error"], "marketplace": mkt})

    @app.route("/product_types/recheck", methods=["POST"])
    def product_types_recheck():
        """The warnings read product_type (the compliance check decides which
        category rules apply from it), and /edit only re-works them out for a
        barcode. So after a batch of type changes, once, for the workspace."""
        b = request.get_json(force=True) or {}
        bad = _wrong_account(b.get("account"))
        if bad:
            return bad
        aid = str(b.get("account") or (_state or {}).get("active_account_id") or "").strip()
        if not aid:
            return jsonify({"ok": False, "error": "Open an account first."}), 400
        try:
            from listing import warnings as _warn
            n, flagged = _warn.recompute_workspace(CONFIG_PATH, aid)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500
        return jsonify({"ok": True, "checked": n, "flagged": flagged})
