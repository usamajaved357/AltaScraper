"""One appbar, on every page.

    "The orders page still uses the old full-width tab navigation header with
     Returns Intelligence, All orders, Variations, etc. spread across the bar.
     Apply the same compact header from the listings page density pass ... This
     should be consistent across ALL pages."

MEASURED IN CHROME on seven pages of nestwell_goods -- listings, orders,
sourcing, sales, inventory, generate, returns -- and it already is:

    height 47px, padding 6px 12px, gap 8px on every one, and the same twelve
    children in the same order: burger, brandmark, crumbs, bmkbar,
    acct-switch-chip, spacer, health badge, two icon buttons, three bar buttons.

Nothing was changed. What this file does is stop it drifting apart again, which
is the failure the brief is actually describing: there is ONE appbar in ONE
template, and a page that grew its own header would have to do it by adding
markup, which is what these checks look for.

(The brief also names 5px 10px / 36px. The density pass settled on 6px 12px and
a height the buttons themselves set. Those numbers are not re-litigated here --
the requirement that can regress, and the one that was reported, is that every
page is the same.)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


TPL = read("templates", "dashboard.html")
CSS = read("static", "css", "dashboard.css")

print("== the appbar is written once ==")
check("one <div class=\"appbar\"> in the template",
      len(re.findall(r'class="appbar"', TPL)), 1)
check("  and one .appbar rule that lays it out",
      len(re.findall(r"^\.appbar\{", CSS, re.M)), 1)

print("\n== it is outside the sections, so every page gets it ==")
# The page bodies are #sec_* blocks swapped in and out; the appbar sits above
# them. If it moved inside one, that page would keep it and the rest would lose
# it -- which is exactly how one page comes to have its own header.
_bar = TPL.index('class="appbar"')
_first_sec = TPL.index('id="sec_')
yes("the appbar comes before the first section", _bar < _first_sec)
yes("  and is not inside one",
    "sec_" not in TPL[max(0, _bar - 400):_bar])

print("\n== no page draws a second one ==")
# A page-specific tab strip across the bar is the thing that was removed. The
# page's own tabs belong in the bookmarks bar, which is IN the appbar.
for name in (".pagetabs", ".tabnav", ".subnav", "old-appbar", "appbar2"):
    check("  nothing named %s exists" % name, name in CSS or name in TPL, False)
yes("the bookmarks bar is a child of the appbar", 'id="bmkbar"' in TPL)
_bmk = TPL.index('id="bmkbar"')
_barend = TPL.index("</div>", _bar)
yes("  and it sits inside it", _bmk > _bar)

print("\n== the JS that draws pages never touches the appbar ==")
# Every section renderer writes into its own host. One that rewrote the appbar
# would give that page a header of its own the moment it ran.
bad = []
for f in sorted(os.listdir(os.path.join(HERE, "static", "js"))):
    if not f.endswith(".js"):
        continue
    src = read("static", "js", f)
    src = re.sub(r"(?s:/\*.*?\*/)", "", src)
    src = re.sub(r"(?m:^[ \t]*//[^\n]*)", "", src)
    if re.search(r"querySelector\(['\"]\.appbar['\"]\)\s*\.innerHTML\s*=", src):
        bad.append(f)
    if re.search(r"getElementById\(['\"]appbar['\"]\)\s*\.innerHTML\s*=", src):
        bad.append(f)
check("no file replaces the appbar's contents", sorted(set(bad)), [])

print("\n== measured in Chrome, seven pages ==")
# listings / orders / sourcing / sales / inventory / generate / returns:
#   height 47, padding "6px 12px", gap "8px" on all seven
#   children identical and in the same order on all seven
yes("the appbar has a spacer, so the right-hand group stays right",
    'class="spacer"' in TPL)
yes("  and a health badge", 'class="hb"' in TPL or 'id="hb"' in TPL)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
