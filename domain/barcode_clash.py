"""domain/barcode_clash.py -- is this barcode already on another listing?

    "maybe i used the barcode of my another listing, so the app should tell me"

He had. MEASURED on his own data, 26 Aug 2026: EAN 4545644574860 was on
jack_uk/8.99_5Days_B09BNLQG2Q, which is LIVE, and on
nestwell_goods/11.59_3Days_B0DNJH3CRX, which he had just submitted. Amazon
matched the barcode to the live one's ASIN (B0H8Q3VMPD), saw the second
listing's data was different, and refused to create it:

    "The standard product ids (such as UPC, ISBN, EAN, or JAN codes) provided
     matches the ASIN B0H8Q3VMPD, but some of the [data is different]"
    "Your offer to the SKU cannot be added because the product is not in the
     catalogue."

SIXTEEN barcodes in the store are on more than one listing, one of them on
three. Every one will fail the same way when submitted, and until now nothing
looked.

WHY THIS CANNOT BE A STRING COMPARE. listing/barcode.py exists because the same
barcode is written differently everywhere -- 4545644574860 and 04545644574860
are the same code, one padded to 14 digits. Comparing the raw text would miss
exactly the pair that collides at Amazon, so every value goes through
normalize_gtin first. That module stays the only thing that knows how a barcode
is written (CLAUDE.md Rule 12); this one only asks who else has it.

ACROSS ACCOUNTS, DELIBERATELY. Amazon's catalogue is one catalogue: a barcode
used by Jack Reacherd is taken as far as Nestwell Goods is concerned. Scoping
this to one workspace would miss the case that actually happened.
"""
from listing.barcode import normalize_gtin


def _code(raw):
    """The barcode as Amazon would see it, or "" if it is not a usable one.

    normalize_gtin, NOT gtin_digits. Digits alone are not the code: a GTIN-14
    is a 13-digit barcode with a packaging indicator bolted on the front, so
    04545644574860 and 4545644574860 are the SAME code written two ways and
    compare as different digit strings. Measured -- the padded form found none
    of the two listings that carry it until this went through normalize_gtin,
    which is exactly the collision this module exists to catch.
    """
    return (normalize_gtin(raw) or ("", ""))[0]

# A status that means the listing is on Amazon and holds the barcode against
# any other listing that tries to use it.
_LIVE = ("LIVE", "SUBMITTED", "ACTIVE")


def _rows(config_path):
    from data import db as _db
    try:
        return _db.get_db(config_path).execute(
            "SELECT workspace_id, sku, upc, status, title FROM listings "
            "WHERE upc IS NOT NULL AND TRIM(upc) <> ''").fetchall()
    except Exception:
        return []


def others_with(config_path, barcode, exclude_workspace=None, exclude_sku=None):
    """Every OTHER listing carrying this barcode. [] when it is unused.

    Returns dicts with workspace_id, sku, status, title and `live` -- whether
    that listing is the one Amazon would consider the owner of the code.
    """
    want = _code(barcode)
    if not want:
        return []
    out = []
    for r in _rows(config_path):
        if _code(r["upc"]) != want:
            continue
        if (exclude_sku and str(r["sku"]) == str(exclude_sku)
                and (not exclude_workspace
                     or str(r["workspace_id"]) == str(exclude_workspace))):
            continue
        st = str(r["status"] or "").strip().upper()
        out.append({"workspace_id": r["workspace_id"], "sku": r["sku"],
                    "status": st, "title": r["title"] or "",
                    "live": st in _LIVE})
    # The live one first: it is the listing Amazon will say the barcode
    # belongs to, and therefore the one the reader has to deal with.
    out.sort(key=lambda x: (not x["live"], x["workspace_id"], x["sku"]))
    return out


def sentence(clashes, barcode=""):
    """What to tell somebody about a clash. "" when there is nothing to say."""
    if not clashes:
        return ""
    live = [c for c in clashes if c["live"]]
    first = (live or clashes)[0]
    who = "%s / %s" % (first["workspace_id"], first["sku"])
    if live:
        return ("This barcode%s is already on %s, which is on Amazon. Amazon "
                "will match this listing to that product and refuse to create "
                "a new one. Use a different barcode, or apply for a GTIN "
                "exemption."
                % ((" " + str(barcode)) if barcode else "", who))
    return ("This barcode%s is also on %s. Only one listing can carry a "
            "barcode -- whichever reaches Amazon first will own it."
            % ((" " + str(barcode)) if barcode else "", who))


def scan(config_path):
    """Every barcode used by more than one listing. [{code, listings:[...]}].

    For a screen that wants to show the whole problem at once rather than one
    listing at a time -- sixteen of these existed before anything checked.
    """
    by_code = {}
    for r in _rows(config_path):
        d = _code(r["upc"])
        if not d:
            continue
        st = str(r["status"] or "").strip().upper()
        by_code.setdefault(d, []).append(
            {"workspace_id": r["workspace_id"], "sku": r["sku"],
             "status": st, "title": r["title"] or "", "live": st in _LIVE})
    out = [{"code": c, "listings": v, "count": len(v)}
           for c, v in by_code.items() if len(v) > 1]
    out.sort(key=lambda x: (-x["count"], x["code"]))
    return out

