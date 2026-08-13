"""domain/cogs.py -- what the stock cost, resolved in ONE place.

WHERE COST COMES FROM
These SKUs are built by the generator as {source_cost}_{N}Days_{COMPETITOR_ASIN}
-- see build_sku() in amazon_listing_generator.py, which formats the first field
from source_cost. So the cost of goods is already written on every SKU the
generator made, and does not need entering again.

Two things about that are easy to get wrong and both produce a confident wrong
number:

  * 0.00 MEANS UNKNOWN, NOT FREE. build_sku writes "0.00" when it had no cost to
    write. Treating that as a zero cost makes an item look infinitely
    profitable, which is precisely the item someone would then order more of.

  * THE ASIN IN THE SKU IS THE COMPETITOR'S, NOT OURS. CLAUDE.md Rule 1. It is a
    reference used at generation time. It must never be used to identify our own
    listing, and nothing here does -- only the leading cost is read.

NOT EVERY SKU IS ONE OF OURS
Hand-made SKUs exist ("46 pcs wrench", "cleaning brush_11GBP"). On the live
account 85 of 107 SKUs carry a readable cost and 22 do not. Those 22 have NO
cost, not a zero cost, and every figure derived from them has to say so rather
than quietly assuming.

WHY THIS FILE EXISTS AT ALL
_cogs_from_sku and _resolve_cogs already lived in dashboard.py and are used by
the listings screen. The sales dashboard needs the same answer. A second copy
would have drifted the first time either changed (CLAUDE.md Rule 12), so the
originals were MOVED here and dashboard.py now calls these. Behaviour is
unchanged -- same parse, same override precedence.
"""


def cost_from_sku(sku):
    """The source cost written into a generated SKU, or None.

    Deliberately the same permissive parse dashboard.py has always used: take
    everything before the first underscore and see if it is a number. Anything
    that is not -- a hand-typed SKU, a name -- has no cost, and 0.00 is treated
    as no cost rather than as free.
    """
    try:
        first = str(sku).split("_", 1)[0]
        v = float(first)
        if v > 0:
            return v
    except Exception:
        pass
    return None


def resolve(overrides, account_id, sku):
    """(cost, source) for one SKU. source is 'manual', 'sku', or ''.

    A manual override always wins: someone typed it because the SKU was wrong or
    absent, and a parsed number must never quietly overrule a person.
    """
    key = "%s::%s" % (account_id, sku)
    if overrides and key in overrides:
        try:
            return float(overrides[key]), "manual"
        except (TypeError, ValueError):
            pass
    c = cost_from_sku(sku)
    if c is not None:
        return c, "sku"
    return None, ""


def lookup(overrides, account_id):
    """A one-argument cost function for callers that only have a SKU.

    Returns f(sku) -> (cost_or_None, source), so the finance parser can price
    each shipment line without knowing anything about where costs come from.
    """
    def _f(sku):
        return resolve(overrides, account_id, sku)
    return _f


def coverage(config_path, account_id, marketplace, overrides=None):
    """How much of this catalogue has a known cost. For telling the truth on screen.

    A profit figure covering four fifths of your SKUs is useful; the same figure
    presented as if it covered all of them is not. This is what lets the screen
    say which it is.
    """
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, account_id, marketplace) or {}
    except Exception:
        rec = {}
    known = unknown = 0
    missing = []
    for it in (rec.get("items") or []):
        sku = str(it.get("sku") or "").strip()
        if not sku:
            continue
        cost, _src = resolve(overrides, account_id, sku)
        if cost is None:
            unknown += 1
            if len(missing) < 50:
                missing.append(sku)
        else:
            known += 1
    total = known + unknown
    return {"known": known, "unknown": unknown, "total": total,
            "pct": (round(known / total * 100, 1) if total else None),
            "missing_skus": missing}
