"""Four trackers, one engine.

    Orbit's menu has BSR Tracker, BuyBox Tracker, Price Tracker and Fee Tracker,
    plus "All Trackers" over the top and a single Alerts count fed by all four.

Looked at closely they are one thing pointed at different numbers, so there is
one engine and the metrics are data. This test is mostly about the two places
that engine could be quietly, invisibly wrong:

  WHICH WAY IS GOOD. A sales rank of 900 beats 4,000; a price of 9.99 does not
  beat 12.99 when you are trying to hold a price. Get this backwards and every
  alert is exactly inverted -- and nothing in the numbers themselves says so.

  A MISSING READING IS NOT A ZERO. This app has already been bitten twice by
  that shape: bool() of Amazon's dict made every order claim the buyer wanted to
  cancel it, and a self-perpetuating "partial" flag froze two accounts' stock.
  A monitoring screen that turns a failed fetch into a perfect score is worse
  than one that shows nothing.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain import trackers as T  # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def truthy(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="trk")
CFG = os.path.join(TMP, "config.json")
WS = "jack_uk"

print("== the four trackers are one engine ==")
check("four metrics", sorted(T.METRICS), ["bsr", "buybox", "fee", "price"])
truthy("each names its Orbit tracker",
       all(m.get("tracker") for m in T.METRICS.values()))
# The field that makes the whole thing correct or exactly backwards.
check("a lower sales rank is better", T.METRICS["bsr"]["good"], T.LOWER_IS_BETTER)
check("a lower Buy Box price is better", T.METRICS["buybox"]["good"], T.LOWER_IS_BETTER)
check("a lower fee is better", T.METRICS["fee"]["good"], T.LOWER_IS_BETTER)
# The one that goes the other way, which is why it cannot be assumed.
check("a HIGHER selling price is better", T.METRICS["price"]["good"], T.HIGHER_IS_BETTER)

print("\n== drift is signed the same way for every metric ==")
# Positive means WORSE, whichever direction better happens to be. Every caller
# then uses one rule instead of each remembering which way round its metric is.
check("rank 1200 against a target of 1000 is 20% worse",
      round(T.drift(1200, 1000, T.LOWER_IS_BETTER), 4), 0.2)
check("  rank 800 against 1000 is 20% better",
      round(T.drift(800, 1000, T.LOWER_IS_BETTER), 4), -0.2)
check("price 8.00 against a target of 10.00 is 20% WORSE",
      round(T.drift(8.0, 10.0, T.HIGHER_IS_BETTER), 4), 0.2)
check("  price 12.00 against 10.00 is 20% better",
      round(T.drift(12.0, 10.0, T.HIGHER_IS_BETTER), 4), -0.2)
check("no target means no drift", T.drift(10, None, T.LOWER_IS_BETTER), None)
check("no value means no drift", T.drift(None, 10, T.LOWER_IS_BETTER), None)
# A zero target would divide by zero; it is unanswerable, not infinite.
check("a zero target means no drift", T.drift(10, 0, T.LOWER_IS_BETTER), None)

print("\n== unknown is its own answer, and never a pass ==")
check("no reading is UNKNOWN",
      T.status_for(None, 100, T.LOWER_IS_BETTER, 0.2), T.UNKNOWN)
# An ASIN you never gave a target to cannot be off track -- but calling it OK
# would claim a judgement nobody made.
check("no target is UNKNOWN too",
      T.status_for(100, None, T.LOWER_IS_BETTER, 0.2), T.UNKNOWN)
check("inside tolerance is OK",
      T.status_for(1100, 1000, T.LOWER_IS_BETTER, 0.2), T.OK)
check("outside tolerance is OFF",
      T.status_for(1300, 1000, T.LOWER_IS_BETTER, 0.2), T.OFF)
check("better than target is OK, never OFF",
      T.status_for(500, 1000, T.LOWER_IS_BETTER, 0.2), T.OK)

print("\n== the watch list ==")
truthy("nothing is tracked to begin with", T.tracked(CFG, WS) == {})
r = T.watch_set(CFG, WS, "B00TEST0001", "bsr", on=True, target=1000)
truthy("a tracker can be switched on", r.get("ok"))
check("  and remembers the target",
      T.watch_get(CFG, WS, "B00TEST0001", "bsr")["target"], 1000.0)
check("  it appears in the tracked list", list(T.tracked(CFG, WS)), ["B00TEST0001"])
T.watch_set(CFG, WS, "B00TEST0002", "bsr", on=False, target=500)
check("  a target without tracking does NOT get fetched",
      list(T.tracked(CFG, WS)), ["B00TEST0001"])
truthy("an unknown metric is refused",
       not T.watch_set(CFG, WS, "B00TEST0001", "nonsense", on=True).get("ok"))

# The same ASIN under two accounts must not share a row: these accounts do list
# the same ASIN at different prices, and one shared row would have them
# overwriting each other -- which reads as a price flapping for no reason.
T.watch_set(CFG, "other_acct", "B00TEST0001", "price", on=True, target=9.99)
check("another account's tracking is separate",
      list(T.tracked(CFG, WS)), ["B00TEST0001"])
check("  and has its own metrics",
      sorted(T.tracked(CFG, "other_acct")["B00TEST0001"]), ["price"])

print("\n== a failed fetch is not a data point ==")
truthy("a real reading is stored", T.record(CFG, WS, "B00TEST0001", "bsr", 1200))
truthy("None is refused", not T.record(CFG, WS, "B00TEST0001", "bsr", None))
truthy("  so is a non-number", not T.record(CFG, WS, "B00TEST0001", "bsr", "n/a"))
truthy("  and so is NaN", not T.record(CFG, WS, "B00TEST0001", "bsr", float("nan")))
check("only the real one is in the history",
      [h["v"] for h in T.history(CFG, WS, "B00TEST0001", "bsr")], [1200.0])
truthy("a reading for an unknown metric is refused",
       not T.record(CFG, WS, "B00TEST0001", "nonsense", 5))

print("\n== the rows a screen draws ==")
T.record(CFG, WS, "B00TEST0001", "bsr", 1500)
rows = T.rows(CFG, WS)
check("one row per tracked ASIN per metric", len(rows), 1)
row = rows[0]
check("  the value is the newest reading", row["value"], 1500.0)
check("  the target came from the watch list", row["target"], 1000.0)
check("  drift is 50% worse", round(row["drift"], 4), 0.5)
check("  which is off track", row["status"], T.OFF)
# Movement is reported but is NOT what raises the alert: a rank that has been
# bad for a month is a problem every day of it, and an alert firing only on the
# day it moved would have gone quiet after the first one.
check("  the change since the last reading is reported", row["change"], 300.0)
truthy("  and the reading is dated", row["last_at"])
check("  with the number of readings behind it", row["points"], 2)

print("\n== one alert count, over all four ==")
a = T.alerts(CFG, WS)
check("the off-track row is an alert", a["count"], 1)
T.watch_set(CFG, WS, "B00TEST0003", "price", on=True, target=10.0)
T.record(CFG, WS, "B00TEST0003", "price", 10.10)
check("  a row that is on target is not", T.alerts(CFG, WS)["count"], 1)
# An ASIN with no reading at all must not silently count as fine.
T.watch_set(CFG, WS, "B00TEST0004", "buybox", on=True, target=20.0)
check("  and one with no reading is neither ok nor an alert",
      T.alerts(CFG, WS)["count"], 1)
unknowns = [r for r in T.rows(CFG, WS) if r["status"] == T.UNKNOWN]
check("  it is reported as UNKNOWN", len(unknowns), 1)
check("  with no value invented for it", unknowns[0]["value"], None)

print("\n== the All Trackers summary ==")
s = T.summary(CFG, WS)
check("every tracker is listed even with nothing in it", sorted(s), ["bsr", "buybox", "fee", "price"])
check("  bsr has one tracked, one off", (s["bsr"]["tracked"], s["bsr"]["off"]), (1, 1))
check("  price has one tracked, none off", (s["price"]["tracked"], s["price"]["off"]), (1, 0))
check("  buybox's single row is unknown", s["buybox"]["unknown"], 1)
check("  fee has nothing tracked", s["fee"]["tracked"], 0)

print("\n== the history is bounded ==")
# Left unbounded this file grows without limit on an hourly schedule.
for i in range(T.MAX_HISTORY + 25):
    T.record(CFG, WS, "B00TEST0009", "bsr", 1000 + i)
check("it stops at MAX_HISTORY",
      len(T.history(CFG, WS, "B00TEST0009", "bsr")), T.MAX_HISTORY)
check("  keeping the NEWEST readings",
      T.history(CFG, WS, "B00TEST0009", "bsr")[-1]["v"],
      float(1000 + T.MAX_HISTORY + 24))

print("\n== a corrupt file reads as empty, never as a crash ==")
with open(T._path(CFG), "w", encoding="utf-8") as fh:
    fh.write("{ this is not json")
check("a broken store still loads", T.load(CFG), {"watch": {}, "history": {}})
check("  and the screen just has no rows", T.rows(CFG, WS), [])

shutil.rmtree(TMP, ignore_errors=True)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
