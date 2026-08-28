"""The product card states its facts, and offers fewer ways to do the same thing.

    "no asin in the screenshot opens a product some shows the brand name and
     some do not show the brand name, i want the brand name to be displayed in
     all, make the selling price being able to be changed by just clicking on
     it and then on save, reflect true handling time in front of the listings
     and remove that change the listings selling price button which is already
     there on the product card and also remove that edit button, as we can
     directly edit the listing by clicking on the product card. delete that
     auto fix button... i see a button that says open this listing on amazon
     remove that button as we should be able to open the listing by clicking on
     the green asin and make that search bar long"

Four of those are one defect wearing four hats: the card carried a BUTTON for
something the card itself should already do. Clicking a card, clicking an ASIN
and clicking a price are the obvious gestures, and each had a separate icon
because the obvious gesture did nothing.

brand.js is exercised for real through node -- it is small, pure and decides
which brand Amazon receives, which is not a thing to check by grepping for a
string.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*parts):
    return open(os.path.join(HERE, *parts), encoding="utf-8").read()


LJ = read("static", "js", "listings.js")
MT = read("static", "js", "miles_template.js")
BR = read("static", "js", "brand.js")
CSS = read("static", "css", "dashboard.css")
OPT = read("routes", "optimize_routes.py")

# ===================================================================
print("== which brand, decided once and actually run ==")
# brand.js is pure and has no DOM in it, so node can run the real thing rather
# than us asserting on its source and hoping.
NODE_SRC = BR + """
const out = [];
function t(label, got, want){ out.push([label, got, want]); }

CUR_ACCOUNT = {id:"nestwell", label:"Nestwell Goods",
               brands:["AltaboltaVoo", "Green Haven"]};
t("row brand wins",            rowBrand({brand:"Green Haven"}).name,  "Green Haven");
t("row brand is from the row", rowBrand({brand:"Green Haven"}).from,  "row");
t("blank row falls back",      rowBrand({}).name,                     "AltaboltaVoo");
t("and says it is a default",  rowBrand({}).from,                     "account");
// "i am trying to put the brand name as AltaboltaVoo ... my nestwell goods
//  account has that brand name approved ... but the app says Amazon flagged
//  this". Case must not decide whether an approved trademark is recognised.
t("case does not unapprove a brand", rowBrand({brand:"altaboltavoo"}).ours, true);
t("ALL CAPS likewise",               rowBrand({brand:"ALTABOLTAVOO"}).ours, true);
t("a brand we are not registered for is marked",
  rowBrand({brand:"Sony"}).ours, false);
t("  but it is still shown, not swallowed", rowBrand({brand:"Sony"}).name, "Sony");
t("whitespace is not a brand",  rowBrand({brand:"   "}).from,          "account");

// No trademarks recorded: the label is the fallback, and nothing is "not ours"
// -- with no list to check against, flagging every brand would be noise.
CUR_ACCOUNT = {id:"x", label:"Jack Reacherd", brands:[]};
t("no trademarks -> the label", rowBrand({}).name,                 "Jack Reacherd");
t("  and no brand is flagged",  rowBrand({brand:"Anything"}).ours,  true);

// No account open at all must not throw -- this runs during first paint.
CUR_ACCOUNT = null;
t("no account is empty, not an error", rowBrand({}).name, "");
t("  and the row still wins",          rowBrand({brand:"Selvora"}).name, "Selvora");

console.log(JSON.stringify(out));
"""
_tmp = os.path.join(HERE, "_brand_probe.js")
try:
    open(_tmp, "w", encoding="utf-8").write(NODE_SRC)
    _p = subprocess.run(["node", _tmp], capture_output=True, text=True, timeout=60)
    if _p.returncode != 0:
        fails.append("brand.js would not run under node")
        print("  FAIL node:", (_p.stderr or "")[:400])
    else:
        for label, got, want in json.loads(_p.stdout.strip().splitlines()[-1]):
            check(label, got, want)
finally:
    try:
        os.remove(_tmp)
    except OSError:
        pass

print("\n== and the six hand-written copies of it are gone ==")
# CUR_ACCOUNT.brands[0] : CUR_ACCOUNT.label was written out by hand in six
# files. Six places to fix when the rule changes, on the one field that decides
# whether Amazon takes the listing (rule 12).
for f in ("asinresearch.js", "genimage.js", "miles_template.js",
          "pastelisting.js", "studiopicker.js"):
    src = read("static", "js", f)
    falsy("%s no longer picks the brand itself" % f, "CUR_ACCOUNT.brands[0]" in src)
    truthy("  it asks brand.js", "accountBrand()" in src)
truthy("and brand.js is loaded before anything that calls it",
       "/static/js/brand.js" in read("templates", "dashboard.html"))

# ===================================================================
print("\n== the card no longer needs a button to do what the card does ==")
falsy("no Edit button -- the card opens the editor",   "title=\"Edit / details\"" in LJ)
falsy("no Auto-fix button on the card",                "autoFixLoop('${sku}')" in LJ)
falsy("no change-price button on the card",            "Change this listing's selling price" in LJ)
falsy("no open-on-Amazon button on the card",          "title=\"Open this listing on Amazon\"" in LJ)
falsy("  nor on the live table row",                   "title=\"View on Amazon\"" in LJ)
falsy("  nor a second change-price button there",      "Change what this sells for on Amazon" in LJ)

print("\n== but every one of those actions still has a way in ==")
# Removing the last route to a feature is not a cleanup, it is a deletion.
truthy("Auto-fix is still in the drawer",  "onclick=\"autoFixLoop(" in LJ)
truthy("Edit is still in the More menu",   "Edit details" in LJ)
truthy("Edit is still the whole card",     "class=\"tilebody\" onclick=\"openDrawer(" in LJ)
truthy("the price panel is still what sends a price", "priceEdit('" in LJ)
truthy("and the table row keeps its Review button",   ">Review</button>" in LJ)
# The way IN to Amazon is the ASIN itself -- "we should be able to open the
# listing by clicking on the green asin". The card lost its button; the drawer
# header's ASIN is a link. Asserted so the button's removal can never quietly
# take the last route with it.
truthy("and the drawer header's ASIN opens Amazon",
       'class="dw2-asin" href="https://www.amazon.' in LJ)

print("\n== the green ASIN is the link the icon always promised ==")
# It carried a ti-external-link icon inside a plain <span>: an icon promising
# something the element could not do.
truthy("the draft row's ASIN is an anchor", "<a class=\"asin\" href=" in LJ)
check("both row kinds link it", LJ.count("<a class=\"asin\" href="), 2)
truthy("  it stops the row's own click",
       "onclick=\"event.stopPropagation()\" style=\"text-decoration:none\"" in LJ)
truthy("  and the live tile linked it already", "_dpUrl(it.asin)" in MT)

print("\n== clicking a card opens the listing, whichever kind of card ==")
truthy("a live tile opens the live editor", "onclick=\"optimizeLive(" in MT)
truthy("a live table row does too",
       "const _open = `optimizeLive(" in LJ)
falsy("  and no longer renders itself un-clickable",
      '<tr style="cursor:default"' in LJ)

# ===================================================================
print("\n== the price is the control ==")
truthy("there is one price cell", "function _priceCell(" in LJ)
truthy("  a live price opens the price panel", "pricehot" in LJ and "priceEdit(" in LJ)
truthy("  and looks like a control",  ".pricehot{cursor:pointer" in CSS)
# A draft has no price on Amazon to change, so it must not offer to change one.
truthy("a draft price is not clickable",
       "This listing is not live on Amazon, so there is no selling price to change" in LJ)
# The panel is kept because it is the only thing that names the account on the
# request -- an in-card input would be a thinner second path to the same write.
truthy("and the reason the panel is kept is written down",
       "WRONG SELLER ACCOUNT" in LJ)

print("\n== the handling time is the one the buyer is actually promised ==")
truthy("there is one handling cell", "function _handCell(" in LJ)
# handling_days is what WE hold for a draft; handling_time is what Amazon
# reports for a live listing. The old code took whichever was set first and
# labelled neither, so a stale draft value could sit in front of a live
# listing looking like fact.
falsy("no first-one-wins between ours and Amazon's",
      "r.handling_days || r.handling_time" in LJ)
truthy("Amazon's number wins on a live listing",
       "what buyers are being promised now" in LJ)
truthy("  and ours is marked as ours", "(ours)" in LJ)
truthy("the live table row shows one at all", "_handCell(_r, true)" in LJ)
falsy("  instead of the dash it used to print",
      "<td><span class=\"cc\">—</span></td>\n    <td><span class=\"badge b-LIVE\">" in LJ)
# FBA's "0 days handling" is this code's assumption, not Amazon's figure, and
# the ship-by date hid that completely.
truthy("an assumed handling time says it is assumed", "(assumed)" in MT)

print("\n== and Amazon's figure is actually fetched, not just labelled ==")
# MEASURED, not assumed. 46 of 47 live listings arrived with no handling time
# at all, because the catalogue is built from GET_MERCHANT_LISTINGS_ALL_DATA
# and that report has no handling column -- the 30 columns Amazon really sends
# were dumped and read (rule 4). will-ship-internationally looked like a
# candidate at 3-on-every-row until SKUs named 2Days and 5Days also read 3.
DASH = read("dashboard.py")
LR = read("routes", "live_routes.py")
truthy("the report's missing column is recorded where somebody would look",
       "there is NO handling-time column" in DASH)
truthy("  including why the obvious candidate is not it",
       "will-ship-internationally" in DASH)
falsy("  and nobody has hopefully added one anyway",
      '"handling", "handling-time"' in DASH)
truthy("the catalogue carries the figure the image path already fetched",
       "def _attach_handling(" in LR)
truthy("  from the cache, costing no extra Amazon call", "_IMG_CACHE.get(" in LR)
# The catalogue is usually served from the durable snapshot and never rebuilt,
# so attaching this at FETCH time would have been dead code on the common path
# -- the same reason _attach_compliance runs on the way out.
check("it runs on every path that serves items, not just a fresh fetch",
      LR.count("_attach_handling("), LR.count("_attach_compliance("))
truthy("  including the snapshot path", "_attach_handling(_rec.get(\"items\")" in LR)

print("\n== a disagreement about the promise is shown, not averaged away ==")
# Sampled through getListingsItem: Amazon held lead_time_to_ship_max_days = 2
# on three SKUs named 2Days, 3Days and 5Days. The SKU's label is what was
# intended at creation; Amazon's number is what buyers are promised, and
# nothing had ever compared the two.
truthy("the two numbers are compared", "const clash =" in LJ)
truthy("  Amazon's is the one shown when they differ",
       "Amazon is promising buyers" in LJ)
truthy("  and ours is still named, not hidden", "(we hold" in LJ)
truthy("  with the reason it matters", "late-dispatch" in LJ)

print("\n== the brand is stated on every card ==")
truthy("there is one brand cell", "function _brandCell(" in LJ)
falsy("no more show-it-only-if-set", "${r.brand?`<span class=\"brand pii\">" in LJ)
truthy("the draft tile states it",     "_brandCell(r)" in LJ)
truthy("the live tile states it",      "_brandCell(it)" in MT)
truthy("the table rows state it",      LJ.count("_brandCell(") >= 3)
truthy("an account default is labelled as one", "(account default)" in LJ)

# ===================================================================
print("\n== one action row, so grid and list cannot drift apart again ==")
# The live TABLE row had Sync and Add-variant; the live TILE did not. Same
# listing, two views, different things you could do to it.
truthy("Sync comes from rowActions now",       "syncForSku('${sku}')" in LJ)
truthy("Add variant too",                      "addVariant('${sku}')" in LJ)
truthy("the live table row calls rowActions",  "rowActions(_r, \"dotb\", {live: true})" in LJ)
# Approve set a draft's status to "ready to send". On a listing Amazon has
# already published there is nothing to approve -- and on a catalogue-only card
# there is not even a row to set it on.
truthy("Approve is offered on drafts only", "Approve — mark this draft ready to send" in LJ)
truthy("  and live cards get Sync in its place", "APPROVE IS FOR DRAFTS" in LJ)

print("\n== the search bar takes the room it was leaving empty ==")
falsy("the 420px cap is gone", "min-width:260px;max-width:420px" in CSS)
truthy("  it grows with the toolbar", "flex:1 1 420px" in CSS)
truthy("  and still survives a narrow window", "min-width:260px" in CSS)

# ===================================================================
print("\n== Optimize does not report a success it did not verify ==")
#     "what is this optimize listing copy button, do it works correctly i am
#      not sure check it"
# It works: fetch the live listing, rewrite, push back only the approved fields
# behind a confirm flag. But it could CLAIM a push succeeded when it had not
# read Amazon's answer:
#
#     ok = status.upper() in ("ACCEPTED", "VALID") or not issues
#
# An empty status with no issues -- what you get if the payload arrives in an
# unexpected shape -- came out ok=True, and the browser printed "Submitted to
# Amazon (accepted)", supplying the word "accepted" itself.
truthy("the push is still gated on an explicit confirm", 'b.get("confirmed")' in OPT)
truthy("  and refuses read-only workspaces",             "_require_publish()" in OPT)
truthy("  and sends only approved fields",               "_build_patches(changes)" in OPT)
# Line-based, because the old expression is quoted in the comment that explains
# why it went. A comment recording the defect is not the defect.
_code = [l.split("#")[0].strip() for l in OPT.splitlines()]
falsy("an unread reply is no longer a success",
      any(l.startswith("ok =") and "or not issues" in l for l in _code))
truthy("only Amazon's own yes counts",
       '_s in ("ACCEPTED", "VALID")' in OPT)
truthy("  and an unreadable reply is reported as unknown", '"unknown": unknown' in OPT)
falsy("the browser no longer invents the word accepted", 'j.status||"accepted"' in MT)
truthy("  it says it cannot tell, and how to settle it",
       "cannot tell you whether it was applied" in MT)
truthy("  which is Sync, because Sync reads the listing back",
       "reads the listing back from Amazon" in MT)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
