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

from flask import request, jsonify

from domain import source_apply as _apply
from domain import source_fetch as _fetch
from domain import source_repo as _repo
from domain import source_run as _run
from domain import sourcing as _sourcing


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach the /sourcing/* routes to the existing Flask app."""

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
        wsid, mkt = _where()
        run = _run.dry_run(CONFIG_PATH, wsid, mkt, record=False)
        rows = []
        for d in run["decisions"]:
            pairs = _repo.pairs_for(CONFIG_PATH, d["workspace_id"],
                                    d["marketplace"], d["sku"])
            # The SKU's own rule travels with the row because min_price's ABSENCE
            # is what stops it being armed, and that belongs next to the Arm
            # button rather than in the error you get after pressing it.
            rows.append({**d, "sources": [{**s, "check": c} for s, c in pairs],
                         "rule": _sourcing.rule_with_defaults(
                             _repo.rule_for(CONFIG_PATH, d["workspace_id"],
                                            d["marketplace"], d["sku"]))})
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "rows": rows, "counts": run["counts"],
                        "note": run["note"],
                        "master_enabled": _apply.is_enabled(_cfg),
                        "rule": _sourcing.rule_with_defaults(
                            _repo.rule_for(CONFIG_PATH, wsid, mkt, "")),
                        "defaults": _sourcing.DEFAULT_RULE})

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
