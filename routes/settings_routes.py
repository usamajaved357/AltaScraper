"""routes/settings_routes.py — AI/model, admin, and sheet/eBay settings endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern; route bodies moved VERBATIM (CLAUDE.md §10).
The settings-only helper _parse_sheet_url moves in as a nested function. Injected:
_cfg, CONFIG_PATH, _state, _client. ai_providers is imported inline in the bodies.

Routes: GET/POST /ai/settings, POST /admin/logic_settings, GET /ai/test,
        GET/POST /settings/dropshipping_sheets, GET/POST /settings/ebay
"""
import json

from flask import request, jsonify


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


    @app.route("/settings/dropshipping_sheets", methods=["GET", "POST"])
    def settings_dropshipping_sheets():
        """View / update the DEFAULT (Dropshipping / no-account) input + output sheets.
        The built-in Dropshipping workspace has no account object, so it previously
        always fell back to the hardcoded google_spreadsheet_id + OUTPUT_TAB. This lets
        a user point it at any sheet/tab from the UI, exactly like a real account.
        POST accepts full Google Sheets URLs, parses id + gid, resolves the output tab
        NAME (so api/regen runs -- which open the worksheet by name -- hit the right
        tab), and saves. Blank clears the override -> back to config defaults."""
        cfg = _cfg()
        if request.method == "GET":
            return jsonify({
                "ok": True,
                "output_sheet_url": cfg.get("dropshipping_output_sheet_url", ""),
                "input_sheet_url":  cfg.get("dropshipping_input_sheet_url", ""),
                "output_tab":       cfg.get("dropshipping_output_tab", ""),
            })
        b = request.get_json(force=True) or {}
        out_url = str(b.get("output_sheet_url", "") or "").strip()
        in_url  = str(b.get("input_sheet_url", "") or "").strip()
        out_id, out_gid = _parse_sheet_url(out_url)
        in_id,  in_gid  = _parse_sheet_url(in_url)
        if out_url and not out_id:
            return jsonify({"ok": False, "error": "couldn't read a sheet ID from the output link"}), 400
        if in_url and not in_id:
            return jsonify({"ok": False, "error": "couldn't read a sheet ID from the input link"}), 400
        # resolve the output tab NAME from its gid (best-effort; run_api opens by name)
        out_tab = ""
        if out_id and out_gid.isdigit():
            try:
                _wsg = _client().open_by_key(out_id).get_worksheet_by_id(int(out_gid))
                if _wsg is not None:
                    out_tab = _wsg.title
            except Exception:
                out_tab = ""
        try:
            raw = json.load(open(CONFIG_PATH, encoding="utf-8"))
            raw["dropshipping_output_sheet_url"]      = out_url
            raw["dropshipping_output_spreadsheet_id"] = out_id
            raw["dropshipping_output_tab_gid"]        = out_gid
            raw["dropshipping_output_tab"]            = out_tab
            raw["dropshipping_input_sheet_url"]       = in_url
            raw["dropshipping_input_spreadsheet_id"]  = in_id
            raw["dropshipping_input_tab_gid"]         = in_gid
            json.dump(raw, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            _state["cfg"] = None
            return jsonify({"ok": True, "output_tab": out_tab,
                            "output_sheet_id": out_id, "input_sheet_id": in_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500


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
