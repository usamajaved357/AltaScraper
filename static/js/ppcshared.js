/* static/js/ppcshared.js -- what the three advertising screens have in common.
 *
 * PPC Analytics, Search Terms and Campaign Analytics are three views of one set
 * of numbers, so they share one formatter, one KPI card, one "this cannot be
 * drawn" notice and one date picker. Three screens formatting ACOS three ways
 * is the small version of three screens computing it three ways, and both are
 * the thing CLAUDE.md Rule 12 is about.
 *
 * NULL IS NOT ZERO, AND THIS FILE IS WHERE THAT IS ENFORCED ON SCREEN.
 * The server sends None for anything it could not measure -- an ACOS with no
 * sales, a profit with no cost rate, a day with no advertising row. Every
 * formatter here renders those as a dash with a reason on hover, never as
 * "0.0%" or "£0.00". A zero is a measurement, and printing one that nobody made
 * is how somebody switches off a campaign that was working.
 */

const PPC_ACCENT = "#39d2c0";

function _pEsc(s){
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* The account and marketplace every one of these calls is scoped to. `account`
 * is the one spelling the app settled on -- see domain/request_account.py. */
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
 * Each of these takes the server's value, which may be null, and returns
 * display text. `ppcDash` is the single answer to "what does a figure we could
 * not work out look like", so an unmeasurable ACOS and an unmeasurable profit
 * look the same and neither looks like a zero. */

function ppcDash(why){
  return '<span class="cc" style="opacity:.45"'
       + (why ? ' title="' + _pEsc(why) + '"' : '') + '>—</span>';
}

function ppcMoney(v, cur, why){
  if(v === null || v === undefined) return ppcDash(why);
  const sym = (cur === "USD") ? "$" : (cur === "EUR") ? "€" : "£";
  const n = Number(v);
  const s = Math.abs(n) >= 1000
    ? n.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})
    : n.toFixed(2);
  return (n < 0 ? "-" : "") + sym + s.replace("-", "");
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

/* ---- change badges --------------------------------------------------------
 *
 * WHICH DIRECTION IS GOOD IS PER METRIC, and getting it wrong is worse than
 * showing no colour at all: ACOS falling is good news painted red, spend rising
 * is bad news painted green. `good` says which way is up for this metric.
 *
 * A null change is NOT 0%. It means the period before had no data to compare
 * against, which happens on every account in its first month of advertising --
 * and rendering that as "0.0%, no change" claims a measurement nobody made. */
function ppcChange(v, good, why){
  if(v === null || v === undefined){
    return '<span class="cc" style="font-size:11px;opacity:.5"'
         + ' title="' + _pEsc(why || "Nothing stored for the period before this "
           + "one, so there is nothing to compare against. This is not a change "
           + "of zero.") + '">no comparison</span>';
  }
  const n = Number(v);
  if(!n) return '<span class="cc" style="font-size:11px">no change</span>';
  const up = n > 0;
  // `good` is "up" when a rise is good (sales), "down" when a fall is good
  // (ACOS, CPC, spend, wasted spend).
  const isGood = (good === "up") ? up : (good === "down" ? !up : null);
  const col = (isGood === null) ? "var(--ink2)"
            : (isGood ? "var(--ok,#3fb950)" : "var(--red,#f85149)");
  const bg = (isGood === null) ? "transparent"
           : (isGood ? "rgba(63,185,80,0.15)" : "rgba(248,81,73,0.15)");
  return '<span style="font-size:11px;color:' + col + ';background:' + bg
       + ';border-radius:14px;padding:2px 9px;white-space:nowrap">'
       + (up ? "↗ " : "↘ ") + Math.abs(n).toFixed(1) + '%</span>';
}

/* ---- a KPI card -----------------------------------------------------------
 *
 * One card, used by all three pages. `help` becomes the ? bubble: every metric
 * on these screens is a ratio of two other numbers, and a card that shows
 * "31.1%" without saying what was divided by what is decoration. */
function ppcCard(o){
  return '<div class="panelcard" style="padding:12px 14px;border-radius:8px">'
    + '<div style="display:flex;align-items:center;gap:5px;margin-bottom:4px">'
    +   '<span class="cc" style="font-size:10.5px;text-transform:uppercase;'
    +     'letter-spacing:.7px">' + _pEsc(o.label) + '</span>'
    +   (o.help ? '<span class="hbub" title="' + _pEsc(o.help) + '">?</span>' : '')
    + '</div>'
    + '<div style="font-size:24px;font-weight:600;line-height:1.15">'
    +   (o.value === "" || o.value === null || o.value === undefined
         ? ppcDash(o.why) : o.value) + '</div>'
    + (o.change !== undefined
        ? '<div style="margin-top:5px">' + o.change + '</div>' : '')
    + (o.note ? '<div class="cc" style="font-size:10.5px;margin-top:4px">'
                + _pEsc(o.note) + '</div>' : '')
    + '</div>';
}

function ppcCards(list){
  return '<div style="display:grid;grid-template-columns:repeat(auto-fit,'
    + 'minmax(160px,1fr));gap:6px;margin:0 0 10px">'
    + list.join("") + '</div>';
}

/* ---- a panel that cannot be drawn -----------------------------------------
 *
 *     "i still see the organic vs ppc sales graph as a placeholder"
 *     "now i have the ppc data campaign performance from amazon but the graph
 *      is still as a placeholder"
 *
 * Said twice. So when a source is missing, these pages do not draw a stubbed
 * chart, an empty axis or a row of zeros -- they say what is missing and what
 * would fix it. This is the only thing that goes where a panel would have been.
 */
function ppcUnavailable(title, why){
  return '<div class="panelcard" style="padding:16px 18px;border-radius:8px;'
    + 'margin:0 0 10px">'
    + '<div style="font-weight:600;margin-bottom:5px">' + _pEsc(title) + '</div>'
    + '<div class="cc" style="font-size:12px;line-height:1.6">'
    + '<i class="ti ti-info-circle"></i> ' + _pEsc(why) + '</div></div>';
}

/* Where the profit figures on these screens come from, said once per page.
 *
 * Amazon attributes SALES to a campaign. It does not attribute the stock cost
 * or the referral fee, and neither can be known per campaign -- so profit here
 * is the account's own measured rates applied to that campaign's sales. That is
 * an estimate, it is a good one, and it is labelled rather than presented as
 * settled. */
function ppcRatesNote(r){
  if(!r) return "";
  const bits = [];
  if(r.fee_rate !== null && r.fee_rate !== undefined){
    bits.push("Amazon's fee measured at "
      + (Number(r.fee_rate) * 100).toFixed(1) + "% on this account's own settled "
      + "orders");
  }
  if(r.cogs_rate !== null && r.cogs_rate !== undefined){
    bits.push("stock cost at " + (Number(r.cogs_rate) * 100).toFixed(1) + "% ("
      + _pEsc(r.cogs_basis || "") + ")");
  }
  if(r.breakeven_acos_pct !== null && r.breakeven_acos_pct !== undefined){
    bits.push("<b>break-even ACOS " + Number(r.breakeven_acos_pct).toFixed(1)
      + "%</b> — above that a campaign is losing money");
  }
  if(!bits.length){
    return '<div class="odp-note warn" style="padding:9px 11px;margin:0 0 10px;'
      + 'font-size:11.5px;line-height:1.6">'
      + '<b>Profit cannot be worked out for this window.</b> '
      + _pEsc(r.why || "This account has no measured fee rate or no costed "
              + "orders, so there is no honest way to say whether a campaign "
              + "made money. The profit and cohort columns are left blank "
              + "rather than filled with a guess.") + '</div>';
  }
  return '<div class="cc" style="font-size:11.5px;margin:0 0 10px;padding:8px 11px;'
    + 'border:1px solid var(--line2);border-radius:6px;line-height:1.6">'
    + '<i class="ti ti-calculator"></i> Profit here is <b>estimated</b>: Amazon '
    + 'attributes sales to a campaign but not the stock cost or the fee, so '
    + 'this applies the account\'s own rates — ' + bits.join(", ") + '.'
    + (r.why ? ' <span style="color:var(--warn)">' + _pEsc(r.why) + '</span>' : '')
    + '</div>';
}

/* ---- the date window ------------------------------------------------------
 *
 * Shared state, because all three pages answer for the same window and moving
 * from one to another with the dates silently reset is how two screens end up
 * being compared across different months. */
const PPCWIN = {days: 30, start: "", end: ""};

function ppcWindowBar(onchange){
  const btn = function(d){
    return '<button class="db-chip' + (PPCWIN.days === d && !PPCWIN.start ? " on" : "")
      + '" onclick="ppcSetDays(' + d + ',' + jsArg(onchange) + ')">'
      + d + ' days</button>';
  };
  return '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
    + 'margin:0 0 10px">'
    + btn(7) + btn(14) + btn(30) + btn(90)
    + '<span class="cc" style="font-size:11.5px;margin-left:6px">'
    + (PPCWIN.start ? _pEsc(PPCWIN.start + " to " + PPCWIN.end)
                    : "last " + PPCWIN.days + " days")
    + '</span></div>';
}

function ppcSetDays(d, fn){
  PPCWIN.days = d;
  PPCWIN.start = "";
  PPCWIN.end = "";
  if(fn && typeof window[fn] === "function") window[fn]();
}

/* Every panel that could not be filled, listed once at the top of a page.
 *
 * Deliberately at the TOP and not where each panel would be: somebody opening
 * a screen with three empty sections should learn why in one place before
 * scrolling past three separate apologies. */
function ppcAvailabilityNote(av){
  if(!av) return "";
  const off = Object.keys(av).filter(function(k){
    return av[k] && !av[k].ok && av[k].why;
  });
  if(!off.length) return "";
  let h = '<div class="odp-note warn" style="padding:10px 12px;margin:0 0 10px;'
    + 'font-size:11.5px;line-height:1.6">'
    + '<b>Some panels on this page cannot be drawn from what is stored.</b>'
    + '<ul style="margin:5px 0 0 16px;padding:0">';
  off.forEach(function(k){ h += '<li>' + _pEsc(av[k].why) + '</li>'; });
  return h + '</ul></div>';
}

/* Sponsored Brands and Display are separate report types. If the account runs
 * them and they are not stored, every ACOS on these screens is flattering --
 * which is worth one sentence rather than a footnote nobody reads. */
function ppcProductNote(av){
  const p = av && av.ad_products;
  if(!p || !p.why) return "";
  return '<div class="cc" style="font-size:11.5px;margin:0 0 10px;padding:8px 11px;'
    + 'border:1px solid var(--warn-line);background:var(--warn-bg);'
    + 'border-radius:6px;line-height:1.6"><i class="ti ti-alert-triangle"></i> '
    + _pEsc(p.why) + '</div>';
}

/* A sortable table header cell. The three pages all want the same behaviour and
 * had no business each inventing it. */
function ppcTh(label, key, state, fn, align, help){
  const on = (state.sort === key);
  return '<th style="text-align:' + (align || "left") + ';white-space:nowrap;'
    + 'cursor:pointer;font-size:11.5px" onclick="' + fn + '(' + jsArg(key) + ')"'
    + (help ? ' title="' + _pEsc(help) + '"' : '') + '>'
    + _pEsc(label)
    + '<span style="margin-left:3px;opacity:' + (on ? "1" : ".3") + ';color:'
    + (on ? PPC_ACCENT : "inherit") + '">'
    + (on ? (state.desc ? "↓" : "↑") : "↕") + '</span></th>';
}

/* Sort rows by a key, nulls always last.
 *
 * A null is "not measured", and letting it sort as zero would put every
 * campaign with no data at the profitable end of a profit sort -- or the
 * cheapest end of an ACOS sort, which is where somebody looks for what is
 * working. */
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

/* The opportunity badge. Our own score, so the tooltip says what it means --
 * a number between 0 and 100 with no explanation is something nobody can act
 * on, which is the failure mode of copying a competitor's screen. */
function ppcOpp(v){
  if(v === null || v === undefined)
    return ppcDash("No spend in this window, so there is nothing to gain or "
                   + "lose by changing it.");
  const good = Number(v) >= 40;
  const col = good ? "#3fb950" : "#d29922";
  const bg = good ? "rgba(63,185,80,0.15)" : "rgba(210,153,34,0.15)";
  return '<span title="How much there is to gain by looking at this one: money '
    + 'at stake, how far past break-even it is, and clicks that bought no '
    + 'order. 40 and over is worth opening." style="display:inline-block;'
    + 'min-width:34px;text-align:center;padding:3px 6px;border-radius:6px;'
    + 'font-size:12.5px;font-weight:700;color:' + col + ';background:' + bg
    + '">' + Number(v) + '</span>';
}

/* Profit, coloured. Blank when the account has no measured rates -- see
 * ppcRatesNote. A profit column full of zeros on an account with no cost data
 * would read as "every campaign breaks exactly even". */
function ppcProfit(v, cur){
  if(v === null || v === undefined)
    return ppcDash("Not worked out — this account has no measured fee rate or "
                   + "no costed orders in this window.");
  const n = Number(v);
  const col = n > 0 ? PPC_ACCENT : (n < 0 ? "#d29922" : "var(--ink2)");
  return '<span style="color:' + col + ';font-weight:600">'
       + ppcMoney(n, cur) + '</span>';
}
