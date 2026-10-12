"""The Repricer shows what each unit REALLY left, beside the next sale.

    OWNER, 12 Oct 2026, asked which cost the Repricer's profit should use, chose
    "Supplier price today": relabelled "Profit on your next sale", with the
    real profit shown beside it.

contribution.recent_per_unit is that real figure: each product's contribution
over the last 30 days (after fees, its cost, refunds and its own ads -- the
Finance screen's by_product_orders) divided by the units sold. Never raises.
"""
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from domain import contribution as C            # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


seen = {}


def fake(config_path, ws, mkt, start, end, vat_rate=None):
    seen["window"] = (start, end)
    return ([{"asin": "B0FAN", "units": 4, "contribution": 30.0,
              "uncosted_units": 1},
             {"asin": "B0ROLL", "units": 0, "contribution": None},
             {"asin": "B0AIR", "units": 2, "contribution": None}], {})


C.by_product_orders = fake
import domain.order_cogs as _oc                  # noqa: E402
_oc.ensure_costed = lambda *a, **k: {}

got = C.recent_per_unit("cfg", "acct", "UK", 30, today=dt.date(2026, 10, 12))
check("30 days, today included", seen["window"], ("2026-09-13", "2026-10-12"))
check("profit per unit = contribution / units", got["B0FAN"]["profit_per_unit"], 7.5)
check("  and the too-high count travels with it", got["B0FAN"]["uncosted_units"], 1)
check("a product with no units is left out", "B0ROLL" in got, False)
check("a product with no figure is left out, not shown as 0", "B0AIR" in got, False)


def boom(*a, **k):
    raise RuntimeError("db gone")


C.by_product_orders = boom
check("a failure gives nothing, never an exception",
      C.recent_per_unit("cfg", "acct", "UK"), {})

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
