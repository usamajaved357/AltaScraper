"""One name for "the account the route was handed, else the open one" (architecture batch A5).

Fifteen route sites wrote the same fallback out by hand:

    aid = b.get("id", "") or _state.get("active_account_id", "")

They now call domain.request_account.id_or_open(asked, state). This pins that
the helper answers EXACTLY as the expression did for every kind of input --
including the real WorkspaceState object the routes are given -- and that the
hand-written reads of the open account in routes/ can only go down from here.
"""
import glob
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
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from domain.request_account import id_or_open

print("=== the same answer as the hand-written expression ===")
states = [{}, {"active_account_id": ""}, {"active_account_id": None},
          {"active_account_id": "jack_uk"}, {"active_account_id": " spaced "}]
asks = ["", None, "nestwell_goods", " spaced ", 0, 7]
for st in states:
    for a in asks:
        b = {"id": a}
        old = b.get("id", "") or st.get("active_account_id", "")
        check("asked=%r open=%r" % (a, st.get("active_account_id", "<unset>")),
              id_or_open(b.get("id", ""), st), old)
b = {}
check("no id in the body at all", id_or_open(b.get("id", ""), {"active_account_id": "x"}),
      b.get("id", "") or "x")

print("=== with the real WorkspaceState the routes are given ===")
import dashboard as D
_had = "active_account_id" in D._state
_prev = D._state.get("active_account_id", "")
try:
    D._state["active_account_id"] = "open_one"
    check("falls back to the open account", id_or_open("", D._state), "open_one")
    check("  the named one wins", id_or_open("named", D._state), "named")
finally:
    if _had:
        D._state["active_account_id"] = _prev
    else:
        D._state.pop("active_account_id", None)

print("=== the copies are gone and cannot come back ===")
# Both spellings of the read: .get("...") / .get('...') and ["..."] / ['...'].
RX = r'_state(?:\s*or\s*\{\}\))?(?:\.get\(\s*|\[\s*)["\']active_account_id["\']\s*[\),\]](?!\s*=[^=])'
EXACT = ('b.get("id", "") or _state.get("active_account_id", "")',
         'request.args.get("id", "") or _state.get("active_account_id", "")')
total = 0
for f in sorted(glob.glob("routes/*.py")):
    src = open(f, "rb").read().decode("utf-8")
    for e in EXACT:
        if e in src:
            fails.append("hand-written copy in %s" % f)
            print("  hand-written copy back in %s: %s" % (f, e))
    total += len(re.findall(RX, src))
# 52 on 29 Sep 2026 after A5 (either quote, .get or [...] reads; writes not counted). The remaining reads differ from the helper (str(),
# strip(), None instead of "", reading ?account= too) -- each is a behaviour of
# its own route, left for its route's batch. Lower this as they move; never raise it.
# 51 on 29 Sep 2026 (evening): the tracking routes stopped falling back to the
# open account (test_tracking_named_account.py).
CEILING = 51
print("  hand-written reads of the open account in routes/: %d (ceiling %d)" % (total, CEILING))
if total > CEILING:
    fails.append("new hand-written read of active_account_id in routes/ (%d > %d): "
                 "use domain.request_account.id_or_open / current / routes.scope" % (total, CEILING))
# AND THE CEILING FOLLOWS THE COUNT DOWN (architecture guard, 29 Sep 2026): a
# ceiling left above the real count is room for a new read to slip in unseen.
if total < CEILING:
    fails.append("the open-account reads fell to %d: lower CEILING from %d to %d"
                 % (total, CEILING, total))

if fails:
    raise SystemExit("FAILED: %d -- %s" % (len(fails), fails[:3]))
print("\nid_or_open answers exactly as the copies did")
