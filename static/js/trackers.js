// static/js/trackers.js — the four trackers and the alert list.
//
//     Orbit's menu has All Trackers, BSR Tracker, BuyBox Tracker, Price Tracker,
//     Fee Tracker and Alerts.
//
// One screen with a tab each. The four are the same table pointed at a different
// number, so five separate screens would be four copies of one table drifting
// apart — and the first thing to drift would be how each one decides that a row
// is off target, which is the only judgement the screen makes.
//
// The engine (domain/trackers.py) does all of that judging. This file draws what
// it is told and never re-derives it: no thresholds here, no "which way is good"
// here. That matters because a sales rank of 900 beats 4,000 while a price of
// 9.99 does not beat 12.99, and a second opinion about which is which — held in
// JavaScript, invisible from the Python — is exactly the bug nobody would find.

let TRK = { metric: "", metrics: {}, rows: [], loading: false };

// Which account and marketplace this screen is about. Through the one shared
// builder rather than a fifth hand-rolled copy -- see static/js/scopeq.js for
// the two real faults that comparing the previous four turned up.
function _trkQs() { return (typeof scopeQs === "function") ? scopeQs() : ""; }

function trkFmt(v, kind, cur) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  if (kind === "money") return (cur || "") + n.toFixed(2);
  if (kind === "rank") return "#" + Math.round(n).toLocaleString();
  if (kind === "percent") return n.toFixed(1) + "%";
  return String(n);
}

// Drift is already signed so that POSITIVE MEANS WORSE for every metric,
// whichever direction better happens to be. Reading it any other way here would
// re-introduce the per-metric question the engine exists to have answered once.
function trkDrift(d) {
  if (d === null || d === undefined) return '<span class="cc">—</span>';
  const pct = (d * 100);
  const cls = d > 0 ? "trkbad" : "trkgood";
  const sign = d > 0 ? "+" : "";
  return '<span class="' + cls + '">' + sign + pct.toFixed(1) + "%</span>";
}

function trkStatus(s) {
  if (s === "off") return '<span class="trkpill off">Off target</span>';
  if (s === "ok") return '<span class="trkpill ok">On target</span>';
  // NOT a tick and NOT a cross. "Could not be read" and "no target set" are
  // both genuinely unknown, and showing either as a pass is how a monitoring
  // screen starts lying.
  return '<span class="trkpill unk">Not known</span>';
}

function trkCur() {
  return (typeof curSymbol === "function") ? curSymbol("") : "";
}

function trkTabs() {
  const box = document.getElementById("trk_tabs");
  if (!box) return;
  const ms = TRK.metrics || {};
  let html = '<div class="stk-tab' + (TRK.metric ? "" : " on") +
             '" onclick="trkTab(\'\')">All trackers</div>';
  Object.keys(ms).forEach(function (k) {
    const m = ms[k];
    const on = (TRK.metric === k) ? " on" : "";
    html += '<div class="stk-tab' + on + '" onclick="trkTab(\'' + k + '\')">' +
            esc(m.tracker || k) + "</div>";
  });
  box.innerHTML = html;
}

function trkTab(m) {
  TRK.metric = m || "";
  trkTabs();
  trkRender();
}

// WHAT THE SCREEN SAYS BEFORE YOU READ ANYTHING.
//
// This page opened with a table. A table makes you do the reading before you
// know anything, and most of the time nobody does. These four are the state of
// the account in one glance: how much is watched, how much is wrong, how much
// is unjudged, and when it was last looked at.
function trkStatCards() {
  const rows = TRK.rows || [];
  const off = rows.filter(function (r) { return r.status === "off"; }).length;
  const unk = rows.filter(function (r) { return r.status === "unknown"; }).length;
  const last = rows.map(function (r) { return r.last_at || ""; })
                   .filter(Boolean).sort().pop();
  return uiStats([
    { label: "Being watched", value: rows.length,
      note: rows.length ? "across " + new Set(rows.map(function (r) { return r.asin; })).size +
            " product(s)" : "nothing yet" },
    { label: "Off target", value: off, tone: off ? "bad" : "",
      note: off ? "worth acting on" : "nothing is off" },
    // Not a failure and not a pass -- no reading, or no target set.
    { label: "Not known", value: unk, tone: unk ? "warn" : "",
      note: "no reading, or no target set" },
    { label: "Last checked", value: last ? esc(last.slice(0, 16)) : "never",
      note: "nothing is read until you press Check now" },
  ]);
}

function trkRender() {
  const box = document.getElementById("trk_body");
  if (!box) return;
  const cur = trkCur();
  const rows = TRK.metric ? TRK.rows.filter(function (r) { return r.metric === TRK.metric; })
                          : TRK.rows;
  if (!rows.length) {
    // An empty screen has to say what to DO, not just that it is empty. The
    // trackers are opt-in per ASIN, so "nothing here" is the normal first state
    // and needs to read as a starting point rather than a failure.
    box.innerHTML = trkStatCards() +
      uiEmpty("Nothing is being tracked yet",
        "A tracker watches one number on one listing and tells you when it moves " +
        "away from what you wanted. Add an ASIN below, choose which number to " +
        "watch and what you are aiming for, then press <b>Check now</b>. Nothing " +
        "is read from Amazon until you do — each check costs an API call, so it " +
        "happens when you ask.") +
      trkAddForm();
    return;
  }
  let html = trkStatCards() + trkAddForm() +
    uiPanel("Everything being watched",
            "Drift is measured against the target you set, and positive always " +
            "means worse — whichever direction better happens to be for that number.",
    '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
    "<th>Product</th><th>Tracker</th><th>Now</th><th>Target</th><th>Drift</th>" +
    "<th>Change</th><th>Status</th><th>Last read</th><th></th>" +
    "</tr></thead><tbody>");
  rows.forEach(function (r) {
    html += "<tr>" +
      "<td><div style=\"font-weight:600\">" + esc(r.asin) + "</div>" +
      '<div class="cc" style="font-size:11px">' + esc((r.name || "").slice(0, 60)) + "</div></td>" +
      "<td>" + esc(r.tracker) + "</td>" +
      "<td>" + trkFmt(r.value, r.kind, cur) + "</td>" +
      '<td><input class="ed trktgt" style="width:88px;padding:3px 6px;font-size:12px" ' +
      'value="' + (r.target === null || r.target === undefined ? "" : r.target) + '" ' +
      "onchange=\"trkSetTarget('" + r.asin + "','" + r.metric + "',this.value)\"></td>" +
      "<td>" + trkDrift(r.drift) + "</td>" +
      "<td>" + (r.change === null || r.change === undefined ? '<span class="cc">—</span>'
                                                           : trkFmt(r.change, r.kind, cur)) + "</td>" +
      "<td>" + trkStatus(r.status) + "</td>" +
      '<td class="cc" style="font-size:11px">' + esc(r.last_at || "never") +
      (r.points ? ' <span class="cc">(' + r.points + ")</span>" : "") + "</td>" +
      '<td><button class="ib" title="Stop tracking this" onclick="trkStop(\'' +
      r.asin + "','" + r.metric + "')\"><i class=\"ti ti-x\"></i></button></td>" +
      "</tr>";
  });
  html += "</tbody></table></div></div>";
  box.innerHTML = html;
}

function trkAddForm() {
  const ms = TRK.metrics || {};
  let opts = "";
  Object.keys(ms).forEach(function (k) {
    opts += '<option value="' + k + '">' + esc(ms[k].label || k) + "</option>";
  });
  // WAS A MOSTLY-EMPTY BOX. The fields were laid out with flex and a wide
  // explanatory note, which pushed them into the right-hand corner of a card
  // that was otherwise blank -- most of a screen given over to nothing. It is a
  // toolbar now: the controls sit together on the left, at the size they need,
  // and the note goes underneath where it belongs.
  return uiToolbar(
    '<span class="ui-lbl">Watch a number</span>' +
    '<input id="trk_asin" class="ed" style="width:140px" placeholder="B0XXXXXXXX">' +
    '<select id="trk_metric" class="ed" style="width:160px">' + opts + "</select>" +
    '<input id="trk_target" class="ed" style="width:110px" placeholder="target (optional)">' +
    '<button class="primary" onclick="trkAdd()"><i class="ti ti-plus"></i> Track it</button>',
    '<span class="cc" style="font-size:11px;max-width:330px;text-align:right">' +
    "Without a target the value is recorded but nothing can be off track — " +
    "there is nothing to be off.</span>");
}

async function trkLoad() {
  const box = document.getElementById("trk_body");
  if (box && !TRK.rows.length) box.innerHTML = '<div class="cc" style="padding:14px">Loading…</div>';
  try {
    const j = await (await fetch("/trackers" + _trkQs())).json();
    if (!j.ok) { if (box) box.innerHTML = '<div class="sresfail">' + esc(j.error || "failed") + "</div>"; return; }
    TRK.metrics = j.metrics || {};
    TRK.rows = j.rows || [];
  } catch (e) {
    if (box) box.innerHTML = '<div class="sresfail">' + esc(String(e)) + "</div>";
    return;
  }
  trkTabs();
  trkRender();
  trkBadge();
}

async function trkAdd() {
  const asin = (document.getElementById("trk_asin") || {}).value || "";
  const metric = (document.getElementById("trk_metric") || {}).value || "";
  const target = (document.getElementById("trk_target") || {}).value || "";
  if (!asin.trim()) { toast("Enter an ASIN."); return; }
  const j = await (await fetch("/trackers/watch" + _trkQs(), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asin: asin, metric: metric, on: true, target: target })
  })).json();
  if (!j.ok) { toast(j.error || "Could not track that."); return; }
  const a = document.getElementById("trk_asin"); if (a) a.value = "";
  trkLoad();
}

async function trkSetTarget(asin, metric, value) {
  const j = await (await fetch("/trackers/watch" + _trkQs(), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asin: asin, metric: metric, target: value })
  })).json();
  if (!j.ok) { toast(j.error || "Could not save that target."); return; }
  trkLoad();
}

async function trkStop(asin, metric) {
  await fetch("/trackers/watch" + _trkQs(), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asin: asin, metric: metric, on: false })
  });
  trkLoad();
}

async function trkRefresh() {
  if (TRK.loading) return;
  TRK.loading = true;
  const btn = document.getElementById("trk_refresh");
  const was = btn ? btn.innerHTML : "";
  if (btn) { btn.innerHTML = '<i class="ti ti-loader"></i> Checking…'; btn.disabled = true; }
  try {
    const j = await (await fetch("/trackers/refresh" + _trkQs(), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    })).json();
    if (!j.ok) toast(j.error || "Could not check.");
    else {
      // read AND stored, because they differ exactly when something failed and
      // one combined number would hide it.
      let msg = j.stored + " reading" + (j.stored === 1 ? "" : "s") +
                " from " + j.asins + " ASIN" + (j.asins === 1 ? "" : "s");
      if (j.read !== j.stored) msg += " (" + j.read + " read)";
      if (j.errors && j.errors.length) msg += " — " + j.errors.length + " problem(s)";
      toast(msg);
    }
  } catch (e) {
    toast(String(e));
  }
  if (btn) { btn.innerHTML = was; btn.disabled = false; }
  TRK.loading = false;
  trkLoad();
}

// ---- alerts ----------------------------------------------------------------

async function alertsLoad() {
  const box = document.getElementById("alr_body");
  if (box) box.innerHTML = '<div class="cc" style="padding:14px">Loading…</div>';
  let j;
  try {
    j = await (await fetch("/trackers/alerts" + _trkQs())).json();
  } catch (e) {
    if (box) box.innerHTML = '<div class="sresfail">' + esc(String(e)) + "</div>";
    return;
  }
  if (!j.ok) { if (box) box.innerHTML = '<div class="sresfail">' + esc(j.error || "failed") + "</div>"; return; }
  const cur = trkCur();
  if (!j.rows.length) {
    box.innerHTML =
      uiStats([{ label: "Off target", value: 0, tone: "good",
                 note: "nothing needs attention" }]) +
      uiEmpty("Nothing is off target",
        "Only numbers with a target set can be off one. Anything that could not " +
        "be read is shown as <b>not known</b> on the Trackers screen rather than " +
        "counted as fine here.");
    trkBadge(0);
    return;
  }
  // The worst one, named, above the list -- so the screen says something before
  // it is read rather than after.
  const worst = j.rows[0] || {};
  let html = uiStats([
    { label: "Off target", value: j.count, tone: "bad" },
    { label: "Worst", value: esc(worst.asin || "—"),
      note: worst.tracker || "" },
    { label: "How far off",
      value: (worst.drift === null || worst.drift === undefined)
        ? "—" : ("+" + (worst.drift * 100).toFixed(0) + "%"),
      note: "against the target you set" },
  ]) +
  uiPanel("Everything off target", "Worst first.",
    '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
    "<th>Product</th><th>Tracker</th><th>Now</th><th>Target</th><th>Drift</th><th>Last read</th>" +
    "</tr></thead><tbody>");
  j.rows.forEach(function (r) {
    html += "<tr><td><div style=\"font-weight:600\">" + esc(r.asin) + "</div>" +
      '<div class="cc" style="font-size:11px">' + esc((r.name || "").slice(0, 60)) + "</div></td>" +
      "<td>" + esc(r.tracker) + "</td>" +
      "<td>" + trkFmt(r.value, r.kind, cur) + "</td>" +
      "<td>" + trkFmt(r.target, r.kind, cur) + "</td>" +
      "<td>" + trkDrift(r.drift) + "</td>" +
      '<td class="cc" style="font-size:11px">' + esc(r.last_at || "never") + "</td></tr>";
  });
  html += "</tbody></table></div></div>";
  box.innerHTML = html;
  trkBadge(j.count);
}

// The sidebar badge. Counted once, over all four trackers, because four badges
// would be four things to check and four chances to miss the one that mattered.
async function trkBadge(known) {
  const el = document.getElementById("alr_badge");
  if (!el) return;
  let n = known;
  if (n === undefined || n === null) {
    try {
      const j = await (await fetch("/trackers/alerts" + _trkQs())).json();
      n = j && j.ok ? j.count : 0;
    } catch (e) { n = 0; }
  }
  if (n > 0) { el.textContent = String(n); el.style.display = "inline-block"; }
  else { el.style.display = "none"; el.textContent = ""; }
  // A collapsed nav group has to repeat its children's badges, or shutting the
  // group would hide the alert.
  if (typeof navGroupBadges === "function") navGroupBadges();
}
