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
 * VAT IS SHOWN BOTH WAYS AND NEVER SUBTRACTED SILENTLY. Whether an account is
 * registered is a fact about the business that this app cannot measure. Taking
 * a fifth off somebody who is not registered is as wrong as leaving it in for
 * somebody who is, so both figures are on screen and the basis says which one
 * to use.
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
    const j = await (await fetch("/sales/pnl?" + qs)).json();
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
      PNL.expenses = await (await fetch("/expenses?" + q2.join("&"))).json();
    }catch(e){ PNL.expenses = null; }
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

function pnlRender(){
  const host = document.getElementById("pnl_body");
  const j = PNL.data;
  if(!host || !j) return;
  const cur = j.currency || "";

  let h = "";

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
    + '<tr style="font-weight:600"><td style="padding:5px 0;'
    +   'border-top:1px solid var(--line2)">Profit excluding VAT</td>'
    +   '<td style="text-align:right;border-top:1px solid var(--line2)">'
    +   _pnlMoney(v.profit_ex_vat, cur) + '</td></tr>'
    + '</tbody></table>'
    + '<div class="cc' + (risky ? " " : " ") + '" style="font-size:11px;'
    +   'margin-top:7px;line-height:1.6' + (risky ? ';color:var(--warn)' : '')
    +   '">' + esc(v.explain || "") + ' Nothing is taken off automatically — '
    + 'the profit line above includes VAT, and this is what it looks like '
    + 'without.</div>'
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
