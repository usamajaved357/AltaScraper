"""listing/warnings.py -- what is wrong with a listing, said rather than enforced.

NOTHING BLOCKS ANY MORE. IP_HOLD and COMPLIANCE_HOLD used to stop a listing:
the row sat there and Submit was not available until somebody cleared it. Those
statuses are gone (scripts/migrate_statuses.py folded them into GENERATED) and
what they were protecting against is now said out loud instead. The person
decides what to fix and what to send anyway.

That is a real trade and worth being honest about: a warning that is ignored is
a listing that goes to Amazon with a known problem. The bet is that a person
looking at 200 listings, each carrying a plain sentence about what is wrong with
it, catches more than a status that stops 22 of them and says "hold".

WHERE THIS RUNS. After a generate finishes, over the whole workspace, because
five of the eight checks are about how rows relate to EACH OTHER -- a duplicate
barcode is not a property of one row. Recomputing the set is also what keeps
them true: fix the barcode on one listing and the warning on the other one it
clashed with has to go, and a warning written once at generation time would sit
there for ever being wrong.

WHAT IT DOES NOT DO. It does not re-run the IP and compliance analysers. Those
belong to listing/flags.py and listing/compliance.py, they run during
generation, and they write their verdicts onto the row (ip_risk,
compliance_risk, notes). This reads those verdicts and words them as warnings --
the same thing scripts/migrate_statuses.py did for the rows that already had
holds, so a migrated warning and a freshly generated one say the same thing
about the same situation (CLAUDE.md Rule 12).
"""
import json

# Rows in any of these count as "already using" a barcode or an ASIN. A QUEUED
# row counts: two queued rows sharing a barcode is exactly the clash worth
# knowing about before either is generated.
ACTIVE_STATUSES = ("QUEUED", "GENERATED", "SUBMITTED", "LIVE")

# Amazon's catalogue is fetched by a Sync. Past this, the "already live" check
# below is answering from data old enough to be wrong.
STALE_AFTER_HOURS = 24

SEVERITY_WORDS = {
    "HIGH": "high", "MEDIUM": "medium", "MED": "medium",
    "LOW": "low", "BASELINE": "low", "NONE": "low",
}


def _s(row, field):
    v = str((row or {}).get(field) or "").strip()
    return "" if v.lower() in ("none", "null", "n/a", "-") else v


def _warn(wtype, severity, message, **details):
    return {"type": wtype, "severity": severity, "message": message,
            "details": details}


# ---- the checks ------------------------------------------------------------

def _index(rows, field):
    """value -> [rows carrying it], for the active statuses only."""
    out = {}
    for r in rows:
        if str(r.get("status") or "").upper() not in ACTIVE_STATUSES:
            continue
        v = _s(r, field)
        if v:
            out.setdefault(v.upper(), []).append(r)
    return out


def _others(bucket, row):
    """The rows in a bucket that are not this one."""
    return [r for r in bucket if r.get("sku") != row.get("sku")]


def duplicate_barcode(row, by_upc):
    upc = _s(row, "upc")
    if not upc:
        return None
    others = _others(by_upc.get(upc.upper(), []), row)
    if not others:
        return None
    o = others[0]
    return _warn(
        "duplicate_barcode", "high",
        "This EAN is already used in %s (%s) — change it before submitting."
        % (o.get("sku"), o.get("status")),
        existing_sku=o.get("sku"), existing_status=o.get("status"),
        also_on=[x.get("sku") for x in others[:5]])


def duplicate_ebay_item(row, by_item):
    """Matched on listing id AND variation id.

    api/ebay.py records the measurement that makes this necessary: on a live
    104-child variation listing all 104 children share ONE /itm/ id and are told
    apart only by ?var=, with prices from 9.99 to 23.49. Matching on the /itm/
    number alone would report every child as a duplicate of its 103 siblings,
    which would bury the duplicates this check exists to find.
    """
    item = _s(row, "ebay_item_id")
    if not item:
        return None
    ident = "%s|%s" % (item, _s(row, "ebay_variation_id"))
    others = _others(by_item.get(ident.upper(), []), row)
    if not others:
        return None
    o = others[0]
    return _warn(
        "duplicate_ebay_item", "medium",
        "This eBay item (ID %s) was already listed as %s — could be a duplicate."
        % (item, o.get("sku")),
        existing_sku=o.get("sku"), existing_status=o.get("status"),
        ebay_item_id=item, ebay_variation_id=_s(row, "ebay_variation_id"))


def duplicate_competitor_asin(row, by_asin):
    asin = _s(row, "competitor_asin")
    if not asin:
        return None
    others = _others(by_asin.get(asin.upper(), []), row)
    if not others:
        return None
    o = others[0]
    return _warn(
        "duplicate_competitor_asin", "medium",
        "Another listing already references ASIN %s (%s) — check whether this "
        "is a duplicate." % (asin, o.get("sku")),
        existing_sku=o.get("sku"), existing_status=o.get("status"), asin=asin)


def ip_risk(row):
    """From the verdict listing/flags.py already wrote onto the row."""
    level = _s(row, "ip_risk").upper()
    if not level or level in ("NONE", "BASELINE", "LOW"):
        return None
    reason = _s(row, "notes") or _s(row, "compliance_notes")
    return _warn(
        "ip_risk", SEVERITY_WORDS.get(level, "high"),
        reason[:600] or "This app's IP check flagged this listing (%s)." % level,
        recorded_risk=level, source="listing/flags.py")


def compliance_risk(row):
    """From the verdict listing/compliance.py already wrote onto the row."""
    level = _s(row, "compliance_risk").upper()
    if not level or level in ("NONE", "BASELINE"):
        return None
    reason = _s(row, "notes") or _s(row, "compliance_notes")
    extra = _s(row, "compliance_notes")
    return _warn(
        "compliance_risk", SEVERITY_WORDS.get(level, "medium"),
        reason[:600] or ("This category may require Amazon approval (%s)."
                         % level),
        recorded_risk=level, product_notes=extra[:400] or None,
        source="listing/compliance.py")


def no_barcode(row):
    if _s(row, "upc"):
        return None
    # NOT a recommendation to invent one. CLAUDE.md rule 1: never send a fake or
    # generated barcode, and the GTIN exemption is the owner's decision, never
    # the app's. Amazon refusing for want of an identifier is the correct
    # outcome, so this says what will happen and stops there.
    return _warn(
        "no_barcode", "low",
        "No barcode provided — Amazon may refuse this listing. Add a real EAN "
        "or UPC, or tick GTIN Exemption if this product genuinely has none.")


def barcode_live_on_amazon(row, live_by_upc):
    upc = _s(row, "upc")
    if not upc or not live_by_upc:
        return None
    hit = live_by_upc.get(upc.upper())
    if not hit:
        return None
    return _warn(
        "barcode_live_on_amazon", "medium",
        "This barcode is already live on Amazon under ASIN %s — Amazon matches "
        "a barcode to the listing that owns it and will refuse a second one."
        % hit, live_asin=hit)


def stale_catalogue(age_hours):
    if age_hours is None or age_hours < STALE_AFTER_HOURS:
        return None
    days = max(1, int(age_hours // 24))
    return _warn(
        "stale_catalogue", "low",
        "Amazon catalogue data is %d day%s old — Sync for more accurate "
        "duplicate checking." % (days, "" if days == 1 else "s"),
        age_hours=round(age_hours, 1))


# ---- putting them together -------------------------------------------------

def for_rows(rows, live_by_upc=None, age_hours=None):
    """{sku: [warning, ...]} for a whole workspace."""
    rows = list(rows or [])
    by_upc = _index(rows, "upc")
    by_asin = _index(rows, "competitor_asin")

    by_item = {}
    for r in rows:
        if str(r.get("status") or "").upper() not in ACTIVE_STATUSES:
            continue
        item = _s(r, "ebay_item_id")
        if item:
            ident = "%s|%s" % (item, _s(r, "ebay_variation_id"))
            by_item.setdefault(ident.upper(), []).append(r)

    stale = stale_catalogue(age_hours)
    out = {}
    for r in rows:
        if str(r.get("status") or "").upper() not in ACTIVE_STATUSES:
            continue
        found = [
            duplicate_barcode(r, by_upc),
            duplicate_ebay_item(r, by_item),
            duplicate_competitor_asin(r, by_asin),
            ip_risk(r),
            compliance_risk(r),
            no_barcode(r),
            barcode_live_on_amazon(r, live_by_upc or {}),
        ]
        # The catalogue's age is a property of the whole run, but it only
        # matters to a row whose barcode check depended on it.
        if stale and _s(r, "upc"):
            found.append(stale)
        out[r.get("sku")] = [w for w in found if w]
    return out


def live_barcodes(config_path, account_id, marketplace):
    """({barcode: asin}, age_in_hours) from the last Sync. ({}, None) if none."""
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, account_id, marketplace)
        if not rec:
            return {}, None
        age = _ls.age_seconds(rec)
        hours = (age / 3600.0) if age is not None else None
        by_upc = {}
        for it in (rec.get("items") or []):
            code = str(it.get("upc") or it.get("ean") or it.get("barcode") or "").strip()
            if code:
                by_upc.setdefault(code.upper(), it.get("asin") or "")
        return by_upc, hours
    except Exception:
        return {}, None


def backfill_ebay_ids(config_path, workspace_id):
    """Fill ebay_item_id / ebay_variation_id from source_url where they are empty.

    The columns are new, so every listing made before them is blank and the
    duplicate-eBay-item check would find nothing at all -- it would look like it
    was working and quietly never fire. The ids are derived from the URL that is
    already on the row, so nothing is invented; this is reading a field that was
    always there into a column that only just exists.

    Only fills blanks. A value already stored is never overwritten.
    """
    from data import db as _db
    from data import input_row as _ir

    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT sku, source_url FROM listings WHERE workspace_id=? "
        "AND source_url IS NOT NULL AND source_url<>'' "
        "AND (ebay_item_id IS NULL OR ebay_item_id='')", (workspace_id,)).fetchall()
    n = 0
    for r in rows:
        lid, vid = _ir.ebay_ids(r["source_url"])
        if not lid:
            continue
        conn.execute("UPDATE listings SET ebay_item_id=?, ebay_variation_id=? "
                     "WHERE workspace_id=? AND sku=?",
                     (lid, vid, workspace_id, r["sku"]))
        n += 1
    if n:
        conn.commit()
    return n


def recompute_workspace(config_path, workspace_id, marketplace=""):
    """Work the warnings out for a workspace and write them onto the rows.

    Returns (rows_examined, rows_carrying_at_least_one_warning).
    """
    from data import db as _db
    from data import queued_store as _qs

    _qs.ensure_columns(config_path)
    conn = _db.get_db(config_path)
    backfill_ebay_ids(config_path, workspace_id)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM listings WHERE workspace_id=?", (workspace_id,))]
    if not rows:
        return 0, 0

    live_by_upc, age_hours = live_barcodes(config_path, workspace_id, marketplace)
    found = for_rows(rows, live_by_upc, age_hours)

    flagged = 0
    for sku, warns in found.items():
        if not sku:
            continue
        if warns:
            flagged += 1
        conn.execute("UPDATE listings SET warnings=? WHERE workspace_id=? AND sku=?",
                     (json.dumps(warns, ensure_ascii=False), workspace_id, sku))
    conn.commit()
    return len(rows), flagged
