"""routes/monitor_routes.py — ASIN Monitor endpoints.

Stage 2: CRUD over the tracked-ASIN list. Stage 3: alerts / status / check-now / history from
the hourly checker. No Slack anywhere — in-app only.

register(app, ...) injection pattern.
"""
from flask import request, jsonify


def register(app, *, CONFIG_PATH, _cfg=None):
    from monitor import asin_monitor as _mon
    from monitor import checker as _chk

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

    @app.route("/monitor/overview")
    def monitor_overview():
        """Per-ASIN latest offer picture (sellers classified me/amazon/authorised/unknown) + the
        top summary. Read-only; uses stored snapshots + the name cache, no live Amazon calls."""
        cfg = _cfg() if _cfg else {}
        return jsonify({"ok": True, **_chk.overview(CONFIG_PATH, cfg)})

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
