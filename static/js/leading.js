// static/js/leading.js — yesterday against its own history, in sigma.
//
//     Orbit's Leading Indicators screen: each figure for yesterday, next to the
//     historical mean and standard deviation, in standard deviations, with an
//     ON TRACK status.
//
// The screen has to SHOW ITS WORKING. A bare "3.1σ" is a number to be argued
// with; "312 sessions, where this account normally does 180 give or take 42" is
// a statement anyone can check. So every row carries the mean and the deviation
// it was judged against, and a row that could not be judged says why in words
// rather than showing a dash.
//
// All the arithmetic is in domain/leading.py. Nothing here recomputes a sigma, a
// mean or a direction — the sign already means "better" for every indicator, so
// this file has one colour rule rather than eight.

let LEAD = { data: null, note: "", loading: false };

function _leadQs() { return (typeof scopeQs === "function") ? scopeQs() : ""; }

function leadFmt(v, kind) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  if (kind === "money") {
    const c = (typeof CURRENCY_SYMBOL !== "undefined" && CURRENCY_SYMBOL) ? CURRENCY_SYMBOL : "";
    return c + n.toFixed(2);
  }
  if (kind === "percent") return n.toFixed(2) + "%";
  return Math.round(n).toLocaleString();
}

function leadSigma(s) {
  if (s === null || s === undefined) return '<span class="cc">—</span>';
  const cls = s <= -2 ? "ld-bad" : (s <= -1 ? "ld-warn" : (s >= 2 ? "ld-good" : "ld-mid"));
  return '<span class="' + cls + '">' + (s > 0 ? "+" : "") + s.toFixed(2) + "σ</span>";
}

function leadStatus(st) {
  if (st === "on_track") return '<span class="ld-pill ok">On track</span>';
  if (st === "watch") return '<span class="ld-pill warn">Worth a look</span>';
  if (st === "off") return '<span class="ld-pill off">Off track</span>';
  // Not a pass and not a failure. Too little history, or a day Amazon has not
  // reported — both genuinely unjudged, and a tick would claim otherwise.
  return '<span class="ld-pill unk">Not enough to say</span>';
}

// A bare sparkline, drawn as an inline SVG. No library: the whole point is a
// shape, and the shape is fourteen points.
function leadSpark(trail) {
  if (!trail || trail.length < 2) return "";
  const vs = trail.map(function (p) { return Number(p.v); }).filter(function (n) { return !isNaN(n); });
  if (vs.length < 2) return "";
  const min = Math.min.apply(null, vs), max = Math.max.apply(null, vs);
  const span = (max - min) || 1;
  const w = 92, h = 22;
  const pts = vs.map(function (v, i) {
    const x = (i / (vs.length - 1)) * w;
    const y = h - ((v - min) / span) * h;
    return x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  return '<svg class="ld-spark" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h +
         '" preserveAspectRatio="none"><polyline points="' + pts + '" fill="none" ' +
         'stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';
}

function leadRender() {
  const box = document.getElementById("ld_body");
  if (!box) return;
  if (LEAD.loading) { box.innerHTML = '<div class="cc" style="padding:14px">Loading…</div>'; return; }
  if (LEAD.note) { box.innerHTML = '<div class="sresfail">' + esc(LEAD.note) + "</div>"; return; }
  const d = LEAD.data;
  if (!d) { box.innerHTML = ""; return; }

  let head = '<div class="ld-head">' +
    '<div><div class="ld-day">' + esc(d.day) + "</div>" +
    '<div class="cc" style="font-size:11.5px">Compared with the ' + d.window_days +
    " days before it. A figure needs " + d.min_days +
    " days of history before it can be judged at all.</div></div>" +
    '<div class="ld-counts">' +
    '<span class="ld-pill off">' + d.off + " off track</span>" +
    '<span class="ld-pill warn">' + d.watch + " worth a look</span>" +
    '<span class="ld-pill ok">' + d.on_track + " on track</span>" +
    '<span class="ld-pill unk">' + d.unknown + " not enough to say</span>" +
    "</div></div>";

  if (d.note) {
    head += '<div class="issuesbox" style="background:#241f10;border:1px solid #3a3320;' +
            'color:#e6d9b8">' + esc(d.note) + "</div>";
  }

  let html = head + '<div class="card" style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
    "<th>Figure</th><th>Yesterday</th><th>Usually</th><th>Give or take</th>" +
    "<th>How unusual</th><th>Last fortnight</th><th>Status</th>" +
    "</tr></thead><tbody>";
  (d.indicators || []).forEach(function (i) {
    html += "<tr>" +
      '<td><div style="font-weight:600">' + esc(i.label) + "</div>" +
      '<div class="cc" style="font-size:11px;max-width:280px">' + esc(i.blurb) + "</div></td>" +
      '<td style="font-weight:600">' + leadFmt(i.value, i.kind) + "</td>" +
      "<td>" + leadFmt(i.mean, i.kind) + "</td>" +
      // The deviation is what makes the sigma believable — without it the
      // reader has no way to tell a big move from a noisy figure.
      '<td class="cc">' + (i.stdev === null || i.stdev === undefined
                            ? "—" : "± " + leadFmt(i.stdev, i.kind)) + "</td>" +
      "<td>" + leadSigma(i.sigma) +
      (i.change_pct !== null && i.change_pct !== undefined
        ? '<div class="cc" style="font-size:11px">' +
          (i.change_pct > 0 ? "+" : "") + i.change_pct.toFixed(1) + "% vs usual</div>" : "") +
      "</td>" +
      '<td class="ld-sparkcell">' + leadSpark(i.trail) +
      '<div class="cc" style="font-size:10.5px">' + i.days + " days</div></td>" +
      "<td>" + leadStatus(i.status) +
      // Why, in words, whenever there is no judgement to show.
      (i.note ? '<div class="cc" style="font-size:11px;max-width:220px">' +
                esc(i.note) + "</div>" : "") +
      "</td></tr>";
  });
  html += "</tbody></table></div>";
  box.innerHTML = html;
}

async function leadLoad() {
  LEAD.loading = true; LEAD.note = ""; leadRender();
  try {
    const j = await (await fetch("/leading" + _leadQs())).json();
    if (j && j.ok) { LEAD.data = j; }
    else { LEAD.note = (j && j.error) || "Could not read the indicators."; }
  } catch (e) {
    LEAD.note = "Could not read the indicators: " + e;
  }
  LEAD.loading = false;
  leadRender();
}
