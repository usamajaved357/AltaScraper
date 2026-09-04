// static/js/catalogpage.js — the Product Catalog (Orbit's ASINs page).
//
// A table of every product, and above it four sentences that each change a
// decision:
//
//   how concentrated the revenue is   — how exposed the business is
//   what the best product is worth    — what one suspension would cost
//   what is listed and earning nothing— the only card that names work to do
//   how big the tail is               — worth knowing before spending a week on it
//
// A catalogue of eighty products is a list nobody reads. The four cards are the
// reason to open the page at all, so they go first and they are sentences, not
// numbers needing interpretation.

let CATP = { data: null, note: "", loading: false, period: "all", q: "", sort: "revenue" };

function _catpQs(extra) {
  return (typeof scopeQs === "function") ? scopeQs(extra) : "";
}

function catpMoney(v, cur) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  return (cur || "") + n.toLocaleString(undefined, { minimumFractionDigits: 2,
                                                     maximumFractionDigits: 2 });
}

function catpNum(v) {
  if (v === null || v === undefined) return "—";
  return Math.round(Number(v)).toLocaleString();
}

function catpPct(v) {
  if (v === null || v === undefined) return '<span class="cc">—</span>';
  return (Number(v) * 100).toFixed(1) + "%";
}

function catpCur() {
  return (typeof curSymbol === "function") ? curSymbol("") : "";
}

function catpRender() {
  const box = document.getElementById("catp_body");
  if (!box) return;
  if (CATP.loading) { box.innerHTML = '<div class="cc" style="padding:14px">Loading…</div>'; return; }
  if (CATP.note) { box.innerHTML = '<div class="sresfail">' + esc(CATP.note) + "</div>"; return; }
  const d = CATP.data;
  if (!d) { box.innerHTML = ""; return; }
  const cur = catpCur();

  let html = "";
  if (d.note) {
    html += '<div class="issuesbox" style="background:var(--warn-bg);border:1px solid var(--warn-line);' +
            'color:var(--gold);margin-bottom:12px">' + esc(d.note) + "</div>";
  }

  // ---- the four findings --------------------------------------------------
  const f = d.findings || {};
  // THE BAR UNDER EACH CARD IS THE SAME QUANTITY THE NUMBER STATES, drawn
  // against its whole -- never a second, different fact smuggled in under the
  // first. "8" above a bar a fifth of the way across says eight out of forty
  // without needing the sentence, and the sentence is still there underneath.
  const cards = [];
  if (f.concentration) {
    cards.push({ k: "Revenue concentration", v: f.concentration.n,
                 s: f.concentration.label, cls: "",
                 // the count IS a share of the catalogue, and that is the share
                 share: f.concentration.pct_of_catalogue, bar: "var(--accent)" });
  }
  if (f.top) {
    cards.push({ k: "Top performer", v: (f.top.share * 100).toFixed(0) + "%",
                 s: f.top.label + (f.top.title ? " — " + f.top.title.slice(0, 46) : ""),
                 cls: "", share: f.top.share, bar: "var(--ok)" });
  }
  if (f.dead) {
    // The only one that names work to do, so it is the one that carries a
    // colour. The others are facts; this is a job.
    const _prods = Number(d.products) || 0;
    cards.push({ k: "Listed, earning nothing", v: f.dead.n, s: f.dead.label,
                 cls: "warn", bar: "var(--gold)",
                 share: _prods > 0 ? (f.dead.n / _prods) : null });
  }
  if (f.losers) {
    cards.push({ k: "The tail", v: catpPct(f.losers.share).replace(/<[^>]*>/g, ""),
                 s: f.losers.label, cls: "",
                 share: f.losers.share, bar: "var(--ink4)" });
  }
  // Built by the shared uiStat() rather than by hand here (CLAUDE.md Rule 12).
  // This wrote out .ui-stat markup itself -- the same three divs pageui.js
  // already emits -- which is how the Catalog's cards ended up label-first
  // while the Repricer's were number-first, on two screens that both open with
  // four numbers above a table of products. One builder, one look, and
  // anything that changes about the card now changes on every screen at once.
  if (cards.length) {
    html += uiStats(cards.map(function (c) {
      return { label: c.k, value: esc(String(c.v)), note: c.s,
               tone: c.cls, share: c.share, barColor: c.bar };
    }));
  }

  // ---- counters -----------------------------------------------------------
  const c = d.counts || {};
  html += '<div class="catp-counts">' +
    '<span><b>' + catpNum(d.products) + "</b> products</span>" +
    '<span><b>' + catpNum(c.parents) + "</b> parents</span>" +
    '<span><b>' + catpNum(c.variations) + "</b> variations</span>" +
    '<span><b>' + catpMoney(d.total_revenue, cur) + "</b> revenue</span>" +
    '<span><b>' + catpNum(d.total_units) + "</b> units</span>" +
    '<span class="cc">' + esc(d.period === "all" ? "all time"
      : (d.start + " → " + d.end)) + "</span>" +
    "</div>";

  // ---- controls -----------------------------------------------------------
  html += '<div class="catp-bar">';
  [["all", "All time"], ["month", "Last month"], ["quarter", "Last 3 months"],
   ["year", "Last year"]].forEach(function (p) {
    html += '<button class="db-chip' + (CATP.period === p[0] ? " on" : "") +
            '" onclick="catpPeriod(\'' + p[0] + '\')">' + p[1] + "</button>";
  });
  html += '<input class="ed" id="catp_q" placeholder="Search ASIN, title or SKU…" ' +
          'style="flex:1;min-width:180px" value="' + esc(CATP.q) +
          '" oninput="catpSearch(this.value)">';
  html += "</div>";

  // ---- the table ----------------------------------------------------------
  let rows = d.rows || [];
  if (CATP.q) {
    const q = CATP.q.toLowerCase();
    rows = rows.filter(function (r) {
      return (r.asin || "").toLowerCase().indexOf(q) >= 0 ||
             (r.title || "").toLowerCase().indexOf(q) >= 0 ||
             (r.sku || "").toLowerCase().indexOf(q) >= 0;
    });
  }
  if (!rows.length) {
    html += '<div class="card" style="padding:18px"><div class="cc">No products match.</div></div>';
    box.innerHTML = html;
    return;
  }
  html += uiPanel('Every product, best first', 'Ranked by what it earns. A product with no cost entered shows no margin rather than a flattering one.',
    '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
    "<th>#</th><th>Product</th><th>Parent</th><th>Units</th><th>Revenue</th>" +
    "<th>Share</th><th>Unit cost</th><th>Margin</th><th>Days with sales</th>" +
    "</tr></thead><tbody>");
  rows.forEach(function (r) {
    const dead = (r.revenue <= 0 && r.units <= 0);
    html += '<tr' + (dead ? ' class="catp-dead"' : "") + ">" +
      '<td class="cc">' + r.rank + "</td>" +
      '<td><div class="stk-prod">' +
      (r.img ? '<img src="' + esc(r.img) + '" class="catp-img" loading="lazy" alt="">'
             : '<span class="catp-img catp-noimg"><i class="ti ti-photo-off"></i></span>') +
      '<div class="stk-pname"><div style="font-weight:600">' + esc(r.asin) + "</div>" +
      '<div class="cc" style="font-size:11px;max-width:320px;overflow:hidden;' +
      'text-overflow:ellipsis;white-space:nowrap">' + esc(r.title || "") + "</div>" +
      (r.sku ? '<div class="cc" style="font-size:10px">' + esc(r.sku) + "</div>" : "") +
      "</div></div></td>" +
      '<td class="cc" style="font-size:11px">' + esc(r.parent_asin || "—") + "</td>" +
      "<td>" + catpNum(r.units) + "</td>" +
      "<td>" + catpMoney(r.revenue, cur) + "</td>" +
      "<td>" + catpPct(r.share) + "</td>" +
      // A blank cost is blank, not zero: nobody has entered one.
      "<td>" + (r.cogs === null || r.cogs === undefined
                ? '<span class="cc">not set</span>' : catpMoney(r.cogs, cur)) + "</td>" +
      // And with no cost there is NO margin — a margin against a missing cost
      // would read as "this product makes 100%".
      "<td>" + (r.margin === null || r.margin === undefined
                ? '<span class="cc">—</span>'
                : '<span class="' + (r.margin < 0 ? "trkbad" : "trkgood") + '">' +
                  (r.margin * 100).toFixed(0) + "%</span>") + "</td>" +
      '<td class="cc">' + (r.days || 0) + "</td>" +
      "</tr>";
  });
  html += "</tbody></table></div></div>";
  box.innerHTML = html;
}

function catpSearch(v) {
  CATP.q = v || "";
  catpRender();
}

function catpPeriod(p) {
  CATP.period = p;
  catpLoad();
}

async function catpLoad() {
  CATP.loading = true; CATP.note = ""; catpRender();
  try {
    const j = await (await fetch("/catalog/products" +
      _catpQs({ period: CATP.period }))).json();
    if (j && j.ok) CATP.data = j;
    else CATP.note = (j && j.error) || "Could not read the catalogue.";
  } catch (e) {
    CATP.note = "Could not read the catalogue: " + e;
  }
  CATP.loading = false;
  catpRender();
}
