"""Submitting from the list left nothing on screen and nothing following it.

    "when i submit the approved row from drafts i see no progress or log what
     happened to that listing"

THE PROGRESS PANEL LIVES INSIDE THE OPEN DRAWER. rqWatch began with

    if(!_runPanel(sku)) return;

and _runPanel looks for `runpanel_<sku>`, which exists only while that listing's
drawer is open. So submitting from a row, with the drawer shut, stopped the
watcher on its first line -- and everything after it was skipped:

    no progress, no log            what was reported
    no terminal verdict            nothing ever said whether Amazon took it
    _rqRefreshRow never ran        so the row itself did not update either
    avSubmitted() never started    so the auto-verify clock that re-asks Amazon
                                   at 5, 10 and 15 minutes never began

That last one is the serious half: a listing submitted from the list was not
being followed at all. The report was about a missing log; the missing log was
the visible edge of a watcher that had never started.

The panel is one place to RENDER, not a precondition for watching.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def rd(p):
    return io.open(os.path.join(HERE, *p.split("/")), encoding="utf-8").read()


RQ = rd("static/js/runqueue.js")
SUB = rd("static/js/submit.js")
CSS = rd("static/css/dashboard.css")

CODE = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", RQ, flags=re.S))


def fn(src, name):
    i = src.find("function " + name + "(")
    if i < 0:
        return ""
    j = src.find("\n}", i)
    return src[i:] if j < 0 else src[i:j + 2]


print("=== the watcher no longer needs a drawer ===")
W = fn(RQ, "rqWatch")
falsy("the early return is gone",
      re.search(r"rqStopWatch\(\);\s*\n\s*if\(!_runPanel\(sku\)\) return;", CODE) is not None)
truthy("  and what it was costing is written down",
       "avSubmitted() never started" in RQ)
# EVERY RENDER IS STILL GUARDED. The panel is optional, not assumed.
truthy("rendering is still conditional on there being a panel", "if(P){" in W)
truthy("  and the panel is re-resolved every tick", "const P=_runPanel(sku);" in W)

print("\n=== and the terminal work happens either way ===")
# These three lines sit AFTER the if(P) block, so they run with or without one.
for what, mark in (("the row is refreshed", "_rqRefreshRow(sku)"),
                   ("the queue badge is updated", "rqGlobalPollNow()"),
                   ("the streaming lock is dropped", "window.RUN_STREAMING=false")):
    truthy("  " + what, mark in W)
# THE ONE THAT MATTERS MOST.
truthy("the auto-verify clock starts on the JOB, not the panel",
       'typeof avSubmitted==="function"' in W and "avSubmitted(sku)" in W)
_iP = W.find("if(P){")
_iAv = W.find("avSubmitted(sku)")
truthy("  and it is outside the panel branch", _iAv > _iP and
       W.find("}else{", _iP) < _iAv)

print("\n=== with no panel, the outcome is said out loud ===")
truthy("there is an outcome reporter", "function _rqSayOutcome" in RQ)
truthy("  called when there is no panel", "_rqSayOutcome(st, sku, mode, j.status)" in W)
S = fn(RQ, "_rqSayOutcome")
# IT READS THE SAME PARSED STATE _rqFinish DOES -- one conclusion per run.
for field in ("st.verdict", "st.summary", "st.notSubmitted", "st.sawStart"):
    truthy("  it reads %s, as the panel version does" % field, field in S)
falsy("  and does not parse the log again", "_rqParseLine" in S)
# Every branch _rqFinish has, this one answers too.
for kind in ("nocreds", "network", "missing", "error", "ok_submit_pending"):
    truthy("  it handles %s" % kind, kind in S)
truthy("  a submit that sent nothing says so", "NOT sent to Amazon" in S)
# ACCEPTED IS NOT LIVE. Amazon publishes 5-30 minutes later.
truthy("  accepted is not claimed as live", "Amazon accepted it" in S)
falsy("    and never called live", re.search(r"is now live|it is live", S) is not None)
truthy("  with the reason that distinction matters recorded",
       "would be a claim nobody has checked" in RQ)

print("\n=== there is something to watch while it runs ===")
E = fn(RQ, "rqEnqueue")
truthy("no drawer -> the runs panel is opened", "rqTogglePanel" in E)
truthy("  only when it is not already open", "!RQ._panelOpen" in E)
truthy("  and only when there is no drawer panel", "else if" in E)

print("\n=== the badge outlives the run ===")
B = fn(RQ, "rqRenderBadge")
truthy("it lingers after the queue empties", "RQ_BADGE_LINGER_MS" in RQ)
truthy("  tracked from when a job was last active", "RQ._lastActiveAt = Date.now()" in B)
truthy("  and the field is declared", "_lastActiveAt:0" in RQ)
# A BADGE SAYING "0 running" WOULD BE WORSE THAN NONE.
truthy("  it lingers only when something actually finished", "recent.length" in B)
truthy("  saying whether it failed", '" failed — open"' in B or "failed — open" in B)
truthy("  and it does go away", 'el.style.display="none"' in B)
# It stops pulsing, because a pulsing dot means "working".
truthy("the finished badge is styled", ".rqbadge.ok" in CSS and ".rqbadge.bad" in CSS)
truthy("  and stops pulsing", "animation:none" in CSS)
truthy("  in the app's own colours, not new ones",
       "background:var(--ok)" in CSS and "background:var(--red)" in CSS)

print("\n=== the submit path itself is unchanged ===")
# Nothing here touches what is sent or when -- only what is shown about it.
truthy("submitOne still confirms the account", "PUBLISH THIS LISTING LIVE" in SUB)
truthy("  still checks for a local image first", "/submit/precheck" in SUB)
truthy("  still warns about an existing live SKU", "/dup_check" in SUB)
truthy("  and still goes through the queue", "rqEnqueue(sku, \"api_submit\"" in SUB)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
