// static/js/listings_drawer_build.js -- building the product page / drawer content. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

// ---- DRAWER: full editor for one listing ----
function _marketIsUS(){
  try{ return String((typeof WS_MARKET!=="undefined"&&WS_MARKET)||(CUR_ACCOUNT&&CUR_ACCOUNT.marketplace)||"").toUpperCase()==="US"; }
  catch(e){ return false; }
}
function _stripUKforUS(s){
  // Old rows were generated before compliance became marketplace-aware, so their
  // saved notes can carry UK wording (UKCA, BS 1363, UK/EU dangerous goods) even
  // on a US listing. When the active marketplace is US, rewrite those phrases at
  // DISPLAY time so the flag isn't misleading. (Does not change stored data.)
  if(!_marketIsUS()) return s;
  return String(s)
    .replace(/UK\/EU dangerous goods shipping regulations/gi, "US/international dangerous goods shipping regulations")
    .replace(/\bUKCA\b[^.;|]*/gi, "")
    .replace(/BS\s?1363[^.;|]*/gi, "")
    .replace(/UK Batteries Regulations[^.;|]*/gi, "")
    .replace(/\bWEEE\b[^.;|]*/gi, "")
    .replace(/for (the )?UK market/gi, "for the US market")
    .replace(/\s{2,}/g," ").trim();
}
/* `row` is optional and only used for context (barcode, product type) when
   translating Amazon's own messages. Every other caller is unaffected. */
function formatFindings(findings, row){
  if(!findings || !findings.length) return "A note is set, but no specific detail was recorded.";
  // Notes may already contain HTML entities (e.g. &#39; for apostrophes) if a
  // previous run stored them escaped. Decode first so splitting + display work.
  const deEntity = (s)=> String(s)
    .replace(/&#39;/g,"'").replace(/&apos;/g,"'").replace(/&quot;/g,'"')
    .replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">");
  findings = findings.map(f=>_stripUKforUS(deEntity(f)));
  const joined = findings.join(" ");
  // If this looks like an API preview error list, split into individual rows so
  // each missing/invalid field is its own line item instead of a wall of text.
  if(/required but missing|\[E\]|\[W\]|API (PREVIEW|SUBMIT)/i.test(joined)){
    // strip the "API PREVIEW - N error(s):" prefix, then split on "; "
    const body = joined.replace(/API (PREVIEW|SUBMIT)[^:]*:\s*/i, "");
    const items = body.split(/;\s*/).map(s=>s.trim()).filter(Boolean);
    if(items.length){
      /* SAY WHAT IT MEANS, not just what Amazon typed.
       *
       *     "when amazon is rejecting something or there is an error i should
       *      be able to see what is it and also i should be able to understand
       *      it"
       *
       * This box is where a stored Amazon message is actually read — the
       * Preview panel is only on screen for the moment a run finishes. It
       * showed the raw line with its first word in bold, so the reader got
       * "item_dimensions_fraction Value '10.' for attribute 'Overall Height
       * Derived' has too few decimal places" and no idea what to do.
       *
       * renderAmazonErrors is the SAME translator the Preview panel uses
       * (CLAUDE.md Rule 12) and it keeps the verbatim text under a toggle, so
       * nothing is hidden — it just is not the first thing you read. Measured
       * over the 97 Amazon lines stored across every account: all 97 translate.
       */
      const _plain = items.map(it => it.replace(/^\[[EW]\]\s*/, ""));
      if(typeof renderAmazonErrors === "function"){
        const _ctx = {barcode: (row && row.barcode) || "",
                      sku: (row && row.sku) || "",
                      productType: (row && row.product_type) || ""};
        const _t = renderAmazonErrors(_plain, body, _ctx);
        if(_t.matched) return _t.html;
      }
      // Nothing recognised: the raw list, exactly as before.
      return '<div class="errlist">' + items.map(it=>{
        const isErr = /^\[E\]/.test(it) || /required|invalid|missing/i.test(it);
        const txt = it.replace(/^\[[EW]\]\s*/,"");
        // pull the field name (first token) to bold it
        const m = txt.match(/^(\S+)\s+(.*)$/);
        const field = m? m[1] : "";
        const rest  = m? m[2] : txt;
        return '<div class="erritem '+(isErr?'e':'w')+'"><span class="errfield">'+esc(field)+'</span> '+esc(rest)+'</div>';
      }).join("") + '</div>';
    }
  }
  // not an API error list -> show as-is (compliance/IP notes), escaped + newlines
  return findings.map(f=>esc(f)).join("\n");
}
// Read-only "Actual on Amazon" panel: the REAL listing data pulled by a Sync
// (images, item-type-keyword, variations/theme, bullets, description). Kept apart from
// the editable draft fields — this is a mirror of what's live, never your draft copy.
// Returns "" when nothing has been synced for this SKU.
/* "2 hours ago" for when Sync read this listing from Amazon, or "" when the
 * entry carries no time. lrAgo (listrow_detailed.js) is the app's one "ago"
 * formatter. The time is stored with the entry (domain/live_mirror_store.py),
 * so it survives a reload -- which is when saying it matters most. */
function _mirrorAgo(m){
  const t = m && Number(m._synced_at);
  if(!t || typeof lrAgo !== "function") return "";
  return lrAgo(t);
}

function liveMirrorPanel(r){
  const m = LIVE_MIRROR[String(r&&r.sku||"").trim()];
  if(!m) return "";
  const imgs = (m.images||[]);
  const imgHtml = imgs.length
    ? `<div class="mirimgs">${imgs.map(u=>`<a href="${esc(u)}" target="_blank" rel="noopener"><img src="${esc(u)}" loading="lazy" onerror="this.closest('a').style.display='none'"></a>`).join("")}</div>`
    : `<div class="cc">No images returned by Amazon.</div>`;
  const bullets = (m.bullets||[]).filter(Boolean);
  const bulletHtml = bullets.length
    ? `<ul class="mirbul">${bullets.map(b=>`<li>${esc(b)}</li>`).join("")}</ul>` : "";
  const v = m.variations||{};
  const varBits = [];
  if(m.variation_theme) varBits.push(`theme: <b>${esc(m.variation_theme)}</b>`);
  if(v.is_parent && (v.child_skus||[]).length) varBits.push(`${v.child_skus.length} child SKU(s)`);
  if(v.is_child && (v.parent_skus||[]).length) varBits.push(`child of ${esc(v.parent_skus.join(', '))}`);
  const varHtml = varBits.length ? `<div class="mirrow"><span class="mirk">Variations</span><span>${varBits.join(" · ")}</span></div>` : "";
  const kw = m.item_type_keyword ? `<div class="mirrow"><span class="mirk">Item type keyword</span><span>${esc(m.item_type_keyword)}</span></div>` : "";
  const desc = m.description ? `<div class="mirrow"><span class="mirk">Description</span><span class="mirdesc">${esc(m.description)}</span></div>` : "";
  return `<details class="mirbox" open>
    <summary class="mirsum"><i class="ti ti-brand-amazon"></i> Actual on Amazon <span class="cc">(read-only — pulled by Sync${_mirrorAgo(m) ? ", synced " + esc(_mirrorAgo(m)) : ""}, ${imgs.length} image(s))</span></summary>
    <div class="mirbody">
      ${imgHtml}
      ${kw}${varHtml}
      ${bulletHtml?`<div class="mirrow"><span class="mirk">Bullets</span><span>${bulletHtml}</span></div>`:''}
      ${desc}
      <div class="cc" style="margin-top:6px">This mirrors what's live on Amazon. It never changes your draft — edit the fields below to change your copy.</div>
    </div></details>`;
}

function drawerContent(r){
  const risks = [];
  if(r.ip_risk==="HIGH") risks.push('<span class="risk hi">IP: HIGH</span>');
  return _dwShell(r, _rowImages(r),
                  r.price?`${CUR_SYMBOL}${esc(String(r.price).replace(/^[A-Z]{3}/,''))}`:'',
                  risks);
}

/* AMAZON'S OWN MESSAGES ABOUT THIS ROW, and our IP note.
 *
 * Pulled out of drawerContent into its own function so that the fold which
 * shows it (_dwVerdictFolds) can be rebuilt with the data block after an
 * edit. The text, the reasons and the wording are exactly as they were.
 */
function _dwStatusBlock(r){
  const findings = [];
  if(r.notes && r.notes.trim()) findings.push(r.notes);
  if(r.comp_notes && r.comp_notes.trim()) findings.push(r.comp_notes);
  // Header risk chips: keep only the genuine IP/trademark one. The old "Compliance: HIGH/MED"
  // chips came from the legacy category matcher and cried wolf on clean products -- the
  // Restricted products check panel now carries real compliance, so those are dropped.
  const hasFeedback = findings.length>0;
  // This panel shows AMAZON'S OWN post-submit messages (attribute conflicts, catalogue
  // mismatches) + our IP note -- NOT a restricted-products / docs verdict. That lives in the
  // separate "Restricted products check" panel. Label it honestly so it never masquerades
  // as "docs required".
  // Say WHY on the summary line itself. It used to read "IP / trademark review"
  // with the actual cause hidden inside the collapsed box, so a row could show
  // IP: HIGH with no visible reason at all -- there was no way to tell a real
  // trademark leak from a false flag without opening it.
  let reason = (r.ip_risk && r.ip_risk!=="") ? "IP / trademark review" : "Amazon feedback";
  // A cell that literally says "None" is a Python None that was written out as
  // four characters, not a value. 193 stored rows carry one in compliance
  // notes alone, and joining it onto the note behind it is what produced
  // "IP: forbidden phrase — compatible with None" on screen: the phrase was
  // "compatible with", and "None" was the next cell.
  const _ipNote = _noneless(r.notes) + ' ' + _noneless(r.comp_notes);
  if(r.ip_risk && r.ip_risk!==""){
    let mm=_ipNote.match(/COMPETITOR BRAND in copy:\s*([^|]+)/i);
    if(mm) reason = "IP: competitor brand in copy — "+mm[1].trim();
    else if((mm=_ipNote.match(/phrases?:\s*([^|]+)/i)))
      reason = "IP: forbidden phrase — "+mm[1].trim();
    else if((mm=_ipNote.match(/(?:suspected|possible) brand words?(?:\s*\(unconfirmed\))?:\s*([^|]+)/i)))
      reason = "IP: possible brand words (unconfirmed) — "+mm[1].trim();
  }
  if(reason.length>110) reason = reason.slice(0,107)+"…";
  // Is this an ACTUAL blocking problem, or just an informational compliance note
  // (e.g. "lithium battery -> these docs may be requested")? A real problem = an
  // API error/hold or an IP risk. A compliance note on an already-submitted/live
  // listing is informational, so show it ORANGE, not alarming red.
  // Keyed off ip_risk, not off the reason text -- the reason now varies per row.
  const _fbNote = (r.ip_risk && r.ip_risk!=="")
    ? "Our brand/trademark check — not a docs requirement."
    : "Amazon’s own submission messages (attribute conflicts, catalogue mismatches) — NOT a restricted-products or docs verdict. See the Restricted products check panel for that.";
  const statusBlock = hasFeedback
    ? `<details class="findingsbox"><summary class="findsum neutral">\u2139 ${esc(reason)}</summary>
        <div class="cc" style="margin:2px 0 6px;font-size:11.5px;color:var(--muted)">${esc(_fbNote)}</div>
        <div class="findings neutral">${formatFindings(findings, r)}</div>
        <button class="linkbtn" style="margin-top:6px" onclick="locateFlags(${jsArg(r.sku)},this)">\ud83d\udd0d Locate flagged terms</button>
        <div class="locout" id="loc_${sid(r.sku)}"></div></details>`
    : "";
  return statusBlock;
}

/* A+ CONTENT LIVE ON AMAZON for this ASIN, straight from the A+ Content API.
 * Grouped per document, because one ASIN can carry more than one. Unchanged
 * except that it is now its own function, for the same reason as
 * _dwStatusBlock above. */
function _dwAplus(r){
  const aplusDocs = aplusFor(r);
  const aplusHtml = aplusDocs.length ? `
    <div class="kvsec" style="color:var(--ai);margin-top:14px"><i class="ti ti-layout-board"></i> A+ content live on Amazon</div>
    ${aplusDocs.map(function(d){ return `
      <div class="aplusdoc">
        <div class="aplushead">
          <b>${esc(d.name||'(untitled)')}</b>
          <span class="livestatus" style="background:var(--ok-bg);color:var(--ok)">${esc(d.status||'')}</span>
          <span class="cc">${d.module_count} module(s) · ${(d.images||[]).length} image(s)</span>
        </div>
        <div class="aplusimgs">
          ${(d.images||[]).map(function(im){ return `<a href="${esc(im.url)}" target="_blank" rel="noopener" title="${esc(im.alt||'')} — ${im.w||'?'}x${im.h||'?'} — open full size"><img src="${esc(im.url)}" loading="lazy" alt="${esc(im.alt||'')}" onerror="this.closest('a').style.display='none'"></a>`; }).join("")}
        </div>
      </div>`; }).join("")}` : aplusUnknownNote();
  return aplusHtml;
}

/* ============================================================================
   THE DRAWER, AS THE DESIGN DRAWS IT
   ============================================================================
   Three fixed parts: a header that never scrolls away, a body that does, and
   a footer holding the three things you actually do to a listing.

   NOTHING BELOW DECIDES ANYTHING. Every button calls the function it called
   before -- previewOne, autoFixLoop, submitOne, setStatus, drawerMore,
   openStudioSingle, askAbout -- and every value is read off the same row. The
   panels that the design file does not draw are all still here; they are
   folded (dwFold) with their verdict on the closed summary, so a compliance
   flag or a document demand is still readable without opening anything.

   THE EXCEPTION, DELIBERATELY: a BLOCKING banner is never folded. A barcode
   that already belongs to another listing, or a prohibited product, is drawn
   open, above everything. CLAUDE.md Rule 1 requires a clash to be reported,
   and a report you have to go looking for has not been made.
   ========================================================================= */
function _dwShell(r, urls, priceStr, risks){
  const sv = sid(r.sku);
  const live = isAmazonLive(r);
  const st = String(r.status||"").toUpperCase();
  const ownAsin = (rowAsin(r)||{}).own || "";
  const srcAsin = (rowAsin(r)||{}).source || "";
  const ro = !!window.WS_READONLY;

  // ---- header ---------------------------------------------------------
  // The ASIN shown is OURS when we have one. The competitor reference from
  // the SKU is labelled as a source and never presented as this listing's
  // ASIN -- see rowAsin(); this app creates new products, it does not add
  // offers to somebody else's.
  // The ASIN IS the link -- "we should be able to open the listing by clicking
  // on the green asin". Deliberately NOT titled "Open this listing on Amazon":
  // that exact wording belongs to the card button that was removed, and
  // test_product_card.py guards it. This says which ASIN it opens, which is
  // the thing worth saying here anyway.
  const asinBit = ownAsin
    ? `<a class="dw2-asin" href="https://www.amazon.${_dwTld(r)}/dp/${esc(ownAsin)}" target="_blank" rel="noopener" title="Open ${esc(ownAsin)} on Amazon in a new tab">${esc(ownAsin)}</a>`
    : (srcAsin ? `<span class="dw2-asin src" title="The competitor ASIN in the SKU \u2014 the reference this listing was built from, NOT our listing">ref ${esc(srcAsin)}</span>` : "");
  // THE DRAWER IS WHERE SOMEBODY GOES TO CHECK, so it must not be the one place
  // still showing the stale word. This printed r.status raw, while every list
  // view -- and the `live` flag three lines above -- had already worked out that
  // a listing carrying an old IP_HOLD is on Amazon. Opening it to find out why
  // it was held would have shown the hold that no longer applies.
  const _shown = (typeof _shownStatus === "function")
    ? String(_shownStatus(r) || "").toUpperCase()
    : String(r.status || "").toUpperCase();
  // AND THE SAME WORD THE ROW SHOWS. The badge text goes through liststatus.js
  // like the table's pill and the detailed row's badge do, so opening a row
  // badged DRAFT cannot show a drawer headed GENERATED for the same listing.
  // That drift is the exact fault the header of liststatus.js was written about,
  // and this was the third renderer -- missed when the first two were changed.
  // Colour still from badgeClass(_shown): only the word is mapped.
  const _word = (typeof lsBadgeWord === "function") ? lsBadgeWord(_shown) : _shown;
  const bar = `<div class="dw2-bar">
      <span class="badge ${badgeClass(_shown)}"${
        _shown !== String(r.status||"").toUpperCase()
          ? ` title="Amazon is showing this listing, so it is live. Its stored status still says ${esc(r.status||'')} from an earlier attempt."`
          : ""}>${esc(_word||'\u2014')}</span>
      ${risks.join("")}
      ${asinBit}
      <span class="dw2-spacer"></span>
      <button class="dw2-ib" onclick="previewOne(${jsArg(r.sku)})" title="Preview \u2014 check this listing against Amazon. Nothing is sent."><i class="ti ti-eye"></i></button>
      <button class="dw2-ib accent" onclick="autoFixLoop(${jsArg(r.sku)})" title="Auto-fix \u2014 suggest, apply, preview, repeatedly, until there are no errors left (max 8 rounds)"><i class="ti ti-wand"></i></button>
      ${ro ? `<button class="dw2-ib" disabled title="Read-only workspace \u2014 cannot publish"><i class="ti ti-lock"></i></button>`
           : `<button class="dw2-ib success" onclick="submitOne(${jsArg(r.sku)})" title="Submit \u2014 publish ONLY this listing live"><i class="ti ti-upload"></i></button>`}
      <button class="dw2-ib ${st==='APPROVED'?'on-approve':''}" onclick="setStatus(${jsArg(r.sku)},'APPROVED',this)" title="${st==='APPROVED'?'Already approved':'Approve \u2014 mark ready to send'}"><i class="ti ti-check"></i></button>
      <button class="dw2-ib ${st==='NEEDS_REVIEW'?'on-hold':''}" onclick="setStatus(${jsArg(r.sku)},'NEEDS_REVIEW',this)" title="${st==='NEEDS_REVIEW'?'Already held':'Hold \u2014 keep it back'}"><i class="ti ti-hand-stop"></i></button>
      <button class="dw2-ib" onclick="drawerMore(event,${jsArg(r.sku)},${r.row||0},${live?'true':'false'})" title="Everything else"><i class="ti ti-dots"></i></button>
      <button class="dw2-ib" onclick="pdpOpen(${jsArg(r.sku)})" title="Open full screen — the same listing with room for the description, the bullets and every attribute side by side"><i class="ti ti-arrows-diagonal"></i></button>
      <button class="dw2-ib bare" onclick="closeDrawer()" title="Close"><i class="ti ti-x" style="font-size:16px"></i></button>
    </div>`;

  // ---- hero -----------------------------------------------------------
  // The title is edited HERE and nowhere else. It keeps its claim-risk
  // highlights, and saveEdit reads textContent, so the <mark> markup can
  // never reach Amazon. Its counter and the 27 Jul 2026 cap warning sit
  // under it -- the same TITLE_OPTS every other title check uses.
  // dwTitleParts (drawer.js) builds the editor, its counter and its cap
  // warning. The full-screen product page uses the same one -- see the note on
  // that function for why a second title box is never the answer.
  const tp = dwTitleParts(r, "dwtitlec_" + sv);
  const heroImg = (urls && urls.length)
    // 68px, which is what .dw2-heroimg draws. It was the raw URL.
    ? `<div class="dw2-heroimg"><i class="ti ti-photo"></i><img src="${esc(thumbUrl(urls[0],68))}" loading="lazy" decoding="async" onerror="this.remove()"></div>`
    : `<div class="dw2-heroimg"><i class="ti ti-photo"></i></div>`;
  const cost = _dwCost(r);
  const heroBlock = `<div class="dw2-hero">
      ${heroImg}
      <div class="dw2-heroinfo">
        ${tp.editor}
        <div class="dw2-sku">${esc(r.sku)||'\u2014'}${r.brand?(' \u00b7 '+esc(r.brand)):''}</div>
        <div class="dw2-prices">
          ${priceStr?`<span class="big">${priceStr}</span>`:''}
          ${cost?`<span class="muted">cost ${esc(cost)}</span>`:''}
          ${r.profit?`<span class="green">${CUR_SYMBOL}${esc(String(r.profit).replace(/^[A-Z]{3}/,''))}</span>`:''}
        </div>
      </div>
    </div>
    <div class="dw2-sec" style="padding-top:9px;padding-bottom:9px">
      <div class="dw2-sechead" style="margin-bottom:0"><span>Title</span><span class="dw2-secright">
        ${tp.count}
        ${tp.indexTag}
      </span></div>
      ${tp.warnNote}
    </div>`;

  // ---- metrics --------------------------------------------------------
  const m = _dwMetrics(r);
  const metrics = `<div class="dw2-metrics">
      <div class="dw2-metric" title="${esc(m.flagTip)}"><div class="dw2-mv ${m.flagCls}">${m.flags}</div><div class="dw2-ml">Flags</div></div>
      <div class="dw2-metric" title="${esc(m.idxTip)}"><div class="dw2-mv ${m.idxCls}">${m.idx}</div><div class="dw2-ml">Indexed</div></div>
      <div class="dw2-metric" title="Profit stored for this listing."><div class="dw2-mv ${m.profit?'green':''}">${m.profit||'\u2014'}</div><div class="dw2-ml">Profit</div></div>
    </div>`;

  // ---- what stays open, and what folds ---------------------------------
  // identifierPanel and complianceBanner already return "" when there is
  // nothing to say, and a BLOCKED one is the loudest thing in the drawer.
  // Those two are never folded (see the note at the top of this function).
  const idPanel = identifierPanel(r);
  const compBan = complianceBanner(r);
  // Wrapped, because these three carry their own inline margins from when
  // they sat inside a padded drawer. The drawer has no padding now -- each
  // section supplies its own -- so without this they would run edge to edge.
  const _on = needsCopyPanel(r) + idPanel + compBan;
  const alwaysOn = _on ? `<div class="dw2-alwayson">${_on}</div>` : "";

  const footer = `<div class="dw2-foot">
      <button onclick="previewOne(${jsArg(r.sku)})" title="Check this listing against Amazon. Nothing is sent."><i class="ti ti-eye"></i> Preview</button>
      <button class="primary" onclick="autoFixLoop(${jsArg(r.sku)})" title="Suggest, apply, preview -- repeatedly, until there are no errors left or it stops making progress (max 8 rounds)."><i class="ti ti-wand"></i> Auto-fix</button>
      ${ro ? `<span class="ro"><i class="ti ti-lock"></i> Read-only workspace</span>`
           : `<button class="success" onclick="submitOne(${jsArg(r.sku)})" title="Publish ONLY this listing live"><i class="ti ti-upload"></i> Submit</button>`}
    </div>`;

  return `<div class="dw2">
    ${bar}
    <div class="dw2-body">
      ${alwaysOn}
      ${_dwWarnings(r)}
      ${heroBlock}
      ${metrics}
      <label class="dw2-setting" title="Send only the fields Amazon strictly requires (plus price/title/etc.). Create the listing now, add the rest in Seller Central. Note: lithium-battery products still require their safety fields.">
        <input type="checkbox" onchange="toggleMinimal(this)" ${MINIMAL_MODE_ON?'checked':''}>
        <span>Minimal mode \u2014 send only the fields Amazon strictly requires</span>
      </label>
      <div id="suggestbox_${sv}" class="suggestbox"></div>
      <div id="runpanel_${sv}" class="runpanel" style="display:none">
        <div class="runhead"><span class="runtitle"></span><button class="runclose" onclick="window.RUN_STREAMING=false;this.closest('.runpanel').style.display='none'">\u2715</button></div>
        <div class="runverdict"></div>
        <details class="runlogwrap"><summary>Show the full Amazon response log</summary><pre class="runlog"></pre></details>
      </div>
      <div id="fulldata_${sv}">${fullData(r)}</div>
      <div class="dw2-ask">
        <button onclick="openStudioSingle(${jsArg(r.sku)})"><i class="ti ti-photo"></i> Image Studio</button>
        ${live ? `<button onclick="optimizeLive(${jsArg(ownAsin)},${jsArg(r.sku)})"><i class="ti ti-sparkles"></i> Optimize live copy</button>` : ""}
        <button onclick="askAbout(${jsArg(r.sku)})"><i class="ti ti-message-circle"></i> Ask Claude about this listing</button>
      </div>
    </div>
    ${footer}
  </div>`;
}

// Amazon domain for the row's marketplace, so the ASIN in the header opens the
// right storefront rather than always amazon.co.uk.
function _dwTld(r){
  const m = (typeof rowMkt === "function") ? rowMkt(r) : "UK";
  return ({UK:"co.uk", US:"com", DE:"de", FR:"fr", IT:"it", ES:"es", NL:"nl",
           CA:"ca", MX:"com.mx", AU:"com.au", SE:"se", PL:"pl", TR:"com.tr",
           AE:"ae", SA:"sa", IN:"in", JP:"co.jp", BR:"com.br"})[m] || "co.uk";
}

/* WHAT THE STOCK COST, IF WE ACTUALLY KNOW -- as cogsOf() says (cogs.js).
 *
 * This used to fall back to the number at the front of the SKU
 * (8.00_3Days_B0...), after cogsOf() had stopped doing exactly that on the
 * owner's word ("lets remove the cogs from sku things entirely"). So the
 * product page's and drawer's Cost badge printed a figure on rows the rest of
 * the app, and the profit beside it, treat as having no cost at all. One
 * resolver now (Rule 12): a cost typed this session (COGS_LOCAL), else the
 * row's resolved cogs, else "" -- a made-up cost would make the profit beside
 * it a lie. */
function _dwCost(r){
  const c = (typeof cogsOf === "function") ? cogsOf(r) : {cost: null};
  if(c.cost === null || c.cost === undefined || !isFinite(Number(c.cost))) return "";
  return CUR_SYMBOL + Number(c.cost).toFixed(2);
}

/* THE THREE NUMBERS AT THE TOP, AND WHERE EACH ONE COMES FROM.
 *
 * There is no invented "listing quality score" here. The design file shows
 * one; this app computes no such thing, and a number with nothing behind it
 * is worse than an empty space, because it will be trusted.
 *
 * Flags    every warning already raised against this listing -- claim risks,
 *          restricted-product matches, document demands. Counted, not judged.
 * Indexed  how much of the bullet copy Amazon actually searches: the
 *          1,000-byte cap over the real byte length of all five bullets.
 * Profit   the stored figure, untouched.
 */
function _dwMetrics(r){
  const claims = (r.claim_flags || []).length;
  const rest = (r.restricted && r.restricted.matched && (r.restricted.matches || []).length) || 0;
  const docs = (r.viability && r.viability.matched && (r.viability.risks || []).length) || 0;
  const flags = claims + rest + docs;
  const bytes = (r.bullets || []).reduce(function(n, b){ return n + byteLen(b || ""); }, 0);
  const pct = bytes ? Math.min(100, Math.round(1000 / bytes * 100)) : 0;
  const pnum = String(r.profit == null ? "" : r.profit).replace(/[^0-9.\-]/g, "");
  return {
    flags: flags,
    flagCls: flags === 0 ? "green" : (rest || claims ? "amber" : "amber"),
    flagTip: flags === 0
      ? "No claim risks, no restricted-product match and no document demand. Keyword checks \u2014 not a clearance."
      : claims + " claim risk(s), " + rest + " restricted match(es), " + docs + " document demand(s). None of these blocks publishing.",
    idx: bytes ? (pct + "%") : "\u2014",
    idxCls: !bytes ? "" : (pct >= 100 ? "green" : (pct >= 60 ? "amber" : "red")),
    idxTip: bytes
      ? bytes + " bytes of bullet copy; Amazon indexes the first 1,000 across all five combined, so " + pct + "% of it is searchable."
      : "No bullet copy yet.",
    profit: pnum ? (CUR_SYMBOL + pnum) : ""
  };
}

/* THE SIX VERDICT PANELS, FOLDED, IN THE ORDER THEY MATTER.
 *
 * They sit between the attributes and the reference material (raw JSON, the
 * exact payload) rather than after it, because "is there a restriction on
 * this product" is a question about the listing and "what JSON did we send"
 * is a question about the app.
 *
 * CALLED FROM _fullDataInner, not from _dwShell, and that is deliberate:
 * three other places rebuild ONLY the fulldata block after an edit
 * (_rebuildDrawerData, reloadSchemaNow, and the run queue). If these were
 * rendered by the shell instead, a rebuild would silently drop every
 * compliance verdict from the drawer until it was closed and reopened.
 *
 * Each one returns "" when it has nothing to say, and dwFold drops an empty
 * body -- so a listing with no flags shows no fold rather than six empty ones.
 */
/* WHAT IS WRONG WITH THIS LISTING — first, and open when it matters.
 *
 * These used to be statuses that STOPPED the listing: IP_HOLD and
 * COMPLIANCE_HOLD sat on the row and there was nothing to press until somebody
 * cleared them. They are warnings now and Submit is always available, so this
 * panel is the whole of what replaced the block. If it is not read, nothing is.
 *
 * Open by default when anything high-severity is in it, closed otherwise: a
 * duplicate barcode is worth interrupting for, "no barcode provided" on a
 * listing you already know has none is not.
 */
// WHAT EACH KIND OF WARNING LOOKS LIKE. An icon carries the kind at a glance so
// six warnings do not read as six identical paragraphs; the colour carries the
// severity, which is a different question. Anything unlisted falls back to a
// plain alert triangle rather than rendering nothing.
const WARN_ICONS = {
  duplicate_barcode: "ti-barcode",
  barcode_live_on_amazon: "ti-barcode",
  no_barcode: "ti-barcode-off",
  duplicate_ebay_item: "ti-copy",
  duplicate_competitor_asin: "ti-copy",
  ip_risk: "ti-gavel",
  compliance_risk: "ti-file-certificate",
  amazon_rejected: "ti-ban",
  stale_catalogue: "ti-clock-exclamation",
  placeholder_sku: "ti-tag",
};
function _warnIcon(t){ return WARN_ICONS[String(t || "")] || "ti-alert-triangle"; }

function _dwWarnings(r){
  const w = (typeof lsWarnings === "function") ? lsWarnings(r) : {n: 0, list: []};
  // NO WARNINGS, NO SECTION. An empty "Warnings" heading on a clean listing is
  // a thing to read and dismiss on every single one of them.
  if(!w.n) return "";
  const tone = function(s){
    s = String(s || "low").toLowerCase();
    return s === "high" ? "red" : (s === "medium" ? "warn" : "info");
  };
  const rows = w.list.map(function(x, i){
    const sev = String((x && x.severity) || "low").toLowerCase();
    const det = (x && x.details) || {};
    const bits = Object.keys(det).filter(function(k){
      return det[k] !== null && det[k] !== undefined && det[k] !== "";
    });
    // The "why", folded away. Every check records what it matched on, and that
    // is the difference between "change the barcode" and "which barcode".
    const why = bits.length
      ? '<div class="dw2-why" id="dww' + i + '" style="display:none">'
        + bits.map(function(k){
            return '<div><span class="cc">' + esc(k.replace(/_/g, " "))
                 + ':</span> ' + esc(String(det[k])) + '</div>';
          }).join("")
        + '</div>'
      : "";
    return '<div class="dw2-warn ' + tone(sev) + '">'
      + '<div><i class="ti ' + _warnIcon(x && x.type) + '"></i> '
      + '<span class="dw2-tag ' + tone(sev) + '">' + esc(sev) + '</span> '
      + esc(String((x && x.message) || "")) + '</div>'
      + (bits.length
          ? '<button class="linkbtn" style="font-size:11px" onclick="'
            + "var e=document.getElementById('dww" + i + "');"
            + "e.style.display=e.style.display==='none'?'block':'none';"
            + '">why</button>'
          : "")
      + why + '</div>';
  }).join("");

  const tag = '<span class="dw2-tag ' + (w.high ? "red" : (w.medium ? "warn" : "info"))
            + '">' + w.n + (w.high ? " — " + w.high + " high" : "") + '</span>';
  return dwFold("Warnings", tag,
    '<div class="dw2-warns">' + rows
    + '<div class="cc" style="margin-top:7px;font-size:11px">These do not stop '
    + 'anything. Submit is available whether you fix them or not — they are '
    + 'here so the decision is yours.</div></div>',
    !!w.high);
}

function _dwVerdictFolds(r){
  // WARNINGS ARE NOT IN HERE ANY MORE, deliberately.
  //
  // They were, and it put them in the wrong place. This block is rendered by
  // autofix.js as part of the drawer's DATA section, which comes after the
  // highlights, bullets, search terms, description, images, identity and
  // attributes -- so "at the top of the drawer" was, in practice, most of a
  // drawer's scrolling later. A panel nobody scrolls to is not a panel.
  //
  // _dwShell renders them now, first thing in the body, above the title. See
  // _dwWarnings.
  const p = _dwVerdictFoldParts(r);
  return p.compliance + p.mirror;
}

/* THE SAME SIX FOLDS, IN TWO GROUPS.
 *
 * The drawer shows them as one run, which is what _dwVerdictFolds joins them
 * into above. The product page has a Compliance tab, and "what Amazon is
 * serving right now" is not a compliance verdict -- the live mirror and A+
 * content are a different question from restricted products, document demands
 * and claim risks. Split here rather than in the page, so both views agree
 * about which fold is which (Rule 12). Every fold below is unchanged. */
function _dwVerdictFoldParts(r){
  const statusBlock = (typeof _dwStatusBlock === "function") ? _dwStatusBlock(r) : "";
  return {
    compliance:
        dwFold("Restricted products check", _dwVerdictTag(r.restricted && r.restricted.matched, "checked"), restrictedPanel(r))
      + dwFold("Compliance requirements", _dwVerdictTag(r.viability && r.viability.matched, "no demand"), viabilityPanel(r))
      + dwFold("Claim risks", (r.claim_flags||[]).length ? `<span class="dw2-tag warn">${(r.claim_flags||[]).length}</span>` : "", claimBox(r))
      + dwFold("Amazon feedback", statusBlock ? '<span class="dw2-tag warn">see inside</span>' : "", statusBlock),
    mirror:
        dwFold("Actual on Amazon", '<span class="dw2-tag info">read-only mirror'
               + (_mirrorAgo(LIVE_MIRROR[String(r && r.sku || "").trim()])
                   ? " · synced " + esc(_mirrorAgo(LIVE_MIRROR[String(r.sku).trim()])) : "")
               + '</span>', liveMirrorPanel(r))
      + dwFold("A+ content", '<span class="dw2-tag info">live on Amazon</span>', _dwAplus(r))
      // WHERE THIS LISTING IS BOUGHT FROM.
      //
      //     "on draft the sources should stay on the drafts page but should
      //      display the handling time, the carrier info and delivery time and
      //      source price and source name etc same as repricer shows it"
      //
      // Drawn by _ordSourcesHtml, the renderer the order panel and the repricer
      // both use, so it is the same format because it is the same code. Folded
      // rather than always-on: it is reference, not a verdict, and the panels
      // above are the ones that stop a listing being created.
      + ((typeof draftSourcesHtml === "function")
          ? dwFold("Suppliers", _dsFoldTag(r), draftSourcesHtml(r)) : "")
  };
}

/* What the closed Suppliers fold says, so it can be left closed.
 *
 * The count is what decides whether opening it is worth it -- one supplier is
 * the ordinary case and three is the reason the multi-supplier feature exists.
 * "not tracked yet" is the other half: these are attached to a DRAFT, and the
 * repricer does not price them until Amazon confirms the listing buyable. */
function _dsFoldTag(r){
  const D = (typeof dsGet === "function") ? dsGet(r && r.sku) : null;
  if(!D || D.state === "loading") return '<span class="dw2-tag info">reading…</span>';
  if(D.state === "error") return '<span class="dw2-tag warn">could not read</span>';
  const n = (D.options || []).length;
  if(!n) return '<span class="dw2-tag">none recorded</span>';
  return '<span class="dw2-tag info">' + n + (n === 1 ? " supplier" : " suppliers")
       + (D.tracked ? "" : " · not tracked yet") + '</span>';
}

// A closed fold has to say enough that you can decide not to open it.
function _dwVerdictTag(matched, clearWord){
  return matched
    ? '<span class="dw2-tag warn"><i class="ti ti-alert-triangle"></i> attention</span>'
    : '<span class="dw2-tag ok"><i class="ti ti-check"></i> ' + esc(clearWord) + "</span>";
}
