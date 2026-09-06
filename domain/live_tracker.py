"""domain/live_tracker.py -- the Live Tracker's figures.

Built to LIVE-TRACKER-BUILD-PROMPT.md, which asks for something Amazon will not
supply, and something it will.

WHAT IT ASKS FOR THAT CANNOT EXIST
The page is built around three time ranges -- "Last 24 Hours", "Last 7 Days"
(hourly) and "Day by Day" -- and the first two plot one point per HOUR. There is
no hourly advertising data to plot. Asked of Amazon directly on 6 Sep 2026,
against the one account here with an advertising login:

    spCampaigns          timeUnit HOURLY -> HTTP 400, "configuration timeUnit is
                         not supported for this report type"
    spAdvertisedProduct  timeUnit HOURLY -> the same refusal
    spCampaigns with campaignPlacement, HOURLY -> the same refusal
    spCampaigns with campaignPlacement, DAILY  -> ACCEPTED

So the daily grain is not a simplification chosen here. It is the finest grain
Amazon offers, and the page says so where the hourly ranges would have been
rather than drawing twenty-four points through a day nobody measured. A chart
whose shape implies hourly measurement is a lie told in pictures, and it is the
one thing this app has been asked repeatedly not to do.

WHAT IT ASKS FOR THAT DOES EXIST
The placement breakdown -- top of search, product pages, the rest of Amazon --
is real, and is now pulled and stored. It is the genuinely new thing on this
page: two campaigns spending the same amount are not making the same buy if one
sits at the top of search and the other on a competitor's product page.

CUMULATIVE IS A VIEW, NOT A MEASUREMENT, so it is computed here from the same
rows rather than fetched separately -- the running total and the daily figures
can then never disagree.

Nothing here writes anything (Rule 8).
"""
import datetime as _dt

from data import db as _db
from domain import ppc_analytics as _pa

ACCOUNT_TOTAL = "*"

# Amazon's own placement words, and what to call them on screen. The KEY is
# whatever Amazon sent -- anything unrecognised is shown under Amazon's own
# spelling rather than dropped, because a placement nobody has seen before is
# still real spend.
PLACEMENT_LABELS = {
    "Top of Search on-Amazon": "Top of Search",
    "Detail Page on-Amazon": "Product Pages",
    "Other on-Amazon": "Rest of Amazon",
    "Off Amazon": "Off Amazon",
}

# The ranges this page can honestly offer.
RANGES = (
    ("7", "Last 7 days", 7),
    ("14", "Last 14 days", 14),
    ("30", "Last 30 days", 30),
)

HOURLY_WHY = (
    "Amazon does not provide advertising figures by the hour through its "
    "reporting API. Asked directly — spCampaigns, spAdvertisedProduct and the "
    "placement report all refuse timeUnit HOURLY with \"configuration timeUnit "
    "is not supported for this report type\". Every advertising row Amazon "
    "sends is one whole day, so an hourly view would be twenty-four invented "
    "points per day. The ranges below are days, which is the finest grain that "
    "exists."
)


def hourly_state(config_path=None):
    """Whether hourly data exists, and the sentence to show when it does not.

    ONE MODULE DECIDES THIS FOR THE WHOLE APP. This file used to answer a flat
    False with a paragraph of its own, and the PPC Analytics screen answered the
    same question with a different paragraph of its own. Two answers to one
    question drift the first time either changes -- and the day an AWS queue
    does appear, exactly one thing should start saying yes (Rule 12).

    domain/ams.py holds it. Its `available` follows STORED ROWS rather than an
    environment variable, which is the distinction that matters here: a queue
    URL can be set hours before the first message lands, and this page
    abandoning a correct daily chart for an empty hourly one would be a
    regression dressed as a feature.

    The refusal above is kept and appended to what ams says, because it is a
    DIFFERENT fact and both are worth having: ams explains that the push
    integration is not set up, and this explains that the pull API has no hourly
    data either, so nobody goes looking for a report that does not exist.
    """
    try:
        from domain import ams as _ams
        st = _ams.status(config_path)
    except Exception:
        return {"available": False, "why": HOURLY_WHY}
    if st.get("available"):
        return {"available": True, "why": ""}
    return {"available": False,
            "configured": st.get("configured"),
            "why": "%s %s" % (st.get("why") or "", HOURLY_WHY)}


def _f(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _win(days, end=None):
    e = _dt.date.fromisoformat(end) if end else _dt.date.today()
    return (e - _dt.timedelta(days=int(days) - 1)).isoformat(), e.isoformat()


def series(config_path, workspace_id, marketplace, days=7, cumulative=False):
    """The main chart: one point per DAY, and why it is not per hour. -> dict.

    Cumulative is applied here, over the same rows, so the running total and the
    daily figures cannot disagree. A day with no advertising row stays None and
    is NOT carried forward in the cumulative view either -- a flat step across a
    day nobody measured looks exactly like a day of no spend.
    """
    start, end = _win(days)
    rows = _pa.daily(config_path, workspace_id, marketplace, start, end)

    out, run = [], {"spend": 0.0, "ad_sales": 0.0, "total_sales": 0.0,
                    "impressions": 0.0, "clicks": 0.0, "orders": 0.0}
    for r in rows:
        point = {"date": r["date"]}
        known = r.get("spend") is not None
        for k in ("spend", "ad_sales", "total_sales", "impressions", "clicks",
                  "orders"):
            v = _f(r.get(k))
            if cumulative:
                if v is None:
                    # NOT carried forward. A cumulative line that steps flat
                    # across an unmeasured day is indistinguishable from one
                    # that steps flat across a day of no spend.
                    point[k] = None if not known else run[k]
                else:
                    run[k] += v
                    point[k] = round(run[k], 2)
            else:
                point[k] = v
        # TACOS per point, recomputed rather than accumulated: a ratio of two
        # running totals is not the running total of a ratio.
        sp = point.get("spend")
        ts = point.get("total_sales")
        point["tacos_pct"] = (round(100.0 * sp / ts, 2)
                              if (sp is not None and ts) else None)
        ads = point.get("ad_sales")
        point["acos_pct"] = (round(100.0 * sp / ads, 2)
                             if (sp is not None and ads) else None)
        out.append(point)

    _h = hourly_state(config_path)
    return {"points": out, "start": start, "end": end, "days": int(days),
            "cumulative": bool(cumulative),
            "hourly_available": bool(_h.get("available")),
            "hourly_why": _h.get("why") or ""}


def kpis(config_path, workspace_id, marketplace, days=7):
    """The six cards. Every one a sum or a recomputed ratio over the window."""
    start, end = _win(days)
    t = _pa.totals_for(config_path, workspace_id, marketplace, start, end)
    return {
        "start": start, "end": end,
        "spend": t.get("spend"), "total_sales": t.get("total_sales"),
        "ad_sales": t.get("sales"),
        "tacos_pct": t.get("tacos_pct"), "acos_pct": t.get("acos_pct"),
        "orders": t.get("orders"), "clicks": t.get("clicks"),
        "impressions": t.get("impressions"),
        "has_data": bool(t.get("has_data")),
        # UNITS IS NOT ORDERS, and this page's mockup asks for both. Only ad
        # ORDERS are attributed per campaign; units sold through advertising are
        # not stored, so the card says so rather than repeating the order count
        # under a second name.
        "units": None,
        "units_why": ("Units sold through advertising are not stored — only ad "
                      "ORDERS are attributed. Showing the order count here "
                      "under a second name would report one figure twice."),
    }


def placements(config_path, workspace_id, marketplace, days=7, asin=None):
    """Where the ads appeared, per day. -> dict.

    THE NEW THING ON THIS PAGE, and the only part of the mockup's per-ASIN
    breakdown Amazon actually supports.

    PER ASIN IS NOT AVAILABLE and is not faked. The placement report groups by
    campaign and placement; there is no advertised-ASIN column in it. A campaign
    usually advertises several products, so splitting its placement spend across
    its ASINs would be an assumption dressed as a measurement. `asin` is accepted
    and reported back as unsupported rather than silently ignored.
    """
    start, end = _win(days)
    conn = _db.get_db(config_path)
    have = 0
    try:
        have = conn.execute(
            "SELECT COUNT(*) FROM ads_placement_daily WHERE workspace_id=? "
            "AND marketplace=?", (workspace_id, marketplace)).fetchone()[0] or 0
    except Exception:
        have = 0
    if not have:
        return {"rows": [], "by_day": [], "labels": PLACEMENT_LABELS,
                "start": start, "end": end, "has_data": False,
                "asin_supported": False,
                "why": ("No placement rows are stored for this account yet. "
                        "They arrive with the advertising sync, which now asks "
                        "for the placement report alongside the others.")}

    rows = []
    for r in conn.execute(
            "SELECT placement, ROUND(SUM(spend),2) spend, SUM(clicks) clicks, "
            "SUM(impressions) impressions, SUM(ad_orders) orders, "
            "ROUND(SUM(ad_sales),2) sales FROM ads_placement_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
            "GROUP BY placement ORDER BY spend DESC",
            (workspace_id, marketplace, start, end)):
        d = dict(r)
        d["label"] = PLACEMENT_LABELS.get(d["placement"], d["placement"])
        sp, sa = _f(d["spend"]), _f(d["sales"])
        d["acos_pct"] = (round(100.0 * sp / sa, 1) if (sp is not None and sa)
                         else None)
        d["cpc"] = (round(sp / d["clicks"], 2)
                    if (sp is not None and d["clicks"]) else None)
        rows.append(d)

    by_day = {}
    for r in conn.execute(
            "SELECT date, placement, ROUND(SUM(spend),2) spend, "
            "SUM(clicks) clicks, SUM(impressions) impressions, "
            "ROUND(SUM(ad_sales),2) sales FROM ads_placement_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
            "GROUP BY date, placement ORDER BY date",
            (workspace_id, marketplace, start, end)):
        by_day.setdefault(r["date"], {})[r["placement"]] = dict(r)

    total = sum(_f(r["spend"]) or 0.0 for r in rows)
    for r in rows:
        r["share_pct"] = (round(100.0 * (_f(r["spend"]) or 0.0) / total, 1)
                          if total else None)

    return {
        "rows": rows,
        "by_day": [{"date": d, "cells": by_day[d]} for d in sorted(by_day)],
        "labels": PLACEMENT_LABELS, "start": start, "end": end,
        "has_data": True, "total_spend": round(total, 2),
        # Said plainly rather than left for somebody to discover from an empty
        # dropdown.
        "asin_supported": False,
        "asin_why": ("Amazon's placement report groups by campaign, not by ASIN "
                     "— there is no advertised-ASIN column in it. A campaign "
                     "usually advertises several products, so splitting its "
                     "placement spend between them would be an assumption "
                     "presented as a measurement."),
        "why": ("Where each ad actually appeared. Two campaigns spending the "
                "same are not making the same buy if one is at the top of "
                "search and the other on a competitor's product page."),
    }


def products(config_path, workspace_id, marketplace, days=7, limit=20):
    """The per-ASIN cards, from the advertised-product rows that DO exist.

    The mockup's own per-ASIN charts are hourly and cannot be drawn. What can be
    drawn is each product's daily line, which is the same question asked at the
    grain Amazon answers.
    """
    start, end = _win(days)
    conn = _db.get_db(config_path)
    out = []
    try:
        for r in conn.execute(
                "SELECT asin, ROUND(SUM(spend),2) spend, SUM(clicks) clicks, "
                "SUM(impressions) impressions, SUM(ad_orders) orders, "
                "ROUND(SUM(ad_sales),2) sales FROM ads_daily "
                "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
                "AND asin<>? GROUP BY asin ORDER BY spend DESC LIMIT ?",
                (workspace_id, marketplace, start, end, ACCOUNT_TOTAL,
                 int(limit))):
            d = dict(r)
            sp, sa = _f(d["spend"]), _f(d["sales"])
            d["acos_pct"] = (round(100.0 * sp / sa, 1)
                             if (sp is not None and sa) else None)
            d["cvr_pct"] = (round(100.0 * (d["orders"] or 0) / d["clicks"], 2)
                            if d["clicks"] else None)
            out.append(d)
    except Exception:
        pass

    # The picture and the name, from the ONE shared lookup rather than from
    # live_snapshots directly (Rule 12).
    if out:
        try:
            from domain import catalogue as _cat
            idx = _cat.merged(config_path, [(workspace_id, marketplace)])
            for d in out:
                info = idx.get(d["asin"]) or {}
                d["title"] = info.get("title") or ""
                d["img"] = info.get("img") or ""
        except Exception:
            for d in out:
                d.setdefault("title", "")
                d.setdefault("img", "")

    total = sum(_f(d["spend"]) or 0.0 for d in out)
    for d in out:
        d["share_pct"] = (round(100.0 * (_f(d["spend"]) or 0.0) / total, 1)
                          if total else None)
    return {"rows": out, "start": start, "end": end,
            "why": ("Per product, per day. The mockup draws these hourly; "
                    "Amazon has no hourly advertising data to draw.")}


def daily_for_asin(config_path, workspace_id, marketplace, asin, days=7):
    """One product's own daily line, for the expanded card."""
    start, end = _win(days)
    conn = _db.get_db(config_path)
    got = {}
    try:
        for r in conn.execute(
                "SELECT date, spend, clicks, impressions, ad_orders orders, "
                "ad_sales sales FROM ads_daily WHERE workspace_id=? AND "
                "marketplace=? AND asin=? AND date>=? AND date<=? ORDER BY date",
                (workspace_id, marketplace, asin, start, end)):
            got[r["date"]] = dict(r)
    except Exception:
        pass
    # EVERY DAY IN THE RANGE, so a gap is a gap rather than the line simply
    # skipping to the next day it has.
    out, d = [], _dt.date.fromisoformat(start)
    last = _dt.date.fromisoformat(end)
    while d <= last:
        ds = d.isoformat()
        r = got.get(ds)
        out.append({"date": ds,
                    "spend": _f(r["spend"]) if r else None,
                    "clicks": (r["clicks"] if r else None),
                    "impressions": (r["impressions"] if r else None),
                    "orders": (r["orders"] if r else None),
                    "sales": _f(r["sales"]) if r else None})
        d += _dt.timedelta(days=1)
    return {"asin": asin, "points": out, "start": start, "end": end}
