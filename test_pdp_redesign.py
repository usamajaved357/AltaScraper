"""The product page, against PDP_REDESIGN_TASK.md.

Twelve items. These check the ones that can be checked without a browser --
the rest were driven in Chrome. Each test names the item it covers.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


def code(src):
    """JS with its comments stripped. A test that passes on a comment about a
    feature rather than the feature has caught nothing -- this has happened
    here often enough to be worth a helper."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


PDP = code(read("static", "js", "pdp.js"))
CSS = read("static", "css", "pdp.css")
AF = code(read("static", "js", "autofix.js"))
DA = code(read("static", "js", "drawer_attributes.js"))
RT = read("routes", "listing_routes.py")
DASH = read("dashboard.py")

print("\n== item 1: the panel is 680px ==")
# width:min(680px,94vw) -> width:100% + max-width:680px. PDP_MATCH_MOCKUP.md
# spells the panel out, and the difference matters: min() made the panel size
# itself against the VIEWPORT, so on a narrow window it shrank while the
# backdrop's own padding was already reserving the same space twice.
yes("the panel is 680 at most", "max-width:680px" in CSS and "width:100%;" in CSS)
yes("  and the backdrop keeps a gap all round", "padding:40px 60px" in CSS)
yes("the rail is 130px", re.search(r"\.pdp-side\{[^}]*width:130px", CSS, re.S))
yes("content padding is 12px 16px", ".pdp-content{ flex:1; min-width:0; padding:12px 16px; }" in CSS)

print("\n== item 2: what Amazon is showing shoppers, above the box ==")
yes("the endpoint passes summaries on", '"summary": summary' in RT)
yes("  under Amazon's own key names", '"itemName", "asin", "brand"' in RT)
yes("  and the cache keeps it apart from `values`", "summary:j.summary||{}" in DA)
yes("pdpLiveLine exists", "function pdpLiveLine(sku, kind)" in PDP)
yes("  it prefers the catalogue value", "S.itemName" in PDP)
yes("  and says which of the two it is showing", "pdp-livetag" in PDP and ".pdp-livetag{" in CSS)
yes("  it draws nothing for a listing that is not live",
    'L.state !== "ok"' in PDP.split("function pdpLiveLine")[1][:400])
_det = PDP[PDP.index('if(PDP_TAB === "details")'):]
_det = _det[:_det.index("else if")]
for kind in ("title", "bullets", "desc", "search"):
    yes("  the details tab draws it for %s" % kind, 'pdpLiveLine(sku, "%s")' % kind in _det)

print("\n== item 3: a (?) on every attribute label, from Amazon's schema ==")
yes("_load_schema collects Amazon's description", '"help": {}' in DASH)
yes("/schema serves it", '"help"' in RT)
yes("pdpHelp exists", "function pdpHelp(m, key)" in PDP)
yes("  and every label gets one", "pdpHelp(m, k)" in PDP)
yes("  nothing is hardcoded -- it reads m.help", "m.help[key]" in PDP)

print("\n== item 5: Add More / Remove Last, from the schema's maxItems ==")
yes("pdpMaxItems reads m.maxitems", "function pdpMaxItems(m, key)" in PDP
    and "m.maxitems[key]" in PDP)
yes("  0 means no ceiling, not 'no multi'", "return n;" in PDP)
yes("the cell exists", "function pdpMvCell(sku, key, val, max)" in PDP)
yes("  Add More disappears at the ceiling", "const canAdd = (max === 0) || (parts.length < max)" in PDP)
yes("  Remove Last only shows with 2+ entries", "parts.length > 1" in PDP)
yes("  it saves through editField, not a second /edit call",
    'editField(sku, "attr", key, joined)' in PDP and "fetch(\"/edit\"" not in PDP)
yes("  a dropdown never becomes multi-value", "const wantsMulti = !hasEnum &&" in PDP)
# FOUND IN CHROME, ON A REAL LISTING: special_features held seven entries
# against a schema maxItems of five, written as one comma-separated line before
# anything counted them. "7/5" states the fact without saying what it costs.
yes("being over Amazon's ceiling is said in words", "pdp-mvover" in PDP
    and "will be refused" in PDP)
yes("  and the count goes red", ".pdp-mvcap.over{" in CSS)
yes("  both stay right after an add or a remove",
    'cap.classList.toggle("over"' in PDP)

print("\n== item 6: textareas grow to fit ==")
yes("field-sizing is set", "field-sizing:content" in CSS)
yes("  with a JS fallback for browsers without it", "function pdpGrow(ta)" in PDP)
yes("  which stands aside where the browser does it",
    'CSS.supports("field-sizing", "content")' in PDP)
yes("  bound once, by delegation", "PDP_GROW_BOUND" in PDP)
yes("  and re-measured after a render", "pdpAutoGrow();" in PDP)

print("\n== item 7: Amazon's rejection is visible (see test_api_issues.py too) ==")
yes("the banner is built", "function pdpApiIssues(r)" in PDP)
yes("  and each field name is a destination", "function pdpGoToField(key)" in PDP)

print("\n== item 8: Cancel / Save and finish, stuck to the bottom ==")
yes("the footer is built", "function pdpFooter(r)" in PDP)
yes("  and rendered inside the panel", "+ pdpFooter(r) +" in PDP)
yes("  it is sticky", re.search(r"\.pdp-footer\{[^}]*position:sticky", CSS, re.S))
yes("Cancel closes", 'class="pdp-footer-cancel" onclick="pdpClose()"' in PDP)
yes("  Save and finish commits the focused box first",
    "function pdpSaveAndFinish()" in PDP and "a.blur()" in PDP)
# NOTHING IS SENT TO AMAZON FROM THIS FOOTER. "Save and finish" in the brief
# meant putListingsItem, which PUBLISHES. A button that reads like closing a
# dialog must not put a listing live -- Submit is labelled Submit.
yes("  and it does not submit to Amazon",
    "submitOne" not in PDP.split("function pdpFooter")[1].split("function pdpRender")[0])

print("\n== item 10: read-only fields ==")
yes("_load_schema collects readOnly", '"readonly": []' in DASH)
yes("  the table locks them", "const locked = (m.readonly || []).indexOf(k) >= 0;" in PDP)
yes("  with a padlock", "ti-lock pdp-lock" in PDP)

print("\n== item 11: dropdowns come from the schema's enum ==")
yes("hasEnum drives the control", "const hasEnum = !!(m.enums[k] && m.enums[k].length);" in PDP)
yes("  and editCell renders a <select> for it", 'select class="ed"' in AF)

print("\n== item 12: grouped attributes ==")
yes("dotted keys are pulled together", "const keys = (function(){" in PDP)
yes("  a heading is drawn once per family", "pdp-agrouphead" in PDP)
yes("  only when a member survived the filter", "openGroup !== top" in PDP)
# The rows are not table rows any more -- see test_pdp.js. A member of a group
# is set in from the label column rather than indented inside a cell.
yes("  members are set in from the label column",
    ".pdp-attr.sub > .pdp-attr-label{ padding-right:10px; }" in CSS)
yes("  and labelled by their leaf", "String(k).slice(topKey.length + 1)" in PDP)

print("\n== the cache cannot hide a newly-read field ==")
SCH = read("domain", "schema_cache.py")
yes("the stored shape is checked", "def is_current_shape(info)" in SCH)
yes("  help, maxitems and readonly are part of it",
    '"help", "maxitems", "readonly"' in SCH)
yes("  a stale fallback still accepts an older one", "require_current=False" in SCH)

print("\n== nothing here reimplements a save ==")
# CLAUDE.md Rule 12. editField is the single caller of /edit; a second fetch to
# it from this file would be exactly the drift the rule exists to stop.
check("pdp.js never calls /edit itself", PDP.count("'/edit'") + PDP.count('"/edit"'), 0)

print("\n== driven in Chrome, on a real listing (MASSAGER, 37 attributes) ==")
# Recorded here so the numbers are not lost with the terminal. All of these were
# read out of the live page, not out of the source:
#
#   groups drawn ............ Cable, Unit Count
#   sub-rows indented ....... 4, labelled "Length unit" not "Cable Length Unit"
#   Add More ................ 10 boxes -> 11, cap 3/5 -> 4/5
#   Remove Last ............. back to 10, and no save for an empty box
#   over the ceiling ........ "Amazon allows 5 here and this has 7..."
#   error banner ............ 2 errors shown, 1 warning folded
#   field chips ............. item_name, cable.length.unit
#   clicking a chip ......... 1 row highlighted, tab switched to attributes
#   per-field messages ...... 2, under the boxes Amazon named
#   help bubble ............. shows the schema's own description on hover
#   panel ................... 680px wide, centred, rail 130px, footer sticky
#   page errors ............. 0
yes("the page is still one render call", "function pdpRender()" in PDP)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
