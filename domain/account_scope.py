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

AND THERE IS ONE CALLER WITH NO SCREEN BEHIND IT
------------------------------------------------
domain/live_refresher.py rotates through EVERY account, refreshing the ones
nobody is looking at -- which is the whole reason it exists. It has no browser,
so "the account that is open" is not a question that applies to it, and the
guard refused it on every account but whichever the browser happened to show.
Measured in the server log with jack_uk open: five of six accounts' live
catalogues never refreshed at all. And each refusal was written into
marketplace_health.json as that pair's `last_transient` -- so the diagnostics
screen showed this app's own refusal in the place a reader looks for what Amazon
said. (It did NOT rest those marketplaces: looks_permanent() does not match this
text, so it was not counted towards a rest. The entries that are rested carry
real Amazon errors.)

It says so with BACKGROUND_ENVIRON_KEY below rather than with a flag in the
request body. A body flag is JSON a browser can send, and a guard a browser can
switch off is not a guard. Werkzeug builds the WSGI environ from the incoming
request and maps headers to HTTP_* keys, so no HTTP client can produce a key
called "alta.background"; only code holding the app object can.
"""

# Set by in-process callers that ARE the server: app.test_request_context(...,
# environ_base={BACKGROUND_ENVIRON_KEY: True}). Never settable over HTTP.
BACKGROUND_ENVIRON_KEY = "alta.background"


def is_background(environ) -> bool:
    """True when this request was built in-process by the app itself."""
    try:
        return bool((environ or {}).get(BACKGROUND_ENVIRON_KEY))
    except Exception:
        return False


def background_context(app, *args, **kwargs):
    """app.test_request_context(...) marked as the server calling itself.

    One helper so a caller cannot half-remember the key. Every in-process call
    that legitimately targets an account nobody has open goes through this.
    """
    env = dict(kwargs.pop("environ_base", None) or {})
    env[BACKGROUND_ENVIRON_KEY] = True
    return app.test_request_context(*args, environ_base=env, **kwargs)


def is_mismatch(asked, open_id) -> bool:
    """Always False now. The account a request NAMES is the account it gets.

    THIS USED TO REFUSE ANY REQUEST THAT DISAGREED WITH THE SERVER'S SELECTION,
    and that was wrong in a way that took a user report to see:

        "i switched from headbanger lures recently but i am on nestwell goods
         but still i am shown this error"

    The screenshot: the address bar on /w/nestwell_goods/orders, the sidebar
    reading Nestwell Goods LTD, and the screen refusing because the SERVER still
    had headbanger_lures selected.

    `open_id` comes from _state["active_account_id"] -- ONE VARIABLE FOR THE
    WHOLE SERVER PROCESS. routes/accounts_routes.py says exactly this about its
    marketplace twin: "one variable for the whole server and 44 places across 20
    files fall back to it, so one stale value answers for all of them at once".
    With more than one browser tab open -- there were three in that screenshot
    -- whichever tab last called /accounts/select owns it, and every other tab
    is refused for asking about the account it is actually showing. Two people
    using the app at once is the same collision, permanently.

    WHY DROPPING IT IS SAFE, and this is the part that matters:

    This comparison never established WHO was asking. It asked whether a global
    agreed with them. Authorisation -- may this signed-in user open this account
    at all -- lives in auth/guard.py, which checks the named account against the
    user's own workspace list on EVERY request, one level into a list of rows,
    across every parameter a route might read it from. `account` was missing
    from that list and has been added, which closed a real hole on the four
    handlers that read it, two of which return another company's order lines and
    the buyer's town and postcode.

    So the check that mattered now runs earlier and covers more, and the check
    that fired was the wrong one.

    WHAT IS GIVEN UP, stated plainly rather than glossed: this also caught a
    BROWSER bug -- a screen showing one account while asking about another. That
    was worth having. It is traded for a screen that works with more than one
    tab open, and the trade is only acceptable because the authorisation above
    is real and independent of it. If a client bug of that shape appears, it
    will now show wrong data rather than an error, so the browser-side check in
    static/js/orders.js (which compares the reply's account to the one on
    screen) is the remaining line and should stay.

    Kept as a function rather than deleted at seven call sites so there is one
    place to read this, and one place to change it back.
    """
    return False


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
