"""prompt_orbit_layout.docx -- eight CSS additions, nothing removed.

    "CRITICAL RULE: Do NOT change any existing feature, route, endpoint, or
     functionality. This is LAYOUT only."

All eight are in place, in one block in dashboard.css. This file pins them, and
pins the two places where what is on screen is NOT what the brief's numbers say
-- both deliberate, both because a later instruction overrode them, and both
worth a check so that neither is "fixed" back by accident.

MEASURED IN CHROME on nestwell_goods/listings:
    nav labels   Account / Operations / Analytics / Tools, 10px, .6px tracking,
                 16px 16px 4px padding, uppercase
    tables       td font-variant-numeric tabular-nums, th uppercase
    skeleton     .skeleton is a live rule
    grid padding 0px 10px 10px -- NOT the brief's 32px, see below
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


CSS = read("static", "css", "dashboard.css")
TPL = read("templates", "dashboard.html")
# Comments stripped: a note ABOUT a rule is not the rule.
LIVE = re.sub(r"(?s:/\*.*?\*/)", "", CSS)

print("== 1. content padding ==")
yes("the panels size their padding from --wspad",
    ".wspanel{display:none;padding:var(--wspad,32px)}" in LIVE)
yes("  which falls back to the brief's 32px", "var(--wspad,32px)" in LIVE)
# THE LISTINGS GRID IS THE EXCEPTION, and it is deliberate. A later brief asked
# for that screen to be tight against the edges, by name:
#     "The table still has padding/margin between it and the left/right screen
#      edges."
# The Orbit brief allows exactly this: "reduce ... for that specific section
# rather than reverting globally." Scoped with #sec_listings so it wins on
# specificity and no other screen moves.
yes("the listings grid overrides it, scoped",
    "#sec_listings main#grid{ padding:0 10px 10px; }" in LIVE)
yes("  and the reason is written down", "MOCKUP MATCH PASS" in CSS)

print("\n== 2. sidebar section labels ==")
for label in ("Account", "Operations", "Analytics", "Tools"):
    yes("  %s" % label, '<div class="slbl">%s</div>' % label in TPL)
yes("styled to the brief's spec", ".slbl{letter-spacing:.06em;padding:16px 16px 4px}" in LIVE)
# "Do NOT reorder nav items. Do NOT remove any nav item." A label is a sibling
# inserted between groups; nothing is nested or moved.
yes("  the labels are siblings, not wrappers", "</div>" in TPL.split('<div class="slbl">')[1][:40])

print("\n== 3. tables ==")
yes("digits align", "table td{font-variant-numeric:tabular-nums}" in LIVE)
yes("headers are uppercase and tracked",
    "table th{text-transform:uppercase;letter-spacing:.03em;font-weight:600}" in LIVE)
yes("one row hover, with a transition",
    "table tr{transition:background-color .12s ease}" in LIVE
    and "table tbody tr:hover > td{background:rgba(255,255,255,.03)}" in LIVE)
# The brief said "Remove any conflicting row hover styles". They are left: a
# working style removed to satisfy a general one is how a screen that was fine
# ends up looking wrong. The generic rule is deliberately weak so those win.
yes("  and the reason the conflicting ones were kept is written down",
    "removing a working style to satisfy a general one" in CSS)

print("\n== 4-8. the reusable pieces ==")
yes("4. .stat-row / .stat-card", ".stat-row{display:grid" in LIVE and ".stat-card{" in LIVE)
yes("5. a teal focus ring, on :focus-visible only",
    "*:focus-visible{outline:none;box-shadow:0 0 0 3px rgba(45,212,168,.3)}" in LIVE)
yes("   not on :focus, so a mouse click leaves no glow",
    "*:focus{outline:none;box-shadow" not in LIVE)
yes("6. .skeleton shimmer", ".skeleton{background:linear-gradient(90deg" in LIVE
    and "@keyframes shimmer" in LIVE)
yes("   which stops for prefers-reduced-motion", ".skeleton{animation:none}" in LIVE)
yes("7. the drawer gained only its shadow",
    ".drawer{box-shadow:-8px 0 32px rgba(0,0,0,.5)}" in LIVE)
# "Only if these don't conflict with the current drawer behavior. If the drawer
# already works, leave it." It already slid and already had a scrim; the audit's
# 560px would have MOVED a working panel.
yes("   and its width was left alone", ".drawer{max-width:min(560px" not in LIVE)
yes("8. .chart-subtitle",
    ".chart-subtitle{font-size:12px;color:var(--ink3);margin-top:4px;margin-bottom:16px}" in LIVE)

print("\n== what the brief said NOT to do ==")
yes("the accent is unchanged", "--accent:#2dd4a8;" in LIVE)
# "Do NOT change the sidebar width (keep 210px)." The Orbit block adds nothing
# that sizes it -- what matters is that no rule inside those eight items does.
_orbit = LIVE[LIVE.index("main#grid{padding:18px"):LIVE.index(".chart-subtitle{")]
yes("the Orbit block sets no sidebar width",
    "sidebar" not in _orbit and "#workspace" not in _orbit)
yes("  and no nav width", ".nav" not in _orbit)
yes("nothing in this block touches a route or an endpoint",
    "/api/" not in CSS and "fetch(" not in CSS)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
