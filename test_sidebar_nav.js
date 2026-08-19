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

console.log("\n=== the rail does not leak onto a phone ===");
// This section used to assert the phone turned the sidebar into a horizontal
// STRIP. That decision was reversed on purpose: Orbit, measured at 390px, parks
// its sidebar off-screen at x:-300 and opens it with one button, and the strip
// was fighting every screen built since. The strip rules are gone from
// dashboard.css and the drawer lives in static/css/mobile.css.
//
// What this section was really protecting still matters, so it is restated
// rather than dropped: `navmini` is a DESKTOP control -- give me back 156px of
// a wide screen -- and it must not follow a person onto a phone, where it would
// turn the drawer into a 54px sliver of unlabelled icons.
const MOBILE = read("static/css/mobile.css");
truthy("the phone sidebar is a drawer, not a strip",
       /#workspace \.sidebar\{[\s\S]*?translateX\(-100%\)/.test(MOBILE.replace(/\s*\{\s*/g, "{")));
truthy("  and dashboard.css no longer has an opinion about it",
       !/\.sidebar\{[^}]*flex-direction:row/.test(CSS.replace(/\s*\{\s*/g, "{")));
truthy("the rail is neutralised at phone width",
       /#workspace\.navmini \.sidebar\{[^}]*width:284px/.test(MOBILE.replace(/\s*\{\s*/g, "{")));
truthy("  including the labels it collapses to font-size:0",
       /#workspace\.navmini \.navitem\{[^}]*font-size:13\.5px/.test(MOBILE.replace(/\s*\{\s*/g, "{")));
truthy("  and the fold control itself, which a drawer has no use for",
       /\.navtoggle\{[^}]*display:none/.test(MOBILE.replace(/\s*\{\s*/g, "{")));

/* ------------------------------------------------------------------------ *
 * EVERY ADDRESSABLE SCREEN IS ALSO A SCREEN navTo() MAKES VISIBLE.
 *
 * navTo keeps two lists of the same thing: one decides which panel gets .show,
 * ALTA_SECTIONS decides which screens have an address and therefore a nav link
 * and an "open in a new tab". Permissions was added to the second and left out
 * of the first, so it had a link, an address, and an onOpen that ran and drew
 * the whole page into a panel that was never shown. It looked like a blank
 * screen with no error, and only opening it in a real browser found it.
 *
 * Listings is excluded on purpose: it is the one panel navTo shows with an
 * explicit style.display rather than the .show class, on its own line above.
 * ------------------------------------------------------------------------ */
console.log("\n== no screen can have an address but no way to be seen ==");
const _navBody = fnBody(SHELL, "navTo");
const _showList = (/\[([^\]]*)\]\.forEach\(s=>\{/.exec(_navBody) || [])[1] || "";
const _shown = _showList.split(",").map(s => s.trim().replace(/^["']|["']$/g, ""))
                        .filter(Boolean);
const _addr = ((/const ALTA_SECTIONS\s*=\s*\[([\s\S]*?)\]/.exec(SHELL) || [])[1] || "")
              .split(",").map(s => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
truthy("navTo has a show-list at all", _shown.length > 10);
truthy("  and an address list", _addr.length > 10);
check("every addressable section is one navTo can show",
      _addr.filter(s => s !== "listings" && _shown.indexOf(s) < 0), []);
check("  and nothing is shown that has no address",
      _shown.filter(s => _addr.indexOf(s) < 0), []);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
