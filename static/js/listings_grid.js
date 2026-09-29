// static/js/listings_grid.js -- the card (grid) view and its chips. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* _warnCell was here -- the same count under the status pill in the table.
 * Removed with the card's badge and for the same reason: the Compliance column
 * is the next cell along, and it already names what is wrong. See the note
 * above _statusPill's neighbour, where _warnChip used to be. */

/* WAITING TO GENERATE. A queued row has a SKU and almost nothing else -- no
 * title yet, no bullets, no images -- so it needs to say why it looks empty. */
function _queuedChip(r){
  if(typeof lsIsQueued !== "function" || !lsIsQueued(r)) return "";
  return '<span class="tilefact cc" title="Uploaded or added by hand. Press '
       + 'Generate to fill it in."><i class="ti ti-clock"></i> '
       + 'Waiting to generate</span>';
}

function _statusDot(r){
  var s = r.status || "";
  // Amazon's own answer beats the stored word, exactly as the counts do.
  var live = false;
  try{
    var sets = _liveCatSetsForCurrentView();
    live = isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown);
  }catch(e){ live = (s === "LIVE"); }
  if(live || s === "LIVE"){
    // A REAL flag still shows. Nothing else does.
    if(_rowHasFlag(r)) return "var(--warn)";
    return "var(--ink3)";              // quiet: live and nothing against it
  }
  if(isHold(s) || s === "API_ERROR" || s === "ERROR") return "var(--red)";
  if(s === "NEEDS_REVIEW") return "var(--warn)";
  if(s === "APPROVED") return "var(--ok)";
  return "var(--ink3)";
}

// Is there anything actually WRONG with this row? The checks that already run --
// restricted product types, compliance document demands, IP and claim risks --
// rather than the status word.
function _rowHasFlag(r){
  if(!r) return false;
  if(String(r.ip_risk || "").toUpperCase() === "HIGH") return true;
  if((r.claim_flags || []).length) return true;
  var v = r.viability;
  if(v && v.matched && (v.risks || []).length) return true;
  var rs = r.restricted;
  if(rs && rs.matched && String(rs.overall_action || "").toUpperCase() !== "NONE")
    return true;
  return false;
}
// ---- GALLERY TILE ----
// Is this row confirmed live by AMAZON right now? Used to gate the live-only
// actions (Optimize, Pull live data). These used to key off r.status === "LIVE",
// i.e. the sheet's own claim -- so they appeared on rows Amazon had never seen and
// were missing from rows Amazon HAD published but whose sheet status was stale
// (e.g. still "SUBMITTED"). Returns false in the Drafts view, where the catalog was
// never fetched and we genuinely do not know.
function isAmazonLive(r){
  const sets = _liveCatSetsForCurrentView();
  if(!sets.liveGroupShown) return false;
  return isActuallyLive(r, sets.skus, sets.asins, true);
}

// A+ content (EBC) for this row, keyed by ASIN. Populated by loadAplus() from
// /live/aplus. getListingsItem never returns A+ modules -- they live behind Amazon's
// separate A+ Content API -- which is why the card only ever showed the main and
// secondary images. Returns [] when the account has no A+ content, or none for this ASIN.
function aplusFor(r){
  // KEYED BY OUR ASIN. This read r.asin, which on an app row is the competitor
  // reference from the SKU -- while APLUS_BY_ASIN is filled by /live/aplus with
  // OUR OWN A+ content under OUR OWN ASINs. The two could therefore only meet
  // by coincidence, so the A+ badge never appeared on a draft card that had A+
  // content; and on the coincidence it would have shown a competitor's A+
  // modules on our listing.
  //
  // Not demonstrable from the current data -- APLUS_BY_ASIN was empty on the
  // view measured, so there was nothing to match either way -- but the two
  // sides plainly key on different ASINs.
  const a = String(ownLiveAsin(r) || "").trim().toUpperCase();
  if(!a || typeof APLUS_BY_ASIN === "undefined") return [];
  return APLUS_BY_ASIN[a] || [];
}
function aplusImages(r){
  const out = [];
  aplusFor(r).forEach(function(d){ (d.images||[]).forEach(function(im){ if(im.url) out.push(im); }); });
  return out;
}

/* WHEN THERE IS NO A+ TO SHOW, WHICH OF THE TWO REASONS IS IT?
 *
 * "This listing has no A+ content" is a measurement. "Amazon would not tell us"
 * is not one, and drawing nothing for both says the first when the second is
 * true. MEASURED on jack_uk/UK: the A+ Content API answers Unauthorized because
 * that role is not granted to this SP-API application, so the whole index is
 * empty on every account and every A+ badge in the app has been answering "no"
 * from a question that was never asked.
 *
 * Nothing is drawn in the ordinary case -- an account with no A+ pages does not
 * need telling on every card. Only the unknown gets a line, and the line says
 * what to do about it.
 */
function aplusUnknownNote(){
  if(typeof APLUS_ERROR === "undefined" || !APLUS_ERROR) return "";
  // The one Amazon actually returns here is worth naming, because the fix is a
  // permission in Seller Central rather than anything in this app.
  const denied = /unauthor|denied|access/i.test(APLUS_ERROR);
  return '<div class="kvsec" style="color:var(--ai);margin-top:14px">'
    + '<i class="ti ti-layout-board"></i> A+ content live on Amazon</div>'
    + '<div class="odp-note warn" style="padding:10px 12px;line-height:1.6">'
    + '<b>Not known.</b> Amazon would not tell this app what A+ content this '
    + 'listing has, so an empty space here does not mean there is none.'
    // NAMING ONE ROLE WAS TOO NARROW. This said "grant the A+ Content role",
    // which sends somebody to fix one permission and find everything still
    // broken: measured on jack_uk/UK, the app authenticates fine (its refresh
    // token works) and then gets 403 [ROLE] on marketplace participation,
    // catalogue, pricing and product definitions as well. Several roles are
    // missing, and this screen cannot know which. The app already has a
    // diagnostic that lists them one by one, so it points there instead of
    // guessing which single permission to blame.
    //
    // THE BUTTON IS HERE, not "at the top of this page". It sent people to a
    // Diagnose button on the listings toolbar -- which, inside the product page,
    // is BEHIND the overlay, and has since moved into the ⋯ menu. runSpDiagnose
    // opens its own dialog above everything, so it works from right here (the
    // owner's PDP redesign).
    + (denied
        ? ' Amazon is refusing this app’s requests for this account. Run '
          + 'Diagnose SP-API (the button below) — it checks each permission in '
          + 'turn and names the ones that are missing.'
        : '')
    + '<div class="cc" style="margin-top:6px">Amazon said: '
    + esc(APLUS_ERROR) + '</div>'
    + (typeof runSpDiagnose === "function"
        ? '<button class="pdp-tb" style="margin-top:8px" onclick="event.stopPropagation();runSpDiagnose()">'
          + '<i class="ti ti-stethoscope"></i> Run diagnostics</button>' : '')
    + '</div>';
}

// "Inactive" chip carrying Amazon's own reason (out of stock, policy issue, no offer).
// Only rendered once /live/reconcile has actually asked Amazon about this SKU.
function _inactiveChip(r){
  if(typeof amzState !== "function") return "";
  const st = amzState(r);
  if(st.state !== "inactive") return "";
  const why = st.reason || "Amazon reports this listing is not buyable";
  return `<span class="tileinactive" title="${esc(why)}"><i class="ti ti-alert-circle"></i> Inactive</span>`;
}

function card(r){
  const findings = [];
  if(r.notes && r.notes.trim()) findings.push(r.notes);
  if(r.comp_notes && r.comp_notes.trim()) findings.push(r.comp_notes);
  // CARD ⚠️ ICON = a genuine RESTRICTED-PRODUCTS flag (prohibited/gated) OR a real hard
  // blocker ONLY. Deliberately EXCLUDED so they never raise the icon:
  //   - API_ERROR  -> that's Amazon's preview/submit attribute feedback (item_type_keyword,
  //                   color, is_fragile, catalogue mismatches). Informational; lives in the
  //                   "Amazon feedback" panel, NEVER the card icon. (This was the bug.)
  //   - COMPLIANCE_HOLD -> legacy category-matcher noise (the restricted check replaces it).
  //   - stored notes / old comp_risk / claims-risk -> never the icon.
  // Genuine blockers that DO raise it: IP_HOLD (trademark) and ERROR (generation failure).
  const _rest = r.restricted;
  const _restProhibited = !!(_rest && _rest.matches && _rest.matches.some(m=>m.tier==="PROHIBITED"));
  const _restFlag = !!(_rest && _rest.matched);
  // THE STATUS THIS ROW IS ACTUALLY IN, not the word left in the database.
  //
  // This read r.status raw, and the dot two lines below already does not: it
  // asks Amazon's catalogue through isActuallyLive(). So a listing that went
  // live months ago, whose stored status still says IP_HOLD from a failed
  // attempt before that, showed a quiet dot AND a red blocker icon on the same
  // tile -- and the table and detailed views showed it as LIVE.
  //
  // Exactly the disagreement this page has had before, fixed in the tiles and
  // in the table and missed here. _shownStatus is the one answer (Rule 12).
  const _st = (typeof _shownStatus === "function")
    ? String(_shownStatus(r) || "").toUpperCase()
    : String(r.status || "").toUpperCase();
  const _blocker = (_st==="IP_HOLD" || _st==="ERROR");
  const realIssue = _restFlag || _blocker;
  const flagRed = _restProhibited || _blocker;   // gated-only -> amber
  const urls=_cardImages(r);
  // The STRUCK-THROUGH camera, not the plain one. A plain camera glyph on a
  // grey square reads as an image that has not loaded yet; the struck-through
  // one says there is none. Both are in the font subset -- checked, because an
  // icon class that is not renders as an empty box with no error anywhere.
  // (test_http_perf.py scans this file for icon names and reads comments too,
  // so neither is written here as a partial name.)
  //
  // The onerror path adds .noimg to the CONTAINER, which is what draws the
  // "No image" caption underneath (see .tileimg.noimg::after) -- so a picture
  // that fails to load and one that was never there end up saying the same
  // thing, in the same place, instead of one of them leaving a blank square.
  const thumb = (urls&&urls.length)
    ? `<img src="${esc(thumbUrl(urls[0],120))}" loading="lazy" decoding="async" onerror="this.style.display='none';this.parentNode.classList.add('noimg');this.parentNode.innerHTML='<i class=\\'ti ti-photo-off\\'></i>'">`
    : `<i class="ti ti-photo-off"></i>`;
  const selected = SELECTED.has(String(r.sku));
  const skuId=sid(r.sku);
  const ownAsin=ownLiveAsin(r);   // your OWN live ASIN (from the live catalogue), or "" if not live/not loaded
  const _isDup=(typeof isDuplicate==="function") && isDuplicate(r);   // same SKU on another card/tab
  const _dupOther=_isDup?dupOtherTabs(r):[];
  return `<div class="tile ${selected?'sel':''} ${_isDup?'dup':''} ${flagRed?'flag':(realIssue?'flagamber':'')}" data-sku="${esc(r.sku)}">
    <div class="tileimg pii-img ${(urls&&urls.length)?'':'noimg'}" onclick="openListing(${jsArg(r.sku)})">
      ${thumb}
      <span class="tiledot" style="background:${_statusDot(r)}" title="${esc(_st||r.status||'')}"></span>
      ${rowSelectBox(r, "tilesel")}
      ${realIssue?`<span class="tileflag ${flagRed?'red':'amber'}" title="${flagRed?'Restricted / blocked — open to see why':'Restricted — docs required'}"><i class="ti ti-alert-triangle"></i></span>`:''}
      ${claimBadge(r)}
      ${viabilityBadge(r)}
      ${needsCopyBadge(r)}
      ${aplusImages(r).length?`<span class="tileaplus" title="A+ content live on Amazon — ${aplusImages(r).length} image(s). Open the listing to see them.">A+</span>`:''}
      ${_inactiveChip(r)}
      <button class="peek" title="Reveal this listing" onclick="event.stopPropagation();peekTile(this)"><i class="ti ti-eye"></i></button>
    </div>
    <div class="tilebody" onclick="openListing(${jsArg(r.sku)})">
      <div class="tiletitle pii">${esc(r.title)||'<span class="cc">(no title)</span>'}</div>
      <div class="tilemeta">
        ${_priceCell(r, "tileprice pii")}
        <span class="tilesku pii">${esc(r.sku)||''}</span>
      </div>
      <div class="tilefacts">${_brandCell(r)}${_handCell(r)}${_queuedChip(r)}</div>
      ${_econLine(r)}
      ${_ppcLine(r)}
      <!-- the "lives on the X tab" badge went with the spreadsheet -->

      ${_isDup?`<div class="tiledup" onclick="event.stopPropagation()">
        <span class="tiledup-lbl"><i class="ti ti-copy"></i> Duplicate SKU${_dupOther.length?` — also on ${esc(_dupOther.join(', '))}`:` — appears ${dupCopies(r).length}×`}</span>
        <button class="tiledup-del" title="Delete this copy from this app only (other copies stay, and nothing is sent to Amazon)" onclick="event.stopPropagation();delDuplicate(${jsArg(String(r.sku))},${r.row||0},${jsArg(String(r.tab||''))},this)"><i class="ti ti-trash"></i> Delete this copy</button>
      </div>`:''}
      ${ownAsin?`<div class="tileasin" title="Your own live ASIN on Amazon (from the live catalogue)"><i class="ti ti-brand-amazon"></i> <a href="${_dpUrl(ownAsin)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${esc(ownAsin)}</a></div>`:''}
    </div>
    <!-- Built by rowActions so the table row offers exactly the same set. The
         two used to be written out separately and had drifted: the table had
         no Approve, no Auto-fix and no More menu, and no checkbox at all. -->
    <div class="tileacts">${rowActions(r, "ib")}</div>
  </div>`;
}
