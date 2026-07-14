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
        try:
            json.dump(cfg, open(CONFIG_PATH, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
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
                p = subprocess.Popen(args, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
                _running["proc"] = p
                for line in iter(p.stdout.readline, ""):
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
        return Response(_PANEL_HTML, mimetype="text/html")


# =============================================================================
# Brand panel HTML/JS  (mounts into #brandpanel; uses the page's existing CSS)
# =============================================================================

_PANEL_HTML = r"""
<div style="max-width:880px">
  <div style="display:flex;gap:8px;margin-bottom:14px">
    <span class="pill active" id="tab-brand" onclick="brandTab('brand')">Brand Settings</span>
    <span class="pill" id="tab-conn" onclick="brandTab('conn')">Connections</span>
  </div>

  <!-- BRAND SETTINGS -->
  <div id="pane-brand">
    <div id="brand_cards" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px"></div>
    <table class="kv">
      <tr><td class="k">Brand</td><td class="v">
        <select class="ed" id="b_select" onchange="brandLoad(this.value)"></select>
        <span class="cc">or type a new name below to create one</span>
      </td></tr>
      <tr><td class="k">Brand name</td><td class="v"><input class="ed" id="b_name"></td></tr>
      <tr><td class="k">Vendor mode</td><td class="v">
        <select class="ed" id="b_vendor_mode">
          <option value="single_brand">single_brand (one brand owns everything)</option>
          <option value="reseller">reseller (multi-vendor store)</option>
        </select></td></tr>
      <tr><td class="k">Voice mode</td><td class="v">
        <select class="ed" id="b_voice_mode">
          <option value="regenerate">regenerate (fresh optimised copy)</option>
          <option value="preserve">preserve (keep brand phrasing, restructure)</option>
        </select></td></tr>
      <tr><td class="k">Tone / output language</td><td class="v">
        <select class="ed" id="b_tone"></select>
        <span class="cc">English is default; brand's source language appears if non-English</span>
      </td></tr>
      <tr><td class="k">Marketplace</td><td class="v">
        <select class="ed" id="b_marketplace"><option>UK</option><option>US</option></select></td></tr>
      <tr><td class="k">Pricing</td><td class="v">
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <span class="cc">source currency</span>
          <input class="ed" id="b_srccur" placeholder="SEK" style="width:70px;display:inline-block">
          <span class="cc">× FX rate</span>
          <input class="ed" id="b_fx" placeholder="0.075" style="width:80px;display:inline-block">
          <span class="cc">× markup</span>
          <input class="ed" id="b_markup" placeholder="1.0" style="width:70px;display:inline-block">
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:6px">
          <label class="cc"><input type="checkbox" id="b_round99"> round to .99</label>
          <span class="cc" style="margin-left:10px">or fixed price</span>
          <input class="ed" id="b_fixed" placeholder="(overrides)" style="width:90px;display:inline-block">
        </div>
        <span class="cc">Shopify price × FX × markup = Amazon price. e.g. 1490 SEK × 0.075 = £111.75</span>
      </td></tr>
      <tr><td class="k">Country of origin</td><td class="v">
        <input class="ed" id="b_coo" placeholder="brand-stated, else leave blank"></td></tr>
      <tr><td class="k">Lead title with brand</td><td class="v">
        <select class="ed" id="b_lead"><option value="true">Yes</option><option value="false">No</option></select></td></tr>
      <tr><td class="k">SKU prefix</td><td class="v">
        <select class="ed" id="b_prefix_on" style="width:auto;display:inline-block">
          <option value="false">off (use brand SKU as-is)</option>
          <option value="true">on</option></select>
        <input class="ed" id="b_prefix" placeholder="e.g. LEECH" style="display:inline-block;width:auto;margin-left:8px">
        <span class="cc">on -> LEECH-P2601B</span>
      </td></tr>
      <tr><td class="k">Shopify export path</td><td class="v">
        <input class="ed" id="b_csv" placeholder="click Browse to upload, or type a path">
        <div style="margin-top:6px;display:flex;gap:8px;align-items:center">
          <input type="file" id="b_csvfile" accept=".csv,.tsv,.txt" style="display:none" onchange="brandUpload(this)">
          <button class="ghost" onclick="document.getElementById('b_csvfile').click()">Browse…</button>
          <button class="ghost" onclick="brandPreview()">Preview export</button>
          <span id="b_uploadstatus" class="cc"></span>
        </div>
        <div id="b_preview" class="cc" style="margin-top:6px"></div>
        <div id="brandhow_import"></div>
      </td></tr>
      <tr><td class="k">Output Google Sheet</td><td class="v">
        <input class="ed" id="b_outsheet" placeholder="Sheet ID (blank = use default sheet)">
        <span class="cc">e.g. a US brand writes to your US sheet, not the UK one</span>
      </td></tr>
      <tr><td class="k">Output tab name</td><td class="v">
        <input class="ed" id="b_outtab" placeholder="e.g. Listings v7.0 USA (blank = default tab)"></td></tr>
      <tr><td class="k">Main image reference (AI)</td><td class="v">
        <div style="display:flex;gap:6px;align-items:center">
          <input class="ed" id="b_mainimgref" style="flex:1" placeholder="https://... or upload from your computer \u2192">
          <label class="uploadbtn" title="Upload from your computer">
            <i class="ti ti-upload"></i> Upload
            <input type="file" accept="image/*" style="display:none" onchange="uploadBrandRef(this)">
          </label>
        </div>
        <div id="b_mainimgref_prev"></div>
        <span class="cc">used when generating main images for this brand's products</span>
      </td></tr>
      <tr><td class="k">Claims-docs Drive folder</td><td class="v">
        <input class="ed" id="b_drive" placeholder="https://drive.google.com/drive/folders/...">
        <span class="cc">share this folder with the service-account email</span>
      </td></tr>
      <tr><td class="k">Competitor ASINs (optional)</td><td class="v">
        <input class="ed" id="b_comp" placeholder="B0..., B0... (comma separated, optional)"></td></tr>
      <tr><td class="k">Forbidden brands (IP)</td><td class="v">
        <input class="ed" id="b_forbidden" placeholder="rival brand names, comma separated"></td></tr>
      <tr><td class="k">Voice notes</td><td class="v">
        <textarea class="ed" id="b_voicenotes" rows="3" placeholder="positioning, tone, words to favour/avoid"></textarea></td></tr>
    </table>
    <div style="display:flex;gap:8px;margin-top:12px;align-items:center;flex-wrap:wrap">
      <button class="primary" onclick="brandSave()">Save brand</button>
      <span style="margin-left:12px;color:var(--muted)">Test mode — generate only</span>
      <input class="ed" id="b_testlimit" value="2" style="width:60px;display:inline-block">
      <span style="color:var(--muted)">listing(s)</span>
      <button class="ok" onclick="brandRun(true)">Test run (limited)</button>
      <button class="danger" onclick="brandRun(false)" title="Generates ALL products — uses full credits">
        Generate ALL listings</button>
      <button class="danger" id="b_stopbtn" onclick="brandStop()" style="display:none">Stop</button>
    </div>
    <div id="brandhow_run"></div>
    <pre id="brandlog" style="display:none;margin-top:12px;padding:10px;background:#0b0d11;
      border:1px solid var(--line);border-radius:8px;max-height:260px;overflow:auto;
      font:12px/1.5 ui-monospace,Consolas,monospace;color:#cbd3e1;white-space:pre-wrap"></pre>
  </div>

  <!-- CONNECTIONS -->
  <div id="pane-conn" style="display:none">
    <table class="kv">
      <tr><td class="k">Auth method</td><td class="v">
        <select class="ed" id="c_auth">
          <option value="service_account">service account (default, headless)</option>
          <option value="oauth">oauth (client accounts - coming soon)</option>
        </select></td></tr>
      <tr><td class="k">Service account JSON</td><td class="v">
        <input class="ed" id="c_sa" placeholder="service_account.json"></td></tr>
      <tr><td class="k">Default claims-docs folder</td><td class="v">
        <input class="ed" id="c_drive" placeholder="https://drive.google.com/drive/folders/..."></td></tr>
      <tr><td class="k">Label</td><td class="v"><input class="ed" id="c_label" placeholder="Owner (default)"></td></tr>
    </table>
    <div style="margin-top:8px" class="reqnote">
      <b>Setup:</b> enable the Drive API on your Google Cloud project and share the
      claims-docs folder with the service-account email. OAuth (for client-owned
      Drives) activates in the client-onboarding phase.
    </div>
    <button class="primary" onclick="connSave()" style="margin-top:12px">Save connection</button>
  </div>
</div>

<script>
// Self-contained "how it works" for the standalone brand panel (it can't reach
// the main page's helper). Respects the same admin flag from /ai/settings.
var BRAND_LOGIC_VISIBLE = true;
function _bEsc(s){ return String(s==null?"":s).replace(/[&<>"']/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; }); }
function brandHow(which){
  if(!BRAND_LOGIC_VISIBLE) return "";
  var reg = {
    brand_import: { title:"How importing a brand's Shopify export works", steps:[
      "<b>Parses your Shopify CSV/TSV</b> (<code>load_shopify_products</code>) — detecting the delimiter and reading each product: title, type, primary variant SKU, price (and price range for variants), cleaned EAN/UPC barcode, variant option axes, and all images (parent + continuation rows, de-duped).",
      "<b>Pulls description metafields</b> and strips their HTML to clean text.",
      "<b>Detects the catalogue language</b> so non-English source copy is handled (and never output verbatim).",
      "<b>Preview</b> just shows the product count and a sample — nothing is generated or written until you run." ]},
    brand_run: { title:"How generating a brand's listings works (vs dropshipping)", steps:[
      "<b>This is YOUR brand's own product</b> — so identity is preserved, not invented. <code>extract_identity</code> takes the MPN/model, GTIN/barcode and SKU <i>verbatim</i> from the export, each tagged with a code-verified <i>provenance</i> source.",
      "<b>Writes the listing with the brand's voice.</b> <code>build_brand_prompt</code> keeps the brand's strong phrasing and positioning but restructures it for Amazon and outputs English.",
      "<b>Claims are gated to evidence.</b> Any performance/health claim must be backed by your claim documents (pulled from the shared Drive folder); unsupported claims are dropped.",
      "<b>Brand pricing</b> (<code>compute_brand_price</code>): source price \u00d7 FX rate \u00d7 your markup, optionally rounded to .99 — or a fixed price if you set one.",
      "<b>Writes to your chosen Sheet/tab</b> (e.g. a US brand to your US sheet) with a status for review. Test run does a limited few; Generate ALL does the whole catalogue and uses full credits." ]}
  };
  var b = reg[which]; if(!b) return "";
  return '<details class="howbox"><summary><span class="chev">\u25b6</span> How this works \u2014 the actual steps behind the button</summary>'
    + '<div class="howbody"><div style="font-weight:600;color:var(--text);margin-bottom:2px">'+_bEsc(b.title)+'</div><ol>'
    + b.steps.map(function(s){return "<li>"+s+"</li>";}).join("")
    + '</ol><div style="margin-top:6px;opacity:.8">Nothing is sent to Amazon here \u2014 a brand run only fills your Google Sheet for review.</div></div></details>';
}
function brandRefreshHow(){
  var map={ "brandhow_import":"brand_import", "brandhow_run":"brand_run" };
  Object.keys(map).forEach(function(id){
    var el=document.getElementById(id);
    if(el) el.innerHTML = brandHow(map[id]);
  });
}
async function brandLoadLogicFlag(){
  try{ var s=await (await fetch("/ai/settings")).json();
    if(s&&s.admin){ BRAND_LOGIC_VISIBLE = !!s.admin.show_logic && !s.admin.preview_as_user; }
  }catch(e){}
  brandRefreshHow();
}
function brandTab(t){
  document.getElementById('pane-brand').style.display = t==='brand'?'block':'none';
  document.getElementById('pane-conn').style.display  = t==='conn'?'block':'none';
  document.getElementById('tab-brand').classList.toggle('active', t==='brand');
  document.getElementById('tab-conn').classList.toggle('active', t==='conn');
  if(t==='conn') connLoad();
}
function setTone(opts, current){
  const sel=document.getElementById('b_tone'); sel.innerHTML='';
  (opts||[{code:'en',label:'English',default:true}]).forEach(o=>{
    const op=document.createElement('option'); op.value=o.code; op.textContent=o.label; sel.appendChild(op);
  });
  sel.value = current || 'en';
}
async function brandRefresh(){
  const r=await (await fetch('/brand/list')).json();
  const sel=document.getElementById('b_select'); sel.innerHTML='<option value="">(new brand)</option>';
  const cards=document.getElementById('brand_cards'); if(cards) cards.innerHTML='';
  (r.brands||[]).forEach(b=>{
    const o=document.createElement('option');o.value=b.brand_name;o.textContent=b.brand_name;sel.appendChild(o);
    if(cards){
      const c=document.createElement('div');
      c.style.cssText='border:1px solid var(--line);border-radius:9px;padding:8px 11px;background:var(--panel2);cursor:pointer;min-width:150px;position:relative';
      c.innerHTML='<div style="font-weight:600;padding-right:18px">'+b.brand_name+'</div><div class="cc">'+(b.vendor_mode||'')+' \u00b7 '+(b.marketplace||'')+' \u00b7 '+(b.source_language||'en')+'</div>'
        +'<span title="Remove this trademark from this account" style="position:absolute;top:5px;right:7px;color:#e0696b;font-weight:700;cursor:pointer" onclick="event.stopPropagation();brandRemoveFromAccount('+JSON.stringify(b.brand_name)+')">\u00d7</span>';
      c.onclick=()=>{document.getElementById('b_select').value=b.brand_name; brandLoad(b.brand_name);};
      cards.appendChild(c);
    }
  });
  if(cards && !(r.brands||[]).length){ cards.innerHTML='<div class="cc">No brands saved yet. Fill the form below and click Save brand.</div>'; }
  // WORKSPACE LOCK: if opened inside a workspace, hide the multi-brand chooser
  // and auto-load only that brand.
  var locked = window.WS_BRAND || "";
  var chooserRow = document.getElementById('b_select') ? document.getElementById('b_select').closest('tr') : null;
  if(locked){
    if(cards) cards.style.display='none';
    if(chooserRow) chooserRow.style.display='none';
    var has=(r.brands||[]).some(function(b){return b.brand_name===locked;});
    if(has){ document.getElementById('b_select').value=locked; brandLoad(locked); }
    else { var nm=document.getElementById('b_name'); if(nm) nm.value=locked; }
  } else {
    if(cards) cards.style.display='flex';
    if(chooserRow) chooserRow.style.display='';
  }
}
async function brandLoad(name){
  if(!name){return;}
  const p=await (await fetch('/brand/get/'+encodeURIComponent(name))).json();
  b_name.value=p.brand_name||''; b_vendor_mode.value=p.vendor_mode||'single_brand';
  b_voice_mode.value=p.voice_mode||'regenerate'; b_marketplace.value=p.marketplace||'UK';
  b_coo.value=p.country_of_origin||''; b_lead.value=String(p.lead_with_brand!==false);
  b_prefix_on.value=String(!!p.sku_prefix_enabled); b_prefix.value=p.sku_prefix||'';
  b_csv.value=p.shopify_export_path||''; b_drive.value=p.claims_docs_drive_url||'';
  b_comp.value=(p.competitor_asins||[]).join(', '); b_forbidden.value=(p.forbidden_brands||[]).join(', ');
  b_voicenotes.value=p.voice_notes||'';
  document.getElementById('b_srccur').value=p.source_currency||'';
  document.getElementById('b_fx').value=p.fx_rate||'';
  document.getElementById('b_markup').value=p.price_markup||'';
  document.getElementById('b_round99').checked=!!p.price_round_99;
  document.getElementById('b_fixed').value=p.price_fixed||'';
  document.getElementById('b_outsheet').value=p.output_spreadsheet_id||'';
  document.getElementById('b_outtab').value=p.output_tab||'';
  document.getElementById('b_mainimgref').value=p.main_image_reference||'';
  setTone(p._tone_options, p.tone_language);
}
async function brandSave(){
  const body={brand_name:b_name.value, vendor_mode:b_vendor_mode.value, voice_mode:b_voice_mode.value,
    tone_language:b_tone.value, marketplace:b_marketplace.value, country_of_origin:b_coo.value,
    lead_with_brand:b_lead.value==='true', sku_prefix_enabled:b_prefix_on.value==='true',
    sku_prefix:b_prefix.value, shopify_export_path:b_csv.value, claims_docs_drive_url:b_drive.value,
    competitor_asins:b_comp.value, forbidden_brands:b_forbidden.value, voice_notes:b_voicenotes.value,
    source_currency:document.getElementById('b_srccur').value,
    fx_rate:document.getElementById('b_fx').value,
    price_markup:document.getElementById('b_markup').value,
    price_round_99:document.getElementById('b_round99').checked,
    price_fixed:document.getElementById('b_fixed').value,
    output_spreadsheet_id:document.getElementById('b_outsheet').value,
    output_tab:document.getElementById('b_outtab').value,
    main_image_reference:document.getElementById('b_mainimgref').value};
  const r=await (await fetch('/brand/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)})).json();
  alert(r.ok?'Brand saved.':'Error: '+(r.error||'?')); brandRefresh();
}
async function brandUpload(input){
  const f = input.files && input.files[0]; if(!f) return;
  const st=document.getElementById('b_uploadstatus'); st.textContent='Uploading '+f.name+'…';
  const fd=new FormData(); fd.append('file', f);
  try{
    const r=await (await fetch('/brand/upload',{method:'POST',body:fd})).json();
    if(!r.ok){ st.textContent='Upload failed: '+(r.error||'?'); return; }
    document.getElementById('b_csv').value = r.path;
    st.textContent='Uploaded ('+(r.bytes/1024|0)+' KB) → '+r.path;
    brandPreview();   // auto-preview so they see product count + language immediately
  }catch(e){ st.textContent='Upload error: '+e; }
}
async function brandPreview(){
  const out=document.getElementById('b_preview'); out.textContent='Parsing...';
  const r=await (await fetch('/brand/preview',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({csv_path:b_csv.value})})).json();
  if(!r.ok){out.textContent='Error: '+r.error;return;}
  setTone(r.tone_options, b_tone.value);
  out.innerHTML = `<b>${r.count}</b> products | source language: <b>${r.language.name}</b>`
    + ` | statuses: ${JSON.stringify(r.statuses)}`
    + `<br>top vendors: ` + r.vendors.map(v=>`${v.name} (${v.count})`).join(', ');
}
function brandRun(testMode){
  if(!b_name.value){alert('Save the brand first.');return;}
  let limit=0;
  if(testMode){ limit=parseInt((document.getElementById('b_testlimit')||{}).value||'2',10)||2; }
  const log=document.getElementById('brandlog'); log.style.display='block';
  log.textContent=testMode?('TEST RUN \u2014 first '+limit+' listing(s)\n'):'GENERATING ALL listings\n';
  const stop=document.getElementById('b_stopbtn'); if(stop) stop.style.display='inline-block';
  const es=new EventSource('/brand/run/'+encodeURIComponent(b_name.value)+'?limit='+limit);
  window._brandES = es;
  es.onmessage=e=>{log.textContent+=e.data+'\n'; log.scrollTop=log.scrollHeight;};
  es.addEventListener('end',()=>{es.close(); if(stop) stop.style.display='none';});
}
async function brandStop(){
  try{ await fetch('/stop',{method:'POST'}); }catch(e){}
  if(window._brandES){ window._brandES.close(); }
  const log=document.getElementById('brandlog'); if(log) log.textContent+='\n[stopped by user]\n';
  const stop=document.getElementById('b_stopbtn'); if(stop) stop.style.display='none';
}
async function connLoad(){
  const c=await (await fetch('/brand/connection')).json();
  c_auth.value=c.auth_method||'service_account'; c_sa.value=c.service_account_json||'service_account.json';
  c_drive.value=c.claims_docs_drive_url||''; c_label.value=c.label||'Owner (default)';
}
async function connSave(){
  const body={auth_method:c_auth.value, service_account_json:c_sa.value,
    claims_docs_drive_url:c_drive.value, label:c_label.value};
  const r=await (await fetch('/brand/connection',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)})).json();
  alert(r.ok?'Connection saved.':'Error: '+(r.error||'?'));
}
function brandInit(){ brandRefresh(); setTone(null,'en'); brandLoadLogicFlag(); }
window.brandInit = brandInit;
window.brandRefresh = brandRefresh;
async function brandRemoveFromAccount(name){
  if(!confirm('Remove "'+name+'" from this account?\n\nThis unassigns the trademark from this workspace. (The brand profile itself is kept and can be re-added later.)')) return;
  try{
    const r=await (await fetch('/accounts/remove_brand',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand:name})})).json();
    if(!r.ok){ alert('Could not remove: '+(r.error||'?')); return; }
    if(window.ACCOUNTS && window.CUR_ACCOUNT){ /* refresh local copy */ }
    brandRefresh();
  }catch(e){ alert('Error: '+e); }
}
window.brandRemoveFromAccount = brandRemoveFromAccount;
function _bfileToDataURL(file){return new Promise(function(res,rej){var fr=new FileReader();fr.onload=function(){res(fr.result);};fr.onerror=rej;fr.readAsDataURL(file);});}
async function uploadBrandRef(input){
  var file=input.files&&input.files[0]; if(!file) return;
  var brand=(document.getElementById('b_name')||{}).value||(window.WS_BRAND||'brand');
  var prev=document.getElementById('b_mainimgref_prev');
  if(prev) prev.innerHTML='<span class="cc">Uploading…</span>';
  try{
    var dataUrl=await _bfileToDataURL(file);
    var res=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:'_brand_'+brand,data:dataUrl,name:file.name,kind:'brandref'})});
    var j=await res.json();
    if(!j.ok){ if(prev) prev.innerHTML='<span class="cc" style="color:#e0696b">Upload failed: '+(j.error||'')+'</span>'; return; }
    document.getElementById('b_mainimgref').value=j.url;
    if(prev) prev.innerHTML='<img src="'+j.url+'" style="max-width:120px;border-radius:8px;border:1px solid var(--line);margin-top:6px"><div class="cc">\u2713 uploaded \u2014 remember to Save brand</div>';
  }catch(e){ if(prev) prev.innerHTML='<span class="cc" style="color:#e0696b">Error: '+e+'</span>'; }
}
window.uploadBrandRef = uploadBrandRef;
</script>
"""


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
