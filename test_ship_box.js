// The "Preview dispatch to Amazon" box (static/js/orders.js, 29 Sep 2026).
// Pins: only FBM orders still to post get it; preview posts the row's own
// account with the typed tracking and carrier; a Send button is drawn ONLY when
// the server says sending is switched on; Send asks first and stops on "no".

const fs = require("fs");
const vm = require("vm");

let fails = [];
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(70) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}

const JS = fs.readFileSync(__dirname + "/static/js/orders.js", "utf8");
const BOARD = fs.readFileSync(__dirname + "/static/js/orders_board.js", "utf8");
function lift(src, decl) {
  const at = src.indexOf(decl + "(");
  if (at < 0) throw new Error("not found: " + decl);
  return src.slice(at, src.indexOf("\n}", at) + 2);
}

const posted = [];
const out = { textContent: "", innerHTML: "" };
const sb = {
  console, jsArg: require("./test_helpers.js").jsArg, ORD: { details: {} },
  toast: () => {}, ordersRender: () => {}, ordersLoad: async () => {}, ordersToggle: () => {},
  reply: { ok: true, summary: "Amazon would be told: X", switched_on: false, why_off: "switched off" },
  confirmAnswer: false, uiConfirm: async () => sb.confirmAnswer,
  fetch: async (url, init) => { posted.push({ url, body: JSON.parse(init.body) }); return { json: async () => sb.reply }; },
  document: { getElementById: id => ({ ordtrk_num: { value: " RM1234567GB " }, ordtrk_car: { value: "Royal Mail" }, ordship_out: out }[id] || null) },
};
vm.createContext(sb);
vm.runInContext([lift(JS, "function _oEsc"), lift(BOARD, "function _ordUnshipped"), lift(JS, "function _ordShipBox"),
  lift(JS, "function _ordShipBody"), lift(JS, "async function ordShipPreview"),
  lift(JS, "async function ordShipConfirm"), lift(JS, "async function _ordWriteThenReload")].join("\n"), sb);

const row = { order_id: "203-1", account_id: "acct_b", marketplace: "UK", fulfilment: "MFN", status: "Unshipped", unshipped: 1 };
console.log("=== who gets the box ===");
check("FBM still to post -> offered", /Preview dispatch to Amazon/.test(sb._ordShipBox(row)), true);
check("FBA -> not offered", sb._ordShipBox(Object.assign({}, row, { fulfilment: "AFN" })), "");
check("already shipped -> not offered", sb._ordShipBox(Object.assign({}, row, { status: "Shipped", unshipped: 0 })), "");
check("no Send button is drawn up front", /ordShipConfirm/.test(sb._ordShipBox(row)), false);

(async () => {
  console.log("\n=== preview ===");
  await sb.ordShipPreview("203-1", "acct_b", "UK", null);
  check("posts to the preview route", posted[0].url, "/orders/ship/preview");
  check("  with the row's account and the typed tracking + carrier",
        [posted[0].body.account, posted[0].body.tracking_number, posted[0].body.carrier], ["acct_b", "RM1234567GB", "Royal Mail"]);
  check("switched off -> no Send button, and the reason", [/ordShipConfirm/.test(out.innerHTML), /switched off/.test(out.innerHTML)], [false, true]);
  sb.reply = { ok: true, summary: "Amazon would be told: X", switched_on: true };
  await sb.ordShipPreview("203-1", "acct_b", "UK", null);
  check("switched on -> a Send button", /ordShipConfirm/.test(out.innerHTML), true);
  sb.reply = { ok: false, error: "Type the tracking number first." };
  await sb.ordShipPreview("203-1", "acct_b", "UK", null);
  check("a refusal is shown in words", out.textContent, "Not ready to send: Type the tracking number first.");

  console.log("\n=== send: only what was previewed, and it asks first ===");
  let n = posted.length;
  sb.ORD.shipPreview = null;
  await sb.ordShipConfirm("203-1", "acct_b", "UK", { disabled: false });
  check("no preview -> nothing sent", posted.length, n);
  sb.reply = { ok: true, summary: "Amazon would be told: shipped, RM1234567GB", switched_on: true };
  await sb.ordShipPreview("203-1", "acct_b", "UK", null);
  n = posted.length;
  let asked = "";
  sb.uiConfirm = async (m) => { asked = m; return sb.confirmAnswer; };
  sb.confirmAnswer = false;
  await sb.ordShipConfirm("203-1", "acct_b", "UK", { disabled: false });
  check("'no' sends nothing", posted.length, n);
  check("  and the question repeated what would be sent", /RM1234567GB/.test(asked), true);
  const realGet = sb.document.getElementById;
  sb.document.getElementById = id => (id === "ordtrk_num" ? { value: "CHANGED99999" } : realGet(id));
  sb.confirmAnswer = true;
  await sb.ordShipConfirm("203-1", "acct_b", "UK", { disabled: false });
  check("boxes changed since the preview -> nothing sent", [posted.length, /changed since the preview/.test(out.textContent)], [n, true]);
  sb.document.getElementById = realGet;
  sb.reply = { ok: false, uncertain: true, error: "It is not known whether Amazon received this" };
  const b1 = { disabled: false };
  await sb.ordShipConfirm("203-1", "acct_b", "UK", b1);
  check("'yes' posts the previewed body to the confirm route, row's account",
        [posted[n].url, posted[n].body.account, posted[n].body.tracking_number], ["/orders/ship/confirm", "acct_b", "RM1234567GB"]);
  check("result not known -> the button stays OFF (it may have been sent)", b1.disabled, true);
  sb.reply = { ok: true, summary: "Amazon would be told: shipped, RM1234567GB", switched_on: true };
  await sb.ordShipPreview("203-1", "acct_b", "UK", null);
  sb.reply = { ok: false, error: "Amazon refused the dispatch confirmation: bad carrier" };
  const b2 = { disabled: false };
  await sb.ordShipConfirm("203-1", "acct_b", "UK", b2);
  check("a clear refusal frees the button", b2.disabled, false);

  if (fails.length) { console.log("\nFAILED: " + fails.length); process.exit(1); }
  console.log("\nall dispatch box checks passed");
})();
