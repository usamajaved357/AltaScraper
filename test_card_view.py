"""CARD_VIEW_FIX.md: the grid view's images, warnings and consistency.

THE IMAGES WERE NOT BEING STRETCHED OR CROPPED. object-fit:contain has been on
them the whole time, and contain cannot crop. What was happening is worse and
explains why it looked random:

    .tileimg is display:flex.
    _warnChip and _queuedChip returned a .tilefact, which is inline-flex.
    Neither was positioned.

So on a card that had a warning, the text span became a FLEX ITEM BESIDE the
<img width:100%> and the browser squeezed the picture sideways to make room for
it. Every other overlay in that box -- .tiledot, .tilesel, .tileflag,
.tileclaim, .tileinactive -- is position:absolute; those two were the
exceptions. That is why it was "the first few cards": the first few are the
ones carrying warnings.

Removing the "N warnings" TEXT, which is what the brief asks for, therefore also
fixes the images. The two items were one bug.

THE SECOND HALF OF "INCONSISTENTLY FORMATTED" is that the Live tab draws TWO
kinds of card in one grid -- one from an app row (listings.card) and one from
Amazon's catalogue (miles_template.liveTile) -- and the second has always shown
a .profchip that the first did not have at all. Adding a third look would have
made it worse; the draft card now draws the same chip with the same bands.
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
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def rd(p):
    return io.open(os.path.join(HERE, *p.split("/")), encoding="utf-8").read()


LS = rd("static/js/listings.js")
LSTAT = rd("static/js/liststatus.js")
MT = rd("static/js/miles_template.js")
CSS = rd("static/css/dashboard.css")
ICONS = rd("static/vendor/tabler-icons/tabler-icons.min.css")


def fn(src, name):
    i = src.find("function " + name + "(")
    if i < 0:
        return ""
    j = src.find("\n}", i)
    return src[i:] if j < 0 else src[i:j + 2]


def rule(css, sel):
    i = css.find(sel)
    return css[i + len(sel):css.find("}", i)] if i >= 0 else ""


print("=== 1 and 2. the text in front of the picture ===")
CARD = fn(LS, "card")
# THE PICTURE BOX IS A FLEX CONTAINER, which is the whole mechanism.
truthy(".tileimg is a flex row", "display:flex" in rule(CSS, ".tileimg{"))
truthy("  and .tilefact is inline-flex, so it would be an item in it",
       "display:inline-flex" in rule(CSS, ".tilefact{"))
# So nothing unpositioned may be placed inside it.
_img = CARD[CARD.find('class="tileimg'):CARD.find('class="tilebody')]
# THE WARNING MARK IS GONE ALTOGETHER NOW, badge and all.
#
#     "there is still a symbol saying 1 warning worst: medium. i dont want this
#      symbol at all, i already have 3 symbols for restricted compliance and
#      claims risk, i will maintain those"
#
# This section used to pin the badge's SHAPE -- positioned, count kept, words on
# hover -- which was the right answer to the previous brief and is now the wrong
# question. What it pins instead is that nothing draws it.
falsy("no warning mark is placed inside the picture box", "_warnChip(r)" in _img)
falsy("  _warnChip is gone", "function _warnChip" in LS)
falsy("  and so is its badge class", ".tilewarn{" in CSS)
# THE THREE THAT STAY, and the reason the fourth was redundant: each of these
# names WHICH risk, where the count named none.
truthy("the restricted flag stays", "tileflag" in CARD)
truthy("  the claims-risk badge stays", "claimBadge(r)" in CARD)
truthy("  the viability badge stays", "viabilityBadge(r)" in CARD)
# THE OTHER UNPOSITIONED ONE moved out of the picture box too.
truthy("the queued chip moved to the facts line",
       "${_brandCell(r)}${_handCell(r)}${_queuedChip(r)}" in CARD)
falsy("  and is no longer over the image", "_queuedChip(r)" in _img)
truthy("the mechanism is written down where the next person will look",
       "FLEX ITEM BESIDE THE <img>" in LS)

print("\n=== the picture is its own shape, on a square of the panel ===")
truthy("the box is a 1:1 ratio", "aspect-ratio:1/1" in rule(CSS, ".tileimg{"))
falsy("  not a fixed pixel height", "height:180px" in rule(CSS, ".tileimg{"))
truthy("  on the panel colour", "background:var(--panel2)" in rule(CSS, ".tileimg{"))
# THE WHITE WAS BEHIND THE WHOLE BOX, not behind the picture: the <img> element
# filled the square and was painted white, so a photo sat in a white rectangle
# on a charcoal card.
_i = rule(CSS, ".tileimg img{")
# MEASURED IN A BROWSER: auto sizing collapses an <img> that has not loaded to
# 0x0, and two of the first eight tiles rendered that way -- the same complaint
# in a new form. 100% gives it the box whether or not the bytes have arrived.
truthy("the image fills the box", "width:100%" in _i and "height:100%" in _i)
truthy("  never cropped or stretched", "object-fit:contain" in _i)
falsy("  and the element is not painted white", "background:#fff" in _i)
truthy("  the surround is the panel", "background:var(--panel2)" in rule(CSS, ".tileimg{"))
truthy("  with the browser measurement recorded", "lays out at 0x0" in CSS)

print("\n=== 5. the no-image placeholder ===")
truthy("a struck-through camera, not a plain one", "ti-photo-off" in CARD)
# AN ICON THE FONT DOES NOT HAVE RENDERS AS AN EMPTY BOX, silently.
truthy("  and that glyph is in the subset this app ships", ".ti-photo-off" in ICONS)
truthy("said in words as well", 'content:"No image"' in CSS)
truthy("  and the failed-to-load path lands in the same state",
       "classList.add('noimg')" in CARD)
# The live tile writes its own longer caption; one caption, not two stacked.
truthy("the live tile's own wording is not doubled up",
       ":has(.noimgmsg)::after{content:none}" in CSS)

print("\n=== 3. one card format, not two in one grid ===")
# BOTH KINDS OF CARD APPEAR TOGETHER on the Live tab.
truthy("the live tile draws a profit chip", "profchip" in MT)
truthy("  and the draft card now draws the same one", "profchip" in fn(LS, "_econLine"))
truthy("  with the same margin bands", "margin >= 25" in fn(LS, "_econLine")
       and "margin>=25" in MT)
truthy("  and the same three figures",
       all(w in fn(LS, "_econLine") for w in ("margin ", "ROI ")))
falsy("no third chip class was invented", "tileecon" in LS)
truthy("the line is on the draft card", "${_econLine(r)}" in CARD)
# NOTHING IS SHOWN WITHOUT A PROFIT FIGURE -- a margin from a missing cost is
# the "free stock looks infinitely profitable" mistake in another form.
truthy("no profit means no line", 'String(r.profit || "").trim() === ""' in fn(LS, "_econLine"))
truthy("  and ROI is skipped when the cost is unknown",
       "cost != null && cost > 0" in fn(LS, "_econLine"))
truthy("the profit is the stored one, not re-derived from a fee guess",
       "r.profit" in fn(LS, "_econLine"))

print("\n=== 4. the buttons line up across a row ===")
_a = rule(CSS, ".tileacts{")
truthy("the action row is pinned to the bottom", "margin-top:auto" in _a)
truthy("  and separated from the facts", "border-top" in _a)
# NOT rule(CSS, ".tile{") -- the first match of that selector is the SVG mark in
# the app bar (`.appbar .brandmark .amark .tile{fill:...}`), which is a rectangle
# in the logo. Exactly the trap that let the density pass assert the wrong
# main#grid; matched on the rule's own content instead.
_tile = re.search(r"\n\s*\.tile\{([^}]*background:var\(--panel\)[^}]*)\}", CSS)
truthy("the card is a column",
       _tile is not None and "flex-direction:column" in _tile.group(1))
truthy("  whose body takes the slack", "flex:1" in rule(CSS, ".tilebody{"))
# Both kinds of card share every one of those classes, which is what makes them
# the same height and the same shape.
for cls in (".tileimg", ".tilebody", ".tileacts", ".tiletitle", ".tilemeta"):
    truthy("the live tile shares %s" % cls, cls.lstrip(".") in MT)

print("\n=== what was NOT to change ===")
truthy("the action buttons are still rowActions", 'rowActions(r, "ib")' in CARD)
truthy("  on the live tile too", 'rowActions(' in MT)
truthy("the warning ICON is kept where it names a risk",
       "ti-alert-triangle" in fn(LS, "card"))
# The table's cell went with the card's badge -- both were the same count, and
# leaving one would have answered the complaint on one screen out of four.
falsy("the table's warning cell went too", "function _warnCell" in LS)
# WHAT IS NOT REMOVED: the checks themselves, and the full list in the detail
# view. A badge was taken off the screen; nothing stopped being checked.
truthy("lsWarnings still decides the counts", "function lsWarnings" in LSTAT)
truthy("  and the Safety & Compliance tab still lists every message",
       "function _dwWarnings" in LS)

print("\n=== one header over the whole list, found in a browser ===")
# MEASURED ON THE REAL DRAFTS SCREEN: 16 <th> over a 40-row list -- two full
# headers and two bordered boxes. listBlock opens its own card with its own
# header, and the drafts path called it twice (queued, then generated). It is
# the same complaint the live view had -- "why do i have two separate
# boxes/borders containing the listings?" -- fixed there with listBlocks() and
# never carried across.
MT = rd("static/js/miles_template.js")
truthy("the drafts view draws its groups under one header",
       "listBlocks([{rows: _queuedAll}, {rows: _draftsAll}])" in MT)
truthy("  and so does the Drafts tab's own branch",
       "listBlocks([{rows: queuedRows}, {rows: draftsOnly}])" in MT)
# Against the CODE: the comment above the fix names the calls that were there,
# which is the record of what went wrong.
_mt = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", MT, flags=re.S))
falsy("  neither calls listBlock for those groups separately",
      any(c in _mt for c in ("listBlock(_queuedAll)", "listBlock(_draftsAll)",
                             "listBlock(queuedRows)", "listBlock(draftsOnly)")))
# THE SENTENCE STAYS. It explains why some rows look empty; what went is the
# heading over a second bordered card. The rows keep their own badge.
truthy("the queued explanation is kept", "not generated yet" in MT)
truthy("  and the rows are still marked individually", "_queuedChip(r)" in LS)
truthy("  with the browser measurement recorded", "16 <th> on a 40-row list" in MT)

print("\n=== a closed fold is closed ===")
# ALSO FOUND IN A BROWSER, on the same screen and for the same visible symptom.
# The "N listings not confirmed by Amazon" group reported open === false and its
# ten rows were on screen anyway, in a second bordered card with a second table
# header. The browser hides a closed disclosure's children at user-agent weight;
# `.card{display:flex}` on the child beats it with one class. Nothing about that
# rule is wrong -- it cannot know it is inside a <details>.
truthy("closed means closed, for every details in the app",
       "details:not([open]) > *:not(summary){ display:none !important; }" in CSS)
_cssflat = re.sub(r"\s+", " ", re.sub(r"^\s*\*\s?", "", CSS, flags=re.M))
truthy("  and the specificity trap is written down", "carrying only user-agent weight" in _cssflat)
# The rule it is competing with is still there and still correct.
_card = re.search(r"\n\s*\.card\{([^}]*background:var\(--panel\)[^}]*)\}", CSS)
truthy("  the .card display rule is untouched",
       _card is not None and "display:flex" in _card.group(1))

print("\n=== nothing is half-written ===")
check("dashboard.css braces balance", CSS.count("{"), CSS.count("}"))
falsy("no mojibake", re.search(r"â€|Â·|â•", LS + CSS) is not None)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
