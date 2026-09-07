"""domain/ppc_analytics.py -- the figures behind the three advertising screens.

PPC Analytics, Search Terms and Campaign Analytics are three views of the same
numbers, so they read the same module. One definition of ACOS, one of profit,
one of "wasted spend" -- three screens quoting three different ACOSes for the
same window is the failure this exists to prevent (CLAUDE.md Rule 12).

WHAT IS REAL, AND WHAT THIS REFUSES TO INVENT
The build specs say: "If any data source isn't available yet, stub it with
placeholder data." This does not do that, because it has been asked for twice:

    "and i still see the organic vs ppc sales graph as a placeholder, you said
     it shows actual data of ppc now"
    "now i have the ppc data campaign performance from amazon but the graph is
     still as a placeholder"

A stub is indistinguishable from a measurement once it is drawn on a chart, and
the person reading it is the person paying for the ads. So every figure here
either comes from a stored row or comes back None with a REASON attached, and
`availability()` lists what cannot be drawn and why. An empty panel that says
why is worth more than a full one that is fiction.

MEASURED, on nestwell_goods/UK 2026-08-08..09-04, before any of this was built:

    ads_campaign_daily   254 campaigns, 28 days, status and budget on every row
    ppc_search_terms     774 rows in the current report, with match type,
                         campaign, ad group and keyword
    ads_daily  asin='*'  the day's account total
    ads_daily  per ASIN  37 products
    sales_daily          sessions, page views and buy box, for TACOS and the
                         ASIN table
    HOURLY               nothing, anywhere

That last one decides two panels. The Day Trail's cumulative-by-hour cards and
the ACoS heatmap's day x hour grid both need a clock, and Amazon has not been
asked for one on this account. They report unavailable rather than drawing a
smooth curve through invented hours.

SPONSORED PRODUCTS ONLY, TODAY. Every stored row is SPONSORED_PRODUCTS. The
SP/SB/SD split is computed from `ad_product` so it is right the day Brands or
Display data arrives, and until then it says one product rather than drawing an
empty second slice as if it were a measured zero.

NOTHING HERE WRITES. No bid, no budget, no campaign state (CLAUDE.md Rule 8).
"""
import datetime as _dt

from data import db as _db

# The one place the two-grain convention is named for this module. ads_daily and
# sales_daily both hold the day's account total at asin='*' beside the same
# money broken out per product; adding them returns exactly double.
ACCOUNT_TOTAL = "*"

# Cohorts, by what the campaign did rather than by a rule of thumb. The
# boundary is the account's own break-even ACOS, not a fixed 30%: a product on a
# 60% margin and one on a 15% margin do not become unprofitable at the same
# ACOS, and a fixed line calls one of them wrong.
PROFITABLE, MARGINAL, UNPROFITABLE, NO_SALES, NO_ACTIVITY = (
    "profitable", "marginal", "unprofitable", "no_sales", "no_activity")

COHORT_LABEL = {
    PROFITABLE: "Profitable",
    MARGINAL: "Marginal",
    UNPROFITABLE: "Unprofitable",
    # SPENT AND SOLD NOTHING. The most actionable state on the screen, and
    # knowable without any rate at all.
    NO_SALES: "No sales",
    # SPENT NOTHING AND SOLD NOTHING -- a campaign that did not run in this
    # window. Kept apart from "no sales", which is money gone for nothing:
    # putting the two together would put 84 campaigns' wasted spend in the same
    # bucket as 148 that cost nothing, and make the wasted figure meaningless.
    NO_ACTIVITY: "No activity",
}


def _f(v, d=None):
    if v is None:
        return d
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _rate(top, bottom, pct=True, nd=1):
    """top/bottom, or None. NEVER zero for an undefined ratio.

    An ACOS with no sales is undefined, not 0%, and a printed 0% reads as
    "this advertising costs nothing" -- the exact opposite of a campaign that
    spent money and sold none.
    """
    t, b = _f(top), _f(bottom)
    if t is None or not b:
        return None
    return round((100.0 * t / b) if pct else (t / b), nd)


def window(days=30, end=None):
    """The default window, and the period before it of the same length."""
    e = _dt.date.fromisoformat(end) if end else _dt.date.today()
    s = e - _dt.timedelta(days=int(days) - 1)
    span = (e - s).days + 1
    pe = s - _dt.timedelta(days=1)
    ps = pe - _dt.timedelta(days=span - 1)
    return (s.isoformat(), e.isoformat(), ps.isoformat(), pe.isoformat())


# ---------------------------------------------------------------------------
# Which days are finished being counted
# ---------------------------------------------------------------------------

# THE LAST TWO DAYS ARE NOT WRONG, THEY ARE UNFINISHED.
#
#     "Trailing 2-day exclusion: The last 2 complete days are
#      attribution-immature. Exclude them from any optimization/analysis
#      calculations. Display them on charts but mark as immature."
#
# A click today can be credited with a sale up to seven days later (fourteen on
# Sponsored Brands), and the day of the CLICK owns that sale. So a recent day
# has all of its spend and only some of its sales, and every ratio built on it
# is wrong in one direction:
#
#     ACOS       too HIGH   spend is complete, sales are not
#     ROAS       too LOW
#     CVR        too LOW    clicks booked, orders not yet attributed
#     profit     too LOW
#     wasted     too HIGH   a term that has converted looks like one that never will
#
# Always the same direction: recent advertising looks worse than it was. Judged
# on it, the obvious action is to cut bids on campaigns that were fine.
#
# TWO NUMBERS, AND THEY ARE NOT THE SAME THING:
#
#     IMMATURE_DAYS   how long attribution keeps moving. A judgement about
#                     Amazon's attribution windows.
#     the ads feed's own lag, which is a separate fact measured per account by
#     latest_ad_day() -- how far behind Amazon's REPORTING is.
#
# Both are handled: mature_end() steps back from the last day that has DATA,
# not from today, so an account whose feed is already three days behind is not
# penalised twice.
IMMATURE_DAYS = 2


def mature_end(config_path, workspace_id, marketplace, end=None):
    """The last day whose attribution can be trusted, or "" when none can.

    Measured from the newest day that actually has advertising data rather than
    from the calendar: an account whose feed is four days behind has no
    immature days in view at all, and clipping two more off it would throw away
    days that finished counting long ago.

    Returns "" when every day in the window is still maturing -- which is a real
    answer, not an error, and callers say so rather than showing a figure built
    on nothing.
    """
    latest = latest_ad_day(config_path, workspace_id, marketplace)
    if not latest:
        return ""
    cap = _dt.date.fromisoformat(latest) - _dt.timedelta(days=IMMATURE_DAYS)
    if end:
        try:
            asked = _dt.date.fromisoformat(str(end)[:10])
            if asked < cap:
                cap = asked
        except ValueError:
            pass
    return cap.isoformat()


def immature_days(config_path, workspace_id, marketplace, start, end):
    """Which days in a window are still being attributed. For MARKING, not hiding.

    The spec is explicit that these are shown: "Display them on charts but mark
    as immature." A chart that silently stops two days early looks like an
    account that stopped advertising, which is a worse lie than the one being
    fixed.
    """
    cut = mature_end(config_path, workspace_id, marketplace)
    if not cut:
        return []
    try:
        s = _dt.date.fromisoformat(str(start)[:10])
        e = _dt.date.fromisoformat(str(end)[:10])
        c = _dt.date.fromisoformat(cut)
    except ValueError:
        return []
    out, d = [], max(s, c + _dt.timedelta(days=1))
    while d <= e:
        out.append(d.isoformat())
        d += _dt.timedelta(days=1)
    return out


def maturity(config_path, workspace_id, marketplace, start, end):
    """Everything a screen needs to say which days are still moving.

    One dict so the browser asks once and every panel agrees, rather than each
    working out its own idea of "recent" (Rule 12).
    """
    days = immature_days(config_path, workspace_id, marketplace, start, end)
    cut = mature_end(config_path, workspace_id, marketplace)
    return {
        "immature_days": days,
        "mature_end": cut,
        "immature_count": len(days),
        "window_days": IMMATURE_DAYS,
        "why": (
            "Amazon credits a sale to the day of the CLICK, and a click can be "
            "credited up to 7 days later (14 on Sponsored Brands). The last %d "
            "day%s therefore have all their spend and only some of their sales, "
            "so their ACOS reads high and their profit low. They are drawn, and "
            "marked, but left out of the figures used to judge performance."
            % (IMMATURE_DAYS, "" if IMMATURE_DAYS == 1 else "s")),
    }


# ---------------------------------------------------------------------------
# What can and cannot be drawn
# ---------------------------------------------------------------------------


def availability(config_path, workspace_id, marketplace):
    """What each panel can be filled from, and why not when it cannot.

    Returned to the browser and rendered in place of the panel. A screen that
    silently omits a section teaches nobody anything; one that says "no hourly
    data, so this cannot be drawn" tells you what to go and get.
    """
    conn = _db.get_db(config_path)

    def n(sql, args):
        try:
            return conn.execute(sql, args).fetchone()[0] or 0
        except Exception:
            return 0

    camp = n("SELECT COUNT(*) FROM ads_campaign_daily WHERE workspace_id=? "
             "AND marketplace=?", (workspace_id, marketplace))
    tot = n("SELECT COUNT(*) FROM ads_daily WHERE workspace_id=? AND "
            "marketplace=? AND asin=?", (workspace_id, marketplace, ACCOUNT_TOTAL))
    per = n("SELECT COUNT(*) FROM ads_daily WHERE workspace_id=? AND "
            "marketplace=? AND asin<>?", (workspace_id, marketplace, ACCOUNT_TOTAL))
    # THE NEWEST REPORT'S TERMS, NOT EVERY REPORT'S. This was a plain COUNT(*),
    # which added every report the table holds -- and the API sync writes a new
    # report id every time the window moves, so the count grew by a near-copy a
    # day. Measured: it reported 1,595 stored terms where 821 were real.
    # ppc_view.stored_totals is the one place that answers this (Rule 12).
    from domain import ppc_view as _pv
    terms = (_pv.stored_totals(config_path, workspace_id, marketplace)
             or {}).get("terms") or 0
    sales = n("SELECT COUNT(*) FROM sales_daily WHERE workspace_id=? AND "
              "marketplace=? AND asin=?", (workspace_id, marketplace, ACCOUNT_TOTAL))
    products = set()
    try:
        for r in conn.execute("SELECT DISTINCT ad_product FROM ads_campaign_daily "
                              "WHERE workspace_id=? AND marketplace=?",
                              (workspace_id, marketplace)):
            if r[0]:
                products.add(str(r[0]))
    except Exception:
        pass

    NO_ADS = ("No advertising data is stored for this account and marketplace "
              "yet. It arrives from the Advertising API sync — check Settings › "
              "Advertising, then the Jobs screen.")
    # WHETHER HOURS EXIST IS domain/ams.py's QUESTION, NOT THIS FILE'S.
    #
    # This used to answer a flat False with its own sentence. Two panels and a
    # banner each need the same answer, and the day an AWS queue does appear
    # exactly one thing should change -- so the test lives in one module (Rule
    # 12), and it tests for STORED ROWS rather than for an environment variable.
    # See ams.available(): a queue URL can be set hours before the first message
    # lands, and a screen that switched on the variable would abandon a correct
    # daily chart for an empty hourly one.
    from domain import ams as _ams
    _hourly = _ams.status(config_path)

    return {
        "campaigns": {"ok": bool(camp), "rows": camp, "why": "" if camp else NO_ADS},
        "account_totals": {"ok": bool(tot), "rows": tot,
                           "why": "" if tot else NO_ADS},
        "per_asin": {"ok": bool(per), "rows": per, "why": "" if per else NO_ADS},
        "search_terms": {
            "ok": bool(terms), "rows": terms,
            "why": "" if terms else
                   ("No Search Term Report is stored for this account. It is "
                    "pulled automatically once the Advertising API is "
                    "connected, or can be uploaded by hand on the PPC screen.")},
        "total_sales": {
            "ok": bool(sales), "rows": sales,
            "why": "" if sales else
                   ("No daily sales are stored, so TACOS and anything comparing "
                    "advertising against total sales cannot be worked out.")},
        # HOURLY, ANSWERED BY THE ONE MODULE THAT KNOWS. `ok` follows stored
        # rows, never the environment -- so the panels that fall back to daily
        # figures keep doing so until hours actually arrive. `configured` and
        # `missing_env` are carried through for the diagnostic, so someone who
        # has set the AWS variables can see that they landed without the screen
        # pretending the data did.
        "hourly": {"ok": _hourly["available"], "rows": 0,
                   "why": "" if _hourly["available"] else _hourly["why"],
                   "configured": _hourly["configured"],
                   "missing_env": _hourly["missing_env"]},
        "ad_products": {
            "ok": bool(products), "products": sorted(products),
            "why": "" if len(products) > 1 else
                   ("Only Sponsored Products data is stored, so a split by ad "
                    "type has one slice. Sponsored Brands and Sponsored Display "
                    "are separate report types; if this account runs them, the "
                    "spend here is lower than the real total and every ACOS on "
                    "these screens is flattering.")},
    }


# ---------------------------------------------------------------------------
# The account's own rates, measured
# ---------------------------------------------------------------------------


def rates(config_path, workspace_id, marketplace, start, end):
    """This account's fee and cost rates, measured from its own settled history.

    Both are needed to say whether a campaign made money, and neither is a rule
    of thumb: the fee rate is asked of domain/order_profit, which owns that
    measurement (Rule 12), and the cost rate comes from the orders that actually
    have a cost recorded.

    Returns None for either when it cannot be measured, and says so. A
    break-even ACOS computed from a guessed margin is a number that decides
    which campaigns get switched off.
    """
    out = {"fee_rate": None, "fee_rate_basis": "", "fee_rate_detail": "",
           "cogs_rate": None, "cogs_basis": "", "breakeven_acos_pct": None,
           "why": ""}
    try:
        from domain import order_profit as _op
        # END_DATE IS REQUIRED, and it is the window's end rather than today:
        # the rate is measured over the settled past BEFORE that date, so
        # reporting on August with September's rate would price August's
        # campaigns with fees Amazon had not charged yet.
        rate, basis, detail = _op.fee_rate(config_path, workspace_id, marketplace,
                                           end)
        out["fee_rate"] = rate
        out["fee_rate_basis"] = basis
        out["fee_rate_detail"] = detail
    except Exception as e:
        out["why"] = "Could not measure this account's fee rate (%s)." % str(e)[:120]

    conn = _db.get_db(config_path)
    try:
        r = conn.execute(
            "SELECT SUM(cogs) c, SUM(revenue) rev, COUNT(*) n, "
            "       SUM(CASE WHEN cogs IS NULL THEN 1 ELSE 0 END) uncosted "
            "FROM order_lines WHERE workspace_id=? AND marketplace=? "
            "AND purchase_date>=? AND purchase_date<=?",
            (workspace_id, marketplace, start, end + "T23:59:59")).fetchone()
    except Exception:
        r = None
    if r and _f(r["rev"]) and _f(r["c"]) is not None:
        out["cogs_rate"] = round(_f(r["c"]) / _f(r["rev"]), 4)
        # HOW MUCH OF IT IS ACTUALLY COSTED. A cost rate measured over a third
        # of the orders is not this account's cost rate, and the screen says so
        # rather than presenting it as settled.
        n, unc = int(r["n"] or 0), int(r["uncosted"] or 0)
        out["cogs_basis"] = ("measured on %d of %d order lines in this window"
                             % (n - unc, n))
        if n and unc and (n - unc) < n * 0.6:
            out["why"] = ((out["why"] + " ") if out["why"] else "") + (
                "Only %d of %d order lines in this window have a cost recorded, "
                "so the cost rate — and the break-even ACOS built on it — is "
                "based on a minority of the orders." % (n - unc, n))
    else:
        out["cogs_basis"] = "no costed orders in this window"

    fee, cogs = out["fee_rate"], out["cogs_rate"]
    if fee is not None and cogs is not None:
        # What is left of a pound of revenue after Amazon's fee and the stock,
        # which is the most a campaign can spend before it stops making money.
        margin = 1.0 - float(fee) - float(cogs)
        out["breakeven_acos_pct"] = (round(100.0 * margin, 1)
                                     if margin > 0 else 0.0)
    return out


# ---------------------------------------------------------------------------
# Daily series
# ---------------------------------------------------------------------------


def daily(config_path, workspace_id, marketplace, start, end):
    """One row per day: ad spend, ad sales, all sales, and what that implies.

    The account total comes from the asin='*' row, never from summing the
    per-product rows beside it -- see ads_sync.totals for what that cost.
    """
    conn = _db.get_db(config_path)
    ads = {}
    for r in conn.execute(
            "SELECT date, spend, ad_sales, clicks, impressions, ad_orders "
            "FROM ads_daily WHERE workspace_id=? AND marketplace=? "
            "AND date>=? AND date<=? AND asin=? ORDER BY date",
            (workspace_id, marketplace, start, end, ACCOUNT_TOTAL)):
        ads[r["date"]] = dict(r)

    tot = {}
    for r in conn.execute(
            "SELECT date, ordered_sales FROM sales_daily WHERE workspace_id=? "
            "AND marketplace=? AND date>=? AND date<=? AND asin=? ORDER BY date",
            (workspace_id, marketplace, start, end, ACCOUNT_TOTAL)):
        tot[r["date"]] = _f(r["ordered_sales"])

    out = []
    d0 = _dt.date.fromisoformat(start)
    d1 = _dt.date.fromisoformat(end)
    d = d0
    while d <= d1:
        k = d.isoformat()
        a = ads.get(k) or {}
        spend, asales = _f(a.get("spend")), _f(a.get("ad_sales"))
        total = tot.get(k)
        out.append({
            "date": k,
            # A DAY WITH NO ROW IS NOT A DAY WITH NO SPEND. None draws a gap;
            # 0.0 draws a line to the floor and reads as "we stopped advertising".
            "spend": spend, "ad_sales": asales,
            "clicks": _f(a.get("clicks")), "impressions": _f(a.get("impressions")),
            "orders": _f(a.get("ad_orders")),
            "total_sales": total,
            "acos_pct": _rate(spend, asales),
            "roas": _rate(asales, spend, pct=False, nd=2),
            "tacos_pct": _rate(spend, total),
            "cpc": _rate(spend, _f(a.get("clicks")), pct=False, nd=2),
            "ctr_pct": _rate(_f(a.get("clicks")), _f(a.get("impressions")), nd=2),
        })
        d += _dt.timedelta(days=1)
    return out


def daily_by_ad_product(config_path, workspace_id, marketplace, start, end):
    """Spend per day, split by ad product. -> {dates, series}.

    The campaign screen's stacked chart. Read from ads_campaign_daily rather
    than ads_daily because that is the only table carrying `ad_product` at a
    grain the split needs -- and because the campaign grain is what the rest of
    that screen is about, so the two cannot disagree.

    A product with no rows contributes NO SERIES, rather than a flat line along
    the floor. An empty band labelled "Sponsored Brands" is a claim that Brands
    ran and returned nothing, which is a different thing from not being pulled.
    """
    conn = _db.get_db(config_path)
    dates, acc = [], {}
    d0 = _dt.date.fromisoformat(start)
    d1 = _dt.date.fromisoformat(end)
    d = d0
    while d <= d1:
        dates.append(d.isoformat())
        d += _dt.timedelta(days=1)
    idx = {v: i for i, v in enumerate(dates)}

    for r in conn.execute(
            "SELECT date, COALESCE(ad_product,'?') p, SUM(spend) s "
            "FROM ads_campaign_daily WHERE workspace_id=? AND marketplace=? "
            "AND date>=? AND date<=? GROUP BY date, p",
            (workspace_id, marketplace, start, end)):
        p = str(r["p"])
        if p not in acc:
            acc[p] = [None] * len(dates)
        i = idx.get(r["date"])
        if i is not None:
            acc[p][i] = _f(r["s"])
    return {"dates": dates,
            "series": [{"key": k, "values": v} for k, v in sorted(acc.items())]}


def totals_for(config_path, workspace_id, marketplace, start, end):
    """The window's headline figures. Asks ads_sync, which owns the grain."""
    from domain import ads_sync as _as
    t = _as.totals(config_path, workspace_id, marketplace, start, end)

    conn = _db.get_db(config_path)
    r = conn.execute(
        "SELECT SUM(ordered_sales) s FROM sales_daily WHERE workspace_id=? "
        "AND marketplace=? AND date>=? AND date<=? AND asin=?",
        (workspace_id, marketplace, start, end, ACCOUNT_TOTAL)).fetchone()
    total_sales = _f(r["s"]) if r else None

    # TACOS MUST DIVIDE TWO FIGURES THAT COVER THE SAME DAYS.
    #
    # It did not. total_sales summed every day in the window; spend covered only
    # the days Amazon has actually sent advertising for -- and the advertising
    # feed runs about two days behind the sales feed, always. So the divisor
    # included days the dividend could not, and TACOS came out LOW on every
    # screen that shows it, every day, by however much sold in those two days.
    #
    # The window's own total sales is still reported as total_sales, because
    # that IS what the window sold. The ratio uses the overlap, and says so.
    ad_days = set()
    try:
        for (d,) in conn.execute(
                "SELECT DISTINCT date FROM ads_daily WHERE workspace_id=? "
                "AND marketplace=? AND date>=? AND date<=? AND asin=?",
                (workspace_id, marketplace, start, end, ACCOUNT_TOTAL)):
            ad_days.add(d)
    except Exception:
        ad_days = set()
    comparable = None
    if ad_days:
        marks = ",".join("?" * len(ad_days))
        try:
            rr = conn.execute(
                "SELECT SUM(ordered_sales) s FROM sales_daily WHERE "
                "workspace_id=? AND marketplace=? AND asin=? AND date IN (%s)"
                % marks,
                [workspace_id, marketplace, ACCOUNT_TOTAL] + sorted(ad_days)
            ).fetchone()
            comparable = _f(rr["s"]) if rr else None
        except Exception:
            comparable = None

    spend, sales, clicks = t["spend"], t["sales"], t["clicks"]
    out = dict(t)
    out.update({
        "total_sales": (round(total_sales, 2) if total_sales is not None else None),
        # The sales of the days advertising actually covers -- the divisor.
        "comparable_sales": (round(comparable, 2) if comparable is not None
                             else None),
        "ad_days": len(ad_days),
        "tacos_pct": _rate(spend, comparable if comparable is not None
                           else total_sales),
        "tacos_note": (
            ("TACOS divides ad spend by the sales of the %d day(s) that have "
             "advertising figures, not by the whole window: Amazon's advertising "
             "feed runs about two days behind its sales feed, and dividing by "
             "days the spend cannot cover reports a TACOS that is too low."
             % len(ad_days))
            if (comparable is not None and total_sales is not None
                and abs(comparable - total_sales) > 0.005) else ""),
        "cpc": _rate(spend, clicks, pct=False, nd=2),
        "ctr_pct": _rate(clicks, t["impressions"], nd=2),
        "cvr_pct": _rate(t["orders"], clicks, nd=2),
        "cpa": _rate(spend, t["orders"], pct=False, nd=2),
    })
    return out


def latest_ad_day(config_path, workspace_id, marketplace):
    """The newest day Amazon has actually sent advertising figures for.

    NOT today. Amazon's advertising reports lag: measured on nestwell_goods on
    6 Sep 2026, the newest stored day was 4 Sep. Asking for "today" therefore
    asks for a day that does not exist yet.
    """
    conn = _db.get_db(config_path)
    r = conn.execute(
        "SELECT MAX(date) d FROM ads_daily WHERE workspace_id=? AND "
        "marketplace=? AND asin=?",
        (workspace_id, marketplace, ACCOUNT_TOTAL)).fetchone()
    return (r["d"] if r and r["d"] else "") or ""


def today_bar(config_path, workspace_id, marketplace):
    """The most recent day Amazon has reported, against the day before it.

    THE MOCKUP CALLS THIS "TODAY" AND IT CANNOT BE TODAY.
    Amazon's advertising figures lag by a day or two and today's are partial
    until the day ends. Asking for today therefore produced a row of six dashes
    on an account with plenty of data -- measured: the newest stored day was
    4 Sep while the calendar said the 6th.

    A strip of dashes is accurate and useless. Worse, it reads as "the
    advertising did nothing today", which is a different and false claim.

    So the strip reports the LATEST DAY THERE IS and says which day that is,
    against the day before it. `is_today` lets the screen label it honestly --
    "Today" when it really is, the date when it is not. Nothing is invented: an
    account with no advertising at all still comes back empty, with `date` blank.
    """
    latest = latest_ad_day(config_path, workspace_id, marketplace)
    if not latest:
        blank = totals_for(config_path, workspace_id, marketplace,
                           "1970-01-01", "1970-01-01")
        return {"date": "", "compare_date": "", "is_today": False,
                "lag_days": None, "now": blank, "previous": blank, "change": {}}

    d = _dt.date.fromisoformat(latest)
    prev_day = (d - _dt.timedelta(days=1)).isoformat()
    now = totals_for(config_path, workspace_id, marketplace, latest, latest)
    prev = totals_for(config_path, workspace_id, marketplace, prev_day, prev_day)
    today = _dt.date.today()
    return {"date": latest, "compare_date": prev_day,
            "is_today": (d == today),
            # HOW FAR BEHIND AMAZON IS, so the screen can say so rather than
            # letting somebody read two-day-old figures as this morning's.
            "lag_days": (today - d).days,
            "now": now, "previous": prev, "change": change(now, prev)}


def trail(config_path, workspace_id, marketplace, days=7):
    """One card per day: that day's own total, and the units it sold.

    The mockup draws each card as spend accumulating BY HOUR. There are no
    hourly advertising figures -- Amazon refuses timeUnit HOURLY on this report
    type, measured, its own words: "configuration timeUnit is not supported for
    this report type". They would come from Marketing Stream, which needs an
    AWS queue that is deliberately not being built (see domain/ams.py).

    SO THE CARD DRAWS `spend`, THE DAY'S OWN TOTAL, AS ONE BAR. It drew
    `cumulative` -- the window adding up -- which is still returned because the
    hover reports it, but is no longer the shape: a running total can only
    climb, so the last card always towered over the first and a quiet Saturday
    looked like the account's biggest day. It also implied hours, which is the
    one thing these panels must not do.

    None is preserved and never turned into 0.0: a day with no stored row is not
    a day that spent nothing, and the bar leaves an empty track for it rather
    than a nought sitting on the floor.
    """
    end = _dt.date.today()
    start = end - _dt.timedelta(days=int(days) - 1)
    rows = daily(config_path, workspace_id, marketplace,
                 start.isoformat(), end.isoformat())
    run, out = 0.0, []
    for r in rows:
        sp = r["spend"]
        if sp is not None:
            run += float(sp)
        out.append({
            "date": r["date"],
            "spend": sp,
            "orders": r["orders"],
            "cumulative": round(run, 2),
            "today": (r["date"] == end.isoformat()),
        })
    return out


def per_click_trend(rows, fee_rate, cogs_rate):
    """Daily profit per click. The mockup's "Profit per Click Trend".

    None on a day with no clicks -- dividing by nothing is undefined, and a 0.00
    on the chart's zero line would read as a day that broke exactly even.
    Refuses entirely when the rates behind profit cannot be measured.
    """
    if fee_rate is None or cogs_rate is None:
        return None
    out = []
    for r in rows or []:
        sales, spend, clicks = r.get("ad_sales"), r.get("spend"), r.get("clicks")
        if sales is None or spend is None or not clicks:
            out.append(None)
            continue
        profit = (float(sales) - float(spend) - float(sales) * float(fee_rate)
                  - float(sales) * float(cogs_rate))
        out.append(round(profit / float(clicks), 3))
    return out


def efficiency_trend(rows, breakeven_acos_pct):
    """Daily "efficiency score". OUR OWN DEFINITION, STATED.

    Orbit shows a score and does not say what it is, and a number nobody can
    explain is a number nobody can act on. This one is simply how far the day's
    ACOS sits from this account's break-even, expressed so that 100 is
    break-even and higher is better:

        score = 100 x (break-even ACOS / the day's ACOS)

    A day that spent nothing scores nothing (None, not 0). A day that sold
    nothing has an undefined ACOS and so an undefined score -- it is a bad day,
    but it is not a measurable score, and inventing one would put it on the
    chart next to days that were measured.
    """
    if not breakeven_acos_pct:
        return None
    out = []
    for r in rows or []:
        acos = r.get("acos_pct")
        if acos is None or acos <= 0:
            out.append(None)
            continue
        out.append(round(100.0 * float(breakeven_acos_pct) / float(acos), 1))
    return out


# METRICS THAT ARE ALREADY A PERCENTAGE MOVE IN POINTS, NOT IN PER CENT.
#
# ACOS going 24.3% -> 28.4% is +4.1 POINTS. Reported as a percentage change it
# is +16.9%, which is a true statement about a different question and reads as
# far worse news than it is. The same trap catches CTR, CVR, TACOS and the
# buy-box share.
#
# Money and counts -- spend, sales, clicks, impressions, orders -- move in per
# cent, because "spend rose 4.1 points" means nothing.
_POINT_METRICS = frozenset((
    "acos_pct", "tacos_pct", "ctr_pct", "cvr_pct", "buy_box_pct",
    "margin_pct", "refund_rate", "unit_session_pct",
))


def change(now, before):
    """How each metric moved, and in the RIGHT UNIT. -> {key: number or None}.

    A ratio moves in percentage POINTS; money and counts move in per cent. Which
    is which is not cosmetic: +4.1pts and +16.9% describe the same ACOS move and
    only one of them is the one anybody means.

    `change_units` below says which was used for each, so the screen can print
    "pts" rather than leaving the reader to assume.

    NEVER A CHANGE AGAINST NOTHING. A move from no data to a number is not a
    rise, and rendering it as +100% invites somebody to celebrate a sync
    finishing.
    """
    out = {}
    for k, v in (now or {}).items():
        b = (before or {}).get(k)
        if not isinstance(v, (int, float)) or not isinstance(b, (int, float)):
            out[k] = None
            continue
        if k in _POINT_METRICS:
            # A RATIO OFF A FLOOR-LEVEL BASE IS ARITHMETIC, NOT NEWS.
            #
            #     "When prior period had near-zero spend, TACOS change can show
            #      +922% or similar. This is mathematically correct but
            #      meaningless. Consider: if prior TACOS < 2%, suppress the %
            #      change and show 'N/A -- prior period baseline too low'"
            #
            # Applied in POINTS as well as per cent, and to every ratio rather
            # than to TACOS alone, because the fault is the base and not the
            # metric: a prior ACOS of 0.4% rising to 30% is a true +29.6 points
            # and still describes an account that barely advertised last month
            # against one that did. The screen prints the reason from
            # change_floor() instead of a number nobody can act on.
            if b is not None and 0 < abs(float(b)) < _RATIO_FLOOR_PCT:
                out[k] = None
                continue
            out[k] = round(float(v) - float(b), 1)
            continue
        if not b:
            out[k] = None
            continue
        # A PERCENTAGE OFF A TINY BASE IS ARITHMETIC, NOT NEWS -- the same fault
        # as the ratio floor above, and the spec gives the numbers:
        #     Spend  < 10.00   "$5 -> $11,768 shows '--' not +235,260%"
        #     Sales  < 25.00
        #     Orders / Units < 3
        floor = _COUNT_FLOORS.get(k)
        if floor is not None and abs(float(b)) < floor:
            out[k] = None
            continue
        out[k] = round(100.0 * (float(v) - float(b)) / abs(float(b)), 1)
    return out


# Below these, the previous period is too small to compare a percentage
# against. Section 20, "Comparison Period Suppression Thresholds".
_COUNT_FLOORS = {
    "spend": 10.0,
    "sales": 25.0, "ad_sales": 25.0, "total_sales": 25.0,
    "orders": 3.0, "ad_orders": 3.0, "units": 3.0, "purchases": 3.0,
}


# Below this, a ratio's previous value is too small to compare against. The
# spec names 2% for TACOS; the same floor is used for every ratio because the
# problem is the size of the base, not which metric sits on it.
_RATIO_FLOOR_PCT = 2.0


def change_floor(now, before):
    """Which metrics had their change SUPPRESSED, and the sentence to show.

    Separate from change() so a blank arrow can explain itself. A dash with no
    reason reads as missing data, which is a different and wrong finding: the
    data is there, it is the comparison that would be meaningless.
    """
    out = {}
    for k, v in (now or {}).items():
        b = (before or {}).get(k)
        if not isinstance(v, (int, float)) or not isinstance(b, (int, float)):
            continue
        name = k.replace("_pct", "").replace("_", " ")
        if k in _POINT_METRICS:
            if 0 < abs(float(b)) < _RATIO_FLOOR_PCT:
                out[k] = ("No comparison: the previous period's %s was %.2f%%, "
                          "too low a base to measure a move against."
                          % (name, float(b)))
            continue
        floor = _COUNT_FLOORS.get(k)
        if floor is not None and 0 < abs(float(b)) < floor:
            out[k] = ("No comparison: the previous period's %s was only %s, too "
                      "small a base for a percentage to mean anything."
                      % (name, ("%.2f" % float(b)).rstrip("0").rstrip(".")))
    return out


def change_units(now=None):
    """Which unit each change is in: 'pts' or 'pct'. For the screen to print."""
    keys = list((now or {}).keys()) or list(_POINT_METRICS)
    return {k: ("pts" if k in _POINT_METRICS else "pct") for k in keys}


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


def campaigns(config_path, workspace_id, marketplace, start, end, rate_info=None,
              judge_end=None):
    """Every campaign in the window, with an ESTIMATED profit and a cohort.

    THE PROFIT IS ESTIMATED AND SAYS SO. Amazon attributes sales to a campaign;
    it does not attribute the stock cost or the referral fee, and neither can be
    known per campaign. So this applies the account's own MEASURED fee and cost
    rates to that campaign's attributed sales:

        profit = ad_sales - spend - ad_sales x fee_rate - ad_sales x cogs_rate

    When either rate cannot be measured, profit is None for every campaign
    rather than being computed from a default. A campaign switched off on the
    strength of a guessed margin is a real cost.
    """
    r = rate_info or rates(config_path, workspace_id, marketplace, start, end)
    fee, cogs = r.get("fee_rate"), r.get("cogs_rate")
    can_profit = (fee is not None and cogs is not None)
    be = r.get("breakeven_acos_pct")

    conn = _db.get_db(config_path)
    SQL = ("SELECT campaign_id, MAX(campaign_name) name, MAX(status) status, "
           "MAX(budget) budget, MAX(ad_product) ad_product, "
           "SUM(impressions) impressions, SUM(clicks) clicks, "
           "SUM(spend) spend, SUM(ad_orders) orders, SUM(ad_sales) sales "
           "FROM ads_campaign_daily WHERE workspace_id=? AND marketplace=? "
           "AND date>=? AND date<=? GROUP BY campaign_id")

    # WHAT IS SHOWN AND WHAT IS JUDGED ARE DIFFERENT WINDOWS, deliberately.
    #
    #     "Trailing 2-day exclusion: The last 2 complete days are
    #      attribution-immature. Exclude them from any optimization/analysis
    #      calculations. Display them on charts but mark as immature."
    #
    # The money columns cover the FULL window, because that is what the account
    # actually spent and a table that quietly showed less would not reconcile
    # with the KPI row above it. The COHORT and the OPPORTUNITY SCORE -- the two
    # fields that say "do something about this campaign" -- are worked out on
    # the days that have finished being attributed.
    #
    # Without this, a campaign that converted perfectly well two days ago has
    # its spend counted and its sales not, so it reads as unprofitable with a
    # high opportunity score, and the obvious action is to cut a campaign that
    # was fine. The error is one-directional, so it is not noise: recent
    # advertising ALWAYS looks worse than it was.
    # THE TABLE-WIDE FIGURES THE OPPORTUNITY SCORE NEEDS, worked out ONCE.
    #
    # "Money at stake" is 40 x sqrt(spend / max_spend), so it is a property of
    # the whole set rather than of one row. Two consequences, both deliberate:
    #
    #   the max comes from the UN-PAGINATED, UNFILTERED set. Section 18:
    #   "Absolute, not re-scaled on filter." A score that moved when somebody
    #   picked a filter would not be a property of the campaign at all, and two
    #   people looking at the same campaign would read different numbers.
    #
    #   it is taken from the JUDGED window when there is one, so the score and
    #   the cohort rest on the same days.
    judged = {}
    jend = str(judge_end or "")[:10]
    if jend and jend < str(end)[:10]:
        if jend >= str(start)[:10]:
            for row in conn.execute(SQL, (workspace_id, marketplace, start, jend)):
                judged[row["campaign_id"]] = dict(row)
        else:
            # The whole window is still maturing. Judging on nothing is worse
            # than judging on immature data, so nothing is judged and the
            # screen is told why.
            judged = None

    raw = [dict(r) for r in conn.execute(SQL, (workspace_id, marketplace,
                                               start, end))]

    # The scoring set, and the biggest spend in it. Taken from whichever window
    # the scores will be made on, so the denominator and the numerators are the
    # same days.
    if judged:
        _scoring = list(judged.values())
    elif judged is None:
        _scoring = []
    else:
        _scoring = raw
    _spends = [_f(r.get("spend")) or 0.0 for r in _scoring]
    top_spend = max(_spends) if _spends else None
    cap_cpo = max_cost_per_order(
        r, totals_for(config_path, workspace_id, marketplace, start,
                      jend if judged else end))

    out = []
    for d in raw:
        spend, sales = _f(d["spend"]), _f(d["sales"])
        profit = None
        if can_profit and spend is not None and sales is not None:
            profit = round(sales - spend - sales * float(fee) - sales * float(cogs), 2)

        # The figures the judgement is made on: the mature ones when there are
        # any, otherwise the same ones being displayed.
        if judged is None:
            j = None
        elif judged:
            j = judged.get(d["campaign_id"]) or {"spend": 0, "sales": 0,
                                                 "clicks": 0, "orders": 0}
        else:
            j = d
        if j is None:
            j_cohort, j_opp, j_profit = None, None, None
        else:
            j_spend, j_sales = _f(j["spend"]), _f(j["sales"])
            j_profit = None
            if can_profit and j_spend is not None and j_sales is not None:
                j_profit = round(j_sales - j_spend - j_sales * float(fee)
                                 - j_sales * float(cogs), 2)
            j_cohort = _cohort(j_spend, j_sales, j_profit, be, can_profit)
            j_opp = _opportunity(j_spend, j_sales, _f(j["clicks"]),
                                 _f(j["orders"]), be,
                                 max_spend=top_spend,
                                 max_cost_per_order=cap_cpo)

        d.update({
            "spend": (round(spend, 2) if spend is not None else None),
            "sales": (round(sales, 2) if sales is not None else None),
            "acos_pct": _rate(spend, sales),
            "roas": _rate(sales, spend, pct=False, nd=2),
            "ctr_pct": _rate(_f(d["clicks"]), _f(d["impressions"]), nd=2),
            "cpc": _rate(spend, _f(d["clicks"]), pct=False, nd=2),
            # CPA IS UNDEFINED WITHOUT AN ORDER, not zero: "-- when orders = 0
            # (undefined, not $0)". _rate already returns None on a nil divisor.
            "cpa": _rate(spend, _f(d["orders"]), pct=False, nd=2),
            "cvr_pct": _rate(_f(d["orders"]), _f(d["clicks"]), nd=2),
            "profit": profit,
            "profit_estimated": can_profit,
            "cohort": j_cohort,
            "opportunity": j_opp,
            # So the row can say which days its verdict rests on, and so the
            # two numbers being different is legible rather than looking wrong.
            "judged_to": (jend if judged else ""),
            "judged_profit": j_profit,
        })
        out.append(d)
    out.sort(key=lambda x: (x["spend"] is None, -(x["spend"] or 0)))
    return out


def _cohort(spend, sales, profit, breakeven_acos, can_profit):
    """Which bucket this campaign is in. UNKNOWN is a bucket, not a default.

    Sorted before profit exists, because "spent money and sold nothing" is
    knowable without any rate at all and is the most actionable state on the
    screen.
    """
    if not sales:
        # Spent and sold nothing is a finding. Spent nothing and sold nothing is
        # a campaign that did not run, and is not the same thing at all.
        return NO_SALES if spend else NO_ACTIVITY
    if not can_profit or profit is None:
        return None
    # MARGINAL IS MEASURED AGAINST SPEND, NOT AGAINST BREAK-EVEN ACOS.
    #
    # The spec says so twice, in the same words both times:
    #     section 5   "Marginal | profitable by < 10% of spend"
    #     section 18  "Profitable | profit > 0 AND profit > 10% of spend"
    #                 "Marginal   | 0 <= profit <= 10% of spend"
    #
    # This used a rule of our own -- profitable, but with ACOS within a tenth of
    # break-even. The two disagree in an important place. Break-even ACOS is an
    # ACCOUNT-WIDE rate, so a campaign selling a product with a fatter margin
    # than the account average was called Marginal for sitting near a threshold
    # that does not apply to it, while its actual profit was healthy. Profit
    # over spend asks the question directly and needs no account rate at all.
    #
    # `breakeven_acos` is still taken so no caller changes, and is no longer
    # used to sort the bucket.
    if profit <= 0:
        return UNPROFITABLE
    s = _f(spend) or 0.0
    if s and profit <= s * 0.10:
        return MARGINAL
    return PROFITABLE


# The volume of wasted clicks that counts as a full finding. The spec's number
# and the spec's reason: "Threshold of 30 = empirical sample size for 3.3% CVR
# significance" -- below it, no orders is not yet evidence of anything.
UNCONVERTED_CLICK_THRESHOLD = 30


def _opportunity(spend, sales, clicks, orders, breakeven_acos,
                 max_spend=None, max_cost_per_order=None):
    """0-100: how much is there to gain by touching this one?

    THE SPEC'S EXACT ARITHMETIC (section 20), not an approximation of it:

        Opportunity = min(100, round(S_spend + S_breakeven + S_unconverted))

        S_spend       40 x sqrt(spend / max_spend)
        S_breakeven   sales > 0:  35 x min(1, (acos - be) / be)
                      sales = 0:  35 x min(1, spend / max_cost_per_order)
        S_unconverted 25 x min(1, (clicks - orders) / 30)

    THREE PLACES THE EARLIER VERSION WAS WRONG, and the spec names the harm in
    the first one itself:

      A CAMPAIGN THAT SPENT 50p AND SOLD NOTHING SCORED THE FULL 35. Zero sales
      means an undefined ACOS, and undefined was read as "the worst case there
      is". So one test click on a new campaign outranked a campaign quietly
      losing money all month. The spec: "This prevents a single test click from
      scoring 35 points." It is now scaled by how much was spent against what an
      order is allowed to cost.

      MONEY AT STAKE WAS ABSOLUTE, not relative to the table. `sqrt(spend)/20`
      hard-codes what "a lot" means -- it saturates near 400 pounds, so on this
      account, where the biggest campaign spends 34, every campaign scored under
      12 on a component worth 40 and the whole column was compressed into its
      bottom third. Against `max_spend` the biggest spender always scores 40 and
      the rest are placed against it, which is what makes the column sortable.

      UNCONVERTED CLICKS WERE A RATE, not a volume. The old form scored by CVR
      against a 10% target, so 5 clicks and no orders scored the same 25 as
      1,000 clicks and no orders. The spec is explicit that this one is
      "Based on VOLUME of wasted clicks, not percentage": 990 unconverted clicks
      is a finding, 5 is a Tuesday.

    max_spend and max_cost_per_order are passed in because they are properties
    of the WHOLE table, not of one row. campaigns() works them out once. When
    max_spend is absent the money component cannot be placed and is scored 0
    rather than guessed -- a component that cannot be measured must not quietly
    become an average one.

    None when there is nothing to score -- no spend means no opportunity and no
    problem, and a 0 would sort alongside campaigns that are merely fine.
    """
    s = _f(spend)
    if not s or s <= 0:
        return None
    score = 0.0

    # 1. MONEY AT STAKE, against the biggest spender in the same table.
    top = _f(max_spend)
    if top and top > 0:
        score += 40.0 * min(1.0, (max(0.0, s) / top) ** 0.5)

    # 2. DISTANCE PAST BREAK-EVEN.
    sa = _f(sales)
    acos = _rate(s, sa)
    if acos is None:
        # Spent and sold nothing. Scaled by spend against what one order is
        # allowed to cost, so a 50p experiment is not the same finding as 25
        # pounds of silence. Without that ceiling the size cannot be judged, and
        # the component is left at 0 rather than defaulted to the full 35.
        cap = _f(max_cost_per_order)
        if cap and cap > 0:
            score += 35.0 * min(1.0, s / cap)
    elif breakeven_acos and float(breakeven_acos) > 0:
        rel = (acos - float(breakeven_acos)) / float(breakeven_acos)
        score += 35.0 * min(1.0, max(0.0, rel))

    # 3. UNCONVERTED CLICKS, by volume.
    c, o = _f(clicks) or 0, _f(orders) or 0
    unconverted = max(0.0, float(c) - float(o))
    if unconverted:
        score += 25.0 * min(1.0, unconverted / float(UNCONVERTED_CLICK_THRESHOLD))

    return int(round(min(100.0, score)))


def max_cost_per_order(rate_info, totals=None):
    """The most one order may cost before it stops paying. None when unknowable.

    The ceiling the zero-sales branch of the opportunity score is measured
    against -- the spec calls it max_cost_per_order and defines it as the
    break-even CPA.

        break-even CPA = what an order is worth x the share of it advertising
                         may take = average order value x break-even ACOS

    None rather than a default when either half is missing. A guessed ceiling
    would silently rank every zero-sales campaign against a number nobody chose.
    """
    be = (rate_info or {}).get("breakeven_acos_pct")
    if not be or float(be) <= 0:
        return None
    t = totals or {}
    # totals_for() names these `sales` and `orders` -- they are already
    # ad-attributed, which is the whole of what ads_daily holds. The ad_*
    # spellings are accepted too so a caller holding a differently-shaped
    # totals dict is not silently answered None.
    sales = _f(t.get("sales"))
    if sales is None:
        sales = _f(t.get("ad_sales"))
    orders = _f(t.get("orders"))
    if orders is None:
        orders = _f(t.get("ad_orders"))
    if not sales or not orders or orders <= 0:
        return None
    aov = float(sales) / float(orders)
    v = aov * (float(be) / 100.0)
    return round(v, 2) if v > 0 else None


def cohorts(config_path, workspace_id, marketplace, start, end, rows=None,
            rate_info=None):
    """The five buckets, counted and totalled."""
    rows = rows if rows is not None else campaigns(
        config_path, workspace_id, marketplace, start, end, rate_info)
    out = {"all": {"n": 0, "spend": 0.0, "sales": 0.0}}
    for k in (PROFITABLE, MARGINAL, UNPROFITABLE, NO_SALES, NO_ACTIVITY):
        out[k] = {"n": 0, "spend": 0.0, "sales": 0.0, "label": COHORT_LABEL[k]}
    unknown = {"n": 0, "spend": 0.0, "sales": 0.0,
               "label": "Not yet classified"}
    for r in rows:
        sp, sa = _f(r["spend"]) or 0.0, _f(r["sales"]) or 0.0
        out["all"]["n"] += 1
        out["all"]["spend"] += sp
        out["all"]["sales"] += sa
        b = out.get(r["cohort"]) if r["cohort"] else None
        if b is None:
            b = unknown
        b["n"] += 1
        b["spend"] += sp
        b["sales"] += sa
    for b in list(out.values()) + [unknown]:
        b["spend"] = round(b["spend"], 2)
        b["sales"] = round(b["sales"], 2)
    if unknown["n"]:
        # SHOWN, NOT DROPPED. Campaigns that could not be classified because the
        # account has no measured cost rate are a fact about the setup, and
        # hiding them makes the four buckets add up to less than the total with
        # nothing to say why.
        out["unclassified"] = unknown
    return out


# Clicks a term must have taken, with no order, before it is worth negating.
# Section 20's "Qualified" wasted-spend definition. Below this, no orders is
# not yet evidence that the term will never convert.
QUALIFIED_CLICKS = 10


def _report_window_spend(config_path, workspace_id, marketplace, start, end):
    """Account spend over the search-term report's OWN window, or None."""
    if not (start and end):
        return None
    try:
        conn = _db.get_db(config_path)
        r = conn.execute(
            "SELECT ROUND(SUM(spend),2) s FROM ads_daily WHERE workspace_id=? "
            "AND marketplace=? AND asin=? AND date>=? AND date<=?",
            (workspace_id, marketplace, ACCOUNT_TOTAL, str(start),
             str(end))).fetchone()
        return _f(r["s"]) if r else None
    except Exception:
        return None


def efficiency_score(totals, rates_info, wasted_info, cvr_baseline=None):
    """The headline 0-100 efficiency score. -> dict, or a stated refusal.

    THREE PARTS, WEIGHTED, AND EVERY ONE OF THEM PUBLISHED:

        0.50  how far ACOS sits under break-even
        0.30  how normal the conversion rate is against its own history
        0.20  how little of the spend bought clicks and no orders

    Distinct from efficiency_trend() below, which is the DAILY line and answers a
    narrower question -- break-even over that day's ACOS. Both are ours, both are
    stated; this one is the summary, that one is the shape.

    IT REFUSES RATHER THAN GUESSES. A score is a single number people act on, so
    a part that cannot be measured makes the whole thing unavailable and says
    which part was missing. Scoring on two legs out of three and not saying so
    would be worse than no score: it looks identical to a real one.
    """
    missing = []
    acos = (totals or {}).get("acos_pct")
    be = (rates_info or {}).get("breakeven_acos_pct")
    if acos is None:
        missing.append("this window has no ACOS — the ads made no attributed "
                       "sales")
    if not be:
        missing.append("this account has no break-even ACOS — its fee or cost "
                       "rate could not be measured")
    # THE WASTED SHARE MUST DIVIDE TWO FIGURES THAT COVER THE SAME DAYS.
    #
    # wasted_spend comes from the Search Term Report, whose window is fixed and
    # is usually ~30 days. totals["spend"] is the window on the date picker. On
    # a 14-day view the first divided by the second gave 144% -- "more than all
    # of the spend was wasted", which is arithmetic on two different periods and
    # not a fact about anything.
    #
    # `report_spend` is the spend over the REPORT's own window, passed in by the
    # caller. Without it this part cannot be scored honestly, and the score is
    # withheld rather than computed on mismatched periods.
    spend = (wasted_info or {}).get("report_spend")
    wasted = (wasted_info or {}).get("spend")
    if spend is None or wasted is None:
        missing.append("wasted spend cannot be compared with the spend over the "
                       "same days")
    cvr = (totals or {}).get("cvr_pct")

    if missing:
        return {"score": None, "band": "", "parts": {}, "why": (
            "The efficiency score needs all three of its parts and is not shown "
            "on two: " + "; ".join(missing) + ".")}

    # 1. ACOS against break-even. At break-even this is 0; at half of it, 50.
    acos_part = max(0.0, 1.0 - (float(acos) / float(be))) * 100.0

    # 2. Conversion rate against its own history. Without a baseline this part
    # cannot be scored, so the whole score is not shown -- see above.
    if cvr is None or not cvr_baseline or cvr_baseline.get("sd") in (None, 0):
        return {"score": None, "band": "", "parts": {}, "why": (
            "The efficiency score needs the conversion rate measured against "
            "its own history, and this account has too little of it yet. The "
            "other two parts are on the page separately.")}
    z = abs(float(cvr) - float(cvr_baseline["mean"])) / float(cvr_baseline["sd"])
    cvr_part = max(0.0, 1.0 - z / 2.0) * 100.0

    # 3. The share of spend that bought clicks and no orders.
    share = (float(wasted) / float(spend)) if spend else 0.0
    wasted_part = max(0.0, 1.0 - share) * 100.0

    score = round(0.50 * acos_part + 0.30 * cvr_part + 0.20 * wasted_part, 2)
    band = "Poor" if score < 50 else ("Average" if score <= 75 else "Good")
    return {
        "score": score, "band": band,
        "parts": {
            "acos": {"weight": 0.50, "value": round(acos_part, 2),
                     "why": "ACOS %.1f%% against a break-even of %.1f%%"
                            % (acos, be)},
            "cvr": {"weight": 0.30, "value": round(cvr_part, 2),
                    "why": "conversion rate %.2f%%, %.1f standard deviations "
                           "from its own %d-day mean"
                           % (cvr, z, cvr_baseline.get("n") or 0)},
            "wasted": {"weight": 0.20, "value": round(wasted_part, 2),
                       "why": "%.1f%% of spend bought clicks and no orders"
                              % (share * 100.0)},
        },
        "bands": {"poor": "< 50", "average": "50-75", "good": "> 75"},
        "why": "",
    }


def cvr_baseline(config_path, workspace_id, marketplace, end, days=60):
    """The conversion rate's own mean and spread, for the score above.

    Sixty complete days, ending the day BEFORE the window being scored, so the
    days being judged are not part of what they are judged against.
    """
    import datetime as _d

    try:
        e = _d.date.fromisoformat(str(end)[:10]) - _d.timedelta(days=1)
    except Exception:
        return None
    s = e - _d.timedelta(days=int(days) - 1)
    rows = daily(config_path, workspace_id, marketplace, s.isoformat(),
                 e.isoformat())
    vals = []
    for r in rows:
        c, o = _f(r.get("clicks")), _f(r.get("orders"))
        if c:
            vals.append(100.0 * (o or 0.0) / c)
    if len(vals) < 14:
        return None
    mean = sum(vals) / len(vals)
    sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
    return {"mean": round(mean, 4), "sd": round(sd, 4), "n": len(vals),
            "start": s.isoformat(), "end": e.isoformat()}


def wasted_spend(config_path, workspace_id, marketplace, start=None, end=None,
                 min_clicks=0, min_spend=0.0):
    """Spend that bought clicks and no orders. OUR DEFINITION, SAID OUT LOUD.

    Orbit shows a "wasted spend" figure and does not define it. This one is:
    the spend on search terms that took at least one click and produced no
    order. Not "ACOS above target" -- that is a judgement about price; this is
    money that bought traffic which bought nothing, which nobody disputes.

    IT DOES NOT MOVE WITH THE DATE PICKER, AND IT CANNOT.

    `start` and `end` are accepted and IGNORED, deliberately. The figure comes
    from the stored Search Term Report, and that report is one fixed window
    chosen when it was pulled -- it carries no per-day breakdown, so there is no
    way to ask it what was wasted last Tuesday.

    They used to be accepted and silently ignored, which was worse than not
    taking them at all: the caller asked for 7 days, then 14, then 90, and got
    251.56 every time; and the page compared it against a "previous period" that
    was the same query, so the change arrow could only ever read zero. Measured
    on nestwell_goods across four windows: identical to the penny in all of them.

    So the window this figure ACTUALLY covers is returned with it, for the screen
    to print, and `comparable` says plainly that there is nothing to compare it
    against.
    """
    # SCOPED TO THE NEWEST REPORT, like everything else that reads this table.
    #
    # It was not, and this is a headline card. ppc_search_terms holds one row per
    # term PER REPORT, and the API sync names each report after its window --
    # so a second sync leaves two near-identical reports and this summed both.
    # Measured on nestwell_goods/UK: two reports sharing 572 of their terms, so
    # the wasted-spend card was reporting close to twice the real figure, and
    # would have grown by another report every day the sync ran.
    from domain import ppc_view as _pv

    conn = _db.get_db(config_path)
    meta = _pv.report_meta(config_path, workspace_id, marketplace)
    if not meta:
        return {"spend": None, "terms": 0,
                "why": "No search term report is stored, so spend that bought "
                       "clicks and no orders cannot be identified."}
    try:
        r = conn.execute(
            "SELECT ROUND(SUM(spend),2) s, COUNT(*) n FROM ppc_search_terms "
            "WHERE workspace_id=? AND marketplace=? AND report_id=? "
            "AND COALESCE(clicks,0) > 0 AND COALESCE(orders,0) = 0",
            (workspace_id, marketplace, meta["report_id"])).fetchone()
        # AND THE SAME THING WORTH ACTING ON.
        #
        # Most of these terms are one or two clicks and a few pence -- true, and
        # useless as a list. The floor is a SECOND figure beside the total, never
        # instead of it: quietly reporting only the actionable part would
        # understate the waste, which is the opposite of the point.
        # THE GATE IS TEN CLICKS, and the spec gives both the number and the
        # reason: "clicks >= 10 AND orders = 0 ... The qualification gate
        # prevents generating optimization actions for 1,400+ single-click terms
        # that would clog campaign negative keyword limits with noise."
        #
        # It was three clicks OR a pound spent, which is a different and weaker
        # question -- a term with two clicks and 1.10 spent passed it, and two
        # clicks is not yet evidence that a term will never convert. Ten is a
        # sample; three is a coincidence.
        big = conn.execute(
            "SELECT ROUND(SUM(spend),2) s, COUNT(*) n FROM ppc_search_terms "
            "WHERE workspace_id=? AND marketplace=? AND report_id=? "
            "AND COALESCE(orders,0) = 0 AND COALESCE(clicks,0) >= ?",
            (workspace_id, marketplace, meta["report_id"],
             int(min_clicks or QUALIFIED_CLICKS))).fetchone()
    except Exception:
        return {"spend": None, "terms": 0,
                "why": "No search term report is stored."}
    if not r or not r["n"]:
        return {"spend": None, "terms": 0,
                "why": "No search term report is stored, so spend that bought "
                       "clicks and no orders cannot be identified."}
    return {"spend": _f(r["s"]), "terms": int(r["n"]),
            "definition": "spend on search terms that took a click and "
                          "produced no order",
            # TWO DEFINITIONS, BOTH SHOWN, and the spec is explicit that it
            # wants both: the full universe is "Financial audit / reporting"
            # and the qualified subset is "Actionable optimization". Reporting
            # only the actionable part would understate the waste; reporting
            # only the total gives a list of 1,400 single-click terms nobody
            # can act on.
            # NOTHING QUALIFYING IS A MEASURED ZERO, NOT AN UNKNOWN. SUM over no
            # rows is NULL, and passing that through would draw a dash -- which
            # on this app means "could not be worked out". Here it was worked
            # out, and the answer is that no term has taken ten clicks without
            # converting, which is a good result and should read as one.
            "actionable_spend": ((_f(big["s"]) or 0.0)
                                 if (big and (big["n"] or 0)) else
                                 (0.0 if big is not None else None)),
            "actionable_terms": int((big["n"] if big else 0) or 0),
            "actionable_rule": ("at least %d clicks and no orders"
                                % int(min_clicks or QUALIFIED_CLICKS)),
            # THE SPEND OVER THE REPORT'S OWN WINDOW, so anything expressing
            # wasted spend as a SHARE divides two figures covering the same
            # days. Dividing it by the date picker's spend gave 144% on a
            # 14-day view -- more than all of it, which is not a fact.
            "report_spend": _report_window_spend(
                config_path, workspace_id, marketplace,
                meta.get("date_from"), meta.get("date_to")),
            # THE WINDOW THIS FIGURE REALLY COVERS -- the report's own, not the
            # one on the date picker. Sent so the card can print it instead of
            # sitting under a range it does not answer for.
            "report_start": meta.get("date_from") or "",
            "report_end": meta.get("date_to") or "",
            "follows_date_picker": False,
            # And there is nothing to compare it with: the same query answers
            # for every window, so a change arrow would always read zero.
            "comparable": False,
            "comparable_why": (
                "This comes from the stored Search Term Report, which covers %s "
                "to %s and carries no day-by-day breakdown. It does not change "
                "with the dates above, and there is no earlier report to compare "
                "it against, so no change is shown rather than a nil one."
                % (meta.get("date_from") or "?", meta.get("date_to") or "?")),
            "why": ""}


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


def asins(config_path, workspace_id, marketplace, start, end, rate_info=None):
    """Per-product advertising, joined to what the listing actually did.

    The advertising half comes from ads_daily's per-product rows, the traffic
    half from sales_daily -- both of which keep the account total at asin='*',
    and neither of which is summed across grains here.
    """
    conn = _db.get_db(config_path)
    r = rate_info or rates(config_path, workspace_id, marketplace, start, end)
    fee, cogs = r.get("fee_rate"), r.get("cogs_rate")
    can_profit = (fee is not None and cogs is not None)

    ads = {}
    # Same literal, same reason -- see the sales_daily query below.
    for row in conn.execute(
            "SELECT asin, SUM(impressions) impressions, SUM(clicks) clicks, "
            "SUM(spend) spend, SUM(ad_orders) orders, SUM(ad_sales) sales "
            "FROM ads_daily WHERE workspace_id=? AND marketplace=? "
            "AND date>=? AND date<=? AND asin<>'*' GROUP BY asin",
            (workspace_id, marketplace, start, end)):
        ads[row["asin"]] = dict(row)

    biz = {}
    # THE LITERAL asin<>'*', NOT A PARAMETER. sales_daily keeps the day's
    # account total in the same table as the per-product rows, exactly as
    # ads_daily does, and a per-product GROUP BY that does not exclude it counts
    # the whole account as one extra product. Written out rather than bound so
    # it is greppable: test_weekly_total_row.py walks every query in domain/ and
    # routes/ looking for this clause, and a bound "?" could be anything.
    for row in conn.execute(
            "SELECT asin, SUM(sessions) sessions, SUM(page_views) page_views, "
            "AVG(buy_box_pct) buy_box_pct, SUM(units) units, "
            "SUM(ordered_sales) ordered_sales FROM sales_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
            "AND asin<>'*' GROUP BY asin",
            (workspace_id, marketplace, start, end)):
        biz[row["asin"]] = dict(row)

    from domain import catalogue as _cat
    try:
        # PAIRS, not bare workspace ids. merged() iterates `for wsid, mkt in
        # pairs`, so a list of strings unpacks each id into characters and
        # raises -- which was swallowed here, leaving every product without its
        # picture or its name on a screen built around showing them.
        idx = _cat.merged(config_path, [(workspace_id, marketplace)])
    except Exception:
        idx = {}

    out = []
    for asin in sorted(set(ads) | set(biz)):
        a = ads.get(asin) or {}
        b = biz.get(asin) or {}
        spend, sales = _f(a.get("spend")), _f(a.get("sales"))
        profit = None
        if can_profit and spend is not None and sales is not None:
            profit = round(sales - spend - sales * float(fee) - sales * float(cogs), 2)
        look = {}
        try:
            look = _cat.look(idx, None, asin) or {}
        except Exception:
            look = {}
        out.append({
            "asin": asin,
            "title": look.get("title") or "",
            "img": look.get("img") or "",
            "impressions": _f(a.get("impressions")), "clicks": _f(a.get("clicks")),
            "spend": (round(spend, 2) if spend is not None else None),
            "orders": _f(a.get("orders")),
            "sales": (round(sales, 2) if sales is not None else None),
            "acos_pct": _rate(spend, sales),
            "sessions": _f(b.get("sessions")), "page_views": _f(b.get("page_views")),
            "buy_box_pct": (round(_f(b.get("buy_box_pct")), 1)
                            if _f(b.get("buy_box_pct")) is not None else None),
            # CVR here is the LISTING's, not the ad's: units per session is what
            # the Business Report means by conversion, and mixing it with the
            # ad's orders-per-click would put two different rates in one column.
            "cvr_pct": _rate(_f(b.get("units")), _f(b.get("sessions")), nd=2),
            "profit": profit,
            "profit_estimated": can_profit,
        })
    out.sort(key=lambda x: (x["spend"] is None, -(x["spend"] or 0)))
    return out


# ---------------------------------------------------------------------------
# Search terms
# ---------------------------------------------------------------------------


def terms(config_path, workspace_id, marketplace, rate_info=None, limit=1000,
          start=None, end=None):
    """Every stored search term, with a branded flag and an opportunity score.

    The reading and the branded test both belong to domain/ppc_view, which the
    existing PPC screen already uses -- asked, not reimplemented, so one term
    cannot be branded on one screen and not on another (Rule 12).

    A WINDOW IS HONOURED WHEN THE ROWS CARRY DAYS.

        "The Search Terms page DOES respect the date picker ... The backend
         re-queries the stored daily search term records for the selected
         window. It is NOT a fixed batch sliced client-side."

    Passed straight to load_rows, which keeps undated rows in every window --
    an account whose report came from an uploaded file has no days to filter on,
    and emptying its table the moment a picker moved would be a worse answer
    than showing the window the report actually covers. ppc_view.dated_window()
    says which case a screen is in.
    """
    from domain import ppc_view as _pv

    r = rate_info or {}
    fee, cogs = r.get("fee_rate"), r.get("cogs_rate")
    can_profit = (fee is not None and cogs is not None)
    be = r.get("breakeven_acos_pct")

    brands = _pv.brand_terms(config_path, workspace_id)
    rows = _pv.load_rows(config_path, workspace_id, marketplace,
                         start=start, end=end)
    out = []
    for row in rows[:limit]:
        d = dict(row)
        spend, sales = _f(d.get("spend")), _f(d.get("sales"))
        clicks, orders = _f(d.get("clicks")), _f(d.get("orders"))
        profit = None
        if can_profit and spend is not None and sales is not None:
            profit = round(sales - spend - sales * float(fee) - sales * float(cogs), 2)
        term = str(d.get("search_term") or "")
        out.append({
            "search_term": term,
            "keyword": d.get("keyword") or "",
            "match_type": str(d.get("match_type") or ""),
            "campaign": d.get("campaign") or "",
            "ad_group": d.get("ad_group") or "",
            "impressions": _f(d.get("impressions")), "clicks": clicks,
            "spend": (round(spend, 2) if spend is not None else None),
            "orders": orders,
            "sales": (round(sales, 2) if sales is not None else None),
            "acos_pct": _rate(spend, sales),
            "roas": _rate(sales, spend, pct=False, nd=2),
            "ctr_pct": _rate(clicks, _f(d.get("impressions")), nd=2),
            "cpc": _rate(spend, clicks, pct=False, nd=2),
            "cpa": _rate(spend, orders, pct=False, nd=2),
            "cvr_pct": _rate(orders, clicks, nd=2),
            "branded": _pv.is_branded(term, brands),
            # An ASIN in the search term column is a product-targeting
            # placement, not something anybody typed into Amazon.
            "product_target": term.lower().startswith("b0"),
            "profit": profit,
            "profit_estimated": can_profit,
            "opportunity": _opportunity(spend, sales, clicks, orders, be),
        })
    out.sort(key=lambda x: (x["spend"] is None, -(x["spend"] or 0)))
    return out


def by_group(rows, key):
    """Fold term or campaign rows onto one column -- match type, ad product.

    One folder for every breakdown on the three screens, so match types and
    campaign types cannot end up computing ACOS two different ways.
    """
    acc = {}
    for r in rows or []:
        k = str(r.get(key) or "") or "(none)"
        a = acc.setdefault(k, {"key": k, "n": 0, "impressions": 0.0, "clicks": 0.0,
                               "spend": 0.0, "orders": 0.0, "sales": 0.0,
                               "profit": 0.0, "profit_known": True})
        a["n"] += 1
        for f in ("impressions", "clicks", "spend", "orders", "sales"):
            v = _f(r.get(f))
            if v:
                a[f] += v
        p = r.get("profit")
        if p is None:
            a["profit_known"] = False
        else:
            a["profit"] += float(p)
    out = []
    for a in acc.values():
        a["spend"] = round(a["spend"], 2)
        a["sales"] = round(a["sales"], 2)
        a["profit"] = round(a["profit"], 2) if a["profit_known"] else None
        a["acos_pct"] = _rate(a["spend"], a["sales"])
        a["roas"] = _rate(a["sales"], a["spend"], pct=False, nd=2)
        a["ctr_pct"] = _rate(a["clicks"], a["impressions"], nd=2)
        a["cpc"] = _rate(a["spend"], a["clicks"], pct=False, nd=2)
        a["cpa"] = _rate(a["spend"], a["orders"], pct=False, nd=2)
        a["cvr_pct"] = _rate(a["orders"], a["clicks"], nd=2)
        out.append(a)
    total = sum(a["spend"] or 0 for a in out)
    tprofit = sum((a["profit"] or 0) for a in out if a["profit"] is not None)
    for a in out:
        a["spend_share_pct"] = _rate(a["spend"], total)
        a["profit_share_pct"] = (_rate(a["profit"], tprofit)
                                 if a["profit"] is not None else None)
    out.sort(key=lambda x: -(x["spend"] or 0))
    return out


def branded_split(rows):
    """Branded against everything else. Paying to appear on your own name.

    The most useful cut on the screen: defensive spend mixed in with the rest
    makes a healthy-looking ACOS out of money that never won a new customer.

    "NO BRAND TERMS SET UP" IS NOT "NOTHING IS BRANDED".
    ppc_view.is_branded returns None, deliberately, when the brand list is
    empty -- "not set up: not 'no', which is a claim". The first version of this
    read that None as falsey and reported all 774 terms as non-branded, which is
    a measurement nobody made: it would have shown a confident 0% branded spend
    for an account that had simply never typed its brand in. Now an unanswered
    split says so and asks for the terms.
    """
    rows = rows or []
    unknown = [r for r in rows if r.get("branded") is None]
    if unknown and len(unknown) == len(rows):
        return {"branded": None, "non_branded": None,
                "branded_terms": None, "non_branded_terms": None,
                "why": ("No brand terms are set for this account, so branded "
                        "and non-branded spend cannot be told apart. Add your "
                        "brand words on the PPC screen — paying to appear on "
                        "your own name is defensive spend, and mixed in with "
                        "the rest it makes a healthy-looking ACOS out of money "
                        "that never won a new customer.")}

    b = [r for r in rows if r.get("branded") is True]
    n = [r for r in rows if r.get("branded") is False]
    folded = by_group(
        [dict(r, _b=("branded" if r.get("branded") else "non_branded"))
         for r in rows if r.get("branded") is not None], "_b")
    out = {"branded": None, "non_branded": None, "why": "",
           "branded_terms": len(b), "non_branded_terms": len(n)}
    for f in folded:
        out[f["key"]] = f
    if unknown:
        out["unclassified_terms"] = len(unknown)
    return out
