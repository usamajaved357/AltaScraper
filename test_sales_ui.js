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
check("navTo shows/hides it", /"miles","sales","ppc"/.test(shell), true);
check("navTo calls salesOpen", /sec==="sales"[\s\S]{0,60}salesOpen/.test(shell), true);
check("the URL allow-list (browser) has it", /"sales","ppc"/.test(shell), true);
check("the URL allow-list (server) has it", /"generate", "sales", "ppc"/.test(ui), true);

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

console.log("\n=== the tint: one hue, five steps, per row ===");
const tint = (v,lo,hi) => vm.runInContext(`_sTint(${v},${lo},${hi})`, sb);
check("the lowest value gets the faintest step", tint(0, 0, 100), "rgba(45,212,168,.05)");
check("the highest gets the strongest", tint(100, 0, 100), "rgba(45,212,168,.34)");
check("a flat row is not shaded at all", tint(5, 5, 5), "");
check("no data is not shaded", tint(null, 0, 100), "");
const steps = new Set([0,10,30,60,100].map(v => tint(v,0,100)));
check("five classes, not a continuous ramp", steps.size <= 5, true);
check("every step is the SAME hue",
      [...steps].every(s => s.startsWith("rgba(45,212,168,")), true);

console.log("\n=== every cell prints its number (the grid is the table view) ===");
check("the cell text is the formatted value", /_sNum\(v, m\.kind, ser\.currency\)/.test(js), true);
check("  and is written into the cell, not only the tooltip",
      />'\+_sEsc\(txt\)\+'<\/td>/.test(js), true);
check("shading is computed per METRIC row",
      /m\.cells\.filter[\s\S]{0,200}Math\.min/.test(js), true);

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
