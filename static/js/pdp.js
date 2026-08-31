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

function pdpRow(){
  if(!PDP_SKU || typeof ROWS === "undefined") return null;
  return ROWS.find(x => String(x.sku) === String(PDP_SKU)) || null;
}
function pdpIsOpen(){ return !!PDP_SKU; }

/* ---- open / close ------------------------------------------------------ */

function pdpOpen(sku){
  sku = String(sku || "");
  const r = (typeof ROWS !== "undefined") ? ROWS.find(x => String(x.sku) === sku) : null;
  if(!r){ if(typeof toast === "function") toast("That listing is not on this screen."); return; }
  if(!PDP_SKU){                                  // entering from the grid, not
    try{ PDP_BACK_SCROLL = window.scrollY || 0; }catch(e){ PDP_BACK_SCROLL = 0; }
  }                                              // moving between listings
  const changed = PDP_SKU !== sku;
  PDP_SKU = sku;
  if(changed) PDP_TAB = "details";               // a new listing starts at the front
  // The drawer and this page are two views of one listing; having both open
  // means two title boxes saving to the same cell.
  if(typeof closeDrawer === "function"){ try{ closeDrawer(); }catch(e){} }

  const host = document.getElementById("pdp");
  if(host) host.style.display = "block";
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
  if(r.product_type && typeof loadSchemas === "function"
     && !(SCHEMAS[r.product_type] && (SCHEMAS[r.product_type].attrs||[]).length)){
    loadSchemas([r.product_type], false, (typeof rowMkt==="function")?rowMkt(r):"")
      .then(() => { if(PDP_SKU === sku) pdpRender(); }).catch(() => {});
  }
  // What Amazon currently holds, for the comparison column.
  if(typeof lvEnsure === "function") lvEnsure(r);

  if(typeof altaSyncUrl === "function") altaSyncUrl();
}

/* Back to the grid, which is still underneath exactly as it was. */
function pdpClose(){
  if(!PDP_SKU) return;
  PDP_SKU = "";
  const host = document.getElementById("pdp");
  if(host){
    host.classList.remove("in");
    host.style.display = "none";
    host.innerHTML = "";
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
  const w = (typeof lsWarnings === "function") ? lsWarnings(r) : {n:0, high:0};
  const cur = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  const profit = String(r.profit == null ? "" : r.profit).replace(/^[A-Z]{3}/, "");

  return '<div class="pdp-hero"><div class="pdp-hero-in">'
    + '<div class="pdp-heroimg">'
    +   (urls && urls.length
        ? '<img src="' + esc(urls[0]) + '" loading="lazy" onerror="this.remove()">'
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
    +     (w.n ? '<span class="pdp-hb warn" onclick="pdpTab(\'compliance\')" '
              + 'title="Open the Compliance tab"><i class="ti ti-alert-triangle"></i> '
              + w.n + ' warning' + (w.n === 1 ? '' : 's') + '</span>' : "")
    +   '</div>'
    + '</div></div></div>';
}

const PDP_TABS = [
  {key:"details",    label:"Product details"},
  {key:"images",     label:"Images"},
  {key:"attributes", label:"Attributes"},
  {key:"offer",      label:"Offer"},
  {key:"compliance", label:"Compliance"},
];

function pdpTab(name){
  PDP_TAB = String(name || "details");
  pdpRender();
  try{ window.scrollTo(0, 0); }catch(e){}
}

function pdpTabBar(){
  return '<div class="pdp-tabs">' + PDP_TABS.map(function(t){
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
  const restricted = r.restricted && r.restricted.matched;
  const viability  = r.viability && r.viability.matched;
  const claims     = (r.claim_flags || []).length;
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
    +   chk(restricted ? "warn" : "ok", restricted ? "ti-alert-triangle" : "ti-shield-check",
            restricted ? "Restricted — see why" : "Restricted", "compliance")
    +   chk(viability ? "warn" : "ok", viability ? "ti-alert-triangle" : "ti-file-check",
            viability ? "Docs may be demanded" : "Compliance", "compliance")
    +   chk(claims ? "warn" : "ok", claims ? "ti-alert-triangle" : "ti-circle-check",
            claims ? (claims + " claim risk" + (claims === 1 ? "" : "s")) : "Claim risks", "compliance")
    +   chk("info", "ti-message-dots", "Amazon feedback", "compliance")
    + '</div></div>';
}

/* ---- the attributes table ----------------------------------------------
 * A PRESENTER of _fullDataParts' attrModel. It re-decides nothing: which keys
 * exist, which Amazon requires, which its Preview flagged and what the allowed
 * values are all arrive already worked out, and the editable cell is the same
 * editCell() the drawer's grid uses, saving through the same saveEdit(). */

function pdpAttrFilter(f){ PDP_ATTR_FILTER = String(f || "all"); pdpRender(); }

function pdpAttrTable(m){
  if(!m) return '<div class="pdp-note">No attributes yet.</div>';
  const sku = m.sku;
  const L = (typeof lvGet === "function") ? lvGet(sku) : null;
  const live = (L && L.state === "ok") ? (L.values || {}) : {};
  const lbl = k => m.titles[k] || (typeof _cleanLabel === "function" ? _cleanLabel(String(k)) : String(k));
  // The same order the grid uses: what the listing has, then what Amazon is
  // still asking for.
  const keys = [...m.aKeys, ...m.missing.filter(k => m.aKeys.indexOf(k) < 0)];

  let nMatch = 0, nDiff = 0, nOnlyAmz = 0, nOnlyUs = 0;
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
    const req = amazonFlagged
      ? '<span class="pdp-req" title="Amazon flagged this in Preview — it must be filled">★</span>'
      : (schemaReq ? '<span class="pdp-reqsoft" title="The schema lists this as required. Amazon’s last Preview did not flag it.">☆</span>' : "");

    const multi = (L && L.multi) ? (L.multi[String(k).split(".")[0]] || 0) : 0;
    const hasEnum = !!(m.enums[k] && m.enums[k].length);
    const ctrl = multi
      ? '<span class="pdp-ro" title="Amazon holds ' + multi + ' values for this attribute. '
        + 'Editing it here would drop the rest on the next submit — change it in Seller Central.">'
        + esc(String(val) || "—") + '</span>'
      : editCell(sku, "attr", k, val, hasEnum ? m.enums[k] : null, false, !hasEnum);

    const amzVal = Object.prototype.hasOwnProperty.call(live, k) ? String(live[k]) : "";
    const canUse = (v === "differs" || v === "live_only") && !multi;
    return '<tr' + (amazonFlagged ? ' class="flagged"' : '') + '>'
      + '<td class="pdp-c1">' + icon + '</td>'
      + '<td class="pdp-aname" title="' + esc(k) + '">' + esc(lbl(k)) + req + '</td>'
      + '<td class="pdp-aval">' + ctrl + '</td>'
      + '<td class="pdp-aamz" title="' + esc(amzVal) + '">'
      +   (amzVal ? esc(amzVal) : '<span class="pdp-dim">—</span>')
      +   (multi ? ' <span class="pdp-dim">(' + multi + ')</span>' : '')
      + '</td>'
      + '<td class="pdp-c5">'
      +   (canUse ? '<button class="pdp-ause" title="Copy Amazon’s value into this listing. Saves to the app only — nothing is sent to Amazon until you press Submit." onclick="lvUse(\'' + esc(sku) + '\',\'' + esc(k) + '\')">use</button>' : "")
      + '</td></tr>';
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
    ? '<tr><td colspan="5" class="pdp-note">Nothing matches this filter.</td></tr>' : "";

  return summary
    + '<div class="pdp-afrow">' + fbtn("all", "All", keys.length)
    +   fbtn("differs", "Differs", nDiff) + fbtn("amazon", "Only Amazon", nOnlyAmz)
    +   fbtn("empty", "Empty") + '</div>'
    + '<div class="pdp-atwrap"><table class="pdp-at">'
    +   '<thead><tr><th class="pdp-c1"></th><th>Field</th><th>Yours</th>'
    +   '<th>Amazon</th><th class="pdp-c5"></th></tr></thead>'
    +   '<tbody>' + rows + empty + '</tbody></table></div>'
    + (nOnlyAmz ? '<div class="pdp-more" onclick="lvFillEmpty(\'' + esc(sku) + '\')">'
        + '<i class="ti ti-arrow-down"></i> Fill ' + nOnlyAmz + ' empty field(s) from Amazon</div>' : "")
    + (m.productType ? '<div class="pdp-more amber" onclick="saveDefault(\'' + esc(sku) + '\',\''
        + esc(m.productType) + '\',this)"><i class="ti ti-star"></i> Remember these as defaults for all '
        + esc(m.productType) + ' listings</div>' : "");
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

  const top = '<div class="pdp-top">'
    + '<a class="pdp-back" onclick="pdpClose()"><i class="ti ti-arrow-left"></i> Back to listings</a>'
    + '<span class="pdp-spacer"></span>'
    // THE SAME THREE ACTIONS THE DRAWER'S FOOTER RUNS, calling the same
    // functions. Nothing here is reimplemented.
    + '<button class="pdp-tb" onclick="previewOne(\'' + esc(sku) + '\')" title="Check this listing against Amazon. Nothing is sent."><i class="ti ti-eye"></i> Preview</button>'
    + '<button class="pdp-tb accent" onclick="autoFixLoop(\'' + esc(sku) + '\')" title="Suggest, apply, preview — repeatedly, until there are no errors left or it stops making progress (max 8 rounds)."><i class="ti ti-wand"></i> Auto-fix</button>'
    + (ro
      ? '<span class="pdp-rolock"><i class="ti ti-lock"></i> Read-only workspace</span>'
      : '<button class="pdp-tb success" onclick="submitOne(\'' + esc(sku) + '\')" title="Publish ONLY this listing live"><i class="ti ti-upload"></i> Submit</button>')
    + '<button class="pdp-tb" onclick="drawerMore(event,\'' + esc(sku) + '\',' + (r.row||0) + ','
      + ((typeof isAmazonLive === "function" && isAmazonLive(r)) ? 'true' : 'false')
      + ')" title="Everything else"><i class="ti ti-dots"></i></button>'
    + '</div>';

  // A BLOCKING PROBLEM IS NEVER PUT BEHIND A TAB. A barcode already on another
  // listing, or a prohibited product, is drawn above everything -- CLAUDE.md
  // Rule 1 requires a clash to be REPORTED, and a report you have to go
  // looking for has not been made. Same two panels the drawer never folds.
  const blocking = ((typeof identifierPanel === "function") ? identifierPanel(r) : "")
                 + ((typeof complianceBanner === "function") ? complianceBanner(r) : "");

  let tab = "";
  if(PDP_TAB === "details"){
    tab = '<div class="pdp-field">'
        +   '<div class="pdp-flabel">Item name'
        +     '<span class="pdp-fmeta">' + tp.count + tp.indexTag + '</span></div>'
        +   tp.editor + tp.warnNote
        + '</div>'
        + p.highlights + p.bullets + p.desc + p.search;
  } else if(PDP_TAB === "images"){
    tab = p.images;
  } else if(PDP_TAB === "attributes"){
    tab = pdpAttrTable(p.attrModel) + (p.addCtrl || "");
  } else if(PDP_TAB === "offer"){
    tab = p.offerOnly + p.identityOnly;
  } else {
    tab = ((typeof _dwWarnings === "function") ? _dwWarnings(r) : "")
        + p.compliance + p.tools;
  }

  host.innerHTML = '<div class="pdp">' + top + pdpHero(r) + pdpTabBar()
    + '<div class="pdp-layout">'
    +   pdpSidebar(r)
    +   '<div class="pdp-content">' + blocking + tab + '</div>'
    + '</div></div>';

  // The bullets' shared byte budget is measured from the DOM once the cards
  // exist -- the same call openDrawer makes, for the same reason.
  setTimeout(function(){ if(typeof bulletMeter === "function") bulletMeter(); }, 40);
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
