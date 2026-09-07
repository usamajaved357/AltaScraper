"""listing/adopt.py -- take a LIVE listing into a workspace so it can be edited.

THE HOLE THIS FILLS

    "i am trying to make changes in the live listing, ASIN B0H8TFYNB9
     SKU 14.99_2Days_B09V19CTQ5 ... it says save failed, no skus in this
     workspace and i told you that i have mee too listing this so i should be
     able to add data atleast"

Two different sets, and the app was treating them as one:

    what the app has MADE   the `listings` table -- rows the generator wrote
    what the account SELLS  the live snapshot -- what Amazon says is listed

Every editor in the app writes to the first. A me-too listing is only ever in
the second, so every field on the drawer refused to save, with an error that
reads like a bug and is actually a true statement about an empty table.

MEASURED ON THE OWNER'S OWN DATA, 7 Sep 2026:

    listings row      jack_uk ONLY
    live on Amazon    jack_uk/UK AND nestwell_goods/UK AND nestwell_goods/IE
    orders            nestwell_goods, 5 of them

The same SKU really is live on two accounts -- that is what a me-too listing is,
and [[skus-are-not-unique-across-accounts]] records that a SKU never identifies
an account here. So viewing nestwell_goods and editing found nothing, because
the row belongs to jack_uk.

WHY /edit MUST NOT SIMPLY FALL BACK TO THE OTHER ACCOUNT'S ROW. It would edit
the OTHER company's listing from this company's screen. routes/listing_routes
already refuses that deliberately and says why. The answer is not to relax the
scope; it is to give this workspace a row of its own.

WHAT IS SEEDED, AND FROM WHERE

Amazon's own snapshot for THAT account and marketplace -- title, brand, price,
product type. Not the other account's row: two accounts selling the same product
have their own titles, their own prices and their own compliance answers, and
copying one into the other would put a neighbour's data under this brand.

    THE ASIN IS OURS, AND IS NOT WRITTEN TO competitor_asin (CLAUDE.md Rule 1).
    B0H8TFYNB9 is the live listing. B09V19CTQ5 -- the tail of the SKU -- is the
    COMPETITOR the listing was researched from. The column is named for the
    second and must never hold the first, or every screen that reads it starts
    treating our own product as the competitor to price against.

The row is created as a record of something that already exists on Amazon. It
sends nothing: adopting is a local act, and the listing is live either way.
"""

# The columns a seeded row fills. Everything else is left empty for the owner to
# fill in, which is the point -- an adopted row is a place to put data, not a
# claim to have it.
SEEDED = ("sku", "competitor_asin", "title", "brand", "our_price",
          "product_type", "status", "listing_marketplace", "notes")


def competitor_asin_from_sku(sku):
    """The ASIN the SKU was built from, or "".

    The generator's SKU is {cost}_{N}Days_{COMPETITOR_ASIN} -- see build_sku.
    The tail is a COMPETITOR reference used at generation time and never our own
    listing (Rule 1), so it is the only ASIN that may go in competitor_asin.

    Returns "" for a hand-named SKU, which has no ASIN in it and must not be
    given one.
    """
    parts = str(sku or "").strip().split("_")
    if len(parts) < 3:
        return ""
    tail = parts[-1].strip().upper()
    # An Amazon ASIN is ten characters, letters and digits, and conventionally
    # starts with B. Anything else is part of a name and is not an ASIN.
    if len(tail) == 10 and tail.isalnum() and tail[0].isalpha():
        return tail
    return ""


def live_item(config_path, workspace_id, marketplace, sku):
    """The snapshot's own record of this SKU on this account, or None."""
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, workspace_id, marketplace) or {}
    except Exception:
        return None
    want = str(sku or "").strip().upper()
    if not want:
        return None
    for it in (rec.get("items") or []):
        if str(it.get("sku") or "").strip().upper() == want:
            return it
    return None


def can_adopt(config_path, workspace_id, marketplace, sku):
    """(bool, why). Is this SKU live on THIS account, so a row may be made?

    The gate is deliberately narrow: the SKU has to be in this workspace's own
    live snapshot. Without that check this becomes "create a row for anything
    anybody types", which is how a typo becomes a listing.
    """
    it = live_item(config_path, workspace_id, marketplace, sku)
    if it:
        return True, ""
    return False, (
        "This SKU is not in %s's live catalogue for %s, so there is nothing to "
        "take in. If it really is listed there, sync the live catalogue first — "
        "the app can only adopt a listing Amazon has told it about."
        % (workspace_id or "this account", marketplace or "this marketplace"))


def seed_row(config_path, workspace_id, marketplace, sku, headers):
    """The row to write, as a list matching `headers`. None when it cannot.

    Values come from Amazon's snapshot for this account. Anything the snapshot
    does not carry is left EMPTY rather than guessed -- an adopted row exists so
    the owner can fill it in, and a seeded guess is indistinguishable from
    something he typed.
    """
    it = live_item(config_path, workspace_id, marketplace, sku)
    if not it:
        return None

    vals = {
        "sku": str(sku or "").strip(),
        # OURS IS NOT WRITTEN HERE. Only the competitor reference out of the
        # SKU's own tail -- see the module note and Rule 1.
        "competitor_asin": competitor_asin_from_sku(sku),
        "title": str(it.get("title") or ""),
        "brand": str(it.get("brand") or ""),
        "our_price": ("" if it.get("price") in (None, "")
                      else str(it.get("price"))),
        "product_type": str(it.get("product_type") or ""),
        # LIVE, because it is: Amazon is showing it right now. Marking it draft
        # would invite somebody to submit a listing that already exists.
        "status": "LIVE",
        "listing_marketplace": str(marketplace or "").upper(),
        "notes": ("Taken into this workspace from the live catalogue on Amazon, "
                  "so its details can be edited here. Nothing was sent to "
                  "Amazon."),
    }
    out = []
    for h in headers:
        out.append(vals.get(_col_for(h), ""))
    return out


# The sheet-style header names the app writes, mapped back to the column names
# used above. data/column_map owns this mapping for the app at large; only the
# handful this file seeds are needed here, and they are looked up through that
# module so the two cannot disagree (Rule 12).
def _col_for(header):
    try:
        from data import column_map as _cm
        got = _cm.col_for_header(header)
        if got:
            return got
    except Exception:
        pass
    return str(header or "").strip().lower().replace(" ", "_")


def adopt(config_path, ws, workspace_id, marketplace, sku):
    """Create the row. Returns (ok, why).

    Never raises: this runs inside a save the owner is waiting on, and a failure
    to adopt must report itself rather than become a 500 on an edit.
    """
    from listing import repo as _repo

    ok, why = can_adopt(config_path, workspace_id, marketplace, sku)
    if not ok:
        return False, why

    try:
        headers = _repo.read_headers(ws)
    except Exception as e:
        return False, "could not read the listing columns: %s" % str(e)[:120]
    if not headers:
        return False, "this workspace has no listing columns to write into"

    # ALREADY THERE? Then this is a no-op rather than a second row. Two rows
    # with one SKU is worse than none: every reader takes the first and the
    # edits land on whichever that happens to be.
    try:
        found = _repo.locate(ws, sku, headers=headers)
        if found.ok:
            return True, "already in this workspace"
    except Exception:
        pass

    row = seed_row(config_path, workspace_id, marketplace, sku, headers)
    if row is None:
        return False, why or "nothing in the live catalogue to seed a row from"
    try:
        wrote = _repo.write_row(ws, row,
                                comp_asin=competitor_asin_from_sku(sku))
    except Exception as e:
        return False, "could not write the row: %s" % str(e)[:120]
    if not wrote:
        return False, "the row could not be written"
    return True, ""
