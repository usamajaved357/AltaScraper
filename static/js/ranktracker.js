// static/js/ranktracker.js — Rank Tracker.
//
// A list of keyword + ASIN pairs to follow, and a Check Now button. Nothing on
// a timer: a check happens because somebody pressed the button, which is the
// whole design.
//
// WHAT THIS MEASURES, AND WHAT IT REFUSES TO PRETEND TO MEASURE.
//
// It does not measure organic rank. Nothing available here can. SP-API has no
// endpoint that returns "your position in the search results for this word",
// and the other way to get it — loading the search page and counting — is
// against Amazon's terms and would put the real selling accounts at risk. So
// the column is not filled with a guess wearing the name "position".
//
// What IS measured is the Search Query Performance signal for that keyword and
// ASIN in the chosen week: impressions, clicks, purchases. That is search
// VISIBILITY. It answers "is this keyword showing my product, and does it
// convert" — a genuinely useful question, and a different one from "am I fourth
// or fourteenth". Every label on this screen says which of the two it is.
//
// A KEYWORD WITH NO DATA IS RECORDED AS ZERO, NOT SKIPPED. "This keyword
// produced no impressions that week" is a finding. A gap in the history is not,
// and six months later it reads as "never checked" rather than "checked, and
// there was nothing".

let KRT = { watch: [], history: [], counts: null, note: "", loading: false,
            checking: false, what: "" };

function _krtQs(extra) {
  return (typeof scopeQs === "function") ? scopeQs(extra) : "";
}
function _krtEsc(s) {
  return (typeof esc === "function") ? esc(s) : String(s == null ? "" : s);
}

async function krtLoad() {
  KRT.loading = true; krtRender();
  try {
    const j = await (await fetch("/keywords/rank-tracker" + _krtQs())).json();
    if (j && j.ok) {
      KRT.watch = j.watch || []; KRT.history = j.history || [];
      KRT.counts = j.counts || null; KRT.what = j.what_this_measures || "";
      KRT.note = "";
    } else {
      KRT.note = (j && j.error) || "Could not read the tracker.";
    }
  } catch (e) { KRT.note = "Could not read the tracker: " + e; }
  KRT.loading = false; krtRender();
}

async function krtAdd() {
  const kw = ((document.getElementById("krt_kw") || {}).value || "").trim();
  const asin = ((document.getElementById("krt_asin") || {}).value || "").trim().toUpperCase();
  if (!kw || !asin) {
    KRT.note = "Both a keyword and one of your ASINs are needed."; krtRender(); return;
  }
  try {
    const j = await (await fetch("/keywords/rank-tracker/add", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign(
        (typeof acctBody === "function") ? acctBody({}) : {},
        { keyword: kw, asin: asin,
          marketplace: (typeof WS_MARKET !== "undefined" ? WS_MARKET : "") }))
    })).json();
    if (j && j.ok) {
      KRT.watch = j.watch || []; KRT.note = "";
      const a = document.getElementById("krt_kw"); if (a) a.value = "";
    } else { KRT.note = (j && j.error) || "Could not add it."; }
  } catch (e) { KRT.note = "Could not add it: " + e; }
  krtRender();
}

async function krtRemove(kw, asin) {
  try {
    const j = await (await fetch("/keywords/rank-tracker/remove", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign(
        (typeof acctBody === "function") ? acctBody({}) : {},
        { keyword: kw, asin: asin,
          marketplace: (typeof WS_MARKET !== "undefined" ? WS_MARKET : "") }))
    })).json();
    if (j && j.ok) KRT.watch = j.watch || [];
  } catch (e) { KRT.note = "Could not remove it: " + e; }
  krtRender();
}

// ONE PULL PER ASIN, NOT PER PAIR — the server groups them, because the SQP
// report is per ASIN and already contains every query for it. Ten keywords on
// one ASIN is one report. Amazon rations these at about one a minute, so the
// button says how many reports it is about to ask for rather than starting an
// unknown amount of waiting.
async function krtCheckNow() {
  if (!KRT.watch.length) {
    KRT.note = "Add a keyword and an ASIN first."; krtRender(); return;
  }
  const asins = [...new Set(KRT.watch.map(function (w) { return w.asin; }))];
  const msg = "Check " + KRT.watch.length + " keyword"
    + (KRT.watch.length > 1 ? "s" : "") + " across " + asins.length + " ASIN"
    + (asins.length > 1 ? "s" : "") + "?\n\n"
    + "That is " + asins.length + " Search Query Performance report"
    + (asins.length > 1 ? "s" : "") + " from Amazon. Reports are built on "
    + "request and rationed to roughly one a minute, so this can take a while "
    + "the first time for a given week.\n\nNothing runs on a timer — this "
    + "happens only when you press OK.";
  if (!await uiConfirm(msg)) return;

  KRT.checking = true; KRT.note = ""; krtRender();
  try {
    const start = (document.getElementById("krt_start") || {}).value || "";
    const end = (document.getElementById("krt_end") || {}).value || "";
    const j = await (await fetch("/keywords/rank-tracker/check", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign(
        (typeof acctBody === "function") ? acctBody({}) : {},
        { start: start, end: end,
          marketplace: (typeof WS_MARKET !== "undefined" ? WS_MARKET : "") }))
    })).json();
    if (j && j.ok) {
      KRT.watch = j.watch || KRT.watch; KRT.history = j.history || [];
      let n = "Checked " + j.checked + " keyword" + (j.checked === 1 ? "" : "s")
            + " from " + j.asins_pulled + " report"
            + (j.asins_pulled === 1 ? "" : "s") + ".";
      if ((j.failed || []).length) {
        n += " " + j.failed.length + " ASIN"
          + (j.failed.length > 1 ? "s" : "") + " could not be read: "
          + j.failed.map(function (f) { return f.asin + " (" + f.error + ")"; })
              .join("; ");
      }
      KRT.note = n;
    } else { KRT.note = (j && j.error) || "The check failed."; }
  } catch (e) { KRT.note = "The check failed: " + e; }
  KRT.checking = false; krtRender();
}

function krtRender() {
  const host = document.getElementById("ranktrackerbody");
  if (!host) return;
  let h = "";

  if (KRT.what) {
    h += '<div class="gendiag" style="margin-bottom:12px"><b>What this '
       + 'measures:</b> ' + _krtEsc(KRT.what) + "</div>";
  }
  if (KRT.note) h += '<div class="gendiag">' + _krtEsc(KRT.note) + "</div>";

  h += '<div class="wstoolbar" style="gap:8px;margin:10px 0">'
     + '<input id="krt_kw" class="ed" placeholder="Keyword to follow…" style="min-width:220px">'
     + '<input id="krt_asin" class="ed" placeholder="One of YOUR ASINs" style="min-width:150px">'
     + '<button class="mktbtn on" onclick="krtAdd()">Add</button>'
     + '<span style="flex:1"></span>'
     + '<label class="cc">Week <input id="krt_start" type="date" class="ed"></label>'
     + '<label class="cc">to <input id="krt_end" type="date" class="ed"></label>'
     + '<button class="mktbtn" onclick="krtCheckNow()"' + (KRT.checking ? " disabled" : "")
     + ' title="Pull Search Query Performance once, now, for the watched ASINs. '
     + 'Nothing runs automatically.">'
     + (KRT.checking ? '<span class="genspin"></span> Checking…'
                     : '<i class="ti ti-refresh"></i> Check now')
     + "</button></div>";

  if (!KRT.watch.length) {
    h += '<div class="empty">Nothing is being tracked yet. Add a keyword and '
       + 'one of your own ASINs above, or press Track on a row in ASIN '
       + "Insights.</div>";
  } else {
    h += '<table class="tbl"><thead><tr><th>Keyword</th><th>ASIN</th>'
       + '<th title="How many times your listing was shown for this query in '
       + 'the checked week.">Impressions</th><th>Clicks</th><th>Purchases</th>'
       + '<th title="Organic position is not available from any source this app '
       + 'is allowed to use. It stays empty rather than being guessed.">'
       + "Organic position</th><th>Last checked</th><th></th></tr></thead><tbody>";
    // The newest check per pair — the table is "where things stand", the chart
    // below it is the history.
    const latest = {};
    KRT.history.forEach(function (r) {
      const k = r.keyword + " " + r.asin;
      if (!latest[k]) latest[k] = r;      // history comes back newest first
    });
    KRT.watch.forEach(function (w) {
      const r = latest[w.keyword + " " + w.asin];
      h += "<tr><td>" + _krtEsc(w.keyword) + "</td><td>"
         + '<span class="asin">' + _krtEsc(w.asin) + "</span></td>"
         + "<td>" + (r ? (r.impressions || 0).toLocaleString() : '<span class="cc">not checked</span>') + "</td>"
         + "<td>" + (r ? (r.clicks || 0).toLocaleString() : "") + "</td>"
         + "<td>" + (r ? "<b>" + (r.purchases || 0).toLocaleString() + "</b>" : "") + "</td>"
         + '<td><span class="cc" title="Not measurable without a rank data '
         + 'source or scraping, and scraping is not something this app does.">'
         + "not available</span></td>"
         + "<td>" + (r ? _krtEsc(String(r.checked_at || "").slice(0, 16).replace("T", " "))
                       : '<span class="cc">—</span>') + "</td>"
         + '<td><button class="ghost" onclick="krtRemove(' + "'"
         + _krtEsc(String(w.keyword).replace(/'/g, "\\'")) + "','"
         + _krtEsc(w.asin) + "'" + ')">Remove</button></td></tr>';
    });
    h += "</tbody></table>";

    if (KRT.history.length) {
      h += '<h3 style="margin-top:20px">Every check, newest first</h3>'
         + '<div class="cc" style="margin-bottom:8px">' + KRT.history.length
         + " recorded check" + (KRT.history.length === 1 ? "" : "s")
         + ". A row of zeros means the keyword was checked and produced nothing "
         + "that week — which is different from not having been checked.</div>"
         + '<table class="tbl"><thead><tr><th>Checked</th><th>Keyword</th>'
         + "<th>ASIN</th><th>Week</th><th>Impressions</th><th>Clicks</th>"
         + "<th>Purchases</th></tr></thead><tbody>";
      KRT.history.slice(0, 200).forEach(function (r) {
        h += "<tr><td>" + _krtEsc(String(r.checked_at || "").slice(0, 16).replace("T", " "))
           + "</td><td>" + _krtEsc(r.keyword) + "</td><td>"
           + '<span class="asin">' + _krtEsc(r.asin) + "</span></td><td>"
           + _krtEsc(r.report_start || "—") + "</td><td>"
           + (r.impressions || 0).toLocaleString() + "</td><td>"
           + (r.clicks || 0).toLocaleString() + "</td><td>"
           + (r.purchases || 0).toLocaleString() + "</td></tr>";
      });
      h += "</tbody></table>";
    }
  }
  host.innerHTML = h;
}

function krtOnOpen() {
  const t = new Date();
  const end = new Date(t); end.setDate(t.getDate() - (t.getDay() === 0 ? 1 : t.getDay() + 1));
  const start = new Date(end); start.setDate(end.getDate() - 6);
  const iso = function (d) { return d.toISOString().slice(0, 10); };
  krtLoad().then(function () {
    const s = document.getElementById("krt_start"), e = document.getElementById("krt_end");
    if (s && !s.value) s.value = iso(start);
    if (e && !e.value) e.value = iso(end);
  });
}
