"""Permissions can be set per PAGE, and adding that changed nobody's access.

"i want you to ... give me an option to appoint the permissions to each user by
 page because we have features of the apps available per page also"

The app already had a two-axis model: an ACTION permission ("may they submit?")
and a FEATURE level ("may they see this area at all?"). The feature axis had
seven areas, and roughly nineteen pages rode on them -- Orders, Finance,
Returns, Traffic, Hourly and AI spend were all "sales"; the Repricer,
Variations, Import seller and Generate were all "listings".

So the finer features are members of the SAME system, not a second one.

The property that makes it safe to add to a live app with real users on it is
INHERITANCE. An unset page falls back to its area. If it defaulted to "view"
like any other unknown feature, then merely adding `orders` would have handed
the Orders screen -- individual revenue, order by order -- to every lister, who
is deliberately given sales="none".
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from auth import users as U
from auth import guard as G

LISTER = {"active": True, "role": "lister", "features": {}}
MANAGER = {"active": True, "role": "manager", "features": {}}


print("=== every page is nameable ===")
for f in ("generate", "repricer", "variations", "sellerimport", "orders",
          "returns", "traffic", "hourly", "finance", "aiusage"):
    truthy("  " + f.ljust(14) + " is a feature", f in U.FEATURES)
    truthy("    and has a parent area", f in U.FEATURE_PARENT)
truthy("the settings screen has an order to show them in", bool(U.FEATURE_GROUPS))
_listed = {f for _, fs in U.FEATURE_GROUPS for f in fs}
check("  and it covers every feature, so none is unreachable",
      sorted(set(U.FEATURES) - _listed), [])


print("\n=== NOBODY'S ACCESS CHANGED (the whole point) ===")
# A lister has sales="none" by role. Every page under sales must stay none.
for f in ("orders", "finance", "returns", "traffic", "hourly", "aiusage"):
    check("a lister still cannot see %s" % f, U.feature_level(LISTER, f), "none")
# ...and every page under listings must stay at the listings level.
for f in ("generate", "repricer", "variations", "sellerimport"):
    check("a lister keeps %s at their listings level" % f,
          U.feature_level(LISTER, f), U.feature_level(LISTER, "listings"))
check("a manager sees orders at their sales level",
      U.feature_level(MANAGER, "orders"), U.feature_level(MANAGER, "sales"))
check("  which is view, not edit", U.feature_level(MANAGER, "orders"), "view")


print("\n=== and a page can now be set on its own ===")
u = {"active": True, "role": "lister", "features": {"orders": "view"}}
check("a lister can be given orders alone", U.feature_level(u, "orders"), "view")
check("  without being given the rest of sales", U.feature_level(u, "sales"), "none")
check("  or finance", U.feature_level(u, "finance"), "none")
u2 = {"active": True, "role": "manager", "features": {"repricer": "none"}}
check("a manager can be denied the repricer alone",
      U.feature_level(u2, "repricer"), "none")
check("  while keeping listings", U.feature_level(u2, "listings"), "edit")


print("\n=== the server enforces it, per page ===")
# Hiding a button in the browser is not security -- the check is on the request.
for path, feat in (("/orders/list", "orders"), ("/returns/x", "returns"),
                   ("/traffic/y", "traffic"), ("/hourly/z", "hourly"),
                   ("/finance/a", "finance"), ("/aiusage/b", "aiusage"),
                   ("/sourcing/list", "repricer"), ("/variations/x", "variations"),
                   ("/variant/plan", "variations"), ("/seller/find", "sellerimport"),
                   ("/run/generate", "generate"), ("/input/add", "generate"),
                   ("/preview/jobs", "generate")):
    check("  %-16s -> %s" % (path, feat), G.feature_for(path), feat)
check("  /sales/summary still maps to sales", G.feature_for("/sales/summary"), "sales")
check("  /rows still maps to listings", G.feature_for("/rows"), "listings")

# The finer entries have to be BEFORE the broader ones or they never match.
_paths = [p for p, _ in G.FEATURE_PATHS]
truthy("the page entries come before the area they sit under",
       _paths.index("/orders") < _paths.index("/sales")
       or "/sales" not in _paths)

print("\n=== a page set to none is refused, not merely hidden ===")
denied = {"active": True, "role": "manager", "features": {"orders": "none"}}
ok, msg = G.check("/orders/list", "GET", denied)
check("refused", ok, False)
truthy("  and says which area", "Orders" in msg or "orders" in msg.lower())
ok2, _ = G.check("/sales/summary", "GET", denied)
check("  while the rest of sales still works", ok2, True)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
