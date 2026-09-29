/* An unanswered VAT question survives Save (VAT audit C2, 29 Sep 2026).
 *
 * The server keeps "nobody has said" as its own answer (accounts_routes:
 * "None must survive the round trip, or opening the editor and pressing Save
 * would quietly declare every unanswered account 'not registered'"). The form
 * sent vat_percent: 0 whenever the box was unticked -- including when nobody had
 * ever answered and nobody touched it -- so a routine Save of an account's
 * settings declared it not VAT registered and changed its profit figures.
 *
 * Runs the REAL saveAccount and _toggleVat from static/js/shell.js against a
 * fake page and captures what would be posted.
 */
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const SRC = fs.readFileSync(path.join(__dirname, "static/js/shell.js"), "utf8");
let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(66), ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
function fn(name) {
  const re = new RegExp("(?:async )?function " + name + "\\(([\\s\\S]*?)\\r?\\n\\}\\r?\\n");
  const m = SRC.match(re);
  if (!m) throw new Error("cannot find " + name);
  return m[0];
}

function page(answered, checked, pct) {
  const els = {
    ac_label: { value: "Acme" }, ac_vat_on: { checked, dataset: { answered } },
    ac_vat_pct: { value: pct }, ac_vat_wrap: { style: {} },
  };
  const posted = [];
  const s = {
    console, posted,
    document: { getElementById: (id) => els[id] || { value: "", checked: false, dataset: {}, style: {}, classList: { remove() {}, add() {} } } },
    fetch: (url, opt) => { posted.push(JSON.parse(opt.body)); return Promise.resolve({ json: () => Promise.resolve({ ok: false, error: "stop" }) }); },
    toast() {}, ACCOUNTS: [], EDITING_ACCOUNT: "acme", _editingId: "acme",
    loadAccounts() {}, renderAccounts() {}, closeAccountEditor() {},
  };
  vm.createContext(s);
  vm.runInContext(fn("_toggleVat"), s);
  vm.runInContext(fn("parseSheetUrl"), s);
  vm.runInContext(fn("saveAccount"), s);
  return { s, els };
}

(async () => {
  console.log("=== the question was never answered ===");
  {
    const { s } = page("0", false, "20");
    await vm.runInContext("saveAccount()", s);
    check("the save really posted (not a vacuous pass)", s.posted.length, 1);
    check("saving without touching the box sends NO vat_percent", "vat_percent" in (s.posted[0] || {}), false);
  }
  {
    const { s, els } = page("0", false, "20");
    els.ac_vat_unanswered = { style: {} };
    vm.runInContext("_toggleVat(false)", s);                    // touched, left unticked
    check("touching the box hides the 'not answered yet' note", els.ac_vat_unanswered.style.display, "none");
    await vm.runInContext("saveAccount()", s);
    check("touching it and leaving it unticked IS an answer: 0", (s.posted[0] || {}).vat_percent, 0);
  }
  {
    const { s, els } = page("0", false, "");
    els.ac_vat_on.checked = true;
    vm.runInContext("_toggleVat(true)", s);                     // ticked -> defaults to 20
    await vm.runInContext("saveAccount()", s);
    check("ticking it sends the rate (20 by default)", (s.posted[0] || {}).vat_percent, 20);
  }
  console.log("=== the question was answered before ===");
  {
    const { s } = page("1", false, "20");
    await vm.runInContext("saveAccount()", s);
    check("answered 'not registered' stays 0", (s.posted[0] || {}).vat_percent, 0);
  }
  {
    const { s } = page("1", true, "17.5");
    await vm.runInContext("saveAccount()", s);
    check("answered registered keeps its rate", (s.posted[0] || {}).vat_percent, 17.5);
  }
  console.log("=== the editor marks whether it was answered ===");
  const cbLine = SRC.split(/\r?\n/).find((l) => l.indexOf('id="ac_vat_on"') >= 0) || "";
  check("the checkbox carries data-answered from the stored rate",
        cbLine.indexOf("data-answered=\"${(a.vat_percent === null || a.vat_percent === undefined) ? '0' : '1'}\"") >= 0, true);
  const R = fs.readFileSync(path.join(__dirname, "routes/accounts_routes.py"), "utf8");
  check("the server refuses a 100% rate, as the decimal form refuses 1.0", /_vp < 0 or _vp >= 100/.test(R), true);
  console.log("\nFAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})();

