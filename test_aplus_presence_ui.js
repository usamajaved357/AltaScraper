// The A+ presence choice has to REACH the backend, or it does not exist.
//
//     "every module contains item images"
//
// The route was taught to accept a product_presence and to withhold the
// reference photograph when the answer is "none". That fixed nothing on its
// own: the screen never sent the field, so every module still defaulted to
// "hero" and still got the photograph. A backend fix nobody can reach is not a
// fix, and this test is the wire between the two.
//
// It also covers the phone rendition and the size label, both of which are the
// same shape of bug: the work exists on the server and is only real if the
// screen asks for it and reports it back honestly.
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

// Comments explain the fault; they must never be what satisfies the test. This
// mistake has been made twice on this codebase already -- an assertion matched
// a phrase that appeared only in the comment written to explain it.
function codeOnly(s) {
  return s
    .split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .map((l) => l.replace(/\s\/\/.*$/, ""))
    .join("\n");
}

const JS = codeOnly(read("static/js/genimage.js"));
const CSS = read("static/css/dashboard.css");
const PY = read("routes/aplus_routes.py");

console.log("== the choice is offered per module ==");
// Per module, not per batch: the complaint is that they were all the same, so
// the answer has to be sayable one module at a time.
check("each module row carries a presence control", /class="appres"/.test(JS));
check("  keyed to that module", /data-mid="\$\{esc\(m\.id\)\}"/.test(JS));
check("  offering all four answers",
  ['"hero"', '"detail"', '"in_use"', '"none"'].every((v) =>
    new RegExp("value=" + v.replace(/"/g, '"')).test(JS)));
check("  and 'no product' is spelled out in plain words",
  /No product — a designed panel/.test(JS));
check("  defaulting to the whole product, so nothing changes unasked",
  /\|\|\s*"hero"/.test(JS));

console.log("\n== the choice is sent ==");
check("the payload carries the presence", /product_presence:pres/.test(JS));
// A product-free module is built from facts and nothing else, so without this
// it has nothing to draw but inventions. It was never sent on this path.
check("  and the listing's own words go with it", /listing:\(it\|\|null\)/.test(JS));
check("the route reads it", /b\.get\("product_presence"/.test(PY));

console.log("\n== the phone version is a second image, not a resize ==");
check("modules with a mobile size offer it", /class="apmobchk"/.test(JS));
check("  only those that declare one", /\$\{m\.mobile\?/.test(JS));
check("  and it queues a SECOND job", /viewport:"mobile"/.test(JS));
check("  labelled so the two are tellable apart", /\(phone\)/.test(JS));

console.log("\n== the size shown is the size made ==");
// The module carries the DESKTOP dimensions. A screen reading module.w x
// module.h labels a 600x450 phone asset as 1464x600, which is the wrong number
// against a real file and how the wrong one gets uploaded.
check("the route reports what it actually made",
  /"width": _w, "height": _h/.test(PY) && /"viewport": viewport/.test(PY));
check("  and the card uses that, not the module's", /j\.width&&j\.height/.test(JS));
check("  falling back to the module only when it must",
  /j\.module\?\(j\.module\.w/.test(JS));
check("  a phone asset says so on the card", /apscr/.test(JS));

console.log("\n== the controls are styled, not raw ==");
["apopts", "appres", "apmob", "apscr"].forEach((c) =>
  check("  ." + c + " has a rule", new RegExp("\\." + c + "\\s*\\{").test(CSS)));
// Clicking a control inside the module's <label> would otherwise toggle the
// module's own checkbox, which is how a select becomes unusable.
check("clicking a control does not toggle the module",
  /event\.stopPropagation\(\)/.test(JS));

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
