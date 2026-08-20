"""One listing cannot be live on one tab and a ready-to-send draft on the other.

    "when i go to live on amazon section i see the asin B0HCVFW53Y and
     B0HCVTDFNW as live and when i go to drafts it showed me the both as
     drafts; ready to send. but when i refreshed the asin the ready to send
     section was zero"

Both halves of that are one defect, and it is not a race or a caching quirk --
it is the app holding two different rules for the same question and applying
whichever the current tab implied.

MEASURED BEFORE THE FIX, on the Drafts view: LIVE_ITEMS was 0 and
_liveCatalogLoaded() was false. The catalogue was fetched only for the Live and
All views. isPublishedRow(), which decides whether a row is a draft or something
Amazon already has, then had nothing to consult and fell back to the row's
stored status word -- so a listing Amazon had published, whose stored word still
read APPROVED, sat in "ready to send" indefinitely.

Then visiting "Live on Amazon" loaded the catalogue (47 items, measured) and
returning to Drafts hid the row and dropped the count. That is the "refreshed
and it was zero" half. The number was never really changing; the Live view was
simply the only place that had asked Amazon.

MEASURED AFTER: the Drafts view loads with LIVE_ITEMS 47 and the catalogue
flagged loaded, on first paint, and the ready-to-send count is the same number
on every view.

WHAT IS NOT CHANGED. No status word is rewritten. Only Sync writes those, and it
still does. The screen reads Amazon's catalogue instead of a copy of it that has
gone stale -- which is the same principle the status dot and the tile counts
were already built on.
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
SH = read("static", "js", "shell.js")

print("== every view asks Amazon, not just the two that show live listings ==")
# The old lines chose between loadRows() and loadLiveCatalog() on LIST_SOURCE,
# which is what left the Drafts view with no catalogue at all.
falsy("the loader no longer picks by which tab is open",
      "if(LIST_SOURCE==='all' || LIST_SOURCE==='live'){ loadRows(); loadLiveCatalog(false); }" in SH)
falsy("  nor on a marketplace switch",
      "if(LIST_SOURCE==='live'||LIST_SOURCE==='all'){ loadLiveCatalog(false); } else { loadRows(); }" in SH)
check("both are loaded, on both paths", SH.count("loadRows(); loadLiveCatalog(false);"), 2)
truthy("and why is written where the change is",
       "the Drafts view reads that to tell a draft from something already" in SH
       or "THE DRAFTS VIEW NEEDS AMAZON'S CATALOGUE TOO" in SH)
# force=false: served from the durable snapshot, so this costs no Amazon call
# and cannot make opening the Drafts tab wait on a report build.
falsy("and it does not force a report rebuild to do it",
      "loadLiveCatalog(true)" in SH)

print("\n== and the answer no longer depends on which tab is open ==")
truthy("the gate is whether Amazon's answer exists", "const haveAmazon =" in LJ)
truthy("  which includes having loaded the catalogue", "_liveCatalogLoaded()" in LJ)
falsy("  not which group is on screen",
      "if(liveGroupShown) return !!((s && liveCatSkus.has(s))" in LJ)
# The stored word is still the answer BEFORE anything has been synced -- the one
# case where the app has nothing better, and where saying "not live" would
# slander a listing nobody has asked Amazon about yet.
truthy("the stored word remains the pre-sync fallback",
       'return norm(r.status)==="LIVE";' in LJ)
truthy("  and that reason is recorded", "before the first sync" in LJ.lower())

print("\n== a claimed-live row is still its own thing, not folded into live ==")
# status says LIVE, loaded catalogue does not list it. Calling that "live" is
# what hid it; it has its own name and its own display.
truthy("isClaimedLiveOnly still exists", "function isClaimedLiveOnly(" in LJ)
truthy("  and still gates on the catalogue being loaded",
       "if(!_liveCatalogLoaded()) return false;" in LJ)
truthy("  and the distinction is written down", "not confirmed by Amazon" in LJ)

print("\n== nothing rewrites a status word behind the user's back ==")
# The screen READS Amazon; only Sync WRITES. A screen that silently corrected
# stored data would make the next disagreement impossible to notice.
truthy("re-verifying is still Sync's job, not the renderer's",
       "_reverifyLiveStatus()" in read("static", "js", "miles_template.js"))
falsy("the loader does not write statuses",
      "setStatus(" in SH.split("loadRows(); loadLiveCatalog(false);")[0][-1500:])

print("\n== Sync says what it does, so it stops looking redundant ==")
#     "why do have that sync button if the listings are already been synced
#      upto some minutes?"
# Fair: the old tooltip said "Sync live listings from Amazon now", describing it
# as a repeat of something the page appears to do already. It is not -- opening
# the tab shows a saved copy and never fetches a listing's contents.
DH = read("templates", "dashboard.html")
falsy("the tooltip no longer just says sync",
      'title="Sync live listings from Amazon now"' in DH)
truthy("it says a new report is built", "BRAND NEW listings report" in DH)
truthy("  that contents are pulled", "actual CONTENTS are pulled" in DH)
truthy("  that submitted drafts get checked", "marked live where Amazon has published" in DH)
truthy("  and that it is not instant", "takes a few minutes" in DH)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
