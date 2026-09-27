"""domain/unit_profit.py -- what ONE unit of a listing earns at ONE price.

THE ONE ANSWER for every screen that shows a listing's profit:

    the price editor / revenue calculator   routes/revenue_routes.py
    the Live catalogue rows                 routes/live_routes.py
    the profit returned after a cost edit   routes/cogs_routes.py

Measured 27 Sep 2026, those three worked it out three ways: the calculator from
Amazon's fee on the price the buyer paid with VAT left in the profit, the Live
rows and the cost editor from a FLAT 15% (dashboard._estimate_profit, whose
callers never passed a rate). The repricer, a fourth way, is built on the same
pieces as this one: listing/pricing.achieved for the arithmetic and the
three-tier fee resolver for Amazon's cut (CLAUDE.md Rule 12).

    profit = what the buyer paid (price + postage they paid)
           - VAT, at the account's own setting
           - Amazon's fee   (what it actually took on this product's settled
                             sales, else its own quote, else this account's
                             measured rate -- domain/amazon_fees.breakdown_for)
           - what the unit cost

    margin = profit / what the buyer paid after VAT    -- as on every screen
    roi    = profit / what the unit cost

NO COST, NO PROFIT. A unit whose cost is unknown has no profit to state -- an
item that appears to cost nothing looks infinitely profitable. (A PERIOD with
some uncosted units is different: the owner's rule is to show it and say it is
too high, because most of it is still known. See domain/order_profit.)

NOTHING HERE CALLS AMAZON. breakdown_for reads what is stored.
"""
from domain import amazon_fees as _fees
from listing import pricing as _pricing

_ACCOUNT = object()      # "use the account's own VAT setting"


def account_vat_rate(config_path, workspace_id):
    """The VAT rate set on the account, or None when nobody has said."""
    try:
        from config import settings as _settings
        from domain import sales_data as _sd
        return _sd.vat_rate_for(_settings.read_raw(config_path) or {},
                                workspace_id)
    except Exception:
        return None


def at_price(config_path, workspace_id, marketplace, sku, asin, price, cost,
             shipping=0.0, is_fba=False, currency="GBP", vat_rate=_ACCOUNT):
    """{gross, vat, net_price, fees, fees_total, cost, profit, margin_pct,
        roi_pct, vat_rate} for one unit. Never raises."""
    try:
        gross = round(float(price or 0.0) + float(shipping or 0.0), 2)
    except (TypeError, ValueError):
        gross = 0.0
    if vat_rate is _ACCOUNT:
        vat_rate = account_vat_rate(config_path, workspace_id)

    fees = {}
    if gross > 0:
        try:
            fees = _fees.breakdown_for(config_path, workspace_id, marketplace,
                                       asin, gross, is_fba=is_fba,
                                       currency=currency, sku=sku) or {}
        except Exception:
            fees = {}
    taken = fees.get("total")

    out = {"gross": gross, "fees": fees,
           "fees_total": (None if taken is None else round(float(taken), 2)),
           "cost": cost, "vat_rate": vat_rate, "vat": None, "net_price": None,
           "profit": None, "margin_pct": None, "roi_pct": None}
    if gross <= 0 or taken is None:
        return out
    # The rate is passed as nought and Amazon's whole charge as `other_fees`:
    # breakdown_for has already worked the fee out in pounds at this price.
    got = _pricing.achieved(gross, cost if cost is not None else 0.0, 0.0,
                            other_fees=float(taken), vat_rate=vat_rate)
    out["vat"], out["net_price"] = got.get("vat"), got.get("net_price")
    if cost is None:
        return out
    out.update({"profit": got["profit"], "margin_pct": got["margin_pct"],
                "roi_pct": got["roi_pct"]})
    return out


def as_estimate(u):
    """The shape the Live catalogue rows and the cost editor have always read
    ({price, cogs, referral, net, margin, roi}), filled from at_price -- so the
    screens keep working while the number behind them changes."""
    if not u or u.get("profit") is None:
        return None
    return {"price": u["gross"], "cogs": round(float(u["cost"]), 2),
            "referral": u["fees_total"], "vat": u["vat"],
            "net": u["profit"], "margin": u["margin_pct"], "roi": u["roi_pct"],
            "fee_basis": (u.get("fees") or {}).get("basis") or ""}
