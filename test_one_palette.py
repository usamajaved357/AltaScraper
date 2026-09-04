"""One palette. No screen invents a colour of its own.

    VISUAL_CONSISTENCY_AUDIT.md, step 4:
      "No hardcoded hex colors in any JS file"

Before this there were 298 of them across 34 files: eighty-odd distinct greens,
ambers, reds and blue-greys, each a slightly different shade of the same idea,
so the inventory page's "ACTIVE" green and the listings page's "LIVE" green
were not the same green. They are now, because both read --ok.

WHY THE PROPERTY MATTERS AND NOT JUST THE COLOUR
The same amber is a tint behind a badge and the text on it. Those are two
variables, --warn-bg and --warn, and a mapping that went by hex alone put a
border colour behind a badge. This checks the pairs are used as pairs.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(ROOT, "static", "js")
CSS = os.path.join(ROOT, "static", "css")
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                          % (got, want)))


def read(p):
    with open(p, encoding="utf-8-sig") as f:
        return f.read()


def code(src):
    """Comments stripped. A note recording an old hex value is history, not a
    colour anything renders -- and the two must not be confused, which is how a
    line-comment pattern under DOTALL once swallowed a whole file."""
    src = re.sub(r"(?s:/\*.*?\*/)", "", src)
    return re.sub(r"(?m:^[ \t]*//[^\n]*)", "", src)


# The same pattern that found them: a colour ANYWHERE in one of these
# declarations, not only as the first word ("border:1px solid #2a7a2a").
DECL = re.compile(
    r"\b(color|background|background-color|border|border-color|border-top|"
    r"border-bottom|border-left|border-right|outline|fill|stroke|box-shadow)"
    r"(\s*:\s*)([^;\"'`}]*?)(#[0-9a-fA-F]{3,8})")

print("== no JavaScript file names a colour ==")
offenders = {}
for f in sorted(os.listdir(JS)):
    if not f.endswith(".js"):
        continue
    hits = DECL.findall(code(read(os.path.join(JS, f))))
    if hits:
        offenders[f] = len(hits)
check("hardcoded colours in static/js", offenders, {})

print("\n== the palette a screen is allowed to use ==")
dash = read(os.path.join(CSS, "dashboard.css"))
root = dash[dash.index(":root{"):dash.index("}", dash.index(":root{"))]
for v in ("--ok", "--ok-bg", "--ok-line", "--warn", "--warn-bg", "--warn-line",
          "--red", "--red-bg", "--red-line", "--gold", "--gold-bg", "--gold-line",
          "--accent", "--accent-bg", "--accent-line", "--ai", "--ai-bg",
          "--ai-line", "--ink", "--ink2", "--ink3", "--panel", "--panel2",
          "--panel3", "--sidebar", "--line", "--line2", "--paper"):
    check("  %s is defined" % v, ("%s:" % v) in root, True)

print("\n== every variable a screen uses actually exists ==")
# A var() naming something undefined does not error -- the browser drops the
# declaration and the element renders with no colour at all, which is the
# failure mode --fg and --text had before they were defined. #ffffff was written
# in seven files and --paper was only in login.css, so this is not theoretical.
defined = set()
for f in sorted(os.listdir(CSS)):
    if f.endswith(".css"):
        for m in re.finditer(r"(--[a-z0-9-]+)\s*:", read(os.path.join(CSS, f))):
            defined.add(m.group(1))
used = set()
for f in sorted(os.listdir(JS)):
    if f.endswith(".js"):
        for m in re.finditer(r"var\((--[a-z0-9-]+)", code(read(os.path.join(JS, f)))):
            used.add(m.group(1))
check("variables used in JS but defined nowhere", sorted(used - defined), [])

print("\n== the pairs are used as pairs ==")
# A background and the text on it come from the same family. Spot-checked on
# the badge rows the first, hex-only mapping got wrong.
inv = code(read(os.path.join(JS, "inventory.js")))
for bgv, fgv, line in (("--ok-bg", "--ok", "--ok-line"),
                       ("--red-bg", "--red", "--red-line")):
    pat = (r"background:var\(%s\);color:var\(%s\);border:1px solid var\(%s\)"
           % (bgv, fgv, line))
    check("  %s / %s / %s appear together" % (bgv, fgv, line),
          re.search(pat, inv) is not None, True)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
