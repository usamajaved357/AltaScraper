"""domain/pnl_ledger.py -- the items behind each line of the account statement.

Asked for (owner, 30 Sep 2026): "which sku's dont have the cogs i want the
orders numbers of them. i want every detailed breakdown of how these profit
numbers are calculated and also references so i can verify them".

WHAT THIS IS: for one line of domain/pnl.build, the individual orders, refund
postings, days, invoices or costs it is made of -- each with its date (dated
the way the statement dates it), order id, SKU, quantity, amount and where the
figure came from.

WHAT THIS IS NOT: a second calculation. Every line is itemised from the SAME
reads and the SAME per-order arithmetic the statement is built from
(order_finance.placed_orders / settled_orders / order_money / refund_rows,
pnl.settled_fee_rows, order_profit.lines_between / line_cogs,
ad_cost.by_day, expenses.account_charge_parts / adjustment_days /
for_window). The items' total is compared with the statement's own line on
screen, and a difference is shown in red rather than smoothed over.

Amounts are positive as the statement shows them (the line's sign says which
way it moves profit); "Other Amazon transactions" is signed, as on the
statement. Nothing is rounded before it is added: `total` is the rounded sum.
"""
from data import db as _db

# The lines that can be itemised. The subtotals (net_sales,
# profit_before_own_costs, profit) are sums of the lines above them and are
# explained on the screen from the statement itself.
LEDGER_LINES = ("ordered_sales", "vat_line", "refunds", "cogs",
                "referral_fees", "fba_fees", "promo_fees", "other_fees",
                "fees_estimated", "promos", "refund_fees_returned",
                "reimbursements", "charges", "ad_spend", "account_charges",
                "other_amazon", "manual_expenses")


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(r):
    return ("%.2f%%" % (float(r) * 100)).replace(".00%", "%")


def _item(date, amount, source, order_id="", sku="", qty=None, ref="",
          **extra):
    d = {"date": date or "", "order_id": order_id or "", "sku": sku or "",
         "qty": qty, "amount": (None if amount is None else round(float(amount), 4)),
         "source": source, "ref": ref or ""}
    d.update(extra)
    return d


def _skus(lines):
    return ", ".join(sorted({str(L["sku"] or L["asin"] or "") for L in lines} - {""}))


def _units(lines):
    return sum(int(L["units"] or 0) for L in lines)


def _gross(lines):
    return round(sum(float(L["gross"] or 0) for L in lines), 2)


# ---- the order-calendar lines: one pass over the orders -------------------

def _orders(config_path, workspace_id, marketplace, start, end, vat_rate):
    """Every order placed in the window with its money, exactly as
    order_finance.complete_by_order_date works it out."""
    from domain import order_finance as _of
    from domain import order_profit as _op
    conn = _db.get_db(config_path)
    rate, _basis, _detail = _op.fee_rate(config_path, workspace_id, marketplace, end)
    orders = _of.placed_orders(conn, workspace_id, marketplace, start, end)
    settled = _of.settled_orders(conn, workspace_id, marketplace)
    vr = _of._vat_ratio(vat_rate)
    out = []
    for oid in sorted(orders, key=lambda k: (orders[k]["d"], str(k))):
        order = orders[oid]
        o, flags = _of.order_money(order, settled.get(oid), rate, vr)
        out.append((oid, order, o, flags))
    return out, rate, vr


def _sales(rows, vr):
    items = []
    for oid, order, o, fl in rows:
        amt = o["principal"] + o["tax"]
        src = "Amazon settled" if fl["orders_settled"] else "order total (not settled yet)"
        items.append(_item(order["d"], amt, src, oid, _skus(order["lines"]),
                           _units(order["lines"])))
    return items


def _vat(rows, vr):
    items = []
    for oid, order, o, fl in rows:
        if not o["tax"]:
            continue
        if fl["orders_settled"] and not fl["orders_vat_derived"]:
            src = "Amazon's VAT (settled)"
        else:
            src = "worked out at %s (account VAT rate)" % _pct(vr)
        items.append(_item(order["d"], o["tax"], src, oid, _skus(order["lines"]),
                           _units(order["lines"]),
                           "of %.2f the buyer paid" % (o["principal"] + o["tax"])))
    return items


def _estimated(rows, rate):
    items = []
    for oid, order, o, fl in rows:
        if not o["fees_estimated"]:
            continue
        g = _gross(order["lines"])
        items.append(_item(order["d"], o["fees_estimated"],
                           "estimated at %s" % _pct(rate), oid,
                           _skus(order["lines"]), _units(order["lines"]),
                           "%.2f paid x %s (not settled yet)" % (g, _pct(rate))))
    return items


def _promos(rows):
    items = []
    for oid, order, o, fl in rows:
        if o["promos"]:
            items.append(_item(order["d"], o["promos"], "Amazon settled (promotion)",
                               oid, _skus(order["lines"]), _units(order["lines"])))
    return items


def _charges(config_path, workspace_id, marketplace, rows):
    from domain import order_finance as _of
    charge = _of.charge_fn(config_path, workspace_id, marketplace)
    items = []
    for oid, order, o, fl in rows:
        for L in order["lines"]:
            u = int(L["units"] or 0)
            if not u:
                continue
            per = charge(L["asin"], L["sku"], order["d"])
            if per:
                items.append(_item(order["d"], per * u, "your per-product charge",
                                   oid, L["sku"] or L["asin"], u,
                                   "%s a unit x %d" % (("%.4f" % per).rstrip("0").rstrip("."), u)))
    # THE STATEMENT ROUNDS EACH DAY to the penny (order_finance buckets), so a
    # per-unit charge with more than two decimals is shown with that day's
    # rounding as its own item -- the items then add up to the line exactly.
    by_day = {}
    for it in items:
        by_day[it["date"]] = by_day.get(it["date"], 0.0) + it["amount"]
    for d, raw in sorted(by_day.items()):
        diff = round(raw, 2) - raw
        if abs(diff) >= 0.00005:
            items.append(_item(d, diff, "rounding (per day, as the statement)"))
    return items


# ---- fees Amazon itemised, per order --------------------------------------

_FEE_COL = {"referral_fees": "ref", "fba_fees": "fba", "promo_fees": "promo",
            "other_fees": "oth"}


def _fees(config_path, workspace_id, marketplace, start, end, line):
    from domain import pnl as _pnl
    conn = _db.get_db(config_path)
    placed = {}
    for r in conn.execute(
            "SELECT order_id, MIN(substr(purchase_date,1,10)) d, "
            "GROUP_CONCAT(DISTINCT sku) skus, SUM(units) u FROM order_lines "
            "WHERE workspace_id=? AND marketplace=? AND substr(purchase_date,1,10)>=? "
            "AND substr(purchase_date,1,10)<=? GROUP BY order_id",
            (workspace_id, marketplace, start, end)):
        placed[r["order_id"]] = r
    col = _FEE_COL[line]
    items = []
    for r in _pnl.settled_fee_rows(conn, workspace_id, marketplace, start, end):
        amt = _pnl._f(r[col])          # the statement rounds per order
        if not amt:
            continue
        p = placed.get(r["order_id"])
        items.append(_item(p["d"] if p else "", amt, "Amazon settled", r["order_id"],
                           (p["skus"] if p else ""), (p["u"] if p else None),
                           "posted %s" % (str(r["posted"] or "")[:10])))
    return items


# ---- money on the day it moved: refunds, fees back, reimbursements --------

def _order_postings(conn, workspace_id, marketplace, start, end, col):
    """Per-order postings of one order_fees column (refunds, or fees given back)
    dated by when the money moved (posted_date) inside the window, with the
    order's price and SKUs from order_lines where we hold the order."""
    out = []
    for r in conn.execute(
            "SELECT f.order_id, substr(f.posted_date,1,10) d, f.%s a, "
            "f.refund_units ru, f.refund_tax rt, "
            "(SELECT SUM(COALESCE(revenue,0)+COALESCE(shipping,0)) FROM order_lines l "
            " WHERE l.workspace_id=f.workspace_id AND l.marketplace=f.marketplace "
            " AND l.order_id=f.order_id) price, "
            "(SELECT GROUP_CONCAT(DISTINCT sku) FROM order_lines l "
            " WHERE l.workspace_id=f.workspace_id AND l.marketplace=f.marketplace "
            " AND l.order_id=f.order_id) skus "
            "FROM order_fees f WHERE f.workspace_id=? AND f.marketplace=? "
            "AND substr(f.posted_date,1,10)>=? AND substr(f.posted_date,1,10)<=? "
            "AND COALESCE(f.%s,0)<>0 ORDER BY d, f.order_id" % (col, col),
            (workspace_id, marketplace, str(start), str(end))):
        out.append(r)
    return out


def refund_events(config_path, workspace_id, marketplace, start, end):
    """THE per-order refund EVENTS reader (Rule 12: the P&L's Refunds breakdown
    and any other screen that lists refund events use this; order_finance.
    refund_for_order answers a different question -- one order's refunds
    summed over all time, for the Orders screen). -> [{order_id, date, amount,
    refund_units, refund_tax, sku, order_price, full_or_partial, source}].

    One item per order per posting day (order_fees), dated on the day the
    money went back (the owner's rule). `full_or_partial` compares the refund
    with what the buyer paid for the order: "full", "partial", or "unknown"
    when the order is not held here. Amounts positive, as Amazon's refund
    column is stored. Postings Amazon made without an order id are NOT here --
    they are only in finance_daily's day totals (the ledger shows that part
    separately)."""
    conn = _db.get_db(config_path)
    out = []
    for r in _order_postings(conn, workspace_id, marketplace, start, end, "refunds"):
        a, price = _n(r["a"]), r["price"]
        if price:
            # What the buyer got back INCLUDING the VAT Amazon itemised beside
            # it, against what they paid (which includes it): a full refund on
            # a VAT-itemised order is otherwise ex-VAT and looks partial.
            fp = "full" if a + _n(r["rt"]) >= _n(price) - 0.005 else "partial"
        else:
            fp = "unknown"
        out.append({"order_id": r["order_id"], "date": r["d"], "amount": a,
                    "refund_units": int(r["ru"] or 0), "refund_tax": _n(r["rt"]),
                    "sku": r["skus"] or "",
                    "order_price": (round(_n(price), 2) if price else None),
                    "full_or_partial": fp, "source": "Amazon refund posting"})
    return out


def _by_posting_day(config_path, workspace_id, marketplace, start, end, key, col):
    """finance_daily's day totals (what the statement adds), each broken into
    the order postings that make it; any part of a day Amazon did not tie to an
    order we hold is shown as its own item, never dropped or guessed."""
    from domain import order_finance as _of
    conn = _db.get_db(config_path)
    by_day = {}
    if col == "refunds":
        for e in refund_events(config_path, workspace_id, marketplace, start, end):
            ref = {"full": "full refund of %.2f" % (e["order_price"] or 0),
                   "partial": "partial: %.2f of %.2f" % (e["amount"] + e["refund_tax"],
                                                         e["order_price"] or 0),
                   "unknown": "order not held here"}[e["full_or_partial"]]
            by_day.setdefault(e["date"], []).append(
                _item(e["date"], e["amount"], e["source"], e["order_id"], e["sku"],
                      e["refund_units"] or None, ref))
    elif col:
        for r in _order_postings(conn, workspace_id, marketplace, start, end, col):
            by_day.setdefault(r["d"], []).append(
                _item(r["d"], _n(r["a"]), "fee Amazon gave back", r["order_id"],
                      r["skus"] or "", r["ru"] or None))
    totals = {day["k"]: _n(day[key])
              for day in _of.refund_rows(conn, workspace_id, marketplace, start, end)}
    items = []
    for d in sorted(set(totals) | set(by_day)):
        total = totals.get(d, 0.0)
        mine = by_day.get(d, [])
        items.extend(mine)
        rest = total - sum(_n(i["amount"]) for i in mine)
        if abs(rest) < 0.005:
            continue
        if not col:
            src = "Amazon's day total"
        elif rest > 0:
            src = "Amazon's day total, no order held"
        else:
            # An order posting Amazon's day total does not carry: listed above
            # so it is seen, and set against here because the line is the day
            # total (never silently dropped, never counted twice).
            src = "not in Amazon's day total"
        items.append(_item(d, rest, src, ref="finance postings on %s" % d))
    return items


# ---- stock cost, per order line -------------------------------------------

_COST_SRC = {"manual-order": "your cost (this order)", "manual": "your cost (product)"}


def _cogs(config_path, workspace_id, marketplace, start, end):
    from domain import order_profit as _op
    lines = _op.lines_between(config_path, workspace_id, marketplace, start, end)
    items, missing = [], {}
    for L in sorted(lines, key=lambda x: (str(x.get("purchase_date") or ""), str(x.get("order_id")))):
        amt = _op.line_cogs(L)
        d = str(L.get("purchase_date") or "")[:10]
        u = int(L.get("units") or 0)
        sku = str(L.get("sku") or L.get("asin") or "(no sku)")
        if amt is None:
            items.append(_item(d, None, "no cost recorded", L.get("order_id"), sku, u,
                               missing=True))
            m = missing.setdefault(sku, {"sku": sku, "asin": L.get("asin") or "",
                                         # A product cost is kept per SKU: a line
                                         # with none can only take an order cost.
                                         "has_sku": bool(L.get("sku")),
                                         "title": L.get("title") or "", "units": 0,
                                         "value": 0.0, "orders": []})
            m["units"] += u
            v = _n(L.get("revenue")) + _n(L.get("shipping"))
            m["value"] = round(m["value"] + v, 2)
            m["orders"].append({"order_id": L.get("order_id"), "date": d,
                                "qty": u, "value": round(v, 2)})
            continue
        src = _COST_SRC.get(str(L.get("cogs_source") or ""),
                            "older cost (%s)" % (L.get("cogs_source") or "frozen"))
        items.append(_item(d, amt, src, L.get("order_id"), sku, u,
                           "%.2f a unit x %d" % (_n(L.get("cogs")), u)))
    return items, sorted(missing.values(), key=lambda m: -m["units"])


# ---- advertising, per day --------------------------------------------------

def _ads(config_path, workspace_id, marketplace, start, end, vat_rate):
    from domain import ad_cost as _adc
    days, info = _adc.by_day(config_path, workspace_id, marketplace, start, end,
                             _adc.vat_registered(vat_rate), detail=True)
    det = info.get("detail") or {}
    items = []
    for d in sorted(days):
        x = det.get(d) or {}
        vat = _n(x.get("vat"))
        if x.get("source") == "invoices":
            src = "ad invoice"
            ref = "invoice %.2f + VAT %.2f" % (_n(x.get("base")), _n(x.get("vat_invoiced")))
            if not vat and _n(x.get("vat_invoiced")):
                ref += " (VAT reclaimable, not counted)"
        else:
            src = "Ads API"
            ref = ("spend %.2f + VAT %.2f at %s" % (_n(x.get("base")), vat,
                                                   _pct(x.get("vat_ratio") or 0))
                   if vat else "spend %.2f" % _n(x.get("base")))
        items.append(_item(d, days[d], src, ref=ref, base=round(_n(x.get("base")), 4),
                           vat=round(vat, 4)))
    return items, info


# ---- what belongs to the account, not an order ------------------------------

def _account_charges(config_path, workspace_id, marketplace, start, end):
    from domain import expenses as _exp
    conn = _db.get_db(config_path)
    parts = _exp.account_charge_parts(config_path, workspace_id, marketplace, start, end)
    ov = _exp.overhead_for(config_path, workspace_id, marketplace, start, end)
    undated = {}
    try:
        for r in conn.execute(
                "SELECT placed_on, field, SUM(amount) a FROM finance_undated "
                "WHERE workspace_id=? AND marketplace=? AND placed_on>=? AND placed_on<=? "
                "GROUP BY placed_on, field", (workspace_id, marketplace, start, end)):
            undated.setdefault(r["placed_on"], []).append("%s %.2f" % (r["field"], _n(r["a"])))
    except Exception as e:
        # Only a reference is lost, never money -- but said, not swallowed.
        undated = {"_error": "undated charges could not be read (%s)" % e}
    items, got = [], 0.0
    for d in parts["days"]:
        if parts["rule"] == "other-only":
            amt = d["other"]
            ref = "account 'other' fees posted %s" % d["date"]
        else:
            amt = d["charged"] - d["attributed"]
            ref = ("posted %.2f (other %.2f, FBA %.2f, coupon %.2f); %.2f of it on orders"
                   % (d["charged"], d["other"], d["fba"], d["promo"], d["attributed"]))
        if abs(amt) < 0.005:
            continue
        if d["date"] in undated:
            ref += "; undated charge placed here (usually the monthly subscription): " \
                   + ", ".join(undated[d["date"]])
        elif "_error" in undated:
            ref += "; " + undated["_error"]
        got += amt
        items.append(_item(d["date"], amt, "account charge (posted %s)" % d["date"], ref=ref))
    seen = _n(ov.get("amazon_charge_seen"))
    if abs(round(got, 2) - seen) >= 0.005:
        # The rule "never below zero" (expenses.account_level_charge): orders
        # carried more fees than Amazon posted against the account.
        items.append(_item(end, seen - got, "rule: never below zero",
                           ref="orders carried more fees than the account was charged"))
    covered = seen - _n(ov.get("amazon_account_charges"))
    if abs(covered) >= 0.005:
        items.append(_item(end, -covered, "already in your own costs",
                           ref="not taken off twice"))
    return items


def _other_amazon(config_path, workspace_id, marketplace, start, end):
    from domain import expenses as _exp
    return [_item(d, a, "Amazon posting (signed)", ref="adjustments posted %s" % d)
            for d, a in _exp.adjustment_days(config_path, workspace_id, marketplace,
                                             start, end)]


def _own_costs(config_path, workspace_id, marketplace, start, end):
    from domain import expenses as _exp
    w = _exp.for_window(config_path, workspace_id, marketplace, start, end)
    return [_item(x["starts"], x["in_window"], "your own cost",
                  sku=x["name"], ref="%.2f a month, %d day%s here"
                  % (x["monthly"], x["days"], "" if x["days"] == 1 else "s"))
            for x in (w.get("items") or [])]


def ledger(config_path, workspace_id, marketplace, start, end, line,
           vat_rate=None):
    """The items behind one statement line. -> {ok, line, items, total, ...}."""
    if line not in LEDGER_LINES:
        return {"ok": False, "error": "that line has no ledger: %s" % line}
    out = {"ok": True, "line": line, "workspace": workspace_id,
           "marketplace": marketplace, "start": start, "end": end}
    rows = rate = vr = None
    if line in ("ordered_sales", "vat_line", "fees_estimated", "promos", "charges"):
        rows, rate, vr = _orders(config_path, workspace_id, marketplace, start, end,
                                 vat_rate)
    if line == "ordered_sales":
        items = _sales(rows, vr)
    elif line == "vat_line":
        items = _vat(rows, vr)
    elif line == "fees_estimated":
        items = _estimated(rows, rate)
        out["rate"] = rate
    elif line == "promos":
        items = _promos(rows)
    elif line == "charges":
        items = _charges(config_path, workspace_id, marketplace, rows)
    elif line in _FEE_COL:
        items = _fees(config_path, workspace_id, marketplace, start, end, line)
    elif line == "refunds":
        items = _by_posting_day(config_path, workspace_id, marketplace, start, end,
                                "rd", "refunds")
    elif line == "refund_fees_returned":
        items = _by_posting_day(config_path, workspace_id, marketplace, start, end,
                                "rfr", "refund_fees_returned")
    elif line == "reimbursements":
        items = _by_posting_day(config_path, workspace_id, marketplace, start, end,
                                "rb", None)
        for it in items:
            it["source"] = "Amazon reimbursement"
    elif line == "cogs":
        items, missing = _cogs(config_path, workspace_id, marketplace, start, end)
        out["missing"] = missing
        out["missing_units"] = sum(m["units"] for m in missing)
    elif line == "ad_spend":
        items, info = _ads(config_path, workspace_id, marketplace, start, end, vat_rate)
        out["ads_source"] = info.get("source")
        out["vat_added"] = info.get("vat_added")
    elif line == "account_charges":
        items = _account_charges(config_path, workspace_id, marketplace, start, end)
    elif line == "other_amazon":
        items = _other_amazon(config_path, workspace_id, marketplace, start, end)
    else:  # manual_expenses
        items = _own_costs(config_path, workspace_id, marketplace, start, end)
    out["items"] = items
    out["count"] = len(items)
    out["total"] = round(sum(_n(i["amount"]) for i in items if i["amount"] is not None), 2)
    return out
