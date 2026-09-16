# -*- coding: utf-8 -*-
"""The AI image generator is on the product page's Images tab, and it starts.

    "do you remember how we had the image generation built inside the pdp?? i
     want that option again"

It had not been deleted: _fullDataParts still built it, but the product page
drew it only as a fold at the bottom of Safety & Compliance, and nothing on the
page called initGenPanel -- so its model pickers were empty and its connection
check never ran. Only the old drawer started it.
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(name, got, want):
    if got == want:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s   got=%r want=%r" % (name, got, want))
        FAILS.append(name)


def read(p):
    return open(os.path.join(HERE, *p.split("/")), encoding="utf-8").read()


PDP = read("static/js/pdp.js")
AF = read("static/js/autofix.js")

print("== the parts ==")
check("the generator is handed out on its own", "gen: genBlock" in AF, True)
check("  and the tools without it", "toolsNoGen: _vf.mirror + _otherTools" in AF, True)
check("the drawer still gets the generator in its fold run",
      "const toolFolds = _vf.mirror + _genFold + _otherTools;" in AF, True)

print("\n== the product page ==")
images = PDP[PDP.find('PDP_TAB === "images"'):PDP.find('PDP_TAB === "variations"')]
check("the Images tab draws the generator", "pdpGenSection(p.gen)" in images, True)
other = PDP[PDP.find('PDP_TAB === "offer"'):]
other = other[:other.find("host.innerHTML")]
check("Safety & Compliance no longer carries it",
      "p.toolsNoGen != null ? p.toolsNoGen : p.tools" in other, True)
after = PDP[PDP.find("pdpWatchEdits();"):]
after = after[:after.find("}, 40);")]
check("the page starts it once drawn (model pickers + connection check)",
      bool(re.search(r'PDP_TAB === "images".*initGenPanel\(sid\(r\.sku\)\)', after, re.S)), True)
check("  through the drawer's own starter, not a copy",
      len(re.findall(r"function initGenPanel\(", read("static/js/listings.js") + PDP + AF)), 1)

node = shutil.which("node")
if not node:
    FAILS.append("node")
    print("  FAIL  node not found")
else:
    start = PDP.find("function pdpGenSection(")
    end = PDP.find("\n}\n", start) + 3
    js = PDP[start:end] + '\nconsole.log(pdpGenSection("<div id=\\"genpanel_x\\">PANEL</div>"));\n'
    p = subprocess.run([node, "-e", js], capture_output=True, text=True)
    out = p.stdout
    check("the section wraps the panel it is given", 'id="genpanel_x">PANEL' in out, True)
    check("  under a heading that says what it is", "Generate an image with AI" in out, True)

print()
if FAILS:
    print("FAILED: %d" % len(FAILS))
    sys.exit(1)
print("all passed")
