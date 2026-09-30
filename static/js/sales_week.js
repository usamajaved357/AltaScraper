// static/js/sales_week.js -- Week to Date: its card, series and ad footer. Moved word for word out of sales.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* ---- week to date ------------------------------------------------------
 * The second of Orbit's two "how is it going right now" cards: the start of
 * this week to today, drawn against the same days of the week before.
 *
 * WHICH DAY THE WEEK STARTS ON is SALES_WEEK_START and nothing here decides it
 * again -- Sunday, to agree with Orbit and with Amazon's own reports.
 *
 * Built from a request of its own rather than sliced out of the main range,
 * because the main range is whatever the user last picked -- on a 90-day view
 * there would be no "this week" in it to slice, and on a custom range there
 * might be no week boundary in it at all.
 */
// WHICH REVENUE METRIC BOTH WEEKS WILL BE DRAWN FROM.
//
// net_revenue is the better number -- it is after Amazon's fees -- but it is
// often unknown for recent days, and a line of nulls draws nothing. ordered_sales
// is coarser and more complete. So: count how many cells each one actually KNOWS
// across the two weeks, and take the better-known. Ties go to net_revenue,
// because when both are equally known it is the truer figure.
//
// Chosen ONCE and used for both series, so the solid line and the dashed line
// are always the same quantity.
/* The ad footer under the week card, from the figures the page already has.
 *
 * THREE DIFFERENT ANSWERS, AND ONLY ONE OF THEM IS "not connected".
 *
 *   spend in the window   -> print it, with TACOS beside it
 *   connected, no spend   -> say the account ran no advertising in these dates,
 *                            which is a measurement and not a gap
 *   no advertising login  -> say THAT, and that it is a separate login
 *
 * The old footer said the third thing unconditionally. It was written when no
 * account had a login and was never revisited when one did, so an account
 * spending real money was told its spend did not exist.
 */
function _sAdFooter(j, whenLabel){
  const cells = function(k){
    const m = ((j && j.metrics) || []).filter(function(x){
      return x.key === k; })[0];
    return (m && m.cells) ? m.cells.filter(function(v){
      return v !== null && v !== undefined; }) : [];
  };
  const spend = cells("spend");
  const conn = (j && j.ads) || {};

  if(!spend.length){
    // conn.ok === false is the ONLY "not connected". A connected account with
    // no spend rows, and an unknown connection state, are "none" -- see the
    // three answers above.
    const why = (conn.ok === false)
      ? ("not connected — advertising needs its own Amazon login, separate "
         + "from the selling one")
      : ("no advertising ran " + whenLabel);
    return '<div class="adfooter">'
      + '<span class="lbl">Ad spend ' + _sEsc(whenLabel) + '</span> '
      + '<b>' + _sEsc(conn.ok === false ? "not connected" : "none") + '</b>'
      + '<span style="color:var(--as-lit-9ca3af-fg)"> — ' + _sEsc(why) + '.</span>'
      + '</div>';
  }

  const total = spend.reduce(function(a, b){ return a + Number(b); }, 0);
  // TACOS IS RECOMPUTED OVER THE WHOLE WEEK, not averaged across its days: a
  // quiet Sunday with an odd ratio would otherwise weigh the same as a busy
  // Monday, and the figure would stop matching what was actually spent.
  const sales = cells("ordered_sales").reduce(function(a, b){
    return a + Number(b); }, 0);
  const tacos = sales ? (100 * total / sales) : null;
  // THE SHARED SYMBOL TABLE (money.js curSymbol, Rule 12). This had its own
  // three-way guess that printed £ for anything not USD/EUR -- SEK, PLN, CAD
  // and a reply with no currency all read as pounds.
  const cur = (j && j.currency) || "";
  const sym = (typeof curSymbol === "function") ? curSymbol(cur)
            : (_sCur(cur) || (cur ? cur + " " : ""));
  return '<div class="adfooter">'
    + '<span class="lbl">Ad spend ' + _sEsc(whenLabel) + '</span> <b>'
    + sym + total.toFixed(2) + '</b>'
    + '<span class="lbl" style="margin-left:8px">Tacos</span> <b>'
    + (tacos === null
       ? '<span title="No sales in this window, so there is nothing to divide '
         + 'the spend by. That is not a TACOS of nought.">—</span>'
       : tacos.toFixed(1) + '%') + '</b>'
    + '</div>';
}


function _sWeekMetric(now, before){
  const known = function(j, k){
    const m = ((j && j.metrics) || []).filter(function(x){ return x.key === k; })[0];
    if(!m || !m.cells) return -1;                 // absent, not merely unknown
    return m.cells.filter(function(v){
      return v !== null && v !== undefined; }).length;
  };
  const nNet = known(now, "net_revenue") + known(before, "net_revenue");
  const nOrd = known(now, "ordered_sales") + known(before, "ordered_sales");
  return (nOrd > nNet) ? "ordered_sales" : "net_revenue";
}

// One week's cells for that metric, padded to the week's own column count.
//
// A week that traded nothing is a FACT and gets a flat line along the bottom;
// only a week with no columns at all has nothing to draw. Nulls stay null: a day
// Amazon has not delivered is shaded by the chart, and turning it into a zero
// would draw a sale of nothing on a day nobody has reported on.
function _sWeekSeries(j, wantKey){
  const n = ((j && j.columns) || []).length;
  if(!n) return null;
  const m = ((j.metrics) || []).filter(function(x){ return x.key === wantKey; })[0];
  if(!m) return null;
  return {key: m.key, label: m.label,
          cells: (m.cells && m.cells.length === n) ? m.cells
                                                  : new Array(n).fill(0)};
}

async function salesLoadWeek(){
  const host = document.getElementById("sales_week");
  const badge = document.getElementById("sales_week_delta");
  if(!host) return;
  const today = new Date();
  // WHICH DAY THE WEEK STARTS ON, in one place.
  //
  // Asked for as Monday: "Week start Monday". Then measured against the thing
  // being matched: "on orbit there is sales data displayed, and it starts from
  // sunday and ends at saturday". Amazon's own reports run Sunday to Saturday
  // too, so a card meant to be read beside Orbit has to agree with it -- a
  // week-on-week comparison against a week offset by a day is not a comparison.
  //
  // SALES_WEEK_START is the only place this is decided: 0 = Sunday, 1 = Monday.
  // Change this one number and the window, the comparison week, the axis labels
  // and the card's subtitle all follow, because they all read it from here.
  // THE BROWSER'S OWN DAY, not UTC's. getUTC* and toISOString() put "today"
  // on Greenwich time, so between midnight and 01:00 in a UK summer (and all
  // evening for a US viewer) the card asked for the wrong day and, on the
  // week's first day, the wrong week. Dates are built from the local calendar
  // and written out from it; the Date objects below are pinned to UTC midnight
  // of that local day only so the day arithmetic has no DST hour in it.
  const dow = (today.getDay() - SALES_WEEK_START + 7) % 7;
  const todayU = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()));
  const wkStart = new Date(Date.UTC(today.getFullYear(), today.getMonth(),
                                today.getDate() - dow));
  const prevStart = new Date(wkStart.getTime() - 7 * 86400000);
  const prevEnd2 = new Date(wkStart.getTime() - 86400000);
  const iso = d => d.toISOString().slice(0, 10);   // of a UTC-midnight local day
  const base = function(a, b){
    const q = ["preset=custom", "start=" + iso(a), "end=" + iso(b), "granularity=day"];
    if(SALES.asin) q.push("asin=" + encodeURIComponent(SALES.asin));
    if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
      q.push("marketplace=" + encodeURIComponent(WS_MARKET));
    return q.join("&");
  };
  host.innerHTML = '<div class="cc" style="padding:14px;font-size:12px">Loading…</div>';
  let now, before;
  // Newest load wins (see salesReload): a week reply for a load that has been
  // overtaken is not painted.
  const tk = SALES.loadSeq;
  try{
    now    = await _sFetch("/sales/series?" + base(wkStart, todayU));
    before = await _sFetch("/sales/series?" + base(prevStart, prevEnd2));
    if(now === null || before === null) return;
  }catch(e){
    if(tk !== SALES.loadSeq) return;
    // THE SAME ERROR CARD AS LIVE SALES, which says whether Amazon refused,
    // throttled or the request broke -- not a bare "could not load".
    _sCardError(host, (e && e.message) || e, "This week");
    return;
  }
  if(tk !== SALES.loadSeq) return;
  // A REFUSAL IS SAID, not drawn as an empty card. `!now.ok` used to blank
  // the panel, which reads as a week with nothing in it.
  if(!now || !now.ok){
    _sCardError(host, (now && now.error) || "no reply", "This week");
    return;
  }
  // Kept so the Live Sales footer, which is drawn from a different call, can say
  // whether advertising is connected without asking again.
  SALES._lastSeries = now;

  // THE CHART IS ALWAYS DRAWN, INCLUDING A WEEK WITH NO SALES IN IT.
  //
  // "week to date graph is shown as empty to me on jack reacherd" and then
  // "even i dont have any sales the graph should be displayed".
  //
  // It was replaced by the sentence "Nothing recorded for this week yet" the
  // moment no metric had a non-zero cell -- so a quiet week produced no chart at
  // all, which reads as a broken card rather than as a quiet week. A flat line
  // along zero says "nothing sold" and looks like a working app; a paragraph
  // where a chart should be does not.
  //
  // On jack_uk the window was Sunday 16 August to Monday 17 August with nothing
  // sold on either -- correct, and it should have drawn two points at zero.
  //
  // `mNow` is now only used to decide what to SAY under the chart, never whether
  // to draw one.
  // ONE METRIC FOR BOTH WEEKS, chosen once from both replies together.
  //
  // This is the rest of "the dotted lines are not accurately representing last
  // week data", and it is worse than a missing line. Each week picked its own
  // metric independently: `key()` returns net_revenue when it has any non-zero
  // cell, else ordered_sales. MEASURED on jack_uk, week of 16 August:
  //
  //   this week  net_revenue   [0.0, null]                      <- all unknown
  //              ordered_sales [0.0, 0.0]                       <- known zeros
  //   last week  net_revenue   [null,null,null,null,null,85.17,null]
  //              ordered_sales [0,0,0,0,0,102.21,0]
  //
  // So this week could end up drawn as ordered_sales and last week as
  // net_revenue -- a solid line of one quantity against a dashed line of a
  // different one, on the same axis, labelled This Week and Last Week. The two
  // are not comparable: net_revenue is after Amazon's fees and ordered_sales is
  // before them, so the dashed line would sit below the solid one for no reason
  // but the arithmetic.
  //
  // Now: whichever metric is best known ACROSS BOTH weeks wins, and both series
  // are read from it. A comparison has to be of like with like or it is not a
  // comparison.
  const wkKey = _sWeekMetric(now, before);
  const mNow = _sWeekSeries(now, wkKey);
  const mBefore = _sWeekSeries(before, wkKey);

  const cols = now.columns || [];
  const pts = cols.map(function(d, i){ return {label: d, value: mNow ? mNow.cells[i] : null}; });
  let cmp = null;
  if(mBefore && (before.columns||[]).length){
    // PAIRED BY DATE, SEVEN DAYS BACK -- not by position in the array.
    //
    // Both weeks start on the same weekday, so position pairing is right
    // whenever both replies carry every day. They do not always: a reply
    // carries only the buckets it has figures for, and the main chart already
    // had to be fixed for exactly this (see compareOffsetDays, "a 30-day
    // request came back with 28 columns for this period and 1 for the period
    // before"). Position-paired, last Friday's takings would be drawn under
    // this Sunday and labelled Last Week.
    //
    // Same rule as the main chart now: subtract seven days from the date and
    // look it up. A day the week before has no figure for is a gap, which the
    // chart shades, rather than somebody else's number.
    const was = {};
    (before.columns || []).forEach(function(d, i){ was[d] = mBefore.cells[i]; });
    cmp = cols.map(function(d){
      const dt = new Date(String(d) + "T00:00:00Z");
      if(isNaN(dt)) return {label: "", value: null};
      const back = new Date(dt.getTime() - 7 * 86400000).toISOString().slice(0, 10);
      return {label: back, value: (back in was) ? was[back] : null};
    });
    // KNOWN, not non-zero. Dropping the line when last week was quiet is what
    // made the comparison look broken -- see anyKnown in salesDrawCharts. A week
    // that took nothing is drawn along the bottom; only a week with no figures
    // at all has no line.
    if(!cmp.some(function(p){ return p.value !== null && p.value !== undefined; })) cmp = null;
  }

  // A WEEK IS SEVEN BUCKETS, NOT SEVEN INSTANTS, so the points sit at the middle
  // of each day's band and are captioned by day name -- Sun, Mon, Tue … -- which
  // is what Orbit's Week to Date x-axis reads (measured: seven labels at 106.4
  // through 603.6, one per band centre). Ours read "Aug 9 … Aug 15": the same
  // information in the form you would use to file it rather than to say it, and
  // on a chart of one week the date adds nothing the title has not said.
  const wkOpts = {
    title: "", kind: "money", color: "#3b82f6", id: "sales_week_chart",
    currency: (now && now.currency),
    // The card's own width, so the chart is drawn at 1:1 and keeps its 200px
    // height at every screen size -- which is what Orbit does. See
    // scChartWidth: with height:auto a 340px phone got a 102px-tall chart.
    width: scChartWidth("sales_week", 665),
    height: 200, compare: cmp, scale: "band", xLabel: "dow",
    compact: true, thisLabel: "This Week", compareLabel: "Last Week",
    // Named for the days actually DRAWN. Last week is fetched Monday to Sunday,
    // but the dashed line is aligned by position against this week's columns, so
    // on a partial week it stops where this week stops -- and saying it runs to
    // Sunday describes a line that is not on the chart.
    compareTitle: cmp
      ? ("the dashed line is " + (cmp[0] ? cmp[0].label : iso(prevStart)) + " to "
         + (cmp[cmp.length - 1] ? cmp[cmp.length - 1].label : iso(prevEnd2)))
      : ""};
  // Remembered so a window resize can REDRAW at the new width without fetching
  // the week again. A chart drawn at a fixed pixel width has to be redrawn when
  // that width changes, or turning a phone sideways letterboxes it.
  SALES._weekDraw = function(){
    wkOpts.width = scChartWidth("sales_week", 665);
    host.innerHTML = _wkStrip + salesChart(pts, wkOpts) + SALES._weekFoot;
  };
  /* THIS WEEK IN NUMBERS, above the chart -- the same strip Live Sales has.
   *
   *     "the weekly graph is smaller than the daily graph"
   *
   * Measured: the two charts are IDENTICAL, 579x200 with a 559x160 plot area
   * and seven gridlines each. What differs is the box around them. Live Sales
   * carries a revenue/orders/units strip, so its chart starts 164px down a
   * 429px panel and there is 65px under it. Week to Date has no strip, so its
   * chart starts at 72px and leaves 145px of nothing below -- a smaller-looking
   * chart floating in an emptier box, side by side with a full one.
   *
   * Filled with the figures rather than by stretching the chart, because the
   * question the card raises -- "how much this week, then?" -- had only a
   * percentage badge in the corner to answer it. Every number here is summed
   * from the reply already fetched; nothing new is asked of the server.
   *
   * The comparison is like for like: last week's SAME DAYS, not its whole week.
   * A Tuesday-to-date against a full Monday-to-Sunday would report a fall every
   * time, which is what "down 40%" would mean on a Tuesday morning.
   */
  const _wkSum = function(series, upto){
    if(!series || !series.cells) return null;
    let any = false, tot = 0;
    series.cells.slice(0, upto === undefined ? series.cells.length : upto)
      .forEach(function(v){
        if(v === null || v === undefined) return;
        any = true; tot += Number(v) || 0;
      });
    return any ? tot : null;
  };
  const _wkPct = function(now_, was_){
    if(now_ === null || was_ === null || !was_) return null;
    return ((now_ - was_) / Math.abs(was_)) * 100;
  };
  const _wkCur = (now && now.currency) || "";
  const _wkDays = cols.length;
  const _wkBit = function(label, key, kind){
    const a = _wkSum(_sWeekSeries(now, key));
    // Last week, cut to the same number of days this week has so far.
    const b = _wkSum(_sWeekSeries(before, key), _wkDays);
    if(a === null) return "";
    const p = _wkPct(a, b);
    const arrow = (p === null) ? ""
      : ' <span class="' + (p >= 0 ? "good" : "bad") + '">'
        + (p >= 0 ? "↑" : "↓") + Math.abs(p).toFixed(1) + '%</span>';
    return '<span class="todaybit"><b>' + _sEsc(_sNum(a, kind, _wkCur)) + '</b>'
         + arrow + ' <span class="cc">' + _sEsc(label) + '</span></span>';
  };
  const _wkStrip = '<div class="todaystrip">'
    + _wkBit("revenue", wkKey, "money")
    + _wkBit("orders", "orders", "count")
    + _wkBit("units", "units", "count")
    + '<span class="cc todaynote">' + _wkDays + ' day'
    + (_wkDays === 1 ? "" : "s") + ' so far'
    + (cmp ? ' · vs the same days last week' : '') + '</span></div>';

  host.innerHTML = _wkStrip + salesChart(pts, wkOpts);

  // The key goes in the card's HEADER, which is where Orbit has it -- "This
  // Week", "Last Week", then the change badge, all on the title's own line.
  // It used to sit between the header and the chart, pushing the chart down and
  // giving the card a band of small print Orbit does not have.
  const wkey = document.getElementById("sales_week_key");
  if(wkey) wkey.innerHTML = salesChartKey(wkOpts);

  // The missing days still have to be explained -- the shaded block on the right
  // is the days Amazon has not delivered, and unexplained it reads as a fault.
  // It goes under the subtitle rather than over the chart.
  const wnote = document.getElementById("sales_week_note");
  if(wnote){
    const gaps = pts.filter(function(p){
      return p.value === null || p.value === undefined; }).length;
    wnote.className = "panelnote warn";
    wnote.textContent = gaps
      ? ("· " + gaps + " day" + (gaps === 1 ? "" : "s")
         + " not in from Amazon yet — shaded, not zero")
      : "";
  }

  // ORBIT'S WEEK CARD HAS AN AD FOOTER TOO -- measured: "Ad spend this week
  // $10,633 · TACOS 9.8%", the label at 10px and the figure at 12px.
  //
  // THIS USED TO READ "not connected" ALWAYS, as a hard-coded string. It was
  // written when no account here had an Advertising login and it stayed that
  // way after one did -- so an account with real spend and a real TACOS was
  // told neither figure existed, on the card where they matter most.
  SALES._weekFoot = _sAdFooter(now, "this week");
  host.innerHTML += SALES._weekFoot;

  // THE SAME DAYS, WHICH IS WHAT THE CHIP SAYS IT IS COMPARING.
  //
  // This week runs Monday to TODAY; last week is fetched Monday to Sunday so the
  // dashed line has somewhere to come from. The chip summed both in full -- a
  // partial week against a whole one -- so on a Wednesday it reported roughly
  // -57% on trade that had not moved at all, and its own tooltip said "against
  // the same days last week" while doing it.
  //
  // Week to Date is a CALENDAR week, SALES_WEEK_START (Sunday) to today. Its comparison has to be
  // the same slice of the week before, not the whole of it.
  if(badge){
    const cellsOf = function(m){ return (m ? (m.cells || []) : []); };
    const daysSoFar = cellsOf(mNow).length;
    const sum = function(cells){
      return cells.reduce(function(a, v){ return a + (Number(v) || 0); }, 0);
    };
    const a = sum(cellsOf(mNow));
    const b = sum(cellsOf(mBefore).slice(0, daysSoFar));
    if(!b){ badge.innerHTML = ""; }
    else badge.innerHTML = _sBadge(((a - b) / Math.abs(b)) * 100,
      {title: "against the same " + daysSoFar + " day"
              + (daysSoFar === 1 ? "" : "s") + " of last week"});
  }
}
