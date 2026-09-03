"""The menu is an overlay at every width, and there is only one of it.

    "The app's left sidebar is causing the listings table to shrink and resize.
     On Amazon, the sidebar opens as an overlay/drawer on TOP of the page -- it
     does NOT push the content."
    "i want sidebar overlay"

WHAT WAS ALREADY THERE. The app had two menus, not one: a DESKTOP fold that
shrank the sidebar to a 44px rail and left the content narrower, and a PHONE
drawer -- fixed, off-canvas, scrim, escape-to-close, closes when you pick a
destination -- built into mobilenav.js and mobile.css and fenced inside
@media (max-width: 860px).

Everything the request describes was therefore already written and in use, on
phones. So the drawer rules were lifted out of the media query rather than a
second overlay being written beside them: one implementation, one scrim, one
piece of state (CLAUDE.md Rule 12). What stays behind the breakpoint is what is
genuinely about a small screen -- the no-sideways-scroll guards, the stacked
toolbars, the touch target sizes.

THE PAGE NEVER MOVES, which is the whole of the ask: the sidebar is out of flow
at every width, so the content is full width whether the menu is open or shut.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


CSS = open(os.path.join(HERE, "static", "css", "mobile.css"), encoding="utf-8").read()
MNAV = open(os.path.join(HERE, "static", "js", "mobilenav.js"), encoding="utf-8").read()
SIDE = open(os.path.join(HERE, "static", "js", "sidebar.js"), encoding="utf-8").read()

# Everything before the first @media is what applies at EVERY width.
GLOBAL = CSS.split("@media")[0]

print("=== the drawer applies at every width ===")
truthy("the sidebar is fixed and off-canvas globally",
       "#workspace .sidebar{" in GLOBAL
       and "position:fixed" in GLOBAL.split("#workspace .sidebar{")[1].split("}")[0]
       and "translateX(-100%)" in GLOBAL.split("#workspace .sidebar{")[1].split("}")[0])
truthy("  and slides in when the menu is open",
       "body.navopen #workspace .sidebar{" in GLOBAL)
truthy("the button that opens it is drawn at every width",
       "display:flex" in GLOBAL.split("#navburger{")[1].split("}")[0])
falsy("  it is no longer hidden above the breakpoint",
      re.search(r"#navburger\{\s*display:none", GLOBAL) is not None)
truthy("the scrim is drawn at every width",
       "display:block" in GLOBAL.split(".navscrim{")[1].split("}")[0])

print("\n=== the page underneath never moves ===")
# Fixed means out of flow: the content cannot be pushed or resized by it.
truthy("the sidebar takes no width from the layout",
       "position:fixed" in GLOBAL.split("#workspace .sidebar{")[1].split("}")[0])
truthy("  and the old 44px fold cannot shrink it back",
       "#workspace.navmini .sidebar{" in GLOBAL)
truthy("the page behind cannot scroll while it is open",
       "body.navopen{ overflow:hidden; }" in GLOBAL)

print("\n=== one menu, one state ===")
truthy("the in-drawer button drives the drawer", "mnavToggle()" in SIDE)
truthy("  and says why the old fold is finished",
       "nothing left to fold" in SIDE)
truthy("  with the old path kept only for mobilenav.js being absent",
       'typeof mnavToggle === "function"' in SIDE)
falsy("choosing a destination no longer only closes it on a phone",
      "if(!mnavIsPhone() || !mnavIsOpen()) return;" in MNAV)
truthy("  it closes whenever the menu is open", "if(!mnavIsOpen()) return;" in MNAV)
falsy("the breakpoint watcher that force-closed it is gone",
      "addEventListener(\"change\", function(e){ if(!e.matches) mnavClose(); })" in MNAV)
# One line of it: the sentence wraps, and matching across the break finds a
# newline rather than the words.
truthy("  and says why it could go", "The drawer never stops" in MNAV)

print("\n=== what stays behind the breakpoint ===")
PHONE = CSS[CSS.find("@media"):]
truthy("the phone-only layout guards are still there",
       "overflow-x:hidden" in PHONE)
truthy("MNAV_BREAKPOINT is still used by the phone checks",
       "MNAV_BREAKPOINT" in MNAV and "function mnavIsPhone(" in MNAV)

print("\n=== nothing is left half-written ===")
check("the stylesheet's braces balance", CSS.count("{"), CSS.count("}"))

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
