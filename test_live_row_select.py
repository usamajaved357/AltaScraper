"""The Live view's catalogue rows can be ticked, and draft actions skip them.

    "i am still not able to see the option to select all products on the page"

Reported a second time, from a screenshot of the LIST view. The previous fix
gave the TILE a checkbox and made "Select all" read the grid back instead of
re-deriving the list -- both correct, and both beside the point on this screen,
because the list view's catalogue row drew

    <td class="selcol"></td>

an empty cell where every other row has a checkbox. So the grid was asked and
the grid honestly answered "two": two rows offered a tick out of forty-eight.

The empty cell had a written reason, and it WAS a good one -- the bulk bar held
Approve and Hold, which are about drafts, and a listing Amazon has published is
not a draft to approve. Three actions have since been added that are the exact
opposite: handling time, stock and price are live Amazon changes, and a listing
that exists only on Amazon is their most ordinary target. The reason expired;
the empty cell did not.

So the tick is offered, and the draft actions are the ones that now have to be
careful. They are: they split the selection (splitByDraft) and say what they
left alone, instead of posting forty-six catalogue SKUs to /approve and
reporting "46 failed" -- which destroys nothing (the route answers "row not
found") but describes what happened untruthfully.
"""
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
    print("  %-68s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


LIST = open("static/js/listings.js", encoding="utf-8").read()
MILES = open("static/js/miles_template.js", encoding="utf-8").read()
AUTOFIX = open("static/js/autofix.js", encoding="utf-8").read()
HANDLING = open("static/js/handling.js", encoding="utf-8").read()

PROBE = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.esc = s => String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;");
globalThis.SELECTED = new Set();
globalThis.ROWS = [];
// Everything liveTableRow leans on that is not what is under test. Each returns
// the SHAPE the real one returns -- cogsCell a whole cell, the others a cell's
// contents -- so the column count below is the real column count.
globalThis.thumbUrl   = (u) => u;
globalThis._priceCell = () => "9.99";
globalThis.cogsCell   = () => "<td>cogs</td>";
globalThis._handCell  = () => "3d";
globalThis.rowActions = () => "<button>x</button>";
globalThis._dpUrl     = (a) => "https://amazon.co.uk/dp/" + a;
globalThis._brandCell = () => "brand";
// ...and the few more the DRAFT row needs. It is here only as the yardstick for
// the column count, so its contents are stubbed the same way.
globalThis.rowAsin      = () => ({own: "B0DRAFT001", source: ""});
globalThis._shownStatus = () => "LIVE";
globalThis._statusPill  = () => "LIVE";
globalThis._compCell    = () => "clear";
globalThis.needsCopy    = () => false;
globalThis.badgeClass   = () => "b-LIVE";

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
// _warnCell WAS GRABBED HERE, because tableRow called it. It no longer exists:
// the warning-count mark was removed from all four views it appeared in ("i
// dont want this symbol at all, i already have 3 symbols for restricted
// compliance and claims risk"). grab() throws on a missing name rather than
// stubbing one, which is what caught this -- and is the behaviour worth keeping.
vm.runInThisContext([grab("rowSelectBox"), grab("liveTableRow"),
                     grab("splitByDraft"), grab("_draftOnlyNote"),
                     grab("tableRow")].join("\n"));

const out = {};
const IT = {sku: "9.18_3Days_B0C6XTNXL8", asin: "B0H8VHDX8B", title: "Floor Brush"};

// ---- 1. the catalogue row offers a tick, and carries the SKU to find it by --
const row = liveTableRow(IT);
out.hasCheckbox   = /<td class="selcol"><input type="checkbox"/.test(row);
out.hasDataSku    = row.indexOf('data-sku="' + IT.sku + '"') >= 0;
out.boxCarriesSku = row.indexOf("toggleSelect('" + IT.sku + "'") >= 0;
// Clicking the tick must not also open the live editor behind it.
out.boxStopsRow   = /onclick="event.stopPropagation\(\)"/.test(row);
// The row still opens the listing -- the tick was added, nothing was taken.
// THROUGH openLiveListing NOW, not optimizeLive directly: a catalogue row whose
// SKU this app also holds opens the product page like any other listing, and
// only one it has no row for falls back to the live editor. openLiveListing is
// the single place that decides which, so the row asks it rather than choosing.
out.rowStillOpens = /openLiveListing\('B0H8VHDX8B'/.test(row);

// ---- 2. still ten columns. The last fix to this row was a column count -----
out.cells       = (row.match(/<td/g) || []).length;
out.draftCells  = (tableRow({sku:"S", title:"t", price:"1", row:2}).match(/<td/g) || []).length;

// ---- 3. a ticked catalogue row survives a redraw ---------------------------
out.notMarkedWhenUnselected = !/class="rowon"/.test(row);
SELECTED.add(IT.sku);
out.markedWhenSelected = /class="rowon"/.test(liveTableRow(IT));
out.boxCheckedWhenSelected = /checkbox" class="rowsel" checked/.test(liveTableRow(IT));
SELECTED.clear();

// ---- 4. the split itself ---------------------------------------------------
ROWS = [{sku: "DRAFT-1"}, {sku: "DRAFT-2"}, {sku: ""}];
const s = splitByDraft(["DRAFT-1", "AMZ-1", "DRAFT-2", "AMZ-2", "AMZ-3"]);
out.drafts     = s.drafts;
out.amazonOnly = s.amazonOnly;
// A blank SKU in ROWS must not make a blank selection look like a draft.
out.blankIsNotADraft = splitByDraft([""]).drafts.length;
// Whitespace is not a different listing.
out.trimmed = splitByDraft([" DRAFT-1 "]).drafts.length;
// Nothing selected, nothing anywhere -- no throw, two empty lists.
out.emptyOk = JSON.stringify(splitByDraft([]));
ROWS = [];
out.noRowsMeansNoDrafts = splitByDraft(["ANY"]).drafts.length;

// ---- 5. the note is silent in the ordinary case ----------------------------
out.silentWhenAllDrafts = _draftOnlyNote([], "approve");
const note = _draftOnlyNote(["A","B"], "approve");
out.noteCounts   = /\b2\b/.test(note);
out.noteSaysWhy  = /no draft here/.test(note);
out.noteSaysWhat = /left alone/.test(note);
out.noteSaysNext = /Sync/.test(note);
out.noteUsesVerb = /to approve/.test(note);

console.log(JSON.stringify(out));
"""

try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, PROBE.encode("utf-8"))
    os.close(fd)
    r = subprocess.run(["node", path], capture_output=True, text=True,
                       encoding="utf-8", cwd=HERE)
    os.unlink(path)
    if r.returncode != 0:
        print("  FAIL listings.js threw:", (r.stderr or "")[:600])
        raise SystemExit(1)
    g = json.loads(r.stdout.strip().splitlines()[-1])
except FileNotFoundError:
    print("  (node is not on this machine -- not exercised)")
    raise SystemExit(0)

print("=== the catalogue row can be ticked ===")
truthy("its select cell holds a checkbox, not nothing", g["hasCheckbox"])
# visibleSelectableSkus() reads '#grid [data-sku]' and requires a checkbox
# inside. Without data-sku ON THE ROW the checkbox is invisible to Select all,
# which is the whole reported bug.
truthy("  and the row carries data-sku, so Select all can see it",
       g["hasDataSku"])
truthy("  the box knows which SKU it is", g["boxCarriesSku"])
truthy("  ticking it does not also open the editor", g["boxStopsRow"])
truthy("  and the row still opens the live listing", g["rowStillOpens"])

print("\n=== the columns still line up ===")
# This row's previous bug was a missing cell shifting every column left. Adding
# a checkbox INSIDE the existing cell must not add a cell.
check("the catalogue row has ten cells", g["cells"], 10)
check("  the same number as a draft row", g["draftCells"], g["cells"])

print("\n=== a tick survives the redraw that follows it ===")
truthy("an unselected row is not marked", g["notMarkedWhenUnselected"])
truthy("a selected row is marked", g["markedWhenSelected"])
truthy("  and its box is drawn checked", g["boxCheckedWhenSelected"])

print("\n=== which listings have a draft here ===")
check("the drafts are separated", g["drafts"], ["DRAFT-1", "DRAFT-2"])
check("  from the ones that are only on Amazon", g["amazonOnly"],
      ["AMZ-1", "AMZ-2", "AMZ-3"])
check("a blank SKU is not a draft", g["blankIsNotADraft"], 0)
check("  and stray whitespace is the same listing", g["trimmed"], 1)
check("nothing selected does not throw", g["emptyOk"],
      '{"drafts":[],"amazonOnly":[]}')
check("with no rows loaded, nothing is claimed as a draft",
      g["noRowsMeansNoDrafts"], 0)

print("\n=== what the user is told ===")
# THE ORDINARY CASE STAYS SILENT. On the Drafts tab every selection is drafts,
# and a warning about none of them would be noise on every single press.
check("all-drafts says nothing at all", g["silentWhenAllDrafts"], "")
truthy("it says how many were left alone", g["noteCounts"])
truthy("  and why -- the same words the row badge uses", g["noteSaysWhy"])
truthy("  and that they were not touched", g["noteSaysWhat"])
truthy("  and what to do about it", g["noteSaysNext"])
truthy("  named for the action being taken", g["noteUsesVerb"])

print("\n=== every draft action splits, and no live action does ===")
# Approve/Hold, Delete and Auto-fix act on the payload this app holds.
truthy("bulkStatus splits before sending", "splitByDraft(_sel)" in MILES.split(
    "async function bulkStatus")[1][:600])
truthy("bulkDelete splits before sending", "splitByDraft(_sel)" in MILES.split(
    "async function bulkDelete")[1][:600])
truthy("bulkAutoFix splits before starting", "splitByDraft(sel)" in AUTOFIX)
# ...and each one refuses outright rather than sending an empty list, which
# would read as "approved 0" instead of "there was nothing to approve".
truthy("bulkStatus stops when none of them is a draft",
       "if(!skus.length){" in MILES.split("async function bulkStatus")[1][:1200])
truthy("bulkDelete says it never removes a live listing",
       "never removes a live" in MILES)
truthy("bulkAutoFix stops when none of them is a draft",
       "if(!s.drafts.length){" in AUTOFIX)

# Handling/stock/price are live Amazon changes -- an Amazon-only listing is
# their most ordinary target, so they must NOT split.
truthy("the live actions do not split -- they apply to all of them",
       "splitByDraft" not in HANDLING)

print("\n=== 'all of them' means the same thing however it is reached ===")
# "Select all then Set stock" and "Set stock with nothing selected" are the same
# gesture on the same screen and must cover the same listings. The fallback
# re-derived the list from ROWS, which excludes Amazon's catalogue entirely.
truthy("the no-selection fallback asks the screen",
       "visibleSelectableSkus()" in HANDLING)
truthy("  and only falls back to ROWS if nothing is drawn",
       "if(onScreen.length) return onScreen;" in HANDLING)
# The CALL form, not the bare name -- "function _handlingSkus(){" contains
# "_handlingSkus()" too, so counting the name counts the definition as a fourth
# caller and the assertion passes whatever the callers do.
truthy("all three live actions share that one list",
       HANDLING.count("= _handlingSkus();") == 3)

print("\n=== the reason the old cell was empty is written down, not deleted ===")
truthy("the row explains why it changed", "THAT IS NOW THE BUG" in LIST)
truthy("splitByDraft explains which actions want which half",
       "about the DRAFT" in LIST and "about the LISTING" in LIST)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
