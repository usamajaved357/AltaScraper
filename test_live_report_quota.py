"""Opening the listings page must not commission an Amazon report.

    "The listings page at /listings is triggering Amazon report rate-limits on
     page load."

WHAT WAS ACTUALLY HAPPENING. The click path was already innocent: /live/catalog
returns the saved snapshot and never builds a report unless `force` is set, and
`enterAccount` calls it with force=false. But the Live/All tab took a second
step afterwards, in setListSource:

    const old = c && c.syncedAt && (Date.now()-c.syncedAt > LIVE_AUTOSYNC_MS);
    if(nothingYet || old){ ... backgroundSync(); }      // -> force:true

and `old` was true on essentially every load. The arithmetic, not bad luck:

    29 account+marketplace pairs in live_snapshots.json
     2 reports per sync (GET_MERCHANT_LISTINGS_ALL_DATA, then _INACTIVE_DATA)
    ~1 report per minute is what Amazon allows per selling account

so a ten-minute freshness target was never reachable, and the saved snapshots
were in fact 1.9 to 7.5 hours old -- every one of them past the threshold. And
it ran on a PAGE LOAD, not just a click, because shell.js restores ?src=live|all
from the address bar.

THE SECOND HALF, and the reason it never recovered: the code that reuses a
report Amazon has ALREADY BUILT could not run. Both reuse blocks were guarded by
`if not force:` -- a hundred lines below the point where a falsy `force` had
already returned. Dead code. The proof is in the data rather than the reading:
all 29 saved snapshots record report_source="new", and "reused" has never once
been written since the field existed.

    ask Amazon for a new report only when what we hold is older than
    anything Amazon can already give us

is the whole rule, and it now has somewhere to be true.

THE THIRD PART is the message. A throttled inactive report that successfully
falls back to Amazon's last completed one is a fully populated catalogue -- yet
it was filed as a `warning`, which toasts, and sets `partial`. So the rate-limit
message appeared when nothing was wrong. That is how a message stops being read
before the day it matters.
"""
import io
import json
import os
import re
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
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


J = read("static", "js", "miles_template.js")
R = read("routes", "live_routes.py")
S = read("static", "js", "shell.js")
# Comments describe intent; only code can break. Strip them for the assertions
# that are about behaviour.
JCODE = "\n".join(l.split("//")[0] for l in J.splitlines()
                  if not l.strip().startswith(("*", "/*", "//")))
RCODE = "\n".join(l.split("#")[0] for l in R.splitlines()
                  if not l.strip().startswith("#"))

print("== a page load asks Amazon for nothing ==")
# The Live tab is reachable straight from the address bar, so this IS a load.
truthy("shell.js restores ?src=live|all on load", 'setListSource(src)' in S)
_ss = JCODE.split("function setListSource")[1].split("\nasync function")[0]
truthy("the load path still pulls the saved copy", "loadLiveCatalog(false)" in _ss)
truthy("  and still fetches when there is nothing at all", "nothingYet" in _ss)
truthy("    which is the only case that forces", "backgroundSync();" in _ss)
# THE FIX: the staleness trigger is gone from the load path.
falsy("a merely-old saved copy no longer forces a sync",
      "LIVE_AUTOSYNC_MS" in _ss)
falsy("  the `old` test is gone entirely", re.search(r"\bold\b\s*=", _ss))
check("  exactly one forced call remains on this path",
      _ss.count("backgroundSync()"), 1)
# Single-line fragments, matched case-sensitively. The sentence wraps in the
# source and the comment writes "ONE report a minute" in capitals; matching
# across the line break, or in the wrong case, is how these assertions fail on
# correct code.
truthy("why is written down, with the arithmetic",
       "29 account+marketplace pairs" in J)
truthy("  including Amazon's limit", "ONE report a minute" in J)
truthy("  and who is responsible instead", "live_refresher" in J)

print("\n== an automatic refresh says so, a person pressing Sync does not ==")
truthy("the timer marks itself automatic", "loadLiveCatalog(true, {auto: true})"
       in JCODE)
truthy("  the flag reaches the server", '"auto":auto' in JCODE
       or "auto:auto" in JCODE)
check("  both catalogue fetches send it", JCODE.count("auto:auto"), 2)
truthy("  and __all__ passes it down", "loadAllMarketplaces(force, opts)" in JCODE)
# syncLive/refreshView are button presses and must NOT be marked automatic.
for fn in ("syncLive", "refreshView"):
    if "function " + fn in JCODE:
        _b = JCODE.split("function " + fn)[1][:700]
        falsy("  %s stays a human sync" % fn, "auto" in _b)

print("\n== the reuse gate is reachable at all ==")
# The bug: `if not force:` a hundred lines below where falsy force returned.
truthy("reuse is decided by a named condition", "may_reuse = " in RCODE)
truthy("  set from the two automatic callers",
       'b.get("_bg")' in RCODE and 'b.get("auto")' in RCODE)
check("  and used by both reports", RCODE.count("if may_reuse:"), 2)
# There must be exactly ONE `if not force:` left -- the legitimate snapshot path.
check("only the snapshot path is still gated on `not force`",
      RCODE.count("if not force:"), 1)
_snap_gate = RCODE.split("if not force:")[1][:600]
truthy("  and that one is the snapshot read", "_snap.get(" in _snap_gate)
truthy("the dead-code history is recorded", "dead code" in R)
truthy("  with the evidence from the saved snapshots",
       'report_source="new"' in R and "29" in R)

print("\n== reuse can never stall the catalogue ==")
# Reusing "any report from the last 6h" would re-download the same old report
# forever while stamping each copy with a fresh ts -- hiding staleness instead
# of fixing it.
_reuse = RCODE.split("if may_reuse:")[1][:1400]
truthy("the window is floored at our own snapshot", "_held_ts" in _reuse)
truthy("  taken from the saved record", "_snap.get(" in _reuse)
truthy("  and only used when it is the LATER of the two", "_floor" in _reuse)
truthy("the inactive report is bounded the same way",
       "_held_age" in RCODE and "min(_win" in RCODE)
truthy("the stalling hazard is written down", "stall the catalogue" in R)
truthy("  and the rule stated plainly", "older than anything" in R)

print("\n== a fully successful sync says nothing about rate limits ==")
_thr = RCODE.split("_idoc, _iage = _newest_inactive(None)")[1][:900]
truthy("the throttle fallback files a note", "notes.append(" in _thr)
falsy("  not a warning", "warnings.append(" in _thr)
# The rate-limit wording is GONE FROM THIS BRANCH but deliberately kept in the
# branch below it, where no fallback report was found and suppressed listings
# really are absent. That case has always been a warning and stays one -- the
# point was never to silence the message, only to stop it firing when nothing
# was wrong.
falsy("the fallback branch no longer mentions rate limiting",
      "rate-limit" in _thr or "rate limiting" in _thr)
truthy("  it explains the timestamp instead", "last completed report" in _thr)
truthy("the no-fallback branch still says it plainly",
       "Amazon is rate-limiting report requests just now, so" in RCODE)
# The genuinely-incomplete cases MUST still warn.
truthy("a missing inactive report still warns",
       'warnings.append("Inactive/suppressed listings could not be loaded'
       in RCODE)
truthy("  and so does the no-fallback throttle",
       "suppressed and inactive listings are not included" in RCODE)

print("\n== warnings and notes stay apart, all the way to the screen ==")
truthy("the response carries both", '"notes": list(notes or [])' in RCODE)
check("  warnings is warnings only",
      '"warnings": list(warnings or []),' in RCODE, True)
falsy("  they are no longer merged",
      "list(warnings or []) + list(notes or [])" in RCODE)
truthy("partial still means a category is missing", '"partial": bool(warnings)'
       in RCODE)
falsy("  so a note cannot make a sync look partial",
      "bool(warnings) + bool(notes)" in RCODE or "bool(notes)" in RCODE)
truthy("the browser interrupts for warnings", "toast(j.warnings.join" in JCODE)
falsy("  and never for notes", "toast(j.notes" in JCODE
      or "j.notes.join" in JCODE.split("toast(")[1][:120] if "toast(" in JCODE
      else False)
truthy("  notes reach the sync label instead", "c.notes && c.notes.length" in JCODE)
truthy("    where the warnings already were", "c.warnings && c.warnings.length"
       in JCODE)

print("\n== a stored warning is not replayed as a fresh alarm ==")
# The snapshot path returns what was written possibly hours ago, and the browser
# toasts warnings on arrival -- so this popped a message about a long-finished
# hiccup on every cached load.
_snapret = RCODE.split('"from_snapshot": True')[1][:900]
truthy("the cached reply sends no warnings", '"warnings": []' in _snapret)
truthy("  the stored text comes back as notes",
       '"notes": _rec.get("warnings")' in _snapret)
truthy("  and partial still labels it", '"partial": _rec.get("partial"' in _snapret)
truthy("only real warnings are written to disk",
       "warnings=list(warnings or [])" in RCODE)
falsy("  notes are not persisted",
      "warnings=(list(warnings or []) + list(notes or []))" in RCODE)
truthy("why is recorded", "still be true whenever it is next read" in R)

print("\n== against the live snapshot store, if it is here ==")
_p = os.path.join(HERE, "live_snapshots.json")
if os.path.exists(_p):
    d = json.load(io.open(_p, encoding="utf-8"))
    recs = {k: v for k, v in d.items() if isinstance(v, dict)}
    print("     (%d saved account+marketplace pairs)" % len(recs))
    srcs = {}
    for v in recs.values():
        s = str(v.get("report_source") or "")
        srcs[s] = srcs.get(s, 0) + 1
    print("     report_source seen: %r" % srcs)
    # This is the measurement that proves the reuse block never ran. It is
    # recorded, not asserted: once the fix ships, "reused" starts appearing and
    # an assertion that it is absent would then fail for the right reason.
    truthy("every pair has a timestamp to compare against",
           all(isinstance(v.get("ts"), (int, float)) for v in recs.values()))
    import time
    ages = sorted((time.time() - float(v["ts"])) / 3600.0
                  for v in recs.values() if v.get("ts"))
    if ages:
        print("     ages in hours: min %.1f  max %.1f" % (ages[0], ages[-1]))
        # The load path used to force whenever this exceeded 10 minutes.
        over = sum(1 for a in ages if a > (10 / 60.0))
        print("     %d of %d were past the old 10-minute trigger" % (over, len(ages)))
else:
    print("     (no live_snapshots.json here -- the source checks stand)")

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
