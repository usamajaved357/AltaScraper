// ============ THE WEEKLY KPI PACK ============
//
//   "i want to make a system where i upload the reports and i get this data, in
//    a format like return intelligence. and also an option where i just need to
//    connect an account like nestwell goods and all of this data is extracted
//    without the need of reports"
//
// Replaces a Google Sheet that was wrong in five ways at once when its formulas
// were read on 18 Aug 2026 — see domain/weekly_kpi.py for all five. The two that
// matter most on screen:
//
//   * the "current" week showed the previous week's figures to the cent, and
//     nothing said so;
//   * CPA was spend/units in the history and spend/ad-orders in the present, so
//     the row tripled between two weeks that were actually the same.
//
// So: a week is FROZEN when it is built, movement is shown against the week
// before, and every figure that could not be measured says so rather than
// showing 0.00.

const WK = {week: null, weeks: [], change: {}, loading: false, note: "",
            want: "business", brandTerms: []};

function weeklyOnOpen(){
  const d = document.getElementById("wk_week");
  if(d && !d.value){
    // The week just gone, which is the one being reported on a Monday.
    const t = new Date(); t.setDate(t.getDate() - 7);
    d.value = t.toISOString().slice(0, 10);
  }
  weeklyLoad();
}

// See the note in daily.js: this was the same hand-built copy, reading an
// undefined WS_ID and forwarding "__all__" as though it were a marketplace.
// One shared builder now (CLAUDE.md Rule 12) -- static/js/scopeq.js.
function _wkQs(){ return (typeof scopeQs === "function") ? scopeQs() : ""; }

async function weeklyLoad(){
  WK.loading = true; weeklyRender();
  try{
    const j = await (await fetch("/weekly/list" + _wkQs())).json();
    if(j && j.ok){
      WK.weeks = j.weeks || [];
      WK.change = j.change || {};
      WK.brandTerms = j.brand_terms || [];
      WK.week = _wkPick();
      WK.note = "";
    }else{
      WK.note = (j && j.error) || "Could not read the stored weeks.";
    }
  }catch(e){ WK.note = "Could not read the stored weeks: " + e; }
  WK.loading = false; weeklyRender();
}

/* The week the date box is pointing at, else the newest stored one. */
function _wkPick(){
  const d = (document.getElementById("wk_week") || {}).value || "";
  if(d){
    const hit = (WK.weeks || []).find(w => w.week_start <= d && d <= w.week_end);
    if(hit) return hit;
  }
  return (WK.weeks || [])[0] || null;
}

function weeklyUploadOpen(which){
  WK.want = which;                       // only decides the toast wording
  const el = document.getElementById("wk_file");
  if(el){ el.value = ""; el.click(); }
}

async function weeklyUploadFile(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  const fd = new FormData();
  fd.append("file", f);
  const d = (document.getElementById("wk_week") || {}).value || "";
  if(d) fd.append("week_start", d);
  // The upload posts a form rather than a query string, so it takes the id on
  // its own. Same source as every other screen's -- previously the undefined
  // WS_ID, which meant an uploaded week was filed against whichever account the
  // server happened to think was active rather than the one on screen.
  const _sid = (typeof scopeAccountId === "function") ? scopeAccountId() : "";
  if(_sid) fd.append("id", _sid);
  if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
    fd.append("marketplace", WS_MARKET);
  toast("Reading " + f.name + "…");
  try{
    const j = await (await fetch("/weekly/upload", {method: "POST", body: fd})).json();
    if(!j || !j.ok){ toast((j && j.error) || "Could not read that file."); return; }
    // Says which report it TURNED OUT to be, not which button was pressed --
    // the file is identified by its columns, so pressing the wrong button is
    // corrected rather than punished.
    toast((j.family === "campaign_manager" ? "Campaign export" : "Business Report")
          + " read — " + j.rows_read + " rows.");
    await weeklyLoad();
  }catch(e){ toast("Upload failed: " + e); }
}

async function weeklyPull(){
  toast("Building the week from what the app already holds…");
  const d = (document.getElementById("wk_week") || {}).value || "";
  try{
    const j = await (await fetch("/weekly/pull" + _wkQs(), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({week_start: d})})).json();
    if(!j || !j.ok){ toast((j && j.error) || "Could not build it."); return; }
    (j.notes || []).forEach(n => toast(n));
    await weeklyLoad();
  }catch(e){ toast("Could not build it: " + e); }
}

// ---- rendering -------------------------------------------------------------

function _wkEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
/* The symbol the REPORT is written in, not the account's.
 *
 * An agency runs a client's US pack with a UK workspace open and every dollar
 * figure is drawn with a pound sign — the number right and the label a lie,
 * which is worse than either being wrong alone. Measured: uploading Naturealm's
 * US reports into jack_uk showed "£61,843.59" for $61,843.59.
 *
 * Amazon writes the symbol into the cell, so the file already knows. The
 * account is the fallback for when it does not say. */
// Was a fourth private copy of the currency map. One now, in money.js (Rule 12).
//
// Resolved WHEN CALLED, not at load. Read at module scope this file would
// capture whatever CUR_SYMBOLS was at the moment weekly.js parsed -- and
// weekly.js is loaded BEFORE money.js in the page, so it captured nothing and
// silently dropped every currency symbol on this screen. A lazy lookup cannot
// be broken by the order the tags happen to sit in.
function _wkSym(){
  const c = WK.week && WK.week.currency;
  if(c && typeof curSymbol === "function"){
    const s = curSymbol(c);
    if(s) return s;
  }
  return (typeof CUR_SYMBOL !== "undefined" && CUR_SYMBOL) ? CUR_SYMBOL : "£";
}
function _wkMoney(v){
  if(v === null || v === undefined || v === "") return "—";
  return _wkSym() + Number(v).toLocaleString(undefined,
    {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function _wkNum(v){
  return (v === null || v === undefined) ? "—" : Number(v).toLocaleString();
}
function _wkPct(v, dp){
  return (v === null || v === undefined) ? "—"
       : (Number(v) * 100).toFixed(dp === undefined ? 2 : dp) + "%";
}
function _wkX(v){
  return (v === null || v === undefined) ? "—" : Number(v).toFixed(2);
}

/* Movement against the week before. BETTER and WORSE, never up and down: for
   ACOS, CPC, CPA and TACOS down is the good direction, and an arrow alone reads
   backwards on half the rows. */
function _wkDelta(key){
  const c = WK.change[key];
  if(!c || c.better === null || c.better === undefined || !isFinite(c.pct)) return "";
  const cls = c.better ? "wk-up" : "wk-down";
  const sign = c.delta > 0 ? "+" : "";
  return '<span class="wk-d ' + cls + '" title="was ' + _wkEsc(String(c.from))
       + ' the week before">' + sign + (c.pct * 100).toFixed(1) + '%</span>';
}

function _wkCard(label, value, key, note){
  return '<div class="wk-card">'
    + '<div class="lbl">' + _wkEsc(label) + '</div>'
    + '<div class="val">' + value + (key ? " " + _wkDelta(key) : "") + '</div>'
    + (note ? '<div class="sub cc">' + note + '</div>' : '')
    + '</div>';
}

function weeklyRender(){
  const host = document.getElementById("wk_body");
  if(!host) return;
  if(WK.loading && !WK.week){
    host.innerHTML = '<div class="cc" style="padding:14px">Reading…</div>';
    return;
  }
  if(WK.note && !WK.week){
    host.innerHTML = '<div class="odp-note warn" style="padding:14px">'
      + _wkEsc(WK.note) + '</div>';
    return;
  }
  if(!WK.week){
    host.innerHTML = _wkEmpty();
    return;
  }

  const w = WK.week, k = w.kpis || {};
  let h = '';

  // TWO MARKETPLACES IN ONE PACK. Named rather than averaged away: a Business
  // Report in dollars beside a campaign export in pounds is two different
  // clients' data in one week, and every combined figure below it is meaningless.
  if(w.currency_mixed){
    h += '<div class="odp-note warn" style="padding:11px 13px;margin-bottom:12px">'
      + '<b>These two reports are in different currencies</b> — the Business '
      + 'Report is in ' + _wkEsc(w.business_currency) + ' and the campaign '
      + 'export is in ' + _wkEsc(w.campaign_currency) + '. Every figure that '
      + 'mixes them (TACOS, total spend) is not comparable. Check you exported '
      + 'both from the same marketplace.</div>';
  }

  // WHICH HALVES ARE HERE. A pack built from one report is not wrong, but every
  // figure from the other half is MISSING rather than zero, and a screen that
  // does not say so is the fault this whole feature exists to fix.
  if(!w.has_business || !w.has_campaigns){
    h += '<div class="odp-note warn" style="padding:11px 13px;margin-bottom:12px">'
      + '<b>Half a pack.</b> '
      + (!w.has_business
          ? 'No Business Report for this week, so sales, sessions and units are missing — not zero. '
          : '')
      + (!w.has_campaigns
          ? 'No campaign data for this week, so every advertising figure is missing — not zero. '
          : '')
      + 'Upload the other report, or press Build from connected account.</div>';
  }

  h += '<div class="wk-head">'
    + '<div><div class="wk-eyebrow">Week</div>'
    + '<div class="wk-week">' + _wkEsc(_wkDate(w.week_start)) + ' &ndash; '
    + _wkEsc(_wkDate(w.week_end)) + '</div></div>'
    + '<div class="cc wk-built">' + (w.source === "api" ? "built from connected data"
                                                        : "built from uploads")
    + (w.built_at ? ' · ' + _wkEsc(w.built_at) : '') + '</div></div>';

  h += '<div class="wk-grid">'
    + _wkCard("Total sales", _wkMoney(k.total_sales), "total_sales")
    + _wkCard("Sessions", _wkNum(k.sessions), "sessions")
    + _wkCard("Units", _wkNum(k.units), "units")
    + _wkCard("Unit session %", _wkPct(k.unit_session_pct), "unit_session_pct",
              "units per session, from the totals")
    + '</div>';

  h += '<div class="wk-grid">'
    + _wkCard("Ad spend", _wkMoney(k.ad_spend), "ad_spend")
    + _wkCard("Ad sales", _wkMoney(k.ad_sales), "ad_sales")
    + _wkCard("RoAS", _wkX(k.roas), "roas")
    + _wkCard("ACOS", _wkPct(k.acos), "acos")
    + _wkCard("TACOS", _wkPct(k.tacos), "tacos", "all spend ÷ all sales")
    + '</div>';

  h += '<div class="wk-grid">'
    + _wkCard("Impressions", _wkNum(k.ad_impressions), "ad_impressions")
    + _wkCard("Clicks", _wkNum(k.ad_clicks), "ad_clicks")
    + _wkCard("CTR", _wkPct(k.ctr), "ctr")
    + _wkCard("Ad orders", _wkNum(k.ad_orders), "ad_orders")
    + _wkCard("Ads CVR", _wkPct(k.ads_cvr), "ads_cvr")
    + _wkCard("CPC", _wkMoney(k.cpc), "cpc")
    // CPA is named in full because the sheet's history computed it a different
    // way and the row was not comparable.
    + _wkCard("CPA", _wkMoney(k.cpa), "cpa", "spend ÷ ad orders")
    + '</div>';

  // BRANDED vs NOT. Zero in every pack the spreadsheet ever produced, because
  // its SUMIF tested the campaign NAME against the literal text "br".
  h += '<div class="card" style="padding:0;overflow:hidden;margin:14px 0">'
    + '<div style="padding:11px 14px;border-bottom:1px solid var(--line)">'
    + '<b style="font-size:12.5px">Branded vs non-branded</b>'
    + '<span class="infodot" title="A campaign counts as branded when its NAME '
    + 'contains one of your brand terms. Paying to appear on your own name is '
    + 'defensive spend, and mixing it in makes a healthy-looking ACOS out of '
    + 'money that was never winning new customers.">i</span></div>';
  if(!(WK.brandTerms || []).length){
    h += '<div class="odp-note" style="padding:11px 14px">'
      + '<b>No brand terms are set</b>, so every campaign counts as '
      + 'non-branded. That is a setting, not a finding — add your brand words '
      + 'on the PPC screen and this splits properly.</div>';
  }
  h += '<table class="stk-table"><thead><tr><th></th>'
    + '<th class="r">Campaigns</th><th class="r">Spend</th>'
    + '<th class="r">Sales</th><th class="r">Orders</th><th class="r">RoAS</th>'
    + '</tr></thead><tbody>'
    + _wkSplitRow("Branded", k.br_campaigns, k.br_spend, k.br_sales, k.br_orders, k.br_roas)
    + _wkSplitRow("Non-branded", k.nb_campaigns, k.nb_spend, k.nb_sales, k.nb_orders, k.nb_roas)
    + '</tbody></table></div>';

  // NEW TO BRAND — from the campaign export, which really carries it. The sheet
  // summed a column that did not exist on the tab it pointed at, so this read 0
  // every week and looked like a measurement.
  h += '<div class="wk-grid">'
    + _wkCard("New-to-brand orders", _wkNum(k.ntb_orders), "ntb_orders")
    + _wkCard("New-to-brand sales", _wkMoney(k.ntb_sales), "ntb_sales")
    + _wkCard("Total spend", _wkMoney(k.total_spend), "total_spend",
              _wkManualNote(k))
    + '</div>';

  h += _wkProducts(w);
  h += _wkWeeksTable();
  host.innerHTML = h;
}

function _wkSplitRow(label, n, spend, sales, orders, roas){
  return '<tr><td><b>' + label + '</b></td>'
    + '<td class="r stk-num">' + _wkNum(n) + '</td>'
    + '<td class="r stk-num">' + _wkMoney(spend) + '</td>'
    + '<td class="r stk-num">' + _wkMoney(sales) + '</td>'
    + '<td class="r stk-num">' + _wkNum(orders) + '</td>'
    + '<td class="r stk-num"><b>' + _wkX(roas) + '</b></td></tr>';
}

/* Total spend is ad spend PLUS things Amazon does not report — DSP, giveaways,
   Meta. Absent means absent, and the card says which of them were counted so
   the total is never mistaken for the whole picture. */
function _wkManualNote(k){
  const missing = [];
  if(k.dsp_spend === null || k.dsp_spend === undefined) missing.push("DSP");
  if(k.giveaway_spend === null || k.giveaway_spend === undefined) missing.push("giveaways");
  if(k.meta_spend === null || k.meta_spend === undefined) missing.push("Meta");
  return missing.length
    ? "Amazon ads only — " + missing.join(", ") + " not entered"
    : "Amazon ads plus DSP, giveaways and Meta";
}

function _wkProducts(w){
  const p = w.products || [];
  if(!p.length) return "";
  let h = '<div class="card" style="padding:0;overflow:hidden;margin-bottom:14px">'
    + '<div style="padding:11px 14px;border-bottom:1px solid var(--line)">'
    + '<b style="font-size:12.5px">By product</b>'
    + '<span class="cc"> · ' + p.length + ' with data this week</span></div>'
    + '<table class="stk-table"><thead><tr>'
    + '<th>Product</th><th class="r">Units</th><th class="r">Sessions</th>'
    + '<th class="r">Conversion</th><th class="r">Units / day</th>'
    + '<th class="r">Sales</th></tr></thead><tbody>';
  p.forEach(function(r){
    h += '<tr><td><div class="stk-pname">'
      + '<div class="varfam-t">' + _wkEsc(r.title || r.child_asin) + '</div>'
      + '<div class="cc" style="font-size:10.5px">' + _wkEsc(r.child_asin)
      + (r.parent_asin && r.parent_asin !== r.child_asin
          ? ' · child of ' + _wkEsc(r.parent_asin) : '')
      + '</div></div></td>'
      + '<td class="r stk-num"><b>' + _wkNum(r.units) + '</b></td>'
      + '<td class="r stk-num">' + _wkNum(r.sessions) + '</td>'
      + '<td class="r stk-num">' + _wkPct(r.conversion, 1) + '</td>'
      + '<td class="r stk-num">' + _wkNum(r.units_per_day) + '</td>'
      + '<td class="r stk-num">' + _wkMoney(r.sales) + '</td></tr>';
  });
  return h + '</tbody></table></div>';
}

/* Every frozen week, so the history is visible rather than implied. */
function _wkWeeksTable(){
  const ws = WK.weeks || [];
  if(ws.length < 2) return "";
  let h = '<div class="card" style="padding:0;overflow:hidden">'
    + '<div style="padding:11px 14px;border-bottom:1px solid var(--line)">'
    + '<b style="font-size:12.5px">Every week</b>'
    + '<span class="infodot" title="Each week is frozen when it is built and '
    + 'never recomputed. That is what stops a change to the arithmetic quietly '
    + 'rewriting what was already reported.">i</span></div>'
    + '<table class="stk-table"><thead><tr><th>Week</th>'
    + '<th class="r">Sales</th><th class="r">Sessions</th><th class="r">Units</th>'
    + '<th class="r">Ad spend</th><th class="r">RoAS</th><th class="r">TACOS</th>'
    + '</tr></thead><tbody>';
  ws.forEach(function(w){
    const k = w.kpis || {};
    const on = WK.week && w.week_start === WK.week.week_start;
    h += '<tr' + (on ? ' style="background:rgba(45,212,168,.06)"' : '') + '>'
      + '<td>' + _wkEsc(_wkDate(w.week_start)) + '</td>'
      + '<td class="r stk-num">' + _wkMoney(k.total_sales) + '</td>'
      + '<td class="r stk-num">' + _wkNum(k.sessions) + '</td>'
      + '<td class="r stk-num">' + _wkNum(k.units) + '</td>'
      + '<td class="r stk-num">' + _wkMoney(k.ad_spend) + '</td>'
      + '<td class="r stk-num">' + _wkX(k.roas) + '</td>'
      + '<td class="r stk-num">' + _wkPct(k.tacos, 1) + '</td></tr>';
  });
  return h + '</tbody></table></div>';
}

function _wkDate(s){
  if(!s) return "—";
  try{
    return new Date(s + "T00:00:00").toLocaleDateString(undefined,
      {day: "numeric", month: "short", year: "numeric"});
  }catch(e){ return s; }
}

function _wkEmpty(){
  return '<div class="odp-note" style="padding:16px;border:1px dashed var(--line);'
    + 'border-radius:10px">'
    + '<b>Nothing built for this week yet.</b>'
    + '<div style="margin-top:8px;line-height:1.7">'
    + 'Two ways to fill it, and they produce exactly the same pack:'
    + '<div style="margin-top:7px"><b>1. Build from connected account</b> — uses '
    + 'the Sales &amp; Traffic data this app already syncs. No files. The '
    + 'advertising half needs the Amazon Advertising API, which is a separate '
    + 'login (Settings → Amazon Advertising credentials).</div>'
    + '<div style="margin-top:5px"><b>2. Upload the two reports</b> — the '
    + 'Business Report (Seller Central → Reports → Business Reports → Detail '
    + 'Page Sales and Traffic by Child Item) and the Campaign Manager export '
    + '(Campaign Manager → the campaign table → Export).</div>'
    + '<div class="cc" style="margin-top:8px">Either file can go in either '
    + 'upload button — the report is identified by its columns, not by which '
    + 'button you pressed.</div>'
    + '</div></div>';
}

/* ---- the export, in the shape of the sheet it feeds -----------------------
 *
 *   "The current Export button on Weekly KPIs downloads data in a single-column
 *    format. It must match the exact layout of this Google Sheet"
 *
 * WHAT IT USED TO DO: one week, as a vertical list of key/value pairs, from
 * whichever week was selected. The sheet it is meant to feed is the opposite
 * shape in every respect -- metrics down the side, weeks across the top, newest
 * first, every saved week present -- so you could not paste one into the other
 * and there was nothing to compare a week against.
 *
 * The layout is built SERVER-SIDE, in domain/weekly_grid.py, and this file only
 * asks for it. The CSV and the Google Sheet are then the same grid by
 * construction rather than by two implementations agreeing (rule 12) -- which
 * matters here more than usual, because the two are meant to be
 * interchangeable: paste the CSV or sync the sheet and get the same thing.
 */
function _wkGroup(){
  const el = document.getElementById("wk_group");
  return (el && el.value === "child") ? "child" : "parent";
}

function _wkQuery(){
  const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT) ? CUR_ACCOUNT.id : "";
  const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
  return "?id=" + encodeURIComponent(a) + "&marketplace=" + encodeURIComponent(m)
       + "&group=" + encodeURIComponent(_wkGroup());
}

/* Every saved week, in the sheet's layout. A plain navigation would show a JSON
   error page when there is nothing to export, so the reply is sniffed first. */
async function weeklyExport(){
  try{
    const r = await fetch("/weekly/export.csv" + _wkQuery());
    const type = r.headers.get("content-type") || "";
    if(!r.ok || type.indexOf("json") >= 0){
      const j = await r.json().catch(function(){ return null; });
      toast((j && j.error) || "Could not build the export");
      return;
    }
    const blob = await r.blob();
    const name = (r.headers.get("content-disposition") || "")
      .replace(/.*filename="?([^"]+)"?.*/, "$1") || "weekly-kpis.csv";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function(){ URL.revokeObjectURL(a.href); }, 4000);
    toast("Exported every saved week, newest column first.");
  }catch(e){ toast(String(e)); }
}

/* Write the same grid into this account's weekly Google Sheet.
 *
 * TWO PRESSES, ON PURPOSE. The first is a dry run: the server reports which
 * sheet, which tab, and how many rows and columns it would write, and writes
 * nothing. The second does it. Writing over somebody's live sheet cannot be
 * undone from in here, and a button that does it on the first click is a button
 * that eventually does it by accident. */
let _WK_PENDING = null;

async function weeklySheetSync(){
  const out = document.getElementById("wk_sheetmsg");
  const say = function(html, cls){
    if(out) out.innerHTML = '<div class="' + (cls || "cc")
      + '" style="font-size:11.5px;margin-top:6px">' + html + '</div>';
  };
  const confirmNow = !!_WK_PENDING;
  say('<span class="genspin"></span> ' + (confirmNow ? "Writing\u2026" : "Checking\u2026"));
  try{
    const r = await fetch("/weekly/sheet" + _wkQuery(), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({group: _wkGroup(), confirm: confirmNow})});
    const j = await r.json();
    if(!j || !j.ok){
      _WK_PENDING = null;
      say(esc((j && j.error) || "Could not write the sheet"), "db-warn-red");
      return;
    }
    if(j.dry_run){
      _WK_PENDING = true;
      say('<b>Nothing written yet.</b> ' + esc(j.note || "")
          + '<div style="margin-top:6px">' + esc(j.br_means || "") + '</div>'
          + '<div style="margin-top:8px">'
          + '<button class="db-chip btn-primary" onclick="weeklySheetSync()">'
          + 'Yes, write it</button> '
          + '<button class="db-chip" onclick="weeklySheetCancel()">Cancel</button>'
          + '</div>', "db-warn-amber");
      return;
    }
    _WK_PENDING = null;
    say('<b>Done.</b> ' + esc(j.note || "")
        + (j.url ? ' <a href="' + esc(j.url) + '" target="_blank" '
                   + 'rel="noopener">Open the sheet</a>' : ''), "db-warn-green");
    toast("Weekly KPIs written to the sheet.");
  }catch(e){
    _WK_PENDING = null;
    say(esc(String(e)), "db-warn-red");
  }
}

function weeklySheetCancel(){
  _WK_PENDING = null;
  const out = document.getElementById("wk_sheetmsg");
  if(out) out.innerHTML = "";
}
