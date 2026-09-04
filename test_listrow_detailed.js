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

// isAmazonLive decides whether Amazon's handling read-out is drawn beside our
// own editable one; cogsOf decides what the cost cell holds. Both are
// listings.js/cogs.js helpers the row now calls at draw time.
globalThis.isAmazonLive = r => globalThis.lsStatusOf(r) === "LIVE";
globalThis.cogsOf = r => ({cost: r.cogs ? Number(r.cogs) : null,
                           source: r.cogs ? "manual" : ""});

const ctx = vm.createContext(globalThis);
// THE EDITABLE BOXES ARE A REAL DEPENDENCY OF THE ROW, not a stub. The price,
// cost, handling and stock cells all call lrEditBox, so the row cannot be
// rendered without it -- and stubbing it would mean a change that broke the box
// still passed here, which is the opposite of what running the renderer is for.
// thumbs.js too: every picture on the row asks it for a sized URL, so the
// renderer cannot draw without it. Real rather than stubbed, for the same
// reason as the edit boxes below.
vm.runInContext(fs.readFileSync("static/js/thumbs.js", "utf8"), ctx,
                {filename:"thumbs.js"});
vm.runInContext(fs.readFileSync("static/js/listrow_edit.js", "utf8"), ctx,
                {filename:"listrow_edit.js"});
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
check("nothing known -> a dash",     ctx.lrVal(undefined), '<span class="dash">—</span>');
check("null -> a dash",              ctx.lrVal(null),      '<span class="dash">—</span>');
check("empty string -> a dash",      ctx.lrVal(""),        '<span class="dash">—</span>');
check("a real ZERO is shown as zero, not a dash", ctx.lrVal(0), "0");
check("a number survives",           ctx.lrVal(14), "14");
check("thousands get separators",    ctx.lrVal(24810, {comma:true}), "24,810");
check("money gets the currency",     ctx.lrVal("342", {money:true}), "£342.00");

console.log("\n  ...so an unfilled metrics table draws dashes, not zeros");
truthy("Phase 1 starts with no metrics", Object.keys(LM()).length === 0);
const perf = ctx.lrPerf(LIVE);
check("four dashes in Performance", (perf.match(/class="dash"/g) || []).length, 4);
check("  and no zeros",             /">0</.test(perf), false);

console.log("\n  ...and once filled, the values appear");
// The field names are the ones /listing/live_metrics really returns -- see
// domain/listing_metrics.py and routes/metrics_routes.py.
LM()[LIVE.sku] = {sales:342, units:14, views:89, rank:24810,
                  // AMAZON-fulfilled, so the warehouse lines apply. Without a
                  // channel the row draws neither them nor a guess -- see
                  // lrInvChannel.
                  fulfillment:"AMAZON",
                  on_hand:3, available:3, inbound:0, reserved:0,
                  buybox_pct:100, buy_box_price:"23.99", offer_count:4};
const perf2 = ctx.lrPerf(LIVE);
truthy("sales",  perf2.indexOf("£342") >= 0);
truthy("units",  perf2.indexOf(">14<") >= 0);
truthy("views",  perf2.indexOf(">89<") >= 0);
truthy("rank, with separators", perf2.indexOf("24,810") >= 0);
const inv2 = ctx.lrInv(LIVE);
truthy("on-hand", inv2.indexOf(">3<") >= 0);
truthy("a real zero inbound is shown as 0", inv2.indexOf(">0<") >= 0);
const pr2 = ctx.lrPricing(LIVE);
truthy("the featured price has its own row", pr2.indexOf("Featured offer") >= 0);
truthy("  and holding it all window is said as ours", pr2.indexOf("Ours, all of the window") >= 0);
truthy("the market price when known", pr2.indexOf("£23.99") >= 0);
truthy("and how many offers there are", pr2.indexOf(">4<") >= 0);

console.log("\n  ...zero stock is called out in red");
LM()[LIVE.sku].on_hand = 0; LM()[LIVE.sku].available = 0;
const inv3 = ctx.lrInv(LIVE);
check("on-hand 0 is red", (inv3.match(/d-val red/g) || []).length, 2);

console.log("\n  ...the buy box is a SHARE of the window, and is not dressed as a live yes/no");
LM()[LIVE.sku].buybox_pct = 0;
truthy("never held -> never ours", ctx.lrPricing(LIVE).indexOf("Never ours") >= 0);
LM()[LIVE.sku].buybox_pct = 52.73;
const partial = ctx.lrPricing(LIVE);
check("held for part of it is NOT reported as ours outright",
      partial.indexOf("Ours, all of the window") >= 0, false);
check("  nor as never ours", partial.indexOf("Never ours") >= 0, false);
truthy("  it says what the share actually was", partial.indexOf("Ours for 53% of views") >= 0);
LM()[LIVE.sku].buybox_pct = undefined;
// AN UNKNOWN SHARE SAYS NOTHING. The featured PRICE row is still drawn, with
// a dash -- "not asked yet" and "no featured offer" must not look alike.
check("an UNKNOWN share says nothing at all — it is not 'never ours'",
      /Never ours|Ours for|Ours, all/.test(ctx.lrPricing(LIVE)), false);
truthy("  but the featured price row is still there, as a dash",
       ctx.lrPricing(LIVE).indexOf("Featured offer") >= 0);
delete LM()[LIVE.sku];

// ---------------------------------------------------------------------------
console.log("\na listing that was never sent has no performance to report");
// ---------------------------------------------------------------------------
truthy("it says 'Not yet live' rather than four dashes",
       ctx.lrPerf(DRAFT).indexOf("Not yet live") >= 0);
check("  and does not invent inventory for it",
      ctx.lrInv(DRAFT).indexOf("On-hand") >= 0, false);
// PRICE AND COST ARE EDITABLE BOXES NOW (listrow_edit.js), so they carry the
// figure as a value rather than as printed money. The profit is still text.
const _pd = ctx.lrPricing(DRAFT);
truthy("the price is in its box", _pd.indexOf('data-lr-field="price" data-lr-orig="12.99"') >= 0);
truthy("the cost is in its box",  _pd.indexOf('data-lr-field="cost"') >= 0 && _pd.indexOf("11.99") >= 0);
truthy("and the profit is shown", _pd.indexOf("1.62") >= 0);
truthy("a negative profit is red",
       ctx.lrPricing(DRAFT).indexOf('d-val red') >= 0);

// ---------------------------------------------------------------------------
console.log("\nthe header and the rows carry the same columns");
// ---------------------------------------------------------------------------
const head = ctx.detailedHead([LIVE, DRAFT]);
// The class name must END here: \b would also match lr-status-badge and
// lr-status-date, which are inside the status column, not columns themselves.
const cols = h => (h.match(/class="col-(cb|status|product|perf|inv|price|actions)["\s]/g) || [])
                    .map(s => s.replace('class="col-', '').replace(/["\s]$/, ''));
check("the header's columns", cols(head),
      ["cb","status","product","perf","inv","price","actions"]);
check("the row's columns are the same, in the same order",
      cols(ctx.detailedRow(LIVE)), cols(head));
// The widths are declared once as variables so the two cannot drift.
truthy("and the widths are declared once, shared by both",
       /\.col-cb\{ width:28px/.test(CSS));

console.log("\n  ...a block is one header over all the rows");
const block = ctx.detailedBlock([LIVE, DRAFT]);
check("exactly one header", (block.match(/inv-head/g) || []).length, 1);
check("one row per listing",  (block.match(/class="inv-row/g) || []).length, 2);
check("no rows -> nothing at all", ctx.detailedBlock([]), "");

// ---------------------------------------------------------------------------
console.log("\nrows behave like the other views' rows");
// ---------------------------------------------------------------------------
truthy("clicking opens the listing through openListing()",
       /onclick="openListing\('/.test(liveHtml));
truthy("the batch-actions checkbox is the shared one",
       liveHtml.indexOf('data-sku="' + LIVE.sku + '"') >= 0);
truthy("  and clicking it does not also open the listing",
       /class="col-cb" onclick="event\.stopPropagation\(\)"/.test(liveHtml));
truthy("the row menu is the shared overflow, drawerMore",
       /onclick="drawerMore\(event,/.test(liveHtml));
truthy("  and it does not open the listing either",
       /class="col-actions" onclick="event\.stopPropagation\(\)"/.test(liveHtml));
globalThis.SELECTED.add(LIVE.sku);
truthy("a selected row is marked", /class="inv-row sel"/.test(ctx.detailedRow(LIVE)));
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

// ---------------------------------------------------------------------------
console.log("\nthe view says where its numbers came from and how fresh they are");
// ---------------------------------------------------------------------------
check("nothing ever fetched -> no age claim at all", ctx.lrAgo(0), "");
check("seconds ago",  ctx.lrAgo(Date.now()/1000 - 10), "just now");
check("minutes ago",  ctx.lrAgo(Date.now()/1000 - 600), "10 minutes ago");
check("one hour is singular", ctx.lrAgo(Date.now()/1000 - 3700), "1 hour ago");
check("hours ago",    ctx.lrAgo(Date.now()/1000 - 7200), "2 hours ago");
check("days ago",     ctx.lrAgo(Date.now()/1000 - 3*86400), "3 days ago");

vm.runInContext("LR_COVERAGE = {days:30, sales_days:30, sales_last:'2026-08-30',"
                + " stock_last:'2026-08-23'};"
                + "LR_LAST_FETCH = " + (Date.now()/1000 - 7200) + "; LR_ERRORS = {};", ctx);
const bar = ctx.lrMetricsBar();
truthy("the window it covers",        bar.indexOf("30 days") >= 0);
truthy("when the stock was counted",  bar.indexOf("2026-08-23") >= 0);
truthy("when Amazon was last asked",  bar.indexOf("2 hours ago") >= 0);
truthy("and a way to ask again",      bar.indexOf("lrRefreshMetrics()") >= 0);

console.log("\n  ...a PARTLY reported window is not passed off as a full one");
vm.runInContext("LR_COVERAGE = {days:30, sales_days:4, sales_last:'2026-08-30'};", ctx);
const partBar = ctx.lrMetricsBar();
truthy("it says how many days it really had", partBar.indexOf("4 of 30 days") >= 0);
truthy("and marks it",                        partBar.indexOf("lr-part") >= 0);

console.log("\n  ...Amazon refusing is REPORTED, never shown as 'there is none'");
vm.runInContext("LR_ERRORS = {rank:'403 Forbidden — role not granted'};", ctx);
const errBar = ctx.lrMetricsBar();
truthy("the group that failed",  errBar.indexOf("rank") >= 0);
truthy("the reason",             errBar.indexOf("403 Forbidden") >= 0);
truthy("and that the rest is still this app's own record",
       errBar.indexOf("this app’s own records") >= 0);
vm.runInContext("LR_ERRORS = {};", ctx);

console.log("\n  ...a page render never calls Amazon; only Refresh does");
truthy("the loader defaults to the local-only form",
       /if\(force\) url \+= "&fetch=1"/.test(SRC));
check("  and detailedBlock does not force a fetch",
      /lrLoadMetrics\(rows\)/.test(SRC), true);
truthy("  while the refresh button does",  /lrLoadMetrics\(rows, true\)/.test(SRC));
// A SET OF SKUs, NOT A KEY. It held one key -- the sorted SKUs of the last
// set it fetched -- and one screen draws several blocks with different sets, so
// the key alternated for ever and every reply re-rendered. A set cannot
// alternate: once a SKU has been asked about it stays asked about.
truthy("the same SKU is not asked for twice",
       /LR_ASKED\.has\(s\)/.test(SRC) && /LR_ASKED\.add\(s\)/.test(SRC));

// ---------------------------------------------------------------------------
console.log("\nvariation families: grouped when known, flat when not");
// ---------------------------------------------------------------------------
// The grouping is domain/families.py's answer, served by /variations/families.
// Nothing here works it out, so the fixture is that route's shape.
const P = "PARENT-HOSE", C1 = "6.99_3Days_B09MQ46LGJ", C2 = "6.99_3Days_B09MQ46ABC";
const kid = (sku, colour) => ({sku:sku, status:"LIVE", title:"Garden Hose, " + colour,
                               price:"24.99", cogs:"6.99", profit:"8.57", warnings:[],
                               _asin:{own:"B0" + colour, source:""}, _imgs:[]});
const parentRow = {sku:P, status:"PARENT", title:"Expandable Garden Hose 50ft",
                   warnings:[], _asin:{own:"B0H8K1LXXT", source:""}, _imgs:[]};
const ROWSET = [kid(C1, "Green"), kid(C2, "Blue"), LIVE, parentRow];
globalThis.ROWS = ROWSET;

console.log("\n  ...with no family data, everything is flat");
vm.runInContext("LR_FAMILIES = null;", ctx);
let g = ctx.lrGroupRows(ROWSET);
check("no groups",             g.groups.length, 0);
check("every row stays flat",  g.flat.length, 4);
vm.runInContext("LR_FAMILIES = {};", ctx);
check("an EMPTY answer is also flat — not an error, just no families",
      ctx.lrGroupRows(ROWSET).groups.length, 0);

console.log("\n  ...with a family, the children group under a parent");
vm.runInContext("LR_FAMILIES = {'" + P + "': {parent:{title:'Expandable Garden Hose 50ft',"
  + " asin:'B0H8K1LXXT'}, theme:'COLOR', children:['" + C1 + "','" + C2 + "']}};", ctx);
g = ctx.lrGroupRows(ROWSET);
check("one family",                 g.groups.length, 1);
check("  with both children",       g.groups[0].children.length, 2);
check("the parent row is claimed, not left loose", g.flat.map(r => r.sku), [LIVE.sku]);

const famRow = ctx.lrFamilyRow(g.groups[0]);
truthy("the row counts the variations", famRow.indexOf("Variations (2)") >= 0);
truthy("names the family",              famRow.indexOf("Expandable Garden Hose 50ft") >= 0);
truthy("names the parent ASIN",         famRow.indexOf("B0H8K1LXXT") >= 0);
truthy("names the parent SKU",          famRow.indexOf(P) >= 0);
truthy("and says what varies",          famRow.indexOf("varies by color") >= 0);
// A parent is not buyable, so it must carry no price/stock/performance block.
check("the parent row has NO pricing block",   /lr-pricing/.test(famRow), false);
check("  no inventory block",                  /lr-inv/.test(famRow), false);
check("  and no performance block",            /lr-perf/.test(famRow), false);

console.log("\n  ...collapsed by default, like Amazon");
vm.runInContext("LR_OPEN_FAMS = {};", ctx);
let famBlock = ctx.detailedBlock(ROWSET);
check("the children are not drawn",  famBlock.indexOf(C1) >= 0, false);
truthy("but the family row is",      famBlock.indexOf("Variations (2)") >= 0);
truthy("and the single listing is",  famBlock.indexOf(LIVE.sku) >= 0);
truthy("with an expand-all control", famBlock.indexOf("lrExpandAll(") >= 0);
truthy("  that says Expand all",     famBlock.indexOf("Expand all") >= 0);

console.log("\n  ...expanding shows the children, indented, with their full data");
ctx.lrToggleFamily(P);
famBlock = ctx.detailedBlock(ROWSET);
truthy("child one",  famBlock.indexOf(C1) >= 0);
truthy("child two",  famBlock.indexOf(C2) >= 0);
check("both are marked as children", (famBlock.match(/var-child/g) || []).length, 2);
// The price is in an editable box now, so it is a value rather than printed
// money -- the point stands: a child row carries its own pricing block.
truthy("a child keeps its pricing block",
       famBlock.indexOf('data-lr-field="price" data-lr-orig="24.99"') >= 0);
truthy("and the control now offers Collapse all", famBlock.indexOf("Collapse all") >= 0);
ctx.lrToggleFamily(P);
check("toggling again collapses it",
      ctx.detailedBlock(ROWSET).indexOf(C1) >= 0, false);

console.log("\n  ...expand all / collapse all");
ctx.lrExpandAll(true);
truthy("expand all opens it", ctx.detailedBlock(ROWSET).indexOf(C1) >= 0);
ctx.lrExpandAll(false);
check("collapse all closes it", ctx.detailedBlock(ROWSET).indexOf(C1) >= 0, false);

console.log("\n  ...a family whose children are FILTERED OFF SCREEN does not appear");
// The listings page filters. A group claiming "Variations (2)" with nothing
// under it would be a lie about what is on this screen.
check("no children shown -> no group", ctx.lrGroupRows([LIVE]).groups.length, 0);
check("  and the single row is untouched", ctx.lrGroupRows([LIVE]).flat.length, 1);
check("one child shown -> the group counts ONE",
      ctx.lrGroupRows([kid(C1, "Green"), LIVE]).groups[0].children.length, 1);

console.log("\n  ...nothing is grouped that Amazon did not say was a family");
truthy("the grouping comes from /variations/families",
       /\/variations\/families/.test(SRC));
check("  nothing infers a family from the SKU or the title",
      /startsWith|commonPrefix|title\.slice/.test(SRC), false);
truthy("  and a failed lookup leaves every row flat",
       /LR_FAMILIES = \{\};[\s\S]{0,200}finally/.test(SRC));

console.log("\n%d failed", fails);
process.exit(fails ? 1 : 0);
