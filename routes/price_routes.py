"""routes/price_routes.py -- change a live listing's selling price from the app.

    POST /listing/price/preview   what would change, and what it does to profit
    POST /listing/price/apply     send exactly what preview showed

WHY THIS IS NOT A ONE-LINE PATCH
purchasable_offer is not a number. It is a nest of marketplace, audience,
currency and a dated schedule, and the shape differs by product type. Writing a
minimal one of our own invention REPLACES what Amazon holds -- so the currency,
the audience and any scheduled pricing go with it. There is already a builder
that gets this right: domain/source_apply.build_patches deep-copies the offer
Amazon returned and changes only the number inside it, so the shape sent is
always one Amazon has already accepted for that product (CLAUDE.md Rule 4).
This calls THAT rather than composing a second opinion (Rule 12).

WHAT IT REFUSES
A price below what the product costs to sell. floor_price in listing/pricing.py
is the app's single pricing rule -- source cost plus Amazon's fees plus shipping,
ads and a minimum profit -- and selling under it loses money on every unit. The
refusal is not absolute: you can confirm past it deliberately, because clearance
is a real thing. What you cannot do is walk into it without being told.
"""
from flask import request, jsonify

from routes import scope as _scope_mod


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /listing/price/* to the app."""

    def _load_account(aid):
        """The account record for an id the PAGE named -- credentials included.

        Without this the price screen read the id from the request and the
        CREDENTIALS from the server's global, which is how a price could be
        aimed at the wrong seller account.
        """
        try:
            import accounts as _acc_mod
            return _acc_mod.get_account(_cfg(), aid, CONFIG_PATH)
        except Exception:
            return None

    def _scope():
        b = request.get_json(silent=True) or {}
        return _scope_mod.resolve(
            state=_state, account=_active_account() or {},
            asked_id=b.get("id") or b.get("account_id"),
            asked_marketplace=b.get("marketplace"),
            load_account=_load_account)

    def _body():
        return request.get_json(silent=True) or {}

    def _live(sku, acc, mkt):
        """What Amazon currently holds for this SKU. None means it would not say.

        Read live, never from a cache: a price is being changed, and changing it
        from a stale copy of the offer is how a scheduled price or a currency
        gets quietly dropped.
        """
        from api import amazon_listings as _al
        from domain import accounts as _acc_mod
        try:
            res = _al.get_item(_acc_mod.account_creds(acc or {}), mkt,
                               str((acc or {}).get("seller_id") or ""), sku,
                               _acc_mod.marketplace_id(mkt))
        except Exception as e:
            # WHY it would not answer is the whole of what the person needs.
            # This caught everything and returned None, so a temporary rate
            # limit, an unauthorised app and a SKU that does not exist all
            # produced the same sentence -- "Amazon would not return X" -- and
            # none of them told anyone what to do next. Reported as
            # "i am also not able to change selling price from the app".
            _live.last_error = str(e)[:300]
            return None
        if not res or res.get("status") != _al.OK:
            _live.last_error = str((res or {}).get("error")
                                   or (res or {}).get("status") or "")[:300]
            return None
        _live.last_error = ""
        return {"attributes": res.get("attributes") or {},
                "productType": res.get("product_type") or ""}

    _live.last_error = ""

    def _why_no_live(sku):
        """The refusal, said so somebody can act on it."""
        raw = str(getattr(_live, "last_error", "") or "")
        low = raw.lower()
        if "quotaexceeded" in low or "throttl" in low or "429" in low:
            return ("Amazon is rate-limiting us at the moment, so %s's current "
                    "price could not be read. Nothing is wrong with the listing "
                    "— try again in a minute." % sku)
        if "unauthor" in low or "forbidden" in low or "accessdenied" in low:
            return ("This account's Amazon app is not authorised to read %s. "
                    "Re-authorise it in Seller Central with the Product Listing "
                    "role, then try again." % sku)
        if "notfound" in low or "not found" in low or "404" in low:
            return ("Amazon has no listing with the SKU %s on this marketplace, "
                    "so there is no price to change." % sku)
        return ("Amazon would not return %s, so its current price could not be "
                "read — and a price is never changed without reading what it is "
                "now.%s" % (sku, (" Amazon said: %s" % raw[:160]) if raw else ""))

    def _current_price(attrs):
        """The price in the offer as it stands, or None."""
        for off in (attrs.get("purchasable_offer") or []):
            for entry in (off.get("our_price") or []):
                for sched in (entry.get("schedule") or []):
                    for k in ("value_with_tax", "value"):
                        if sched.get(k) is not None:
                            try:
                                return float(sched[k])
                            except (TypeError, ValueError):
                                return None
        return None

    def _floor_for(sku, acc, mkt, price):
        """The lowest this may go before it stops making money. (floor, why).

        THE ACCOUNT'S OWN RULE, not a hardcoded one.

        This called floor_from_rate(cost, 0.15) directly, which ignored every
        setting the owner had made -- their measured referral rate, their postage
        and ads allowances, their minimum return -- and quietly assumed a flat
        15% and the old built-in 3.00/2.00/1.00. Those defaults are 0.00 now, so
        the same call returns cost/(1-rate), which is BREAK-EVEN, and a warning
        built on it would tell someone a price was safe when it earns nothing.

        domain/sourcing.floor_price is the one function that turns a cost and a
        rule into a floor, and it is what the repricer prices with. Using it here
        means the number this screen warns about and the number the repricer
        works to are the same number (Rule 12).
        """
        from domain import cogs as _cogs
        cost = None
        try:
            cost = _cogs.cost_from_sku(sku)
        except Exception:
            cost = None
        if cost is None:
            return None, ("This SKU records no source cost, so there is no floor "
                          "to check the new price against.")
        try:
            from domain import source_repo as _repo
            from domain import sourcing as _sourcing
            rule = None
            try:
                rule = _repo.rule_for(CONFIG_PATH, (acc or {}).get("id") or "",
                                      mkt, sku)
            except Exception:
                rule = None
            floor = _sourcing.floor_price(cost, rule)
            if floor is None:
                return None, ("This account has no profit requirement set, so "
                              "there is no floor to check against. Set a margin "
                              "or ROI target in the repricer to get one.")
            return float(floor), ""
        except Exception as e:
            return None, "The floor could not be worked out (%s)." % str(e)[:80]


    @app.route("/listing/price/preview", methods=["POST"])
    def listing_price_preview():
        """What changing this price would do. Sends nothing."""
        b = _body()
        acc, wsid, mkt = _scope()
        sku = str(b.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        if not mkt:
            return jsonify({"ok": False, "error": _scope_mod.NO_MARKETPLACE}), 400
        try:
            new_price = float(b.get("price"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "that is not a price"}), 400
        if new_price <= 0:
            return jsonify({"ok": False, "error": (
                "A price of zero or less is not a price. To stop selling "
                "something, set its stock to zero instead.")}), 400

        live = _live(sku, acc, mkt)
        if live is None:
            # The REASON, not a shrug -- a rate limit, a missing
            # authorisation and a SKU that does not exist all produced the
            # same sentence, and none of them said what to do. See
            # _why_no_live.
            return jsonify({"ok": False, "error": _why_no_live(sku)}), 502

        attrs = live.get("attributes") or {}
        now = _current_price(attrs)
        floor, why = _floor_for(sku, acc, mkt, new_price)

        from domain import accounts as _acc_mod
        from domain import source_apply as _apply
        patches, err = _apply.build_patches(
            attrs, {"price": new_price}, _acc_mod.marketplace_id(mkt))
        if err:
            return jsonify({"ok": False, "error": err}), 400

        # WARNINGS ARE FOR THINGS THAT ARE ACTUALLY WRONG.
        #
        #     "why is it giving me fake and wrong warnings ... i do not know
        #      about which floor is it talking about. i was increasing the price,
        #      not decreasing it."
        #
        # Three things were being reported as warnings that are not warnings:
        #
        #   * "this SKU records no source cost, so there is no floor" -- true of
        #     every hand-named SKU, and it is a fact about the setup, not a
        #     danger in this change. It is a NOTE now.
        #   * the floor text named "postage and advertising" as though they had
        #     been deducted. They are 0.00 unless the owner sets them, so the
        #     sentence described money that had not been counted.
        #   * a large move was flagged in BOTH directions with the same wording,
        #     "usually a typo -- check the decimal point", on a deliberate price
        #     rise. Raising a price is the ordinary thing this screen is for.
        #
        # So: warnings only when money is at risk, notes for everything else, and
        # the two are kept apart in the reply so the screen can show them
        # differently.
        warn, notes = [], []
        if floor is not None and new_price < floor:
            warn.append(
                "%.2f is below this product's floor of %.2f — the least it can "
                "sell for and still meet your profit rule once the stock and "
                "Amazon's fees are paid. Every unit sold at %.2f gives up about "
                "%.2f against that."
                % (new_price, floor, new_price, floor - new_price))
        elif why:
            notes.append(why)
        elif floor is not None:
            notes.append("Above this product's floor of %.2f, so it still meets "
                         "your profit rule." % floor)
        if now is not None and now > 0:
            move = (new_price - now) / now * 100.0
            # A CUT is the direction worth questioning: it is the one that can
            # lose money on every unit, and the one a misplaced decimal point
            # produces. A rise is stated, not warned about.
            if move <= -30:
                warn.append("That cuts the price by %.0f%%, from %.2f to %.2f. "
                            "A drop that size is usually a misplaced decimal "
                            "point." % (abs(move), now, new_price))
            elif move >= 30:
                notes.append("That raises the price by %.0f%%, from %.2f to %.2f."
                             % (move, now, new_price))
        return jsonify({"ok": True, "sku": sku, "marketplace": mkt,
                        "current": now, "new": new_price, "floor": floor,
                        "warnings": warn, "notes": notes, "patches": patches,
                        "product_type": live.get("productType") or "",
                        "note": ("Nothing has been sent. This is exactly what "
                                 "would be.")})

    @app.route("/listing/price/apply", methods=["POST"])
    def listing_price_apply():
        """Send it. Requires the confirmation the preview asked for."""
        b = _body()
        acc, wsid, mkt = _scope()
        sku = str(b.get("sku") or "").strip()
        if not b.get("confirmed"):
            return jsonify({"ok": False, "error": "not confirmed"}), 400
        if not (sku and mkt):
            return jsonify({"ok": False, "error": "need a sku and a marketplace"}), 400
        try:
            new_price = float(b.get("price"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "that is not a price"}), 400

        # PUBLISHING, so the publish gate applies -- this changes what buyers pay
        # on a real listing.
        from domain import accounts as _acc_mod
        if not _acc_mod.seller_scope_allowed(acc or {}):
            return jsonify({"ok": False, "error": (
                "%s has no Amazon account of its own, so nothing here can change "
                "a live price." % ((acc or {}).get("label") or wsid))}), 400

        live = _live(sku, acc, mkt)
        if live is None:
            return jsonify({"ok": False, "error": (
                "Amazon would not return %s, so nothing was sent." % sku)}), 502
        attrs = live.get("attributes") or {}
        was = _current_price(attrs)

        from domain import source_apply as _apply
        mkt_id = _acc_mod.marketplace_id(mkt)
        patches, err = _apply.build_patches(attrs, {"price": new_price}, mkt_id)
        if err:
            return jsonify({"ok": False, "error": err}), 400

        floor, _why = _floor_for(sku, acc, mkt, new_price)
        if floor is not None and new_price < floor and not b.get("below_floor_ok"):
            # Refused SERVER-side as well as warned about in the browser: a
            # dialog someone clicked through is not a control.
            return jsonify({"ok": False, "below_floor": True, "floor": floor,
                            "error": ("%.2f is below the %.2f floor for this "
                                      "product. Send below_floor_ok to price it "
                                      "there deliberately."
                                      % (new_price, floor))}), 400

        from api import amazon_listings as _al
        res = _al.patch(_acc_mod.account_creds(acc or {}), mkt,
                        str((acc or {}).get("seller_id") or ""), sku, mkt_id,
                        live.get("productType") or "", patches,
                        issue_locale=("en_US" if mkt == "US" else "en_GB"))
        if res["status"] != _al.OK:
            why = res.get("error") or "Amazon rejected it"
            if res.get("issues"):
                why += " -- " + "; ".join(str(i.get("message") or "")[:140]
                                          for i in res["issues"][:3])
            return jsonify({"ok": False, "error": why}), 502

        # Recorded in the same place the repricer records its own changes, so one
        # history answers "why did this price move" whoever moved it.
        try:
            from domain import source_repo as _repo
            _repo.record_action(CONFIG_PATH, wsid, mkt, sku,
                                {"price": new_price, "reason": "changed by hand"},
                                applied=1, error="")
        except Exception:
            pass

        return jsonify({"ok": True, "sku": sku, "was": was, "now": new_price,
                        "submission_id": res.get("submission_id"),
                        "note": ("Amazon usually shows a new price within a few "
                                 "minutes.")})
