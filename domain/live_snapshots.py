"""domain/live_snapshots.py -- DURABLE storage for the live Amazon catalogue.

WHY THIS EXISTS
The live catalogue used to be held in exactly two volatile places: a module-level
dict in dashboard.py (`_LIVE_CACHE`, 30-minute TTL) and a JavaScript variable in
the browser (`LIVE_STORE`). A page reload emptied the browser copy; thirty
minutes, a container restart or a redeploy emptied the server copy. Nothing was
ever written to disk, so a Sync that fetched 64 listings could show 16 an hour
later with no error -- the app had simply forgotten, and then re-answered from a
stale Amazon report.

That hurts most on the live server. On Render the container restarts on every
deploy, on health-check failures and on instance recycling, and each restart
takes the whole cache with it.

WHERE IT WRITES
Beside config.json, i.e. the persistent disk on Render (CONFIG_PATH=/data/...),
matching what listing/sync.py already does for its own snapshots. Nothing is
written next to the code, so a redeploy never wipes it.

CONCURRENCY
dashboard.py serves with app.run(threaded=True): one process, many threads. So
in-process state is guarded by a lock, and every file write goes to a temporary
file in the same directory and is then os.replace()d over the target -- atomic on
both Windows and Linux, so a crash or a concurrent read can never observe a
half-written file.

This module stores and returns data. It makes no Amazon calls and holds no
opinion about freshness -- the caller decides what is too old, and every record
carries the timestamp needed to decide.
"""
import threading
import time

from domain import jsonstore

_FILE = "live_snapshots.json"
_LOCK = threading.RLock()
_MEM = {"path": None, "data": None}      # process-local mirror of the file


def _path(config_path):
    return jsonstore.path_beside_config(config_path, _FILE)


def _read_all(config_path):
    """Whole store, read through the process-local mirror."""
    p = _path(config_path)
    with _LOCK:
        if _MEM["path"] == p and isinstance(_MEM["data"], dict):
            return _MEM["data"]
        loaded = jsonstore.read_json(p, default=None)
        # A missing or corrupt file is simply "no snapshots yet".
        data = loaded if isinstance(loaded, dict) else {}
        _MEM["path"], _MEM["data"] = p, data
        return data


def _write_all(config_path, data):
    """Atomic whole-store write. Persistence is best-effort, never fatal."""
    return jsonstore.write_json_atomic(_path(config_path), data)


def key(account_id, marketplace):
    return f"{account_id}::{str(marketplace or '').upper()}"


# FIELDS THE CATALOGUE REPORT DOES NOT CARRY.
#
# Amazon's listings report has no images in it. They arrive afterwards, one SKU
# at a time, from a different API -- enrich() writes them and domain/
# live_refresher.py grinds through the backlog a batch per pass.
#
# So a fresh report legitimately arrives with these blank, and treating blank as
# "Amazon says there is no image" erased hours of that work on every Sync. See
# _carry_forward below.
#
# The variation fields are here for exactly the same reason as the images. The
# listings report has no relationships block in it, so a fresh sync legitimately
# arrives with them blank -- and a straight replace would wipe every family the
# refresher had learned, on every Sync, exactly as it used to wipe the
# thumbnails.
_ENRICHED_FIELDS = ("img", "images", "img_source",
                    "parent_skus", "child_skus", "variation_theme")


def _carry_forward(new_items, prev_items):
    """Keep what a fresh report does not know, per SKU. Returns (items, kept).

    THE BUG THIS FIXES, in the owner's words:

        "i am not able to see the images of the items in the inventory section,
         i was able to see it once but now even after clicking on refresh or
         reloading the page i am not able to see the images"

    Every Sync called save(), save() replaced `items` wholesale, and the
    catalogue report has no images in it -- so each Sync wiped every thumbnail
    the background refresher had collected, and they trickled back over the next
    hour. Pressing Refresh made it WORSE, which is the opposite of what a
    refresh button should do.

    Measured on nestwell_goods: 39 of 45 items had an image before a sync and 0
    after, with the refresher then re-fetching them a batch at a time.

    A BLANK NEVER OVERWRITES A KNOWN VALUE, and that is the whole rule. If the
    new report genuinely carries an image, it wins -- this only fills gaps. It
    is the same principle already in save(): a partial result must not erase a
    complete one.
    """
    prev_by_sku = {}
    for it in (prev_items or []):
        if isinstance(it, dict):
            s = str(it.get("sku") or "").strip().upper()
            if s:
                prev_by_sku[s] = it
    if not prev_by_sku:
        return list(new_items or []), 0

    out, kept = [], 0
    for it in (new_items or []):
        if not isinstance(it, dict):
            out.append(it)
            continue
        old = prev_by_sku.get(str(it.get("sku") or "").strip().upper())
        if old:
            merged = dict(it)
            filled = False
            for f in _ENRICHED_FIELDS:
                if not merged.get(f) and old.get(f):
                    merged[f] = old[f]
                    filled = True
            if filled:
                kept += 1
            out.append(merged)
        else:
            out.append(it)
    return out, kept


def _merge_missing(new_items, prev_items):
    """Fresh items, plus any previous listing the fresh set does not mention.

    Returns (items, carried). Used only when a sync is known to be INCOMPLETE.

    THE RULE: within a SKU the fresh reading always wins -- that is the whole
    point of syncing. A SKU the incomplete sync never mentioned is kept from the
    previous record, because "the inactive report did not load" is not the same
    statement as "that listing is gone".
    """
    fresh_skus = set()
    for it in (new_items or []):
        if isinstance(it, dict):
            s = str(it.get("sku") or "").strip().upper()
            if s:
                fresh_skus.add(s)
    out = list(new_items or [])
    carried = 0
    for it in (prev_items or []):
        if not isinstance(it, dict):
            continue
        s = str(it.get("sku") or "").strip().upper()
        if s and s not in fresh_skus:
            kept = dict(it)
            # Marked, so nothing downstream mistakes a carried row for something
            # Amazon confirmed in this sync.
            kept["carried_from_previous_sync"] = True
            out.append(kept)
            carried += 1
    return out, carried


def save(config_path, account_id, marketplace, items, report_source="",
         partial=False, warnings=None):
    """Store one account+marketplace catalogue. Returns the stored record.

    A COMPLETE sync REPLACES what is stored. It is the authority: if a listing
    is not in it, that listing is gone, and a delete has to be able to reach the
    store or the catalogue only ever grows.

    AN INCOMPLETE sync MERGES. Fresh readings win per SKU; listings the
    incomplete sync never mentioned are carried over from the previous record.

    WHY THIS CHANGED, AND WHAT IT COST

        "the app was showing some items out of stock i went to seller central
         and added stock to some of them in nestwell goods but the app is still
         showing it out of stock even i have refreshed and wait for many hours"

    This used to DISCARD an incomplete result wholesale and return the previous
    record untouched. That guarded the real 64 -> 16 collapse, but it also meant
    a single flag froze the entire catalogue -- every price, every status, every
    QUANTITY -- at whatever it was when the last complete sync landed.

    Measured in live_snapshots.json on 18 Aug 2026:

        nestwell_goods::UK   count 45, ts 04:49:33
                             superseded_by_partial_at 08:36:04
                             last_partial_count 42
        jack_uk::UK          the same signature, ~08:26

    Seven nestwell SKUs sat at qty 0 that had been restocked in Seller Central
    hours earlier. The background refresher re-queued the pair every ten
    minutes, and every attempt was refused by this guard, silently, for ever.

    The caller made it self-perpetuating: it raised a warning BECAUSE the new
    list was shorter, and the warning is what set partial -- so any account
    whose listing count went down could never write again. The warning even
    said "Showing the new result", which was true of the screen and false of
    the disk. That is fixed at the caller; this function no longer has to be
    the last line of defence.

    Merging keeps both properties: nothing that Amazon failed to report is
    erased, and everything Amazon DID report is written. There is no state in
    which the store cannot move.

    AND A BLANK FIELD NEVER OVERWRITES A KNOWN ONE. The report carries no
    images; they are filled in afterwards, and a straight replace threw them all
    away on every Sync. See _carry_forward.
    """
    with _LOCK:
        _prev = (_read_all(config_path).get(key(account_id, marketplace))
                 or {}).get("items") or []
    items, _kept = _carry_forward(items, _prev)
    # An incomplete sync is missing whole categories of listing, not individual
    # fields, so the gaps are filled a row at a time rather than a field at a
    # time. A complete one is the authority and keeps nothing back.
    _carried = 0
    if partial and _prev:
        items, _carried = _merge_missing(items, _prev)
    rec = {
        "items": list(items or []),
        # How many listings kept a picture the fresh report did not carry.
        # Reported rather than silent: if this is ever 0 on an account that had
        # images, something has changed about the report and it is worth seeing.
        "carried_forward": _kept,
        # How many whole listings this record kept from the previous sync
        # because an incomplete one never mentioned them. 0 on a complete sync,
        # always, because a complete sync carries nothing over.
        "carried_listings": _carried,
        "count": len(items or []),
        "ts": time.time(),
        "report_source": report_source or "",
        "partial": bool(partial),
        "warnings": list(warnings or []),
    }
    with _LOCK:
        data = dict(_read_all(config_path))
        k = key(account_id, marketplace)
        # Always written. The record above already carries anything an incomplete
        # sync could not see, so there is no case left where refusing the write
        # protects something -- and refusing it is what froze two accounts'
        # quantities for half a day.
        data[k] = rec
        _MEM["data"] = data
        _write_all(config_path, data)
    return rec


def enrich(config_path, account_id, marketplace, by_sku):
    """Merge extra fields onto items already stored, without re-dating them.

    Images, real statuses and fulfillment details arrive AFTER the catalogue
    report, from a different Amazon API and one SKU at a time. They belong on the
    saved listing so the next person to open the workspace sees a complete card
    immediately, rather than watching thumbnails trickle in.

    Deliberately does NOT touch `ts`, `count`, `partial` or `report_source`. This
    is not a new catalogue -- it is the same catalogue with more known about it,
    and moving the timestamp would tell the refresher the listings had been
    re-fetched from Amazon when they had not, so a genuinely stale catalogue
    would never come up for refresh again.

    Returns how many items were changed.
    """
    if not by_sku:
        return 0
    changed = 0
    with _LOCK:
        data = dict(_read_all(config_path))
        k = key(account_id, marketplace)
        rec = data.get(k)
        if not isinstance(rec, dict):
            return 0
        items = list(rec.get("items") or [])
        for it in items:
            extra = by_sku.get(str(it.get("sku") or ""))
            if not extra:
                continue
            touched = False
            for f, v in extra.items():
                if v not in (None, "") and it.get(f) != v:
                    it[f] = v
                    touched = True
            if touched:
                changed += 1
        if not changed:
            return 0
        rec = dict(rec)
        rec["items"] = items
        rec["enriched_ts"] = time.time()
        data[k] = rec
        _MEM["data"] = data
        _write_all(config_path, data)
    return changed


def get(config_path, account_id, marketplace):
    """The stored record for one account+marketplace, or None."""
    rec = _read_all(config_path).get(key(account_id, marketplace))
    return rec if isinstance(rec, dict) else None


def age_seconds(rec):
    """How old a record is, or None when there is no usable timestamp."""
    try:
        return max(0.0, time.time() - float((rec or {}).get("ts") or 0)) if rec else None
    except Exception:
        return None


def summary(config_path):
    """Every stored key with its count and age -- for diagnostics/health views."""
    out = []
    for k, rec in (_read_all(config_path) or {}).items():
        if not isinstance(rec, dict):
            continue
        out.append({"key": k, "count": rec.get("count", 0), "ts": rec.get("ts"),
                    "age_seconds": age_seconds(rec), "partial": rec.get("partial", False)})
    return sorted(out, key=lambda r: r["key"])
