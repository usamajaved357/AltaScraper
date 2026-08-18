"""domain/source_link.py -- where a SKU was sourced from, in ONE place.

To track what a listing really costs, the repricer needs its supplier link. That
link is not missing: the app CREATED these listings from a source, and wrote it
down at the time. It is just written down in two places, because two different
routes into the app record it:

  listings.source_url         the generator's own record of the page it built
                              this listing from. Keyed by SKU, and failing that
                              by the competitor ASIN in the SKU.
  input_products.ebay_url     the import queue's copy, keyed by ASIN.

Asking both, in that order, is the difference between enrolling 53 SKUs with
their real suppliers attached and enrolling 53 empty rows for someone to paste
links into by hand.

WHAT COUNTS AS USABLE
Only a link a fetcher can actually read. An amazon.co.uk/dp/... URL is a
COMPETITOR REFERENCE, not a supplier -- it is where the product data came from,
never where the stock is bought (CLAUDE.md Rule 1) -- so it is refused here
rather than enrolled as a source that would answer "could not tell" for ever.
Same for a bare eBay search or shop link with no item number in it.

Nothing here writes anything. It answers a question; the caller decides.
"""
import re

from api import ebay as _ebay

# Hosts we know are a REFERENCE rather than a supplier. Listed rather than
# inferred, because "not eBay" is not the same as "not a supplier" -- an html
# supplier page is perfectly valid, and the scraper reads those.
_NOT_SUPPLIERS = ("amazon.com", "amazon.co.uk", "amazon.de", "amazon.fr",
                  "amazon.it", "amazon.es", "amazon.nl", "amazon.se",
                  "amazon.pl", "amazon.ca", "amazon.com.au", "amzn.to")


def classify(url):
    """(kind, why) for a candidate link. kind is 'ebay', 'html', or ''.

    The reason is written for the person reading a bulk-enrol report, who needs
    to know whether to go and find a link or whether there was never going to be
    one.
    """
    u = str(url or "").strip()
    if not u:
        return "", "no source link was recorded for this listing"
    low = u.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        return "", "the recorded source is not a web address"
    host = low.split("/")[2] if "//" in low else ""
    if any(h in host for h in _NOT_SUPPLIERS):
        return "", ("the recorded source is an Amazon page -- that is the "
                    "competitor this listing was modelled on, not where the "
                    "stock is bought")
    if "ebay." in host:
        if not _ebay.item_id_from_url(u):
            return "", ("that eBay link has no item number in it, so there is "
                        "nothing to price from")
        return "ebay", ""
    return "html", ""


def _asin_from_sku(sku):
    """The competitor ASIN the generator wrote into the SKU, or ''.

    Format is {cost}_{N}Days_{ASIN} -- see build_sku(). Rule 1: this is the
    COMPETITOR's ASIN and is used here only to look a row up, never to identify
    our own listing.
    """
    m = re.search(r"_([A-Z0-9]{10})$", str(sku or "").strip().upper())
    return m.group(1) if m else ""


def for_sku(config_path, workspace_id, sku):
    """{"url", "kind", "where", "why"} -- the supplier link for one SKU.

    url is "" when there is nothing usable, and `why` then says which of the
    several quite different reasons applies.
    """
    from data import db as _db
    conn = _db.get_db(config_path)
    sku = str(sku or "").strip()
    asin = _asin_from_sku(sku)
    tried = []

    def _take(url, where):
        kind, why = classify(url)
        if kind:
            return {"url": str(url).strip(), "kind": kind, "where": where, "why": ""}
        if url:
            tried.append("%s (%s)" % (where, why))
        return None

    # 1. The generator's own record, by SKU. The most specific answer there is.
    try:
        r = conn.execute("SELECT source_url FROM listings WHERE workspace_id=? AND sku=? "
                         "ORDER BY id DESC LIMIT 1", (workspace_id, sku)).fetchone()
        if r:
            got = _take(r["source_url"], "the listing's own record")
            if got:
                return got
    except Exception:
        pass

    # 2. The same table by competitor ASIN -- catches a SKU that was re-created
    #    or renamed, where the product is the same but the row is not.
    if asin:
        try:
            r = conn.execute("SELECT source_url FROM listings WHERE workspace_id=? AND "
                             "competitor_asin=? AND IFNULL(source_url,'')<>'' "
                             "ORDER BY id DESC LIMIT 1", (workspace_id, asin)).fetchone()
            if r:
                got = _take(r["source_url"], "another listing for the same product")
                if got:
                    return got
        except Exception:
            pass

    # 3. The import queue, by ASIN, and SCOPED TO THIS WORKSPACE. Two accounts
    #    can both be watching the same competitor ASIN with different suppliers,
    #    and an unscoped lookup would hand one account the other's supplier --
    #    then price from it, quietly, for ever. The column is matched directly
    #    rather than by searching the amazon_url text, which would also match an
    #    ASIN that merely appeared somewhere in a query string.
    if asin:
        try:
            r = conn.execute("SELECT ebay_url FROM input_products WHERE workspace_id=? "
                             "AND UPPER(IFNULL(competitor_asin,''))=? "
                             "AND IFNULL(ebay_url,'')<>'' "
                             "ORDER BY id DESC LIMIT 1",
                             (workspace_id, asin)).fetchone()
            if r:
                got = _take(r["ebay_url"], "the import queue")
                if got:
                    return got
        except Exception:
            pass

    # The same link is often recorded in all three places, so all three fail for
    # the same reason. Saying it once is the report; saying it three times is
    # noise that hides the SKUs whose problem is different.
    seen, uniq = set(), []
    for t in tried:
        why = t[t.find("(") + 1:t.rfind(")")] if "(" in t else t
        if why in seen:
            continue
        seen.add(why)
        uniq.append(t)
    return {"url": "", "kind": "", "where": "",
            "why": ("; ".join(uniq) if uniq
                    else "no source link was recorded for this listing")}


# ---- what to CALL a supplier link -------------------------------------------

_ITEM_RE = re.compile(r"/itm/(?:[^/?#]*?/)?(\d{9,15})")


def display_name(url, seller="", label=""):
    """The name to put on screen for a supplier link. Never the raw URL.

        "i do not want the full ebay link just display the name of the seller
         and the link attached to it so i can click on the seller name to open
         the product link"

    A raw eBay URL is about 120 characters of tracking parameters. It told the
    reader nothing, and it was the widest thing in the app: MEASURED, the
    supplier column of the order panel was 5,523px wide on a 390px screen
    because a grid column will not shrink below its longest unbreakable word.

    In order of what is actually known about the link:

      1. a label somebody typed against it in the supplier template -- their own
         name for a supplier beats anything derived from a URL;
      2. the seller name the supplier published (eBay's seller.username), which
         is the name printed on the listing itself and can be checked;
      3. the site, and the item number when the URL carries one. Honest about
         being a fallback: it says where, not who.

    Nothing is invented. An unrecognisable URL returns "supplier link", which is
    true, rather than a guess dressed as a seller name.
    """
    label = str(label or "").strip()
    # A "label" that is just the URL again is not a label. That is what the old
    # `label or url` fallback wrote into the field, so it is still in the data.
    if label and not label.lower().startswith(("http://", "https://")):
        return label

    seller = str(seller or "").strip()
    if seller:
        return seller

    url = str(url or "").strip()
    if not url:
        return "supplier link"

    host = url.split("//", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    host = host.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return "supplier link"

    m = _ITEM_RE.search(url)
    return "%s · item %s" % (host, m.group(1)) if m else host
