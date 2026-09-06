/* static/js/ppcanalytics.js -- the PPC Analytics screen.
 *
 * Advertising spend, sales, efficiency and campaign performance for a window,
 * against the window before it.
 *
 * WHAT IS HERE AND WHAT IS DELIBERATELY NOT
 * The build spec asks for a "Day trail" of seven cards, each a cumulative
 * spend-by-HOUR curve, and an ACoS heatmap of day x hour. Neither is drawn,
 * because there are no hourly advertising figures stored for this account --
 * every row Amazon has sent is one whole day. Both panels say so in place of
 * the chart. Drawing a smooth curve through twenty-four hours nobody measured
 * would be indistinguishable from a measurement, and the spec's instruction to
 * "stub it with placeholder data" is the one thing this screen has already been
 * told off for twice.
 *
 * Everything else on the spec is real: the KPI rows, the profitability figures,
 * the revenue/spend/profit chart, the TACOS trend, the cohorts, the campaign
 * table and the per-ASIN table all come from stored rows.
 *
 * NOTHING HERE WRITES. No bid, no budget, no campaign state (CLAUDE.md Rule 8).
 */

const PPCA = {data: null, loading: false, sort: "spend", desc: true,
              tab: "campaigns", q: ""};

async function ppcaLoad(){
  const host = document.getElementById("ppca_body");
  if(!host) return;
  if(PPCA.loading) return;
  PPCA.loading = true;
  host.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Reading the advertising figures…</div>';
  try{
    const qs = ppcQS(PPCWIN.start
      ? {start: PPCWIN.start, end: PPCWIN.end} : {days: PPCWIN.days});
    const j = await (await fetch("/ppc/analytics/overview?" + qs)).json();
    PPCA.loading = false;
    if(!j || !j.ok){
      host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _pEsc((j && j.error) || "Could not read the advertising figures.")
        + '</div>';
      return;
    }
    PPCA.data = j;
    ppcaRender();
  }catch(e){
    PPCA.loading = false;
    host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + 'Could not read the advertising figures.</div>';
  }
}

function ppcaSort(key){
  if(PPCA.sort === key) PPCA.desc = !PPCA.desc;
  else { PPCA.sort = key; PPCA.desc = true; }
  ppcaRender();
}

function ppcaTab(t){ PPCA.tab = t; ppcaRender(); }
function ppcaFilter(v){ PPCA.q = (v || "").toLowerCase(); ppcaRender(); }

function ppcaRender(){
  const host = document.getElementById("ppca_body");
  const j = PPCA.data;
  if(!host || !j) return;
  const cur = "GBP";
  const t = j.totals || {}, ch = j.change || {}, av = j.availability || {};

  let h = ppcWindowBar("ppcaLoad");

  // NOTHING STORED AT ALL is a different screen from a quiet month, and the
  // difference is the first thing to say.
  if(!t.has_data){
    host.innerHTML = h + ppcUnavailable(
      "No advertising figures for this window",
      (av.campaigns && av.campaigns.why)
        || "Nothing is stored for this account and marketplace in this window.");
    return;
  }

  h += ppcAvailabilityNote(av);
  h += ppcProductNote(av);
  h += ppcRatesNote(j.rates);

  // ---- the headline figures ------------------------------------------
  h += ppcCards([
    ppcCard({label: "Spend", value: ppcMoney(t.spend, cur),
             change: ppcChange(ch.spend, "down"),
             help: "What Amazon charged for the ads in this window."}),
    ppcCard({label: "Ad sales", value: ppcMoney(t.sales, cur),
             change: ppcChange(ch.sales, "up"),
             help: "Sales Amazon attributes to those ads. Not the same as total "
                 + "sales — an organic sale is not in here."}),
    ppcCard({label: "ACOS", value: ppcPct(t.acos_pct),
             change: ppcChange(ch.acos_pct, "down"),
             help: "Spend divided by AD sales. How much of the advertised "
                 + "revenue the advertising ate. Lower is better."}),
    ppcCard({label: "TACOS", value: ppcPct(t.tacos_pct),
             change: ppcChange(ch.tacos_pct, "down"),
             help: "Spend divided by ALL sales, advertised and organic "
                 + "together. The honest measure of what advertising costs the "
                 + "business."}),
  ]);
  h += ppcCards([
    ppcCard({label: "ROAS", value: ppcX(t.roas),
             change: ppcChange(ch.roas, "up"),
             help: "Ad sales for every pound of spend."}),
    ppcCard({label: "Impressions", value: ppcNum(t.impressions),
             change: ppcChange(ch.impressions, "up"),
             help: "How many times the ads were shown."}),
    ppcCard({label: "Clicks", value: ppcNum(t.clicks),
             change: ppcChange(ch.clicks, "up"),
             help: "How many times somebody clicked one."}),
    ppcCard({label: "CTR", value: ppcPct(t.ctr_pct, "", 2),
             change: ppcChange(ch.ctr_pct, "up"),
             help: "Clicks per impression."}),
  ]);
  h += ppcCards([
    ppcCard({label: "Orders", value: ppcNum(t.orders),
             change: ppcChange(ch.orders, "up"),
             help: "Orders Amazon attributes to the ads."}),
    ppcCard({label: "CVR", value: ppcPct(t.cvr_pct, "", 2),
             change: ppcChange(ch.cvr_pct, "up"),
             help: "Orders per click."}),
    ppcCard({label: "CPC", value: ppcMoney(t.cpc, cur),
             change: ppcChange(ch.cpc, "down"),
             help: "What each click cost on average."}),
    ppcCard({label: "CPA", value: ppcMoney(t.cpa, cur),
             change: ppcChange(ch.cpa, "down"),
             help: "What each attributed order cost in advertising."}),
  ]);

  // ---- profitability --------------------------------------------------
  h += ppcaProfitability(j, cur);

  // ---- the chart ------------------------------------------------------
  h += ppcaChart(j, cur);

  // ---- the two panels that cannot be honest ---------------------------
  //
  // Named, in the place they would have been, so it is obvious they were
  // considered rather than forgotten.
  if(av.hourly && !av.hourly.ok){
    h += ppcUnavailable("Day trail — cumulative spend by hour", av.hourly.why);
    h += ppcUnavailable("ACoS heatmap — day × hour", av.hourly.why);
  }

  // ---- cohorts --------------------------------------------------------
  h += ppcaCohorts(j, cur);

  // ---- the tables -----------------------------------------------------
  h += ppcaTables(j, cur);

  host.innerHTML = h;
  if(typeof altaChartsInView === "function"){
    try{ altaChartsInView(host); }catch(e){}
  }
}

/* Is the advertising making money, and where is the line?
 *
 * BREAK-EVEN ACOS IS THE ONE FIGURE ON THIS SCREEN WORTH ACTING ON. It is what
 * is left of a pound after Amazon's fee and the stock, so it is the most an ad
 * can cost before the sale stops being worth having -- and it is measured from
 * this account rather than assumed, because a 60%-margin product and a
 * 15%-margin one do not become unprofitable at the same ACOS. */
function ppcaProfitability(j, cur){
  const r = j.rates || {}, t = j.totals || {}, w = j.wasted || {};
  const be = r.breakeven_acos_pct;
  const acos = t.acos_pct;
  let verdict = "";
  if(be !== null && be !== undefined && acos !== null && acos !== undefined){
    const ok = acos < be;
    verdict = '<span style="color:' + (ok ? "var(--ok,#3fb950)" : "var(--red)")
      + ';font-weight:600">' + (ok ? "Profitable" : "Losing money")
      + '</span> — ACOS ' + ppcPct(acos) + ' against a break-even of '
      + ppcPct(be);
  }else{
    verdict = '<span class="cc">Cannot be judged: this account has no measured '
      + 'break-even ACOS for this window.</span>';
  }

  return '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
    + 'margin:0 0 10px">'
    + '<div style="font-weight:600;margin-bottom:6px">Profitability</div>'
    + '<div style="font-size:12.5px;margin-bottom:10px">' + verdict + '</div>'
    + ppcCards([
        ppcCard({label: "Break-even ACOS", value: ppcPct(be),
                 note: (r.cogs_basis || ""),
                 help: "What is left of a pound of revenue after Amazon's fee "
                     + "and the stock cost. Spend more than this on an ad and "
                     + "the sale loses money. Measured from this account, not "
                     + "a rule of thumb."}),
        ppcCard({label: "Wasted spend", value: ppcMoney(w.spend, cur, w.why),
                 note: (w.terms ? w.terms + " search terms" : ""),
                 why: w.why,
                 help: "Spend on search terms that took at least one click and "
                     + "produced no order. Not 'ACOS above target' — that is a "
                     + "judgement about price. This is money that bought "
                     + "traffic which bought nothing."}),
        ppcCard({label: "Amazon's fee", value: ppcPct(
                   (r.fee_rate === null || r.fee_rate === undefined)
                     ? null : r.fee_rate * 100),
                 note: (r.fee_rate_basis || ""),
                 help: "Measured from what Amazon has actually charged this "
                     + "account on settled orders."}),
        ppcCard({label: "Stock cost", value: ppcPct(
                   (r.cogs_rate === null || r.cogs_rate === undefined)
                     ? null : r.cogs_rate * 100),
                 note: (r.cogs_basis || ""),
                 help: "What the goods cost, as a share of what they sold for, "
                     + "across the orders in this window that have a cost "
                     + "recorded."}),
      ])
    + '</div>';
}

/* Spend, ad sales, total sales and TACOS over the window.
 *
 * Drawn with salesCombo -- the app's own chart, the one the Sales page uses --
 * so the two screens look like one app and a reader is not relearning the key.
 * A day with no advertising row leaves a GAP rather than a point on the floor:
 * "we did not advertise" and "we advertised and spent nothing" are different,
 * and only the chart can tell you which. */
function ppcaChart(j, cur){
  const d = j.daily || [];
  if(!d.length) return "";
  const cols = d.map(function(x){ return x.date; });
  const has = function(k){
    return d.some(function(x){ return x[k] !== null && x[k] !== undefined; });
  };
  const lines = [];
  if(has("spend"))
    lines.push({key: "ad_spend", values: d.map(function(x){ return x.spend; })});
  if(has("ad_sales"))
    lines.push({key: "ad_sales", values: d.map(function(x){ return x.ad_sales; })});
  if(has("total_sales"))
    lines.push({key: "total_sales",
                values: d.map(function(x){ return x.total_sales; })});
  if(!lines.length) return "";

  let h = '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
    + 'margin:0 0 10px">'
    + '<div style="font-weight:600;margin-bottom:2px">Revenue, ad spend and what '
    + 'it returned</div>'
    + '<div class="cc" style="font-size:11.5px;margin-bottom:8px">'
    + 'Hover for the day\'s figures · drag across to zoom · click a name below '
    + 'to hide that line. A gap is a day with nothing stored, not a day with no '
    + 'spend.</div>'
    + '<div id="ppca_chart">'
    + salesCombo({id: "ppca_combo", columns: cols, bars: null, lines: lines,
                  currency: cur, unit: "day",
                  width: scChartWidth("ppca_chart", 1365), height: 320})
    + '</div></div>';

  // TACOS ON ITS OWN, because it is a percentage and the chart above is money.
  // Putting a rate on a money axis draws it as a flat line along the floor --
  // the same reason the app's other rate charts are separate.
  if(has("tacos_pct")){
    h += '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
      + 'margin:0 0 10px">'
      + '<div style="font-weight:600;margin-bottom:2px">TACOS over time</div>'
      + '<div class="cc" style="font-size:11.5px;margin-bottom:8px">'
      + 'Advertising spend as a share of <b>all</b> sales that day, organic '
      + 'included. Its own chart because it is a rate, and a rate on a money '
      + 'axis draws as a flat line.</div>'
      + '<div id="ppca_tacos">'
      + salesCombo({id: "ppca_tacos_c", columns: cols, bars: null,
                    lines: [{key: "tacos",
                             values: d.map(function(x){ return x.tacos_pct; })}],
                    unit: "day", kind: "pct",
                    width: scChartWidth("ppca_tacos", 1365), height: 240})
      + '</div></div>';
  }
  return h;
}

/* The five buckets. "No sales" and "No activity" are kept apart on purpose:
 * one is money gone for nothing, the other is a campaign that did not run, and
 * merging them would put 84 campaigns' wasted spend in the same box as 148 that
 * cost nothing. */
function ppcaCohorts(j, cur){
  const c = j.cohorts || {};
  if(!c.all || !c.all.n) return "";
  const order = ["profitable", "marginal", "unprofitable", "no_sales",
                 "no_activity", "unclassified"];
  const tone = {profitable: "#3fb950", marginal: "#d29922",
                unprofitable: "#f85149", no_sales: "#c04b45",
                no_activity: "#6e7681", unclassified: "#8b949e"};
  let h = '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
    + 'margin:0 0 10px">'
    + '<div style="font-weight:600;margin-bottom:2px">How the campaigns are '
    + 'doing</div>'
    + '<div class="cc" style="font-size:11.5px;margin-bottom:10px">'
    + 'Sorted against this account\'s own break-even ACOS. '
    + '<b>Marginal</b> means profitable but within a tenth of break-even, where '
    + 'a small rise in cost per click takes it under.</div>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fit,'
    + 'minmax(150px,1fr));gap:6px">';
  h += '<div class="panelcard" style="padding:11px 13px;border-radius:8px;'
    + 'border:2px solid var(--gold)">'
    + '<div class="cc" style="font-size:10.5px;text-transform:uppercase;'
    + 'letter-spacing:.7px">All</div>'
    + '<div style="font-size:24px;font-weight:600">' + c.all.n + '</div>'
    + '<div class="cc" style="font-size:10.5px">' + ppcMoney(c.all.spend, cur)
    + ' spend</div></div>';
  order.forEach(function(k){
    const b = c[k];
    if(!b || !b.n) return;
    h += '<div class="panelcard" style="padding:11px 13px;border-radius:8px">'
      + '<div class="cc" style="font-size:10.5px;text-transform:uppercase;'
      + 'letter-spacing:.7px;color:' + tone[k] + '">'
      + '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
      + 'background:' + tone[k] + ';margin-right:5px"></span>'
      + _pEsc(b.label || k) + '</div>'
      + '<div style="font-size:24px;font-weight:600">' + b.n + '</div>'
      + '<div class="cc" style="font-size:10.5px">' + ppcMoney(b.spend, cur)
      + ' spend · ' + ppcMoney(b.sales, cur) + ' sales</div></div>';
  });
  return h + '</div></div>';
}

/* Campaigns and products, on two tabs of one panel. */
function ppcaTables(j, cur){
  const isC = (PPCA.tab === "campaigns");
  let h = '<div class="panelcard" style="padding:0;border-radius:8px;'
    + 'overflow:hidden">'
    + '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
    + 'padding:12px 14px">'
    + '<button class="db-chip' + (isC ? " on" : "") + '" '
    + 'onclick="ppcaTab(\'campaigns\')">Campaigns'
    + (j.campaign_count ? ' <span class="cc">' + j.campaign_count + '</span>' : '')
    + '</button>'
    + '<button class="db-chip' + (!isC ? " on" : "") + '" '
    + 'onclick="ppcaTab(\'asins\')">Products'
    + ((j.asins || []).length ? ' <span class="cc">' + j.asins.length + '</span>' : '')
    + '</button>'
    + '<input placeholder="Filter…" oninput="ppcaFilter(this.value)" '
    + 'style="font-size:12px;padding:5px 9px;min-width:170px;margin-left:auto">'
    + '</div>';
  h += isC ? ppcaCampaignTable(j, cur) : ppcaAsinTable(j, cur);
  return h + '</div>';
}

function ppcaCampaignTable(j, cur){
  let rows = (j.campaigns || []);
  if(PPCA.q){
    rows = rows.filter(function(r){
      return String(r.name || "").toLowerCase().indexOf(PPCA.q) >= 0;
    });
  }
  rows = ppcSortRows(rows, PPCA.sort, PPCA.desc);
  if(!rows.length){
    return '<div class="cc" style="padding:16px">No campaigns match.</div>';
  }
  const tone = {profitable: "#3fb950", marginal: "#d29922",
                unprofitable: "#f85149", no_sales: "#c04b45",
                no_activity: "#6e7681"};
  let h = '<div style="overflow-x:auto"><table class="kv ordtable" '
    + 'style="width:100%;min-width:1000px"><thead><tr>'
    + ppcTh("Opp", "opportunity", PPCA, "ppcaSort", "left",
            "How much there is to gain by looking at this one.")
    + ppcTh("Campaign", "name", PPCA, "ppcaSort", "left")
    + ppcTh("Status", "status", PPCA, "ppcaSort", "left")
    + ppcTh("Profit", "profit", PPCA, "ppcaSort", "right",
            "Estimated: Amazon's attributed sales less the spend, this "
            + "account's measured fee and its measured stock cost.")
    + ppcTh("Spend", "spend", PPCA, "ppcaSort", "right")
    + ppcTh("Sales", "sales", PPCA, "ppcaSort", "right")
    + ppcTh("ACOS", "acos_pct", PPCA, "ppcaSort", "right")
    + ppcTh("ROAS", "roas", PPCA, "ppcaSort", "right")
    + ppcTh("Clicks", "clicks", PPCA, "ppcaSort", "right")
    + ppcTh("CPC", "cpc", PPCA, "ppcaSort", "right")
    + ppcTh("Orders", "orders", PPCA, "ppcaSort", "right")
    + '</tr></thead><tbody>';
  rows.forEach(function(r){
    h += '<tr>'
      + '<td>' + ppcOpp(r.opportunity) + '</td>'
      + '<td style="font-size:11.5px;max-width:280px;overflow-wrap:anywhere">'
      +   _pEsc(r.name || r.campaign_id)
      +   (r.cohort ? '<div style="font-size:10px;color:' + (tone[r.cohort] || "")
                      + '">' + _pEsc((j.cohorts && j.cohorts[r.cohort]
                                      && j.cohorts[r.cohort].label) || r.cohort)
                      + '</div>' : '')
      + '</td>'
      + '<td style="font-size:11px">' + _pEsc(r.status || "") + '</td>'
      + '<td style="text-align:right">' + ppcProfit(r.profit, cur) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.spend, cur) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.sales, cur) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.acos_pct,
          "No attributed sales, so ACOS is undefined — not 0%.") + '</td>'
      + '<td style="text-align:right">' + ppcX(r.roas) + '</td>'
      + '<td style="text-align:right">' + ppcNum(r.clicks) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.cpc, cur) + '</td>'
      + '<td style="text-align:right">' + ppcNum(r.orders) + '</td>'
      + '</tr>';
  });
  h += '</tbody></table></div>';
  if(j.campaign_count > (j.campaigns || []).length){
    h += '<div class="cc" style="padding:9px 14px;font-size:11.5px">Showing the '
      + (j.campaigns || []).length + ' biggest spenders of ' + j.campaign_count
      + '. Campaign Analytics lists them all.</div>';
  }
  return h;
}

/* Per product: what the advertising did, beside what the listing did.
 *
 * The two halves come from different reports and mean different things -- CVR
 * here is the LISTING's units per session, from the Business Report, not the
 * ad's orders per click. Two conversion rates in one column would be
 * meaningless, so the column says which. */
function ppcaAsinTable(j, cur){
  let rows = (j.asins || []);
  if(PPCA.q){
    rows = rows.filter(function(r){
      return (String(r.asin || "") + " " + String(r.title || ""))
        .toLowerCase().indexOf(PPCA.q) >= 0;
    });
  }
  rows = ppcSortRows(rows, PPCA.sort === "name" ? "asin" : PPCA.sort, PPCA.desc);
  if(!rows.length){
    return '<div class="cc" style="padding:16px">No products match.</div>';
  }
  let h = '<div style="overflow-x:auto"><table class="kv ordtable" '
    + 'style="width:100%;min-width:1020px"><thead><tr>'
    + '<th style="width:34%">Product<span class="th-sub">ASIN, title</span></th>'
    + ppcTh("Profit", "profit", PPCA, "ppcaSort", "right",
            "Estimated from this account's measured fee and stock cost.")
    + ppcTh("Spend", "spend", PPCA, "ppcaSort", "right")
    + ppcTh("Ad sales", "sales", PPCA, "ppcaSort", "right")
    + ppcTh("ACOS", "acos_pct", PPCA, "ppcaSort", "right")
    + ppcTh("Clicks", "clicks", PPCA, "ppcaSort", "right")
    + ppcTh("Sessions", "sessions", PPCA, "ppcaSort", "right",
            "Visits to the listing, from the Business Report — all traffic, "
            + "not just advertising.")
    + ppcTh("Views", "page_views", PPCA, "ppcaSort", "right")
    + ppcTh("Buy box", "buy_box_pct", PPCA, "ppcaSort", "right")
    + ppcTh("CVR", "cvr_pct", PPCA, "ppcaSort", "right",
            "The LISTING's conversion: units per session. Not the ad's orders "
            + "per click.")
    + '</tr></thead><tbody>';
  rows.forEach(function(r){
    h += '<tr>'
      + '<td style="min-width:220px"><div style="display:flex;gap:8px;'
      +   'align-items:center">'
      +   (r.img ? '<img src="' + _pEsc(r.img) + '" style="width:30px;height:30px;'
                   + 'object-fit:contain;border-radius:4px" loading="lazy">'
                 : '<span class="cc" style="width:30px;text-align:center">'
                   + '<i class="ti ti-photo-off"></i></span>')
      +   '<div style="min-width:0"><code style="font-size:10.5px;'
      +     'color:var(--accent2)">' + _pEsc(r.asin) + '</code>'
      +     '<div class="cc" style="font-size:10.5px;overflow:hidden;'
      +       'text-overflow:ellipsis;white-space:nowrap;max-width:230px">'
      +       _pEsc(r.title || "") + '</div></div></div></td>'
      + '<td style="text-align:right">' + ppcProfit(r.profit, cur) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.spend, cur) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.sales, cur) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.acos_pct,
          "No attributed sales, so ACOS is undefined — not 0%.") + '</td>'
      + '<td style="text-align:right">' + ppcNum(r.clicks) + '</td>'
      + '<td style="text-align:right">' + ppcNum(r.sessions,
          "No Business Report data stored for this product in this window.") + '</td>'
      + '<td style="text-align:right">' + ppcNum(r.page_views) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.buy_box_pct) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.cvr_pct, "", 2) + '</td>'
      + '</tr>';
  });
  return h + '</tbody></table></div>';
}
