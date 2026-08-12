"""data/import_sheets.py -- one-time copy of a Google Sheet into the database.

    python -m data.import_sheets --workspace jack_uk --sheet-id 1abc...xyz
    python -m data.import_sheets --workspace jack_uk --sheet-id 1abc...xyz --dry-run

THE SHEET IS NEVER WRITTEN TO. This only reads. If the import turns out wrong,
the original is untouched and you can drop the database and try again -- which is
the entire safety net for this migration, so nothing here is allowed to modify a
sheet, not even to mark rows as imported.

--dry-run reads and reports without writing anything. Worth doing first: it tells
you how many rows will land, how many will be skipped and, importantly, whether
the sheet has columns the mapping does not know about.
"""
import argparse
import json
import os
import sys


def _gspread_client(service_account_path):
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        print("Missing a library: %s\n  pip install gspread google-auth" % e)
        sys.exit(2)
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    if not os.path.exists(service_account_path):
        print("Service account file not found: %s" % service_account_path)
        sys.exit(2)
    creds = Credentials.from_service_account_file(service_account_path, scopes=scopes)
    return gspread.authorize(creds)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Copy an existing Google Sheet of listings into the database. "
                    "Reads only -- the sheet is never modified.")
    p.add_argument("--workspace", required=True,
                   help="Workspace id to import into, e.g. jack_uk")
    p.add_argument("--sheet-id", required=True, help="Google spreadsheet id")
    p.add_argument("--tab", default=None,
                   help="Worksheet/tab name (default: the first tab)")
    p.add_argument("--service-account", default="service_account.json",
                   help="Path to the Google service account JSON")
    p.add_argument("--config", default=os.environ.get("CONFIG_PATH", "config.json"),
                   help="config.json path -- decides where the database file lives")
    p.add_argument("--dry-run", action="store_true",
                   help="Read and report, write nothing")
    a = p.parse_args(argv)

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data.store import ListingStore
    from data import db as _db

    print("database : %s" % _db.db_path(a.config))
    print("workspace: %s" % a.workspace)
    print("sheet    : %s%s" % (a.sheet_id, (" tab=%s" % a.tab) if a.tab else ""))
    print("mode     : %s\n" % ("DRY RUN -- nothing will be written" if a.dry_run
                               else "import"))

    gc = _gspread_client(a.service_account)
    store = ListingStore(a.workspace, config_path=a.config)

    before = store.row_count()
    res = store.import_from_sheet(gc, a.sheet_id, tab=a.tab, dry_run=a.dry_run)
    after = store.row_count()

    print("rows in sheet     : %s" % res.get("sheet_rows"))
    print("imported          : %s" % res["imported"])
    print("skipped (no SKU)  : %s" % res["skipped"])
    print("rows before/after : %d / %d" % (before, after))

    if res.get("unknown_headers"):
        print("\nColumns in the sheet that the mapping does not know, so their data "
              "was NOT imported:")
        for h in res["unknown_headers"]:
            print("   %r" % h)
        print("Add them to data/column_map.py (and the listings table) if they matter.")

    if res["errors"]:
        print("\nerrors (%d):" % len(res["errors"]))
        for e in res["errors"][:25]:
            print("   " + e)
        if len(res["errors"]) > 25:
            print("   ... and %d more" % (len(res["errors"]) - 25))

    print("\nDone. The sheet was not modified.")
    return 0 if not res["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
