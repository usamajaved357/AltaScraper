"""The account you ask for is the account you get -- even when SKUs are shared.

    "no one account data should be shared with another"
    "i asked for jacks listings so jacks listings should appear, not another
     account"

MEASURED ON THE RUNNING APP, before the fix:

    /rows_all?account=jack_uk         -> 86 rows, workspace=nestwell_goods
    /rows_all?account=nestwell_goods  -> 86 rows, workspace=nestwell_goods

Both answers were Nestwell's. The route read the workspace out of _state -- the
server's process-wide "currently open account" -- and ignored the one named. The
browser half was already correct: it sends ?account=, drops a reply that arrives
after a switch, and honours a refusal.

NOT FIXED BY REFUSING. account_scope.is_mismatch() is deliberately always False,
because refusing was tried and was worse: the stale value is the GLOBAL and the
browser is the one that is right. "i switched from headbanger lures recently but
i am on nestwell goods but still i am shown this error" is that refusal
punishing a correct request. Answering the question actually asked fixes the
leak AND that.

WHY THE OLD SAFETY ARGUMENT IS GONE. /edit and /delete carried a note saying a
stale account was only a latent hazard, because "282 rows across five accounts,
282 distinct SKUs, none shared between two accounts" -- a wrong workspace would
miss and 404. The owner has withdrawn that premise: "i am also doing mee too
listings on both accounts, so ... some can share the same asin and maybe i have
set the same sku for those asins in both accounts". A shared SKU turns that 404
into an edit, or a delete, of the other company's row.

So this test does NOT rely on SKUs being unique. It creates the same SKU in two
workspaces on purpose and checks each account still gets its own row.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-68s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


SRC = open(os.path.join("routes", "listing_routes.py"), encoding="utf-8").read()

print("=== the store can be opened for a NAMED workspace ===")
truthy("there is one helper for it", "def _store_for(" in SRC)
_sf = SRC.split("def _store_for(")[1].split("    def ")[0]
truthy("  it opens that workspace's own store", "ListingStore(aid" in _sf)
# It must not invent a store for a backend that has no such thing, nor blow up
# a working screen when it cannot help.
truthy("  it declines when there is no account named", "if not aid:" in _sf)
truthy("  and when the backend is not the database", '!= "db"' in _sf)

print("\n=== the three routes that read or write a workspace's rows ===")
for name, marker in (("rows_all", "_store_for(_use_aid)"),
                     ("edit", '_store_for(b.get("account")) or _ws()'),
                     ("delete", '_store_for(b.get("account")) or _ws()')):
    truthy("%s reads the named workspace" % name, marker in SRC)
# Two of those are WRITES, which is why they matter more than the read.
check("both writes use it", SRC.count('_store_for(b.get("account")) or _ws()'), 2)
# The reply has to name the workspace actually read, or the browser's own check
# ("is this reply for the account I asked about?") agrees with itself always.
truthy("the reply reports the workspace it read",
       '"workspace": str(_use_aid or "_no_account")' in SRC)

print("\n=== a SKU shared between two accounts still resolves per account ===")
import sqlite3
import tempfile
from data.store import ListingStore

tmp = tempfile.mkdtemp()
cfgp = os.path.join(tmp, "config.json")
open(cfgp, "w", encoding="utf-8").write('{"data_backend": "db"}')

SHARED = "9.99_3Days_B0SHAREDASIN"
try:
    a = ListingStore("acct_a", config_path=cfgp)
    b = ListingStore("acct_b", config_path=cfgp)
    a.upsert_row({"SKU": SHARED, "Title": "A's listing"})
    b.upsert_row({"SKU": SHARED, "Title": "B's listing"})
    ra = [r for r in a.get_all_rows() if r.get("SKU") == SHARED]
    rb = [r for r in b.get_all_rows() if r.get("SKU") == SHARED]
    check("account A sees one row for the shared SKU", len(ra), 1)
    check("  and it is A's", (ra[0].get("Title") if ra else None), "A's listing")
    check("account B sees one row for the shared SKU", len(rb), 1)
    check("  and it is B's", (rb[0].get("Title") if rb else None), "B's listing")
    # THE WHOLE POINT: the same SKU, two accounts, two different rows. Nothing
    # about a SKU tells you whose listing it is.
    check("the two are different rows",
          (ra[0].get("Title") if ra else 1) != (rb[0].get("Title") if rb else 2),
          True)
except Exception as e:
    print("  (could not exercise the store directly: %s)" % str(e)[:200])
    FAILS.append("shared-SKU store check did not run")

print("\n=== the old premise is recorded as withdrawn, not just deleted ===")
# The next person to read /edit must not re-derive "SKUs are unique so this is
# safe" from the note that used to say so.
truthy("edit says why the uniqueness argument no longer holds",
       "no longer holds" in SRC.lower() or "withdrawn" in SRC.lower())
truthy("  and names me-too listings as the reason",
       "mee too" in SRC or "me-too" in SRC)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
