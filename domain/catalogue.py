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

_EMPTY = {"img": "", "img_source": "", "title": "", "asin": "", "sku": ""}


def key(s):
    """The form both sides of a match are compared in. Case and space folded."""
    return str(s or "").strip().upper()


def index(config_path, workspace_id, marketplace, include_drafts=False):
    """{sku or asin -> {img, title, asin, sku, img_source}} for one workspace.

    Both keys point at the same record, so a caller with either code gets the
    same answer. SKU entries are written first and never overwritten, so an ASIN
    shared by several SKUs cannot displace an exact match.

    `img_source` is "amazon" when the picture came from Amazon's own summary of
    the live listing, and "supplier" when it came from the draft this app built
    -- which is the eBay listing's photograph. THEY ARE NEVER CONFLATED. A
    screen showing a supplier photo where an Amazon one is implied is the app
    telling you what is live on your listing when it is nothing of the kind.

    include_drafts fills in from the app's own records for anything the live
    snapshot cannot picture. Off by default, so screens ABOUT live listings are
    unaffected; the Repricer turns it on because it tracks drafts as well as
    live SKUs, and there "which product is this row" is the question.
    """
    out = {}
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, str(workspace_id or ""),
                      str(marketplace or "")) or {}
    except Exception:
        rec = {}
    items = rec.get("items") or []
    for pass_on in ("sku", "asin"):
        for it in items:
            if not isinstance(it, dict):
                continue
            k = key(it.get(pass_on))
            if not k or k in out:
                continue
            img = str(it.get("img") or "")
            out[k] = {"img": img,
                      "img_source": "amazon" if img else "",
                      "title": str(it.get("title") or ""),
                      "asin": str(it.get("asin") or ""),
                      "sku": str(it.get("sku") or "")}
    if include_drafts:
        _fill_from_drafts(config_path, workspace_id, out)
    return out


# The image attributes a draft carries, best first. A draft built by this app
# holds the SOURCE listing's photographs, which is what makes a row on the
# Repricer identifiable before anything has been sent to Amazon.
_DRAFT_IMG_KEYS = ("main_product_image_locator",
                   "other_product_image_locator_1",
                   "other_product_image_locator_2")


def _fill_from_drafts(config_path, workspace_id, out):
    """Add what the app's own records can picture, without overwriting Amazon.

    Two gaps this closes, both measured on jack_uk's 67 tracked SKUs, 22 of
    which had no picture:

      the SKU is in the live snapshot but Amazon returned no main image
      the SKU is a draft and is not on Amazon at all -- the six variations
      imported from a seller, for instance

    An entry Amazon could picture is never touched.
    """
    import json as _json
    try:
        from data import db as _db
        conn = _db.get_db(config_path)
        rows = conn.execute(
            "SELECT sku, title, competitor_asin, attributes_json "
            "FROM listings WHERE workspace_id=? AND IFNULL(sku,'')<>''",
            (str(workspace_id or ""),)).fetchall()
    except Exception:
        return
    for r in rows:
        k = key(r["sku"])
        if not k:
            continue
        got = out.get(k)
        if got and got.get("img"):
            continue                     # Amazon can picture it; leave it alone
        img = ""
        try:
            attrs = _json.loads(r["attributes_json"] or "{}") or {}
        except Exception:
            attrs = {}
        src = attrs.get("attributes") if isinstance(attrs.get("attributes"), dict) else attrs
        for kk in _DRAFT_IMG_KEYS:
            v = (src or {}).get(kk)
            if isinstance(v, list) and v:
                v = v[0]
            if isinstance(v, dict):
                v = v.get("media_location") or v.get("value") or ""
            v = str(v or "").strip()
            if v.startswith("http"):
                img = v
                break
        if not img and not got:
            # Still worth an entry: the NAME alone makes a row readable, and a
            # row with a name and no picture beats a row with neither.
            out[k] = {"img": "", "img_source": "",
                      "title": str(r["title"] or ""),
                      "asin": str(r["competitor_asin"] or ""), "sku": str(r["sku"])}
            continue
        if not img:
            continue
        if got:
            got["img"] = img
            got["img_source"] = "supplier"
            if not got.get("title"):
                got["title"] = str(r["title"] or "")
        else:
            out[k] = {"img": img, "img_source": "supplier",
                      "title": str(r["title"] or ""),
                      "asin": str(r["competitor_asin"] or ""),
                      "sku": str(r["sku"])}


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
