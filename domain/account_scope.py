"""ONE ANSWER TO "IS THE CALLER ASKING ABOUT THE ACCOUNT THAT IS OPEN?"

WHY THIS FILE EXISTS
--------------------
The rule was written out by hand twice, in two route files, with two different
messages and two different status codes:

    routes/listing_routes.py   inline inside /rows_all
    routes/orders_routes.py    _refuse_other_account()

Both exist because the same defect was found twice: a request answered for
whichever account the SERVER happened to have selected, rather than the one the
browser was actually looking at. In listings it painted one account's listings
under another's name. In orders it went further -- order lines, product titles,
profit, and on /orders/detail the buyer's town and postcode.

A rule about who may see whose data is the worst possible thing to keep two
copies of: the next route to need it copies whichever one it finds first, and a
fix to either leaves the other wrong. Rule 12 -- extract it, then add the third
caller.

THE RULE ITSELF
---------------
Nothing is inferred and nothing is substituted. If the caller names an account
and it is not the open one, the request is REFUSED. Answering for the open
account instead is precisely what produced the wrong data on screen, and
answering for the named one would let any caller read any account by asking.

SILENCE IS NOT A MISMATCH. A caller that names no account behaves exactly as it
always did, so adding this to a route cannot break the callers that have not
been taught to send it yet. That is deliberate: it lets the guard go in first
and the callers follow, instead of needing one flag-day change across every
screen at once.
"""


def is_mismatch(asked, open_id) -> bool:
    """True when `asked` names an account other than the one that is open.

    `asked` of None means the caller said nothing -- never a mismatch.
    An open_id of "" means nothing is open, so there is nothing to disagree
    with; the route's own credential checks refuse that case with a better
    message than this could give ("connect this account first").
    """
    if asked is None:
        return False
    a = str(asked).strip()
    o = str(open_id or "").strip()
    if not a or not o:
        return False
    return a != o


def refusal(asked, open_id, subject="data"):
    """The body to return when is_mismatch() is true.

    A plain dict, not a Flask response, so this module stays importable without
    a request context and can be unit-tested directly. Callers wrap it in
    jsonify() with the status code their screen expects -- 200 where the
    browser treats it as "try again after the switch settles", 409 where it is
    a genuine conflict worth surfacing.

    account_mismatch is the flag every caller keys off; the wording under it is
    for a human reading a network tab.
    """
    return {
        "ok": False,
        "account_mismatch": True,
        "asked_for": str(asked or "").strip(),
        "selected": str(open_id or "").strip(),
        "error": ("This request asked about %s for a different account than the "
                  "one that is open, so nothing was read or changed. Answering "
                  "would risk showing or altering one company's %s under "
                  "another's name." % (subject, subject)),
    }
