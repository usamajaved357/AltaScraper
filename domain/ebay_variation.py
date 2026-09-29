"""domain/ebay_variation.py -- an eBay supplier link, made to point at ONE product.

    "when a listing has 3 variations but 2 of them are out of stock then the
     url of ebay do not have variation id, and then when it is uploaded to the
     repricer, it says that there is no variant id in the link and item seems to
     contains variations so there is an error in accepting that link"
                                                      -- owner, 30 Sep 2026

A variation listing is one eBay listing holding several products. A link to it
without ?var= does not say which one, so there is no single price or stock to
read -- that part of the refusal is right. What was wrong is that the app gave
up there, although the answer was already in hand: api/ebay.get_item fetches
the family (get_items_by_item_group) to tell a family from an ended listing,
and each child carries its own stock.

THE RULE, and why each branch is what it is:
  * exactly ONE child is in stock and every other one is DEFINITELY out of
    stock  -> that child is the only product the link can mean. It is linked,
    and the note says which one, so nothing is picked silently;
  * two or more in stock, or ANY child's stock is unknown -> the owner chooses.
    Unknown is never read as out of stock (the repricer's rule everywhere), so
    an unknown sibling is never ruled out;
  * none in stock -> the owner chooses too; there is nothing to prefer.

The chosen link is stored in one form, https://<host>/itm/<listing>?var=<id>,
because every later read (the sweep's check_source -> get_item) takes the
variation from the URL, and the supplier list de-duplicates on exact text.

One helper for every way a supplier link comes in (add one, the supplier
sheet, add a variant) -- Rule 12.
"""
from api import ebay as _ebay
from domain import seller_import as _si
from domain import source_fetch as _sf


def _label(child):
    """What tells this child from its siblings: its aspects, else its title."""
    asp = _si._aspects(child)
    bits = [v for k, v in asp.items() if v and k.lower() not in ("brand", "mpn", "ean", "upc", "type")]
    return " / ".join(bits[:4]) or str(child.get("title") or "").strip()[:80]


def variations(group_data, base_url=""):
    """The children of a family -> [{url, var_id, label, price, currency,
    in_stock}] in eBay's order. in_stock is True / False / None (unknown)."""
    out = []
    for c in (group_data or {}).get("items") or []:
        iid = str(c.get("itemId") or "").split("|")
        var = iid[2] if len(iid) == 3 and iid[2] not in ("", "0") else ""
        if not var:
            continue
        url = _si._child_url(c, {"url": base_url})
        price = (c.get("price") or {}) if isinstance(c.get("price"), dict) else {}
        try:
            p = float(price.get("value")) if price.get("value") is not None else None
        except (TypeError, ValueError):
            p = None
        out.append({"url": url, "var_id": var, "label": _label(c), "price": p,
                    "currency": str(price.get("currency") or ""),
                    "in_stock": _sf._ebay_stock(c)})
    return out


def pick(choices):
    """The one child the link can only mean, or None. See the module rule."""
    in_stock = [c for c in choices if c.get("in_stock") is True]
    unknown = [c for c in choices if c.get("in_stock") is None]
    if len(in_stock) == 1 and not unknown:
        return in_stock[0]
    return None


def resolve(url, app_id, cert_id, marketplace="EBAY_GB", postcode=""):
    """An eBay link -> one of:
        {"url": <link to use>, "note": ""}              a single product already
        {"url": <child link>, "note": "Only ... linked"} the one in-stock child
        {"choose": True, "variations": [...], "error": "..."}  the owner picks
        {"url": url, "note": "", "unchecked": True}      eBay could not be asked
    Never raises."""
    try:
        got = _ebay.get_item(url, app_id, cert_id, marketplace=marketplace,
                             postcode=postcode)
    except Exception as e:                    # api/ebay never raises; belt and braces
        return {"url": url, "note": "", "unchecked": True, "error": str(e)[:160]}
    if got.get("status") != _ebay.GROUP:
        return {"url": url, "note": "", "status": got.get("status")}
    kids = variations(got.get("data") or {}, url)
    one = pick(kids)
    if one:
        others = len(kids) - 1
        return {"url": one["url"], "variation": one,
                "note": ("This eBay listing has %d variations and only %s is in "
                         "stock, so that one was linked (the other %d are out "
                         "of stock)." % (len(kids), one["label"] or "one", others))}
    n_in = sum(1 for c in kids if c.get("in_stock") is True)
    n_unk = sum(1 for c in kids if c.get("in_stock") is None)
    why = ("%d of them are in stock" % n_in if n_in > 1 else
           ("the stock of %d of them is unknown" % n_unk if n_unk else
            "none of them is in stock"))
    return {"choose": True, "variations": kids,
            "error": ("This eBay link is a listing with %d variations and %s, so "
                      "it cannot tell which product you mean. Pick the one you "
                      "buy." % (len(kids), why))}
