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
    NO_HOURS = ("Amazon has not been asked for hourly advertising figures on "
                "this account, and none are stored, so this cannot be drawn. "
                "Every stored row is one whole day. Drawing a curve through "
                "hours nobody measured would look exactly like a measurement.")

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
        # THE TWO PANELS THAT CANNOT BE HONEST TODAY.
        "hourly": {"ok": False, "rows": 0, "why": NO_HOURS},
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
    """One card per day: the spend curve through it, the total, and the units.

    The mockup draws each card as spend accumulating BY HOUR. There are no
    hourly advertising figures -- Amazon refuses timeUnit HOURLY on this report
    type, measured, its own words: "configuration timeUnit is not supported for
    this report type". So each card carries the day's own cumulative shape at
    the finest grain that exists, and the page says the curve is a day rather
    than pretending to twenty-four measured hours.
    """
    end = _dt.date.today()
    start = end - _dt.timedelta(days=int(days) - 1)
    rows = daily(config_path, workspace_id, marketplace,
                 start.isoformat(), end.isoformat())
    # THE CURVE IS THE WINDOW ACCUMULATING, not the day. Said in the caption
    # rather than drawn as if it were hours.
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


def change(now, before):
    """Percentage change per metric, or None. Never a change against nothing.

    A move from no data to a number is not a rise, and rendering it as +100%
    invites somebody to celebrate a sync finishing.
    """
    out = {}
    for k, v in (now or {}).items():
        b = (before or {}).get(k)
        if not isinstance(v, (int, float)) or not isinstance(b, (int, float)):
            out[k] = None
            continue
        if not b:
            out[k] = None
            continue
        out[k] = round(100.0 * (float(v) - float(b)) / abs(float(b)), 1)
    return out


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


def campaigns(config_path, workspace_id, marketplace, start, end, rate_info=None):
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
    out = []
    for row in conn.execute(
            "SELECT campaign_id, MAX(campaign_name) name, MAX(status) status, "
            "MAX(budget) budget, MAX(ad_product) ad_product, "
            "SUM(impressions) impressions, SUM(clicks) clicks, "
            "SUM(spend) spend, SUM(ad_orders) orders, SUM(ad_sales) sales "
            "FROM ads_campaign_daily WHERE workspace_id=? AND marketplace=? "
            "AND date>=? AND date<=? GROUP BY campaign_id",
            (workspace_id, marketplace, start, end)):
        d = dict(row)
        spend, sales = _f(d["spend"]), _f(d["sales"])
        profit = None
        if can_profit and spend is not None and sales is not None:
            profit = round(sales - spend - sales * float(fee) - sales * float(cogs), 2)
        d.update({
            "spend": (round(spend, 2) if spend is not None else None),
            "sales": (round(sales, 2) if sales is not None else None),
            "acos_pct": _rate(spend, sales),
            "roas": _rate(sales, spend, pct=False, nd=2),
            "ctr_pct": _rate(_f(d["clicks"]), _f(d["impressions"]), nd=2),
            "cpc": _rate(spend, _f(d["clicks"]), pct=False, nd=2),
            "cpa": _rate(spend, _f(d["orders"]), pct=False, nd=2),
            "cvr_pct": _rate(_f(d["orders"]), _f(d["clicks"]), nd=2),
            "profit": profit,
            "profit_estimated": can_profit,
            "cohort": _cohort(spend, sales, profit, be, can_profit),
            "opportunity": _opportunity(spend, sales, _f(d["clicks"]),
                                        _f(d["orders"]), be),
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
    if profit > 0:
        # MARGINAL is "profitable, but only just" -- inside a tenth of
        # break-even, where a small CPC rise takes it under.
        acos = _rate(spend, sales)
        if breakeven_acos and acos is not None and acos > breakeven_acos * 0.9:
            return MARGINAL
        return PROFITABLE
    return UNPROFITABLE


def _opportunity(spend, sales, clicks, orders, breakeven_acos):
    """0-100: how much is there to gain by touching this one?

    OUR OWN DEFINITION, STATED, because Orbit does not publish its own and
    copying an unexplained number is how a screen ends up with a score nobody
    can act on. Three things raise it, all of them things you would actually do
    something about:

        money at stake     a campaign spending 2 pounds is not worth an hour
        distance from      the further past break-even, the more there is to fix
          break-even
        clicks with no     spend that has bought traffic and no orders is the
          orders           clearest waste there is

    None when there is nothing to score -- no spend means no opportunity and no
    problem, and a 0 would sort alongside campaigns that are merely fine.
    """
    s = _f(spend)
    if not s:
        return None
    score = 0.0
    # Money at stake, flattening out: 50 pounds and 500 pounds are both "worth
    # looking at", and a linear scale would let one big campaign own the list.
    score += min(40.0, 40.0 * (s ** 0.5) / 20.0)
    acos = _rate(s, _f(sales))
    if acos is None:
        score += 35.0           # spent, sold nothing: the clearest case there is
    elif breakeven_acos and acos > breakeven_acos:
        score += min(35.0, 35.0 * (acos - breakeven_acos) / max(breakeven_acos, 1))
    c, o = _f(clicks) or 0, _f(orders) or 0
    if c >= 10 and not o:
        score += 25.0
    elif c and o:
        score += max(0.0, 25.0 * (1.0 - min(1.0, (o / c) / 0.10)))
    return int(round(min(100.0, score)))


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


def wasted_spend(config_path, workspace_id, marketplace, start, end):
    """Spend that bought clicks and no orders. OUR DEFINITION, SAID OUT LOUD.

    Orbit shows a "wasted spend" figure and does not define it. This one is:
    the spend on search terms that took at least one click and produced no
    order, in the stored report's window. Not "ACOS above target" -- that is a
    judgement about price; this is money that bought traffic which bought
    nothing, which nobody disputes.
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


def terms(config_path, workspace_id, marketplace, rate_info=None, limit=1000):
    """Every stored search term, with a branded flag and an opportunity score.

    The reading and the branded test both belong to domain/ppc_view, which the
    existing PPC screen already uses -- asked, not reimplemented, so one term
    cannot be branded on one screen and not on another (Rule 12).
    """
    from domain import ppc_view as _pv

    r = rate_info or {}
    fee, cogs = r.get("fee_rate"), r.get("cogs_rate")
    can_profit = (fee is not None and cogs is not None)
    be = r.get("breakeven_acos_pct")

    brands = _pv.brand_terms(config_path, workspace_id)
    rows = _pv.load_rows(config_path, workspace_id, marketplace)
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
