/* static/js/pnl.js -- the account's profit and loss, and the costs you enter.
 *
 * /sales/pnl has existed since the fee work went in and NOTHING IN THE BROWSER
 * CALLED IT. A finished endpoint with no way to reach it is a feature nobody
 * has -- the same fault /cogs/order had, found the same way.
 *
 * WHAT THIS SCREEN IS FOR, beyond showing a number. The profit figure is only
 * as honest as what it says about itself, so every line carries its basis:
 *
 *     "actual"        Amazon has settled it and this is what it charged
 *     "part-actual"   some of the window is settled, the rest is estimated
 *     "not itemised"  Amazon has broken nothing down for this window, so the
 *                     category is UNKNOWN rather than nought
 *
 * And the two things the statement cannot know on its own are asked for here:
 * the costs Amazon never sees, and whether VAT applies.
 *
 * VAT IS TAKEN OUT AT THE ACCOUNT'S OWN SETTING, on its own line, and the box
 * below says how it was worked out. It used to be left in the profit and shown
 * beside it; on 28 Sep 2026 the owner decided every profit figure follows the
 * VAT rate set on the account, so this statement agrees with the Sales card.
 * Where no rate is set the box says the VAT could not be worked out.
 */

const PNL = {data: null, loading: false, expenses: null, adding: false};

async function pnlLoad(){
  const host = document.getElementById("pnl_body");
  if(!host || PNL.loading) return;
  PNL.loading = true;
  host.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Working out the profit…</div>';
  try{
    // The Sales page owns the date range; this reads whatever it is showing so
    // the two screens cannot answer for different months.
    const qs = (typeof _sQuery === "function") ? _sQuery() : "";
    const _sc = (typeof screenScope === "function") ? screenScope() : null;  // audit S5
    const j = await (await fetch("/sales/pnl?" + qs)).json();
    if(_sc && !screenStillIn(_sc)) return;   // switched account/marketplace meanwhile
    PNL.loading = false;
    if(!j || j.ok === false){
      host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + esc((j && j.error) || "Could not work out the profit.") + '</div>';
      return;
    }
    PNL.data = j;
    // The costs you enter are a separate table and a separate call.
    try{
      const q2 = [];
      if(j.workspace) q2.push("account=" + encodeURIComponent(j.workspace));
      if(j.marketplace) q2.push("marketplace=" + encodeURIComponent(j.marketplace));
      if(j.start) q2.push("start=" + encodeURIComponent(j.start));
      if(j.end) q2.push("end=" + encodeURIComponent(j.end));
      const _ex = await (await fetch("/expenses?" + q2.join("&"))).json();
      if(_sc && !screenStillIn(_sc)) return;   // switched meanwhile (audit S5)
      PNL.expenses = _ex;
    }catch(e){ PNL.expenses = null; }
    if(_sc && !screenStillIn(_sc)) return;
    pnlRender();
  }catch(e){
    PNL.loading = false;
    host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + 'Could not work out the profit.</div>';
  }
}

function _pnlMoney(v, cur){
  if(v === null || v === undefined){
    return '<span class="cc" style="opacity:.5" title="Not known — see the '
      + 'notes below.">not known</span>';
  }
  const sym = (cur === "USD") ? "$" : (cur === "EUR") ? "€" : "£";
  const n = Number(v);
  return (n < 0 ? "−" : "") + sym
    + Math.abs(n).toLocaleString(undefined, {minimumFractionDigits: 2,
                                             maximumFractionDigits: 2});
}

/* What a basis means, in words. The codes are the server's; these are the only
 * place they are turned into English, so two screens cannot explain them
 * differently. */
const _PNL_BASIS = {
  "actual": ["Amazon's own figure", "var(--ok,#3fb950)"],
  "part-actual": ["part Amazon's figure, part estimated", "var(--warn)"],
  "not itemised": ["Amazon has not broken this down yet", "var(--ink2)"],
  "estimated at the account's measured rate":
    ["estimated at this account's own measured rate", "var(--warn)"],
};

/* THE SAME STATEMENT, SAID PLAINLY (design package 05 section 8, owner-approved):
 * You sold / Your costs / You kept, then "Where your costs went".
 *
 * NOTHING HERE IS A SECOND CALCULATION. Every figure is read off the lines the
 * server already sent (domain/pnl.LINES): "You sold" is the Sales line, "You
 * kept" is the Net profit line, and "Your costs" is the difference -- so the
 * three tiles cannot disagree with the statement under them. The rows below
 * only GROUP the statement's own deduction lines; a line this map does not
 * know lands in "Other".
 *
 * THE ROWS ADD UP TO "YOUR COSTS". By construction the statement's deduction
 * lines sum to sales minus profit (domain/pnl.LINES, measured against
 * sales_data.period_money). Pennies of rounding go on the largest row; anything
 * bigger is shown as its own row, "Difference from the statement", and logged
 * -- it would be a bug, and a label that made it look normal would hide it.
 */
// Which group each statement line belongs to...
const _PNL_GROUP_OF = {
  cogs: "stock", ad_spend: "ads",
  referral_fees: "fees", fba_fees: "fees", promo_fees: "fees", other_fees: "fees",
  fees_estimated: "fees", account_charges: "fees", refund_fees_returned: "fees",
  refunds: "refunds", vat_line: "vat", promos: "promos", charges: "charges",
  manual_expenses: "own", reimbursements: "back",
};
// ...and how each group is named and coloured (foundations.css --as-viz-*).
const _PNL_GROUP = {
  stock:   ["Stock",               "what the goods cost you",                    "var(--as-viz-stock)"],
  ads:     ["Advertising",         "Amazon ads",                                 "var(--as-viz-ads)"],
  fees:    ["Amazon fees",         "referral, FBA, promotion and account fees",  "var(--as-viz-fees)"],
  refunds: ["Refunds",             "given back, on the day the money went back", "var(--as-viz-refunds)"],
  vat:     ["VAT",                 "collected for HMRC, not earned",             "var(--as-viz-compare)"],
  promos:  ["Coupons and deals",   "discounts you funded",                       "var(--as-viz-postage)"],
  charges: ["Per-product charges", "postage, packaging and the like",            "var(--as-viz-supplier)"],
  own:     ["Your own costs",      "the ones Amazon never sees",                 "var(--as-viz-referral)"],
  back:    ["Money back",          "reimbursements from Amazon",                 "var(--as-viz-profit)"],
  other:   ["Other",               "lines not listed above",                     "var(--as-viz-other)"],
  rest:    ["Difference from the statement", "should be nothing -- please report it", "var(--as-border-strong)"],
};
const _PNL_ROUGH = {"part-actual": 1, "not itemised": 1,
                    "estimated at the account's measured rate": 1};

function pnlSummary(lines){
  const by = {};
  (lines || []).forEach(function(l){ by[l.key] = l; });
  const num = function(k){
    const l = by[k];
    return (l && l.value !== null && l.value !== undefined) ? Number(l.value) : null;
  };
  const sold = num("ordered_sales"), kept = num("profit");
  if(sold === null || kept === null) return null;
  const groups = {}, order = [];
  let rough = false;
  const missing = [];
  (lines || []).forEach(function(l){
    if(l.sign !== 1 && l.sign !== -1) return;          // subtotals
    if(l.key === "ordered_sales") return;               // the sales themselves
    if(l.value === null || l.value === undefined){ missing.push(l.label || l.key); return; }
    if(_PNL_ROUGH[l.basis]) rough = true;
    const id = _PNL_GROUP_OF[l.key] || "other";
    const meta = _PNL_GROUP[id];
    if(!groups[id]){
      groups[id] = {id: id, label: meta[0], why: meta[1], colour: meta[2], amount: 0};
      order.push(id);
    }
    // A cost is what LEFT the sales: a -1 line of 5 is 5; a +1 line (money
    // back) reduces the costs. Math.abs because the server may sign the value.
    // Values arrive positive (sales_data stores every money column so); used as
    // sent, so a wrongly signed one shows up rather than being hidden by abs().
    groups[id].amount += (l.sign === -1 ? 1 : -1) * Number(l.value);
  });
  const costs = Math.round((sold - kept) * 100) / 100;
  let named = 0;
  order.forEach(function(id){ named += groups[id].amount; });
  const rest = Math.round((costs - named) * 100) / 100;
  if(Math.abs(rest) >= 0.01 && Math.abs(rest) <= 0.05 && order.length){
    // Rounding: each line was rounded on its own. Onto the largest row.
    let big = order[0];
    order.forEach(function(id){ if(groups[id].amount > groups[big].amount) big = id; });
    groups[big].amount += rest;
  }else if(Math.abs(rest) > 0.05){
    if(typeof console !== "undefined") console.warn("P&L: cost rows differ from sales - profit by", rest);
    const m = _PNL_GROUP.rest;
    groups.rest = {id: "rest", label: m[0], why: m[1], colour: m[2], amount: rest};
    order.push("rest");
  }
  const rows = order.map(function(id){
    const g = groups[id];
    g.amount = Math.round(g.amount * 100) / 100;
    g.pct = sold ? (g.amount / sold * 100) : null;
    return g;
  }).filter(function(g){ return Math.abs(g.amount) >= 0.005; })
    .sort(function(a, b){ return b.amount - a.amount; });   // largest first
  return {sold: sold, kept: kept, costs: costs,
          rows: rows, missing: missing, rough: rough};
}

function pnlPlainHtml(j, cur){
  const s = pnlSummary(j.lines);
  if(!s) return "";
  const lost = s.kept < 0;
  // THE STATEMENT'S OWN MARGIN (profit over sales after VAT, domain/pnl), not
  // a second one worked out here over sales including VAT.
  const per10 = (j.margin_pct === null || j.margin_pct === undefined)
    ? null : Number(j.margin_pct) / 10;
  const ten = _pnlMoney(10, cur).replace(/[.,]00$/, "");
  const n = (j.fee_coverage || {}).orders;
  const tile = function(cls, label, value, sub){
    return '<div class="pnl-tile' + cls + '"><div class="pnl-tl">' + label + '</div>'
      + '<div class="pnl-tv">' + value + '</div>'
      + '<div class="pnl-ts">' + sub + '</div></div>';
  };
  let h = '<div class="pnl-plain">'
    + '<div class="pnl-tiles">'
    + tile("", "You sold", _pnlMoney(s.sold, cur),
           n ? ("from " + n + " order" + (n === 1 ? "" : "s")) : "sales in this window")
    + tile("", "Your costs", _pnlMoney(s.costs, cur),
           "stock, ads, Amazon fees and more")
    + tile(lost ? " lost" : " kept", lost ? "You lost" : "You kept (profit)",
           _pnlMoney(Math.abs(s.kept), cur),
           per10 === null ? "" : (lost
             ? ("about " + _pnlMoney(Math.abs(per10), cur) + " lost on every "
                + ten + " of sales after VAT")
             : ("about " + _pnlMoney(per10, cur) + " from every "
                + ten + " of sales after VAT")))
    + '</div>';
  if(s.rows.length){
    h += '<div class="pnl-where"><div class="pnl-wh">Where your costs went</div>';
    s.rows.forEach(function(r){
      const w = (r.pct === null || r.amount <= 0) ? 0 : Math.min(100, r.pct);
      h += '<div class="pnl-row">'
        + '<span class="pnl-sw" style="background:' + r.colour + '"></span>'
        + '<div class="pnl-rl"><b>' + esc(r.label) + '</b>'
        +   '<span>' + esc(r.why) + '</span></div>'
        + '<div class="pnl-ra">' + (r.amount < 0 ? "−" : "")
        +   _pnlMoney(Math.abs(r.amount), cur) + '</div>'
        + '<div class="pnl-bar" aria-hidden="true"><i style="width:' + w.toFixed(1)
        +   '%;background:' + r.colour + '"></i></div>'
        + '<div class="pnl-rp">' + (r.pct === null ? "" : (r.pct.toFixed(1) + "% of sales"))
        + '</div></div>';
    });
    h += '</div>';
  }
  // THE GREEN TILE MUST NOT OVERSELL. Units with no cost recorded mean stock
  // was subtracted for none of them -- the server counts them (uncosted_units)
  // and the notes below say so; the tile's own alert says it too.
  const unc = Number(j.uncosted_units) || 0;
  // SAYS WHICH, rather than blaming Amazon for all of it: an advertising line
  // that is not connected, or own costs nobody has entered, are not Amazon's.
  if(s.missing.length || s.rough || unc){
    h += '<div class="pnl-alert" role="note"><i class="ti ti-alert-triangle"></i> '
      + (unc ? ('<b>' + unc + ' unit' + (unc === 1 ? ' has' : 's have') + ' no cost '
                + 'recorded</b>, so this profit is higher than the truth. ') : '')
      + (s.rough ? 'Amazon\'s fees are partly estimated until it settles. ' : '')
      + (s.missing.length ? ('Not known yet: ' + esc(s.missing.join(", ")) + '. ') : '')
      + 'The statement and notes below say more.</div>';
  }
  return h + '</div>';
}

function pnlRender(){
  const host = document.getElementById("pnl_body");
  const j = PNL.data;
  if(!host || !j) return;
  const cur = j.currency || "";

  let h = pnlPlainHtml(j, cur);

  // ---- how much of this is measured -----------------------------------
  const cov = j.fee_coverage || {};
  if(cov.orders){
    const pct = cov.pct_settled === null ? null : Number(cov.pct_settled);
    h += '<div class="odp-note' + ((pct !== null && pct < 50) ? " warn" : "")
      + '" style="margin:0 0 10px;padding:9px 11px;font-size:11.5px;'
      + 'line-height:1.6"><b>' + (pct === null ? "—" : pct.toFixed(0))
      + '% of this window is settled.</b> ' + cov.settled + ' of ' + cov.orders
      + ' orders carry the fees Amazon actually charged; the other '
      + cov.estimated + ' are charged at this account\'s measured rate of '
      + ((Number(j.fee_rate) || 0) * 100).toFixed(2) + '%. The figure tightens '
      + 'on its own as Amazon settles.</div>';
  }

  // ---- the statement ---------------------------------------------------
  h += '<div class="panelcard" style="padding:0;overflow:hidden;margin:0 0 12px">'
    + '<table class="kv" style="width:100%"><tbody>';
  (j.lines || []).forEach(function(l){
    // The three subtotal rows carry sign 0 and are the ones worth weight.
    const isTotal = (l.sign === 0);
    const b = _PNL_BASIS[l.basis];
    h += '<tr' + (isTotal ? ' style="font-weight:600"' : '') + '>'
      + '<td style="padding:8px 14px' + (isTotal
          ? ';border-top:1px solid var(--line2)' : '') + '">'
      +   esc(l.label)
      +   (b ? '<div class="cc" style="font-size:10.5px;font-weight:400;'
              + 'color:' + b[1] + '">' + esc(b[0]) + '</div>' : '')
      + '</td>'
      + '<td style="padding:8px 14px;text-align:right;white-space:nowrap'
      +   (isTotal ? ';border-top:1px solid var(--line2)' : '') + '">'
      +   (l.sign === -1 && l.value ? "−" : "")
      +   _pnlMoney(l.value === null || l.value === undefined
                    ? null : Math.abs(l.value), cur)
      + '</td></tr>';
  });
  h += '</tbody></table></div>';

  // ---- VAT, both ways --------------------------------------------------
  h += pnlVat(j, cur);

  // ---- the costs Amazon never sees -------------------------------------
  h += pnlExpenses(j, cur);

  // ---- everything the statement wants understood -----------------------
  if((j.notes || []).length){
    h += '<div class="panelcard" style="padding:12px 14px">'
      + '<div style="font-weight:600;margin-bottom:6px">What this figure '
      + 'assumes</div><ul style="margin:0 0 0 16px;padding:0;font-size:11.5px;'
      + 'line-height:1.7;color:var(--ink2)">';
    (j.notes || []).forEach(function(n){
      if(n) h += '<li>' + esc(n) + '</li>';
    });
    h += '</ul></div>';
  }

  host.innerHTML = h;
}

/* VAT: gross, the tax, and the net -- with the basis that produced them.
 *
 * `unknown` and `none` are the two that matter. "Not registered" is a real
 * answer and produces a real zero; "nobody has said" is not, and the profit
 * above is overstated by whatever the rate would have been. */
function pnlVat(j, cur){
  const v = j.vat || {};
  if(!v.basis) return "";
  const risky = (v.basis === "unknown" || v.basis === "none");
  return '<div class="panelcard" style="padding:12px 14px;margin:0 0 12px">'
    + '<div style="display:flex;justify-content:space-between;'
    +   'align-items:center;flex-wrap:wrap;gap:8px">'
    + '<div style="font-weight:600">VAT</div>'
    + '<div class="cc" style="font-size:11px">'
    +   esc({amazon: "from Amazon's own tax figures",
             derived: "worked out from the rate on this account",
             none: "this account is set as not registered",
             unknown: "no rate set, and Amazon sent no tax figures"}[v.basis]
            || v.basis) + '</div></div>'
    + '<table class="kv" style="width:100%;margin-top:8px"><tbody>'
    + '<tr><td style="padding:5px 0">Sales including VAT</td>'
    +   '<td style="text-align:right">' + _pnlMoney(v.sales_gross, cur) + '</td></tr>'
    + '<tr><td style="padding:5px 0">VAT in them</td>'
    +   '<td style="text-align:right">' + _pnlMoney(v.amount, cur) + '</td></tr>'
    + '<tr><td style="padding:5px 0">Sales excluding VAT</td>'
    +   '<td style="text-align:right">' + _pnlMoney(v.sales_ex_vat, cur) + '</td></tr>'
    + '</tbody></table>'
    + '<div class="cc' + (risky ? " " : " ") + '" style="font-size:11px;'
    +   'margin-top:7px;line-height:1.6' + (risky ? ';color:var(--warn)' : '')
    +   '">' + esc(v.explain || "") + ' The VAT line in the statement above is '
    + 'this figure — the profit is already after it.</div>'
    + '</div>';
}

/* The costs Amazon never sees, and the one it charges against no order. */
function pnlExpenses(j, cur){
  const e = PNL.expenses || {};
  const win = e.window || {};
  const items = win.items || [];
  const sug = j.suggested_expense;

  let h = '<div class="panelcard" style="padding:12px 14px;margin:0 0 12px">'
    + '<div style="display:flex;justify-content:space-between;'
    +   'align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px">'
    + '<div><div style="font-weight:600">Your own costs</div>'
    +   '<div class="cc" style="font-size:11px">The accountant, the software, '
    +   'the packaging, the postage bought elsewhere — Amazon reports none of '
    +   'it, so a profit without it is not the business\'s profit.</div></div>'
    + '<button class="db-chip" onclick="pnlAddOpen()">'
    +   '<i class="ti ti-plus"></i> Add a cost</button></div>';

  // THE AMAZON CHARGE THAT BELONGS TO NO ORDER, offered ready to accept. The
  // statement could always SEE it; until now all it could do was ask somebody
  // to remember a number and do something about it elsewhere.
  if(sug){
    h += '<div class="odp-note warn" style="padding:9px 11px;margin:0 0 9px;'
      + 'font-size:11.5px;line-height:1.6">'
      + esc(sug.why)
      + '<div style="margin-top:7px"><button class="db-chip" '
      + 'onclick="pnlAcceptSuggestion()"><i class="ti ti-check"></i> '
      + 'Add “' + esc(sug.name) + '” at ' + _pnlMoney(sug.amount, cur)
      + ' a month</button></div></div>';
  }

  if(PNL.adding){
    h += '<div class="odp-note" style="padding:10px 12px;margin:0 0 9px">'
      + '<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">'
      + '<input id="pnlx_name" class="ed" placeholder="What is it? e.g. Accountant" '
      +   'style="min-width:180px">'
      + '<input id="pnlx_amount" class="ed" placeholder="per month" '
      +   'style="width:110px">'
      + '<input id="pnlx_starts" class="ed" type="date" style="width:150px" '
      +   'value="' + esc((j.start || "").slice(0, 10)) + '">'
      + '<button class="db-chip" onclick="pnlAddSave()">Save</button>'
      + '<button class="db-chip" onclick="pnlAddCancel()">Cancel</button>'
      + '</div>'
      + '<div class="cc" style="font-size:11px;margin-top:6px">The amount is '
      + '<b>per month</b>, and only the days of it inside the window you are '
      + 'looking at are counted — a fortnight carries half a month.</div>'
      + '</div>';
  }

  if(!items.length){
    h += '<div class="cc" style="font-size:11.5px">'
      + (e.all && e.all.length
          ? ('Nothing you have recorded falls inside ' + esc(j.start || "")
             + ' to ' + esc(j.end || "") + '.')
          : 'Nothing recorded yet, so nothing has been subtracted for it.')
      + '</div></div>';
    return h;
  }

  h += '<table class="kv" style="width:100%"><thead><tr>'
    + '<th style="text-align:left">Cost</th>'
    + '<th style="text-align:right">Per month</th>'
    + '<th style="text-align:right">In this window</th>'
    + '<th></th></tr></thead><tbody>';
  items.forEach(function(x){
    h += '<tr><td style="padding:6px 0">' + esc(x.name)
      +   (x.category ? ' <span class="cc" style="font-size:10.5px">'
                        + esc(x.category) + '</span>' : '')
      +   '<div class="cc" style="font-size:10.5px">' + esc(x.starts)
      +   (x.ends ? (" to " + esc(x.ends)) : " onwards")
      +   ' · ' + x.days + ' day' + (x.days === 1 ? "" : "s") + ' here'
      +   (x.marketplace ? (" · " + esc(x.marketplace)) : " · all marketplaces")
      +   '</div></td>'
      + '<td style="text-align:right">' + _pnlMoney(x.monthly, cur) + '</td>'
      + '<td style="text-align:right">' + _pnlMoney(x.in_window, cur) + '</td>'
      + '<td style="text-align:right"><button class="ghost" '
      +   'onclick="pnlDeleteExpense(' + x.id + ',' + jsArg(x.name)
      +   ')">Remove</button></td></tr>';
  });
  h += '<tr style="font-weight:600"><td style="padding:7px 0;'
    +   'border-top:1px solid var(--line2)">Total in this window</td>'
    + '<td style="border-top:1px solid var(--line2)"></td>'
    + '<td style="text-align:right;border-top:1px solid var(--line2)">'
    +   _pnlMoney(win.total, cur) + '</td><td style="border-top:1px solid '
    +   'var(--line2)"></td></tr>'
    + '</tbody></table>'
    + '<div class="cc" style="font-size:11px;margin-top:7px">'
    + esc(e.note || "") + '</div></div>';
  return h;
}

function pnlAddOpen(){ PNL.adding = true; pnlRender(); }
function pnlAddCancel(){ PNL.adding = false; pnlRender(); }

async function pnlAddSave(){
  const g = function(id){
    const el = document.getElementById(id);
    return ((el && el.value) || "").trim();
  };
  const j = PNL.data || {};
  const body = {account: j.workspace, marketplace: j.marketplace,
                name: g("pnlx_name"), amount: g("pnlx_amount"),
                starts: g("pnlx_starts")};
  if(!body.name || !body.amount || !body.starts){
    if(typeof toast === "function")
      toast("A cost needs a name, an amount and a start date.");
    return;
  }
  try{
    const r = await (await fetch("/expenses", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)})).json();
    if(!r || !r.ok){
      if(typeof toast === "function")
        toast("Could not save that: " + ((r && r.error) || "unknown"));
      return;
    }
    PNL.adding = false;
    if(typeof toast === "function") toast("Cost recorded. Profit will be lower.");
    pnlLoad();
  }catch(e){
    if(typeof toast === "function") toast("Could not save that cost.");
  }
}

async function pnlDeleteExpense(id, name){
  // ASKED FIRST. Removing a cost puts profit UP, which is the direction nobody
  // questions -- so a mis-click here is the kind that goes unnoticed.
  //
  // AWAITED. uiConfirm returns a Promise, and a Promise object is always
  // truthy: `if(!uiConfirm(...))` would never stop anything and would look
  // right in review. That is the whole reason test_no_native_dialogs checks it.
  const ok = await uiConfirm('Remove "' + name + '"? Profit for every window it '
                             + 'touched will go up by its share of it.');
  if(!ok) return;
  const j = PNL.data || {};
  try{
    const r = await (await fetch("/expenses/delete", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({account: j.workspace, id: id})})).json();
    if(!r || !r.ok){
      if(typeof toast === "function")
        toast("Could not remove that: " + ((r && r.error) || "unknown"));
      return;
    }
    if(typeof toast === "function") toast("Removed.");
    pnlLoad();
  }catch(e){
    if(typeof toast === "function") toast("Could not remove that cost.");
  }
}

async function pnlAcceptSuggestion(){
  const j = PNL.data || {};
  try{
    const q = [];
    if(j.workspace) q.push("account=" + encodeURIComponent(j.workspace));
    if(j.marketplace) q.push("marketplace=" + encodeURIComponent(j.marketplace));
    if(j.start) q.push("start=" + encodeURIComponent(j.start));
    if(j.end) q.push("end=" + encodeURIComponent(j.end));
    const r = await (await fetch("/expenses/accept?" + q.join("&"), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: "{}"})).json();
    if(!r || !r.ok){
      if(typeof toast === "function")
        toast("Could not add it: " + ((r && r.error) || "unknown"));
      return;
    }
    if(typeof toast === "function") toast(r.note || "Added.");
    pnlLoad();
  }catch(e){
    if(typeof toast === "function") toast("Could not add it.");
  }
}
