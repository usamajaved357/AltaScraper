"""prompt.docx -- the app's STRUCTURE against full_app_orbit.html.

    "The colors match Orbit now but the UX is still the old app. These are the
     structural differences between the Orbit prototype (full_app_orbit.html)
     and the current app."

    "Open the mockup HTML, match this structure exactly."

Every number below is READ OUT OF full_app_orbit.html at run time, not typed in
from the brief -- so if the prototype is edited this test moves with it and
cannot go quietly out of date. Each check names the prototype rule it came from.

WHERE THE APP DELIBERATELY DIFFERS, the difference is named here with the
instruction that overruled the prototype. There are three, and all three are
the owner overruling his own mockup in a later message.
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
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


def nocomments(s):
    return re.sub(r"(?s:/\*.*?\*/)", "", s)


PROTO = read("full_app_orbit.html")
CSS = {}
_d = os.path.join(HERE, "static", "css")
for _f in sorted(os.listdir(_d)):
    if _f.endswith(".css"):
        CSS[_f] = nocomments(read("static", "css", _f))
ALLCSS = "\n".join(CSS.values())
JS = {}
_d = os.path.join(HERE, "static", "js")
for _f in sorted(os.listdir(_d)):
    if _f.endswith(".js"):
        JS[_f] = read("static", "js", _f)


def proto_rule(sel):
    """The prototype's declarations for one selector, as a dict."""
    m = re.search(r"(?m)^" + re.escape(sel) + r"\{([^}]*)\}", PROTO)
    if not m:
        return {}
    out = {}
    for d in m.group(1).split(";"):
        if ":" in d:
            k, v = d.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def app_rule(sel_re):
    """Every declaration the app makes under any selector matching sel_re,
    flattened. Selectors are written differently here (the app scopes .thumb
    under .lt, for one) so this asks WHAT IS SET, not where."""
    body = ""
    for s in CSS.values():
        for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", s):
            head = m.group(1).strip().split("\n")[-1].strip()
            if re.search(sel_re, head):
                body += m.group(2) + ";"
    out = {}
    for d in body.split(";"):
        if ":" in d:
            k, v = d.split(":", 1)
            out.setdefault(k.strip(), []).append(" ".join(v.split()))
    return out


# The app names its radii; the prototype writes them out. Resolved from :root so
# "6px" and "var(--radius-sm)" are recognised as the same measurement -- and the
# app's version is the better one, because it moves with the theme.
ROOT = {}
for _m in re.finditer(r"--([a-z0-9-]+)\s*:\s*([^;}]+)", CSS.get("dashboard.css", "")):
    ROOT.setdefault("var(--%s)" % _m.group(1), _m.group(2).strip())


def norm(v, subs):
    """One value in comparable form: the prototype's token names swapped for
    this app's, then any remaining var() resolved to what it holds."""
    v = " ".join(str(v).split())
    for a, b in subs.items():
        v = v.replace(a, b)
    for tok, val in ROOT.items():
        v = v.replace(tok, val)
    return v


def same(label, proto_sel, app_sel_re, props, subs=None, allow=None):
    """Each named property, prototype value vs the app's.

    `allow` names a property the app deliberately sets differently, with the
    instruction that overruled the prototype. It is REPORTED, not skipped --
    a departure nobody can see is indistinguishable from a bug."""
    p = proto_rule(proto_sel)
    a = app_rule(app_sel_re)
    subs = subs or {}
    allow = allow or {}
    for prop in props:
        want = p.get(prop)
        if want is None:
            FAILS.append("%s: prototype has no %s" % (label, prop))
            print("  %-62s FAIL prototype has no %s" % (label, prop))
            continue
        want = norm(want, subs)
        got = [norm(g, subs) for g in a.get(prop, [])]
        ok = want in got
        if not ok and prop in allow:
            print("  %-40s %-14s DIFFERS ON PURPOSE app=%s -- %s"
                  % (label + " " + prop, want, got[:1], allow[prop]))
            continue
        if not ok:
            FAILS.append("%s %s" % (label, prop))
        print("  %-40s %-14s %s" % (label + " " + prop, want,
                                    "OK" if ok else "FAIL app=%r" % (got[:3],)))


# The prototype hard-codes hex; the app uses its own token names for the same
# colours. Mapping them here is what lets a value comparison mean anything.
TOK = {
    "var(--brd)": "var(--line)",
    "var(--card)": "var(--panel)",
    "var(--card2)": "var(--panel2)",
    "var(--teal)": "var(--accent)",
    "var(--green-bg)": "var(--ok-bg)",
    "var(--green)": "var(--ok)",
    "var(--red)": "var(--bad)",
    "var(--side-bg)": "var(--sidebar)",
}

print("== item 1: LISTINGS ARE A TABLE, and the tile grid is still there ==")
L = JS["listings.js"]
yes("tableRow(r) exists beside card(r)",
    "function tableRow(r)" in L and "function card(r)" in L)
yes("  and card() was not deleted", L.count("function card(r)") == 1)
yes("table is the DEFAULT view", 'let LIST_VIEW = "table"' in L)
yes("  the preference is in localStorage", '"alta_list_view"' in L)
yes("  and an unknown stored value falls back rather than sticking",
    "function listViewNow()" in L)
yes("there is a toggle in the toolbar", "viewtoggle" in L)
# The brief names two views. A third -- the Amazon Manage-All-Inventory row --
# was added later by LISTINGS_FUNCTIONAL_FIXES.md and is additive: table is
# still the default and the card grid is still one click away.
yes("  the grid view is one of its options", 'data-view="grid"' in L
    or "dataset.view" in L)
print("\n  -- the .lt rules, against the prototype's --")
# THE TABLE IS DENSER THAN THE PROTOTYPE, on a later instruction:
#     "the sizing and the theme of the repricer page is nice, i want this to be
#      applied on all listings page and the catalog page"
# static/css/datatable.css is now the ONE definition of a product table for the
# Listings, Catalog, Stock, PPC and Repricer screens (CLAUDE.md Rule 12), and
# its header is 9px uppercase on 7px 5px rather than the prototype's 11px on
# 10px 8px. That is what took the Listings row from 80px to 44px -- five rows a
# screen to nine -- with nothing removed from it. Restoring the prototype's
# numbers here would undo that instruction AND re-split one rule into five.
_DENSER = "datatable.css is the one table look, per the repricer instruction"
same("th", ".lt th", r"\.lt th\b",
     ["font-size", "font-weight", "color", "letter-spacing", "padding"], TOK,
     allow={"font-size": _DENSER, "letter-spacing": _DENSER, "padding": _DENSER})
same("td", ".lt td", r"\.lt td\b", ["padding", "font-size"], TOK,
     allow={"padding": _DENSER})
# 36px, not the prototype's 44 -- the same shared-table instruction. One thumb
# size for the Listings, Catalog, Stock, PPC and Repricer tables; three sizes
# (34, 38, 36) existed before it.
_SHARED_THUMB = "one 36px thumb across the five product tables"
same("thumb", ".thumb", r"\.lt \.thumb\b",
     ["width", "height", "border-radius"], TOK,
     allow={"width": _SHARED_THUMB, "height": _SHARED_THUMB})
same("asin", ".asin", r"\.lt \.asin\b", ["color", "font-size", "font-weight"], TOK)
same("brand", ".brand", r"\.lt \.brand\b", ["color", "font-size"], TOK)
same("ttl", ".ttl", r"\.lt \.ttl\b",
     ["font-size", "font-weight", "max-width", "text-overflow"], TOK)
same("comp", ".comp", r"\.lt \.comp\b", ["font-size", "gap"], TOK)
same("dotb", ".dotb", r"^\.lt \.dotb$", ["width", "height", "border-radius"], TOK)
yes("a row hover, as the prototype has", re.search(
    r"\.lt tbody tr:hover td|\.lt tr:hover td", ALLCSS) is not None)

print("\n  -- ONE definition each (CLAUDE.md Rule 12) --")
# ALL THREE HAD TWO, and the cascade picked a different winner for each:
#   .lt .acts   kept flex-wrap:wrap from the copy the later one never reset.
#               Five controls in a 150px column folded onto two lines and every
#               row measured 73px -- six rows a screen where datatable.css was
#               written for nine. Measured 53px with one definition.
#   .lt .dotb   the dead copy was `.lt .acts .dotb`, three classes, so it
#               outranked the 28px rule however late that came. Measured 26px
#               on screen against a brief that says 28. Now 28.
#   .lt .thumb  44px in dashboard.css, 36px in datatable.css which loads later.
#               The 44 had been saying nothing for months.
def defs(sel, prop):
    """How many rules SET this property on this exact selector. Two rules that
    do different jobs are fine -- .lt .thumb's size and its centring are
    separate lines in datatable.css. Two rules setting the same property is the
    thing that produces a winner nobody chose."""
    n = 0
    for s in CSS.values():
        for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", s):
            head = " ".join(m.group(1).strip().split("\n")[-1].split())
            if any(o.strip() == sel for o in head.split(",")):
                if re.search(r"(^|;)\s*" + prop + r"\s*:", m.group(2)):
                    n += 1
    return n


for sel, prop in ((".lt .acts", "display"), (".lt .dotb", "width"),
                  (".lt .thumb", "width")):
    check("%-12s sets %-7s in one place" % (sel, prop), defs(sel, prop), 1)
# The dead copy was `.lt .acts .dotb` -- a THIRD class, so it outranked the
# 28px rule wherever that sat in the file. Specificity, not order.
check("  and nothing outranks .lt .dotb with a third class",
      ".lt .acts .dotb" in ALLCSS, False)
acts = re.search(r"\.lt \.acts\{([^}]*)\}", ALLCSS)
yes("  and the actions row never wraps",
    acts and "flex-wrap:nowrap" in " ".join(acts.group(1).split()))
# The placeholder icon centring came off the deleted .lt .thumb rule and had to
# land somewhere, or it would sit in the corner of the box.
yes("  the thumb still centres its placeholder",
    re.search(r"\.lt \.thumb\{[^}]*justify-content:center", ALLCSS) is not None)

print("\n== item 2: THE TOP BAR IS SPARSE ==")
#     "Current: 6+ buttons (Research ASIN, Privacy, AI settings, Home)
#      Orbit: just breadcrumb text + health badge on the right"
DASH = read("templates", "dashboard.html")
bar = re.search(r'<div class="appbar".*?</div>\s*(?=<)', DASH, re.S)
yes("the health badge is on the right", ".appbar .hb" in ALLCSS
    and "margin-left:auto" in ALLCSS)
yes("  green dot and all", ".appbar .hb .dot" in ALLCSS)
yes("there is a breadcrumb", "crumb" in DASH or "breadcrumb" in DASH)
# "Move Research ASIN and AI settings to the sidebar footer or a dropdown."
for gone in ("Research ASIN", "AI settings"):
    inbar = bar and gone.lower() in bar.group(0).lower()
    check("  %r is not a button in the bar" % gone, bool(inbar), False)
yes("  they are still reachable from the sidebar menu",
    "asinresearch" in DASH or "openAsinResearch" in DASH
    or "asinresearch" in JS.get("sidebar.js", ""))

print("\n== item 3/4: METRIC TILES REPLACE THE TEXT SUMMARY ==")
yes("the summary line is four clickable tiles", "metricFilter(" in L)
yes("  clicking the lit one clears the filter", "neutralFilter()" in L)
# THE FIRST PLACE THE APP DEPARTS FROM THE PROTOTYPE, on a later instruction:
#     "the sizing and the theme of the repricer page is nice, i want this to be
#      applied on all listings page and the catalog page"
# The prototype's tile is centred, 22px, no bar. The Repricer's is left-aligned
# with a share bar, and three screens now call one uiStat() (CLAUDE.md Rule 12)
# rather than each building its own card. The prototype's numbers are therefore
# NOT asserted here -- doing so would undo that instruction.
yes("  built by the ONE shared card, not a fourth private one",
    "uiStat(" in L and "function uiStat" in JS["pageui.js"])
check("  and listings.js no longer builds its own .metric",
      re.search(r'class="metric[" ]', L) is not None, False)

print("\n== item 5: FORM FIELDS ==")
same("fld", ".fld", r"^\.fld$",
     ["background", "border", "border-radius", "padding"], TOK)
same("fld label", ".fld .k", r"\.fld > label|\.fld \.fldlab", ["font-size", "color"], TOK)
same("fld input", ".fld input,.fld textarea",
     r"\.fld input,\.fld select,\.fld textarea", ["font-size", "color"], TOK)

print("\n== item 6: THE COMPLIANCE BANNER ==")
#     "Orbit shows a full-width banner in the detail view ... Clear: green bg,
#      green border, green text, shield-check icon, 'Compliance clear -- no
#      restricted-product or claim flags'"
yes("the exact wording is in the app",
    "Compliance clear \u2014 no restricted-product or claim flags" in L)
yes("  with the shield-check icon", "shield-check" in L)
# SECOND DEPARTURE, and the reason is in listings.js:
#     "It returns NOTHING when the checks did not run. Showing 'compliance
#      clear' for a listing nobody checked is a claim the app cannot make."
yes("  and it is silent when the checks never ran",
    "It returns NOTHING when the checks did not run" in L)
yes("gold and red states as well",
    "shield-x" in L and ("alert-triangle" in L or "shield-exclamation" in L))
# The prototype writes the banner inline rather than as a class, so there is no
# rule to compare -- these are its inline numbers, read out of the markup.
pb = re.search(r'padding:10px 12px;background:var\(--green-bg\);'
               r'border:1px solid #1a4a28;border-radius:8px', PROTO)
yes("the prototype's banner is 10px 12px / radius 8px", pb is not None)

print("\n== item 3 (first half): SIDEBAR SIZING ==")
# THE SIDEBAR IS 284px ON SCREEN, NOT THE PROTOTYPE'S 210. A later instruction:
#     "The app's left sidebar is causing the listings table to shrink and
#      resize. On Amazon, the sidebar opens as an overlay/drawer on TOP of the
#      page -- it does NOT push the content."  /  "i want sidebar overlay"
# static/css/mobile.css took the sidebar out of the flow at EVERY width and
# gave it the drawer's own 284px. dashboard.css still says 210px and that rule
# no longer decides anything -- which is why this is measured against the file
# that wins, not the first one that mentions a width.
same("sidebar (dashboard.css, superseded)", ".side", r"^\.sidebar$", ["width"], TOK)
_ov = re.search(r"#workspace \.sidebar\{([^}]*)\}", CSS["mobile.css"])
yes("the overlay drawer is what actually sizes it", _ov)
_ovb = " ".join(_ov.group(1).split()) if _ov else ""
check("  284px, over the page rather than beside it",
      "width:284px" in _ovb and "position:fixed" in _ovb, True)
same("section label", ".slbl", r"^\.slbl$",
     ["font-size", "font-weight", "letter-spacing", "text-transform", "color"], TOK)
# The prototype's nav item is a bare <a class="snv">; this app's is .navitem in a
# collapsible tree (navgroups.js) with a mini mode. Different name, same item --
# so what the brief actually specifies is checked by value.
#
#     "Nav item font: 12px (not 13 or 14). Nav item padding: 8px 14px.
#      Active state: 3px left border --teal + teal text + --teal-bg"
nav = re.search(r"(?m)^\s*\.navitem\{([^}]*)\}", CSS["dashboard.css"])
yes("the nav item rule is there", nav)
navb = " ".join(nav.group(1).split()) if nav else ""
check("  font-size 12px", "font-size:12px" in navb, True)
# 11px on the left, not 14: the 3px border sits inside it and the two together
# are the prototype's 14. Measured on screen, the text starts in the same place.
check("  padding 8px 14px, the left split with the border",
      "padding:8px 14px 8px 11px" in navb and "border-left:3px solid transparent" in navb, True)
act = re.search(r"(?m)^\s*\.navitem\.active\{([^}]*)\}", CSS["dashboard.css"])
actb = " ".join(act.group(1).split()) if act else ""
check("  active: 3px accent border, accent text, accent background",
      ("border-left-color:var(--accent)" in actb and "color:var(--accent)" in actb
       and "background:var(--accent-bg)" in actb), True)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
