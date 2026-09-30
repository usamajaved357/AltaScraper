/* Repricer rows show, without opening them, whether each SKU is ARMED and which
 * way its price may move (owner, 30 Sep 2026). Runs the real _rpRuleMarks. */
const fs = require("fs"), vm = require("vm"), path = require("path");
const src = fs.readFileSync(path.join(__dirname, "static/js/sourcing_row.js"), "utf8");
let fails = 0;
const check = (label, ok) => { if (!ok) fails++; console.log("  %s %s", label.padEnd(64), ok ? "OK" : "FAIL"); };
const pick = (re) => (src.match(re) || [""])[0];
const s = { _sesc: (x) => String(x).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;") };
vm.createContext(s);
vm.runInContext(pick(/const RP_DIR_MARK = \{[\s\S]*?\n\};/) + "\n"
  + pick(/function _rpRuleMarks\(r\)\{[\s\S]*?\n\}/) + "\nthis.RP_DIR_MARK = RP_DIR_MARK;", s);
const m = (r) => vm.runInContext("_rpRuleMarks(" + JSON.stringify(r) + ")", s);
check("armed shows a green bolt", /ti-bolt rp-g/.test(m({ mode: "live", rule: {} })) && /aria-label="Armed"/.test(m({ mode: "live" })));
check("dry run shows a dim bolt-off", /ti-bolt-off rp-d/.test(m({ mode: "dry_run", rule: {} })));
check("up only -> up arrow", /ti-arrow-up rp-g/.test(m({ rule: { direction: "up_only" } })));
check("up and down -> both arrows", /ti-arrows-vertical/.test(m({ rule: { direction: "up_and_down" } })));
check("match floor -> equals", /ti-equal/.test(m({ rule: { direction: "match_floor" } })));
check("no direction set -> up only, as domain/sourcing.py uses", /ti-arrow-up/.test(m({ rule: {} })) && /ti-arrow-up/.test(m({})));
check("the row draws the marks beside the dot", /_rpRuleMarks\(r\)\s*\n?\s*\+ '<span class="rp-dot/.test(src));
console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
