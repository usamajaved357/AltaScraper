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
# GENERATED reads as DRAFT, which is what it plainly is: written by this app and
# not yet sent. The stored word names the STEP that produced it, which is of no
# interest to anyone reading a row.
check("GENERATED becomes DRAFT", pairs.get("GENERATED"), "DRAFT")

print("\n=== QUEUED is still NOT draft -- the line that must hold ===")
# A queued row has a SKU and almost nothing else: the generator has not run, so
# there is no copy, no images, and nothing Submit could send. Badging it DRAFT
# makes "nothing made yet" identical to "made, ready to go" -- the two states on
# this screen it is most expensive to confuse.
check("QUEUED keeps its own word", "QUEUED" in pairs, False)
# APPROVED/API_READY are the step between generated and sent, and the Approved
# tile counts them separately (listings.js: c.APPROVED + c.API_READY).
for word in ("LIVE", "PARENT", "API_READY", "APPROVED"):
    check("%s is left alone" % word, word in pairs, False)
check("exactly three words are remapped", len(pairs), 3)

print("\n=== ALL THREE renderers use it, so no view can disagree ===")
# There are three places a status word is drawn, and the third was missed when
# the first two were changed -- so a row badged DRAFT opened a drawer headed
# GENERATED for the same listing. That is the exact drift the header of
# liststatus.js was written about, and it is why this counts them.
check("the detailed row's badge uses it", "lsBadgeWord(st)" in lr, True)
check("the table's pill uses it", "lsBadgeWord(s)" in li, True)
check("the drawer's bar uses it", "lsBadgeWord(_shown)" in li, True)
# EVERY badge built from badgeClass() must take its TEXT from the map. Rather
# than count (the definition and the comments match too), find each call and
# check the variable it classes is NOT the variable it prints -- printing the
# same variable means the raw status reached the screen.
_code = "\n".join(l.split("//")[0] for l in li.splitlines())
_sites = [m for m in re.finditer(r"badgeClass\((\w+)\)", _code)
          if not _code[max(0, m.start() - 9):m.start()].endswith("function ")]
check("there are exactly two badge call sites", len(_sites), 2)
for m in _sites:
    var = m.group(1)
    after = _code[m.end():m.end() + 260]
    ln = _code[:m.start()].count("\n") + 1
    check("line %d classes on %s but prints a mapped word" % (ln, var),
          ("esc(%s" % var) in after, False)
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

print("\n=== the tile that counts those rows says the same word ===")
# A tile reading "Generated" above rows badged DRAFT is the same drift as the
# drawer's, one level up. The LABEL changes; the filter key must not.
tiles = li.split("tiles = tile(")[1].split("}else{")[0]
check("the tile is labelled Drafts", '"Drafts", "generated"' in tiles, True)
check("  and no tile still says Generated", '"Generated"' in tiles, False)
check("the filter key is untouched, so the click still works",
      '"generated"' in tiles, True)
check("  metricFilter still receives a key, not a label",
      "metricFilter('\" + filter + \"')" in li, True)
# QUEUED keeps its own tile and its own word, for the same reason it keeps its
# own badge: nothing has been generated yet, so it is not a draft.
check("Queued is still its own tile", '"Queued", "queued"' in tiles, True)

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
