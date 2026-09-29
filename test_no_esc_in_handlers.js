// No value reaches an inline handler through esc().
//
// WHY. esc() makes text safe for HTML, and turns ' into &#39;. Inside
// onclick="fn('${esc(x)}')" the browser DECODES that entity before the handler
// runs, so a product title containing  ');alert(document.cookie);//  closes the
// string and runs as code -- a stored cross-site script, fed by anything that
// lands in a title: a supplier page, an Amazon listing, an upload. The master
// audit (28 Sep 2026) counted 85+ of them. The right helper is jsArg() (users.js):
// escape for JavaScript FIRST, then for the attribute.
//
// Checked two ways: no `'${esc(` left inside an on*="..." attribute anywhere in
// static/js, and jsArg's output, put through the same decoding a browser does,
// is still one harmless string. Milestone 2.
"use strict";
const fs = require("fs");
const path = require("path");

const JS = path.join(__dirname, "static", "js");
let fails = 0, ran = 0;
function check(label, got, want){
  ran++;
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
              + " want=" + JSON.stringify(want)));
}

console.log("\n1. no esc() inside an inline handler");
const offenders = [];
for(const f of fs.readdirSync(JS).filter(f => f.endsWith(".js"))){
  const lines = fs.readFileSync(path.join(JS, f), "utf8").split(/\r?\n/);
  lines.forEach((line, n) => {
    let from = 0, j;
    while((j = line.indexOf("'${esc(", from)) >= 0){
      const before = line.slice(0, j);
      let m = null, re = /\bon[a-z]+=\\?"/g, mm;
      while((mm = re.exec(before))) m = mm;
      const tail = m ? before.slice(m.index + m[0].length).replace(/\\"/g, "") : "";
      if(m && tail.indexOf('"') < 0) offenders.push(f + ":" + (n + 1));
      // A handler assembled in a variable first: `fn('${esc(x)}')` then
      // onclick="${that}". Caught by the call shape itself.
      else if(/`[A-Za-z_$][\w$.]*\(\s*$/.test(before.replace(/'\$\{[^}]*\}',\s*$/, "")))
        offenders.push(f + ":" + (n + 1) + " (built in a variable)");
      from = j + 7;
    }
  });
}
check("offending places", offenders, []);

// THE OTHER TWO SHAPES OF THE SAME SINK (the payload guardian's review found
// them): a quoted argument built by concatenation, onclick="fn(\'' + x + '\')",
// and a raw template value, onclick="fn('${x}')" -- escaped or not, the value
// sits inside a JS string the browser has already un-escaped. On one line,
// a handler that opens a quoted argument that way is the defect.
const shapes = [];
// Element ids built in code, not data: allowed by name, with the reason.
const ALLOWED = [/getElementById\(\\''\s*\+\s*id\s*\+/];   // sourcing.js: an id it made
for(const f of fs.readdirSync(JS).filter(f => f.endsWith(".js"))){
  fs.readFileSync(path.join(JS, f), "utf8").split(/\r?\n/).forEach((line, n) => {
    const h = /\bon[a-z]+=\\?"/.exec(line);
    if(!h) return;
    const rest = line.slice(h.index);
    if(ALLOWED.some(re => re.test(rest))) return;
    if(/[(,]\\''\s*\+/.test(rest) || /[(,]'\$\{/.test(rest))
      shapes.push(f + ":" + (n + 1));
  });
}
check("no quoted argument built by concatenation or a raw ${} either", shapes, []);

console.log("\n2. jsArg survives what the browser does to an attribute");
const U = fs.readFileSync(path.join(JS, "users.js"), "utf8");
const jsArg = new Function(U.slice(U.indexOf("function jsArg("),
  U.indexOf("\n}", U.indexOf("function jsArg(")) + 2) + "\nreturn jsArg;")();
// What the HTML parser does to an attribute value before the handler runs.
const decode = s => s.replace(/&#39;/g, "'").replace(/&quot;/g, '"')
  .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const nasty = ["');alert(1);//", '"><img src=x onerror=alert(1)>',
               "back\\slash'", "it's a \"quote\"", "</script>", "&#39;"];
for(const v of nasty){
  const attr = "fn(" + jsArg(v) + ")";
  check("attribute has no raw double quote: " + v, attr.indexOf('"') < 0, true);
  let seen;
  new Function("fn", decode(attr))(x => { seen = x; });
  check("  and runs as exactly one string argument", seen, v);
}
// And the old way really was broken, so this test would have caught it.
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",
  ">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let escaped = false;
try{
  new Function("fn", "alert", decode("fn('" + esc("');alert(1);//") + "')"))(
    () => {}, () => { escaped = true; });
}catch(e){}
check("(the old esc() form did let the code run)", escaped, true);

console.log("\n" + ran + " checks, " + fails + " failed");
console.log("FAILURES: " + fails);
process.exit(fails ? 1 : 0);
