"""routes/misc_routes.py — small standalone utility endpoints, extracted from dashboard.py (Phase 3).

Two independent single routes that don't belong to a larger domain group yet:
  POST /sp_diagnose -> run the SP-API end-to-end diagnostic script (injects CONFIG_PATH)
  POST /dup_check   -> check whether SKU(s) already exist as live Amazon listings
                       (injects _active_account, _state)
register(app, ...) injection pattern; bodies VERBATIM (CLAUDE.md §10). These can be
re-homed later (dup_check is listing-adjacent) without changing behaviour.
"""
import os

from flask import request, jsonify


def register(app, *, CONFIG_PATH, _active_account, _state):
    """Attach the standalone utility routes to the existing Flask app."""

    @app.route("/sp_diagnose", methods=["POST"])
    def sp_diagnose_run():
        """One-shot end-to-end SP-API diagnostic. Runs the standalone script so it
        tests EVERY layer -- DNS, TCP, TLS, LWA auth, and each SP-API operation --
        and streams the plain-text result back. Uses the ACTIVE account's creds."""
        import subprocess, sys as _sys
        b = request.get_json(silent=True) or {}
        mkt = (b.get("marketplace", "") or "UK").upper()
        acct = (b.get("account_id", "") or "").strip()
        script = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "sp_diagnose.py")
        if not os.path.exists(script):
            return jsonify({"ok": False, "error": f"sp_diagnose.py not found at {script}"}), 404
        args = [_sys.executable, "-u", script, "--marketplace", mkt]
        if acct:
            args += ["--account-id", acct]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=180,
                                  cwd=os.path.dirname(os.path.abspath(CONFIG_PATH)))
            # strip ANSI colour codes for clean display in the browser
            import re as _re
            clean = _re.sub(r"\x1b\[[0-9;]*m", "", (proc.stdout or "") + (proc.stderr or ""))
            return jsonify({"ok": True, "exit_code": proc.returncode, "output": clean})
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "diagnostic timed out after 180s"}), 500
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500


    @app.route("/dup_check", methods=["POST"])
    def dup_check():
        """Check whether the given SKU(s) ALREADY exist as live listings on Amazon
        for the active account (via getListingsItem). Returns the subset that exist,
        so the UI can warn 'already on Amazon -- continue?' before generating/creating.
        This is the Amazon-side safety net (the sheet-side check happens in the
        generator)."""
        b = request.get_json(force=True) or {}
        skus = b.get("skus") or []
        if isinstance(skus, str):
            skus = [skus]
        skus = [str(s).strip() for s in skus if str(s).strip()]
        if not skus:
            return jsonify({"ok": True, "exists": [], "checked": 0})
        acc = _active_account()
        if not acc:
            return jsonify({"ok": False, "error": "no active account"}), 400
        rt = str(acc.get("refresh_token", ""))
        if not rt or rt.startswith(("PUT_", "ROTATE")):
            return jsonify({"ok": False, "error": "connect this account first"}), 400
        try:
            import accounts as _acc
            creds = _acc.account_creds(acc)
        except Exception as e:
            return jsonify({"ok": False, "error": f"creds error: {str(e)[:120]}"}), 500
        seller = acc.get("seller_id", "")
        mkt = (_state.get("active_marketplace") or acc.get("default_marketplace") or "UK").upper()
        try:
            from sp_api.api import ListingsItemsV20210801 as LI
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api Listings not available: {e}"}), 500
        mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.UK
        try:
            mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
        except Exception:
            mid = ""
        exists = []
        checked = 0
        try:
            li = LI(credentials=creds, marketplace=mkt_enum)
            for sku in skus[:50]:   # cap to keep it quick
                checked += 1
                try:
                    resp = li.get_listings_item(seller, sku,
                                                marketplaceIds=[mid] if mid else None,
                                                includedData="summaries")
                    pay = resp.payload if hasattr(resp, "payload") else resp
                    # a real listing returns summaries with a status; 404s raise instead
                    summ = (pay or {}).get("summaries", []) if isinstance(pay, dict) else []
                    if summ:
                        _title = ""
                        try:
                            _title = summ[0].get("itemName", "") or ""
                        except Exception:
                            _title = ""
                        exists.append({"sku": sku, "title": _title})
                except Exception:
                    # getListingsItem raises 404 when the SKU is NOT on Amazon -> not a dup
                    pass
        except Exception as e:
            return jsonify({"ok": False, "error": f"check failed: {str(e)[:160]}"}), 502
        return jsonify({"ok": True, "exists": exists, "checked": checked,
                        "marketplace": mkt, "account_label": acc.get("label", "")})
