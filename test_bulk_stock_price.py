"""Selecting listings, and changing stock and price on all of them at once.

    "i dont have any option to update the quantity of the items ... i want to
     select the products of which i want to update the quantity and then select
     it like we set handling time for many items at once"

    "increasing the seller price should be allowed to be updated by percentage.
     e.g. increase or decrease the selling price by this percent."

    "i am not able to select all the listings by clicking on that white button
     ... only 2 listings are allowed to be selected when i select the live on
     amazon tab"

THE TWO SELECTION COMPLAINTS ARE ONE BUG. selectAllVisible walked ROWS -- the
listings this app holds -- while the Live on Amazon tab draws TWO collections:
the app rows Amazon confirmed, and LIVE_ITEMS, which is Amazon's own catalogue
and is most of that view. Two listings existed in both; everything else existed
only in the catalogue. So "Select all" ticked two out of a screenful.

Re-deriving the visible list is what caused it: render() decides what to draw
from LIST_SOURCE, the filter, the dedupe between the collections and the
live/claimed/gone split, and a second attempt at that answer is a copy that can
disagree. It asks the GRID now.

STOCK IS THE SAME AMAZON ATTRIBUTE AS HANDLING TIME. fulfillment_availability
carries quantity and lead_time_to_ship_max_days together and Amazon replaces the
whole array on a patch, so a separate quantity writer would silently undo the
handling time every time -- which is why there is one module, not two (Rule 12).

A PERCENTAGE IS NOT A PRICE. "+10%" is a different number on every listing, so
the preview works each one out and the apply sends THOSE FIGURES rather than the
percentage again -- otherwise somebody approves a table and different numbers go
out, off prices that may have moved in between.
"""
import ast
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def read(*p):
    return open(os.path.join(*p), encoding="utf-8").read()


print("=== select all asks the grid, not one of the two collections ===")
PROBE = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.addEventListener = function(){};

// A grid holding BOTH kinds of card: two app rows, and six of Amazon's own
// catalogue tiles. This is the shape that produced "only 2 selected".
const tiles = [];
for(let i = 1; i <= 2; i++) tiles.push({sku: "APP-" + i, kind: "tile"});
for(let i = 1; i <= 6; i++) tiles.push({sku: "CAT-" + i, kind: "tile live"});
const nodes = tiles.map(t => ({
  _sku: t.sku,
  getAttribute: k => (k === "data-sku" ? t._sku || t.sku : null),
  querySelector: sel => ({type: "checkbox"})
}));
// One extra container that carries a data-sku but offers no tick -- it must be
// ignored rather than selected.
nodes.push({getAttribute: k => (k === "data-sku" ? "NOTICKABLE" : null),
            querySelector: () => null});

globalThis.document = {
  getElementById: () => null,
  querySelectorAll: function(sel){
    return (sel === '#grid [data-sku]') ? nodes : [];
  },
  createElement: () => ({innerHTML: "", querySelector: () => null}),
  addEventListener(){}
};
globalThis.SELECTED = new Set();
globalThis.ROWS = [{sku: "APP-1"}, {sku: "APP-2"}];   // the sheet knows only two
globalThis.passFilter = () => true;
globalThis.isEmptyRow = () => false;
globalThis.render = function(){};
globalThis.updateSelBar = function(){};
globalThis.toast = function(m){ globalThis._toast = m; };

const src = fs.readFileSync("static/js/listings.js", "utf8");
const grab = function(name){
  const i = src.indexOf("function " + name + "(");
  if(i < 0) throw new Error("missing " + name);
  let d = 0;
  for(let k = src.indexOf("{", i); k < src.length; k++){
    if(src[k] === "{") d++;
    else if(src[k] === "}"){ d--; if(!d) return src.slice(i, k + 1); }
  }
  throw new Error("unbalanced " + name);
};
vm.runInThisContext(grab("visibleSelectableSkus") + "\n" + grab("selectAllVisible"));

const out = {};
out.visible = visibleSelectableSkus();
selectAllVisible(true);
out.afterAll = Array.from(SELECTED).sort();
selectAllVisible(false);
out.afterClear = Array.from(SELECTED);

// Nothing drawn yet: say so rather than doing nothing silently.
globalThis.document.querySelectorAll = () => [];
globalThis._toast = "";
selectAllVisible(true);
out.emptyToast = globalThis._toast;
console.log(JSON.stringify(out));
"""
try:
    fd, p = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, PROBE.encode("utf-8"))
    os.close(fd)
    r = subprocess.run(["node", p], capture_output=True, text=True, cwd=HERE,
                       encoding="utf-8")
    os.unlink(p)
    if r.returncode != 0:
        FAILS.append("listings.js threw")
        print("  FAIL listings.js threw:", (r.stderr or "")[:400])
    else:
        g = json.loads(r.stdout.strip().splitlines()[-1])
        # THE HEADLINE. Eight on screen, eight selected -- not the two the sheet
        # happens to know about.
        check("every listing on screen is selected, not just the app's own",
              len(g["afterAll"]), 8)
        check("  the catalogue-only tiles are included",
              [s for s in g["afterAll"] if s.startswith("CAT-")],
              ["CAT-1", "CAT-2", "CAT-3", "CAT-4", "CAT-5", "CAT-6"])
        check("  and the app's own rows still are",
              [s for s in g["afterAll"] if s.startswith("APP-")],
              ["APP-1", "APP-2"])
        # A container with a data-sku but no checkbox is not selectable, and
        # ticking it would put a SKU in the selection with nothing on screen to
        # show for it.
        truthy("something with no tick box is not selected",
               "NOTICKABLE" not in g["afterAll"])
        check("unticking clears them all", g["afterClear"], [])
        truthy("an empty grid says so rather than doing nothing",
               "Nothing on screen" in (g["emptyToast"] or ""))
except FileNotFoundError:
    print("  (node is not on this machine -- not exercised)")


print("\n=== the live tile can be found and ticked like every other card ===")
MT = read("static", "js", "miles_template.js")
LJ = read("static", "js", "listings.js")
# The whole function, not a guessed window: liveTile runs to about 5,000
# characters and a 4,000-char slice stopped just short of its return, so this
# asserted against text it had not read.
_tile = MT.split("function liveTile(")[1].split("\nfunction ")[0]
# WITHOUT data-sku THIS TILE IS INVISIBLE TWICE OVER: to Select all, and to
# toggleSelect's tick-sync. The draft tile and the table row have carried it all
# along; this was the copy that drifted.
truthy("the catalogue tile carries data-sku", 'data-sku="${esc(it.sku' in _tile)
truthy("  and uses the one shared checkbox", "rowSelectBox({sku:" in _tile)
truthy("  rather than spelling its own", 'class="tilesel" ${SELECTED' not in _tile)
truthy("select-all reads the grid, not ROWS",
       "'#grid [data-sku]'" in LJ)
_sel = LJ.split("function selectAllVisible(")[1][:700]
truthy("  and no longer re-derives the list from ROWS",
       "ROWS.filter" not in _sel)


print("\n=== stock and handling time are ONE writer, because Amazon has one field ===")
H = read("listing", "handling.py")
tree = ast.parse(H)
fns = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
truthy("handling time still has its function", "push_handling_time" in fns)
truthy("  and stock has one", "push_quantity" in fns)
truthy("  both going through one patcher", "_patch_fulfillment" in fns)
# THE POINT OF SHARING IT. Amazon replaces the whole fulfillment_availability
# array, so a second writer would drop the field it does not know about.
check("the workbook is read and patched in exactly one place",
      H.count("patch_listings_item"), 1)
check("  and read once", H.count("get_listings_item"), 1)
truthy("the shared patcher keeps every field it was not asked to change",
       "e2.update(changes)" in H)
# A SINGLE-LINE FRAGMENT. The sentence wraps across two comment lines, and
# matching across the break is how these assertions keep failing on correct code.
truthy("  and says why that matters", "through untouched" in H)
# FBA: inventing a stock record would be claiming units nobody has.
_q = H.split("def push_quantity(")[1].split("def _patch_fulfillment")[0]
truthy("stock refuses to invent a fulfilment record", "default_entry=None" in _q)
truthy("  and the refusal explains FBA",
       "Amazon's warehouse" in H and "cannot be typed in" in H)
# Handling time, by contrast, may reasonably add one.
_h = H.split("def push_handling_time(")[1].split("def push_quantity")[0]
truthy("handling time may still add a minimal entry",
       "fulfillment_channel_code" in _h)


print("\n=== the stock route validates before Amazon ever hears about it ===")
RT = read("routes", "handling_routes.py")
truthy("there is a stock endpoint",
       '@app.route("/stock/bulk_update", methods=["POST"])' in RT)
_st = RT.split("def stock_bulk_update")[1].split("@app.route")[0]
truthy("  it refuses a negative", "cannot be negative" in _st)
truthy("  it refuses a fractional unit", "whole number of units" in _st)
# AN EXTRA DIGIT PROMISES STOCK THAT DOES NOT EXIST, and the orders arrive anyway.
truthy("  and caps a runaway number", "100,000 units" in _st)
truthy("  it offers the same single-listing test as handling time",
       "test_one" in _st)
truthy("  and writes no local copy of the stock",
       "sheet" not in _st.split('"""')[2] if _st.count('"""') > 2 else True)
truthy("  saying why it does not", "Amazon is the authority" in _st)


print("\n=== a percentage is worked out per listing, then those figures are sent ===")
P = read("routes", "price_routes.py")
truthy("there is a preview", '"/listing/price/percent_preview"' in P)
truthy("  and an apply", '"/listing/price/percent_apply"' in P)
_pv = P.split("def listing_price_percent_preview")[1].split("@app.route")[0]
_ap = P.split("def listing_price_percent_apply")[1].split("@app.route")[0]
# THE WHOLE DESIGN. Apply must not recompute from the percentage, or somebody
# approves a table and different numbers go out.
truthy("preview returns a per-listing table", '"rows": rows' in _pv)
truthy("  including what each is now and becomes",
       '"current": now' in _pv and '"new": new_price' in _pv)
truthy("apply reads the figures it is given", 'b.get("rows")' in _ap)
truthy("  and does NOT re-apply the percentage",
       "_pct_new_price" not in _ap)
truthy("  it still validates each one rather than trusting the browser",
       "p > 0" in _ap)
# Rule 12: the floor, the offer builder and the read-failure wording are the
# single-listing route's, not a second opinion about what a safe price is.
truthy("the floor is the same one the single listing uses", "_floor_for(" in _ap)
truthy("  the offer builder likewise", "_apply.build_patches" in _ap)
truthy("  and the read-failure wording", "_why_no_live(" in _ap)
truthy("below the floor is refused server-side, not just warned about",
       "below_floor" in _ap and "left alone" in _ap)
truthy("  and can be overridden deliberately", "below_floor_ok" in _ap)
truthy("a listing with no current price is skipped, not guessed at",
       "nothing to take a percentage of" in _pv)
truthy("an absurd percentage is refused", "-90" in _pv and "500" in _pv)
truthy("0% is refused as a no-op", "would change nothing" in _pv)


print("\n=== permissions: reading is free, changing a live listing is publishing ===")
from auth import guard
check("working out the new prices needs nothing special",
      guard.required_permission("/listing/price/percent_preview", "POST"), None)
check("  sending them is publishing",
      guard.required_permission("/listing/price/percent_apply", "POST"), "publish")
check("  and so is setting stock",
      guard.required_permission("/stock/bulk_update", "POST"), "publish")
check("  handling time is unchanged",
      guard.required_permission("/handling/bulk_update", "POST"), "publish")


print("\n=== the screen: three controls, one shape ===")
HTML = read("templates", "dashboard.html")
_bar = HTML.split('id="selbar"')[1].split("</div>")[0]
truthy("stock has a box and a button", 'id="stockqty"' in _bar and 'id="stockbtn"' in _bar)
truthy("  wired up", 'onclick="bulkQuantity()"' in _bar)
truthy("percentage has a box and a button",
       'id="pricepct"' in _bar and 'id="pricepctbtn"' in _bar)
truthy("  wired up", 'onclick="bulkPricePercent()"' in _bar)
truthy("  and it accepts a negative, or it cannot lower a price",
       'step="0.5"' in _bar and 'min="0"' not in _bar.split('id="pricepct"')[1][:120])
truthy("they sit beside handling time", 'id="handlingdays"' in _bar)
JS = read("static", "js", "handling.js")
truthy("both handlers exist",
       "async function bulkQuantity(" in JS and "async function bulkPricePercent(" in JS)
truthy("stock tests one listing before the rest", "test_one:true" in JS)
truthy("  and reports FBA separately from a real failure",
       "warehouse, not ours to set" in JS)
truthy("the price flow shows what each listing becomes before sending",
       "Nothing has been sent yet" in JS)
truthy("  and sends the previewed figures", "rows.map(r=>({sku:r.sku, new:r.new}))" in JS)
truthy("  warning that below the floor loses money on every unit",
       "still make money" in JS)
truthy("0 stock is called what it is", "takes them off sale" in JS)
# All three reuse the one selection helper rather than each deciding what
# "selected, or everything in view" means.
check("one definition of which listings are acted on",
      JS.count("function _handlingSkus("), 1)
# The CALLS, not every mention -- "function _handlingSkus(){" contains "()" too,
# so counting the bare name counted the definition as a fourth caller.
check("  used by all three", JS.count("= _handlingSkus()"), 3)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
