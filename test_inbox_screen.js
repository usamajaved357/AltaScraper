// Customer messages screen (static/js/inbox.js), 30 Sep 2026: its states, and
// that one account's buyers never appear under another.
//   not connected / loading / error / empty / list (escaped) / after a switch
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = 0, ran = 0;
function check(label, got, want){
  ran++;
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
              + " want=" + JSON.stringify(want)));
}
const read = p => fs.readFileSync(path.join(__dirname, p), "utf8");

const els = {};
function el(id){ return els[id] || (els[id] = {id, innerHTML: "", style: {}, textContent: "", disabled: false,
  value: "", _a: {}, setAttribute(k, v){ this._a[k] = String(v); }, getAttribute(k){ return k in this._a ? this._a[k] : null; }}); }
["ibx_body", "ibx_badge", "ibx_check", "mbx_box", "mbx_result", "mbx_status", "mbx_user", "mbx_pw"].forEach(el);
const doc = {readyState: "complete", hidden: false,
             getElementById: id => els[id] || null,
             querySelector: () => null, querySelectorAll: () => [],
             addEventListener(){}};

// fetch: each call parks until the test answers it.
const calls = [];
function fakeFetch(url, init){
  return new Promise(res => calls.push({url: String(url), init, answer: (body, status) =>
    res({status: status || 200, ok: (status || 200) < 400, json: async () => body})}));
}
const toasts = [];
const ctx = {document: doc, console, setTimeout: () => 0, clearTimeout(){},
             setInterval: () => 1, clearInterval(){}, fetch: fakeFetch,
             toast: (m) => toasts.push(m), jsArg: s => "'" + String(s) + "'",
             can: () => true, CUR_ACCOUNT: {id: "ta"}, WS_MARKET: "UK"};
vm.createContext(ctx);
for(const f of ["static/js/core_util.js", "static/js/pageui.js", "static/js/reqscope.js",
                "static/js/screenstate.js", "static/js/inbox.js"]){
  vm.runInContext(read(f), ctx, {filename: f});
}
const run = s => vm.runInContext(s, ctx);
const tick = () => new Promise(r => setImmediate(r));
const body = () => els.ibx_body.innerHTML;

(async function(){
  console.log("== loading, then not connected ==");
  calls.length = 0;
  const p1 = run("inboxLoad()");
  check("loading is said while the reply is awaited", body().includes("Reading stored messages"), true);
  const c1 = calls.find(c => c.url.startsWith("/inbox/threads"));
  check("the request names the account", !!c1 && c1.url.includes("account=ta"), true);
  c1.answer({ok: true, connected: false, threads: [], unread: 0, status: {}});
  await p1; await tick();
  check("not connected: one-line empty state + connect button",
        [body().includes("No mailbox connected"), body().includes("Connect mailbox")], [true, true]);

  console.log("== error ==");
  calls.length = 0;
  run("INBOX.data = null");
  const p2 = run("inboxLoad()");
  calls.find(c => c.url.startsWith("/inbox/threads")).answer({ok: false, error: "disk <b>gone</b>"}, 500);
  await p2; await tick();
  check("a failed load is drawn as an error, escaped, with a retry",
        [body().includes("ui-error"), body().includes("disk &lt;b&gt;gone"), body().includes("inboxLoad()")],
        [true, true, true]);

  console.log("== connected, nothing yet ==");
  calls.length = 0;
  const p3 = run("inboxLoad()");
  calls.find(c => c.url.startsWith("/inbox/threads")).answer({ok: true, connected: true, threads: [],
    unread: 0, status: {last_ok_at: "2026-09-30T09:00:00+00:00"}, mailbox_user: "s@example.com"});
  await p3; await tick();
  check("empty: says it was checked and offers Check now",
        [body().includes("No buyer messages yet"), body().includes("inboxRefresh()")], [true, true]);

  console.log("== a list ==");
  calls.length = 0;
  const p4 = run("inboxLoad()");
  calls.find(c => c.url.startsWith("/inbox/threads")).answer({ok: true, connected: true, unread: 1,
    status: {last_ok_at: "2026-09-30T09:00:00+00:00", last_error: "timed out"},
    threads: [{key: "202-1234567-7654321", order_id: "202-1234567-7654321", marketplace: "UK",
               subject: "<script>x</script> Where is it", snippet: "hello", last_at: "2026-09-30T08:00:00+00:00",
               count: 1, unread: 1, reply_url: "https://sellercentral.amazon.co.uk/messaging/inbox"}]});
  await p4; await tick();
  check("one row per order, unread marked", [body().includes("ibx-row unread"), body().includes("202-1234567-7654321")],
        [true, true]);
  check("the subject is escaped, never markup", [body().includes("<script>x"), body().includes("&lt;script&gt;")],
        [false, true]);
  check("a failed last check is shown above the list", body().includes("The last mailbox check failed"), true);
  check("the nav badge shows the unread count", [els.ibx_badge.textContent, els.ibx_badge.style.display], ["1", ""]);

  console.log("== after an account switch ==");
  calls.length = 0;
  const p5 = run("inboxLoad()");
  const late = calls.find(c => c.url.startsWith("/inbox/threads"));
  run("CUR_ACCOUNT = {id: 'tb'}; screenForgetAll()");
  check("switching empties the panel and the held data",
        [body(), run("INBOX.data"), run("INBOX.threads.length"), els.ibx_badge.style.display], ["", null, 0, "none"]);
  late.answer({ok: true, connected: true, unread: 5, status: {},
               threads: [{key: "A-ONLY", order_id: "A-ONLY", subject: "A's buyer", unread: 5, count: 5}]});
  await p5; await tick();
  check("A's late reply is dropped, not drawn under B", [body().includes("A-ONLY"), run("INBOX.threads.length")],
        [false, 0]);
  calls.length = 0;
  const p6 = run("inboxOnOpen()");
  const c6 = calls.find(c => c.url.startsWith("/inbox/threads"));
  check("reopening under B asks for B", !!c6 && c6.url.includes("account=tb"), true);
  c6.answer({ok: true, connected: false, threads: [], unread: 0, status: {}});
  await p6; await tick();

  console.log("== the mailbox form belongs to the account it was drawn for ==");
  calls.length = 0;
  const p7 = run("mbxSettingsLoad()");
  const c7 = calls.find(c => c.url.startsWith("/settings/mailbox"));
  check("the settings read names the account", !!c7 && c7.url.includes("account=tb"), true);
  c7.answer({ok: true, account: "tb", host: "imap.gmail.com", port: 993, user: "b@example.com",
             has_password: true, password_tail: "wxyz", sealed: true, configured: true});
  await p7; await tick();
  check("the password is never put in the form, only its last four",
        [els.mbx_box.innerHTML.includes("•••• wxyz"), /value="[^"]*wxyz/.test(els.mbx_box.innerHTML)], [true, false]);
  run("CUR_ACCOUNT = {id: 'ta'}");
  calls.length = 0;
  await run("mbxSave()");
  await run("mbxTest()");
  check("after a switch, Save and Test send nothing", calls.filter(c => c.init && c.init.method === "POST").length, 0);
  check("  and say why", els.mbx_result.innerHTML.includes("Another account was opened"), true);

  console.log("\n" + ran + " checks, " + fails + " failed");
  console.log("FAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})().catch(e => { console.log("CRASH " + (e && e.stack || e)); process.exit(1); });
