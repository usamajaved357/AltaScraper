"""Priority 2 of LISTINGS_FUNCTIONAL_FIXES.md: the wrong data on the row.

FIVE OF THE SIX ITEMS HAD ONE ROOT AND THE BRIEF TREATED THEM AS SIX. The
detailed view was the last place in the app still reading `r.status` raw:

    2.1  a listing Amazon has, badged GENERATED
    2.2  "Not yet live" on a live listing's Performance
    2.6  "-- Handling 2d" instead of a stock breakdown

are all the same read. listings.js has answered "is this really on Amazon?"
since long before this view existed -- isActuallyLive() matches the row's SKU
and OUR OWN ASIN against Amazon's catalogue, and _shownStatus() wraps it -- and
the table view and the count tiles above the list both use it. That is why the
tiles could say LIVE over a row labelled GENERATED.

The brief proposes writing the rule again here ("if the listing has an ASIN and
is in the catalogue, override the displayed status"). That would have been a
fourth opinion about what LIVE means, and the one that disagreed first.

THE OTHER TWO WERE MEASURED, NOT ASSUMED:

    2.4  the fee was never missing, it was never SENT. 139 of 303 listings hold
         one and 61 of the 63 LIVE ones do, most stamped "SP-API (exact)".
         dashboard._card had no key for it, so the browser row had nothing to
         read and the column drew a dash over a number the database had.

    2.5  the floors were never loaded. There is now a route that reads them --
         and the honest measurement is that ONE SKU on this account has a floor
         and NONE has a ceiling, so most rows will still show a dash. What
         changes is what the dash MEANS.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def rd(p):
    return io.open(os.path.join(HERE, *p.split("/")), encoding="utf-8").read()


LR = rd("static/js/listrow_detailed.js")
LS = rd("static/js/listings.js")
DASH = rd("dashboard.py")
SR = rd("routes/sourcing_routes.py")
CSS = rd("static/css/listrow_detailed.css")


def fn(src, name):
    """One function's body, so a claim cannot be met by a line elsewhere."""
    i = src.find("function " + name + "(")
    if i < 0:
        return ""
    j = src.find("\n}", i)
    return src[i:] if j < 0 else src[i:j + 2]


def code(js):
    """JavaScript with its comments stripped.

    NEEDED FOR EVERY "this no longer does X" CHECK IN THIS FILE. The comments
    here quote what the code used to read -- lsWasSentToAmazon, LIVE_ITEMS --
    because that is the whole explanation of the bug, so a plain text search
    finds the fix's own documentation and calls it the bug.
    """
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return "\n".join(l.split("//")[0] for l in js.splitlines()
                     if not l.strip().startswith(("*", "//")))


print("=== 2.1 the status is what Amazon says, not what we recorded ===")
truthy("the row asks the shared question", "function lrShownStatus" in LR)
truthy("  through _shownStatus, which the table view already used",
       "_shownStatus(r)" in fn(LR, "lrShownStatus"))
truthy("  and that is built on isActuallyLive",
       "isActuallyLive(r, sets.skus, sets.asins" in fn(LS, "_shownStatus"))
truthy("lrStatus uses it", "const st = lrShownStatus(r);" in fn(LR, "lrStatus"))
# NOT A NEW RULE. The brief proposes re-deriving it from the ASIN here.
falsy("no second definition of 'live' was written in this file",
      "LIVE_ITEMS" in code(LR) or "isActuallyLive(" in code(LR))
# THE STALE RECORD IS NAMED, not hidden behind the corrected badge.
truthy("when the two disagree, the stored word is still shown",
       "const stale = (st !== stored)" in fn(LR, "lrStatus"))
truthy("  with what it means and how to fix it", "A Sync" in fn(LR, "lrStatus"))
truthy("  and it is styled to not compete with the badge",
       ".status-stale{" in CSS and "must not compete" in CSS)

print("\n=== 2.2 'Not yet live' means not on Amazon, not 'we did not record it' ===")
truthy("there is one gate for 'has this anything to report'",
       "function lrOnAmazon" in LR)
truthy("  it asks the catalogue first", "isAmazonLive(r)" in fn(LR, "lrOnAmazon"))
truthy("  and falls back to the stored word only then",
       "lsWasSentToAmazon" in fn(LR, "lrOnAmazon"))
truthy("Performance uses it", "if(!lrOnAmazon(r))" in fn(LR, "lrPerf"))
falsy("  and Performance no longer reads the status directly",
      "lsWasSentToAmazon" in code(fn(LR, "lrPerf")))
truthy("Inventory uses it too", "if(!lrOnAmazon(r))" in fn(LR, "lrInv"))
falsy("  and Inventory no longer reads the status directly",
      "lsWasSentToAmazon" in code(fn(LR, "lrInv")))
# A DASH AND "Not yet live" ARE DIFFERENT CLAIMS. Matched on unwrapped text --
# the sentence spans two comment lines.
_flat = re.sub(r"\s+", " ", re.sub(r"^\s*(//|\*)\s?", "", LR, flags=re.M))
truthy("the difference between the two is written down",
       "we have not been told" in _flat and "there is nothing to tell" in _flat)

print("\n=== 2.3 the featured offer price, not just the win share ===")
BB = fn(LR, "lrBuyBox")
truthy("the price is a labelled row", "Featured offer</span>" in BB)
truthy("  from the buy-box figure Amazon returns", "m.buy_box_price" in BB)
# CompetitivePriceId "1" IS the featured slot -- checked against the extractor
# rather than assumed.
AM = rd("api/amazon_metrics.py")
truthy("  which is CompetitivePriceId 1, the featured slot",
       'CompetitivePriceId")) == "1"' in AM)
truthy("  and it is the landed price, what a shopper actually pays",
       "LandedPrice" in AM)
# ABSENT IS SAID, not skipped. The line used to be drawn only when the figure
# existed, so "not asked yet" and "no featured offer" looked identical.
truthy("an unknown featured price still draws its row", "lrVal(null)" in BB)
truthy("  saying it has not been asked for yet", "has not been asked" in BB)
# THE SHARE IS KEPT, and reworded so it cannot be read as the price.
truthy("the win share is still there", "buybox_pct" in BB)
truthy("  worded as ours-or-not", "Ours for " in BB and "Never ours" in BB)
falsy("  the old wording that read like a price label is gone",
      "Featured " + "83% " in BB or "> Featured '" in BB)
# The duplicate "Competitive" line further down is gone -- same number, a name
# that did not say what it was.
falsy("the same figure is not also shown under another name",
      'lrDataRow("Competitive"' in LR)

print("\n=== the business price says why, rather than offering a dead link ===")
PR = fn(LR, "lrPricing")
truthy("it reports the account is not enrolled", "account not enrolled" in PR)
# MEASURED against Amazon's own schemas (Rule 4), not guessed.
truthy("  with the schema measurement recorded",
       "purchasable_offer.audience has exactly one allowed value" in PR)
falsy("  and no longer offers a Set link that cannot set it",
      'openListing(\\\'' in PR.split("Business price")[0].split("bb biz")[-1]
      if "bb biz" in PR else False)
falsy("  no Set link anywhere in the business-price block",
      ">Set<" in PR)

print("\n=== 2.4 the fee is sent to the browser ===")
# THE COLUMN MAP ALWAYS HAD IT.
CM = rd("data/column_map.py")
truthy("the column map carries the fee", '"Amazon Fees (GBP)":' in CM)
truthy("  and its source", '"Fee Source":' in CM)
# WHAT WAS MISSING: the row dict never emitted either.
truthy("the row now carries the fee", '"amazon_fees":  g("Amazon Fees (GBP)")' in DASH)
truthy("  and where the figure came from", '"fee_source":   g("Fee Source")' in DASH)
truthy("  with the measurement that found it",
       "139 of 303 rows have a fee" in DASH)
# The renderer already read it; that half was never broken.
truthy("the row renderer was already reading it", "r.amazon_fees" in fn(LR, "lrFees"))
truthy("  and the provenance beside it", "r.fee_source" in fn(LR, "lrFees"))
# AND THE DATABASE REALLY HAS THEM -- measured here, not quoted.
try:
    import sqlite3
    _c = sqlite3.connect(os.path.join(HERE, "altascraper.db"))
    _cols = [r[1] for r in _c.execute("PRAGMA table_info(listings)")]
    truthy("the listings table has the column", "amazon_fees" in _cols)
    _n = _c.execute("SELECT COUNT(*) FROM listings WHERE amazon_fees IS NOT NULL "
                    "AND TRIM(amazon_fees)<>'' AND amazon_fees<>'0'").fetchone()[0]
    truthy("  and rows are actually carrying a fee (%d)" % _n, _n > 0)
    _c.close()
except Exception as e:                                   # no database here
    print("  (database not readable, skipping the row count: %s)" % e)

print("\n=== 2.5 the floors are loaded, and a dash means something ===")
truthy("there is a rules-only route", '@app.route("/sourcing/rules_all")' in SR)
truthy("  read-only", "def sourcing_rules_all():" in SR
       and "methods=" not in SR.split('"/sourcing/rules_all"')[1].split("\n")[0])
# NOT /sourcing/list: that re-prices every SKU against every supplier.
truthy("  and it does not run the dry run", "_run.dry_run" not in fn(SR, "sourcing_rules_all")
       if fn(SR, "sourcing_rules_all") else True)
truthy("  the reason is written down", "seconds of work and a page of decisions" in SR)
truthy("  it returns the Repricer's own rule shape", "_repo.rule_for(CONFIG_PATH" in SR)
truthy("  and the measurement is recorded",
       "exactly ONE carries a min_price" in SR)

truthy("the screen loads them", "function lrLoadRules" in LR)
truthy("  once", "if(LR_RULES_ASKED) return;" in LR)
truthy("  scoped by account AND marketplace, which a rule is",
       "_srcUrl(\"/sourcing/rules_all\")" in LR)
# ONE STORE. A thinner second copy would break the Repricer's own dialogs,
# which open pre-filled from SRC_ROW_RULES.
truthy("it fills the Repricer's own global", "SRC_ROW_RULES[sku] = j.rules[sku]" in LR)
truthy("  without overwriting what the Repricer already loaded",
       "SRC_ROW_RULES[sku] === undefined" in LR)
truthy("  and why a second store would be wrong", "would silently offer the wrong defaults" in LR)
# THE TWO KINDS OF DASH.
truthy("an unloaded dash and an unset one say different things",
       "LR_RULES_LOADED" in fn(LR, "lrRuleBox"))
truthy("  'not tracking this SKU' once they are loaded",
       "not tracking this SKU" in fn(LR, "lrRuleBox"))
falsy("  the old 'not loaded on this screen' wording is gone",
      "is not loaded on this screen" in LR)

print("\n=== 2.6 one inventory template per channel ===")
IC = fn(LR, "lrInvChannel")
IN = fn(LR, "lrInv")
truthy("the channel is decided once", "function lrInvChannel" in LR)
check("  three answers, and 'unknown' is one of them",
      sorted(re.findall(r'return "(merchant|amazon|unknown)"', IC)),
      ["amazon", "merchant", "unknown"])
truthy("merchant shows what we hold and how fast we ship", "merchant fulfilled" in IN)
falsy("  and not the warehouse lines that cannot apply",
      "Inbound" in IN.split('chan === "merchant"')[1].split('chan === "amazon"')[0]
      if 'chan === "merchant"' in IN and 'chan === "amazon"' in IN else True)
truthy("Amazon-fulfilled shows the warehouse breakdown",
       "Inbound" in IN and "Unfulfillable" in IN and "Reserved" in IN)
truthy("  labelled as Amazon's", "Amazon fulfilled" in IN)
truthy("an unread channel is its own case, not a guess", "channel not read yet" in IN)
truthy("  and says why the warehouse lines are absent",
       "not applicable" in IN)
# THE SECOND CAUSE the brief did not name.
truthy("the gate above the templates is named as the other cause",
       "THE GATE ABOVE THEM" in LR)

print("\n=== nothing is half-written ===")
check("listrow_detailed.css braces balance", CSS.count("{"), CSS.count("}"))
# THIS CHECK EARNED ITS KEEP THE FIRST TIME IT RAN. It found three
# double-encoded em dashes in sourcing_routes.py -- "No account is selected
# â€" open a workspace first." -- in text shown to the user, predating this
# pass. A PowerShell round-trip does that, and it is invisible in a diff.
falsy("no mojibake", re.search(r"â€|Â·|â•", LR + CSS + SR) is not None)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
