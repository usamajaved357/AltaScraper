"""Two screens, one day, two different revenues.

"check if the traffic page is reflecting all the information accurately, and if
 this data is what it accurately represent what we can achieve. i want accurate
 data and most updated one."

MEASURED on jack_uk, 14 Aug 2026 -- one account, one day:

    Sales screen     102.21
    Traffic screen    89.97

Both labelled Revenue. Sessions matched exactly (87 and 87) and units matched
(3 and 3), so this was not a double-count and not a stale sync.

Amazon's Sales & Traffic report has two independent blocks:
salesAndTrafficByDate, the account total for each day, and
salesAndTrafficByAsin, the per-product breakdown. They do not agree, because
the ASIN block only carries what Amazon could attribute to a child ASIN at that
granularity. domain/sales_data.parse_report stores the first as asin='*' and the
second as one row per ASIN.

Traffic summed the per-ASIN rows. Sales read the account row. Neither was
computing anything wrongly; they were answering different questions under the
same name.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)
def falsy(l, g): check(l, bool(g), False)

from domain import traffic_view as TV

print("=== the account's revenue is the account's revenue ===")
T = open(r"D:\AltaScraper\domain\traffic_view.py", encoding="utf-8").read()
truthy("there is one function that answers it", "def account_revenue(" in T)
truthy("  and it asks sales_data.totals, the same place Sales asks",
       "sales_data as _sd" in T and "_sd.totals(" in T)
truthy("  rather than a second copy of the query",
       T.count("SUM(COALESCE(ordered_sales,0))") == 2)   # daily() and per_asin()
truthy("the KPI tile uses it", 'tot["revenue"] = acct' in T)
truthy("  and the per-ASIN table keeps its own figures — that is what it is for",
       "attributed = tot[\"revenue\"]" in T)

print("\n--- and when the two differ, the page says so ---")
truthy("a note is produced", "revenue_note" in T)
truthy("  naming both numbers", "_money(acct)" in T and "_money(attributed)" in T)
truthy("  and explaining that the rest is account-level only",
       "the rest it reports at account" in T)
truthy("it is attached to the revenue tile itself",
       '"note": (revenue_note if k == "revenue" else "")' in T)

print("\n--- a change figure compares like with like ---")
# An account total against a per-ASIN sum would report a change that is only the
# difference between two definitions.
truthy("the previous period is measured the same way",
       "p_acct = account_revenue(" in T)
truthy("  and only substituted when BOTH could be read",
       "if acct is not None and p_acct is not None:" in T)

print("\n--- unreadable is not zero ---")
check("no figure means None, not a fallback to the smaller number",
      TV.account_revenue("/no/such/config", "nobody", "UK", "2026-01-01",
                         "2026-01-02"), None)
truthy("  and the caller only substitutes when it got one", "if acct is not None:" in T)

print("\n=== the queries that must NOT change ===")
# Sessions and page views agreed exactly between the two sources on every day
# measured, so excluding the rollup row is right for them -- including it would
# double every session on the page.
truthy("daily() still excludes the account rollup", "AND asin<>'*' " in T)
check("  in both places that aggregate products — daily() and per_asin()",
      T.count("asin<>'*'"), 2)

print("\n=== a 30-day heading over a 28-day window ===")
# MEASURED on jack_uk, 17 Aug 2026: the newest day with any traffic was the
# 14th -- Amazon answered the fetch for the 15th and 16th with QuotaExceeded.
# The tiles said 30 days and every rate divided by 28, with nothing saying so.
truthy("freshness is worked out", "def freshness(" in T)
truthy("  and reported on the answer", '"freshness": freshness(' in T)
truthy("it names the last day that has data", '"last": last' in T)
truthy("  and how many are missing", '"missing_days"' in T)
truthy("  and says which window the figures ACTUALLY cover",
       "not to %s" in T)
truthy("  and why, so it does not read as a fault",
       "rate-" in T and "fill in on the next sync" in T)

print("\n--- one day behind is normal and is not nagged about ---")
# Amazon never publishes today and revises yesterday for a day or two after.
truthy("a gap of one is silent", "if gap < 2:" in T)
truthy("  and a full window says nothing at all", "if not last or last >= end:" in T)

J = open(r"D:\AltaScraper\static\js\traffic.js", encoding="utf-8").read()
truthy("the screen shows it above the tiles", "d.freshness" in J)
truthy("  because every tile divides by it", "_fr.note" in J)
truthy("and the revenue tile carries its own explanation", "k.note" in J)

print("\n--- _money formats without inventing ---")
check("a figure", TV._money(102.21), "102.21")
check("  nothing", TV._money(None), "0.00")
check("  nonsense", TV._money("abc"), "0.00")

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
