"""domain/cogs_estimate.py -- a cost from the SKU and a quick profit estimate.

Moved word for word out of dashboard.py (Milestone 4, owner-approved 28 Sep 2026).
dashboard.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""

from domain import cogs as _cogs_mod


def _cogs_from_sku(sku):
    """Generated SKUs are formatted {source_price}_{N}Days_{ASIN}; the first
    number is the source cost (incl. shipping). Returns float or None."""
    return _cogs_mod.cost_from_sku(sku)


def _estimate_profit(price, cogs, referral_rate=0.15):
    """Quick profit estimate: price - cogs - referral fee (default 15%).
    FBA fee is not included in the fast estimate (use the Fees API for exact)."""
    try:
        price = float(str(price).replace(",", "").strip() or 0)
    except Exception:
        return None
    if not price or cogs is None:
        return None
    referral = price * referral_rate
    net = price - float(cogs) - referral
    margin = (net / price) if price else 0
    # MARGIN and ROI answer different questions and the card only ever showed the
    # first. Margin is "how much of the sale price do I keep" -- it decides
    # whether a price is healthy. ROI is "how hard is my cash working" -- it
    # decides what to buy next, and on cheap stock it is a far bigger number:
    # 9.50 of goods sold at 18.24 keeps 14.6% margin and returns 28% on the cash.
    roi = (net / float(cogs)) if float(cogs) else None
    return {"price": round(price, 2), "cogs": round(float(cogs), 2),
            "referral": round(referral, 2), "net": round(net, 2),
            "margin": round(margin * 100, 1),
            "roi": (round(roi * 100, 1) if roi is not None else None)}
