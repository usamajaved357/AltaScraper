// No browser code calls a function that is defined nowhere.
//
// WHY THIS EXISTS. All 118 files in static/js share ONE global scope, so a call
// to a function that was renamed, removed or never loaded is not a syntax
// error -- `node --check` passes it -- and it only fails when somebody clicks
// the button: "_fetchJSON is not defined" (load order), "h is not defined",
// "items is not defined". Found by the owner, in the browser, each time.
//
// WHAT IT CHECKS, NARROWLY. Every `name(` call and every inline handler
// (onclick="name(...)" in JS strings and in templates) whose name is declared
// in NO file -- not as a function, variable, parameter, class or window
// property -- and is not a browser built-in. It is a lexical check, so it
// cannot see a name built at run time (window[fn]); ALLOWED_DYNAMIC lists the
// ones that exist that way on purpose. Milestone 1, 28 Sep 2026.
//
// WHAT IT CANNOT CATCH -- said plainly so a green here is not over-read:
//   * LOAD ORDER. A name declared in a file that loads AFTER the caller runs
//     counts as declared. "_fetchJSON is not defined" was that kind.
//   * A NAME DECLARED ANYWHERE. A local `h` in one file makes every `h(` in
//     every other file look fine; "h is not defined" was that kind.
//   * Short or unusual names outside FN_SHAPE, and calls built at run time.
// It catches the commonest kind: a function renamed or deleted everywhere.
"use strict";
const fs = require("fs");
const path = require("path");
const { stripJsComments } = require("./test_helpers.js");

const JS_DIR = path.join(__dirname, "static", "js");
const TPL_DIR = path.join(__dirname, "templates");

// The browser and the JS language, as far as this app uses them.
const BUILTINS = new Set((
  "if for while switch catch function return typeof instanceof new delete void " +
  "do else try throw case in of await async yield super this with " +
  "JSON Math Object Array String Number Boolean Date Promise RegExp Error " +
  "TypeError RangeError SyntaxError Symbol Map Set WeakMap WeakSet Proxy Reflect " +
  "BigInt Intl ArrayBuffer Uint8Array Uint16Array Int32Array Float32Array " +
  "Float64Array DataView TextEncoder TextDecoder parseInt parseFloat isNaN " +
  "isFinite setTimeout setInterval clearTimeout clearInterval fetch alert confirm " +
  "prompt encodeURIComponent decodeURIComponent encodeURI decodeURI escape unescape " +
  "requestAnimationFrame cancelAnimationFrame requestIdleCallback FormData URL " +
  "URLSearchParams Blob File FileReader Image Audio AbortController Headers " +
  "Request Response getComputedStyle atob btoa structuredClone queueMicrotask " +
  "CustomEvent Event KeyboardEvent MouseEvent MutationObserver ResizeObserver " +
  "IntersectionObserver XMLHttpRequest WebSocket EventSource Worker " +
  "DOMParser XMLSerializer Notification BroadcastChannel matchMedia open close " +
  "print scrollTo scroll postMessage require eval Function globalThis " +
  "XLSX Chart Option Range Selection Node Element HTMLElement DocumentFragment " +
  "ClipboardItem ImageData OffscreenCanvas Path2D performance console " +
  "setImmediate import"
).split(/\s+/));

// Names called that exist only at run time, on purpose. Add with a reason.
const ALLOWED_DYNAMIC = new Set([
]);

function read(p) {
  return fs.readFileSync(p, "utf8").replace(/\r\n/g, "\n");
}

const files = fs.readdirSync(JS_DIR).filter(f => f.endsWith(".js"));
const sources = {};
for (const f of files) sources[f] = stripJsComments(read(path.join(JS_DIR, f)));
const templates = fs.readdirSync(TPL_DIR).filter(f => f.endsWith(".html"))
  .map(f => [f, read(path.join(TPL_DIR, f))]);

// ---- everything declared anywhere --------------------------------------
const declared = new Set();
const add = n => { if (n) declared.add(n); };
// DECLARATIONS ARE READ FROM THE RAW FILES, not the comment-stripped ones: the
// stripper can take a "//" inside a string for a comment and swallow the rest
// of the line, and a declaration lost that way would be reported as missing.
// (A declaration that only exists inside a comment is then counted too -- the
// safe direction for a check that must not cry wolf.)
const all = files.map(f => read(path.join(JS_DIR, f))).join("\n") + "\n" +
  templates.map(t => (t[1].match(/<script[^>]*>([\s\S]*?)<\/script>/g) || []).join("\n")).join("\n");
for (const m of all.matchAll(/\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(/g)) add(m[1]);
for (const m of all.matchAll(/\b(?:const|let|var|class)\s+([A-Za-z_$][\w$]*)/g)) add(m[1]);
for (const m of all.matchAll(/\b(?:window|globalThis|self)\.([A-Za-z_$][\w$]*)\s*=/g)) add(m[1]);
for (const m of all.matchAll(/(?:^|[;{}\s])([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\()/gm)) add(m[1]);
// Parameters: of function declarations/expressions and of arrows.
const paramLists = [
  ...all.matchAll(/\bfunction\s*\*?\s*[\w$]*\s*\(([^)]*)\)/g),
  ...all.matchAll(/\(([^()]*)\)\s*=>/g),
  ...all.matchAll(/\bcatch\s*\(([^)]*)\)/g),
];
for (const m of paramLists)
  for (const p of m[1].split(/[,{}\[\]=\s.]+/)) if (/^[A-Za-z_$][\w$]*$/.test(p)) add(p);
for (const m of all.matchAll(/([A-Za-z_$][\w$]*)\s*=>/g)) add(m[1]);
// Destructuring: const {a, b} = / const [a, b] =
for (const m of all.matchAll(/\b(?:const|let|var)\s*[{\[]([^}\]]*)[}\]]/g))
  for (const p of m[1].split(/[,:\s=]+/)) if (/^[A-Za-z_$][\w$]*$/.test(p)) add(p);

// ---- strings are text, not code -----------------------------------------
// Blank every string literal's CONTENT (keeping newlines, so line numbers
// hold) -- prose and CSS such as "var(" and "Report (" are not calls -- while
// the code inside a template literal's ${...} is kept and scanned. A regex
// literal is skipped whole. Handlers written INSIDE strings are pulled out
// separately below, because onclick="fn()" in a string IS a call.
function codeOnly(src) {
  let out = "", i = 0, n = src.length;
  const prevSig = () => { for (let k = out.length - 1; k >= 0; k--) { const c = out[k];
    if (!/\s/.test(c)) return c; } return ""; };
  function str(q) {                       // at opening quote
    out += q; i++;
    while (i < n) {
      const c = src[i];
      if (c === "\\") { out += "  "; i += 2; continue; }
      if (c === q) { out += q; i++; return; }
      if (q === "`" && c === "$" && src[i + 1] === "{") {
        out += "${"; i += 2; let depth = 1;
        while (i < n && depth) {
          const d = src[i];
          if (d === "'" || d === '"' || d === "`") { str(d); continue; }
          if (d === "{") depth++;
          if (d === "}") { depth--; if (!depth) { out += "}"; i++; break; } }
          out += d; i++;
        }
        continue;
      }
      out += (c === "\n" ? "\n" : " "); i++;
    }
  }
  while (i < n) {
    const c = src[i];
    if (c === "'" || c === '"' || c === "`") { str(c); continue; }
    if (c === "/" && "(,=:[!&|?{};+-*%<>~^".includes(prevSig() || ";")) {
      // a regex literal: copy as blanks up to its closing slash
      out += " "; i++;
      let inClass = false;
      while (i < n && src[i] !== "\n") {
        const d = src[i];
        if (d === "\\") { out += "  "; i += 2; continue; }
        if (d === "[") inClass = true; else if (d === "]") inClass = false;
        else if (d === "/" && !inClass) { out += " "; i++; break; }
        out += " "; i++;
      }
      continue;
    }
    out += c; i++;
  }
  return out;
}

// Handlers inside strings: onclick="fn(...)", onclick=\"fn()\", onclick='fn()'.
function handlersIn(src) {
  const got = [];
  const re = /\bon[a-z]+\s*=\s*\\?(["'])([\s\S]*?)\\?\1/g;
  for (const m of src.matchAll(re)) {
    const line = src.slice(0, m.index).split("\n").length;
    // Only the literal parts of the handler: a fragment like
    // "fn('" + jsArg(x) + "')" is split on the concatenation, and the
    // pieces outside the quotes are real code the main scan already sees.
    got.push([line, m[2].replace(/(["'])\s*\+[\s\S]*?\+\s*\1/g, " ")]);
  }
  return got;
}

// A call guarded by `typeof name === "function"` is optional ON PURPOSE (the
// function belongs to a file that may not be loaded), so it is not a fault.
const guarded = new Set();
for (const m of all.matchAll(/typeof\s+([A-Za-z_$][\w$]*)\s*[!=]==?\s*["']function["']/g))
  guarded.add(m[1]);

// ONLY NAMES SHAPED LIKE THIS APP'S FUNCTIONS: camelCase with a capital inside
// (openDrawer, pdpLeaveContext) or a leading underscore (_sFetch). Prose and
// CSS inside HTML strings ("var(", "rgb(", "report (", "LEFT (") never have
// that shape, and a lexical scanner cannot always tell a string from code in
// 3 MB of hand-built HTML -- so the shape is what keeps this check quiet
// enough to be believed.
const FN_SHAPE = /^(?:_[A-Za-z$][\w$]*|[a-z][a-z0-9]*[A-Z][\w$]*)$/;

// ---- everything called -------------------------------------------------
const problems = [];
function scan(label, text) {
  const lines = text.split("\n");
  lines.forEach((line, i) => {
    for (const m of line.matchAll(/(^|[^.\w$])([A-Za-z_$][\w$]*)\s*\(/g)) {
      const name = m[2];
      const before = line.slice(0, m.index + m[1].length);
      if (/\bfunction\s*\*?\s*$/.test(before)) continue;      // a declaration
      if (/\b(?:new|class)\s+$/.test(before) && BUILTINS.has(name)) continue;
      if (!FN_SHAPE.test(name)) continue;
      if (declared.has(name) || BUILTINS.has(name) || ALLOWED_DYNAMIC.has(name)
          || guarded.has(name)) continue;
      problems.push(label + ":" + (i + 1) + "  " + name + "(");
    }
  });
}
// JS: the code, and separately the handler strings inside it.
for (const f of files) {
  scan("static/js/" + f, codeOnly(sources[f]));
  for (const [line, h] of handlersIn(sources[f]))
    scan("static/js/" + f + ":" + line + " handler", h);
}
// Templates: inline handlers only (on*="..."), where a missing function only
// shows up as a dead button.
for (const [f, html] of templates) {
  const lines = html.split("\n");
  lines.forEach((line, i) => {
    for (const h of line.matchAll(/\bon[a-z]+\s*=\s*"([^"]*)"/g))
      scan("templates/" + f + ":" + (i + 1) + " handler", h[1]);
  });
}

const uniq = [...new Set(problems)];
uniq.forEach(p => console.log("  UNDEFINED " + p));
console.log(uniq.length + " call(s) to a name defined nowhere");
console.log("FAILURES: " + uniq.length);
process.exit(uniq.length ? 1 : 0);
