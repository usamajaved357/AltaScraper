"""routes/sourcing_routes.py -- the source repricer's screen.

Holds no decision logic of its own. Enrolment and sources come from
domain/source_repo.py, readings from domain/source_fetch.py, and every "what
would happen" answer from domain/source_run.py, which is the same code Phase D
will act on. That matters: the log this screen shows is not a preview built for
display, it is the actual decision, recorded.

Permissions are in auth/guard.py, not here. Reading the dry run is open to any
signed-in user because it is how you find out what the app is about to do;
everything that changes what it WILL do needs 'publish', which is the permission
for pushing changes to Amazon -- and that is precisely what enrolling a SKU
eventually causes.
"""
import json

from flask import request, jsonify, Response

from domain import source_apply as _apply
from domain import source_bulk as _bulk
from domain import source_drift as _drift
from domain import source_fetch as _fetch
from domain import source_repo as _repo
from domain import source_run as _run
from domain import sourcing as _sourcing


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state,
             _COGS_OVERRIDE=None):
    """Attach the /sourcing/* routes to the existing Flask app.

    _COGS_OVERRIDE is the same dict the listings screen edits. Optional, because
    the tests register this blueprint on their own; without it a SKU's cost falls
    back to the number in its name, which is what cogs.resolve() does anyway.
    """

    def _read_config():
        try:
            return json.load(open(CONFIG_PATH, encoding="utf-8"))
        except Exception:
            return {}

    def _write_config(raw):
        json.dump(raw, open(CONFIG_PATH, "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
        _state["cfg"] = None            # drop the cache so the switch takes effect

    def _creds_for(workspace_id, marketplace):
        """(creds, marketplace_id, seller_id) for one account.

        Read through domain/accounts.py, which every other Amazon call already
        uses -- a second way of assembling credentials here would eventually
        disagree with the one the rest of the app publishes through.
        """
        from domain import accounts as _acc
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        acc = None
        for a in (cfg.get("accounts") or []):
            if str(a.get("id")) == str(workspace_id):
                acc = a
                break
        if not acc:
            raise RuntimeError("no account called %s" % workspace_id)
        return (_acc.account_creds(acc), _acc.marketplace_id(marketplace),
                str(acc.get("seller_id") or ""))

    def _where():
        """(account_id, marketplace) for the request.

        The marketplace used to come only from the request or from
        _state["active_marketplace"], and neither is reliably set when this
        screen is opened directly -- the Repricer is not the screen that selects
        a marketplace, so opening it first left mkt as "". Everything then looked
        up jack_uk::"" , found nothing, and reported "no live listings cached",
        which is a completely different problem from the real one and sent you to
        press Sync on an account that had 55 listings already cached.

        So it now falls back, in order, to the account's default marketplace and
        then to the one that actually HAS a snapshot -- because a marketplace
        with cached listings is a better guess than none at all, and there is
        usually exactly one.
        """
        acc = _active_account() or {}
        body = request.get_json(silent=True) or {}
        wsid = (request.args.get("id") or body.get("id")
                or acc.get("id") or _state.get("active_account_id") or "")
        mkt = (request.args.get("marketplace") or body.get("marketplace")
               or _state.get("active_marketplace")
               or acc.get("default_marketplace") or "").upper()
        if not mkt and wsid:
            mkt = _only_marketplace_with_data(wsid)
        return wsid, mkt

    def _only_marketplace_with_data(wsid):
        """The marketplace this account has cached listings for, if just one.

        Deliberately only when there is exactly ONE. Picking the largest of
        several would be a guess that is right most of the time and silently
        wrong the rest, on a screen that changes live prices.
        """
        try:
            from domain import live_snapshots as _ls
            allrec = _ls._read_all(CONFIG_PATH) or {}
        except Exception:
            return ""
        found = []
        for key, rec in allrec.items():
            if "::" not in str(key):
                continue
            a, m = str(key).split("::", 1)
            if a == wsid and ((rec or {}).get("items") or []):
                found.append(m.upper())
        return found[0] if len(found) == 1 else ""

    def _body():
        return request.get_json(force=True, silent=True) or {}

    # ---- what is enrolled, and what would happen to it -------------------
    @app.route("/sourcing/list")
    def sourcing_list():
        """Everything the screen draws: enrolment, sources, readings, decisions."""
        from domain import catalogue as _cat
        wsid, mkt = _where()
        run = _run.dry_run(CONFIG_PATH, wsid, mkt, record=False)
        # WHICH PRODUCT EACH ROW IS. "i want to see the images of the items in
        # the repricer so it is easy to understand for which product are we
        # talking about" -- and a SKU like 10.39_3Days_B0F6LQ1S93 tells nobody.
        # From the shared lookup, so the picture here is the one the Listings
        # cards and the Orders rows show; built once for the whole list rather
        # than per row.
        idx = _cat.index(CONFIG_PATH, wsid, mkt)
        rows = []
        for d in run["decisions"]:
            pairs = _repo.pairs_for(CONFIG_PATH, d["workspace_id"],
                                    d["marketplace"], d["sku"])
            # The SKU's own rule travels with the row because min_price's ABSENCE
            # is what stops it being armed, and that belongs next to the Arm
            # button rather than in the error you get after pressing it.
            # What we think the unit cost vs what the supplier charges now. The
            # repricer never consults COGS to price -- this is here so the gap
            # between the two is visible instead of silent. Per source, the
            # readings behind it, so "has it moved" is answerable on the screen.
            srcs = []
            for s, c in pairs:
                srcs.append({**s, "check": c,
                             "history": _drift.price_history(CONFIG_PATH, s["id"])})
            _rule = _sourcing.rule_with_defaults(
                _repo.rule_for(CONFIG_PATH, d["workspace_id"],
                               d["marketplace"], d["sku"]))
            rows.append({**d, "sources": srcs,
                         "drift": _drift.for_sku(
                             _COGS_OVERRIDE, d["workspace_id"], d["sku"], pairs,
                             (d.get("decision") or {}).get("source_id")),
                         # What an order arriving right now would actually earn:
                         # today's supplier price against today's Amazon price.
                         "glance": _drift.at_a_glance(
                             pairs, d.get("current"), _rule,
                             (d.get("decision") or {}).get("source_id")),
                         "item": _cat.look(idx, d["sku"]),
                         "rule": _rule})
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "rows": rows, "counts": run["counts"],
                        "note": run["note"],
                        "master_enabled": _apply.is_enabled(_cfg),
                        "rule": _sourcing.rule_with_defaults(
                            _repo.rule_for(CONFIG_PATH, wsid, mkt, "")),
                        "defaults": _sourcing.DEFAULT_RULE})

    @app.route("/sourcing/template.csv")
    def sourcing_template():
        """The supplier-link sheet, already filled in with what we know.

        "give the user the template first filled by the asins enrolled for
         tracking in the repricer, the user will fill that template and upload
         it back to update the source links"

        So the only empty column is the one they are there to fill. A blank
        sheet means typing forty SKUs by hand, and a hand-typed SKU is the
        NO-SUCH-SKU-123 that domain/source_bulk already has a check for -- the
        real fix for which is not making anyone type them.

        Downloaded rather than posted anywhere: this reads and sends nothing.
        """
        from domain import catalogue as _cat
        wsid, mkt = _where()
        enrolled = [r["sku"] for r in _repo.enrolled(CONFIG_PATH, wsid, mkt)]

        # WHAT IS ALREADY ATTACHED, so a row that is done looks done. Someone
        # changing one supplier should be able to see the other forty are
        # already filled in and leave them alone, rather than wondering whether
        # a blank column means "none" or "we did not look".
        current = {}
        for sku in enrolled:
            urls = [str(s.get("url") or "")
                    for s, _c in _repo.pairs_for(CONFIG_PATH, wsid, mkt, sku)
                    if s.get("url")]
            if urls:
                current[sku] = urls[0]

        rows = _bulk.template_rows(CONFIG_PATH, wsid, mkt, enrolled,
                                   catalogue=_cat.index(CONFIG_PATH, wsid, mkt),
                                   current=current)
        body = _bulk.to_csv(_bulk.TEMPLATE_HEADERS, rows)
        name = "supplier-links-%s-%s.csv" % (wsid or "account", mkt or "")
        return Response(body, mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition":
                                 'attachment; filename="%s"' % name})

    @app.route("/sourcing/log")
    def sourcing_log():
        """The audit trail -- every decision, whether or not it was pushed."""
        wsid, mkt = _where()
        return jsonify({"ok": True, "actions": _repo.recent_actions(
            CONFIG_PATH, wsid, mkt, request.args.get("sku") or None,
            int(request.args.get("limit") or 200))})

    @app.route("/sourcing/candidates")
    def sourcing_candidates():
        """This account's live listings, with whether each is already enrolled.

        Read from the catalogue snapshot the app already holds, so enrolling is a
        matter of picking from what is actually on Amazon rather than typing a SKU
        from memory -- which is how a typo becomes a SKU that silently never
        matches anything and a repricer that appears to do nothing.
        """
        wsid, mkt = _where()
        try:
            from domain import live_snapshots as _ls
            rec = _ls.get(CONFIG_PATH, wsid, mkt) or {}
        except Exception:
            rec = {}
        enrolled = {r["sku"]: r for r in _repo.enrolled(CONFIG_PATH, wsid, mkt)}
        q = (request.args.get("q") or "").strip().lower()
        out = []
        for it in (rec.get("items") or []):
            sku = str(it.get("sku") or "").strip()
            if not sku:
                continue
            title = str(it.get("title") or "")
            if q and q not in sku.lower() and q not in title.lower():
                continue
            row = enrolled.get(sku)
            out.append({
                "sku": sku, "asin": str(it.get("asin") or ""), "title": title,
                # The picture, because a SKU is "10.06_3Days_B0081ZHHTS" and a
                # title is forty words of keywords -- neither tells you what the
                # thing IS at a glance, and enrolling the wrong product means
                # repricing it against somebody else's supplier. It is already in
                # the snapshot; it simply was not being passed on.
                "img": str(it.get("img") or ""),
                "price": it.get("price"), "qty": it.get("qty"),
                "status": str(it.get("status") or ""),
                "fulfillment": str(it.get("fulfillment") or ""),
                "enrolled": bool(row),
                "mode": (row or {}).get("mode") or "",
                "sources": len(_repo.sources_for(CONFIG_PATH, wsid, mkt, sku)) if row else 0,
            })
        out.sort(key=lambda r: (not r["enrolled"], r["sku"]))
        # An empty list has three quite different causes and they need three
        # different actions. Telling everyone to press Sync when the real problem
        # is that no marketplace was resolved sends them to fix something that
        # was never broken.
        note = ""
        if not out:
            if not wsid:
                note = "No account is selected — open a workspace first."
            elif not mkt:
                note = ("No marketplace is selected, so there was nothing to look "
                        "up. Pick one on the Listings screen and come back.")
            elif not rec.get("items"):
                note = ("No live listings are cached for %s on %s yet — press Sync "
                        "on the Listings screen first." % (wsid, mkt))
            else:
                note = "No listings match that filter."
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "count": len(out), "items": out, "note": note})

    # ---- enrolment ------------------------------------------------------
    @app.route("/sourcing/enrol", methods=["POST"])
    def sourcing_enrol():
        b = _body()
        wsid, mkt = _where()
        sku = (b.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        if b.get("enrolled") is False:
            _repo.unenrol(CONFIG_PATH, wsid, mkt, sku)
        else:
            # 'live' is refused here on purpose. Phase D owns arming, and it will
            # require a min_price first -- the only guard that survives a
            # misread supplier cost.
            _repo.enrol(CONFIG_PATH, wsid, mkt, sku, mode="dry_run")
        return jsonify({"ok": True})

    @app.route("/sourcing/enrol_bulk", methods=["POST"])
    def sourcing_enrol_bulk():
        """Track many SKUs at once, attaching each one's known supplier link.

        "i want to enroll all my items to the repricer ... uploading or selecting
         the skus in the repricer means to track their true costs from the
         sources"

        Tracking is not pricing. Everything enrolled here is in dry run and
        cannot change a listing -- arming is separate and still needs a
        min_price per SKU. What this does is start reading what each unit
        actually costs, which is the thing you cannot get back later: a supplier
        price on a day nobody was watching is simply gone.

        The supplier link is not asked for, because the app already recorded it
        when it built the listing (domain/source_link.py). A SKU whose link
        cannot be found is still enrolled and says what it is missing, rather
        than being dropped from a bulk action silently.
        """
        b = _body()
        wsid, mkt = _where()
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        if not skus:
            return jsonify({"ok": False, "error": "no SKUs given"}), 400
        if len(skus) > 2000:
            return jsonify({"ok": False, "error": (
                "%d SKUs at once is more than this was meant for -- enrol in "
                "batches so a failure part-way is easy to see" % len(skus))}), 400

        from domain import source_link as _link
        out = {"enrolled": 0, "already": 0, "linked": 0, "no_link": 0, "rows": []}
        have = {r["sku"] for r in _repo.enrolled(CONFIG_PATH, wsid, mkt)}
        for sku in skus:
            was = sku in have
            _repo.enrol(CONFIG_PATH, wsid, mkt, sku, mode="dry_run")
            out["already" if was else "enrolled"] += 1
            row = {"sku": sku, "was_enrolled": was, "source": "", "note": ""}
            # Never a SECOND source for a SKU that already has one: this can be
            # run repeatedly over a growing catalogue, and each pass would
            # otherwise add another copy of the same link.
            if _repo.sources_for(CONFIG_PATH, wsid, mkt, sku):
                row["note"] = "already has a supplier"
            else:
                got = _link.for_sku(CONFIG_PATH, wsid, sku)
                if got["url"]:
                    try:
                        # ensure_source, not add_source: this is automatic, and
                        # add_source INSERTs unconditionally -- running it twice
                        # over a growing catalogue would give every SKU a second
                        # identical supplier, then a third, each one fetched on
                        # every sweep.
                        _repo.ensure_source(CONFIG_PATH, wsid, mkt, sku, got["url"],
                                            kind=got["kind"], label=got["url"])
                        out["linked"] += 1
                        row["source"] = got["url"]
                        row["note"] = "from " + got["where"]
                    except Exception as e:
                        out["no_link"] += 1
                        row["note"] = "could not attach: %s" % str(e)[:120]
                else:
                    out["no_link"] += 1
                    row["note"] = got["why"]
            out["rows"].append(row)
        out["ok"] = True
        return jsonify(out)

    @app.route("/sourcing/sources/upload", methods=["POST"])
    def sourcing_sources_upload():
        """Attach suppliers to many listings from one uploaded sheet.

        Rows identify their listing by SKU or by ASIN, and carry the supplier
        link. Parsing and matching are in domain/source_bulk.py; this route only
        takes the file and hands back the per-row report, because a bulk import
        that reports a total and nothing else is how silently-skipped rows
        become "the repricer is not working".
        """
        from domain import source_bulk as _bulk
        wsid, mkt = _where()
        f = request.files.get("file")
        if f is None:
            return jsonify({"ok": False, "error": "no file was uploaded"}), 400
        try:
            data = f.read()
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:160]}), 400
        headers, rows, err = _bulk.read_table(data, getattr(f, "filename", ""))
        if err:
            return jsonify({"ok": False, "error": err}), 400
        out = _bulk.apply_rows(CONFIG_PATH, wsid, mkt, headers, rows)
        return jsonify(out), (200 if out.get("ok") else 400)

    # ---- sources --------------------------------------------------------
    @app.route("/sourcing/source/add", methods=["POST"])
    def sourcing_source_add():
        b = _body()
        wsid, mkt = _where()
        sku = (b.get("sku") or "").strip()
        url = (b.get("url") or "").strip()
        if not sku or not url:
            return jsonify({"ok": False, "error": "need a sku and a url"}), 400
        kind = (b.get("kind") or "").strip().lower()
        if not kind:
            kind = "ebay" if "ebay." in url.lower() else "html"
        from api import ebay as _ebay
        if kind == "ebay":
            if not _ebay.item_id_from_url(url):
                return jsonify({"ok": False, "error": (
                    "that does not look like an eBay item link -- it should "
                    "contain /itm/ and the item number")}), 400
        # Refused at the point you can still fix it. A variation listing has no
        # one price or stock level, so this source could never produce a usable
        # reading -- it would sit in every sweep answering "could not tell", and
        # the repricer would correctly do nothing, silently, for ever.
        if kind == "ebay" and not _ebay.variation_id_from_url(url):
            _c = _cfg() if callable(_cfg) else (_cfg or {})
            app_id = str(_c.get("ebay_app_id", "") or "")
            cert_id = str(_c.get("ebay_cert_id", "") or "")
            if app_id and cert_id:
                probe = _ebay.get_item(url, app_id, cert_id,
                                       marketplace=_ebay.site_for(mkt))
                if probe["status"] == _ebay.GROUP:
                    return jsonify({"ok": False, "error": probe["error"]}), 400

        # Not add_source: the same supplier link twice is two fetches of the same
        # answer on every sweep, and that supplier then counts twice in the
        # ranking. ensure_source says whether it was already there.
        sid, created = _repo.ensure_source(
            CONFIG_PATH, wsid, mkt, sku, url, kind=kind,
            label=(b.get("label") or "").strip(),
            priority=int(b.get("priority") or 100),
            shipping_override=b.get("shipping_override"))
        return jsonify({"ok": True, "id": sid, "created": created,
                        "note": ("" if created else
                                 "That link was already a source for this SKU, "
                                 "so nothing was added.")})

    @app.route("/sourcing/source/update", methods=["POST"])
    def sourcing_source_update():
        b = _body()
        sid = b.get("source_id")
        if not sid:
            return jsonify({"ok": False, "error": "no source"}), 400
        if "enabled" in b:
            _repo.set_source_enabled(CONFIG_PATH, sid, bool(b["enabled"]))
        if "shipping_override" in b:
            v = b["shipping_override"]
            _repo.set_shipping_override(
                CONFIG_PATH, sid, None if v in ("", None) else float(v))
        return jsonify({"ok": True})

    @app.route("/sourcing/source/remove", methods=["POST"])
    def sourcing_source_remove():
        b = _body()
        if not b.get("source_id"):
            return jsonify({"ok": False, "error": "no source"}), 400
        _repo.remove_source(CONFIG_PATH, b["source_id"])
        return jsonify({"ok": True})

    # ---- rules ----------------------------------------------------------
    @app.route("/sourcing/rules", methods=["POST"])
    def sourcing_rules():
        b = _body()
        wsid, mkt = _where()
        vals = {k: v for k, v in (b.get("rule") or {}).items()
                if k in _sourcing.DEFAULT_RULE}

        # A MISTYPED TARGET MUST NOT LOOK LIKE NO TARGET.
        # A percentage that does not parse would store, fail every check inside
        # target_floor, and leave someone believing a 20% floor was in force
        # while the repricer priced to the flat £1. Two boxes now, each checked
        # the same way and each clearable on its own -- turning the margin target
        # off must not disturb the ROI one.
        for key, label in (("target_margin_pct", "margin"),
                           ("target_roi_pct", "ROI")):
            if key not in vals:
                continue
            v = vals[key]
            if v in (None, ""):
                vals[key] = None
                continue
            try:
                v = float(str(v).replace("%", "").strip())
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": (
                    "the %s target must be a number of percent, e.g. 20 -- got %r"
                    % (label, vals[key]))}), 400
            if v < 0:
                return jsonify({"ok": False, "error": (
                    "a %s target cannot be negative" % label)}), 400
            # ROI has no upper bound worth refusing: 200% back on a cheap unit is
            # ambitious, not impossible. Margin does -- see below.
            if label == "margin" and v >= 100:
                return jsonify({"ok": False, "error": (
                    "a margin target of %g%% would need the customer to pay more "
                    "than the whole price as profit" % v)}), 400
            vals[key] = v

        # SETTING EITHER BOX RETIRES THE OLD SINGLE TARGET.
        #
        # rule_with_defaults folds a stored profit_target_kind/pct into whichever
        # box it names, so an account that set "20% roi" before there were two
        # boxes keeps its floor. But that fold happens on every read -- so
        # clearing both boxes left the old row behind and the 20% came straight
        # back. Measured: saving {margin: null, roi: null} on jack_uk answered
        # roi=20.0. "Off" has to mean off.
        #
        # Cleared alongside, in the same write, so there is no moment where one
        # is set and the other is not.
        if "target_margin_pct" in vals or "target_roi_pct" in vals:
            vals["profit_target_kind"] = None
            vals["profit_target_pct"] = None

        # A margin target competes with Amazon's cut for the same pound, so past
        # a point there is no price that satisfies it. Said here, once, rather
        # than as "cannot be priced" against every SKU afterwards. ROI is never
        # refused for this: it is measured against the cost, not the price, so
        # Amazon's cut does not eat into it the same way.
        merged = _sourcing.rule_with_defaults(
            {**_repo.rule_for(CONFIG_PATH, wsid, mkt, (b.get("sku") or "").strip()),
             **vals})
        m_pct = merged.get("target_margin_pct")
        if m_pct is not None:
            room = (1.0 - float(merged["referral_rate"])) * 100.0
            if float(m_pct) >= room - 1:
                return jsonify({"ok": False, "error": (
                    "Amazon takes %.0f%% of the sale, so a MARGIN target has to "
                    "stay under about %.0f%% to be reachable at any price. %g%% "
                    "in the ROI box -- a share of what you paid -- is a different "
                    "and quite reachable number."
                    % (float(merged["referral_rate"]) * 100, room - 1,
                       float(m_pct)))}), 400

        _repo.save_rule(CONFIG_PATH, wsid, mkt, (b.get("sku") or "").strip(), vals)
        return jsonify({"ok": True, "rule": _sourcing.rule_with_defaults(
            _repo.rule_for(CONFIG_PATH, wsid, mkt, (b.get("sku") or "").strip()))})

    # ---- run it now -----------------------------------------------------
    @app.route("/sourcing/check", methods=["POST"])
    def sourcing_check_now():
        """Re-read every supplier now, then decide. The same two steps the timer
        runs, so pressing this cannot produce a different answer from waiting."""
        wsid, mkt = _where()
        got = _fetch.sweep(CONFIG_PATH, _cfg, workspace_id=wsid, marketplace=mkt,
                           pause=0.0)
        run = _run.dry_run(CONFIG_PATH, wsid, mkt)
        return jsonify({"ok": True, "fetch": got, "counts": run["counts"],
                        "skus": run["skus"]})

    # ---- arming ---------------------------------------------------------
    @app.route("/sourcing/arm", methods=["POST"])
    def sourcing_arm():
        """Move one SKU from dry run to live, or back.

        Refuses to arm without a minimum price. That is not a formality: the
        floor is worked out FROM the supplier's cost, so a misread cost produces
        a wrong floor just as confidently, and min_price is the only guard that
        does not depend on the reading.
        """
        b = _body()
        wsid, mkt = _where()
        sku = (b.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        if not b.get("live"):
            _repo.enrol(CONFIG_PATH, wsid, mkt, sku, mode="dry_run")
            return jsonify({"ok": True, "mode": "dry_run"})

        rule = _sourcing.rule_with_defaults(_repo.rule_for(CONFIG_PATH, wsid, mkt, sku))
        if rule.get("min_price") is None:
            return jsonify({"ok": False, "error": (
                "Set a minimum price for this SKU first. It is the one guard that "
                "still works when a supplier's page is misread, so nothing is "
                "armed without it.")}), 400
        _repo.enrol(CONFIG_PATH, wsid, mkt, sku, mode="live")
        return jsonify({"ok": True, "mode": "live",
                        "note": ("Armed. It will push at most one change every "
                                 "%.0f hours, and never below %.2f."
                                 % (_apply.COOLDOWN_HOURS, rule["min_price"]))})

    @app.route("/sourcing/master", methods=["GET", "POST"])
    def sourcing_master():
        """The master switch. Off by default, and off means nothing is pushed
        however many SKUs are armed -- one place to stop everything at once."""
        if request.method == "GET":
            return jsonify({"ok": True, "enabled": _apply.is_enabled(_cfg)})
        b = _body()
        raw = _read_config()
        raw["repricer_enabled"] = bool(b.get("enabled"))
        _write_config(raw)
        return jsonify({"ok": True, "enabled": bool(b.get("enabled"))})

    @app.route("/sourcing/apply", methods=["POST"])
    def sourcing_apply():
        """Push now for every armed SKU. Same gates as the timer, no shortcuts."""
        wsid, mkt = _where()
        res = _apply.run_live(CONFIG_PATH, _cfg, _creds_for,
                              workspace_id=wsid, marketplace=mkt)
        return jsonify({"ok": True, **res})
