"""Search Query Performance -- what people typed, and where the funnel breaks.

    Orbit calls it Keywords (SQP).

It is the only report that shows the search itself rather than what happened
after somebody arrived, and its value is entirely in the SHARE: your slice of
what a query produced across all sellers. That is what turns "we sold four" into
"we sold four out of two hundred".

Which makes the failure modes specific:

  * a share invented where the total is missing -- "0% of the clicks" and "we do
    not know how many clicks there were" look identical and mean opposite things
  * a diagnosis from nine impressions, where one click is an 11% share
  * blaming the wrong step, because the funnel is sequential: if nobody is
    seeing you, your click share is measured on the handful who did
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain import search_query as Q  # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def close(label, got, want, tol=0.001):
    ok = got is not None and abs(got - want) <= tol
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want~%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def truthy(label, got):
    check(label, bool(got), True)


def row(**kw):
    base = {"query": "q", "impressions": 1000, "impressions_total": 2000,
            "clicks": 100, "clicks_total": 200,
            "cart_adds": 20, "cart_adds_total": 40,
            "purchases": 10, "purchases_total": 20}
    base.update(kw)
    return base


print("== the funnel is four steps, each with a different job ==")
check("four steps in order",
      [s["key"] for s in Q.STEPS], ["impression", "click", "cart", "purchase"])
truthy("each says what a low share MEANS", all(s["means"] for s in Q.STEPS))
truthy("and what to actually do about it", all(s["do"] for s in Q.STEPS))
# The four are genuinely different actions -- that is the whole point of naming
# the step rather than reporting "conversion is bad".
truthy("the advice differs per step",
       len({s["do"] for s in Q.STEPS}) == len(Q.STEPS))

print("\n== a share is never invented ==")
check("a straight share", Q._share(10, 40), 0.25)
# NOT zero. A missing total is a gap in the data, not a wipeout.
check("no total means no share", Q._share(10, None), None)
check("  a zero total means no share either", Q._share(10, 0), None)
check("  and no value of your own means no share", Q._share(None, 40), None)

print("\n== a handful of impressions is not evidence ==")
d = Q.diagnose(row(impressions_total=9, impressions=9, clicks=1, clicks_total=9))
check("no diagnosis below the floor", d["break"], "")
truthy("  and it says why", "Too few impressions" in d["note"])
# The shares are still computed and shown -- they are just not judged.
truthy("  the shares are still reported", d["shares"]["click"] is not None)
d = Q.diagnose(row(impressions_total=None, impressions=None))
truthy("no impression figures at all is said out loud",
       "no impression figures" in d["note"])

print("\n== the first weak step is the one named ==")
# The funnel is sequential. If they are not seeing you, your click share is
# measured on the few who did, and advice about the main image is advice about
# the wrong problem.
d = Q.diagnose(row(impressions=100, impressions_total=5000,   # 2% seen
                   clicks=1, clicks_total=500))               # also weak
check("the break is the earliest weak step", d["break"], "impression")
truthy("  with its own meaning", "not seeing you" in d["means"])
truthy("  and a ranking/advertising action", "advertising" in d["do"])

d = Q.diagnose(row(impressions=4000, impressions_total=5000,  # 80% seen
                   clicks=10, clicks_total=500))              # 2% clicked
check("a healthy first step passes to the second", d["break"], "click")
truthy("  which is about the search result, not the page",
       "scroll past" in d["means"])

d = Q.diagnose(row(impressions=4000, impressions_total=5000,
                   clicks=400, clicks_total=500,
                   cart_adds=2, cart_adds_total=200))
check("then the listing page", d["break"], "cart")
truthy("  named as the page itself", "listing page itself" in d["means"] or
       "listing page itself" in d["do"])

d = Q.diagnose(row(impressions=4000, impressions_total=5000,
                   clicks=400, clicks_total=500,
                   cart_adds=180, cart_adds_total=200,
                   purchases=2, purchases_total=200))
check("then the basket", d["break"], "purchase")
truthy("  which is postage and delivery", "Postage" in d["do"])

print("\n== a step Amazon did not report is not a step that failed ==")
# Stopping at an unreported step would blame the last one it DID report.
d = Q.diagnose(row(clicks_total=None, clicks=None,
                   cart_adds=180, cart_adds_total=200,
                   purchases=90, purchases_total=200))
check("the unreported step is skipped, not blamed", d["break"], "")
check("  its share is None", d["shares"]["click"], None)

print("\n== a healthy funnel says so ==")
d = Q.diagnose(row())
check("nothing is named", d["break"], "")
truthy("  and it says nothing is obviously weak", "Nothing obviously weak" in d["note"])

print("\n== the list is sorted by what you are LOSING ==")
# The queries worth working on are the big ones you are losing. Sorting by your
# own units puts those at the bottom.
rows = [
    row(query="small win", purchases=9, purchases_total=10),      # missed 1
    row(query="big miss", purchases=2, purchases_total=500),      # missed 498
    row(query="middling", purchases=5, purchases_total=60),       # missed 55
]
built = Q.build(rows)
check("the biggest miss is first", built[0]["query"], "big miss")
check("  then the middle one", built[1]["query"], "middling")
check("  and your best seller is last", built[2]["query"], "small win")
check("  the missed figure is carried", built[0]["missed"], 498.0)

print("\n== the parser reads what Amazon sends ==")
# The nesting has changed at least once between report versions, so several
# field names are tried rather than one being guessed (CLAUDE.md Rule 4).
payload = {"dataByAsin": [{
    "searchQuery": "protein powder", "asin": "B00X",
    "searchQueryVolume": 1234,
    "impressionData": {"asinImpressionCount": 100, "totalQueryImpressionCount": 1000},
    "clickData": {"asinClickCount": 10, "totalClickCount": 200},
    "cartAddData": {"asinCartAddCount": 3, "totalCartAddCount": 50},
    "purchaseData": {"asinPurchaseCount": 1, "totalPurchaseCount": 25},
}]}
p = Q.parse(payload)
check("one row read", len(p), 1)
check("  the query", p[0]["query"], "protein powder")
check("  your impressions", p[0]["impressions"], 100.0)
check("  and the query's total", p[0]["impressions_total"], 1000.0)
close("  so the impression share is 10%",
      Q._share(p[0]["impressions"], p[0]["impressions_total"]), 0.10)
# Rows without a query are not rows.
check("a row with no query is skipped", len(Q.parse({"dataByAsin": [{"asin": "B0"}]})), 0)
check("junk parses to nothing rather than crashing", Q.parse("not a report"), [])
check("  and so does None", Q.parse(None), [])

print("\n== the summary says which job moves the most ==")
s = Q.summary(Q.build([
    row(query="a", impressions=10, impressions_total=5000),
    row(query="b", impressions=10, impressions_total=5000),
    row(query="c", impressions=4000, impressions_total=5000, clicks=1, clicks_total=500),
    row(query="d"),
    row(query="e", impressions_total=5, impressions=5),
]))
check("two queries break at being seen", s["impression"]["count"], 2)
check("  one at the click", s["click"]["count"], 1)
check("  one is healthy", s["none"]["count"], 1)
check("  and one cannot be read", s["unreadable"]["count"], 1)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
