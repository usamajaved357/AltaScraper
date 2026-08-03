"""listing/sync.py -- two-way Amazon <-> app sync core (feature 2). SAFE BY DESIGN.

Pull = Amazon -> app; Push = app -> Amazon. These are OPPOSITE directions and are kept
strictly separate. NOTHING here writes blindly: pull/push functions PROPOSE (return both
versions) and only the *apply/confirm* functions write, one listing at a time. A row that
was regenerated but not yet pushed is protected from being overwritten by a pull.

Capability is gated per account: PULL is only offered where a live read-test confirmed it;
PUSH is only offered where the account can publish (still INFERRED until a real push).

Snapshot model (answers "what does status show before a first pull?"):
  * The per-row status is computed against a CACHED last-known-Amazon snapshot
    (sync_snapshots.json, in the data dir), which is populated ONLY by a pull.
  * Before any pull has ever run for a SKU there is NO snapshot, so status is
    "unknown-never-pulled" -- NEVER a false "synced". Honest unknown, not a guess.
"""
import os
import json
import time

import domain.accounts as _acc

# Data caches live beside config.json (the data dir), never with the code.
def _data_dir():
    import amazon_listing_generator as G
    return str(G.CONFIG_PATH.parent)

_SNAP_FILE = "sync_snapshots.json"       # {account_id: {sku: {"copy":{...}, "pulled_at":ts}}}
_CAP_FILE  = "sync_capability.json"      # {account_id: {"pull_confirmed":bool, "tested_at":ts}}

COPY_FIELDS = ["title", "item_highlights", "bullet_1", "bullet_2", "bullet_3",
               "bullet_4", "bullet_5", "description", "search_terms"]


# --- small json cache helpers ----------------------------------------------
def _load(fn):
    try:
        return json.load(open(os.path.join(_data_dir(), fn), encoding="utf-8"))
    except Exception:
        return {}

def _save(fn, obj):
    try:
        json.dump(obj, open(os.path.join(_data_dir(), fn), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# --- capability (config-derived + live-confirmed pull) ---------------------
# Read-test outcomes. A FAILURE is not automatically a permanent 'no access': a 403 can
# mean the account is DEACTIVATED (temporary -- access returns on reinstatement) OR that
# the credentials genuinely lack the role (a real gap). Amazon's generic 403 does not say
# which, so an ambiguous failure is 'blocked_unconfirmed', never a guessed cause.
CONFIRMED = "confirmed"
DEACTIVATED = "deactivated"
ROLE_GAP = "role_gap"
BLOCKED_UNCONFIRMED = "blocked_unconfirmed"
UNTESTED = "untested"


def classify_read_error(err_text: str) -> str:
    """Classify a read-test failure from Amazon's message. Only auto-labels a cause when
    the message clearly says so; otherwise 'blocked_unconfirmed' (never a guess)."""
    m = (err_text or "").lower()
    if any(k in m for k in ("suspend", "deactivat", "inactive", "not active", "account status")):
        return DEACTIVATED
    if any(k in m for k in ("not authorized to perform", "grantless", "developer", "application id",
                            "missing role", "unauthorized for operation")):
        return ROLE_GAP
    return BLOCKED_UNCONFIRMED           # e.g. generic "Access to requested resource is denied"


def capability(account: dict) -> dict:
    """Per-account sync capability. PULL is enabled ONLY on a live-CONFIRMED read-test. A
    failure is labelled BY CAUSE (deactivated=temporary vs role_gap=real vs unconfirmed),
    and is always RE-TESTABLE -- one re-test on reinstatement flips it back to confirmed
    with no code change. PUSH is enabled from can_publish but stays INFERRED. An operator
    override can name a cause the generic 403 cannot."""
    aid = account.get("id", "")
    own = _acc.has_own_creds(account)
    borrowed = _acc.is_borrowed(account)
    can_read_scope = _acc.seller_scope_allowed(account)
    can_push_cfg = _acc.can_publish(account)
    cap = _load(_CAP_FILE).get(aid, {})
    status = cap.get("status")
    manual = cap.get("manual", "")
    if borrowed:
        status_lbl, reason = "borrowed", "borrowed credentials -> catalogue-only (no seller read/write)"
    elif not own:
        status_lbl, reason = "not_connected", "not connected (no own SP-API app)"
    elif status == CONFIRMED:
        status_lbl, reason = CONFIRMED, "own creds; pull CONFIRMED (live read-test)"
    elif status == DEACTIVATED:
        status_lbl, reason = DEACTIVATED, ("access blocked -- account DEACTIVATED (temporary); "
                                           "access returns on reinstatement, then re-test")
    elif status == ROLE_GAP:
        status_lbl, reason = ROLE_GAP, "credentials lack the Listings read role -- a real gap (fix creds)"
    elif status == BLOCKED_UNCONFIRMED:
        status_lbl, reason = BLOCKED_UNCONFIRMED, ("access blocked -- reason UNCONFIRMED (generic 403); "
                                                   "re-test, or mark the cause (deactivated vs role gap)")
    else:
        status_lbl, reason = UNTESTED, "own creds; pull not yet read-tested"
    if manual:
        reason += " | operator note: " + manual
    pull_confirmed = (status == CONFIRMED)
    return {
        "account_id": aid,
        "status": status_lbl,
        "pull_enabled": bool(can_read_scope and pull_confirmed),
        "pull_possible": bool(can_read_scope),
        "pull_confirmed": pull_confirmed,
        "re_testable": bool(own and not borrowed),      # a failure is never a permanent verdict
        "push_enabled": bool(can_push_cfg),              # INFERRED until a real push
        "push_confirmed": bool(cap.get("push_confirmed")),
        "reason": reason,
        "tested_at": cap.get("tested_at"),
    }


def set_pull_result(account_id: str, status: str, detail: str = ""):
    """Record a read-test outcome. Re-running the read-test overwrites this -- never frozen.
    A fresh CONFIRMED clears any stale operator note (access is back)."""
    cap = _load(_CAP_FILE)
    e = cap.setdefault(account_id, {})
    e["status"] = status
    e["detail"] = detail
    e["tested_at"] = int(time.time())
    if status == CONFIRMED:
        e.pop("manual", None)
    _save(_CAP_FILE, cap)


def mark_status(account_id: str, status: str, note: str = ""):
    """OPERATOR override to name a cause the 403 cannot (e.g. 'deactivated'). Sets status +
    a note; does NOT touch the Amazon account. A later successful re-test clears it."""
    cap = _load(_CAP_FILE)
    e = cap.setdefault(account_id, {})
    e["status"] = status
    e["manual"] = note
    e.setdefault("tested_at", int(time.time()))
    _save(_CAP_FILE, cap)


# --- per-row status --------------------------------------------------------
UNKNOWN   = "unknown-never-pulled"
SYNCED    = "synced"
APP_AHEAD = "regenerated-not-on-amazon"
AMZ_AHEAD = "changed-on-amazon"

def _snapshot(account_id, sku):
    return _load(_SNAP_FILE).get(account_id, {}).get(sku)

def compute_status(account_id: str, sku: str, stored_copy: dict, regenerated_at) -> dict:
    """Honest per-row status. No snapshot yet -> UNKNOWN (never a false 'synced')."""
    snap = _snapshot(account_id, sku)
    if not snap:
        return {"status": UNKNOWN, "label": "Unknown -- never pulled",
                "detail": "no Amazon snapshot yet; run Pull to establish the true state"}
    amazon = snap.get("copy", {})
    pulled_at = snap.get("pulled_at", 0)
    # app has regenerated since the last pull -> app is ahead of Amazon
    if regenerated_at and regenerated_at > pulled_at:
        return {"status": APP_AHEAD, "label": "Regenerated -- not yet on Amazon",
                "detail": "app copy is newer than the last pull; push (with review) to publish"}
    # stored copy differs from the last known Amazon copy, with no app-side change
    if {k: stored_copy.get(k, "") for k in COPY_FIELDS} != {k: amazon.get(k, "") for k in COPY_FIELDS}:
        return {"status": AMZ_AHEAD, "label": "Changed on Amazon -- app behind",
                "detail": f"differs from last pull ({time.strftime('%Y-%m-%d %H:%M', time.localtime(pulled_at))}); pull to review"}
    return {"status": SYNCED, "label": "Synced",
            "detail": f"matches Amazon as of last pull ({time.strftime('%Y-%m-%d %H:%M', time.localtime(pulled_at))})"}


# --- pull (Amazon -> app): PROPOSE only, plus snapshot update --------------
def _amazon_copy_from_item(pay: dict) -> dict:
    """Extract the copy fields we track from a getListingsItem payload."""
    out = {k: "" for k in COPY_FIELDS}
    summ = (pay or {}).get("summaries") or []
    if summ:
        out["title"] = summ[0].get("itemName", "") or ""
    attrs = (pay or {}).get("attributes") or {}
    def _first(key):
        v = attrs.get(key)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v[0].get("value", "")
        return ""
    for i in range(1, 6):
        bp = attrs.get("bullet_point") or []
        if isinstance(bp, list) and len(bp) >= i and isinstance(bp[i-1], dict):
            out[f"bullet_{i}"] = bp[i-1].get("value", "")
    out["description"] = _first("product_description")
    return out


def pull_from_amazon(cfg: dict, account: dict, sku: str) -> dict:
    """LIVE READ. Fetch Amazon's current copy for one SKU, update the snapshot, and
    RETURN it for a side-by-side (does NOT write to the sheet). Caller applies chosen
    fields via the /apply endpoint. Returns {"ok","amazon_copy","error"}."""
    cap = capability(account)
    if not cap["pull_enabled"]:
        return {"ok": False, "error": "pull not enabled for this account: " + cap["reason"]}
    try:
        from sp_api.api import ListingsItemsV20210801 as LI
        from sp_api.base import Marketplaces
    except Exception as e:
        return {"ok": False, "error": f"sp_api unavailable: {e}"}
    mkt = (account.get("default_marketplace") or "UK").upper()
    mkt = "UK" if mkt == "GB" else mkt
    mid = _acc.marketplace_id(mkt)
    creds = _acc.account_creds(account)
    try:
        li = LI(credentials=creds, marketplace=getattr(Marketplaces, mkt, Marketplaces.UK), timeout=60)
        resp = li.get_listings_item(account.get("seller_id", ""), sku,
                                    marketplaceIds=[mid] if mid else None,
                                    includedData="summaries,attributes")
        pay = resp.payload if hasattr(resp, "payload") else (resp or {})
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}
    amazon = _amazon_copy_from_item(pay)
    snaps = _load(_SNAP_FILE)
    snaps.setdefault(account.get("id", ""), {})[sku] = {"copy": amazon, "pulled_at": int(time.time())}
    _save(_SNAP_FILE, snaps)
    return {"ok": True, "amazon_copy": amazon}


# --- push (app -> Amazon): PROPOSE + gated confirm -------------------------
def push_to_amazon(cfg: dict, account: dict, sku: str, fields: dict) -> dict:
    """LIVE WRITE (patchListingsItem). GATED: the caller must have shown the side-by-side
    and the operator confirmed. This is the first-push test surface -- run ONE listing,
    review, report, before any second push. Returns {"ok","error"}.

    NOTE: enforcement of the business rules (LISTING requirements, GTIN exemption, brand
    kept, never merchant_suggested_asin / LISTING_OFFER_ONLY) is the generator's submit
    path -- this function is intentionally a stub that REFUSES until wired to that path,
    so 'push is wired' can never silently become 'push wrote to a live listing'."""
    cap = capability(account)
    if not cap["push_enabled"]:
        return {"ok": False, "error": "push not enabled for this account: " + cap["reason"]}
    # SAFETY STOP: no live write is performed here yet. The first live push must be an
    # explicit, reviewed, one-listing test wired through the generator's compliant submit
    # path -- deliberately not auto-executed.
    return {"ok": False, "error": "push path wired but LIVE WRITE is intentionally halted "
                                  "pending the gated first-push test (one listing, reviewed)."}
