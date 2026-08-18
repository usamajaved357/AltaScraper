"""domain/amazon_flags.py -- Amazon's idea of true and false, in ONE place.

WHY THIS EXISTS

    "ON ORDERS DETAIL PAGE IT SHOWS ON EVERY ORDER THAT BUYER ASKED TO cancell"

Every order said the buyer had asked to cancel it. Including orders that had
already shipped. The code was:

    "cancel_requested": bool(it.get("BuyerRequestedCancel")),

which looks correct and is not, because Amazon does not send a boolean there.
probe_cancel_flag.py read 15 real order lines off nestwell_goods and printed the
raw payload. In ONE OrderItem object, three different shapes:

    BuyerRequestedCancel   dict   {"IsBuyerRequestedCancel": "false",
                                   "BuyerCancelReason": ""}
    IsGift                 str    "false"
    IsTransparency         bool   False

`bool()` of a non-empty dict is True. `bool("false")` is True. So the flag was
on for every order that had ever existed, and the gift flag beside it was too.

CLAUDE.md Rule 4 says never guess what Amazon returns -- read the schema. This
module is the other half of that rule: once you HAVE read it, put the answer
somewhere every caller shares, so the next field Amazon sends as a string does
not need the same bug to be found again in a different screen.

Rule 12: one helper, every caller. There were four other `bool(x.get("Is..."))`
call sites across orders and the buy-box monitor, each making the same
assumption, each one field away from the same fault.

WHY NOT JUST FIX THE ONE FIELD
Because the shape is Amazon's choice and it varies by field, by API and over
time. A helper that copes with all of them is right whichever shape arrives; a
cast that assumes one shape is right only until the next field.
"""

# What Amazon writes when it means yes. Everything else is no.
#
# NOT a list of what means no. An unrecognised value has to fall to False,
# because these flags are WARNINGS -- "the buyer wants to cancel", "this is a
# gift" -- and a warning shown wrongly is worse than one missed: it is the
# reason nobody believed this screen. The cost of a false yes here is posting a
# parcel you should not have posted, or not posting one you should.
_YES = ("true", "yes", "y", "1")


def truth(value, key=None):
    """True / False, whatever shape Amazon chose for it.

    Handles, because all four have been seen in real payloads:

        True                                  a real boolean
        "false" / "true"                      a string
        1 / 0                                 a number
        {"IsBuyerRequestedCancel": "false"}   an object wrapping the flag

    `key` names the field inside an object when it is known. Without it, the
    first key beginning with "Is" is taken -- which is how Amazon names the flag
    inside every wrapper of this kind. An object with no such key returns False
    rather than True-because-it-is-not-empty, which is the whole bug.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in _YES
    if isinstance(value, dict):
        if key is not None and key in value:
            return truth(value.get(key))
        for k, v in value.items():
            if str(k).startswith("Is"):
                return truth(v)
        return False
    # A list, or something new. Not understood is not a warning.
    return False


def text(value, key):
    """A string carried alongside a flag, e.g. why the buyer wants to cancel.

    Amazon puts BuyerCancelReason inside the same object as the flag. It is
    almost always empty, and empty is reported as empty rather than as a
    sentence somebody has to read to discover it says nothing.
    """
    if isinstance(value, dict):
        return str(value.get(key) or "").strip()
    return ""
