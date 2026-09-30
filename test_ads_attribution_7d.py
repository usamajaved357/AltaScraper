# -*- coding: utf-8 -*-
"""Ad sales use Amazon's 7-day window, as Seller Central shows sellers (30 Sep 2026).

Owner-approved read-only capture: on a settled week (nestwell UK, 18-24 Aug)
sales30d was 48% above sales7d, so ad sales / ACOS / ad profit read higher here
than Campaign Manager. Every Sponsored Products report type the app pulls was
re-created with 7d columns and ACCEPTED by Amazon before this change.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
fails = []


def check(label, ok):
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL"))


from api import amazon_ads as A               # noqa: E402

for name, spec in A.REPORT_TYPES.items():
    if spec.get("adProduct"):                  # Brands / Display: 14d is their longest
        continue
    cols = spec.get("columns") or []
    if any(c.startswith(("sales", "purchases")) for c in cols):
        check("%s asks for sales7d + purchases7d, not 30d" % name,
              "sales7d" in cols and "purchases7d" in cols
              and "sales30d" not in cols and "purchases30d" not in cols)
    if any(c.startswith("unitsSoldClicks") for c in cols):
        check("%s asks for unitsSoldClicks7d" % name, "unitsSoldClicks7d" in cols)
check("a row's sales are read from sales7d first", A.MAPPING["sales"][0] == "sales7d")
check("a row's orders are read from purchases7d first", A.MAPPING["orders"][0] == "purchases7d")
row = A._row({"sales7d": 72.46, "purchases7d": 4, "campaignId": "1"})
check("a 7d row maps to sales and orders", row["sales"] == 72.46 and row["orders"] == 4)
old = A._row({"sales30d": 107.45, "purchases30d": 5, "campaignId": "1"})
check("an older 30d-only row still reads (fallback)", old["sales"] == 107.45 and old["orders"] == 5)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
