"""A listing Amazon has ACCEPTED is not a draft, and must not be described as live.

    "listing submitted via SP-API, Amazon responds accepted, drawer says
     'Published live to Amazon', API log shows 'ok: 1, errors: 0' -- but the
     listing stays in the Drafts tab"

Both halves of that were true at once, on one screen, and both were the app's own
doing.

WHAT WAS ACTUALLY HAPPENING. Amazon publishes ASYNCHRONOUSLY: putListingsItem
returns ACCEPTED and the listing appears 5-30 minutes later. The generator writes
SUBMITTED for that gap, which is honest (amazon_listing_generator.py:7285). Two
things then went wrong with it.

ONE: the Drafts filter did not know the word. isPublishedRow() hid a row only when
its status was exactly "LIVE" or Amazon's fetched catalogue already listed the SKU
-- and a catalogue synced BEFORE the submit cannot contain it. So the row stayed
under "Drafts (not yet live on Amazon)", a heading that reads as "you still have to
send this". Meanwhile _PUBLISHED_STATES in miles_template.js DID count SUBMITTED,
and _LIVE in domain/barcode_clash.py counted it too. Three definitions of "is this
published", in three files, disagreeing (CLAUDE.md Rule 12).

TWO: the verdict classifier matched the word "live" inside the generator's
"SUBMITTED -- accepted by Amazon (live shortly)" line and printed "Published live to
Amazon. The listing is now live on your account." The log line saying the opposite
was two inches below it.

AND NOTHING EVER PROMOTED IT. The SUBMITTED -> LIVE flip exists
(amazon_listing_generator.py:7086-7134, verify mode) but its only caller was the
Sync button, so the row moved only if the user pressed Sync late enough. Recorded
in routes/listing_routes.py:108-110 as a listing that read "SUBMITTED" for a
fortnight.

WHAT IS PINNED HERE: one definition of the vocabulary, a sentence that cannot claim
"live" about a row that is not, the submitted rows getting their own group, and the
5/10/15-minute schedule that asks Amazon instead of waiting to be asked.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


LS = read("static", "js", "liststatus.js")
LJ = read("static", "js", "listings.js")
MT = read("static", "js", "miles_template.js")
RQ = read("static", "js", "runqueue.js")
SB = read("static", "js", "submit.js")
AV = read("static", "js", "autoverify.js")
DH = read("templates", "dashboard.html")


# ---------------------------------------------------------------- behaviour
# The predicates are RUN, not just grepped: the whole defect was two rules that
# looked reasonable in isolation and disagreed when applied to the same row.
JS_ASSERT = r"""
function eq(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log((ok ? "PASS " : "FAIL ") + label + (ok ? "" : "  got=" + JSON.stringify(got)));
  if(!ok) process.exitCode = 1;
}
// A row this app sent to Amazon, which Amazon has not confirmed yet.
const pending = {status: "SUBMITTED", sku: "9.99_2Days_B0BP1HNW8G"};

eq("SUBMITTED is not published",        lsIsPublished(pending), false);
eq("SUBMITTED WAS sent to Amazon",      lsWasSentToAmazon(pending), true);
eq("SUBMITTED is waiting on Amazon",    lsIsWaitingOnAmazon(pending), true);
eq("LIVE is published",                 lsIsPublished({status: "LIVE"}), true);
eq("LIVE is not waiting",               lsIsWaitingOnAmazon({status: "LIVE"}), false);
eq("APPROVED is not published",         lsIsPublished({status: "APPROVED"}), false);
eq("APPROVED is not waiting",           lsIsWaitingOnAmazon({status: "APPROVED"}), false);
eq("APPROVED was never sent",           lsWasSentToAmazon({status: "APPROVED"}), false);
eq("blank status is not sent",          lsWasSentToAmazon({}), false);
eq("lower case still counts",           lsWasSentToAmazon({status: "submitted"}), true);

// Once Amazon's catalogue lists the SKU, the same row IS published and is no
// longer waiting -- without the stored word having changed.
LIVE_ITEMS = [{sku: "9.99_2Days_B0BP1HNW8G", asin: "B0HCVFW53Y"}];
eq("catalogue hit makes it published",  lsIsPublished(pending), true);
eq("  and it stops waiting",            lsIsWaitingOnAmazon(pending), false);
LIVE_ITEMS = [];

// The sentence. This is the one that was lying.
const pendingHtml = lsVerdictHtml("ok_submit_pending", "");
eq("accepted does NOT claim published", /Published live/i.test(pendingHtml), false);
eq("  nor 'now live on your account'",  /now live on your account/i.test(pendingHtml), false);
eq("  it says accepted",                /Accepted by Amazon/i.test(pendingHtml), true);
eq("  and says it is not live yet",     /not live yet/i.test(pendingHtml), true);
eq("  and gives Amazon's own timing",   /5.{0,3}30/.test(pendingHtml), true);

const liveHtml = lsVerdictHtml("ok_live", "");
eq("confirmed live may say so",         /Published live to Amazon/i.test(liveHtml), true);
"""

print("== the rules, actually run ==")
node = None
for cand in ("node", "node.exe"):
    try:
        subprocess.run([cand, "--version"], capture_output=True, timeout=30)
        node = cand
        break
    except Exception:
        continue

if not node:
    print("  node not available -- behaviour checks SKIPPED (static checks still run)")
else:
    # liststatus.js declares its helpers with const/function at top level, which in
    # a vm context are not visible to a second script. Concatenating keeps them in
    # one lexical scope, which is also how the browser loads the file.
    src = "var LIVE_ITEMS = [];\n" + LS + "\n" + JS_ASSERT
    tmp = os.path.join(tempfile.gettempdir(), "_liststatus_check.js")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        p = subprocess.run([node, tmp], capture_output=True, text=True, timeout=120)
        for line in (p.stdout or "").splitlines():
            print("  " + line)
            if line.startswith("FAIL "):
                fails.append(line[5:].strip())
        if p.returncode != 0 and not (p.stdout or "").strip():
            fails.append("liststatus.js did not run: " + (p.stderr or "")[:300])
            print("  liststatus.js did not run: " + (p.stderr or "")[:300])
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


# ------------------------------------------------------- one definition only
print("\n== one definition of 'is this published' (Rule 12) ==")
truthy("the rule lives in liststatus.js", "function lsIsPublished(" in LS)
truthy("isPublishedRow delegates to it",
       "function isPublishedRow(r){ return lsIsPublished(r); }" in LJ)
falsy("  and keeps no copy of the rule",
      'const skus  = new Set((LIVE_ITEMS||[]).map(x=>n(x.sku))' in LJ)
truthy("wasPublished delegates too", "function wasPublished(r){ return lsWasSentToAmazon(r); }" in MT)
falsy("  and the second copy of the set is gone",
      'const _PUBLISHED_STATES = new Set(["LIVE", "SUBMITTED"]);' in MT)
# The two questions are different and must stay named apart -- collapsing them is
# what produced the bug in the first place.
truthy("'did we send it' is its own question", "function lsWasSentToAmazon(" in LS)
truthy("'is it live now' is its own question", "function lsIsPublished(" in LS)
truthy("  and the difference is written down", "different question" in MT.lower()
       or "DIFFERENT question" in MT)


# ------------------------------------------------------------ the classifier
print("\n== 'accepted' is never read as 'live' ==")
# "SUBMITTED -- accepted by Amazon (live shortly)" contains BOTH words, so the
# order of these two tests is load-bearing: submitted must be tested first.
for name, src in (("runqueue.js", RQ), ("submit.js", SB)):
    i_sub = src.find('low.indexOf("submitted")')
    i_live = src.find('low.indexOf("live")>=0){')
    truthy("%s tests 'submitted' first" % name, i_sub > 0 and i_live > 0 and i_sub < i_live)
falsy("no file still lumps the two together",
      'low.indexOf("live")>=0 || low.indexOf("submitted")>=0' in RQ + SB)
falsy("and neither hardcodes the old sentence",
      "Published live to Amazon.</div>" in RQ or "Published live to Amazon.</div>" in SB)
truthy("both render through the shared wording", "lsVerdictHtml(" in RQ and "lsVerdictHtml(" in SB)


# ------------------------------------------------------------- the schedule
print("\n== the app asks Amazon, instead of waiting to be asked ==")
truthy("there is a post-submit schedule", "const AV_CHECKS" in AV)
truthy("  re-checking at 5 minutes", "5 * 60 * 1000" in AV)
truthy("  and again at 10", "10 * 60 * 1000" in AV)
truthy("  warning at 15", "AV_WARN_AT = 15 * 60 * 1000" in AV)
truthy("  in the owner's words",
       "this is unusual, check Seller Central" in AV)
truthy("a submit starts the clock", "avSubmitted(sku)" in RQ)
# It must drive the EXISTING verify mode, not a second implementation of it.
truthy("it drives the existing verify run", "/run/api_verify?skus=" in AV)
falsy("  and does not call Amazon itself", "putListingsItem" in AV or "sp_api" in AV)
# A schedule that only survives while the tab is open is just the Sync button.
truthy("the schedule survives a refresh", "localStorage" in AV)
truthy("it is scoped to one account", "account" in AV and "avAccountId" in AV)


# --------------------------------------------------------------- the group
print("\n== submitted listings are shown as submitted, not as drafts ==")
truthy("there is a group for them", 'Submitted — waiting on Amazon' in AV)
# Both views split waiting rows out of the generated ones, and QUEUED rows out
# of both. The filters gained the _isQueued term when the queue moved into the
# listings store, so the shape of the test is the same and the predicate is not.
truthy("the Drafts view splits them out",
       "notPublished.filter(r=>!_isQueued(r) && _isWaiting(r))" in MT)
truthy("  and the All view splits them the same way",
       "real.filter(r => !_isQueued(r) && _isWaiting(r))" in MT)
truthy("  with queued rows in a group of their own",
       "real.filter(_isQueued)" in MT and "notPublished.filter(_isQueued)" in MT)
truthy("  asked of the shared rule, not tested inline",
       "lsIsQueued(r)" in MT)
truthy("both render the group", MT.count("submittedGroupHtml(") >= 2)
# IT NO LONGER SAYS "Nothing here needs doing". That was true of a listing
# submitted two minutes ago and false of one submitted yesterday that Amazon is
# refusing -- and the group could not tell them apart, because it never showed
# what Amazon said. It does now, so the group reports the answer instead of
# promising there isn't one.
truthy("the group shows Amazon's own answer per listing", "avAmazonSaid(" in AV)
truthy("  read from the note the verify run records", "RE-VERIFI" in AV)
truthy("  and a refusal is not styled as a quiet aside",
       "var(--red)" in AV)
truthy("there is always a way to ask Amazon now",
       "avCheckStaleNow(" in AV and "Ask Amazon now" in AV)

# --------------------------------------------- it keeps asking after 15 minutes
print("\n== a listing submitted yesterday is still chased ==")
# The 5/10/15 schedule ran out and nothing ever asked again, so a SUBMITTED row
# sat untouched indefinitely -- the reported defect.
truthy("opening the screen re-checks what is still waiting",
       "async function avCheckStaleOnLoad(" in AV)
truthy("  it asks the shared rule which rows those are",
       "lsIsWaitingOnAmazon(r)" in AV)
truthy("  bounded by a per-SKU cooldown", "AV_STALE_COOLDOWN" in AV)
truthy("  and a cap per screen open", "AV_STALE_MAX" in AV)
truthy("  and it reuses the existing verify run, not a new call",
       "avRunVerify(" in AV)
SB = open("static/js/submit.js", encoding="utf-8").read()
truthy("the listings load actually triggers it", "avCheckStaleOnLoad()" in SB)
# An empty Drafts list must not claim there is nothing here when the waiting group
# is full -- that is the old "no listings in this view" wrong answer, moved.
truthy("an empty drafts list accounts for them",
       "(!draftsHtml && !waitingHtml && !queuedHere)" in MT)


# ------------------------------------------------------------- load order
print("\n== the shared rule is loaded before anything that calls it ==")
i_ls = DH.find("/static/js/liststatus.js")
i_lj = DH.find("/static/js/listings.js")
i_av = DH.find("/static/js/autoverify.js")
truthy("liststatus.js is loaded", i_ls > 0)
truthy("  before listings.js", i_ls > 0 and i_lj > 0 and i_ls < i_lj)
truthy("autoverify.js is loaded", i_av > 0)


print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
