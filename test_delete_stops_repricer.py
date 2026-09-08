"""A listing deleted from Amazon stops being priced.

    "when a item is deleted from amazon, delete it from repricer too, stop
     tracking and disarm"

The repricer would otherwise go on checking suppliers for a SKU that cannot be
sold and, if it was armed, go on trying to push prices to a listing that is not
there. Both halves matter and doing one is worse than doing neither: a SKU
unenrolled but still armed, or armed but marked gone, is a half-state somebody
has to reason about later.

The pieces already existed -- unenrol() stops it being priced, and
set_listing_state(GONE) is what disarms it, setting mode='dry_run' in the same
statement. What was missing was anything calling them when a delete succeeded.
"""
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
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import source_repo as R
from data import db as _db

TMP = tempfile.mkdtemp(prefix="altastop_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write('{"data_backend": "db"}')
_db.get_db(CFG)

W, M, SKU = "ws1", "UK", "9.99_2Days_BTEST00001"

print("=== both halves, in one call ===")
falsy("a SKU the repricer never had reports nothing done",
      R.stop_tracking(CFG, W, M, SKU))

R.enrol(CFG, W, M, SKU, mode="apply")          # enrolled AND armed
rows = [dict(r) for r in R.enrolled(CFG, W, M)]
check("enrolled to begin with", len(rows), 1)
check("  and armed", str(rows[0].get("mode")), "apply")

truthy("stopping it reports that there was something to stop",
       R.stop_tracking(CFG, W, M, SKU))

after = _db.get_db(CFG).execute(
    "SELECT enrolled, mode, listing_state FROM sourcing_enrolment "
    "WHERE workspace_id=? AND marketplace=? AND sku=?", (W, M, SKU)).fetchone()
check("  tracking is off", int(after["enrolled"]), 0)
check("  and it is DISARMED", str(after["mode"]), "dry_run")
check("  and marked gone, which is what disarmed it",
      str(after["listing_state"]), R.GONE)
# The row itself SURVIVES. Its sources, price history and rule outlive the
# listing, and a SKU deleted today may be relisted tomorrow.
truthy("the enrolment row is kept, not deleted", after is not None)
check("  so it no longer appears as enrolled", len(R.enrolled(CFG, W, M)), 0)

print("\n=== doing it twice changes nothing further ===")
truthy("it is safe to repeat", R.stop_tracking(CFG, W, M, SKU) in (True, False))
again = _db.get_db(CFG).execute(
    "SELECT enrolled, mode FROM sourcing_enrolment WHERE workspace_id=? "
    "AND marketplace=? AND sku=?", (W, M, SKU)).fetchone()
check("  still off", int(again["enrolled"]), 0)
check("  still disarmed", str(again["mode"]), "dry_run")

print("\n=== and the delete path calls it ===")
L = open(os.path.join("routes", "listing_routes.py"), encoding="utf-8").read()
truthy("the delete asks the repricer to let go",
       "_srepo.stop_tracking(" in L)
# ONLY WHEN AMAZON ACTUALLY REMOVED IT. A draft delete must not disarm a live
# listing that happens to share the SKU, and a refused delete must not either.
_ok = L.split("if res.get(\"status\") in (_al.OK, _al.GONE):")[1].split("else:")[0]
truthy("  only after Amazon confirmed the removal",
       "stop_tracking(" in _ok)
truthy("  and a bookkeeping failure never loses the delete",
       "NEVER FATAL" in _ok)
truthy("  the result is reported back", '"untracked"' in L)
JS = open(os.path.join("static", "js", "miles_template.js"), encoding="utf-8").read()
truthy("  and said on screen", "repricer stopped tracking it" in JS)

print("\n=== the delete button cannot silently do nothing ===")
# Its own regression, found by the owner: "pressing the delete listing button
# but nothing is happening". _delWarning threw while building the confirm's
# argument, so the dialog never opened.
truthy("the row lookup is defensive", "}catch(e){ live = false; }" in JS)
truthy("  a missing button does not stop the delete", "if(btn) btn.disabled=true;" in JS)
truthy("  and the bulk path is guarded the same way",
       "}catch(e){ return false; }" in JS)
falsy("  it no longer claims 'this is a draft' without a row",
      "This is a draft and was never sent to Amazon" in JS)

import shutil
shutil.rmtree(TMP, ignore_errors=True)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
