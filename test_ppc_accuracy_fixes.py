"""PPC Analytics accuracy: the seven data faults the 30 Sep 2026 audit found.

Nestwell UK, 31 Aug - 29 Sep, on a copy of real data: the arithmetic was right
and the DATA was wrong (ad profit shown -109 against about -202; break-even
ACOS 28.2% against 23.5%). Each section pins one fix:

  1. ad VAT silently 0 when no ad invoice was stored (ad_cost.ad_vat)
  2. days stored on 30-day attribution never re-pulled (ads_sync.resync_windows)
  3. order lines stored with a blank purchase_date never counted, never filled
  4. the newest ad day shown as final while Amazon was still counting it
  5. change arrows comparing 28 days of ad data with 23 (ppc_analytics.compare)
  6. campaign labels judged on fewer days than their money columns
  7. the overview's branded split ignored the date picker and capped at 1,000

Runs on its own temporary database; nothing real is read or written.
"""
import datetime as dt
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
_TMP = tempfile.mkdtemp(prefix="ppc_accuracy_")
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t" + ".db")
_CFG = os.path.join(_TMP, "config" + ".json")
with open(_CFG, "w") as _fh:
    _fh.write('{"accounts": [{"id": "__nw__", "vat_rate": 0}, '
              '{"id": "__reg__", "vat_rate": 0.2}]}')
os.environ["CONFIG_PATH"] = _CFG

from data import db as _db                      # noqa: E402
from domain import ad_cost as _adc              # noqa: E402
from domain import ads_sync as _as              # noqa: E402
from domain import hourly_week as _hw           # noqa: E402
from domain import ppc_analytics as _pa         # noqa: E402
from api import amazon_ads as _ads              # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-72s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


conn = _db.get_db()


def ins(table, **kv):
    conn.execute("INSERT INTO %s (%s) VALUES (%s)"
                 % (table, ", ".join(kv), ",".join("?" * len(kv))), list(kv.values()))


def day(d, n):
    return (dt.date.fromisoformat(d) + dt.timedelta(days=n)).isoformat()


print("\n1. ad VAT: measured, else the UK's 20% said as an estimate, never a silent 0")
check("not registered, UK, no invoice -> 20% estimated",
      _adc.ad_vat(None, "__a1__", "UK", "2026-09-29", False)["ratio"], 0.20)
check("  and the page is told it is an estimate",
      _adc.ad_vat(None, "__a1__", "UK", "2026-09-29", False)["basis"], "estimated")
check("  product_ratio (per-product screens) uses the same rule",
      _adc.product_ratio(None, "__a1__", "UK", "2026-09-29", 0), 0.20)
_it = _adc.ad_vat(None, "__a1__", "IT", "2026-09-29", False)
check("not registered, not UK, no invoice -> not added", _it["ratio"], None)
check("  but SAID, not silent", bool(_it["note"]), True)
check("registered -> nothing added",
      _adc.ad_vat(None, "__a1__", "UK", "2026-09-29", True)["ratio"], None)
check("unset -> nothing added, and said",
      bool(_adc.ad_vat(None, "__a1__", "UK", "2026-09-29", None)["note"]), True)
# An invoice from long before the window's 365 days is still a measurement.
ins("finance_daily", workspace_id="__a2__", marketplace="UK", date="2024-01-10",
    asin="*", ads_charged=100.0, ads_charged_tax=21.0, currency="GBP")
conn.commit()
check("an invoice from any stored period is measured (21%)",
      _adc.ad_vat(None, "__a2__", "UK", "2026-09-29", False),
      {"ratio": 0.21, "basis": "measured", "note": ""})
ins("finance_daily", workspace_id="__a2__", marketplace="UK", date="2026-09-01",
    asin="*", ads_charged=100.0, ads_charged_tax=20.0, currency="GBP")
conn.commit()
check("  the last 365 days win over older ones (20%)",
      _adc.ad_vat(None, "__a2__", "UK", "2026-09-29", False)["ratio"], 0.20)
ins("ads_daily", workspace_id="__a1__", marketplace="UK", date="2026-09-10",
    asin="*", spend=10.0, ad_product="SPONSORED_PRODUCTS")
conn.commit()
_fw = _adc.for_window(None, "__a1__", "UK", "2026-09-01", "2026-09-30", False)
check("the profit screens' cost carries the estimate (10 + 2)", _fw["cost"], 12.0)
check("  with the note", "estimated at 20%" in _fw["note"], True)
_r = _pa.rates(_CFG, "__nw__", "UK", "2026-09-01", "2026-09-30")
check("PPC rates(): nestwell-like account (vat_rate 0) gets 0.2", _r["ad_vat_ratio"], 0.2)
check("  basis 'estimated' for the page", _r["ad_vat_basis"], "estimated")
check("PPC rates(): a registered account adds none",
      _pa.rates(_CFG, "__reg__", "UK", "2026-09-01", "2026-09-30")["ad_vat_ratio"], 0.0)


print("\n2. attribution marker, and old 30-day days pulled again")
check("_row names the 7-day window",
      _ads._row({"date": "2026-09-01", "cost": 1.0, "sales7d": 2.0})["attribution"], "7d")
check("_row names the 30-day window",
      _ads._row({"date": "2026-09-01", "cost": 1.0, "sales30d": 2.0})["attribution"], "30d")
_rows7 = [_ads._row({"date": "2026-09-20", "campaignId": "C1", "campaignName": "c",
                     "cost": 3.0, "sales7d": 9.0, "purchases7d": 1})]
_as.store_rows(conn, "__ad__", "UK", "campaign", _rows7, "2026-09-21T10:00:00")
conn.commit()
check("store_rows marks the account row 7d",
      conn.execute("SELECT attribution FROM ads_daily WHERE workspace_id='__ad__' "
                   "AND asin='*'").fetchone()[0], "7d")
check("  and the campaign row",
      conn.execute("SELECT attribution FROM ads_campaign_daily WHERE "
                   "workspace_id='__ad__'").fetchone()[0], "7d")

_as._today = lambda: dt.date(2026, 9, 30)
check("normal window only when nothing old is on 30 days",
      _as.resync_windows(None, "__ad__", "UK", 30), [("2026-08-31", "2026-09-29")])
# Days stored before the marker existed (NULL) inside the last 60 days.
for d in ("2026-08-08", "2026-08-20", "2026-07-01"):
    ins("ads_daily", workspace_id="__ad__", marketplace="UK", date=d, asin="*",
        spend=1.0, ad_product="SPONSORED_PRODUCTS")
conn.commit()
_w = _as.resync_windows(None, "__ad__", "UK", 30)
check("an extra window reaches back to the oldest non-7d day in 60 (8 Aug)",
      _w, [("2026-08-31", "2026-09-29"), ("2026-08-08", "2026-08-30")])
check("  and never beyond 60 days (1 Jul is left alone)",
      min(s for s, _e in _w) >= "2026-07-31", True)
check("  every extra window fits one report (<= 30 days)",
      all((dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days < 30 for s, e in _w),
      True)
check("the extra windows skip the search term report",
      "search_term" in _as._kinds_for_window(("SPONSORED_PRODUCTS",), 1), False)
check("  the normal window keeps it",
      "search_term" in _as._kinds_for_window(("SPONSORED_PRODUCTS",), 0), True)
_w1 = _as.resync_windows(None, "__ad__", "UK", 1)
check("the newest days are always re-pulled (>= 3 days back from yesterday)",
      _w1[0], ("2026-09-27", "2026-09-29"))


# Per-product rows count too: the account row is 7d, a product row is not.
ins("ads_daily", workspace_id="__pp__", marketplace="UK", date="2026-08-20", asin="*",
    spend=1.0, ad_product="SPONSORED_PRODUCTS", attribution="7d")
ins("ads_daily", workspace_id="__pp__", marketplace="UK", date="2026-08-20",
    asin="B0X", spend=1.0, ad_product="SPONSORED_PRODUCTS")
conn.commit()
check("a per-product row still on 30 days is re-pulled too",
      _as.resync_windows(None, "__pp__", "UK", 30)[1:], [("2026-08-20", "2026-08-30")])

# An older window already waiting to be collected is not commissioned again.
_asked = []


def _fake_request(creds, mkt, kind, s, e, unit):
    _asked.append((kind, s, e))
    return "rid-%d" % len(_asked)


_as.creds_or_why = lambda ws, cp=None: ({"ads_profile_id": "p"}, None)
_as._settings.read_raw = lambda *a, **k: {"accounts": [{"id": "__ad__"}]}
_as._ads.report_request = _fake_request
_as.request_reports("__ad__", "UK", 30, None)
_first_old = [a for a in _asked if a[1] == "2026-08-08"]
_asked.clear()
_as.request_reports("__ad__", "UK", 30, None)
_second_old = [a for a in _asked if a[1] == "2026-08-08"]
check("the first run commissions the older window", bool(_first_old), True)
check("  a second run before collection does not ask again", _second_old, [])
check("  the normal window is still asked every run",
      any(a[1] == "2026-08-31" for a in _asked), True)

print("\n3. an order line stored without its date gets it later")
check("clean_header keeps an ISO date and a known status",
      _hw.clean_header("2026-09-20T10:00:00Z", "Shipped"), ("2026-09-20T10:00:00Z", "Shipped"))
check("  and a date with an offset",
      _hw.clean_header("2026-09-20T10:00:00+01:00", "Pending")[0], "2026-09-20T10:00:00+01:00")
check("  drops a malformed date and an unknown status",
      _hw.clean_header("20/09/2026", "Delivered!"), ("", ""))
check("  drops an impossible date", _hw.clean_header("2026-13-45", "")[0], "")
_osrc = open(os.path.join(HERE, "routes", "orders_routes.py"), encoding="utf-8").read()
check("/orders/items cleans the body's date and status before storing",
      "clean_header(w.get(\"purchased\"), w.get(\"status\"))" in _osrc, True)
_hw.store_lines(None, "__ol__", "UK", [{
    "order_id": "O1", "purchase_date": "", "asin": "A", "sku": "S", "title": "t",
    "units": 1, "revenue": 20.0, "shipping": 0.0, "currency": "GBP", "status": ""}])
_hw.store_lines(None, "__ol__", "UK", [{
    "order_id": "O1", "purchase_date": "2026-09-20T10:00:00Z", "asin": "A",
    "sku": "S", "title": "t", "units": 1, "revenue": 20.0, "shipping": 0.0,
    "currency": "GBP", "status": "Shipped"}])
_l = conn.execute("SELECT purchase_date, status FROM order_lines WHERE "
                  "workspace_id='__ol__' AND order_id='O1'").fetchone()
check("the blank purchase_date is filled on the next store",
      _l[0], "2026-09-20T10:00:00Z")
check("  and the blank status", _l[1], "Shipped")
_hw.store_lines(None, "__ol__", "UK", [{
    "order_id": "O1", "purchase_date": "", "asin": "A", "sku": "S", "title": "t",
    "units": 1, "revenue": 20.0, "shipping": 0.0, "currency": "GBP", "status": ""}])
_l = conn.execute("SELECT purchase_date, status FROM order_lines WHERE "
                  "workspace_id='__ol__' AND order_id='O1'").fetchone()
check("a later blank never wipes a stored date", _l[0], "2026-09-20T10:00:00Z")
check("  or a stored status", _l[1], "Shipped")
_hw.store_lines(None, "__ol__", "UK", [{
    "order_id": "O2", "purchase_date": "", "asin": "B", "sku": "T", "title": "t",
    "units": 1, "revenue": 5.0, "shipping": 0.0, "currency": "GBP", "status": ""}])
check("fill_blanks dates a line read from the store",
      _hw.fill_blanks(None, "__ol__", "UK", "O2", "2026-09-21T09:00:00Z", "Shipped"), 2)
check("  only blanks: a second call changes nothing",
      _hw.fill_blanks(None, "__ol__", "UK", "O2", "2026-01-01T00:00:00Z", "Pending"), 0)
_orders_src = open(os.path.join(HERE, "routes", "orders_routes.py"), encoding="utf-8").read()
check("the Orders route passes the order's date and status to the store",
      "_store_items(account_id, mkt, order_id, got, purchased, status)" in _orders_src, True)
_ojs = open(os.path.join(HERE, "static", "js", "orders.js"), encoding="utf-8").read()
check("the Orders screen sends purchased + status with /orders/items",
      "purchased:r.purchased" in _ojs and "status:r.status" in _ojs, True)


print("\n4. the newest ad day is 'still settling', not final")
for d, f in (("2026-09-25", "2026-09-28T15:18:31"), ("2026-09-26", "2026-09-28T15:18:31"),
             ("2026-09-27", "2026-09-28T15:18:31")):
    ins("ads_daily", workspace_id="__st__", marketplace="UK", date=d, asin="*",
        spend=10.0, ad_sales=20.0, fetched_at=f, ad_product="SPONSORED_PRODUCTS")
conn.commit()
check("days read under 3 days after they happened are settling",
      _as.settling_days(None, "__st__", "UK"), ["2026-09-26", "2026-09-27"])
check("today_bar marks the latest day as settling",
      _pa.today_bar(None, "__st__", "UK")["settling"], True)
check("maturity() lists them for the charts",
      _pa.maturity(None, "__st__", "UK", "2026-09-01", "2026-09-30")["settling_days"],
      ["2026-09-26", "2026-09-27"])
conn.execute("UPDATE ads_daily SET fetched_at='2026-09-30T08:00:00' WHERE "
             "workspace_id='__st__' AND date='2026-09-27'")
conn.commit()
check("re-read 3 days later, it is final",
      _as.settling_days(None, "__st__", "UK"), ["2026-09-26"])


print("\n5. change arrows compare like with like")
# 10 days of ads now, only 5 in the 10 days before -> no arrow, reason given.
for i in range(10):
    ins("ads_daily", workspace_id="__cm__", marketplace="UK", date=day("2026-09-11", i),
        asin="*", spend=10.0, ad_sales=30.0, clicks=10, impressions=100, ad_orders=1,
        ad_product="SPONSORED_PRODUCTS")
for i in range(5):
    ins("ads_daily", workspace_id="__cm__", marketplace="UK", date=day("2026-09-06", i),
        asin="*", spend=10.0, ad_sales=30.0, clicks=10, impressions=100, ad_orders=1,
        ad_product="SPONSORED_PRODUCTS")
conn.commit()
_c = _pa.compare(None, "__cm__", "UK", "2026-09-11", "2026-09-20")
check("previous period with fewer ad days -> no spend arrow", _c["change"].get("spend"), None)
check("  and says why", "only 5" in _c["change_floor"].get("spend", ""), True)
for i in range(5):
    ins("ads_daily", workspace_id="__cm__", marketplace="UK", date=day("2026-09-01", i),
        asin="*", spend=5.0, ad_sales=15.0, clicks=5, impressions=50, ad_orders=1,
        ad_product="SPONSORED_PRODUCTS")
conn.commit()
_c = _pa.compare(None, "__cm__", "UK", "2026-09-11", "2026-09-20")
check("complete previous period -> a real change (100 vs 75: +33.3%)",
      _c["change"].get("spend"), 33.3)
_c = _pa.compare(None, "__cm__", "UK", "2026-09-11", "2026-09-25")
check("the span compared is the ad days, not the calendar (lagging feed)",
      (_c["now_end"], _c["compare_start"], _c["compare_end"]),
      ("2026-09-20", "2026-09-01", "2026-09-10"))


print("\n6. labels still leave out the 2 settling days (spec section 4) -- and SAY so")
# Two campaigns: C1 sold on a mature day; C2 spent only on the last 2 days.
for d, cid, sp, sa in (("2026-09-10", "C1", 5.0, 50.0), ("2026-09-19", "C1", 4.0, 0.0),
                       ("2026-09-20", "C2", 6.0, 0.0)):
    ins("ads_campaign_daily", workspace_id="__jd__", marketplace="UK", date=d,
        campaign_id=cid, campaign_name=cid, spend=sp, ad_sales=sa, clicks=5,
        impressions=50, ad_orders=(1 if sa else 0), ad_product="SPONSORED_PRODUCTS")
    ins("ads_daily", workspace_id="__jd__", marketplace="UK", date=d, asin="*",
        spend=sp, ad_sales=sa, ad_product="SPONSORED_PRODUCTS")
conn.commit()
_mat = _pa.maturity(None, "__jd__", "UK", "2026-09-01", "2026-09-20")
check("mature_end is 2 days before the latest ad day", _mat["mature_end"], "2026-09-18")
_rt = {"fee_rate": 0.15, "cogs_rate": 0.3, "breakeven_acos_pct": 55.0,
       "vat_share": 0.0, "ad_vat_ratio": 0.0}
_cs = {c["campaign_id"]: c for c in _pa.campaigns(
    None, "__jd__", "UK", "2026-09-01", "2026-09-20", _rt, judge_end=_mat["mature_end"])}
check("money columns cover the full window (C1 spend 9)", _cs["C1"]["spend"], 9.0)
check("  the label is judged to mature_end", _cs["C1"]["judged_to"], "2026-09-18")
check("  and the settling spend is named on the row (4)", _cs["C1"]["settling_spend"], 4.0)
check("a campaign that ran only on settling days is not judged 'no sales'",
      _cs["C2"]["cohort"] != "no_sales", True)
check("  its 6 is marked settling", _cs["C2"]["settling_spend"], 6.0)
_rsrc = open(os.path.join(HERE, "routes", "ppc_analytics_routes.py"), encoding="utf-8").read()
check("both campaign screens judge without the trailing 2 days",
      _rsrc.count('judge_end=mat.get("mature_end")'), 2)
_sh = open(os.path.join(HERE, "static", "js", "ppcshared.js"), encoding="utf-8").read()
_cjs = open(os.path.join(HERE, "static", "js", "ppccampaigns.js"), encoding="utf-8").read()
check("the page says which day the labels are judged to",
      "Labels judged to" in _sh and "ppcJudgedNote(j.maturity)" in _cjs, True)
check("  and tags settling spend on the row", "r.settling_spend" in _cjs, True)

print("\n7. branded split follows the picker")
_ov = _rsrc.split('def ppc_analytics_overview')[1].split('@app.route')[0]
check("the overview's terms are every term, in the picked window",
      "limit=None" in _ov and "start=(start if _fo else None)" in _ov, True)

print("\n%d checks, %d failed" % (len(ran), len(fails)))
sys.exit(1 if fails else 0)
