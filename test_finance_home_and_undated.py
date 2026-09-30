"""Account-wide money: filed under the account's HOME marketplace, the monthly
subscription counted once however often the finances are re-read.

Faults found on real data (finance audit + review, 30 Sep 2026):

  1. WRONG MARKETPLACE. The guard that files the account-wide Finances feed under
     the account's default marketplace read it through load_settings(), which
     refuses to load when an unrelated key is missing. The failure was swallowed
     and nestwell_goods' refunds, fees and ad invoices were stored under IT.
  2. SUBSCRIPTION DOUBLE-COUNTED. Amazon sends the 30.00 subscription with no
     date. Every pull put it on ITS last day and a re-sync ending on another day
     kept both: 180.00 counted for a window holding 90.00.
  3. (review) a part-read pull must never replace a real day; a new month's
     charge must not hide behind an old backfill; two syncs at once must not
     record one charge twice.

No Amazon call is made: fetch_range is replaced by a fake that answers each
window the way Amazon does -- by a posting date, hidden for undated charges.
"""
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import os, sys, json, tempfile, threading, datetime as dt
sys.path.insert(0, _REPO)

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-68s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

TMP = tempfile.mkdtemp(prefix="altafinhome_")
CFG = os.path.join(TMP, "config.json")
# No google_service_account_json: load_settings() refuses this file, exactly as
# on the live server on 28 Sep 2026.
ACC = {"id": "nw", "label": "Nestwell", "default_marketplace": "UK",
       "marketplaces": ["UK", "IT"], "lwa_client_id": "cid",
       "lwa_client_secret": "sec", "refresh_token": "Atzr|test"}
json.dump({"accounts": [ACC]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "fin.db")

from config import settings as _settings
from data import db as _db
from domain import finance_data as fd
from domain import finance_fetch as ff
from domain import finance_coverage as fcov
from domain import accounts as accts

ff.PAUSE = 0
ORIG_UTCNOW = ff._utcnow
# The test's clock: late on the day NOW["d"] (UTC), unless a time is set.
NOW = {"d": dt.date(2026, 9, 30), "t": dt.time(23, 0)}
ff._utcnow = lambda: dt.datetime.combine(NOW["d"], NOW["t"])

def money(v):
    return {"CurrencyAmount": v, "CurrencyCode": "GBP"}

def sub(posted):
    # "_T" is the posting date Amazon keeps to itself: it decides which window
    # returns the charge, and the parser never sees it.
    return {"_T": posted, "FeeList": [{"FeeType": "Subscription", "FeeAmount": money(-30.0)}]}

def ship(posted, units=1):
    return {"AmazonOrderId": "203-" + posted, "PostedDate": posted + "T10:00:00Z",
            "ShipmentItemList": [{"SellerSKU": "SKU-A", "QuantityShipped": units,
                                  "ItemChargeList": [{"ChargeType": "Principal",
                                                      "ChargeAmount": money(20.0)}],
                                  "ItemFeeList": [{"FeeType": "Commission",
                                                   "FeeAmount": money(-3.0)}]}]}

FEED = {"ShipmentEventList": [ship("2026-09-20")],
        "ServiceFeeEventList": [sub("2026-07-05"), sub("2026-08-05"), sub("2026-09-05")]}
PARTIAL = set()          # half-month starts Amazon answers with "more pages"
BUSY_DAYS = set()        # single days Amazon answers with "more pages"
CALLS = []

def fake_fetch(marketplace, creds, start, end, max_pages=12, next_token=None, log=None):
    CALLS.append((start, end))
    out = {}
    for k, items in FEED.items():
        for e in items:
            d = e.get("_T") or str(e.get("PostedDate", ""))[:10]
            if start <= d <= end:
                out.setdefault(k, []).append({x: y for x, y in e.items() if x != "_T"})
    more = ((start != end and start in PARTIAL)
            or (start == end and start in BUSY_DAYS))
    return {"FinancialEvents": out}, ("more" if more else None), 1
ff.fetch_range = fake_fetch


def rows(mkt="UK", ws="nw", asin="*"):
    return _db.get_db(CFG).execute(
        "SELECT date, other_fees, referral_fees, units FROM finance_daily "
        "WHERE workspace_id=? AND marketplace=? AND asin=? ORDER BY date",
        (ws, mkt, asin)).fetchall()

def subs(mkt="UK"):
    return round(sum(float(r["other_fees"] or 0) for r in rows(mkt)), 2)

def sync(days=95, mkt="UK", aid="nw"):
    return ff.sync(CFG, aid, mkt, {}, account_id=aid, days_back=days)


print("== 1. account-wide money goes under the HOME marketplace ==")
try:
    _settings.load_settings(CFG)
    refused = False
except Exception:
    refused = True
check("fixture: load_settings refuses this config (as on the live server)", refused, True)
check("home_marketplace reads it anyway", accts.home_marketplace(CFG, "nw"), ("UK", ""))
res = sync(mkt="IT")
check("asked for IT: skipped, not stored", bool(res.get("skipped")), True)
check("  nothing under IT", len(rows("IT")), 0)
res = sync()
check("asked for UK: stored", res.get("ok"), True)
check("  the sale's day is under UK", "2026-09-20" in [r["date"] for r in rows()], True)
res = sync(mkt="IT", aid="ghost")
check("an account that cannot be read: REFUSED", (res.get("ok"), bool(res.get("refused"))),
      (False, True))
check("  and nothing stored for it anywhere",
      _db.get_db(CFG).execute("SELECT COUNT(*) FROM finance_daily WHERE workspace_id='ghost'"
                              ).fetchone()[0], 0)
check("  the refusal says why", "no account called" in res.get("error", ""), True)
check("an unreadable settings file: no marketplace",
      accts.home_marketplace(os.path.join(TMP, "missing.json"), "nw")[0], "")
json.dump({"accounts": [{"id": "x", "marketplaces": ["UK", "DE"]}]},
          open(os.path.join(TMP, "two.json"), "w"))
check("no default and two marketplaces: no guess",
      accts.home_marketplace(os.path.join(TMP, "two.json"), "x")[0], "")

print("\n== 2. the undated subscription is counted once, per half-month ==")
check("half-months, aligned down: 16 Jun .. 30 Sep",
      (ff.periods(dt.date(2026, 6, 27), dt.date(2026, 9, 30))[0],
       ff.periods(dt.date(2026, 6, 27), dt.date(2026, 9, 30))[-1]),
      ((dt.date(2026, 6, 16), dt.date(2026, 6, 30)), (dt.date(2026, 9, 16), dt.date(2026, 9, 30))))
check("first 95-day pull: 90.00", subs(), 90.0)
check("  each on its own half-month's last day",
      [r["date"] for r in rows() if r["other_fees"]],
      ["2026-07-15", "2026-08-15", "2026-09-15"])
sync()
check("re-sync: still 90.00 (was 180.00)", subs(), 90.0)
sync(days=30)
check("a 30-day re-sync: still 90.00", subs(), 90.0)
NOW["d"] = dt.date(2026, 9, 29)
sync()
check("a window ending yesterday: still 90.00", subs(), 90.0)
check("three placements recorded, no more",
      _db.get_db(CFG).execute("SELECT COUNT(*) FROM finance_undated").fetchone()[0], 3)

print("\n== 3. a NEW month's charge after a backfill is counted (review #2) ==")
FEED["ServiceFeeEventList"].append(sub("2026-10-05"))
NOW["d"] = dt.date(2026, 10, 30)
sync(days=30)
check("a 30-day pull a month later adds October's 30.00", subs(), 120.0)
sync(days=95)
check("  and a 95-day pull after it does not add it again", subs(), 120.0)

print("\n== 4. a part-read pull never replaces a real day (review #1) ==")
FEED["ShipmentEventList"].append(ship("2026-10-15", units=2))
sync(days=30)
before = [dict(r) for r in rows() if r["date"] == "2026-10-15"]
check("15 Oct holds the sale AND the subscription",
      (before[0]["units"], before[0]["other_fees"]) if before else None, (2, 30.0))
PARTIAL.add("2026-10-01")
BUSY_DAYS.add("2026-10-15")
res = sync(days=30)
after = [dict(r) for r in rows() if r["date"] == "2026-10-15"]
check("  1-15 Oct AND 15 Oct itself too busy: the day is untouched", after, before)
check("  the pull says what it left", (res.get("more"), res.get("periods_not_stored")),
      (True, ["2026-10-01 to 2026-10-15"]))
BUSY_DAYS.clear()
res = sync(days=30)
after = [dict(r) for r in rows() if r["date"] == "2026-10-15"]
check("  read day by day instead: 15 Oct keeps its sale AND its 30.00", after, before)
check("  what the 12-page budget could not reach is named, not 15 Oct",
      res.get("periods_not_stored"), ["2026-10-01 to 2026-10-05", "2026-09-16 to 2026-09-30"])
check("  no placement recorded from a single day",
      _db.get_db(CFG).execute("SELECT COUNT(*) FROM finance_undated").fetchone()[0], 4)
PARTIAL.clear()

print("\n== 4b. a BUSY current half-month still stores recent days (review 2 #1) ==")
FEED["ShipmentEventList"] += [ship("2026-10-28"), ship("2026-10-10")]
PARTIAL.add("2026-10-16")
BUSY_DAYS.add("2026-10-25")
CALLS.clear()
res = sync(days=30)
got = [r["date"] for r in rows()]
check("the newest complete days are stored (28 Oct)", "2026-10-28" in got, True)
check("older half-months are still read and stored (10 Oct)", "2026-10-10" in got, True)
check("  what was left is named", res.get("periods_not_stored"), ["2026-10-16 to 2026-10-25"])
check("  and SAID: the sentence the toast and refresher print",
      "Fees and refunds NOT updated for 2026-10-16 to 2026-10-25" in (res.get("not_updated") or ""),
      True)
check("  within the page budget", len(CALLS) <= ff.PAGES_PER_PASS, True)
PARTIAL.clear(); BUSY_DAYS.clear()
sync(days=30)
check("  the next quiet sync: the subscription total is unchanged", subs(), 120.0)

print("\n== 5. a complete re-read clears what older pulls left behind ==")
conn = _db.get_db(CFG)
for asin in ("*", "B0STALE001"):      # the old fallback: account total AND a product row
    conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
                 "other_fees, units, principal) VALUES ('nw','UK','2026-10-20',?,30.0,0,0)",
                 (asin,))
conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
             "referral_fees, units, principal) VALUES ('nw','UK','2026-10-21','*',1.0,1,9.0)")
conn.commit()
PARTIAL.add("2026-10-16")
sync(days=30)
check("a part-read half-month removes nothing", "2026-10-20" in [r["date"] for r in rows()], True)
PARTIAL.clear()
res = sync(days=30)
check("read whole: the stale no-trade 30.00 goes", res.get("stale_undated_days_removed"),
      ["2026-10-20"])
check("  its product row goes too", len(rows(asin="B0STALE001")), 0)
check("  the total is right again", subs(), 120.0)
check("  a day with trade is left alone", "2026-10-21" in [r["date"] for r in rows()], True)

print("\n== 6. two syncs at once record a charge once (review #4) ==")
errs = []
def _one():
    try:
        fd.place_undated(CFG, "nw", "UK", [{"field": "other_fees", "sku": None,
                                            "amount": 30.0, "currency": "GBP"}],
                         "2026-01-01", "2026-01-15")
    except Exception as ex:
        errs.append(str(ex))
ts = [threading.Thread(target=_one) for _ in range(6)]
for t in ts: t.start()
for t in ts: t.join()
check("six at once: one placement, no errors",
      (_db.get_db(CFG).execute("SELECT COUNT(*) FROM finance_undated WHERE "
                               "placed_on='2026-01-15'").fetchone()[0], errs), (1, []))

print("\n== 6b. just after midnight UTC on the 16th (review 2 #2) ==")
_src = open(os.path.join(_REPO, "domain", "finance_fetch.py"), encoding="utf-8").read()
check("today is the UTC date, not the machine's",
      ("return _utcnow().date()" in _src,
       abs((ORIG_UTCNOW() - dt.datetime.utcnow()).total_seconds()) < 5), (True, True))
NOW["d"], NOW["t"] = dt.date(2099, 1, 16), dt.time(0, 2)     # 00:02 UTC on the 16th
check("the 16th at 00:02: its window ends before it starts, so not askable",
      ff._askable("2099-01-16", "2099-01-16"), False)
CALLS.clear()
res = sync(days=5)
check("  that period is skipped, not sent to be rejected; the rest is read",
      (res.get("ok"), [c for c in CALLS if c[0] == "2099-01-16"],
       ("2099-01-01", "2099-01-15") in CALLS), (True, [], True))
NOW["d"], NOW["t"] = dt.date(2026, 10, 30), dt.time(23, 0)

print("\n== 7. money already filed under the wrong marketplace is REPORTED ==")
conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
             "refunds) VALUES ('nw','IT','2026-10-03','*',12.0)")
conn.commit()
note = fcov.misfiled(CFG, "nw", "IT")
check("IT: a red note naming UK", (note or {}).get("level"), "bad")
check("  it names the home marketplace", "under UK" in (note or {}).get("text", ""), True)
check("UK itself: no note", fcov.misfiled(CFG, "nw", "UK"), None)
check("the IT row is still there (not deleted)", len(rows("IT")), 1)

print("\n== 8. /finance/resync: names its account, pulls 95 days under home ==")
from flask import Flask
from routes import finance_routes
import domain.live_refresher as _lr
app = Flask(__name__)
finance_routes.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
                        _active_account=lambda: {}, _state={})
seen = {}
def _fake_sync(config_path, ws, mkt, creds, **kw):
    seen.update({"ws": ws, "mkt": mkt, "days": kw.get("days_back"),
                 "pages": kw.get("max_pages"), "busy": _lr.user_busy("nw")})
    return {"ok": True, "days": 3, "start": "a", "end": "b"}
_real_sync, ff.sync = ff.sync, _fake_sync
c = app.test_client()
r = c.post("/finance/resync", json={"account": "nw", "marketplace": "IT"})
check("named account: 200", r.status_code, 200)
check("  pulled under UK, 95 days, one bigger pass", (seen.get("ws"), seen.get("mkt"),
      seen.get("days"), seen.get("pages")), ("nw", "UK", 95, ff.RESYNC_PAGES))
check("  the refresher stands aside while it runs", seen.get("busy"), True)
check("  and is released after", _lr._USER["active"].get("nw"), 0)
seen.clear()
r = c.post("/finance/resync", json={})
check("no account named: refused, nothing pulled", (r.status_code, seen), (400, {}))
r = c.post("/finance/resync", json={"account": "ghost"})
check("unknown account: 404", r.status_code, 404)
ff.sync = _real_sync
_g = open(os.path.join(_REPO, "auth", "guard.py"), encoding="utf-8").read()
check("the guard lists it as a write", '("/finance/resync",                 "edit")' in _g, True)

print("\n== 9. a refused finance pull is SAID, not dropped (review #3) ==")
_sj = open(os.path.join(_REPO, "static", "js", "sales.js"), encoding="utf-8").read()
check("Sales Sync's toast names a failed finance half",
      "j.finance && j.finance.ok === false" in _sj, True)
_lrs = open(os.path.join(_REPO, "domain", "live_refresher.py"), encoding="utf-8").read()
check("the refresher's result records it", "FINANCE NOT UPDATED" in _lrs, True)
check("Sales Sync's toast shows a pull that left days unread",
      "j.finance.not_updated" in _sj, True)
check("  and so does the refresher's result", 'fin.get("not_updated")' in _lrs, True)
check("  and its status shows the sales/finance results", "sales_results" in _lr.status(), True)

print("\n%d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
