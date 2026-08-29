"""The listings page had two ASINs and could not tell them apart.

    "read every litteral part of the code that handles the all listing page
     and then solve and fix all the bugs possible."

THE BIG ONE. Rule 1: this app creates NEW products under our own brands, and
the ASIN inside the SKU (price_days_ASIN, e.g. 9.89_3Days_B07NT77GT8) is a
COMPETITOR REFERENCE used only to pull product data during generation.

MEASURED on jack_uk, all 67 rows: every one of the 56 rows carrying an ASIN
carried the COMPETITOR's -- r.asin was identical to the ASIN embedded in the
SKU in 56 cases out of 56, with none differing. Where the listing is actually
live, our real ASIN is a completely different code:

    SKU 9.89_3Days_B07NT77GT8   r.asin B07NT77GT8   ours B0H66Q1XFK
    SKU 7.99_2Days_B07GDBY3YS   r.asin B07GDBY3YS   ours B0H6Y62F96

ownLiveAsin() had said so in a comment the whole time -- "we deliberately never
fall back to r.asin here, which is competitor" -- and six other functions did
exactly that anyway, each deciding for itself and each deciding wrong. One
concept, no shared helper, six answers. rowAsin() and _matchableAsin() are the
shared helpers; this file pins them and every caller.

The worst of the six was mine, added the day before while removing the
open-on-Amazon button: the green ASIN became a link, to r.asin, so clicking it
opened the COMPETITOR's product page while looking exactly like our own listing.
Measured after the fix: 47 rendered ASIN links, none pointing anywhere but our
own catalogue.

WHY THE OTHERS MATTER even though they rarely fire. Matching an app row against
our catalogue BY ASIN can only ever produce a false positive, because the ASIN
on the row is somebody else's: a hit means we happen to also list the
competitor's ASIN. The consequences were a draft declared live, a competitor's
photograph shown as our listing's image, a competitor's A+ modules on our card,
and a genuinely live listing dropped out of the total.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


LJ = read("static", "js", "listings.js")
DH = read("templates", "dashboard.html")

# ===================================================================
print("== there is one helper, and it knows the two ASINs apart ==")
truthy("rowAsin exists", "function rowAsin(" in LJ)
truthy("  and reports ours separately from the source",
       "return {own: own, source: src, ours: !!own};" in LJ)
truthy("_matchableAsin exists", "function _matchableAsin(" in LJ)
truthy("  built on a test for the SKU-embedded reference",
       "function _asinIsCompetitorRef(" in LJ)
# The same field means different things depending on what was passed in: on an
# app row r.asin is the competitor, on a catalogue item it is ours. Both go to
# the same rendering functions, which is what made this easy to get wrong.
truthy("the row/catalogue ambiguity is written down",
       "On an APP ROW, r.asin is the" in LJ)
truthy("a catalogue item's own asin is not reported as a source",
       "if(src && own && src === String(own).trim().toUpperCase()) src = \"\";" in LJ)

print("\n== the green ASIN opens OUR listing, or admits there isn't one ==")
truthy("the link is built from our own asin", "_dpUrl(_a.own)" in LJ)
falsy("  never from the row's asin field", "_dpUrl(r.asin)" in LJ)
truthy("a draft says it is not live yet", "not live yet" in LJ)
truthy("  and still shows what it was researched from", "srcasin" in LJ)
truthy("  labelled as the competitor, not as ours",
       "is the competitor product it was researched from" in LJ)
truthy("  and the label is not a link", ".srcasin{" in read("static", "css", "dashboard.css"))

print("\n== generated images are not filed against a competitor's ASIN ==")
# _asinForSku's one caller stamps this onto every image job.
_f = LJ.split("function _asinForSku")[1].split("function ")[0]
falsy("no fallback to the rows' asin field", "ROWS||[]" in _f)
truthy("  and why is recorded", "never the competitor reference" in _f)

print("\n== A+ content is keyed by our ASIN ==")
_a = LJ.split("function aplusFor")[1].split("function ")[0]
truthy("keyed by ownLiveAsin", "ownLiveAsin(r)" in _a)
falsy("  not by the row's asin", 'String((r && r.asin) || "")' in _a)
# Honest about the evidence: APLUS_BY_ASIN was empty on the view measured, so
# this one is fixed on the code argument, not on an observed miss.
truthy("  and the limit of the evidence is stated", "Not demonstrable" in _a)

print("\n== catalogue matching cannot fire on a competitor's ASIN ==")
# isPublishedRow's BODY moved to static/js/liststatus.js (lsInLiveCatalogue) when
# the three disagreeing definitions of "is this published" were consolidated into
# one (CLAUDE.md Rule 12). The guarantee is unchanged and still pinned -- it is
# just pinned where the code now lives. isPublishedRow itself must therefore be a
# delegator and hold no matching logic of its own.
LS = read("static", "js", "liststatus.js")
for fn, src in (("isActuallyLive", LJ), ("lsInLiveCatalogue", LS),
                ("_liveImageFor", LJ), ("liveItemForRow", LJ)):
    body = src.split("function %s(" % fn)[1].split("\nfunction ")[0]
    truthy("%s uses _matchableAsin" % fn, "_matchableAsin(r)" in body)
    falsy("  and not the raw field" if fn else "", 'norm(r && r.asin)' in body)
truthy("isPublishedRow is a delegator, with no rule of its own",
       "function isPublishedRow(r){ return lsIsPublished(r); }" in LJ)
truthy("the count's exclusion set does too",
       "new Set(_liveAppRows.map(_matchableAsin)" in LJ)
truthy("and the reason is recorded once",
       "can only ever produce a FALSE POSITIVE" in LJ)

print("\n== and the grid's dedupe cannot hide a live listing ==")
# This set REMOVES cards from the grid. Seeded with competitor ASINs, a match
# against one of our own catalogue entries would make a genuinely live listing
# vanish from the screen -- the disappearing-listing version of the same
# mistake. The SKU set beside it is the one that actually does this job.
MT = read("static", "js", "miles_template.js")
truthy("the dedupe set uses _matchableAsin",
       "const liveAppAsins = new Set(liveRows.map(_mAsin)" in MT)
falsy("  not the rows' raw asin field",
      "new Set(liveRows.map(r=>_norm(r.asin))" in MT)
truthy("  and says what it would have cost", "vanish from the screen" in MT)

print("\n== searching by the source ASIN still works ==")
# It is genuinely useful to find a draft by the product it was built from.
truthy("search still looks at the row's asin", "r.asin, r.competitor_asin" in LJ)

# ===================================================================
print("\n== a count you click shows you that count ==")
#     Two counts, worded differently, both sending the SAME filter:
#       "3 listings Amazon refused"          -> metricFilter('holds')
#       "25 held by a compliance or IP check"-> metricFilter('holds')
#     isHold is the UNION of the two, so clicking a count of 3 showed 28 rows.
truthy("the two halves are named separately",
       "function isRefusedByAmazon(" in LJ and "function isBlockedByOurChecks(" in LJ)
truthy("  and isHold is their union, from one definition each",
       "return isBlockedByOurChecks(s) || isRefusedByAmazon(s);" in LJ)
truthy("the filter understands each half",
       'FILTER==="refused"' in LJ and 'FILTER==="blocked"' in LJ)
truthy("Amazon's refusals go to their own list", "metricFilter('refused')" in LJ)
truthy("  and our own checks to theirs", "metricFilter('blocked')" in LJ)
# The tile that genuinely wants both keeps the union.
truthy("the combined tile still asks for both",
       '"Blocked or errored", "holds"' in LJ)
truthy("and the difference is explained where it is decided",
       "Nothing has reached Amazon" in LJ)

print("\n== the dropdown never goes blank while the list is filtered ==")
# metricFilter does `sel.value = v` then applies the filter regardless. With no
# matching <option> the assignment silently does nothing, so the control that
# tells you what you are looking at stopped saying anything -- on 6 of the 11
# filters, including all four live tiles.
for v in ("all", "review", "holds", "blocked", "refused", "approved", "live",
          "live_all", "live_notshowing", "live_nocost", "live_oos"):
    truthy("dropdown offers %-16s" % v, '<option value="%s">' % v in DH)
truthy("and why every filter needs an option is recorded",
       "the dropdown goes BLANK" in DH)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
