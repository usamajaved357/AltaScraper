// The sidebar's expanding master items.
//
//     "i want the tools to be arranged under the relevant master tool, like we
//      have in amazon, manage inventory expands into manage all inventory, sell
//      globally, fulfillment by amazon etc etc"
//
// The danger in regrouping a menu is not that it looks wrong -- that is visible
// immediately. It is that a screen quietly stops being reachable: it still
// exists, navTo still handles it, the URL still works, and there is simply no
// longer anything to click. Nobody notices until they go looking for it.
//
// So the first and most important thing here is a reachability check: every
// section navTo knows how to show must have a nav item pointing at it.
const fs = require("fs");
const path = require("path");

const FAIL = [];
function check(label, ok) {
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL"));
  if (!ok) FAIL.push(label);
}
function read(p) {
  return fs.readFileSync(path.join(__dirname, p), "utf8");
}
// Comments explain the fault; they must never be what satisfies the test.
function codeOnly(s) {
  return s.split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .map((l) => l.replace(/\s\/\/.*$/, ""))
    .join("\n");
}

const HTML = read("templates/dashboard.html");
const NG = codeOnly(read("static/js/navgroups.js"));
const SHELL = codeOnly(read("static/js/shell.js"));
const CSS = read("static/css/dashboard.css");

console.log("== nothing became unreachable ==");
const navSecs = new Set(
  (HTML.match(/data-sec="([a-z]+)"/g) || []).map((m) => m.split('"')[1]));
// The list navTo iterates to show/hide panels IS the set of real screens.
const listMatch = SHELL.match(/\["imagerefs"[^\]]*\]/);
const known = listMatch ? (listMatch[0].match(/"([a-z]+)"/g) || []).map((s) => s.replace(/"/g, "")) : [];
check("navTo's screen list was found", known.length > 10);
const orphans = known.filter((s) => !navSecs.has(s));
check("  every screen still has something to click on",
  orphans.length === 0 ? true : (console.log("      orphans: " + orphans.join(", ")), false));
check("  listings is still reachable too", navSecs.has("listings"));

console.log("\n== the groups exist and hold the screens ==");
const groups = (HTML.match(/data-grp="([a-z]+)"/g) || []).map((m) => m.split('"')[1]);
check("there are master groups", groups.length >= 6);
check("  each has a children container",
  (HTML.match(/class="navkids"/g) || []).length === groups.length);
check("  each has one master row",
  (HTML.match(/class="navitem navmaster"/g) || []).length === groups.length);
check("  an inventory group, as the request named",
  groups.indexOf("inventory") >= 0);
check("  and each master toggles its own group",
  groups.every((g) => HTML.indexOf("navGroupToggle('" + g + "')") >= 0));

console.log("\n== the group you are in opens itself ==");
// Without this the highlight sits inside a shut drawer and the app looks like
// it has forgotten where you are -- worst on a deep link into a group the user
// last left closed.
check("navTo syncs the open group", /navGroupSyncActive\(sec\)/.test(SHELL));
check("  guarded so nav survives navgroups.js failing to load",
  /typeof navGroupSyncActive === "function"/.test(SHELL));
check("  and the sync opens it", /set\.add\(name\)/.test(NG));
// Derived from the DOM, not a second hand-kept list that would drift the first
// time a screen moved between groups.
check("which group a screen is in is read from the DOM",
  /querySelector\('\.navkids \.navitem\[data-sec="'/.test(NG));

console.log("\n== a shut group cannot hide an alert ==");
// Stock alerts and monitor alerts are the reason those screens exist. A
// collapsed group hiding the one thing that needed attention would make the
// grouping worse than the flat list it replaced.
check("a master carries its shut children's badges", /navGroupBadges/.test(NG));
check("  summed from the children", /_badge'\]/.test(NG));
check("  shown only while the group is shut",
  /classList\.contains\("open"\)/.test(NG));
check("  every group has a badge slot",
  groups.every((g) => HTML.indexOf('id="grpbadge_' + g + '"') >= 0));
check("  styled the same red as the child badges", /\.navmbadge\{/.test(CSS));

console.log("\n== what you opened stays open ==");
check("the open set is stored", /localStorage\.setItem\(NAVGRP_KEY/.test(NG));
check("  and read back", /localStorage\.getItem\(NAVGRP_KEY/.test(NG));
check("  surviving a corrupt value", /catch \(e\)/.test(NG));

console.log("\n== the icon rail is not two taps deep ==");
// The rail is icons only. A master there would be an icon revealing more icons,
// with no label to say what either does -- two taps to reach a screen that was
// one tap away.
check("masters are hidden in the rail", /navmini \.navmaster\{display:none\}/.test(CSS));
check("  and the children show flat", /navmini \.navgroup \.navkids\{max-height:none/.test(CSS));

console.log("\n== the nesting reads as nesting ==");
check("children are indented", /\.navkids \.navitem\{padding-left:30px/.test(CSS));
check("  under a chevron that turns", /\.navgroup\.open .*navchev\{transform:rotate/.test(CSS));
check("  and a shut group still shows it holds you",
  /\.navgroup\.hasactive:not\(\.open\)/.test(CSS));
check("the script is loaded by the page",
  /navgroups\.js\?v=/.test(HTML));

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
