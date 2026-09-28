// reqscope.js stamps the TAB's account on the paths that used to answer for
// the server's open account (image library, uploads, image generation,
// Variations). See test_tab_account_routes.py for the server half.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = 0, ran = 0;
function check(label, got, want){
  ran++;
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)));
}

const src = fs.readFileSync(path.join(__dirname, "static", "js", "reqscope.js"), "utf8");
const seen = [];
const window = { fetch: function(u){ seen.push(u); return Promise.resolve({}); } };
const ctx = { window, CUR_ACCOUNT: { id: "tab1" }, console };
vm.createContext(ctx);
vm.runInContext(src, ctx);

console.log("\n1. which paths are stamped");
const P = u => vm.runInContext("acctScopedPath(" + JSON.stringify(u) + ")", ctx);
check("/media/list", P("/media/list"), true);
check("/media/upload", P("/media/upload"), true);
check("/genimage/start_batch (prefix)", P("/genimage/start_batch"), true);
check("/variations/families?x=1", P("/variations/families?x=1"), true);
check("/listing/image_slots", P("/listing/image_slots?sku=A"), true);
check("not /media/listX", P("/media/listX"), false);
check("not /rows_all", P("/rows_all"), false);
check("not a url that already names an account", P("/media/list?account=other"), false);
check("not an absolute url", P("https://example.com/media/list"), false);

console.log("\n2. the fetch wrapper adds the tab's account");
window.fetch("/media/list?sku=S1");
window.fetch("/variations/families");
window.fetch("/rows_all?account=tab1");
window.fetch("/sales/summary");
check("stamped where listed, untouched elsewhere", seen, [
  "/media/list?sku=S1&account=tab1",
  "/variations/families?account=tab1",
  "/rows_all?account=tab1",
  "/sales/summary",
]);
check("installed once", !!window.fetch._acctScoped, true);

console.log("\n3. the tab's marketplace goes with it (the country must not follow another tab)");
seen.length = 0;
ctx.WS_MARKET = "US";
window.fetch("/variations/apply");
window.fetch("/input/rows?marketplace=UK");
ctx.WS_MARKET = "__all__";
window.fetch("/miles/run");
check("marketplace added; an explicit one kept; 'All' never sent", seen, [
  "/variations/apply?account=tab1&marketplace=US",
  "/input/rows?marketplace=UK&account=tab1",
  "/miles/run?account=tab1",
]);
check("the audit's write paths are covered",
      ["/settings/ads", "/input/add", "/drive/upload", "/miles/generate",
       "/miles_template/render", "/sync/pull/apply", "/variant/queue",
       "/agent/ask", "/submit/target", "/dup_check"].map(P), Array(10).fill(true));
check("push_image and the Ads connection test are covered",
      ["/listing/push_image", "/settings/ads/test"].map(P), [true, true]);

console.log("\n" + ran + " checks, " + fails + " failed");
console.log("FAILURES: " + fails);
process.exit(fails ? 1 : 0);
