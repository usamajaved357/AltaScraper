"""routes/settings_routes.py — AI/model, admin, and sheet/eBay settings endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern; route bodies moved VERBATIM (CLAUDE.md §10).
The settings-only helper _parse_sheet_url moves in as a nested function. Injected:
_cfg, CONFIG_PATH, _state, _client. ai_providers is imported inline in the bodies.

Routes: GET/POST /ai/settings, POST /admin/logic_settings, GET /ai/test,
        GET/POST /settings/ebay
"""
import json

from flask import request, jsonify

from config import settings as _settings


def register(app, *, _cfg, CONFIG_PATH, _state, _client):
    """Attach the settings / ai / admin routes to the existing Flask app."""

    @app.route("/ai/settings", methods=["GET", "POST"])
    def ai_settings():
        """Read or save which OpenRouter model is used for each purpose. GET also
        returns the live list of available text + image models (discovered from
        OpenRouter), so the dashboard dropdowns show only usable models."""
        try:
            import ai_providers
        except Exception:
            return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
        cfg = _cfg()
        if request.method == "GET":
            force = request.args.get("refresh") == "1"
            disc = ai_providers.discover_models(cfg, force=force)
            return jsonify({
                "ok": True,
                "has_key": bool(cfg.get("openrouter_api_key", "").strip()),
                "discover_ok": disc.get("ok", False),
                "discover_error": disc.get("error", ""),
                "text_models": disc.get("text", []),
                "image_models": disc.get("image", []),
                "select": {
                    "prompt_enhance": ai_providers.select(cfg, "prompt_enhance"),
                    "image_generate": ai_providers.select(cfg, "image_generate"),
                },
                "admin": {
                    # whether the "how it works" logic panels are shown at all,
                    # and whether the admin is currently previewing as a normal user
                    "show_logic": bool(cfg.get("show_logic", True)),
                    "preview_as_user": bool(cfg.get("preview_as_user", False)),
                },
            })
        b = request.get_json(force=True) or {}
        try:
            raw = json.load(open(CONFIG_PATH, encoding="utf-8"))
            sel = raw.get("ai_select") or {}
            if b.get("prompt_enhance"):
                sel["prompt_enhance"] = b["prompt_enhance"]
            if b.get("image_generate"):
                sel["image_generate"] = b["image_generate"]
            raw["ai_select"] = sel
            json.dump(raw, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            _state["cfg"] = None
            return jsonify({"ok": True, "select": sel})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500


    @app.route("/admin/logic_settings", methods=["POST"])
    def admin_logic_settings():
        """Save the admin's 'how it works' preferences: show_logic (master on/off for
        the logic disclosure panels) and preview_as_user (temporarily view the app as a
        non-admin would, i.e. with logic hidden, regardless of show_logic)."""
        b = request.get_json(force=True) or {}
        try:
            raw = json.load(open(CONFIG_PATH, encoding="utf-8"))
            if "show_logic" in b:
                raw["show_logic"] = bool(b["show_logic"])
            if "preview_as_user" in b:
                raw["preview_as_user"] = bool(b["preview_as_user"])
            json.dump(raw, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            _state["cfg"] = None
            return jsonify({"ok": True,
                            "show_logic": bool(raw.get("show_logic", True)),
                            "preview_as_user": bool(raw.get("preview_as_user", False))})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500


    @app.route("/ai/test")
    def ai_test():
        """Quick diagnostic: is the OpenRouter key present and reachable? Returns
        fast so the user can tell config problems from slow generations."""
        try:
            import ai_providers
        except Exception as e:
            return jsonify({"ok": False, "error": f"ai_providers import failed: {e}"}), 500
        cfg = _cfg()
        key = (cfg.get("openrouter_api_key", "") or "").strip()
        if not key or key.startswith("PUT_YOUR") or key.startswith("ROTATE"):
            return jsonify({"ok": False, "stage": "key",
                            "error": "No real openrouter_api_key in config.json (still a placeholder)."})
        disc = ai_providers.discover_models(cfg, force=True)
        if not disc.get("ok"):
            return jsonify({"ok": False, "stage": "discover", "error": disc.get("error", "discovery failed")})
        return jsonify({"ok": True,
                        "text_count": len(disc.get("text", [])),
                        "image_count": len(disc.get("image", [])),
                        "image_model": ai_providers.select(cfg, "image_generate"),
                        "text_model": ai_providers.select(cfg, "prompt_enhance")})


    # /settings/dropshipping_sheets was here. It edited the default sheets the
    # built-in Dropshipping workspace read from, and that workspace has been
    # removed: it described itself as "eBay -> Amazon arbitrage", which
    # CLAUDE.md rule 1 says this app does not do. No dropshipping_* key was ever
    # set in config.json, so nothing was migrated -- there was nothing to
    # migrate. Every account sets its own sheets from its own card.



    def _parse_sheet_url(url: str):
        """Extract (spreadsheet_id, tab_gid) from a full Google Sheets URL (or a bare
        id). Returns ('','') if no id is found. Server-side mirror of the client's
        parseSheetUrl so both paths agree on how a link is read."""
        import re as _re
        u = str(url or "").strip()
        if not u:
            return "", ""
        m = _re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", u)
        sid = m.group(1) if m else (u if _re.fullmatch(r"[a-zA-Z0-9_-]{20,}", u) else "")
        g = _re.search(r"[#?&]gid=(\d+)", u)
        return sid, (g.group(1) if g else "")


    @app.route("/settings/ads", methods=["GET", "POST"])
    def settings_ads():
        """The Amazon ADVERTISING credentials -- a different login from SP-API.

        Six of Orbit's PPC features cannot be built from the Search Term Report
        and are not blocked on effort: the day trail, the 7/14/30 toggle, the
        per-ASIN table, the SP/SB/SD split, the enabled/paused filter and the
        live tracker. All six need this connection, and only the account owner
        can make it -- it is its own developer registration, its own
        Login-with-Amazon application and its own refresh token.

        Same shape as the eBay keys: one set can serve every account, and an
        account advertising through its own agency login overrides it on the
        account object. GET never returns a secret -- only whether one is
        stored and its last four characters, so you can tell which is saved.
        """
        from api import amazon_ads as _ads

        cfg = _cfg()
        if request.method == "GET":
            def tail(v):
                v = str(v or "")
                return (v[-4:] if len(v) >= 4 else "•" * len(v)) if v else ""
            return jsonify({
                "ok": True,
                "ads_client_id": str(cfg.get("ads_client_id", "") or ""),
                "ads_profile_id": str(cfg.get("ads_profile_id", "") or ""),
                "has_secret": bool(str(cfg.get("ads_client_secret", "") or "").strip()),
                "secret_tail": tail(cfg.get("ads_client_secret")),
                "has_refresh": bool(str(cfg.get("ads_refresh_token", "") or "").strip()),
                "refresh_tail": tail(cfg.get("ads_refresh_token")),
                "fields": list(_ads.FIELDS),
            })
        b = request.get_json(force=True) or {}
        try:
            raw = _settings.read_raw(CONFIG_PATH)
            for f in ("ads_client_id", "ads_profile_id"):
                if f in b:
                    raw[f] = str(b.get(f) or "").strip()
            # A blank secret KEEPS the stored one, so editing the client id
            # alone cannot wipe the token. Same rule as the eBay cert above.
            for f in ("ads_client_secret", "ads_refresh_token"):
                v = str(b.get(f) or "").strip()
                if v and not v.startswith(("•", "*", "PUT_", "ROTATE")):
                    raw[f] = v
            _settings.write_raw(raw, CONFIG_PATH)
            _state["cfg"] = None
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/settings/ads/test", methods=["POST"])
    def settings_ads_test():
        """Does the advertising connection actually work?

        Makes ONE real call -- the token exchange, then listing the profiles
        this login can see. Listing them is also how the profile id gets set
        honestly: pick from what Amazon says exists rather than typing a number
        off a screenshot.

        Read-only. Nothing in api/amazon_ads.py can write a bid, a budget or a
        campaign state (CLAUDE.md Rule 8).
        """
        from api import amazon_ads as _ads

        # The open account, resolved the same way every other route here does --
        # from _state, against the accounts in config. An account may override
        # the global advertising login with its own, so which one is open
        # changes the answer.
        cfg = _cfg() or {}
        aid = str((_state or {}).get("active_account_id") or "")
        acc = next((a for a in (cfg.get("accounts") or [])
                    if str(a.get("id")) == aid), {}) if aid else {}
        mkt = (request.get_json(silent=True) or {}).get("marketplace") \
            or acc.get("default_marketplace") \
            or (_state or {}).get("active_marketplace") or "UK"
        return jsonify(_ads.test(_cfg, acc, mkt))

    @app.route("/settings/ebay", methods=["GET", "POST"])
    def settings_ebay():
        """View / update the GLOBAL eBay Browse-API credentials (used to scrape the
        source product for each row). GET never returns the raw Cert ID (secret) --
        only the App ID (a public client id) and whether a Cert is stored, plus a
        masked tail so the user can recognise which key is saved. POST saves; a blank
        Cert ID keeps the existing one (so editing the App ID alone won't wipe it).
        Per-account overrides live on the account object (see /accounts/save)."""
        cfg = _cfg()
        if request.method == "GET":
            cert = str(cfg.get("ebay_cert_id", "") or "")
            return jsonify({
                "ok": True,
                "ebay_app_id": str(cfg.get("ebay_app_id", "") or ""),
                "has_cert": bool(cert.strip()),
                # last 4 chars only, so the user can tell which secret is saved
                "cert_tail": (cert[-4:] if len(cert) >= 4 else ("•" * len(cert))) if cert else "",
            })
        b = request.get_json(force=True) or {}
        try:
            raw = json.load(open(CONFIG_PATH, encoding="utf-8"))
            if "ebay_app_id" in b:
                raw["ebay_app_id"] = str(b.get("ebay_app_id", "") or "").strip()
            # only overwrite the secret when a real, non-masked value is supplied
            _cert = str(b.get("ebay_cert_id", "") or "").strip()
            if _cert and not _cert.startswith(("•", "*", "PUT_", "ROTATE")):
                raw["ebay_cert_id"] = _cert
            json.dump(raw, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            _state["cfg"] = None
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
