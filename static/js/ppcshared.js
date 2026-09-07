/* static/js/ppcshared.js -- the components the three advertising screens share.
 *
 * Built to the mockups: orbit-ppc-v3.jsx, orbit-search-terms-v4.jsx and
 * orbit-campaign-analytics-v2.jsx. Their type scale, spacing and palette live in
 * static/css/ppc.css as tokens; this file draws with them. The hexes are the
 * mockups' own, unchanged -- only their address moved, because static/js may not
 * name a colour (test_one_palette.py) and a screen inventing its own shade is
 * how an app stops looking like one app.
 *
 * PPC Analytics, Search Terms and Campaign Analytics are three views of one set
 * of numbers, so they share one formatter, one KPI card, one sparkline and one
 * "this cannot be drawn" notice. Three screens formatting ACOS three ways is the
 * small version of three screens computing it three ways (Rule 12).
 *
 * NULL IS NOT ZERO, AND THIS FILE IS WHERE THAT IS ENFORCED ON SCREEN.
 * The server sends None for anything it could not measure -- an ACOS with no
 * sales, a profit with no cost rate, a day with no advertising row. Every
 * formatter renders those as a dash with a reason on hover, never "0.0%" or
 * "£0.00". A zero is a measurement, and printing one nobody made is how somebody
 * switches off a campaign that was working.
 */

function _pEsc(s){
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* The account and marketplace every call is scoped to. `account` is the one
 * spelling the app settled on -- see domain/request_account.py. */
function ppcQS(extra){
  const q = [];
  const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
            ? CUR_ACCOUNT.id : "";
  const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
  if(a) q.push("account=" + encodeURIComponent(a));
  if(m && m !== "__all__") q.push("marketplace=" + encodeURIComponent(m));
  Object.keys(extra || {}).forEach(function(k){
    const v = extra[k];
    if(v !== null && v !== undefined && v !== "")
      q.push(k + "=" + encodeURIComponent(v));
  });
  return q.join("&");
}

/* ---- formatting -----------------------------------------------------------
 *
 * `ppcDash` is the single answer to "what does a figure we could not work out
 * look like", so an unmeasurable ACOS and an unmeasurable profit look the same
 * and neither looks like a zero. */

function ppcDash(why){
  return '<span class="ppc-dash"'
       + (why ? ' title="' + _pEsc(why) + '"' : '') + '>—</span>';
}

/* Money, in the mockup's shape: no decimals once past a thousand, two below. */
function ppcMoney(v, cur, why){
  if(v === null || v === undefined) return ppcDash(why);
  const sym = (cur === "USD") ? "$" : (cur === "EUR") ? "€" : "£";
  const n = Number(v);
  const a = Math.abs(n);
  const s = a >= 1000
    ? a.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})
    : a.toFixed(2);
  return (n < 0 ? "-" : "") + sym + s;
}

/* $11,853 style -- whole pounds, for the big headline numbers. */
function ppcMoney0(v, cur, why){
  if(v === null || v === undefined) return ppcDash(why);
  const sym = (cur === "USD") ? "$" : (cur === "EUR") ? "€" : "£";
  const n = Number(v);
  return (n < 0 ? "-" : "") + sym
    + Math.abs(Math.round(n)).toLocaleString();
}

function ppcPct(v, why, nd){
  if(v === null || v === undefined) return ppcDash(why);
  return Number(v).toFixed(nd === undefined ? 1 : nd) + "%";
}

function ppcNum(v, why){
  if(v === null || v === undefined) return ppcDash(why);
  return Number(v).toLocaleString();
}

function ppcX(v, why){
  if(v === null || v === undefined) return ppcDash(why);
  return Number(v).toFixed(2) + "x";
}

/* ---- change ---------------------------------------------------------------
 *
 * WHICH DIRECTION IS GOOD IS PER METRIC, and getting it wrong is worse than no
 * colour: ACOS falling is good news painted red, spend rising is bad news
 * painted green. The mockup is explicit about it -- "TACOS increasing = RED",
 * "Wasted Spend decreasing = GREEN" -- so `good` says which way is up.
 *
 * A null change is NOT 0%. It means the period before had nothing to compare
 * against, which is every account in its first month of advertising, and
 * rendering that as "0.0%, no change" claims a measurement nobody made. */
/* A RATIO MOVES IN POINTS, MONEY MOVES IN PER CENT, AND THE ARROW SAYS WHICH.
 *
 * ACOS going 24.3% -> 28.4% is +4.1 POINTS. Written as a percentage change it
 * is +16.9%, which is a true answer to a question nobody asked and reads as far
 * worse news than it is. The server decides which unit each metric uses
 * (ppc_analytics.change_units) and it is printed, so nobody has to assume.
 */
function ppcChangeText(v, good, why, unit){
  if(v === null || v === undefined){
    return '<span class="ppc-chg flat" title="'
      + _pEsc(why || "Nothing stored for the period before this one, so there "
              + "is nothing to compare against. This is not a change of zero.")
      + '">—</span>';
  }
  const sfx = (unit === "pts") ? "pts" : "%";
  const n = Number(v);
  if(!n){
    // A FLAT ZERO CAN MEAN TWO THINGS and the tooltip says so: genuinely
    // unchanged, or a comparison period whose data does not reach this grain.
    return '<span class="ppc-chg flat" title="No change against the period '
      + 'before — or the comparison period has no figure at this level of '
      + 'detail. A 0% here is not always flat traffic.">— 0' + sfx + '</span>';
  }
  const up = n > 0;
  const isGood = (good === "up") ? up : (good === "down" ? !up : null);
  const cls = (isGood === null) ? "flat" : (isGood ? "good" : "bad");
  return '<span class="ppc-chg ' + cls + '" title="'
       + (sfx === "pts"
          ? "Percentage POINTS. This metric is already a percentage, so a move "
            + "from 24.3% to 28.4% is +4.1pts — not +16.9%."
          : "Percentage change against the period before this one.")
       + '">' + (up ? "↗" : "↘") + " " + Math.abs(n).toFixed(1) + sfx
       + '</span>';
}

/* The bare arrow-and-figure the KPI card uses, without the pill. */
function ppcChangeBare(v, good, why, unit){
  if(v === null || v === undefined){
    return '<span class="ppc-kpi-c ppc-dash" title="'
      + _pEsc(why || "No data for the period before this one.") + '">—</span>';
  }
  // Same rule as ppcChangeText: a metric that IS a percentage moves in points.
  const sfx = (unit === "pts") ? "pts" : "%";
  const n = Number(v);
  const up = n > 0;
  const isGood = (good === "up") ? up : (good === "down" ? !up : null);
  const col = (isGood === null) ? "var(--ppc-muted)"
            : (isGood ? "var(--ppc-green)" : "var(--ppc-red)");
  return '<span class="c" style="color:' + col + '" title="'
       + (sfx === "pts"
          ? "Percentage POINTS — this metric is already a percentage."
          : "Percentage change against the period before.")
       + (n === 0 ? " A 0 here can also mean the comparison period has no "
                    + "figure at this level of detail." : "")
       + '">'
       + (n === 0 ? "—" : (up ? "↗" : "↘")) + " "
       + Math.abs(n).toFixed(1) + sfx + '</span>';
}

/* ---- sparkline ------------------------------------------------------------
 *
 * The mockup's: 200x28, a bare 2px stroke, no dots, no axes, stretched to the
 * card. Gaps are real -- a day with no advertising row is not a day of zero
 * spend, and joining across it would draw a line through a measurement nobody
 * made. So the path breaks and resumes. */
function ppcSparkline(data, colour){
  const vals = (data || []).map(function(v){
    return (v === null || v === undefined) ? null : Number(v);
  });
  const known = vals.filter(function(v){ return v !== null; });
  if(known.length < 2) return '<div class="spark"></div>';
  const w = 200, h = 28;
  const min = Math.min.apply(null, known), max = Math.max.apply(null, known);
  const range = (max - min) || 1;

  // THE LINE JOINS ACROSS A MISSING DAY RATHER THAN SHATTERING.
  //
  //     "the 8 graphs under day trail shows graph which are erased from in
  //      between, graphs dont break usually they are dropped to zero when no
  //      data but they dont vanish normally"
  //
  // It lifted the pen on every null, so a metric with holes came out as a
  // handful of disconnected fragments. Measured on nestwell_goods over 30 days:
  // spend, sales, clicks, impressions, orders and CTR have no holes at all --
  // only the trailing two days Amazon has not reported yet. ACOS has NINE
  // mid-series holes and ROAS two, and those two cards were the shattered ones.
  //
  // A hole in ACOS is a day that SPENT and sold nothing, so the ratio is
  // undefined. It is not zero, and drawing it at zero -- the other obvious fix
  // -- would say the opposite of the truth: 0% ACOS means sales that cost
  // nothing to get, which is the best possible day rather than the worst.
  //
  // So the line connects its known points and claims nothing for the days
  // between. No value is invented, and the shape survives. The KPI card's
  // tooltip says how many days were skipped, because a straight run through a
  // gap should be attributable rather than mistaken for measurement.
  let d = "", pen = false, skipped = 0;
  vals.forEach(function(v, i){
    if(v === null){ if(pen) skipped++; return; }
    const x = (i / Math.max(1, vals.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    d += (pen ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1) + " ";
    pen = true;
  });
  const tip = skipped
    ? (skipped + " day" + (skipped === 1 ? "" : "s")
       + " in this range had no figure to plot — usually a day that spent and "
       + "sold nothing, which has no ratio rather than a ratio of zero. The "
       + "line joins across them and claims nothing for them.")
    : "";
  return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" '
    + 'style="width:100%;height:' + h + 'px" preserveAspectRatio="none">'
    + (tip ? '<title>' + _pEsc(tip) + '</title>' : '')
    + '<path d="' + d.trim() + '" fill="none" stroke="' + colour
    + '" stroke-width="2"/></svg>';
}

/* The day-trail card's chart: 120x50, a 1.5px line over a gradient that fades
 * 0.25 -> 0.02. Cumulative, so it only ever climbs. */
let _PPC_GRAD = 0;
function ppcMiniLine(points, colour){
  const pts = (points || []).filter(function(v){
    return v !== null && v !== undefined;
  }).map(Number);
  if(pts.length < 2) return "";
  const w = 120, h = 50;
  const max = Math.max.apply(null, pts) || 1;
  const id = "ppcg" + (++_PPC_GRAD);
  let d = "";
  pts.forEach(function(p, i){
    const x = (i / (pts.length - 1)) * w;
    const y = h - (p / max) * h;
    d += (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1) + " ";
  });
  const fill = d + "L" + w + "," + h + " L0," + h + " Z";
  return '<svg viewBox="0 0 ' + w + ' ' + h + '" '
    + 'style="width:100%;height:100%" preserveAspectRatio="none">'
    + '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1">'
    + '<stop offset="0%" stop-color="' + colour + '" stop-opacity="0.25"/>'
    + '<stop offset="100%" stop-color="' + colour + '" stop-opacity="0.02"/>'
    + '</linearGradient></defs>'
    + '<path d="' + fill + '" fill="url(#' + id + ')"/>'
    + '<path d="' + d.trim() + '" fill="none" stroke="' + colour
    + '" stroke-width="1.5"/></svg>';
}

/* ppcMiniBar() WAS HERE AND IS GONE.
 *
 * It drew one bar per day-trail card instead of the cumulative curve. The
 * owner has seen both and asked for the curve back -- "please revert the day
 * trails graph style" -- so the bar has no caller, and an unused renderer is
 * one more thing for the next person to wonder about. ppcMiniLine above is
 * what the trail uses. */

/* ---- a KPI card -----------------------------------------------------------
 *
 * The mockup's exactly: label 11px uppercase with a ⓘ, value 28/700 with the
 * change on the same baseline, sparkline underneath. */
function ppcKpi(o){
  return '<div class="ppc-kpi">'
    + '<div class="k">' + _pEsc(o.label)
    +   (o.help ? '<span class="ppc-i" title="' + _pEsc(o.help) + '">ⓘ</span>' : '')
    + '</div>'
    + '<div class="row"><span class="v">'
    +   (o.value === "" || o.value === null || o.value === undefined
         ? ppcDash(o.why) : o.value) + '</span>'
    +   (o.change === undefined ? "" : o.change)
    + '</div>'
    + (o.spark || '<div class="spark"></div>')
    + '</div>';
}

/* A card inside a panel -- the profitability grid's six. */
function ppcSubCard(o){
  return '<div class="ppc-sub-card">'
    + '<div class="k">' + _pEsc(o.label)
    +   (o.help ? '<span class="ppc-i" title="' + _pEsc(o.help) + '">ⓘ</span>' : '')
    + '</div>'
    + '<div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">'
    +   '<span class="v"' + (o.colour ? ' style="color:' + o.colour + '"' : '')
    +   '>' + (o.value === null || o.value === undefined
               ? ppcDash(o.why) : o.value) + '</span>'
    +   (o.change || "") + (o.badge || "")
    + '</div>'
    + (o.note ? '<div class="n">' + o.note + '</div>' : '')
    + (o.note2 ? '<div class="n" style="margin-top:0">' + o.note2 + '</div>' : '')
    + '</div>';
}

/* ---- a panel that cannot be drawn -----------------------------------------
 *
 *     "i still see the organic vs ppc sales graph as a placeholder"
 *     "now i have the ppc data campaign performance from amazon but the graph
 *      is still as a placeholder"
 *
 * Said twice. So a missing source draws nothing -- not a stub, not an empty
 * axis, not a row of zeros -- and says what is missing and what would fix it.
 */
function ppcUnavailable(title, why){
  return '<div class="ppc-panel ppc-panel-sm">'
    + '<div class="ppc-panel-title-sm">' + _pEsc(title) + '</div>'
    + '<div style="font-size:12px;line-height:1.6;color:var(--ppc-muted)">'
    + _pEsc(why) + '</div></div>';
}

/* Where the profit figures come from, said once per page.
 *
 * Amazon attributes SALES to a campaign. It does not attribute the stock cost
 * or the referral fee, and neither can be known per campaign -- so profit here
 * is the account's own measured rates applied to that campaign's sales. An
 * estimate, a good one, labelled rather than presented as settled. */
function ppcRatesNote(r){
  if(!r) return "";
  const bits = [];
  if(r.fee_rate !== null && r.fee_rate !== undefined){
    bits.push("Amazon's fee measured at "
      + (Number(r.fee_rate) * 100).toFixed(1) + "%");
  }
  if(r.cogs_rate !== null && r.cogs_rate !== undefined){
    bits.push("stock at " + (Number(r.cogs_rate) * 100).toFixed(1)
      + "% (" + _pEsc(r.cogs_basis || "") + ")");
  }
  if(!bits.length){
    return '<div class="ppc-note warn"><b>Profit cannot be worked out for this '
      + 'window.</b> ' + _pEsc(r.why || "This account has no measured fee rate "
      + "or no costed orders, so there is no honest way to say whether a "
      + "campaign made money. The profit and cohort columns are left blank "
      + "rather than filled with a guess.") + '</div>';
  }
  return '<div class="ppc-note">Profit here is <b>estimated</b>: Amazon '
    + 'attributes sales to a campaign but not the stock cost or the fee, so this '
    + 'applies the account\'s own rates — ' + bits.join(", ") + '.'
    + (r.why ? ' <span style="color:var(--ppc-orange)">' + _pEsc(r.why)
               + '</span>' : '')
    + '</div>';
}

/* Every panel that could not be filled, listed once at the top. Deliberately
 * at the top rather than in each empty section: somebody opening a screen with
 * three blank panels should learn why once, before scrolling past three
 * separate apologies. */
function ppcAvailabilityNote(av){
  if(!av) return "";
  const off = Object.keys(av).filter(function(k){
    return av[k] && !av[k].ok && av[k].why;
  });
  if(!off.length) return "";
  let h = '<div class="ppc-note warn"><b>Some panels on this page cannot be '
    + 'drawn from what is stored.</b><ul style="margin:5px 0 0 16px;padding:0">';
  off.forEach(function(k){ h += '<li>' + _pEsc(av[k].why) + '</li>'; });
  return h + '</ul></div>';
}

/* THE EMPTY SCREEN, EXPLAINED PROPERLY.
 *
 *     "PPC Analytics page seems to be just an image not a full interactive page"
 *
 * Measured afterwards, and this is the reason: five of the six accounts have no
 * Amazon Advertising login at all. On those there is no spend, no campaign, no
 * search term and nothing to hover -- so the page drew its frame and nothing
 * else, which is indistinguishable from a page that is broken.
 *
 * What it used to say was "Nothing is stored for this account and marketplace in
 * this window", in small grey type. True, and useless: it does not say whether
 * the fix is to connect a login, to run a sync, or to widen the dates. Those are
 * three different problems and only one of them is about the window.
 *
 * So this states which one it is, in the order a person would act on:
 *
 *     no login          -> connect it, and which account HAS one
 *     login, no rows    -> run the advertising sync
 *     rows, none here   -> widen the range; the data is elsewhere in time
 *
 * Shared by all three advertising screens and the console, because an empty
 * Search Terms page and an empty PPC Analytics page have the same cause and
 * deserve the same sentence (Rule 12).
 */
function ppcNoData(av, what){
  const c = (av && av.connection) || {};
  const camp = (av && av.campaigns) || {};
  let title, body, cls;
  if(c.ok === false){
    cls = "warn";
    title = "This account has no Amazon Advertising login connected";
    body = c.why + " Advertising figures are read with a SEPARATE login from "
         + "the Selling Partner one, so nothing on this page can be filled "
         + "until that is set — it is not that the window is empty.";
  }else if(c.ok === true && !camp.ok){
    cls = "warn";
    title = "Connected, but nothing has been mirrored yet";
    body = "The Advertising login for this account resolves, so the connection "
         + "is good. No advertising rows are stored yet — the sync has not run, "
         + "or ran before this account was connected. Run the advertising sync "
         + "and this page fills.";
  }else{
    cls = "";
    title = "No advertising figures in this window";
    body = "This account has advertising data stored, but none inside the dates "
         + "chosen. Widen the range — the figures are there, just not here.";
  }
  return '<div class="ppc-note ' + cls + '" style="padding:16px 18px">'
    + '<b style="font-size:15px;display:block;margin-bottom:6px">'
    + _pEsc(title) + '</b>'
    + '<div style="line-height:1.6">' + _pEsc(body) + '</div>'
    + (what ? '<div style="margin-top:8px;font-size:12px;opacity:.8">'
              + _pEsc(what) + '</div>' : "")
    + '</div>';
}

function ppcProductNote(av){
  const p = av && av.ad_products;
  if(!p || !p.why) return "";
  return '<div class="ppc-note warn">' + _pEsc(p.why) + '</div>';
}

/* ---- reloading without blanking the screen --------------------------------
 *
 *     "when i change the range the whole screen dissappears and then reappear
 *      after loading, normally the filters change results in a franction of
 *      seconds without blinking the screen"
 *
 * All three screens wiped innerHTML and drew a spinner. What is already on
 * screen is still TRUE -- it is simply for the previous window -- so it stays,
 * dimmed, with a small bar saying so. Only a first load, with nothing worth
 * keeping, draws the spinner on its own.
 *
 * WHOLLY DEFENSIVE. This is decoration around the real work; a missing element
 * must never stop a render that would otherwise have succeeded. */
function ppcBusy(hostId, on){
  try{
    const host = document.getElementById(hostId);
    if(!host || typeof host.querySelector !== "function") return;
    const page = host.querySelector(".ppc-page");
    if(page && page.style) page.style.opacity = on ? "0.55" : "";
    const barId = hostId + "_busy";
    let bar = document.getElementById(barId);
    if(on && !bar && page && typeof document.createElement === "function"){
      bar = document.createElement("div");
      bar.id = barId;
      bar.className = "ppc-busy";
      bar.innerHTML = '<span class="genspin"></span> Updating…';
      if(typeof page.prepend === "function") page.prepend(bar);
      else if(typeof page.insertBefore === "function")
        page.insertBefore(bar, page.firstChild);
    }else if(!on && bar && typeof bar.remove === "function"){
      bar.remove();
    }
  }catch(e){ /* never let the busy state break the page */ }
}

/* Arm the draw-in animation on charts just inserted. The hover and drag
 * handlers are inline on the SVG salesCombo returns, so they need nothing. */
function ppcArm(hostId){
  if(typeof altaChartsInView !== "function") return;
  try{ altaChartsInView(document.getElementById(hostId) || document); }
  catch(e){}
}

/* ---- the shared window ----------------------------------------------------
 *
 * All three screens answer for the same window, because moving between them
 * with the dates silently reset is how two screens get compared across
 * different months. */
// `shown` is what the date boxes were last drawn with -- the picked window when
// there is one, otherwise the server's. ppcSetDate falls back to it so changing
// one end keeps the other. See the note there.
const PPCWIN = {days: 30, start: "", end: "", shown: {start: "", end: ""}};

function ppcSeg(days, onchange){
  return '<div class="ppc-seg">'
    + [7, 14, 30, 90].map(function(d){
        return '<button class="' + (PPCWIN.days === d && !PPCWIN.start ? "on" : "")
          + '" onclick="ppcSetDays(' + d + ',' + jsArg(onchange) + ')">'
          + d + ' days</button>';
      }).join("")
    + '</div>';
}

function ppcSetDays(d, fn){
  PPCWIN.days = d;
  PPCWIN.start = "";
  PPCWIN.end = "";
  if(fn && typeof window[fn] === "function") window[fn]();
}

/* THE DATE RANGE IS PICKABLE, not just printed.
 *
 *     "i dont have an option to select dates range in ppc analytics page, a
 *      caledar should appear to set the filter"
 *
 * It showed the window as read-only text -- "2026-08-08 to 2026-09-05" -- next
 * to 7/14/30/90 buttons, so the only reachable windows were those four. PPCWIN
 * has carried `start` and `end` all along and ppcQS already sends them; the
 * control to set them was simply never drawn.
 *
 * Two native date inputs, which is what puts a real calendar on the screen
 * without shipping a picker library. They are the browser's own, so they follow
 * the machine's locale and keyboard conventions rather than inventing them.
 *
 * SETTING EITHER ONE APPLIES IMMEDIATELY, and the day buttons de-select
 * themselves because the window is no longer one of theirs -- ppcSeg already
 * tests `!PPCWIN.start` for that. Clearing both hands the window back to them.
 */
function ppcDateRange(j, onchange){
  const w = (j && j.window) || {};
  // The picked dates when there are any, otherwise the window the server
  // actually answered for -- so the boxes always show the range on screen
  // rather than sitting empty until touched.
  const s = PPCWIN.start || w.start || "";
  const e = PPCWIN.end || w.end || "";
  // WHAT THE BOXES ARE SHOWING, remembered for ppcSetDate.
  //
  // Changing ONE end must keep the other as displayed. PPCWIN.start and .end
  // are EMPTY while the day buttons are driving -- the boxes are showing the
  // server's window, not a picked one -- so a handler that fell back to
  // PPCWIN had nothing to fall back to. Touching the end box then set the
  // start to the same day and collapsed the window to twenty-four hours,
  // which is what "i am not able to select more than 2 days in past" was.
  PPCWIN.shown = {start: s, end: e};
  const box = function(which, val){
    return '<input type="date" class="ppc-fctl ppc-date" value="'
      + _pEsc(val) + '" max="' + _pEsc(ppcToday()) + '"'
      + ' onchange="ppcSetDate(' + jsArg(which) + ', this.value, '
      + jsArg(onchange) + ')">';
  };
  return '<div><div class="ppc-flabel">Date range</div>'
    + '<div style="display:flex;align-items:center;gap:6px">'
    +   box("start", s)
    +   '<span style="font-size:12px;color:var(--ppc-dim)">to</span>'
    +   box("end", e)
    +   (PPCWIN.start
        ? '<button class="ppc-btn" style="background:transparent;'
          + 'color:var(--ppc-muted);padding:5px 9px" title="Back to the day '
          + 'buttons" onclick="ppcClearDates(' + jsArg(onchange) + ')">✕</button>'
        : '')
    + '</div></div>';
}

function ppcToday(){
  const d = new Date();
  const p = function(n){ return (n < 10 ? "0" : "") + n; };
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

/* DRAG-TO-ZOOM, RESOLVED PROPERLY. -> true when the window moved.
 *
 *     "i clicked and dragged on the revenue, ad spend & profitibality, to
 *      select a specific time period, it showed me server error: Invalid
 *      isoformat string: '23', the sales graph changes its date range and shows
 *      a zoom in version but this is not, all the graphs should have this
 *      feature"
 *
 * salescharts._scDragEnd hands its handler two COLUMN INDICES and the chart id
 * -- fn(a, b, cid) -- not two dates. The Sales page has always known that and
 * translates them through the columns it drew. The PPC handlers did
 * `String(from).slice(0,10)` on them, so dragging sent start=23 to the server
 * and Python said "Invalid isoformat string: '23'".
 *
 * It was not obvious from either handler, because the SAME function is also
 * called with real dates from the day-trail cards -- ppcaZoomTo(r.date, r.date).
 * One function, two argument types, and only one of them ever tested by hand.
 *
 * So this takes both: a number is an index into whatever that chart was drawn
 * with, a string is already a date. The columns come from SC_LAST, which
 * salesCombo already keeps PER CHART ID -- which is what makes this correct on
 * a page with several charts over different ranges, rather than assuming every
 * chart shares the page's window.
 */
function ppcZoomResolve(v, cid){
  if(v === null || v === undefined) return "";
  // Already a date.
  if(typeof v === "string" && v.length >= 8 && v.indexOf("-") > 0)
    return v.slice(0, 10);
  const n = Number(v);
  if(isNaN(n)) return "";
  let cols = [];
  try{
    const last = (typeof SC_LAST !== "undefined") ? SC_LAST[cid] : null;
    cols = (last && last.columns) || [];
  }catch(e){ cols = []; }
  const c = cols[Math.max(0, Math.min(cols.length - 1, Math.round(n)))];
  return (c === null || c === undefined) ? "" : String(c).slice(0, 10);
}

function ppcZoomTo(from, to, cid, reload){
  const a = ppcZoomResolve(from, cid);
  const b = ppcZoomResolve(to, cid);
  // REFUSE RATHER THAN SEND RUBBISH. A chart whose columns are not dates -- or
  // one drawn before SC_LAST had it -- resolves to nothing, and asking the
  // server for a window of "" is how a screen ends up showing an error where a
  // gesture should simply have done nothing.
  if(!a || !b) return false;
  PPCWIN.start = (a <= b) ? a : b;
  PPCWIN.end = (a <= b) ? b : a;
  if(reload && typeof window[reload] === "function") window[reload]();
  return true;
}

function ppcSetDate(which, value, fn){
  const v = String(value || "").slice(0, 10);
  if(!v) return;
  // THE OTHER END IS WHATEVER THE OTHER BOX IS SHOWING.
  //
  // Changing one date must leave the other alone. This used to fall back to
  // PPCWIN.start / PPCWIN.end, which are EMPTY whenever the day buttons are
  // driving -- the boxes show the SERVER's window then, not a picked one. So
  // touching the end box read the start as "", `if(!s) s = e` set it to the
  // same day, and a thirty-day view collapsed to twenty-four hours. From the
  // outside that is "i am not able to select more than 2 days in past": every
  // attempt to move one end threw the other away.
  //
  // PPCWIN.shown is what ppcDateRange last drew, so the fallback is the range
  // actually on screen. today() remains the last resort for a first render
  // that somehow had neither.
  const shown = PPCWIN.shown || {};
  const other = (which === "start")
    ? (PPCWIN.end || shown.end || ppcToday())
    : (PPCWIN.start || shown.start || "");
  let s = (which === "start") ? v : other;
  let e = (which === "end") ? v : other;
  if(!s) s = e;
  // A BACKWARDS RANGE IS SWAPPED, NOT REFUSED. Picking the end first and then
  // an earlier start is a normal way to use two date boxes, and answering it
  // with an error would be the app being pedantic about the order of two
  // clicks.
  if(s && e && s > e){ const t = s; s = e; e = t; }
  PPCWIN.start = s;
  PPCWIN.end = e;
  if(fn && typeof window[fn] === "function") window[fn]();
}

function ppcClearDates(fn){
  PPCWIN.start = "";
  PPCWIN.end = "";
  if(fn && typeof window[fn] === "function") window[fn]();
}

/* The mockup's filter row: labels ABOVE their controls, COMPARE TO pushed
 * right with the compared range beside it. */
function ppcFilterRow(j, onchange){
  const w = (j && j.window) || {};
  return '<div class="ppc-filters">'
    + ppcDateRange(j, onchange)
    + '<div><div class="ppc-flabel">Range</div>' + ppcSeg(30, onchange) + '</div>'
    + '<div style="margin-left:auto">'
    +   '<div class="ppc-flabel">Compare to</div>'
    +   '<div style="display:flex;align-items:center;gap:10px">'
    +     '<div class="ppc-fctl">Previous period</div>'
    +     '<span style="font-size:12px;color:var(--ppc-dim)">'
    +     _pEsc((w.compare_start || "") + " – " + (w.compare_end || ""))
    +     '</span></div></div>'
    + '</div>';
}

/* A sortable header cell, in the mockup's ↕ / ↑ / ↓ form. */
function ppcTh(label, key, state, fn, align, help){
  const on = (state.sort === key);
  return '<th class="ppc-sortable"'
    + (align ? ' style="text-align:' + align + '"' : '')
    + ' onclick="' + fn + '(' + jsArg(key) + ')"'
    + (help ? ' title="' + _pEsc(help) + '"' : '') + '>'
    + _pEsc(label)
    + (help ? '<span class="ppc-i">ⓘ</span>' : '')
    + '<span class="ppc-sortarrow' + (on ? " on" : "") + '">'
    + (on ? (state.desc ? "↓" : "↑") : "↕") + '</span></th>';
}

/* Sort rows by a key, nulls always last.
 *
 * A null is "not measured". Letting it sort as zero puts every campaign with no
 * data at the profitable end of a profit sort, or the cheapest end of an ACOS
 * sort -- which is exactly where somebody looks for what is working. */
function ppcSortRows(rows, key, desc){
  return (rows || []).slice().sort(function(a, b){
    const x = a[key], y = b[key];
    const xn = (x === null || x === undefined), yn = (y === null || y === undefined);
    if(xn && yn) return 0;
    if(xn) return 1;
    if(yn) return -1;
    if(typeof x === "string" || typeof y === "string"){
      const c = String(x).localeCompare(String(y));
      return desc ? -c : c;
    }
    return desc ? (y - x) : (x - y);
  });
}

/* The opportunity badge: a rounded rectangle, transparent tint, no border --
 * green at 40 and over, orange below. Our own score, so the tooltip says what
 * it means: a number between 0 and 100 with no explanation is something nobody
 * can act on, which is the failure mode of copying a competitor's screen. */
function ppcOpp(v){
  if(v === null || v === undefined)
    return ppcDash("No spend in this window, so there is nothing to gain or "
                   + "lose by changing it.");
  // THE WHOLE FORMULA, on hover.
  //
  //     "there is a coulmn for oppurtunity i am concerd about the data accuracy"
  //
  // A fair concern about any invented score, and the honest answer is to publish
  // the arithmetic rather than assert the number is right. Every input is
  // Amazon's own figure for the window; only the weighting is ours, and it is
  // stated here so it can be argued with.
  return '<span class="ppc-opp ' + (Number(v) >= 40 ? "hi" : "lo")
    + '" title="OUR score, 0-100, not Amazon\'s — how much there is to gain by '
    + 'looking at this one. Three parts, added:\n'
    + '  up to 40  money at stake, on a square-root scale so one big campaign '
    + 'cannot own the list\n'
    + '  up to 35  how far past break-even the ACOS is (35 outright if it spent '
    + 'and sold nothing)\n'
    + '  up to 25  clicks that bought no order — 25 at ten or more clicks and '
    + 'no sale, tapering to 0 at a 10% conversion rate\n'
    + 'Inputs are Amazon\'s own spend, sales, clicks and orders for this window; '
    + 'the weighting is ours. Blank when nothing was spent — no spend is no '
    + 'opportunity and no problem. 40 and over is worth opening.">'
    + Number(v) + '</span>';
}

/* Profit, coloured. Cyan positive, orange negative on the term screens; the
 * campaign table asks for green/red and passes `tone`. Blank when the account
 * has no measured rates -- a profit column full of zeros would read as "every
 * campaign breaks exactly even". */
function ppcProfit(v, cur, tone){
  if(v === null || v === undefined)
    return ppcDash("Not worked out — this account has no measured fee rate or "
                   + "no costed orders in this window.");
  const n = Number(v);
  const pos = (tone === "greenred") ? "var(--ppc-green)" : "var(--ppc-cyan)";
  const neg = (tone === "greenred") ? "var(--ppc-red)" : "var(--ppc-orange)";
  const col = n > 0 ? pos : (n < 0 ? neg : "var(--ppc-muted)");
  return '<span style="color:' + col + ';font-weight:600">'
       + ppcMoney(n, cur) + '</span>';
}

/* A legend row, centred under a chart, in the mockup's "● Label" form. */
function ppcLegend(items){
  return '<div class="ppc-legend">'
    + items.map(function(it){
        return '<span><span class="dot" style="color:' + it[1] + '">●</span> '
          + _pEsc(it[0]) + '</span>';
      }).join("")
    + '</div>';
}
