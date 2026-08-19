"""A stockout day is not a day of no demand.

    Steven, Orbit's inventory agent, on its own method:
    "OOS days are excluded from the OOS-adjusted pace calculation -- that is the
     adjustment. We do not count an out-of-stock day as a zero-sales day, so it
     does not understate true demand."

That is the difference this file exists to pin. A product that sold 30 units in
a month while being out of stock for twenty of those days is not selling one a
day. It is selling three a day and losing two thirds of the month.

    flat average      30 units / 30 days = 1.0 a day
    OOS-adjusted      30 units / 10 in-stock days = 3.0 a day

Everything downstream inherits that error: days of cover is three times too
long, the thirty-day forecast is a third of the truth, and a product that needs
ordering today looks fine for a month.

Amazon keeps no stock history for a merchant-fulfilled seller, so the app
records it (domain/stock_history.py). The metrics say how many days they
actually had, and refuse to report a pace built on too few.
"""
import datetime as _dt
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="stockmetrics_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write(json.dumps({"data_backend": "db"}))

from data import db as _db                                    # noqa: E402
from domain import stock_history as SH                        # noqa: E402
from domain import stock_metrics as SM                        # noqa: E402

conn = _db.get_db(CFG)

WS, MKT = "testco", "UK"
END = "2026-08-30"
DAYS = [( _dt.date.fromisoformat(END) - _dt.timedelta(days=i)).isoformat()
        for i in range(29, -1, -1)]           # 30 days, oldest first

# SKU A: in stock for 10 of the 30 days, sold 30 units on those days.
# SKU B: in stock every day, sold 30 units, and holds enough to cover a month.
# Both sold the SAME total. Only the pace should differ.
for i, d in enumerate(DAYS):
    a_qty = 5 if i >= 20 else 0               # last 10 days in stock
    SH.record(CFG, WS, MKT, [
        {"sku": "A", "asin": "B0A", "qty": a_qty, "status": "Active",
         "fulfillment": "DEFAULT"},
        {"sku": "B", "asin": "B0B", "qty": 40, "status": "Active",
         "fulfillment": "DEFAULT"},
    ], when=d)

with conn:
    for i, d in enumerate(DAYS):
        if i >= 20:
            conn.execute(
                "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
                "purchase_date, asin, sku, units, revenue, currency) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (WS, MKT, "o%d" % i, d + "T10:00:00Z", "B0A", "A", 3, 30, "GBP"))
        conn.execute(
            "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
            "purchase_date, asin, sku, units, revenue, currency) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (WS, MKT, "p%d" % i, d + "T10:00:00Z", "B0B", "B", 1, 10, "GBP"))

out = SM.for_account(CFG, WS, MKT, window=30, today=END)
rows = {r["sku"]: r for r in out["rows"]}
A, B = rows["A"], rows["B"]

print("== the same 30 units, two very different products ==")
check("both sold 30 units", (sum(1 for _ in DAYS[20:]) * 3, len(DAYS) * 1), (30, 30))
check("A was in stock for 10 days", A["days_known"] - A["oos_days"], 10)
check("B was in stock for 30 days", B["days_known"] - B["oos_days"], 30)
# THE POINT. A flat average would call both of these 1.0 a day.
check("A's pace is 3.0 a day, not 1.0", A["pace_30d"], 3.0)
check("B's pace is 1.0 a day", B["pace_30d"], 1.0)
check("  and A's pace was computed over its 10 in-stock days", A["pace_30d_days"], 10)

print("\n== and everything downstream follows from it ==")
check("A's 30-day demand is 90, not 30", A["forecast_demand_30d"], 90.0)
check("A has 5 on hand", A["on_hand"], 5)
check("  so cover is 1.7 days", A["days_of_cover"], 1.7)
check("  and the gap is 85 units", A["stock_gap_30d"], 85.0)
check("A needs attention", A["status"], "needs_attention")
check("B is covered", B["status"], "ok")
check("A's in-stock rate is 33.3%", A["in_stock_rate"], 33.3)

print("\n== out of stock is a fact, not a forecast ==")
SH.record(CFG, WS, MKT, [{"sku": "C", "asin": "B0C", "qty": 0,
                          "status": "Active", "fulfillment": "DEFAULT"}],
          when=END)
out2 = SM.for_account(CFG, WS, MKT, window=30, today=END)
C = {r["sku"]: r for r in out2["rows"]}["C"]
check("nothing sellable reads as out of stock", C["status"], "out_of_stock")
check("  and it is not dressed up as a pace", C["pace_30d"], None)

print("\n== a pace is refused when the history is too thin ==")
TMP2 = tempfile.mkdtemp(prefix="stockthin_")
CFG2 = os.path.join(TMP2, "config.json")
open(CFG2, "w", encoding="utf-8").write(json.dumps({"data_backend": "db"}))
_db.close_db()
SH.record(CFG2, WS, MKT, [{"sku": "D", "qty": 4, "status": "Active"}], when=END)
thin = SM.for_account(CFG2, WS, MKT, window=30, today=END)
D = {r["sku"]: r for r in thin["rows"]}["D"]
check("one day of history gives no pace", D["pace_30d"], None)
check("  and the status says so, rather than guessing", D["status"], "unknown")
truthy("  in words", "Not enough recorded history" in D["why"])
truthy("the response says how much history there is",
       "day(s) so far" in thin["note"])
check("  and how many days it needs", SM.MIN_DAYS_FOR_PACE, 7)

print("\n== a gap is not a purchase order, and says so ==")
truthy("stated on every response", "not a purchase order" in out["gap_is_not_a_po"])
truthy("  and no order quantity is offered anywhere",
       not any("order_qty" in r or "reorder_qty" in r for r in out["rows"]))

print("\n== a day we never recorded is unknown, not a stockout ==")
# Inventing a stockout out of a gap in our own recording would invent lost
# sales that never happened.
marks = SH.in_stock_days({"2026-08-01": 3}, ["2026-08-01", "2026-08-02"])
check("the recorded day is known", marks["known"], ["2026-08-01"])
check("  the missing day is not counted out of stock", marks["oos"], [])

_db.close_db()
shutil.rmtree(TMP, ignore_errors=True)
shutil.rmtree(TMP2, ignore_errors=True)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
