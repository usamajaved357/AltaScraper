/* THE FIELD DEFINITIONS MUST NOT TAKE THE WHOLE BROWSER.
 *
 * THE REPORT: "fix the listings loading speed too", and then the Sales screen
 * showing skeletons for half a minute on one account and opening instantly on
 * the others.
 *
 * It was never that account being slow. A browser opens at most six connections
 * to one host. When the rows land, submit.js asks Amazon for the field
 * definitions of every distinct product type in the account, and loadSchemas
 * fired them all at once with Promise.all. Each goes to Amazon, so each is
 * seconds rather than milliseconds.
 *
 * Nestwell Goods has 42 distinct product types. Jack Reacherd has a handful.
 * Measured by driving the real app on a cold start:
 *
 *     before   SALES.busy stuck true past 28s, no cards, no series -- with
 *              /sales/availability, a 31 ms call, sitting in the queue
 *     after    the whole Sales screen finished at +3s, 14 responses in the
 *              first fifteen seconds instead of forty-two
 *
 * Two rules, and this checks both: a few at a time, and after the screen the
 * person actually opened rather than in front of it.
 */
const fs = require("fs");

let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(62),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const how = read("static/js/howworks.js");
const submit = read("static/js/submit.js");

function fnBody(src, name) {
  const m = new RegExp("\\bfunction\\s+" + name + "\\s*\\(").exec(src);
  if (!m) return "";
  let i = src.indexOf("{", m.index + m[0].length - 1);
  if (i < 0) return "";
  for (let j = i, depth = 0; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}" && --depth === 0) return src.slice(i, j + 1);
  }
  return src.slice(i);
}

console.log("\n=== a few at a time ===");
const load = fnBody(how, "loadSchemas");
check("loadSchemas exists", load.length > 0, true);
check("  the number of lanes is named, not buried", /_SCHEMA_LANES/.test(how), true);
check("  and it is small enough to leave the pool free",
      /_SCHEMA_LANES = ([1-4])\b/.test(how), true);
check("  it no longer fires every type at once",
      /Promise\.all\(pts\.map/.test(how), false);
check("  the lanes are capped by how many there are to do",
      /Math\.min\(_SCHEMA_LANES, todo\.length\)/.test(load), true);

console.log("\n=== asked once, however many callers want it ===");
const one = fnBody(how, "_loadOneSchema");
check("there is one place that fetches a schema", one.length > 0, true);
check("  and it shares a request already in the air",
      /_SCHEMA_INFLIGHT\[key\]/.test(one), true);
check("  keyed by marketplace too, so two do not get crossed",
      /pt \+ "\|" \+ mp/.test(one), true);
check("  a forced refresh is never served from one in flight",
      /if\(!force && _SCHEMA_INFLIGHT\[key\]\)/.test(one), true);
check("  and the entry is always cleared",
      /finally\{[\s\S]{0,80}delete _SCHEMA_INFLIGHT\[key\]/.test(one), true);
check("an already-loaded schema is still skipped",
      /SCHEMAS\[pt\] && \(SCHEMAS\[pt\]\.attrs\|\|\[\]\)\.length && !force/.test(load), true);

console.log("\n=== and behind the screen, not in front of it ===");
check("loading the rows does not wait for the schemas",
      /await loadSchemas\(pts\)/.test(submit), false);
check("  they start on a delay",
      /setTimeout\(function\(\)\{\s*loadSchemas\(pts\)/.test(submit), true);
check("  and the screen still redraws when they land",
      /loadSchemas\(pts\)\.then\(function\(\)\{ render\(\); \}\)/.test(submit), true);

console.log("\nFAILURES: %d", fails);
process.exit(fails ? 1 : 0);
