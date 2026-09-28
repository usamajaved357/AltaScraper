// static/js/sales_live.js -- Live Sales today, hourly, the range label, resizing and the profit card. Moved word for word out of sales.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

function salesDrawRange(sum, av){
  const el=document.getElementById("sales_range");
  if(!el) return;
  if(!sum || !sum.ok){ el.textContent=""; return; }
  const a=(av&&av.sales)||{};
  let t = sum.start+" to "+sum.end;
  if(a.last_date) t += " · Amazon has data to "+a.last_date;
  // AND WHERE IT STARTS, when you have asked for more than there is.
  //
  // Reported as "the sales report and p&l heatmap do not show data beyond 27th
  // july no matter if i select 30 day, 60d or 90d". Nestwell Goods has nothing
  // before 27 July -- checked against Amazon, which returns a genuine zero for
  // 10 July -- so 30, 60 and 90 days really are the same figures. The screen
  // said none of that: it drew the extra weeks as empty columns, which reads
  // as the app failing to load them rather than as an account that was not
  // trading yet.
  // Short, for the same reason as the grid's own note: the figures say it.
  if(a.first_date && sum.start && sum.start < a.first_date){
    t += " · trading from " + a.first_date;
  }
  el.textContent=t;
}

/* ---- today so far ------------------------------------------------------
 * Kept visually apart from the grid, because it is a DIFFERENT measurement:
 * orders counted as they are placed, not as Amazon finally settled them. It will
 * not tie out to the grid and is not meant to, so it says where it came from and
 * what it is being compared against.
 */
async function salesLoadToday(){
  const el=document.getElementById("sales_today");
  if(!el) return;
  try{
    // _sScope(), not _sQuery(): "today so far" is today whatever period is set.
    const j=await _sFetch("/sales/today?"+_sScope());
    if(j === null) return;   // the workspace moved on while this was in flight
    // NOT BLANKED. See _sCardError: measured on sheelady_us, this call answers
    // 502 because Amazon refuses the account's app the Orders data, and the
    // card simply disappeared -- which reads as "no sales today" rather than
    // "Amazon would not tell us".
    if(!j || !j.ok){ _sCardError(el, (j && j.error) || "", "Live Sales"); return; }
    const t=j.today||{}, y=j.yesterday||null, d=j.delta_pct||{};
    const cur=t.currency||"";
    function bit(label, v, kind, key){
      const dp=d[key];
      const arrow = (dp===null||dp===undefined) ? "" :
        ' <span class="'+(dp>=0?"good":"bad")+'">'+(dp>=0?"↑":"↓")+Math.abs(dp).toFixed(1)+'%</span>';
      return '<span class="todaybit"><b>'+_sEsc(_sNum(v,kind,cur))+'</b>'+arrow
           + ' <span class="cc">'+_sEsc(label)+'</span></span>';
    }
    let extra="";
    if(t.pending) extra += ' · '+t.pending+' pending (no value yet)';
    if(j.truncated) extra += ' · partial — very busy day';
    el.innerHTML = '<div class="todaystrip">'
      + bit("revenue", t.revenue, "money", "revenue")
      + bit("orders", t.orders, "count", "orders")
      + bit("units", t.units, "count", "units")
      + '<span class="cc todaynote">live from orders'
      + (y ? ' · vs '+_sEsc(j.compared_to||"the same time yesterday") : "")
      + _sEsc(extra) + '</span></div>'
      + '<div id="sales_hourly"></div>';
    // The curve underneath, which is the shape Orbit's Live Sales card is.
    salesLoadHourly().catch(function(){});
  }catch(e){ _sCardError(el, String(e), "Live Sales"); }
}

/* A CARD THAT COULD NOT LOAD SAYS SO.
 *
 * Found by driving the live app: /sales/today answers 502 on sheelady_us,
 * because Amazon refuses it -- "Unauthorized: Access to requested resource is
 * denied", which is an SP-API role the app registration has not been granted.
 * The three UK accounts answer 200 on the same call, so it is that account's
 * authorisation and not this code.
 *
 * What the screen did with that was blank the card. An empty region reads as a
 * design that forgot something, or as "no sales", and neither is true -- the
 * figure was refused, which is a different fact and the only one that tells you
 * what to go and fix.
 *
 * Amazon's own words are shown, because the fix is in Seller Central and the
 * message is what identifies which permission is missing.
 */
function _sCardError(el, err, what){
  if(!el) return;
  const raw = String(err || "").trim();
  const denied = /unauthor|forbidden|access to requested resource/i.test(raw);
  // A QUOTA REFUSAL IS NOT A FAULT, and showing Amazon's raw dict for it --
  // "[{'code': 'QuotaExceeded', ...}]" -- reads as something broken. Amazon
  // limits how often it will answer; the figures are fine and the next attempt
  // will get them. Said in those words, because "the request failed" beside a
  // machine error is the most alarming way to describe waiting.
  const throttled = /quotaexceeded|throttl|too many requests|429/i.test(raw);
  el.innerHTML = '<div class="ri-samplebar" style="margin:0">'
    + '<b>' + _sEsc(what) + (throttled ? ' is waiting on Amazon.' : ' could not be loaded.') + '</b> '
    + (throttled
        ? 'Amazon limits how often it will answer this, and that limit has been '
          + 'reached for the moment. Nothing is wrong with your figures — this '
          + 'card fills itself in as soon as Amazon allows, usually within a '
          + 'minute or two.'
        : denied
        // THE THIRD COPY OF ONE SENTENCE, and the three did not agree.
        //
        // This one said "re-authorise it in Seller Central with the role that
        // covers it" -- singular, and measurably wrong about the size of it:
        // Diagnose SP-API on jack_uk/UK returns 403 [ROLE] for marketplace
        // participation, Catalog Items, Product Pricing and Product Definitions
        // at once. Sending somebody after "the role" has them fix one and meet
        // the next refusal. The A+ note and marketplace_health.explain() both
        // point at the diagnostic instead; this now says the same thing, because
        // one fact should not have three wordings (CLAUDE.md Rule 12).
        ? 'Amazon refused the request: this account\'s Amazon app is not '
          + 'authorised for the data this card needs. Press "Diagnose SP-API" '
          + 'on the listings page — it checks each Amazon permission in turn '
          + 'and lists the ones that are missing, which is usually more than one.'
        : 'The request failed.')
    // Amazon's own words are kept for the cases where they help someone act.
    // On a quota refusal they do not: the message is machine noise and the
    // advice above is the whole of what can be done.
    + ((raw && !throttled)
        ? '<div class="cc" style="margin-top:6px;font-size:11px;'
          + 'font-family:ui-monospace,monospace">' + _sEsc(raw.slice(0, 220))
          + '</div>' : "")
    + '</div>';
}

/* THE CHANGE BADGE -- "↑ 16.9 %" -- built in ONE place.
 *
 * Rule 12: this was written out three times, on the Live Sales card, on the Week
 * to Date card and on every stat card, and the three had already drifted -- two
 * of them put no space before the % and the third added a sign the others did
 * not. Orbit's is one component and reads the same everywhere.
 *
 * MEASURED off Orbit's own badges: "↑ 16.9 %" and "↓ 0.4 %" -- a space after the
 * arrow AND a space before the per-cent sign, at 12px weight 500.
 *
 * `sign` is for the stat cards, which show "↑ +5.2 %" against a named previous
 * figure; the two top cards show the arrow alone. `zero` is the flat case, which
 * gets an arrow that means neither up nor down rather than an up-arrow on a
 * change of nothing.
 */
function _sBadge(pct, opts){
  const o = opts || {};
  if(pct === null || pct === undefined || !isFinite(Number(pct))) return "";
  const n = Number(pct);
  const flat = (n === 0);
  const up = n > 0;
  const cls = flat ? "flat" : (up ? "up" : "down");
  const arrow = flat ? "→" : (up ? "↑" : "↓");
  const sign = (!o.sign || flat) ? "" : (up ? "+" : "−");
  return '<span class="pct-badge ' + cls + '"'
       + (o.title ? ' title="' + _sEsc(o.title) + '"' : "")
       + '>' + arrow + " " + sign + Math.abs(n).toFixed(1) + " %</span>";
}

/* "Pacific Time (PDT) · 7:20 PM" -- the marketplace's zone in words and its own
 * current time, which is what Orbit shows on the Live Sales header.
 *
 * Both come from Intl, so the zone name is whatever the browser calls it rather
 * than a table this app would have to keep. If the zone is one Intl does not
 * know, the identifier itself is shown: a name that is merely unfriendly beats
 * a card that silently drops which day it is talking about. */
function _sClock(tz){
  if(!tz) return "";
  const now = new Date();
  // en-US for the ZONE NAME, because that is the only locale that gives the
  // abbreviation Orbit shows: en-GB renders America/Los_Angeles as "GMT-7" where
  // en-US renders it "PDT". The TIME below stays on the app's own locale.
  const zone = function(style){
    try{
      const p = new Intl.DateTimeFormat("en-US", {timeZone: tz, timeZoneName: style})
        .formatToParts(now).filter(function(x){ return x.type === "timeZoneName"; });
      return p.length ? p[0].value : "";
    }catch(e){ return ""; }
  };
  // ORBIT'S EXACT FORM, read off its live header: "Pacific Time (PDT) • 7:20 PM"
  // -- the generic name, the current abbreviation in brackets, a middle dot, the
  // time. Ours was "Pacific Time: 5:17 PM", which is the same fact punctuated
  // differently.
  //
  // The brackets are dropped when they would only repeat the name, and the whole
  // thing falls back to the abbreviation when the generic name is long: "United
  // Kingdom Time (GMT+1)" is 27 characters and pushes the change badge onto a
  // second line, and a header that reflows is worse than an abbreviation.
  const generic = zone("longGeneric");
  const shortz = zone("short");
  let name = generic;
  if(name && shortz && shortz !== name && !/^GMT/.test(shortz)) name += " (" + shortz + ")";
  if(!name || name.length > 20) name = shortz || generic || tz;
  let time = "";
  try{
    time = new Intl.DateTimeFormat("en-GB", {timeZone: tz, hour: "numeric",
      minute: "2-digit", hour12: true}).format(now).toUpperCase();
  }catch(e){ return _sEsc(name); }
  return '<span class="cc">' + _sEsc(name) + ' &middot; </span>' + _sEsc(time);
}

/* ---- the hourly curve --------------------------------------------------
 * Orbit's Live Sales card: today climbing across the day in gold, yesterday
 * running the full 24 hours behind it in grey dashes, so "am I ahead of
 * yesterday" is answered by which line is higher at the same hour.
 *
 * Built from order timestamps, which the app already pulls -- see
 * domain/hourly_sales.py for why this is a different measurement from
 * everything on the settled report below, and why the card says so.
 */
async function salesLoadHourly(){
  const el = document.getElementById("sales_hourly");
  const badge = document.getElementById("sales_today_delta");
  if(!el) return;
  let j;
  try{
    // _sScope(), not _sQuery(): the curve is always today against yesterday.
    j = await _sFetch("/sales/hourly?" + _sScope());
    if(j === null) return;
  }catch(e){ return; }
  if(!j || !j.ok || !(j.hours || []).length) return;

  // Midnight, 3am, 6am … as Orbit labels them, rather than 00:00..23:00.
  const label = function(h){
    const n = Number(String(h).slice(0, 2));
    const ampm = n < 12 ? "AM" : "PM";
    const hh = (n % 12) === 0 ? 12 : (n % 12);
    return hh + " " + ampm;
  };
  const pts = (j.hours || []).map(function(h, i){
    return {label: label(h), value: (j.today || [])[i]};
  });
  const cmp = (j.yesterday || []).map(function(v, i){
    return {label: label((j.hours || [])[i]), value: v};
  });

  // The strip along the bottom of Orbit's card is AD SPEND TODAY and TACOS.
  //
  // THIS ONE STAYS BLANK EVEN ON A CONNECTED ACCOUNT, and for a better reason
  // than the one it used to give. Amazon does not report advertising for the
  // current day: measured on nestwell_goods on 6 Sep, the newest advertising day
  // stored was 4 Sep. There is no such figure as today's ad spend, so printing
  // one -- or a nought -- would be inventing it. What CAN be said is why, and
  // where the real number lives.
  //
  // The old text blamed a missing connection. That was true when it was written
  // and is now wrong for the one account that has spend, which would have read
  // "not connected" beside a live campaign list.
  const _liveConn = (SALES._lastSeries && SALES._lastSeries.ads) || {};
  const adsFoot = '<div class="adfooter">'
    + '<span class="lbl">Ad spend today</span> <b>—</b>'
    + '<span style="color:rgb(156,163,175)"> — '
    + (_liveConn.ok === false
       ? 'advertising needs its own Amazon login, separate from the selling one'
       : 'Amazon reports advertising about two days behind, so there is no '
         + 'figure for today yet. The latest complete day is on PPC Analytics')
    + '.</span></div>';

  // A POINT SCALE here, not a band: these are readings across a continuous day,
  // and midnight IS the start of the axis. Measured on Orbit's Live Sales: 24
  // hourly points from x=65 (on the y-axis) to x=645 (the right edge), labelled
  // every third hour.
  const hrOpts = {
    title: "", kind: "money", color: "#fbbf24", id: "sales_hourly_chart",
    currency: (j && j.currency),
    width: scChartWidth("sales_hourly", 665),
    height: 200, compare: cmp, scale: "point",
    compact: true, thisLabel: "Today", compareLabel: "Yesterday"};
  SALES._hourlyDraw = function(){
    hrOpts.width = scChartWidth("sales_hourly", 665);
    el.innerHTML = salesChart(pts, hrOpts) + adsFoot;
  };
  el.innerHTML = salesChart(pts, hrOpts) + adsFoot;

  const hkey = document.getElementById("sales_today_key");
  if(hkey) hkey.innerHTML = salesChartKey(hrOpts);

  // WHICH CLOCK "today" IS ON, in the header where Orbit puts it -- measured:
  // "Pacific Time (PDT): 5:14 PM", the zone named in words and the marketplace's
  // own current time beside it. Ours had the IANA identifier in a subtitle under
  // the chart, which is the same fact written for a machine.
  //
  // It matters more here than it does for Orbit: this app is run from Pakistan
  // against UK and US stores, so "today so far" is three different days
  // depending on which account is open.
  const clock = document.getElementById("sales_today_clock");
  if(clock) clock.innerHTML = _sClock(j.timezone);
  const hnote = document.getElementById("sales_today_note");
  if(hnote) hnote.textContent = "";

  // Against the SAME HOUR yesterday, never yesterday's full day -- otherwise
  // every morning shows a collapse and every evening a recovery.
  if(badge){
    const a = Number(j.today_total || 0), b = Number(j.yesterday_so_far || 0);
    if(!b){ badge.innerHTML = ""; }
    else badge.innerHTML = _sBadge(((a - b) / Math.abs(b)) * 100,
      {title: "against the same time yesterday"});
  }
}

/* ---- redraw when the window changes size --------------------------------
 *
 * A chart drawn at the container's pixel width has to be redrawn when that width
 * changes. Without this, turning a phone sideways or dragging a window wider
 * letterboxes every chart -- the viewBox is honest about its aspect ratio, so it
 * centres itself in the new box rather than filling it.
 *
 * Nothing is re-fetched. Each renderer left behind a closure over the data it
 * already had, so this is a redraw and not a reload: no request, no spinner, and
 * the figures on screen cannot change just because the window did.
 *
 * Debounced, because a drag fires resize continuously and redrawing four charts
 * per frame is how a resize comes to feel like the app has locked up. 150ms is
 * after the drag stops, not during it.
 */
let _sResizeTimer = null;
let _sLastW = 0;
function salesOnResize(){
  clearTimeout(_sResizeTimer);
  _sResizeTimer = setTimeout(function(){
    const w = window.innerWidth || 0;
    // Only when the width ACTUALLY changed. Mobile browsers fire resize when the
    // address bar hides, which changes the height and nothing else -- redrawing
    // there would make the page flicker as you scroll.
    if(w === _sLastW) return;
    _sLastW = w;
    try{ if(SALES._hourlyDraw) SALES._hourlyDraw(); }catch(e){}
    try{ if(SALES._weekDraw) SALES._weekDraw(); }catch(e){}
    try{ if(SALES.series){ salesDrawCharts(SALES.series); salesDrawOrgPpc(SALES.series); } }catch(e){}
  }, 150);
}
if(typeof window !== "undefined" && window.addEventListener){
  _sLastW = window.innerWidth || 0;
  window.addEventListener("resize", salesOnResize);
}

/* The Profit card, on the SAME basis as the sales beside it.
 *
 * This is the card that read "£80" next to "Total Sales £0". Both were right and
 * they were about different trades: Amazon dates sales by when the order was
 * PLACED and profit by when the MONEY MOVED, so a window whose orders have not
 * settled showed this week's sales beside last month's profit.
 *
 * The order-dated figure is preferred, worked out from the owner's own cost
 * prices -- revenue, less VAT where the company is registered, less Amazon's fee
 * at the rate this account actually pays, less what the stock cost and what was
 * spent getting it out. Amazon has no answer on this basis; the owner does.
 *
 * It is never shown as if it were Amazon's own figure. Where costs are missing
 * the number is knowingly too high, and the card says so rather than hiding it.
 */
function _sProfitCard(sum, byKey){
  const est = sum && sum.order_profit;
  const settled = byKey["profit"] || {key: "profit", kind: "money", value: null};

  if(!est || est.profit === null || est.profit === undefined){
    // Nothing costed at all -- fall back to the settled figure, but say which
    // days it is really about so it cannot be read as this week's.
    return Object.assign({}, settled, {
      label: "Profit",
      note: (est && est.error) ? "" : "on settled orders — a different set of days",
    });
  }

  // TWO DIFFERENT WAYS THIS FIGURE CAN BE INCOMPLETE, and they are not the same
  // thing: some UNITS have no cost (the figure is too high), or some ORDERS of
  // the period have not been fetched at all (the figure is about less than the
  // period). Both are warnings and both are shown; neither is left to be
  // guessed at from a number on its own.
  const warns = [];
  if(est.coverage_note) warns.push(est.coverage_note);
  if(est.warning) warns.push(est.warning);
  return {
    key: "profit", kind: "money", label: "Profit",
    value: est.profit,
    previous: null, delta_pct: null,
    note: warns.length ? warns.join(" ") : (est.note || ""),
    warn: warns.length > 0,
    detail: est,
  };
}

/* The full working, on hover. Every number that went into the profit, so a
 * figure nobody expected can be taken apart rather than argued with. */
function _sProfitTip(c){
  const d = c && c.detail;
  if(!d) return "Revenue after Amazon's fees and what the stock cost.";
  const L = [];
  L.push("revenue " + _sNum(d.revenue, "money"));
  if(d.goods !== undefined)
    L.push("  = goods " + _sNum(d.goods, "money")
           + " + postage the buyer paid " + _sNum(d.postage, "money"));
  if(d.vat) L.push("less VAT " + _sNum(d.vat, "money") + " (HMRC's, not yours)");
  // Every line domain/order_profit.for_period subtracts, so the working adds up
  // to the figure on the card -- the same one the P&L and Finance now state.
  L.push("less Amazon fees " + _sNum(d.fees, "money")
         + (d.fees_estimated ? " (" + _sNum(d.fees_estimated, "money")
            + " estimated for orders Amazon has not settled — "
            + (d.rate_detail || "") + ")" : ""));
  if(d.promos) L.push("less coupons you funded " + _sNum(d.promos, "money"));
  if(d.refunds) L.push("less refunds " + _sNum(d.refunds, "money")
                       + " (counted on the day the money went back)");
  if(d.refund_fees_returned)
    L.push("plus fees returned on refunds " + _sNum(d.refund_fees_returned, "money"));
  if(d.reimbursements)
    L.push("plus reimbursements " + _sNum(d.reimbursements, "money"));
  L.push("less stock cost " + _sNum(d.cogs, "money")
         + " (" + d.costed_units + " of " + d.units + " units costed)");
  if(d.charges)
    L.push("less your charges " + _sNum(d.charges, "money")
           + (d.charge_parts && d.charge_parts.length
              ? " — " + d.charge_parts.map(function(p){
                  return p.label + " " + _sNum(p.amount, "money"); }).join(", ")
              : ""));
  L.push(d.ads_connected
         ? "less ad spend " + _sNum(d.ad_spend, "money")
         : "ad spend NOT subtracted — Advertising is not connected");
  L.push("= " + _sNum(d.profit, "money")
         + (d.margin_pct !== null && d.margin_pct !== undefined
            ? "  (" + d.margin_pct + "% margin)" : ""));
  return L.join("\n");
}
