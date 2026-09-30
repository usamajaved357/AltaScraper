"""SQL in routes/ can only shrink (architecture batch A6).

The target (docs/architecture-audit-2026-09-29.md): routes read the request and
call a domain function; the SQL lives with the feature that owns the table.
Batch A6 moved Finance, Sales, Orders and the listing edit's reads. What is left
is pinned here, per file, so a route cannot grow a new query unnoticed. When a
file's queries move, lower its number (or drop it); never raise one without
writing down why.
"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# 29 Sep 2026, after A6. Each still to move into its feature's module.
LEFT = {
    "routes/ads_routes.py": 3,
    "routes/aiusage_routes.py": 1,
    "routes/brandview_routes.py": 1,
    "routes/catalog_page_routes.py": 1,
    "routes/daily_routes.py": 4,
    "routes/drive_routes.py": 2,
    "routes/ppc_analytics_routes.py": 1,
    # 2 -> 1 (30 Sep 2026): the buyer_messages read moved to
    # domain/buyer_inbox.sent_for, shared with Customer messages.
    "routes/returns_routes.py": 1,
    "routes/sourcing_routes.py": 1,
    "routes/variations_routes.py": 2,
    "routes/weekly_routes.py": 1,
}

fails = []
for f in sorted(glob.glob("routes/*.py")):
    rel = f.replace("\\", "/")
    n = len(re.findall(r"\.execute(?:many|script)?\(", open(f, "rb").read().decode("utf-8")))
    cap = LEFT.get(rel, 0)
    if n > cap:
        fails.append("%s: %d SQL calls (allowed %d) -- put the query in the feature's "
                     "domain/data module" % (rel, n, cap))
    elif n < cap:
        print("  %s now has %d (was %d): lower LEFT" % (rel, n, cap))
        fails.append("%s: lower its LEFT entry to %d" % (rel, n))
for f in fails:
    print("  " + f)
if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("SQL in routes/: %d calls in %d files, none new" % (sum(LEFT.values()), len(LEFT)))
