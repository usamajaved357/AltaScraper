"""A user restricted to one account must not be able to read another one.

    "why is one user able to see the information of another user, every account
     is separate. everything of it should stay separate ... i am concerned that
     when i give this tool out to random people to test and use they will be
     able to see other people information"

THE DESIGN WAS SOUND AND HAD STOPPED BEING TRUE.

auth/guard.py refuses the workspace SWITCH -- and because every data route used
to read whichever account was currently selected, that one choke point covered
all of them. It says so in its own comment: "Blocking only the UI would leave
the data one fetch() away."

Then routes started taking an EXPLICIT account -- ?id=jack_uk -- so a screen
could say which account it was showing instead of trusting a process-wide
variable. That was itself a fix, for a real bug where pressing Generate while
looking at Jack Reacherd ran the generator against Nestwell.

But check() was handed the PATH ONLY. It never saw the query string. MEASURED,
with a user whose workspaces list is ["nestwell_goods"]:

    POST /accounts/select {id: jack_uk}  -> refused, correctly
    GET  /trackers?id=jack_uk            -> ALLOWED
    GET  /catalog/products?id=jack_uk    -> ALLOWED
    GET  /overview                       -> ALLOWED, and read every account

The switch was bolted and the window was open.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth import guard, users  # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def truthy(label, got):
    check(label, bool(got), True)


def user(workspaces, role="lister"):
    return {"id": "u", "email": "x@example.com", "name": "X", "active": True,
            "role": role, "workspaces": list(workspaces),
            "features": {f: "edit" for f in users.FEATURES},
            "permissions": ["edit"]}


VA = user(["nestwell_goods"])          # may see one account
BOSS = user([users.ALL_WORKSPACES], "owner")   # may see everything

print("== the switch is still refused, as it always was ==")
check("selecting another workspace",
      guard.check("/accounts/select", "POST", VA, {"id": "jack_uk"})[0], False)
check("  and the one they own is allowed",
      guard.check("/accounts/select", "POST", VA, {"id": "nestwell_goods"})[0], True)

print("\n== and now so is naming one in the query string ==")
# The hole. Every one of these was ALLOWED before.
for path in ("/trackers", "/catalog/products", "/leading", "/run/plan",
             "/weekly/list", "/daily/check", "/sqp", "/categories",
             "/compliance/scans", "/drppc/status", "/inventory/stock"):
    check("GET %s?id=jack_uk" % path,
          guard.check(path, "GET", VA, None, {"id": "jack_uk"})[0], False)

print("\n== every spelling of the parameter, not just the one I thought of ==")
for field in ("id", "account_id", "workspace_id", "workspace", "ws"):
    check("  ?%s=jack_uk is refused" % field,
          guard.check("/trackers", "GET", VA, None, {field: "jack_uk"})[0], False)
check("  and in a POST body too",
      guard.check("/trackers/refresh", "POST", VA, {"id": "jack_uk"}, None)[0], False)

print("\n== their OWN account still works ==")
# A security fix that blocks ordinary work is a security fix nobody keeps.
for path in ("/trackers", "/catalog/products", "/leading", "/weekly/list"):
    check("GET %s?id=nestwell_goods" % path,
          guard.check(path, "GET", VA, None, {"id": "nestwell_goods"})[0], True)
check("  and a request naming no account is untouched",
      guard.check("/trackers", "GET", VA, None, {})[0], True)

print("\n== an owner is unaffected ==")
for path in ("/trackers", "/catalog/products", "/brief"):
    check("owner GET %s?id=jack_uk" % path,
          guard.check(path, "GET", BOSS, None, {"id": "jack_uk"})[0], True)

print("\n== an 'id' that is not a workspace is left alone ==")
# Deleting a media file by id, editing a user by id, a notification channel by
# id -- these carry an `id` that means something else entirely, and checking it
# against the workspace list would refuse ordinary work.
#
# Asserted on named_workspace() rather than on check(), and the difference
# matters: /users and /notify are refused for this user anyway, by PERMISSIONS,
# which is correct and has nothing to do with workspace scope. The first version
# of this test conflated "the workspace check did not fire" with "the request
# was allowed" and reported two failures that were the permission system working
# properly.
for path, args in (("/users", {"id": "u123"}),
                   ("/media/delete", {"id": "abc"}),
                   ("/notify/channel", {"id": "3"}),
                   ("/trackers/watch", {"id": "B0XXXXXXXX"}),
                   ("/genimage/job_status", {"id": "job1"})):
    check("%-26s id is not read as a workspace" % path,
          guard.named_workspace(path, args, None), "")
# ...while a data route's id IS read as one.
check("but /trackers?id= IS a workspace",
      guard.named_workspace("/trackers", {"id": "jack_uk"}, None), "jack_uk")

print("\n== the doorman actually passes the query string ==")
# The check is only real if the thing calling it hands over what it needs.
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "auth", "guard.py"), encoding="utf-8").read()
truthy("before_request passes request.args",
       "check(request.path, request.method, user, body, request.args)" in src)
truthy("  and the check reads them", "named_workspace(p, args, json_body)" in src)
truthy("  before features or permissions are considered",
       src.index("named_workspace(p, args") < src.index("feat = feature_for(p)"))

print("\n== NO screen reads every account any more ==")
# There WAS one: the Business overview aggregated all six limited companies and
# was reachable from inside any one of them. The doorman could not help it --
# no account is named for it to refuse -- so it filtered the list itself.
#
# It was deleted whole on 21 Aug 2026, on request: "why am i watching this in
# jack reacherd ... you should delete that page entirely for now". What it did
# that is still wanted, one account across its own marketplaces, is
# /brand/marketplaces, which IS scoped and needs no filtering of its own.
_gone = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "routes", "overview_routes.py")
check("the cross-account route is gone", os.path.exists(_gone), False)
check("  and nothing registers it",
      "_overview_routes.register" in open(os.path.join(
          os.path.dirname(os.path.abspath(__file__)), "dashboard.py"),
          encoding="utf-8").read(), False)
truthy("  the scoped replacement exists",
       os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "routes", "brandview_routes.py")))
_bv = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "routes", "brandview_routes.py"), encoding="utf-8").read()
truthy("  and it resolves ONE account", "_scope_mod.resolve(" in _bv)

print("\n== an empty workspace list is not a wildcard ==")
# Recorded in auth/users.py as a fail-open that was already fixed once. Guarded
# here too, because it is the single worst way this could regress.
NOBODY = user([])
check("a user with no workspaces may open none",
      users.can_access_workspace(NOBODY, "jack_uk"), False)
check("  not even the default one",
      users.can_access_workspace(NOBODY, ""), False)
check("  and is refused by the guard",
      guard.check("/trackers", "GET", NOBODY, None, {"id": "jack_uk"})[0], False)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
