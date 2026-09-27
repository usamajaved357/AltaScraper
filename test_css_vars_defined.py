"""Every CSS variable used without a fallback is defined somewhere.

`color: var(--fg2)` with --fg2 defined nowhere is not an error the browser
reports: the declaration is silently dropped and the element takes its
parent's colour. Four of these were found and defined over time (--fg, --text,
--bd, --card); --fg2 was the fifth, on the bookmark bar (master audit section
13; Milestone 8, 28 Sep 2026). `var(--x, fallback)` is fine and not checked.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _files():
    for sub, ext in (("static/css", ".css"), ("templates", ".html"), ("static/js", ".js")):
        d = os.path.join(HERE, *sub.split("/"))
        for f in sorted(os.listdir(d)):
            if f.endswith(ext):
                yield os.path.join(d, f)


defined, used = set(), {}
for fp in _files():
    src = open(fp, encoding="utf-8", errors="replace").read()
    defined.update(re.findall(r"(--[a-zA-Z0-9-]+)\s*:", src))
    # also variables set from JS: el.style.setProperty("--x", ...)
    defined.update(re.findall(r"setProperty\(\s*['\"](--[a-zA-Z0-9-]+)", src))
    for v in re.findall(r"var\(\s*(--[a-zA-Z0-9-]+)\s*\)", src):
        used.setdefault(v, os.path.relpath(fp, HERE))

missing = sorted(v for v in used if v not in defined)
for v in missing:
    print("  %-20s used (no fallback) in %s, defined nowhere" % (v, used[v]))
print("%d variable(s) used without a fallback and never defined" % len(missing))
print("FAILURES: %d" % len(missing))
sys.exit(1 if missing else 0)
