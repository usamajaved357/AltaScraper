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
truthy("  from the cache only", "allow_quote=False" in RUN)
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

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
