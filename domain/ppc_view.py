"""domain/ppc_view.py -- what the advertising is doing, and what it is wasting.

    "dive a detailed harvest of ppc feature in orbit and then develope same
     feature in my app"

ORBIT'S SCREENS, REBUILT ON A FILE YOU CAN DOWNLOAD TODAY

The harvest is in orbit_ppc_complete.md. Orbit's PPC section is five routes; the
metrics on four of them come from data this app can have without connecting
anything new:

    AD SPEND, AD SALES, ACOS, ROAS, CTR, CVR, AVG CPC, WASTED SPEND
    the per-search-term table, with a match-type and branded/non-branded cut
    the campaign and match-type breakdown, with % of spend against % of profit

WHY NOT THE ADVERTISING API. It is a separate OAuth from SP-API -- its own
client id, secret, refresh token and profile id -- and it is connected on none
of the six accounts. Measured 18 Aug 2026: ads_daily 0 rows, ppc_campaigns
0 rows, no credentials anywhere. Waiting for it would mean shipping empty
screens.

The SP Search Term Report is downloadable from Seller Central by hand, and
domain/ppc_module.py has been able to read one since it was written. It simply
never kept the rows -- /ppc/harvest turned an upload into three CSVs and threw
them away. data/db.py now has ppc_search_terms, and this module is what reads it.

THE FORMULAS, AND WHERE EACH ONE COMES FROM

    ACOS  = spend / sales                    industry standard; checked against
    ROAS  = sales / spend                    Orbit's own rendered figures --
    CTR   = clicks / impressions             1,639/8,569 = 19.1% and
    CVR   = orders / clicks                  1,639/18,150 = 9.03%, both exact
    CPC   = spend / clicks
    CPA   = spend / orders                   cost per ACQUISITION, not per click
    TACOS = spend / TOTAL sales              needs sales the ads did not make,
                                             which this app has in order_lines

WASTED SPEND is Orbit's own metric and the best thing on its screen: spend on
terms that produced no sales. It turns "your ACOS is 14.9%" into "here is 2,891
you could stop spending", which is an action rather than a score. Orbit does not
state its definition, so ours is stated here: **spend on search terms with zero
orders in the window**. Anything cleverer would be a guess at someone else's
arithmetic.

NOTHING HERE WRITES TO AMAZON. CLAUDE.md Rule 8: no bid, no budget, no negation
is ever applied from this module. It reports, and where it has an opinion it
says "this term has spent X and sold nothing" and leaves the decision alone.
"""

import datetime as _dt

# A term is only worth judging once it has had a fair run. Below this a zero-sale
# term is not evidence of waste -- it is evidence of nothing, and negating on it
# would be throwing away terms that had never been given a chance to convert.
MIN_CLICKS_TO_JUDGE = 10

# Spend on a zero-order term above this is worth surfacing on its own, rather
# than only inside the wasted-spend total. Stated rather than hidden.
WASTE_ALERT_SPEND = 10.0


def _f(v, d=0.0):
    try:
        f = float(v)
        return f if f == f else d
    except (TypeError, ValueError):
        return d


def _i(v, d=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


def rate(top, bottom, pct=True, nd=1):
    """top/bottom, or None when the question does not arise.

    NONE, NEVER ZERO. A term with no clicks does not have a CTR of 0% -- it has
    no CTR, and printing 0% invites somebody to act on a number that was never
    measured. Every derived metric in this module goes through here, which is
    the same rule the rest of the app applies to an unknown cost or velocity.
    """
    b = _f(bottom, 0.0)
    if not b:
        return None
    v = _f(top, 0.0) / b
    return round(v * 100.0, nd) if pct else round(v, 2)


def brand_terms(config_path, workspace_id):
    """The seller's own brand words, lower-cased. [] when none are set."""
    from data import db as _db
    try:
        conn = _db.get_db(config_path)
        return [str(r["term"]).strip().lower()
                for r in conn.execute(
                    "SELECT term FROM ppc_brand_terms WHERE workspace_id=? "
                    "ORDER BY term", (workspace_id,))
                if str(r["term"] or "").strip()]
    except Exception:
        return []


def is_branded(term, brands):
    """Does this search term contain one of the brand's own words?

    Substring, deliberately: "flux footwear mens" and "fluxfootwear" and
    "flux sandals" are all defending the brand, and requiring a whole-word match
    would count the first as prospecting. Over-counting branded spend is the
    safer error -- it makes the non-branded figure, which is the one being
    judged, conservative.
    """
    if not brands:
        return None                      # not set up: not "no", which is a claim
    t = str(term or "").lower()
    return any(b and b in t for b in brands)


def totals(rows, total_sales=None):
    """The headline row Orbit puts across the top of /ppc and /ppc/search-terms.

    `total_sales` is the whole business's sales for the window -- ad and organic
    together -- which is what makes TACOS possible. It comes from order_lines,
    not from this report, and is left out rather than guessed when absent.
    """
    imp = clicks = orders = units = 0
    spend = sales = 0.0
    waste = 0.0
    waste_terms = 0
    for r in rows or []:
        imp += _i(r.get("impressions"))
        clicks += _i(r.get("clicks"))
        orders += _i(r.get("orders"))
        units += _i(r.get("units"))
        spend += _f(r.get("spend"))
        sales += _f(r.get("sales"))

    # WASTED SPEND, per the definition in this module's docstring: spend on
    # terms that produced no orders. Grouped by TERM first, because the same
    # term across three match types that all failed is one wasted term, not
    # three.
    by_term = {}
    for r in rows or []:
        k = str(r.get("search_term") or "").strip().lower()
        if not k:
            continue
        e = by_term.setdefault(k, {"spend": 0.0, "orders": 0, "clicks": 0})
        e["spend"] += _f(r.get("spend"))
        e["orders"] += _i(r.get("orders"))
        e["clicks"] += _i(r.get("clicks"))
    for k, e in by_term.items():
        if e["orders"] == 0 and e["clicks"] >= MIN_CLICKS_TO_JUDGE:
            waste += e["spend"]
            waste_terms += 1

    out = {
        "impressions": imp, "clicks": clicks, "orders": orders, "units": units,
        "spend": round(spend, 2), "sales": round(sales, 2),
        "acos": rate(spend, sales),
        "roas": rate(sales, spend, pct=False),
        "ctr": rate(clicks, imp),
        "cvr": rate(orders, clicks),
        "cpc": rate(spend, clicks, pct=False),
        "cpa": rate(spend, orders, pct=False),
        "wasted_spend": round(waste, 2),
        "wasted_terms": waste_terms,
        "wasted_pct": rate(waste, spend),
        "terms": len(by_term),
        "rows": len(rows or []),
        "min_clicks_to_judge": MIN_CLICKS_TO_JUDGE,
    }
    # TACOS -- what advertising costs the BUSINESS, not what it costs the ads.
    # A brand can have a healthy ACOS and a TACOS that is eating it, and only
    # the second answers "should I be spending this at all".
    out["total_sales"] = None
    out["tacos"] = None
    out["organic_sales"] = None
    out["tacos_note"] = ""
    if total_sales is not None:
        ts = _f(total_sales)
        out["total_sales"] = round(ts, 2)
        # AD SALES CANNOT EXCEED ALL SALES. When they do, the two figures are
        # not describing the same trade -- the report covers a different window,
        # or a different account, or the orders for that period were never
        # synced. Found while testing: a report showing 1,873 of ad sales
        # against 279 of total sales produced a TACOS of 148%, which is not a
        # high TACOS, it is a contradiction.
        #
        # Reported as one rather than published as a number somebody might act
        # on. The ad-only metrics beside it are unaffected and stay.
        if sales > ts * 1.02 and ts >= 0:
            out["tacos_note"] = (
                "Ad sales in this report (%.2f) are higher than all the sales "
                "recorded for the same dates (%.2f), so TACOS cannot be worked "
                "out. Usually the report covers a different period from the "
                "orders, or belongs to another account. ACOS and everything "
                "else on this page are unaffected." % (sales, ts))
        else:
            out["tacos"] = rate(spend, ts)
            out["organic_sales"] = round(max(0.0, ts - sales), 2)
    return out


def opportunity(term):
    """(flag, why) for one aggregated term. Orbit's `Opp` column, our rules.

    Orbit shows the flag and never states how it decides, so this is ours and
    is described in words on screen rather than as a score nobody can check.

    IT NEVER SAYS "DO THIS". It says what the term has actually done and what
    that usually means. Applying a negation or a bid is a decision with money
    attached and belongs to the person (CLAUDE.md Rule 8).
    """
    clicks = _i(term.get("clicks"))
    orders = _i(term.get("orders"))
    spend = _f(term.get("spend"))
    sales = _f(term.get("sales"))
    acos = rate(spend, sales)

    if clicks < MIN_CLICKS_TO_JUDGE:
        return "", ("Only %d click%s so far — too little to judge either way."
                    % (clicks, "" if clicks == 1 else "s"))
    if orders == 0:
        return "wasting", (
            "%d clicks and no orders. It has cost %.2f and returned nothing."
            % (clicks, spend))
    if acos is not None and acos > 100:
        return "losing", (
            "It sells, but every sale costs more than it makes: %.0f%% ACOS."
            % acos)
    if acos is not None and acos <= 15 and orders >= 2:
        return "scaling", (
            "%d orders at %.0f%% ACOS. It is converting cheaply."
            % (orders, acos))
    return "", ""


def by_term(rows, brands=None):
    """One row per search term, Orbit's Search Terms table.

    Aggregated across match types, campaigns and ad groups -- the report has a
    row per targeting that triggered the term, and a person reading the screen
    is asking about the TERM. The match types it appeared under travel with it
    so nothing is lost.
    """
    agg = {}
    for r in rows or []:
        k = str(r.get("search_term") or "").strip()
        if not k:
            continue
        e = agg.setdefault(k.lower(), {
            "search_term": k, "impressions": 0, "clicks": 0, "orders": 0,
            "units": 0, "spend": 0.0, "sales": 0.0,
            "match_types": set(), "campaigns": set(), "keywords": set()})
        e["impressions"] += _i(r.get("impressions"))
        e["clicks"] += _i(r.get("clicks"))
        e["orders"] += _i(r.get("orders"))
        e["units"] += _i(r.get("units"))
        e["spend"] += _f(r.get("spend"))
        e["sales"] += _f(r.get("sales"))
        for f, s in (("match_type", "match_types"), ("campaign", "campaigns"),
                     ("keyword", "keywords")):
            v = str(r.get(f) or "").strip()
            if v:
                e[s].add(v)

    out = []
    for e in agg.values():
        e["match_types"] = sorted(e["match_types"])
        e["campaigns"] = sorted(e["campaigns"])
        e["keywords"] = sorted(e["keywords"])
        e["spend"] = round(e["spend"], 2)
        e["sales"] = round(e["sales"], 2)
        e["acos"] = rate(e["spend"], e["sales"])
        e["roas"] = rate(e["sales"], e["spend"], pct=False)
        e["ctr"] = rate(e["clicks"], e["impressions"])
        e["cvr"] = rate(e["orders"], e["clicks"])
        e["cpc"] = rate(e["spend"], e["clicks"], pct=False)
        e["cpa"] = rate(e["spend"], e["orders"], pct=False)
        e["profit"] = round(e["sales"] - e["spend"], 2)
        e["branded"] = is_branded(e["search_term"], brands)
        flag, why = opportunity(e)
        e["opportunity"] = flag
        e["why"] = why
        out.append(e)

    # Most money at stake first. Spend, not ACOS: a 400% ACOS on 80p is not the
    # problem, and sorting by ratio puts it above a term quietly burning 200.
    out.sort(key=lambda x: -x["spend"])
    return out


def by_match_type(rows):
    """Orbit's campaign-type table, on the cut this report can actually make.

    Orbit splits by SP/SB/SD, which the Search Term Report does not carry -- it
    is Sponsored Products only. It DOES carry the match type, which is the
    breakdown that changes what you do: broad discovers, exact converts, and
    knowing which is taking the spend is the point.

    Reported with % of spend against % of profit, which is Orbit's own idea and
    the most useful pair of columns on its page: a bucket taking 40% of the
    spend and returning 12% of the profit is visible without arithmetic.
    """
    agg = {}
    for r in rows or []:
        k = str(r.get("match_type") or "unknown").strip().lower() or "unknown"
        e = agg.setdefault(k, {"match_type": k, "impressions": 0, "clicks": 0,
                               "orders": 0, "spend": 0.0, "sales": 0.0})
        e["impressions"] += _i(r.get("impressions"))
        e["clicks"] += _i(r.get("clicks"))
        e["orders"] += _i(r.get("orders"))
        e["spend"] += _f(r.get("spend"))
        e["sales"] += _f(r.get("sales"))

    tot_spend = sum(e["spend"] for e in agg.values())
    tot_profit = sum(e["sales"] - e["spend"] for e in agg.values())
    out = []
    for e in agg.values():
        e["spend"] = round(e["spend"], 2)
        e["sales"] = round(e["sales"], 2)
        e["profit"] = round(e["sales"] - e["spend"], 2)
        e["acos"] = rate(e["spend"], e["sales"])
        e["ctr"] = rate(e["clicks"], e["impressions"])
        e["cvr"] = rate(e["orders"], e["clicks"])
        e["cpc"] = rate(e["spend"], e["clicks"], pct=False)
        e["cpa"] = rate(e["spend"], e["orders"], pct=False)
        e["pct_spend"] = rate(e["spend"], tot_spend)
        # A share of a NEGATIVE total is meaningless -- if the advertising lost
        # money overall, "this bucket is 140% of profit" is noise. Left out.
        e["pct_profit"] = (rate(e["profit"], tot_profit)
                           if tot_profit > 0 else None)
        out.append(e)
    out.sort(key=lambda x: -x["spend"])
    return out


def by_campaign(rows):
    """Orbit's Campaign Analytics table, on what the report actually carries.

    Orbit splits campaigns by SP / SB / SD and shows Enabled / Paused. The
    Search Term Report is Sponsored Products only and carries no status, so
    neither of those can be honestly shown -- but it DOES carry the campaign and
    ad group names, which is the cut that answers "which campaign is burning the
    money".

    Same % of spend against % of profit as by_match_type, for the same reason:
    a campaign taking 40% of the spend and returning 12% of the profit is
    visible without arithmetic.
    """
    agg = {}
    for r in rows or []:
        k = str(r.get("campaign") or "").strip() or "(no campaign named)"
        e = agg.setdefault(k, {"campaign": k, "impressions": 0, "clicks": 0,
                               "orders": 0, "spend": 0.0, "sales": 0.0,
                               "ad_groups": set(), "terms": set(),
                               "match_types": set()})
        e["impressions"] += _i(r.get("impressions"))
        e["clicks"] += _i(r.get("clicks"))
        e["orders"] += _i(r.get("orders"))
        e["spend"] += _f(r.get("spend"))
        e["sales"] += _f(r.get("sales"))
        for f, s in (("ad_group", "ad_groups"), ("search_term", "terms"),
                     ("match_type", "match_types")):
            v = str(r.get(f) or "").strip()
            if v:
                e[s].add(v)

    tot_spend = sum(e["spend"] for e in agg.values())
    tot_profit = sum(e["sales"] - e["spend"] for e in agg.values())
    out = []
    for e in agg.values():
        e["ad_groups"] = sorted(e["ad_groups"])
        e["match_types"] = sorted(e["match_types"])
        e["terms"] = len(e["terms"])
        e["spend"] = round(e["spend"], 2)
        e["sales"] = round(e["sales"], 2)
        e["profit"] = round(e["sales"] - e["spend"], 2)
        e["acos"] = rate(e["spend"], e["sales"])
        e["roas"] = rate(e["sales"], e["spend"], pct=False)
        e["ctr"] = rate(e["clicks"], e["impressions"])
        e["cvr"] = rate(e["orders"], e["clicks"])
        e["cpc"] = rate(e["spend"], e["clicks"], pct=False)
        e["cpa"] = rate(e["spend"], e["orders"], pct=False)
        e["pct_spend"] = rate(e["spend"], tot_spend)
        e["pct_profit"] = (rate(e["profit"], tot_profit)
                           if tot_profit > 0 else None)
        out.append(e)
    out.sort(key=lambda x: -x["spend"])
    return out


def compare(now, before):
    """Period-over-period change on each headline figure. Orbit shows one.

    {metric: {now, before, change_pct, direction}}. `direction` is "better" or
    "worse" rather than up/down, because for ACOS and wasted spend DOWN is the
    good direction and an arrow alone would read backwards on half the row.

    None when there is nothing to compare against -- one report is one window,
    and inventing a baseline would be worse than showing none.
    """
    if not now or not before:
        return None
    # For these, LOWER is better.
    lower_better = {"acos", "tacos", "cpc", "cpa", "wasted_spend", "spend"}
    out = {}
    for k in ("spend", "sales", "acos", "roas", "ctr", "cvr", "cpc", "cpa",
              "wasted_spend", "orders", "clicks"):
        a, b = now.get(k), before.get(k)
        if a is None or b is None or not b:
            continue
        chg = round((float(a) - float(b)) / abs(float(b)) * 100.0, 1)
        better = (chg < 0) if k in lower_better else (chg > 0)
        out[k] = {"now": a, "before": b, "change_pct": chg,
                  "direction": ("better" if chg and better
                                else ("worse" if chg else "same"))}
    return out or None


def reports(config_path, workspace_id, marketplace, limit=12):
    """Every stored report, newest first, so two can be compared."""
    from data import db as _db
    try:
        conn = _db.get_db(config_path)
        return [{"report_id": r["report_id"], "date_from": r["a"],
                 "date_to": r["b"], "rows": r["n"], "uploaded_at": r["up"]}
                for r in conn.execute(
                    "SELECT report_id, MIN(date_from) a, MAX(date_to) b, "
                    "       COUNT(*) n, MAX(uploaded_at) up "
                    "FROM ppc_search_terms WHERE workspace_id=? AND "
                    "marketplace=? GROUP BY report_id "
                    "ORDER BY up DESC LIMIT ?",
                    (workspace_id, marketplace, int(limit)))]
    except Exception:
        return []


def to_csv(terms):
    """The terms table as a CSV, for Orbit's Export button.

    Written with the csv module rather than by joining commas: a search term can
    contain one, and the sheet this app already hands out for supplier links was
    broken exactly that way once (see domain/cogs.apply_sheet).
    """
    import csv as _csv
    import io as _io

    cols = ["search_term", "opportunity", "why", "match_types", "campaigns",
            "branded", "impressions", "clicks", "ctr", "cpc", "cpa",
            "spend", "sales", "orders", "acos", "roas", "profit"]
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(cols)
    for t in terms or []:
        row = []
        for c in cols:
            v = t.get(c)
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            elif v is None:
                v = ""            # blank, never 0 -- see rate()
            elif v is True:
                v = "yes"
            elif v is False:
                v = "no"
            row.append(v)
        w.writerow(row)
    # A byte-order mark, so Excel opens it as UTF-8 and a pound sign survives.
    # Written as the escape, never as a literal BOM character: a real one
    # sitting in the middle of a source file is invisible and breaks parsers
    # that only expect one at the start. test_encoding.js refuses them.
    return "\ufeff" + buf.getvalue()


def branded_split(rows, brands):
    """Branded against non-branded, Orbit's most transferable idea.

    None when no brand terms are set -- that is a setup step, not a result, and
    reporting "0% branded" would be a claim nobody made.
    """
    if not brands:
        return None
    buckets = {"branded": [], "non_branded": []}
    for r in rows or []:
        k = ("branded" if is_branded(r.get("search_term"), brands)
             else "non_branded")
        buckets[k].append(r)
    return {k: totals(v) for k, v in buckets.items()}


def report_meta(config_path, workspace_id, marketplace):
    """Which report is loaded, and when it covers. None when there is none."""
    from data import db as _db
    try:
        conn = _db.get_db(config_path)
        r = conn.execute(
            "SELECT report_id, MIN(date_from) a, MAX(date_to) b, "
            "       COUNT(*) n, MAX(uploaded_at) up "
            "FROM ppc_search_terms WHERE workspace_id=? AND marketplace=? "
            "GROUP BY report_id ORDER BY up DESC LIMIT 1",
            (workspace_id, marketplace)).fetchone()
    except Exception:
        return None
    if not r or not r["n"]:
        return None
    return {"report_id": r["report_id"], "date_from": r["a"],
            "date_to": r["b"], "rows": r["n"], "uploaded_at": r["up"]}


def load_rows(config_path, workspace_id, marketplace, report_id=None):
    """The stored search-term rows for the newest report, or a named one."""
    from data import db as _db
    try:
        conn = _db.get_db(config_path)
    except Exception:
        return []
    if not report_id:
        m = report_meta(config_path, workspace_id, marketplace)
        if not m:
            return []
        report_id = m["report_id"]
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM ppc_search_terms WHERE workspace_id=? AND "
            "marketplace=? AND report_id=?",
            (workspace_id, marketplace, report_id))]
    except Exception:
        return []


def store_rows(config_path, workspace_id, marketplace, rows, report_id=None,
               date_from="", date_to=""):
    """Keep an ingested report. Re-uploading the same id REPLACES it.

    Replaces rather than adds, because uploading the same file twice is the
    normal accident and doubling every figure is the worst possible response to
    it. Returns (report_id, rows_kept).
    """
    from data import db as _db

    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rid = report_id or now.replace(" ", "T")
    conn = _db.get_db(config_path)
    conn.execute("DELETE FROM ppc_search_terms WHERE workspace_id=? AND "
                 "marketplace=? AND report_id=?",
                 (workspace_id, marketplace, rid))
    n = 0
    for r in rows or []:
        term = str(r.get("customer_search_term")
                   or r.get("search_term") or "").strip()
        if not term:
            continue
        conn.execute(
            "INSERT INTO ppc_search_terms (workspace_id, marketplace, "
            " report_id, date_from, date_to, search_term, keyword, match_type, "
            " campaign, ad_group, impressions, clicks, spend, sales, orders, "
            " units, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (workspace_id, marketplace, rid, date_from, date_to, term,
             str(r.get("triggering_keyword") or r.get("keyword") or ""),
             str(r.get("match_type") or ""), str(r.get("campaign") or ""),
             str(r.get("ad_group") or ""),
             _i(r.get("impressions")), _i(r.get("clicks")),
             _f(r.get("spend")), _f(r.get("sales")),
             _i(r.get("orders")), _i(r.get("units")), now))
        n += 1
    conn.commit()
    return rid, n


def total_sales_for(config_path, workspace_id, marketplace, start, end):
    """The whole business's sales in the window, for TACOS. None if unknown.

    From order_lines, which is what the Sales screen counts, so TACOS here and
    revenue there cannot disagree (Rule 12).
    """
    from data import db as _db
    try:
        conn = _db.get_db(config_path)
        r = conn.execute(
            "SELECT SUM(revenue + IFNULL(shipping,0)) s FROM order_lines "
            "WHERE workspace_id=? AND marketplace=? "
            "  AND lower(IFNULL(status,'')) NOT IN ('canceled','cancelled') "
            "  AND substr(purchase_date,1,10) >= ? "
            "  AND substr(purchase_date,1,10) <= ?",
            (workspace_id, marketplace, str(start), str(end))).fetchone()
        return None if not r or r["s"] is None else round(float(r["s"]), 2)
    except Exception:
        return None
