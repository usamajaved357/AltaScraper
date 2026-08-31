// The detailed listing row (Amazon "Manage All Inventory" view).
//
// WHAT THIS PINS
//
// This is a third view of rows the other two views already draw, so the ways it
// can fail are the ways two renderers of one fact drift apart:
//
//   * THE TWO ASINs. A SKU is price_days_ASIN and that ASIN is the
//     COMPETITOR's (CLAUDE.md Rule 1). Our own only exists once Amazon accepts
//     the listing. A view that parsed the SKU for an ASIN, or linked the
//     competitor's as if it were ours, would tell someone a draft is live.
//   * DASHES ARE NOT ZEROS. "0 units sold" and "we have not looked" are
//     different facts. Amazon prints -- for the second and so must this.
//   * The header and the rows must carry the same columns -- the table view
//     shipped with a nine-cell row under a ten-column header and drew every
//     live listing one column to the left, silently.
//   * The view must degrade to the table if its own file did not load, rather
//     than rendering an empty page.
//
// Run: node test_listrow_detailed.js
const fs = require("fs"), vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK"
    : "FAIL\n      got  " + JSON.stringify(got) + "\n      want " + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const SRC      = fs.readFileSync("static/js/listrow_detailed.js", "utf8");
const LISTINGS = fs.readFileSync("static/js/listings.js", "utf8");
const CSS      = fs.readFileSync("static/css/listrow_detailed.css", "utf8");

// ---- the app's helpers, as the page provides them -------------------------
globalThis.window = globalThis;
globalThis.esc = s => String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
                                                .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
globalThis.CUR_SYMBOL = "£";
globalThis.SELECTED = new Set();
globalThis.lsStatusOf = r => String(r.status||"").toUpperCase();
globalThis.lsWasSentToAmazon = r => ["LIVE","SUBMITTED"].indexOf(globalThis.lsStatusOf(r)) >= 0;
globalThis.lsWarnings = r => ({n:(r.warnings||[]).length});
globalThis.rowAsin = r => r._asin || {own:"", source:""};
globalThis._rowImages = r => r._imgs || [];
globalThis._dwCost = r => r.cogs ? ("£" + r.cogs) : "";
globalThis._dpUrl = a => "https://www.amazon.co.uk/dp/" + a;
globalThis.rowSelectBox = r => '<input type="checkbox" data-sku="' + r.sku + '">';
globalThis.rowActions = r => '<div class="acts"><button class="btn">…</button></div>';
globalThis.openListing = () => {};

const ctx = vm.createContext(globalThis);
vm.runInContext(SRC, ctx, {filename:"listrow_detailed.js"});
const LM = () => vm.runInContext("LISTING_METRICS", ctx);

const LIVE = {sku:"9.18_3Days_B0C6XTNXL8", status:"LIVE", title:"Floor Scrub Brush",
              barcode:"4553334465572", price:"24.99", cogs:"9.18", profit:"8.57",
              date_processed:"2026-08-15", warnings:[],
              _asin:{own:"B0H8VHDX8B", source:"B0C6XTNXL8"}, _imgs:["http://i/1.jpg"]};
const DRAFT = {sku:"11.99_2Days_B0C7GSCV5W", status:"GENERATED", title:"Window Kit",
               barcode:"4553334465596", price:"12.99", cogs:"11.99", profit:"-1.62",
               date_processed:"2026-08-29", warnings:[{severity:"high"},{severity:"low"}],
               _asin:{own:"", source:"B0C7GSCV5W"}, _imgs:[]};

// ---------------------------------------------------------------------------
console.log("\nthe two ASINs are never confused");
// ---------------------------------------------------------------------------
const liveHtml = ctx.detailedRow(LIVE);
truthy("our own ASIN is shown",            liveHtml.indexOf("B0H8VHDX8B") >= 0);
truthy("  and links to the live product page",
       liveHtml.indexOf("amazon.co.uk/dp/B0H8VHDX8B") >= 0);
const draftHtml = ctx.detailedRow(DRAFT);
check("a draft is NOT given a product link",
      /href=[^>]*\/dp\//.test(draftHtml), false);
truthy("it says it is not live yet",       draftHtml.indexOf("not live yet") >= 0);
truthy("  and names the competitor as the source, not as ours",
       draftHtml.indexOf("from B0C7GSCV5W") >= 0);
// The decisive one: the SKU carries the competitor ASIN. Nothing may dig it out.
check("the file never parses an ASIN out of a SKU",
      /_\d+Days_|sku[^\n]{0,40}\.split\(['"]_/.test(SRC), false);
truthy("it asks rowAsin() instead", /rowAsin\(r\)/.test(SRC));

// ---------------------------------------------------------------------------
console.log("\ndashes mean \"we have not got this\", and zero never stands in");
// ---------------------------------------------------------------------------
check("nothing known -> a dash",     ctx.lrVal(undefined), '<span class="lr-dash">--</span>');
check("null -> a dash",              ctx.lrVal(null),      '<span class="lr-dash">--</span>');
check("empty string -> a dash",      ctx.lrVal(""),        '<span class="lr-dash">--</span>');
check("a real ZERO is shown as zero, not a dash", ctx.lrVal(0), "0");
check("a number survives",           ctx.lrVal(14), "14");
check("thousands get separators",    ctx.lrVal(24810, {comma:true}), "24,810");
check("money gets the currency",     ctx.lrVal("342", {money:true}), "£342");

console.log("\n  ...so an unfilled metrics table draws dashes, not zeros");
truthy("Phase 1 starts with no metrics", Object.keys(LM()).length === 0);
const perf = ctx.lrPerf(LIVE);
check("four dashes in Performance", (perf.match(/lr-dash/g) || []).length, 4);
check("  and no zeros",             /">0</.test(perf), false);

console.log("\n  ...and once filled, the values appear");
LM()[LIVE.sku] = {sales:342, units:14, views:89, rank:24810,
                  on_hand:3, available:3, inbound:0, reserved:0,
                  buybox:true, lowest_price:"23.99"};
const perf2 = ctx.lrPerf(LIVE);
truthy("sales",  perf2.indexOf("£342") >= 0);
truthy("units",  perf2.indexOf(">14<") >= 0);
truthy("views",  perf2.indexOf(">89<") >= 0);
truthy("rank, with separators", perf2.indexOf("24,810") >= 0);
const inv2 = ctx.lrInv(LIVE);
truthy("on-hand", inv2.indexOf(">3<") >= 0);
truthy("a real zero inbound is shown as 0", inv2.indexOf(">0<") >= 0);
const pr2 = ctx.lrPricing(LIVE);
truthy("the buy box when we hold it", pr2.indexOf("Featured offer") >= 0);
truthy("the lowest price when known", pr2.indexOf("£23.99") >= 0);

console.log("\n  ...zero stock is called out in red");
LM()[LIVE.sku].on_hand = 0; LM()[LIVE.sku].available = 0;
const inv3 = ctx.lrInv(LIVE);
check("on-hand 0 is red", (inv3.match(/lr-data-val red/g) || []).length, 2);

console.log("\n  ...and losing the buy box is stated, not left blank");
LM()[LIVE.sku].buybox = false;
truthy("not winning", ctx.lrPricing(LIVE).indexOf("Not winning") >= 0);
LM()[LIVE.sku].buybox = undefined;
check("but an UNKNOWN buy box says nothing at all — it is not 'not winning'",
      /Not winning|Featured offer/.test(ctx.lrPricing(LIVE)), false);
delete LM()[LIVE.sku];

// ---------------------------------------------------------------------------
console.log("\na listing that was never sent has no performance to report");
// ---------------------------------------------------------------------------
truthy("it says 'Not yet live' rather than four dashes",
       ctx.lrPerf(DRAFT).indexOf("Not yet live") >= 0);
check("  and does not invent inventory for it",
      ctx.lrInv(DRAFT).indexOf("On-hand") >= 0, false);
truthy("but price, cost and profit ARE known and shown",
       ctx.lrPricing(DRAFT).indexOf("£12.99") >= 0
       && ctx.lrPricing(DRAFT).indexOf("£11.99") >= 0);
truthy("a negative profit is red",
       ctx.lrPricing(DRAFT).indexOf('lr-data-val red') >= 0);

// ---------------------------------------------------------------------------
console.log("\nthe header and the rows carry the same columns");
// ---------------------------------------------------------------------------
const head = ctx.detailedHead([LIVE, DRAFT]);
// The class name must END here: \b would also match lr-status-badge and
// lr-status-date, which are inside the status column, not columns themselves.
const cols = h => (h.match(/class="lr-(cb|status|product|perf|inv|pricing|actions)["\s]/g) || [])
                    .map(s => s.replace('class="lr-', '').replace(/["\s]$/, ''));
check("the header's columns", cols(head),
      ["cb","status","product","perf","inv","pricing","actions"]);
check("the row's columns are the same, in the same order",
      cols(ctx.detailedRow(LIVE)), cols(head));
// The widths are declared once as variables so the two cannot drift.
truthy("and the widths are declared once, shared by both",
       /\.lr-head,\s*\.lr\{[\s\S]{0,200}--lr-cb:/.test(CSS));

console.log("\n  ...a block is one header over all the rows");
const block = ctx.detailedBlock([LIVE, DRAFT]);
check("exactly one header", (block.match(/lr-head/g) || []).length, 1);
check("one row per listing",  (block.match(/class="lr[ "]/g) || []).length, 2);
check("no rows -> nothing at all", ctx.detailedBlock([]), "");

// ---------------------------------------------------------------------------
console.log("\nrows behave like the other views' rows");
// ---------------------------------------------------------------------------
truthy("clicking opens the listing through openListing()",
       /onclick="openListing\('/.test(liveHtml));
truthy("the batch-actions checkbox is the shared one",
       liveHtml.indexOf('data-sku="' + LIVE.sku + '"') >= 0);
truthy("  and clicking it does not also open the listing",
       /class="lr-cb" onclick="event\.stopPropagation\(\)"/.test(liveHtml));
truthy("the row menu is the shared rowActions()", liveHtml.indexOf('class="acts"') >= 0);
truthy("  and it does not open the listing either",
       /class="lr-actions" onclick="event\.stopPropagation\(\)"/.test(liveHtml));
globalThis.SELECTED.add(LIVE.sku);
truthy("a selected row is marked", /class="lr sel"/.test(ctx.detailedRow(LIVE)));
globalThis.SELECTED.clear();

console.log("\n  ...warnings are surfaced on the row");
truthy("counted",  draftHtml.indexOf("2 warnings") >= 0);
check("and one warning is singular",
      ctx.detailedRow(Object.assign({}, DRAFT, {warnings:[{}]})).indexOf("1 warning") >= 0, true);

console.log("\n  ...dates are readable, and bad ones do not print 'Invalid Date'");
check("an ISO date",        ctx.lrDate("2026-08-15"), "15 Aug 2026");
check("a timestamp",        ctx.lrDate("2026-08-15T13:11:00Z").slice(-8), "Aug 2026");
check("nonsense falls back to the raw text, not 'Invalid Date'",
      ctx.lrDate("not a date"), "not a date");
check("empty stays empty",  ctx.lrDate(""), "");
truthy("the row shows the date", liveHtml.indexOf("15 Aug 2026") >= 0);

// ---------------------------------------------------------------------------
console.log("\nthe view is additional, and degrades safely");
// ---------------------------------------------------------------------------
truthy("listViewNow() exists to decide what is drawable",
       /function listViewNow\(\)/.test(LISTINGS));
truthy("  and falls back to the table when the file did not load",
       /LIST_VIEW === "detailed" && typeof detailedBlock !== "function"[\s\S]{0,40}return "table"/.test(LISTINGS));
truthy("  without erasing the stored preference",
       !/localStorage\.setItem[^\n]*\n?[^\n]*listViewNow/.test(LISTINGS));
truthy("both dispatchers ask it rather than reading LIST_VIEW directly",
       (LISTINGS.match(/listViewNow\(\)/g) || []).length >= 3);
// The other two views must still be reachable and unchanged.
truthy("the table view is still there", /=== "table"/.test(LISTINGS));
truthy("the card view is still there",  /=== "grid"\) \? "grid"/.test(LISTINGS));
const TPL = fs.readFileSync("templates/dashboard.html", "utf8");
check("three toggle buttons now",
      (TPL.match(/data-view="(table|detailed|grid)"/g) || []).sort(),
      ['data-view="detailed"', 'data-view="grid"', 'data-view="table"']);
truthy("the detailed stylesheet is loaded", TPL.indexOf("listrow_detailed.css") >= 0);
truthy("and the renderer",                  TPL.indexOf("listrow_detailed.js") >= 0);
truthy("the card grid's layout is switched off for it",
       /detailedview|view === "detailed"/.test(LISTINGS));

console.log("\n%d failed", fails);
process.exit(fails ? 1 : 0);
