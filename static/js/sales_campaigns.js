// static/js/sales_campaigns.js -- the campaign table, the PPC cards and Organic vs PPC. Moved word for word out of sales.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* ---- campaign performance table -----------------------------------------
 * Every campaign that ran in the chosen window, sortable, worst-value first by
 * default -- because the question this table exists to answer is "what is
 * wasting money", not "what is biggest".
 *
 * THE PERIOD IS THE ONE ON SCREEN. Rows are summed server-side over the same
 * start/end as every other panel, so a campaign's spend here and the Ad Spend
 * card above it are the same money over the same days.
 *
 * ACOS, ROAS and CPC ARE THE SERVER'S. It sums first and divides once; averaging
 * thirty daily ACOS figures gives a different and wrong answer, and on a day
 * with spend and no sales it gives no answer at all. Nothing is recomputed here.
 *
 * A campaign with spend and NO sales shows "—" for ACOS, never 0%. Zero would
 * read as perfect efficiency for money that bought nothing; the dash says there
 * is no ratio to state, and the spend column still shows what it cost.
 */
var SALES_CAMP = {rows: [], totals: {}, currency: "", sort: "spend", desc: true,
                  loaded: false, error: "", products: []};

const _CAMP_COLS = [
  {k: "campaign_name", t: "Campaign",    kind: "text"},
  {k: "status",        t: "Status",      kind: "status"},
  {k: "budget",        t: "Budget",      kind: "money"},
  {k: "spend",         t: "Spend",       kind: "money"},
  {k: "ad_sales",      t: "Sales",       kind: "money"},
  {k: "acos",          t: "ACOS",        kind: "pct"},
  {k: "roas",          t: "ROAS",        kind: "x"},
  {k: "ad_orders",     t: "Orders",      kind: "count"},
  {k: "clicks",        t: "Clicks",      kind: "count"},
  {k: "impressions",   t: "Impr",        kind: "count"},
  {k: "cpc",           t: "CPC",         kind: "money4"},
];

function salesCampSort(k){
  if(SALES_CAMP.sort === k) SALES_CAMP.desc = !SALES_CAMP.desc;
  else { SALES_CAMP.sort = k; SALES_CAMP.desc = true; }
  salesDrawCampaigns();
}

async function salesLoadCampaigns(){
  const host = document.getElementById("sales_campaigns");
  if(!host) return;
  // Same query builder and same fetch wrapper as every other panel, so the
  // campaign table is always showing the period the rest of the screen is.
  // Newest ask wins: an older period's campaigns must not land over a newer's.
  const tk = SALES_CAMP.seq = (SALES_CAMP.seq || 0) + 1;
  try{
    const j = await _sFetch("/sales/campaigns?" + _sQuery());
    if(j === null) return;                       // superseded by a newer request
    if(tk !== SALES_CAMP.seq) return;
    SALES_CAMP.rows = (j && j.rows) || [];
    SALES_CAMP.totals = (j && j.totals) || {};
    SALES_CAMP.currency = (j && j.currency) || "";
    SALES_CAMP.products = (j && j.ad_products) || [];
    SALES_CAMP.error = (j && j.ok) ? "" : ((j && j.error) || "could not load campaigns");
  }catch(e){
    if(tk !== SALES_CAMP.seq) return;
    SALES_CAMP.rows = []; SALES_CAMP.error = "could not load campaigns";
  }
  SALES_CAMP.loaded = true;
  salesDrawCampaigns();
}

async function salesAdsRefresh(btn){
  /* Ask Amazon for fresh reports. DOES NOT WAIT -- see /sales/ads-refresh.
     The button says what actually happened rather than implying the numbers
     have just changed, because they usually have not yet. */
  const note = document.getElementById("sales_camp_note");
  if(btn){ btn.disabled = true; btn.dataset.old = btn.innerHTML;
           btn.innerHTML = '<i class="ti ti-loader"></i> Asking Amazon…'; }
  try{
    // _sFetch, NOT a raw fetch. Every /sales/ call goes through it so the
    // account is on the request and a reply that arrives after the workspace
    // has been switched is dropped rather than painted onto the account you
    // have just opened -- the account-mixing fault this codebase has been
    // bitten by before. It does not cache or de-duplicate when opts are given,
    // so a POST is sent exactly once. test_request_account.py enforces this.
    const j = await _sFetch("/sales/ads-refresh", {method: "POST"});
    if(j === null) return;               // superseded by an account switch
    if(note){
      note.innerHTML = j && j.ok
        ? '<span class="cc">' + _sEsc(j.note || "") + '</span>'
        : '<span style="color:var(--red)">' + _sEsc((j && j.error) || "refresh failed") + '</span>';
    }
    if(j && j.ok && j.collected) await salesLoadCampaigns();
  }catch(e){
    if(note) note.innerHTML = '<span style="color:var(--red)">refresh failed</span>';
  }
  if(btn){ btn.disabled = false; btn.innerHTML = btn.dataset.old || "Refresh PPC data"; }
}

function salesDrawCampaigns(){
  const host = document.getElementById("sales_campaigns");
  if(!host) return;
  const cur = SALES_CAMP.currency;
  const rows = SALES_CAMP.rows || [];

  let h = '<div style="display:flex;align-items:center;gap:10px;margin:2px 0 10px;flex-wrap:wrap">'
    + '<div style="font-size:12.5px;font-weight:600">Campaign performance</div>'
    + '<span class="cc" style="font-size:11px">' + rows.length + ' campaign'
    + (rows.length === 1 ? '' : 's') + ' in this period'
    + (SALES_CAMP.products && SALES_CAMP.products.length
        ? ' · ' + _sEsc(SALES_CAMP.products.map(function(p){
            return p.replace("SPONSORED_", "Sponsored ").toLowerCase()
                    .replace(/(^|\s)\w/g, function(c){ return c.toUpperCase(); });
          }).join(", "))
        : '')
    + '</span>'
    + '<span style="margin-left:auto;display:flex;align-items:center;gap:8px">'
    + '<span id="sales_camp_note" style="font-size:11px"></span>'
    + '<button class="mktbtn" onclick="salesAdsRefresh(this)" '
    + 'title="Ask Amazon to build fresh advertising reports. They take about ten '
    + 'minutes, so the new figures appear on a later refresh — nothing is lost '
    + 'in the meantime."><i class="ti ti-refresh"></i> Refresh PPC data</button>'
    + '</span></div>';

  if(!rows.length){
    h += '<div class="cc" style="padding:14px;border:1px dashed var(--line2);'
      +  'border-radius:6px;font-size:12px">'
      +  _sEsc(SALES_CAMP.error
                || "No advertising campaigns ran in this period.")
      +  '</div>';
    host.innerHTML = h; return;
  }

  const dir = SALES_CAMP.desc ? -1 : 1;
  const sorted = rows.slice().sort(function(a, b){
    let x = a[SALES_CAMP.sort], y = b[SALES_CAMP.sort];
    // Unknown is not "smallest". A campaign with no ACOS must not sort as the
    // most efficient one on the screen.
    if(x === null || x === undefined) return 1;
    if(y === null || y === undefined) return -1;
    // The same direction as the numbers: A-Z when the header says ascending.
    // It was inverted, so a descending (▾) text column read A-Z (review, 30 Sep).
    if(typeof x === "string") return dir * (x < y ? -1 : x > y ? 1 : 0);
    return dir * (x - y);
  });

  h += '<div style="overflow-x:auto"><table class="kv" style="width:100%;min-width:900px">'
    + '<thead><tr>';
  _CAMP_COLS.forEach(function(c){
    h += '<th style="text-align:' + (c.kind === "text" || c.kind === "status" ? "left" : "right")
      +  ';font-size:11px;cursor:pointer;white-space:nowrap;padding:6px 8px" '
      +  'onclick="salesCampSort(' + jsArg(c.k) + ')">'
      +  _sEsc(c.t) + (SALES_CAMP.sort === c.k ? (SALES_CAMP.desc ? " ▾" : " ▴") : "")
      +  '</th>';
  });
  h += '</tr></thead><tbody>';

  sorted.forEach(function(r){
    h += '<tr>';
    _CAMP_COLS.forEach(function(c){
      const v = r[c.k];
      let cell, align = (c.kind === "text" || c.kind === "status") ? "left" : "right";
      if(c.kind === "text"){
        cell = '<span style="display:block;overflow:hidden;text-overflow:ellipsis;'
             + 'white-space:nowrap;max-width:320px;font-size:11.5px" title="'
             + _sEsc(String(v || "")) + '">' + _sEsc(String(v || "—")) + '</span>';
      } else if(c.kind === "status"){
        // PAUSED and ARCHIVED are not failures -- a campaign that ran and was
        // stopped still spent what it spent, and the history is the point of
        // the table. Marked, not hidden.
        const s = String(v || "").toUpperCase();
        const col = s === "ENABLED" ? "var(--ok)"
                  : (s === "PAUSED" ? "var(--warn)" : "");
        cell = s ? '<span style="font-size:10.5px' + (col ? ";color:" + col : "") + '">'
                   + _sEsc(s.charAt(0) + s.slice(1).toLowerCase()) + '</span>'
                 : '<span class="cc">—</span>';
      } else if(v === null || v === undefined){
        cell = '<span class="cc">—</span>';
      } else if(c.kind === "money")  cell = _sEsc(_sNum(v, "money", cur));
      else if(c.kind === "money4")   cell = _sEsc(_sCur(cur) + Number(v).toFixed(3));
      else if(c.kind === "pct")      cell = Number(v).toFixed(1) + "%";
      else if(c.kind === "x")        cell = Number(v).toFixed(2) + "x";
      else                           cell = Number(v).toLocaleString();
      h += '<td style="text-align:' + align + ';padding:5px 8px;font-size:11.5px">'
        +  cell + '</td>';
    });
    h += '</tr>';
  });

  // THE TOTAL ROW IS THE SERVER'S SUM, not a sum of what is displayed -- they
  // are the same today and would silently stop being the same the moment this
  // table gains a filter or a row limit.
  const t = SALES_CAMP.totals || {};
  const tAcos = (t.spend && t.ad_sales) ? (100 * t.spend / t.ad_sales) : null;
  const tRoas = (t.spend && t.ad_sales) ? (t.ad_sales / t.spend) : null;
  const tCpc  = (t.spend && t.clicks)   ? (t.spend / t.clicks) : null;
  h += '</tbody><tfoot><tr style="border-top:1px solid var(--line2);font-weight:600">'
    + '<td style="padding:6px 8px;font-size:11.5px">All campaigns</td>'
    + '<td></td><td></td>'
    + '<td style="text-align:right;padding:6px 8px;font-size:11.5px">' + _sEsc(_sNum(t.spend, "money", cur)) + '</td>'
    + '<td style="text-align:right;padding:6px 8px;font-size:11.5px">' + _sEsc(_sNum(t.ad_sales, "money", cur)) + '</td>'
    + '<td style="text-align:right;padding:6px 8px;font-size:11.5px">' + (tAcos === null ? "—" : tAcos.toFixed(1) + "%") + '</td>'
    + '<td style="text-align:right;padding:6px 8px;font-size:11.5px">' + (tRoas === null ? "—" : tRoas.toFixed(2) + "x") + '</td>'
    + '<td style="text-align:right;padding:6px 8px;font-size:11.5px">' + Number(t.ad_orders || 0).toLocaleString() + '</td>'
    + '<td style="text-align:right;padding:6px 8px;font-size:11.5px">' + Number(t.clicks || 0).toLocaleString() + '</td>'
    + '<td style="text-align:right;padding:6px 8px;font-size:11.5px">' + Number(t.impressions || 0).toLocaleString() + '</td>'
    + '<td style="text-align:right;padding:6px 8px;font-size:11.5px">' + (tCpc === null ? "—" : _sEsc(_sCur(cur) + tCpc.toFixed(3))) + '</td>'
    + '</tr></tfoot></table></div>';

  host.innerHTML = h;
}

/* ---- PPC summary cards ---------------------------------------------------
 * Spend, ACOS, TACOS, ROAS and CPC, sitting above the Organic vs PPC split so
 * the cost of the paid half is read before the split it produced.
 *
 * EVERY FIGURE IS THE SERVER'S. spend, acos, tacos and roas are already in
 * sum.totals -- domain/sales_data.py derives them from ads_daily and defines
 * acos as spend/ad_sales, tacos as spend/ordered_sales, roas as ad_sales/spend.
 * Recomputing any of them here would be a second definition that can disagree
 * with the grid on the same screen (CLAUDE.md Rule 12), so this only formats.
 *
 * CPC is the exception and is derived here, because nothing else in the app
 * shows it: spend / clicks, both from the same totals, so it cannot drift.
 *
 * NOT CONNECTED DRAWS NOTHING. An account with no advertising data gets an
 * empty row, not five zeros -- a zero ACOS is a claim about performance.
 */
function salesDrawPpcCards(sum){
  const host = document.getElementById("sales_ppccards");
  if(!host) return;
  const t = (sum && sum.totals) || {};
  const cur = (sum && sum.currency) || t.currency;
  const connected = !!(sum && sum.ads_connected);
  const spend = Number(t.spend);
  if(!connected || !isFinite(spend) || !spend){ host.innerHTML = ""; return; }

  const clicks = Number(t.clicks);
  const cpc = (isFinite(clicks) && clicks) ? (spend / clicks) : null;
  const n = function(v){ return (v === null || v === undefined || !isFinite(Number(v)))
                                ? null : Number(v); };

  // Sponsored Products only. Said on every card that could be read as "all of
  // your advertising", because Brands and Display are not in these figures and
  // a spend that is a floor must not be read as a total.
  const SP = "Sponsored Products only — Sponsored Brands and Sponsored Display "
           + "are separate ad products and are not included, so this is a floor.";

  const CARDS = [
    {label: "Ad Spend", value: n(t.spend), kind: "money",
     note: "What Amazon charged for clicks in this period. " + SP},
    {label: "ACOS", value: n(t.acos), kind: "pct", lowerIsBetter: true,
     note: "Ad spend as a share of the sales advertising is credited with "
         + "(spend ÷ ad sales). Lower is better."},
    {label: "TACOS", value: n(t.tacos), kind: "pct", lowerIsBetter: true,
     note: "Ad spend as a share of ALL sales, advertised or not "
         + "(spend ÷ total sales). This is the one that says whether "
         + "advertising is growing the business or just carrying it."},
    {label: "ROAS", value: n(t.roas), kind: "count",
     note: "Sales credited to advertising for each unit of currency spent "
         + "(ad sales ÷ spend). 3.0 means £3 back for every £1 out."},
    // CPC IS FORMATTED EXACTLY, not shortened. _sShort renders money with no
    // decimals -- right for a £1,294 sales card, fatal for a 26p click, which
    // it would print as "£0". Pence are the whole figure here.
    {label: "Avg CPC", value: cpc, kind: "money", exact: true,
     note: cpc === null ? "No clicks in this period."
                        : "Average cost per click: spend ÷ " + _sNum(clicks, "count") + " clicks."},
  ];

  host.innerHTML = CARDS.map(function(c){
    const missing = (c.value === null);
    const shown = missing ? "—"
                : (c.exact ? _sNum(c.value, c.kind, cur)
                           : _sShort(c.value, c.kind, cur));
    return '<div class="stat-card' + (missing ? " is-empty" : "") + '">'
      + '<p class="stat-label">' + _sEsc(c.label) + ' '
      + '<span class="statinfo" title="' + _sEsc(c.note) + '">'
      + '<i class="ti ti-info-circle"></i></span></p>'
      + '<p class="stat-number">'
      + _sEsc(shown)
      + (c.kind === "count" && !missing ? "x" : "")
      + '</p>'
      + '<p class="stat-delta">' + (missing ? "" : "Sponsored Products") + '</p>'
      + '</div>';
  }).join("");
}

/* ---- organic vs PPC -----------------------------------------------------
 * Orbit's split of what sold on its own against what advertising paid for:
 * two stacked areas in its own measured colours (#10b981 organic, #8b5cf6
 * PPC), a share bar above them, and the percentages named.
 *
 * BUILT BEFORE THE API WAS CONNECTED, with the shape drawn from a sample series
 * and every figure marked as such, so the panel was judgeable before it had
 * anything real in it. The one thing it must never do is show a plausible split
 * as though it were measured: an organic/paid ratio drives what you spend, and
 * a made-up one is worse than a blank panel.
 *
 * CONNECTED 5 Sep 2026 for nestwell_goods, and the switch below needed no
 * change -- haveAds went true on its own the moment domain/ads_sync.py put real
 * rows in ads_daily, the 70/30 banner disappeared and the two lines became
 * measured. The sample branch stays because it is still the truth for every
 * account that has not connected: five of the six have no advertising login.
 *
 * First real reading, Nestwell UK, 30 days: 1,294.97 total, 827.29 attributed
 * to advertising, 467.68 organic. Nearly two thirds of the revenue is paid for,
 * which is exactly the kind of thing a made-up 70/30 would have hidden.
 */
function salesDrawOrgPpc(ser){
  const host = document.getElementById("sales_orgppc");
  if(!host || typeof salesCombo !== "function") return;
  const cols = (ser && ser.columns) || [];
  const by = {};
  ((ser && ser.metrics) || []).forEach(function(m){ by[m.key] = m.cells || []; });

  const total = by["ordered_sales"] || by["net_revenue"] || [];
  // ad_sales is what the Advertising API would give. Absent today.
  const adSales = by["ad_sales"] || [];
  const haveAds = adSales.some(function(v){
    return v !== null && v !== undefined && Number(v) !== 0; });

  // CONNECTED WITH NO AD SALES IS A MEASUREMENT, not "not connected". The
  // placeholder used to appear whenever no ad sale was non-zero, so an account
  // WITH an Advertising login that sold nothing through ads this period was
  // told it was not connected. ser.ads is api/amazon_ads.connection's answer
  // (the one place that decides it); ok === true means connected.
  const adsConnected = !!(ser && ser.ads && ser.ads.ok === true);
  let organic, ppc, sample = false, note = "";
  if(!haveAds && adsConnected){
    ppc = total.map(function(t, i){
      if(t === null || t === undefined) return null;
      const a = adSales[i];
      return (a === null || a === undefined) ? 0 : Number(a);
    });
    organic = total.map(function(t){
      return (t === null || t === undefined) ? null : Number(t);
    });
    note = '<div class="cc" style="font-size:11.5px;margin:0 0 10px">'
      + 'Advertising is connected, and no sales were attributed to ads in this '
      + 'period — so everything here is organic.</div>';
  } else if(haveAds){
    ppc = adSales.slice();
    organic = total.map(function(t, i){
      const a = Number(adSales[i] || 0);
      if(t === null || t === undefined) return null;
      // Attributed sales cannot exceed the total; if they do, the two feeds
      // disagree and the honest answer is zero organic, not a negative.
      return Math.max(0, Number(t) - a);
    });
  } else {
    // The SHAPE, from this account's own real sales, split on a fixed ratio so
    // the panel is not a straight line. Marked, never presented as measured.
    sample = true;
    const base = total.length ? total : cols.map(function(){ return null; });
    organic = base.map(function(v){ return v === null || v === undefined ? null : Number(v) * 0.7; });
    ppc     = base.map(function(v){ return v === null || v === undefined ? null : Number(v) * 0.3; });
    note = '<div class="ri-samplebar" style="margin:0 0 12px">'
      + '<b>This split is a placeholder, not your data.</b> It divides your real '
      + 'sales 70/30 purely to show the shape. The real split needs the '
      + 'Advertising API, which this account is not connected to — until then '
      + 'nothing here is measured, and the app will not guess at a ratio that '
      + 'decides what you spend.</div>';
  }

  const sum = function(a){ return a.reduce(function(x, v){ return x + (Number(v) || 0); }, 0); };
  const o = sum(organic), p = sum(ppc), t = o + p;
  const oPct = t ? Math.round((o / t) * 100) : 0;
  const pPct = t ? (100 - oPct) : 0;

  // THE SWATCHES TAKE THE CHART'S OWN COLOURS, rather than naming their own.
  //
  // They used var(--ok-bg) and var(--ai-bg) -- theme variables that have never
  // had anything to do with what the chart draws. So the key above the chart
  // and the two areas inside it were only ever the same colour by luck, and
  // changing either one silently broke the pairing. Read from SC_SERIES and
  // they cannot disagree (Rule 12): one definition, used by the line, the fill
  // and the swatch.
  const _sc = (typeof SC_SERIES !== "undefined") ? SC_SERIES : {};
  const cOrg = (_sc.organic && _sc.organic.color) || "var(--ok-bg)";
  const cPpc = (_sc.ppc && _sc.ppc.color) || "var(--ai-bg)";
  const sw = function(colour){
    return '<span style="display:inline-block;width:9px;height:9px;'
         + 'border-radius:2px;background:' + colour + ';margin-right:6px"></span>';
  };
  const bar = '<div style="display:flex;height:8px;border-radius:4px;overflow:hidden;'
    + 'background:var(--panel2);margin:0 0 6px">'
    + '<div style="width:' + oPct + '%;background:' + cOrg + '"></div>'
    + '<div style="width:' + pPct + '%;background:' + cPpc + '"></div></div>'
    + '<div style="display:flex;gap:16px;font-size:12px;margin:0 0 10px"'
    + (sample ? ' class="ri-sample"' : '') + '>'
    + '<span>' + sw(cOrg) + 'Organic <b>' + oPct + '%</b>'
    + ' <span class="cc">' + _sShort(o, "money", ser && ser.currency) + '</span></span>'
    + '<span>' + sw(cPpc) + 'PPC <b>' + pPct + '%</b>'
    + ' <span class="cc">' + _sShort(p, "money", ser && ser.currency) + '</span></span>'
    + '</div>';

  if(!cols.length || !t){
    host.innerHTML = note
      + '<div class="cc" style="font-size:12px;padding:12px 0">'
      + 'No sales in this period to split.</div>';
    return;
  }

  // Measured: Orbit's Organic vs PPC panel is 1365 x 380, taller than its Sales
  // Report because the two areas overlap and need the room to stay readable.
  const chart = salesCombo({
    // Same columns as the main chart (both are ser.columns), so it zooms too.
    id: "orgppc", onZoom: "salesZoomTo", columns: cols, bars: null,
    currency: (ser && ser.currency),
    lines: [{key: "organic", values: organic}, {key: "ppc", values: ppc}],
    width: scChartWidth("sales_orgppc", 1365), height: 380,
  });
  host.innerHTML = note + bar
    + (sample ? '<div class="ri-sample">' + chart + '</div>' : chart);
  // This one is always below the fold, which is exactly what the hold is for.
  if(typeof altaChartsInView === "function") altaChartsInView(host);
}
