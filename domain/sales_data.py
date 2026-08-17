"""domain/sales_data.py -- the Sales dashboard's numbers.

WHERE THEY COME FROM
One SP-API report: GET_SALES_AND_TRAFFIC_REPORT, asked for with dateGranularity
DAY and asinGranularity CHILD. It returns sales AND traffic together -- units,
orders, revenue, sessions, page views, buy box, conversion -- per day and per
ASIN, in a single JSON document. Most of the dashboard is that one call.

WHAT IS NOT HERE
Ad spend, ACOS and ROAS. Those are the Amazon ADVERTISING API, which is a
different API with its own authorisation, and this app is not connected to it.
ads_daily exists and is read by the same code path; it is simply empty until
either a Sponsored Products report is uploaded or the API is connected. The
dashboard says "not connected" rather than showing a zero, because a zero is a
claim that there was no ad spend.

AMAZON'S LAG IS REAL
Sales for today never exist, and yesterday is often incomplete. Every reply
carries the range that genuinely has data, so the dashboard can draw "no data
yet" instead of a column of zeros that reads as "you sold nothing".
"""
import datetime as _dt
import json
import time

from data import db as _db

REPORT_TYPE = "GET_SALES_AND_TRAFFIC_REPORT"

# The stored columns, and how to read them out of Amazon's JSON. Kept as one
# table rather than scattered through the parser so adding a metric is one line
# and cannot be half-added.
#   (column, salesByAsin/salesByDate key path, traffic key path)
_SALES_KEYS = [
    ("units",             ("unitsOrdered",)),
    ("units_b2b",         ("unitsOrderedB2B",)),
    ("order_items",       ("totalOrderItems",)),
    ("ordered_sales",     ("orderedProductSales", "amount")),
    ("ordered_sales_b2b", ("orderedProductSalesB2B", "amount")),
    ("avg_selling_price", ("averageSellingPrice", "amount")),
]
_TRAFFIC_KEYS = [
    ("sessions",         ("sessions",)),
    ("sessions_mobile",  ("mobileAppSessions",)),
    ("sessions_browser", ("browserSessions",)),
    ("page_views",       ("pageViews",)),
    ("buy_box_pct",      ("buyBoxPercentage",)),
    ("unit_session_pct", ("unitSessionPercentage",)),
]


def _dig(d, path):
    cur = d or {}
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def parse_report(doc):
    """Amazon's JSON -> rows ready for sales_daily.

    Handles both blocks the report contains: salesAndTrafficByDate (the account
    total for each day) and salesAndTrafficByAsin (the per-ASIN breakdown). The
    ASIN block has no date of its own when the report covers a range, so a
    single-day request is made per day -- see fetch_range.
    """
    rows = []
    if not isinstance(doc, dict):
        return rows

    currency = ""
    for block in (doc.get("salesAndTrafficByDate") or []):
        s = block.get("salesByDate") or {}
        t = block.get("trafficByDate") or {}
        currency = currency or (_dig(s, ("orderedProductSales", "currencyCode")) or "")
        row = {"date": str(block.get("date") or "")[:10], "asin": "*",
               "currency": currency}
        for col, path in _SALES_KEYS:
            row[col] = _dig(s, path)
        for col, path in _TRAFFIC_KEYS:
            row[col] = _dig(t, path)
        # Amazon reports order ITEMS by date; distinct orders are not in this
        # report. Recording items and naming the column honestly beats inventing
        # an "orders" number the report does not contain.
        row["orders"] = row.get("order_items")
        if row["date"]:
            rows.append(row)

    for block in (doc.get("salesAndTrafficByAsin") or []):
        s = block.get("salesByAsin") or {}
        t = block.get("trafficByAsin") or {}
        # The CHILD asin is the key, not the parent. With asinGranularity CHILD
        # every block carries BOTH, and preferring the parent files every
        # variation of a product under one key -- which the unique index then
        # collapses, so a parent with five children keeps only the last one's
        # numbers and loses the other four silently. The parent is kept in its
        # own column so variations can still be grouped.
        row = {"date": str(block.get("date") or doc.get("_date") or "")[:10],
               "asin": str(block.get("childAsin") or block.get("parentAsin") or "") or "?",
               "parent_asin": str(block.get("parentAsin") or ""),
               "currency": currency}
        for col, path in _SALES_KEYS:
            row[col] = _dig(s, path)
        for col, path in _TRAFFIC_KEYS:
            row[col] = _dig(t, path)
        row["orders"] = row.get("order_items")
        if row["date"] and row["asin"] != "?":
            rows.append(row)
    return rows


_COLS = ["parent_asin", "units", "units_b2b", "orders", "order_items",
         "ordered_sales", "ordered_sales_b2b", "sessions", "sessions_mobile",
         "sessions_browser", "page_views", "buy_box_pct", "unit_session_pct",
         "avg_selling_price", "currency"]


def store(config_path, workspace_id, marketplace, rows):
    """Upsert. Returns how many rows were written.

    Re-fetching a day REPLACES it: Amazon revises recent days as returns and
    cancellations settle, and keeping the first answer would freeze a number that
    Amazon itself no longer agrees with.
    """
    if not rows:
        return 0
    conn = _db.get_db(config_path)
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    # DAYS THE ORDERS API HAS ALREADY ANSWERED FOR are not overwritten with the
    # report's version of orders / units / sales. The report is a day or more
    # behind and it is the SAME measurement, so its answer is not newer, only
    # later -- and on nestwell_goods it was three days of nothing against 173.43
    # of real sales. Everything the report uniquely has (sessions, page views,
    # buy box, conversion) is still written, for every day, unchanged.
    #
    # See domain/live_reconcile.py, and Orbit's own rule: "Orders API wins for
    # top-line because it's realtime order-date basis."
    _LIVE_OWNED = ("orders", "units", "ordered_sales")
    owned = set()
    try:
        dates = [r["date"] for r in rows if r.get("date")]
        if dates:
            from domain import live_reconcile as _lr
            owned = _lr.owned_days(config_path, workspace_id, marketplace,
                                   min(dates), max(dates))
    except Exception:
        owned = set()

    n = 0
    for r in rows:
        # Only the ACCOUNT-WIDE row is ever claimed by the live feed; per-ASIN
        # rows come from the report alone, so they are always written in full.
        live_owns = (str(r.get("asin", "*")) == "*" and r.get("date") in owned)
        cols = ([c for c in _COLS if c not in _LIVE_OWNED] if live_owns else _COLS)
        vals = [r.get(c) for c in cols]
        conn.execute(
            "INSERT INTO sales_daily (workspace_id, marketplace, date, asin, %s, fetched_at) "
            "VALUES (?,?,?,?,%s,?) "
            "ON CONFLICT(workspace_id, marketplace, date, asin) DO UPDATE SET %s, fetched_at=excluded.fetched_at"
            % (", ".join(cols), ",".join("?" * len(cols)),
               ", ".join("%s=excluded.%s" % (c, c) for c in cols)),
            [workspace_id, marketplace, r["date"], r.get("asin", "*")] + vals + [now])
        n += 1
    conn.commit()
    _refresh_availability(conn, workspace_id, marketplace, "sales")
    return n


def _refresh_availability(conn, workspace_id, marketplace, source):
    """What dates we actually have figures for. A ROW IS NOT EVIDENCE.

    This counted every row in the table, and rows get written for days nothing
    is known about. live_reconcile.from_lines() writes one per day across the
    whole window it is given, so a single year-to-date view created a row for
    every day back to January -- all of them empty.

    Availability then said this account had data from 19 May 2025, and the
    screen believed it: asking for 90 days drew ninety columns of zeros instead
    of saying "there is nothing here before 27 July". Reported as "the sales
    report and p&l heatmap do not show data beyond 27th july no matter if i
    select 30 day, 60d or 90d" -- the screen was drawing the empty rows as
    though they were real quiet days.

    So the first date is the first day that carries an actual figure -- a sale,
    an order, a unit, or a visitor. A genuinely quiet day inside a trading
    period is still counted, because the days around it carry something; what
    is excluded is a run of empty placeholder rows before the account had
    anything at all.
    """
    table = "sales_daily" if source == "sales" else "ads_daily"
    # Which columns mean "something happened", per table.
    cols = (("ordered_sales", "orders", "units", "sessions", "page_views")
            if source == "sales" else
            ("impressions", "clicks", "spend", "ad_orders", "ad_sales"))
    real = " OR ".join("COALESCE(%s,0) <> 0" % c for c in cols)
    r = conn.execute(
        "SELECT MIN(date) a, MAX(date) b, COUNT(DISTINCT date) n FROM %s "
        "WHERE workspace_id=? AND marketplace=? AND (%s)" % (table, real),
        (workspace_id, marketplace)).fetchone()
    # Nothing at all yet is a real answer too -- but then fall back to the rows
    # we do have, so a brand new account with one quiet day still reports the
    # day it was looked at rather than nothing.
    if not (r and r["a"]):
        r = conn.execute(
            "SELECT MIN(date) a, MAX(date) b, 0 AS n FROM %s "
            "WHERE workspace_id=? AND marketplace=?" % table,
            (workspace_id, marketplace)).fetchone()
    conn.execute(
        "INSERT INTO data_availability (workspace_id, marketplace, source, first_date, "
        "last_date, days, fetched_at) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(workspace_id, marketplace, source) DO UPDATE SET "
        "first_date=excluded.first_date, last_date=excluded.last_date, "
        "days=excluded.days, fetched_at=excluded.fetched_at",
        (workspace_id, marketplace, source, r["a"], r["b"], r["n"] or 0,
         time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()


def availability(config_path, workspace_id, marketplace):
    """What dates genuinely have data, asked BEFORE anything requests data."""
    conn = _db.get_db(config_path)
    out = {}
    for src in ("sales", "ads"):
        r = conn.execute(
            "SELECT first_date, last_date, days, fetched_at FROM data_availability "
            "WHERE workspace_id=? AND marketplace=? AND source=?",
            (workspace_id, marketplace, src)).fetchone()
        out[src] = (dict(r) if r else
                    {"first_date": None, "last_date": None, "days": 0, "fetched_at": None})
    out["ads"]["connected"] = bool(out["ads"]["days"])
    out["ads"]["note"] = ("" if out["ads"]["days"] else
                          "Ad data needs the Amazon Advertising API, which is not "
                          "connected. Upload a Sponsored Products report, or connect "
                          "the API, and these fill in.")
    return out


_FIN_COLS = ("referral_fees", "fba_fees", "other_fees", "refunds", "refund_units",
             "refund_fees_returned", "reimbursements", "promos", "principal",
             "tax", "refund_tax", "units_shipped", "cogs", "cogs_units")


# ---- VAT -------------------------------------------------------------------
# Two arrangements, and telling them apart decides whether every profit figure in
# the app is right or a fifth too high.
#
#   Amazon sent a Tax line ALONGSIDE principal
#       -> principal is the EX-VAT price. Revenue is already net; the tax was
#          collected on top and is owed onward. Nothing to subtract.
#   No tax line, and the account is VAT-registered
#       -> principal is what the buyer paid, VAT inside it. It must come out:
#          vat = gross * rate / (1 + rate).  NOT gross * rate, which is the
#          classic error and understates the VAT by a fifth of itself.
#   No tax line, no rate configured
#       -> we do not know. The figure is shown, and the screen says it may be
#          overstated, because silence here reads as "no VAT applies".

VAT_FROM_AMAZON = "amazon"      # Amazon itemised it; revenue already net
VAT_DERIVED     = "derived"     # we took it out of a gross principal
VAT_UNKNOWN     = "unknown"     # no tax line and no rate set
VAT_NONE        = "none"        # not VAT-registered; nothing to take out


def vat_for(row, vat_rate=None):
    """(vat, net_revenue, basis) for one row. Never invents a number."""
    gross = float((row or {}).get("principal") or 0.0)
    tax = (row or {}).get("tax")
    # `is not None`, NOT truthiness. A stored 0.00 means "we read Amazon's tax
    # lines and they came to zero"; NULL means "this row predates us capturing
    # tax at all". Treating a legitimate zero as absent falls through to the
    # derived branch and subtracts VAT from a principal that is ALREADY net of
    # it -- deducting it twice, on exactly the zero-rated days.
    #
    # Measured on the live UK account 14 Aug 2026 (probe_finance.py): Amazon
    # sends Tax as its own ChargeType, 80.47 against 402.39 of Principal, which
    # is 20.0% ON TOP. So Principal is the VAT-EXCLUSIVE price and there is
    # nothing to take out of it.
    if tax is not None:
        return round(float(tax), 2), round(gross, 2), VAT_FROM_AMAZON
    if vat_rate in (None, "", 0, 0.0):
        # A rate of 0 is a real answer -- not registered -- but None is not.
        return ((0.0, round(gross, 2), VAT_NONE) if vat_rate == 0
                else (None, round(gross, 2), VAT_UNKNOWN))
    try:
        r = float(vat_rate)
    except (TypeError, ValueError):
        return None, round(gross, 2), VAT_UNKNOWN
    if r <= 0 or r >= 1:
        return None, round(gross, 2), VAT_UNKNOWN
    vat = round(gross * r / (1.0 + r), 2)
    return vat, round(gross - vat, 2), VAT_DERIVED


def net_proceeds_for(row, vat_rate=None):
    """What was actually kept out of one bucket of money movements.

        net proceeds = principal
                     - VAT                (collected, never earned)
                     - Amazon's fees
                     - refunds paid back to buyers
                     - promotions you funded
                     + the fee Amazon returns on a refund
                     + reimbursements for Amazon's own mistakes

    Returns {vat, vat_basis, net_revenue, total_fees, net_proceeds}. net_proceeds
    is None when there is nothing to work from -- no fees AND no refunds means
    this bucket has no money movements in it, which is not the same as zero.

    WHY THIS IS A FUNCTION AND NOT SEVEN LINES WRITTEN WHEREVER NEEDED
    It was written twice: here, inside the daily loop, and again in
    domain/contribution.py for the Finance screen. The two copies did not agree,
    and could not be seen side by side to notice:

        this one          - fees - refunds - PROMOS + REFUND FEES BACK + reimb
        contribution.py   - fees - refunds                            + reimb

    So the Finance screen counted a funded discount as if you had kept it, and
    ignored the fee Amazon gives back on a refund. On any product with a coupon
    the two screens reported different money for the same days, and the Finance
    one was the flattering one. Measured on nestwell_goods, which runs coupons.

    CLAUDE.md Rule 12: one concept, one implementation. Everything that wants
    "what did we keep" calls this. Do not inline it again -- if a screen needs a
    variation, add a named argument here so the difference is visible.
    """
    row = row or {}

    def _n(key):
        try:
            return float(row.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    fees = [row.get(k) for k in ("referral_fees", "fba_fees", "other_fees")]
    fees = [float(x) for x in fees if x is not None]
    total_fees = round(sum(fees), 2) if fees else None

    vat, net_revenue, basis = vat_for(row, vat_rate)
    out = {"vat": vat, "vat_basis": basis, "net_revenue": net_revenue,
           "total_fees": total_fees, "net_proceeds": None}

    # NOTHING TO WORK FROM is not the same as zero. A day Amazon has sent no
    # events for has no fees and no refunds, and reporting 0.00 kept on it would
    # draw a real figure for a day that has not landed.
    if total_fees is None and row.get("refunds") is None:
        out["vat"] = None
        out["vat_basis"] = ""
        out["net_revenue"] = None
        return out

    # SIGNS. Every one of these columns is stored POSITIVE -- see the note at the
    # top of domain/finance_data.py. Amazon sends fees and refunds negative and
    # they are abs()'d on the way in, so the arithmetic here is all explicit
    # subtraction. A column that is sometimes signed is how a profit figure comes
    # out backwards.
    out["net_proceeds"] = round(
        net_revenue
        - float(total_fees or 0.0)
        - _n("refunds")
        - _n("promos")
        + _n("refund_fees_returned")
        + _n("reimbursements"), 2)
    return out


def vat_rate_for(config, workspace_id):
    """The account's VAT rate, or None if nobody has said.

    Per ACCOUNT, not per marketplace: VAT registration is a fact about the
    business, and two accounts selling on the same marketplace can differ.
    """
    cfg = config() if callable(config) else (config or {})
    for a in (cfg.get("accounts") or []):
        if str(a.get("id")) == str(workspace_id):
            v = a.get("vat_rate", None)
            return None if v in (None, "") else float(v)
    return None


def series(config_path, workspace_id, marketplace, start, end, asin=None,
           vat_rate=None, basis="money", meta=None):
    """Daily rows for a range, sales joined with ads and finance.

    The dates come from the UNION of the three sources, not from sales alone. A
    refund posts on the day the money went back, which can easily be a day with
    no sales of its own -- keying off sales would drop that refund entirely and
    quietly overstate what you kept.

    `basis` decides WHICH DAY Amazon's money is reported on:

      "money"  the day it moved. Answers "what landed in my account this week",
               which is a cash question and a real one.
      "order"  the day the order that caused it was PLACED. Answers "what did
               the orders I took this week earn", which is what a P&L is for.

    The difference is not small. Measured on jack_uk, Amazon settles ten to
    twelve days after the order -- so on the money basis a week's sales and that
    week's fees describe entirely different trades, and no day carries both.
    That is what made the P&L grid impossible to read across.

    Only the settled columns move. Sales, units, orders and traffic are dated by
    the order already, on either basis, and are untouched.

    `meta`, if a dict is passed in, is filled with what actually happened:
    meta["basis"] is the basis USED, which is not always the one asked for --
    a product filter or a re-dating failure falls back to money. The caller
    that echoes the request back to the screen has to echo this, not the
    request, or the screen labels money-basis figures as order-basis ones.
    """
    conn = _db.get_db(config_path)
    key = asin or "*"
    sales = {r["date"]: dict(r) for r in conn.execute(
        "SELECT * FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin=?",
        (workspace_id, marketplace, start, end, key)).fetchall()}
    ads = {r["date"]: dict(r) for r in conn.execute(
        "SELECT * FROM ads_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin=?",
        (workspace_id, marketplace, start, end, key)).fetchall()}
    from domain import finance_data as _fd
    fin = _fd.series(config_path, workspace_id, marketplace, start, end, key)

    # ON THE ORDER BASIS the settled money is re-dated to the day each order was
    # placed, using the order id Amazon puts on every shipment and refund event.
    # Only for the account-wide series: fees are known per ORDER, and splitting
    # one order's fee across the ASINs in it is a different job from this one.
    fin_note = ""
    if basis == "order" and key != "*":
        # A PRODUCT FILTER CANNOT BE RE-DATED, so say so rather than pretend.
        # Amazon charges fees per ORDER, and an order can hold several products;
        # splitting one fee across them is a different job from this one. The
        # figures below are therefore the money basis, and calling them anything
        # else is how a screen comes to be labelled with a calendar it is not on.
        basis = "money"
    if basis == "order" and key == "*":
        try:
            from domain import order_finance as _of
            # BOTH SIDES FROM THE SAME ROWS. The money side below is built from
            # order_lines, which reaches back ninety days; the sales side was
            # written by a fourteen-day pass, so on a longer window the money
            # covered more days than the sales did -- 2861.33 charged against
            # 1241.13 of sales on selvora_limited. Rewriting the sales side from
            # the same rows first makes that impossible rather than unlikely.
            from domain import live_reconcile as _lr
            try:
                _lr.from_lines(config_path, workspace_id, marketplace, start, end)
                sales = {r["date"]: dict(r) for r in conn.execute(
                    "SELECT * FROM sales_daily WHERE workspace_id=? AND marketplace=? "
                    "AND date>=? AND date<=? AND asin=?",
                    (workspace_id, marketplace, start, end, key)).fetchall()}
            except Exception:
                pass
            # EVERY ORDER IN THE WINDOW, settled or not. Amazon settles about
            # eleven days after the order, so a day's sales covered nine units
            # while its fees covered six -- and profit came out as six orders'
            # proceeds minus nine units of stock, a loss on a day that made
            # money. Unsettled orders get their fee estimated at the rate this
            # account actually pays, and each day says how much of it is
            # estimated. See order_finance.complete_by_order_date.
            from domain import order_profit as _op
            _rate, _rbasis, _rdetail = _op.fee_rate(config_path, workspace_id,
                                                    marketplace, end)
            redated = _of.complete_by_order_date(config_path, workspace_id,
                                                 marketplace, start, end,
                                                 fee_rate=_rate, vat_rate=vat_rate)
            # RE-DATING THAT LOSES THE FEES IS NOT AN ANSWER, IT IS A HOLE.
            #
            # Every fee is re-dated by looking its order up in order_lines. An
            # order the app has never fetched cannot be dated, so its fee is
            # simply not carried -- and where the history does not reach at all,
            # NOTHING is carried. The screen then shows a period's sales with no
            # fees against them, and profit comes out as revenue: a P&L that
            # flatters by exactly the amount Amazon took.
            #
            # A hole is worse than the wrong calendar, because the wrong
            # calendar is at least labelled. So when the money basis had fees
            # and the re-dating produced none, this keeps the money figures and
            # says so, instead of publishing a period with no costs in it.
            if fin and not redated:
                basis = "money"
                fin_note = ("Amazon's fees for this period could not be dated "
                            "to the orders that caused them -- those orders are "
                            "older than this app's order history -- so the fees "
                            "below are on the day the money moved.")
            else:
                fin = redated
            miss = _of.unattributed(config_path, workspace_id, marketplace)
            # Added to whatever the fallback above may have said, not over it --
            # they are two different gaps and a reader needs to know about both.
            if miss.get("orders") and basis == "order":
                fin_note = (fin_note + " " if fin_note else "") + (
                    "%d settled order(s) worth %.2f in fees are older "
                    "than this app's order history, so they cannot be "
                    "dated to when they were placed and are not in these "
                    "figures." % (miss["orders"], miss["fees"]))
        except Exception:
            basis = "money"          # never lose the figures over a re-dating

    # EVERY DAY IN THE WINDOW YOU ASKED FOR, whether anything happened or not.
    #
    # "i still dont see the graph accurately as of 90 days. i selected 90 days
    # and it shows me the first date of 9th july."
    #
    # Exactly right, and it was a side-effect of clearing the invented rows: the
    # columns were the dates that HAD a stored row, so once the empty ones were
    # gone the axis stopped at the first day of trade. Ask for ninety days and
    # you got thirty-eight, with nothing saying why.
    #
    # The window is a question the caller asked and the answer has to cover it.
    # The days with nothing in them come back with nulls, so the chart and the
    # grid span the period on the button and the empty stretch is visible as an
    # empty stretch.
    #
    # This is NOT the fault that was fixed: nothing is written to the store.
    # Inventing rows in the database made the app believe it had fifteen months
    # of data it had never fetched; spanning the requested window in the REPLY
    # states only what was asked for.
    span = set()
    try:
        _d0 = _dt.date.fromisoformat(str(start)[:10])
        _d1 = _dt.date.fromisoformat(str(end)[:10])
        if _d1 >= _d0 and (_d1 - _d0).days <= 800:
            while _d0 <= _d1:
                span.add(_d0.isoformat())
                _d0 += _dt.timedelta(days=1)
    except Exception:
        span = set()          # an unparseable range falls back to what we hold

    out = []
    for d in sorted(span | set(sales) | set(ads) | set(fin)):
        row = dict(sales.get(d) or {"date": d, "asin": key, "currency": ""})
        row["date"] = d
        a = ads.get(d) or {}
        for k in ("impressions", "clicks", "spend", "ad_orders", "ad_sales"):
            row[k] = a.get(k)
        f = fin.get(d) or {}
        for k in _FIN_COLS:
            row[k] = f.get(k)
        # finance_daily.units is units SHIPPED (money basis); sales_daily.units is
        # units ORDERED (order-date basis). Same word, different measurements, and
        # letting one land on the other would silently replace one with the other.
        row["units_shipped"] = f.get("units")
        if not row.get("currency"):
            row["currency"] = f.get("currency") or ""
        # Derived per DAY as well as per bucket, because a bucket that sums
        # already-derived days would be summing ratios. These two are additive,
        # so summing them is safe; the rates below are recomputed instead.
        # PRINCIPAL, not ordered_sales -- and VAT out first, before anything else.
        # Both are revenue but they are dated differently: ordered_sales by order
        # date, principal by the date the money moved, which is the same basis as
        # the fees and refunds. Mixing the two gives a figure that is neither -- on
        # a live UK account it read 246.53 when the money-basis answer was 281.52,
        # and nothing on screen could have shown which was meant.
        #
        # The arithmetic itself is in net_proceeds_for(), which the Finance screen
        # calls too. It used to be written out here, and a second, quietly
        # different copy lived in domain/contribution.py -- see that function.
        row.update(net_proceeds_for(row, vat_rate))

        # PROFIT -- only when the cost of every unit shipped that day is known.
        #
        # A partial cost is not a small error, it is a number in the wrong
        # direction: the units missing a cost contribute revenue and no cost, so
        # profit comes out HIGH, and it comes out high exactly on the products
        # nobody has costed. Better to say nothing for that day and show the
        # coverage than to publish a figure that flatters.
        u, cu = row.get("units_shipped"), row.get("cogs_units")
        if row["net_proceeds"] is not None and u and cu == u:
            row["profit"] = round(row["net_proceeds"] - float(row.get("cogs") or 0.0), 2)
            p = float(row.get("principal") or 0.0)
            row["margin_pct"] = round(row["profit"] / p * 100, 2) if p else None
        else:
            row["profit"] = None
            row["margin_pct"] = None
        out.append(row)
    # WHERE AMAZON'S OWN TWO ANSWERS DISAGREE, SAY SO RATHER THAN PICK ONE.
    #
    # A row should read across: what the buyers paid, split into the part that
    # is yours and the VAT that is not. On most days it does exactly that. On a
    # few it cannot, because Amazon's Finances feed and its Orders feed do not
    # agree about those particular orders -- measured, all of them are orders
    # that were refunded in full, or where Amazon collected the VAT itself on a
    # cross-border sale and reported a different total from the one the Orders
    # API gave for the same order id.
    #
    # Neither figure is wrong and neither can be derived from the other, so
    # nothing here quietly adjusts one to match. What was missing was any
    # acknowledgement: the screen showed 601.08 + 15.80 under a sales row of
    # 605.77 and left the reader to notice, which reads as a fault in the app.
    if meta is not None:
        gaps = []
        for row in out:
            sold = row.get("ordered_sales")
            ex, vat = row.get("principal"), row.get("vat")
            if not sold or ex is None or vat is None:
                continue
            d = round(float(ex) + float(vat) - float(sold), 2)
            if abs(d) > 0.02:
                gaps.append((row["date"], d))
        meta["basis"] = basis            # what was USED, after any fallback
        meta["basis_note"] = fin_note
        if gaps:
            total = round(sum(d for _, d in gaps), 2)
            meta["tie_out"] = {
                "days": len(gaps), "amount": total,
                "worst": sorted(gaps, key=lambda g: -abs(g[1]))[:3],
                "note": ("On %d day(s) Amazon's settled figures do not add back "
                         "to what the buyers paid, by %s in total. Both come "
                         "from Amazon and neither has been adjusted to fit the "
                         "other; it happens on orders that were refunded in "
                         "full, and on cross-border orders where Amazon "
                         "collected the VAT itself."
                         % (len(gaps), ("%+.2f" % total))),
            }
    return out


def breakdown(config_path, workspace_id, marketplace, start, end, group="asin"):
    """Sales per product for a range, optionally rolled up to the PARENT.

    group='asin'   -> one row per child ASIN, which is the thing that sells
    group='parent' -> variations grouped, so a parent with five children reads as
                      one product rather than five unrelated ones

    parent_asin has been stored on every row since the sales report was first
    parsed and has never been shown anywhere. A t-shirt in six sizes looked like
    six weak products instead of one strong one, which is the opposite of the
    conclusion the numbers support.
    """
    conn = _db.get_db(config_path)
    # COALESCE, not parent_asin alone: a product with no variations has an empty
    # parent, and grouping on that would collapse every standalone product in the
    # account into a single nameless row.
    key = ("CASE WHEN COALESCE(parent_asin,'')<>'' THEN parent_asin ELSE asin END"
           if group == "parent" else "asin")
    rows = conn.execute(
        "SELECT %s k, MAX(COALESCE(parent_asin,'')) parent_asin, "
        "  COUNT(DISTINCT asin) children, "
        "  SUM(COALESCE(units,0)) units, SUM(COALESCE(ordered_sales,0)) revenue, "
        "  SUM(COALESCE(sessions,0)) sessions, SUM(COALESCE(page_views,0)) page_views, "
        "  SUM(COALESCE(order_items,0)) orders, MAX(currency) currency "
        "FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "  AND date>=? AND date<=? AND asin<>'*' "
        "GROUP BY k ORDER BY revenue DESC, units DESC, k" % key,
        (workspace_id, marketplace, start, end)).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        u, s = d["units"] or 0, d["sessions"] or 0
        # Recomputed from the totals, never averaged from the daily rates: the
        # mean of seven daily conversion rates is not the week's conversion rate,
        # and the gap widens the more the daily traffic varies.
        d["conversion"] = round(u / s * 100, 2) if s else None
        d["avg_price"] = round((d["revenue"] or 0) / u, 2) if u else None
        out.append(d)
    return out


def products(config_path, workspace_id, marketplace, start, end):
    """The ASINs that actually sold in a range, biggest first.

    Read from sales_daily rather than the live catalogue, because this list only
    has to contain what the filter can usefully select. An ASIN with no sales in
    the period filters to an empty screen, and a catalogue-driven list is also
    empty until someone has synced the catalogue -- which has nothing to do with
    looking at sales.
    """
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT asin, MAX(parent_asin) parent_asin, "
        "       SUM(COALESCE(units,0)) units, SUM(COALESCE(ordered_sales,0)) revenue "
        "FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "  AND date>=? AND date<=? AND asin<>'*' "
        "GROUP BY asin ORDER BY revenue DESC, units DESC, asin",
        (workspace_id, marketplace, start, end)).fetchall()
    return [dict(r) for r in rows]


# =============================================================================
# HOW EACH METRIC AGGREGATES -- the single definition, used by every caller.
#
# This table is the reason the grid, the stat cards and the CSV cannot disagree.
# It previously existed twice, once here and once in the route, and the two had
# already drifted: the route SUMMED average selling price, so a 30-day column
# read about thirty times the real price. A metric is defined once, here, or it
# will be defined twice and one of them will be wrong (CLAUDE.md Rule 12).
#
#   sum       -- add the values up (units, revenue, sessions)
#   ratio     -- divide one total by another (price = revenue / units)
#   rate      -- the same, as a percentage (conversion = units / sessions)
#   weighted  -- a share, weighted by the thing it is a share OF
#
#   (key, label, kind, good, how)
# `good` says which direction is an improvement, so a rise in ACOS or ad spend
# is never coloured as a win.
# =============================================================================
METRICS = [
    ("ordered_sales",     "Ordered product sales", "money", "up",   ("sum",)),
    ("units",             "Units ordered",         "count", "up",   ("sum",)),
    # ORDERS, not order items. The Sales & Traffic report has no distinct-order
    # count, so this column used to be filled with totalOrderItems and a
    # two-item order counted as two. The Orders API does have it, counts
    # AmazonOrderIds, and now owns this column -- see domain/live_reconcile.py.
    # `order_items` below still carries the report's own figure, so nothing was
    # lost by the column starting to mean what its name says.
    ("orders",            "Orders",                "count", "up",   ("sum",)),
    ("order_items",       "Order items",           "count", "up",   ("sum",)),
    ("avg_selling_price", "Average selling price", "money", "up",   ("ratio", "ordered_sales", "units")),
    ("sessions",          "Sessions",              "count", "up",   ("sum",)),
    ("sessions_mobile",   "Sessions — mobile",     "count", "up",   ("sum",)),
    ("sessions_browser",  "Sessions — browser",    "count", "up",   ("sum",)),
    ("page_views",        "Page views",            "count", "up",   ("sum",)),
    ("unit_session_pct",  "Conversion rate",       "pct",   "up",   ("rate", "units", "sessions")),
    ("buy_box_pct",       "Buy box",               "pct",   "up",   ("weighted", "page_views")),
    ("units_b2b",         "Units — B2B",           "count", "up",   ("sum",)),
    ("ordered_sales_b2b", "Sales — B2B",           "money", "up",   ("sum",)),
    ("impressions",       "Ad impressions",        "count", "up",   ("sum",)),
    ("clicks",            "Ad clicks",             "count", "up",   ("sum",)),
    ("spend",             "Ad spend",              "money", "down", ("sum",)),
    ("ad_sales",          "Ad sales",              "money", "up",   ("sum",)),
    ("ad_orders",         "Ad orders",             "count", "up",   ("sum",)),
    ("acos",              "ACOS",                  "pct",   "down", ("rate", "spend", "ad_sales")),
    ("roas",              "ROAS",                  "count", "up",   ("ratio", "ad_sales", "spend")),
    ("tacos",             "TACOS",                 "pct",   "down", ("rate", "spend", "ordered_sales")),
    # ---- from the Finances API: what Amazon took and what went back ---------
    ("referral_fees",     "Referral fees",         "money", "down", ("sum",)),
    ("fba_fees",          "FBA fees",              "money", "down", ("sum",)),
    ("other_fees",        "Other fees",            "money", "down", ("sum",)),
    ("total_fees",        "Amazon fees",           "money", "down", ("sum",)),
    # Over PRINCIPAL, not ordered_sales: fees are dated when the money moved and
    # ordered_sales when the order was placed, so dividing one by the other gives
    # a rate for no period at all. On live data that read 70% when the true share
    # of what buyers were charged was 18%.
    ("fee_rate",          "Fees as % of charged",  "pct",   "down", ("rate", "total_fees", "principal")),
    ("refunds",           "Refunds",               "money", "down", ("sum",)),
    # THE PART OF THE FEE AMAZON HANDS BACK WITH A REFUND. It was stored, used
    # in net proceeds, and never shown -- 31.67 on selvora_limited that moved
    # the bottom line and appeared on no row, so the arithmetic on screen could
    # not be followed. Money in, so "up" is the good direction.
    ("refund_fees_returned", "Fees returned on refunds", "money", "up", ("sum",)),
    ("refund_units",      "Units refunded",        "count", "down", ("sum",)),
    ("refund_rate",       "Refund rate",           "pct",   "down", ("rate", "refund_units", "units")),
    ("promos",            "Promotions funded",     "money", "down", ("sum",)),
    ("reimbursements",    "Reimbursements",        "money", "up",   ("sum",)),
    # What is left after Amazon's cut, refunds and funded discounts. NOT profit:
    # it is before cost of goods, and calling it profit would be a wrong number
    # dressed as a right one.
    # "(ex VAT)" IS THE WHOLE POINT OF THE NAME. Amazon reports Principal
    # EXCLUDING VAT and sends the tax as its own line -- measured, 80.47 of tax
    # against 402.39 of principal, exactly 20% on top. So there is nothing for
    # "Revenue after VAT" below to take out, and the two rows show the identical
    # number. That is arithmetically right and it reads as a fault: a row called
    # "Charged to buyers" sounds like what the buyer actually handed over, which
    # is this plus the VAT. Saying "ex VAT" here is what makes the pair make
    # sense at a glance instead of looking like the VAT was forgotten.
    ("principal",         "Charged to buyers (ex VAT)", "money", "up", ("sum",)),
    # VAT out first: it was collected, not earned. net_revenue is what is left.
    ("vat",               "VAT",                   "money", "down", ("sum",)),
    ("net_revenue",       "Revenue after VAT",     "money", "up",   ("sum",)),
    ("net_proceeds",      "Net proceeds",          "money", "up",   ("sum",)),
    # ---- cost of goods, from the cost written into each generated SKU -------
    ("units_shipped",     "Units shipped",         "count", "up",   ("sum",)),
    ("cogs",              "Cost of goods",         "money", "down", ("sum",)),
    # Profit and margin are recomputed from the parts, and are None for any
    # bucket containing a unit whose cost is unknown -- see profit_for() below.
    ("profit",            "Profit",                "money", "up",   ("profit",)),
    ("margin_pct",        "Margin",                "pct",   "up",   ("margin",)),
]

_AGG = {m[0]: m[4] for m in METRICS}
METRIC_KEYS = [m[0] for m in METRICS]

# =============================================================================
# WHICH SECTION OF THE GRID EACH METRIC BELONGS TO.
#
# "the p&l heatmap has spacing in it to separate data and make it easy to
# understand visually". Measured on Orbit: its grid is not one long list of
# thirty-three rows. It is six SECTIONS, each introduced by a header row --
# 24px tall on rgb(45,50,66), against 29px transparent for a data row:
#
#     SALES & REVENUE   ORGANIC   PPC   COSTS & DEDUCTIONS   TRAFFIC   DERIVED
#
# That banding is the whole difference between a grid you can scan and a wall of
# numbers: "is my advertising working" is answered by four adjacent rows rather
# than by four rows scattered through thirty.
#
# Declared HERE, beside the metrics themselves, because a metric's section is a
# fact about the metric. Kept as a separate table rather than a seventh element
# of each tuple so that nothing already unpacking those five positions breaks.
#
# Order matters: the grid draws the sections in this order and the metrics
# within each section in METRICS order. Anything not listed falls into "Other",
# which is how a newly added metric appears at all rather than vanishing.
METRIC_SECTIONS = [
    ("Sales & revenue", [
        "ordered_sales", "net_revenue", "principal", "profit", "margin_pct",
        "orders", "units", "units_shipped", "avg_selling_price",
        "ordered_sales_b2b", "units_b2b",
    ]),
    ("PPC", [
        "ad_sales", "spend", "ad_orders", "acos", "tacos", "roas",
        "impressions", "clicks",
    ]),
    ("Costs & deductions", [
        "total_fees", "referral_fees", "fba_fees", "other_fees", "fee_rate",
        "cogs", "vat", "refunds", "refund_units", "refund_rate",
        "refund_fees_returned", "promos",
        "reimbursements", "net_proceeds",
    ]),
    ("Traffic", [
        "sessions", "sessions_mobile", "sessions_browser", "page_views",
        "unit_session_pct", "buy_box_pct",
    ]),
]

# key -> section name, for the renderer.
METRIC_SECTION_OF = {k: name for name, keys in METRIC_SECTIONS for k in keys}


def sections_for(keys):
    """[(section, [key, ...]), ...] for the keys actually present, in order.

    Empty sections are dropped: a heading over nothing is worse than no heading,
    and which metrics arrive depends on which Amazon feeds have answered.
    """
    have = set(keys or [])
    out = []
    for name, wanted in METRIC_SECTIONS:
        got = [k for k in wanted if k in have]
        if got:
            out.append((name, got))
    placed = {k for _, got in out for k in got}
    rest = [k for k in (keys or []) if k not in placed]
    if rest:
        out.append(("Other", rest))
    return out


def aggregate(rows, key):
    """One metric over many rows, by that metric's OWN rule.

    Rates and prices are recomputed from their parts, never averaged from the
    daily figures: the mean of thirty conversion rates is not the period's
    conversion rate, and the gap grows the more uneven the days are.
    """
    how = _AGG.get(key, ("sum",))
    if how[0] == "ratio":
        return _div(_sum(rows, how[1]), _sum(rows, how[2]))
    if how[0] == "rate":
        return _pct(_sum(rows, how[1]), _sum(rows, how[2]))
    if how[0] == "weighted":
        return _weighted(rows, key, how[1])
    if how[0] == "profit":
        return profit_for(rows)
    if how[0] == "margin":
        p, charged = profit_for(rows), _sum(rows, "principal")
        return _pct(p, charged) if p is not None else None
    return _sum(rows, key)


def profit_for(rows):
    """Profit across rows, or None if ANY unit in them has no known cost.

    Not the sum of the daily profits: a week containing one uncosted day would
    then report the other six days' profit as the week's, which is a smaller
    number presented as a complete one. Recomputed from the parts, and withheld
    entirely unless every unit in the bucket is costed -- because a partial cost
    of goods only ever makes profit look BETTER than it is.
    """
    units = _sum(rows, "units_shipped")
    costed = _sum(rows, "cogs_units")
    if not units or costed != units:
        return None
    net = _sum(rows, "net_proceeds")
    if net is None:
        return None
    return round(net - float(_sum(rows, "cogs") or 0.0), 2)


def bucket(rows, gran):
    """Group daily rows into day, week (Mon-start) or month. Returns (map, order)."""
    import datetime as _dt
    buckets, order = {}, []
    for r in rows:
        d = r["date"]
        if gran == "week":
            dt = _dt.datetime.strptime(d, "%Y-%m-%d").date()
            key = (dt - _dt.timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
        elif gran == "month":
            key = d[:7]
        else:
            key = d
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(r)
    return buckets, order


def currency_of(rows):
    """The currency a set of daily rows is in. The FIRST ROW IS NOT IT.

    A row exists for every day in the window, including days with no trade,
    and a day with no trade carries no currency. So taking rows[0] returns ""
    whenever the range starts before the account's first sale -- which is
    exactly what "90 days" and "year to date" do. The screen then printed
    "Total Sales 583" with no pound sign, on the same account where "30 days"
    printed "GBP 384", and nothing on it said why.

    The first row that actually HAS one, which is what contribution.py has
    always done, and now the only implementation of it.
    """
    return next((r.get("currency") for r in (rows or []) if r.get("currency")), "")


def totals(config_path, workspace_id, marketplace, start, end, asin=None,
           vat_rate=None, basis="money", meta=None):
    """Every metric over a range, each by its own aggregation rule.

    THE CARDS AND THE GRID ARE THE SAME NUMBERS. This sums the very rows the
    grid draws, so `basis` has to reach here too. Without it the cards were
    stuck on the money calendar while the grid moved to the order one, and the
    two halves of one screen described different trades: on jack_uk, widening
    7d to 14d left Total Sales at 102.21 and moved Profit by 2.72 -- the 7th
    August settlement, a day with no orders in either window.
    """
    rows = series(config_path, workspace_id, marketplace, start, end, asin,
                  vat_rate, basis=basis, meta=meta)
    # DAYS WITH SOMETHING IN THEM, not days in the window.
    #
    # This was len(rows), which meant the same thing until series() began
    # returning a row for every day of the range asked for -- see the note there
    # on the 90-day chart that only drew 38 columns. After that, an untraded
    # September would have reported thirty days of data.
    #
    # The name says "days"; a reader takes that as "days we have figures for",
    # and every use of it does too.
    _real = ("ordered_sales", "orders", "units", "sessions", "page_views",
             "principal", "total_fees", "refunds")
    out = {"days": sum(1 for r in rows
                       if any(r.get(k) is not None for k in _real)),
           "currency": currency_of(rows)}
    for key in METRIC_KEYS:
        out[key] = aggregate(rows, key)
    out["order_items"] = aggregate(rows, "order_items")
    return out


def _sum(rows, key):
    vals = [r.get(key) for r in rows if r.get(key) is not None]
    return round(sum(float(v) for v in vals), 2) if vals else None


def _div(a, b):
    try:
        return round(float(a) / float(b), 2) if a is not None and b else None
    except Exception:
        return None


def _pct(a, b):
    """a as a percentage of b, rounded ONCE at the end.

    This used to call _div, which rounds the RATIO to two decimals -- and a
    ratio is a much smaller number than the percentage it becomes, so rounding
    it first throws away the digits that matter:

        9 units / 513 sessions = 0.017543...
        round(0.0175, 2)       = 0.02
        x 100                  = 2.00%      the truth is 1.75%

    A 14% error on the conversion rate, and worse further down: a genuine 0.4%
    conversion rounds to 0.00 and disappears altogether, so a product that IS
    selling reads as one that never sells. Every rate in the app went through
    here -- conversion, fee rate, refund rate, ACOS, TACOS and margin.
    """
    try:
        if a is None or not b:
            return None
        return round(float(a) / float(b) * 100.0, 2)
    except Exception:
        return None


def _weighted(rows, field, weight):
    num = den = 0.0
    for r in rows:
        v, w = r.get(field), r.get(weight)
        if v is None or not w:
            continue
        num += float(v) * float(w)
        den += float(w)
    return round(num / den, 2) if den else None
