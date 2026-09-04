// static/js/asinstudio.js — ASIN Studio.
//
// Put in any ASIN, optionally a few of its competitors, and the brand the
// finished listing goes out under. Out comes a DRAFT in this account: copy,
// attributes, and the Image Studio seeded with the real product photo for the
// main image, secondaries and A+.
//
// THE ASIN IS A REFERENCE, NOT A LISTING TO JOIN. CLAUDE.md Rule 1: this app
// creates NEW products under the seller's own brands. Nothing here claims the
// source ASIN, and the screen says so where somebody might assume otherwise --
// because "put in an ASIN and generate" is exactly the shape of a me-too tool,
// and it is not one.
//
// THREE STEPS, VISIBLE AS THREE STEPS. Research (free, read-only), Generate
// (spends tokens), Create draft (writes a row). Each one says what it will do
// before it does it, because the second costs money and the third puts
// something in your listings.

let ASTUDIO = { source: null, competitors: [], copy: null, attributes: null,
                brand: "", ipNotes: [], findings: [], brandNote: "",
                busy: "", note: "", sku: "" };

function _asQs(extra) {
  return (typeof scopeQs === "function") ? scopeQs(extra) : "";
}
function _asEsc(s) {
  return (typeof esc === "function") ? esc(s) : String(s == null ? "" : s);
}
function _asBody(o) {
  return (typeof acctBody === "function") ? acctBody(o || {}) : (o || {});
}

// ------------------------------------------------------------------ step 1
async function asStudioResearch() {
  const asin = ((document.getElementById("as_asin") || {}).value || "")
                 .trim().toUpperCase();
  if (!asin) { ASTUDIO.note = "Enter the ASIN you want content for."; asStudioRender(); return; }
  const comps = ((document.getElementById("as_comps") || {}).value || "")
    .split(/[\s,]+/).map(s => s.trim().toUpperCase()).filter(Boolean);

  ASTUDIO.busy = "research"; ASTUDIO.note = ""; asStudioRender();
  try {
    const j = await (await fetch("/asin-studio/research", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_asBody({ asin: asin, competitors: comps,
        marketplace: (typeof WS_MARKET !== "undefined" ? WS_MARKET : "") }))
    })).json();
    if (j && j.ok) {
      ASTUDIO.source = j.source || null;
      ASTUDIO.competitors = j.competitors || [];
      ASTUDIO.copy = null; ASTUDIO.sku = "";
      if ((j.failed || []).length) {
        ASTUDIO.note = j.failed.length + " competitor ASIN"
          + (j.failed.length > 1 ? "s" : "") + " could not be read: "
          + j.failed.map(f => f.asin).join(", ")
          + ". The rest were used.";
      }
    } else {
      ASTUDIO.source = null;
      ASTUDIO.note = (j && j.error) || "Could not read that ASIN.";
    }
  } catch (e) {
    ASTUDIO.source = null; ASTUDIO.note = "Could not read that ASIN: " + e;
  }
  ASTUDIO.busy = ""; asStudioRender();
}

// ------------------------------------------------------------------ step 2
async function asStudioGenerate() {
  if (!ASTUDIO.source) { ASTUDIO.note = "Research an ASIN first."; asStudioRender(); return; }
  const brand = ((document.getElementById("as_brand") || {}).value || "").trim();
  if (!brand) {
    ASTUDIO.note = "Enter the brand this listing goes out under — that is what "
                 + "keeps the copy branded rather than generic.";
    asStudioRender(); return;
  }
  ASTUDIO.brand = brand;
  ASTUDIO.busy = "generate"; ASTUDIO.note = ""; asStudioRender();
  try {
    const j = await (await fetch("/asin-studio/generate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_asBody({
        source: ASTUDIO.source, competitors: ASTUDIO.competitors, brand: brand,
        marketplace: (typeof WS_MARKET !== "undefined" ? WS_MARKET : "") }))
    })).json();
    if (j && j.ok) {
      ASTUDIO.copy = j.copy || null;
      ASTUDIO.attributes = j.attributes || {};
      ASTUDIO.ipNotes = j.ip_notes || [];
      ASTUDIO.findings = j.findings || [];
      ASTUDIO.brandNote = j.brand_note || "";
    } else {
      ASTUDIO.note = (j && j.error) || "The copywriter failed.";
    }
  } catch (e) { ASTUDIO.note = "The copywriter failed: " + e; }
  ASTUDIO.busy = ""; asStudioRender();
}

// ------------------------------------------------------------------ step 3
async function asStudioCreateDraft() {
  if (!ASTUDIO.copy) { ASTUDIO.note = "Generate the copy first."; asStudioRender(); return; }
  const price = ((document.getElementById("as_price") || {}).value || "").trim();
  const days = ((document.getElementById("as_days") || {}).value || "3").trim();
  ASTUDIO.busy = "draft"; ASTUDIO.note = ""; asStudioRender();
  try {
    const j = await (await fetch("/asin-studio/create-draft", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_asBody({
        copy: ASTUDIO.copy, attributes: ASTUDIO.attributes,
        brand: ASTUDIO.brand,
        source_asin: (ASTUDIO.source || {}).asin || "",
        price: price, handling_days: days,
        marketplace: (typeof WS_MARKET !== "undefined" ? WS_MARKET : "") }))
    })).json();
    if (j && j.ok) {
      ASTUDIO.sku = j.sku || "";
      ASTUDIO.note = j.message || "Draft created.";
      if (typeof loadRows === "function") { try { loadRows(); } catch (e) {} }
    } else { ASTUDIO.note = (j && j.error) || "Could not create the draft."; }
  } catch (e) { ASTUDIO.note = "Could not create the draft: " + e; }
  ASTUDIO.busy = ""; asStudioRender();
}

// Hand the researched product to the existing Image Studio, seeded with the
// REAL photo. Not a second image pipeline -- the same STUDIO the rest of the
// app uses, so main, secondary and A+ all behave exactly as they do elsewhere.
function asStudioImages() {
  const s = ASTUDIO.source || {};
  const img = s.main_image || s.image || (s.images || [])[0] || "";
  if (!img) { ASTUDIO.note = "That ASIN returned no image to work from."; asStudioRender(); return; }
  try {
    STUDIO = {
      skus: [ASTUDIO.sku || (s.asin || "ASIN")],
      items: [{ sku: ASTUDIO.sku || (s.asin || "ASIN"),
                title: (ASTUDIO.copy && ASTUDIO.copy.title) || s.title || "",
                asin: s.asin || "", images: s.images || [img], img: img,
                source_image: img,
                product_type: s.product_type || "",
                attributes: ASTUDIO.attributes || s.attributes || {} }],
      brand: ASTUDIO.brand || (typeof accountBrand === "function" ? accountBrand() : ""),
      manualRef: img, recipes: [], results: {}
    };
    if (typeof _studioShow === "function") _studioShow();
    if (typeof loadRecipes === "function") {
      loadRecipes().then(() => { try { renderStudio(); } catch (e) {} });
    } else if (typeof renderStudio === "function") { renderStudio(); }
  } catch (e) { ASTUDIO.note = "Could not open the Image Studio: " + e; }
}

// ------------------------------------------------------------------ render
function asStudioRender() {
  const host = document.getElementById("asinstudiobody");
  if (!host) return;
  const s = ASTUDIO.source, c = ASTUDIO.copy;
  let h = "";

  if (ASTUDIO.note) {
    h += '<div class="gendiag' + (ASTUDIO.sku ? " ok" : "") + '">'
       + _asEsc(ASTUDIO.note)
       + (ASTUDIO.sku
          ? ' <button class="linkbtn" onclick="navTo(\'listings\')">Open it in Listings</button>'
          : "")
       + "</div>";
  }

  // --- step 1 -------------------------------------------------------------
  h += '<div class="srcgroup">1 · The product to write about</div>'
     + '<div class="wstoolbar" style="gap:8px;flex-wrap:wrap">'
     + '<input id="as_asin" class="ed" placeholder="ASIN to generate content for…" '
     + 'style="min-width:200px" value="' + _asEsc((s && s.asin) || "") + '">'
     + '<input id="as_comps" class="ed" placeholder="Competitor ASINs (optional, space separated)" '
     + 'style="min-width:300px;flex:1">'
     + '<button class="mktbtn on" onclick="asStudioResearch()"'
     + (ASTUDIO.busy === "research" ? " disabled" : "") + '>'
     + (ASTUDIO.busy === "research"
        ? '<span class="genspin"></span> Reading Amazon…'
        : '<i class="ti ti-search"></i> Research')
     + "</button></div>"
     + '<div class="cc" style="margin:6px 0 14px">Read-only. The ASIN is a '
     + '<b>reference for the product facts</b> — this creates a NEW listing '
     + 'under your own brand, and never joins or claims that ASIN.</div>';

  if (s) {
    const img = s.main_image || s.image || (s.images || [])[0] || "";
    h += '<div class="tile" style="max-width:100%;display:flex;gap:14px;padding:12px;margin-bottom:16px">'
       + (img ? '<img src="' + _asEsc(img) + '" style="width:90px;height:90px;'
                + 'object-fit:contain;border-radius:8px;background:var(--paper)">' : "")
       + '<div style="flex:1;min-width:0">'
       + '<div style="font-weight:600">' + _asEsc(s.title || "(no title)") + "</div>"
       + '<div class="cc" style="margin-top:4px">'
       + '<span class="asin">' + _asEsc(s.asin || "") + "</span>"
       + (s.brand ? ' · source brand <b>' + _asEsc(s.brand) + "</b>" : "")
       + (s.product_type ? " · " + _asEsc(s.product_type) : "")
       + "</div>"
       + ((s.bullets || []).length
          ? '<ul class="cc" style="margin:8px 0 0;padding-left:18px">'
            + s.bullets.slice(0, 3).map(b => "<li>" + _asEsc(b) + "</li>").join("")
            + "</ul>" : "")
       + "</div></div>";
    if (ASTUDIO.competitors.length) {
      h += '<div class="cc" style="margin:-8px 0 16px">Plus '
         + ASTUDIO.competitors.length + " competitor"
         + (ASTUDIO.competitors.length > 1 ? "s" : "")
         + " for category context: "
         + ASTUDIO.competitors.map(x => '<span class="asin">'
             + _asEsc(x.asin || "") + "</span>").join(" ") + "</div>";
    }
  }

  // --- step 2 -------------------------------------------------------------
  if (s) {
    h += '<div class="srcgroup">2 · Your brand, and the copy</div>'
       + '<div class="wstoolbar" style="gap:8px;flex-wrap:wrap">'
       + '<input id="as_brand" class="ed" placeholder="Brand this listing goes out under…" '
       + 'style="min-width:240px" value="' + _asEsc(ASTUDIO.brand) + '"'
       + ' list="as_brandlist">'
       + '<datalist id="as_brandlist">'
       + ((typeof accountBrands === "function" ? accountBrands() : [])
           .map(b => '<option value="' + _asEsc(b) + '">').join(""))
       + "</datalist>"
       + '<button class="mktbtn on" onclick="asStudioGenerate()"'
       + (ASTUDIO.busy === "generate" ? " disabled" : "") + '>'
       + (ASTUDIO.busy === "generate"
          ? '<span class="genspin"></span> Writing…'
          : '<i class="ti ti-sparkles"></i> Generate copy')
       + "</button></div>"
       + '<div class="cc" style="margin:6px 0 14px">Your own trademarks are '
       + 'suggested, but the field takes anything. On <b>submit</b> a brand this '
       + 'account is not registered for is replaced with your own and the swap '
       + 'is reported — that rule is not changed here.</div>';
  }

  if (ASTUDIO.brandNote) {
    h += '<div class="gendiag" style="border-color:var(--warn)">⚠ '
       + _asEsc(ASTUDIO.brandNote) + "</div>";
  }

  if (c) {
    h += '<div class="tile" style="max-width:100%;padding:14px;margin:10px 0">'
       + '<div style="font-weight:600;margin-bottom:6px">' + _asEsc(c.title || "") + "</div>"
       + '<ul style="margin:0 0 10px;padding-left:18px">'
       + (c.bullets || []).map(b => "<li>" + _asEsc(b) + "</li>").join("")
       + "</ul>"
       + '<div class="cc" style="white-space:pre-wrap">' + _asEsc(c.description || "") + "</div>"
       + (c.search_terms
          ? '<div class="cc" style="margin-top:10px"><b>Search terms:</b> '
            + _asEsc(c.search_terms) + "</div>" : "")
       + "</div>";

    // The checks are shown BEFORE the draft button, because they are the reason
    // to read it rather than press on.
    if ((ASTUDIO.findings || []).length) {
      h += '<div class="gendiag bad"><b>' + ASTUDIO.findings.length
         + " compliance / IP finding"
         + (ASTUDIO.findings.length > 1 ? "s" : "") + "</b> — these travel with "
         + "the draft and will hold it until dealt with:<ul style=\"margin:6px 0 0;"
         + "padding-left:18px\">"
         + ASTUDIO.findings.slice(0, 8).map(f =>
             "<li>" + _asEsc((f.severity || "") + " · " + (f.kind || "")
                             + (f.term ? " — " + f.term : "")
                             + (f.why ? ": " + f.why : "")) + "</li>").join("")
         + "</ul></div>";
    }
    if ((ASTUDIO.ipNotes || []).length) {
      h += '<div class="gendiag">Removed automatically: '
         + _asEsc(ASTUDIO.ipNotes.slice(0, 6).join("; ")) + "</div>";
    }

    // --- step 3 -----------------------------------------------------------
    h += '<div class="srcgroup">3 · Make it a draft</div>'
       + '<div class="wstoolbar" style="gap:8px;flex-wrap:wrap">'
       + '<label class="cc">Price <input id="as_price" class="ed" style="width:90px" placeholder="0.00"></label>'
       + '<label class="cc">Handling days <input id="as_days" class="ed" style="width:60px" value="3"></label>'
       + '<button class="mktbtn on" onclick="asStudioCreateDraft()"'
       + (ASTUDIO.busy === "draft" ? " disabled" : "") + '>'
       + (ASTUDIO.busy === "draft" ? '<span class="genspin"></span> Saving…'
                                   : '<i class="ti ti-file-plus"></i> Create draft')
       + "</button>"
       + '<button class="mktbtn" onclick="asStudioImages()">'
       + '<i class="ti ti-photo"></i> Open Image Studio</button>'
       + "</div>"
       + '<div class="cc" style="margin-top:6px">The draft lands in Listings as '
       + '<b>Needs review</b>, with the compliance and IP checks still to run. '
       + "Nothing is sent to Amazon until you submit it there.</div>";
  }

  host.innerHTML = h;
}

function asStudioOnOpen() { asStudioRender(); }
