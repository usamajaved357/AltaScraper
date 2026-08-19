"""domain/search_query.py -- Search Query Performance: what people typed.

    Orbit calls this Keywords (SQP). It is the one Amazon report that says what
    buyers actually SEARCHED FOR before they reached a listing, and what
    happened at each step afterwards.

WHY IT IS WORTH ITS OWN SCREEN.

Every other report in this app measures what happened AFTER somebody arrived.
Sessions, conversion, units -- all downstream of a search that either found you
or did not. SQP is the only place that shows the search itself, and it breaks
each query into a funnel:

    impressions   the query happened and you were on the page
    clicks        somebody clicked YOUR listing
    cart adds     they added it
    purchases     they bought it

...each with a share: your slice of everything that query produced across all
sellers. That share is the number nobody else can give you, and it is what turns
"we sold four" into "we sold four out of two hundred, so there are a hundred and
ninety-six we did not".

THE DIAGNOSIS IS WHERE THE FUNNEL BREAKS, and it is a genuinely different action
each time. This module names it rather than leaving a wall of numbers:

    impression share low     they are not seeing you at all -- a ranking and
                             advertising problem
    click share low          they see you and scroll past -- main image, title,
                             price, review count
    cart share low           they click and leave -- the listing page itself:
                             bullets, A+, images, price against the page
    purchase share low       they add and abandon -- postage, delivery date,
                             the basket

Told apart, those are four different jobs. Averaged into "conversion is bad",
they are none.

WHAT THIS MODULE WILL NOT DO.

    IT WILL NOT INVENT A SHARE. Amazon reports both the total for a query and
    your part of it. Where a total is missing the share is None, never zero --
    "0% of the clicks" and "we do not know" look identical on a screen and mean
    opposite things.

    IT WILL NOT RANK ON A HANDFUL OF IMPRESSIONS. A query with nine impressions
    and one click is a 11% click share and it means nothing. Anything below
    MIN_IMPRESSIONS is carried but never diagnosed, and says so.

ACCESS. This report needs Brand Registry. An account without it gets a clear
refusal from Amazon, which is reported as what it is -- a permission the account
does not have -- rather than as an empty week, because those two look the same
and only one of them is worth doing something about.
"""

REPORT_TYPE = "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT"

# Below this many impressions a query's shares are noise. Fifty is low enough to
# keep the long tail visible and high enough that one click cannot swing a share
# by twenty points.
MIN_IMPRESSIONS = 50

# A share below this, at the step where it first happens, is what gets named as
# the break. Not a universal truth -- a deliberately narrow niche product can sit
# under it happily -- which is why it is a threshold with a name rather than a
# number buried in a condition.
WEAK_SHARE = 0.15

# The funnel, in order. Each step names the share to look at, and what a low one
# actually means in terms of something a person can go and change.
STEPS = [
    {"key": "impression", "label": "Seen",
     "mine": "impressions", "total": "impressions_total",
     "means": "They are not seeing you for this search at all.",
     "do": "This is a ranking and advertising problem, not a listing problem: "
           "the page never gets looked at."},
    {"key": "click", "label": "Clicked",
     "mine": "clicks", "total": "clicks_total",
     "means": "They see you in the results and scroll past.",
     "do": "The main image, the title, the price and the review count are what "
           "they are judging -- nothing inside the listing has been read yet."},
    {"key": "cart", "label": "Added to basket",
     "mine": "cart_adds", "total": "cart_adds_total",
     "means": "They click through and leave without adding.",
     "do": "This one is the listing page itself: bullets, A+ content, the "
           "secondary images, and the price against what the page promises."},
    {"key": "purchase", "label": "Bought",
     "mine": "purchases", "total": "purchases_total",
     "means": "They add it to the basket and do not finish.",
     "do": "Postage cost, the delivery date shown, and anything that changes "
           "between the page and the checkout."},
]

STEP_INDEX = {s["key"]: s for s in STEPS}


def _n(v):
    """A number, or None. Amazon omits fields it has nothing for."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        v = v.strip().replace(",", "").replace("%", "")
        if not v:
            return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _share(mine, total):
    """Your part of a total, 0..1. None when it cannot be known.

    NOT zero when the total is missing. "0% of the clicks" and "we do not know
    how many clicks there were" look identical on a screen and mean opposite
    things -- the first is a problem to fix, the second is a gap in the data.
    """
    m, t = _n(mine), _n(total)
    if m is None or t is None or t <= 0:
        return None
    return m / t


def _dig(d, *names):
    """First present value among several possible field names.

    Amazon's JSON for this report nests differently between versions and
    marketplaces, and the field names have changed at least once. Reading
    several candidates is honest about that; guessing one and getting an empty
    column is not (CLAUDE.md Rule 4 -- do not guess a shape, read what is there).
    """
    for n in names:
        if isinstance(d, dict) and n in d and d[n] is not None:
            return d[n]
    return None


def parse(payload):
    """Amazon's report JSON -> a flat list of query rows.

    Tolerant by design: the report is returned as JSON whose exact nesting has
    changed between versions. Anything that cannot be read is skipped rather
    than crashing the screen, and the count of rows read is returned so a
    partial parse cannot masquerade as a quiet week.
    """
    rows = []
    if isinstance(payload, dict):
        data = (_dig(payload, "dataByAsin", "dataByDepartmentAndSearchTerm",
                     "data", "records") or [])
    elif isinstance(payload, list):
        data = payload
    else:
        data = []
    for r in data:
        if not isinstance(r, dict):
            continue
        q = _dig(r, "searchQuery", "search_query", "query", "searchTerm")
        if not q:
            continue
        imp = _dig(r, "impressionData", "impressions") or {}
        clk = _dig(r, "clickData", "clicks") or {}
        crt = _dig(r, "cartAddData", "cartAdds") or {}
        buy = _dig(r, "purchaseData", "purchases") or {}
        imp = imp if isinstance(imp, dict) else {}
        clk = clk if isinstance(clk, dict) else {}
        crt = crt if isinstance(crt, dict) else {}
        buy = buy if isinstance(buy, dict) else {}
        rows.append({
            "query": str(q),
            "asin": str(_dig(r, "asin", "childAsin") or ""),
            "rank": _n(_dig(r, "searchQueryScore", "searchFrequencyRank",
                            "search_frequency_rank")),
            "volume": _n(_dig(r, "searchQueryVolume", "searchVolume")),
            "impressions": _n(_dig(imp, "asinImpressionCount", "brandImpressionCount")),
            "impressions_total": _n(_dig(imp, "totalQueryImpressionCount", "totalCount")),
            "clicks": _n(_dig(clk, "asinClickCount", "brandClickCount")),
            "clicks_total": _n(_dig(clk, "totalClickCount", "totalCount")),
            "cart_adds": _n(_dig(crt, "asinCartAddCount", "brandCartAddCount")),
            "cart_adds_total": _n(_dig(crt, "totalCartAddCount", "totalCount")),
            "purchases": _n(_dig(buy, "asinPurchaseCount", "brandPurchaseCount")),
            "purchases_total": _n(_dig(buy, "totalPurchaseCount", "totalCount")),
        })
    return rows


def diagnose(row, min_impressions=MIN_IMPRESSIONS, weak=WEAK_SHARE):
    """Where this query's funnel breaks, and what to do about it.

    Returns the FIRST weak step, because the funnel is sequential: if they are
    not seeing you, the click share is measured on the few who did and telling
    somebody to improve their main image is advice about the wrong problem.
    """
    out = {"shares": {}, "break": "", "means": "", "do": "", "note": ""}
    for s in STEPS:
        out["shares"][s["key"]] = _share(row.get(s["mine"]), row.get(s["total"]))
    imp = _n(row.get("impressions_total")) or _n(row.get("impressions"))
    if imp is None:
        out["note"] = "Amazon reported no impression figures for this query."
        return out
    if imp < min_impressions:
        # One click on nine impressions is an 11% share and means nothing.
        out["note"] = ("Too few impressions (%d) to read anything into the "
                       "shares." % int(imp))
        return out
    for s in STEPS:
        sh = out["shares"].get(s["key"])
        if sh is None:
            # A step Amazon did not report is not a step that failed. Stopping
            # here would blame the last step it DID report.
            continue
        if sh < weak:
            out["break"] = s["key"]
            out["means"] = s["means"]
            out["do"] = s["do"]
            return out
    out["note"] = "Nothing obviously weak in this funnel."
    return out


def build(rows, min_impressions=MIN_IMPRESSIONS, weak=WEAK_SHARE, limit=200):
    """The screen: every query with its funnel, its shares and its diagnosis.

    Sorted by the size of the OPPORTUNITY -- total purchases for the query that
    were not yours -- rather than by your own sales. The queries worth working
    on are precisely the big ones you are losing, and sorting by your own units
    puts those at the bottom.
    """
    out = []
    for r in rows:
        d = diagnose(r, min_impressions, weak)
        mine = _n(r.get("purchases")) or 0
        total = _n(r.get("purchases_total"))
        missed = (total - mine) if total is not None else None
        row = dict(r)
        row.update({"shares": d["shares"], "break": d["break"],
                    "means": d["means"], "do": d["do"], "note": d["note"],
                    "missed": missed})
        out.append(row)
    out.sort(key=lambda x: (-(x["missed"] if x["missed"] is not None else -1),
                            x["query"]))
    return out[:limit] if limit else out


def summary(rows):
    """Counts per break point -- which job would move the most queries."""
    out = {s["key"]: {"key": s["key"], "label": s["label"], "count": 0,
                      "missed": 0.0, "means": s["means"], "do": s["do"]}
           for s in STEPS}
    out["none"] = {"key": "none", "label": "Nothing obviously weak",
                   "count": 0, "missed": 0.0, "means": "", "do": ""}
    out["unreadable"] = {"key": "unreadable", "label": "Too little data to say",
                         "count": 0, "missed": 0.0, "means": "", "do": ""}
    for r in rows:
        b = r.get("break") or ("unreadable" if r.get("note", "").startswith("Too few")
                               or r.get("note", "").startswith("Amazon reported no")
                               else "none")
        slot = out.get(b) or out["none"]
        slot["count"] += 1
        if r.get("missed"):
            slot["missed"] += r["missed"]
    return out
