// static/js/sqp.js — Keywords (Search Query Performance).
//
// The only report that shows the SEARCH rather than what happened after somebody
// arrived. Its whole value is the share: your slice of what a query produced
// across every seller. That is what turns "we sold four" into "we sold four out
// of two hundred, so there are a hundred and ninety-six we did not".
//
// THE SCREEN'S JOB IS TO NAME THE BREAK, not to show a wall of percentages. Four
// steps, four completely different jobs:
//
//   not seen      ranking and advertising — the page is never looked at
//   not clicked   main image, title, price, review count
//   not added     the listing page itself
//   not bought    postage, delivery date, the basket
//
// Averaged into "conversion is bad" those are none of them. So the diagnosis
// comes from the server (domain/search_query.py) and is drawn here as a sentence
// a person can act on.

let SQP = { data: null, note: "", loading: false, filter: "" };

function _sqpQs(extra) {
  return (typeof scopeQs === "function") ? scopeQs(extra) : "";
}

function sqpPct(v) {
  if (v === null || v === undefined) return '<span class="cc">—</span>';
  return (v * 100).toFixed(1) + "%";
}

function sqpNum(v) {
  if (v === null || v === undefined) return "—";
  return Math.round(v).toLocaleString();
}

// Your figure over the query's total, drawn as one cell. Showing both is what
// makes the share checkable rather than a number to be believed.
function sqpCell(mine, total, share) {
  if (mine === null || mine === undefined) return '<span class="cc">—</span>';
  let s = "<b>" + sqpNum(mine) + "</b>";
  if (total !== null && total !== undefined) {
    s += '<span class="cc"> / ' + sqpNum(total) + "</span>";
  }
  if (share !== null && share !== undefined) {
    const cls = share < (SQP.data ? SQP.data.weak_share : 0.15) ? "trkbad" : "trkgood";
    s += '<div class="' + cls + '" style="font-size:11px">' + sqpPct(share) + "</div>";
  }
  return s;
}

function sqpRender() {
  const box = document.getElementById("sqp_body");
  if (!box) return;
  if (SQP.loading) { box.innerHTML = '<div class="cc" style="padding:14px">Asking Amazon for the report — these are built on request and can take a minute…</div>'; return; }
  if (SQP.note) { box.innerHTML = '<div class="issuesbox" style="background:#241f10;border:1px solid #3a3320;color:#e6d9b8">' + esc(SQP.note) + "</div>"; return; }
  const d = SQP.data;
  if (!d) { box.innerHTML = ""; return; }

  let html = '<div class="ld-head"><div>' +
    '<div class="ld-day">' + esc(d.start) + " → " + esc(d.end) + "</div>" +
    '<div class="cc" style="font-size:11.5px">' + d.queries_read +
    " search queries. A query with fewer than " + d.min_impressions +
    " impressions is shown but not judged — one click on nine impressions is an " +
    "11% share and means nothing." +
    (d.source === "reused" ? " This report was built by Amazon at " +
      esc(d.built_at || "an earlier time") + " and reused rather than rebuilt." : "") +
    "</div></div></div>";

  if (d.note) {
    html += '<div class="issuesbox" style="background:#241f10;border:1px solid #3a3320;' +
            'color:#e6d9b8;margin-bottom:12px">' + esc(d.note) + "</div>";
  }

  // ---- where the funnel breaks, across all queries ------------------------
  const s = d.summary || {};
  const order = ["impression", "click", "cart", "purchase", "none", "unreadable"];
  html += '<div class="sqp-cards">';
  order.forEach(function (k) {
    const c = s[k];
    if (!c || !c.count) return;
    const on = SQP.filter === k ? " on" : "";
    html += '<div class="sqp-card' + on + '" onclick="sqpFilter(\'' + k + '\')">' +
      '<div class="sqp-n">' + c.count + "</div>" +
      '<div class="sqp-l">' + esc(c.label) + "</div>" +
      (c.missed ? '<div class="cc" style="font-size:11px">' + sqpNum(c.missed) +
                  " sales went elsewhere</div>" : "") +
      (c.do ? '<div class="cc" style="font-size:11px;margin-top:5px;line-height:1.45">' +
              esc(c.do) + "</div>" : "") +
      "</div>";
  });
  html += "</div>";
  if (SQP.filter) {
    html += '<div style="margin:8px 0"><button class="db-chip" onclick="sqpFilter(\'\')">' +
            '<i class="ti ti-x"></i> Show every query</button></div>';
  }

  // ---- the queries --------------------------------------------------------
  let rows = d.rows || [];
  if (SQP.filter) {
    rows = rows.filter(function (r) {
      const b = r.break || ((r.note || "").indexOf("Too few") === 0 ||
                            (r.note || "").indexOf("Amazon reported no") === 0
                            ? "unreadable" : "none");
      return b === SQP.filter;
    });
  }
  if (!rows.length) {
    html += '<div class="card" style="padding:18px"><div class="cc">No queries to show.</div></div>';
    box.innerHTML = html;
    return;
  }
  html += '<div class="card" style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
    "<th>Search</th><th>Seen</th><th>Clicked</th><th>Added</th><th>Bought</th>" +
    "<th>Missed</th><th>Where it breaks</th></tr></thead><tbody>";
  rows.forEach(function (r) {
    const sh = r.shares || {};
    html += "<tr>" +
      '<td><div style="font-weight:600">' + esc(r.query) + "</div>" +
      (r.asin ? '<div class="cc" style="font-size:11px">' + esc(r.asin) + "</div>" : "") + "</td>" +
      "<td>" + sqpCell(r.impressions, r.impressions_total, sh.impression) + "</td>" +
      "<td>" + sqpCell(r.clicks, r.clicks_total, sh.click) + "</td>" +
      "<td>" + sqpCell(r.cart_adds, r.cart_adds_total, sh.cart) + "</td>" +
      "<td>" + sqpCell(r.purchases, r.purchases_total, sh.purchase) + "</td>" +
      '<td style="font-weight:600">' + sqpNum(r.missed) + "</td>" +
      "<td>" + (r.break
        ? '<div class="ld-pill off">' + esc((d.summary[r.break] || {}).label || r.break) + "</div>" +
          '<div class="cc" style="font-size:11px;max-width:300px;margin-top:4px">' +
          esc(r.means) + " " + esc(r.do) + "</div>"
        // Not a tick. Too little data and a healthy funnel are different things.
        : '<span class="cc" style="font-size:11.5px">' + esc(r.note || "") + "</span>") +
      "</td></tr>";
  });
  html += "</tbody></table></div>";
  box.innerHTML = html;
}

function sqpFilter(k) {
  SQP.filter = (SQP.filter === k) ? "" : k;
  sqpRender();
}

async function sqpLoad() {
  SQP.loading = true; SQP.note = ""; sqpRender();
  try {
    const j = await (await fetch("/sqp" + _sqpQs())).json();
    if (j && j.ok) { SQP.data = j; }
    else if (j && (j.reason === "not_brand_registered" || j.reason === "fatal" ||
                   j.reason === "no_data")) {
      // The distinction that matters: a refusal is not an empty week. Reported
      // as "no keywords", it reads as "nobody searched for us", which is a
      // completely different and much more alarming thing. Where Amazon itself
      // will not say which it is, the message says BOTH and how to tell.
      SQP.note = j.error;
    } else {
      SQP.note = (j && j.error) || "Could not get the report.";
    }
  } catch (e) {
    SQP.note = "Could not get the report: " + e;
  }
  SQP.loading = false;
  sqpRender();
}
