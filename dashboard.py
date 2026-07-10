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

# The selected workspace (the account AND its sheet/tab scope) lived ONLY in the in-memory
# _state dict, so EVERY restart -- a Render redeploy, an instance recycle -- silently dropped
# it. _active_account() then fell back to accounts[0] (Jack Reacherd) and _ws() fell back to
# the default sheet, so the user saw the wrong account's sheets and thought their saved sheet
# links had "reverted". Persist the selection next to config.json (Render's persistent disk)
# and restore it on boot, so the chosen workspace survives restarts.
_ACTIVE_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "app_state.json")
_ACTIVE_KEYS = ("active_account_id", "active_marketplace", "active_sheet_id",
                "active_tab", "active_tab_gid", "active_view")


def _save_active_state():
    """Persist the chosen workspace so a restart can't silently switch accounts."""
    try:
        data = {k: _state.get(k) for k in _ACTIVE_KEYS if _state.get(k) is not None}
        with open(_ACTIVE_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _load_active_state():
    """Restore the workspace chosen before the last restart. Only fills blanks, so an
    explicit in-session selection always wins."""
    try:
        with open(_ACTIVE_STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in _ACTIVE_KEYS:
                if k in data and not _state.get(k):
                    _state[k] = data[k]
    except Exception:
        pass


_load_active_state()   # restore on boot, before any request is served


class ConfigError(Exception):
    pass


class SheetScopeError(Exception):
    """An account workspace has no output sheet/tab configured.

    Raised instead of falling back to the shared default sheet + OUTPUT_TAB.
    That tab holds whichever account was configured first, so the fallback
    showed one account's listings under another's name -- and a Submit there
    would have published them under the wrong Amazon seller.
    """
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
    tab = str(_state.get("active_tab") or "").strip()
    gid = str(_state.get("active_tab_gid") or "").strip()

    # An ACCOUNT workspace must never fall back to the shared default sheet/tab:
    # that tab belongs to the first-configured account. Refuse and tell the user
    # what to set. Dropshipping (no active_account_id) keeps the historic default.
    _aid = _state.get("active_account_id")
    _who = _state.get("active_view") or _aid
    if _aid:
        if not _state.get("active_sheet_id"):
            raise SheetScopeError(
                f"{_who} has no output sheet configured, so nothing was read or written. "
                f"Open Account & sheets and paste this account's output Google Sheets link. "
                f"The app will not fall back to another account's sheet.")
        if not gid.isdigit() and not tab:
            raise SheetScopeError(
                f"{_who} has no output tab configured, so nothing was read or written. "
                f"Open Account & sheets and paste the output sheet link with the correct tab "
                f"open, so the URL ends in '#gid=...'. The app will not fall back to the shared "
                f"'{OUTPUT_TAB}' tab, which holds another account's listings.")
    if not tab:
        tab = OUTPUT_TAB
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
    except Exception as e:
        # An account workspace must fail loudly rather than serve the shared tab.
        if _aid:
            raise SheetScopeError(
                f"Could not open or create tab '{tab}' in sheet {sid} for {_who} ({e}). "
                f"Check the output sheet link in Account & sheets, and that the service "
                f"account has edit access. Nothing was read or written.")
        # last resort (dropshipping only): default sheet/tab, keeps the app alive
        return _client().open_by_key(_cfg()["google_spreadsheet_id"]).worksheet(OUTPUT_TAB)


class AccountScopeError(Exception):
    """This workspace may not make the call that was attempted.

    Either no workspace is selected, or the workspace has no Amazon app of its own
    and the call is seller-scoped (it would be answered for the LENDER's seller id)
    or a write (it would modify the lender's catalogue).
    """
    pass


def _active_account():
    """The account (workspace) currently in focus, or None.

    It used to fall back to accounts[0] when nothing was selected. accounts[0] is
    jack_uk, whose credentials are byte-identical to the legacy global sp_api_*
    block -- so ANY request that arrived without a workspace silently ran as Jack
    Reacherd, against Jack's sheet and Jack's Amazon account. Return None instead;
    the callers now refuse rather than guess.
    """
    try:
        import accounts as _acc
        aid = _state.get("active_account_id")
        if not aid:
            return None
        return _acc.get_account(_cfg(), aid, CONFIG_PATH) or None
    except Exception:
        return None


def _sp_creds(marketplace: str = "UK") -> dict:
    """CATALOGUE-scope credentials: product-type definitions, item type keywords,
    valid values, competitor ASIN lookups, fees. These return no seller data and
    cannot write, so a workspace with no Amazon app of its own may BORROW another
    account's app for them (accounts.resolve_catalog_creds).

    For seller-scoped calls or writes use _seller_creds() -- never this.
    """
    acc = _active_account()
    if acc:
        import accounts as _acc
        try:
            creds, lender = _acc.resolve_catalog_creds(_cfg(), acc, CONFIG_PATH)
        except LookupError as e:
            raise AccountScopeError(str(e))
        return creds
    # No account workspace: the built-in Dropshipping workspace. It has no account
    # object, so it uses the app-wide credential block. Catalogue scope only -- the
    # seller-scoped routes all go through _seller_creds(), which refuses here.
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


def _seller_creds(acc: dict = None):
    """(creds, seller_id) for SELLER-scoped calls and writes.

    Requires the workspace to own its Amazon app. A borrowed token authenticates as
    the LENDER, so every seller-scoped response would be the lender's listings,
    inventory and marketplaces -- which is exactly how one workspace ended up
    displaying another's data.
    """
    import accounts as _acc
    acc = acc if acc is not None else _active_account()
    if not acc:
        raise AccountScopeError(
            "No Amazon workspace is selected, so this action was refused rather than "
            "run against whichever account happens to be first in your config. "
            "Open an account workspace and try again.")
    if not _acc.seller_scope_allowed(acc):
        label = acc.get("label") or acc.get("id")
        if _acc.is_borrowed(acc):
            src = _acc.get_account(_cfg(), _acc.credentials_source_id(acc), CONFIG_PATH) or {}
            raise AccountScopeError(
                f"{label} is a read-only workspace. It borrows "
                f"{src.get('label') or _acc.credentials_source_id(acc)}'s Amazon app to look up "
                f"catalogue data, but it may not read or change that account's listings, "
                f"inventory or marketplaces. Connect {label}'s own SP-API credentials to "
                f"enable this.")
        raise AccountScopeError(
            f"{label} has no Amazon credentials, so this action was refused. "
            f"Add its SP-API credentials in Account & sheets.")
    return _acc.account_creds(acc), acc.get("seller_id", "")


def _require_publish(acc: dict = None):
    """Hard gate before ANY write to Amazon. Read-only workspaces never pass."""
    import accounts as _acc
    acc = acc if acc is not None else _active_account()
    if not acc:
        raise AccountScopeError("No Amazon workspace is selected — refusing to publish.")
    if not _acc.can_publish(acc):
        label = acc.get("label") or acc.get("id")
        raise AccountScopeError(
            f"{label} is a read-only workspace and cannot publish to Amazon. "
            f"It can generate listings, but submitting them requires its own "
            f"Seller Central account and SP-API credentials.")
    return acc


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




def _run_img_jobs_bg(jid, jobs, kind):
    """Crash-safe wrapper around the image worker.

    A worker that dies on an unhandled exception -- e.g. the genimage/aplus NameError, or
    any failure BEFORE the per-job try -- never reached _job_finish, so its job sat on
    "running" forever: the UI spun at 0/N and Stop looked broken (Stop only sets a `cancel`
    flag, which a dead worker never reads). This guarantees the job is always retired.
    """
    try:
        _run_img_jobs_bg_inner(jid, jobs, kind)
    except Exception as _we:
        try:
            _job_finish(jid, error=f"worker crashed: {type(_we).__name__}: {str(_we)[:160]}")
        except Exception:
            pass
    finally:
        # Belt-and-braces: whatever happened, never leave the job on "running".
        try:
            with _IMG_JOBS_LOCK:
                _j = _IMG_JOBS.get(jid)
                if _j and _j.get("status") == "running":
                    _j["status"] = "error"
                    _j["error"] = _j.get("error") or "worker exited without finishing"
        except Exception:
            pass


def _run_img_jobs_bg_inner(jid, jobs, kind):
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
                # These handlers were extracted into route modules in Phase 3, so they're
                # no longer bare names in this module. Call them via the Flask view registry
                # (endpoint == function name) -- fixes "name 'genimage_from_concept' is not
                # defined" and the same latent break for recipe/source/secondary/aplus.
                if kind in ("recipe", "creative"):
                    with app.test_request_context(json=payload):
                        resp = app.view_functions["genimage_recipe"]()
                elif kind == "concept":
                    with app.test_request_context(json=payload):
                        resp = app.view_functions["genimage_from_concept"]()
                elif kind == "source":
                    with app.test_request_context(json=payload):
                        resp = app.view_functions["genimage_process_source"]()
                elif kind == "secondary":
                    with app.test_request_context(json=payload):
                        resp = app.view_functions["genimage_secondary_v2"]()
                elif kind == "aplus":
                    with app.test_request_context(json=payload):
                        resp = app.view_functions["aplus_generate"]()
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








_RECORDS_CACHE = {}   # {sheet_id::tab: (ts, records)} -- short TTL to avoid 429s
_RECORDS_TTL = 12     # seconds


def _bust_records_cache():
    """Clear the short read-cache so a just-written change is read fresh."""
    _RECORDS_CACHE.clear()




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










_EDITABLE_COLS = {"Title", "Bullet 1", "Bullet 2", "Bullet 3", "Bullet 4", "Bullet 5",
                  "Description (HTML)", "Search Terms / KW", "Our Price (GBP)",
                  "Brand", "UPC", "Handling Days", "Product Type"}






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
    import routes.media_routes as _media_routes
    _media_routes.register(app, _media_root=_media_root, _safe_sku=_safe_sku,
                           _sku_dir=_sku_dir, _state=_state, _active_account=_active_account,
                           _drive_folder_id_from_url=_drive_folder_id_from_url,
                           _records=_records, _ws=_ws, _drive_upload_image=_drive_upload_image,
                           _drive_map_put=_drive_map_put, _account_media_root=_account_media_root,
                           _sniff_image_ext=_sniff_image_ext, _to_jpeg_bytes=_to_jpeg_bytes,
                           _drive_map_remove=_drive_map_remove, _drive_delete_file=_drive_delete_file)
    import routes.inventory_routes as _inventory_routes
    _inventory_routes.register(app, _INV=_INV, _INV_IMPORT_ERR=_INV_IMPORT_ERR,
                               _INV2=_INV2, _INV2_IMPORT_ERR=_INV2_IMPORT_ERR,
                               _parse_3pl_csv=_parse_3pl_csv, _parse_sales_csv=_parse_sales_csv,
                               _parse_uplift_csv=_parse_uplift_csv,
                               _fetch_fba_inventory_via_spapi=_fetch_fba_inventory_via_spapi,
                               _num=_num, _INV_OUT_DIR=_INV_OUT_DIR, _inv2_cache=_inv2_cache,
                               _INV_ALERT_COUNTS=_INV_ALERT_COUNTS, _cfg=_cfg)
    import routes.optimize_routes as _optimize_routes
    _optimize_routes.register(app, _state=_state, _cfg=_cfg, CONFIG_PATH=CONFIG_PATH,
                              _build_patches=_build_patches)
    import routes.ppc_routes as _ppc_routes
    _ppc_routes.register(app, _PPC=_PPC, _PPC_IMPORT_ERR=_PPC_IMPORT_ERR,
                         _PPC_OUT_DIR=_PPC_OUT_DIR,
                         _parse_pct_from_context=_parse_pct_from_context,
                         _cfg=_cfg, CHAT_MODEL=CHAT_MODEL)
    import routes.accounts_routes as _accounts_routes
    _accounts_routes.register(app, _state=_state, _cfg=_cfg, CONFIG_PATH=CONFIG_PATH,
                              _LIVE_CACHE=_LIVE_CACHE,
                              live_catalog=(lambda: app.view_functions["live_catalog"]()),
                              OUTPUT_TAB=OUTPUT_TAB, ConfigError=ConfigError, _client=_client,
                              _save_active_state=_save_active_state)
    import routes.misc_routes as _misc_routes
    _misc_routes.register(app, CONFIG_PATH=CONFIG_PATH, _active_account=_active_account,
                          _state=_state)
    import routes.autofix_log_routes as _autofix_log_routes
    _autofix_log_routes.register(app, CONFIG_PATH=CONFIG_PATH)
    import routes.aplus_routes as _aplus_routes
    _aplus_routes.register(app, _APLUS_MODULES=_APLUS_MODULES, _cfg=_cfg,
                           _load_img_instructions=_load_img_instructions,
                           _imgresult=_imgresult)
    import routes.settings_routes as _settings_routes
    _settings_routes.register(app, _cfg=_cfg, CONFIG_PATH=CONFIG_PATH,
                              _state=_state, _client=_client)
    import routes.miles_template_routes as _miles_template_routes
    _miles_template_routes.register(app, _cfg=_cfg, _state=_state,
                                    _load_miles_templates=_load_miles_templates,
                                    _save_miles_templates=_save_miles_templates,
                                    _miles_tpl_dir=_miles_tpl_dir,
                                    _sniff_image_ext=_sniff_image_ext,
                                    _sku_dir=_sku_dir, _safe_sku=_safe_sku)
    import routes.miles_routes as _miles_routes
    _miles_routes.register(app, _miles_set_pref=_miles_set_pref, _miles_get_pref=_miles_get_pref,
                           CONFIG_PATH=CONFIG_PATH, SCRIPT=SCRIPT, _MILES_STATE=_MILES_STATE,
                           _active_account=_active_account, _miles_load_history=_miles_load_history,
                           _miles_save_history=_miles_save_history, _run_lock=_run_lock,
                           _running=_running)
    import routes.genimage_routes as _genimage_routes
    _genimage_routes.register(app, CONFIG_PATH=CONFIG_PATH, _CREATIVE_STRATEGIES=_CREATIVE_STRATEGIES,
                              _IMG_JOBS=_IMG_JOBS, _IMG_JOBS_LOCK=_IMG_JOBS_LOCK,
                              _SECONDARY_ROLES=_SECONDARY_ROLES, _active_brand=_active_brand,
                              _cfg=_cfg, _imgresult=_imgresult,
                              _load_img_instructions=_load_img_instructions,
                              _load_recipes=_load_recipes, _new_img_job=_new_img_job,
                              _records=_records, _run_img_jobs_bg=_run_img_jobs_bg,
                              _safe_sku=_safe_sku, _save_img_instructions=_save_img_instructions,
                              _sku_dir=_sku_dir, _state=_state,
                              _write_attrs_for_sku=_write_attrs_for_sku, _ws=_ws)
    import routes.listing_routes as _listing_routes
    _listing_routes.register(app, CHAT_MODEL=CHAT_MODEL, CONFIG_PATH=CONFIG_PATH, SCRIPT=SCRIPT,
                             SKU_HEADER=SKU_HEADER, STATUS_HEADER=STATUS_HEADER, _ANSI=_ANSI,
                             _EDITABLE_COLS=_EDITABLE_COLS, _URL_RE=_URL_RE,
                             _VALID_SET_STATUS=_VALID_SET_STATUS, _acquire_run_lock=_acquire_run_lock,
                             _active_account=_active_account, _build_patches=_build_patches,
                             _bust_records_cache=_bust_records_cache, _card=_card, _cfg=_cfg,
                             _client=_client, _drive_folder_id_from_url=_drive_folder_id_from_url,
                             _drive_map_get=_drive_map_get, _drive_map_put=_drive_map_put,
                             _drive_upload_image=_drive_upload_image, _ebay_creds=_ebay_creds,
                             _fetch_image_b64=_fetch_image_b64, _load_schema=_load_schema,
                             _marketplace_for_row=_marketplace_for_row, _media_root=_media_root,
                             _options_for=_options_for, _parse_required_missing=_parse_required_missing,
                             _product_types=_product_types, _records=_records,
                             _resolve_fields=_resolve_fields, _run_lock=_run_lock, _running=_running,
                             _schema_attrs=_schema_attrs, _schema_required=_schema_required,
                             _schema_subfields=_schema_subfields, _sp_creds=_sp_creds, _state=_state,
                             _ws=_ws)
    import routes.ui_routes as _ui_routes
    _ui_routes.register(app, CONFIG_PATH=CONFIG_PATH, _kill_proc=_kill_proc,
                        _records=_records, _run_lock=_run_lock, _running=_running, _ws=_ws)
    import routes.live_routes as _live_routes
    _live_routes.register(app, CONFIG_PATH=CONFIG_PATH, _IMG_CACHE=_IMG_CACHE, _IMG_TTL=_IMG_TTL,
                          _LIVE_CACHE=_LIVE_CACHE, _LIVE_TTL=_LIVE_TTL, _cfg=_cfg,
                          _estimate_profit=_estimate_profit,
                          _parse_listings_report=_parse_listings_report,
                          _resolve_cogs=_resolve_cogs, _state=_state)
    import routes.dash_auth_routes as _dash_auth_routes
    _dash_auth_routes.register(app, _APP_PASSWORD=_APP_PASSWORD)
    app.run(host=HOST, port=PORT, threaded=True)
