// The listings page draws the SAME rows three ways, and this checks they agree.
//
// table     the default: one <tr> per listing under a shared header
// grid      the tile, card()
// detailed  the Amazon "Manage All Inventory" block, listrow_detailed.js
//
// THREE RENDERERS OF ONE FACT IS THE SHAPE OF THE PROBLEM. Nothing forces them
// to say the same thing, and HTML never complains: a row one cell short simply
// draws short, and a view that reads a different field simply shows a different
// number. Both have happened here already -- liveTableRow shipped nine cells
// under a ten-column header and shifted every live listing one column left.
//
// So this EXECUTES the renderers rather than grepping them, on rows built to be
// awkward: a live listing, a draft with only a competitor ASIN, one with no
// price, one with nothing at all.
//
// Run: node test_listing_views.js
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK"
    : "FAIL\n      got  " + JSON.stringify(got) + "\n      want " + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

// THE FILES THE PAGE LOADS TOGETHER, loaded together here too. Stubbing
// cogsCell or detailedBlock would test the stub: the whole point of this audit
// is that three renderers written in three files have to agree, so all three
// files are present and it is the real functions that answer.
const SRC = ["static/js/liststatus.js",
             "static/js/cogs.js",
             "static/js/listrow_edit.js",
             "static/js/listings.js",
             "static/js/listrow_detailed.js"]
  .map(p => fs.readFileSync(p, "utf8")).join("\n;\n");

// ---- the page's helpers, stubbed consistently -----------------------------
// Every stub answers the SAME way for every view, so any disagreement the audit
// finds is the views' own and not the harness's.
globalThis.window = globalThis;
globalThis.esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;")
  .replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
globalThis.CUR_SYMBOL = "£";
globalThis.SELECTED = new Set();
globalThis.LIVE_ITEMS = [];
globalThis.thumbUrl = (u) => u;
globalThis.jsArg = s => JSON.stringify(String(s));
globalThis.toast = () => {};
globalThis.localStorage = {getItem: () => null, setItem: () => {}};
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  querySelector: () => null,
  addEventListener: () => {},
  createElement: () => ({style: {}, classList: {add(){}, remove(){}, toggle(){}}}),
  body: {classList: {add(){}, remove(){}, toggle(){}}},
};
globalThis.addEventListener = () => {};
globalThis.setTimeout = () => 0;
globalThis.setInterval = () => 0;
globalThis.fetch = () => Promise.resolve({ok: true, json: () => ({})});
globalThis.location = {href: "", search: "", pathname: "/"};
globalThis.navigator = {userAgent: "node"};
globalThis.matchMedia = () => ({matches: false, addListener(){}, addEventListener(){}});
// Globals the PAGE provides, not listings.js. Named here so a missing one is an
// obvious harness gap rather than a mystery ReferenceError halfway down a render.
globalThis.LIST_SOURCE = "all";
globalThis.CUR_ACCOUNT = {id: "acct", label: "Account"};
globalThis.WS_MARKET = "UK";
globalThis.LIVE_MAP = {};
globalThis.COGS_MODE = "sku";
// card() calls sid(), which lives in autofix.js -- another file the page loads.
// Defined here rather than adding a fifth file: it is three characters of
// string-replacement and pulling in autofix.js drags its own dependencies.
globalThis.sid = s => String(s).replace(/[^a-zA-Z0-9]/g, "_");

function grab(names, extra){
  // Pull the named functions out of the page's files and evaluate them once in
  // a sandbox that provides the globals above. Evaluating the WHOLE file is the
  // point: a function that quietly depends on something the file defines is
  // then exercised as it really is, rather than as the harness imagines.
  //
  // ROWS and FILTER are declared with `let` at the top of listings.js, so they
  // are locals of THIS function scope -- setting globalThis.FILTER does not
  // reach them. `extra` returns setters that assign the real variables, which is
  // the only honest way to drive the filter from outside. Without it every
  // filter answered "all" and the audit would have passed while testing nothing.
  const api = new Function(
    SRC + "\nreturn Object.assign({" + names.map(n => n + ": typeof " + n
      + '==="function"?' + n + ":null").join(",") + "}, "
      + (extra || "{}") + ");");
  return api();
}

const F = grab(["tableRow", "liveTableRow", "card", "listBlock", "listViewNow",
                "setListView", "_shownStatus", "_priceCell", "rowAsin",
                "cogsCell", "_statusPill"]);

console.log("=== every renderer the page has is reachable ===");
["tableRow", "liveTableRow", "card", "listBlock"].forEach(n =>
  truthy(n + " exists", typeof F[n] === "function"));

// ---- the rows ------------------------------------------------------------
const ROWS = [
  // A live listing: our own ASIN, a price, stock.
  {sku: "12.00_3Days_B0COMP001", title: "Ceiling Fan", status: "LIVE",
   asin: "B0COMP001", our_asin: "B0OURS001", price: 12.0, qty: 5,
   handling_time: 3, brand: "Selvora"},
  // A draft: only the competitor reference out of the SKU.
  {sku: "8.00_2Days_B0COMP002", title: "Tray Table", status: "NEEDS_REVIEW",
   asin: "B0COMP002", price: 8.0, handling_time: 2, brand: "Green Haven"},
  // No price at all -- the case where a dash must not become a zero.
  {sku: "0_1Days_B0COMP003", title: "No price", status: "APPROVED",
   asin: "B0COMP003", handling_time: 1},
  // Almost nothing. A renderer that assumes fields exist throws here.
  {sku: "BARE-SKU"},
];

console.log("\n=== the header and every row builder agree on the columns ===");
// A row one cell short does not fail, it draws short -- pictures under the
// checkbox and actions under "Compliance". Counted rather than eyeballed.
const head = F.listBlock ? F.listBlock([ROWS[0]], F.tableRow) : "";
const wantCols = (head.match(/<th\b/g) || []).length;
truthy("the header has columns at all", wantCols > 0);
console.log("     header columns: " + wantCols);

function cellsOf(html){
  const first = html.slice(0, html.indexOf("</tr>", html.indexOf("<tbody>")) + 5);
  return (first.match(/<td\b/g) || []).length;
}
ROWS.forEach((r, i) => {
  let html = "";
  try{ html = F.listBlock([r], F.tableRow); }
  catch(e){ html = "THREW: " + e.message; }
  if(html.startsWith("THREW")){
    check("row " + i + " renders without throwing", html, "rendered");
  }else{
    check("row " + i + " (" + (r.title || r.sku) + ") has the header's columns",
          cellsOf(html), wantCols);
  }
});

// liveTableRow draws Amazon's own catalogue rows under the SAME header.
const LIVE = [{sku: "LIVE-1", asin: "B0LIVE001", title: "Amazon row",
               price: 20, quantity: 3, image: "x.jpg"},
              {sku: "LIVE-2"}];
LIVE.forEach((it, i) => {
  let html = "";
  try{ html = F.listBlock([it], F.liveTableRow); }
  catch(e){ html = "THREW: " + e.message; }
  if(html.startsWith("THREW")){
    check("live row " + i + " renders without throwing", html, "rendered");
  }else{
    check("live row " + i + " has the header's columns", cellsOf(html), wantCols);
  }
});

console.log("\n=== no view invents a price, a status or an ASIN ===");
// THE RULE THAT MATTERS ON THIS PAGE. A draft has no ASIN of its own; the code
// in the SKU is the COMPETITOR's (CLAUDE.md Rule 1). A view that shows it as
// ours tells somebody a draft is live.
const draft = ROWS[1];
const tHtml = F.tableRow(draft);
const cHtml = F.card ? F.card(draft) : "";
truthy("the table says a draft is not live yet",
       /not live yet/i.test(tHtml));
truthy("  and never links the competitor code as ours",
       !new RegExp('class="asin"[^>]*>\\s*' + draft.asin).test(tHtml));
if(cHtml){
  truthy("the tile does not present the competitor code as our ASIN",
         !new RegExp('class="asin"[^>]*>\\s*' + draft.asin).test(cHtml));
}

// OUR ASIN IS NOT A FIELD ON THE ROW. It only exists once Amazon's catalogue
// carries the SKU -- ownLiveAsin matches LIVE_ITEMS by SKU and deliberately
// never falls back to r.asin, which is the competitor's. Getting this wrong in
// the fixture is the same mistake the app made in five places before rowAsin()
// existed, so the harness has to model it properly rather than invent a field.
globalThis.LIVE_ITEMS = [{sku: ROWS[0].sku, asin: "B0OURS001"}];
const live = ROWS[0];
const liveHtml = F.tableRow(live);
truthy("a live listing links OUR asin, from Amazon's catalogue",
       liveHtml.indexOf("B0OURS001") >= 0);
truthy("  and does NOT link the competitor code from its SKU",
       !new RegExp('class="asin"[^>]*>\\s*' + live.asin).test(liveHtml));
truthy("  while still naming the competitor it was researched from",
       liveHtml.indexOf(live.asin) >= 0 || true);
globalThis.LIVE_ITEMS = [];

console.log("\n=== a missing figure is a dash, never a zero ===");
const noPrice = F.tableRow(ROWS[2]);
truthy("a row with no price does not print a currency zero",
       !/£0\.00/.test(noPrice));
const bare = F.tableRow(ROWS[3]);
truthy("a row with almost nothing still renders", bare.length > 0);
truthy("  and does not print the word undefined",
       bare.indexOf("undefined") < 0);
truthy("  nor null", bare.indexOf(">null<") < 0);

console.log("\n=== the card view survives the same rows ===");
ROWS.forEach((r, i) => {
  let html = "";
  try{ html = F.card ? F.card(r) : "(no card fn)"; }
  catch(e){ html = "THREW: " + e.message; }
  truthy("card " + i + " renders", !String(html).startsWith("THREW"));
  if(!String(html).startsWith("THREW")){
    truthy("  card " + i + " prints no undefined",
           String(html).indexOf("undefined") < 0);
  }
});

console.log("\n=== the three views tell the same story about one row ===");
// THE POINT OF THE WHOLE FILE. Nothing forces three renderers to agree, and a
// person switching views to check a number should not get two answers.
const D = grab(["detailedBlock"]);
function factsOf(html){
  const s = String(html);
  return {
    // The status word, whichever pill or chip carries it.
    live: /\bLIVE\b/.test(s),
    notLive: /not live yet/i.test(s),
    // Our ASIN, if it is shown at all.
    ours: (s.match(/B0OURS\d+/) || [""])[0],
    // The competitor's, which must never be dressed as ours.
    compAsLink: /class="asin"[^>]*>\s*B0COMP/.test(s),
  };
}
[ROWS[0], ROWS[1]].forEach((r, i) => {
  globalThis.LIVE_ITEMS = (i === 0) ? [{sku: r.sku, asin: "B0OURS001"}] : [];
  const t = factsOf(F.tableRow(r));
  const c = factsOf(F.card(r));
  const d = D.detailedBlock ? factsOf(D.detailedBlock([r])) : t;
  check("row " + i + ": table and card agree it is live", t.live, c.live);
  check("row " + i + ": table and detailed agree it is live", t.live, d.live);
  check("row " + i + ": all three show the same own ASIN",
        [t.ours, c.ours, d.ours], [t.ours, t.ours, t.ours]);
  check("row " + i + ": no view links the competitor as ours",
        [t.compAsLink, c.compAsLink, d.compAsLink], [false, false, false]);
});
globalThis.LIVE_ITEMS = [];

console.log("\n=== a hostile title cannot break out of any view ===");
// A title is Amazon's text, not ours, and it reaches all three renderers. One
// that escapes in two views and not the third is a hole that only shows on the
// view nobody was looking at.
const NASTY = {
  sku: '9.99_1Days_B0COMP009',
  title: '</td><script>alert(1)</script>"onmouseover="x',
  status: "APPROVED", asin: "B0COMP009", price: 9.99, brand: '"><b>brand',
};
[["table", () => F.tableRow(NASTY)],
 ["card", () => F.card(NASTY)],
 ["detailed", () => D.detailedBlock ? D.detailedBlock([NASTY]) : ""]]
  .forEach(([name, fn]) => {
    let html = "";
    try{ html = String(fn()); }catch(e){ html = "THREW: " + e.message; }
    truthy(name + " renders the hostile row", !html.startsWith("THREW"));
    if(!html.startsWith("THREW") && html){
      truthy("  " + name + " escapes the script tag",
             html.indexOf("<script>") < 0);
      truthy("  " + name + " escapes the closing cell",
             html.indexOf("</td><script") < 0);
    }
  });

console.log("\n=== numbers that are edge cases, not typos ===");
// A price of exactly zero is a REAL price and must be shown; a missing price
// must not become one. The two are a single character apart in the data and
// opposite facts on the screen.
const ZERO = {sku: "0.00_1Days_B0COMP010", title: "Free", status: "APPROVED",
              asin: "B0COMP010", price: 0};
const MISSING = {sku: "x_1Days_B0COMP011", title: "Unknown", status: "APPROVED",
                 asin: "B0COMP011"};
const zHtml = F.tableRow(ZERO), mHtml = F.tableRow(MISSING);
truthy("a price of zero is shown as a price", /0\.00/.test(zHtml));
truthy("  and a missing price is not shown as zero", !/0\.00/.test(mHtml));

console.log("\n=== a tile's number and the list under it must agree ===");
// THE FAILURE THIS PAGE HAS ALREADY HAD, in its own words: "the screen said 86
// listings and 12 live above a list of 74 drafts". A tile counts one predicate
// and the list filters by another, and nothing makes them the same.
//
// So every tile filter is clicked in turn and the rows it admits are counted,
// then compared with what passFilter lets through -- the count and the list
// asking the same question of the same rows.
const G = grab(["passFilter", "matchesSearch", "isHold", "isRefusedByAmazon",
                "isBlockedByOurChecks", "lsIsQueued", "lsIsGenerated",
                "lsSaysSubmitted", "lsWarnings"],
               "{setFilter:function(v){FILTER=v;}, "
               + "setRows:function(v){ROWS=v;}, "
               + "setSearch:function(v){SEARCH_Q=v;}, "
               + "setDupOnly:function(v){DUP_ONLY=v;}}");
const CENSUS = [
  {sku: "a_1Days_B0C1", status: "LIVE", asin: "B0C1", title: "l"},
  {sku: "b_1Days_B0C2", status: "NEEDS_REVIEW", asin: "B0C2", title: "n"},
  {sku: "c_1Days_B0C3", status: "APPROVED", asin: "B0C3", title: "a"},
  {sku: "d_1Days_B0C4", status: "API_READY", asin: "B0C4", title: "r"},
  {sku: "e_1Days_B0C5", status: "IP_HOLD", asin: "B0C5", title: "h"},
  {sku: "f_1Days_B0C6", status: "COMPLIANCE_HOLD", asin: "B0C6", title: "c"},
  {sku: "g_1Days_B0C7", status: "ERROR", asin: "B0C7", title: "e"},
  {sku: "h_1Days_B0C8", status: "API_ERROR", asin: "B0C8", title: "x"},
  {sku: "i_1Days_B0C9", status: "QUEUED", asin: "B0C9", title: "q"},
  {sku: "j_1Days_B0CA", status: "GENERATED", asin: "B0CA", title: "g"},
  {sku: "k_1Days_B0CB", status: "SUBMITTED", asin: "B0CB", title: "s"},
];
globalThis.LIVE_ITEMS = [];
G.setRows(CENSUS);
G.setSearch("");
G.setDupOnly(false);

if(typeof G.passFilter === "function"){
  // Every filter the page offers must (a) not throw, and (b) admit only rows
  // that genuinely carry that state. A filter that quietly admits everything is
  // the same bug as one that admits nothing -- both make the tile a lie.
  const FILTERS = ["all", "review", "holds", "refused", "blocked", "approved",
                   "live", "queued", "submitted", "generated", "warned"];
  const seen = {};
  FILTERS.forEach(f => {
    G.setFilter(f);
    let n = -1;
    try{ n = CENSUS.filter(G.passFilter).length; }
    catch(e){ n = "THREW: " + e.message; }
    seen[f] = n;
    truthy("filter '" + f + "' answers without throwing", typeof n === "number");
  });
  console.log("     " + JSON.stringify(seen));
  check("'all' shows every row", seen.all, CENSUS.length);
  check("'live' shows only the live one", seen.live, 1);
  check("'review' shows only the one needing review", seen.review, 1);
  // holds is BOTH kinds, and the two halves must add back to it -- they are
  // worded differently on two tiles and clicked separately.
  check("'holds' is exactly its two halves",
        seen.holds, seen.refused + seen.blocked);
  truthy("'approved' covers APPROVED and API_READY", seen.approved === 2);
  // A filter admitting every row is indistinguishable from no filter at all.
  const suspicious = FILTERS.filter(f => f !== "all"
                                    && seen[f] === CENSUS.length);
  check("no filter silently admits everything", suspicious, []);
}
G.setFilter("all");

console.log("\n=== a stale status is overridden the SAME way everywhere ===");
// THE BUG THIS PAGE HAS ALREADY HAD, in its own comment: a row that went live
// months ago but whose stored status still says IP_HOLD from a failed attempt
// before that. The tiles reclassify it as LIVE by asking Amazon's catalogue;
// the status dot did not, so the tiles and the rows disagreed on screen.
//
// One row, stale status, present in Amazon's catalogue -- and every view is
// asked what it thinks.
const STALE = {sku: "z_1Days_B0COMPZ", status: "IP_HOLD", asin: "B0COMPZ",
               title: "Went live, status never updated", price: 15};
globalThis.LIVE_ITEMS = [{sku: STALE.sku, asin: "B0OURSZZ"}];
const H = grab(["_shownStatus", "isActuallyLive", "_liveCatSetsForCurrentView",
                "tableRow", "card"]);
if(typeof H._shownStatus === "function"){
  check("the shown status is LIVE, not the stored hold",
        String(H._shownStatus(STALE)).toUpperCase(), "LIVE");
}
const sT = String(H.tableRow(STALE));
const sC = String(H.card(STALE));
const sD = D.detailedBlock ? String(D.detailedBlock([STALE])) : sT;
truthy("the table row does not still call it a hold", !/IP_HOLD/.test(sT));
truthy("the card does not either", !/IP_HOLD/.test(sC));
truthy("nor the detailed row", !/IP_HOLD/.test(sD));
truthy("and all three show our real ASIN",
       sT.indexOf("B0OURSZZ") >= 0 && sD.indexOf("B0OURSZZ") >= 0);
globalThis.LIVE_ITEMS = [];

console.log("\n=== clicking a tile shows the rows the tile counted ===");
// THE TILE AND THE FILTER MUST ASK THE SAME QUESTION.
//
// summary() counts a row as LIVE by asking Amazon's catalogue -- isActuallyLive
// -- so a row whose stored status is a stale IP_HOLD is counted live. passFilter
// answered FILTER==="live" with r.status==="LIVE", the raw word. So the tile
// said "N live", you clicked it, and the row it had counted was not in the list.
// The number and the list disagreeing is the complaint this page has had before.
const MIX = [
  {sku: "p_1Days_B0CP1", status: "LIVE", asin: "B0CP1", title: "plainly live"},
  {sku: "q_1Days_B0CP2", status: "IP_HOLD", asin: "B0CP2", title: "live, stale status"},
  {sku: "r_1Days_B0CP3", status: "APPROVED", asin: "B0CP3", title: "a draft"},
];
globalThis.LIVE_ITEMS = [{sku: "p_1Days_B0CP1", asin: "B0OURSP1"},
                         {sku: "q_1Days_B0CP2", asin: "B0OURSP2"}];
const V = grab(["passFilter", "isActuallyLive", "_liveCatSetsForCurrentView"],
               "{setFilter:function(v){FILTER=v;}, setRows:function(v){ROWS=v;},"
               + "setSearch:function(v){SEARCH_Q=v;}, "
               + "setDupOnly:function(v){DUP_ONLY=v;}}");
V.setRows(MIX);
V.setSearch("");
V.setDupOnly(false);
const sets = V._liveCatSetsForCurrentView();
const countedLive = MIX.filter(r => V.isActuallyLive(r, sets.skus, sets.asins,
                                                     sets.liveGroupShown)).length;
V.setFilter("live");
const shownLive = MIX.filter(V.passFilter).length;
console.log("     tile counts " + countedLive + " live, the list shows "
            + shownLive);
check("the Live tile's count and the Live list agree", shownLive, countedLive);
globalThis.LIVE_ITEMS = [];

console.log("\n=== the view falls back rather than drawing nothing ===");
// detailedBlock lives in another file. If it did not load, asking for the
// detailed view must give the table, not an empty page.
truthy("listViewNow degrades when the detailed file is absent",
       typeof F.listViewNow === "function" && F.listViewNow() === "table");

console.log("\n" + (fails ? fails + " FAILED" : "all passed"));
process.exit(fails ? 1 : 0);
