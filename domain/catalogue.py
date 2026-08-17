"""domain/catalogue.py -- what a product IS, for screens that only have its code.

Sales, Traffic and Orders all end up holding an ASIN or a SKU and needing the
two things that make it readable to a person: the product's name and its
picture. B0F9NQ6WZK is not a shoe to anybody.

ONE LOOKUP, because there were about to be three. domain/traffic_view.py had
_titles(); routes/orders_routes.py grew _pictures(); and the Sales breakdown --
"i dont see the images reflecting correctly on the sales page" -- needed both.
Three readings of the same snapshot drift: one matches SKU before ASIN, another
only ASIN, a third lowercases and the fourth does not, and the same product
quietly gets two different pictures on two screens of one app. CLAUDE.md Rule 12.

THE SOURCE IS THE CACHED LIVE SNAPSHOT, which is what the Listings cards draw
from, so a product looks the same everywhere. Nothing here calls Amazon: a
screen that cannot name a product must still draw, and an empty answer is a
missing label rather than a failure.

WHY SKU BEATS ASIN. One ASIN can carry several of our SKUs, at different prices
and from different suppliers. Given a SKU we can be exact; given only an ASIN we
take the first, and the picture of the wrong SKU is still the wrong picture.
"""

_EMPTY = {"img": "", "title": "", "asin": "", "sku": ""}


def key(s):
    """The form both sides of a match are compared in. Case and space folded."""
    return str(s or "").strip().upper()


def index(config_path, workspace_id, marketplace):
    """{sku or asin -> {img, title, asin, sku}} for one workspace.

    Both keys point at the same record, so a caller with either code gets the
    same answer. SKU entries are written first and never overwritten, so an ASIN
    shared by several SKUs cannot displace an exact match.
    """
    out = {}
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, str(workspace_id or ""),
                      str(marketplace or "")) or {}
    except Exception:
        return out
    items = rec.get("items") or []
    for pass_on in ("sku", "asin"):
        for it in items:
            if not isinstance(it, dict):
                continue
            k = key(it.get(pass_on))
            if not k or k in out:
                continue
            out[k] = {"img": str(it.get("img") or ""),
                      "title": str(it.get("title") or ""),
                      "asin": str(it.get("asin") or ""),
                      "sku": str(it.get("sku") or "")}
    return out


def merged(config_path, pairs):
    """One index across several (workspace, marketplace) pairs.

    For the Orders screen, which can be showing more than one account at once.
    Earlier pairs win, so the account you have open is not overwritten by
    another that happens to sell the same ASIN.
    """
    out = {}
    for wsid, mkt in (pairs or []):
        for k, v in index(config_path, wsid, mkt).items():
            out.setdefault(k, v)
    return out


def look(idx, *codes):
    """The first of these codes the index knows. Never raises, never None."""
    for c in codes:
        got = (idx or {}).get(key(c))
        if got:
            return got
    return dict(_EMPTY)


def titles(config_path, workspace_id, marketplace):
    """{asin -> title}, for callers that only want the name.

    Keyed on ASIN alone, which is what the Traffic table groups by.
    """
    out = {}
    for v in index(config_path, workspace_id, marketplace).values():
        a, t = v.get("asin"), v.get("title")
        if a and t:
            out.setdefault(a, t)
    return out
