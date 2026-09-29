// Test runs only: a text read of a split file returns the whole feature.
//
// run_tests.py starts every Node test with `--require` pointing here (through
// NODE_OPTIONS, so a Node process a Python test starts gets it too). It changes
// ONE thing: fs.readFileSync(path, <text encoding>) where path is an original
// listed in tests_support/features.json that now has parts returns the joined
// text of the feature. Every other read, and every binary read, is untouched.
// See tests_support/features.py for why.
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.dirname(__dirname);
let FEATURES = {};
try {
  // ALTA_FEATURES_JSON: a practice manifest for test_feature_sources.py.
  const raw = JSON.parse(fs.readFileSync(process.env.ALTA_FEATURES_JSON || path.join(__dirname, "features.json"), "utf8"));
  for (const k of Object.keys(raw)) if (!k.startsWith("_")) FEATURES[k] = raw[k];
} catch (e) { FEATURES = {}; }         // a broken manifest must not break Node

const norm = p => path.resolve(p).toLowerCase();
const INDEX = {}, MAINS = {};
for (const k of Object.keys(FEATURES)) {
  if (FEATURES[k].length > 1) {
    INDEX[norm(path.join(ROOT, ...k.split("/")))] = FEATURES[k];
    MAINS[norm(path.join(ROOT, ...k.split("/")))] = k;
  }
}

// THE FEATURE IN THE ORIGINAL FILE'S ORDER -- the same rule as
// tests_support/features.py (keep the two in step): a part named by exactly one
// "moved to <file> (Milestone 4)" pointer, or by an {% include %}, goes back
// at that spot; any other part follows in manifest order.
const POINTER = /^[ \t]*\/\/ .*: moved to (static\/js\/[\w./-]+) \(Milestone 4\)[^\r\n]*$/gm;
const INCLUDE = /^\{% include "([\w./-]+\.html)" %\}$/gm;
function readRel(rel, enc) { return realRead.call(fs, path.join(ROOT, ...rel.split("/")), enc); }
function body(rel, enc) {
  let t = readRel(rel, enc).replace(/\r\n/g, "\n");
  if (rel.endsWith(".js") && t.startsWith("//") && t.indexOf("\n\n") >= 0) t = t.slice(t.indexOf("\n\n") + 2);
  return t;
}
function featureText(main, parts, enc) {
  const orig = readRel(main, enc);
  const nl = orig.indexOf("\r\n") >= 0 ? "\r\n" : "\n";
  let o = orig.replace(/\r\n/g, "\n");
  const placed = new Set(), ptr = {};
  for (const m of o.matchAll(POINTER)) (ptr[m[1]] = ptr[m[1]] || []).push(m[0]);
  for (const rel of Object.keys(ptr)) {
    if (ptr[rel].length === 1 && parts.includes(rel)) {
      const b = body(rel, enc).replace(/\n+$/, "");
      o = o.replace(ptr[rel][0], () => b);
      placed.add(rel);
    }
  }
  if (main.endsWith(".html")) {
    o = o.replace(INCLUDE, (all, inc) => {
      const rel = "templates/" + inc;
      if (!parts.includes(rel)) return all;
      placed.add(rel);
      return readRel(rel, enc).replace(/\r\n/g, "\n").replace(/\n+$/, "");
    });
  }
  return parts.map(rel => {
    let t;
    if (rel === main) t = o.replace(/\n/g, nl);
    else if (placed.has(rel)) return "";
    else t = readRel(rel, enc);
    return t.endsWith("\n") ? t : t + "\n";
  }).join("");
}

// Only a TEST's own read is answered with the feature (see sitecustomize.py):
// the caller must be a test_*.js file or the shared test_helpers.js.
// A script sitting directly in the repo folder counts too: some Python tests
// write a temporary .js there and run it with node. No app code runs in these
// Node processes; the check keeps the rule the same shape as Python's.
function calledFromATest() {
  const lines = String(new Error().stack || "").split("\n").slice(1);
  for (const l of lines) {
    if (l.indexOf("feature_read.js") >= 0 || l.indexOf("node:") >= 0) continue;
    const m = /\(?((?:[A-Za-z]:)?[^():]+\.js):\d+:\d+\)?\s*$/.exec(l);
    if (!m) return false;
    const f = m[1];
    return /^test_/.test(path.basename(f)) || path.resolve(path.dirname(f)).toLowerCase() === ROOT.toLowerCase();
  }
  return false;
}

const realRead = fs.readFileSync;
fs.readFileSync = function (file, options) {
  const enc = typeof options === "string" ? options : (options && options.encoding);
  if (enc && (typeof file === "string" || file instanceof URL) && calledFromATest()) {
    const key = norm(file instanceof URL ? file.pathname : file);
    const parts = INDEX[key];
    if (parts) return featureText(MAINS[key], parts, enc);
  }
  return realRead.apply(fs, arguments);
};
