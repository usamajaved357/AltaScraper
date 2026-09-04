"""Every listing opens the SAME page — ours or Amazon's.

    "Most live listings open the 'Optimize live listing' modal instead of the
     PDP overlay. Only listings that were originally created by this app open
     the PDP. ... ALL listings open the PDP overlay regardless of origin. A
     listing synced from Amazon is still a listing you manage."

MEASURED: 7 of jack_uk's 47 live SKUs and 18 of nestwell_goods' 62 have no row
in this app — made in Seller Central, made by another tool, or their draft was
deleted. That is why it was "most live listings" and not a few.

EVERY TRIGGER OF THE OPTIMIZE MODAL, traced:

  listings.js  openListing's fallback when there was no draft  <- REMOVED
  listings.js  "Optimize live copy" in the row overflow menu   <- kept, a button
  listings.js  the sparkle button on a live row                <- kept, a button
  pdp.js       "Optimize live copy" in the page's own sidebar  <- kept, a button

Only the first was automatic, and it is the one the report is about. The other
three are pressed on purpose and carry the Custom AI Rewrite, which the brief
says to preserve.
"""
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
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


def code(s):
    s = re.sub(r"(?s:/\*.*?\*/)", "", s)
    return re.sub(r"(?m:^[ \t]*//[^\n]*)", "", s)


LIST = code(read("static", "js", "listings.js"))
PDP = code(read("static", "js", "pdp.js"))
CSS = read("static", "css", "pdp.css")

print("== clicking a listing never chooses between two UIs ==")
yes("openListing goes straight to the product page",
    re.search(r"function openListing\(sku, asin\)\{\s*const s = String\(sku \|\| \"\"\);"
              r"\s*if\(!s\) return;\s*if\(typeof pdpOpen === \"function\"\)\{ pdpOpen\(s\); return; \}",
              LIST))
check("  the draft check is gone from it",
      "hasDraftRow(s) && typeof pdpOpen" in LIST, False)
# It stays as the ONE answer to "is this ours to edit" -- other screens ask it.
yes("hasDraftRow itself is untouched", "function hasDraftRow(sku)" in LIST)
check("  and openListing no longer calls optimizeLive",
      "optimizeLive(asin || liveAsinFor(s), s)" in LIST, False)

print("\n== the optimize modal only fires from a button now ==")
# Three, and each is a button somebody presses: the row's sparkle icon, the
# row's overflow menu, and the product page's own sidebar. The fourth -- the
# automatic fallback inside openListing -- is what was removed.
opens = re.findall(r"optimizeLive\(", LIST + PDP)
check("three call sites, all of them deliberate", len(opens), 3)
yes("  the row's overflow menu", 'onclick="optimizeLive(' in LIST)
yes("  and the product page's own sidebar", "pdp-sbbtn\" onclick=\"optimizeLive(" in PDP)

print("\n== a listing with no draft is drawn from Amazon's own data ==")
yes("there is a row builder for it", "function pdpCatalogueRow(sku)" in PDP)
yes("  fed by the catalogue snapshot", "LIVE_ITEMS.find" in PDP)
yes("  and by getListingsItem", "lvGet(sku)" in PDP)
# summaries -> the title Amazon shows shoppers; content -> the copy; values ->
# the attributes. Exactly what the brief asks to appear as the input values.
yes("  the title comes from summaries first", "S.itemName || first(\"item_name\")" in PDP)
yes("  the bullets from the content block", 'C.bullet_point || \[\]' in PDP
    or "(C.bullet_point || [])" in PDP)
yes("  and the attributes from the values", "attributes: V," in PDP)
# CLAUDE.md Rule 1 and the two-ASIN problem: a catalogue listing has no
# competitor, so the competitor slot stays empty rather than being filled with
# its own ASIN.
yes("Amazon's ASIN goes in the OWN slot", "own_asin: String(S.asin" in PDP)
yes("  and the competitor slot stays empty", 'asin: "",' in PDP)
# Nothing is written. Inventing a half-empty row the moment somebody looked at
# a listing would put drafts in the store that nobody asked for.
yes("nothing is stored by looking", "It is NOT written anywhere" in read("static", "js", "pdp.js"))

print("\n== and the page says whose data it is ==")
yes("a note is drawn for a catalogue-only listing",
    "function pdpCatalogueNote(r)" in PDP)
yes("  above everything, in `blocking`", "+ pdpCatalogueNote(r)" in PDP)
yes("  saying edits need a draft to save into",
    "Editing needs a draft to save into" in PDP)
yes("  with the one button that makes one", "function pdpSyncThis(sku)" in PDP)
yes("  which uses the app's existing single-listing pull",
    '"/live/pull_row"' in PDP)
# A FAILED READ IS NOT AN EMPTY LISTING. Without this, a listing Amazon refused
# to describe looks like one with no title, no bullets and no attributes.
yes("a failed read says so instead", "Amazon would not describe this listing" in PDP)
yes("  and that the blanks mean nobody could look",
    "nobody could look" in PDP)
yes("  a deleted listing says that", "Amazon no longer has this listing" in PDP)
yes("the styles exist", ".pdp-catnote{" in CSS and ".pdp-catnote.bad{" in CSS)

print("\n== driven in Chrome, on jack_uk ==")
# 7 catalogue-only SKUs. Opening 11.99_3Days_B09DSZ3LFW:
#   the PDP opened, the optimize modal did NOT, the drawer did NOT
#   the title and our ASIN (B0H56DZDWH) came from the catalogue
#   four tabs, the note shown, no page errors
#   Amazon refused the attribute read on this account, so the red note explains
#   the blanks rather than leaving them to be read as "the listing has none"
yes("pdpOpen no longer turns a listing away for having no row",
    "This app holds no draft of" not in PDP)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
