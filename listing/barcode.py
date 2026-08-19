"""listing/barcode.py — the ONE place that decides what a barcode IS.

PLAIN ENGLISH
-------------
A barcode number can arrive in several shapes. The shop's own label, a supplier
export and Amazon all write the SAME barcode differently:

    4545944574867     13 digits  -- an EAN-13, the normal European retail barcode
    04545944574867    14 digits  -- the SAME barcode, padded to 14 with a zero
    045459 445748 67  with spaces -- the same again, printed for humans

Amazon will only accept it in the exact shape it expects. If we hand over the
14-digit padded form and label it a "upc", Amazon rejects it -- and because the
number really is valid, the auto-fix loop keeps resubmitting the same rejected
value forever. That is what stalled SKU 11.96_2Days_B0FM82BDC5 on
"Amazon still rejects: 04545944574867".

WHAT THIS MODULE DOES
---------------------
Takes whatever was typed in the "Barcode / GTIN" box and works out two things:
the clean number to send, and what to call it. The padded 14-digit form is
converted back to the 13-digit EAN it actually is.

WHY IT IS ITS OWN FILE (CLAUDE.md §12)
--------------------------------------
This decision used to be made in three separate places, each with its own copy
of `"ean" if len(barcode) == 13 else "upc"`. Fixing one left the others broken.
Every caller now uses these functions -- there is no second implementation.

TYPE NAMES: only "ean" and "upc" are produced. Both are already proven in
production on this account, so no new value is being guessed at (CLAUDE.md §4).
"""
import re

_NON_DIGIT = re.compile(r"\D")

# Barcode lengths that are real retail barcodes, and what Amazon calls each.
# 8 = EAN-8 (small packs), 12 = UPC-A (US), 13 = EAN-13 (UK/EU).
_LENGTH_TO_TYPE = {13: "ean", 12: "upc", 8: "ean"}


def gtin_digits(raw) -> str:
    """Strip everything that is not a digit.

    Handles spaces and hyphens from hand-typed values, and the stray leading
    glyph a cp1252-decoded supplier export can prepend to a barcode.
    """
    if not raw:
        return ""
    return _NON_DIGIT.sub("", str(raw))


def normalize_gtin(raw):
    """Return (value, type) ready to send to Amazon.

    type is "ean", "upc", or "" when the value is not a usable retail barcode.
    A caller that gets ("", "") has NO barcode and must claim the GTIN
    exemption rather than send anything (CLAUDE.md §1 -- never send a fake,
    placeholder or reshaped-until-it-fits barcode).

        >>> normalize_gtin("04545944574867")   # 14-digit padded form
        ('4545944574867', 'ean')
        >>> normalize_gtin("4545944574867")
        ('4545944574867', 'ean')
        >>> normalize_gtin("045459 445748 67")
        ('4545944574867', 'ean')
        >>> normalize_gtin("012345678905")
        ('012345678905', 'upc')
        >>> normalize_gtin("")
        ('', '')
    """
    d = gtin_digits(raw)

    # A GTIN-14 is a 13-digit retail barcode with a one-digit "packaging
    # indicator" bolted on the front. When that indicator is 0 the number is a
    # plain EAN-13 wearing a hat -- take the hat off. A LEADING NON-ZERO means
    # a genuine case/carton code, which is NOT the single-unit barcode Amazon
    # wants, so it is left over-length and rejected below.
    while len(d) > 13 and d.startswith("0"):
        d = d[1:]

    if len(d) not in _LENGTH_TO_TYPE:
        return ("", "")
    # LENGTH WAS THE ONLY TEST, and the docstring above already promised more
    # than that -- "never send a fake, placeholder or reshaped-until-it-fits
    # barcode". MEASURED: "000000000000" passed this function and would have
    # gone to Amazon as a UPC.
    if _is_placeholder(d) or not _check_digit_ok(d):
        return ("", "")
    return (d, _LENGTH_TO_TYPE[len(d)])


def _is_placeholder(d):
    """Numbers nobody printed on a product.

    All one digit, or a straight run of them. These are what somebody types to
    get past a required field, and CLAUDE.md Rule 1 is explicit that a
    placeholder must never be sent. A checksum does NOT catch them: both
    "000000000000" and "123456789012" have a valid check digit.
    """
    if len(set(d)) == 1:
        return True
    asc = "01234567890123456789"
    desc = asc[::-1]
    return d in asc or d in desc


def _check_digit_ok(d):
    """The GS1 mod-10 check digit -- the thing that makes a barcode a barcode.

    Weights alternate 3 and 1 from the rightmost body digit. An invented number
    fails this about nine times in ten, which is most of the protection Rule 1
    is asking for.

    MEASURED AGAINST THE REAL DATA before being switched on, because a check
    that rejected the owner's genuine purchased EANs would be a far worse bug
    than the one being fixed. Of 283 barcodes stored across every account, 274
    pass and 2 fail -- and a barcode with a wrong check digit is not a valid
    barcode: Amazon rejects it, which is exactly the loop the comment in
    build_api_attributes describes as "auto-fix resubmitting the same number
    forever". Catching it here turns that loop into one clear sentence.
    """
    body, check = d[:-1], int(d[-1])
    total = sum(int(ch) * (3 if i % 2 == 0 else 1)
                for i, ch in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def gtin_or_reason(raw):
    """Same as normalize_gtin, plus a plain-English reason when unusable.

    Returns (value, type, reason). reason is "" on success. Callers use it to
    tell the user WHY a barcode they can see in the box was not sent, instead
    of silently falling back to the GTIN exemption.
    """
    value, typ = normalize_gtin(raw)
    if value:
        return value, typ, ""
    digits = gtin_digits(raw)
    if not digits:
        return "", "", "no digits in the Barcode / GTIN box"
    # WHICH fault it was. "Not a retail barcode" covers three very different
    # situations and only one of them is worth going and looking at:
    #   wrong length  -> probably the wrong field was pasted
    #   placeholder   -> somebody typed something to get past a required box
    #   bad check     -> a real barcode with a typo in it, and the ONE case
    #                    where going back to the invoice will fix it
    trimmed = digits
    while len(trimmed) > 13 and trimmed.startswith("0"):
        trimmed = trimmed[1:]
    if len(trimmed) in _LENGTH_TO_TYPE:
        if _is_placeholder(trimmed):
            return "", "", (f"'{trimmed}' is a placeholder, not a barcode "
                            f"anybody printed on a product")
        if not _check_digit_ok(trimmed):
            return "", "", (f"'{trimmed}' has the right length but its check "
                            f"digit is wrong -- one digit is mistyped. Amazon "
                            f"would reject it, so check it against the invoice")
    return "", "", (f"{len(digits)}-digit value '{digits}' is not a retail "
                    f"barcode (need 13-digit EAN, 12-digit UPC or 8-digit EAN-8)")
