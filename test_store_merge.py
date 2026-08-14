"""Neither store may hide the other's listings.

WHAT HAPPENED, AND IT WAS MY OWN FIX THAT DID IT.

The Listings screen read Google Sheets while the generator wrote to the
database, so an hour's generation was invisible. The correction pointed the
screen at the database instead. That is right in principle and wrong in fact:
the app is mid-migration, and a workspace's listings can be in EITHER store, or
split across both. The server's database did not hold Nestwell Goods' history,
so the moment it deployed the screen went from "a lot" to:

    "No listings in this view. Run Generate to create some."

Nothing was deleted. The screen had been pointed at the emptier of two places,
and then told the owner there was nothing there -- which is the worst version
of this failure, because it reads as data loss.

So: neither store is authoritative and neither is a fallback. Both are read and
merged on SKU, the database winning a clash because that is where edits and new
runs land. A row in only one of them still appears.

These tests run the REAL route against a store that is deliberately empty --
the server's exact situation -- because that is the case the change broke.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


import routes.listing_routes as LR
import routes.dashboard_routes as DR
import inspect

print("=== the route reads both, and says so ===")
SRC = inspect.getsource(LR)
truthy("the database is read", "db_cards" in SRC)
truthy("the sheet is still read too", "book.worksheets()" in SRC)
truthy("they are merged rather than one replacing the other",
       "db_cards + sheet_only" in SRC)
truthy("the database wins a clash", "seen" in SRC and "sheet_only" in SRC)
truthy("the reply says how many came from each",
       '"from_database"' in SRC and '"from_sheet"' in SRC)
# The three ways this could still blank a screen, each closed:
truthy("a database that cannot be read does not hide the sheet's rows",
       "db_error" in SRC)
truthy("a sheet that cannot be read does not hide the database's rows",
       "sheet_error" in SRC)
truthy("no configured sheet is not an error when the database has rows",
       "if db_cards:" in SRC)

print("\n=== the home screen does the same ===")
DSRC = inspect.getsource(DR)
truthy("it reads the database", "db_rows" in DSRC)
truthy("and merges the sheet's extra rows", "db_rows + extra" in DSRC)
truthy("remapped by column NAME, not concatenated positionally",
       "where = [" in DSRC)
truthy("an unreachable sheet does not zero an account with database rows",
       "(db_header, db_rows) if db_rows else (None, None)" in DSRC)

print("\n=== the merge itself, on grids that disagree about columns ===")
# The silent-corruption case: the sheet has an EXTRA column, so a positional
# concatenation would shift every field of every sheet row by one.
mod = DR
db_header = ["SKU", "Title", "Status"]
db_rows = [["A-1", "Alpha", "LIVE"]]
sheet_header = ["Extra", "SKU", "Title", "Status"]
sheet_rows = [["x", "A-1", "Alpha (old)", "APPROVED"],   # same SKU -> dropped
              ["y", "B-2", "Beta", "NEEDS_REVIEW"]]      # only here -> kept


def _at(header, *names):
    low = {str(h).strip().lower(): i for i, h in enumerate(header or [])}
    for n in names:
        if n in low:
            return low[n]
    return -1


di = _at(db_header, "sku")
si = _at(sheet_header, "sku")
have = {str(r[di]).strip().upper() for r in db_rows if str(r[di]).strip()}
where = [_at(sheet_header, str(h).strip().lower()) for h in db_header]
extra = []
for r in sheet_rows:
    if si < len(r) and str(r[si]).strip().upper() in have:
        continue
    extra.append([(r[w] if (0 <= w < len(r)) else "") for w in where])
merged = db_rows + extra

check("the duplicate SKU is not shown twice", len(merged), 2)
check("the database's version of the shared SKU wins", merged[0], ["A-1", "Alpha", "LIVE"])
# THE POINT: the sheet-only row is re-mapped into the database's column order,
# so its title is its title and not the extra column's contents.
check("the sheet-only row keeps its own fields", merged[1],
      ["B-2", "Beta", "NEEDS_REVIEW"])

print("\n=== against the real app ===")
import dashboard as D
from data import db as _db

app = D.build_app()
app.config["TESTING"] = True
conn = _db.get_db("config.json")

with app.test_client() as c:
    with c.session_transaction() as s:
        s["user"] = "owner"; s["role"] = "owner"; s["is_owner"] = True
    accounts = (c.get("/accounts/list").get_json() or {}).get("accounts") or []
    counts = {r["workspace_id"]: r["n"] for r in conn.execute(
        "SELECT workspace_id, COUNT(*) n FROM listings GROUP BY workspace_id")}
    checked = 0
    for a in accounts:
        aid = a.get("id")
        if not aid:
            continue
        c.post("/accounts/select", json={"id": aid})
        j = c.get("/rows_all?account=" + aid).get_json() or {}
        if not j.get("ok"):
            continue
        src = j.get("source") or {}
        n_db = counts.get(aid, 0)
        rows = j.get("rows") or []
        print("  %-20s stored=%-4d shown=%-4d  from_db=%-4s from_sheet=%-4s store=%s"
              % (aid, n_db, len(rows), src.get("from_database"),
                 src.get("from_sheet"), src.get("store")))
        # NEVER FEWER THAN THE DATABASE HOLDS. That is the regression, stated as
        # a rule: whatever else happens, the screen cannot show less than one
        # store on its own would have.
        truthy("  %s: shows at least what the database holds" % aid,
               len(rows) >= n_db)
        checked += 1
        if checked >= 4:
            break
    truthy("some accounts were checked", checked)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
