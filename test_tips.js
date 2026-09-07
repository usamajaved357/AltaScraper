/* The ⓘ marks carry their statement into a styled bubble.
 *
 *     "see there are I circular marks everywhere in the app including the ppc
 *      analytics page, they should show some statements"
 *
 * They always carried one -- in title="", the browser's native tooltip, which
 * waits about a second, draws in the OS's style and flattens the newlines these
 * statements are written with. So the text is MOVED to data-tip and drawn by
 * dashboard.css.
 *
 * Two things this has to get right and would fail silently at:
 *   the title is REMOVED, or both tooltips appear, the native one on a delay
 *   and on top of the styled one;
 *   only the HELP marks are touched. Plenty of elements in this app have a
 *   legitimate native tooltip -- a truncated product name, a table cell -- and
 *   hijacking every title in the app would be a large change nobody asked for.
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

const TIPS = fs.readFileSync(path.join(ROOT, "static/js/tips.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "static/css/dashboard.css"), "utf8");

// A tiny DOM: enough for the pass to walk and set attributes.
function el(cls, title){
  const a = {class: cls, title: title};
  return {
    className: cls,
    _a: a,
    classList: {
      _s: new Set(),
      add: function(){ for(const c of arguments) this._s.add(c); },
      remove: function(){ for(const c of arguments) this._s.delete(c); },
      has: function(c){ return this._s.has(c); },
    },
    getAttribute: function(k){ return this._a[k] === undefined ? null : this._a[k]; },
    setAttribute: function(k, v){ this._a[k] = v; },
    removeAttribute: function(k){ delete this._a[k]; },
    hasAttribute: function(k){ return this._a[k] !== undefined; },
    getBoundingClientRect: function(){ return {left: 500, right: 520}; },
  };
}

const marks = [
  el("infodot", "Sessions ÷ page views, over the whole window."),
  el("ppc-i", "Spend ÷ attributed ad sales.\nBlank when the ads made no sales."),
  el("ppc-q", "Spend over sales, across the rows shown."),
];
const plain = el("productname", "A very long product name that is truncated");

const doc = {
  readyState: "complete",
  body: {},
  querySelectorAll: function(sel){
    // Only the three help classes are selected; the plain element is not.
    if(sel.indexOf("infodot") >= 0) return marks;
    return [];
  },
  addEventListener: function(){},
};
const win = {innerWidth: 1400, addEventListener: function(){}};

new Function("document", "window", "MutationObserver", "setTimeout",
             "clearTimeout", TIPS)(
  doc, win, undefined, function(f){ return 0; }, function(){});

console.log("=== the statement moves from title to data-tip ===");
check("the ⓘ keeps its words", marks[0].getAttribute("data-tip"),
      "Sessions ÷ page views, over the whole window.");
// BOTH ATTRIBUTES PRESENT = BOTH TOOLTIPS. The native one appears on a delay,
// on top of the styled one, which is worse than either alone.
check("  and the native title is REMOVED", marks[0].getAttribute("title"), null);
check("newlines survive, because the statements are written with them",
      marks[1].getAttribute("data-tip").indexOf("\n") > 0, true);
check("the ? marks are covered too", marks[2].getAttribute("data-tip"),
      "Spend over sales, across the rows shown.");

console.log("\n=== reachable without a mouse ===");
check("a mark takes focus", marks[0].getAttribute("tabindex"), "0");
check("  and says what it is", marks[0].getAttribute("role"), "note");

console.log("\n=== only the HELP marks are touched ===");
truthy("the selector names the three help classes",
       /\.infodot\[title\]/.test(TIPS) && /\.ppc-i\[title\]/.test(TIPS)
       && /\.ppc-q\[title\]/.test(TIPS));
check("  an ordinary title is left alone", plain.getAttribute("title"),
      "A very long product name that is truncated");
truthy("  and the reason is recorded",
       /NOT EVERY title IN THE APP/.test(TIPS));

console.log("\n=== the bubble is actually drawn ===");
truthy("data-tip renders as content", /\[data-tip\]::after/.test(CSS));
truthy("  with the attribute's own text", /content:attr\(data-tip\)/.test(CSS));
truthy("  shown on hover AND on focus",
       /\[data-tip\]:hover::after, \[data-tip\]:focus::after/.test(CSS));
// The statements contain real newlines; the native tooltip flattened them and
// so would `white-space:nowrap`.
truthy("  keeping the line breaks", /white-space:pre-line/.test(CSS));
truthy("  and above everything else", /z-index:9999/.test(CSS));

console.log("\n=== it stays on screen at the edges ===");
truthy("there are edge classes", /\.tip-l::after/.test(CSS) && /\.tip-r::after/.test(CSS));
truthy("  and the pass applies them", /altaTipEdge/.test(TIPS));
truthy("  re-measured when the window resizes", /addEventListener\("resize"/.test(TIPS));

console.log("\n=== it survives a redraw ===");
// Every screen rebuilds its panels with innerHTML, which throws the attributes
// away with the elements. Once at startup would not be enough.
truthy("it watches the DOM rather than being called by each screen",
       /MutationObserver/.test(TIPS));
truthy("  debounced, because innerHTML fires a great many mutations",
       /clearTimeout\(_ALTA_TIP_T\)/.test(TIPS));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
