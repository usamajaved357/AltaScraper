"""Deleting every cost on an account, and the three ways that could go wrong.

    "Give me a button to delete the current cogs filled in the account but give
     warning before user decides to delete cogs"

Costs could be put in one at a time and by the sheetful, and only ever taken out
one SKU at a time by emptying its box. So a cost sheet uploaded against the wrong
account -- one wrong click on the account switcher -- had no undo.

THE THREE THINGS THIS HAS TO GET RIGHT, in order of how bad they are:

  1. ONE ACCOUNT. Every workspace's costs share one flat dict keyed
     "<account>::<SKU>". A clear() here wipes Nestwell while Jack's screen is
     open, and nothing would say so until a margin looked wrong weeks later.
  2. THE NUMBER IN THE WARNING IS THE NUMBER THAT GOES. A confirmation that says
     41 and deletes 200 is worse than no confirmation.
  3. IT SAYS WHAT SURVIVES. A cost read out of a SKU's own name
     (8.00_3Days_B0G1K5B7QS) is not stored here and does not go. Without saying
     so, the screen afterwards looks like it lost more than it did.

Run against a temporary config so the real cogs_overrides.json is never touched.
"""
import json
import os
import shutil
import sys
import tempfile

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import cogs_store as cs

TMP = tempfile.mkdtemp(prefix="cogsclear_")
CFG = os.path.join(TMP, "config.json")
with open(CFG, "w", encoding="utf-8") as fh:
    json.dump({}, fh)

SEED = {
    "jack_uk::8.00_3Days_B0G1K5B7QS": 8.0,
    "jack_uk::12.50_2Days_B0ABCDEFGH": 12.5,
    "jack_uk::46 pcs wrench": 4.5,
    "nestwell_goods::9.99_3Days_B0XYZ": 9.99,
    "nestwell_goods::spin mop": 3.25,
    "sheelady_us::5.00_1Days_B0QQQ": 5.0,
}
with open(cs.path_for(CFG), "w", encoding="utf-8") as fh:
    json.dump(SEED, fh)
cs.load(CFG, force=True)

print("=== the count is real before anything is deleted ===")
check("jack_uk has three", cs.count_for(CFG, "jack_uk"), 3)
check("nestwell_goods has two", cs.count_for(CFG, "nestwell_goods"), 2)
check("an account with none says none", cs.count_for(CFG, "headbanger_lures"), 0)
# The warning quotes this number, so a count that disagreed with the delete would
# be a dialog that lies.
check("  and it matches what a delete would remove",
      cs.count_for(CFG, "jack_uk"), 3)

print("\n=== deleting one account leaves every other alone ===")
gone = cs.clear_account(CFG, "jack_uk")
check("it reports what it removed", gone, 3)
check("jack_uk is empty now", cs.count_for(CFG, "jack_uk"), 0)
check("  nestwell_goods is untouched", cs.count_for(CFG, "nestwell_goods"), 2)
check("  and so is sheelady_us", cs.count_for(CFG, "sheelady_us"), 1)
# THE PREFIX IS A PREFIX ON THE KEY SHAPE, not a substring search. An account
# named jack would otherwise take jack_uk's costs with it.
cs.load(CFG, force=True)
with open(cs.path_for(CFG), encoding="utf-8") as fh:
    left = json.load(fh)
check("the file on disk agrees", sorted(left), sorted(
    [k for k in SEED if not k.startswith("jack_uk::")]))

print("\n=== an account name that is a prefix of another is still separate ===")
cs.set_cost(CFG, "jack", "some-sku", 1.0)
cs.set_cost(CFG, "jack_uk", "back-again", 2.0)
check("both exist", (cs.count_for(CFG, "jack"), cs.count_for(CFG, "jack_uk")), (1, 1))
cs.clear_account(CFG, "jack")
check("clearing 'jack' leaves 'jack_uk'", cs.count_for(CFG, "jack_uk"), 1)
check("  and 'jack' is gone", cs.count_for(CFG, "jack"), 0)

print("\n=== an empty account name deletes NOTHING, rather than everything ===")
before = len(cs.all_overrides(CFG))
check("no account id removes nothing", cs.clear_account(CFG, ""), 0)
check("  and None likewise", cs.clear_account(CFG, None), 0)
check("  the store is the size it was", len(cs.all_overrides(CFG)), before)

print("\n=== the dict is mutated, never rebound ===")
# Something registered at startup holds this dict -- dashboard.py takes the
# reference once. Rebinding here would leave every reader on the old one, which
# is the module-identity bug cogs_store.py exists to end.
live = cs.all_overrides(CFG)
cs.set_cost(CFG, "temp_acct", "s1", 1.0)
cs.clear_account(CFG, "temp_acct")
check("the same object is still the store", cs.all_overrides(CFG) is live, True)

shutil.rmtree(TMP, ignore_errors=True)

print("\n=== the route asks before it deletes, and refuses a moved target ===")
RT = open("routes/cogs_routes.py", encoding="utf-8").read()
truthy("there is a count endpoint to word the warning with",
       '@app.route("/cogs/count")' in RT)
truthy("  and it changes nothing", "clear_account" not in
       RT.split('def cogs_count')[1].split("@app.route")[0])
truthy("the delete endpoint exists", '@app.route("/cogs/clear", methods=["POST"])' in RT)
_clear = RT.split("def cogs_clear")[1].split("@app.route")[0]
truthy("  it goes through the store, not its own loop",
       "_cs.clear_account(CONFIG_PATH, aid)" in _clear)
truthy("  it refuses when no account is open", '"no account is open"' in _clear)
# If the stored count moved while the dialog was open -- another tab, a sheet
# upload finishing -- the amount agreed to is not the amount that would go.
truthy("  and refuses when the number has moved under the dialog",
       "expect" in _clear and "409" in _clear)
truthy("  reporting what actually went, not what was asked for",
       '"deleted": gone' in _clear)

print("\n=== it needs the same permission as any other bulk delete ===")
from auth import guard
check("/cogs/clear needs approve_delete",
      guard.required_permission("/cogs/clear", "POST"), "approve_delete")
# Setting ONE cost is ordinary editing and must not have been swept up.
check("  setting one cost is still ordinary editing",
      guard.required_permission("/cogs/set", "POST"), "edit")
check("  and reading the count is a read",
      guard.required_permission("/cogs/count", "GET"), None)

print("\n=== the screen warns, with the number, and says what survives ===")
JS = open("static/js/cogs.js", encoding="utf-8").read()
_fn = JS.split("async function cogsClearAll")[1]
truthy("the count comes from the server, not from the rows on screen",
       '"/cogs/count' in _fn)
truthy("  because the screen only ever shows one view of them",
       "screen" in JS.split("TAKING THEM ALL BACK OUT")[1][:900])
truthy("nothing is deleted without a confirm", "confirm(" in _fn)
truthy("  which states the number", 'Delete all " + n + " saved cost' in _fn)
truthy("  and that it cannot be undone", "cannot be undone" in _fn)
truthy("  and what KEEPS its price afterwards",
       "8.00_3Days_B0G1K5B7QS" in _fn and "read from the name" in _fn)
truthy("  and that every profit figure moves", "profit, margin and ROI" in _fn)
truthy("the agreed number is sent back with the request", "expect: n" in _fn)
# An empty account should not open a dialog offering to delete nothing.
truthy("no confirmation at all when there is nothing to delete",
       "if(!n){" in _fn and "no saved costs" in _fn)
truthy("the local cache is dropped too, or the cells keep drawing stale costs",
       "delete COGS_LOCAL[k]" in _fn)

HTML = open("templates/dashboard.html", encoding="utf-8").read()
truthy("the button is on the toolbar", 'onclick="cogsClearAll()"' in HTML)
# All four cost controls in one group, in order: get the sheet, upload it, learn
# how it works, clear it. A character-distance check broke the moment two more
# buttons went between them, which measures the markup rather than the grouping.
_grp = HTML[HTML.index("/cogs/template.csv"):]
_grp = _grp[:_grp.index("</div>")]
for _what, _mark in (("get the sheet", "/cogs/template.csv"),
                     ("upload it", 'onclick="cogsUploadOpen()"'),
                     ("explain it", 'onclick="cogsExplain()"'),
                     ("clear it", 'onclick="cogsClearAll()"')):
    truthy("  the control to %s is in the same group" % _what, _mark in _grp)
CSS = open("static/css/dashboard.css", encoding="utf-8").read()
# The rule it lives on, not the exact selector text: the Weekly KPIs page grew
# the same kind of button and the two now share one declaration, so pinning the
# literal ".mktbtn.cogswipe{...}" broke on a change that only added a second
# class beside it.
truthy("  and it does not look like them",
       "cogswipe" in CSS and "var(--red)" in
       CSS[CSS.index("cogswipe"):CSS.index("cogswipe") + 200])

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
