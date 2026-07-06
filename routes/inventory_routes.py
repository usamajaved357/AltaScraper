"""routes/inventory_routes.py — FBA inventory / replenishment endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern; route bodies moved VERBATIM (CLAUDE.md §10).
Shared helpers (inventory model refs _INV/_INV2, CSV parsers, the SP-API FBA fetch,
output dir, alert counts, per-account cache, _cfg) are injected.

Routes: POST /inventory/build, GET /inventory/download/<fname>,
        POST /inventory/v2/run, GET /inventory/v2/alerts
"""
import os

from flask import request, jsonify


def register(app, *, _INV, _INV_IMPORT_ERR, _INV2, _INV2_IMPORT_ERR,
             _parse_3pl_csv, _parse_sales_csv, _parse_uplift_csv,
             _fetch_fba_inventory_via_spapi, _num, _INV_OUT_DIR,
             _inv2_cache, _INV_ALERT_COUNTS, _cfg):
    """Attach the /inventory/* routes to the existing Flask app."""

    @app.route("/inventory/build", methods=["POST"])
    def inventory_build():
        """Run the replenishment model.

        Auto-pulls FBA inventory from SP-API. User uploads:
          3pl_file          -- 3PL stock CSV (required)
          sales_file        -- Daily sales CSV with per-day rate (required)
          yoy_file          -- YoY uplift CSV (optional; defaults 0)
          pd_file           -- Prime Day uplift CSV (optional; defaults 0)

        Form fields (all optional -- defaults from ReplenishmentTargets):
          target_normal_days   (default 85)
          reorder_cycle_days   (default 5)
          target_long_days     (default 110)
          marketplace          (default UK)
          cycle_label          (free text for the assumptions sheet)
        """
        if _INV is None:
            return jsonify({"ok": False, "error": f"inventory_model not available: {_INV_IMPORT_ERR}"}), 500
        try:
            marketplace = (request.form.get("marketplace") or "UK").strip().upper()
            try:
                targets = _INV.ReplenishmentTargets(
                    target_normal_days=int(request.form.get("target_normal_days") or 85),
                    reorder_cycle_days=int(request.form.get("reorder_cycle_days") or 5),
                    target_long_days=int(request.form.get("target_long_days") or 110),
                )
            except ValueError:
                return jsonify({"ok": False, "error": "target values must be integers"}), 400
            cycle_label = (request.form.get("cycle_label") or "").strip()

            # ---- Required uploads ----
            pl3_file = request.files.get("pl3_file")
            sales_file = request.files.get("sales_file")
            if not pl3_file:
                return jsonify({"ok": False, "error": "3PL stock CSV required"}), 400
            if not sales_file:
                return jsonify({"ok": False, "error": "Daily sales CSV required"}), 400
            pl3_by_sku   = _parse_3pl_csv(pl3_file.read())
            sales_by_sku = _parse_sales_csv(sales_file.read())

            # ---- Optional uplift files ----
            yoy_by_sku = {}
            pd_by_sku  = {}
            yf = request.files.get("yoy_file")
            pf = request.files.get("pd_file")
            if yf: yoy_by_sku = _parse_uplift_csv(yf.read(), "yoy_uplift")
            if pf: pd_by_sku  = _parse_uplift_csv(pf.read(), "pd_uplift")

            # ---- Pull FBA inventory from SP-API ----
            fba_result = _fetch_fba_inventory_via_spapi(marketplace)
            if not fba_result["ok"]:
                return jsonify({"ok": False, "error": f"SP-API FBA fetch failed: {fba_result['error']}",
                                "warnings": fba_result.get("warnings", [])}), 502
            fba_by_sku = fba_result["by_sku"]

            # ---- Merge all sources into canonical rows ----
            # Union of all SKUs seen: prefer FBA (has product name + asin), then 3PL, then sales.
            all_skus = set(fba_by_sku) | set(pl3_by_sku) | set(sales_by_sku)
            rows = []
            for sku in sorted(all_skus):
                fba = fba_by_sku.get(sku, {})
                pl3 = pl3_by_sku.get(sku, {})
                sal = sales_by_sku.get(sku, {})
                row = {
                    "sku":                sku,
                    "asin":               fba.get("asin", ""),
                    "product_name":       fba.get("product_name", ""),
                    "market":             marketplace,
                    "fulfillment":        "FBA" if sku in fba_by_sku else "FBM",
                    "selling_status":     "Continue",
                    "fba_available":      fba.get("fba_available", 0),
                    "fba_reserved":       fba.get("fba_reserved", 0),
                    "fba_inbound":        fba.get("fba_inbound", 0),
                    "pl3_available":      pl3.get("pl3_available", 0),
                    "pl3_in_transit":     pl3.get("pl3_in_transit", 0),
                    "pl3_ordered":        pl3.get("pl3_ordered", 0),
                    "sales_last_n":       sal.get("sales_last_n", 0),
                    "sales_window_days":  sal.get("sales_window_days", 30),
                    "yoy_uplift":         yoy_by_sku.get(sku, 0),
                    "pd_uplift":          pd_by_sku.get(sku, 0),
                    "increment_pct":      1.0,
                }
                rows.append(row)

            computed = _INV.compute_replenishment(rows, targets)

            # ---- Emit xlsx ----
            xlsx_bytes = _INV.build_replenishment_xlsx(computed, targets,
                                                          cycle_label=cycle_label)
            import time as _t
            ts = int(_t.time())
            fname = f"replenishment_{marketplace}_{ts}.xlsx"
            fpath = os.path.join(_INV_OUT_DIR, fname)
            with open(fpath, "wb") as fh:
                fh.write(xlsx_bytes)

            # Summary metrics for the UI
            skus_needing_replenish = sum(1 for r in computed if r.get("normal_replenish") == "Yes")
            total_units_flagged = sum(_num(r.get("normal_units_needed", 0)) for r in computed
                                       if r.get("normal_replenish") == "Yes")
            stockout_risk_skus = sum(1 for r in computed
                                       if _num(r.get("dos_amz_total", 0)) < 14
                                       and r.get("selling_status") == "Continue")

            return jsonify({
                "ok":               True,
                "download_url":     f"/inventory/download/{fname}",
                "filename":         fname,
                "row_count":        len(computed),
                "sku_coverage": {
                    "in_fba":       len(fba_by_sku),
                    "in_3pl":       len(pl3_by_sku),
                    "in_sales":     len(sales_by_sku),
                    "in_yoy":       len(yoy_by_sku),
                    "in_pd":        len(pd_by_sku),
                    "union":        len(all_skus),
                },
                "summary": {
                    "replenish_yes":       skus_needing_replenish,
                    "units_flagged":       int(total_units_flagged),
                    "stockout_risk_skus":  stockout_risk_skus,
                },
                "warnings":         fba_result.get("warnings", []),
            })
        except Exception as e:
            import traceback
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:250]}",
                            "trace": traceback.format_exc()[-800:]}), 500


    @app.route("/inventory/download/<path:fname>")
    def inventory_download(fname):
        from flask import send_from_directory
        if ".." in fname or fname.startswith("/") or fname.startswith("\\"):
            return "invalid filename", 400
        return send_from_directory(_INV_OUT_DIR, fname, as_attachment=True)


    # ============================================================================
    # v2 inventory endpoints: full SP-API automation, 4-bucket classification,
    # per-account caching (protects Seller Central from report clutter), and
    # in-app alerts (red badge in the sidebar when SKUs need reorder).
    # ============================================================================

    @app.route("/inventory/v2/run", methods=["POST"])
    def inventory_v2_run():
        """Run the full inventory model:
          1. Fetch FBA inventory from SP-API (cached 6h per account)
          2. Fetch sales velocity from SP-API Orders API (last N days)
          3. Optional 3PL CSV upload
          4. Compute replenishment with 4-bucket zero-velocity classification
          5. Emit downloadable xlsx + populate in-app alerts

        Form fields (all optional except account_id):
          account_id, marketplace, marketplace_id
          target_normal_dos (85), reorder_cycle_days (5), target_long_horizon_dos (110)
          sales_window_days (30)
          cache_hours (6)  -- how stale a cached report can be before refresh
          force_refresh    -- 'true' to bypass cache

        File uploads:
          three_pl_file (optional)   -- 3PL CSV matching the user's sheet columns
        """
        if _INV2 is None:
            return jsonify({"ok": False, "error": f"inventory_module not available: {_INV2_IMPORT_ERR}"}), 500

        try:
            account_id = (request.form.get("account_id") or "").strip()
            if not account_id:
                return jsonify({"ok": False, "error": "account_id is required so caching is per-workspace"}), 400
            marketplace = (request.form.get("marketplace") or "US").strip().upper()

            try:
                cfg = _INV2.InventoryConfig(
                    target_normal_dos       = int(request.form.get("target_normal_dos")       or 85),
                    reorder_cycle_days      = int(request.form.get("reorder_cycle_days")      or 5),
                    target_long_horizon_dos = int(request.form.get("target_long_horizon_dos") or 110),
                    sales_window_days       = int(request.form.get("sales_window_days")       or 30),
                    cache_hours             = int(request.form.get("cache_hours")             or 6),
                )
            except ValueError:
                return jsonify({"ok": False, "error": "config values must be integers"}), 400

            force_refresh = (request.form.get("force_refresh") or "").lower() in ("true", "1", "yes")

            # ---- Marketplace ID resolution ----
            try:
                import accounts as _acc2
                marketplace_id = _acc2.marketplace_id(marketplace) if hasattr(_acc2, "marketplace_id") else ""
            except Exception:
                marketplace_id = ""

            # ---- Load account credentials ----
            creds = None
            try:
                import accounts as _acc2
                for a in _cfg().get("accounts", []):
                    if a.get("id") == account_id:
                        creds = _acc2.account_creds(a) if hasattr(_acc2, "account_creds") else None
                        break
            except Exception as e:
                return jsonify({"ok": False, "error": f"could not resolve credentials: {e}"}), 500
            if not creds:
                return jsonify({"ok": False, "error": f"no credentials for account {account_id!r}"}), 400

            cache = _inv2_cache()

            # ---- FBA inventory (cache-aware) ----
            cache_report_type = f"FBA_INVENTORY_{marketplace}"
            fba_cached = None if force_refresh else cache.get(account_id, marketplace, cache_report_type, cfg.cache_hours)
            if fba_cached:
                fba_rows = fba_cached.get("rows", [])
                fba_source = f"cached ({fba_cached.get('_cache_age_hours', 0)}h old)"
            else:
                # Fetch fresh; on error, fall back to stale cache
                fba_result = _INV2.fetch_fba_inventory(creds, marketplace, marketplace_id)
                if fba_result["error"]:
                    stale = cache.get_stale(account_id, marketplace, cache_report_type)
                    if stale:
                        fba_rows = stale.get("rows", [])
                        fba_source = f"stale ({stale.get('_cache_age_hours', 0)}h old) -- SP-API fetch failed: {fba_result['error']}"
                    else:
                        return jsonify({"ok": False, "error": f"FBA fetch failed and no cache available: {fba_result['error']}"}), 502
                else:
                    fba_rows = fba_result["rows"]
                    cache.put(account_id, marketplace, cache_report_type, {"rows": fba_rows})
                    fba_source = f"fresh ({fba_result['report_source']}) -- {len(fba_rows)} SKUs"

            # ---- Sales velocity (cache-aware) ----
            vel_report_type = f"VELOCITY_{marketplace}_{cfg.sales_window_days}d"
            vel_cached = None if force_refresh else cache.get(account_id, marketplace, vel_report_type, cfg.cache_hours)
            if vel_cached:
                velocity = vel_cached.get("units_by_sku", {})
                vel_source = f"cached ({vel_cached.get('_cache_age_hours', 0)}h old)"
            else:
                vel_result = _INV2.fetch_sales_velocity(creds, marketplace, marketplace_id,
                                                         days_back=cfg.sales_window_days)
                if vel_result["error"]:
                    stale = cache.get_stale(account_id, marketplace, vel_report_type)
                    if stale:
                        velocity = stale.get("units_by_sku", {})
                        vel_source = f"stale ({stale.get('_cache_age_hours', 0)}h old) -- Orders API failed: {vel_result['error']}"
                    else:
                        return jsonify({"ok": False, "error": f"Sales velocity fetch failed and no cache: {vel_result['error']}"}), 502
                else:
                    velocity = vel_result["units_by_sku"]
                    cache.put(account_id, marketplace, vel_report_type,
                              {"units_by_sku": velocity, "total_orders": vel_result.get("total_orders", 0)})
                    vel_source = f"fresh -- {len(velocity)} SKUs from {vel_result.get('total_orders', 0)} orders"

            # ---- Optional 3PL CSV ----
            three_pl_rows = []
            three_pl_warnings = []
            tf = request.files.get("three_pl_file")
            if tf:
                result = _INV2.ingest_3pl_csv(tf.read())
                three_pl_rows    = result["rows"]
                three_pl_warnings = result["warnings"]

            # ---- Launch dates: not fetched in v1 (SP-API Catalog Items is slow) ----
            # For now age-classification uses whatever the FBA row contains as fallback.
            # Future: pull createdAt from Catalog Items API in a background pass.
            launch_dates_by_sku = {}

            # ---- Compute ----
            result = _INV2.run_inventory_model(
                fba_rows, velocity, three_pl_rows, launch_dates_by_sku,
                cfg, market=marketplace,
            )

            # ---- Populate the in-app alert count for the sidebar badge ----
            # Count SKUs where reorder is needed (any of: FBA reorder Yes, or 3PL reorder Yes)
            alert_count = sum(1 for r in result["rows"]
                              if r.get("replenish_yesno") == "Yes" or r.get("replenish_3pl") == "Yes")
            _INV_ALERT_COUNTS[account_id] = alert_count

            # ---- Emit xlsx ----
            import time as _t
            ts = int(_t.time())
            fname = f"inventory_v2_{account_id}_{marketplace}_{ts}.xlsx"
            fpath = os.path.join(_INV_OUT_DIR, fname)
            import datetime as _dt
            xlsx_bytes = _INV2.build_inventory_xlsx(
                result, cfg, account_label=account_id,
                generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes"),
            )
            with open(fpath, "wb") as f:
                f.write(xlsx_bytes)

            return jsonify({
                "ok": True,
                "summary": result["summary"],
                "alert_count": alert_count,
                "alerts_sample": result["alerts"][:10],   # first 10 for UI preview
                "fba_source": fba_source,
                "velocity_source": vel_source,
                "three_pl_warnings": three_pl_warnings,
                "download_url": f"/inventory/download/{fname}",
                "filename": fname,
            })
        except Exception as e:
            import traceback
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                            "trace": traceback.format_exc()[-800:]}), 500


    @app.route("/inventory/v2/alerts")
    def inventory_v2_alerts():
        """Return the current alert count for a workspace (drives the sidebar badge)."""
        account_id = (request.args.get("account_id") or "").strip()
        if not account_id:
            return jsonify({"count": 0})
        return jsonify({"count": _INV_ALERT_COUNTS.get(account_id, 0)})
