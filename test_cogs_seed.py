"""migrate_sku_costs -- seeding the product costs, exactly once.

WHY THIS EXISTS AT ALL. The cost used to be read out of the SKU:
`15.10_2Days_B0F7D29MFZ` was taken to cost 15.10. That is gone -- a cost is
something the owner sets. But measured before the change, EVERY cost in the
database came from that parse (50 of 50 costed order lines) and the product
store held one entry, so removing it alone would have taken profit, margin and
break-even ACOS to "not known" on every screen at once.

So the values are copied into the product store first. Two things have to be
true about that, and both are checked here.

IT MUST RUN ON EVERY DATABASE, not just the one on a laptop. The deployed
instance has its own and nobody has a shell on it, so this runs at start-up.

AND IT MUST RUN ONLY ONCE. "Idempotent" in the sense that matters here is not
"writes the same value twice harmlessly" -- it is "does not undo a decision".
Somebody who deletes a cost they have decided is wrong must not find it back
after the next restart.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

TMP = tempfile.mkdtemp(prefix="cogsseed_")
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t.db")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write('{"accounts": [{"id": "acct"}]}')

from data import db as _db                        # noqa: E402
from domain import cogs_store as _store           # noqa: E402
from domain import cogs as _cogs                  # noqa: E402
import migrate_sku_costs as M                     # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


conn = _db.get_db(CFG)
for sku in ("15.10_2Days_B0F7D29MFZ",      # parses, and has sold
            "8.49_3Days_B083HN61GL",       # parses, and has sold
            "AltaboltaVoo Ceiling Fan",    # hand-named: no number to read
            "0.00_3Days_B0ZEROZERO"):      # 0.00 means unknown, not free
    conn.execute(
        "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
        "purchase_date, asin, sku, units, revenue, currency) "
        "VALUES ('acct','UK',?,?,?,?,1,29.99,'GBP')",
        ("O-" + sku[:8], "2026-08-10T00:00:00Z", "B0TEST0001", sku))
conn.commit()

print("\nthe seed writes the costs the SKU parse used to supply")
check("nothing is stored to begin with", len(_store.load(CFG) or {}), 0)
res = M.run_once(CFG)
check("it ran", res.get("ran"), True)
check("  and wrote the two SKUs that carry a number", res.get("wrote"), 2)
ov = _store.load(CFG) or {}
check("the store now holds them", len(ov), 2)
check("  at the value the SKU carried", ov.get("acct::15.10_2Days_B0F7D29MFZ"),
      15.10)

print("\nand they resolve as costs the owner SET, not as SKU-derived ones")
cost, src = _cogs.resolve(ov, "acct", "15.10_2Days_B0F7D29MFZ")
check("the cost comes back", cost, 15.10)
# THE SOURCE MATTERS. It is 'manual' -- a cost on the books, editable, and not
# a number quietly re-derived from a filename on every read.
check("  and is owned, not inferred", src, "manual")

print("\nwhat it deliberately leaves alone")
check("a hand-named SKU gets no cost invented for it",
      "acct::AltaboltaVoo Ceiling Fan" in ov, False)
# 0.00 has always meant "the generator had no cost to write", not "free".
check("0.00 is not seeded as a cost of nothing",
      "acct::0.00_3Days_B0ZEROZERO" in ov, False)

print("\nit runs ONCE, and a deleted cost stays deleted")
truthy("the run is recorded against this database", M.already_ran(CFG))
# THE ONE THAT MATTERS. Somebody decides 15.10 is wrong and removes it.
_store.set_cost(CFG, "acct", "15.10_2Days_B0F7D29MFZ", None)
check("the cost is gone", "acct::15.10_2Days_B0F7D29MFZ" in
      (_store.load(CFG) or {}), False)
again = M.run_once(CFG)
check("a second run does nothing", again.get("ran"), False)
truthy("  and says why", "already" in str(again.get("why")))
check("the deleted cost is STILL gone", "acct::15.10_2Days_B0F7D29MFZ" in
      (_store.load(CFG) or {}), False)

print("\na cost already set is never overwritten by the seed")
# A fresh database, with one cost already typed at a different value.
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t2.db")
_db.close_db()
CFG2 = os.path.join(TMP, "config2.json")
open(CFG2, "w", encoding="utf-8").write('{"accounts": [{"id": "acct"}]}')
conn2 = _db.get_db(CFG2)
conn2.execute(
    "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
    "purchase_date, asin, sku, units, revenue, currency) "
    "VALUES ('acct','UK','O-1','2026-08-10T00:00:00Z','B0T','"
    "15.10_2Days_B0F7D29MFZ',1,29.99,'GBP')")
conn2.commit()
_store.load(CFG2, force=True)
_store.set_cost(CFG2, "acct", "15.10_2Days_B0F7D29MFZ", 9.99)
M.run_once(CFG2)
ov2 = _store.load(CFG2) or {}
check("the typed cost survives the seed",
      ov2.get("acct::15.10_2Days_B0F7D29MFZ"), 9.99)

_db.close_db()
os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    for f in fails:
        print("  FAILED:", f)
    sys.exit(1)
print("all passed")
