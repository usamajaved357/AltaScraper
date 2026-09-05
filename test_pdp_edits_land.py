"""Do PDP edits actually save, and does the screen show it?

    "The user changed the Brand Name field from 'Nestwell Goods' to
     'AltaboltaVoo' on the PDP. But the error message STILL shows 'Nestwell
     Goods' ... the hero section STILL shows 'Brand: Nestwell Goods'. This means
     either the edit didn't save to the database, or the PDP is reading from a
     stale cache, or Submit is sending old data."

    "i suspect that this brand name change is not recorded and the app is
     sending nestwell goods to amazon"

THREE SEPARATE QUESTIONS, and the answers are different. Each is measured, and
what was measured is written down beside the check so the next person does not
have to re-run it to know.

  1. Does the edit reach the database?   YES -- and it always did.
  2. Does the screen show it?            NO, it did not. That is fixed here.
  3. Does Submit send the new value?     YES, given the brand is registered.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with io.open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


def nojs_comments(s):
    s = re.sub(r"(?s:/\*.*?\*/)", "", s)
    return re.sub(r"(?m:^[ \t]*//[^\n]*)", "", s)


PDP = nojs_comments(read("static", "js", "pdp.js"))
AF = nojs_comments(read("static", "js", "autofix.js"))
GEN = read("amazon_listing_generator.py")

print("== 1. THE EDIT REACHES THE DATABASE ==")
# MEASURED IN CHROME on draft 7.96_3Days_B0841BD4JY (nestwell_goods): each of
# the eight editable columns was set to a marker through the real control, the
# page was RELOADED, and every one came back with the marker. /edit answered 200
# ok to all eight, none refused. The originals were restored afterwards.
#
#     Title  Brand  UPC  Our Price (GBP)  Handling Days
#     Bullet 1  Description (HTML)  Search Terms / KW      -> 8/8 PERSISTED
#
# So "the edit didn't save to the database" is not what happened.
yes("there is one save path and it posts to /edit",
    "async function editField(sku, target, key, value)" in AF
    and AF.count('fetch("/edit"') == 1)
yes("  a column typed empty is saved as empty, an attribute is deleted",
    'if(target === "attr")' in AF and "delete r.attributes[key]" in AF)
yes("  and the row in memory is updated from the same answer",
    "updateLocalCol(r, key, value)" in AF)

print("\n== 2. THE SCREEN SHOWS IT ==")
#     "the hero section STILL shows 'Brand: Nestwell Goods'"
#
# Measured before the fix: after typing into the Brand box and clicking away,
# the ROW held the new value and the BOX held the new value, and the HERO still
# read the old one -- then a bare pdpRender() showed the new value, which is
# what proves the data was there and only the drawing was behind.
yes("the hero can be refreshed on its own", "function pdpHeroRefresh(sku)" in PDP)
yes("  it replaces only the hero element",
    '.pdp-hero' in PDP and "old.replaceWith(fresh)" in PDP)
# NOT the whole panel: a blur-save fires as you TAB into the next box, and
# re-rendering would take the focus out of it.
yes("  not the whole panel", "function pdpRebuild(sku)" in PDP
    and "pdpRender()" in PDP)
yes("the fields the hero shows are named beside it",
    "const PDP_HERO_COLS" in PDP and "function pdpHeroShows(key)" in PDP)
for col in ("Title", "Brand", "UPC", "Our Price (GBP)"):
    m = re.search(r"const PDP_HERO_COLS = \[(.*?)\];", PDP, re.S)
    yes("  %s is on that list" % col, m and ('"%s"' % col) in m.group(1))
yes("the saver refreshes it after a column save",
    "pdpHeroShows(key)" in AF and "pdpHeroRefresh(sku)" in AF)
# An attribute is not on the hero, so it must not trigger the swap.
yes("  and not after an attribute save", 'target !== "attr"' in AF)

print("\n== 2b. AND THE LIST UNDERNEATH, which is the same bug one screen out ==")
#     "please check what other problems are related to it and this same
#      behavior may be occuring at multiple places"
#
# It was. Measured: edit the title on the product page, close it, and the row in
# the table still read the OLD title -- nothing after a save re-drew the grid.
# The row object was already correct, so this is a redraw, not a re-read.
yes("closing the page redraws the grid when something was edited",
    re.search(r"function pdpClose\(\)\{(?:(?!\n\}).)*const _edited = PDP_DIRTY",
              PDP, re.S) is not None)
yes("  and only then", "if(_edited && typeof render === \"function\")" in PDP)
# ON CLOSE, NOT ON EVERY SAVE: a blur-save fires as you tab between fields and
# redrawing 86 rows behind the panel each time is work nobody can see.
yes("  the flag is read before it is cleared", re.search(
    r"const _edited = PDP_DIRTY;.*?PDP_DIRTY = false;", PDP, re.S) is not None)
# MARKED FROM THE SAVE, not from the keystroke. Typing raises the save bar, but
# it is not proof anything was written -- and a value set another way (a
# suggestion applied, a live value copied in) would slip past a keystroke test.
yes("the save marks it, not the input event",
    "typeof pdpMarkDirty === \"function\"" in AF
    and 'String(PDP_SKU) === String(sku)' in AF)

print("\n== 3. WHAT SUBMIT SENDS ==")
#     "i suspect ... the app is sending nestwell goods to amazon"
#
# It is not. The payload's brand is the Brand COLUMN, passed through
# resolve_account_brand -- the one place that decides whose trademark goes out.
# Called with the real config for nestwell_goods, whose Brands list is
# ['Nestwell Goods', 'AltaboltaVoo']:
#
#     typed 'AltaboltaVoo'   -> SENDS 'AltaboltaVoo'
#     typed 'Nestwell Goods' -> SENDS 'Nestwell Goods'
#     typed 'Selvora'        -> SENDS 'Nestwell Goods' + a note
#     typed ''               -> SENDS 'Nestwell Goods'
yes("the payload's brand is the Brand column",
    'brand, _brand_note = resolve_account_brand(g("Brand"), config)' in GEN)
yes("  through the one resolver", "def resolve_account_brand(row_brand, config)" in GEN)
# THE GUARD STAYS. One account's trademark on another's listing is the worse
# fault, and it has happened -- see the docstring.
_fn = GEN[GEN.index("def resolve_account_brand"):]
_fn = _fn[:_fn.index("\ndef ")]
# The sentence is split across source lines, so match a fragment that is really
# contiguous rather than the wording as it reads on screen.
yes("  a brand not on the account's list is replaced, not sent",
    "which is not one of this account's " in _fn
    and "registered brands (%s). Sending %r instead." in _fn)
yes("  and an account with no brand sends none rather than borrowing one",
    "so no brand is being sent" in _fn)
# It is NEVER the global. That leak is how one account's brand reached another's
# listings, and the docstring records it.
yes("  never the global brand_name once an account is resolved",
    'config.get("brand_name", "")' in _fn
    and _fn.index('config.get("_account_brands")') < _fn.index('config.get("brand_name", "")'))

print("\n== 3b. AND WHEN IT SENDS SOMETHING ELSE, IT SAYS SO ==")
# The suspicion was reasonable even though it was wrong here, because the app
# CAN send a different brand and said so only on the console. The guard stays --
# one account's trademark on another's listing is the worse fault -- but the
# editor showed what you typed while the payload could carry something else.
R = read("routes", "listing_routes.py")
yes("the server works out what will be sent", "def _attach_brand_send(" in R)
yes("  by asking the ONE resolver, not by repeating its rule",
    "from amazon_listing_generator import resolve_account_brand" in R
    and "resolve_account_brand(out[\"typed\"], probe)" in R)
yes("  and attaches it to the rows the editor reads",
    "_attach_brand_send(c, _brands, _cfg())" in R)
# ONCE PER REQUEST. It runs per row, and the account is a property of the
# request -- 86 listings meant 86 identical account lookups.
yes("the account is looked up once, not once per row",
    "def _account_brands(cfg, workspace_id, config_path)" in R
    and "_brands = _account_brands(" in R)
# config_path IS A PARAMETER. There is no module-level CONFIG_PATH in that file
# -- it is a keyword of register() -- so a module-level function reaching for it
# raised NameError, the except swallowed it, and every row of an account with
# two brands reported "this account has no registered brand".
check("  and CONFIG_PATH is not reached for from module scope",
      re.search(r"def _account_brands[^)]*\)[^\n]*\n(?:(?!\ndef ).)*?"
                r"get_account\(cfg, workspace_id, CONFIG_PATH\)", R, re.S) is not None,
      False)
# THE ID COMES OFF THE STORE the rows were read from, not from _state, which is
# empty on a plain page load.
yes("the workspace id comes off the store", "def _ws_id_of(store)" in R)
yes("  reaching through the shim as well as the store",
    'getattr(getattr(store, "store", None), "workspace_id", "")' in R)
AF2 = nojs_comments(read("static", "js", "autofix.js"))
yes("the Brand field draws the warning", "r.brand_send" in AF2
    and "Amazon will receive" in AF2)
# An account with an EMPTY Brands list sends no brand rather than borrowing one,
# and "Amazon will receive """ was the wrong sentence for the more serious case.
yes("  and says so differently when NO brand will be sent",
    "No brand will be sent to Amazon." in AF2)
# Measured in Chrome on nestwell_goods, whose Brands list is
# ['Nestwell Goods','AltaboltaVoo']:
#   brand "Nestwell Goods" -> swapped false, no warning drawn
#   brand "Selvora"        -> swapped true, "Amazon will receive Nestwell Goods"
#   the row was restored afterwards.

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
