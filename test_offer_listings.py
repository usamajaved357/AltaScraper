"""A me-too offer is not your product, and the app must not show them alike.

    "how can you say that they are under a different marketplace it is not
     possible, the items i listed were same in both, but i did mee too on
     nestwell goods so they were not used using the app"

Twenty-six of these were once diagnosed as "misfiled under the wrong account"
and nearly moved -- which would have taken the other account's own listings
away. The diagnosis was wrong because the drawer showed a me-too offer and an
own-brand product identically. These checks are about the three places that now
tell them apart.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


RT = read("routes", "listing_routes.py")
DA = read("static", "js", "drawer_attributes.js")
LE = read("static", "js", "listrow_edit.js")

# Pull _offer_shape out and run it, rather than asserting on its source.
_src = RT[RT.index("def _offer_shape"):]
_end = _src.find("\n    @app.route")
_body = _src[:_end] if _end > 0 else _src
_ns = {}
exec("\n".join(l[4:] if l.startswith("    ") else l
               for l in _body.splitlines()), _ns)
shape = _ns["_offer_shape"]

print("\ntelling an offer apart from your own product")
# THE FACT IS merchant_suggested_asin, not a count of attributes. It is the
# seller naming the ASIN they are joining, and Rule 1 forbids this app sending
# one -- so anything carrying it was made elsewhere.
off = shape({"merchant_suggested_asin": [{"value": "B0H8TFYNB9"}],
             "condition_type": [{"value": "new_new"}],
             "fulfillment_availability": [{"quantity": 3}]})
check("an offer is recognised", off["kind"], "offer")
check("and it names the ASIN being joined", off["asin"], "B0H8TFYNB9")
truthy("it says the product data is not yours to edit",
       "cannot change what shoppers see" in off["why"])
truthy("and that price and stock ARE yours",
       "Price, stock and handling time ARE yours" in off["why"])

own = shape({"brand": [{"value": "Selvora"}],
             "item_name": [{"value": "A thing"}]})
check("your own product is recognised", own["kind"], "own")
check("and names no ASIN, because it joined none", own["asin"], "")

# NOT INFERRED FROM A COUNT. A rich offer and a sparse own listing both exist,
# and counting attributes would call each of them the other.
many = dict({"merchant_suggested_asin": [{"value": "B0TEST"}]},
            **{("f%d" % i): [{"value": i}] for i in range(30)})
check("a well-filled offer is still an offer", shape(many)["kind"], "offer")
check("a sparse own listing is still your own",
      shape({"brand": [{"value": "x"}]})["kind"], "own")

# AN EMPTY ANSWER IS NOT EVIDENCE OF EITHER, and guessing would put a warning
# on a listing nobody has read yet.
check("no attributes at all is unknown, not 'own'", shape({})["kind"], "unknown")
truthy("and it says why", "nothing to tell the two apart" in shape({})["why"])

# Amazon sends attributes as a list of objects; a bare string is not the shape
# but has been seen, so it is read rather than crashed on.
check("a bare string ASIN is still read",
      shape({"merchant_suggested_asin": "B0BARE"})["asin"], "B0BARE")

print("\nthe drawer says so, and only where there is something to say")
truthy("the route hands the shape to the browser", '"shape": _offer_shape(' in RT)
truthy("the drawer keeps it", "shape:j.shape" in DA)
truthy("and draws a bar for it", "function lvShapeBar(" in DA)
_bar = DA[DA.index("function lvShapeBar("):]
_bar = _bar[:_bar.index("\n/*", 10)] if "\n/*" in _bar[10:] else _bar[:800]
# NO BANNER ON YOUR OWN LISTINGS. A warning on every listing is a warning on
# none, and this one is only true of offers.
truthy("nothing is drawn for your own product", 'kind !== "offer"' in _bar)
truthy("nor for one Amazon returned nothing for", 'kind === "unknown"' in _bar)

print("\nAmazon's mismatch says which value is whose")
truthy("there is a renderer for one issue", "function lvIssueHtml(" in DA)
_iss = DA[DA.index("function lvIssueHtml("):]
_iss = _iss[:_iss.index("\nfunction ", 10)]
truthy("it labels the first value as yours", "Yours:" in _iss)
truthy("and the second as the ASIN's", "The ASIN\\'s:" in _iss or "ASIN\\'s" in _iss)
# THE POINT OF THE WHOLE THING. "Merchant 1 / Amazon 2" on number_of_items
# means the barcode matched a 2-pack; copying Amazon's 2 would build a
# piggyback listing on somebody else's ASIN, which Rule 1 forbids.
truthy("it warns against copying the ASIN's value",
       "would join somebody else" in _iss)
# CLAUDE.md Rule 4's parsing rule: the attribute NAME comes from the structured
# field, never from the prose. That is the "The"/"Your" phantom-field bug.
truthy("the values are only read once Amazon named an attribute",
       "if(names.length)" in _iss)

print("\nstock stays editable on a listing this app holds no draft of")
# The guard turned EVERY box read-only without a draft row. Price, cost and
# handling are written into the row and genuinely cannot work; stock goes to
# /stock/bulk_update and patches Amazon by SKU, so it always could.
# THE FLAG SPLIT IN TWO on 8 Sep 2026. `live` was carrying both "reaches
# Amazon" and "is stored on our row", which held until cost turned out to be
# neither -- it goes nowhere near Amazon AND lives in the COGS store keyed by
# (account, sku). Reading `live` here meant "does not reach Amazon" was taken to
# mean "must be on our row", and the cost box was refused on every listing with
# no draft:
#
#     "for many listings i dont have an option to put the cogs, i should be able
#      to put the cogs"
#
# The invariant is the same one: the guard asks about the FIELD, not about the
# row alone.
truthy("the guard asks whether the field needs a row at all",
       "const _needsRow = !_f || _f.needsRow !== false" in LE)
truthy("and only then refuses", "if(_needsRow && o.sku" in LE)
truthy("stock is declared as going live to Amazon",
       re.search(r"qty:\s*\{label:[^}]*live:\s*true", LE) is not None)
for f in ("price", "cost", "handling"):
    truthy("%s is declared as needing the row" % f,
           re.search(r"%s:\s*\{label:[^}]*live:\s*false" % f, LE) is not None)
# Matched on a phrase that is NOT split across the source's concatenated lines.
# "Stock is different" reads as one string on screen and is two in the file.
truthy("the read-only tooltip says stock is the exception",
       "goes straight to Amazon, so it stays editable" in LE)

print("\nnothing here sends a merchant_suggested_asin (Rule 1)")
# The app READS the attribute to recognise an offer somebody else made. It must
# never WRITE one -- that is what would turn its own listings into piggybacks.
for f in ("routes/listing_routes.py",):
    src = read(*f.split("/"))
    body = re.sub(r'(?s:""".*?""")', "", src)
    body = re.sub(r"(?m:^\s*#[^\n]*)", "", body)
    sends = re.search(r'"merchant_suggested_asin"\s*:\s*[^=\s]', body)
    check("%s never builds one into a payload" % f, bool(sends), False)

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
