// static/js/keywordasin.js — ASIN Insights.
//
// One of your ASINs in, the search queries that produced its impressions,
// clicks and purchases out. Saved on every search, like the Spy screen, so the
// history builds through use.
//
// THE THING THE PLAN CALLS "REVERSE ASIN" AND THIS IS NOT.
// Search Query Performance is reported for ASINs the CONNECTED SELLER owns.
// Amazon does not hand over another seller's query performance to anybody, at
// any price. Typed a competitor's ASIN, this returns nothing — a true answer
// that reads exactly like a broken feature, so the screen says so before you
// try it rather than after.
//
// AND TWO WORDS THIS SCREEN WILL NOT MISUSE.
// Amazon's "click share" is one ASIN's slice of ALL clicks for a query, across
// every seller — the number that turns "we sold four" into "we sold four of two
// hundred". This report does not contain it. What can be computed is
// clicks ÷ impressions and purchases ÷ clicks for THIS listing, which are its
// click-through and conversion rates. Those are shown, under those names. A
// 40% CTR is not 40% of the market and must never be able to be read as it.

let KWASIN = { rows: [], note: "", loading: false, asin: "", meta: null };

function _kwaQs(extra) {
  return (typeof scopeQs === "function") ? scopeQs(extra) : "";
}
function _kwaEsc(s) {
  return (typeof esc === "function") ? esc(s) : String(s == null ? "" : s);
}
function _kwaPct(v) {
  return (v === null || v === undefined) ? '<span class="cc">—</span>'
                                         : v.toFixed(1) + "%";
}

async function kwAsinSearch() {
  const el = document.getElementById("kwa_asin");
  const asin = (el && el.value || "").trim().toUpperCase();
  if (!asin) {
    KWASIN.note = "Enter one of your own ASINs."; kwAsinRender(); return;
  }
  KWASIN.asin = asin; KWASIN.loading = true; KWASIN.note = ""; kwAsinRender();
  try {
    const start = (document.getElementById("kwa_start") || {}).value || "";
    const end = (document.getElementById("kwa_end") || {}).value || "";
    const j = await (await fetch("/keywords/asin-insights" + _kwaQs({
      asin: asin, start: start, end: end }))).json();
    if (j && j.ok) {
      KWASIN.rows = j.rows || []; KWASIN.meta = j;
      if (!KWASIN.rows.length) {
        KWASIN.note = "No search queries came back for " + asin + " in that week. "
          + "That happens when the ASIN is not one this selling account owns, "
          + "when it had no searches, or when it is too new to have a week of "
          + "history yet.";
      }
    } else {
      KWASIN.rows = [];
      KWASIN.note = (j && j.error) || "Could not read Search Query Performance.";
      KWASIN.meta = j || null;
    }
  } catch (e) {
    KWASIN.rows = []; KWASIN.note = "Could not read the report: " + e;
  }
  KWASIN.loading = false; kwAsinRender();
}

function kwAsinRender() {
  const host = document.getElementById("kwasinbody");
  if (!host) return;
  const m = KWASIN.meta || {};
  let h = "";

  if (KWASIN.loading) {
    h = '<div class="gendiag"><span class="genspin"></span> Asking Amazon for '
      + 'Search Query Performance for ' + _kwaEsc(KWASIN.asin) + "…</div>";
    host.innerHTML = h; return;
  }

  if (KWASIN.note) {
    h += '<div class="gendiag ' + (m.brand_registry ? "bad" : "") + '">'
       + _kwaEsc(KWASIN.note) + "</div>";
  }

  if (KWASIN.rows.length) {
    h += '<div class="cc" style="margin:10px 0"><b>'
       + KWASIN.rows.length.toLocaleString() + "</b> queries for "
       + _kwaEsc(KWASIN.asin) + ", " + _kwaEsc(m.start) + " to " + _kwaEsc(m.end)
       + ". " + (m.saved ? ('<span style="color:var(--ok)">' + m.saved
                            + " saved to your keyword history.</span>") : "")
       + "</div>";
    if (m.rates_note) {
      h += '<div class="cc" style="margin:0 0 10px">' + _kwaEsc(m.rates_note) + "</div>";
    }
    h += '<table class="tbl"><thead><tr><th>Search query</th>'
       + '<th title="How many times your listing was shown for this query.">Impressions</th>'
       + "<th>Clicks</th>"
       + '<th title="Clicks ÷ impressions, for THIS listing. Not Amazon\'s click share.">CTR</th>'
       + "<th>Cart adds</th><th>Purchases</th>"
       + '<th title="Purchases ÷ clicks, for THIS listing.">CVR</th>'
       + "<th></th></tr></thead><tbody>";
    KWASIN.rows.forEach(function (r) {
      h += "<tr><td>" + _kwaEsc(r.query) + "</td>"
         + "<td>" + (r.impressions || 0).toLocaleString() + "</td>"
         + "<td>" + (r.clicks || 0).toLocaleString() + "</td>"
         + "<td>" + _kwaPct(r.ctr) + "</td>"
         + "<td>" + (r.cart_adds || 0).toLocaleString() + "</td>"
         + "<td><b>" + (r.purchases || 0).toLocaleString() + "</b></td>"
         + "<td>" + _kwaPct(r.cvr) + "</td>"
         + '<td><button class="ghost" onclick="kwAsinWatch(' + "'"
         + _kwaEsc(String(r.query).replace(/'/g, "\\'")) + "'" + ')" '
         + 'title="Track this query for this ASIN">Track</button></td></tr>';
    });
    h += "</tbody></table>";
  } else if (!KWASIN.note) {
    h += '<div class="empty">Enter one of your own ASINs and press Search.'
       + '<div class="cc" style="margin-top:8px">Search Query Performance only '
       + 'covers ASINs this selling account owns — a competitor\'s ASIN returns '
       + 'nothing, because Amazon does not share another seller\'s query '
       + 'performance.</div></div>';
  }
  host.innerHTML = h;
}

// Both halves are known here, unlike on the Spy screen: the query AND one of
// our own ASINs, which is the only pair the tracker can actually measure.
async function kwAsinWatch(query) {
  try {
    const j = await (await fetch("/keywords/rank-tracker/add", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign(
        (typeof acctBody === "function") ? acctBody({}) : {},
        { keyword: query, asin: KWASIN.asin,
          marketplace: (typeof WS_MARKET !== "undefined" ? WS_MARKET : "") }))
    })).json();
    if (typeof toast === "function") {
      toast(j && j.ok ? ("Tracking “" + query + "” for " + KWASIN.asin)
                      : ("Could not track it: " + ((j && j.error) || "")));
    }
  } catch (e) {
    if (typeof toast === "function") toast("Could not track it: " + e);
  }
}

function kwAsinOnOpen() {
  const t = new Date();
  const end = new Date(t); end.setDate(t.getDate() - (t.getDay() === 0 ? 1 : t.getDay() + 1));
  const start = new Date(end); start.setDate(end.getDate() - 6);
  const iso = function (d) { return d.toISOString().slice(0, 10); };
  const s = document.getElementById("kwa_start"), e = document.getElementById("kwa_end");
  if (s && !s.value) s.value = iso(start);
  if (e && !e.value) e.value = iso(end);
  kwAsinRender();
}
