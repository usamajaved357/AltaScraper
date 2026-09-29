"""The Brand panel's HTML and JS live in templates/ and static/js/, not a Python string.

Master audit A16, CLAUDE.md Rule 7. The panel is fetched from /brand/panel and
its inline <script> is run by copying its text (listings.js loadBrandPanel), so
the reply must stay ONE document with ONE inline script -- the move keeps the
reply exactly as it was, assembled from the two files.
"""
import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


spec = importlib.util.spec_from_file_location("bp", os.path.join(HERE, "dashboard_brand_patch.py"))
BP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BP)
html = BP._panel_html()

print("\n1. the reply is one document with one inline script")
check("exactly one <script> and one </script>", (html.count("<script>"), html.count("</script>")), (1, 1))
check("  and it ends with the script, as before", html.endswith("</script>\n"), True)
check("the brand form is in it", all(('id="%s"' % i) in html for i in ("b_name", "b_select", "b_markup")), True)
check("  with its accessible labels", 'aria-label="Brand name"' in html, True)
check("the script defines what the page calls", "brandInit" in html, True)

print("\n2. and it no longer lives in Python")
src = open(os.path.join(HERE, "dashboard_brand_patch.py"), encoding="utf-8").read()
check("no _PANEL_HTML string", "_PANEL_HTML" in src, False)
check("no <input ...> markup in the Python file", bool(re.search(r"<input [^>]*id=\"b_", src)), False)
check("templates/brand_panel.html exists", os.path.isfile(os.path.join(HERE, "templates", "brand_panel.html")), True)
js = os.path.join(HERE, "static", "js", "brand_panel.js")
check("static/js/brand_panel.js exists", os.path.isfile(js), True)
try:
    r = subprocess.run(["node", "--check", js], capture_output=True, text=True, timeout=60)
    check("  and it parses", r.returncode, 0)
except FileNotFoundError:
    print("  (node not found -- parse check skipped)")

print("\nFAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
