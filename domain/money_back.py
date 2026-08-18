"""domain/money_back.py -- money Amazon owes back, found by checking its own rule.

    "i want each and every feature and page about the inventory and ppc, of
     orbit into my app, please built them"

Orbit has a Reimbursements page. This is the version of it that is TRUE for this
business, built only on figures the app already holds and can show you.

WHAT IT CHECKS, AND WHY THIS ONE

Most of Amazon's reimbursement categories are FBA: units lost in the warehouse,
damaged in transit, disposed of by mistake. Measured across all six accounts,
there are ZERO FBA units here -- everything is merchant-fulfilled, so those
categories cannot happen and a page listing them would be theatre.

What DOES happen on every account is a refund, and a refund has an arithmetic
Amazon publishes:

    When an order is refunded, Amazon returns the referral fee it took, MINUS a
    refund administration fee of the lesser of 5.00 or 20% of that referral fee.

So the most it may keep is:

    keep_allowed = min(5.00, referral_fee * 0.20)

and anything it keeps beyond that is money owed back. That is checkable against
`order_fees`, which already stores what Amazon actually took and actually
returned, per order, from the Finances API -- not estimated, not inferred.

WHAT IT DOES NOT DO

It does not file anything. Not a claim, not a case, not a message. It finds and
it shows the arithmetic, and filing is a decision a person makes in Seller
Central with the figures in front of them. Every entry is called a CANDIDATE for
that reason: Amazon has exceptions (a promotional fee, a category minimum, a
partial refund settled across two events) that this cannot see, and calling a
candidate a certainty is how a page like this stops being believed.

MEASURED ON THE REAL ACCOUNTS, 18 Aug 2026: 7 refunded orders across
selvora_limited and jack_uk, and Amazon kept LESS than its cap on every one.
Zero owed. That is the answer the page should give when it is the true one, and
it is why the page is worth having: it will say something different the day it
is not.
"""

from data import db as _db

# Amazon's refund administration fee: the lesser of this and RATE of the
# referral fee. Published by Amazon and the same in GBP, USD and EUR -- it is a
# flat number per marketplace currency rather than a converted one.
ADMIN_FEE_CAP = 5.00
ADMIN_FEE_RATE = 0.20

# Below this, it is rounding rather than a claim. Amazon settles in pennies and
# the fee is computed on a figure we see rounded to two places, so a one or two
# penny difference says nothing. Chasing it would bury a real one.
MIN_CLAIM = 0.10


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def keep_allowed(referral_fee):
    """The most Amazon may keep of a referral fee when it refunds the order."""
    referral_fee = abs(_f(referral_fee))
    if referral_fee <= 0:
        return 0.0
    return min(ADMIN_FEE_CAP, referral_fee * ADMIN_FEE_RATE)


def check_order(row):
    """One settled order -> a candidate, or None.

    `row` is an order_fees record. Returns None when there is nothing to claim,
    which is the normal answer and the one this returns most of the time.
    """
    refunds = abs(_f(row.get("refunds")))
    if refunds <= 0:
        return None                      # nothing was refunded: nothing to check

    referral = abs(_f(row.get("referral_fees")))
    if referral <= 0:
        # No referral fee was taken, so none can be owed back. Not a fault.
        return None

    principal = abs(_f(row.get("principal")))
    if principal <= 0:
        # Cannot tell what share of the sale came back, so cannot say what share
        # of the fee should have. Unknown is not a claim.
        return None

    # A PARTIAL refund returns a proportional share of the fee. Capped at 1.0
    # because a refund larger than the principal means tax or postage is in
    # there too, and that does not increase the referral fee that was charged.
    share = min(1.0, refunds / principal)
    fee_share = referral * share
    returned = abs(_f(row.get("refund_fees_returned")))

    allowed = keep_allowed(fee_share)
    kept = fee_share - returned
    owed = kept - allowed

    if owed < MIN_CLAIM:
        return None

    return {
        "order_id": row.get("order_id") or "",
        "posted_date": row.get("posted_date") or "",
        "currency": row.get("currency") or "",
        "workspace_id": row.get("workspace_id") or "",
        "marketplace": row.get("marketplace") or "",
        "kind": "referral_fee_not_returned",
        "owed": round(owed, 2),
        # The whole arithmetic, so the figure can be checked rather than
        # believed -- and so it can be typed into a Seller Central case.
        "principal": round(principal, 2),
        "refunded": round(refunds, 2),
        "share_pct": round(share * 100, 1),
        "referral_fee": round(referral, 2),
        "fee_on_refunded_part": round(fee_share, 2),
        "returned": round(returned, 2),
        "kept": round(kept, 2),
        "allowed_to_keep": round(allowed, 2),
        "why": ("Amazon refunded %.2f of a %.2f sale and kept %.2f of the "
                "referral fee. Its own refund administration fee is the lesser "
                "of %.2f and %d%% of that fee, which is %.2f here."
                % (refunds, principal, kept, ADMIN_FEE_CAP,
                   int(ADMIN_FEE_RATE * 100), allowed)),
    }


def _rows(config_path, workspace_id, marketplace=None):
    conn = _db.get_db(config_path)
    sql = ("SELECT workspace_id, marketplace, order_id, posted_date, "
           "referral_fees, principal, refunds, refund_fees_returned, "
           "refund_units, currency FROM order_fees WHERE workspace_id = ?")
    args = [workspace_id]
    if marketplace:
        sql += " AND marketplace = ?"
        args.append(marketplace)
    sql += " ORDER BY posted_date DESC"
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    except Exception:
        return []


def find(config_path, workspace_id, marketplace=None):
    """Every candidate for this account, newest first, with a summary.

    `checked` and `refunded_checked` are reported alongside the candidates
    because "nothing owed" means one thing when 200 refunds were examined and
    something entirely different when none were. A zero with no denominator is
    not an answer.
    """
    rows = _rows(config_path, workspace_id, marketplace)
    refunded = [r for r in rows if abs(_f(r.get("refunds"))) > 0]
    found = [c for c in (check_order(r) for r in refunded) if c]
    found.sort(key=lambda c: (-c["owed"], c["order_id"]))

    by_ccy = {}
    for c in found:
        by_ccy[c["currency"]] = round(by_ccy.get(c["currency"], 0.0) + c["owed"], 2)

    return {
        "candidates": found,
        "count": len(found),
        "owed_by_currency": by_ccy,
        # What was actually looked at, so a zero can be read properly.
        "orders_checked": len(rows),
        "refunds_checked": len(refunded),
        "rule": ("On a refund Amazon returns the referral fee minus an "
                 "administration fee of the lesser of %.2f or %d%% of it. "
                 "Anything kept beyond that is owed back."
                 % (ADMIN_FEE_CAP, int(ADMIN_FEE_RATE * 100))),
        # Said on the page, not only here. This finds; it never files.
        "files_nothing": True,
    }
