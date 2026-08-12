"""routes/ui_routes.py — extracted from dashboard.py (Phase 3). Bodies VERBATIM.

Auto-extracted @app.route("paths:/,/ui,/stop,/save_default...") funcs; shared helpers injected. Verified with
verify_free_vars.py.
"""
from flask import (request, jsonify, Response, send_from_directory,
                   render_template, redirect)
from urllib.parse import quote
import json
import os


def register(app, *, CONFIG_PATH, _kill_proc, _records, _run_lock, _running, _ws):
    """Attach the paths:/,/ui,/stop,/save_default routes to the existing Flask app."""

    @app.route("/save_default", methods=["POST"])
    def save_default():
        """Remember a listing's current attributes as defaults for its product type,
        so future listings of that type prefill them (attribute_defaults.json, shared
        with amazon_listing_generator.py)."""
        b   = request.get_json(force=True) or {}
        sku = str(b.get("sku", "")).strip()
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        try:
            rec = next((r for r in _records(_ws()) if str(r.get("SKU", "")).strip() == sku), None)
            if not rec:
                return jsonify({"ok": False, "error": "row not found (refresh and retry)"}), 404
            pt = str(rec.get("Product Type", "")).strip()
            if not pt:
                return jsonify({"ok": False, "error": "this row has no Product Type"}), 400
            try:
                attrs = json.loads(rec.get("Attributes JSON", "") or "{}")
            except Exception:
                attrs = {}
            attrs = {k: v for k, v in (attrs.items() if isinstance(attrs, dict) else [])
                     if str(v).strip() != ""}
            if not attrs:
                return jsonify({"ok": False, "error": "no filled attributes to remember"}), 400
            path = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "attribute_defaults.json")
            try:
                data = json.load(open(path, encoding="utf-8"))
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            cur = data.get(pt, {})
            if not isinstance(cur, dict):
                cur = {}
            cur.update(attrs)
            data[pt] = cur
            json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            return jsonify({"ok": True, "pt": pt, "count": len(cur)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500

    @app.route("/")
    def index():
        return render_template("dashboard.html")

    # ---- Addressable workspace pages -------------------------------------
    # Plain English: until now the whole app lived at one web address ("/"), so
    # refreshing always threw you back to the workspace list and no screen could
    # be bookmarked or opened in a second tab. Each screen now has its own
    # address, e.g. /w/nestwell/ppc. These serve the SAME dashboard.html as "/";
    # the browser-side router in static/js/shell.js reads the address on load and
    # reopens that workspace and section.
    #
    # Deliberately an explicit list of sections, not a catch-all rule. A
    # catch-all would answer a mistyped API path with the dashboard's HTML
    # instead of an honest 404, which turns a one-line typo into an hour of
    # debugging.
    _SECTIONS = ("listings", "imagerefs", "setup", "generate", "ppc",
                 "inventory", "sync", "monitor", "miles")

    @app.route("/w/<ws>")
    def workspace_root(ws):
        """A workspace with no section named opens on its listings."""
        return redirect("/w/" + quote(ws, safe="") + "/listings")

    @app.route("/w/<ws>/<section>")
    def workspace_page(ws, section):
        """Serve the dashboard for a deep link. The workspace name is not checked
        here on purpose -- which workspaces exist is answered by /accounts/list,
        and the browser router reports an unknown one to the user rather than
        silently opening someone else's data."""
        if section not in _SECTIONS:
            return Response(
                "Unknown section '%s'. Valid sections: %s"
                % (section, ", ".join(_SECTIONS)),
                status=404, mimetype="text/plain")
        return render_template("dashboard.html")

    @app.route("/ui")
    def ui_preview():
        """ADDITIVE preview of the new 'ListingOS' layout, served from the live app so
        the page can call the real endpoints (/accounts/list, /rows, ...) on the same
        origin. This does NOT touch the existing dashboard at '/'. Read fresh from disk
        each request so edits to ui/index.html show on refresh with no restart."""
        try:
            _p = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "ui", "index.html")
            with open(_p, encoding="utf-8") as _f:
                return Response(_f.read(), mimetype="text/html")
        except Exception as e:
            return Response(f"<pre>ui/index.html not found: {e}</pre>",
                            mimetype="text/html", status=404)

    @app.route("/stop", methods=["POST"])
    def stop():
        p = _running.get("proc")
        was_on = bool(_running.get("on"))
        # Kill the child if it's still alive.
        if p is not None:
            try:
                _kill_proc(p)
            except Exception:
                pass
        # ALWAYS clear the lock -- even if proc was already gone. This is what makes
        # Stop a reliable un-stick for a wedged lock (stream abandoned, on=True,
        # proc=None) instead of returning "nothing is running" and leaving it stuck.
        with _run_lock:
            _running["on"] = False
            _running["proc"] = None
            _running["started"] = 0.0
        return jsonify({"ok": True, "was_running": was_on})

