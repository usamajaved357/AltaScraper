/* The Sales screen: wired everywhere it needs to be, and honest about missing data.
 *
 * The two rules this screen is built on, asserted rather than assumed:
 *   1. No data is an em-dash, never a 0. A zero claims you sold nothing.
 *   2. Colour never carries a value alone — every cell prints its number, so the
 *      grid IS the accessible table view.
 */
const fs = require("fs");
const vm = require("vm");
let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(62),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const js = read("static/js/sales.js");
const shell = read("static/js/shell.js");
const tpl = read("templates/dashboard.html");
const css = read("static/css/dashboard.css");
const ui = read("routes/ui_routes.py");

console.log("=== wired in every place a section has to be listed ===");
check("nav item exists", /data-sec="sales"/.test(tpl), true);
check("  under Analytics",
      tpl.indexOf('<div class="slbl">Analytics</div>') < tpl.indexOf('data-sec="sales"'), true);
check("the panel exists", /id="sec_sales"/.test(tpl), true);
check("the script is loaded", /\/static\/js\/sales\.js\?v=/.test(tpl), true);
// These three used to pin Sales by its NEIGHBOUR in each list -- "miles","sales"
// ,"ppc" and so on -- so adding Traffic between Sales and PPC broke all three
// while nothing was wrong. The invariant is that "sales" is IN each list, not
// what happens to sit next to it.
const _inList = function(src, marker, want){
  const i = src.indexOf(marker);
  if(i < 0) return false;
  const end = src.indexOf("]", i);
  return end > i && src.slice(i, end).indexOf('"' + want + '"') >= 0;
};
// TWO OF THE FOUR LISTS NO LONGER EXIST, and that is the fix rather than a
// regression: both were second copies of "what screens are there", and both had
// drifted from the menu.
//
//   navTo kept its own array of panels to show and hide, beginning
//   ["imagerefs", ...]. It now derives them from ALTA_SECTIONS, so the pair
//   cannot disagree -- they had, and `permissions` plus all four keyword
//   screens rendered into panels that were never shown.
//
//   ui_routes kept a typed _SECTIONS tuple of twelve, written when there were
//   twelve. The app has forty, so the other twenty-eight answered a refresh or
//   a bookmark with a plain-text 404. It now reads data-sec straight out of the
//   template.
//
// Greping for either literal is greping for the bug. What is asserted instead
// is that each list is DERIVED, and that Sales survives the derivation.
check("navTo shows/hides it via the one section list",
      /ALTA_SECTIONS\.filter\(s => s !== "listings"\)\.forEach/.test(shell), true);
check("navTo calls salesOpen", /sec==="sales"[\s\S]{0,60}salesOpen/.test(shell), true);
check("the URL allow-list (browser) has it",
      _inList(shell, "const ALTA_SECTIONS", "sales"), true);
check("the server reads its allow-list from the menu, not a typed copy",
      /data-sec="\(\[\\w-\]\+\)"/.test(ui), true);
check("  so Sales is deep-linkable because the menu offers it",
      /data-sec="sales"/.test(tpl), true);

// And the same four places for Traffic, which is the screen most likely to be
// half-wired: a section that renders but cannot be reached by URL looks fine
// until someone bookmarks it.
console.log("\n=== Traffic is wired in all four places too ===");
check("nav item exists", /data-sec="traffic"/.test(tpl), true);
check("the panel exists", /id="sec_traffic"/.test(tpl), true);
check("the script is loaded", /\/static\/js\/traffic\.js\?v=/.test(tpl), true);
check("  after sales.js, which it borrows _sNum and salesCombo from",
      tpl.indexOf("/static/js/sales.js") < tpl.indexOf("/static/js/traffic.js"), true);
// Same two corrections as for Sales above: navTo's own panel array and the
// server's typed _SECTIONS tuple are both gone, replaced by one derivation each.
check("navTo calls trafficOnOpen",
      /sec==="traffic"[\s\S]{0,60}trafficOnOpen/.test(shell), true);
check("the URL allow-list (browser) has it",
      _inList(shell, "const ALTA_SECTIONS", "traffic"), true);
check("  and the menu offers it, which is what the server reads",
      /data-sec="traffic"/.test(tpl), true);
check("and the route is registered on the app",
      /_traffic_routes\.register\(app/.test(
        require("fs").readFileSync("D:/AltaScraper/dashboard.py", "utf8")), true);

console.log("\n=== the product filter actually filters ===");
// It was wired to salesReload(), which rebuilds the query from SALES.asin --
// a value the select never wrote to. Choosing a product re-requested the range
// it already had, so the filter looked wired and did nothing.
check("the select writes its value into the state",
      /onchange="salesSetAsin\(this\.value\)"/.test(tpl), true);
check("  and that handler sets SALES.asin",
      /function salesSetAsin\(v\)\{[\s\S]{0,120}SALES\.asin\s*=/.test(js), true);
check("  then reloads", /function salesSetAsin\(v\)\{[\s\S]{0,200}salesReload\(\)/.test(js), true);
check("options come from what SOLD, not the live catalogue",
      /\/sales\/products\?/.test(js), true);
check("  so the catalogue global is no longer read", /LIVE_ITEMS/.test(js), false);

console.log("\n=== a custom range exists and is not half-applied ===");
check("Custom is offered as a preset", /\["custom","Custom"\]/.test(js), true);
check("  with two date inputs", /id="sales_start"/.test(tpl) && /id="sales_end"/.test(tpl), true);
check("  hidden until Custom is chosen", /id="sales_custom"[^>]*display:none/.test(tpl), true);
check("  and not requested until BOTH are filled",
      /if\(SALES\.preset==="custom" && !\(SALES\.start && SALES\.end\)\) return;/.test(js), true);

console.log("\n=== availability is asked BEFORE the numbers ===");
check("it fetches availability", /\/sales\/availability\?/.test(js), true);
check("  before summary and series",
      js.indexOf("/sales/availability?") < js.indexOf("/sales/summary?"), true);

console.log("\n=== formatting: no data is NOT zero ===");
const sb = {window:{}, document:{getElementById:()=>null, querySelectorAll:()=>[]},
            fetch:()=>Promise.reject(), console};
sb.window.document = sb.document;
vm.createContext(sb);
vm.runInContext(js, sb);
const num = (v,k,c) => vm.runInContext(`_sNum(${JSON.stringify(v)},${JSON.stringify(k)},${JSON.stringify(c||"GBP")})`, sb);
check("null renders as an em-dash", num(null, "count"), "\u2014");
check("undefined too", num(undefined, "count"), "\u2014");
check("an actual zero still renders as 0", num(0, "count"), "0");
check("money carries its symbol", num(1234.5, "money", "GBP"), "\u00a31,234.50");
check("percentages keep two places", num(7, "pct"), "7.00%");
const short = (v,k,c) => vm.runInContext(`_sShort(${JSON.stringify(v)},${JSON.stringify(k)},${JSON.stringify(c||"GBP")})`, sb);
check("big figures shorten", short(12431, "money", "GBP"), "\u00a312.4k");
check("  and millions", short(2400000, "count"), "2.4m");
check("  but missing stays an em-dash", short(null, "money"), "\u2014");

// THE TINT CHANGED SHAPE. It used to take (value, rowLow, rowHigh, key) and
// shade by how big the number was on its row -- so the biggest Amazon fee was
// the darkest green on the sheet. It now takes (value, previousValue, key,
// goodDirection) and shades by the effect on PROFIT of the change against the
// column before. test_heatmap_colours.js covers that logic in full; this only
// checks the shape and the things this file has always guarded.
console.log("\n=== the tint: four steps, by change, per row ===");
const tint = (v,p,k,g) => vm.runInContext(
  `_sTint(${JSON.stringify(v)},${JSON.stringify(p)},${JSON.stringify(k||"ordered_sales")},${JSON.stringify(g||"up")})`, sb);
check("a small change is faint", tint(103, 100), "rgba(45,212,168,.10)");
check("a big one is strongest", tint(140, 100), "rgba(45,212,168,.46)");
check("a flat cell is not shaded at all", tint(100, 100), "");
check("no data is not shaded", tint(null, 100), "");
check("nothing to compare against is not shaded", tint(100, null), "");
const steps = new Set([103, 107, 115, 140].map(v => tint(v, 100)));
check("four classes, not a continuous ramp", steps.size <= 4, true);
check("a rise in an income row is green",
      [...steps].every(s => s.startsWith("rgba(45,212,168,")), true);
// ...and the same rise in a COST row is the other hue. This is the whole point.
check("the same rise in a cost row is red",
      tint(140, 100, "referral_fees", "down").startsWith("rgba(239,68,68,"), true);

console.log("\n=== every cell prints its number (the grid is the table view) ===");
check("the cell text is the formatted value",
      /_sNum\(shown, m\.kind, ser\.currency\)/.test(js), true);
check("  and is written into the cell, not only the tooltip",
      />'\+_sEsc\(txt\)\+'<\/td>/.test(js), true);
check("shading is computed against the previous COLUMN of the same row",
      /const prev = \(i > 0\) \? shownAt\[i - 1\] : null/.test(js), true);

console.log("\n=== deltas carry direction and words, not colour alone ===");
check("an arrow is rendered", /\u2191|\u2193/.test(js), true);
// The words moved: the delta now names the earlier FIGURE ("was: £1,234 ↑ +5.2%",
// or "LY:" when the comparison is a year back), which is Orbit's layout and says
// more than "vs previous" did -- you can see what it is being compared against,
// not just that it is.
check("and the earlier figure is named, not just the change",
      /prevLabel\|\|"was"/.test(js), true);
check("  and it says LY only when the comparison really is a year",
      /compareKind === "year" \? "LY" : "was"/.test(js), true);
check("no baseline says so instead of 0%", /no earlier period/.test(js), true);
check("rising ad spend is NOT a win",
      /c\.key\s*===\s*"spend"\)\s*\?\s*!up\s*:\s*up/.test(js), true);
// The arrow still points the way the number went; only the COLOUR flips. The
// badge is now built in one place (_sBadge), which draws the arrow from the
// number, so this is the one case on the screen where the two deliberately
// disagree and the class is corrected afterwards.
check("  but the arrow still follows the number",
      /good !== up/.test(js), true);

console.log("\n=== one change badge, not three ===");
/* Rule 12. "↑ 16.9 %" was written out three times -- Live Sales, Week to Date,
 * and every stat card -- and the three had already drifted: two put no space
 * before the % and the third added a sign the others did not.
 *
 * MEASURED off Orbit's own badges: a space after the arrow AND a space before
 * the per-cent sign. "↑ 16.9 %", "↓ 0.4 %".
 */
{
  const _sEsc = x => String(x == null ? "" : x);
  const a = js.indexOf("function _sBadge");
  const b = js.indexOf('/* "Pacific Time');
  check("there is a single badge builder", a >= 0 && b > a, true);
  const badge = new Function("_sEsc", js.slice(a, b) + "; return _sBadge;")(_sEsc);
  const plain = h => h.replace(/<[^>]*>/g, "");
  check("Orbit's spacing, up", plain(badge(16.9, {})), "↑ 16.9 %");
  check("Orbit's spacing, down", plain(badge(-0.4, {})), "↓ 0.4 %");
  check("a flat change gets neither arrow", plain(badge(0, {})), "→ 0.0 %");
  check("the stat cards add the sign", plain(badge(5.2, {sign: true})), "↑ +5.2 %");
  check("nothing to compare draws nothing", badge(null, {}), "");
  check("and a non-number is not drawn as 0", badge(undefined, {}), "");
  // Nobody builds one by hand any more.
  check("no hand-rolled badge is left",
        (js.match(/<span class="pct-badge /g) || []).length, 1);
}

console.log("\n=== yesterday's orders, from the feed Amazon itself shows ===");
/* "but in amazn i am able to see the sales from yesterday accurately, why not
 * here". Because Seller Central reads the Orders API and this chart read the
 * Sales & Traffic report, which runs a day or two behind.
 *
 * MEASURED on jack_uk: the report had NOTHING for 14 August; the Orders API had
 * three orders, GBP 102.21. Both count an order on the day it was PLACED, so
 * they are the same measurement and the later one may fill the earlier one's
 * gap -- which is not the same as mixing in the finance feed, dated by when the
 * money moved and belonging to different days.
 */
check("there is a loader for the live tail", /async function salesLoadRecent/.test(js), true);
check("  it asks for a few days, not a month",
      /\/sales\/recent\?days=6&/.test(js), true);
check("  and it is not awaited, so the chart draws from the report first",
      /salesLoadRecent\(\)\.catch/.test(js), true);
check("  it redraws from the series in hand rather than refetching",
      /SALES\._live = j\.days;[\s\S]{0,900}salesDrawCharts\(SALES\.series\)/.test(js), true);
// AND THE CARDS. They come from /sales/summary, which reads the report alone, so
// without this a week whose only trade was yesterday reads "0 orders, GBP 0" on
// the cards while the chart beside them shows three. Reported exactly that way.
check("  and the cards are redrawn too, so they cannot disagree with the chart",
      /SALES\._live = j\.days;[\s\S]{0,900}salesDrawCards\(SALES\.data/.test(js), true);
check("there is one place that decides what the live feed adds",
      /function _sLiveAdd/.test(js), true);
check("  and it only fills days Amazon has NOT reported",
      /if\(v !== null && v !== undefined\) return;\s*\/\/ Amazon has spoken/.test(js), true);
check("  so a reported zero is left alone",
      /a day Amazon HAS reported is never touched/.test(js), true);

console.log("\n=== 'no earlier period' means what it says ===");
/* Reported: every card on a week that had a perfectly ordinary week before it
 * read "no earlier period". Two different facts were being given one sentence:
 * the period before had NOTHING (a real figure, and a rise from zero has no
 * percentage), versus there IS no period before. Only the second deserves that
 * wording; the first says the app cannot see history when it can.
 */
check("a zero earlier period is reported as a zero, not as an absence",
      /no % from zero/.test(js), true);
check("  and a genuinely absent one still says so",
      /: "no earlier period"/.test(js), true);
check("  the two are told apart by whether a previous figure exists",
      /const had = \(prevValue !== null && prevValue !== undefined\);/.test(js), true);
// THE RULE THAT KEEPS THE CHART AND THE GRID AGREEING: a delivered figure is
// never overwritten, only a missing one is filled.
check("only a MISSING day is filled",
      /if\(v !== null && v !== undefined\) return v;/.test(js), true);
// THE RULE THAT STOPS A FOURTH CROSS-ACCOUNT LEAK.
check("the live figures are cleared before each load",
      /SALES\._live = null;/.test(js), true);
check("  next to where the comparison is cleared, on every reload",
      /SALES\.compare = null;[\s\S]{0,400}SALES\._live = null;/.test(js), true);
// Matched on a run of text that is not split across a `+`, since these strings
// are built by concatenation and a longer phrase spans two source lines.
check("the days that were filled are named on the panel",
      /counted live from the Orders/.test(js), true);

console.log("\n=== the bars are labelled with what is IN them ===");
/* Reported: "the graph shows i generated an order on 7 9 and 12th aug but i did
 * not a single in these days". Reproduced exactly on a 14-day range: that
 * account's report feed had delivered nothing, so the chart fell back to the
 * finance feed and drew a bar on each of those three SETTLEMENT days -- under a
 * key that read "Orders".
 */
check("the bar label follows the basis, rather than always saying Orders",
      /label: \(orderBasis \? "Orders" : "Units shipped"\)/.test(js), true);
check("  and the money-basis note says the bars are not orders",
      /the gold bars are <b>units/.test(js) && /<b>not orders<\/b>/.test(js), true);

console.log("\n=== the P&L heatmap's own toolbar ===");
/* MEASURED on Orbit's P&L Heatmap, control by control:
 *
 *   "33/33 Metrics"       10px/500, transparent, radius 6, padding 4px 12px
 *   PRODUCTS              11px/600 uppercase, rgb(156,163,175)
 *   All Products (166)    13px/400 on rgb(45,50,66), radius 8
 *   GRANULARITY           Day | Week | Month, active 600 on #fbbf24, radius 4
 *   Last: 8/13
 *   PERIOD                7d | 14d | 30d | 60d | 90d | Custom
 *   Export
 *   COGS  Actual - $22.36 avg/unit - 99.7% of shipped units covered
 */
check("the toolbar is built in one place", /function _sGridTools/.test(js), true);
["Products", "Granularity", "Period", "Metrics", "COGS", "Export"].forEach(function(w){
  check("  it carries " + w, js.indexOf(w) >= 0, true);
});
check("the granularity choices are Orbit's",
      /\[\["day", "Day"\], \["week", "Week"\], \["month", "Month"\]\]/.test(js), true);
check("  and the periods are too",
      /"7d"[\s\S]*"14d"[\s\S]*"30d"[\s\S]*"60d"[\s\S]*"90d"/
        .test(js.slice(js.indexOf("_S_GRID_PERIODS"),
                       js.indexOf("_S_GRID_PERIODS") + 300)), true);

// THE GRID HAS ITS OWN PERIOD, which is the point of the control: the shape of
// a month is a chart question and "which week was expensive" is a grid one.
check("the grid can be taken off the screen's range",
      /gridGran:"", gridPreset:""/.test(js), true);
check("  empty means FOLLOW the screen, so the common case costs no request",
      /if\(!SALES\.gridGran && !SALES\.gridPreset\)\{[\s\S]{0,160}salesDrawGrid\(SALES\.series\)/.test(js), true);
check("  and there is a way back to matching the charts",
      /function salesGridFollow/.test(js), true);
check("  which is offered on screen once they differ",
      js.indexOf("Match the charts") >= 0, true);
// Same endpoint as the chart, so a figure cannot be produced two ways.
{
  const from = js.indexOf("async function salesLoadGrid");
  const body = js.slice(from, js.indexOf("\n}", from));
  // _sFetch, not a bare fetch: every /sales/ call on this screen goes through
  // the one wrapper that attaches the account and drops a reply that arrives
  // after the workspace has changed. See test_request_account.py.
  check("the grid's own fetch uses the same series endpoint",
        from >= 0 && /_sFetch\("\/sales\/series\?/.test(body), true);
  check("  carrying the same product filter and marketplace",
        /asin=/.test(body) && /marketplace=/.test(body), true);
}
check("  and a failed fetch leaves the grid as it was, not blank",
      /catch\(e\)\{[\s\S]{0,220}\}finally\{[\s\S]{0,120}gridBusy = false/.test(js), true);

// RULE 12: the product filter is the one that already exists.
check("no second product filter was invented",
      /function salesFocusProducts/.test(js), true);
check("  it sends you to the existing one",
      /getElementById\("sales_asin"\)/.test(js), true);

console.log("\n=== the metrics picker ===");
check("rows can be switched off", /function salesMetricToggle/.test(js), true);
check("  remembered between visits", /alta_grid_hidden/.test(js), true);
check("  a section with every row hidden loses its heading too",
      /\(s\.keys \|\| \[\]\)\.some\(visible\)/.test(js), true);
check("  and switching them ALL off explains itself rather than drawing nothing",
      js.indexOf("Every row is switched off") >= 0, true);

console.log("\n=== the COGS strip says what THIS app knows ===");
// Orbit's reads "99.7% of shipped units covered". Ours counts SKUs with a cost
// against SKUs without one, which is a different measurement -- borrowing the
// wording would be a wrong number with a right-sounding label.
// Checked against the CODE, not the comments: the comment beside it quotes
// Orbit's wording to explain why ours differs, and a test that cannot tell
// those apart would fail on the explanation for the thing it is asserting.
const jsRules = js.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/^\s*\/\/[^\n]*$/gm, " ");
check("it reports SKUs, which is what is actually counted",
      jsRules.indexOf("of SKUs costed") >= 0, true);
check("  never claims to have measured units",
      jsRules.indexOf("of shipped units covered") >= 0, false);
check("  and the average is worked out from the grid's own figures",
      /const c = sum\("cogs"\), u = sum\("units_shipped"\)/.test(js), true);

console.log("\n=== a card that could not load says so ===");
/* FOUND BY DRIVING THE LIVE APP: /sales/today answers 502 on sheelady_us --
 * Amazon's own words are "Unauthorized: Access to requested resource is
 * denied", an SP-API role that account's app registration has not been granted.
 * The three UK accounts answer 200 to the same call, so it is that account's
 * authorisation and not this code.
 *
 * The screen's response was to blank the card. An empty region reads as "no
 * sales today", which is a different fact from "Amazon refused to say" -- and
 * only one of them tells you what to go and fix.
 */
{
  const _sEsc = x => String(x == null ? "" : x);
  const a = js.indexOf("function _sCardError");
  const b = js.indexOf("/* THE CHANGE BADGE");
  check("there is one place that reports a failed card", a >= 0 && b > a, true);
  const fn = new Function("_sEsc", js.slice(a, b) + "; return _sCardError;")(_sEsc);
  let el = {innerHTML: ""};
  fn(el, "[{'code': 'Unauthorized', 'message': 'Access to requested resource is denied.'}]",
     "Live Sales");
  check("it names the card", el.innerHTML.indexOf("Live Sales") >= 0, true);
  check("  says Amazon refused, not that there were no sales",
        el.innerHTML.indexOf("Amazon refused") >= 0, true);
  check("  points at where the fix actually is",
        el.innerHTML.indexOf("Seller Central") >= 0, true);
  check("  and shows Amazon's own words, which name the missing role",
        el.innerHTML.indexOf("Unauthorized") >= 0, true);
  // A different failure must NOT be described as a permissions problem.
  el = {innerHTML: ""};
  fn(el, "NetworkError: failed to fetch", "Live Sales");
  check("an ordinary failure is not mislabelled as a permission",
        el.innerHTML.indexOf("Seller Central") >= 0, false);
  check("  but it is still reported",
        el.innerHTML.indexOf("could not be loaded") >= 0, true);
  // And the call sites use it rather than blanking.
  check("the Live Sales loader no longer blanks itself",
        /if\(!j \|\| !j\.ok\)\{ el\.innerHTML="";/.test(js), false);
  check("  it reports instead", /_sCardError\(el, \(j && j\.error\)/.test(js), true);
  check("  and so does the catch",
        /catch\(e\)\{ _sCardError\(el, String\(e\)/.test(js), true);
}

console.log("\n=== an empty period is said, not left blank ===");
// The same fault in a second place: a period with no columns drew nothing at
// all, so the top half of the screen was empty with no explanation. Seen on a
// live account whose range genuinely had no figures.
check("the charts region explains an empty period",
      js.indexOf("Nothing to chart for this period yet") >= 0, true);
check("  and offers Sync as the fix",
      /Nothing to chart[\s\S]{0,240}Sync/.test(js), true);

console.log("\n=== ads are declared missing, never zero ===");
check("the card says 'not connected'", /not connected/.test(js), true);
check("and the reason is shown", /sum\.ads_note/.test(js), true);

console.log("\n=== refetch holds the old render, no skeleton flash ===");
check("previous render dimmed", /grid\.style\.opacity=".45"/.test(js), true);
check("  and restored", /grid\.style\.opacity=""/.test(js), true);

console.log("\n=== filters: ONE row, above what they scope ===");
check("a single filter bar", (tpl.match(/id="sales_filters"/g) || []).length, 1);
check("  above the cards", tpl.indexOf('id="sales_filters"') < tpl.indexOf('id="sales_cards"'), true);
check("  and above the grid", tpl.indexOf('id="sales_filters"') < tpl.indexOf('id="sales_grid"'), true);

console.log("\n=== typography rules from the dataviz method ===");
check("the big stat figure is NOT tabular",
      /\.stat-card \.stat-number\{font-variant-numeric:normal\}/.test(css), true);
check("  but grid cells ARE (they stack vertically)",
      /\.salesgrid td\{[^}]*tabular-nums/.test(css), true);
check("the metric column stays put while dates scroll",
      /\.salesgrid th\.mcol\{position:sticky;left:0/.test(css), true);
check("the grid scrolls in its own box, not the page",
      /\.salesgridwrap\{overflow:auto/.test(css), true);
check("no dashed rules anywhere in the grid",
      /\.salesgrid[^}]*dashed/.test(css), false);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
