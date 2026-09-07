/* Expanding a sidebar group must not close the drawer.
 *
 *     "when i click on the dropdown menu from the side drawer for example
 *      inventory it should displays the 2 sub tabs under it by expanding
 *      inventory option, but it closes the drawer immediately"
 *
 * The group headings are markup like
 *     <div class="navitem navmaster" onclick="navGroupToggle('inventory')">
 * so they look and sit like every other nav row -- and that is exactly why the
 * drawer's delegated close handler caught them. Pressing one expanded the group
 * and shut the drawer in the same click, so the children it had just revealed
 * were never on screen long enough to be read.
 *
 * The rule the handler already stated was right and simply predates the groups:
 * "Only things that GO somewhere." A master goes nowhere.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = "D:\\AltaScraper";

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(60) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                              + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const MN = fs.readFileSync(path.join(ROOT, "static/js/mobilenav.js"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "templates/dashboard.html"), "utf8");

console.log("=== every group heading is marked as one ===");
const masters = HTML.match(/class="navitem navmaster"/g) || [];
const toggles = HTML.match(/navGroupToggle\(/g) || [];
truthy("there are group headings", masters.length > 0);
// A master WITHOUT the class would be caught by the close handler again, and
// the symptom -- one group that cannot be opened -- is invisible until someone
// happens to want that group.
check("  every navGroupToggle row carries .navmaster",
      masters.length, toggles.length);

console.log("\n=== the close handler lets a heading through ===");
truthy("it checks for a master", /t\.closest\("\.navmaster"\)/.test(MN));
// ORDER DECIDES IT: .navmaster is also a .navitem, so the exclusion has to run
// before the rule that closes on .navitem.
const iMaster = MN.indexOf('t.closest(".navmaster")');
const iItem = MN.indexOf('t.closest(".navitem, .backlink")');
truthy("  and does so BEFORE the navitem rule", iMaster > 0 && iMaster < iItem);
truthy("  returning rather than closing",
       /t\.closest\("\.navmaster"\)\) return;/.test(MN));

console.log("\n=== but a real destination still closes it ===");
// The whole point of the handler: the drawer is an overlay at every width, so
// leaving it open would cover the screen the user just asked for.
truthy("a navitem still closes the drawer",
       /t\.closest\("\.navitem, \.backlink"\)\) mnavClose\(\);/.test(MN));
truthy("  and the scrim still closes it",
       /scrim\.addEventListener\("click", mnavClose\)/.test(MN));
truthy("  and Escape still closes it",
       /ev\.key === "Escape" && mnavIsOpen\(\)/.test(MN));

console.log("\n=== the behaviour, exercised ===");
// The handler, lifted out and run against stand-in elements, so this asserts
// what it DOES rather than how it reads.
function el(classes, parentClasses){
  const own = classes.split(" ");
  const all = own.concat((parentClasses || "").split(" ").filter(Boolean));
  return {
    closest: function(sel){
      // Enough of closest() for these selectors: any class in the chain.
      const wanted = sel.split(",").map(s => s.trim().replace(/^\./, ""));
      return all.some(c => wanted.indexOf(c) >= 0) ? {} : null;
    },
  };
}
let closed = 0;
const body = MN.split('side.addEventListener("click", function(ev){')[1]
               .split("\n    });")[0];
const handler = new Function("ev", "mnavIsOpen", "mnavClose",
                             body.replace(/mnavClose\(\)/g, "mnavClose()"));
const run = function(target){
  closed = 0;
  handler({target: target}, function(){ return true; },
          function(){ closed++; });
  return closed;
};

check("clicking a group heading does NOT close",
      run(el("navitem navmaster")), 0);
check("  clicking a child inside a group DOES close",
      run(el("navitem", "navkids navgroup")), 1);
check("  clicking an ordinary nav row DOES close", run(el("navitem")), 1);
check("  clicking a back link DOES close", run(el("backlink")), 1);
// The account switcher and marketplace picker open their own menus inside the
// sidebar; closing under them would shut the menu just opened.
check("  clicking neither leaves it open", run(el("switchrow")), 0);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
