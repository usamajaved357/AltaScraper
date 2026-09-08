"""A delete that located the row and then deleted nothing.

    "i am still not able to delete the drafted listing, no error is shown still
     the same error appears"

    "Deleted 0 listing(s) / 1 failed - 7.99_2Days_B0CGDKS28N: Nothing was
     deleted - no row in this workspace matched that SKU"

TWO MESSAGES LIVE IN /delete AND HE WAS HITTING THE OTHER ONE. The first fix
addressed "SKU not found". His error comes from the branch AFTER the row is
found: repo.locate returned a row, delete ran, and removed nothing.

THE PATH WAS A ROUND TRIP:

    SKU -> row NUMBER (repo.locate) -> back to a SKU (_sku_for_row) -> DELETE

Two separate reads of the same table with a number in between that means
nothing outside whichever ordering produced it -- and a final DELETE comparing
the SKU byte for byte. A SKU stored with a trailing space, or in a different
case from the one that came back, matched nothing. The app located the row on
one line and reported "no row matched that SKU" on the next.

Not reproducible on the local database -- all 86 SKUs there round-trip cleanly,
which is why three attempts to diagnose it from local data went nowhere. The
fix removes the round trip rather than making it more careful: the database can
delete by SKU, so the row number is not used at all when a SKU is given.
"""
import os
import shutil
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
    print("  %-64s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from data import db as _db
from data.store import ListingStore, SheetLikeStore
from listing import repo as _repo

TMP = tempfile.mkdtemp(prefix="altadelsku_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write('{"data_backend": "db"}')
_db.get_db(CFG)

st = ListingStore("ws1", config_path=CFG)
ws = SheetLikeStore(st)
conn = _db.get_db(CFG)
for s in ["CLEAN", "  PADDED  ", "MixedCase", "KEEP"]:
    conn.execute("INSERT INTO listings (workspace_id, sku, status) VALUES (?,?,?)",
                 ("ws1", s, "GENERATED"))
conn.commit()

print("=== the SKU is matched as it is WRITTEN, not byte for byte ===")
check("an exact SKU still deletes", st.delete_row("CLEAN"), 1)
# The two that used to come back 0 while the row was plainly there.
check("one stored with padding deletes", st.delete_row("PADDED"), 1)
check("one asked for in another case deletes", st.delete_row("mixedcase"), 1)
check("one that is genuinely absent still deletes nothing",
      st.delete_row("NOT_HERE"), 0)
check("and nothing else was swept up",
      [str(r.get("SKU")) for r in st.get_all_rows()], ["KEEP"])

print("\n=== an exact hit still wins over the loose pass ===")
# Two SKUs differing only in case must not both go on one call.
conn.execute("INSERT INTO listings (workspace_id, sku) VALUES (?,?)", ("ws1", "dup"))
conn.execute("INSERT INTO listings (workspace_id, sku) VALUES (?,?)", ("ws1", "DUP"))
conn.commit()
check("only the exact one goes", st.delete_row("DUP"), 1)
check("  the other survives",
      sorted(str(r.get("SKU")) for r in st.get_all_rows()), ["KEEP", "dup"])

print("\n=== the route deletes BY SKU, not by round trip ===")
L = open(os.path.join("routes", "listing_routes.py"), encoding="utf-8").read()
_del = L.split("def delete_row():")[1].split("\n    @app.route")[0]
truthy("it asks the store for a SKU delete", "_store.delete_row(sku)" in _del)
truthy("  only when a SKU was actually given", 'if sku and _store is not None' in _del)
# The row-number path SURVIVES for the sheet backend, which really does address
# rows by position -- but only as a fallback.
truthy("  the row path remains as a fallback", "_repo.delete_row(ws, target)" in _del)
truthy("    and only after the SKU delete found nothing",
       _del.index("_store.delete_row(sku)") < _del.index("_repo.delete_row(ws, target)"))
# From the earlier fix, and it must not regress: a row NUMBER is a position, so
# it is never used to delete when a SKU was named.
truthy("a named SKU is never deleted by position",
       "if target is None and row and not sku:" in _del)

print("\n=== end to end, the way the route does it ===")
for s in ["E2E_CLEAN", " E2E_PADDED ", "E2E_MixedCase"]:
    conn.execute("INSERT INTO listings (workspace_id, sku) VALUES (?,?)", ("ws1", s))
conn.commit()


def route_delete(sku):
    found = _repo.locate(ws, sku, sku_headers=("SKU",))
    target = found.row if getattr(found, "ok", False) else None
    gone = 0
    _store = getattr(ws, "store", None)
    if sku and _store is not None and hasattr(_store, "delete_row"):
        gone = int(_store.delete_row(sku) or 0)
    if not gone and target:
        gone = _repo.delete_row(ws, target)
    return gone


check("a clean SKU", route_delete("E2E_CLEAN"), 1)
check("a padded one", route_delete("E2E_PADDED"), 1)
# repo.locate normalises, so it FINDS a mis-cased SKU -- and the old DELETE
# then compared byte for byte and matched nothing. That gap between "found" and
# "deleted" is the whole bug, and it is why the screen could report "no row
# matched that SKU" about a row it had just located.
truthy("  locate finds a mis-cased SKU",
       getattr(_repo.locate(ws, "E2E_MixedCase", sku_headers=("SKU",)), "ok", False))
check("  and now it is actually deleted", route_delete("E2E_MixedCase"), 1)
check("a SKU that is not there", route_delete("E2E_GHOST"), 0)

shutil.rmtree(TMP, ignore_errors=True)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
