# -*- coding: utf-8 -*-
"""Where to buy an order from, and the alert when there is nowhere.

WHAT WAS ASKED FOR
  "display the source links in the order details arranged by low to high price,
   which tells the user you have received an order and you can place the order
   from one of these. also show handling time and profit pounds if the user place
   order from each link what will be the profit and when will my order will be
   delivered to the buyer"
  "i want to see this information of the source in the repricer as well"
  "add an alert in the app that whenever all the links go out of stock i should
   receive a notification"

THE TWO THINGS MOST LIKELY TO GO WRONG HERE, both covered below:

  1. A DEAD LINK SORTING TO THE TOP. It has no price, and None sorts before every
     number in Python 2 habits and raises in Python 3 -- so the natural sort is
     either wrong or a crash. "Cheapest first" has to mean cheapest of the ones
     you can actually buy.

  2. AN ALERT THAT CRIES WOLF. "eBay would not answer" is not "there is nowhere to
     buy it". If a failed fetch raised the out-of-stock alarm it would fire every
     time eBay had a bad minute, and the next real one would be ignored.
"""
import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-66s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


def truthy(l, g):
    check(l, bool(g), True)


def falsy(l, g):
    check(l, bool(g), False)


TMP = tempfile.mkdtemp(prefix="altaordsrc_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "o.db")

from domain import order_sources as OS                         # noqa: E402
from domain import source_repo as R                            # noqa: E402
from domain import sourcing as S                               # noqa: E402
from domain import stock_alerts as A                           # noqa: E402
from listing import pricing as P                               # noqa: E402

WS, MKT, SKU = "ws", "UK", "SKU-1"
NOW = dt.datetime(2026, 8, 17, 12, 0, 0)


def add(url, label=""):
    R.add_source(CFG, WS, MKT, SKU, url, label=label or url, kind="ebay")
    return [s for s in R.sources_for(CFG, WS, MKT, SKU) if s["url"] == url][0]["id"]


def reading(price, shipping=0.0, in_stock=True, status=S.FETCHED, **kw):
    out = {"status": status, "price": price, "shipping": shipping,
           "currency": "GBP", "in_stock": in_stock, "dispatch_days": kw.get("days", 3),
           "error": kw.get("error", ""), "available_qty": kw.get("qty"),
           "carrier": kw.get("carrier", "Royal Mail Tracked 48"),
           "postage_text": kw.get("postage_text", "Free Royal Mail Tracked 48"),
           "delivery_min": kw.get("dmin", "2026-08-19"),
           "delivery_max": kw.get("dmax", "2026-08-20"),
           "delivery_postcode": kw.get("pc", "B11AA"),
           "checked_at": kw.get("at", "2026-08-17 09:00:00")}
    return out


print("=== cheapest first, and a dead link never leads ===")
# Three suppliers. The DEAREST is in stock, the CHEAPEST has ended, and one is
# mid-priced and fine. Cheapest-of-the-buyable must win, and the ended one -- which
# has no price at all -- must not sort to the front on a missing number.
a = add("https://www.ebay.co.uk/itm/1", "dear but available")
b = add("https://www.ebay.co.uk/itm/2", "mid and fine")
c = add("https://www.ebay.co.uk/itm/3", "cheap but ended")
R.record_check(CFG, a, reading(19.00, 0.0))
R.record_check(CFG, b, reading(11.00, 1.50))
R.record_check(CFG, c, reading(None, None, in_stock=None, status=S.GONE,
                               error="HTTP 404 Not Found"))
opts = OS.options_for(CFG, WS, MKT, SKU, sell_price=30.00, now=NOW)
check("all three are listed", len(opts), 3)
check("  the cheapest BUYABLE one is first", opts[0]["label"], "mid and fine")
check("  then the dearer one", opts[1]["label"], "dear but available")
check("  and the ended one is last", opts[2]["label"], "cheap but ended")
check("  the ended one is marked dead", opts[2]["state"], OS.DEAD)
truthy("the first is flagged as the one to use", opts[0]["cheapest"])
falsy("  and the dead one never is", opts[2]["cheapest"])
check("landed cost is item + postage", opts[0]["landed"], 12.50)

print("\n=== profit per link, from the one pricing function ===")
# 30.00 sold, 12.50 landed, 15% referral, plus the label and ads allowances.
want = P.achieved(30.00, 12.50, 0.15,
                  S.DEFAULT_RULE["shipping_label"], S.DEFAULT_RULE["ads_margin"])
check("profit matches listing/pricing.achieved", opts[0]["profit"], want["profit"])
check("  and so does the ROI", opts[0]["roi_pct"], want["roi_pct"])
check("  and the margin", opts[0]["margin_pct"], want["margin_pct"])
# NOT recomputed here with its own formula -- that is the whole point. If this
# ever disagrees, the order screen and the repricer are pricing differently.
truthy("the dearer link earns less", opts[1]["profit"] < opts[0]["profit"])
check("a dead link has no profit", opts[2]["profit"], None)

print("\n=== nothing is invented without a sale price ===")
noprice = OS.options_for(CFG, WS, MKT, SKU, sell_price=None, now=NOW)
check("no sell price -> no profit figure", noprice[0]["profit"], None)
check("  but the cost is still shown", noprice[0]["landed"], 12.50)

print("\n=== how it gets to the buyer, and when ===")
check("the carrier eBay named", opts[0]["carrier"], "Royal Mail Tracked 48")
check("  the postage line", opts[0]["postage_text"], "Free Royal Mail Tracked 48")
# The wording the owner used: "delivery estimated between wed 19 aug and thu 20
# aug". Formatted on the server so the order screen and the repricer read alike.
check("  the window, in words", opts[0]["delivery_text"], "Wed 19 Aug to Thu 20 Aug")
check("  and the postcode it was worked out for",
      opts[0]["delivery_postcode"], "B11AA")
check("  handling days come through", opts[0]["dispatch_days"], 3)
# One date only, when eBay gives one date.
R.record_check(CFG, b, reading(11.00, 1.50, dmin="2026-08-20", dmax="2026-08-20"))
one = OS.options_for(CFG, WS, MKT, SKU, sell_price=30.00, now=NOW)
check("a single date is not printed twice",
      [o for o in one if o["source_id"] == b][0]["delivery_text"], "Thu 20 Aug")
# THE DAY NAMES MUST NOT FOLLOW THE MACHINE'S LANGUAGE. A server set to another
# locale would print a day name the owner does not read.
#
# Asserted against the CODE, not the file: the comment in order_sources.py says
# "done by hand rather than with strftime", so a plain substring search over the
# whole file fails on my own explanation. This has caught me more than once --
# always strip the prose before asserting on source text.
import ast                                                     # noqa: E402
_osrc_tree = ast.parse(open(os.path.join("domain", "order_sources.py"),
                            encoding="utf-8").read())
for _n in ast.walk(_osrc_tree):
    if isinstance(_n, (ast.Module, ast.ClassDef, ast.FunctionDef)):
        _b = getattr(_n, "body", [])
        if (_b and isinstance(_b[0], ast.Expr)
                and isinstance(_b[0].value, ast.Constant)
                and isinstance(_b[0].value.value, str)):
            _b[0].value.value = ""
_osrc_code = ast.unparse(_osrc_tree)
falsy("day and month names are written out, not localised",
      "strftime" in _osrc_code)
truthy("  the names are spelled out in the code", "'Aug'" in _osrc_code
       or '"Aug"' in _osrc_code)

print("\n=== a stale reading says so ===")
# A price from four days ago is not a price you can buy at.
R.record_check(CFG, b, reading(11.00, 1.50, at="2026-08-13 09:00:00"))
old = OS.options_for(CFG, WS, MKT, SKU, sell_price=30.00, now=NOW)
stale = [o for o in old if o["source_id"] == b][0]
truthy("a four-day-old reading is flagged stale", stale["stale"])
truthy("  and its age is reported", stale["age_minutes"] > 4000)
R.record_check(CFG, b, reading(11.00, 1.50))          # put it back
fresh = [o for o in OS.options_for(CFG, WS, MKT, SKU, now=NOW)
         if o["source_id"] == b][0]
falsy("a reading from this morning is not", fresh["stale"])

print("\n=== the summary, which the alert is built on ===")
s = OS.summary(OS.options_for(CFG, WS, MKT, SKU, sell_price=30.00, now=NOW))
check("counts the sources", s["total"], 3)
check("  how many can be bought from", s["buyable"], 2)
check("  and how many are gone", s["dead"], 1)
falsy("not every source is gone, so no alarm", s["all_dead"])
check("the best profit available", s["best_profit"],
      max(o["profit"] for o in opts if o["profit"] is not None))

print("\n=== every link gone -> the alert fires ===")
R.record_check(CFG, a, reading(None, None, in_stock=False))
R.record_check(CFG, b, reading(None, None, in_stock=False))
allgone = OS.summary(OS.options_for(CFG, WS, MKT, SKU, now=NOW))
check("nothing is buyable", allgone["buyable"], 0)
truthy("  and the alarm is raised", allgone["all_dead"])

print("\n=== but NOT when we simply could not look ===")
# THE FALSE-ALARM GUARD. A failed fetch is not an out-of-stock. An alert that
# fires whenever eBay has a bad minute stops being read, and then the real one is
# missed too.
R.record_check(CFG, a, reading(None, None, in_stock=None, status=S.FAILED,
                              error="HTTP 503"))
R.record_check(CFG, b, reading(None, None, in_stock=None, status=S.FAILED,
                              error="timed out"))
unread = OS.summary(OS.options_for(CFG, WS, MKT, SKU, now=NOW))
check("still nothing buyable", unread["buyable"], 0)
check("  two readings are simply unknown", unread["unknown"], 2)
falsy("  and the out-of-stock alarm does NOT fire", unread["all_dead"])

print("\n=== the account-wide alert list ===")
R.enrol(CFG, WS, MKT, SKU)
# A second SKU with a supplier that is definitely out of stock.
R.add_source(CFG, WS, MKT, "SKU-2", "https://www.ebay.co.uk/itm/9", kind="ebay")
sid2 = R.sources_for(CFG, WS, MKT, "SKU-2")[0]["id"]
R.record_check(CFG, sid2, reading(None, None, in_stock=False))
R.enrol(CFG, WS, MKT, "SKU-2")
# A third with no suppliers at all -- NOT an alert, just unconfigured.
R.enrol(CFG, WS, MKT, "SKU-3")

got = A.for_account(CFG, WS, MKT, now=NOW)
skus = sorted(x["sku"] for x in got["alerts"])
check("only the SKU with everything dead is an alert", skus, ["SKU-2"])
check("  the one we could not read is reported separately",
      sorted(x["sku"] for x in got["unreadable"]), ["SKU-1"])
truthy("  a SKU with no suppliers at all is neither",
       "SKU-3" not in skus
       and "SKU-3" not in [x["sku"] for x in got["unreadable"]])
check("  and all three were looked at", got["checked"], 3)

print("\n=== the alert says what to do about it ===")
one = got["alerts"][0]
line = A.sentence(one)
truthy("it names the SKU", "SKU-2" in line)
truthy("  says every supplier is gone", "out of stock or ended" in line)
truthy("  and says it is still selling on Amazon, which is the urgent part",
       "still live on Amazon" in line)
check("  the kind is machine-readable too", one["kind"], A.ALL_GONE)
# The unreadable one must NOT read like an emergency.
soft = A.sentence(got["unreadable"][0])
truthy("the unreadable one asks for a re-check", "Press Check" in soft)
falsy("  and does not claim anything is out of stock",
      "out of stock or ended" in soft)

print("\n=== no second copy of the truth is kept ===")
# The alert is a question asked of the readings every time. A table of alerts
# would be a second copy that drifts the moment a sweep dies half way.
src = open(os.path.join("domain", "stock_alerts.py"), encoding="utf-8").read()
falsy("stock_alerts creates no table of its own",
      "CREATE TABLE" in src or "INSERT INTO" in src)
truthy("  and the file says why", "second copy" in src)
# Prove it: change a reading and the alert changes with no sweep, no write.
R.record_check(CFG, sid2, reading(9.99, 0.0, in_stock=True))
after = A.for_account(CFG, WS, MKT, now=NOW)
check("a supplier coming back clears the alert by itself",
      [x["sku"] for x in after["alerts"]], [])

print("\n" + ("FAILURES: %s" % ", ".join(fails) if fails else "FAILURES: 0"))
sys.exit(1 if fails else 0)
