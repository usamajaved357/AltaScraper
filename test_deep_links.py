"""Every screen in the menu can be refreshed, bookmarked and opened in a tab.

MEASURED 21 Aug 2026 by asking the running app for all forty section addresses:

    served   12   listings, imagerefs, setup, generate, sales, traffic, hourly,
                  ppc, inventory, sync, monitor, miles
    refused  28   weekly, daily, orders, returns, variations, sellerimport,
                  sourcing, finance, aiusage, imagestudio, imagelib, trackers,
                  alerts, leading, notify, sqp, catalog, compliance, categories,
                  drppc, permissions, reimbursements, brief, kwspy, kwasin,
                  ranktracker, kwhistory, asinstudio

routes/ui_routes.py held a hand-typed tuple of twelve, written when there were
twelve. The app grew to forty and the tuple did not, so refreshing Orders,
Finance, Weekly, the Product Catalog or any of the newer screens answered with a
plain-text "Unknown section" and a blank app -- as did every bookmark, and the
bookmark bar exists to make exactly those links.

TWO LISTS OF "WHAT SCREENS EXIST" DRIFT, AND THESE DID. The menu is the one
definition now: data-sec in templates/dashboard.html, which is also what the
Ctrl+K palette reads (rule 12). A section added to the menu is deep-linkable the
same day, with no second place to remember.

AND IT IS STILL NOT A CATCH-ALL. A path that is not a section is still an honest
404 -- a catch-all would answer a mistyped API path with the dashboard's HTML,
which turns a one-line typo into an hour of debugging.
"""
import io
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
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


U = read("routes", "ui_routes.py")
H = read("templates", "dashboard.html")
SH = read("static", "js", "shell.js")

print("== the server reads the menu rather than keeping its own list ==")
falsy("the hand-typed tuple is gone",
      '_SECTIONS = ("listings", "imagerefs", "setup", "generate"' in U)
truthy("sections come from data-sec in the template",
       r'data-sec="([\w-]+)"' in U)
truthy("  cached on the template's modification time", "getmtime" in U)
truthy("  so a local edit takes effect without a restart",
       "without a restart" in U)
truthy("an unreadable template still serves something",
       'found or ("listings",)' in U)
truthy("it is still not a catch-all", "Unknown section" in U)

print("\n== the menu and the browser's own list agree ==")
menu = list(dict.fromkeys(re.findall(r'data-sec="([\w-]+)"', H)))
m = re.search(r"ALTA_SECTIONS\s*=\s*\[(.*?)\]", SH, re.S)
js = list(dict.fromkeys(re.findall(r'"([\w-]+)"', m.group(1)))) if m else []
print("     menu: %d sections, ALTA_SECTIONS: %d" % (len(menu), len(js)))
truthy("the menu has every screen", len(menu) >= 40)
check("nothing is in the browser's list but missing from the menu",
      sorted(set(js) - set(menu)), [])
check("  nor the other way round", sorted(set(menu) - set(js)), [])

print("\n== the deleted Business overview is in neither ==")
falsy("not in the menu", "overview" in menu)
falsy("  not in ALTA_SECTIONS", "overview" in js)
falsy("  and its screen is gone", 'id="sec_overview"' in H)
falsy("  and its script tag with it", "overview.js" in H)
falsy("  the module is deleted",
      os.path.exists(os.path.join(HERE, "routes", "overview_routes.py")))
falsy("  and so is the browser file",
      os.path.exists(os.path.join(HERE, "static", "js", "overview.js")))
falsy("  nothing registers it", "_overview_routes.register" in read("dashboard.py"))
falsy("  it has no permission entry",
      re.search(r"\boverview\s*:", read("static", "js", "users.js")) is not None)
falsy("  and no row in the guard's feature table",
      '("/overview"' in read("auth", "guard.py"))
truthy("  why it went is recorded", "why am i watching this in jack" in read("dashboard.py"))

print("\n== against the running app, if one is up ==")
import urllib.error
import urllib.request
BASE = "http://127.0.0.1:5077"
try:
    urllib.request.urlopen(BASE + "/healthz", timeout=3)
    served, refused = [], []
    for s in menu:
        try:
            with urllib.request.urlopen(BASE + "/w/jack_uk/" + s, timeout=30) as r:
                (served if r.status == 200 else refused).append(s)
        except urllib.error.HTTPError:
            refused.append(s)
    check("every section in the menu is served", refused, [])
    print("     (%d served)" % len(served))
    # And something that is NOT a section must still be refused.
    for bad in ("nonsense", "rows", "overview"):
        code = 0
        try:
            with urllib.request.urlopen(BASE + "/w/jack_uk/" + bad, timeout=30) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        check("  %-9s is still an honest 404" % bad, code, 404)
except Exception:
    print("     (no app running on 5077 -- the checks above stand on their own)")

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
