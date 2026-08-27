"""The Repricer never blanks itself for a one-item action.

    "when i arm a sku the screen shows blank and only a confirmation
     notification message appears on the screen and then the data comes back on
     the screen, this should not be happening, i told you earlier about this"

WHAT WAS HAPPENING. Every action -- arming, disarming, setting a target,
holding a price, adding or removing a supplier -- finished by calling
sourcingLoad(). Its first statement replaced the whole table with a spinner:

    body.innerHTML = '<div class="cc" ...>Loading…</div>'

and only THEN went and fetched sixty-seven decisions. So for as long as that
took, the screen held a spinner and a toast and nothing else. Every open panel
shut and the scroll jumped to the top. On a phone, where the fetch is slower,
it reads as the app having lost the page.

THE FIX IS NOT "make it faster". A refresh that redraws from nothing is wrong
however fast it is, because it throws away what the person was looking at.
sourcingLoad(quiet) leaves the old table on screen until the new HTML is ready,
swaps it in one go, and puts the open rows and the scroll position back.

WHICH ONES MAY STILL BE LOUD. The first load, and the four buttons that change
what the list CONTAINS -- re-reading every supplier, tracking everything,
clearing all suppliers, importing a sheet. There the wait is real, the whole
list is about to be different, and a spinner is honest about it.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


JS = io.open(os.path.join("static", "js", "sourcing.js"),
             encoding="utf-8").read()

print("=== the quiet path exists and really is quiet ===")
_fn = JS.split("async function sourcingLoad(quiet){")[1].split("\n/*")[0]
truthy("sourcingLoad takes a quiet flag", "async function sourcingLoad(quiet)" in JS)
# THE BLANK IS THIS ONE LINE, and it must be behind the flag.
truthy("  the spinner is only drawn when NOT quiet", "if(!quiet){" in _fn)
truthy("    and that is the only thing that empties the table",
       _fn.count("body.innerHTML") == 3)     # spinner + two error paths
# A quiet refresh that FAILS must leave what is on screen alone. Replacing a
# working table with an error because a background refresh timed out would be
# worse than the stale table.
truthy("  a failed quiet refresh keeps the table and says so in a toast",
       'if(quiet){ toast("Could not refresh: "' in _fn)
truthy("  it remembers which rows were open",
       'tr[id^="srcrow_"]' in _fn and "table-row" in _fn)
truthy("  and where the page was scrolled to", "window.scrollY" in _fn)
truthy("  putting both back afterwards",
       "window.scrollTo(0, scrollY)" in _fn)

print("\n=== every one-item action refreshes QUIETLY ===")
# Walk each call and name the function it sits in, so a new action added later
# that forgets the flag is caught here rather than by somebody on a phone.
LOUD_OK = {
    # These change what the LIST CONTAINS, not one row in it.
    "sourcingCheckNow",        # re-reads every supplier
    "sourcingTrackAll",        # enrolls everything not yet tracked
    "sourcingClearSuppliers",  # deletes every supplier link
    "sourcingUpload",          # a whole sheet of suppliers
    "sourcingCheckListings",   # asks Amazon about every SKU
    "sourcingGetFees",         # asks Amazon about every SKU
}


def enclosing(src, pos):
    head = src.rfind("function ", 0, pos)
    while head >= 0:
        m = re.match(r"function\s+([A-Za-z_$][\w$]*)", src[head:head + 80])
        if m:
            return m.group(1)
        head = src.rfind("function ", 0, head)
    return "?"


loud, quiet = [], []
for m in re.finditer(r"sourcingLoad\((true)?\)", JS):
    ls = JS.rfind("\n", 0, m.start()) + 1
    if JS[ls:m.start()].lstrip().startswith(("//", "*")):
        continue
    fn = enclosing(JS, m.start())
    if fn == "sourcingLoad":          # its own declaration
        continue
    (quiet if m.group(1) else loud).append(fn)

print("  quiet in %d place(s), loud in %d" % (len(quiet), len(loud)))
offenders = sorted(set(f for f in loud if f not in LOUD_OK
                       and f != "sourcingOnOpen"))
check("no one-item action blanks the screen", offenders, [])
# The ones that matter most, named, because they are the ones reported.
for fn in ("sourcingArm", "sourcingSaveRule", "sourcingBulkArm"):
    truthy("  %s refreshes quietly" % fn, fn in quiet)

print("\n=== the first load is still allowed to be loud ===")
# Opening the screen from nothing SHOULD show a spinner: there is no stale
# table to keep, and a blank page with no explanation is worse.
truthy("opening the screen loads loudly",
       "function sourcingOnOpen(){ sourcingLoad(); }" in JS)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
