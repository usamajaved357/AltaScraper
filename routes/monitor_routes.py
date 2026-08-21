"""routes/monitor_routes.py — ASIN Monitor endpoints.

Stage 2: CRUD over the tracked-ASIN list. Stage 3: alerts / status / check-now / history from
the hourly checker. No Slack anywhere — in-app only.

register(app, ...) injection pattern.
"""
from flask import request, jsonify


def register(app, *, CONFIG_PATH, _cfg=None, _reload_cfg=None):
    from config import settings as _settings
    from monitor import asin_monitor as _mon
    from monitor import checker as _chk

    # config.json is read and written in ONE place. Not a private pair of
    # helpers here -- routes/sourcing_routes.py grew those for the repricer's
    # master switch, and copying them for a second setting is what Rule 12 is
    # about. The shared writer is atomic, which matters for the file holding
    # every credential in the app.
    def _read_config():
        return _settings.read_raw(CONFIG_PATH)

    def _write_config(raw):
        _settings.write_raw(raw, CONFIG_PATH)

    @app.route("/monitor/list")
    def monitor_list():
        return jsonify({"ok": True,
                        "asins": _mon.list_asins(CONFIG_PATH),
                        "eu_marketplaces": _mon.EU_MARKETPLACES})

    @app.route("/monitor/add", methods=["POST"])
    def monitor_add():
        b = request.get_json(force=True) or {}
        res = _mon.add(CONFIG_PATH,
                       b.get("asin", ""),
                       b.get("label", ""),
                       b.get("marketplaces"),
                       b.get("condition", "New"))
        return jsonify(res), (200 if res.get("ok") else 400)

    @app.route("/monitor/remove", methods=["POST"])
    def monitor_remove():
        b = request.get_json(force=True) or {}
        res = _mon.remove(CONFIG_PATH, asin=b.get("asin"), id=b.get("id"))
        return jsonify(res), (200 if res.get("ok") else 400)

    # ---- Stage 3: alerts / status / manual check / history ----
    @app.route("/monitor/alerts")
    def monitor_alerts():
        unread = request.args.get("unread") in ("1", "true", "yes")
        return jsonify({"ok": True,
                        "alerts": _chk.get_alerts(CONFIG_PATH, unread_only=unread, limit=200),
                        "unread": _chk.unread_count(CONFIG_PATH),
                        "status": _chk.status()})

    @app.route("/monitor/alerts/read", methods=["POST"])
    def monitor_alerts_read():
        b = request.get_json(force=True) or {}
        _chk.mark_alerts_read(CONFIG_PATH, ids=b.get("ids"))   # ids omitted -> mark all read
        return jsonify({"ok": True, "unread": _chk.unread_count(CONFIG_PATH)})

    @app.route("/monitor/status")
    def monitor_status():
        return jsonify({"ok": True, "status": _chk.status(),
                        "unread": _chk.unread_count(CONFIG_PATH)})

    @app.route("/monitor/export")
    def monitor_export():
        """Download the current results as an .xlsx (Summary + detailed Sellers sheet)."""
        from flask import Response
        from monitor import export as _exp
        import datetime
        cfg = _cfg() if _cfg else {}
        try:
            data = _exp.build_xlsx(CONFIG_PATH, cfg)
        except Exception as e:
            return jsonify({"ok": False, "error": f"export failed: {str(e)[:160]}"}), 500
        fname = "asin_monitor_" + datetime.datetime.now().strftime("%Y%m%d_%H%M") + ".xlsx"
        return Response(data,
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    @app.route("/monitor/seller_info")
    def monitor_seller_info():
        """Current classification + name + FOOTPRINT (blast radius) + evidence for a seller id."""
        sid = (request.args.get("seller_id") or "").strip()
        if not sid:
            return jsonify({"ok": False, "error": "seller_id required"}), 400
        cfg = _cfg() if _cfg else {}
        return jsonify({"ok": True, **_chk.seller_info(CONFIG_PATH, cfg, sid)})

    @app.route("/monitor/seller_label", methods=["POST"])
    def monitor_seller_label():
        """Name/classify a seller GLOBALLY by seller id -> writes config.json known_sellers, applies
        to every ASIN/marketplace + past snapshots. Body: {seller_id, name, kind, marketplace}."""
        from monitor import known_sellers as _ks
        import datetime
        b = request.get_json(force=True) or {}
        res = _ks.set_seller(CONFIG_PATH, b.get("seller_id", ""), b.get("name", ""),
                             b.get("kind", "name"), b.get("marketplace", ""))
        if res.get("ok"):
            if _reload_cfg:
                _reload_cfg()                       # BUG 2 fix: drop the cached config so overview re-reads
            _chk.log_manual_label(CONFIG_PATH, {
                "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "seller_id": b.get("seller_id", ""), "name": b.get("name", ""),
                "kind": res.get("kind"), "previous": res.get("previous"), "by": "operator"})
        return jsonify(res), (200 if res.get("ok") else 400)

    def _seller_file(b):
        """The uploaded file's bytes, from the same data-URI shape the ASIN
        importer already posts. -> (bytes, filename, error)."""
        import base64
        raw = str(b.get("data") or "")
        if "," in raw and raw[:5].lower() == "data:":
            raw = raw.split(",", 1)[1]
        if not raw:
            return b"", "", "No file came through."
        try:
            return base64.b64decode(raw), str(b.get("filename") or ""), ""
        except Exception as e:
            return b"", "", "Could not read that file: %s" % str(e)[:120]

    @app.route("/monitor/sellers_preview", methods=["POST"])
    def monitor_sellers_preview():
        """Read a CSV of seller IDs and say what it WOULD change. Writes nothing.

        The counterpart to naming sellers one at a time. Shown before applying
        because a mapping file gets pasted together from a spreadsheet and the
        first version usually has a column in the wrong place -- and this writes
        into config.json, which is not somewhere to find out afterwards.
        """
        from monitor import bulk_import as _bulk
        from monitor import known_sellers as _ks
        b = request.get_json(force=True) or {}
        data, fname, err = _seller_file(b)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        got = _bulk.parse_sellers(data, fname)
        if got.get("error"):
            return jsonify({"ok": False, "error": got["error"]}), 400
        cfg = _cfg() if callable(_cfg) else (_cfg or {})
        rows = []
        for r in got["rows"]:
            prev = _ks.classify(r["seller_id"], "", cfg)
            rows.append(dict(r, previous_kind=(prev or {}).get("kind", "unknown"),
                             previous_label=(prev or {}).get("label", ""),
                             changes=((prev or {}).get("kind") != r["kind"]
                                      or (prev or {}).get("label") != r["name"])))
        return jsonify({"ok": True, "rows": rows, "invalid": got["invalid"],
                        "columns": got["columns"], "count": len(rows)})

    @app.route("/monitor/sellers_import", methods=["POST"])
    def monitor_sellers_import():
        """Apply the previewed rows. One write of config.json for the lot."""
        from monitor import known_sellers as _ks
        import datetime
        b = request.get_json(force=True) or {}
        rows = b.get("rows") or []
        if not rows:
            return jsonify({"ok": False, "error": "nothing to import"}), 400
        res = _ks.set_sellers_bulk(CONFIG_PATH, rows)
        if not res.get("ok"):
            return jsonify(res), 400
        if _reload_cfg:
            _reload_cfg()      # drop the cached config so the overview re-reads
        # THE SAME AUDIT TRAIL the one-at-a-time path writes. A hundred sellers
        # renamed silently is exactly the change somebody will want to trace
        # back in a month.
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        for c in res.get("changes") or []:
            _chk.log_manual_label(CONFIG_PATH, {
                "ts": ts, "seller_id": c["seller_id"], "name": c["name"],
                "kind": c["kind"], "previous": c["previous"], "by": "csv import"})
        return jsonify(res)

    @app.route("/monitor/label_log")
    def monitor_label_log():
        """Audit log of manual classifications (who/what/when/previous)."""
        return jsonify({"ok": True, "log": _chk.get_manual_labels(CONFIG_PATH, limit=100)})

    @app.route("/monitor/overview")
    def monitor_overview():
        """Per-ASIN latest offer picture (sellers classified me/amazon/authorised/unknown) + the
        top summary. Read-only; uses stored snapshots + the name cache, no live Amazon calls."""
        cfg = _cfg() if _cfg else {}
        return jsonify({"ok": True, **_chk.overview(CONFIG_PATH, cfg)})

    @app.route("/monitor/schedule", methods=["GET", "POST"])
    def monitor_schedule():
        """How often the monitor checks Amazon on its own -- or whether it does.

            "i dont want the asin monitor to be working always, give 2 options.
             option 1 is to recheck the status of the buybox by clicking a
             button. option two is to setup a time of your choice. e.g. every 4
             hours. 10 hours etc etc. a user should be able to choose time on
             his choice"

        Option 1 is /monitor/check_now and always works, whatever is set here.
        This is option 2, and off is the default.

        Any whole number of hours is accepted, not a fixed menu -- "a user
        should be able to choose time on his choice". monitor/schedule.py puts
        it in range rather than refusing it: a settings screen that will not
        save is worse than one that rounds a silly number and says what it did.
        """
        from monitor import schedule as _sch
        cfg = _cfg() if _cfg else {}
        if request.method == "GET":
            return jsonify({"ok": True, **_sch.read(cfg),
                            "suggested_hours": list(_sch.SUGGESTED_HOURS),
                            "min_hours": _sch.MIN_HOURS,
                            "max_hours": _sch.MAX_HOURS,
                            "explains": _sch.describe(cfg)})
        b = request.get_json(silent=True) or {}
        raw = _read_config()
        plan = _sch.store(raw, b.get("mode"), b.get("hours"))
        _write_config(raw)
        if _reload_cfg:
            _reload_cfg()
        # The loop re-reads this within a minute; telling it now means the
        # screen's next-run estimate is right immediately rather than after a
        # tick nobody can see.
        _chk.set_interval(plan["hours"] * 3600 if plan["mode"] == _sch.EVERY else 0)
        fresh = _cfg() if _cfg else raw
        return jsonify({"ok": True, **plan, "explains": _sch.describe(fresh)})

    @app.route("/monitor/check_now", methods=["POST"])
    def monitor_check_now():
        if _cfg is None:
            return jsonify({"ok": False, "error": "config unavailable"}), 500
        b = request.get_json(silent=True) or {}
        force = bool(b.get("rescan") or b.get("force"))   # 'Re-scan all marketplaces' ignores dead-skip
        return jsonify(_chk.check_now_async(_cfg(), CONFIG_PATH, force_rescan=force))

    @app.route("/monitor/bulk_preview", methods=["POST"])
    def monitor_bulk_preview():
        """Parse an uploaded CSV/TXT/XLSX and return a PREVIEW (found / new / existing / invalid)
        BEFORE anything is committed. Body: {filename, data (base64 or data-uri)}."""
        import base64
        from monitor import bulk_import as _bulk
        b = request.get_json(force=True) or {}
        data = b.get("data", "") or ""
        if data.startswith("data:"):
            data = data.split(",", 1)[1] if "," in data else ""
        try:
            raw = base64.b64decode(data)
        except Exception:
            return jsonify({"ok": False, "error": "could not decode the uploaded file"}), 400
        try:
            res = _bulk.parse(raw, b.get("filename", ""))
        except Exception as e:
            return jsonify({"ok": False, "error": f"could not read the file: {str(e)[:160]}"}), 400
        existing = {str(r.get("asin", "")).upper() for r in _mon.list_asins(CONFIG_PATH)}
        for r in res["rows"]:
            r["existing"] = r["asin"] in existing
        new = sum(1 for r in res["rows"] if not r["existing"])
        return jsonify({"ok": True, "rows": res["rows"], "invalid": res["invalid"],
                        "found": len(res["rows"]), "new": new,
                        "existing": len(res["rows"]) - new,
                        "status_counts": res.get("status_counts", {}),
                        "detected": res.get("detected", {})})

    @app.route("/monitor/bulk_import", methods=["POST"])
    def monitor_bulk_import():
        """Commit the confirmed rows. Adds new ASINs; UPDATES ones already tracked (same rule as
        the single-add form). Body: {rows:[{asin,label,marketplaces}]}."""
        b = request.get_json(force=True) or {}
        added = updated = failed = 0
        errors = []
        for r in (b.get("rows") or []):
            res = _mon.add(CONFIG_PATH, r.get("asin", ""), r.get("label", ""),
                           r.get("marketplaces"), r.get("condition", "New"),
                           sku=r.get("sku", ""), status=r.get("status", ""))
            if res.get("ok"):
                if res.get("updated"):
                    updated += 1
                else:
                    added += 1
            else:
                failed += 1
                errors.append({"asin": r.get("asin"), "error": res.get("error")})
        return jsonify({"ok": True, "added": added, "updated": updated,
                        "failed": failed, "errors": errors})

    @app.route("/monitor/history")
    def monitor_history():
        asin = (request.args.get("asin") or "").strip()
        mkt = (request.args.get("marketplace") or "").strip() or None
        if not asin:
            return jsonify({"ok": False, "error": "asin required"}), 400
        return jsonify({"ok": True,
                        "history": _chk.get_history(CONFIG_PATH, asin, mkt),
                        "names": _chk.get_seller_names(CONFIG_PATH)})
