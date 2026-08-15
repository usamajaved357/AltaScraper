"""domain/order_profit.py -- profit on orders PLACED, from the seller's own costs.

WHY THIS EXISTS
The Sales cards showed "Total Sales £0" beside "Profit £80". Both figures were
right and they described different trades, because Amazon dates its two feeds
differently:

    Sales & Traffic report / Orders API   dated by when the order was PLACED
    finance records                       dated by when the MONEY MOVED

So an order placed yesterday is a sale yesterday and a profit whenever Amazon
settles it, which may be weeks later. Profit on the cards came from the settled
side while sales came from the ordered side, and a row of five cards contradicted
itself.

Amazon cannot answer "what did I make on yesterday's orders" -- it has not
settled them, so it reports no profit against them at all. But the seller can:
they know what the stock cost. Asked for exactly that: "yes use my cost prices
for profit".

    profit = product sales - Amazon's fees - what the stock cost

TWO OF THOSE THREE ARE FACTS.
  product sales   the item price Amazon returned for each line (order_lines)
  cost of goods   the seller's own cost, resolved by domain/cogs.py

THE THIRD IS AN ESTIMATE AND IS TREATED AS ONE. Amazon's exact fee for an
unsettled order does not exist yet. Rather than assume the textbook 15%, this
works the rate out from THE ACCOUNT'S OWN settled history -- what Amazon has
actually charged this seller, on their own products, per pound of sales. The
textbook rate is only the fallback for an account with no settled history at all,
and which of the two was used is reported, never hidden.

WHAT IT WILL NOT DO
Silently price the SKUs it has no cost for. Those lines are counted and named.
A profit figure covering four fifths of the orders is useful; the same figure
presented as if it covered all of them is not.
"""

# Amazon's most common referral rate, and the same constant the Orders screen
# already estimates a single order with. Imported from there rather than
# redeclared so there is one number, not two that drift.
try:
    from domain.orders_view import DEFAULT_REFERRAL_RATE
except Exception:                                    # importable in isolation
    DEFAULT_REFERRAL_RATE = 0.15

# Below this, a derived rate is not worth trusting -- a couple of settled orders
# can be atypical, and a wrong fee rate moves profit more than anything else here.
MIN_PRINCIPAL_FOR_RATE = 50.0

# How far back to look for settled history when working the rate out.
RATE_WINDOW_DAYS = 120


def fee_rate(config_path, workspace_id, marketplace, end_date, days=RATE_WINDOW_DAYS):
    """(rate, basis, detail) -- what Amazon actually charges THIS account.

    Worked out from the finance records: every fee Amazon has taken, over
    everything buyers were charged, across the recent settled past. That is a
    measurement of this seller's own products in their own categories, which a
    flat 15% is not.
    """
    import datetime as _dt
    try:
        end = _dt.date.fromisoformat(str(end_date))
    except Exception:
        end = _dt.date.today()
    start = end - _dt.timedelta(days=int(days))

    try:
        from domain import finance_data as _fd
        rows = _fd.series(config_path, workspace_id, marketplace,
                          start.isoformat(), end.isoformat())
    except Exception:
        rows = {}

    fees = principal = 0.0
    for r in (rows or {}).values():
        for k in ("referral_fees", "fba_fees", "other_fees"):
            try:
                fees += float(r.get(k) or 0.0)
            except (TypeError, ValueError):
                pass
        try:
            principal += float(r.get("principal") or 0.0)
        except (TypeError, ValueError):
            pass

    if principal >= MIN_PRINCIPAL_FOR_RATE and fees > 0:
        rate = round(fees / principal, 4)
        return rate, "measured", (
            "%.1f%% -- what Amazon actually charged this account on %.2f of "
            "settled sales since %s" % (rate * 100, principal, start.isoformat()))
    return DEFAULT_REFERRAL_RATE, "assumed", (
        "%.0f%% -- Amazon's usual referral rate, used because this account has "
        "no settled history to measure yet" % (DEFAULT_REFERRAL_RATE * 100))


def for_lines(lines, cost_of, rate):
    """Profit across order lines, plus exactly what could not be priced.

    `lines` are order_lines rows: each has sku, units and revenue (the item
    price Amazon returned). `cost_of` is domain/cogs.lookup -- so SKU costs,
    manual overrides and their precedence stay decided in one place.
    """
    revenue = cogs = covered_revenue = 0.0
    units = costed_units = 0
    missing, orders = {}, set()

    for L in lines or []:
        sku = str((L or {}).get("sku") or "")
        try:
            qty = int((L or {}).get("units") or 0)
        except (TypeError, ValueError):
            qty = 0
        try:
            rev = float((L or {}).get("revenue") or 0.0)
        except (TypeError, ValueError):
            rev = 0.0
        oid = str((L or {}).get("order_id") or "")
        if oid:
            orders.add(oid)
        revenue += rev
        units += qty

        cost, _src = cost_of(sku) if cost_of else (None, "")
        if cost is None:
            # NOT counted as free. A missing cost is the single easiest way to
            # make a product look wonderful, and it is exactly the product
            # someone would then buy more of.
            missing[sku or "(no sku)"] = missing.get(sku or "(no sku)", 0) + 1
        else:
            cogs += float(cost) * qty
            costed_units += qty
            # The revenue of the costed lines ONLY. Profit has to be worked out
            # against the sales it actually has costs for; measuring costed
            # stock against ALL the revenue understates cost and overstates
            # profit, which is the direction that does damage.
            covered_revenue += rev

    revenue = round(revenue, 2)
    covered_revenue = round(covered_revenue, 2)
    fees = round(revenue * float(rate), 2)
    covered_fees = round(covered_revenue * float(rate), 2)
    profit = round(covered_revenue - covered_fees - cogs, 2) if costed_units else None
    margin = (round(profit / covered_revenue * 100, 1)
              if profit is not None and covered_revenue else None)

    return {
        "profit": profit,
        "margin_pct": margin,
        "revenue": revenue,
        "covered_revenue": covered_revenue,
        "fees": fees,
        "covered_fees": covered_fees,
        "cogs": round(cogs, 2),
        "units": units,
        "costed_units": costed_units,
        "orders": len(orders),
        "complete": (not missing) and bool(costed_units),
        "missing_skus": sorted(missing.keys())[:20],
        "missing_units": sum(missing.values()),
    }


def for_period(config_path, workspace_id, marketplace, start, end, overrides=None):
    """Profit on orders PLACED between two dates, from the seller's own costs.

    Returns the figure, how the fee rate was arrived at, and what it does not
    cover -- so the screen can state all three rather than showing a number and
    hoping.
    """
    from domain import cogs as _cogs
    lines = lines_between(config_path, workspace_id, marketplace, start, end)
    rate, basis, detail = fee_rate(config_path, workspace_id, marketplace, end)
    out = for_lines(lines, _cogs.lookup(overrides or {}, workspace_id), rate)
    out.update({"rate": rate, "rate_basis": basis, "rate_detail": detail,
                "start": start, "end": end,
                "basis": "order",
                "note": ("Worked out from your own cost prices, because Amazon "
                         "reports no profit against an order until it settles. "
                         "Fees: " + detail)})
    return out


def lines_between(config_path, workspace_id, marketplace, start, end):
    """Stored order lines for orders PLACED in the window.

    purchase_date is the full UTC timestamp Amazon sent, so the range is
    compared on its date part.
    """
    from data import db as _db
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT order_id, sku, asin, units, revenue, currency, status, purchase_date "
        "FROM order_lines "
        "WHERE workspace_id=? AND marketplace=? "
        "  AND substr(purchase_date, 1, 10) >= ? "
        "  AND substr(purchase_date, 1, 10) <= ? ",
        (workspace_id, marketplace, str(start), str(end))).fetchall()
    # Cancelled orders are not sales and must not carry a profit either.
    dead = ("canceled", "cancelled")
    return [dict(r) for r in rows
            if str(r["status"] or "").lower() not in dead]
