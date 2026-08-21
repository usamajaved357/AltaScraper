// static/js/keywordspy.js — Keyword Spy.
//
// One seed word in, the marketplace's top search terms containing it out, and
// every search quietly written to the keyword store so history builds up through
// ordinary use rather than through a scheduler.
//
// THE ONE THING THIS SCREEN MUST NOT IMPLY. It is not a search sent to Amazon.
// The report is the WHOLE marketplace's top search terms for a week; the seed
// filters what came back. Somebody expecting "type anything, get results" will
// read an empty list as a broken feature instead of as "that word is not in this
// marketplace's top terms" — so the screen says which it is, with the size of
// the report it filtered.
//
// AND RANK COUNTS DOWN. 1 is the most searched term in the marketplace. Every
// number on this screen is that way round, and the header says so, because a
// column of large numbers that means "unpopular" is read backwards by everyone
// exactly once.

let KWSPY = { rows: [], note: "", loading: false, seed: "", meta: null };

function _kwsQs(extra) {
  return (typeof scopeQs === "function") ? scopeQs(extra) : "";
}
function _kwsEsc(s) {
  return (typeof esc === "function") ? esc(s) : String(s == null ? "" : s);
}

async function kwSpySearch() {
  const el = document.getElementById("kws_q");
  const seed = (el && el.value || "").trim();
  KWSPY.seed = seed;
  KWSPY.loading = true; KWSPY.note = ""; kwSpyRender();
  try {
    const start = (document.getElementById("kws_start") || {}).value || "";
    const end = (document.getElementById("kws_end") || {}).value || "";
    const j = await (await fetch("/keywords/spy" + _kwsQs({
      q: seed, start: start, end: end }))).json();
    if (j && j.ok) {
      KWSPY.rows = j.rows || [];
      KWSPY.meta = j;
      if (!KWSPY.rows.length) {
        KWSPY.note = seed
          ? ('No term containing “' + seed + '” is in this week\'s top search '
             + 'terms. Amazon returned ' + (j.total_in_report || 0).toLocaleString()
             + ' terms for the marketplace; none of them match.')
          : "Amazon returned no search terms for this week.";
      }
    } else {
      // A permission refusal and an empty week look identical on a screen and
      // only one is worth acting on, so the server tells them apart and this
      // repeats which it was.
      KWSPY.rows = [];
      KWSPY.note = (j && j.error) || "Could not read the search terms.";
      KWSPY.meta = j || null;
    }
  } catch (e) {
    KWSPY.rows = []; KWSPY.note = "Could not read the search terms: " + e;
  }
  KWSPY.loading = false; kwSpyRender();
}

function kwSpyRender() {
  const host = document.getElementById("kwspybody");
  if (!host) return;
  const m = KWSPY.meta || {};
  let h = "";

  if (KWSPY.loading) {
    h = '<div class="gendiag"><span class="genspin"></span> Asking Amazon for '
      + 'this week\'s search terms… Brand Analytics reports are built on '
      + 'request and rationed to roughly one a minute, so the first pull of a '
      + 'week is slow and the rest are instant.</div>';
    host.innerHTML = h; return;
  }

  if (KWSPY.note) {
    h += '<div class="gendiag ' + (m.brand_registry ? "bad" : "") + '">'
       + _kwsEsc(KWSPY.note) + "</div>";
  }

  if (KWSPY.rows.length) {
    h += '<div class="cc" style="margin:10px 0">'
       + '<b>' + KWSPY.rows.length.toLocaleString() + '</b> terms containing “'
       + _kwsEsc(KWSPY.seed || "anything") + '”, out of '
       + (m.total_in_report || 0).toLocaleString() + ' in the report for '
       + _kwsEsc(m.start) + ' to ' + _kwsEsc(m.end) + '. '
       + (m.saved ? ('<span style="color:var(--ok)">' + m.saved
                     + ' saved to your keyword history.</span>') : "")
       + "</div>";
    h += '<table class="tbl"><thead><tr>'
       + '<th title="Amazon\'s search frequency rank. 1 is the MOST searched '
       + 'term in the marketplace, so smaller is bigger.">Rank ↓</th>'
       + "<th>Search term</th>"
       + '<th title="The ASINs shoppers clicked most after this search. Not '
       + 'necessarily yours — this is the whole marketplace.">Most clicked</th>'
       + "<th></th></tr></thead><tbody>";
    KWSPY.rows.forEach(function (r) {
      const asins = [r.asin1, r.asin2, r.asin3].filter(Boolean);
      h += "<tr><td><b>" + (r.rank ? r.rank.toLocaleString() : '<span class="cc">—</span>')
         + "</b></td><td>" + _kwsEsc(r.term) + "</td><td>"
         + (asins.length
            ? asins.map(function (a) {
                return '<a class="asin" href="' + _kwsEsc(
                  (typeof _dpUrl === "function") ? _dpUrl(a) : "#")
                  + '" target="_blank" rel="noopener">' + _kwsEsc(a) + "</a>";
              }).join(" ")
            : '<span class="cc">—</span>')
         + '</td><td><button class="ghost" onclick="kwSpyWatch(' + "'"
         + _kwsEsc(String(r.term).replace(/'/g, "\\'")) + "'" + ')" '
         + 'title="Add this keyword to the rank tracker">Track</button></td></tr>';
    });
    h += "</tbody></table>";
  } else if (!KWSPY.note) {
    h += '<div class="empty">Type a word and press Search. '
       + 'Every search is saved, so your keyword history builds up as you use '
       + 'this — nothing runs on a timer.</div>';
  }
  host.innerHTML = h;
}

// Sends the keyword over to the tracker screen with the word already filled in.
// The ASIN is deliberately NOT guessed: the most-clicked ASIN for a marketplace
// term is usually a competitor's, and tracking a competitor's ASIN would return
// nothing (Amazon does not share another seller's query performance).
function kwSpyWatch(term) {
  try {
    if (typeof navTo === "function") navTo("ranktracker");
    const el = document.getElementById("krt_kw");
    if (el) { el.value = term; el.focus(); }
    if (typeof toast === "function") {
      toast("Add one of YOUR ASINs to track this keyword against.");
    }
  } catch (e) {}
}

function kwSpyOnOpen() {
  // Default the dates to the last complete week, matching the server.
  const t = new Date();
  const end = new Date(t); end.setDate(t.getDate() - (t.getDay() === 0 ? 1 : t.getDay() + 1));
  const start = new Date(end); start.setDate(end.getDate() - 6);
  const iso = function (d) { return d.toISOString().slice(0, 10); };
  const s = document.getElementById("kws_start"), e = document.getElementById("kws_end");
  if (s && !s.value) s.value = iso(start);
  if (e && !e.value) e.value = iso(end);
  kwSpyRender();
}
