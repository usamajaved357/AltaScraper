"""routes/scope.py -- WHICH ACCOUNT and WHICH MARKETPLACE a request is about.

WHY THIS FILE EXISTS
Every screen has to answer the same two questions before it can do anything, and
every screen was answering them for itself. An audit on 15 Aug 2026 found the
marketplace resolved in twenty-four places across fifteen route files, in three
mutually incompatible ways:

    ...or _state["active_marketplace"] or ""              14 places
    ...or _state["active_marketplace"] or acc default      6 places
    ...or _state["active_marketplace"] or "UK"             4 places

The first group is a bug, and it is the bug the owner keeps hitting. Nothing
guarantees _state["active_marketplace"] is set: it is written when a marketplace
is CHOSEN, and most screens are not the screen that chooses one. Open the app and
go straight to Finance and it is "", so:

    Finance      "no marketplace selected", on an account with real sales
    Repricer     "no live listings are cached", on an account with 55 cached

Both messages describe a different problem from the real one and send you off to
fix something that was never broken. The third group is worse in a quieter way:
defaulting to "UK" gives a US account a confident answer about the wrong country.

So the resolution order lives here, once:

    1. what the request explicitly asked for   -- always wins
    2. the marketplace currently selected
    3. the ACCOUNT'S OWN default               -- the missing step
    4. the only marketplace that has data      -- see below
    5. "" -- and then the caller must say so, not guess

Step 4 is deliberately only ever used when there is exactly ONE candidate.
Picking the biggest of several would be right most of the time and silently
wrong the rest, on screens that change live prices.

Nothing here reads a request or touches Flask, so it can be tested directly.
"""


def workspace_id(*, state=None, account=None, asked=None):
    """Which account. The request wins, then the account, then what is selected."""
    for v in (asked, (account or {}).get("id"),
              (state or {}).get("active_account_id")):
        s = str(v or "").strip()
        if s:
            return s
    return ""


def marketplace(*, state=None, account=None, asked=None, with_data=None):
    """Which marketplace, by the order above. "" means genuinely unknown.

    `with_data` is an optional callable taking the workspace id and returning a
    marketplace, used only as the last resort before giving up. It is passed in
    rather than imported so this module stays free of storage concerns and the
    caller decides what "has data" means for its own screen.

    THE SELECTED MARKETPLACE ONLY COUNTS IF THIS ACCOUNT SELLS THERE.

    active_marketplace is one variable for the whole server and it is written
    when a marketplace is CHOSEN -- on some other account, possibly hours ago.
    Step 2 handed it to whatever screen asked next, ahead of the account's own
    default, so a US account was answered about the United Kingdom.

    MEASURED on 21 Aug 2026, opening each account in turn and asking the
    Finance screen:

        Sheelady (USA)     marketplaces ["MX","CA","BR","US"], default US
                           -> "No finance data has ever been pulled for
                               Sheelady (USA) on UK"
        Miles Lubricants   default US -> "...on UK"
        Headbanger Lures   no default at all -> "...on UK"

    UK is not one of Sheelady's marketplaces. That answer was not a judgement
    call about which of several to show; it named a country the account does not
    sell in, and then reported "no data" -- which reads as "you have no sales",
    not as "I looked in the wrong place". This file's own docstring says it:
    "defaulting to 'UK' gives a US account a confident answer about the wrong
    country". The default was not the only way to arrive there.

    So the selected marketplace is skipped when the account lists its
    marketplaces and this is not one of them. Nothing else changes: an account
    that does sell there is answered about it exactly as before, and an account
    that lists nothing cannot contradict anything, so it is left as it was.
    """
    acc = account or {}
    sells_in = {str(m or "").strip().upper()
                for m in (acc.get("marketplaces") or []) if str(m or "").strip()}
    selected = str((state or {}).get("active_marketplace") or "").strip().upper()
    if selected and sells_in and selected not in sells_in:
        selected = ""
    # An account that lists no marketplaces but HAS named a default has still
    # said something about itself, and it is more specific than a global that
    # belongs to whichever account was open last.
    if (selected and not sells_in
            and str(acc.get("default_marketplace") or "").strip()):
        selected = ""
    for v in (asked, selected, acc.get("default_marketplace")):
        s = str(v or "").strip().upper()
        if s:
            return s
    if with_data:
        wsid = workspace_id(state=state, account=account)
        if wsid:
            try:
                return str(with_data(wsid) or "").strip().upper()
            except Exception:
                # A lookup that fails is "we could not tell", which is the same
                # answer as none -- never a reason to fail the whole request.
                return ""
    return ""


def resolve(*, state=None, account=None, asked_id=None, asked_marketplace=None,
            with_data=None, load_account=None):
    """Both answers at once: (account, workspace_id, marketplace).

    IF THE REQUEST NAMES AN ACCOUNT, THE ACCOUNT RECORD MUST FOLLOW IT.

    This returned the workspace id the request asked for while handing back the
    account record from the process-wide global -- so the id said one company
    and the CREDENTIALS belonged to another. On the price screen that meant a
    change could be read from, and sent to, the wrong seller account; and with
    the global unset it failed outright with "Credentials are missing:
    lwa_app_id, lwa_client_secret", which is why a price could not be changed
    at all.

    `load_account` is passed in rather than imported so this module stays free
    of storage concerns. Without it, behaviour is exactly as before.
    """
    acc = account or {}
    wsid = workspace_id(state=state, account=acc, asked=asked_id)
    asked = str(asked_id or "").strip()
    if asked and load_account and str(acc.get("id") or "") != asked:
        try:
            found = load_account(asked)
        except Exception:
            found = None
        if found:
            acc = found
    mkt = marketplace(state=state, account=acc, asked=asked_marketplace,
                      with_data=with_data)
    return acc, wsid, mkt


# What a screen should SAY when it still has nothing. One sentence, in the same
# words everywhere, naming the thing to do rather than the thing that is missing:
# "no marketplace selected" tells you what is absent and not how to supply it.
NO_MARKETPLACE = ("No marketplace could be worked out for this account. Pick one "
                  "at the top of the screen, or set a default marketplace for the "
                  "account under Settings.")

NO_ACCOUNT = ("No account is open. Choose one at the top of the screen — this "
              "screen is per account, because the figures are.")
