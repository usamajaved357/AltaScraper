// static/js/keywordhistory.js — Keyword History.
//
// Everything the other two screens have already pulled, browsable by week, with
// week-over-week movement. This page never calls Amazon, which is what makes it
// instant and free to open — it is the record, not another request.
//
// RANK COUNTS DOWN, AND THAT IS THE TRAP THIS WHOLE SCREEN IS BUILT AROUND.
// Search frequency rank 1 is the MOST searched term in the marketplace. So a
// keyword whose rank FELL from 1500 to 1100 has become MORE popular. Shown raw,
// every arrow on this page would point the wrong way, and somebody would drop a
// keyword that was climbing.
//
// So "moved" is last week's rank MINUS this week's: positive means rising,
// which is what a person means by up. The header says it, the arrows follow it,
// and the server computes it the same way so the two cannot disagree.
//
// AND A GAP IS NOT A FALL. History only holds weeks somebody actually searched
// in — there is no scheduler filling them in. A keyword present in one week and
// absent from the other usually means nobody pulled that week, not that the
// keyword vanished. Those rows are shown, marked, and deliberately NOT counted
// as movements: calling an absent week a 100% drop would be inventing a finding.

let KWH = { weeks: [], rows: [], movers: [], counts: null, note: "",
            loading: false, week: "", prev: "", q: "", tab: "movers" };

function _kwhQs(extra) {
  return (typeof scopeQs === "function") ? scopeQs(extra) : "";
}
function _kwhEsc(s) {
  return (typeof esc === "function") ? esc(s) : String(s == null ? "" : s);
}

async function kwhLoad() {
  KWH.loading = true; kwhRender();
  try {
    const j = await (await fetch("/keywords/history" + _kwhQs({
      week: KWH.week, prev: KWH.prev, q: KWH.q }))).json();
    if (j && j.ok) {
      KWH.weeks = j.weeks || []; KWH.rows = j.rows || [];
      KWH.movers = j.movers || []; KWH.counts = j.counts || null;
      KWH.week = j.week || ""; KWH.prev = j.prev || "";
      KWH.rankNote = j.rank_note || ""; KWH.gapNote = j.gap_note || "";
      KWH.note = "";
    } else { KWH.note = (j && j.error) || "Could not read the history."; }
  } catch (e) { KWH.note = "Could not read the history: " + e; }
  KWH.loading = false; kwhRender();
}

function kwhSetWeek(v) { KWH.week = v; kwhLoad(); }
function kwhSetPrev(v) { KWH.prev = v; kwhLoad(); }
function kwhSetTab(t) { KWH.tab = t; kwhRender(); }
function kwhSearch() {
  KWH.q = ((document.getElementById("kwh_q") || {}).value || "").trim();
  kwhLoad();
}

function _kwhMoved(r) {
  if (r.only_in) {
    return '<span class="cc" title="This keyword is only in one of the two '
         + 'weeks, which usually means nobody pulled the other week. Not '
         + 'counted as a movement.">only in ' + (r.only_in === "now" ? "this" : "the earlier")
         + " week</span>";
  }
  if (r.moved === null || r.moved === undefined) return '<span class="cc">—</span>';
  if (r.moved === 0) return '<span class="cc">no change</span>';
  const up = r.moved > 0;
  return '<span style="color:' + (up ? "var(--ok)" : "var(--warn)") + '">'
       + (up ? "▲ " : "▼ ") + Math.abs(r.moved).toLocaleString()
       + '</span> <span class="cc">' + (up ? "more searched" : "less searched")
       + "</span>";
}

function kwhRender() {
  const host = document.getElementById("kwhistorybody");
  if (!host) return;
  let h = "";

  if (KWH.loading) {
    host.innerHTML = '<div class="gendiag"><span class="genspin"></span> '
      + "Reading your stored keywords…</div>";
    return;
  }
  if (KWH.note) h += '<div class="gendiag">' + _kwhEsc(KWH.note) + "</div>";

  const c = KWH.counts || {};
  if (!KWH.weeks.length) {
    h += '<div class="empty">Nothing stored yet.'
       + '<div class="cc" style="margin-top:8px">This page is the record of '
       + 'what Keyword Spy and ASIN Insights have already pulled. Search on '
       + 'either of those and the week appears here. Nothing runs on a timer, '
       + "so history builds up as you use the tools.</div></div>";
    host.innerHTML = h; return;
  }

  h += '<div class="cc" style="margin:4px 0 12px">'
     + "<b>" + (c.keywords || 0).toLocaleString() + "</b> keywords across <b>"
     + (c.weeks || 0) + "</b> week" + (c.weeks === 1 ? "" : "s")
     + ", <b>" + (c.asin_queries || 0).toLocaleString() + "</b> ASIN queries, <b>"
     + (c.checks || 0).toLocaleString() + "</b> tracker checks.</div>";

  // The week pickers offer ONLY weeks that have data. Offering a calendar would
  // invite comparing against a week nobody pulled, which reads as a collapse.
  const opts = function (sel) {
    return KWH.weeks.map(function (w) {
      return '<option value="' + _kwhEsc(w.report_start) + '"'
        + (w.report_start === sel ? " selected" : "") + ">"
        + _kwhEsc(w.report_start) + " to " + _kwhEsc(w.report_end)
        + " (" + w.n + ")</option>";
    }).join("");
  };
  h += '<div class="wstoolbar" style="gap:8px;margin-bottom:12px">'
     + '<label class="cc">Week <select class="ed" onchange="kwhSetWeek(this.value)">'
     + opts(KWH.week) + "</select></label>"
     + '<label class="cc">compared with <select class="ed" onchange="kwhSetPrev(this.value)">'
     + '<option value="">— none —</option>' + opts(KWH.prev) + "</select></label>"
     + '<span style="flex:1"></span>'
     + '<input id="kwh_q" class="ed" placeholder="Filter keywords…" value="'
     + _kwhEsc(KWH.q) + '" oninput="clearTimeout(window._kwhT);'
     + 'window._kwhT=setTimeout(kwhSearch,400)">'
     + "</div>";

  h += '<div class="viewtoggle" style="margin-bottom:10px">'
     + '<button class="' + (KWH.tab === "movers" ? "on" : "") + '" onclick="kwhSetTab(\'movers\')">Movement</button>'
     + '<button class="' + (KWH.tab === "all" ? "on" : "") + '" onclick="kwhSetTab(\'all\')">All keywords this week</button>'
     + "</div>";

  if (KWH.tab === "movers") {
    if (!KWH.prev) {
      h += '<div class="empty">Pick a second week to compare against. '
         + "Only weeks that have data are offered.</div>";
    } else if (!KWH.movers.length) {
      h += '<div class="empty">Nothing to compare in those two weeks.</div>';
    } else {
      if (KWH.rankNote) h += '<div class="cc" style="margin-bottom:8px">' + _kwhEsc(KWH.rankNote) + "</div>";
      if (KWH.gapNote) h += '<div class="cc" style="margin-bottom:10px">' + _kwhEsc(KWH.gapNote) + "</div>";
      h += '<table class="tbl"><thead><tr><th>Keyword</th>'
         + '<th title="1 is the most searched term.">Rank now ↓</th>'
         + "<th>Rank before</th><th>Movement</th><th>Most clicked</th>"
         + "</tr></thead><tbody>";
      KWH.movers.slice(0, 400).forEach(function (r) {
        h += "<tr><td>" + _kwhEsc(r.keyword) + "</td><td>"
           + (r.rank_now ? r.rank_now.toLocaleString() : '<span class="cc">—</span>')
           + "</td><td>"
           + (r.rank_prev ? r.rank_prev.toLocaleString() : '<span class="cc">—</span>')
           + "</td><td>" + _kwhMoved(r) + "</td><td>"
           + (r.top_asin_1 ? '<span class="asin">' + _kwhEsc(r.top_asin_1) + "</span>"
                           : '<span class="cc">—</span>')
           + "</td></tr>";
      });
      h += "</tbody></table>";
    }
  } else {
    if (!KWH.rows.length) {
      h += '<div class="empty">No keywords stored for that week'
         + (KWH.q ? " matching “" + _kwhEsc(KWH.q) + "”" : "") + ".</div>";
    } else {
      h += '<table class="tbl"><thead><tr>'
         + '<th title="1 is the most searched term.">Rank ↓</th><th>Keyword</th>'
         + "<th>Most clicked</th><th>Found by searching</th>"
         + "</tr></thead><tbody>";
      KWH.rows.forEach(function (r) {
        h += "<tr><td><b>"
           + (r.search_frequency_rank ? r.search_frequency_rank.toLocaleString()
                                      : '<span class="cc">—</span>')
           + "</b></td><td>" + _kwhEsc(r.keyword) + "</td><td>"
           + (r.top_asin_1 ? '<span class="asin">' + _kwhEsc(r.top_asin_1) + "</span>"
                           : '<span class="cc">—</span>')
           + '</td><td><span class="cc">' + _kwhEsc(r.seed || "—") + "</span></td></tr>";
      });
      h += "</tbody></table>";
    }
  }
  host.innerHTML = h;
}

function kwhOnOpen() { kwhLoad(); }
