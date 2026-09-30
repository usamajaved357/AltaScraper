// ===================== FINANCE: CONTRIBUTION PER PRODUCT =====================
// What each product actually left behind, after Amazon's fees, refunds and what
// the stock cost.
//
// Two things on this screen are deliberately NOT numbers:
//   * Ad spend reads "not connected" rather than 0.00. Nothing writes to
//     ads_daily yet, and a zero would inflate every advertised product's
//     contribution by exactly what you are spending on it — convincingly.
//   * A product with uncosted units IS shown, flagged "N uncosted" -- its
//     figure counts that stock as free, so it is too high. The owner's rule:
//     "if no cogs are added show profit as wrong ... the user should know he
//     needs to add cogs". Only a product whose FEE is unknown shows nothing.
// Both are stated on screen rather than left for the reader to notice.

let FIN = {rows: [], totals: {}, sort: "revenue", desc: true,
           preset: "30d", filter: "all",
           // WHICH CALENDAR. See financeSetBasis.
           basis: "orders", overhead: null, previous: null, openOverhead: false};

// The window, as periods people actually ask for. The date boxes stayed EMPTY
// while the screen quietly showed the last thirty days, so the one thing a
// money screen must be unambiguous about -- which days it is counting -- was
// the one thing it never said. Picking a preset fills the boxes, and typing in
// the boxes clears the preset, so the two can never disagree.
// "LAST MONTH" AND "LAST 30 DAYS" ARE NOT THE SAME PERIOD, and the way to stop
// them being confused is to offer both by name rather than to pick one.
//
//     Ava, on its own most common way of being wrong:
//     "Mixing time grains ... User asks 'last month' and I answer with 30d
//      comparison if I don't label grain. Looks right, 9 days off."
//
// Nine days off, on a money screen, with nothing on the page saying which was
// used. "30 days" is plainly rolling; "Last month" is plainly a calendar month;
// with both present neither can be mistaken for the other.
const FIN_PRESETS = [
  {k: "7d",   t: "7 days",       days: 7},
  {k: "30d",  t: "30 days",      days: 30},
  {k: "90d",  t: "90 days",      days: 90},
  {k: "mtd",  t: "This month",   month: true},
  {k: "lastmonth", t: "Last month", lastMonth: true},
  {k: "qtd",  t: "This quarter", quarter: true},
];

const FIN_FILTERS = [
  {k: "all",    t: "All"},
  // The products that are actually costing something to sell. Asked for
  // directly, and the one cut this screen was missing: a product with no ad
  // spend cannot be losing money to advertising, so filtering to the ones that
  // do is how the question "is the advertising worth it" gets asked per product.
  {k: "ppc",    t: "Active PPC"},
  {k: "profit", t: "Profitable"},
  {k: "loss",   t: "Loss-making"},
  {k: "blank",  t: "No contribution"},
];

/* WHICH CALENDAR THE FIGURES ARE ON, and it is not a cosmetic switch.
 *
 *   orders      every order PLACED in the window, settled or not. Ties to what
 *               was sold. Fifteen products for August on nestwell_goods.
 *   settlement  money that has actually MOVED. Ties to the Amazon payout, and
 *               lags -- the SAME month returns ONE product, which reads as
 *               "nothing sold" unless the screen says why.
 *
 * Neither is the truer number. They answer different questions, and the screen
 * names the one it is showing rather than letting a lagging feed look like a
 * quiet month. */
function financeSetBasis(b){
  if(FIN.basis === b) return;
  FIN.basis = (b === "settlement") ? "settlement" : "orders";
  financeLoad();
}

function financeToggleOverhead(){
  FIN.openOverhead = !FIN.openOverhead;
  financeRender();
}

// THE LOCAL DAY, not UTC: toISOString moved "This month" to the last day of
// the previous month around UK midnight in summer time (Finance review, 30 Sep).
function _finIso(d){
  const m = d.getMonth() + 1, day = d.getDate();
  return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (day < 10 ? "0" : "") + day;
}

function financePreset(k){
  FIN.preset = k || "";
  if(k){
    const p = FIN_PRESETS.filter(x => x.k === k)[0];
    if(p){
      // ENDING YESTERDAY, as the Sales page does ("Amazon never has today"),
      // so "30 days" here is the same thirty days as there.
      const end = new Date(), start = new Date();
      end.setDate(end.getDate() - 1);
      start.setDate(start.getDate() - 1);
      if(p.month){ start.setDate(1); }
      else if(p.lastMonth){
        // The whole of the previous calendar month, first to last. Day 0 of
        // this month IS the last day of the previous one, which avoids having
        // to know how long February was.
        start.setDate(1);
        start.setMonth(start.getMonth() - 1);
        end.setDate(0);
      }
      else if(p.quarter){ start.setMonth(Math.floor(start.getMonth() / 3) * 3, 1); }
      else { start.setDate(start.getDate() - (p.days - 1)); }
      const a = document.getElementById("fin_start"), b = document.getElementById("fin_end");
      if(a) a.value = _finIso(start);
      if(b) b.value = _finIso(end);
    }
  }
  financeLoad();
}

function financeFilter(k){ FIN.filter = k; financeRender(); }

// Jump straight to the days this account actually has, instead of leaving
// someone to work out the dates from a sentence.
function financeShowAll(from, to){
  const a = document.getElementById("fin_start"), b = document.getElementById("fin_end");
  if(a) a.value = from;
  if(b) b.value = to;
  FIN.preset = "";
  financeLoad();
}

function _finChips(){
  const p = document.getElementById("fin_presets");
  if(p){
    p.innerHTML = FIN_PRESETS.map(function(x){
      return '<button class="db-chip'+(FIN.preset===x.k?" on":"")+'" '
           + 'onclick="financePreset('+jsArg(x.k)+')">'+_fesc(x.t)+'</button>';
    }).join("");
  }
  const f = document.getElementById("fin_filters");
  if(f){
    // Each filter carries its own count, so choosing one is never a guess about
    // whether it will show anything.
    f.innerHTML = FIN_FILTERS.map(function(x){
      const n = _finMatching(x.k).length;
      return '<button class="db-chip'+(FIN.filter===x.k?" on":"")+'"'
           + (n ? "" : ' style="opacity:.45"')
           + ' onclick="financeFilter('+jsArg(x.k)+')">'+_fesc(x.t)+' '+n+'</button>';
    }).join("");
  }
}

function _fesc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function _fmoney(v, cur){
  if(v===null || v===undefined || v==="") return '<span class="cc">—</span>';
  const n = Number(v);
  return (n<0 ? "−" : "") + (cur ? cur+" " : "") + Math.abs(n).toFixed(2);
}
function _fpct(v){
  return (v===null||v===undefined||v==="") ? '<span class="cc">—</span>'
                                           : Number(v).toFixed(1)+"%";
}

// Opens on the preset it was already silently using, with the dates FILLED IN
// rather than left blank for the reader to wonder about.
function financeOnOpen(){ financePreset(FIN.preset || "30d"); }

async function financeLoad(){
  const body = document.getElementById("finbody");
  if(!body) return;
  body.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> Loading…</div>';
  const qs = [];
  const s = (document.getElementById("fin_start")||{}).value;
  const e = (document.getElementById("fin_end")||{}).value;
  if(s && e){ qs.push("start="+encodeURIComponent(s), "end="+encodeURIComponent(e)); }
  // THIS PAGE SAYS WHOSE MONEY IT IS SHOWING.
  //
  // It used to send only the dates, so the server fell back to its own
  // process-wide active_account_id and active_marketplace -- one pair of
  // variables for the whole server, written whenever anybody chooses something.
  // Measured 21 Aug 2026: opening Sheelady (USA), whose marketplaces are MX,
  // CA, BR and US, this screen reported "No finance data has ever been pulled
  // for Sheelady (USA) on UK". Not a judgement call between several; a country
  // the account does not sell in, and then "no data" -- which reads as "you
  // have no sales" rather than "I looked in the wrong place".
  //
  // The page knows both. Every other money screen already says so; this is a
  // page of money that did not. See routes/scope.py.
  if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id){
    qs.push("account=" + encodeURIComponent(CUR_ACCOUNT.id));
  }
  if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__"){
    qs.push("marketplace=" + encodeURIComponent(WS_MARKET));
  }
  // Which calendar. Sent every time, so the reply cannot be about a different
  // basis from the one the toggle is showing.
  qs.push("basis=" + encodeURIComponent(FIN.basis || "orders"));
  let j;
  // ONLY THE NEWEST REQUEST, AND ONLY FOR THE ACCOUNT STILL ON SCREEN. There
  // was no guard at all: two preset clicks raced and the slower reply won, and
  // a reply landing after an account switch painted the old account's rows on
  // the new account's screen -- measured in the master audit (S5).
  const _seq = (FIN._seq = (FIN._seq || 0) + 1);
  const _sc = (typeof screenScope === "function") ? screenScope() : null;
  const _stale = () => _seq !== FIN._seq || (_sc && !screenStillIn(_sc));
  try{ j = await (await fetch("/finance/contribution"+(qs.length?"?"+qs.join("&"):""))).json(); }
  catch(err){ if(_stale()) return; body.innerHTML = uiError("Finance could not be loaded", String(err), "financeLoad", "finance"); return; }
  if(_stale()) return;
  if(!j || !j.ok){
    body.innerHTML = uiError("Finance could not be loaded", (j&&j.error)||"no reason given", "financeLoad", "finance");
    return;
  }
  FIN.rows = j.rows || [];
  FIN.totals = j.totals || {};
  // THE ACCOUNT'S PROFIT FOR THE SAME DAYS, every line (domain/pnl.build via
  // /sales/pnl -- the Sales card's own statement; pnl.js draws it).
  if(typeof pnlLoad === "function"){
    const pq = [];
    if(j.workspace) pq.push("account=" + encodeURIComponent(j.workspace));
    else if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
      pq.push("account=" + encodeURIComponent(CUR_ACCOUNT.id));
    if(j.marketplace) pq.push("marketplace=" + encodeURIComponent(j.marketplace));
    if(j.start && j.end) pq.push("start=" + encodeURIComponent(j.start), "end=" + encodeURIComponent(j.end));
    pnlLoad("fin_pnl", pq.join("&"));
  }
  FIN.overhead = j.overhead || null;
  FIN.previous = j.previous || null;
  // The server decides the basis (it validates it); the screen follows, so the
  // toggle can never claim one calendar while the figures are on the other.
  FIN.basis = j.basis || FIN.basis;
  FIN.meta = j;
  financeRender();
}

function financeSort(key){
  if(FIN.sort === key){ FIN.desc = !FIN.desc; } else { FIN.sort = key; FIN.desc = true; }
  financeRender();
}

// A product with NO contribution is its own answer, not a loss and not a
// profit. Lumping it in with either would be the quiet lie on this screen:
// "loss-making" would fill up with products whose cost simply is not known.
function _finMatching(f){
  return FIN.rows.filter(function(r){
    const c = r.contribution;
    if(f === "profit") return c !== null && c !== undefined && c > 0;
    if(f === "loss")   return c !== null && c !== undefined && c <= 0;
    if(f === "blank")  return c === null || c === undefined;
    // SPENDING SOMETHING, not merely having an ad_spend field. null means the
    // advertising is not connected for this product and 0 means it ran none --
    // neither is "actively advertised", and lumping them in would fill the
    // filter with products it cannot say anything about.
    if(f === "ppc") return (r.ad_spend !== null && r.ad_spend !== undefined
                            && r.ad_spend > 0);
    return true;
  });
}

// Children rolled into their parent. Money adds up; margin does NOT -- it is
// recomputed from the rolled-up parts, because averaging percentages weights a
// product that sold twice the same as one that sold two hundred times. And a
// parent containing ONE product whose contribution is unknown reports no
// contribution for the whole family, exactly as a single product does: a
// partial total only ever flatters.
// EVERY FIELD THIS SCREEN ADDS UP, named once.
//
// It was written out four times -- the rollup's starting object, the rollup's
// add loop, the totals' starting object and the totals' rounding loop -- and
// adding a column meant remembering all four. `promos` was the column that
// proved it: the server sends it, and a family rollup would have quietly
// dropped the discounts of every child while the single-product rows showed
// them.
//
// MONEY, not counts, is a separate list because only money gets rounded to
// pence at the end; rounding a unit count is meaningless and rounding it twice
// is how a count of 3 becomes 2.999999.
// net_revenue is summed because margin is worked out over it -- sales after
// VAT, the same denominator as every other profit screen.
const FIN_MONEY = ["revenue", "vat", "net_revenue", "fees", "cogs", "refunds",
                   "promos"];
const FIN_COUNTS = ["units", "uncosted_units"];
const FIN_SUM = FIN_MONEY.concat(FIN_COUNTS);

function _finRollup(rows){
  const out = {}, order = [];
  rows.forEach(function(r){
    const key = r.parent_asin || r.asin;
    if(!out[key]){
      out[key] = {asin: key, title: r.title || "", parent_asin: "", _n: 0,
                  ad_spend: null, contribution: 0,
                  _blank: false, _isGroup: false};
      FIN_SUM.forEach(function(k){ out[key][k] = 0; });
      order.push(key);
    }
    const g = out[key];
    g._n++;
    if(r.parent_asin) g._isGroup = true;
    FIN_SUM.forEach(function(k){ g[k] += Number(r[k] || 0); });
    if(r.ad_spend !== null && r.ad_spend !== undefined){
      g.ad_spend = Number(g.ad_spend || 0) + Number(r.ad_spend);
    }
    if(r.contribution === null || r.contribution === undefined) g._blank = true;
    else g.contribution += Number(r.contribution);
    if(!g.title && r.title) g.title = r.title;
  });
  return order.map(function(k){
    const g = out[k];
    if(g._blank) g.contribution = null;
    // Over sales AFTER VAT, as the server and every other screen do.
    g.margin_pct = (g.contribution !== null && g.net_revenue)
                 ? Number((g.contribution / g.net_revenue * 100).toFixed(2)) : null;
    if(g._isGroup) g.title = (g.title || "") + " (" + g._n + " children)";
    return g;
  });
}

function _finVisible(){
  let rows = _finMatching(FIN.filter);
  const box = document.getElementById("fin_by_parent");
  if(box && box.checked) rows = _finRollup(rows);
  return rows;
}

function _finSorted(){
  const k = FIN.sort, dir = FIN.desc ? -1 : 1;
  return _finVisible().slice().sort(function(a, b){
    let x = a[k], y = b[k];
    // Blanks sort to the bottom whichever way the column is pointing: a withheld
    // contribution is not "the smallest", it is "not known".
    if(x===null||x===undefined) return 1;
    if(y===null||y===undefined) return -1;
    if(typeof x === "string") return dir * (x < y ? 1 : x > y ? -1 : 0);
    return dir * (x - y);
  });
}

const FIN_COLS = [
  {k:"asin",         t:"Product",       kind:"text"},
  {k:"units",        t:"Units",         kind:"int",   tip:"Units SHIPPED — the same basis as the fees and refunds beside them"},
  {k:"revenue",      t:"Revenue",       kind:"money", tip:"Charged to buyers, from Amazon's finance records"},
  {k:"vat",          t:"VAT",           kind:"money", tip:"Collected from the buyer and owed onward — never yours"},
  {k:"ad_spend",     t:"Ad spend",      kind:"money", tip:"Not connected yet"},
  {k:"fees",         t:"Amazon fees",   kind:"money", tip:"Referral + FBA + other"},
  {k:"cogs",         t:"COGS",          kind:"money", tip:"What the units cost, from the cost written into each SKU"},
  {k:"refunds",      t:"Refunds",       kind:"money", tip:"Paid back to buyers. The referral fee Amazon returns with a refund is added back in the contribution, so a return is not charged a fee twice"},
  // COUPONS AND DEALS YOU FUNDED. Amazon reports these separately from the item
  // price -- the price it sends is the FULL one -- so a discount was invisible
  // on this screen and counted as money kept. Given a column of its own rather
  // than netted off Revenue, so "Revenue" still means what Amazon charged and
  // the discount can be seen for what it is.
  {k:"promos",       t:"Promotions",    kind:"money", tip:"Coupons and deals you funded. Amazon sends the full price separately from the discount, so this is money that never reached you"},
  {k:"contribution", t:"Contribution",  kind:"money", tip:"Revenue − VAT − fees − refunds − promotions + returned fees + reimbursements − COGS. Before advertising."},
  {k:"margin_pct",   t:"Margin",        kind:"pct"},
];

// Totals for whatever is on screen. NOT the server's whole-period totals: with
// a filter on, showing those under a filtered table invites reading the two as
// the same thing, and "Loss-making" with a healthy total underneath it is the
// most misleading arrangement this screen could produce. Contribution is
// withheld if ANY visible row withholds it -- the same rule one product follows.
function _finTotals(rows){
  const t = {products: rows.length, ad_spend: null, contribution: 0};
  FIN_SUM.forEach(function(k){ t[k] = 0; });
  let blank = false, anyAds = false;
  rows.forEach(function(r){
    FIN_SUM.forEach(function(k){ t[k] += Number(r[k] || 0); });
    if(r.ad_spend !== null && r.ad_spend !== undefined){
      anyAds = true; t.ad_spend = Number(t.ad_spend || 0) + Number(r.ad_spend);
    }
    if(r.contribution === null || r.contribution === undefined) blank = true;
    else t.contribution += Number(r.contribution);
  });
  if(!anyAds) t.ad_spend = null;
  if(blank) t.contribution = null;
  // Over sales AFTER VAT, as the server and every other screen do.
  t.margin_pct = (t.contribution !== null && t.net_revenue)
               ? Number((t.contribution / t.net_revenue * 100).toFixed(2)) : null;
  FIN_MONEY.forEach(function(k){ t[k] = Number(t[k].toFixed(2)); });
  if(t.contribution !== null) t.contribution = Number(t.contribution.toFixed(2));
  return t;
}

/* The order/settlement toggle, and the sentence that says what it changed.
 *
 * The two are not a display preference: on nestwell_goods for August, orders
 * shows fifteen products and settlement shows one, for the same month. A screen
 * that switches between them silently would look broken on one of the two. */
function financeBasisToggle(){
  const on = (FIN.basis === "settlement") ? "settlement" : "orders";
  const btn = function(k, label){
    return '<button class="db-chip' + (on === k ? " on" : "") + '" '
      + 'onclick="financeSetBasis(' + jsArg(k) + ')">' + label + '</button>';
  };
  const said = (on === "settlement")
    ? ("Money that has actually moved — this ties to your Amazon payouts. "
       + "Amazon settles days after a sale, so a recent window shows only the "
       + "part it has paid out, which is fewer products than actually sold.")
    : ("Every order placed in this window, whether Amazon has settled it or "
       + "not — this ties to what was sold. Fees are Amazon's own where it has "
       + "settled them and this account's measured rate where it has not.");
  const t = FIN.totals || {};
  let cover = "";
  if(on === "orders" && t.estimated_revenue !== undefined
     && t.revenue) {
    const est = Number(t.estimated_revenue || 0);
    const pct = t.revenue ? Math.round(100 * est / t.revenue) : 0;
    // NO RATE IS NOT A 0% RATE. With nothing settled to measure from, the
    // unsettled revenue carries no fee at all -- saying "charged at 0.00%"
    // read as though Amazon had charged nothing (Milestone 1 review).
    const unpriced = Number(t.unpriced_fee_revenue || 0);
    cover = " " + pct + "% of the revenue here has not settled yet, so ";
    if(t.fee_rate) {
      cover += "its fees are charged at "
             + (Number(t.fee_rate) * 100).toFixed(2) + "%";
      cover += unpriced > 0
        ? ", except where no rate could be measured — those carry no fee yet."
        : ".";
    } else {
      cover += "no fee rate could be measured for it yet — it carries no fee "
             + "until Amazon settles it.";
    }
  }
  return '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;'
    + 'margin:0 0 8px">'
    + '<span class="cc" style="font-size:11px;text-transform:uppercase;'
    +   'letter-spacing:.5px">Basis</span>'
    + btn("orders", "Order-based") + btn("settlement", "Settlement")
    // What the basis means is behind the (i); the share not yet settled stays
    // on the line as a number (owner, 30 Sep 2026: less text, more visual).
    + uiHint(said + cover)
    + (cover && t.revenue
       ? '<span class="cc" style="font-size:11.5px">'
         + Math.round(100 * Number(t.estimated_revenue || 0) / t.revenue)
         + '% not settled yet</span>' : '')
    + '</div>';
}

/* The gap between what the products contributed and what the account kept.
 *
 * Collapsed to one line, because most of the time the number is all anybody
 * wants; expanded it names what is in it. The eight Amazon fee types the spec
 * asks for are NOT in it, and it says so rather than inventing them -- the fee
 * type Amazon sends is not stored, only the bucket it falls into. A real
 * limitation with a real fix, and naming it is how it gets fixed. */
function financeOverhead(cur){
  const o = FIN.overhead;
  if(!o || (!o.items || !o.items.length)) return "";
  const money = function(v){
    return (v === null || v === undefined)
      ? '<span class="cc">not recorded</span>' : _fmoney(v, cur);
  };
  let h = '<div class="panelcard" style="padding:0;margin:0 0 12px;'
    + 'overflow:hidden">'
    + '<div style="display:flex;align-items:center;gap:10px;padding:11px 14px;'
    +   'cursor:pointer" onclick="financeToggleOverhead()">'
    + '<span class="cc" style="font-size:12px">'
    +   (FIN.openOverhead ? "▾" : "▸") + '</span>'
    + '<div style="flex:1"><div style="font-weight:600">Account-level '
    +   'overhead' + uiHint('The gap between what the products contributed and '
    +   'what the account kept') + '</div></div>'
    + '<div style="font-size:18px;font-weight:700">'
    +   _fmoney(o.total, cur) + '</div></div>';
  // A PART THAT COULD NOT BE READ, said on the panel whether it is open or
  // not: the net profit below is then too high (30 Sep 2026).
  (o.errors || []).forEach(function(e){
    h += '<div style="padding:0 14px 10px;color:var(--warn);font-size:12px">'
      + 'Net profit may be too high: ' + _fesc(e) + '.</div>';
  });

  if(FIN.openOverhead){
    h += '<div style="padding:0 14px 12px">';
    (o.items || []).forEach(function(it){
      h += '<div style="display:flex;justify-content:space-between;gap:12px;'
        +   'padding:7px 0;border-top:1px solid var(--line2)">'
        + '<div><div>' + _fesc(it.label) + '</div>'
        +   (it.note ? '<div class="cc" style="font-size:11px">'
                       + _fesc(it.note) + '</div>' : '')
        + '</div><div style="white-space:nowrap">' + money(it.amount)
        + '</div></div>';
      (it.children || []).forEach(function(ch){
        h += '<div style="display:flex;justify-content:space-between;gap:12px;'
          +   'padding:4px 0 4px 24px;font-size:12.5px;color:var(--ink2)">'
          + '<div>' + _fesc(ch.label) + '</div><div>'
          + _fmoney(ch.amount, cur) + '</div></div>';
      });
    });
    h += '<div style="display:flex;justify-content:space-between;gap:12px;'
      +   'padding:8px 0 0;margin-top:6px;border-top:1px solid var(--line2);'
      +   'font-weight:600"><div>Contribution (before overhead)</div><div>'
      +   money(o.contribution) + '</div></div>'
      + '<div style="display:flex;justify-content:space-between;gap:12px;'
      +   'padding:4px 0"><div>Less: account overhead</div>'
      +   '<div style="color:var(--red)">−' + _fmoney(o.total, cur)
      +   '</div></div>'
      + '<div style="display:flex;justify-content:space-between;gap:12px;'
      +   'padding:8px 0 0;border-top:1px solid var(--line2);font-weight:700;'
      +   'font-size:15px"><div>Net profit</div><div>'
      +   money(o.net_profit) + '</div></div>'
      + (o.why ? '<div class="cc" style="font-size:11px;margin-top:9px">'
                 + 'How this is worked out' + uiHint(o.why) + '</div>' : '')
      + '</div>';
  }
  return h + '</div>';
}

function financeRender(){
  const body = document.getElementById("finbody");
  _finChips();
  const visible = _finVisible();
  const t = _finTotals(visible), cur = (FIN.meta && FIN.meta.currency) || "";
  let h = "";

  h += financeBasisToggle();

  // Which days this screen is counting, said out loud. It defaulted to the last
  // thirty while the date boxes sat empty, so the number on screen belonged to a
  // period nobody had been told about.
  if(FIN.meta && FIN.meta.start){
    h += '<div class="cc" style="font-size:11.5px;margin:0 0 8px">'
      // WHOSE money, and in which country. This screen is per account and per
      // marketplace and said neither, so a figure could not be placed.
      +  (FIN.meta.account_label
          ? '<b>'+_fesc(FIN.meta.account_label)+'</b>'
            + (FIN.meta.marketplace ? ' · '+_fesc(FIN.meta.marketplace) : '')
            + ' — '
          : '')
      +  (FIN.basis === "settlement" ? 'money that moved between <b>' : 'orders placed between <b>')
      +  _fesc(FIN.meta.start)+'</b> and <b>'
      +  _fesc(FIN.meta.end)+'</b>'
      +  (FIN.filter !== "all"
          ? ' — showing <b>'+_fesc((FIN_FILTERS.filter(x=>x.k===FIN.filter)[0]||{}).t)
            +'</b> only · '+visible.length+' row'+(visible.length===1?'':'s')
            + uiHint('The totals below are for those '+visible.length
            +' row'+(visible.length===1?'':'s')+', not the whole period.')
          : '')
      +  '</div>';
  }

  // HOW LOUD EACH NOTE IS.
  //
  // They were all the same amber box, which put "1,578.54 GBP of revenue is NOT
  // in the list below" in the same styling as "ad spend is not connected yet".
  // The first means the screen is not answering the question; the second is a
  // limit on an answer that is otherwise right. Someone who has learned to skim
  // the amber boxes skims both.
  //
  //   bad   red     the figures on screen do not add up to the account
  //   warn  amber   right as far as they go, and here is the limit
  //   info  grey    how a figure was worked out
  //
  // The level comes from the server (domain/contribution.NOTE_*). A plain string
  // is still accepted and treated as a warning, so an older response renders.
  // The shared status colours (owner, 29 Sep 2026: hard-coded colours onto the
  // shared ones, so these notes follow the light theme too).
  const FIN_NOTE_STYLE = {
    bad:  {border: 'var(--as-danger-border)',  bg: 'var(--as-danger-bg)',  icon: 'ti-alert-triangle', fg: 'var(--as-danger)'},
    warn: {border: 'var(--as-warning-border)', bg: 'var(--as-warning-bg)', icon: 'ti-info-circle',    fg: ''},
    info: {border: 'var(--as-neutral-border)', bg: 'var(--as-neutral-bg)', icon: 'ti-info-circle',    fg: ''},
  };
  ((FIN.meta && FIN.meta.notes) || []).forEach(function(n){
    const text = (typeof n === 'string') ? n : (n && n.text) || '';
    if(!text) return;
    const lvl = (typeof n === 'string') ? 'warn' : ((n && n.level) || 'warn');
    const s = FIN_NOTE_STYLE[lvl] || FIN_NOTE_STYLE.warn;
    // THE FIRST SENTENCE ON THE LINE, THE REST BEHIND ITS (i) (owner, 30 Sep
    // 2026: less text, more visual). The colour and icon still carry how loud
    // it is; the whole note is in the hover, word for word.
    const cut = text.search(/[.!?](\s|$)/);
    const head = (cut > 0 && cut < text.length - 1) ? text.slice(0, cut + 1) : text;
    h += '<div class="cc" style="font-size:12px;margin:2px 0 10px;padding:7px 11px;'
      +  'border:1px solid '+s.border+';background:'+s.bg+';border-radius:6px'
      +  (s.fg ? ';color:'+s.fg : '')+'">'
      +  '<i class="ti '+s.icon+'"></i> '+_fesc(head)
      +  (head !== text ? uiHint(text) : '')+'</div>';
  });

  if(!FIN.rows.length){
    // The server says WHICH kind of empty this is: data outside the window,
    // data on another marketplace, or none ever pulled. One sentence for all
    // three was wrong for two of them.
    const why = (FIN.meta && FIN.meta.empty_note) || '';
    const have = (FIN.meta && FIN.meta.have) || {};
    h += '<div class="cc" style="padding:18px;border:1px dashed var(--line2);border-radius:6px;'
      +  'font-size:12.5px;line-height:1.6">'
      +  (why ? (function(){
               // First sentence on screen, the full reason behind the (i).
               const c = why.search(/[.!?](\s|$)/);
               return (c > 0 && c < why.length - 1)
                 ? _fesc(why.slice(0, c + 1)) + uiHint(why) : _fesc(why);
             })()
             : 'Nothing in this period yet. Finance data is pulled per day — press '
               + '<b>Sync</b> on the Sales screen and come back.');
    // A one-click way out of the commonest case, rather than a date box to work
    // out for yourself.
    if(have.first && have.last){
      h += '<div style="margin-top:10px">'
        +  '<button class="db-chip" onclick="financeShowAll('+jsArg(have.first)
        +  ','+jsArg(have.last)+')">Show me those '+have.rows+' days ('
        +  _fesc(have.first)+' → '+_fesc(have.last)+')</button></div>';
    }
    h += '</div>';
    body.innerHTML = h; return;
  }
  if(!visible.length){
    // The period HAS products; this filter has none. Two different facts, and
    // the empty-period wording above would have said the wrong one.
    h += '<div class="cc" style="padding:20px;border:1px dashed var(--line2);border-radius:6px">'
      +  'None of the '+FIN.rows.length+' products in this period are '
      +  _fesc(((FIN_FILTERS.filter(x=>x.k===FIN.filter)[0])||{}).t||"").toLowerCase()
      +  '. Pick <b>All</b> to see them.</div>';
    body.innerHTML = h; return;
  }

  // WHERE THESE FIGURES CAME FROM, before the figures.
  //
  // This screen is on the MONEY basis -- units shipped, dated when the money
  // moved -- and the Sales screen is on the ORDER basis. They describe the same
  // trade and they do not agree, which is correct and is the single most asked
  // question about either. Saying so here costs one line.
  if(typeof uiSource === "function" && FIN.meta){
    h += uiSource([
      {k: "Source", v: "Amazon Finances (listFinancialEvents)"},
      {k: "Basis", v: (FIN.basis === "settlement") ? "money moved — units shipped"
                                                    : "orders placed — the Sales page's calendar"},
      {k: "Account", v: FIN.meta.account_label},
      {k: "Marketplace", v: FIN.meta.marketplace},
      {k: "Dates", v: (FIN.meta.start && FIN.meta.end)
                      ? (FIN.meta.start + " → " + FIN.meta.end) : ""},
      {k: "Currency", v: cur},
    ], (FIN.basis === "settlement")
       ? "Settlement counts money as it moved, so it lags the Sales page's order calendar. Neither is wrong."
       : "The same calendar as the Sales page, so the account profit above matches its Profit card.");

    // A PERIOD THAT HAS NOT FINISHED IS NOT A PERIOD.
    //
    //     Ava: "This month: 2026-08-01 to 2026-08-19 - partial
    //           (month_is_partial=true). I always flag partial."
    //
    // Comparing a part-month against a whole one and reading the difference as
    // a fall is the easiest mistake on any money screen, and the window here
    // defaults to the last thirty days — which always includes today.
    const _today = new Date().toISOString().slice(0, 10);
    if(FIN.meta.end && FIN.meta.end >= _today){
      h += '<div class="cc" style="font-size:11.5px;margin:-6px 0 12px;'
        + 'padding:7px 10px;border:1px solid var(--warn-line);background:var(--warn-bg);'
        + 'border-radius:6px;max-width:760px">'
        + '<i class="ti ti-clock"></i> Includes <b>today</b> — still changing'
        + uiHint('This period includes today, which is not over. Amazon also '
        + 'posts fees and refunds for a day after it — so the last few days here '
        + 'will keep changing, and comparing them with a finished month '
        + 'reads as a fall that has not happened.') + '</div>';
    }
  }

  // WHAT THE PERIOD CAME TO, before the table.
  //
  // Every one of these was already computed by _finTotals and shown only in the
  // last ROW of a nine-column table, below the fold on a short screen. The one
  // number this page exists to give you -- what the products left behind -- was
  // the hardest thing on it to find.
  //
  // The totals are for what is VISIBLE, which is why the caption above says so
  // when a filter is on. Cards that quietly showed whole-period totals over a
  // filtered table would be the most misleading arrangement here.
  h += uiStats([
    {label: "Revenue", value: _fmoney(t.revenue, ""),
     note: t.units + " unit" + (t.units === 1 ? "" : "s") + " across "
           + t.products + " product" + (t.products === 1 ? "" : "s")},
    {label: "Fees + stock", value: _fmoney(t.fees + t.cogs, ""),
     note: "Amazon " + _fmoney(t.fees, "") + " · stock " + _fmoney(t.cogs, "")},
    // THE PRODUCTS' figure -- the account's is the statement above, which also
    // carries ads no product matched and the account's own charges.
    {label: "Products' contribution", value: _fmoney(t.contribution, ""),
     // Withheld, not zero, when a product's FEE is unknown. Uncosted stock is
     // shown and flagged instead -- the owner's rule -- so the card says the
     // figure is too high rather than hiding it.
     tone: (t.contribution === null || t.uncosted_units) ? "warn"
           : (t.contribution < 0 ? "bad" : "good"),
     note: (t.contribution === null)
           ? "withheld - Amazon's fee on a product could not be worked out"
           : (t.uncosted_units
              ? "TOO HIGH - " + t.uncosted_units + " unit"
                + (t.uncosted_units === 1 ? "" : "s") + " have no cost recorded"
              : "after fees, stock, refunds and promotions")},
    {label: "Margin", value: _fpct(t.margin_pct),
     tone: (t.margin_pct === null || t.margin_pct === undefined) ? ""
           : (t.margin_pct < 0 ? "bad" : (t.margin_pct < 10 ? "warn" : "good")),
     note: (t.ad_spend === null)
           ? ((FIN.basis === "settlement") ? "before advertising"
              : "ads are in Account profit above")
           : "after " + _fmoney(t.ad_spend, "") + " of ad spend"},
  ]);

  // The account-level overhead, between the cards and the table -- which is
  // where it belongs: it is the step from what the cards say the products
  // contributed to what the account actually kept.
  // THE OVERHEAD FOLD IS GONE FROM HERE: its three lines (account charges,
  // other Amazon postings, your own costs) and the net profit are the last
  // lines of the Account profit statement above, which also carries the ads
  // (30 Sep 2026). Two net profits on one screen was the review's first bug.

  h += '<div class="salespanel"><div class="panelhead"><div>'
    +  '<div class="paneltitle">Every product, and what it left behind'
    +  uiHint('Totals are recomputed from the parts, never summed '
    +  'from the column above — summing would quietly drop every product whose '
    +  'contribution is withheld and present the remainder as the whole.') + '</div>'
    +  '</div></div>';
  h += '<div style="overflow-x:auto"><table class="kv" style="width:100%;min-width:820px">'
    +  '<thead><tr>';
  FIN_COLS.forEach(function(c){
    const on = (FIN.sort === c.k);
    h += '<th style="text-align:'+(c.kind==="text"?"left":"right")+';font-size:11px;'
      +  'cursor:pointer;white-space:nowrap;padding:6px 8px"'
      +  (c.tip ? ' title="'+_fesc(c.tip)+'"' : '')
      +  ' onclick="financeSort('+jsArg(c.k)+')">'
      +  _fesc(c.t) + (on ? (FIN.desc ? " ▾" : " ▴") : "") + '</th>';
  });
  h += '</tr></thead><tbody>';

  _finSorted().forEach(function(r){
    h += '<tr>';
    FIN_COLS.forEach(function(c){
      const v = r[c.k];
      let cell;
      if(c.kind === "text"){
        // The product, not just its code. An ASIN alone is unreadable, and a
        // table of unreadable identifiers is one nobody checks.
        cell = r.title
          ? '<div style="max-width:290px"><div style="font-size:11.5px;'
            + 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'
            + _fesc(r.title)+'">'+_fesc(r.title)+'</div>'
            + '<code class="cc" style="font-size:10px">'+_fesc(v)+'</code></div>'
          : '<code style="font-size:11.5px">'+_fesc(v)+'</code>';
        if(r.uncosted_units){
          cell += '<span class="cc" style="font-size:10px;color:var(--warn);margin-left:6px" '
                + 'title="These units have no cost recorded, so nothing was subtracted '
                + 'for them and this product\'s contribution is HIGHER than the truth. '
                + 'Set a cost, then press Sync.">'
                + r.uncosted_units+' uncosted</span>';
        }
      } else if(c.kind === "int"){
        cell = (v===null||v===undefined) ? '<span class="cc">—</span>' : String(v);
      } else if(c.kind === "pct"){
        cell = _fpct(v);
      } else {
        cell = _fmoney(v, "");
        if(c.k === "ad_spend" && (v===null||v===undefined)){
          cell = '<span class="cc" title="No ad spend matched to this product. The account\'s whole ad cost is in Account profit above.">—</span>';
        }
      }
      const strong = (c.k === "contribution") ? "font-weight:600;" : "";
      h += '<td style="text-align:'+(c.kind==="text"?"left":"right")+';'+strong
        +  'white-space:nowrap;padding:5px 8px">'+cell+'</td>';
    });
    h += '</tr>';
  });

  h += '</tbody><tfoot><tr style="border-top:2px solid var(--line2);font-weight:600">';
  FIN_COLS.forEach(function(c){
    let cell;
    if(c.kind === "text") cell = t.products + " product" + (t.products===1?"":"s");
    else if(c.kind === "int") cell = String(t[c.k] || 0);
    else if(c.kind === "pct") cell = _fpct(t[c.k]);
    else if(c.k === "ad_spend" && t.ad_spend===null) cell = '<span class="cc">—</span>';
    else cell = _fmoney(t[c.k], "");
    h += '<td style="text-align:'+(c.kind==="text"?"left":"right")+';padding:7px 8px">'
      +  cell+'</td>';
  });
  h += '</tr></tfoot></table></div></div>';

  if(cur){
    h += '<div class="cc" style="font-size:11px;margin-top:10px">'
      +  'Amounts in '+_fesc(cur)+'.</div>';
  }

  body.innerHTML = h;
}
