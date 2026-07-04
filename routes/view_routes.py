"""routes/view_routes.py — sheet/tab "view" switcher endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern. _state (mutable, same object) and _cfg are
injected; CONFIG_PATH / OUTPUT_TAB are passed as values. Bodies moved VERBATIM.

Routes:
  GET  /view/list -> list the Dropshipping view + every saved brand's sheet/tab
  POST /view/set  -> switch which sheet/tab the dashboard reads
"""
import json

from flask import request, jsonify


def register(app, *, _state, _cfg, CONFIG_PATH, OUTPUT_TAB):
    """Attach the /view/* routes to the existing Flask app."""

    @app.route("/view/list")
    def view_list():
        """List available views: the default sheet + every saved brand's sheet/tab."""
        import glob, os, re
        views = [{"key": "", "label": "Dropshipping", "sheet": "", "tab": "",
                  "brand": "", "marketplace": "UK · US", "count": None}]
        base = os.path.join(os.path.dirname(CONFIG_PATH), "brands")
        for pf in glob.glob(os.path.join(base, "*", "profile.json")):
            try:
                p = json.load(open(pf, encoding="utf-8"))
            except Exception:
                continue
            name = p.get("brand_name") or os.path.basename(os.path.dirname(pf))
            sid = (p.get("output_spreadsheet_id") or "").strip()
            m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sid)
            if m:
                sid = m.group(1)
            tab = (p.get("output_tab") or "").strip()
            mkt = (p.get("marketplace", "") or "")
            label = name
            views.append({"key": name, "label": label, "sheet": sid, "tab": tab,
                          "brand": name, "marketplace": mkt, "count": None})
        return jsonify({"ok": True, "views": views, "active": _state.get("active_view", "")})

    @app.route("/view/set", methods=["POST"])
    def view_set():
        """Switch which sheet/tab the dashboard reads."""
        body = request.get_json(force=True, silent=True) or {}
        sheet = (body.get("sheet") or "").strip()
        tab   = (body.get("tab") or "").strip()
        key   = (body.get("key") or "").strip()
        _state["active_sheet_id"] = sheet or None
        _state["active_tab"]      = tab or None
        _state["active_view"]     = key
        # resolve & cache the marketplace for this brand (for $/£ display)
        _mkt = ""
        if key:
            try:
                import glob as _g, os as _o
                for _pf in _g.glob(_o.path.join(_o.path.dirname(CONFIG_PATH), "brands", "*", "profile.json")):
                    _p = json.load(open(_pf, encoding="utf-8"))
                    if (_p.get("brand_name") or "") == key:
                        _mkt = _p.get("marketplace", "") or ""
                        break
            except Exception:
                pass
        _state["active_marketplace"] = _mkt
        return jsonify({"ok": True, "active": key,
                        "sheet": sheet or _cfg()["google_spreadsheet_id"],
                        "tab": tab or OUTPUT_TAB})
