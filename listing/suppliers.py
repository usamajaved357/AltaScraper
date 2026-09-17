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


def from_listing_row(row):
    """Every supplier link stored ON A LISTING ROW, in priority order. -> [(position, url)].

    The listings store keeps supplier 1 as `source_url` and the rest as
    `supplier_2`, `supplier_3`, ... (data/column_map.py). This is the one reader
    of that shape: the generator's input for an uploaded row
    (listing/queued_input.py) and the repricer's backfill
    (domain/source_repo.listing_supplier_urls) both go through it (Rule 12).

    Same rules as urls_from: blanks skipped, one link pasted twice is one
    supplier, and the NUMBER orders them, so supplier_10 comes after supplier_9.
    """
    r = row or {}
    found = []
    first = str(r.get(PRIMARY) or "").strip()
    if first:
        found.append((1, first))
    for k, v in r.items():
        m = _PAT.match(_norm(k))
        if not m:
            continue
        try:
            pos = int(m.group(1))
        except ValueError:
            continue
        u = str(v or "").strip()
        if pos >= 2 and u:
            found.append((pos, u))
    found.sort(key=lambda x: x[0])
    out, seen = [], set()
    for pos, u in found:
        k = u.lower().rstrip("/")
        if k in seen:
            continue
        seen.add(k)
        out.append((pos, u))
    return out


# What a supplement carries that is worth merging. Named rather than "whatever
# keys turned up", so a new key in the fetcher cannot start silently
# participating in a merge nobody designed.
#
# AND THAT NAMED LIST IS WHY THE DRAFTS HAD NO PICTURES.
#
#     "images was supposed to be coming from ebay why my draftws dont have
#      images"
#
# fetch_ebay_supplement returns the eBay photo URLs as `images` (up to ten of
# them), and the generator reads exactly that -- comp_data["images"] =
# ebay_supp["images"][:5] -- code that has worked since July 2026. When this
# merge went in on 7 Sep 2026 it became the thing handing that dict over, and
# `images` was not on this list. So from that day the URLs were fetched from
# eBay and dropped one step later, on every run. Only image_count survived,
# which is why a run could log "7 imgs" over a draft that had none.
#
# The safeguard the paragraph above describes is right, and the answer to it is
# to NAME the key rather than to widen the rule. First non-empty wins applies to
# the photos as it does to everything else, so supplier 1's pictures stand and a
# later seller's are used only when supplier 1 had none -- the owner's own
# priority order, which is the whole point of the ordering.
MERGE_KEYS = ("title", "description", "price", "condition", "category_path",
              "images")
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
    #
    # Except when the URLs themselves came through, where the count is simply
    # how many there are. Keeping the maximum then would restate the old defect
    # in miniature: a count describing pictures this dict is not carrying, which
    # is precisely what allowed a run to log "7 imgs" over a draft that had
    # none.
    merged["image_count"] = len(merged["images"]) if merged.get("images") else imgs
    for k in MERGE_KEYS:
        merged.setdefault(k, [] if k == "images" else "")
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

    ...BUT NOT UNTIL THE LISTING IS ACTUALLY SELLING.

        "these suppliers should be added to the all orders page sources and in
         repricer when the listing goes live, not on draft, on draft the sources
         should stay on the drafts page but should display the handling time,
         the carrier info and delivery time and source price and source name etc
         same as repricer shows it, in the same format"

    So they go in at stage DRAFT. The rows exist -- which is what lets the
    drafts page show the price, the carrier, the delivery window and the
    dispatch days in the repricer's own format, from the repricer's own function
    -- and the order panel and the repricer both ask for LIVE, so they do not
    see them. source_repo.promote_to_live flips them when Amazon confirms the
    listing BUYABLE, carrying every check already taken with them.

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
                                priority=int(pos),
                                stage=_repo.DRAFT)
            n += 1
        except Exception as e:
            if log:
                log("could not enrol supplier %d (%s): %s"
                    % (pos, url[:50], str(e)[:80]))
    return n


def add_missing_row_suppliers(config_path, workspace_id=None, log=None):
    """Enrol the suppliers an UPLOADED draft carried and generation dropped.

    -> {"skus": [...], "added": how many supplier rows}

        "I generated the listings with 3 suppliers (ebay links) in the template
         and the drafts are generated but the repricer has received only 1
         supplier in it, other 2 are not there"

    Until listing/queued_input carried supplier_urls, a row generated from an
    upload enrolled supplier 1 only, while supplier_2 / supplier_3 stayed on the
    listing row. join_live cannot mend it: it reads the row only for a SKU with
    NO supplier at all, and these have one.

    NARROW ON PURPOSE. A source the owner removes is deleted outright
    (source_repo.remove_source), so nothing records that it was ever there, and
    a repair that added "whatever the row names" would put back a supplier he
    took out. So a SKU is repaired only when it carries exactly the signature
    this bug leaves: every supplier recorded for it is one of its own row's
    links, the row's supplier 1 is among them, and at least one of the row's
    later links is missing. The added ones take the stage the recorded ones
    have, so a live listing's suppliers are live and a draft's stay drafts.
    Run once (see run_row_supplier_repair_once), not on a timer.
    """
    from data import db as _db
    from domain import source_repo as _repo
    out = {"skus": [], "added": 0}
    conn = _db.get_db(config_path)
    try:
        q = "SELECT * FROM listings WHERE IFNULL(sku,'')<>''"
        args = []
        if workspace_id:
            q += " AND workspace_id=?"
            args.append(workspace_id)
        rows = [dict(r) for r in conn.execute(q, args)]
    except Exception:
        return out
    for row in rows:
        urls = from_listing_row(row)
        if len(urls) < 2:
            continue
        ws, sku = str(row.get("workspace_id") or ""), str(row.get("sku") or "")
        want = {u.lower().rstrip("/"): (pos, u) for pos, u in urls}
        first_key = urls[0][1].lower().rstrip("/") if urls[0][0] == 1 else None
        try:
            recorded = [dict(r) for r in conn.execute(
                "SELECT marketplace, url, stage FROM sourcing_sources "
                "WHERE workspace_id=? AND sku=?", (ws, sku))]
        except Exception:
            continue
        by_mkt = {}
        for r in recorded:
            by_mkt.setdefault(str(r.get("marketplace") or ""), []).append(r)
        for mkt, recs in by_mkt.items():
            have = {str(r.get("url") or "").strip().lower().rstrip("/") for r in recs}
            if not have or not have.issubset(set(want)):
                continue            # something here the row does not name: hands off
            if first_key is None or first_key not in have:
                continue
            missing = [want[k] for k in want if k not in have]
            if not missing:
                continue
            n = enrol(config_path, ws, mkt, sku, missing, log=log)
            if any(_repo._stage_of(r) == _repo.LIVE for r in recs):
                _repo.promote_to_live(config_path, ws, mkt, sku)
            if n:
                out["added"] += n
                out["skus"].append(sku)
    return out


_REPAIR_MARK = ".supplier_columns_repair_20260917.done"


def run_row_supplier_repair_once(config_path, log=None):
    """add_missing_row_suppliers, exactly once per data directory. -> result or None.

    Once, because the repair cannot tell a supplier that was never enrolled from
    one the owner later removed; after the generator carries every supplier, the
    only drafts with the signature are the ones made before this fix. The mark
    sits beside config.json -- on the persistent disk in production -- and is
    written only after the repair finished, so a crash half way runs it again.
    """
    import os
    base = os.path.dirname(os.path.abspath(str(config_path or "")))
    mark = os.path.join(base, _REPAIR_MARK)
    if os.path.exists(mark):
        return None
    res = add_missing_row_suppliers(config_path, log=log)
    try:
        with open(mark, "w", encoding="utf-8") as fh:
            fh.write("added %d supplier(s) on %d SKU(s)\n%s\n"
                     % (res["added"], len(res["skus"]), "\n".join(res["skus"])))
    except Exception:
        pass
    if log:
        log("supplier repair: added %d supplier(s) on %d SKU(s)"
            % (res["added"], len(res["skus"])))
    return res


def join_live(config_path, workspace_id, marketplace, skus, log=None):
    """Listings Amazon reports as ACTIVE join the repricer, with their suppliers.

    -> {"added": [...], "rejoined": [...], "backfilled": [...], "no_supplier": [...]}

        "new listings didn't joined repricer"
        "i received an order of the sku 12.90_2Days_B0CZ6SWQQY ... couldn't find
         it in repricer, no suppliers, why? i think i am creating listings with
         their suppliers in the sheet, so the suppliers should already be there"

    He was right that they were there. MEASURED on nestwell_goods: that SKU is
    Active in the live catalogue as B0HJ8S7C82, and its own row holds the eBay
    link it was built from -- but it was generated on 13 Aug 2026, and copying a
    row's suppliers into the repricer only began with generation on 7 Sep
    (3cdf2cf). Nothing went back for the listings made before. And even a listing
    that DID have its suppliers recorded never joined, because going live only
    moved their stage (promote_to_live) and never enrolled the SKU.

    CALLED FROM ONE PLACE: domain/live_snapshots.save, which every route to
    Amazon's live catalogue goes through -- the Sync button and the background
    refresher alike. That is where the app LEARNS a listing is live, so it is the
    only place that sees old listings as well as new ones. A hook on the submit
    path would never reach a listing already selling.

    PER SKU, in this order:
      1. no supplier recorded yet -> read them off the listing row and record
         them, through enrol() above so priority and dedupe are the same as at
         generation (Rule 12)
      2. still no supplier -> left out. The repricer prices FROM a supplier; a
         SKU with none has nothing for it to do, and it stays on the Add screen
         for the owner to enrol by hand if he wants it watched anyway.
      3. promote its suppliers to LIVE, then source_repo.auto_enrol -- the one
         rule that decides whether it joins, which never disarms an armed SKU and
         never re-adds one the owner removed.

    DRY RUN, ALWAYS, which is what makes an automatic join safe: nothing moves a
    price until a floor is set and the SKU is armed by hand. Never raises -- a
    catalogue that saved must not be undone by the bookkeeping after it.
    """
    from domain import source_repo as _repo
    out = {"added": [], "rejoined": [], "backfilled": [], "no_supplier": []}
    for sku in (skus or []):
        s = str(sku or "").strip()
        if not s:
            continue
        try:
            if not _repo.has_sources(config_path, workspace_id, marketplace, s):
                urls = _repo.listing_supplier_urls(config_path, workspace_id, s)
                if urls and enrol(config_path, workspace_id, marketplace, s,
                                  urls, log=log):
                    out["backfilled"].append(s)
            if not _repo.has_sources(config_path, workspace_id, marketplace, s):
                out["no_supplier"].append(s)
                continue
            _repo.promote_to_live(config_path, workspace_id, marketplace, s)
            got = _repo.auto_enrol(config_path, workspace_id, marketplace, s)
            if got == _repo.ADDED:
                out["added"].append(s)
            elif got == _repo.REJOINED:
                out["rejoined"].append(s)
        except Exception as e:
            if log:
                log("could not join %s to the repricer: %s" % (s, str(e)[:120]))
    return out
