"""A barcode another listing owns is reported, and the exemption is opt-in.

    "i submitted a listing on amazon from the app but it shows submitted and i
     dont know if it is live on amazon ... where is the error message"

It was never live. Amazon had refused it and had said why the whole time:

    "The standard product ids (such as UPC, ISBN, EAN, or JAN codes) provided
     matches the ASIN B0H8Q3VMPD, but some of the [data is different]"
    "Your offer to the SKU cannot be added because the product is not in the
     catalogue."

MEASURED on his own store: EAN 4545644574860 was on jack_uk/8.99_5Days_B09BNLQG2Q,
which is LIVE, and on the nestwell_goods listing he had just submitted. Amazon
matched the barcode to the live one and would not create a second product.
SIXTEEN barcodes are on more than one listing, one of them on three. Nothing had
ever looked.

    "maybe i used the barcode of my another listing, so the app should tell me"

AND THE EXEMPTION IS NOW HIS DECISION:

    "i dont want to use the gtin exemption until the user wants to, he can check
     the button under the box apply for gtin exemption as we have in amazon
     backend, dont apply for exemption automatically"

It used to be claimed automatically whenever the barcode box was empty or the
value unusable -- because CLAUDE.md Rule 1 said to. That instruction has been
changed by the owner and the rule file changed with it, so the file and the code
agree; otherwise the next reader of CLAUDE.md puts the old behaviour back.
Claiming an exemption is a declaration to Amazon that a product has no barcode,
and the app must not make it for him.
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


from domain import barcode_clash as BC

print("=== the same barcode written differently is the same barcode ===")
# This is the whole reason it cannot be a string compare: a GTIN-14 is a 13
# digit code with a packaging indicator on the front.
codes = ["4545644574860", "04545644574860", "4545-6445-74860", " 4545644574860 "]
seen = {BC._code(c) for c in codes}
check("all four forms normalise to one code", len(seen), 1)
check("  and it is the EAN-13", seen.pop(), "4545644574860")
check("rubbish is not a code", BC._code("not a barcode"), "")
check("empty is not a code", BC._code(""), "")

print("\n=== who else has it, on the owner's real data ===")
cl = BC.others_with("config.json", "4545644574860",
                    exclude_workspace="nestwell_goods",
                    exclude_sku="11.59_3Days_B0DNJH3CRX")
truthy("the clash is found", len(cl) >= 1)
if cl:
    check("  it is the jack_uk listing", cl[0]["sku"], "8.99_5Days_B09BNLQG2Q")
    truthy("  and it is live, which is why Amazon refused", cl[0]["live"])
# THE LIVE ONE FIRST. It is the listing Amazon says owns the code, so it is the
# one the reader has to deal with.
truthy("a live clash sorts to the front",
       all(c["live"] for c in cl[:1]) or not any(c["live"] for c in cl))
truthy("the padded form finds the same clash",
       len(BC.others_with("config.json", "04545644574860")) ==
       len(BC.others_with("config.json", "4545644574860")))
check("a listing is not reported as clashing with itself",
      [c for c in BC.others_with("config.json", "4545644574860",
                                 exclude_workspace="jack_uk",
                                 exclude_sku="8.99_5Days_B09BNLQG2Q")
       if c["sku"] == "8.99_5Days_B09BNLQG2Q"], [])

print("\n=== what it says ===")
s = BC.sentence(cl, "4545644574860")
truthy("it names the barcode", "4545644574860" in s)
truthy("  and the listing that owns it", "8.99_5Days_B09BNLQG2Q" in s)
truthy("  and what Amazon will do", "refuse" in s)
truthy("  and the two ways out", "different barcode" in s and "exemption" in s)
check("nothing to say when there is no clash", BC.sentence([]), "")

print("\n=== the whole problem at once ===")
allc = BC.scan("config.json")
truthy("more than one barcode is shared", len(allc) > 1)
truthy("  the worst offender is listed first",
       allc[0]["count"] >= allc[-1]["count"])
truthy("  and every entry names its listings",
       all(len(c["listings"]) == c["count"] for c in allc))
print("     (%d barcodes on more than one listing right now)" % len(allc))

print("\n=== the exemption is opt-in, in the generator ===")
G = open("amazon_listing_generator.py", encoding="utf-8").read()
truthy("it reads a per-listing tick", 'g("GTIN Exemption")' in G)
truthy("  and only claims the exemption when it is set", "elif _exempt_asked:" in G)
# THE THIRD BRANCH IS THE POINT. Neither identifier -> send neither.
truthy("neither barcode nor tick sends NEITHER",
       'A.pop("supplier_declared_has_product_identifier_exemption", None)' in
       G.split("elif _exempt_asked:")[1])
truthy("  and says so rather than going quiet",
       "No product identifier" in G)
truthy("a real barcode still drops any exemption claim",
       'A.pop("supplier_declared_has_product_identifier_exemption", None)' in
       G.split("_barcode, _typ, _why = gtin_or_reason")[1][:600])

print("\n=== the column exists everywhere it has to ===")
CM = open(os.path.join("data", "column_map.py"), encoding="utf-8").read()
truthy("the header maps to a column", '"GTIN Exemption":         "gtin_exemption"' in CM)
DB = open(os.path.join("data", "db.py"), encoding="utf-8").read()
truthy("the column is added to the table",
       '("listings", "gtin_exemption", "TEXT")' in DB)
D = open("dashboard.py", encoding="utf-8").read()
truthy("and it is editable, so the tick can be saved",
       '"GTIN Exemption"' in D.split("_EDITABLE_COLS = {")[1][:600])

print("\n=== the screen says it BEFORE the submit ===")
R = open(os.path.join("routes", "listing_routes.py"), encoding="utf-8").read()
truthy("the row carries an identifier verdict", "def _attach_identifier(" in R)
_fn = R.split("def _attach_identifier(")[1].split("\ndef ")[0]
truthy("  a live clash blocks", '"blocking"] = True' in _fn)
truthy("  no barcode and no tick blocks too", "exemption is not ticked" in _fn)
truthy("  a ticked exemption is stated, not hidden",
       "declares to Amazon" in _fn)
truthy("  and it is attached to the drawer's row",
       "_attach_identifier(c, r, CONFIG_PATH" in R)
JS = open(os.path.join("static", "js", "listings.js"), encoding="utf-8").read()
truthy("the drawer draws it", "function identifierPanel(" in JS)
# The drawer was rebuilt to the listing-editor-lighter design on 29 Aug 2026
# and no longer interpolates these two straight into one template literal --
# it assigns them, then puts them in the always-on block above the hero. So
# the check moved to _dwShell, and it now asserts the thing that actually
# matters rather than a spelling: the panel is above the compliance banner AND
# it is NOT one of the folds. A barcode already on another listing has to be
# REPORTED (CLAUDE.md Rule 1), and a report behind a collapsed summary has not
# been made.
_shell = JS.split("function _dwShell(")[1].split("\nfunction ")[0]
truthy("  above the compliance banner",
       _shell.index("identifierPanel(r)") < _shell.index("complianceBanner(r)"))
truthy("  drawn open at the top, never folded away",
       "dw2-alwayson" in _shell
       and _shell.index("${alwaysOn}") < _shell.index("${heroBlock}")
       and "dwFold" not in _shell)
truthy("  with the tick box", "Apply for GTIN exemption" in JS)
truthy("  saying what ticking it declares", "it is a declaration" in JS)
truthy("  and the tick saves", "function setGtinExemption(" in JS)

print("\n=== the rule file and the code now agree ===")
C = open("CLAUDE.md", encoding="utf-8").read()
truthy("CLAUDE.md says the exemption is the owner's decision",
       "THE GTIN EXEMPTION IS THE OWNER'S DECISION" in C)
truthy("  quoting the instruction that changed it",
       "dont apply for exemption automatically" in C)
falsy("  and no longer tells the app to claim it automatically",
      "When no real GS1-registered barcode is available, use the GTIN exemption"
      in C)
truthy("  and a clashing barcode must be reported",
       "MUST BE REPORTED" in C)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
