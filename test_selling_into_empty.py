"""Selling faster than the stock lasts.

Orbit's brand agent names this as the cross-domain join worth having -- it calls
it "ads spending into stockout" and reaches it by crossing low-stock ASINs
against top-spend ones. The advertising half needs the Advertising API, which is
not connected. The half that IS answerable is the more important one: a product
selling faster than its cover.

WHY IT DEPENDS ON THE OOS-ADJUSTED PACE. On a flat units/days average, a product
that keeps running out looks like a SLOW seller -- the stockout days drag the
average down -- which is precisely backwards, and would leave this check silent
on exactly the products it exists to find.

TWO CONDITIONS, not one. Low cover on something that sells once a quarter is not
urgent, and listing it would bury the ones that are.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from domain import daily_check as DC

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def row(sku, cover, pace):
    return {"sku": sku, "days_of_cover": cover, "pace_30d": pace}


def run(rows, days=30):
    return DC.check_selling_into_empty(
        {"coverage": {"rows": rows, "history": {"days": days}}})


print("== it finds what runs out soon AND is moving ==")
r = run([row("FAST-LOW", 3.2, 4.0), row("SLOW-LOW", 5.0, 0.1),
         row("FAST-DEEP", 90.0, 4.0)])
check("one product flagged", r["value"], "1")
check("  and it is off-track", r["status"], DC.OFF)
truthy("  it names the one that matters", "FAST-LOW" in r["detail"])
# A product with five days left that sells one every ten days is not urgent.
truthy("  a slow seller with low cover is not raised", "SLOW-LOW" not in r["detail"])
truthy("  and neither is a fast seller with deep cover",
       "FAST-DEEP" not in r["detail"])
truthy("  it says the pace was measured on in-stock days",
       "actually in stock" in r["detail"])
truthy("  and points somewhere", "Real pace & cover" in r["action"])

print("\n== the worst one leads, and the rest are counted ==")
r2 = run([row("A", 9.0, 2.0), row("B", 1.5, 3.0), row("C", 12.0, 1.0)])
check("all three flagged", r2["value"], "3")
truthy("  the one closest to empty is named", "B" in r2["detail"])
truthy("  the others are counted, not listed", "2 more" in r2["detail"])

print("\n== nothing urgent is a real answer, not silence ==")
r3 = run([row("A", 60.0, 2.0)])
check("status is ok", r3["status"], DC.OK)
check("  and it says zero", r3["value"], "0")
truthy("  with the rule it applied", "fortnight" in r3["detail"])

print("\n== it will not judge without a measured pace ==")
# Every row unrated: the history is too thin for any pace at all.
r4 = run([{"sku": "A", "days_of_cover": None, "pace_30d": None}], days=2)
check("reported as could-not-look, not as fine", r4["status"], DC.UNKNOWN)
truthy("  and says how many days of history there were", "2 day(s)" in r4["detail"])
# Missing entirely is different again from present-but-thin.
r5 = DC.check_selling_into_empty({})
check("no coverage data at all is also unknown", r5["status"], DC.UNKNOWN)
truthy("  and names what it needed", "pace history" in r5["needs"])

print("\n== it is wired into the round, and fed ==")
truthy("the check runs", DC.check_selling_into_empty in DC.CHECKS)
ROUTES = open(os.path.join(HERE, "routes", "daily_routes.py"), encoding="utf-8").read()
truthy("the route supplies coverage", 'ctx["coverage"] = _sm.for_account' in ROUTES)
# A failed feed must leave the key ABSENT so the check says "could not look".
truthy("  and leaves it out entirely when it fails",
       'notes.append("coverage:' in ROUTES)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
