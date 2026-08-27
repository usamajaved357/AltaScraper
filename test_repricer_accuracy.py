"""The Repricer shows the seller's own data, and one price at a time.

Three defects found by reading the rendered screen back and comparing every
figure with the decision it claims to represent. All three were things a person
would believe.

1. A COMPETITOR'S ASIN SHOWN AS THE SELLER'S OWN.

   The row read `cur.asin || it.asin`. cur is Amazon's snapshot; `it` is the
   shared catalogue, asked with include_drafts so a never-sent SKU still gets a
   PICTURE. For a SKU Amazon has no record of, the only asin available is the
   draft's -- and CLAUDE.md Rule 1 is explicit about what that is:

       "The ASIN in the SKU format ... is a COMPETITOR REFERENCE used only
        during generation to pull product data. It is not the target listing."

   Measured on jack_uk: six rows showed somebody else's ASIN under the seller's
   own product name, each a link straight to that competitor's page.

   WORSE IN THE SHEET. The min-price template had the same fallback, and the
   upload matches by ASIN when the SKU is missing -- so a competitor's code in
   that column could attach a floor to whichever of the seller's SKUs happened
   to sit on that ASIN.

2. TWO FEE RATES ON ONE PANEL.

   decide_one resolves the real referral rate -- Amazon's quote for the ASIN,
   or this account's measured average -- and prices with it. The route then
   built a SECOND rule for the supplier table from rule_for + defaults, whose
   referral_rate is NULL and so filled in at 15%.

   So the tiles and the bar were at 17.5% and the supplier table beneath them
   at 15%: "you keep" disagreed with "profit / unit" by 0.34 on a 13.42 price,
   inches apart, with nothing saying why.

3. A LOSS DRAWN IN GREEN, in a column headed "You keep". Three suppliers on
   jack_uk were showing a negative figure in the same green as a profit.
"""
import io
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
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


JS = io.open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()
RT = io.open(os.path.join("routes", "sourcing_routes.py"),
             encoding="utf-8").read()

print("=== 1. only OUR ASIN is ever shown as ours ===")
truthy("the row takes it from Amazon's snapshot alone",
       'const asin = String(cur.asin || "");' in JS)
falsy("  never falling back to the catalogue item",
      "cur.asin || it.asin" in JS)
# The draft's asin is still WORTH KNOWING -- it says what the listing was
# modelled on. It is kept, named as a competitor, and never linked.
truthy("  the draft's is kept separately", "const draftAsin =" in JS)
truthy("  labelled as somebody else's product",
       "(a competitor)" in JS or "a COMPETITOR" in JS)
_link = JS.split('class="rp-asin"')[1][:260]
truthy("  and only a real ASIN is ever a link",
       "_srcAmzHost()" in _link)
# A LINK TO THE WRONG STORE IS ALSO WRONG. It was hardcoded to .co.uk for every
# account, including the two that sell in dollars.
truthy("the link follows the marketplace", "function _srcAmzHost(" in JS)
truthy("  US goes to amazon.com", 'US: "com"' in JS)
truthy("  UK to amazon.co.uk", 'UK: "co.uk"' in JS)

print("\n=== the sheet carries our ASIN or none ===")
_tpl = RT.split("def sourcing_minprice_template")[1].split("@app.route")[0]
truthy('the ASIN column is cur.asin only', 'cur.get("asin") or "",' in _tpl)
falsy("  with no catalogue fallback",
      'cur.get("asin") or item.get("asin")' in _tpl)
# Why it matters more here than on screen.
_up = RT.split("def sourcing_minprice_upload")[1].split("@app.route")[0]
truthy("  because the upload matches by ASIN when a SKU is missing",
       "by_asin" in _up)
truthy("    and refuses an ambiguous one rather than guessing",
       "cannot tell which" in _up)

print("\n=== 2. one fee rate per panel ===")
truthy("the supplier table is built with the rate the DECISION used",
       '_rule["referral_rate"] = _fr' in RT)
truthy("  taken off the breakdown, not resolved a second time",
       '.get("breakdown") or {}).get("fee_rate")' in RT)
# ...and at the same PRICE as the tiles above it.
truthy("and at the price the panel is about",
       '_sell = ((d.get("decision") or {}).get("price")' in RT)
truthy("  falling back to today's when nothing changes",
       'or (d.get("current") or {}).get("price"))' in RT)
truthy("  with the column saying which price that is",
       "'You keep' + (_at != null" in JS)

print("\n=== 3. a loss is not green ===")
truthy("a negative 'you keep' is red",
       "s.profit < 0 ? 'var(--red)'" in JS)

print("\n=== and the arithmetic still holds on the real data ===")
# Not a code check: the actual rows, from the real database.
from domain import source_repo as REPO
from domain import source_run as RUN

CFG, WS, MKT = "config.json", "jack_uk", "UK"
try:
    rows = REPO.enrolled(CFG, WS, MKT)
except Exception:
    rows = []
if not rows:
    print("  (nothing tracked on %s -- the live half is not exercised)" % WS)
else:
    bad_asin = bad_sum = seen = 0
    for e in rows:
        cur, d = RUN.decide_one(CFG, WS, MKT, e["sku"])
        b = d.get("breakdown") or {}
        # OUR ASIN never comes out of the SKU name
        a = str(cur.get("asin") or "")
        if a and not cur.get("found"):
            bad_asin += 1
        if b.get("price") is None:
            continue
        seen += 1
        parts = (b["cost"] + b["fee"] + b["postage_label"] + b["ads"]
                 + b["profit"])
        if abs(parts - b["price"]) > 0.02:
            bad_sum += 1
    check("no ASIN is reported for a SKU Amazon does not have", bad_asin, 0)
    check("every priced row's parts add up to its price", bad_sum, 0)
    truthy("  and that was checked on real rows", seen > 0)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
