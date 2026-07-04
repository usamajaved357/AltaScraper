#!/usr/bin/env python3
"""
Local review + run dashboard for the Amazon listing pipeline.

WHAT IT DOES
  - "Generate" / "Retry" / "Export" buttons run amazon_listing_generator.py as a
    background process; its progress streams live into the page (no cmd window).
  - Reads your Google Sheet ("Listings v7.0 UK") live and shows each listing as a
    review card: status, IP risk, compliance risk, the Notes findings, title,
    bullets, price/profit, and a link to the source listing.
  - Approve / Hold buttons write Status back to the sheet, so your existing
    export step still works unchanged. NOTHING is published to Amazon from here.

RUN
  pip install flask          (gspread/google-auth are already installed by the main script)
  py -3.11 dashboard.py
  then open  http://127.0.0.1:5000  in your browser.

It reuses config.json (google_spreadsheet_id, google_service_account_json,
brand_name) and runs in the SAME folder as amazon_listing_generator.py.
"""

import json
import re
import sys
import os
import subprocess
import threading
import base64
try:
    import image_gen
except Exception:
    image_gen = None

from flask import Flask, Response, request, jsonify, session, redirect, url_for
import gspread
from google.oauth2.service_account import Credentials

# --- must match amazon_listing_generator.py -----------------------------------
CONFIG_PATH       = os.environ.get("CONFIG_PATH", "config.json")
SCRIPT            = "amazon_listing_generator.py"
OUTPUT_TAB        = "Listings v7.0 UK"      # OUTPUT_TAB in the main script
STATUS_HEADER     = "Status"
SKU_HEADER        = "SKU"
def _pick_port(preferred=5000, tries=20):
    """Return a bindable port. On macOS, AirPlay Receiver occupies 5000 by
    default, which would make app.run() fail with 'Address already in use'
    and/or send the browser to AirPlay instead of the dashboard. Try the
    preferred port first, then walk upward to the next free one so a fresh
    Mac works without the user having to disable any system service."""
    import socket as _sock
    for _p in range(preferred, preferred + tries):
        _s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
        _s.setsockopt(_sock.SOL_SOCKET, _sock.SO_REUSEADDR, 1)
        try:
            _s.bind(("127.0.0.1", _p))
            _s.close()
            return _p
        except OSError:
            _s.close()
            continue
    return preferred  # all busy: let app.run surface the real error

# On Render (and similar PaaS), the platform sets $PORT and expects the app to
# bind 0.0.0.0. Locally, no $PORT is set, so we keep the old AirPlay-avoiding
# auto-port-pick behaviour bound to 127.0.0.1 unchanged.
IS_HOSTED         = bool(os.environ.get("PORT"))
HOST              = "0.0.0.0" if IS_HOSTED else "127.0.0.1"
PORT              = int(os.environ["PORT"]) if IS_HOSTED else _pick_port(5000)

# --- config + Google auth (same service account the script uses) --------------
SCOPES   = ["https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"]
_ANSI    = re.compile(r"\x1b\[[0-9;]*m")
_VALID_SET_STATUS = {"APPROVED", "NEEDS_REVIEW", "IP_HOLD", "COMPLIANCE_HOLD"}

app       = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET_KEY") or os.urandom(32)

# --- shared-password login gate (hosted deployments only) --------------------
# APP_PASSWORD is only set on a real deployment (Render etc.); locally it's
# unset so the gate no-ops and dev workflow is unchanged.
_APP_PASSWORD = os.environ.get("APP_PASSWORD")
_LOGIN_HTML = """<!doctype html><html><head><title>Sign in</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#0f1115;
color:#e6e6e6;display:flex;height:100vh;align-items:center;justify-content:center;margin:0}
form{background:#1a1d24;padding:32px 36px;border-radius:10px;box-shadow:0 4px 24px rgba(0,0,0,.4);
width:280px}h1{font-size:17px;margin:0 0 18px}input{width:100%;box-sizing:border-box;padding:10px;
border-radius:6px;border:1px solid #333;background:#0f1115;color:#fff;margin-bottom:12px}
button{width:100%;padding:10px;border:0;border-radius:6px;background:#4c8bf5;color:#fff;
font-weight:600;cursor:pointer}.err{color:#ff6b6b;font-size:13px;margin-bottom:10px}</style>
</head><body><form method="post">
<h1>Listing Dashboard</h1>{err}
<input type="password" name="password" placeholder="Password" autofocus>
<button type="submit">Sign in</button>
</form></body></html>"""


@app.route("/healthz")
def _healthz():
    return "ok", 200


@app.route("/login", methods=["GET", "POST"])
def _login():
    if not _APP_PASSWORD:
        return "Login is not configured.", 404
    err = ""
    if request.method == "POST":
        if request.form.get("password") == _APP_PASSWORD:
            session["authed"] = True
            return redirect(url_for("index"))
        err = '<div class="err">Wrong password.</div>'
    return Response(_LOGIN_HTML.replace("{err}", err), mimetype="text/html")


@app.route("/logout")
def _logout():
    session.clear()
    return redirect(url_for("_login"))


@app.before_request
def _require_login():
    if not _APP_PASSWORD:
        return  # no password configured (local dev) -> gate disabled
    if request.endpoint in ("_login", "_healthz", "static"):
        return
    if not session.get("authed"):
        return redirect(url_for("_login"))


@app.errorhandler(500)
@app.errorhandler(Exception)
def _json_errors(e):
    """Ensure API routes (anything under our JSON endpoints) return JSON on error,
    never Flask's HTML error page — that HTML is what causes 'Unexpected token <,
    <!doctype ... is not valid JSON' in the browser."""
    import traceback as _tb
    code = getattr(e, "code", 500) or 500
    try:
        path = request.path or ""
    except Exception:
        path = ""
    # for our JSON API routes, always return JSON
    if any(path.startswith(p) for p in ("/genimage", "/aplus", "/optimize", "/recipes",
                                         "/live", "/media", "/accounts", "/ai", "/brand",
                                         "/cogs", "/rows", "/run")):
        msg = str(e)
        if code == 500:
            # include a short traceback tail to make debugging possible
            tail = _tb.format_exc().strip().splitlines()[-1:] or [""]
            msg = f"server error: {msg or tail[0]}"
        return jsonify({"ok": False, "error": msg}), (code if isinstance(code, int) else 500)
    # otherwise re-raise default behaviour
    if isinstance(code, int) and code != 500:
        return e
    return ("Internal Server Error", 500)

# --- brand-listing feature (added) ------------------------------------------
import dashboard_brand_patch
_run_lock = threading.Lock()
_running  = {"on": False, "proc": None, "started": 0.0}
_RUN_MAX_SECONDS = 600   # a Preview/Submit should never take >10 min; after that the
                          # lock is presumed stuck (abandoned stream) and is reclaimable.

def _acquire_run_lock():
    """Try to mark a run as started. Returns True if WE acquired it, False if a
    genuine live run is already going. Self-healing: if the flag is on but the
    previous run's subprocess has already exited, or the run is older than
    _RUN_MAX_SECONDS, the lock is considered stale (an abandoned SSE stream never
    ran its release `finally`) and is reclaimed. This fixes the 'Another run is
    already in progress' wedge that otherwise needs an app restart."""
    import time as _t
    with _run_lock:
        on = _running.get("on")
        if on:
            proc = _running.get("proc")
            started = _running.get("started") or 0.0
            proc_dead = (proc is None) or (proc.poll() is not None)
            too_old = (_t.time() - started) > _RUN_MAX_SECONDS
            if not (proc_dead or too_old):
                return False          # a real run is genuinely in progress
            # else: stale lock -> fall through and reclaim it
        _running["on"] = True
        _running["started"] = _t.time()
        return True
_state    = {"cfg": None, "gc": None, "schemas": {}, "vv": None}


class ConfigError(Exception):
    pass

def _cfg() -> dict:
    if _state["cfg"] is None:
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                _state["cfg"] = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(
                f"config.json has a JSON syntax error at line {e.lineno}, column {e.colno}: "
                f"{e.msg}. Common causes: a missing or extra comma, or an unclosed quote. "
                f"Paste your config into jsonlint.com to find it."
            )
        except FileNotFoundError:
            raise ConfigError(f"config.json not found at {CONFIG_PATH}")
    return _state["cfg"]


def _client():
    if _state["gc"] is None:
        c = _cfg()
        creds = Credentials.from_service_account_file(c["google_service_account_json"], scopes=SCOPES)
        _state["gc"] = gspread.authorize(creds)
    return _state["gc"]


def _ws():
    # Read the ACTIVE account's own sheet/tab. Resolve the tab by gid first (the
    # exact tab the generator writes to), then by name. If it doesn't exist yet,
    # auto-create it so accounts never silently fall back to another's listings.
    sid = _state.get("active_sheet_id") or _cfg()["google_spreadsheet_id"]
    tab = _state.get("active_tab") or OUTPUT_TAB
    gid = str(_state.get("active_tab_gid") or "").strip()
    try:
        book = _client().open_by_key(sid)
        if gid.isdigit():
            wbg = book.get_worksheet_by_id(int(gid))
            if wbg is not None:
                return wbg
        return book.worksheet(tab)
    except Exception:
        pass
    # tab (or sheet) not found -> try to CREATE the tab in the target sheet
    try:
        book = _client().open_by_key(sid)
        # copy header row from the default tab if we can, else a minimal header
        header = None
        try:
            dflt = _client().open_by_key(_cfg()["google_spreadsheet_id"]).worksheet(OUTPUT_TAB)
            header = dflt.row_values(1)
        except Exception:
            header = None
        ws = book.add_worksheet(title=tab, rows=200, cols=max(26, len(header or []) or 26))
        if header:
            ws.update("A1", [header])
        return ws
    except Exception:
        # last resort: default sheet/tab (keeps app alive; only hit if creation fails)
        return _client().open_by_key(_cfg()["google_spreadsheet_id"]).worksheet(OUTPUT_TAB)


def _active_account():
    """The account (workspace) currently in focus, or None."""
    try:
        import accounts as _acc
        aid = _state.get("active_account_id")
        if aid:
            a = _acc.get_account(_cfg(), aid, CONFIG_PATH)
            if a:
                return a
        # fall back to first account
        al = _acc.load_accounts(_cfg(), CONFIG_PATH)
        return al[0] if al else None
    except Exception:
        return None


def _sp_creds(marketplace: str = "UK") -> dict:
    # ACCOUNT-AWARE: if a workspace (account) is active, use ITS credentials --
    # never infer the account from marketplace. Marketplace only selects the
    # marketplace_id within that one account.
    acc = _active_account()
    if acc and acc.get("refresh_token") and not str(acc.get("refresh_token","")).startswith(("PUT_","ROTATE")):
        try:
            import accounts as _acc
            return _acc.account_creds(acc)
        except Exception:
            pass
    # legacy fallback (pre-accounts): marketplace-based selection
    c = _cfg()
    if str(marketplace).upper() == "US":
        us = c.get("us_spapi") or {}
        if us.get("lwa_client_secret") and us.get("refresh_token"):
            return {"lwa_app_id":        us.get("lwa_client_id") or us.get("lwa_app_id", ""),
                    "lwa_client_secret": us["lwa_client_secret"],
                    "refresh_token":     us["refresh_token"]}
    return {"lwa_app_id":        c["sp_api_client_id"],
            "lwa_client_secret": c["sp_api_client_secret"],
            "refresh_token":     c["sp_api_refresh_token"]}


_SUBFIELD_PLUMBING = {"language_tag", "marketplace_id", "audience"}


def _sf_enum_of(node):
    """Enum list for a schema node, unwrapping a localized array+items.value wrapper."""
    if not isinstance(node, dict):
        return None
    if isinstance(node.get("enum"), list):
        return [str(x) for x in node["enum"]]
    it = node.get("items")
    if isinstance(it, dict):
        props = it.get("properties")
        vp = props.get("value") if isinstance(props, dict) else None
        if isinstance(vp, dict) and isinstance(vp.get("enum"), list):
            return [str(x) for x in vp["enum"]]
    return None


def _sf_kind(node):
    t = node.get("type") if isinstance(node, dict) else None
    return "number" if t in ("number", "integer") else "text"


def _extract_subfields(prop) -> list:
    """Return the fillable sub-field controls Amazon expects under ONE attribute.
    [] -> plain single-value attribute. Otherwise a list of {path,label,kind,enum}.
    'path' is dot-joined keys UNDER the attribute, saved flat as '<field>.<path>'.

    Handles Amazon's habit of nesting attributes two levels deep -- e.g.
    `cable.length` in MASSAGER is itself a `{value, unit}` object, not a scalar.
    Without walking into the child's inner `items.properties` we'd expose
    `cable.length` as a single box and the AI would fill only the number OR
    only the unit, producing 'invalid value for cable' rejections. Amazon's
    schema often omits an explicit `type: "array"` marker on the inner wrapper,
    so we probe for `items.properties` and `properties` regardless of the
    marker. Same fix applies to `leg.length` (HARDWARE_TUBING) and any other
    attribute where the second level is itself a value+unit pair."""
    if not isinstance(prop, dict):
        return []
    node = prop
    if isinstance(node.get("items"), dict):
        # Unwrap array wrapper whether or not the "type": "array" marker is
        # present -- Amazon frequently omits it on inner wrappers.
        node = node["items"]
    sub = node.get("properties") if isinstance(node, dict) else None
    if not isinstance(sub, dict):
        return []
    keys = [k for k in sub.keys() if k not in _SUBFIELD_PLUMBING]
    if keys == ["value"]:
        return []
    out = []
    for k in keys:
        child = sub[k]
        cnode = child
        # Unwrap child's array/items wrapper regardless of "type" marker
        if isinstance(child, dict) and isinstance(child.get("items"), dict):
            cnode = child["items"]
        cprops = {}
        if isinstance(cnode, dict) and isinstance(cnode.get("properties"), dict):
            cprops = {ck: cv for ck, cv in cnode["properties"].items()
                      if ck not in _SUBFIELD_PLUMBING}
        if set(cprops.keys()) == {"value", "unit"}:
            out.append({"path": k + ".value", "label": (k + " value").replace("_", " "),
                        "kind": _sf_kind(cprops["value"]), "enum": _sf_enum_of(cprops["value"])})
            out.append({"path": k + ".unit", "label": (k + " unit").replace("_", " "),
                        "kind": "text", "enum": _sf_enum_of(cprops["unit"])})
        elif cprops:
            # Grandchildren present but not the plain value+unit shape: recurse
            # so multi-level nested objects (like some battery.capacity variants)
            # get exposed at every leaf. Prevents "invalid value" rejections
            # on nested composites the AI could otherwise only half-fill.
            grand = _extract_subfields(child)
            if grand:
                for g in grand:
                    out.append({"path": k + "." + g["path"], "label": (k + " " + g["label"]),
                                "kind": g.get("kind"), "enum": g.get("enum")})
            else:
                out.append({"path": k, "label": k.replace("_", " "),
                            "kind": _sf_kind(child), "enum": _sf_enum_of(child)})
        else:
            out.append({"path": k, "label": k.replace("_", " "),
                        "kind": _sf_kind(child), "enum": _sf_enum_of(child)})
    return out


def _load_schema(pt: str) -> dict:
    """Fetch+cache {'enums', 'required', 'attrs', 'subfields'} for a product type
    from Amazon getDefinitions, for the active marketplace. Empties on failure."""
    if not pt:
        return {"enums": {}, "required": [], "attrs": [], "subfields": {}, "titles": {}}
    # marketplace-aware: US brands must get US sub-field schemas, not UK
    _mkt = str(_state.get("active_marketplace", "") or "UK").upper()
    _ck = f"{pt}::{_mkt}"
    if _ck in _state["schemas"]:
        return _state["schemas"][_ck]
    info = {"enums": {}, "required": [], "attrs": [], "subfields": {}, "titles": {}}
    try:
        import urllib.request
        from sp_api.api import ProductTypeDefinitions
        from sp_api.base import Marketplaces
        _mkt_enum = Marketplaces.US if _mkt == "US" else Marketplaces.UK
        _locale = "en_US" if _mkt == "US" else "en_GB"
        ptd  = ProductTypeDefinitions(credentials=_sp_creds(_mkt), marketplace=_mkt_enum, timeout=30)
        resp = ptd.get_definitions_product_type(productType=pt, requirements="LISTING",
                                                requirementsEnforced="ENFORCED", locale=_locale)
        link = resp.payload.get("schema", {}).get("link", {}).get("resource", "")
        raw = {}
        if link:
            # Retry the download: from Pakistan to a US CDN this can stall, and a
            # single timeout would otherwise collapse the whole schema to empty.
            _last = None
            for _attempt in range(3):
                try:
                    with urllib.request.urlopen(link, timeout=60) as r:
                        raw = json.loads(r.read().decode("utf-8"))
                    break
                except Exception as _de:
                    _last = _de
                    if _attempt < 2:
                        import time as _t
                        _t.sleep(2)
                    else:
                        raise
        # ENFORCED mode omits enum defs for some required fields (battery,
        # light_source, ...). Fetch the UNENFORCED schema too and merge its
        # fuller property defs so we get Amazon's REAL allowed values for every
        # field -- the whole point is to only ever offer Amazon's own values.
        _full_props = {}
        raw2 = {}
        try:
            resp2 = ptd.get_definitions_product_type(productType=pt, requirements="LISTING",
                                                     locale=_locale)
            link2 = resp2.payload.get("schema", {}).get("link", {}).get("resource", "")
            if link2:
                with urllib.request.urlopen(link2, timeout=60) as r2:
                    raw2 = json.loads(r2.read().decode("utf-8"))
                _full_props = raw2.get("properties", {}) or {}
        except Exception:
            _full_props = {}
        if raw or _full_props:
            info["required"] = [str(x) for x in (raw.get("required", []) or [])]
            # merge: enforced props first, fill gaps + missing enums from full
            _merged = dict(raw.get("properties", {}) or {})
            for _k, _v in _full_props.items():
                if _k not in _merged or not _merged.get(_k):
                    _merged[_k] = _v
                elif isinstance(_merged.get(_k), dict) and isinstance(_v, dict) and "items" not in _merged[_k] and "items" in _v:
                    _merged[_k] = _v
            info["attrs"]    = sorted(_merged.keys())
            # PERMANENT FIX: also pull allowed values out of the schema's
            # conditional branches (allOf/anyOf/oneOf/if-then) so fields like
            # battery_installation_device_type get a REAL dropdown instead of
            # showing as free-text. Reuse the generator's merge for one source
            # of truth. Use the unenforced raw if available (it has the branches).
            try:
                from amazon_listing_generator import _merge_conditional_enums as _mce
                _branch_raw = raw2 if isinstance(raw2, dict) and raw2 else raw
                _merged = _mce(_merged, _branch_raw)
            except Exception:
                pass
            def _enum_of(prop):
                """Extract an allowed-value list from a property def, checking the
                usual Amazon nesting (items.properties.value.enum first)."""
                if not isinstance(prop, dict):
                    return []
                _it = prop.get("items", {}) if isinstance(prop.get("items"), dict) else {}
                _ipp = _it.get("properties", {}) if isinstance(_it, dict) else {}
                _vp = _ipp.get("value", {}) if isinstance(_ipp, dict) else {}
                return (_vp.get("enum") or _ipp.get("enum") or _it.get("enum") or prop.get("enum") or [])
            for field, prop in _merged.items():
                # Amazon's REAL display label for this field (matches Seller
                # Central's listing editor). Falls back to a prettified key.
                _ttl = prop.get("title") or ""
                if _ttl:
                    info["titles"][field] = str(_ttl)
                items   = prop.get("items", {})
                ip      = items.get("properties", {}) if isinstance(items, dict) else {}
                # Enum from the merged (usually ENFORCED) def. If empty, fall back
                # to the UNENFORCED def -- the ENFORCED view frequently ships
                # `items` WITHOUT the enum inside, which silently dropped real
                # dropdowns (e.g. battery_installation_device_type, special_feature).
                allowed = _enum_of(prop)
                if not allowed and field in _full_props:
                    allowed = _enum_of(_full_props[field])
                if allowed:
                    info["enums"][field] = [str(a) for a in allowed]
                # capture sub-field titles too (e.g. battery.cell_composition -> "Battery Cell Composition")
                for _sk, _sv in ip.items():
                    if isinstance(_sv, dict) and _sv.get("title"):
                        info["titles"][f"{field}.{_sk}"] = str(_sv.get("title"))
                # nested objects: merge sub-fields from BOTH the enforced and
                # unenforced defs. The enforced view often keeps the sub-field but
                # strips its enum, so for each sub-field take the enum from whichever
                # version has one (this is what left hazmat's "Aspect" dropdown empty).
                subs = _extract_subfields(prop)          # nested objects
                if field in _full_props:
                    subs_full = _extract_subfields(_full_props[field])
                    if subs_full:
                        if not subs or len(subs_full) > len(subs):
                            subs = subs_full
                        else:
                            _byp = {s["path"]: s for s in subs_full}
                            for _s in subs:
                                if not _s.get("enum"):
                                    _alt = _byp.get(_s["path"])
                                    if _alt and _alt.get("enum"):
                                        _s["enum"] = _alt["enum"]
                if subs:
                    info["subfields"][field] = subs
    except Exception as _e:
        # record why it failed so the UI can show a real reason instead of a
        # silent empty schema (which collapses nested fields to flat boxes).
        info["_error"] = str(_e)[:200]
    # CRITICAL: only cache a SUCCESSFUL load. Caching an empty result (after a
    # timeout/network blip) used to "stick" -- every later view showed flat boxes
    # with no nested structure or notes until restart. If we got no attributes,
    # DON'T cache; let the next call retry.
    if info.get("attrs"):
        _state["schemas"][_ck] = info
    return info


def _schema_subfields(pt: str) -> dict:
    return _load_schema(pt).get("subfields", {})


def _schema_enums(pt: str) -> dict:
    return _load_schema(pt)["enums"]


def _schema_required(pt: str) -> list:
    return _load_schema(pt)["required"]


def _schema_attrs(pt: str) -> list:
    return _load_schema(pt)["attrs"]


def _valid_values() -> dict:
    """The flat-file allowed-values file ({product_type: {attr: [values]}})."""
    if _state["vv"] is None:
        try:
            _state["vv"] = json.load(open("valid_values.json", encoding="utf-8"))
        except Exception:
            _state["vv"] = {}
    return _state["vv"]


_FALLBACK_VV_PT = "HOME"   # generic options for product types not in valid_values.json


def _options_for(pt: str) -> dict:
    """Dropdown options per attribute: human-readable valid_values (flat-file) first,
    falling back to HOME for unknown types, with schema enums filling any gaps."""
    vv   = _valid_values()
    base = pt if pt in vv else _FALLBACK_VV_PT
    opts = {k: list(v) for k, v in vv.get(base, {}).items() if isinstance(v, list) and v}
    for k, v in _schema_enums(pt).items():
        opts.setdefault(k, v)
    return opts


def _product_types() -> list:
    return sorted(k for k in _valid_values().keys() if k != "_meta")


def _card(r: dict) -> dict:
    g = lambda k: r.get(k, "")
    # Some rows use the Miles 12-column layout with different header names than
    # the standard 48-column format. Fall back to the Miles names so the drawer
    # editor shows the data instead of empty boxes.
    def gm(standard, *miles_alts):
        v = r.get(standard, "")
        if v:
            return v
        for alt in miles_alts:
            if r.get(alt, ""):
                return r.get(alt, "")
        return ""
    try:
        attrs = json.loads(str(g("Attributes JSON") or "{}"))
        if not isinstance(attrs, dict):
            attrs = {}
    except Exception:
        attrs = {}
    return {
        "sku":          gm("SKU", "Sku"),
        "status":       str(g("Status")).upper().strip(),
        "title":        gm("Title"),
        "item_highlights": gm("Item Highlights", "Highlights"),
        "product_type": g("Product Type"),
        "category":     g("Amazon Category"),
        "brand":        g("Brand"),
        "bullets":      [gm(f"Bullet {i}", f"Bullet Point {i}") for i in range(1, 6)],
        "ip_risk":      str(g("IP Risk")).upper().strip(),
        "comp_risk":    str(g("Compliance Risk")).upper().strip(),
        "notes":        gm("Notes", "Compliance Report"),
        "comp_notes":   gm("Compliance Notes", "Compliance Report"),
        "price":        g("Our Price (GBP)"),
        "profit":       g("Profit (GBP)"),
        "viable":       g("Viable?"),
        "source":       g("Source URL"),
        "asin":         gm("Competitor ASIN", "ASIN"),
        "barcode":      g("UPC"),
        "search_terms": gm("Search Terms / KW", "Backend Keywords"),
        "description":  gm("Description (HTML)", "Description"),
        "handling_days":g("Handling Days"),
        "model_number": g("Model Number"),
        "attributes":   attrs,
        "attrs":        json.dumps(attrs),
        "api_payload":  g("API Payload JSON"),   # exact body sent to Amazon (debug viewer)
        "_marketplace": _state.get("active_marketplace", "") or attrs.get("marketplace", ""),
        "row":          g("_row"),
    }


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


_URL_RE    = re.compile(r"https?://[^\s)>\]]+")
CHAT_MODEL = "claude-sonnet-4-6"


def _fetch_image_b64(url: str):
    """Fetch an image URL -> (media_type, base64_str). None on failure / non-image / >5MB."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ct   = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = r.read()
        if not ct.startswith("image/") or len(data) > 5_000_000:
            return None
        return ct, base64.b64encode(data).decode("ascii")
    except Exception:
        return None


import os
import base64 as _b64
from flask import send_from_directory

def _media_root():
    root = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "media")
    os.makedirs(root, exist_ok=True)
    return root

def _account_media_root(aid=None):
    """Per-account media folder so each workspace shows only its OWN images.
    Falls back to the shared root for the dropshipping (no-account) view."""
    if aid is None:
        aid = _state.get("active_account_id", "") or ""
    if not aid:
        return _media_root()        # dropshipping / no account -> shared root
    d = os.path.join(_media_root(), "_acct", _safe_sku(aid))
    os.makedirs(d, exist_ok=True)
    return d

def _safe_sku(sku):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(sku or "_misc"))[:120] or "_misc"


# ---- Google Drive image storage -------------------------------------------
# Each account can set a master Drive FOLDER (its URL). Generated images for that
# account are uploaded into per-product subfolders named "{SKU}_{ProductName}".
# IMPORTANT: the Google service account email must be granted access (Editor) to
# that Drive folder, exactly like sharing a Google Sheet with it.
_DRIVE_FOLDER_CACHE = {}   # {"<parent>::<name>": folder_id}

def _drive_folder_id_from_url(url):
    """Pull the Drive folder ID out of a folder URL or accept a raw ID."""
    s = str(url or "").strip()
    if not s:
        return ""
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    # raw id (no slashes/spaces)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):
        return s
    return ""

def _drive_service():
    """Build a Drive API client using the same service account as Sheets.

    If config has 'drive_impersonate_email' (a real Google account, with
    domain-wide delegation enabled for the service account), the client acts AS
    that user -- so uploads use the user's storage quota and the 'service accounts
    have no storage' 403 disappears, even for personal 'My Drive' folders."""
    try:
        from googleapiclient.discovery import build
    except Exception as e:
        raise RuntimeError(f"google-api-python-client not installed: {e}")
    c = _cfg()
    creds = Credentials.from_service_account_file(c["google_service_account_json"], scopes=SCOPES)
    _imp = (c.get("drive_impersonate_email", "") or "").strip()
    if _imp:
        try:
            creds = creds.with_subject(_imp)
        except Exception:
            pass  # delegation not set up -> fall back to normal service-account creds
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def _drive_get_or_create_subfolder(svc, parent_id, name):
    """Return the ID of subfolder `name` under `parent_id`, creating it if needed."""
    name = str(name or "").strip()[:200] or "_misc"
    ck = f"{parent_id}::{name}"
    if ck in _DRIVE_FOLDER_CACHE:
        return _DRIVE_FOLDER_CACHE[ck]
    # look for an existing folder with this name under the parent
    safe_name = name.replace("'", "\\'")
    q = (f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.folder' "
         f"and '{parent_id}' in parents and trashed = false")
    try:
        res = svc.files().list(q=q, fields="files(id,name)", pageSize=1,
                               supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        files = res.get("files", [])
        if files:
            _DRIVE_FOLDER_CACHE[ck] = files[0]["id"]
            return files[0]["id"]
    except Exception:
        pass
    # create it
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    created = svc.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    fid = created["id"]
    _DRIVE_FOLDER_CACHE[ck] = fid
    return fid

def _drive_direct_url(file_id):
    """Convert a Drive file id into a DIRECT image URL that external platforms
    (Amazon, eBay) can fetch. The reliable format is lh3.googleusercontent.com/d/<id>
    (the older drive.google.com/uc?export=view redirect is flaky). The file must
    also be shared 'anyone with link: reader' for this to load -- see _drive_make_public."""
    fid = str(file_id or "").strip()
    return f"https://lh3.googleusercontent.com/d/{fid}" if fid else ""


def _drive_make_public(svc, file_id):
    """Grant 'anyone with the link: reader' on a Drive file so external platforms
    can fetch the image. Idempotent -- ignores 'already exists' style errors."""
    try:
        svc.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()
    except Exception:
        pass  # already public, or permission already present -> fine


def _drive_upload_image(parent_folder_id, sku, product_name, local_path, filename=None, subpath=""):
    """Upload one local image into {parent}/{SKU_ProductName}/[subpath]/, make it
    publicly readable, and return a dict:
      {"id", "view_url" (human Drive page), "direct_url" (Amazon-usable lh3 link)}.
    `subpath` (e.g. "aplus/basic") nests the image inside the SKU folder so A+
    content is organized. Raises on a hard upload failure."""
    from googleapiclient.http import MediaFileUpload
    svc = _drive_service()
    sub_name = f"{_safe_sku(sku)}_{re.sub(r'[^A-Za-z0-9 ._-]', '', str(product_name or ''))[:80]}".strip("_ ")
    sub_id = _drive_get_or_create_subfolder(svc, parent_folder_id, sub_name)
    # nest into subpath segments (sanitized) if given
    if subpath:
        for seg in str(subpath).replace("\\", "/").split("/"):
            seg = re.sub(r"[^A-Za-z0-9_-]", "", seg).strip()
            if seg and seg not in (".", ".."):
                sub_id = _drive_get_or_create_subfolder(svc, sub_id, seg)
    fname = filename or os.path.basename(local_path)
    media = MediaFileUpload(local_path, resumable=False)
    meta = {"name": fname, "parents": [sub_id]}
    try:
        f = svc.files().create(body=meta, media_body=media, fields="id,webViewLink",
                               supportsAllDrives=True).execute()
    except Exception as _ce:
        _m = str(_ce)
        if "storageQuotaExceeded" in _m or "do not have storage" in _m or "storage quota" in _m.lower():
            # Service accounts have NO Drive storage of their own. Uploading into a
            # personal "My Drive" folder makes Google bill the file to the service
            # account -> 403. The fix is a Shared Drive (which has its own quota) or
            # an impersonated user. Raise a clear, actionable message.
            raise RuntimeError(
                "Google rejected the upload: a service account has no Drive storage of its own, "
                "and your folder is a personal 'My Drive' folder. Fix: create a SHARED DRIVE in "
                "Google Drive, add the service account as a Content Manager, put the account's "
                "folder inside that Shared Drive, and paste that folder's URL into the account. "
                "Shared Drives have their own storage so the service account can write there. "
                f"(raw: {_m[:160]})")
        raise
    fid = f.get("id", "")
    # make public so Amazon/eBay can actually load the image, then build a direct URL
    if fid:
        _drive_make_public(svc, fid)
    return {
        "id":         fid,
        "view_url":   f.get("webViewLink", ""),
        "direct_url": _drive_direct_url(fid),
    }


def _drive_map_path():
    """Path to the sidecar that maps a local media relpath -> its Drive file id +
    URLs, so we can (a) reuse the Amazon-usable link and (b) delete from Drive when
    the local copy is deleted. Kept next to config.json, per active account root."""
    try:
        return os.path.join(_account_media_root(), "_drive_map.json")
    except Exception:
        return os.path.join(_media_root(), "_drive_map.json")


def _drive_map_load():
    try:
        with open(_drive_map_path(), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _drive_map_save(m):
    try:
        with open(_drive_map_path(), "w", encoding="utf-8") as f:
            json.dump(m, f)
    except Exception:
        pass


def _drive_map_put(media_url, info):
    m = _drive_map_load()
    m[str(media_url)] = info
    _drive_map_save(m)


def _drive_map_get(media_url):
    return _drive_map_load().get(str(media_url))


def _drive_map_remove(media_url):
    m = _drive_map_load()
    info = m.pop(str(media_url), None)
    _drive_map_save(m)
    return info


def _drive_delete_file(file_id):
    """Delete a file from Drive by id. Best-effort; ignores 'not found'."""
    if not file_id:
        return False
    try:
        svc = _drive_service()
        svc.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        return True
    except Exception:
        return False


def _sniff_image_ext(raw: bytes, fallback: str = "jpg") -> str:
    """Return the TRUE image extension by reading the file's magic-number bytes,
    not the (often-wrong) mime label the AI model claims. Amazon rejects a file
    whose bytes don't match its extension (e.g. JPEG bytes named .png), so the
    saved filename must reflect the actual format. Covers the formats image models
    return: JPEG, PNG, WebP, GIF."""
    if not raw or len(raw) < 12:
        return fallback
    b = raw[:12]
    if b[:3] == b"\xff\xd8\xff":                      # JPEG
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":                  # PNG
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":        # WebP
        return "webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):                # GIF
        return "gif"
    return fallback


def _to_jpeg_bytes(raw: bytes, quality: int = 90) -> bytes:
    """Convert any image bytes (PNG/WebP/GIF/JPEG) to JPEG bytes. Amazon prefers
    JPEG for listing images and they're much smaller than PNG. Transparency is
    flattened onto a white background (Amazon main images need white anyway).
    Falls back to the original bytes if PIL/conversion fails."""
    try:
        from io import BytesIO
        from PIL import Image as _PImg
        im = _PImg.open(BytesIO(raw))
        # flatten alpha onto white so JPEG (no transparency) looks right
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = _PImg.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        out = BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return raw


def _sku_dir(sku):
    d = os.path.join(_account_media_root(), _safe_sku(sku))
    os.makedirs(d, exist_ok=True)
    return d


@app.route("/media/<path:relpath>")
def media_serve(relpath):
    """Serve a stored media file by its media/<sku>/<file> path."""
    return send_from_directory(_media_root(), relpath)


@app.route("/media/upload", methods=["POST"])
def media_upload():
    """Save an uploaded image (base64 data URL or raw b64) under media/<sku>/.
    Returns the served URL. Used for reference uploads and saving generations."""
    b = request.get_json(force=True) or {}
    sku  = b.get("sku", "_misc")
    data = b.get("data", "")            # data URL or bare base64
    name = b.get("name", "")           # optional original filename
    kind = b.get("kind", "ref")        # 'ref' | 'generated' | 'main'
    # optional subfolder to organize images inside the SKU folder, e.g.
    # "aplus/basic", "aplus/premium", "secondary". Sanitized to a safe set of
    # path segments (letters/digits/_/-) so it can never traverse outside.
    subfolder = b.get("subfolder", "") or ""
    safe_segs = []
    for seg in str(subfolder).replace("\\", "/").split("/"):
        seg = re.sub(r"[^A-Za-z0-9_-]", "", seg).strip()
        if seg and seg not in (".", ".."):
            safe_segs.append(seg)
    subfolder = "/".join(safe_segs[:3])  # cap depth
    if not data:
        return jsonify({"ok": False, "error": "no image data"}), 400
    mime = "image/png"
    if data.startswith("data:"):
        head, _, data = data.partition(",")
        m = re.search(r"data:([^;]+)", head)
        if m: mime = m.group(1)
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
           "image/webp": "webp", "image/gif": "gif"}.get(mime, "png")
    # data can be: a data-URL (base64, handled above), bare base64, OR a remote
    # https URL (some image models return a URL, not base64). If it's a URL, fetch
    # the real image bytes -- otherwise b64decode fails and we'd save nothing,
    # leaving an EMPTY Drive folder (the bug). Resolve all three to raw bytes.
    raw = None
    if re.match(r"^https?://", data.strip(), re.I):
        try:
            import urllib.request as _ur
            _req = _ur.Request(data.strip(), headers={"User-Agent": "Mozilla/5.0"})
            with _ur.urlopen(_req, timeout=30) as _r:
                raw = _r.read()
            _ct = ""
            try:
                _ct = _r.headers.get("Content-Type", "") if hasattr(_r, "headers") else ""
            except Exception:
                _ct = ""
            if "jpeg" in _ct or "jpg" in _ct: ext = "jpg"
            elif "webp" in _ct: ext = "webp"
            elif "gif" in _ct: ext = "gif"
            elif "png" in _ct: ext = "png"
        except Exception as e:
            return jsonify({"ok": False, "error": f"could not fetch image URL: {str(e)[:160]}"}), 400
    else:
        try:
            raw = _b64.b64decode(data)
        except Exception as e:
            return jsonify({"ok": False, "error": f"bad base64: {e}"}), 400
    if not raw:
        return jsonify({"ok": False, "error": "no image bytes resolved"}), 400
    # AUTHORITATIVE: name the file by the REAL format read from the bytes, not the
    # mime label or Content-Type (either can be wrong -- a model may hand back JPEG
    # bytes tagged image/png, which Amazon then rejects). The bytes never lie.
    ext = _sniff_image_ext(raw, ext)
    # 'ref' uploads (a reference image the user provides) are kept as-is so we
    # don't degrade a source photo; GENERATED/main images are converted to JPEG
    # (Amazon-preferred, much smaller). Skip re-encoding if it's already JPEG.
    if kind != "ref" and ext != "jpg":
        raw = _to_jpeg_bytes(raw, quality=90)
        ext = "jpg"
    import time as _t
    base = _safe_sku(os.path.splitext(name)[0]) if name else kind
    fname = f"{kind}_{int(_t.time())}_{base}.{ext}"[:140]
    d = _sku_dir(sku)
    if subfolder:
        d = os.path.join(d, *subfolder.split("/"))
        os.makedirs(d, exist_ok=True)
    fpath = os.path.join(d, fname)
    try:
        with open(fpath, "wb") as f:
            f.write(raw)
    except Exception as e:
        return jsonify({"ok": False, "error": f"write failed: {e}"}), 500
    aid = _state.get("active_account_id", "") or ""
    _pfx = f"/media/_acct/{_safe_sku(aid)}" if aid else "/media"
    _subpart = f"{subfolder}/" if subfolder else ""
    url = f"{_pfx}/{_safe_sku(sku)}/{_subpart}{fname}"

    # AUTO-DRIVE: for generated/main images, push to the account's Drive folder
    # right away, make it public, and record the mapping so (a) we can hand Amazon
    # a usable direct URL and (b) deleting the local copy also deletes it on Drive.
    drive_direct = drive_view = drive_id = ""
    drive_error = ""
    try:
        if kind in ("generated", "main"):
            acc = _active_account()
            folder = (acc or {}).get("drive_folder_url", "")
            parent_id = _drive_folder_id_from_url(folder)
            if not parent_id:
                drive_error = "no Drive folder configured for this account"
            if parent_id:
                _prod = ""
                try:
                    _rec = next((r for r in _records(_ws())
                                 if str(r.get("SKU", "")).strip() == str(sku).strip()), None)
                    _prod = (_rec or {}).get("Title", "") or ""
                except Exception:
                    _prod = ""
                res = _drive_upload_image(parent_id, sku, _prod, fpath, filename=fname, subpath=subfolder)
                drive_direct = res.get("direct_url", "")
                drive_view   = res.get("view_url", "")
                drive_id     = res.get("id", "")
                if drive_id:
                    _drive_map_put(url, {"drive_id": drive_id,
                                         "direct_url": drive_direct,
                                         "view_url": drive_view})
                else:
                    drive_error = "Drive upload returned no file id"
    except Exception as _e:
        # never let a Drive hiccup fail the LOCAL save; the image is still saved.
        # But DO report the reason so an empty Drive folder isn't a silent mystery.
        drive_direct = drive_view = drive_id = ""
        drive_error = str(_e)[:200]

    return jsonify({"ok": True, "url": url, "name": fname, "sku": _safe_sku(sku),
                    "drive_direct_url": drive_direct, "drive_view_url": drive_view,
                    "drive_id": drive_id, "drive_error": drive_error})


@app.route("/media/list")
def media_list():
    """List stored media grouped by SKU for the ACTIVE account only, so each
    workspace shows its own image library. Optional ?sku= filters."""
    aid = _state.get("active_account_id", "") or ""
    root = _account_media_root(aid)
    # URL prefix that media_serve can resolve back to this root
    url_prefix = f"/media/_acct/{_safe_sku(aid)}" if aid else "/media"
    only = request.args.get("sku")
    out = []
    try:
        skus = [only] if only else sorted(os.listdir(root))
        for s in skus:
            sd = os.path.join(root, _safe_sku(s)) if only else os.path.join(root, s)
            if not os.path.isdir(sd):
                continue
            base = os.path.basename(sd)
            if base == "_acct":      # never list the account container itself
                continue
            files = []
            # walk the SKU folder AND its subfolders (e.g. aplus/basic, aplus/premium,
            # secondary) so organized A+ content is listed too, tagged by group.
            for dirpath, dirnames, filenames in os.walk(sd):
                rel = os.path.relpath(dirpath, sd)
                group = "" if rel == "." else rel.replace(os.sep, "/")
                for fn in sorted(filenames, reverse=True):
                    if fn.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp", "gif"):
                        _fp = os.path.join(dirpath, fn)
                        _w = _h = 0
                        _sz = 0
                        try:
                            _sz = os.path.getsize(_fp)
                            from PIL import Image as _PImg
                            with _PImg.open(_fp) as _im:
                                _w, _h = _im.size
                        except Exception:
                            _w = _h = 0
                        _urlpath = f"{base}/{group}/{fn}" if group else f"{base}/{fn}"
                        files.append({"name": fn, "url": f"{url_prefix}/{_urlpath}",
                                      "width": _w, "height": _h, "bytes": _sz,
                                      "group": group})
            if files:
                # sort so root images come first, then grouped (aplus/basic, etc.)
                files.sort(key=lambda x: (x.get("group", ""), x["name"]), reverse=False)
                out.append({"sku": base, "count": len(files), "files": files})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "folders": out})


@app.route("/media/delete", methods=["POST"])
def media_delete():
    b = request.get_json(force=True) or {}
    url = b.get("url", "")
    # Accept both legacy /media/<sku>/<file> and account-scoped
    # /media/_acct/<aid>/<sku>/<file>. Resolve relative to the media root and
    # guard against path traversal.
    m = re.match(r"^/media/(.+)$", url or "")
    if not m:
        return jsonify({"ok": False, "error": "bad url"}), 400
    relpath = m.group(1)
    if ".." in relpath or relpath.startswith("/"):
        return jsonify({"ok": False, "error": "bad path"}), 400
    fpath = os.path.normpath(os.path.join(_media_root(), relpath))
    if not fpath.startswith(os.path.normpath(_media_root())):
        return jsonify({"ok": False, "error": "bad path"}), 400
    try:
        if os.path.exists(fpath):
            os.remove(fpath)
        # Also remove from Drive if we have a record for this image, so the user's
        # "delete from workspace" truly removes it everywhere (local + Drive).
        drive_removed = False
        try:
            info = _drive_map_remove(url)
            if info and info.get("drive_id"):
                drive_removed = _drive_delete_file(info["drive_id"])
        except Exception:
            drive_removed = False
        return jsonify({"ok": True, "drive_removed": drive_removed})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


_LIVE_CACHE = {}   # key "accountid::MKT" -> {"ts":epoch, "items":[...]}
_LIVE_TTL = 1800   # 30 min (SP-API is free; matches auto-sync cadence)
_COGS_OVERRIDE = {}  # {"accountid::SKU": cost} manual overrides (also persisted to file)
_COGS_FILE = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "cogs_overrides.json")
_IMG_CACHE = {}  # {"accountid::MKT::SKU": {"url":..., "ts":epoch}} live listing main images

# ---- background image-generation jobs (so the UI never blocks) ----
_IMG_JOBS = {}        # job_id -> {status, total, done, results:[...], error, ts}
_IMG_JOBS_LOCK = threading.Lock()


def _new_img_job(total, label="", plan=None):
    import time as _t, uuid as _u
    jid = _u.uuid4().hex[:12]
    with _IMG_JOBS_LOCK:
        _IMG_JOBS[jid] = {"status": "running", "total": total, "done": 0,
                          "results": [], "error": "", "ts": _t.time(),
                          "cancel": False, "label": label, "plan": plan or []}
    try:
        with _IMG_JOBS_LOCK:
            for k in [k for k, v in _IMG_JOBS.items() if _t.time() - v.get("ts", 0) > 3600]:
                _IMG_JOBS.pop(k, None)
    except Exception:
        pass
    return jid


def _job_push(jid, result):
    with _IMG_JOBS_LOCK:
        j = _IMG_JOBS.get(jid)
        if j:
            j["results"].append(result)
            j["done"] = len(j["results"])


def _job_finish(jid, error=""):
    with _IMG_JOBS_LOCK:
        j = _IMG_JOBS.get(jid)
        if j:
            j["status"] = "error" if error else "done"
            if error:
                j["error"] = error


def _job_cancelled(jid):
    """Workers check this between images so a Stop-all takes effect promptly."""
    with _IMG_JOBS_LOCK:
        j = _IMG_JOBS.get(jid)
        return bool(j and j.get("cancel"))


@app.route("/genimage/jobs_active")
def genimage_jobs_active():
    """List every still-running image job so a floating status bar can show
    'Generating X/Y' on ANY page, and survive navigation (jobs live server-side)."""
    import time as _t
    out = []
    with _IMG_JOBS_LOCK:
        for jid, j in _IMG_JOBS.items():
            if j.get("status") == "running":
                out.append({"job": jid, "total": j.get("total", 0),
                            "done": j.get("done", 0), "label": j.get("label", ""),
                            "ts": j.get("ts", 0)})
    out.sort(key=lambda x: x.get("ts", 0))
    return jsonify({"ok": True, "jobs": out})


@app.route("/genimage/stop_all", methods=["POST"])
def genimage_stop_all():
    """Flag every running image job as cancelled. Workers stop between images."""
    n = 0
    with _IMG_JOBS_LOCK:
        for j in _IMG_JOBS.values():
            if j.get("status") == "running":
                j["cancel"] = True
                n += 1
    return jsonify({"ok": True, "stopped": n})


@app.route("/genimage/stop_job", methods=["POST"])
def genimage_stop_job():
    jid = (request.get_json(silent=True) or {}).get("job", "")
    with _IMG_JOBS_LOCK:
        j = _IMG_JOBS.get(jid)
        if j:
            j["cancel"] = True
    return jsonify({"ok": True})


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


# ---------- PPC endpoints ----------
# The PPC section is a per-workspace capability: campaign builder, harvest,
# audit, dashboard, forecast, weekly deck. This module wires the shortcut
# forms and the agent chat to the ppc_module (canonical schemas + builder).

try:
    import ppc_module as _PPC
except Exception as _pe:
    _PPC = None
    _PPC_IMPORT_ERR = str(_pe)
else:
    _PPC_IMPORT_ERR = ""

# Where built bulk files land, so the browser can download them
_PPC_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "ppc_out")
os.makedirs(_PPC_OUT_DIR, exist_ok=True)


@app.route("/ppc/build_campaigns", methods=["POST"])
def ppc_build_campaigns():
    """Build the Sponsored Products bulk CSV from an uploaded keyword file
    + ASIN/SKU/short-name. Validates before returning; the download link is
    only useful if validation passed (or the user overrides warnings)."""
    if _PPC is None:
        return jsonify({"ok": False, "error": f"PPC module not available: {_PPC_IMPORT_ERR}"}), 500
    try:
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "no keyword file uploaded"}), 400
        raw = f.read()
        ingest = _PPC.ingest_csv_bytes(raw)
        if not ingest.get("family"):
            return jsonify({"ok": False, "error":
                f"Could not identify keyword file family from columns: "
                f"{ingest.get('detected_columns', [])[:10]}. Supported: DataDive, Helium 10 Cerebro, Brand Analytics SQP."
            }), 400

        asin = (request.form.get("asin") or "").strip()
        sku  = (request.form.get("sku")  or "").strip()
        pname = (request.form.get("product_short_name") or "").strip()
        if not asin or not sku or not pname:
            return jsonify({"ok": False, "error": "asin, sku, and product_short_name are all required"}), 400
        if asin == sku:
            return jsonify({"ok": False, "error": "SKU cannot equal ASIN -- use the seller SKU from Seller Central"}), 400
        try:
            budget = float(request.form.get("daily_budget") or 8.0)
            bid    = float(request.form.get("default_bid")  or 0.30)
        except ValueError:
            return jsonify({"ok": False, "error": "daily_budget and default_bid must be numbers"}), 400
        try:
            conquest    = tuple(json.loads(request.form.get("conquest_asins")    or "[]"))
            compbrands  = tuple(json.loads(request.form.get("competitor_brands") or "[]"))
            headterms   = tuple(json.loads(request.form.get("category_heads")    or "[]"))
        except json.JSONDecodeError as je:
            return jsonify({"ok": False, "error": f"invalid JSON in list field: {je}"}), 400

        # Bucketing config from the form; per-niche brands/heads
        cfg = _PPC.BucketingConfig(competitor_brands=compbrands,
                                    category_heads=headterms)
        buckets = _PPC.bucket_all(ingest["rows"], cfg)

        inp = _PPC.CampaignBuildInput(
            asin=asin, sku=sku, product_short_name=pname,
            marketplace=(request.form.get("marketplace") or "UK").upper(),
            daily_budget=budget, default_bid=bid,
            conquest_asins=conquest,
        )
        # Standard 20-term negative fence from the doc (universal wastage terms)
        # These are safe defaults; niche-specific ones added by user later.
        default_negs = ("free", "cheap", "used", "second hand", "reviews",
                        "how to", "diy", "manual", "instructions", "recall")
        try:
            out = _PPC.build_sp_bulk(inp, buckets["buckets"], negatives=default_negs)
        except ValueError as ve:
            return jsonify({"ok": False, "error": str(ve)}), 400

        # save the file so it can be downloaded
        import time as _t
        fname = f"sp_bulk_{asin}_{int(_t.time())}.csv"
        fpath = os.path.join(_PPC_OUT_DIR, fname)
        with open(fpath, "w", encoding="utf-8", newline="") as fh:
            fh.write(out["csv"])

        unique_kws = len({r["Keyword Text"] for r in out["rows"] if r.get("Entity") == "Keyword"})

        return jsonify({
            "ok":              True,
            "row_count":       len(out["rows"]),
            "campaign_count":  len(out["campaigns"]),
            "unique_keywords": unique_kws,
            "bucket_counts":   buckets["counts"],
            "validation":      out["validation"],
            "filename":        fname,
            "download_url":    f"/ppc/download/{fname}",
        })
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                        "trace": traceback.format_exc()[-800:]}), 500


@app.route("/ppc/download/<path:fname>")
def ppc_download(fname):
    """Serve a previously-built PPC file. Restricted to _PPC_OUT_DIR to avoid
    directory traversal (Flask's send_from_directory refuses paths outside)."""
    from flask import send_from_directory
    if ".." in fname or fname.startswith("/") or fname.startswith("\\"):
        return "invalid filename", 400
    return send_from_directory(_PPC_OUT_DIR, fname, as_attachment=True)


@app.route("/ppc/harvest", methods=["POST"])
def ppc_harvest():
    """Process an SP Search Term Report into three deliverables:
      - status sheet CSV (colour-coded per term)
      - harvest bulk CSV (new converting terms in all 3 match types)
      - negatives bulk CSV (past-$10 zero-order terms)

    Accepts a keywords-already-targeted list (optional) so already-covered
    terms are excluded from the harvest file -- prevents duplicate
    (keyword, match-type) pairs when uploaded.
    """
    if _PPC is None:
        return jsonify({"ok": False, "error": f"PPC module not available: {_PPC_IMPORT_ERR}"}), 500
    try:
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "SP Search Term Report CSV required"}), 400
        raw = f.read()
        ingest = _PPC.ingest_csv_bytes(raw)
        if ingest.get("family") != "sp_search_term_report":
            return jsonify({"ok": False, "error":
                f"Uploaded file doesn't look like an SP Search Term Report "
                f"(detected: {ingest.get('family') or 'unknown'}). "
                f"Download it from Ads > Measurement & Reporting > Sponsored Products "
                f"Search Term Report."
            }), 400

        asin  = (request.form.get("asin")  or "").strip()
        sku   = (request.form.get("sku")   or "").strip()
        pname = (request.form.get("product_short_name") or "").strip()
        if not asin or not sku or not pname:
            return jsonify({"ok": False, "error": "asin, sku, and product_short_name are required"}), 400
        if asin == sku:
            return jsonify({"ok": False, "error": "SKU cannot equal ASIN"}), 400
        try:
            break_even = float(request.form.get("break_even_acos") or 0.35)
            budget     = float(request.form.get("daily_budget")    or 8.0)
            bid        = float(request.form.get("default_bid")     or 0.30)
        except ValueError:
            return jsonify({"ok": False, "error": "break_even_acos, daily_budget, default_bid must be numbers"}), 400

        # Already-targeted keywords (excluded from harvest to prevent duplicate
        # (keyword, match-type) pairs at upload time). Optional; accepts:
        #   - a CSV file field 'targeted_file' (one keyword per row, any column)
        #   - a JSON array 'targeted_kws'
        already: set = set()
        tf = request.files.get("targeted_file")
        if tf:
            for row in _PPC.ingest_csv_bytes(tf.read()).get("rows", []):
                v = row.get("keyword_text") or row.get("keyword") or list(row.values())[0]
                if v:
                    already.add(_PPC._normalise_kw(v))
        try:
            for k in json.loads(request.form.get("targeted_kws") or "[]"):
                already.add(_PPC._normalise_kw(k))
        except json.JSONDecodeError as je:
            return jsonify({"ok": False, "error": f"invalid targeted_kws JSON: {je}"}), 400

        cfg = _PPC.HarvestConfig(break_even_acos=break_even,
                                  currency=("$" if (request.form.get("marketplace") or "UK").upper() == "US" else "£"))
        result = _PPC.run_harvest(ingest["rows"],
                                    current_targeting_kws=already,
                                    cfg=cfg)

        # Emit the three CSVs and save to _PPC_OUT_DIR
        inp = _PPC.CampaignBuildInput(asin=asin, sku=sku, product_short_name=pname,
                                        daily_budget=budget, default_bid=bid,
                                        marketplace=(request.form.get("marketplace") or "UK").upper())
        harvest_csv    = _PPC.build_harvest_bulk_csv(result["harvest_rows"], inp)
        negatives_csv  = _PPC.build_negatives_bulk_csv(result["negative_rows"], inp)
        status_csv     = _PPC.build_status_sheet_csv(result["status_rows"], currency=cfg.currency)
        # Also emit a COLOURED xlsx status sheet (new): each row tinted by status.
        try:
            import ppc_deliverables as _PD
            status_xlsx = _PD.build_status_xlsx(result["status_rows"], currency=cfg.currency)
        except Exception as _xe:
            # Non-fatal -- CSV still available. Log the error into the response so
            # the user knows the xlsx button will be missing.
            status_xlsx = None
            _xlsx_err = f"xlsx build failed: {_xe}"

        import time as _t
        ts = int(_t.time())
        base = f"{asin}_{ts}"
        fnames = {
            "status":      f"status_{base}.csv",
            "status_xlsx": f"status_{base}.xlsx",
            "harvest":     f"harvest_{base}.csv",
            "negatives":   f"negatives_{base}.csv",
        }
        with open(os.path.join(_PPC_OUT_DIR, fnames["status"]),    "w", encoding="utf-8", newline="") as fh:
            fh.write(status_csv)
        with open(os.path.join(_PPC_OUT_DIR, fnames["harvest"]),   "w", encoding="utf-8", newline="") as fh:
            fh.write(harvest_csv)
        with open(os.path.join(_PPC_OUT_DIR, fnames["negatives"]), "w", encoding="utf-8", newline="") as fh:
            fh.write(negatives_csv)
        if status_xlsx:
            with open(os.path.join(_PPC_OUT_DIR, fnames["status_xlsx"]), "wb") as fh:
                fh.write(status_xlsx)

        downloads = {
            "status":    f"/ppc/download/{fnames['status']}",
            "harvest":   f"/ppc/download/{fnames['harvest']}",
            "negatives": f"/ppc/download/{fnames['negatives']}",
        }
        if status_xlsx:
            downloads["status_xlsx"] = f"/ppc/download/{fnames['status_xlsx']}"

        return jsonify({
            "ok":            True,
            "counts":        result["counts"],
            "totals":        result["totals"],
            "excluded_already_targeted": len(already),
            "downloads":     downloads,
            "filenames":     fnames,
        })
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                        "trace": traceback.format_exc()[-800:]}), 500


@app.route("/ppc/deliverable", methods=["POST"])
def ppc_deliverable():
    """Unified endpoint for the audit / dashboard / forecast / weekly-deck
    shortcuts. Detects file families, produces the polished output
    (docx/pptx/xlsx/html) via ppc_deliverables, and ALSO gets Claude to give
    inline analysis notes so the user sees both the deliverable link and a
    short executive summary.

    For 'auditor' the primary requirement is an SP bulk export; performance
    report is optional (financial section only appears if performance is
    supplied). For 'dashboard' same. For 'forecaster' the primary requirement
    is a business report + target TACOS + net margin. For 'weekly-deck' the
    primary requirement is this-week performance (last-week optional for WoW).
    """
    if _PPC is None:
        return jsonify({"ok": False, "error": f"PPC module not available: {_PPC_IMPORT_ERR}"}), 500
    try:
        import ppc_deliverables as _PD
    except Exception as _pde:
        return jsonify({"ok": False, "error": f"deliverables module not available: {_pde}"}), 500

    try:
        skill    = (request.form.get("skill")    or "").strip()
        context  = (request.form.get("context")  or "").strip()
        account_id  = (request.form.get("account_id")  or "").strip()
        marketplace = (request.form.get("marketplace") or "UK").strip().upper()
        if skill not in _PPC.SKILL_CATALOGUE:
            return jsonify({"ok": False, "error": f"unknown skill: {skill!r}"}), 400

        files = request.files.getlist("files")
        if not files:
            return jsonify({"ok": False, "error": "attach at least one file"}), 400

        # Detect file families + capture full rows for the builders.
        # NOTE: `by_family` concatenates rows across files sharing a family --
        # useful for audit/dashboard where "more rows = better picture", but
        # DESTRUCTIVE for weekly-deck which needs to keep this-week and
        # last-week files SEPARATE. We also keep `by_file` (per-file rows) so
        # skills that need per-file isolation can use that instead.
        file_summary = []
        by_family    = {}   # family -> concatenated rows across all files
        by_file      = []   # list of {filename, family, rows} preserving isolation
        for f in files:
            raw = f.read()
            ingest = _PPC.ingest_csv_bytes(raw)
            fam = ingest.get("family")
            rows = ingest.get("rows") or []
            file_summary.append({
                "filename":  f.filename,
                "family":    fam or "",
                "row_count": ingest.get("raw_row_count", 0),
                "columns":   (ingest.get("detected_columns") or [])[:20],
            })
            by_file.append({"filename": f.filename, "family": fam or "", "rows": rows})
            if fam:
                by_family.setdefault(fam, []).extend(rows)

        # ---- Build the polished output per skill ----
        import time as _t
        ts = int(_t.time())
        base = f"{skill}_{ts}"
        downloads = {}
        missing   = []
        note      = ""

        if skill == "auditor":
            bulk = by_family.get("sp_bulk_export", [])
            if not bulk:
                missing.append("SP bulk export (CSV) -- required for the audit structure")
            else:
                # Performance report shape isn't formally detected as its own family
                # in this MVP -- if there are search-term rows we treat those as
                # performance-adjacent. Real perf report support is a follow-up.
                perf = by_family.get("sp_search_term_report", [])
                audit_bytes = _PD.build_audit_docx(bulk, perf,
                                                    account_label=account_id or "Account",
                                                    marketplace=marketplace)
                fname = f"{base}.docx"
                with open(os.path.join(_PPC_OUT_DIR, fname), "wb") as fh:
                    fh.write(audit_bytes)
                downloads["audit_docx"] = f"/ppc/download/{fname}"
                note = f"Built structural audit from {len(bulk)} bulk-export rows"
                if perf:
                    note += f" + {len(perf)} search-term rows for financial section"

        elif skill == "dashboard":
            bulk = by_family.get("sp_bulk_export", [])
            if not bulk:
                missing.append("SP bulk export (CSV) -- required for the dashboard")
            else:
                perf = by_family.get("sp_search_term_report", [])
                html_bytes = _PD.build_dashboard_html(bulk, perf,
                                                       account_label=account_id or "Account",
                                                       marketplace=marketplace)
                fname = f"{base}.html"
                with open(os.path.join(_PPC_OUT_DIR, fname), "wb") as fh:
                    fh.write(html_bytes)
                downloads["dashboard_html"] = f"/ppc/download/{fname}"
                note = f"Built control-room from {len(bulk)} bulk-export rows"

        elif skill == "forecaster":
            biz = by_family.get("amazon_business_report", [])
            if not biz:
                missing.append("Amazon Business Report (CSV) -- required for the forecast base")
            else:
                # Parse target TACOS + margin from context (user's own numbers -- never invent)
                target_tacos = _parse_pct_from_context(context, "tacos", default=None)
                margin       = _parse_pct_from_context(context, "margin", default=None)
                if target_tacos is None or margin is None:
                    missing.append("Target TACOS % and net margin % -- please state them in the "
                                   "context box (e.g. 'TACOS 15%, margin 25%'). I never invent these.")
                else:
                    fc_bytes = _PD.build_forecast_xlsx(biz,
                                                        target_tacos_pct=target_tacos,
                                                        net_margin_pct=margin)
                    fname = f"{base}.xlsx"
                    with open(os.path.join(_PPC_OUT_DIR, fname), "wb") as fh:
                        fh.write(fc_bytes)
                    downloads["forecast_xlsx"] = f"/ppc/download/{fname}"
                    note = (f"3-scenario forecast: {len(biz)} report days, "
                            f"target TACOS {target_tacos}%, margin {margin}%")

        elif skill == "weekly-deck":
            # Weekly deck needs THIS-WEEK and LAST-WEEK kept SEPARATE. Real
            # Amazon Ads exports have DATES in filenames, not the words 'last'/
            # 'prior'. So we prefer date-parsing over word hints -- the latest
            # date is this-week, earlier dates are last-week. Word hints are a
            # fallback for oddly-named files.
            perf_files = [b for b in by_file if b["family"] == "sp_search_term_report"]
            if not perf_files:
                missing.append("Sponsored Products performance data (Search Term Report or campaign report)")
            else:
                import re as _re
                import datetime as _dt

                def _extract_date(fn: str):
                    """Pull a date out of an Amazon Ads export filename. Tries
                    ISO (YYYY-MM-DD), UK (DD-MM-YYYY), US (MM-DD-YYYY), and
                    'Mon DD YYYY' formats. Returns date or None."""
                    fn = fn or ""
                    # ISO first: 2026-08-08
                    m = _re.search(r"(20\d{2})[-_/](\d{1,2})[-_/](\d{1,2})", fn)
                    if m:
                        try:
                            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                        except ValueError:
                            pass
                    # Mon DD, YYYY: "Aug 8, 2026" or "Aug 08 2026"
                    m = _re.search(r"([A-Za-z]{3,9})[\s,_-]+(\d{1,2})[\s,_-]+(20\d{2})", fn)
                    if m:
                        try:
                            return _dt.datetime.strptime(
                                f"{m.group(1)[:3]} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
                        except ValueError:
                            pass
                    # DD-MM-YYYY (UK) or MM-DD-YYYY (US) -- ambiguous, treat as UK
                    m = _re.search(r"(\d{1,2})[-_/](\d{1,2})[-_/](20\d{2})", fn)
                    if m:
                        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                        if d > 12 and mo <= 12:
                            try: return _dt.date(y, mo, d)
                            except ValueError: pass
                        if mo > 12 and d <= 12:
                            try: return _dt.date(y, d, mo)
                            except ValueError: pass
                        # Both plausible as either day-first or month-first; assume UK
                        try: return _dt.date(y, mo, d)
                        except ValueError:
                            try: return _dt.date(y, d, mo)
                            except ValueError: pass
                    return None

                # Attach an extracted date to each file (None if no date)
                for pf in perf_files:
                    pf["_date"] = _extract_date(pf["filename"])

                dated_files    = [pf for pf in perf_files if pf["_date"] is not None]
                undated_files  = [pf for pf in perf_files if pf["_date"] is None]

                tw_rows = []
                lw_rows = []
                classification = []   # for the response note so user can verify

                if len(dated_files) >= 2:
                    # PRIMARY: sort by date; latest = this-week, rest = last-week
                    dated_files.sort(key=lambda x: x["_date"], reverse=True)
                    tw_file = dated_files[0]
                    tw_rows.extend(tw_file["rows"])
                    classification.append(f"THIS-WEEK: {tw_file['filename']} ({tw_file['_date']})")
                    for pf in dated_files[1:]:
                        lw_rows.extend(pf["rows"])
                        classification.append(f"LAST-WEEK: {pf['filename']} ({pf['_date']})")
                    # Undated files: default to this-week (safer than pretending they're old)
                    for pf in undated_files:
                        tw_rows.extend(pf["rows"])
                        classification.append(f"THIS-WEEK (no date in filename): {pf['filename']}")
                else:
                    # FALLBACK: no dates or only one dated file. Use filename word hints
                    # like 'last'/'prior'/'lw'/'week1' as a last-ditch heuristic.
                    for pf in perf_files:
                        fn = pf["filename"].lower()
                        if ("last" in fn or "prior" in fn or "_lw" in fn or "week1" in fn):
                            lw_rows.extend(pf["rows"])
                            classification.append(f"LAST-WEEK (word hint): {pf['filename']}")
                        else:
                            tw_rows.extend(pf["rows"])
                            classification.append(f"THIS-WEEK: {pf['filename']}")
                    # If ONLY last-week hints matched, promote the first back to this-week
                    if not tw_rows and perf_files:
                        first = perf_files[0]
                        tw_rows = first["rows"]
                        lw_rows = [r for pf in perf_files[1:] for r in pf["rows"]]
                        classification = ([f"THIS-WEEK (promoted): {first['filename']}"] +
                                          [f"LAST-WEEK: {pf['filename']}" for pf in perf_files[1:]])

                brand_from_ctx = ""
                week_from_ctx  = ""
                for line in context.splitlines():
                    ll = line.lower()
                    if ll.startswith("brand:"):        brand_from_ctx = line.split(":",1)[1].strip()
                    elif ll.startswith("week ending:"): week_from_ctx  = line.split(":",1)[1].strip()
                deck_bytes = _PD.build_weekly_deck_pptx(tw_rows, lw_rows or None,
                                                          brand=brand_from_ctx or account_id or "Brand",
                                                          week_ending=week_from_ctx)
                fname = f"{base}.pptx"
                with open(os.path.join(_PPC_OUT_DIR, fname), "wb") as fh:
                    fh.write(deck_bytes)
                downloads["weekly_deck_pptx"] = f"/ppc/download/{fname}"
                note = (f"5-slide deck: {len(tw_rows)} this-week rows"
                        + (f", {len(lw_rows)} last-week rows for WoW" if lw_rows
                           else " (no last-week file detected -- WoW slide will say so)")
                        + "\nFile classification:\n  " + "\n  ".join(classification))

        else:
            missing.append(f"skill '{skill}' has no hand-built deliverable yet")

        # ---- Claude analysis note (optional; degrades gracefully) ----
        spec = _PPC.SKILL_CATALOGUE[skill]
        analysis = ""
        key = (_cfg().get("anthropic_api_key") or "").strip()
        if key and not missing:
            system = (
                "You are the PPC assistant. A polished deliverable was JUST built. "
                "Your job: 3-6 sentence executive summary of what the user should look at "
                "first in the deliverable, based on the file summaries and context. "
                "NEVER invent numbers. NEVER touch bids/budgets. Plain English."
            )
            file_lines = "\n".join(f"- {f['filename']}: {f['family'] or 'unknown'}, "
                                    f"{f['row_count']} rows"
                                    for f in file_summary)
            user_msg = (f"Skill: {skill}\nWorkspace: {account_id or '(unspecified)'} · {marketplace}\n"
                        f"Files:\n{file_lines}\n\nContext:\n{context or '(none)'}\n\n"
                        f"Deliverable built: {list(downloads.keys())}\n")
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=key)
                r = client.messages.create(model=CHAT_MODEL, max_tokens=600,
                                             system=system,
                                             messages=[{"role": "user", "content": user_msg}])
                analysis = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            except Exception as _ce:
                analysis = f"(Claude note skipped: {str(_ce)[:120]})"

        return jsonify({"ok": True,
                        "file_summary": file_summary,
                        "downloads":    downloads,
                        "missing":      missing,
                        "note":         note,
                        "reply":        analysis or note or "Deliverable built."})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                        "trace": traceback.format_exc()[-800:]}), 500


def _parse_pct_from_context(ctx: str, key: str, default=None):
    """Find something like 'TACOS 15%' or 'target tacos: 15' in the user's
    context string. Returns None if not found -- caller adds to `missing` list.
    NEVER invents a value."""
    import re
    if not ctx:
        return default
    pat = re.compile(rf"{key}\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%?", re.I)
    m = pat.search(ctx)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return default
    return default


# ---------- Inventory replenishment endpoints ----------
# Automated port of the manual Lure Essentials Inventory Control Sheet.
# Auto-pulls FBA inventory from SP-API; user uploads 3PL stock file + optional
# YoY/PD uplift files. Formula parity verified against the source workbook.

try:
    import inventory_model as _INV
except Exception as _ie:
    _INV = None
    _INV_IMPORT_ERR = str(_ie)
else:
    _INV_IMPORT_ERR = ""

# v2 module: SP-API Orders API auto-fetch + 4-bucket zero-velocity classification
# + per-account caching (protects Seller Central from report spam).
try:
    import inventory_module as _INV2
except Exception as _ie2:
    _INV2 = None
    _INV2_IMPORT_ERR = str(_ie2)
else:
    _INV2_IMPORT_ERR = ""

_INV_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "inventory_out")
os.makedirs(_INV_OUT_DIR, exist_ok=True)

# v2 cache: per-account report caching, initialised lazily so tests don't need CONFIG_PATH
_INV2_CACHE = None
def _inv2_cache():
    global _INV2_CACHE
    if _INV2_CACHE is None and _INV2 is not None:
        _INV2_CACHE = _INV2.InventoryCache(os.path.join(_INV_OUT_DIR, "cache"))
    return _INV2_CACHE

# Live alerts: {account_id -> count of SKUs needing reorder}. Populated on each run.
_INV_ALERT_COUNTS = {}


def _fetch_fba_inventory_via_spapi(marketplace: str) -> dict:
    """Pull FBA inventory summaries via Inventories API. Returns dict keyed by
    SKU with fba_available / fba_reserved / fba_inbound counts.

    Returns {"ok": bool, "by_sku": dict, "error": str, "warnings": list}.
    Wrapped in try/except so a partial failure doesn't kill the whole request.
    """
    out = {"ok": True, "by_sku": {}, "error": "", "warnings": []}
    try:
        from sp_api.api import Inventories
        from sp_api.base import Marketplaces
    except ImportError as e:
        return {"ok": False, "by_sku": {}, "error": f"sp_api Inventories not available: {e}",
                "warnings": []}
    creds = _sp_creds(marketplace)
    mkt_id = "ATVPDKIKX0DER" if str(marketplace).upper() == "US" else "A1F83G8C2ARO7P"
    mkt = getattr(Marketplaces, "US" if str(marketplace).upper() == "US" else "UK",
                   Marketplaces.UK)
    try:
        client = Inventories(credentials=creds, marketplace=mkt, timeout=30)
    except Exception as e:
        return {"ok": False, "by_sku": {}, "error": f"Inventories client init failed: {e}",
                "warnings": []}
    # Paginated: get all inventory summaries. Amazon returns up to 50 per page.
    next_token = None
    pages = 0
    max_pages = 40      # safety ceiling (~2000 SKUs)
    while True:
        pages += 1
        if pages > max_pages:
            out["warnings"].append(f"Stopped after {max_pages} pages -- more may exist")
            break
        try:
            if next_token:
                resp = client.get_inventory_summary_marketplace(
                    details=True, marketplaceIds=[mkt_id], nextToken=next_token)
            else:
                resp = client.get_inventory_summary_marketplace(
                    details=True, marketplaceIds=[mkt_id])
        except Exception as e:
            out["warnings"].append(f"page {pages}: {str(e)[:150]}")
            if pages == 1:
                out["ok"] = False
                out["error"] = f"first page failed: {e}"
            break
        payload = getattr(resp, "payload", {}) or {}
        summaries = payload.get("inventorySummaries", []) or []
        for s in summaries:
            sku = s.get("sellerSku") or ""
            if not sku:
                continue
            details = s.get("inventoryDetails") or {}
            fulfillable = details.get("fulfillableQuantity", 0) or 0
            reserved = (details.get("reservedQuantity") or {}).get("totalReservedQuantity", 0) or 0
            inbound_working = (details.get("inboundWorkingQuantity") or 0) or 0
            inbound_shipped = (details.get("inboundShippedQuantity") or 0) or 0
            inbound_receiving = (details.get("inboundReceivingQuantity") or 0) or 0
            inbound = inbound_working + inbound_shipped + inbound_receiving
            # If SKU appears twice (edge case), sum them
            if sku in out["by_sku"]:
                out["by_sku"][sku]["fba_available"] += fulfillable
                out["by_sku"][sku]["fba_reserved"]  += reserved
                out["by_sku"][sku]["fba_inbound"]   += inbound
            else:
                out["by_sku"][sku] = {
                    "sku":            sku,
                    "asin":           s.get("asin") or "",
                    "product_name":   s.get("productName") or "",
                    "fba_available":  fulfillable,
                    "fba_reserved":   reserved,
                    "fba_inbound":    inbound,
                }
        # Pagination token
        pagination = payload.get("pagination") or {}
        next_token = pagination.get("nextToken")
        if not next_token:
            break
    return out


def _parse_3pl_csv(raw_bytes: bytes) -> dict:
    """Parse an uploaded 3PL stock CSV. Expected columns (order-insensitive):
      sku (or SKUs, natural sku, sku)
      3PL Stock (Available at Warehouse)
      In-Transit Stock (Sea/Truck to 3PL)
      Ordered Quantity
    Returns dict keyed by SKU.
    """
    import csv, io
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    by_sku = {}
    # tolerant column name matching
    def _pick(row, options):
        for opt in options:
            for k in row:
                if k and k.strip().lower() == opt.lower():
                    return row[k]
        # fuzzier: substring match
        for opt in options:
            for k in row:
                if k and opt.lower() in k.strip().lower():
                    return row[k]
        return ""
    for row in reader:
        sku = _pick(row, ["sku", "skus", "seller sku", "natural sku"])
        if not sku:
            continue
        by_sku[sku.strip()] = {
            "sku":            sku.strip(),
            "pl3_available":  _num(_pick(row, ["3pl stock", "available at warehouse", "warehouse stock"])),
            "pl3_in_transit": _num(_pick(row, ["in-transit", "in transit", "sea/truck"])),
            "pl3_ordered":    _num(_pick(row, ["ordered quantity", "on order", "ordered qty"])),
        }
    return by_sku


def _num(x, default=0.0) -> float:
    if x is None or x == "":
        return default
    try:
        s = str(x).replace(",", "").strip()
        return float(s) if s else default
    except (ValueError, TypeError):
        return default


def _parse_sales_csv(raw_bytes: bytes) -> dict:
    """Parse a Daily Sales CSV. Only needs SKU + per-day rate (units/day).
    Expected columns: sku, daily_rate  OR  sku, sales_last_30, window_days.
    Returns {sku: {sales_last_n, sales_window_days}}.
    """
    import csv, io
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    by_sku = {}
    def _pick(row, options):
        for opt in options:
            for k in row:
                if k and k.strip().lower() == opt.lower():
                    return row[k]
        for opt in options:
            for k in row:
                if k and opt.lower() in k.strip().lower():
                    return row[k]
        return ""
    for row in reader:
        sku = _pick(row, ["sku", "seller sku"])
        if not sku:
            continue
        # daily_rate is preferred; fallback to sales/window
        daily = _pick(row, ["daily rate", "daily_rate", "units per day", "sales per day"])
        sales_n = _pick(row, ["sales_last_n", "sales", "units", "sales last 30"])
        window = _pick(row, ["window_days", "window", "days"])
        if daily != "":
            by_sku[sku.strip()] = {
                "sales_last_n":       _num(daily),
                "sales_window_days":  1,
            }
        else:
            by_sku[sku.strip()] = {
                "sales_last_n":       _num(sales_n),
                "sales_window_days":  _num(window, default=30) or 30,
            }
    return by_sku


def _parse_uplift_csv(raw_bytes: bytes, field: str) -> dict:
    """Parse a YoY or PD uplift CSV (sku -> uplift fraction).
    field: 'yoy_uplift' or 'pd_uplift'
    Expected columns: sku, uplift (or the specific field name)
    """
    import csv, io
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    by_sku = {}
    def _pick(row, options):
        for opt in options:
            for k in row:
                if k and k.strip().lower() == opt.lower():
                    return row[k]
        return ""
    for row in reader:
        sku = _pick(row, ["sku", "seller sku"])
        if not sku:
            continue
        val = _pick(row, [field, "uplift", "increment", "yoy", "pd"])
        by_sku[sku.strip()] = _num(val)
    return by_sku


@app.route("/inventory/build", methods=["POST"])
def inventory_build():
    """Run the replenishment model.

    Auto-pulls FBA inventory from SP-API. User uploads:
      3pl_file          -- 3PL stock CSV (required)
      sales_file        -- Daily sales CSV with per-day rate (required)
      yoy_file          -- YoY uplift CSV (optional; defaults 0)
      pd_file           -- Prime Day uplift CSV (optional; defaults 0)

    Form fields (all optional -- defaults from ReplenishmentTargets):
      target_normal_days   (default 85)
      reorder_cycle_days   (default 5)
      target_long_days     (default 110)
      marketplace          (default UK)
      cycle_label          (free text for the assumptions sheet)
    """
    if _INV is None:
        return jsonify({"ok": False, "error": f"inventory_model not available: {_INV_IMPORT_ERR}"}), 500
    try:
        marketplace = (request.form.get("marketplace") or "UK").strip().upper()
        try:
            targets = _INV.ReplenishmentTargets(
                target_normal_days=int(request.form.get("target_normal_days") or 85),
                reorder_cycle_days=int(request.form.get("reorder_cycle_days") or 5),
                target_long_days=int(request.form.get("target_long_days") or 110),
            )
        except ValueError:
            return jsonify({"ok": False, "error": "target values must be integers"}), 400
        cycle_label = (request.form.get("cycle_label") or "").strip()

        # ---- Required uploads ----
        pl3_file = request.files.get("pl3_file")
        sales_file = request.files.get("sales_file")
        if not pl3_file:
            return jsonify({"ok": False, "error": "3PL stock CSV required"}), 400
        if not sales_file:
            return jsonify({"ok": False, "error": "Daily sales CSV required"}), 400
        pl3_by_sku   = _parse_3pl_csv(pl3_file.read())
        sales_by_sku = _parse_sales_csv(sales_file.read())

        # ---- Optional uplift files ----
        yoy_by_sku = {}
        pd_by_sku  = {}
        yf = request.files.get("yoy_file")
        pf = request.files.get("pd_file")
        if yf: yoy_by_sku = _parse_uplift_csv(yf.read(), "yoy_uplift")
        if pf: pd_by_sku  = _parse_uplift_csv(pf.read(), "pd_uplift")

        # ---- Pull FBA inventory from SP-API ----
        fba_result = _fetch_fba_inventory_via_spapi(marketplace)
        if not fba_result["ok"]:
            return jsonify({"ok": False, "error": f"SP-API FBA fetch failed: {fba_result['error']}",
                            "warnings": fba_result.get("warnings", [])}), 502
        fba_by_sku = fba_result["by_sku"]

        # ---- Merge all sources into canonical rows ----
        # Union of all SKUs seen: prefer FBA (has product name + asin), then 3PL, then sales.
        all_skus = set(fba_by_sku) | set(pl3_by_sku) | set(sales_by_sku)
        rows = []
        for sku in sorted(all_skus):
            fba = fba_by_sku.get(sku, {})
            pl3 = pl3_by_sku.get(sku, {})
            sal = sales_by_sku.get(sku, {})
            row = {
                "sku":                sku,
                "asin":               fba.get("asin", ""),
                "product_name":       fba.get("product_name", ""),
                "market":             marketplace,
                "fulfillment":        "FBA" if sku in fba_by_sku else "FBM",
                "selling_status":     "Continue",
                "fba_available":      fba.get("fba_available", 0),
                "fba_reserved":       fba.get("fba_reserved", 0),
                "fba_inbound":        fba.get("fba_inbound", 0),
                "pl3_available":      pl3.get("pl3_available", 0),
                "pl3_in_transit":     pl3.get("pl3_in_transit", 0),
                "pl3_ordered":        pl3.get("pl3_ordered", 0),
                "sales_last_n":       sal.get("sales_last_n", 0),
                "sales_window_days":  sal.get("sales_window_days", 30),
                "yoy_uplift":         yoy_by_sku.get(sku, 0),
                "pd_uplift":          pd_by_sku.get(sku, 0),
                "increment_pct":      1.0,
            }
            rows.append(row)

        computed = _INV.compute_replenishment(rows, targets)

        # ---- Emit xlsx ----
        xlsx_bytes = _INV.build_replenishment_xlsx(computed, targets,
                                                      cycle_label=cycle_label)
        import time as _t
        ts = int(_t.time())
        fname = f"replenishment_{marketplace}_{ts}.xlsx"
        fpath = os.path.join(_INV_OUT_DIR, fname)
        with open(fpath, "wb") as fh:
            fh.write(xlsx_bytes)

        # Summary metrics for the UI
        skus_needing_replenish = sum(1 for r in computed if r.get("normal_replenish") == "Yes")
        total_units_flagged = sum(_num(r.get("normal_units_needed", 0)) for r in computed
                                   if r.get("normal_replenish") == "Yes")
        stockout_risk_skus = sum(1 for r in computed
                                   if _num(r.get("dos_amz_total", 0)) < 14
                                   and r.get("selling_status") == "Continue")

        return jsonify({
            "ok":               True,
            "download_url":     f"/inventory/download/{fname}",
            "filename":         fname,
            "row_count":        len(computed),
            "sku_coverage": {
                "in_fba":       len(fba_by_sku),
                "in_3pl":       len(pl3_by_sku),
                "in_sales":     len(sales_by_sku),
                "in_yoy":       len(yoy_by_sku),
                "in_pd":        len(pd_by_sku),
                "union":        len(all_skus),
            },
            "summary": {
                "replenish_yes":       skus_needing_replenish,
                "units_flagged":       int(total_units_flagged),
                "stockout_risk_skus":  stockout_risk_skus,
            },
            "warnings":         fba_result.get("warnings", []),
        })
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:250]}",
                        "trace": traceback.format_exc()[-800:]}), 500


@app.route("/inventory/download/<path:fname>")
def inventory_download(fname):
    from flask import send_from_directory
    if ".." in fname or fname.startswith("/") or fname.startswith("\\"):
        return "invalid filename", 400
    return send_from_directory(_INV_OUT_DIR, fname, as_attachment=True)


# ============================================================================
# v2 inventory endpoints: full SP-API automation, 4-bucket classification,
# per-account caching (protects Seller Central from report clutter), and
# in-app alerts (red badge in the sidebar when SKUs need reorder).
# ============================================================================

@app.route("/inventory/v2/run", methods=["POST"])
def inventory_v2_run():
    """Run the full inventory model:
      1. Fetch FBA inventory from SP-API (cached 6h per account)
      2. Fetch sales velocity from SP-API Orders API (last N days)
      3. Optional 3PL CSV upload
      4. Compute replenishment with 4-bucket zero-velocity classification
      5. Emit downloadable xlsx + populate in-app alerts

    Form fields (all optional except account_id):
      account_id, marketplace, marketplace_id
      target_normal_dos (85), reorder_cycle_days (5), target_long_horizon_dos (110)
      sales_window_days (30)
      cache_hours (6)  -- how stale a cached report can be before refresh
      force_refresh    -- 'true' to bypass cache

    File uploads:
      three_pl_file (optional)   -- 3PL CSV matching the user's sheet columns
    """
    if _INV2 is None:
        return jsonify({"ok": False, "error": f"inventory_module not available: {_INV2_IMPORT_ERR}"}), 500

    try:
        account_id = (request.form.get("account_id") or "").strip()
        if not account_id:
            return jsonify({"ok": False, "error": "account_id is required so caching is per-workspace"}), 400
        marketplace = (request.form.get("marketplace") or "US").strip().upper()

        try:
            cfg = _INV2.InventoryConfig(
                target_normal_dos       = int(request.form.get("target_normal_dos")       or 85),
                reorder_cycle_days      = int(request.form.get("reorder_cycle_days")      or 5),
                target_long_horizon_dos = int(request.form.get("target_long_horizon_dos") or 110),
                sales_window_days       = int(request.form.get("sales_window_days")       or 30),
                cache_hours             = int(request.form.get("cache_hours")             or 6),
            )
        except ValueError:
            return jsonify({"ok": False, "error": "config values must be integers"}), 400

        force_refresh = (request.form.get("force_refresh") or "").lower() in ("true", "1", "yes")

        # ---- Marketplace ID resolution ----
        try:
            import accounts as _acc2
            marketplace_id = _acc2.marketplace_id(marketplace) if hasattr(_acc2, "marketplace_id") else ""
        except Exception:
            marketplace_id = ""

        # ---- Load account credentials ----
        creds = None
        try:
            import accounts as _acc2
            for a in _cfg().get("accounts", []):
                if a.get("id") == account_id:
                    creds = _acc2.account_creds(a) if hasattr(_acc2, "account_creds") else None
                    break
        except Exception as e:
            return jsonify({"ok": False, "error": f"could not resolve credentials: {e}"}), 500
        if not creds:
            return jsonify({"ok": False, "error": f"no credentials for account {account_id!r}"}), 400

        cache = _inv2_cache()

        # ---- FBA inventory (cache-aware) ----
        cache_report_type = f"FBA_INVENTORY_{marketplace}"
        fba_cached = None if force_refresh else cache.get(account_id, marketplace, cache_report_type, cfg.cache_hours)
        if fba_cached:
            fba_rows = fba_cached.get("rows", [])
            fba_source = f"cached ({fba_cached.get('_cache_age_hours', 0)}h old)"
        else:
            # Fetch fresh; on error, fall back to stale cache
            fba_result = _INV2.fetch_fba_inventory(creds, marketplace, marketplace_id)
            if fba_result["error"]:
                stale = cache.get_stale(account_id, marketplace, cache_report_type)
                if stale:
                    fba_rows = stale.get("rows", [])
                    fba_source = f"stale ({stale.get('_cache_age_hours', 0)}h old) -- SP-API fetch failed: {fba_result['error']}"
                else:
                    return jsonify({"ok": False, "error": f"FBA fetch failed and no cache available: {fba_result['error']}"}), 502
            else:
                fba_rows = fba_result["rows"]
                cache.put(account_id, marketplace, cache_report_type, {"rows": fba_rows})
                fba_source = f"fresh ({fba_result['report_source']}) -- {len(fba_rows)} SKUs"

        # ---- Sales velocity (cache-aware) ----
        vel_report_type = f"VELOCITY_{marketplace}_{cfg.sales_window_days}d"
        vel_cached = None if force_refresh else cache.get(account_id, marketplace, vel_report_type, cfg.cache_hours)
        if vel_cached:
            velocity = vel_cached.get("units_by_sku", {})
            vel_source = f"cached ({vel_cached.get('_cache_age_hours', 0)}h old)"
        else:
            vel_result = _INV2.fetch_sales_velocity(creds, marketplace, marketplace_id,
                                                     days_back=cfg.sales_window_days)
            if vel_result["error"]:
                stale = cache.get_stale(account_id, marketplace, vel_report_type)
                if stale:
                    velocity = stale.get("units_by_sku", {})
                    vel_source = f"stale ({stale.get('_cache_age_hours', 0)}h old) -- Orders API failed: {vel_result['error']}"
                else:
                    return jsonify({"ok": False, "error": f"Sales velocity fetch failed and no cache: {vel_result['error']}"}), 502
            else:
                velocity = vel_result["units_by_sku"]
                cache.put(account_id, marketplace, vel_report_type,
                          {"units_by_sku": velocity, "total_orders": vel_result.get("total_orders", 0)})
                vel_source = f"fresh -- {len(velocity)} SKUs from {vel_result.get('total_orders', 0)} orders"

        # ---- Optional 3PL CSV ----
        three_pl_rows = []
        three_pl_warnings = []
        tf = request.files.get("three_pl_file")
        if tf:
            result = _INV2.ingest_3pl_csv(tf.read())
            three_pl_rows    = result["rows"]
            three_pl_warnings = result["warnings"]

        # ---- Launch dates: not fetched in v1 (SP-API Catalog Items is slow) ----
        # For now age-classification uses whatever the FBA row contains as fallback.
        # Future: pull createdAt from Catalog Items API in a background pass.
        launch_dates_by_sku = {}

        # ---- Compute ----
        result = _INV2.run_inventory_model(
            fba_rows, velocity, three_pl_rows, launch_dates_by_sku,
            cfg, market=marketplace,
        )

        # ---- Populate the in-app alert count for the sidebar badge ----
        # Count SKUs where reorder is needed (any of: FBA reorder Yes, or 3PL reorder Yes)
        alert_count = sum(1 for r in result["rows"]
                          if r.get("replenish_yesno") == "Yes" or r.get("replenish_3pl") == "Yes")
        _INV_ALERT_COUNTS[account_id] = alert_count

        # ---- Emit xlsx ----
        import time as _t
        ts = int(_t.time())
        fname = f"inventory_v2_{account_id}_{marketplace}_{ts}.xlsx"
        fpath = os.path.join(_INV_OUT_DIR, fname)
        import datetime as _dt
        xlsx_bytes = _INV2.build_inventory_xlsx(
            result, cfg, account_label=account_id,
            generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes"),
        )
        with open(fpath, "wb") as f:
            f.write(xlsx_bytes)

        return jsonify({
            "ok": True,
            "summary": result["summary"],
            "alert_count": alert_count,
            "alerts_sample": result["alerts"][:10],   # first 10 for UI preview
            "fba_source": fba_source,
            "velocity_source": vel_source,
            "three_pl_warnings": three_pl_warnings,
            "download_url": f"/inventory/download/{fname}",
            "filename": fname,
        })
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                        "trace": traceback.format_exc()[-800:]}), 500


@app.route("/inventory/v2/alerts")
def inventory_v2_alerts():
    """Return the current alert count for a workspace (drives the sidebar badge)."""
    account_id = (request.args.get("account_id") or "").strip()
    if not account_id:
        return jsonify({"count": 0})
    return jsonify({"count": _INV_ALERT_COUNTS.get(account_id, 0)})


@app.route("/ppc/agent", methods=["POST"])
def ppc_agent():
    """PPC assistant chat. Routes intent to the right skill, invokes Claude with
    a system prompt that encodes the doc's non-negotiable rules, and returns a
    plain-text reply plus (if matched) the skill id and a next-action hint.

    Non-negotiable rules baked into the prompt:
    - Never sets or changes bids/budgets on its own initiative
    - Enforces match types spelled out / SKU on ads / kw+PT not in same ad group
    - Every keyword in all 3 match types across the portfolio (base + Coverage)
    """
    if _PPC is None:
        return jsonify({"ok": False, "error": f"PPC module not available: {_PPC_IMPORT_ERR}"}), 500
    b = request.get_json(silent=True) or {}
    msg = (b.get("message") or "").strip()
    if not msg:
        return jsonify({"ok": False, "error": "message required"}), 400
    account_id  = (b.get("account_id")  or "").strip()
    marketplace = (b.get("marketplace") or "UK").strip().upper()

    routed = _PPC.route_intent(msg)
    skill = _PPC.SKILL_CATALOGUE.get(routed) if routed else None

    # Build context for the model: workspace + which skill was routed
    ctx_lines = [f"Workspace account: {account_id or '(unspecified)'}",
                 f"Marketplace: {marketplace}"]
    if skill:
        ctx_lines.append(f"Routed skill: {routed}")
        ctx_lines.append(f"Requires: {', '.join(skill['requires'])}")
        ctx_lines.append(f"Produces: {skill['produces']}")
    else:
        ctx_lines.append("No skill matched -- ask user to clarify which capability they want.")
    ctx = "\n".join(ctx_lines)

    system = (
        "You are the PPC assistant inside a listing-generator app. You handle Amazon "
        "Sponsored Products work end to end: campaign building, keyword bucketing, "
        "search-term harvest, negative-keyword rules, audits, dashboards, forecasts, "
        "and weekly client decks.\n\n"
        "NON-NEGOTIABLE RULES (never violate, no exceptions):\n"
        "1. Never set or change bids/budgets on your own initiative. Only when the "
        "user explicitly specifies the value in their message.\n"
        "2. Match types are always spelled out: Exact, Phrase, Broad. Never Ex/Ph/Br.\n"
        "3. Product Ad rows carry the SELLER SKU, never the ASIN.\n"
        "4. Keywords and Product Targets can NEVER share one ad group. Split them.\n"
        "5. Every relevant keyword must exist in all 3 match types across the portfolio "
        "(base campaigns hold primary; a CATCH ALL Coverage campaign fills missing).\n"
        "6. Zero duplicate (keyword, match-type) pairs across the whole bulk file.\n"
        "7. For forecasts and profit math: NEVER fabricate a number. If input data is "
        "missing, stop and ask for it or drop a tier and say so.\n\n"
        "STYLE:\n"
        "- Simple plain English + a short technical explanation when relevant.\n"
        "- Address the user directly. Do not narrate your reasoning at length.\n"
        "- When a shortcut form exists (campaign builder), point the user to it.\n"
        "- When you need input files, list them by name and stop; do not guess content.\n"
    )
    user_msg = f"Context:\n{ctx}\n\nUser message:\n{msg}"

    key = (_cfg().get("anthropic_api_key") or "").strip()
    if not key:
        # Degrade gracefully with routing info even without an LLM key
        parts = ["Anthropic API key not configured -- returning routing info only."]
        if skill:
            parts += [f"", f"Best-matched skill: {routed}.",
                      f"This skill needs: {', '.join(skill['requires'])}.",
                      f"It produces: {skill['produces']}."]
        else:
            parts.append("Could not match your message to a known PPC capability. "
                         "Try: 'build campaigns from a keyword export', 'harvest my "
                         "search-term report', 'audit my PPC health', 'weekly client deck'.")
        return jsonify({"ok": True, "reply": "\n".join(parts),
                        "routed_skill": routed,
                        "next_action":  ""})

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(
            model=CHAT_MODEL, max_tokens=1200,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        reply = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    except Exception as e:
        return jsonify({"ok": False, "error": f"LLM call failed: {str(e)[:200]}"}), 500

    next_action = ""
    if routed == "campaign-builder":
        next_action = "Use the 'Build campaigns from keywords' shortcut (top-left) — it validates before download."
    elif routed == "harvester":
        next_action = "Upload your SP Search Term Report as CSV. (Harvest form coming next session.)"

    return jsonify({"ok": True, "reply": reply,
                    "routed_skill": routed,
                    "next_action":  next_action})


@app.route("/genimage/job_status")
def genimage_job_status():
    jid = request.args.get("job", "")
    with _IMG_JOBS_LOCK:
        j = _IMG_JOBS.get(jid)
        if not j:
            return jsonify({"ok": False, "error": "job not found"}), 404
        return jsonify({"ok": True, "status": j["status"], "total": j["total"],
                        "done": j["done"], "results": j["results"], "error": j["error"],
                        "plan": j.get("plan", []), "cancel": j.get("cancel", False)})


def _img_instructions_path():
    """Sidecar file holding the user's custom image instructions that the AI
    should remember for EVERY image generation, on top of the strategist's brief."""
    return os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "_image_instructions.json")


def _load_img_instructions(aid=None):
    """Returns the custom instruction text. Stored per-account when an account is
    active, with a global fallback that applies to all accounts."""
    try:
        with open(_img_instructions_path(), encoding="utf-8") as f:
            d = json.load(f) or {}
    except Exception:
        d = {}
    aid = aid or _state.get("active_account_id", "") or ""
    # per-account instruction wins; otherwise the global one
    return (d.get("by_account", {}).get(aid, "") or d.get("global", "") or "").strip()


def _save_img_instructions(text, aid=None, scope="account"):
    try:
        try:
            with open(_img_instructions_path(), encoding="utf-8") as f:
                d = json.load(f) or {}
        except Exception:
            d = {}
        d.setdefault("by_account", {})
        if scope == "global":
            d["global"] = text or ""
        else:
            aid = aid or _state.get("active_account_id", "") or ""
            d["by_account"][aid] = text or ""
        with open(_img_instructions_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        return True
    except Exception:
        return False


@app.route("/genimage/instructions", methods=["GET", "POST"])
def genimage_instructions():
    """Get or save the custom image instructions the AI remembers for every image."""
    if request.method == "GET":
        aid = request.args.get("id", "") or _state.get("active_account_id", "")
        return jsonify({"ok": True, "instructions": _load_img_instructions(aid)})
    b = request.get_json(force=True) or {}
    text = (b.get("instructions", "") or "").strip()[:4000]
    scope = (b.get("scope", "account") or "account").lower()
    aid = b.get("id", "") or _state.get("active_account_id", "")
    ok = _save_img_instructions(text, aid=aid, scope=scope)
    return jsonify({"ok": ok, "instructions": text})


def _run_img_jobs_bg(jid, jobs, kind):
    """Background worker: runs a list of generation jobs, pushing each result."""
    # Custom instructions the user wants the AI to remember for EVERY image
    # (e.g. "always pure white background", "include our logo top-left", "no people").
    # We append them to each job's brief so they apply on top of the strategist.
    _custom = _load_img_instructions()
    with app.app_context():
        for job in jobs:
            if _job_cancelled(jid):
                _job_finish(jid, error="stopped by user")
                return
            label = job.get("label", "")
            ref = job.get("ref", "")
            if not ref:
                _job_push(jid, {"ok": False, "label": label, "sku": job.get("sku", ""),
                                "error": "no reference image"})
                continue
            try:
                payload = job.get("payload", {})
                if _custom:
                    # add to whatever brief field the endpoint reads, without
                    # clobbering the strategist's art direction.
                    payload["custom_instructions"] = _custom
                    if payload.get("art_direction") is not None:
                        payload["art_direction"] = (str(payload.get("art_direction", "")).rstrip()
                                                    + "\n\nUSER STANDING INSTRUCTIONS (always apply): " + _custom)
                if kind in ("recipe", "creative"):
                    with app.test_request_context(json=payload):
                        resp = genimage_recipe()
                elif kind == "concept":
                    with app.test_request_context(json=payload):
                        resp = genimage_from_concept()
                elif kind == "source":
                    with app.test_request_context(json=payload):
                        resp = genimage_process_source()
                elif kind == "secondary":
                    with app.test_request_context(json=payload):
                        resp = genimage_secondary_v2()
                elif kind == "aplus":
                    with app.test_request_context(json=payload):
                        resp = aplus_generate()
                else:
                    _job_push(jid, {"ok": False, "label": label, "error": "unknown job kind"})
                    continue
                if isinstance(resp, tuple):
                    data = resp[0].get_json()
                else:
                    data = resp.get_json()
                data = data or {"ok": False, "error": "no response"}
                data["label"] = label
                data["sku"] = job.get("sku", "")
                data["_kind"] = kind
                data["_payload"] = job.get("payload", {})
                # AUTO-SAVE every successful image to the SKU's media library so
                # background results are NEVER lost (even if the user closes the modal)
                if data.get("ok") and data.get("data_url"):
                    try:
                        sku = job.get("sku", "_misc")
                        du = data["data_url"]
                        # Decide a subfolder so A+ content is organized inside the
                        # SKU folder: aplus/basic or aplus/premium; secondary images
                        # go under "secondary". Main/concept stay at the SKU root.
                        _sub = ""
                        if kind == "aplus":
                            _tier = str(payload.get("tier", "") or data.get("tier", "") or "basic").lower()
                            _tier = "premium" if "prem" in _tier else "basic"
                            _sub = f"aplus/{_tier}"
                        elif kind == "secondary":
                            _sub = "secondary"
                        # Resolve the image to RAW BYTES. The model may return a
                        # data: URL (base64) OR a remote https URL -- the old code
                        # only handled data: URLs, so URL-returning models saved
                        # NOTHING (empty Drive + empty library). Handle both.
                        raw_bytes = None
                        ext = "png"
                        if du.startswith("data:"):
                            head, _, raw = du.partition(",")
                            mime = (re.search(r"data:([^;]+)", head) or [None, "image/png"])[1]
                            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")
                            try:
                                raw_bytes = _b64.b64decode(raw)
                            except Exception:
                                raw_bytes = None
                        elif re.match(r"^https?://", du.strip(), re.I):
                            try:
                                import urllib.request as _ur
                                _rq = _ur.Request(du.strip(), headers={"User-Agent": "Mozilla/5.0"})
                                with _ur.urlopen(_rq, timeout=30) as _rr:
                                    raw_bytes = _rr.read()
                                    _ct = _rr.headers.get("Content-Type", "") if hasattr(_rr, "headers") else ""
                                if "jpeg" in _ct or "jpg" in _ct: ext = "jpg"
                                elif "webp" in _ct: ext = "webp"
                                elif "gif" in _ct: ext = "gif"
                            except Exception as _fe:
                                data["save_error"] = f"could not fetch image url: {str(_fe)[:120]}"
                                raw_bytes = None
                        if raw_bytes:
                            import time as _t
                            # Convert every generated image to JPEG: Amazon prefers
                            # JPEG for listing images and they're far smaller than the
                            # ~3-4 MB PNGs the models return. (No quality loss that
                            # matters at q90 for photographic product images.)
                            raw_bytes = _to_jpeg_bytes(raw_bytes, quality=90)
                            ext = "jpg"
                            # Naming: for LIVE Amazon listings we want Amazon's own
                            # convention {ASIN}.{TYPE}.{ext} (e.g. B000123456.MAIN.jpg,
                            # ...PT01.jpg for secondary, ...APLUS01.jpg for A+). The
                            # frontend passes 'asin' + 'img_code' on the job for that.
                            # Fall back to the old timestamp name when no code is set.
                            _asin = str(job.get("asin", "") or "").strip().upper()
                            _code = str(job.get("img_code", "") or "").strip().upper()
                            if _asin and _code:
                                fname = f"{_asin}.{_code}.{ext}"
                            else:
                                fname = f"generated_{int(_t.time()*1000)}.{ext}"
                            _dir = _sku_dir(sku)
                            if _sub:
                                _dir = os.path.join(_dir, *_sub.split("/"))
                                os.makedirs(_dir, exist_ok=True)
                            _full = os.path.join(_dir, fname)
                            with open(_full, "wb") as f:
                                f.write(raw_bytes)
                            _aid = _state.get("active_account_id", "") or ""
                            _pfx = f"/media/_acct/{_safe_sku(_aid)}" if _aid else "/media"
                            _subpart = f"{_sub}/" if _sub else ""
                            saved_url = f"{_pfx}/{_safe_sku(sku)}/{_subpart}{fname}"
                            data["saved_url"] = saved_url
                            # mirror to Drive under the same subpath, make public, map it
                            try:
                                acc = _active_account()
                                folder = (acc or {}).get("drive_folder_url", "")
                                parent_id = _drive_folder_id_from_url(folder)
                                if not parent_id:
                                    data["drive_error"] = "no Drive folder set for this account"
                                else:
                                    _prod = ""
                                    try:
                                        _rec = next((r for r in _records(_ws())
                                                     if str(r.get("SKU", "")).strip() == str(sku).strip()), None)
                                        _prod = (_rec or {}).get("Title", "") or ""
                                    except Exception:
                                        _prod = ""
                                    dres = _drive_upload_image(parent_id, sku, _prod, _full,
                                                               filename=fname, subpath=_sub)
                                    if dres.get("id"):
                                        _drive_map_put(saved_url, {"drive_id": dres.get("id"),
                                                                   "direct_url": dres.get("direct_url", ""),
                                                                   "view_url": dres.get("view_url", "")})
                                        data["drive_direct_url"] = dres.get("direct_url", "")
                                    else:
                                        data["drive_error"] = "Drive upload returned no file id"
                            except Exception as _de:
                                data["drive_error"] = str(_de)[:200]
                    except Exception as _se:
                        data["save_error"] = str(_se)[:200]
                _job_push(jid, data)
            except Exception as e:
                _job_push(jid, {"ok": False, "label": label, "sku": job.get("sku", ""),
                                "error": str(e)[:200]})
    _job_finish(jid)


@app.route("/genimage/start_batch", methods=["POST"])
def genimage_start_batch():
    """Start a background batch of generations. Returns a job_id immediately;
    poll /genimage/job_status?job=ID for progress."""
    b = request.get_json(force=True) or {}
    kind = b.get("kind", "")
    jobs = b.get("jobs", []) or []
    if not jobs:
        return jsonify({"ok": False, "error": "no jobs"}), 400
    label = (b.get("label", "") or "").strip()[:80]
    # a lightweight plan (label + concept per job) so the UI can show every
    # planned image and its status from the very start, not just as they finish.
    plan = [{"label": jb.get("label", ""), "sku": jb.get("sku", ""),
             "concept": (jb.get("payload", {}) or {}).get("concept", "")[:200],
             "img_code": jb.get("img_code", "")} for jb in jobs]
    jid = _new_img_job(len(jobs), label=label, plan=plan)
    t = threading.Thread(target=_run_img_jobs_bg, args=(jid, jobs, kind), daemon=True)
    t.start()
    return jsonify({"ok": True, "job": jid, "total": len(jobs)})
_IMG_TTL = 86400  # 24h — product images rarely change


def _load_cogs_overrides():
    global _COGS_OVERRIDE
    try:
        import json as _j, os as _o
        if _o.path.exists(_COGS_FILE):
            _COGS_OVERRIDE = _j.load(open(_COGS_FILE, encoding="utf-8"))
    except Exception:
        _COGS_OVERRIDE = {}


def _save_cogs_overrides():
    try:
        import json as _j
        _j.dump(_COGS_OVERRIDE, open(_COGS_FILE, "w", encoding="utf-8"), indent=2)
    except Exception:
        pass


def _cogs_from_sku(sku):
    """Dropshipping SKUs are formatted {source_price}_{N}Days_{ASIN}; the first
    number is the source cost (incl. shipping). Returns float or None."""
    try:
        first = str(sku).split("_", 1)[0]
        v = float(first)
        if v > 0:
            return v
    except Exception:
        pass
    return None


def _resolve_cogs(account_id, sku):
    """COGS priority: manual override (by SKU) -> price embedded in SKU. Returns
    (cost_or_None, source_label)."""
    key = f"{account_id}::{sku}"
    if key in _COGS_OVERRIDE:
        try:
            return float(_COGS_OVERRIDE[key]), "manual"
        except Exception:
            pass
    c = _cogs_from_sku(sku)
    if c is not None:
        return c, "sku"
    return None, ""


def _estimate_profit(price, cogs, referral_rate=0.15):
    """Quick profit estimate: price - cogs - referral fee (default 15%).
    FBA fee is not included in the fast estimate (use the Fees API for exact)."""
    try:
        price = float(str(price).replace(",", "").strip() or 0)
    except Exception:
        return None
    if not price or cogs is None:
        return None
    referral = price * referral_rate
    net = price - float(cogs) - referral
    margin = (net / price) if price else 0
    return {"price": round(price, 2), "cogs": round(float(cogs), 2),
            "referral": round(referral, 2), "net": round(net, 2),
            "margin": round(margin * 100, 1)}

@app.route("/optimize/fetch", methods=["POST"])
def optimize_fetch():
    """Read-only: pull a live listing's CURRENT data from Amazon so the user can
    draft edits against it. Nothing is changed. Uses getListingsItem."""
    try:
        import accounts as _acc
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    b = request.get_json(force=True) or {}
    aid = b.get("id", "") or _state.get("active_account_id", "")
    sku = (b.get("sku", "") or "").strip()
    mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
    if not sku:
        return jsonify({"ok": False, "error": "missing sku"}), 400
    acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
    if not acc:
        return jsonify({"ok": False, "error": "account not found"}), 404
    rt = str(acc.get("refresh_token", ""))
    if not rt or rt.startswith(("PUT_", "ROTATE")):
        return jsonify({"ok": False, "error": "connect this account first"}), 400
    creds = _acc.account_creds(acc)
    seller = acc.get("seller_id", "")
    try:
        from sp_api.api import ListingsItemsV20210801 as LI
        from sp_api.base import Marketplaces
    except Exception as e:
        return jsonify({"ok": False, "error": f"sp_api Listings not available: {e}"}), 500
    mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
    mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
    try:
        li = LI(credentials=creds, marketplace=mkt_enum)
        resp = li.get_listings_item(
            seller, sku,
            marketplaceIds=[mid] if mid else None,
            includedData="attributes,summaries,issues")
        pay = resp.payload if hasattr(resp, "payload") else resp
    except Exception as e:
        return jsonify({"ok": False, "error": f"getListingsItem failed: {str(e)[:240]}"}), 502
    # extract the editable fields from the attributes block
    attrs = (pay or {}).get("attributes", {}) if isinstance(pay, dict) else {}
    summaries = (pay or {}).get("summaries", []) if isinstance(pay, dict) else []
    issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
    ptype = ""
    if summaries and isinstance(summaries, list):
        ptype = summaries[0].get("productType", "")
    fields = _extract_editable_fields(attrs)
    # parse issues into a tidy, actionable list naming the exact attributes at fault
    parsed_issues = []
    for iss in issues:
        if not isinstance(iss, dict):
            continue
        names = iss.get("attributeNames") or iss.get("attributeName") or []
        if isinstance(names, str):
            names = [names]
        parsed_issues.append({
            "code": iss.get("code", ""),
            "message": iss.get("message", ""),
            "severity": iss.get("severity", ""),    # ERROR / WARNING / INFO
            "attributes": names,
            "enforcement": (iss.get("enforcements", {}) or {}).get("actions", []),
        })
    # which status does Amazon report?
    listing_status = ""
    if summaries and isinstance(summaries, list):
        st_arr = summaries[0].get("status", []) or []
        listing_status = ", ".join(st_arr) if isinstance(st_arr, list) else str(st_arr)
    return jsonify({"ok": True, "sku": sku, "asin": (summaries[0].get("asin", "") if summaries else ""),
                    "product_type": ptype, "marketplace": mkt, "marketplace_id": mid,
                    "fields": fields, "raw_attributes": attrs,
                    "issues": parsed_issues, "listing_status": listing_status})


@app.route("/optimize/diagnose_fill", methods=["POST"])
def optimize_diagnose_fill():
    """Look at the listing's SP-API issues (the real reason for the red dot) and
    ask the AI to suggest values ONLY for the flagged attributes. Returns
    suggestions for the user to review — nothing is pushed here."""
    try:
        import accounts as _acc
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    b = request.get_json(force=True) or {}
    aid = b.get("id", "") or _state.get("active_account_id", "")
    sku = (b.get("sku", "") or "").strip()
    mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
    if not sku:
        return jsonify({"ok": False, "error": "missing sku"}), 400
    acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
    if not acc:
        return jsonify({"ok": False, "error": "account not found"}), 404
    creds = _acc.account_creds(acc)
    seller = acc.get("seller_id", "")
    mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
    try:
        from sp_api.api import ListingsItemsV20210801 as LI
        from sp_api.base import Marketplaces
    except Exception as e:
        return jsonify({"ok": False, "error": f"sp_api Listings not available: {e}"}), 500
    mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
    try:
        li = LI(credentials=creds, marketplace=mkt_enum)
        resp = li.get_listings_item(seller, sku, marketplaceIds=[mid] if mid else None,
                                    includedData="attributes,summaries,issues")
        pay = resp.payload if hasattr(resp, "payload") else resp
    except Exception as e:
        return jsonify({"ok": False, "error": f"getListingsItem failed: {str(e)[:240]}"}), 502
    attrs = (pay or {}).get("attributes", {}) if isinstance(pay, dict) else {}
    summaries = (pay or {}).get("summaries", []) if isinstance(pay, dict) else []
    issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
    ptype = summaries[0].get("productType", "") if summaries else ""
    title = ""
    try:
        title = attrs.get("item_name", [{}])[0].get("value", "")
    except Exception:
        title = ""

    # collect the attributes Amazon is complaining about (missing/invalid)
    flagged = []
    for iss in issues:
        if not isinstance(iss, dict):
            continue
        names = iss.get("attributeNames") or iss.get("attributeName") or []
        if isinstance(names, str):
            names = [names]
        for nm in names:
            flagged.append({"attribute": nm, "message": iss.get("message", ""),
                            "severity": iss.get("severity", "")})
    # de-dup by attribute name
    seen = set(); flagged_u = []
    for f in flagged:
        if f["attribute"] and f["attribute"] not in seen:
            seen.add(f["attribute"]); flagged_u.append(f)

    if not flagged_u:
        return jsonify({"ok": True, "flagged": [], "suggestions": {},
                        "note": "No attribute-level issues reported. The red status may be due to "
                                "pricing, images, or a category review rather than a missing field."})

    # ask the AI to suggest values for ONLY the flagged attributes
    key = (_cfg().get("anthropic_api_key") or "").strip()
    if not key:
        return jsonify({"ok": True, "flagged": flagged_u, "suggestions": {},
                        "note": "No anthropic_api_key set — showing the flagged fields without AI suggestions."})
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        # give the AI the product context + the current attribute values for reference
        ctx_attrs = {k: attrs.get(k) for k in list(attrs.keys())[:60]}
        sys = (
            "You are an Amazon catalog specialist. Given a product and a list of attributes Amazon "
            "flagged as missing or invalid, suggest a sensible, compliant value for EACH flagged "
            "attribute. Use the product title and existing attributes to infer realistic values "
            "(e.g. dimensions, material, color, unit). For measurements include the unit. If a value "
            "genuinely cannot be inferred and would need the seller to measure/know it, return null for "
            "that attribute and a short 'needs' note. Do NOT invent certifications, safety claims, or "
            "identifiers (UPC/EAN/GTIN). Return ONLY JSON: "
            '{"attribute_name": {"value": <value or null>, "note": "<short reason / what unit>"}}.'
        )
        user = (f"Product title: {title}\nProduct type: {ptype}\n\n"
                f"Flagged attributes:\n{json.dumps(flagged_u, ensure_ascii=False)}\n\n"
                f"Existing attributes (for reference):\n{json.dumps(ctx_attrs, ensure_ascii=False)[:6000]}\n\n"
                "Suggest values for the flagged attributes now. JSON only.")
        msg = client.messages.create(model="claude-sonnet-4-5", max_tokens=1500,
                                     system=sys, messages=[{"role": "user", "content": user}])
        raw = "".join(getattr(x, "text", "") for x in msg.content).strip()
        raw = re.sub(r"^```json|```$", "", raw).strip()
        suggestions = json.loads(raw) if raw else {}
    except Exception as e:
        return jsonify({"ok": True, "flagged": flagged_u, "suggestions": {},
                        "note": f"Could not get AI suggestions ({str(e)[:120]}). Showing flagged fields only."})

    return jsonify({"ok": True, "flagged": flagged_u, "suggestions": suggestions,
                    "product_type": ptype, "title": title})


def _extract_editable_fields(attrs):
    """Pull current values for the editable fields out of the SP-API attributes
    object (which is {attr_name: [{value/...}]}). Returns a tidy dict."""
    def first(name, key="value"):
        v = attrs.get(name)
        if isinstance(v, list) and v:
            item = v[0]
            if isinstance(item, dict):
                return item.get(key, item.get("value", ""))
        return ""
    # bullets are bullet_point: list of {value}
    bullets = []
    bp = attrs.get("bullet_point")
    if isinstance(bp, list):
        bullets = [x.get("value", "") for x in bp if isinstance(x, dict)]
    # price
    price = ""
    pp = attrs.get("purchasable_offer")
    try:
        if isinstance(pp, list) and pp:
            price = pp[0]["our_price"][0]["schedule"][0]["value_with_tax"]
    except Exception:
        price = first("list_price", "value") or ""
    return {
        "title": first("item_name"),
        "bullets": bullets,
        "description": first("product_description"),
        "price": str(price),
        "main_image": first("main_product_image_locator", "media_location") or first("main_product_image_locator"),
    }


@app.route("/optimize/push", methods=["POST"])
def optimize_push():
    """GATED push: apply ONLY the fields the user explicitly approved to the live
    listing via patchListingsItem. The frontend sends only checked fields; we
    double-check an explicit confirm flag is present."""
    try:
        import accounts as _acc
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    b = request.get_json(force=True) or {}
    if not b.get("confirmed"):
        return jsonify({"ok": False, "error": "push not confirmed"}), 400
    aid = b.get("id", "") or _state.get("active_account_id", "")
    sku = (b.get("sku", "") or "").strip()
    mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
    ptype = b.get("product_type", "") or ""
    changes = b.get("changes", {})   # {field: new_value} -- ONLY approved fields
    if not sku or not changes:
        return jsonify({"ok": False, "error": "missing sku or no approved changes"}), 400
    acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
    if not acc:
        return jsonify({"ok": False, "error": "account not found"}), 404
    rt = str(acc.get("refresh_token", ""))
    if not rt or rt.startswith(("PUT_", "ROTATE")):
        return jsonify({"ok": False, "error": "connect this account first"}), 400
    creds = _acc.account_creds(acc)
    seller = acc.get("seller_id", "")
    mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
    # build JSON Patch operations for only the approved fields
    patches = _build_patches(changes)
    if not patches:
        return jsonify({"ok": False, "error": "no patchable fields in approved changes"}), 400
    try:
        from sp_api.api import ListingsItemsV20210801 as LI
        from sp_api.base import Marketplaces
    except Exception as e:
        return jsonify({"ok": False, "error": f"sp_api Listings not available: {e}"}), 500
    mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
    body = {"productType": ptype or "PRODUCT", "patches": patches}
    try:
        li = LI(credentials=creds, marketplace=mkt_enum)
        resp = li.patch_listings_item(
            seller, sku,
            marketplaceIds=[mid] if mid else None,
            body=body)
        pay = resp.payload if hasattr(resp, "payload") else resp
    except Exception as e:
        return jsonify({"ok": False, "error": f"patchListingsItem failed: {str(e)[:240]}"}), 502
    status = (pay or {}).get("status", "") if isinstance(pay, dict) else ""
    issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
    ok = status.upper() in ("ACCEPTED", "VALID") or not issues
    return jsonify({"ok": ok, "status": status, "issues": issues,
                    "pushed_fields": list(changes.keys()), "raw": pay})


@app.route("/listing/push_image", methods=["POST"])
def listing_push_image():
    """Push ONLY the main image to the LIVE Amazon listing via patchListingsItem.
    Amazon must be able to fetch the image over the public internet, so we resolve
    the row's main image to a PUBLIC Drive direct URL (uploading to Drive first if
    it isn't there yet). Local /media/... paths are never sent to Amazon."""
    try:
        import accounts as _acc
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    b = request.get_json(force=True) or {}
    if not b.get("confirmed"):
        return jsonify({"ok": False, "error": "not confirmed"}), 400
    sku = (b.get("sku", "") or "").strip()
    if not sku:
        return jsonify({"ok": False, "error": "missing sku"}), 400
    aid = b.get("id", "") or _state.get("active_account_id", "")
    mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
    ptype = b.get("product_type", "") or ""

    # 1) find the row's current main image (what the user saved via "use as main")
    img = (b.get("image_url", "") or "").strip()
    if not img:
        try:
            _rec = next((r for r in _records(_ws())
                         if str(r.get("SKU", "")).strip() == sku), None)
        except Exception:
            _rec = None
        if _rec:
            for _k in ("main_product_image_locator", "Main Image", "main_image"):
                if _rec.get(_k):
                    img = str(_rec.get(_k)).strip(); break
            if not img:
                try:
                    _attrs = json.loads(_rec.get("Attributes JSON", "") or "{}")
                    img = str(_attrs.get("main_product_image_locator", "")).strip()
                except Exception:
                    img = ""
    if not img:
        return jsonify({"ok": False, "error": "no main image found on this listing"}), 400

    # 2) resolve to a PUBLIC url Amazon can fetch
    public_url = ""
    if re.match(r"^https?://", img, re.I) and "/media/" not in img:
        # already a public URL (e.g. an lh3 Drive link or competitor URL)
        public_url = img
    else:
        # it's a local /media path -> use the Drive map, or upload to Drive now
        mapped = _drive_map_get(img)
        if mapped and mapped.get("direct_url"):
            public_url = mapped["direct_url"]
        else:
            # upload the local file to Drive right now, make public, map it
            m = re.match(r"^/media/(.+)$", img)
            if not m:
                return jsonify({"ok": False, "error": "main image is a local path that can't be resolved"}), 400
            relpath = m.group(1)
            if ".." in relpath or relpath.startswith("/"):
                return jsonify({"ok": False, "error": "bad image path"}), 400
            fpath = os.path.normpath(os.path.join(_media_root(), relpath))
            if not fpath.startswith(os.path.normpath(_media_root())) or not os.path.exists(fpath):
                return jsonify({"ok": False, "error": "main image file not found on disk"}), 400
            acc0 = _active_account()
            folder = (acc0 or {}).get("drive_folder_url", "")
            parent_id = _drive_folder_id_from_url(folder)
            if not parent_id:
                return jsonify({"ok": False, "error": "no Drive folder set for this account — can't make the image public for Amazon"}), 400
            try:
                _prodttl = ""
                try:
                    _rec2 = next((r for r in _records(_ws())
                                  if str(r.get("SKU", "")).strip() == sku), None)
                    _prodttl = (_rec2 or {}).get("Title", "") or ""
                except Exception:
                    _prodttl = ""
                res = _drive_upload_image(parent_id, sku, _prodttl, fpath,
                                          filename=os.path.basename(fpath))
                public_url = res.get("direct_url", "")
                if res.get("id"):
                    _drive_map_put(img, {"drive_id": res.get("id"),
                                         "direct_url": res.get("direct_url", ""),
                                         "view_url": res.get("view_url", "")})
            except Exception as e:
                return jsonify({"ok": False, "error": f"could not upload image to Drive: {str(e)[:160]}"}), 502
    if not public_url:
        return jsonify({"ok": False, "error": "could not resolve a public image URL for Amazon"}), 400

    # 3) patch ONLY the main image on the live listing (reuse the gated push)
    acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
    if not acc:
        return jsonify({"ok": False, "error": "account not found"}), 404
    rt = str(acc.get("refresh_token", ""))
    if not rt or rt.startswith(("PUT_", "ROTATE")):
        return jsonify({"ok": False, "error": "connect this account first"}), 400
    creds = _acc.account_creds(acc)
    seller = acc.get("seller_id", "")
    mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
    patches = _build_patches({"main_image": public_url})
    if not patches:
        return jsonify({"ok": False, "error": "could not build image patch"}), 400
    try:
        from sp_api.api import ListingsItemsV20210801 as LI
        from sp_api.base import Marketplaces
    except Exception as e:
        return jsonify({"ok": False, "error": f"sp_api Listings not available: {e}"}), 500
    mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
    body = {"productType": ptype or "PRODUCT", "patches": patches}
    try:
        li = LI(credentials=creds, marketplace=mkt_enum)
        resp = li.patch_listings_item(seller, sku,
                                      marketplaceIds=[mid] if mid else None, body=body)
        pay = resp.payload if hasattr(resp, "payload") else resp
    except Exception as e:
        return jsonify({"ok": False, "error": f"patchListingsItem failed: {str(e)[:240]}"}), 502
    status = (pay or {}).get("status", "") if isinstance(pay, dict) else ""
    issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
    ok = status.upper() in ("ACCEPTED", "VALID") or not issues
    return jsonify({"ok": ok, "status": status, "issues": issues,
                    "public_url": public_url, "raw": pay})


def _build_patches(changes):
    """Translate approved {field:value} into SP-API JSON-Patch attribute ops."""
    patches = []
    if "title" in changes:
        patches.append({"op": "replace", "path": "/attributes/item_name",
                        "value": [{"value": changes["title"]}]})
    if "description" in changes:
        patches.append({"op": "replace", "path": "/attributes/product_description",
                        "value": [{"value": changes["description"]}]})
    if "bullets" in changes:
        bl = changes["bullets"]
        if isinstance(bl, str):
            bl = [x for x in bl.split("\n") if x.strip()]
        patches.append({"op": "replace", "path": "/attributes/bullet_point",
                        "value": [{"value": x} for x in bl]})
    if "price" in changes and changes["price"]:
        patches.append({"op": "replace", "path": "/attributes/purchasable_offer",
                        "value": [{"our_price": [{"schedule": [{"value_with_tax": float(changes["price"])}]}]}]})
    if "main_image" in changes and changes["main_image"]:
        patches.append({"op": "replace", "path": "/attributes/main_product_image_locator",
                        "value": [{"media_location": changes["main_image"]}]})
    # generic attributes from the full editable list (keys like "attr:<name>")
    for k, v in changes.items():
        if not k.startswith("attr:"):
            continue
        name = k[5:]
        val = v
        if isinstance(val, str) and " | " in val:
            # multi-value attribute -> split back into list of {value}
            parts = [p.strip() for p in val.split(" | ") if p.strip()]
            if "image_locator" in name:
                patches.append({"op": "replace", "path": f"/attributes/{name}",
                                "value": [{"media_location": p} for p in parts]})
            else:
                patches.append({"op": "replace", "path": f"/attributes/{name}",
                                "value": [{"value": p} for p in parts]})
        else:
            if "image_locator" in name:
                patches.append({"op": "replace", "path": f"/attributes/{name}",
                                "value": [{"media_location": val}]})
            else:
                patches.append({"op": "replace", "path": f"/attributes/{name}",
                                "value": [{"value": val}]})
    return patches


@app.route("/live/images", methods=["POST"])
def live_images():
    """Fetch real main images for a batch of SKUs via getListingsItem (summaries
    only — lightweight). Cached per SKU for 24h so it's only slow the first time.
    Body: {id, marketplace, skus:[...]}. Returns {ok, images:{sku:url}}."""
    try:
        import accounts as _acc
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    b = request.get_json(force=True) or {}
    aid = b.get("id", "") or _state.get("active_account_id", "")
    mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
    skus = [s for s in (b.get("skus") or []) if s]
    if not skus:
        return jsonify({"ok": True, "images": {}})
    acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
    if not acc:
        return jsonify({"ok": False, "error": "account not found"}), 404
    rt = str(acc.get("refresh_token", ""))
    if not rt or rt.startswith(("PUT_", "ROTATE")):
        return jsonify({"ok": False, "error": "account not connected"}), 400
    import time as _t
    out = {}
    statuses = {}
    meta = {}
    todo = []
    for sku in skus:
        ck = f"{aid}::{mkt}::{sku}"
        c = _IMG_CACHE.get(ck)
        if c and (_t.time() - c["ts"] < _IMG_TTL):
            out[sku] = c["url"]
            if c.get("status"):
                statuses[sku] = c["status"]
            if c.get("fulfillment") or c.get("handling") is not None:
                meta[sku] = {"fulfillment": c.get("fulfillment", ""), "handling": c.get("handling")}
        else:
            todo.append(sku)
    if todo:
        try:
            from sp_api.api import ListingsItemsV20210801 as LI
            from sp_api.base import Marketplaces
            creds = _acc.account_creds(acc)
            seller = acc.get("seller_id", "")
            mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
            mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
            li = LI(credentials=creds, marketplace=mkt_enum)
            for sku in todo[:40]:
                try:
                    resp = li.get_listings_item(seller, sku,
                                                marketplaceIds=[mid] if mid else None,
                                                includedData="summaries,issues,fulfillmentAvailability,attributes")
                    pay = resp.payload if hasattr(resp, "payload") else resp
                    summaries = (pay or {}).get("summaries", []) if isinstance(pay, dict) else []
                    issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
                    fa = (pay or {}).get("fulfillmentAvailability", []) if isinstance(pay, dict) else []
                    attrs = (pay or {}).get("attributes", {}) if isinstance(pay, dict) else {}
                    url = ""
                    real_status = ""
                    fulfillment = ""
                    handling = None
                    # fulfillment channel + handling time
                    if fa and isinstance(fa, list):
                        code = fa[0].get("fulfillmentChannelCode", "") if isinstance(fa[0], dict) else ""
                        if code:
                            fulfillment = "FBA" if ("AMAZON" in code.upper()) else "FBM"
                    # handling/lead time from attributes (FBM): lead_time_to_ship_max_days
                    try:
                        lt = attrs.get("fulfillment_availability") or []
                        if lt and isinstance(lt, list):
                            handling = lt[0].get("lead_time_to_ship_max_days")
                    except Exception:
                        handling = None
                    if handling is None:
                        try:
                            lt2 = attrs.get("lead_time_to_ship_max_days") or []
                            if lt2 and isinstance(lt2, list):
                                handling = lt2[0].get("value")
                        except Exception:
                            handling = None
                    if summaries:
                        s0 = summaries[0]
                        mi = s0.get("mainImage") or {}
                        url = mi.get("link", "") if isinstance(mi, dict) else ""
                        live_title = s0.get("itemName", "") or ""
                        st_arr = s0.get("status", []) or []
                        has_error = any((iss.get("severity", "") == "ERROR") for iss in issues if isinstance(iss, dict))
                        suppressed = any(("suppress" in str(iss.get("message", "")).lower()
                                          or "search suppress" in str(iss.get("message", "")).lower())
                                         for iss in issues if isinstance(iss, dict))
                        if suppressed:
                            real_status = "Suppressed"
                        elif "BUYABLE" in st_arr:
                            real_status = "Active"
                        elif has_error:
                            real_status = "Incomplete"
                        elif st_arr:
                            real_status = "Inactive"
                        else:
                            real_status = "Inactive"
                        if not fulfillment:
                            fc = s0.get("fulfillmentChannel", "")
                            if fc:
                                fulfillment = "FBA" if "AMAZON" in str(fc).upper() else "FBM"
                    _IMG_CACHE[f"{aid}::{mkt}::{sku}"] = {"url": url, "status": real_status,
                                                          "fulfillment": fulfillment, "handling": handling,
                                                          "ts": _t.time()}
                    if url:
                        out[sku] = url
                    if real_status:
                        statuses[sku] = real_status
                    # carry the live title (reflects edits immediately) in meta
                    _lt = ""
                    try:
                        _lt = live_title
                    except Exception:
                        _lt = ""
                    if fulfillment or handling is not None or _lt:
                        meta[sku] = {"fulfillment": fulfillment, "handling": handling, "title": _lt}
                except Exception:
                    continue
        except Exception as e:
            return jsonify({"ok": False, "error": f"image fetch failed: {str(e)[:160]}",
                            "images": out, "statuses": statuses, "meta": meta}), 502
    return jsonify({"ok": True, "images": out, "statuses": statuses, "meta": meta})


@app.route("/live/catalog", methods=["POST"])
def live_catalog():
    """Fetch the account's LIVE Amazon listings for a marketplace via the Reports
    API (GET_MERCHANT_LISTINGS_ALL_DATA), parse, cache, and return them. This is
    the seller's already-published catalog -- separate from app drafts."""
    try:
        import accounts as _acc
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    b = request.get_json(force=True) or {}
    aid = b.get("id", "") or _state.get("active_account_id", "")
    mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
    force = bool(b.get("force"))
    acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
    if not acc:
        return jsonify({"ok": False, "error": "account not found"}), 404
    rt = str(acc.get("refresh_token", ""))
    if not rt or rt.startswith(("PUT_", "ROTATE")):
        return jsonify({"ok": False, "error": "account has no real refresh token yet"}), 400
    if not mkt:
        return jsonify({"ok": False, "error": "no marketplace selected"}), 400

    ck = f"{aid}::{mkt}"
    import time as _t
    if not force and ck in _LIVE_CACHE and (_t.time() - _LIVE_CACHE[ck]["ts"] < _LIVE_TTL):
        return jsonify({"ok": True, "items": _LIVE_CACHE[ck]["items"], "cached": True})
    # on a forced sync, also drop the per-listing image/status/meta cache for
    # this account+marketplace so titles/images/status/fulfillment all refresh
    if force:
        _pref = f"{aid}::{mkt}::"
        for _k in [k for k in list(_IMG_CACHE.keys()) if k.startswith(_pref)]:
            _IMG_CACHE.pop(_k, None)

    creds = _acc.account_creds(acc)
    try:
        from sp_api.api import Reports
        from sp_api.base import Marketplaces
    except Exception as e:
        return jsonify({"ok": False, "error": f"sp_api Reports not available: {e}"}), 500
    mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.UK
    try:
        import accounts as _acc2
        mkt_id = _acc2.marketplace_id(mkt) if hasattr(_acc2, "marketplace_id") else ""
    except Exception:
        mkt_id = ""
    try:
        rc = Reports(credentials=creds, marketplace=mkt_enum)
        RT = "GET_MERCHANT_LISTINGS_ALL_DATA"
        doc_id = None
        report_source = "new"
        # 0) reuse a recently-generated report ONLY when not forcing. When the
        #    user clicks Sync (force=True), we must generate a FRESH report so
        #    edits made on Amazon are reflected — reusing the old report would
        #    show stale data.
        if not force:
            try:
                existing = rc.get_reports(reportTypes=[RT], processingStatuses=["DONE"],
                                          marketplaceIds=[mkt_id] if mkt_id else None, pageSize=1)
                epay = existing.payload if hasattr(existing, "payload") else existing
                reps = (epay or {}).get("reports", []) if isinstance(epay, dict) else []
                if reps:
                    doc_id = reps[0].get("reportDocumentId")
                    report_source = "reused"
            except Exception:
                doc_id = None
        # 1) else create a fresh report
        if not doc_id:
            cr = rc.create_report(reportType=RT,
                                  marketplaceIds=[mkt_id] if mkt_id else None)
            rid = (cr.payload or {}).get("reportId") if hasattr(cr, "payload") else cr.get("reportId")
            if not rid:
                return jsonify({"ok": False, "error": "no reportId returned"}), 502
            # 2) poll for completion — up to ~4 minutes (Amazon reports can be slow)
            for attempt in range(60):
                st = rc.get_report(rid)
                pay = st.payload if hasattr(st, "payload") else st
                status = pay.get("processingStatus")
                if status == "DONE":
                    doc_id = pay.get("reportDocumentId"); break
                if status in ("CANCELLED", "FATAL"):
                    return jsonify({"ok": False, "error": f"report {status}"}), 502
                _t.sleep(2 if attempt < 10 else 4)   # poll fast early, slower later
            if not doc_id:
                return jsonify({"ok": False, "error":
                    "Amazon is still generating the report (large catalogs can take several minutes). "
                    "Click Sync again in a minute — the report will usually be ready and load instantly."}), 504
        # 3) download + decode the document (param is 'download', not 'decrypt')
        doc = rc.get_report_document(doc_id, download=True)
        dpay = doc.payload if hasattr(doc, "payload") else doc
        # when download=True, the library fetches+decrypts and puts text in 'document'
        text = ""
        if isinstance(dpay, dict):
            text = dpay.get("document", "") or ""
        if not text:
            text = getattr(doc, "document", "") or ""
        # some versions return the URL only; fetch it ourselves as a fallback
        if not text and isinstance(dpay, dict) and dpay.get("url"):
            try:
                import urllib.request, gzip, io
                raw = urllib.request.urlopen(dpay["url"], timeout=60).read()
                if dpay.get("compressionAlgorithm") == "GZIP" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                text = raw.decode("utf-8", "replace")
            except Exception as _e:
                return jsonify({"ok": False, "error": f"could not download report doc: {_e}"}), 502
        items = _parse_listings_report(text)
        # enrich each item with COGS + profit estimate
        for it in items:
            cost, csrc = _resolve_cogs(aid, it.get("sku", ""))
            if cost is not None:
                it["cogs"] = cost
                it["cogs_source"] = csrc
                prof = _estimate_profit(it.get("price", ""), cost)
                if prof:
                    it["profit"] = prof
        # capture the header so we can diagnose missing-title issues
        hdr = []
        try:
            hdr = [h.strip() for h in (text.splitlines()[0].split("\t"))] if text else []
        except Exception:
            hdr = []
        _LIVE_CACHE[ck] = {"ts": _t.time(), "items": items}
        return jsonify({"ok": True, "items": items, "count": len(items),
                        "cached": False, "columns": hdr, "report_source": report_source})
    except Exception as e:
        return jsonify({"ok": False, "error": f"report flow failed: {str(e)[:220]}"}), 500


def _parse_listings_report(text):
    """Parse the TSV from GET_MERCHANT_LISTINGS_ALL_DATA into compact dicts.
    Header names vary slightly between accounts/marketplaces, so match flexibly."""
    if not text:
        return []
    lines = text.splitlines()
    if not lines:
        return []
    header = [h.strip().lower().replace("_", "-") for h in lines[0].split("\t")]

    def col(row, *names):
        # exact match first
        for n in names:
            if n in header:
                i = header.index(n)
                if i < len(row):
                    return row[i].strip()
        # fuzzy: any header that contains the wanted token
        for n in names:
            for i, h in enumerate(header):
                if n in h and i < len(row):
                    v = row[i].strip()
                    if v:
                        return v
        return ""

    out = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        r = ln.split("\t")
        title = col(r, "item-name", "title", "product-name")
        out.append({
            "sku":   col(r, "seller-sku", "sku"),
            "asin":  col(r, "asin1", "asin"),
            "title": title,
            "price": col(r, "price"),
            "qty":   col(r, "quantity"),
            "status": col(r, "status", "listing-status") or "Active",
            "brand": col(r, "brand", "brand-name"),
            "fulfillment": col(r, "fulfillment-channel", "fulfilment-channel"),
            "ship_group": col(r, "merchant-shipping-group", "merchant-shipping-group-name"),
        })
    return out


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
            acc2 = dict(acc); acc2["brands"] = merged
            _acc.save_account(_cfg(), CONFIG_PATH, acc2)
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
        acc2 = dict(acc); acc2["marketplaces"] = detected
        _acc.save_account(_cfg(), CONFIG_PATH, acc2)
        _state["cfg"] = None
    except Exception:
        pass
    return jsonify({"ok": True, "marketplaces": detected, "raw": raw})


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
    return jsonify({"ok": True, "scope": "account",
                    "sheet": sid or _cfg().get("google_spreadsheet_id", ""),
                    "tab": _state["active_tab"]})


def _account_tab_name(acc):
    """The worksheet tab this account's listings live in.

    Priority must MATCH what the generator writes to, or the dashboard reads an
    empty/wrong tab:
      1. _tab_override  -> explicit tab (e.g. a brand tab)
      2. output tab resolved from output_tab_gid (handled by the caller)
      3. the generator's marketplace default -> "Listings v7.0 US" for a US
         account, else "Listings v7.0 UK". (NOT the account label, which would
         point at a non-existent tab and show no listings.)
    """
    if acc.get("_tab_override"):
        return acc["_tab_override"]
    _mkt = str(acc.get("default_marketplace") or "").upper()
    if _mkt == "US":
        return "Listings v7.0 US"
    return OUTPUT_TAB   # "Listings v7.0 UK"


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
    acc["default_marketplace"] = mkt
    try:
        _acc.save_account(_cfg(), CONFIG_PATH, acc)
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
    acc["brands"] = brands
    # persist via save_account (writes back into config accounts list)
    try:
        _acc.save_account(_cfg(), CONFIG_PATH, acc)
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


@app.route("/suggest", methods=["POST"])
def suggest():
    """For a listing's missing/flagged fields, produce a value for each, walking a
    SOURCE PRIORITY chain and labelling where each answer came from:
      1) eBay source (the item we actually sell) -- item specifics
      2) SP-API competitor ASIN data (Amazon)
      3) Amazon search (best-effort; honest about confidence)
      4) AI reasoning (clearly labelled)
    Returns: {ok, product:{title,...}, suggestions:[{field,value,source,confidence,note}]}
    The eBay product stays the anchor throughout."""
    b = request.get_json(force=True) or {}
    sku    = str(b.get("sku", "")).strip()
    fields = b.get("fields") or []          # field keys to fill; empty = infer from flags
    if not sku:
        return jsonify({"ok": False, "error": "missing sku"}), 400

    cfg = _cfg()
    # find the row
    recs = _records(_ws())
    row = None
    for r in recs:
        if str(r.get("SKU", "")).strip() == sku:
            row = r
            break
    if not row:
        return jsonify({"ok": False, "error": "sku not found in current view"}), 404

    try:
        attrs = json.loads(row.get("Attributes JSON") or "{}")
        if not isinstance(attrs, dict): attrs = {}
    except Exception:
        attrs = {}
    title       = row.get("Title", "") or row.get("Product Title", "")
    product_type= row.get("Product Type", "") or attrs.get("product_type", "")
    ebay_url    = row.get("eBay URL", "") or row.get("Source URL", "") or row.get("eBay Link", "")
    comp_asin   = row.get("Competitor ASIN", "") or row.get("ASIN", "")
    marketplace = _marketplace_for_row(row)

    # if no explicit fields requested, derive from the flag note (required-but-missing)
    if not fields:
        note = (row.get("Notes", "") or "") + " " + (row.get("Comp Notes", "") or "")
        fields = _parse_required_missing(note)

    # ---- gather SOURCES (the eBay product is the anchor) ----
    sources = {"ebay": {}, "sp": {}, "ebay_image": "", "raw": {}}
    # tier 1: eBay specifics
    try:
        from amazon_listing_generator import fetch_ebay_supplement
        _eb_app, _eb_cert = _ebay_creds()   # account override wins, else global
        eb = fetch_ebay_supplement(ebay_url, _eb_app, _eb_cert)
        sources["ebay"] = (eb.get("item_specifics") or {})
        imgs = eb.get("images") or eb.get("image_urls") or []
        sources["ebay_image"] = imgs[0] if imgs else (attrs.get("main_product_image_locator", "") or "")
        sources["raw"]["ebay_title"] = eb.get("title", "")
        sources["raw"]["ebay_desc"]  = eb.get("description", "")
    except Exception as e:
        sources["raw"]["ebay_error"] = str(e)[:160]
    # tier 2: SP-API competitor data
    if comp_asin:
        try:
            from amazon_listing_generator import get_competitor_asin_data
            sp = get_competitor_asin_data(comp_asin, _sp_creds(marketplace))
            sources["sp"] = sp.get("attributes", sp) if isinstance(sp, dict) else {}
        except Exception as e:
            sources["raw"]["sp_error"] = str(e)[:160]

    # ---- per-field resolution via the priority chain + AI to finalise ----
    suggestions = _resolve_fields(cfg, fields, attrs, sources, title, product_type, marketplace)
    return jsonify({"ok": True,
                    "product": {"title": title, "sku": sku, "product_type": product_type,
                                "ebay_image": sources["ebay_image"], "ebay_url": ebay_url},
                    "suggestions": suggestions})


def _parse_required_missing(note: str):
    """Pull field keys out of an API-preview note like
    "[E] warranty_description 'Product Warranty' is required but missing."."""
    import re
    out = []
    for m in re.finditer(r"\[E\]\s*([a-z0-9_]+)", note or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    # also catch "'x' is required"
    for m in re.finditer(r"([a-z0-9_]{3,})\s+'[^']+'\s+is required", note or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def _marketplace_for_row(row):
    return (row.get("Marketplace", "") or _state.get("active_marketplace") or "UK").upper().replace("US","US")


def _resolve_fields(cfg, fields, attrs, sources, title, product_type, marketplace):
    """For each field, pick the highest-priority source that has a value, then ask
    the AI to finalise/validate against the eBay product. Returns list of dicts.

    CRITICAL: every value must be one Amazon actually accepts. We pull the exact
    allowed values (enums) + field titles from Amazon's own schema and (a) snap
    source values to them deterministically, (b) hand the allowed lists to the AI
    so it can ONLY choose Amazon's own values -- no translations or alternatives
    that cause "invalid value" / "required but missing" rejections.

    SUB-FIELD AWARE: when Amazon flags a parent field like `maximum_speed` and the
    schema declares sub-fields (value + unit) under it, we EXPAND that flagged
    field into per-sub-field suggestions with dot-notation keys
    (`maximum_speed.value`, `maximum_speed.unit`). This ensures Applied values
    actually populate the boxes the sub-field renderer reads from, and the
    generator's _renest folds them back into Amazon's expected object shape.
    Without this expansion, the AI wrote a combined string ('80.0 kilometers_per_hour')
    to the parent key -- the sub-field boxes stayed empty, the user thought the
    apply failed, and Amazon rejected the submit with 'unit does not have enough
    values'."""
    ebay = {k.lower(): v for k, v in (sources.get("ebay") or {}).items()}
    sp   = {k.lower(): v for k, v in (sources.get("sp") or {}).items()}

    # Amazon's real allowed values for THIS product type (the ground truth).
    _schema = _load_schema(product_type)
    _enums  = _schema.get("enums", {})        # {field: [allowed, ...]}
    _subs   = _schema.get("subfields", {})    # {parent: [{path,label,kind,enum}]}

    # ---- SUB-FIELD EXPANSION -----------------------------------------------
    # For each flagged parent that has sub-fields, replace it with per-sub-field
    # entries using dot-notation keys. Also build a per-sub-key enum map so the
    # AI knows the allowed values for each sub-field (e.g. maximum_speed.unit
    # gets [kilometers_per_hour, miles_per_hour, meters_per_second]).
    expanded_fields = []
    _sub_enums = {}                # {'maximum_speed.unit': [...allowed...]}
    _parent_of = {}                # {'maximum_speed.value': 'maximum_speed'}
    for f in fields:
        if f in _subs and _subs[f]:
            for s in _subs[f]:
                sub_key = f + "." + s["path"]
                expanded_fields.append(sub_key)
                _parent_of[sub_key] = f
                if s.get("enum"):
                    _sub_enums[sub_key] = list(s["enum"])
        else:
            expanded_fields.append(f)
    fields = expanded_fields

    def _snap_to_enum(field, value):
        """If the field is an enum (top-level or sub-field), force `value` to an
        allowed Amazon value. Returns (snapped_value, matched_bool)."""
        allowed = _sub_enums.get(field) or _enums.get(field)
        if not allowed:
            return value, True                # not an enum -> free text ok
        if value is None or str(value).strip() == "":
            return None, False
        v = str(value).strip()

        # UK-US spelling + singular/plural normaliser. 'centimetres' vs
        # 'centimeters' differ by more than substring, so we canonicalise both
        # sides before comparing. This is the same approach as the generator's
        # _norm_tok, kept in sync.
        def _canon(s):
            s = str(s).lower().replace(" ", "_").replace("-", "_")
            s = s.replace("metre", "meter").replace("litre", "liter")
            if s.endswith("s"): s = s[:-1]  # drop trailing 's' for plural
            return s

        # 1) exact
        for a in allowed:
            if v == a:
                return a, True
        # 2) case-insensitive / normalised
        vn = v.lower().replace(" ", "_").replace("-", "_")
        for a in allowed:
            an = a.lower().replace(" ", "_").replace("-", "_")
            if vn == an:
                return a, True
        # 3) UK/US + singular/plural canonical match
        vc = _canon(v)
        for a in allowed:
            if _canon(a) == vc:
                return a, True
        # 4) substring either way (lithium ion -> lithium_ion)
        for a in allowed:
            an = a.lower().replace(" ", "_").replace("-", "_")
            if vn in an or an in vn:
                return a, True
        return v, False                       # no match -> caller decides

    # ---- DETERMINISTIC VALUE+UNIT SPLIT FROM SOURCE DATA -------------------
    # If a source has 'maximum_speed' as '80 km/h' or '80 kilometers per hour',
    # split it into value + unit BEFORE handing to the AI. This means the AI
    # doesn't have to guess -- the source value is already fed as separate
    # numeric + unit strings, each mapped to the correct sub-key.
    def _split_source_value_unit(raw):
        """Return (number_str, unit_str) or (None, None). Accepts the same shapes
        as the generator's _split_value_unit -- kept in sync deliberately."""
        import re as _re
        m = _re.match(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z][A-Za-z0-9 ._-]*)?\s*$",
                       str(raw or ""))
        if not m:
            return None, None
        num = m.group(1)
        unit = (m.group(2) or "").strip() or None
        return num, unit

    # quick deterministic match: does a source already hold this field (by fuzzy key)?
    def _from_source(field):
        # For dot-keys, look up the parent in the source and split
        if "." in field:
            parent = _parent_of.get(field) or field.split(".", 1)[0]
            leaf   = field.split(".", 1)[1]     # 'value' or 'unit' typically
            f = parent.lower().replace("_", " ").strip()
            for src_name, src in (("eBay", ebay), ("Amazon competitor (SP-API)", sp)):
                for k, v in src.items():
                    if not v:
                        continue
                    kk = k.lower().replace("_", " ")
                    if kk == f or f in kk or kk in f:
                        # Split the combined string into value + unit
                        num, unit = _split_source_value_unit(v)
                        if leaf == "value" and num is not None:
                            return num, src_name
                        if leaf == "unit" and unit:
                            return unit, src_name
                        # Fallback for non-value/unit leaves: use the whole string
                        if leaf not in ("value", "unit"):
                            return str(v), src_name
            return None, None
        # Flat field lookup
        f = field.lower().replace("_", " ").strip()
        for src_name, src in (("eBay", ebay), ("Amazon competitor (SP-API)", sp)):
            for k, v in src.items():
                if not v:
                    continue
                kk = k.lower().replace("_", " ")
                if kk == f or f in kk or kk in f:
                    return str(v), src_name
        return None, None

    prelim = []
    # COMPLIANCE FIELDS OWNED BY THE GENERATOR: these have exactly-one-correct
    # structure (boolean switches, hazmat aspect+UN3481, wattage+unit, battery
    # composites). The generator's build_api_attributes fills them deterministically
    # on every Preview/Submit. If the AI also guesses them we get a fight and a
    # broken shape. So we DON'T ask the AI for these -- we surface a clear,
    # already-correct note instead, and let the code own them.
    _CODE_OWNED = {
        "hazmat", "contains_battery_or_cell", "batteries_included",
        "batteries_required", "battery_installation_device_type", "wattage",
        "battery", "lithium_battery", "number_of_lithium_ion_cells",
        "number_of_lithium_metal_cells", "supplier_declared_dg_hz_regulation",
    }
    _code_owned_hits = []
    for field in list(fields):
        if str(field).strip().lower() in _CODE_OWNED:
            _code_owned_hits.append({
                "field": field,
                "value": "(filled automatically on Preview)",
                "source": "app compliance fix",
                "confidence": "high",
                "note": "The app fills this in Amazon's exact required format when you "
                        "click Preview \u2014 you don't need to set it here. Just click "
                        "Preview after applying the other suggestions.",
                "_code_owned": True,
            })
    # remove code-owned fields from the AI work list
    fields = [f for f in fields if str(f).strip().lower() not in _CODE_OWNED]

    for field in fields:
        val, src = _from_source(field)
        # snap any source value to Amazon's allowed list right away
        # (works for both flat fields and dot-notation sub-fields)
        if val and (field in _enums or field in _sub_enums):
            snapped, ok = _snap_to_enum(field, val)
            if ok and snapped:
                val = snapped
                src = (src or "source") + " -> Amazon value"
        prelim.append({"field": field, "value": val or "", "source": src or "", "note": ""})

    # hand the whole picture to the AI to finalise: confirm source values fit the
    # eBay product, and fill any still-empty fields with clearly-labelled reasoning.
    key = (cfg.get("anthropic_api_key") or "").strip()
    if not key:
        # no AI: return what the sources gave, mark empties as needing input
        for p in prelim:
            if not p["value"]:
                p["source"] = "none"; p["note"] = "No source data; add your Anthropic key for AI reasoning."
            else:
                p["confidence"] = "from source"
        return _code_owned_hits + prelim
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        # Build a UNIFIED allowed-values map covering BOTH flat fields and
        # sub-field dot-keys. The AI sees one map, doesn't need to know which is
        # which -- it just picks from the allowed list per key.
        _allowed_for_ai = {}
        for f in fields:
            if f in _enums:
                _allowed_for_ai[f] = _enums[f]
            elif f in _sub_enums:
                _allowed_for_ai[f] = _sub_enums[f]
        payload = {
            "product_title": title, "product_type": product_type, "marketplace": marketplace,
            "ebay_specifics": sources.get("ebay", {}),
            "amazon_competitor_data": sources.get("sp", {}),
            "current_attributes": {k: attrs.get(k) for k in list(attrs)[:40]},
            "fields_to_fill": fields,
            "preliminary_from_sources": prelim,
            # Amazon's EXACT allowed values per field. The AI MUST choose from
            # these for any field listed here -- nothing else is accepted.
            "amazon_allowed_values": _allowed_for_ai,
            # Guidance for the AI so it understands dot-notation keys are
            # sub-fields, and should be returned as numeric-only for '.value'
            # keys and enum-picked for '.unit' keys.
            "subfield_guidance": (
                "Keys with a dot (e.g. 'maximum_speed.value', 'maximum_speed.unit') "
                "are sub-fields of a nested attribute. For '.value' sub-keys return "
                "ONLY the numeric part (e.g. '80' or '80.0', not '80 km/h'). For "
                "'.unit' sub-keys pick from amazon_allowed_values -- exact string."
            ),
        }
        system = (
            "You fill missing Amazon listing attributes for a product the seller is "
            "sourcing FROM EBAY. The eBay item is the ground truth -- anchor every answer "
            "to it. For each requested field, return the best value and its SOURCE, using "
            "this strict priority: (1) eBay specifics, (2) Amazon competitor data, "
            "(3) general knowledge of this exact product, (4) reasonable inference. "
            "NEVER invent specifics that contradict the eBay data. "
            "CRITICAL VALUE RULE: 'amazon_allowed_values' gives the EXACT set of values "
            "Amazon accepts for certain fields. For ANY field present in that map, your "
            "value MUST be copied verbatim from its allowed list -- exact string, exact "
            "case, exact underscores. Do NOT translate, prettify, or substitute (e.g. if "
            "allowed has 'led' do not return 'LED'; if it has 'battery_powered' do not "
            "return 'USB'). Pick the allowed value that best matches the eBay product. "
            "For required compliance fields on an ordinary non-hazardous product, choose "
            "the allowed value meaning 'not applicable'/'no' if present. "
            "Mark source as one of: 'eBay', 'Amazon competitor (SP-API)', 'AI knowledge', "
            "'AI inference'. Give a confidence: 'high' | 'medium' | 'low'. "
            "Respond ONLY as JSON: {\"suggestions\":[{\"field\":\"..\",\"value\":\"..\","
            "\"source\":\"..\",\"confidence\":\"..\",\"note\":\"short why\"}]}. No prose."
        )
        msg = client.messages.create(
            model=CHAT_MODEL, max_tokens=1500, system=system,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        text = "".join(getattr(p, "text", "") for p in msg.content if getattr(p, "type", "") == "text")
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        data = json.loads(text)
        out = data.get("suggestions", [])
        # HARD GUARANTEE: snap every AI value to Amazon's allowed list. Even if the
        # model returned 'LED' or 'USB', force it to the exact Amazon string so the
        # value the user applies is one Amazon will accept. Now handles both flat
        # fields AND sub-field dot-keys via the unified allowed map.
        for s in out:
            f = s.get("field")
            allowed = _allowed_for_ai.get(f)
            if allowed and s.get("value"):
                snapped, ok = _snap_to_enum(f, s["value"])
                if ok and snapped:
                    if snapped != s["value"]:
                        s["note"] = (s.get("note", "") + " (snapped to Amazon value)").strip()
                    s["value"] = snapped
                else:
                    # AI value isn't valid and nothing matched -> offer the first
                    # allowed value rather than a guaranteed rejection.
                    s["value"] = allowed[0]
                    s["source"] = "Amazon allowed values"
                    s["note"] = "AI value not in Amazon's list; defaulted to first allowed value."
        # ensure every requested field is present
        have = {s.get("field") for s in out}
        for f in fields:
            if f not in have:
                allowed = _allowed_for_ai.get(f)
                # if it's an enum field (flat or sub), offer Amazon's first allowed value
                if allowed:
                    out.append({"field": f, "value": allowed[0],
                                "source": "Amazon allowed values", "confidence": "medium",
                                "note": "Chosen from Amazon's allowed values."})
                else:
                    out.append({"field": f, "value": "", "source": "none",
                                "confidence": "low", "note": "AI returned no value; please fill manually."})
        return _code_owned_hits + out
    except Exception as e:
        for p in prelim:
            if not p.get("value"):
                p["source"] = "none"; p["note"] = f"AI step failed: {str(e)[:120]}"
            p.setdefault("confidence", "from source" if p.get("value") else "low")
        return _code_owned_hits + prelim


def _fetch_page_text(url, limit=9000):
    """Fetch a web page and return cleaned visible text (best-effort)."""
    try:
        import urllib.request, gzip, io, re as _re
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"})
        raw = urllib.request.urlopen(req, timeout=20).read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        html = raw.decode("utf-8", "replace")
        # strip scripts/styles, collapse tags to text
        html = _re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
        text = _re.sub(r"(?s)<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit]
    except Exception as e:
        return f"__FETCH_ERROR__: {e}"


@app.route("/optimize/from_source", methods=["POST"])
def optimize_from_source():
    """Read the REAL product from an eBay and/or Amazon URL, then rewrite the
    listing copy (title/bullets/description) for the user's own brand. Returns
    JSON suggestions for the optimize editor to apply. Nothing is sent to Amazon."""
    b = request.get_json(force=True) or {}
    ebay_url = (b.get("ebay_url", "") or "").strip()
    amazon_url = (b.get("amazon_url", "") or "").strip()
    current = b.get("current", {}) or {}        # current title/bullets/description
    product_type = b.get("product_type", "")
    instruction = (b.get("instruction", "") or "").strip()   # user's custom request to the AI
    aid = b.get("id", "") or _state.get("active_account_id", "")
    if not ebay_url and not amazon_url and not instruction:
        return jsonify({"ok": False, "error": "Provide a product link and/or a custom instruction."}), 400

    # resolve the account's brand as OPTIONAL context (do NOT force it into copy,
    # and never fall back to the account label as a brand)
    brand = ""
    try:
        import accounts as _acc
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if acc:
            bl = [x for x in (acc.get("brands") or []) if x and x.strip()]
            brand = bl[0] if bl else ""
    except Exception:
        brand = ""

    sources = []
    for label, u in (("eBay", ebay_url), ("Amazon", amazon_url)):
        if not u:
            continue
        txt = _fetch_page_text(u)
        if txt.startswith("__FETCH_ERROR__"):
            sources.append(f"[{label} link could not be fetched: {txt}]")
        else:
            sources.append(f"=== {label} source page ===\n{txt}")
    source_blob = "\n\n".join(sources) if sources else "(no source link provided — work from the current copy and the user's instruction)"

    key = (_cfg().get("anthropic_api_key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "No anthropic_api_key in config.json"}), 400
    try:
        import anthropic
    except ImportError:
        return jsonify({"ok": False, "error": "anthropic not installed"}), 500

    # load compliance + IP guidance if present so the rewrite respects them
    compliance_hint = ""
    try:
        import os as _o
        if _o.path.exists("ip_rules.json"):
            ipr = json.load(open("ip_rules.json", encoding="utf-8"))
            forb = ipr.get("forbidden_phrases", []) or ipr.get("forbidden", [])
            if forb:
                compliance_hint += ("\nDo NOT use these trademarked/forbidden phrases: "
                                    + ", ".join(list(forb)[:60]) + ".")
    except Exception:
        pass

    system = (
        "You are an expert Amazon listing copywriter helping a seller fix/optimize a live listing. "
        "You may be given: the raw text of the REAL product page (eBay/Amazon), the seller's current "
        "copy, and a custom instruction from the seller. Identify what the product ACTUALLY is, then "
        "write accurate, conversion-focused Amazon copy.\n"
        "HARD RULES:\n"
        "- Follow the seller's custom instruction exactly when given (e.g. whether or not to include a "
        "brand name, tone, focus, length).\n"
        "- Be factually faithful to the real product; do NOT invent specs not supported by the source.\n"
        "- Do NOT copy the source text verbatim; do NOT mention the source seller or their brand.\n"
        "- Do NOT force any brand name into the title or copy unless the seller asks for it. If the "
        "seller says not to include a brand, write generic brandless copy.\n"
        "- Stay Amazon-compliant: no medical/disease claims, no '#1/best seller' unverifiable claims, "
        "no guarantee/cure language." + compliance_hint + "\n"
        'Return ONLY JSON: {"title": "<=200 chars", "bullets": [5 strings], "description": "2-4 short paragraphs"}. '
        "No preamble, no markdown."
    )
    brand_line = (f"Seller's brand (available if the instruction asks to use it; otherwise do NOT insert it): {brand}\n"
                  if brand else "Seller has no brand set — write brandless unless the instruction says otherwise.\n")
    user_msg = (
        f"Product type: {product_type or 'unknown'}\n"
        + brand_line
        + (f"\nSELLER'S CUSTOM INSTRUCTION (follow this):\n{instruction}\n" if instruction else "\n(No custom instruction given — just produce accurate, optimized copy.)\n")
        + f"\nSELLER'S CURRENT COPY:\n{json.dumps(current, ensure_ascii=False)[:2000]}\n\n"
        f"REAL PRODUCT SOURCE TEXT:\n{source_blob[:14000]}\n\n"
        "Now produce the JSON copy following all rules and the seller's instruction."
    )
    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-sonnet-4-5", max_tokens=1500,
            system=system, messages=[{"role": "user", "content": user_msg}])
        txt = "".join(getattr(blk, "text", "") for blk in resp.content).strip()
        txt = txt.replace("```json", "").replace("```", "").strip()
        data = json.loads(txt)
        return jsonify({"ok": True, "suggestion": {
            "title": data.get("title", ""),
            "bullets": data.get("bullets", []) if isinstance(data.get("bullets"), list) else [],
            "description": data.get("description", ""),
        }, "brand": brand, "fetched": [s[:60] for s in sources]})
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "AI returned non-JSON; try again."}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": f"AI error: {str(e)[:200]}"}), 502


@app.route("/ask", methods=["POST"])
def ask():
    b       = request.get_json(force=True) or {}
    history = b.get("messages", [])
    ctx     = b.get("context")
    uploads = b.get("images", [])
    key = (_cfg().get("anthropic_api_key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "No anthropic_api_key in config.json"}), 400
    if not history:
        return jsonify({"ok": False, "error": "empty message"}), 400
    try:
        import anthropic
    except ImportError:
        return jsonify({"ok": False, "error": "anthropic not installed (pip install anthropic)"}), 500
    try:
        client = anthropic.Anthropic(api_key=key)
        system = (
            "You are a practical assistant embedded in an Amazon UK listing tool. You help the seller "
            "choose values for listing attributes (size, is_assembly_required, material, dimensions, "
            "item_type_keyword, colour, etc.) for the product they are listing. Give concise, decisive "
            "answers with brief reasoning. Use UK marketplace conventions and metric units where relevant. "
            "If the user shares a competitor image, read it carefully and answer what it shows (for example "
            "whether assembly looks required). If unsure, say so and say how to confirm. Keep answers short "
            "unless asked for more detail."
        )
        api_messages = []
        for m in history:
            role = "assistant" if m.get("role") == "assistant" else "user"
            api_messages.append({"role": role, "content": str(m.get("text", ""))})
        if api_messages and api_messages[-1]["role"] == "user":
            last_text = api_messages[-1]["content"]
            blocks = []
            for img in uploads:
                d = img.get("data")
                if d:
                    blocks.append({"type": "image", "source": {
                        "type": "base64", "media_type": img.get("media_type", "image/jpeg"), "data": d}})
            for u in _URL_RE.findall(last_text)[:4]:
                got = _fetch_image_b64(u)
                if got:
                    blocks.append({"type": "image", "source": {
                        "type": "base64", "media_type": got[0], "data": got[1]}})
            prefix = ""
            if ctx:
                prefix = ("The user is asking about this listing:\n"
                          + json.dumps(ctx, ensure_ascii=False, indent=2) + "\n\n")
            blocks.append({"type": "text", "text": prefix + last_text})
            api_messages[-1]["content"] = blocks
        resp  = client.messages.create(model=CHAT_MODEL, max_tokens=1500,
                                       system=system, messages=api_messages)
        reply = "".join(getattr(p, "text", "") for p in resp.content
                        if getattr(p, "type", "") == "text")
        return jsonify({"ok": True, "reply": reply or "(no text in response)"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 500


@app.route("/")
def index():
    return Response(_HTML, mimetype="text/html")


_RECORDS_CACHE = {}   # {sheet_id::tab: (ts, records)} -- short TTL to avoid 429s
_RECORDS_TTL = 12     # seconds


def _bust_records_cache():
    """Clear the short read-cache so a just-written change is read fresh."""
    _RECORDS_CACHE.clear()


@app.route("/input_sheet")
def input_sheet():
    """Return the active account's INPUT sheet as a grid (headers + rows) so it can
    be shown inside the app without opening Google Sheets separately. Read-only."""
    acc = _active_account()
    if not acc:
        return jsonify({"ok": False, "error": "no active account"}), 400
    sid = (acc.get("input_spreadsheet_id") or "").strip()
    gid = str(acc.get("input_tab_gid") or "").strip()
    in_url = acc.get("input_sheet_url", "") or ""
    if not sid:
        m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", in_url)
        if m:
            sid = m.group(1)
    if not sid:
        return jsonify({"ok": False, "error": "no input sheet configured for this account"}), 400
    try:
        book = _client().open_by_key(sid)
        ws = None
        if gid.isdigit():
            try:
                ws = book.get_worksheet_by_id(int(gid))
            except Exception:
                ws = None
        if ws is None:
            ws = book.sheet1
        title = ws.title
        grid = ws.get_all_values()
        headers = grid[0] if grid else []
        rows = grid[1:] if len(grid) > 1 else []
        view_url = f"https://docs.google.com/spreadsheets/d/{sid}/edit"
        if gid.isdigit():
            view_url += f"#gid={gid}"
        return jsonify({"ok": True, "title": title, "headers": headers, "rows": rows,
                        "row_count": len(rows), "col_count": len(headers),
                        "sheet_id": sid, "gid": gid, "view_url": view_url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 500


def _records(ws, _use_cache: bool = True):
    """Like get_all_records() but tolerant of blank / duplicate header cells.
    gspread's get_all_records() raises when the header row repeats a value
    (including empty strings from trailing blank columns).

    Short-TTL cached: rapid repeated reads (dashboard refresh + sync + API run)
    were tripping Google's 'Read requests per minute' quota (HTTP 429). A 12s
    cache collapses those bursts into one read without making data look stale."""
    import time as _t
    _key = None
    try:
        _key = f"{ws.spreadsheet.id}::{ws.title}"
    except Exception:
        _key = None
    if _use_cache and _key:
        hit = _RECORDS_CACHE.get(_key)
        if hit and (_t.time() - hit[0]) < _RECORDS_TTL:
            return hit[1]
    vals = ws.get_all_values()
    if not vals:
        if _key:
            _RECORDS_CACHE[_key] = (_t.time(), [])
        return []
    headers = vals[0]
    cols, seen = [], set()
    for i, h in enumerate(headers):
        name = (h or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        cols.append((i, name))
    out = []
    for ridx, row in enumerate(vals[1:], start=2):     # row 1 = header, data starts at 2
        rec = {name: (row[i] if i < len(row) else "") for i, name in cols}
        rec["_row"] = ridx
        out.append(rec)
    if _key:
        _RECORDS_CACHE[_key] = (_t.time(), out)
    return out


@app.route("/row")
def single_row():
    """Return one row's fresh data by SKU (cache-bypassed) so the drawer can
    refresh its status/notes right after an API preview/submit."""
    sku = (request.args.get("sku") or "").strip()
    if not sku:
        return jsonify({"ok": False, "error": "missing sku"}), 400
    try:
        _bust_records_cache()                     # force a truly fresh read
        data = _records(_ws(), _use_cache=False)
        for i, r in enumerate(data):
            if str(r.get("SKU", "")).strip() == sku:
                c = _card(r)
                c["row"] = i + 2
                return jsonify({"ok": True, "row": c})
        return jsonify({"ok": False, "error": "sku not found"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/rows")
def rows():
    try:
        data  = _records(_ws())
        cards = []
        for i, r in enumerate(data):
            c = _card(r)
            c["row"] = i + 2          # actual sheet row number (row 1 = header)
            cards.append(c)
        return jsonify({"ok": True,
                        "shipping_group": _cfg().get("merchant_shipping_group", ""),
                        "product_types": _product_types(),
                        "rows": cards})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/approve", methods=["POST"])
def approve():
    body   = request.get_json(force=True) or {}
    sku    = str(body.get("sku", "")).strip()
    status = str(body.get("status", "")).strip().upper()
    if status not in _VALID_SET_STATUS:
        return jsonify({"ok": False, "error": "invalid status"}), 400
    if not sku:
        return jsonify({"ok": False, "error": "no sku"}), 400
    try:
        ws      = _ws()
        headers = ws.row_values(1)
        scol    = headers.index(STATUS_HEADER) + 1
        kcol    = headers.index(SKU_HEADER) + 1
        target  = None
        for i, v in enumerate(ws.col_values(kcol), start=1):
            if str(v).strip() == sku:
                target = i
                break
        if not target:
            return jsonify({"ok": False, "error": "sku not found in sheet"}), 404
        ws.update_cell(target, scol, status)
        _bust_records_cache()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/schema/<path:pt>")
def schema(pt):
    try:
        # The listing's OWN marketplace can be passed explicitly (?mkt=US) so the
        # right schema+creds are used regardless of the global active_marketplace.
        # This fixes US-account listings loading an empty UK schema (wrong creds).
        _mkt_param = (request.args.get("mkt") or "").strip().upper()
        _prev_mkt = _state.get("active_marketplace", "")
        if _mkt_param:
            _state["active_marketplace"] = _mkt_param
        try:
            # ?refresh=1 clears the cached schema for this product type so the new
            # (unenforced-merged) enums are re-fetched without a server restart.
            if request.args.get("refresh"):
                _mkt = str(_state.get("active_marketplace", "") or "UK").upper()
                _state["schemas"].pop(f"{pt}::{_mkt}", None)
            payload = {"ok": True, "enums": _options_for(pt), "required": _schema_required(pt),
                       "attrs": _schema_attrs(pt), "subfields": _schema_subfields(pt),
                       "titles": _load_schema(pt).get("titles", {}),
                       "marketplace": str(_state.get("active_marketplace", "") or "UK").upper(),
                       "enum_count": len(_options_for(pt)),
                       "schema_error": _load_schema(pt).get("_error", "")}
            return jsonify(payload)
        finally:
            # restore global state so a one-off schema fetch doesn't change the
            # user's active workspace marketplace
            if _mkt_param:
                _state["active_marketplace"] = _prev_mkt
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


_EDITABLE_COLS = {"Title", "Bullet 1", "Bullet 2", "Bullet 3", "Bullet 4", "Bullet 5",
                  "Description (HTML)", "Search Terms / KW", "Our Price (GBP)",
                  "Brand", "UPC", "Handling Days", "Product Type"}


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


@app.route("/genimage", methods=["POST"])
def genimage():
    """Two-stage AI main image: brief -> detailed prompt (text AI) -> image
    (image AI), using the user's selected providers and a reference image.
    Returns BOTH the detailed prompt and the image for review."""
    try:
        import ai_providers
    except Exception:
        return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
    b = request.get_json(force=True) or {}
    brief     = b.get("brief", "") or b.get("extra_prompt", "")
    ref_img   = b.get("reference_image", "") or b.get("product_image", "")
    title     = b.get("title", "")
    tprov     = b.get("text_provider") or None
    iprov     = b.get("image_provider") or None
    # resolve brand-saved reference image if requested
    if ref_img == "__BRAND_REF__":
        ref_img = ""
        try:
            import glob as _g, os as _o
            _vk = _state.get("active_view") or ""
            for _pf in _g.glob(_o.path.join(_o.path.dirname(CONFIG_PATH), "brands", "*", "profile.json")):
                _p = json.load(open(_pf, encoding="utf-8"))
                if (_p.get("brand_name") or "") == _vk:
                    ref_img = _p.get("main_image_reference", "") or ""
                    break
        except Exception:
            pass
    res = ai_providers.run_pipeline(
        _cfg(), brief=brief, reference_image=ref_img, product_title=title,
        text_provider=tprov, image_provider=iprov)
    if not res.get("ok"):
        return jsonify(res), 400
    if res.get("image_b64"):
        data_url = f"data:{res.get('mime','image/png')};base64,{res['image_b64']}"
    elif res.get("image_url"):
        data_url = res["image_url"]
    else:
        return jsonify({"ok": False, "error": "no image returned"}), 400
    # Compute pixel dimensions + byte size so the UI can show them right away.
    _w = _h = 0
    _bytes = 0
    try:
        if res.get("image_b64"):
            _raw = _b64.b64decode(res["image_b64"])
            _bytes = len(_raw)
            from PIL import Image as _PImg
            import io as _io
            _im = _PImg.open(_io.BytesIO(_raw))
            _w, _h = _im.size
    except Exception:
        _w = _h = _bytes = 0
    return jsonify({"ok": True, "data_url": data_url,
                    "detailed_prompt": res.get("detailed_prompt", ""),
                    "text_provider": res.get("text_provider"),
                    "image_provider": res.get("image_provider"),
                    "width": _w, "height": _h, "bytes": _bytes})


def _recipes_path():
    return os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "image_recipes.json")


def _load_recipes():
    try:
        if os.path.exists(_recipes_path()):
            return json.load(open(_recipes_path(), encoding="utf-8"))
    except Exception:
        pass
    return {}   # {brand_name: [ {id,name,template_image,instructions,ts}, ... ]}


def _save_recipes(data):
    try:
        json.dump(data, open(_recipes_path(), "w", encoding="utf-8"), indent=2)
        return True
    except Exception:
        return False


def _active_brand():
    """Best-effort current brand: active view/brand, else active account's first brand."""
    try:
        bv = _state.get("active_view") or _state.get("active_brand") or ""
        if bv:
            return bv
    except Exception:
        pass
    try:
        import accounts as _acc
        aid = _state.get("active_account_id", "")
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if acc:
            bl = [x for x in (acc.get("brands") or []) if x and x.strip()]
            return bl[0] if bl else (acc.get("label", "") or "")
    except Exception:
        pass
    return ""


def _miles_tpl_dir():
    d = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "miles_templates")
    os.makedirs(d, exist_ok=True)
    return d


def _miles_tpl_index_path():
    return os.path.join(_miles_tpl_dir(), "_index.json")


def _load_miles_templates():
    try:
        p = _miles_tpl_index_path()
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
    except Exception:
        pass
    return []   # [ {id,label,container,filename}, ... ]


def _save_miles_templates(data):
    try:
        json.dump(data, open(_miles_tpl_index_path(), "w", encoding="utf-8"), indent=2)
        return True
    except Exception:
        return False


@app.route("/miles_template/ai_fill", methods=["POST"])
def miles_template_ai_fill():
    """Use the AI to decide the panel text (title / grade subtitle / application)
    from the listing's title + specs. Returns a spec the UI can drop into the
    form. Body: {sku}."""
    b = request.get_json(force=True) or {}
    sku = b.get("sku", "")
    cfg = _cfg()
    key = (cfg.get("anthropic_api_key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "No anthropic_api_key in config.json"}), 400
    # gather the listing's text from the active sheet rows already loaded
    title = b.get("title", "") or ""
    bullets = b.get("bullets", "") or ""
    specs = b.get("specs", "") or ""
    if not (title or bullets or specs):
        return jsonify({"ok": False, "error": "no listing text provided"}), 400
    prompt = (
        "You lay out the text panel for a Miles Lubricants product main image. "
        "The panel has these zones, top to bottom:\n"
        "- TITLE: the product family/name, 1-3 short words (e.g. 'INDUSTRIAL GEAR OIL', 'SXR COOLANT').\n"
        "- GRADE: the single most important viscosity/grade/spec, very short (e.g. '80W-90', 'ISO 32', 'ISO VG 46').\n"
        "- (CHOICE OF MECHANICS is fixed, do not output it.)\n"
        "- APPLICATION: what the fluid IS, 1-2 short words (e.g. 'HYDRAULIC FLUID', 'COMPRESSOR FLUID', 'GEAR OIL').\n\n"
        "Rules: ALL CAPS. Keep each field SHORT so it fits a narrow panel. No brand names of other companies. "
        "No marketing sentences. Pull the grade/viscosity exactly from the product text if present.\n\n"
        f"PRODUCT TITLE: {title}\n"
        f"BULLETS/COPY: {bullets[:1200]}\n"
        f"SPECS: {specs[:800]}\n\n"
        "Return ONLY JSON, no markdown:\n"
        '{"title":"", "grade":"", "application":"", "application_lines":2}'
    )
    try:
        import anthropic as _ant
        client = _ant.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=300,
            messages=[{"role": "user", "content": prompt}])
        txt = "".join(getattr(p, "text", "") for p in msg.content).strip()
        txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
        data = json.loads(txt)
    except Exception as e:
        return jsonify({"ok": False, "error": f"AI failed: {str(e)[:200]}"}), 500
    spec = {
        "title": (data.get("title", "") or "").strip(),
        "subtitles": [{"text": (data.get("grade", "") or "").strip(), "lines": 1}],
        "application": {"text": (data.get("application", "") or "").strip(),
                        "lines": int(data.get("application_lines", 2) or 2)},
    }
    return jsonify({"ok": True, "spec": spec})


@app.route("/miles_template/list", methods=["GET"])
def miles_template_list():
    return jsonify({"ok": True, "templates": _load_miles_templates()})


@app.route("/miles_template/upload", methods=["POST"])
def miles_template_upload():
    """Save an uploaded blank template PNG and register it.
    Body: {label, container:'pail'|'drum', data:<dataURL>}"""
    b = request.get_json(force=True) or {}
    label = (b.get("label", "") or "").strip() or "Template"
    container = (b.get("container", "") or "drum").strip().lower()
    data = b.get("data", "") or ""
    if not data.startswith("data:"):
        return jsonify({"ok": False, "error": "no image data"}), 400
    try:
        head, _, raw = data.partition(",")
        mime = (re.search(r"data:([^;]+)", head) or [None, "image/png"])[1]
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")
        import time as _t
        fname = f"tpl_{container}_{int(_t.time())}.{ext}"
        with open(os.path.join(_miles_tpl_dir(), fname), "wb") as f:
            f.write(_b64.b64decode(raw))
    except Exception as e:
        return jsonify({"ok": False, "error": f"save failed: {e}"}), 500
    data_idx = _load_miles_templates()
    rid = "mt" + str(int(__import__("time").time() * 1000))
    rec = {"id": rid, "label": label, "container": container, "filename": fname}
    data_idx.append(rec)
    _save_miles_templates(data_idx)
    return jsonify({"ok": True, "template": rec})


@app.route("/miles_template/delete", methods=["POST"])
def miles_template_delete():
    b = request.get_json(force=True) or {}
    rid = b.get("id", "")
    data_idx = _load_miles_templates()
    keep, removed = [], None
    for t in data_idx:
        if t.get("id") == rid:
            removed = t
        else:
            keep.append(t)
    if removed:
        try:
            fp = os.path.join(_miles_tpl_dir(), removed.get("filename", ""))
            if os.path.exists(fp):
                os.remove(fp)
        except Exception:
            pass
    _save_miles_templates(keep)
    return jsonify({"ok": True})


@app.route("/miles_template/preview/<rid>")
def miles_template_preview(rid):
    """Serve a stored blank template image."""
    for t in _load_miles_templates():
        if t.get("id") == rid:
            return send_from_directory(_miles_tpl_dir(), t.get("filename", ""))
    return ("not found", 404)


@app.route("/miles_template/save_zones", methods=["POST"])
def miles_template_save_zones():
    """Persist the text-zone rectangles (from the visual editor) for a template.
    Body: {id, zones:{title:[x0,y0,x1,y1], grade:[...], choice:[...], application:[...]}}
    Coordinates are fractions 0..1 of the image."""
    b = request.get_json(force=True) or {}
    rid = b.get("id", "")
    zones = b.get("zones", {}) or {}
    erase = b.get("erase", []) or []
    data_idx = _load_miles_templates()
    found = False
    for t in data_idx:
        if t.get("id") == rid:
            t["zones"] = zones
            t["erase"] = erase
            found = True
            break
    if not found:
        return jsonify({"ok": False, "error": "template not found"}), 404
    _save_miles_templates(data_idx)
    return jsonify({"ok": True})


@app.route("/miles_template/render", methods=["POST"])
def miles_template_render():
    """Render text onto a chosen blank template and save the result as a main
    image for the given SKU (scoped to the active account).
    Body: {template_id, sku, spec:{title,subtitles,application,container,...}}"""
    try:
        import miles_template as _mt
    except Exception as e:
        return jsonify({"ok": False, "error": f"miles_template import failed: {e}"}), 500
    b = request.get_json(force=True) or {}
    tid = b.get("template_id", "")
    sku = b.get("sku", "") or "_misc"
    spec = b.get("spec", {}) or {}
    tpl = next((t for t in _load_miles_templates() if t.get("id") == tid), None)
    if not tpl:
        return jsonify({"ok": False, "error": "template not found — upload one first"}), 404
    blank_path = os.path.join(_miles_tpl_dir(), tpl.get("filename", ""))
    if not os.path.exists(blank_path):
        return jsonify({"ok": False, "error": "template file missing"}), 404
    spec.setdefault("container", tpl.get("container", "drum"))
    # Use the template's saved zones (from the visual editor) unless the caller
    # passed explicit ones. This is what makes placement pixel-exact per template.
    if not spec.get("zones") and tpl.get("zones"):
        spec["zones"] = tpl["zones"]
    if not spec.get("erase") and tpl.get("erase"):
        spec["erase"] = tpl["erase"]
    try:
        png = _mt.render_onto_blank(blank_path, spec)
    except Exception as e:
        return jsonify({"ok": False, "error": f"render failed: {e}"}), 500
    # save into the account-scoped media library for this SKU
    try:
        import time as _t
        # name the file by its REAL format (sniffed from bytes), not a hardcoded
        # .png -- Amazon rejects a .png whose bytes are actually JPEG.
        _ext = _sniff_image_ext(png, "png")
        fname = f"main_{int(_t.time())}.{_ext}"
        d = _sku_dir(sku)
        with open(os.path.join(d, fname), "wb") as f:
            f.write(png)
        aid = _state.get("active_account_id", "") or ""
        pfx = f"/media/_acct/{_safe_sku(aid)}" if aid else "/media"
        url = f"{pfx}/{_safe_sku(sku)}/{fname}"
        # Return a SMALL thumbnail for instant preview (not the full 2616px image
        # as base64 -- that bloats the response and the browser). The full image
        # is loaded from `url`.
        data_url = ""
        try:
            from PIL import Image as _PImg
            import io as _io
            thumb = _PImg.open(_io.BytesIO(png)).convert("RGB")
            thumb.thumbnail((520, 520))
            buf = _io.BytesIO()
            thumb.save(buf, format="JPEG", quality=82)
            data_url = "data:image/jpeg;base64," + _b64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            data_url = ""
        return jsonify({"ok": True, "url": url, "data_url": data_url})
    except Exception as e:
        return jsonify({"ok": False, "error": f"save failed: {e}"}), 500


# ---- strategy prompts for the creative (non-templated) main-image path ----
_CREATIVE_STRATEGIES = {
    "hero_straight": (
        "A clean, premium straight-on Amazon MAIN hero: 100% pure solid white background "
        "(RGB 255,255,255) edge to edge, the product shot straight-on at eye level, centered and "
        "filling 85%+ of the frame, crisp high-definition studio photography, even soft 5500K lighting, "
        "a subtle natural contact shadow. The classic confidence shot. No text, no props, no people, "
        "1:1 square."),
    "hero_angle": (
        "The SAME product on a 100% pure white background (RGB 255,255,255), but captured from a "
        "flattering creative camera angle — a slightly elevated three-quarter / 30-45 degree hero angle "
        "that shows the front and a hint of the side/top for depth and a premium feel. Product fills "
        "85%+ of the frame, sharp HD studio quality, soft directional lighting with a gentle contact "
        "shadow and a subtle highlight to make it pop. The angle should make the product look desirable "
        "and 'hero', the way top Amazon brands shoot. Pure white only — no scene, no props, no text. "
        "1:1 square."),
    "hero_personality": (
        "The SAME product on a 100% pure white background (RGB 255,255,255), styled to feel alive and "
        "attractive so it draws the customer in. Use a dynamic camera angle and product positioning that "
        "gives it personality and makes it the 'hero'. ADD a tasteful creative touch that suits the "
        "product and makes it look premium and desirable — for example fresh water droplets or condensation "
        "on the surface, a soft splash, a light dusting, gentle steam, or a dramatic highlight — whatever "
        "best fits THIS product. Beautiful soft studio lighting, a crisp highlight, and a natural contact "
        "shadow. Think like a world-class product photographer making this item irresistible while keeping "
        "it on plain white. The creative element must enhance, never cover or obscure the product or its "
        "label. Product fills 85%+, sharp HD, 1:1 square. Pure white background only — no scene, no added "
        "text, no people."),
}


@app.route("/genimage/strategize", methods=["POST"])
def genimage_strategize():
    """Run the strategist AI: it invents conversion-focused image concepts for the
    product (thinking like a strategist + customer). Returns concepts to choose from."""
    try:
        import ai_providers
    except Exception:
        return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
    b = request.get_json(force=True) or {}
    product_image = b.get("product_image", "") or b.get("reference_image", "")
    title = b.get("title", "")
    kind = b.get("kind", "main")          # 'main' | 'secondary'
    n = int(b.get("n", 3) or 3)
    tprov = b.get("text_provider") or None
    # per-run custom instructions for the strategist (NOT the saved standing
    # instructions) -- e.g. "don't show pets", "pour the medicine into the tub in
    # one image", "show the product in only some images". Optional, not persisted.
    custom_instr = (b.get("custom_instructions", "") or b.get("strategist_instructions", "") or "").strip()
    if not product_image:
        return jsonify({"ok": False, "error": "This product has no reference image."}), 400
    # read the product first so the strategist's ideas fit the real item
    spec = ""
    try:
        d = ai_providers.describe_product(_cfg(), product_image, title, provider=tprov)
        if d.get("ok"):
            spec = d.get("description", "")
    except Exception:
        spec = ""
    res = ai_providers.strategize_images(_cfg(), image=product_image, product_title=title,
                                         product_spec=spec, n=n, kind=kind, provider=tprov,
                                         custom_instructions=custom_instr)
    if not res.get("ok"):
        return jsonify({"ok": False, "error": res.get("error", "strategist failed")}), 400
    return jsonify({"ok": True, "concepts": res.get("concepts", []), "product_spec": spec})


@app.route("/genimage/from_concept", methods=["POST"])
def genimage_from_concept():
    """Generate an image from a strategist concept's art direction. Keeps the
    product faithful via the reference image + low strength."""
    try:
        import ai_providers
    except Exception:
        return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
    b = request.get_json(force=True) or {}
    product_image = b.get("product_image", "") or b.get("reference_image", "")
    title = b.get("title", "")
    kind = b.get("kind", "main")
    art = (b.get("art_direction", "") or "").strip()
    concept = (b.get("concept", "") or "").strip()
    tprov = b.get("text_provider") or None
    iprov = b.get("image_provider") or None
    fid = (b.get("fidelity", "high") or "high").lower()
    strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(fid, 0.2)
    # A+/secondary scenes push the model to redraw the product to fit the scene,
    # which drifts it from the real item. For these (non-main) kinds on High
    # fidelity, use an even LOWER strength so the product stays locked to the
    # reference photo (only the scene around it changes).
    if kind in ("aplus", "secondary") and fid == "high":
        strength = 0.14
    if not product_image:
        return jsonify({"ok": False, "error": "This product has no reference image."}), 400
    if not art and not concept:
        return jsonify({"ok": False, "error": "No concept provided."}), 400
    if kind == "main":
        brief = (
            "Create an Amazon MAIN product image on a 100% pure white background (RGB 255,255,255), "
            "product filling 85%+, NO added text or logos. Realise this creative concept: "
            f"{concept}. Art direction: {art}. Keep the product itself identical to the reference image "
            "(same shape, colours, label, text); the creativity is in angle, lighting, positioning and "
            "any tasteful physical touch — never alter or cover the product or its label."
        )
        image_kind = "main"
    elif kind == "aplus":
        brief = (
            "Create an Amazon A+ CONTENT module image (text and graphics allowed; this is the enhanced "
            "brand-story section). Realise this concept: "
            f"{concept}. Art direction: {art}. CRITICAL PRODUCT FIDELITY: the product shown MUST be an "
            "EXACT reproduction of the attached reference photo — identical shape, proportions, colour, "
            "materials, buttons, and every line of label/branding text. Do NOT redesign, restyle, or "
            "re-imagine the product to fit the scene; place the REAL product into the scene unchanged. "
            "Build the module layout/scene around it, roughly 70% visual / 30% text, premium and "
            "uncluttered, with one clear headline idea. Do NOT make prohibited medical/efficacy claims."
        )
        image_kind = "aplus"
    else:
        brief = (
            "Create an Amazon SECONDARY image (text and graphics allowed). Realise this concept: "
            f"{concept}. Art direction: {art}. CRITICAL PRODUCT FIDELITY: the product shown MUST be an "
            "EXACT reproduction of the attached reference photo — identical shape, proportions, colour, "
            "materials, buttons, and every line of label/branding text. Do NOT redesign or re-imagine the "
            "product to fit the scene; place the REAL product into the scene unchanged. Build the "
            "scene/graphic around it. Premium, clean, one clear message."
        )
        image_kind = "secondary"
    # standing user instructions remembered for every image
    _ci2 = (b.get("custom_instructions", "") or "").strip() or _load_img_instructions()
    if _ci2:
        brief = brief + "\n\nUSER STANDING INSTRUCTIONS (must always be followed): " + _ci2
    # For A+ concepts from the strategist, resize to the tier's standard module
    # dimensions (basic 970×600, premium 1464×600) so the output is upload-ready.
    _tw = _th = 0
    if kind == "aplus":
        _tier = (b.get("tier", "basic") or "basic").lower()
        if _tier == "premium":
            _tw, _th = 1464, 600
        else:
            _tw, _th = 970, 600
    # For A+/secondary, anchor the REAL product as a SECOND reference too (same
    # technique the refine path uses) so the model is doubly pinned to the actual
    # product and is far less likely to invent a generic look-alike.
    _extra_ref = product_image if kind in ("aplus", "secondary") else ""
    res = ai_providers.run_pipeline(_cfg(), brief=brief, reference_image=product_image,
                                    product_title=title, text_provider=tprov, image_provider=iprov,
                                    image_kind=image_kind, strength=strength,
                                    target_w=_tw, target_h=_th, extra_reference=_extra_ref)
    if not res.get("ok"):
        return jsonify(res), 400
    return _imgresult(res, extra={"concept": concept})


@app.route("/genimage/refine", methods=["POST"])
def genimage_refine():
    """Refine an ALREADY-generated image with a small user instruction.
    Feeds the generated image back in as the reference and applies the change at
    HIGH fidelity (low strength) so only the requested tweak is made and the rest
    of the image/product stays as-is. Works for main, secondary and aplus."""
    try:
        import ai_providers
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    b = request.get_json(force=True) or {}
    base_image = b.get("image", "") or b.get("reference_image", "") or b.get("product_image", "")
    orig_ref = b.get("original_reference", "") or b.get("product_reference", "")
    instruction = (b.get("instruction", "") or "").strip()
    title = b.get("title", "")
    kind = (b.get("kind", "main") or "main").lower()
    if kind == "concept":
        kind = "main"
    if kind not in ("main", "secondary", "aplus"):
        kind = "main"
    tprov = b.get("text_provider") or None
    iprov = b.get("image_provider") or None
    if not base_image:
        return jsonify({"ok": False, "error": "No image to refine."}), 400
    if not instruction:
        return jsonify({"ok": False, "error": "Tell me what to change."}), 400
    # refine is always high-fidelity: we want the SAME image with one small change
    _strength = 0.18
    kind_rules = {
        "main": "This is an Amazon MAIN image: keep the 100% pure white background, no added text/logos.",
        "secondary": "This is an Amazon SECONDARY image: text and graphics are allowed.",
        "aplus": "This is an Amazon A+ module: text and graphics allowed, ~70% visual / 30% text, no prohibited claims.",
    }[kind]
    # When we have the ORIGINAL product image, attach it as a second reference and
    # tell the model it is the source of truth for the product itself -- so the
    # edit can't drift the real product (shape, colours, label text).
    if orig_ref:
        brief = (
            "You are given TWO reference images: (1) the CURRENT image to edit, and (2) the ORIGINAL "
            "product photo. Make a SMALL, TARGETED edit to image (1) — keep its composition, layout and "
            "background the same and change ONLY what is asked. CRITICAL: the product must match the "
            "ORIGINAL product photo (2) EXACTLY — same shape, proportions, colours, gradient, logo and "
            "every line of label text. Do not let the edit alter the real product. "
            f"Requested change: {instruction}. {kind_rules}"
        )
    else:
        brief = (
            "Make a SMALL, TARGETED edit to the attached image. Keep everything else exactly the same — "
            "same product, same composition, same colours, same layout — and change ONLY what is asked. "
            f"Requested change: {instruction}. {kind_rules} Do not redesign or re-pose the product."
        )
    _ciR = (b.get("custom_instructions", "") or "").strip() or _load_img_instructions()
    if _ciR:
        brief = brief + "\n\nAlso keep honoring these standing rules where relevant (do not let them override the requested change): " + _ciR
    res = ai_providers.run_pipeline(
        _cfg(), brief=brief, reference_image=base_image, product_title=title,
        text_provider=tprov, image_provider=iprov, image_kind=kind,
        read_product=False, strength=_strength, extra_reference=orig_ref)
    if not res.get("ok"):
        return jsonify(res), 400
    return _imgresult(res, extra={"refined": True, "instruction": instruction})


@app.route("/genimage/process_source", methods=["POST"])
def genimage_process_source():
    """Process a SOURCE image (eBay/Amazon competitor scrape OR brand CSV) into a
    clean, Amazon-ready MAIN image that keeps the product IDENTICAL.
    Logo rule driven by source:
      - source='competitor' (eBay/Amazon): remove any brand logo IF present (clean
        the area to blend with the product surface), keep the product itself.
      - source='brand' (CSV): keep the product AND logo (preserve_logo defaults True);
        if preserve_logo is False, remove the logo as above.
    Optional 'instruction' for extra edits. Product stays faithful (low strength)."""
    try:
        import ai_providers
    except Exception:
        return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
    b = request.get_json(force=True) or {}
    product_image = b.get("product_image", "") or b.get("reference_image", "")
    title = b.get("title", "")
    source = (b.get("source", "competitor") or "competitor").lower()   # 'competitor' | 'brand'
    preserve_logo = b.get("preserve_logo", True)
    instruction = (b.get("instruction", "") or "").strip()
    tprov = b.get("text_provider") or None
    iprov = b.get("image_provider") or None
    fid = (b.get("fidelity", "high") or "high").lower()
    strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(fid, 0.2)

    if not product_image:
        return jsonify({"ok": False, "error": "No source image to process."}), 400

    # decide the logo rule
    remove_logo = (source == "competitor") or (not preserve_logo)

    # read the actual product first (faithful spec, incl. any logo/text)
    spec = ""
    try:
        d = ai_providers.describe_product(_cfg(), product_image, title, provider=tprov)
        if d.get("ok"):
            spec = d.get("description", "")
    except Exception:
        spec = ""

    if remove_logo:
        logo_rule = (
            "LOGO RULE: If the product/packaging shows a BRAND LOGO, brand name, or store branding, "
            "REMOVE it cleanly — erase the logo and blend that area to match the surrounding product "
            "surface (same colour, material, finish), as if the logo was never there. Do NOT replace it "
            "with any other text or logo; leave it clean. If there is NO logo present, simply keep the "
            "product exactly as-is. Keep ALL other product details — shape, colours, proportions, "
            "material, and any NON-branding text (like size, directions) — unchanged."
        )
    else:
        logo_rule = (
            "LOGO RULE: KEEP the product's own brand logo and all its label text exactly as shown — this "
            "is the brand's real product. Reproduce the logo, brand name, and all text faithfully."
        )

    brief = (
        "Produce a clean, professional Amazon MAIN product image from the reference image. "
        "Background must be 100% pure white (RGB 255,255,255), product filling 85%+, sharp HD, 1:1 square, "
        "no added text or graphics. Keep the PRODUCT itself identical to the reference (same shape, "
        "colours, proportions, material, design). " + logo_rule
        + (f" Additional edits requested by the seller: {instruction}." if instruction else "")
    )
    if spec:
        brief += ("\n\nEXACT PRODUCT SPEC (reproduce the product precisely from this; apply the LOGO RULE "
                  "above to any branding):\n" + spec)
    res = ai_providers.run_pipeline(_cfg(), brief=brief, reference_image=product_image,
                                    product_title=title, text_provider=tprov, image_provider=iprov,
                                    image_kind="main", strength=strength, read_product=False)
    if not res.get("ok"):
        return jsonify(res), 400
    return _imgresult(res, extra={"source": source, "logo_removed": remove_logo})


@app.route("/genimage/recipe", methods=["POST"])
def genimage_recipe():
    """Generate a MAIN image for ONE product using a saved recipe (templated path)
    OR a creative strategy (non-templated path). Always passes the product's own
    reference image so the product stays faithful. Returns the image for review."""
    try:
        import ai_providers
    except Exception:
        return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
    b = request.get_json(force=True) or {}
    product_image = b.get("product_image", "") or b.get("reference_image", "")
    title = b.get("title", "")
    mode = b.get("mode", "recipe")          # 'recipe' | 'creative'
    tprov = b.get("text_provider") or None
    iprov = b.get("image_provider") or None
    inspiration = (b.get("inspiration", "") or "").strip()   # optional creative inspiration text/url
    # fidelity: how closely to keep the real product (lower strength = more faithful).
    # 'high' = very faithful (0.2), 'medium' = balanced (0.35), 'creative' = more freedom (0.55)
    fid = (b.get("fidelity", "high") or "high").lower()
    strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(fid, 0.2)

    if not product_image:
        return jsonify({"ok": False, "error": "This product has no reference image to base the generation on."}), 400

    if mode == "recipe":
        brand = (b.get("brand", "") or _active_brand()).strip()
        rid = b.get("recipe_id", "")
        data = _load_recipes()
        rec = None
        for bn, lst in data.items():
            for r in lst:
                if r.get("id") == rid:
                    rec = r; break
            if rec:
                break
        if not rec:
            return jsonify({"ok": False, "error": "Recipe not found."}), 404
        brief = (
            "Apply this exact treatment to the product shown in the reference image, keeping the "
            "product itself identical (same shape, colour, label, text — do NOT redesign it). "
            f"Treatment: {rec['instructions']}"
        )
        # if the recipe has a template image, mention it (gen model uses product ref as the anchor)
        res = ai_providers.run_pipeline(_cfg(), brief=brief, reference_image=product_image,
                                        product_title=title, text_provider=tprov, image_provider=iprov, strength=strength)
        if not res.get("ok"):
            return jsonify(res), 400
        return _imgresult(res, extra={"recipe_id": rid})

    # creative path: generate the 3 strategies (or whichever requested)
    strat = b.get("strategy", "")
    if strat and strat in _CREATIVE_STRATEGIES:
        brief = (_CREATIVE_STRATEGIES[strat]
                 + " Keep the product itself identical to the reference image (same shape, colour, "
                   "label and text); only change the scene, angle, lighting and composition."
                 + (f" Inspiration to draw from: {inspiration}" if inspiration else ""))
        res = ai_providers.run_pipeline(_cfg(), brief=brief, reference_image=product_image,
                                        product_title=title, text_provider=tprov, image_provider=iprov, strength=strength)
        if not res.get("ok"):
            return jsonify(res), 400
        return _imgresult(res, extra={"strategy": strat})

    return jsonify({"ok": False, "error": "Specify a recipe_id or a creative strategy."}), 400


def _imgresult(res, extra=None):
    if res.get("image_b64"):
        data_url = f"data:{res.get('mime','image/png')};base64,{res['image_b64']}"
    elif res.get("image_url"):
        data_url = res["image_url"]
    else:
        return jsonify({"ok": False, "error": "no image returned"}), 400
    out = {"ok": True, "data_url": data_url,
           "detailed_prompt": res.get("detailed_prompt", ""),
           "text_provider": res.get("text_provider"),
           "image_provider": res.get("image_provider")}
    if extra:
        out.update(extra)
    return jsonify(out)


@app.route("/genimage/save_to_media", methods=["POST"])
def genimage_save_to_media():
    """Save a generated image (data URL) into a SKU's media library."""
    b = request.get_json(force=True) or {}
    sku = b.get("sku", "_misc")
    data = b.get("data_url", "") or b.get("data", "")
    if not data:
        return jsonify({"ok": False, "error": "no image"}), 400
    if data.startswith("data:"):
        head, _, raw = data.partition(",")
        mime = (re.search(r"data:([^;]+)", head) or [None, "image/png"])[1]
    else:
        raw, mime = data, "image/png"
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")
    import time as _t
    fname = f"generated_{int(_t.time())}.{ext}"
    try:
        with open(os.path.join(_sku_dir(sku), fname), "wb") as f:
            f.write(_b64.b64decode(raw))
    except Exception as e:
        return jsonify({"ok": False, "error": f"write failed: {e}"}), 500
    _aid = _state.get("active_account_id", "") or ""
    _pfx = f"/media/_acct/{_safe_sku(_aid)}" if _aid else "/media"
    return jsonify({"ok": True, "url": f"{_pfx}/{_safe_sku(sku)}/{fname}"})


# ---- secondary image roles: each role has ONE job (clean, premium) ----
_SECONDARY_ROLES = {
    "benefit": ("A single-benefit infographic image: show ONE clear product benefit with a short bold "
                "headline (a few words only) and a clean visual that proves it. Lots of negative space, "
                "premium minimal look — NOT cluttered with text."),
    "feature": ("A feature/spec callout: highlight one key feature or what's-in-the-box with a clean "
                "labelled visual and minimal text."),
    "lifestyle": ("A lifestyle in-use image: the product being used in a real, aspirational setting that "
                  "fits its purpose, warm natural light, emotional and premium, minimal or no text."),
    "dimensions": ("A size/dimensions image: show the product scale or measurements clearly with subtle "
                   "clean callout lines, on a simple background, minimal text."),
    "trust": ("A trust/quality image: convey durability, materials or guarantee with a clean confident "
              "visual and at most a short phrase."),
    "comparison": ("A subtle 'why choose us' image contrasting a desirable outcome vs a poor one, clean "
                   "and tasteful, minimal text — no competitor brands."),
}


@app.route("/genimage/secondary_v2", methods=["POST"])
def genimage_secondary_v2():
    """Generate ONE secondary image for a product. Supports:
    - role (benefit/feature/lifestyle/...) OR free-form instruction
    - benefit_count (1 or 2) to control how many benefits are highlighted
    - competitor refs with mode 'describe' (vision AI extracts style) or 'direct'
      (competitor image passed to the image model as a style reference)
    Always passes the product's own image so the product stays faithful."""
    try:
        import ai_providers
    except Exception:
        return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
    b = request.get_json(force=True) or {}
    product_image = b.get("product_image", "") or b.get("reference_image", "")
    title = b.get("title", "")
    role = b.get("role", "")                       # one of _SECONDARY_ROLES, or "" for free-form
    free_instruction = (b.get("instruction", "") or "").strip()
    benefit_count = int(b.get("benefit_count", 1) or 1)
    benefit_text = (b.get("benefit_text", "") or "").strip()   # optional specific benefit(s) to show
    comp_refs = b.get("competitor_refs", []) or []  # [{image, mode}]
    comp_mode = b.get("competitor_mode", "describe")  # default mode if not per-ref
    tprov = b.get("text_provider") or None
    # respect the user's fidelity choice so the product is kept as faithfully
    # as the main images (default High = most faithful)
    _fid = (b.get("fidelity", "high") or "high").lower()
    _strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(_fid, 0.2)
    iprov = b.get("image_provider") or None

    if not product_image:
        return jsonify({"ok": False, "error": "This product has no reference image."}), 400

    # 1) build the role/free-form brief
    if role and role in _SECONDARY_ROLES:
        brief = _SECONDARY_ROLES[role]
    elif free_instruction:
        brief = free_instruction
    else:
        brief = _SECONDARY_ROLES["benefit"]

    # benefit restraint (the user wants clean, premium — 1-2 benefits max)
    if benefit_count <= 1:
        brief += " Highlight EXACTLY ONE benefit. Keep text to a single short headline."
    else:
        brief += " Highlight at most TWO benefits, each with a very short label. Do not overcrowd."
    if benefit_text:
        brief += f" The benefit(s) to highlight: {benefit_text}."
    brief += (" Keep the product itself identical to the reference image (same shape, colour, label, "
              "text); only build the scene/graphic around it. Premium, clean, lots of negative space.")

    # 2) competitor style handling
    style_desc = ""
    direct_refs = []
    describe_imgs = []
    for cr in comp_refs[:3]:
        img = cr.get("image", "") if isinstance(cr, dict) else str(cr)
        mode = (cr.get("mode") if isinstance(cr, dict) else "") or comp_mode
        if not img:
            continue
        if mode == "direct":
            direct_refs.append(img)
        else:
            describe_imgs.append(img)
    if describe_imgs:
        d = ai_providers.describe_image(_cfg(), describe_imgs, focus="style to reproduce on a different product", provider=tprov)
        if d.get("ok"):
            style_desc = d.get("description", "")
    if style_desc:
        brief += (" Reproduce THIS visual style/technique (from competitor inspiration), applied to the "
                  "seller's own product — do not copy their product or branding: " + style_desc)

    # 3) generate: prompt AI -> image AI, with product reference (+ direct competitor refs if any)
    # read the actual product first so the model keeps it faithful (exact label text, shape)
    try:
        _pdesc = ai_providers.describe_product(_cfg(), product_image, title, provider=tprov)
        if _pdesc.get("ok") and _pdesc.get("description"):
            brief += ("\n\nEXACT PRODUCT SPEC (reproduce the product precisely — same shape, colours, "
                      "layout, logo, and ALL label text exactly as written; do not alter it):\n"
                      + _pdesc["description"])
    except Exception:
        pass
    # standing user instructions (remembered for every image), applied last so
    # they always take effect on top of the strategist + product spec.
    _ci = (b.get("custom_instructions", "") or "").strip() or _load_img_instructions()
    if _ci:
        brief += "\n\nUSER STANDING INSTRUCTIONS (must always be followed): " + _ci
    enh = ai_providers.enhance_prompt(_cfg(), brief, title, provider=tprov, image_kind="secondary")
    if not enh.get("ok"):
        return jsonify({"ok": False, "error": "Prompt stage: " + enh.get("error", "")}), 400
    detailed = enh["prompt"]
    # image model takes the product image as the anchor reference; if direct competitor
    # refs were supplied, mention them in the prompt (most models accept one primary ref)
    gen = ai_providers.generate_image(_cfg(), detailed, reference_image=product_image, provider=iprov, strength=_strength, image_size="4K")
    if not gen.get("ok"):
        return jsonify({"ok": False, "error": "Image stage: " + gen.get("error", "")}), 400
    res = {"ok": True, "detailed_prompt": detailed,
           "text_provider": enh.get("provider"), "image_provider": gen.get("provider")}
    if gen.get("image_b64"):
        res["image_b64"] = gen["image_b64"]; res["mime"] = gen.get("mime", "image/png")
    elif gen.get("image_url"):
        res["image_url"] = gen["image_url"]
    return _imgresult(res, extra={"role": role or "custom"})


# ============ A+ CONTENT ============
# Amazon A+ module catalog with EXACT pixel dimensions (2025 specs).
# basic = available to all Brand Registered sellers; premium = wider canvas,
# requires Premium A+ access (Brand Story on all ASINs + 15 approved submissions).
_APLUS_MODULES = {
    "basic": [
        {"id": "logo", "name": "Brand logo", "w": 600, "h": 180,
         "desc": "Small brand logo strip. Clean, centered, no tagline."},
        {"id": "image_header_text", "name": "Standard Image Header with Text", "w": 970, "h": 600,
         "desc": "Large header banner with a short headline and supporting text — great at the very top."},
        {"id": "text_header", "name": "Image header (no text overlay)", "w": 970, "h": 300,
         "desc": "A wide visual divider between sections; pure imagery, no text."},
        {"id": "three_image_text", "name": "Three images & text", "w": 300, "h": 300,
         "desc": "Three side-by-side images (angles, benefits, or use cases) each with a short caption."},
        {"id": "four_quadrant", "name": "Four-image highlight (text)", "w": 220, "h": 220,
         "desc": "Four small square images with text — four features or four benefits."},
        {"id": "sidebar_main", "name": "Image sidebar (main)", "w": 300, "h": 300,
         "desc": "Single main image with a sidebar of detail; pairs with 100x100 thumbnails."},
        {"id": "sidebar_thumb", "name": "Image sidebar (thumbnail)", "w": 100, "h": 100,
         "desc": "Small thumbnail used inside a sidebar module."},
        {"id": "single_image_highlight", "name": "Single image & highlights", "w": 300, "h": 300,
         "desc": "One feature image beside a bulleted highlight list."},
        {"id": "comparison", "name": "Comparison chart image", "w": 150, "h": 300,
         "desc": "One product image per column for the comparison chart — same angle, clean white background."},
    ],
    "premium": [
        {"id": "premium_full", "name": "Premium full-width module", "w": 1464, "h": 600,
         "desc": "Full-width immersive banner (Apple-style). Premium A+ only."},
        {"id": "premium_header", "name": "Premium image header", "w": 1464, "h": 600,
         "desc": "Premium wide header with short headline; lots of visual impact."},
        {"id": "premium_three", "name": "Premium three-image & text", "w": 488, "h": 600,
         "desc": "Three wide images with captions across the full premium canvas."},
    ],
}


@app.route("/aplus/modules", methods=["GET"])
def aplus_modules():
    """Return the A+ module catalog (basic + premium) with exact dimensions."""
    return jsonify({"ok": True, "modules": _APLUS_MODULES})


@app.route("/aplus/generate", methods=["POST"])
def aplus_generate():
    """Generate ONE A+ Content module image at its exact Amazon dimensions, plus
    the suggested module text (70% visual / 30% text). Always passes the product
    reference image. Body: {product_image, title, tier, module_id, instruction,
    benefit_text}."""
    try:
        import ai_providers
    except Exception:
        return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
    b = request.get_json(force=True) or {}
    product_image = b.get("product_image", "") or b.get("reference_image", "")
    title = b.get("title", "")
    tier = b.get("tier", "basic")
    module_id = b.get("module_id", "")
    instruction = (b.get("instruction", "") or "").strip()
    benefit_text = (b.get("benefit_text", "") or "").strip()
    tprov = b.get("text_provider") or None
    # respect the user's fidelity choice so the product is kept as faithfully
    # as the main images (default High = most faithful)
    _fid = (b.get("fidelity", "high") or "high").lower()
    _strength = {"high": 0.2, "medium": 0.35, "creative": 0.55}.get(_fid, 0.2)
    iprov = b.get("image_provider") or None

    if not product_image:
        return jsonify({"ok": False, "error": "This product has no reference image."}), 400
    mod = None
    for m in _APLUS_MODULES.get(tier, []):
        if m["id"] == module_id:
            mod = m; break
    if not mod:
        return jsonify({"ok": False, "error": "Unknown A+ module."}), 404

    brief = (
        f"Design an Amazon A+ Content module: '{mod['name']}'. {mod['desc']} "
        f"EXACT output size: {mod['w']}x{mod['h']} pixels (aspect ratio {mod['w']}:{mod['h']}). "
        "Follow the 70% visual / 30% text rule, keep text short and readable on mobile, premium and clean. "
        + (f"Seller's instruction: {instruction}. " if instruction else "")
        + (f"Benefit(s) to feature: {benefit_text}. " if benefit_text else "")
    )
    # read the actual product first so A+ keeps it faithful
    # Multi-image modules (three/four small images) are the ones that drift: asking
    # the model to render the product several times at small size makes it invent a
    # generic stand-in. For these, lower the strength hard and instruct it to reuse
    # the SAME exact product in every sub-image rather than redrawing variations.
    _multi_image_mods = {"three_image_text", "four_quadrant"}
    if _fid == "high":
        _strength = 0.12 if module_id in _multi_image_mods else 0.16
    if module_id in _multi_image_mods:
        brief += (
            " CRITICAL: every sub-image in this module must show the SAME identical product from the "
            "attached reference — do NOT invent variations or a generic look-alike; reuse the exact same "
            "product (same shape, colour, proportions, label text), only changing angle or context "
            "between the small images."
        )
    try:
        _pdesc = ai_providers.describe_product(_cfg(), product_image, title, provider=tprov)
        if _pdesc.get("ok") and _pdesc.get("description"):
            brief += ("\n\nEXACT PRODUCT SPEC (reproduce the product precisely — same shape, colours, "
                      "layout, logo, and ALL label text exactly as written):\n" + _pdesc["description"])
    except Exception:
        pass
    _ci3 = (b.get("custom_instructions", "") or "").strip() or _load_img_instructions()
    if _ci3:
        brief = brief + "\n\nUSER STANDING INSTRUCTIONS (must always be followed): " + _ci3
    enh = ai_providers.enhance_prompt(_cfg(), brief, title, provider=tprov, image_kind="aplus")
    if not enh.get("ok"):
        return jsonify({"ok": False, "error": "Prompt stage: " + enh.get("error", "")}), 400
    detailed = enh["prompt"] + f"\n\nIMPORTANT: output the image at exactly {mod['w']}x{mod['h']} pixels."
    _ar = ai_providers._closest_aspect_ratio(mod["w"], mod["h"])
    gen = ai_providers.generate_image(_cfg(), detailed, reference_image=product_image,
                                      provider=iprov, strength=_strength,
                                      aspect_ratio=_ar, image_size="4K",
                                      extra_reference=product_image)
    if not gen.get("ok"):
        return jsonify({"ok": False, "error": "Image stage: " + gen.get("error", "")}), 400
    # EXACT-DIMENSION RESIZE: the model returns ~square 4K regardless of the prompt;
    # cover-crop + resize to the module's exact Amazon pixels so it's not rejected.
    if gen.get("image_b64"):
        try:
            gen["image_b64"] = ai_providers._resize_to_exact(gen["image_b64"], int(mod["w"]), int(mod["h"]))
            gen["mime"] = "image/png"
            gen["resized_to"] = f"{mod['w']}x{mod['h']}"
        except Exception as _re:
            gen["resize_error"] = str(_re)[:120]

    # also draft the module copy (separate from the image, so text is reliable)
    copy_text = ""
    try:
        key = (_cfg().get("anthropic_api_key") or "").strip()
        if key:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-sonnet-4-5", max_tokens=400,
                system=("Write concise Amazon A+ module copy: one short headline (<=8 words) and "
                        "2-3 short benefit-led sentences. No claims like 'best seller', '#1', pricing, "
                        "or external links. Return JSON {\"headline\":\"\",\"body\":\"\"} only."),
                messages=[{"role": "user", "content": f"Product: {title}\nModule: {mod['name']}\n"
                           f"Benefit(s): {benefit_text or '(infer sensible benefits)'}"}])
            raw = "".join(getattr(x, "text", "") for x in msg.content).strip()
            raw = re.sub(r"^```json|```$", "", raw).strip()
            copy_text = raw
    except Exception:
        copy_text = ""

    res = {"ok": True, "detailed_prompt": detailed,
           "text_provider": enh.get("provider"), "image_provider": gen.get("provider"),
           "module": mod, "copy": copy_text}
    if gen.get("image_b64"):
        res["image_b64"] = gen["image_b64"]; res["mime"] = gen.get("mime", "image/png")
    elif gen.get("image_url"):
        res["image_url"] = gen["image_url"]
    return _imgresult(res, extra={"module_id": module_id, "module": mod, "copy": copy_text})


def _write_attrs_for_sku(ws, sku, attrs):
    """Overwrite the Attributes JSON cell for a given SKU with the provided dict."""
    headers = ws.row_values(1)
    if "Attributes JSON" not in headers:
        raise RuntimeError("no attributes column")
    kcol = headers.index(SKU_HEADER) + 1
    trow = None
    for i, v in enumerate(ws.col_values(kcol), start=1):
        if str(v).strip() == str(sku).strip():
            trow = i
            break
    if not trow:
        raise RuntimeError("sku not found")
    acol = headers.index("Attributes JSON") + 1
    ws.update_cell(trow, acol, json.dumps(attrs, ensure_ascii=False))
    _bust_records_cache()


@app.route("/genimage/secondary", methods=["POST"])
def genimage_secondary():
    """Generate secondary images ONCE from a brief and apply the same set across
    all selected SKUs (siblings share lifestyle/infographic images). Writes them
    as other_product_image_locator_N on each selected row."""
    try:
        import ai_providers
    except Exception:
        return jsonify({"ok": False, "error": "ai_providers module missing"}), 500
    b = request.get_json(force=True) or {}
    skus  = [s for s in (b.get("skus") or []) if s]
    brief = b.get("brief", "")
    live      = bool(b.get("live"))
    live_refs = b.get("live_refs") or {}
    if not skus:
        return jsonify({"ok": False, "error": "no skus selected"}), 400
    if not brief.strip():
        return jsonify({"ok": False, "error": "no brief given"}), 400

    # Reference image: for LIVE listings use the Amazon photo passed from the
    # client; for draft listings pull the main image from the sheet row.
    by_sku = {}
    ref_img = ""
    if live:
        # first selected SKU that has a live Amazon image
        for s in skus:
            if live_refs.get(str(s)):
                ref_img = live_refs[str(s)]
                break
    else:
        try:
            recs = _records(_ws())
        except Exception as e:
            return jsonify({"ok": False, "error": f"could not read sheet: {e}"}), 500
        for r in recs:
            by_sku[str(r.get("SKU", ""))] = r
        first = by_sku.get(str(skus[0]))
        if first:
            try:
                a = json.loads(first.get("Attributes JSON") or "{}")
                ref_img = a.get("main_product_image_locator", "") or a.get("other_product_image_locator_1", "")
            except Exception:
                pass

    # split brief into up to N distinct secondary-image briefs (by line / comma)
    parts = [p.strip() for p in re.split(r"[\n;]+|,(?=\s*[a-zA-Z])", brief) if p.strip()][:6]
    if not parts:
        parts = [brief.strip()]

    images = []   # data URLs, generated ONCE
    for p in parts:
        res = ai_providers.run_pipeline(_cfg(), brief=p, reference_image=ref_img,
                                        product_title="secondary image")
        if res.get("ok"):
            if res.get("image_b64"):
                images.append(f"data:{res.get('mime','image/png')};base64,{res['image_b64']}")
            elif res.get("image_url"):
                images.append(res["image_url"])
            else:
                return jsonify({"ok": False, "error": "no image returned", "generated": len(images)}), 400
        else:
            return jsonify({"ok": False, "error": f"image gen failed: {res.get('error','')}",
                            "generated": len(images)}), 400

    # LIVE listings aren't sheet rows -> just return the generated images for
    # the user to download and upload via Amazon Manage Images.
    if live:
        return jsonify({"ok": True, "images": images, "applied": 0, "live": True})

    # apply the SAME images across every selected SKU's row (draft listings)
    ws = _ws()
    applied = 0
    for sku in skus:
        r = by_sku.get(str(sku))
        if not r:
            continue
        try:
            attrs = json.loads(r.get("Attributes JSON") or "{}")
            if not isinstance(attrs, dict):
                attrs = {}
        except Exception:
            attrs = {}
        for i, img in enumerate(images, start=1):
            attrs[f"other_product_image_locator_{i}"] = img
        # write back via the same path the editor uses
        try:
            _write_attrs_for_sku(ws, sku, attrs)
            applied += 1
        except Exception:
            pass
    # return the image URLs too so the UI can preview them
    return jsonify({"ok": True, "images": images, "applied": applied})


@app.route("/edit", methods=["POST"])
def edit():
    b      = request.get_json(force=True) or {}
    sku    = str(b.get("sku", "")).strip()
    target = b.get("target")
    key    = str(b.get("key", "")).strip()
    value  = b.get("value", "")
    if not sku or not key:
        return jsonify({"ok": False, "error": "missing sku/key"}), 400
    try:
        ws      = _ws()
        headers = ws.row_values(1)
        kcol    = headers.index(SKU_HEADER) + 1
        trow    = None
        for i, v in enumerate(ws.col_values(kcol), start=1):
            if str(v).strip() == sku:
                trow = i
                break
        if not trow:
            return jsonify({"ok": False, "error": "sku not found in sheet"}), 404
        if target == "col":
            if key not in _EDITABLE_COLS or key not in headers:
                return jsonify({"ok": False, "error": "column not editable"}), 400
            ws.update_cell(trow, headers.index(key) + 1, value)
        elif target == "attr":
            if "Attributes JSON" not in headers:
                return jsonify({"ok": False, "error": "no attributes column"}), 400
            acol = headers.index("Attributes JSON") + 1
            cur  = ws.cell(trow, acol).value or "{}"
            try:
                obj = json.loads(cur)
            except Exception:
                obj = {}
            if not isinstance(obj, dict):
                obj = {}
            if str(value).strip() == "":
                obj.pop(key, None)
            else:
                # PREFIX CLEANUP: when writing a deeper dot-key like
                # `leg.length.decimal_value`, purge any shallower keys at
                # the same prefix (`leg`, `leg.length`) that are STRINGS.
                # Without this, older shallow saves (from prior schema-
                # extractor versions) sit alongside new deeper saves and
                # collide in the generator's _renest, crashing with
                # "'str' object does not support item assignment".
                # Only strip when the shallower value is a scalar -- if
                # it's already a dict (a previous nested write), leave it
                # alone. Also strip DEEPER keys under the same prefix when
                # we write a scalar (rare -- happens if user manually
                # replaces a nested attr with a single value).
                if "." in key:
                    parts = key.split(".")
                    for i in range(1, len(parts)):
                        prefix = ".".join(parts[:i])
                        if prefix in obj and not isinstance(obj[prefix], dict):
                            obj.pop(prefix, None)
                else:
                    # New scalar write: strip any dot-keys underneath us
                    _pfx = key + "."
                    for _stale in [k for k in list(obj.keys()) if k.startswith(_pfx)]:
                        obj.pop(_stale, None)
                obj[key] = value
            ws.update_cell(trow, acol, json.dumps(obj, ensure_ascii=False))
        else:
            return jsonify({"ok": False, "error": "bad target"}), 400
        _bust_records_cache()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/delete", methods=["POST"])
def delete_row():
    b   = request.get_json(force=True) or {}
    sku = str(b.get("sku", "")).strip()
    row = b.get("row")
    try:
        ws     = _ws()
        target = None
        if sku:                                   # prefer matching by SKU (stable)
            headers = ws.row_values(1)
            if SKU_HEADER in headers:
                kcol = headers.index(SKU_HEADER) + 1
                for i, v in enumerate(ws.col_values(kcol), start=1):
                    if str(v).strip() == sku:
                        target = i
                        break
        if target is None and row:                # fall back to row number (blank rows)
            try:
                target = int(row)
            except Exception:
                target = None
        if not target or target < 2:
            return jsonify({"ok": False, "error": "row not found"}), 404
        ws.delete_rows(target)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/clear_empty", methods=["POST"])
def clear_empty():
    """Delete every data row whose SKU, Title, Competitor ASIN and Product Type are all blank."""
    try:
        ws   = _ws()
        vals = ws.get_all_values()
        if not vals:
            return jsonify({"ok": True, "deleted": 0})
        headers = vals[0]
        keycols = [headers.index(h) for h in (SKU_HEADER, "Title", "Competitor ASIN", "Product Type")
                   if h in headers]
        blanks = []
        for r in range(1, len(vals)):                       # data rows (row 2 = index 1)
            rv = vals[r]
            if all((c >= len(rv) or not str(rv[c]).strip()) for c in keycols):
                blanks.append(r + 1)                        # 1-based sheet row
        for rownum in sorted(blanks, reverse=True):         # bottom-up keeps indices valid
            ws.delete_rows(rownum)
        return jsonify({"ok": True, "deleted": len(blanks)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



@app.route("/miles/sheet_pref", methods=["POST"])
def miles_sheet_pref_set():
    """Persist the output Sheet ID/tab so the user need not re-paste it each run."""
    b = request.get_json(force=True) or {}
    ok = _miles_set_pref(b.get("sheet", ""), b.get("tab", ""))
    return jsonify({"ok": bool(ok)})


@app.route("/miles/sheet_pref", methods=["GET"])
def miles_sheet_pref_get():
    """Return the saved output Sheet ID/tab for the active account (for pre-fill)."""
    return jsonify(_miles_get_pref())


def _miles_set_pref(sheet: str, tab: str) -> bool:
    try:
        import json as _j
        d = _miles_load_prefs()
        d[_miles_prefs_key()] = {"sheet": (sheet or "").strip(), "tab": (tab or "").strip()}
        _j.dump(d, open(_miles_prefs_file(), "w", encoding="utf-8"))
        return True
    except Exception:
        return False


def _miles_get_pref() -> dict:
    p = _miles_load_prefs().get(_miles_prefs_key()) or {}
    return {"sheet": str(p.get("sheet", "") or ""), "tab": str(p.get("tab", "") or "")}


def _miles_prefs_key() -> str:
    # Key per account so multiple workspaces each remember their own sheet.
    try:
        a = _active_account()
        return (a.get("id") if a else "") or "_default"
    except Exception:
        return "_default"


def _miles_load_prefs() -> dict:
    try:
        import json as _j
        d = _j.load(open(_miles_prefs_file(), encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _miles_prefs_file():
    return os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "miles_ui_prefs.json")


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


def _ebay_creds() -> tuple:
    """(app_id, cert_id) for the eBay Browse API used to scrape source products.

    Resolution: the ACTIVE account's own eBay credentials OVERRIDE the global
    ones -- but only when BOTH are present on the account (a half-filled pair
    would break OAuth, so we fall back to global rather than send a broken mix).
    Otherwise the global config values are used. Mirrors _sp_creds's
    account-aware pattern."""
    c = _cfg()
    g_app  = str(c.get("ebay_app_id", "") or "").strip()
    g_cert = str(c.get("ebay_cert_id", "") or "").strip()
    try:
        acc = _active_account()
    except Exception:
        acc = None
    if acc:
        a_app  = str(acc.get("ebay_app_id", "") or "").strip()
        a_cert = str(acc.get("ebay_cert_id", "") or "").strip()
        if a_app and a_cert:
            return a_app, a_cert
    return g_app, g_cert

def _kill_proc(p):
    """Stop a running child process (and its descendants on Windows)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


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


# =============================================================================
# MILES LUBRICANTS  --  supplier-site harvest workspace
# =============================================================================
_MILES_STATE = {"items": [], "results": None, "cancel": False}
_MILES_HISTORY_PATH = None   # resolved lazily next to config

def _miles_history_file():
    global _MILES_HISTORY_PATH
    if _MILES_HISTORY_PATH is None:
        _MILES_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "miles_harvested.json")
    return _MILES_HISTORY_PATH

def _miles_load_history() -> set:
    try:
        import json as _j
        return set(_j.load(open(_miles_history_file(), encoding="utf-8")))
    except Exception:
        return set()

def _miles_save_history(done: set):
    try:
        import json as _j
        _j.dump(sorted(done), open(_miles_history_file(), "w", encoding="utf-8"))
    except Exception:
        pass

@app.route("/miles/upload", methods=["POST"])
def miles_upload():
    """Receive the item-number list (parsed client-side from CSV/XLSX) and stash
    it for the harvest run. Body: {items:[...]}."""
    b = request.get_json(force=True) or {}
    items = [str(x).strip() for x in (b.get("items") or []) if str(x).strip()]
    # de-dup preserve order
    seen, clean = set(), []
    for it in items:
        if it not in seen:
            seen.add(it); clean.append(it)
    _MILES_STATE["items"] = clean
    done = _miles_load_history()
    already = [it for it in clean if it in done]
    return jsonify({"ok": True, "count": len(clean), "items": clean[:50],
                    "already_harvested": already})


@app.route("/miles/clear_history", methods=["POST"])
def miles_clear_history():
    """Forget which item numbers were harvested, so they can run again."""
    done = _miles_load_history()
    n = len(done)
    _miles_save_history(set())
    # ALSO clear the permanent text store -- otherwise items saved there are still
    # treated as 'done' and skipped even after clearing history (the reason
    # 'Clear harvested history' seemed not to work). Now it fully resets.
    store_n = 0
    try:
        _sp = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "miles_bundles_store.json")
        if os.path.exists(_sp):
            _sd = json.load(open(_sp, encoding="utf-8"))
            store_n = len(_sd) if isinstance(_sd, dict) else 0
            json.dump({}, open(_sp, "w", encoding="utf-8"))
    except Exception:
        pass
    return jsonify({"ok": True, "cleared": n, "store_cleared": store_n})


@app.route("/miles/stop", methods=["POST"])
def miles_stop():
    """Kill any in-flight harvest OR generation subprocess immediately, then
    release the busy lock so a new run can start."""
    _MILES_STATE["cancel"] = True
    # Kill the generator subprocess if one is running
    proc = _running.get("proc")
    if proc and proc.poll() is None:
        try:
            import signal as _sig
            proc.send_signal(_sig.SIGTERM)
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
    try:
        with _run_lock:
            _running["on"] = False
    except Exception:
        _running["on"] = False
    _running["proc"] = None
    return jsonify({"ok": True, "killed": proc is not None})


@app.route("/miles/generate")
def miles_generate():
    """Run the generator's 'miles' mode: turn harvested bundles into Amazon
    draft listings (compliance + IP + copy). Streams the generator output."""
    _cfg_path = str(CONFIG_PATH)
    # scope to the active account's sheet + marketplace, like generate does
    try:
        _acc = _active_account()
    except Exception:
        _acc = None

    # user-provided output sheet/tab (override account defaults). Accept a bare
    # ID or a full Google Sheets URL.
    import re as _re
    def _sheet_id(s):
        s = (s or "").strip()
        m = _re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", s)
        return m.group(1) if m else s
    _user_sheet = _sheet_id(request.args.get("sheet", ""))
    _user_tab   = (request.args.get("tab", "") or "").strip()
    try:
        _user_limit = int(request.args.get("limit", "0") or "0")
    except ValueError:
        _user_limit = 0
    _use_ba = request.args.get("use_ba", "") == "1"

    def stream():
        # Log what we received so it's visible in the panel
        yield (f"data: [params] sheet='{_user_sheet[:20]}...' "
               f"tab='{_user_tab or '(none)'}' "
               f"limit={_user_limit or 'all'}\n\n")
        with _run_lock:
            busy = _running["on"]
            if not busy:
                _running["on"] = True
        if busy:
            yield "data: [busy] a run is already in progress\n\n"
            yield "event: end\ndata: end\n\n"
            return
        try:
            bundle_path = os.path.join(os.path.dirname(os.path.abspath(_cfg_path)),
                                       "miles_bundles.json")
            if not os.path.exists(bundle_path):
                yield "data: [error] No harvested bundles yet. Run a harvest first.\n\n"
                yield "event: end\ndata: end\n\n"
                return
            extra = ["miles"]
            if _acc:
                _aid = _acc.get("id") or ""
                if _aid:
                    extra += ["--account-id", _aid]
                _amkt = (_acc.get("default_marketplace") or "").strip().upper()
                if _amkt in ("US", "UK", "GB"):
                    extra += ["--marketplace", _amkt]
            # Output sheet/tab: user input wins, else account default.
            _out_sheet = _user_sheet or (_acc.get("output_spreadsheet_id") if _acc else "") or ""
            _out_tab   = _user_tab or (_acc.get("output_tab") or _acc.get("output_worksheet") if _acc else "") or ""
            if _out_sheet:
                extra += ["--sheet", _out_sheet]
            if _out_tab:
                extra += ["--tab", _out_tab]
            if _user_limit and _user_limit > 0:
                extra += ["--limit", str(_user_limit)]
                yield f"data: [limit] generating up to {_user_limit} listing(s) this run\n\n"
            if _use_ba:
                extra += ["--use-brand-analytics"]
                yield "data: [BA] real Amazon search data (Brand Analytics) ENABLED for this run\n\n"
            if _acc and "image_template" in (_acc.get("features") or []):
                extra += ["--auto-image"]
                yield "data: [image] Auto main image ENABLED -- a templated main image will be generated per listing\n\n"
            if _user_sheet or _user_tab:
                yield (f"data: [target] writing to sheet '{_out_sheet[:16]}...' / tab "
                       f"'{_out_tab or '(default)'}'\n\n")
            # GENERATION SET = every item folder in Drive (NOT the uploaded Excel,
            # which is HARVEST-ONLY). We scan Drive fresh each time and write the
            # full list to miles_items.json, so Generate never depends on a stale
            # file or on whether a spreadsheet was uploaded this session. run_miles
            # back-fills any missing from Drive and skips any SKU already present on
            # ANY tab -- so this builds exactly the missing listing copies.
            try:
                import miles_import as _MG
                _base_g = os.path.dirname(os.path.abspath(_cfg_path))
                _cfg_g = json.load(open(_cfg_path, encoding="utf-8"))
                _drv_g, _derr_g = _MG.build_drive_rw(_cfg_g, _base_g)
                _all_items = _MG.list_all_item_folders(_drv_g, log=lambda m: None) if _drv_g else []
                with open(os.path.join(_base_g, "miles_items.json"), "w", encoding="utf-8") as _itf:
                    json.dump(_all_items, _itf)
                if _all_items:
                    yield (f"data: [items] {len(_all_items)} item folder(s) in Drive -- building the "
                           f"ones not already in the sheet (existing rows on ANY tab are skipped)\n\n")
                else:
                    yield (f"data: [items] Drive scan returned nothing"
                           f"{(' ('+_derr_g+')') if _derr_g else ''} -- falling back to all "
                           f"locally-harvested items in the store\n\n")
            except Exception as _ie:
                yield f"data: [items] could not scan Drive for item list: {_ie}\n\n"
            args = [sys.executable, "-u", SCRIPT] + extra
            yield f"data: [start] {' '.join(args)}\n\n"
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1,
                                 cwd=os.path.dirname(os.path.abspath(_cfg_path)))
            _running["proc"] = p
            for line in iter(p.stdout.readline, ""):
                if line:
                    yield f"data: {line.rstrip()}\n\n"
            p.wait()
            yield f"data: [done] generation finished (exit {p.returncode})\n\n"
        except GeneratorExit:
            # The browser closed the SSE connection (navigated away / refreshed /
            # stale tab). Kill the subprocess if running, release the lock, and
            # RE-RAISE without yielding -- yielding here is what caused the noisy
            # 'generator ignored GeneratorExit' RuntimeError in the terminal.
            try:
                _p = _running.get("proc")
                if _p and _p.poll() is None:
                    _p.terminate()
            except Exception:
                pass
            with _run_lock:
                _running["on"] = False
            _running["proc"] = None
            raise
        except Exception as e:
            import traceback as _tb
            yield f"data: [error] {type(e).__name__}: {str(e)[:200]}\n\n"
            yield f"data:   {_tb.format_exc().splitlines()[-1][:200]}\n\n"
            with _run_lock:
                _running["on"] = False
            _running["proc"] = None
            yield "event: end\ndata: end\n\n"
            return
        # normal completion: release lock and signal end
        with _run_lock:
            _running["on"] = False
        _running["proc"] = None
        yield "event: end\ndata: end\n\n"
    return Response(stream(), mimetype="text/event-stream")


@app.route("/miles/optimize")
def miles_optimize():
    """PHASE 2: pull real Search Query Performance for the live ASINs in the
    Miles sheet and rewrite the copy to front-load converting queries."""
    _cfg_path = str(CONFIG_PATH)
    try:
        _acc = _active_account()
    except Exception:
        _acc = None
    import re as _re
    def _sheet_id(s):
        s = (s or "").strip()
        m = _re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", s)
        return m.group(1) if m else s
    _user_sheet = _sheet_id(request.args.get("sheet", ""))
    _user_tab   = (request.args.get("tab", "") or "").strip()

    def stream():
        yield (f"data: [start] SQP optimize -- sheet='{_user_sheet[:16]}...' "
               f"tab='{_user_tab or '(default)'}'\n\n")
        with _run_lock:
            busy = _running["on"]
            if not busy:
                _running["on"] = True
        if busy:
            yield "data: [busy] a run is already in progress\n\n"
            yield "event: end\ndata: end\n\n"
            return
        try:
            extra = ["miles-optimize"]
            if _acc:
                _aid = _acc.get("id") or ""
                if _aid:
                    extra += ["--account-id", _aid]
                _amkt = (_acc.get("default_marketplace") or "").strip().upper()
                if _amkt in ("US", "UK", "GB"):
                    extra += ["--marketplace", _amkt]
            _out_sheet = _user_sheet or (_acc.get("output_spreadsheet_id") if _acc else "") or ""
            _out_tab   = _user_tab or (_acc.get("output_tab") or _acc.get("output_worksheet") if _acc else "") or ""
            if _out_sheet:
                extra += ["--sheet", _out_sheet]
            if _out_tab:
                extra += ["--tab", _out_tab]
            args = [sys.executable, "-u", SCRIPT] + extra
            yield f"data: [start] {' '.join(args)}\n\n"
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1,
                                 cwd=os.path.dirname(os.path.abspath(_cfg_path)))
            _running["proc"] = p
            for line in iter(p.stdout.readline, ""):
                if line:
                    yield f"data: {line.rstrip()}\n\n"
            p.wait()
            yield f"data: [done] optimize finished (exit {p.returncode})\n\n"
        except GeneratorExit:
            try:
                _p = _running.get("proc")
                if _p and _p.poll() is None:
                    _p.terminate()
            except Exception:
                pass
            with _run_lock:
                _running["on"] = False
            _running["proc"] = None
            raise
        except Exception as e:
            import traceback as _tb
            yield f"data: [error] {type(e).__name__}: {str(e)[:200]}\n\n"
            yield f"data:   {_tb.format_exc().splitlines()[-1][:200]}\n\n"
            with _run_lock:
                _running["on"] = False
            _running["proc"] = None
            yield "event: end\ndata: end\n\n"
            return
        with _run_lock:
            _running["on"] = False
        _running["proc"] = None
        yield "event: end\ndata: end\n\n"
    return Response(stream(), mimetype="text/event-stream")


@app.route("/miles/run")
def miles_run():
    """Stream the Miles harvest over SSE. Reads the stashed item numbers, runs
    the harvester (search -> match -> scrape -> download -> Drive -> bundle)."""
    # Read state in the request context (SSE generator runs outside it).
    _items = list(_MILES_STATE.get("items") or [])
    _skip_done = (request.args.get("skip_done", "1") == "1")
    _cfg_path = str(CONFIG_PATH)
    # Resolve the output target + account HERE (request context) so the harvest
    # can CHAIN generation once it finishes -- the SSE generator below runs
    # outside request context and can't call _active_account()/_miles_get_pref().
    try:
        _acc = _active_account()
    except Exception:
        _acc = None
    _pref = _miles_get_pref()

    def stream():
        if not _items:
            yield "data: [error] No item numbers uploaded. Upload a CSV/Excel first.\n\n"
            yield "event: end\ndata: end\n\n"
            return
        _my_token = None
        with _run_lock:
            busy = _running["on"]
            if not busy:
                _running["on"] = True
                _my_token = __import__("time").time()
                _running["miles_token"] = _my_token
        if busy:
            yield "data: [busy] a run is already in progress\n\n"
            yield "event: end\ndata: end\n\n"
            return
        try:
            try:
                import miles_import as _M   # available for the whole harvest below
            except Exception as _ie:
                yield f"data: [error] miles_import import failed: {_ie}\n\n"
                yield "event: end\ndata: end\n\n"
                return

            def _generate_missing():
                """Harvest is done -> build listing copies for EVERY item folder in
                Drive that is NOT already in the output sheet. The uploaded Excel is
                HARVEST-ONLY; the generation set comes from Drive (all harvested
                folders), and run_miles skips any SKU already present in the sheet
                (replace_existing=False), so re-hitting Harvest never duplicates a
                row -- it only fills in what's missing."""
                yield "data: \n\n"
                yield "data: [generate] scanning Drive for harvested item folders...\n\n"
                _base_g = os.path.dirname(os.path.abspath(_cfg_path))
                try:
                    _cfg_g = json.load(open(_cfg_path, encoding="utf-8"))
                except Exception as _ce:
                    yield f"data: [error] cannot read config for generation: {_ce}\n\n"
                    return
                _drv_g, _derr_g = _M.build_drive_rw(_cfg_g, _base_g)
                if not _drv_g:
                    yield f"data: [error] cannot scan Drive for generation: {_derr_g}\n\n"
                    return
                _all = _M.list_all_item_folders(_drv_g, log=lambda m: None)
                if not _all:
                    yield "data: [generate] no item folders found in Drive -- nothing to generate.\n\n"
                    return
                yield (f"data: [generate] {len(_all)} item folder(s) in Drive; building the ones "
                       f"not already in the sheet (existing rows are skipped)...\n\n")
                try:
                    with open(os.path.join(_base_g, "miles_items.json"), "w", encoding="utf-8") as _f:
                        json.dump(_all, _f)
                except Exception as _we:
                    yield f"data: [error] could not write item list for generation: {_we}\n\n"
                    return
                # Account/sheet-scoped generation command (mirrors /miles/generate).
                gen_extra = ["miles"]
                if _acc:
                    _aid = _acc.get("id") or ""
                    if _aid:
                        gen_extra += ["--account-id", _aid]
                    _amkt = (_acc.get("default_marketplace") or "").strip().upper()
                    if _amkt in ("US", "UK", "GB"):
                        gen_extra += ["--marketplace", _amkt]
                # The saved pref may hold a full Google Sheets URL -- extract the
                # bare spreadsheet ID (the generator's --sheet expects an ID, not a
                # URL). Mirrors _sheet_id() in /miles/generate.
                _raw_sheet = (_pref.get("sheet") or (_acc.get("output_spreadsheet_id") if _acc else "") or "")
                _sm = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", _raw_sheet)
                _out_sheet = _sm.group(1) if _sm else _raw_sheet.strip()
                _out_tab   = (_pref.get("tab") or ((_acc.get("output_tab") or _acc.get("output_worksheet")) if _acc else "") or "")
                if _out_sheet:
                    gen_extra += ["--sheet", _out_sheet]
                if _out_tab:
                    gen_extra += ["--tab", _out_tab]
                if _acc and "image_template" in (_acc.get("features") or []):
                    gen_extra += ["--auto-image"]
                    yield "data: [image] Auto main image ENABLED for generated listings\n\n"
                args = [sys.executable, "-u", SCRIPT] + gen_extra
                yield f"data: [start] {' '.join(args)}\n\n"
                _gp = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, bufsize=1,
                                       cwd=_base_g)
                _running["proc"] = _gp
                for _line in iter(_gp.stdout.readline, ""):
                    if _line:
                        yield f"data: {_line.rstrip()}\n\n"
                _gp.wait()
                _running["proc"] = None
                yield f"data: [done] generation finished (exit {_gp.returncode})\n\n"

            done = _miles_load_history()
            # Also treat anything already in the PERMANENT store as done -- its
            # text is saved, so there's no need to re-scrape it.
            try:
                _app_dir = os.path.dirname(os.path.abspath(_cfg_path))
                _store_path = os.path.join(_app_dir, "miles_bundles_store.json")
                _store = json.load(open(_store_path, encoding="utf-8"))
                if isinstance(_store, dict):
                    done = set(done) | set(_store.keys())
            except Exception:
                pass
            items = _items
            if _skip_done:
                # Verify each 'done' item's files STILL EXIST in Drive. If the user
                # deleted the PDFs from Drive, re-harvest it instead of trusting the
                # local history/text-store (the old bug: deleted-from-Drive items
                # were skipped forever). If Drive can't be checked, DON'T silently
                # skip everything -- surface why, and only skip items we can confirm
                # are still present.
                # Emit immediately so the log shows life while Drive auth happens.
                yield "data: [start] connecting to Drive to check what's already harvested...\n\n"
                _drv = None
                _drv_err = ""
                try:
                    _cfg_for_drv = json.load(open(_cfg_path, encoding="utf-8"))
                    _base_for_drv = os.path.dirname(os.path.abspath(_cfg_path))
                    _drv, _drv_err = _M.build_drive_rw(_cfg_for_drv, _base_for_drv)
                except Exception as _de:
                    _drv = None; _drv_err = str(_de)[:160]
                if _drv is None:
                    # Can't verify Drive -> do NOT skip on text-store/history alone,
                    # or the user can never re-harvest. Tell them and run everything.
                    yield (f"data: [note] Could not check Drive to confirm which items "
                           f"still have files{(' ('+_drv_err+')') if _drv_err else ''}; "
                           f"running all {len(items)} item(s) rather than skipping blindly.\n\n")
                else:
                    skipped, _revived = [], []
                    _items_after = []
                    _newly_skipped = []                        # had Drive files but NOT in local history
                    # DRIVE is the source of truth for "already harvested": if the
                    # item's folder holds at least one file, skip it -- even when our
                    # LOCAL history / text-store never recorded it (cleared history,
                    # a different machine, or a prior run on another install). The
                    # old code only checked Drive for items already in `done`, so an
                    # item whose files WERE in Drive but absent from local history
                    # dropped into the else-branch and got needlessly re-harvested.
                    #
                    # Each check is 2 Drive list calls (network). STREAM the result of
                    # each item as it comes in -- if we accumulated and dumped after the
                    # loop, the log would sit on an empty box for many seconds while N
                    # items are checked silently (looked like "nothing is happening").
                    _ntotal = len(items)
                    yield (f"data: [check] verifying {_ntotal} item(s) against Drive "
                           f"(skip anything already harvested)...\n\n")
                    for _idx, it in enumerate(items, 1):
                        _one_log = []
                        _has = _M.item_has_drive_files(_drv, it,
                                                       log=lambda m: _one_log.append(str(m)))
                        for _cl in _one_log:                   # live per-item detail
                            yield f"data: {_cl}\n\n"
                        if _has:
                            skipped.append(it)
                            if it not in done:
                                _newly_skipped.append(it)
                                done.add(it)                   # sync local history to Drive
                        else:
                            if it in done:
                                _revived.append(it)            # was 'done' but files gone
                                done.discard(it)               # forget stale 'done'
                            _items_after.append(it)            # (re-)harvest it
                        if _idx % 25 == 0 and _idx != _ntotal:
                            yield f"data: [check] {_idx}/{_ntotal} checked...\n\n"
                    items = _items_after
                    # Persist history when Drive told us something new (files exist for
                    # items local history didn't know about).
                    if _newly_skipped:
                        _miles_save_history(done)
                        yield (f"data: Skipping {len(_newly_skipped)} item(s) whose files were "
                               f"already in Drive (not in local history): "
                               f"{', '.join(_newly_skipped[:20])}\n\n")
                    if _revived:
                        yield (f"data: Re-harvesting {len(_revived)} item(s) whose files were "
                               f"deleted from Drive: {', '.join(_revived[:20])}\n\n")
                        _miles_save_history(done)
                        # also drop revived items from the permanent text store so
                        # they actually re-scrape (the store otherwise marks them done)
                        try:
                            _sp = os.path.join(os.path.dirname(os.path.abspath(_cfg_path)),
                                               "miles_bundles_store.json")
                            _sd = json.load(open(_sp, encoding="utf-8"))
                            if isinstance(_sd, dict):
                                for _it in _revived:
                                    _sd.pop(_it, None)
                                json.dump(_sd, open(_sp, "w", encoding="utf-8"))
                        except Exception:
                            pass
                    if skipped:
                        yield (f"data: Skipping {len(skipped)} item(s) already saved "
                               f"(files still present in Drive): "
                               f"{', '.join(skipped[:20])}\n\n")
            if not items:
                yield (f"data: [note] Nothing new to harvest -- all {len(_items)} uploaded item(s) "
                       "already have their files in Drive. Building any missing listings now...\n\n")
                yield from _generate_missing()
                with _run_lock:
                    if _running.get("miles_token") == _my_token:
                        _running["on"] = False
                yield "event: end\ndata: end\n\n"
                return

            # Count against the FULL uploaded list, not just the remaining items.
            # e.g. uploaded 146, 25 already harvested (skipped) -> the harvest of the
            # remaining 121 shows as [26/146] .. [146/146], so the numbers line up
            # with the sheet the user uploaded instead of restarting at [1/121].
            _orig_total  = len(_items)                 # full uploaded count (e.g. 146)
            _done_before = _orig_total - len(items)    # already harvested / skipped (e.g. 25)
            if _done_before > 0:
                yield (f"data: [start] Miles harvest -- {_done_before} of {_orig_total} already "
                       f"harvested (skipped); harvesting the remaining {len(items)} "
                       f"as {_done_before + 1}-{_orig_total} of {_orig_total}\n\n")
            else:
                yield f"data: [start] Miles harvest -- {_orig_total} item number(s)\n\n"
            import asyncio
            try:
                import miles_import as _miles
            except Exception as e:
                yield f"data: [error] miles_import import failed: {e}\n\n"
                yield "event: end\ndata: end\n\n"
                return

            cfg = json.load(open(_cfg_path, encoding="utf-8"))
            base_dir = os.path.dirname(os.path.abspath(_cfg_path))

            # Stream progress live by running per-item and yielding as we go.
            import miles_import as _M
            drive_service, derr = _M.build_drive_rw(cfg, base_dir)
            if derr:
                yield f"data: [error] Drive unavailable -- files will NOT be saved: {derr}\n\n"
                drive_service = None
            else:
                yield "data: Drive connected -- files will be saved per item number.\n\n"

            results = {"products": [], "needs_review": [], "not_found": [], "errors": []}
            total = _orig_total              # count against the FULL uploaded list
            _MILES_STATE["cancel"] = False   # clear any stale cancel request
            for i, item in enumerate(items, 1):
                _pos = _done_before + i      # position within the uploaded list (e.g. 26)
                if _MILES_STATE.get("cancel"):
                    yield f"data: [stopped] cancelled after {_pos-1}/{total} item(s)\n\n"
                    break
                yield f"data: [{_pos}/{total}] {item} -- searching...\n\n"
                _item_log = []
                try:
                    res = asyncio.run(_M.harvest_item(item, drive_service,
                                                      log=lambda m: _item_log.append(str(m))))
                except Exception as e:
                    import traceback as _tb
                    for _l in _item_log:
                        yield f"data: {_l}\n\n"
                    results["errors"].append({"item": item, "message": f"{type(e).__name__}: {str(e)[:160]}"})
                    yield f"data: [error]   {item}: {type(e).__name__}: {str(e)[:160]}\n\n"
                    yield f"data:   (trace) {_tb.format_exc().splitlines()[-1][:160]}\n\n"
                    continue
                # stream the harvester's own detailed lines (search diag, page size, pdfs)
                for _l in _item_log:
                    yield f"data: {_l}\n\n"
                st = res.get("status")
                if st == _M.OK:
                    p = res["product"]
                    results["products"].append(p)
                    _nfiles = len(p.get("pdf_files", []))
                    # Only remember it as 'done' if we actually got files. A 0-file
                    # OK is a partial result -- let it re-run next time, don't skip.
                    if _nfiles > 0:
                        done.add(item)
                    yield (f"data:   OK -- '{(p.get('title') or '')[:45]}' | "
                           f"{_nfiles} file(s) | "
                           f"{'SDS' if p.get('sds_text') else 'no SDS'}"
                           f"{'' if _nfiles else '  (0 files -- will retry next run)'} | {res.get('message','')}\n\n")
                elif st == _M.NEEDS_REVIEW:
                    results["needs_review"].append({"item": item, "message": res.get("message", "")})
                    yield f"data:   NEEDS_REVIEW -- {res.get('message','')}\n\n"
                elif st == _M.NOT_FOUND:
                    results["not_found"].append({"item": item, "message": res.get("message", "")})
                    yield f"data:   NOT_FOUND -- {res.get('message','')}\n\n"
                else:
                    results["errors"].append({"item": item, "message": res.get("message", "")})
                    yield f"data: [error]   {item}: {res.get('message','')}\n\n"

            _miles_save_history(done)
            _MILES_STATE["results"] = {
                "ok": len(results["products"]),
                "needs_review": results["needs_review"],
                "not_found": results["not_found"],
                "errors": results["errors"],
                "products": results["products"],
            }
            # Persist harvested bundles into a PERMANENT store keyed by item
            # number (merge, never overwrite). This way an item harvested once is
            # kept forever -- you never have to re-harvest it to regenerate. The
            # 'latest run' file is also written for convenience.
            try:
                _app_dir = os.path.dirname(os.path.abspath(_cfg_path))
                _store_path = os.path.join(_app_dir, "miles_bundles_store.json")
                # load existing permanent store
                try:
                    _store = json.load(open(_store_path, encoding="utf-8"))
                    if not isinstance(_store, dict):
                        _store = {}
                except Exception:
                    _store = {}
                # merge this run's products in, keyed by item_number
                for _p in results["products"]:
                    _key = _p.get("item_number") or _p.get("sku") or ""
                    if _key:
                        _store[_key] = _p
                json.dump(_store, open(_store_path, "w", encoding="utf-8"))
                # also write the latest-run file (back-compat)
                _bundle_path = os.path.join(_app_dir, "miles_bundles.json")
                json.dump(results["products"], open(_bundle_path, "w", encoding="utf-8"))
            except Exception:
                pass
            yield (f"data: [done] harvested {len(results['products'])} | "
                   f"review {len(results['needs_review'])} | "
                   f"not found {len(results['not_found'])} | "
                   f"errors {len(results['errors'])}\n\n")
            # Harvest finished -> automatically build listing copies for every Drive
            # item folder not yet in the output sheet (the requested one-click flow).
            yield from _generate_missing()
        except GeneratorExit:
            # browser closed the SSE connection; kill any chained generation
            # subprocess, release lock if we own it, re-raise
            try:
                _p = _running.get("proc")
                if _p and _p.poll() is None:
                    _p.terminate()
            except Exception:
                pass
            _running["proc"] = None
            with _run_lock:
                if _running.get("miles_token") == _my_token:
                    _running["on"] = False
            raise
        except Exception as e:
            import traceback as _tb
            yield f"data: [error] {type(e).__name__}: {str(e)[:200]}\n\n"
            yield f"data:   {_tb.format_exc().splitlines()[-1][:200]}\n\n"
            try:
                _p = _running.get("proc")
                if _p and _p.poll() is None:
                    _p.terminate()
            except Exception:
                pass
            _running["proc"] = None
            with _run_lock:
                if _running.get("miles_token") == _my_token:
                    _running["on"] = False
            yield "event: end\ndata: end\n\n"
            return
        with _run_lock:
            # Only release if THIS run still owns the lock. A wedged old
            # stream finishing late must not clear a newer run's lock.
            if _running.get("miles_token") == _my_token:
                _running["on"] = False
        yield "event: end\ndata: end\n\n"
    return Response(stream(), mimetype="text/event-stream")


@app.route("/miles/results")
def miles_results():
    """Return the last harvest's summary for the UI."""
    r = _MILES_STATE.get("results")
    if not r:
        return jsonify({"ok": False, "message": "no harvest run yet"})
    # don't ship the full product text blobs to the list view; summarise
    prods = [{"item_number": p.get("item_number"), "title": p.get("title"),
              "pdf_count": len(p.get("pdf_files", [])),
              "has_sds": bool(p.get("sds_text"))}
             for p in r.get("products", [])]
    return jsonify({"ok": True, "summary": {
        "ok": r.get("ok", 0), "needs_review": r.get("needs_review", []),
        "not_found": r.get("not_found", []), "errors": r.get("errors", []),
        "products": prods}})


@app.route("/run/<mode>")
def run(mode):
    if mode not in ("generate", "retry", "export", "api", "api_submit", "regen"):
        return Response("data: [error] unknown mode\n\nevent: end\ndata: end\n\n",
                        mimetype="text/event-stream")

    # IMPORTANT: read request.args HERE, inside the request context. The streaming
    # generator below runs OUTSIDE the request context, where `request` is gone --
    # touching it there raises "Working outside of request context" and kills the
    # stream before any data is sent (looks like "couldn't reach the stream").
    _req_skus = (request.args.get("skus") or "").strip()
    _req_select = (request.args.get("select") or "").strip()
    _req_select_type = (request.args.get("select_type") or "auto").strip()
    _req_minimal = (request.args.get("minimal") or "") == "1"

    def stream():
        if not _acquire_run_lock():
            yield "data: [busy] a run is already in progress -- wait for it to finish\n\n"
            yield "event: end\ndata: end\n\n"
            return
        try:
            # -u = unbuffered child stdout so progress streams live
            extra = ([] if mode == "generate"
                     else ["api", "submit"] if mode == "api_submit"
                     else [mode])
            # REGEN: re-run the generator scoped to a specific set of SKUs and the
            # active sheet/tab/marketplace. Needs generator support for --skus.
            if mode == "regen":
                skus = _req_skus
                _sid = _state.get("active_sheet_id")
                _tab = _state.get("active_tab")
                _mkt = _state.get("active_marketplace") or ""
                extra = ["regen"]
                if skus: extra += ["--skus", skus]
                if _sid: extra += ["--sheet", _sid]
                if _tab: extra += ["--tab", _tab]
                if _mkt: extra += ["--marketplace", _mkt]
            # SCOPE TO THE ACTIVE ACCOUNT/WORKSPACE for ALL modes (including
            # generate) so listings are created on the CORRECT account's sheet --
            # not the default dropshipping sheet. Account sheet/tab take priority;
            # brand-view scoping (below) refines marketplace for api/submit.
            try:
                _acc = _active_account()
            except Exception:
                _acc = None
            if _acc:
                _acc_id = _acc.get("id") or ""
                if _acc_id and "--account-id" not in extra:
                    extra += ["--account-id", _acc_id]
                _acc_sheet = _acc.get("output_spreadsheet_id") or ""
                _acc_tab = _acc.get("output_tab") or _acc.get("output_worksheet") or ""
                _acc_out_gid = str(_acc.get("output_tab_gid") or "")
                _acc_in_sheet = _acc.get("input_spreadsheet_id") or ""
                _acc_in_gid = str(_acc.get("input_tab_gid") or "")
                if _acc_sheet and "--sheet" not in extra:
                    extra += ["--sheet", _acc_sheet]
                if _acc_tab and "--tab" not in extra:
                    extra += ["--tab", _acc_tab]
                if _acc_out_gid and "--tab-gid" not in extra:
                    extra += ["--tab-gid", _acc_out_gid]
                if _acc_in_sheet and "--input-sheet" not in extra:
                    extra += ["--input-sheet", _acc_in_sheet]
                if _acc_in_gid and "--input-tab-gid" not in extra:
                    extra += ["--input-tab-gid", _acc_in_gid]
                # marketplace (US/UK) for this account -- so pricing, fees, SP-API
                # and the flat-file route match the account, not the UK default.
                _acc_mkt = (_acc.get("default_marketplace") or "").strip().upper()
                if _acc_mkt not in ("US", "UK", "GB") and _acc.get("marketplaces"):
                    # pick the first US/UK/GB entry, not blindly [0] (which can be
                    # MX/CA/BR -> generator would fall through to the UK default
                    # and deny a US token on catalog/pricing/fees).
                    for _mm in _acc["marketplaces"]:
                        _mmu = str(_mm).strip().upper()
                        if _mmu in ("US", "UK", "GB"):
                            _acc_mkt = _mmu
                            break
                if _acc_mkt and "--marketplace" not in extra:
                    extra += ["--marketplace", _acc_mkt]
            else:
                # DROPSHIPPING (no active account): honour the user-assigned default
                # sheets from "AI & settings ▸ Dropshipping sheets", if set. Purely
                # additive -- when unset, nothing is passed and the generator uses
                # its config.json defaults exactly as before (zero regression). We
                # pass BOTH the tab name (--tab, for api/regen whose run_api opens
                # the worksheet by name) and the gid (--tab-gid, for generate whose
                # init_sheets resolves by gid), so either path targets the right tab.
                _cfg0 = _cfg()
                _ds_out  = str(_cfg0.get("dropshipping_output_spreadsheet_id") or "").strip()
                _ds_otab = str(_cfg0.get("dropshipping_output_tab") or "").strip()
                _ds_ogid = str(_cfg0.get("dropshipping_output_tab_gid") or "").strip()
                _ds_in   = str(_cfg0.get("dropshipping_input_spreadsheet_id") or "").strip()
                _ds_igid = str(_cfg0.get("dropshipping_input_tab_gid") or "").strip()
                if _ds_out and "--sheet" not in extra:
                    extra += ["--sheet", _ds_out]
                if _ds_otab and "--tab" not in extra:
                    extra += ["--tab", _ds_otab]
                if _ds_ogid and "--tab-gid" not in extra:
                    extra += ["--tab-gid", _ds_ogid]
                if _ds_in and "--input-sheet" not in extra:
                    extra += ["--input-sheet", _ds_in]
                if _ds_igid and "--input-tab-gid" not in extra:
                    extra += ["--input-tab-gid", _ds_igid]
            # If a brand view is active, scope api preview/submit to THAT sheet +
            # marketplace only -- so it never previews every marketplace/account
            # at once (which would waste credits), and validates against the
            # correct catalogue (US for US brands).
            if mode in ("api", "api_submit"):
                # per-listing Preview/Submit: a ?skus= filter limits to those SKUs
                _api_skus = _req_skus
                if _api_skus and "--skus" not in extra:
                    extra += ["--skus", _api_skus]
                if _req_minimal and "--minimal" not in extra:
                    extra += ["--minimal"]
                _sid = _state.get("active_sheet_id")
                _tab = _state.get("active_tab")
                _mkt = ""
                # resolve marketplace from the active brand profile, if any
                _vk = _state.get("active_view") or ""
                if _vk:
                    try:
                        import glob as _glob, os as _os
                        for _pf in _glob.glob(_os.path.join(_os.path.dirname(CONFIG_PATH), "brands", "*", "profile.json")):
                            _p = json.load(open(_pf, encoding="utf-8"))
                            if (_p.get("brand_name") or "") == _vk:
                                _mkt = _p.get("marketplace", "") or ""
                                break
                    except Exception:
                        pass
                if _sid:
                    extra += ["--sheet", _sid]
                if _tab:
                    extra += ["--tab", _tab]
                if _mkt:
                    extra += ["--marketplace", _mkt]
            # ROW SELECTION (generate only): limit the run to chosen input rows.
            # Empty -> generator processes all rows (unchanged).
            if mode == "generate" and _req_select:
                extra += ["--select", _req_select]
                extra += ["--select-type", _req_select_type or "auto"]
            args = [sys.executable, "-u", SCRIPT] + extra
            yield f"data: [start] {' '.join(args)}\n\n"
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1)
            _running["proc"] = p
            try:
                # generation asks once for a brand; feed the configured one (Enter = auto)
                if mode == "generate":
                    p.stdin.write((_cfg().get("brand_name", "") or "") + "\n")
                p.stdin.flush()
                p.stdin.close()
            except Exception:
                pass
            for line in iter(p.stdout.readline, ""):
                clean = _ANSI.sub("", line.rstrip("\n"))
                if clean.strip():
                    yield f"data: {clean}\n\n"
            p.wait()
            yield f"data: [done] finished (exit code {p.returncode})\n\n"
            yield "event: end\ndata: end\n\n"
        finally:
            with _run_lock:
                _running["proc"] = None
                _running["on"] = False

    return Response(stream(), mimetype="text/event-stream")


_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Listing Generator</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.5.0/dist/tabler-icons.min.css">
<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
<link rel="stylesheet" href="https://unpkg.com/@tabler/icons-webfont@3.5.0/dist/tabler-icons.min.css">
<style>
  :root{
    --bg:#0f1115; --panel:#181b22; --panel2:#1f232c; --line:#2a2f3a;
    --ink:#e8eaed; --muted:#9aa3b2; --accent:#4c8dff;
    --green:#1f7a3d; --greenbg:#15301f; --amber:#9a6b00; --amberbg:#2e2510;
    --red:#a12a2a; --redbg:#2e1414; --sidebar:#14171d;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:14px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  button{font:inherit;border:1px solid var(--line);background:var(--panel2);
         color:var(--ink);padding:7px 13px;border-radius:7px;cursor:pointer}
  button:hover{border-color:#3a4150}
  button.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
  button.ghost{background:transparent}
  button.danger{background:#7a1f1f;border-color:#7a1f1f;color:#fff;font-weight:600}
  button.danger:hover{background:#8f2626;border-color:#8f2626}

  /* ---- top bar (always visible) ---- */
  .appbar{position:sticky;top:0;z-index:20;background:var(--panel);
          border-bottom:1px solid var(--line);padding:11px 18px;display:flex;
          align-items:center;gap:12px}
  .appbar .brandmark{display:flex;align-items:center;gap:9px;font-weight:650;font-size:15px;cursor:pointer}
  .appbar .brandmark .dot{width:22px;height:22px;border-radius:6px;background:var(--accent);
        display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px}
  .appbar .spacer{flex:1}
  .appbar .barbtn{font-size:13px;color:var(--muted);background:transparent;border:1px solid transparent;
        padding:6px 10px;border-radius:8px;cursor:pointer}
  .appbar .barbtn:hover{background:var(--panel2);color:var(--ink)}
  .barbtn.privon{color:#ffd479;border-color:#5a4a1e;background:#2a2310}
  /* visual zone editor boxes */
  .zebox{position:absolute;border:2px dashed #4c8dff;background:rgba(76,141,255,.10);cursor:move;box-sizing:border-box;display:flex;align-items:center;overflow:hidden}
  .zebox.sel{border-style:solid;box-shadow:0 0 0 2px rgba(255,255,255,.3)}
  .zelbl{position:absolute;top:-16px;left:-2px;font-size:9px;font-weight:700;color:#0a0e14;padding:1px 5px;border-radius:3px;white-space:nowrap;z-index:2}
  .zetext{color:#fff;font-size:13px;padding:0 6px;pointer-events:none;text-transform:uppercase;line-height:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%}
  .zegrip{position:absolute;right:-6px;bottom:-6px;width:12px;height:12px;background:#fff;border:2px solid #4c8dff;border-radius:2px;cursor:nwse-resize;z-index:2}
  .zeerase{position:absolute;background:rgba(0,0,0,.78);border:1px solid #ff6b6b;box-sizing:border-box}
  .zeerase .zex{position:absolute;top:-9px;right:-6px;background:#ff6b6b;color:#fff;border-radius:50%;width:16px;height:16px;font-size:12px;line-height:16px;text-align:center;cursor:pointer}
  .crumbs{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px}
  .dwhl{margin:2px 0 8px;font-size:13px;color:#cdd6e4;line-height:1.4}
  .dwhl-lbl{display:inline-block;background:#2a3a52;color:#9cc1ff;font-size:10px;font-weight:700;padding:1px 6px;border-radius:4px;margin-right:6px;text-transform:uppercase;letter-spacing:.04em}
  .crumbs .sep{opacity:.5}
  .crumbs .here{color:var(--ink);font-weight:600}

  /* ---- privacy mode: blur sensitive info for screen-sharing/demos ---- */
  /* Any element tagged .pii gets blurred when body.privacy-on is set. */
  body.privacy-on .pii{
    filter:blur(7px);
    -webkit-filter:blur(7px);
    transition:filter .12s ease;
    user-select:none;pointer-events:none;
  }
  /* Images blur a bit harder so the product isn't recognisable. */
  body.privacy-on .pii-img img,
  body.privacy-on .pii-img > i{
    filter:blur(12px);
    -webkit-filter:blur(12px);
  }
  /* A tile/card marked .unblurred (via its eye button) reveals everything
     inside it, overriding the global blur. */
  body.privacy-on .unblurred .pii,
  body.privacy-on .unblurred.pii{filter:none;-webkit-filter:none;pointer-events:auto;user-select:auto}
  body.privacy-on .unblurred .pii-img img,
  body.privacy-on .unblurred .pii-img > i{filter:none;-webkit-filter:none}
  /* The eye button sits in the corner of each tile image; only shown in privacy mode. */
  .peek{display:none}
  body.privacy-on .peek{
    display:flex;position:absolute;top:6px;right:6px;z-index:6;
    width:26px;height:26px;align-items:center;justify-content:center;
    border-radius:7px;cursor:pointer;
    background:rgba(10,14,20,.82);color:#ffd479;border:1px solid #5a4a1e;
  }
  body.privacy-on .peek:hover{background:rgba(20,28,40,.95)}
  body.privacy-on .peek .ti{font-size:15px;pointer-events:none}


  /* ---- home screen ---- */
  #home{padding:26px 30px;display:none}
  #home.show{display:block}
  .homehd{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:0 0 16px}
  .wsgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
  .wscard{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;cursor:pointer;
          transition:border-color .12s,transform .12s;display:flex;flex-direction:column;gap:12px}
  .wscard:hover{border-color:#3d4658;transform:translateY(-1px)}
  .wsedit{background:var(--panel2);border:1px solid var(--line);color:var(--muted);border-radius:8px;width:30px;height:30px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex:0 0 auto}
  .wsedit:hover{color:var(--ink);border-color:#3d4658}
  .wscard .ic{width:38px;height:38px;border-radius:9px;display:flex;align-items:center;justify-content:center;
              font-size:15px;font-weight:700}
  .wscard .nm{font-weight:600;font-size:14.5px}
  .wscard .sub{color:var(--muted);font-size:12px;margin-top:1px}
  .wscard .stats{display:flex;gap:14px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:10px}
  .wscard.add{border-style:dashed;align-items:center;justify-content:center;color:var(--muted);
              flex-direction:row;gap:8px;min-height:118px}
  .wscard.add:hover{color:var(--ink)}
  /* reserve space for any icon so a missing CDN glyph never collapses layout */
  .ti{display:inline-block;min-width:1em;min-height:1em;line-height:1}
  .wscard .ic .ti{font-size:18px}

  /* ---- workspace screen ---- */
  #workspace{display:none}
  #workspace.show{display:flex;min-height:calc(100vh - 49px)}
  .sidebar{width:188px;flex-shrink:0;background:var(--sidebar);border-right:1px solid var(--line);
           padding:16px 12px;position:sticky;top:49px;height:calc(100vh - 49px);overflow:auto}
  .backlink{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:12.5px;cursor:pointer;margin-bottom:16px}
  .backlink:hover{color:var(--ink)}
  .wsident{display:flex;align-items:center;gap:9px;margin-bottom:18px}
  .wsident .ic{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700}
  .wsident .nm{font-weight:600;font-size:13.5px}
  .navitem{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:8px;font-size:13px;
           color:var(--muted);cursor:pointer;margin-bottom:2px}
  .navitem:hover{background:var(--panel2);color:var(--ink)}
  .navitem.active{background:rgba(76,141,255,.14);color:#9cc1ff}
  .navitem .ti{font-size:16px;width:18px;text-align:center}
  .wsmain{flex:1;min-width:0;display:flex;flex-direction:column}
  .wstoolbar{position:sticky;top:49px;z-index:10;background:var(--panel);border-bottom:1px solid var(--line);
             padding:12px 20px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .wstoolbar h2{font-size:15px;margin:0;font-weight:650}
  .wstoolbar .sub{color:var(--muted);font-size:12px}
  .wstoolbar .spacer{flex:1}
  .pill{padding:4px 10px;border-radius:999px;border:1px solid var(--line);
        background:var(--panel2);color:var(--muted);cursor:pointer;font-size:13px}
  .pill.active{color:#fff;border-color:var(--accent);background:rgba(76,141,255,.15)}
  #summary{padding:8px 20px;color:var(--muted);border-bottom:1px solid var(--line);
           background:var(--panel);font-size:13px}
  #log{display:none;margin:0;padding:12px 20px;background:#0b0d11;color:#cbd3e1;
       border-bottom:1px solid var(--line);max-height:230px;overflow:auto;
       font:12px/1.5 ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap}
  #log .l{opacity:.92}
  #log .start,#log .done{color:#7fd1a0}
  main#grid{padding:18px 20px;display:grid;gap:14px;
       grid-template-columns:repeat(auto-fill,minmax(360px,1fr));align-content:start}
  /* secondary panels inside workspace (image refs / brand setup / generate) */
  .wspanel{display:none;padding:20px}
  .wspanel.show{display:block}

  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
        padding:14px;display:flex;flex-direction:column;gap:10px}
  .card.flag{border-color:#5a2230}
  .top{display:flex;align-items:center;gap:8px}
  .badge{font-size:11px;font-weight:700;letter-spacing:.02em;padding:3px 9px;
         border-radius:999px;text-transform:uppercase;white-space:nowrap}
  .b-APPROVED{background:var(--greenbg);color:#7fd1a0;border:1px solid #285c39}
  .b-NEEDS_REVIEW{background:var(--amberbg);color:#e3b768;border:1px solid #5c4a16}
  .b-IP_HOLD,.b-COMPLIANCE_HOLD,.b-ERROR{background:var(--redbg);color:#ef9a9a;border:1px solid #5c2424}
  .b-none{background:var(--panel2);color:var(--muted);border:1px solid var(--line)}
  .risk{font-size:11px;font-weight:700;padding:3px 8px;border-radius:6px}
  .risk.hi{background:var(--redbg);color:#ef9a9a;border:1px solid #5c2424}
  .risk.med{background:var(--amberbg);color:#e3b768;border:1px solid #5c4a16}
  .title{font-weight:600;font-size:14px}
  .meta{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--muted);font-size:12.5px}
  .meta b{color:var(--ink);font-weight:600}
  .findings{background:var(--redbg);border:1px solid #5c2424;border-radius:8px;
            padding:8px 10px;font-size:12.5px;color:#f0c4c4;white-space:pre-wrap}
  .findings .h{font-weight:700;color:#ef9a9a;margin-bottom:2px}
  .errlist{display:flex;flex-direction:column;gap:5px;white-space:normal}
  .erritem{background:#2a1414;border:1px solid #5c2424;border-radius:6px;padding:6px 9px;
           font-size:12px;color:#f0c4c4;line-height:1.35}
  .erritem.w{background:#2a2414;border-color:#5c5024;color:#e8d9a8}
  .errfield{font-weight:700;color:#ffb4b4;font-family:ui-monospace,Menlo,monospace;font-size:11.5px}
  .erritem.w .errfield{color:#ffe08a}
  details summary{cursor:pointer;color:var(--muted);font-size:12.5px}
  ul.bul{margin:6px 0 0;padding-left:18px;color:var(--ink);font-size:12.5px}
  ul.bul li{margin:2px 0}
  .acts{display:flex;gap:8px;margin-top:2px}
  .acts a{margin-left:auto;color:var(--accent);text-decoration:none;font-size:12.5px;align-self:center}
  .ok{background:var(--green);border-color:var(--green);color:#fff}
  .hold{background:transparent}
  .empty{color:var(--muted);padding:40px;text-align:center;grid-column:1/-1}
  .toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);
         background:#222a36;border:1px solid var(--line);color:var(--ink);
         padding:9px 16px;border-radius:8px;opacity:0;transition:.2s;pointer-events:none;z-index:80}
  .toast.show{opacity:1}
  .b-API_READY{background:rgba(76,141,255,.12);color:#9cc1ff;border:1px solid #2f4a73}
  .b-API_ERROR{background:var(--redbg);color:#ef9a9a;border:1px solid #5c2424}
  .b-LIVE{background:#10301f;color:#74e0a3;border:1px solid #1f7a3d}
  table.kv{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px;table-layout:fixed}
  table.kv td{padding:3px 8px;border-bottom:1px solid var(--line);vertical-align:top}
  table.kv td.k{color:var(--muted);width:38%;word-break:break-word;overflow-wrap:anywhere}
  table.kv td.v{color:var(--ink);width:62%;word-break:break-word;overflow-wrap:anywhere}
  .kvsec{margin-top:10px;color:#9cc1ff;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
  pre.raw{display:none;margin:8px 0 0;padding:8px;background:#0b0d11;border:1px solid var(--line);
          border-radius:6px;font:11.5px/1.45 ui-monospace,Consolas,monospace;color:#cbd3e1;
          white-space:pre-wrap;max-height:280px;overflow:auto}
  .rawtoggle{margin-top:8px;color:var(--accent);cursor:pointer;font-size:12px;display:inline-block}
  .payloadbox{margin-top:10px;border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:#0c1016}
  .payloadbox>summary{color:#8fd0ff;font-size:12px}
  .payloadnote{color:#8a93a6;font-size:11px;margin:6px 0;line-height:1.5}
  pre.payloadraw{display:block;max-height:340px}
  input.ed,select.ed,textarea.ed{width:100%;background:#0f141b;border:1px solid var(--line);
    color:var(--ink);border-radius:5px;padding:4px 6px;font:inherit;font-size:12.5px}
  textarea.ed{resize:vertical;line-height:1.4}
  input.ed:focus,select.ed:focus,textarea.ed:focus{outline:none;border-color:var(--accent)}
  .ed.saved{border-color:#1f7a3d !important}
  .ed.err{border-color:#a12a2a !important}
  .ed.saving{opacity:.55}
  select.ed{cursor:pointer}
  td.k{padding-top:9px;white-space:nowrap}
  .ro{color:var(--muted)}
  .safe{background:#10301f;border:1px solid #1f7a3d;border-radius:8px;padding:8px 10px;font-size:12.5px;color:#9fe0b8}
  td.wcell{padding:6px 8px}
  .wlab{color:var(--muted);font-size:11.5px;margin-bottom:3px}
  textarea.ed{min-height:42px}
  .reqrow .ed{border-color:#9a6b00}
  .fixhint{color:#e0a3a3;font-size:11px;font-weight:600;display:block;margin-top:2px;white-space:normal;overflow-wrap:anywhere}
  .nesthint{display:inline-block;margin-left:8px;color:#86d0a8;font-size:10.5px;font-weight:500;font-style:italic;white-space:normal;overflow-wrap:anywhere;cursor:help}
  .reqtag{display:inline-block;white-space:normal}
  .klabel{overflow-wrap:anywhere}
  .flaggedrow .ed{border-color:#9a6b00}
  .flaggedrow .k{color:#e9c965}
  .subhead td{padding-top:8px;border-top:1px solid #2a3142;color:#9cc1ff;font-size:12px}
  .subhead.flaggedrow td{color:#e9c965}
  .imgrow{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 8px}
  .imgrow a{position:relative;display:block;text-decoration:none}
  .thumbwrap{position:relative;display:inline-block}
  .thumbedit{position:absolute;top:3px;right:3px;border-radius:6px;background:rgba(16,42,48,.9);
            border:1px solid #2a6a78;color:#8fe0f0;cursor:pointer;font-size:11px;padding:2px 5px;
            display:inline-flex;align-items:center;line-height:1}
  .thumbedit:hover{background:#143842}
  .thumb{width:88px;height:88px;object-fit:cover;border:1px solid #2c3340;border-radius:6px;background:#0e1217}
  .thumbcap{position:absolute;left:4px;bottom:4px;font-size:10px;background:rgba(0,0,0,.7);color:#cdd6e4;padding:1px 5px;border-radius:4px}
  .askthis{background:#3a2d5e;color:#e8e0ff;border:1px solid #5a4a8a}
  .reqnote{font-size:12px;color:#d9b441;background:#2a2410;border:1px solid #5c4a16;border-radius:8px;padding:8px 10px;margin:8px 0;line-height:1.5}
  .schemadiag{font-size:11.5px;border-radius:8px;padding:7px 10px;margin:6px 0;line-height:1.5}
  .schemadiag.ok{color:#7fb98a;background:#13241a;border:1px solid #244e30}
  .schemadiag.bad{color:#ffcf99;background:#2c1f10;border:1px solid #6b4a1a}
  .schemadiag.bad b{color:#ffd9a8}
  .reqnote b{color:#e9c965}
  .reqtag{color:#e3b768;font-size:10px;border:1px solid #5c4a16;padding:0 4px;border-radius:4px;margin-left:4px}
  .addfield{margin:8px 0 2px}
  .addfield select{background:#0f1420;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:12px;max-width:100%}
  .addfield .hint{color:var(--muted);font-size:11px;margin:4px 0 0}
  .cc{color:var(--muted);font-size:10.5px;margin-left:6px;font-weight:400}
  .cc.over{color:#e0696b}
  .cc.warn{color:#e3b768}
  .idxnote{display:inline-block;margin-left:8px;font-size:9.5px;color:#7fa7d9;background:#11203a;
           border:1px solid #243d63;border-radius:6px;padding:1px 7px;font-weight:500;cursor:help;vertical-align:middle}
  .cwarn{font-size:10.5px;color:#e3b768;background:#1f1810;border:1px solid #5c4a24;border-radius:6px;
         padding:4px 8px;margin:4px 0 2px}
  .bulletmeter{margin:2px 0 8px;padding:7px 10px;background:#0f1726;border:1px solid #1f2f48;border-radius:8px}
  .idxbar{height:7px;border-radius:4px;background:#1b2942;overflow:hidden;margin-bottom:4px}
  .idxfill{height:100%;background:linear-gradient(90deg,#3f7bd6,#5c8fe6);border-radius:4px;transition:width .2s}
  .idxfill.over{background:linear-gradient(90deg,#d68a3f,#e0696b)}
  .idxlbl{font-size:10px;color:#8fb0dc}
  .idxlbl.over{color:#e3b768}
  .reqstar{color:#ff5a5f;font-size:11px;margin-left:5px;vertical-align:super;font-weight:700}
  .ishtable{border-collapse:collapse;width:100%;font-size:12px}
  .ishtable th,.ishtable td{border:1px solid var(--line,#2a2f3a);padding:5px 9px;text-align:left;white-space:nowrap;max-width:340px;overflow:hidden;text-overflow:ellipsis}
  .ishtable thead th{position:sticky;top:0;background:#1a1f29;color:#cdd6e4;font-weight:600;z-index:2}
  .ishtable tbody tr:nth-child(even){background:rgba(255,255,255,.02)}
  .ishtable tbody tr:hover{background:rgba(120,160,255,.07)}
  .ishtable .isgut{background:#141821;color:#7b8699;text-align:right;position:sticky;left:0;font-variant-numeric:tabular-nums;font-weight:600;z-index:1}
  .ishtable thead .isgut{z-index:3}
  .reqsoft{color:#8a93a6;font-size:10px;margin-left:6px;font-weight:600;font-style:italic}
  .srcbadge{display:inline-block;margin-left:6px;font-size:9px;font-weight:700;padding:1px 6px;border-radius:5px;vertical-align:middle;letter-spacing:.3px}
  .src-ebay{background:#0d2a1a;color:#5fd39a;border:1px solid #1f5c3a}
  .src-amazon{background:#2a230d;color:#e0b34c;border:1px solid #5c4a1f}
  .src-ai{background:#1a1330;color:#b89cff;border:1px solid #3a2f5c}
  .refpicker{margin:6px 0 12px;padding:8px;background:#0f1726;border:1px solid #1f2f48;border-radius:8px}
  .refrow{display:flex;gap:8px;flex-wrap:wrap}
  .refthumb{position:relative;width:72px;height:72px;border-radius:8px;overflow:hidden;border:2px solid #243d63;cursor:pointer;transition:border-color .15s}
  .refthumb:hover{border-color:#4c8dff}
  .refthumb.on{border-color:#5fd39a;box-shadow:0 0 0 2px rgba(95,211,154,.25)}
  .refthumb img{width:100%;height:100%;object-fit:cover}
  .refbadge{position:absolute;bottom:0;left:0;right:0;background:rgba(15,40,26,.92);color:#5fd39a;font-size:8px;text-align:center;font-weight:700;padding:1px 0}
  .imgmeta{font-size:10px;color:#8fb0dc;background:#0f1726;border:1px solid #1f2f48;border-radius:5px;padding:2px 7px;display:inline-block;margin-top:4px;font-weight:600}
  .acts .del{background:#3a1d1d;border:1px solid #5c2b2b;color:#e0a3a3}
  .acts .del:hover{background:#4a2525}
  .emptynote{color:var(--muted);font-size:12px;padding:8px 10px;margin-bottom:10px;border:1px dashed var(--line);border-radius:8px}
  .linkbtn{background:none;border:none;color:#6ea8fe;cursor:pointer;font-size:12px;padding:0;text-decoration:underline}
  .fab{position:fixed;right:20px;bottom:20px;z-index:60;background:#6c5ce7;color:#fff;border:none;cursor:pointer;
       font-size:13px;font-weight:600;padding:11px 16px;border-radius:24px;box-shadow:0 6px 20px rgba(0,0,0,.45)}
  .fab:hover{filter:brightness(1.08)}
  .chatwrap{position:fixed;right:20px;bottom:74px;z-index:60;width:384px;max-width:92vw;height:560px;max-height:80vh;
            display:none;flex-direction:column;background:#15161a;border:1px solid #2a2c33;border-radius:14px;
            box-shadow:0 14px 44px rgba(0,0,0,.55);overflow:hidden}
  .chatwrap.open{display:flex}
  .chathead{padding:10px 12px;background:#1d1f25;border-bottom:1px solid #2a2c33;display:flex;align-items:center;gap:8px}
  .chathead b{font-size:14px}
  .chathead select{margin-left:auto;background:#0f1013;color:#cfd2da;border:1px solid #2a2c33;border-radius:8px;font-size:11px;padding:4px 6px;max-width:170px}
  .chathead .x{background:none;border:none;color:#9aa0aa;cursor:pointer;font-size:20px;padding:0 2px;line-height:1}
  .chatbody{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
  .chatempty{color:#7a808a;font-size:12px;line-height:1.6;text-align:center;margin:auto 8px}
  .msg{max-width:86%;padding:8px 11px;border-radius:12px;font-size:13px;line-height:1.55;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere}
  .msg.u{align-self:flex-end;background:#2b2f6e;color:#eef}
  .msg.a{align-self:flex-start;background:#202228;color:#dfe2ea;border:1px solid #2a2c33}
  .msg img{max-width:100%;border-radius:8px;margin-top:6px;display:block}
  .chatfoot{border-top:1px solid #2a2c33;padding:8px;display:flex;flex-direction:column;gap:6px}
  .chips{display:flex;flex-wrap:wrap;gap:6px}
  .chip{font-size:11px;background:#202228;border:1px solid #2a2c33;border-radius:8px;padding:3px 6px;color:#cfd2da;display:flex;align-items:center;gap:5px}
  .chip button{background:none;border:none;color:#9aa0aa;cursor:pointer;padding:0;font-size:13px}
  .chatin{display:flex;gap:6px;align-items:flex-end}
  .chatin textarea{flex:1;resize:none;background:#0f1013;color:#e8eaf0;border:1px solid #2a2c33;border-radius:10px;
                   padding:8px;font-size:13px;font-family:inherit;min-height:38px;max-height:120px}
  .chatin .ic{background:#202228;border:1px solid #2a2c33;color:#cfd2da;border-radius:9px;cursor:pointer;height:38px;width:38px;font-size:15px}
  .chatin .snd{background:#6c5ce7;border:none;color:#fff;border-radius:9px;cursor:pointer;height:38px;padding:0 14px;font-size:13px;font-weight:600}
  .chatin .snd:disabled{opacity:.5;cursor:default}
  .chathint{font-size:10px;color:#7a808a;padding:0 2px;line-height:1.4}
  .rememberbtn{margin-top:10px;background:#15241a;border:1px solid #2f5c3a;color:#7fd99a;border-radius:8px;padding:7px 11px;font-size:12px;cursor:pointer;font-weight:600}
  .curlbl{display:inline-block;margin-right:6px;color:#9aa3b2;font-weight:600}
  .genimg{margin-top:10px}
  .genimgbtn{background:#1b1530;border:1px solid #4a3a7a;color:#c8b6ff;border-radius:8px;padding:7px 12px;font-size:12.5px;cursor:pointer;font-weight:600;margin-right:6px}
  .genimgbtn.apply{background:#15241a;border-color:#2f5c3a;color:#7fd99a}
  .genpanel{margin-top:8px;padding:10px;border:1px solid var(--line);border-radius:8px;background:#0e1217}
  .genrow{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:6px 0}
  .geninput{width:100%;margin:5px 0;display:block}
  .genpreview img{max-width:260px;border:1px solid var(--line);border-radius:8px;background:#fff;margin:8px 0;display:block}
  .genprompt{white-space:pre-wrap;font-size:11px;color:#9aa3b2;max-height:160px;overflow:auto;background:#0a0d12;padding:8px;border-radius:6px;border:1px solid var(--line)}
  .genspin{display:inline-block;width:12px;height:12px;border:2px solid #4a3a7a;border-top-color:#c8b6ff;
           border-radius:50%;animation:genspin .7s linear infinite;vertical-align:-2px;margin-right:5px}
  @keyframes genspin{to{transform:rotate(360deg)}}
  #genstatus_,.genrow .cc{line-height:1.5}
  .gendiag{font-size:11.5px;padding:7px 10px;border-radius:7px;margin-bottom:8px}
  .gendiag.ok{background:#10301f;border:1px solid #1f7a3d;color:#7fd99a}
  .gendiag.bad{background:#2e1414;border:1px solid #5c2424;color:#ef9a9a}
  .suggestbtn{background:#15233a;border:1px solid #2f4a73;color:#9cc1ff;font-weight:600;display:inline-flex;align-items:center;gap:6px}
  .minlbl{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);
          background:#1a1410;border:1px solid #5c4a24;border-radius:8px;padding:5px 10px;cursor:pointer}
  .minlbl input{cursor:pointer}
  .suggestbtn:hover{filter:brightness(1.15)}
  .suggestbox{margin-top:12px}
  .sgtop{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:13px}
  .sgtop .sgall{margin-left:auto;background:#15233a;border:1px solid #2f4a73;color:#9cc1ff;font-size:12px;padding:5px 11px;border-radius:7px;cursor:pointer;font-weight:600}
  .sgrow{border:1px solid var(--line);border-radius:9px;padding:9px 11px;margin-bottom:8px;background:#0e1217}
  .sgrow.applied{border-color:#1f7a3d;opacity:.75}
  .sghead{display:flex;align-items:center;gap:8px;margin-bottom:6px}
  .sgfield{font-family:ui-monospace,Consolas,monospace;font-size:12px;font-weight:600;color:#e8eaed}
  .srcbadge{font-size:10px;padding:2px 8px;border-radius:999px;font-weight:600}
  .confbadge{font-size:10.5px;font-weight:600;margin-left:auto}
  .sgval{min-height:38px;font-size:12.5px}
  .sgnote{font-size:11px;color:var(--muted);margin-top:4px}
  .sgacts{margin-top:6px}
  .sgapply{background:var(--green);border:1px solid var(--green);color:#fff;font-size:12px;padding:5px 12px;border-radius:7px;cursor:pointer;font-weight:600}
  .sgapply:disabled{opacity:.7}
  .uploadbtn{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:6px 11px;
             background:var(--panel2);border:1px solid var(--line);border-radius:8px;color:#c8d3e6;cursor:pointer;white-space:nowrap}
  .uploadbtn:hover{border-color:#3d4658;color:#fff}
  .mediafolder{border:1px solid var(--line);border-radius:9px;margin-bottom:8px;background:var(--panel);overflow:hidden}
  .mediafolder>summary{cursor:pointer;padding:10px 12px;font-size:13px;font-weight:600;list-style:none;display:flex;align-items:center;gap:8px}
  .mediafolder>summary::-webkit-details-marker{display:none}
  .mediafolder>summary .ti{color:#e3b768}
  .mediagrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;padding:0 12px 12px}
  .mediacell{position:relative;border:1px solid var(--line);border-radius:7px;overflow:hidden;background:#0e1217;aspect-ratio:1}
  .mediameta{position:absolute;left:0;right:0;bottom:0;background:rgba(8,10,14,.82);color:#b8c2d4;font-size:9.5px;padding:2px 4px;text-align:center;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mediacell img{width:100%;height:100%;object-fit:cover;cursor:pointer;display:block}
  .mediadel{position:absolute;top:4px;right:4px;width:22px;height:22px;border-radius:6px;
            background:rgba(0,0,0,.6);border:none;color:#e0a3a3;cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center}
  .mediadel:hover{background:#3a1d1d}
  .mediaedit{position:absolute;top:4px;left:4px;border-radius:6px;background:rgba(16,42,48,.85);
            border:1px solid #2a6a78;color:#8fe0f0;cursor:pointer;font-size:10.5px;padding:2px 6px;
            display:inline-flex;align-items:center;gap:3px;line-height:1.4}
  .mediaedit:hover{background:#143842}
  .medagroup{position:absolute;top:3px;left:3px;font-size:9px;background:rgba(74,58,122,.92);color:#d9ccff;
            padding:1px 5px;border-radius:5px;border:1px solid #5a4a8a;letter-spacing:.2px}
  .acctbanner{margin-top:12px;padding:10px 12px;border-radius:9px;font-size:13px;border:1px solid var(--line);background:var(--panel2);color:var(--muted)}
  .acctbanner.ok{background:#10301f;border-color:#1f7a3d;color:#bfe9cf}
  .acctbanner.ok b{color:#fff}
  .acctbanner.bad{background:#2e1414;border-color:#5c2424;color:#f0c4c4}
  .acctbanner .ti{vertical-align:-2px;margin-right:5px}
  .tile.live{opacity:.92}
  .tile.live .tileimg.noimg{color:#74e0a3}
  .srcgroup{grid-column:1/-1;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#9cc1ff;
            font-weight:700;margin:8px 2px 2px;padding-top:6px;border-top:1px solid var(--line)}
  .connpill{font-size:10px;padding:3px 9px;border-radius:999px;font-weight:600;display:inline-flex;align-items:center;gap:4px;white-space:nowrap}
  .connpill.on{background:#10301f;color:#7fd99a}
  .connpill.off{background:#2a2410;color:#e3b768}
  .connpill .ti{font-size:12px}
  .livestatus{font-size:10px;padding:2px 7px;border-radius:999px;font-weight:600}
  .profchip{font-size:10.5px;padding:2px 8px;border-radius:999px;font-weight:700;border:1px solid var(--line);display:inline-block}
  .noimgmsg{display:flex;flex-direction:column;align-items:center;gap:4px;color:#8a93a6;font-size:11px}
  .noimgmsg .ti{font-size:22px}
  .studiotabs{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
  .stab{background:var(--panel2);border:1px solid var(--line);color:var(--muted);padding:7px 12px;border-radius:8px;cursor:pointer;font-size:13px}
  .stab.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  .studiopane label{font-size:12px;display:block;margin-bottom:3px}
  .studiogrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
  .srescard{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--panel2)}
  .sresimg{width:100%;height:180px;object-fit:contain;background:#fff;display:block}
  .srescap{font-size:11px;color:var(--muted);padding:5px 8px}
  .sresacts{display:flex;flex-wrap:wrap;gap:6px;padding:0 8px 8px;align-items:center}
  .sresacts .ib{white-space:nowrap}
  .sresfail{padding:18px 10px;color:#e0696b;font-size:12px;text-align:center}
  .recipecard{display:flex;gap:10px;align-items:center;border:1px solid var(--line);border-radius:9px;padding:8px;margin-bottom:8px}
  .recipecard img{width:54px;height:54px;object-fit:cover;border-radius:7px;background:#fff}
  .studiomodels{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;padding:10px;background:var(--panel2);border:1px solid var(--line);border-radius:9px}
  .smodel label{font-size:11px;display:block;margin-bottom:3px}
  .smodelhint{font-size:10.5px;margin-top:3px;line-height:1.4}
  .ideabox{background:#16202c;border:1px solid #2a3a4d;border-radius:9px;padding:11px 13px;margin-bottom:8px}
  .buildbox{background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:11px 13px}
  .ordiv{display:flex;align-items:center;text-align:center;margin:14px 0;color:var(--muted);font-size:12px;font-weight:600}
  .ordiv::before,.ordiv::after{content:"";flex:1;border-bottom:1px solid var(--line)}
  .ordiv span{padding:0 12px}
  .howbox{margin-top:8px;border:1px solid var(--line);border-radius:7px;background:rgba(255,255,255,.02)}
  .howbox summary{cursor:pointer;padding:7px 10px;font-size:11.5px;color:var(--muted);list-style:none;user-select:none;display:flex;align-items:center;gap:6px}
  .howbox summary::-webkit-details-marker{display:none}
  .howbox summary .chev{transition:transform .15s;display:inline-block}
  .howbox[open] summary .chev{transform:rotate(90deg)}
  .howbox .howbody{padding:2px 12px 11px 12px;font-size:11.5px;line-height:1.55;color:var(--muted)}
  .howbox .howbody ol{margin:4px 0 0 0;padding-left:18px}
  .howbox .howbody li{margin-bottom:5px}
  .howbox .howbody b{color:var(--text)}
  .howbox .howbody code{background:rgba(255,255,255,.06);padding:1px 5px;border-radius:4px;font-size:10.5px}
  .adminbox{margin-top:14px;border:1px solid #3a3050;background:rgba(120,90,200,.08);border-radius:9px;padding:11px 13px}
  .conceptcard{display:flex;gap:10px;align-items:flex-start;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:9px 11px;margin-bottom:7px}
  .conceptcard .ib{white-space:nowrap;align-self:center}
  .secroles{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:4px}
  .seccheck{display:flex;align-items:center;gap:6px;font-size:13px;background:var(--panel2);border:1px solid var(--line);padding:6px 9px;border-radius:7px;cursor:pointer}
  .seccomp8.row{display:flex;gap:6px;align-items:center;margin-top:6px}
  .secrow{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .aplusnote{background:#1a2230;border:1px solid #2c3a4f;border-radius:8px;padding:10px 12px;font-size:12px;color:#bcc7d6;line-height:1.5}
  .apmods{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:5px}
  .apmod{display:flex;gap:8px;align-items:flex-start;background:var(--panel2);border:1px solid var(--line);padding:8px 10px;border-radius:8px;cursor:pointer}
  .apmod input{margin-top:3px}
  .apdim{display:inline-block;font-size:10px;color:#7fd99a;background:#16291d;border:1px solid #2c5840;padding:1px 6px;border-radius:999px;margin-left:4px}
  .apcopy{font-size:11px;color:#c7d0dc;padding:6px 8px;border-top:1px dashed var(--line);line-height:1.45}
  .issuesbox{border-radius:9px;padding:11px 13px;margin-bottom:12px;font-size:12.5px;line-height:1.5}
  .issuesbox.ok{background:#16241a;border:1px solid #2c5036;color:#bfe3c9}
  .issuesbox.warn{background:#2a2014;border:1px solid #5c4528;color:#e9d5b6}
  .issgrp{margin-top:8px}
  .issgrp-h{font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px}
  .issgrp-h.err{color:#ef9a9a}
  .issgrp-h.warn{color:#e3b768}
  .issrow{background:rgba(0,0,0,.18);border-radius:6px;padding:6px 9px;margin-bottom:4px}
  .issmsg{font-size:12px}
  .issattr{font-size:10.5px;color:#9aa7b6;margin-top:2px}
  .issattr code,.optfix~* code{background:#1c2430;padding:0 4px;border-radius:4px}
  .optsec{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#9cc1ff;font-weight:700;margin:4px 0 8px}
  .srcbox{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:14px}
  .optall{margin-top:14px;border:1px solid var(--line);border-radius:9px;padding:4px 10px}
  .optall>summary{cursor:pointer;font-size:13px;font-weight:600;padding:6px 0}
  .optattr{font-size:12px}
  .subrow .k{padding-left:18px;color:#9fb0c8;font-size:12.5px}
  .subrow .subarrow{color:#5b6b82;margin-right:3px}
  .optdiff{border:1px solid var(--line);border-radius:9px;padding:10px 12px;margin-bottom:8px}
  .optdiff.chg{border-color:#5a4a2a;background:#1c1810}
  .optdiff.same{opacity:.6}
  .optcheck{display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:6px;cursor:pointer}
  .optcheck input{width:16px;height:16px;accent-color:var(--accent)}
  .chgflag{font-size:10px;background:#5a4a2a;color:#e3b768;padding:1px 7px;border-radius:999px;font-weight:600}
  .optold{font-size:12px;color:#caa;margin:2px 0;padding:4px 8px;background:#1a1414;border-radius:6px}
  .optnew{font-size:12px;color:#aca;padding:4px 8px;background:#141a14;border-radius:6px}
  .rememberbtn:hover{filter:brightness(1.12)}
  .rememberbtn:disabled{opacity:.6;cursor:default}
  #stopbtn:disabled{opacity:.4;cursor:default}
  .ibtn{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;
        border-radius:50%;font-size:10px;font-weight:700;cursor:help;margin-left:6px;
        border:1px solid var(--line);font-style:normal}
  .ibtn.iok{color:#9cc1ff;border-color:#2f4a73}
  .ibtn.iwarn{color:#e3b768;border-color:#5c4a16;background:var(--amberbg)}
  .heroimg{margin:6px 0 2px}
  .heroimg img{max-width:100%;max-height:190px;object-fit:contain;border:1px solid var(--line);border-radius:8px;background:#0e1217;display:block}
  .findsum{font-size:12.5px;font-weight:600;padding:7px 11px;border-radius:8px;cursor:pointer;list-style:none;margin:2px 0}
  .findsum.good{background:#10301f;border:1px solid #1f7a3d;color:#7fd99a;cursor:default}
  .findsum.bad{background:var(--redbg);border:1px solid #5c2424;color:#ef9a9a}
  .findsum.info{background:var(--amberbg);border:1px solid #5c4a16;color:#e3b768}
  .findings.info{background:var(--amberbg);border:1px solid #5c4a16}
  .findingsbox .findings{margin-top:6px}
  details.findingsbox>summary::-webkit-details-marker{display:none}
  /* ---- GALLERY GRID ---- */
  main#grid{grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;max-width:none;align-content:start}
  .tile{background:var(--panel);border:1px solid var(--line);border-radius:11px;overflow:hidden;
        display:flex;flex-direction:column;transition:border-color .12s,transform .12s}
  .tile:hover{border-color:#3d4658;transform:translateY(-1px)}
  .tile.sel{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
  .tile.flag{border-color:#5a3030}
  .tileimg{position:relative;height:180px;background:#1c2531;display:flex;align-items:center;
           justify-content:center;cursor:pointer;overflow:hidden}
  .tileimg img{width:100%;height:100%;object-fit:contain;background:#fff}
  .tileimg.noimg{color:#4a5260;font-size:34px}
  .tiledot{position:absolute;top:8px;left:8px;width:10px;height:10px;border-radius:50%;border:2px solid var(--panel)}
  .tilesel{position:absolute;top:8px;right:8px;width:22px;height:22px;cursor:pointer;accent-color:var(--accent);z-index:5;background:rgba(10,14,20,.6);border-radius:5px;box-shadow:0 0 0 2px rgba(255,255,255,.15)}
  .tile:hover .tilesel{box-shadow:0 0 0 2px var(--accent)}
  .tileflag{position:absolute;bottom:8px;right:8px;color:#e3b768;background:rgba(0,0,0,.55);
            border-radius:6px;width:22px;height:22px;display:flex;align-items:center;justify-content:center;font-size:13px}
  .tilebody{padding:11px 13px 6px;cursor:pointer;flex:1;display:flex;flex-direction:column;gap:2px}
  .tiletitle{font-size:13.5px;font-weight:600;line-height:1.4;min-height:38px;overflow:hidden;
             display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
  .tilemeta{display:flex;justify-content:space-between;align-items:center;margin-top:5px;gap:8px}
  .fmode{font-size:10px;padding:1px 7px;border-radius:999px;font-weight:700;border:1px solid var(--line)}
  .shipline{font-size:11px;line-height:1.4}
  .tileprice{font-size:12.5px;font-weight:600}
  .tilesku{font-size:10.5px;color:var(--muted);font-family:ui-monospace,Consolas,monospace}
  .tileacts{display:flex;gap:3px;padding:7px 9px 9px}
  .tileacts .ib{flex:1}
  .ib{height:30px;padding:0;display:flex;align-items:center;justify-content:center;
      background:var(--panel2);border:1px solid var(--line);border-radius:7px;color:#c2c9d6;
      cursor:pointer;font-size:14px;text-decoration:none}
  .ib:hover{border-color:#3d4658;color:#fff}
  .ib.gen{color:#c8b6ff;border-color:#4a3a7a}
  .ib.del:hover,.ib.more:hover{color:#fff}
  /* tile context menu */
  .tilemenu{position:fixed;z-index:85;background:var(--panel);border:1px solid var(--line);
            border-radius:9px;padding:5px;min-width:170px;box-shadow:0 10px 30px rgba(0,0,0,.5)}
  .tilemenu button{display:flex;align-items:center;gap:9px;width:100%;text-align:left;
                   background:transparent;border:none;color:var(--ink);font-size:12.5px;padding:8px 10px;border-radius:6px;cursor:pointer}
  .tilemenu button:hover{background:var(--panel2)}
  .tilemenu button.danger{color:#e0a3a3}
  .tilemenu .ti{font-size:15px}
  /* ---- SIDE DRAWER ---- */
  .drawerscrim{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:70;opacity:0;
               pointer-events:none;transition:opacity .18s}
  .drawerscrim.open{opacity:1;pointer-events:auto}
  .drawer{position:fixed;top:0;right:0;height:100vh;width:520px;max-width:94vw;z-index:75;
          background:var(--panel);border-left:1px solid var(--line);overflow:auto;
          transform:translateX(100%);transition:transform .2s ease;padding:16px 18px}
  .drawer.open{transform:translateX(0)}
  .dwhead{margin-bottom:10px}
  .dwtop{display:flex;align-items:center;gap:8px;margin-bottom:10px}
  .dwtop .spacer{flex:1}
  .dwtitle{font-size:16px;font-weight:650;line-height:1.3;margin-bottom:6px}
  .dwactions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}
  .dwactions button,.dwactions .srcbtn{font-size:12.5px;padding:7px 12px;border-radius:8px;cursor:pointer;text-decoration:none}
  .dwactions .ok{background:var(--green);border:1px solid var(--green);color:#fff;font-weight:600}
  .dwactions .genmain{background:#1b1530;border:1px solid #4a3a7a;color:#c8b6ff;font-weight:600;display:inline-flex;align-items:center;gap:6px}
  .dwactions .pushimg{background:#102a30;border:1px solid #2a6a78;color:#8fe0f0;font-weight:600;display:inline-flex;align-items:center;gap:6px}
  .dwactions .pushimg:disabled{opacity:.6;cursor:default}
  .dwactions .genmain:hover{filter:brightness(1.15)}
  .dwactions .hold{background:var(--panel2);border:1px solid var(--line);color:var(--ink)}
  .dwactions .askthis{background:#3a2d5e;border:1px solid #5a4a8a;color:#e8e0ff}
  .dwactions .del{background:#3a1d1d;border:1px solid #5c2b2b;color:#e0a3a3}
  .dwactions .srcbtn{background:var(--panel2);border:1px solid var(--line);color:var(--accent);align-self:center}
  .dwactions .prev1{background:#15232e;border:1px solid #2a4257;color:#9cc1ff;font-weight:600}
  .dwactions .submit1{background:#1d2a1d;border:1px solid #2f5c3a;color:#86efac;font-weight:600}
  .runpanel{margin-top:12px;border:1px solid var(--line);border-radius:10px;background:var(--panel2);padding:12px}
  .runhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
  .runtitle{font-weight:600;font-size:13.5px}
  .runclose{background:none;border:none;color:var(--muted);cursor:pointer;font-size:14px}
  .runverdict{font-size:13px;line-height:1.5}
  .runverdict .rgood{color:#7fd99a;font-weight:600}
  .runverdict .rbad{color:#e0696b;font-weight:600}
  .runverdict .rwarn{color:#e0b84a;margin-top:4px}
  .runverdict .rmsg{color:var(--muted);margin-top:3px}
  .runverdict .ramz{margin-top:5px;padding:8px;background:#2a1a1a;border:1px solid #5c2b2b;border-radius:7px;color:#e8b4b4;font-size:12px;white-space:pre-wrap}
  .runverdict .rhint{margin-top:6px;color:#9cc1ff;font-size:12px}
  .runlogwrap{margin-top:8px}
  .runlogwrap summary{cursor:pointer;color:var(--muted);font-size:12px}
  .runlog{margin-top:6px;max-height:220px;overflow:auto;background:#0c1320;border:1px solid var(--line);border-radius:7px;padding:8px;font-size:11px;color:#aebbd0;white-space:pre-wrap}
  .rspin,.genspin{display:inline-block;width:11px;height:11px;border:2px solid #3a4658;border-top-color:#9cc1ff;border-radius:50%;animation:spin .7s linear infinite;vertical-align:-1px}
  @keyframes spin{to{transform:rotate(360deg)}}
  .lmeta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
  .lsku{font-family:ui-monospace,Consolas,monospace;font-size:11.5px}
  .lprice{color:var(--ink);font-weight:600}
  /* selection action bar */
  .selbar{display:flex;align-items:center;gap:8px;padding:8px 20px;background:#141b2b;
          border-bottom:1px solid var(--line);font-size:12.5px;color:#9cc1ff;
          position:sticky;top:0;z-index:40;flex-wrap:wrap;
          box-shadow:0 2px 8px rgba(0,0,0,.25)}
  .selbar .spacer{flex:1}
  .selbar button{font-size:12px;padding:5px 10px}
  #selcount{font-weight:600}
  /* marketplace switcher */
  .mktswitch{display:flex;gap:4px;align-items:center;margin-right:8px}
  .mktbtn{font-size:12px;padding:5px 11px;border-radius:8px;background:var(--panel2);
          border:1px solid var(--line);color:var(--muted);cursor:pointer}
  .mktbtn.on{background:rgba(76,141,255,.16);border-color:var(--accent);color:#fff;font-weight:600}
  .mktlabel{font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:7px;padding:4px 9px}
  .browsemodels{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--accent);
                text-decoration:none;padding:7px 11px;border:1px solid #2f3a4d;border-radius:8px}
  .browsemodels:hover{background:var(--panel2)}
  .browsemodels.sm{font-size:11px;padding:4px 8px}
  /* settings modal */
  .modalwrap{position:fixed;inset:0;z-index:90;background:rgba(0,0,0,.55);display:none;align-items:flex-start;justify-content:center;padding:60px 16px;overflow:auto}
  .modalwrap.open{display:flex}
  .modal{background:var(--panel);border:1px solid var(--line);border-radius:14px;width:560px;max-width:100%;padding:20px;position:relative}
  .modal h3{margin:0 0 4px;font-size:16px;padding-right:34px}
  .modal .x{position:absolute;top:14px;right:16px;background:none;border:none;color:var(--muted);font-size:22px;cursor:pointer;line-height:1;z-index:2}
</style>
</head>
<body>

<div class="appbar">
  <div class="brandmark" onclick="goHome()">
    <span class="dot">L</span><span>Listing Generator</span>
  </div>
  <div class="crumbs" id="crumbs"></div>
  <span class="spacer"></span>
  <button class="barbtn" id="privbtn" onclick="togglePrivacy()" title="Privacy mode: blur account names, titles, ASINs and images for screen-sharing"><i class="ti ti-eye-off"></i> Privacy</button>
  <button class="barbtn" id="aibtn" onclick="openAISettings()"><i class="ti ti-settings"></i> AI &amp; settings</button>
  <button class="barbtn" onclick="goHome()"><i class="ti ti-home"></i> Home</button>
</div>

<!-- ============ HOME SCREEN ============ -->
<div id="home" class="show">
  <p class="homehd">Workspaces</p>
  <div class="wsgrid" id="wsgrid">
    <div class="empty" style="grid-column:1/-1">Loading workspaces…</div>
  </div>
</div>

<!-- ============ WORKSPACE SCREEN ============ -->
<div id="workspace">
  <div class="sidebar">
    <div class="backlink" onclick="goHome()"><i class="ti ti-arrow-left"></i> All workspaces</div>
    <div class="wsident">
      <div class="ic" id="ws_ic">··</div>
      <div><div class="nm pii" id="ws_nm">Workspace</div><div class="sub cc pii" id="ws_sub"></div></div>
    </div>
    <div class="navitem active" data-sec="listings" onclick="navTo('listings')"><i class="ti ti-list"></i> Listings</div>
    <div class="navitem" data-sec="imagerefs" onclick="navTo('imagerefs')"><i class="ti ti-photo"></i> Image refs</div>
    <div class="navitem" data-sec="setup" id="nav_setup" onclick="navTo('setup')"><i class="ti ti-settings"></i> Brand setup</div>
    <div class="navitem" id="nav_acctsettings" onclick="openCurrentAccountSettings()"><i class="ti ti-table"></i> Account &amp; sheets</div>
    <div class="navitem" data-sec="generate" onclick="navTo('generate')"><i class="ti ti-upload"></i> Generate &amp; submit</div>
    <div class="navitem" data-sec="ppc" onclick="navTo('ppc')"><i class="ti ti-target"></i> PPC</div>
    <div class="navitem" data-sec="inventory" onclick="navTo('inventory')"><i class="ti ti-package"></i> Inventory <span id="inv_badge" style="display:none;background:#e0696b;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;margin-left:4px;font-weight:600"></span></div>
    <div class="navitem" data-sec="miles" id="nav_harvest" onclick="navTo('miles')" style="display:none"><i class="ti ti-droplet"></i> Supplier Import</div>
  </div>

  <div class="wsmain">
    <!-- LISTINGS section -->
    <div id="sec_listings">
      <div class="wstoolbar">
        <div><h2 id="ws_title">Listings</h2><div class="sub" id="ws_rowsub"></div></div>
        <span class="spacer"></span>
        <div id="srcswitch" class="mktswitch">
          <button class="mktbtn on" data-src="drafts" onclick="setListSource('drafts')">Drafts</button>
          <button class="mktbtn" data-src="live" onclick="setListSource('live')">Live on Amazon</button>
          <button class="mktbtn" data-src="all" onclick="setListSource('all')">All</button>
          <button class="mktbtn" title="Sync live listings from Amazon now" onclick="syncLive()"><i class="ti ti-refresh"></i> Sync</button>
          <span id="synclabel" class="cc" style="font-size:11px;margin-left:2px"></span>
          <button class="mktbtn" title="Run a full SP-API health check for this account and marketplace — tests DNS, network, auth, and every SP-API operation in one shot; tells you exactly which layer is broken and how to fix it" onclick="runSpDiagnose()"><i class="ti ti-stethoscope"></i> Diagnose SP-API</button>
          <button class="mktbtn" title="Upload a CSV of SKU/ASIN + cost to set COGS in bulk" onclick="document.getElementById('cogscsv').click()"><i class="ti ti-upload"></i> COGS CSV</button>
          <input type="file" id="cogscsv" accept=".csv" style="display:none" onchange="uploadCogsCsv(this)">
        </div>
        <div id="mktswitch" class="mktswitch"></div>
        <select id="statussel" onchange="setFilterVal(this.value)" title="Filter by status"
          style="background:#161b24;color:#c8d3e6;border:1px solid #2f3a4d;border-radius:8px;padding:5px 10px;font-size:13px">
          <option value="all">All statuses</option>
          <option value="review">Needs review</option>
          <option value="holds">Holds</option>
          <option value="approved">Approved</option>
          <option value="live">Live</option>
        </select>
        <button class="ghost" onclick="loadRows()"><i class="ti ti-refresh"></i> Refresh</button>
      </div>
      <div id="gridhow"></div>
      <div id="selbar" class="selbar" style="display:none">
        <span id="selcount">0 selected</span>
        <span class="spacer"></span>
        <button onclick="bulkStatus('APPROVED')" title="Approve all selected listings"><i class="ti ti-check"></i> Approve</button>
        <button onclick="bulkStatus('HOLD')" title="Put all selected listings on hold"><i class="ti ti-player-pause"></i> Hold</button>
        <button onclick="bulkAutoFix()" title="Run Suggest→Apply→Preview loop on every selected listing. Auto-stops per SKU when clean or stuck." style="border-color:#2563eb;color:#93c5fd"><i class="ti ti-wand"></i> Auto-fix</button>
        <button onclick="openStudioBatch()" title="Generate main images for all selected products"><i class="ti ti-photo"></i> Generate main images</button>
        <button onclick="batchGenerate('regen')" title="Regenerate the listing copy for the selected SKUs"><i class="ti ti-refresh"></i> Regenerate listings</button>
        <button onclick="batchSecondaryImages()" title="Generate secondary images once and apply to all selected SKUs"><i class="ti ti-photo"></i> Secondary images</button>
        <button onclick="batchAutoGenerate('secondary')" title="Strategist proposes secondary-image ideas and generates them for every selected product — runs in the background, no pop-up" style="border-color:#4a6cff"><i class="ti ti-bolt"></i> Auto-generate (Secondary)</button>
        <button onclick="batchAutoGenerate('aplus')" title="Strategist proposes A+ modules and generates them for every selected product — runs in the background, no pop-up" style="border-color:#4a6cff"><i class="ti ti-bolt"></i> Auto-generate (A+)</button>
        <button onclick="bulkDelete()" title="Delete all selected listings" style="color:#ff8a8a;border-color:#5c2424"><i class="ti ti-trash"></i> Delete</button>
        <button onclick="selectAllVisible(true)">Select all</button>
        <button onclick="clearSelection()">Clear</button>
      </div>
      <div id="summary">Loading…</div>
      <pre id="log"></pre>
      <main id="grid"><div class="empty">Loading listings…</div></main>
      <div id="drawerscrim" class="drawerscrim" onclick="closeDrawer()"></div>
      <aside id="drawer" class="drawer"><div id="drawerbody"></div></aside>
    </div>

    <!-- IMAGE REFS section -->
    <div id="sec_imagerefs" class="wspanel">
      <div class="wstoolbar" style="position:static;margin:-20px -20px 16px"><div><h2>Image references</h2><div class="sub">Saved reference images used for AI main-image generation in this workspace</div></div></div>
      <div id="imagerefsbody"></div>
    </div>

    <!-- BRAND SETUP section -->
    <div id="sec_setup" class="wspanel">
      <div id="brandpanel"></div>
    </div>

    <!-- GENERATE & SUBMIT section -->
    <div id="sec_generate" class="wspanel">
      <div class="wstoolbar" style="position:static;margin:-20px -20px 16px"><div><h2>Generate &amp; submit</h2><div class="sub">Run generation, export, preview the API, and submit live — scoped to this workspace</div></div></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
        <button class="primary" onclick="runMode('generate')"><i class="ti ti-player-play"></i> Generate</button>
        <button onclick="runMode('retry')">Retry holds</button>
        <button onclick="runMode('export')">Export .xlsm</button>
        <button onclick="runMode('api')">Preview (API)</button>
        <button class="danger" onclick="submitLive()">Submit · go live</button>
        <button class="danger" id="stopbtn" onclick="stopRun()" disabled title="Stops the current run">Stop</button>
      </div>
      <!-- Row selector: pick which input-sheet rows to generate -->
      <div id="genselectwrap" style="margin:-4px 0 14px;padding:12px 14px;border:1px solid var(--line,#2a2f3a);border-radius:10px;background:var(--panel2,rgba(255,255,255,.02))">
        <div style="font-size:13px;opacity:.85;margin-bottom:8px">
          <b>Generate</b> creates every input-sheet listing that isn't in the app yet.
          To create only specific ones, enter them below.
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <input id="gensel_value" type="text" placeholder="Paste an eBay / Amazon URL, or type a value…"
                 oninput="genSelOnInput()"
                 style="flex:1;min-width:240px;padding:8px 10px;border:1px solid var(--line,#2a2f3a);border-radius:8px;background:var(--bg,#0e1116);color:inherit">
          <select id="gensel_type" title="What you're entering (ignored when a URL is pasted)"
                  style="padding:8px 10px;border:1px solid var(--line,#2a2f3a);border-radius:8px;background:var(--bg,#0e1116);color:inherit">
            <option value="row" selected>Row number</option>
            <option value="asin">ASIN</option>
            <option value="ebay_item">eBay item number</option>
          </select>
        </div>
        <div id="gensel_hint" style="font-size:12px;opacity:.6;margin-top:6px">
          Row numbers can be comma-separated (e.g. 2, 5, 7). For one product you can paste its URL — the dropdown is ignored then.
        </div>
      </div>
      <div id="genhow"></div>
      <div class="reqnote">Runs here only touch <b id="gen_scope">this workspace's</b> sheet/marketplace — nothing else is affected.</div>
      <div id="targetacct" class="acctbanner">Resolving destination account…</div>

      <!-- INPUT SHEET VIEWER: see the source sheet right here, no need to open Google Sheets -->
      <div id="inputsheetwrap" style="margin-top:18px;border:1px solid var(--line,#2a2f3a);border-radius:10px;overflow:hidden">
        <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--panel2,rgba(255,255,255,.02));flex-wrap:wrap">
          <b style="font-size:14px"><i class="ti ti-table"></i> Input sheet</b>
          <span class="cc" id="inputsheet_meta" style="font-size:12px;opacity:.7"></span>
          <span class="spacer" style="flex:1"></span>
          <input id="inputsheet_filter" placeholder="Filter rows…" oninput="filterInputSheet()"
                 style="padding:6px 9px;border:1px solid var(--line,#2a2f3a);border-radius:7px;background:var(--bg,#0e1116);color:inherit;font-size:12px;min-width:160px">
          <button class="ib" onclick="loadInputSheet()"><i class="ti ti-refresh"></i> Refresh</button>
          <a class="ib" id="inputsheet_open" href="#" target="_blank" rel="noopener" style="display:none"><i class="ti ti-external-link"></i> Open in Google Sheets</a>
        </div>
        <div id="inputsheet_body" style="max-height:520px;overflow:auto">
          <div class="cc" style="padding:16px;opacity:.6">Click Refresh to load the input sheet.</div>
        </div>
      </div>
    </div>

    <!-- PPC section -->
    <div id="sec_ppc" class="wspanel">
      <div class="wstoolbar" style="position:static;margin:-20px -20px 16px">
        <div><h2>PPC</h2>
        <div class="sub">Amazon Sponsored Products — campaign builder, harvest, audits, forecasts, weekly decks. Ask the agent below or use a shortcut. Every deliverable is scoped to this workspace's account and marketplace.</div></div>
      </div>

      <div style="display:grid;grid-template-columns:340px 1fr;gap:14px;min-height:420px">
        <!-- Left: shortcut buttons -->
        <div>
          <div style="font-weight:600;margin-bottom:8px;font-size:13px;opacity:.85">Shortcuts</div>
          <button class="mktbtn" style="width:100%;text-align:left;margin-bottom:6px" onclick="ppcOpenBuilder()"><i class="ti ti-plus"></i> Build campaigns from keywords</button>
          <button class="mktbtn" style="width:100%;text-align:left;margin-bottom:6px" onclick="ppcOpenHarvest()"><i class="ti ti-tractor"></i> Harvest search-term report</button>
          <button class="mktbtn" style="width:100%;text-align:left;margin-bottom:6px" onclick="ppcOpenDeliverable('auditor', 'Audit account PPC health', 'Upload the SP bulk export + a campaign performance report (last 30 days is fine). Optionally add the SP Search Term Report. I audit clusters, budget benchmarks, match-type pyramid, funnel coverage, and bid-gap; deliver as docx.')"><i class="ti ti-stethoscope"></i> Audit account PPC health</button>
          <button class="mktbtn" style="width:100%;text-align:left;margin-bottom:6px" onclick="ppcOpenDeliverable('dashboard', 'Control-Room dashboard', 'Upload the SP bulk export + a campaign performance report. I build the interactive Control-Room dashboard as HTML. Optionally add an organic ranking XLSX to unlock the Targeting Opportunity Map.')"><i class="ti ti-dashboard"></i> Control-Room dashboard</button>
          <button class="mktbtn" style="width:100%;text-align:left;margin-bottom:6px" onclick="ppcOpenDeliverable('forecaster', 'Sales forecast', 'Upload the Amazon business report (session/units data) + SQP files (Brand Analytics), and tell me your target TACOS and net margin %. I build 3-scenario revenue+unit forecasts with growth-rate decay. If required data is missing I stop and ask — I never fabricate numbers.')"><i class="ti ti-chart-line"></i> Sales forecast</button>
          <button class="mktbtn" style="width:100%;text-align:left;margin-bottom:6px" onclick="ppcOpenDeliverable('weekly-deck', 'Weekly client deck', 'Upload this week and last week performance data (business report + Ads campaign report per week). Give me the brand name, week ending, and any context. I produce a strategic PPC deck (pptx).')"><i class="ti ti-presentation"></i> Weekly client deck</button>
          <div style="font-size:11px;opacity:.65;margin-top:12px;line-height:1.5">
            <b>Hard rules baked in:</b><br>
            · Match types spelled out (Exact/Phrase/Broad)<br>
            · SKU (never ASIN) on Product Ads<br>
            · Keywords + Product Targets never share an ad group<br>
            · Never sets bids/budgets on its own initiative
          </div>
        </div>

        <!-- Right: agent chat -->
        <div style="display:flex;flex-direction:column;border:1px solid var(--line);border-radius:10px;overflow:hidden">
          <div id="ppc_chatlog" style="flex:1;padding:14px;overflow-y:auto;min-height:360px;max-height:520px;background:#0d1220">
            <div style="opacity:.75;font-size:13px;line-height:1.5">
              <b>PPC Agent.</b> Describe what you want — build campaigns, harvest a search-term report, audit, dashboard, forecast, weekly deck. The agent knows the full PPC skill set from the handover doc and applies your standing rules (never touches bids/budgets without your value; SKU on ads; kw + PT never share; every kw in all 3 match types).
              <br><br>
              Scoped to: <b id="ppc_ctx">this workspace</b>.
            </div>
          </div>
          <div style="padding:10px;border-top:1px solid var(--line);background:#141b2b">
            <div style="display:flex;gap:8px">
              <textarea id="ppc_input" placeholder="e.g. Build campaigns for ASIN B0EXAMPLE1, SKU MYSKU-001…" rows="2" style="flex:1;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:8px;padding:8px;font-family:inherit;font-size:13px;resize:vertical"></textarea>
              <button class="mktbtn on" style="align-self:stretch;padding:0 16px" onclick="ppcAgentSend()">Send</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Campaign-builder shortcut modal -->
      <div id="ppc_builder_modal" class="modalwrap">
        <div class="modal" style="max-width:640px">
          <button class="x" onclick="ppcCloseBuilder()">×</button>
          <h3><i class="ti ti-plus"></i> Build Sponsored Products campaigns</h3>
          <div class="cc" style="margin:6px 0 12px">Feed a keyword export + ASIN/SKU. The tool buckets keywords (drop/head/comp/core), builds 5 campaigns with the full-coverage structure, and validates before letting you download.</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
            <div><label class="cc" style="font-size:11px">ASIN</label><input id="pb_asin" placeholder="B0EXAMPLE1" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Seller SKU (NOT ASIN)</label><input id="pb_sku" placeholder="MYSKU-001" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Product short name (for campaign names)</label><input id="pb_name" placeholder="BodyScale" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Daily budget (£/$)</label><input id="pb_budget" type="number" step="0.01" value="8.00" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Flat bid (£/$) — you set this, never auto</label><input id="pb_bid" type="number" step="0.01" value="0.30" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Conquest ASINs (comma-sep, optional)</label><input id="pb_conquest" placeholder="B0COMP0001, B0COMP0002" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
          </div>
          <div style="margin-bottom:10px">
            <label class="cc" style="font-size:11px">Competitor brand names (comma-sep, for bucketing)</label>
            <input id="pb_compbrands" placeholder="dyson, shark, vax" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
          </div>
          <div style="margin-bottom:10px">
            <label class="cc" style="font-size:11px">Category-head terms (comma-sep — go to Phrase discovery)</label>
            <input id="pb_headterms" placeholder="vacuum, hoover" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
          </div>
          <div style="margin-bottom:10px">
            <label class="cc" style="font-size:11px">Keyword file (CSV) — DataDive / Helium 10 / SQP</label>
            <input type="file" id="pb_file" accept=".csv,.tsv,.txt" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
          </div>
          <div style="display:flex;gap:8px;justify-content:flex-end">
            <button class="mktbtn" onclick="ppcCloseBuilder()">Cancel</button>
            <button class="mktbtn on" onclick="ppcRunBuilder()">Build bulk file</button>
          </div>
          <div id="pb_result" style="margin-top:12px"></div>
        </div>
      </div>

      <!-- Harvest shortcut modal -->
      <div id="ppc_harvest_modal" class="modalwrap">
        <div class="modal" style="max-width:640px">
          <button class="x" onclick="ppcCloseHarvest()">×</button>
          <h3><i class="ti ti-tractor"></i> Harvest a Sponsored Products Search Term Report</h3>
          <div class="cc" style="margin:6px 0 12px">Applies the $10 rule + break-even ACOS: converters → harvest bulk (3 match types); past-$10 zero-order → negatives bulk; everything else → colour-coded status sheet. Already-targeted keywords are excluded from harvest to prevent duplicate (keyword, match-type) pairs on upload.</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
            <div><label class="cc" style="font-size:11px">ASIN</label><input id="ph_asin" placeholder="B0EXAMPLE1" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Seller SKU (NOT ASIN)</label><input id="ph_sku" placeholder="MYSKU-001" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Product short name</label><input id="ph_name" placeholder="BodyScale" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Break-even ACOS (0-1) — from your unit economics</label><input id="ph_be" type="number" step="0.01" value="0.35" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Bid for harvested keywords (you set — never auto)</label><input id="ph_bid" type="number" step="0.01" value="0.30" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
            <div><label class="cc" style="font-size:11px">Daily budget for new campaign (if none set)</label><input id="ph_budget" type="number" step="0.01" value="8.00" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px"></div>
          </div>
          <div style="margin-bottom:10px">
            <label class="cc" style="font-size:11px">SP Search Term Report (CSV) — required</label>
            <input type="file" id="ph_file" accept=".csv,.tsv,.txt" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
          </div>
          <div style="margin-bottom:10px">
            <label class="cc" style="font-size:11px">Already-targeted keywords file (CSV, optional) — excluded from harvest</label>
            <input type="file" id="ph_targeted" accept=".csv,.tsv,.txt" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
          </div>
          <div style="display:flex;gap:8px;justify-content:flex-end">
            <button class="mktbtn" onclick="ppcCloseHarvest()">Cancel</button>
            <button class="mktbtn on" onclick="ppcRunHarvest()">Run harvest</button>
          </div>
          <div id="ph_result" style="margin-top:12px"></div>
        </div>
      </div>

      <!-- Unified deliverable modal: audit / dashboard / forecast / weekly-deck -->
      <div id="ppc_deliv_modal" class="modalwrap">
        <div class="modal" style="max-width:640px">
          <button class="x" onclick="ppcCloseDeliv()">×</button>
          <h3 id="pd_title"><i class="ti ti-file"></i> PPC Deliverable</h3>
          <div class="cc" style="margin:6px 0 12px" id="pd_desc">…</div>
          <div style="margin-bottom:10px">
            <label class="cc" style="font-size:11px">Files (multi-select; drop the right family for the task)</label>
            <input type="file" id="pd_files" multiple style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
            <div class="cc" style="font-size:11px;margin-top:4px;opacity:.7">Accepted families: SP bulk export, Search Term Report, Business Report, Brand Analytics SQP, Scale Insights exports. I auto-detect from column headers.</div>
          </div>
          <div style="margin-bottom:10px">
            <label class="cc" style="font-size:11px">Context / notes (optional — brand, week, targets, whatever helps)</label>
            <textarea id="pd_context" rows="3" style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px;font-family:inherit;font-size:13px"></textarea>
          </div>
          <div style="display:flex;gap:8px;justify-content:flex-end">
            <button class="mktbtn" onclick="ppcCloseDeliv()">Cancel</button>
            <button class="mktbtn on" onclick="ppcRunDeliv()">Send to PPC agent</button>
          </div>
          <div id="pd_result" style="margin-top:12px"></div>
        </div>
      </div>
    </div>

    <!-- INVENTORY REPLENISHMENT -->
    <div id="sec_inventory" class="wspanel">
      <div class="wstoolbar" style="position:static;margin:-20px -20px 16px">
        <div><h2>Inventory replenishment</h2>
        <div class="sub">Fully automated. Pulls FBA inventory + sales velocity from SP-API. Applies four-bucket zero-velocity classification (Active / New Launch / Dormant / Dead). Coloured xlsx output mirrors your original Excel model.</div></div>
      </div>

      <div style="padding:14px;border:1px solid var(--line);border-radius:10px;margin-bottom:14px">
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-bottom:12px">
          <div>
            <label class="cc" style="font-size:11px">Target normal FBA DOS</label>
            <input id="inv2_normal" type="number" value="85" min="0" max="365"
              style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
          </div>
          <div>
            <label class="cc" style="font-size:11px">Reorder cycle days</label>
            <input id="inv2_reorder" type="number" value="5" min="0" max="90"
              style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
          </div>
          <div>
            <label class="cc" style="font-size:11px">Long-horizon 3PL DOS</label>
            <input id="inv2_long" type="number" value="110" min="0" max="365"
              style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
          </div>
          <div>
            <label class="cc" style="font-size:11px">Sales window (days)</label>
            <input id="inv2_window" type="number" value="30" min="7" max="180"
              style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
          <div>
            <label class="cc" style="font-size:11px">3PL stock CSV (optional) — matches your existing sheet columns</label>
            <input type="file" id="inv2_3pl" accept=".csv,.tsv,.txt"
              style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
            <div class="cc" style="font-size:10px;margin-top:2px;opacity:.65">
              Cols: Natural SKUs · SKUs · Product Name · ASIN · 3PL Stock · In-Transit · Ordered Qty
            </div>
          </div>
          <div>
            <label class="cc" style="font-size:11px">Cache lifetime (hours) — protects Seller Central from report spam</label>
            <input id="inv2_cache" type="number" value="6" min="0" max="72"
              style="width:100%;background:#0d1220;border:1px solid var(--line);color:#e8eaed;border-radius:6px;padding:7px">
            <div class="cc" style="font-size:10px;margin-top:2px;opacity:.65">
              6h = at most 4 reports/day per account. Set to 0 to always fetch fresh (creates a Seller Central report each run).
            </div>
          </div>
        </div>

        <div style="display:flex;gap:8px;justify-content:space-between;align-items:center">
          <label style="font-size:12px;display:flex;align-items:center;gap:6px">
            <input type="checkbox" id="inv2_force"> Force refresh (bypass cache, generates new Seller Central report)
          </label>
          <button class="mktbtn on" onclick="inv2Run()"><i class="ti ti-package"></i> Run inventory model</button>
        </div>
        <div id="inv2_result" style="margin-top:12px"></div>

        <div style="margin-top:14px;padding:10px;border:1px solid #263145;border-radius:8px;background:#0d1220;font-size:11px;line-height:1.6;opacity:.8">
          <b>How it works:</b> Fetches FBA inventory via the SP-API <code>GET_FBA_MYI_ALL_INVENTORY_DATA</code> report (cached 6h by default). Fetches sales velocity per SKU via the Orders API over the sales window. Classifies each SKU as <b>ACTIVE</b> (has sales), <b>NEW_LAUNCH</b> (0 sales but &lt;60 days old), <b>DORMANT</b> (0 sales, 60-365 days), or <b>DEAD</b> (0 sales &gt;365 days or Discontinued). Only ACTIVE and NEW_LAUNCH SKUs get reorder recommendations. The red badge in the sidebar shows count of SKUs needing reorder.
        </div>
      </div>
    </div>

    <!-- MILES LUBRICANTS IMPORT -->
    <div id="sec_miles" class="wspanel">
      <div class="wstoolbar" style="position:static;margin:-20px -20px 16px">
        <div><h2>Miles Lubricants Import</h2>
        <div class="sub">Harvest products from mileslubricants.com by item number — pulls page text, spec table, and the PDF spec/SDS sheets into Drive, then drafts Amazon listings with compliance &amp; IP checks.</div></div>
      </div>

      <div style="padding:14px;border:1px solid var(--line);border-radius:10px;margin-bottom:14px">
        <div style="font-size:13px;opacity:.85;margin-bottom:10px">
          <b>Step 1.</b> Upload a CSV or Excel file with one column of item numbers (e.g. <code>M001000603</code>). One item number = one product = one listing.
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
          <input type="file" id="miles_file" accept=".csv,.xlsx,.xls" onchange="milesPickFile(this)"
                 style="padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg,#0e1116);color:inherit">
          <span id="miles_filestatus" style="font-size:12px;opacity:.7"></span>
        </div>
        <div id="miles_items" style="font-size:12px;opacity:.6;margin-top:8px"></div>
      </div>

      <div style="padding:14px;border:1px solid var(--line);border-radius:10px;margin-bottom:14px">
        <div style="font-size:13px;opacity:.85;margin-bottom:10px">
          <b>Step 2.</b> Where should the listing copy go? Paste the Google Sheet ID (or full URL) and the tab name. Leave blank to use the account default.
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
          <input type="text" id="miles_sheet" placeholder="Output Sheet ID or URL" onchange="milesSavePref()"
                 style="flex:1;min-width:260px;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg,#0e1116);color:inherit">
          <input type="text" id="miles_tab" placeholder="Tab name (e.g. Sheet2)" onchange="milesSavePref()"
                 style="width:180px;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg,#0e1116);color:inherit">
          <input type="number" id="miles_limit" min="1" placeholder="How many? (blank = all)"
                 style="width:170px;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg,#0e1116);color:inherit">
        </div>
        <div style="font-size:11px;opacity:.6;margin-top:8px">
          Columns written: SKU, Title, Bullet Point 1-5, Description, Backend Keywords, Compliance Report, Uploaded. Enter a number (e.g. 5) to generate just that many this run.
        </div>
        <label style="display:flex;align-items:center;gap:8px;margin-top:10px;font-size:13px;cursor:pointer">
          <input type="checkbox" id="miles_use_ba" style="width:16px;height:16px">
          Use real Amazon search data (Brand Analytics) to seed keywords — needs Brand Registry on the account
        </label>
      </div>

      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
        <button class="primary" id="miles_runbtn" onclick="milesRun()" disabled><i class="ti ti-player-play"></i> Harvest &amp; draft</button>
        <button id="miles_genbtn" onclick="milesGenerate()"><i class="ti ti-file-text"></i> Generate drafts</button>
        <button id="miles_optbtn" onclick="milesOptimize()" title="Pull real Search Query Performance for live ASINs and front-load converting keywords"><i class="ti ti-trending-up"></i> Optimize live listings (SQP)</button>
        <button class="danger" id="miles_stopbtn" onclick="milesStop()" disabled>Stop</button>
      </div>

      <div class="reqnote" style="margin-bottom:10px">
        Files are saved to your Drive master folder, one subfolder per item number. Industrial lubricants are hazmat on Amazon — the SDS sheet drives the compliance fields.
        <br><b>Optimize live listings</b> pulls each ASIN's real Search Query Performance (the searches that actually drove sales) and rewrites the copy to front-load those — use it 2–4 weeks after listings go live.
      </div>

      <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
        <label style="font-size:12px;display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" id="miles_skip_done" checked> Skip item numbers already harvested
        </label>
        <button class="browsemodels sm" onclick="milesClearHistory()" title="Forget which items were harvested so they can run again">Clear harvested history</button>
      </div>

      <pre id="miles_log" style="display:none;background:#0a0d12;border:1px solid var(--line);border-radius:8px;padding:12px;font-size:12px;line-height:1.5;max-height:340px;overflow:auto;white-space:pre-wrap;margin:8px 0"></pre>

      <div id="miles_results" style="margin-top:14px"></div>
    </div>
  </div>
</div>

<!-- AI settings modal -->
<div class="modalwrap" id="aimodal">
  <div class="modal">
    <button class="x" onclick="closeAISettings()">×</button>
    <h3>AI &amp; settings</h3>
    <p class="cc" style="margin:0 0 14px">Pick which AI handles each job. Providers without a key show “(no key)” — add keys in your local config.json under <code>ai_keys</code>.</p>
    <div id="aimodalbody">Loading…</div>
    <div style="margin-top:16px;border-top:1px solid var(--line);padding-top:12px">
      <h4 style="margin:0 0 8px;font-size:13px;color:#cbd3e1">Display</h4>
      <label class="minlbl" title="Show the 'Exact payload sent to Amazon' section under each listing. This is read-only debug info — turning it off only hides it, nothing else changes.">
        <input type="checkbox" id="payloadViewerToggle" onchange="togglePayloadViewer(this)"> Show exact payload sent to Amazon (debug)
      </label>
    </div>
  </div>
</div>

<div class="modalwrap" id="acctmodal">
  <div class="modal">
    <button class="x" onclick="closeAccountEditor()">×</button>
    <h3>Amazon account</h3>
    <p class="cc" style="margin:0 0 14px">Each account is a workspace. Submits in this workspace publish to <b>this account only</b>, using its own credentials.</p>
    <div id="acctmodalbody">Loading…</div>
  </div>
</div>

<div class="modalwrap" id="optmodal">
  <div class="modal" style="max-width:680px">
    <button class="x" onclick="closeOpt()">×</button>
    <h3><i class="ti ti-wand"></i> Optimize live listing</h3>
    <div id="optbody">Loading…</div>
  </div>
</div>

<div class="modalwrap" id="imgstudio">
  <div class="modal" style="max-width:860px">
    <button class="x" onclick="closeStudio()">×</button>
    <h3><i class="ti ti-photo-edit"></i> Image Studio</h3>
    <div id="studiobody">Loading…</div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let ROWS = [], FILTER = "all", SHIP = "", SCHEMAS = {}, PTYPES = [];
let SELECTED = new Set();      // SKUs ticked for batch actions
let CUR_SYMBOL = "\u00a3";     // £ default; flips to $ for US workspaces
let WS_MARKET = "";           // active marketplace within the workspace
let DRAWER_SKU = null;        // SKU currently open in the side drawer

// Resolve a listing's OWN marketplace (US/UK/…): the row's marketplace first,
// then its attributes, then the active workspace marketplace, then UK. Used so
// the schema/value lists are fetched for the listing's real marketplace+creds.
function rowMkt(r){
  r=r||{};
  return String(r._marketplace || (r.attributes||{}).marketplace || WS_MARKET || "UK").toUpperCase();
}

function toggleSelect(sku, on){
  if(on) SELECTED.add(String(sku)); else SELECTED.delete(String(sku));
  const c=document.querySelector('.lcard[data-sku="'+CSS.escape(String(sku))+'"]');
  if(c) c.classList.toggle('sel', on);
  updateSelBar();
}
function selectAllVisible(on){
  ROWS.filter(passFilter).filter(r=>!isEmptyRow(r)).forEach(r=>{
    if(on) SELECTED.add(String(r.sku)); else SELECTED.delete(String(r.sku));
  });
  render(); updateSelBar();
}
function clearSelection(){ SELECTED.clear(); render(); updateSelBar(); }
function updateSelBar(){
  const bar=document.getElementById('selbar'); if(!bar) return;
  const n=SELECTED.size;
  bar.style.display = n? 'flex':'none';
  const cnt=document.getElementById('selcount'); if(cnt) cnt.textContent=n+' selected';
}
function selectedSkus(){ return Array.from(SELECTED); }

async function batchGenerate(kind){
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  // Batch COPY regeneration runs through the generator with a --skus filter.
  // If your generator build doesn't have --skus yet, it will report that.
  if(!confirm("Regenerate listing copy for "+skus.length+" selected SKU(s)?\nThis reruns the generator scoped to just these SKUs.")) return;
  navTo("generate");
  const log=document.getElementById("log"); if(log){ log.style.display="block"; log.textContent="Starting regeneration for "+skus.length+" SKU(s)…\n"; }
  try{
    const es=new EventSource("/run/regen?skus="+encodeURIComponent(skus.join(",")));
    es.onmessage=e=>{ if(log){ log.textContent+=e.data+"\n"; log.scrollTop=log.scrollHeight; } };
    es.addEventListener("end",()=>{ es.close(); showStop(false); loadRows(); toast("Regeneration finished"); });
    showStop(true);
  }catch(e){ toast("Could not start: "+e); }
}

async function batchAutoGenerate(kind){
  // Bulk one-click: strategize + generate in the BACKGROUND. Does NOT open the
  // studio — the floating status bar shows progress, results auto-save to each
  // product's media library, and it keeps running on any page. kind defaults to
  // 'secondary'; pass 'aplus' for the A+ button.
  kind=kind||"secondary";
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  const per=(kind==="aplus")?7:7; // 7 secondary or up to 7 A+ modules
  const n=skus.length;
  if(!confirm("Auto-generate "+(kind==="aplus"?"A+ modules":"secondary images")+" for "+n+
              " product"+(n>1?"s":"")+" (~"+(n*per)+" images). The strategist proposes ideas and "+
              "generates them all in the background. You can keep working. Continue?")) return;

  const liveSel = (LIST_SOURCE==='live' || LIST_SOURCE==='all');
  toast("Designing concepts for each product…");
  // Strategize SEPARATELY for EACH product using its own reference image, so
  // every product gets concepts tailored to ITSELF — no shared/mixed set.
  let jobs=[];
  let skipped=[];
  for(let si=0; si<skus.length; si++){
    const sku=skus[si];
    const it=_itemForSku(sku);
    const ref=_refImgForItem(it);
    if(!ref){ skipped.push(sku); continue; }
    let concepts=[];
    try{
      const sj=await (await fetch("/genimage/strategize",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({product_image:ref, title:(it&&it.title)||"", kind:kind,
          n:per, text_provider:(window.AI_TEXT||null)})})).json();
      if(!sj.ok){ toast("Strategist failed for "+sku+": "+(sj.error||"unknown")); continue; }
      concepts=sj.concepts||[];
    }catch(e){ toast("Strategist error for "+sku+": "+e); continue; }
    if(!concepts.length){ continue; }
    const asin=liveSel?_asinForSku(sku):"";
    concepts.forEach((c,ci)=>{
      const code=(kind==="aplus")
        ? ("APLUS"+String(ci+1).padStart(2,"0"))
        : ("PT"+String(ci+1).padStart(2,"0"));
      jobs.push({sku:sku, ref:ref, label:sku+" · "+(c.title||code),
        asin:asin, img_code:code,
        payload:{ product_image:ref, title:(it&&it.title)||"", kind:kind,
          concept:c.concept||"", art_direction:c.art_direction||"",
          fidelity:"high", tier:"basic",
          text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null) }});
    });
  }
  if(skipped.length){ toast(skipped.length+" product(s) skipped — no reference image: "+skipped.join(", ")); }
  if(!jobs.length){ toast("Nothing to generate — no products had reference images or concepts."); return; }

  // 3) submit as a background batch — no studio window, status bar tracks it
  try{
    const r=await (await fetch("/genimage/start_batch",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kind:"concept", jobs:jobs, label:(kind==="aplus"?"A+ ":"Secondary ")+"× "+n+" product"+(n>1?"s":"")})})).json();
    if(!r.ok){ toast("Could not start: "+(r.error||"unknown")); return; }
    GEN_ACTIVE_JOB=r.job;
    toast("Started "+jobs.length+" image(s) in the background.");
    openGenPanel();
    startGenStatusPoll();
  }catch(e){ toast("Error: "+e); }
}
function _asinForSku(sku){
  // find the ASIN for a SKU from live items or rows
  const s=String(sku);
  let it=(LIVE_ITEMS||[]).find(x=>String(x.sku)===s);
  if(it && it.asin) return String(it.asin);
  it=(ROWS||[]).find(x=>String(x.sku)===s);
  return (it && it.asin) ? String(it.asin) : "";
}
async function batchSecondaryImages(){
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  // Detect whether the selected SKUs are LIVE Amazon listings (not in the draft
  // sheet). Live listings aren't rows in our sheet, so we generate the images
  // and hand them back for download (upload via Amazon Manage Images), using
  // each live listing's own Amazon photo as the visual reference.
  const liveSel = (LIST_SOURCE==='live' || LIST_SOURCE==='all');
  const liveRefs = {};
  if(liveSel){
    (LIVE_ITEMS||[]).forEach(it=>{ if(it.sku && skus.includes(String(it.sku)) && it.img) liveRefs[it.sku]=it.img; });
  }
  const brief=prompt("Describe the secondary images to generate (one shared set applied to all "+skus.length+" selected SKUs).\nSeparate each image idea with a comma or new line — e.g. 'lifestyle shot in a modern bathroom, infographic of key ingredients, clean packaging shot, how-to-use steps'.\n\nTip: keep text minimal and premium.");
  if(brief===null) return;
  toast("Generating secondary images for "+skus.length+" SKU(s)…");
  try{
    const res=await fetch("/genimage/secondary",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({skus:skus, brief:brief, live:liveSel, live_refs:liveRefs})});
    const j=await res.json();
    if(!j.ok){ toast("Failed: "+(j.error||"unknown")); return; }
    if(j.images && j.images.length){
      // show the generated set in a panel so the user can download each one
      showSecondaryResults(j.images, skus, liveSel);
    }
    toast(liveSel ? ("Generated "+ (j.images? j.images.length:0) +" image(s) — download below")
                  : ("Secondary images applied to "+skus.length+" SKU(s)"));
    if(!liveSel) loadRows();
  }catch(e){ toast("Error: "+e); }
}
function showSecondaryResults(images, skus, live){
  let host=document.getElementById("secresults");
  if(!host){
    host=document.createElement("div"); host.id="secresults";
    host.style.cssText="position:fixed;right:18px;bottom:18px;width:340px;max-height:70vh;overflow:auto;background:var(--card,#0f1722);border:1px solid var(--line,#22304a);border-radius:12px;padding:14px;z-index:9999;box-shadow:0 10px 40px rgba(0,0,0,.5)";
    document.body.appendChild(host);
  }
  const note = live
    ? "These are generated as a shared set. Download each, then upload to your live listings via Amazon → Manage Images (live listings can't be image-updated automatically)."
    : "Applied to the selected draft SKUs and saved to the sheet.";
  host.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
    + '<b style="font-size:13px">Secondary images ('+images.length+')</b>'
    + '<button onclick="document.getElementById(\'secresults\').remove()" style="background:none;border:none;color:#9cc1ff;cursor:pointer;font-size:16px">✕</button></div>'
    + '<div style="font-size:11px;color:#9fb2cc;margin-bottom:10px">'+note+'</div>'
    + images.map((u,i)=>'<div style="margin-bottom:10px"><img src="'+u+'" style="width:100%;border-radius:8px;border:1px solid var(--line,#22304a)"><a href="#" onclick="_downloadAsJpeg(\''+u+'\',\'secondary_'+(i+1)+'\');return false;" style="display:inline-block;margin-top:4px;font-size:12px;color:#9cc1ff">⬇ Download image '+(i+1)+'</a></div>').join("");
}
async function loadBrandPanel(){
  const host=document.getElementById('brandpanel');
  if(!host.dataset.loaded){
    host.innerHTML = await (await fetch('/brand/panel')).text();
    host.dataset.loaded='1';
    host.querySelectorAll('script').forEach(old=>{const s=document.createElement('script'); s.textContent=old.textContent; document.body.appendChild(s);});
    if(window.brandInit) window.brandInit();
  } else if(window.brandRefresh){
    window.brandRefresh();   // re-lock to the current workspace's brand
  }
}
function iBtnEntry(p){
  if(!p) return '';
  const verified = p.verified ? 'code-verified' : 'AI-reported';
  const tip = ((p.source||'') + (p.note? ' \u2014 '+p.note : '') + ' ('+verified+')');
  const warn = (String(p.source||'').startsWith('INFERRED') && !p.verified);
  return '<i class="ibtn '+(warn?'iwarn':'iok')+'" title="'+tip.replace(/"/g,'&quot;')+'">i</i>';
}
function iBtn(prov, key){ return (prov&&prov[key])?iBtnEntry(prov[key]):''; }
// Small source badge for an attribute value: where the data came from.
function srcBadge(src){
  if(!src) return '';
  const s=String(src).toLowerCase();
  let cls='', label='';
  if(s==='ebay'){ cls='src-ebay'; label='eBay'; }
  else if(s==='amazon'){ cls='src-amazon'; label='Amazon'; }
  else if(s==='ai'){ cls='src-ai'; label='AI'; }
  else return '';
  const tip = (s==='ebay') ? 'Value sourced from the eBay listing'
            : (s==='amazon') ? 'Value sourced from Amazon catalogue data'
            : 'Value written by AI from product knowledge — please verify';
  return '<span class="srcbadge '+cls+'" title="'+tip+'">'+label+'</span>';
}
function rowProvenance(r){ try{ return (JSON.parse(r.attrs||'{}')._provenance)||null; }catch(e){ return null; } }
function locateFlags(sku, btn){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r) return;
  const out=document.getElementById('loc_'+sid(sku)); if(!out) return;
  // pull flagged terms from notes: "phrases: a, b" and "suspected brand words: c, d"
  const notes=String(r.notes||'')+' '+String(r.comp_notes||'');
  let terms=[];
  let m=notes.match(/phrases?:\s*([^|]+)/i); if(m) terms=terms.concat(m[1].split(',').map(s=>s.trim()));
  m=notes.match(/suspected brand words?:\s*([^|]+)/i); if(m) terms=terms.concat(m[1].split(',').map(s=>s.trim()));
  terms=terms.filter(t=>t&&t.length>1);
  if(!terms.length){ out.innerHTML='<div class="cc" style="margin-top:6px">No specific terms parsed from the note — the flag may be a category/compliance signal, not a word match.</div>'; return; }
  // search each content field for each term
  const fields={'Title':r.title,'Bullet 1':(r.bullets||[])[0],'Bullet 2':(r.bullets||[])[1],
    'Bullet 3':(r.bullets||[])[2],'Bullet 4':(r.bullets||[])[3],'Bullet 5':(r.bullets||[])[4],
    'Description':r.description,'Search terms':r.search_terms};
  let html='<div style="margin-top:8px;border-top:1px solid var(--line);padding-top:6px">';
  let any=false;
  terms.forEach(t=>{
    const re=new RegExp('('+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig');
    Object.keys(fields).forEach(fn=>{
      const v=String(fields[fn]||'');
      if(v && re.test(v)){
        any=true;
        const hl=esc(v).replace(re,'<mark style="background:#5c4a16;color:#ffe9a8">$1</mark>');
        html+='<div style="margin:4px 0"><b style="color:#e3b768">'+esc(t)+'</b> in <b>'+fn+'</b>: <span style="color:#cbd3e1">'+hl+'</span></div>';
      }
    });
  });
  if(!any) html+='<div class="cc">None of the flagged terms were found in the current copy — they may have already been edited out. Safe to re-check.</div>';
  html+='</div>';
  out.innerHTML=html;
}
(function(){
  document.querySelectorAll('header .pill[data-f]').forEach(p=>{
    p.addEventListener('click',()=>{
      document.getElementById('brandpanel').style.display='none';
      document.getElementById('grid').style.display='';
      document.getElementById('summary').style.display='';
    });
  });
})();

function esc(s){return (s==null?"":String(s)).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");
  clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove("show"),1800);}

function badgeClass(s){return ["APPROVED","NEEDS_REVIEW","IP_HOLD","COMPLIANCE_HOLD","ERROR","API_READY","API_ERROR","LIVE"].includes(s)?("b-"+s):"b-none";}
function isHold(s){return s==="IP_HOLD"||s==="COMPLIANCE_HOLD"||s==="ERROR"||s==="API_ERROR";}

function passFilter(r){
  if(FILTER==="all")return true;
  if(FILTER==="review")return r.status==="NEEDS_REVIEW";
  if(FILTER==="holds")return isHold(r.status);
  if(FILTER==="approved")return r.status==="APPROVED"||r.status==="API_READY";
  if(FILTER==="live")return r.status==="LIVE";
  return true;
}

// A row is "actually live" if its status is LIVE, OR its SKU/ASIN already
// exists in the Amazon live catalog. This must return the SAME answer whether
// called by render() (for grouping) or summary() (for counting) -- otherwise
// the two drift and the top-bar shows a HOLD count for rows that are actually
// live on Amazon (a leftover pre-submit status the sheet never updated).
function isActuallyLive(r, liveCatSkus, liveCatAsins, liveGroupShown){
  const norm = v => String(v||"").trim().toUpperCase();
  if(norm(r.status)==="LIVE") return true;
  if(!liveGroupShown) return false;   // don't reclassify in views without a Live group
  const s=norm(r.sku), a=norm(r.asin);
  if(s && liveCatSkus.has(s)) return true;
  if(a && liveCatAsins.has(a)) return true;
  return false;
}

// Build the SKU/ASIN sets once per render -- reused by summary()
function _liveCatSetsForCurrentView(){
  const norm = v => String(v||"").trim().toUpperCase();
  return {
    skus:  new Set((LIVE_ITEMS||[]).map(it=>norm(it.sku)).filter(Boolean)),
    asins: new Set((LIVE_ITEMS||[]).map(it=>norm(it.asin)).filter(Boolean)),
    liveGroupShown: (LIST_SOURCE==="live" || LIST_SOURCE==="all"),
  };
}

function summary(){
  const c={APPROVED:0,API_READY:0,NEEDS_REVIEW:0,HOLD:0,ERROR:0,LIVE:0};
  const sets = _liveCatSetsForCurrentView();
  ROWS.forEach(r=>{
    // FIX: reclassify HOLD/NEEDS_REVIEW/etc. as LIVE if the row's SKU/ASIN
    // matches the Amazon catalog. Without this the top-bar shows a stale
    // "N on hold" count for rows that already went live on Amazon but never
    // had their stored status updated from a pre-submit HOLD.
    if(isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown)){
      c.LIVE++;
      return;
    }
    if(r.status==="APPROVED")c.APPROVED++;
    else if(r.status==="API_READY")c.API_READY++;
    else if(r.status==="LIVE")c.LIVE++;
    else if(r.status==="NEEDS_REVIEW")c.NEEDS_REVIEW++;
    else if(r.status==="IP_HOLD"||r.status==="COMPLIANCE_HOLD")c.HOLD++;
    else if(r.status==="ERROR"||r.status==="API_ERROR")c.ERROR++;
  });
  // include live Amazon listings in the counts when they're part of the view.
  // Deduplicate: a catalog tile whose SKU/ASIN already matched an app row above
  // has already been counted as LIVE -- don't count it twice.
  const norm = v => String(v||"").trim().toUpperCase();
  const alreadyCountedSkus  = new Set(ROWS.filter(r=>isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown))
                                          .map(r=>norm(r.sku)).filter(Boolean));
  const alreadyCountedAsins = new Set(ROWS.filter(r=>isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown))
                                          .map(r=>norm(r.asin)).filter(Boolean));
  const liveCount = ((LIST_SOURCE==='live'||LIST_SOURCE==='all')
                     ? (LIVE_ITEMS||[]).filter(it=>{
                         const s=norm(it.sku), a=norm(it.asin);
                         if(s && alreadyCountedSkus.has(s))  return false;
                         if(a && alreadyCountedAsins.has(a)) return false;
                         return true;
                       }).length
                     : 0);
  c.LIVE += liveCount;
  // total reflects what's actually shown in the current view
  let total = ROWS.length;
  if(LIST_SOURCE==='live') total = liveCount;
  else if(LIST_SOURCE==='all') total = ROWS.length + liveCount;
  document.getElementById("summary").innerHTML =
    `<b style="color:#e8eaed">${total}</b> listings &nbsp;·&nbsp; `+
    `${c.NEEDS_REVIEW} needs review &nbsp;·&nbsp; `+
    `<span style="color:#ef9a9a">${c.HOLD} on hold</span> &nbsp;·&nbsp; `+
    `<span style="color:#ef9a9a">${c.ERROR} error</span> &nbsp;·&nbsp; `+
    `<span style="color:#7fd1a0">${c.APPROVED} approved</span> &nbsp;·&nbsp; `+
    `<span style="color:#9cc1ff">${c.API_READY} preview-ready</span> &nbsp;·&nbsp; `+
    `<span style="color:#74e0a3">${c.LIVE} live</span>`;
}

function _rowImages(r){
  var a={};try{a=JSON.parse(r.attrs||'{}');}catch(e){a={};}
  var IMGRE=/^(main_product_image_locator|other_product_image_locator_\d+)$/;
  var urls=Object.keys(a).filter(k=>IMGRE.test(k)).sort().map(k=>a[k]).filter(Boolean);
  if(!urls.length) urls=Object.keys(a).filter(k=>/image_locator/i.test(k)).map(k=>a[k]).filter(Boolean);
  return urls;
}
function _statusDot(r){
  var s=r.status||"";
  var col = s==="LIVE"?"#74e0a3" : (isHold(s)||s==="API_ERROR"||s==="ERROR")?"#ef9a9a"
          : s==="NEEDS_REVIEW"?"#e3b768" : s==="APPROVED"?"#74e0a3" : "#9aa3b2";
  return col;
}
// ---- GALLERY TILE ----
function card(r){
  const findings = [];
  if(r.notes && r.notes.trim()) findings.push(r.notes);
  if(r.comp_notes && r.comp_notes.trim()) findings.push(r.comp_notes);
  const issues = isHold(r.status) || r.ip_risk==="HIGH" || r.comp_risk==="HIGH" || r.comp_risk==="MEDIUM" || findings.length>0;
  const urls=_rowImages(r);
  const thumb = (urls&&urls.length)
    ? `<img src="${esc(urls[0])}" loading="lazy" onerror="this.style.display='none';this.parentNode.classList.add('noimg');this.parentNode.innerHTML='<i class=\\'ti ti-photo\\'></i>'">`
    : `<i class="ti ti-photo"></i>`;
  const selected = SELECTED.has(String(r.sku));
  const priceStr = r.price?`${CUR_SYMBOL}${esc(String(r.price).replace(/^[A-Z]{3}/,''))}`:'';
  const skuId=sid(r.sku);
  return `<div class="tile ${selected?'sel':''} ${issues?'flag':''}" data-sku="${esc(r.sku)}">
    <div class="tileimg pii-img ${(urls&&urls.length)?'':'noimg'}" onclick="openDrawer('${esc(r.sku)}')">
      ${thumb}
      <span class="tiledot" style="background:${_statusDot(r)}" title="${esc(r.status||'')}"></span>
      <input type="checkbox" class="tilesel" ${selected?'checked':''} onclick="event.stopPropagation()" onchange="toggleSelect('${esc(r.sku)}',this.checked)" title="Select">
      ${issues?'<span class="tileflag" title="Needs review"><i class="ti ti-alert-triangle"></i></span>':''}
      <button class="peek" title="Reveal this listing" onclick="event.stopPropagation();peekTile(this)"><i class="ti ti-eye"></i></button>
    </div>
    <div class="tilebody" onclick="openDrawer('${esc(r.sku)}')">
      <div class="tiletitle pii">${esc(r.title)||'<span class="cc">(no title)</span>'}</div>
      <div class="tilemeta">
        ${priceStr?`<span class="tileprice pii">${priceStr}</span>`:'<span></span>'}
        <span class="tilesku pii">${esc(r.sku)||''}</span>
      </div>
    </div>
    <div class="tileacts">
      <button class="ib" title="Approve" onclick="setStatus('${esc(r.sku)}','APPROVED',this)"><i class="ti ti-check"></i></button>
      <button class="ib gen" title="Image Studio (creative ideas, prompt &amp; image AI)" onclick="event.stopPropagation();openStudioSingle('${esc(r.sku)}')"><i class="ti ti-photo"></i></button>
      <button class="ib" title="Edit / details" onclick="openDrawer('${esc(r.sku)}')"><i class="ti ti-edit"></i></button>
      <button class="ib" title="✦ Auto-fix: Suggest → Apply → Preview loop until zero errors" style="color:#93c5fd" onclick="event.stopPropagation();autoFixLoop('${esc(r.sku)}')"><i class="ti ti-wand"></i></button>
      <button class="ib more" title="More" onclick="tileMenu(event,'${esc(r.sku)}',${r.row||0})"><i class="ti ti-dots"></i></button>
    </div>
  </div>`;
}

// ---- DRAWER: full editor for one listing ----
function _marketIsUS(){
  try{ return String((typeof WS_MARKET!=="undefined"&&WS_MARKET)||(CUR_ACCOUNT&&CUR_ACCOUNT.marketplace)||"").toUpperCase()==="US"; }
  catch(e){ return false; }
}
function _stripUKforUS(s){
  // Old rows were generated before compliance became marketplace-aware, so their
  // saved notes can carry UK wording (UKCA, BS 1363, UK/EU dangerous goods) even
  // on a US listing. When the active marketplace is US, rewrite those phrases at
  // DISPLAY time so the flag isn't misleading. (Does not change stored data.)
  if(!_marketIsUS()) return s;
  return String(s)
    .replace(/UK\/EU dangerous goods shipping regulations/gi, "US/international dangerous goods shipping regulations")
    .replace(/\bUKCA\b[^.;|]*/gi, "")
    .replace(/BS\s?1363[^.;|]*/gi, "")
    .replace(/UK Batteries Regulations[^.;|]*/gi, "")
    .replace(/\bWEEE\b[^.;|]*/gi, "")
    .replace(/for (the )?UK market/gi, "for the US market")
    .replace(/\s{2,}/g," ").trim();
}
function formatFindings(findings){
  if(!findings || !findings.length) return "A note is set, but no specific detail was recorded.";
  // Notes may already contain HTML entities (e.g. &#39; for apostrophes) if a
  // previous run stored them escaped. Decode first so splitting + display work.
  const deEntity = (s)=> String(s)
    .replace(/&#39;/g,"'").replace(/&apos;/g,"'").replace(/&quot;/g,'"')
    .replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">");
  findings = findings.map(f=>_stripUKforUS(deEntity(f)));
  const joined = findings.join(" ");
  // If this looks like an API preview error list, split into individual rows so
  // each missing/invalid field is its own line item instead of a wall of text.
  if(/required but missing|\[E\]|\[W\]|API (PREVIEW|SUBMIT)/i.test(joined)){
    // strip the "API PREVIEW - N error(s):" prefix, then split on "; "
    const body = joined.replace(/API (PREVIEW|SUBMIT)[^:]*:\s*/i, "");
    const items = body.split(/;\s*/).map(s=>s.trim()).filter(Boolean);
    if(items.length){
      return '<div class="errlist">' + items.map(it=>{
        const isErr = /^\[E\]/.test(it) || /required|invalid|missing/i.test(it);
        const txt = it.replace(/^\[[EW]\]\s*/,"");
        // pull the field name (first token) to bold it
        const m = txt.match(/^(\S+)\s+(.*)$/);
        const field = m? m[1] : "";
        const rest  = m? m[2] : txt;
        return '<div class="erritem '+(isErr?'e':'w')+'"><span class="errfield">'+esc(field)+'</span> '+esc(rest)+'</div>';
      }).join("") + '</div>';
    }
  }
  // not an API error list -> show as-is (compliance/IP notes), escaped + newlines
  return findings.map(f=>esc(f)).join("\n");
}
function drawerContent(r){
  const findings = [];
  if(r.notes && r.notes.trim()) findings.push(r.notes);
  if(r.comp_notes && r.comp_notes.trim()) findings.push(r.comp_notes);
  const issues = isHold(r.status) || r.ip_risk==="HIGH" || r.comp_risk==="HIGH" || r.comp_risk==="MEDIUM" || findings.length>0;
  const risks = [];
  if(r.ip_risk==="HIGH") risks.push('<span class="risk hi">IP: HIGH</span>');
  if(r.comp_risk==="HIGH") risks.push('<span class="risk hi">Compliance: HIGH</span>');
  else if(r.comp_risk==="MEDIUM") risks.push('<span class="risk med">Compliance: MED</span>');
  let reason = "";
  if(issues){
    if(r.comp_risk==="HIGH") reason="Compliance flag";
    else if(r.ip_risk&&r.ip_risk!=="") reason="IP review";
    else if(r.comp_risk==="MEDIUM") reason="Minor compliance note";
    else reason="Review note";
  }
  // Is this an ACTUAL blocking problem, or just an informational compliance note
  // (e.g. "lithium battery -> these docs may be requested")? A real problem = an
  // API error/hold or an IP risk. A compliance note on an already-submitted/live
  // listing is informational, so show it ORANGE, not alarming red.
  const _allNotes = String((r.notes||"")+" "+(r.comp_notes||""));
  const _hasApiError = /\[E\]|required but missing|API (PREVIEW|SUBMIT)[^:]*:\s*\d+\s*error|invalid/i.test(_allNotes);
  const _isHoldOrErr = (typeof isHold==="function" && isHold(r.status)) ||
                       String(r.status||"").toUpperCase().indexOf("ERROR")>=0;
  const _ipProblem = r.ip_risk==="HIGH";
  const _informational = issues && !_hasApiError && !_isHoldOrErr && !_ipProblem;
  if(_informational){
    reason = "Compliance info — documents Amazon may request";
  }
  const _sumClass = _informational ? "findsum info" : "findsum bad";
  const _findClass = _informational ? "findings info" : "findings";
  const statusBlock = issues
    ? `<details class="findingsbox" open><summary class="${_sumClass}">\u2139 ${esc(reason)}</summary>
        <div class="${_findClass}">${formatFindings(findings)}</div>
        <button class="linkbtn" style="margin-top:6px" onclick="locateFlags('${esc(r.sku)}',this)">\ud83d\udd0d Locate flagged terms</button>
        <div class="locout" id="loc_${sid(r.sku)}"></div></details>`
    : `<div class="findsum good">\u2713 No issues detected</div>`;
  const urls=_rowImages(r);
  const priceStr = r.price?`${CUR_SYMBOL}${esc(String(r.price).replace(/^[A-Z]{3}/,''))}`:'';
  const hero = (urls&&urls.length)?`<div class="heroimg"><img src="${esc(urls[0])}" loading="lazy" onerror="this.parentNode.style.display='none'"></div>`:'';
  return `
    <div class="dwhead">
      <div class="dwtop">
        <span class="badge ${badgeClass(r.status)}">${esc(r.status||'\u2014')}</span>
        ${risks.join("")}
        <span class="spacer"></span>
        <button class="ib" onclick="closeDrawer()" title="Close"><i class="ti ti-x"></i></button>
      </div>
      <div class="dwtitle">${esc(r.title)||'<span class="cc">(no title)</span>'}</div>
      ${r.item_highlights?`<div class="dwhl"><span class="dwhl-lbl">Highlights</span> ${esc(r.item_highlights)}</div>`:''}
      <div class="lmeta">
        <span class="lsku">${esc(r.sku)||'\u2014'}</span>
        ${priceStr?`<span class="lprice">${priceStr}</span>`:''}
        ${r.profit?`<span class="cc">profit ${CUR_SYMBOL}${esc(String(r.profit).replace(/^[A-Z]{3}/,''))}</span>`:''}
      </div>
      <div class="dwactions">
        <button class="suggestbtn" onclick="suggestFields('${esc(r.sku)}')"><i class="ti ti-wand"></i> Suggest missing fields</button>
        <button class="suggestbtn" onclick="refreshSchemaFor('${esc(r.sku)}')" title="Re-fetch Amazon's allowed values so dropdowns show the latest options"><i class="ti ti-refresh"></i> Refresh Amazon values</button>
        <label class="minlbl" title="Send only the fields Amazon strictly requires (plus price/title/etc.). Create the listing now, add the rest in Seller Central. Note: lithium-battery products still require their safety fields."><input type="checkbox" onchange="toggleMinimal(this)" ${MINIMAL_MODE_ON?'checked':''}> Minimal mode (required fields only)</label>
        <button class="genmain" onclick="openStudioSingle('${esc(r.sku)}')"><i class="ti ti-photo"></i> Image Studio</button>
        <button class="pushimg" onclick="pushImageLive('${esc(r.sku)}',this)" title="Send the current main image to the LIVE Amazon listing (updates just the image, no full resubmit)"><i class="ti ti-cloud-upload"></i> Push image to live</button>
        <label class="pushimg" style="cursor:pointer" title="Upload a clean main image from your computer. It's hosted publicly so Amazon can fetch it, then set as this listing's main image. Preview/Submit sends it."><i class="ti ti-photo-up"></i> Upload main image<input type="file" accept="image/*" style="display:none" onchange="uploadMainImage('${esc(r.sku)}',this)"></label>
        <button class="ok" onclick="setStatus('${esc(r.sku)}','APPROVED',this)">Approve</button>
        <button class="prev1" onclick="previewOne('${esc(r.sku)}')" title="Preview this listing against Amazon (no changes sent)"><i class="ti ti-eye"></i> Preview</button>
        <button class="prev1" style="background:#fff;color:#111;border-color:#fff" onclick="autoFixLoop('${esc(r.sku)}')" title="Auto-loop: Suggest → Apply → Preview. Repeats until zero errors, or stops if progress stalls (max 8 rounds)."><i class="ti ti-wand"></i> Auto-fix</button>
        <button class="submit1" onclick="submitOne('${esc(r.sku)}')" title="Publish ONLY this listing live"><i class="ti ti-upload"></i> Submit this</button>
        <button class="hold" onclick="setStatus('${esc(r.sku)}','NEEDS_REVIEW',this)">Hold</button>
        <button class="askthis" onclick="askAbout('${esc(r.sku)}')">\u2726 Ask Claude</button>
        ${r.source?`<a class="srcbtn" href="${esc(r.source)}" target="_blank" rel="noopener">source \u2197</a>`:''}
        <button class="del" onclick="delRow('${esc(r.sku)}',${r.row||0},this)">Delete</button>
      </div>
      <div id="suggestbox_${sid(r.sku)}" class="suggestbox"></div>
      <div id="runpanel_${sid(r.sku)}" class="runpanel" style="display:none">
        <div class="runhead"><span class="runtitle"></span><button class="runclose" onclick="window.RUN_STREAMING=false;this.closest('.runpanel').style.display='none'">✕</button></div>
        <div class="runverdict"></div>
        <details class="runlogwrap"><summary>Show the full Amazon response log</summary><pre class="runlog"></pre></details>
      </div>
    </div>
    ${hero}
    ${statusBlock}
    <div id="fulldata_${sid(r.sku)}">${fullData(r)}</div>`;
}

function openDrawer(sku, jumpGen){
  const r=ROWS.find(x=>String(x.sku)===String(sku));
  if(!r) return;
  DRAWER_SKU=sku;
  const dw=document.getElementById("drawer");
  const body=document.getElementById("drawerbody");
  body.innerHTML=drawerContent(r);
  dw.classList.add("open");
  document.getElementById("drawerscrim").classList.add("open");
  dw.scrollTop=0;
  // If this product type's schema (allowed values + nested sub-fields like ghs /
  // battery) isn't loaded yet, fetch it then re-render -- otherwise required
  // nested fields render as flat boxes (or not at all) and you can't see the
  // dropdowns Amazon needs. This is what made flagged fields invisible.
  if(r.product_type && typeof loadSchemas==="function" && !(SCHEMAS[r.product_type] && (SCHEMAS[r.product_type].attrs||[]).length)){
    loadSchemas([r.product_type], false, rowMkt(r)).then(()=>{
      if(DRAWER_SKU===sku){ body.innerHTML=drawerContent(r); var sv=sid(sku);
        setTimeout(function(){ if(typeof bulletMeter==='function') bulletMeter(); }, 60); }
    }).catch(()=>{});
  }
  // populate the (always-visible) image panel's model dropdowns + run the
  // connection check, once the drawer is in place
  var sidv=sid(sku);
  setTimeout(function(){ initGenPanel(sidv); if(typeof initMilesPanel==='function') initMilesPanel(sidv); if(typeof bulletMeter==='function') bulletMeter(); }, 120);
  if(jumpGen){
    setTimeout(function(){
      var anchor=document.getElementById('genimg_'+sidv);
      if(anchor && dw){ dw.scrollTo({top: anchor.offsetTop - 12, behavior:'smooth'}); }
    }, 280);
  }
}
// Shared OpenRouter connection tester: NEVER hangs (12s timeout) and writes a
// clear, specific status into the given diag element so the user knows exactly
// what's wrong (missing key / bad key / discovery / network / app unreachable).
async function _orTestInto(diag){
  if(!diag) return null;
  diag.className='gendiag'; diag.textContent='Checking OpenRouter connection…';
  let t=null;
  try{
    const ctrl=new AbortController();
    const timer=setTimeout(()=>ctrl.abort(), 12000);   // 12s hard cap, no infinite hang
    let resp;
    try{ resp=await fetch('/ai/test',{signal:ctrl.signal}); }
    finally{ clearTimeout(timer); }
    t=await resp.json();
  }catch(e){
    diag.className='gendiag bad';
    diag.textContent = (e&&e.name==='AbortError')
      ? '\u2717 OpenRouter check timed out (12s). Likely a slow or blocked connection to openrouter.ai — check your internet/VPN, then reopen this panel.'
      : '\u2717 Could not reach the app to test OpenRouter (is the app still running?).';
    return null;
  }
  if(t&&t.ok){
    diag.className='gendiag ok';
    diag.textContent='\u2713 OpenRouter ready \u2014 image model: '+(t.image_model||'?')+' ('+(t.image_count||0)+' image models available)';
  } else {
    diag.className='gendiag bad';
    const stage=(t&&t.stage)||'';
    const base='\u2717 '+((t&&t.error)||'OpenRouter not ready');
    const tip = stage==='key'     ? ' \u2014 add your real openrouter_api_key to config.json and restart the app.'
              : stage==='discover'? ' \u2014 the key was found but OpenRouter rejected it or returned no models. Check the key is valid/active at openrouter.ai/keys.'
              :                     ' \u2014 reopen this panel to retry.';
    diag.textContent=base+tip;
  }
  return t;
}
async function initGenPanel(sidv){
  var s=await loadAISettings();
  // If the cached settings have no image models yet (discovery hadn't finished
  // on first page load), force a fresh discovery so the dropdowns populate.
  if(!s || !s.ok || !(s.image_models && s.image_models.length)){
    try{
      AISET=null;
      s=await (await fetch('/ai/settings?refresh=1')).json();
      AISET=s;
    }catch(e){}
  }
  if(s&&s.ok){
    fillModelSelect(document.getElementById('gentai_'+sidv), s.text_models, s.select.prompt_enhance);
    fillModelSelect(document.getElementById('geniai_'+sidv), s.image_models, s.select.image_generate);
  }
  var diag=document.getElementById('gendiag_'+sidv);
  await _orTestInto(diag);
}
function closeDrawer(){
  DRAWER_SKU=null;
  window.RUN_STREAMING=false;
  if(ES){ try{ES.close();}catch(e){} ES=null; }
  document.getElementById("drawer").classList.remove("open");
  document.getElementById("drawerscrim").classList.remove("open");
}
function tileMenu(ev, sku, row){
  ev.stopPropagation();
  // simple context menu
  closeTileMenu();
  const m=document.createElement("div"); m.className="tilemenu"; m.id="tilemenu";
  m.innerHTML=`
    <button onclick="setStatus('${esc(sku)}','NEEDS_REVIEW',this);closeTileMenu()"><i class="ti ti-player-pause"></i> Hold</button>
    <button onclick="askAbout('${esc(sku)}');closeTileMenu()"><i class="ti ti-message-circle"></i> Ask Claude</button>
    <button onclick="openDrawer('${esc(sku)}');closeTileMenu()"><i class="ti ti-edit"></i> Edit details</button>
    <button class="danger" onclick="delRow('${esc(sku)}',${row},this);closeTileMenu()"><i class="ti ti-trash"></i> Delete</button>`;
  document.body.appendChild(m);
  const rect=ev.target.closest("button").getBoundingClientRect();
  m.style.top=(rect.bottom+4)+"px";
  m.style.left=Math.min(rect.left, window.innerWidth-180)+"px";
  setTimeout(()=>document.addEventListener("click",closeTileMenu,{once:true}),0);
}
function closeTileMenu(){ const m=document.getElementById("tilemenu"); if(m) m.remove(); }
function openGenPanelInDrawer(sku){
  try{
    var sidv=sid(sku);
    var dw=document.getElementById("drawer");
    var anchor=document.getElementById('genimg_'+sidv);
    if(!anchor){ toast("Image panel not found \u2014 try reopening the drawer"); return; }
    if(dw){ dw.scrollTo({top: anchor.offsetTop - 12, behavior:'smooth'}); }
    initGenPanel(sidv);
  }catch(e){ toast("Could not open image panel: "+e); }
}
function openGenFromHead(sku){ openStudioSingle(sku); }

function _fileToDataURL(file){
  return new Promise(function(res,rej){
    var fr=new FileReader(); fr.onload=function(){res(fr.result);}; fr.onerror=rej; fr.readAsDataURL(file);
  });
}
async function uploadRef(input, sku, sidv){
  var file=input.files&&input.files[0]; if(!file) return;
  var st=document.getElementById('genstatus_'+sidv); if(st) st.textContent='Uploading reference…';
  try{
    var dataUrl=await _fileToDataURL(file);
    var res=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,data:dataUrl,name:file.name,kind:'ref'})});
    var j=await res.json();
    if(!j.ok){ if(st) st.textContent='Upload failed: '+(j.error||''); return; }
    var fld=document.getElementById('genraw_'+sidv); if(fld) fld.value=j.url;
    if(st) st.innerHTML='<span style="color:#7fd99a">\u2713 Reference uploaded \u2014 saved to this SKU\u2019s media folder.</span>';
  }catch(e){ if(st) st.textContent='Upload error: '+e; }
}

// ---- AI sourced suggestions for missing fields ----
function _srcBadge(src){
  var map={
    'eBay':['#10301f','#74e0a3','eBay source'],
    'Amazon competitor (SP-API)':['#15233a','#9cc1ff','Amazon competitor'],
    'AI knowledge':['#2a2440','#c8b6ff','AI knowledge'],
    'AI inference':['#2e2510','#e3b768','AI inference'],
    'none':['#2e1414','#ef9a9a','no source']
  };
  var m=map[src]||map['AI inference'];
  return '<span class="srcbadge" style="background:'+m[0]+';color:'+m[1]+'">'+m[2]+'</span>';
}
function _confBadge(c){
  if(!c) return '';
  var col=c==='high'?'#7fd99a':(c==='medium'?'#e3b768':'#9aa3b2');
  return '<span class="confbadge" style="color:'+col+'">'+esc(c)+'</span>';
}
async function suggestFields(sku){
  var box=document.getElementById('suggestbox_'+sid(sku));
  if(!box) return;
  box.innerHTML='<div class="gendiag"><span class="genspin"></span> Checking eBay \u2192 Amazon competitor \u2192 search \u2192 AI for the missing fields\u2026</div>';
  try{
    var res=await fetch('/suggest',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku})});
    var j=await res.json();
    if(!j.ok){ box.innerHTML='<div class="gendiag bad">\u2717 '+esc(j.error||'failed')+'</div>'; return; }
    if(!j.suggestions || !j.suggestions.length){
      // The /suggest endpoint only knows fields Amazon flagged in a PRIOR Preview
      // (read from Notes). But the schema also has its own required list, and a
      // required field can be EMPTY while unflagged -- that's the field with a
      // star. Cross-check the schema so the message doesn't contradict the stars.
      var _emptyReq = [];
      try{
        var r=(ROWS||[]).find(function(x){return String(x.sku)===String(sku);});
        var pt=(r&&r.product_type)||"";
        var sc=SCHEMAS[pt]||{}; var reqL=sc.req||[];
        var a=(r&&r.attributes)||{};
        reqL.forEach(function(k){
          // consider the field "filled" if it has a value directly OR any of its
          // dotted sub-keys has a value (nested fields like dangerous goods).
          var direct=(k in a)&&String(a[k]).trim()!=="";
          var nested=Object.keys(a).some(function(kk){return kk.indexOf(k+".")===0 && String(a[kk]).trim()!=="";});
          if(!direct && !nested) _emptyReq.push(k);
        });
      }catch(e){}
      if(_emptyReq.length){
        box.innerHTML='<div class="gendiag" style="color:#e3b768">\u2605 '+_emptyReq.length+' required field'+(_emptyReq.length>1?'s':'')+' still need a value (marked with \u2605 below): <b>'+_emptyReq.map(function(x){return esc(x.replace(/_/g," "));}).join(", ")+'</b>.<br><span class="cc">Amazon hasn\u2019t flagged these yet \u2014 fill them now, or click Preview API to confirm exactly what\u2019s required.</span></div>';
      } else {
        box.innerHTML='<div class="gendiag ok">\u2713 No missing required fields detected. (If Amazon flagged some, click Preview API first so they\u2019re known.)</div>';
      }
      return;
    }
    var rows=j.suggestions.map(function(s){
      var sidv=sid(sku)+'__'+sid(s.field);
      if(s._code_owned){
        // Compliance field the app fills automatically on Preview -- show as an
        // info card with NO editable box and NO Apply button, so the user knows
        // it's handled and won't try to fill it by hand.
        return '<div class="sgrow applied" id="sg_'+sidv+'">'+
          '<div class="sghead"><span class="sgfield">'+esc(s.field)+'</span>'+
          '<span class="srcbadge" style="background:#13371f;border-color:#1f7a3a;color:#7fdca0">auto-filled on Preview</span></div>'+
          (s.note?'<div class="sgnote">'+esc(s.note)+'</div>':'')+
        '</div>';
      }
      return '<div class="sgrow" id="sg_'+sidv+'">'+
        '<div class="sghead"><span class="sgfield">'+esc(s.field)+'</span>'+_srcBadge(s.source)+_confBadge(s.confidence)+'</div>'+
        '<textarea class="ed sgval" id="sgval_'+sidv+'">'+esc(s.value||'')+'</textarea>'+
        (s.note?'<div class="sgnote">'+esc(s.note)+'</div>':'')+
        '<div class="sgacts"><button class="sgapply" onclick="applySuggestion(\''+esc(sku)+'\',\''+esc(s.field)+'\',\''+sidv+'\')">Apply this</button></div>'+
      '</div>';
    }).join('');
    box.innerHTML='<div class="sgtop"><b>Suggested values</b> <span class="cc">each tagged with where it came from</span>'+
      '<button class="sgall" onclick="applyAllSuggestions(\''+esc(sku)+'\')">Apply all</button></div>'+rows;
  }catch(e){ box.innerHTML='<div class="gendiag bad">\u2717 '+esc(String(e))+'</div>'; }
}
async function applySuggestion(sku, field, sidv){
  var ta=document.getElementById('sgval_'+sidv);
  var val=ta?ta.value:'';
  var btn=document.querySelector('#sg_'+sidv+' .sgapply');
  if(btn){ btn.disabled=true; btn.textContent='Applying…'; }
  try{
    await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,target:'attr',key:field,value:val})});
    var rowEl=document.getElementById('sg_'+sidv);
    if(rowEl){ rowEl.classList.add('applied'); }
    if(btn){ btn.textContent='\u2713 Applied'; }
    // reflect immediately in the open drawer so scrolling down shows the value
    // (single-apply previously only saved server-side and never refreshed UI).
    try{
      // 1) update the in-memory row so the value persists in the UI model
      var r=(ROWS||[]).find(function(x){return String(x.sku)===String(sku);});
      if(r){ r.attributes=r.attributes||{}; r.attributes[field]=val; }
      // 2) re-render the open drawer's full-data section so the filled value is
      //    visible when you scroll down (single-apply used to never refresh it).
      if(DRAWER_SKU && String(DRAWER_SKU)===String(sku) && typeof fullData==='function'){
        var fr=(ROWS||[]).find(function(x){return String(x.sku)===String(DRAWER_SKU);});
        var host=document.getElementById('fulldata_'+sid(DRAWER_SKU));
        if(host && fr){ host.innerHTML=fullData(fr); }
      }
    }catch(e){}
  }catch(e){ if(btn){ btn.disabled=false; btn.textContent='Apply this'; } toast('Could not apply: '+e); }
}
async function applyAllSuggestions(sku){
  var box=document.getElementById('suggestbox_'+sid(sku));
  if(!box) return;
  var rows=box.querySelectorAll('.sgrow:not(.applied)');
  for(var i=0;i<rows.length;i++){
    var id=rows[i].id.replace('sg_','');
    var field=rows[i].querySelector('.sgfield').textContent;
    await applySuggestion(sku, field, id);
  }
  toast('Applied all suggestions');
  loadRows();
}

// ============================================================================
// AUTO-FIX LOOP: Suggest → Apply → Preview → check errors → repeat until clean
// or progress stalls. Max 8 rounds. Reports back through a floating status box.
//
// TRACE CAPTURE: every round records the AI's suggestions (field + value +
// source + confidence), which values were actually applied to the sheet, the
// full Amazon error banner (verbatim [E] lines), and the changed error set.
// A "Copy trace" button dumps the whole diagnostic to the clipboard as a
// pasteable block for handing to Claude in this chat -- so you can share the
// exact sequence of what happened per round instead of reconstructing it.
// ============================================================================
window.AUTOFIX_STATE = null;

async function autoFixLoop(sku){
  if(!sku) return;
  if(window.AUTOFIX_STATE && window.AUTOFIX_STATE.sku === sku){
    toast('Auto-fix already running for this SKU'); return;
  }
  const MAX_ROUNDS = 8;
  const state = {sku:sku, round:0, prevErrors:null, stopped:false, cancelled:false,
                  trace: [], startedAt: new Date().toISOString()};
  window.AUTOFIX_STATE = state;
  window._AUTOFIX_LAST_STATE = state;   // set NOW so bulkAutoFix can read it back regardless of which panel path we take

  // If we're inside a bulk batch, DON'T create our own panel -- the batch panel
  // is already on screen and using the same DOM slot ('autofix_panel'). We
  // still capture the full trace in `state` so the batch panel can render it,
  // but skip the per-SKU floating box to avoid destroying the batch UI.
  const insideBulk = !!(window.BULK_AUTOFIX && !window.BULK_AUTOFIX.done);
  const panel = insideBulk ? _autoFixNullPanel() : _autoFixPanel(sku, state);
  if(!insideBulk){
    panel.show('Auto-fix started for '+sku);
  }

  try{
    while(state.round < MAX_ROUNDS && !state.cancelled){
      state.round++;
      const roundEntry = {
        round: state.round,
        started_at: new Date().toISOString(),
        suggestions: [],
        applied: [],
        skipped: [],
        preview_verdict: null,
        preview_error_fields: [],
        preview_raw_lines: [],
        diagnosis: '',
      };
      state.trace.push(roundEntry);
      panel.step('Round '+state.round+' of '+MAX_ROUNDS+' — asking AI for suggestions…');

      // --- 1. Get suggestions from AI ---
      let sugRes;
      try{
        sugRes = await fetch('/suggest',{method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({sku:sku})});
        sugRes = await sugRes.json();
      }catch(e){
        roundEntry.diagnosis = '/suggest network error: '+String(e);
        panel.fail('Round '+state.round+': /suggest failed — see trace');
        panel.renderTrace();
        break;
      }
      if(!sugRes.ok){
        // If the error mentions "sku not found" it means the row isn't in the
        // current worksheet -- usually because the user switched account
        // workspaces (or the app was restarted) after ticking this SKU.
        // Explain that plainly so the trace tells the user what to fix.
        const errRaw = String(sugRes.error || 'no error field');
        const isMissing = /sku not found|not in.*view|not in.*sheet/i.test(errRaw);
        roundEntry.diagnosis = isMissing
          ? ('SKU not visible in current workspace. This usually means you switched '+
              'account workspaces (or the app restarted) after ticking this SKU. '+
              'Click into the correct account workspace first, then try again. '+
              '(Raw: '+errRaw+')')
          : ('/suggest returned ok=false: '+errRaw);
        panel.fail('Round '+state.round+': '+(isMissing ? 'SKU not in current workspace' : 'suggestion API error')+' — see trace');
        panel.renderTrace();
        break;
      }
      // Capture EVERY suggestion (both code_owned info cards and AI-fillable ones)
      // so the trace shows exactly what the system chose per field.
      roundEntry.suggestions = (sugRes.suggestions||[]).map(function(s){
        return {
          field: s.field, value: s.value || '', source: s.source || '',
          confidence: s.confidence || '', note: s.note || '',
          code_owned: !!s._code_owned,
        };
      });
      const suggestions = (sugRes.suggestions||[]).filter(function(s){ return !s._code_owned; });
      panel.step('Round '+state.round+': got '+suggestions.length+' AI suggestions ('+
                 (roundEntry.suggestions.length-suggestions.length)+' code-owned)');

      // --- 2. Apply each suggestion ---
      for(let i=0;i<suggestions.length;i++){
        const s = suggestions[i];
        if(!s.value){
          roundEntry.skipped.push({field:s.field, reason:'empty AI value'});
          continue;
        }
        try{
          const editRes = await fetch('/edit',{method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({sku:sku, target:'attr', key:s.field, value:s.value})});
          const editJson = await editRes.json();
          if(editJson.ok){
            roundEntry.applied.push({field:s.field, value:s.value, source:s.source});
          } else {
            const err = String(editJson.error || 'unknown');
            roundEntry.skipped.push({field:s.field, reason:'edit failed: '+err});
            // If the sheet says the SKU doesn't exist, all further edits in this
            // round WILL fail identically -- abort the loop immediately with a
            // clear diagnosis instead of grinding through every suggestion.
            if(/sku not found|not in.*sheet|not in.*view/i.test(err)){
              roundEntry.diagnosis = 'SKU not visible in current workspace at edit time. '+
                                      'The row was found by /suggest but had disappeared by /edit -- '+
                                      'this usually means you switched workspaces mid-run or a '+
                                      'concurrent submit moved the row. Click into the correct '+
                                      'account workspace and retry.';
              panel.fail('Round '+state.round+': SKU disappeared from workspace between /suggest and /edit — see trace');
              panel.renderTrace();
              // Break out of BOTH the inner apply loop and the outer round loop
              window._AUTOFIX_STOP = true;
              break;
            }
          }
        }catch(e){
          roundEntry.skipped.push({field:s.field, reason:'edit exception: '+String(e)});
        }
      }
      if(window._AUTOFIX_STOP){ window._AUTOFIX_STOP = false; break; }
      panel.step('Round '+state.round+': applied '+roundEntry.applied.length+
                 ' / skipped '+roundEntry.skipped.length);

      // Count code-owned suggestions: these DON'T get "applied" (nothing to
      // apply -- the generator fills them itself when Preview runs), but they
      // ARE progress. If the current round applied 0 AI values but flagged
      // code-owned fields exist, running Preview WILL fill them via the
      // generator's compliance block. So don't stop when the only work left
      // is code-owned -- Preview is what actually resolves those.
      const codeOwnedCount = roundEntry.suggestions.filter(function(s){ return s.code_owned; }).length;
      if(roundEntry.applied.length === 0 && codeOwnedCount === 0 && state.round > 1){
        roundEntry.diagnosis = 'Nothing new to apply after round 1 and no code-owned fields to fill. AI has no more suggestions.';
        panel.stop('Round '+state.round+': nothing new to apply. Stopping.');
        panel.renderTrace();
        break;
      }

      // --- 3. Run Preview and capture EVERY line ---
      panel.step('Round '+state.round+': running Preview…');
      const verdict = await _autoFixPreview(sku, panel, roundEntry);
      roundEntry.preview_verdict = verdict.kind;
      roundEntry.preview_error_fields = verdict.errorFields || [];
      roundEntry.preview_verdict_raw = verdict.raw || '';

      if(state.cancelled){ break; }

      // --- 4. Interpret verdict ---
      if(verdict.kind === 'ok_preview'){
        roundEntry.diagnosis = 'Amazon accepted the Preview. Ready to Submit.';
        panel.done('✓ Round '+state.round+': Amazon accepted Preview. Ready to Submit!');
        panel.renderTrace();
        loadRows();
        break;
      }

      if(verdict.kind === 'network' || verdict.kind === 'nocreds' ||
          verdict.kind === 'busy' || verdict.kind === 'timeout'){
        roundEntry.diagnosis = 'Environment issue ('+verdict.kind+') — not a listing problem.';
        panel.fail('Round '+state.round+': '+verdict.kind+' — see trace');
        panel.renderTrace();
        break;
      }

      if(verdict.kind === 'error'){
        const errKey = (verdict.errorFields||[]).slice().sort().join('|');
        roundEntry.diagnosis = 'Amazon flagged '+verdict.n+' error(s) on fields: '+
                                (verdict.errorFields||[]).join(', ');
        panel.step('Round '+state.round+': Amazon flagged '+verdict.n+' error(s) on: '+
                   (verdict.errorFields||[]).join(', '));
        if(state.prevErrors && state.prevErrors === errKey){
          roundEntry.diagnosis += ' — IDENTICAL to previous round, no progress.';
          panel.stop('Round '+state.round+': Same errors as last round. Auto-fix cannot resolve these. Stopped.');
          panel.renderTrace();
          break;
        }
        state.prevErrors = errKey;
        panel.renderTrace();   // incremental render so user sees progress
        continue;
      }

      roundEntry.diagnosis = 'Unclear outcome ('+verdict.kind+'). Stopped for safety.';
      panel.fail('Round '+state.round+': unclear outcome — see trace');
      panel.renderTrace();
      break;
    }
    if(state.round >= MAX_ROUNDS && !state.cancelled){
      panel.stop('Hit max rounds ('+MAX_ROUNDS+'). Stopped. Review trace to see the loop pattern.');
      panel.renderTrace();
    }
  } finally {
    window.AUTOFIX_STATE = null;
    // Skip the per-SKU sheet refresh when running inside a batch -- the batch
    // wrapper calls loadRows() once at the very end. Doing it per SKU would
    // hit /rows 20+ times in a bulk run.
    if(!(window.BULK_AUTOFIX && !window.BULK_AUTOFIX.done)){
      loadRows();
    }
  }
}

// Runs one Preview and returns a verdict object. Also appends every stream line
// to roundEntry.preview_raw_lines so the trace has the full Amazon response
// for that round.
function _autoFixPreview(sku, panel, roundEntry){
  return new Promise(function(resolve){
    const url = '/run/api?skus='+encodeURIComponent(sku)+_minParam();
    const es = new EventSource(url);
    let verdict = null;
    let errorFields = [];
    let sawStart = false;
    let done = false;
    function finish(v){
      if(done) return; done=true;
      try{ es.close(); }catch(e){}
      v.errorFields = errorFields;
      resolve(v);
    }
    es.onmessage = function(e){
      const d = e.data || '';
      if(panel) panel.log(d);
      if(roundEntry) roundEntry.preview_raw_lines.push(d);
      if(d.indexOf('[start]') === 0) sawStart = true;
      // parse [E] field markers -- track ALL, not just first-per-line, in case
      // multiple errors share one message
      const mm = d.match(/\[E\]\s*([a-z0-9_.]+)/g);
      if(mm){
        mm.forEach(function(x){
          const m2 = x.match(/\[E\]\s*([a-z0-9_.]+)/);
          if(m2 && errorFields.indexOf(m2[1]) < 0) errorFields.push(m2[1]);
        });
      }
      // detect final verdict lines
      if(d.indexOf(sku) >= 0){
        const low = d.toLowerCase();
        let m = d.match(/(\d+)\s+error\(s\)/i);
        if(m){ verdict = {kind:'error', n:parseInt(m[1]), raw:d}; }
        else if(low.indexOf('missing') >= 0 && low.indexOf('skip') >= 0){ verdict = {kind:'missing', raw:d}; }
        else if(low.indexOf('api_ready') >= 0 || low.indexOf('preview clean') >= 0){ verdict = {kind:'ok_preview', raw:d}; }
        else if(low.indexOf('api call failed') >= 0 || low.indexOf('api_error') >= 0){ verdict = {kind:'error', n:0, raw:d}; }
      }
      if(d.toLowerCase().indexOf('no seller_id') >= 0) verdict = {kind:'nocreds', raw:d};
      if(d.indexOf('[done]') === 0 || d.indexOf('[busy]') >= 0){
        if(d.indexOf('[busy]') >= 0 && !verdict) verdict = {kind:'busy', raw:d};
        finish(verdict || {kind:'unknown', raw:d});
      }
      if(/getaddrinfo failed|failed to resolve|nameresolutionerror/i.test(d)){
        verdict = {kind:'network', raw:d};
      }
    };
    es.onerror = function(){
      // EventSource fires onerror on server-side stream end too, so treat this
      // as "the stream is done"; use whatever verdict we've collected so far.
      if(!done) finish(verdict || {kind: sawStart ? 'unknown' : 'network', raw:'stream ended'});
    };
    setTimeout(function(){
      if(!done) finish(verdict || {kind:'timeout', raw:'exceeded 5 minutes'});
    }, 5*60*1000);
  });
}

// Build a plain-text trace of the whole loop, ready to paste to Claude.
function _autoFixTraceText(state){
  const lines = [];
  lines.push('=== AUTO-FIX TRACE ===');
  lines.push('SKU: '+state.sku);
  lines.push('Started: '+state.startedAt);
  lines.push('Rounds run: '+state.trace.length+' / '+8);
  lines.push('');
  state.trace.forEach(function(r){
    lines.push('---- ROUND '+r.round+' ('+r.started_at+') ----');
    lines.push('');
    lines.push('SUGGESTIONS FROM AI ('+r.suggestions.length+' total):');
    if(r.suggestions.length === 0){
      lines.push('  (none)');
    } else {
      r.suggestions.forEach(function(s){
        const tag = s.code_owned ? '[CODE-OWNED]' : '[AI]';
        lines.push('  '+tag+' '+s.field+' = '+JSON.stringify(s.value)+
                    '  (source: '+(s.source||'-')+', confidence: '+(s.confidence||'-')+')');
        if(s.note) lines.push('    note: '+s.note);
      });
    }
    lines.push('');
    lines.push('APPLIED TO SHEET ('+r.applied.length+'):');
    if(r.applied.length === 0){
      lines.push('  (none applied)');
    } else {
      r.applied.forEach(function(a){
        lines.push('  ✓ '+a.field+' = '+JSON.stringify(a.value)+'  (from: '+(a.source||'-')+')');
      });
    }
    if(r.skipped.length){
      lines.push('');
      lines.push('SKIPPED ('+r.skipped.length+'):');
      r.skipped.forEach(function(x){
        lines.push('  ✗ '+x.field+' — '+x.reason);
      });
    }
    lines.push('');
    lines.push('PREVIEW VERDICT: '+r.preview_verdict);
    if(r.preview_error_fields && r.preview_error_fields.length){
      lines.push('Amazon flagged ('+r.preview_error_fields.length+'): '+
                  r.preview_error_fields.join(', '));
    }
    lines.push('');
    lines.push('PREVIEW STREAM (full Amazon response, verbatim):');
    // Include EVERY raw line, not a filtered subset. Filtering was hiding
    // parser mismatches (e.g. verdict `unknown` with an empty filtered view
    // when the stream actually did contain success/error lines the parser
    // failed to recognise). The full stream lets us see what Amazon sent
    // vs what our parser did with it, without which "unknown outcome"
    // diagnoses are un-debuggable.
    const raw_all = r.preview_raw_lines || [];
    if(raw_all.length){
      raw_all.forEach(function(x){ lines.push('  | '+x); });
    } else {
      lines.push('  (no stream lines received)');
    }
    lines.push('');
    if(r.diagnosis){
      lines.push('DIAGNOSIS: '+r.diagnosis);
      lines.push('');
    }
  });
  lines.push('=== END TRACE ===');
  return lines.join('\n');
}

async function _autoFixCopyTrace(){
  const state = window._AUTOFIX_LAST_STATE || window.AUTOFIX_STATE;
  if(!state){ toast('No auto-fix trace to copy'); return; }
  const text = _autoFixTraceText(state);
  try{
    await navigator.clipboard.writeText(text);
    toast('Trace copied — paste into Claude chat');
  }catch(e){
    // Clipboard API can fail in non-secure contexts; fall back to a prompt
    const w = window.open('', '_blank', 'width=700,height=500');
    if(w){
      w.document.title = 'Auto-fix trace';
      w.document.body.innerHTML = '<pre style="font:12px ui-monospace,Consolas,monospace;padding:12px;white-space:pre-wrap">'+
        text.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</pre>';
    } else {
      prompt('Copy the trace below:', text);
    }
  }
}

// A no-op panel used when autoFixLoop runs inside a bulk batch. The batch has
// its own panel; we just need the API surface (show/step/log/etc.) so
// autoFixLoop's calls are harmless.
function _autoFixNullPanel(){
  const noop = function(){};
  return {show:noop, step:noop, log:noop, done:noop, stop:noop, fail:noop, renderTrace:noop};
}

// Floating progress panel with an in-panel trace view + Copy button
function _autoFixPanel(sku, state){
  let el = document.getElementById('autofix_panel');
  if(el){ el.remove(); }
  el = document.createElement('div');
  el.id = 'autofix_panel';
  el.style.cssText = 'position:fixed;bottom:20px;right:20px;width:560px;max-height:80vh;'+
    'background:#141b2b;border:1px solid #3b4d70;border-radius:10px;padding:12px;'+
    'box-shadow:0 8px 24px rgba(0,0,0,0.5);z-index:9999;font-size:12px;color:#e8eaed;'+
    'display:flex;flex-direction:column;gap:8px';
  el.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:center;font-weight:600">'+
      '<span>✦ Auto-fix: '+esc(sku)+'</span>'+
      '<div style="display:flex;gap:8px;align-items:center">'+
        '<button id="autofix_copy" onclick="_autoFixCopyTrace()" '+
          'style="background:#5b3fb8;color:#fff;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">'+
          '📋 Copy trace</button>'+
        '<button onclick="if(window.AUTOFIX_STATE)window.AUTOFIX_STATE.cancelled=true;this.parentElement.parentElement.parentElement.remove()" '+
        'style="background:none;color:#e8eaed;border:none;cursor:pointer;font-size:16px">✕</button>'+
      '</div>'+
    '</div>'+
    '<div id="autofix_status" style="color:#9cc1ff"></div>'+
    '<div style="display:flex;gap:6px;font-size:10px">'+
      '<button onclick="document.getElementById(\'autofix_traceview\').style.display=\'none\';document.getElementById(\'autofix_log\').style.display=\'block\'" '+
        'style="background:#0d1220;border:1px solid #263145;color:#e8eaed;padding:3px 8px;border-radius:4px;cursor:pointer">Live log</button>'+
      '<button onclick="document.getElementById(\'autofix_log\').style.display=\'none\';document.getElementById(\'autofix_traceview\').style.display=\'block\'" '+
        'style="background:#0d1220;border:1px solid #263145;color:#e8eaed;padding:3px 8px;border-radius:4px;cursor:pointer">Round-by-round trace</button>'+
    '</div>'+
    '<div id="autofix_log" style="background:#0d1220;border:1px solid #263145;border-radius:6px;'+
      'padding:6px 8px;font-family:ui-monospace,Consolas,monospace;font-size:10px;'+
      'max-height:280px;overflow:auto;flex:1"></div>'+
    '<div id="autofix_traceview" style="display:none;background:#0d1220;border:1px solid #263145;border-radius:6px;'+
      'padding:6px 8px;font-family:ui-monospace,Consolas,monospace;font-size:10px;'+
      'max-height:280px;overflow:auto;flex:1;white-space:pre-wrap"></div>';
  document.body.appendChild(el);
  window._AUTOFIX_LAST_STATE = state;   // keep after the loop ends so Copy still works
  return {
    show: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
    },
    step: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
    },
    log: function(line){
      const l = document.getElementById('autofix_log');
      if(l){ l.textContent += line+'\n'; l.scrollTop = l.scrollHeight; }
    },
    done: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:#74e0a3">'+esc(msg)+'</span>';
    },
    stop: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:#e3b768">⚠ '+esc(msg)+'</span>';
    },
    fail: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:#e0696b">✗ '+esc(msg)+'</span>';
    },
    renderTrace: function(){
      const t = document.getElementById('autofix_traceview');
      if(t) t.textContent = _autoFixTraceText(state);
    },
  };
}

// ============================================================================
// BULK AUTO-FIX: run autoFixLoop sequentially across every selected SKU.
// Sequential (not parallel) because each Preview call hits SP-API and Amazon
// rate-limits per-seller; running 20 in parallel would trip 429s and slow
// everything down. A shared trace records every SKU's rounds so one Copy
// button gives you the whole batch's diagnostic to paste to Claude.
// ============================================================================
window.BULK_AUTOFIX = null;

async function bulkAutoFix(){
  const skus = selectedSkus();
  if(!skus.length){ toast("Nothing selected — tick some listings first"); return; }
  if(window.BULK_AUTOFIX && !window.BULK_AUTOFIX.done){
    toast("A batch auto-fix is already running"); return;
  }

  // PRE-FLIGHT: verify every selected SKU is actually in the current workspace.
  // The batch UI persists SELECTED across page-loads and Flask restarts, so it's
  // possible to tick SKUs on Account A, switch to Account B (or restart Flask
  // which resets active_account to default), and end up asking Amazon about
  // rows that aren't visible to the current worksheet. Without this check the
  // /suggest and /edit endpoints just 404 with cryptic 'sku not found in
  // current view' messages -- the batch trace shows those but doesn't explain
  // WHY, which wastes the user's time.
  //
  // The current view rows are already loaded into ROWS as of the last
  // loadRows() call. Cross-check locally before hitting the network.
  const inView = new Set((ROWS || []).map(r => String(r.sku || "")));
  const missing = skus.filter(s => !inView.has(String(s)));
  if(missing.length){
    const inViewCount = skus.length - missing.length;
    const msg = "⚠ "+missing.length+" of "+skus.length+" selected SKU(s) are NOT in the current workspace view:\n\n" +
                 missing.slice(0, 10).join("\n") +
                 (missing.length > 10 ? "\n  ...and "+(missing.length-10)+" more" : "") +
                 "\n\nThis usually means you switched account workspaces (or the app restarted) after ticking them. " +
                 "The auto-fix loop can't Suggest/Apply/Preview rows it can't see.\n\n" +
                 (inViewCount > 0
                   ? "Continue anyway with the "+inViewCount+" SKU(s) still in view?"
                   : "None of the selected SKUs are in this view. Please click into the correct account workspace first and re-tick.");
    if(inViewCount === 0){ alert(msg); return; }
    if(!confirm(msg)) return;
    // Filter to just the SKUs actually visible
    for(let i = skus.length - 1; i >= 0; i--){
      if(!inView.has(String(skus[i]))) skus.splice(i, 1);
    }
  }

  if(!confirm("Run Auto-fix on "+skus.length+" selected listing(s)?\n\n"+
              "Each SKU will loop through Suggest→Apply→Preview until Amazon accepts "+
              "or the loop can\u2019t make progress. This is sequential (one at a time) "+
              "so it may take a few minutes.")) return;

  const batch = {
    skus: skus, done: false, cancelled: false, startedAt: new Date().toISOString(),
    per_sku_states: [],    // one autoFix state per SKU
    current_idx: -1,
    summary: {ok: 0, stuck: 0, failed: 0},
  };
  window.BULK_AUTOFIX = batch;

  const panel = _bulkAutoFixPanel(batch);
  panel.show("Batch auto-fix: "+skus.length+" listing(s)");

  try{
    for(let i=0; i<skus.length; i++){
      if(batch.cancelled){ break; }
      batch.current_idx = i;
      const sku = skus[i];
      panel.step("["+(i+1)+"/"+skus.length+"] "+sku+" — running…");

      // Run the single-SKU loop and capture its state into the batch trace.
      // The single-SKU loop already stores state on window.AUTOFIX_STATE and
      // window._AUTOFIX_LAST_STATE so we can read it back when it finishes.
      window.AUTOFIX_STATE = null;
      try{
        await autoFixLoop(sku);
      }catch(e){
        batch.summary.failed++;
        batch.per_sku_states.push({sku: sku, error: String(e)});
        panel.step("["+(i+1)+"/"+skus.length+"] "+sku+" — CRASHED: "+String(e));
        panel.renderTrace();
        continue;
      }
      // autoFixLoop finished — pull the final state
      const finalState = window._AUTOFIX_LAST_STATE;
      if(finalState && finalState.sku === sku){
        batch.per_sku_states.push(finalState);
        // Judge the outcome from the last round's verdict (trace may be empty
        // if the loop bailed before completing any round -- e.g. /suggest 500)
        const lastRound = (finalState.trace && finalState.trace.length)
                          ? finalState.trace[finalState.trace.length-1]
                          : null;
        if(lastRound && lastRound.preview_verdict === 'ok_preview'){
          batch.summary.ok++;
        } else if(lastRound && lastRound.preview_verdict === 'error'){
          batch.summary.stuck++;
        } else {
          batch.summary.failed++;
        }
      } else {
        batch.summary.failed++;
        batch.per_sku_states.push({sku: sku, error: "no state captured"});
      }
      panel.renderTrace();
    }
    batch.done = true;
    if(batch.cancelled){
      panel.stop("Cancelled after "+batch.current_idx+" of "+skus.length+" SKU(s). "+
                  "Cleared: "+batch.summary.ok+" · stuck: "+batch.summary.stuck+" · failed: "+batch.summary.failed);
    } else {
      panel.done("Batch complete. Cleared: "+batch.summary.ok+
                 " · stuck: "+batch.summary.stuck+" · failed: "+batch.summary.failed);
    }
    panel.renderTrace();
  } finally {
    loadRows();
  }
}

// Build one large trace text covering every SKU in the batch, ready to paste
// to Claude in one message.
function _bulkAutoFixTraceText(batch){
  const lines = [];
  lines.push('=== BULK AUTO-FIX BATCH TRACE ===');
  lines.push('Started: '+batch.startedAt);
  lines.push('SKUs: '+batch.skus.length);
  lines.push('Summary: cleared='+batch.summary.ok+
              ' · stuck='+batch.summary.stuck+
              ' · failed='+batch.summary.failed);
  lines.push('');
  batch.per_sku_states.forEach(function(s, idx){
    lines.push('################################################################');
    lines.push('# SKU '+(idx+1)+' of '+batch.skus.length+': '+(s.sku||'(unknown)'));
    lines.push('################################################################');
    if(s.error){
      lines.push('LOOP ERROR: '+s.error);
      lines.push('');
      return;
    }
    if(!s.trace){
      lines.push('(no trace captured)');
      lines.push('');
      return;
    }
    // Reuse the single-SKU trace formatter
    lines.push(_autoFixTraceText(s));
    lines.push('');
  });
  lines.push('=== END BATCH TRACE ===');
  return lines.join('\n');
}

async function _bulkAutoFixCopyTrace(){
  const batch = window.BULK_AUTOFIX;
  if(!batch){ toast('No batch trace to copy'); return; }
  const text = _bulkAutoFixTraceText(batch);
  try{
    await navigator.clipboard.writeText(text);
    toast('Batch trace copied — paste into Claude chat');
  }catch(e){
    const w = window.open('', '_blank', 'width=800,height=600');
    if(w){
      w.document.title = 'Bulk auto-fix trace';
      w.document.body.innerHTML = '<pre style="font:12px ui-monospace,Consolas,monospace;padding:12px;white-space:pre-wrap">'+
        text.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</pre>';
    } else {
      prompt('Copy the trace below:', text);
    }
  }
}

function _bulkAutoFixPanel(batch){
  // Reuse the same slot as single-SKU panel so we never have two on screen
  let el = document.getElementById('autofix_panel');
  if(el){ el.remove(); }
  el = document.createElement('div');
  el.id = 'autofix_panel';
  el.style.cssText = 'position:fixed;bottom:20px;right:20px;width:620px;max-height:80vh;'+
    'background:#141b2b;border:1px solid #3b4d70;border-radius:10px;padding:12px;'+
    'box-shadow:0 8px 24px rgba(0,0,0,0.5);z-index:9999;font-size:12px;color:#e8eaed;'+
    'display:flex;flex-direction:column;gap:8px';
  el.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:center;font-weight:600">'+
      '<span>✦ Batch Auto-fix ('+batch.skus.length+' SKU'+(batch.skus.length===1?'':'s')+')</span>'+
      '<div style="display:flex;gap:8px;align-items:center">'+
        '<button onclick="_bulkAutoFixCopyTrace()" '+
          'style="background:#5b3fb8;color:#fff;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">'+
          '📋 Copy batch trace</button>'+
        '<button onclick="if(window.BULK_AUTOFIX)window.BULK_AUTOFIX.cancelled=true;if(window.AUTOFIX_STATE)window.AUTOFIX_STATE.cancelled=true;this.parentElement.parentElement.parentElement.remove()" '+
          'style="background:none;color:#e8eaed;border:none;cursor:pointer;font-size:16px" title="Cancel batch and close">✕</button>'+
      '</div>'+
    '</div>'+
    '<div id="bulk_autofix_status" style="color:#9cc1ff"></div>'+
    '<div id="bulk_autofix_summary" style="font-size:11px;color:#bfc7d5"></div>'+
    '<div id="bulk_autofix_traceview" style="background:#0d1220;border:1px solid #263145;border-radius:6px;'+
      'padding:6px 8px;font-family:ui-monospace,Consolas,monospace;font-size:10px;'+
      'max-height:400px;overflow:auto;flex:1;white-space:pre-wrap"></div>';
  document.body.appendChild(el);
  return {
    show: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
    },
    step: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
      const sm = document.getElementById('bulk_autofix_summary');
      if(sm) sm.textContent = 'Progress: '+batch.summary.ok+' cleared · '+
                              batch.summary.stuck+' stuck · '+batch.summary.failed+' failed';
    },
    done: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span style="color:#74e0a3">✓ '+esc(msg)+'</span>';
    },
    stop: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span style="color:#e3b768">⚠ '+esc(msg)+'</span>';
    },
    renderTrace: function(){
      const t = document.getElementById('bulk_autofix_traceview');
      if(t) t.textContent = _bulkAutoFixTraceText(batch);
    },
  };
}

function roCell(v){ return `<span class="ro">${esc(v==null?"":String(v))}</span>`; }
// Suggested Amazon browse-node IDs per product type (mirrors the generator's
// PT_DEFAULT_NODE). Used only to offer a sensible default; the field stays optional.
const PT_NODE_MAP = {
  "HEALTH_PERSONAL_CARE":"66280031", "BEAUTY":"18918424031", "KITCHEN":"3187111031",
  "HOME":"3579745031", "COOKWARE_SET":"11715891", "LAMP":"10709381",
  "HARDWARE":"1938668031", "SPORT_TARGET":"26971320031"
};
function PT_NODE_DEFAULT(){
  let pt="";
  try{ pt = (window.OPT_CURRENT&&OPT_CURRENT.product_type) || (window.OPT_EDIT_ROW&&OPT_EDIT_ROW.product_type) || ""; }catch(e){}
  return PT_NODE_MAP[(pt||"").toUpperCase()] || "";
}
// Product Type control: defaults to Amazon's catalogue-assigned type (the
// ground truth). The static list is still selectable, but choosing anything
// other than the Amazon-assigned type shows a clear warning, because that's
// what causes "product type not allowed" rejections.
function productTypeCell(sku, r){
  const amazonPT = String(r.product_type||"").trim();   // assigned by get_catalog_item
  // option list = the Amazon type first (always), then the static list
  const opts = [];
  if(amazonPT) opts.push(amazonPT);
  (PTYPES||[]).forEach(p=>{ if(p && opts.indexOf(p)<0) opts.push(p); });
  const wid="pt_"+sid(sku);
  let h=`<select id="${wid}" class="ed" onchange="onProductTypeChange(this,'${esc(sku)}','${esc(amazonPT)}')">`;
  if(!amazonPT) h+=`<option value="" selected>—</option>`;
  opts.forEach(o=>{
    const isAmz = (o===amazonPT);
    h+=`<option value="${esc(o)}"${o===amazonPT?" selected":""}>${esc(o)}${isAmz?" (Amazon-assigned)":""}</option>`;
  });
  h+=`</select>`;
  h+=`<div id="${wid}_warn" class="cwarn" style="display:none"></div>`;
  return h;
}
function onProductTypeChange(sel, sku, amazonPT){
  const warn=document.getElementById("pt_"+sid(sku)+"_warn");
  const chosen=sel.value;
  if(warn){
    if(amazonPT && chosen && chosen!==amazonPT){
      warn.style.display="block";
      warn.innerHTML="⚠ Amazon assigned this product the type <b>"+esc(amazonPT)+"</b>. "
        +"Listing it as <b>"+esc(chosen)+"</b> may be rejected. Only change this if you are certain.";
    } else { warn.style.display="none"; warn.innerHTML=""; }
  }
  // save via the normal column path
  saveEdit(sel, sku, "col", "Product Type");
  // refresh the schema for the newly chosen type so the fields update
  if(typeof loadSchemas==="function"){ var _r=ROWS.find(x=>String(x.sku)===String(sku)); loadSchemas([chosen], true, _r?rowMkt(_r):WS_MARKET).then(()=>{ if(DRAWER_SKU===sku) openDrawer(sku); }); }
}
function editCell(sku,target,key,value,opts,multiline){
  const cur=(value==null?"":String(value));
  // recommended_browse_nodes is a single Amazon category NODE ID (a number), not a
  // pick-list — Amazon never ships the full node tree as an enum. Force a free-text
  // input so users aren't stuck with an empty/irrelevant dropdown.
  const isBrowseNode = /(^|\.)recommended_browse_nodes$|(^|\.)browse_node/.test(key||"");
  if(isBrowseNode){
    const def=(typeof PT_NODE_DEFAULT==="function")?PT_NODE_DEFAULT():"";
    const ph = def?("e.g. "+def+" (suggested for this type) — optional"):"e.g. 66280031 — optional";
    return `<input class="ed" value="${esc(cur)}" placeholder="${esc(ph)}" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">`
      + (def&&!cur?`<div class="cc" style="font-size:11px;margin-top:3px">Leave blank to let Amazon auto-assign the category, or use the suggested node <a href="#" onclick="(function(e){e.preventDefault();var i=e.target.closest('td').querySelector('input');i.value='${esc(def)}';i.dispatchEvent(new Event('change'));})(event)">${esc(def)}</a>.</div>`:"");
  }
  if(opts&&opts.length){
    let h=`<select class="ed" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">`;
    h+=`<option value=""${cur===""?" selected":""}>—</option>`;
    if(cur&&!opts.includes(cur)) h+=`<option value="${esc(cur)}" selected>${esc(cur)} (current)</option>`;
    opts.forEach(o=>{h+=`<option value="${esc(o)}"${o===cur?" selected":""}>${esc(o)}</option>`;});
    return h+`</select>`;
  }
  if(multiline) return `<textarea class="ed" rows="3" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">${esc(cur)}</textarea>`;
  return `<input class="ed" value="${esc(cur)}" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">`;
}
function edRow(label,ctrl,hint,prov,sub,req,softReq){ const provHtml = (typeof prov==='string') ? srcBadge(prov) : (prov?iBtnEntry(prov):""); const reqHtml = softReq ? '<span class="reqsoft" title="The schema lists this as required, but Amazon\u2019s last Preview accepted the listing WITHOUT it. Fill it only if a later Preview flags it.">\u2606 schema-listed</span>' : (req?'<span class="reqstar" title="Required by Amazon">\u2605</span>':""); return `<tr class="${hint?'flaggedrow':''}${sub?' subrow':''}"><td class="k">${sub?'<span class="subarrow">\u21b3</span> ':''}${esc(_cleanLabel(label))}${reqHtml}${provHtml}${hint?` <span class="fixhint">\u26a0 ${esc(hint)}</span>`:""}</td><td class="v">${ctrl}</td></tr>`; }
function _cleanLabel(s){ s=String(s==null?"":s); s=s.replace(/&nbsp;/g,"").replace(/\u21b3/g,"").replace(/[._]/g," ").trim(); return s.charAt(0).toUpperCase()+s.slice(1); }
function wideRow(label,ctrl){ return `<tr><td colspan="2" class="wcell"><div class="wlab">${esc(label)}</div>${ctrl}</td></tr>`; }
function ccount(el, cid, limit){
  const c=document.getElementById(cid); if(!c) return;
  const useBytes = el.getAttribute && el.getAttribute("data-bytes")==="1";
  const warnAt = parseInt((el.getAttribute&&el.getAttribute("data-warn"))||"0",10)||0;
  const n = useBytes ? (function(){try{return new Blob([el.value]).size;}catch(e){return el.value.length;}})() : el.value.length;
  const unit = useBytes ? " bytes" : " chars";
  c.textContent=n+(limit?(' / '+limit):'')+unit;
  const over = limit && n>limit;
  const warn = warnAt && n>warnAt && !over;
  c.classList.toggle('over', !!over);
  c.classList.toggle('warn', !!warn);
}
// Combined indexing meter: Amazon indexes only the FIRST ~1,000 BYTES across ALL
// 5 bullets COMBINED (not per bullet). Show how much of that budget is used.
function bulletMeter(){
  const meter=document.getElementById('bulletIdxMeter'); if(!meter) return;
  let total=0;
  for(let i=1;i<=5;i++){
    const ta=document.querySelector('textarea[data-bkt="bullet'+i+'"]');
    if(ta){ try{ total+=new Blob([ta.value]).size; }catch(e){ total+=ta.value.length; } }
  }
  const cap=1000;
  const pct=Math.min(100, Math.round(total/cap*100));
  const over=total>cap;
  meter.innerHTML='<div class="idxbar"><div class="idxfill'+(over?' over':'')+'" style="width:'+pct+'%"></div></div>'
    +'<span class="idxlbl'+(over?' over':'')+'">'+total+' / '+cap+' bytes indexed across all 5 bullets'
    +(over?' — content past 1,000 bytes is NOT indexed (still shown to shoppers)':'')+'</span>';
}
// byte length (UTF-8) — Amazon counts backend search terms + bullet indexing in BYTES, not chars
function byteLen(s){ try{ return new Blob([String(s==null?"":s)]).size; }catch(e){ return String(s==null?"":s).length; } }
// Approx file size of a data: URL (base64 -> bytes) as a human string.
function dataUrlSize(durl){
  try{
    const i=String(durl).indexOf(",");
    const b64=i>=0?String(durl).slice(i+1):String(durl);
    const bytes=Math.floor(b64.length*3/4);
    if(bytes>=1048576) return (bytes/1048576).toFixed(1)+" MB";
    if(bytes>=1024) return Math.round(bytes/1024)+" KB";
    return bytes+" B";
  }catch(e){ return ""; }
}
// Attach a small "WxH · size" label under a freshly generated image. Reads the
// image's real natural dimensions once it loads. Call from the img onload.
function imgMetaLabel(imgEl, durl){
  try{
    const w=imgEl.naturalWidth||0, h=imgEl.naturalHeight||0;
    const size=durl?dataUrlSize(durl):"";
    const txt=(w&&h)?(w+"\u00d7"+h+" px"+(size?(" \u00b7 "+size):"")):(size||"");
    let cap=imgEl.parentElement&&imgEl.parentElement.querySelector(".imgmeta");
    if(!cap){ cap=document.createElement("div"); cap.className="imgmeta"; imgEl.insertAdjacentElement("afterend",cap); }
    cap.textContent=txt;
  }catch(e){}
}
function contentRow(label, sku, colKey, value, limit, opts){
  opts = opts||{};
  const cur=(value==null?"":String(value));
  const cid="cc_"+Math.random().toString(36).slice(2,8);
  const lim=limit||0;
  const useBytes = !!opts.bytes;
  const n = useBytes ? byteLen(cur) : cur.length;
  // soft warn threshold (e.g. title 75-char hard cap inside a 200 system max)
  const warnAt = opts.warnAt||0;
  const over = lim && n>lim;
  const warn = warnAt && n>warnAt && !over;
  const unit = useBytes ? " bytes" : " chars";
  const counter=`<span class="cc${over?' over':(warn?' warn':'')}" id="${cid}">${n}${lim?' / '+lim:''}${unit}</span>`;
  const idx = opts.indexNote ? `<span class="idxnote" title="${esc(opts.indexTip||'')}">${esc(opts.indexNote)}</span>` : "";
  const warnmsg = opts.warnMsg && (warn||over) ? `<div class="cwarn">⚠ ${esc(opts.warnMsg)}</div>` : "";
  const rows = opts.rows||3;
  const tgt = opts.target||"col";
  const ta=`<textarea class="ed" rows="${rows}" data-bkt="${esc(opts.bucket||'')}" data-bytes="${useBytes?1:0}" data-warn="${warnAt}" data-lim="${lim}" oninput="ccount(this,'${cid}',${lim});bulletMeter()" onchange="saveEdit(this,'${esc(sku)}','${tgt}','${esc(colKey)}')">${esc(cur)}</textarea>`;
  return `<tr><td colspan="2" class="wcell"><div class="wlab">${esc(label)} ${counter} ${idx}</div>${warnmsg}${ta}</td></tr>`;
}
function edRowReq(label,ctrl,hint){ return `<tr class="reqrow"><td class="k"><span class="klabel">${esc(label)}<span class="reqstar" title="Required by Amazon">\u2605</span></span> <span class="reqtag">needs value</span>${hint?`<span class="fixhint">\u26a0 ${esc(hint)}</span>`:""}</td><td class="v">${ctrl}</td></tr>`; }
function sid(s){ return String(s).replace(/[^a-zA-Z0-9]/g,"_"); }
function parseMissing(notes){
  // pull field names Amazon's preview flagged as "required but missing" (ground truth)
  if(!notes) return [];
  const out=[];
  String(notes).split(";").forEach(p=>{
    const m=p.match(/\[E\]\s+(\S+)\s+.*required but missing/i);
    if(m && m[1]) out.push(m[1]);
  });
  return out;
}
const AXIS_FIELD={width:"item_width",depth:"item_depth",height:"item_height",length:"item_length"};
// Plain-English, value-specific guidance shown UNDER the flagged field so the
// user knows exactly what to enter. Keyed by Amazon attribute name. Generic
// errors fall through to the phrasing matchers below; only known fields get a
// precise instruction here. Sub-field errors (e.g. hazmat.aspect) inherit the
// parent's hint, and the hazmat parent also carries the full instruction.
const SPECIFIC_HINT={
  hazmat:"Lithium battery item. Aspect = united_nations_regulatory_id, Value = UN3481 (battery packed in equipment).",
  contains_battery_or_cell:"App fills this automatically on Preview (Yes / true to match Amazon's list). You don't need to type here.",
  batteries_included:"Pick Yes / No from the list (not the word True).",
  batteries_required:"Pick Yes / No from the list (not the word True).",
  battery_installation_device_type:"For a LITHIUM battery, Amazon requires not_installed (installed_in_equipment is rejected for lithium). Other valid values: installed_in_vehicle, installed_in_vessel. The word Flashlight is NOT accepted.",
  wattage:"Enter a number AND pick the Wattage Unit (e.g. watts) — or remove wattage entirely.",
  warranty_description:"Type the warranty text, e.g. 1 Year Manufacturer Warranty.",
  special_feature:"Enter each feature as its own value (this is the singular field Amazon wants, not Special features).",
  model_name:"Enter the model name / number for this product.",
  supplier_declared_dg_hz_regulation:"Is this product hazardous/dangerous to ship? For a normal non-chemical, non-battery item (e.g. a hand tool) choose \u201cnot_applicable\u201d. Only pick a regulation (e.g. for lithium batteries or chemicals) if the product actually contains one.",
  lithium_battery_packaging:"Battery is inside the device — choose batteries_contained_in_equipment."
};
// Per-sub-field guidance for nested compliance attributes (key = "parent.subpath").
const SUBFIELD_HINT={
  "hazmat.aspect":"Choose united_nations_regulatory_id.",
  "hazmat.value":"Type UN3481 (lithium-ion battery packed with equipment).",
  "hazmat.united_nations_regulatory_id":"Type UN3481."
};
function parseFlagged(notes){
  // {field: hint} for every fixable attribute issue Amazon flagged in the last preview.
  // Maps composite dimension errors (item_depth_width_height) to the editable axis field.
  const out={};
  if(!notes) return out;
  String(notes).split(";").forEach(seg=>{
    const m=seg.match(/\[[EW]\]\s+([a-z][a-z0-9_]+)\s+([\s\S]*)/i);   // skips non-attribute "fields" like a bare barcode number
    if(!m) return;
    const field=m[1].toLowerCase(), msg=m[2];
    if(/required but missing/i.test(msg)){ if(!out[field]) out[field]="required"; return; }
    let mm=msg.match(/at least '([^']+)'\s+(\w+)\s+for '([^']+)'/i);
    if(mm){ out[AXIS_FIELD[mm[3].toLowerCase()]||field]="must be at least "+mm[1]+" "+mm[2]; return; }
    mm=msg.match(/at most '([^']+)'\s+(\w+)\s+for '([^']+)'/i);
    if(mm){ out[AXIS_FIELD[mm[3].toLowerCase()]||field]="must be at most "+mm[1]+" "+mm[2]; return; }
    mm=msg.match(/must be at least '([^']+)'\s*(\w+)?/i);
    if(mm){ out[field]="must be at least "+mm[1]+(mm[2]?(" "+mm[2]):""); return; }
    // SPECIFIC, ACTIONABLE HINT for the common compliance offenders, so the box
    // tells the user exactly WHAT to enter (not just "choose a value"). Overrides
    // the generic phrasing below. Falls through to generic/catch-all if unknown.
    if(SPECIFIC_HINT[field]){ out[field]=SPECIFIC_HINT[field]; return; }
    if(/not a valid value|approved value|select an approved/i.test(msg)){ out[field]="choose an allowed value"; return; }
    if(/does not have the expected value|expected value|unexpected value|invalid value|not.*expected/i.test(msg)){ out[field]="choose an allowed value"; return; }
    if(/less than the minimum|greater than the maximum|out of range/i.test(msg)){ out[field]="value out of allowed range"; return; }
    // CATCH-ALL: any other error Amazon flagged on a real attribute still gets a
    // visible box, so a field is NEVER silently dropped from the editor just
    // because its error phrasing is new. (This is what hid `hazmat` before.)
    if(!out[field]) out[field]="Amazon flagged this — review the value";
    return;
  });
  return out;
}
function addField(sku, pt, sel){
  const k=sel.value; if(!k) return;
  const sc=SCHEMAS[pt]||{opts:{}}; const opts=(sc.opts||{}); const subs=(sc.subs||{});
  const tb=document.getElementById("added_"+sid(sku));
  if(!tb){ sel.value=""; return; }
  if(tb.querySelector('tr[data-fk="'+k+'"]')){ sel.value=""; return; }
  const sf=subs[k];
  if(sf&&sf.length){
    const head=document.createElement("tr");
    head.setAttribute("data-fk",k); head.className="subhead";
    head.innerHTML='<td class="k" colspan="2"><b>'+k.replace(/_/g," ")+'</b></td>';
    tb.appendChild(head);
    sf.forEach(s=>{
      const full=k+"."+s.path;
      const tr=document.createElement("tr");
      tr.className='subrow';
      tr.innerHTML='<td class="k"><span class="subarrow">\u21b3</span> '+esc(_cleanLabel(s.label))+'</td><td class="v">'+editCell(sku,"attr",full,"",(s.enum&&s.enum.length?s.enum:null))+'</td>';
      tb.appendChild(tr);
    });
  }else{
    const tr=document.createElement("tr");
    tr.setAttribute("data-fk",k);
    tr.innerHTML='<td class="k">'+k.replace(/_/g," ")+'</td><td class="v">'+editCell(sku,"attr",k,"",opts[k]||null)+'</td>';
    tb.appendChild(tr);
  }
  for(let i=sel.options.length-1;i>=0;i--){ if(sel.options[i].value===k) sel.remove(i); }
  sel.value="";
}
const COLMAP={"Title":"title","Description (HTML)":"description","Search Terms / KW":"search_terms",
  "Our Price (GBP)":"price","Brand":"brand","UPC":"barcode","Handling Days":"handling_days","Product Type":"product_type"};
function updateLocalCol(r,key,value){
  if(key in COLMAP){ r[COLMAP[key]]=value; return; }
  const m=key.match(/^Bullet (\d)$/); if(m){ r.bullets=r.bullets||[]; r.bullets[+m[1]-1]=value; }
}
async function saveEdit(el,sku,target,key){
  const value=el.value; el.classList.remove("saved","err"); el.classList.add("saving");
  try{
    const res=await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku,target,key,value})});
    const j=await res.json(); el.classList.remove("saving");
    if(j.ok){ el.classList.add("saved"); toast("Saved ✓"); setTimeout(()=>el.classList.remove("saved"),1000);
      const r=ROWS.find(x=>x.sku===sku);
      if(r){ if(target==="attr"){ r.attributes=r.attributes||{};
               if(String(value).trim()==="") delete r.attributes[key]; else r.attributes[key]=value; }
             else updateLocalCol(r,key,value); }
    } else { el.classList.add("err"); toast("Save failed: "+(j.error||"")); }
  }catch(e){ el.classList.remove("saving"); el.classList.add("err"); toast("Save failed: "+e); }
}
// Schema-state diagnostic strip. The #1 reason flagged boxes render without
// dropdowns (or look "empty/shrunk") is that the LIVE Amazon schema for this
// product type failed to load in the browser -- so enums is empty and every
// field falls back to a plain text box. This makes that state visible and gives
// a one-click reload, instead of silently looking broken.
function schemaDiag(pt, nEnum, nAttrs, nSubs, missing, flagged, a){
  if(!pt) return "";
  const loaded = !!(SCHEMAS[pt] && (SCHEMAS[pt].attrs||[]).length);
  const flaggedKeys=Object.keys(flagged||{});
  const SS=(SCHEMAS[pt]||{});
  const hasList=(k)=>{
    if(SS.opts && SS.opts[k] && SS.opts[k].length) return true;        // top-level dropdown
    const sf=(SS.subs||{})[k];                                          // nested: any sub-field with a list
    if(sf && sf.some(s=>s.enum && s.enum.length)) return true;
    return false;
  };
  const noDropdown=flaggedKeys.filter(k=>!hasList(k));
  if(loaded && nEnum>0){
    // healthy: schema loaded with enums. Tiny unobtrusive confirmation.
    let note="";
    if(flaggedKeys.length && noDropdown.length){
      note=`<div style="font-size:11px;color:#c9a227;margin-top:4px">${noDropdown.length} flagged field(s) have no preset list from Amazon (${noDropdown.map(esc).join(", ")}) — these are free-text: type the value Amazon expects.</div>`;
    }
    return `<div class="schemadiag ok">Amazon schema loaded for <b>${esc(pt)}</b> · ${nEnum} field(s) with dropdown values, ${nAttrs} total, ${nSubs} nested.${note}</div>`;
  }
  // unhealthy: schema not loaded / empty -> THIS is why boxes look broken
  return `<div class="schemadiag bad">
    <b>⚠ Amazon's value lists for “${esc(pt)}” haven't loaded in this view.</b>
    That's why flagged fields show as plain boxes without dropdowns. The listing data is still editable, but the allowed-value menus are missing.
    <div style="margin-top:6px">
      <button class="ghost" onclick="reloadSchemaNow('${esc(pt)}')"><i class="ti ti-refresh"></i> Reload Amazon values now</button>
      <button class="ghost" onclick="dumpSchemaState('${esc(pt)}')"><i class="ti ti-bug"></i> Show what loaded</button>
    </div>
    <div id="schemadump_${sid(pt)}" style="font-size:11px;color:#9bb;margin-top:6px;white-space:pre-wrap"></div>
  </div>`;
}
async function reloadSchemaNow(pt){
  toast("Reloading Amazon values for "+pt+"…");
  try{
    var _r = DRAWER_SKU ? ROWS.find(x=>String(x.sku)===String(DRAWER_SKU)) : null;
    var _mkt = _r ? rowMkt(_r) : WS_MARKET;
    if(typeof loadSchemas==="function"){ await loadSchemas([pt], true, _mkt); }
    if(DRAWER_SKU){ const fr=ROWS.find(x=>String(x.product_type)===String(pt)&&String(x.sku)===String(DRAWER_SKU)) || ROWS.find(x=>String(x.sku)===String(DRAWER_SKU)); const host=document.getElementById("fulldata_"+sid(DRAWER_SKU)); if(host&&fr){ host.innerHTML=fullData(fr); } }
    const s=SCHEMAS[pt]||{};
    const n=(s.opts?Object.keys(s.opts).length:0);
    toast(n>0?("Loaded "+n+" value lists ✓"):"Still empty — Amazon schema call returned nothing. Check the app's terminal for an SP-API error.");
  }catch(e){ toast("Reload failed: "+(e&&e.message||e)); }
}
async function dumpSchemaState(pt){
  const el=document.getElementById("schemadump_"+sid(pt));
  var _r = DRAWER_SKU ? ROWS.find(x=>String(x.sku)===String(DRAWER_SKU)) : null;
  var _mkt = _r ? rowMkt(_r) : WS_MARKET;
  let txt="listing marketplace: "+(_mkt||"(none)")+"\nclient SCHEMAS["+pt+"]: ";
  const s=SCHEMAS[pt];
  if(!s){ txt+="NOT LOADED\n"; } else {
    txt+= (s.attrs||[]).length+" attrs, "+(s.opts?Object.keys(s.opts).length:0)+" enums, "+(s.subs?Object.keys(s.subs).length:0)+" nested\n";
  }
  // also ask the server directly so we can compare
  try{
    const j=await (await fetch("/schema/"+encodeURIComponent(pt)+"?refresh=1"+(_mkt?("&mkt="+encodeURIComponent(_mkt)):""))).json();
    if(j.ok){ txt+="server /schema ("+(j.marketplace||"?")+"): "+(j.attrs||[]).length+" attrs, "+Object.keys(j.enums||{}).length+" enums, "+Object.keys(j.subfields||{}).length+" nested\n";
      txt+="enum fields: "+Object.keys(j.enums||{}).slice(0,30).join(", ");
    } else { txt+="server /schema ERROR: "+(j.error||"unknown")+"\n"; }
  }catch(e){ txt+="server /schema fetch failed: "+(e&&e.message||e); }
  if(el) el.textContent=txt;
}
function fullData(r){
  try{
    return _fullDataInner(r);
  }catch(err){
    // Never let a render error silently collapse the drawer into empty boxes.
    // Show what failed so it can be fixed instead of guessed at.
    return `<details open><summary>Full listing data</summary>
      <div style="background:#3a1212;border:1px solid #6b2222;border-radius:8px;padding:12px;margin:8px 0">
        <b style="color:#ff8a8a">This listing's detail view hit an error while rendering.</b>
        <div style="font-size:12px;color:#ffb3b3;margin-top:6px">${esc(String(err&&err.message||err))}</div>
        <div style="font-size:11px;color:#c98;margin-top:8px">The raw data is still below so you can read/edit it.</div>
        <pre class="raw" style="display:block;margin-top:8px">${esc(JSON.stringify(r,null,2))}</pre>
      </div></details>`;
  }
}
function _fullDataInner(r){
  const sku=r.sku;
  const sc=SCHEMAS[r.product_type]||{opts:{},req:[],attrs:[],subs:{},titles:{}};
  const enums=sc.opts||{}, reqList=sc.req||[], allAttrs=sc.attrs||[];
  const titles=sc.titles||{};
  // Amazon's REAL field label (matches Seller Central) -> falls back to prettified key
  const lbl=(k)=> titles[k] || _cleanLabel(String(k));
  const idRows=[
    edRow("Product type", productTypeCell(sku, r), "Amazon-assigned from the catalogue. Changing it can cause rejection."),
    edRow("SKU", roCell(r.sku)),
    edRow("Brand", editCell(sku,"col","Brand",r.brand), null, (rowProvenance(r)||{}).brand),
    edRow("Condition", roCell("New")),
    edRow("Category", roCell((r.category||r.amazon_category||"")+(r.subcategory?(" › "+r.subcategory):""))),
    edRow("Browse node(s)", roCell((r.attributes||{}).recommended_browse_nodes||(r.attributes||{}).browse_node||"—")),
    edRow("Barcode / GTIN", editCell(sku,"col","UPC",r.barcode)),
    (function(){
       // Currency follows the ACTIVE workspace marketplace (reliable), with a
       // per-row override if the row itself carries a marketplace.
       var rowMkt = String(r._marketplace||(r.attributes||{}).marketplace||"").toUpperCase();
       var mkt = rowMkt || String(WS_MARKET||"").toUpperCase() || "UK";
       var cur = (mkt==="US"||mkt==="CA"||mkt==="MX") ? "$"
               : (mkt==="EU"||["DE","FR","IT","ES","NL"].indexOf(mkt)>=0) ? "\u20ac" : "\u00a3";
       var raw=String(r.price==null?"":r.price);
       var num=raw.replace(/[^0-9.\-]/g,"");            // strip any currency -> number only
       return edRow("Price ("+cur+")", '<span class="curlbl">'+cur+'</span>'+editCell(sku,"col","Our Price (GBP)",num));
    })(),
    edRow("List price", roCell((function(){var lp=(r.attributes||{}).list_price; return lp?String(lp).replace(/[^0-9.\-]/g,"")||"—":"—";})())),
    edRow("Quantity — blank = default 10", editCell(sku,"attr","fulfillment_quantity",(r.attributes||{}).fulfillment_quantity||"")),
    (function(){
       var rowMkt = String(r._marketplace||(r.attributes||{}).marketplace||"").toUpperCase();
       var mkt = rowMkt || String(WS_MARKET||"").toUpperCase() || "UK";
       var cur = (mkt==="US"||mkt==="CA"||mkt==="MX") ? "$"
               : (mkt==="EU"||["DE","FR","IT","ES","NL"].indexOf(mkt)>=0) ? "\u20ac" : "\u00a3";
       var pnum=String(r.profit==null?"":r.profit).replace(/[^0-9.\-]/g,"");
       return edRow("Profit ("+cur+")", roCell(pnum?(cur+pnum):"—"));
    })(),
    edRow("Handling days", editCell(sku,"col","Handling Days",r.handling_days)),
    edRow("Shipping group", roCell(SHIP)),
  ].join("");
  const a=r.attributes||{};
  const IMGRE=/^(main_product_image_locator|other_product_image_locator_\d+)$/;
  const imgUrls=Object.keys(a).filter(k=>IMGRE.test(k)).sort().map(k=>a[k]).filter(Boolean);
  const HIDEKEYS=new Set([...Object.keys(a).filter(k=>IMGRE.test(k)),"fulfillment_quantity"]);
  const _AHIDE=new Set(["_provenance","provenance"]); const aKeys=Object.keys(a).filter(k=>!HIDEKEYS.has(k));
  // fields the script fills itself (structural / identity / dimensions) -- never shown as needs-value
  const EXCLUDE_REQ=new Set(["item_name","bullet_point","product_description","generic_keyword","purchasable_offer","fulfillment_availability","brand","condition_type","merchant_shipping_group","supplier_declared_has_product_identifier_exemption","externally_assigned_product_identifier","list_price","manufacturer","model_number","part_number","item_dimensions","item_package_dimensions","item_depth_width_height","item_length_width_height","website_shipping_weight","recommended_browse_nodes","browse_node","browse_nodes"]);
  // required-but-missing = schema top-level required UNION the fields Amazon's last preview flagged
  const flagged=parseFlagged(r.notes);   // {field: hint} from Amazon's last preview (required / min-max / invalid)
  const flaggedKeys=Object.keys(flagged);
  const reqUnion=new Set([...(reqList||[]), ...flaggedKeys]);
  // A field Amazon EXPLICITLY flagged must ALWAYS show a box, even if it's in
  // EXCLUDE_REQ (our "script fills it" assumption) -- Amazon is overriding us.
  // Only EXCLUDE_REQ filters the schema-required list, never the flagged list.
  const missing=[...reqUnion].filter(k=>{
    if(!k) return false;
    if(k in a) return false;                       // already has a value
    if(flagged[k]) return true;                    // Amazon flagged it -> ALWAYS show
    if(EXCLUDE_REQ.has(k)) return false;           // script fills it (and not flagged)
    if(k.endsWith("_image_locator")) return false; // images optional
    return true;
  }).sort();
  const _prov=rowProvenance(r);
  const subs=sc.subs||{};
  // FALLBACK nested structure: when the live schema didn't load, sc.subs is empty
  // and nested fields would collapse to flat boxes (losing the structure AND the
  // "filling this requires its sub-fields" note). Rebuild the nesting from (a) any
  // dotted keys already in the data (e.g. "battery.cell_composition") and (b) a
  // known map of common Amazon nested fields. This makes the structure + note show
  // ALL the time, regardless of whether Amazon's value lists loaded this view.
  const KNOWN_NESTED={
    battery:["cell_composition","average_life","weight","charge_time","capacity"],
    hazmat:["aspect","value"],
    wattage:["value","unit"],
    unit_count:["value","type"],
    item_length:["value","unit"],
    item_width:["value","unit"],
    item_height:["value","unit"],
    item_weight:["value","unit"],
    package_weight:["value","unit"],
    voltage:["value","unit"],
    item_dimensions:["length","width","height"],
    supplier_declared_dg_hz_regulation:["value"]
  };
  function _fallbackSubs(){
    const out={};
    // (a) from dotted keys in the data
    Object.keys(a).forEach(function(key){
      const dot=key.indexOf(".");
      if(dot>0){
        const parent=key.slice(0,dot), child=key.slice(dot+1);
        if(!out[parent]) out[parent]=[];
        if(!out[parent].some(s=>s.path===child)) out[parent].push({path:child,label:child.replace(/_/g," "),enum:null});
      }
    });
    // (b) from the known map -- only add a parent that the data/attrs actually reference
    Object.keys(KNOWN_NESTED).forEach(function(parent){
      const referenced = (parent in a) || aKeys.indexOf(parent)>=0 ||
                         Object.keys(a).some(k=>k.indexOf(parent+".")===0) ||
                         (reqList||[]).indexOf(parent)>=0;
      if(referenced && !out[parent]){
        out[parent]=KNOWN_NESTED[parent].map(c=>({path:c,label:c.replace(/_/g," "),enum:null}));
      }
    });
    return out;
  }
  const fbSubs=_fallbackSubs();
  // merged view: prefer the real schema subs; fall back to reconstructed ones
  const subsView=Object.assign({}, fbSubs, subs);
  // Render ONE attribute. If schema says it's a nested object (battery,
  // maximum_speed, item_dimensions, ...), expand into its real sub-field boxes;
  // each sub-field saves flat as "<field>.<path>".
  const renderAttr=(k,isMissing)=>{
    const sf=subsView[k];
    // A field is "required" for star purposes if the schema lists it OR Amazon's
    // preview flagged it (conditionally required, e.g. hazmat on a battery item).
    const _schemaReq = (reqList||[]).indexOf(k)>=0;
    const isReqParent = _schemaReq || !!isMissing;
    // HONESTY: the schema's static required list is broader than what Amazon's
    // live validation actually enforces. If a clean Preview already ran for this
    // listing (status API_READY / "PREVIEW clean") and did NOT flag this field,
    // then a hard red "Required" star is misleading -- Amazon accepted it without
    // it. Show a SOFTER marker in that case so the user isn't sent chasing a
    // field Amazon didn't ask for (e.g. dangerous goods on a manual tool).
    const _cleanPrev = (String(r.status||"").toUpperCase()==="API_READY")
                       || /PREVIEW clean/i.test(String(r.notes||""));
    const _amazonFlagged = !!isMissing || !!flagged[k];
    const _schemaOnly = _schemaReq && !_amazonFlagged && _cleanPrev;
    const reqMark = _amazonFlagged
      ? '<span class="reqstar" title="Amazon flagged this in Preview — it must be filled">\u2605</span>'
      : (_schemaOnly
          ? '<span class="reqsoft" title="The schema lists this as required, but Amazon\u2019s last Preview accepted the listing WITHOUT it. Fill it only if a later Preview flags it.">\u2606 schema-listed</span>'
          : (isReqParent ? '<span class="reqstar" title="Required by Amazon">\u2605</span>' : ''));
    if(sf&&sf.length){
      // Specific parent instruction (e.g. hazmat) shown right on the group header
      // so the user sees WHAT to enter at the field, not just in the top red box.
      const headHint = isMissing ? (SPECIFIC_HINT[k] || "fill the sub-fields below") : null;
      // ALWAYS-ON guidance for multi-level (nested) fields: a parent like this is
      // usually optional, BUT the moment you put a value in it, Amazon makes its
      // sub-fields required -- leaving any blank then throws an error. This note
      // prevents the "why did filling one box create new errors?" surprise.
      const nestNote = isReqParent
        ? ""   // already required -> the star + headHint already say to fill it
        : `<span class="nesthint" title="This field is optional. But if you enter a value here, Amazon will require ALL its sub-fields below to be filled too — otherwise it errors. Leave the whole group blank if you don't need it.">\u2139 optional — but filling this makes its sub-fields required</span>`;
      const head=`<tr class="subhead${isMissing?' flaggedrow':''}"><td class="k" colspan="2"><b>${esc(lbl(k))}</b>${reqMark}${headHint?` <span class="fixhint">\u26a0 ${esc(headHint)}</span>`:''}${nestNote}</td></tr>`;
      const rows=sf.map(s=>{
        const full=k+"."+s.path;                 // flat dot-key in Attributes JSON
        const val=(full in a)?a[full]:"";
        const sHasEnum=!!(s.enum&&s.enum.length);
        // Per-sub-field guidance for the known compliance fields.
        const subKey=(k+"."+s.path).toLowerCase();
        let sHint = isMissing ? (sHasEnum?"choose an allowed value":"type the value Amazon expects") : null;
        if(isMissing && SUBFIELD_HINT[subKey]) sHint = SUBFIELD_HINT[subKey];
        return edRow(titles[full]||s.label, editCell(sku,"attr",full,val,(sHasEnum?s.enum:null)), sHint, _prov&&_prov[full], true);
      }).join("");
      return head+rows;
    }
    const isReq = ((reqList||[]).indexOf(k)>=0) || !!isMissing;
    // same honesty rule as the nested head: a schema-required field that a clean
    // Preview didn't flag shows a soft marker, not a hard "required" star.
    const _flatAmazonFlagged = !!isMissing || !!flagged[k];
    const _flatSchemaOnly = ((reqList||[]).indexOf(k)>=0) && !_flatAmazonFlagged && _cleanPrev;
    // Accurate hint: if Amazon gives an allowed-value list -> dropdown ("choose
    // a value"); if not -> free text, so tell the user to type what Amazon wants
    // rather than showing the misleading "choose an allowed value".
    const hasEnum = !!(enums[k] && enums[k].length);
    const baseHint = flagged[k] || "";
    const missHint = hasEnum
      ? (baseHint || "choose an allowed value")
      : (/required/i.test(baseHint) ? "required — type the value Amazon expects"
                                    : "type the value Amazon expects (free text)");
    return isMissing
      ? edRowReq(lbl(k), editCell(sku,"attr",k,"",enums[k]||null), missHint)
      : edRow(lbl(k), editCell(sku,"attr",k,a[k],enums[k]||null), flagged[k], _prov&&_prov[k], false, isReq, _flatSchemaOnly);
  };
  // skip flat dot-keys that belong to a nested group (rendered under their head)
  const isSubKey=k=>k.includes(".")&&subsView[k.split(".")[0]];
  // parents whose sub-values are already filled (so head + sub-rows still show)
  const filledParents=[...new Set(aKeys.filter(isSubKey).map(k=>k.split(".")[0]))]
      .filter(p=>!aKeys.includes(p)&&!missing.includes(p));
  const presentTop=aKeys.filter(k=>!_AHIDE.has(k)&&!isSubKey(k));
  const attrRows=presentTop.map(k=>renderAttr(k,false)).join("")
    + filledParents.map(k=>renderAttr(k,false)).join("")
    + missing.map(k=>renderAttr(k,true)).join("");
  // every other schema field the user MAY fill (optional) -> add-on demand picker
  const addable=allAttrs.filter(k=>!(k in a) && !missing.includes(k) && !EXCLUDE_REQ.has(k) && !k.endsWith("_image_locator")).sort();
  const sidv=sid(sku);
  const addCtrl = addable.length ? `<div class="addfield">
      <select onchange="addField('${esc(sku)}','${esc(r.product_type)}',this)">
        <option value="">+ add another field (${addable.length} optional available)…</option>
        ${addable.map(k=>`<option value="${esc(k)}">${esc(lbl(k))}</option>`).join("")}
      </select>
      <table class="kv" id="added_${sidv}"></table>
      <div class="hint">Pick any field to add and fill — saves automatically.</div>
    </div>` : "";
  // ---- CONTENT FIELDS with 2026 limits + indexing depth indicators ----------
  // Title: 200 system max, but a 75-char HARD CAP lands Jul 27 2026 (all cats
  //        except media). Mobile truncates ~70. Fully indexed, highest weight.
  // Bullets: 500 each, but only the first ~1,000 BYTES across all 5 COMBINED are
  //          indexed -> a shared byte meter sits above the bullets.
  // Description: 2,000 incl HTML, indexed but LOWEST weight of visible fields.
  // Item Highlights: 125, new structured field, own A10 weight.
  // Backend search terms: 249 BYTES (not chars); one byte over de-indexes ALL.
  const titleOpts={ warnAt:75, warnMsg:"Amazon's 75-char hard cap applies from 27 Jul 2026 (all categories except media). Front-load the first ~70 chars — mobile truncates there.", indexNote:"fully indexed · highest weight", indexTip:"Title carries the most A10 search weight. Mobile shows ~70-80 chars, so put the most important words first." };
  const bulletOptsFor=(i)=>({ bucket:"bullet"+i, indexNote:(i===1?"first 1,000 bytes (all 5 combined) indexed":""), indexTip:"Amazon indexes only the first ~1,000 bytes across ALL five bullets combined — not per bullet. See the meter above." });
  const descOpts={ indexNote:"indexed · lowest weight", indexTip:"The description is indexed but weighted lowest of the visible fields. Won't save past 2,000 chars (HTML included)." };
  const highlightOpts={ target:"attr", indexNote:"indexed · own weight", indexTip:"Item Highlights is a structured field shown with the title in search and on the PDP. Carries its own A10 weight (2026)." };
  const backendOpts={ bytes:true, warnAt:249, warnMsg:"Backend search terms are measured in BYTES. One byte over 249 silently de-indexes the ENTIRE field — keep it at or under 249.", indexNote:"249-byte cap · de-index risk", indexTip:"Counted in bytes, not characters. Going one byte over 249 removes the whole field from search." };
  const bulletMeterRow = `<tr><td colspan="2" class="wcell"><div id="bulletIdxMeter" class="bulletmeter"></div></td></tr>`;
  const itemHi = (r.attributes||{}).item_type_keyword===undefined ? "" : "";
  const _highlightVal = (function(){ try{ return (r.attributes||{}).item_highlights || r.item_highlights || ""; }catch(e){ return ""; } })();
  const cRows=[
      contentRow("Backend search terms", sku, "Search Terms / KW", r.search_terms, 249, backendOpts),
      contentRow("Title", sku, "Title", r.title, 200, titleOpts),
      contentRow("Item Highlights", sku, "item_highlights", _highlightVal, 125, highlightOpts)
    ]
    .concat([bulletMeterRow])
    .concat((r.bullets||[]).map((b,i)=>contentRow("Bullet "+(i+1), sku, "Bullet "+(i+1), b, 500, bulletOptsFor(i+1))))
    .concat([contentRow("Description", sku, "Description (HTML)", r.description, 2000, descOpts)]).join("");
  const rid="raw_"+Math.random().toString(36).slice(2,8);
  const nEnum=Object.keys(enums).length;
  const hasAttrs=aKeys.length||missing.length;
  const nFix=missing.length + Object.keys(flagged).filter(k=>k in a).length;
  const attrHdr=nFix?` — ${nFix} field(s) flagged by Amazon — fix the highlighted ones`:(hasAttrs?'':' — none yet');
  const st=(r.status||"").toUpperCase();
  const reqNote = missing.length
    ? `<div class="reqnote">Amazon reveals required fields in <b>stages</b> — fill the highlighted box(es) above, then click <b>Preview (API)</b> again. More required fields may appear after each Preview; repeat until Preview reports no errors.</div>`
    : (["API_READY","API_ERROR","LIVE"].includes(st) ? ""
        : `<div class="reqnote">Required fields are revealed by Amazon's validation, not upfront. Click <b>Preview (API)</b> to check this row — any required fields will appear here as highlighted boxes.</div>`);
  const rememberBtn = (aKeys.length||missing.length)
    ? `<button class="rememberbtn" onclick="saveDefault('${esc(sku)}','${esc(r.product_type)}',this)">★ Remember these as defaults for all ${esc(r.product_type||"this type")} listings</button>`
    : "";
  const isBrandRow = !r.asin || (r.sku && /^[A-Za-z]/.test(String(r.sku)) && !/_\d+Days_/.test(String(r.sku)));
  const imgLabel = isBrandRow ? "Images — from brand catalogue" : "Images — from competitor (eBay priority)";
  const _mainIsLocal = imgUrls.length && !/^https?:\/\//i.test(String(imgUrls[0]||""));
  const _imgWarn = _mainIsLocal
    ? `<div class="hint" style="color:#e3b768;margin-top:4px">⚠ The main image is a LOCAL file Amazon can't fetch — it will block submission. Remove it (submit without an image) or set a public https URL.</div>`
    : "";
  const _imgActions = imgUrls.length
    ? `<div style="margin-top:6px;display:flex;gap:8px">
         <button class="suggestbtn" style="background:#2a1414;border-color:#5c2424;color:#ff8a8a" onclick="clearMainImage('${esc(sku)}')" title="Remove the main image URL so the listing can be created without an image (add one later in Seller Central)"><i class="ti ti-photo-off"></i> Remove main image</button>
       </div>`
    : "";
  const imgBlock = (imgUrls.length
    ? `<div class="kvsec">${imgLabel}</div><div class="imgrow">${imgUrls.map((u,i)=>`<div class="thumbwrap"><a href="${esc(u)}" target="_blank" title="${i===0?'MAIN image':'additional #'+i}"><img class="thumb" src="${esc(u)}" loading="lazy"><span class="thumbcap">${i===0?'main':'#'+i}</span></a><button class="thumbedit" title="Edit this image (AI changes only what you ask)" onclick="editListingImage('${esc(sku)}','${esc(u)}',${i})"><i class="ti ti-wand"></i></button></div>`).join("")}</div>${_imgWarn}${_imgActions}`
    : `<div class="kvsec">Images</div><div class="hint">No image captured for this row.</div>`)
    + `<div class="genimg" id="genimg_${sidv}">
        <div class="kvsec" style="color:#c8b6ff;margin-top:12px"><i class="ti ti-sparkles"></i> AI image generation</div>
        <div class="genpanel" id="genpanel_${sidv}" style="display:block">
          <div class="gendiag" id="gendiag_${sidv}">Checking OpenRouter connection…</div>
          <div class="genrow">
            <span class="cc">Reference image:</span>
            <input class="ed geninput" id="genraw_${sidv}" style="flex:1"
                   value="${esc(imgUrls[0]||'')}"
                   placeholder="${isBrandRow?'brand/product image URL':'eBay source image (auto)'}">
            <label class="uploadbtn" title="Upload a reference image from your computer">
              <i class="ti ti-upload"></i> Upload
              <input type="file" accept="image/*" style="display:none" onchange="uploadRef(this,'${esc(sku)}','${sidv}')">
            </label>
          </div>
          ${isBrandRow?`<label class="cc"><input type="checkbox" id="genusebrand_${sidv}"> use brand-saved reference image instead</label>`:''}
          <textarea class="ed geninput" id="genbrief_${sidv}" rows="2"
            placeholder="Your command: how should the image look? e.g. 'premium studio shot, soft shadow, blue mirror lens variant'"></textarea>
          <div class="genrow">
            <span class="cc">Prompt AI:</span>
            <select class="ed" id="gentai_${sidv}" style="width:auto"></select>
            <span class="cc">Image AI:</span>
            <select class="ed" id="geniai_${sidv}" style="width:auto"></select>
            <a class="browsemodels sm" href="https://openrouter.ai/models?output_modalities=image" target="_blank" rel="noopener" title="See all image models on OpenRouter"><i class="ti ti-external-link"></i> all image models</a>
          </div>
          <div class="genrow">
            <button class="genimgbtn" id="genbtn_${sidv}" onclick="doGen('${esc(sku)}','${sidv}')">Generate</button>
            <span class="cc" id="genstatus_${sidv}"></span>
          </div>
          <details id="genpromptwrap_${sidv}" style="display:none"><summary class="cc">view detailed prompt the AI wrote</summary><pre class="genprompt" id="genprompt_${sidv}"></pre></details>
          <div id="genresult_${sidv}"></div>
        </div>
      </div>`
      + ((window.WS_FEATURES&&window.WS_FEATURES.indexOf('harvest')>=0)
         ? milesTemplatePanel(sku, sidv) : "");
  // COMPLETE submission view: every attribute key, no exclusions, read-only,
  // so the user sees everything that will be sent to Amazon (browse nodes,
  // dimensions, compliance flags, image locators, prices -- the lot).
  const allSubKeys=Object.keys(a).filter(k=>k!=="_provenance"&&k!=="provenance").sort();
  const fmtVal=v=>{ if(v==null) return ""; if(typeof v==="object") return esc(JSON.stringify(v)); return esc(String(v)); };
  const fullSubRows=allSubKeys.map(k=>`<tr><td class="k">${esc(k.replace(/_/g," "))}</td><td class="v"><span class="ro">${fmtVal(a[k])}</span></td></tr>`).join("");
  const fullSubBlock=allSubKeys.length
    ? `<details class="suball"><summary class="kvsec" style="cursor:pointer">Complete submission data — everything sent to Amazon (${allSubKeys.length} fields, read-only)</summary>
        <table class="kv">${fullSubRows}</table></details>`
    : "";
  return `<details open><summary>Full listing data — click any value to edit; saves automatically${nEnum?'. Dropdowns = Amazon allowed values':''}</summary>
    ${imgBlock}
    <div class="kvsec">Identity &amp; offer</div><table class="kv">${idRows}</table>
    <div class="kvsec">Attributes${attrHdr}</div>${schemaDiag(r.product_type, nEnum, allAttrs.length, Object.keys(subs).length, missing, flagged, a)}${(typeof howWorks==="function")?howWorks('required_fields'):""}${hasAttrs?`<table class="kv">${attrRows}</table>`:''}${reqNote}${addCtrl}${rememberBtn}
    <div class="kvsec">Content</div>${(typeof howWorks==="function")?howWorks('content_index'):""}<table class="kv">${cRows}</table>
    ${fullSubBlock}
    <span class="rawtoggle" onclick="var e=document.getElementById('${rid}');e.style.display=(e.style.display==='block'?'none':'block')">show / hide raw JSON</span>
    <pre class="raw" id="${rid}">${esc(JSON.stringify(a,null,2))}</pre>
    ${ (window.SHOW_PAYLOAD_VIEWER===true && r.api_payload && String(r.api_payload).trim())
       ? `<details class="payloadbox"><summary class="kvsec" style="cursor:pointer">\ud83d\udce6 Exact payload sent to Amazon (literal API body from last Preview/Submit, read-only)</summary>
            <div class="payloadnote">This is the verbatim JSON the app sent to Amazon on the last Preview or Submit for this SKU — every word, exactly as transmitted. It does not affect anything; it is for visibility only. You can hide this section in Settings.</div>
            <pre class="raw payloadraw" id="pl_${sidv}">${esc(String(r.api_payload))}</pre>
            <button class="linkbtn" onclick="navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('pl_${sidv}').textContent);toast&&toast('Payload copied')">Copy payload</button>
          </details>`
       : "" }
  </details>`;
}
var AISET=null;
async function loadAISettings(){
  if(AISET) return AISET;
  try{ AISET=await (await fetch('/ai/settings')).json(); }catch(e){ AISET={ok:false}; }
  if(AISET&&AISET.admin){ window.LOGIC_VISIBLE = !!AISET.admin.show_logic && !AISET.admin.preview_as_user; }
  return AISET;
}
function fillModelSelect(sel, models, chosen){
  if(!sel) return;
  sel.innerHTML=(models||[]).map(function(m){
    return '<option value="'+esc(m.id)+'"'+(m.id===chosen?' selected':'')+'>'+esc(m.name||m.id)+'</option>';
  }).join('');
}
async function toggleGen(sidv){
  var p=document.getElementById('genpanel_'+sidv);
  if(p) p.style.display = (p.style.display==='none'?'block':'none');
  var s=await loadAISettings();
  if(!s || !s.ok || !(s.image_models && s.image_models.length)){
    try{ AISET=null; s=await (await fetch('/ai/settings?refresh=1')).json(); AISET=s; }catch(e){}
  }
  if(s&&s.ok){
    fillModelSelect(document.getElementById('gentai_'+sidv), s.text_models, s.select.prompt_enhance);
    fillModelSelect(document.getElementById('geniai_'+sidv), s.image_models, s.select.image_generate);
  }
  // quick connectivity check so the user knows BEFORE generating whether the key works
  var diag=document.getElementById('gendiag_'+sidv);
  if(diag && p && p.style.display!=='none'){
    await _orTestInto(diag);
  }
}
async function doGen(sku, sidv){
  var r=ROWS.find(x=>String(x.sku)===String(sku));
  var title=r?(r.title||''):'';
  var ref=(document.getElementById('genraw_'+sidv)||{}).value||'';
  var brief=(document.getElementById('genbrief_'+sidv)||{}).value||'';
  var tprov=(document.getElementById('gentai_'+sidv)||{}).value||'';
  var iprov=(document.getElementById('geniai_'+sidv)||{}).value||'';
  var useBrand=document.getElementById('genusebrand_'+sidv);
  if(useBrand&&useBrand.checked){ ref='__BRAND_REF__'; }
  var st=document.getElementById('genstatus_'+sidv);
  var btn=document.getElementById('genbtn_'+sidv);
  if(btn){ btn.disabled=true; btn.textContent='Generating…'; }
  if(st){ st.innerHTML='<span class="genspin"></span> Stage 1: writing prompt… then creating image. This can take 30\u201390s \u2014 please wait.'; }
  // elapsed-time ticker so the user sees it IS working
  var t0=Date.now();
  var ticker=setInterval(function(){
    if(st){ var s=Math.round((Date.now()-t0)/1000); var base=st.getAttribute('data-base')||'Working'; st.innerHTML='<span class="genspin"></span> '+base+' \u2014 '+s+'s elapsed'; }
  }, 1000);
  if(st) st.setAttribute('data-base','Generating image');
  try{
    var res=await fetch('/genimage',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brief:brief,reference_image:ref,title:title,text_provider:tprov,image_provider:iprov})});
    var j=await res.json();
    clearInterval(ticker);
    if(btn){ btn.disabled=false; btn.textContent='Generate'; }
    if(!j.ok){
      if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 Failed ('+(j.stage||'')+'): '+esc(j.error||'unknown')+'</span>';
      if(j.detailed_prompt){ var pw=document.getElementById('genpromptwrap_'+sidv); var pp=document.getElementById('genprompt_'+sidv); if(pw&&pp){pw.style.display='block'; pp.textContent=j.detailed_prompt;} }
      return;
    }
    if(st) st.innerHTML='<span style="color:#7fd99a">\u2713 Done ('+esc(j.text_provider||'')+' \u2192 '+esc(j.image_provider||'')+') \u2014 review below.</span>';
    var pw=document.getElementById('genpromptwrap_'+sidv); var pp=document.getElementById('genprompt_'+sidv);
    if(pw&&pp){ pw.style.display='block'; pp.textContent=j.detailed_prompt||''; }
    var out=document.getElementById('genresult_'+sidv);
    if(out){
      var _dimtxt=(j.width&&j.height)?(j.width+'×'+j.height+' px'):'';
      var _sztxt=(j.bytes)?_fmtBytes(j.bytes):'';
      var _meta=(_dimtxt||_sztxt)?('<div class="cc" style="margin:4px 0">'+esc([_dimtxt,_sztxt].filter(Boolean).join(' · '))+'</div>'):'';
      out.innerHTML='<div class="genpreview"><img src="'+j.data_url+'">'+_meta+
        '<div class="cc" id="gendrive_'+sidv+'" style="margin:2px 0;color:#86d0a8"></div>'+
        '<div class="genrow">'+
        '<button class="genimgbtn apply" onclick="applyGen(\''+esc(sku)+'\',\''+sidv+'\')">Use as main image</button>'+
        '<button class="genimgbtn" onclick="document.getElementById(\'genresult_'+sidv+'\').innerHTML=\'\'">Discard</button></div></div>';
      out.dataset.img=j.data_url;
    }
    // auto-save the generation into this SKU's media folder (builds the library)
    // AND auto-push to Drive (server does this for kind=generated), then show the link.
    try{
      var sv=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sku:sku,data:j.data_url,kind:'generated'})});
      var svj=await sv.json();
      if(svj.ok && out){
        out.dataset.savedurl=svj.url;
        var dr=document.getElementById('gendrive_'+sidv);
        if(dr){
          if(svj.drive_direct_url){
            dr.innerHTML='\u2713 Saved to Drive \u2014 <a href="'+esc(svj.drive_view_url||svj.drive_direct_url)+'" target="_blank">open</a> '+
              '<span class="cc" style="color:#8a93a6">(Amazon-ready link saved)</span>';
            out.dataset.driveurl=svj.drive_direct_url;
          } else {
            var _de = svj.drive_error ? (' Reason: '+esc(svj.drive_error)) : '';
            dr.innerHTML='<span class="cc" style="color:#e3b768">Saved locally, but NOT uploaded to Drive.'+_de+'</span>';
          }
        }
      }
    }catch(e){}
  }catch(e){
    clearInterval(ticker);
    if(btn){ btn.disabled=false; btn.textContent='Generate'; }
    if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 Error: '+esc(String(e))+'</span>';
  }
}
function uploadMainImage(sku, inp){
  // Upload a LOCAL image as this listing's main image. Chains two existing routes:
  //  1) /media/upload (kind:'main') -> saves + auto-pushes to Drive, returns a
  //     PUBLIC drive_direct_url Amazon can fetch.
  //  2) /edit -> writes that public URL onto the row's main_product_image_locator,
  //     so the next Preview/Submit sends YOUR clean image instead of the source one.
  const f = inp && inp.files && inp.files[0];
  if(!f){ return; }
  if(!/^image\//.test(f.type||"")){ toast("Please choose an image file"); inp.value=""; return; }
  const rd = new FileReader();
  rd.onload = async () => {
    toast("Uploading main image…");
    try{
      const up = await (await fetch("/media/upload",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, data:rd.result, name:f.name, kind:"main"})})).json();
      if(!up || !up.ok){ toast("Upload failed: "+((up&&up.error)||"unknown")); return; }
      const pub = up.drive_direct_url || "";
      if(!pub){ toast("Uploaded, but no public URL"+(up.drive_error?(" ("+up.drive_error+")"):"")+". Set the account's Drive folder so Amazon can fetch it."); return; }
      const sv = await (await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, target:"attr", key:"main_product_image_locator", value:pub})})).json();
      if(sv && sv.ok){ toast("Main image set ✓ — Preview/Submit to send it to Amazon"); loadRows(); }
      else { toast("Image hosted but couldn't save to the row: "+((sv&&sv.error)||"")); }
    }catch(e){ toast("Upload error: "+((e&&e.message)||e)); }
    finally { if(inp) inp.value=""; }
  };
  rd.readAsDataURL(f);
}
async function pushImageLive(sku, btn){
  var r=(ROWS||[]).find(x=>String(x.sku)===String(sku));
  if(!r){ toast('Listing not found'); return; }
  if(!confirm("Send the current main image to the LIVE Amazon listing for "+sku+"?\n\nThis updates ONLY the main image on Amazon (no full resubmit). Amazon must be able to fetch the image, so it will be uploaded to your Drive and made public if it isn't already.")) return;
  var old = btn?btn.textContent:'';
  if(btn){ btn.disabled=true; btn.textContent='Pushing…'; }
  try{
    var res=await fetch('/listing/push_image',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({confirmed:true, sku:sku,
        marketplace:(typeof WS_MARKET!=='undefined'?WS_MARKET:''),
        product_type:(r.product_type||''),
        id:(CUR_ACCOUNT&&CUR_ACCOUNT.id)||''})});
    var j=await res.json();
    if(j.ok){
      toast('✓ Image sent to Amazon ('+(j.status||'accepted')+'). Amazon takes a few minutes to show it.');
    } else {
      var extra = (j.issues&&j.issues.length)?(' — '+j.issues.map(function(i){return (i.message||i.code||'');}).join('; ')):'';
      toast('Could not push image: '+(j.error||'unknown')+extra);
    }
  }catch(e){ toast('Push failed: '+e); }
  finally{ if(btn){ btn.disabled=false; btn.textContent=old||'Push image to live'; } }
}
async function applyGen(sku, sidv){
  var out=document.getElementById('genresult_'+sidv);
  var dataUrl=out?out.dataset.img:'';
  if(!dataUrl){ toast('No generated image to apply'); return; }
  // prefer the saved file URL (real hosted path) over the inline data URL
  var savedUrl=out?out.dataset.savedurl:'';
  var useUrl=savedUrl||dataUrl;
  try{
    await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,target:'attr',key:'main_product_image_locator',value:useUrl})});
    toast(savedUrl?'Set as main image (saved to media)':'Set as main image');
    loadRows();
  }catch(e){ toast('Could not apply: '+e); }
}
// ===== Miles template main-image builder (overlay text on blank template) =====
let MILES_TPLS = null;
async function _loadMilesTpls(){
  if(MILES_TPLS) return MILES_TPLS;
  try{ var j=await (await fetch('/miles_template/list')).json(); MILES_TPLS=(j&&j.templates)||[]; }
  catch(e){ MILES_TPLS=[]; }
  return MILES_TPLS;
}
function milesTemplatePanel(sku, sidv){
  return `<div class="genimg" id="milestpl_${sidv}">
    <div class="kvsec" style="color:#7fd0ff;margin-top:14px"><i class="ti ti-stack"></i> Miles template main image</div>
    <div class="genpanel" style="display:block">
      <div class="cc" style="margin-bottom:6px">Overlay product text onto your blank Miles template — pixel-faithful, no AI. <a href="#" onclick="openMilesTplManager();return false" style="color:#9cc1ff">Manage templates</a></div>
      <div class="genrow">
        <span class="cc">Template:</span>
        <select class="ed" id="mtpl_${sidv}" style="flex:1" onfocus="refreshMilesDropdowns()"><option value="">— loading templates —</option></select>
      </div>
      <div class="genrow">
        <span class="cc">Title:</span>
        <input class="ed geninput" id="mtitle_${sidv}" style="flex:1" placeholder="VOLTAGE II">
      </div>
      <div class="cc" style="margin:6px 0 2px">Subtitle lines <button class="genimgbtn" style="padding:2px 8px" onclick="milesAddLine('${sidv}')">+ add line</button></div>
      <div id="msubs_${sidv}"></div>
      <div class="cc" style="margin:8px 0 2px;opacity:.7">CHOICE OF MECHANICS — fixed (always shown)</div>
      <div class="genrow">
        <span class="cc">Application:</span>
        <input class="ed geninput" id="mapp_${sidv}" style="flex:1" placeholder="HYDRAULIC FLUID">
        <label class="cc" style="white-space:nowrap"><input type="checkbox" id="mappL_${sidv}" checked> 2 lines</label>
      </div>
      <div class="genrow" style="margin-top:8px">
        <button class="genimgbtn apply" id="mbtn_${sidv}" onclick="milesRender('${esc(sku)}','${sidv}')">Generate template image</button>
        <button class="genimgbtn" id="maibtn_${sidv}" onclick="milesAiFill('${esc(sku)}','${sidv}')" title="Let AI fill the title, grade and application from the listing"><i class="ti ti-sparkles"></i> AI fill text</button>
        <span class="cc" id="mstatus_${sidv}"></span>
      </div>
      <div id="mresult_${sidv}"></div>
    </div>
  </div>`;
}
// populate the template dropdown + seed two subtitle lines when the drawer opens
async function initMilesPanel(sidv){
  var sel=document.getElementById('mtpl_'+sidv); if(!sel) return;
  var tpls=await _loadMilesTpls();
  sel.innerHTML = tpls.length
    ? tpls.map(t=>`<option value="${esc(t.id)}">${esc(t.label)} (${esc(t.container)})</option>`).join("")
    : '<option value="">no templates yet — click Manage templates to upload</option>';
  var box=document.getElementById('msubs_'+sidv);
  if(box && !box.children.length){ milesAddLine(sidv,'ELECTRICAL INSULATING'); milesAddLine(sidv,'OIL TYPE II INHIBITED'); }
}
function milesAddLine(sidv, val){
  var box=document.getElementById('msubs_'+sidv); if(!box) return;
  var i=box.children.length;
  var row=document.createElement('div'); row.className='genrow'; row.style.marginBottom='4px';
  row.innerHTML=`<input class="ed geninput msubin" style="flex:1" value="${esc(val||'')}" placeholder="subtitle line">
    <label class="cc" style="white-space:nowrap"><input type="checkbox" class="msub2" checked> 2 lines</label>
    <button class="genimgbtn" style="padding:2px 8px" onclick="this.parentNode.remove()">−</button>`;
  box.appendChild(row);
}
async function milesAiFill(sku, sidv){
  var r=ROWS.find(x=>String(x.sku)===String(sku));
  var st=document.getElementById('mstatus_'+sidv);
  var btn=document.getElementById('maibtn_'+sidv);
  if(btn) btn.disabled=true;
  if(st) st.innerHTML='<span class="genspin"></span> AI reading listing…';
  try{
    var body={ sku:sku,
      title:(r&&r.title)||'',
      bullets:(r&&(r.bullets||[]).join(' \u2022 '))||'',
      specs:(r&&(r.search_terms||''))||'' };
    var j=await (await fetch('/miles_template/ai_fill',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)})).json();
    if(btn) btn.disabled=false;
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 '+esc(j.error||'failed')+'</span>'; return; }
    var sp=j.spec||{};
    // fill title
    var t=document.getElementById('mtitle_'+sidv); if(t) t.value=(sp.title||'');
    // rebuild subtitle lines from the AI's grade
    var box=document.getElementById('msubs_'+sidv);
    if(box){ box.innerHTML=''; (sp.subtitles||[]).forEach(function(s){ milesAddLine(sidv, s.text); }); }
    // fill application
    var ap=document.getElementById('mapp_'+sidv); if(ap) ap.value=((sp.application||{}).text||'');
    var apL=document.getElementById('mappL_'+sidv); if(apL) apL.checked=(((sp.application||{}).lines||2)>=2);
    if(st) st.innerHTML='<span style="color:#7fd99a">\u2713 AI filled — review &amp; Generate</span>';
  }catch(e){ if(btn) btn.disabled=false; if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 '+esc(String(e))+'</span>'; }
}
async function milesRender(sku, sidv){
  var tid=(document.getElementById('mtpl_'+sidv)||{}).value||'';
  if(!tid){ toast('Upload/select a Miles template first'); return; }
  var title=(document.getElementById('mtitle_'+sidv)||{}).value||'';
  var subs=[...document.querySelectorAll('#msubs_'+sidv+' .genrow')].map(function(rw){
    var t=rw.querySelector('.msubin'); var c=rw.querySelector('.msub2');
    return {text:(t&&t.value)||'', lines:(c&&c.checked)?2:1};
  }).filter(s=>s.text.trim());
  var app=(document.getElementById('mapp_'+sidv)||{}).value||'';
  var appL=(document.getElementById('mappL_'+sidv)||{}).checked?2:1;
  var st=document.getElementById('mstatus_'+sidv);
  var btn=document.getElementById('mbtn_'+sidv);
  if(btn){ btn.disabled=true; }
  if(st){ st.innerHTML='<span class="genspin"></span> rendering…'; }
  try{
    var j=await (await fetch('/miles_template/render',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({template_id:tid, sku:sku, spec:{title:title, subtitles:subs, application:{text:app, lines:appL}}})})).json();
    if(btn){ btn.disabled=false; }
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#ef9a9a">✗ '+esc(j.error||'failed')+'</span>'; return; }
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ rendered</span>';
    var out=document.getElementById('mresult_'+sidv);
    if(out){
      out.dataset.savedurl=j.url||'';
      out.dataset.dataurl=j.data_url||'';
      out.innerHTML='<div class="genpreview"><img src="'+(j.data_url||j.url)+'" style="max-width:320px">'+
        '<div class="genrow"><button class="genimgbtn apply" onclick="milesApply(\''+esc(sku)+'\',\''+sidv+'\')">Use as main image</button>'+
        '<button class="genimgbtn" onclick="milesDownload(\''+esc(sku)+'\',\''+sidv+'\')"><i class="ti ti-download"></i> Download</button>'+
        '<button class="genimgbtn" onclick="document.getElementById(\'mresult_'+sidv+'\').innerHTML=\'\'">Discard</button></div></div>';
    }
  }catch(e){ if(btn){btn.disabled=false;} if(st) st.innerHTML='<span style="color:#ef9a9a">✗ '+esc(String(e))+'</span>'; }
}
function milesDownload(sku, sidv){
  var out=document.getElementById('mresult_'+sidv);
  var url=out?out.dataset.savedurl:'';
  if(!url){ toast('Nothing to download'); return; }
  // download the full-resolution saved image, named by its REAL extension (the
  // saved file already has the correct format suffix) so Amazon accepts it.
  var _m=String(url).split("?")[0].match(/\.(png|jpe?g|webp|gif)$/i);
  var _ext=_m?(_m[1].toLowerCase()==="jpeg"?"jpg":_m[1].toLowerCase()):"jpg";
  var a=document.createElement('a');
  a.href=url; a.download=(sku||'miles')+'_main.'+_ext;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}
async function milesApply(sku, sidv){
  var out=document.getElementById('mresult_'+sidv);
  var url=out?out.dataset.savedurl:'';
  if(!url){ toast('Nothing to apply'); return; }
  try{
    await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,target:'attr',key:'main_product_image_locator',value:url})});
    toast('Set as main image'); loadRows();
  }catch(e){ toast('Could not apply: '+e); }
}
// ===== Visual zone editor: drag boxes onto the template to place text =====
let ZE_STATE = null;
// ===== Advanced visual zone editor =====
// Zone object: {key, label, color, box:[x0,y0,x1,y1], align, bold, size, text, builtin}
function _defaultZones(){
  return [
    {key:'title',       label:'TITLE',          color:'#4c8dff', box:[0.07,0.33,0.40,0.42], align:'left',   bold:true,  size:1.0, builtin:true},
    {key:'grade',       label:'GRADE',          color:'#ffd479', box:[0.07,0.50,0.40,0.56], align:'center', bold:true,  size:1.0, builtin:true},
    {key:'choice',      label:'CHOICE (fixed)', color:'#9aa0aa', box:[0.07,0.565,0.40,0.60],align:'center', bold:false, size:1.0, builtin:true},
    {key:'application', label:'APPLICATION',    color:'#7fd99a', box:[0.07,0.78,0.40,0.88], align:'left',   bold:true,  size:1.0, builtin:true}
  ];
}
function _zonesToArray(saved){
  // accept either the new dict-of-objects or legacy dict-of-arrays
  var def=_defaultZones(); var byKey={}; def.forEach(z=>byKey[z.key]=z);
  if(!saved) return def;
  var out=[];
  Object.keys(saved).forEach(function(k){
    var v=saved[k]; var base=byKey[k]||{key:k,label:k.toUpperCase(),color:'#c792ea',builtin:false};
    if(Array.isArray(v)){ out.push(Object.assign({},base,{box:v,align:base.align||'left',bold:base.bold!==false,size:1.0,text:''})); }
    else { out.push(Object.assign({},base,{box:v.box,align:v.align||'left',bold:v.bold!==false,size:v.size||1.0,text:v.text||''})); }
  });
  // ensure builtins exist
  def.forEach(function(d){ if(!out.find(z=>z.key===d.key)) out.push(d); });
  return out;
}
function _zonesToSave(){
  var o={};
  ZE_STATE.zones.forEach(function(z){
    o[z.key]={box:z.box, align:z.align, bold:z.bold, size:z.size, text:z.text||''};
  });
  return o;
}
async function openZoneEditor(tid){
  var tpls=await (await fetch('/miles_template/list')).json().catch(()=>({templates:[]}));
  var t=(tpls.templates||[]).find(x=>x.id===tid);
  if(!t){ toast('Template not found'); return; }
  ZE_STATE={tid:tid, zones:_zonesToArray(t.zones), erase:(t.erase||[]), sel:null, tool:'move'};
  renderZoneEditor();
}
function renderZoneEditor(){
  var tid=ZE_STATE.tid;
  var html=`<div style="display:flex;gap:14px;flex-wrap:wrap">
    <div style="flex:1;min-width:300px">
      <div style="font-weight:600;margin-bottom:6px">Design the panel — drag boxes, edit each on the right</div>
      <div class="cc" style="margin-bottom:6px">Tools:
        <button class="genimgbtn ${ZE_STATE.tool==='move'?'apply':''}" onclick="zeTool('move')">Move/Resize</button>
        <button class="genimgbtn ${ZE_STATE.tool==='erase'?'apply':''}" onclick="zeTool('erase')">Eraser (drag to cover badge)</button>
      </div>
      <div id="zewrap" style="position:relative;display:inline-block;max-width:100%;user-select:none;border:1px solid #2a3344">
        <img id="zeimg" src="/miles_template/preview/${esc(tid)}" style="display:block;max-width:100%;max-height:56vh">
      </div>
      <div class="genrow" style="margin-top:10px">
        <button class="primary" onclick="saveZones()">Save</button>
        <span id="zesaved" style="display:none;color:#7fd99a;font-size:12px;margin-left:6px"></span>
        <button class="genimgbtn" onclick="zonePreview()">Preview with sample text</button>
        <button class="genimgbtn" onclick="zeAddZone()">+ Add text box</button>
        <button class="genimgbtn" onclick="openMilesTplManager()">Back</button>
      </div>
      <div id="zepreview" style="margin-top:10px"></div>
    </div>
    <div id="zeside" style="width:230px;flex-shrink:0"></div>
  </div>`;
  document.getElementById("acctmodalbody").innerHTML=html;
  document.getElementById("acctmodal").classList.add("open");
  setTimeout(function(){ zeDrawBoxes(); zeRenderSide(); }, 60);
}
function zeTool(t){ ZE_STATE.tool=t; renderZoneEditor(); }
function zeAddZone(){
  var n=ZE_STATE.zones.filter(z=>!z.builtin).length+1;
  ZE_STATE.zones.push({key:'custom'+Date.now(), label:'TEXT '+n, color:'#c792ea',
    box:[0.07,0.62,0.40,0.68], align:'center', bold:true, size:1.0, text:'TEXT', builtin:false});
  renderZoneEditor();
}
function zeDelZone(key){
  ZE_STATE.zones=ZE_STATE.zones.filter(z=>z.key!==key);
  if(ZE_STATE.sel===key) ZE_STATE.sel=null;
  renderZoneEditor();
}
function zeDrawBoxes(){
  var img=document.getElementById('zeimg'), wrap=document.getElementById('zewrap');
  if(!img||!wrap) return;
  function draw(){
    var iw=img.clientWidth, ih=img.clientHeight;
    // remove old
    wrap.querySelectorAll('.zebox,.zeerase').forEach(e=>e.remove());
    // erase rectangles
    (ZE_STATE.erase||[]).forEach(function(e,i){
      var d=document.createElement('div'); d.className='zeerase';
      d.style.left=(e[0]*iw)+'px'; d.style.top=(e[1]*ih)+'px';
      d.style.width=((e[2]-e[0])*iw)+'px'; d.style.height=((e[3]-e[1])*ih)+'px';
      d.innerHTML='<span class="zex" onclick="ZE_STATE.erase.splice('+i+',1);renderZoneEditor()">×</span>';
      wrap.appendChild(d);
    });
    // text zones with live text
    ZE_STATE.zones.forEach(function(z){
      var bx=document.createElement('div'); bx.className='zebox'+(ZE_STATE.sel===z.key?' sel':'');
      bx.dataset.zone=z.key; bx.style.borderColor=z.color;
      bx.style.left=(z.box[0]*iw)+'px'; bx.style.top=(z.box[1]*ih)+'px';
      bx.style.width=((z.box[2]-z.box[0])*iw)+'px'; bx.style.height=((z.box[3]-z.box[1])*ih)+'px';
      var shown = z.key==='choice'?'CHOICE OF MECHANICS':(z.builtin?z.label:(z.text||z.label));
      bx.style.justifyContent = 'flex-start';   // render is always left-aligned
      bx.innerHTML='<span class="zelbl" style="background:'+z.color+'">'+esc(z.label)+'</span>'+
        '<span class="zetext" style="font-weight:'+(z.bold?'700':'500')+'">'+esc(shown)+'</span>'+
        '<span class="zegrip"></span>';
      wrap.appendChild(bx);
    });
    zeBind();
  }
  if(!img.complete){ img.onload=draw; } else draw();
}
function zeBind(){
  var img=document.getElementById('zeimg'), wrap=document.getElementById('zewrap');
  var iw=img.clientWidth, ih=img.clientHeight;
  // eraser: drag a new rectangle
  if(ZE_STATE.tool==='erase'){
    wrap.onmousedown=function(e){
      if(e.target!==img && !e.target.classList.contains('zetext')) { /* allow */ }
      var r=img.getBoundingClientRect();
      var sx=(e.clientX-r.left)/iw, sy=(e.clientY-r.top)/ih;
      var box=[sx,sy,sx,sy];
      function mv(ev){ box[2]=(ev.clientX-r.left)/iw; box[3]=(ev.clientY-r.top)/ih; zeTempErase(box); }
      function up(){ document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up);
        var x0=Math.min(box[0],box[2]),y0=Math.min(box[1],box[3]),x1=Math.max(box[0],box[2]),y1=Math.max(box[1],box[3]);
        if(x1-x0>0.01&&y1-y0>0.01){ ZE_STATE.erase.push([x0,y0,x1,y1]); }
        renderZoneEditor();
      }
      document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
    };
    return;
  }
  wrap.onmousedown=null;
  // move/resize boxes
  wrap.querySelectorAll('.zebox').forEach(function(bx){
    bx.addEventListener('mousedown', function(e){
      e.preventDefault(); e.stopPropagation();
      ZE_STATE.sel=bx.dataset.zone; zeRenderSide();
      var z=ZE_STATE.zones.find(zz=>zz.key===bx.dataset.zone); if(!z) return;
      var isGrip=e.target.classList.contains('zegrip');
      var sX=e.clientX, sY=e.clientY, ob=z.box.slice();
      function mv(ev){
        var dx=(ev.clientX-sX)/iw, dy=(ev.clientY-sY)/ih;
        if(isGrip){ z.box=[ob[0],ob[1],Math.min(1,ob[2]+dx),Math.min(1,ob[3]+dy)]; }
        else { var w=ob[2]-ob[0],h=ob[3]-ob[1];
          var nx=Math.max(0,Math.min(1-w,ob[0]+dx)), ny=Math.max(0,Math.min(1-h,ob[1]+dy));
          z.box=[nx,ny,nx+w,ny+h]; }
        bx.style.left=(z.box[0]*iw)+'px'; bx.style.top=(z.box[1]*ih)+'px';
        bx.style.width=((z.box[2]-z.box[0])*iw)+'px'; bx.style.height=((z.box[3]-z.box[1])*ih)+'px';
      }
      function up(){ document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up); }
      document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
    });
  });
}
function zeTempErase(box){
  var img=document.getElementById('zeimg'), wrap=document.getElementById('zewrap');
  var iw=img.clientWidth, ih=img.clientHeight;
  var t=wrap.querySelector('.zetmp'); if(!t){ t=document.createElement('div'); t.className='zeerase zetmp'; wrap.appendChild(t); }
  var x0=Math.min(box[0],box[2]),y0=Math.min(box[1],box[3]);
  t.style.left=(x0*iw)+'px'; t.style.top=(y0*ih)+'px';
  t.style.width=(Math.abs(box[2]-box[0])*iw)+'px'; t.style.height=(Math.abs(box[3]-box[1])*ih)+'px';
}
function zeRenderSide(){
  var side=document.getElementById('zeside'); if(!side) return;
  var z=ZE_STATE.zones.find(zz=>zz.key===ZE_STATE.sel);
  if(!z){ side.innerHTML='<div class="cc">Click a box to edit its style.</div>'; return; }
  side.innerHTML=`<div style="font-weight:600;margin-bottom:8px">${esc(z.label)}</div>
    ${z.builtin?'':`<div class="genrow"><span class="cc">Text:</span><input class="ed" style="flex:1" value="${esc(z.text||'')}" oninput="zeSet('text',this.value)"></div>`}
    <div class="genrow" style="margin-top:6px"><label class="cc"><input type="checkbox" ${z.bold?'checked':''} onchange="zeSet('bold',this.checked)"> Bold</label></div>
    <div class="genrow" style="margin-top:6px"><span class="cc">Max size:</span>
      <input type="range" min="0.3" max="1" step="0.05" value="${z.size||1}" oninput="zeSet('size',parseFloat(this.value))" style="flex:1">
    </div>
    ${z.builtin?'':`<button class="del" style="margin-top:8px" onclick="zeDelZone('${z.key}')">Remove this box</button>`}
    <div class="cc" style="margin-top:10px;font-size:11px">Tip: drag the box on the left to move; drag its corner to resize.</div>`;
}
function zeSet(prop,val){
  var z=ZE_STATE.zones.find(zz=>zz.key===ZE_STATE.sel); if(!z) return;
  z[prop]=val; zeDrawBoxes(); zeRenderSide();
}
async function saveZones(){
  if(!ZE_STATE){ alert('Open a template first'); return; }
  var btn=event&&event.target;
  if(btn){ btn.disabled=true; btn.textContent='Saving…'; }
  try{
    var j=await (await fetch('/miles_template/save_zones',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:ZE_STATE.tid, zones:_zonesToSave(), erase:ZE_STATE.erase})})).json();
    if(btn){ btn.disabled=false; btn.textContent='Save'; }
    if(j.ok){
      MILES_TPLS=null;
      var s=document.getElementById('zesaved');
      if(s){ s.textContent='✓ Saved — every product on this template now uses this layout'; s.style.display='inline'; }
      if(typeof toast==='function') toast('Zones saved');
    } else {
      alert('Save failed: '+(j.error||'unknown'));
    }
  }catch(e){ if(btn){btn.disabled=false; btn.textContent='Save';} alert('Save error: '+e); }
}
async function zonePreview(){
  if(!ZE_STATE) return;
  var box=document.getElementById('zepreview');
  if(box) box.innerHTML='<span class="genspin"></span> rendering…';
  var j=await (await fetch('/miles_template/render',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({template_id:ZE_STATE.tid, sku:'_zonetest',
      spec:{title:'INDUSTIAL GEAR OIL', subtitles:[{text:'80W-90',lines:1}],
        application:{text:'HYDRAULIC FLUID',lines:2}, zones:_zonesToSave(), erase:ZE_STATE.erase}})})).json();
  if(box) box.innerHTML = j.ok ? '<img src="'+(j.data_url||j.url)+'" style="max-width:300px;border:1px solid #2a3344">'
    : '<span style="color:#ef9a9a">'+esc(j.error||'failed')+'</span>';
}
async function openMilesTplManager(){
  var tpls=await (await fetch('/miles_template/list')).json().catch(()=>({templates:[]}));
  var list=(tpls.templates||[]).map(t=>`<tr><td><img src="/miles_template/preview/${esc(t.id)}" style="height:48px"></td>`+
    `<td>${esc(t.label)}</td><td>${esc(t.container)}</td>`+
    `<td>${t.zones?'<span style="color:#7fd99a">✓ zones set</span>':'<span class="cc">no zones</span>'}</td>`+
    `<td><button class="primary" style="padding:3px 8px" onclick="openZoneEditor('${esc(t.id)}')">Edit zones</button> `+
    `<button class="del" onclick="milesTplDelete('${esc(t.id)}')">Delete</button></td></tr>`).join("")
    || '<tr><td colspan="5" class="cc">No templates yet.</td></tr>';
  var html=`<div style="font-weight:600;margin-bottom:8px">Miles blank templates</div>
    <table class="kv"><tr><td class="k">Label</td><td class="v"><input class="ed" id="mtm_label" placeholder="e.g. Drum 55gal"></td></tr>
    <tr><td class="k">Container</td><td class="v"><select class="ed" id="mtm_cont"><option value="pail">Pail (5 gal)</option><option value="drum">Drum (55 gal)</option></select></td></tr>
    <tr><td class="k">Blank PNG</td><td class="v"><input type="file" id="mtm_file" accept="image/png,image/jpeg"></td></tr></table>
    <button class="primary" style="margin:8px 0" onclick="milesTplUpload()">Upload template</button>
    <table class="kv" style="margin-top:10px">${list}</table>`;
  var m=document.getElementById("acctmodal");
  document.getElementById("acctmodalbody").innerHTML=html; m.classList.add("open");
}
async function milesTplUpload(){
  var f=(document.getElementById('mtm_file')||{}).files;
  if(!f||!f.length){ toast('Choose a PNG'); return; }
  var label=(document.getElementById('mtm_label')||{}).value||'Template';
  var cont=(document.getElementById('mtm_cont')||{}).value||'drum';
  var rd=new FileReader();
  rd.onload=async function(){
    try{
      var j=await (await fetch('/miles_template/upload',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({label:label, container:cont, data:rd.result})})).json();
      if(j.ok){ toast('Template uploaded'); MILES_TPLS=null; await refreshMilesDropdowns(); openMilesTplManager(); }
      else toast('Upload failed: '+(j.error||''));
    }catch(e){ toast('Error: '+e); }
  };
  rd.readAsDataURL(f[0]);
}
// Re-populate every open Miles template dropdown in the drawer with the latest list.
async function refreshMilesDropdowns(){
  MILES_TPLS=null;
  var tpls=await _loadMilesTpls();
  document.querySelectorAll('select[id^="mtpl_"]').forEach(function(sel){
    var cur=sel.value;
    sel.innerHTML = tpls.length
      ? tpls.map(t=>`<option value="${esc(t.id)}">${esc(t.label)} (${esc(t.container)})</option>`).join("")
      : '<option value="">no templates yet — click Manage templates to upload</option>';
    if(cur) sel.value=cur;
  });
}
async function milesTplDelete(id){
  if(!confirm('Delete this template?')) return;
  await fetch('/miles_template/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
  MILES_TPLS=null; toast('Deleted'); await refreshMilesDropdowns(); openMilesTplManager();
}
function askAbout(sku){
  var w=document.getElementById("chatwrap"); if(!w) return;
  w.classList.add("open"); fillChatCtx();
  var sel=document.getElementById("chatctx"); if(sel) sel.value=sku;
  setTimeout(function(){var i=document.getElementById("chatinput"); if(i) i.focus();},60);
}
async function submitLive(){
  // PRECHECK: catch local /media images Amazon can't fetch, before submitting.
  try{
    const pc=await (await fetch('/submit/precheck')).json();
    if(pc && pc.ok && pc.count>0){
      const skus=pc.local_image_rows.map(x=>x.sku).join(", ");
      alert("⚠ "+pc.count+" listing(s) have a LOCAL image that Amazon cannot fetch:\n\n  "+skus+"\n\n"
        +"AI images saved to your media library live on your PC (127.0.0.1), so Amazon's servers can't reach them. "
        +"These rows will FAIL with 'Unable to Retrieve Media Content'.\n\n"
        +"Fix: use a publicly-hosted image URL for the main image (e.g. upload to a host, or use the source image URL), "
        +"then submit again. The other rows can still go through.");
      if(!confirm("Submit anyway? (the local-image rows above will error)")) return;
    }
  }catch(e){}
  // SAFETY: confirm WHICH Amazon account this will publish to, by name.
  let t;
  try{ t=await (await fetch('/submit/target')).json(); }catch(e){ t=null; }
  if(!t || !t.ok){
    if(!confirm("Could not determine the target account. Submit anyway to your live account?")) return;
  } else {
    if(t.block==='none'){
      alert("This view is set to the "+t.marketplace+" marketplace, but no credentials are configured for it. Nothing will be submitted. Add the account's SP-API credentials first.");
      return;
    }
    var _sel = selectedSkus();
    var _scope = _sel.length
      ? ("the "+_sel.length+" SELECTED listing(s):\n    "+_sel.join(", ")+"\n")
      : "every APPROVED / API_READY row in THIS view";
    var msg = "PUBLISH LIVE \u2014 confirm the destination account:\n\n"
      + "  Account:    "+t.account_label+"\n"
      + (t.seller_id?("  Seller ID:  "+t.seller_id+"\n"):"")
      + "  Marketplace: "+t.marketplace+"\n"
      + "  Workspace:  "+t.view+"\n\n"
      + "This will CREATE or REPLACE live listings for "+_scope+", on the account above.\n"
      + "(Already-live listings are skipped automatically.)\n\nIs this the correct account?";
    if(!confirm(msg)) return;
  }
  // Scope the submit to the user's SELECTION when there is one; otherwise fall back
  // to all approved/ready rows (the server's default).
  var _sel2 = selectedSkus();
  if(_sel2.length) runMode('api_submit', _sel2);
  else runMode('api_submit');
}
function isEmptyRow(r){
  const s=x=>String(x==null?"":x).trim();
  return !s(r.sku)&&!s(r.title)&&!s(r.asin)&&!s(r.product_type)&&!s(r.price);
}
function render(){
  const grid=document.getElementById("grid");
  const list=ROWS.filter(passFilter);
  const empties=list.filter(isEmptyRow);
  const realAll=list.filter(r=>!isEmptyRow(r));
  const _norm = v => String(v||"").trim().toUpperCase();
  // Use the shared isActuallyLive() so render() and summary() ALWAYS agree.
  // Before this fix, render() had inline logic while summary() did not, so a
  // row displayed under "Live on Amazon" was still counted as HOLD in the top
  // bar. Any future changes to the "is this live?" rule need only edit
  // isActuallyLive() -- both callers pick up the fix automatically.
  const sets = _liveCatSetsForCurrentView();
  const _liveCatSkus  = sets.skus;
  const _liveCatAsins = sets.asins;
  const _liveGroupShown = sets.liveGroupShown;
  const _isActuallyLive = r => isActuallyLive(r, _liveCatSkus, _liveCatAsins, _liveGroupShown);
  const real     = realAll.filter(r=>!_isActuallyLive(r));
  const liveRows = realAll.filter(r=> _isActuallyLive(r));
  const note = empties.length
    ? `<div class="emptynote">${empties.length} empty row${empties.length>1?'s':''} hidden — <button class="linkbtn" onclick="clearEmpty(this)">clear them from the sheet</button></div>`
    : "";
  // SOURCE: drafts (app rows) / live (Amazon catalog) / all (both)
  let draftHtml = real.length ? real.map(card).join("") : "";
  // DEDUPE: the same SKU can exist BOTH as an app row marked LIVE and as an
  // Amazon-catalog tile (fetched from Seller Central). Showing both makes one
  // real listing appear twice. Prefer the app row (it has the edit controls +
  // "Push image to live"), and drop any catalog tile whose SKU/ASIN already
  // appears as a LIVE app row.
  const liveAppSkus = new Set(liveRows.map(r=>_norm(r.sku)));
  const liveAppAsins = new Set(liveRows.map(r=>_norm(r.asin)).filter(Boolean));
  const liveCatalog = (LIVE_ITEMS||[]).filter(it=>{
    const s=_norm(it.sku), a=_norm(it.asin);
    if(s && liveAppSkus.has(s)) return false;   // same SKU already shown as app row
    if(a && liveAppAsins.has(a)) return false;  // or same ASIN
    return true;
  });
  // live group = app rows already submitted (status LIVE) + non-duplicate catalog tiles
  let liveHtml  = (liveRows.length ? liveRows.map(card).join("") : "")
                + (liveCatalog.length ? liveCatalog.map(liveTile).join("") : "");
  if(LIST_SOURCE==="live"){
    grid.innerHTML = liveHtml || `<div class="empty">No live listings loaded yet.${CUR_ACCOUNT?(WS_MARKET?` <button class="mktbtn on" style="margin-left:8px" onclick="loadLiveCatalog(true)">Fetch ${esc(WS_MARKET)} live listings now</button>`:' Select a marketplace first.'):' Open an Amazon account workspace.'}</div>`;
  } else if(LIST_SOURCE==="all"){
    grid.innerHTML = note
      + (draftHtml?('<div class="srcgroup">Drafts (in this app)</div>'+draftHtml):'')
      + (liveHtml?('<div class="srcgroup">Live on Amazon</div>'+liveHtml):'')
      + ((!draftHtml&&!liveHtml)?'<div class="empty">Nothing to show yet.</div>':'');
  } else {
    // default view: show drafts, then any already-live (submitted) app rows,
    // each under a clear heading, so a submitted listing is visible but not
    // mislabeled as a draft.
    const liveAppHtml = liveRows.length ? liveRows.map(card).join("") : "";
    grid.innerHTML = note
      + (draftHtml?('<div class="srcgroup">Drafts (in this app)</div>'+draftHtml):'')
      + (liveAppHtml?('<div class="srcgroup">Live on Amazon</div>'+liveAppHtml):'')
      + ((!draftHtml&&!liveAppHtml)?(empties.length ? "" : `<div class="empty">No listings in this view.${ROWS.length?'':' Run Generate to create some.'}</div>`):'');
  }
  summary();
  // fetch real product images for live tiles that don't have one yet
  if((LIST_SOURCE==="live"||LIST_SOURCE==="all") && LIVE_ITEMS.length){ fetchLiveImages(); }
  // keep an open drawer in sync with refreshed data -- BUT never while a per-
  // listing Preview/Submit run is streaming into the drawer panel, or the panel
  // (and its live log) would be wiped mid-run.
  if(DRAWER_SKU && !window.RUN_STREAMING){
    var dr=ROWS.find(x=>String(x.sku)===String(DRAWER_SKU));
    if(dr){ var b=document.getElementById("drawerbody"); if(b) b.innerHTML=drawerContent(dr); }
    else closeDrawer();
  }
}
async function delRow(sku, row, btn){
  if(!confirm("Delete this row from the sheet? This cannot be undone.")) return;
  btn.disabled=true;
  try{
    const res=await fetch("/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sku:sku,row:row})});
    const j=await res.json();
    if(j.ok){ toast("Row deleted"); loadRows(); }
    else{ toast("Delete failed: "+(j.error||"")); btn.disabled=false; }
  }catch(e){ toast("Delete failed"); btn.disabled=false; }
}
async function bulkStatus(status){
  const skus=selectedSkus();
  if(!skus.length){ toast("Nothing selected"); return; }
  // normalise: the sheet uses NEEDS_REVIEW for "hold"
  if(status==="HOLD") status="NEEDS_REVIEW";
  const label = status==="APPROVED" ? "Approve" : "Hold";
  if(!confirm(label+" "+skus.length+" selected listing(s)?")) return;
  let ok=0, fail=0;
  toast(label+"ing "+skus.length+"…");
  for(const sku of skus){
    try{
      const res=await fetch("/approve",{method:"POST",headers:{"Content-Type":"application/json"},
                  body:JSON.stringify({sku:sku, status:status})});
      const j=await res.json();
      if(j.ok) ok++; else fail++;
    }catch(e){ fail++; }
  }
  toast(label+"d "+ok+(fail?(" / "+fail+" failed"):""));
  clearSelection(); loadRows();
}
async function bulkDelete(){
  const skus=selectedSkus();
  if(!skus.length){ toast("Nothing selected"); return; }
  if(!confirm("Delete "+skus.length+" selected listing(s) from the sheet? This cannot be undone.")) return;
  let ok=0, fail=0;
  toast("Deleting "+skus.length+"…");
  // delete from the BOTTOM up so row numbers don't shift mid-loop
  const items=skus.map(s=>{const r=ROWS.find(x=>String(x.sku)===String(s)); return {sku:s, row:(r&&r.row)||null};})
                  .sort((a,b)=>(b.row||0)-(a.row||0));
  for(const it of items){
    try{
      const res=await fetch("/delete",{method:"POST",headers:{"Content-Type":"application/json"},
                  body:JSON.stringify({sku:it.sku, row:it.row})});
      const j=await res.json();
      if(j.ok) ok++; else fail++;
    }catch(e){ fail++; }
  }
  toast("Deleted "+ok+(fail?(" / "+fail+" failed"):""));
  clearSelection(); loadRows();
}
async function clearMainImage(sku){
  if(!sku) return;
  if(!confirm("Remove the main image from this listing?\n\nThe listing can then be created WITHOUT an image (add one later in Seller Central). This also clears any additional image URLs that are local files.")) return;
  try{
    // remove main + any local (non-http) additional image locators
    const r=ROWS.find(x=>String(x.sku)===String(sku));
    let a={}; try{a=JSON.parse((r&&r.attrs)||"{}");}catch(e){a={};}
    const toClear=["main_product_image_locator"];
    Object.keys(a).forEach(k=>{
      if(/^other_product_image_locator_\d+$/.test(k)){
        const v=String(a[k]||"");
        if(!/^https?:\/\//i.test(v)) toClear.push(k);   // only drop local ones
      }
    });
    for(const k of toClear){
      await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, target:"attr", key:k, value:""})});
    }
    toast("Main image removed — listing can be created without it");
    // refresh this row so the panel updates
    try{
      const j=await (await fetch("/row?sku="+encodeURIComponent(sku))).json();
      if(j&&j.ok&&j.row){ const i=ROWS.findIndex(x=>String(x.sku)===String(sku)); if(i>=0) ROWS[i]={...ROWS[i],...j.row}; }
    }catch(e){}
    if(DRAWER_SKU===sku) openDrawer(sku); else render();
  }catch(e){ toast("Could not remove image: "+e); }
}
async function clearEmpty(btn){
  if(!confirm("Remove all empty rows from the sheet?")) return;
  btn.disabled=true;
  try{
    const res=await fetch("/clear_empty",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    const j=await res.json();
    if(j.ok){ toast("Removed "+(j.deleted||0)+" empty row(s)"); loadRows(); }
    else{ toast("Failed: "+(j.error||"")); btn.disabled=false; }
  }catch(e){ toast("Failed"); btn.disabled=false; }
}

let LIST_SOURCE = "drafts";   // 'drafts' | 'live' | 'all'
let LIVE_ITEMS = [];          // fetched live Amazon catalog for current account+mkt
let LIVE_STORE = {};          // cache: "accountid::MKT" -> {items, ts}
let LIVE_SYNC_TIMER = null;   // auto-sync interval handle

function _liveKey(){ return (CUR_ACCOUNT?CUR_ACCOUNT.id:"")+"::"+(WS_MARKET||""); }

function setListSource(src){
  if((src==="live"||src==="all") && CUR_ACCOUNT && !CUR_ACCOUNT.has_creds){
    toast("Live listings need a connected account. Add SP-API credentials to this account first.");
    // keep on drafts
    document.querySelectorAll('#srcswitch .mktbtn').forEach(b=>b.classList.toggle('on', b.dataset.src==='drafts'));
    LIST_SOURCE='drafts'; render();
    return;
  }
  LIST_SOURCE=src;
  document.querySelectorAll('#srcswitch .mktbtn').forEach(b=>b.classList.toggle('on', b.dataset.src===src));
  if((src==="live"||src==="all") && CUR_ACCOUNT){
    if(!WS_MARKET){ toast("Select a marketplace (US, UK, etc.) first, then it will load."); render(); return; }
    loadLiveCatalog(false);   // uses cache if present; fetches only if not cached
  }
  else render();
}
async function loadLiveCatalog(force){
  if(!CUR_ACCOUNT){ toast("Live catalog is per Amazon account — open an account workspace"); return; }
  if(!WS_MARKET){ toast("Pick a marketplace first"); return; }
  // Never refresh the live catalog while a per-listing Preview/Submit is streaming
  // into the drawer panel -- rewriting grid.innerHTML below would destroy that
  // panel (and its live log) mid-run. Defer; the next manual Sync/refresh picks it up.
  if(window.RUN_STREAMING){ return; }
  // "All marketplaces": fetch each marketplace's catalog and merge
  if(WS_MARKET==="__all__"){ return loadAllMarketplaces(force); }
  const key=_liveKey();
  const reqAccount=CUR_ACCOUNT.id, reqMkt=WS_MARKET;   // remember what THIS request is for
  // use in-browser cache unless forced -> returning to the page is instant
  if(!force && LIVE_STORE[key]){
    LIVE_ITEMS=LIVE_STORE[key].items; render(); updateSyncLabel(); return;
  }
  const grid=document.getElementById("grid");
  if(grid) grid.innerHTML='<div class="empty"><span class="genspin"></span> Fetching live listings from Amazon…<div class="cc" style="margin-top:8px">The first fetch generates a report on Amazon\u2019s side and can take 1\u20134 minutes for larger accounts. After that it\u2019s cached for 30 minutes. Please leave this open.</div></div>';
  try{
    const j=await (await fetch("/live/catalog",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:reqAccount,marketplace:reqMkt,force:!!force})})).json();
    // GUARD: if the user switched account/marketplace while this was loading,
    // store the result in its own cache slot but do NOT render it into the
    // current (different) view. This prevents one account's listings leaking
    // into another.
    const stillHere = (CUR_ACCOUNT && CUR_ACCOUNT.id===reqAccount && WS_MARKET===reqMkt);
    if(!j.ok){
      if(stillHere && grid) grid.innerHTML='<div class="empty">Could not load live catalog: '+esc(j.error||"")+'</div>';
      return;
    }
    LIVE_STORE[reqAccount+"::"+reqMkt]={items:(j.items||[]), ts:Date.now()};
    if(stillHere){
      LIVE_ITEMS=j.items||[];
      // If a Preview/Submit started streaming while this fetch was in flight,
      // cache the result but don't render now -- rendering would wipe the panel.
      if(window.RUN_STREAMING){ updateSyncLabel(); startAutoSync(); return; }
      render(); updateSyncLabel(); startAutoSync();
    }
  }catch(e){ if(grid && CUR_ACCOUNT && CUR_ACCOUNT.id===reqAccount && WS_MARKET===reqMkt) grid.innerHTML='<div class="empty">Error: '+esc(String(e))+'</div>'; }
}
function updateSyncLabel(){
  const el=document.getElementById("synclabel"); if(!el) return;
  const key=_liveKey(); const c=LIVE_STORE[key];
  if(c){ const mins=Math.round((Date.now()-c.ts)/60000);
    el.textContent = mins<1?"synced just now":("synced "+mins+"m ago"); }
  else el.textContent="";
}
function startAutoSync(){
  // SP-API is free (no AI credits), so a periodic background sync is fine.
  if(LIVE_SYNC_TIMER) return;
  LIVE_SYNC_TIMER=setInterval(()=>{
    if(window.RUN_STREAMING) return;   // don't wipe a streaming drawer panel
    if((LIST_SOURCE==="live"||LIST_SOURCE==="all") && CUR_ACCOUNT && WS_MARKET){
      loadLiveCatalog(true);   // refresh quietly every 30 min
    }
  }, 30*60*1000);
}
async function syncLive(){
  toast("Syncing live listings from Amazon…");
  await loadLiveCatalog(true);
}
async function runSpDiagnose(){
  // Run the one-shot SP-API health check for THIS workspace's account +
  // marketplace, and show the raw per-layer report in a modal. Every layer
  // (DNS, TCP, TLS, LWA auth, each SP-API operation) prints PASS/FAIL and
  // exactly what to fix if it fails -- so we don't have to guess anymore.
  const mkt = WS_MARKET && WS_MARKET!=="__all__" ? WS_MARKET : "UK";
  const acct = (CUR_ACCOUNT && CUR_ACCOUNT.id) ? CUR_ACCOUNT.id : "";
  const dlg = document.createElement("div");
  dlg.className = "modalwrap open";
  dlg.style.zIndex = "130";
  dlg.innerHTML = `<div class="modal" style="max-width:820px;position:relative">
    <button class="x" onclick="this.closest('.modalwrap').remove()">×</button>
    <h3><i class="ti ti-stethoscope"></i> SP-API diagnostic — ${esc(mkt)}${acct?(' · '+esc(acct)):''}</h3>
    <div class="cc" style="margin:2px 0 10px">Testing DNS → TCP → TLS → LWA auth → every SP-API operation. This takes ~15–45 seconds. The output tells you exactly which layer is broken and how to fix it.</div>
    <pre id="spdiagout" style="background:#0d1220;border:1px solid var(--line);border-radius:8px;padding:12px;font-size:12px;max-height:65vh;overflow:auto;white-space:pre-wrap;color:#cfe0ff"><span class="genspin"></span> Running…</pre>
  </div>`;
  document.body.appendChild(dlg);
  try{
    const j = await (await fetch("/sp_diagnose",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({marketplace:mkt, account_id:acct})})).json();
    const box=document.getElementById("spdiagout");
    if(!box) return;
    if(!j.ok){ box.textContent = "Error: "+(j.error||"unknown"); return; }
    // colour-tint PASS/FAIL/WARN lines for scannability
    const lines=(j.output||"").split("\n").map(l=>{
      if(/\bPASS\b/.test(l))  return '<span style="color:#7fd99a">'+esc(l)+'</span>';
      if(/\bFAIL\b/.test(l))  return '<span style="color:#e0696b">'+esc(l)+'</span>';
      if(/\bWARN\b/.test(l))  return '<span style="color:#e3b768">'+esc(l)+'</span>';
      if(/^\[.\d+\]/.test(l)) return '<span style="color:#9cc1ff;font-weight:600">'+esc(l)+'</span>';
      return esc(l);
    }).join("\n");
    box.innerHTML = lines + '\n\n<span style="color:'+(j.exit_code===0?'#7fd99a':'#e3b768')+'">Exit code: '+j.exit_code+'</span>';
  }catch(e){
    const box=document.getElementById("spdiagout");
    if(box) box.textContent = "Diagnostic failed to start: "+e;
  }
}
async function loadAllMarketplaces(force){
  if(window.RUN_STREAMING){ return; }   // don't wipe a streaming drawer panel mid-run
  const mkts=(CUR_ACCOUNT.marketplaces||[]);
  if(!mkts.length){ toast("No marketplaces detected for this account."); return; }
  const grid=document.getElementById("grid");
  // serve from cache if every marketplace is already cached and not forcing
  const allCached = mkts.every(mm => LIVE_STORE[CUR_ACCOUNT.id+"::"+mm]);
  if(!force && allCached){
    LIVE_ITEMS = mkts.flatMap(mm => (LIVE_STORE[CUR_ACCOUNT.id+"::"+mm].items||[]).map(it=>({...it,_mkt:mm})));
    render(); updateSyncLabel(); return;
  }
  const reqAccount=CUR_ACCOUNT.id;
  let merged=[]; let done=0;
  for(const mm of mkts){
    if(!(CUR_ACCOUNT && CUR_ACCOUNT.id===reqAccount && WS_MARKET==="__all__")) return; // user moved on
    if(grid) grid.innerHTML='<div class="empty"><span class="genspin"></span> Fetching all marketplaces… '+(done)+'/'+mkts.length+' ('+esc(mm)+')<div class="cc" style="margin-top:8px">Each marketplace is a separate Amazon report; this can take a few minutes the first time.</div></div>';
    try{
      const j=await (await fetch("/live/catalog",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:reqAccount,marketplace:mm,force:!!force})})).json();
      if(j.ok){
        LIVE_STORE[reqAccount+"::"+mm]={items:(j.items||[]), ts:Date.now()};
        merged=merged.concat((j.items||[]).map(it=>({...it,_mkt:mm})));
      }
    }catch(e){}
    done++;
  }
  if(CUR_ACCOUNT && CUR_ACCOUNT.id===reqAccount && WS_MARKET==="__all__"){
    LIVE_ITEMS=merged; render(); updateSyncLabel(); startAutoSync();
  }
}
function liveTile(it){
  // real status from the report (Active/Inactive/Incomplete), not a hardcoded LIVE
  var st=(it.status||"Active").trim();
  var stl=st.toLowerCase();
  // check inactive/suppressed/incomplete BEFORE active ("inactive" contains "active")
  var col = (stl.indexOf("inactive")>=0||stl.indexOf("suppress")>=0)?"#ef9a9a"
          : stl.indexOf("incomplete")>=0?"#e3b768"
          : stl.indexOf("active")>=0?"#74e0a3"
          : "#9aa3b2";
  var price = it.price ? (CUR_SYMBOL+esc(String(it.price).replace(/^[A-Z]{3}\s?/,''))) : '';
  // image slot — filled from the real getListingsItem image (fetched in batch after render)
  var sidv = sid(it.sku||it.asin||'');
  var imgHtml = it.img
    ? `<img src="${esc(it.img)}" loading="lazy">`
    : (it._noImg
        ? `<div class="noimgmsg"><i class="ti ti-photo-off"></i><span>No image uploaded</span></div>`
        : `<i class="ti ti-cloud-check" id="liveimg_${sidv}"></i>`);
  // qty: show value, or FBA/— when the report omits it
  var qtyHtml = (it.qty!==undefined && it.qty!=='' && it.qty!==null) ? ('qty '+esc(it.qty)) : '<span class="cc">qty —</span>';
  // profit margin chip
  var profHtml = '';
  if(it.profit){
    var mcol = it.profit.margin>=25?'#74e0a3':(it.profit.margin>=10?'#e3b768':'#ef9a9a');
    profHtml = `<span class="profchip" style="color:${mcol};border-color:${mcol}55;background:${mcol}1a" title="Price ${CUR_SYMBOL}${it.profit.price} − COGS ${CUR_SYMBOL}${it.profit.cogs} − ~15% referral ${CUR_SYMBOL}${it.profit.referral} = ${CUR_SYMBOL}${it.profit.net}">${it.profit.margin}% · ${CUR_SYMBOL}${it.profit.net}</span>`;
  } else {
    profHtml = `<span class="profchip cc" style="cursor:pointer" title="Set cost to see margin" onclick="event.stopPropagation();setCogs('${esc(it.sku||'')}','${esc(String(it.price||''))}')">+ COGS</span>`;
  }
  // fulfillment (FBA/FBM) + handling time + delivery estimate
  var fch = it.fulfillment||"";
  var fmode = /FBA|AMAZON/i.test(fch) ? "FBA" : (fch ? "FBM" : "");
  var fcol = fmode==="FBA" ? "#9cc1ff" : "#c9b6e8";
  var shipHtml = "";
  if(fmode){
    var fmt = (d)=>d.toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric'});
    var hd, transit;
    if(it.handling!==undefined && it.handling!==null && it.handling!=="" && !isNaN(parseInt(it.handling))){
      hd = parseInt(it.handling);
      transit = fmode==="FBA" ? 2 : 5;
    } else if(fmode==="FBA"){
      hd = 0; transit = 2;   // FBA: typically same/next-day handling + ~2d transit
    } else {
      hd = null;             // FBM with unknown handling
    }
    if(hd!==null){
      var shipBy = new Date(Date.now()+hd*864e5);
      var delBy  = new Date(Date.now()+(hd+transit)*864e5);
      shipHtml = `<div class="cc shipline" style="margin-top:4px"><span class="fmode" style="color:${fcol};border-color:${fcol}55;background:${fcol}1a">${fmode}</span> `+
                 `<span title="When it leaves the warehouse if ordered today">📦 ships by ${fmt(shipBy)}</span> · `+
                 `<span title="Estimated arrival for the customer">🚚 delivery ~${fmt(delBy)}</span>`+
                 `${it.ship_group?(' · <span class="cc" title="Shipping template">'+esc(it.ship_group)+'</span>'):''}</div>`;
    } else {
      shipHtml = `<div class="cc shipline" style="margin-top:4px"><span class="fmode" style="color:${fcol};border-color:${fcol}55;background:${fcol}1a">${fmode}</span> <span class="cc">handling time not set</span>${it.ship_group?(' · '+esc(it.ship_group)):''}</div>`;
    }
  } else {
    shipHtml = `<div class="cc shipline" style="margin-top:4px"><span class="cc">fulfillment loading…</span></div>`;
  }
  return `<div class="tile live" title="On Amazon — status: ${esc(st)}">
    <input type="checkbox" class="tilesel" ${SELECTED.has(String(it.sku))?'checked':''} onclick="event.stopPropagation()" onchange="toggleSelect('${esc(it.sku||'')}',this.checked)" title="Select for batch image generation">
    <div class="tileimg ${it.asin?'':'noimg'}">${imgHtml}</div>
    <div class="tilebody">
      <div class="tiletitle">${esc(it.title)||'<span class="cc">(no title in report)</span>'}</div>
      <div class="tilemeta"><span class="tileprice">${price}</span><span class="tilesku">${esc(it.sku||'')}</span></div>
      <div class="cc" style="margin-top:4px"><span class="livestatus" style="background:${col}1f;color:${col};border:1px solid ${col}55">${esc(st)}</span> ${esc(it.asin||'')} · ${qtyHtml}</div>
      ${shipHtml}
      <div style="margin-top:5px">${profHtml}</div>
    </div>
    <div class="tileacts">
      <button class="ib" title="Optimize this live listing" onclick="optimizeLive('${esc(it.asin||'')}','${esc(it.sku||'')}')"><i class="ti ti-wand"></i> Optimize</button>
      <button class="ib" title="Generate images for this product" onclick="event.stopPropagation();openStudioSingle('${esc(it.sku||'')}')"><i class="ti ti-photo"></i> Images</button>
      <a class="ib" title="View on Amazon" href="https://www.amazon.${WS_MARKET==='UK'?'co.uk':(WS_MARKET==='US'?'com':'com')}/dp/${esc(it.asin||'')}" target="_blank" rel="noopener"><i class="ti ti-external-link"></i></a>
    </div>
  </div>`;
}
async function uploadCogsCsv(input){
  const file=input.files&&input.files[0]; if(!file) return;
  const text=await file.text();
  const lines=text.split(/\r?\n/).filter(l=>l.trim());
  if(!lines.length){ toast("Empty CSV."); return; }
  // detect columns from header
  const hdr=lines[0].split(",").map(h=>h.trim().toLowerCase());
  const skuI=hdr.findIndex(h=>h==="sku"||h==="seller-sku"||h==="seller_sku");
  const asinI=hdr.findIndex(h=>h==="asin"||h==="asin1");
  const costI=hdr.findIndex(h=>h==="cost"||h==="cogs"||h==="source price"||h==="source_price"||h==="price");
  if(costI<0||(skuI<0&&asinI<0)){ toast("CSV needs a cost column and a sku or asin column."); input.value=""; return; }
  // build sku->cost; for ASIN-only rows, map against loaded live items
  const asinToSku={}; (LIVE_ITEMS||[]).forEach(it=>{ if(it.asin) asinToSku[it.asin]=it.sku; });
  const rows=[];
  for(let i=1;i<lines.length;i++){
    const c=lines[i].split(",");
    const cost=(c[costI]||"").trim(); if(!cost) continue;
    let sku=skuI>=0?(c[skuI]||"").trim():"";
    if(!sku && asinI>=0){ const asin=(c[asinI]||"").trim(); sku=asinToSku[asin]||""; }
    if(sku) rows.push({sku:sku, cost:cost});
  }
  if(!rows.length){ toast("No matchable rows (check sku/asin values match your listings)."); input.value=""; return; }
  try{
    const j=await (await fetch("/cogs/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT.id,rows:rows})})).json();
    if(!j.ok){ toast("Upload failed: "+(j.error||"")); input.value=""; return; }
    toast("COGS set for "+j.count+" SKUs. Re-syncing to show margins…");
    input.value="";
    await loadLiveCatalog(true);   // refresh so margins recompute
  }catch(e){ toast("Error: "+e); input.value=""; }
}
let _imgFetchBusy=false;
async function fetchLiveImages(){
  if(_imgFetchBusy) return;
  const need=(LIVE_ITEMS||[]).filter(it=>!it.img && it.sku).map(it=>it.sku);
  if(!need.length) return;
  _imgFetchBusy=true;
  const reqAccount=CUR_ACCOUNT?CUR_ACCOUNT.id:"", reqMkt=WS_MARKET;
  try{
    // fetch in chunks so images appear progressively
    for(let i=0;i<need.length;i+=20){
      if(!CUR_ACCOUNT||CUR_ACCOUNT.id!==reqAccount||WS_MARKET!==reqMkt) break; // user moved on
      const chunk=need.slice(i,i+20);
      const j=await (await fetch("/live/images",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:reqAccount,marketplace:reqMkt,skus:chunk})})).json();
      if(j&&j.ok){
        let changed=false;
        Object.entries(j.images||{}).forEach(([sku,url])=>{
          if(!url) return;
          const it=(LIVE_ITEMS||[]).find(x=>x.sku===sku); if(it){ it.img=url; }
          const slot=document.getElementById("liveimg_"+sid(sku));
          if(slot){ const box=slot.parentNode; box.classList.remove("noimg"); box.innerHTML='<img src="'+url+'" loading="lazy">'; }
        });
        // apply REAL status (from getListingsItem) which is more accurate than the report
        Object.entries(j.statuses||{}).forEach(([sku,st])=>{
          const it=(LIVE_ITEMS||[]).find(x=>x.sku===sku);
          if(it && st && it.status!==st){ it.status=st; it._realStatus=true; changed=true; }
        });
        // apply fulfillment (FBA/FBM) + handling time + live title
        Object.entries(j.meta||{}).forEach(([sku,mm])=>{
          const it=(LIVE_ITEMS||[]).find(x=>x.sku===sku);
          if(it && mm){
            if(mm.fulfillment && it.fulfillment!==mm.fulfillment){ it.fulfillment=mm.fulfillment; changed=true; }
            if(mm.handling!==undefined && mm.handling!==null && it.handling!==mm.handling){ it.handling=mm.handling; changed=true; }
            // live title from getListingsItem reflects Amazon edits immediately;
            // prefer it over the (possibly stale) report title
            if(mm.title && mm.title.trim() && it.title!==mm.title){ it.title=mm.title; changed=true; }
          }
        });
        // mark items we checked that have NO image, so we can show "no image" text
        chunk.forEach(sku=>{
          const it=(LIVE_ITEMS||[]).find(x=>x.sku===sku);
          if(it && !it.img){ it._noImg=true; }
        });
        const key=_liveKey(); if(LIVE_STORE[key]) LIVE_STORE[key].items=LIVE_ITEMS;
        if(changed) render();   // refresh so corrected statuses/colors show
      }
    }
  }catch(e){ /* silent — images are best-effort */ }
  _imgFetchBusy=false;
}
async function setCogs(sku, price){
  const cur=prompt("Enter your cost (COGS) for SKU "+sku+"\n\nThis is your total cost including shipping. Margin = (price − COGS − ~15% Amazon referral) / price.","");
  if(cur===null) return;
  try{
    const j=await (await fetch("/cogs/set",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT.id,sku:sku,cost:cur,price:price})})).json();
    if(!j.ok){ toast("Could not set COGS: "+(j.error||"")); return; }
    // update the cached item and re-render
    const key=_liveKey();
    (LIVE_ITEMS||[]).forEach(it=>{ if(it.sku===sku){ it.profit=j.profit; it.cogs=parseFloat(cur); } });
    if(LIVE_STORE[key]) LIVE_STORE[key].items=LIVE_ITEMS;
    render();
  }catch(e){ toast("Error: "+e); }
}
let OPT_CURRENT = null;   // {sku, asin, product_type, marketplace, marketplace_id, fields}
async function optimizeLive(asin, sku){
  if(!sku){ toast("This listing has no SKU in the report — can't optimize it directly."); return; }
  const mod=document.getElementById("optmodal"); mod.classList.add("open");
  document.getElementById("optbody").innerHTML='<div class="gendiag"><span class="genspin"></span> Fetching current live data from Amazon…</div>';
  try{
    const j=await (await fetch("/optimize/fetch",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT?CUR_ACCOUNT.id:"",sku:sku,marketplace:WS_MARKET})})).json();
    if(!j.ok){ document.getElementById("optbody").innerHTML='<div class="gendiag bad">✗ '+esc(j.error||"failed")+'</div>'; return; }
    OPT_CURRENT=j;
    OPT_EDIT_STATE=null;   // fresh listing -> clear any prior edits
    OPT_BRAND_HINT = (CUR_ACCOUNT && CUR_ACCOUNT.brands && CUR_ACCOUNT.brands.length) ? CUR_ACCOUNT.brands[0] : (CUR_ACCOUNT?CUR_ACCOUNT.label:"");
    renderOptEditor(j);
  }catch(e){ document.getElementById("optbody").innerHTML='<div class="gendiag bad">✗ '+esc(String(e))+'</div>'; }
}
function _optAttrToText(v){
  // turn an SP-API attribute value (list of dicts) into an editable string
  if(Array.isArray(v)){
    return v.map(x=>{
      if(x && typeof x==='object'){
        return x.value!==undefined?x.value:(x.media_location!==undefined?x.media_location:JSON.stringify(x));
      }
      return String(x);
    }).join(" | ");
  }
  return v==null?"":String(v);
}
function optIssuesPanel(j){
  const issues=j.issues||[];
  const errs=issues.filter(i=>(i.severity||"").toUpperCase()==="ERROR");
  const warns=issues.filter(i=>(i.severity||"").toUpperCase()!=="ERROR");
  let statusLine = j.listing_status ? `<div class="cc" style="margin-bottom:6px">Amazon status: <b>${esc(j.listing_status)}</b></div>` : "";
  if(!issues.length){
    return statusLine+`<div class="issuesbox ok"><b>✓ No attribute issues reported by Amazon.</b> If you still see a red dot, it's usually a <i>recommended</i> (not required) field, a pricing/Buy-Box issue, or a category review — not a missing attribute. You can still run a full diagnosis below.
      <div style="margin-top:8px"><button class="suggestbtn" onclick="optDiagnose()"><i class="ti ti-stethoscope"></i> Diagnose with Amazon &amp; suggest fixes</button> <span id="opt_diagstatus" class="cc"></span></div></div>`;
  }
  const renderList=(arr,cls,label)=> arr.length?`
    <div class="issgrp">
      <div class="issgrp-h ${cls}">${label} (${arr.length})</div>
      ${arr.map(i=>`<div class="issrow"><div class="issmsg">${esc(i.message||i.code||"issue")}</div>
        ${(i.attributes&&i.attributes.length)?`<div class="issattr">fields: ${i.attributes.map(a=>'<code>'+esc(a)+'</code>').join(", ")}</div>`:""}</div>`).join("")}
    </div>`:"";
  return statusLine+`<div class="issuesbox warn">
    <b>⚠ Amazon is reporting issues on this listing</b> — the text below is <b>Amazon's own wording, pulled live from the SP-API</b> (not our guess). It's what causes the red status.
    ${typeof howWorks==="function"?howWorks('opt_fetch'):""}
    ${renderList(errs,"err","Errors (must fix)")}
    ${renderList(warns,"warn","Warnings / recommended")}
    <div style="margin-top:8px"><button class="suggestbtn" onclick="optDiagnose()"><i class="ti ti-stethoscope"></i> Suggest fixes with AI</button> <span id="opt_diagstatus" class="cc"></span></div>
    ${typeof howWorks==="function"?howWorks('opt_diagnose'):""}
    <div id="opt_diagresults"></div>
  </div>`;
}
async function optDiagnose(){
  const st=document.getElementById("opt_diagstatus");
  if(st) st.innerHTML='<span class="genspin"></span> Asking Amazon what\u2019s wrong and drafting fixes…';
  try{
    const j=await (await fetch("/optimize/diagnose_fill",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT?CUR_ACCOUNT.id:"", sku:OPT_CURRENT.sku, marketplace:WS_MARKET})})).json();
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; return; }
    const box=document.getElementById("opt_diagresults");
    if(!j.flagged || !j.flagged.length){
      if(st) st.innerHTML='';
      if(box) box.innerHTML='<div class="cc" style="margin-top:8px">'+esc(j.note||"No attribute-level issues to fix.")+'</div>';
      return;
    }
    const sugg=j.suggestions||{};
    let rows=j.flagged.map(f=>{
      const s=sugg[f.attribute]||{};
      const val=(s.value!==undefined&&s.value!==null)?s.value:"";
      const note=s.note||"";
      const needs=(s.value===null||s.value===undefined)&&note;
      return `<tr>
        <td class="k"><code>${esc(f.attribute)}</code><div class="cc" style="font-size:10px">${esc(f.message||"")}</div></td>
        <td class="v">
          ${needs?`<div class="cc" style="color:#e3b768">⚠ ${esc(note)} (you'll need to provide this)</div>`:""}
          <input class="ed optfix" data-attr="${esc(f.attribute)}" value="${esc(String(val))}" placeholder="${esc(note||'value')}">
          <label class="cc" style="display:flex;align-items:center;gap:5px;margin-top:3px"><input type="checkbox" class="optfixchk" data-attr="${esc(f.attribute)}" ${val?'checked':''}> apply this fix</label>
        </td></tr>`;
    }).join("");
    if(box) box.innerHTML=`<div style="margin-top:10px"><div class="optsec">AI-suggested values — these are <b>estimates the AI inferred</b>, not from Amazon. Review &amp; correct each before applying.</div>
      <table class="kv">${rows}</table>
      <div class="cc" style="margin:6px 0">These get added to your approved changes. Simple fields push fine; <b>dimensions with units are safest filled in Seller Central</b> (the form structures them correctly). Tick only what you want.</div>
      <button class="primary" onclick="optApplyFixes()"><i class="ti ti-check"></i> Add ticked fixes to changes</button></div>${typeof howWorks==="function"?howWorks('opt_push'):""}`;
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ Drafted '+Object.keys(sugg).length+' suggestion(s)</span>';
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">Error: '+esc(String(e))+'</span>'; }
}
function optApplyFixes(){
  _captureOptEditor();
  const st=OPT_EDIT_STATE||(OPT_EDIT_STATE={});
  st.attrs=st.attrs||{};
  let n=0;
  document.querySelectorAll(".optfixchk:checked").forEach(chk=>{
    const attr=chk.dataset.attr;
    const inp=document.querySelector('.optfix[data-attr="'+CSS.escape(attr)+'"]');
    if(inp && inp.value.trim()){ st.attrs[attr]=inp.value.trim(); n++; }
  });
  toast(n+" fix(es) added to your changes. Review changes to approve & push.");
}
function renderOptEditor(j){
  OPT_CURRENT=j;
  const f=j.fields||{};
  const attrs=j.raw_attributes||{};
  const s=OPT_EDIT_STATE||{};   // saved edits (incl. AI copy) take precedence over original
  const vTitle = (s.title!==undefined?s.title:(f.title||""));
  const vBullets = (s.bullets!==undefined?s.bullets:(f.bullets||[]));
  const vDesc = (s.description!==undefined?s.description:(f.description||""));
  const vPrice = (s.price!==undefined?s.price:(f.price||""));
  const vImg = (s.main_image!==undefined?s.main_image:(f.main_image||""));
  const bulletsText=(vBullets||[]).join("\n");
  const img=vImg;
  // core fields shown prominently
  let core=`
    <table class="kv">
      <tr><td class="k">Title</td><td class="v"><textarea class="ed" id="opt_title" rows="2">${esc(vTitle)}</textarea></td></tr>
      <tr><td class="k">Bullets <span class="cc">(one per line)</span></td><td class="v"><textarea class="ed" id="opt_bullets" rows="5">${esc(bulletsText)}</textarea></td></tr>
      <tr><td class="k">Description</td><td class="v"><textarea class="ed" id="opt_description" rows="4">${esc(vDesc)}</textarea></td></tr>
      <tr><td class="k">Price</td><td class="v"><input class="ed" id="opt_price" value="${esc(vPrice)}"></td></tr>
      <tr><td class="k">Main image</td><td class="v">
        ${img?`<img src="${esc(img)}" style="max-width:120px;border-radius:8px;border:1px solid var(--line);display:block;margin-bottom:6px">`:'<span class="cc">no image</span>'}
        <input class="ed" id="opt_main_image" value="${esc(img)}"></td></tr>
    </table>`;
  // ALL other attributes — full editable list, like Amazon's edit page
  const coreKeys=new Set(["item_name","bullet_point","product_description","purchasable_offer",
                          "main_product_image_locator"]);
  let allRows="";
  const savedAttrs=s.attrs||{};
  const keys=Object.keys(attrs).filter(k=>!coreKeys.has(k)).sort();
  for(const k of keys){
    const val=(savedAttrs[k]!==undefined?savedAttrs[k]:_optAttrToText(attrs[k]));
    const isImg=/image_locator/i.test(k);
    const long=val.length>60;
    allRows+=`<tr><td class="k">${esc(k)}</td><td class="v">`+
      (isImg&&val?`<img src="${esc(val.split(' | ')[0])}" style="max-width:70px;border-radius:6px;border:1px solid var(--line);display:block;margin-bottom:4px">`:"")+
      (long?`<textarea class="ed optattr" data-attr="${esc(k)}" rows="2">${esc(val)}</textarea>`
           :`<input class="ed optattr" data-attr="${esc(k)}" value="${esc(val)}">`)+
      `</td></tr>`;
  }
  document.getElementById("optbody").innerHTML=`
    <div class="cc" style="margin-bottom:10px">Editing a <b>LIVE</b> listing on <b>${esc(CUR_ACCOUNT?CUR_ACCOUNT.label:"")}</b> · ${esc(j.marketplace)} · ASIN ${esc(j.asin||"")} · SKU ${esc(j.sku)} · type <b>${esc(j.product_type||"")}</b>. <b>Nothing is sent to Amazon</b> until you review and approve each field.</div>
    ${optIssuesPanel(j)}
    <div class="srcbox">
      <div class="optsec" style="margin-bottom:6px"><i class="ti ti-robot"></i> Custom AI rewrite</div>
      <div class="cc" style="margin-bottom:8px">Tell the AI exactly what you want (e.g. <i>"don't put any brand in the title, focus on iPhone 17 Pro fit, make it sound premium"</i>). Optionally paste the real product's eBay/Amazon link so it knows the actual product. Compliance &amp; IP rules stay applied.</div>
      <textarea class="ed" id="opt_src_instruction" rows="2" placeholder="What do you want? e.g. rewrite without my brand name, emphasise durability, keep it under 150 chars…" style="margin-bottom:6px"></textarea>
      <input class="ed" id="opt_src_ebay" placeholder="eBay product URL (optional)" style="margin-bottom:6px">
      <input class="ed" id="opt_src_amazon" placeholder="Amazon product URL (optional)" style="margin-bottom:8px">
      <button class="suggestbtn" onclick="optRewriteFromSource()"><i class="ti ti-wand"></i> Rewrite with these instructions</button>
      <span id="opt_srcstatus" class="cc" style="margin-left:8px"></span>
      ${typeof howWorks==="function"?howWorks('opt_rewrite'):""}
    </div>
    <div class="optsec">Core listing fields</div>
    ${core}
    <details class="optall"><summary>All other attributes (${keys.length}) — required &amp; optional, exactly as Amazon has them</summary>
      <table class="kv">${allRows||'<tr><td class="cc">No additional attributes returned.</td></tr>'}</table>
    </details>
    <div style="margin-top:14px;display:flex;gap:8px">
      <button class="suggestbtn" onclick="optAISuggest()"><i class="ti ti-wand"></i> AI optimize copy</button>
      <button class="primary" onclick="optReview()"><i class="ti ti-eye"></i> Review changes before pushing</button>
      <button onclick="closeOpt()">Cancel</button>
    </div>
    <div id="opt_aistatus" class="cc" style="margin-top:6px"></div>`;
}
let OPT_BRAND_HINT = "";
async function optRewriteFromSource(){
  const eb=(document.getElementById("opt_src_ebay")||{}).value||"";
  const az=(document.getElementById("opt_src_amazon")||{}).value||"";
  const ins=(document.getElementById("opt_src_instruction")||{}).value||"";
  const st=document.getElementById("opt_srcstatus");
  if(!eb.trim() && !az.trim() && !ins.trim()){ if(st) st.textContent="Type an instruction and/or paste a product link first."; return; }
  _captureOptEditor();
  if(st) st.innerHTML='<span class="genspin"></span> AI is rewriting per your instructions (can take 20–40s)…';
  try{
    const j=await (await fetch("/optimize/from_source",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT.id, ebay_url:eb.trim(), amazon_url:az.trim(), instruction:ins.trim(),
        product_type:OPT_CURRENT.product_type,
        current:{title:(document.getElementById("opt_title")||{}).value,
                 bullets:(document.getElementById("opt_bullets")||{}).value,
                 description:(document.getElementById("opt_description")||{}).value}})})).json();
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; return; }
    const s=j.suggestion||{};
    if(s.title) document.getElementById("opt_title").value=s.title;
    if(Array.isArray(s.bullets)&&s.bullets.length) document.getElementById("opt_bullets").value=s.bullets.join("\n");
    if(s.description) document.getElementById("opt_description").value=s.description;
    _captureOptEditor();
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ Rewritten per your instructions. Review &amp; edit, then Review changes to approve.</span>';
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">Error: '+esc(String(e))+'</span>'; }
}
async function optAISuggest(){
  const st=document.getElementById("opt_aistatus");
  if(st) st.innerHTML='<span class="genspin"></span> AI optimizing title, bullets, description…';
  try{
    const j=await (await fetch("/ask",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({messages:[{role:"user",text:"Optimize this Amazon listing's title, bullets and description for conversions and SEO. Return ONLY JSON {\"title\":\"..\",\"bullets\":[\"..\"],\"description\":\"..\"} no preamble."}],
        context:{title:(document.getElementById("opt_title")||{}).value,bullets:(document.getElementById("opt_bullets")||{}).value,description:(document.getElementById("opt_description")||{}).value,product_type:OPT_CURRENT.product_type}})})).json();
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#e0696b">AI failed: '+esc(j.error||"")+'</span>'; return; }
    let txt=(j.reply||"").trim().replace(/^```json/i,'').replace(/```$/,'').trim();
    let s=JSON.parse(txt);
    if(s.title) document.getElementById("opt_title").value=s.title;
    if(Array.isArray(s.bullets)&&s.bullets.length) document.getElementById("opt_bullets").value=s.bullets.join("\n");
    if(s.description) document.getElementById("opt_description").value=s.description;
    _captureOptEditor();   // save AI copy into state so it survives Back-to-edit / Review
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ AI suggestions applied — they\u2019re saved. Click Review changes to approve.</span>';
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">Could not parse AI: '+esc(String(e))+'</span>'; }
}
let OPT_EDIT_STATE = null;   // persists edited values across editor<->review
function _captureOptEditor(){
  // read the editor inputs WHILE they exist and save into OPT_EDIT_STATE
  const f=OPT_CURRENT.fields||{};
  const attrs=OPT_CURRENT.raw_attributes||{};
  const gv=(id)=>{ const el=document.getElementById(id); return el?(el.value||""):null; };
  const bv=gv("opt_bullets");
  const st={
    title:   gv("opt_title"),
    bullets: bv===null?null:bv.split("\n").map(s=>s.trim()).filter(Boolean),
    description: gv("opt_description"),
    price:   gv("opt_price"),
    main_image: gv("opt_main_image"),
    attrs:{}
  };
  document.querySelectorAll(".optattr").forEach(el=>{ st.attrs[el.dataset.attr]=(el.value||"").trim(); });
  // merge into existing state so values persist even if some inputs are absent
  OPT_EDIT_STATE = OPT_EDIT_STATE || {};
  if(st.title!==null) OPT_EDIT_STATE.title=st.title.trim();
  if(st.bullets!==null) OPT_EDIT_STATE.bullets=st.bullets;
  if(st.description!==null) OPT_EDIT_STATE.description=st.description.trim();
  if(st.price!==null) OPT_EDIT_STATE.price=st.price.trim();
  if(st.main_image!==null) OPT_EDIT_STATE.main_image=st.main_image.trim();
  OPT_EDIT_STATE.attrs = Object.assign(OPT_EDIT_STATE.attrs||{}, st.attrs);
  return OPT_EDIT_STATE;
}
function _optEdited(){
  const f=OPT_CURRENT.fields||{};
  const attrs=OPT_CURRENT.raw_attributes||{};
  // if the editor is on screen, refresh saved state from it first
  if(document.getElementById("opt_title")) _captureOptEditor();
  const s=OPT_EDIT_STATE||{};
  const ed={
    title:{old:f.title||"", new:(s.title!==undefined?s.title:(f.title||""))},
    bullets:{old:(f.bullets||[]), new:(s.bullets!==undefined?s.bullets:(f.bullets||[]))},
    description:{old:f.description||"", new:(s.description!==undefined?s.description:(f.description||""))},
    price:{old:String(f.price||""), new:(s.price!==undefined?s.price:String(f.price||""))},
    main_image:{old:f.main_image||"", new:(s.main_image!==undefined?s.main_image:(f.main_image||""))},
  };
  const savedAttrs=s.attrs||{};
  Object.keys(attrs).forEach(k=>{
    if(["item_name","bullet_point","product_description","purchasable_offer","main_product_image_locator"].includes(k)) return;
    const oldVal=_optAttrToText(attrs[k]);
    const newVal=(savedAttrs[k]!==undefined?savedAttrs[k]:oldVal);
    ed["attr:"+k]={old:oldVal, new:newVal, _isAttr:true};
  });
  return ed;
}
function optReview(){
  const ed=_optEdited();
  let rows="";
  const changed=[];
  for(const [field,val] of Object.entries(ed)){
    const oldS=Array.isArray(val.old)?val.old.join(" | "):String(val.old);
    const newS=Array.isArray(val.new)?val.new.join(" | "):String(val.new);
    const isChanged = oldS!==newS;
    if(isChanged) changed.push(field);
    rows+=`<div class="optdiff ${isChanged?'chg':'same'}">
      <label class="optcheck"><input type="checkbox" id="optapprove_${field}" ${isChanged?'':'disabled'} onchange="optCountApproved()"> <b>${esc(field)}</b> ${isChanged?'<span class="chgflag">changed</span>':'<span class="cc">unchanged</span>'}</label>
      <div class="optold"><span class="cc">Current (live):</span> ${esc(oldS)||'<span class="cc">(empty)</span>'}</div>
      <div class="optnew"><span class="cc">New:</span> ${esc(newS)||'<span class="cc">(empty)</span>'}</div>
    </div>`;
  }
  document.getElementById("optbody").innerHTML=`
    <div class="cc" style="margin-bottom:10px"><b>Review every change.</b> Only the fields you tick will be sent to Amazon. Unticked fields stay exactly as they are on the live listing.</div>
    ${rows}
    <div style="margin-top:14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;position:sticky;bottom:0;background:var(--panel);padding:12px 0;border-top:1px solid var(--line)">
      <button id="optpushbtn" disabled onclick="optPush()" style="background:#3a1d1d;border:1px solid #5c2b2b;color:#e0a3a3;padding:9px 16px;border-radius:8px;cursor:pointer;font-weight:600">Push approved fields to LIVE Amazon</button>
      <span id="optapprovedcount" class="cc">0 fields approved</span>
      <button onclick="renderOptEditor(OPT_CURRENT)">← Back to edit</button>
      <button onclick="closeOpt()">Cancel</button>
    </div>`;
  optCountApproved();
}
function optCountApproved(){
  const ed=_optEdited();
  let n=0;
  for(const field of Object.keys(ed)){
    const cb=document.getElementById("optapprove_"+field);
    if(cb&&cb.checked) n++;
  }
  const lbl=document.getElementById("optapprovedcount"); if(lbl) lbl.textContent=n+" field"+(n===1?"":"s")+" approved";
  const btn=document.getElementById("optpushbtn"); if(btn) btn.disabled=(n===0);
  if(btn){ btn.style.opacity=(n===0)?".5":"1"; }
}
async function optPush(){
  const ed=_optEdited();
  const changes={};
  for(const [field,val] of Object.entries(ed)){
    const cb=document.getElementById("optapprove_"+field);
    if(cb&&cb.checked){ changes[field]=val.new; }
  }
  const fieldList=Object.keys(changes);
  if(!fieldList.length){ toast("Tick at least one changed field to push."); return; }
  if(!confirm("PUSH TO LIVE AMAZON\n\nAccount: "+(CUR_ACCOUNT?CUR_ACCOUNT.label:"")+"\nASIN: "+(OPT_CURRENT.asin||"")+"\nSKU: "+OPT_CURRENT.sku+"\nMarketplace: "+OPT_CURRENT.marketplace+"\n\nFields being changed: "+fieldList.join(", ")+"\n\nThis updates the LIVE listing customers see. Proceed?")) return;
  const btn=document.getElementById("optpushbtn"); if(btn){ btn.disabled=true; btn.textContent="Pushing…"; }
  try{
    const j=await (await fetch("/optimize/push",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT?CUR_ACCOUNT.id:"",sku:OPT_CURRENT.sku,marketplace:OPT_CURRENT.marketplace,
        product_type:OPT_CURRENT.product_type,changes:changes,confirmed:true})})).json();
    if(j.ok){
      document.getElementById("optbody").innerHTML='<div class="gendiag ok">✓ Submitted to Amazon ('+esc(j.status||"accepted")+'). Pushed: '+esc((j.pushed_fields||[]).join(", "))+'.<div class="cc" style="margin-top:6px">Amazon may take time to reflect changes. Use Sync to refresh.</div></div>';
    } else {
      let issues=(j.issues||[]).map(x=>(x.message||JSON.stringify(x))).join("; ");
      document.getElementById("optbody").innerHTML='<div class="gendiag bad">✗ Amazon rejected the change: '+esc(j.error||issues||j.status||"unknown")+'</div><button onclick="renderOptEditor(OPT_CURRENT)" style="margin-top:10px">← Back to edit</button>';
    }
  }catch(e){ if(btn){btn.disabled=false;btn.textContent="Push approved fields to LIVE Amazon";} toast("Push error: "+e); }
}
function closeOpt(){ document.getElementById("optmodal").classList.remove("open"); OPT_CURRENT=null; }

// ============ IMAGE STUDIO (main image generation: recipes + creative + batch) ============
let STUDIO = { skus: [], items: [], brand: "", recipes: [], results: {} };
function _itemForSku(sku){ return (LIVE_ITEMS||[]).find(x=>String(x.sku)===String(sku)) || (ROWS||[]).find(x=>String(x.sku)===String(sku)); }
function _refImgForItem(it){
  if(!it){ return (typeof STUDIO!=='undefined' && STUDIO.manualRef) || ""; }
  var direct = it.img || it.main_image || it.image || "";
  if(direct) return direct;
  // draft rows store images inside the attributes JSON (main_product_image_locator)
  try{
    var imgs=_rowImages(it);
    if(imgs && imgs.length) return imgs[0];
  }catch(e){}
  // brand/source image, then a manually-provided reference (upload/URL) as last resort
  return it.source_image || it.src_image || (typeof STUDIO!=='undefined' && STUDIO.manualRef) || "";
}
async function openStudioSingle(sku){
  const it=_itemForSku(sku);
  STUDIO={ skus:[String(sku)], items: it?[it]:[], brand: (CUR_ACCOUNT&&CUR_ACCOUNT.brands&&CUR_ACCOUNT.brands.length?CUR_ACCOUNT.brands[0]:(CUR_ACCOUNT?CUR_ACCOUNT.label:"")), recipes:[], results:{} };
  document.getElementById("imgstudio").classList.add("open");
  await loadRecipes();
  renderStudio();
  studioLoadModels();
  loadStudioInstructions();
}
async function openStudioBatch(){
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some products first (tick the cards)."); return; }
  const items=skus.map(_itemForSku).filter(Boolean);
  STUDIO={ skus:skus.map(String), items:items, brand:(CUR_ACCOUNT&&CUR_ACCOUNT.brands&&CUR_ACCOUNT.brands.length?CUR_ACCOUNT.brands[0]:(CUR_ACCOUNT?CUR_ACCOUNT.label:"")), recipes:[], results:{} };
  document.getElementById("imgstudio").classList.add("open");
  await loadRecipes();
  renderStudio();
  studioLoadModels();
  loadStudioInstructions();
}
function closeStudio(){ document.getElementById("imgstudio").classList.remove("open"); }
async function loadRecipes(){
  try{
    const j=await (await fetch("/recipes/list",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({brand:STUDIO.brand})})).json();
    if(j.ok){ STUDIO.recipes=j.recipes||[]; STUDIO.all_recipes=j.all_recipes||[]; }
  }catch(e){}
}
// known strengths of popular image models (shown as guidance next to the picker)
const IMG_MODEL_NOTES=[
  {match:/seedream/i, note:"★ Best for product shots & packaging, native up to 4K, strong text — top pick for main images"},
  {match:/ideogram/i, note:"★ Best text rendering — ideal for secondary images & A+ with benefit text"},
  {match:/imagen.*ultra|imagen-4/i, note:"Most photorealistic — great for hero shots (pricier)"},
  {match:/flux.*2|flux\.2/i, note:"Strong photorealism & reference preservation (good for keeping your product)"},
  {match:/nano-banana-2|gemini-3.*image|nano banana 2/i, note:"Fast, native 2K, good all-round"},
  {match:/nano-banana|gemini-2.5-flash-image/i, note:"Fast & cheap, ~1024px (may need upscaling for Amazon)"},
  {match:/gpt-image|gpt-5-image/i, note:"Top-ranked quality, good text & editing"},
  {match:/recraft/i, note:"Design-first, good for clean e-commerce mockups & vectors"},
];
function _imgModelNote(id){
  for(const m of IMG_MODEL_NOTES){ if(m.match.test(id||"")) return m.note; }
  return "";
}
async function studioLoadModels(){
  let s=null;
  try{ s=await (await fetch('/ai/settings')).json(); }catch(e){}
  if(!s||!s.ok){ return; }
  // admin gate for the "how it works" panels
  if(s.admin){ window.LOGIC_VISIBLE = !!s.admin.show_logic && !s.admin.preview_as_user; }
  const tsel=document.getElementById("studio_text_model");
  const isel=document.getElementById("studio_image_model");
  if(tsel){
    tsel.innerHTML=(s.text_models||[]).map(m=>`<option value="${esc(m.id)}" ${m.id===s.select.prompt_enhance?'selected':''}>${esc(m.name||m.id)}</option>`).join("")||'<option value="">no text models</option>';
    window.AI_TEXT=tsel.value;
    tsel.onchange=()=>{ window.AI_TEXT=tsel.value; };
  }
  if(isel){
    isel.innerHTML=(s.image_models||[]).map(m=>`<option value="${esc(m.id)}" ${m.id===s.select.image_generate?'selected':''}>${esc(m.name||m.id)}</option>`).join("")||'<option value="">no image models</option>';
    window.AI_IMAGE=isel.value;
    isel.onchange=()=>{ window.AI_IMAGE=isel.value; studioModelHint(); };
  }
  // text hint: which models are good for the product-reading job
  const th=document.getElementById("studio_text_hint");
  if(th) th.innerHTML="Tip: a strong vision model (e.g. one that can read images well) reads your label text more accurately. This AI examines your product and writes the detailed prompt.";
  studioModelHint();
}
function studioModelHint(){
  const isel=document.getElementById("studio_image_model");
  const ih=document.getElementById("studio_image_hint");
  if(isel&&ih){ const note=_imgModelNote(isel.value); ih.innerHTML=note?('<span style="color:#7fd99a">'+esc(note)+'</span>'):'<span class="cc">Pick the image model. Models that support reference images keep your product faithful.</span>'; }
}
function renderStudio(){
  const body=document.getElementById("studiobody");
  const n=STUDIO.skus.length;
  const batch = n>1;
  const recipeOpts=(STUDIO.recipes||[]).map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join("");
  const otherRecipes=(STUDIO.all_recipes||[]).filter(r=>!(STUDIO.recipes||[]).some(x=>x.id===r.id));
  const otherOpts=otherRecipes.map(r=>`<option value="${esc(r.id)}">${esc(r.name)} — ${esc(r.brand)}</option>`).join("");
  body.innerHTML=`
    <div class="cc" style="margin-bottom:10px">${batch?('<b>Batch:</b> '+n+' products selected — the chosen treatment applies to each, using each product\u2019s own image.'):'Generating a main image for <b>'+esc(STUDIO.skus[0])+'</b>.'} Brand: <b>${esc(STUDIO.brand||'(none)')}</b></div>
    <div class="studiomodels">
      <div class="smodel">
        <label class="cc">Prompt AI (reads your product &amp; writes the prompt)</label>
        <select id="studio_text_model" class="ed"><option value="">Loading…</option></select>
        <div class="cc smodelhint" id="studio_text_hint"></div>
      </div>
      <div class="smodel">
        <label class="cc">Image AI (generates the image)</label>
        <select id="studio_image_model" class="ed" onchange="studioModelHint()"><option value="">Loading…</option></select>
        <div class="cc smodelhint" id="studio_image_hint"></div>
      </div>
      <div class="smodel">
        <label class="cc">Product fidelity (how closely to keep your exact product)</label>
        <select id="studio_fidelity" class="ed">
          <option value="high" selected>High — keep my product as exact as possible (recommended)</option>
          <option value="medium">Medium — balanced</option>
          <option value="creative">Creative — allow more artistic freedom</option>
        </select>
        <div class="cc smodelhint">Higher fidelity keeps the shape, colours and proportions closest to your real product. Note: how well this works depends heavily on the image model — reference-preserving models (Seedream, FLUX) keep the product far better than Gemini Flash.</div>
      </div>
      <div class="smodel" style="grid-column:1/-1">
        <label class="cc"><i class="ti ti-message-2-cog"></i> Your standing instructions (the AI remembers these for every image)</label>
        <textarea id="studio_custom_instructions" class="ed" rows="2" placeholder="e.g. Always use a pure white background. Keep our logo in the top-left. Never include people. Warm lighting."></textarea>
        <div style="display:flex;gap:8px;align-items:center;margin-top:5px;flex-wrap:wrap">
          <button class="ib" onclick="saveStudioInstructions()"><i class="ti ti-device-floppy"></i> Save instructions</button>
          <span class="cc" id="studio_ci_status" style="font-size:11px"></span>
        </div>
        <div class="cc smodelhint">These are added on top of the strategist's creative brief for every image you generate or edit — so your rules are always applied without retyping.</div>
      </div>
    </div>
    <div class="studiotabs">
      <button class="stab on" data-tab="recipe" onclick="studioTab('recipe')">Use a saved recipe (templated)</button>
      <button class="stab" data-tab="creative" onclick="studioTab('creative')">Creative (3 variations)</button>
      <button class="stab" data-tab="source" onclick="studioTab('source')">Main image (clean white bg)</button>
      <button class="stab" data-tab="secondary" onclick="studioTab('secondary')">Secondary images</button>
      <button class="stab" data-tab="aplus" onclick="studioTab('aplus')">A+ Content</button>
      <button class="stab" data-tab="recipes_manage" onclick="studioTab('recipes_manage')">Manage recipes</button>
    </div>
    <div id="studio_recipe" class="studiopane">
      ${recipeOpts||otherOpts ? `
        <label class="cc">Recipe</label>
        <select id="studio_recipe_sel" class="ed">${recipeOpts}${otherOpts?('<optgroup label="Other brands">'+otherOpts+'</optgroup>'):''}</select>
        <div class="cc" style="margin:8px 0">The recipe\u2019s saved instructions are applied to ${batch?'each selected product':'this product'}; the product itself stays identical.</div>
        <button class="primary" onclick="studioRun('recipe')"><i class="ti ti-sparkles"></i> ${batch?('Generate for all '+n+' products'):'Generate main image'}</button>
      ` : `<div class="cc">No recipes yet for <b>${esc(STUDIO.brand||'this brand')}</b>. Create one under <b>Manage recipes</b> — a recipe is a saved treatment (template image + the changes you want) that you can reuse on any product.</div>`}
      ${typeof howWorks==="function"?(howWorks('recipes')+howWorks('media')):""}
    </div>
    <div id="studio_creative" class="studiopane" style="display:none">
      <div class="ideabox">
        <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-bulb"></i> Option A — Let the AI strategist invent the ideas</div>
        <div class="cc" style="margin-bottom:8px">Instead of you supplying the idea, the AI thinks like a top Amazon conversion strategist <i>and</i> like your customer — what stops them scrolling, what makes them feel "this is the one" — then proposes concrete photo concepts for <b>this</b> product. You pick which to generate. (Main images stay pure white; creativity is in angle, lighting &amp; touches like droplets.)</div>
        <label class="cc" style="display:block;margin-bottom:3px">Instructions for the strategist (optional, not saved) — e.g. "don't show pets", "show the product in only some images, not all"</label>
        <textarea id="strat_instr_main" class="ed" rows="2" placeholder='e.g. no people; show one close-up of the texture; keep it minimal' style="margin-bottom:8px"></textarea>
        <button class="primary" onclick="studioStrategize('main')"><i class="ti ti-sparkles"></i> Suggest image ideas</button>
        <button class="primary" onclick="studioStrategize('main', true)" style="margin-left:6px" title="Ask the strategist for ideas AND generate them all automatically — no manual picking"><i class="ti ti-bolt"></i> Suggest &amp; auto-generate${batch?(' ('+n+' products)'):''}</button>
        <span id="studio_strat_status" class="cc" style="margin-left:8px"></span>
        ${howWorks('strategist')}
        <div id="studio_concepts" style="margin-top:10px"></div>
      </div>
      <div class="ordiv"><span>OR</span></div>
      <div class="buildbox">
        <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-adjustments"></i> Option B — Use the 3 ready-made variations</div>
        <div class="cc" style="margin-bottom:8px">Generates 3 fixed treatments — straight-on hero, flattering angle, and a creative "personality" shot — all on pure white, product kept identical.</div>
        <label class="cc">Optional inspiration (a link, image URL, or a few words)</label>
        <input id="studio_inspo" class="ed" placeholder="e.g. https://… or 'bright airy bathroom, marble surface'">
        <div style="margin-top:10px"><button class="primary" onclick="studioRun('creative')"><i class="ti ti-sparkles"></i> ${batch?('Generate 3 variations for each of '+n+' products'):'Generate 3 variations'}</button></div>
        ${howWorks('ready3')}
      </div>
    </div>
    <div id="studio_recipes_manage" class="studiopane" style="display:none">${recipesManageHTML()}</div>
    <div id="studio_secondary" class="studiopane" style="display:none">${secondaryPaneHTML(batch,n)}</div>
    <div id="studio_source" class="studiopane" style="display:none">${sourcePaneHTML(batch,n)}</div>
    <div id="studio_aplus" class="studiopane" style="display:none">${aplusPaneHTML(batch,n)}</div>
    <div id="studio_progress" style="margin-top:14px"></div>
    <div id="studio_results" class="studiogrid" style="margin-top:14px"></div>`;
}
function sourcePaneHTML(batch,n){
  // default: if this workspace has brand profiles/CSV products, assume 'brand' (keep logo);
  // otherwise assume 'competitor' (dropshipping/scrape -> remove logo)
  const looksBrand = !!(STUDIO.brand && STUDIO.brand.trim());
  return `
    <div class="cc" style="margin-bottom:8px">Turn the <b>source product photo</b> (from eBay/Amazon, or your brand's own upload) into a clean Amazon main image — <b>pure white background, product kept identical</b>. ${batch?('Applies to each of '+n+' selected products.'):''}</div>
    ${batch?'':refPickerHTML()}
    <div class="secrow">
      <label class="cc">Where is this image from?</label>
      <select id="src_source" class="ed" onchange="srcSourceChange()">
        <option value="competitor" ${looksBrand?'':'selected'}>Competitor / eBay / Amazon scrape — remove their logo</option>
        <option value="brand" ${looksBrand?'selected':''}>My brand's own product (CSV/upload) — keep my product &amp; logo</option>
      </select>
    </div>
    <div id="src_brandopts" style="margin-top:8px;${looksBrand?'':'display:none'}">
      <label class="seccheck"><input type="checkbox" id="src_preserve_logo" checked> Preserve product <b>and logo</b> (keep my branding exactly)</label>
    </div>
    <div id="src_competitornote" class="cc" style="margin-top:8px;font-size:11px;${looksBrand?'display:none':''}">
      Any brand logo found on the product will be cleanly removed (blended to match the surface — no replacement). If the photo has no logo, the product is kept as-is.
    </div>
    <label class="cc" style="margin-top:10px;display:block">Optional — any other edits you want</label>
    <textarea id="src_instruction" class="ed" rows="2" placeholder="e.g. straighten the bottle, brighten it, remove the reflection, centre it"></textarea>
    <div style="margin-top:10px"><button class="primary" onclick="studioRunSource()"><i class="ti ti-wand"></i> ${batch?('Clean source image for all '+n+' products'):'Clean &amp; generate from source'}</button></div>
    ${howWorks('source')}`;
}
// Reference-image picker: shows the product's source images (eBay first) so the
// user can choose which one to use as the AI reference. If none is picked, the
// first (auto-picked "cleanest") is used. Choice is stored in STUDIO.chosenRef.
function refPickerHTML(){
  const sku = (STUDIO.skus&&STUDIO.skus[0])||"";
  const it = _itemForSku(sku);
  let imgs=[];
  try{ imgs=_rowImages(it)||[]; }catch(e){ imgs=[]; }
  if(!imgs.length){
    const r=_refImgForItem(it); if(r) imgs=[r];
  }
  if(!imgs.length){
    // No auto-found source image -> let the user PROVIDE one (upload a file or
    // paste a URL) instead of falling back to text-only generation.
    const manual = STUDIO.manualRef || "";
    return `
      <div class="refpicker">
        <div class="cc" style="margin-bottom:6px;color:#e3b768">No source image was found for this product automatically. Add one below so the AI can keep your real product (otherwise it generates from the text description only).</div>
        <div class="secrow" style="gap:8px;align-items:center;flex-wrap:wrap">
          <button class="ib" onclick="document.getElementById('manual_ref_file').click()"><i class="ti ti-upload"></i> Upload product image</button>
          <span class="cc" style="font-size:11px">or paste an image URL:</span>
          <input id="manual_ref_url" class="ed" style="min-width:220px;flex:1" placeholder="https://…/product.jpg" value="${manual && /^https?:/i.test(manual)?esc(manual):''}" onchange="setManualRefUrl(this.value)">
        </div>
        <input type="file" id="manual_ref_file" accept="image/*" style="display:none" onchange="onManualRefFile(this)">
        ${manual?`<div class="refrow" style="margin-top:8px"><div class="refthumb on"><img src="${esc(manual)}" loading="lazy"><span class="refbadge">reference</span></div></div>`:''}
      </div>`;
  }
  // auto-pick the first as default reference if not chosen yet
  if(!STUDIO.chosenRef || imgs.indexOf(STUDIO.chosenRef)<0){ STUDIO.chosenRef = imgs[0]; }
  const thumbs = imgs.map((u,i)=>`
    <div class="refthumb${u===STUDIO.chosenRef?' on':''}" onclick="pickRef('${esc(u)}')" title="Use this image as the AI reference">
      <img src="${esc(u)}" loading="lazy">
      ${u===STUDIO.chosenRef?'<span class="refbadge">reference</span>':''}
    </div>`).join("");
  return `
    <div class="refpicker">
      <div class="cc" style="margin-bottom:6px"><b>Choose the reference image</b> — tap the eBay/source photo that best shows the product (cleanest, least text). The first is auto-selected.</div>
      <div class="refrow">${thumbs}</div>
    </div>`;
}
function pickRef(u){
  STUDIO.chosenRef = u;
  // re-render just the picker (cheap: re-render the whole source pane)
  const pane=document.getElementById("studio_source");
  if(pane){ const batch=(STUDIO.skus||[]).length>1; pane.innerHTML=sourcePaneHTML(batch,(STUDIO.skus||[]).length); }
}
function _rerenderSourcePane(){
  const pane=document.getElementById("studio_source");
  if(pane){ const batch=(STUDIO.skus||[]).length>1; pane.innerHTML=sourcePaneHTML(batch,(STUDIO.skus||[]).length); }
}
function setManualRefUrl(u){
  u=(u||"").trim();
  if(!u){ return; }
  STUDIO.manualRef=u; STUDIO.chosenRef=u;
  _rerenderSourcePane();
}
function onManualRefFile(input){
  const f=input && input.files && input.files[0];
  if(!f) return;
  if(!/^image\//.test(f.type)){ toast("Please choose an image file."); return; }
  const rd=new FileReader();
  rd.onload=function(){
    // store as a data URL — the generator accepts data URLs as the reference
    STUDIO.manualRef=rd.result; STUDIO.chosenRef=rd.result;
    _rerenderSourcePane();
    toast("Reference image added ✓");
  };
  rd.onerror=function(){ toast("Could not read that file."); };
  rd.readAsDataURL(f);
}
function srcSourceChange(){
  const v=(document.getElementById("src_source")||{}).value;
  const bo=document.getElementById("src_brandopts");
  const cn=document.getElementById("src_competitornote");
  if(bo) bo.style.display = v==="brand"?"block":"none";
  if(cn) cn.style.display = v==="competitor"?"block":"none";
}
async function studioRunSource(){
  const source=(document.getElementById("src_source")||{}).value||"competitor";
  const preserveLogo=(document.getElementById("src_preserve_logo")||{checked:true}).checked;
  const instr=(document.getElementById("src_instruction")||{}).value||"";
  const fid=(document.getElementById("studio_fidelity")||{}).value||"high";
  const single=(STUDIO.skus||[]).length===1;
  let jobs=[];
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku);
    // single product: honour the reference the user picked (eBay picker) OR a
    // manually-provided upload/URL; batch: each product uses its own image.
    const ref=(single && (STUDIO.chosenRef||STUDIO.manualRef)) ? (STUDIO.chosenRef||STUDIO.manualRef) : _refImgForItem(it);
    jobs.push({sku:sku, ref:ref, label:(source==="brand"?"brand-clean":"logo-removed"), payload:{
      product_image:ref, title:(it&&it.title)||"", source:source, preserve_logo:preserveLogo,
      instruction:instr, fidelity:fid, text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)
    }});
  });
  const total=jobs.length;
  if(total>4 && !confirm("This will generate "+total+" image(s). Each is a paid call. Continue?")) return;
  studioRunBackground("source", jobs, total);
}

function secondaryPaneHTML(batch,n){
  const roles=[["benefit","Benefit infographic"],["feature","Feature / what's-in-box"],["lifestyle","Lifestyle in-use"],["dimensions","Size / dimensions"],["trust","Trust / quality"],["comparison","Why choose us"],["detail","Close-up detail / materials"],["usecase","Use-case / scenario"]];
  return `
    <div class="ideabox">
      <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-bulb"></i> Option A — Let the AI strategist design the set</div>
      <div class="cc" style="margin-bottom:8px">The AI thinks like a conversion strategist + your customer and proposes secondary-image concepts (which benefit to lead with, what objection to kill, what lifestyle moment sells it) for <b>this</b> product. Click below, then pick which ideas to generate.</div>
      <label class="cc" style="display:block;margin-bottom:3px">Instructions for the strategist (optional, not saved) — e.g. "don't show pets", "pour the medicine into the tub in one image", "show the product in only some images, not all"</label>
      <textarea id="strat_instr_secondary" class="ed" rows="2" placeholder='e.g. no pets; one image pouring liquid into a tub; show product in ~half the images so the buyer still knows what it is' style="margin-bottom:8px"></textarea>
      <button class="primary" onclick="studioStrategize('secondary')"><i class="ti ti-sparkles"></i> Suggest secondary ideas</button>
      <button class="primary" onclick="studioStrategize('secondary', true)" style="margin-left:6px" title="Ask the strategist for ideas AND generate them all automatically — no manual picking"><i class="ti ti-bolt"></i> Suggest &amp; auto-generate${batch?(' ('+n+' products)'):''}</button>
      <span id="sec_strat_status" class="cc" style="margin-left:8px"></span>
      ${howWorks('secAI')}
      <div id="sec_concepts" style="margin-top:10px"></div>
      <div class="cc" style="font-size:11px;margin-top:6px;opacity:.75">↑ The "Generate all ideas" button appears here <i>after</i> the AI suggests ideas — it generates the AI's concepts.</div>
    </div>

    <div class="ordiv"><span>OR</span></div>

    <div class="buildbox">
      <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-adjustments"></i> Option B — Build the set yourself</div>
      <div class="cc" style="margin-bottom:8px">You choose the roles and details. Secondary images each do <b>one job</b> — clean and premium, not cluttered. ${batch?('Applies to each of '+n+' selected products.'):''}</div>
      <div class="secrow">
        <label class="cc">Mode</label>
        <select id="sec_mode" class="ed" onchange="secModeChange()">
          <option value="planned">Planned roles (recommended)</option>
          <option value="free">Free-form (write my own)</option>
        </select>
      </div>
      <div id="sec_planned">
        <label class="cc" style="margin-top:8px;display:block">Choose the images to generate</label>
        <div class="secroles">
          ${roles.map(r=>`<label class="seccheck"><input type="checkbox" class="secrole" value="${r[0]}" ${r[0]==='benefit'?'checked':''}> ${r[1]}</label>`).join("")}
        </div>
      </div>
      <div id="sec_free" style="display:none">
        <label class="cc" style="margin-top:8px;display:block">Describe the secondary image(s) you want</label>
        <textarea id="sec_instruction" class="ed" rows="2" placeholder="e.g. an infographic showing the 2L capacity with a clean water splash, premium feel"></textarea>
        <div class="secrow" style="margin-top:8px;align-items:center;gap:8px">
          <label class="cc">How many images?</label>
          <input id="sec_free_count" type="number" min="1" max="10" value="1" class="ed" style="max-width:90px" title="How many secondary images to generate from your description (1–10).">
          <span class="cc" style="font-size:11px;opacity:.7">per product${batch?(' × '+n+' products'):''}</span>
        </div>
      </div>
      <div class="secrow" style="margin-top:10px">
        <label class="seccheck"><input type="radio" name="benc" value="1" checked> Highlight 1 benefit per image</label>
        <label class="seccheck"><input type="radio" name="benc" value="2"> Highlight 2 benefits per image</label>
      </div>
      <label class="cc" style="margin-top:8px;display:block">Specific benefit(s) to highlight (optional)</label>
      <input id="sec_benefit_text" class="ed" placeholder="e.g. dishwasher-safe; BPA-free">
      <div class="seccomp">
        <label class="cc" style="margin-top:10px;display:block">Competitor inspiration (optional, up to 3) — paste an image URL or upload</label>
        ${[0,1,2].map(i=>`
          <div class="seccomp8 row">
            <input id="sec_comp_${i}" class="ed" placeholder="competitor image URL" style="flex:1">
            <input type="file" id="sec_compf_${i}" accept="image/*" onchange="secCompPick(${i},this)" style="max-width:160px">
            <select id="sec_compm_${i}" class="ed" style="max-width:150px" title="How to use this reference">
              <option value="describe">Describe style (safe)</option>
              <option value="direct">Direct reference</option>
            </select>
          </div>`).join("")}
        <div class="cc" style="font-size:11px;margin-top:4px"><b>Describe style</b>: AI extracts the look (lighting, angle, effects like oil-drops) and reapplies it to your product — recommended, avoids copying. <b>Direct</b>: feeds the competitor image to the model directly.</div>
      </div>
      <div style="margin-top:12px"><button class="primary" onclick="studioRunSecondary()"><i class="ti ti-sparkles"></i> ${batch?('Generate my hand-built set for all '+n+' products'):'Generate my hand-built set'}</button></div>
      ${howWorks('secManual')}
    </div>`;
}
function secModeChange(){
  const m=(document.getElementById("sec_mode")||{}).value;
  document.getElementById("sec_planned").style.display = m==="planned"?"block":"none";
  document.getElementById("sec_free").style.display = m==="free"?"block":"none";
}
let SEC_COMP_DATA={};
function secCompPick(i, input){
  const f=input.files&&input.files[0]; if(!f) return;
  const r=new FileReader(); r.onload=()=>{ SEC_COMP_DATA[i]=r.result; toast("Competitor image "+(i+1)+" loaded"); };
  r.readAsDataURL(f);
}
function _collectCompRefs(){
  const refs=[];
  for(let i=0;i<3;i++){
    const url=(document.getElementById("sec_comp_"+i)||{}).value||"";
    const data=SEC_COMP_DATA[i]||"";
    const mode=(document.getElementById("sec_compm_"+i)||{}).value||"describe";
    const img=data||url.trim();
    if(img) refs.push({image:img, mode:mode});
  }
  return refs;
}
async function studioRunSecondary(){
  const mode=(document.getElementById("sec_mode")||{}).value;
  const benc=parseInt((document.querySelector('input[name="benc"]:checked')||{}).value||"1");
  const benefitText=(document.getElementById("sec_benefit_text")||{}).value||"";
  const compRefs=_collectCompRefs();
  let roles=[];
  if(mode==="planned"){
    roles=Array.from(document.querySelectorAll(".secrole:checked")).map(c=>c.value);
    if(!roles.length){ toast("Pick at least one image role."); return; }
  } else {
    const instr=(document.getElementById("sec_instruction")||{}).value||"";
    if(!instr.trim()){ toast("Describe the secondary image you want."); return; }
    // honor the "how many images?" count in free-form mode: make that many jobs,
    // each from the same description (the model varies them naturally).
    let cnt=parseInt((document.getElementById("sec_free_count")||{}).value||"1");
    if(isNaN(cnt)||cnt<1) cnt=1; if(cnt>10) cnt=10;
    roles=[]; for(let _i=0;_i<cnt;_i++) roles.push("__free__");
  }
  const freeInstr=(document.getElementById("sec_instruction")||{}).value||"";
  let jobs=[];
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku); const ref=_refImgForItem(it);
    let _freeIdx=0;
    roles.forEach(role=>{
      // number multiple free-form images so results are distinguishable
      const roleLabel=role==="__free__"?("custom "+(++_freeIdx)):role;
      const body={ product_image:ref, title:(it&&it.title)||"", benefit_count:benc, benefit_text:benefitText,
        competitor_refs:compRefs, text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null),
        fidelity:((document.getElementById("studio_fidelity")||{}).value||"high") };
      if(role==="__free__") body.instruction=freeInstr; else body.role=role;
      jobs.push({sku:sku, ref:ref, label:roleLabel, payload:body});
    });
  });
  const total=jobs.length;
  if(total>4 && !confirm("This will generate "+total+" secondary image"+(total>1?"s":"")+" ("+STUDIO.skus.length+" product(s) × "+roles.length+" image(s)).\nEach is a paid OpenRouter call. Continue?")) return;
  studioRunBackground("secondary", jobs, total);
}

// ============ A+ CONTENT ============
let APLUS_MODULES={basic:[],premium:[]};
function aplusPaneHTML(batch,n){
  return `
    <div class="aplusnote">
      <b>A+ Content</b> requires <b>Amazon Brand Registry</b>. <b>Premium A+</b> additionally requires a Brand Story on all your ASINs and 15+ approved A+ submissions in the last 12 months. This tool generates module images at Amazon's <b>exact pixel dimensions</b> plus draft copy — you then upload them in Seller Central's A+ builder.
    </div>
    <div class="ideabox" style="margin-top:10px">
      <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-bulb"></i> Option A — Let the AI strategist design your A+ story</div>
      <div class="cc" style="margin-bottom:8px">The AI thinks like a brand strategist + your customer and proposes a coherent A+ module sequence (hero banner, key benefits, how-to-use, ingredients, lifestyle, why-us, trust) for <b>this</b> product. Pick which modules to generate.</div>
      <div class="secrow" style="margin-bottom:8px;align-items:center;gap:8px">
        <label class="cc">Tier</label>
        <select id="ap_strat_tier" class="ed" style="max-width:280px">
          <option value="basic">Basic A+ (all Brand Registered sellers) — 5 modules</option>
          <option value="premium">Premium A+ (requires Premium access) — 7 modules</option>
        </select>
      </div>
      <button class="primary" onclick="studioStrategize('aplus')"><i class="ti ti-sparkles"></i> Suggest A+ modules</button>
      <button class="primary" onclick="studioStrategize('aplus', true)" style="margin-left:6px" title="Ask the strategist for A+ modules AND generate them all automatically — no manual picking"><i class="ti ti-bolt"></i> Suggest &amp; auto-generate${batch?(' ('+n+' products)'):''}</button>
      <span id="ap_strat_status" class="cc" style="margin-left:8px"></span>
      <label class="cc" style="display:block;margin:8px 0 3px">Instructions for the strategist (optional, not saved) — e.g. "don't show pets", "include a how-to-use module", "show the product in only some modules"</label>
      <textarea id="strat_instr_aplus" class="ed" rows="2" placeholder='e.g. no people or pets; one module showing it poured into a bath; keep palette blue/white'></textarea>
      <div id="ap_concepts" style="margin-top:10px"></div>
    </div>
    <div class="ordiv"><span>OR</span></div>
    <div class="buildbox">
    <div style="font-weight:600;margin-bottom:8px"><i class="ti ti-adjustments"></i> Option B — Pick the exact modules yourself</div>
    <div class="secrow" style="margin-top:10px">
      <label class="cc">Tier</label>
      <select id="ap_tier" class="ed" onchange="aplusRenderModules()">
        <option value="basic">Basic A+ (all Brand Registered sellers)</option>
        <option value="premium">Premium A+ (requires Premium access)</option>
      </select>
    </div>
    <label class="cc" style="margin-top:10px;display:block">Choose modules to generate (each shows Amazon's exact size)</label>
    <div id="ap_modules" class="apmods"><span class="cc">Loading modules…</span></div>
    <label class="cc" style="margin-top:10px;display:block">Benefit(s) / message to feature (optional)</label>
    <input id="ap_benefit" class="ed" placeholder="e.g. keeps drinks cold 24h; leak-proof lid">
    <label class="cc" style="margin-top:8px;display:block">Extra instruction (optional)</label>
    <textarea id="ap_instruction" class="ed" rows="2" placeholder="e.g. match our brand's clean blue palette, show the product on a marble surface"></textarea>
    <div style="margin-top:12px"><button class="primary" onclick="studioRunAplus()"><i class="ti ti-sparkles"></i> ${batch?('Generate A+ modules for all '+n+' products'):'Generate A+ module images'}</button></div>
    </div>${typeof howWorks==="function"?howWorks('aplus'):""}`;
}
async function aplusLoadModules(){
  if(APLUS_MODULES.basic.length) { aplusRenderModules(); return; }
  try{
    const j=await (await fetch("/aplus/modules")).json();
    if(j.ok){ APLUS_MODULES=j.modules; }
  }catch(e){}
  aplusRenderModules();
}
function aplusRenderModules(){
  const tier=(document.getElementById("ap_tier")||{}).value||"basic";
  const box=document.getElementById("ap_modules"); if(!box) return;
  const mods=APLUS_MODULES[tier]||[];
  if(!mods.length){ box.innerHTML='<span class="cc">No modules.</span>'; return; }
  box.innerHTML=mods.map(m=>`
    <label class="apmod">
      <input type="checkbox" class="apmodchk" value="${esc(m.id)}" ${m.id==='image_header_text'||m.id==='premium_full'?'checked':''}>
      <div>
        <div style="font-weight:600;font-size:13px">${esc(m.name)} <span class="apdim">${m.w}×${m.h}px</span></div>
        <div class="cc" style="font-size:11px">${esc(m.desc)}</div>
      </div>
    </label>`).join("");
}
async function studioRunAplus(){
  const tier=(document.getElementById("ap_tier")||{}).value||"basic";
  const benefit=(document.getElementById("ap_benefit")||{}).value||"";
  const instr=(document.getElementById("ap_instruction")||{}).value||"";
  const mods=Array.from(document.querySelectorAll(".apmodchk:checked")).map(c=>c.value);
  if(!mods.length){ toast("Pick at least one A+ module."); return; }
  let jobs=[];
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku); const ref=_refImgForItem(it);
    mods.forEach(mid=>{
      const modName=((APLUS_MODULES[tier]||[]).find(m=>m.id===mid)||{}).name||mid;
      const body={ product_image:ref, title:(it&&it.title)||"", tier:tier, module_id:mid,
        benefit_text:benefit, instruction:instr, text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null),
        fidelity:((document.getElementById("studio_fidelity")||{}).value||"high") };
      jobs.push({sku:sku, ref:ref, label:modName, payload:body});
    });
  });
  const total=jobs.length;
  if(total>4 && !confirm("This will generate "+total+" A+ module image"+(total>1?"s":"")+" ("+STUDIO.skus.length+" product(s) × "+mods.length+" module(s)).\nEach is a paid OpenRouter call. Continue?")) return;
  studioRunBackground("aplus", jobs, total);
}
function _aplusAddResult(job, j, grid){
  grid=grid||document.getElementById("studio_results");
  const cardId="ares_"+Math.random().toString(36).slice(2);
  const dim=j&&j.module?(j.module.w+'×'+j.module.h+'px'):'';
  let copyHtml="";
  if(j&&j.copy){
    try{ const c=JSON.parse(j.copy); copyHtml=`<div class="apcopy"><b>${esc(c.headline||'')}</b><br>${esc(c.body||'')}</div>`; }
    catch(e){ copyHtml=`<div class="apcopy">${esc(j.copy)}</div>`; }
  }
  let inner;
  if(j&&j.ok&&j.data_url){
    inner=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
      <div class="srescap">${esc(job.sku)} · ${esc(job.modName)} <span class="apdim">${dim}</span></div>
      ${copyHtml}
      <div class="sresacts">
        <button class="ib" onclick="studioSave('${cardId}','${esc(job.sku)}')"><i class="ti ti-device-floppy"></i> Save</button>
        <button class="ib" onclick="studioDownload('${cardId}','${esc(job.sku)}')"><i class="ti ti-download"></i></button>
        <button class="ib" onclick="studioToDrive('${cardId}','${esc(job.sku)}')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
      </div>`;
    STUDIO.results[cardId]={data_url:j.data_url, sku:job.sku};
  } else {
    inner=`<div class="sresfail">✗ ${esc((j&&j.error)||'failed')}</div><div class="srescap">${esc(job.sku)} · ${esc(job.modName)}</div>`;
  }
  const div=document.createElement("div");
  div.className="srescard"; div.id=cardId; div.innerHTML=inner;
  grid.appendChild(div);
}
function studioTab(t){
  document.querySelectorAll('#studiobody .stab').forEach(b=>b.classList.toggle('on', b.dataset.tab===t));
  ['recipe','creative','source','secondary','aplus','recipes_manage'].forEach(p=>{
    const el=document.getElementById('studio_'+p); if(el) el.style.display = (p===t)?'block':'none';
  });
  if(t==='aplus') aplusLoadModules();
}
function recipesManageHTML(){
  const list=(STUDIO.recipes||[]).map(r=>`
    <div class="recipecard">
      ${r.template_image?`<img src="${esc(r.template_image)}">`:'<div class="noimgmsg" style="height:60px"><span>no template image</span></div>'}
      <div style="flex:1">
        <div style="font-weight:600">${esc(r.name)}</div>
        <div class="cc" style="font-size:11px;max-height:38px;overflow:hidden">${esc(r.instructions)}</div>
      </div>
      <button class="ib" title="Delete recipe" onclick="deleteRecipe('${esc(r.id)}')"><i class="ti ti-trash"></i></button>
    </div>`).join("");
  return `
    <div class="cc" style="margin-bottom:8px">A recipe = a <b>template image</b> (a main image from one of your products) + the <b>changes you want</b>. Save it once and reuse it on any product. The AI improves your wording before generating, and always keeps each product faithful via its own reference image.</div>
    <label class="cc">Recipe name</label>
    <input id="rec_name" class="ed" placeholder="e.g. Shee'lady white hero">
    <label class="cc" style="margin-top:6px;display:block">Template image (optional — upload a main image to mimic)</label>
    <input type="file" id="rec_tpl" accept="image/*" onchange="recTplPick(this)">
    <div id="rec_tpl_prev"></div>
    <label class="cc" style="margin-top:6px;display:block">Changes / treatment you want</label>
    <textarea id="rec_instr" class="ed" rows="3" placeholder="e.g. pure white background, soft top-light, product centered at 85% with a subtle shadow, premium clean look"></textarea>
    <div style="margin-top:8px"><button class="primary" onclick="saveRecipe()"><i class="ti ti-device-floppy"></i> Save recipe</button> <span id="rec_status" class="cc"></span></div>
    <div style="margin-top:14px">${list||'<div class="cc">No recipes saved yet.</div>'}</div>`;
}
let REC_TPL_DATA="";
function recTplPick(input){
  const f=input.files&&input.files[0]; if(!f) return;
  const r=new FileReader(); r.onload=()=>{ REC_TPL_DATA=r.result; document.getElementById("rec_tpl_prev").innerHTML='<img src="'+REC_TPL_DATA+'" style="max-width:120px;border-radius:8px;margin-top:6px">'; };
  r.readAsDataURL(f);
}
async function saveRecipe(){
  const name=(document.getElementById("rec_name")||{}).value||"";
  const instr=(document.getElementById("rec_instr")||{}).value||"";
  const st=document.getElementById("rec_status");
  if(!name.trim()||!instr.trim()){ if(st) st.textContent="Name and changes are required."; return; }
  if(st) st.innerHTML='<span class="genspin"></span> saving…';
  try{
    const j=await (await fetch("/recipes/save",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({brand:STUDIO.brand, name:name.trim(), instructions:instr.trim(), template_image:REC_TPL_DATA})})).json();
    if(!j.ok){ if(st) st.textContent=j.error||"failed"; return; }
    REC_TPL_DATA=""; await loadRecipes();
    document.getElementById("studio_recipes_manage").innerHTML=recipesManageHTML();
    if(st) st.textContent="Saved ✓";
  }catch(e){ if(st) st.textContent="Error: "+e; }
}
async function deleteRecipe(id){
  if(!confirm("Delete this recipe?")) return;
  await fetch("/recipes/delete",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({brand:STUDIO.brand, id:id})});
  await loadRecipes();
  document.getElementById("studio_recipes_manage").innerHTML=recipesManageHTML();
  renderStudio();
}
// ---- shared background-job runner: submit jobs, poll, render as they complete ----
let STUDIO_POLL=null;
function _studioRenderResult(kind, r, grid){
  // r has .ok,.data_url,.label,.sku and (for aplus) .module,.copy
  if(kind==="aplus"){ _aplusAddResult({sku:r.sku, modName:(r.module&&r.module.name)||r.label||""}, r, grid); }
  else { _studioAddResult({sku:r.sku, strategy:r.label}, r, grid); }
}
async function studioRunBackground(kind, jobs, total){
  // Each section (main / secondary / aplus) has its OWN concept list but they
  // shared a single results container before -- so generating from the secondary
  // or A+ section wrote into (or failed to find) the MAIN container and looked
  // like "nothing happened". Resolve the right containers for the active section,
  // and create them on the fly if that section doesn't have them yet.
  const section = STUDIO.conceptKind || (kind==="concept" ? (STUDIO.conceptKind||"main") : "main");
  function _ensure(anchorId, id, cls){
    let el=document.getElementById(id);
    if(el) return el;
    const anchor=document.getElementById(anchorId);
    if(!anchor) return null;
    el=document.createElement("div");
    el.id=id; if(cls) el.className=cls; el.style.marginTop="14px";
    anchor.parentNode.insertBefore(el, anchor.nextSibling);
    return el;
  }
  let prog, grid;
  if(section==="secondary"){
    prog=_ensure("sec_concepts","sec_progress");
    grid=_ensure("sec_progress","sec_results","studiogrid");
  } else if(section==="aplus"){
    prog=_ensure("ap_concepts","ap_progress");
    grid=_ensure("ap_progress","ap_results","studiogrid");
  }
  // fall back to the main containers if section ones couldn't be made
  prog=prog||document.getElementById("studio_progress");
  grid=grid||document.getElementById("studio_results");
  if(!prog||!grid){ toast("Couldn't find a place to show results — try reopening Image Studio."); return; }
  grid.innerHTML=""; STUDIO.results={};
  if(STUDIO_POLL){ clearInterval(STUDIO_POLL); STUDIO_POLL=null; }
  prog.innerHTML='<span class="genspin"></span> Starting '+total+' generation'+(total>1?'s':'')+' in the background…';
  let resp;
  try{
    resp=await (await fetch("/genimage/start_batch",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kind:kind, jobs:jobs})})).json();
  }catch(e){ prog.innerHTML='<span style="color:#e0696b">Could not start: '+esc(String(e))+'</span>'; return; }
  if(!resp.ok){ prog.innerHTML='<span style="color:#e0696b">'+esc(resp.error||"failed to start")+'</span>'; return; }
  const jobId=resp.job;
  STUDIO.currentJob=jobId;
  let shown=0;
  prog.innerHTML='<span class="genspin"></span> Generating in background… <span class="cc">you can keep using the app; results appear below as they finish.</span>';
  STUDIO_POLL=setInterval(async ()=>{
    try{
      const st=await (await fetch("/genimage/job_status?job="+encodeURIComponent(jobId))).json();
      if(!st.ok){ return; }
      // render any new results
      for(let i=shown;i<st.results.length;i++){ _studioRenderResult(kind, st.results[i], grid); }
      shown=st.results.length;
      if(st.status!=="running"){
        clearInterval(STUDIO_POLL); STUDIO_POLL=null;
        const okN=st.results.filter(r=>r.ok).length;
        prog.innerHTML='<span style="color:#7fd99a">✓ Done — '+okN+'/'+st.total+' succeeded. <b>All generated images were auto-saved to each product\u2019s media library</b> (Image refs), so they\u2019re safe even if you close this.</span>'
          + (st.error?(' <span style="color:#e0696b">'+esc(st.error)+'</span>'):'');
      } else {
        prog.innerHTML='<span class="genspin"></span> Generating '+st.done+'/'+st.total+' in background… <span class="cc">each finished image is auto-saved to its media library; safe to close or keep working.</span>';
      }
    }catch(e){}
  }, 2000);
}

// ---- STRATEGIST: AI invents conversion-focused image concepts ----
async function saveStudioInstructions(){
  const ta=document.getElementById("studio_custom_instructions");
  const st=document.getElementById("studio_ci_status");
  if(!ta) return;
  const txt=ta.value||"";
  if(st) st.innerHTML='<span class="genspin"></span> saving…';
  try{
    const j=await (await fetch("/genimage/instructions",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({instructions:txt, scope:"account", id:(CUR_ACCOUNT&&CUR_ACCOUNT.id)||""})})).json();
    window.IMG_INSTRUCTIONS = j.instructions||"";
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ saved — applied to every image</span>';
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">could not save</span>'; }
}
async function loadStudioInstructions(){
  try{
    const j=await (await fetch("/genimage/instructions?id="+encodeURIComponent((CUR_ACCOUNT&&CUR_ACCOUNT.id)||""))).json();
    window.IMG_INSTRUCTIONS = j.instructions||"";
    const ta=document.getElementById("studio_custom_instructions");
    if(ta && !ta.value) ta.value=window.IMG_INSTRUCTIONS;
  }catch(e){}
}
async function studioStrategize(kind, autoGen){
  const statusId = kind==="main" ? "studio_strat_status" : (kind==="aplus" ? "ap_strat_status" : "sec_strat_status");
  const boxId = kind==="main" ? "studio_concepts" : (kind==="aplus" ? "ap_concepts" : "sec_concepts");
  const st=document.getElementById(statusId);
  const box=document.getElementById(boxId);
  if(STUDIO.skus.length>1){
    // for batch, strategize on the first product as the template, applied to all
    if(st) st.innerHTML='<span class="cc">(using the first selected product to design concepts, then applies to all)</span>';
  }
  const sku=STUDIO.skus[0];
  const it=_itemForSku(sku); const ref=_refImgForItem(it);
  if(!ref){ if(st) st.innerHTML='<span style="color:#e0696b">first product has no reference image</span>'; return; }
  if(st) st.innerHTML='<span class="genspin"></span> The strategist is thinking like a customer & conversion expert…';
  if(box) box.innerHTML="";
  // How many ideas to ask for depends on the section:
  //  - secondary: Amazon allows up to 8 extra images, so propose 8
  //  - aplus: match the chosen tier's module count (basic 5 / premium 7)
  //  - main: 3 hero concepts
  let _n = 3;
  if(kind==="secondary") _n = 8;
  else if(kind==="aplus"){
    // read the tier selector that lives in Option A (the strategist's own), so
    // the user can pick Premium for the strategist directly. Fall back to Option
    // B's tier, then basic.
    const _tier = ((document.getElementById("ap_strat_tier")||{}).value
                   || (document.getElementById("ap_tier")||{}).value || "basic");
    _n = _tier==="premium" ? 7 : 5;
    STUDIO.aplusTier = _tier;   // remember so generated modules go to the right subfolder
  }
  try{
    // per-run instructions for the strategist (not saved) — keyed by section
    const _instrEl=document.getElementById("strat_instr_"+kind);
    const _customInstr=(_instrEl && _instrEl.value || "").trim();
    const j=await (await fetch("/genimage/strategize",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({product_image:ref, title:(it&&it.title)||"", kind:kind, n:_n, text_provider:(window.AI_TEXT||null), custom_instructions:_customInstr})})).json();
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; return; }
    const concepts=j.concepts||[];
    if(!concepts.length){ if(st) st.innerHTML='<span class="cc">No concepts returned — try again.</span>'; return; }
    STUDIO.concepts=concepts; STUDIO.conceptKind=kind;
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ '+concepts.length+' ideas'+(autoGen?' — generating all now…':' — pick to generate')+'</span>';
    if(box) box.innerHTML=concepts.map((c,i)=>`
      <div class="conceptcard">
        <div style="flex:1">
          <div style="font-weight:600;font-size:13px">${esc(c.title||('Idea '+(i+1)))}</div>
          <div class="cc" style="font-size:11px;margin:2px 0"><b>Customer insight:</b> ${esc(c.customer_insight||"")}</div>
          <div class="cc" style="font-size:11.5px;margin:2px 0">${esc(c.concept||"")}</div>
          <div class="cc" style="font-size:10.5px;opacity:.8"><b>Art direction:</b> ${esc(c.art_direction||"")}</div>
        </div>
        <button class="ib" onclick="studioGenConcept(${i})"><i class="ti ti-photo"></i> Generate${STUDIO.skus.length>1?(' ×'+STUDIO.skus.length):''}</button>
      </div>`).join("") +
      (concepts.length>1?`<div style="margin-top:8px"><button class="primary" onclick="studioGenAllConcepts()"><i class="ti ti-sparkles"></i> Generate all ${concepts.length} AI ideas${STUDIO.skus.length>1?(' for each of '+STUDIO.skus.length+' products'):''}</button></div>`:"");
    // AUTO-ACCEPT: if the user asked to auto-generate, skip the manual pick and
    // generate every suggested concept right away (across all selected products).
    if(autoGen){ studioGenAllConcepts(true); }
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">Error: '+esc(String(e))+'</span>'; }
}
function _conceptJobs(concepts){
  const kind=STUDIO.conceptKind||"main";
  const fid=(document.getElementById("studio_fidelity")||{}).value||"high";
  const ci=((document.getElementById("studio_custom_instructions")||{}).value||window.IMG_INSTRUCTIONS||"");
  let jobs=[];
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku); const ref=_refImgForItem(it);
    concepts.forEach(c=>{
      jobs.push({sku:sku, ref:ref, label:(c.title||"idea"), payload:{
        product_image:ref, title:(it&&it.title)||"", kind:kind,
        concept:c.concept||"", art_direction:c.art_direction||"",
        fidelity:fid, custom_instructions:ci,
        tier:(STUDIO.aplusTier||"basic"),
        text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)
      }});
    });
  });
  return jobs;
}
function studioGenConcept(i){
  const c=(STUDIO.concepts||[])[i]; if(!c) return;
  const jobs=_conceptJobs([c]);
  studioRunBackgroundConcept(jobs, jobs.length);
}
function studioGenAllConcepts(auto){
  const concepts=STUDIO.concepts||[]; if(!concepts.length) return;
  const jobs=_conceptJobs(concepts);
  // when auto-invoked (user clicked "Suggest & auto-generate"), they've already
  // opted in, so skip the paid-call confirm; otherwise still confirm for >4.
  if(!auto && jobs.length>4 && !confirm("This will generate "+jobs.length+" image(s). Each is a paid call. Continue?")) return;
  studioRunBackgroundConcept(jobs, jobs.length);
}
function studioRunBackgroundConcept(jobs, total){
  studioRunBackground("concept", jobs, total);
}

async function studioRun(mode){
  let jobs=[];
  const strategies = mode==="creative" ? ["hero_straight","hero_angle","hero_personality"] : [null];
  const recipeId = mode==="recipe" ? ((document.getElementById("studio_recipe_sel")||{}).value||"") : "";
  const inspo = mode==="creative" ? ((document.getElementById("studio_inspo")||{}).value||"") : "";
  if(mode==="recipe" && !recipeId){ toast("Pick a recipe first."); return; }
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku);
    const ref=_refImgForItem(it);
    strategies.forEach(strat=>{
      const body={ product_image:ref, title:(it&&it.title)||"", text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null), fidelity:((document.getElementById("studio_fidelity")||{}).value||"high") };
      if(mode==="recipe"){ body.mode="recipe"; body.recipe_id=recipeId; body.brand=STUDIO.brand; }
      else { body.mode="creative"; body.strategy=strat; body.inspiration=inspo; }
      jobs.push({sku:sku, ref:ref, label:(strat?strat.replace(/_/g,' '):'main'), payload:body});
    });
  });
  const total=jobs.length;
  if(total>4 && !confirm("This will generate "+total+" image"+(total>1?"s":"")+" ("+STUDIO.skus.length+" product(s)"+(mode==="creative"?" × 3 variations":"")+").\nEach is a paid OpenRouter call. Continue?")) return;
  studioRunBackground(mode==="creative"?"creative":"recipe", jobs, total);
}
// ============================================================
// "HOW IT WORKS" LOGIC FRAMEWORK (admin-visible transparency layer)
// One central registry + one helper. To document any feature anywhere in the
// app, add an entry to LOGIC_REGISTRY and drop ${howWorks('key')} after its button.
// Visibility is gated: admin sees panels when LOGIC_VISIBLE is true; a non-admin
// (or admin in "preview as user" mode) sees nothing.
// ============================================================
window.LOGIC_VISIBLE = true;      // set from /ai/settings admin flags on load
function _mdl(){
  var f=((document.getElementById("studio_fidelity")||{}).value||"high");
  return { C:(window.AI_IMAGE||"your image model"), T:(window.AI_TEXT||"your prompt model"),
    fid:f, strn:(f==="high"?"0.2":(f==="medium"?"0.35":"0.55")) };
}
function LOGIC_REGISTRY(){
  const {C,T,strn} = _mdl();
  return {
    strategist: { title:"How the AI strategist works", steps:[
      `<b>Reads your real product.</b> Your product image goes to the prompt AI (<code>${esc(T)}</code>) for a forensic read — shape, proportions, material, exact colours/gradient, every line of label text, the logo — producing a written spec.`,
      `<b>Thinks like a strategist + customer.</b> That spec + your title go to <code>strategize_images</code>, prompted to reason as an Amazon conversion expert and as your buyer. It invents 3 concepts: <i>customer insight</i>, <i>concept</i>, <i>art direction</i>.`,
      `<b>You pick.</b> Nothing is generated yet — you choose one idea or "Generate all".`,
      `<b>Generates faithfully.</b> The art direction runs through <code>run_pipeline</code> → <code>from_concept</code>: your product image attached as reference, image AI (<code>${esc(C)}</code>) renders at <b>strength ${strn}</b> (low = stay close), <b>4K, pure white</b>.`,
      `<b>Auto-saves</b> each finished image to this product's media library immediately.` ]},
    ready3: { title:"How the 3 ready-made variations work", steps:[
      `<b>No idea-invention step</b> — uses 3 fixed treatments: straight-on hero, flattering angle, creative "personality" shot.`,
      `<b>Reads your product</b> (<code>${esc(T)}</code>) for an exact spec, folded into each brief so the product can't drift.`,
      `<b>Writes the prompt.</b> <code>enhance_prompt</code> turns each treatment + spec into a detailed prompt with strict pure-white-background rules.`,
      `<b>Generates with your product as reference.</b> Image AI (<code>${esc(C)}</code>) renders each at <b>strength ${strn}, 4K, 1:1 pure white</b>.`,
      `<b>Background + auto-save.</b> All 3 run in the background; each saves as it finishes. Use <i>Redo this</i> on any that drifts.` ]},
    secAI: { title:"How the AI-designed secondary set works", steps:[
      `<b>Reads your product</b> (<code>${esc(T)}</code>) for an exact spec.`,
      `<b>Invents secondary concepts</b> — which benefit to lead with, what objection to kill, which lifestyle moment sells it (text/graphics allowed on secondary images).`,
      `<b>You pick which to generate.</b>`,
      `<b>Generates faithfully</b> via <code>run_pipeline</code> with your product attached at <b>strength ${strn}, 4K</b> (image AI: <code>${esc(C)}</code>).`,
      `<b>Auto-saves</b> every result.` ]},
    secManual: { title:"How your hand-built secondary set works", steps:[
      `<b>You define the set</b> — roles ticked, benefits per image, specific benefits, competitor inspiration.`,
      `<b>Competitor inspiration handled safely.</b> "Describe style" → vision AI extracts only the <i>technique</i> (lighting, angle, effects) and reapplies it to your product (no copying). "Direct" → feeds their image to the model.`,
      `<b>Reads your product</b> (<code>${esc(T)}</code>) for an exact spec.`,
      `<b>Generates each role</b> with your product attached at <b>strength 0.35, 4K</b> (image AI: <code>${esc(C)}</code>), one clear message per image.`,
      `<b>Auto-saves</b> every result.` ]},
    source: { title:"How the Main image (clean white bg) works", steps:[
      `<b>Pick the reference photo.</b> The product's source images (eBay first) are shown as thumbnails — tap the cleanest one that best shows the product. If you don't pick, the first is auto-selected.`,
      `<b>Reads the source photo</b> (eBay/Amazon scrape or brand upload) with the prompt AI (<code>${esc(T)}</code>) for a product spec.`,
      `<b>Applies the logo rule by source.</b> Competitor/eBay → remove a brand logo if present, blend to surface (no replacement); no logo → leave as-is. Brand CSV → keep product <i>and</i> logo (unless you uncheck "preserve logo").`,
      `<b>Keeps the product identical</b> — only the logo and your optional edits change.`,
      `<b>Generates clean</b> with your chosen reference attached at your fidelity strength, target <b>2500px, pure white</b> (image AI: <code>${esc(C)}</code>).`,
      `<b>Auto-saves</b> the result, and shows its real <b>pixel size and file size</b> under the image.` ]},
    drive: { title:"How Drive image storage works", steps:[
      `<b>Set a master folder per account.</b> In Account &amp; sheets, paste a Google Drive folder URL. That folder becomes the home for this account's generated images.`,
      `<b>Share it with the service account.</b> Just like a Google Sheet, the folder must be shared (Editor) with the service-account email shown in the Drive panel — otherwise uploads are denied.`,
      `<b>Per-product subfolders.</b> Each image is uploaded into a subfolder named <code>{SKU}_{ProductName}</code>, created automatically if it doesn't exist.`,
      `<b>Your own Drive.</b> Images live in your Drive, organised by product, safe and separate from the app.` ]},
    content_index: { title:"How the content fields & indexing work", steps:[
      `<b>Title</b> — fill close to the 75-char cap (the hard cap lands 27 Jul 2026). Front-load the first ~70 chars; mobile truncates there. Fully indexed, highest A10 weight.`,
      `<b>Item Highlights</b> — a structured 125-char field shown with the title in search and on the PDP; carries its own weight.`,
      `<b>Bullets</b> — 500 chars each, but Amazon indexes only the first ~1,000 <i>bytes</i> across ALL five combined. The meter above the bullets shows how much of that budget is used; overflow still shows to shoppers but isn't indexed.`,
      `<b>Description</b> — up to 2,000 chars incl. HTML; indexed but lowest weight.`,
      `<b>Backend search terms</b> — 249 <i>bytes</i> (not chars). One byte over silently de-indexes the whole field, so the counter is in bytes and warns near the limit.` ]},
    required_fields: { title:"How required fields are shown", steps:[
      `<b>The red ★</b> marks a field Amazon requires, read straight from the live schema's <code>required</code> list for this product type.`,
      `<b>Before Preview</b> we show every <i>static</i> required field. Some are <i>conditional</i> (e.g. the lithium-battery group) and Amazon only reveals them after a Preview.`,
      `<b>After Preview</b> every field Amazon flags gets a visible box — including nested sub-fields — so nothing the validator wants is hidden from you.`,
      `<b>Product type</b> defaults to the type Amazon assigned in the catalogue ("Amazon-assigned"); changing it warns you, because a wrong type causes rejection.` ]},
    // ---------- OPTIMIZE: the red-dot fixer ----------
    opt_fetch: { title:"How 'Optimize live listing' loads the data", steps:[
      `<b>Reads the LIVE listing from Amazon.</b> Calls SP-API <code>getListingsItem</code> with <code>includedData="attributes,summaries,issues"</code> on the connected seller account — so the title, status and fields are the real current ones, not a cached report.`,
      `<b>Shows Amazon's own issues verbatim.</b> The warnings/errors come straight from Amazon's <code>issues</code> array (e.g. "invalid condition type", "missing item_dimensions") and are parsed to name the exact attributes at fault. This text is Amazon's, not the app's guess.`,
      `<b>Nothing is changed.</b> This step only reads. You draft edits against it, and only approved fields are pushed later.` ]},
    opt_diagnose: { title:"How 'Suggest fixes with AI' works", steps:[
      `<b>Re-reads the live listing</b> (<code>getListingsItem</code>) and collects ONLY the attributes Amazon flagged as missing or invalid.`,
      `<b>Asks the AI for values for just those fields.</b> The prompt AI (<code>${esc(T)}</code>) proposes values <i>only</i> for the flagged attributes. These are clearly labeled <b>AI estimates</b> — inferred, not from Amazon.`,
      `<b>You review and tick.</b> Nothing is pushed here. You edit/correct each suggestion and tick only the ones you want.`,
      `<b>Honest limit:</b> dimensions with units are safest finished in Seller Central, which structures the nested fields correctly.` ]},
    opt_push: { title:"How approved changes reach Amazon", steps:[
      `<b>Gated by your approval.</b> The push only runs with a <code>confirmed</code> flag, and only the fields you ticked are sent — nothing else.`,
      `<b>Builds a minimal patch.</b> <code>_build_patches</code> turns your approved fields into JSON-Patch operations, applied via SP-API <code>patchListingsItem</code> (a targeted edit, not a full re-submit).`,
      `<b>Only approved fields change</b> on the live listing; everything you didn't tick is left untouched.` ]},
    opt_rewrite: { title:"How 'Custom AI rewrite' works", steps:[
      `<b>Uses your instruction as the driver.</b> You tell the AI what you want (e.g. "no brand in title, emphasise durability"). A product link is optional extra context.`,
      `<b>Pulls source context if given.</b> Any eBay/Amazon link you paste is fetched and fed in so the AI knows the real product.`,
      `<b>Brand is optional context only.</b> The account's brand is passed as context but never forced into copy — and the app never falls back to the account label as a brand (this fixed the "label leaked into title" bug).`,
      `<b>Applies your compliance & IP rules.</b> The rewrite still runs under <code>compliance_rules.json</code> and <code>ip_rules.json</code> (forbidden phrases / safe words), so the new copy stays Amazon-safe.`,
      `<b>Returns a draft</b> (title/bullets/description) for your review — nothing is pushed automatically.` ]},
    // ---------- GENERATION PIPELINE ----------
    gen_pipeline: { title:"How 'Generate' builds a listing (the full pipeline)", steps:[
      `<b>1 · Scrapes the product.</b> For each source row it pulls real data: the eBay item (Browse API via <code>fetch_ebay_supplement</code> — specifics + images) and the competitor Amazon ASIN (<code>get_competitor_asin_data</code>, plus a crawl4ai PDP scrape as fallback). It also pulls pricing/fees and computes financials.`,
      `<b>2 · Writes the prompt.</b> <code>build_prompt</code> folds the scraped specifics, pricing, keywords (autocomplete) and your rules into a structured brief.`,
      `<b>3 · Generates the listing</b> with the Claude API (<code>generate_listing</code>) — title, bullets, description, and the product-type attributes Amazon's schema requires.`,
      `<b>4 · Runs the compliance + IP gates</b> (see the next two panels) — these can downgrade the status.`,
      `<b>5 · Builds the SKU</b> as <code>{source_price}_{N}Days_{COMP_ASIN}</code> (e.g. <code>7.99_3Days_B0XYZ12345</code>); duplicates get <code>_2</code>, <code>_3</code> appended.`,
      `<b>6 · Maps the flat-file route</b> (<code>detect_route</code> → FILE1 or FILE2) for the right Amazon template, and writes everything to your Google Sheet with a Status for review. <b>Nothing is submitted to Amazon here</b> — generation only fills the sheet.` ]},
    gen_compliance: { title:"How the compliance gate works", steps:[
      `<b>Checks the listing against your rules.</b> <code>check_compliance</code> screens the generated copy using <code>compliance_rules.json</code> (your 17 UK regulatory categories) for risky claims and category risk level.`,
      `<b>Can downgrade the status.</b> If the product falls in a HIGH-risk category, a <code>NEEDS_REVIEW</code> row is downgraded to <code>COMPLIANCE_HOLD</code> so you must review it before it can go live.`,
      `<b>Safety-net defaults</b> are applied where required fields are missing, so the listing isn't left in a non-compliant state silently.` ]},
    gen_ip: { title:"How the IP / trademark gate works", steps:[
      `<b>Screens for brand/trademark risk.</b> <code>check_ip_violations</code> matches the copy against <code>ip_rules.json</code> — your list of forbidden phrases (e.g. "compatible with X", "replacement for X") and ~470 safe words.`,
      `<b>IP_HOLD supersedes other holds.</b> If a forbidden phrase is found, the status is set to <code>IP_HOLD</code> — which overrides <code>NEEDS_REVIEW</code> and <code>COMPLIANCE_HOLD</code> (a hard ERROR stays an error).`,
      `<b>You review every hold.</b> The full status flow is: <code>NEEDS_REVIEW → COMPLIANCE_HOLD / IP_HOLD → APPROVED → export</code>. Only APPROVED rows are exported to the flat file.` ]},
    // ---------- LISTINGS GRID / SYNC ----------
    grid_load: { title:"How the listings grid loads", steps:[
      `<b>Pulls your live listings from Amazon.</b> <code>/live/catalog</code> requests a Reports-API report (<code>GET_MERCHANT_LISTINGS_ALL_DATA</code>) for the connected account + marketplace, then parses each row.`,
      `<b>Reads real fields per listing.</b> From the report it captures SKU, ASIN, title, price, quantity, status, brand, and — importantly — <code>fulfillment-channel</code> (FBA/FBM) and <code>merchant-shipping-group</code>.`,
      `<b>Caches briefly</b> so re-opening is instant. A normal load reuses a recent report/cache; it does <i>not</i> hit Amazon every time.`,
      `<b>Drafts vs Live vs All</b> just filters what's shown — Drafts are from your sheet, Live are pulled from Amazon, All merges both.` ]},
    grid_enrich: { title:"How each card gets its image, title, FBA/FBM & shipping", steps:[
      `<b>Enriches in batches.</b> <code>/live/images</code> calls <code>getListingsItem</code> with <code>includedData="summaries,issues,fulfillmentAvailability,attributes"</code> for the visible SKUs.`,
      `<b>Pulls the real main image and live title</b> (from <code>summaries</code>) — so the title reflects any edit you made immediately, not the cached report.`,
      `<b>Shows fulfillment + handling.</b> FBA/FBM comes from the fulfillment data; FBM handling time is the real <code>lead_time_to_ship_max_days</code>.`,
      `<b>Honest caveat on dates.</b> "Ships by / delivery ~" dates are <i>estimates</i> the app computes (FBM ≈ your handling + ~5d transit; FBA ≈ ~2d) — they are not Amazon's exact promised dates.` ]},
    grid_sync: { title:"How 'Sync' forces fresh data", steps:[
      `<b>Forces a brand-new report.</b> Sync sends <code>force=true</code>, which <i>skips</i> the report/cache reuse and generates a FRESH Reports-API report (this fixed the bug where Sync reused stale data).`,
      `<b>Clears the per-listing cache.</b> It drops the cached images/status/title/fulfillment for this account+marketplace, so everything re-pulls from Amazon.`,
      `<b>Use it after edits or going live.</b> Amazon can take a little time to reflect changes; if a fresh report isn't ready yet, Sync again in a minute and it loads.` ]},
    // ---------- ACCOUNTS / CONNECTION ----------
    acct_connect: { title:"How connecting an account to Amazon works", steps:[
      `<b>You provide SP-API credentials.</b> Seller/merchant ID, LWA client ID, LWA client secret, and a refresh token — the four things Amazon's Selling Partner API needs (<code>account_creds</code>).`,
      `<b>"Connected" = a real refresh token.</b> An account counts as connected only when its refresh token is real (not a <code>PUT_</code>/<code>ROTATE</code> placeholder). Until then it's <b>draft-only</b>: you can build and generate listings, but live features (pulling listings, optimize, submit) are disabled.`,
      `<b>Secrets stay local.</b> The client secret and refresh token are stored in your local <code>config.json</code> and shown as masked dots — the app never displays the saved values, and you can leave them blank to keep the existing ones.`,
      `<b>Each account is a workspace.</b> Account → Marketplace → Listings. Brands are data attached to an account, not a separate level.` ]},
    acct_marketplaces: { title:"How 'Detect marketplaces' works", steps:[
      `<b>Asks Amazon which marketplaces this account sells in.</b> Calls SP-API <code>getMarketplaceParticipations</code> (Sellers API) with the account's credentials.`,
      `<b>Maps IDs to codes</b> using the built-in marketplace table (e.g. <code>A1F83G8C2ARO7P</code> → UK, <code>ATVPDKIKX0DER</code> → US) and saves the detected codes onto the account.`,
      `<b>This is why the workspace shows real marketplaces</b> — the US/UK/DE tabs reflect where the account is actually live, pulled from Amazon, not typed in by hand.` ]},
    acct_brands: { title:"How 'Detect brands' works (and its honest limit)", steps:[
      `<b>Reads the brand field from live listings.</b> It derives the brands actually used on the account from the <code>brand</code> field in the listings report, merged with any brands you typed.`,
      `<b>Honest limit:</b> Amazon has no clean "list my Brand Registry brands" API — so this is what's <i>seen on live listings</i>, not a Brand Registry pull. Add or correct brands manually if needed.` ]},
    // ---------- COGS ----------
    cogs: { title:"How COGS & the profit estimate work", steps:[
      `<b>Two ways to know your cost.</b> <code>_resolve_cogs</code> uses a priority: a <b>manual override</b> you set per SKU wins; otherwise it reads the cost <b>embedded in the dropshipping SKU</b> (the <code>{source_price}_…</code> prefix).`,
      `<b>Bulk upload.</b> The COGS CSV (<code>/cogs/upload</code>) accepts SKU + cost rows and stores them as per-account overrides, so you can set many at once.`,
      `<b>Profit is an estimate.</b> <code>_estimate_profit</code> = price − COGS − a <b>15% referral fee</b> (default). It's a quick margin guide, not Amazon's exact fee — real fees vary by category and include other charges.`,
      `<b>Stored locally</b> in your COGS overrides file, keyed by account+SKU.` ]},
    // ---------- SUBMIT LIVE ----------
    submit_live: { title:"How 'Submit · go live' publishes to Amazon", steps:[
      `<b>Double-confirms the destination.</b> First it calls <code>/submit/target</code> to find the <b>active account</b> and marketplace, then shows you a confirm dialog <b>naming that exact account</b> — so you can't publish to the wrong store.`,
      `<b>Checks credentials exist.</b> If the view's marketplace has no SP-API credentials, it stops and tells you — nothing is sent.`,
      `<b>Publishes only APPROVED rows.</b> It runs <code>api_submit</code>, which creates or replaces live listings for every <b>APPROVED / API_READY</b> row in this view — rows still in NEEDS_REVIEW / holds are skipped.`,
      `<b>This is the only step that writes to Amazon.</b> Generation, optimize drafts, and image generation never publish — only this button does, and only after your confirmation.` ]},
    // ---------- RECIPES / MEDIA / A+ ----------
    recipes: { title:"How image recipes work", steps:[
      `<b>A recipe is a saved, reusable treatment.</b> It stores a template image + the instructions/changes you want (e.g. "droplets on the bottle, soft top light"), so you can apply the same look to any product without retyping it.`,
      `<b>Recipes are per-brand.</b> They're saved against the active brand, but the studio also exposes recipes from your <i>other</i> brands (clearly labelled) so you can reuse across.`,
      `<b>Applying a recipe</b> runs the normal pipeline: your product image is attached as reference and the recipe's instructions become the brief — the product itself stays identical, only the treatment is applied.`,
      `<b>Stored locally</b> in <code>image_recipes.json</code>.` ]},
    media: { title:"How the media library & auto-save work", steps:[
      `<b>Per-SKU folders.</b> Every product has its own media folder; <code>/media/list</code> shows the stored images grouped by SKU, and <code>/media/<sku>/<file></code> serves them.`,
      `<b>Auto-save on generation.</b> Every image the studio generates is written to that product's folder immediately (<code>generated_*.png</code>) — so results are never lost even if you close the window.`,
      `<b>Manual save & upload.</b> "Save to media" stores a chosen image; you can also upload your own images into a SKU's folder. Delete removes a file from the folder.`,
      `<b>These are local files</b> on your machine — separate from Amazon. You choose which to use when building a listing.` ]},
    aplus: { title:"How A+ Content generation works (and what Amazon requires)", steps:[
      `<b>Generates module images at Amazon's EXACT pixel dimensions.</b> The catalog (<code>_APLUS_MODULES</code>) holds each Basic and Premium module with its precise size (e.g. image+text 970×600, four-quadrant 220×220), so the output fits Amazon's A+ builder.`,
      `<b>Drafts the copy separately.</b> It writes the module text (≈70% visual / 30% text) and blocks prohibited claims — the text is drafted by the prompt AI for reliability, not baked into the image.`,
      `<b>Keeps your product faithful.</b> Your product image is always attached as the reference.`,
      `<b>Honest gating:</b> A+ requires <b>Amazon Brand Registry</b>; <b>Premium A+</b> additionally needs a Brand Story on all ASINs + 15 approved submissions in the last 12 months. The app builds the assets — <b>you upload them in Seller Central's A+ builder</b>.` ]}
  };
}
function howWorks(which){
  if(!window.LOGIC_VISIBLE) return "";
  const reg = LOGIC_REGISTRY();
  const b = reg[which]; if(!b) return "";
  return `<details class="howbox"><summary><span class="chev">▶</span> How this works — the actual steps behind the button</summary>
    <div class="howbody"><div style="font-weight:600;color:var(--text);margin-bottom:2px">${esc(b.title)}</div>
      <ol>${b.steps.map(s=>`<li>${s}</li>`).join("")}</ol>
      <div style="margin-top:6px;opacity:.8">Models shown reflect your current dropdown selections. Nothing is sent to Amazon — generated images only go to this product's media library for review.</div>
    </div></details>`;
}
// Inject disclosures that live in STATIC page HTML (not JS template literals).
// Called on boot and whenever the admin toggles logic visibility.
function refreshStaticHowPanels(){
  const map = {
    "genhow":  ['gen_pipeline','gen_compliance','gen_ip','submit_live'],
    "gridhow": ['grid_load','grid_enrich','grid_sync','cogs']
  };
  Object.keys(map).forEach(function(id){
    const el=document.getElementById(id);
    if(el){ el.innerHTML = (typeof howWorks==="function") ? map[id].map(function(k){return howWorks(k);}).join("") : ""; }
  });
}

function _studioAddResult(job, j, grid){
  grid=grid||document.getElementById("studio_results");
  const cardId="sres_"+Math.random().toString(36).slice(2);
  const label=esc(job.sku)+(job.strategy?(' · '+job.strategy.replace('_',' ')):'');
  let inner;
  if(j&&j.ok&&j.data_url){
    // stash the originating kind+payload so we can regenerate JUST this one
    STUDIO._reroll=STUDIO._reroll||{};
    if(j._kind&&j._payload){ STUDIO._reroll[cardId]={kind:j._kind, payload:j._payload, label:(job.strategy||job.sku)}; }
    const canReroll = !!(j._kind&&j._payload);
    const _driveLine = j.drive_direct_url
      ? `<div class="cc" style="color:#86d0a8;font-size:10.5px;padding:0 8px 4px">\u2713 saved to Drive</div>`
      : (j.drive_error
          ? `<div class="cc" style="color:#e3b768;font-size:10.5px;padding:0 8px 4px">Drive: ${esc(j.drive_error)}</div>`
          : (j.save_error
              ? `<div class="cc" style="color:#e0696b;font-size:10.5px;padding:0 8px 4px">Save: ${esc(j.save_error)}</div>`
              : ""));
    inner=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
      <div class="srescap">${label}</div>
      ${_driveLine}
      <div class="sresacts">
        <button class="ib" onclick="studioSave('${cardId}','${esc(job.sku)}')"><i class="ti ti-device-floppy"></i> Save to media</button>
        <button class="ib" onclick="studioDownload('${cardId}','${esc(job.sku)}')"><i class="ti ti-download"></i></button>
        <button class="ib" onclick="studioToDrive('${cardId}','${esc(job.sku)}')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
        ${canReroll?`<button class="ib" onclick="studioReroll('${cardId}')" title="Generate this one again (e.g. if a detail came out wrong)"><i class="ti ti-refresh"></i> Redo this</button>`:''}
        ${canReroll?`<button class="ib" onclick="studioRefine('${cardId}')" title="Tell the AI a small change to make to THIS image"><i class="ti ti-wand"></i> Refine…</button>`:''}
      </div>`;
    STUDIO.results[cardId]={data_url:j.data_url, sku:job.sku};
  } else {
    inner=`<div class="sresfail">✗ ${esc((j&&j.error)||'failed')}</div><div class="srescap">${label}</div>`;
  }
  const div=document.createElement("div");
  div.className="srescard"; div.id=cardId; div.innerHTML=inner;
  grid.appendChild(div);
}
async function studioReroll(cardId){
  const r=(STUDIO._reroll||{})[cardId]; if(!r){ toast("Can't redo this one."); return; }
  const card=document.getElementById(cardId);
  if(card){ card.innerHTML='<div class="srescap"><span class="genspin"></span> regenerating…</div>'; }
  const ep = r.kind==="concept" ? "/genimage/from_concept"
           : r.kind==="source" ? "/genimage/process_source"
           : r.kind==="secondary" ? "/genimage/secondary_v2"
           : r.kind==="aplus" ? "/genimage/generate"
           : "/genimage/recipe";
  try{
    const j=await (await fetch(ep,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(r.payload)})).json();
    if(j&&j.ok&&j.data_url){
      // auto-save the redo too
      try{ await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:r.payload.sku||r.payload.title||"", data_url:j.data_url})}); }catch(e){}
      if(card){
        STUDIO.results[cardId]={data_url:j.data_url, sku:(r.payload.title||"")};
        card.innerHTML=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
          <div class="srescap">${esc(r.label)} · redone</div>
          <div class="sresacts">
            <button class="ib" onclick="studioSave('${cardId}','')"><i class="ti ti-device-floppy"></i> Save to media</button>
            <button class="ib" onclick="studioDownload('${cardId}','')"><i class="ti ti-download"></i></button>
            <button class="ib" onclick="studioToDrive('${cardId}','')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
            <button class="ib" onclick="studioReroll('${cardId}')"><i class="ti ti-refresh"></i> Redo this</button>
          </div>`;
      }
    } else {
      if(card){ card.innerHTML='<div class="sresfail">✗ '+esc((j&&j.error)||'failed')+'</div>'; }
    }
  }catch(e){ if(card){ card.innerHTML='<div class="sresfail">✗ '+esc(String(e))+'</div>'; } }
}
async function studioRefine(cardId){
  const cur=(STUDIO.results||{})[cardId];
  const r=(STUDIO._reroll||{})[cardId];
  if(!cur||!cur.data_url){ toast("Nothing to refine here."); return; }
  const instruction=prompt("What small change should I make to this image?\n(e.g. \"make the background warmer\", \"remove the water droplets\", \"move the product slightly left\", \"make the text bigger\")");
  if(!instruction||!instruction.trim()) return;
  // figure out the kind from the original payload (main / secondary / aplus)
  let kind="main";
  if(r&&r.kind){ kind = (r.kind==="concept")?"main":(r.kind==="aplus"?"aplus":(r.kind==="secondary"?"secondary":"main")); }
  const card=document.getElementById(cardId);
  if(card){ card.innerHTML='<div class="srescap"><span class="genspin"></span> refining…</div>'; }
  // attach the ORIGINAL product reference so the edit can't drift the real product
  let origRef="";
  try{
    const sku=cur.sku||"";
    const it=_itemForSku(sku) || (STUDIO.items&&STUDIO.items[0]);
    origRef=_refImgForItem(it)||"";
  }catch(e){}
  const payload={
    image:cur.data_url, original_reference:origRef, instruction:instruction.trim(), kind:kind,
    title:(cur.sku||""), text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)
  };
  try{
    const j=await (await fetch("/genimage/refine",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload)})).json();
    if(j&&j.ok&&j.data_url){
      try{ await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:cur.sku||"", data_url:j.data_url})}); }catch(e){}
      STUDIO.results[cardId]={data_url:j.data_url, sku:cur.sku};
      // keep refine available so you can iterate (refine the refined image)
      if(j._kind&&j._payload){ STUDIO._reroll[cardId]={kind:j._kind, payload:j._payload, label:(STUDIO._reroll[cardId]?STUDIO._reroll[cardId].label:cur.sku)}; }
      if(card){
        card.innerHTML=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
          <div class="srescap">refined: ${esc(instruction.trim()).slice(0,40)}</div>
          <div class="sresacts">
            <button class="ib" onclick="studioSave('${cardId}','${esc(cur.sku||'')}')"><i class="ti ti-device-floppy"></i> Save to media</button>
            <button class="ib" onclick="studioDownload('${cardId}','${esc(cur.sku||'')}')"><i class="ti ti-download"></i></button>
            <button class="ib" onclick="studioToDrive('${cardId}','${esc(cur.sku||'')}')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
            <button class="ib" onclick="studioRefine('${cardId}')" title="Make another small change"><i class="ti ti-wand"></i> Refine…</button>
          </div>`;
      }
    } else {
      if(card){ card.innerHTML='<div class="sresfail">✗ '+esc((j&&j.error)||'failed')+'</div>'; }
      toast("Refine failed: "+((j&&j.error)||""));
    }
  }catch(e){ if(card){ card.innerHTML='<div class="sresfail">✗ '+esc(String(e))+'</div>'; } }
}
async function studioSave(cardId, sku){
  const r=STUDIO.results[cardId]; if(!r) return;
  try{
    const j=await (await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, data_url:r.data_url})})).json();
    if(j.ok){ r.savedUrl=j.url; toast("Saved to "+sku+" media library"); }
    else toast("Save failed: "+(j.error||""));
  }catch(e){ toast("Error: "+e); }
}
async function studioToDrive(cardId, sku){
  const r=STUDIO.results[cardId]; if(!r) return;
  // confirm a Drive folder is configured for this account
  let ds=null; try{ ds=await (await fetch("/drive/status")).json(); }catch(e){}
  if(!ds||!ds.ok||!ds.configured){
    toast("No Drive folder set for this account — add one in Account & sheets");
    return;
  }
  // ensure it's saved locally first (Drive upload reads the local file)
  if(!r.savedUrl){
    try{
      const sj=await (await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, data_url:r.data_url})})).json();
      if(sj.ok) r.savedUrl=sj.url; else { toast("Save failed: "+(sj.error||"")); return; }
    }catch(e){ toast("Error: "+e); return; }
  }
  const it=_itemForSku(sku);
  const pname=(it&&it.title)||(r.sku||"");
  toast("Uploading to Drive…");
  try{
    const j=await (await fetch("/drive/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, product_name:pname, relpath:r.savedUrl})})).json();
    if(j.ok) toast("Uploaded to Drive ✓");
    else toast("Drive upload failed: "+(j.error||""));
  }catch(e){ toast("Error: "+e); }
}
function _extFromDataUrl(durl){
  // Determine the TRUE image extension from the bytes, not the mime label (which
  // can be wrong -- e.g. JPEG bytes tagged image/png, which Amazon then rejects).
  try{
    if(!durl) return "jpg";
    if(/^https?:/i.test(durl)){
      const m=durl.split("?")[0].match(/\.(png|jpe?g|webp|gif)$/i);
      return m ? (m[1].toLowerCase()==="jpeg"?"jpg":m[1].toLowerCase()) : "jpg";
    }
    const comma=durl.indexOf(","); if(comma<0) return "jpg";
    const bin=atob(durl.slice(comma+1, comma+24));  // first few bytes are enough
    const b=[]; for(let i=0;i<bin.length;i++) b.push(bin.charCodeAt(i)&0xff);
    if(b[0]===0xff&&b[1]===0xd8&&b[2]===0xff) return "jpg";
    if(b[0]===0x89&&b[1]===0x50&&b[2]===0x4e&&b[3]===0x47) return "png";
    if(b[0]===0x52&&b[1]===0x49&&b[2]===0x46&&b[3]===0x46&&b[8]===0x57&&b[9]===0x45) return "webp";
    if(b[0]===0x47&&b[1]===0x49&&b[2]===0x46) return "gif";
  }catch(e){}
  return "jpg";
}
function studioDownload(cardId, sku){
  const r=STUDIO.results[cardId]; if(!r) return;
  // Prefer the full-resolution image URL if we have it; fall back to the inline
  // data. Convert to JPEG on download (Amazon-preferred, smaller files).
  const src = r.url || r.data_url;
  _downloadAsJpeg(src, (sku||"image"));
}
function _downloadAsJpeg(src, baseName){
  // Draw the image to a canvas and export JPEG, so downloads are always .jpg
  // regardless of the source format. Transparency is flattened onto white.
  try{
    const img=new Image();
    img.crossOrigin="anonymous";
    img.onload=function(){
      try{
        const c=document.createElement("canvas");
        c.width=img.naturalWidth||img.width; c.height=img.naturalHeight||img.height;
        const ctx=c.getContext("2d");
        ctx.fillStyle="#ffffff"; ctx.fillRect(0,0,c.width,c.height);
        ctx.drawImage(img,0,0);
        const jpeg=c.toDataURL("image/jpeg",0.9);
        const a=document.createElement("a"); a.href=jpeg; a.download=baseName+".jpg"; a.click();
      }catch(e){
        // tainted canvas (cross-origin) -> fall back to direct download of source
        const a=document.createElement("a"); a.href=src; a.download=baseName+".jpg"; a.click();
      }
    };
    img.onerror=function(){ const a=document.createElement("a"); a.href=src; a.download=baseName+".jpg"; a.click(); };
    img.src=src;
  }catch(e){
    const a=document.createElement("a"); a.href=src; a.download=baseName+".jpg"; a.click();
  }
}
async function loadSchemas(pts, force, mkt){
  const mp = (mkt||"").toString().toUpperCase();
  const q = (force?"?refresh=1":"") + (mp?((force?"&":"?")+"mkt="+encodeURIComponent(mp)):"");
  await Promise.all(pts.map(async pt=>{
    if(SCHEMAS[pt] && (SCHEMAS[pt].attrs||[]).length && !force)return;  // only skip if genuinely loaded
    try{const r=await fetch("/schema/"+encodeURIComponent(pt)+q);const j=await r.json();
        SCHEMAS[pt]=j.ok?{opts:(j.enums||{}),req:(j.required||[]),attrs:(j.attrs||[]),subs:(j.subfields||{}),titles:(j.titles||{}),_mkt:(j.marketplace||mp)}:{opts:{},req:[],attrs:[],subs:{},titles:{}};}catch(e){SCHEMAS[pt]={opts:{},req:[],attrs:[],subs:{},titles:{}};}
  }));
}
async function refreshSchemaFor(sku){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r)return;
  const pt=r.product_type; if(!pt){toast("No product type on this row");return;}
  delete SCHEMAS[pt];
  toast("Refreshing Amazon allowed values…");
  await loadSchemas([pt], true, rowMkt(r));
  if(DRAWER_SKU===sku){ openDrawer(sku); }
  else render();
  toast("Amazon values refreshed — dropdowns updated");
}

async function setStatus(sku,status,btn){
  if(!sku){toast("This row has no SKU yet");return;}
  btn.disabled=true; const old=btn.textContent; btn.textContent="…";
  try{
    const res=await fetch("/approve",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku,status})});
    const j=await res.json();
    if(j.ok){const r=ROWS.find(x=>x.sku===sku); if(r)r.status=status; render(); toast(status==="APPROVED"?"Approved":"Set to needs-review");}
    else {toast("Failed: "+j.error); btn.disabled=false; btn.textContent=old;}
  }catch(e){toast("Failed: "+e); btn.disabled=false; btn.textContent=old;}
}

function setFilter(el){
  document.querySelectorAll(".pill").forEach(p=>p.classList.remove("active"));
  el.classList.add("active"); FILTER=el.dataset.f; render();
}
function setFilterVal(v){
  FILTER=v||"all";
  // leaving brand settings panel if open
  var bp=document.getElementById('brandpanel'); if(bp&&bp.style.display!=='none'){ bp.style.display='none'; var g=document.getElementById('grid'); if(g) g.style.display=''; var sm=document.getElementById('summary'); if(sm) sm.style.display=''; }
  render();
}

let ES=null;
function showStop(on){ const b=document.getElementById("stopbtn"); if(b) b.disabled=!on; }
async function stopRun(){
  const b=document.getElementById("stopbtn"); if(b) b.disabled=true;
  try{ const r=await fetch("/stop",{method:"POST"}); const j=await r.json();
       toast(j.ok?"Stopping the run\u2026":("Stop: "+(j.error||"nothing running"))); }
  catch(e){ toast("Stop failed"); if(b) b.disabled=false; }
}
function genSelOnInput(){
  const v=(document.getElementById("gensel_value").value||"").toLowerCase();
  const dd=document.getElementById("gensel_type");
  const hint=document.getElementById("gensel_hint");
  const isUrl = v.includes("http://")||v.includes("https://")||v.includes("amazon.")||v.includes("ebay.");
  if(dd){ dd.disabled=isUrl; dd.style.opacity=isUrl?.45:1; }
  if(hint){ hint.textContent = isUrl
    ? "URL detected — the platform is read from the link, so the dropdown is ignored."
    : "Row numbers can be comma-separated (e.g. 2, 5, 7). For one product you can paste its URL — the dropdown is ignored then."; }
}
// ---- Miles Lubricants import ----
let MILES_ITEMS=[];
function milesPickFile(input){
  const f=input.files&&input.files[0];
  if(!f) return;
  const status=document.getElementById("miles_filestatus");
  status.textContent="Reading "+f.name+"…";
  const name=f.name.toLowerCase();
  if(name.endsWith(".csv")){
    const reader=new FileReader();
    reader.onload=e=>milesParseCSV(e.target.result, f.name);
    reader.readAsText(f);
  } else {
    // XLSX: parse with SheetJS if available, else ask for CSV
    if(typeof XLSX==="undefined"){
      status.textContent="Excel parsing needs CSV here — please save as CSV and re-upload.";
      return;
    }
    const reader=new FileReader();
    reader.onload=e=>{
      try{
        const wb=XLSX.read(new Uint8Array(e.target.result),{type:"array"});
        const ws=wb.Sheets[wb.SheetNames[0]];
        const rows=XLSX.utils.sheet_to_json(ws,{header:1});
        milesParseRows(rows, f.name);
      }catch(err){ status.textContent="Could not read Excel: "+err; }
    };
    reader.readAsArrayBuffer(f);
  }
}
function milesParseCSV(text, fname){
  const rows=text.split(/\r?\n/).map(l=>l.split(","));
  milesParseRows(rows, fname);
}
function milesParseRows(rows, fname){
  // find the item-number column: header match, else column 0
  const nameKeys=["item number","item_number","item","sku","product number","product_number","number"];
  let col=0, start=0;
  if(rows.length){
    const hdr=rows[0].map(c=>String(c||"").trim().toLowerCase());
    const idx=hdr.findIndex(h=>nameKeys.includes(h));
    if(idx>=0){ col=idx; start=1; }
    else if(!/^[a-z]{1,4}\d{4,}$|^\d{6,}$/i.test(hdr[0]||"")){ start=1; } // looks like header, skip
  }
  const seen=new Set(); const items=[];
  for(let i=start;i<rows.length;i++){
    const v=String((rows[i]||[])[col]||"").trim();
    if(!v || nameKeys.includes(v.toLowerCase())) continue;
    if(!seen.has(v)){ seen.add(v); items.push(v); }
  }
  MILES_ITEMS=items;
  document.getElementById("miles_filestatus").textContent=fname+" — "+items.length+" item number(s)";
  document.getElementById("miles_items").textContent = items.length? ("Items: "+items.slice(0,30).join(", ")+(items.length>30?" …":"")) : "No item numbers found in the file.";
  // upload to server
  fetch("/miles/upload",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({items})}).then(r=>r.json()).then(j=>{
      const btn=document.getElementById("miles_runbtn");
      if(btn) btn.disabled = !(j.ok && j.count>0);
    }).catch(()=>{});
}
function milesRun(){
  if(ES){toast("A run is already streaming");return;}
  if(!MILES_ITEMS.length){toast("Upload an item-number file first");return;}
  const log=document.getElementById("miles_log");
  if(log){ log.style.display="block"; log.textContent=""; }
  const skipDone = document.getElementById("miles_skip_done");
  const url = "/miles/run" + (skipDone && skipDone.checked ? "?skip_done=1" : "?skip_done=0");
  ES=new EventSource(url);
  const rb=document.getElementById("miles_runbtn"); if(rb) rb.disabled=true;
  const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=false;
  ES.onmessage=e=>{
    if(!log) return;
    const div=document.createElement("div");
    if(e.data.startsWith("[error]")) div.style.color="#ff8585";
    else if(e.data.startsWith("[done]")) div.style.color="#7ee08a";
    else if(e.data.startsWith("[start]")) div.style.color="#9cc1ff";
    else if(e.data.indexOf("NOT_FOUND")>=0||e.data.indexOf("NEEDS_REVIEW")>=0) div.style.color="#e3b768";
    div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;
    const rb=document.getElementById("miles_runbtn"); if(rb) rb.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
    milesLoadResults(); toast("Harvest + generation finished");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;
    const rb=document.getElementById("miles_runbtn"); if(rb) rb.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
    if(log){const d=document.createElement("div");d.style.color="#ff8585";d.textContent="[error] stream interrupted — check the app terminal for a Python traceback";log.appendChild(d);}
  }};
}
function milesSavePref(){
  // Persist the output Sheet ID/tab so it survives reloads until changed.
  const sheet=(document.getElementById("miles_sheet")||{}).value||"";
  const tab=(document.getElementById("miles_tab")||{}).value||"";
  fetch("/miles/sheet_pref",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({sheet:sheet.trim(),tab:tab.trim()})}).catch(()=>{});
}
function milesLoadPref(){
  // Pre-fill the saved Sheet ID/tab on open. Only fills empty fields so we never
  // clobber something the user just typed.
  fetch("/miles/sheet_pref").then(r=>r.json()).then(d=>{
    if(!d) return;
    const s=document.getElementById("miles_sheet");
    const t=document.getElementById("miles_tab");
    if(s && !s.value && d.sheet) s.value=d.sheet;
    if(t && !t.value && d.tab)   t.value=d.tab;
  }).catch(()=>{});
}
function milesGenerate(){
  if(ES){toast("A run is already streaming");return;}
  const log=document.getElementById("miles_log");
  if(log){ log.style.display="block"; log.textContent=""; }
  const sheet=(document.getElementById("miles_sheet")||{}).value||"";
  const tab=(document.getElementById("miles_tab")||{}).value||"";
  const lim=(document.getElementById("miles_limit")||{}).value||"";
  // Post params first, then open the SSE stream
  const params=new URLSearchParams();
  if(sheet.trim()) params.set("sheet", sheet.trim());
  if(tab.trim())   params.set("tab",   tab.trim());
  if(lim.trim() && parseInt(lim)>0) params.set("limit", parseInt(lim).toString());
  const useBA=(document.getElementById("miles_use_ba")||{}).checked;
  if(useBA) params.set("use_ba","1");
  // Store in sessionStorage so the SSE GET route can read them back
  sessionStorage.setItem("mg_sheet", sheet.trim());
  sessionStorage.setItem("mg_tab",   tab.trim());
  sessionStorage.setItem("mg_limit", (lim.trim() && parseInt(lim)>0) ? parseInt(lim).toString() : "");
  const qs=params.toString();
  ES=new EventSource("/miles/generate"+(qs?"?"+qs:""));
  const gb=document.getElementById("miles_genbtn"); if(gb) gb.disabled=true;
  const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=false;
  ES.onmessage=e=>{
    if(!log) return;
    const div=document.createElement("div");
    if(e.data.startsWith("[error]")) div.style.color="#ff8585";
    else if(e.data.startsWith("[done]")) div.style.color="#7ee08a";
    else if(e.data.startsWith("[start]")) div.style.color="#9cc1ff";
    div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;
    const gb=document.getElementById("miles_genbtn"); if(gb) gb.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
    loadRows(); toast("Draft generation finished");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;
    const gb=document.getElementById("miles_genbtn"); if(gb) gb.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;}};
}
function milesOptimize(){
  if(ES){toast("A run is already streaming");return;}
  const log=document.getElementById("miles_log");
  if(log){ log.style.display="block"; log.textContent=""; }
  const sheet=(document.getElementById("miles_sheet")||{}).value||"";
  const tab=(document.getElementById("miles_tab")||{}).value||"";
  const params=new URLSearchParams();
  if(sheet.trim()) params.set("sheet", sheet.trim());
  if(tab.trim())   params.set("tab",   tab.trim());
  const qs=params.toString();
  ES=new EventSource("/miles/optimize"+(qs?"?"+qs:""));
  const ob=document.getElementById("miles_optbtn"); if(ob) ob.disabled=true;
  const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=false;
  ES.onmessage=e=>{
    if(!log) return;
    const div=document.createElement("div");
    if(e.data.startsWith("[error]")) div.style.color="#ff8585";
    else if(e.data.startsWith("[done]")) div.style.color="#7ee08a";
    else if(e.data.startsWith("[start]")) div.style.color="#9cc1ff";
    div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;
    const ob=document.getElementById("miles_optbtn"); if(ob) ob.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
    loadRows(); toast("SQP optimization finished");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;
    const ob=document.getElementById("miles_optbtn"); if(ob) ob.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;}};
}
function milesStop(){
  // The Miles harvest is an SSE stream, not a subprocess. Cancel it server-side
  // (so the in-flight loop stops between items) and close the stream client-side.
  fetch("/miles/stop",{method:"POST"}).catch(()=>{});
  if(ES){ try{ES.close();}catch(e){} ES=null; }
  const log=document.getElementById("miles_log");
  if(log){ const d=document.createElement("div"); d.style.color="#e3b768"; d.textContent="[stopped] harvest cancelled by user"; log.appendChild(d); log.scrollTop=log.scrollHeight; }
  const rb=document.getElementById("miles_runbtn"); if(rb) rb.disabled=false;
  const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
  toast("Harvest stopped");
}
function milesClearHistory(){
  fetch("/miles/clear_history",{method:"POST"}).then(r=>r.json()).then(j=>{
    toast(j.ok ? ("Cleared "+(j.cleared||0)+" harvested item(s)") : "Could not clear history");
  }).catch(()=>toast("Could not clear history"));
}
function milesLoadResults(){
  fetch("/miles/results").then(r=>r.json()).then(j=>{
    const box=document.getElementById("miles_results");
    if(!box) return;
    if(!j.ok){ box.innerHTML=""; return; }
    const s=j.summary;
    let h='<div style="padding:12px;border:1px solid var(--line);border-radius:10px">';
    h+='<div style="font-weight:600;margin-bottom:8px">Harvest results</div>';
    h+='<div style="font-size:13px;margin-bottom:6px">✓ '+s.ok+' harvested · ⚠ '+s.needs_review.length+' need review · ✗ '+s.not_found.length+' not found · '+s.errors.length+' errors</div>';
    if(s.products.length){
      h+='<table style="width:100%;font-size:12px;border-collapse:collapse;margin-top:8px">';
      h+='<tr style="text-align:left;opacity:.7"><th style="padding:4px">Item</th><th style="padding:4px">Title</th><th style="padding:4px">PDFs</th><th style="padding:4px">SDS</th></tr>';
      s.products.forEach(p=>{ h+='<tr><td style="padding:4px">'+esc(p.item_number||"")+'</td><td style="padding:4px">'+esc((p.title||"").slice(0,50))+'</td><td style="padding:4px">'+p.pdf_count+'</td><td style="padding:4px">'+(p.has_sds?"✓":"—")+'</td></tr>'; });
      h+='</table>';
    }
    if(s.needs_review.length){
      h+='<div style="margin-top:10px;font-size:12px;color:#e3b768"><b>Manual review (multiple matches):</b> '+s.needs_review.map(x=>esc(x.item)).join(", ")+'</div>';
    }
    if(s.not_found.length){
      h+='<div style="margin-top:6px;font-size:12px;opacity:.7"><b>Not found:</b> '+s.not_found.map(x=>esc(x.item)).join(", ")+'</div>';
    }
    h+='</div>';
    box.innerHTML=h;
  }).catch(()=>{});
}

// ---------- PPC section ----------
function ppcOnOpen(){
  // set the context banner so the agent knows this is scoped per-workspace
  const el=document.getElementById("ppc_ctx");
  if(el){
    const acct=(CUR_ACCOUNT&&CUR_ACCOUNT.label)||"this workspace";
    const mkt=WS_MARKET||"UK";
    el.textContent=acct+" · "+mkt;
  }
}
function ppcAppendChat(who, text){
  const box=document.getElementById("ppc_chatlog"); if(!box) return;
  const div=document.createElement("div");
  div.style.margin="10px 0";
  div.style.fontSize="13px";
  div.style.lineHeight="1.5";
  const who_style = (who==="you") ? "color:#9cc1ff;font-weight:600" : "color:#7fdca0;font-weight:600";
  div.innerHTML='<div style="'+who_style+';font-size:11px;text-transform:uppercase;letter-spacing:.5px">'+esc(who)+'</div><div style="white-space:pre-wrap">'+esc(text)+'</div>';
  box.appendChild(div);
  box.scrollTop=box.scrollHeight;
}
async function ppcAgentSend(){
  const inp=document.getElementById("ppc_input"); if(!inp) return;
  const msg=(inp.value||"").trim(); if(!msg) return;
  inp.value=""; ppcAppendChat("you", msg);
  // spinner
  const box=document.getElementById("ppc_chatlog");
  const sp=document.createElement("div"); sp.className="cc"; sp.innerHTML='<span class="genspin"></span> thinking…';
  sp.style.margin="6px 0";
  box.appendChild(sp); box.scrollTop=box.scrollHeight;
  try{
    const acct=(CUR_ACCOUNT&&CUR_ACCOUNT.id)||"";
    const mkt=WS_MARKET||"UK";
    const j=await (await fetch("/ppc/agent",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({message:msg, account_id:acct, marketplace:mkt})})).json();
    sp.remove();
    if(!j.ok){ ppcAppendChat("agent", "Error: "+(j.error||"unknown")); return; }
    ppcAppendChat("agent", j.reply||"(empty response)");
    if(j.routed_skill){
      ppcAppendChat("agent", "Routed to skill: "+j.routed_skill+". "+(j.next_action||""));
    }
  }catch(e){
    sp.remove();
    ppcAppendChat("agent", "Request failed: "+String(e));
  }
}
function ppcOpenBuilder(){
  const m=document.getElementById("ppc_builder_modal");
  if(m){ m.classList.add("open"); }
}
function ppcCloseBuilder(){
  const m=document.getElementById("ppc_builder_modal");
  if(m){ m.classList.remove("open"); }
  const r=document.getElementById("pb_result"); if(r) r.innerHTML="";
}
async function ppcRunBuilder(){
  const asin=(document.getElementById("pb_asin").value||"").trim();
  const sku=(document.getElementById("pb_sku").value||"").trim();
  const name=(document.getElementById("pb_name").value||"").trim();
  const budget=parseFloat(document.getElementById("pb_budget").value||"8.0");
  const bid=parseFloat(document.getElementById("pb_bid").value||"0.30");
  const conquest=(document.getElementById("pb_conquest").value||"").split(",").map(s=>s.trim()).filter(Boolean);
  const compbrands=(document.getElementById("pb_compbrands").value||"").split(",").map(s=>s.trim()).filter(Boolean);
  const headterms=(document.getElementById("pb_headterms").value||"").split(",").map(s=>s.trim()).filter(Boolean);
  const fileEl=document.getElementById("pb_file");
  const resBox=document.getElementById("pb_result");
  if(!asin||!sku||!name){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">ASIN, SKU, and product short name are all required.</div>'; return; }
  if(asin===sku){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">SKU cannot equal ASIN. Use the seller SKU from Seller Central.</div>'; return; }
  if(!fileEl.files||!fileEl.files[0]){ resBox.innerHTML='<div style="color:#e3b768;font-size:12px;padding:8px;border:1px solid #4d3712;border-radius:6px;background:#241a10">Attach a keyword file (CSV from DataDive, Helium 10, or SQP).</div>'; return; }
  resBox.innerHTML='<div class="cc"><span class="genspin"></span> Bucketing keywords + building bulk file…</div>';
  const fd=new FormData();
  fd.append("file", fileEl.files[0]);
  fd.append("asin", asin);
  fd.append("sku", sku);
  fd.append("product_short_name", name);
  fd.append("daily_budget", String(budget));
  fd.append("default_bid", String(bid));
  fd.append("conquest_asins", JSON.stringify(conquest));
  fd.append("competitor_brands", JSON.stringify(compbrands));
  fd.append("category_heads", JSON.stringify(headterms));
  fd.append("marketplace", WS_MARKET||"UK");
  try{
    const j=await (await fetch("/ppc/build_campaigns",{method:"POST", body:fd})).json();
    if(!j.ok){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"build failed")+'</div>'; return; }
    const v=j.validation||{};
    let html='<div style="padding:10px;border:1px solid var(--line);border-radius:8px">';
    html+='<div style="font-weight:600;margin-bottom:6px;color:'+(v.ok?'#7fdca0':'#e3b768')+'">'+(v.ok?'✓ Built + validated':'⚠ Built but validation flagged issues')+'</div>';
    html+='<div style="font-size:12px;line-height:1.6">';
    html+='Rows: <b>'+(j.row_count||0)+'</b> · Unique keywords: <b>'+(j.unique_keywords||0)+'</b> · Campaigns: <b>'+(j.campaign_count||0)+'</b><br>';
    html+='Buckets: core '+(j.bucket_counts.core||0)+' · head '+(j.bucket_counts['category-head']||0)+' · comp '+(j.bucket_counts.competitor||0)+' · drop '+(j.bucket_counts.drop||0);
    html+='</div>';
    if(v.errors&&v.errors.length){
      html+='<div style="margin-top:8px;font-size:12px;color:#e0696b"><b>Errors (must fix before upload):</b><br>'+v.errors.map(esc).join("<br>")+'</div>';
    }
    if(v.warnings&&v.warnings.length){
      html+='<div style="margin-top:8px;font-size:12px;color:#e3b768"><b>Warnings:</b><br>'+v.warnings.map(esc).join("<br>")+'</div>';
    }
    html+='<div style="margin-top:10px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Download bulk CSV</a></div>';
    html+='</div>';
    resBox.innerHTML=html;
  }catch(e){
    resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

function ppcOpenHarvest(){
  const m=document.getElementById("ppc_harvest_modal");
  if(m){ m.classList.add("open"); }
}
function ppcCloseHarvest(){
  const m=document.getElementById("ppc_harvest_modal");
  if(m){ m.classList.remove("open"); }
  const r=document.getElementById("ph_result"); if(r) r.innerHTML="";
}
async function ppcRunHarvest(){
  const asin=(document.getElementById("ph_asin").value||"").trim();
  const sku=(document.getElementById("ph_sku").value||"").trim();
  const name=(document.getElementById("ph_name").value||"").trim();
  const be=parseFloat(document.getElementById("ph_be").value||"0.35");
  const bid=parseFloat(document.getElementById("ph_bid").value||"0.30");
  const budget=parseFloat(document.getElementById("ph_budget").value||"8.0");
  const fileEl=document.getElementById("ph_file");
  const tgtEl=document.getElementById("ph_targeted");
  const resBox=document.getElementById("ph_result");
  if(!asin||!sku||!name){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">ASIN, SKU, and product short name are all required.</div>'; return; }
  if(asin===sku){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">SKU cannot equal ASIN.</div>'; return; }
  if(!fileEl.files||!fileEl.files[0]){ resBox.innerHTML='<div style="color:#e3b768;font-size:12px;padding:8px;border:1px solid #4d3712;border-radius:6px;background:#241a10">Upload the SP Search Term Report CSV.</div>'; return; }
  resBox.innerHTML='<div class="cc"><span class="genspin"></span> Classifying every term, applying $10 rule + break-even ACOS…</div>';
  const fd=new FormData();
  fd.append("file", fileEl.files[0]);
  fd.append("asin", asin);
  fd.append("sku", sku);
  fd.append("product_short_name", name);
  fd.append("break_even_acos", String(be));
  fd.append("default_bid", String(bid));
  fd.append("daily_budget", String(budget));
  fd.append("marketplace", WS_MARKET||"UK");
  if(tgtEl&&tgtEl.files&&tgtEl.files[0]) fd.append("targeted_file", tgtEl.files[0]);
  try{
    const j=await (await fetch("/ppc/harvest",{method:"POST", body:fd})).json();
    if(!j.ok){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"harvest failed")+'</div>'; return; }
    const t=j.totals||{}, c=j.counts||{};
    let html='<div style="padding:10px;border:1px solid var(--line);border-radius:8px">';
    html+='<div style="font-weight:600;margin-bottom:6px;color:#7fdca0">✓ Harvest complete</div>';
    html+='<div style="font-size:12px;line-height:1.7">';
    html+='Terms: <b>'+(t.total_terms||0)+'</b> · Total spend: <b>'+(t.total_spend||0)+'</b> · Total sales: <b>'+(t.total_sales||0)+'</b> · Orders: <b>'+(t.total_orders||0)+'</b><br>';
    html+='Ready for harvest: <b style="color:#7fdca0">'+(t.harvest_ready||0)+'</b> new converting terms (excluded '+j.excluded_already_targeted+' already-targeted)<br>';
    html+='Ready for negation: <b style="color:#e0696b">'+(t.negatives_ready||0)+'</b> past-$10 zero-order terms';
    html+='</div>';
    html+='<div style="margin:10px 0;display:flex;flex-wrap:wrap;gap:6px;font-size:12px">';
    Object.keys(c).forEach(k=>{
      const col = k==='CONVERTING'?'#7fdca0': (k==='OVER-$10-CUT'||k==='CLICKS-NO-SALE')?'#e0696b': (k==='CONVERTS-BUT-HIGH-ACOS'||k==='HIGH-SPEND-WATCH')?'#e3b768':'#9cc1ff';
      html+='<span style="padding:3px 8px;border-radius:4px;background:'+col+'22;color:'+col+';border:1px solid '+col+'55">'+esc(k)+': '+c[k]+'</span>';
    });
    html+='</div>';
    html+='<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">';
    if(j.downloads.status_xlsx){
      html+='<a href="'+j.downloads.status_xlsx+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Status (coloured xlsx)</a>';
    }
    html+='<a href="'+j.downloads.status+'" class="mktbtn" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Status (CSV)</a>';
    html+='<a href="'+j.downloads.harvest+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Harvest bulk</a>';
    html+='<a href="'+j.downloads.negatives+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Negatives bulk</a>';
    html+='</div>';
    html+='</div>';
    resBox.innerHTML=html;
  }catch(e){
    resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

// Deliverable modal shared by audit / dashboard / forecast / weekly-deck
let PPC_DELIV_SKILL="";
function ppcOpenDeliverable(skill, title, desc){
  PPC_DELIV_SKILL = skill;
  document.getElementById("pd_title").innerHTML='<i class="ti ti-file"></i> '+esc(title);
  document.getElementById("pd_desc").textContent = desc;
  const m=document.getElementById("ppc_deliv_modal");
  if(m){ m.classList.add("open"); }
  const r=document.getElementById("pd_result"); if(r) r.innerHTML="";
}
function ppcCloseDeliv(){
  const m=document.getElementById("ppc_deliv_modal");
  if(m){ m.classList.remove("open"); }
  const r=document.getElementById("pd_result"); if(r) r.innerHTML="";
  PPC_DELIV_SKILL="";
}
async function ppcRunDeliv(){
  const filesEl=document.getElementById("pd_files");
  const ctxEl=document.getElementById("pd_context");
  const resBox=document.getElementById("pd_result");
  const skill = PPC_DELIV_SKILL;
  if(!skill){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">No capability selected — try again from a shortcut.</div>'; return; }
  const files = filesEl && filesEl.files ? Array.from(filesEl.files) : [];
  if(!files.length){ resBox.innerHTML='<div style="color:#e3b768;font-size:12px;padding:8px;border:1px solid #4d3712;border-radius:6px;background:#241a10">Attach at least one file so I can detect its family and act on real data.</div>'; return; }
  resBox.innerHTML='<div class="cc"><span class="genspin"></span> Detecting file families + building deliverable…</div>';
  const fd=new FormData();
  fd.append("skill", skill);
  fd.append("context", (ctxEl && ctxEl.value)||"");
  fd.append("account_id", (CUR_ACCOUNT&&CUR_ACCOUNT.id)||"");
  fd.append("marketplace", WS_MARKET||"UK");
  files.forEach((f,i)=>fd.append("files", f, f.name));
  try{
    const j=await (await fetch("/ppc/deliverable",{method:"POST", body:fd})).json();
    if(!j.ok){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"failed")+'</div>'; return; }
    let html='<div style="padding:10px;border:1px solid var(--line);border-radius:8px">';
    // Files detected
    html+='<div style="font-weight:600;margin-bottom:6px;color:#9cc1ff">Files detected</div>';
    html+='<ul style="font-size:12px;margin:0 0 8px 18px;line-height:1.6">';
    (j.file_summary||[]).forEach(f=>{
      const tag = f.family ? '<span style="color:#7fdca0">'+esc(f.family)+'</span>' : '<span style="color:#e3b768">unknown</span>';
      html+='<li>'+esc(f.filename)+' → '+tag+' ('+f.row_count+' rows)</li>';
    });
    html+='</ul>';
    // Missing inputs
    if(j.missing && j.missing.length){
      html+='<div style="margin-top:10px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:12px">';
      html+='<b>Still needed to build the deliverable:</b><ul style="margin:6px 0 0 18px">';
      j.missing.forEach(m=>html+='<li>'+esc(m)+'</li>');
      html+='</ul></div>';
    }
    // Downloads
    if(j.downloads && Object.keys(j.downloads).length){
      html+='<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">';
      Object.entries(j.downloads).forEach(([k,url])=>{
        const label = k==='audit_docx'?'Audit (docx)':
                      k==='dashboard_html'?'Dashboard (HTML)':
                      k==='forecast_xlsx'?'Forecast (xlsx)':
                      k==='weekly_deck_pptx'?'Weekly deck (pptx)': k;
        html+='<a href="'+url+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ '+esc(label)+'</a>';
      });
      html+='</div>';
    }
    // Analysis text
    if(j.reply){
      html+='<div style="font-weight:600;margin:12px 0 6px;color:#7fdca0">Executive note</div>';
      html+='<div style="white-space:pre-wrap;font-size:13px;line-height:1.5">'+esc(j.reply)+'</div>';
    }
    html+='</div>';
    resBox.innerHTML=html;
  }catch(e){
    resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}
// ---------- /PPC section ----------

// ---------- Inventory section ----------
async function invRunBuild(){
  const resBox = document.getElementById("inv_result");
  const pl3 = document.getElementById("inv_pl3");
  const sales = document.getElementById("inv_sales");
  const yoy = document.getElementById("inv_yoy");
  const pd = document.getElementById("inv_pd");
  if(!pl3.files || !pl3.files[0]){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">3PL stock CSV is required.</div>'; return; }
  if(!sales.files || !sales.files[0]){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">Daily sales CSV is required.</div>'; return; }
  resBox.innerHTML='<div class="cc"><span class="genspin"></span> Pulling FBA inventory from SP-API + computing replenishment for every SKU…</div>';
  const fd = new FormData();
  fd.append("pl3_file", pl3.files[0]);
  fd.append("sales_file", sales.files[0]);
  if(yoy.files && yoy.files[0]) fd.append("yoy_file", yoy.files[0]);
  if(pd.files && pd.files[0]) fd.append("pd_file", pd.files[0]);
  fd.append("target_normal_days", document.getElementById("inv_normal").value || "85");
  fd.append("reorder_cycle_days", document.getElementById("inv_reorder").value || "5");
  fd.append("target_long_days", document.getElementById("inv_long").value || "110");
  fd.append("marketplace", WS_MARKET || "UK");
  fd.append("cycle_label", document.getElementById("inv_cycle").value || "");
  try{
    const j = await (await fetch("/inventory/build",{method:"POST", body:fd})).json();
    if(!j.ok){
      resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"build failed")+'</div>';
      return;
    }
    const s = j.summary || {};
    const c = j.sku_coverage || {};
    let html = '<div style="padding:12px;border:1px solid var(--line);border-radius:8px">';
    html += '<div style="font-weight:600;margin-bottom:8px;color:#7fdca0">✓ Replenishment sheet built</div>';
    html += '<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-bottom:10px">';
    html += '<div><b>'+j.row_count+'</b> SKUs total</div>';
    html += '<div><b style="color:#ffd76b">'+(s.replenish_yes||0)+'</b> flagged for replenishment</div>';
    html += '<div><b style="color:#7fdca0">'+(s.units_flagged||0)+'</b> units to reorder</div>';
    if(s.stockout_risk_skus){
      html += '<div><b style="color:#e0696b">'+s.stockout_risk_skus+'</b> stockout-risk SKUs (DOS &lt; 14)</div>';
    }
    html += '</div>';
    html += '<div style="font-size:11px;opacity:.75;margin-bottom:10px">SKU coverage — FBA (SP-API): '+(c.in_fba||0)+' · 3PL upload: '+(c.in_3pl||0)+' · Sales upload: '+(c.in_sales||0);
    if(c.in_yoy) html += ' · YoY: '+c.in_yoy;
    if(c.in_pd) html += ' · PD: '+c.in_pd;
    html += ' · Union: <b>'+(c.union||0)+'</b></div>';
    if(j.warnings && j.warnings.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:11px">';
      html += '<b>SP-API warnings:</b><br>' + j.warnings.map(esc).join("<br>");
      html += '</div>';
    }
    html += '<div style="margin-top:12px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:8px 14px">⬇ Download replenishment xlsx</a></div>';
    html += '</div>';
    resBox.innerHTML = html;
  }catch(e){
    resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

// ---------- v2 inventory handler (SP-API auto-fetch, 4-bucket classification) ----------
async function inv2Run(){
  const resBox = document.getElementById("inv2_result");
  const acctId = (CUR_ACCOUNT && CUR_ACCOUNT.id) || "";
  if(!acctId){
    resBox.innerHTML = '<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">No workspace/account selected. Pick one from the sidebar first.</div>';
    return;
  }
  resBox.innerHTML = '<div class="cc"><span class="genspin"></span> Running inventory model — fetching FBA + sales from SP-API (5-15 min if cache is stale, instant if cached)…</div>';

  const fd = new FormData();
  fd.append("account_id", acctId);
  fd.append("marketplace", WS_MARKET || "US");
  fd.append("target_normal_dos",       document.getElementById("inv2_normal").value  || "85");
  fd.append("reorder_cycle_days",      document.getElementById("inv2_reorder").value || "5");
  fd.append("target_long_horizon_dos", document.getElementById("inv2_long").value    || "110");
  fd.append("sales_window_days",       document.getElementById("inv2_window").value  || "30");
  fd.append("cache_hours",             document.getElementById("inv2_cache").value   || "6");
  fd.append("force_refresh",           document.getElementById("inv2_force").checked ? "true" : "false");
  const three_pl_file = document.getElementById("inv2_3pl");
  if(three_pl_file.files && three_pl_file.files[0]) fd.append("three_pl_file", three_pl_file.files[0]);

  try{
    const j = await (await fetch("/inventory/v2/run",{method:"POST", body:fd})).json();
    if(!j.ok){
      resBox.innerHTML = '<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"run failed")+'</div>';
      return;
    }
    const s = j.summary || {};
    let html = '<div style="padding:12px;border:1px solid var(--line);border-radius:8px">';
    html += '<div style="font-weight:600;margin-bottom:8px;color:#7fdca0">✓ Inventory model complete</div>';

    // Bucket counts
    html += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px;font-size:12px">';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#1c3a1c;color:#8adca0;border:1px solid #2a7a2a">ACTIVE '+(s.active||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a3a1c;color:#ffe066;border:1px solid #7a7a2a">NEW_LAUNCH '+(s.new_launch||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a2f1a;color:#ffce7a;border:1px solid #7a5a2a">DORMANT '+(s.dormant||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a1f1f;color:#ff8a8a;border:1px solid #7a2a2a">DEAD '+(s.dead||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#1c2a3a;color:#8ac0ff;border:1px solid #2a5a7a">Total '+(s.total_skus||0)+'</div>';
    html += '</div>';

    // Reorder summary
    html += '<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-bottom:10px">';
    html += '<div><b style="color:#ffd76b">'+(s.fba_reorder_count||0)+'</b> SKUs need FBA reorder</div>';
    html += '<div><b>'+Math.round(s.total_fba_units_needed||0).toLocaleString()+'</b> total FBA units</div>';
    if(s.three_pl_reorder_count) html += '<div><b>'+s.three_pl_reorder_count+'</b> SKUs need 3PL reorder</div>';
    html += '</div>';

    // Data sources
    html += '<div style="font-size:11px;opacity:.75;margin-bottom:10px;line-height:1.5">';
    html += '<b>FBA source:</b> '+esc(j.fba_source||"")+'<br>';
    html += '<b>Velocity source:</b> '+esc(j.velocity_source||"");
    html += '</div>';

    // Sample alerts
    if(j.alerts_sample && j.alerts_sample.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:11px">';
      html += '<b>Sample alerts (first 10):</b>';
      html += '<ul style="margin:6px 0 0 18px">';
      j.alerts_sample.forEach(a=>{
        html += '<li>'+esc(a.sku)+' — '+esc(a.alert)+'</li>';
      });
      html += '</ul></div>';
    }
    if(j.three_pl_warnings && j.three_pl_warnings.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:11px">';
      html += '<b>3PL CSV warnings:</b><br>'+j.three_pl_warnings.map(esc).join("<br>");
      html += '</div>';
    }
    html += '<div style="margin-top:12px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:8px 14px">⬇ Download inventory xlsx</a></div>';
    html += '</div>';
    resBox.innerHTML = html;

    // Refresh the sidebar alert badge
    invBadgeRefresh();
  }catch(e){
    resBox.innerHTML = '<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

// Polls /inventory/v2/alerts and updates the sidebar red badge
async function invBadgeRefresh(){
  const badge = document.getElementById("inv_badge");
  if(!badge) return;
  const acctId = (CUR_ACCOUNT && CUR_ACCOUNT.id) || "";
  if(!acctId){ badge.style.display="none"; return; }
  try{
    const j = await (await fetch("/inventory/v2/alerts?account_id="+encodeURIComponent(acctId))).json();
    const n = j.count || 0;
    if(n > 0){
      badge.textContent = n;
      badge.style.display = "inline-block";
    } else {
      badge.style.display = "none";
    }
  }catch(e){ /* silent */ }
}
// ---------- /Inventory section ----------

function runMode(mode, skus){
  if(ES){toast("A run is already streaming");return;}
  const log=document.getElementById("log");
  log.style.display="block"; log.textContent="";
  let url="/run/"+mode;
  // Generate-only: pass the row selection (value + type). Empty -> generate all.
  if(mode==="generate"){
    const valEl=document.getElementById("gensel_value");
    const typeEl=document.getElementById("gensel_type");
    const val=(valEl&&valEl.value||"").trim();
    if(val){
      const params=new URLSearchParams();
      params.set("select", val);
      // when a URL is pasted the dropdown is disabled; send 'auto' so the server auto-detects
      params.set("select_type", (typeEl&&!typeEl.disabled)? typeEl.value : "auto");
      url += "?"+params.toString();
    }
  }
  // Preview/Submit: if specific SKUs are passed (the user's SELECTION), scope the
  // run to exactly those. Empty -> the server's default (all approved/ready rows).
  if((mode==="api"||mode==="api_submit") && skus && skus.length){
    url += (url.indexOf("?")>=0?"&":"?")+"skus="+encodeURIComponent(skus.join(","));
  }
  ES=new EventSource(url);
  showStop(true);
  ES.onmessage=e=>{
    const cls = e.data.startsWith("[start]")?"start":e.data.startsWith("[done]")?"done":"l";
    const div=document.createElement("div"); div.className=cls; div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;showStop(false);loadRows();toast("Run finished");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;showStop(false);loadRows();}};
}
// ---- Per-listing Preview / Submit ----
function _streamRun(url, doneMsg){
  if(ES){toast("A run is already streaming");return;}
  let log=document.getElementById("log");
  if(log){ log.style.display="block"; log.textContent=""; }
  ES=new EventSource(url);
  ES.onmessage=e=>{
    if(!log) return;
    const cls=e.data.startsWith("[start]")?"start":e.data.startsWith("[done]")?"done":"l";
    const div=document.createElement("div"); div.className=cls; div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;loadRows();toast(doneMsg||"Done");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;loadRows();}};
}
function _runPanel(sku){
  const p=document.getElementById("runpanel_"+sid(sku));
  if(!p) return null;
  return {
    box:p,
    title:p.querySelector(".runtitle"),
    verdict:p.querySelector(".runverdict"),
    log:p.querySelector(".runlog"),
    show(t){ p.style.display="block"; this.title.textContent=t; this.verdict.innerHTML=""; this.log.textContent=""; }
  };
}
// Stream a run INTO the listing's own panel, parsing Amazon's response into a
// clear verdict (accepted / needs fields / error).
function _streamRunPanel(url, sku, mode){
  // clear any stale stream first so a previous run can't block this one
  if(ES){ try{ES.close();}catch(e){} ES=null; }
  window.RUN_STREAMING=true;   // block render() from rebuilding the drawer mid-run
  const P=_runPanel(sku);
  if(P) P.show((mode==="submit"?"Submitting ":"Previewing ")+sku+" …");
  let sawStart=false, lines=[], verdict=null, warnings="", done=false;
  ES=new EventSource(url);
  ES.onmessage=e=>{
    const d=e.data||"";
    lines.push(d);
    if(P){ P.log.textContent+=d+"\n"; P.log.scrollTop=P.log.scrollHeight; }
    if(d.indexOf("[busy]")>=0){ verdict={kind:"busy", raw:d}; }
    if(d.startsWith("[start]")){ sawStart=true; if(P) P.verdict.innerHTML='<span class="rspin"></span> Request sent to Amazon… waiting for response.'; }
    // parse the per-row result line for THIS sku
    if(d.indexOf(sku)>=0){
      const low=d.toLowerCase();
      let m=d.match(/(\d+)\s+error\(s\)/i);
      if(m){ verdict={kind:"error", n:parseInt(m[1]), raw:d}; }
      else if(low.indexOf("missing")>=0 && low.indexOf("skip")>=0){ verdict={kind:"missing", raw:d}; }
      else if(low.indexOf("api_ready")>=0 || low.indexOf("preview clean")>=0){ verdict={kind:"ok_preview", raw:d}; }
      else if(low.indexOf("live")>=0 || low.indexOf("submitted")>=0){ verdict={kind:"ok_submit", raw:d}; }
      else if(low.indexOf("api call failed")>=0 || low.indexOf("api_error")>=0){ verdict={kind:"error", n:0, raw:d}; }
      const wm=d.match(/warnings?:\s*(.+)$/i); if(wm) warnings=wm[1];
    }
    if(d.toLowerCase().indexOf("none of the requested")>=0 && !verdict){ verdict={kind:"notfound", raw:d}; }
    if(d.toLowerCase().indexOf("no seller_id")>=0) verdict={kind:"nocreds", raw:d};
    // network / DNS failure (e.g. "getaddrinfo failed", "Failed to resolve",
    // "Max retries exceeded", "NameResolutionError") -> the script couldn't even
    // reach Google/Amazon, so this is a connectivity problem, not a listing one.
    {
      const dl=d.toLowerCase();
      if(/getaddrinfo failed|failed to resolve|nameresolutionerror|max retries exceeded|connectionerror|transporterror|errno 11002|temporary failure in name resolution|connection timed out|handshake operation timed out/.test(dl)){
        verdict={kind:"network", raw:d};
      }
    }
  };
  function finish(){
    if(done) return; done=true;
    if(ES){ ES.close(); ES=null; }
    // NOTE: keep window.RUN_STREAMING = true so render() won't rebuild the drawer
    // and wipe this panel. It's cleared when YOU close the panel (the ✕ button).
    // NOTE: deliberately do NOT call loadRows() here -- it rebuilds the grid and
    // the open drawer, which would wipe this panel. The status is written to the
    // sheet regardless; the panel stays so you can read the result + full log.
    if(!P) return;
    if(!sawStart){
      if(verdict && verdict.kind==="busy"){ P.verdict.innerHTML='<span class="rwarn">A previous Preview/Submit for this account is still finishing (it may be retrying a slow schema download). Wait ~10\u201320 seconds and click Preview again \u2014 the app clears the lock automatically once that run ends or its process exits, so you won\u2019t stay stuck.</span>'; return; }
      P.verdict.innerHTML='<span class="rbad">✗ The run didn\u2019t start. Check that the generator script is reachable.</span>'; return;
    }
    if(verdict && verdict.kind==="network"){
      // Distinguish the common case where ONLY the schema CDN host failed to
      // resolve (the API host worked) -- that points at DNS, not bandwidth.
      const _raw=String(verdict.raw||"");
      const _cdnOnly=/schema host DNS lookup failed|schema download failed[^]*getaddrinfo|no schema for/i.test(_raw)
                     && /seller:|marketplace:|fetching schema/i.test(_raw);
      if(_cdnOnly){
        P.verdict.innerHTML='<div class="rbad">✗ DNS couldn\u2019t resolve Amazon\u2019s schema host.</div>'
          +'<div class="rmsg">Your connection is fine and Amazon\u2019s main API resolved \u2014 but the separate <b>schema CDN host</b> failed a DNS lookup (Errno 11002). Fast internet doesn\u2019t fix this; it\u2019s name-resolution, not speed. This almost always means something is filtering DNS.</div>'
          +'<div class="rhint"><b>Most effective fixes, in order:</b><br>1) <b>Disable any VPN/proxy</b> (the #1 cause \u2014 they reroute DNS).<br>2) Change your DNS to <code>1.1.1.1</code> or <code>8.8.8.8</code> (Wi\u2011Fi \u2192 Properties \u2192 DNS). Public DNS resolves Amazon\u2019s CDN reliably.<br>3) Run <code>ipconfig /flushdns</code> then Preview again.<br>4) Check no firewall/antivirus or hosts\u2011file rule is blocking Amazon CDN domains.</div>';
        return;
      }
      P.verdict.innerHTML='<div class="rbad">✗ Network problem — couldn\u2019t reach Google/Amazon to run this.</div>'
        +'<div class="rmsg">Your computer failed a DNS lookup, so the app never got to validate the listing. This is a connection issue, not a problem with the listing.</div>'
        +'<div class="rhint"><b>Try this:</b> 1) Preview again (often transient). 2) If you\u2019re on a <b>VPN/proxy</b>, turn it off. 3) Open Command Prompt and run <code>ipconfig /flushdns</code>, then retry. 4) Switch your DNS to <code>1.1.1.1</code> or <code>8.8.8.8</code>. 5) Confirm your internet is up by opening any website.</div>';
      return;
    }
    if(!verdict){ P.verdict.innerHTML='<span class="rwarn">Finished, but no result line was found for this SKU. Open the log below to read exactly what happened.</span>'; return; }
    if(verdict.kind==="nocreds"){ P.verdict.innerHTML='<span class="rbad">✗ No SP-API credentials for this account/marketplace.</span> Add them in the account editor before publishing.'; return; }
    if(verdict.kind==="missing"){
      P.verdict.innerHTML='<div class="rbad">✗ This row is missing a SKU or Product Type in the sheet.</div>'
        +'<div class="ramz">'+esc(verdict.raw.trim())+'</div>'
        +'<div class="rhint">Open the listing in the sheet/editor and make sure both <b>SKU</b> and <b>Product Type</b> are filled, then Preview again.</div>';
      return;
    }
    if(verdict.kind==="notfound"){
      P.verdict.innerHTML='<div class="rwarn">This SKU wasn\u2019t found to validate in this account\u2019s sheet/tab.</div>'
        +'<div class="rhint">Make sure you\u2019re in the right account workspace and the listing is in this tab, with <b>SKU</b> and <b>Product Type</b> columns filled.</div>';
      return;
    }
    if(verdict.kind==="error"){
      // A timeout is NOT a rejection -- the call never completed validation. Show
      // it as a connection slowness so the user doesn't go hunting for fields.
      if(/timed out|timeout|read operation|TIMED OUT/i.test(String(verdict.raw||""))){
        P.verdict.innerHTML='<div class="rbad">\u2717 The validation call to Amazon timed out.</div>'
          +'<div class="rmsg">This is <b>not</b> a problem with your listing \u2014 the call to Amazon\u2019s UK/EU endpoint was too slow to finish. The app already retried automatically.</div>'
          +'<div class="rhint"><b>Try this:</b> 1) Preview again (often works on the next try). 2) If you\u2019re on a VPN/proxy, turn it off \u2014 it adds latency to the EU endpoint. 3) Switch DNS to <code>1.1.1.1</code>. 4) If it keeps timing out, your connection to Amazon EU is slow right now \u2014 wait a moment and retry.</div>';
        return;
      }
      const msg=esc(verdict.raw.replace(/^.*error\(s\)\)?/i,"").trim()||verdict.raw);
      P.verdict.innerHTML='<div class="rbad">✗ Amazon did NOT accept this listing — '+(verdict.n||"")+' issue(s).</div>'
        +'<div class="rmsg">Amazon is asking for fixes / extra fields:</div><div class="ramz">'+msg+'</div>'
        +'<div class="rhint">Click <b>Suggest missing fields</b> above to fill what Amazon flagged, then Preview again.</div>';
      return;
    }
    if(verdict.kind==="ok_preview"){
      P.verdict.innerHTML='<div class="rgood">\u2713 Amazon accepted this listing — no missing or invalid fields.</div>'
        +(warnings?('<div class="rwarn">Non-blocking warnings: '+esc(warnings)+'</div>'):'<div class="rmsg">No extra boxes need filling. It\u2019s ready to submit.</div>');
      return;
    }
    if(verdict.kind==="ok_submit"){
      P.verdict.innerHTML='<div class="rgood">\u2713 Published live to Amazon.</div>'
        +(warnings?('<div class="rwarn">Warnings: '+esc(warnings)+'</div>'):'<div class="rmsg">The listing is now live on your account.</div>');
      return;
    }
  }
  ES.addEventListener("end", finish);
  // After the run ends, quietly refresh THIS row's stored data (notes/status)
  // so when the panel is closed the drawer shows the fresh result, not the old
  // cached errors. Doesn't rebuild the grid (that would wipe the panel).
  ES.addEventListener("end", ()=>{
    setTimeout(async ()=>{
      try{
        const j = await (await fetch("/row?sku="+encodeURIComponent(sku))).json();
        if(j && j.ok && j.row){
          const idx = ROWS.findIndex(x=>String(x.sku)===String(sku));
          if(idx>=0){ ROWS[idx] = {...ROWS[idx], ...j.row}; }
          // If the drawer is still open for this SKU, re-render JUST the listing
          // data block so the fields Amazon just flagged (e.g. hazmat) appear as
          // editable boxes right away -- without rebuilding the run panel above.
          if(String(DRAWER_SKU)===String(sku)){
            const host=document.getElementById("fulldata_"+sid(sku));
            const fresh=ROWS.find(x=>String(x.sku)===String(sku));
            if(host && fresh){
              host.innerHTML=fullData(fresh);
              setTimeout(()=>{ if(typeof bulletMeter==='function') bulletMeter(); }, 40);
            }
          }
        }
      }catch(e){}
    }, 800);
  });
  // EventSource fires onerror on NORMAL stream close too. Only treat it as a real
  // error if we haven't already finished AND nothing has streamed yet.
  ES.onerror=()=>{
    if(done) return;
    // give the 'end' event a moment; if it never came and we got no data, it's a real failure
    setTimeout(()=>{
      if(done) return;
      if(ES){ try{ES.close();}catch(e){} ES=null; }
      if(lines.length>0){ finish(); }   // stream produced output then dropped -> show what we have
      else if(P){ done=true; P.verdict.innerHTML='<span class="rbad">✗ Couldn\u2019t reach the run stream. Is the app still running? Try again.</span>'; }
    }, 600);
  };
}
let MINIMAL_MODE_ON = false;
function toggleMinimal(cb){ MINIMAL_MODE_ON = !!cb.checked;
  toast(MINIMAL_MODE_ON ? "Minimal mode ON — only required fields will be sent" : "Minimal mode off"); }
// Exact-payload viewer: off by default (it's debug). Persisted in localStorage.
let SHOW_PAYLOAD_VIEWER = false;
try{ SHOW_PAYLOAD_VIEWER = (localStorage.getItem("show_payload_viewer")==="1"); }catch(e){}
window.SHOW_PAYLOAD_VIEWER = SHOW_PAYLOAD_VIEWER;
function togglePayloadViewer(cb){
  window.SHOW_PAYLOAD_VIEWER = !!cb.checked;
  try{ localStorage.setItem("show_payload_viewer", cb.checked?"1":"0"); }catch(e){}
  toast(cb.checked ? "Exact-payload viewer ON" : "Exact-payload viewer hidden");
  if(typeof render==="function"){ try{ render(); }catch(e){} }
}
function _minParam(){ return MINIMAL_MODE_ON ? "&minimal=1" : ""; }
function previewOne(sku){
  if(!sku) return;
  _streamRunPanel("/run/api?skus="+encodeURIComponent(sku)+_minParam(), sku, "preview");
}
async function submitOne(sku){
  if(!sku) return;
  // same safety as the global submit: precheck local images, then confirm the account
  try{
    const pc=await (await fetch("/submit/precheck")).json();
    if(pc&&pc.ok&&pc.count>0){
      const hit=(pc.local_image_rows||[]).some(x=>String(x.sku)===String(sku));
      if(hit){
        if(!confirm("⚠ This listing's main image is a LOCAL file Amazon can't fetch (it lives on your PC). "
          +"It will FAIL with 'Unable to Retrieve Media Content'.\n\nUse a publicly-hosted image URL first, "
          +"or submit anyway to see the error?")) return;
      }
    }
  }catch(e){}
  let t=null; try{ t=await (await fetch('/submit/target')).json(); }catch(e){}
  let who = (t&&t.ok)?(t.account_label+" · "+t.marketplace):"your live account";
  if(t&&t.ok&&t.block==='none'){ alert("No SP-API credentials for this marketplace. Add them first."); return; }
  // Amazon-side duplicate check: warn if this SKU already exists live on Amazon
  try{
    const dc=await (await fetch("/dup_check",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({skus:[sku]})})).json();
    if(dc&&dc.ok&&dc.exists&&dc.exists.length){
      const ex=dc.exists[0];
      if(!confirm("⚠ This SKU already exists on Amazon ("+who+")"
        +(ex.title?("\n  Live listing: "+ex.title):"")
        +"\n\nSubmitting will REPLACE the existing live listing. Continue?")) return;
    }
  }catch(e){}
  if(!confirm("PUBLISH THIS LISTING LIVE\n\n  SKU: "+sku+"\n  Account: "+who
      +(MINIMAL_MODE_ON?"\n  Mode: MINIMAL (required fields only)":"")
      +"\n\nThis creates/replaces ONLY this listing on the account above. Continue?")) return;
  toast("Submitting "+sku+"…");
  _streamRunPanel("/run/api_submit?skus="+encodeURIComponent(sku)+_minParam(), sku, "submit");
}

async function loadViews(){
  try{
    const j=await (await fetch('/view/list')).json();
    if(!j.ok) return;
    const sel=document.getElementById('viewsel'); if(!sel) return;
    sel.innerHTML=j.views.map(v=>`<option value="${v.key}" data-sheet="${v.sheet||''}" data-tab="${v.tab||''}">${v.label}</option>`).join('');
    sel.value=j.active||'';
  }catch(e){}
}
async function switchView(key){
  const sel=document.getElementById('viewsel');
  const opt=sel&&sel.selectedOptions&&sel.selectedOptions[0];
  const sheet=opt?opt.getAttribute('data-sheet'):'';
  const tab=opt?opt.getAttribute('data-tab'):'';
  try{
    await fetch('/view/set',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({key:key,sheet:sheet,tab:tab})});
    const bp=document.getElementById('brandpanel'); if(bp) bp.style.display='none';
    document.getElementById('grid').style.display='';
    const sm=document.getElementById('summary'); if(sm) sm.style.display='';
    toast(key?('Showing: '+key):'Showing: all (default)');
    loadRows();
  }catch(e){ toast('Could not switch view'); }
}
loadViews();
async function loadRows(){
  try{
    const j=await _fetchJSON("/rows", null, 20000);
    if(!j || j._failed){ toast("Could not load listings: "+((j&&j.error)||"timeout")); return; }
    if(!j.ok){ toast("Sheet error: "+(j.error||"unknown")); return; }
    ROWS=j.rows||[]; SHIP=j.shipping_group||""; PTYPES=j.product_types||[];
    render();
    const pts=[...new Set(ROWS.map(r=>r.product_type).filter(Boolean))];
    try{ await loadSchemas(pts); }catch(e){}
    render();
  }catch(e){ toast("Could not load: "+e); }
}
loadRows();

/* ---------- floating Claude assistant ---------- */
let CHAT = [];
let CHATIMGS = [];
function toggleChat(){
  const w=document.getElementById("chatwrap");
  w.classList.toggle("open");
  if(w.classList.contains("open")){ fillChatCtx(); setTimeout(()=>document.getElementById("chatinput").focus(),50); }
}
function fillChatCtx(){
  const sel=document.getElementById("chatctx"); const cur=sel.value;
  const opts=['<option value="">\u2014 general \u2014</option>'].concat(
    (ROWS||[]).filter(r=>r.sku||r.title||r.product_type).map(r=>{
      const label=(r.product_type||"?")+" \u00b7 "+String(r.title||r.sku||"row").slice(0,42);
      return '<option value="'+esc(String(r.sku||r.row||""))+'">'+esc(label)+'</option>';
    }));
  sel.innerHTML=opts.join(""); sel.value=cur;
}
function chatKey(e){ if(e.key==="Enter"&&!e.shiftKey){ e.preventDefault(); sendChat(); } }
function onChatFile(e){
  const f=e.target.files&&e.target.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=()=>{ CHATIMGS.push({media_type:f.type||"image/jpeg",data:String(rd.result).split(",")[1],name:f.name||"image"}); renderChips(); };
  rd.readAsDataURL(f); e.target.value="";
}
function onChatPaste(e){
  const items=(e.clipboardData&&e.clipboardData.items)||[];
  for(const it of items){
    if(it.type&&it.type.indexOf("image/")===0){
      const f=it.getAsFile();
      if(f){ const rd=new FileReader(); rd.onload=()=>{ CHATIMGS.push({media_type:f.type,data:String(rd.result).split(",")[1],name:"pasted image"}); renderChips(); }; rd.readAsDataURL(f); }
    }
  }
}
function renderChips(){
  document.getElementById("chatchips").innerHTML =
    CHATIMGS.map((im,i)=>'<span class="chip">\ud83d\uddbc '+esc(im.name)+' <button onclick="CHATIMGS.splice('+i+',1);renderChips()">\u00d7</button></span>').join("");
}
function chatBubble(role,text,imgs){
  const em=document.getElementById("chatempty"); if(em) em.remove();
  const body=document.getElementById("chatbody");
  const div=document.createElement("div"); div.className="msg "+(role==="user"?"u":"a"); div.textContent=text;
  if(imgs&&imgs.length){ imgs.forEach(im=>{ const x=document.createElement("img"); x.src="data:"+im.media_type+";base64,"+im.data; div.appendChild(x); }); }
  body.appendChild(div); body.scrollTop=body.scrollHeight; return div;
}
async function sendChat(){
  const ta=document.getElementById("chatinput"); const text=ta.value.trim();
  if(!text && !CHATIMGS.length) return;
  const btn=document.getElementById("chatsend"); btn.disabled=true;
  const imgs=CHATIMGS.slice(); CHATIMGS=[]; renderChips();
  CHAT.push({role:"user", text: text || "(see attached image)"});
  chatBubble("user", text || "(image)", imgs); ta.value="";
  let ctx=null; const sv=document.getElementById("chatctx").value;
  if(sv){ const r=(ROWS||[]).find(x=>String(x.sku)===sv||String(x.row)===sv);
    if(r) ctx={product_type:r.product_type,title:r.title,bullets:r.bullets,attributes:r.attributes,competitor_asin:r.asin,source_url:r.source,price:r.price,status:r.status,amazon_flags:r.notes||"",flagged_fields:parseFlagged(r.notes)}; }
  const wait=chatBubble("assistant","\u2026",null);
  try{
    const res=await fetch("/ask",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({messages:CHAT,context:ctx,images:imgs})});
    const j=await res.json(); wait.remove();
    if(j.ok){ CHAT.push({role:"assistant", text:j.reply}); chatBubble("assistant", j.reply); }
    else{ chatBubble("assistant", "\u26a0 "+(j.error||"failed")); }
  }catch(e){ wait.remove(); chatBubble("assistant","\u26a0 request failed"); }
  btn.disabled=false; ta.focus();
}

async function saveDefault(sku, pt, btn){
  btn.disabled=true; const orig=btn.textContent; btn.textContent="Saving…";
  try{
    const res=await fetch("/save_default",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sku:sku})});
    const j=await res.json();
    if(j.ok){ btn.textContent="★ Saved "+j.count+" default(s) for "+(j.pt||pt); toast("Defaults saved for "+(j.pt||pt)+" — future "+(j.pt||pt)+" listings will prefill these"); setTimeout(()=>{btn.textContent=orig;btn.disabled=false;},2800); }
    else{ btn.textContent=orig; btn.disabled=false; toast("Save failed: "+(j.error||"")); }
  }catch(e){ btn.textContent=orig; btn.disabled=false; toast("Save failed"); }
}

// ---- shell navigation ----
// ===================== SHELL NAVIGATION (new layout) =====================
// Drives home <-> workspace screens and the in-workspace section switching.
// All existing functions (card, render, loadRows, runMode, switchView, the
// brand panel, AI image gen, chat) are preserved and called from here.

let VIEWS = [];        // [{key,label,brand,marketplace,sheet,tab}]
let ACTIVE_WS = null;  // currently-open workspace member (a view)
let CUR_GROUP = null;  // currently-open workspace group (brand across marketplaces)
let CUR_SEC = "listings";

function _wsColor(v){
  // deterministic accent per workspace
  if(!v || !v.brand) return {bg:"rgba(76,141,255,.16)", fg:"#9cc1ff"};
  const palette=[["#E1F5EE","#0F6E56"],["#EEEDFE","#3C3489"],["#FAECE7","#993C1D"],
                 ["#E6F1FB","#185FA5"],["#FBEAF0","#993556"],["#FAEEDA","#854F0B"]];
  let h=0; for(const c of v.key) h=(h*31+c.charCodeAt(0))>>>0;
  const p=palette[h%palette.length];
  return {bg:p[0], fg:p[1]};
}
function _initials(name){
  const w=(name||"").trim().split(/\s+/);
  return ((w[0]||"")[0]||"?").toUpperCase()+((w[1]||"")[0]||"").toUpperCase();
}

function _baseName(v){
  if(!v.brand) return "__dropshipping__";
  return String(v.brand).replace(/\s+(USA?|UK|EU|CA|AU|DE|FR|IT|ES)\b\s*$/i,"").trim() || v.brand;
}
function _mktOf(v){
  const m=(v.marketplace||"").toUpperCase();
  if(m) return m;
  const t=(v.brand||"").toUpperCase();
  if(/\bUSA?\b/.test(t)) return "US";
  if(/\bUK\b/.test(t)) return "UK";
  return "";
}
function workspaceGroups(){
  const groups={};
  VIEWS.forEach(v=>{
    const base=_baseName(v);
    if(!groups[base]) groups[base]={base, members:[], isDrop:!v.brand};
    groups[base].members.push(v);
  });
  return Object.values(groups).map(g=>{ g.label=g.isDrop?"Dropshipping":g.base; return g; });
}

let ACCOUNTS = [];
async function _fetchJSON(url, opts, ms){
  // fetch with a hard timeout so a slow/stalled route can't freeze the page
  ms = ms || 12000;
  const ctrl = new AbortController();
  const t = setTimeout(()=>ctrl.abort(), ms);
  try{
    const r = await fetch(url, Object.assign({signal:ctrl.signal}, opts||{}));
    clearTimeout(t);
    return await r.json();
  }catch(e){
    clearTimeout(t);
    return {ok:false, error:(e&&e.name==='AbortError')?('timed out after '+(ms/1000)+'s'):String(e), _failed:true};
  }
}
async function loadHome(){
  const grid=document.getElementById("wsgrid");
  grid.innerHTML='<div class="empty" style="grid-column:1/-1">Loading workspaces…</div>';
  let acctData=await _fetchJSON("/accounts/list");
  if(acctData && acctData.config_error){
    grid.innerHTML='<div class="empty" style="grid-column:1/-1;text-align:left">'
      +'<div style="color:#ef9a9a;font-weight:600;margin-bottom:8px">⚠ Your config.json has an error</div>'
      +'<div class="cc" style="white-space:pre-wrap">'+esc(acctData.error||"")+'</div>'
      +'<div class="cc" style="margin-top:10px">Fix the file, save it, then click Home to retry.</div></div>';
    return;
  }
  if(acctData && acctData._failed){
    grid.innerHTML='<div class="empty" style="grid-column:1/-1;text-align:left">'
      +'<div style="color:#ef9a9a;font-weight:600;margin-bottom:8px">⚠ Could not load accounts</div>'
      +'<div class="cc">'+esc(acctData.error||"")+'</div>'
      +'<div class="cc" style="margin-top:8px">Try clicking Home again. If this persists, check the terminal where the app runs for an error.</div></div>';
    return;
  }
  ACCOUNTS=(acctData&&acctData.accounts)||[];
  const vd=await _fetchJSON("/view/list", null, 8000);   // don't let this stall the page
  VIEWS=(vd&&vd.views)||[];
  let cards="";
  // inline SVGs so the home cards never depend on the icon-font CDN
  const SVG_CART='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="19" r="2"/><circle cx="17" cy="19" r="2"/><path d="M17 17H6V3H4"/><path d="M6 5l14 1-1 7H6"/></svg>';
  const SVG_PLUG='<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 12h10v3a5 5 0 0 1-10 0z"/><path d="M9 12V7M15 12V7M12 20v2"/></svg>';
  const SVG_PLUGX='<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 12h7v3a5 5 0 0 1-7 4.5"/><path d="M9 12V7M14 12V7"/><path d="M18 6l4 4M22 6l-4 4"/></svg>';
  const SVG_PLUS='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>';
  // Dropshipping workspace (not an Amazon account -- the eBay->Amazon arbitrage side)
  cards += `<div class="wscard" onclick='enterDropshipping()'>
      <button class="peek" title="Reveal" onclick="event.stopPropagation();peekTile(this)"><i class="ti ti-eye"></i></button>
      <div style="display:flex;align-items:center;gap:11px">
        <div class="ic" style="background:rgba(76,141,255,.16);color:#9cc1ff">${SVG_CART}</div>
        <div style="flex:1"><div class="nm pii">Dropshipping</div><div class="sub pii">eBay → Amazon arbitrage</div></div>
        <button class="wsedit" title="Assign input &amp; output sheets" onclick='event.stopPropagation();openDropshippingSheets()'><i class="ti ti-settings"></i></button>
      </div>
      <div class="stats"><span class="cc">cross-account</span></div>
    </div>`;
  // each Amazon ACCOUNT is a workspace
  cards += ACCOUNTS.map(a=>{
    const col=_wsColorKey(a.id||a.label);
    const connected=a.has_creds;
    const mkts=(a.marketplaces&&a.marketplaces.length)?a.marketplaces.join(" · ")
      :(connected?'<span class="cc">marketplaces not detected</span>':'<span class="cc">draft-only · not connected</span>');
    const brandcount=(a.brands&&a.brands.length)?(a.brands.length+" trademark"+(a.brands.length>1?"s":"")):"";
    const stateBadge = connected
      ? '<span class="connpill on" title="SP-API credentials present">'+SVG_PLUG+' connected</span>'
      : '<span class="connpill off" title="No credentials yet — drafting works, live actions disabled">'+SVG_PLUGX+' draft-only</span>';
    return `<div class="wscard" onclick='enterAccount(${JSON.stringify(a.id)})'>
      <button class="peek" title="Reveal" onclick="event.stopPropagation();peekTile(this)"><i class="ti ti-eye"></i></button>
      <div style="display:flex;align-items:center;gap:11px">
        <div class="ic" style="background:${col.bg};color:${col.fg}">${_initials(a.label)}</div>
        <div style="flex:1"><div class="nm pii">${esc(a.label)}</div><div class="sub pii">Amazon account${a.seller_id?(" · "+esc(a.seller_id)):""}</div></div>
        ${stateBadge}
        <button class="wsedit" title="Edit account &amp; sheet links" onclick='event.stopPropagation();openAccountEditor(${JSON.stringify(a.id)})'><i class="ti ti-settings"></i></button>
      </div>
      <div class="stats pii"><span>${mkts}</span>${brandcount?`<span>${esc(brandcount)}</span>`:""}</div>
    </div>`;
  }).join("");
  cards += `<div class="wscard add" onclick="openAccountEditor('')">${SVG_PLUS} Add account</div>`;
  grid.innerHTML = cards;
}
async function openDropshippingSheets(){
  // Reuse the account modal shell to edit the DEFAULT (Dropshipping) sheets.
  const m=document.getElementById("acctmodal"); if(!m) return; m.classList.add("open");
  const body=document.getElementById("acctmodalbody");
  body.innerHTML='<div class="cc" style="padding:12px"><span class="genspin"></span> Loading…</div>';
  let s; try{ s=await (await fetch("/settings/dropshipping_sheets")).json(); }catch(e){ s={ok:false}; }
  const S=(s&&s.ok)?s:{output_sheet_url:"",input_sheet_url:"",output_tab:""};
  body.innerHTML=`
    <div style="font-weight:600;font-size:14px;margin-bottom:2px"><i class="ti ti-table"></i> Dropshipping default sheets</div>
    <div class="cc" style="font-size:11.5px;margin-bottom:10px">The built-in Dropshipping workspace (eBay → Amazon) uses these sheets. Paste the <b>full Google Sheets link</b> with the tab open — the app reads the spreadsheet ID and the tab (gid) from the URL. Leave blank to fall back to the app's config defaults.</div>
    <table class="kv">
      <tr><td class="k">Output sheet URL <span class="cc">(generated listings)</span></td><td class="v"><input class="ed" id="ds_output_url" value="${esc(S.output_sheet_url||'')}" oninput="_showParsed('ds_output_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ds_output_parsed" class="cc" style="font-size:11px;margin-top:2px"></div></td></tr>
      <tr><td class="k">Input sheet URL <span class="cc">(source rows)</span></td><td class="v"><input class="ed" id="ds_input_url" value="${esc(S.input_sheet_url||'')}" oninput="_showParsed('ds_input_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ds_input_parsed" class="cc" style="font-size:11px;margin-top:2px"></div></td></tr>
    </table>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <button class="primary" onclick="saveDropshippingSheets()">Save sheets</button>
      <button onclick="closeAccountEditor()">Cancel</button>
      <span id="ds_status" class="cc"></span>
    </div>`;
}
async function saveDropshippingSheets(){
  const out=((document.getElementById("ds_output_url")||{}).value||"").trim();
  const inp=((document.getElementById("ds_input_url")||{}).value||"").trim();
  const st=document.getElementById("ds_status");
  if(st) st.textContent="Saving…";
  try{
    const j=await (await fetch("/settings/dropshipping_sheets",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({output_sheet_url:out, input_sheet_url:inp})})).json();
    if(j.ok){ toast("Dropshipping sheets saved"+(j.output_tab?(" · tab: "+j.output_tab):"")); closeAccountEditor(); loadHome(); }
    else { if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(String(e))+'</span>'; }
}
function _wsColorKey(key){
  const palette=[["#E1F5EE","#0F6E56"],["#EEEDFE","#3C3489"],["#FAECE7","#993C1D"],
                 ["#E6F1FB","#185FA5"],["#FBEAF0","#993556"],["#FAEEDA","#854F0B"]];
  let h=0; for(const c of String(key)) h=(h*31+c.charCodeAt(0))>>>0;
  const p=palette[h%palette.length]; return {bg:p[0], fg:p[1]};
}

function enterGroup(base){
  const groups=workspaceGroups();
  const g=groups.find(x=>x.base===base) || groups[0];
  CUR_GROUP=g;
  enterWorkspace(g.members[0].key);
  buildMktSwitch(g);
}

let CUR_ACCOUNT = null;
async function enterAccount(accountId){
  const a=ACCOUNTS.find(x=>x.id===accountId) || ACCOUNTS[0];
  if(!a){ toast("Account not found"); return; }
  CUR_ACCOUNT=a;
  // Refresh inventory alert badge when workspace changes (fire-and-forget)
  if(typeof invBadgeRefresh === 'function') invBadgeRefresh();
  const hasCreds = !!(a.has_creds || (a.refresh_token && !String(a.refresh_token).startsWith("PUT_")));
  LIVE_ITEMS=[]; LIST_SOURCE = hasCreds ? 'all' : 'drafts';   // All = drafts + live for connected accounts
  // default marketplace: account's configured default, else first detected
  const dflt = a.default_marketplace && (a.marketplaces||[]).indexOf(a.default_marketplace)>=0 ? a.default_marketplace : null;
  WS_MARKET = dflt || ((a.marketplaces && a.marketplaces.length) ? a.marketplaces[0] : "");
  CUR_SYMBOL = (WS_MARKET==="US"||WS_MARKET==="CA"||WS_MARKET==="MX") ? "$" : ((WS_MARKET==="EU"||["DE","FR","IT","ES","NL"].includes(WS_MARKET)) ? "\u20ac" : "\u00a3");
  var sw=document.getElementById('srcswitch'); if(sw){ sw.style.display='flex'; sw.querySelectorAll('.mktbtn').forEach(b=>b.classList.toggle('on',b.dataset.src===LIST_SOURCE)); }
  // tell the backend this account is active (all submit/preview use ITS creds)
  try{ await fetch("/accounts/select",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:a.id})}); }catch(e){}
  // paint shell
  document.getElementById("home").classList.remove("show");
  document.getElementById("workspace").classList.add("show");
  const col=_wsColorKey(a.id||a.label);
  const icEl=document.getElementById("ws_ic");
  icEl.style.background=col.bg; icEl.style.color=col.fg; icEl.innerHTML=_initials(a.label);
  document.getElementById("ws_nm").textContent=a.label;
  document.getElementById("ws_sub").textContent="Amazon account"+(a.seller_id?(" · "+a.seller_id):"");
  document.getElementById("ws_title").textContent="Listings";
  document.getElementById("crumbs").innerHTML=`<span class="sep">/</span><span class="here">${esc(a.label)}</span>`;
  document.getElementById("nav_setup").style.display="flex"; // brand/account setup
  // Per-workspace features: show the Supplier Import (harvest) nav only if the
  // account has the "harvest" feature enabled in its settings.
  const _feats = a.features || [];
  const _hv = document.getElementById("nav_harvest");
  if(_hv) _hv.style.display = _feats.includes("harvest") ? "flex" : "none";
  window.WS_FEATURES = _feats;
  window.WS_BRAND="";
  ACTIVE_WS={key:a.id, label:a.label, account:true};
  // marketplace switcher from the account's (detected) marketplaces
  buildAccountMktSwitch(a);
  navTo("listings");
  if(LIST_SOURCE==='all' || LIST_SOURCE==='live'){ loadRows(); loadLiveCatalog(false); }
  else loadRows();
}
function enterDropshipping(){
  CUR_ACCOUNT=null;
  try{ fetch("/accounts/select",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:""})}); }catch(e){}
  document.getElementById("home").classList.remove("show");
  document.getElementById("workspace").classList.add("show");
  const icEl=document.getElementById("ws_ic");
  icEl.style.background="rgba(76,141,255,.16)"; icEl.style.color="#9cc1ff";
  icEl.innerHTML='<i class="ti ti-shopping-cart"></i>';
  document.getElementById("ws_nm").textContent="Dropshipping";
  document.getElementById("ws_sub").textContent="eBay → Amazon";
  document.getElementById("ws_title").textContent="Listings";
  document.getElementById("crumbs").innerHTML='<span class="sep">/</span><span class="here">Dropshipping</span>';
  document.getElementById("nav_setup").style.display="none";
  var _hv=document.getElementById("nav_harvest"); if(_hv) _hv.style.display="none";
  window.WS_FEATURES=[];
  window.WS_BRAND="";
  ACTIVE_WS={key:"", label:"Dropshipping"};
  document.getElementById("mktswitch").innerHTML="";
  var sw=document.getElementById('srcswitch'); if(sw) sw.style.display='none';
  LIST_SOURCE='drafts'; LIVE_ITEMS=[];
  navTo("listings");
  loadRows();
}
function buildAccountMktSwitch(a){
  const host=document.getElementById("mktswitch"); if(!host) return;
  if(!a.has_creds){
    host.innerHTML='<span class="mktlabel" title="Add SP-API credentials to enable live features">draft-only · <a href="#" onclick="openAccountEditor(\''+esc(a.id)+'\');return false" style="color:#9cc1ff">connect account</a></span>';
    return;
  }
  const mkts=a.marketplaces&&a.marketplaces.length?a.marketplaces:[];
  if(!mkts.length){
    host.innerHTML='<button class="mktbtn" onclick="detectMarketplaces(\''+esc(a.id)+'\')"><i class="ti ti-radar"></i> Detect marketplaces</button>';
    return;
  }
  // keep the current selection if it's valid for this account; else default to first
  if(!WS_MARKET || (WS_MARKET!=="__all__" && mkts.indexOf(WS_MARKET)<0)){ WS_MARKET=mkts[0]; }
  if(WS_MARKET!=="__all__"){
    CUR_SYMBOL=(WS_MARKET==="US"||WS_MARKET==="CA"||WS_MARKET==="MX")?"$":((WS_MARKET==="EU"||["DE","FR","IT","ES","NL"].includes(WS_MARKET))?"\u20ac":"\u00a3");
  }
  host.innerHTML =
    `<button class="mktbtn ${WS_MARKET==='__all__'?'on':''}" title="Show listings across every marketplace (fetches each — can be slow)" onclick="switchAccountMarket('__all__')">All</button>`
    + mkts.map(m=>{
        const isDflt = a.default_marketplace===m;
        return `<button class="mktbtn ${m===WS_MARKET?'on':''}" onclick="switchAccountMarket('${esc(m)}')">${esc(m)}${isDflt?' <span title="default" style="color:#e3b768">\u2605</span>':''}</button>`;
      }).join("")
    + `<button class="mktbtn" title="Set current marketplace (${esc(WS_MARKET||'')}) as this account\u2019s default" onclick="setDefaultMarketplace()">\u2606 default</button>`
    + '<button class="mktbtn" title="Re-detect" onclick="detectMarketplaces(\''+esc(a.id)+'\')"><i class="ti ti-refresh"></i></button>';
}
async function detectMarketplaces(accountId){
  var host=document.getElementById("mktswitch");
  if(host) host.innerHTML='<span class="mktlabel"><span class="genspin"></span> detecting…</span>';
  try{
    var j=await (await fetch("/accounts/detect_marketplaces",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:accountId})})).json();
    if(!j.ok){ toast("Detect failed: "+(j.error||"")); 
      // refresh the account object so the button comes back
      try{ var al=await (await fetch("/accounts/list")).json(); ACCOUNTS=al.accounts||[]; }catch(e){}
      var a=ACCOUNTS.find(x=>x.id===accountId); if(a) buildAccountMktSwitch(a);
      return;
    }
    toast("Detected: "+(j.marketplaces||[]).join(", "));
    // update local account + rebuild switcher
    try{ var al=await (await fetch("/accounts/list")).json(); ACCOUNTS=al.accounts||[]; }catch(e){}
    var a2=ACCOUNTS.find(x=>x.id===accountId);
    if(a2){ CUR_ACCOUNT=a2; buildAccountMktSwitch(a2); }
  }catch(e){ toast("Error: "+e); }
}
async function setDefaultMarketplace(){
  if(!CUR_ACCOUNT || !WS_MARKET || WS_MARKET==="__all__"){ toast("Pick a specific marketplace first."); return; }
  try{
    const j=await (await fetch("/accounts/set_default_marketplace",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT.id,marketplace:WS_MARKET})})).json();
    if(!j.ok){ toast("Could not set default: "+(j.error||"")); return; }
    CUR_ACCOUNT.default_marketplace=WS_MARKET;
    const acc=ACCOUNTS.find(x=>x.id===CUR_ACCOUNT.id); if(acc) acc.default_marketplace=WS_MARKET;
    buildAccountMktSwitch(CUR_ACCOUNT);
    toast(WS_MARKET+" is now the default marketplace for "+CUR_ACCOUNT.label);
  }catch(e){ toast("Error: "+e); }
}
async function switchAccountMarket(m){
  WS_MARKET=m;
  CUR_SYMBOL=(m==="US"||m==="CA"||m==="MX")?"$":(m==="UK"?"\u00a3":(m==="EU"||["DE","FR","IT","ES","NL"].includes(m))?"\u20ac":"\u00a3");
  try{ await fetch("/accounts/select",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:CUR_ACCOUNT?CUR_ACCOUNT.id:"",marketplace:m})}); }catch(e){}
  if(CUR_ACCOUNT) buildAccountMktSwitch(CUR_ACCOUNT);
  if(LIST_SOURCE==='live'||LIST_SOURCE==='all'){ loadLiveCatalog(false); } else { loadRows(); }
}

function openCurrentAccountSettings(){
  // Resolve the account currently in focus. CUR_ACCOUNT is set by enterAccount;
  // it's intentionally null in the built-in Dropshipping workspace.
  if(CUR_ACCOUNT && CUR_ACCOUNT.id){ openAccountEditor(CUR_ACCOUNT.id); return; }
  // Dropshipping (or no account selected): try the server's active account id.
  if(ACTIVE_WS && ACTIVE_WS.account && ACTIVE_WS.key){ openAccountEditor(ACTIVE_WS.key); return; }
  // Built-in Dropshipping workspace has no account object — explain + send to Home.
  if(ACTIVE_WS && !ACTIVE_WS.account){
    toast("Dropshipping uses the default sheet. To set per-account sheet links, open a real account from All workspaces.");
    return;
  }
  toast("Open an account from All workspaces first, then click Account & sheets.");
}
function openAccountEditor(id){
  const a = id ? (ACCOUNTS.find(x=>x.id===id)||{}) : {};
  const m=document.getElementById("acctmodal"); m.classList.add("open");
  document.getElementById("acctmodalbody").innerHTML=`
    <table class="kv">
      <tr><td class="k">Account name</td><td class="v"><input class="ed" id="ac_label" value="${esc(a.label||'')}" placeholder="e.g. Jack Reacherd (UK)"></td></tr>
      <tr><td class="k">Seller / merchant ID</td><td class="v"><input class="ed" id="ac_seller" value="${esc(a.seller_id||'')}" placeholder="A1B2C3..."></td></tr>
      <tr><td class="k">LWA client ID</td><td class="v"><input class="ed" id="ac_clientid" value="${esc(a.lwa_client_id||'')}" placeholder="amzn1.application-oa2-client..."></td></tr>
      <tr><td class="k">LWA client secret</td><td class="v"><input class="ed" id="ac_secret" type="password" placeholder="${a.has_secret?'•••••• (leave blank to keep)':'paste secret'}"></td></tr>
      <tr><td class="k">Refresh token</td><td class="v"><input class="ed" id="ac_refresh" type="password" placeholder="${a.has_creds?'•••••• (leave blank to keep)':'paste refresh token'}"></td></tr>
      <tr><td class="k">Primary marketplace</td><td class="v"><select class="ed" id="ac_marketplace"><option value="UK"${(a.default_marketplace||'UK')==='UK'?' selected':''}>UK — amazon.co.uk (GBP)</option><option value="US"${(a.default_marketplace||'')==='US'?' selected':''}>US — amazon.com (USD)</option></select><div class="cc" style="font-size:11px;margin-top:2px">Drives pricing, fees, SP-API and the flat-file route for this account's listings.</div></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-table"></i> Google Sheets for this account</div><div class="cc" style="font-size:11.5px">Paste the <b>full Google Sheets link</b> (with the tab open). The app reads the spreadsheet ID and the tab (gid) from the URL — so each account's US/UK listings go to the right place.</div></td></tr>
      <tr><td class="k">Input sheet URL <span class="cc">(source rows)</span></td><td class="v"><input class="ed" id="ac_input_url" value="${esc(a.input_sheet_url||'')}" oninput="_showParsed('ac_input_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ac_input_parsed" class="cc" style="font-size:11px;margin-top:2px"></div></td></tr>
      <tr><td class="k">Output sheet URL <span class="cc">(generated listings)</span></td><td class="v"><input class="ed" id="ac_output_url" value="${esc(a.output_sheet_url||'')}" oninput="_showParsed('ac_output_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ac_output_parsed" class="cc" style="font-size:11px;margin-top:2px"></div></td></tr>
      <tr><td class="k">Drive image folder URL <span class="cc">(image storage)</span></td><td class="v"><input class="ed" id="ac_drive_url" value="${esc(a.drive_folder_url||'')}" placeholder="https://drive.google.com/drive/folders/…"><div class="cc" id="ac_drive_share" style="font-size:11px;margin-top:3px">Generated images upload here into per-product <code>SKU_ProductName</code> subfolders. <b>Share this folder (Editor) with the service account</b> shown below, or uploads will be denied.</div></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-shield-check"></i> UK Responsible Person <span class="cc">(only needed for Amazon.co.uk listings)</span></div><div class="cc" style="font-size:11.5px">Selling on Amazon.co.uk from outside the UK legally requires a UK Responsible Person (name + real UK address + contact). Fill this once and every UK listing inherits it. Leave blank for US-only — US listings are unaffected.</div></td></tr>
      <tr><td class="k">RP legal name</td><td class="v"><input class="ed" id="ac_rp_name" value="${esc((a.uk_responsible_person||{}).name||'')}" placeholder="e.g. FLIPX LTD"></td></tr>
      <tr><td class="k">RP UK address</td><td class="v"><input class="ed" id="ac_rp_address" value="${esc((a.uk_responsible_person||{}).address||'')}" placeholder="Real UK address — no PO boxes"></td></tr>
      <tr><td class="k">RP email</td><td class="v"><input class="ed" id="ac_rp_email" value="${esc((a.uk_responsible_person||{}).email||'')}" placeholder="contact@…"></td></tr>
      <tr><td class="k">RP phone</td><td class="v"><input class="ed" id="ac_rp_phone" value="${esc((a.uk_responsible_person||{}).phone||'')}" placeholder="+44…"></td></tr>
      <tr><td class="k">Trademarks / brands <span class="cc">(comma-separated)</span></td><td class="v"><input class="ed" id="ac_brands" value="${esc((a.brands||[]).join(', '))}" placeholder="Headbanger Lures, Leech Eyewear"></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-shopping-cart"></i> eBay source credentials <span class="cc">(optional — per-account override)</span></div><div class="cc" style="font-size:11.5px">Used to scrape the source eBay listing for each row. Leave blank to use the app-wide eBay keys (set in <b>AI &amp; settings ▸ eBay</b>). <b>If you fill BOTH fields here, they override the global eBay credentials for THIS account.</b></div></td></tr>
      <tr><td class="k">eBay App ID <span class="cc">(client ID)</span></td><td class="v"><input class="ed" id="ac_ebay_app" value="${esc(a.ebay_app_id||'')}" placeholder="leave blank to use global"></td></tr>
      <tr><td class="k">eBay Cert ID <span class="cc">(secret)</span></td><td class="v"><input class="ed" id="ac_ebay_cert" type="password" placeholder="${a.has_ebay_cert?'•••••• (leave blank to keep)':'leave blank to use global'}"></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-plug"></i> Workspace features</div><div class="cc" style="font-size:11.5px">Turn on extra capabilities for this account. Enabling a feature reveals its section inside the workspace; uploads there build listings for THIS account (its sheet, its credentials).</div></td></tr>
      <tr><td class="k">Supplier harvest</td><td class="v">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
          <input type="checkbox" id="ac_feat_harvest" ${(a.features||[]).includes('harvest')?'checked':''} style="width:16px;height:16px">
          Enable supplier-site harvesting (scrape product pages + PDFs, e.g. Miles Lubricants)
        </label></td></tr>
      <tr><td class="k">Auto main image</td><td class="v">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
          <input type="checkbox" id="ac_feat_imgtpl" ${(a.features||[]).includes('image_template')?'checked':''} style="width:16px;height:16px">
          Generate a templated main image for each listing in this workspace
        </label></td></tr>
    </table>
    <input type="hidden" id="ac_id" value="${esc(a.id||'')}">
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
      <button class="primary" onclick="saveAccount()">Save account</button>
      ${id?`<button onclick="detectFromEditor('${esc(id)}')"><i class="ti ti-radar"></i> Detect marketplaces</button>`:''}
      ${id?`<button onclick="detectBrandsFromEditor('${esc(id)}')"><i class="ti ti-tags"></i> Detect brands</button>`:''}
      ${id?`<button class="del" onclick="deleteAccount('${esc(id)}')">Delete</button>`:''}
      <button onclick="closeAccountEditor()">Cancel</button>
    </div>
    ${typeof howWorks==="function"?(howWorks('acct_connect')+howWorks('acct_marketplaces')+howWorks('acct_brands')):""}
    <div id="ac_detectout" class="cc" style="margin-top:8px"></div>
    <p class="cc" style="margin-top:10px">Secrets are stored only in your local config.json. Leave secret/refresh blank when editing to keep the existing values. Marketplaces are auto-detected (next step) once credentials are valid.</p>`;
  // populate the service-account email for the Drive folder share hint
  (async function(){
    try{
      const ds=await (await fetch("/drive/status")).json();
      const el=document.getElementById("ac_drive_share");
      if(el && ds && ds.ok && ds.service_account_email){
        el.innerHTML='Generated images upload here into per-product <code>SKU_ProductName</code> subfolders. '
          +'<b>Share this folder (Editor) with:</b><br><code style="user-select:all;background:#11203a;padding:2px 6px;border-radius:4px;display:inline-block;margin-top:3px">'
          +esc(ds.service_account_email)+'</code><br>or uploads will be denied.';
      }
    }catch(e){}
  })();
}
function closeAccountEditor(){ document.getElementById("acctmodal").classList.remove("open"); }
// Parse a full Google Sheets URL into {id, gid}. Accepts a bare ID too.
function parseSheetUrl(u){
  u=(u||"").trim();
  if(!u) return {id:"", gid:""};
  let id="", gid="";
  let m=u.match(/\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/);
  if(m){ id=m[1]; }
  else if(/^[a-zA-Z0-9_-]{20,}$/.test(u)){ id=u; }   // looks like a bare ID
  let g=u.match(/[#&?]gid=([0-9]+)/);
  if(g){ gid=g[1]; }
  return {id:id, gid:gid};
}
function _showParsed(boxId, url){
  const p=parseSheetUrl(url); const el=document.getElementById(boxId);
  if(!el) return;
  if(!url.trim()){ el.innerHTML=""; return; }
  if(p.id){ el.innerHTML='<span style="color:#7fd99a">✓ sheet '+esc(p.id.slice(0,10))+'…'+(p.gid?(' · tab gid '+esc(p.gid)):' · first tab')+'</span>'; }
  else { el.innerHTML='<span style="color:#e0696b">✗ couldn\u2019t read a sheet ID from that link</span>'; }
}
async function saveAccount(){
  const inUrl=(document.getElementById("ac_input_url")||{}).value||"";
  const outUrl=(document.getElementById("ac_output_url")||{}).value||"";
  const inP=parseSheetUrl(inUrl), outP=parseSheetUrl(outUrl);
  const body={
    id:(document.getElementById("ac_id")||{}).value||"",
    label:(document.getElementById("ac_label")||{}).value||"",
    seller_id:(document.getElementById("ac_seller")||{}).value||"",
    lwa_client_id:(document.getElementById("ac_clientid")||{}).value||"",
    lwa_client_secret:(document.getElementById("ac_secret")||{}).value||"",
    refresh_token:(document.getElementById("ac_refresh")||{}).value||"",
    // store the raw URLs (so the field shows them again) AND the parsed pieces
    input_sheet_url:inUrl, output_sheet_url:outUrl,
    drive_folder_url:((document.getElementById("ac_drive_url")||{}).value||"").trim(),
    uk_responsible_person:{
      name:((document.getElementById("ac_rp_name")||{}).value||"").trim(),
      address:((document.getElementById("ac_rp_address")||{}).value||"").trim(),
      email:((document.getElementById("ac_rp_email")||{}).value||"").trim(),
      phone:((document.getElementById("ac_rp_phone")||{}).value||"").trim()
    },
    input_spreadsheet_id:inP.id, input_tab_gid:inP.gid,
    output_spreadsheet_id:outP.id, output_tab_gid:outP.gid,
    // per-account eBay override (blank = fall back to the global eBay creds)
    ebay_app_id:((document.getElementById("ac_ebay_app")||{}).value||"").trim(),
    ebay_cert_id:((document.getElementById("ac_ebay_cert")||{}).value||"").trim(),
    default_marketplace:(document.getElementById("ac_marketplace")||{}).value||"UK",
    brands:((document.getElementById("ac_brands")||{}).value||"").split(",").map(s=>s.trim()).filter(Boolean),
    features:[
      ...(((document.getElementById("ac_feat_harvest")||{}).checked)?["harvest"]:[]),
      ...(((document.getElementById("ac_feat_imgtpl")||{}).checked)?["image_template"]:[])
    ]
  };
  if(!body.label){ toast("Account name required"); return; }
  if(outUrl.trim() && !outP.id){ toast("Output sheet link looks wrong — couldn't read a sheet ID"); return; }
  try{
    const j=await (await fetch("/accounts/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})).json();
    if(j.ok){ toast("Account saved"); closeAccountEditor(); loadHome(); }
    else toast("Save failed: "+(j.error||""));
  }catch(e){ toast("Error: "+e); }
}
async function deleteAccount(id){
  if(!confirm("Delete this account from the app? (Your Amazon account is unaffected; this only removes it from the tool.)")) return;
  try{ await fetch("/accounts/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})});
    toast("Account removed"); closeAccountEditor(); loadHome(); }
  catch(e){ toast("Error: "+e); }
}
async function detectFromEditor(id){
  var out=document.getElementById("ac_detectout");
  if(out) out.innerHTML='<span class="genspin"></span> Calling Amazon (getMarketplaceParticipations)…';
  try{
    var j=await (await fetch("/accounts/detect_marketplaces",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})})).json();
    if(j.ok){ if(out) out.innerHTML='<span style="color:#7fd99a">\u2713 Detected: '+(j.marketplaces||[]).join(", ")+'</span>'; loadHome(); }
    else { if(out) out.innerHTML='<span style="color:#e0696b">\u2717 '+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(out) out.innerHTML='<span style="color:#e0696b">\u2717 '+esc(String(e))+'</span>'; }
}
async function detectBrandsFromEditor(id){
  var out=document.getElementById("ac_detectout");
  if(out) out.innerHTML='<span class="genspin"></span> Reading brands from your live listings…';
  try{
    var j=await (await fetch("/accounts/detect_brands",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})})).json();
    if(j.ok){
      // reflect into the brands field
      var bf=document.getElementById("ac_brands"); if(bf) bf.value=(j.brands||[]).join(", ");
      if(out) out.innerHTML='<span style="color:#7fd99a">\u2713 Brands ('+esc(j.source||"")+'): '+esc((j.brands||[]).join(", ")||"none found")+'</span>'
        +'<div class="cc" style="margin-top:4px">'+esc(j.note||"")+'</div>';
      loadHome();
    } else { if(out) out.innerHTML='<span style="color:#e0696b">\u2717 '+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(out) out.innerHTML='<span style="color:#e0696b">\u2717 '+esc(String(e))+'</span>'; }
}
function buildMktSwitch(g){
  const host=document.getElementById("mktswitch"); if(!host) return;
  if(!g || g.members.length<2 && !g.isDrop){
    // single-marketplace brand: show its marketplace as a static label (or nothing)
    const m=g&&g.members[0]?_mktOf(g.members[0]):"";
    host.innerHTML = m? `<span class="mktlabel">${esc(m)}</span>`:"";
    return;
  }
  host.innerHTML = g.members.map(v=>{
    const m=_mktOf(v)||v.label;
    const on = ACTIVE_WS && ACTIVE_WS.key===v.key;
    return `<button class="mktbtn ${on?'on':''}" onclick='switchMarket(${JSON.stringify(v.key)})'>${esc(m)}</button>`;
  }).join("");
}
async function switchMarket(key){
  await enterWorkspace(key);
  if(CUR_GROUP) buildMktSwitch(CUR_GROUP);
}

let PRIVACY_ON = false;
function togglePrivacy(){
  PRIVACY_ON = !PRIVACY_ON;
  document.body.classList.toggle("privacy-on", PRIVACY_ON);
  const btn=document.getElementById("privbtn");
  if(btn){
    btn.classList.toggle("privon", PRIVACY_ON);
    btn.innerHTML = PRIVACY_ON
      ? '<i class="ti ti-eye-off"></i> Privacy ON'
      : '<i class="ti ti-eye-off"></i> Privacy';
  }
  // When turning privacy back OFF, clear any per-card reveals so next time
  // privacy is enabled everything starts blurred again.
  if(!PRIVACY_ON){
    document.querySelectorAll(".unblurred").forEach(el=>el.classList.remove("unblurred"));
  }
  try{ localStorage.setItem("priv_on", PRIVACY_ON?"1":"0"); }catch(e){}
}
// Reveal (or re-hide) a single tile/card. The eye button lives inside the
// tile image or card; walk up to the nearest .tile or .wscard and toggle.
function peekTile(btn){
  const host = btn.closest(".tile, .wscard");
  if(!host) return;
  const now = host.classList.toggle("unblurred");
  const ic = btn.querySelector("i");
  if(ic) ic.className = now ? "ti ti-eye-off" : "ti ti-eye";
  btn.title = now ? "Hide again" : "Reveal this listing";
}
function goHome(){
  ACTIVE_WS=null;
  document.getElementById("workspace").classList.remove("show");
  document.getElementById("home").classList.add("show");
  document.getElementById("crumbs").innerHTML="";
  loadHome();
}

async function enterWorkspace(key){
  const v=VIEWS.find(x=>String(x.key)===String(key)) || {key:key,label:key};
  ACTIVE_WS=v;
  // switch the backend view so all existing routes read this workspace's sheet
  try{ await fetch("/view/set",{method:"POST",headers:{"Content-Type":"application/json"},
       body:JSON.stringify({key:v.key, sheet:v.sheet||"", tab:v.tab||""})}); }catch(e){}
  // paint shell
  document.getElementById("home").classList.remove("show");
  document.getElementById("workspace").classList.add("show");
  const col=_wsColor(v), isDrop=!v.brand;
  const icEl=document.getElementById("ws_ic");
  icEl.style.background=col.bg; icEl.style.color=col.fg;
  icEl.innerHTML = isDrop ? '<i class="ti ti-shopping-cart"></i>' : _initials(v.brand||v.label);
  document.getElementById("ws_nm").textContent=v.label||v.brand||"Dropshipping";
  document.getElementById("ws_sub").textContent=v.marketplace||"";
  document.getElementById("ws_title").textContent=(v.label||"Listings");
  document.getElementById("crumbs").innerHTML=
    `<span class="sep">/</span><span class="here">${esc(v.label||v.brand||"Dropshipping")}</span>`;
  // brand-only sections
  document.getElementById("nav_setup").style.display = isDrop ? "none" : "flex";
  window.WS_BRAND = isDrop ? "" : (v.brand||"");
  // currency + marketplace for this workspace
  WS_MARKET = _mktOf(v) || (isDrop ? "" : "");
  CUR_SYMBOL = (WS_MARKET==="US") ? "$" : "\u00a3";
  SELECTED.clear(); updateSelBar();
  document.getElementById("gen_scope").textContent =
    (v.label? "\u201c"+v.label+"\u201d" : "this workspace\u2019s");
  navTo("listings");
  loadRows();
  loadViews();   // keep legacy view <select> in sync if present
}

function navTo(sec){
  CUR_SEC=sec;
  document.querySelectorAll(".navitem").forEach(n=>n.classList.toggle("active", n.dataset.sec===sec));
  // listings uses #sec_listings (always block); others are .wspanel
  document.getElementById("sec_listings").style.display = (sec==="listings")?"block":"none";
  ["imagerefs","setup","generate","miles","ppc","inventory"].forEach(s=>{
    const el=document.getElementById("sec_"+s);
    if(el) el.classList.toggle("show", s===sec);
  });
  if(sec==="setup")     loadBrandPanel();
  if(sec==="imagerefs") loadImageRefs();
  if(sec==="generate"){ loadTargetAccount(); loadInputSheet(); }
  if(sec==="miles"){    milesLoadResults(); milesLoadPref(); }
  if(sec==="ppc")       ppcOnOpen();
}
async function loadTargetAccount(){
  var el=document.getElementById("targetacct"); if(!el) return;
  el.className="acctbanner"; el.textContent="Resolving destination account…";
  try{
    var t=await (await fetch('/submit/target')).json();
    if(t&&t.ok){
      if(t.block==='none'){ el.className="acctbanner bad"; el.innerHTML='\u26a0 '+esc(t.marketplace)+' marketplace selected, but NO credentials configured \u2014 submit will do nothing.'; }
      else { el.className="acctbanner ok"; el.innerHTML='<i class="ti ti-shield-check"></i> Submits here publish to: <b>'+esc(t.account_label)+'</b>'+(t.seller_id?' <span class="cc">('+esc(t.seller_id)+')</span>':'')+' \u2014 marketplace <b>'+esc(t.marketplace)+'</b>'; }
    } else { el.className="acctbanner bad"; el.textContent="Could not resolve destination account."; }
  }catch(e){ el.className="acctbanner bad"; el.textContent="Could not resolve destination account."; }
}

async function loadInputSheet(){
  var body=document.getElementById("inputsheet_body"); if(!body) return;
  var meta=document.getElementById("inputsheet_meta");
  body.innerHTML='<div class="cc" style="padding:16px;opacity:.7"><span class="genspin"></span> Loading input sheet\u2026</div>';
  if(meta) meta.textContent="";
  try{
    var j=await (await fetch('/input_sheet')).json();
    if(!j.ok){ body.innerHTML='<div class="cc" style="padding:16px;color:#e3b768">'+esc(j.error||'could not load')+'</div>'; return; }
    var openA=document.getElementById("inputsheet_open");
    if(openA && j.view_url){ openA.href=j.view_url; openA.style.display="inline-flex"; }
    if(meta) meta.textContent='\u201c'+(j.title||'')+'\u201d \u00b7 '+j.row_count+' rows \u00d7 '+j.col_count+' cols';
    var H=j.headers||[], R=j.rows||[];
    if(!H.length && !R.length){ body.innerHTML='<div class="cc" style="padding:16px;opacity:.6">This sheet is empty.</div>'; return; }
    var html='<table class="ishtable"><thead><tr><th class="isgut">#</th>';
    H.forEach(function(h){ html+='<th>'+esc(h||'')+'</th>'; });
    html+='</tr></thead><tbody id="ishbody">';
    R.forEach(function(row,ri){
      html+='<tr><td class="isgut">'+(ri+2)+'</td>';
      for(var c=0;c<H.length;c++){ html+='<td>'+esc(row[c]!=null?row[c]:'')+'</td>'; }
      html+='</tr>';
    });
    html+='</tbody></table>';
    body.innerHTML=html;
  }catch(e){ body.innerHTML='<div class="cc" style="padding:16px;color:#e0696b">Error: '+esc(String(e))+'</div>'; }
}
function filterInputSheet(){
  var q=((document.getElementById("inputsheet_filter")||{}).value||"").toLowerCase().trim();
  var body=document.getElementById("ishbody"); if(!body) return;
  Array.prototype.forEach.call(body.querySelectorAll("tr"), function(tr){
    if(!q){ tr.style.display=""; return; }
    tr.style.display = (tr.textContent.toLowerCase().indexOf(q)>=0) ? "" : "none";
  });
}

function navToBrandCreate(){
  // open a blank brand setup so the user can create a new brand profile
  enterWorkspaceBlank();
}
function enterWorkspaceBlank(){
  ACTIVE_WS={key:"",label:"New brand",brand:"new"};
  document.getElementById("home").classList.remove("show");
  document.getElementById("workspace").classList.add("show");
  document.getElementById("ws_nm").textContent="New brand";
  document.getElementById("ws_sub").textContent="";
  document.getElementById("nav_setup").style.display="flex";
  document.getElementById("crumbs").innerHTML='<span class="sep">/</span><span class="here">New brand</span>';
  navTo("setup");
}

// ---- Image refs section: shows this workspace's saved reference image ----
let _IREF_PROFILE = null;
async function loadImageRefs(){
  const box=document.getElementById("imagerefsbody");
  let html="";
  // brand reference card (brands only)
  if(ACTIVE_WS && ACTIVE_WS.brand){
    let prof={};
    try{ prof=await (await fetch("/brand/get/"+encodeURIComponent(ACTIVE_WS.brand))).json(); }catch(e){}
    _IREF_PROFILE = prof.profile || prof || {};
    const ref=_IREF_PROFILE.main_image_reference||"";
    html+=`
      <div class="card" style="max-width:560px">
        <div class="kvsec">Brand main-image reference</div>
        <p class="cc" style="margin:0">Offered as the reference when generating a main image for any product in this brand (still overridable per-listing).</p>
        ${ref?`<img class="thumb" style="width:160px;height:160px" src="${esc(ref)}">`:'<div class="hint cc">No reference saved yet.</div>'}
        <div style="display:flex;gap:6px;align-items:center">
          <input class="ed" id="iref_input" style="flex:1" placeholder="https://… or upload →" value="${esc(ref)}">
          <label class="uploadbtn"><i class="ti ti-upload"></i> Upload
            <input type="file" accept="image/*" style="display:none" onchange="uploadIRef(this)"></label>
        </div>
        <div><button class="primary" onclick="saveImageRef()">Save reference</button></div>
      </div>`;
  } else {
    html+=`<div class="reqnote">Dropshipping uses each listing's eBay source image as the AI reference automatically. The media library below holds every image you generate or upload, filed by SKU.</div>`;
  }
  // media library: folders per SKU
  html+=`<div class="kvsec" style="margin-top:18px"><i class="ti ti-folders"></i> Media library — by SKU</div>
         <div id="medialib"><div class="cc">Loading media…</div></div>`;
  box.innerHTML=html;
  loadMediaLibrary();
}
async function uploadIRef(input){
  var file=input.files&&input.files[0]; if(!file) return;
  try{
    var dataUrl=await _fileToDataURL(file);
    var brand=(ACTIVE_WS&&ACTIVE_WS.brand)||'brand';
    var res=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:'_brand_'+brand,data:dataUrl,name:file.name,kind:'brandref'})});
    var j=await res.json();
    if(j.ok){ document.getElementById('iref_input').value=j.url; toast('Uploaded — click Save reference'); loadMediaLibrary(); }
    else toast('Upload failed: '+(j.error||''));
  }catch(e){ toast('Error: '+e); }
}
function _fmtBytes(n){
  n=Number(n)||0;
  if(n<1024) return n+' B';
  if(n<1048576) return (n/1024).toFixed(0)+' KB';
  return (n/1048576).toFixed(2)+' MB';
}
async function loadMediaLibrary(){
  var host=document.getElementById('medialib'); if(!host) return;
  try{
    var j=await (await fetch('/media/list')).json();
    if(!j.ok){ host.innerHTML='<div class="cc">Could not load media: '+esc(j.error||'')+'</div>'; return; }
    if(!j.folders||!j.folders.length){ host.innerHTML='<div class="emptynote">No media yet. Generated and uploaded images will appear here, filed by SKU.</div>'; return; }
    host.innerHTML=j.folders.map(function(f){
      return '<details class="mediafolder"><summary><i class="ti ti-folder"></i> '+esc(f.sku)+' <span class="cc">('+f.count+')</span></summary>'+
        '<div class="mediagrid">'+f.files.map(function(im){
          var _dim=(im.width&&im.height)?(im.width+'×'+im.height+' px'):'';
          var _sz=(im.bytes)?_fmtBytes(im.bytes):'';
          var _grp=im.group?('<span class="medagroup">'+esc(im.group)+'</span>'):'';
          var _meta=(_dim||_sz)?('<div class="mediameta">'+esc([_dim,_sz].filter(Boolean).join(' · '))+'</div>'):'';
          return '<div class="mediacell"><img src="'+esc(im.url)+'" loading="lazy" onclick="window.open(\''+esc(im.url)+'\')">'+_grp+
            '<button class="mediadel" title="Delete" onclick="delMedia(\''+esc(im.url)+'\')"><i class="ti ti-x"></i></button>'+
            '<button class="mediaedit" title="Edit this image (AI changes only what you ask, keeps the rest)" onclick="editMediaImage(\''+esc(im.url)+'\',\''+esc(f.sku)+'\')"><i class="ti ti-wand"></i> Edit</button>'+
            _meta+'</div>';
        }).join('')+'</div></details>';
    }).join('');
  }catch(e){ host.innerHTML='<div class="cc">Error: '+esc(String(e))+'</div>'; }
}
async function editListingImage(sku, url, idx){
  const instruction = prompt("What should the AI change about this image?\n\nIt edits ONLY what you ask and keeps everything else the same.\n\nExamples: \"pure white background\", \"add a soft shadow\", \"brighten the product\".");
  if(instruction===null) return;
  if(!instruction.trim()){ toast("Tell me what to change."); return; }
  toast("Editing image…");
  try{
    var r=(ROWS||[]).find(x=>String(x.sku)===String(sku));
    var res=await (await fetch("/genimage/refine",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({image:url, instruction:instruction.trim(),
        title:(r&&r.title)||"", kind:"main",
        text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)})})).json();
    if(!res.ok){ toast("Edit failed: "+(res.error||"unknown")); return; }
    var sv=await (await fetch("/media/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, data:res.data_url, kind:"generated"})})).json();
    if(!sv.ok){ toast("Edited, but could not save: "+(sv.error||"")); return; }
    // if this was the MAIN image, offer to set the edited version as the new main
    if(idx===0 && confirm("Edited image saved. Set it as the MAIN image for this listing?\n(This updates the app copy; use \"Push image to live\" to send it to Amazon.)")){
      var useUrl=sv.url||res.data_url;
      await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sku:sku,target:'attr',key:'main_product_image_locator',value:useUrl})});
      toast("✓ Set as main image (app copy). Use 'Push image to live' to send to Amazon.");
      loadRows();
    } else {
      toast("✓ Edited image saved to "+sku+"'s library.");
    }
  }catch(e){ toast("Edit error: "+e); }
}
async function editMediaImage(url, sku){
  const instruction = prompt("What should the AI change about this image?\n\nIt edits ONLY what you ask and keeps everything else the same (same product, same layout, same colours).\n\nExamples: \"make the background pure white\", \"add a soft shadow under the product\", \"remove the text in the corner\".");
  if(instruction===null) return;
  if(!instruction.trim()){ toast("Tell me what to change."); return; }
  toast("Editing image… this takes a moment.");
  try{
    // the refine endpoint accepts a URL or data-url as the base image
    var it=_itemForSku(sku);
    var res=await (await fetch("/genimage/refine",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({image:url, instruction:instruction.trim(),
        title:(it&&it.title)||"", kind:"main",
        text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)})})).json();
    if(!res.ok){ toast("Edit failed: "+(res.error||"unknown")); return; }
    // save the edited image back into the same SKU's media library
    var sv=await (await fetch("/media/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, data:res.data_url, kind:"generated"})})).json();
    if(sv.ok){
      toast("✓ Edited image saved to "+sku+"'s library"+(sv.drive_direct_url?" (also on Drive)":""));
      loadMediaLibrary();
    } else {
      toast("Edited, but could not save: "+(sv.error||""));
    }
  }catch(e){ toast("Edit error: "+e); }
}
async function delMedia(url){
  if(!confirm('Delete this image?')) return;
  try{ await fetch('/media/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url})}); loadMediaLibrary(); }
  catch(e){ toast('Could not delete: '+e); }
}
async function saveImageRef(){
  if(!ACTIVE_WS||!ACTIVE_WS.brand) return;
  const val=(document.getElementById("iref_input")||{}).value||"";
  const prof=Object.assign({}, _IREF_PROFILE||{}, {brand_name:ACTIVE_WS.brand, main_image_reference:val});
  try{
    await fetch("/brand/save",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(prof)});
    toast("Reference image saved");
    loadImageRefs();
  }catch(e){ toast("Could not save: "+e); }
}

// ---- AI settings modal ----
async function openAISettings(){
  const m=document.getElementById("aimodal"); m.classList.add("open");
  // reflect current payload-viewer setting on the toggle
  try{ var _pv=document.getElementById("payloadViewerToggle"); if(_pv) _pv.checked=!!window.SHOW_PAYLOAD_VIEWER; }catch(e){}
  const body=document.getElementById("aimodalbody");
  body.innerHTML="Loading models from OpenRouter…";
  let s; try{ s=await (await fetch("/ai/settings")).json(); }catch(e){ s={ok:false}; }
  if(!s.ok){ body.innerHTML='<div class="reqnote">Could not load AI settings.</div>'; return; }
  // current GLOBAL eBay creds (App ID shown; Cert never returned, only a masked tail)
  let eb; try{ eb=await (await fetch("/settings/ebay")).json(); }catch(e){ eb={ok:false}; }
  const ebSafe=(eb&&eb.ok)?eb:{ebay_app_id:"",has_cert:false,cert_tail:""};
  const keyNote = s.has_key
    ? (s.discover_ok ? `<span class="cc" style="color:#7fd99a">\u2713 OpenRouter connected \u2014 ${ (s.text_models||[]).length } text models, ${ (s.image_models||[]).length } image models available</span>`
                     : `<span class="cc" style="color:#e3b768">Key present, but model discovery failed: ${esc(s.discover_error||'')} (showing fallback list)</span>`)
    : `<div class="reqnote">No <code>openrouter_api_key</code> in your config.json. Get one at <a href="https://openrouter.ai/keys" target="_blank">openrouter.ai/keys</a> and add it locally, then click Refresh.</div>`;
  const opt=(models,chosen)=>models.map(mm=>`<option value="${esc(mm.id)}"${mm.id===chosen?" selected":""}>${esc(mm.name||mm.id)}</option>`).join("");
  body.innerHTML=`
    ${keyNote}
    <table class="kv" style="margin-top:10px">
      <tr><td class="k">Prompt enhancement model<br><span class="cc">writes the detailed image prompt</span></td>
          <td class="v"><select class="ed" id="ai_text">${opt(s.text_models||[], s.select.prompt_enhance)}</select></td></tr>
      <tr><td class="k">Image generation model<br><span class="cc">Nano Banana, GPT Image, Seedream, etc.</span></td>
          <td class="v"><select class="ed" id="ai_image">${opt(s.image_models||[], s.select.image_generate)}</select></td></tr>
    </table>
    <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
      <button class="primary" onclick="saveAISettings()">Save selection</button>
      <button onclick="refreshAIModels()"><i class="ti ti-refresh"></i> Refresh model list</button>
      <a class="browsemodels" href="https://openrouter.ai/models" target="_blank" rel="noopener"><i class="ti ti-external-link"></i> Browse all models</a>
      <button onclick="closeAISettings()">Cancel</button>
    </div>
    <div class="adminbox" style="margin-top:12px">
      <div style="font-weight:600;margin-bottom:6px"><i class="ti ti-shopping-cart"></i> eBay source credentials <span class="cc">(global default)</span></div>
      <div class="cc" style="font-size:11.5px;margin-bottom:8px">Used to scrape each row's source eBay listing (title, item specifics, images) via eBay's Browse API. These are the app-wide defaults; any single account can override them in its <b>Account &amp; sheets</b> editor. <b>No eBay Dev ID is required</b> — the Browse API authenticates with only App ID + Cert ID.</div>
      <table class="kv">
        <tr><td class="k">eBay App ID <span class="cc">(client ID)</span></td><td class="v"><input class="ed" id="ebay_app" value="${esc(ebSafe.ebay_app_id||'')}" placeholder="YourApp-xxxx-PRD-xxxx-xxxx"></td></tr>
        <tr><td class="k">eBay Cert ID <span class="cc">(secret)</span></td><td class="v"><input class="ed" id="ebay_cert" type="password" placeholder="${ebSafe.has_cert?('•••• '+esc(ebSafe.cert_tail||'')+' — leave blank to keep'):'paste Cert ID'}"></td></tr>
      </table>
      <div style="margin-top:8px"><button class="primary" onclick="saveEbaySettings()"><i class="ti ti-check"></i> Save eBay credentials</button> <span id="ebay_status" class="cc"></span></div>
    </div>
    <div class="adminbox">
      <div style="font-weight:600;margin-bottom:6px"><i class="ti ti-shield-lock"></i> Admin — transparency &amp; access</div>
      <label class="seccheck" style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px">
        <input type="checkbox" id="adm_show_logic" ${ (s.admin&&s.admin.show_logic)!==false ? 'checked':'' }>
        <span><b>Show "How this works" logic panels</b><br><span class="cc">The collapsible arrows under each button that explain the real backend workflow. Turn OFF to hide them from everyone.</span></span>
      </label>
      <label class="seccheck" style="display:flex;align-items:flex-start;gap:8px">
        <input type="checkbox" id="adm_preview_user" ${ (s.admin&&s.admin.preview_as_user) ? 'checked':'' }>
        <span><b>Preview as a regular user</b><br><span class="cc">See the app exactly as a non-admin signup would — the logic panels are hidden while this is on, even if the option above is enabled. Uncheck to return to admin view.</span></span>
      </label>
      <div style="margin-top:8px"><button class="primary" onclick="saveAdminSettings()"><i class="ti ti-check"></i> Save admin settings</button> <span id="adm_status" class="cc"></span></div>
    </div>
    <p class="cc" style="margin-top:12px">One OpenRouter key powers every model. Your key lives only in your local config.json \u2014 this app never displays or stores the key value.</p>`;
}
async function refreshAIModels(){
  const body=document.getElementById("aimodalbody"); body.innerHTML="Refreshing from OpenRouter…";
  try{ await fetch("/ai/settings?refresh=1"); }catch(e){}
  AISET=null; openAISettings();
}
async function saveAdminSettings(){
  const show=(document.getElementById("adm_show_logic")||{checked:true}).checked;
  const prev=(document.getElementById("adm_preview_user")||{checked:false}).checked;
  const st=document.getElementById("adm_status");
  if(st) st.textContent="Saving…";
  try{
    const j=await (await fetch("/admin/logic_settings",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({show_logic:show, preview_as_user:prev})})).json();
    if(j.ok){
      window.LOGIC_VISIBLE = !!j.show_logic && !j.preview_as_user;
      AISET=null;
      if(typeof refreshStaticHowPanels==="function") refreshStaticHowPanels();
      if(st) st.innerHTML='<span style="color:#7fd99a">\u2713 saved — '+(window.LOGIC_VISIBLE?'logic panels visible':'logic panels hidden')+'</span>';
      toast(window.LOGIC_VISIBLE?"Logic panels are now visible.":"Logic panels are now hidden (user view).");
    } else { if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(String(e))+'</span>'; }
}
function closeAISettings(){ document.getElementById("aimodal").classList.remove("open"); }
async function saveAISettings(){
  const t=(document.getElementById("ai_text")||{}).value;
  const i=(document.getElementById("ai_image")||{}).value;
  try{
    await fetch("/ai/settings",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({prompt_enhance:t,image_generate:i})});
    AISET=null; // force reload in image-gen panels
    toast("AI selection saved");
    closeAISettings();
  }catch(e){ toast("Could not save: "+e); }
}
async function saveEbaySettings(){
  const app=((document.getElementById("ebay_app")||{}).value||"").trim();
  const cert=((document.getElementById("ebay_cert")||{}).value||"").trim();
  const st=document.getElementById("ebay_status");
  if(st) st.textContent="Saving…";
  try{
    const j=await (await fetch("/settings/ebay",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ebay_app_id:app, ebay_cert_id:cert})})).json();
    if(j.ok){ if(st) st.innerHTML='<span style="color:#7fd99a">✓ saved</span>'; toast("eBay credentials saved"); }
    else { if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(String(e))+'</span>'; }
}

// ---- GLOBAL generation status bar + full-visibility panel (works everywhere) ----
// Image jobs run server-side, so they continue no matter what page you're on or
// even if you navigate away. The bottom bar shows overall progress on ANY page;
// the panel (View) shows EVERY planned image, its concept, live status, the
// finished thumbnail, and any error. Stop-all is always available.
let GEN_STATUS_POLL=null;
let GEN_ACTIVE_JOB="";      // the job whose detail the panel shows
let GEN_PANEL_OPEN=false;

async function pollGenStatus(){
  try{
    const j=await (await fetch("/genimage/jobs_active")).json();
    const bar=document.getElementById("genstatusbar");
    const txt=document.getElementById("genstatustext");
    if(bar&&txt){
      if(j.ok && j.jobs && j.jobs.length){
        let done=0,total=0;
        j.jobs.forEach(x=>{ done+=(x.done||0); total+=(x.total||0); });
        txt.textContent="Generating "+done+"/"+total+" image"+(total===1?"":"s")+"…";
        bar.style.display="flex";
        // adopt an active job for the panel if we don't have one yet
        if(!GEN_ACTIVE_JOB && j.jobs[0]) GEN_ACTIVE_JOB=j.jobs[0].job;
      } else {
        bar.style.display="none";
      }
    }
    // if the detail panel is open, refresh it
    if(GEN_PANEL_OPEN && GEN_ACTIVE_JOB){ refreshGenPanel(); }
  }catch(e){}
}
function startGenStatusPoll(){
  if(GEN_STATUS_POLL) return;
  pollGenStatus();
  GEN_STATUS_POLL=setInterval(pollGenStatus, 2000);
}
function openGenPanel(){
  const p=document.getElementById("genpanel"); if(!p) return;
  p.classList.add("open"); GEN_PANEL_OPEN=true;
  refreshGenPanel();
}
function closeGenPanel(){
  const p=document.getElementById("genpanel"); if(p) p.classList.remove("open");
  GEN_PANEL_OPEN=false;
}
async function refreshGenPanel(){
  if(!GEN_ACTIVE_JOB) return;
  let st;
  try{ st=await (await fetch("/genimage/job_status?job="+encodeURIComponent(GEN_ACTIVE_JOB))).json(); }
  catch(e){ return; }
  if(!st || !st.ok) return;
  const head=document.getElementById("genpanelhead");
  const grid=document.getElementById("genpanelgrid");
  const stopBtn=document.getElementById("genpanelstop");
  const okN=(st.results||[]).filter(r=>r.ok).length;
  const failN=(st.results||[]).filter(r=>r&&!r.ok).length;
  if(head){
    if(st.status==="running"){
      head.innerHTML='<span class="genspin"></span> Generating '+st.done+' of '+st.total+
        ' — <span style="color:#7fd99a">'+okN+' done</span>'+(failN?(' · <span style="color:#e0696b">'+failN+' failed</span>'):'');
    } else if(st.status==="error" && st.error==="stopped by user"){
      head.innerHTML='<span style="color:#e3b768">■ Stopped. '+okN+'/'+st.total+' finished before stopping.</span>';
    } else {
      head.innerHTML='<span style="color:#7fd99a">✓ Complete — '+okN+'/'+st.total+' generated'+
        (failN?(' · <span style="color:#e0696b">'+failN+' failed</span>'):'')+
        '. Saved to each product\u2019s library.</span>';
    }
  }
  if(stopBtn) stopBtn.style.display=(st.status==="running")?"":"none";
  if(grid){
    const plan=st.plan||[];
    const results=st.results||[];
    // build the card for each planned image; match results by index (jobs run in order)
    let html=plan.map((pl,i)=>{
      const r=results[i];
      let statusHtml, thumb="";
      if(!r){
        statusHtml = (i===results.length)
          ? '<span style="color:#9cc1ff"><span class="genspin"></span> generating…</span>'
          : '<span class="cc">queued</span>';
      } else if(r.ok && r.data_url){
        statusHtml='<span style="color:#7fd99a">✓ done'+(r.saved_url?' · saved':'')+'</span>';
        thumb='<img src="'+r.data_url+'" style="width:100%;border-radius:7px;margin-bottom:5px">';
      } else {
        statusHtml='<span style="color:#e0696b" title="'+esc(r.error||"failed")+'">✗ '+esc((r.error||"failed").slice(0,60))+'</span>';
      }
      return '<div style="border:1px solid var(--line);border-radius:9px;padding:8px;background:var(--panel2)">'
        + thumb
        + '<div style="font-size:11.5px;font-weight:600">'+esc(pl.img_code||("#"+(i+1)))+' · '+esc(pl.sku||"")+'</div>'
        + '<div class="cc" style="font-size:10.5px;margin:2px 0;max-height:52px;overflow:auto">'+esc((pl.concept||pl.label||"").slice(0,140))+'</div>'
        + '<div style="font-size:11px;margin-top:3px">'+statusHtml+'</div>'
        + '</div>';
    }).join("");
    grid.innerHTML=html || '<div class="cc">No jobs.</div>';
  }
}
async function stopAllGenerations(){
  if(!confirm("Stop ALL image generations currently running?")) return;
  try{
    const j=await (await fetch("/genimage/stop_all",{method:"POST"})).json();
    toast("Stopping "+(j.stopped||0)+" batch(es)… in-flight images finish, the rest are cancelled.");
    if(typeof STUDIO_POLL!=="undefined" && STUDIO_POLL){ clearInterval(STUDIO_POLL); STUDIO_POLL=null; }
    setTimeout(pollGenStatus, 800);
  }catch(e){ toast("Could not stop: "+e); }
}

// boot into the home screen
window.addEventListener("DOMContentLoaded", function(){ try{ if(localStorage.getItem("priv_on")==="1"){ togglePrivacy(); } }catch(e){} loadAISettings().then(function(){ if(typeof refreshStaticHowPanels==="function") refreshStaticHowPanels(); }); loadHome(); startGenStatusPoll(); });

</script>

<div id="genpanel" class="modalwrap" style="z-index:115">
  <div class="modal" style="max-width:760px;position:relative">
    <button class="x" onclick="closeGenPanel()">×</button>
    <h3><i class="ti ti-photo-bolt"></i> Image generation</h3>
    <div id="genpanelhead" class="cc" style="margin:2px 0 10px">Starting…</div>
    <div style="margin-bottom:10px">
      <button id="genpanelstop" onclick="stopAllGenerations()" style="background:#3a1d24;border:1px solid #5c2a33;color:#ffb3b3;border-radius:7px;padding:6px 14px;cursor:pointer"><i class="ti ti-player-stop"></i> Stop all generation</button>
      <span class="cc" style="margin-left:8px">Images save to each product's library as they finish — safe to close this; use the bottom bar to reopen.</span>
    </div>
    <div id="genpanelgrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;max-height:60vh;overflow:auto"></div>
  </div>
</div>
<div id="genstatusbar" style="display:none;position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:120;
     background:#141b2b;border:1px solid #2c3a55;border-radius:10px;padding:9px 14px;
     box-shadow:0 8px 28px rgba(0,0,0,.45);align-items:center;gap:12px;font-size:13px;color:#cfe0ff;min-width:280px">
  <span class="genspin"></span>
  <span id="genstatustext">Generating…</span>
  <button onclick="openGenPanel()" style="background:#1b2942;border:1px solid #2c3a55;color:#cfe0ff;border-radius:7px;padding:5px 12px;cursor:pointer;font-size:12px"><i class="ti ti-eye"></i> View</button>
  <button onclick="stopAllGenerations()" style="background:#3a1d24;border:1px solid #5c2a33;color:#ffb3b3;border-radius:7px;padding:5px 12px;cursor:pointer;font-size:12px"><i class="ti ti-player-stop"></i> Stop all</button>
</div>
<button class="fab" id="fab" onclick="toggleChat()" title="Ask Claude about this product">✦ Ask Claude</button>
<div class="chatwrap" id="chatwrap">
  <div class="chathead">
    <b>Ask Claude</b>
    <select id="chatctx" title="Attach a listing as context"><option value="">— general —</option></select>
    <button class="x" onclick="toggleChat()" title="Close">×</button>
  </div>
  <div class="chatbody" id="chatbody">
    <div class="chatempty" id="chatempty">Ask about attribute values — e.g. “typical size for a folding camping chair?” or “is assembly required?”<br><br>Pick a listing above to give me its context, and paste a competitor image URL (right-click image → Copy image address) or attach a screenshot for me to look at.</div>
  </div>
  <div class="chatfoot">
    <div class="chips" id="chatchips"></div>
    <div class="chatin">
      <button class="ic" onclick="document.getElementById('chatfile').click()" title="Attach image">📎</button>
      <input type="file" id="chatfile" accept="image/*" style="display:none" onchange="onChatFile(event)">
      <textarea id="chatinput" rows="1" placeholder="Ask… (paste a competitor image URL too)" onkeydown="chatKey(event)" onpaste="onChatPaste(event)"></textarea>
      <button class="snd" id="chatsend" onclick="sendChat()">Send</button>
    </div>
    <div class="chathint">Tip: paste a competitor image URL or attach a screenshot, then ask “is assembly required?”. This is just chat — nothing is published.</div>
  </div>
</div>
</body>
</html>
"""



if __name__ == "__main__":
    try:
        with open(".app_port", "w") as _pf:
            _pf.write(str(PORT))
    except Exception:
        pass
    print(f"\n  Listing Review dashboard -> http://{HOST}:{PORT}")
    print("  (Ctrl+C to stop)\n")
    _load_cogs_overrides()
    dashboard_brand_patch.register(app, _cfg, _ws, _records, _run_lock,
                                   _running, _ANSI, SCRIPT, sys, _state, CONFIG_PATH)
    import routes.drive_routes as _drive_routes
    _drive_routes.register(app, _active_account=_active_account, _cfg=_cfg,
                           _media_root=_media_root,
                           _drive_folder_id_from_url=_drive_folder_id_from_url,
                           _drive_service=_drive_service,
                           _drive_upload_image=_drive_upload_image)
    import routes.submit_routes as _submit_routes
    _submit_routes.register(app, _records=_records, _active_account=_active_account,
                            _state=_state, _cfg=_cfg)
    import routes.cogs_routes as _cogs_routes
    _cogs_routes.register(app, _state=_state, _COGS_OVERRIDE=_COGS_OVERRIDE,
                          _save_cogs_overrides=_save_cogs_overrides,
                          _estimate_profit=_estimate_profit)
    import routes.view_routes as _view_routes
    _view_routes.register(app, _state=_state, _cfg=_cfg,
                          CONFIG_PATH=CONFIG_PATH, OUTPUT_TAB=OUTPUT_TAB)
    import routes.recipes_routes as _recipes_routes
    _recipes_routes.register(app, _active_brand=_active_brand, _load_recipes=_load_recipes,
                             _save_recipes=_save_recipes, _media_root=_media_root)
    app.run(host=HOST, port=PORT, threaded=True)
