"""domain/leading.py -- yesterday against its own history, measured in sigma.

    Orbit's Leading Indicators screen: each figure for yesterday, next to the
    historical mean and standard deviation, expressed in standard deviations,
    with an ON TRACK / off status.

WHY SIGMA AND NOT A PERCENTAGE.

"Sessions are down 22%" means nothing on its own. If this listing's sessions
swing 30% every day of the week, 22% is Tuesday. If they have not moved more
than 4% in two months, 22% is an emergency. The percentage is the same number in
both cases and only one of them is worth getting out of bed for.

Sigma answers the question the percentage cannot: is this a NORMAL amount of
movement for this figure, on this account? That is the entire point of the
screen -- it is a filter for attention, and a filter that fires on ordinary
Tuesday noise is a filter nobody reads.

WHAT MAKES THIS HONEST OR DISHONEST.

  A SMALL SAMPLE HAS NO OPINION. Standard deviation over four days is not a
  measure of anything. Below MIN_DAYS the answer is "not enough history yet",
  said out loud, rather than a confident sigma computed from noise. This is the
  single easiest way for a screen like this to look authoritative and be
  meaningless.

  A FLAT HISTORY HAS NO SIGMA. If a figure has not moved at all, the standard
  deviation is zero and every deviation is infinite. That is reported as a plain
  change, not as an infinite sigma, because "sales moved from 0 to 1, which is
  +inf sigma" is technically true and useless.

  YESTERDAY IS NOT IN ITS OWN BASELINE. The mean and deviation are computed from
  the days BEFORE yesterday. Including it drags the baseline towards the value
  being judged and quietly shrinks every genuine spike -- worst exactly when the
  spike is biggest, which is when you needed to see it.

  MISSING IS NOT ZERO. A day with no row is a day Amazon has not reported, not a
  day with no sales. Those days are skipped, and how many were found is
  returned, so a figure resting on three real days out of thirty cannot pass
  itself off as a month.

WHICH WAY IS GOOD IS WRITTEN DOWN, not inferred -- exactly as in
domain/trackers.py, and for the same reason: a rising ACOS and rising sales are
both "up", and treating them alike gets one of them exactly backwards.
"""
import datetime
import math

LOWER_IS_BETTER = "lower"
HIGHER_IS_BETTER = "higher"

# Below this many usable days, no sigma is reported at all. Twelve is chosen so
# a standard deviation spans more than one week -- a shorter window measures the
# shape of the week rather than the behaviour of the figure, and every Monday
# then looks like an event.
MIN_DAYS = 12

# How many days of history to look back over. Long enough to know what normal
# looks like, short enough that a change of strategy two months ago is not still
# setting the baseline.
WINDOW_DAYS = 45

# Beyond this many standard deviations, a figure is called out. Two sigma is
# roughly the outer 5% of ordinary variation: often enough to be worth a screen,
# rare enough that seeing one means something.
SIGMA_ALERT = 2.0

ON_TRACK = "on_track"
WATCH = "watch"
OFF = "off"
UNKNOWN = "unknown"

# The figures, and which direction is good for each.
#
# `expr` is the SQL that produces the number for one day; `agg` says how to
# combine the per-ASIN rows into an account total. A rate cannot be summed --
# averaging conversion across products weights a product with four sessions the
# same as one with four thousand -- so rates are recomputed from their parts.
INDICATORS = [
    {"key": "sessions", "label": "Sessions", "good": HIGHER_IS_BETTER,
     "kind": "count", "agg": "sum", "col": "sessions",
     "blurb": "How many people looked at your listings."},
    {"key": "page_views", "label": "Page views", "good": HIGHER_IS_BETTER,
     "kind": "count", "agg": "sum", "col": "page_views",
     "blurb": "Views including repeat looks in the same session."},
    {"key": "units", "label": "Units sold", "good": HIGHER_IS_BETTER,
     "kind": "count", "agg": "sum", "col": "units",
     "blurb": "How many items were bought."},
    {"key": "ordered_sales", "label": "Sales", "good": HIGHER_IS_BETTER,
     "kind": "money", "agg": "sum", "col": "ordered_sales",
     "blurb": "What those units were worth."},
    # report_only: the Sales & Traffic report counts ORDER ITEMS here; days the
    # live Orders feed has taken over carry distinct orders instead, so they
    # are left out rather than mixed into one baseline (see series()).
    {"key": "orders", "label": "Orders", "good": HIGHER_IS_BETTER,
     "kind": "count", "agg": "sum", "col": "orders", "report_only": True,
     "blurb": "Order items, as Amazon's Sales & Traffic report counts them. "
              "Days filled from the live order feed (which counts whole "
              "orders) are left out so one measure is compared with itself."},
    # Rates: recomputed from the parts, never averaged.
    {"key": "conversion", "label": "Conversion", "good": HIGHER_IS_BETTER,
     "kind": "percent", "agg": "ratio", "num": "units", "den": "sessions",
     "scale": 100.0,
     "blurb": "Of the people who looked, how many bought. Units per session."},
    {"key": "buy_box", "label": "Buy Box share", "good": HIGHER_IS_BETTER,
     "kind": "percent", "agg": "weighted", "col": "buy_box_pct",
     "weight": "sessions",
     "blurb": "How often you held the Buy Box, weighted by how busy each "
              "listing was."},
    {"key": "avg_price", "label": "Average selling price", "good": HIGHER_IS_BETTER,
     "kind": "money", "agg": "ratio", "num": "ordered_sales", "den": "units",
     "scale": 1.0,
     "blurb": "What the average unit went for."},
]

INDEX = {i["key"]: i for i in INDICATORS}


def _f(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _stdev(xs, mean=None):
    """Sample standard deviation. None when fewer than two points.

    The SAMPLE form (n-1) rather than the population form, because these days
    are a sample of how the figure behaves and not the whole of it. With n
    around 45 the difference is small; with n around 12 it is not, and 12 is the
    floor this module allows.
    """
    n = len(xs)
    if n < 2:
        return None
    m = _mean(xs) if mean is None else mean
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var)


def _src(r):
    """orders_source off a sqlite row that may not carry the column."""
    try:
        return r["orders_source"]
    except (KeyError, IndexError):
        return None


def series(rows, ind):
    """{date: value} for one indicator, from raw per-day-per-ASIN rows.

    `rows` are sqlite rows (or dicts) with a `date` and the columns named in the
    indicator. Rows are grouped by date and combined by the indicator's own rule.
    """
    by_day = {}
    for r in rows:
        d = str(r["date"] if not isinstance(r, dict) else r.get("date") or "")
        if not d:
            continue
        by_day.setdefault(d, []).append(r)

    def col(r, name):
        try:
            return _f(r[name] if not isinstance(r, dict) else r.get(name))
        except (KeyError, IndexError):
            return None

    out = {}
    agg = ind["agg"]
    for d, day_rows in by_day.items():
        if ind.get("report_only"):
            # ONE MEASURE, OR NO BASELINE (bug round 30 Sep 2026). The live
            # Orders feed (domain/live_reconcile, orders_source='orders_api')
            # writes DISTINCT orders into the '*' row, where the Sales &
            # Traffic report writes ORDER ITEMS -- a two-item order is one
            # against two. A month of report days with a fortnight of live
            # days on top judged every live day as a drop. Days the live feed
            # owns are left out of this indicator entirely.
            day_rows = [r for r in day_rows
                        if str((r.get("orders_source") if isinstance(r, dict)
                                else _src(r)) or "") != "orders_api"]
            if not day_rows:
                continue
        if agg == "sum":
            vals = [col(r, ind["col"]) for r in day_rows]
            vals = [v for v in vals if v is not None]
            # No rows with a value is NOT a zero -- it is a day Amazon did not
            # report this figure for, and it must not enter the baseline.
            out[d] = sum(vals) if vals else None
        elif agg == "ratio":
            num = sum(v for v in (col(r, ind["num"]) for r in day_rows) if v is not None)
            den = sum(v for v in (col(r, ind["den"]) for r in day_rows) if v is not None)
            out[d] = (num / den * ind.get("scale", 1.0)) if den else None
        elif agg == "weighted":
            wsum = tot = 0.0
            for r in day_rows:
                v = col(r, ind["col"])
                w = col(r, ind.get("weight") or "")
                if v is None:
                    continue
                # An unweighted day still counts -- weight 1 -- rather than
                # being dropped, or a listing with no session data would silently
                # remove the whole day.
                w = 1.0 if w is None else w
                wsum += v * w
                tot += w
            out[d] = (wsum / tot) if tot else None
        else:
            out[d] = None
    return {d: v for d, v in out.items() if v is not None}


def assess(values_by_day, day, good, sigma_alert=SIGMA_ALERT, min_days=MIN_DAYS):
    """Judge one day against the days before it.

    Returns the full picture rather than a verdict alone, so a screen can show
    its working -- the mean and deviation are what make a sigma believable, and
    a bare "3.1 sigma" with nothing behind it is a number to be argued with.
    """
    out = {"value": None, "mean": None, "stdev": None, "sigma": None,
           "change": None, "change_pct": None, "days": 0,
           "status": UNKNOWN, "note": ""}
    v = _f(values_by_day.get(day))
    out["value"] = v
    # THE BASELINE EXCLUDES THE DAY BEING JUDGED. Including it drags the mean
    # towards that value and shrinks every genuine spike, worst when the spike
    # is biggest.
    hist = [_f(values_by_day[d]) for d in sorted(values_by_day) if d < day]
    hist = [x for x in hist if x is not None]
    out["days"] = len(hist)
    if v is None:
        out["note"] = "Amazon has not reported this day yet."
        return out
    if len(hist) < min_days:
        out["note"] = ("Not enough history yet -- %d day%s of the %d needed."
                       % (len(hist), "" if len(hist) == 1 else "s", min_days))
        return out
    m = _mean(hist)
    sd = _stdev(hist, m)
    out["mean"] = m
    out["stdev"] = sd
    out["change"] = v - m
    out["change_pct"] = ((v - m) / abs(m) * 100.0) if m else None
    if sd is None or sd <= 0:
        # A figure that has never moved has no scale to measure movement against.
        # Reported as a plain change rather than an infinite sigma, because
        # "0 to 1 is infinite sigma" is true and useless.
        out["note"] = ("This figure has not varied at all over %d days, so "
                       "there is no normal range to compare against." % len(hist))
        out["status"] = OFF if (v != m) else ON_TRACK
        return out
    z = (v - m) / sd
    # Signed so POSITIVE ALWAYS MEANS BETTER here -- the opposite convention to
    # domain/trackers.drift, and deliberately so: this screen is read as "how is
    # it going", where up should look good. The sign is applied once, here, so
    # no caller has to remember which way round each indicator runs.
    out["sigma"] = z if good == HIGHER_IS_BETTER else -z
    a = abs(out["sigma"])
    if a >= sigma_alert:
        out["status"] = ON_TRACK if out["sigma"] > 0 else OFF
    elif a >= sigma_alert / 2.0:
        out["status"] = ON_TRACK if out["sigma"] > 0 else WATCH
    else:
        out["status"] = ON_TRACK
    return out


def yesterday(today=None, marketplace=""):
    """The day this screen is about.

    Yesterday, not today: Amazon's sales and traffic report for the current day
    is partial all day, and judging a part-day against whole days would make
    every morning look like a collapse.

    ON THE MARKETPLACE'S OWN CLOCK when one is named (bug round 30 Sep 2026).
    The server's date was used, so between midnight UK and midnight Pacific a
    US store was judged on a "yesterday" whose US day was still running --
    the part-day this function exists to avoid. The zone comes from the one
    table the app keeps (domain/orders_live, as routes/daily_routes does).
    """
    if today is None and marketplace:
        try:
            from domain import orders_live as _ol
            return _ol.day_start(marketplace, days_ago=1).date().isoformat()
        except Exception:
            pass
    t = today or datetime.date.today()
    if isinstance(t, str):
        t = datetime.date.fromisoformat(t)
    return (t - datetime.timedelta(days=1)).isoformat()


def rows_for(config_path, workspace_id, marketplace, start, end):
    """The daily rows this module judges, read once and read the same way.

    EVERY DAY IS STORED TWICE: an asin='*' account rollup row AND one row per
    real ASIN. Summing the table without choosing between them gives exactly
    double on any day that has both -- which is how 11.60 once appeared as
    23.20 in the finance figures (domain/order_profit.py records that one).
    Measured: jack_uk has 188 rollup rows and 154 per-ASIN rows, overlapping
    from 2026-07-14 onward.

    So it takes the rollup and nothing else. That also makes the rate
    indicators right for free: the rollup's sessions and units are the
    ACCOUNT'S own, so conversion is units-per-session for the account rather
    than a figure reassembled from whichever ASINs happened to be reported.

    An account whose sync only ever wrote per-ASIN rows has no rollup to read,
    and falling back to summing those is correct there precisely BECAUSE there
    is no rollup to double it.

    Lifted out of routes/leading_routes.py so the weekly brief reads the same
    rows by the same rule (CLAUDE.md rule 12). Two copies of this query would be
    two opinions about what a day's figures are.
    """
    from data import db as _db

    sql = ("SELECT date, asin, sessions, page_views, units, orders, "
           "       ordered_sales, buy_box_pct, orders_source "
           "FROM sales_daily "
           "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
           "  AND asin%s'*' ")
    conn = _db.get_db(config_path)
    args = (workspace_id, marketplace, start, end)
    try:
        rows = conn.execute(sql % "=", args).fetchall()
        rollup = True
        if not rows:
            rows = conn.execute(sql % "<>", args).fetchall()
            rollup = False
    except Exception as e:
        # A database created before the orders_source column existed.
        if "orders_source" not in str(e):
            raise
        sql = sql.replace(", orders_source ", " ")
        rows = conn.execute(sql % "=", args).fetchall()
        rollup = True
        if not rows:
            rows = conn.execute(sql % "<>", args).fetchall()
            rollup = False
    out = [dict(r) for r in rows]
    if not rollup:
        out = fill_quiet_days(out)
    return out


def fill_quiet_days(rows):
    """Per-ASIN rows -> the same rows plus a ZERO row for each quiet day.

    A DAY WITH NO SALES IS STILL A DAY (bug round 30 Sep 2026). With no '*'
    rollup, a day on which nothing sold and nobody looked has no per-ASIN row
    at all -- and `series` then skipped it as "not reported", so the baseline
    was built from the busy days only and every ordinary day looked like a
    collapse. Inside the span the report was synced for (its first to last
    stored day), a missing day is a real zero; outside it, still unknown.
    Rates are left alone: a zero-session day has no conversion, and
    buy_box_pct stays None so it does not enter the weighted share.
    """
    dates = sorted({str(r.get("date") or "") for r in rows if r.get("date")})
    if len(dates) < 2:
        return rows
    have = set(dates)
    out = list(rows)
    d = datetime.date.fromisoformat(dates[0])
    last = datetime.date.fromisoformat(dates[-1])
    while d <= last:
        ds = d.isoformat()
        if ds not in have:
            out.append({"date": ds, "asin": "", "sessions": 0, "page_views": 0,
                        "units": 0, "orders": 0, "ordered_sales": 0.0,
                        "buy_box_pct": None, "orders_source": None,
                        "quiet_day": True})
        d += datetime.timedelta(days=1)
    return out


def build(rows, day=None, window_days=WINDOW_DAYS, sigma_alert=SIGMA_ALERT,
          min_days=MIN_DAYS):
    """The whole screen: every indicator judged for one day.

    `rows` are the raw sales_daily rows for the window. Passed in rather than
    queried here so this module stays pure arithmetic and can be tested without
    a database -- which is what makes the sigma maths above worth trusting.
    """
    day = day or yesterday()
    out = {"day": day, "window_days": window_days, "min_days": min_days,
           "sigma_alert": sigma_alert, "indicators": [],
           "off": 0, "watch": 0, "on_track": 0, "unknown": 0}
    for ind in INDICATORS:
        vals = series(rows, ind)
        a = assess(vals, day, ind["good"], sigma_alert, min_days)
        a.update({"key": ind["key"], "label": ind["label"], "kind": ind["kind"],
                  "good": ind["good"], "blurb": ind["blurb"]})
        # A short trail for a sparkline: the last fortnight, oldest first.
        trail = [{"d": d, "v": vals[d]} for d in sorted(vals) if d <= day][-14:]
        a["trail"] = trail
        out["indicators"].append(a)
        out[a["status"]] = out.get(a["status"], 0) + 1
    return out
