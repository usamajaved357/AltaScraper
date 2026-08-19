// static/js/productpicker.js — pick a product, on whatever page needs one.
//
//     "i wanted the image studio as a separate page and wanted to work it as a
//      separate page, i should not have to go to another screen to generate
//      image to complete the image gen pipeline"
//
// Two pages need the same thing: a searchable list of this account's products,
// pick one, get on with the work. The Image Library grew one first; the Image
// Studio needed the identical thing, and its empty state said in so many words
// "Open Listings and press the photo button" — which IS the round trip being
// complained about.
//
// So the picker is one component (CLAUDE.md Rule 12). A second copy would have
// drifted the first time either page changed how a product is chosen, and the
// symptom would be two pickers disagreeing about what this account sells.
//
// It holds NO page state. The caller passes a container and a callback and owns
// everything that happens after the pick.

const PPICK = { items: [], loaded: false, loading: false, error: "" };

function _ppQs() { return (typeof scopeQs === "function") ? scopeQs() : ""; }

// The account's products, fetched ONCE and shared between pages. Two screens
// asking for the same list on every visit is two waits for the same answer.
async function ppLoad(force) {
  if (PPICK.loading) return;
  if (PPICK.loaded && !force) return;
  PPICK.loading = true; PPICK.error = "";
  try {
    const j = await (await fetch("/catalog/products" + _ppQs())).json();
    if (j && j.ok) {
      PPICK.items = (j.rows || []).map(function (r) {
        return { sku: r.sku || r.asin, asin: r.asin || "", title: r.title || "",
                 img: r.img || "", live: true };
      }).filter(function (r) { return r.sku; });
      PPICK.loaded = true;
    } else {
      PPICK.error = (j && j.error) || "Could not read the product list.";
    }
  } catch (e) {
    PPICK.error = "Could not read the product list: " + e;
  }
  PPICK.loading = false;
}

// The account changed, so the list is somebody else's. Called from navTo's
// account switch rather than left to go stale — showing one account's products
// on another's screen is the exact fault the rest of this app has been
// hardening against.
function ppInvalidate() {
  PPICK.items = []; PPICK.loaded = false; PPICK.error = "";
}

/* Draw the picker into `hostId`.
 *
 *   opts.selected   the sku currently chosen, so it can be marked
 *   opts.onPick     called with the product object
 *   opts.q          the current search text (the caller owns it, because the
 *                   caller owns its own re-render)
 *   opts.onSearch   called with the new search text
 *   opts.limit      how many rows to draw before asking them to search
 */
function ppRender(hostId, opts) {
  const box = document.getElementById(hostId);
  if (!box) return;
  const o = opts || {};
  const q = String(o.q || "").toLowerCase();
  const limit = o.limit || 60;

  let items = PPICK.items;
  if (q) {
    items = items.filter(function (r) {
      return (r.sku || "").toLowerCase().indexOf(q) >= 0 ||
             (r.asin || "").toLowerCase().indexOf(q) >= 0 ||
             (r.title || "").toLowerCase().indexOf(q) >= 0;
    });
  }

  let html =
    '<div class="imgp-bar">' +
    '<input class="ed" id="' + hostId + '_q" placeholder="Find a product — SKU, ASIN or title…" ' +
    'style="flex:1;min-width:180px" value="' + esc(o.q || "") + '" ' +
    'oninput="(' + (o.onSearchName || "function(){}") + ')(this.value)">' +
    '<span class="cc" style="font-size:11.5px">' + items.length + " of " +
    PPICK.items.length + "</span>" +
    "</div>";

  if (PPICK.error) {
    html += '<div class="sresfail">' + esc(PPICK.error) + "</div>";
  } else if (PPICK.loading && !PPICK.items.length) {
    html += '<div class="cc" style="padding:12px;font-size:12.5px">Loading products…</div>';
  } else if (!PPICK.items.length) {
    // An empty picker has to say what to DO. This is the state a brand-new
    // account is in, and "no products" alone reads as a broken screen.
    html += '<div class="cc" style="padding:12px;font-size:12.5px;line-height:1.55">' +
      "No products yet for this account. Import from the input sheet and " +
      "generate some listings first, or use <b>Research ASIN</b> to work from " +
      "any ASIN without one." + "</div>";
  } else if (!items.length) {
    html += '<div class="cc" style="padding:12px;font-size:12.5px">Nothing matches.</div>';
  } else {
    html += '<div class="imgp-list">';
    items.slice(0, limit).forEach(function (r) {
      const on = (String(r.sku) === String(o.selected || "")) ? " on" : "";
      html += '<div class="imgp-row' + on + '" onclick="ppPick(' + jsArg(String(r.sku)) +
        ',' + jsArg(String(o.pickName || "")) + ')">' +
        (r.img ? '<img src="' + esc(r.img) + '" loading="lazy" alt="">'
               : '<span class="imgp-noimg"><i class="ti ti-photo-off"></i></span>') +
        '<div class="imgp-meta">' +
        '<div class="imgp-t">' + esc((r.title || r.sku).slice(0, 58)) + "</div>" +
        '<div class="cc" style="font-size:10.5px">' + esc(r.sku) +
        (r.asin ? " · " + esc(r.asin) : "") + "</div></div></div>";
    });
    html += "</div>";
    if (items.length > limit) {
      html += '<div class="cc" style="font-size:11px;padding:6px 2px">Showing ' +
        limit + " of " + items.length + " — narrow it with the search box.</div>";
    }
  }
  box.innerHTML = html;
}

// The click goes through here so a row's markup carries a short call rather
// than a serialised product, and so the two pages cannot disagree about what
// "picked" means.
function ppPick(sku, handlerName) {
  const it = PPICK.items.find(function (r) { return String(r.sku) === String(sku); });
  if (!it) return;
  const fn = handlerName ? window[handlerName] : null;
  if (typeof fn === "function") fn(it);
}

function ppItem(sku) {
  return PPICK.items.find(function (r) { return String(r.sku) === String(sku); }) || null;
}
