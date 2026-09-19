"""domain/listing_status.py -- what Amazon's answer says a listing's state is.

ONE PLACE, because there were two and they disagreed.

    api/amazon_listings.py   "Active" if BUYABLE else "Inactive" -- the fast
                             catalogue call, which never asked for `issues` and
                             so could not see a suppression at all
    routes/live_routes.py    the four-way ladder including "Suppressed", from a
                             per-SKU getListingsItem pass whose answer was then
                             cached for 24 HOURS beside the product image

The consequence was the reported one:

    "when I fix those main images ... the suppression was removed by Amazon ...
     but when I come to app the app still says that they are suppressed in the
     all listing page"

The catalogue could not know, so the word came from the per-SKU pass; that pass
kept its answer for a day, under a constant whose own comment justifies the
duration with "product images rarely change". A picture rarely changes. A
suppression changes the moment you fix the image.

SUPPRESSION IS READ FROM THE STRUCTURED FIELD, NEVER FROM THE PROSE.

CLAUDE.md Rule 4's parsing rule, applied to a second field. Amazon states this
as data:

    "enforcements": {"actions": [{"action": "SEARCH_SUPPRESSED"}], ...}

and the old test was `"suppress" in issue["message"].lower()`. Amazon's own
messages use that word in sentences that mean the opposite -- measured on
nestwell_goods, 19 Sep 2026, listing 6.65_2Days_B0D2RLWFBF carries both:

    18027  ERROR  "...Please submit a compliant image to lift the suppression."
    100581        "...but this will not lead to ASIN suppression. No action is
                   required at this time..."

Read as prose, the second sentence marks a listing suppressed for saying it is
not. On that day the two tests agreed on all 73 listings -- the false positive
needs a listing carrying 100581 WITHOUT 18027, which is exactly what a listing
looks like after its image is fixed. The structured field cannot be read
backwards, so it is what is read.
"""

SUPPRESSED = "Suppressed"
ACTIVE     = "Active"
INCOMPLETE = "Incomplete"
INACTIVE   = "Inactive"

# What Amazon calls the enforcement. Listed rather than pattern-matched: an
# action we have not seen before must not be guessed at as a suppression.
_SUPPRESSING_ACTIONS = {"SEARCH_SUPPRESSED"}


def suppressed(issues):
    """True only when Amazon says, in the structured field, that it suppressed it."""
    for i in (issues or []):
        if not isinstance(i, dict):
            continue
        acts = ((i.get("enforcements") or {}).get("actions")) or []
        for a in acts:
            if not isinstance(a, dict):
                continue
            if str(a.get("action", "")).strip().upper() in _SUPPRESSING_ACTIONS:
                return True
    return False


def has_error(issues):
    """True when any issue is an ERROR -- a listing Amazon will not publish as-is."""
    return any(isinstance(i, dict) and str(i.get("severity", "")).upper() == "ERROR"
               for i in (issues or []))


def of(summaries, issues):
    """The one word this app shows for a listing. -> Active|Suppressed|Incomplete|Inactive

    `summaries` is getListingsItem's / searchListingsItems' summaries list and
    `issues` its issues list. Both may be absent, which is not an error: a caller
    that did not ask for issues simply cannot be told about a suppression, and
    gets the same answer it always got.

    SUPPRESSED OUTRANKS BUYABLE, and that ordering is load-bearing. A suppressed
    listing still reports BUYABLE -- measured on four of the five suppressed
    nestwell_goods listings on 19 Sep 2026 -- so testing BUYABLE first would call
    every one of them Active. It is buyable by someone holding the link and
    invisible in search, which is the whole point of the enforcement.
    """
    if suppressed(issues):
        return SUPPRESSED
    s0 = {}
    for s in (summaries or []):
        if isinstance(s, dict):
            s0 = s
            break
    states = [str(x).upper() for x in (s0.get("status") or [])]
    if "BUYABLE" in states:
        return ACTIVE
    # An ERROR with no BUYABLE is a listing Amazon is holding back over something
    # we can fix, which is a different instruction to the seller than "inactive".
    if has_error(issues):
        return INCOMPLETE
    return INACTIVE
