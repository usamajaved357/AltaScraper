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

                For a product that has NOT sold yet there is no such statement,
                but for one that HAS there is a run of them, and rate_from_orders
                turns those into the rate Amazon really charges on THIS product.
                That is the truest answer a price can be built on, because it is
                not a quote about what would happen -- it is what did.
    quoted      SP-API getMyFeesEstimateForASIN, which returns the exact
                referral and variable-closing fee for a given ASIN at a given
                price. A live call, so it is used when pricing a listing rather
                than when drawing a list of orders.
    estimated   a percentage of what the buyer paid. The rate is THIS account's
                own measured rate from its settled history where there is
                enough of it (domain/order_profit.fee_rate), and Amazon's usual
                15% only where there is not.

rate_for_listing() walks those three in order and is what a screen should call.
Before it existed, the repricer went straight to the quote and skipped the
settled tier entirely -- so a SKU with a shelf of real Amazon statements behind
it was still being priced off a percentage, and the Sourcing page reported a
higher ROI than the Orders page for the same product on the same day.

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

# HOW LONG AMAZON'S OWN QUOTE IS TRUSTED BEFORE IT IS ASKED AGAIN.
#
# A referral fee is a percentage by category and categories do not move daily,
# so this is not about the number going stale -- it is about noticing when it
# has. A day is short enough that a category change is caught the next morning
# and long enough that 67 products cost 67 calls a day, not 67 an hour.
QUOTE_MAX_AGE_HOURS = 24

# A QUOTE IS ALSO STALE WHEN THE PRICE HAS MOVED, not only when it is old.
# The referral RATE holds at any price, but the variable closing fee is a flat
# amount folded into the stored rate, so at a different price that fold is
# wrong. Pennies of movement are not a price change; this is the threshold.
QUOTE_PRICE_TOLERANCE = 0.01

# ---- the automatic quote, and the three things that stop it running away ----
#
#     "When the app needs a fee rate for a product and tier 1 (settled orders)
#      has no data, it should automatically call getMyFeesEstimate for that
#      ASIN+price if there's no cached quote ... If the API call fails
#      (timeout, rate limit), fall through to tier 3 silently -- don't block
#      the page."
#
# The pricing path used to be forbidden from calling Amazon at all, because it
# runs for every enrolled SKU on every draw of the screen and 67 live calls
# before a page appears is not a page. That is still true. What changed is that
# waiting for a button press meant a brand new listing was priced off a
# percentage until somebody remembered to press it.
#
# So it asks, but it cannot ask sixty-seven times:
#
#   A BUDGET   at most AUTO_QUOTE_MAX calls in a rolling window, across the
#              whole process. The first few new products on a screen are quoted
#              and cached; the rest fall through to tier 3 for now and are
#              picked up on the next draw or by the daily job. A cold cache
#              therefore fills over a few page loads instead of holding one
#              page hostage for two minutes.
#   A MEMO     an account that answers "Unauthorized" is not asked again for
#              ACCOUNT_REFUSAL_MEMO_SECONDS, and an ASIN Amazon will not quote
#              is left alone for ASIN_REFUSAL_MEMO_SECONDS. MEASURED: jack_uk
#              and selvora_limited have no Product Fees role, so every one of
#              their 67 SKUs would spend 2-6 seconds being refused, on every
#              page load, forever. The memo turns that into one refusal.
#   A TIMEOUT  shorter than the batch one. A page cannot wait 30 seconds for a
#              fee it has a fallback for.
#
# None of this applies to the button or the daily job: those are deliberate
# batch operations and are allowed to take as long as they take.
AUTO_QUOTE_MAX = 4
AUTO_QUOTE_WINDOW_SECONDS = 60
AUTO_QUOTE_TIMEOUT_SECONDS = 10
ACCOUNT_REFUSAL_MEMO_SECONDS = 600
ASIN_REFUSAL_MEMO_SECONDS = 900

# WHEN A MEASURED MULTIPLIER IS TOO STRANGE TO BE A MEASUREMENT.
#
# Not a fee figure and not a tax rate -- a sanity bound. Amazon taking half of
# what it quoted, or twice, means the two sides were measured on different
# things rather than that a new charge appeared. The measurement is then
# reported and NOT used, the same way a per-product rate outside 0-100% is.
MULTIPLIER_SANE_LOW = 0.5
MULTIPLIER_SANE_HIGH = 2.0

# HOW MANY SETTLED ORDERS BEFORE A SKU'S OWN RATE IS BELIEVED.
#
# One order is an anecdote. It might have carried a refund administration fee,
# or been the one sale that went out under a promotion, and a price built on it
# would be built on that accident. Two is the same threshold domain/promotions.py
# uses for measuring a coupon, and for the same reason.
MIN_SETTLED_ORDERS = 2


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# The budget and the memo, in module state. Per PROCESS, not per request: the
# limit being protected is Amazon's, and Amazon counts calls from the whole
# application rather than from whichever page happened to make them.
import threading as _threading
import time as _time

_auto_lock = _threading.Lock()
_auto_calls = []                 # timestamps of automatic quotes, newest last
_refused = {}                    # key -> (expires_at, why)


def _refusal(key):
    """The live refusal against this key, or "" -- expired ones are dropped."""
    with _auto_lock:
        got = _refused.get(key)
        if not got:
            return ""
        until, why = got
        if _time.time() >= until:
            _refused.pop(key, None)
            return ""
        return why


def _remember_refusal(key, seconds, why):
    with _auto_lock:
        _refused[key] = (_time.time() + float(seconds), why)


def _auto_slot():
    """Take one of the automatic quote slots, or False when they are all gone.

    Consumed BEFORE the call rather than after it, so a slow or hanging call
    still occupies its slot and a screen cannot start five at once.
    """
    now = _time.time()
    with _auto_lock:
        while _auto_calls and now - _auto_calls[0] > AUTO_QUOTE_WINDOW_SECONDS:
            _auto_calls.pop(0)
        if len(_auto_calls) >= AUTO_QUOTE_MAX:
            return False
        _auto_calls.append(now)
        return True


def _creds_for(config_path, workspace_id, marketplace, cfg=None):
    """(creds, marketplace_id, why_not) for asking Amazon about an account.

    ONE PLACE THAT KNOWS HOW TO GET THEM. Both callers that quote need this --
    the button, which is handed a config, and the pricing path, which is not
    and must read one. Two copies of "find the account, build its credentials"
    is how one of them ends up asking with the wrong account's token
    (CLAUDE.md Rule 12).
    """
    try:
        from domain import accounts as _acc
        c = cfg() if callable(cfg) else cfg
        if not c:
            from config import settings as _settings
            c = _settings.read_raw(config_path) or {}
        acc = _acc.get_account(c, str(workspace_id or "")) or {}
        if not acc:
            return None, None, "no account called %s" % workspace_id
        return (_acc.account_creds(acc), _acc.marketplace_id(marketplace), "")
    except Exception as e:
        # Credentials that cannot be assembled are a reason not to ask, never a
        # reason for a price not to be worked out.
        return None, None, "%s: %s" % (type(e).__name__, str(e)[:80])


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
          currency="", timeout=30):
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
        # THE TIMEOUT IS THE CALLER'S TO SET. A batch refresh can afford to
        # wait; a page that is drawing sixty rows and has a fallback cannot.
        api = ProductFees(credentials=creds, marketplace=mkt,
                          timeout=int(timeout or 30))
        res = api.get_product_fees_estimate_for_asin(
            asin=asin, price=p, currency=cur, is_fba=bool(is_fba),
            marketplace_id=marketplace_id)
        pay = res.payload if hasattr(res, "payload") else (res or {})
        _result = (pay.get("FeesEstimateResult") or {})
        details = (_result.get("FeesEstimate") or {}).get("FeeDetailList") or []
        _status = str(_result.get("Status") or "")
        _err = _result.get("Error") or {}
    except Exception as e:
        out["detail"] = "%s: %s" % (type(e).__name__, str(e)[:120])
        return out
    # AMAZON SAYS WHETHER IT ANSWERED, AND IT WAS NOT BEING READ.
    #
    # FeesEstimateResult carries a Status of "Success" or "ClientError" /
    # "ServerError", and on an error it still returns the surrounding structure.
    # Only FeeDetailList was checked, so an errored result with any lines in it
    # -- or lines that summed to nothing -- was recorded as basis=QUOTED.
    # CLAUDE.md Rule 4: read what the schema says, do not infer it.
    if _status and _status.lower() != "success":
        out["detail"] = "Amazon answered %s%s" % (
            _status, (": " + str(_err.get("Message"))[:90]) if _err else "")
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
    # A REFERRAL OF NOTHING IS NOT A QUOTE.
    #
    # MEASURED on the stored listings: 17 rows across jack_uk and
    # nestwell_goods carry amazon_fees = 0.00 with fee_source "SP-API (exact)"
    # -- a bird table, a pizza peel, a massage gun, an ivy hedge panel. Amazon
    # charges a referral fee on every one of those categories, so a zero is a
    # quote that came back empty, not a product Amazon takes nothing on. Every
    # one of those rows has a stored profit that is too high by the whole fee.
    #
    # Refused rather than recorded: the caller falls back to the account's own
    # measured rate and SAYS it is a rate, which is a smaller error than a
    # confident nothing. There is no legitimate 0.00 referral on a physical
    # product at a non-zero price, so nothing real is lost.
    if referral <= 0 and p > 0:
        out["detail"] = ("Amazon quoted no referral fee on this ASIN at %.2f, "
                         "which no category does -- treated as no answer" % p)
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


def _settled_for(config_path, workspace_id, marketplace, sku=None, asin=None):
    """What Amazon took, and what buyers paid, on ONE product's settled orders.

    {fee, revenue, orders, single_line, last, discounted, refunded, rows_seen}
    or None when the database cannot be read.

    BY SKU OR BY ASIN, one query either way. The per-product rate is asked for
    by SKU, because that is what a listing is; the multiplier is asked for by
    ASIN, because that is what Amazon quotes against. Writing that out twice
    would have meant two versions of "which orders count", and the exclusions
    below are the whole substance of the answer (CLAUDE.md Rule 12).
    """
    ws, mkt = str(workspace_id or ""), str(marketplace or "").upper()
    key, val = ("sku", str(sku or "")) if sku else ("asin", str(asin or ""))
    if not val:
        return None
    try:
        from data import db as _db
        conn = _db.get_db(config_path)
        rows = conn.execute(
            "SELECT f.order_id, f.ref, f.fba, f.oth, f.promos, f.refunds, "
            "       f.returned, l.mine_rev, l.tot_rev, l.nlines, l.last_at "
            "  FROM (SELECT order_id, SUM(referral_fees) ref, SUM(fba_fees) fba, "
            "               SUM(other_fees) oth, SUM(promos) promos, "
            "               SUM(refunds) refunds, "
            "               SUM(refund_fees_returned) returned "
            "          FROM order_fees "
            "         WHERE workspace_id=? AND marketplace=? "
            "         GROUP BY order_id) f "
            "  JOIN (SELECT order_id, "
            "               SUM(CASE WHEN %s=? THEN revenue ELSE 0 END) mine_rev, "
            "               SUM(revenue) tot_rev, COUNT(*) nlines, "
            "               MAX(purchase_date) last_at "
            "          FROM order_lines "
            "         WHERE workspace_id=? AND marketplace=? "
            "           AND lower(IFNULL(status,'')) "
            "               NOT IN ('canceled','cancelled') "
            "         GROUP BY order_id) l ON l.order_id = f.order_id "
            " WHERE l.mine_rev > 0" % key,
            (ws, mkt, val, ws, mkt)).fetchall()
    except Exception:
        return None

    out = {"fee": 0.0, "revenue": 0.0, "orders": 0, "single_line": 0,
           "last": "", "discounted": 0, "refunded": 0, "rows_seen": len(rows)}
    for r in rows:
        if _f(r["promos"]) > 0:
            out["discounted"] += 1
            continue
        if _f(r["refunds"]) > 0 or _f(r["returned"]) > 0:
            out["refunded"] += 1
            continue
        took = _f(r["ref"]) + _f(r["fba"]) + _f(r["oth"])
        mine, tot = _f(r["mine_rev"]), _f(r["tot_rev"])
        if took <= 0 or mine <= 0 or tot <= 0:
            continue                      # settled with nothing taken: not a rate
        one_line = int(r["nlines"] or 1) == 1
        out["fee"] += took if one_line else took * (mine / tot)
        out["revenue"] += mine
        out["orders"] += 1
        out["single_line"] += 1 if one_line else 0
        at = str(r["last_at"] or "")[:10]
        if at > out["last"]:
            out["last"] = at
    return out


def rate_from_orders(config_path, workspace_id, marketplace, sku,
                     min_orders=MIN_SETTLED_ORDERS):
    """What Amazon has ACTUALLY taken on this SKU, as a rate. (rate, basis, why).

    The `actual` tier, made usable for a product that has not sold TODAY but has
    sold before. Amazon's settlement is per order, and a price needs a
    percentage, so this reads every settled order this SKU appears in and
    divides what Amazon took by what buyers paid.

    Returns (None, "", reason) when it cannot answer, and the reason is written
    to be shown -- "no settled sales yet" is a fact worth putting on a screen,
    not an error to swallow.

    WHAT IT DIVIDES BY, AND WHY THAT IS THE INC-VAT FIGURE. `order_lines.revenue`
    is what the buyer was charged, which is the same base a price on Amazon is
    quoted in -- so a rate measured here can be multiplied by a listing price and
    give the right amount. `order_fees.principal` is the EX-VAT figure and would
    not: measured on jack_uk order 204-6325754-5123507, Amazon took 4.50 on a
    29.99 sale whose principal is 24.99. That is 15.0% of what the buyer paid and
    18.0% of the principal, and only the first can be multiplied by a shelf
    price. (On nestwell_goods and selvora_limited the two are the same number,
    which is exactly why this trap is invisible until an account is VAT
    registered.)

    WHAT IS LEFT OUT, DELIBERATELY:

      orders that carried a promotion   Amazon charges its fee on the discounted
                                        price, so those orders measure a rate
                                        against a price that was not the shelf
                                        price. The coupon is a separate figure
                                        with a separate home (domain/promotions)
                                        and folding it in here would charge it
                                        twice.
      refunded orders                   Amazon gives part of the fee back. The
                                        rate on such an order is not the rate on
                                        a sale.
      cancelled lines                   never shipped, never charged.

    A MULTI-LINE ORDER IS SHARED BY REVENUE, the same rule the referral fee is
    apportioned by in domain/orders_view.line_breakdown, so the two cannot
    disagree about which line carried what. How many of the orders were single
    line is reported, because a rate built entirely from unambiguous orders and
    one built from shared ones are not equally solid.
    """
    if not str(sku or ""):
        return None, "", "no SKU, so this product's own sales could not be found"
    got = _settled_for(config_path, workspace_id, marketplace, sku=sku)
    if got is None:
        # A database that cannot be read must not stop a price being worked out.
        # The caller falls through to Amazon's quote, which is the next best
        # answer and does not depend on this table.
        return None, "", "this product's settled orders could not be read"
    fee, rev = got["fee"], got["revenue"]
    n, single, last = got["orders"], got["single_line"], got["last"]
    discounted, refunded, rows = (got["discounted"], got["refunded"],
                                  got["rows_seen"])

    if n < int(min_orders) or rev <= 0 or fee <= 0:
        why = ("this product has no settled sales to measure yet"
               if not rows else
               "this product has %d settled sale%s, and %d %s needed to measure "
               "a rate from them" % (n, "" if n == 1 else "s", int(min_orders),
                                     "is" if int(min_orders) == 1 else "are"))
        if discounted or refunded:
            why += (" (%s left out -- a discounted sale is charged on the "
                    "discounted price and a refunded one has part of the fee "
                    "given back, so neither measures the rate on a sale)"
                    % ", ".join(
                        ([("%d discounted" % discounted)] if discounted else [])
                        + ([("%d refunded" % refunded)] if refunded else [])))
        return None, "", why

    rate = round(fee / rev, 6)
    if rate <= 0 or rate >= 1:
        return None, "", ("this product's settled orders give a fee rate of "
                          "%.1f%%, which cannot be right, so it was not used"
                          % (rate * 100))
    detail = ("%.2f%% -- what Amazon actually took on this product, measured "
              "from %d settled order%s (%.2f of fees on %.2f of sales%s)%s"
              % (rate * 100, n, "" if n == 1 else "s", fee, rev,
                 "" if single == n else
                 ", %d of them shared with other products on the same order"
                 % (n - single),
                 "" if not last else ", most recent %s" % last))
    return rate, ACTUAL, detail


def _measure_key(config_path, workspace_id, marketplace):
    """(settled orders, quotes held) -- what makes a stored multiplier stale.

    BOTH SIDES OF THE RATIO ARE COUNTED, because either can bring in something
    new: an order settling adds an actual, and a quote arriving adds a
    prediction to compare against. Counting is cheap and exact. A timer would
    either re-measure a figure that has not moved or leave a stale one standing
    after the sale that would have corrected it; these counts change precisely
    when there is something new to learn from.

    (-1, -1) when the database cannot be read, which never equals a stored key,
    so a broken read re-measures rather than trusting an old figure.
    """
    ws, mkt = str(workspace_id or ""), str(marketplace or "").upper()
    try:
        from data import db as _db
        conn = _db.get_db(config_path)
        orders = int(conn.execute(
            "SELECT COUNT(DISTINCT order_id) FROM order_fees "
            " WHERE workspace_id=? AND marketplace=?", (ws, mkt)
        ).fetchone()[0] or 0)
        quotes = int(conn.execute(
            "SELECT COUNT(*) FROM fee_quotes "
            " WHERE workspace_id=? AND marketplace=? AND rate IS NOT NULL",
            (ws, mkt)).fetchone()[0] or 0)
        return orders, quotes
    except Exception:
        return -1, -1


def measure_multiplier(config_path, workspace_id, marketplace):
    """Measure actual/quoted across this account's products. The slow path.

    Returns the dict stored in `fee_multipliers`, or None when there is nothing
    to measure from. Called by multiplier_for(); nothing else should call it,
    because it walks every quote this account holds.
    """
    ws, mkt = str(workspace_id or ""), str(marketplace or "").upper()
    try:
        from data import db as _db
        conn = _db.get_db(config_path)
        quotes = conn.execute(
            "SELECT asin, rate FROM fee_quotes "
            " WHERE workspace_id=? AND marketplace=? AND rate IS NOT NULL",
            (ws, mkt)).fetchall()
    except Exception:
        return None

    actual = quoted = 0.0
    samples, products = 0, []
    for q in quotes:
        got = _settled_for(config_path, ws, mkt, asin=q["asin"])
        if not got or got["orders"] < MIN_SETTLED_ORDERS:
            continue
        rev, took = got["revenue"], got["fee"]
        if rev <= 0 or took <= 0:
            continue
        # WHAT THE QUOTE WOULD HAVE PREDICTED ON THE SAME SALES, so the two
        # sides are the same shape and the ratio means something. Comparing a
        # rate with an amount, or two rates measured on different revenue,
        # would give a number that moves when the sales mix does.
        predicted = _f(q["rate"]) * rev
        if predicted <= 0:
            continue
        actual += took
        quoted += predicted
        samples += 1
        products.append((str(q["asin"]), took / predicted))

    if not samples or quoted <= 0:
        return None
    mult = round(actual / quoted, 6)
    return {"workspace_id": ws, "marketplace": mkt, "multiplier": mult,
            "samples": samples, "actual_fees": round(actual, 2),
            "quoted_fees": round(quoted, 2), "products": products}


def multiplier_for(config_path, workspace_id, marketplace):
    """(multiplier, detail) -- what a quote for this account has to be scaled by.

        "Remove the hardcoded 1.2 VAT multiplier. Replace it with a measured
         multiplier per account, calculated automatically from real data. No
         hardcoded values anywhere. No config dependency. Fully automatic."

    Amazon's quote is the referral and closing fee. It is not everything that
    leaves the account, and how much else leaves differs BY ACCOUNT: measured
    on the same ASIN at the same 34.99 price, Amazon quoted 5.25 and took 5.25
    on jack_uk, and quoted 5.25 and took 6.30 on nestwell_goods.

    So the gap is measured rather than explained. Across every product that has
    both a quote and settled sales, the money Amazon actually took is divided by
    the money the quotes predicted. That ratio captures fee VAT, digital
    services tax, a per-order charge, a fee type Amazon invents next year --
    without this file ever learning what any of them are called. A hardcoded
    1.2 would have been a guess about a tax position that changes the day a VAT
    number is registered.

    (1.0, why) WHEN THERE IS NOTHING TO MEASURE FROM, which is the honest
    answer for an account that has never sold: the quote stands as it is,
    because it is the best figure available. The multiplier appears by itself
    once the first sales settle.

    SELF-CORRECTING, WITHOUT A TIMER. The stored figure records how many settled
    orders it was measured from; when that count moves, it is measured again. A
    VAT registration, a fee change, an account moving to a different fee tier --
    each shows up as new settlements, and each shifts the multiplier on its own.
    """
    ws, mkt = str(workspace_id or ""), str(marketplace or "").upper()
    orders, quotes = _measure_key(config_path, ws, mkt)

    conn, row = None, None
    try:
        from data import db as _db
        conn = _db.get_db(config_path)
        row = conn.execute(
            "SELECT multiplier, samples, actual_fees, quoted_fees, orders_seen, "
            "       quotes_seen, measured_at FROM fee_multipliers "
            " WHERE workspace_id=? AND marketplace=?", (ws, mkt)).fetchone()
    except Exception:
        conn, row = None, None

    if (row is not None and int(row["orders_seen"] or -1) == orders
            and int(row["quotes_seen"] or -1) == quotes):
        if not int(row["samples"] or 0):
            return 1.0, _NOTHING_TO_MEASURE
        return _multiplier_words(row["multiplier"], row["samples"],
                                 row["actual_fees"], row["quoted_fees"])

    got = measure_multiplier(config_path, ws, mkt)

    # THE "NOTHING TO MEASURE" ANSWER IS STORED TOO, with samples 0.
    #
    # Without that, an account with no overlap between its quotes and its sales
    # re-walked every quote it holds, for every SKU, on every draw of the
    # screen -- the one case where the work is largest and the answer never
    # changes. It is invalidated by the same counts as any other answer, so the
    # first settlement that creates an overlap is picked up at once.
    keep = got or {"multiplier": 1.0, "samples": 0, "actual_fees": 0.0,
                   "quoted_fees": 0.0}
    if conn is not None:
        try:
            import datetime as _dt
            conn.execute(
                "INSERT INTO fee_multipliers(workspace_id, marketplace, "
                " multiplier, samples, actual_fees, quoted_fees, orders_seen, "
                " quotes_seen, measured_at) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(workspace_id, marketplace) DO UPDATE SET "
                " multiplier=excluded.multiplier, samples=excluded.samples, "
                " actual_fees=excluded.actual_fees, "
                " quoted_fees=excluded.quoted_fees, "
                " orders_seen=excluded.orders_seen, "
                " quotes_seen=excluded.quotes_seen, "
                " measured_at=excluded.measured_at",
                (ws, mkt, keep["multiplier"], keep["samples"],
                 keep["actual_fees"], keep["quoted_fees"], orders, quotes,
                 _dt.datetime.now().isoformat(" ", "seconds")))
            conn.commit()
        except Exception:
            pass      # a store that fails must not lose the measurement
    if not got:
        return 1.0, _NOTHING_TO_MEASURE
    return _multiplier_words(got["multiplier"], got["samples"],
                             got["actual_fees"], got["quoted_fees"])


# Said in one place because two paths reach it -- the stored "nothing yet" and
# a fresh measurement that found nothing -- and they are the same fact.
_NOTHING_TO_MEASURE = (
    "no product on this account has both an Amazon quote and settled sales "
    "yet, so the quote is used exactly as Amazon gave it")


def _multiplier_words(mult, samples, actual, quoted):
    """(multiplier, sentence) -- and the refusal of a figure that cannot be real.

    A ratio far from 1 is not a discovery, it is a sign that the two sides were
    measured on different things -- one product's quote against another's sales,
    or a revenue figure that is not what the quote was priced against. Using it
    would move every price on the account. It is refused and said out loud
    instead, which is the same rule the per-product rate follows.
    """
    m = _f(mult, 0.0)
    if m <= 0 or m < MULTIPLIER_SANE_LOW or m > MULTIPLIER_SANE_HIGH:
        return 1.0, ("the settled orders and Amazon's quotes disagree by a "
                     "factor of %.2f on this account, which cannot be right, so "
                     "the quote is used unscaled" % m)
    if abs(m - 1.0) < 0.005:
        return m, ("Amazon takes what it quotes on this account -- measured "
                   "across %d product%s (%.2f taken against %.2f quoted)"
                   % (samples, "" if samples == 1 else "s", _f(actual),
                      _f(quoted)))
    return m, ("Amazon takes %.0f%% %s than it quotes on this account, measured "
               "across %d product%s (%.2f taken against %.2f quoted). Amazon's "
               "quote covers the referral and closing fee; this is what the "
               "settlements show on top of it."
               % (abs(m - 1.0) * 100, "more" if m > 1 else "less", samples,
                  "" if samples == 1 else "s", _f(actual), _f(quoted)))


def rate_for_asin(config_path, creds, workspace_id, marketplace, marketplace_id,
                  asin, price, is_fba=False, currency="",
                  max_age_hours=QUOTE_MAX_AGE_HOURS,
                  force=False, allow_quote=True, auto=False):
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

    WHY IT IS CACHED. One call per product per DAY instead of one per product
    per cycle -- 67 products cost 67 calls a day rather than four hundred. A
    category's rate does not move; a day is soon enough to catch it if Amazon
    changes one, and `force` re-asks immediately.

    A QUOTE GOES STALE TWO WAYS: it gets old (QUOTE_MAX_AGE_HOURS) or the price
    it was taken at stops being the price. The referral RATE holds at any price,
    but the flat variable-closing fee is folded into the stored rate, so at a
    different price that fold is wrong.

    A STALE QUOTE IS STILL AMAZON'S FIGURE, AND IT IS STILL RETURNED. Only the
    caller that is allowed to ask (the button, the daily job) re-asks; the
    pricing path, which may not call Amazon at all, gets the old quote with its
    age said out loud rather than being dropped to a percentage. Amazon's rate
    for this product's category from yesterday beats an average of every other
    product this account sells, and it certainly beats a flat 15%.

    FBA IS NOT IN THE RATE, deliberately -- see the note on the fee_quotes
    table. A per-unit fulfilment fee is not a share of the price.

    IT NEVER SILENTLY DOWNGRADES. If Amazon will not answer -- and on an account
    whose SP-API roles are not granted it will not -- this falls back to the
    account's own measured rate and says so in `detail`, with basis ESTIMATED.
    The caller can then tell a reader which one it got, which is the whole point
    of `basis` existing.

    `auto` MARKS THE CALL AS ONE A PAGE IS WAITING ON. It still asks Amazon --
    that is the point of it -- but under the budget, the refusal memo and the
    short timeout described at the top of this module, so a screen with sixty
    uncached products cannot turn into sixty live calls. A batch caller (the
    button, the daily job) leaves it False and is not limited.

    `creds` MAY BE None ON THE AUTOMATIC PATH. The pricing path has no account
    to hand, so this resolves one from the config rather than making every
    caller learn how (Rule 12).
    """
    from data import db as _db

    ws = str(workspace_id or "")
    mkt = str(marketplace or "").upper()
    a = str(asin or "").strip().upper()
    p = _f(price, None) if price is not None else None

    def _fallback(why):
        rate, basis, detail = rate_for(config_path, ws, mkt)
        return rate, ESTIMATED, "%s %s" % (detail, why)

    # WHAT AMAZON QUOTES IS NOT ALL AMAZON TAKES, and how much more is a fact
    # about this account measured from its own settlements. Applied in ONE
    # place, on the way out, so a cached quote and a freshly fetched one cannot
    # be scaled differently -- and so the raw figure Amazon gave is what stays
    # in fee_quotes. A multiplier that changes then moves every stored quote
    # with it, instead of leaving the cache holding pre-scaled numbers that
    # would have to be rewritten.
    def _quoted(raw_rate, said):
        mult, why = multiplier_for(config_path, ws, mkt)
        raw = _f(raw_rate)
        if abs(mult - 1.0) < 0.005:
            return round(raw, 6), QUOTED, "%.2f%% -- %s" % (raw * 100, said)
        scaled = round(raw * mult, 6)
        return scaled, QUOTED, (
            "%.2f%% -- %s. Amazon quoted %.2f%%; %s"
            % (scaled * 100, said.rstrip(". "), raw * 100, why))

    if not a:
        return _fallback("(no ASIN, so Amazon could not be asked per product).")

    conn = _db.get_db(config_path)
    row = None
    try:
        row = conn.execute(
            "SELECT rate, quoted_price, quoted_at FROM fee_quotes "
            "WHERE workspace_id=? AND marketplace=? AND asin=?",
            (ws, mkt, a)).fetchone()
    except Exception:
        row = None
    if row is not None and row["rate"] is None:
        row = None

    # HOW OLD IT IS, AND WHETHER THE PRICE HAS MOVED UNDER IT. Both are worked
    # out whatever happens next, because the answer is worth saying even when
    # the quote is still used.
    hours, moved, when = None, False, ""
    if row is not None:
        try:
            import datetime as _dt
            hours = ((_dt.datetime.now()
                      - _dt.datetime.fromisoformat(str(row["quoted_at"])))
                     .total_seconds() / 3600.0)
        except Exception:
            hours = None
        qp = _f(row["quoted_price"], 0.0)
        moved = (p is not None and qp > 0
                 and abs(p - qp) > QUOTE_PRICE_TOLERANCE)
        when = ("" if hours is None else
                (" just now" if hours < 1 else
                 (" %d hour(s) ago" % int(hours) if hours < 48 else
                  " %d day(s) ago" % int(hours // 24))))
    current = (row is not None and not moved
               and (hours is None or hours <= float(max_age_hours) * 1.0))

    if row is not None and current and not force:
        return _quoted(row["rate"],
                       "Amazon's own figure for %s, quoted at %.2f%s"
                       % (a, _f(row["quoted_price"]), when))

    def _held(why):
        """The stored quote when there is one, the account's average when not.

        A quote that is due a refresh has not stopped being Amazon's figure for
        this product's category, and swapping it for an average of everything
        else this account sells would be a downgrade dressed as caution. So it
        is returned, with its age and the price it was taken at said plainly,
        and the refresh happens on the next run of the daily job or the moment
        somebody presses the button.
        """
        if row is None:
            return _fallback(why)
        return _quoted(row["rate"],
                       "Amazon's own figure for %s, quoted at %.2f%s. %s"
                       % (a, _f(row["quoted_price"]), when,
                          ("The price has moved since, so it is due a refresh."
                           if moved else "It is due a refresh.")))

    # A CALLER THAT IS NOT ALLOWED TO ASK. The batch refresher passes
    # allow_quote=False when it only wants to know what is already held.
    if not allow_quote:
        return _held("(Amazon has not been asked about this product yet "
                     "-- press “Get Amazon's fees”).")

    if p is None or p <= 0:
        return _held("(no current price to ask Amazon about).")

    # ---- the guards on the automatic path ---------------------------------
    #
    # Each of these ends in _held, which is the same silent fall-through a
    # failed call gets: the screen shows the next best rate and says why. None
    # of them is an error and none of them stops a price being worked out.
    if auto:
        why = _refusal(("account", ws, mkt)) or _refusal(("asin", ws, mkt, a))
        if why:
            return _held("(%s)" % why)
        if not _auto_slot():
            return _held("(Amazon has not been asked about this one yet -- "
                         "several other products were asked about just now, so "
                         "this one waits for the next look or the daily refresh)")

    if not creds:
        creds, _mid, _why = _creds_for(config_path, ws, mkt)
        marketplace_id = marketplace_id or _mid
        if not creds:
            return _held("(Amazon could not be asked: %s)"
                         % (_why or "no credentials for this account"))

    q = quote(creds, mkt, marketplace_id, a, p, is_fba=is_fba, currency=currency,
              timeout=(AUTO_QUOTE_TIMEOUT_SECONDS if auto else 30))
    if q.get("basis") != QUOTED:
        # WHY IT WAS REFUSED DECIDES HOW LONG TO LEAVE IT. A missing Product
        # Fees role is an account-wide fact that will not change this
        # afternoon, and re-asking about all 67 SKUs would cost minutes per
        # page load to learn it again. Anything else is treated as this one
        # product's problem, briefly.
        d = str(q.get("detail") or "")
        if auto:
            if "Unauthorized" in d or "Forbidden" in d or "AccessDenied" in d:
                _remember_refusal(
                    ("account", ws, mkt), ACCOUNT_REFUSAL_MEMO_SECONDS,
                    "Amazon will not answer fee questions for this account -- "
                    "its SP-API Product Fees role is not granted. Run Diagnose "
                    "SP-API")
            else:
                _remember_refusal(
                    ("asin", ws, mkt, a), ASIN_REFUSAL_MEMO_SECONDS,
                    "Amazon would not quote a fee for %s: %s" % (a, d[:120]))
        return _held("(Amazon would not quote a fee for %s: %s)"
                     % (a, d or "no answer"))

    # The share of the price Amazon takes as a CUT. FBA is excluded above.
    rate = round((_f(q.get("referral")) + _f(q.get("closing"))) / p, 6)
    if rate <= 0 or rate >= 1:
        return _held("(Amazon quoted a fee that is not a usable rate).")
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
    # THE RAW FIGURE IS WHAT IS STORED, above; the scaling happens on the way
    # out, so the cache holds what Amazon said and nothing else.
    return _quoted(rate, "Amazon's own figure for %s, quoted at %.2f" % (a, p))


def rate_for_listing(config_path, creds, workspace_id, marketplace,
                     marketplace_id, sku, asin, price, is_fba=False,
                     currency="", force=False, allow_quote=True, auto=False):
    """The fee rate for one listing, best answer first. (rate, basis, detail).

    THE ONE FUNCTION A SCREEN OR A PRICE SHOULD CALL. Three tiers, in this
    order, each one only reached because the one above it could not answer:

      1. actual     what Amazon has really taken on THIS product, measured from
                    its own settled orders. Not a forecast -- a record.
      2. quoted     Amazon's getMyFeesEstimate for this ASIN at this price --
                    from the cache, and ASKED FOR ON THE SPOT when nothing is
                    cached and `auto` is set. This is what answers for a product
                    that has never sold, which is exactly where a flat 15% did
                    most damage: a brand new listing had no history to measure
                    and got the guess, then was priced off it. Waiting for a
                    button press meant it kept the guess until somebody
                    remembered; now the first draw of the screen fetches it and
                    every draw after that reads the cache.
      3. estimated  this account's own measured average, then Amazon's usual 15%
                    if even that cannot be worked out.

    WHY THE SETTLED TIER OUTRANKS AMAZON'S OWN QUOTE. The quote is what Amazon
    says it will charge in referral and closing fees. The settlement is what
    Amazon actually took, including the per-order charges a quote does not
    mention. Where both exist they agree closely, and where they do not, the
    bank statement wins.

    `detail` always names which tier answered and says what the others could
    not, so the tooltip on a screen is the audit trail -- there is never a rate
    on this app's screens whose origin cannot be read off the screen itself.
    """
    rate, basis, why = rate_from_orders(config_path, workspace_id, marketplace,
                                        sku)
    if rate:
        return rate, basis, why

    rate, basis, detail = rate_for_asin(
        config_path, creds, workspace_id, marketplace, marketplace_id,
        asin, price, is_fba=is_fba, currency=currency, force=force,
        allow_quote=allow_quote, auto=auto)
    # WHY THE TRUER ANSWER WAS NOT AVAILABLE, carried along. Without it a
    # reader is told what the rate IS and never that a better one exists as
    # soon as the product sells twice.
    if why:
        detail = "%s (%s)" % (detail, why)
    return rate, basis, detail


def quote_for_sku(config_path, cfg, workspace_id, marketplace, sku,
                  force=False, allow_quote=True):
    """Ask Amazon what it charges on ONE enrolled SKU, and remember it.

    (rate, basis, detail, note) -- `note` is "" when Amazon was asked, or the
    reason it could not be.

    ONE PLACE, because four callers want exactly this: enrolling a SKU, the
    "Get Amazon's fees" button, the weekly refresh job, and the bulk enroll. Each
    of them needs the account looked up, the current price and OUR ASIN found,
    and the answer stored -- and four copies of that would drift apart on the
    detail that matters, which is that NOTHING is asked about a product without
    a real ASIN and a real price (CLAUDE.md Rule 12).
    """
    from domain import source_run as _run

    # Through the shared resolver, which the automatic path also uses -- the
    # account lookup and the credential building were written out again here
    # and the two could have disagreed about which account was being asked.
    creds, mid, why = _creds_for(config_path, workspace_id, marketplace, cfg)
    if not creds:
        return None, "", "", (why or "no account called %s" % workspace_id)
    cur = _run.current_for(config_path, workspace_id, marketplace, sku) or {}
    asin, price = cur.get("asin"), cur.get("price")
    # AMAZON IS ASKED ABOUT A PRODUCT AT A PRICE. Without either there is no
    # question to put to it, and a made-up one would be answered confidently
    # about the wrong thing.
    if not asin:
        return None, "", "", "no ASIN in the catalogue snapshot"
    if not price:
        return None, "", "", "no current price to ask about"
    # auto is left False: this IS the batch path, and it is not rationed.
    rate, basis, detail = rate_for_asin(
        config_path, creds, workspace_id, marketplace, mid, asin, price,
        is_fba=_run._is_fba(cur), force=force, allow_quote=allow_quote)
    return rate, basis, detail, ""


# WHAT EACH AMAZON CHARGE IS, IN ONE PLACE.
#
# Two screens describe these fees: the P&L, which shows what was taken off a
# settled order, and the Repricer, which shows what WILL be taken at a price it
# is about to set. Same charges, same names, so they are written once
# (CLAUDE.md Rule 12) -- two copies drift, and a reader who sees "Fixed closing
# fee" on one screen and "Variable closing fee" on the other has to work out
# whether those are the same thing.
FEE_WORDS = {
    "referral": ("Referral fee",
                 "Amazon's commission on the sale price, including any "
                 "postage the buyer paid."),
    "fba": ("FBA fee",
            "Picking, packing and posting the item from Amazon's warehouse. "
            "Charged per unit by size and weight."),
    # Amazon's own name for it in the fee API is VariableClosingFee, so that is
    # what both screens call it. "Variable" describes the CATEGORY it applies
    # to, not the amount -- the amount is a flat charge per item.
    "closing": ("Variable closing fee",
                "A flat charge Amazon adds on media items -- books, music, "
                "video, DVD, software and games."),
    "other": ("Other Amazon charges",
              "Anything else Amazon took against this order in its own "
              "settlement, such as a refund administration fee."),
}


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
        out.append(FEE_WORDS["referral"][:1] + (f["referral"],)
                   + FEE_WORDS["referral"][1:])
    for key in ("fba", "closing", "other"):
        if _f(f.get(key)):
            out.append(FEE_WORDS[key][:1] + (f[key],) + FEE_WORDS[key][1:])
    return [(lab, amt, why) for lab, amt, why in out]


def breakdown_for(config_path, workspace_id, marketplace, asin, price,
                  is_fba=False, currency="GBP", rate=None, basis="", detail=""):
    """Every Amazon charge on ONE product at ONE price -- charged or not.

        "the fees of amazon reflecting in the details should be accurate and
         not estimate of 15 percent like i see right now in the app"

    WHY IT SHOWS FEES THAT ARE NOT CHARGED. parts_for_display drops the zeros,
    which is right on a P&L -- an FBA line reading 0.00 next to a merchant
    order invites the question of whether something was missed. The Repricer is
    answering a different question: "what does Amazon take out of this price?"
    There, a fee you are NOT paying is information, so it is listed and dimmed
    rather than hidden. That is the reference mockup's "All Amazon fees"
    pattern, and it is why this returns `charged` on every line instead of
    filtering.

    WHY THE CLOSING FEE DOES NOT SCALE AND THE REFERRAL FEE DOES. The referral
    fee is a PERCENTAGE of the sale price, so it is worked out again at whatever
    price is being considered. The variable closing fee is a FLAT amount per
    item (media categories only), so it stays exactly as Amazon quoted it.
    Multiplying a stored rate by the price would quietly inflate that flat
    charge every time the price went up.

    NOTHING IS INVENTED. If Amazon has not been asked about this ASIN, the
    referral line falls back to the account's own MEASURED rate and says so;
    the FBA line is 0.00 with the reason, because these listings are shipped by
    the seller and Amazon does not charge a fulfilment fee on them. An FBA
    figure is never estimated -- it is a per-unit charge by size and weight,
    and there is no honest way to guess it.

    `rate`/`basis`/`detail` ARE THE ALREADY-RESOLVED ANSWER, passed in by a
    caller that has one. The repricer does: it resolves the rate once through
    rate_for_listing and prices with it, so this panel must show THAT rate and
    not go looking for its own. Resolving twice is how a panel comes to sit
    underneath a price it disagrees with (CLAUDE.md Rule 12).
    """
    from data import db as _db

    ws, mkt = str(workspace_id or ""), str(marketplace or "").upper()
    a = str(asin or "").strip().upper()
    p = _f(price, 0.0)
    cur = str(currency or "GBP").upper()
    given_rate, given_basis, given_detail = rate, str(basis or ""), detail

    row = None
    if a:
        try:
            row = _db.get_db(config_path).execute(
                "SELECT rate, referral, closing, quoted_price, currency, "
                " quoted_at FROM fee_quotes "
                "WHERE workspace_id=? AND marketplace=? AND asin=?",
                (ws, mkt, a)).fetchone()
        except Exception:
            row = None

    lines, basis, detail, asked_at = [], ESTIMATED, "", ""

    # ---- referral -------------------------------------------------------
    if given_rate and given_basis in (ACTUAL, QUOTED):
        # THE RATE THE PRICE WAS BUILT ON, whichever tier it came from, and it
        # is a rate for EVERYTHING Amazon takes -- the settled tier measures the
        # lot, and a quoted one has been scaled by what this account's
        # settlements show on top of a quote. So it goes on the referral line
        # whole and the closing line stays at zero rather than being counted a
        # second time.
        #
        # It used to accept only the settled tier, which left the panel
        # recomputing a QUOTED rate from the raw stored quote -- 15.00% under a
        # row that had been priced at 18.00%, with nothing to say why.
        basis, ref_rate, closing = given_basis, float(given_rate), 0.0
        detail = given_detail or (
            "Measured from what Amazon actually took on this product's settled "
            "orders.")
    elif row and row["rate"] is not None and _f(row["quoted_price"]) > 0:
        basis, asked_at = QUOTED, str(row["quoted_at"] or "")
        cur = str(row["currency"] or cur).upper()
        # The referral fee's OWN share, not the stored blended rate -- the
        # stored one has the flat closing fee folded into it.
        ref_rate = _f(row["referral"]) / _f(row["quoted_price"])
        closing = round(_f(row["closing"]), 2)
        detail = ("Amazon quoted these on %s at %.2f." % (a, _f(row["quoted_price"]))
                  + ("" if not asked_at else " Asked %s." % asked_at))
    else:
        ref_rate, _b, detail = rate_for(config_path, ws, mkt)
        closing = 0.0
        detail = ("Amazon has not been asked about this product yet, so the "
                  "referral fee below is %s Press “Get Amazon's fees” "
                  "to replace it with Amazon's own figure." % detail)

    referral = round(p * ref_rate, 2)
    floor = MIN_REFERRAL.get(cur)
    if floor is not None and p > 0 and referral < floor:
        referral = floor
    lab, why = FEE_WORDS["referral"]
    lines.append({
        "key": "referral", "label": lab, "amount": referral, "charged": True,
        "note": "%.2f%% of %.2f%s%s" % (
            ref_rate * 100, p,
            "" if floor is None or referral > floor
            else " (Amazon's %.2f minimum applies)" % floor,
            # WHERE THAT PERCENTAGE CAME FROM, on the line itself. The panel is
            # read on its own, away from the tooltip that carries `detail`.
            ", measured on this product's own settled orders"
            if basis == ACTUAL else
            (", Amazon's quote for this product scaled by what its settlements "
             "show" if (given_rate and basis == QUOTED) else "")),
        "why": why})

    # ---- variable closing ----------------------------------------------
    lab, why = FEE_WORDS["closing"]
    lines.append({
        "key": "closing", "label": lab, "amount": closing,
        "charged": closing > 0,
        "note": ("a flat %.2f per item" % closing if closing > 0
                 else ("already inside the rate above"
                       if given_rate and basis in (ACTUAL, QUOTED)
                       else "not charged -- this is not a media category")),
        "why": why})

    # ---- FBA ------------------------------------------------------------
    lab, why = FEE_WORDS["fba"]
    lines.append({
        "key": "fba", "label": lab, "amount": 0.0,
        "charged": bool(is_fba),
        "note": ("Amazon fulfils this one -- the per-unit fee depends on size "
                 "and weight and is not in this quote"
                 if is_fba else
                 "not charged -- you post this yourself"),
        "why": why})

    return {
        "asin": a, "price": round(p, 2), "currency": cur, "basis": basis,
        "detail": detail, "asked_at": asked_at,
        "rate": round(ref_rate, 6), "lines": lines,
        "total": round(sum(l["amount"] for l in lines if l["charged"]), 2),
    }
