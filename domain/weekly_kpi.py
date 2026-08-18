"""domain/weekly_kpi.py -- the weekly KPI pack, computed instead of hand-built.

    "i want to make a system where i upload the reports and i get this data, in
     a format like return intelligence. and also an option where i just need to
     connect an account like nestwell goods and all of this data is extracted
     without the need of reports. i use the campaign manager data as a download
     and business reports by child asin report to generate this sheet"

TWO REPORTS IN, ONE PACK OUT

    BUSINESS REPORT   Seller Central > Reports > Business Reports >
                      "Detail Page Sales and Traffic by Child Item".
                      Gives sessions, units, sales and page views per child ASIN.
                      Also available from SP-API as GET_SALES_AND_TRAFFIC_REPORT
                      at CHILD granularity -- which is why a connected account
                      needs no upload at all.

    CAMPAIGN EXPORT   Campaign Manager > the campaign table > Export.
                      Gives impressions, clicks, spend, purchases and sales per
                      campaign. Only the Advertising API can replace this one,
                      and that is a separate login (see api/amazon_ads.py).

FIVE THINGS THE SPREADSHEET GOT WRONG

This replaces a Google Sheet whose formulas were read on 18 Aug 2026. Every one
of these is why a computed pack beats a hand-frozen one:

  1. THE CURRENT WEEK WAS THE PREVIOUS WEEK. Column C held live formulas over
     the two source tabs; column D onward held frozen numbers. Both showed
     $61,843.59, 4,995 sessions and 1,370 units -- identical to the cent --
     because the freeze happened and the source tabs were never refreshed.

  2. CPA WAS NOT COMPARABLE WEEK TO WEEK. The current column computed
     spend / ad orders = $27.26. The frozen columns held $7.70, which is
     spend / UNITS -- an older formula. A client reading that row saw CPA
     triple. It had not.

  3. NEW-TO-BRAND ORDERS WAS ALWAYS ZERO. `SUM('Child Sales US'!AD:AD)` sums
     column AD of a tab that has SIXTEEN columns. Column AD does not exist, so
     the answer was 0 every week and looked like a real measurement.

  4. THE BRANDED / NON-BRANDED SPLIT WAS ALWAYS ZERO.
     `SUMIF('PPC US'!B:B,"br",...)` tests whether the CAMPAIGN NAME equals the
     literal text "br". Campaign names look like "[Laurence] B0DP2V7GR2 - Co...".
     Nothing ever matched, so BR/NB spend, sales, orders, RoAS and CPA were all
     0.00 in every pack ever sent.

  5. SPEND AND SALES CAME FROM DIFFERENT CURRENCIES. Spend read "Total cost"
     and sales read "Sales (converted)". Identical for a USD account, wrong the
     moment the report is run for a marketplace that converts.

WHAT IS MEASURED AND WHAT IS NOT

DSP spend, giveaway spend, Meta spend and T.RoAS are blank in the source sheet
because Amazon does not report them -- they come from other places entirely.
They are carried as fields somebody types, and anything derived from them says
so. Nothing here invents a number to fill a row (see [[profit-is-measured-not-padded]]).
"""
import datetime as _dt

from domain import report_reader as _rr

# ---------------------------------------------------------------------------
# What each report looks like. By NAME -- never by column letter, which is how
# defects 3 and 5 above happened.
# ---------------------------------------------------------------------------

BUSINESS_COLS = {
    "parent_asin": ("(Parent) ASIN", "Parent ASIN"),
    "child_asin": ("(Child) ASIN", "Child ASIN", "ASIN"),
    "title": ("Title",),
    "sessions": ("Sessions - Total", "Sessions"),
    "sessions_b2b": ("Sessions - Total - B2B",),
    "page_views": ("Page Views - Total", "Page Views"),
    "units": ("Units Ordered",),
    "usp": ("Unit Session Percentage",),
    "sales": ("Ordered Product Sales",),
    "order_items": ("Total Order Items",),
}

CAMPAIGN_COLS = {
    "state": ("State",),
    "campaign": ("Campaign name", "Campaign Name"),
    "status": ("Status",),
    "type": ("Type",),
    "targeting": ("Targeting",),
    "impressions": ("Impressions",),
    "clicks": ("Clicks",),
    # "Total cost" and "Total cost (converted)" are both present. Sales are
    # taken converted, so spend is too -- defect 5.
    "spend": ("Total cost (converted)", "Total cost", "Spend"),
    "orders": ("Purchases", "Orders"),
    "sales": ("Sales (converted)", "Sales"),
    "ntb_orders": ("Purchases (new to brand)",),
    "ntb_sales": ("Sales (new to brand) (converted)", "Sales (new to brand)"),
}

# A report is identified by the columns that could only be in it.
BUSINESS_MARKS = ("sessions", "units", "sales", "child_asin")
CAMPAIGN_MARKS = ("impressions", "clicks", "spend", "campaign")

BUSINESS = "business_child"
CAMPAIGN = "campaign_manager"

# Figures Amazon does not report. Typed, or left blank and said to be blank.
MANUAL_FIELDS = ("dsp_spend", "giveaway_spend", "meta_spend")


def detect(headers):
    """Which of the two reports is this? "" when it is neither.

    By columns, not by filename -- the person uploading has no reason to keep
    Amazon's filename, and being told "wrong report" after picking the right
    file is the whole frustration this avoids.
    """
    b = _rr.index(headers, BUSINESS_COLS)
    c = _rr.index(headers, CAMPAIGN_COLS)
    b_hits = sum(1 for k in BUSINESS_MARKS if k in b)
    c_hits = sum(1 for k in CAMPAIGN_MARKS if k in c)
    # The campaign export also has a "Sales" column, so a tie must not fall to
    # the business report. Requiring the distinctive marks and comparing counts
    # keeps them apart.
    if c_hits >= 3 and c_hits >= b_hits:
        return CAMPAIGN
    if b_hits >= 3:
        return BUSINESS
    return ""


def _rows_of(table, cols):
    idx = _rr.index(table.get("headers"), cols)
    out = []
    for row in table.get("rows") or []:
        rec = {}
        for f in cols:
            rec[f] = _rr.cell(row, idx, f, "")
        out.append(rec)
    return out, idx


def _currency_of(raw, field):
    """The currency the money column is written in, read off the report."""
    return _rr.currency_of([r.get(field) for r in raw[:40]])


def parse_business(table):
    """The Business Report -> one record per child ASIN."""
    raw, idx = _rows_of(table, BUSINESS_COLS)
    out = []
    for r in raw:
        child = str(r.get("child_asin") or "").strip()
        if not child:
            continue
        out.append({
            "parent_asin": str(r.get("parent_asin") or "").strip(),
            "child_asin": child,
            "title": str(r.get("title") or "").strip(),
            "sessions": _rr.num(r.get("sessions"), 0) or 0,
            "page_views": _rr.num(r.get("page_views"), 0) or 0,
            "units": _rr.num(r.get("units"), 0) or 0,
            "sales": _rr.num(r.get("sales"), 0) or 0,
            "order_items": _rr.num(r.get("order_items"), 0) or 0,
        })
    return {"rows": out, "found_columns": sorted(idx.keys()),
            "currency": _currency_of(raw, "sales"),
            "missing_columns": sorted(set(BUSINESS_COLS) - set(idx))}


def parse_campaigns(table):
    """The Campaign Manager export -> one record per campaign."""
    raw, idx = _rows_of(table, CAMPAIGN_COLS)
    out = []
    for r in raw:
        name = str(r.get("campaign") or "").strip()
        if not name:
            continue
        out.append({
            "campaign": name,
            "state": str(r.get("state") or "").strip(),
            "status": str(r.get("status") or "").strip(),
            "type": str(r.get("type") or "").strip().upper(),
            "targeting": str(r.get("targeting") or "").strip(),
            "impressions": _rr.num(r.get("impressions"), 0) or 0,
            "clicks": _rr.num(r.get("clicks"), 0) or 0,
            "spend": _rr.num(r.get("spend"), 0) or 0,
            "orders": _rr.num(r.get("orders"), 0) or 0,
            "sales": _rr.num(r.get("sales"), 0) or 0,
            "ntb_orders": _rr.num(r.get("ntb_orders"), 0) or 0,
            "ntb_sales": _rr.num(r.get("ntb_sales"), 0) or 0,
        })
    return {"rows": out, "found_columns": sorted(idx.keys()),
            "currency": _currency_of(raw, "spend"),
            "missing_columns": sorted(set(CAMPAIGN_COLS) - set(idx))}


# ---------------------------------------------------------------------------
# Branded vs non-branded
# ---------------------------------------------------------------------------

def is_branded(campaign_name, brand_terms):
    """Does this campaign target your own brand?

    The sheet tried to do this with SUMIF(campaign name = "br"), which never
    matched anything (defect 4). A campaign is branded when its NAME CONTAINS
    one of your brand terms, which is how everybody actually names them --
    "SB - Exact - branded", "[Laurence] SBV Branded - C".

    The terms come from ppc_brand_terms, the same list the PPC screen's branded
    split already uses, so the two cannot disagree (Rule 12).
    """
    n = str(campaign_name or "").lower()
    for t in (brand_terms or []):
        t = str(t or "").strip().lower()
        if t and t in n:
            return True
    return False


def _rate(top, bottom):
    """top/bottom, or None. None is not zero and never renders as 0."""
    try:
        top = float(top)
        bottom = float(bottom)
    except (TypeError, ValueError):
        return None
    return (top / bottom) if bottom else None


def kpis(business, campaigns, brand_terms=None, manual=None):
    """Every headline figure, from the two parsed reports.

    `manual` carries the figures Amazon does not report -- DSP, giveaway and
    Meta spend. Absent means absent: Total Spend then says what it could see.
    """
    b = (business or {}).get("rows") or []
    c = (campaigns or {}).get("rows") or []
    manual = manual or {}

    sales = sum(x["sales"] for x in b)
    sessions = sum(x["sessions"] for x in b)
    units = sum(x["units"] for x in b)
    page_views = sum(x["page_views"] for x in b)

    ad_sales = sum(x["sales"] for x in c)
    ad_spend = sum(x["spend"] for x in c)
    impressions = sum(x["impressions"] for x in c)
    clicks = sum(x["clicks"] for x in c)
    ad_orders = sum(x["orders"] for x in c)
    ntb_orders = sum(x["ntb_orders"] for x in c)
    ntb_sales = sum(x["ntb_sales"] for x in c)

    br = [x for x in c if is_branded(x["campaign"], brand_terms)]
    nb = [x for x in c if not is_branded(x["campaign"], brand_terms)]

    def tot(rows, key):
        return sum(x[key] for x in rows)

    dsp = _rr.num(manual.get("dsp_spend"))
    giveaway = _rr.num(manual.get("giveaway_spend"))
    meta = _rr.num(manual.get("meta_spend"))
    extra = sum(x for x in (dsp, giveaway, meta) if x is not None)
    total_spend = ad_spend + extra

    out = {
        # ---- the store ----
        "total_sales": round(sales, 2),
        "sessions": int(sessions),
        "page_views": int(page_views),
        "units": int(units),
        # Units per session, from the two totals -- NOT the average of the
        # per-ASIN percentages, which weights a product with 5 sessions the
        # same as one with 1,791.
        "unit_session_pct": _rate(units, sessions),

        # ---- advertising ----
        "ad_sales": round(ad_sales, 2),
        "ad_spend": round(ad_spend, 2),
        "ad_impressions": int(impressions),
        "ad_clicks": int(clicks),
        "ad_orders": int(ad_orders),
        "ctr": _rate(clicks, impressions),
        "ads_cvr": _rate(ad_orders, clicks),
        "roas": _rate(ad_sales, ad_spend),
        "acos": _rate(ad_spend, ad_sales),
        # CPA is spend per AD ORDER. Stated because the sheet's history has it
        # as spend per unit, which is a different and much smaller number.
        "cpa": _rate(ad_spend, ad_orders),
        "cpc": _rate(ad_spend, clicks),

        # ---- new to brand: from the CAMPAIGN export, which really has it ----
        "ntb_orders": int(ntb_orders),
        "ntb_sales": round(ntb_sales, 2),

        # ---- branded vs not ----
        "br_spend": round(tot(br, "spend"), 2),
        "br_sales": round(tot(br, "sales"), 2),
        "br_orders": int(tot(br, "orders")),
        "br_roas": _rate(tot(br, "sales"), tot(br, "spend")),
        "br_campaigns": len(br),
        "nb_spend": round(tot(nb, "spend"), 2),
        "nb_sales": round(tot(nb, "sales"), 2),
        "nb_orders": int(tot(nb, "orders")),
        "nb_roas": _rate(tot(nb, "sales"), tot(nb, "spend")),
        "nb_cpa": _rate(tot(nb, "spend"), tot(nb, "orders")),
        "nb_campaigns": len(nb),

        # ---- everything together ----
        "dsp_spend": dsp,
        "giveaway_spend": giveaway,
        "meta_spend": meta,
        "total_spend": round(total_spend, 2),
        "tacos": _rate(total_spend, sales),
        "troas": _rate(sales, total_spend),

        # ---- what this is built on, so a figure can be trusted ----
        "products_counted": len(b),
        "campaigns_counted": len(c),
        # Said out loud: with no brand term set, EVERY campaign counts as
        # non-branded, and that is a setting rather than a finding.
        "brand_terms_used": list(brand_terms or []),
    }
    return out


def products(business, days=7):
    """The per-product blocks: units, sessions, conversion, units a day.

    Sorted by units, because the question the block answers is "what is
    selling". `days` divides units for the per-day figure -- 7 for a week, and
    passed in rather than hardcoded so a part week is not quietly reported as a
    full one.
    """
    rows = list((business or {}).get("rows") or [])
    rows.sort(key=lambda r: (-r["units"], -r["sessions"], r["child_asin"]))
    days = max(1, int(days or 7))
    out = []
    for r in rows:
        out.append({
            "child_asin": r["child_asin"],
            "parent_asin": r["parent_asin"],
            "title": r["title"],
            "units": int(r["units"]),
            "sessions": int(r["sessions"]),
            "page_views": int(r["page_views"]),
            "sales": round(r["sales"], 2),
            "conversion": _rate(r["units"], r["sessions"]),
            "units_per_day": round(r["units"] / days, 1),
        })
    return out


# ---------------------------------------------------------------------------
# Weeks
# ---------------------------------------------------------------------------

def week_bounds(any_day=None, week_starts="SUN"):
    """(start, end) of the week containing `any_day`, as YYYY-MM-DD.

    The source sheet runs Sunday to Saturday -- "August 9, 2026" to
    "August 15, 2026" -- so that is the default. It is a parameter because a
    week that silently means something different from the client's week is a
    reporting fault nobody spots until a total disagrees.
    """
    d = any_day or _dt.date.today()
    if isinstance(d, _dt.datetime):
        d = d.date()
    # Monday=0 .. Sunday=6
    offset = (d.weekday() + 1) % 7 if str(week_starts).upper() == "SUN" \
        else d.weekday()
    start = d - _dt.timedelta(days=offset)
    return start.isoformat(), (start + _dt.timedelta(days=6)).isoformat()


def build(business_table, campaign_table, brand_terms=None, manual=None,
          week_start=None, week_end=None, days=7):
    """Everything the screen needs, from two already-read tables."""
    b = parse_business(business_table) if business_table else {"rows": []}
    c = parse_campaigns(campaign_table) if campaign_table else {"rows": []}

    # THE CURRENCY COMES FROM THE REPORT, not from whichever account happens to
    # be open. An agency runs a client's US pack with a UK workspace selected
    # and every dollar is drawn with a pound sign -- the number right and the
    # label a lie. Amazon writes the symbol into the cell, so the file knows.
    # "" means the file did not say, and the screen falls back to the account.
    ccy = b.get("currency") or c.get("currency") or ""
    # When the two halves disagree the pack is being built from two different
    # marketplaces' reports, which is a mistake worth naming rather than
    # averaging away.
    mixed = bool(b.get("currency") and c.get("currency")
                 and b["currency"] != c["currency"])

    return {
        "week_start": week_start,
        "week_end": week_end,
        "days": days,
        "currency": ccy,
        "currency_mixed": mixed,
        "business_currency": b.get("currency") or "",
        "campaign_currency": c.get("currency") or "",
        "kpis": kpis(b, c, brand_terms, manual),
        "products": products(b, days),
        "campaigns": sorted(c.get("rows") or [],
                            key=lambda x: -x["spend"]),
        # WHICH HALVES ARE PRESENT. A pack built from one report is not wrong,
        # but every advertising figure in it is missing rather than zero, and
        # the screen has to be able to say which.
        "has_business": bool(b.get("rows")),
        "has_campaigns": bool(c.get("rows")),
        "missing_business_columns": b.get("missing_columns") or [],
        "missing_campaign_columns": c.get("missing_columns") or [],
    }


# ---------------------------------------------------------------------------
# Storage -- a week is written once and never recomputed
# ---------------------------------------------------------------------------

def store(config_path, workspace_id, marketplace, pack, source="upload"):
    """Freeze one week. Re-storing the same week CORRECTS it, never duplicates.

    The finished pack is stored as JSON rather than recomputed on read. That is
    deliberate: it is what stops a later improvement to the arithmetic silently
    rewriting what was already reported to a client. The sheet this replaces had
    exactly that fault -- CPA was corrected from spend/units to spend/orders at
    some point, and the two sat in the same row looking comparable.
    """
    import json as _json

    from data import db as _db
    conn = _db.get_db(config_path)
    conn.execute(
        "INSERT OR REPLACE INTO weekly_kpi (workspace_id, marketplace, "
        "week_start, week_end, payload, source, built_at) VALUES (?,?,?,?,?,?,?)",
        (workspace_id, str(marketplace or "").upper(),
         pack.get("week_start") or "", pack.get("week_end") or "",
         _json.dumps(pack), source,
         _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    return pack


def weeks(config_path, workspace_id, marketplace, limit=26):
    """Every stored week, newest first. Just the headline of each."""
    import json as _json

    from data import db as _db
    conn = _db.get_db(config_path)
    try:
        rows = conn.execute(
            "SELECT week_start, week_end, payload, source, built_at "
            "FROM weekly_kpi WHERE workspace_id=? AND marketplace=? "
            "ORDER BY week_start DESC LIMIT ?",
            (workspace_id, str(marketplace or "").upper(), int(limit))).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        try:
            pack = _json.loads(r["payload"])
        except Exception:
            continue
        out.append({"week_start": r["week_start"], "week_end": r["week_end"],
                    "source": r["source"], "built_at": r["built_at"],
                    "kpis": pack.get("kpis") or {},
                    "products": pack.get("products") or [],
                    "has_business": pack.get("has_business"),
                    "has_campaigns": pack.get("has_campaigns"),
                    # The currency the REPORT was written in. Dropped here once,
                    # which put a pound sign on dollar figures even though the
                    # stored pack knew better -- a field list that has to be
                    # kept in step with the pack is one that will fall out of it.
                    "currency": pack.get("currency") or "",
                    "currency_mixed": pack.get("currency_mixed") or False,
                    "business_currency": pack.get("business_currency") or "",
                    "campaign_currency": pack.get("campaign_currency") or ""})
    return out


def compare(this_week, last_week):
    """Movement on every headline figure, week over week.

    Returns {kpi: {"from", "to", "delta", "pct", "better"}}. `better` is the
    DIRECTION OF GOOD, not the direction of the arrow -- for ACOS, CPC, CPA and
    TACOS down is good, and an arrow alone reads backwards on half the row. Same
    rule the PPC screen already follows.
    """
    # Lower is better for these. Everything else: higher is better.
    DOWN_IS_GOOD = {"acos", "cpc", "cpa", "nb_cpa", "tacos", "ad_spend",
                    "total_spend"}
    a = (last_week or {}).get("kpis") or (last_week or {})
    b = (this_week or {}).get("kpis") or (this_week or {})
    out = {}
    for k, now in b.items():
        was = a.get(k)
        if not isinstance(now, (int, float)) or not isinstance(was, (int, float)):
            continue
        if isinstance(now, bool) or isinstance(was, bool):
            continue
        delta = now - was
        pct = (delta / abs(was)) if was else None
        if delta == 0:
            better = None                     # no movement is neither
        elif k in DOWN_IS_GOOD:
            better = delta < 0
        else:
            better = delta > 0
        out[k] = {"from": was, "to": now, "delta": delta, "pct": pct,
                  "better": better}
    return out
