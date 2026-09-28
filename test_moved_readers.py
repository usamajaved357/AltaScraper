"""Readers moved out of routes into the module that owns their table (architecture batch A6).

    domain/hourly_week.stored_items   <- routes/orders_routes._items_from_store
    listing/warnings.warnings_by_sku  <- the /listing edit route's before/after read

Same SQL, same parameters. This pins what they return on a fixture database,
including the str() the orders reader always applied to its keys.
"""
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import os, sys, json, tempfile
sys.path.insert(0, _REPO)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


TMP = tempfile.mkdtemp(prefix="altareaders_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "r.db")

from data import db as _db
from domain import hourly_week as HW
from listing import warnings as W

conn = _db.get_db(CFG)
HW.store_lines(CFG, "ws1", "UK", [
    {"order_id": "111-1", "asin": "B0A", "sku": "S-A", "title": "Lamp", "units": 2,
     "purchase_date": "2026-08-01T10:00:00Z"},
    {"order_id": "111-1", "asin": "B0B", "sku": "S-B", "title": "Shade", "units": 1,
     "purchase_date": "2026-08-01T10:00:00Z"},
    {"order_id": "222-2", "asin": "B0C", "sku": "S-C", "title": "Other", "units": 1,
     "purchase_date": "2026-08-02T10:00:00Z"},
])
got = sorted((r["asin"], r["sku"], r["title"], r["units"])
             for r in HW.stored_items(CFG, "ws1", "UK", "111-1"))
check("one order's lines", got, [("B0A", "S-A", "Lamp", 2), ("B0B", "S-B", "Shade", 1)])
check("  not another marketplace's", list(HW.stored_items(CFG, "ws1", "US", "111-1")), [])
check("  None keys read as '' (as the route's str() did)",
      list(HW.stored_items(CFG, None, None, None)), [])

from data import queued_store as _qs
_qs.ensure_columns(CFG)      # the warnings column, as recompute_workspace makes it
for sku, w in (("S1", '["dup"]'), ("S2", None), ("S3", "")):
    conn.execute("INSERT INTO listings (workspace_id, sku, warnings) VALUES (?,?,?)", ("ws1", sku, w))
conn.execute("INSERT INTO listings (workspace_id, sku, warnings) VALUES (?,?,?)", ("ws2", "S9", '["x"]'))
conn.commit()
got = sorted((r["sku"], r["warnings"]) for r in W.warnings_by_sku(CFG, "ws1"))
check("every row of the workspace, and only it", got,
      [("S1", '["dup"]'), ("S2", None), ("S3", "")])

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nthe moved readers answer as the routes' own queries did")
