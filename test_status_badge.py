"""The badge says what the situation is, not which mechanism produced it.

    LISTING_GENERATOR_REDESIGN_SPEC.md §3: "Instead of raw text paragraphs
    showing submission status, use compact badges on each row."

Two stored words get read wrong, and only two:

    SUBMITTED  reads as "done". It is not -- Amazon publishes asynchronously,
               and this is the gap between accepted and shown.  -> WAITING
    API_ERROR  reads as "the app broke". It did not -- Amazon rejected the
               listing and said why.                             -> ISSUE

WHAT THIS TEST IS REALLY GUARDING.

The mapping is ONE function in liststatus.js and both renderers call it. Two
copies would drift, and the drift is invisible: the table view and the detailed
view would show the same listing as two different things, which is exactly the
defect the header of liststatus.js was written about.

It also pins the half that must NOT change. The badge's COLOUR still keys off
the stored status, so renaming the word cannot quietly change which rows look
urgent -- and the spec's own suggestion of four badges is NOT implemented,
because it would make QUEUED (nothing generated yet, Submit can do nothing)
indistinguishable from a row that is ready to send.
"""
import re
import sys

LS = r"D:\AltaScraper\static\js\liststatus.js"
LR = r"D:\AltaScraper\static\js\listrow_detailed.js"
LI = r"D:\AltaScraper\static\js\listings.js"
ls, lr, li = (open(p, encoding="utf-8").read() for p in (LS, LR, LI))
fails = []


def check(label, got, want):
    ok = got == want
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        fails.append(label)


print("=== the mapping exists once, in the file that owns status wording ===")
check("lsBadgeWord is defined in liststatus.js",
      bool(re.search(r"\bfunction\s+lsBadgeWord\s*\(", ls)), True)
check("  and nowhere else",
      bool(re.search(r"\bfunction\s+lsBadgeWord\s*\(", lr + li)), False)

# The table read as if it were pulled out of the map itself, so a future edit to
# the map is what this test follows -- not a copy of today's answer.
m = re.search(r"LS_BADGE_WORDS\s*=\s*\{([^}]*)\}", ls)
check("the map is a literal that can be read", bool(m), True)
pairs = dict(re.findall(r"([A-Z_]+)\s*:\s*[\"']([A-Z]+)[\"']", m.group(1) if m else ""))
check("SUBMITTED becomes WAITING", pairs.get("SUBMITTED"), "WAITING")
check("API_ERROR becomes ISSUE", pairs.get("API_ERROR"), "ISSUE")

print("\n=== nothing else is renamed ===")
# The spec asked for four badges. QUEUED must stay QUEUED: it is the one status
# where Submit genuinely cannot do anything yet, and calling it DRAFT would make
# it identical on screen to a row that is ready to send.
for word in ("LIVE", "QUEUED", "GENERATED", "PARENT", "API_READY", "APPROVED"):
    check("%s is left alone" % word, word in pairs, False)
check("exactly two words are remapped", len(pairs), 2)

print("\n=== both renderers use it, so the two views cannot disagree ===")
check("the detailed row's badge uses it", "lsBadgeWord(st)" in lr, True)
check("the table's pill uses it", "lsBadgeWord(s)" in li, True)
# Guarded calls, because liststatus.js load order is a real thing in this app.
for name, src in (("listrow_detailed.js", lr), ("listings.js", li)):
    check("%s calls it defensively" % name,
          'typeof lsBadgeWord === "function"' in src, True)

print("\n=== the COLOUR still comes from the stored status, not the new word ===")
# This is the half that must not change: renaming a word must not silently
# change which rows look urgent.
pill = li.split("function _statusPill")[1].split("\n}")[0]
check("the pill's class is computed from the stored status",
      "badgeClass(s)" in pill, True)
check("  not from the renamed word", "badgeClass(word)" in pill, False)
badge = lr.split("const badge =")[1].split(";")[0]
check("the detailed badge's class keys off the stored status",
      'st === "SUBMITTED" ? " sent"' in badge, True)
check("  and only its TEXT is the mapped word", "esc(word" in badge, True)

print("\n=== WAITING cannot land on a published row ===")
# Not by a check in lsBadgeWord, but by construction: both callers pass
# _shownStatus(), which already returns LIVE for anything Amazon confirms.
check("the detailed view passes the SHOWN status", "lrShownStatus(r)" in lr, True)
check("the table passes the SHOWN status", "_statusPill(_shownStatus(r))" in li, True)
check("_shownStatus returns LIVE when Amazon confirms it",
      'return "LIVE"' in li.split("function _shownStatus")[1].split("\n}")[0], True)

print("\n=== the detail line underneath is still accurate ===")
# The spec wanted "Amazon reviewing -- may need action within 48h" for the error
# state. API_ERROR means Amazon REJECTED it synchronously with reasons: nothing
# is being reviewed and there is no 48-hour clock. lrAmazonSaid keeps the truth.
said = lr.split("function lrAmazonSaid")[1].split("\n}")[0]
check("a rejection is described as a rejection", "Amazon rejected" in said, True)
check("  and no 48-hour review is claimed", "48h" in said or "reviewing" in said, False)
check("the full note is still available on hover", 'title="' in said, True)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - %s" % f)
sys.exit(1 if fails else 0)
