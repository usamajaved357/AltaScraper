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
def capability(account: dict) -> dict:
    """Per-account sync capability. PULL is only 'enabled' when a live read-test has
    CONFIRMED it (config alone is not trusted -- Sheelady looked pull-capable in config
    but was denied live). PUSH is enabled from can_publish but stays INFERRED (a write
    is never tested by writing)."""
    aid = account.get("id", "")
    own = _acc.has_own_creds(account)
    borrowed = _acc.is_borrowed(account)
    can_read_scope = _acc.seller_scope_allowed(account)   # config says seller-scope possible
    can_push_cfg = _acc.can_publish(account)
    cap = _load(_CAP_FILE).get(aid, {})
    pull_confirmed = bool(cap.get("pull_confirmed"))
    if borrowed:
        reason = "borrowed credentials -> catalogue-only (no seller read/write)"
    elif not own:
        reason = "not connected (no own SP-API app)"
    elif not can_read_scope:
        reason = "own creds but seller-scope not allowed"
    elif cap.get("tested_at"):
        reason = "own creds; pull CONFIRMED (live read-test)" if pull_confirmed else \
                 "own creds; pull DENIED (live read-test) -- no Listings read role"
    else:
        reason = "own creds; pull not yet read-tested"
    return {
        "account_id": aid,
        "pull_enabled": bool(can_read_scope and pull_confirmed),   # LIVE-confirmed only
        "pull_possible": bool(can_read_scope),                     # config thinks so (needs read-test)
        "pull_confirmed": pull_confirmed,
        "push_enabled": bool(can_push_cfg),                        # INFERRED until a real push
        "push_confirmed": bool(cap.get("push_confirmed")),
        "reason": reason,
    }


def set_pull_confirmed(account_id: str, confirmed: bool):
    cap = _load(_CAP_FILE)
    cap.setdefault(account_id, {})["pull_confirmed"] = bool(confirmed)
    cap[account_id]["tested_at"] = int(time.time())
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
