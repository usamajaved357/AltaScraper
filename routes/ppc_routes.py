"""routes/ppc_routes.py — Sponsored Products PPC endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern; route bodies moved VERBATIM (CLAUDE.md §10).
Shared helpers stay in dashboard.py and are injected: the PPC module refs
(_PPC, _PPC_IMPORT_ERR), output dir (_PPC_OUT_DIR), the ppc-only helper
_parse_pct_from_context (used by /ppc/deliverable), _cfg and CHAT_MODEL (used by the
agent). ppc_deliverables (domain) is imported inline in the bodies.

Routes: POST /ppc/build_campaigns, GET /ppc/download/<fname>, POST /ppc/harvest,
        POST /ppc/deliverable, POST /ppc/agent
"""
import json
import os

from flask import request, jsonify


def register(app, *, _PPC, _PPC_IMPORT_ERR, _PPC_OUT_DIR, _parse_pct_from_context,
             _cfg, CHAT_MODEL):
    """Attach the /ppc/* routes to the existing Flask app."""

    @app.route("/ppc/build_campaigns", methods=["POST"])
    def ppc_build_campaigns():
        """Build the Sponsored Products bulk CSV from an uploaded keyword file
        + ASIN/SKU/short-name. Validates before returning; the download link is
        only useful if validation passed (or the user overrides warnings)."""
        if _PPC is None:
            return jsonify({"ok": False, "error": f"PPC module not available: {_PPC_IMPORT_ERR}"}), 500
        try:
            f = request.files.get("file")
            if not f:
                return jsonify({"ok": False, "error": "no keyword file uploaded"}), 400
            raw = f.read()
            ingest = _PPC.ingest_csv_bytes(raw)
            if not ingest.get("family"):
                return jsonify({"ok": False, "error":
                    f"Could not identify keyword file family from columns: "
                    f"{ingest.get('detected_columns', [])[:10]}. Supported: DataDive, Helium 10 Cerebro, Brand Analytics SQP."
                }), 400

            asin = (request.form.get("asin") or "").strip()
            sku  = (request.form.get("sku")  or "").strip()
            pname = (request.form.get("product_short_name") or "").strip()
            if not asin or not sku or not pname:
                return jsonify({"ok": False, "error": "asin, sku, and product_short_name are all required"}), 400
            if asin == sku:
                return jsonify({"ok": False, "error": "SKU cannot equal ASIN -- use the seller SKU from Seller Central"}), 400
            try:
                budget = float(request.form.get("daily_budget") or 8.0)
                bid    = float(request.form.get("default_bid")  or 0.30)
            except ValueError:
                return jsonify({"ok": False, "error": "daily_budget and default_bid must be numbers"}), 400
            try:
                conquest    = tuple(json.loads(request.form.get("conquest_asins")    or "[]"))
                compbrands  = tuple(json.loads(request.form.get("competitor_brands") or "[]"))
                headterms   = tuple(json.loads(request.form.get("category_heads")    or "[]"))
            except json.JSONDecodeError as je:
                return jsonify({"ok": False, "error": f"invalid JSON in list field: {je}"}), 400

            # Bucketing config from the form; per-niche brands/heads
            cfg = _PPC.BucketingConfig(competitor_brands=compbrands,
                                        category_heads=headterms)
            buckets = _PPC.bucket_all(ingest["rows"], cfg)

            inp = _PPC.CampaignBuildInput(
                asin=asin, sku=sku, product_short_name=pname,
                marketplace=(request.form.get("marketplace") or "UK").upper(),
                daily_budget=budget, default_bid=bid,
                conquest_asins=conquest,
            )
            # Standard 20-term negative fence from the doc (universal wastage terms)
            # These are safe defaults; niche-specific ones added by user later.
            default_negs = ("free", "cheap", "used", "second hand", "reviews",
                            "how to", "diy", "manual", "instructions", "recall")
            try:
                out = _PPC.build_sp_bulk(inp, buckets["buckets"], negatives=default_negs)
            except ValueError as ve:
                return jsonify({"ok": False, "error": str(ve)}), 400

            # save the file so it can be downloaded
            import time as _t
            fname = f"sp_bulk_{asin}_{int(_t.time())}.csv"
            fpath = os.path.join(_PPC_OUT_DIR, fname)
            with open(fpath, "w", encoding="utf-8", newline="") as fh:
                fh.write(out["csv"])

            unique_kws = len({r["Keyword Text"] for r in out["rows"] if r.get("Entity") == "Keyword"})

            return jsonify({
                "ok":              True,
                "row_count":       len(out["rows"]),
                "campaign_count":  len(out["campaigns"]),
                "unique_keywords": unique_kws,
                "bucket_counts":   buckets["counts"],
                "validation":      out["validation"],
                "filename":        fname,
                "download_url":    f"/ppc/download/{fname}",
            })
        except Exception as e:
            import traceback
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                            "trace": traceback.format_exc()[-800:]}), 500


    @app.route("/ppc/download/<path:fname>")
    def ppc_download(fname):
        """Serve a previously-built PPC file. Restricted to _PPC_OUT_DIR to avoid
        directory traversal (Flask's send_from_directory refuses paths outside)."""
        from flask import send_from_directory
        if ".." in fname or fname.startswith("/") or fname.startswith("\\"):
            return "invalid filename", 400
        return send_from_directory(_PPC_OUT_DIR, fname, as_attachment=True)


    @app.route("/ppc/harvest", methods=["POST"])
    def ppc_harvest():
        """Process an SP Search Term Report into three deliverables:
          - status sheet CSV (colour-coded per term)
          - harvest bulk CSV (new converting terms in all 3 match types)
          - negatives bulk CSV (past-$10 zero-order terms)

        Accepts a keywords-already-targeted list (optional) so already-covered
        terms are excluded from the harvest file -- prevents duplicate
        (keyword, match-type) pairs when uploaded.
        """
        if _PPC is None:
            return jsonify({"ok": False, "error": f"PPC module not available: {_PPC_IMPORT_ERR}"}), 500
        try:
            f = request.files.get("file")
            if not f:
                return jsonify({"ok": False, "error": "SP Search Term Report CSV required"}), 400
            raw = f.read()
            ingest = _PPC.ingest_csv_bytes(raw)
            if ingest.get("family") != "sp_search_term_report":
                return jsonify({"ok": False, "error":
                    f"Uploaded file doesn't look like an SP Search Term Report "
                    f"(detected: {ingest.get('family') or 'unknown'}). "
                    f"Download it from Ads > Measurement & Reporting > Sponsored Products "
                    f"Search Term Report."
                }), 400

            asin  = (request.form.get("asin")  or "").strip()
            sku   = (request.form.get("sku")   or "").strip()
            pname = (request.form.get("product_short_name") or "").strip()
            if not asin or not sku or not pname:
                return jsonify({"ok": False, "error": "asin, sku, and product_short_name are required"}), 400
            if asin == sku:
                return jsonify({"ok": False, "error": "SKU cannot equal ASIN"}), 400
            try:
                break_even = float(request.form.get("break_even_acos") or 0.35)
                budget     = float(request.form.get("daily_budget")    or 8.0)
                bid        = float(request.form.get("default_bid")     or 0.30)
            except ValueError:
                return jsonify({"ok": False, "error": "break_even_acos, daily_budget, default_bid must be numbers"}), 400

            # Already-targeted keywords (excluded from harvest to prevent duplicate
            # (keyword, match-type) pairs at upload time). Optional; accepts:
            #   - a CSV file field 'targeted_file' (one keyword per row, any column)
            #   - a JSON array 'targeted_kws'
            already: set = set()
            tf = request.files.get("targeted_file")
            if tf:
                for row in _PPC.ingest_csv_bytes(tf.read()).get("rows", []):
                    v = row.get("keyword_text") or row.get("keyword") or list(row.values())[0]
                    if v:
                        already.add(_PPC._normalise_kw(v))
            try:
                for k in json.loads(request.form.get("targeted_kws") or "[]"):
                    already.add(_PPC._normalise_kw(k))
            except json.JSONDecodeError as je:
                return jsonify({"ok": False, "error": f"invalid targeted_kws JSON: {je}"}), 400

            cfg = _PPC.HarvestConfig(break_even_acos=break_even,
                                      currency=("$" if (request.form.get("marketplace") or "UK").upper() == "US" else "£"))
            result = _PPC.run_harvest(ingest["rows"],
                                        current_targeting_kws=already,
                                        cfg=cfg)

            # Emit the three CSVs and save to _PPC_OUT_DIR
            inp = _PPC.CampaignBuildInput(asin=asin, sku=sku, product_short_name=pname,
                                            daily_budget=budget, default_bid=bid,
                                            marketplace=(request.form.get("marketplace") or "UK").upper())
            harvest_csv    = _PPC.build_harvest_bulk_csv(result["harvest_rows"], inp)
            negatives_csv  = _PPC.build_negatives_bulk_csv(result["negative_rows"], inp)
            status_csv     = _PPC.build_status_sheet_csv(result["status_rows"], currency=cfg.currency)
            # Also emit a COLOURED xlsx status sheet (new): each row tinted by status.
            try:
                import ppc_deliverables as _PD
                status_xlsx = _PD.build_status_xlsx(result["status_rows"], currency=cfg.currency)
            except Exception as _xe:
                # Non-fatal -- CSV still available. Log the error into the response so
                # the user knows the xlsx button will be missing.
                status_xlsx = None
                _xlsx_err = f"xlsx build failed: {_xe}"

            import time as _t
            ts = int(_t.time())
            base = f"{asin}_{ts}"
            fnames = {
                "status":      f"status_{base}.csv",
                "status_xlsx": f"status_{base}.xlsx",
                "harvest":     f"harvest_{base}.csv",
                "negatives":   f"negatives_{base}.csv",
            }
            with open(os.path.join(_PPC_OUT_DIR, fnames["status"]),    "w", encoding="utf-8", newline="") as fh:
                fh.write(status_csv)
            with open(os.path.join(_PPC_OUT_DIR, fnames["harvest"]),   "w", encoding="utf-8", newline="") as fh:
                fh.write(harvest_csv)
            with open(os.path.join(_PPC_OUT_DIR, fnames["negatives"]), "w", encoding="utf-8", newline="") as fh:
                fh.write(negatives_csv)
            if status_xlsx:
                with open(os.path.join(_PPC_OUT_DIR, fnames["status_xlsx"]), "wb") as fh:
                    fh.write(status_xlsx)

            downloads = {
                "status":    f"/ppc/download/{fnames['status']}",
                "harvest":   f"/ppc/download/{fnames['harvest']}",
                "negatives": f"/ppc/download/{fnames['negatives']}",
            }
            if status_xlsx:
                downloads["status_xlsx"] = f"/ppc/download/{fnames['status_xlsx']}"

            return jsonify({
                "ok":            True,
                "counts":        result["counts"],
                "totals":        result["totals"],
                "excluded_already_targeted": len(already),
                "downloads":     downloads,
                "filenames":     fnames,
            })
        except Exception as e:
            import traceback
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                            "trace": traceback.format_exc()[-800:]}), 500


    @app.route("/ppc/deliverable", methods=["POST"])
    def ppc_deliverable():
        """Unified endpoint for the audit / dashboard / forecast / weekly-deck
        shortcuts. Detects file families, produces the polished output
        (docx/pptx/xlsx/html) via ppc_deliverables, and ALSO gets Claude to give
        inline analysis notes so the user sees both the deliverable link and a
        short executive summary.

        For 'auditor' the primary requirement is an SP bulk export; performance
        report is optional (financial section only appears if performance is
        supplied). For 'dashboard' same. For 'forecaster' the primary requirement
        is a business report + target TACOS + net margin. For 'weekly-deck' the
        primary requirement is this-week performance (last-week optional for WoW).
        """
        if _PPC is None:
            return jsonify({"ok": False, "error": f"PPC module not available: {_PPC_IMPORT_ERR}"}), 500
        try:
            import ppc_deliverables as _PD
        except Exception as _pde:
            return jsonify({"ok": False, "error": f"deliverables module not available: {_pde}"}), 500

        try:
            skill    = (request.form.get("skill")    or "").strip()
            context  = (request.form.get("context")  or "").strip()
            account_id  = (request.form.get("account_id")  or "").strip()
            marketplace = (request.form.get("marketplace") or "UK").strip().upper()
            if skill not in _PPC.SKILL_CATALOGUE:
                return jsonify({"ok": False, "error": f"unknown skill: {skill!r}"}), 400

            files = request.files.getlist("files")
            if not files:
                return jsonify({"ok": False, "error": "attach at least one file"}), 400

            # Detect file families + capture full rows for the builders.
            # NOTE: `by_family` concatenates rows across files sharing a family --
            # useful for audit/dashboard where "more rows = better picture", but
            # DESTRUCTIVE for weekly-deck which needs to keep this-week and
            # last-week files SEPARATE. We also keep `by_file` (per-file rows) so
            # skills that need per-file isolation can use that instead.
            file_summary = []
            by_family    = {}   # family -> concatenated rows across all files
            by_file      = []   # list of {filename, family, rows} preserving isolation
            for f in files:
                raw = f.read()
                ingest = _PPC.ingest_csv_bytes(raw)
                fam = ingest.get("family")
                rows = ingest.get("rows") or []
                file_summary.append({
                    "filename":  f.filename,
                    "family":    fam or "",
                    "row_count": ingest.get("raw_row_count", 0),
                    "columns":   (ingest.get("detected_columns") or [])[:20],
                })
                by_file.append({"filename": f.filename, "family": fam or "", "rows": rows})
                if fam:
                    by_family.setdefault(fam, []).extend(rows)

            # ---- Build the polished output per skill ----
            import time as _t
            ts = int(_t.time())
            base = f"{skill}_{ts}"
            downloads = {}
            missing   = []
            note      = ""

            if skill == "auditor":
                bulk = by_family.get("sp_bulk_export", [])
                if not bulk:
                    missing.append("SP bulk export (CSV) -- required for the audit structure")
                else:
                    # Performance report shape isn't formally detected as its own family
                    # in this MVP -- if there are search-term rows we treat those as
                    # performance-adjacent. Real perf report support is a follow-up.
                    perf = by_family.get("sp_search_term_report", [])
                    audit_bytes = _PD.build_audit_docx(bulk, perf,
                                                        account_label=account_id or "Account",
                                                        marketplace=marketplace)
                    fname = f"{base}.docx"
                    with open(os.path.join(_PPC_OUT_DIR, fname), "wb") as fh:
                        fh.write(audit_bytes)
                    downloads["audit_docx"] = f"/ppc/download/{fname}"
                    note = f"Built structural audit from {len(bulk)} bulk-export rows"
                    if perf:
                        note += f" + {len(perf)} search-term rows for financial section"

            elif skill == "dashboard":
                bulk = by_family.get("sp_bulk_export", [])
                if not bulk:
                    missing.append("SP bulk export (CSV) -- required for the dashboard")
                else:
                    perf = by_family.get("sp_search_term_report", [])
                    html_bytes = _PD.build_dashboard_html(bulk, perf,
                                                           account_label=account_id or "Account",
                                                           marketplace=marketplace)
                    fname = f"{base}.html"
                    with open(os.path.join(_PPC_OUT_DIR, fname), "wb") as fh:
                        fh.write(html_bytes)
                    downloads["dashboard_html"] = f"/ppc/download/{fname}"
                    note = f"Built control-room from {len(bulk)} bulk-export rows"

            elif skill == "forecaster":
                biz = by_family.get("amazon_business_report", [])
                if not biz:
                    missing.append("Amazon Business Report (CSV) -- required for the forecast base")
                else:
                    # Parse target TACOS + margin from context (user's own numbers -- never invent)
                    target_tacos = _parse_pct_from_context(context, "tacos", default=None)
                    margin       = _parse_pct_from_context(context, "margin", default=None)
                    if target_tacos is None or margin is None:
                        missing.append("Target TACOS % and net margin % -- please state them in the "
                                       "context box (e.g. 'TACOS 15%, margin 25%'). I never invent these.")
                    else:
                        fc_bytes = _PD.build_forecast_xlsx(biz,
                                                            target_tacos_pct=target_tacos,
                                                            net_margin_pct=margin)
                        fname = f"{base}.xlsx"
                        with open(os.path.join(_PPC_OUT_DIR, fname), "wb") as fh:
                            fh.write(fc_bytes)
                        downloads["forecast_xlsx"] = f"/ppc/download/{fname}"
                        note = (f"3-scenario forecast: {len(biz)} report days, "
                                f"target TACOS {target_tacos}%, margin {margin}%")

            elif skill == "weekly-deck":
                # Weekly deck needs THIS-WEEK and LAST-WEEK kept SEPARATE. Real
                # Amazon Ads exports have DATES in filenames, not the words 'last'/
                # 'prior'. So we prefer date-parsing over word hints -- the latest
                # date is this-week, earlier dates are last-week. Word hints are a
                # fallback for oddly-named files.
                perf_files = [b for b in by_file if b["family"] == "sp_search_term_report"]
                if not perf_files:
                    missing.append("Sponsored Products performance data (Search Term Report or campaign report)")
                else:
                    import re as _re
                    import datetime as _dt

                    def _extract_date(fn: str):
                        """Pull a date out of an Amazon Ads export filename. Tries
                        ISO (YYYY-MM-DD), UK (DD-MM-YYYY), US (MM-DD-YYYY), and
                        'Mon DD YYYY' formats. Returns date or None."""
                        fn = fn or ""
                        # ISO first: 2026-08-08
                        m = _re.search(r"(20\d{2})[-_/](\d{1,2})[-_/](\d{1,2})", fn)
                        if m:
                            try:
                                return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                            except ValueError:
                                pass
                        # Mon DD, YYYY: "Aug 8, 2026" or "Aug 08 2026"
                        m = _re.search(r"([A-Za-z]{3,9})[\s,_-]+(\d{1,2})[\s,_-]+(20\d{2})", fn)
                        if m:
                            try:
                                return _dt.datetime.strptime(
                                    f"{m.group(1)[:3]} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
                            except ValueError:
                                pass
                        # DD-MM-YYYY (UK) or MM-DD-YYYY (US) -- ambiguous, treat as UK
                        m = _re.search(r"(\d{1,2})[-_/](\d{1,2})[-_/](20\d{2})", fn)
                        if m:
                            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                            if d > 12 and mo <= 12:
                                try: return _dt.date(y, mo, d)
                                except ValueError: pass
                            if mo > 12 and d <= 12:
                                try: return _dt.date(y, d, mo)
                                except ValueError: pass
                            # Both plausible as either day-first or month-first; assume UK
                            try: return _dt.date(y, mo, d)
                            except ValueError:
                                try: return _dt.date(y, d, mo)
                                except ValueError: pass
                        return None

                    # Attach an extracted date to each file (None if no date)
                    for pf in perf_files:
                        pf["_date"] = _extract_date(pf["filename"])

                    dated_files    = [pf for pf in perf_files if pf["_date"] is not None]
                    undated_files  = [pf for pf in perf_files if pf["_date"] is None]

                    tw_rows = []
                    lw_rows = []
                    classification = []   # for the response note so user can verify

                    if len(dated_files) >= 2:
                        # PRIMARY: sort by date; latest = this-week, rest = last-week
                        dated_files.sort(key=lambda x: x["_date"], reverse=True)
                        tw_file = dated_files[0]
                        tw_rows.extend(tw_file["rows"])
                        classification.append(f"THIS-WEEK: {tw_file['filename']} ({tw_file['_date']})")
                        for pf in dated_files[1:]:
                            lw_rows.extend(pf["rows"])
                            classification.append(f"LAST-WEEK: {pf['filename']} ({pf['_date']})")
                        # Undated files: default to this-week (safer than pretending they're old)
                        for pf in undated_files:
                            tw_rows.extend(pf["rows"])
                            classification.append(f"THIS-WEEK (no date in filename): {pf['filename']}")
                    else:
                        # FALLBACK: no dates or only one dated file. Use filename word hints
                        # like 'last'/'prior'/'lw'/'week1' as a last-ditch heuristic.
                        for pf in perf_files:
                            fn = pf["filename"].lower()
                            if ("last" in fn or "prior" in fn or "_lw" in fn or "week1" in fn):
                                lw_rows.extend(pf["rows"])
                                classification.append(f"LAST-WEEK (word hint): {pf['filename']}")
                            else:
                                tw_rows.extend(pf["rows"])
                                classification.append(f"THIS-WEEK: {pf['filename']}")
                        # If ONLY last-week hints matched, promote the first back to this-week
                        if not tw_rows and perf_files:
                            first = perf_files[0]
                            tw_rows = first["rows"]
                            lw_rows = [r for pf in perf_files[1:] for r in pf["rows"]]
                            classification = ([f"THIS-WEEK (promoted): {first['filename']}"] +
                                              [f"LAST-WEEK: {pf['filename']}" for pf in perf_files[1:]])

                    brand_from_ctx = ""
                    week_from_ctx  = ""
                    for line in context.splitlines():
                        ll = line.lower()
                        if ll.startswith("brand:"):        brand_from_ctx = line.split(":",1)[1].strip()
                        elif ll.startswith("week ending:"): week_from_ctx  = line.split(":",1)[1].strip()
                    deck_bytes = _PD.build_weekly_deck_pptx(tw_rows, lw_rows or None,
                                                              brand=brand_from_ctx or account_id or "Brand",
                                                              week_ending=week_from_ctx)
                    fname = f"{base}.pptx"
                    with open(os.path.join(_PPC_OUT_DIR, fname), "wb") as fh:
                        fh.write(deck_bytes)
                    downloads["weekly_deck_pptx"] = f"/ppc/download/{fname}"
                    note = (f"5-slide deck: {len(tw_rows)} this-week rows"
                            + (f", {len(lw_rows)} last-week rows for WoW" if lw_rows
                               else " (no last-week file detected -- WoW slide will say so)")
                            + "\nFile classification:\n  " + "\n  ".join(classification))

            else:
                missing.append(f"skill '{skill}' has no hand-built deliverable yet")

            # ---- Claude analysis note (optional; degrades gracefully) ----
            spec = _PPC.SKILL_CATALOGUE[skill]
            analysis = ""
            key = (_cfg().get("anthropic_api_key") or "").strip()
            if key and not missing:
                system = (
                    "You are the PPC assistant. A polished deliverable was JUST built. "
                    "Your job: 3-6 sentence executive summary of what the user should look at "
                    "first in the deliverable, based on the file summaries and context. "
                    "NEVER invent numbers. NEVER touch bids/budgets. Plain English."
                )
                file_lines = "\n".join(f"- {f['filename']}: {f['family'] or 'unknown'}, "
                                        f"{f['row_count']} rows"
                                        for f in file_summary)
                user_msg = (f"Skill: {skill}\nWorkspace: {account_id or '(unspecified)'} · {marketplace}\n"
                            f"Files:\n{file_lines}\n\nContext:\n{context or '(none)'}\n\n"
                            f"Deliverable built: {list(downloads.keys())}\n")
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=key)
                    r = client.messages.create(model=CHAT_MODEL, max_tokens=600,
                                                 system=system,
                                                 messages=[{"role": "user", "content": user_msg}])
                    analysis = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
                except Exception as _ce:
                    analysis = f"(Claude note skipped: {str(_ce)[:120]})"

            return jsonify({"ok": True,
                            "file_summary": file_summary,
                            "downloads":    downloads,
                            "missing":      missing,
                            "note":         note,
                            "reply":        analysis or note or "Deliverable built."})
        except Exception as e:
            import traceback
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                            "trace": traceback.format_exc()[-800:]}), 500


    @app.route("/ppc/agent", methods=["POST"])
    def ppc_agent():
        """PPC assistant chat. Routes intent to the right skill, invokes Claude with
        a system prompt that encodes the doc's non-negotiable rules, and returns a
        plain-text reply plus (if matched) the skill id and a next-action hint.

        Non-negotiable rules baked into the prompt:
        - Never sets or changes bids/budgets on its own initiative
        - Enforces match types spelled out / SKU on ads / kw+PT not in same ad group
        - Every keyword in all 3 match types across the portfolio (base + Coverage)
        """
        if _PPC is None:
            return jsonify({"ok": False, "error": f"PPC module not available: {_PPC_IMPORT_ERR}"}), 500
        b = request.get_json(silent=True) or {}
        msg = (b.get("message") or "").strip()
        if not msg:
            return jsonify({"ok": False, "error": "message required"}), 400
        account_id  = (b.get("account_id")  or "").strip()
        marketplace = (b.get("marketplace") or "UK").strip().upper()

        routed = _PPC.route_intent(msg)
        skill = _PPC.SKILL_CATALOGUE.get(routed) if routed else None

        # Build context for the model: workspace + which skill was routed
        ctx_lines = [f"Workspace account: {account_id or '(unspecified)'}",
                     f"Marketplace: {marketplace}"]
        if skill:
            ctx_lines.append(f"Routed skill: {routed}")
            ctx_lines.append(f"Requires: {', '.join(skill['requires'])}")
            ctx_lines.append(f"Produces: {skill['produces']}")
        else:
            ctx_lines.append("No skill matched -- ask user to clarify which capability they want.")
        ctx = "\n".join(ctx_lines)

        system = (
            "You are the PPC assistant inside a listing-generator app. You handle Amazon "
            "Sponsored Products work end to end: campaign building, keyword bucketing, "
            "search-term harvest, negative-keyword rules, audits, dashboards, forecasts, "
            "and weekly client decks.\n\n"
            "NON-NEGOTIABLE RULES (never violate, no exceptions):\n"
            "1. Never set or change bids/budgets on your own initiative. Only when the "
            "user explicitly specifies the value in their message.\n"
            "2. Match types are always spelled out: Exact, Phrase, Broad. Never Ex/Ph/Br.\n"
            "3. Product Ad rows carry the SELLER SKU, never the ASIN.\n"
            "4. Keywords and Product Targets can NEVER share one ad group. Split them.\n"
            "5. Every relevant keyword must exist in all 3 match types across the portfolio "
            "(base campaigns hold primary; a CATCH ALL Coverage campaign fills missing).\n"
            "6. Zero duplicate (keyword, match-type) pairs across the whole bulk file.\n"
            "7. For forecasts and profit math: NEVER fabricate a number. If input data is "
            "missing, stop and ask for it or drop a tier and say so.\n\n"
            "STYLE:\n"
            "- Simple plain English + a short technical explanation when relevant.\n"
            "- Address the user directly. Do not narrate your reasoning at length.\n"
            "- When a shortcut form exists (campaign builder), point the user to it.\n"
            "- When you need input files, list them by name and stop; do not guess content.\n"
        )
        user_msg = f"Context:\n{ctx}\n\nUser message:\n{msg}"

        key = (_cfg().get("anthropic_api_key") or "").strip()
        if not key:
            # Degrade gracefully with routing info even without an LLM key
            parts = ["Anthropic API key not configured -- returning routing info only."]
            if skill:
                parts += [f"", f"Best-matched skill: {routed}.",
                          f"This skill needs: {', '.join(skill['requires'])}.",
                          f"It produces: {skill['produces']}."]
            else:
                parts.append("Could not match your message to a known PPC capability. "
                             "Try: 'build campaigns from a keyword export', 'harvest my "
                             "search-term report', 'audit my PPC health', 'weekly client deck'.")
            return jsonify({"ok": True, "reply": "\n".join(parts),
                            "routed_skill": routed,
                            "next_action":  ""})

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            r = client.messages.create(
                model=CHAT_MODEL, max_tokens=1200,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            reply = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        except Exception as e:
            return jsonify({"ok": False, "error": f"LLM call failed: {str(e)[:200]}"}), 500

        next_action = ""
        if routed == "campaign-builder":
            next_action = "Use the 'Build campaigns from keywords' shortcut (top-left) — it validates before download."
        elif routed == "harvester":
            next_action = "Upload your SP Search Term Report as CSV. (Harvest form coming next session.)"

        return jsonify({"ok": True, "reply": reply,
                        "routed_skill": routed,
                        "next_action":  next_action})
