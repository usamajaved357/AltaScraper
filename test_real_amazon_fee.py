"""The repricer prices from what Amazon actually charges, per product.

    "the fees of amazon reflecting in the details should be accurate and not
     estimate of 15 percent like i see right now in the app"
    "get accurate fees from amazon per item"

IT WAS WORSE THAN A ROUNDING DIFFERENCE. The repricer built every floor on a
flat 15%. Measured against what Amazon has ACTUALLY SETTLED on these accounts
(domain/order_profit.fee_rate, from the Finances feed):

    jack_uk / UK          17.5%   from 402.39 of settled sales
    nestwell_goods / UK   18.0%   from 344.90
    selvora_limited / UK  18.0%   from 1909.11, 59 orders

So every floor was too low and every "20% ROI" was really about 14%.

THREE TIERS, AND THE SCREEN IS TOLD WHICH ONE IT GOT. domain/amazon_fees already
owned this for the rest of the app -- actual (settled), quoted (Amazon's own
figure for an ASIN), estimated (a rate). The repricer was the one screen not
using it (CLAUDE.md Rule 12).

A RATE, NOT AN AMOUNT, is what makes a per-item quote workable at all. The fee
depends on the price and the repricer is computing the price, so asking for an
amount is circular. Amazon's referral fee is a percentage BY CATEGORY, so one
quote gives a rate that holds at any price. It is also what keeps the API usage
sane: one call per product per week rather than 67 per four-hour cycle.

THE PRICING PATH NEVER CALLS AMAZON. decide_one runs for every enrolled SKU on
every page load. It reads the cache and falls back honestly; /sourcing/fees is
the only thing that asks.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import amazon_fees as F
from domain import sourcing as S

print("=== the fee changes the price, and by how much ===")
COST = 24.00
at15 = S.floor_price(COST, {"referral_rate": 0.15, "target_roi_pct": 20.0})
at175 = S.floor_price(COST, {"referral_rate": 0.175, "target_roi_pct": 20.0})
at18 = S.floor_price(COST, {"referral_rate": 0.18, "target_roi_pct": 20.0})
print("     24.00 cost, 20%% ROI:  15%% -> %s   17.5%% -> %s   18%% -> %s"
      % (at15, at175, at18))
truthy("a truer fee asks for a HIGHER price", at175 > at15)
truthy("  and higher again at 18%", at18 > at175)
# The harm, stated as the owner would feel it: at the old price, against the
# real fee, the return he was promised is not the return he gets.
got = S._pricing.achieved(at15, COST, 0.175)
truthy("pricing at 15%% when Amazon takes 17.5%% misses the 20%% target",
       got["roi_pct"] < 20.0)
print("     ...a 33.89 price returns %.1f%% ROI, not 20%%" % got["roi_pct"])

print("\n=== the cache-only path never calls Amazon, and says so ===")
rate, basis, detail = F.rate_for_asin(
    "config.json", None, "jack_uk", "UK", None, "B0TESTASIN", 20.99,
    allow_quote=False)
check("it falls back to the account's measured rate", basis, F.ESTIMATED)
truthy("  which is this account's own 17.5%, not 15%", abs(rate - 0.175) < 0.02)
truthy("  and it says Amazon has not been asked yet",
       "not been asked" in detail)
truthy("  naming the button that would ask", "Get Amazon" in detail)

print("\n=== nothing is invented when there is nothing to ask about ===")
r2, b2, d2 = F.rate_for_asin("config.json", None, "jack_uk", "UK", None,
                             "", 20.99, allow_quote=True)
check("no ASIN -> no quote", b2, F.ESTIMATED)
truthy("  and it says why", "no ASIN" in d2)
r3, b3, d3 = F.rate_for_asin("config.json", None, "jack_uk", "UK", None,
                             "B0TESTASIN", None, allow_quote=True)
check("no price -> no quote", b3, F.ESTIMATED)
truthy("  and it says why", "no current price" in d3)

print("\n=== the rate is stored per product, and FBA is not in it ===")
DB = open(os.path.join("data", "db.py"), encoding="utf-8").read()
truthy("there is a cache table", "CREATE TABLE IF NOT EXISTS fee_quotes" in DB)
truthy("  keyed per account, marketplace and ASIN",
       "PRIMARY KEY (workspace_id, marketplace, asin)" in
       DB.split("fee_quotes")[1][:900])
truthy("  keeping the price it was quoted at", "quoted_price" in DB)
# A per-unit fulfilment fee is not a share of the price. Rolled into a rate it
# would be wrong at every price except the one it was quoted at.
truthy("  and the table says why FBA is excluded",
       "FBA IS DELIBERATELY NOT IN THE RATE" in DB)
FEE = open(os.path.join("domain", "amazon_fees.py"), encoding="utf-8").read()
_fn = FEE.split("def rate_for_asin(")[1].split("\ndef ")[0]
truthy("the rate is referral + closing only, over the price",
       '_f(q.get("referral")) + _f(q.get("closing"))) / p' in _fn)
falsy("  FBA is not added into it", '+ _f(q.get("fba"))' in _fn)
truthy("a nonsense rate is refused rather than stored",
       "rate <= 0 or rate >= 1" in _fn)
truthy("a cache that cannot be written does not lose the answer",
       "must not lose the answer" in _fn)

print("\n=== one place sets it, so every use follows ===")
RUN = open(os.path.join("domain", "source_run.py"), encoding="utf-8").read()
truthy("decide_one resolves the rate before decide runs",
       'rule["referral_rate"] = _rate' in RUN)
# IT USED TO BE FORBIDDEN FROM ASKING AT ALL (allow_quote=False), because 67
# live calls before a screen can draw is not a screen. It asks now -- "don't
# wait for the scheduler or a manual button press" -- and what makes that safe
# is `auto`, which rations the calls rather than banning them. Asserted below.
truthy("  and it may ask Amazon itself when nothing is cached",
       "allow_quote=True, auto=True" in RUN)
truthy("  and a failure never stops a price being worked out",
       "must never stop a price" in RUN)
# OUR ASIN, not the competitor's in the SKU.
truthy("our own ASIN is carried out of the snapshot", '"asin": str(it.get("asin")' in RUN)
# One word, because the note wraps: "that is the COMPETITOR\n# ASIN the listing
# was researched from". Matching the phrase finds the line break, not the text.
truthy("  and it says why the SKU's ASIN is the wrong one",
       "COMPETITOR" in RUN)
truthy("the basis reaches the screen", 'decision["fee_basis"]' in RUN)

print("\n=== the screen says whose figure it is ===")
JS = open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()
# The "Amazon's cut" line went with the rest of the price list. The distinction
# it carried is now on the Amazon fee PILL, which is greened when quoted and
# prints the word beside the rate -- "17.5% measured" or "15.3% quoted" -- so it
# reads without hovering, which the old note did not.
truthy("a quote is named as Amazon's own",
       ("Amazon\\'s own figure for this product" in JS
        or "Amazon's own figure for this product" in JS)
       and "'quoted' : 'measured'" in JS)
truthy("  and an estimate is not dressed up as one",
       "your measured rate, not Amazon" in JS.replace("\\'", "'"))
truthy("    with the quoted one marked green and the estimate not",
       "quoted ? 'rp-g' : ''" in JS)
# It printed a rounded whole number, so 17.5% read as "18%" and 15% and 15.4%
# looked identical.
# Asserted on the CODE that formats it rather than on "whatever appears near
# the words Amazon's cut" -- the old form split on the first occurrence of that
# phrase, and adding a comment mentioning it elsewhere in the file moved the
# split point and failed a line that had not changed.
truthy("the rate is shown to the decimal",
       "(b.fee_rate * 100).toFixed(2)" in JS)
truthy("  without a pointless trailing zero",
       ".replace(/\\.00$/, '')" in JS)

print("\n=== asking Amazon is a read, and its own button ===")
G = open(os.path.join("auth", "guard.py"), encoding="utf-8").read()
truthy("the fee route needs no publish right", '("/sourcing/fees",' in G)
_g = G.split('("/sourcing/fees",')[1][:60]
truthy("  it is None", "None" in _g)
truthy("  and sits ABOVE the broad /sourcing line",
       G.index('("/sourcing/fees",') < G.index('("/sourcing",                       "publish")'))
R = open(os.path.join("routes", "sourcing_routes.py"), encoding="utf-8").read()
truthy("the route exists", '@app.route("/sourcing/fees"' in R)
_r = R.split("def sourcing_fees(")[1].split("@app.route")[0]
# THE GUARD MOVED INTO THE SHARED ASKER, and that is the point of it moving.
# Four callers now want "ask Amazon about one enrolled SKU" -- the button, the
# weekly refresh, enrolling one SKU and enrolling in bulk -- and each of them
# needed the same refusal to invent an ASIN or a price. Four copies of that
# would have drifted (CLAUDE.md Rule 12), so the route is asserted to DELEGATE
# and the refusal is asserted where it now lives.
truthy("  the route asks through the one shared function",
       "_fees.quote_for_sku(" in _r)
F = open(os.path.join("domain", "amazon_fees.py"), encoding="utf-8").read()
_q = F.split("def quote_for_sku(")[1].split("\ndef ")[0]
truthy("  a SKU with no ASIN or price is skipped, not guessed",
       "no ASIN in the catalogue snapshot" in _q
       and "no current price to ask about" in _q)
truthy("  and what could not be quoted is returned per SKU", "not_quoted" in _r)
truthy("the button is on the toolbar", "sourcingGetFees(" in JS)
truthy("  and it reports what Amazon refused", "could not be quoted" in JS)

print("\n=== the settled tier: what Amazon really took on THIS product ===")
# THE BUG THIS TIER FIXES, in the owner's words: "The Sourcing page shows ROI
# 30% and the Orders page shows ROI 22.5% for the same product ... sourcing uses
# estimated fees, orders uses actual fees." Orders reads Amazon's settlement.
# Sourcing multiplied by a percentage and never looked at the settlement at all,
# even for a product with a shelf of them behind it.
import sqlite3

# `F` was rebound to the FILE TEXT further up (the section that asserts on the
# source), so the module is imported again under its own name rather than
# reading like the two are the same thing.
from domain import amazon_fees as AF
from data import db as _db

_conn = sqlite3.connect("file:%s?mode=ro" % _db.db_path("config.json").replace("\\", "/"),
                        uri=True)
_conn.row_factory = sqlite3.Row
_sold = _conn.execute(
    "SELECT workspace_id ws, marketplace mkt, sku, COUNT(DISTINCT order_id) n "
    "  FROM order_lines WHERE IFNULL(sku,'')<>'' "
    " GROUP BY workspace_id, marketplace, sku HAVING n >= 2 "
    " ORDER BY n DESC LIMIT 1").fetchone()
truthy("there is a SKU with settled sales to measure", _sold is not None)
if _sold:
    _r, _b, _d = AF.rate_from_orders("config.json", _sold["ws"], _sold["mkt"],
                                    _sold["sku"])
    print("     %s / %s -> %s" % (_sold["ws"], _sold["sku"],
                                  ("%.2f%%" % (_r * 100)) if _r else _d))
    check("  a sold product's own rate is ACTUAL, not an estimate", _b, AF.ACTUAL)
    truthy("    and it is a believable rate", 0.05 < _r < 0.35)
    truthy("    and it says how many orders it was measured from",
           "settled order" in _d)
    # THE WHOLE POINT: it outranks the quote and the average.
    _r2, _b2, _d2 = AF.rate_for_listing("config.json", None, _sold["ws"],
                                       _sold["mkt"], None, _sold["sku"],
                                       "B0TESTASIN", 30.00, allow_quote=False)
    check("  and the resolver prefers it over Amazon's quote", _b2, AF.ACTUAL)
    check("    answering with the same number", round(_r2, 6), round(_r, 6))

# A PRODUCT THAT HAS NEVER SOLD FALLS THROUGH, which is the case the owner
# named: "This fixes the fee for new products that haven't sold yet."
_r3, _b3, _d3 = AF.rate_for_listing("config.json", None, "jack_uk", "UK", None,
                                   "NO-SUCH-SKU-EVER", "B0TESTASIN", 30.00,
                                   allow_quote=False)
truthy("a product with no sales falls through to the next tier",
       _b3 in (AF.QUOTED, AF.ESTIMATED))
truthy("  and says the settled tier had nothing to measure",
       "no settled sales" in _d3)
truthy("  without inventing a rate", 0.05 < _r3 < 0.35)

# ONE SALE IS NOT A RATE.
_F2 = AF.rate_from_orders("config.json", "jack_uk", "UK", "NO-SUCH-SKU-EVER",
                         min_orders=99)
check("a SKU cannot clear a threshold it has no orders for", _F2[0], None)

FEE = open(os.path.join("domain", "amazon_fees.py"), encoding="utf-8").read()
_fo = FEE.split("def rate_from_orders(")[1].split("\ndef ")[0]
# THE VAT TRAP. Amazon takes its cut on what the BUYER paid; `principal` is the
# ex-VAT figure. Measured on jack_uk order 204-6325754-5123507: 4.50 taken on a
# 29.99 sale whose principal is 24.99 -- 15.0% of the one and 18.0% of the
# other, and only the first can be multiplied by a shelf price. Dividing by the
# principal would have overstated every VAT-registered account's fee by a fifth.
truthy("the rate is measured against what the buyer paid, not the ex-VAT figure",
       "l.sku_rev" in _fo and "SUM(revenue)" in _fo)
truthy("  and principal is deliberately not the divisor",
       "principal" not in _fo.split("SELECT f.order_id")[1].split("fetchall")[0])
truthy("  with the reason written down", "INC-VAT" in _fo)
truthy("a discounted order is left out of the rate", 'r["promos"]' in _fo)
truthy("  and so is a refunded one", 'r["refunds"]' in _fo)
truthy("  and a cancelled line", "cancelled" in _fo)
truthy("a multi-line order is shared by revenue, not counted whole",
       "sku_rev / tot_rev" in _fo)
truthy("a database that cannot be read does not stop a price",
       "must not stop a price" in _fo)

print("\n=== the quote is cached per ASIN and price, for a day ===")
truthy("the age limit is 24 hours", AF.QUOTE_MAX_AGE_HOURS == 24)
truthy("  and a price move makes a quote stale too",
       AF.QUOTE_PRICE_TOLERANCE > 0)
_ra = FEE.split("def rate_for_asin(")[1].split("\ndef ")[0]
truthy("staleness is measured in hours, not days", "max_age_hours" in _ra)
truthy("  and against the price it was quoted at", "moved = (" in _ra)
# A STALE QUOTE IS STILL AMAZON'S FIGURE. Dropping it for an average of every
# other product this account sells would be a downgrade dressed as caution.
truthy("a stale quote is still returned rather than dropped to an average",
       "def _held(" in _ra and "due a refresh" in _ra)
SCH = open(os.path.join("data", "scheduler.py"), encoding="utf-8").read()
truthy("the refresh job runs daily, matching the age limit",
       'register_job("sourcing_fees", sourcing_fees, hours=24' in SCH)
# One line of it, because the sentence wraps and matching across the break
# finds a newline rather than the words.
truthy("  and a price change is picked up by it on its own",
       "therefore picked up here on its own" in SCH)

print("\n=== the quote fetches itself, without holding the page hostage ===")
# "First time a new product appears on the sourcing page -> automatic API call
#  -> real fee shown immediately. Second time -> reads from cache, no API call."
# The danger is the OTHER case: sixty-seven uncached products on one draw, on
# two accounts whose SP-API role is not granted, each refusal costing seconds.
truthy("there is a ration on automatic calls", AF.AUTO_QUOTE_MAX > 0)
truthy("  measured over a window, not for all time",
       AF.AUTO_QUOTE_WINDOW_SECONDS > 0)
truthy("  and a page waits less for one than a batch job does",
       AF.AUTO_QUOTE_TIMEOUT_SECONDS < 30)
truthy("an account Amazon refuses is remembered, not asked 67 times",
       AF.ACCOUNT_REFUSAL_MEMO_SECONDS >= 60)
truthy("  and so is an ASIN it will not quote",
       AF.ASIN_REFUSAL_MEMO_SECONDS >= 60)

# THE RATION ACTUALLY RATIONS. Taken directly rather than by making Amazon
# calls: the slot is consumed before the call, which is the property that stops
# a screen starting five at once.
_before = list(AF._auto_calls)
try:
    AF._auto_calls[:] = []
    _got = [AF._auto_slot() for _ in range(AF.AUTO_QUOTE_MAX + 3)]
    check("the first calls get a slot", _got[:AF.AUTO_QUOTE_MAX],
          [True] * AF.AUTO_QUOTE_MAX)
    check("  and the ones past the ration do not",
          _got[AF.AUTO_QUOTE_MAX:], [False] * 3)
finally:
    AF._auto_calls[:] = _before

# THE MEMO REMEMBERS, AND FORGETS. A refusal that never expired would mean one
# bad afternoon disabled the fee lookup until the app was restarted.
AF._remember_refusal(("account", "test_ws", "UK"), 60, "not allowed")
truthy("a remembered refusal is found", AF._refusal(("account", "test_ws", "UK")))
AF._remember_refusal(("account", "test_ws", "UK"), -1, "expired")
falsy("  and an expired one is dropped", AF._refusal(("account", "test_ws", "UK")))

_ra2 = FEE.split("def rate_for_asin(")[1].split("\ndef ")[0]
truthy("the ration is taken before the call, not after", "_auto_slot()" in _ra2)
truthy("  a refused account is checked first", '_refusal(("account"' in _ra2)
truthy("  a 403 is remembered account-wide, not per product",
       '"Unauthorized" in d' in _ra2 and "ACCOUNT_REFUSAL_MEMO" in _ra2)
truthy("  and every guard ends in the same silent fall-through",
       _ra2.count("return _held(") >= 6)
# THE PRICING PATH HAS NO ACCOUNT TO HAND, so the module finds one rather than
# every caller learning how.
truthy("credentials are resolved when the caller has none",
       "if not creds:" in _ra2 and "_creds_for(" in _ra2)
_qs = FEE.split("def quote_for_sku(")[1].split("\ndef ")[0]
truthy("  and the button resolves them the same way, not its own way",
       "_creds_for(" in _qs)
falsy("    with the old duplicate lookup gone",
      'a.get("id")) == str(workspace_id)' in _qs)
truthy("the batch path is not rationed", "auto is left False" in _qs)

print("\n=== one rate, and every part of the panel follows it ===")
RUN = open(os.path.join("domain", "source_run.py"), encoding="utf-8").read()
truthy("pricing resolves through the three tiers", "_fees.rate_for_listing(" in RUN)
truthy("  asking Amazon itself, under the ration", "auto=True" in RUN)
truthy("  and a fee that cannot be fetched never delays a price",
       "never delays or breaks a price" in RUN)
truthy("the fee panel is handed the rate the price was built on",
       'rate=rule.get("referral_rate")' in RUN)
_bd = FEE.split("def breakdown_for(")[1].split("\ndef ")[0]
truthy("  and uses it instead of looking the rate up again",
       "given_rate and given_basis == ACTUAL" in _bd)
truthy("    without charging the closing fee twice",
       "already inside the measured rate above" in _bd)
JS = open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()
truthy("the screen names the settled figure as its own kind",
       "d.fee_basis === 'actual'" in JS and "from your sales" in JS)
truthy("  and says it is the number the Orders page reports",
       "same fee the Orders page reports" in JS)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
