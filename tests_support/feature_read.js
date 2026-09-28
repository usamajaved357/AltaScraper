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
const INDEX = {};
for (const k of Object.keys(FEATURES)) {
  if (FEATURES[k].length > 1) INDEX[norm(path.join(ROOT, ...k.split("/")))] = FEATURES[k];
}

const realRead = fs.readFileSync;
fs.readFileSync = function (file, options) {
  const enc = typeof options === "string" ? options : (options && options.encoding);
  if (enc && (typeof file === "string" || file instanceof URL)) {
    const parts = INDEX[norm(file instanceof URL ? file.pathname : file)];
    if (parts) {
      return parts.map(function (rel) {
        const t = realRead.call(fs, path.join(ROOT, ...rel.split("/")), enc);
        return t.endsWith("\n") ? t : t + "\n";
      }).join("");
    }
  }
  return realRead.apply(fs, arguments);
};
