"""routes/variations_routes.py -- merge SKUs into a variation family.

Two endpoints, and the split between them is the whole safety story:

    /variations/preview   decides and explains. Sends nothing.
    /variations/apply     sends exactly what preview showed.

Both build the payload with the SAME listing/variations.build(), so the screen
cannot show one thing and Amazon receive another. Every rule -- what makes a
merge refusable, which themes a product type allows -- lives in that module;
this file supplies the data and does the sending.

WHY APPLY GOES PARENT FIRST
A child naming a parent that does not exist yet is rejected. So the parent is
created and confirmed accepted before any child is touched, and if it fails
nothing else is sent -- rather than half a family existing, which is the state
Amazon accepts silently and which makes products vanish from search.
"""
from flask import request, jsonify

from listing import variations as _var
from routes import scope as _scope_mod


def _skus_first(v):
    """The first SKU out of Amazon's parentSkus/childSkus list, or ""."""
    if isinstance(v, str):
        return v.strip()
    for x in (v or []):
        x = str(x or "").strip()
        if x:
            return x
    return ""


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state, _sp_creds,
             _schema_for=None, _public_media_url=lambda u: ""):
    """Attach /variations/* to the app."""

    def _scope():
        acc = _active_account() or {}
        wsid = str(acc.get("id") or _state.get("active_account_id") or "")
        # Same resolution as every other screen, from routes/scope.py: this one
        # stopped at active_marketplace, which is only set when a marketplace has
        # been CHOSEN, and Variations is not where you choose one.
        mkt = _scope_mod.marketplace(
            state=_state, account=acc,
            asked=(request.args.get("marketplace")
                   or (request.get_json(silent=True) or {}).get("marketplace")))
        return acc, wsid, mkt

    def _body():
        return request.get_json(force=True, silent=True) or {}

    def _live_items(wsid, mkt):
        try:
            from domain import live_snapshots as _ls
            return ((_ls.get(CONFIG_PATH, wsid, mkt) or {}).get("items") or [])
        except Exception:
            return []

    # WHICH KEY HOLDS THE VALUE, per wrapper Amazon uses.
    #
    # "media_location" is the image one, and leaving it out is why every image
    # slot on the picker read "empty" for a listing that had five images on it.
    # MEASURED on a live UK listing:
    #
    #   main_product_image_locator:
    #     [{"media_location": "https://m.media-amazon.com/images/I/61qid...jpg",
    #       "marketplace_id": "A1F83G8C2ARO7P"}]
    #
    # That is the dangerous direction to get wrong: the picker uses this to warn
    # that a slot already has an image, and sending to an occupied slot replaces
    # it with no copy kept by Amazon. Reading "empty" would have let someone
    # destroy an image without being asked.
    _VALUE_KEYS = ("value", "name", "media_location")

    def _one(attrs, key):
        """An attribute's plain value, whatever wrapper Amazon put it in."""
        v = (attrs or {}).get(key)
        if isinstance(v, list) and v:
            f = v[0]
            if isinstance(f, dict):
                for k in _VALUE_KEYS:
                    if k in f:
                        return str(f[k])
                return ""
            return str(f)
        if isinstance(v, dict):
            for k in _VALUE_KEYS:
                if k in v:
                    return str(v[k])
        return str(v) if v not in (None, "") else ""

    def _live_attributes(sku, wsid, mkt):
        """What Amazon holds for this SKU right now, flattened for the checker.

        None means it could not be read -- which is reported as such rather than
        as an empty listing, because "no brand" and "could not read the brand"
        lead to opposite decisions.
        """
        from api import amazon_listings as _al
        from domain import accounts as _acc_mod
        acc = _active_account() or {}
        got = _al.get_item(_acc_mod.account_creds(acc), mkt,
                           str(acc.get("seller_id") or ""), sku,
                           _acc_mod.marketplace_id(mkt))
        if got["status"] != _al.OK:
            return None
        a = got.get("attributes") or {}
        flat = {}
        for k, v in a.items():
            val = _one(a, k)
            if val:
                flat[k] = val
        # WHAT AMAZON SERVES, from its own summary of the listing, and the
        # things it is unhappy about. Both come back on the call that was
        # already being made, and both are what makes "did my image land"
        # answerable inside the app instead of in Seller Central.
        summaries = got.get("summaries") or []
        s0 = summaries[0] if (summaries and isinstance(summaries[0], dict)) else {}
        mi = s0.get("mainImage") or {}
        issues = [{"message": str(i.get("message") or ""),
                   "severity": str(i.get("severity") or "")}
                  for i in (got.get("issues") or []) if isinstance(i, dict)]
        return {"sku": sku,
                "product_type": got.get("product_type") or "",
                "brand": _one(a, "brand"),
                "item_type_keyword": _one(a, "item_type_keyword"),
                "parent_sku": _one(a, "child_parent_sku_relationship"),
                "title": _one(a, "item_name"),
                "shopper_image": (mi.get("link") or "") if isinstance(mi, dict) else "",
                "issues": issues,
                "attributes": flat,
                # AMAZON'S OWN SHAPE, KEPT. `flat` is for the checker, which
                # compares values as text; the parent has to be WRITTEN, and a
                # flattened "AltaboltaVoo" is not what goes back up --
                # [{"value": "AltaboltaVoo", "language_tag": "en_GB",
                #   "marketplace_id": "A1F83G8C2ARO7P"}] is. Copying what came
                # down is how the parent is built without guessing at wrappers
                # (CLAUDE.md Rule 4).
                "raw": a}

    def _schema(pt, mkt):
        """The product type's live schema, for the themes it allows.

        None means we could not fetch it -- which is reported as "could not
        check" rather than silently skipping the check, because a theme the type
        does not allow is accepted by Amazon and then ignored.

        THE FULL SCHEMA, DELIBERATELY. The parent schema below is smaller and
        wrong for this job: Amazon drops colour, size, material, pattern and
        every other varying attribute from it -- 29 of SQUEEGEE's 112. The theme
        checker asks "does this product type HAVE a colour attribute", and asked
        of the parent schema the answer is no, for every axis, so every theme on
        every type would come back unusable.
        """
        if not _schema_for:
            return None
        try:
            return _schema_for(pt, mkt)
        except Exception:
            return None

    def _parent_schema(pt, mkt):
        """The schema for the PARENT listing specifically, or None.

        Amazon's parentageLevel=PARENT resolves the conditional logic down to
        what a variation container actually is. Two things come out of it that
        the standalone schema cannot answer:

          what the parent MUST carry   its own `required` list -- SQUEEGEE's is
                                       the standalone six plus variation_theme
                                       and child_parent_sku_relationship
          what a parent cannot have    no product identifier and no exemption
                                       field, so neither is sent

        None when it could not be fetched, and the caller then falls back to the
        standalone list rather than guessing -- the same "could not check"
        honesty as _schema above. It never silently substitutes one for the
        other: they are different lists and using the wrong one is the bug this
        whole change is about.
        """
        if not _schema_for:
            return None
        try:
            return _schema_for(pt, mkt, "PARENT")
        except TypeError:
            # A fetcher injected before parentage existed. Asking it for the
            # parent schema and being handed the standalone one back would be
            # worse than not asking, so this says so instead.
            return None
        except Exception:
            return None

    def _parent_required(pt, mkt):
        """(required list, whether it is the parent's own). Never raises."""
        ps = _parent_schema(pt, mkt)
        if ps is not None:
            return _var.required_from_schema(ps), True
        return _var.required_from_schema(_schema(pt, mkt)), False

    @app.route("/variations/families")
    def variations_families():
        """The parent/child families that already exist, as Amazon holds them.

            "ALSO I WANT MY APP TO SHOW the parents and child relation like we
             have in amazon."

        Read-only, and read from the stored snapshot rather than from Amazon --
        the relationships are collected on the pass that already visits every
        SKU for its thumbnail, so this costs nothing and answers instantly.

        Everything else on this screen CREATES a family. This is the half that
        shows you the ones you have.
        """
        from domain import families as _fam

        # _scope() here returns THREE values -- the account object as well as
        # its id and marketplace. Every other route in this file unpacks three;
        # this one unpacked two and failed with "too many values to unpack",
        # which reads like a data problem rather than a typo.
        _acc, wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400
        try:
            out = _fam.for_account(CONFIG_PATH, wsid, mkt)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:300]}), 500
        return jsonify({"ok": True, **out})

    @app.route("/variations/candidates")
    def variations_candidates():
        """The account's live listings, with what they vary by, for picking from."""
        _acc, wsid, mkt = _scope()
        q = (request.args.get("q") or "").strip().lower()

        # THE PRODUCT TYPE, WHICH THE SNAPSHOT DOES NOT CARRY.
        #
        # This screen dead-ended here. The live snapshot holds sku, asin, price,
        # image and so on but NO product type, so every candidate came back with
        # product_type "" -- and step 2 asks /variations/themes for the themes a
        # product type allows, which answered "no product type", left the
        # dropdown empty, and stopped the flow dead with nothing on screen
        # explaining why.
        #
        # The app already knows: every one of the 55 listings has a product_type
        # in its own table. Joining it here costs one query instead of 55 calls
        # to Amazon.
        types = {}
        try:
            from data import db as _db
            for r in _db.get_db(CONFIG_PATH).execute(
                    "SELECT sku, product_type FROM listings WHERE workspace_id=? "
                    "AND product_type IS NOT NULL AND product_type<>''",
                    (wsid,)):
                types[str(r["sku"])] = str(r["product_type"])
        except Exception:
            types = {}

        out = []
        for it in _live_items(wsid, mkt):
            sku = str(it.get("sku") or "").strip()
            if not sku:
                continue
            title = str(it.get("title") or "")
            if q and q not in sku.lower() and q not in title.lower():
                continue
            out.append({"sku": sku, "asin": str(it.get("asin") or ""),
                        "title": title, "price": it.get("price"),
                        # Deciding which products are the same thing in different
                        # colours is a VISUAL judgement. Doing it from SKUs like
                        # 10.06_3Days_B0081ZHHTS is guesswork, and a wrong family
                        # does not fail loudly -- Amazon accepts it and the
                        # products quietly stop appearing.
                        "img": str(it.get("img") or ""),
                        # Snapshot first (if it ever gains one), then the app's
                        # own record. "" only when neither knows, which the
                        # screen can now resolve live rather than giving up.
                        "product_type": (str(it.get("product_type") or "")
                                         or types.get(sku, "")),
                        # Already in a family? Then it is not free to join
                        # another. This read `parent_sku` -- singular -- which
                        # nothing has ever written, so the "already in a family"
                        # chip on this screen has been dead since it was added.
                        # Amazon's field is parentSkus, a LIST, and it is now
                        # stored on the snapshot as parent_skus.
                        "parent_sku": (_skus_first(it.get("parent_skus"))
                                       or str(it.get("parent_sku") or "")),
                        "variation_theme": str(it.get("variation_theme") or "")})
        out.sort(key=lambda r: r["sku"])
        # An empty list has more than one cause and they need different actions.
        # "Press Sync" is the wrong advice when the real problem is that no
        # marketplace was resolved -- which is what this screen used to do, on an
        # account with 55 listings already cached.
        note = ""
        if not out:
            if not mkt:
                note = ("No marketplace could be worked out for this account, so "
                        "there is nothing to list. Pick one at the top, or set the "
                        "account's default marketplace under Settings.")
            elif q:
                note = "Nothing matches %r in %s." % (q, mkt)
            else:
                note = ("No live listings are cached for %s yet — press Sync on "
                        "the Listings screen first." % (mkt or "this account"))
        return jsonify({"ok": True, "items": out, "count": len(out),
                        "marketplace": mkt, "note": note})

    @app.route("/listing/image_slots")
    def listing_image_slots():
        """Which image slots this listing has, and what is in each one now.

        Lives beside the variation routes because both answer the same kind of
        question -- "what does the schema say this product type supports" -- and
        both read the live listing rather than a cache. What is IN a slot matters
        as much as which slots exist: sending to an occupied one replaces its
        image and Amazon keeps no copy, so the screen has to be able to say so
        before the click rather than after.
        """
        from listing import images as _img
        _acc, wsid, mkt = _scope()
        sku = (request.args.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400

        # A DRAFT HAS SLOTS TOO, AND IT IS THE ONE BEING FILLED IN.
        #
        # This read the live listing and answered 502 when Amazon did not have
        # the SKU -- which is every listing that has not been submitted yet, and
        # those are exactly the ones somebody is choosing images for. The
        # product type is enough to answer "which slots does Amazon allow",
        # because that question is about the TYPE and not about the listing:
        # slots_from_schema reads the schema and nothing else.
        #
        # So the live read is still made and still preferred -- what is IN a
        # slot on a live listing can only come from Amazon -- and its absence is
        # reported as `live: false` rather than as a failure. The caller passes
        # the row's product type for the draft case.
        asked_pt = (request.args.get("product_type") or "").strip()
        live = _live_attributes(sku, wsid, mkt)
        if live is None and not asked_pt:
            return jsonify({"ok": False, "error": (
                "Amazon would not return %s and no product type was given, so "
                "its image slots could not be worked out." % sku)}), 502

        pt = (live or {}).get("product_type") or asked_pt
        sch = _schema(pt, mkt)
        if sch is None:
            return jsonify({"ok": True, "sku": sku, "product_type": pt,
                            "slots": [], "checked": False,
                            "note": ("Could not read this product type's schema, "
                                     "so its image slots are unknown. Amazon "
                                     "rejects a slot a type does not have.")})

        attrs = (live or {}).get("attributes") or {}
        slots = []
        for s in _img.slots_from_schema(sch):
            cur = attrs.get(s["key"]) or ""
            slots.append({**s, "current": cur, "occupied": bool(cur)})
        return jsonify({"ok": True, "sku": sku, "product_type": pt,
                        "slots": slots, "checked": True,
                        # WHETHER `current` MEANS ANYTHING. On a draft there is
                        # no live listing to read, so every slot comes back
                        # empty -- which is not the same as Amazon holding
                        # nothing, and the screen must not say it is.
                        "live": live is not None,
                        # WHAT A SHOPPER ACTUALLY SEES, which is a different
                        # question from what is in a slot. Amazon re-hosts and
                        # re-renders the main image, so this URL never matches
                        # the one that was submitted even when it is the same
                        # photograph -- and the app has no business claiming a
                        # slot value IS the product page picture.
                        "shopper_image": (live or {}).get("shopper_image") or "",
                        # An image Amazon accepted and then rejected shows up
                        # here and nowhere else.
                        "issues": (live or {}).get("issues") or [],
                        "is_variation_child": bool((live or {}).get("parent_sku")),
                        "note": ("" if slots else
                                 "This product type defines no image slots at "
                                 "all, which would be unusual — check the "
                                 "product type is right.")})

    @app.route("/listing/image_push", methods=["POST"])
    def listing_image_push():
        """Send one image to one named slot. Refuses what Amazon cannot fetch."""
        from listing import images as _img
        from api import amazon_listings as _al
        from domain import accounts as _acc_mod

        b = _body()
        acc, wsid, mkt = _scope()
        sku = (b.get("sku") or "").strip()
        slot = (b.get("slot") or "").strip()
        url = (b.get("url") or "").strip()
        if not b.get("confirmed"):
            return jsonify({"ok": False, "error": "not confirmed"}), 400
        if not (sku and slot):
            return jsonify({"ok": False, "error": "need a sku and a slot"}), 400

        # AN IMAGE IN THIS APP'S OWN LIBRARY IS ALREADY PUBLISHABLE.
        #
        # Amazon fetches the image itself, over the open internet, so a
        # "/media/..." path is no use to it -- that much was already checked.
        # What was missing is that this app SERVES those files publicly, at
        # /img/<token>/<path>, login-exempt and HMAC-signed so the media tree
        # cannot be enumerated. The older push route has converted paths that
        # way for a long time; the slot picker did not, so it refused every
        # image the app had generated and told people to put it in Google Drive
        # first -- for a file the server was already able to hand Amazon.
        #
        # Converted here, before the check, so the check now only fails on
        # something genuinely unreachable.
        if url.startswith("/media/"):
            pub = ""
            try:
                pub = _public_media_url(url) or ""
            except Exception:
                pub = ""
            if not pub:
                return jsonify({"ok": False, "error": (
                    "This image is in the app's library, but the app does not "
                    "know its own public address, so Amazon could not be told "
                    "where to fetch it. Set PUBLIC_BASE_URL to the address this "
                    "app is served on and try again.")}), 400
            url = pub

        bad = _img.check_url(url)
        if bad:
            return jsonify({"ok": False, "error": bad}), 400
        # What the app MADE this image for. The browser sends it, but the refusal
        # is decided here -- a dropdown cannot be trusted to have withheld an
        # option, and this one stops a listing being suppressed.
        bad = _img.refuse_slot(slot, b.get("made_as") or "")
        if bad:
            return jsonify({"ok": False, "error": bad}), 400

        live = _live_attributes(sku, wsid, mkt)
        if live is None:
            return jsonify({"ok": False, "error": (
                "Amazon would not return %s, so nothing was sent." % sku)}), 502
        pt = live.get("product_type") or ""
        sch = _schema(pt, mkt)
        if sch is not None:
            allowed = {s["key"] for s in _img.slots_from_schema(sch)}
            if slot not in allowed:
                # Re-checked against the schema, not trusted from the dropdown:
                # a slot this type does not define is rejected by Amazon with an
                # error that does not name the slot.
                return jsonify({"ok": False, "error": (
                    "%s is not an image slot %s has." % (slot, pt))}), 400

        mkt_id = _acc_mod.marketplace_id(mkt)
        res = _al.patch(_acc_mod.account_creds(acc or {}), mkt,
                        str((acc or {}).get("seller_id") or ""), sku, mkt_id, pt,
                        [_img.build_patch(slot, url, mkt_id)],
                        issue_locale=("en_US" if mkt == "US" else "en_GB"))
        if res["status"] != _al.OK:
            why = res["error"] or "Amazon rejected it"
            if res["issues"]:
                why += " -- " + "; ".join(str(i.get("message") or "")[:140]
                                          for i in res["issues"][:3])
            return jsonify({"ok": False, "error": why}), 502
        return jsonify({"ok": True, "slot": slot, "sku": sku,
                        "submission_id": res["submission_id"],
                        "note": "Amazon usually shows a new image within a few minutes."})

    @app.route("/variations/themes")
    def variations_themes():
        """Which themes a product type allows, read from its live schema.

        Takes EITHER a product_type or the SKUs, and works out the type itself
        when only the SKUs are known. It used to demand the type and refuse with
        "no product type" when the screen did not have one -- and the screen
        frequently did not, because the source it read from carries no type.
        Refusing to answer a question the caller cannot phrase is how a flow
        stops dead with nothing on screen to explain it.
        """
        acc, wsid, mkt = _scope()
        pt = (request.args.get("product_type") or "").strip()
        if not pt:
            skus = [s.strip() for s in
                    (request.args.get("skus") or "").split(",") if s.strip()]
            # 1. What the app already recorded.
            if skus:
                try:
                    from data import db as _db
                    row = _db.get_db(CONFIG_PATH).execute(
                        "SELECT product_type FROM listings WHERE workspace_id=? "
                        "AND sku=? AND product_type IS NOT NULL AND product_type<>''",
                        (wsid, skus[0])).fetchone()
                    if row:
                        pt = str(row["product_type"])
                except Exception:
                    pass
            # 2. Failing that, ask Amazon for the listing itself. One call, and
            #    only when the cheap answer was not there.
            if not pt and skus:
                live = _live_attributes(skus[0], wsid, mkt)
                pt = str((live or {}).get("product_type") or "")
        if not pt:
            return jsonify({"ok": False, "error": (
                "Could not work out what kind of product this is, so the "
                "groupings Amazon allows for it cannot be listed. Sync the "
                "Listings screen, or open the listing once so its product type "
                "is recorded.")}), 400
        sch = _schema(pt, mkt)
        if sch is None:
            return jsonify({"ok": True, "product_type": pt, "themes": [],
                            "checked": False,
                            "note": ("Could not read this product type's schema, so "
                                     "the theme cannot be checked against it. Amazon "
                                     "silently ignores a theme a type does not "
                                     "allow, so confirm it before applying.")})
        offered = _var.themes_from_schema(sch)
        # WHAT AMAZON OFFERS IS NOT THE SAME AS WHAT WORKS HERE.
        #
        # A theme names the attributes it groups by, and a type does not always
        # have them. MEASURED on OUTDOOR_LIVING: 10 themes offered, 5 of them
        # naming color_name / material_type / item_display_height, none of which
        # is an attribute of the type. Choosing one of those got the user a
        # refusal that read like their products were incomplete.
        #
        # They are still returned -- as `unusable`, with the reason -- rather
        # than dropped, because a theme vanishing from a list is not an
        # explanation, and someone looking for MATERIAL_TYPE needs to be told why
        # it is not on offer. Same treatment the deprecated themes get, one step
        # further on.
        attrs = _var.attribute_names(sch)
        themes, blocked = _var.split_themes(offered, attrs)
        note = ""
        if not offered:
            note = ("This product type has no variation theme in its schema, "
                    "which means it does not support variations at all.")
        elif not themes:
            note = ("Amazon offers %d groupings for %s, but every one of them "
                    "groups by an attribute this product type does not have, so "
                    "none can be used." % (len(offered), pt))
        elif blocked:
            note = ("%d of the %d groupings Amazon lists for %s are left out: "
                    "they group by an attribute this type does not have."
                    % (len(blocked), len(offered), pt))
        return jsonify({"ok": True, "product_type": pt, "themes": themes,
                        "checked": True,
                        "unusable": [{"theme": t,
                                      "missing": m,
                                      "why": ("%s has no %s attribute"
                                              % (pt, " or ".join(m)))}
                                     for t, m in blocked],
                        "note": note})

    @app.route("/variations/preview", methods=["POST"])
    def variations_preview():
        """What would be sent, and every reason it should not be. Sends nothing."""
        b = _body()
        _acc, wsid, mkt = _scope()
        parent_sku = (b.get("parent_sku") or "").strip()
        theme = (b.get("theme") or "").strip()
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]

        items = {str(i.get("sku") or "").strip(): i for i in _live_items(wsid, mkt)}
        children, missing, unreadable = [], [], []
        for s in skus:
            if s not in items:
                missing.append(s)
                continue
            # READ FROM AMAZON, not from the cached snapshot. The constraints a
            # family has to satisfy -- same brand, same item type keyword, values
            # that genuinely differ on the theme's axis -- are about what Amazon
            # HOLDS RIGHT NOW. A snapshot is what it held whenever it was last
            # synced, and merging on a stale brand produces a family Amazon
            # accepts and then does not show.
            live = _live_attributes(s, wsid, mkt)
            if live is None:
                unreadable.append(s)
                continue
            children.append(live)

        pt = next((c["product_type"] for c in children if c["product_type"]), "")
        if not parent_sku:
            parent_sku = _var.suggest_parent_sku(children, theme)

        problems = list(_var.check(parent_sku, children, theme,
                                   _schema(pt, mkt), pt))
        if missing:
            problems.insert(0, "Not in the cached catalogue: %s. Press Sync on the "
                               "Listings screen, then try again."
                               % ", ".join(missing))
        if unreadable:
            problems.insert(0, "Amazon would not return %s, so nothing about them "
                               "could be checked. Nothing is merged on data we "
                               "could not read." % ", ".join(unreadable))
        already = [c["sku"] for c in children if c.get("parent_sku")]
        if already:
            problems.append("%s already belong%s to another family. Amazon allows "
                            "one parent per child, so it would have to be removed "
                            "from that one first."
                            % (", ".join(already), "s" if len(already) == 1 else ""))

        # THE PARENT'S OWN ATTRIBUTES, WORKED OUT HERE AND SHOWN. Preview used to
        # build the parent with four attributes while apply built it with five,
        # so the screen could not have revealed that Amazon would reject it --
        # and it rejected every one. Both paths now call the same
        # parent_attributes(), so the preview IS what gets sent.
        from domain import accounts as _acc_mod
        mkt_id = _acc_mod.marketplace_id(mkt)
        # FROM THE PARENT'S OWN SCHEMA. Built against the standalone list, the
        # parent was borrowing towards six attributes when Amazon's parent
        # schema asks for eight -- and claiming a GTIN exemption on a field that
        # does not exist at this parentage level.
        _req, _req_is_parent = _parent_required(pt, mkt)
        pa = _var.parent_attributes(children, theme,
                                    title=(b.get("parent_title") or ""),
                                    marketplace_id=mkt_id,
                                    extra=(b.get("parent_attributes") or {}),
                                    required=_req)
        payload = _var.build(parent_sku, children, theme, pt,
                             parent_attributes=pa["attributes"])
        if pa["unresolved"]:
            problems.append(
                "The parent listing still needs %s, and neither product has a "
                "value to take it from. Amazon rejects a parent that is missing "
                "what the product type requires."
                % ", ".join(pa["unresolved"]))
        return jsonify({"ok": True, "can_apply": not problems,
                        "problems": problems, "payload": payload,
                        "parent_sku": parent_sku, "product_type": pt,
                        # WHICH SCHEMA THE PARENT WAS BUILT AGAINST. A preview
                        # that cannot say whether it read the parent's own
                        # requirements or fell back to the standalone ones is a
                        # preview of something the reader cannot check.
                        "parent_schema": ("parent" if _req_is_parent
                                          else "standalone (parent schema "
                                               "could not be fetched)"),
                        "parent_required": _req,
                        "parent_inherited": pa["inherited"],
                        "parent_differ": pa["differ"],
                        "parent_borrowed": pa["borrowed"],
                        "parent_image_from": pa["images_from"],
                        "children": [{k: v for k, v in c.items() if k != "raw"}
                                     for c in children]})

    @app.route("/variations/apply", methods=["POST"])
    def variations_apply():
        """Create the parent, then point the children at it. Stops on the first failure."""
        from api import amazon_listings as _al
        from domain import accounts as _acc_mod

        b = _body()
        acc, wsid, mkt = _scope()
        if not b.get("confirmed"):
            return jsonify({"ok": False, "error": "not confirmed"}), 400

        parent_sku = (b.get("parent_sku") or "").strip()
        theme = (b.get("theme") or "").strip()
        title = (b.get("parent_title") or "").strip()
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]

        # Re-read from AMAZON, exactly as preview did. Re-checking against a
        # cached snapshot instead would make this weaker than the check it is
        # meant to repeat -- which would let through precisely the merges preview
        # refused, and only when something had changed since.
        children, unread = [], []
        for s in skus:
            live = _live_attributes(s, wsid, mkt)
            if live is None:
                unread.append(s)
            else:
                children.append(live)
        if unread:
            return jsonify({"ok": False, "error": (
                "Amazon would not return %s, so nothing about them could be "
                "checked. Nothing is merged on data we could not read."
                % ", ".join(unread))}), 400
        pt = next((c["product_type"] for c in children if c["product_type"]), "")

        problems = _var.check(parent_sku, children, theme, _schema(pt, mkt), pt)
        already = [c["sku"] for c in children if c.get("parent_sku")]
        if already:
            problems.append("%s already belong%s to another family."
                            % (", ".join(already), "s" if len(already) == 1 else ""))
        if problems:
            # Not trusted from the preview: the browser could be showing one from
            # before someone changed something.
            return jsonify({"ok": False, "error": "; ".join(problems)}), 400

        creds = _acc_mod.account_creds(acc or {})
        mkt_id = _acc_mod.marketplace_id(mkt)
        seller = str((acc or {}).get("seller_id") or "")
        locale = "en_US" if mkt == "US" else "en_GB"

        # The SAME builder the preview used, against the SAME schema, so what
        # was shown is what is sent. The title is inside it, along with
        # everything the children agree on -- brand, country of origin,
        # dangerous goods, batteries -- without which Amazon rejected every
        # parent ever built. No GTIN exemption: the parent schema has no such
        # field (see listing/variations.parent_attributes).
        _req, _req_is_parent = _parent_required(pt, mkt)
        pa = _var.parent_attributes(children, theme, title=title,
                                    marketplace_id=mkt_id,
                                    extra=(b.get("parent_attributes") or {}),
                                    required=_req)
        if pa["unresolved"]:
            return jsonify({"ok": False, "stage": "parent", "error": (
                "The parent listing still needs %s and neither product has a "
                "value to take it from. Nothing was sent."
                % ", ".join(pa["unresolved"])), "children_touched": 0}), 400
        pattrs = pa["attributes"]
        payload = _var.build(parent_sku, children, theme, pt,
                             parent_attributes=pattrs)

        res = _al.put(creds, mkt, seller, parent_sku, mkt_id, pt, pattrs,
                      issue_locale=locale)
        if res["status"] != _al.OK:
            why = res["error"] or "Amazon rejected the parent"
            if res["issues"]:
                why += " -- " + "; ".join(str(i.get("message") or "")[:140]
                                          for i in res["issues"][:3])
            # Nothing else is sent. Half a family is the state Amazon accepts in
            # silence and which makes the products disappear from search.
            return jsonify({"ok": False, "stage": "parent", "error": why,
                            "children_touched": 0}), 502

        done, failed = [], []
        for c in payload["children"]:
            patches = [{"op": "replace", "path": "/attributes/" + k, "value": v}
                       for k, v in c["attributes"].items()]
            r = _al.patch(creds, mkt, seller, c["sku"], mkt_id,
                          c["product_type"] or pt, patches, issue_locale=locale)
            if r["status"] == _al.OK:
                done.append(c["sku"])
            else:
                failed.append({"sku": c["sku"],
                               "error": (r["error"] or "rejected") + (
                                   " -- " + "; ".join(str(i.get("message") or "")[:120]
                                                      for i in r["issues"][:2])
                                   if r["issues"] else "")})

        return jsonify({"ok": not failed, "stage": "children",
                        "parent_sku": parent_sku,
                        "parent_submission": res["submission_id"],
                        "joined": done, "failed": failed,
                        "note": ("Amazon publishes variations asynchronously — the "
                                 "family usually appears within a few minutes. "
                                 + ("Some children were rejected and are NOT in the "
                                    "family; fix them and apply again."
                                    if failed else ""))})
