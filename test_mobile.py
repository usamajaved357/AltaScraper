"""The phone layout, checked against what Orbit actually does.

WHAT WAS WRONG

    "the app in the mobile version is moving freely the texts are going out of
     the boxes no lines no arrangements, everything is distorted and moving
     freely where is descipline ... i want you to match the mobile version of
     the orbit view as mine, see how the side bar appear and everything else."

WHERE THE NUMBERS IN THIS FILE COME FROM

Orbit was opened at 390x844 and measured, rather than described from memory.
Three pages (Inventory, PPC, Sales) all reported the same shape:

    sidebar          x:-300, width 284      -- parked off the screen, a drawer
    the control      one 40x40 button at (16, 8), aria-label "Open menu"
    cards            grid-template-columns: "289px"  -- ONE column
    a wide table     1539px, inside a parent with overflow-x:auto
    the page         document.scrollWidth == 390 == the viewport

That last line is the complaint restated as a measurement. If ONE element is
wider than the screen then the page itself scrolls sideways, every fixed thing
slides out of position as you scroll, and the result reads exactly as
"everything is moving freely". It is a layout fault, not a matter of taste.

WHAT THIS TEST IS FOR

Not to re-check that CSS parses -- to pin the four decisions that were made
from those measurements, so that a later change cannot quietly undo one:

  1. the sidebar is a DRAWER, and the old horizontal nav strip is really gone
     rather than left behind to fight it
  2. the breakpoint in the JavaScript equals the breakpoint in the CSS
  3. the drawer state cannot survive the drawer disappearing
  4. wide tables scroll inside their own box instead of being clipped
"""
import re
import sys

CSS = r"D:\AltaScraper\static\css\mobile.css"
BASE_CSS = r"D:\AltaScraper\static\css\dashboard.css"
JS = r"D:\AltaScraper\static\js\mobilenav.js"
HTML = r"D:\AltaScraper\templates\dashboard.html"

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def read(p):
    return open(p, encoding="utf-8-sig").read()


css = read(CSS)
base = read(BASE_CSS)
js = read(JS)
html = read(HTML)

# Comments in these files quote the bug and name the very selectors under test,
# so reading them as code makes a test pass on its own documentation. That has
# already happened three times in this suite.
def strip_css_comments(s):
    return re.sub(r"/\*[\s\S]*?\*/", "", s)


def strip_js_comments(s):
    s = re.sub(r"/\*[\s\S]*?\*/", "", s)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in s.split("\n"))


CSSC = strip_css_comments(css)
BASEC = strip_css_comments(base)
JSC = strip_js_comments(js)
HTMLC = re.sub(r"<!--[\s\S]*?-->", "", html)


print("\n== the page itself never scrolls sideways (Orbit: scrollWidth == 390) ==")
truthy("the page is clipped horizontally on a phone",
       re.search(r"html,\s*body\s*\{[^}]*overflow-x\s*:\s*hidden", CSSC))
truthy("images cannot exceed their box",
       re.search(r"img\s*\{[^}]*max-width\s*:\s*100%", CSSC))
truthy("a long unbroken word breaks instead of pushing its box wider",
       "overflow-wrap:anywhere" in CSSC.replace(" ", ""))
truthy("grid and flex children are allowed to shrink (min-width:0)",
       "min-width:0" in CSSC.replace(" ", ""))


print("\n== the sidebar is a drawer, like Orbit's ==")
truthy("it is taken out of the flow and fixed to the edge",
       re.search(r"#workspace\s+\.sidebar\s*\{[^}]*position\s*:\s*fixed", CSSC))
truthy("it is parked off the left of the screen when closed",
       re.search(r"#workspace\s+\.sidebar\s*\{[^}]*translateX\(-100%\)", CSSC))
truthy("284px wide, the width measured off Orbit",
       re.search(r"#workspace\s+\.sidebar\s*\{[^}]*width\s*:\s*284px", CSSC))
truthy("opening it is one class on <body>, so there is one place to change it",
       "body.navopen #workspace .sidebar" in CSSC)
truthy("a closed drawer is hidden, not merely off-screen (no phantom tab stop)",
       re.search(r"#workspace\s+\.sidebar\s*\{[^}]*visibility\s*:\s*hidden", CSSC))
truthy("the page behind it cannot scroll while it is open",
       re.search(r"body\.navopen\s*\{[^}]*overflow\s*:\s*hidden", CSSC))

print("\n== the old horizontal nav strip is gone, not merely overridden ==")
# Two files each holding half of one answer is how the strip ended up fighting
# everything built after it. The strip's signature was turning the sidebar into
# a row -- if that is still in the base stylesheet, both are live.
truthy("dashboard.css no longer turns the sidebar into a row",
       not re.search(r"\.sidebar\s*\{[^}]*flex-direction\s*:\s*row", BASEC))
truthy("dashboard.css no longer gives the nav an underline-style active state",
       not re.search(r"\.navitem\.active\s*\{[^}]*border-bottom-color\s*:\s*var\(--accent\)",
                     BASEC))
truthy("mobile.css is the file that owns the phone sidebar",
       ".sidebar .navitem" in CSSC)


print("\n== the control that opens it (Orbit: 40x40, aria-label 'Open menu') ==")
truthy("the button exists in the page", 'id="navburger"' in HTMLC)
truthy("it is not drawn at all on a desktop",
       re.search(r"#navburger\s*\{\s*display\s*:\s*none", CSSC))
truthy("it is 40px square, the size measured off Orbit",
       re.search(r"#navburger\s*\{[^}]*width\s*:\s*40px[^}]*height\s*:\s*40px", CSSC))
truthy("it says whether the menu is open, for a screen reader",
       'aria-expanded' in HTMLC and 'aria-expanded' in JSC)
truthy("the dimming sheet behind the drawer exists", 'class="navscrim"' in HTMLC)
truthy("tapping that sheet closes the menu",
       re.search(r"scrim\.addEventListener\(\s*[\"']click[\"']\s*,\s*mnavClose", JSC))


print("\n== the two breakpoints agree ==")
# A drawer whose JavaScript thinks the phone ends at 768 and whose CSS thinks it
# ends at 860 is broken for every width in between, and it is invisible on the
# two sizes anybody tests.
m = re.search(r"MNAV_BREAKPOINT\s*=\s*(\d+)", JSC)
truthy("the JavaScript states its breakpoint", m)
js_bp = m.group(1) if m else None
css_bps = set(re.findall(r"@media\s*\(max-width:\s*(\d+)px\)", CSSC))
check("the CSS uses the same number as the JavaScript",
      js_bp in css_bps, True)
print("       javascript=%r  css=%r" % (js_bp, sorted(css_bps)))


print("\n== the drawer cannot outlive the drawer ==")
# Rotating to landscape past the breakpoint used to leave body.navopen set,
# which on a desktop layout means overflow:hidden on the body -- a page that
# will not scroll, with nothing on screen to explain why.
truthy("growing past the breakpoint drops the open state",
       re.search(r"matchMedia[\s\S]{0,220}?if\s*\(\s*!\s*e\.matches\s*\)\s*mnavClose", JSC))
truthy("Escape closes it, like every other overlay here",
       re.search(r"Escape[\s\S]{0,80}mnavClose", JSC))
truthy("choosing a destination closes it",
       re.search(r"navitem[\s\S]{0,60}mnavClose", JSC))
# The account and marketplace pickers open their own menus INSIDE the sidebar.
# Closing the drawer on any sidebar click would shut the menu just opened.
truthy("but only for things that actually go somewhere",
       ".navitem, .backlink" in JSC)


print("\n== cards go to one column, like Orbit's 289px single column ==")
truthy("the tile grids collapse to one column",
       re.search(r"main#grid[^{]*\{[^}]*grid-template-columns\s*:\s*1fr", CSSC))
truthy("the stock cockpit cards collapse to one column",
       re.search(r"\.stk-grid\s*\{[^}]*grid-template-columns\s*:\s*1fr", CSSC))


print("\n== wide tables scroll inside their box, they are not clipped ==")
# The ledger cards are overflow:hidden so their corners stay round. On a phone
# that clips a 7-column table instead of scrolling it, and whole columns vanish
# with nothing on screen to say they exist.
truthy("the ledger cards scroll sideways on a phone",
       re.search(r"#stk_ledger[\s\S]{0,120}overflow-x\s*:\s*auto\s*!important", CSSC))
truthy("the PPC term table does too",
       re.search(r"#ppc_terms[\s\S]{0,120}overflow-x\s*:\s*auto\s*!important", CSSC))
truthy("and the table keeps a real width so there is something to scroll",
       re.search(r"\.stk-table\s*\{[^}]*min-width\s*:\s*\d\d\dpx", CSSC))


print("\n== it is actually wired into the page ==")
truthy("the stylesheet is linked", "/static/css/mobile.css" in HTMLC)
truthy("the script is loaded", "/static/js/mobilenav.js" in HTMLC)
# Several rules in mobile.css match the same elements as dashboard.css with the
# same specificity, so the later file is the one that wins. Load it first and
# the phone layout silently loses to the desktop one.
i_base = HTMLC.find("/static/css/dashboard.css")
i_mob = HTMLC.find("/static/css/mobile.css")
check("mobile.css is loaded AFTER dashboard.css",
      i_base >= 0 and i_mob > i_base, True)


print("\n== the desktop is untouched ==")
# Everything above lives inside a media query or on an element that is
# display:none until the breakpoint. Nothing may leak out.
outside = re.split(r"@media", CSSC)[0]
for banned in ("position:fixed", "translateX", "overflow:hidden"):
    check("nothing outside a media query does %r" % banned,
          banned in outside.replace(" ", ""), False)


print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
