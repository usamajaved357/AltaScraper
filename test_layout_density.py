"""The density pass: more listing rows above the fold, nothing else touched.

    "A CSS/HTML/JS pass to remove wasted vertical and horizontal space on the
     listings page ... purely about removing dead space, hiding unnecessary
     elements, and making the toolbar buttons small enough to fit on one line."

The brief is explicit about what must NOT move -- "do not change any font sizes
in the app except the .mktbtn / .ghost buttons inside .wstoolbar" -- so this
guards the restraint as much as the change: the button shrink is asserted to be
SCOPED to the toolbar, and the app-wide rules are asserted unchanged.

ITEM 9 IS A BUG I SHIPPED. The sidebar became a drawer overlay in an earlier
commit, and anyone whose browser remembered the old desktop fold
(alta_navmini="1") opened the drawer to find every item hidden and the words
"Show menu" alone in it -- because dashboard.css:450 carries an id and three
classes and the override alongside the drawer carried an id and two.
"""
import io
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


def rd(p):
    return io.open(os.path.join(HERE, *p.split("/")), encoding="utf-8").read()


CSS = rd("static/css/dashboard.css")
LR = rd("static/css/listrow_detailed.css")
MOB = rd("static/css/mobile.css")
HTML = rd("templates/dashboard.html")
SW = rd("static/js/switcher.js")
SIDE = rd("static/js/sidebar.js")


def rule(css, sel):
    """The body of one rule, or "" -- so a value cannot be matched from the
    wrong block."""
    i = css.find(sel)
    return css[i + len(sel):css.find("}", i)] if i >= 0 else ""


print("=== 1. the appbar is 40px, and everything measured from it followed ===")
truthy("the appbar is tighter", "padding:6px 12px" in rule(CSS, ".appbar{"))
truthy("  with a smaller gap", "gap:8px" in rule(CSS, ".appbar{"))
# The sticky offsets are the half that gets forgotten: a 40px bar with a 49px
# offset leaves a 9px stripe of nothing under it on every screen.
falsy("no 49px offset is left behind",
      re.search(r"(top|calc\(100vh -):\s*49px", CSS) is not None
      or "100vh - 49px" in CSS)
truthy("the sidebar starts at 40px", "top:40px" in rule(CSS, ".sidebar{"))
truthy("  and so does the toolbar", "top:40px" in rule(CSS, ".wstoolbar{"))
truthy("the workspace is measured from 40px too", "100vh - 40px" in CSS)

print("\n=== the account is visible without opening the drawer ===")
truthy("the chip is in the appbar", 'id="appbar_acctswitch"' in HTML)
truthy("  it opens the existing switcher", "openAccountSwitch(event)" in HTML)
truthy("  and is styled", ".appbar .acct-switch-chip{" in CSS)
# ONE writer for both, or the header and the sidebar can name different
# companies -- on an app that shows three limited companies through one screen.
truthy("the label is written by the same function as the sidebar's",
       "appbar_acct_label" in SW
       and SW.index("appbar_acct_label") > SW.index("nav_acct_label"))
truthy("  from one value, not two lookups", "const name = a ?" in SW)

print("\n=== 2. the toolbar fits on one line ===")
truthy("it may not wrap", "flex-wrap:nowrap" in rule(CSS, ".wstoolbar{"))
truthy("  and is tighter", "padding:5px 10px" in rule(CSS, ".wstoolbar{"))
# NO SCROLLBAR: the brief is explicit, and a scrollbar hides the buttons at the
# end from anyone who does not think to drag it.
falsy("no horizontal scrollbar is added",
      re.search(r"overflow-x:\s*(auto|scroll)", rule(CSS, ".wstoolbar{"))
      is not None)
truthy("the buttons shrink", ".wstoolbar .mktbtn{" in CSS
       and "font-size:11px" in rule(CSS, ".wstoolbar .mktbtn{"))
truthy("  ghosts too", ".wstoolbar .ghost{" in CSS)
# SCOPED. The brief forbids changing button sizes anywhere else.
#
# Matched with a regex that will not settle for the SCOPED rule: a plain
# find(".mktbtn{") hits ".wstoolbar .mktbtn{" first, which is the thing being
# distinguished from.
_appwide = re.search(r"(?<!\.wstoolbar )\.mktbtn\{([^}]*)\}", CSS)
truthy("the app-wide .mktbtn keeps its own size",
       _appwide and "font-size:12px" in _appwide.group(1))
truthy("the synced label truncates instead of pushing buttons off the end",
       "text-overflow:ellipsis" in rule(CSS, ".wstoolbar #synclabel{"))
truthy("the view toggles are 22px", "width:22px" in rule(CSS, ".viewtoggle button{")
       and "height:22px" in rule(CSS, ".viewtoggle button{"))
for long_, short in (("Diagnose SP-API", "Diagnose"),
                     ("Paste listing", "Paste"),
                     ("How costs work", "How costs")):
    falsy("'%s' shortened" % long_, ("> " + long_ + "</button>") in HTML)
    truthy("  to '%s'" % short, ("> " + short + "</button>") in HTML)

print("\n=== 3 and 6. what is hidden rather than deleted ===")
# metricFilter() writes sel.value; a missing element would throw.
truthy("the status dropdown is hidden", "#statussel{display:none !important}" in CSS)
truthy("  but still in the markup", 'id="statussel"' in HTML)
truthy("the datasrc bar is hidden", "#ws_datasrc.datasrc{display:none !important}" in CSS)
truthy("the gridhow bar is hidden", "#gridhow{display:none !important}" in CSS)

print("\n=== 4. the content reaches the edges ===")
truthy("the shared gutter is 10px", "--wspad:10px" in CSS)
for sel, want in ((".runhealth{", "padding:6px 10px"),
                  ("#log{", "padding:8px 10px"),
                  ("#summary{", "padding:6px 10px"),
                  ("main#grid{", "padding:8px 10px")):
    truthy("%s is 10px in from the edge" % sel.strip("{"), want in rule(CSS, sel))
truthy("and the Orbit layout's own three", "#sec_listings > .tabfilter{" in CSS)

print("\n=== 5 and 8. the bars above the table ===")
truthy("the metrics bar is hidden", "display:none !important" in rule(LR, ".lr-metricsbar{"))
truthy("  and says the refresh went with it",
       "no visible control that asks" in LR)
truthy("the count/sort row is slim", "padding:2px 10px" in rule(LR, ".lr-sortbar{"))
truthy("  with a smaller select", "font-size:10px" in rule(LR, ".lr-sortbar select{"))

print("\n=== 7. the product column takes what is left ===")
falsy("the minimum that caused the gap is gone", ".col-product{ min-width" in LR)
for sel, w in ((".col-cb{", "28px"), (".col-status{", "100px"),
               (".col-perf{", "120px"), (".col-inv{", "110px"),
               (".col-price{", "145px"), (".col-fees{", "105px"),
               (".col-actions{", "24px")):
    truthy("%s is %s" % (sel.strip("{"), w), "width:" + w in rule(LR, sel))
truthy("the data columns do not wrap", "white-space:nowrap" in rule(LR, ".col-perf{"))
# Comments stripped: the file explains WHY it does not use table-layout:fixed,
# and matching the whole text would fail on its own reasoning.
LRCODE = re.sub(r"/\*.*?\*/", "", LR, flags=re.S)
falsy("and the table is NOT fixed-layout", "table-layout:fixed" in LRCODE)
# The title wraps rather than being cut: a clamped title left the rest of the
# column empty underneath, which is the dead space this pass is about.
falsy("the title is not clamped", "-webkit-line-clamp" in rule(LR, ".prod-title{"))
truthy("  it wraps", "white-space:normal" in rule(LR, ".prod-title{"))

print("\n=== 9. the drawer cannot open empty ===")
truthy("the remembered fold is thrown away, not read",
       "localStorage.removeItem(NAVMINI_KEY)" in SIDE)
falsy("  it no longer restores it", 'getItem(NAVMINI_KEY) === "1"' in SIDE)
truthy("  and says why", "Show menu" in SIDE)
truthy("the CSS guarantees the items regardless",
       "display:revert !important" in MOB)
truthy("  and explains the specificity it is beating",
       ":not(.navtoggle) counts" in MOB)
# BOTH are needed: the JS stops it at load, the CSS stops anything setting it
# later from hiding the menu.
truthy("both halves are present and each says the other is needed",
       "both are needed" in MOB.lower() or "both are needed" in SIDE.lower()
       or "one of the two fixes alone" in SIDE)

print("\n=== nothing is half-written ===")
for name, txt in (("dashboard.css", CSS), ("listrow_detailed.css", LR),
                  ("mobile.css", MOB)):
    check("%s braces balance" % name, txt.count("{"), txt.count("}"))
truthy("no mojibake in anything touched",
       not re.search(r"â€|Â·|â•", CSS + LR + MOB + HTML + SW + SIDE))

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
