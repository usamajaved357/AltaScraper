// static/js/categories.js — Category Explorer.
//
//   Orbit: "Where <brand>'s products sit in Amazon's category tree."
//
// The category comes from an ASIN's sales ranks, which is one Catalog call per
// product. Fifty products is fifty calls, so this is a BUTTON — Orbit has a
// "Populate from Amazon" button for the same reason. Opening the page draws
// what is stored and calls nothing.
//
// UNCATEGORIZED IS A REAL ANSWER AND IS SPLIT IN TWO. Amazon does not rank every
// listing: a product with no sales history often has no rank and therefore no
// category. That is different from a product nobody has looked up yet, and a
// screen showing both as "uncategorized" tells you to go and populate something
// that has already been populated.

let CATS = { data: null, loading: false, note: "" };

function _catsQs() { return (typeof scopeQs === "function") ? scopeQs() : ""; }

function catsRender() {
  const box = document.getElementById("cats_body");
  if (!box) return;
  if (CATS.loading) {
    box.innerHTML = '<div class="cc" style="padding:14px">Reading categories from ' +
      "Amazon — one call per product…</div>";
    return;
  }
  if (CATS.note) { box.innerHTML = '<div class="sresfail">' + esc(CATS.note) + "</div>"; return; }
  const d = CATS.data;
  if (!d) { box.innerHTML = ""; return; }
  const c = d.counts || {};

  let html = uiToolbar(
    '<button class="primary" onclick="catsPopulate()"' + (CATS.loading ? " disabled" : "") + '>' +
    '<i class="ti ti-download"></i> Populate from Amazon</button>',
    '<div class="cc" style="font-size:11.5px;max-width:560px;text-align:right">One call per ' +
    "product, so it is capped per press and picks up where it left off. " +
    (d.fetched_at ? "Last read " + esc(d.fetched_at) + "." : "Never read yet.") + "</div>");

  if (d.note) {
    html += '<div class="issuesbox" style="background:#241f10;border:1px solid #3a3320;' +
            'color:#e6d9b8;margin-bottom:12px">' + esc(d.note) + "</div>";
  }

  html += '<div class="ui-stats">' +
    '<div class="ui-stat"><div class="ui-stat-k">Categories</div>' +
    '<div class="ui-stat-v">' + (c.categories || 0) + "</div>" +
    '<div class="ui-note">you have products ranked in</div></div>' +
    '<div class="ui-stat"><div class="ui-stat-k">Placed</div>' +
    '<div class="ui-stat-v">' + (c.mapped || 0) + "</div>" +
    '<div class="ui-note">of ' + (c.products || 0) + " products in the catalogue</div></div>" +
    '<div class="ui-stat' + (c.uncategorized ? " warn" : "") + '">' +
    '<div class="ui-stat-k">No category</div>' +
    '<div class="ui-stat-v">' + (c.uncategorized || 0) + "</div>" +
    // The distinction that stops a pointless second press.
    '<div class="ui-note">' + (c.never_checked || 0) + " never read; " +
    ((c.uncategorized || 0) - (c.never_checked || 0)) +
    " read and Amazon gave no rank</div></div>" +
    "</div>";

  if (!(d.categories || []).length && !(d.uncategorized || []).length) {
    html += uiEmpty("Nothing read yet",
      "A product's category comes from its sales ranks, which is one call to Amazon per " +
      "product — so this page draws what is stored and fetches nothing on its own. " +
      "Press Populate to read them.");
    box.innerHTML = html;
    return;
  }

  if ((d.categories || []).length) {
    let t = '<div style="overflow-x:auto">' +
      '<table class="stk-table"><thead><tr><th>Category</th><th>Products</th>' +
      "<th>Best rank</th><th>What is in it</th></tr></thead><tbody>";
    d.categories.forEach(function (cat) {
      const names = cat.products.slice(0, 4).map(function (p) {
        return (p.title || p.asin).slice(0, 34);
      }).join(", ");
      t += "<tr>" +
        '<td style="font-weight:600">' + esc(cat.category) + "</td>" +
        "<td>" + cat.products.length + "</td>" +
        "<td>" + (cat.best_rank === null || cat.best_rank === undefined
          ? '<span class="cc">—</span>'
          : "#" + Math.round(cat.best_rank).toLocaleString()) + "</td>" +
        '<td class="cc" style="font-size:11.5px;max-width:420px">' + esc(names) +
        (cat.products.length > 4 ? " …and " + (cat.products.length - 4) + " more" : "") +
        "</td></tr>";
    });
    t += "</tbody></table></div>";
    html += uiPanel("Where your products sit",
      "Best rank is the strongest position any one of your products holds in that " +
      "category — not an average, which would hide it.", t);
  }

  if ((d.uncategorized || []).length) {
    let u = '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
      "<th>ASIN</th><th>Product</th><th>Read yet?</th></tr></thead><tbody>";
    d.uncategorized.slice(0, 200).forEach(function (p) {
      u += "<tr>" +
        '<td style="font-weight:600">' + esc(p.asin) + "</td>" +
        '<td class="cc" style="font-size:11.5px;max-width:420px;overflow:hidden;' +
        'text-overflow:ellipsis;white-space:nowrap">' + esc(p.title || "") + "</td>" +
        "<td>" + (p.checked
          ? '<span class="ld-pill unk">read — no rank</span>'
          : '<span class="ld-pill warn">not read yet</span>') + "</td></tr>";
    });
    u += "</tbody></table></div>";
    html += uiPanel("Not in any category (" + d.uncategorized.length + ")",
      "Amazon ranks a listing once it has sales history. A product here either has not " +
      "been read yet, or was read and Amazon had no rank for it — which usually means " +
      "it has not sold.", u);
  }

  box.innerHTML = html;
}

async function catsLoad() {
  try {
    const j = await (await fetch("/categories" + _catsQs())).json();
    if (j && j.ok) { CATS.data = j; CATS.note = ""; }
    else CATS.note = (j && j.error) || "Could not read the categories.";
  } catch (e) {
    CATS.note = "Could not read the categories: " + e;
  }
  catsRender();
}

async function catsPopulate() {
  CATS.loading = true; CATS.note = ""; catsRender();
  try {
    const j = await (await fetch("/categories/populate" + _catsQs(), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    })).json();
    if (j && j.ok) {
      CATS.data = j;
      toast(j.read + " of " + j.asked + " read" +
            (j.remaining ? " — " + j.remaining + " still to go" : ""));
    } else {
      CATS.note = (j && j.error) || "Could not read from Amazon.";
    }
  } catch (e) {
    CATS.note = "Could not read from Amazon: " + e;
  }
  CATS.loading = false;
  catsRender();
}
