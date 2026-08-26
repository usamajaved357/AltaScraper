"""domain/amazon_fees.py -- what Amazon actually takes out of a sale.

ONE ANSWER, EVERYWHERE. Asked for as:

    "i want to be shown the profit as the truth and as long as i remember the
     profit is calculated by selling price + shipping price minus the cogs minus
     amazon fees like referal fee, fba fee (if applicable) minus fixed closing
     fee minus any promotions currently going on like coupon or price discount
     etc. and maybe many more, you know amazon more than me, verify everything."

Before this, four places worked out "Amazon's cut" and three of them multiplied
by a flat 15%. This is the only one now (CLAUDE.md Rule 12).

THREE TIERS OF CERTAINTY, AND THE SCREEN IS ALWAYS TOLD WHICH ONE IT GOT

    actual      Amazon has settled the order and itemised what it took. Stored
                per order in `order_fees` by domain/order_finance.py, straight
                from the Finances API. Nothing here improves on it.
    quoted      SP-API getMyFeesEstimateForASIN, which returns the exact
                referral and variable-closing fee for a given ASIN at a given
                price. A live call, so it is used when pricing a listing rather
                than when drawing a list of orders.
    estimated   a percentage of what the buyer paid. The rate is THIS account's
                own measured rate from its settled history where there is
                enough of it (domain/order_profit.fee_rate), and Amazon's usual
                15% only where there is not.

`basis` on every reply says which of the three it is, so a screen can never
present an estimate as a settlement.

WHAT IS AND IS NOT SUBTRACTED, AND WHY

    referral fee        always. A percentage of the total sales price (item +
                        the postage the buyer paid), by category.
    FBA fulfilment fee  only when Amazon fulfilled it. NEVER estimated: it is a
                        per-unit figure that depends on the item's size and
                        weight band, and a guessed one would be wrong by more
                        than it is worth. On a merchant-fulfilled order it is
                        genuinely zero.
    variable closing    media categories only (books, music, video, DVD,
                        software, games). Zero on everything these accounts
                        sell, so it is carried as a field that is normally 0
                        rather than assumed away -- if a media listing ever
                        appears, the settled figure brings it in on its own.
    promotions          coupons and percentage-off funded by the seller.
                        HANDLED BY THE CALLER, because the two feeds disagree
                        about whether it is already out -- see below.
    storage, subscription, high-volume listing fees
                        NOT here. They are account-level monthly charges, not a
                        cut of a sale, and dividing them across orders would
                        move with how many orders there happened to be. They
                        belong in the P&L, which is where finance_data puts
                        them (`other_fees`).

THE PROMOTION TRAP, WRITTEN DOWN SO IT IS NOT RE-DISCOVERED
Amazon's Orders API OrderTotal is what the buyer was CHARGED -- the coupon is
already deducted. Its Finances API reports Principal and PromotionList as
SEPARATE entries, so there the revenue is gross and the coupon must come off.
Both were verified against seven real discounted orders; see
domain/orders_view.profit_for. So this module reports what the promotion WAS,
and never decides whether to subtract it. The caller knows which revenue figure
it started from; this module does not.

NOTHING IS INVENTED HERE
There is no postage allowance, no advertising allowance and no minimum profit
in this file. Those are the seller's own costs and a pricing policy, not money
Amazon takes, and mixing them in is what made an order that earned 2.58 report
as a 2.32 loss. See listing/pricing.py.
"""

# The smallest referral fee Amazon will charge on a sale, per marketplace
# currency. A published figure, and it only ever bites on a very cheap item --
# at the 15% ordinary rate it is reached below 1.67 GBP. Applied to ESTIMATES
# only: a settled order carries the real number and needs no floor.
MIN_REFERRAL = {"GBP": 0.25, "USD": 0.30, "EUR": 0.30, "CAD": 0.30,
                "AUD": 0.30, "SEK": 3.00, "PLN": 1.00}

# Used only when an account has no settled history to measure. domain/orders_view
# owns the number so there is one default, not two that drift.
try:
    from domain.orders_view import DEFAULT_REFERRAL_RATE
except Exception:                                    # importable in isolation
    DEFAULT_REFERRAL_RATE = 0.15

ACTUAL = "actual"
QUOTED = "quoted"
ESTIMATED = "estimated"


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def blank():
    """The shape every function here returns, with nothing in it.

    Returned rather than None when the answer is unknown, so a caller can lay
    out the same rows either way instead of branching on a missing dict.
    """
    return {"referral": None, "fba": 0.0, "closing": 0.0, "other": 0.0,
            "promos": 0.0, "total": None, "basis": "", "rate": None,
            "detail": "", "currency": ""}


def estimate(gross, rate=None, currency="GBP"):
    """Amazon's cut as a percentage of what the buyer paid.

    `gross` is the total sales price -- the item plus any postage the buyer was
    charged -- because that is what Amazon takes its referral fee on. Passing
    the item price alone understates the fee on every order with postage.

    No FBA fee and no closing fee are invented. Both are zero unless a settled
    record says otherwise, which is the honest answer for merchant-fulfilled
    non-media stock and is what these accounts sell.
    """
    out = blank()
    g = _f(gross, None) if gross is not None else None
    if g is None:
        return out
    r = DEFAULT_REFERRAL_RATE if rate is None else _f(rate, DEFAULT_REFERRAL_RATE)
    cur = str(currency or "GBP").upper()
    ref = round(g * r, 2)
    floor = MIN_REFERRAL.get(cur)
    if floor is not None and 0 < g and ref < floor:
        ref = floor
    out.update({"referral": ref, "total": ref, "basis": ESTIMATED, "rate": r,
                "currency": cur,
                "detail": "estimated at %.1f%% of the %.2f the buyer paid; "
                          "Amazon's exact figure arrives when the order settles"
                          % (r * 100, g)})
    return out


def from_settled(row):
    """Amazon's own itemised fees for one order, from `order_fees`.

    `row` is a mapping with referral_fees / fba_fees / other_fees / promos, as
    domain/order_finance.py stores them -- positive numbers meaning money taken.
    Returns None when there is nothing to read, so the caller can fall back.
    """
    if not row:
        return None
    ref = _f(row.get("referral_fees"), 0.0)
    fba = _f(row.get("fba_fees"), 0.0)
    other = _f(row.get("other_fees"), 0.0)
    promos = _f(row.get("promos"), 0.0)
    if ref == 0.0 and fba == 0.0 and other == 0.0:
        # A row exists but Amazon has taken nothing yet. Not a settlement.
        return None
    out = blank()
    bits = ["referral %.2f" % ref]
    if fba:
        bits.append("FBA %.2f" % fba)
    if other:
        bits.append("other %.2f" % other)
    out.update({
        "referral": round(ref, 2), "fba": round(fba, 2),
        "other": round(other, 2), "promos": round(promos, 2),
        "total": round(ref + fba + other, 2), "basis": ACTUAL,
        "detail": "what Amazon actually took, from its own settlement: "
                  + ", ".join(bits),
    })
    return out


def for_order(config_path, workspace_id, marketplace, order_id, gross,
              rate=None, currency="GBP"):
    """Amazon's cut for ONE order: settled where possible, estimated otherwise.

    This is the function every order screen should call. It answers with the
    same shape either way and says in `basis` which it managed.

    Never raises. A database that cannot be read must not stop an order being
    looked at -- it falls back to the estimate, which is what the screen showed
    before this module existed.
    """
    if order_id:
        try:
            from data import db as _db
            conn = _db.get_db(config_path)
            r = conn.execute(
                "SELECT SUM(referral_fees) referral_fees, SUM(fba_fees) fba_fees, "
                "       SUM(other_fees) other_fees, SUM(promos) promos "
                "FROM order_fees WHERE workspace_id=? AND marketplace=? "
                "  AND order_id=?",
                (workspace_id, marketplace, str(order_id))).fetchone()
            got = from_settled(dict(r) if r else None)
            if got:
                got["currency"] = str(currency or "").upper()
                return got
        except Exception:
            pass
    return estimate(gross, rate, currency)


def quote(creds, marketplace, marketplace_id, asin, price, is_fba=False,
          currency=""):
    """Amazon's OWN figure for this ASIN at this price -- the `quoted` tier.

    getMyFeesEstimateForASIN. Unlike estimate(), nothing here is a percentage of
    anything: Amazon returns the referral and closing fees it would actually
    charge, for this ASIN's real category, which is the difference between "about
    15%" and the number.

    THIS WAS ONLY EVER INSIDE THE GENERATOR. amazon_listing_generator.get_fees
    had the single copy, welded to that module's MARKETPLACE / MARKETPLACE_ID
    globals and its console, so nothing outside the generator could ask Amazon
    what a fee would be -- which is why the Fee Tracker needed it extracted
    rather than written a second time (CLAUDE.md Rule 12). get_fees now calls
    this and keeps its own return shape, so its callers are unchanged.

    Returns the standard blank() shape with basis=QUOTED, or a blank with no
    basis when Amazon could not be asked. It never raises and it never falls back
    to a percentage: a caller that wants an estimate should ask for one, because
    silently downgrading is how a screen ends up presenting a guess as Amazon's
    own figure.
    """
    out = blank()
    p = _f(price, None) if price is not None else None
    if not asin or p is None or p <= 0:
        return out
    cur = str(currency or "").upper()
    if not cur:
        # Only two marketplaces are in use; anything else is asked for in GBP
        # rather than guessed, and Amazon rejects a currency that does not match
        # the marketplace, which surfaces as an error rather than a wrong number.
        cur = "USD" if str(marketplace).upper() in ("US", "USA") else "GBP"
    try:
        from sp_api.api import ProductFees
        from sp_api.base import Marketplaces
        mkt = getattr(Marketplaces, str(marketplace).upper(), None) or Marketplaces.UK
        api = ProductFees(credentials=creds, marketplace=mkt, timeout=30)
        res = api.get_product_fees_estimate_for_asin(
            asin=asin, price=p, currency=cur, is_fba=bool(is_fba),
            marketplace_id=marketplace_id)
        pay = res.payload if hasattr(res, "payload") else (res or {})
        details = ((pay.get("FeesEstimateResult") or {})
                   .get("FeesEstimate") or {}).get("FeeDetailList") or []
    except Exception as e:
        out["detail"] = "%s: %s" % (type(e).__name__, str(e)[:120])
        return out
    referral = closing = fba = other = 0.0
    for d in details:
        amt = _f((d.get("FinalFee") or {}).get("Amount"))
        ft = d.get("FeeType") or ""
        if ft == "ReferralFee":
            referral += amt
        elif ft == "VariableClosingFee":
            closing += amt
        elif ft in ("FBAFees", "FulfillmentFees"):
            fba += amt
        else:
            other += amt
    if not details:
        out["detail"] = "Amazon returned no fee lines for this ASIN"
        return out
    out.update({"referral": round(referral, 2), "closing": round(closing, 2),
                "fba": round(fba, 2), "other": round(other, 2),
                "total": round(referral + closing + fba + other, 2),
                "basis": QUOTED, "currency": cur,
                "detail": "Amazon's own quote for this ASIN at %.2f" % p})
    return out


def rate_for(config_path, workspace_id, marketplace, end_date=None):
    """This account's own measured referral rate, or the 15% default.

    A thin wrapper so callers do not each have to know that the measurement
    lives in domain/order_profit.py. Returns (rate, basis, detail) exactly as
    that function does, and falls back rather than raising.
    """
    try:
        import datetime as _dt
        from domain import order_profit as _op
        end = end_date or _dt.date.today().isoformat()
        return _op.fee_rate(config_path, workspace_id, marketplace, end)
    except Exception:
        return DEFAULT_REFERRAL_RATE, "assumed", (
            "%.0f%% -- Amazon's usual referral rate"
            % (DEFAULT_REFERRAL_RATE * 100))


def rate_for_asin(config_path, creds, workspace_id, marketplace, marketplace_id,
                  asin, price, is_fba=False, currency="", max_age_days=7,
                  force=False, allow_quote=True):
    """Amazon's OWN referral rate for THIS product. (rate, basis, detail).

        "get accurate fees from amazon per item"

    WHY A RATE AND NOT AN AMOUNT. The fee depends on the price, and the caller
    asking is usually the repricer, which is computing the price -- so asking
    for an amount is circular. Amazon's referral fee is a PERCENTAGE by
    category, so the rate implied by one quote holds at any price. Quote once,
    derive the rate, and the circle is gone. The generator solves the same
    problem the other way, by pricing twice to settle; it can afford to,
    because it is doing one product at a time and not sixty-seven every four
    hours.

    WHY IT IS CACHED. One call per product per WEEK instead of one per product
    per cycle. A category's rate does not move; if Amazon changes one, a week is
    soon enough to catch it, and `force` re-asks immediately.

    FBA IS NOT IN THE RATE, deliberately -- see the note on the fee_quotes
    table. A per-unit fulfilment fee is not a share of the price.

    IT NEVER SILENTLY DOWNGRADES. If Amazon will not answer -- and on an account
    whose SP-API roles are not granted it will not -- this falls back to the
    account's own measured rate and says so in `detail`, with basis ESTIMATED.
    The caller can then tell a reader which one it got, which is the whole point
    of `basis` existing.
    """
    from data import db as _db

    ws = str(workspace_id or "")
    mkt = str(marketplace or "").upper()
    a = str(asin or "").strip().upper()
    p = _f(price, None) if price is not None else None

    def _fallback(why):
        rate, basis, detail = rate_for(config_path, ws, mkt)
        return rate, ESTIMATED, "%s %s" % (detail, why)

    if not a:
        return _fallback("(no ASIN, so Amazon could not be asked per product).")

    conn = _db.get_db(config_path)
    if not force:
        try:
            row = conn.execute(
                "SELECT rate, quoted_price, quoted_at FROM fee_quotes "
                "WHERE workspace_id=? AND marketplace=? AND asin=?",
                (ws, mkt, a)).fetchone()
        except Exception:
            row = None
        if row and row["rate"] is not None:
            fresh = True
            try:
                import datetime as _dt
                age = (_dt.datetime.now()
                       - _dt.datetime.fromisoformat(str(row["quoted_at"]))).days
                fresh = age <= int(max_age_days)
            except Exception:
                age, fresh = None, True
            if fresh:
                return (float(row["rate"]), QUOTED,
                        "%.2f%% -- Amazon's own figure for %s, quoted at %.2f%s"
                        % (float(row["rate"]) * 100, a,
                           _f(row["quoted_price"]),
                           "" if age is None else
                           (" today" if age == 0 else " %d day(s) ago" % age)))

    # THE PRICING PATH NEVER CALLS AMAZON. decide_one runs for every enrolled
    # SKU on every page load; quoting there would be 67 live calls before the
    # screen could draw, on a limit Amazon enforces. So pricing reads the cache
    # and falls back honestly, and the cache is FILLED by an explicit action --
    # see routes/sourcing_routes.py /sourcing/fees.
    if not allow_quote:
        return _fallback("(Amazon has not been asked about this product yet "
                         "-- press “Get Amazon's fees”).")

    if p is None or p <= 0:
        return _fallback("(no current price to ask Amazon about).")

    q = quote(creds, mkt, marketplace_id, a, p, is_fba=is_fba, currency=currency)
    if q.get("basis") != QUOTED:
        return _fallback("(Amazon would not quote a fee for %s: %s)"
                         % (a, q.get("detail") or "no answer"))

    # The share of the price Amazon takes as a CUT. FBA is excluded above.
    rate = round((_f(q.get("referral")) + _f(q.get("closing"))) / p, 6)
    if rate <= 0 or rate >= 1:
        return _fallback("(Amazon quoted a fee that is not a usable rate).")
    try:
        import datetime as _dt
        conn.execute(
            "INSERT INTO fee_quotes(workspace_id, marketplace, asin, rate, "
            " referral, closing, quoted_price, currency, quoted_at) "
            "VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(workspace_id, marketplace, asin) DO UPDATE SET "
            " rate=excluded.rate, referral=excluded.referral, "
            " closing=excluded.closing, quoted_price=excluded.quoted_price, "
            " currency=excluded.currency, quoted_at=excluded.quoted_at",
            (ws, mkt, a, rate, _f(q.get("referral")), _f(q.get("closing")),
             p, q.get("currency") or "", _dt.datetime.now().isoformat(" ", "seconds")))
        conn.commit()
    except Exception:
        pass          # a cache that cannot be written must not lose the answer
    return (rate, QUOTED,
            "%.2f%% -- Amazon's own figure for %s, quoted at %.2f"
            % (rate * 100, a, p))


def parts_for_display(fees, currency_symbol=""):
    """[(label, amount, explanation)] -- the rows a breakdown table draws.

    Only the parts that are actually non-zero, so a merchant-fulfilled order
    does not show an "FBA fee 0.00" line that invites the question of whether it
    should have one. The referral fee is always shown, because every sale has
    one and a missing row reads as a fee that was forgotten.
    """
    f = fees or blank()
    out = []
    if f.get("referral") is not None:
        out.append(("Referral fee", f["referral"],
                    "Amazon's commission on the sale price, including any "
                    "postage the buyer paid."))
    if _f(f.get("fba")):
        out.append(("FBA fee", f["fba"],
                    "Picking, packing and posting the item from Amazon's "
                    "warehouse. Charged per unit by size and weight."))
    if _f(f.get("closing")):
        out.append(("Fixed closing fee", f["closing"],
                    "A flat charge Amazon adds on media items -- books, music, "
                    "video, DVD, software and games."))
    if _f(f.get("other")):
        out.append(("Other Amazon charges", f["other"],
                    "Anything else Amazon took against this order in its own "
                    "settlement, such as a refund administration fee."))
    return out
