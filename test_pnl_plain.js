// The plain-language Profit & Loss (pnl.js pnlSummary / pnlPlainHtml).
//
// Design package 05 section 8, owner-approved: You sold / Your costs / You kept,
// then "Where your costs went". The one rule that matters: THE NUMBERS MUST
// MATCH THE STATEMENT. "You sold" is the Sales line, "You kept" the Net profit
// line, "Your costs" the difference, and the rows add up to "Your costs" to the
// penny -- including when Amazon has not itemised a fee category (null).

const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = [];
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(72) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}

const sb = { console, document: { getElementById: () => null } };
sb.window = sb;
sb.esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
vm.createContext(sb);
vm.runInContext(fs.readFileSync(path.join("static", "js", "pnl.js"), "utf8"), sb);
const { pnlSummary, pnlPlainHtml } = sb;

// ---- every line the server sends has a named group -----------------------
// Read off domain/pnl.LINES itself, so a new line there fails here until it is
// given a name, rather than quietly landing in "Other".
const py = fs.readFileSync(path.join("domain", "pnl.py"), "utf8");
const block = py.slice(py.indexOf("LINES = ("), py.indexOf("\n)\n", py.indexOf("LINES = (")));
const keys = [...block.matchAll(/\("(\w+)",\s*"[^"]*",\s*([+-]?\d)\)/g)]
  .filter(m => m[2] !== "0" && m[1] !== "ordered_sales").map(m => m[1]);
check("LINES parsed (at least ten cost lines)", keys.length >= 10, true);
const unmapped = keys.filter(k => !vm.runInContext("_PNL_GROUP_OF", sb)[k]);
check("every cost line on the server has a named group", unmapped, []);

// ---- a statement shaped like the server's --------------------------------
const L = (key, sign, value, basis) => ({ key, label: key, sign, value, basis: basis || "" });
function lines(o) {
  return [
    L("ordered_sales", 1, o.sales), L("vat_line", -1, o.vat), L("refunds", -1, o.refunds),
    L("net_sales", 0, 0), L("cogs", -1, o.cogs),
    L("referral_fees", -1, o.ref, o.fb), L("fba_fees", -1, o.fba, o.fb),
    L("promo_fees", -1, o.promo, o.fb), L("other_fees", -1, o.oth, o.fb),
    L("fees_estimated", -1, o.est, "estimated at the account's measured rate"),
    L("promos", -1, o.promos), L("refund_fees_returned", 1, o.back1),
    L("reimbursements", 1, o.reimb), L("charges", -1, o.charges),
    L("ad_spend", -1, o.ads), L("profit_before_own_costs", 0, 0),
    L("account_charges", -1, o.acct), L("manual_expenses", -1, o.own),
    L("profit", 0, o.profit),
  ];
}
const sum = rows => Math.round(rows.reduce((a, r) => a + r.amount, 0) * 100) / 100;

// Fully itemised: profit is exactly sales minus the deductions.
const a = {sales: 1000, vat: 166.67, refunds: 20, cogs: 300, ref: 150, fba: 0, promo: 5,
           oth: 10, est: 0, promos: 12, back1: 3, reimb: 7, charges: 40, ads: 90,
           acct: 25, own: 30, fb: "actual"};
a.profit = Math.round((a.sales - a.vat - a.refunds - a.cogs - a.ref - a.fba - a.promo - a.oth
  - a.est - a.promos + a.back1 + a.reimb - a.charges - a.ads - a.acct - a.own) * 100) / 100;
let s = pnlSummary(lines(a));
check("You sold is the Sales line", s.sold, 1000);
check("You kept is the Net profit line", s.kept, a.profit);
check("Your costs = sold - kept", s.costs, Math.round((1000 - a.profit) * 100) / 100);
check("the rows add up to Your costs", sum(s.rows), s.costs);
check("no 'Not broken down' row when everything is itemised",
      s.rows.some(r => r.id === "rest"), false);
check("largest cost first", s.rows[0].id, "stock");
check("fees grouped into one row (ref+promo+oth+acct-returned)",
      s.rows.find(r => r.id === "fees").amount,
      Math.round((150 + 5 + 10 + 25 - 3) * 100) / 100);
check("money back is a negative cost", s.rows.find(r => r.id === "back").amount, -7);

// Not itemised: the fee categories are null and the server carries the whole
// estimate on "Fees not yet itemised" (domain/pnl.build) -- still adds up.
const b = Object.assign({}, a, {ref: null, fba: null, promo: null, oth: null,
                                est: 165, fb: "not itemised"});
s = pnlSummary(lines(b));
check("null categories: tiles still read the statement", [s.sold, s.kept], [1000, a.profit]);
check("null categories: rows still add up to Your costs", sum(s.rows), s.costs);
check("null categories: no difference row", s.rows.some(r => r.id === "rest"), false);
check("the null lines are named as not known", s.missing.length, 4);
check("the estimate marks it rough", s.rough, true);

// Pennies of rounding go on the largest row, not a row of their own.
const pen = lines(a); pen[pen.length - 1].value = a.profit - 0.03;
s = pnlSummary(pen);
check("rounding pennies: no difference row", s.rows.some(r => r.id === "rest"), false);
check("rounding pennies: rows still add up", sum(s.rows), s.costs);

// A real mismatch is shown, not hidden.
const bad = lines(a); bad[bad.length - 1].value = a.profit - 40;
s = pnlSummary(bad);
check("a real mismatch gets its own row", s.rows.find(r => r.id === "rest").amount, 40);

// The per-£10 line is the statement's margin (after VAT), not a new one.
const hm = pnlPlainHtml({lines: lines(a), margin_pct: 23.4}, "GBP");
check("per-£10 uses margin_pct", hm.includes("about £2.34 from every £10 of sales after VAT"), true);

// A loss.
const c = Object.assign({}, a, {ads: 900});
c.profit = a.profit - 810;
s = pnlSummary(lines(c));
check("a loss is a negative kept", s.kept < 0, true);
const html = pnlPlainHtml({lines: lines(c), fee_coverage: {orders: 62}}, "GBP");
check("a loss reads 'You lost', in the danger tile", /pnl-tile lost[\s\S]*You lost/.test(html), true);
check("'from 62 orders' under You sold", html.includes("from 62 orders"), true);

const h2 = pnlPlainHtml({lines: lines(a), uncosted_units: 20}, "GBP");
check("uncosted units are warned about under the tiles", h2.includes("20 units have no cost recorded"), true);

// No profit line: nothing is drawn rather than a guess.
check("no Net profit -> no summary", pnlSummary([L("ordered_sales", 1, 10)]), null);

if (fails.length) { console.log("\nFAILED: " + fails.length); process.exit(1); }
console.log("\nall plain P&L checks passed");

