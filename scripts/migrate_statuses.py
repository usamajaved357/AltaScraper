"""scripts/migrate_statuses.py -- fold the old hold statuses into GENERATED.

    python scripts/migrate_statuses.py              # dry run, changes nothing
    python scripts/migrate_statuses.py --apply      # do it, after a backup

WHAT THIS IS FOR

The listing flow had statuses that BLOCKED: a row that tripped the IP check or
the compliance check stopped, and nothing could be submitted until somebody
cleared it. The new flow has four -- QUEUED, GENERATED, SUBMITTED, LIVE -- and
nothing blocks. What used to stop a listing becomes a WARNING carried on the
row, and the person decides what to fix and what to send anyway.

So this moves the old statuses onto GENERATED and, where the old status was
carrying a REASON, keeps that reason as a warning. That last part is the whole
point of the script: NEEDS_REVIEW carries nothing and can simply be renamed,
but IP_HOLD, COMPLIANCE_HOLD and API_ERROR each mean something specific, and a
migration that renamed them to GENERATED and stopped would throw away the only
record of why the listing was stopped.

THE MAP

    NEEDS_REVIEW     -> GENERATED
    APPROVED         -> GENERATED
    API_READY        -> GENERATED      passed Amazon's preview; passFilter
                                       already counts it as ready-to-submit
    IP_HOLD          -> GENERATED  + warning (ip_risk)
    COMPLIANCE_HOLD  -> GENERATED  + warning (compliance_risk / notes)
    API_ERROR        -> GENERATED  + warning (Amazon's own rejection text)

    SUBMITTED, LIVE  -> unchanged
    PARENT           -> LEFT ALONE. A variation parent is not a listing and has
                        no place in a four-status model for listings.
    anything else    -> LEFT ALONE, and reported, rather than guessed at.

DRY RUN IS THE DEFAULT, and --apply is the only way to write. This follows the
same rule the sheet importer uses: a script that changes several hundred rows on
its first run is one nobody can safely run to find out what it does.

--apply copies the database into _backups/ first. The status column is being
overwritten in place and there is no other record of what it held.
"""
import argparse
import json
import os
import shutil
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# THE SAME CONFIG THE APP READS, resolved the same way dashboard.py resolves it.
#
# A bare "config.json" is right on a developer machine and wrong in the deployed
# container, where the code is at /app and the config on the persistent volume
# at /data/config.json. Hardcoding the relative name there would resolve to
# /app/config.json, which does not exist -- so db_path() would hand back
# /app/altascraper.db, an empty database this script would migrate happily and
# report "nothing to do" about, while production sat untouched.
#
# That is the same class of mistake as clearing the wrong workspace: not a
# crash, an answer about the wrong thing.
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")

# ---- the map ---------------------------------------------------------------

PLAIN = {                       # renamed, nothing to carry over
    "NEEDS_REVIEW": "GENERATED",
    "APPROVED": "GENERATED",
    "API_READY": "GENERATED",
}

# THE RISK COLUMNS ARE A SEVERITY, NOT A REASON.
#
# ip_risk and compliance_risk hold one word -- HIGH, MEDIUM, BASELINE. Measured
# across all 22 hold rows in this database, neither is ever longer than twelve
# characters, and the first version of this script read them as the message and
# would have written a warning whose entire text was "HIGH".
#
# The reason lives in `notes`, which is populated on every one of those rows and
# always substantial: "COMPLIANCE [HIGH]: electrical | Key reqs: UKCA marking
# required for UK market...". compliance_notes carries the product-specific
# declarations (batteries, liquids, expiry) on 19 of them and is worth keeping,
# but as detail rather than as the headline.
#
# So each column is used for what it actually is: the risk column sets the
# severity, `notes` is the message, compliance_notes rides along in details.
#
# status -> (new status, warning type, the column giving severity,
#            default severity when that column is empty)
WITH_REASON = {
    "IP_HOLD": ("GENERATED", "ip_risk", "ip_risk", "high"),
    "COMPLIANCE_HOLD": ("GENERATED", "compliance_risk", "compliance_risk", "medium"),
    # Amazon REFUSED this one. The reason is the most valuable thing on the row
    # and the only thing separating it from an ordinary generated listing.
    "API_ERROR": ("GENERATED", "amazon_rejected", None, "high"),
}

# What the risk columns say -> what a warning calls it.
SEVERITY_WORDS = {
    "HIGH": "high", "MEDIUM": "medium", "MED": "medium",
    "LOW": "low", "BASELINE": "low", "NONE": "low",
}

UNCHANGED = {"SUBMITTED", "LIVE", "GENERATED", "QUEUED"}
LEAVE_ALONE = {"PARENT", "REMOVED", "GONE"}

FALLBACK_MESSAGE = {
    "ip_risk": "Held by this app's IP check before the new flow. No reason was "
               "recorded on the row.",
    "compliance_risk": "Held by this app's compliance check before the new "
                       "flow. No reason was recorded on the row.",
    "amazon_rejected": "Amazon refused this listing before the new flow. No "
                       "reason was recorded on the row.",
}


def _clean(row, field):
    """A field's value, with the app's ways of writing "nothing" treated as such."""
    if not field:
        return ""
    v = str(row.get(field) or "").strip()
    return "" if v.lower() in ("none", "null", "n/a", "-", "") else v


def warning_for(status, row):
    """The warning that preserves why this row was stopped, or None."""
    if status not in WITH_REASON:
        return None
    _new, wtype, sev_field, default_sev = WITH_REASON[status]

    # Severity: what the row itself recorded, not a guess. A COMPLIANCE_HOLD
    # marked BASELINE and one marked HIGH are not the same warning.
    recorded = _clean(row, sev_field).upper()
    severity = SEVERITY_WORDS.get(recorded, default_sev)

    # Message: the prose. `notes` is where the app writes it.
    reason = _clean(row, "notes")
    extra = _clean(row, "compliance_notes")
    if not reason:
        # compliance_notes is the only prose on some rows; better than nothing.
        reason, extra = extra, ""

    details = {"migrated_from": status, "recorded_reason": bool(reason)}
    if recorded:
        details["recorded_risk"] = recorded
    if extra:
        details["product_notes"] = extra[:600]

    return {
        "type": wtype,
        "severity": severity,
        "message": reason[:600] or FALLBACK_MESSAGE[wtype],
        "details": details,
    }


# ---- the database ----------------------------------------------------------

def connect():
    from data import db as _db
    return _db.get_db(CONFIG_PATH)


def db_file():
    from data import db as _db
    try:
        return _db.db_path(CONFIG_PATH)
    except Exception:
        return os.path.join(ROOT, "altascraper.db")


def has_warnings_column(conn):
    return "warnings" in [r[1] for r in conn.execute("PRAGMA table_info(listings)")]


def backup_dir():
    """_backups NEXT TO THE DATABASE, not next to the code.

    On this machine those are the same folder and it never mattered. In the
    deployed container they are not: the code lives at /app and the database on
    the persistent volume at /data, and /app is rebuilt on every deploy. A
    backup written beside the code would be destroyed by the next redeploy --
    which is to say, exactly when someone came looking for it.

    Following the database means the backup lands wherever the database really
    is, on any host, without this script knowing which host it is on.
    """
    d = os.path.join(os.path.dirname(os.path.abspath(db_file())), "_backups")
    os.makedirs(d, exist_ok=True)
    return d


def backup_db():
    src = db_file()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(backup_dir(),
                       "altascraper.before-status-migration-%s.db" % stamp)
    shutil.copy2(src, dst)
    return dst


def merge_warnings(existing_json, new_warning):
    """Add a warning without dropping any that are already on the row.

    Stored as a JSON ARRAY, not {"warnings": [...]}. The column is called
    warnings; wrapping an array in an object of the same name buys nothing and
    makes every reader unwrap twice.
    """
    try:
        cur = json.loads(existing_json) if existing_json else []
        if isinstance(cur, dict):                 # tolerate the nested shape
            cur = cur.get("warnings") or []
        if not isinstance(cur, list):
            cur = []
    except Exception:
        cur = []
    if new_warning:
        already = any(w.get("type") == new_warning["type"]
                      and w.get("details", {}).get("migrated_from")
                      == new_warning["details"]["migrated_from"]
                      for w in cur if isinstance(w, dict))
        if not already:
            cur.append(new_warning)
    return json.dumps(cur, ensure_ascii=False)


# ---- the run ---------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually write. Without this, nothing changes.")
    ap.add_argument("--dry-run", action="store_true",
                    help="the default; accepted so it can be said out loud")
    args = ap.parse_args()
    apply = bool(args.apply) and not args.dry_run

    conn = connect()
    print("database : %s" % db_file())
    print("mode     : %s\n" % ("APPLY -- rows will be written" if apply
                               else "DRY RUN -- nothing will be changed"))

    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM listings ORDER BY workspace_id, status")]
    if not rows:
        print("No listings. Nothing to do.")
        return 0

    plan = []            # (id, workspace, sku, old, new, warning)
    untouched = Counter()
    for r in rows:
        old = str(r.get("status") or "").strip().upper()
        if old in PLAIN:
            plan.append((r["id"], r["workspace_id"], r.get("sku"), old,
                         PLAIN[old], None))
        elif old in WITH_REASON:
            plan.append((r["id"], r["workspace_id"], r.get("sku"), old,
                         WITH_REASON[old][0], warning_for(old, r)))  # noqa: E501
        elif old in UNCHANGED:
            untouched["%s (already correct)" % (old or "(blank)")] += 1
        elif old in LEAVE_ALONE:
            untouched["%s (left alone deliberately)" % old] += 1
        else:
            untouched["%s (UNKNOWN -- left alone)" % (old or "(blank)")] += 1

    # ---- what would change -------------------------------------------------
    by_ws = {}
    for _id, ws, _sku, old, new, warn in plan:
        by_ws.setdefault(ws, Counter())["%s -> %s%s" % (
            old, new, "  + warning" if warn else "")] += 1

    print("=== what changes ===")
    if not plan:
        print("  nothing")
    for ws in sorted(by_ws):
        print("  %s" % ws)
        for change, n in sorted(by_ws[ws].items()):
            print("      %-34s %d" % (change, n))
    print("\n  %d row(s) would change status" % len(plan))
    n_warn = sum(1 for p in plan if p[5])
    print("  %d of them keep a reason as a warning" % n_warn)

    print("\n=== left as they are ===")
    for k, n in sorted(untouched.items()):
        print("  %-40s %d" % (k, n))

    # A reason worth seeing before it is written, not after.
    if n_warn:
        print("\n=== a sample of the warnings that would be written ===")
        shown = 0
        for _id, ws, sku, old, _new, warn in plan:
            if warn and shown < 5:
                print("  %s / %s" % (ws, str(sku)[:34]))
                print("      [%s/%s] %s" % (warn["type"], warn["severity"],
                                            warn["message"][:100]))
                shown += 1

    has_col = has_warnings_column(conn)
    print("\n=== schema ===")
    print("  listings.warnings column exists: %s" % has_col)
    if not has_col:
        print("      --apply will add it:  ALTER TABLE listings ADD COLUMN "
              "warnings TEXT DEFAULT ''")

    # The old input queue, for completeness. Moving those rows needs a real SKU
    # built for each, which is step 2's job -- reported here, not done here.
    try:
        q = conn.execute("SELECT workspace_id, COUNT(*) n FROM input_products "
                         "GROUP BY workspace_id").fetchall()
        print("\n=== the old input queue (moved in step 2, not here) ===")
        if not q:
            print("  empty")
        for r in q:
            print("  %-20s %d row(s) still queued" % (r[0], r[1]))
    except Exception as e:
        print("\n  (could not read the input queue: %s)" % str(e)[:80])

    if not apply:
        print("\nDRY RUN -- nothing was changed. Re-run with --apply to write.")
        return 0

    # ---- the leftover queue rows ------------------------------------------
    # Anything still sitting in the old input_products table that was never
    # generated becomes a QUEUED listing, with a real SKU built the same way an
    # upload builds one. The queue row is FLAGGED, not deleted: if the move is
    # wrong, the original is still there to read.

    # ---- write -------------------------------------------------------------
    print("\nbackup   : %s" % backup_db())
    if not has_col:
        conn.execute("ALTER TABLE listings ADD COLUMN warnings TEXT DEFAULT ''")
        conn.commit()
        print("schema   : added listings.warnings")

    changed = 0
    for _id, _ws, _sku, _old, new, warn in plan:
        if warn:
            cur = conn.execute("SELECT warnings FROM listings WHERE id=?",
                               (_id,)).fetchone()
            merged = merge_warnings(cur["warnings"] if cur else "", warn)
            conn.execute("UPDATE listings SET status=?, warnings=? WHERE id=?",
                         (new, merged, _id))
        else:
            conn.execute("UPDATE listings SET status=? WHERE id=?", (new, _id))
        changed += 1
    conn.commit()
    print("written  : %d row(s)" % changed)

    print("\n=== the old input queue ===")
    print("  %s" % migrate_queue(conn))

    print("\n=== statuses now ===")
    for r in conn.execute("SELECT status, COUNT(*) n FROM listings "
                          "GROUP BY status ORDER BY n DESC"):
        print("  %-18s %d" % (r[0] or "(blank)", r[1]))
    return 0


def migrate_queue(conn):
    """Old input_products rows -> QUEUED listings. Returns a one-line report.

    Marked rather than deleted: `source` becomes "migrated:<original>", so the
    row is still readable and cannot be picked up twice.
    """
    from data import queued_store as _qs

    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM input_products WHERE source NOT LIKE 'migrated:%'")]
    except Exception as e:
        return "no queue table to migrate (%s)" % str(e)[:60]
    if not rows:
        return "nothing left in the old queue"

    moved = failed = 0
    per_ws = {}
    for r in rows:
        ws = r.get("workspace_id") or "_no_account"
        try:
            product = {k: r.get(k) for k in (
                "ebay_url", "amazon_url", "competitor_asin", "item_name",
                "source_cost", "selling_price", "handling_time", "upc")}
            taken = per_ws.setdefault(ws, _qs.taken_skus(CONFIG_PATH, ws))
            _qs.add_queued(CONFIG_PATH, ws, product, taken=taken)
            conn.execute("UPDATE input_products SET source=? WHERE id=?",
                         ("migrated:%s" % (r.get("source") or ""), r["id"]))
            moved += 1
        except Exception:
            failed += 1
    conn.commit()
    return "moved %d row(s) into the listings store as QUEUED%s" % (
        moved, (", %d could not be moved" % failed) if failed else "")


if __name__ == "__main__":
    sys.exit(main())
