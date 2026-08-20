/* static/js/brief.js -- the weekly brief.
 *
 * Draws GET /brief and nothing else. Every figure and every sentence comes back
 * from domain/weekly_brief.py; there is no arithmetic in this file and there
 * must not be, or the screen and the data could disagree about the same week.
 *
 * IT IS THE ONE SCREEN NOT SCOPED TO THE OPEN ACCOUNT, and that is the point.
 * Everything else answers for the account you chose, which is right for working
 * and wrong for noticing -- the account with a problem this week is the one
 * nobody opened.
 *
 * WHAT COULD NOT BE LOOKED AT IS DRAWN AS PROMINENTLY AS WHAT COULD. A brief
 * with a silent hole in it is worse than no brief: it reads as "nothing to
 * report" for the part it never read.
 */
var BRIEF = {data: null, loading: false, asked: false};

function _bfEsc(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* A figure, or an em-dash that means "no figure" rather than "zero". */
function _bfNum(v, dp) {
  if (v === null || v === undefined || v === "") return '<span class="cc">—</span>';
  var n = Number(v);
  if (!isFinite(n)) return '<span class="cc">—</span>';
  return n.toFixed(dp === undefined ? 2 : dp);
}

function _bfPct(v) {
  if (v === null || v === undefined) return '<span class="cc">—</span>';
  var n = Number(v);
  var col = n >= 0 ? "var(--ok)" : "var(--red)";
  return '<span style="color:' + col + '">' + (n > 0 ? "+" : "") + n + "%</span>";
}

function briefOnOpen() {
  if (!BRIEF.data && !BRIEF.asked) { BRIEF.asked = true; briefLoad(); }
  briefRender();
}

async function briefLoad() {
  BRIEF.loading = true; briefRender();
  try {
    const j = await (await fetch("/brief")).json();
    BRIEF.data = j;
  } catch (e) {
    BRIEF.data = {ok: false, error: "Could not load the brief: " + e};
  }
  BRIEF.loading = false;
  briefRender();
}

function briefRender() {
  const host = document.getElementById("brief_body");
  if (!host) return;
  const b = BRIEF.data;
  if (BRIEF.loading || !b) {
    host.innerHTML = '<div class="cc" style="padding:16px">Reading every '
      + 'account…</div>';
    return;
  }
  if (!b.ok) {
    host.innerHTML = '<div class="odp-note warn" style="padding:14px">'
      + _bfEsc(b.error || "Could not build the brief.") + "</div>";
    return;
  }

  let h = "";
  if (typeof uiSource === "function") {
    h += uiSource([
      {k: "Covering", v: b.accounts + " account(s)"},
      {k: "Week", v: (b.sales && b.sales.window)
        ? (b.sales.window.start + " → " + b.sales.window.end) : ""},
      {k: "Against", v: (b.sales && b.sales.compared_with)
        ? (b.sales.compared_with.start + " → " + b.sales.compared_with.end) : ""},
    ], b.period_note || "");
  }

  // WHAT COULD NOT BE READ, FIRST. Everything below is only as complete as
  // this list is short, and a reader who does not know that will read a gap as
  // a clean bill of health.
  const gaps = b.could_not_look || [];
  if (gaps.length) {
    h += '<div class="odp-note warn" style="padding:12px;margin:0 0 14px">'
      + '<b>' + gaps.length + " thing" + (gaps.length === 1 ? "" : "s")
      + " could not be looked at</b><ul style=\"margin:6px 0 0;padding-left:18px\">"
      + gaps.map(function (g) {
          return "<li>" + _bfEsc(g) + "</li>";
        }).join("") + "</ul></div>";
  }

  h += _bfSales(b.sales || {});
  h += _bfOffTrack(b.off_track || {});
  h += _bfStock(b.stock || {});
  h += _bfProfit(b.profit || {});
  h += _bfAds(b.ads || {});
  host.innerHTML = h;
}

function _bfWhy(s) {
  return s ? '<div class="cc" style="font-size:11px;line-height:1.5;'
    + 'margin:0 0 10px;max-width:760px">' + _bfEsc(s) + "</div>" : "";
}

function _bfSales(s) {
  const rows = s.rows || [];
  let t = "";
  if (!rows.length) {
    t = '<div class="cc" style="padding:10px">No account had sales figures for '
      + "this week.</div>";
  } else {
    t = '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>'
      + "<th>Account</th><th>Where</th><th>Revenue</th><th>Was</th>"
      + "<th>Change</th><th>Units</th><th>Orders</th></tr></thead><tbody>";
    rows.forEach(function (r) {
      // The currency sits on the FIGURE, not in a column heading -- these rows
      // are in different currencies and a single heading would imply one.
      const cur = r.currency ? (_bfEsc(r.currency) + " ") : "";
      t += "<tr><td><b>" + _bfEsc(r.account) + "</b></td>"
        + "<td>" + _bfEsc(r.marketplace || "—") + "</td>"
        + "<td>" + cur + _bfNum(r.revenue) + "</td>"
        + "<td class=\"cc\">" + cur + _bfNum(r.revenue_prev) + "</td>"
        + "<td>" + _bfPct(r.change_pct) + "</td>"
        + "<td>" + _bfNum(r.units, 0) + "</td>"
        + "<td>" + _bfNum(r.orders, 0) + "</td></tr>";
    });
    t += "</tbody></table></div>";
  }
  const movers = [];
  (s.up || []).forEach(function (r) {
    movers.push("<b>" + _bfEsc(r.account) + "</b> up " + r.change_pct + "%");
  });
  (s.down || []).forEach(function (r) {
    movers.push("<b>" + _bfEsc(r.account) + "</b> down "
                + Math.abs(r.change_pct) + "%");
  });
  const head = movers.length
    ? '<div style="font-size:13px;margin:0 0 8px">' + movers.join(" · ") + "</div>"
    : '<div class="cc" style="font-size:12px;margin:0 0 8px">No account moved '
      + "materially either way.</div>";
  const body = head + _bfWhy(s.why) + _bfWhy(s.read_the_base)
    + _bfWhy(s.no_total) + t;
  return (typeof uiPanel === "function")
    ? uiPanel("What moved", "Seven days against the seven before, per account.", body)
    : body;
}

function _bfOffTrack(o) {
  const reds = o.reds || [];
  let body = _bfWhy(o.why);
  if (!reds.length) {
    body += '<div class="cc" style="padding:10px">Nothing was outside its '
      + "normal range yesterday.</div>";
  } else {
    body += '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>'
      + "<th>Account</th><th>What</th><th>Yesterday</th><th>Normally</th>"
      + "<th>How far out</th></tr></thead><tbody>";
    reds.forEach(function (r) {
      body += "<tr title=\"" + _bfEsc(r.why || "") + "\">"
        + "<td><b>" + _bfEsc(r.account) + "</b></td>"
        + "<td>" + _bfEsc(r.metric) + "</td>"
        + "<td>" + _bfNum(r.value) + "</td>"
        + "<td class=\"cc\">" + _bfNum(r.normal) + "</td>"
        + "<td>" + (r.sigma === null || r.sigma === undefined
            ? '<span class="cc">—</span>'
            : "<b>" + Number(r.sigma).toFixed(1) + "σ</b>") + "</td></tr>";
    });
    body += "</tbody></table></div>";
    if (o.red_count > reds.length) {
      body += '<div class="cc" style="font-size:11px;margin-top:8px">Showing the '
        + reds.length + " furthest out of " + o.red_count + ".</div>";
    }
  }
  return (typeof uiPanel === "function")
    ? uiPanel("What is off", "Yesterday against each account's own history.", body)
    : body;
}

function _bfStock(s) {
  let body = _bfWhy(s.why);
  const out = s.out_now || [], soon = s.running_out || [];
  if (!out.length && !soon.length) {
    body += '<div class="cc" style="padding:10px">Nothing is out of stock or '
      + "inside two weeks of cover.</div>";
  }
  if (out.length) {
    body += '<div style="font-size:12.5px;margin:0 0 6px"><b>'
      + s.out_count + "</b> out of stock now</div><ul style=\"margin:0 0 12px;"
      + "padding-left:18px;font-size:12px\">"
      + out.map(function (r) {
          return "<li>" + _bfEsc(r.account) + " · " + _bfEsc(r.sku)
            + (r.pace ? " — was selling " + r.pace + " a day" : "") + "</li>";
        }).join("") + "</ul>";
  }
  if (soon.length) {
    body += '<div style="font-size:12.5px;margin:0 0 6px"><b>'
      + s.running_out_count + "</b> inside two weeks of cover</div>"
      + "<ul style=\"margin:0;padding-left:18px;font-size:12px\">"
      + soon.map(function (r) {
          return "<li>" + _bfEsc(r.account) + " · " + _bfEsc(r.sku)
            + " — " + r.cover_days + " days left</li>";
        }).join("") + "</ul>";
  }
  return (typeof uiPanel === "function")
    ? uiPanel("What runs out", "Measured over the days each product was in stock.", body)
    : body;
}

function _bfProfit(p) {
  let body = _bfWhy(p.why);
  const rows = p.rows || [];
  if (!rows.length) {
    body += '<div class="cc" style="padding:10px">No account could be checked.</div>';
  } else {
    body += '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>'
      + "<th>Account</th><th>Products with a cost</th><th>Coverage</th>"
      + "<th>Missing</th></tr></thead><tbody>";
    rows.forEach(function (r) {
      const pc = r.coverage_pct;
      const tone = (pc === null || pc === undefined) ? ""
        : (pc >= 95 ? "var(--ok)" : (pc >= 80 ? "var(--warn)" : "var(--red)"));
      body += "<tr><td><b>" + _bfEsc(r.account) + "</b></td>"
        + "<td>" + _bfNum(r.costed, 0) + " of " + _bfNum(r.products, 0) + "</td>"
        + "<td>" + (pc === null || pc === undefined
            ? '<span class="cc">—</span>'
            : '<b style="color:' + tone + '">' + pc + "%</b>") + "</td>"
        + "<td class=\"cc\" style=\"font-size:11px\">"
        + _bfEsc((r.missing_skus || []).join(", ")) + "</td></tr>";
    });
    body += "</tbody></table></div>";
  }
  return (typeof uiPanel === "function")
    ? uiPanel("Whether the profit can be trusted",
        "A product with no cost brings revenue and no cost, so it can only "
        + "flatter the margin.", body)
    : body;
}

function _bfAds(a) {
  let body = _bfWhy(a.why);
  if (!a.connected) {
    body += '<div class="odp-note" style="padding:12px">'
      + _bfEsc((a.notes || [])[0] || "No advertising data.") + "</div>";
  } else {
    body += '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>'
      + "<th>Account</th><th>Spend</th><th>Ad sales</th><th>ACOS</th>"
      + "</tr></thead><tbody>";
    (a.rows || []).forEach(function (r) {
      body += "<tr><td><b>" + _bfEsc(r.account) + "</b></td>"
        + "<td>" + _bfNum(r.spend) + "</td>"
        + "<td>" + _bfNum(r.ad_sales) + "</td>"
        // No sales is not an ACOS of 0% -- it is no ACOS at all.
        + "<td>" + (r.acos_pct === null || r.acos_pct === undefined
            ? '<span class="cc">—</span>' : r.acos_pct + "%") + "</td></tr>";
    });
    body += "</tbody></table></div>";
  }
  return (typeof uiPanel === "function")
    ? uiPanel("What advertising cost", "", body) : body;
}
