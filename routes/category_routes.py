"""routes/category_routes.py -- Category Explorer: where your products sit.

    GET  /categories          what has been mapped
    POST /categories/populate read categories from Amazon for this account

    Orbit's Category Explorer -- "Where <brand>'s products sit in Amazon's
    category tree", with counts of mapped and uncategorized products.

WHY THIS IS ONE CALL PER PRODUCT, AND THEREFORE A BUTTON.

The category comes from the ASIN's sales ranks, which is a Catalog Items call
per ASIN -- fifty products is fifty calls. Orbit has a "Populate from Amazon"
button for exactly this reason and so does this. Nothing here runs on a timer
and nothing runs on page load; the stored map is what the screen draws.

THE RANK COMES BACK WITH IT, because it is the same call. A category with no
rank in it is a category you are listed in and not selling in, and that
distinction is most of what the screen is for.

UNCATEGORIZED IS A REAL ANSWER. Amazon does not rank every listing -- a product
with no sales history often has no rank at all, and therefore no category. Those
are counted and named rather than dropped, because "39 uncategorized" is the
number that tells you the map is partial.
"""
import datetime

from flask import jsonify, request

from domain import jsonstore

_FILE = "categories.json"


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /categories/* to the app."""

    def _path():
        return jsonstore.path_beside_config(CONFIG_PATH, _FILE)

    def _load():
        d = jsonstore.read_json(_path(), None)
        return d if isinstance(d, dict) else {}

    def _scope():
        aid = (request.args.get("id") or request.args.get("account_id") or "").strip()
        mkt = (request.args.get("marketplace") or "").strip().upper()
        b = request.get_json(silent=True) or {}
        aid = aid or str(b.get("id") or "").strip()
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

    def _catalogue(wsid, mkt):
        """{asin: record} for this account, from the shared lookup."""
        try:
            from domain import catalogue as _cat
            idx = _cat.index(CONFIG_PATH, wsid, mkt) or {}
            out = {}
            for rec in idx.values():
                a = str((rec or {}).get("asin") or "").strip().upper()
                if a and a not in out:
                    out[a] = rec
            return out
        except Exception:
            return {}

    def _view(wsid, mkt):
        stored = (_load().get("%s::%s" % (wsid, mkt)) or {})
        known = _catalogue(wsid, mkt)
        by_cat = {}
        uncategorized = []
        for asin, rec in sorted(known.items()):
            got = stored.get(asin) or {}
            cat = str(got.get("category") or "")
            row = {"asin": asin,
                   "title": rec.get("title") or "",
                   "img": rec.get("img") or "",
                   "rank": got.get("rank"),
                   "category": cat,
                   # Never read from Amazon, versus read and Amazon had no rank.
                   # A screen that shows both as "uncategorized" tells you to go
                   # and populate something that has already been populated.
                   "checked": asin in stored}
            if cat:
                c = by_cat.setdefault(cat, {"category": cat, "products": [],
                                            "best_rank": None})
                c["products"].append(row)
                r = got.get("rank")
                if r is not None and (c["best_rank"] is None or r < c["best_rank"]):
                    c["best_rank"] = r
            else:
                uncategorized.append(row)
        cats = sorted(by_cat.values(),
                      key=lambda c: (-len(c["products"]),
                                     c["best_rank"] if c["best_rank"] is not None else 1e12))
        return {
            "categories": cats,
            "uncategorized": uncategorized,
            "counts": {
                "categories": len(cats),
                "mapped": sum(len(c["products"]) for c in cats),
                "uncategorized": len(uncategorized),
                "never_checked": len([r for r in uncategorized if not r["checked"]]),
                "products": len(known),
            },
            "fetched_at": stored.get("_at", "") if isinstance(stored, dict) else "",
        }

    @app.route("/categories", methods=["GET"])
    def categories_get():
        wsid, mkt = _scope()
        out = _view(wsid, mkt)
        out.update({"ok": True, "account": wsid, "marketplace": mkt})
        if not out["counts"]["products"]:
            out["note"] = ("This account has no catalogue snapshot yet, so there "
                           "are no products to place. Refresh the listings first.")
        elif not out["counts"]["mapped"]:
            out["note"] = ("Nothing has been read from Amazon yet. Press "
                           "\"Populate from Amazon\" — it is one call per "
                           "product, so it is a button rather than something "
                           "that happens on its own.")
        return jsonify(out)

    @app.route("/categories/populate", methods=["POST"])
    def categories_populate():
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        try:
            limit = int(b.get("limit") or 60)
        except ValueError:
            limit = 60
        # A CEILING, AND IT IS DECLARED. One Catalog call per product; without a
        # bound, pressing this on a large catalogue is hundreds of calls nobody
        # asked for. What was skipped is reported rather than silently dropped.
        limit = max(1, min(limit, 200))

        known = _catalogue(wsid, mkt)
        if not known:
            return jsonify({"ok": False,
                            "error": "No catalogue snapshot for this account."}), 400
        key = "%s::%s" % (wsid, mkt)
        stored = (_load().get(key) or {})
        # Products never checked come first, so pressing it twice makes progress
        # rather than re-reading the same sixty.
        todo = [a for a in sorted(known) if a not in stored][:limit]
        if not todo:
            todo = sorted(known)[:limit]

        try:
            import accounts as _acc
            cfg = (_cfg() or {}) if callable(_cfg) else {}
            accts = _acc.load_accounts(cfg, CONFIG_PATH) or []
            acc = next((a for a in accts if str(a.get("id")) == str(wsid)), None)
            if not acc:
                return jsonify({"ok": False,
                                "error": "That account is not connected."}), 400
            creds = _acc.account_creds(acc)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read the account: %s" % str(e)[:150]}), 500

        try:
            from domain import tracker_fetch as _tf
            got = _tf.fetch_ranks(creds, todo, mkt) or {}
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "%s: %s" % (type(e).__name__, str(e)[:170])}), 502

        data = _load()
        row = data.setdefault(key, {})
        for a, d in got.items():
            row[a] = {"rank": (d or {}).get("rank"),
                      "category": (d or {}).get("category") or "",
                      "all": (d or {}).get("all") or []}
        row["_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        jsonstore.write_json_atomic(_path(), data, indent=2)

        out = _view(wsid, mkt)
        out.update({"ok": True, "account": wsid, "marketplace": mkt,
                    "read": len(got), "asked": len(todo),
                    "remaining": len([a for a in known if a not in row])})
        if out["remaining"]:
            out["note"] = ("%d products still to read — press it again. Each one "
                           "is a separate call to Amazon, so this is capped per "
                           "press rather than running for minutes."
                           % out["remaining"])
        return jsonify(out)
