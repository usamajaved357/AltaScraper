"""routes/tracking_routes.py -- where the parcels are.

    GET  /tracking/template.csv   the orders, with the tracking column empty
    POST /tracking/upload         read the filled-in file back
    GET  /tracking/summary        how many parcels are in each state
    POST /tracking/refresh        ask the carrier where they are now
    POST /tracking/set            record or remove ONE order's tracking

Its own file because it is its own feature (CLAUDE.md Rule 7), and because
orders_routes.py is already the longest route file in the app.

TWO QUESTIONS, AND ONLY ONE OF THEM COSTS ANYTHING
"Has Amazon marked this shipped" is already on the order row and is free.
"Where is the parcel" needs a carrier, and there is no free universal carrier
API -- so /tracking/refresh does nothing at all until a provider is configured,
and says so in words rather than leaving every parcel showing a status nobody
asked for.
"""
from flask import jsonify, request

import domain.request_account as _req_acct
from domain import tracking as _tr


def register(app, *, CONFIG_PATH, _cfg, _state, _active_account):

    def _scope():
        """Which account and marketplace this request is about.

        `account` is the standard spelling across the app; request_account.named
        accepts `account_id` as well for the older callers.

        THE ACCOUNT MUST BE NAMED (29 Sep 2026). This used to fall back to the
        server's open account -- owned by whichever browser tab switched last --
        so a tracking sheet read with no account named was filed under another
        company's orders (CLAUDE.md Rule 14). Every browser caller names one
        (ordertracking.js _otQS, orders.js _ordTrackWrite); with none, _need
        refuses in words. Likewise the marketplace is the one asked for, else
        the ACCOUNT's own -- never the server's last-selected one.
        """
        from flask import g
        from domain import order_scope as _osc
        g.trk_refused = None
        b = request.get_json(silent=True) or {}
        aid = _req_acct.named(request) or str(b.get("account") or "").strip()
        asked = (request.args.get("marketplace") or b.get("marketplace") or "").upper()
        if asked == "__ALL__":
            asked = ""
        if not aid:
            return "", ""
        # THE SAME RULES AS THE OTHER ORDERS WRITES (domain/order_scope.py):
        # an account this app has, and one of its own marketplaces -- the one
        # asked for, else its default, which is where its orders came from.
        # An account it does not have ("__all__" included) and a marketplace
        # that is not the account's are refused, not filed somewhere.
        acc = _osc.account(_cfg, aid)
        if acc is None:
            g.trk_refused = (jsonify({"ok": False, "error": (
                "There is no account called %r in this app." % aid)}), 404)
            return "", ""
        mkt = _osc.marketplace(acc, asked)
        if asked and not mkt:
            g.trk_refused = (jsonify({"ok": False, "error": (
                "That marketplace is not one of %s's, so nothing was done."
                % (acc.get("label") or aid))}), 400)
            return aid, ""
        return aid, mkt

    def _need(aid, mkt, what="that"):
        from flask import g
        if getattr(g, "trk_refused", None):
            return g.trk_refused
        missing = [n for n, v in (("account", aid), ("marketplace", mkt)) if not v]
        if not missing:
            return None
        return jsonify({"ok": False, "error": (
            "could not %s: no %s came with the request. Tracking is recorded "
            "against one order of one account, so both are needed."
            % (what, " or ".join(missing)))}), 400

    @app.route("/tracking/template.csv")
    def tracking_template():
        """The tracking sheet: one row per order, tracking column empty.

        Handed out with whatever is already recorded shown beside the empty
        columns, so the sheet is corrected rather than retyped -- which is what
        makes re-uploading an unedited file harmless.
        """
        import csv as _csv
        import io as _io
        from flask import Response
        from domain import tracking_sheet as _ts

        aid, mkt = _scope()
        bad = _need(aid, mkt, "build that sheet")
        if bad:
            return bad
        start = (request.args.get("start") or "").strip() or None
        end = (request.args.get("end") or "").strip() or None
        only = str(request.args.get("untracked") or "").lower() in (
            "1", "true", "yes")

        headers, rows = _ts.template_rows(CONFIG_PATH, aid, mkt, start, end, only)
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(headers)
        for r in rows:
            w.writerow(r)
        # utf-8-sig: Excel opens a plain UTF-8 CSV in the wrong encoding and
        # mangles every pound sign and every accented product name.
        data = buf.getvalue().encode("utf-8-sig")
        name = "tracking-%s-%s.csv" % (aid, mkt)
        return Response(data, mimetype="text/csv", headers={
            "Content-Disposition": 'attachment; filename="%s"' % name})

    @app.route("/tracking/upload", methods=["POST"])
    def tracking_upload():
        """Read a filled-in tracking sheet and record every number in it.

        SERVER-SIDE, like both cost sheets and for the same reason: a product
        name such as "Grill, Large" is quoted and contains a comma, so splitting
        lines on commas in the browser shifts every column after it and reads
        the tracking out of the wrong place.
        """
        from domain import source_bulk as _sb
        from domain import tracking_sheet as _ts

        aid, mkt = _scope()
        bad = _need(aid, mkt, "read that file")
        if bad:
            return bad

        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "no file was sent"}), 400
        raw = f.read()
        from domain import upload_log as _ul

        def _keep(**kw):
            _ul.record(CONFIG_PATH, aid, mkt, "tracking", f.filename or "", raw, **kw)

        headers, rows, err = _sb.read_table(raw, f.filename or "")
        if err:
            _keep(error=err)
            return jsonify({"ok": False, "error": err}), 400
        if not headers:
            _keep(error="there were no columns in that file")
            return jsonify({"ok": False,
                            "error": "there were no columns in that file"}), 400

        res = _ts.apply_sheet(CONFIG_PATH, aid, mkt, headers, rows)
        if not res.get("ok"):
            _keep(error=res.get("error") or "the sheet was refused")
            return jsonify(res), 400

        # SAY WHAT HAPPENED TO EVERY ROW, in the order it matters. A bulk action
        # that reports only its successes hides exactly the rows worth looking at.
        bits = []
        if res["set"]:
            bits.append("Recorded tracking on %d order%s."
                        % (res["set"], "" if res["set"] == 1 else "s"))
        if res["blank"]:
            bits.append("%d row%s had no tracking filled in and %s left alone."
                        % (res["blank"], "" if res["blank"] == 1 else "s",
                           "was" if res["blank"] == 1 else "were"))
        if res["unknown_order"]:
            bits.append("%d order%s in the file %s not found in this account "
                        "and marketplace."
                        % (res["unknown_order"],
                           "" if res["unknown_order"] == 1 else "s",
                           "was" if res["unknown_order"] == 1 else "were"))
        if res["bad_number"]:
            bits.append("%d tracking number%s could not be read."
                        % (res["bad_number"],
                           "" if res["bad_number"] == 1 else "s"))
        if not bits:
            bits.append("Nothing in that file changed anything.")

        # AND WHETHER ANYTHING WILL ACTUALLY BE CHECKED. Recording a number and
        # then showing "Not checked" for ever, with no explanation, is the
        # failure this sentence exists to prevent.
        fn, why = _tr.provider_for(_cfg)
        if res["set"] and not fn:
            bits.append(why)
        res["note"] = " ".join(bits)
        res["can_check"] = bool(fn)
        _keep(ok=res["set"], skipped=res["blank"],
              errors=res["unknown_order"] + res["bad_number"],
              summary=res["note"], rows=res.get("rows") or [])
        return jsonify(res)

    @app.route("/tracking/summary")
    def tracking_summary():
        """How many parcels are in each state, and how many nobody has asked about."""
        aid, mkt = _scope()
        bad = _need(aid, mkt, "count those")
        if bad:
            return bad
        out = _tr.summary(CONFIG_PATH, aid, mkt)
        out["labels"] = dict(_tr.STATUS_LABEL)
        fn, why = _tr.provider_for(_cfg)
        out["can_check"] = bool(fn)
        # WHY EVERYTHING SAYS "Not checked", stated on the screen that shows it
        # rather than left for someone to work out.
        out["why"] = "" if fn else why
        return jsonify({"ok": True, **out})

    @app.route("/tracking/refresh", methods=["POST"])
    def tracking_refresh():
        """Ask the carrier where each parcel is.

        Refuses in words when no provider is configured. It does NOT invent a
        status from the ship date: "Delivered" is the single most consequential
        word on this screen -- it decides whether a refund is argued or paid --
        and a guess wearing a fact's clothes is worse than no status at all.
        """
        aid, mkt = _scope()
        bad = _need(aid, mkt, "check those")
        if bad:
            return bad
        b = request.get_json(silent=True) or {}
        try:
            limit = max(1, min(500, int(b.get("limit") or 50)))
        except (TypeError, ValueError):
            limit = 50
        res = _tr.refresh(CONFIG_PATH, _cfg, aid, mkt, limit=limit)
        return jsonify(res if res.get("ok") else res), (200 if res.get("ok") else 400)

    @app.route("/tracking/set", methods=["POST"])
    def tracking_set():
        """Record ONE order's tracking, or remove one number from it.

        Removal is explicit and one number at a time, which is why the bulk
        upload can safely treat a blank cell as "leave this alone".
        """
        aid, mkt = _scope()
        from flask import g
        if getattr(g, "trk_refused", None):
            return g.trk_refused        # an account it lacks, or not its marketplace
        b = request.get_json(force=True) or {}
        oid = str(b.get("order_id") or "").strip()
        missing = [n for n, v in (("account", aid), ("marketplace", mkt),
                                  ("order", oid)) if not v]
        if missing:
            return jsonify({"ok": False, "error": (
                "could not save that tracking: no %s came with the request. "
                "Tracking is recorded against one order of one account, so all "
                "three are needed." % " or ".join(missing))}), 400

        tn = str(b.get("tracking_number") or "").strip()
        if not tn:
            return jsonify({"ok": False,
                            "error": "no tracking number was sent"}), 400
        if b.get("remove"):
            n = _tr.remove(CONFIG_PATH, aid, mkt, oid, tn)
            return jsonify({"ok": True, "removed": n})

        from domain import tracking_sheet as _ts
        if not _ts.looks_like_tracking(tn):
            return jsonify({"ok": False, "error": (
                "that does not look like a tracking number — it needs at least "
                "six letters or digits")}), 400
        n = _tr.add(CONFIG_PATH, aid, mkt, oid, tn,
                    carrier=b.get("carrier") or "", sku=b.get("sku") or "",
                    source="upload")
        fn, why = _tr.provider_for(_cfg)
        return jsonify({"ok": True, "saved": n,
                        "carrier_code": _tr.carrier_code(b.get("carrier") or ""),
                        "can_check": bool(fn),
                        "note": "" if fn else why})
