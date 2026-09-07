"""domain/ppc_targeting.py -- spend split by MATCH TYPE, at a daily grain.

WHAT THIS IS FOR, AND WHY IT IS NOT THE SEARCH TERM REPORT

The Campaign Analytics page draws spend split by match type twice: as a donut
for the window, and as a stacked area BY DAY. The spec is explicit about the
source and repeats it for both:

    "Data from daily targeting-level reports (keyword/target grain), NOT search
     term report"

ppc_search_terms also carries a match_type, and using it would have been easier
because it was already there. It would also have been wrong, in a way nobody
would have noticed:

  IT IS PRIVACY-THRESHOLDED. Amazon suppresses low-volume queries from the
  Search Term Report, so its spend is short of what was actually billed. The
  spec's own reconciliation on the reference account: campaign reports 11,768,
  search terms 11,703. A donut whose slices are drawn from the smaller figure
  sits next to a total drawn from the larger one and does not add up to it.

  IT HAD NO DATES. Until the daily-grain change it was stored one batch per
  window, so a stacked area BY DAY could not be drawn from it at all.

ads_targeting_daily is the fifth cut of the same money -- account, per-ASIN,
per-campaign, per-placement, per-targeting -- and the rule that governs all of
them governs this one: NOTHING MAY EVER ADD TWO GRAINS TOGETHER. Each answers
the same question a different way and each sums to the same total on its own.

THE CLICK GAP IS REAL AND IS REPORTED, NOT HIDDEN

Match-type clicks do not add up to campaign clicks, and the spec says so:

    "Auto campaign clicks use targeting predicates (close-match, loose-match,
     substitutes, complements), not standard match types. SB store/video clicks
     also don't map to keyword match types. The gap is real and expected --
     display both totals."

So gap() measures it rather than explaining it away. An auto campaign's spend
is not missing -- it arrives under TARGETING_EXPRESSION_PREDEFINED, which is
Amazon's literal enum string and is kept as sent (see ads_sync._upsert_targeting).
label_for() makes it readable at the edge, where a person sees it.
"""
from data import db as _db

# Amazon's own strings, and what to call them on screen. The KEY is what the
# database holds; nothing here rewrites what was stored.
MATCH_LABELS = {
    "EXACT": "Exact",
    "PHRASE": "Phrase",
    "BROAD": "Broad",
    # Auto targeting. Amazon returns the enum, and the actual predicate --
    # close-match, loose-match, substitutes, complements -- arrives in the
    # keyword column beside it.
    "TARGETING_EXPRESSION_PREDEFINED": "Auto",
    # Product and category targeting, which the spec calls PAT.
    "TARGETING_EXPRESSION": "Product targeting",
}

# The order the donut and the table read in. Biggest, most familiar buys first;
# auto and product targeting after, because they are a different kind of buy.
MATCH_ORDER = ["EXACT", "PHRASE", "BROAD", "TARGETING_EXPRESSION",
               "TARGETING_EXPRESSION_PREDEFINED"]


def _f(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _rate(top, bottom, pct=True, nd=1):
    t, b = _f(top), _f(bottom)
    if t is None or not b:
        return None
    return round((100.0 * t / b) if pct else (t / b), nd)


def label_for(match_type):
    """A readable name, with Amazon's own string kept for anything unmapped.

    An unknown value is SHOWN AS ITSELF rather than bucketed into "Other".
    Amazon adds enum values, and a new one silently swept into Other is spend
    that disappears from a chart while still being counted in the total beside
    it -- which reads as an arithmetic error in the page.
    """
    m = str(match_type or "").strip()
    if not m:
        return "Not stated"
    return MATCH_LABELS.get(m.upper(), m)


def available(config_path, workspace_id, marketplace):
    """Is there targeting data at all? -> dict the screen can render instead.

    Its own answer rather than a bare count, because "no targeting report yet"
    is a setup state and not an empty result: the page has to say the donut is
    waiting on a sync rather than drawing an empty circle that reads as an
    account that targeted nothing.
    """
    out = {"ok": False, "rows": 0, "days": 0, "first": "", "last": "", "why": ""}
    try:
        r = _db.get_db(config_path).execute(
            "SELECT COUNT(*) n, COUNT(DISTINCT date) d, MIN(date) a, "
            "MAX(date) b FROM ads_targeting_daily "
            "WHERE workspace_id=? AND marketplace=?",
            (workspace_id, marketplace)).fetchone()
    except Exception:
        out["why"] = ("The targeting table could not be read, so spend cannot "
                      "be split by match type.")
        return out
    if not r or not r["n"]:
        out["why"] = (
            "No targeting report is stored for this account, so spend cannot "
            "be split by match type. It arrives from the Advertising API sync "
            "as the spTargeting report -- the Search Term Report is not a "
            "substitute, because Amazon suppresses low-volume queries from it "
            "and its spend is short of what was billed.")
        return out
    out.update({"ok": True, "rows": int(r["n"]), "days": int(r["d"] or 0),
                "first": r["a"] or "", "last": r["b"] or ""})
    return out


def by_match_type(config_path, workspace_id, marketplace, start, end,
                  fee_rate=None, cogs_rate=None):
    """The match-type table and the donut: one row per match type in the window.

    Columns are the spec's: clicks, CTR, CPC, CPA, spend, % spend, sales, ACOS,
    profit, % profit.

    "% Profit" IS A SHARE OF THE PROFIT POOL, NOT A MARGIN. The spec is explicit
    -- "Share of total profit pool, NOT margin on spend" -- and the difference
    is not cosmetic: a lane earning 30 on 100 of spend has a 30% margin and might
    be 5% of the profit pool. Computed against the pool of POSITIVE profit only,
    because a loss-making lane would otherwise shrink the denominator and push
    every other lane's share above what it earned.
    """
    rows = []
    try:
        cur = _db.get_db(config_path).execute(
            "SELECT match_type, SUM(impressions) impressions, SUM(clicks) clicks, "
            "  ROUND(SUM(spend),2) spend, SUM(ad_orders) orders, "
            "  ROUND(SUM(ad_sales),2) sales "
            "FROM ads_targeting_daily WHERE workspace_id=? AND marketplace=? "
            "  AND date>=? AND date<=? GROUP BY match_type",
            (workspace_id, marketplace, str(start), str(end)))
        rows = [dict(r) for r in cur]
    except Exception:
        return []
    if not rows:
        return []

    can_profit = (fee_rate is not None and cogs_rate is not None)
    tot_spend = sum((_f(r["spend"]) or 0.0) for r in rows)

    out = []
    for r in rows:
        spend, sales = _f(r["spend"]), _f(r["sales"])
        profit = None
        if can_profit and spend is not None and sales is not None:
            profit = round(sales - spend - sales * float(fee_rate)
                           - sales * float(cogs_rate), 2)
        out.append({
            "match_type": r["match_type"] or "",
            # `key` is the name by_group() uses and the Campaign Analytics donut
            # already reads. Kept so this can replace that source without the
            # screen changing shape, rather than renaming a field and making the
            # ring silently blank (Rule 12).
            "key": r["match_type"] or "",
            "label": label_for(r["match_type"]),
            "impressions": int(r["impressions"] or 0),
            "clicks": int(r["clicks"] or 0),
            "orders": int(r["orders"] or 0),
            "spend": spend, "sales": sales,
            "ctr_pct": _rate(r["clicks"], r["impressions"], nd=2),
            "cpc": _rate(spend, r["clicks"], pct=False, nd=2),
            # UNDEFINED WITHOUT AN ORDER, never zero -- the same rule the
            # campaign table follows.
            "cpa": _rate(spend, r["orders"], pct=False, nd=2),
            "acos_pct": _rate(spend, sales),
            "roas": _rate(sales, spend, pct=False, nd=2),
            "spend_share_pct": _rate(spend, tot_spend),
            "profit": profit,
        })

    pool = sum(r["profit"] for r in out
               if r["profit"] is not None and r["profit"] > 0)
    for r in out:
        r["profit_share_pct"] = (
            _rate(r["profit"], pool)
            if (pool and r["profit"] is not None and r["profit"] > 0) else None)

    known = {m: i for i, m in enumerate(MATCH_ORDER)}
    out.sort(key=lambda r: (known.get(str(r["match_type"]).upper(), 99),
                            -(r["spend"] or 0)))
    return out


def daily_by_match_type(config_path, workspace_id, marketplace, start, end,
                        metric="spend"):
    """The stacked area: one column per day, one line per match type.

    Returned in the shape the app's own chart engine takes -- `columns` (the
    dates) and `lines` (a name and its values) -- rather than a new shape of its
    own, so this chart pans, zooms and hovers exactly like every other one on
    the site (Rule 12).

    EVERY DAY IN THE WINDOW APPEARS, including days with no spend, and a day a
    lane did not run is 0 rather than a gap. On a stacked area a gap is not a
    hole, it is a step in every lane above it -- so a missing Sunday would
    visibly change the shape of lanes that did run.
    """
    import datetime as _dt

    col = {"spend": "spend", "clicks": "clicks", "sales": "ad_sales",
           "impressions": "impressions",
           "orders": "ad_orders"}.get(str(metric), "spend")
    got = {}
    try:
        cur = _db.get_db(config_path).execute(
            "SELECT date, match_type, ROUND(SUM(%s),2) v "
            "FROM ads_targeting_daily WHERE workspace_id=? AND marketplace=? "
            "  AND date>=? AND date<=? GROUP BY date, match_type" % col,
            (workspace_id, marketplace, str(start), str(end)))
        for r in cur:
            got.setdefault(str(r["match_type"] or ""), {})[r["date"]] = _f(r["v"], 0.0)
    except Exception:
        return {"columns": [], "lines": []}
    if not got:
        return {"columns": [], "lines": []}

    try:
        s = _dt.date.fromisoformat(str(start)[:10])
        e = _dt.date.fromisoformat(str(end)[:10])
    except ValueError:
        return {"columns": [], "lines": []}
    days, d = [], s
    while d <= e:
        days.append(d.isoformat())
        d += _dt.timedelta(days=1)

    known = {m: i for i, m in enumerate(MATCH_ORDER)}
    order = sorted(got, key=lambda m: (known.get(m.upper(), 99), m))
    lines = [{"key": m, "name": label_for(m),
              "values": [round(got[m].get(day, 0.0), 2) for day in days]}
             for m in order]
    return {"columns": days, "lines": lines, "metric": metric}


def gap(config_path, workspace_id, marketplace, start, end):
    """How far the targeting grain falls short of the campaign grain, measured.

    The spec expects a shortfall and says to show both totals rather than
    reconcile them away. This measures it instead of asserting it, because the
    SIZE is the useful part: a few pence is auto campaigns rounding, and a third
    of the spend missing is a report that did not finish syncing.

    Returns None for the shortfall when either side has nothing, rather than 0 --
    "no targeting data" and "no gap" are opposite findings.
    """
    out = {"targeting_spend": None, "campaign_spend": None,
           "gap": None, "gap_pct": None, "why": ""}
    try:
        conn = _db.get_db(config_path)
        t = conn.execute(
            "SELECT ROUND(SUM(spend),2) s, SUM(clicks) c FROM ads_targeting_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=?",
            (workspace_id, marketplace, str(start), str(end))).fetchone()
        c = conn.execute(
            "SELECT ROUND(SUM(spend),2) s, SUM(clicks) c FROM ads_campaign_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=?",
            (workspace_id, marketplace, str(start), str(end))).fetchone()
    except Exception:
        return out
    ts = _f(t["s"]) if t else None
    cs = _f(c["s"]) if c else None
    out["targeting_spend"], out["campaign_spend"] = ts, cs
    out["targeting_clicks"] = int((t["c"] if t else 0) or 0)
    out["campaign_clicks"] = int((c["c"] if c else 0) or 0)
    if ts is None or cs is None:
        out["why"] = ("One of the two grains has no rows in this window, so "
                      "there is nothing to compare.")
        return out
    out["gap"] = round(cs - ts, 2)
    out["gap_pct"] = _rate(cs - ts, cs, nd=2)
    out["why"] = (
        "Spend split by match type comes to %.2f against %.2f on the campaign "
        "reports, a difference of %.2f. The two are not expected to match: auto "
        "campaigns buy through targeting predicates rather than keyword match "
        "types, and Sponsored Brands store and video placements do not map to a "
        "match type at all. Both totals are shown rather than reconciled."
        % (ts, cs, cs - ts))
    return out
