/* Orbit layout: additions only. Nothing removed, nothing moved, nothing broken.
 *
 * The brief's own critical rule is that no feature, route, endpoint or control
 * may change -- this is layout. So most of these checks are about what did NOT
 * happen: the nav still has every item in its original order, the sidebar is
 * still 210px, the palette is untouched, and no onclick moved.
 */
const fs = require("fs");
let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(60),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
const css = fs.readFileSync("D:/AltaScraper/static/css/dashboard.css", "utf8");
const tpl = fs.readFileSync("D:/AltaScraper/templates/dashboard.html", "utf8");

console.log("=== nothing was mangled ===");
// A real ellipsis as the canary: if the file is ever written back in the wrong
// encoding this is the character that mangles first. (It read "Loading
// workspaces\u2026" until the home page was removed and the grid became the accounts
// panel -- the check is about the encoding, not the word.)
check("the template is still valid UTF-8", /Loading accounts\u2026/.test(tpl), true);
check("  no mojibake in the template", /\u00e2\u20ac/.test(tpl), false);
check("  nor in the stylesheet", /\u00e2\u20ac/.test(css), false);
check("braces balance", (css.match(/\{/g) || []).length === (css.match(/\}/g) || []).length, true);

console.log("\n=== 1. content padding, from ONE number ===");
check("the panel padding is a variable", /\.wspanel\{display:none;padding:var\(--wspad,32px\)\}/.test(css), true);
check("the bleed derives from the same variable",
      /\.wstoolbar\.bleed\{[\s\S]{0,120}calc\(var\(--wspad,32px\) \* -1\)/.test(css), true);
check("every inline bleed style is gone", /margin:-20px -20px 16px/.test(tpl), false);
// AT LEAST the seven that were converted. Pinning an exact count made this fail
// the moment a new section was added -- which is the test objecting to ordinary
// growth, not catching a fault. What matters is that none was left inline.
check("  replaced by the class",
      (tpl.match(/class="wstoolbar bleed"/g) || []).length >= 7, true);
check("the listings screen is padded to match",
      /#sec_listings > \.datasrc/.test(css) && /main#grid\{padding:18px var\(--wspad,32px\)\}/.test(css), true);

console.log("\n=== 2. section labels, reusing the existing class ===");
// Match the RULE and the ATTRIBUTE, not the words. The comment above the labels
// names the class it deliberately did not create, and a check that trips over
// its own explanation is a worse test than none.
check("no second label class was invented",
      /\.nav-section-label\s*\{/.test(css) || /class="nav-section-label"/.test(tpl), false);
check("Operations label added", /<div class="slbl">Operations<\/div>/.test(tpl), true);
check("Analytics label added", /<div class="slbl">Analytics<\/div>/.test(tpl), true);
check("Tools label still there", /<div class="slbl">Tools<\/div>/.test(tpl), true);
check("the label spacing matches the audit",
      /\.slbl\{letter-spacing:\.06em;padding:16px 16px 4px\}/.test(css), true);
// A label directly above a hidden item would render with nothing under it.
const milesAt = tpl.indexOf('id="nav_harvest"');
const lastLabelBefore = tpl.lastIndexOf('class="slbl"', milesAt);
const between = tpl.slice(lastLabelBefore, milesAt);
check("no label sits directly above the hidden Supplier Import",
      (between.match(/class="navitem"/g) || []).length > 0, true);

console.log("\n=== NOTHING WAS REORDERED OR REMOVED ===");
// "Sync" was renamed to "Compare with Amazon" deliberately: asked what that
// screen was for, the honest answer was that its name described a mechanism
// rather than a job, and it opened on a diagnostic matrix. The guard here is
// about ORDER and PRESENCE -- that nothing was silently dropped or shuffled --
// so it follows the rename rather than pinning a label we chose to improve.
const NAV = ["Listings", "Image refs", "Brand setup", "Account &amp; sheets",
             "Generate &amp; submit", "PPC", "Inventory", "Compare with Amazon",
             "ASIN Monitor", "Supplier Import", "Research ASIN",
             "AI &amp; settings"];
let pos = -1, ordered = true;
for (const item of NAV) {
  const at = tpl.indexOf(item, pos + 1);
  if (at < 0 || at < pos) { ordered = false; console.log("     out of order:", item); }
  pos = at;
}
check("all 12 nav items present, in the original order", ordered, true);
check("the sidebar is still 210px", /\.sidebar\{width:210px/.test(css), true);
check("the top bar is still there", /class="appbar"/.test(tpl), true);

console.log("\n=== 3. tables: presentation only ===");
check("numbers align", /table td\{font-variant-numeric:tabular-nums\}/.test(css), true);
check("headers are uppercase", /table th\{text-transform:uppercase/.test(css), true);
check("a generic row hover exists", /table tbody tr:hover > td/.test(css), true);
check("  and it is weak enough for specific tables to win",
      /\.lt tr:hover/.test(css) || /\.lt tbody tr:hover/.test(css), true);

console.log("\n=== 4,6,8. new components, not yet used anywhere ===");
for (const [name, cls] of [["stat cards", "stat-card"], ["skeleton", "skeleton"],
                           ["chart subtitle", "chart-subtitle"]]) {
  check(name + " is defined", new RegExp("\\." + cls + "\\{").test(css), true);
}
check("skeleton respects reduced motion",
      /prefers-reduced-motion[\s\S]{0,80}\.skeleton\{animation:none\}/.test(css), true);

console.log("\n=== 5. focus ring ===");
check("it is focus-VISIBLE, not focus",
      /\*:focus-visible\{outline:none;box-shadow:0 0 0 3px rgba\(45,212,168,\.3\)\}/.test(css), true);
check("  so a mouse click leaves no glow", /\*:focus\{/.test(css), false);
check("the accent stays teal, not the audit's gold",
      /rgba\(45,212,168/.test(css), true);

console.log("\n=== 7. drawer: only what was missing ===");
check("the shadow was added", /\.drawer\{box-shadow:-8px 0 32px rgba\(0,0,0,\.5\)\}/.test(css), true);
check("its width was NOT changed", /\.drawer\{position:fixed[\s\S]{0,80}width:520px/.test(css), true);
check("its existing slide is untouched",
      /transform:translateX\(100%\);transition:transform \.2s ease/.test(css), true);

console.log("\n=== no JS logic was touched ===");
check("every onclick in the nav is unchanged",
      (tpl.match(/navTo\('(listings|imagerefs|setup|generate|ppc|inventory|sync|monitor|miles)'\)/g) || []).length, 9);
check("no route or endpoint appears in the CSS", /\/(live|users|input)\//.test(css), false);

console.log("\n=== the stylesheet is well formed ===");
/* A comment closed early leaves its remaining lines as loose text in the
 * stylesheet -- the browser discards from there to the next brace and takes
 * real rules with it, silently. It happened while writing the Sales column rule
 * below, and nothing in this suite would have caught it.
 */
{
  check("every comment is closed exactly once",
        (css.match(/\/\*/g) || []).length, (css.match(/\*\//g) || []).length);
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  // A line of prose left outside a comment has spaces and no CSS punctuation.
  const stray = stripped.split("\n").map(l => l.trim()).filter(l =>
    l && !/[{}:;,]/.test(l) && /\s/.test(l) && !/^[@.#\w\-\[\]>+~*()="'\/]+$/.test(l));
  check("no loose prose outside a comment", stray.length, 0);
  if (stray.length) console.log("      first:", JSON.stringify(stray[0].slice(0, 70)));
}

console.log("\n=== the Sales column is Orbit's ===");
{
  const flat = css.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\s+/g, "");
  // MEASURED on Orbit: a 260px sidebar, a <main> with 32px padding, and a
  // container inside it at max-width 1400, centred. border-box here, so the
  // padding comes out of the width: 1400 + 32 + 32 = 1464.
  check("the sales screen is held to Orbit's column width",
        /#sec_sales\{[^}]*max-width:1464px/.test(flat), true);
  check("  and centred in whatever is left",
        /#sec_sales\{[^}]*margin-left:auto/.test(flat), true);
  // Two EQUAL columns. auto-fit drops to one the moment the container is a few
  // pixels short of twice the minimum, and both cards jump to full width --
  // which is the "uneven".
  check("the two top cards are two equal columns",
        /\.sales-toprow\{[^}]*grid-template-columns:1fr1fr/.test(flat), true);
  check("  and never auto-fit, which changes column count mid-resize",
        /\.sales-toprow\{[^}]*auto-fit/.test(flat), false);
  check("they stack on a narrow screen, as Orbit's do on a phone",
        /@media\(max-width:900px\)\{\.sales-toprow\{grid-template-columns:1fr;?\}/.test(flat), true);
  // Rule 12: one definition. There were two of each, and the later silently
  // added to or overrode the earlier, so the comments described a layout the app
  // was not using.
  const rules = css.replace(/\/\*[\s\S]*?\*\//g, "");
  check("only one .sales-toprow rule outside the media query",
        (rules.match(/^\.sales-toprow\s*\{/gm) || []).length, 1);
  check("and only one #sec_sales rule",
        (rules.match(/^#sec_sales\s*\{/gm) || []).length, 1);
}

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
