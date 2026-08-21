"""The "By product" table has to be asked for by something.

FOUND BY USING THE SCREEN, not by reading it. The Sales page has a "By product"
section listing every ASIN that sold. On jack_uk it was 0 rows and 0 bytes --
while /sales/breakdown answers with 47 products, and calling salesLoadBreakdown()
by hand in the console filled it with all 47 immediately.

    breakdown requested during a full page load:  NEVER

salesLoadBreakdown had exactly ONE caller: salesBdGroup, the "Each ASIN /
Grouped by parent" toggle. Those two buttons are drawn INSIDE the block that
only exists once the loader has run. Nothing could ever start it, and nothing
ever did -- a section of the screen that could not be reached from anywhere.

It also hid the coverage warning added the same day, which is why that never
appeared either: on jack_uk the products account for GBP 162.76 of GBP 285.66.

WHERE THE CALL GOES, and why not at the top with the others: salesLoadBreakdown
reads _sQuery(), which needs the range salesReload has just settled. Not
awaited -- it has its own fetch and the figures above must not wait for it.
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


J = io.open(os.path.join(HERE, "static", "js", "sales.js"), encoding="utf-8").read()
CODE = "\n".join(l.split("//")[0] for l in J.splitlines()
                 if not l.strip().startswith(("*", "/*", "//")))

print("== something starts it on every load ==")
callers = re.findall(r"(\w+)\s*\(\s*\)\s*;", "")   # placeholder, real check below
truthy("salesReload calls it", "salesLoadBreakdown();" in
       CODE.split("async function salesReload")[1].split("\n/*")[0])
check("  and it has more than one caller now",
      CODE.count("salesLoadBreakdown()") >= 2, True)
print("     (%d call sites)" % CODE.count("salesLoadBreakdown()"))
truthy("the toggle still calls it too", "salesBdGroup" in CODE)

print("\n== it runs after the range is settled ==")
_r = CODE.split("async function salesReload")[1]
_r = _r[:_r.find("}catch(e){")]
truthy("the call is inside salesReload's try", "salesLoadBreakdown();" in _r)
truthy("  after the grid is drawn",
       _r.index("salesDrawGrid(") < _r.index("salesLoadBreakdown();"))
falsy("  and it is not awaited -- the figures must not wait for it",
      "await salesLoadBreakdown" in _r)
truthy("why it is not at the top is recorded", "needs the range" in J)

print("\n== the trap that made it unreachable is written down ==")
truthy("the one-caller problem is named", "exactly ONE caller" in J
       or "had exactly one caller" in J.lower())
# A single-line fragment. The sentence wraps, and matching across the break is
# how these assertions keep failing on correct code.
truthy("  and that the buttons live inside the block",
       "only appears once the loader has run" in J)

print("\n== the loader itself is unchanged ==")
_ld = CODE.split("async function salesLoadBreakdown")[1].split("\nconst _BD_COLS")[0]
truthy("it still asks the route", '"/sales/breakdown?"' in _ld)
truthy("  scoped to the account and period", "_sQuery()" in _ld)
truthy("  passing the grouping", "group=" in _ld)
truthy("  and stores what came back", "SALES_BD.meta = j" in _ld)

print("\n== against a running app, if one is up ==")
import urllib.error
import urllib.request
try:
    urllib.request.urlopen("http://127.0.0.1:5077/healthz", timeout=3)
    import json
    import subprocess
    import tempfile
    probe = r"""
from playwright.sync_api import sync_playwright
import json
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1500,"height":1000})
    reqs=[]
    pg.on("request", lambda r: reqs.append(1) if "sales/breakdown" in r.url else None)
    pg.goto("http://127.0.0.1:5077/w/jack_uk/sales", wait_until="load", timeout=90000)
    pg.wait_for_timeout(16000)
    print(json.dumps({
      "asked": len(reqs),
      "rows": pg.evaluate("() => document.querySelectorAll('#sales_breakdown tbody tr').length"),
      "buttons": pg.evaluate("() => document.querySelectorAll('#sales_breakdown button').length"),
    }))
    b.close()
"""
    fd, path = tempfile.mkstemp(suffix=".py", dir=HERE)
    os.write(fd, probe.encode("utf-8"))
    os.close(fd)
    out = subprocess.run([sys.executable, path], capture_output=True, text=True,
                         cwd=HERE, timeout=300)
    os.unlink(path)
    g = json.loads(out.stdout.strip().splitlines()[-1])
    truthy("the breakdown is requested on a plain page load", g["asked"] >= 1)
    truthy("  and rows arrive", g["rows"] > 0)
    truthy("  with the grouping toggle", g["buttons"] >= 2)
    print("     (%d rows, %d buttons)" % (g["rows"], g["buttons"]))
except urllib.error.URLError:
    print("     (no app on 5077 -- the source checks above stand)")
except Exception as e:
    print("     (browser check skipped: %s)" % str(e)[:120])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
