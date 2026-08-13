/* A sync must not take the listings off the screen.
 *
 * The bug: loadLiveCatalog() replaced the whole grid with
 * "Rebuilding the listings report on Amazon..." for the 1-4 minutes a forced
 * report takes. The listings already loaded were correct the entire time, and
 * the work was happening on the server -- only the screen was blocked.
 */
const fs = require("fs");
const src = fs.readFileSync("D:/AltaScraper/static/js/miles_template.js", "utf8");

let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(62),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}

function body(fnName) {
  const i = src.indexOf("async function " + fnName + "(");
  if (i < 0) throw new Error("cannot find " + fnName);
  // to the next top-level "async function" / "function " at column 0
  const rest = src.slice(i + 10);
  const j = rest.search(/\n(?:async )?function /);
  return rest.slice(0, j < 0 ? rest.length : j);
}

console.log("=== the single-marketplace path ===");
const one = body("loadLiveCatalog");
check("it paints what is already cached first",
      /_liveShowCached\(key\)/.test(one), true);
check("the grid is only blanked when there is nothing to show",
      /else if\(grid\)\{[\s\S]*Rebuilding the listings report/.test(one), true);
check("the blocking message is no longer unconditional",
      /if\(grid\) grid\.innerHTML = force/.test(one), false);
check("the in-flight note is raised",
      /_liveWorking\(force/.test(one), true);
check("and cleared in a finally, so no path can strand it",
      /finally\{[\s\S]*_liveWorkingDone\(\)/.test(one), true);

console.log("\n=== the all-marketplaces path ===");
const all = body("loadAllMarketplaces");
check("it paints what is already cached first", /_anyCached/.test(all), true);
check("per-marketplace blanking is now conditional",
      /if\(!_anyCached && grid\) grid\.innerHTML/.test(all), true);
check("progress is reported in the label instead",
      /_liveWorking\("fetching marketplace /.test(all), true);
check("the note is cleared when the loop ends",
      /_liveWorkingDone\(\);\s*\/\/ clear the in-flight note/.test(all), true);
check("and when the user navigates away mid-loop",
      /_liveWorkingDone\(\); return;/.test(all), true);

console.log("\n=== one place answers 'how fresh is this?' ===");
const lbl = src.slice(src.indexOf("function updateSyncLabel()"));
check("updateSyncLabel shows the in-flight note when set",
      /if\(LIVE_WORKING\)\{[\s\S]{0,200}genspin/.test(lbl), true);
check("  and returns before the freshness text",
      lbl.indexOf("LIVE_WORKING") < lbl.indexOf("synced just now"), true);
const helpers = (src.match(/function _liveWorking\(/g) || []).length;
check("_liveWorking is defined exactly once", helpers, 1);
check("_liveShowCached is defined exactly once",
      (src.match(/function _liveShowCached\(/g) || []).length, 1);

console.log("\n=== the guards that were already there still are ===");
check("a streaming Preview/Submit still blocks a re-render",
      /if\(window\.RUN_STREAMING\)\{ return; \}/.test(one), true);
check("the account/marketplace race guard survives",
      /const stillHere = /.test(one), true);
check("the hard timeout survives", /const tmo = setTimeout/.test(one), true);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
