"""domain/order_finance.py -- Amazon's fees, kept against the ORDER that caused them.

WHY THIS EXISTS
The P&L grid had two calendars in one column. Sales were dated by when the order
was placed; fees, refunds and everything settled were dated by when the money
moved. Measured on jack_uk over thirty days:

    date          ord.sales    charged
    2026-07-22         None      24.99
    2026-07-29         None     116.64
    2026-08-12         None      29.16
    2026-08-14       102.21       None     <- the sales day has no money rows

The two halves never overlapped on a single day, so reading across a row was
meaningless and the owner was right that it "does not seem to be telling the
truth". It was telling two truths at once.

Amazon does say which order each fee belongs to -- measured on the live account,
13 of 13 shipment events and 1 of 1 refund events carry an AmazonOrderId. That id
was being thrown away: domain/finance_data.parse_events aggregates straight to
date and ASIN. Keeping it lets every fee be reported on the day its ORDER was
placed, which is the day its sale is already reported on.

WHAT THIS DOES NOT TRY TO DO
Advertising. A click on Tuesday may produce an order on Friday or none at all,
so ad spend has no order to belong to and stays on the click date. That is a real
limit of the data, not a shortcut -- Orbit keeps it on the click date for the
same reason and says so.

CLASSIFICATION IS NOT REPEATED HERE. Which charge counts as referral, which as
FBA, what is tax and what is revenue -- all of that is decided in
domain/finance_data and imported. Two copies of that judgement would drift, and
the first symptom would be two screens disagreeing about the same fee.
"""
import datetime as _dt

from data import db as _db
from domain import finance_data as _fd

_COLS = ("referral_fees", "fba_fees", "other_fees", "promo_fees",
         "principal", "tax",
         "refunds", "refund_tax", "refund_units", "refund_fees_returned",
         "promos", "units")


def _blank(order_id, posted):
    d = {"order_id": order_id, "posted_date": posted, "currency": ""}
    for c in _COLS:
        d[c] = 0
    return d


def parse_by_order(payload):
    """Amazon's FinancialEvents -> one row per (order, posting day).

    Walks the same payload finance_data.parse_events does and applies the same
    classification, but keeps the order id instead of collapsing to date+ASIN.

    Returns (rows, skipped) where `skipped` counts events carrying no order id
    -- advertising payments, service fees and anything else that belongs to the
    account rather than to a sale. Those are NOT invented onto an order; they
    stay finance_daily's business and are reported so the gap is visible.
    """
    ev = ((payload or {}).get("FinancialEvents")
          if isinstance(payload, dict) else None) or {}
    rows = {}
    skipped = 0

    def row_for(oid, posted):
        key = (oid, posted)
        if key not in rows:
            rows[key] = _blank(oid, posted)
        return rows[key]

    # ---- shipments: what was charged, and what Amazon took for it -----------
    for s in (ev.get("ShipmentEventList") or []):
        oid = str(s.get("AmazonOrderId") or "")
        posted = _fd._day(s.get("PostedDate"))
        if not oid or not posted:
            skipped += 1
            continue
        r = row_for(oid, posted)
        for it in (s.get("ShipmentItemList") or []):
            try:
                r["units"] += int(it.get("QuantityShipped") or 0)
            except (TypeError, ValueError):
                pass
            for ch in (it.get("ItemChargeList") or []):
                t = str(ch.get("ChargeType") or "").lower().replace("_", "")
                amt = _fd._amt(ch.get("ChargeAmount"))
                cur = _fd._cur(ch.get("ChargeAmount"))
                if cur and not r["currency"]:
                    r["currency"] = cur
                if t in _fd._TAX_TYPES:
                    r["tax"] += amt
                elif t in _fd._REVENUE_TYPES:
                    r["principal"] += amt
            for f in (it.get("ItemFeeList") or []):
                # Fees arrive negative -- money leaving. Stored positive, because
                # "Amazon fees: 3.00" is what a person means by a fee.
                r[_fd._bucket_fee(f.get("FeeType"))] += -_fd._amt(f.get("FeeAmount"))
            for p in (it.get("PromotionList") or []):
                r["promos"] += -_fd._amt(p.get("PromotionAmount"))

    # ---- refunds: money going back, against the order it came from ---------
    # Chargebacks and A-to-z guarantee claims take the money back the same way
    # (same shape), so they count against the order too (30 Sep 2026).
    for s in ((ev.get("RefundEventList") or []) + (ev.get("ChargebackEventList") or [])
              + (ev.get("GuaranteeClaimEventList") or [])):
        oid = str(s.get("AmazonOrderId") or "")
        posted = _fd._day(s.get("PostedDate"))
        if not oid or not posted:
            skipped += 1
            continue
        r = row_for(oid, posted)
        for it in (s.get("ShipmentItemAdjustmentList") or []):
            try:
                r["refund_units"] += abs(int(it.get("QuantityShipped") or 0))
            except (TypeError, ValueError):
                pass
            for ch in (it.get("ItemChargeAdjustmentList") or []):
                t = str(ch.get("ChargeType") or "").lower().replace("_", "")
                amt = -_fd._amt(ch.get("ChargeAmount"))
                if t in _fd._TAX_TYPES:
                    r["refund_tax"] += amt
                elif t in _fd._REVENUE_TYPES or t.replace(" ", "") in ("returnshipping",
                                                                        "restockingfee"):
                    # Return postage / restocking go with the refund they belong to.
                    r["refunds"] += amt
            # The discount you funded, posted back on a refund: the buyer got
            # the price LESS it back, so it makes the refund smaller -- on the
            # refund's own date. Booked against `promos` it moved the ORDER's
            # month and made a refund-only row look like a settled sale
            # (review, 30 Sep 2026). finance_data reads it the same way.
            for p in (it.get("PromotionAdjustmentList") or []):
                r["refunds"] -= _fd._amt(p.get("PromotionAmount"))
            for f in (it.get("ItemFeeAdjustmentList") or []):
                # The part of the fee Amazon hands back with a refund.
                r["refund_fees_returned"] += _fd._amt(f.get("FeeAmount"))

    # ---- everything with no order: counted, never guessed onto one ---------
    for k, v in ev.items():
        if k in ("ShipmentEventList", "RefundEventList", "ChargebackEventList",
                 "GuaranteeClaimEventList"):
            continue
        if isinstance(v, list):
            skipped += sum(1 for x in v
                           if isinstance(x, dict) and not x.get("AmazonOrderId"))

    out = []
    for r in rows.values():
        for c in _COLS:
            r[c] = round(float(r[c]), 2) if c not in ("units", "refund_units") \
                else int(r[c])
        out.append(r)
    return out, skipped


def store(config_path, workspace_id, marketplace, rows):
    """Upsert per-order fees. Re-reading a window REPLACES that window's rows."""
    if not rows:
        return 0
    conn = _db.get_db(config_path)
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cols = list(_COLS) + ["currency"]
    n = 0
    for r in rows:
        conn.execute(
            "INSERT INTO order_fees (workspace_id, marketplace, order_id,"
            " posted_date, %s, fetched_at) VALUES (?,?,?,?,%s,?) "
            "ON CONFLICT(workspace_id, marketplace, order_id, posted_date) "
            "DO UPDATE SET %s, fetched_at=excluded.fetched_at"
            % (", ".join(cols), ",".join("?" * len(cols)),
               ", ".join("%s=excluded.%s" % (c, c) for c in cols)),
            [workspace_id, marketplace, r["order_id"], r["posted_date"]]
            + [r.get(c, 0) for c in cols] + [now])
        n += 1
    conn.commit()
    return n


def refund_for_order(config_path, workspace_id, marketplace, order_id):
    """One order's refunds, from its own postings -> {refunds, refund_tax,
    refund_fees_returned, refund_units} or None. refund_fees_returned is SIGNED:
    fees Amazon handed back less the RefundCommission it kept (30 Sep 2026)."""
    if not order_id:
        return None
    try:
        r = _db.get_db(config_path).execute(
            "SELECT SUM(COALESCE(refunds,0)) refunds, SUM(COALESCE(refund_tax,0)) refund_tax, "
            "SUM(COALESCE(refund_fees_returned,0)) refund_fees_returned, "
            "SUM(COALESCE(refund_units,0)) refund_units FROM order_fees "
            "WHERE workspace_id=? AND marketplace=? AND order_id=?",
            (workspace_id, marketplace, str(order_id))).fetchone()
    except Exception:
        return None
    if not r or not (r["refunds"] or r["refund_fees_returned"]):
        return None
    return {k: round(float(r[k] or 0), 2) for k in ("refunds", "refund_tax",
                                                   "refund_fees_returned")} | {
        "refund_units": int(r["refund_units"] or 0)}


def by_order_date(config_path, workspace_id, marketplace, start, end):
    """{order_date: {fees...}} -- Amazon's money, on the day the ORDER was placed.

    The join is order_fees.order_id -> order_lines.purchase_date, which is the
    whole point: order_lines already knows when each order happened.

    An order whose purchase date we do not hold -- older than the live window
    ever reached -- is reported separately rather than dropped or guessed at. A
    fee with nowhere honest to go must be visible, not silently absent.
    """
    conn = _db.get_db(config_path)
    sums = ", ".join("SUM(f.%s) AS %s" % (c, c) for c in _COLS)
    rows = conn.execute(
        "SELECT substr(l.purchase_date, 1, 10) AS d, %s "
        "FROM order_fees f "
        "JOIN (SELECT DISTINCT workspace_id, marketplace, order_id, purchase_date "
        "      FROM order_lines) l "
        "  ON l.workspace_id = f.workspace_id "
        " AND l.marketplace  = f.marketplace "
        " AND l.order_id     = f.order_id "
        "WHERE f.workspace_id=? AND f.marketplace=? "
        "  AND substr(l.purchase_date,1,10) >= ? "
        "  AND substr(l.purchase_date,1,10) <= ? "
        "GROUP BY d ORDER BY d" % sums,
        (workspace_id, marketplace, str(start), str(end))).fetchall()

    out = {}
    for r in rows:
        d = dict(r)
        day = d.pop("d")
        out[day] = {k: (round(float(v), 2) if v is not None else 0.0)
                    for k, v in d.items()}
    return out


def cogs_by_order_date(config_path, workspace_id, marketplace, start, end):
    """{order_date: {cogs, cogs_units, units}} from the cost frozen on each line.

    On the order basis the stock cost belongs to the day the order was placed --
    the same day as its sale -- and order_lines already holds both, because the
    cost was frozen onto the line when the order was first seen.

    cogs_units counts only the units that HAVE a cost, so the caller can tell a
    complete figure from a partial one. Everything downstream refuses to publish
    a profit unless those two match, and that rule is the reason an uncosted
    product cannot quietly flatter a day.
    """
    conn = _db.get_db(config_path)
    dead = ("canceled", "cancelled")
    rows = conn.execute(
        "SELECT substr(purchase_date,1,10) AS d, "
        "       SUM(CASE WHEN cogs IS NOT NULL THEN cogs * units ELSE 0 END) AS cogs, "
        "       SUM(CASE WHEN cogs IS NOT NULL THEN units ELSE 0 END) AS costed, "
        "       SUM(units) AS units "
        "FROM order_lines "
        "WHERE workspace_id=? AND marketplace=? "
        "  AND lower(COALESCE(status,'')) NOT IN (?,?) "
        "  AND substr(purchase_date,1,10) >= ? "
        "  AND substr(purchase_date,1,10) <= ? "
        "GROUP BY d ORDER BY d",
        (workspace_id, marketplace, dead[0], dead[1], str(start), str(end))
    ).fetchall()
    return {r["d"]: {"cogs": round(float(r["cogs"] or 0), 2),
                     "cogs_units": int(r["costed"] or 0),
                     "units_shipped": int(r["units"] or 0)}
            for r in rows}


def _blank_bucket(key, group):
    """One empty day (or product) of order-calendar money."""
    return {
        "date": key if group == "date" else None,
        "asin": key if group == "asin" else None,
        "currency": "",
        "referral_fees": 0.0, "fba_fees": 0.0, "other_fees": 0.0,
        "promo_fees": 0.0,
        "principal": 0.0, "tax": 0.0, "refunds": 0.0, "refund_tax": 0.0,
        "refund_units": 0, "refund_fees_returned": 0.0, "promos": 0.0,
        "units": 0, "cogs": 0.0, "cogs_units": 0,
        # The owner's own per-unit charges (domain/asin_charges: postage out,
        # prep ...), beside the stock cost they sit with.
        "charges": 0.0,
        "orders_settled": 0, "orders_estimated": 0,
        "fees_estimated": 0.0, "reimbursements": 0.0,
        # Orders whose fee could not be estimated at all, because this
        # account has no measured fee rate. Separate from orders_estimated:
        # one is a figure with a stated method, the other is a gap.
        "orders_fee_unknown": 0, "revenue_fee_unknown": 0.0,
        # How much of the VAT we worked out rather than were told, so a figure
        # that is partly our arithmetic can say so.
        "vat_derived": 0.0, "orders_vat_derived": 0,
    }


def complete_by_order_date(config_path, workspace_id, marketplace, start, end,
                           fee_rate=None, vat_rate=None, group="date"):
    """A whole day's economics on the ORDER's calendar, settled or not.

    `group` is "date" (one bucket per day the orders were placed -- the Sales
    series and the P&L) or "asin" (one bucket per product -- the Finance
    screen). ONE function for both, so the per-product table and the account
    total are the same arithmetic cut two ways and cannot disagree
    (CLAUDE.md Rule 12). Measured 27 Sep 2026: the Finance screen had its own
    copy, which left the VAT in, dropped the postage, counted cancelled orders
    and charged a two-product order's whole fee to BOTH products.

    AN ORDER WITH SEVERAL PRODUCTS is split between them by what each line
    sold for. Amazon settles the order, not the line, so its fee, VAT and
    promotion have no truer per-product split than the share of the money.

    REFUNDS AND REIMBURSEMENTS SIT ON THEIR OWN DATE, never re-dated to the
    order. The owner's rule, quoted in domain/pnl.py and reaffirmed 28 Sep 2026:
    "REFUNDS stay on the refund event date -- NOT re-dated to the original
    order. July's profit stays locked. September's refund hits September's
    P&L." They are read from finance_daily, which is dated when the money moved.
    This used to take each order's refunds from order_fees and move them back to
    the order date, so the Sales screen and the P&L put the same refund in
    different months. Reimbursements were never carried at all on this basis.

    WHY THIS EXISTS. by_order_date() can only speak for orders Amazon has
    already settled, and Amazon settles about eleven days after the order. So a
    day's sales covered nine units while its fees covered six, and profit came
    out as six orders' proceeds minus nine units of stock -- a loss on a day
    that made money.

    Every order placed in the window is therefore accounted for:

        settled    Amazon's own fees, principal and tax, exactly as reported
        not yet    the fee ESTIMATED at this account's measured rate, and the
                   principal derived from what the buyer paid

    Which is Orbit's rule too: "Referral, FBA fees = Finances API basis when
    final, else estimate on order date."

    Every day reports how much of it is estimated, so a figure that is mostly
    guesswork can say so rather than looking as settled as the rest.
    """
    conn = _db.get_db(config_path)
    dead = ("canceled", "cancelled")
    by_asin = (group == "asin")

    # Every LINE of every order placed in the window: what it sold for, what it
    # cost, which product. Gathered per order below, because the order is what
    # Amazon settles.
    orders = {}
    for r in conn.execute(
            "SELECT substr(l.purchase_date,1,10) AS d, l.order_id, "
            "       COALESCE(l.asin,'') AS asin, COALESCE(l.sku,'') AS sku, "
            "       COALESCE(l.revenue,0) + COALESCE(l.shipping,0) AS gross, "
            "       COALESCE(l.units,0) AS units, l.cogs AS cogs, "
            "       l.currency AS currency "
            "FROM order_lines l "
            "WHERE l.workspace_id=? AND l.marketplace=? "
            "  AND lower(COALESCE(l.status,'')) NOT IN (?,?) "
            "  AND substr(l.purchase_date,1,10) >= ? "
            "  AND substr(l.purchase_date,1,10) <= ?",
            (workspace_id, marketplace, dead[0], dead[1], str(start), str(end))):
        o = orders.setdefault(r["order_id"], {"d": r["d"], "lines": []})
        o["lines"].append(r)

    # What Amazon SETTLED, per order. Refunds are deliberately not read here --
    # they come from their own date, below.
    settled = {}
    for r in conn.execute(
            "SELECT order_id, SUM(referral_fees) rf, SUM(fba_fees) ff, "
            "       SUM(other_fees) of_, SUM(promo_fees) pf, "
            "       SUM(principal) pr, SUM(tax) tx, SUM(promos) pm "
            "FROM order_fees WHERE workspace_id=? AND marketplace=? "
            "GROUP BY order_id", (workspace_id, marketplace)):
        # A refund posting is also an order_fees row. An order whose ONLY rows
        # are a refund has not had its sale settled, and treating it as settled
        # would give it no fee and no revenue.
        if (r["rf"] or r["ff"] or r["of_"] or r["pf"] or r["pr"] or r["tx"]
                or r["pm"]):
            settled[r["order_id"]] = r

    try:
        vr = float(vat_rate) if vat_rate else 0.0
    except (TypeError, ValueError):
        vr = 0.0
    # AN UNKNOWN FEE RATE IS NOT A FEE OF NOTHING.
    #
    # This read `float(fee_rate or 0)`, and order_profit.fee_rate returns None
    # whenever it cannot measure a rate -- a new account, one with no settled
    # orders yet, one whose settlement feed has not arrived. None became 0.0,
    # every unsettled order was estimated to cost nothing in fees, and the day's
    # profit was overstated by the whole referral fee. Silently, and precisely
    # when the app knew least.
    #
    # The default was 0.15 for the same reason and is no better: measured on
    # this owner's own accounts, nestwell and selvora pay about 18% because
    # Amazon charges VAT on its fees. A fee rate is a measurement, not a
    # constant, so there is no number to fall back to -- only an answer of
    # "not known", which the callers can then report.
    try:
        rate = None if fee_rate is None else float(fee_rate)
    except (TypeError, ValueError):
        rate = None

    out = {}

    def _bucket(key):
        return out.setdefault(key, _blank_bucket(key, group))

    # THE OWNER'S PER-UNIT CHARGES, per line, at the rate that applied on the
    # day of the order. Worked out HERE so every screen built on this function
    # subtracts them -- they used to come off the Profit card and the P&L only,
    # so the Sales grid and the Finance product rows read higher by exactly
    # that. Found by the review of the profit-accuracy work, 28 Sep 2026.
    _charge_memo = {}

    def _charge(asin, sku, day):
        k = (asin, sku, day)
        if k not in _charge_memo:
            try:
                from domain import asin_charges as _ac
                per, _parts = _ac.per_unit(config_path, workspace_id,
                                           marketplace, asin, sku=sku,
                                           on_date=day)
                _charge_memo[k] = float(per or 0.0)
            except Exception:
                _charge_memo[k] = 0.0
        return _charge_memo[k]

    for oid, order in orders.items():
        lines = order["lines"]
        gross_total = sum(float(L["gross"] or 0) for L in lines)
        # Each line's share of the order. Equal shares for an order that sold
        # for nothing, so its fee is still carried somewhere rather than lost.
        if gross_total > 0:
            shares = [float(L["gross"] or 0) / gross_total for L in lines]
        else:
            shares = [1.0 / len(lines)] * len(lines)

        # THE ORDER'S MONEY, worked out once for the whole order exactly as it
        # always was, then shared between its lines. Grouped by date every line
        # of an order is on the same day, so the day's figures are unchanged.
        o = {k: 0.0 for k in ("referral_fees", "fba_fees", "other_fees",
                              "promo_fees", "principal", "tax", "promos",
                              "fees_estimated", "vat_derived",
                              "revenue_fee_unknown")}
        flags = {"orders_settled": 0, "orders_estimated": 0,
                 "orders_fee_unknown": 0, "orders_vat_derived": 0}
        s = settled.get(oid)
        if s is not None:
            o["referral_fees"] += float(s["rf"] or 0)
            o["fba_fees"] += float(s["ff"] or 0)
            o["other_fees"] += float(s["of_"] or 0)
            # COUPON AND DEAL FEES. The newer sync files them in their own
            # column rather than inside other_fees (finance_data._bucket_fee),
            # and this left them out -- so a coupon's fee vanished from every
            # order-calendar profit. Older rows have NULL here and their coupon
            # fees still inside other_fees, so adding both never counts twice.
            o["promo_fees"] += float(s["pf"] or 0)
            # WHETHER AMAZON HAS ALREADY TAKEN THE VAT OUT, ASKED PER ORDER.
            #
            # Amazon does not always itemise it. Where it acts as the collector
            # it sends a Tax line and the Principal beside it is NET; where the
            # seller accounts for the VAT themselves it sends NO tax line and
            # the Principal is the whole price the buyer paid.
            #
            # Both shapes arrive on the same day. Measured on selvora_limited,
            # 28 July: 15 of 17 orders came back with tax 0.00 and Principal
            # equal to the full price, and 2 with the VAT itemised. Taking the
            # day's total as reported therefore called 601.08 "Charged to
            # buyers (ex VAT)" when about 88.72 of it was VAT -- so Revenue
            # after VAT was overstated, and profit with it, by the same amount.
            #
            # Asked per ORDER because that is the level Amazon answers it at. A
            # day is a mixture and has no single answer. The unsettled branch
            # below has always derived it this way; this is the same rule
            # applied to the settled ones.
            _pr, _tx = float(s["pr"] or 0), float(s["tx"] or 0)
            if _tx or not vr:
                # Amazon itemised it, or this account is not VAT-registered and
                # there is nothing to take out. Its figures, unaltered.
                o["principal"] += _pr
                o["tax"] += _tx
            else:
                # No tax line and the owner IS registered: the principal is what
                # the buyer paid, VAT included. The rate is the owner's own
                # declaration -- Amazon has not said, and this does not guess it.
                _v = round(_pr * vr / (1.0 + vr), 2)
                o["principal"] += round(_pr - _v, 2)
                o["tax"] += _v
                o["vat_derived"] += _v
                flags["orders_vat_derived"] = 1
            o["promos"] += float(s["pm"] or 0)
            flags["orders_settled"] = 1
        else:
            # NOT YET SETTLED. What the buyer paid is known exactly; how Amazon
            # will split it is not, so the VAT is taken out at the account's own
            # rate and the fee estimated at the rate this account actually pays.
            gross = gross_total
            vat = round(gross * vr / (1.0 + vr), 2) if vr else 0.0
            net = round(gross - vat, 2)
            o["principal"] += net
            o["tax"] += vat
            if rate is None:
                # NO RATE, SO NO ESTIMATE. Adding 0.00 here would make the day
                # report a fee it never worked out, and "estimated 0.00" reads
                # as "we checked and it is nothing". Counted separately so the
                # screen can say how much of the window is uncosted.
                flags["orders_fee_unknown"] = 1
                # What the buyer PAID, the same base the estimate below is
                # charged on, so "revenue not yet itemised" adds up across both.
                o["revenue_fee_unknown"] += gross
            else:
                # ON WHAT THE BUYER PAID. The rate is measured over the
                # VAT-inclusive figure (order_profit.fee_rate), because that is
                # what Amazon charges its fee on; applying it to the figure
                # after VAT would take a sixth too little.
                est = round(gross * rate, 2)
                o["referral_fees"] += est
                o["fees_estimated"] += est
                flags["orders_estimated"] = 1

        # Shared out between the lines, each landing in its own bucket. An
        # order is counted once in every bucket it reaches.
        reached = set()
        for L, w in zip(lines, shares):
            key = (L["asin"] or "") if by_asin else order["d"]
            b = _bucket(key)
            if not b["currency"] and L["currency"]:
                b["currency"] = L["currency"]
            for k, v in o.items():
                b[k] += v * w
            units = int(L["units"] or 0)
            b["units"] += units
            if L["cogs"] is not None:
                b["cogs"] += float(L["cogs"]) * units
                b["cogs_units"] += units
            if units:
                b["charges"] += _charge(L["asin"], L["sku"], order["d"]) * units
            if key not in reached:
                reached.add(key)
                for k, v in flags.items():
                    b[k] += v

    # ---- refunds and reimbursements, on the day the money moved ----------
    if by_asin:
        q = ("SELECT asin AS k, SUM(refunds) rd, SUM(refund_tax) rdt, "
             "SUM(refund_units) ru, SUM(refund_fees_returned) rfr, "
             "SUM(reimbursements) rb, MAX(currency) cur "
             "FROM finance_daily WHERE workspace_id=? AND marketplace=? "
             "AND asin<>'*' AND date>=? AND date<=? GROUP BY asin")
    else:
        q = ("SELECT date AS k, SUM(refunds) rd, SUM(refund_tax) rdt, "
             "SUM(refund_units) ru, SUM(refund_fees_returned) rfr, "
             "SUM(reimbursements) rb, MAX(currency) cur "
             "FROM finance_daily WHERE workspace_id=? AND marketplace=? "
             "AND asin='*' AND date>=? AND date<=? GROUP BY date")
    for r in conn.execute(q, (workspace_id, marketplace, str(start), str(end))):
        if not (r["rd"] or r["rdt"] or r["ru"] or r["rfr"] or r["rb"]):
            continue          # a fees-only day: nothing of this kind happened
        b = _bucket(r["k"])
        if not b["currency"] and r["cur"]:
            b["currency"] = r["cur"]
        b["refunds"] += float(r["rd"] or 0)
        b["refund_tax"] += float(r["rdt"] or 0)
        b["refund_units"] += int(r["ru"] or 0)
        b["refund_fees_returned"] += float(r["rfr"] or 0)
        b["reimbursements"] += float(r["rb"] or 0)

    for o in out.values():
        for k, v in list(o.items()):
            if isinstance(v, float):
                o[k] = round(v, 2)
    return out


def unattributed(config_path, workspace_id, marketplace):
    """Fees whose order this app has never seen, so cannot date.

    Reported rather than hidden: they are real money, and a P&L that quietly
    omits them is wrong in the flattering direction.
    """
    conn = _db.get_db(config_path)
    r = conn.execute(
        "SELECT COUNT(*) AS n, "
        "       SUM(referral_fees + fba_fees + other_fees) AS fees, "
        "       SUM(principal) AS principal "
        "FROM order_fees f WHERE f.workspace_id=? AND f.marketplace=? "
        "  AND NOT EXISTS (SELECT 1 FROM order_lines l "
        "                  WHERE l.workspace_id=f.workspace_id "
        "                    AND l.marketplace=f.marketplace "
        "                    AND l.order_id=f.order_id)",
        (workspace_id, marketplace)).fetchone()
    return {"orders": int(r["n"] or 0),
            "fees": round(float(r["fees"] or 0), 2),
            "principal": round(float(r["principal"] or 0), 2)}
