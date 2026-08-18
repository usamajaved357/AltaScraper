#!/usr/bin/env python3
"""
Local review + run dashboard for the Amazon listing pipeline.

WHAT IT DOES
  - "Generate" / "Retry" / "Export" buttons run amazon_listing_generator.py as a
    background process; its progress streams live into the page (no cmd window).
  - Reads the listing store and shows each listing as a review card: status, IP
    risk, compliance risk, the Notes findings, title, bullets, price/profit, and
    a link to the source listing. The store is this app's own database unless an
    account is still configured for the "sheets" backend.
  - Approve / Hold buttons write Status back to that store.

RUN
  pip install flask
  Google (gspread / google-auth) is OPTIONAL: it is needed only to import from a
  spreadsheet or to use the "sheets" backend. Without it the app runs normally.
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
# image_gen removed: its only public function (generate_main_image) had zero
# callers -- auto-image runs through domain/ai_providers.run_pipeline instead.
# This import was never referenced again anywhere in the file.

from flask import Flask, Response, request, jsonify, session, redirect, url_for, send_from_directory

# GOOGLE IS OPTIONAL NOW, SO IMPORTING IT MUST BE TOO.
#
# These were plain top-level imports, which made gspread and google-auth a hard
# requirement for the app to START -- on a deployment that stores everything in
# its own database and may never touch a spreadsheet. An install without them,
# or one where they fail to import, could not run the app at all rather than
# running it without the import-from-sheet button.
#
# Kept as names so the ~20 places that reference them still read the same; they
# are simply None when Google is not installed, and the paths that need them
# already fail with their own message.
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_AVAILABLE = True
except Exception:                       # ImportError, or a broken install
    gspread = None
    Credentials = None
    GOOGLE_AVAILABLE = False

# --- must match amazon_listing_generator.py -----------------------------------
CONFIG_PATH       = os.environ.get("CONFIG_PATH", "config.json")
# APP_DIR is where the CODE lives; CONFIG_PATH may point somewhere else entirely
# (on Render it is /data/config.json). SCRIPT must be absolute or a subprocess
# launched with any other cwd cannot find it.
APP_DIR           = os.path.dirname(os.path.abspath(__file__))
SCRIPT            = os.path.join(APP_DIR, "amazon_listing_generator.py")
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

# Keep the user signed in across a screen lock, a laptop sleep, and a browser restart.
# The login set session["authed"] but never session.permanent, so Flask issued a plain
# BROWSER-SESSION cookie -- dropped as soon as Chrome suspended/restored the window.
# That is why locking the screen forced a fresh sign-in. A permanent cookie with an
# explicit lifetime survives that. (It does NOT weaken the gate: the cookie is still
# signed with APP_SECRET_KEY, and /logout still clears it.)
from datetime import timedelta as _timedelta
app.permanent_session_lifetime = _timedelta(days=30)

# --- shared-password login gate (hosted deployments only) --------------------
# APP_PASSWORD is only set on a real deployment (Render etc.); locally it's
# unset so the gate no-ops and dev workflow is unchanged.
_APP_PASSWORD = os.environ.get("APP_PASSWORD")


# --- PUBLIC image serving (so Amazon can fetch generated images WITHOUT Drive) ---
# Amazon fetches listing images by URL; it never accepts uploaded bytes. The app's
# own /media/<path> route sits behind the login gate, so Amazon can't reach it --
# which is the ONLY reason the app used to require a Google Drive folder (to get a
# public URL). Instead, serve the SAME file at a login-exempt URL carrying an HMAC
# token of its path, so the link is unguessable but needs no auth. Product images are
# public on Amazon anyway; the token only stops the media tree from being enumerable.
import hmac as _hmac
import hashlib as _hashlib

def _img_token(relpath: str) -> str:
    # SIGNED WITH A KEY THAT OUTLIVES A RESTART -- see domain/image_urls.py.
    #
    # This used app.secret_key, and APP_SECRET_KEY is not set on this
    # deployment, so Flask makes a random one every boot. Amazon does not keep
    # the image; it keeps the ADDRESS and re-fetches it later. Every link
    # already handed over therefore stopped working at the next deploy, and the
    # pictures would fall off the listings some time afterwards with nothing to
    # connect it to the deploy that caused it.
    try:
        from domain import image_urls as _iu
        return _iu.token(CONFIG_PATH, relpath)
    except Exception:
        key = (app.secret_key if isinstance(app.secret_key, bytes)
               else str(app.secret_key).encode())
        return _hmac.new(key, ("pubimg:" + str(relpath)).encode("utf-8"),
                         _hashlib.sha256).hexdigest()[:24]

def _public_media_url(media_url: str) -> str:
    """Turn a local '/media/<relpath>' path into a full, public, Amazon-fetchable URL.
    Returns '' if it isn't a local media path or no base URL can be determined."""
    # ONE BUILDER, in domain/image_urls.py. This used to assemble the URL here
    # and the SUBMIT path had no way to build one at all, so the same picture
    # worked when pushed to a live listing and was silently dropped when the
    # draft it came from was submitted (Rule 12).
    from domain import image_urls as _iu
    out = _iu.public_url(CONFIG_PATH, media_url)
    if out:
        return out
    # Inside a request we can still answer from the host we were reached on,
    # which is what makes this work on a deployment where nobody has set
    # PUBLIC_BASE_URL. The generator cannot do this -- it has no request -- which
    # is exactly why the setting exists.
    m = re.match(r"^/media/(.+)$", str(media_url or ""))
    if not m or ".." in m.group(1):
        return ""
    relpath = m.group(1)
    try:
        base = request.host_url.rstrip("/")
    except Exception:
        return ""
    if base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    from urllib.parse import quote as _q
    return f"{base}/img/{_img_token(relpath)}/{_q(relpath)}"








# The doorman: signed in? and allowed to do this? Both questions are answered by
# auth/guard.py, which holds the whole policy in one readable table. Nothing about
# who-may-do-what is decided in this file.
from auth.guard import make_doorman as _make_doorman
app.before_request(_make_doorman(CONFIG_PATH, _APP_PASSWORD))


@app.route("/img/<token>/<path:relpath>")
def _pubimg(token, relpath):
    """PUBLIC (login-exempt) image serving for Amazon. The URL must carry a valid
    HMAC token for exactly this path, so the media tree can't be enumerated."""
    try:
        if not _hmac.compare_digest(str(token), _img_token(relpath)):
            return ("forbidden", 403)
    except Exception:
        return ("forbidden", 403)
    if ".." in relpath or relpath.startswith("/"):
        return ("bad path", 400)
    root = _media_root()
    full = os.path.normpath(os.path.join(root, relpath))
    if not full.startswith(os.path.normpath(root)) or not os.path.isfile(full):
        return ("not found", 404)
    return send_from_directory(root, relpath, max_age=86400)


@app.errorhandler(500)
@app.errorhandler(Exception)
def _json_errors(e):
    """Ensure API calls return JSON on error, never Flask's HTML error page —
    that HTML is what causes 'Unexpected token <, <!doctype ... is not valid
    JSON' in the browser.

    Which callers want JSON is decided by auth.guard.wants_json(), the same
    function the login doorman uses. It used to be a hardcoded list of URL
    prefixes here, which had gone stale: /users, /ppc, /inventory, /monitor,
    /miles, /submit, /preview and /suggest were all missing, so a crash in any
    of them still sent an HTML page to code expecting JSON.
    """
    import traceback as _tb
    from auth.guard import wants_json as _wants_json
    code = getattr(e, "code", 500) or 500

    # Record it before answering. A server error the user only ever sees as a
    # broken screen is one they have to describe from memory; recorded, it can
    # be read back at /diag with the URL, the time and the real line number.
    # Only genuine faults -- a 404 or a 403 is the app working correctly.
    if code == 500:
        try:
            import domain.selfcheck as _sc
            _sc.record(getattr(request, "path", ""), getattr(request, "method", ""),
                       code, e, user=(session.get("email") or session.get("uid") or ""))
        except Exception:
            pass

    if _wants_json():
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


class _RunningFlag(dict):
    """The legacy run flag, kept working now that runs are concurrent.

    Fifteen places across dashboard.py, listing_routes.py, miles_routes.py and
    ui_routes.py end a run by setting _running["on"] = False. That was a correct
    way to release ONE global lock. With several runs at once it is ambiguous --
    which run just ended? -- and none of those fifteen sites has the answer.

    The THREAD has the answer: every run occupies its own thread. So setting the
    flag to False releases whatever slot this thread is holding, and all fifteen
    call sites keep working exactly as written. Rule 12 again: change the
    behaviour in one place rather than the call sites in fifteen.
    """

    def __setitem__(self, key, value):
        if key == "on" and not value:
            try:
                from domain.run_slots import SLOTS as _S
                _S.release_current()
            except Exception:
                pass
        dict.__setitem__(self, key, value)


_running = _RunningFlag({"on": False, "proc": None, "started": 0.0,
                         "key": None, "busy_reason": ""})
_RUN_MAX_SECONDS = 600   # a Preview/Submit should never take >10 min; after that the
                          # lock is presumed stuck (abandoned stream) and is reclaimable.

def _acquire_run_lock(account_id=None, sku=""):
    """Try to start a run. True if we may, False if a limit says otherwise.

    WAS: one flag for the whole app, so ONE Preview or Submit at a time no matter
    who asked or what for. Two people could not work at once and the second was
    told "a run is already in progress" however unrelated their listing was.

    NOW: domain/run_slots.py decides, per ACCOUNT and per SKU. The same SKU still
    never runs twice at once -- that is correctness, two runs would write the same
    sheet row and submit the same listing twice -- and each Amazon account is
    capped, because SP-API quota is per selling account and exceeding it turns
    into throttling that reads as Amazon being broken. Different accounts do not
    block each other at all.

    Returns a bool so the ~2 existing callers are unchanged; the KEY needed to
    release it is stashed on _running for them. Callers that can name their
    account and SKU should pass them -- those that cannot fall back to the active
    workspace, which is what the single lock effectively assumed anyway.
    """
    from domain.run_slots import SLOTS as _SLOTS
    from domain import job_owner as _jo
    if account_id is None:
        account_id = _state.get("active_account_id", "") or ""
    ok, res = _SLOTS.acquire(account_id, sku, owner=_jo.current())
    if not ok:
        _running["busy_reason"] = res
        return False
    import time as _t
    _running["busy_reason"] = ""
    # Kept for the existing /stop and status paths, which still read these.
    _running["on"] = True
    _running["started"] = _t.time()
    _running["key"] = res
    return True


def _release_run_lock(key=None):
    """Give the slot back. Safe to call twice."""
    from domain.run_slots import SLOTS as _SLOTS
    k = key or _running.get("key")
    if k:
        _SLOTS.release(k)
    if not _SLOTS.busy():
        _running["on"] = False
        _running["proc"] = None
        _running["started"] = 0.0
_ACTIVE_KEYS = ("active_account_id", "active_marketplace", "active_sheet_id",
                "active_tab", "active_tab_gid", "active_view")

# _state used to be a plain dict, which meant ONE selected workspace for the
# whole server. With two people signed in that is not a limitation, it is a
# hazard: when a VA opened their workspace the owner's changed too, and the
# owner's next Approve/Delete/Submit went to the VA's sheet with no warning.
#
# WorkspaceState answers the workspace keys per signed-in user and everything
# else -- cfg, gc, schemas, vv -- from the one shared cache, exactly as before.
# The ~40 call sites that read _state are untouched: changing the answer is one
# edit, changing the question would have been forty, and forty edits is forty
# chances to miss the one that writes to the wrong Amazon account.
from domain.workspace_state import WorkspaceState as _WorkspaceState
_state    = _WorkspaceState({"cfg": None, "gc": None, "schemas": {}, "vv": None},
                            scoped=_ACTIVE_KEYS)

# The selected workspace (the account AND its sheet/tab scope) lived ONLY in the in-memory
# _state dict, so EVERY restart -- a Render redeploy, an instance recycle -- silently dropped
# it. _active_account() then fell back to accounts[0] (Jack Reacherd) and _ws() fell back to
# the default sheet, so the user saw the wrong account's sheets and thought their saved sheet
# links had "reverted". Persist the selection next to config.json (Render's persistent disk)
# and restore it on boot, so the chosen workspace survives restarts.
_ACTIVE_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), "app_state.json")


def _save_active_state():
    """Persist the SHARED default workspace so a restart can't silently switch
    accounts.

    Reads through .shared() on purpose. app_state.json is the starting point for
    someone who has not chosen a workspace yet and the only thing background work
    can use -- so writing one user's personal choice into it would put the
    original bug back on disk, where it would outlive the process.
    """
    try:
        data = {k: _state.shared(k) for k in _ACTIVE_KEYS
                if _state.shared(k) is not None}
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
                if k in data and not _state.shared(k):
                    _state.set_shared(k, data[k])
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
            from listing import repo as _repo
            header = _repo.read_headers(dflt)
        except Exception:
            header = None
        # Open-or-create-with-headers is shared (Rule 12): the same thing was
        # written out in the generator's init_sheets() and run_brand(), and in
        # data/store.export_to_sheet(). ensure_tab also returns the EXISTING tab
        # untouched if it turns out to be there, which matters here -- this path
        # is reached after a lookup failed, and re-headering a populated tab
        # would shift every column's meaning without changing a single value.
        from listing import repo as _repo
        ws, _created = _repo.ensure_tab(
            book, tab, headers=header, rows=200,
            cols=max(26, len(header or []) or 26), freeze_header=False)
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
    # KEPT BETWEEN RESTARTS, not only for the life of this process.
    #
    # The dict above is lost every time the app restarts -- every deploy, and
    # every idle spin-down on Render -- so the app used to re-fetch every
    # product type from Amazon afterwards. That is two calls each plus a CDN
    # download, 42 of them on one account, and it spends the same quota the
    # sales figures are waiting on. Product type definitions barely change, so
    # a copy on disk is good for a fortnight. See domain/schema_cache.py, which
    # holds the rules; nothing about how to talk to Amazon lives there.
    try:
        from domain import schema_cache as _sc
        _hit = _sc.read(CONFIG_PATH, pt, _mkt)
        if _hit is not None:
            _state["schemas"][_ck] = _hit
            return _hit
    except Exception:
        pass                    # a cache must never be the reason this fails
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
        # ...and on disk, so the next restart does not pay for this again. Same
        # condition deliberately: schema_cache refuses an empty one as well, but
        # the rule is worth being true in both places rather than relied on in
        # one. A failure to store is not a failure to load.
        try:
            from domain import schema_cache as _sc
            _sc.write(CONFIG_PATH, pt, _mkt, info)
        except Exception:
            pass
    return info


def _schema_subfields(pt: str) -> dict:
    return _load_schema(pt).get("subfields", {})


def _schema_enums(pt: str) -> dict:
    return _load_schema(pt)["enums"]


def _schema_required(pt: str) -> list:
    return _load_schema(pt)["required"]


def _schema_attrs(pt: str) -> list:
    return _load_schema(pt)["attrs"]


def _variation_schema(product_type: str, marketplace: str = "") -> dict:
    """The parts of a product type's schema the screens actually read.

    Returns None when the schema could not be loaded at all -- which the caller
    reports as "could not check" instead of quietly treating as "nothing
    allowed", because those two lead to opposite conclusions.

    WHAT THIS USED TO RETURN, AND THE BUG IT CAUSED.

    It kept ONE property -- variation_theme -- and threw the rest away. It is
    injected as `_schema_for` into routes/variations_routes.py, and that module
    serves TWO screens: the variation checker, which wants variation_theme, and
    /listing/image_slots, which asks slots_from_schema() which image attributes
    the type defines.

    So the image picker was handed a schema containing a single property and
    correctly found no image slots in it. Every product type, every listing:
    open a product card, press Listing images, and the slot list was empty --
    "i still dont have an option to select the image secondary image 1 (pt1), 2
    and so on".

    The properties kept are now the ones BOTH callers need. Not the whole schema:
    a product type's schema runs to hundreds of kilobytes and this is held in
    memory per type for the life of the process, which is the reason it was
    trimmed in the first place. Keeping the image attributes as well costs a few
    hundred bytes and is what makes the picker work.
    """
    # Fetched raw rather than read from the cached enums, because the cache keeps
    # only the values and the DEPRECATION list is what matters here: measured on
    # the live UK account, SPACE_HEATER lists 76 themes of which 47 are dead and
    # TOOLS 122 of which 111 are. Offering a dead one is offering something
    # Amazon will not accept.
    _ck = "vt::%s::%s" % (product_type, marketplace or _state.get("active_marketplace") or "UK")
    cached = _state.setdefault("variation_themes", {}).get(_ck)
    if cached is not None:
        return cached
    try:
        import urllib.request                 # imported per-function in this file
        from sp_api.api import ProductTypeDefinitions
        from sp_api.base import Marketplaces
        mkt = (marketplace or _state.get("active_marketplace") or "UK").upper()
        enum_ = Marketplaces.US if mkt == "US" else getattr(Marketplaces, mkt,
                                                            Marketplaces.UK)
        ptd = ProductTypeDefinitions(credentials=_sp_creds(mkt),
                                     marketplace=enum_, timeout=30)
        d = ptd.get_definitions_product_type(
            productType=product_type, requirements="LISTING",
            locale=("en_US" if mkt == "US" else "en_GB"))
        pay = d.payload if hasattr(d, "payload") else d
        link = ((pay.get("schema") or {}).get("link") or {}).get("resource", "")
        if not link:
            return None
        with urllib.request.urlopen(link, timeout=60) as r:
            raw = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None                      # "could not check", not "none allowed"
    props = raw.get("properties") or {}
    kept = {"variation_theme": props.get("variation_theme") or {}}
    # Every image attribute the type defines. slots_from_schema() looks for
    # "image" in the key and sorts MAIN, PT1..PT8, swatch and the offer slots
    # out of whatever it finds, so the filter here has to be as loose as its --
    # narrowing it to a list of names would silently drop any slot Amazon adds.
    for k, v in props.items():
        if "image" in k.lower():
            kept[k] = v
    # THE NAMES OF EVERY ATTRIBUTE THIS TYPE HAS -- names only, not the schemas.
    #
    # A variation theme is written as its attribute names joined by "/", so
    # MATERIAL_TYPE means "group these by the material_type attribute". MEASURED
    # on OUTDOOR_LIVING (UK, 17 Aug 2026): Amazon offers 10 themes, and 7 of the
    # axes those themes name are NOT attributes of the type. It has `material`,
    # not `material_type`; `color`, not `color_name`; and no item_display_height
    # at all.
    #
    # Without this list the checker could only say "these products have no
    # material_type set" -- a refusal nobody can clear, because there is no
    # material_type field on this product type to set. Same shape as the
    # item_type_keyword bug in listing/variations.py: a field Amazon does not
    # carry is not a field anyone can fill in.
    #
    # 114 short strings for OUTDOOR_LIVING. The full schemas are what made this
    # worth trimming; the names are a few kilobytes.
    out = {"properties": kept, "attribute_names": sorted(props.keys()),
           # WHICH ATTRIBUTES THE TYPE CANNOT DO WITHOUT, from the schema and
           # never from Amazon's prose (Rule 4). A parent is held to these like
           # any other listing, and the ones the children disagree on -- their
           # bullet points, their descriptions -- are the ones the parent has to
           # be given for itself.
           "required": [str(r) for r in (raw.get("required") or []) if r]}
    _state["variation_themes"][_ck] = out
    return out


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
        # WHAT THE STOCK COST, and where that came from, ON THE ROW.
        #
        # The row carried no cost at all, so after a reload the COGS cell fell
        # back to reading the SKU prefix -- and a cost typed by hand simply
        # disappeared from the screen it was typed on. Worse than absent: for a
        # SKU whose name carries a number, the cell then showed THAT number, so
        # the override looked as though it had been discarded.
        #
        # Reported as "i am concirned that after putting the cogs in the listngs
        # section for an item will reflect right data about profits".
        #
        # From domain/cogs.resolve -- the one resolver every other screen uses,
        # not a second reading of the SKU here (Rule 12).
        **_card_cogs(gm("SKU", "Sku")),
    }


def _card_cogs(sku):
    """{cogs, cogs_source} for one SKU, from the one resolver. Never raises."""
    try:
        from domain import cogs as _c
        cost, src = _c.resolve(_COGS_OVERRIDE,
                               str(_state.get("active_account_id", "") or ""),
                               str(sku or ""))
        return {"cogs": cost, "cogs_source": src}
    except Exception:
        return {"cogs": None, "cogs_source": ""}




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




_APLUS_CACHE = {}  # key "accountid::MKT" -> {"ts":epoch, "by_asin":{asin:[docs]}}
_APLUS_TTL = 1800  # 30 min. A+ content changes rarely and each refresh is 1+N API calls.
_LIVE_CACHE = {}   # key "accountid::MKT" -> {"ts":epoch, "items":[...]}
_LIVE_TTL = 1800   # 30 min (SP-API is free; matches auto-sync cadence)
# {"accountid::SKU": cost} manual overrides. THE STORE'S OWN DICT, not a copy:
# domain/cogs_store.py owns it, loads into it in place and never replaces it, so
# every module that has ever been handed a reference is looking at the same one.
#
# This used to be a plain {} here, and other modules reached it with
# `import dashboard as _d`. dashboard.py is the file that is RUN, so its name is
# "__main__" -- `import dashboard` loaded the file a SECOND time and gave them a
# different, permanently empty dict. Sales and Orders both did that, so both
# ignored every manual cost ever typed. See domain/cogs_store.py.
from domain import cogs_store as _cogs_store_mod
_COGS_OVERRIDE = _cogs_store_mod.all_overrides()
_COGS_FILE = _cogs_store_mod.path_for(CONFIG_PATH)
_IMG_CACHE = {}  # {"accountid::MKT::SKU": {"url":..., "ts":epoch}} live listing main images

# ---- background image-generation jobs (so the UI never blocks) ----
_IMG_JOBS = {}        # job_id -> {status, total, done, results:[...], error, ts}
_IMG_JOBS_LOCK = threading.Lock()


def _new_img_job(total, label="", plan=None):
    import time as _t, uuid as _u
    jid = _u.uuid4().hex[:12]
    with _IMG_JOBS_LOCK:
        from domain import job_owner as _jo
        _IMG_JOBS[jid] = _jo.stamp(
            {"status": "running", "total": total, "done": 0,
             "results": [], "error": "", "ts": _t.time(),
             "cancel": False, "label": label, "plan": plan or [],
             # WHICH ACCOUNT THIS BATCH BELONGS TO. Jobs carried an owner but no
             # account, so one person's batches were indistinguishable across
             # workspaces: the progress bar for a Nestwell batch appeared while
             # you were in Jack Reacherd, and "Stop all" on that screen ended it.
             # Accounts are independent; their jobs and their Stop buttons have
             # to be too.
             "account": str(_state.get("active_account_id", "") or "")})
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


# =============================================================================
# AUTO-FIX AS A SERVER-SIDE JOB
# =============================================================================
# Auto-fix used to be a loop inside the BROWSER (static/js/autofix.js): it called
# /suggest -> /edit -> /run/api in a JS `while`. So it died whenever the browser
# stopped executing JS -- a locked screen, a slept laptop, a closed tab, a re-login.
# The user would come back to a half-finished batch with no progress shown.
#
# It now runs HERE, on the server, exactly like image generation:
#   * it keeps running when nobody is watching,
#   * ANY signed-in browser can see the same live progress (the job registry is
#     server state, not per-tab state),
#   * it stops only when it finishes, or when the user presses Stop.
# Same code path locally and on Render -- there is no browser dependency left.
# =============================================================================
_AF_JOBS = {}                       # job_id -> {...}
_AF_JOBS_LOCK = threading.Lock()
_AF_MAX_ROUNDS = 8                  # matches the old browser loop


def _af_new(skus, account_id, label=""):
    import time as _t, uuid as _u
    jid = _u.uuid4().hex[:12]
    with _AF_JOBS_LOCK:
        # retire anything older than an hour so the registry can't grow forever
        for k in [k for k, v in _AF_JOBS.items() if _t.time() - v.get("ts", 0) > 3600]:
            _AF_JOBS.pop(k, None)
        from domain import job_owner as _jo
        _AF_JOBS[jid] = _jo.stamp({
            "id": jid, "status": "running", "cancel": False, "error": "",
            "ts": _t.time(), "started_at": _t.strftime("%Y-%m-%d %H:%M:%S"),
            "account_id": account_id, "label": label,
            "skus": list(skus), "total": len(skus), "done": 0,
            "current": "", "current_round": 0,
            "summary": {"cleared": 0, "stuck": 0, "failed": 0, "not_run": len(skus)},
            "results": [],          # one entry per finished SKU
            "steps": [],            # human-readable progress lines
        })
    return jid


def _af_get(jid):
    with _AF_JOBS_LOCK:
        j = _AF_JOBS.get(jid)
        return dict(j) if j else None


def _af_active():
    """The job to show when no id is given: the newest RUNNING one, else the newest
    job of any status.

    The fallback matters. Returning only running jobs meant that the moment a run
    finished, this went None -- so the polling browser lost the final result and the
    panel just froze on the last tick. A finished job stays visible (for the hour it
    lives in the registry) so the outcome is always readable, including by someone who
    signs in after it ended.
    """
    # SCOPED TO THE ACCOUNT ASKING. The registry is process-wide and this
    # returned the newest job of ANY account, so opening Jack Reacherd showed a
    # Nestwell auto-fix in progress -- somebody else's SKUs, somebody else's
    # errors, and a Stop button next to them. The job already records the
    # account it was started for; it simply was not being read.
    #
    # A job stamped before accounts were recorded has none, and is still shown:
    # hiding work that is genuinely running is the worse failure.
    acct = str(_state.get("active_account_id", "") or "")
    with _AF_JOBS_LOCK:
        if not _AF_JOBS:
            return None
        def _mine(v):
            a = str(v.get("account_id") or "")
            return (not a) or (not acct) or a == acct
        pool_all = [v for v in _AF_JOBS.values() if _mine(v)]
        if not pool_all:
            return None
        run = [v for v in pool_all if v.get("status") == "running"]
        pool = run or pool_all
        return dict(sorted(pool, key=lambda x: x.get("ts", 0))[-1])


def _af_cancelled(jid):
    with _AF_JOBS_LOCK:
        j = _AF_JOBS.get(jid)
        return bool(j and j.get("cancel"))


def _af_stop(jid=""):
    """Stop one job, or every running job IN THIS ACCOUNT when jid is empty.

    "Every running job" meant every one on the server, so Stop in one workspace
    cancelled an auto-fix loop running in another -- work that was part-way
    through rewriting listings and had to be started again from the beginning.
    Naming a job id still stops exactly that job, wherever it belongs.
    """
    acct = str(_state.get("active_account_id", "") or "")
    n = 0
    with _AF_JOBS_LOCK:
        for k, j in _AF_JOBS.items():
            if j.get("status") != "running":
                continue
            if jid:
                if k != jid:
                    continue
            else:
                a = str(j.get("account_id") or "")
                if a and acct and a != acct:
                    continue
            j["cancel"] = True
            n += 1
    return n


def _af_step(jid, msg):
    with _AF_JOBS_LOCK:
        j = _AF_JOBS.get(jid)
        if j:
            j["steps"].append(msg)
            del j["steps"][:-400]          # keep the tail bounded


def _af_set(jid, **kw):
    with _AF_JOBS_LOCK:
        j = _AF_JOBS.get(jid)
        if j:
            j.update(kw)


def _af_finish(jid, error=""):
    with _AF_JOBS_LOCK:
        j = _AF_JOBS.get(jid)
        if j:
            if j.get("cancel") and not error:
                j["status"] = "stopped"
            else:
                j["status"] = "error" if error else "done"
            if error:
                j["error"] = error


# --- the Preview step, run synchronously inside the worker --------------------
# Reuse the EXISTING /run/api route by consuming its stream generator, rather than
# rebuilding the generator's command line here. That keeps ONE source of truth for
# account/sheet/tab/marketplace scoping -- if that logic changes, auto-fix follows.
_AF_PROSE = re.compile(r"none of the requested|only publishes|fix any flagged errors|then click approve"
                       r"|not processed|were not (?:submitted|processed)|not found in this tab|^\s*accounting:", re.I)
_AF_ERRNUM = re.compile(r"(\d+)\s+(?:error|issue)\(s\)", re.I)
_AF_EFIELD = re.compile(r"\[E\]\s*([a-z0-9_.]+)", re.I)
_AF_NET = re.compile(r"getaddrinfo failed|failed to resolve|nameresolutionerror|max retries exceeded"
                     r"|connectionerror|errno 11002|temporary failure in name resolution"
                     r"|connection timed out|handshake operation timed out", re.I)


def _af_preview(sku):
    """Run one Preview for `sku` and return (verdict, error_fields, lines).

    verdict: ok_preview | error | missing | busy | network | nocreds | unknown
    """
    from urllib.parse import quote as _q
    lines, verdict, n_err, fields = [], None, 0, []
    try:
        with app.test_request_context(f"/run/api?skus={_q(sku)}"):
            resp = app.view_functions["run"]("api")
            for chunk in resp.response:            # drives the generator to completion
                text = chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else str(chunk)
                for raw in text.splitlines():
                    if not raw.startswith("data: "):
                        continue
                    d = raw[6:]
                    lines.append(d)
                    if "[busy]" in d:
                        verdict = "busy"
                    if _AF_NET.search(d):
                        verdict = "network"
                    if "no seller_id" in d.lower():
                        verdict = "nocreds"
                    for m in _AF_EFIELD.finditer(d):
                        if m.group(1) not in fields:
                            fields.append(m.group(1))
                    # NEVER read the generator's explanatory prose as a per-row result:
                    # it names the SKU *and* the words "API_READY, APPROVED", which used
                    # to be misparsed as success.
                    if _AF_PROSE.search(d) or sku not in d:
                        continue
                    low = d.lower()
                    m = _AF_ERRNUM.search(d)
                    if m:
                        verdict, n_err = "error", int(m.group(1))
                    elif "not live" in low or "api call failed" in low or "api_error" in low:
                        verdict, n_err = "error", 0
                    elif "missing" in low and "skip" in low:
                        verdict = "missing"
                    elif "api_ready" in low or "preview clean" in low:
                        verdict = "ok_preview"
    except Exception as e:
        return "exception", fields, lines + [f"preview crashed: {type(e).__name__}: {e}"]
    return (verdict or "unknown"), fields, lines


def _run_autofix_bg(jid):
    """Crash-safe wrapper -- a worker that dies must never leave the job 'running'."""
    try:
        _run_autofix_bg_inner(jid)
    except Exception as e:
        try:
            _af_finish(jid, error=f"worker crashed: {type(e).__name__}: {str(e)[:200]}")
        except Exception:
            pass
    finally:
        try:
            with _AF_JOBS_LOCK:
                j = _AF_JOBS.get(jid)
                if j and j.get("status") == "running":
                    j["status"] = "error"
                    j["error"] = j.get("error") or "worker exited without finishing"
        except Exception:
            pass


def _run_autofix_bg_inner(jid):
    """Suggest -> Apply -> Preview, per SKU, until clean / stuck / stopped."""
    job = _af_get(jid)
    if not job:
        return
    skus = job["skus"]
    acct = job["account_id"]

    with app.app_context():
        for idx, sku in enumerate(skus):
            if _af_cancelled(jid):
                _af_step(jid, "Stopped by user.")
                break
            # The worker writes to whatever sheet _ws() resolves, which follows the
            # ACTIVE workspace. If the user switches account mid-run we would edit the
            # wrong account's rows -- refuse rather than corrupt someone else's sheet.
            if (_state.get("active_account_id") or "") != (acct or ""):
                _af_finish(jid, error="Workspace changed while auto-fix was running, so it "
                                      "stopped to avoid editing another account's listings. "
                                      "Go back to the original workspace and run it again.")
                return

            _af_set(jid, current=sku, current_round=0)
            _af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — starting")
            rounds, prev_errors, outcome, diagnosis = [], None, "failed", ""

            for rnd in range(1, _AF_MAX_ROUNDS + 1):
                if _af_cancelled(jid):
                    break
                _af_set(jid, current_round=rnd)
                entry = {"round": rnd, "suggestions": [], "applied": [], "skipped": [],
                         "verdict": None, "error_fields": [], "diagnosis": ""}

                # 1) ask for suggestions
                try:
                    with app.test_request_context(json={"sku": sku}):
                        sres = app.view_functions["suggest"]().get_json() or {}
                except Exception as e:
                    entry["diagnosis"] = f"/suggest crashed: {e}"
                    rounds.append(entry); diagnosis = entry["diagnosis"]; break
                if not sres.get("ok"):
                    err = str(sres.get("error") or "unknown")
                    entry["diagnosis"] = f"/suggest failed: {err}"
                    rounds.append(entry); diagnosis = entry["diagnosis"]; break

                allsug = sres.get("suggestions") or []
                entry["suggestions"] = [{"field": s.get("field"), "value": s.get("value", ""),
                                         "source": s.get("source", ""),
                                         "code_owned": bool(s.get("_code_owned"))} for s in allsug]
                ai = [s for s in allsug if not s.get("_code_owned")]
                code_owned = len(allsug) - len(ai)
                _af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — round {rnd}: "
                              f"{len(ai)} AI suggestion(s), {code_owned} code-owned")

                # 2) apply them -- ONE batched write for the whole round. The old
                # path called /edit per field (2-3 reads + a write + a cache-bust
                # EACH), which tripped Google's per-minute quota (429) on multi-SKU
                # runs. Collapsing a round into a single write also cuts wall-clock.
                for s in ai:
                    if not s.get("value"):
                        entry["skipped"].append({"field": s.get("field"), "reason": "empty AI value"})
                _batch = [{"target": "attr", "key": s.get("field"), "value": s.get("value")}
                          for s in ai if s.get("value")]
                if _batch and not _af_cancelled(jid):
                    try:
                        _ap, _sk = _apply_edits_batch(sku, _batch)
                        entry["applied"].extend(_ap)
                        entry["skipped"].extend(_sk)
                    except Exception as e:
                        for _s2 in _batch:
                            entry["skipped"].append({"field": _s2.get("key"),
                                                     "reason": f"batch edit crashed: {e}"})

                # nothing new to apply and nothing code-owned -> the AI is out of ideas
                if rnd > 1 and not entry["applied"] and code_owned == 0:
                    entry["diagnosis"] = ("Nothing new to apply and no code-owned fields left. "
                                          + ("Amazon still rejects: " + ", ".join(prev_errors.split("|"))
                                             if prev_errors else "The AI has no more suggestions."))
                    rounds.append(entry); outcome = "stuck"; diagnosis = entry["diagnosis"]; break

                # 3) preview
                _af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — round {rnd}: previewing against Amazon…")
                verdict, fields, _lines = _af_preview(sku)
                entry["verdict"] = verdict
                entry["error_fields"] = fields
                rounds.append(entry)

                if _af_cancelled(jid):
                    break
                if verdict == "ok_preview":
                    entry["diagnosis"] = "Amazon accepted the Preview. Ready to Submit."
                    outcome = "cleared"; diagnosis = entry["diagnosis"]
                    _af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — ✓ clean, ready to submit")
                    break
                if verdict in ("network", "nocreds", "busy", "exception"):
                    entry["diagnosis"] = f"Environment issue ({verdict}) — not a listing problem."
                    outcome = "failed"; diagnosis = entry["diagnosis"]; break
                if verdict == "error":
                    key = "|".join(sorted(fields))
                    entry["diagnosis"] = "Amazon flagged: " + (", ".join(fields) or "(no field named)")
                    if prev_errors is not None and prev_errors == key:
                        entry["diagnosis"] += " — identical to the previous round, no progress."
                        outcome = "stuck"; diagnosis = entry["diagnosis"]
                        _af_step(jid, f"[{idx+1}/{len(skus)}] {sku} — stuck on: {', '.join(fields)}")
                        break
                    prev_errors = key
                    continue
                entry["diagnosis"] = f"Unclear outcome ({verdict}). Stopped for safety."
                outcome = "failed"; diagnosis = entry["diagnosis"]; break

            if _af_cancelled(jid):
                _af_step(jid, "Stopped by user.")
                break

            with _AF_JOBS_LOCK:
                j = _AF_JOBS.get(jid)
                if j:
                    j["results"].append({"sku": sku, "outcome": outcome,
                                         "diagnosis": diagnosis, "rounds": rounds})
                    j["done"] = len(j["results"])
                    s = j["summary"]
                    s[outcome] = s.get(outcome, 0) + 1
                    s["not_run"] = max(0, j["total"] - j["done"])

    _af_finish(jid)










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
    # SELLER SCOPE. The Inventories API answers for the TOKEN's own seller. This used
    # _sp_creds(), the CATALOGUE resolver -- which for a borrowing workspace returns the
    # lender's token, so Miles' Inventory page would have listed Shee'lady's FBA stock
    # (and, before the borrow existed, whatever the global sp_api_* block pointed at,
    # i.e. Jack's). Demand the workspace's own credentials.
    try:
        creds, _ = _seller_creds()
    except AccountScopeError as e:
        return {"ok": False, "by_sku": {}, "error": str(e), "warnings": []}
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
        _run_img_jobs_parallel(jid, jobs, kind)
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


# How many products may be generated for at the same time. Small on purpose:
# every image is a paid model call, and the image APIs rate-limit per account, so
# a large pool converts "faster" into "throttled and more expensive". Three is
# roughly three times quicker than the old strictly-sequential worker without
# getting near the limits. ALTA_IMG_WORKERS overrides it.
def _img_worker_count():
    try:
        n = int(os.environ.get("ALTA_IMG_WORKERS") or 3)
    except Exception:
        n = 3
    return max(1, min(n, 8))


def _run_img_jobs_parallel(jid, jobs, kind):
    """Generate for several PRODUCTS at once, images within a product in order.

    The worker ran every image in one sequence, so generating 8 images each for
    two products meant 16 one after another -- the second product did not start
    until the first had completely finished. Grouping by SKU and running the
    groups concurrently is what "side by side" means here, and it keeps each
    product's own images in their intended order (main before secondaries).

    Splitting by SKU rather than round-robin also keeps a product's images
    together on one thread, so a rate-limit stall delays one product rather than
    smearing across all of them.
    """
    groups = {}
    for jb in jobs:
        groups.setdefault(str(jb.get("sku", "") or "_misc"), []).append(jb)
    chunks = list(groups.values())

    if len(chunks) <= 1:
        _run_img_jobs_bg_inner(jid, jobs, kind, finish=False)
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(_img_worker_count(), len(chunks))) as pool:
            list(pool.map(lambda c: _run_img_jobs_bg_inner(jid, c, kind, finish=False),
                          chunks))
    # Finished exactly once, by the dispatcher. Letting each worker finish the
    # job would retire it the moment the FIRST product was done, and the rest
    # would keep writing results into a job the UI had already stopped watching.
    _job_finish(jid)


def _run_img_jobs_bg_inner(jid, jobs, kind, finish=True):
    """Background worker: runs a list of generation jobs, pushing each result.

    `finish=False` when several of these run as one job (see
    _run_img_jobs_parallel) -- the dispatcher retires the job after all of them.
    """
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
                # WHICH LISTING THIS PICTURE IS FOR.
                #
                # The SKU was on the job WRAPPER and the payload is what gets
                # dispatched, so it never arrived. Every endpoint here grounds
                # its image in the listing via _listing_for(), which needs a sku
                # or a listing and was getting neither -- so every image was
                # designed from a photograph and a title, with the bullets,
                # attributes and package contents never consulted.
                #
                # That is how a set comes back disagreeing with its own copy: an
                # image showing two carabiners under text that says one. Stamped
                # here rather than in each of the five callers, so a new kind of
                # image cannot be added without it.
                if job.get("sku") and not payload.get("sku"):
                    payload["sku"] = job.get("sku")
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
                # "recipe" here is the ENGINE, not the deleted saved-recipe feature.
                # The Creative button ("Generate 3 variations") runs through this
                # view, so genimage_recipe must stay even though no recipe UI is
                # left. See the header of static/js/genimage.js.
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
                            # Use the account captured when the batch was ENQUEUED, not
                            # whatever is active now -- a background job can finish after
                            # a redeploy or a workspace switch, and reading _state here is
                            # what misfiled images (and lost the user's A+ content).
                            _aid = str(job.get("_acct_id", "") or _state.get("active_account_id", "") or "")
                            _acct_root = _account_media_root(_aid) if _aid else _media_root()
                            _dir = os.path.join(_acct_root, _safe_sku(sku))
                            if _sub:
                                _dir = os.path.join(_dir, *_sub.split("/"))
                            os.makedirs(_dir, exist_ok=True)
                            _full = os.path.join(_dir, fname)
                            with open(_full, "wb") as f:
                                f.write(raw_bytes)
                            _pfx = f"/media/_acct/{_safe_sku(_aid)}" if _aid else "/media"
                            _subpart = f"{_sub}/" if _sub else ""
                            saved_url = f"{_pfx}/{_safe_sku(sku)}/{_subpart}{fname}"
                            data["saved_url"] = saved_url
                            data["saved_to_disk"] = True   # the persistent copy that survives redeploys
                            # OPTIONAL mirror to Drive. Drive is a nice-to-have backup, not
                            # required: the image is already safe on the persistent disk
                            # above. So "no Drive folder" is a normal state, not an error --
                            # surfacing it as drive_error made the UI look like the save
                            # failed when it fully succeeded on disk.
                            try:
                                # the account that OWNS this image (captured at enqueue),
                                # not whichever workspace is active now
                                acc = None
                                if _aid:
                                    try:
                                        import accounts as _accmod
                                        acc = _accmod.get_account(_cfg(), _aid, CONFIG_PATH)
                                    except Exception:
                                        acc = None
                                acc = acc or _active_account()
                                folder = (acc or {}).get("drive_folder_url", "")
                                parent_id = _drive_folder_id_from_url(folder) if folder else ""
                                if not parent_id:
                                    data["drive_skipped"] = "no Drive folder configured (optional)"
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
    if finish:
        _job_finish(jid)


_IMG_TTL = 86400  # 24h — product images rarely change


def _load_cogs_overrides():
    """Load the manual costs. The STORE owns them now -- see domain/cogs_store.py.

    This used to `global _COGS_OVERRIDE` and REBIND it to a freshly loaded dict,
    which left anything holding the old one pointing at a dict that would never
    change again. The store loads in place for exactly that reason, and
    _COGS_OVERRIDE below is a reference to the store's own dict rather than a
    copy of it -- so there is one set of manual costs in the process, not one per
    module that went looking.
    """
    from domain import cogs_store as _cs
    _cs.load(CONFIG_PATH)


def _save_cogs_overrides():
    from domain import cogs_store as _cs
    _cs.save(CONFIG_PATH)


# MOVED to domain/cogs.py so the Sales dashboard resolves cost the same way this
# screen does. Same parse, same override precedence -- these are now the one
# definition, called from two places instead of copied into two (Rule 12).
from domain import cogs as _cogs_mod


def _cogs_from_sku(sku):
    """Dropshipping SKUs are formatted {source_price}_{N}Days_{ASIN}; the first
    number is the source cost (incl. shipping). Returns float or None."""
    return _cogs_mod.cost_from_sku(sku)


def _resolve_cogs(account_id, sku):
    """COGS priority: manual override (by SKU) -> price embedded in SKU. Returns
    (cost_or_None, source_label)."""
    return _cogs_mod.resolve(_COGS_OVERRIDE, account_id, sku)


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
    # MARGIN and ROI answer different questions and the card only ever showed the
    # first. Margin is "how much of the sale price do I keep" -- it decides
    # whether a price is healthy. ROI is "how hard is my cash working" -- it
    # decides what to buy next, and on cheap stock it is a far bigger number:
    # 9.50 of goods sold at 18.24 keeps 14.6% margin and returns 28% on the cash.
    roi = (net / float(cogs)) if float(cogs) else None
    return {"price": round(price, 2), "cogs": round(float(cogs), 2),
            "referral": round(referral, 2), "net": round(net, 2),
            "margin": round(margin * 100, 1),
            "roi": (round(roi * 100, 1) if roi is not None else None)}





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

    # CREDIT SAVER: only spend a Claude call when the AI actually has work to do.
    # If the deterministic chain (eBay/competitor source + Amazon enum-snap) already
    # produced a value for EVERY requested field -- or there are no AI fields left at
    # all (all code-owned) -- skip the call entirely. Amazon's Preview is the
    # backstop: any value it rejects comes back as a flagged field and DOES get the
    # AI on the next round. On multi-SKU auto-fix runs this removes most of the
    # per-round AI calls (the ones that were only re-validating already-filled
    # fields), cutting token spend without changing what gets written.
    # Flag-gated OFF by default (per owner): with the flag unset, the AI still runs
    # to re-validate already-sourced values. The "no AI fields at all" case always
    # short-circuits (nothing for the model to do). Set config autofix_skip_ai_when_sourced
    # true to re-enable the credit-saver skip.
    _skip_ai_when_sourced = bool(cfg.get("autofix_skip_ai_when_sourced", False))
    if not fields or (_skip_ai_when_sourced and all(p.get("value") for p in prelim)):
        for p in prelim:
            p.setdefault("confidence", "from source")
        return _code_owned_hits + prelim

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


import threading as _threading
# READ PACER: Google's per-user quota is ~300 reads/min (5/sec). We PACE reads to stay under
# it PROACTIVELY (so a burst can't spike past the limit) instead of only reacting to 429s.
# min_interval 0.22s -> ~4.5 reads/sec sustained, process-wide (the lock serialises the pace).
_READ_PACE_LOCK = _threading.Lock()
_READ_PACE = {"last": 0.0, "min_interval": 0.22}


def _pace_sheet_read():
    import time as _t
    with _READ_PACE_LOCK:
        wait = _READ_PACE["min_interval"] - (_t.monotonic() - _READ_PACE["last"])
        if wait > 0:
            _t.sleep(wait)
        _READ_PACE["last"] = _t.monotonic()


def _sheet_read_retry(fn, *args, _tries=6, **kwargs):
    """gspread READ, PACED (~4.5/sec) to stay under Google's 300/min read quota, with long
    exponential backoff on a 429. Because the quota is PER-MINUTE, the backoff waits 30,45,60,60s
    (not 2-8s) so the minute-window actually resets before retrying. Mirrors
    amazon_listing_generator._read_retry (the CLI backs off even harder, deferring to the web app)."""
    # Throttle DETECTION is shared (listing/repo.is_throttled) -- it was written
    # out identically here and in the generator. The BACKOFF POLICY stays here,
    # because the two are deliberately different: this is the web app and waits
    # 30/45/60s, while the CLI waits far longer to yield the shared per-minute
    # quota to this process.
    from listing import repo as _repo
    return _repo.read_retry(fn, *args, tries=_tries,
                            pace=_pace_sheet_read,
                            backoff=lambda i: min(60, 30 + 15 * i),
                            **kwargs)


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
    vals = _sheet_read_retry(ws.get_all_values)
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


def _apply_edits_batch(sku, edits):
    """Apply MANY attribute edits to one SKU in a SINGLE write (auto-fix helper).

    The old auto-fix path called /edit once PER field, and each /edit did
    row_values(1) + a full col_values scan + a cell read + a write + a cache-bust.
    Seven fields => ~15-20 reads + 7 writes per round, which drove Google's
    per-minute read/write quota to HTTP 429 on multi-SKU runs. This reads the row
    from the short cache (already populated by the round's /suggest, so ~0 extra
    reads), merges every edit into the Attributes JSON in memory, and writes it
    ONCE (retry-wrapped). Returns (applied, skipped). Faithfully mirrors /edit's
    attr prefix-cleanup so nested dot-keys behave identically."""
    applied, skipped = [], []
    ws   = _ws()
    recs = _records(ws)                       # cache hit from /suggest -> ~0 reads
    row  = next((r for r in recs if str(r.get("SKU", "")).strip() == sku), None)
    if not row:
        return applied, [{"field": e.get("key"), "reason": "sku not in current view"} for e in edits]
    trow = row.get("_row")
    try:
        obj = json.loads(row.get("Attributes JSON") or "{}")
        if not isinstance(obj, dict):
            obj = {}
    except Exception:
        obj = {}
    for e in edits:
        key   = str(e.get("key", "")).strip()
        value = e.get("value", "")
        if not key or str(value).strip() == "":
            skipped.append({"field": key, "reason": "empty value"})
            continue
        if "." in key:                        # deeper dot-key: drop shallower scalar prefixes
            parts = key.split(".")
            for i in range(1, len(parts)):
                prefix = ".".join(parts[:i])
                if prefix in obj and not isinstance(obj[prefix], dict):
                    obj.pop(prefix, None)
        else:                                 # scalar write: drop dot-keys underneath us
            _pfx = key + "."
            for _stale in [k for k in list(obj.keys()) if k.startswith(_pfx)]:
                obj.pop(_stale, None)
        obj[key] = value
        applied.append({"field": key, "value": value})
    if not applied:
        return applied, skipped
    hdr = _sheet_read_retry(ws.row_values, 1)
    if "Attributes JSON" not in hdr:
        return [], [{"field": e.get("key"), "reason": "no attributes column"} for e in edits]
    acol = hdr.index("Attributes JSON") + 1
    _sheet_read_retry(ws.update_cell, trow, acol, json.dumps(obj, ensure_ascii=False))
    _bust_records_cache()
    return applied, skipped










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
           # WAS THE BRIEF REWORDED TO GET PAST THE SAFETY FILTER?
           #
           # Some product words (slasher, blade, weapon-ish nouns) trip the image
           # provider's filter -- a real weed slasher came back as "the input text
           # may contain sensitive information". run_pipeline now rewords once and
           # retries instead of failing, which is right, but the picture is then
           # made from words the user did not write. Carry the flag through so the
           # screen can say so; detailed_prompt above is the wording actually used.
           "softened_prompt": bool(res.get("softened_prompt")),
           "text_provider": res.get("text_provider"),
           "image_provider": res.get("image_provider")}
    if extra:
        out.update(extra)
    return jsonify(out)




# ---- secondary image roles: each role has ONE job (clean, premium) ----
#
# HOW MUCH OF THE PRODUCT EACH ROLE NEEDS. Every role used to be generated the
# same way -- the whole product, on a background, with a headline beside it --
# so a set of eight came out as eight photographs of the same bottle:
#
#     "i see the item image in all the seconary images"
#
# Look at what actually sells on Amazon and several of the strongest secondary
# images contain NO product at all: a wall of journal pages under "3,319
# peer-reviewed studies", a specification panel with the numbers called out
# around it. The product is already in the main image and in half the others;
# repeating it is a wasted slot.
#
# So each role declares what it needs, and `present` is the honest answer:
#
#   "hero"    the whole product, as the subject
#   "detail"  a tight crop -- the stitching, the thread, the capsule surface
#   "in_use"  in a hand, on a bench, being used; the product is context
#   "none"    no product at all; the evidence, the chart, the box contents
#
# `none` is the one that could not be expressed before, and it is why the sets
# looked repetitive.
_SECONDARY_ROLES = {
    "benefit": {
        "present": "hero",
        "brief": ("A single-benefit image: ONE clear benefit, a short bold headline of a few "
                  "words, and a visual that PROVES it rather than decorating it. Generous "
                  "negative space, premium and minimal -- never a wall of text."),
    },
    "feature": {
        "present": "detail",
        "brief": ("A feature callout: ONE part or function, shown CLOSE UP -- the mechanism, "
                  "the texture, the fitting, the seal. Thin clean leader lines to at most "
                  "three labels. The whole product does not need to be in frame; the point is "
                  "the part."),
    },
    "lifestyle": {
        "present": "in_use",
        "brief": ("A real moment of use, in the place and by the kind of person this product "
                  "is actually for. Natural light, believable setting, nothing staged-looking. "
                  "Minimal text or none -- the scene carries it."),
    },
    "dimensions": {
        "present": "hero",
        "brief": ("Size, made obvious. Clean dimension lines with real measurements, and where "
                  "it helps, the product beside an everyday object of known size so the scale "
                  "is felt rather than read. Plain background, few words."),
    },
    "trust": {
        "present": "none",
        "brief": ("The reason to believe, as icons and short lines on a clean panel -- the "
                  "material, the standard it is made to, the guarantee, what it is tested "
                  "for. The product need not appear at all; this slot is about credibility. "
                  "Only ever claims the listing actually supports."),
    },
    "comparison": {
        "present": "none",
        "brief": ("A clean comparison that contrasts the outcome this product gives against "
                  "the ordinary alternative -- a tidy two-column table or a before/after. "
                  "Never a named competitor, never a disparaging claim."),
    },
    # These two were offered on screen and did not exist here, so choosing
    # either silently produced a benefit infographic instead.
    "detail": {
        "present": "detail",
        "brief": ("A macro study of the material and the making: the weave, the grain, the "
                  "weld, the finish, the powder, the capsule. Frame-filling, beautifully lit, "
                  "no more than a few words. This is the image that answers 'is it cheap "
                  "tat'."),
    },
    "usecase": {
        "present": "in_use",
        "brief": ("One specific situation this product is bought FOR, shown as a scene a buyer "
                  "recognises as their own problem. Not a generic lifestyle shot -- a "
                  "particular moment, with the product doing its job in it."),
    },
    # New. Each of these is a slot the old set could not fill, and each is a
    # kind of image that routinely outperforms another photograph of the box.
    "contents": {
        "present": "hero",
        "brief": ("Everything that comes in the box, laid out flat and evenly lit, each item "
                  "labelled with what it is and how many. Exactly what is supplied -- no "
                  "extra piece, no spare, nothing borrowed from the reference photo."),
    },
    "howto": {
        "present": "in_use",
        "brief": ("How it is used, in three or four numbered steps across one image. Each step "
                  "a small clear picture with a few words under it. This is the image that "
                  "answers 'will I be able to work it'."),
    },
    "spec": {
        "present": "none",
        "brief": ("The specification, as a designed panel rather than a photograph: the table, "
                  "chart or facts panel this product's buyer wants to read, with the handful "
                  "of numbers that matter called out around it. Every figure taken from the "
                  "listing, none invented."),
    },
    "evidence": {
        "present": "none",
        "brief": ("The proof behind the claim, shown as a designed image -- the testing, the "
                  "standard, the certification, the record of use. No product needed. ONLY "
                  "ever what the listing genuinely supports; if there is no real evidence to "
                  "show, this concept must not be used at all."),
    },
}

# How much product each role needs, on its own, for the generator to read.
SECONDARY_PRESENCE = {k: v["present"] for k, v in _SECONDARY_ROLES.items()}




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
         "desc": "Full-width immersive banner (Apple-style). Premium A+ only.",
         "mobile": {"w": 600, "h": 450}},
        {"id": "premium_header", "name": "Premium image header", "w": 1464, "h": 600,
         "desc": "Premium wide header with short headline; lots of visual impact.",
         "mobile": {"w": 600, "h": 450}},
        {"id": "premium_three", "name": "Premium three-image & text", "w": 488, "h": 600,
         "desc": "Three wide images with captions across the full premium canvas."},
    ],
}

# A PHONE IS NOT A NARROW DESKTOP.
#
#     "in premium aplus content there is mobile version and desktop version but
#      app is not making separate diensions content"
#
# One image was produced per module and used everywhere. A headline sized to
# read across a 1464px banner is a few pixels tall on a phone, and a layout that
# works wide has nowhere to go when the column is 400px -- which is where most
# of this is actually read.
#
# So a module that declares `mobile` can be generated twice: the desktop asset
# at its documented size, and a SEPARATELY COMPOSED mobile one -- same message,
# far larger type, fewer words, stacked rather than side by side.
#
# ABOUT THE MOBILE PIXEL SIZE. 1464x600 for the premium desktop banner is
# Amazon's published figure. The mobile one here is the size commonly used for
# it and is NOT quoted from an Amazon schema this app can read -- A+ is
# read-only over SP-API here, so there is nothing to check it against
# (CLAUDE.md Rule 4). It is a starting point, it is labelled as one on screen,
# and it is one number in one place if Seller Central says otherwise. What is
# NOT a guess is the part that matters: the mobile asset is composed for a
# phone rather than being the desktop one squeezed.
APLUS_MOBILE_IS_ASSUMED = (
    "The mobile pixel size is this app's default, not a figure read from "
    "Amazon. Confirm it against your own module in Seller Central; the "
    "composition is built for a phone either way."
)




def _write_attrs_for_sku(ws, sku, attrs):
    """Overwrite the Attributes JSON cell for a given SKU with the provided dict."""
    from listing import repo as _repo          # the ONE SKU->row lookup (Rule 12)
    found = _repo.locate(ws, sku, sku_headers=(SKU_HEADER,))
    if "Attributes JSON" not in found.headers:
        raise RuntimeError("no attributes column")
    if not found.ok:
        raise RuntimeError(found.error or "sku not found")
    _repo.set_field(ws, found.row, "Attributes JSON",
                    json.dumps(attrs, ensure_ascii=False), headers=found.headers)
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








def build_app(backend=None):
    """Wire every route onto the app and return it.

    WHY THIS IS A FUNCTION AND NOT AN `if __name__` BLOCK
    All of this registration used to sit inside `if __name__ == "__main__":`,
    which meant importing dashboard.py gave you an app with no routes on it. The
    SQLite beta needs the same wiring against a different data source, and the
    only way to reuse it was to copy the whole file -- roughly 2,700 lines that
    would drift apart from the first fix onward.

    Moving it into a function is a MOVE, not a rewrite: the body below is
    unchanged, only its wrapper. `dashboard_beta.py` now calls
    build_app(backend="db") instead of duplicating any of it, so a fix made here
    applies to both.

    backend="sheets" -> Google Sheets, exactly as before (still the default; the
                        live app's behaviour is untouched)
    backend="db"     -> SQLite, by swapping the two functions every route module
                        is already given by injection
    backend=None     -> ask data/choice.py, the ONE place that decides.

    Passing None rather than "sheets" is the fix for a genuine split brain: this
    argument used to be the dashboard's only input, and docker-entrypoint.sh runs
    `python dashboard.py`, so the deployed app was ALWAYS on sheets no matter
    what ALTA_DATA_BACKEND said -- while the generator subprocess read that
    variable and obeyed it. The two halves of the app could therefore be reading
    and writing different stores at the same time.
    """
    global _ws, _records
    from data import choice as _choice
    _decision = _choice.decide(_cfg() if callable(_cfg) else None, CONFIG_PATH)
    if backend is None:
        backend = _decision["backend"]
    else:
        # An explicit argument still wins (dashboard_beta.py passes "db"), but
        # record what was asked for so the report below is about THIS app.
        _decision = dict(_decision, backend=backend, source="how the app was started")

    # Every reporter reads this instead of re-reading the environment, so /diag
    # and /users/me describe the app that is actually running.
    app.config["DATA_BACKEND"] = backend
    app.config["DATA_BACKEND_DECISION"] = _decision

    if backend == "db":
        from data import backend as _data_backend
        _ws, _records = _data_backend.make(_state, config_path=CONFIG_PATH)

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
                          _estimate_profit=_estimate_profit,
                          # For the cost template: which account's SKUs to list,
                          # and where the catalogue snapshot lives.
                          CONFIG_PATH=CONFIG_PATH,
                          _active_account=_active_account)
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
    # Same media folder, opposite question: media_routes shows the ACTIVE
    # workspace's images, this one shows every image on the disk regardless of
    # workspace -- which is the only way to tell "filed somewhere else" apart
    # from "gone".
    # The costs that are not the supplier's price: postage out, prep, a hand-
    # allocated ad figure. Its own file from day one -- a new feature never goes
    # into dashboard.py (CLAUDE.md Rule 7).
    # Which way stock cost is worked out, and correcting one order by hand.
    import routes.cogs_mode_routes as _cogs_mode_routes
    import accounts as _acc_for_cogs
    _cogs_mode_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                               _state=_state, _active_account=_active_account,
                               _save_account=_acc_for_cogs.save_account,
                               _cogs_overrides=lambda: _COGS_OVERRIDE)
    import routes.asin_charges_routes as _asin_charges_routes
    _asin_charges_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                                  _state=_state, _active_account=_active_account)
    import routes.media_recover_routes as _media_recover_routes
    _media_recover_routes.register(app, _media_root=_media_root, _cfg=_cfg,
                                   CONFIG_PATH=CONFIG_PATH)
    import routes.inventory_routes as _inventory_routes
    _inventory_routes.register(app, _INV=_INV, _INV_IMPORT_ERR=_INV_IMPORT_ERR,
                               _INV2=_INV2, _INV2_IMPORT_ERR=_INV2_IMPORT_ERR,
                               _parse_3pl_csv=_parse_3pl_csv, _parse_sales_csv=_parse_sales_csv,
                               _parse_uplift_csv=_parse_uplift_csv,
                               _fetch_fba_inventory_via_spapi=_fetch_fba_inventory_via_spapi,
                               _num=_num, _INV_OUT_DIR=_INV_OUT_DIR, _inv2_cache=_inv2_cache,
                               _INV_ALERT_COUNTS=_INV_ALERT_COUNTS, _cfg=_cfg,
                               # The stock cockpit needs to know which account is
                               # open and where the database is; the FBA
                               # replenishment routes above never did.
                               CONFIG_PATH=CONFIG_PATH, _state=_state,
                               _active_account=_active_account)
    import routes.optimize_routes as _optimize_routes
    _optimize_routes.register(app, _state=_state, _cfg=_cfg, CONFIG_PATH=CONFIG_PATH,
                              _build_patches=_build_patches, _require_publish=_require_publish)
    import routes.ppc_routes as _ppc_routes
    _ppc_routes.register(app, _PPC=_PPC, _PPC_IMPORT_ERR=_PPC_IMPORT_ERR,
                         _PPC_OUT_DIR=_PPC_OUT_DIR,
                         _parse_pct_from_context=_parse_pct_from_context,
                         _cfg=_cfg, CHAT_MODEL=CHAT_MODEL,
                         # The analytics screen needs the database and which
                         # account is open; the campaign builder never did.
                         CONFIG_PATH=CONFIG_PATH, _state=_state,
                         _active_account=_active_account)
    import routes.accounts_routes as _accounts_routes
    _accounts_routes.register(app, _state=_state, _cfg=_cfg, CONFIG_PATH=CONFIG_PATH,
                              _LIVE_CACHE=_LIVE_CACHE,
                              live_catalog=(lambda: app.view_functions["live_catalog"]()),
                              OUTPUT_TAB=OUTPUT_TAB, ConfigError=ConfigError, _client=_client,
                              _save_active_state=_save_active_state)
    # Sales dashboard: one SP-API report (sales AND traffic), stored per day.
    import routes.sales_routes as _sales_routes
    _sales_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                           _active_account=_active_account, _state=_state)

    # Import an eBay seller's catalogue as DRAFTS. Nothing here reaches Amazon:
    # it finds, screens and writes rows into this app's own store, and the
    # existing approve-and-submit path publishes them.
    import routes.seller_routes as _seller_routes
    _seller_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                            _active_account=_active_account, _state=_state)

    # Variation families. Preview decides and explains; apply sends exactly what
    # preview showed. _schema_for gives it the live product-type schema, which is
    # where the allowed variation themes come from (Rule 4).
    import routes.variations_routes as _variations_routes
    _variations_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                                _active_account=_active_account, _state=_state,
                                _sp_creds=_sp_creds,
                                _schema_for=_variation_schema,
                                # So the image slot picker can hand Amazon a
                                # public URL for an image in this app's own
                                # media library, instead of refusing it and
                                # sending people to Google Drive.
                                _public_media_url=_public_media_url)

    # Finance: contribution per product. Read-only, and built from finance rows
    # already stored per ASIN -- it pulls nothing new from Amazon.
    import routes.finance_routes as _finance_routes
    _finance_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                             _active_account=_active_account, _state=_state)

    # Changing a live selling price by hand. Composes the patch with the SAME
    # builder the repricer uses, which edits the offer Amazon returned rather
    # than inventing a purchasable_offer shape (Rule 4 and Rule 12).
    import routes.price_routes as _price_routes
    _price_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                           _active_account=_active_account, _state=_state)

    # Adding a colour or size to something already listed. Queues the new
    # product; the family itself is built on the Variations screen once it is
    # live, because Amazon can only build one over listings that exist.
    import routes.variant_routes as _variant_routes
    _variant_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                             _active_account=_active_account, _state=_state)

    # Orders from every account on one screen, so seeing what sold does not mean
    # opening each Amazon account in turn. Read-only.
    import routes.orders_routes as _orders_routes
    _orders_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                            _active_account=_active_account, _state=_state)

    # Why things come back, and what it costs. Pulls the returns report, or
    # reads one you upload -- an FBA file carries two columns the API will not
    # give a seller-fulfilled account.
    import routes.returns_routes as _returns_routes
    _returns_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                             _active_account=_active_account, _state=_state)
    # The weekly KPI pack. Two reports in -- uploaded, or read from what the app
    # already syncs -- and one frozen week out. See routes/weekly_routes.py.
    import routes.weekly_routes as _weekly_routes
    _weekly_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                            _active_account=_active_account, _state=_state)
    # The daily round -- the checklist somebody works through every morning,
    # run by the app. See routes/daily_routes.py.
    import routes.daily_routes as _daily_routes
    _daily_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                           _active_account=_active_account, _state=_state)
    # The four trackers -- BSR, Buy Box, price and fee -- and the single alert
    # count they feed. Orbit lists them as five menu items plus Alerts; they are
    # one engine pointed at different numbers, so they are one set of routes.
    # See domain/trackers.py for why the metrics are data rather than code.
    import routes.tracker_routes as _tracker_routes
    _tracker_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                             _active_account=_active_account, _state=_state)

    # Sessions, page views, conversion and buy box -- Orbit's Traffic &
    # Conversions screen, built on figures this app has been storing per ASIN and
    # per day all along without ever showing them.
    import routes.traffic_routes as _traffic_routes
    _traffic_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                             _active_account=_active_account, _state=_state)

    # Which hour of which day each product sells in. Amazon publishes no hourly
    # report, so this is built from order TIMES -- one Amazon call per order,
    # which is why every order it learns about is kept.
    import routes.hourly_routes as _hourly_routes
    _hourly_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                            _active_account=_active_account, _state=_state)

    # Moving a workspace's listings out of Google Sheets and into the app. The
    # import has always existed as a command line; it has to be runnable HERE,
    # because it must run where the database is and that is not a laptop.
    import routes.migrate_routes as _migrate_routes
    _migrate_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                             _client=_client, _state=_state)

    # What protects the data once the database is the only store. Sheets stops
    # being the store and becomes the backup -- written to, never read back.
    import routes.backup_routes as _backup_routes
    _backup_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                            _client=_client, _state=_state)

    # What the AI cost, per account and per feature. Reads the ledger written by
    # domain/ai_usage.py; spends nothing itself.
    import routes.aiusage_routes as _aiusage_routes
    _aiusage_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                             _active_account=_active_account, _state=_state)

    # The source repricer. Dry run only: it decides and records, and nothing
    # here writes to Amazon. Only SKUs enrolled on that screen are ever read.
    import routes.sourcing_routes as _sourcing_routes
    _sourcing_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                              _active_account=_active_account, _state=_state,
                              # The SAME dict the listings screen edits, so the
                              # repricer shows the cost a person typed rather
                              # than re-deriving one from the SKU (Rule 12).
                              _COGS_OVERRIDE=_COGS_OVERRIDE)

    # The generator's INPUT, imported on demand instead of read live from Google.
    import routes.input_routes as _input_routes
    _input_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                           _active_account=_active_account, _state=_state,
                           _client=_client)

    import routes.misc_routes as _misc_routes
    _misc_routes.register(app, CONFIG_PATH=CONFIG_PATH, _active_account=_active_account,
                          _state=_state)
    import routes.autofix_log_routes as _autofix_log_routes
    _autofix_log_routes.register(app, CONFIG_PATH=CONFIG_PATH)
    import routes.autofix_job_routes as _autofix_job_routes
    _autofix_job_routes.register(app, _af_new=_af_new, _af_get=_af_get, _af_active=_af_active,
                                 _af_stop=_af_stop, _run_autofix_bg=_run_autofix_bg,
                                 _state=_state, _threading=threading,
                                 CONFIG_PATH=CONFIG_PATH)
    import routes.sync_routes as _sync_routes
    _sync_routes.register(app, _cfg=_cfg, _active_account=_active_account,
                          _records=_records, _ws=_ws, _bust_records_cache=_bust_records_cache)
    # Bulk handling-time updates (sheet + live Amazon push).
    import routes.handling_routes as _handling_routes
    _handling_routes.register(app, _cfg=_cfg, _active_account=_active_account,
                              _ws=_ws, _bust_records_cache=_bust_records_cache, _state=_state)
    # ASIN Monitor — competitor/hijacker tracking + hourly checker (read-only, in-app alerts).
    import routes.monitor_routes as _monitor_routes
    _monitor_routes.register(app, CONFIG_PATH=CONFIG_PATH, _cfg=_cfg,
                             _reload_cfg=lambda: _state.update(cfg=None))   # drop config cache so edits take effect
    try:
        from monitor import checker as _mon_checker
        # WHEN THIS RUNS IS NOW A SETTING, not a constant.
        #
        #     "i dont want the asin monitor to be working always, give 2 options.
        #      option 1 is to recheck the status of the buybox by clicking a
        #      button. option two is to setup a time of your choice."
        #
        # monitor/schedule.py holds the choice and the loop re-reads it every
        # minute, so no interval is passed here. Off by default: this was the
        # app's largest consumer of the Amazon quota and it ran whether or not
        # anybody was looking at it. "Check now" works regardless.
        #
        # MONITOR_INTERVAL_S still forces one, for a machine that needs the old
        # behaviour without anyone opening the screen.
        _mon_checker.start_scheduler(
            _cfg, CONFIG_PATH,
            interval=int(os.environ.get("MONITOR_INTERVAL_S") or 0))
    except Exception as _mon_e:
        print("[asin-monitor] scheduler not started:", str(_mon_e)[:200])
    # Opt-in UI redesign (Stage 1) -- additive read-only endpoints for the new dashboard.
    import routes.dashboard_routes as _dashboard_routes
    _dashboard_routes.register(app, _cfg=_cfg, _client=_client, _state=_state,
                               STATUS_HEADER=STATUS_HEADER, SKU_HEADER=SKU_HEADER,
                               _INV_ALERT_COUNTS=_INV_ALERT_COUNTS)
    # ASIN research (read-only Catalog Items lookup; no publish)
    import routes.catalog_routes as _catalog_routes
    _catalog_routes.register(app, _cfg=_cfg, _state=_state, CONFIG_PATH=CONFIG_PATH)
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
                              _write_attrs_for_sku=_write_attrs_for_sku, _ws=_ws,
                              # So a strategist-made A+ image can be generated at
                              # its OWN module's size rather than one flat size
                              # per tier.
                              _APLUS_MODULES=_APLUS_MODULES)
    import routes.listing_routes as _listing_routes
    _listing_routes.register(app, CHAT_MODEL=CHAT_MODEL, CONFIG_PATH=CONFIG_PATH, SCRIPT=SCRIPT,
                             SKU_HEADER=SKU_HEADER, STATUS_HEADER=STATUS_HEADER, _ANSI=_ANSI,
                             _EDITABLE_COLS=_EDITABLE_COLS, _URL_RE=_URL_RE,
                             _VALID_SET_STATUS=_VALID_SET_STATUS, _acquire_run_lock=_acquire_run_lock,
                             _active_account=_active_account, _build_patches=_build_patches,
                             _require_publish=_require_publish,
                             _bust_records_cache=_bust_records_cache, _card=_card, _cfg=_cfg,
                             _client=_client, _drive_folder_id_from_url=_drive_folder_id_from_url,
                             _drive_map_get=_drive_map_get, _drive_map_put=_drive_map_put,
                             _drive_upload_image=_drive_upload_image, _ebay_creds=_ebay_creds,
                             _public_media_url=_public_media_url,
                             _fetch_image_b64=_fetch_image_b64, _load_schema=_load_schema,
                             _marketplace_for_row=_marketplace_for_row, _media_root=_media_root,
                             _options_for=_options_for, _parse_required_missing=_parse_required_missing,
                             _product_types=_product_types, _records=_records,
                             _resolve_fields=_resolve_fields, _run_lock=_run_lock, _running=_running,
                             _schema_attrs=_schema_attrs, _schema_required=_schema_required,
                             _schema_subfields=_schema_subfields, _sp_creds=_sp_creds, _state=_state,
                             _ws=_ws)
    # Preview/Submit as background JOBS (queue + visibility that survives navigation +
    # reload). Shares the SAME global run lock so jobs never run concurrently with an SSE
    # run / generate / auto-fix. The live /run/<mode> SSE endpoint is left untouched.
    from listing import preview_jobs as _preview_jobs
    _preview_jobs.configure(acquire_lock=_acquire_run_lock, run_lock=_run_lock,
                            running=_running, ansi_re=_ANSI)
    import routes.preview_job_routes as _preview_job_routes
    _preview_job_routes.register(app, CONFIG_PATH=CONFIG_PATH, SCRIPT=SCRIPT, _cfg=_cfg,
                                 _active_account=_active_account, _state=_state,
                                 _require_publish=_require_publish)
    import routes.ui_routes as _ui_routes
    _ui_routes.register(app, CONFIG_PATH=CONFIG_PATH, _kill_proc=_kill_proc,
                        _records=_records, _run_lock=_run_lock, _running=_running,
                        _ws=_ws, _state=_state)
    import routes.live_routes as _live_routes
    _live_routes.register(app, CONFIG_PATH=CONFIG_PATH, _IMG_CACHE=_IMG_CACHE, _IMG_TTL=_IMG_TTL,
                          _LIVE_CACHE=_LIVE_CACHE, _LIVE_TTL=_LIVE_TTL, _cfg=_cfg,
                          _estimate_profit=_estimate_profit,
                          _parse_listings_report=_parse_listings_report,
                          _resolve_cogs=_resolve_cogs, _state=_state,
                          _APLUS_CACHE=_APLUS_CACHE, _APLUS_TTL=_APLUS_TTL)
    import routes.dash_auth_routes as _dash_auth_routes
    _dash_auth_routes.register(app, _APP_PASSWORD=_APP_PASSWORD, CONFIG_PATH=CONFIG_PATH)
    import routes.users_routes as _users_routes
    _users_routes.register(app, CONFIG_PATH=CONFIG_PATH)

    # Keep EVERY connected account+marketplace's live catalogue fresh, server-side.
    # The browser timer could only refresh the one workspace that happened to be
    # open, and only while a tab was open, so every other account stayed stale and
    # the first visit paid the full report-build wait. This walks them all, one at
    # a time and spread out so Amazon is not asked for everything at once.
    import domain.live_refresher as _refresher

    @app.route("/diag")
    def _deploy_diag():
        """Is THIS deployment configured correctly?

        On a server there is no terminal, and a misconfigured deployment looks
        exactly like an application bug -- listings vanish, users get signed out.
        This says which it is, from inside the running app.
        """
        import domain.deploy_check as _dc
        import domain.selfcheck as _sc
        res = _dc.check(CONFIG_PATH, in_use=app.config.get("DATA_BACKEND"))
        res["refresher"] = _refresher.status()
        # Marketplaces the background job has stopped asking about. A pair that
        # is quietly not being refreshed is exactly the thing nobody notices
        # until they ask why a country has no data, so it is reported rather
        # than only logged.
        try:
            import domain.marketplace_health as _mh
            res["marketplaces_rested"] = _mh.status(CONFIG_PATH)
        except Exception:
            res["marketplaces_rested"] = []
        # The configuration and the actual faults belong on ONE page. Split
        # across two, the obvious question -- "is this error caused by that
        # misconfiguration?" -- needs two tabs and a guess.
        res["recent"] = _sc.recent(25)
        res["text"] = _sc.as_text(res)      # the copy-to-clipboard block
        return jsonify({"ok": True, **res})

    @app.route("/live/refresher")
    def _live_refresher_status():
        """What the background refresher is doing, and when each account last ran.
        Reads real state -- a refresher that cannot be inspected is one you have
        to take on faith."""
        return jsonify({"ok": True, **_refresher.status()})

    # CACHE-BUSTING FOR THE BROWSER.
    # Every page loaded 22 scripts and stylesheets as bare /static/... URLs. A
    # browser that has one cached has no reason to ask for it again, so a deploy
    # could fix a screen on the server while the person looking at it kept
    # running yesterday's JavaScript -- the fix is live and invisible, which is
    # the most confusing possible outcome and impossible to tell apart from "the
    # fix did not work".
    #
    # The stamp is the newest modification time under static/, so it changes
    # exactly when an asset changes and not on every restart (which would throw
    # away everyone's cache for nothing).
    def _asset_version():
        newest = 0.0
        for root, _dirs, files in os.walk(os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "static")):
            for fn in files:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, fn)))
                except OSError:
                    pass
        return str(int(newest)) or "0"

    app.config["ASSET_V"] = _asset_version()

    # ON A SERVER the stamp is computed once and left alone: a deploy restarts
    # the app, so the value is always current and walking static/ on every page
    # load would be waste.
    #
    # RUNNING LOCALLY there is no restart. The stamp stayed at whatever it was
    # when the app booted, so the browser kept being handed the SAME
    # dashboard.css?v=... it already had cached, and edits to CSS or JS were
    # invisible until the app was restarted -- which looks exactly like "the
    # change didn't work". Re-checked at most once every few seconds, which is
    # cheap and only happens off-server.
    _paas = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER")
                 or os.environ.get("DYNO"))
    _av = {"ts": 0.0}

    # AND THE TEMPLATE ITSELF.
    # Flask compiles templates/dashboard.html once and keeps it in memory unless
    # told otherwise. Without debug mode that means a locally running app serves
    # the HTML it read at startup FOR EVER -- so an edit to the page could not
    # appear no matter how many times the browser was refreshed, and the only
    # symptom was "nothing changed". Stamping the assets did not help, because
    # the stamp is written INTO the cached template.
    #
    # On a server this is right and stays off: a deploy restarts the app, and
    # re-reading the file per request would be pure cost. Off-server, correctness
    # while editing beats a saving nobody can measure on one machine.
    if not _paas:
        app.config["TEMPLATES_AUTO_RELOAD"] = True
        app.jinja_env.auto_reload = True

    @app.context_processor
    def _inject_asset_version():
        if not _paas:
            import time as _t
            if _t.time() - _av["ts"] > 2:
                app.config["ASSET_V"] = _asset_version()
                _av["ts"] = _t.time()
        return {"ASSET_V": app.config.get("ASSET_V", "0")}

    # Say at BOOT whether this deployment is configured correctly. A wiped disk
    # or a missing APP_SECRET_KEY otherwise announces itself hours later as
    # missing data, which reads as an application bug. The server log is the one
    # place a deployment always has, so the verdict goes there, every start.
    try:
        import domain.deploy_check as _dc0
        import domain.selfcheck as _sc0
        print(_sc0.boot_banner(_dc0.check(CONFIG_PATH,
                                          in_use=app.config.get("DATA_BACKEND"))),
              flush=True)
    except Exception as _e0:
        print(f"  (deployment check could not run: {_e0})", flush=True)

    # ---- AI spend: record every call, and know whose it was --------------
    # Installed here, once, rather than at each of the fourteen places that call
    # a model. See domain/ai_usage.install_anthropic_recorder for why it is done
    # by interception: a per-site wrapper is a per-site chance to forget one, and
    # a spend report that quietly omits a feature is worse than none.
    try:
        from domain import ai_usage as _aiu
        _aiu.install_anthropic_recorder(CONFIG_PATH)

        @app.before_request
        def _stamp_ai_account():
            # Which account is spending, AND WHICH PRODUCT. Set per request from
            # the same resolver every screen uses, so attribution cannot drift
            # from what the header says. The feature name is added by each AI
            # step itself.
            #
            # THE SKU WAS ALWAYS BLANK. It was set to "" here and nothing ever
            # filled it, so all 46 rows in the ledger named an account and a
            # feature and no product -- and "which item did that spend go on"
            # could not be answered at all. Read here, once, rather than in each
            # of the fourteen routes that generate something: a per-route line is
            # a per-route chance to forget one, which is the same reasoning the
            # recorder itself is installed by interception for.
            sku = ""
            try:
                from flask import request as _rq
                sku = str((_rq.args.get("sku") or "")).strip()
                if not sku and _rq.method == "POST":
                    b = _rq.get_json(silent=True) or {}
                    if isinstance(b, dict):
                        sku = str(b.get("sku") or "").strip()
            except Exception:
                sku = ""
            try:
                from routes import scope as _scope
                _aiu.set_context(
                    workspace_id=_scope.workspace_id(
                        state=_state, account=_active_account() or {}),
                    config_path=CONFIG_PATH, feature="", sku=sku)
            except Exception:
                _aiu.set_context(config_path=CONFIG_PATH, sku=sku)
    except Exception as _e1:
        print(f"  (AI usage recording could not start: {_e1})", flush=True)

    _refresher.start(app, _cfg, CONFIG_PATH,
                     log=lambda m: print(f"[refresher] {m}"))

    # ---- the daily backup ------------------------------------------------
    # Armed here so it runs wherever the app runs, rather than depending on
    # somebody remembering. It writes each account's listings to its own
    # backup_ tab and never reads one back, so it cannot become a source.
    try:
        from domain import backup as _backup_mod

        def _backup_accounts():
            from domain import accounts as _acc
            return _acc.load_accounts(_cfg(), CONFIG_PATH) or []

        _backup_mod.NIGHTLY.start(_client, CONFIG_PATH, _backup_accounts,
                                  log=lambda m: print(f"[backup] {m}", flush=True))
    except Exception as _eb:
        print(f"  (the daily backup could not be armed: {_eb})", flush=True)

    return app


if __name__ == "__main__":
    try:
        with open(".app_port", "w") as _pf:
            _pf.write(str(PORT))
    except Exception:
        pass
    print(f"\n  Listing Review dashboard -> http://{HOST}:{PORT}")
    print("  (Ctrl+C to stop)\n")
    build_app()
    app.run(host=HOST, port=PORT, threaded=True)
