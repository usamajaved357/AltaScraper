"""scripts/recompute_warnings.py -- work out every listing's warnings, everywhere.

    python scripts/recompute_warnings.py            # dry run: counts, no writes
    python scripts/recompute_warnings.py --apply    # write them onto the rows

WHY THIS IS A SEPARATE STEP FROM THE MIGRATION

scripts/migrate_statuses.py moves the old hold statuses onto GENERATED and keeps
each row's own recorded reason as a warning. That is all it can do: those
warnings come off the row that is being migrated.

FIVE OF THE EIGHT CHECKS ARE ABOUT HOW ROWS RELATE TO EACH OTHER -- a duplicate
barcode, a duplicate eBay item, a duplicate competitor ASIN. None of those is a
property of one row, so none of them can be worked out while migrating one. They
need the whole workspace at once, which is what this does.

So after a migration, existing listings carry their old hold reasons and nothing
else. Until this runs, the duplicate warnings do not exist for anything that was
generated before the warning system did.

EVERY WORKSPACE. Read from the listings table rather than from config, so a
workspace with rows but no account entry is still covered.

THE DRY RUN IS ACCURATE, not an estimate. The duplicate-eBay-item check needs
ebay_item_id, which is blank on every row made before that column existed;
recompute_workspace backfills it from source_url. A dry run must not write, so
it derives those ids IN MEMORY instead -- otherwise it would report zero eBay
duplicates and the apply would then find nine, which is the sort of surprise
that makes people distrust the dry run.
"""
import argparse
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# The same config the app reads -- see the note in migrate_statuses.py about
# what a hardcoded "config.json" does inside the container.
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")


def workspaces(conn):
    """Every workspace that has listings, in a stable order."""
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT workspace_id FROM listings "
        "WHERE workspace_id IS NOT NULL AND workspace_id<>'' ORDER BY 1")]


def marketplace_for(workspace_id):
    """The account's marketplace, for the "already live on Amazon" check.

    That check reads the catalogue captured by the last Sync, which is stored
    per (account, marketplace). Without the marketplace it finds nothing -- the
    check silently never fires rather than reporting that it could not run.
    """
    try:
        import json
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
        for a in (cfg.get("accounts") or []):
            if str(a.get("id") or "") == str(workspace_id):
                mkt = str(a.get("default_marketplace") or "").strip().upper()
                if mkt:
                    return mkt
                for m in (a.get("marketplaces") or []):
                    if str(m).strip():
                        return str(m).strip().upper()
    except Exception:
        pass
    return ""


def rows_for_dry_run(conn, workspace_id):
    """The workspace's rows, with eBay ids derived in memory (nothing written)."""
    from data import input_row as _ir
    out = []
    for r in conn.execute("SELECT * FROM listings WHERE workspace_id=?",
                          (workspace_id,)):
        d = dict(r)
        if not str(d.get("ebay_item_id") or "").strip():
            lid, vid = _ir.ebay_ids(d.get("source_url") or "")
            d["ebay_item_id"] = lid
            d["ebay_variation_id"] = vid
        out.append(d)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the warnings onto the rows. Without this, "
                         "nothing is changed.")
    ap.add_argument("--dry-run", action="store_true",
                    help="the default; accepted so it can be said out loud")
    args = ap.parse_args()
    apply = bool(args.apply) and not args.dry_run

    from data import db as _db
    from listing import warnings as _w

    conn = _db.get_db(CONFIG_PATH)
    print("database : %s" % _db.db_path(CONFIG_PATH))
    print("mode     : %s\n" % ("APPLY -- warnings will be written"
                               if apply else "DRY RUN -- nothing is written"))

    wss = workspaces(conn)
    if not wss:
        print("No listings in any workspace. Nothing to do.")
        return 0

    by_type, by_sev = Counter(), Counter()
    per_ws = []

    for ws in wss:
        mkt = marketplace_for(ws)
        if apply:
            n, flagged = _w.recompute_workspace(CONFIG_PATH, ws, mkt)
            found = {}
            for r in conn.execute(
                    "SELECT sku, warnings FROM listings WHERE workspace_id=? "
                    "AND warnings IS NOT NULL AND warnings<>''", (ws,)):
                import json as _json
                try:
                    found[r[0]] = _json.loads(r[1] or "[]") or []
                except Exception:
                    found[r[0]] = []
        else:
            rows = rows_for_dry_run(conn, ws)
            live_by_upc, age_hours = _w.live_barcodes(CONFIG_PATH, ws, mkt)
            found = _w.for_rows(rows, live_by_upc, age_hours)
            n = len(rows)
            flagged = sum(1 for v in found.values() if v)

        for warns in found.values():
            for x in (warns or []):
                by_type[x.get("type") or "?"] += 1
                by_sev[x.get("severity") or "?"] += 1
        per_ws.append((ws, mkt or "-", n, flagged))

    print("=== per workspace ===")
    print("  %-20s %-6s %8s %10s" % ("WORKSPACE", "MKT", "LISTINGS", "WITH WARN"))
    for ws, mkt, n, flagged in per_ws:
        print("  %-20s %-6s %8d %10d" % (ws, mkt, n, flagged))

    print("\n=== warnings by type, across every workspace ===")
    if not by_type:
        print("  none")
    for k, n in by_type.most_common():
        print("  %-28s %d" % (k, n))

    print("\n=== by severity ===")
    for k in ("high", "medium", "low"):
        if by_sev.get(k):
            print("  %-10s %d" % (k, by_sev[k]))

    total = sum(by_type.values())
    print("\n  %d warning(s) on %d listing(s) across %d workspace(s)"
          % (total, sum(p[3] for p in per_ws), len(per_ws)))

    if not apply:
        print("\nDRY RUN -- nothing was written. Re-run with --apply to store them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
