"""listing/verify_live.py -- reading Amazon's verdict on a submitted listing.

Moved word for word out of amazon_listing_generator.py (Milestone 4, owner-approved 28 Sep 2026).
amazon_listing_generator.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""



def _issue_str(issues, sent_attrs: dict = None) -> str:
    """Format Amazon's listing issues. Amazon reports a field with a MALFORMED
    value using the same "X is required but missing" text it uses for a truly
    empty required field -- which is misleading. When we know we actually sent a
    value for that field (it's in sent_attrs), we relabel it so the user isn't
    sent hunting for an empty field that isn't empty."""
    sent_attrs = sent_attrs or {}
    parts = []
    for x in issues:
        sev = str(x.get("severity", "?"))[:1].upper()
        an  = x.get("attributeNames") or []
        a   = an[0] if an else ""
        msg = x.get("message", "")
        # misleading-error rewrite: we DID send this attribute, yet Amazon says
        # "required but missing" -> it's really a structure/format problem.
        if a and a in sent_attrs and "required but missing" in msg.lower():
            msg = (f"value was sent but Amazon rejected its STRUCTURE/format "
                   f"(reported as '{msg.strip()}') -- the field is not actually "
                   f"empty; its shape didn't match Amazon's schema.")
        parts.append(f"[{sev}] {a} {msg}".strip())
    # Keep generous room so all errors are stored (was 1500 -> cut off ~8+ errors,
    # making the sheet/dashboard show fewer than the terminal).
    return "; ".join(parts)[:6000]


def _classify_verify_error(exc) -> str:
    """Turn a getListingsItem exception into a plain-English REASON the status check
    failed, so 'unverified' means something (timeout vs not-found vs auth vs other)
    instead of silently swallowing every error. Returns a short human sentence."""
    m = (type(exc).__name__ + " " + str(exc)).lower()
    if "timed out" in m or "timeout" in m or "read operation" in m:
        return ("status check TIMED OUT (connection to Amazon too slow) -- the listing "
                "may well be fine; re-check shortly with 'Re-verify live status'")
    if "404" in m or "not found" in m or "notfound" in m or "does not exist" in m:
        return ("Amazon has NO record of this SKU yet -- either still processing right "
                "after submit (re-check shortly), or the submission did not create a listing")
    if ("403" in m or "401" in m or "forbidden" in m or "unauthorized" in m
            or "unauthorised" in m or "accessdenied" in m or "access to requested" in m):
        return ("PERMISSION DENIED reading the listing (the app's SP-API Listings role "
                "may lack read access) -- fix the role, then re-verify")
    if "429" in m or "quota" in m or "throttl" in m or "too many requests" in m:
        return "Amazon THROTTLED the status check (rate limit) -- re-check shortly"
    return f"status check failed: {str(exc)[:140]}"


def _verify_live_status(li, seller_id, sku, mid, locale="en_GB", settle=True):
    """After a SUBMIT is 'accepted', Amazon processes the listing ASYNCHRONOUSLY --
    'accepted' is NOT 'published'. Query the REAL listing state so a row is marked
    LIVE only when Amazon actually shows it BUYABLE/DISCOVERABLE, and reflects a
    downstream rejection (e.g. a blocked main image) instead of a false LIVE.
    Returns (status_list, error_issues, reason, asin): on success reason is "" and asin is
    the ASIN Amazon assigned (for the LIVE note); if the check itself failed, status/errs
    are None, reason is a plain-English WHY (timeout / not-found / auth / throttle / other)
    captured from the LAST exception (never swallowed silently), and asin is "".

    settle=True waits a few seconds first (right after a fresh submit, Amazon needs a
    moment). Pass settle=False when RE-verifying an already-submitted listing minutes
    later -- there's nothing to wait for, so skip the delay and check immediately."""
    import time as _t
    _last_exc = None
    for _attempt in range(2):
        try:
            if settle:
                _t.sleep(4)   # give Amazon a moment to process the submission
            resp = li.get_listings_item(seller_id, sku, marketplaceIds=[mid],
                                        issueLocale=locale,
                                        includedData=["summaries", "issues"])
            p = resp.payload if hasattr(resp, "payload") else (resp or {})
            summaries = (p or {}).get("summaries", []) or []
            status = summaries[0].get("status", []) if summaries else []
            asin = summaries[0].get("asin", "") if summaries else ""
            issues = (p or {}).get("issues", []) or []
            errs = [x for x in issues if str(x.get("severity", "")).upper() == "ERROR"]
            return status, errs, "", asin
        except Exception as _e:
            _last_exc = _e
            continue
    return None, None, (_classify_verify_error(_last_exc) if _last_exc else "status check failed (no response)"), ""


def _verify_live_settled(li, seller_id, sku, mid, locale="en_GB",
                         attempts=8, interval=12, log=None, tag=""):
    """Poll getListingsItem until the listing SETTLES, instead of judging it from a single
    snapshot taken ~4s after submit. Amazon processes asynchronously: right after a submit
    a listing commonly shows ERRORS and a not-yet-DISCOVERABLE status for a few seconds,
    then goes LIVE. Judging at 4s recorded a FALSE 'NOT live -- rejected' for listings
    Amazon actually published (see 11.95_3Days_B09JYYJR7H -> ASIN B0HCV5XDBK went
    DISCOVERABLE moments later). This returns as soon as the listing is BUYABLE/
    DISCOVERABLE; otherwise it re-checks every `interval`s for up to attempts*interval
    seconds before returning the SETTLED status. Same (status, errs, reason) shape as
    _verify_live_status, so the caller's branch logic is unchanged. Safe to run long in
    the background-job model (the user isn't waiting on a live connection)."""
    import time as _t
    last = (None, None, "status check did not complete")
    n = max(1, int(attempts))
    for _i in range(n):
        status, errs, why, _asin = _verify_live_status(li, seller_id, sku, mid, locale, settle=(_i == 0))
        if status is not None or errs is not None:
            last = (status, errs, why)
            if status and any(str(s).upper() in ("BUYABLE", "DISCOVERABLE") for s in status):
                return status, errs, ""            # settled LIVE -> done immediately
        if _i < n - 1:                             # not live yet -> wait and re-check
            if log and tag:
                log(f"  [dim]{tag}: not live yet -- re-checking Amazon ({_i + 1}/{n})…[/dim]")
            _t.sleep(max(1, int(interval)))
    return last
