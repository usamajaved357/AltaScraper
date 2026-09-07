"""listing/suppliers.py -- more than one supplier for the same product.

    "right now we use 1 supplier from ebay to create the listing copy but i want
     to add more then 1 supplier from ebay, they all sell same item so some
     suppliers may have less listing optimized and the 2nd will have some
     attributes the first missed, the third ine will have some more attributes
     the first two missed, so i can mention in the sheet supplier 1, which is
     prioritized for info then supplier 2 which is prioritized at the second
     number and so on"

THE PROBLEM THIS SOLVES. One eBay seller's listing is one seller's idea of what
matters. A cheap listing may carry the price and nothing else; a careful one may
have twelve item specifics and no dimensions. Generating from a single link
means every gap in that one listing becomes a gap in the Amazon listing, and the
information usually exists -- on the next seller's page for the same product.

FIRST NON-EMPTY WINS, AND NOTHING IS EVER OVERWRITTEN. Supplier 1 is the
owner's own ordering, so its value stands wherever it has one. Supplier 2 fills
only what supplier 1 left blank, supplier 3 what the first two both left blank.
A later supplier can ADD a field and can never CHANGE one.

That direction matters and is not arbitrary. These are different sellers
describing the same product, and they disagree -- about the title, the colour,
sometimes the size. Letting a later one overwrite would mean the listing's
content changed depending on which supplier happened to answer fastest, and the
owner's priority order would be decoration.

WHY THIS IS ITS OWN FILE. CLAUDE.md Rule 7: no new logic in
amazon_listing_generator.py, which is being broken up. The generator calls in
here; the merging, the column discovery and the enrolment all live together
where they can be tested without running a generation.
"""
import re

# The first supplier is the column the sheet has always had. The rest are found
# by pattern, so a sixth supplier is a new column and no code change.
PRIMARY = "source_url"

# Both spellings, because the owner described one and the sheet already uses the
# other, and guessing which he will type is how a link is silently ignored:
#     "Supplier 2", "supplier_2", "Supplier2"
#     "Source URL 2", "source_url_2"
# The number is what orders them, not the position of the column in the sheet --
# a column inserted in the middle must not silently re-prioritise the rest.
_PAT = re.compile(r"^(?:supplier|source[_\s]*url|ebay[_\s]*link)[_\s]*(\d+)$")


def _norm(h):
    return str(h or "").strip().lower().replace(" ", "_")


def supplier_columns(headers):
    """The supplier columns present, in the owner's priority order.

    -> [(position, column_name)], position 1 first.

    The primary column is position 1 whatever it is called. A numbered column
    takes the number it carries, so "Supplier 2" is second even if it happens to
    sit before "Supplier 3" was inserted.
    """
    out, seen = [], set()
    for h in (headers or []):
        n = _norm(h)
        if not n or n in seen:
            continue
        seen.add(n)
        if n in (PRIMARY, "ebay_link", "ebay_url"):
            out.append((1, h))
            continue
        m = _PAT.match(n)
        if not m:
            continue
        try:
            pos = int(m.group(1))
        except ValueError:
            continue
        # "Supplier 1" and "Source URL" are the same slot. Keeping both would
        # fetch the same seller twice and score it twice.
        if pos >= 1:
            out.append((pos, h))
    out.sort(key=lambda x: (x[0], _norm(x[1])))
    # One column per position, the first seen winning, so a sheet carrying both
    # "Source URL" and "Supplier 1" does not produce two slot ones.
    got, final = set(), []
    for pos, name in out:
        if pos in got:
            continue
        got.add(pos)
        final.append((pos, name))
    return final


def urls_from(item, headers=None):
    """Every supplier URL on one row, in priority order. -> [(position, url)].

    `item` is the row already keyed by normalised header, which is the shape
    read_products builds. Blanks are skipped rather than kept as empty slots: a
    sheet with supplier 1 and supplier 3 filled in should fetch two suppliers,
    not two and a hole.
    """
    out, seen = [], set()
    cols = supplier_columns(headers) if headers else None
    if cols is None:
        # No headers to work from -- take the keys the row itself carries.
        cols = supplier_columns(list(item.keys()))
    for pos, name in cols:
        url = str(item.get(_norm(name), "") or "").strip()
        if not url:
            continue
        # THE SAME LINK TWICE IS ONE SUPPLIER. Pasting the same URL into two
        # columns is an ordinary slip, and fetching it twice would cost a second
        # request to learn nothing.
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append((pos, url))
    return out


# What a supplement carries that is worth merging. Named rather than "whatever
# keys turned up", so a new key in the fetcher cannot start silently
# participating in a merge nobody designed.
MERGE_KEYS = ("title", "description", "price", "condition", "category_path")
DICT_KEYS = ("item_specifics",)
NUM_KEYS = ("image_count",)


def _empty(v):
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (dict, list, tuple)):
        return not v
    return False


def merge(parts):
    """Merge supplier supplements in priority order. -> (merged, provenance).

    `parts` is [(position, url, supplement)], best first.

    FIRST NON-EMPTY WINS for every plain field. For item_specifics -- which is
    the whole point of asking a second seller -- the merge is PER SPEC: supplier
    1's "Colour" stands, and supplier 2's "Material" is added because supplier 1
    had none. That is where the owner's "the 2nd will have some attributes the
    first missed" actually lives.

    `provenance` says which supplier each value came from, so the drawer can
    show it and a wrong value can be traced to the seller it came from rather
    than to "the app".
    """
    merged, prov = {}, {}
    spec_prov = {}
    specs = {}
    imgs = 0
    for pos, url, supp in (parts or []):
        if not isinstance(supp, dict):
            continue
        for k in MERGE_KEYS:
            if _empty(merged.get(k)) and not _empty(supp.get(k)):
                merged[k] = supp[k]
                prov[k] = {"supplier": pos, "url": url}
        for name, val in (supp.get("item_specifics") or {}).items():
            n = str(name or "").strip()
            if not n or _empty(val):
                continue
            if n in specs:
                continue                      # an earlier supplier already said
            specs[n] = val
            spec_prov[n] = {"supplier": pos, "url": url}
        try:
            imgs = max(imgs, int(supp.get("image_count") or 0))
        except (TypeError, ValueError):
            pass
    merged["item_specifics"] = specs
    # THE MOST IMAGES ANY ONE SUPPLIER HAD, not the sum: they are photographs of
    # the same product, and adding them would claim a picture count nobody has.
    merged["image_count"] = imgs
    for k in MERGE_KEYS:
        merged.setdefault(k, "")
    prov["item_specifics"] = spec_prov
    return merged, prov


# What a listing needs before another supplier is worth asking. Deliberately
# short: these are the fields a thin eBay listing actually omits, and the ones
# whose absence shows on the Amazon listing.
GAP_KEYS = ("title", "description", "price", "condition")

# Below this many item specifics, another seller is likely to add some. Above
# it, a second fetch usually returns things the first already said. Chosen as
# the point where a listing stops looking sparse rather than measured -- if it
# turns out to be wrong the cost is one extra fetch, not a wrong listing.
GAP_SPECS = 6


def has_gap(parts):
    """Is anything still missing after merging what has been fetched so far?

    THE REASON LATER SUPPLIERS ARE NOT ALWAYS FETCHED. Three suppliers on every
    row means three eBay calls per listing to answer a question the first seller
    usually already answered, and generation is already the slowest thing this
    app does. So the next supplier is asked only when there is something left
    for it to fill.

    Returns True when there is nothing yet -- an empty list has every gap.
    """
    if not parts:
        return True
    merged, _prov = merge(parts)
    for k in GAP_KEYS:
        if _empty(merged.get(k)):
            return True
    if len(merged.get("item_specifics") or {}) < GAP_SPECS:
        return True
    if not merged.get("image_count"):
        return True
    return False


def summary(parts, merged):
    """One line per supplier saying what it contributed. For the run log.

    Worth printing: with one supplier a blank field is just blank, but with
    three the interesting fact is WHICH one filled a gap -- that is how the
    owner learns whether a supplier is worth keeping in the sheet at all.
    """
    lines = []
    for pos, url, supp in (parts or []):
        if not isinstance(supp, dict) or not supp.get("title"):
            lines.append("  supplier %d: no usable data (%s)" % (pos, url[:60]))
            continue
        lines.append("  supplier %d: %d spec(s), %d image(s) -- %s"
                     % (pos, len(supp.get("item_specifics") or {}),
                        int(supp.get("image_count") or 0),
                        str(supp.get("title") or "")[:50]))
    return lines


def enrol(config_path, workspace_id, marketplace, sku, urls, log=None):
    """Put every supplier into the repricer's source list. -> how many.

        "when i add suppliers for draft creation, enroll those suppliers
         automatically in all orders section where we see the available
         suppliers and also in the repricer where we see the available
         suppliers of the asin"

    Both of those screens read domain/source_repo, so there is one thing to do
    and both get it (Rule 12). The sheet's order becomes the source PRIORITY, so
    the repricer prefers the same supplier the listing was written from.

    ensure_source rather than add_source: generating the same row twice must not
    leave two copies of one supplier, which would then be checked twice and
    shown twice.

    NEVER FATAL. This runs at the end of a generation that has already cost
    model calls and API quota; a failure to enrol must not lose the listing. It
    is reported and the row stands.
    """
    if not sku or not urls:
        return 0
    try:
        from domain import source_repo as _repo
    except Exception:
        return 0
    n = 0
    for pos, url in urls:
        try:
            _repo.ensure_source(config_path, workspace_id, marketplace, sku, url,
                                kind="ebay",
                                label="Supplier %d" % pos,
                                priority=int(pos))
            n += 1
        except Exception as e:
            if log:
                log("could not enrol supplier %d (%s): %s"
                    % (pos, url[:50], str(e)[:80]))
    return n
