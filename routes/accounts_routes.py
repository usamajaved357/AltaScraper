"""routes/accounts_routes.py — account/workspace management endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern; route bodies moved VERBATIM (CLAUDE.md §10).
The accounts-only helper _account_tab_name moves in as a nested function. Injected
shared deps: _state, _cfg, CONFIG_PATH, _LIVE_CACHE, live_catalog (the /live/catalog
route function, which detect_brands calls directly), OUTPUT_TAB, ConfigError, _client.
`import accounts` (domain) stays inline in the bodies.

Routes: POST /accounts/detect_brands, POST /accounts/detect_marketplaces,
        GET /accounts/list, POST /accounts/select, POST /accounts/save,
        POST /accounts/set_default_marketplace, POST /accounts/remove_brand,
        POST /accounts/delete.  (/dup_check sits between the two source blocks and
        stays in dashboard.py for now.)
"""
from flask import request, jsonify


def register(app, *, _state, _cfg, CONFIG_PATH, _LIVE_CACHE, live_catalog,
             OUTPUT_TAB, ConfigError, _client, _save_active_state=lambda: None):
    """Attach the /accounts/* routes to the existing Flask app."""

    @app.route("/accounts/detect_brands", methods=["POST"])
    def accounts_detect_brands():
        """Best-effort: derive the brands actually used on this account by reading the
        'brand' field from its live listings (where the report includes it), merged
        with any brands the user typed. NOTE: Amazon has no clean 'list my registered
        trademarks' API -- Brand Registry isn't exposed via SP-API -- so this reflects
        brands seen on live listings, not a Brand Registry pull."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "")
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        rt = str(acc.get("refresh_token", ""))
        if not rt or rt.startswith(("PUT_", "ROTATE")):
            return jsonify({"ok": False, "error": "connect this account first (no credentials yet)"}), 400

        existing = [x for x in (acc.get("brands") or []) if x]
        from_live = []
        source = "manual only"
        # reuse cached live catalog if present, else note we couldn't read live brands
        import time as _t
        ck = f"{aid}::{mkt}"
        items = (_LIVE_CACHE.get(ck) or {}).get("items")
        if items is None:
            # try one live fetch via the same route logic
            try:
                with app.test_request_context(json={"id": aid, "marketplace": mkt}):
                    resp = live_catalog()
                data = resp[0].get_json() if isinstance(resp, tuple) else resp.get_json()
                if data and data.get("ok"):
                    items = data.get("items", [])
            except Exception:
                items = None
        if items:
            seen = {}
            for it in items:
                bn = (it.get("brand") or "").strip()
                if bn:
                    seen[bn.lower()] = bn
            from_live = list(seen.values())
            source = "live listings" if from_live else "live listings (no brand column in report)"

        merged = list(dict.fromkeys([*existing, *from_live]))  # dedupe, keep order
        if merged != existing:
            try:
                # Write ONLY the field we changed. save_account merges {**disk, **passed},
                # so passing a full (possibly stale) snapshot of `acc` silently reverts
                # anything changed on disk since it was read -- e.g. the account's
                # input/output sheet IDs. That's what made new accounts lose their sheets.
                _acc.save_account(_cfg(), CONFIG_PATH,
                                  {"id": acc.get("id"), "brands": merged})
                _state["cfg"] = None
            except Exception:
                pass
        return jsonify({"ok": True, "brands": merged, "from_live": from_live,
                        "source": source,
                        "note": ("Brands are read from your live listings. Amazon does not expose a full "
                                 "Brand Registry list via SP-API, so add any missing trademarks manually.")})


    @app.route("/accounts/detect_marketplaces", methods=["POST"])
    def accounts_detect_marketplaces():
        """Call SP-API getMarketplaceParticipations for an account's credentials and
        save the detected marketplace CODES back onto the account. This is what makes
        the workspace show the account's REAL live marketplaces."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "")
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        rt = str(acc.get("refresh_token", ""))
        if not rt or rt.startswith(("PUT_", "ROTATE")):
            return jsonify({"ok": False, "error": "this account has no real refresh token yet"}), 400

        creds = _acc.account_creds(acc)
        # try the Sellers API; build a reverse map from marketplace_id -> code
        try:
            from sp_api.api import Sellers
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api not available: {e}"}), 500

        # marketplace_id -> our short code (US, UK, DE, ...)
        id_to_code = {}
        try:
            import accounts as _a2
            for code, mid in _a2.MARKETPLACE_IDS.items():
                id_to_code[mid] = code
        except Exception:
            pass

        detected = []
        raw = []
        try:
            # Sellers participations are global to the refresh token; any marketplace
            # enum works as the signing region anchor. Use a sensible default per the
            # account's seller (NA vs EU vs FE) -- try a couple if the first errors.
            anchors = []
            # pick an anchor by what we already know, else try common ones
            seen = set(acc.get("marketplaces", []) or [])
            for guess in (["US"] if "US" in seen else []) + (["UK"] if "UK" in seen else []) + ["UK", "US", "DE"]:
                if guess not in anchors:
                    anchors.append(guess)
            last_err = ""
            part = None
            for anchor in anchors:
                try:
                    mkt_enum = getattr(Marketplaces, anchor, None) or Marketplaces.UK
                    client = Sellers(credentials=creds, marketplace=mkt_enum)
                    resp = client.get_marketplace_participation()
                    part = resp.payload if hasattr(resp, "payload") else resp
                    break
                except Exception as e:
                    last_err = str(e)[:200]
                    continue
            if part is None:
                return jsonify({"ok": False, "error": f"participations call failed: {last_err}"}), 502

            # payload is a list of {marketplace:{id,countryCode,...}, participation:{...}}
            items = part if isinstance(part, list) else part.get("payload", part)
            for it in items:
                mp = it.get("marketplace", {}) if isinstance(it, dict) else {}
                mid = mp.get("id", "")
                cc  = mp.get("countryCode", "")
                code = id_to_code.get(mid) or cc or mid
                participates = True
                par = it.get("participation", {}) if isinstance(it, dict) else {}
                if isinstance(par, dict) and par.get("isParticipating") is False:
                    participates = False
                if participates and code and code not in detected:
                    detected.append(code)
                raw.append({"id": mid, "code": code, "country": cc})
        except Exception as e:
            return jsonify({"ok": False, "error": f"detection failed: {str(e)[:200]}"}), 500

        # save back onto the account
        try:
            # Write ONLY the changed field (see accounts_detect_brands): a full snapshot
            # would clobber the account's sheet IDs and other fields with stale values.
            # This route auto-runs for a NEW account (empty marketplaces), which is exactly
            # why new accounts lost their sheets while old ones were fine.
            _acc.save_account(_cfg(), CONFIG_PATH,
                              {"id": acc.get("id"), "marketplaces": detected})
            _state["cfg"] = None
        except Exception:
            pass
        return jsonify({"ok": True, "marketplaces": detected, "raw": raw})


    @app.route("/accounts/list")
    def accounts_list():
        """List all accounts (workspaces). Secrets are NOT returned -- only presence.
        """
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        try:
            cfg = _cfg()
        except ConfigError as e:
            return jsonify({"ok": False, "error": str(e), "config_error": True}), 200
        al = _acc.load_accounts(cfg, CONFIG_PATH)
        safe = []
        for a in al:
            rt = str(a.get("refresh_token", ""))
            ready = bool(rt) and not rt.startswith(("PUT_", "ROTATE"))
            safe.append({"id": a.get("id"), "label": a.get("label"),
                         "seller_id": a.get("seller_id", ""),
                         "marketplaces": a.get("marketplaces", []),
                         "brands": a.get("brands", []),
                         "output_spreadsheet_id": a.get("output_spreadsheet_id", ""),
                         "input_sheet_url": a.get("input_sheet_url", ""),
                         "output_sheet_url": a.get("output_sheet_url", ""),
                         "drive_folder_url": a.get("drive_folder_url", ""),
                         "uk_responsible_person": a.get("uk_responsible_person", {}),
                         "input_spreadsheet_id": a.get("input_spreadsheet_id", ""),
                         "input_tab_gid": a.get("input_tab_gid", ""),
                         "output_tab_gid": a.get("output_tab_gid", ""),
                         "default_marketplace": a.get("default_marketplace", "UK"),
                         "features": a.get("features", []),
                         "has_creds": ready,
                         "has_secret": bool(a.get("lwa_client_secret")),
                         "lwa_client_id": a.get("lwa_client_id", ""),
                         # per-account eBay override: expose the App ID (public) and
                         # whether a Cert (secret) is stored -- never the Cert itself.
                         "ebay_app_id": a.get("ebay_app_id", ""),
                         "has_ebay_cert": bool(a.get("ebay_cert_id"))})
        return jsonify({"ok": True, "accounts": safe, "active": _state.get("active_account_id", "")})


    @app.route("/accounts/select", methods=["POST"])
    def accounts_select():
        """Select an account workspace AND scope the listings view to that account's
        own sheet/tab, so accounts never show each other's listings."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "")
        _state["active_account_id"] = aid
        _state["active_marketplace"] = b.get("marketplace", "") or _state.get("active_marketplace", "")
        if not aid:
            # Dropshipping: use the user-assigned default sheet/tab if one was set in
            # "Dropshipping sheets"; otherwise leave None so _ws() falls back to the
            # config default (google_spreadsheet_id + OUTPUT_TAB) exactly as before.
            _c0 = _cfg()
            _ds_sid = str(_c0.get("dropshipping_output_spreadsheet_id") or "").strip()
            _state["active_sheet_id"] = _ds_sid or None
            _state["active_tab"] = (str(_c0.get("dropshipping_output_tab") or "").strip() or None)
            _state["active_tab_gid"] = str(_c0.get("dropshipping_output_tab_gid") or "").strip()
            _state["active_view"] = ""
            _save_active_state()   # persist, so a restart can't silently revert the workspace
            return jsonify({"ok": True, "scope": "dropshipping"})
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        # this account's own sheet + the EXACT tab its listings are written to. The
        # generator writes by output_tab_gid (from the sheet URL), so the app must
        # read the SAME tab -- not a tab guessed from the account label.
        sid = (acc.get("output_spreadsheet_id") or "").strip()
        import re as _re
        mm = _re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sid)
        if mm:
            sid = mm.group(1)
        _state["active_sheet_id"] = sid or None
        _state["active_tab_gid"] = str(acc.get("output_tab_gid") or "").strip()
        # resolve the tab NAME from the gid (so _ws can also fall back by name)
        _resolved_tab = None
        if sid and _state["active_tab_gid"].isdigit():
            try:
                _bk = _client().open_by_key(sid)
                _wsbygid = _bk.get_worksheet_by_id(int(_state["active_tab_gid"]))
                if _wsbygid is not None:
                    _resolved_tab = _wsbygid.title
            except Exception:
                _resolved_tab = None
        _state["active_tab"] = _resolved_tab or _account_tab_name(acc)
        _state["active_view"] = acc.get("label", aid)
        _save_active_state()   # persist the chosen workspace so a restart can't revert it
        # Tell the browser EXACTLY which sheet + tab this workspace is bound to, and
        # whether that binding is incomplete -- so it can show the data source in the
        # header and warn instead of the app quietly reading someone else's tab.
        _in_sid = str(acc.get("input_spreadsheet_id") or "").strip()
        _in_gid = str(acc.get("input_tab_gid") or "").strip()
        _missing = []
        if not sid:
            _missing.append("output sheet")
        elif not (_state["active_tab_gid"].isdigit() or _state["active_tab"]):
            _missing.append("output tab")
        if not _in_sid:
            _missing.append("input sheet")
        return jsonify({"ok": True, "scope": "account",
                        "sheet": sid,
                        "tab": _state["active_tab"],
                        "tab_gid": _state["active_tab_gid"],
                        "input_sheet": _in_sid,
                        "input_tab_gid": _in_gid,
                        "missing": _missing,
                        "scope_ok": not _missing})


    def _account_tab_name(acc):
        """The worksheet tab this account's listings live in.

        Priority must MATCH what the generator writes to, or the dashboard reads an
        empty/wrong tab:
          1. _tab_override  -> explicit tab (e.g. a brand tab)
          2. output tab resolved from output_tab_gid (handled by the caller)
          3. nothing -- "" means NOT CONFIGURED.

        It used to fall back to the marketplace default ("Listings v7.0 UK" / "US").
        That was wrong: those tabs are shared, and hold whichever account was set up
        first. An account with no output_tab_gid therefore silently displayed another
        account's listings, and a Submit would have published them under the wrong
        Amazon seller. _ws() now raises SheetScopeError on "" so the user is told to
        set the tab in Account & sheets, rather than the app guessing for them.
        """
        if acc.get("_tab_override"):
            return acc["_tab_override"]
        return ""


    @app.route("/accounts/save", methods=["POST"])
    def accounts_save():
        """Add or update an account. Only overwrites secret fields if a non-empty,
        non-placeholder value is provided (so editing labels won't wipe secrets)."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        if not b.get("label"):
            return jsonify({"ok": False, "error": "label required"}), 400
        existing = _acc.get_account(_cfg(), b.get("id", ""), CONFIG_PATH) if b.get("id") else {}
        acct = dict(existing) if existing else {}
        acct["id"] = b.get("id") or existing.get("id") or ""
        acct["label"] = b["label"]
        acct["seller_id"] = b.get("seller_id", acct.get("seller_id", ""))
        acct["lwa_client_id"] = b.get("lwa_client_id", acct.get("lwa_client_id", ""))
        acct["output_spreadsheet_id"] = b.get("output_spreadsheet_id", acct.get("output_spreadsheet_id", ""))
        # full Google Sheets URLs (input + output) and the parsed pieces, so each
        # account routes its listings to the correct spreadsheet + tab
        for k in ("input_sheet_url", "output_sheet_url", "input_spreadsheet_id",
                  "input_tab_gid", "output_tab_gid", "drive_folder_url",
                  "uk_responsible_person", "ebay_app_id"):
            if k in b:
                acct[k] = b.get(k, acct.get(k, ""))
        if b.get("default_marketplace"):
            acct["default_marketplace"] = str(b["default_marketplace"]).strip().upper()
        if isinstance(b.get("brands"), list):
            acct["brands"] = b["brands"]
        # Per-workspace feature flags (e.g. "harvest" for supplier-scrape accounts
        # like Miles, "image_template" for auto main-image generation).
        if isinstance(b.get("features"), list):
            acct["features"] = [str(f).strip() for f in b["features"] if str(f).strip()]
        acct.setdefault("marketplaces", existing.get("marketplaces", []))
        # only overwrite secrets if a real value was supplied. ebay_cert_id is the
        # per-account eBay secret (blank keeps the existing one, like the SP-API
        # secrets); when set alongside ebay_app_id it overrides the global eBay creds.
        for sk in ("lwa_client_secret", "refresh_token", "ebay_cert_id"):
            v = (b.get(sk) or "").strip()
            if v and not v.startswith(("PUT_", "ROTATE", "•", "*")):
                acct[sk] = v
            else:
                acct.setdefault(sk, existing.get(sk, ""))
        saved = _acc.save_account(_cfg(), CONFIG_PATH, acct)
        _state["cfg"] = None
        return jsonify({"ok": True, "id": saved.get("id")})


    @app.route("/accounts/set_default_marketplace", methods=["POST"])
    def accounts_set_default_marketplace():
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        mkt = (b.get("marketplace", "") or "").upper()
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        try:
            # only the changed field -- a full snapshot would clobber the sheet IDs
            _acc.save_account(_cfg(), CONFIG_PATH,
                              {"id": acc.get("id") or aid, "default_marketplace": mkt})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        _state["cfg"] = None
        return jsonify({"ok": True, "default_marketplace": mkt})


    @app.route("/accounts/remove_brand", methods=["POST"])
    def accounts_remove_brand():
        """Remove a brand/trademark from the ACTIVE account's brands list.
        The brand profile on disk is kept; this only unassigns it from the account."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        brand = (b.get("brand", "") or "").strip()
        aid = b.get("id", "") or _state.get("active_account_id", "")
        if not brand:
            return jsonify({"ok": False, "error": "no brand specified"}), 400
        if not aid:
            return jsonify({"ok": False, "error": "no active account"}), 400
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        brands = [x for x in (acc.get("brands") or []) if x.strip().lower() != brand.lower()]
        # persist ONLY the changed field -- a full snapshot would clobber the sheet IDs
        try:
            _acc.save_account(_cfg(), CONFIG_PATH,
                              {"id": acc.get("id") or aid, "brands": brands})
        except Exception as e:
            return jsonify({"ok": False, "error": f"save failed: {e}"}), 500
        _state["cfg"] = None
        return jsonify({"ok": True, "brands": brands})


    @app.route("/accounts/delete", methods=["POST"])
    def accounts_delete():
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        ok = _acc.delete_account(_cfg(), CONFIG_PATH, b.get("id", ""))
        _state["cfg"] = None
        return jsonify({"ok": ok})
