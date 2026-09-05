"""The PDP against altascraper-pdp-mockup.html, and what it lets you edit.

    "i want to match my pdp exactly like this, size color font pixels boxes
     style grey text over boxes, relative position, layout, every single bit of
     it identical and in working condition"

    "that mockup donot contain the description as scrollable so make it
     scrollable when there is more text than the box"

    "some things can not be changed like brand check amazon answer if it can be
     changed or not when the listing is live on amazon and make the boxes
     editable or not according to it, and also you know in draft everything is
     changeable, but we also have dependencies of the fields to one another and
     conditions stored in the code so respect them"

Every colour and size below is READ OUT OF THE MOCKUP at run time, so this moves
with the file rather than going quietly out of date.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-60s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with io.open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


MOCK = read("altascraper-pdp-mockup.html")
CSS = re.sub(r"(?s:/\*.*?\*/)", "", read("static", "css", "pdp.css"))
DRAW = re.sub(r"(?s:/\*.*?\*/)", "", read("static", "css", "drawer.css"))
AF = re.sub(r"(?m:^[ \t]*//[^\n]*)", "",
            re.sub(r"(?s:/\*.*?\*/)", "", read("static", "js", "autofix.js")))

# The mockup's :root, read rather than copied.
ROOT = dict(re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", MOCK.split(":root {")[1].split("}")[0]))
print("mockup :root carries %d tokens" % len(ROOT))

print("\n== the palette is the mockup's, token for token ==")
# The page used to be drawn in the drawer's BLUES, from a different mockup. That
# was a deliberate choice and it is overruled by the instruction above.
PAIRS = [("--pdp-bg", "bg"), ("--pdp-panel", "panel"), ("--pdp-raise", "panel2"),
         ("--pdp-input", "sidebar"), ("--pdp-line", "line"),
         ("--pdp-ink", "ink"), ("--pdp-ink2", "ink2"), ("--pdp-ink3", "ink3"),
         ("--pdp-faint", "ink4"), ("--pdp-accent", "accent"),
         ("--pdp-link", "link"), ("--pdp-ok", "ok"), ("--pdp-warn", "warn")]
tok = CSS[CSS.index("#pdp{"):CSS.index("}", CSS.index("#pdp{"))]
for ours, theirs in PAIRS:
    want = ROOT.get(theirs, "").strip()
    m = re.search(re.escape(ours) + r"\s*:\s*([^;]+);", tok)
    got = (m.group(1).strip() if m else None)
    check("%-14s = mockup --%s" % (ours, theirs), got, want)
# THE ACCENT IS THE ONE THAT SHOWS. Everything lit -- the active tab, the save
# button, a focus ring -- was the old blue.
check("  and the accent is the teal, not the old blue",
      "#3b7dd4" in CSS or "#4a8ce0" in CSS, False)
# The base type: the mockup's body is 12px/1.45; dashboard.css sets 14px/1.5 on
# the page underneath and every unstyled line inherited it.
yes("the base type is the mockup's 12px/1.45",
    "font-size:12px; line-height:1.45;" in tok)

print("\n== the surfaces are the mockup's way round ==")
# The mockup's INPUTS are --sidebar, DARKER than the card. They were --raise,
# lighter -- boxes standing off the card instead of cut into it, which is most
# of why the two did not look alike.
yes("the card is --panel and carries no border",
    "background:var(--pdp-panel);\n  border-radius:10px;" in CSS)
for bar in ("padding:8px 16px; background:transparent;",):
    yes("the top bar is transparent over the card", bar in CSS)
yes("  so is the hero", "background:transparent; border-bottom:1px solid var(--pdp-line); padding:12px 0;" in CSS)
yes("  and the tab row", "background:transparent; border-bottom:1px solid var(--pdp-line);" in CSS)
yes("the boxes are cut in, not raised", CSS.count("var(--pdp-input)") >= 5)
yes("  and the footer sits on the same dark", "background:var(--pdp-input);" in CSS)

print("\n== the mockup's own numbers ==")
def mockrule(sel):
    m = re.search(r"(?m)^" + re.escape(sel) + r"\{([^}]*)\}", MOCK)
    return " ".join(m.group(1).split()) if m else ""
_tab = mockrule(".pdp-tab")
yes("the tab is 8px 14px", "padding:8px 14px" in _tab and "padding:8px 14px" in CSS)
yes("  and weight 400, not bolded", "font-weight:400; color:var(--pdp-ink3);" in CSS)
yes("  lit tab is accent text AND an accent underline",
    ".pdp-tab.active{ color:var(--pdp-accent); border-bottom-color:var(--pdp-accent); }" in CSS)
_chk = mockrule(".pdp-check")
yes("the check row is a line with a dot, not a pill",
    "padding:5px 8px" in _chk and "background:none; border:none;" in CSS)
yes("  the verdict is carried by colour alone",
    ".pdp-ck.ok{   color:var(--pdp-ok); }" in CSS)

print("\n== the description scrolls; the bullets still grow ==")
#     "make it scrollable when there is more text than the box"
_ed = re.search(r"\.pdp-content \.dw2-edit\{([^}]*)\}", CSS)
yes("the copy boxes have the mockup's 80px floor", _ed and "min-height:80px" in _ed.group(1))
yes("  a ceiling", _ed and "max-height:240px" in _ed.group(1))
yes("  and scroll rather than grow past it", _ed and "overflow-y:auto" in _ed.group(1))
# THE OPPOSITE OF THE BULLETS, on purpose: a bullet is 500 characters and is
# judged whole; a description is four times that and would push the footer off.
yes("the bullets still grow to fit", "field-sizing:content;" in CSS)

print("\n== what Amazon lets you change ==")
#     "check amazon answer if it can be changed or not when the listing is live"
yes("the identity boxes ask before drawing an editor", "const _lockOn = (col)" in AF)
# 1. AMAZON'S OWN ANSWER FIRST -- the product type definition's read-only list,
#    which arrives with the schema and which these boxes never consulted.
yes("  the product type's read-only list is consulted",
    "const _roList = sc.readonly || [];" in AF
    and "_roList.indexOf(attr) >= 0" in AF)
yes("  through the same column->attribute map the banner uses",
    'const _COL_ATTR = {"Brand":"brand", "UPC":"externally_assigned_product_identifier"};' in AF)
# 2. AND WHETHER IT IS LIVE. A draft is ours; once the ASIN exists the brand and
#    the identifier belong to Amazon's catalogue, not to our offer.
yes("  and whether the listing is live", "const _live = (typeof lsInLiveCatalogue" in AF)
yes("  which is the shared answer, not a status string compare",
    "lsInLiveCatalogue(r)" in AF)
yes("the lock says WHICH rule locked it", "Amazon marks this read-only for" in AF
    and "belongs to the ASIN in Amazon's catalogue" in AF)
# A SPAN, NOT A DISABLED INPUT: the value is what you opened the listing to
# read, and a greyed box with no explanation reads as a broken field.
yes("a locked field still shows its value", "const _roCell = (val, why)" in AF
    and 'class="dw2-ro"' in AF)
yes("  with the padlock the mockup draws", "ti ti-lock dw2-rolock" in AF)
yes("  styled as the mockup's readonly row", ".dw2-ro{" in DRAW
    and "background:var(--panel2);" in DRAW and "color:var(--ink3);" in DRAW)
# NOT LOCKED WHEN LIVE: the copy and the offer are what this app exists to
# change, and Amazon takes both on a live listing. The invariant is the MAP --
# only what is on it can ever be locked by this rule, so checking its contents
# checks every field at once rather than three of them.
_map = re.search(r"const _COL_ATTR = \{([^}]*)\}", AF)
_locked_cols = sorted(re.findall(r'"([^"]+)"\s*:', _map.group(1) if _map else ""))
check("only the two identity columns can be locked", _locked_cols, ["Brand", "UPC"])
# The title is edited in the hero (drawer.js dwTitleParts), the price and
# handling in the offer rows -- none of them passes through _lockOn at all.
yes("  the title editor is untouched by it",
    'dwBlurSave(this,\\\'\' + esc(r.sku) + \'\\\',\\\'col\\\',\\\'Title\\\')'
    in read("static", "js", "drawer.js")
    or "'col','Title'" in read("static", "js", "drawer.js"))
yes("  and the price and handling boxes are still editCell",
    'editCell(sku,"col","Our Price (GBP)"' in AF
    and 'editCell(sku,"col","Handling Days"' in AF)

# MEASURED IN CHROME, mockup and app side by side at 1600x900:
#   draft 7.96_3Days_B0841BD4JY  brand editable, barcode editable
#   live  9.18_3Days_B0C6XTNXL8  both locked, padlock shown, reason on hover
#   no page errors on either
print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
