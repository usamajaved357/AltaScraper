/* static/js/pdp.js -- the full-screen listing editor, as an OVERLAY.
 *
 * Layout is docspdp-seller-central-layout.html's: a top bar, a product hero, a
 * row of tabs, a left sidebar of quick actions and checks, and one content
 * column per tab.
 *
 * IT IS AN OVERLAY, NOT A ROUTE. The listings grid is never unmounted -- this
 * panel is laid over it and the grid sits underneath with its filters, its
 * Drafts/Live/All switch, its selection and its expanded rows all intact. That
 * is what makes "back leaves everything exactly as it was" true by
 * construction rather than by remembering to save and restore it. The address
 * still becomes /w/<ws>/listing/<sku> so a listing can be linked and
 * bookmarked, but nothing reloads.
 *
 * IT BUILDS ALMOST NOTHING OF ITS OWN. Every editor on this page is the one the
 * drawer already uses, redistributed across the tabs:
 *
 *     _fullDataParts(r)   images, bullets, description, search terms,
 *                         highlights, identity, offer, compliance, and the
 *                         ATTRIBUTE MODEL the table below is drawn from
 *     dwTitleParts(r)     the title editor, its counter, its 27 Jul 2026 cap
 *     _dwWarnings(r)      the warnings, severity-coloured
 *     editCell / saveEdit one write path, shared with the drawer
 *
 * That is the design (CLAUDE.md Rule 12). Those blocks carry behaviour that is
 * invisible until it is missing: the byte budget shared across five bullets,
 * the 249-byte search-terms cliff that de-indexes a listing silently, the
 * required stars, the nested sub-field boxes, the live-vs-Amazon comparison. A
 * second set of editors would drift, and the drift would only show when one
 * screen let something through that the other stopped.
 *
 * THE ATTRIBUTE TABLE IS THE ONE NEW PRESENTATION, and it is a presenter only:
 * it reads the model _fullDataParts already computed and calls the same
 * editCell() and lvVerdict(). It decides nothing about which fields exist,
 * which Amazon requires, or what its allowed values are.
 */

let PDP_SKU = "";
let PDP_TAB = "details";
/* Where the grid was when you left it. The grid keeps its DOM -- it is covered,
 * not emptied -- so its filters and selection survive on their own. Scroll does
 * NOT: the overlay takes the page's height, and the browser clamps scrollTop.
 * The sidebar is position:sticky and the WINDOW is what scrolls
 * (dashboard.css:331), so this is the one number carried by hand. */
let PDP_BACK_SCROLL = 0;
/* Which attribute rows the table is showing: all | differs | amazon | empty. */
let PDP_ATTR_FILTER = "all";

/* THE ROW THIS PAGE IS DRAWING -- ours, or one built from Amazon's own data.
 *
 *     "ALL listings open the PDP overlay regardless of origin. A listing synced
 *      from Amazon is still a listing you manage. ... For synced-only listings,
 *      the PDP should show Amazon's current attribute data as the input values
 *      (from the catalogue/summaries), not empty fields."
 *
 * MEASURED: 7 of jack_uk's 47 live SKUs and 18 of nestwell_goods' 62 have no
 * row in this app -- made in Seller Central, made by another tool, or their
 * draft was deleted. Those opened a different UI, which is the whole complaint:
 * "Most live listings open the Optimize live listing modal instead of the PDP."
 */
function pdpRow(){
  if(!PDP_SKU) return null;
  const own = (typeof ROWS !== "undefined" && ROWS)
    ? ROWS.find(x => String(x.sku) === String(PDP_SKU)) : null;
  return own || pdpCatalogueRow(PDP_SKU);
}

/* A row shaped like ours, filled from what AMAZON says.
 *
 * Two sources, both already fetched and cached by the time this runs:
 *   LIVE_ITEMS   the catalogue snapshot -- sku, asin, title, price, picture
 *   lvGet(sku)   getListingsItem -- the attributes, the copy, the summaries
 *
 * NOTHING IS INVENTED. Every field is either Amazon's or absent, and the row is
 * stamped `catalogue_only` so the page can say where it came from and offer the
 * one thing that changes it (Sync, which pulls the listing in as a real row).
 *
 * It is NOT written anywhere. This is a view of Amazon's data, not a draft --
 * inventing a half-empty row in the store the moment somebody looked at a
 * listing would put rows in the database that nobody asked for.
 */
function pdpCatalogueRow(sku){
  sku = String(sku || "");
  const it = (typeof LIVE_ITEMS !== "undefined" && LIVE_ITEMS)
    ? LIVE_ITEMS.find(x => String(x && x.sku) === sku) : null;
  const L = (typeof lvGet === "function") ? lvGet(sku) : null;
  const live = (L && L.state === "ok") ? L : null;
  if(!it && !live) return null;

  const C = (live && live.content) || {};
  const S = (live && live.summary) || {};
  const V = (live && live.values) || {};
  const first = k => (C[k] && C[k].length) ? C[k][0] : "";

  const row = {
    sku: sku,
    catalogue_only: true,
    // LIVE by definition: Amazon is the only reason we know about it.
    status: "LIVE",
    title: String(S.itemName || first("item_name") || (it && it.title) || ""),
    // Amazon's own ASIN for this listing, in the field the app reads as OURS.
    // r.asin is the COMPETITOR slot and stays empty -- there is no competitor
    // here, this listing was never researched from one (CLAUDE.md Rule 1).
    own_asin: String(S.asin || (it && it.asin) || ""),
    asin: "",
    brand: String(S.brand || V.brand || ""),
    product_type: String((live && live.product_type) || ""),
    barcode: String(V.externally_assigned_product_identifier || ""),
    our_price: String((it && it.price) || "").replace(/[^0-9.]/g, ""),
    handling_days: String(V["fulfillment_availability.lead_time_to_ship_max_days"]
                          || V.lead_time_to_ship_max_days || ""),
    description_html: first("product_description"),
    search_terms: (C.generic_keyword || []).join(" "),
    attributes: V,
    attrs: JSON.stringify(V),
    warnings: [],
    row: 0,
  };
  (C.bullet_point || []).slice(0, 5).forEach(function(b, i){
    row["bullet_" + (i + 1)] = b;
  });
  return row;
}

/* Is the page showing a listing this app holds no draft of? */
function pdpIsCatalogueOnly(r){ return !!(r && r.catalogue_only); }

function pdpIsOpen(){ return !!PDP_SKU; }

/* ---- open / close ------------------------------------------------------ */

function pdpOpen(sku){
  sku = String(sku || "");
  const own = (typeof ROWS !== "undefined" && ROWS)
    ? ROWS.find(x => String(x.sku) === sku) : null;
  // EVERY LISTING OPENS HERE NOW, ours or Amazon's.
  //
  //     "ALL listings open the PDP overlay regardless of origin. A listing
  //      synced from Amazon is still a listing you manage."
  //
  // A listing with no draft used to be turned away, and openListing sent it to
  // the Optimize modal instead -- a third detail view for the majority of live
  // listings. It is drawn from Amazon's own data now (pdpCatalogueRow).
  //
  // AND THE DATA IS FETCHED IF IT IS NOT ALREADY HERE. lvEnsure is the one
  // place that reads a live listing from Amazon, and it re-renders this page
  // when the answer lands, so opening on a cold cache shows the catalogue's
  // title and picture immediately and fills in the rest a moment later.
  const cat = own ? null : pdpCatalogueRow(sku);
  if(!own && typeof lvEnsure === "function"){
    try{
      lvEnsure(cat || {sku: sku, status: "LIVE"});
    }catch(e){}
  }
  if(!own && !cat){
    if(typeof toast === "function")
      toast("Nothing is known about " + sku + " — it is not in this app and not "
            + "in Amazon's catalogue for this account. Press Sync and try again.");
    return;
  }
  if(!PDP_SKU){                                  // entering from the grid, not
    try{ PDP_BACK_SCROLL = window.scrollY || 0; }catch(e){ PDP_BACK_SCROLL = 0; }
  }                                              // moving between listings
  const changed = PDP_SKU !== sku;
  PDP_SKU = sku;
  if(changed){
    PDP_TAB = "details";                         // a new listing starts at the front
    // A DIFFERENT LISTING HAS NOT BEEN EDITED YET. Moving between two listings
    // without closing the page would otherwise carry the bar across, and it
    // would be reporting the last listing's work over this one's fields.
    PDP_DIRTY = false;
  }
  // The drawer and this page are two views of one listing; having both open
  // means two title boxes saving to the same cell.
  if(typeof closeDrawer === "function"){ try{ closeDrawer(); }catch(e){} }

  const host = document.getElementById("pdp");
  if(host){
    // FLEX, NOT BLOCK. The backdrop centres the panel and holds it to the top
    // (#pdp.in in pdp.css); an inline display:block is more specific than that
    // class rule and silently undid the centring, leaving a 680px card hard
    // against the left edge with all the backdrop on the right.
    host.style.display = "flex";
    // CLICKING THE PAGE BEHIND CLOSES THE PANEL, which is how every other
    // layer in this app behaves and the reason the listings page is left
    // visible at all. Only a click that lands on the BACKDROP itself counts --
    // ev.target === host -- so a click anywhere inside the panel, including on
    // its own padding, does nothing. Assigned rather than added, so re-opening
    // cannot stack a second listener.
    host.onclick = function(ev){ if(ev.target === host) pdpClose(); };
  }
  document.body.classList.add("pdp-on");
  pdpRender();
  // The slide-in is a class added on the next frame, so the browser has a
  // painted "off screen" state to animate FROM. Setting it in the same frame
  // as display:block would show the panel already in place.
  if(host){
    try{ requestAnimationFrame(function(){ host.classList.add("in"); }); }
    catch(e){ host.classList.add("in"); }
  }
  try{ window.scrollTo(0, 0); }catch(e){}

  // The product type's schema drives the attribute dropdowns and the nested
  // sub-field boxes. openDrawer fetches it on demand for exactly this reason;
  // without it the fields render as flat boxes with no allowed values.
  //
  // Whichever row this page ended up with -- ours, or Amazon's. On a
  // catalogue-only listing the product type is the one Amazon reports, so the
  // dropdowns are right for what the listing actually IS.
  const r = own || cat || {sku: sku};
  if(r.product_type && typeof loadSchemas === "function"
     && !(SCHEMAS[r.product_type] && (SCHEMAS[r.product_type].attrs||[]).length)){
    loadSchemas([r.product_type], false, (typeof rowMkt==="function")?rowMkt(r):"")
      .then(() => { if(PDP_SKU === sku) pdpRender(); }).catch(() => {});
  }
  // What Amazon currently holds, for the comparison column. Already asked for
  // above when there is no draft -- lvEnsure is re-entrant, so a second call
  // while one is in flight does nothing.
  if(typeof lvEnsure === "function") lvEnsure(r);

  if(typeof altaSyncUrl === "function") altaSyncUrl();
}

/* Back to the grid, which is still underneath exactly as it was. */
function pdpClose(){
  if(!PDP_SKU) return;
  PDP_SKU = "";
  // "When saved or cancelled: bar disappears." Both buttons close the page, so
  // it goes with it -- and the flag has to go too, or the next listing opens
  // wearing the last one's bar.
  PDP_DIRTY = false;
  const host = document.getElementById("pdp");
  if(host){
    host.classList.remove("in");
    host.style.display = "none";
    host.innerHTML = "";
    host.onclick = null;
  }
  document.body.classList.remove("pdp-on");
  if(typeof altaSyncUrl === "function") altaSyncUrl();
  // After the grid is on screen again, not before -- scrolling a hidden
  // element sets nothing.
  try{ window.scrollTo(0, PDP_BACK_SCROLL || 0); }catch(e){}
}

/* ESCAPE CLOSES IT, unless you are in the middle of typing.
 *
 * Every editor on this page is a contenteditable, an input, a textarea or a
 * select, and they save on blur. Escape while the caret is in one would close
 * the page out from under an edit in progress, so the first Escape leaves the
 * field (which commits it through the normal blur) and a second closes.
 *
 * Registered once, on the document, rather than on the panel: the panel is
 * rebuilt on every render and a listener on it would be dropped each time. */
document.addEventListener("keydown", function(ev){
  if(ev.key !== "Escape" || !pdpIsOpen()) return;
  const el = document.activeElement;
  const tag = el ? String(el.tagName || "").toLowerCase() : "";
  const typing = el && (el.isContentEditable === true
                        || tag === "input" || tag === "textarea" || tag === "select");
  if(typing){ try{ el.blur(); }catch(e){} return; }
  // A dialog or a menu over the page owns Escape first.
  if(document.querySelector(".uidlg, .uiinline")) return;
  pdpClose();
});

/* ---- the pieces -------------------------------------------------------- */

/* The status word, in the four-status vocabulary liststatus.js owns, plus what
 * Amazon itself says about the listing when we have read it. The WORD comes
 * from lsStatusOf so this page can never disagree with the card and the table
 * about a listing's status. */
function pdpStatusBadge(r){
  const st = (typeof lsStatusOf === "function") ? lsStatusOf(r)
                                                : String(r.status||"").toUpperCase();
  const cls = st === "LIVE" ? "live" : st === "SUBMITTED" ? "sent"
            : st === "GENERATED" ? "gen" : st === "QUEUED" ? "queued" : "other";
  const L = (typeof lvGet === "function") ? lvGet(r.sku) : null;
  const amz = (L && L.state === "ok" && L.amazon_status) ? (" · " + L.amazon_status) : "";
  return '<span class="pdp-hb ' + cls + '">' + esc(st || "—") + esc(amz) + '</span>';
}

function pdpHero(r){
  const urls = (typeof _rowImages === "function") ? _rowImages(r) : [];
  const asin = (typeof rowAsin === "function") ? (rowAsin(r)||{}) : {};
  const shownAsin = asin.own || asin.source || r.asin || "";
  // "not live yet" is said in words rather than left as a blank, because an
  // empty ASIN and an ASIN we could not read are different things.
  const asinTxt = asin.own ? esc(asin.own)
    : (asin.source ? esc(asin.source) + ' <span class="pdp-dim">(competitor reference — not ours)</span>'
                   : '<span class="pdp-dim">not live yet</span>');
  const cost = (typeof _dwCost === "function") ? _dwCost(r) : "";
  const cur = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  const profit = String(r.profit == null ? "" : r.profit).replace(/^[A-Z]{3}/, "");

  return '<div class="pdp-hero"><div class="pdp-hero-in">'
    + '<div class="pdp-heroimg">'
    +   (urls && urls.length
        // 120px, the size .pdp-heroimg draws. It was the raw URL, so opening a
        // listing fetched the full-size picture to fill a small square.
        // EAGER, not lazy: this is the one image on the screen you just asked
        // for, and it is above the fold by definition.
        ? '<img src="' + esc(thumbUrl(urls[0], 120)) + '" decoding="async"'
          + ' fetchpriority="high" onerror="this.remove()">'
        : '<i class="ti ti-photo"></i>')
    + '</div>'
    + '<div class="pdp-heroinfo">'
    +   '<div class="pdp-ptitle">' + (esc(r.title || "") || '<span class="pdp-dim">(no title)</span>') + '</div>'
    +   '<div class="pdp-meta">'
    +     '<div><span class="pdp-mlabel">ASIN</span>' + asinTxt + '</div>'
    +     '<div><span class="pdp-mlabel">SKU</span><b>' + esc(r.sku || "") + '</b></div>'
    +     '<div><span class="pdp-mlabel">Barcode</span>'
    +       (r.barcode ? '<b>' + esc(r.barcode) + '</b>' : '<span class="pdp-dim">none</span>') + '</div>'
    +     '<div><span class="pdp-mlabel">Brand</span>'
    +       (r.brand ? '<b>' + esc(r.brand) + '</b>' : '<span class="pdp-dim">not set</span>') + '</div>'
    +   '</div>'
    +   '<div class="pdp-badges">'
    +     pdpStatusBadge(r)
    +     (profit ? '<span class="pdp-hb profit">Profit ' + esc(cur + profit) + '</span>' : "")
    +     (cost ? '<span class="pdp-hb cost">Cost ' + esc(cost) + '</span>' : "")
    // THE WARNING-COUNT BADGE WAS HERE, and went with the three on the list.
    //
    //     "i dont want this symbol at all, i already have 3 symbols for
    //      restricted compliance and claims risk, i will maintain those"
    //
    // It is the least useful of the four places it appeared: this page has a
    // Safety & Compliance TAB, two inches below, that lists every warning in
    // full with what each one matched on. A badge saying "1" above a tab that
    // says which one is a count of something already on screen.
    +   '</div>'
    + '</div></div></div>';
}

/* AMAZON'S OWN FOUR, PLUS VARIATIONS WHEN THERE ARE ANY.
 *
 *     "Normal listing (no variations): Product Details | Images | Offer |
 *      Safety & Compliance. Listing with variations: ... | Variations | ...
 *      There is NO 'Attributes' tab."
 *
 * THE ATTRIBUTES TAB IS GONE, not hidden. Its whole contents -- brand, EAN,
 * material, colour, weight, included components, every schema field -- now sits
 * on Product Details under the description, which is where Seller Central puts
 * it. A tab called "Attributes" beside one called "Product details" asks the
 * reader to guess which of two names covers "colour", and the answer was never
 * obvious.
 *
 * VARIATIONS APPEARS ONLY WHEN THE LISTING HAS THEM. A tab that is empty on
 * nine listings in ten is a tab that trains you to skip it.
 */
const PDP_TABS = [
  {key:"details",    label:"Product Details"},
  {key:"images",     label:"Images"},
  {key:"variations", label:"Variations", only: "hasVariations"},
  {key:"offer",      label:"Offer"},
  {key:"compliance", label:"Safety & Compliance"},
];

/* Does this listing have variations? Asked of the row the app already holds --
 * a parent SKU, a variation theme, or children recorded against it. */
function pdpHasVariations(r){
  if(!r) return false;
  if(String(r.status || "").toUpperCase() === "PARENT") return true;
  if(String(r.variation_theme || "").trim()) return true;
  if(String(r.parent_sku || "").trim()) return true;
  const v = r.variations;
  if(Array.isArray(v) && v.length) return true;
  if(v && typeof v === "object" && (v.children || []).length) return true;
  return false;
}

/* The tabs this listing actually gets. */
function pdpTabsFor(r){
  const has = {hasVariations: pdpHasVariations(r)};
  return PDP_TABS.filter(function(t){ return !t.only || has[t.only]; });
}

function pdpTab(name){
  PDP_TAB = String(name || "details");
  pdpRender();
  try{ window.scrollTo(0, 0); }catch(e){}
}

function pdpTabBar(r){
  const tabs = pdpTabsFor(r);
  // A TAB THAT NO LONGER EXISTS MUST NOT LEAVE A BLANK PAGE. PDP_TAB survives
  // between listings, so moving from a listing with variations to one without
  // -- or opening an old bookmark that says "attributes" -- would otherwise
  // select nothing and draw nothing.
  if(!tabs.some(function(t){ return t.key === PDP_TAB; })) PDP_TAB = "details";
  return '<div class="pdp-tabs">' + tabs.map(function(t){
    return '<div class="pdp-tab' + (PDP_TAB === t.key ? " active" : "") + '"'
         + ' onclick="pdpTab(\'' + t.key + '\')">' + esc(t.label) + '</div>';
  }).join("") + '</div>';
}

/* The left rail: the things you go and do, and the four checks at a glance.
 * Every one of these calls the function the drawer called. */
function pdpSidebar(r){
  const sku = String(r.sku);
  const live = (typeof isAmazonLive === "function") ? isAmazonLive(r) : false;
  const ownAsin = (typeof ownLiveAsin === "function") ? ownLiveAsin(r) : "";
  const chk = function(cls, icon, label, tab){
    return '<div class="pdp-ck ' + cls + '" onclick="pdpTab(\'' + tab + '\')">'
         + '<i class="ti ' + icon + '"></i> ' + esc(label) + '</div>';
  };

  /* THE RAIL AND THE COMPLIANCE TAB READ THE SAME WARNINGS NOW.
   *
   *     "The left sidebar shows Restricted, Compliance, and Claim risks all as
   *      GREEN — but Compliance tab shows 2 HIGH warnings. The indicators are
   *      lying."
   *
   * They were. The rail read three row fields of its own -- r.restricted.matched,
   * r.viability.matched, r.claim_flags -- and the tab read r.warnings, so a
   * warning could exist in one and not the other and nothing reconciled them.
   * Both go through liststatus.js now (Rule 12): lsWarnTypes counts r.warnings
   * by type, lsCheckTone turns a type into a colour.
   *
   * high -> red, medium -> amber, none or low -> green.
   */
  const wt = (typeof lsWarnTypes === "function") ? lsWarnTypes(r) : {};
  const tone = (typeof lsCheckTone === "function")
             ? lsCheckTone : function(){ return "ok"; };
  const wcount = (typeof lsCheckCount === "function")
               ? lsCheckCount : function(){ return 0; };
  // Which warning types belong under which light. Named here rather than
  // guessed at in three places.
  const T_RESTRICTED = ["restricted", "restricted_product", "prohibited"];
  const T_COMPLIANCE = ["compliance_risk", "hazmat", "documents_required"];
  const T_CLAIMS     = ["ip_risk", "claim_risk", "unsupported_claim"];
  // The row's OWN verdicts still count, because they are not all mirrored into
  // warnings: listing/restricted.py writes r.restricted and never a warning
  // row, so ignoring it would swap one lie for another.
  const restrictedHit = !!(r.restricted && r.restricted.matched
                           && r.restricted.matched.length);
  const viabilityHit  = !!(r.viability && r.viability.matched
                           && r.viability.matched.length);
  const claimHit      = ((r.claim_flags || []).length > 0);
  const restrictedTone = restrictedHit ? "bad" : tone(wt, T_RESTRICTED);
  // A verdict on the row is a warning nobody wrote down: it colours amber, and
  // an actual HIGH warning of that type still overrides it to red.
  const complianceTone = (function(){
    const t = tone(wt, T_COMPLIANCE);
    return (t === "ok" && viabilityHit) ? "warn" : t;
  })();
  const claimsTone = (function(){
    const t = tone(wt, T_CLAIMS);
    return (t === "ok" && claimHit) ? "warn" : t;
  })();
  const nRestricted = wcount(wt, T_RESTRICTED);
  const nCompliance = wcount(wt, T_COMPLIANCE);
  const nClaims     = wcount(wt, T_CLAIMS) || claimHit ? (wcount(wt, T_CLAIMS)
                      || (r.claim_flags || []).length) : 0;
  const label = function(base, n, tone_){
    if(tone_ === "ok") return base;
    return n ? (base + " — " + n) : (base + " — see why");
  };
  const icon = function(tone_, okIcon){
    return tone_ === "ok" ? okIcon : "ti-alert-triangle";
  };
  return '<div class="pdp-side">'
    + (live && ownAsin
        ? '<button class="pdp-sbbtn" onclick="optimizeLive(\'' + esc(ownAsin) + '\',\'' + esc(sku) + '\')">'
          + '<i class="ti ti-sparkles"></i> Optimize live copy</button>'
        : "")
    + '<div class="pdp-sbsec"><div class="pdp-sblabel">Quick actions</div>'
    +   '<div class="pdp-sbitem" onclick="openStudioSingle(\'' + esc(sku) + '\')"><i class="ti ti-photo-edit"></i> Image studio</div>'
    +   '<div class="pdp-sbitem" onclick="askAbout(\'' + esc(sku) + '\')"><i class="ti ti-message-circle"></i> Ask Claude</div>'
    +   '<div class="pdp-sbitem" onclick="pdpTab(\'compliance\')"><i class="ti ti-code"></i> Raw data</div>'
    + '</div>'
    + '<div class="pdp-sbsec"><div class="pdp-sblabel">Checks</div>'
    +   chk(restrictedTone, icon(restrictedTone, "ti-shield-check"),
            label("Restricted", nRestricted, restrictedTone), "compliance")
    +   chk(complianceTone, icon(complianceTone, "ti-file-check"),
            (complianceTone === "ok" ? "Compliance"
             : (nCompliance ? "Compliance — " + nCompliance
                            : "Docs may be demanded")), "compliance")
    +   chk(claimsTone, icon(claimsTone, "ti-circle-check"),
            (claimsTone === "ok" ? "Claim risks"
             : (nClaims + " claim risk" + (nClaims === 1 ? "" : "s"))),
            "compliance")
    +   chk("info", "ti-message-dots", "Amazon feedback", "compliance")
    + '</div></div>';
}

/* ---- the attributes table ----------------------------------------------
 * A PRESENTER of _fullDataParts' attrModel. It re-decides nothing: which keys
 * exist, which Amazon requires, which its Preview flagged and what the allowed
 * values are all arrive already worked out, and the editable cell is the same
 * editCell() the drawer's grid uses, saving through the same saveEdit(). */

function pdpAttrFilter(f){ PDP_ATTR_FILTER = String(f || "all"); pdpRender(); }

/* THE (?) BUBBLE, IN AMAZON'S OWN WORDS.
 *
 *     "Amazon shows a (?) circle next to every field label. ... Do NOT hardcode
 *      tooltip text. Read it from the cached product type schema."
 *
 * There was nothing to read it from: dashboard._load_schema pulled `title` out
 * of each property and dropped `description` on the floor. It keeps it now, the
 * /schema route serves it, and this draws it verbatim -- no rewording, because
 * the wording is the part that distinguishes two attributes whose names sound
 * the same.
 *
 * NO BUBBLE WHERE THERE IS NO TEXT. An empty (?) is a promise of an explanation
 * that does not exist, which is worse than not offering one.
 */
function pdpHelp(m, key){
  const h = (m && m.help) ? (m.help[key] || m.help[String(key).split(".")[0]] || "") : "";
  if(!h) return "";
  return '<span class="pdp-help" tabindex="0">?<span class="tip">'
       + esc(h) + '</span></span>';
}

/* THE ATTRIBUTES, AS A SECTION OF PRODUCT DETAILS.
 *
 * Was pdpAttrTable, on a tab of its own. The tab is gone -- Seller Central has
 * no "Attributes" tab and neither does the mockup -- so this is the section
 * that sits under the description. Renamed rather than wrapped, because two
 * names for one renderer is how a screen ends up with two of them. */
function pdpAttrSection(m, addCtrl){
  const body = pdpAttrRows(m);
  if(!body) return "";
  return '<div class="pdp-field pdp-attrsec">'
       + '<div class="pdp-flabel">Attributes</div>'
       + body + (addCtrl || "")
       + '</div>';
}

function pdpAttrRows(m){
  if(!m) return '<div class="pdp-note">No attributes yet.</div>';
  const sku = m.sku;
  const L = (typeof lvGet === "function") ? lvGet(sku) : null;
  const live = (L && L.state === "ok") ? (L.values || {}) : {};
  const lbl = k => m.titles[k] || (typeof _cleanLabel === "function" ? _cleanLabel(String(k)) : String(k));
  // WHICH FIELDS AMAZON BLAMED, by name. Built once from the stored reply so
  // each row can carry its own complaint instead of sending the reader back to
  // the banner to work out which box the message is about. Keyed on the top
  // level ("item_dimensions"), because Amazon names the parent even when the
  // fault is in a child ("item_dimensions.length.value").
  const rowIssues = {};
  const _rec = (m.row && m.row.api_issues) || null;
  ((_rec && _rec.issues) || []).forEach(function(i){
    (i.fields || []).forEach(function(f){
      const t = String(f).split(".")[0];
      (rowIssues[t] = rowIssues[t] || []).push(i);
    });
  });
  // The same order the grid uses: what the listing has, then what Amazon is
  // still asking for.
  const keys0 = [...m.aKeys, ...m.missing.filter(k => m.aKeys.indexOf(k) < 0)];

  // A GROUP IS ONE AMAZON ATTRIBUTE WITH PARTS, NOT A CATEGORY WE INVENTED.
  //
  // Amazon's definition gives some attributes sub-properties: battery is one
  // attribute holding average_life, capacity, cell_composition, iec_code and
  // weight, and each of those is itself a value+unit pair. The app already
  // stores them flattened -- "battery.capacity.value" -- and the table listed
  // all thirteen as thirteen unrelated rows between `barcode` and `brand`,
  // because the keys were only in whatever order they were written.
  //
  // So the keys are put in order here: singles keep their place, and every
  // dotted key is pulled up to sit with the first of its family, under a
  // heading. Nothing is added, removed or renamed -- only ordered.
  const keys = (function(){
    const seen = {}, out = [];
    keys0.forEach(function(k){
      const fam = String(k).split(".")[0];
      if(String(k).indexOf(".") < 0){ out.push(k); return; }
      if(seen[fam] === undefined){ seen[fam] = out.length; out.push(k); return; }
      // Insert after the last key already in this family, so the order inside
      // a group is the order Amazon's schema gave it.
      let at = seen[fam] + 1;
      while(at < out.length && String(out[at]).split(".")[0] === fam) at++;
      out.splice(at, 0, k);
    });
    return out;
  })();

  let nMatch = 0, nDiff = 0, nOnlyAmz = 0, nOnlyUs = 0;
  // Which group heading has been drawn, so one is drawn per family and only
  // when a member of it actually survived the filter.
  let openGroup = "";
  const rows = keys.map(function(k){
    const isMissing = m.missing.indexOf(k) >= 0 && !(k in m.a);
    const val = isMissing ? "" : (m.a[k] == null ? "" : m.a[k]);
    const v = (typeof lvVerdict === "function") ? lvVerdict(sku, k, val) : "";
    if(v === "same") nMatch++;
    else if(v === "differs") nDiff++;
    else if(v === "live_only") nOnlyAmz++;
    else if(v === "app_only") nOnlyUs++;

    if(PDP_ATTR_FILTER === "differs" && v !== "differs") return "";
    if(PDP_ATTR_FILTER === "amazon"  && v !== "live_only") return "";
    if(PDP_ATTR_FILTER === "empty"   && String(val).trim() !== "") return "";

    const icon = v === "same" ? '<span class="pdp-ai match" title="This app and Amazon hold the same value">✓</span>'
      : v === "differs"   ? '<span class="pdp-ai differ" title="This app and Amazon disagree">≠</span>'
      : v === "live_only" ? '<span class="pdp-ai onlyamz" title="Amazon has a value and this app does not">←</span>'
      : v === "app_only"  ? '<span class="pdp-ai onlyus" title="This app has a value and Amazon does not. It goes on the next submit.">→</span>'
      : '<span class="pdp-ai none"></span>';

    // The required marker is KEPT even though the mockup's table has no column
    // for it. Which fields Amazon demands is the single most consequential
    // thing this table can say, and the drawer's grid says it -- dropping it
    // here would make the two views disagree about what blocks a submit.
    const amazonFlagged = isMissing || !!m.flagged[k];
    const schemaReq = (m.reqList || []).indexOf(k) >= 0;
    // A RED ASTERISK, as the mockup and Amazon both use.
    //
    //     "Required fields have red asterisk."
    //
    // It was ★ and ☆. Two problems: ☆ is a hollow star that renders as a
    // tofu box in the font stack this panel uses -- visible on screen as a
    // stray glyph before "Country Of Origin" -- and neither shape says
    // "required" to anyone who has filled in a form before.
    //
    // THE TWO KINDS ARE STILL TOLD APART, because they need different actions:
    // solid red is Amazon having flagged it in a Preview (fill it or the submit
    // fails), muted red is the schema listing it as required without Amazon
    // having complained yet. Same character, different weight -- the difference
    // is in the tooltip, where the explanation belongs.
    const req = amazonFlagged
      ? '<span class="pdp-req" title="Amazon flagged this in Preview — it must be filled">*</span>'
      : (schemaReq ? '<span class="pdp-reqsoft" title="The schema lists this as required. Amazon’s last Preview did not flag it.">*</span>' : "");

    const multi = (L && L.multi) ? (L.multi[String(k).split(".")[0]] || 0) : 0;
    const hasEnum = !!(m.enums[k] && m.enums[k].length);
    // AMAZON SAYS THIS ONE CANNOT BE SET. readOnly comes off the product type
    // definition; before now nothing read it, so a field Amazon would refuse
    // looked exactly like one it would accept.
    const locked = (m.readonly || []).indexOf(k) >= 0;
    // HOW MANY VALUES AMAZON ALLOWS HERE. From the product type definition, so
    // it is right for THIS type -- see pdpMaxItems. A free-text field whose
    // schema allows more than one gets a box per value instead of one box the
    // user has to remember to comma-separate. A dropdown never does: picking
    // from an enum twice is a different control and Amazon's own page does not
    // offer it either.
    const maxItems = pdpMaxItems(m, k);
    const wantsMulti = !hasEnum && (maxItems === 0 || maxItems > 1);

    const ctrl = locked
      ? '<span class="pdp-ro" title="Amazon marks this attribute read-only for '
        + 'this product type — it cannot be set from here.">'
        + esc(String(val) || "—") + '</span>'
        + '<i class="ti ti-lock pdp-lock" title="Read-only on Amazon"></i>'
      : (multi
        ? '<span class="pdp-ro" title="Amazon holds ' + multi + ' values for this attribute. '
          + 'Editing it here would drop the rest on the next submit — change it in Seller Central.">'
          + esc(String(val) || "—") + '</span>'
        : (wantsMulti
          ? pdpMvCell(sku, k, val, maxItems)
          : editCell(sku, "attr", k, val, hasEnum ? m.enums[k] : null, false, !hasEnum)));

    const amzVal = Object.prototype.hasOwnProperty.call(live, k) ? String(live[k]) : "";
    const canUse = (v === "differs" || v === "live_only") && !multi;
    // WHICH FIELD AMAZON MEANT -- said SHORT here, in full at the top.
    //
    //     "Show ONCE at the top of the content area. Do NOT duplicate the full
    //      error message next to the field -- the field only gets a red border
    //      + short one-line summary."
    //
    // Right: Amazon's messages run to two hundred characters and printing one
    // under a box turned a form row into a paragraph, twice on the page. The
    // row is tinted and the line says what KIND of problem it is and how many,
    // with the wording itself in the banner where there is room for it.
    const mine = rowIssues[String(k).split(".")[0]] || [];
    const mineErr = mine.filter(x => x.severity === "ERROR").length;
    const said = mine.length
      ? '<div class="pdp-afield' + (mineErr ? " err" : " warn") + '" title="'
        + esc(mine.map(x => x.message || "").join("\n")) + '">'
        + (mineErr
            ? 'Amazon refused this field' + (mineErr > 1 ? ' — ' + mineErr + ' problems' : '')
            : 'Amazon commented on this field')
        + ' · <a onclick="pdpScrollToErrors()">see what it said</a></div>'
      : "";

    // THE HEADING, ONCE PER FAMILY. Drawn from here rather than in a first pass
    // so that a filter which hides every member of a group hides its heading
    // too -- an empty "Battery" heading over nothing would read as a group with
    // no fields rather than as a group filtered out.
    const topKey = String(k).split(".")[0];
    const inGroup = String(k).indexOf(".") >= 0;
    let head = "";
    if(inGroup && openGroup !== topKey){
      openGroup = topKey;
      head = '<div class="pdp-agrouphead">'
           + esc(lbl(topKey)) + pdpHelp(m, topKey) + '</div>';
    }else if(!inGroup){
      openGroup = "";
    }
    // Inside a group the leaf is the label: under "Battery", "capacity.value"
    // reads better than "Battery Capacity Value" repeated five times.
    const shown = inGroup
      ? (m.titles[k] || (typeof _cleanLabel === "function"
          ? _cleanLabel(String(k).slice(topKey.length + 1))
          : String(k).slice(topKey.length + 1)))
      : lbl(k);

    // ONE ROW: a right-aligned label in a 110px column, and the value beside it
    // with what Amazon has in grey above the box.
    //
    //     "Label is right-aligned in a 110px column on the left. Input fills
    //      the rest. ... The grey live value appears above each input showing
    //      what Amazon currently has."
    //
    // THIS REPLACES A FIVE-COLUMN TABLE and loses nothing: the "Amazon" column
    // IS the grey line now, which is where the mockup puts the same fact, and
    // the verdict tick and the "use" button ride on the label and the line
    // rather than in columns of their own. Two of the five columns were empty
    // on most rows, and at 548px of content the value column was 220px wide --
    // an input too narrow to read a title in.
    return head
      + '<div class="pdp-attr' + (inGroup ? " sub" : "")
      +   (mine.some(x => x.severity === "ERROR") ? " apierr"
           : (amazonFlagged ? " flagged" : "")) + '">'
      + '<div class="pdp-attr-label" title="' + esc(k) + '">'
      +   req + esc(shown) + pdpHelp(m, k) + '</div>'
      + '<div class="pdp-attr-value">'
      +   (amzVal
            ? '<div class="pdp-attr-amazon" title="What Amazon holds for this '
              + 'attribute right now">' + icon + ' ' + esc(amzVal)
              + (multi ? ' <span class="pdp-dim">(' + multi + ' values)</span>' : '')
              + (canUse ? ' <button class="pdp-ause" title="Copy Amazon’s value '
                 + 'into this listing. Saves to the app only — nothing is sent '
                 + 'to Amazon until you press Submit." onclick="lvUse(\''
                 + esc(sku) + '\',\'' + esc(k) + '\')">use</button>' : "")
              + '</div>'
            : "")
      +   ctrl + said
      + '</div></div>';
  }).join("");

  const fbtn = (key, label, n) =>
    '<button class="pdp-af' + (PDP_ATTR_FILTER === key ? " active" : "") + '"'
    + ' onclick="pdpAttrFilter(\'' + key + '\')">' + esc(label)
    + (n == null ? "" : ' <b>' + n + '</b>') + '</button>';

  const noLive = !L || L.state !== "ok";
  const summary = '<div class="pdp-asum">'
    + '<span><span class="pdp-ai match">●</span> ' + nMatch + ' match</span>'
    + '<span><span class="pdp-ai differ">●</span> ' + nDiff + ' differ</span>'
    + '<span><span class="pdp-ai onlyamz">●</span> ' + nOnlyAmz + ' only Amazon</span>'
    + '<span><span class="pdp-ai onlyus">●</span> ' + nOnlyUs + ' only ours</span>'
    + (noLive ? '<span class="pdp-dim">' + esc(
        L && L.state === "loading" ? "reading Amazon…"
        : L && L.state === "gone"  ? "not on Amazon — nothing to compare"
        : L && L.state === "error" ? "could not read Amazon: " + (L.error || "")
        : "not compared against Amazon") + '</span>' : "")
    + '</div>';

  const empty = !rows
    ? '<div class="pdp-note">Nothing matches this filter.</div>' : "";

  return summary
    + '<div class="pdp-afrow">' + fbtn("all", "All", keys.length)
    +   fbtn("differs", "Differs", nDiff) + fbtn("amazon", "Only Amazon", nOnlyAmz)
    +   fbtn("empty", "Empty") + '</div>'
    + '<div class="pdp-attrs">' + rows + empty + '</div>'
    + (nOnlyAmz ? '<div class="pdp-more" onclick="lvFillEmpty(\'' + esc(sku) + '\')">'
        + '<i class="ti ti-arrow-down"></i> Fill ' + nOnlyAmz + ' empty field(s) from Amazon</div>' : "")
    + (m.productType ? '<div class="pdp-more amber" onclick="saveDefault(\'' + esc(sku) + '\',\''
        + esc(m.productType) + '\',this)"><i class="ti ti-star"></i> Remember these as defaults for all '
        + esc(m.productType) + ' listings</div>' : "");
}

/* ---- what Amazon is showing shoppers ------------------------------------ */

/* THE GREY LINE ABOVE A BOX IS NOT A COPY OF THE BOX.
 *
 * Amazon holds two different things for a live listing and they are easy to
 * confuse:
 *
 *   attributes   what THIS seller submitted, read back. That is what the box
 *                already contains, and repeating it above would say nothing.
 *   summaries    the CATALOGUE record -- what a shopper actually sees. On an
 *                ASIN with more than one seller Amazon merges contributions and
 *                picks what to display, so a title submitted and a title shown
 *                can be different, and nothing in this app could show that.
 *
 * So the line prefers the catalogue value and falls back to the submitted one,
 * and says which it is. It is drawn only for a listing that IS on Amazon: on a
 * draft there is no live value, and an empty grey line above every box would be
 * furniture that means nothing.
 */
function pdpLiveLine(sku, kind){
  const L = (typeof lvGet === "function") ? lvGet(sku) : null;
  if(!L || L.state !== "ok") return "";
  const S = L.summary || {}, C = L.content || {};
  let text = "", from = "on Amazon now";
  if(kind === "title"){
    text = String(S.itemName || "");
    if(!text){ text = String((C.item_name || [])[0] || ""); from = "your last submission"; }
  }else if(kind === "bullets"){
    text = (C.bullet_point || []).join("  •  ");
    from = "your last submission";
  }else if(kind === "desc"){
    text = String((C.product_description || [])[0] || "");
    from = "your last submission";
  }else if(kind === "search"){
    text = (C.generic_keyword || []).join(" ");
    from = "your last submission";
  }
  if(!String(text).trim()) return "";
  return '<div class="pdp-live" title="' + esc(from) + '">'
       + '<span class="pdp-livetag">' + esc(from) + '</span>'
       + esc(text) + '</div>';
}

/* ---- attributes that hold more than one value --------------------------- */

/* HOW MANY VALUES AMAZON ALLOWS, AND WHERE THAT NUMBER COMES FROM.
 *
 * The product type definition, and nothing else. maxItems is per attribute AND
 * per product type -- a field that takes five values on a shaker bottle takes
 * one on a power tool -- so a list kept here would be wrong for most listings.
 * dashboard._load_schema reads it off Amazon's definition; 0 means the schema
 * says "array" without a ceiling.
 *
 * Returns 1 for anything that takes a single value, which is most of them.
 */
function pdpMaxItems(m, key){
  const mi = (m && m.maxitems) ? m.maxitems[key] : undefined;
  if(mi === undefined || mi === null) return 1;
  const n = Number(mi);
  if(!isFinite(n) || n < 0) return 1;
  return n;                       // 0 = no ceiling
}

/* THE SEPARATOR IS ", " BECAUSE THAT IS WHAT IS ALREADY IN THE DATA.
 *
 * Measured before choosing it: across 6,425 stored attribute values there is
 * not one array -- every multi-value field is a single comma-separated string
 * ("1x Wireless Car Charger, 1x Air Vent Clip, 1x USB Cable"). Splitting on
 * ", " and re-joining with ", " round-trips byte for byte, so opening a
 * listing and closing it again cannot alter a value that was not typed in.
 *
 * This is a VIEW of the stored string, not a new storage shape. Nothing about
 * what is sent to Amazon changes here -- see the note in the report.
 */
const PDP_MV_SEP = ", ";

function pdpMvParts(val){
  const s = String(val == null ? "" : val);
  if(!s.trim()) return [""];
  return s.split(PDP_MV_SEP);
}

/* One box per value, stacked, with Add More / Remove Last underneath. */
function pdpMvCell(sku, key, val, max){
  const parts = pdpMvParts(val);
  const id = "mv_" + sid(sku) + "_" + String(key).replace(/[^A-Za-z0-9]/g, "_");
  const boxes = parts.map(p =>
      // class "ed" is the app's own input, styled once in the shared sheet --
      // a second class here would be a second look for the same control.
      '<input class="ed pdp-mv" value="' + esc(p) + '"'
    + ' onchange="pdpMvSave(\'' + esc(id) + '\',\'' + esc(sku) + '\',\'' + esc(key) + '\')">'
  ).join("");

  // "Add More" disappears at the ceiling; "Remove Last" only exists once there
  // is a second box to remove.
  const canAdd = (max === 0) || (parts.length < max);
  const links = '<div class="pdp-addmore">'
    + (canAdd ? '<a onclick="pdpMvAdd(\'' + esc(id) + '\')">Add More</a>' : "")
    + (canAdd && parts.length > 1 ? '<span>|</span>' : "")
    + (parts.length > 1
        ? '<a class="remove" onclick="pdpMvRemove(\'' + esc(id) + '\',\''
          + esc(sku) + '\',\'' + esc(key) + '\')">Remove Last</a>' : "")
    + (max ? '<span class="pdp-mvcap">' + parts.length + '/' + max + '</span>'
           : '<span class="pdp-mvcap">' + parts.length + '</span>')
    + '</div>';

  // MORE VALUES THAN AMAZON ALLOWS IS NOT A DISPLAY DETAIL.
  //
  // Found by opening a real listing: special_features held seven entries
  // against a schema maxItems of five, from a value written as one long
  // comma-separated line before anything counted them. The count alone ("7/5")
  // states it without saying it means the submit will be refused, and this is
  // the only screen where it can be seen at all.
  const over = (max && parts.length > max)
    ? '<div class="pdp-mvover">Amazon allows ' + max + ' here and this has '
      + parts.length + '. Remove ' + (parts.length - max)
      + ' or the submit will be refused.</div>'
    : "";

  return '<div class="pdp-multi" id="' + esc(id) + '" data-max="' + max + '">'
       + boxes + over + links + '</div>';
}

function _pdpMvBoxes(id){
  const host = document.getElementById(id);
  return host ? Array.prototype.slice.call(host.querySelectorAll("input.pdp-mv")) : [];
}

/* Every box, joined back into the one string the row stores. Blank boxes are
 * dropped: an empty entry in the middle would become ", ," on the way out and
 * Amazon would be sent an empty value it never asked for. */
function pdpMvSave(id, sku, key){
  const vals = _pdpMvBoxes(id).map(b => String(b.value || "").trim()).filter(Boolean);
  const joined = vals.join(PDP_MV_SEP);
  if(typeof editField !== "function") return;
  editField(sku, "attr", key, joined).then(function(res){
    if(res && res.ok){
      if(typeof toast === "function") toast("Saved");
    }else if(typeof toast === "function"){
      toast("Could not save: " + ((res && res.error) || "unknown"));
    }
  });
}

/* Add an empty box. Nothing is saved until something is typed into it and the
 * box is left -- an empty entry has nothing to record. */
function pdpMvAdd(id){
  const host = document.getElementById(id);
  if(!host) return;
  const max = Number(host.getAttribute("data-max") || 0);
  const boxes = _pdpMvBoxes(id);
  if(max && boxes.length >= max) return;
  const last = boxes[boxes.length - 1];
  if(!last) return;
  const el = last.cloneNode(true);
  el.value = "";
  last.parentNode.insertBefore(el, last.nextSibling);
  el.focus();
  _pdpMvCount(host);
}

function pdpMvRemove(id, sku, key){
  const boxes = _pdpMvBoxes(id);
  if(boxes.length < 2) return;
  const gone = boxes[boxes.length - 1];
  const had  = String(gone.value || "").trim();
  gone.parentNode.removeChild(gone);
  const host = document.getElementById(id);
  if(host) _pdpMvCount(host);
  // Only write when the box being dropped actually held something. Removing an
  // empty box changes nothing, and a save would be a write with no edit behind
  // it -- which shows up in the row's history as a change that never happened.
  if(had) pdpMvSave(id, sku, key);
}

/* Keep the "3/5" and the two links honest after an add or a remove, without
 * re-rendering the whole page and losing what is in the other boxes. */
function _pdpMvCount(host){
  const n = host.querySelectorAll("input.pdp-mv").length;
  const max = Number(host.getAttribute("data-max") || 0);
  const cap = host.querySelector(".pdp-mvcap");
  if(cap){
    cap.textContent = max ? (n + "/" + max) : String(n);
    cap.classList.toggle("over", !!(max && n > max));
  }
  const over = host.querySelector(".pdp-mvover");
  if(over){
    if(max && n > max){
      over.style.display = "";
      over.textContent = "Amazon allows " + max + " here and this has " + n
        + ". Remove " + (n - max) + " or the submit will be refused.";
    }else{
      over.style.display = "none";
    }
  }
  const add = host.querySelector(".pdp-addmore a:not(.remove)");
  if(add) add.style.display = (max && n >= max) ? "none" : "";
  const rem = host.querySelector(".pdp-addmore a.remove");
  if(rem) rem.style.display = (n > 1) ? "" : "none";
  const bar = host.querySelector(".pdp-addmore span:not(.pdp-mvcap)");
  if(bar) bar.style.display = (n > 1 && !(max && n >= max)) ? "" : "none";
}

/* ---- textareas that grow to fit ----------------------------------------- */

/* THE FALLBACK FOR field-sizing:content.
 *
 * Chrome 123+ sizes a textarea to its own text with one CSS line; everything
 * else still needs to be told. This measures scrollHeight and sets the height
 * to match, which is the same result by the older route.
 *
 * Bound ONCE, by delegation, on the page host -- a listener per textarea would
 * be re-attached on every pdpRender and every one of those renders replaces the
 * whole innerHTML, so the old listeners would pile up on detached nodes.
 *
 * Capped at the same 60vh the stylesheet uses. Past that it scrolls, because a
 * 2,000-character description that grew without limit would push the panel's
 * own controls off the bottom of the screen.
 */
let PDP_GROW_BOUND = false;

function pdpGrow(ta){
  if(!ta || ta.tagName !== "TEXTAREA") return;
  // Native support already did it -- measuring would fight the browser.
  if(window.CSS && CSS.supports && CSS.supports("field-sizing", "content")) return;
  const cap = Math.round(window.innerHeight * 0.6);
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight + 2, cap) + "px";
}

function pdpAutoGrow(){
  const host = document.getElementById("pdp");
  if(!host) return;
  if(!PDP_GROW_BOUND){
    host.addEventListener("input", function(ev){
      if(ev.target && ev.target.tagName === "TEXTAREA") pdpGrow(ev.target);
    });
    // A COLLAPSED BOX MEASURES ZERO. The bullet cards open on click, and a
    // textarea inside a hidden panel has no scrollHeight to read, so the first
    // measurement has to happen after it is shown.
    host.addEventListener("click", function(){
      setTimeout(function(){ host.querySelectorAll("textarea").forEach(pdpGrow); }, 0);
    });
    PDP_GROW_BOUND = true;
  }
  host.querySelectorAll("textarea").forEach(pdpGrow);
}

/* ---- what Amazon said back ---------------------------------------------- */

/* THE REPLY, NOT OUR SUMMARY OF IT.
 *
 * Every Preview and every Submit gets an `issues` array back from Amazon. Until
 * now only the sentences survived, joined into the Notes column -- so a rejected
 * listing could say WHAT Amazon objected to but never WHICH FIELD, and on this
 * page it said nothing at all. dashboard._card now serves the array whole
 * (listing/api_issues.py owns the shape); this draws it.
 *
 * Errors first and always; warnings folded, because "accepted with warnings" is
 * a success and a wall of amber on a listing that went live is noise.
 */
function pdpApiIssues(r){
  const rec = (r && r.api_issues) || null;
  const all = (rec && rec.issues) || [];
  if(!all.length) return "";

  const errs  = all.filter(i => i.severity === "ERROR");
  const warns = all.filter(i => i.severity !== "ERROR");
  const sub   = String(rec.mode || "") === "submit";
  const when  = rec.at ? ' <span class="pdp-dim">· ' + esc(rec.at) + '</span>' : "";

  // A FIELD NAME IS A DESTINATION, not decoration. attributeNames is the whole
  // reason for keeping the structure, so each one is a button that opens the
  // Attributes tab and scrolls to that row.
  const chips = i => (i.fields || []).map(f =>
      '<button class="pdp-errfield" title="Go to this field"'
      + ' onclick="pdpGoToField(\'' + esc(f) + '\')">' + esc(f) + '</button>').join("");

  const line = (i, cls) =>
    '<div class="pdp-error ' + cls + '">'
    + '<i class="ti ti-' + (cls === "warn" ? "alert-triangle" : "alert-circle") + '"></i>'
    + '<div><div>' + esc(i.message || "Amazon reported a problem with this listing.") + '</div>'
    + (i.fields && i.fields.length ? '<div class="pdp-errfields">' + chips(i) + '</div>' : "")
    + (i.code ? '<div class="pdp-error-code">Amazon code ' + esc(i.code) + '</div>' : "")
    + '</div></div>';

  let out = "";
  if(errs.length){
    out += '<div class="pdp-errhead"><b>'
        +  (sub ? "Amazon refused this listing" : "Amazon would refuse this listing")
        +  '</b> — ' + errs.length + (errs.length === 1 ? " problem" : " problems")
        +  when + '</div>'
        +  errs.map(i => line(i, "err")).join("");
  }
  if(warns.length){
    out += '<details class="pdp-errwarns"' + (errs.length ? "" : " open") + '>'
        +  '<summary>' + warns.length
        +  (warns.length === 1 ? " warning" : " warnings")
        +  (errs.length ? "" : ' — Amazon accepted this, with notes' + when)
        +  '</summary>'
        +  warns.map(i => line(i, "warn")).join("")
        +  '</details>';
  }
  return '<div class="pdp-errors">' + out + '</div>';
}

/* Back up to the banner, from a field that says Amazon complained about it.
 * The other half of "show it once": the short line under the box has to be able
 * to reach the full wording rather than leaving the reader to find it. */
function pdpScrollToErrors(){
  const el = document.querySelector("#pdp .pdp-errors");
  if(el) el.scrollIntoView({block: "start", behavior: "smooth"});
}

/* Put the named field in view, highlighted.
 *
 * The attributes are a SECTION of Product Details now, not a tab, so this
 * switches to details rather than to a tab that no longer exists. The scroll
 * waits a frame because the section does not exist until the re-render has run.
 */
function pdpGoToField(key){
  const base = String(key || "").split(".")[0];
  if(PDP_TAB !== "details"){ PDP_TAB = "details"; pdpRender(); }
  setTimeout(function(){
    const rows = document.querySelectorAll("#pdp .pdp-attr-label");
    for(let i = 0; i < rows.length; i++){
      const t = String(rows[i].getAttribute("title") || "");
      if(t === key || t.split(".")[0] === base){
        const row = rows[i].closest(".pdp-attr");
        if(row){
          row.scrollIntoView({block: "center", behavior: "smooth"});
          row.classList.add("pdp-hit");
          setTimeout(function(){ row.classList.remove("pdp-hit"); }, 2200);
          const box = row.querySelector("input, textarea, select, [contenteditable]");
          if(box) try{ box.focus(); }catch(e){}
        }
        return;
      }
    }
    if(typeof toast === "function")
      toast("Amazon named “" + base + "”, but this listing has no such field yet.");
  }, 60);
}

/* WHOSE DATA THIS IS, when it is not ours.
 *
 * A listing synced from Amazon opens here now like any other, and every field
 * on the page is Amazon's own value. That is the point -- but it changes what
 * an edit means, and saying nothing would let somebody type into a box that has
 * nowhere to save to.
 *
 * The app's edits go through /edit, which finds a listing by SKU and correctly
 * refuses when there is no row. So the boxes read but do not write until Sync
 * pulls the listing in as a real draft -- and this says so, once, with the
 * button that does it.
 */
function pdpCatalogueNote(r){
  if(!pdpIsCatalogueOnly(r)) return "";
  const L = (typeof lvGet === "function") ? lvGet(r.sku) : null;
  const state = (L && L.state) || "";

  // A FAILED READ IS NOT AN EMPTY LISTING, and on this page the difference is
  // everything: without it, a listing Amazon refused to describe looks like one
  // with no title, no bullets and no attributes. The same distinction
  // drawer_attributes draws, said here because this page has nothing else on it
  // to explain the blanks.
  if(state === "error"){
    return '<div class="pdp-catnote bad">'
      + '<i class="ti ti-alert-triangle"></i>'
      + '<div><b>Amazon would not describe this listing.</b> '
      + 'It is on your account and this app holds no draft of it, so everything '
      + 'below the title had to come from Amazon — and that read failed'
      + (L.error ? ': ' + esc(String(L.error).slice(0, 140)) : '')
      + '. The empty fields mean <b>nobody could look</b>, not that the listing '
      + 'has none. Press "Diagnose SP-API" on the listings page if this keeps '
      + 'happening.'
      + '</div>'
      + '<button class="pdp-tb" onclick="lvRefresh(\'' + esc(r.sku) + '\')">'
      + '<i class="ti ti-refresh"></i> Try again</button>'
      + '</div>';
  }
  if(state === "gone"){
    return '<div class="pdp-catnote bad">'
      + '<i class="ti ti-alert-triangle"></i>'
      + '<div><b>Amazon no longer has this listing.</b> '
      + 'It was in the catalogue this app last read, and asking about it now '
      + 'returns nothing. It may have been deleted or closed.</div></div>';
  }

  return '<div class="pdp-catnote">'
    + '<i class="ti ti-cloud-download"></i>'
    + '<div><b>This is Amazon\'s copy of the listing, read live.</b> '
    + 'It is on your account but this app holds no draft of it, so every field '
    + 'below is Amazon\'s own value'
    + (state === "loading" ? ' — still reading the rest' : '')
    + '. Editing needs a draft to save into: press Sync to pull this listing in, '
    + 'and it then behaves like any other.'
    + '</div>'
    + '<button class="pdp-tb" onclick="pdpSyncThis(\'' + esc(r.sku) + '\')">'
    + '<i class="ti ti-refresh"></i> Sync this listing</button>'
    + '</div>';
}

/* Pull ONE listing in from Amazon, so it becomes a draft that can be edited.
 * Uses /live/pull_row, which is the app's existing single-listing pull -- it
 * merges Amazon's real images and product type into a row (Rule 12). */
function pdpSyncThis(sku){
  if(typeof toast === "function") toast("Pulling " + sku + " in from Amazon…");
  const body = (typeof acctBody === "function")
    ? acctBody({sku: sku}) : {sku: sku};
  fetch("/live/pull_row", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)})
    .then(r => r.json())
    .then(function(j){
      if(!j || !j.ok){
        if(typeof toast === "function")
          toast("Could not pull it in: " + ((j && j.error) || "unknown"));
        return;
      }
      if(typeof toast === "function") toast("Pulled in. Reloading the listing…");
      if(typeof loadRows === "function"){
        Promise.resolve(loadRows()).then(function(){ pdpRender(); });
      }else{
        pdpRender();
      }
    })
    .catch(e => { if(typeof toast === "function") toast(String(e)); });
}

/* ---- the footer --------------------------------------------------------- */

/* Cancel | Save and finish, stuck to the bottom of the panel.
 *
 * WHAT THESE TWO BUTTONS HONESTLY DO, which is not quite what the brief's
 * wording suggests:
 *
 *   "Cancel — discards all unsaved changes"
 *   "Save and finish — saves all attribute changes via putListingsItem"
 *
 * Neither is possible as written, and pretending otherwise would be worse than
 * not having the buttons. Every box on this page saves the moment you leave it
 * (saveEdit -> /edit), so by the time a Cancel is pressed there is nothing left
 * unsaved to discard -- a button that claimed to undo would silently do
 * nothing. And "save via putListingsItem" is SUBMIT: it publishes to Amazon.
 * Putting that behind a button called "Save and finish" would send a listing
 * live from a control that reads like closing a dialog.
 *
 * So: Cancel closes, and says in its tooltip that edits are already saved.
 * Save and finish commits whatever box still has focus, then closes -- the one
 * thing that genuinely can be lost is a value typed and never blurred. Sending
 * to Amazon stays on the Submit button at the top, where it is labelled.
 */
/* AND IT IS NOT THERE UNTIL YOU HAVE CHANGED SOMETHING.
 *
 *     "The 'Cancel / Save and finish' bar is always visible. It should only
 *      appear AFTER the user has modified any field. Same pattern as the Save
 *      All bar on the listings page ... When no changes have been made: no bar
 *      visible."
 *
 * A bar that is always there is furniture; one that appears when you have
 * touched something is a statement about this listing. It also buys back 53px
 * of the panel for the listing itself, which at a capped height is 53px of
 * fields.
 *
 * NOT RENDERED CONDITIONALLY -- always drawn, and hidden. pdpRender replaces the
 * whole panel, so a bar that only existed once dirty could not slide in; and a
 * height that appears mid-edit would push the field you are typing in upwards.
 * It is in the layout from the start and reveals itself.
 */
function pdpFooter(r){
  const ro = !!window.WS_READONLY;
  return '<div class="pdp-footer' + (PDP_DIRTY ? " on" : "") + '">'
    + '<span class="pdp-footer-note">'
    +   (ro ? 'Read-only workspace — nothing here can be changed.'
          : 'Edits save as you leave each box. Nothing reaches Amazon until Submit.')
    + '</span>'
    + '<button class="pdp-footer-cancel" onclick="pdpClose()"'
    +   ' title="Close this page and go back to the list. Your edits are already saved.">'
    +   'Cancel</button>'
    + '<button class="pdp-footer-save" onclick="pdpSaveAndFinish()"'
    +   ' title="Save whatever box you are still in, then close. Use Submit at the top to send the listing to Amazon.">'
    +   'Save and finish</button>'
    + '</div>';
}

/* Has anything on this listing been touched since it was opened?
 *
 * Reset when the page opens on a DIFFERENT listing, and when it closes -- the
 * bar is about the listing in front of you, not about the session. */
let PDP_DIRTY = false;
let PDP_DIRTY_BOUND = false;

/* One delegated listener, bound once, on the panel host.
 *
 * `input` rather than `change`, so the bar appears as you type rather than when
 * you leave the box -- "When any field is modified: bar appears at the bottom."
 * Bound by delegation because pdpRender replaces every control on the page and
 * a listener per box would be re-attached on every render and pile up on
 * detached nodes.
 *
 * ONLY THE EDITING SURFACE COUNTS. The panel also holds an attribute filter, a
 * tab strip and the rail's own buttons, and none of those is a change to the
 * listing -- a bar that appeared because somebody clicked "Differs" would be
 * saying something untrue about their work.
 */
function pdpWatchEdits(){
  const host = document.getElementById("pdp");
  if(!host || PDP_DIRTY_BOUND) return;
  const touched = function(ev){
    const t = ev.target;
    if(!t || !t.closest) return;
    if(!t.closest(".pdp-content")) return;          // not the rail, top bar or tabs
    if(t.closest(".pdp-afrow")) return;             // the attribute filter buttons
    if(t.closest(".pdp-footer")) return;
    const tag = t.tagName;
    if(tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT"
       && !t.isContentEditable) return;
    pdpMarkDirty();
  };
  host.addEventListener("input", touched);
  // A <select> fires change, not input, in some browsers; a contenteditable
  // fires neither reliably until blur. Both are covered.
  host.addEventListener("change", touched);
  PDP_DIRTY_BOUND = true;
}

/* Show the bar. Toggles a class rather than re-rendering: a render mid-keystroke
 * would replace the box under the cursor and lose the caret. */
function pdpMarkDirty(){
  if(PDP_DIRTY) return;
  PDP_DIRTY = true;
  const f = document.querySelector("#pdp .pdp-footer");
  if(f) f.classList.add("on");
}

/* Commit the field still under the cursor, then close.
 *
 * blur() is what triggers the onchange the boxes save on, so this is the same
 * save the user would get by clicking anywhere else -- not a second, parallel
 * save path (Rule 12). The close waits a beat so that request is on the wire
 * before the page it came from is torn down.
 */
function pdpSaveAndFinish(){
  try{
    const a = document.activeElement;
    if(a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.tagName === "SELECT")) a.blur();
  }catch(e){}
  setTimeout(pdpClose, 120);
}

/* ---- render ------------------------------------------------------------ */

function pdpRender(){
  const host = document.getElementById("pdp");
  const r = pdpRow();
  if(!host) return;
  if(!r){ pdpClose(); return; }

  const sku = String(r.sku);
  const ro  = !!window.WS_READONLY;
  // NEVER LET A RENDER ERROR COLLAPSE THE PAGE INTO NOTHING. fullData() has
  // guarded the drawer this way since a thrown builder turned it into empty
  // boxes with no clue why; this page is built from the same builders, so it
  // can fail the same way. Say what broke and keep the raw row readable.
  let tp, p;
  try{
    tp = dwTitleParts(r, "pdptitlec_" + sid(sku));
    p  = _fullDataParts(r);
  }catch(err){
    host.innerHTML = '<div class="pdp"><div class="pdp-top">'
      + '<a class="pdp-back" onclick="pdpClose()"><i class="ti ti-arrow-left"></i> Back to listings</a>'
      + '</div><div class="pdp-body"><div class="pdp-err">'
      + '<b>This listing’s page hit an error while rendering.</b>'
      + '<div class="pdp-errmsg">' + esc(String((err && err.message) || err)) + '</div>'
      + '<div class="pdp-dim">The drawer may still open it — and the raw data is below either way.</div>'
      + '<pre class="raw">' + esc(JSON.stringify(r, null, 2)) + '</pre>'
      + '</div></div></div>';
    return;
  }

  // [← Back] [Preview] [Auto-fix] [Submit] ................ [...]
  //
  // The three actions sit NEXT TO the back link rather than across the bar. The
  // spacer moved from in front of them to behind, so the only thing pushed to
  // the far right is the overflow menu. They stay in the banner either way --
  // moving them under the title was asked for and then asked against.
  const top = '<div class="pdp-top">'
    + '<a class="pdp-back" onclick="pdpClose()"><i class="ti ti-arrow-left"></i> Back to listings</a>'
    // THE SAME THREE ACTIONS THE DRAWER'S FOOTER RUNS, calling the same
    // functions. Nothing here is reimplemented.
    + '<button class="pdp-tb" onclick="previewOne(\'' + esc(sku) + '\')" title="Check this listing against Amazon. Nothing is sent."><i class="ti ti-eye"></i> Preview</button>'
    + '<button class="pdp-tb accent" onclick="autoFixLoop(\'' + esc(sku) + '\')" title="Suggest, apply, preview — repeatedly, until there are no errors left or it stops making progress (max 8 rounds)."><i class="ti ti-wand"></i> Auto-fix</button>'
    + (ro
      ? '<span class="pdp-rolock"><i class="ti ti-lock"></i> Read-only workspace</span>'
      : '<button class="pdp-tb success" onclick="submitOne(\'' + esc(sku) + '\')" title="Publish ONLY this listing live"><i class="ti ti-upload"></i> Submit</button>')
    + '<span class="pdp-spacer"></span>'
    + '<button class="pdp-tb" onclick="drawerMore(event,\'' + esc(sku) + '\',' + (r.row||0) + ','
      + ((typeof isAmazonLive === "function" && isAmazonLive(r)) ? 'true' : 'false')
      + ')" title="Everything else"><i class="ti ti-dots"></i></button>'
    + '</div>';

  // A BLOCKING PROBLEM IS NEVER PUT BEHIND A TAB. A barcode already on another
  // listing, or a prohibited product, is drawn above everything -- CLAUDE.md
  // Rule 1 requires a clash to be REPORTED, and a report you have to go
  // looking for has not been made. Same two panels the drawer never folds.
  const blocking = ((typeof identifierPanel === "function") ? identifierPanel(r) : "")
                 + ((typeof complianceBanner === "function") ? complianceBanner(r) : "")
                 // Amazon's own reply to the last Preview/Submit. Above the tabs
                 // for the same reason as the two panels above it: a rejection
                 // you have to go looking for has not been reported.
                 + pdpApiIssues(r)
                 // AND WHERE THIS PAGE'S CONTENTS CAME FROM, when they are not
                 // ours. Above everything, because it changes what every field
                 // below it means.
                 + pdpCatalogueNote(r);

  let tab = "";
  if(PDP_TAB === "details"){
    // The grey line above each box is what Amazon has, not a second copy of
    // what is in the box -- see pdpLiveLine. Empty for a listing that has never
    // been on Amazon, which is most of them.
    tab = '<div class="pdp-field">'
        +   '<div class="pdp-flabel">Item name'
        +     '<span class="pdp-fmeta">' + tp.count + tp.indexTag + '</span></div>'
        +   pdpLiveLine(sku, "title")
        +   tp.editor + tp.warnNote
        + '</div>'
        + p.highlights
        + pdpLiveLine(sku, "bullets") + p.bullets
        + pdpLiveLine(sku, "desc")    + p.desc
        + pdpLiveLine(sku, "search")  + p.search
        // AND THE ATTRIBUTES, HERE, WHERE SELLER CENTRAL PUTS THEM.
        //
        //     "There is NO 'Attributes' tab. All attributes ... are displayed
        //      on the Product Details tab, below the title/highlights/bullets/
        //      description fields."
        //
        // The tab is gone; this is the same builder it used, so nothing about
        // which fields appear, which are required or what their allowed values
        // are has changed -- only where they are read.
        + pdpAttrSection(p.attrModel, p.addCtrl);
  } else if(PDP_TAB === "images"){
    // The four-section slot editor, which lives in its own file (Rule 7). The
    // old strip of source thumbnails is kept underneath it: it carries the AI
    // generation panel and the per-image edit buttons, which are a different
    // job from deciding what goes in which slot.
    tab = ((typeof pdpImagesTab === "function") ? pdpImagesTab(r) : "") + p.images;
  } else if(PDP_TAB === "variations"){
    // The family this listing belongs to. Drawn by the variations screen's own
    // builder where there is one, so the parent/child rules live in one place.
    tab = (typeof pdpVariationsTab === "function")
      ? pdpVariationsTab(r)
      : '<div class="pdp-note">This listing is part of a variation family. '
        + 'Open Variations from the sidebar to work on the family.</div>';
  } else if(PDP_TAB === "offer"){
    tab = p.offerOnly + p.identityOnly;
  } else {
    tab = ((typeof _dwWarnings === "function") ? _dwWarnings(r) : "")
        + p.compliance + p.tools;
  }

  host.innerHTML = '<div class="pdp">' + top + pdpHero(r) + pdpTabBar(r)
    + '<div class="pdp-layout">'
    +   pdpSidebar(r)
    +   '<div class="pdp-content">' + blocking + tab + '</div>'
    + '</div>' + pdpFooter(r) + '</div>';

  // The bullets' shared byte budget is measured from the DOM once the cards
  // exist -- the same call openDrawer makes, for the same reason.
  setTimeout(function(){
    if(typeof bulletMeter === "function") bulletMeter();
    pdpAutoGrow();
    // Bound once, here rather than in pdpOpen, because the host's contents are
    // what the listener delegates over and they do not exist until a render.
    pdpWatchEdits();
  }, 40);
}

/* Redraw after a structural edit (a field deleted, an optional one added, a
 * live value copied in). Mirrors _rebuildDrawerData; called from it, so there
 * is one place that decides a listing view is stale. */
function pdpRebuild(sku){
  if(PDP_SKU && String(PDP_SKU) === String(sku)) pdpRender();
}

/* ---- the address ------------------------------------------------------- */

/* /w/<workspace>/listing/<sku>. Built here rather than in shell.js because the
 * workspace half is altaPathFor's business and the sku half is this page's.
 * Returns "" when there is no address to give. */
function pdpPath(){
  if(!PDP_SKU) return "";
  if(typeof ACTIVE_WS === "undefined" || !ACTIVE_WS || ACTIVE_WS.brand === "new") return "";
  const slug = String(ACTIVE_WS.key || "") || "default";
  return "/w/" + encodeURIComponent(slug) + "/listing/" + encodeURIComponent(PDP_SKU);
}

/* Reopen from an address. Called by the router once the workspace is open and
 * the rows have loaded; returns false when the SKU is not on this screen, so
 * the router can say so instead of showing an empty page. */
function pdpOpenFromUrl(sku){
  sku = String(sku || "");
  if(!sku) return false;
  const r = (typeof ROWS !== "undefined") ? ROWS.find(x => String(x.sku) === sku) : null;
  if(!r) return false;
  pdpOpen(sku);
  return true;
}
