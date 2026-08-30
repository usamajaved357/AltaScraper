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
    # Deliberately not a catch-all rule. A catch-all would answer a mistyped API
    # path with the dashboard's HTML instead of an honest 404, which turns a
    # one-line typo into an hour of debugging.
    #
    # BUT THE LIST IS READ FROM THE MENU, NOT TYPED HERE.
    #
    # It WAS typed here -- twelve sections, written when there were twelve. The
    # app has forty. The other twenty-eight were never added, so every one of
    # them answered a refresh, a bookmark or a second tab with a plain-text 404:
    #
    #     weekly, daily, orders, returns, variations, sellerimport, sourcing,
    #     finance, aiusage, imagestudio, imagelib, trackers, alerts, leading,
    #     notify, sqp, catalog, compliance, categories, drppc, permissions,
    #     reimbursements, brief, kwspy, kwasin, ranktracker, kwhistory, asinstudio
    #
    # Measured 21 Aug 2026 by asking for all forty: 12 served, 28 refused. That
    # includes Orders, Finance and every screen added since -- and the bookmark
    # bar exists to make links to exactly these.
    #
    # Two lists of "what screens exist" drift, and these did. The menu is the
    # one definition: data-sec in templates/dashboard.html, which is also what
    # the Ctrl+K palette reads (rule 12). A section added to the menu is
    # deep-linkable the same day, and a path that is not in the menu is still an
    # honest 404.
    _TPL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "templates", "dashboard.html")
    _sec_cache = {"stamp": None, "secs": ()}

    def _sections():
        """The section ids the menu offers. Re-read when the template changes.

        Cached on the template's modification time: on a server the file never
        changes after boot, and locally an edit takes effect on the next request
        without a restart -- the same rule ASSET_V uses.
        """
        try:
            stamp = os.path.getmtime(_TPL)
        except OSError:
            return _sec_cache["secs"] or ("listings",)
        if _sec_cache["stamp"] != stamp:
            import re as _re
            try:
                with open(_TPL, encoding="utf-8") as fh:
                    html = fh.read()
                found = tuple(dict.fromkeys(
                    _re.findall(r'data-sec="([\w-]+)"', html)))
            except Exception:
                found = ()
            # Never end up with nothing: an unreadable template would otherwise
            # 404 the whole app, including the screen it is trying to serve.
            _sec_cache["secs"] = found or ("listings",)
            _sec_cache["stamp"] = stamp
        return _sec_cache["secs"]

    @app.route("/w/<ws>")
    def workspace_root(ws):
        """A workspace with no section named opens on its listings."""
        return redirect("/w/" + quote(ws, safe="") + "/listings")

    @app.route("/w/<ws>/listing/<path:sku>")
    def workspace_listing(ws, sku):
        """One listing, open full screen: /w/<workspace>/listing/<sku>.

        Serves the same dashboard; the browser router (shell.js
        altaRouteFromUrl) reads the address and opens that listing's page once
        the workspace and its rows are loaded.

        <path:sku> rather than the default converter because a SKU is
        price_days_ASIN -- it contains dots, and the default converter would
        also refuse one containing a slash. Nothing about the SKU is checked
        here: which listings exist is answered by /rows for the open account,
        and the router reports one it cannot find to the user. Checking here
        would mean a second, different answer to that question, from a route
        that does not know which workspace the browser has open.

        DECLARED ABOVE /w/<ws>/<section> ON PURPOSE. Flask's routing is not
        order-dependent -- it ranks by specificity -- but a reader's is, and
        "listing" would otherwise look like a section name that is missing from
        the template.
        """
        return render_template("dashboard.html")

    @app.route("/w/<ws>/<section>")
    def workspace_page(ws, section):
        """Serve the dashboard for a deep link. The workspace name is not checked
        here on purpose -- which workspaces exist is answered by /accounts/list,
        and the browser router reports an unknown one to the user rather than
        silently opening someone else's data."""
        secs = _sections()
        if section not in secs:
            return Response(
                "Unknown section '%s'. Valid sections: %s"
                % (section, ", ".join(secs)),
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
        # or one that never attached its subprocess.
        #
        # THE CONDITION USED TO INCLUDE `not _SLOTS.busy()`, and that made Stop
        # useless in the case it was most needed: a run whose slot exists but
        # whose subprocess never attached, or one whose slot belongs to another
        # account. Nothing was stopped, the slots were busy, so the fallback was
        # skipped too, and Stop cheerfully reported success while the generator
        # carried on spending. Now: if nothing of the caller's was stopped and
        # there is a live process, end it. `left` above already records what
        # belongs to somebody else, and that is what the reply reports.
        if not stopped:
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

