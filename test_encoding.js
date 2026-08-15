/* Is anything the app ships mojibake?
 *
 * UTF-8 read as Latin-1 and written back is how "£" becomes "Â£", "—" becomes
 * "â€”" and "·" becomes "Â·". It is silent: the file still parses, the tests
 * still pass, and the damage only shows on the screen the user is looking at.
 *
 * It has happened three times in this repo, twice from PowerShell's Set-Content
 * writing a file that had non-ASCII in it. A narrower version of this check
 * looked only for the "â€" family and walked straight past a "Â·" that had
 * already shipped into the Traffic table -- so the pattern here is the whole
 * family: a C1-range byte pair is never legitimate text in this codebase.
 */
"use strict";
const fs = require("fs");
const path = require("path");

let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  " + label.padEnd(58) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}

const ROOT = "D:/AltaScraper";
const DIRS = ["static/js", "static/css", "templates", "domain", "routes", "listing",
              "api", "data", "auth"];
const EXT = /\.(js|css|html|py)$/;

/* Â, Ã, â followed by another high byte -- the signature of UTF-8 that has been
 * through a Latin-1 round trip. A lone Â or Ã in real text is vanishingly rare
 * and never appears in this codebase; a PAIR is the giveaway. */
const MOJIBAKE = /[\u00c2\u00c3\u00e2][\u0080-\u00bf]/;

function walk(dir, out) {
  let entries;
  try { entries = fs.readdirSync(dir, {withFileTypes: true}); } catch (e) { return out; }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === "__pycache__" || e.name.startsWith(".")) continue;
      walk(p, out);
    } else if (EXT.test(e.name)) {
      out.push(p);
    }
  }
  return out;
}

const files = [];
DIRS.forEach(d => walk(path.join(ROOT, d), files));

console.log("=== nothing the app ships is mojibake ===");
console.log("  (scanning " + files.length + " files)");
const bad = [];
for (const f of files) {
  let s;
  try { s = fs.readFileSync(f, "utf8"); } catch (e) { continue; }
  const hits = s.match(new RegExp(MOJIBAKE.source, "g"));
  if (hits) {
    const rel = f.replace(ROOT + path.sep, "").replace(/\\/g, "/");
    // Which line, so it can be found rather than hunted for.
    const line = s.split("\n").findIndex(l => MOJIBAKE.test(l)) + 1;
    bad.push(rel + ":" + line + "  " + JSON.stringify([...new Set(hits)].slice(0, 4)));
  }
}
check("no file carries a Latin-1 round trip", bad, []);
bad.forEach(b => console.log("      " + b));

/* The replacement character is the other half of the same failure: text that
 * could not be decoded at all, rather than decoded wrongly. */
console.log("\n=== and nothing carries a replacement character ===");
const repl = [];
for (const f of files) {
  let s;
  try { s = fs.readFileSync(f, "utf8"); } catch (e) { continue; }
  if (s.indexOf("\ufffd") >= 0) {
    repl.push(f.replace(ROOT + path.sep, "").replace(/\\/g, "/"));
  }
}
check("no U+FFFD anywhere", repl, []);

/* A BOM in the middle of a file, or at the start of one that is concatenated,
 * shows up as a stray zero-width space in the output. */
console.log("\n=== and no stray byte-order mark ===");
const boms = [];
for (const f of files) {
  let s;
  try { s = fs.readFileSync(f, "utf8"); } catch (e) { continue; }
  if (s.indexOf("\ufeff", 1) >= 0) {
    boms.push(f.replace(ROOT + path.sep, "").replace(/\\/g, "/"));
  }
}
check("no BOM after the first character", boms, []);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
