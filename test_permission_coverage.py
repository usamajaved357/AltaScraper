"""Every screen must be governed, and forgetting must not be silent.

    "i want the permissions distributed by pages also in the manage permission
     page, the user with permissions should only be able to view the page for
     which the permission is aloted to him"

The per-page permissions already existed: seventeen features, grouped by page,
each none/view/edit, editable in the permissions screen and enforced server-side
by auth/guard.py. What was missing was coverage and the door.

COVERAGE. A screen absent from SECTION_FEATURE is never hidden, and a path
absent from FEATURE_PATHS is governed by RULES alone -- which is "any user who
may edit". Both defaults are OPEN, and nothing says so at the time, so
forgetting is silent.

It had already happened once: guard.py carries a note about ten screens found
ungoverned, where "a person with sales set to `none` could open the Business
Overview and read every account's revenue". It then happened AGAIN with /brief,
added after that note was written -- the weekly business brief, revenue, profit
and what moved, readable by a user with sales="none". Two occurrences of the
same omission is a fact about the default, not about the author.

So this test enumerates rather than samples: it fails when a nav section has no
feature, or a screen-serving path has no feature area.

THE DOOR. Hiding the nav item was never the whole job. Every screen has a real
address (/w/<workspace>/<section>), and the bookmark bar, the Back button and
any sent link all reach navTo() without consulting the sidebar. The server
refused the DATA all along, so nothing was exposed by that -- but the screen
opened and then failed, which reads as a broken app rather than as "no".
"""
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
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


USERS_JS = read("static", "js", "users.js")
SHELL_JS = read("static", "js", "shell.js")
GUARD = read("auth", "guard.py")

from auth import users as U
from auth import guard as G

# ===================================================================
print("== the per-page vocabulary is complete and grouped ==")
truthy("there are per-page features, not just areas", len(U.FEATURES) >= 17)
for page in ("orders", "returns", "traffic", "hourly", "finance", "aiusage",
             "generate", "repricer", "variations", "sellerimport"):
    truthy("  %-12s is its own feature" % page, page in U.FEATURES)
check("three levels, no more", list(U.LEVELS), ["none", "view", "edit"])
# Grouping is what makes seventeen rows readable rather than a wall.
grouped = [f for _t, feats in U.FEATURE_GROUPS for f in feats]
missing_from_groups = sorted(set(U.FEATURES) - set(grouped))
check("every feature appears in a group", missing_from_groups, [])
check("  and no group lists one that does not exist",
      sorted(set(grouped) - set(U.FEATURES)), [])

print("\n== a page inherits its area until it is set individually ==")
# This is what let the per-page features be added to a live app without moving
# anybody's access.
for page, area in U.FEATURE_PARENT.items():
    truthy("  %-12s falls back to %s" % (page, area), area in U.FEATURES)
lister = {"role": "lister", "active": True, "features": {}}
check("a lister with sales=none cannot see orders either",
      U.feature_level({**lister, "features": {"sales": "none"}}, "orders"), "none")
check("  but can be given it back on its own",
      U.feature_level({**lister, "features": {"sales": "none", "orders": "view"}},
                      "orders"), "view")

# ===================================================================
print("\n== EVERY nav section maps to a feature ==")
# The map is the only thing that hides a screen. A section missing from it is
# never hidden and nothing reports that at the time.
secs = set(re.findall(r'data-sec="([a-z_]+)"', read("templates", "dashboard.html")))
m = re.search(r"const SECTION_FEATURE\s*=\s*\{(.*?)\n\};", USERS_JS, re.S)
truthy("SECTION_FEATURE is readable", bool(m))
mapped = set(re.findall(r"(\w+)\s*:\s*\"", m.group(1))) if m else set()
unmapped = sorted(s for s in secs if s not in mapped)
if unmapped:
    print("    unmapped sections:", unmapped)
check("no nav section is left ungoverned", unmapped, [])

print("\n== and the screens that show money are on the money features ==")
# THE RESOLVED FEATURE, not the literal one. Every page now names ITSELF and
# inherits its area (auth/users.py FEATURE_PARENT), so `brief: "sales"` became
# `brief: "brief"` with brief's parent being sales. What matters has not
# changed and is what is asserted: follow the chain and it has to END at the
# money feature, so a user with sales="none" still cannot open it.
from auth import users as _AU


def _root(sec):
    """The area a section ultimately answers to, following parents."""
    m2 = re.search(r'\b%s\s*:\s*"(\w+)"' % sec, USERS_JS)
    f = m2.group(1) if m2 else None
    seen = set()
    while f and f in _AU.FEATURE_PARENT and f not in seen:
        seen.add(f)
        f = _AU.FEATURE_PARENT[f]
    return f


for sec, feat in (("brief", "sales"), ("leading", "sales"),
                  ("orders", "sales"), ("finance", "sales")):
    got = _root(sec)
    check("  %-9s answers to %s" % (sec, feat), got, feat)
# And each of them can now be set on its own, which is the point of the change.
for sec in ("brief", "leading", "orders", "finance", "returns"):
    m2 = re.search(r'\b%s\s*:\s*"(\w+)"' % sec, USERS_JS)
    check("  %-9s has a switch of its own" % sec,
          (m2.group(1) if m2 else None), sec)

print("\n== the server governs them too, not just the browser ==")
# feature_for() returning None means RULES alone decides, and RULES defaults to
# "any user who may edit".
for path in ("/brief", "/leading", "/orders", "/finance",
             "/traffic", "/hourly", "/aiusage", "/sourcing", "/variations"):
    got = G.feature_for(path)
    truthy("  %-12s has a feature area (%s)" % (path, got), bool(got))
check("/brief is governed as sales", G.feature_for("/brief"), "sales")
truthy("and the repeat omission is recorded where it happened",
       "the same omission is a fact about the default" in GUARD
       or "second time a new screen has shipped ungoverned" in GUARD)

print("\n== a screen you may not see does not open ==")
truthy("there is a door check", "function maySeeSection(" in USERS_JS)
truthy("  and navTo uses it", "!maySeeSection(sec)" in SHELL_JS)
truthy("  refusing before it changes the screen",
       SHELL_JS.index("maySeeSection(sec)") < SHELL_JS.index('CUR_SEC=sec'))
truthy("  and saying so rather than failing silently",
       "do not have access to that page" in SHELL_JS)
# Failing OPEN on an unmapped section: a mapping mistake must not lock somebody
# out of a working screen, which is why the coverage test above exists instead.
truthy("an unmapped section is allowed, not banned",
       "unmapped -> not a ban" in USERS_JS)
truthy("  and so is a user whose permissions have not loaded",
       "before /users/me lands" in USERS_JS)

print("\n== and the browser is still not the security boundary ==")
truthy("that is stated where the hiding happens",
       "Nothing here is a security boundary" in USERS_JS)
truthy("  and on the permissions page", "refusing the request is the security"
       in read("static", "js", "permissions.js"))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
