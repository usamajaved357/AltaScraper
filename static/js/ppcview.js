/* ============ PPC ANALYTICS ============
 *
 *   "dive a detailed harvest of ppc feature in orbit and then develope same
 *    feature in my app"
 *
 * Orbit's advertising screens, rebuilt on a report that can be downloaded from
 * Seller Central today. The harvest is in orbit_ppc_complete.md; the arithmetic
 * is all in domain/ppc_view.py and none of it happens here.
 *
 * WHY NOT THE ADVERTISING API. It is a separate OAuth from SP-API -- its own
 * client id, secret, refresh token and profile id -- and it is connected on
 * none of the six accounts (measured 18 Aug 2026: ads_daily 0 rows,
 * ppc_campaigns 0 rows, no credentials anywhere). Waiting for it would mean
 * shipping empty screens. The SP Search Term Report carries everything except
 * the intraday view, and domain/ppc_module.py has always been able to read one.
 *
 * NOTHING HERE WRITES. No bid, no budget, no negation. CLAUDE.md Rule 8, and
 * Orbit's own words for the same rule: "approval gates, reversible actions, and
 * an audit trail before changes reach Amazon."
 *
 * It reuses the stock cockpit's card classes (.stk-) on purpose: one design
 * language across the app, and adding a card style for every screen is how two
 * card designs happened on the Listings page.
 */

let PPCV = {data: null, loading: false, filter: "", q: "", sort: "spend",
            dir: 1};

function _pvEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function _pvSym(){
  try{ return (typeof CUR_SYMBOL !== "undefined" && CUR_SYMBOL) || ""; }
  catch(e){ return ""; }
}
/* Every derived metric can legitimately be null -- a term with no clicks has no
 * CTR, not a CTR of zero. Printing 0% would invite acting on a number nobody
 * measured, which is the same rule the cost and velocity code follows. */
function _pvN(v, suffix, nd){
  if(v === null || v === undefined) return '<span class="cc">—</span>';
  return Number(v).toFixed(nd === undefined ? 1 : nd) + (suffix || "");
}
function _pvMoney(v){
  if(v === null || v === undefined) return '<span class="cc">—</span>';
  return _pvSym() + Number(v).toLocaleString(undefined,
    {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function _pvShort(v){
  if(v === null || v === undefined) return "—";
  const n = Number(v);
  if(Math.abs(n) >= 10000) return _pvSym() + (n / 1000).toFixed(1) + "K";
  return _pvSym() + n.toLocaleString(undefined, {maximumFractionDigits: 0});
}

function ppcAnalyticsOnOpen(){ if(!PPCV.data) ppcAnalyticsLoad(); }

async function ppcAnalyticsLoad(force){
  const host = document.getElementById("ppcwrap");
  if(!host || PPCV.loading) return;
  PPCV.loading = true;
  if(force || !PPCV.data){
    host.innerHTML = '<div class="stk-grid">'
      + '<div class="stk-card"><div class="stk-skel" style="height:12px;width:60%"></div>'
      + '<div class="stk-skel" style="height:24px;width:45%"></div></div>'.repeat(1)
      + '</div>';
  }
  let j = null;
  try{
    const qs = [];
    try{
      if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
        qs.push("id=" + encodeURIComponent(CUR_ACCOUNT.id));
      if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
        qs.push("marketplace=" + encodeURIComponent(WS_MARKET));
    }catch(e){}
    j = await (await fetch("/ppc/analytics"
      + (qs.length ? "?" + qs.join("&") : ""))).json();
  }catch(e){
    host.innerHTML = '<div class="odp-note warn" style="padding:14px">'
      + _pvEsc(String(e)) + '</div>';
    PPCV.loading = false; return;
  }
  PPCV.loading = false;
  if(!j || !j.ok){
    host.innerHTML = '<div class="odp-note warn" style="padding:14px">'
      + _pvEsc((j && j.error) || "Could not load") + '</div>';
    return;
  }
  PPCV.data = j;
  ppcAnalyticsRender();
}

function ppcAnalyticsRender(){
  const host = document.getElementById("ppcwrap");
  const j = PPCV.data;
  if(!host || !j) return;

  /* NO REPORT IS A SETUP STEP, NOT A RESULT. A screen of 0.00 would read as
   * "your advertising made nothing", which is a different and much worse
   * statement than "nothing has been uploaded yet". */
  if(!j.report){
    host.innerHTML =
        '<div class="stk-banner"><div class="stk-bannermain">'
      + '<div class="stk-eyebrow">PPC analytics</div>'
      + '<h3 class="stk-headline">No report loaded yet</h3>'
      + '<p class="stk-sub">' + _pvEsc(j.note || "") + '</p>'
      + '<p class="stk-sub" style="margin-top:10px">'
      + '<label class="db-chip" for="ppc_report_file" style="cursor:pointer">'
      + '<i class="ti ti-table-import"></i> Upload the report</label></p>'
      + '</div></div>';
    return;
  }

  host.innerHTML = _pvBanner(j) + _pvCards(j) + _pvBrand(j)
                 + _pvMatchTable(j) + _pvCampaignTable(j)
                 + _pvFilters(j) + _pvTermTable(j) + _pvFooter(j);
}

/* THE BANNER. Orbit leads /ppc with the spend and the efficiency; the one thing
 * worth leading with here is the money that bought nothing, because it is the
 * only figure on the page that names an action. */
function _pvBanner(j){
  const t = j.totals || {};
  const waste = t.wasted_spend || 0;
  let head, cls;
  if(waste > 0){
    head = _pvShort(waste) + " bought nothing";
    cls = "bad";
  }else if(t.spend){
    head = "Every search term that spent, sold";
    cls = "ok";
  }else{
    head = "No spend in this report";
    cls = "";
  }
  const r = j.report || {};
  return '<div class="stk-banner"><div class="stk-bannermain">'
    + '<div class="stk-eyebrow">PPC analytics</div>'
    + '<h3 class="stk-headline ' + cls + '">' + _pvEsc(head) + '</h3>'
    + '<p class="stk-sub">'
    + (waste > 0
        ? '<b>' + (t.wasted_terms || 0) + '</b> search term'
          + ((t.wasted_terms === 1) ? '' : 's')
          + ' took ' + _pvMoney(waste) + ' — that is '
          + _pvN(t.wasted_pct, "%") + ' of the spend — and returned no orders. '
          + 'Only terms with at least ' + (t.min_clicks_to_judge || 10)
          + ' clicks are counted, so a term that has barely run is not blamed.'
        : 'Every term with enough clicks to judge has produced at least one '
          + 'order.')
    + '</p>'
    + (t.tacos_note
        ? '<p class="stk-sub" style="margin-top:8px;color:var(--warn)">'
          + '<i class="ti ti-alert-triangle"></i> ' + _pvEsc(t.tacos_note)
          + '</p>' : '')
    + '<p class="stk-sub" style="margin-top:6px;opacity:.75">'
    + 'From your Search Term Report'
    + (r.date_from ? ', ' + _pvEsc(r.date_from) + ' to ' + _pvEsc(r.date_to) : '')
    + ' · ' + (r.rows || 0) + ' rows · uploaded ' + _pvEsc(r.uploaded_at || "")
    + '</p></div>'
    + '<div class="stk-bannercards">'
    +   _pvCard("risk", "Wasted spend", _pvShort(t.wasted_spend),
               (t.wasted_terms || 0) + " terms, no orders",
               "Spend on search terms that produced no orders in this report. "
             + "Orbit's own metric and the best thing on its screen: it turns "
             + "an ACOS into a number you can stop spending. Only terms with "
             + (t.min_clicks_to_judge || 10) + " or more clicks count — below "
             + "that a zero-order term is evidence of nothing.", "wasted_spend")
    +   _pvCard("cost", "Ad spend", _pvShort(t.spend),
               _pvN(t.acos, "%") + " ACOS · " + _pvN(t.roas, "x", 2) + " ROAS",
               "ACOS is spend divided by the sales the ads made — whether the "
             + "advertising pays for itself. ROAS is the same thing the other "
             + "way up.", "spend")
    +   _pvCard(t.tacos === null ? "info" : "good", "TACOS",
               t.tacos === null ? "—" : _pvN(t.tacos, "%"),
               // A contradiction gets said out loud rather than shown as a
               // number. See tacos_note in domain/ppc_view.totals.
               t.tacos_note ? "figures disagree — see the note"
                 : (t.tacos === null ? "needs the report's dates"
                    : "of " + _pvShort(t.total_sales) + " total sales"),
               t.tacos_note
                 || ("What advertising costs the BUSINESS: spend over ALL "
                   + "sales, ad and organic together. A brand can have a "
                   + "healthy ACOS and a TACOS that is eating it, and only the "
                   + "second answers whether you should be spending this at "
                   + "all. Total sales come from your orders, not from the ad "
                   + "report."))
    + '</div></div>';
}

function _pvCard(kind, label, value, sub, help, metric){
  return '<div class="stk-card ' + kind + '"'
    + (help ? ' title="' + _pvEsc(help) + '"' : '') + '>'
    + '<span class="lbl">' + _pvEsc(label)
    + (help ? ' <i class="ti ti-info-circle" style="opacity:.5"></i>' : '')
    + '</span><span class="val">' + value + _pvChange(metric) + '</span>'
    + '<span class="sub">' + sub + '</span></div>';
}

/* PERIOD-OVER-PERIOD, under every headline figure. Orbit shows one and it is
 * most of what makes the number useful: 19% ACOS means nothing until you know
 * last month's was 14%.
 *
 * BETTER AND WORSE, NOT UP AND DOWN. For ACOS, CPC, CPA and wasted spend, down
 * is the good direction — a green arrow pointing up would read backwards on
 * half the row. The server decides which, because it is the same judgement the
 * arithmetic makes.
 */
function _pvChange(metric){
  const j = PPCV.data, c = j && j.change && metric ? j.change[metric] : null;
  if(!c || c.change_pct === 0) return "";
  const good = c.direction === "better";
  const arrow = c.change_pct > 0 ? "▲" : "▼";
  const prev = j.compared_with || {};
  return '<span style="font-size:12px;font-weight:600;margin-left:7px;color:'
    + (good ? "var(--ok)" : "#f87171") + '" title="'
    + _pvEsc("Was " + c.before + " in the previous report"
             + (prev.date_to ? " (to " + prev.date_to + ")" : "") + ". "
             + (good ? "This is the better direction for this metric."
                     : "This is the worse direction for this metric.")) + '">'
    + arrow + Math.abs(c.change_pct).toFixed(0) + '%</span>';
}

function _pvCards(j){
  const t = j.totals || {};
  return '<div class="stk-grid">'
    + _pvCard("good", "Ad sales", _pvShort(t.sales),
             (t.orders || 0) + " orders",
             "Sales Amazon attributed to these ads in the report window.",
             "sales")
    + _pvCard("info", "Clicks", (t.clicks || 0).toLocaleString(),
             _pvN(t.ctr, "%") + " CTR · " + _pvMoney(t.cpc) + " CPC",
             "CTR is clicks over impressions — whether the ad is worth "
           + "clicking. CPC is what each click cost.", "clicks")
    + _pvCard("info", "Conversion", _pvN(t.cvr, "%"),
             _pvMoney(t.cpa) + " per order",
             "CVR is orders over clicks — whether the LISTING converts the "
           + "traffic the ad bought. CPA is cost per ACQUISITION, not per "
           + "click: a term with a cheap CPC and a terrible CPA is the "
           + "expensive kind of cheap.", "cvr")
    + _pvCard("cost", "Search terms", (t.terms || 0).toLocaleString(),
             (t.rows || 0) + " report rows",
             "One row per term. The report has a row per targeting that "
           + "triggered a term, so there are more rows than terms.")
    + '</div>';
}

/* BRANDED VS NON-BRANDED -- the most transferable idea on Orbit's page.
 * Amazon does not report this split; the seller says which words are theirs. */
function _pvBrand(j){
  const b = j.branded;
  const terms = j.brand_terms || [];
  let h = '<div class="card" style="padding:12px 14px;margin-bottom:12px">'
    + '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;'
    + 'margin-bottom:' + (b ? '10px' : '0') + '">'
    + '<b style="font-size:12.5px">Branded vs non-branded</b>'
    + '<span class="infodot" title="Amazon does not report this. You say which '
    + 'words are your brand, and every search term containing one is counted as '
    + 'branded. It matters because paying to appear on your own name is '
    + 'defensive — mixing it in makes a healthy-looking ACOS out of money that '
    + 'never won a new customer.">i</span>'
    + '<span style="flex:1"></span>';
  terms.forEach(function(t){
    h += '<span class="odp-id" style="cursor:pointer" title="Remove"'
      + ' onclick="ppcBrandTerm(null,' + jsArg(t) + ')">' + _pvEsc(t)
      + ' ×</span>';
  });
  h += '<input class="ed" id="ppc_brand_in" placeholder="Add brand term…" '
    + 'style="width:170px;padding:4px 9px;font-size:12px" '
    + 'onkeydown="if(event.key===\'Enter\'){ppcBrandTerm(this.value,null);'
    + 'this.value=\'\';}">'
    + '</div>';
  if(!b){
    h += '<div class="cc" style="font-size:11.5px">Add your brand name above '
      + 'and this splits in two. Until then nothing is assumed — reporting '
      + '“0% branded” would be a claim nobody made.</div>';
  }else{
    h += '<table class="stk-table"><thead><tr><th></th>'
      + '<th class="r">Spend</th><th class="r">Sales</th><th class="r">ACOS</th>'
      + '<th class="r">Orders</th><th class="r">CVR</th>'
      + '<th class="r">Wasted</th></tr></thead><tbody>';
    [["Branded", b.branded], ["Non-branded", b.non_branded]].forEach(function(p){
      const v = p[1] || {};
      h += '<tr><td><b>' + p[0] + '</b></td>'
        + '<td class="r stk-num">' + _pvMoney(v.spend) + '</td>'
        + '<td class="r stk-num">' + _pvMoney(v.sales) + '</td>'
        + '<td class="r stk-num">' + _pvN(v.acos, "%") + '</td>'
        + '<td class="r stk-num">' + (v.orders || 0) + '</td>'
        + '<td class="r stk-num">' + _pvN(v.cvr, "%") + '</td>'
        + '<td class="r stk-num">' + _pvMoney(v.wasted_spend) + '</td></tr>';
    });
    h += '</tbody></table>';
  }
  return h + '</div>';
}

async function ppcBrandTerm(add, remove){
  const body = {};
  if(add) body.add = [add];
  if(remove) body.remove = [remove];
  // WHICH ACCOUNT. Without this the server falls back to whichever workspace it
  // last had open, and a brand term added here lands on a different account --
  // the save says "saved" and the split never appears.
  try{
    if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
      body.id = CUR_ACCOUNT.id;
    if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
      body.marketplace = WS_MARKET;
  }catch(e){}
  try{
    const j = await (await fetch("/ppc/brand_terms", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)})).json();
    if(!j || !j.ok){ toast((j && j.error) || "Could not save that"); return; }
    ppcAnalyticsLoad(false);
  }catch(e){ toast(String(e)); }
}

/* MATCH TYPE, with % of spend against % of profit -- Orbit's own pair of
 * columns and the most useful thing on its campaign page. A bucket taking 40%
 * of the spend and returning 12% of the profit is visible without arithmetic. */
function _pvMatchTable(j){
  const rows = j.match_types || [];
  if(!rows.length) return "";
  let h = '<div class="card" style="padding:0;overflow:hidden;margin-bottom:12px">'
    + '<div style="padding:10px 14px;border-bottom:1px solid var(--line)">'
    + '<b style="font-size:12.5px">Where the money goes, by match type</b>'
    + '<span class="infodot" title="Broad discovers, exact converts. The two '
    + 'right-hand columns are the point: a match type taking 40% of the spend '
    + 'and returning 12% of the profit is the one to look at.">i</span></div>'
    + '<table class="stk-table"><thead><tr>'
    + '<th>Match type</th><th class="r">Spend</th><th class="r">% of spend</th>'
    + '<th class="r">Sales</th><th class="r">Profit</th>'
    + '<th class="r">% of profit</th><th class="r">ACOS</th>'
    + '<th class="r">CPC</th><th class="r">CVR</th></tr></thead><tbody>';
  rows.forEach(function(r){
    // A share of spend far above its share of profit is the thing worth seeing,
    // so it is coloured rather than left as two numbers to compare by eye.
    const over = (r.pct_profit !== null && r.pct_spend !== null
                  && r.pct_spend - r.pct_profit > 15);
    h += '<tr><td><b>' + _pvEsc(r.match_type) + '</b></td>'
      + '<td class="r stk-num">' + _pvMoney(r.spend) + '</td>'
      + '<td class="r stk-num"' + (over ? ' style="color:var(--red)"' : '') + '>'
      + _pvN(r.pct_spend, "%") + '</td>'
      + '<td class="r stk-num">' + _pvMoney(r.sales) + '</td>'
      + '<td class="r stk-num"' + (r.profit < 0 ? ' style="color:var(--red)"' : '')
      + '>' + _pvMoney(r.profit) + '</td>'
      + '<td class="r stk-num">' + _pvN(r.pct_profit, "%") + '</td>'
      + '<td class="r stk-num">' + _pvN(r.acos, "%") + '</td>'
      + '<td class="r stk-num">' + _pvMoney(r.cpc) + '</td>'
      + '<td class="r stk-num">' + _pvN(r.cvr, "%") + '</td></tr>';
  });
  return h + '</tbody></table></div>';
}

function _pvFilters(j){
  const t = j.terms || [];
  const n = function(k){ return t.filter(function(x){
    return k === "" ? true : (k === "branded" ? x.branded === true
         : k === "nonbranded" ? x.branded === false : x.opportunity === k);
  }).length; };
  const btn = function(k, label){
    return '<button class="stk-fbtn' + (PPCV.filter === k ? " on" : "") + '" '
      + 'onclick="ppcFilter(' + jsArg(k) + ')">' + _pvEsc(label)
      + '<span class="n">' + n(k) + '</span></button>';
  };
  return '<div class="stk-filters">'
    + btn("", "All terms")
    + btn("wasting", "Wasting")
    + btn("losing", "Losing money")
    + btn("scaling", "Worth scaling")
    + (j.brand_terms && j.brand_terms.length
        ? btn("branded", "Branded") + btn("nonbranded", "Non-branded") : "")
    + '<span style="flex:1"></span>'
    + '<a class="stk-fbtn" href="/ppc/analytics.csv' + _pvScopeQs()
    + '" style="text-decoration:none" title="Every search term in the report, '
    + 'not just the ones on screen — an export that silently truncates is '
    + 'worse than none.">Export</a>'
    + '<input class="ed" placeholder="Search terms…" value="' + _pvEsc(PPCV.q)
    + '" oninput="ppcSearch(this.value)" '
    + 'style="width:210px;padding:5px 10px;font-size:12px"></div>';
}

function ppcFilter(k){ PPCV.filter = k; ppcAnalyticsRender(); }
function ppcSearch(v){
  PPCV.q = v || "";
  const el = document.getElementById("ppc_terms");
  if(el) el.outerHTML = _pvTermTable(PPCV.data);
}
function ppcSort(col){
  if(PPCV.sort === col) PPCV.dir = -PPCV.dir; else { PPCV.sort = col; PPCV.dir = 1; }
  const el = document.getElementById("ppc_terms");
  if(el) el.outerHTML = _pvTermTable(PPCV.data);
}

const _PV_OPP = {
  "wasting": ["out", "wasting"],
  "losing":  ["now", "losing money"],
  "scaling": ["safe", "worth scaling"],
};

function _pvTermTable(j){
  let rows = (j.terms || []).slice();
  const f = PPCV.filter, q = (PPCV.q || "").trim().toLowerCase();
  if(f === "branded") rows = rows.filter(function(r){ return r.branded === true; });
  else if(f === "nonbranded") rows = rows.filter(function(r){ return r.branded === false; });
  else if(f) rows = rows.filter(function(r){ return r.opportunity === f; });
  if(q) rows = rows.filter(function(r){
    return String(r.search_term).toLowerCase().indexOf(q) >= 0; });

  const key = PPCV.sort, dir = PPCV.dir;
  rows.sort(function(a, b){
    let x = a[key], y = b[key];
    if(key === "search_term"){
      x = String(x).toLowerCase(); y = String(y).toLowerCase();
    }else{
      // A missing ratio sorts LAST either way: no ACOS is not the best ACOS.
      if(x === null || x === undefined) return 1;
      if(y === null || y === undefined) return -1;
    }
    return x < y ? -dir : x > y ? dir : 0;
  });

  const head = function(col, label, cls){
    return '<th class="' + (cls || "") + '" onclick="ppcSort(' + jsArg(col) + ')">'
      + _pvEsc(label) + (PPCV.sort === col
        ? '<span class="dir">' + (PPCV.dir > 0 ? "▲" : "▼") + '</span>' : '')
      + '</th>';
  };
  let h = '<div id="ppc_terms" class="card" style="padding:0;overflow:hidden">'
    + '<table class="stk-table"><thead><tr>'
    + '<th title="What this term has actually done. It never says what to do — '
    + 'applying a negation or a bid is a decision with money attached.">Opp</th>'
    + head("search_term", "Search term")
    + head("clicks", "Clicks", "r") + head("ctr", "CTR", "r")
    + head("cpc", "CPC", "r") + head("cpa", "CPA", "r")
    + head("spend", "Spend", "r") + head("sales", "Sales", "r")
    + head("acos", "ACOS", "r") + head("profit", "Profit", "r")
    + '</tr></thead><tbody>';
  if(!rows.length){
    h += '<tr><td colspan="10" class="cc" style="padding:20px;text-align:center">'
      + 'Nothing matches that.</td></tr>';
  }
  rows.slice(0, 300).forEach(function(r){
    const o = _PV_OPP[r.opportunity];
    h += '<tr><td>'
      + (o ? '<span class="stk-chip ' + o[0] + '" title="' + _pvEsc(r.why) + '">'
             + o[1] + '</span>'
           : (r.why ? '<span class="cc" style="font-size:10px" title="'
                      + _pvEsc(r.why) + '">—</span>' : ''))
      + '</td>'
      + '<td><div class="stk-pname"><b title="' + _pvEsc(r.search_term) + '">'
      + _pvEsc(r.search_term) + '</b><span>'
      + _pvEsc((r.match_types || []).join(", "))
      + (r.branded === true ? ' · branded' : '') + '</span></div></td>'
      + '<td class="r stk-num">' + (r.clicks || 0) + '</td>'
      + '<td class="r stk-num">' + _pvN(r.ctr, "%") + '</td>'
      + '<td class="r stk-num">' + _pvMoney(r.cpc) + '</td>'
      + '<td class="r stk-num">' + _pvMoney(r.cpa) + '</td>'
      + '<td class="r stk-num">' + _pvMoney(r.spend) + '</td>'
      + '<td class="r stk-num">' + _pvMoney(r.sales) + '</td>'
      + '<td class="r stk-num">' + _pvN(r.acos, "%") + '</td>'
      + '<td class="r stk-num"' + (r.profit < 0 ? ' style="color:var(--red)"' : '')
      + '>' + _pvMoney(r.profit) + '</td></tr>';
  });
  if(rows.length > 300){
    h += '<tr><td colspan="10" class="cc" style="padding:10px;text-align:center">'
      + 'Showing the 300 biggest spenders of ' + rows.length
      + '. Narrow it with the search box.</td></tr>';
  }
  return h + '</tbody></table></div>';
}

function _pvFooter(j){
  return '<div class="odp-note" style="margin-top:10px">'
    + 'Every figure comes from the Search Term Report you uploaded. Nothing on '
    + 'this page changes a bid, a budget or a campaign — to act on a term, use '
    + 'the harvester below, which writes a bulk file for you to review and '
    + 'upload yourself.</div>';
}

async function ppcReportUpload(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  const fd = new FormData();
  fd.append("file", f);
  try{
    if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
      fd.append("id", CUR_ACCOUNT.id);
    if(typeof WS_MARKET !== "undefined" && WS_MARKET) fd.append("marketplace", WS_MARKET);
  }catch(e){}
  toast("Reading " + f.name + "…");
  try{
    const j = await (await fetch("/ppc/report/upload",
                                 {method: "POST", body: fd})).json();
    input.value = "";
    if(!j || !j.ok){ toast((j && j.error) || "Could not read that report"); return; }
    toast(j.note || ("Kept " + j.rows + " rows"));
    ppcAnalyticsLoad(true);
  }catch(e){ toast(String(e)); input.value = ""; }
}


/* The account and marketplace as a query string, for links (the CSV export)
   that cannot post a body. */
// Byte-for-byte identical to stock.js's copy before this. One builder now
// (CLAUDE.md Rule 12) -- static/js/scopeq.js.
function _pvScopeQs(){ return (typeof scopeQs === "function") ? scopeQs() : ""; }

/* CAMPAIGN ANALYTICS. Orbit gives this its own route; the Search Term Report
 * carries the campaign and ad group names, so the table that matters can be
 * built without the Advertising API.
 *
 * What it CANNOT show, and does not pretend to: SP / SB / SD (the report is
 * Sponsored Products only) and Enabled / Paused (status is not in the file).
 */
function _pvCampaignTable(j){
  const use = j.campaigns || [];
  // One campaign is not a breakdown, and a report with no campaign column at
  // all collapses to a single "(no campaign named)" row -- drawing a table of
  // one row that repeats the headline is noise.
  if(use.length < 2) return "";
  let h = '<div class="card" style="padding:0;overflow:hidden;margin-bottom:12px">'
    + '<div style="padding:10px 14px;border-bottom:1px solid var(--line)">'
    + '<b style="font-size:12.5px">Campaigns</b>'
    + '<span class="infodot" title="From the campaign names in your report. It '
    + 'cannot show SP / SB / SD or Enabled / Paused — the Search Term Report is '
    + 'Sponsored Products only and carries no campaign status. Connecting the '
    + 'Advertising API would add both.">i</span></div>'
    + '<table class="stk-table"><thead><tr>'
    + '<th>Campaign</th><th class="r">Terms</th><th class="r">Spend</th>'
    + '<th class="r">% of spend</th><th class="r">Sales</th>'
    + '<th class="r">Profit</th><th class="r">% of profit</th>'
    + '<th class="r">ACOS</th><th class="r">CPC</th></tr></thead><tbody>';
  use.forEach(function(r){
    const over = (r.pct_profit !== null && r.pct_spend !== null
                  && r.pct_spend - r.pct_profit > 15);
    h += '<tr><td><div class="stk-pname"><b title="' + _pvEsc(r.campaign) + '">'
      + _pvEsc(r.campaign) + '</b><span>'
      + _pvEsc((r.ad_groups || []).slice(0, 3).join(", "))
      + ((r.ad_groups || []).length > 3 ? " +" + (r.ad_groups.length - 3) : "")
      + '</span></div></td>'
      + '<td class="r stk-num">' + (r.terms || 0) + '</td>'
      + '<td class="r stk-num">' + _pvMoney(r.spend) + '</td>'
      + '<td class="r stk-num"' + (over ? ' style="color:var(--red)"' : '') + '>'
      + _pvN(r.pct_spend, "%") + '</td>'
      + '<td class="r stk-num">' + _pvMoney(r.sales) + '</td>'
      + '<td class="r stk-num"' + (r.profit < 0 ? ' style="color:var(--red)"' : '')
      + '>' + _pvMoney(r.profit) + '</td>'
      + '<td class="r stk-num">' + _pvN(r.pct_profit, "%") + '</td>'
      + '<td class="r stk-num">' + _pvN(r.acos, "%") + '</td>'
      + '<td class="r stk-num">' + _pvMoney(r.cpc) + '</td></tr>';
  });
  return h + '</tbody></table></div>';
}
