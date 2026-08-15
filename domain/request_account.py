"""domain/request_account.py -- whose account is THIS request about?

WHY THIS EXISTS
_state["active_account_id"] is ONE variable for the whole process. It is not per
browser, not per tab, and it is restored from disk on restart, so it drifts from
what any given screen is showing. Two things go wrong when a request trusts it:

  A READ answers about the wrong company. Opening Nestwell Goods starts a
  /sales/today request; switching account before the reply lands moves the
  global; the server then answers that in-flight request with the OTHER
  account's figures, and the browser paints them into Nestwell's panel.
  Reported as "I opened nestwell goods and it was displaying right data... when
  I switched the account and came back, the data was totally changed."

  A WRITE runs against the wrong company. Pressing Generate while looking at
  Jack Reacherd ran the generator with Nestwell Goods' credentials against
  Nestwell's sheet, and every line of the log said Nestwell while the screen
  still said Jack.

The page always knows which account it is displaying, so it says so, and this
module decides what to do when that disagrees with the global. The two cases
need OPPOSITE answers, which is the whole reason they are settled in one place
rather than at each call site:

  READS  answer for the account the page named. The reply then always matches
         the screen that asked for it, whatever the global has since done, and
         two tabs can show two accounts at once.
  WRITES refuse. A generate writes listings and a submit reaches Amazon; if
         there is any doubt about whose account that is, the only safe answer is
         to do nothing and say so.

This module decides WHICH account. It does not decide whether the user is
allowed it -- that is auth/guard.py's job and it still runs.
"""


def named(request):
    """The account id the calling page says it is displaying, or ""."""
    try:
        v = request.args.get("account_id")
    except Exception:
        v = None
    if not v:
        try:
            v = (request.get_json(silent=True) or {}).get("account_id")
        except Exception:
            v = None
    return str(v or "").strip()


def for_read(request, state, get_account=None):
    """(account_id, account_or_None) for a read-only request.

    The account the PAGE named wins, because the answer is going back to that
    page and has to describe what it is showing. Falls back to the global only
    when the page named nothing -- an old screen, or a background job with no
    page behind it at all.
    """
    aid = named(request)
    if not aid:
        aid = str((state or {}).get("active_account_id", "") or "")
        return aid, None
    acc = None
    if get_account:
        try:
            acc = get_account(aid)
        except Exception:
            acc = None
    return aid, acc


def mismatch_for_write(request, state, what="run"):
    """Why this WRITE must not proceed, or "" if it may.

    Returned as a sentence for the user rather than a boolean, because the only
    useful thing to say here is which two accounts disagreed.
    """
    req = named(request)
    cur = str((state or {}).get("active_account_id", "") or "")
    if req and req != cur:
        return ("ACCOUNT_MISMATCH This page is showing %s but the server has %s "
                "selected, so nothing was %s. A run uses real credentials and "
                "writes real listings, so it will not guess which account you "
                "meant — reselect %s and retry."
                % (req, cur or "no account", what, req))
    if not req and not cur:
        return ("No account is selected, so there is nothing to run against. "
                "Choose an account at the top of the screen.")
    return ""
