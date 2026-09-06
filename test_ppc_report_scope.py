"""ppc_search_terms keeps one row per term PER REPORT, and almost nothing that
reads it remembered.

THE SHAPE OF THE BUG. The API sync names each search-term report after the
window it covers -- ads_api_2026-08-06_2026-09-04 -- so syncing again once the
window has moved writes a SECOND report with almost the same terms in it. Both
sit in the table. domain/ppc_view.load_rows always took the newest, so the
tables on screen were right; every plain COUNT(*) and SUM(spend) over the table
added the reports together.

MEASURED on nestwell_goods/UK before this was fixed:

    stored terms reported     1,595      real: 821
    wasted spend reported     489.38     real: 251.56

Wasted spend is a headline card on PPC Analytics. It was showing nearly double,
it looked entirely plausible, and it would have grown by another report every
day the sync ran.

Every check below fails on the old code.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                        # noqa: E402
from domain import ppc_view as _pv                # noqa: E402
from domain import ppc_analytics as _pa           # noqa: E402
from domain import drppc_console as _dc           # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


WS, MKT = "__reportscope__", "UK"
conn = _db.get_db()
conn.execute("DELETE FROM ppc_search_terms WHERE workspace_id=?", (WS,))
conn.commit()


def put(rid, a, b, rows):
    return _pv.store_rows(None, WS, MKT, rows, report_id=rid,
                          date_from=a, date_to=b)


# TWO OVERLAPPING REPORTS, the way the sync really makes them: the same terms,
# a day apart, with the later one carrying a little more.
OLD = [{"search_term": "ceiling fan", "clicks": 10, "orders": 0, "spend": 5.0,
        "sales": 0.0, "keyword": "fan", "match_type": "BROAD",
        "campaign": "C1", "ad_group": "G1"},
       {"search_term": "desk fan", "clicks": 4, "orders": 1, "spend": 2.0,
        "sales": 20.0, "keyword": "fan", "match_type": "EXACT",
        "campaign": "C1", "ad_group": "G1"}]
NEW = [{"search_term": "ceiling fan", "clicks": 12, "orders": 0, "spend": 6.0,
        "sales": 0.0, "keyword": "fan", "match_type": "BROAD",
        "campaign": "C1", "ad_group": "G1"},
       {"search_term": "desk fan", "clicks": 4, "orders": 1, "spend": 2.0,
        "sales": 20.0, "keyword": "fan", "match_type": "EXACT",
        "campaign": "C1", "ad_group": "G2"},
       {"search_term": "tower fan", "clicks": 3, "orders": 0, "spend": 1.5,
        "sales": 0.0, "keyword": "fan", "match_type": "PHRASE",
        "campaign": "C1", "ad_group": "G2"}]

put("ads_api_2026-08-06_2026-09-04", "2026-08-06", "2026-09-04", OLD)
put("ads_api_2026-08-07_2026-09-05", "2026-08-07", "2026-09-05", NEW)

raw = conn.execute("SELECT COUNT(*) n, ROUND(SUM(spend),2) s FROM "
                   "ppc_search_terms WHERE workspace_id=?", (WS,)).fetchone()
print("\nboth reports are in the table, which is not itself the bug")
check("rows across all reports", raw["n"], 5)
check("spend across all reports", raw["s"], 16.5)

print("\nand the newest is picked even when both landed in the SAME SECOND")
# uploaded_at is stored to the second, and the two put() calls above run inside
# one. Ordering on the timestamp alone lets the database return whichever it
# likes -- which was the OLDER report, and report_meta decides what every screen
# shows. Found by this test, on the real code.
_ts = {r["report_id"]: r["up"] for r in conn.execute(
    "SELECT report_id, MAX(uploaded_at) up FROM ppc_search_terms "
    "WHERE workspace_id=? GROUP BY report_id", (WS,))}
check("both really do share a timestamp", len(set(_ts.values())), 1)

print("\nbut only ONE of them is the current picture")
tot = _pv.stored_totals(None, WS, MKT)
check("the newest report is the current one", tot["report_id"],
      "ads_api_2026-08-07_2026-09-05")
check("its term count, not the sum of both", tot["terms"], 3)
check("its spend, not the sum of both", tot["spend"], 9.5)
check("load_rows agrees", len(_pv.load_rows(None, WS, MKT)), 3)

print("\nand every reader now says the same number")
av = _pa.availability(None, WS, MKT)
check("availability counts the current report", av["search_terms"]["rows"], 3)

# THE HEADLINE CARD. In the current report two terms took clicks and bought
# nothing -- "ceiling fan" at 6.00 and "tower fan" at 1.50. "ceiling fan" also
# appears in the OLD report at 5.00, so adding the reports together reported
# 12.50 of waste where 7.50 is real.
w = _pa.wasted_spend(None, WS, MKT, "2026-08-07", "2026-09-05")
check("wasted spend is the current report's", w["spend"], 7.5)
check("  and its term count", w["terms"], 2)
check("  not the sum across both reports", w["spend"] == 12.5, False)

print("\nthe console counts the same way")
st = _dc.current_state(None, WS, MKT)
# G1 and G2 both appear in the NEW report; the OLD one adds nothing new here,
# but a group that existed ONLY in the old report must not be counted.
check("ad groups from the current report", st["counts"]["ad_groups"], 2)
d = _dc.campaign_detail(None, WS, MKT, "C1")
kw = [k for g in d["ad_groups"] for k in g["keywords"]]
# THE ONE THAT DOUBLED. "fan" as an EXACT keyword appears in both reports at
# 2.00; summed across them it read 4.00.
exact = [k for k in kw if k["match_type"] == "EXACT"]
check("the campaign's keyword spend is not doubled",
      sum(k["spend"] for k in exact), 2.0)

print("\na report entirely inside the kept one is dropped on the next store")
conn.execute("DELETE FROM ppc_search_terms WHERE workspace_id=?", (WS,))
conn.commit()
put("ads_api_2026-08-10_2026-08-20", "2026-08-10", "2026-08-20", OLD)
put("ads_api_2026-08-01_2026-08-31", "2026-08-01", "2026-08-31", NEW)
left = {r["report_id"] for r in conn.execute(
    "SELECT DISTINCT report_id FROM ppc_search_terms WHERE workspace_id=?",
    (WS,))}
check("the contained report is gone", left, {"ads_api_2026-08-01_2026-08-31"})

print("\nbut an OVERLAPPING one is kept — it is the only record of its own days")
conn.execute("DELETE FROM ppc_search_terms WHERE workspace_id=?", (WS,))
conn.commit()
put("ads_api_2026-08-06_2026-09-04", "2026-08-06", "2026-09-04", OLD)
put("ads_api_2026-08-07_2026-09-05", "2026-08-07", "2026-09-05", NEW)
left = {r["report_id"] for r in conn.execute(
    "SELECT DISTINCT report_id FROM ppc_search_terms WHERE workspace_id=?",
    (WS,))}
check("both survive, because 6 August is in one and not the other",
      len(left), 2)

print("\nand a hand-uploaded report is never pruned by a fetched one")
conn.execute("DELETE FROM ppc_search_terms WHERE workspace_id=?", (WS,))
conn.commit()
put("manual-upload-july", "2026-08-10", "2026-08-20", OLD)
put("ads_api_2026-08-01_2026-08-31", "2026-08-01", "2026-08-31", NEW)
left = {r["report_id"] for r in conn.execute(
    "SELECT DISTINCT report_id FROM ppc_search_terms WHERE workspace_id=?",
    (WS,))}
truthy("the uploaded one is still there", "manual-upload-july" in left)

print("\nthe number of fetched reports is capped, so it cannot grow for ever")
conn.execute("DELETE FROM ppc_search_terms WHERE workspace_id=?", (WS,))
conn.commit()
import time                                       # noqa: E402
for i in range(6):
    # Windows that overlap without nesting, which is what the sync produces.
    put("ads_api_2026-0%d-01_2026-0%d-28" % (i + 1, i + 2),
        "2026-0%d-01" % (i + 1), "2026-0%d-28" % (i + 2), OLD)
n = len({r["report_id"] for r in conn.execute(
    "SELECT DISTINCT report_id FROM ppc_search_terms WHERE workspace_id=?",
    (WS,))})
check("no more than the cap are kept", n <= _pv.KEEP_API_REPORTS, True)

conn.execute("DELETE FROM ppc_search_terms WHERE workspace_id=?", (WS,))
conn.commit()

# ---------------------------------------------------------------------------
print("\nTACOS divides two figures that cover the SAME DAYS")
# ---------------------------------------------------------------------------
# Amazon's advertising feed runs about two days behind its sales feed. So a
# window always ends with days that have sales and no advertising -- and TACOS
# used to divide the spend by the WHOLE window's sales, including days the spend
# could not possibly cover. The ratio came out low, every day, on every screen
# that shows it.
for t in ("ads_daily", "sales_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
# Two days with both feeds, then a third with sales only -- the everyday shape.
for d, spend in (("2026-08-01", 10.0), ("2026-08-02", 10.0)):
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
        "ad_sales, clicks, impressions, ad_orders) VALUES (?,?,?,'*',?,?,?,?,?)",
        (WS, MKT, d, spend, 50.0, 20, 900, 2))
for d, sales in (("2026-08-01", 100.0), ("2026-08-02", 100.0),
                 ("2026-08-03", 100.0)):
    conn.execute(
        "INSERT INTO sales_daily (workspace_id, marketplace, date, asin, "
        "ordered_sales, units) VALUES (?,?,?,'*',?,?)", (WS, MKT, d, sales, 3))
conn.commit()

tt = _pa.totals_for(None, WS, MKT, "2026-08-01", "2026-08-03")
check("the window's own total sales are still reported in full",
      tt["total_sales"], 300.0)
check("but only two days carry advertising", tt["ad_days"], 2)
check("  so the comparable sales are those two days", tt["comparable_sales"],
      200.0)
# 20 / 200 = 10.0%. Dividing by the whole 300 gives 6.7% -- a third too low,
# and always in the flattering direction.
check("TACOS uses the overlap", tt["tacos_pct"], 10.0)
check("  not the whole window", tt["tacos_pct"] == 6.7, False)
truthy("  and it says why", tt["tacos_note"])

# When both feeds cover the same days there is nothing to explain.
conn.execute("DELETE FROM sales_daily WHERE workspace_id=? AND date=?",
             (WS, "2026-08-03"))
conn.commit()
tt2 = _pa.totals_for(None, WS, MKT, "2026-08-01", "2026-08-03")
check("with the feeds level the ratio is unchanged", tt2["tacos_pct"], 10.0)
check("  and there is no note to make", tt2["tacos_note"], "")

for t in ("ads_daily", "sales_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    for f in fails:
        print("  FAILED:", f)
    sys.exit(1)
print("all passed")
