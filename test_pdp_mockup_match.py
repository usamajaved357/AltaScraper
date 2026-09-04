"""PDP_MATCH_MOCKUP.md -- the panel against altascraper-pdp-mockup.html.

    "Open the mockup in a browser, open the live app beside it, and make them
     identical. Not similar. Identical."

Every number below was read out of the mockup file, and every one of them was
then read back off the live panel in Chrome. Where the live app deliberately
differs from the mockup, the difference is named and the reason is here -- there
are two, and both are the brief overruling its own mockup.
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


def nocomments_css(s):
    return re.sub(r"(?s:/\*.*?\*/)", "", s)


def nocomments_js(s):
    s = re.sub(r"(?s:/\*.*?\*/)", "", s)
    return re.sub(r"(?m:^[ \t]*//[^\n]*)", "", s)


CSS = nocomments_css(read("static", "css", "pdp.css"))
JS = nocomments_js(read("static", "js", "pdp.js"))

print("== STEP 2: a centred card, backdrop visible on both sides ==")
yes("the backdrop is rgba(0,0,0,.6)", "background:rgba(0,0,0,.6)" in CSS)
yes("  with 40px 60px round the card", "padding:40px 60px" in CSS)
yes("  and it centres what it holds", "justify-content:center" in CSS)
# align-items, NOT justify-content, on the cross axis: this element scrolls, and
# centring an overflowing flex child vertically clips its top.
yes("  holding it to the top so a long panel is not clipped",
    "align-items:flex-start" in CSS)
yes("the panel is width:100% / max-width:680px",
    "max-width:680px" in CSS and "width:100%;" in CSS)
yes("  radius 10px", "border-radius:10px" in CSS)
yes("  shadow 0 8px 40px", "box-shadow:0 8px 40px rgba(0,0,0,.5)" in CSS)
yes("  align-self flex-start", "align-self:flex-start" in CSS)
# The panel used to be min-height:calc(100vh - 38px) -- full screen whatever it
# held, so its bottom edge was always off screen. That is a sheet, not a card.
# It is capped at the viewport now and has NO min-height at all: min-height
# beats max-height in CSS, so min-content kept the cap from applying and the
# panel still grew to 3,107px with nothing scrolling.
yes("  and capped at the viewport, not stretched to it",
    "max-height:calc(100vh - 80px)" in CSS)
check("  with no min-height to override that cap", "min-height:min-content" in CSS, False)

print("\n== the bars do not scroll away ==")
#     "The top bar (Back to listings, Preview, Auto-fix, Submit) and the tabs
#      bar scroll away when you scroll down in the content. They should stay
#      pinned at the top of the PDP panel while the content below scrolls."
#
# They were position:sticky against the BACKDROP, which is what scrolled. A
# sticky element can only stick within its own parent's box, so on a 3,000px
# panel they stuck for a while and then travelled off with it.
yes("the panel is a flex column that hides its own overflow",
    "flex-direction:column" in CSS and "overflow:hidden;" in CSS)
yes("the middle is the one scroller",
    ".pdp-layout{" in CSS and "flex:1; min-height:0; overflow-y:auto" in CSS)
yes("the bars are siblings outside it, and do not shrink",
    ".pdp-top, .pdp-hero, .pdp-tabs, .pdp-footer{ flex-shrink:0; }" in CSS)
check("  none of them is sticky any more",
      "position:sticky; top:0; z-index:3" in CSS
      or "position:sticky; top:41px" in CSS
      or "position:sticky; bottom:0" in CSS, False)
# position:fixed appears once and belongs to #pdp, the BACKDROP -- which has to
# be fixed. What must not be fixed is anything inside the panel.
check("  and none is fixed",
      re.search(r"\.pdp-(top|tabs|footer|hero)\{[^}]*position:fixed", CSS) is not None,
      False)
# The rail is the exception, and it is INSIDE the scroller: sticky there keeps
# a short list of actions in view without having to scroll back up for it.
yes("the rail stays in view inside the scroller",
    "position:sticky; top:0; align-self:flex-start;" in CSS)
yes("the JS shows it as a flex box, not a block", 'host.style.display = "flex"' in JS)

print("\n== STEP 3: four tabs, Amazon's names, no Attributes tab ==")
tabs = re.search(r"const PDP_TABS = \[(.*?)\];", JS, re.S)
yes("PDP_TABS exists", tabs)
labels = re.findall(r'label:"([^"]+)"', tabs.group(1) if tabs else "")
check("the labels", labels,
      ["Product Details", "Images", "Variations", "Offer", "Safety & Compliance"])
check("  and none of them is Attributes", "Attributes" in labels, False)
# "Listing with variations: 5 tabs." One of the five is conditional, so a normal
# listing gets four.
yes("Variations is conditional", 'only: "hasVariations"' in JS)
yes("  on something the row already says", "function pdpHasVariations(r)" in JS)
yes("  and the bar is built per listing", "function pdpTabsFor(r)" in JS)
yes("  from the row", "pdpTabBar(r)" in JS)
# PDP_TAB survives between listings, so a stale one must not draw a blank page.
yes("a tab that no longer exists falls back to details",
    'if(!tabs.some(function(t){ return t.key === PDP_TAB; })) PDP_TAB = "details";' in JS)

print("\n== STEP 4: the attributes are a section of Product Details ==")
det = JS[JS.index('if(PDP_TAB === "details")'):]
det = det[:det.index('} else if(PDP_TAB === "images")')]
yes("the details tab draws them", "pdpAttrSection(p.attrModel, p.addCtrl)" in det)
yes("  after the description", det.index("p.desc") < det.index("pdpAttrSection"))
yes("the rows are label + value, 110px right-aligned",
    ".pdp-attr-label{" in CSS and "width:110px" in CSS and "text-align:right" in CSS)
yes("  and the value takes the rest", ".pdp-attr-value{ flex:1" in CSS)
yes("what Amazon holds sits above the box", ".pdp-attr-amazon{" in CSS
    and "pdp-attr-amazon" in JS)
yes("every control is full width",
    ".pdp-attr .ed,\n.pdp-attr select.ed{\n  width:100%" in CSS)
check("the scrolling five-column table is gone", ".pdp-atwrap{" in CSS, False)
yes("required is a red asterisk, as the mockup has it",
    ">*</span>" in JS and ".pdp-req{" in CSS)
# ★ and ☆ were the markers. ☆ renders as a tofu box in this font stack -- it
# was visible on screen as a stray glyph before "Country Of Origin".
check("  and not a star glyph", "★" in JS or "☆" in JS, False)

print("\n== STEP 5: the sidebar ==")
yes("130px wide, 12px 10px padding",
    ".pdp-side{" in CSS and "width:130px" in CSS and "padding:12px 10px" in CSS)
yes("title 9px uppercase", ".pdp-sblabel{" in CSS and "font-size:9px" in CSS)
yes("items 11px", ".pdp-sbitem{" in CSS and "font-size:11px" in CSS)

print("\n== STEP 6: the hero ==")
yes("image 100x100", ".pdp-heroimg{" in CSS and "width:100px; height:100px" in CSS)
# contain, not cover: a listing photo is rarely square and cover crops the sides
# off the one picture on the page.
yes("  fitted, not cropped", "object-fit:contain" in CSS)
yes("gap 14px, padding 0 16px",
    ".pdp-hero-in{" in CSS and "gap:14px" in CSS and "padding:0 16px" in CSS)
yes("title 15px / 600", "font-size:15px; font-weight:600" in CSS)
yes("meta labels 60px", "width:60px" in CSS)
yes("badges 9px, 2px 6px, radius 3px",
    "font-size:9px; padding:2px 6px; border-radius:3px" in CSS)
# THE ONE PLACE THE BRIEF OVERRULES ITS OWN MOCKUP. The mockup's hero carries
# "⚠ 2 warnings"; step 6 says: "Do NOT show the '2 warnings' TEXT. Only show
# warning badges with counts. The warning text line was removed in a previous
# task." The badge is the triangle and the number, and the sentence is on hover.
check("the warning badge is a count, not a sentence",
      re.search(r"' warning' \+ \(w\.n === 1", JS) is not None, False)
yes("  with the wording on hover instead", "lsWarnTip(w)" in JS)

print("\n== STEP 7: the API error, once ==")
yes("the banner is at the top of the content", "pdpApiIssues(r)" in JS)
yes("  and carries the full wording", "i.message" in JS)
# "Do NOT duplicate the full error message next to the field -- the field only
# gets a red border + short one-line summary."
yes("the field gets a short line", "Amazon refused this field" in JS)
check("  not the message again",
      "mine.map(x => '<div>' + esc(x.message" in JS, False)
yes("  with the full text on hover", 'esc(mine.map(x => x.message' in JS)
yes("  and a way back up to the banner", "function pdpScrollToErrors()" in JS)
yes("the box itself is outlined red", ".pdp-attr.apierr .ed," in CSS)

print("\n== STEP 8: the footer ==")
yes("padding 10px 16px", ".pdp-footer{" in CSS and "padding:10px 16px" in CSS)
yes("Cancel and Save and finish", "pdp-footer-cancel" in JS and "pdp-footer-save" in JS)
yes("  with the note on the left", "pdp-footer-note" in JS
    and "Edits save as you leave each box" in JS)
# It WAS sticky. Item 2 of CLAUDE_CODE_PROMPT_v3.md took that away -- it is the
# last flex item of the panel now, which puts it at the bottom of the CARD
# rather than tracking the viewport. See "the bars do not scroll away" above.

print("\n== v3 item 1: the bar arrives with the first change ==")
#     "It should only appear AFTER the user has modified any field. Same
#      pattern as the Save All bar on the listings page -- hidden until a
#      change is detected, then slides in.
#      When no changes have been made: no bar visible."
yes("the bar is always drawn, and hidden by a class", 'PDP_DIRTY ? " on" : ""' in JS)
# Collapsed, not display:none -- nothing slides in from nothing.
# ANCHORED, because ".pdp-top, .pdp-hero, .pdp-tabs, .pdp-footer{ flex-shrink:0 }"
# is written first and contains ".pdp-footer{" too. This codebase's oldest test
# trap: the first match is not the rule you mean.
foot = re.search(r"^\.pdp-footer\{(.*?)\}", CSS, re.S | re.M)
yes(".pdp-footer takes no height until then",
    foot and "max-height:0" in foot.group(1)
         and "padding-top:0" in foot.group(1)
         and "border-top-width:0" in foot.group(1))
yes("  and is off the bottom edge", foot and "transform:translateY(100%)" in foot.group(1))
# ORDER MATTERS INSIDE THE RULE. padding and border-top are set as SHORTHANDS,
# and a shorthand written after a longhand re-sets it. With the collapse first
# the bar measured 21px on screen -- 0 of content plus the padding and border
# the shorthands had put back.
yes("  written after the padding/border shorthands, not before",
    foot and foot.group(1).index("max-height:0") > foot.group(1).index("padding:10px 16px")
         and foot.group(1).index("border-top-width:0") > foot.group(1).index("border-top:1px"))
# A flex item's min-height defaults to its content, and min-height beats
# max-height -- without this the cap does nothing at all.
yes("  with min-height:0 so the cap can apply", foot and "min-height:0" in foot.group(1))
yes("  with something to animate", foot and "transition:max-height" in foot.group(1))
on = re.search(r"\.pdp-footer\.on\{(.*?)\}", CSS, re.S)
yes(".pdp-footer.on brings it back", on and "transform:none" in on.group(1)
    and "padding-top:10px" in on.group(1) and "border-top-width:1px" in on.group(1))
yes("one delegated listener, bound once",
    "function pdpWatchEdits()" in JS and "PDP_DIRTY_BOUND" in JS)
yes("  on input and change", 'host.addEventListener("input", touched)' in JS
    and 'host.addEventListener("change", touched)' in JS)
# Two boxes inside the panel are NOT the listing: the auto-fix suggestion rows
# and the footer's own controls. Typing in those must not raise the bar.
yes("  ignoring the auto-fix rows", 't.closest(".pdp-afrow")' in JS)
yes("  and the footer itself", 't.closest(".pdp-footer")' in JS)
yes("marking dirty reveals it without a re-render",
    'f.classList.add("on")' in JS)
# "When saved or cancelled: bar disappears." Both buttons close the panel.
yes("closing forgets the change", re.search(
    r"function pdpClose\(\)\{(?:(?!\n\}).)*PDP_DIRTY = false", JS, re.S) is not None)
yes("  and so does opening a different listing", re.search(
    r"if\(changed\)\{(?:(?!\n  \}).)*PDP_DIRTY = false", JS, re.S) is not None)

print("\n== STEP 9: no drawer (see test_one_detail_view.js) ==")
LIST = nocomments_js(read("static", "js", "listings.js"))
yes("openDrawer redirects to the product page",
    'function openDrawer(sku, jumpGen){\n  if(typeof pdpOpen === "function"){' in LIST)

print("\n== measured in Chrome, on a real listing ==")
# Read off the live panel at 1600x1000:
#   backdrop  rgba(0,0,0,.6), padding 40px 60px, justify center
#   panel     680 wide, 460px of backdrop each side, radius 10px,
#             shadow 0 8px 40px, align-self flex-start
#   tabs      Product Details | Images | Offer | Safety & Compliance
#   sidebar   130px, 12px 10px, title 9px uppercase, items 11px, checks 10px
#   hero      image 100x100, title 15px/600, meta label 11px/60px,
#             badges 9px / 2px 6px / radius 3px
#   content   12px 16px
#   footer    10px 16px, sticky, Cancel + Save and finish
#   details   23 attribute rows and 1 group heading under the description
#   errors    none
yes("the page is still one render call", "function pdpRender()" in JS)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
