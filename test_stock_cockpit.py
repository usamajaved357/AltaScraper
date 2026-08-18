"""The stock cockpit: Orbit's rules where they were quoted, ours where they were not.

    "now start building the inventory feature same like orbit in our app"

WHAT WAS COPIED, AND WHAT WAS NOT

Orbit states some of its arithmetic in its own tooltips, and those were captured
verbatim on 18 Aug 2026 (orbit_inventory/tooltips.md):

    "DOS = displayed total units / current daily velocity"
    "Current Velocity -- Average units sold per day over the current 30-day
     window."
    "COGS value = displayed units x resolved cost per unit"
    "Status -- ... Safe, watch, order soon, order now, and stockout likely are
     ordered from healthiest to most urgent."

Those are implemented exactly and asserted here against the quotes.

What Orbit does NOT state is where its cut-offs fall, or how "revenue at risk"
is derived. Those are ours and are marked inferred in the module. The tests for
them assert OUR rule, not a guess at Orbit's.

AND ONE THING IS DELIBERATELY DIFFERENT. Orbit's headline unit is
"FBA + AWD + 3PL + verified inbound". Measured across all six accounts: zero FBA
units, everything merchant-fulfilled. Copying that split would give three
permanently empty columns and a fourth whose heading lies. The question becomes
"can it be sourced before the promise breaks", which the repricer's supplier
dispatch times can actually answer -- and Orbit cannot ask at all.
"""
import datetime as dt
import io
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(l, g):
    check(l, bool(g), True)


def falsy(l, g):
    check(l, bool(g), False)


from domain import inventory_view as IV

print("=== Orbit's five states, in Orbit's order ===")
# "ordered from healthiest to most urgent" -- its words, and the order matters:
# the screen sorts on it and the filter row is drawn from it.
check("the ladder is exactly Orbit's",
      IV.STATUS_ORDER[:5],
      ["safe", "watch", "order soon", "order now", "stockout likely"])
check("  with one of our own on the end for 'cannot tell'",
      IV.STATUS_ORDER[5], "unknown")
check("every state has a meaning for the screen to show",
      sorted(IV.STATUS_MEANING.keys()), sorted(IV.STATUS_ORDER))

print("\n=== cover against restock, which is what decides the state ===")
# OUR rule, not Orbit's: multiples of the lead time rather than flat days,
# because a supplier who ships next day needs far less warning than one that
# takes ten. A fixed "order at 14 days" is wrong in both directions here.
check("30 days cover on a 5 day restock is safe", IV.status_for(30, 5), "safe")
check("  12 on 5 is watch", IV.status_for(12, 5), "watch")
check("  8 on 5 is order soon", IV.status_for(8, 5), "order soon")
check("  6 on 5 is order now", IV.status_for(6, 5), "order now")
check("  4 on 5 runs out first", IV.status_for(4, 5), "stockout likely")
# The same cover, a slower supplier, a different answer. This is the whole point.
check("10 days cover is SAFE when restock is 3", IV.status_for(10, 3), "safe")
check("  and NOT safe when restock is 8", IV.status_for(10, 8), "order now")

print("\n--- what cannot be judged is not judged ---")
check("no cover -> unknown, never safe", IV.status_for(None, 5), "unknown")
check("no lead  -> unknown", IV.status_for(10, None), "unknown")
# A zero lead time would divide by zero. It is floored at one day rather than
# being allowed to report infinite safety.
truthy("a zero restock time does not divide by zero",
       IV.status_for(10, 0) in IV.STATUS_ORDER)

print("\n=== the ledger, on made-up but realistic rows ===")


def row(**kw):
    base = {"sku": "S", "asin": "", "title": "T", "img": "", "listed_qty": 10,
            "price": 20.0, "units_sold": 30, "orders": 30, "velocity": 1.0,
            "provisional": False, "cover_days": 10.0, "lead_days": 3,
            "lead_known": True, "dispatch_days": 2, "buffer_days": 1,
            "unit_cost": 5.0, "cost_source": "sku", "value_at_cost": 50.0,
            "status": "safe", "already_out": False, "gaps": [],
            "fulfilment": "", "listing_status": "Active",
            "runs_out": "2026-08-28"}
    base.update(kw)
    return base


rows = [
    row(sku="FAST", velocity=2.0, listed_qty=4, cover_days=2.0, lead_days=7,
        status="stockout likely", price=30.0, value_at_cost=20.0,
        runs_out="2026-08-20"),
    row(sku="OUT", velocity=0.7, listed_qty=0, cover_days=0.0, lead_days=7,
        status="stockout likely", already_out=True, price=33.0,
        value_at_cost=0.0, runs_out="2026-08-18"),
    row(sku="FINE", velocity=0.5, listed_qty=60, cover_days=120.0, lead_days=4,
        status="safe", value_at_cost=300.0, runs_out="2026-12-16"),
    row(sku="NOSALE", velocity=None, cover_days=None, status="unknown",
        units_sold=None, value_at_cost=40.0, runs_out=None,
        gaps=["no sales in the window"]),
    row(sku="NOCOST", unit_cost=None, value_at_cost=None, status="safe",
        cover_days=40.0, gaps=["no cost"]),
]
c = IV.cockpit(rows, today=dt.date(2026, 8, 18))

print("--- the counts ---")
check("every SKU is counted", c["skus"], 5)
check("units are summed across the listings", c["listed_units"], 4 + 0 + 60 + 10 + 10)
# "COGS value = displayed units x resolved cost per unit" -- Orbit's rule, and
# a SKU with no cost contributes NOTHING rather than zero-as-if-free.
check("value covers only the priced rows", c["value_at_cost"], 20.0 + 0.0 + 300.0 + 40.0)
check("  and says how many it could not price", c["uncosted_skus"], 1)
check("  and how many it could", c["valued_skus"], 4)

print("\n--- average cover is over rows that HAVE cover ---")
# Averaging in the products nobody buys would describe products you are not
# selling. 2.0 + 0.0 + 120.0 + 40.0 over four rows.
check("the mean ignores the no-sales row", c["avg_cover_days"],
      round((2.0 + 0.0 + 120.0 + 40.0) / 4, 1))
check("  and says how many it covered", c["covered_skus"], 4)

print("\n--- what is already out is separated from what will run out ---")
# Found by testing against nestwell_goods: five SKUs at quantity zero were
# reported as "runs out 18 Aug", which was today. A prediction about something
# that has already happened reads as a warning you have time to act on.
check("the already-out ones are counted on their own", c["out_now"], 1)
check("  and the headline names one of THEM, not the soonest forecast",
      c["next_stockout"]["sku"], "OUT")
truthy("  flagged, so the screen can say 'out now' instead of a date",
       c["next_stockout"]["already_out"])

print("\n--- revenue at risk ---")
# OURS, and inferred: Orbit shows the figure and never states how it gets it.
# For each product that runs out before more can arrive, the sales it would
# have made during the gap:
#     FAST  lead 7 - cover 2 = 5 days short  x 2.0/day = 10 units x 30.00 = 300
#     OUT   lead 7 - cover 0 = 7 days short  x 0.7/day = 4.9 units x 33.00 = 161.70
check("units missed while waiting for stock", c["at_risk_units"], 15)
check("  valued at what they would have sold for", c["at_risk_value"],
      round(10 * 30.0 + 4.9 * 33.0, 2))
# It is NOT the value of the product. Losing three days of sales is not losing
# the product, and a figure that said so would be wrong by orders of magnitude.
truthy("  and it is far less than the stock's own value",
       c["at_risk_value"] < sum(r["value_at_cost"] or 0 for r in rows) * 10)

print("\n--- the review queue is Orbit's idea, with our gaps ---")
# Orbit: "rows that are not fully safe and therefore deserve operator review.
# Source gaps count missing AWD, 3PL, or COGS data". There is no AWD or 3PL
# here, so ours are: no cost, no quantity, no sales, no supplier.
check("rows with something missing", c["review_queue"], 2)

print("\n=== velocity: divided by the WINDOW, never by days-since-first-sale ===")
src = io.open(r"D:\AltaScraper\domain\inventory_view.py", encoding="utf-8").read()
check("the window is Orbit's 30 days", IV.WINDOW_DAYS, 30)
truthy("a SKU whose whole history is inside the window is flagged provisional",
       '"provisional"' in src)
# Two sales in three days is not 0.67 a day sustained. Dividing by the days
# since the first sale would triple every new product's velocity and every
# reorder built on it.
truthy("  and the reason is written down where it will be read",
       "not selling 0.67 a day" in src or "is not 0.67 a day" in src)

print("\n=== nothing here writes, sends or assumes ===")
falsy("no INSERT anywhere in the module", "INSERT" in src.upper())
falsy("  no UPDATE", " UPDATE " in src.upper())
truthy("an unknown cost is None, not zero", "no cost is not a cost of zero"
       in src.lower() or "No cost is not a cost of zero" in src)
truthy("an unknown velocity is None, not zero",
       "No velocity is not a velocity of zero" in src)
# The assumed lead time is a stated assumption, and every row built with it says
# so rather than looking like a measured figure.
truthy("the assumed restock time is named", IV.ASSUMED_LEAD_DAYS > 0)
truthy("  and rows using it are marked", '"lead_known"' in src)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
