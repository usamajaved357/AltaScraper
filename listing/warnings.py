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


def _existing(row):
    """The warnings already stored on a row. [] for anything unreadable.

    Needed only to tell "this row has never had a refusal" from "it had one and
    it is now fixed" -- the second has to be written back as an empty list, the
    first must leave the row alone."""
    raw = row.get("warnings") if isinstance(row, dict) else None
    if isinstance(raw, list):
        return [w for w in raw if isinstance(w, dict)]
    if not raw:
        return []
    try:
        got = json.loads(str(raw))
    except Exception:
        return []
    return [w for w in got if isinstance(w, dict)] if isinstance(got, list) else []


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
    # ITS OWN FIELD FIRST. This read `notes` before `compliance_notes`, and so
    # does ip_risk above -- so a listing carrying both risks printed the SAME
    # sentence twice, once under each heading. Measured: 2 rows on jack_uk, both
    # showing "RE-VERIFIED -- LIVE | COMPLIANCE [HIGH]: electrical | Key
    # reqs..." as an IP warning and again as a compliance one.
    #
    # `notes` is the generator's general log line and belongs to neither check;
    # compliance_notes is this one's own. Preferring it means the two warnings
    # say different things, which is the point of there being two.
    reason = _s(row, "compliance_notes") or _s(row, "notes")
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


def amazon_refused(row):
    """Amazon refused this listing, and the row still carries what it said.

        "A listing previously showed API_ERROR status after a failed
         putListingsItem submission. After a Sync the error disappeared and the
         status changed to APPROVED. The API error is now invisible."

    That is what happens when a rejection lives in the STATUS column: the status
    is Amazon's current state and Sync is entitled to change it, so the record
    of the refusal goes with it. The reply is kept in its own column now
    (api_issues_json -- see listing/api_issues.py) which nothing but a fresh
    Preview or Submit writes, so a Sync cannot erase it.

    This turns it into a warning so it shows up wherever warnings already do --
    the card badge, the detailed row's chip, the product page's hero -- without
    any of those three learning about a new field (CLAUDE.md Rule 12). The
    product page draws the full banner from the same column.

    ONLY ERRORS. "Accepted with warnings" is a success, and putting an amber
    mark on a listing Amazon took would make the mark meaningless.
    """
    raw = _s(row, "api_issues_json")
    if not raw:
        return None
    try:
        from listing import api_issues as _ai
    except Exception:
        return None
    rec = _ai.parse(raw)
    errs = _ai.errors(rec)
    if not errs:
        return None
    first = errs[0]
    fields = sorted({f for e in errs for f in (e.get("fields") or [])})
    where = (" It names %s." % ", ".join(fields[:3])) if fields else ""
    when = (" (%s)" % rec["at"]) if rec.get("at") else ""
    what = ("refused this listing" if rec.get("mode") == "submit"
            else "would refuse this listing")
    return _warn(
        "amazon_refused", "high",
        "Amazon %s%s: %s%s%s" % (
            what, when, first.get("message") or "no message given",
            (" ...and %d more." % (len(errs) - 1)) if len(errs) > 1 else "",
            where),
        count=len(errs), at=rec.get("at", ""), mode=rec.get("mode", ""),
        fields=fields)


def fee_of_nothing(row):
    """A stored fee of zero on a listing with a price, presented as Amazon's.

        "i suspect the fee is hardcoded and not actually coming from amazon,
         which is a bad inaccurate behavior, i dont want inaccuracy"

    The fee is NOT hardcoded -- measured across 154 rows stamped
    "SP-API (exact)", the rates Amazon returned are 15%, 13%, 12%, 8%, 14.6%
    and 11.7%, which no flat multiplier produces. But 17 of those rows carry
    0.00, and that IS wrong: Amazon charges a referral fee on every category a
    bird table, a pizza peel or a massage gun could be in. A zero is a quote
    that came back empty and was recorded as a fee of nothing.

    It matters because the stored PROFIT was worked out from it. Every one of
    these is too high by the whole fee -- on a £21.99 massage gun that is £3.30
    of profit that does not exist.

    domain/amazon_fees.quote refuses a zero referral now, so no new row can be
    written this way. This names the ones already stored, because a number that
    is wrong and looks confident is worse than one that is missing.
    """
    fee = _s(row, "amazon_fees")
    price = _s(row, "our_price") or _s(row, "buy_box_price")
    if not fee or not price:
        return None
    try:
        if float(fee) != 0 or float(price) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    src = _s(row, "fee_source")
    return _warn(
        "fee_of_nothing", "medium",
        "This listing records an Amazon fee of 0.00 on a price of %s%s. Amazon "
        "charges a referral fee on every category, so that is a quote that came "
        "back empty rather than a fee of nothing — and the profit shown for this "
        "listing is too high by the whole fee. Preview it again to get a real "
        "figure." % (price, (" (marked \"%s\")" % src) if src else ""),
        price=price, fee_source=src)


def no_product_type(row):
    """This listing has no product type, so some compliance rules cannot apply.

        "why are we having products with no product type, the app should be
         able to pull the product type of the items, dont skip compliance
         checks"

    The checks are not skipped -- a blank type leaves the gate wide open, which
    means every category keyword still flags and nothing is silently dropped.
    But six categories (electrical, health_beauty, knives_blades,
    tools_hardware, cookware_kitchen, toys_children) use the type to rule
    THEMSELVES out on a product they cannot apply to, and without it they
    cannot. So a blank type is a listing whose compliance column is noisier
    than it needs to be, and whose submit will go out under whatever type the
    generator falls back to.

    listing/product_type.backfill fills what it can from the title first, so by
    the time this runs the only blanks left are the ones nothing could type.
    Measured before the backfill: 32 of 303, all on jack_uk, mostly eBay-sourced
    rows whose SKU carries an eBay item id where an ASIN would be -- so there
    was never an ASIN to read a type from.
    """
    if _s(row, "product_type"):
        return None
    return _warn(
        "no_product_type", "low",
        "No product type on this listing. Amazon's own product type is what "
        "lets the compliance checks rule themselves out, so without it this "
        "listing is checked against every category. Press Sync to bring it in "
        "from Amazon, or set it on the listing.")


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
        # A REFUSAL IS NOT ABOUT OUR WORKFLOW STATE, so it is not filtered by it.
        #
        # ACTIVE_STATUSES is QUEUED/GENERATED/SUBMITTED/LIVE -- the rows still
        # moving through this app. A listing Amazon REFUSED is in API_ERROR,
        # and the one in the report had been moved on to APPROVED. Both sit
        # outside that set, so every check below skipped them and the only two
        # statuses that can carry a refusal were the two that could never show
        # one. Amazon's own reply is evaluated for every row.
        _refused = amazon_refused(r)
        if str(r.get("status") or "").upper() not in ACTIVE_STATUSES:
            # Touched only when there is something to say or something to
            # UNsay. A row outside the active set is otherwise left exactly as
            # it is: it may still carry warnings from when it was GENERATED,
            # and dropping those here would be a change nobody asked for.
            _had = any(str(w.get("type")) == "amazon_refused"
                       for w in _existing(r))
            if _refused or _had:
                out[r.get("sku")] = _dedupe([_refused] if _refused else [])
            continue
        found = [
            duplicate_barcode(r, by_upc),
            duplicate_ebay_item(r, by_item),
            duplicate_competitor_asin(r, by_asin),
            ip_risk(r),
            compliance_risk(r),
            no_barcode(r),
            _refused,
            fee_of_nothing(r),
            no_product_type(r),
            barcode_live_on_amazon(r, live_by_upc or {}),
        ]
        # The catalogue's age is a property of the whole run, but it only
        # matters to a row whose barcode check depended on it.
        if stale and _s(r, "upc"):
            found.append(stale)
        out[r.get("sku")] = _dedupe([w for w in found if w])
    return out


def _dedupe(warns):
    """Drop a warning that says exactly what an earlier one already said.

        "listing/warnings.py stores the same warning twice in the warnings JSON
         array."

    IT WAS NEVER THE SAME TYPE TWICE -- for_rows builds one of each, and
    recompute_workspace REPLACES the column rather than appending, so a
    duplicate by (type, message) cannot happen and none exists in the data
    (measured: 0 rows out of 171 carrying warnings).

    What DOES happen, and is what a reader means by a duplicate, is the same
    SENTENCE under two headings: ip_risk and compliance_risk both fell back to
    the row's general `notes`. That is fixed at the source above; this is the
    guard that keeps it fixed, and it works for any future pair.

    THE FIRST ONE WINS, and the order in for_rows is deliberate -- the
    duplicate checks come before the risk verdicts, so the more specific
    warning is the one kept. Nothing is merged or reworded: a warning is either
    new information or it is not shown.
    """
    seen, out = set(), []
    for w in warns:
        if not isinstance(w, dict):
            continue
        msg = " ".join(str(w.get("message") or "").split()).lower()
        key = (str(w.get("type") or ""), msg)
        # Both keys: the same type twice is a duplicate whatever it says, and
        # the same sentence twice is a duplicate whatever it is filed under.
        if key in seen or ("*", msg) in seen:
            continue
        seen.add(key)
        if msg:
            seen.add(("*", msg))
        out.append(w)
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
    # AND FILL IN THE PRODUCT TYPES, before the warnings are worked out.
    #
    #     "why are we having products with no product type, the app should be
    #      able to pull the product type of the items"
    #
    # Because compliance_risk below reads product_type to decide which category
    # rules can apply, a blank one is not cosmetic -- it is a check resting on
    # an empty field. Filled here, next to backfill_ebay_ids and for the same
    # reason: it has to have happened before anything reads the row.
    try:
        from listing import product_type as _pt_mod
        _pt_mod.backfill(config_path, workspace_id)
    except Exception:
        pass          # a backfill must never be the reason warnings do not run
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
