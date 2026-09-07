# Which controls LOOK like they change something on Amazon, and which actually do.
#
#     "also see other buttons which seems like calling amazon but donot call
#      amazon for a change"
#
# The test: for every route the browser posts to, does the server-side code for
# that route reach an Amazon WRITE? The write verbs on the SP-API clients are
# few and named, so this can be answered by reading rather than guessing.
#
# Read-only. It prints a table; it changes nothing.
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# Every way the app can CHANGE something at Amazon. Anything else -- get_*,
# search_*, a report, a catalogue read -- only looks.
WRITE_CALLS = (
    "put_listings_item", "patch_listings_item", "delete_listings_item",
    "_al.put(", "_al.patch(", "amazon_listings.put(", "amazon_listings.patch(",
    "push_handling_time", "push_quantity", "_patch_fulfillment",
    "create_report",          # not a listing change, but it does spend quota
    "put_ads", "update_campaigns", "update_ad_groups", "update_keywords",
)
LISTING_WRITES = WRITE_CALLS[:9]

# The controls the owner actually presses, and the route each one posts to.
# Taken from the templates and the js, then checked against the routes below.
BUTTONS = []
js_dir = os.path.join(HERE, "static", "js")
for fn in sorted(os.listdir(js_dir)):
    if not fn.endswith(".js"):
        continue
    src = open(os.path.join(js_dir, fn), encoding="utf-8", errors="replace").read()
    for m in re.finditer(r'fetch\(\s*(?:acctUrl\()?["\'](/[A-Za-z0-9_/<>-]+)', src):
        BUTTONS.append((fn, m.group(1)))

routes_dir = os.path.join(HERE, "routes")
route_src = {}
for fn in sorted(os.listdir(routes_dir)):
    if fn.endswith(".py"):
        route_src[fn] = open(os.path.join(routes_dir, fn), encoding="utf-8",
                             errors="replace").read()
route_src["dashboard.py"] = open(os.path.join(HERE, "dashboard.py"),
                                 encoding="utf-8", errors="replace").read()


def body_of(path):
    """The source of the handler for a route path, across all route modules."""
    pat = re.compile(r'@app\.route\(\s*["\']' + re.escape(path) + r'["\']')
    for fn, src in route_src.items():
        m = pat.search(src)
        if not m:
            continue
        rest = src[m.end():]
        nxt = rest.find("\n    @app.route(")
        return fn, (rest if nxt < 0 else rest[:nxt])
    return None, ""


seen = {}
for fn, path in BUTTONS:
    if path in seen:
        seen[path][0].add(fn)
        continue
    where, body = body_of(path)
    if not where:
        continue
    writes = sorted({w for w in LISTING_WRITES if w in body})
    # A route that hands off to a background run (the generator) does write.
    spawns = ("preview_jobs" in body or "run_command" in body
              or '"api", "submit"' in body or "api_submit" in body)
    seen[path] = ({fn}, where, writes, spawns)

print("%-34s %-26s %s" % ("ROUTE", "HANDLER", "CHANGES AMAZON?"))
print("-" * 92)
quiet, loud = [], []
for path in sorted(seen):
    callers, where, writes, spawns = seen[path]
    if writes:
        verdict = "YES -- " + ", ".join(w.strip("_(") for w in writes)[:44]
        loud.append(path)
    elif spawns:
        verdict = "YES -- via the generator subprocess"
        loud.append(path)
    else:
        verdict = "no -- local only"
        quiet.append(path)
    print("%-34s %-26s %s" % (path[:34], where[:26], verdict))

print("\n%d route(s) change something on Amazon" % len(loud))
print("%d route(s) are local only" % len(quiet))
print("\nLOCAL-ONLY ROUTES THE BROWSER POSTS TO (check the wording on each):")
for p in quiet:
    print("  %-32s called from %s" % (p, ", ".join(sorted(seen[p][0]))[:60]))
