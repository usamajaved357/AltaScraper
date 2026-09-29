"""The advertising pages' bug round (owner, 30 Sep 2026: "fix all the bugs across
the ppc pages including campaign analytics, everything related to advertising").

Each block fails on the code before the fix:
  1. a search term is ONE row, its days added up (it was one row per day, the
     1000-row cap dropped rows in no order, and every click/order threshold
     was tested against a single day)
  2. wasted spend is counted per term
  3. a campaign's state and budget are the newest day's; a DAILY budget is
     compared with a daily spend
  4. Dr PPC never recommends a negative blind while something was out of stock
  5. ad profit counts the VAT on ad spend; a profit share is of the profit made
  6. the campaign builder never fills in a bid or a budget
  7. the keyword week is Amazon's Sunday-Saturday
  8. the browser side: newest request wins, focus kept, text sort direction,
     currency sent, keyword screens reset on an account switch
"""
import datetime
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


TMP = tempfile.mkdtemp(prefix="altappcfix_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "ws1", "label": "One", "vat_rate": 0}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "p.db")

from data import db as _db                 # noqa: E402
from domain import ppc_view as PV          # noqa: E402
from domain import ppc_analytics as PA     # noqa: E402
from domain import ads_sync as AS          # noqa: E402
from domain import dr_ppc as DR            # noqa: E402

c = _db.get_db(CFG)
cols = [r[1] for r in c.execute("PRAGMA table_info(ppc_search_terms)")]
has_date = "date" in cols


def term(day, t, clicks, spend, orders=0, sales=0.0):
    row = {"workspace_id": "ws1", "marketplace": "UK", "report_id": "R1",
           "search_term": t, "keyword": "kw", "match_type": "BROAD", "campaign": "C1",
           "ad_group": "G1", "impressions": clicks * 10, "clicks": clicks, "spend": spend,
           "sales": sales, "orders": orders, "units": orders, "uploaded_at": "2026-09-30 01:00:00"}
    if has_date:
        row["date"] = day
    c.execute("INSERT INTO ppc_search_terms (%s) VALUES (%s)" % (",".join(row), ",".join("?" * len(row))),
              list(row.values()))


# "wireless mouse": 4 clicks a day for 10 days, no orders -> 40 clicks of waste.
for i in range(10):
    term("2026-09-%02d" % (i + 1), "wireless mouse", 4, 0.5)
term("2026-09-01", "gaming mouse", 12, 6.0, orders=2, sales=40.0)
c.commit()

print("== 1. one row per search term ==")
rows = PV.load_terms(CFG, "ws1", "UK")
check("two terms, not eleven rows", len(rows), 2)
wm = [r for r in rows if r["search_term"] == "wireless mouse"][0]
check("  its days added up", (wm["clicks"], round(wm["spend"], 2), wm["days"]), (40, 5.0, 10))
check("  biggest spend first", rows[0]["search_term"], "gaming mouse")
t = PA.terms(CFG, "ws1", "UK", {"fee_rate": 0.15, "cogs_rate": 0.3, "breakeven_acos_pct": 30.0})
check("the Search Terms table: one row each", sorted(r["search_term"] for r in t),
      ["gaming mouse", "wireless mouse"])

print("\n== 2. wasted spend per term ==")
w = PA.wasted_spend(CFG, "ws1", "UK", "2026-09-01", "2026-09-30")
check("40 clicks over ten days is qualified waste (10+ clicks)",
      (w.get("actionable_terms"), w.get("actionable_spend")), (1, 5.0))

print("\n== 3. campaigns: newest state and budget, daily budget vs daily spend ==")
for d, st, bud, sp in (("2026-09-01", "ENABLED", 20.0, 3.0), ("2026-09-02", "PAUSED", 20.0, 3.0),
                       ("2026-09-03", "ENABLED", 5.0, 3.0)):
    c.execute("INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, campaign_id, "
              "campaign_name, status, budget, spend, ad_sales, clicks, impressions, ad_orders) "
              "VALUES ('ws1','UK',?,'77','Camp',?,?,?,30,10,100,1)", (d, st, bud, sp))
c.commit()
cr = AS.campaign_rows(CFG, "ws1", "UK", "2026-09-01", "2026-09-03")
check("state and budget from the newest day", (cr[0]["state"], cr[0]["budget"]), ("ENABLED", 5.0))
check("  and how many days the sums cover", cr[0]["days"], 3)
capped = DR.check_budget_capped([{"campaign_name": "x", "budget": 8.0, "spend": 90.0,
                                  "sales": 300.0, "days": 30}])
check("3.00 a day is not pressed against an 8.00 daily budget", capped, [])

print("\n== 4. no negative recommended blind ==")
f = DR.check_wasted_spend([{"search_term": "blue cup", "clicks": 30, "spend": 9.0, "sales": 0,
                            "campaign_name": "C"}], oos_skus=["SKU1"])
check("a term with no product named, while something was out of stock, is a "
      "warning to check stock", bool(f) and "wasted-spend-stock-unknown" in json.dumps(f), True)
check("  and never the 'add as a negative' finding",
      '"wasted-spend"' in json.dumps(f), False)

print("\n== 5. ad profit ==")
check("VAT on ad spend comes off (100 sales, 20 spend, 20% ad VAT)",
      round(PA.ad_profit(100, 20, 0.15, 0.30, 0.0, 0.2), 2), 31.0)
g = PA.by_group([{"match_type": "EXACT", "profit": 100.0, "spend": 10},
                 {"match_type": "BROAD", "profit": -90.0, "spend": 10}], "match_type")
check("a share of the profit made, never 1000%",
      sorted((x["key"], x["profit_share_pct"]) for x in g), [("BROAD", None), ("EXACT", 100.0)])

print("\n== 6. the builder never fills in a bid ==")
PR = open(os.path.join(HERE, "routes", "ppc_routes.py"), "rb").read().decode("utf-8")
check("no 0.30 / 8.0 default on the server", ('or 0.30)' in PR, 'or 8.0)' in PR), (False, False))
JS = open(os.path.join(HERE, "static", "js", "ppc.js"), "rb").read().decode("utf-8")
check("  nor in the page", ('||"0.30"' in JS, '||"8.0"' in JS), (False, False))

print("\n== 7. Amazon's keyword week ==")
from domain import brand_analytics as BA   # noqa: E402
s0, e0 = BA._last_complete_week()
check("Sunday to Saturday", (datetime.date.fromisoformat(s0).weekday(),
                              datetime.date.fromisoformat(e0).weekday()), (6, 5))
KR = open(os.path.join(HERE, "routes", "keywords_routes.py"), "rb").read().decode("utf-8")
check("  the keywords routes use it", "_ba._last_complete_week()" in KR, True)

print("\n== 8. the browser side ==")


def js(name):
    return open(os.path.join(HERE, "static", "js", name), "rb").read().decode("utf-8")


for f_, v in (("ppcanalytics.js", "PPCA"), ("ppcterms.js", "PPCT"),
              ("ppccampaigns.js", "PPCC"), ("ppclive.js", "PPCL")):
    s = js(f_)
    check("%s: the newest request wins" % f_,
          ("if(!host || %s.loading) return;" % v) not in s and ("_seq !== %s.seq" % v) in s, True)
check("the filter boxes keep their cursor", all(
    "ppcRedrawKeepingFocus(" in js(f_) for f_ in ("ppcanalytics.js", "ppcterms.js", "ppccampaigns.js")), True)
check("the campaign table sorts text the right way",
      "dir * (x < y ? -1 : x > y ? 1 : 0)" in js("sales_campaigns.js"), True)
check("wasted % is over the report's own spend", "w.spend / w.report_spend" in js("ppcanalytics.js"), True)
SS = js("screenstate.js")
check("the keyword screens are reset on an account switch",
      all(k in SS for k in ("KWASIN", "KWSPY", "KWH")), True)
AR = open(os.path.join(HERE, "routes", "ppc_analytics_routes.py"), "rb").read().decode("utf-8")
check("the PPC pages are told their currency", AR.count('"currency": _sd_cur(aid, mkt)'), 3)

print("\nFAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
