"""
dashboard_brand_patch.py  --  Brand-listing UI + routes for dashboard.py

WHY A SEPARATE FILE
-------------------
Same philosophy as PATCH_apply_to_original_script.py: add capability BESIDE the
original instead of surgically rewriting a 1200-line embedded HTML string. You
register these routes and inject one self-contained panel; the existing review
dashboard is untouched.

WHAT IT ADDS
------------
  GET  /brand/list           -> list saved brand profiles (brands/*/profile.json)
  POST /brand/save           -> create/update a brand profile (Brand Settings tab)
  GET  /brand/get/<name>     -> load one profile (+ tone dropdown options)
  POST /brand/connection     -> save the Drive connection (Connections tab)
  GET  /brand/connection     -> read current connection (defaults to owner's)
  POST /brand/preview        -> parse a Shopify export, return product count +
                                detected source language + vendor list (no Claude)
  GET  /brand/run/<name>     -> stream a brand run (subprocess, like /run/<mode>)
  GET  /brand/panel          -> the HTML/JS for the Brand panel (injected client-side)

The "i" provenance button is rendered client-side from each row's Attributes JSON
(`_provenance`), which brand_listing.py already writes. No backend change needed
for it beyond what the review cards already expose.

HOW TO WIRE (3 tiny edits to dashboard.py)
------------------------------------------
  EDIT A -- at the top of dashboard.py, after `app = Flask(__name__)`:
        import dashboard_brand_patch
        dashboard_brand_patch.register(app, _cfg, _ws, _records, _run_lock,
                                       _running, _ANSI, SCRIPT, sys)

  EDIT B -- in the /run/<mode> allowed-modes check, add "brand" (optional; the
        brand run uses its own /brand/run/<name> route, so this is only needed if
        you also want the generic runner to accept it).

  EDIT C -- in the page, add a "Brand" pill and a container the panel mounts into.
        The register() call injects a loader so you only add this near your other
        pills in _HTML:
            <span class="pill" id="pill-brand" onclick="loadBrandPanel()">Brand</span>
            <div id="brandpanel" style="display:none;padding:18px"></div>
        and this <script> just before </body>:
            <script>
            async function loadBrandPanel(){
              const host=document.getElementById('brandpanel');
              if(!host.dataset.loaded){
                host.innerHTML = await (await fetch('/brand/panel')).text();
                host.dataset.loaded='1';
                if(window.brandInit) brandInit();
              }
              document.querySelector('main').style.display='none';
              host.style.display='block';
            }
            </script>
"""

import json
import subprocess
from pathlib import Path

from flask import Response, request, jsonify

import brand_profile
from routes.stream_pump import pump_lines, spawn


BASE_DIR = Path(__file__).parent


def register(app, _cfg, _ws, _records, _run_lock, _running, _ANSI, SCRIPT, sysmod, _state=None, CONFIG_PATH="config.json"):
    """Attach all brand routes to the existing Flask app."""
    global BASE_DIR
    # Same directory as the real config.json (the persistent disk in production,
    # e.g. /data) -- not this module's own /app location -- so brand profiles,
    # uploads, and media survive a redeploy.
    BASE_DIR = Path(CONFIG_PATH).resolve().parent

    # ---- brand profiles -----------------------------------------------------
    @app.route("/brand/list")
    def brand_list():
        cfg = _cfg()
        brands = brand_profile.list_brands(cfg, BASE_DIR)
        # SCOPE to the active account: only show brands assigned to it. If an
        # account is active, its config "brands" list is the allow-list. The
        # Dropshipping workspace (no active account) shows none of the account
        # trademarks. This stops brands leaking across accounts.
        try:
            aid = _state.get("active_account_id") if _state else None
        except Exception:
            aid = None
        allow = None
        if aid:
            try:
                import accounts as _acc
                acc = _acc.get_account(cfg, aid, CONFIG_PATH)
                allow = set([b.strip().lower() for b in (acc.get("brands") or []) if b])
            except Exception:
                allow = None
        out = []
        for b in brands:
            bn = b.get("brand_name", "")
            if allow is not None and bn.strip().lower() not in allow:
                continue
            out.append({"brand_name": bn,
                        "vendor_mode": b.get("vendor_mode", ""),
                        "marketplace": b.get("marketplace", ""),
                        "source_language": b.get("source_language", "en")})
        return jsonify({"brands": out})

    @app.route("/brand/get/<path:name>")
    def brand_get(name):
        cfg = _cfg()
        prof = brand_profile.load_profile(cfg, BASE_DIR, name)
        prof["_tone_options"] = brand_profile.tone_dropdown_options(
            prof.get("source_language", "en"))
        return jsonify(prof)

    @app.route("/brand/save", methods=["POST"])
    def brand_save():
        cfg = _cfg()
        body = request.get_json(force=True) or {}
        bn = (body.get("brand_name", "") or "").strip()
        if not bn:
            return jsonify({"ok": False, "error": "brand_name required"}), 400
        # normalise list fields that arrive as comma-separated strings
        for key in ("competitor_asins", "forbidden_brands"):
            v = body.get(key)
            if isinstance(v, str):
                body[key] = [x.strip() for x in v.split(",") if x.strip()]
        path = brand_profile.save_profile(cfg, BASE_DIR, body)
        # ASSIGN the brand to the active account. Without this the saved profile is
        # invisible -- /brand/list is scoped to the account's own "brands" list -- so
        # the page still says "No brands saved yet", AND a submit is blocked with
        # "no trademark set for this account" (the generator's BRAND GUARD reads the
        # same account list). Saving a brand and using it are the same intent.
        assigned = False
        try:
            aid = _state.get("active_account_id") if _state else None
        except Exception:
            aid = None
        if aid:
            try:
                import accounts as _acc
                acc = _acc.get_account(cfg, aid, CONFIG_PATH) or {}
                brands = [str(x).strip() for x in (acc.get("brands") or []) if str(x).strip()]
                if bn.lower() not in [x.lower() for x in brands]:
                    brands.append(bn)
                    # minimal patch (id + brands) so we never clobber sheet ids/creds
                    _acc.save_account(cfg, CONFIG_PATH, {"id": aid, "brands": brands})
                if _state is not None:
                    _state["cfg"] = None   # force a reload so the new brand shows now
                assigned = True
            except Exception:
                assigned = False
        return jsonify({"ok": True, "path": path, "assigned_to_account": assigned})

    # ---- connection (Drive auth) -------------------------------------------
    @app.route("/brand/connection", methods=["GET", "POST"])
    def brand_connection():
        cfg = _cfg()
        if request.method == "GET":
            return jsonify(brand_profile.load_connection(cfg))
        body = request.get_json(force=True) or {}
        conn = brand_profile.load_connection(cfg)
        conn.update({k: v for k, v in body.items() if k in conn})
        cfg["connection"] = conn
        # persist back to config.json (same file the app already uses)
        # ATOMICALLY: open(path, "w") empties config.json before writing a
        # byte, and a crash in between loses every credential (Milestone 1).
        try:
            from config import settings as _settings
            if not _settings.write_raw(cfg, CONFIG_PATH):
                raise OSError("could not write config.json")
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:160]}), 500
        return jsonify({"ok": True, "connection": conn})

    # ---- Shopify export upload (browse from local computer) ------------------
    @app.route("/brand/upload", methods=["POST"])
    def brand_upload():
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"ok": False, "error": "no file"}), 400
        name = f.filename
        # keep only a safe base filename; force into the app folder
        safe = "".join(ch for ch in Path(name).name
                       if ch.isalnum() or ch in (" ", ".", "_", "-")).strip()
        if not safe.lower().endswith((".csv", ".txt", ".tsv")):
            return jsonify({"ok": False, "error": "please choose a Shopify CSV export"}), 400
        dest = BASE_DIR / "uploads"
        dest.mkdir(exist_ok=True)
        target = dest / safe
        try:
            f.save(str(target))
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:160]}), 500
        # return a path relative to the app folder (what run_brand expects)
        rel = str(target.relative_to(BASE_DIR))
        return jsonify({"ok": True, "path": rel, "bytes": target.stat().st_size})

    # ---- Shopify export preview (no Claude) ---------------------------------
    @app.route("/brand/preview", methods=["POST"])
    def brand_preview():
        import shopify_import
        body = request.get_json(force=True) or {}
        path = (body.get("csv_path") or "").strip()
        if not path:
            return jsonify({"ok": False, "error": "csv_path required"}), 400
        if not Path(path).is_absolute():
            path = str(BASE_DIR / path)
        if not Path(path).exists():
            return jsonify({"ok": False, "error": f"not found: {path}"}), 404
        try:
            prods = shopify_import.load_shopify_products(path, include_statuses=None)
            catlang = shopify_import.detect_catalogue_language(prods)
            vendors = {}
            statuses = {}
            for p in prods:
                vendors[p["vendor"]] = vendors.get(p["vendor"], 0) + 1
                statuses[p["status"]] = statuses.get(p["status"], 0) + 1
            top_vendors = sorted(vendors.items(), key=lambda x: -x[1])[:12]
            return jsonify({
                "ok": True, "count": len(prods),
                "language": catlang,
                "statuses": statuses,
                "vendors": [{"name": v, "count": c} for v, c in top_vendors],
                "tone_options": brand_profile.tone_dropdown_options(catlang["code"]),
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500

    # ---- brand run (subprocess stream, mirrors /run/<mode>) -----------------
    @app.route("/brand/run/<path:name>")
    def brand_run(name):
        test_limit = request.args.get("limit", "0")
        try:
            test_limit = str(int(test_limit))
        except (ValueError, TypeError):
            test_limit = "0"

        def stream():
            with _run_lock:
                busy = _running["on"]
                if not busy:
                    _running["on"] = True
            if busy:
                yield "data: [busy] a run is already in progress\n\n"
                yield "event: end\ndata: end\n\n"
                return
            try:
                # args: brand <name> <csv(blank->profile)> <test_limit>
                args = [sysmod.executable, "-u", SCRIPT, "brand", name, "", test_limit]
                yield f"data: [start] {' '.join(a for a in args if a)}\n\n"
                p = spawn(args)
                _running["proc"] = p
                # drained on a worker thread so a slow browser can't jam the pipe
                # and freeze the run mid-print -- see routes/stream_pump.py
                for line in pump_lines(p):
                    clean = _ANSI.sub("", line.rstrip("\n"))
                    if clean.strip():
                        yield f"data: {clean}\n\n"
                p.wait()
                yield f"data: [done] finished (exit {p.returncode})\n\n"
                yield "event: end\ndata: end\n\n"
            finally:
                _running["proc"] = None
                _running["on"] = False
        return Response(stream(), mimetype="text/event-stream")

    # ---- the Brand panel HTML ----------------------------------------------
    @app.route("/brand/panel")
    def brand_panel():
        return Response(_panel_html(), mimetype="text/html")


# =============================================================================
# Brand panel HTML/JS  (mounts into #brandpanel; uses the page's existing CSS)
# =============================================================================

def _panel_html():
    """The Brand panel's markup and script, as ONE response (the page runs the
    inline <script> by copying its text, so it must stay inline in the reply).

    MOVED OUT OF A PYTHON STRING (28 Sep 2026, master audit A16; CLAUDE.md
    Rule 7): the markup is templates/brand_panel.html and the script is
    static/js/brand_panel.js. The move itself was byte-for-byte (verified); once
    the script was a real file the standing JS rules applied, so its native
    alert/confirm, three hard-coded colours and one unsafe inline handler were
    then fixed (test_brand_panel_moved.py). Read per request, like the other templates in
    development, so an edit shows on refresh.
    """
    import os as _os
    here = _os.path.dirname(_os.path.abspath(__file__))
    with open(_os.path.join(here, "templates", "brand_panel.html"), encoding="utf-8", newline="") as f:
        html = f.read()
    with open(_os.path.join(here, "static", "js", "brand_panel.js"), encoding="utf-8", newline="") as f:
        js = f.read()
    return html + "<script>" + js + "</script>\n"


# =============================================================================
# Provenance "i" button -- client snippet to drop into the review card renderer.
# =============================================================================
# brand_listing.py writes _provenance into each row's Attributes JSON. To show the
# "i" button on an attribute box, add this helper to dashboard.py's _HTML <script>
# and call iBtn(sku, fieldKey) when rendering each editable cell:
#
#   function iBtn(prov, key){
#     if(!prov || !prov[key]) return '';
#     const p = prov[key];
#     const verified = p.verified ? 'code-verified' : 'AI-reported';
#     const tip = (p.source||'') + (p.note? ' -- '+p.note : '') + ' ('+verified+')';
#     const cls = (String(p.source||'').startsWith('INFERRED') && !p.verified) ? 'iwarn':'iok';
#     return '<span class="ibtn '+cls+'" title="'+tip.replace(/"/g,'&quot;')+'">i</span>';
#   }
#
# CSS (add near the other styles):
#   .ibtn{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;
#         border-radius:50%;font-size:10px;font-weight:700;cursor:help;margin-left:6px;
#         border:1px solid var(--line)}
#   .ibtn.iok{color:#9cc1ff;border-color:#2f4a73}
#   .ibtn.iwarn{color:#e3b768;border-color:#5c4a16;background:var(--amberbg)}
#
# The provenance object for a row is JSON.parse(row.attrs)._provenance.
