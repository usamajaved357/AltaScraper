"""routes/sourcing_routes.py -- the source repricer's screen.

Holds no decision logic of its own. Enrollment and sources come from
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
import datetime as _dt
import json

from flask import request, jsonify, Response

from config import settings as _settings
from domain import order_sources as _osrc
from domain import source_apply as _apply
from domain import source_bulk as _bulk
from domain import amazon_fees as _fees
from domain import source_drift as _drift
from domain import source_fetch as _fetch
from domain import source_link as _slink
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

    # Reading and writing config.json belongs to config/settings.py, which owns
    # the file. These two used to do it here by hand, and the moment a second
    # screen needed to save a setting that private copy would have been copied
    # again (CLAUDE.md Rule 12). The shared writer is also ATOMIC, where this one
    # truncated config.json before writing a byte -- a crash mid-write took every
    # credential in the app with it, and the file is git-ignored.
    def _read_config():
        return _settings.read_raw(CONFIG_PATH)

    def _write_config(raw):
        _settings.write_raw(raw, CONFIG_PATH)
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

    def _where_acc():
        """_where(), plus the account record itself, for the routes that call Amazon."""
        wsid, mkt = _where()
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        acc = next((a for a in (cfg.get("accounts") or [])
                    if str(a.get("id") or "") == str(wsid)), None) \
              or (_active_account() or {})
        return acc, wsid, mkt

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
        """Everything the screen draws: enrollment, sources, readings, decisions."""
        from domain import catalogue as _cat
        wsid, mkt = _where()
        run = _run.dry_run(CONFIG_PATH, wsid, mkt, record=False)
        # WHICH PRODUCT EACH ROW IS. "i want to see the images of the items in
        # the repricer so it is easy to understand for which product are we
        # talking about" -- and a SKU like 10.39_3Days_B0F6LQ1S93 tells nobody.
        # From the shared lookup, so the picture here is the one the Listings
        # cards and the Orders rows show; built once for the whole list rather
        # than per row.
        # include_drafts, because the Repricer tracks drafts as well as live
        # SKUs -- 22 of jack_uk's 67 had no picture without it, being either
        # never-sent drafts or listings whose Amazon summary carried no image.
        # A picture taken from a draft is marked as the SUPPLIER's, never shown
        # as though it were what is live on Amazon.
        idx = _cat.index(CONFIG_PATH, wsid, mkt, include_drafts=True)
        # WHAT DISCOUNT EACH SKU HAS ACTUALLY BEEN SELLING UNDER.
        #
        #     "the app should automatically know when which promotion or coupon
        #      is applied and how much is applied and make the calculations
        #      accordingly"
        #
        # Amazon does not expose the seller's running coupons to this app, so it
        # is measured from what buyers were really charged on settled orders --
        # see domain/promotions.py. Read ONCE for the whole list; per row it
        # would be one query per SKU on a screen that draws sixty of them.
        try:
            from domain import promotions as _promos
            _promos_by_sku = _promos.measured(CONFIG_PATH, wsid, mkt)
        except Exception:
            _promos_by_sku = {}
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
                             # What to CALL this link. From the same function the
                             # order panel uses, so the repricer's detail panel
                             # and the order screen cannot name one supplier two
                             # different ways (Rule 12).
                             "name": _slink.display_name(
                                 s.get("url"), (c or {}).get("seller"),
                                 s.get("label")),
                             "history": _drift.price_history(CONFIG_PATH, s["id"])})
            _rule = _sourcing.rule_with_defaults(
                _repo.rule_for(CONFIG_PATH, d["workspace_id"],
                               d["marketplace"], d["sku"]))
            # THE SUPPLIER LINKS, RANKED, on the row itself.
            #
            #     "i want to be shown all the available supplier/ source links
            #      and highlight the cheapest of all of them ... under it where
            #      the source links are mentioned show the delivery time of the
            #      suppliers"
            #
            # Through domain/order_sources.options_for -- the SAME function the
            # order panel draws its list from -- so the repricer and the order
            # screen cannot disagree about which link is cheapest, what it costs
            # delivered, or when it would arrive (Rule 12).
            try:
                _opts = _osrc.options_for(
                    CONFIG_PATH, d["workspace_id"], d["marketplace"], d["sku"],
                    sell_price=(d.get("current") or {}).get("price"),
                    rule=_rule, now=_dt.datetime.now())
            except Exception:
                _opts = []
            rows.append({**d, "sources": srcs, "options": _opts,
                         "drift": _drift.for_sku(
                             _COGS_OVERRIDE, d["workspace_id"], d["sku"], pairs,
                             (d.get("decision") or {}).get("source_id")),
                         # What an order arriving right now would actually earn:
                         # today's supplier price against today's Amazon price.
                         "glance": _drift.at_a_glance(
                             pairs, d.get("current"), _rule,
                             (d.get("decision") or {}).get("source_id"),
                             promo=_promos_by_sku.get(d["sku"])),
                         "item": _cat.look(idx, d["sku"]),
                         "rule": _rule})
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "rows": rows, "counts": run["counts"],
                        "note": run["note"],
                        "master_enabled": _apply.is_enabled(_cfg),
                        "rule": _sourcing.rule_with_defaults(
                            _repo.rule_for(CONFIG_PATH, wsid, mkt, "")),
                        # How long the postage takes. Sent so the settings menu
                        # can show the value in force rather than the module
                        # default, which would read as "2 days" on an account
                        # that had changed it to 1.
                        "shipping_policy_days": int(
                            _read_config().get("shipping_policy_days")
                            or _sourcing.SHIPPING_POLICY_DAYS),
                        # Which marketplace these rows are from, so the money
                        # editors show the right currency symbol rather than
                        # guessing from whichever screen was opened last.
                        "marketplace": mkt,
                        # What a NEWLY tracked SKU starts with. Shown in the
                        # settings menu; it changes nothing already tracked.
                        "default_target": (
                            _read_config().get("sourcing_default_target")
                            or {"kind": "none", "pct": None}),
                        "defaults": _sourcing.DEFAULT_RULE})

    @app.route("/sourcing/check_listings", methods=["POST"])
    def sourcing_check_listings():
        """Ask Amazon which enrolled SKUs it still has, and disarm the ones it does not.

        "the template and the repricer is saving the skus which i have deleted
         already, turn off the auto repricing for that sku and give warning to
         tell that this offer is deleted"

        One getListingsItem per enrolled SKU, so this is a deliberate act rather
        than something that runs on every page draw. Measured on jack_uk: six of
        67 answer 404 GONE -- 1U-OMQC-HX2V, DigitalPressurGauge_B0H227VG3N,
        EO-GXWE-XOXU, TyrePump_B0H1XFJRFD, WeightMachine_B0H1SFBDNT and
        showerhead_B0H2JWJXN4 -- and the repricer was working out prices for all
        six.

        A SKU found gone is switched to dry run in the same statement that marks
        it, so it cannot be pushed to between the two. Its enrollment row, its
        sources and its history are KEPT: they are worth more than the row costs,
        and it may be relisted tomorrow.
        """
        from api import amazon_listings as _al
        from domain import accounts as _acc_mod
        acc, wsid, mkt = _where_acc()
        rows = _repo.enrolled(CONFIG_PATH, wsid, mkt)
        creds = _acc_mod.account_creds(acc or {})
        mid = _acc_mod.marketplace_id(mkt)
        seller = str((acc or {}).get("seller_id") or "")
        if not (seller and mid):
            return jsonify({"ok": False, "error": (
                "this account has no seller id or marketplace, so Amazon cannot "
                "be asked about its listings")}), 400
        gone, ok, unreadable = [], [], []
        for r in rows:
            sku = str(r.get("sku") or "")
            if not sku:
                continue
            got = _al.get_item(creds, mkt, seller, sku, mid)
            if got["status"] == _al.GONE:
                _repo.set_listing_state(CONFIG_PATH, wsid, mkt, sku, _repo.GONE)
                gone.append(sku)
            elif got["status"] == _al.OK:
                _repo.set_listing_state(CONFIG_PATH, wsid, mkt, sku, _repo.LIVE_OK)
                ok.append(sku)
            else:
                # "Amazon would not answer" is NOT "the listing is gone". Marking
                # it gone on a timeout would disarm a perfectly good SKU.
                unreadable.append(sku)
        note = ("%d still on Amazon, %d gone" % (len(ok), len(gone)))
        if gone:
            note += (" â€” auto-pricing is now off for %s" % ", ".join(gone[:6])
                     + (" and others" if len(gone) > 6 else ""))
        if unreadable:
            note += (". %d could not be read and were left exactly as they were"
                     % len(unreadable))
        return jsonify({"ok": True, "checked": len(rows), "gone": gone,
                        "still_there": len(ok), "unreadable": unreadable,
                        "note": note})

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
        rows_e = _repo.enrolled(CONFIG_PATH, wsid, mkt)
        # A SKU AMAZON NO LONGER HAS IS NOT WORTH A SUPPLIER LINK.
        #
        # "the template and the repricer is saving the skus which i have deleted
        #  already". Left out of the sheet entirely rather than listed with a
        #  note: this sheet exists to be filled in, and a row you must not fill
        #  in is a row that wastes the reader's attention. They are still on the
        #  Repricer screen, marked, which is where the decision to remove them
        #  belongs.
        enrolled = [r["sku"] for r in rows_e
                    if str(r.get("listing_state") or "") != _repo.GONE]
        dropped = [r["sku"] for r in rows_e
                   if str(r.get("listing_state") or "") == _repo.GONE]

        # WHAT IS ALREADY ATTACHED, so a row that is done looks done. Someone
        # changing one supplier should be able to see the other forty are
        # already filled in and leave them alone, rather than wondering whether
        # a blank column means "none" or "we did not look".
        # EVERY supplier a SKU has, not just the first. A SKU can have several --
        # that is the whole point of the repricer, which compares them and takes
        # the cheapest usable one -- and the sheet showing only one made it look
        # as though only one were possible. Asked as "i dont have an option to add
        # multiple sellers in the template".
        sources = {}
        for sku in enrolled:
            urls = [str(s.get("url") or "")
                    for s, _c in _repo.pairs_for(CONFIG_PATH, wsid, mkt, sku)
                    if s.get("url")]
            if urls:
                sources[sku] = urls

        rows = _bulk.template_rows(CONFIG_PATH, wsid, mkt, enrolled,
                                   catalogue=_cat.index(CONFIG_PATH, wsid, mkt),
                                   sources=sources)
        # WIDENED TO FIT THE WIDEST SKU. A fixed ten-column header truncates
        # nothing on the way out -- the row simply runs wider -- but on the way
        # back IN, url_columns finds supplier columns by name and nothing names
        # the eleventh. So exporting a SKU with eleven suppliers, changing
        # nothing and uploading it again silently lost the eleventh. Measured: a
        # 15-cell row against a 13-cell header, 10 supplier columns found.
        body = _bulk.to_csv(_bulk.template_headers(rows), rows)
        name = "supplier-links-%s-%s.csv" % (wsid or "account", mkt or "")
        hdrs = {"Content-Disposition": 'attachment; filename="%s"' % name}
        if dropped:
            # Said in the reply as well as on the screen, so a caller that is not
            # the browser is told too. A header rather than a row in the sheet:
            # a note inside a CSV becomes a row somebody uploads back.
            hdrs["X-Alta-Skipped-Deleted"] = str(len(dropped))
        return Response(body, mimetype="text/csv; charset=utf-8", headers=hdrs)

    @app.route("/sourcing/log")
    def sourcing_log():
        """The audit trail -- every decision, whether or not it was pushed."""
        wsid, mkt = _where()
        return jsonify({"ok": True, "actions": _repo.recent_actions(
            CONFIG_PATH, wsid, mkt, request.args.get("sku") or None,
            int(request.args.get("limit") or 200))})

    @app.route("/sourcing/alerts")
    def sourcing_alerts():
        """SKUs with nowhere left to buy from.

        "add an alert in the app that whenever all the links go out of stock i
         should receive a notification"

        Worked out from the readings every time rather than kept in a table --
        domain/stock_alerts.py explains why. Cheap: local database only, no
        supplier is contacted, so a screen may poll it.
        """
        from domain import stock_alerts as _alerts
        wsid, mkt = _where()
        if not wsid:
            return jsonify({"ok": False, "error": "no account selected"}), 400
        out = _alerts.for_account(CONFIG_PATH, wsid, mkt)
        # The sentence comes from the same place as the alert, so the banner, the
        # repricer and anything added later say the same thing.
        for group in ("alerts", "unreadable"):
            for a in out.get(group, []):
                a["sentence"] = _alerts.sentence(a)
                # The short form, for a list where the shared explanation is
                # already printed above it.
                a["row"] = _alerts.row_label(a)
        # The half that is identical across the whole list, said once. Empty when
        # the alerts do not actually share one, and the screen then falls back to
        # the self-contained sentences.
        out["alerts_shared"] = _alerts.group_sentence(out.get("alerts"))
        out["unreadable_shared"] = _alerts.group_sentence(out.get("unreadable"))
        out["ok"] = True
        return jsonify(out)

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
                note = "No account is selected â€” open a workspace first."
            elif not mkt:
                note = ("No marketplace is selected, so there was nothing to look "
                        "up. Pick one on the Listings screen and come back.")
            elif not rec.get("items"):
                note = ("No live listings are cached for %s on %s yet â€” press Sync "
                        "on the Listings screen first." % (wsid, mkt))
            else:
                note = "No listings match that filter."
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "count": len(out), "items": out, "note": note})

    # ---- enrollment ------------------------------------------------------
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
            # ASK AMAZON ITS FEE NOW, while somebody is here to see it fail.
            #
            # The alternative is that the first price this SKU is ever given
            # comes off a fallback rate, silently, and is corrected a week later
            # when the refresh job runs. One call at the moment of enrolling is
            # the cheapest possible time to make the first price the right one.
            #
            # It never blocks enrolling: an account whose SP-API roles are not
            # granted answers nothing, and that is a reason to price from the
            # measured rate, not a reason to refuse to track the product.
            try:
                _fees.quote_for_sku(CONFIG_PATH, _cfg, wsid, mkt, sku)
            except Exception:
                pass
            _apply_default_target(wsid, mkt, sku)
        return jsonify({"ok": True})

    def _apply_default_target(wsid, mkt, sku):
        """Give a NEWLY tracked SKU the target the owner chose for new ones.

            "Add a setting: 'Default target for new enrollments' ... This
             applies only to NEW enrollments. Existing SKUs keep their current
             rules."

        WHY THIS IS NOT JUST A CHANGED DEFAULT. A default is read on every
        lookup, so changing it would silently re-price every SKU that had never
        set a target of its own -- which is exactly the complaint that took the
        hidden 20% floor out of listing/pricing.py. This WRITES the number onto
        the new SKU's own rule row instead, once, at the moment it is enrolled.
        Change the setting afterwards and nothing already tracked moves.

        Never raises, and never overwrites: a SKU being re-enrolled after being
        removed still has its old rule row, and that row is somebody's decision.
        """
        try:
            d = (_read_config().get("sourcing_default_target") or {})
            kind = str(d.get("kind") or "").lower()
            pct = d.get("pct")
            if kind not in ("roi", "margin") or pct in (None, ""):
                return                      # "none / breakeven", the default
            existing = _repo.rule_for(CONFIG_PATH, wsid, mkt, sku) or {}
            if (existing.get("target_roi_pct") is not None
                    or existing.get("target_margin_pct") is not None):
                return                      # it already has one; leave it
            key = ("target_roi_pct" if kind == "roi" else "target_margin_pct")
            _repo.save_rule(CONFIG_PATH, wsid, mkt, sku, {key: float(pct)})
        except Exception:
            pass          # a default that cannot be applied must not stop tracking

    # ---- floors by the sheetful ------------------------------------------
    #
    #     "This is the fastest path to going live: download -> fill prices in
    #      Excel -> upload -> all armed in 2 minutes."
    #
    # WHY A SHEET AT ALL, when the floor is one click on a row. Because the
    # floor is the gate: nothing can be armed without one, and on this account
    # 66 of 67 SKUs have none. Setting them one at a time is 66 popovers, and
    # each one asks a question you can only answer by comparing three numbers --
    # what it sells for, what it costs, and what you would accept. A spreadsheet
    # puts those three in columns and lets you fill the fourth down the page.
    @app.route("/sourcing/minprice_template.csv")
    def sourcing_minprice_template():
        """Every tracked SKU, with the context needed to choose a floor.

        The only empty column is the one they are here to fill. Read-only
        context beside it, because "what should this SKU never go below" is
        unanswerable without knowing what it sells for and what it costs.
        """
        import csv as _csv
        import io as _io
        from domain import catalogue as _cat

        wsid, mkt = _where()
        rows_e = _repo.enrolled(CONFIG_PATH, wsid, mkt)
        # ALL of them, armed or not -- "Include ALL enrolled SKUs, not just
        # un-armed ones". An armed SKU's floor is still worth revising, and
        # leaving it out would make the sheet an incomplete picture of what the
        # repricer is allowed to do.
        idx = _cat.index(CONFIG_PATH, wsid, mkt, include_drafts=True)
        run = _run.dry_run(CONFIG_PATH, wsid, mkt, record=False)
        by_sku = {}
        for d in (run.get("decisions") or []):
            by_sku[str(d.get("sku"))] = d

        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["SKU", "ASIN", "Product Title", "Current Price",
                    "Supplier Cost", "Current Min Price", "New Min Price"])
        for e in rows_e:
            sku = str(e.get("sku") or "")
            if not sku:
                continue
            d = by_sku.get(sku) or {}
            cur = d.get("current") or {}
            bd = (d.get("decision") or {}).get("breakdown") or {}
            item = _cat.look(idx, sku) or {}
            rule = _sourcing.rule_with_defaults(
                _repo.rule_for(CONFIG_PATH, wsid, mkt, sku))
            mp = rule.get("min_price")
            w.writerow([
                sku,
                cur.get("asin") or item.get("asin") or "",
                (item.get("title") or "")[:120],
                ("" if cur.get("price") is None else "%.2f" % cur["price"]),
                ("" if bd.get("cost") is None else "%.2f" % bd["cost"]),
                ("" if mp is None else "%.2f" % float(mp)),
                "",                      # New Min Price -- the one to fill in
            ])
        out = buf.getvalue()
        return Response(out, mimetype="text/csv", headers={
            "Content-Disposition":
                'attachment; filename="min-prices-%s-%s.csv"' % (wsid, mkt)})

    @app.route("/sourcing/minprice_upload", methods=["POST"])
    def sourcing_minprice_upload():
        """Read the filled-in sheet and set the floors.

        Body: {rows: [{sku, asin, min_price}], arm: bool}

        THE BROWSER PARSES THE FILE, not this. The screen already carries a
        reader for .xlsx and .csv (the supplier sheet uses it), so sending the
        rows as JSON means one parser for both uploads rather than a second one
        here that would disagree with it about a stray column (Rule 12).

        NOTHING IS ARMED BY ACCIDENT. `arm` is a tick the person has to set, and
        even then a SKU is armed only if the floor it just received is real --
        the same check /sourcing/arm makes, because arming without a floor is
        the one thing this whole screen refuses to do.
        """
        b = _body()
        wsid, mkt = _where()
        want_arm = bool(b.get("arm"))
        rows = b.get("rows") or []
        if not isinstance(rows, list) or not rows:
            return jsonify({"ok": False, "error": (
                "That sheet had no rows the app could read. It needs a SKU or "
                "ASIN column and a \"New Min Price\" column.")}), 400

        # SKU first, ASIN second. A SKU names one listing; an ASIN can be on
        # several (the same product listed by two of these accounts), so it is
        # only used when the SKU is missing, and only when it matches exactly
        # one tracked SKU. Ambiguity is reported, never guessed at.
        enrolled = _repo.enrolled(CONFIG_PATH, wsid, mkt)
        known = {str(e.get("sku")): True for e in enrolled}
        by_asin = {}
        for d in (_run.dry_run(CONFIG_PATH, wsid, mkt, record=False)
                  .get("decisions") or []):
            a = str(((d.get("current") or {}).get("asin") or "")).upper()
            if a:
                by_asin.setdefault(a, []).append(str(d.get("sku")))

        done, armed, skipped, errors = [], [], 0, []
        for r in rows:
            raw_sku = str((r or {}).get("sku") or "").strip()
            raw_asin = str((r or {}).get("asin") or "").strip().upper()
            raw_val = (r or {}).get("min_price")
            val = "" if raw_val is None else str(raw_val).strip()
            if val == "":
                skipped += 1                       # a blank row is not an error
                continue

            sku = raw_sku if raw_sku in known else ""
            if not sku and raw_asin:
                hits = by_asin.get(raw_asin) or []
                if len(hits) == 1:
                    sku = hits[0]
                elif len(hits) > 1:
                    errors.append({"row": raw_sku or raw_asin, "why": (
                        "%s is on %d tracked SKUs, so the app cannot tell which "
                        "one this row means" % (raw_asin, len(hits)))})
                    continue
            if not sku:
                errors.append({"row": raw_sku or raw_asin or "(blank)",
                               "why": "not a SKU this account is tracking"})
                continue

            try:
                num = float(val.replace("£", "").replace("$", "")
                            .replace(",", "").strip())
            except (TypeError, ValueError):
                errors.append({"row": sku,
                               "why": "%r is not a number" % val})
                continue
            if num <= 0:
                errors.append({"row": sku,
                               "why": "a floor has to be above zero"})
                continue

            _repo.save_rule(CONFIG_PATH, wsid, mkt, sku, {"min_price": num})
            done.append({"sku": sku, "min_price": round(num, 2)})

            if want_arm:
                # The same gate /sourcing/arm applies. It cannot fail here --
                # a floor was just written -- but it is asked rather than
                # assumed, because "armed" means this SKU can change a live
                # price and that is never inferred from a spreadsheet.
                rule = _sourcing.rule_with_defaults(
                    _repo.rule_for(CONFIG_PATH, wsid, mkt, sku))
                if rule.get("min_price") is not None:
                    _repo.enrol(CONFIG_PATH, wsid, mkt, sku, mode="live")
                    armed.append(sku)

        note = "%d min price%s updated" % (len(done), "" if len(done) == 1 else "s")
        if armed:
            note += ", %d armed" % len(armed)
        if skipped:
            note += ", %d left blank" % skipped
        if errors:
            note += ", %d could not be read" % len(errors)
        return jsonify({"ok": True, "updated": len(done), "armed": len(armed),
                        "skipped": skipped, "errors": errors,
                        "rows": done, "note": note + "."})

    @app.route("/sourcing/default_target", methods=["GET", "POST"])
    def sourcing_default_target():
        """What a newly tracked SKU starts with. Global; changes nothing existing.

        Body: {kind: "roi"|"margin"|"none", pct: 20}
        """
        if request.method == "GET":
            d = (_read_config().get("sourcing_default_target") or {})
            return jsonify({"ok": True,
                            "kind": str(d.get("kind") or "none").lower(),
                            "pct": d.get("pct")})
        b = _body()
        kind = str(b.get("kind") or "none").strip().lower()
        if kind not in ("roi", "margin", "none"):
            return jsonify({"ok": False, "error": (
                "that must be roi, margin or none -- got %r" % b.get("kind"))}), 400
        raw = _read_config()
        if kind == "none":
            raw["sourcing_default_target"] = {"kind": "none", "pct": None}
            _write_config(raw)
            return jsonify({"ok": True, "kind": "none", "pct": None, "note": (
                "New SKUs will start with no target -- priced no lower than "
                "break-even, and no higher until you set one.")})
        # A MISTYPED PERCENTAGE MUST NOT LOOK LIKE NO PERCENTAGE, the same
        # argument as every other number box on this screen: stored as text it
        # would read back as something and be int()ed to nothing at decision
        # time, leaving somebody believing new SKUs had a target.
        try:
            pct = float(str(b.get("pct")).replace("%", "").strip())
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": (
                "the target must be a number, e.g. 20 -- got %r"
                % b.get("pct"))}), 400
        # A margin above 100% is asking for more than the whole price; an ROI
        # can legitimately be large, but a thousand percent is a typo.
        if pct < 0 or (kind == "margin" and pct >= 100) or pct > 500:
            return jsonify({"ok": False, "error": (
                "a margin target must be under 100%, and any target must be "
                "between 0 and 500%")}), 400
        raw["sourcing_default_target"] = {"kind": kind, "pct": pct}
        _write_config(raw)
        return jsonify({"ok": True, "kind": kind, "pct": pct, "note": (
            "New SKUs will start at %g%% %s. Nothing already tracked has "
            "changed." % (pct, kind.upper() if kind == "roi" else kind))})

    @app.route("/sourcing/unenrol_bulk", methods=["POST"])
    def sourcing_unenrol_bulk():
        """Stop tracking several SKUs at once.

        "also allow to select multiple skus at once and unroll them from
         tracking"

        Removing them one at a time is fine for one and unusable for forty, and
        forty is the normal case after a bulk import that pulled in more than
        was wanted.

        NOTHING IS DELETED. unenrol() sets enrolled=0 and keeps the row, so the
        supplier links and the price history survive -- re-enrolling a SKU
        later finds everything still attached. That is deliberate: a mis-click
        here would otherwise throw away readings that took days to collect.
        """
        b = _body()
        wsid, mkt = _where()
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        if not skus:
            return jsonify({"ok": False, "error": "no skus"}), 400
        done, failed = 0, []
        for s in skus:
            try:
                _repo.unenrol(CONFIG_PATH, wsid, mkt, s)
                done += 1
            except Exception as e:
                failed.append("%s: %s" % (s, str(e)[:60]))
        return jsonify({
            "ok": True, "unenrolled": done, "failed": failed,
            "note": ("Stopped tracking %d SKU%s. Their supplier links and price "
                     "history are kept â€” enroll one again and everything is still "
                     "attached." % (done, "" if done == 1 else "s")),
        })

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
                "%d SKUs at once is more than this was meant for -- enroll in "
                "batches so a failure part-way is easy to see" % len(skus))}), 400

        from domain import source_link as _link
        out = {"enrolled": 0, "already": 0, "linked": 0, "no_link": 0, "rows": []}
        have = {r["sku"] for r in _repo.enrolled(CONFIG_PATH, wsid, mkt)}
        for sku in skus:
            was = sku in have
            _repo.enrol(CONFIG_PATH, wsid, mkt, sku, mode="dry_run")
            # The same default a single enrolment gets. "Track everything" is
            # how most SKUs arrive on this screen, so leaving it out here would
            # mean the setting only applied to the ones added one at a time.
            if not was:
                _apply_default_target(wsid, mkt, sku)
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

    @app.route("/sourcing/sources/count")
    def sourcing_sources_count():
        """How many suppliers, on how many SKUs, holding how many readings.

        Read-only. It exists so the confirmation can name real figures before
        anything is deleted -- the screen shows one page of rows, so counting
        those would understate what is about to go.
        """
        wsid, mkt = _where()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400
        out = _repo.count_sources(CONFIG_PATH, wsid, mkt)
        out.update({"ok": True, "account": wsid, "marketplace": mkt})
        return jsonify(out)

    @app.route("/sourcing/sources/clear", methods=["POST"])
    def sourcing_sources_clear():
        """Delete every supplier link for this account and marketplace.

            "I also want to delete all the suppliers from the repricer ... so i
             can add new suppliers"

        The SKUs stay enrolled and their pricing rules stay set -- see
        source_repo.clear_sources -- so uploading a fresh supplier sheet works
        immediately instead of needing every SKU re-enrolled first.

        THE COUNT AGREED TO TRAVELS WITH THE REQUEST. If it moved since the
        dialog opened -- a sweep finishing, another tab -- deleting a different
        number from the one shown is exactly the thing not to do.
        """
        wsid, mkt = _where()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400
        b = _body()
        have = _repo.count_sources(CONFIG_PATH, wsid, mkt)
        expected = b.get("expect", None)
        if expected is not None and int(expected) != int(have.get("sources", 0)):
            return jsonify({"ok": False, "changed": True,
                            "count": have.get("sources", 0),
                            "error": ("This account now has %d supplier link%s, not "
                                      "the %s the warning said. Nothing was "
                                      "deleted -- close this and try again so you "
                                      "are agreeing to the right number."
                                      % (have.get("sources", 0),
                                         "" if have.get("sources") == 1 else "s",
                                         expected))}), 409
        gone = _repo.clear_sources(CONFIG_PATH, wsid, mkt)
        return jsonify({"ok": True, "account": wsid, "marketplace": mkt,
                        "deleted": gone.get("sources", 0),
                        "checks_deleted": gone.get("checks", 0),
                        "note": ("%d supplier link%s and %d price reading%s deleted. "
                                 "The SKUs are still tracked and their targets are "
                                 "unchanged, so a new supplier sheet works straight "
                                 "away."
                                 % (gone.get("sources", 0),
                                    "" if gone.get("sources") == 1 else "s",
                                    gone.get("checks", 0),
                                    "" if gone.get("checks") == 1 else "s"))})

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
    @app.route("/sourcing/fees", methods=["POST"])
    def sourcing_fees():
        """Ask Amazon what it charges on each product, and remember the answer.

            "get accurate fees from amazon per item"

        THE ONLY PLACE THAT CALLS AMAZON ABOUT A FEE. Pricing reads the cache
        this fills (domain/amazon_fees.rate_for_asin with allow_quote=False),
        because the pricing path runs for every enrolled SKU on every page load
        and sixty-seven live calls before a screen can draw is not a page.

        A RATE, NOT AN AMOUNT. Amazon's referral fee is a percentage by
        category, so one quote gives a rate that holds at any price -- which is
        what makes it cacheable at all, and what breaks the circle of "the fee
        depends on the price and we are computing the price".

        Body: {skus:[...]} for some, or {} for every enrolled SKU. force=true
        re-asks even where a fresh answer is already held.
        """

        b = _body()
        wsid, mkt = _where()
        force = bool(b.get("force"))
        want = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        if not want:
            want = [str(e.get("sku")) for e in _repo.enrolled(CONFIG_PATH, wsid, mkt)]
        if not want:
            return jsonify({"ok": False, "error": "no SKUs are being tracked"}), 400

        done, skipped, failed = [], [], []
        for sku in want:
            # ONE PLACE KNOWS HOW TO ASK (Rule 12). quote_for_sku finds the
            # account, our own ASIN and the current price, and stores the
            # answer -- the weekly job and the enroll route call the same thing.
            rate, basis, detail, note = _fees.quote_for_sku(
                CONFIG_PATH, _cfg, wsid, mkt, sku, force=force)
            if note:
                skipped.append({"sku": sku, "why": note})
                continue
            row = {"sku": sku, "rate": rate, "basis": basis, "detail": detail}
            (done if basis == _fees.QUOTED else failed).append(row)
        return jsonify({
            "ok": True, "quoted": len(done), "skipped": len(skipped),
            "failed": len(failed), "rows": done, "not_quoted": failed,
            "left_alone": skipped,
            # The headline a screen should show. Said here so the route and the
            # button cannot describe the same run differently.
            "note": ("Amazon quoted %d of %d. %s"
                     % (len(done), len(want),
                        ("The rest fall back to your own measured rate."
                         if (failed or skipped) else "")).strip())})

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

        # A BUFFER IS A COUNT OF DAYS, and the same argument as the boxes below
        # applies: "2 days" stored as text would read back as something, be
        # int()ed to nothing at decision time, and quietly promise a handling
        # time two days shorter than the one that was asked for.
        if "handling_buffer_days" in vals:
            v = vals["handling_buffer_days"]
            if v in (None, ""):
                vals["handling_buffer_days"] = 0
            else:
                try:
                    v = int(float(str(v).strip()))
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": (
                        "extra handling days must be a whole number, e.g. 0 or "
                        "2 -- got %r" % vals["handling_buffer_days"])}), 400
                # Negative would take days OFF a handling time the postage
                # subtraction has already reduced -- promising sooner than the
                # supplier said, which is the one direction that costs a metric.
                if v < 0 or v > 30:
                    return jsonify({"ok": False, "error": (
                        "extra handling days must be between 0 and 30")}), 400
                vals["handling_buffer_days"] = v

        # A MISTYPED MONEY BOX MUST NOT LOOK LIKE AN EMPTY ONE, for the same
        # reason as the targets above. "40" and "£40" and "40.00" all mean forty;
        # "forty" means the box is not set, and storing it as text would leave
        # someone believing their market price was being held while the repricer
        # priced to the target and cut it in half.
        for key, label in (("hold_price", "held price"),
                           ("min_price", "minimum price"),
                           ("max_price", "maximum price")):
            if key not in vals:
                continue
            v = vals[key]
            if v in (None, ""):
                vals[key] = None
                continue
            try:
                v = float(str(v).replace("£", "").replace("$", "")
                          .replace(",", "").strip())
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": (
                    "the %s must be an amount, e.g. 40 or 40.00 -- got %r"
                    % (label, vals[key]))}), 400
            if v < 0:
                return jsonify({"ok": False, "error": (
                    "the %s cannot be negative" % label)}), 400
            # Zero clears it rather than meaning "hold at nothing", which would be
            # a floor of zero -- indistinguishable from off in effect, and
            # confusing to read back.
            vals[key] = (v if v > 0 else None)

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

    @app.route("/sourcing/shipping_policy", methods=["GET", "POST"])
    def sourcing_shipping_policy():
        """How many days the postage itself takes. Global, not per SKU.

        WHY IT IS A SETTING AT ALL. Amazon builds the delivery date from two
        numbers -- the handling time we set, and the transit time of the postage
        service on the listing. The repricer takes the second off the first so
        the supplier's days are not promised twice (domain/sourcing.handling_days).
        That subtraction is only right if the number matches the courier
        actually used, so a seller who moves from a 2-day Royal Mail service to
        a next-day one has to be able to say so.

        NOT PER SKU. It describes the postage service, not the product. A
        product that needs longer than the others has handling_buffer_days,
        which is per SKU and is added rather than subtracted.
        """
        if request.method == "GET":
            raw = _read_config()
            return jsonify({"ok": True,
                            "days": int(raw.get("shipping_policy_days")
                                        or _sourcing.SHIPPING_POLICY_DAYS)})
        b = _body()
        try:
            d = int(str(b.get("days")).strip())
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": (
                "the postage time must be a whole number of days, e.g. 2 -- "
                "got %r" % b.get("days"))}), 400
        # A NEGATIVE POLICY WOULD ADD DAYS instead of taking them off, and an
        # absurdly long one would set every handling time to the buffer alone.
        if d < 0 or d > 30:
            return jsonify({"ok": False, "error": (
                "the postage time must be between 0 and 30 days")}), 400
        raw = _read_config()
        raw["shipping_policy_days"] = d
        _write_config(raw)
        return jsonify({"ok": True, "days": d, "note": (
            "Postage now counted as %d day%s. Handling times are worked out "
            "again on the next check." % (d, "" if d == 1 else "s"))})

    @app.route("/sourcing/apply", methods=["POST"])
    def sourcing_apply():
        """Push now for every armed SKU. Same gates as the timer, no shortcuts."""
        wsid, mkt = _where()
        res = _apply.run_live(CONFIG_PATH, _cfg, _creds_for,
                              workspace_id=wsid, marketplace=mkt)
        return jsonify({"ok": True, **res})

