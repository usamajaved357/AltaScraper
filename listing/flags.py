"""listing/flags.py — re-judge a row's compliance/IP flags from the sheet alone.

PLAIN ENGLISH
-------------
When a flag rule is wrong, every row generated under it keeps the wrong flag.
Regenerating a row to clear it costs ~50 seconds and Claude credits, for copy
that was fine all along.

It does not need regenerating. The finished copy is already in the sheet, and
the flag checks are pure functions over that copy: same text in, same verdict
out. So this module re-runs the checks against what is already stored and
reports what the flags SHOULD say. No AI, no scraping, no network.

WHAT IT CANNOT DO, AND WHY
--------------------------
The grounding checks -- "unverified figure", "unverified spec", and the
regulated-claim gate -- compare the copy against the SOURCE the app captured at
generation time (competitor title, specs, eBay data, reviews). That source is
never written to the sheet; only the finished copy is. Re-running them here
would mean inventing the evidence, so notes from those checks are PRESERVED
untouched rather than recomputed. Same for the competitor-brand check, which
needs a live SP-API lookup.

It calls the SAME check functions generation uses -- it does not reimplement a
single rule (CLAUDE.md §12). See the note on decide_status() about the one piece
that is still duplicated.
"""

# Notes segments these checks own. On a rescan they are dropped and rebuilt.
# Anything NOT matching stays exactly as it was -- SKU collisions, price notes,
# and the grounding findings this module cannot honestly recompute.
_FLAG_NOTE_PREFIXES = (
    "compliance [",
    "key reqs:",
    "ip risk",
    # The IP check now heads its summary "IP NOTE (no hold)" when what it found
    # is a note rather than evidence. Without this the note would never be
    # recognised as ours, so every rescan would append a fresh copy alongside
    # the old one and the Notes cell would grow without limit.
    "ip note",
    # And the same for the compliance check, which now separates "the title
    # says this is an X" from "the copy mentions X somewhere". The second heads
    # its segment "COMPLIANCE NOTE (no hold)", which "compliance [" above does
    # not match -- so without this line every rescan would leave the previous
    # note in place and add another.
    "compliance note",
    "phrases:",
    "suspected brand words",
    "possible brand words",
    "competitor brand in copy",
    "claim risk",
    "review: restricted phrasing",
)

# Statuses a rescan may rewrite. Everything else is either the operator's
# decision (APPROVED) or Amazon's own state (LIVE / API_*) and is never touched.
#
# THIS GOVERNS THE STATUS COLUMN ONLY, and that distinction is the whole point.
# The other three columns -- Notes, Compliance Risk, IP Risk -- are this app's
# own verdict about its own copy, not Amazon's state and not the operator's
# decision, so they are correctable on any row.
#
# Gating all four on this set is what left the reported symptom in place:
#
#     "i see ip hold and ip high symbols on many items where it does not
#      have to be"
#
# Measured on the 295 stored listings: of the 72 rows carrying an IP flag, 37
# were LIVE, APPROVED, SUBMITTED or API_ERROR. Every one of them was unreachable
# -- a listing already selling on Amazon, wearing an IP: HIGH badge from a rule
# that no longer makes that finding, with no way to clear it short of editing
# the database by hand. Seventeen of jack_uk's twenty were exactly that.
RESCANNABLE_STATUSES = {"NEEDS_REVIEW", "IP_HOLD", "COMPLIANCE_HOLD", ""}


def owned_note(segment: str) -> bool:
    """Is this notes segment produced by the checks we re-run?"""
    s = (segment or "").strip().lower()
    return any(s.startswith(p) for p in _FLAG_NOTE_PREFIXES)


def split_notes(notes: str):
    """Split a Notes cell into (kept, dropped).

    Notes are ' | ' joined, and the IP summary itself contains ' | ' internally
    ("IP RISK | phrases: x | possible brand words: y"), so its pieces arrive as
    separate segments. Each is matched on its own -- which is why the prefix list
    includes the inner fragments as well as the "IP RISK" head.
    """
    kept, dropped = [], []
    for seg in str(notes or "").split(" | "):
        if not seg.strip():
            continue
        (dropped if owned_note(seg) else kept).append(seg.strip())
    return kept, dropped


def decide_status(current: str, compliance_high: bool, ip_violation: bool) -> str:
    """THE flag-precedence rule: IP_HOLD > COMPLIANCE_HOLD > NEEDS_REVIEW.

    Used by BOTH callers -- process_row() at generation and rescan_row() here --
    so the rule exists once (CLAUDE.md §12). It used to be re-implemented inline
    at three separate points in process_row.

    CLEAR-AND-RECOMPUTE. Any hold the flags previously set is dropped and the
    verdict rebuilt from what was just found. That is required for rescan: if a
    stale hold were kept, a corrected rule could never un-hold a row. Generation
    is unaffected -- at its decision point the status is only ever NEEDS_REVIEW
    or ERROR, and for those two this returns exactly what the old inline rules
    returned.

    Statuses the flags do NOT own -- APPROVED, LIVE, ERROR, API_* -- are returned
    untouched. Those are the operator's decision or Amazon's own state.
    """
    status = (current or "").strip().upper() or "NEEDS_REVIEW"
    if status not in RESCANNABLE_STATUSES:
        return status                       # not ours to touch
    status = "NEEDS_REVIEW"                 # clear any hold we previously set
    if compliance_high:
        status = "COMPLIANCE_HOLD"
    if ip_violation:
        status = "IP_HOLD"                  # supersedes
    return status


def _listing_from_row(row: dict) -> dict:
    """Sheet row -> the listing shape the check functions expect."""
    g = lambda k: str(row.get(k, "") or "")
    return {
        "title":        g("Title"),
        "bullet_1":     g("Bullet 1"),
        "bullet_2":     g("Bullet 2"),
        "bullet_3":     g("Bullet 3"),
        "bullet_4":     g("Bullet 4"),
        "bullet_5":     g("Bullet 5"),
        "description":  g("Description (HTML)"),
        "search_terms": g("Search Terms / KW"),
        "item_highlights": g("Item Highlights"),
    }


def rescan_row(row: dict, ip_rules: dict, compliance_rules: dict) -> dict:
    """Re-judge one row. Returns what the flags SHOULD be, plus what changed.

    Never writes anything. The caller decides whether to apply the result.
    """
    from amazon_listing_generator import check_compliance          # lazy: heavy module
    from listing.compliance import (check_ip_violations, check_category_claims,
                                    check_restricted_phrasing)

    listing      = _listing_from_row(row)
    product_type = str(row.get("Product Type", "") or "")
    brand        = str(row.get("Brand", "") or "")
    cur_status   = str(row.get("Status", "") or "").strip().upper()

    comp = check_compliance(listing["title"], listing, compliance_rules)
    ip   = check_ip_violations(listing, brand, ip_rules)   # competitor brand needs SP-API: skipped
    cat  = check_category_claims(listing, product_type)
    rp   = check_restricted_phrasing(listing)

    kept, dropped = split_notes(row.get("Notes", ""))
    fresh = []
    if comp.get("summary"):
        fresh.append(comp["summary"])
        top = (comp.get("requirements") or [])[:3]
        if top:
            fresh.append("Key reqs: " + " // ".join(top))
    if ip.get("summary"):
        fresh.append(ip["summary"])
    if cat.get("has_flagged") and cat.get("note"):
        fresh.append(cat["note"])
    if rp.get("has_flagged"):
        fresh.append("REVIEW: restricted phrasing: "
                     + ", ".join(sorted({h["phrase"] for h in rp.get("hits", [])})))

    new_notes  = " | ".join(kept + fresh)
    new_status = decide_status(cur_status,
                               comp.get("highest_risk") == "HIGH",
                               bool(ip.get("has_violations")))
    new_comp_risk = comp.get("highest_risk", "") or ""
    new_ip_risk   = "HIGH" if ip.get("has_violations") else ""

    old = {"status": cur_status,
           "notes": str(row.get("Notes", "") or ""),
           "compliance_risk": str(row.get("Compliance Risk", "") or ""),
           "ip_risk": str(row.get("IP Risk", "") or "")}
    new = {"status": new_status, "notes": new_notes,
           "compliance_risk": new_comp_risk, "ip_risk": new_ip_risk}

    # decide_status() already returns a status it does not own untouched, so on
    # a LIVE or APPROVED row "status" simply never appears in `changed` and the
    # caller writes the other three columns. There is no second rule here.
    return {
        "sku":     str(row.get("SKU", "") or ""),
        "title":   listing["title"][:60],
        "old":     old,
        "new":     new,
        "changed": {k for k in new if old.get(k, "") != new[k]},
        "dropped_notes": dropped,
        # Whether the STATUS is ours to rewrite. Reported so a caller can say
        # "the badge was corrected, the status was left alone" rather than
        # leaving somebody to wonder why a LIVE row still reads LIVE.
        "status_owned": cur_status in RESCANNABLE_STATUSES,
    }
