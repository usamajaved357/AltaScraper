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

# ---------------------------------------------------------------------------
# A FIXTURE OF ITS OWN (28 Sep 2026). The clash checks used to run against the
# owner's real store and his real EAN; they now run against a temp database
# seeded with the same SHAPE of problem, with invented (check-digit valid)
# barcodes and invented SKUs:
#
#   FIX_EAN   on jack_uk (LIVE), on nestwell_goods (the draft just submitted)
#             and on green_haven_goods (a draft) -- one code on three listings
#   FIX_EAN2  on two nestwell_goods drafts -- a second shared code
#   one listing with a barcode nobody else has, which must not be reported
# Environment set BEFORE any app import, so nothing resolves the real files.
# ---------------------------------------------------------------------------
import json as _jsonf
import tempfile as _tmpf

_FIX = _tmpf.mkdtemp(prefix="fixt_barcode_")
CFG = os.path.join(_FIX, "config.json")
_DBP = os.path.join(_FIX, "altascraper.db")
with open(CFG, "w", encoding="utf-8") as _fh:
    _jsonf.dump({"anthropic_api_key": "test-placeholder-not-a-key",
                 "accounts": [{"id": w, "name": w, "marketplace": "UK"} for w in
                              ("jack_uk", "nestwell_goods", "green_haven_goods")]},
                _fh)
os.environ["CONFIG_PATH"] = CFG
os.environ["ALTASCRAPER_DB"] = _DBP

FIX_EAN = "5012345678900"
FIX_EAN2 = "4006381333931"
LIVE_SKU = "8.99_5Days_B000FIXT01"       # jack_uk, LIVE -- owns FIX_EAN at Amazon
NEW_SKU = "11.59_3Days_B000FIXT02"       # nestwell_goods, the one just submitted


def _seed():
    from data import db as _sdb
    from data.store import ListingStore
    assert os.path.abspath(_sdb.db_path(CFG)) == os.path.abspath(_DBP)
    assert os.path.dirname(os.path.abspath(_DBP)) == os.path.abspath(_FIX)
    for ws, sku, upc, st in (
            ("jack_uk", LIVE_SKU, FIX_EAN, "LIVE"),
            ("nestwell_goods", NEW_SKU, FIX_EAN, "GENERATED"),
            ("green_haven_goods", "7.49_2Days_B000FIXT03", FIX_EAN, "GENERATED"),
            ("nestwell_goods", "5.99_3Days_B000FIXT04", FIX_EAN2, "GENERATED"),
            ("nestwell_goods", "6.99_3Days_B000FIXT05", FIX_EAN2, "GENERATED"),
            ("jack_uk", "4.99_3Days_B000FIXT06", "9780201379624", "GENERATED")):
        ListingStore(ws, config_path=CFG).upsert_row(
            {"SKU": sku, "UPC": upc, "Status": st, "Title": "Fixture " + sku})


_seed()

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

print("\n=== who else has it, on the fixture store (the owner's case, re-made) ===")
cl = BC.others_with(CFG, FIX_EAN,
                    exclude_workspace="nestwell_goods",
                    exclude_sku=NEW_SKU)
truthy("the clash is found", len(cl) >= 1)
if cl:
    check("  it is the jack_uk listing", cl[0]["sku"], LIVE_SKU)
    truthy("  and it is live, which is why Amazon refused", cl[0]["live"])
# THE LIVE ONE FIRST. It is the listing Amazon says owns the code, so it is the
# one the reader has to deal with.
truthy("a live clash sorts to the front",
       all(c["live"] for c in cl[:1]) or not any(c["live"] for c in cl))
# The draft on green_haven_goods sorts alphabetically BEFORE jack_uk, so the
# live listing is only first because the live-first rule put it there -- this
# is a real test of the ordering, not an accident of the names.
check("  and every other holder is still reported", len(cl), 2)
truthy("the padded form finds the same clash",
       len(BC.others_with(CFG, "0" + FIX_EAN)) ==
       len(BC.others_with(CFG, FIX_EAN)) == 3)
check("a listing is not reported as clashing with itself",
      [c for c in BC.others_with(CFG, FIX_EAN,
                                 exclude_workspace="jack_uk",
                                 exclude_sku=LIVE_SKU)
       if c["sku"] == LIVE_SKU], [])
check("a barcode on one listing only is no clash",
      BC.others_with(CFG, "9780201379624", exclude_workspace="jack_uk",
                     exclude_sku="4.99_3Days_B000FIXT06"), [])

print("\n=== what it says ===")
s = BC.sentence(cl, FIX_EAN)
truthy("it names the barcode", FIX_EAN in s)
truthy("  and the listing that owns it", LIVE_SKU in s)
truthy("  and what Amazon will do", "refuse" in s)
truthy("  and the two ways out", "different barcode" in s and "exemption" in s)
check("nothing to say when there is no clash", BC.sentence([]), "")

print("\n=== the whole problem at once ===")
allc = BC.scan(CFG)
truthy("more than one barcode is shared", len(allc) > 1)
truthy("  the worst offender is listed first",
       allc[0]["count"] >= allc[-1]["count"])
# Pinned to the fixture: 3-listing code first, and the unshared one absent.
check("  exactly the two shared codes, worst first",
      [(c["code"], c["count"]) for c in allc], [(FIX_EAN, 3), (FIX_EAN2, 2)])
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

# THE WRITE MOVED OUT OF listings.js on 7 Sep 2026, when the owner asked for a
# second way to claim the exemption:
#
#     "ONLY EXEMPT WHEN USER SELECTS MULTIPLE DRAFTS AND CLICK ON APPLY FOR
#      GTIN EXEMPTION OR DO IT INSIDE THE PDP ONE BY ONE"
#
# Two ways of declaring the same thing to Amazon, written in two files, is the
# duplication Rule 12 exists to stop. gtin.js owns the write; the bulk route is
# a loop over the single route, not a second copy of it.
G = open(os.path.join("static", "js", "gtin.js"), encoding="utf-8").read()
truthy("  and the tick saves, from the file that owns the write",
       "function setGtinExemption(" in G)
falsy("    which listings.js no longer does itself",
      "function setGtinExemption(" in JS)
truthy("  the bulk route exists for several drafts at once",
       "function bulkGtinExemption(" in G)
# RE-PINNED (28 Sep 2026): the bulk call now also passes the account the drafts
# were selected in -- `_gtinWrite(sku, claim, acct)` -- so the match is on the
# call's start. Still one fetch to /edit, still the same writer.
truthy("    and goes through the SAME write, not a second one",
       G.count("fetch(\"/edit\"") == 1 and "_gtinWrite(sku, claim" in G)
truthy("    drafts only -- a catalogue-only listing has no box to tick",
       "splitByDraft" in G)
truthy("    and it says what is being declared before it does it",
       "HAVE NO BARCODE" in G)

# THE BUTTON HAS TO BE REACHABLE, or the second route the owner asked for does
# not exist as far as he is concerned.
H = open(os.path.join("templates", "dashboard.html"), encoding="utf-8").read()
truthy("  the toolbar button calls it", "bulkGtinExemption(true)" in H)
truthy("  and the file is loaded", "/static/js/gtin.js" in H)

print("\n=== nothing claims the exemption from a CONDITION ===")
# The generator used to hold TWO identifier decisions. The first auto-claimed
# the exemption whenever the barcode box was empty and was invisible only
# because the second overwrote it -- an early return between them would have
# silently restored the banned behaviour with no test failing.
_gen = open("amazon_listing_generator.py", encoding="utf-8").read()
# CODE ONLY. The deleted block is quoted in the comment that replaced it, so
# that the next reader knows what was removed and why -- counting comment lines
# here would make that explanation look like the bug it describes.
_code = "\n".join(l for l in _gen.splitlines() if not l.lstrip().startswith("#"))
check("the identifier is decided in exactly one place",
      _code.count('A["supplier_declared_has_product_identifier_exemption"] = ['), 1)
truthy("  and only behind the owner's tick",
       "elif _exempt_asked:" in _gen)
falsy("  never from an empty barcode box",
      "real barcode, else claim GTIN exemption" in _gen)

print("\n=== the app never tells him to empty the box instead ===")
# "Clear the Barcode / GTIN box so the listing uses the GTIN exemption" was
# advice the app gave three times. It stopped being true when the exemption
# became opt-in: clearing the box now sends NO identifier and Amazon refuses.
AE = open(os.path.join("static", "js", "amazon_errors.js"), encoding="utf-8").read()
falsy("no error explanation says clearing the box claims the exemption",
      "box so the listing uses the GTIN exemption" in AE
      or "clear the Barcode / GTIN field to use the GTIN exemption" in AE)
truthy("  they say what emptying it actually does",
       "no identifier" in AE)

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
