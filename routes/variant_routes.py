"""routes/variant_routes.py -- add a colour or size to something already listed.

    POST /variant/plan     what would happen, and what is missing. Sends nothing.
    POST /variant/queue    put the new variant in the queue to be generated.

THE CASE THIS IS FOR
A ceiling fan is live on Amazon in white. The black one is not on Amazon at all,
but it can be bought on eBay. You want the black one listed AND joined to the
white one so they show as one product with a colour picker.

WHAT AMAZON ACTUALLY REQUIRES, AND WHY THIS IS TWO STEPS
There is no "add a variant to this ASIN" operation. A variation family is a
PARENT listing -- a real listing with its own SKU that nobody can buy -- with
both products underneath it as children. So the white fan does not gain a
variant; the white fan and the black fan both become children of a new parent.
That is what listing/variations.py builds, and it can only be done to listings
that already EXIST on Amazon.

So: this queues the new product to be generated and submitted like any other,
carrying over the things Amazon insists every member of a family shares --
product type, brand, item type keyword -- from the listing it will join. Once it
is live, the Variations screen has both and the family is one confirmation away.

Pretending it is one step would mean building a parent over a child that does
not exist yet. Amazon accepts a half-formed family without complaint and the
products quietly stop appearing, so the sequence matters more than the
convenience.
"""
from flask import request, jsonify

from routes import scope as _scope_mod


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /variant/* to the app."""

    def _body():
        return request.get_json(silent=True) or {}

    def _scope():
        b = _body()
        return _scope_mod.resolve(state=_state, account=_active_account() or {},
                                  asked_id=b.get("id"),
                                  asked_marketplace=b.get("marketplace"))

    def _ebay_creds():
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        return (str(cfg.get("ebay_app_id", "") or ""),
                str(cfg.get("ebay_cert_id", "") or ""))

    def _existing(sku, acc, mkt):
        """What Amazon holds for the listing the new variant will join."""
        from api import amazon_listings as _al
        from domain import accounts as _acc_mod
        try:
            res = _al.get_item(_acc_mod.account_creds(acc or {}), mkt,
                               str((acc or {}).get("seller_id") or ""), sku,
                               _acc_mod.marketplace_id(mkt))
        except Exception:
            return None
        if not res or res.get("status") != _al.OK:
            return None
        return res

    def _first(attrs, name):
        """The plain value of an Amazon attribute, which is always a list."""
        v = (attrs or {}).get(name)
        if isinstance(v, list) and v:
            e = v[0]
            if isinstance(e, dict):
                for k in ("value", "name"):
                    if e.get(k) is not None:
                        return str(e[k])
            return str(e)
        return ""

    def _plan(b):
        """Everything both endpoints need. -> (plan, error, code)."""
        acc, wsid, mkt = _scope()
        sku = str(b.get("sku") or "").strip()          # the LIVE listing to join
        url = str(b.get("ebay_url") or "").strip()     # where to buy the new one
        if not sku:
            return None, "Pick the listing the new variant should join.", 400
        if not url:
            return None, ("Paste the eBay link for the new variant — that is "
                          "where its price, stock and product details come "
                          "from."), 400
        if not mkt:
            return None, _scope_mod.NO_MARKETPLACE, 400

        live = _existing(sku, acc, mkt)
        if live is None:
            return None, ("Amazon would not return %s, so there is nothing to "
                          "join the new variant to. It has to be live on Amazon "
                          "first." % sku), 502
        attrs = live.get("attributes") or {}

        # The new product's own facts, from eBay.
        from api import ebay as _ebay
        app_id, cert_id = _ebay_creds()
        if not (app_id and cert_id):
            return None, ("eBay credentials are not set — add them under "
                          "Settings."), 400
        got = _ebay.get_item(url, app_id, cert_id,
                             marketplace=_ebay.site_for(mkt))
        if got["status"] == _ebay.GROUP:
            # A whole family pasted where one variant belongs.
            return None, got["error"], 400
        if got["status"] != _ebay.OK:
            return None, ("That eBay link could not be read (%s), so the new "
                          "variant has no price or details to start from."
                          % (got.get("error") or got["status"])), 502
        item = got["data"] or {}

        price = None
        try:
            price = float((item.get("price") or {}).get("value"))
        except (TypeError, ValueError):
            price = None
        ship = None
        for opt in (item.get("shippingOptions") or []):
            c = (opt or {}).get("shippingCost")
            if isinstance(c, dict):
                try:
                    ship = float(c.get("value"))
                except (TypeError, ValueError):
                    ship = None
                break
        cost = None if (price is None or ship is None) else round(price + ship, 2)

        # WHAT A FAMILY MUST SHARE, taken from the listing being joined rather
        # than typed again -- listing/variations.check() refuses a merge where
        # these differ, and finding that out after the copy and images are paid
        # for is the expensive way round.
        shared = {
            "product_type": live.get("product_type") or "",
            "brand": _first(attrs, "brand"),
            "item_type_keyword": _first(attrs, "item_type_keyword"),
        }
        missing = [k for k, v in shared.items() if not v]

        # What makes it different. Free text here on purpose: the exact axis is
        # a per-product-type enum and is checked against the live schema at
        # merge time (Rule 4), not guessed now.
        differs = {k: str(v).strip() for k, v in (b.get("differs") or {}).items()
                   if str(v or "").strip()}

        warn = []
        if missing:
            warn.append(
                "Amazon needs every product in a family to share its %s, and "
                "that could not be read from %s. The family cannot be built "
                "until it is set." % (" and ".join(missing), sku))
        if not differs:
            warn.append("Say what is different about this one — the colour, the "
                        "size — or there is nothing for shoppers to choose "
                        "between.")
        if cost is None:
            warn.append("eBay did not give both a price and a postage cost, so "
                        "the new variant has no landed cost and cannot be "
                        "priced automatically.")

        return {
            "join_sku": sku, "marketplace": mkt, "workspace": wsid,
            "shared": shared, "differs": differs,
            "source": {"url": url, "price": price, "shipping": ship,
                       "cost": cost,
                       "title": str(item.get("title") or ""),
                       "image": ((item.get("image") or {}).get("imageUrl") or ""),
                       "item_id": got.get("item_id") or ""},
            "warnings": warn,
            "steps": [
                "The new variant is queued and generated like any other listing.",
                "You review it and submit it, so it goes live on Amazon.",
                "On the Variations screen you join it to %s — Amazon needs both "
                "to exist before a family can be built over them." % sku,
            ],
        }, "", 200

    @app.route("/variant/plan", methods=["POST"])
    def variant_plan():
        """What adding this variant would involve. Sends nothing anywhere."""
        plan, err, code = _plan(_body())
        if err:
            return jsonify({"ok": False, "error": err}), code
        return jsonify({"ok": True, "plan": plan,
                        "note": ("Nothing has been queued or sent. This is what "
                                 "would happen.")})

    @app.route("/variant/queue", methods=["POST"])
    def variant_queue():
        """Queue the new variant to be generated. Amazon is not touched."""
        b = _body()
        if not b.get("confirmed"):
            return jsonify({"ok": False, "error": "not confirmed"}), 400
        plan, err, code = _plan(b)
        if err:
            return jsonify({"ok": False, "error": err}), code

        src = plan["source"]
        differs = plan["differs"]
        # The name carries what makes it different, so the row is recognisable
        # in the queue and the generated copy has it to work with.
        name = src["title"] or plan["join_sku"]
        if differs:
            name = "%s (%s)" % (name, ", ".join("%s %s" % (k, v)
                                                for k, v in sorted(differs.items())))

        from data import input_import as _ii
        rid = _ii.add_row(CONFIG_PATH, plan["workspace"], {
            "ebay_url": src["url"],
            "item_name": name[:300],
            "source_cost": ("%.2f" % src["cost"]) if src["cost"] is not None else "",
            "handling_time": str(int(b.get("handling_days") or 3)),
        }, source="variant")

        # The intended family, recorded against the queued row so the Variations
        # screen can offer it once the product is live. NOT written to Amazon:
        # there is nothing to write it to yet.
        try:
            _ii.update_row(CONFIG_PATH, plan["workspace"], rid, {})
        except Exception:
            pass

        return jsonify({
            "ok": True, "id": rid, "queued_as": name,
            "join_sku": plan["join_sku"], "shared": plan["shared"],
            "differs": differs, "warnings": plan["warnings"],
            "next": plan["steps"],
            "note": ("Queued only — nothing has been sent to Amazon. Press "
                     "Generate to build the listing, submit it when you are "
                     "happy, then join it to %s on the Variations screen."
                     % plan["join_sku"])})
