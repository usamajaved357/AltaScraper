// The business overview — every account, month by month.
//
//   Orbit's Brand Overview.
//
// The ONE screen in this app that is not scoped to the account you are standing
// in. Every other screen answers a question about one account, which is right —
// it is what stopped one account's orders appearing on another's. But "how is
// the business doing" is not a question about one account, and until now the
// only way to see six together was to open each in turn and add up by hand.
//
// TWO WAYS THIS SCREEN WOULD LIE, and both were live before being fixed:
//
//   ADDING CURRENCIES. jack_uk trades in pounds, sheelady_us in dollars.
//   £500 + $500 is not 1000 of anything, and one "total revenue" across them
//   would be an invented figure at the top of the most-read page. Orbit has a
//   USD/EUR toggle, so it converts somewhere; converting needs a rate for the
//   day of each sale, this app has none, and inventing one is worse than
//   showing two totals.
//
//   ZERO WHERE NOTHING WAS SYNCED. series() returns a row for EVERY day in the
//   window whether or not anything was stored, and an unsynced day carries
//   ordered_sales=null rather than 0. Summing gives 0 either way — so the first
//   version drew a flat line of zeros for three accounts and an "unknown
//   currency: 0.00, 0 units, 3 accounts" total card. That is a business shown
//   as trading nothing when the truth is nobody has looked.
const fs = require("fs");
const path = require("path");

const FAIL = [];
function check(label, ok) {
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL"));
  if (!ok) FAIL.push(label);
}
function read(p) { return fs.readFileSync(path.join(__dirname, p), "utf8"); }
function codeOnly(s) {
  return s.split("\n")
    .filter((l) => !l.trim().startsWith("//") && !l.trim().startsWith("#"))
    .map((l) => l.replace(/\s\/\/.*$/, ""))
    .join("\n");
}

const PY = codeOnly(read("routes/overview_routes.py"));
const JS = codeOnly(read("static/js/overview.js"));
const HTML = read("templates/dashboard.html");
const SHELL = codeOnly(read("static/js/shell.js"));

console.log("== nothing is recomputed ==");
// The figures come from the same function the Sales screen draws, so the two
// cannot disagree.
check("it reads sales_data.series", /from domain import sales_data as _sd/.test(PY));
check("  and buckets with its own bucket()", /_sd\.bucket\(rows, "month"\)/.test(PY));
check("  and aggregates with its own aggregate()", /_sd\.aggregate\(/.test(PY));
check("  and takes profit from profit_for", /_sd\.profit_for\(/.test(PY));
// profit_for withholds the figure unless EVERY unit is costed. Passed straight
// through: None means "not knowable", never zero.
check("  a profit that cannot be known is not turned into 0",
  !/profit\s*or\s*0/.test(PY));

console.log("== currencies are never added ==");
check("totals are grouped by currency", /totals\.setdefault\(cur/.test(PY));
check("  and there is no single grand total", !/grand_total/.test(PY));
check("  the screen says why", /currency_note/.test(PY) && /currency_note/.test(JS));
check("  naming the exchange-rate problem", /exchange rate/.test(PY));

console.log("== nothing stored is not zero sales ==");
// The fault the live run exposed.
check("a month knows whether anything was stored",
  /"stored": stored/.test(PY) || /stored = any\(/.test(PY));
check("  measured on the null, not the sum",
  /ordered_sales"\) is not None/.test(PY));
check("  an account knows too", /"has_data"/.test(PY));
check("the grid draws a dot, not a zero", /!m \|\| !m\.stored/.test(JS));
check("  and says what the dot means", /nothing stored for this month/.test(JS));
check("  an unsynced account says so rather than showing a total",
  /not synced/.test(JS));

console.log("== an unsynced account is not a total of anything ==");
// A card reading "? — 0.00, 0 units, 3 accounts" is three accounts nobody has
// synced, and putting it beside a real total invites it to be read as one.
check("accounts with no data are left out of the totals",
  /if not b\["has_data"\] or not b\["currency"\]/.test(PY));
check("  but are still listed", /"unsynced": unsynced/.test(PY));
check("  and named in words", /unsynced_note/.test(PY) && /unsynced_note/.test(JS));

console.log("== the current month is marked ==");
// A chart that does not say so shows every business falling off a cliff on the 3rd.
check("the partial month is flagged", /"partial":/.test(PY));
check("  and marked on screen", /ovw-star|ovw-partial/.test(JS));
check("  with the reason on hover", /not finished/.test(JS));

console.log("== it deliberately ignores the active account ==");
check("it loops every connected account", /for a in accts:/.test(PY));
check("  and does not scope to one", !/_active_account\(\)/.test(PY));
check("  which is said out loud in the file",
  /not scoped/i.test(read("routes/overview_routes.py")));

console.log("== it is reachable ==");
check("there is a nav item", /data-sec="overview"/.test(HTML));
check("  a panel", /id="sec_overview"/.test(HTML));
check("  the script is loaded", /overview\.js\?v=/.test(HTML));
check("  and navTo knows it", /"overview"/.test(SHELL) && /ovwLoad/.test(SHELL));

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
