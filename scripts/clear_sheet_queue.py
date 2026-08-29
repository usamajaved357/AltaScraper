"""scripts/clear_sheet_queue.py -- drop the old Google-Sheet imports from the queue.

    python scripts/clear_sheet_queue.py            # dry run, changes nothing
    python scripts/clear_sheet_queue.py --apply    # do it, after two backups

WHAT THIS IS FOR

The input queue (input_products) was filled two ways: rows imported from a
Google input sheet (source="sheet") and rows typed into the app by hand
(source="app"). The sheet import is gone, and on accounts where it ran the
queue is still holding those rows -- already generated, months old, and now
just noise.

ACROSS EVERY WORKSPACE, not one. The same import ran on several accounts and
there is no reason to clean one and leave the rest.

WHAT IT WILL NOT TOUCH

  source="app"          typed in by hand. These are somebody's work and the
                        only copy of it.
  source="upload"       came from a CSV/Excel upload.
  source="migrated:..." already moved into the listings store by
                        scripts/migrate_statuses.py; the flag is the record of
                        that move.
  anything else         reported, never guessed at.

Only source="sheet" is removed, and only after both backups below.

WHY THIS EXISTS SEPARATELY FROM THE MIGRATION

scripts/migrate_statuses.py MOVES leftover queue rows into the listings store as
status=QUEUED. That is right for rows still waiting to be generated and wrong
for these: they were generated long ago, so moving them would put 87 dead
products back in front of you as things to make.

SO THE ORDER MATTERS. Run this BEFORE the simplified-flow code reaches a
machine, or the migration will pick these rows up first and queue them.
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

CONFIG_PATH = "config.json"
TARGET_SOURCE = "sheet"


def db_file():
    from data import db as _db
    try:
        return _db.db_path(CONFIG_PATH)
    except Exception:
        return os.path.join(ROOT, "altascraper.db")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete. Without this, nothing changes.")
    ap.add_argument("--dry-run", action="store_true",
                    help="the default; accepted so it can be said out loud")
    args = ap.parse_args()
    apply = bool(args.apply) and not args.dry_run

    from data import db as _db
    conn = _db.get_db(CONFIG_PATH)

    print("database : %s" % db_file())
    print("mode     : %s\n" % ("APPLY -- rows will be deleted" if apply
                               else "DRY RUN -- nothing will be changed"))

    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM input_products")]
    except Exception as e:
        print("There is no input_products table here (%s)." % str(e)[:80])
        print("Nothing to do -- this queue has already been retired.")
        return 0

    if not rows:
        print("The queue is empty in every workspace. Nothing to do.")
        return 0

    # ---- what is there ------------------------------------------------------
    per = {}
    for r in rows:
        ws = r.get("workspace_id") or "(none)"
        per.setdefault(ws, Counter())[str(r.get("source") or "(none)")] += 1

    print("=== what is in the queue, by workspace and source ===")
    for ws in sorted(per):
        print("  %s" % ws)
        for src, n in sorted(per[ws].items()):
            mark = "  <- to delete" if src == TARGET_SOURCE else "     kept"
            print("      %-22s %5d%s" % (src, n, mark))

    doomed = [r for r in rows if str(r.get("source") or "") == TARGET_SOURCE]
    kept = len(rows) - len(doomed)
    print("\n  %d row(s) would be deleted, %d kept" % (len(doomed), kept))

    if not doomed:
        print("\nNo source=%r rows anywhere. Nothing to do." % TARGET_SOURCE)
        return 0

    if not apply:
        print("\nDRY RUN -- nothing was changed. Re-run with --apply to delete.")
        return 0

    # ---- two backups, because this cannot be undone -------------------------
    stamp = time.strftime("%Y%m%d-%H%M%S")
    os.makedirs("_backups", exist_ok=True)

    dbdst = os.path.join("_backups", "altascraper.before-queue-clear-%s.db" % stamp)
    shutil.copy2(db_file(), dbdst)
    print("\nbackup 1 : %s" % dbdst)

    jsdst = os.path.join("_backups", "input_queue_sheet_rows_%s.json" % stamp)
    with open(jsdst, "w", encoding="utf-8") as fh:
        json.dump({"deleted_at": stamp, "source": TARGET_SOURCE,
                   "count": len(doomed), "rows": doomed}, fh,
                  indent=1, ensure_ascii=False, default=str)
    print("backup 2 : %s (%d row(s), every column)"
          % (jsdst, len(doomed)))

    # ---- delete, scoped to workspace AND source -----------------------------
    # Both in the WHERE clause. Deleting by id alone would work, but a scoped
    # statement is the one that cannot go wrong if this file is ever edited.
    removed = 0
    for r in doomed:
        removed += conn.execute(
            "DELETE FROM input_products WHERE id=? AND workspace_id=? AND source=?",
            (r["id"], r.get("workspace_id"), TARGET_SOURCE)).rowcount
    conn.commit()
    print("deleted  : %d row(s)" % removed)

    print("\n=== the queue now ===")
    left = conn.execute("SELECT workspace_id, source, COUNT(*) n FROM "
                        "input_products GROUP BY workspace_id, source "
                        "ORDER BY 1,2").fetchall()
    if not left:
        print("  empty in every workspace")
    for r in left:
        print("  %-20s %-22s %d" % (r[0], r[1], r[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
