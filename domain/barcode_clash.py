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
import time as _time

from listing.barcode import normalize_gtin

# WHAT AMAZON SAID ABOUT A BARCODE, kept for a while. See on_amazon() for why
# this matters: searchCatalogItems allows 2 requests a second per account, and
# the same barcode gets looked at repeatedly -- every time a row is opened,
# every time a preview runs, every time the box is re-read.
#
# Small on purpose. It holds one tuple per barcode actually asked about, which
# is bounded by how many the owner types, not by how many listings exist.
_AMZ_CACHE = {}
_AMZ_TTL = 600.0        # ten minutes; which product owns a code is not volatile


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


def on_amazon(config_path, account_id, marketplace, barcode):
    """Does Amazon's catalogue already hold this barcode? -> dict.

    -> {"checked": bool, "owners": [{asin, brand, title}], "why": ""}

    THE HALF THIS MODULE COULD NOT SEE. Everything above reads the app's OWN
    rows, and the collision happens at Amazon:

        MEASURED, 8 Sep 2026. nestwell_goods/11.96_2Days_B0FM82BDC5 was refused
        with code 8541. Its barcode 4545944574867 belongs to B0H8SYL36V --
        which is jack_uk/5.98_3Days_B0F7RQLCKC, LIVE, a car headrest pillow.
        others_with() returned nothing, because the app's rows do not record
        that barcode against the jack_uk listing. Amazon knew.

    ONE MARKETPLACE, THE LISTING'S OWN. The catalogue search is scoped to the
    marketplace asked about -- measured, the same barcode returns B0H8SYL36V on
    UK and nothing on DE -- so this answers for where the listing is going and
    claims nothing about anywhere else.

    "COULD NOT CHECK" IS NOT "FREE", and that distinction is the whole safety of
    it. Three of the four accounts answer 403 on this API, and a network failure
    is ordinary. `checked` is False in both cases and the caller must say so
    rather than let a silent failure read as a clean barcode -- which is the
    answer that lets a submit go ahead.

    Never raises.
    """
    out = {"checked": False, "owners": [], "why": ""}
    code, kind = normalize_gtin(barcode)
    if not code:
        out["why"] = "not a usable barcode"
        return out

    # ASKED ONCE PER BARCODE, NOT ONCE PER LOOK.
    #
    #     "i am concerned about the rate limits and other limitation i want to
    #      avoid them"
    #
    # Right to be. searchCatalogItems allows 2 requests a second, burst 2, per
    # selling account -- Amazon's published usage plan. So this is never called
    # in a sweep: 86 rows would be 86 calls and 43 seconds of the account's
    # whole quota, starving the price and stock reads that share it.
    #
    # It is called when a barcode is TYPED, debounced, and when ONE listing is
    # looked at. The cache makes re-opening the same row, or typing the same
    # code again, cost nothing. Which product owns a barcode does not change
    # minute to minute, so ten minutes is generous and still fresh enough.
    key = (str(account_id or ""), str(marketplace or "").upper(), code)
    hit = _AMZ_CACHE.get(key)
    if hit and (_time.time() - hit[0]) < _AMZ_TTL:
        return dict(hit[1])

    try:
        import accounts as _acc
        from config import settings as _settings
        from api import amazon_catalog as _cat
        acc = _acc.get_account(_settings.read_raw(config_path) or {},
                               account_id, config_path) or {}
        if not acc:
            out["why"] = "no such account"
            return out
        mkt = str(marketplace or acc.get("default_marketplace") or "UK").upper()
        mid = _acc.marketplace_id(mkt) or ""
        if not mid:
            out["why"] = "no marketplace"
            return out
        res = _cat.owners_of_barcode(_acc.account_creds(acc), mkt, mid,
                                     code, kind or "ean")
    except Exception as e:
        out["why"] = "%s: %s" % (type(e).__name__, str(e)[:120])
        return out

    if res["status"] == _cat.DENIED:
        out["why"] = ("this account cannot read Amazon's catalogue, so the "
                      "barcode could not be checked against it")
        return out
    if res["status"] not in (_cat.OK, _cat.NONE):
        out["why"] = res.get("error") or "Amazon did not answer"
        return out
    out["checked"] = True
    out["owners"] = res["items"]
    # ONLY A REAL ANSWER IS KEPT. Caching a failure would turn one throttle into
    # ten minutes of "could not check" on a barcode that is perfectly readable.
    _AMZ_CACHE[key] = (_time.time(), dict(out))
    return out


def amazon_sentence(found, barcode=""):
    """What to say about what Amazon holds. "" when there is nothing to say.

    Deliberately silent when the barcode is free AND when the check could not
    run -- a screen that announced "we could not check" on every keystroke for
    three of four accounts would be noise about a permission, not about a
    listing. The caller that wants to show the reason has it in `why`.
    """
    if not found or not found.get("checked"):
        return ""
    owners = found.get("owners") or []
    if not owners:
        return ""
    o = owners[0]
    who = o.get("asin") or "another product"
    what = (o.get("title") or "").strip()
    brand = (o.get("brand") or "").strip()
    return ("This barcode%s already belongs to %s%s in Amazon's catalogue%s. "
            "Amazon matches on the barcode, so it will treat this listing as "
            "that product and refuse to create a new one (error 8541). Use a "
            "barcode that is not already in use."
            % ((" " + str(barcode)) if barcode else "",
               who, (" (%s)" % brand) if brand else "",
               (" -- \"%s\"" % what[:70]) if what else ""))


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

