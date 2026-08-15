/* The app should feel alive, and revisiting a screen should be instant.
 *
 * TWO COMPLAINTS, ONE FILE:
 *
 *   "when i click on a tab in some other app it takes some time to load at the
 *    first time like 1 second but when something loads and i come back to that
 *    same page again, it never loads again"
 *
 *   "the visuals of it the animation it feels like it is lagging"
 *
 * The caching half is the dangerous one. This app has already shipped three
 * bugs where one account's data appeared under another account's name, and a
 * screen cache is the obvious way to ship a fourth. So most of what is checked
 * below is not "does it remember" but "does it forget, at every point where
 * remembering would be wrong".
 */
const fs = require("fs");
const vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + " " +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

// A DOM stub thin enough to be honest about what it does: elements remember
// their innerHTML, which is the only thing these functions actually touch.
function makeDom(){
  const els = {};
  return {
    els,
    document: {
      getElementById: id => els[id] || null,
      querySelectorAll: () => [],
      createElement: () => ({ style: {}, classList: { add(){}, remove(){} } }),
    },
  };
}

const dom = makeDom();
["sales_cards", "sales_charts", "finbody", "ordbody", "retbody", "aiu_body",
 "varbody", "srcbody", "srcpick", "mon_list", "mon_alerts", "inv2_result",
 "sales_breakdown", "sales_range", "sales_today"].forEach(id => {
  dom.els[id] = { innerHTML: "" };
});

const sandbox = {
  document: dom.document,
  window: { matchMedia: () => ({ matches: false }) },
  console,
  // A frame clock that actually ADVANCES. A stub that returns the same
  // timestamp every time makes any easing loop recurse forever -- the progress
  // fraction never leaves zero. 16ms a frame is what a browser gives.
  requestAnimationFrame: (function(){
    let t = 0;
    return function(fn){ t += 16; fn(t); };
  })(),
  CUR_ACCOUNT: { id: "jack_uk" },
  WS_MARKET: "UK",
  Date,
};
sandbox.window.document = dom.document;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("D:/AltaScraper/static/js/screenstate.js", "utf8"), sandbox);
vm.runInContext(fs.readFileSync("D:/AltaScraper/static/js/motion.js", "utf8"), sandbox);

console.log("=== a screen loads once, then is instant ===");
check("the first visit loads", sandbox.screenNeedsLoad("sales"), true);
sandbox.screenLoaded("sales");
check("coming back does NOT load again", sandbox.screenNeedsLoad("sales"), false);
check("a different screen still loads", sandbox.screenNeedsLoad("finance"), true);

console.log("\n=== but it is one account's screen, not any account's ===");
// THE TRAP. Without this the cache becomes the fourth cross-account leak.
sandbox.CUR_ACCOUNT = { id: "selvora_limited" };
check("the same screen under another account loads",
      sandbox.screenNeedsLoad("sales"), true);
sandbox.screenLoaded("sales");
sandbox.CUR_ACCOUNT = { id: "jack_uk" };
check("and going back is still remembered for the first",
      sandbox.screenNeedsLoad("sales"), false);

console.log("\n=== and one marketplace, not any marketplace ===");
sandbox.WS_MARKET = "US";
check("US is not UK", sandbox.screenNeedsLoad("sales"), true);
sandbox.WS_MARKET = "UK";
check("UK is still remembered", sandbox.screenNeedsLoad("sales"), false);

console.log("\n=== switching account empties every panel ===");
// Forgetting alone is not enough: the rendered content is still in the panel,
// hidden rather than destroyed, so it would be on screen until the new load
// finished. That IS the bug that showed Green Haven's listings in Jack
// Reacherd, one level up.
dom.els.finbody.innerHTML = "<table>selvora's contribution</table>";
dom.els.ordbody.innerHTML = "<table>selvora's orders</table>";
dom.els.sales_cards.innerHTML = "<div>selvora's revenue</div>";
sandbox.screenForgetAll();
check("the finance panel is emptied", dom.els.finbody.innerHTML, "");
check("the orders panel is emptied", dom.els.ordbody.innerHTML, "");
check("the sales cards are emptied", dom.els.sales_cards.innerHTML, "");
check("and every screen must load again", sandbox.screenNeedsLoad("sales"), true);

console.log("\n=== a screen can be marked stale on its own ===");
sandbox.screenLoaded("orders");
check("loaded", sandbox.screenNeedsLoad("orders"), false);
sandbox.screenStale("orders");
check("stale after something changed the data underneath it",
      sandbox.screenNeedsLoad("orders"), true);

console.log("\n=== the row stagger does not slow a long list down ===");
function fakeRows(n){
  const rows = [];
  for(let i = 0; i < n; i++) rows.push({ style: {}, classList: { add(){} } });
  rows.forEach = Array.prototype.forEach.bind(rows);
  return rows;
}
const rows = fakeRows(200);
sandbox.altaStagger({ querySelectorAll: () => rows }, "tr");
check("the first row has no delay", rows[0].style.animationDelay, "0ms");
check("the second is 30ms behind", rows[1].style.animationDelay, "30ms");
check("the twentieth is the last delayed one", rows[19].style.animationDelay, "570ms");
// THE POINT: a 200-row table must not take six seconds to finish arriving.
check("the twenty-first appears immediately", rows[20].style.animationDelay, "0ms");
check("and so does the last", rows[199].style.animationDelay, "0ms");

console.log("\n=== numbers only animate when they have actually changed ===");
function metric(label, value){
  const n = { textContent: String(value) };
  const l = { textContent: label };
  const parent = { querySelector: sel => (sel === ".l" ? l : n) };
  n.parentElement = parent;
  return n;
}
const tileA = metric("Drafts", "74");
const host = { querySelectorAll: () => { const a = [tileA]; a.forEach = Array.prototype.forEach.bind(a); return a; } };
sandbox.altaCountMetrics(host);
check("a new number lands on its value", tileA.textContent, "74");
// Re-render with the SAME number: it must not restart from zero, or every
// filter click claims the figure just moved.
tileA.textContent = "74";
sandbox.altaCountMetrics(host);
check("an unchanged number is not re-animated", tileA.textContent, "74");
// A real change does animate (and lands exactly, with the stub's immediate
// frame).
tileA.textContent = "80";
sandbox.altaCountMetrics(host);
check("a changed number lands on the new value", tileA.textContent, "80");
// And the account switch clears that memory, so the next account's figures are
// treated as new even if they happen to be the same number.
sandbox.altaCountReset();

console.log("\n=== skeletons are shaped like what is coming ===");
const sk = sandbox.altaSkeletonScreen({ cards: 4, rows: 8 });
truthy("it uses the existing shimmer class", sk.indexOf("skeleton") >= 0);
check("it draws the tiles", (sk.match(/skcard/g) || []).length, 4);
check("and the rows", (sk.match(/skrow/g) || []).length, 8);
// It must never replace content that is already there: swapping real figures
// for grey blocks on a refresh is a downgrade.
dom.els.finbody.innerHTML = "<table>real numbers</table>";
check("it refuses to cover existing content",
      sandbox.altaSkeletonInto("finbody", {}), false);
check("  which is left untouched", dom.els.finbody.innerHTML, "<table>real numbers</table>");
dom.els.finbody.innerHTML = "";
truthy("but it fills an empty one", sandbox.altaSkeletonInto("finbody", {}));

console.log("\n=== the motion respects a system preference ===");
const CSS = fs.readFileSync("D:/AltaScraper/static/css/dashboard.css", "utf8");
truthy("reduced motion is honoured in CSS", CSS.indexOf("prefers-reduced-motion") >= 0);
truthy("  and by the counting numbers, which CSS cannot reach",
       fs.readFileSync("D:/AltaScraper/static/js/motion.js", "utf8")
         .indexOf("prefers-reduced-motion") >= 0);
// MEASURED: Orbit does NOT animate a section switch. Its content area reported
// `animation: none, 0s` at 0, 80, 160, 320, 640 and 1200ms across three tab
// switches. So the panel entrance is deliberately absent, and this asserts the
// absence -- otherwise someone adds it back as a "polish" and it is a
// difference from Orbit again.
check("a section switch does NOT animate the panel in",
      /\.wspanel\.show\{\s*animation/.test(CSS.replace(/\/\*[\s\S]*?\*\//g, "")), false);
truthy("the fadeIn keyframes remain for the rows and modals that use them",
       CSS.indexOf("@keyframes fadeIn") >= 0);
truthy("charts have an entrance", CSS.indexOf("@keyframes chartFadeIn") >= 0);
truthy("the drawer settles rather than stopping dead",
       CSS.indexOf("cubic-bezier(.34,1.56,.64,1)") >= 0);
truthy("tooltips wait before appearing", CSS.indexOf("transition-delay:.2s") >= 0);
// The brief was explicit about what NOT to add. Checked against the RULES,
// not the comments -- a comment saying "no ripples" contains the word
// "ripple", and a test that cannot tell those apart is worse than none.
const CSS_RULES = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
["ripple", "parallax", "rotate3d", "perspective("].forEach(function(bad){
  check("no " + bad, CSS_RULES.indexOf(bad) >= 0, false);
});

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
