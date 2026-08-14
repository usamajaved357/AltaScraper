"""routes/ui_routes.py — extracted from dashboard.py (Phase 3). Bodies VERBATIM.

Auto-extracted @app.route("paths:/,/ui,/stop,/save_default...") funcs; shared helpers injected. Verified with
verify_free_vars.py.
"""
from flask import (request, jsonify, Response, send_from_directory,
                   render_template, redirect)
from urllib.parse import quote
import json
import os


def register(app, *, CONFIG_PATH, _kill_proc, _records, _run_lock, _running, _ws,
             _state=None):
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
    _SECTIONS = ("listings", "imagerefs", "setup", "generate", "sales", "ppc",
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
        """Stop YOUR runs.

        This used to end whatever single run existed, from anyone holding "edit"
        -- so a Lister pressing Stop killed the owner's submit mid-flight. Runs
        are now per account and per SKU, and each records who started it, so Stop
        ends the caller's own and leaves colleagues alone. The shared-password
        owner is the only user, so for them it still means everything.
        """
        from domain.run_slots import SLOTS as _SLOTS
        from domain import job_owner as _jo
        was_on = bool(_running.get("on"))
        uid = _jo.current()
        # AND ONLY IN THIS ACCOUNT. Owner was the only filter, and for the
        # shared-password owner -- the only user on most installs -- owner is
        # empty, so Stop meant every run on the server. Pressing it in Jack
        # Reacherd ended a Nestwell Goods submit that was halfway through.
        # Defaults to None when the caller did not inject state, in which case
        # Stop keeps its old meaning rather than silently stopping nothing.
        acct = str((_state or {}).get("active_account_id", "") or "")
        stopped = _SLOTS.stop(owner=(uid or None), account=(acct or None))
        # What was deliberately left alone, so Stop never silently does less
        # than it appears to.
        left = [s for s in _SLOTS.active()
                if not acct or str(s.get("account") or "") != acct]

        # The legacy single-proc handle, for a run started before slots existed
        # or one that never attached its subprocess. Only touched when the caller
        # has nothing of their own left running, so it cannot reach across into
        # somebody else's work.
        if not stopped and not _SLOTS.busy():
            p = _running.get("proc")
            if p is not None:
                try:
                    _kill_proc(p)
                except Exception:
                    pass
            # ALWAYS clear the flag -- even if proc was already gone. This is what
            # makes Stop a reliable un-stick for a wedged run (stream abandoned,
            # on=True, proc=None) rather than "nothing is running, still stuck".
            with _run_lock:
                _running["on"] = False
                _running["proc"] = None
                _running["started"] = 0.0
        return jsonify({"ok": True, "was_running": was_on, "stopped": stopped,
                        "account": acct,
                        "left_running_elsewhere": len(left),
                        "note": ("" if not left else
                                 "%d run%s in your other accounts %s left alone."
                                 % (len(left), "" if len(left) == 1 else "s",
                                    "was" if len(left) == 1 else "were"))})

