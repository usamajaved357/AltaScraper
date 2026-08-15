"""Profit on orders PLACED, from the seller's own cost prices.

THE REPORT: "Total Sales GBP 0" beside "Profit GBP 80". Both were right and they
described different trades -- Amazon dates sales by when the order was PLACED and
profit by when the MONEY MOVED, so a week whose orders had not settled showed
this week's sales next to last month's profit.

Amazon reports no profit against an unsettled order. The owner can: "yes use my
cost prices for profit".

WHAT IS BEING PINNED HERE
  revenue    = item price + the postage the buyer paid
  - VAT      where the company is registered (Amazon's figures include it)
  - fees     at the rate THIS account actually pays, measured from its own
             settled history
  - stock    frozen onto the order at the price in force WHEN IT ARRIVED
  - charges  postage out, prep, a hand-allocated ad figure
  - ads      only when the Advertising API is connected

and the rule the owner asked for on missing costs: do not subtract anything,
show the figure, and make it obvious it is too high.
"""
import os, sys, json, tempfile, shutil

sys.path.insert(0, r"D:\AltaScraper")

import domain.order_profit as op
import domain.order_cogs as oc
import domain.asin_charges as ac
from data import db as _db

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altaprof_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "jack_uk", "vat_rate": 0.2, "cogs_mode": "tracked"},
                        {"id": "plain_co", "vat_rate": 0}]}, open(CFG, "w"))
WS, MKT = "jack_uk", "UK"

# Three orders of one item: 29.99 of goods + 4.08 postage each, as Amazon really
# returned them.
LINES = [{"order_id": "A%d" % i, "sku": "7.00_3Days_B0G1K5B7QS",
          "asin": "B0G1K5B7QS", "units": 1, "revenue": 29.99, "shipping": 4.08,
          "cogs": 7.00, "purchase_date": "2026-08-14T18:0%d:00Z" % i}
         for i in range(3)]

print("\n== the sum, with every part visible ==")
r = op.for_lines(LINES, rate=0.15, vat_rate=0.2)
check("revenue is everything the buyer paid", r["revenue"], 102.21)
check("  of which goods", r["goods"], 89.97)
check("  of which postage", r["postage"], 12.24)
check("VAT comes out first -- it was never yours", r["vat"], 17.04)
check("leaving net revenue", r["net_revenue"], 85.17)
check("fees are charged on the NET, not on the VAT", r["fees"], round(85.17 * 0.15, 2))
check("stock cost is 3 x 7.00", r["cogs"], 21.0)
check("profit is what is left", r["profit"],
      round(85.17 - round(85.17 * 0.15, 2) - 21.0, 2))
check_true("and a margin against net revenue", r["margin_pct"] is not None)
check("every unit was costed, so it is complete", r["complete"], True)
check("and there is nothing to warn about", r["warning"], "")

print("\n== a company that is not VAT registered keeps the lot ==")
r0 = op.for_lines(LINES, rate=0.15, vat_rate=0)
check("no VAT taken out", r0["vat"], 0)
check("net revenue is the whole revenue", r0["net_revenue"], 102.21)
check_true("so profit is higher than the registered company's",
           r0["profit"] > r["profit"])

print("\n== a missing cost is NOT treated as zero silently ==")
# The owner's rule: do not subtract, show the figure, say it is wrong.
mixed = [dict(LINES[0]), dict(LINES[1]), dict(LINES[2])]
mixed[2]["cogs"] = None
rm = op.for_lines(mixed, rate=0.15, vat_rate=0.2)
check("only the costed units are subtracted", rm["cogs"], 14.0)
check("the uncosted units are counted", rm["missing_units"], 1)
check("and named", rm["missing_skus"], ["7.00_3Days_B0G1K5B7QS"])
check_true("the figure is declared too high, in words",
           "HIGHER than the truth" in rm["warning"])
check_true("  and says how many", "1 of 3 units" in rm["warning"])
check_true("  and what to do", "Set a cost" in rm["warning"])
check("it is not marked complete", rm["complete"], False)
check_true("and it IS higher than the fully costed figure", rm["profit"] > r["profit"])

print("\n== ad spend is subtracted only when it is known ==")
ra = op.for_lines(LINES, rate=0.15, vat_rate=0.2)
check("nothing is assumed while Advertising is not connected",
      ra.get("ad_spend"), None)

print("\n== the fee rate is measured from this account, not assumed ==")
rate, basis, detail = op.fee_rate(CFG, WS, MKT, "2026-08-15")
check("with no settled history it says it is assuming", basis, "assumed")
check("  and uses Amazon's usual rate", rate, op.DEFAULT_REFERRAL_RATE)
check_true("  and says so in words", "no settled history" in detail)

conn = _db.get_db(CFG)
conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin,"
             " referral_fees, fba_fees, other_fees, principal) "
             "VALUES (?,?,?,?,?,?,?,?)",
             (WS, MKT, "2026-07-20", "*", 30.0, 20.0, 0.0, 400.0))
conn.commit()
rate2, basis2, detail2 = op.fee_rate(CFG, WS, MKT, "2026-08-15")
check("with history it measures", basis2, "measured")
check("  50 of fees on 400 of sales is 12.5%", rate2, 0.125)
check_true("  and says what it measured", "actually charged" in detail2)

print("\n== a FIXED monthly charge is not a per-sale fee ==")
# From the owner's own exported CSV, 2026-08-14: 25.00 of "other fees" against
# 0.00 of sales that day -- the monthly Professional selling subscription.
# Counted as a rate it turned a real 17.5% into 24.1%, and that came off every
# estimated profit as though the subscription scaled with revenue.
conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin,"
             " referral_fees, fba_fees, other_fees, principal) "
             "VALUES (?,?,?,?,?,?,?,?)",
             (WS, MKT, "2026-08-14", "*", 0.0, 0.0, 25.0, 0.0))
conn.commit()
rate3, _b3, detail3 = op.fee_rate(CFG, WS, MKT, "2026-08-15")
check("the subscription does NOT move the rate", rate3, 0.125)
check_true("  but it is named, not hidden", "fixed charges" in detail3)
check_true("  with the amount", "25.00" in detail3)

print("\n== the cost is frozen at the price in force WHEN THE ORDER ARRIVED ==")
# The owner's example: 7 until 2am, then 9, then 11. An order at 00:30 costs 7.
conn.execute("INSERT INTO sourcing_sources (id, workspace_id, marketplace, sku,"
             " url, enabled, priority) VALUES (1,?,?,?,?,1,10)",
             (WS, MKT, "7.00_3Days_B0G1K5B7QS", "http://x"))
for at, price in (("2026-08-12T00:00:00Z", 7.0),
                  ("2026-08-12T02:00:00Z", 9.0),
                  ("2026-08-12T04:00:00Z", 11.0)):
    conn.execute("INSERT INTO sourcing_checks (source_id, checked_at, status,"
                 " price, shipping) VALUES (1,?,'fetched',?,0)", (at, price))
conn.commit()

c1 = oc.tracked_cost(CFG, WS, MKT, "7.00_3Days_B0G1K5B7QS", "2026-08-12T00:30:00Z")
check("an order at 00:30 costs the 7.00 that was in force", c1, 7.0)
c2 = oc.tracked_cost(CFG, WS, MKT, "7.00_3Days_B0G1K5B7QS", "2026-08-12T03:00:00Z")
check("an order at 03:00 costs 9.00, the price then", c2, 9.0)
c3 = oc.tracked_cost(CFG, WS, MKT, "7.00_3Days_B0G1K5B7QS", "2026-08-11T23:00:00Z")
check("an order BEFORE any reading has no tracked cost", c3, None)

print("\n== unknown postage is not free postage ==")
conn.execute("INSERT INTO sourcing_sources (id, workspace_id, marketplace, sku,"
             " url, enabled, priority) VALUES (2,?,?,?,?,1,10)",
             (WS, MKT, "NOSHIP", "http://y"))
conn.execute("INSERT INTO sourcing_checks (source_id, checked_at, status,"
             " price, shipping) VALUES (2,'2026-08-12T00:00:00Z','fetched',5.0,NULL)")
conn.commit()
check("a source with unknown postage gives no cost, rather than a low one",
      oc.tracked_cost(CFG, WS, MKT, "NOSHIP", "2026-08-13T00:00:00Z"), None)

print("\n== the two modes ==")
check("the account's mode is read from config", oc.mode_for(lambda: json.load(open(CFG)), WS),
      "tracked")
check("an account that has not chosen gets the simple one",
      oc.mode_for(lambda: json.load(open(CFG)), "plain_co"), "sku")
cost, src = oc.resolve(CFG, WS, MKT, "7.00_3Days_B0G1K5B7QS",
                       "2026-08-12T00:30:00Z", oc.MODE_TRACKED)
check("tracked mode uses the supplier price", (cost, src), (7.0, "tracked"))
cost2, src2 = oc.resolve(CFG, WS, MKT, "7.00_3Days_B0G1K5B7QS",
                         "2026-08-12T00:30:00Z", oc.MODE_SKU)
check("sku mode uses the cost written in the SKU", (cost2, src2), (7.0, "sku"))

print("\n== a correction to ONE order beats everything, and stays there ==")
cost3, src3 = oc.resolve(CFG, WS, MKT, "7.00_3Days_B0G1K5B7QS",
                         "2026-08-12T00:30:00Z", oc.MODE_TRACKED,
                         order_override=6.25)
check("the typed figure wins", (cost3, src3), (6.25, "manual-order"))

print("\n== freezing does not move what is already frozen ==")
conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id,"
             " purchase_date, asin, sku, units, revenue, shipping) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (WS, MKT, "Z1", "2026-08-12T00:30:00Z", "B0G1K5B7QS",
              "7.00_3Days_B0G1K5B7QS", 1, 29.99, 4.08))
conn.commit()
f1 = oc.freeze_range(CFG, WS, MKT, "2026-08-01", "2026-08-31", oc.MODE_TRACKED)
check("the new line is costed", f1["priced"], 1)
f2 = oc.freeze_range(CFG, WS, MKT, "2026-08-01", "2026-08-31", oc.MODE_TRACKED)
check("a second pass leaves it alone", f2["priced"], 0)
check("  because it already had one", f2["already_had_one"], 1)

print("\n== charges are added on top, per unit, on the order's own date ==")
ac.save(CFG, WS, MKT, "B0G1K5B7QS", "prep", 0.50)
ac.save(CFG, WS, MKT, "B0G1K5B7QS", "postage out", 2.90)


def _charge_of(asin, sku, on_date):
    return ac.per_unit(CFG, WS, MKT, asin, sku=sku, on_date=on_date)


rc = op.for_lines(LINES, rate=0.15, vat_rate=0.2, charge_of=_charge_of)
check("3 units x 3.40 of charges", rc["charges"], 10.2)
check("and each is named", sorted(p["label"] for p in rc["charge_parts"]),
      ["postage out", "prep"])
check_true("so profit is lower than without them", rc["profit"] < r["profit"])

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
