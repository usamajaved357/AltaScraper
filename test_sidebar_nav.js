/* One control per setting, and a sidebar that gets out of the way.
 *
 * "i already have the marketplace section now at the left side of the screen so
 *  remove it from the header"
 * "also make the sidebar hideable like in amazon"
 *
 * The marketplace had TWO controls: a strip in the Listings toolbar and a row
 * in the sidebar. The toolbar one was the wider of the two, on a bar already
 * carrying six other buttons.
 *
 * Removing a control is only safe if everything it could do survives it. That
 * strip could also detect marketplaces and set the account's default, and
 * setting a default was reachable from NOWHERE else -- so what is checked here
 * is mostly that those did not go with it.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const HTML = read("templates/dashboard.html");
const SHELL = read("static/js/shell.js");
const SW = read("static/js/switcher.js");
const SIDE = read("static/js/sidebar.js");
const CSS = read("static/css/dashboard.css");

function fnBody(src, name){
  const m = new RegExp("\\bfunction\\s+" + name + "\\s*\\(").exec(src);
  if(!m) return "";
  let i = src.indexOf("{", m.index + m[0].length - 1);
  if(i < 0) return "";
  for(let j = i, depth = 0; j < src.length; j++){
    if(src[j] === "{") depth++;
    else if(src[j] === "}" && --depth === 0) return src.slice(i, j + 1);
  }
  return src.slice(i);
}

console.log("=== the marketplace has ONE control ===");
truthy("the toolbar strip is gone", HTML.indexOf('id="mktswitch"') < 0);
truthy("  the sidebar row is still there", HTML.indexOf('id="nav_mktswitch"') >= 0);
// It also SETTLED state -- WS_MARKET and CUR_SYMBOL. Deleting it with the markup
// would have left prices in the previous account's currency.
const bams = fnBody(SHELL, "buildAccountMktSwitch");
truthy("the function behind it still settles which marketplace is open",
       /WS_MARKET=mkts\[0\]/.test(bams));
truthy("  and the currency that follows from it", /CUR_SYMBOL = mktSymbol\(WS_MARKET\)/.test(bams));
truthy("  but draws no markup", !/innerHTML/.test(bams));
truthy("  and repaints the sidebar row instead", /renderSwitchRows\(\)/.test(bams));

console.log("\n=== nothing the strip could do was lost with it ===");
const oms = fnBody(SW, "openMarketSwitch");
truthy("setting the default moved to the sidebar menu", /setDefaultMarketplace\(\)/.test(oms));
truthy("  offered only when it is not already the default",
       /a\.default_marketplace !== WS_MARKET/.test(oms));
truthy("detecting moved there too", /detectMarketplaces\(a\.id\)/.test(oms));
truthy("  including for an account with none yet, which used to be a dead end",
       /if\(!mkts\.length\)\{[\s\S]{0,400}?_switchMenu/.test(oms));
// draft-only was in the strip as well, but it is on the account pill AND in the
// account switcher, so that one genuinely was a third copy.
truthy("draft-only is still said on the account pill", /draft-only<\/span>/.test(SHELL));
truthy("  and in the account switcher", /"draft-only"/.test(SW));

console.log("\n=== and nothing is left pointing at the removed element ===");
// This one threw the moment the element went, and took navTo and loadRows with
// it -- the dropshipping workspace would have opened onto a dead screen.
truthy("entering dropshipping no longer clears an element that is not there",
       !/getElementById\("mktswitch"\)\.innerHTML/.test(SHELL));
truthy("detect says what it is doing now that it has no strip to say it in",
       /toast\("Asking Amazon which marketplaces/.test(SHELL));
const stray = (SHELL.match(/getElementById\("mktswitch"\)/g) || []).length;
check("only the already-orphaned group switcher still looks for it", stray, 1);
truthy("  and it guards", /getElementById\("mktswitch"\); if\(!host\) return;/.test(SHELL));

console.log("\n=== the sidebar folds to a rail, and stays folded ===");
truthy("there is a toggle", HTML.indexOf('id="navtoggle"') >= 0);
truthy("  loaded from its own file", /sidebar\.js\?v=/.test(HTML));
truthy("folding is a class on the workspace", /classList\.toggle\("navmini"/.test(SIDE));
truthy("  the rail is narrow", /#workspace\.navmini \.sidebar\{width:54px/.test(CSS));
// The labels are bare text nodes -- there is no element around "Listings" -- so
// they cannot be display:none'd. font-size:0 is what collapses a text node.
truthy("  labels collapse without an element to hide",
       /#workspace\.navmini \.navitem\{font-size:0/.test(CSS));
truthy("  and the icon is put back to a readable size",
       /#workspace\.navmini \.navitem \.ti\{font-size:17px/.test(CSS));
truthy("an icon with no label gets a tooltip", /setAttribute\("title", label\)/.test(SIDE));
truthy("  read from the menu itself, not a hardcoded list",
       /querySelectorAll\("#workspace \.sidebar \.navitem"\)/.test(SIDE));
truthy("  without overwriting one written on purpose",
       /if\(!el\.getAttribute\("title"\)\)/.test(SIDE));
truthy("the choice is remembered", /localStorage\.setItem\(NAVMINI_KEY/.test(SIDE));
truthy("  and restored without re-saving it", /setSidebarMini\(want, false\)/.test(SIDE));
truthy("Ctrl\+B toggles it", /String\(ev\.key\)\.toLowerCase\(\) !== "b"/.test(SIDE));
truthy("  but not while you are typing",
       /tag === "INPUT" \|\| tag === "TEXTAREA"/.test(SIDE));
// Charts measure their container, which just changed width by 156px.
truthy("charts are told the width changed", /new Event\("resize"\)/.test(SIDE));

console.log("\n=== the phone layout is untouched ===");
// On a phone the sidebar is already a horizontal strip; a 54px rail there would
// be a column of icons above the page.
const mobile = CSS.slice(CSS.indexOf("#workspace.show{ flex-direction:column;"));
truthy("the mobile rules still turn it into a strip", /flex-direction:row/.test(mobile));
truthy("  and come after the rail rules so they win",
       CSS.indexOf("#workspace.navmini .sidebar{") < CSS.indexOf("#workspace.show{ flex-direction:column;"));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
