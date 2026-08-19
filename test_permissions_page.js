// User permissions, laid out the way Seller Central lays them out.
//
//     "make the user permission a separate page exact copy paste of like amazon
//      and how amazon distributes the permissions columns and when the user do
//      not have access to a certain feature it should not be displayed to it
//      even not in grey color, he should not even see a sign of it"
//
// TWO SEPARATE THINGS, and the second is the one that matters.
//
// THE LAYOUT. It was seventeen dropdowns stacked in a modal. Seller Central
// puts the same decision in a table: the thing being controlled down the left,
// None / View / View & Edit across the top, one radio per row. A column of
// radios can be READ DOWN — you see at a glance that somebody has View on all
// of Money and nothing in Operations. Seventeen dropdowns each have to be
// opened before you know what they say.
//
// THE HIDING. applyPermissionsToUI() used to set opacity to .45, with a comment
// defending it: "rather than removing them, so the app does not look broken".
// That is the wrong trade for a tool handed to people outside the business. A
// greyed-out control still tells you the feature exists, what it is called and
// roughly what it does — and for somebody meant to see one account, the shape
// of everything else is itself information.
//
// AND A GAP FOUND WHILE DOING IT: ten screens added recently had NO feature
// mapping at all, so feature_for() returned nothing and they were governed by
// "any user who may edit". A person with sales set to none could open the
// Business Overview and read every account's revenue.
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

const P = codeOnly(read("static/js/permissions.js"));
const U = codeOnly(read("static/js/users.js"));
const G = read("auth/guard.py");
const HTML = read("templates/dashboard.html");
const CSS = read("static/css/dashboard.css");
const SHELL = codeOnly(read("static/js/shell.js"));

console.log("== no access means no trace, not grey ==");
// The instruction, and the opposite of what the code used to do.
check("the nav item is removed", /el\.style\.display = "none"/.test(U));
check("  not dimmed", !/opacity = "\.45"/.test(U));
// An expander that opens onto nothing is worse than no expander.
check("  and a group that empties disappears with it",
  /kids\.length === gone\.length/.test(U));
check("every nav section maps to a feature", /const SECTION_FEATURE = \{/.test(U));
// View is NOT the same as none, and conflating them would hide screens from
// people who are meant to read them.
check("view-only keeps the screen and loses the buttons",
  /data-readonly/.test(U) && /=== "view"/.test(U));

console.log("== the screens added later are governed at all ==");
// MEASURED: all ten returned nothing from feature_for() before this.
[["/overview", "sales"], ["/leading", "sales"], ["/catalog/products", "listings"],
 ["/categories", "listings"], ["/compliance", "listings"], ["/trackers", "monitor"],
 ["/sqp", "traffic"], ["/drppc", "ppc"], ["/notify", "accounts"]].forEach(function (p) {
  check("  " + p[0] + " belongs to " + p[1],
    new RegExp('\\("' + p[0].replace(/\//g, "\\/") + '",\\s*"' + p[1] + '"\\)').test(G));
});
// Mapped onto the EXISTING features rather than given ten new ones: "may this
// person see turnover" does not become a different question because the screen
// is new.
check("  and no new feature was invented for them",
  !/all_features\[.overview.\]/.test(G));

console.log("== the table reads like Seller Central's ==");
check("three levels across the top", /PERM_LEVELS = \[/.test(P));
check("  none, view, edit", /"none"/.test(P) && /"view"/.test(P) && /"edit"/.test(P));
check("  one radio per level per row", /type="radio"/.test(P));
check("  grouped", /feature_groups/.test(P));
check("  with a set-all on each group", /permSetGroup\(/.test(P));
// A page under an area offers Inherit, stored as ABSENT -- which is what makes
// it follow its area on the server too.
check("  a page can follow its area", /permSet\([^)]*,''\)/.test(P) || /,'\\''\)/.test(P) || /perm-inherit/.test(P));
check("  and inherit is stored as absent, not as a word",
  /delete PERM\.draft\.features\[feat\]/.test(P));

console.log("== the account boundary comes first ==");
// No amount of feature access makes another company's numbers your business.
check("accounts are chosen on the same page", /permToggleWs\(/.test(P));
check("  and it says they are the outer boundary", /outer boundary/.test(P));

console.log("== nothing saves until Save is pressed ==");
// A permissions screen that writes as you click is one where a mis-click is a
// live change.
check("edits go to a draft", /PERM\.draft = \{/.test(P));
check("  and Save is what posts", /permSave/.test(P) && /\/users\/update/.test(P));

console.log("== it is honest about what it is ==");
// Hiding a screen in the browser is courtesy; refusing the request is security.
check("the page says the server enforces it",
  /refuses the request/.test(P) || /server refuses/.test(P));

console.log("== it is a page, not a modal ==");
check("there is a nav item", /data-sec="permissions"/.test(HTML));
check("  and a panel", /id="sec_permissions"/.test(HTML));
check("  the script is loaded", /permissions\.js\?v=/.test(HTML));
check("  navTo knows it", /permissionsOnOpen/.test(SHELL));
check("  and it has its own address", /"permissions"\]/.test(SHELL));
check("  styled as a table", /\.perm-table\{/.test(CSS));

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
