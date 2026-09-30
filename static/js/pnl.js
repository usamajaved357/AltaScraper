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

const PNL = {data: null, loading: false, expenses: null, adding: false,
             host: "pnl_body", qs: null,
             // The line breakdowns (pnlLedger*): which lines are open, what
             // each one loaded, whether the missing-cost list is open, and the
             // account/marketplace/dates they belong to.
             open: {}, ledgers: {}, missingOpen: false, scopeKey: ""};

/* ONE STATEMENT, TWO PLACES (owner, 30 Sep 2026: "where can i see the account
 * level profits by the date range i can select myself, lets add this into the
 * finance tab"). The Sales page calls pnlLoad() and it reads the Sales date
 * range; the Finance tab calls pnlLoad("fin_pnl", its own query). Same route,
 * same domain/pnl.build -- so the two cannot disagree (Rule 12). */
async function pnlLoad(hostId, qsIn){
  // ONE STATEMENT ON SCREEN AT A TIME: the other place's copy is cleared, so
  // its buttons cannot act on this one's dates (review, 30 Sep 2026).
  const _prev = PNL.host;
  if(_prev && _prev !== (hostId || "pnl_body")){
    const old = document.getElementById(_prev);
    if(old) old.innerHTML = "";
  }
  PNL.host = hostId || "pnl_body";
  PNL.qs = (qsIn === undefined) ? null : qsIn;
  const host = document.getElementById(PNL.host);
  if(!host) return;
  // Newest ask wins (it returned while one was running, so a changed range
  // was dropped).
  const _seq = PNL.seq = (PNL.seq || 0) + 1;
  PNL.loading = true;
  host.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Working out the profit…</div>';
  try{
    // The screen that asked owns the date range: the Sales page's by default,
    // so the two Sales views cannot answer for different months.
    const qs = (PNL.qs !== null) ? PNL.qs : ((typeof _sQuery === "function") ? _sQuery() : "");
    const _sc = (typeof screenScope === "function") ? screenScope() : null;  // audit S5
    const j = await (await fetch("/sales/pnl?" + qs)).json();
    if(_sc && !screenStillIn(_sc)) return;   // switched account/marketplace meanwhile
    if(_seq !== PNL.seq) return;             // a newer ask is on its way
    PNL.loading = false;
    if(!j || j.ok === false){
      host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + esc((j && j.error) || "Could not work out the profit.") + '</div>';
      return;
    }
    PNL.data = j;
    // THE BREAKDOWNS BELONG TO THIS STATEMENT. Loaded items are always
    // re-read (a cost may just have been saved); which lines are open is kept
    // only while the account, marketplace and dates are the same.
    PNL.ledgers = {};
    const _key = [j.workspace, j.marketplace, j.start, j.end].join("|");
    if(_key !== PNL.scopeKey){ PNL.open = {}; PNL.missingOpen = false; }
    PNL.scopeKey = _key;
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
    if(_seq !== PNL.seq) return;
    pnlRender();
  }catch(e){
    if(_seq !== PNL.seq) return;
    PNL.loading = false;
    host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + 'Could not work out the profit.</div>';
  }
}

/* Reload the statement where it is showing, with the same range (the costs
 * buttons below). */
function pnlReload(){ pnlLoad(PNL.host, PNL.qs === null ? undefined : PNL.qs); }

function _pnlMoney(v, cur){
  if(v === null || v === undefined){
    return '<span class="cc" style="opacity:.5" title="Not known — see the '
      + 'notes below.">not known</span>';
  }
  // The app's one symbol map (money.js): this fell back to £ for every
  // currency but USD and EUR (Finance review, 30 Sep 2026).
  const sym = (typeof curSymbol === "function") ? curSymbol(cur)
            : ((cur === "USD") ? "$" : (cur === "EUR") ? "€" : "£");
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
  other_amazon: "fees",           // signed: postage labels, Vine, tax corrections (30 Sep 2026)
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
      // THE COUNT OPENS THE LIST (owner, 30 Sep 2026: "which sku's dont have
      // the cogs i want the orders numbers of them") -- pnlMissingOpen.
      + (unc ? ('<a href="#" class="pnl-mlink" role="button" aria-controls="pnl_missing" '
                + 'aria-expanded="' + (!!PNL.missingOpen) + '" onclick="pnlMissingOpen();return false">'
                + '<b>' + unc + ' unit' + (unc === 1 ? ' has' : 's have') + ' no cost '
                + 'recorded</b></a>, so this profit is higher than the truth. ') : '')
      + (s.rough ? 'Amazon\'s fees are partly estimated until it settles. ' : '')
      + (s.missing.length ? ('Not known yet: ' + esc(s.missing.join(", ")) + '. ') : '')
      + 'The statement and notes below say more.</div>';
  }
  return h + '</div>';
}

function pnlRender(){
  const host = document.getElementById(PNL.host || "pnl_body");
  const j = PNL.data;
  if(!host || !j) return;
  const cur = j.currency || "";

  let h = pnlPlainHtml(j, cur);

  // ---- the products with no cost, when asked for ----------------------
  h += '<div id="pnl_missing">' + (PNL.missingOpen ? pnlMissingHtml() : '') + '</div>';

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
    // EVERY LINE OPENS ITS ITEMS (pnlLedgerToggle): the orders, postings,
    // days or costs it is made of, with a check that they add up to it.
    const canOpen = pnlLedgerCan(l.key);
    const isOpen = !!PNL.open[l.key];
    h += '<tr' + (isTotal ? ' style="font-weight:600"' : '') + '>'
      + '<td style="padding:8px 14px' + (isTotal
          ? ';border-top:1px solid var(--line2)' : '') + '">'
      +   (canOpen
            ? '<button type="button" class="pnl-lx" aria-expanded="' + isOpen + '" '
              + 'aria-controls="pnl_led_' + esc(l.key) + '" '
              + 'onclick="pnlLedgerToggle(' + jsArg(l.key) + ')">'
              + '<i class="ti ti-chevron-' + (isOpen ? 'down' : 'right') + '"></i>'
              + esc(l.label) + '</button>'
            : esc(l.label))
      +   (b ? '<div class="cc" style="font-size:10.5px;font-weight:400;'
              + 'color:' + b[1] + '">' + esc(b[0]) + '</div>' : '')
      // WHERE THE AD FIGURE CAME FROM, and the VAT inside it -- so the line can
      // be checked against Amazon's own numbers (owner: "i want the breakdown
      // of profits how are they calculated so i can trust").
      +   (l.key === "ad_spend" && (j.ads_source || j.ads_vat_added)
            ? '<div class="cc" style="font-size:10.5px;font-weight:400">'
              + esc({ads_api: "Amazon Ads API spend", invoices: "Amazon's ad invoices",
                     both: "Ads API spend, and invoices before it connected"}[j.ads_source] || "")
              + (j.ads_vat_added ? " · includes " + _pnlMoney(j.ads_vat_added, cur).replace(/<[^>]*>/g, "")
                                   + " VAT on ads" : "")
              + '</div>' : '')
      + '</td>'
      + '<td style="padding:8px 14px;text-align:right;white-space:nowrap'
      +   (isTotal ? ';border-top:1px solid var(--line2)' : '') + '">'
      +   (l.sign === -1 && l.value ? "−" : "")
      +   _pnlMoney(l.value === null || l.value === undefined
                    ? null : Math.abs(l.value), cur)
      + '</td></tr>';
    if(canOpen){
      h += '<tr class="pnl-led-tr" id="pnl_led_' + esc(l.key) + '"'
        + (isOpen ? '' : ' hidden') + '><td colspan="2">'
        + (isOpen ? pnlLedgerHtml(l.key) : '') + '</td></tr>';
    }
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
  // Open lines (and the missing-cost list) whose items are not loaded yet --
  // after a reload, or a cost just saved -- ask for them again.
  Object.keys(PNL.open).forEach(function(k){
    if(PNL.open[k] && !_PNL_SUBTOTALS[k] && !PNL.ledgers[k]) pnlLedgerFetch(k);
  });
  if(PNL.missingOpen && !PNL.ledgers.cogs) pnlLedgerFetch("cogs");
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
    pnlReload();
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
    pnlReload();
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
    pnlReload();
  }catch(e){
    if(typeof toast === "function") toast("Could not add it.");
  }
}

/* ==== THE ITEMS BEHIND EACH LINE (owner, 30 Sep 2026) =====================
 *
 *   "i want every detailed breakdown of how these profit numbers are
 *    calculated and also references so i can verify them"
 *
 * Opening a line loads its items from /sales/pnl/ledger (domain/pnl_ledger:
 * the same reads and per-order arithmetic the statement is built from) for
 * the SAME account, marketplace and dates as the statement on screen. The
 * items' total is checked against the line itself, and a difference is said
 * in red -- never smoothed over. The three subtotals are explained from the
 * statement's own lines, here, because they are nothing more than those.
 */

// Lines the server can itemise (domain/pnl_ledger.LEDGER_LINES).
const _PNL_LEDGER_KEYS = {ordered_sales: 1, vat_line: 1, refunds: 1, cogs: 1,
  referral_fees: 1, fba_fees: 1, promo_fees: 1, other_fees: 1, fees_estimated: 1,
  promos: 1, refund_fees_returned: 1, reimbursements: 1, charges: 1, ad_spend: 1,
  account_charges: 1, other_amazon: 1, manual_expenses: 1};
// The subtotals, and the statement lines each is made of (domain/pnl.build).
const _PNL_SUBTOTALS = {
  net_sales: ["ordered_sales", "vat_line", "refunds"],
  profit_before_own_costs: "above",       // every +/- line above it
  profit: ["profit_before_own_costs", "account_charges", "other_amazon",
           "manual_expenses"],
};

function pnlLedgerCan(key){ return !!(_PNL_LEDGER_KEYS[key] || _PNL_SUBTOTALS[key]); }

function _pnlLine(key){
  return ((PNL.data && PNL.data.lines) || []).filter(function(l){ return l.key === key; })[0] || null;
}

function _pnlR2(v){ return Math.round(Number(v || 0) * 100) / 100; }

/* A subtotal, explained: its lines, signed, from the statement itself. */
function pnlSubtotalItems(key, lines){
  const want = _PNL_SUBTOTALS[key];
  const all = lines || [];
  let parts = [];
  if(want === "above"){
    for(let i = 0; i < all.length && all[i].key !== key; i++){
      if(all[i].sign === 1 || all[i].sign === -1) parts.push(all[i]);
    }
  }else{
    parts = all.filter(function(l){ return want.indexOf(l.key) >= 0; });
  }
  const items = parts.map(function(l){
    const known = !(l.value === null || l.value === undefined);
    // A subtotal line (sign 0) adds in as it stands; "other" lines are signed.
    const sign = (l.sign === 0 || l.key === "other_amazon") ? 1 : l.sign;
    return {label: l.label, amount: known ? sign * Number(l.value) : 0,
            known: known};
  });
  let t = 0;
  items.forEach(function(i){ t += i.amount; });
  return {items: items, total: _pnlR2(t)};
}

/* The check: items total against the line on screen. -> {state, text}. */
function pnlLedgerRecon(total, lineValue, count, cur){
  const m = function(v){ return _pnlMoney(v, cur).replace(/<[^>]*>/g, ""); };
  if(lineValue === null || lineValue === undefined){
    return {state: "unknown", text: count + " item" + (count === 1 ? "" : "s")
            + " · items total " + m(total) + " · the line itself is not known"};
  }
  const diff = _pnlR2(Number(total) - Number(lineValue));
  if(Math.abs(diff) < 0.005){
    return {state: "ok", text: count + " item" + (count === 1 ? "" : "s")
            + " · items total " + m(total) + " = line " + m(lineValue)};
  }
  return {state: "bad", text: "Items total " + m(total) + " does not match the line "
          + m(lineValue) + " (difference " + m(diff) + "). Please report this."};
}

function pnlLedgerToggle(key){
  PNL.open[key] = !PNL.open[key];
  if(PNL.open[key] && !_PNL_SUBTOTALS[key] && !PNL.ledgers[key]) pnlLedgerFetch(key);
  pnlLedgerDraw(key);
}

/* Redraw ONE line's items in place (the rest of the statement keeps its state). */
function pnlLedgerDraw(key){
  const tr = document.getElementById("pnl_led_" + key);
  if(!tr) return;
  const open = !!PNL.open[key];
  if(open) tr.removeAttribute("hidden"); else tr.setAttribute("hidden", "");
  const td = tr.querySelector("td");
  if(td) td.innerHTML = open ? pnlLedgerHtml(key) : "";
  const btn = tr.previousElementSibling && tr.previousElementSibling.querySelector(".pnl-lx");
  if(btn){
    btn.setAttribute("aria-expanded", String(open));
    const ic = btn.querySelector(".ti");
    if(ic) ic.className = "ti ti-chevron-" + (open ? "down" : "right");
  }
}

async function pnlLedgerFetch(key){
  const j = PNL.data;
  if(!j) return;
  const seq = PNL.seq;
  const _sc = (typeof screenScope === "function") ? screenScope() : null;
  PNL.ledgers[key] = {loading: true};
  pnlLedgerDraw(key);
  if(key === "cogs") _pnlMissingDraw();
  // THE STATEMENT'S OWN SCOPE, as the server resolved it -- not the picker's.
  const q = ["line=" + encodeURIComponent(key)];
  if(j.workspace) q.push("account=" + encodeURIComponent(j.workspace));
  if(j.marketplace) q.push("marketplace=" + encodeURIComponent(j.marketplace));
  if(j.start) q.push("start=" + encodeURIComponent(j.start));
  if(j.end) q.push("end=" + encodeURIComponent(j.end));
  let r;
  try{
    r = await (await fetch("/sales/pnl/ledger?" + q.join("&"))).json();
  }catch(e){
    r = {ok: false, error: "Could not reach the server."};
  }
  if((_sc && typeof screenStillIn === "function" && !screenStillIn(_sc))
     || seq !== PNL.seq || PNL.data !== j){
    // A newer statement (or another account) is on screen: this reply lands
    // nowhere -- and a placeholder it left is cleared so a later draw asks again.
    const cur = PNL.ledgers[key];
    if(cur && cur.loading && PNL.data !== j) delete PNL.ledgers[key];
    return;
  }
  PNL.ledgers[key] = (r && r.ok) ? r : {error: (r && r.error) || "Could not load the items."};
  pnlLedgerDraw(key);
  if(key === "cogs") _pnlMissingDraw();
}

function _pnlScUrl(oid, mkt){
  if(typeof _opSellerCentral === "function") return _opSellerCentral(oid, mkt);
  return "https://sellercentral.amazon.co.uk/orders-v3/order/" + encodeURIComponent(oid);
}

/* An order id: opens it on Orders, and on Seller Central to check Amazon's own. */
function _pnlOrderCell(oid, mkt){
  if(!oid) return '<span class="cc">—</span>';
  return '<a href="#" onclick="return pnlOpenOrder(' + jsArg(oid) + ')" '
    + 'title="Open on Orders">' + esc(oid) + '</a> '
    + '<a href="' + esc(_pnlScUrl(oid, mkt)) + '" target="_blank" rel="noopener" '
    + 'title="Open on Seller Central" aria-label="Open ' + esc(oid) + ' on Seller Central">'
    + '<i class="ti ti-external-link"></i></a>';
}

/* The same jump the buyer-messages screen makes (inbox.js), not a second one. */
function pnlOpenOrder(oid){
  if(typeof inboxOpenOrder === "function") return inboxOpenOrder(oid);
  if(typeof navTo === "function") navTo("orders");
  return false;
}

const _PNL_LED_MAX = 400;    // drawn on screen; the CSV always carries all

function pnlLedgerHtml(key){
  const j = PNL.data || {};
  const cur = j.currency || "";
  const line = _pnlLine(key) || {};
  if(_PNL_SUBTOTALS[key]){
    const st = pnlSubtotalItems(key, j.lines);
    const rc = pnlLedgerRecon(st.total, line.value, st.items.length, cur);
    let h = '<div class="pnl-led">' + _pnlRecHtml(rc) + '<table class="pnl-led-t pnl-led-sub"><tbody>';
    st.items.forEach(function(i){
      h += '<tr><td>' + esc(i.label) + (i.known ? '' : ' <span class="cc">(not known, counted as 0)</span>')
        + '</td><td class="pnl-led-a">' + _pnlMoney(i.amount, cur) + '</td></tr>';
    });
    return h + '</tbody></table></div>';
  }
  const d = PNL.ledgers[key];
  if(!d || d.loading){
    return '<div class="pnl-led cc"><span class="genspin"></span> Loading the items…</div>';
  }
  if(d.error){
    return '<div class="pnl-led">' + (typeof uiNote === "function"
        ? uiNote("bad", "Could not load the items.", d.error)
        : '<div style="color:var(--as-danger)">' + esc(d.error) + '</div>')
      + '<button type="button" class="db-chip" onclick="pnlLedgerRetry(' + jsArg(key)
      + ')"><i class="ti ti-refresh"></i> Try again</button></div>';
  }
  const items = d.items || [];
  const rc = pnlLedgerRecon(d.total, line.value, items.length, cur);
  let h = '<div class="pnl-led">'
    + '<div class="pnl-led-bar">' + _pnlRecHtml(rc)
    + (items.length ? '<button type="button" class="db-chip" onclick="pnlLedgerCsvDownload('
       + jsArg(key) + ')"><i class="ti ti-download"></i> Download CSV</button>' : '')
    + '</div>';
  if(!items.length){
    return h + (typeof uiEmpty === "function"
      ? uiEmpty("Nothing in this window", "No orders, postings or costs make up this line.")
      : '<div class="cc">Nothing in this window.</div>') + '</div>';
  }
  const mkt = j.marketplace || d.marketplace || "";
  h += '<table class="pnl-led-t"><thead><tr><th>Date</th><th>Order</th><th>SKU</th>'
    + '<th class="pnl-led-n">Qty</th><th class="pnl-led-n">Amount</th><th>Source</th>'
    + '</tr></thead><tbody>';
  items.slice(0, _PNL_LED_MAX).forEach(function(i){
    h += '<tr' + (i.amount === null ? ' class="pnl-led-miss"' : '') + '>'
      // Each value in ONE span, so on a phone (label beside value) it stays together.
      + '<td data-l="Date"><span>' + esc(i.date || "—") + '</span></td>'
      + '<td data-l="Order"><span>' + _pnlOrderCell(i.order_id, mkt) + '</span></td>'
      + '<td data-l="SKU"><span>' + esc(i.sku || "—") + '</span></td>'
      + '<td data-l="Qty" class="pnl-led-n"><span>' + (i.qty === null || i.qty === undefined ? "—" : esc(i.qty)) + '</span></td>'
      + '<td data-l="Amount" class="pnl-led-n pnl-led-a"><span>'
      +   (i.amount === null ? '<span class="pnl-led-no">no cost</span>' : _pnlMoney(i.amount, cur)) + '</span></td>'
      + '<td data-l="Source"><span>' + esc(i.source || "")
      +   (i.ref ? '<div class="cc pnl-led-ref">' + esc(i.ref) + '</div>' : '') + '</span></td></tr>';
  });
  h += '</tbody></table>';
  if(items.length > _PNL_LED_MAX){
    h += '<div class="cc pnl-led-ref">Showing ' + _PNL_LED_MAX + ' of ' + items.length
      + ' — the CSV has every item.</div>';
  }
  return h + '</div>';
}

function _pnlRecHtml(rc){
  if(rc.state === "bad"){
    return '<div class="pnl-rec bad" role="alert"><i class="ti ti-alert-octagon"></i> '
      + esc(rc.text) + '</div>';
  }
  return '<div class="pnl-rec' + (rc.state === "ok" ? " ok" : "") + '">'
    + (rc.state === "ok" ? '<i class="ti ti-circle-check"></i> ' : '') + esc(rc.text) + '</div>';
}

function pnlLedgerRetry(key){ delete PNL.ledgers[key]; pnlLedgerFetch(key); }

/* The loaded items as CSV text -- every item, amounts unrounded, so a
 * spreadsheet's SUM gives the line. */
function pnlLedgerCsv(items){
  const q = function(v){
    let s = (v === null || v === undefined) ? "" : String(v);
    // Text that a spreadsheet would run as a formula is kept as text; numbers
    // (a negative amount included) stay numbers so SUM still works.
    if(typeof v === "string" && /^[=+\-@]/.test(s) && !isFinite(Number(s))) s = "'" + s;
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const rows = [["date", "order_id", "sku", "qty", "amount", "source", "reference"].join(",")];
  (items || []).forEach(function(i){
    rows.push([i.date, i.order_id, i.sku, i.qty, i.amount, i.source, i.ref].map(q).join(","));
  });
  return rows.join("\n");
}

function pnlLedgerCsvDownload(key){
  const d = PNL.ledgers[key], j = PNL.data || {};
  if(!d || !d.items) return;
  // A BOM, so a pound sign survives a double-click into Excel.
  const blob = new Blob(["\ufeff" + pnlLedgerCsv(d.items)], {type: "text/csv;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = ["pnl", key, j.workspace || "account", j.start || "", j.end || ""]
    .join("-").replace(/[^A-Za-z0-9_.-]+/g, "_") + ".csv";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(function(){ URL.revokeObjectURL(a.href); }, 4000);
}

/* ==== THE PRODUCTS WITH NO COST ===========================================
 * Per SKU: its orders (each linked), units and sale value, and a box to set
 * the product's cost (cogs.js cogsSet, the one caller of /cogs/set) -- or one
 * order's own cost (orders.js ordPostOrderCost, /cogs/order). The owner's
 * rule holds: an order's own cost wins for that order; the product cost fills
 * only the lines that have none (/cogs/refreeze without force). */

function pnlMissingOpen(){
  PNL.missingOpen = true;
  if(!PNL.ledgers.cogs) pnlLedgerFetch("cogs");
  _pnlMissingDraw();
  const el = document.getElementById("pnl_missing");
  if(el && el.scrollIntoView) try{ el.scrollIntoView({block: "nearest"}); }catch(e){}
}
function pnlMissingClose(){ PNL.missingOpen = false; _pnlMissingDraw(); }

function _pnlMissingDraw(){
  const el = document.getElementById("pnl_missing");
  if(el) el.innerHTML = PNL.missingOpen ? pnlMissingHtml() : "";
}

function pnlMissingHtml(){
  const j = PNL.data || {};
  const cur = j.currency || "";
  const d = PNL.ledgers.cogs;
  const close = '<button type="button" class="db-chip" onclick="pnlMissingClose()">Close</button>';
  const wrap = function(body){
    return (typeof uiPanel === "function")
      ? uiPanel("Products with no cost", "Profit is too high until these have one.", body, {right: close})
      : '<div class="panelcard">' + body + '</div>';
  };
  if(!d || d.loading) return wrap('<div class="cc"><span class="genspin"></span> Loading…</div>');
  if(d.error){
    return wrap((typeof uiNote === "function" ? uiNote("bad", "Could not load the list.", d.error)
                 : esc(d.error))
      + '<button type="button" class="db-chip" onclick="pnlLedgerRetry(' + jsArg("cogs") + ')">Try again</button>');
  }
  const miss = d.missing || [];
  if(!miss.length){
    return wrap(typeof uiEmpty === "function"
      ? uiEmpty("Every unit has a cost", "Nothing in this window is missing one.")
      : "Every unit has a cost.");
  }
  const mkt = j.marketplace || "";
  let b = '<div class="pnl-miss">';
  miss.forEach(function(m, i){
    b += '<div class="pnl-miss-sku">'
      + '<div class="pnl-miss-h"><div class="pnl-miss-t">' + esc(m.title || m.sku) + '</div>'
      +   '<div class="cc">' + esc(m.sku) + ' · ' + esc(m.units) + ' unit' + (m.units === 1 ? '' : 's')
      +   ' · sold for ' + _pnlMoney(m.value, cur) + '</div></div>'
      + (m.has_sku === false
          ? '<div class="cc pnl-miss-set">No SKU on these orders, so set the cost per order below.</div>'
          : '<div class="pnl-miss-set"><label class="cc" for="pnl_mc_' + i + '">Product cost</label>'
            + '<input id="pnl_mc_' + i + '" class="ed" inputmode="decimal" placeholder="per unit">'
            + '<button type="button" class="db-chip" onclick="pnlMissingSave(' + i + ')">Save</button></div>')
      + '<div class="pnl-miss-orders">';
    (m.orders || []).forEach(function(o, k){
      b += '<div class="pnl-miss-o">' + _pnlOrderCell(o.order_id, mkt)
        + ' <span class="cc">' + esc(o.date) + ' · ' + esc(o.qty) + ' unit' + (o.qty === 1 ? '' : 's')
        +   ' · ' + _pnlMoney(o.value, cur) + '</span>'
        + ' <input id="pnl_moc_' + i + '_' + k + '" class="ed pnl-miss-oc" inputmode="decimal" '
        +   'placeholder="this order" aria-label="Cost per unit for order ' + esc(o.order_id) + ' only">'
        + '<button type="button" class="db-chip" onclick="pnlMissingOrderSave(' + i + ',' + k
        +   ')">Save</button></div>';
    });
    b += '</div></div>';
  });
  return wrap(b + '</div>');
}

function _pnlCostInput(id){
  const el = document.getElementById(id);
  const raw = ((el && el.value) || "").trim();
  const n = Number(raw);
  if(raw === "" || !isFinite(n) || n < 0){
    if(typeof toast === "function") toast("Type a cost per unit, 0 or more.");
    return null;
  }
  return n;
}

/* The statement's account must still be the open one: a cost is saved against
 * one account, and SKUs repeat across accounts. */
function _pnlSameAccount(){
  const j = PNL.data || {};
  const open = (typeof acctId === "function") ? acctId() : "";
  if(!j.workspace || (open && open !== j.workspace)){
    if(typeof toast === "function") toast("The account changed — reopen the statement first.");
    return false;
  }
  return true;
}

async function pnlMissingSave(i){
  const m = ((PNL.ledgers.cogs || {}).missing || [])[i];
  const j = PNL.data || {};
  if(!m || m.has_sku === false || !_pnlSameAccount()) return;
  const cost = _pnlCostInput("pnl_mc_" + i);
  if(cost === null) return;
  const r = await cogsSet(m.sku, cost);
  if(!r.ok){ if(typeof toast === "function") toast("Could not save that cost: " + r.error); return; }
  // Put it on this window's orders that have NO cost yet -- never over an
  // order's own cost (order_cogs.freeze_range without force).
  let rf = null;
  try{
    rf = await (await fetch("/cogs/refreeze", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({account: j.workspace, marketplace: j.marketplace,
                            start: j.start, end: j.end})})).json();
  }catch(e){ rf = {ok: false, error: "could not reach the server"}; }
  if(typeof toast === "function"){
    // SAID, NOT HIDDEN: the product cost is saved either way, but only the
    // re-cost puts it on these orders.
    toast((rf && rf.ok)
      ? "Saved " + m.sku + " at " + cost + " a unit."
      : "Saved " + m.sku + "'s cost, but it could not be put on these orders ("
        + ((rf && rf.error) || "unknown") + "). Try again.");
  }
  pnlReload();
}

async function pnlMissingOrderSave(i, k){
  const m = ((PNL.ledgers.cogs || {}).missing || [])[i];
  const o = m && (m.orders || [])[k];
  const j = PNL.data || {};
  if(!o || !_pnlSameAccount()) return;
  const cost = _pnlCostInput("pnl_moc_" + i + "_" + k);
  if(cost === null) return;
  let r;
  try{ r = await ordPostOrderCost(o.order_id, m.sku, cost, j.workspace, j.marketplace); }
  catch(e){ r = {ok: false, error: String(e)}; }
  if(!r || !r.ok){
    if(typeof toast === "function") toast("Could not save that cost: " + ((r && r.error) || "unknown"));
    return;
  }
  if(typeof toast === "function") toast("Saved for order " + o.order_id + " only.");
  pnlReload();
}

