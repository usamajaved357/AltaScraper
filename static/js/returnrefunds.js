/* static/js/returnrefunds.js -- Returns > Refunds: was each return paid back?
 *
 * Owner, 30 Sep 2026: "please show me all that information in the app -- if we
 * have already paid the refunds and what is the status of the returns or if the
 * returns closed without resolution or refund".
 *
 * NOTHING IS WORKED OUT HERE. /returns/refunds answers with every row already
 * classified by domain/return_refunds.py (the returns report joined with the
 * money Amazon actually moved). This file draws it, filters it by class and
 * offers the CSV the server writes. Reads only.
 */
var RREF = {data: null, error: "", loading: false, cls: "", days: 90, seq: 0};

// Tone of each class's chip: what it means for you, not Amazon's wording.
const RREF_TONE = {
  refunded_full: "ok", refunded_partial: "info", approved_unrefunded: "warn",
  pending: "warn", report_no_money: "bad", closed_no_refund: "",
  no_refund_due: "", refund_no_return: "info",
};

function _rrMoney(v){
  if(v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if(!isFinite(n)) return "—";
  const cc = (RREF.data && RREF.data.currency) || "";
  if(cc && typeof curMoney === "function") return curMoney(n, cc);
  return n.toFixed(2);
}

function _rrRange(){
  const end = new Date();
  const start = new Date(end.getTime() - (RREF.days - 1) * 86400000);
  const iso = d => d.toISOString().slice(0, 10);
  return {start: iso(start), end: iso(end)};
}

function _rrUrl(path){
  const r = _rrRange();
  return path + ((typeof scopeQs === "function") ? scopeQs(r)
                 : "?start=" + r.start + "&end=" + r.end);
}

function refundsOnOpen(){
  if(!RREF.data && !RREF.loading) refundsLoad();
  else refundsRender();
}

/* The returns store changed (a pull, an upload, Start again): read it again
   next time, and now if the view is on screen. */
function refundsForget(){
  RREF.data = null; RREF.error = "";
  const host = document.getElementById("returns_refunds");
  if(host && host.style && host.style.display !== "none" && host.innerHTML) refundsLoad();
}

function refundsSetDays(d){ RREF.days = Number(d) || 90; refundsLoad(); }
function refundsFilter(k){ RREF.cls = (RREF.cls === k) ? "" : k; refundsRender(); }

async function refundsLoad(){
  const host = document.getElementById("returns_refunds");
  if(!host) return;
  const seq = ++RREF.seq;
  const sc = (typeof screenScope === "function") ? screenScope() : null;
  RREF.loading = true; RREF.error = "";
  host.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> '
    + 'Matching returns with refunds…</div>';
  let j = null;
  try{
    const r = await fetch(_rrUrl("/returns/refunds"));
    j = await r.json();
  }catch(e){
    j = {ok: false, error: "Could not reach the server."};
  }
  // Another account, marketplace or a newer load: this reply lands nowhere.
  if(seq !== RREF.seq || (sc && typeof screenStillIn === "function" && !screenStillIn(sc))) return;
  RREF.loading = false;
  if(j && j.ok){ RREF.data = j; }
  else { RREF.data = null; RREF.error = (j && j.error) || "Could not load refunds."; }
  refundsRender();
}

function _rrOrderCell(r){
  const oid = r.order_id || "";
  if(!oid) return '<span class="cc">—</span>';
  const mkt = (RREF.data && RREF.data.marketplace) || "";
  const sc = (typeof _opSellerCentral === "function") ? _opSellerCentral(oid, mkt)
           : "https://sellercentral.amazon.co.uk/orders-v3/order/" + encodeURIComponent(oid);
  return '<a href="#" onclick="return refundsOpenOrder(' + jsArg(oid) + ')" title="Open on Orders">'
    + esc(oid) + '</a> <a href="' + esc(sc) + '" target="_blank" rel="noopener" '
    + 'title="Open the order on Seller Central (its returns and refunds are on it)" '
    + 'aria-label="Open ' + esc(oid) + ' on Seller Central"><i class="ti ti-external-link"></i></a>';
}

function refundsOpenOrder(oid){
  if(typeof inboxOpenOrder === "function") return inboxOpenOrder(oid);
  if(typeof navTo === "function") navTo("orders");
  return false;
}

function _rrMoneyCell(r){
  if(!(Number(r.money_back) > 0)) return '<span class="cc">—</span>';
  const fp = r.full_or_partial === "full" ? "full"
           : r.full_or_partial === "partial" ? "partial" : "";
  return _rrMoney(r.money_back)
    + '<span class="rr-sub">' + esc(r.money_date || "") + (fp ? " · " + fp : "") + '</span>';
}

function _rrWaitCell(r){
  if(r.days === null || r.days === undefined) return '<span class="cc">—</span>';
  const paid = Number(r.money_back) > 0;
  return esc(String(r.days)) + 'd' + (paid ? '<span class="rr-sub">to refund</span>' : '')
    + (r.overdue ? ' <span class="rr-flag">overdue</span>' : '');
}

function refundsRows(){
  const rows = (RREF.data && RREF.data.rows) || [];
  if(!RREF.cls) return rows;
  if(RREF.cls === "_overdue") return rows.filter(r => r.overdue);
  if(RREF.cls === "_awaiting") return rows.filter(r => (RREF.data.awaiting_classes || []).indexOf(r["class"]) >= 0);
  if(RREF.cls === "_mismatch") return rows.filter(r => r.mismatch);
  return rows.filter(r => r["class"] === RREF.cls);
}

function refundsRender(){
  const host = document.getElementById("returns_refunds");
  if(!host) return;
  const d = RREF.data;
  let h = '<div class="rr-filters" style="align-items:center">'
    + '<div style="font-size:12.5px;font-weight:600">Refunds</div>'
    + ((typeof uiHint === "function") ? uiHint(
        "Each return from Amazon's returns report, matched with the refund money "
        + "Amazon actually moved for that order. The report's own 'Refunded Amount' "
        + "is Amazon's paperwork; the money column is what really went back. "
        + "Refund postings reach this app with the finance sync, so one made in the "
        + "last day or two may not show yet.") : "");
  [30, 90, 180].forEach(function(n){
    h += '<button class="db-chip' + (RREF.days === n ? ' on' : '') + '" onclick="refundsSetDays('
      + n + ')">' + n + ' days</button>';
  });
  h += '<span style="margin-left:auto;display:flex;gap:6px">'
    + '<button class="db-chip" onclick="refundsLoad()"><i class="ti ti-refresh"></i> Reload</button>'
    + (d ? '<a class="db-chip" href="' + esc(_rrUrl("/returns/refunds.csv"))
         + '" download><i class="ti ti-file-download"></i> CSV</a>' : '')
    + '</span></div>';

  if(RREF.loading && !d){ host.innerHTML = h + '<div class="cc" style="padding:16px">'
      + '<span class="genspin"></span> Matching returns with refunds…</div>'; return; }
  if(RREF.error){
    host.innerHTML = h + ((typeof uiError === "function")
      ? uiError("Could not load refunds", RREF.error, "refundsLoad", "returns")
      : '<div role="alert" style="color:var(--red)">' + esc(RREF.error) + '</div>');
    return;
  }
  if(!d){ host.innerHTML = h; return; }

  const t = d.totals || {};
  const by = t.by_class || {};
  const cards = [
    {value: _rrMoney(t.refunded), label: "Refunded",
     note: (t.refunded_orders || 0) + " orders", tone: "",
     onclick: "refundsFilter('refunded_full')", on: RREF.cls === "refunded_full"},
    {value: String(t.awaiting || 0), label: "Awaiting refund",
     note: _rrMoney(t.awaiting_value), tone: t.awaiting ? "warn" : "",
     onclick: "refundsFilter('_awaiting')", on: RREF.cls === "_awaiting"},
    {value: String(t.overdue || 0), label: "Overdue", tone: t.overdue ? "bad" : "",
     title: d.rule || "", onclick: "refundsFilter('_overdue')", on: RREF.cls === "_overdue"},
    {value: String(t.mismatches || 0), label: "Mismatches", tone: t.mismatches ? "bad" : "",
     title: "The returns report and the money disagree",
     onclick: "refundsFilter('_mismatch')", on: RREF.cls === "_mismatch"},
  ];
  h += (typeof uiStats === "function") ? uiStats(cards) : "";

  // One chip per class that has rows; each is also the filter.
  h += '<div class="rr-filters">';
  (d.classes || []).forEach(function(c){
    const n = by[c.key] || 0;
    if(!n) return;
    h += '<button class="db-chip' + (RREF.cls === c.key ? ' on' : '') + '" onclick="refundsFilter('
      + jsArg(c.key) + ')"><span class="rr-chip ' + (RREF_TONE[c.key] || "") + '">'
      + esc(c.label) + '</span> <b>' + n + '</b></button>';
  });
  h += (typeof uiHint === "function") ? uiHint(d.rule || "") : "";
  h += '</div>';

  const rows = refundsRows();
  if(!rows.length){
    const cov = d.coverage || {};
    const body = (d.rows || []).length ? "No rows match that filter."
      : (cov.held ? "No returns or refunds between " + esc(d.start) + " and " + esc(d.end) + "."
                  : "No returns stored for this account yet. Press Pull from Amazon above "
                    + "(or wait for the daily pull).");
    host.innerHTML = h + ((typeof uiEmpty === "function") ? uiEmpty("Nothing to show", body)
                                                         : '<div class="cc">' + body + '</div>');
    return;
  }

  h += '<div class="rr-wrap"><table class="rr-tbl kv"><thead><tr>'
    + '<th>Order</th><th>Product</th><th>Returned</th><th>Status</th>'
    + '<th class="num">Report says</th><th class="num">Money back</th>'
    + '<th class="num">Waiting</th><th>Note</th></tr></thead><tbody>';
  rows.forEach(function(r){
    const tone = (r.overdue && r["class"] === "approved_unrefunded") ? "bad"
               : (RREF_TONE[r["class"]] || "");
    // Each cell's content is ONE element, so the phone card (label left,
    // value right) keeps a value and its small second line together.
    const td = (label, cls, html) => '<td data-label="' + label + '"'
      + (cls ? ' class="' + cls + '"' : '') + '><div class="rr-v">' + html + '</div></td>';
    h += '<tr>'
      + td("Order", "", _rrOrderCell(r))
      + td("Product", "", '<span title="' + esc(r.name || "") + '">'
        + esc((r.name || r.sku || "—").slice(0, 60)) + '</span>'
        + '<span class="rr-sub">' + esc(r.sku || "") + '</span>')
      + td("Returned", "", esc(r.return_date || "—")
        + (r.reason ? '<span class="rr-sub">' + esc(r.reason) + '</span>' : ''))
      + td("Status", "", '<span class="rr-chip ' + tone + '">' + esc(r.label) + '</span>'
        + (r.status ? '<span class="rr-sub">' + esc(r.status)
                      + (r.resolution ? " · " + esc(r.resolution) : "") + '</span>' : ''))
      + td("Report says", "num", _rrMoney(r.report_refunded))
      + td("Money back", "num", _rrMoneyCell(r))
      + td("Waiting", "num", _rrWaitCell(r))
      + td("Note", "rr-note", esc(r.note || "")
        + (r.tracking_id ? '<span class="rr-sub">' + esc((r.carrier ? r.carrier + " " : "")
                           + r.tracking_id) + '</span>' : ''))
      + '</tr>';
  });
  h += '</tbody></table></div>';
  host.innerHTML = h;
}
