let ROWS = [], FILTER = "all", SHIP = "", SCHEMAS = {}, PTYPES = [];
// Where the rows on screen came from: {from_database, from_sheet, store, ...}.
// Set by loadRows. See the migration note in summary().
let ROWS_SOURCE = {};
// Multi-tab view: TABS = manifest [{tab,tab_gid,count,url}] from /rows_all.
// TAB_FILTER = "__all__" (show every tab) or a tab_gid to show just that tab.
let TABS = [], TAB_FILTER = "__all__";
// Live MIRROR: the REAL data pulled from Amazon on a Sync, keyed by SKU. Read-only —
// shown beside a live listing, never written into the sheet. Filled by fullPullLive().
let LIVE_MIRROR = {};
let SELECTED = new Set();      // SKUs ticked for batch actions
let CUR_SYMBOL = "\u00a3";     // £ default; flips to $ for US workspaces
let WS_MARKET = "";           // active marketplace within the workspace
let DRAWER_SKU = null;        // SKU currently open in the side drawer

// Resolve a listing's OWN marketplace (US/UK/…): the row's marketplace first,
// then its attributes, then the active workspace marketplace, then UK. Used so
// the schema/value lists are fetched for the listing's real marketplace+creds.
function rowMkt(r){
  r=r||{};
  return String(r._marketplace || (r.attributes||{}).marketplace || WS_MARKET || "UK").toUpperCase();
}

// toggleSelect ... batchAutoGenerate: moved to static/js/listings_selection.js (Milestone 4), loaded right after this file.
function _asinForSku(sku){
  // OUR ASIN FOR THIS SKU, or "" -- never the competitor reference.
  //
  // This fell back to (ROWS.find(...)).asin, which is the competitor ASIN out
  // of the SKU (see rowAsin below). Its one caller is batchAutoGenerate, which
  // stamps this onto every generated image job, so images we made for our own
  // product were being filed against somebody else's ASIN. "" is the correct
  // answer for a draft that is not live yet: it has no ASIN of its own.
  const s=String(sku);
  const it=(LIVE_ITEMS||[]).find(x=>String(x.sku)===s);
  return (it && it.asin) ? String(it.asin) : "";
}
// YOUR OWN live ASIN (the one Amazon assigned to YOUR listing) -- taken ONLY from the live
// catalogue matched by YOUR SKU. This is NOT the competitor ASIN embedded in the SKU
// (price_days_ASIN); we deliberately never fall back to r.asin here, which is competitor.
function ownLiveAsin(r){
  try{
    const s=String((r&&r.sku)||"").trim();
    if(!s) return "";
    const it=(LIVE_ITEMS||[]).find(x=>String(x.sku).trim()===s);
    return (it && it.asin) ? String(it.asin).trim() : "";
  }catch(e){ return ""; }
}

/* ================= WHICH ASIN BELONGS TO THIS ROW ==================
 *
 * TWO DIFFERENT ASINS, AND ONLY ONE OF THEM IS OURS.
 *
 * Rule 1: this app creates NEW products under our own brands. The ASIN in the
 * SKU (price_days_ASIN, e.g. 9.89_3Days_B07NT77GT8) is a COMPETITOR REFERENCE
 * used during generation to pull product data. It is not our listing and never
 * becomes our listing.
 *
 * MEASURED on jack_uk, all 67 rows: every one of the 56 rows carrying an ASIN
 * carries the COMPETITOR's -- r.asin was identical to the ASIN embedded in the
 * SKU in 56 cases out of 56, none differing. Where the listing is actually
 * live, our real ASIN is something else entirely:
 *
 *     SKU 9.89_3Days_B07NT77GT8   r.asin B07NT77GT8   ours B0H66Q1XFK
 *     SKU 7.99_2Days_B07GDBY3YS   r.asin B07GDBY3YS   ours B0H6Y62F96
 *
 * ownLiveAsin() above says so in a comment -- "we deliberately never fall back
 * to r.asin here, which is competitor" -- and then five other functions did
 * exactly that, each deciding for itself and each deciding wrong. One concept,
 * no shared helper, five answers (rule 12). This is the shared helper.
 *
 * THE SAME FIELD MEANS DIFFERENT THINGS depending on what was passed in, which
 * is what made this so easy to get wrong. On an APP ROW, r.asin is the
 * competitor. On a CATALOGUE ITEM straight from Amazon it is OURS. Both are
 * handed to the same rendering functions. This resolves both: `own` comes from
 * matching OUR sku against Amazon's catalogue, which is true either way, and
 * `source` is only reported when it is genuinely a different, non-ours ASIN.
 */
function rowAsin(r){
  const own = ownLiveAsin(r);
  let src = String((r && r.asin) || "").trim().toUpperCase();
  // A catalogue item's own ASIN is not a "source" -- it is the same listing.
  if(src && own && src === String(own).trim().toUpperCase()) src = "";
  return {own: own, source: src, ours: !!own};
}

/* Is this row's asin field the competitor reference embedded in its SKU?
 *
 * Used by the catalogue-matching functions below. Matching an APP ROW to
 * Amazon's catalogue by ASIN can only ever produce a FALSE POSITIVE -- a hit
 * means our catalogue happens to contain the COMPETITOR's ASIN, which would
 * declare our draft live because somebody else's listing exists. Matching by
 * SKU is authoritative and is what those functions do first anyway.
 *
 * Deliberately not "drop the ASIN leg entirely": a row whose asin is genuinely
 * ours (a catalogue item, or a row imported another way) should still match on
 * it. Only the SKU-embedded competitor reference is excluded.
 */
function _asinIsCompetitorRef(r){
  const a = String((r && r.asin) || "").trim().toUpperCase();
  if(!a) return false;
  const m = String((r && r.sku) || "").trim().toUpperCase().match(/_([A-Z0-9]{10})$/);
  return !!(m && m[1] === a);
}

/* The ASIN a row may be matched to Amazon's catalogue by: "" when the only one
   it has is a competitor reference. */
function _matchableAsin(r){
  return _asinIsCompetitorRef(r) ? "" : String((r && r.asin) || "").trim().toUpperCase();
}
// The ONE Amazon domain table. There were four places building these by hand and
// they disagreed: two sent every non-UK marketplace to amazon.com, two hardcoded
// amazon.co.uk outright. On a US or German account those links open the wrong
// country's store, where the ASIN usually does not exist at all.
const _AMZ_TLD = {
  UK:"co.uk", GB:"co.uk", US:"com", CA:"ca", MX:"com.mx", BR:"com.br",
  DE:"de", FR:"fr", IT:"it", ES:"es", NL:"nl", BE:"com.be", IE:"ie",
  PL:"pl", SE:"se", TR:"com.tr", AE:"ae", SA:"sa", EG:"eg", IN:"in",
  JP:"co.jp", AU:"com.au", SG:"sg",
};
function _amzTld(market){
  const m = String(market || (typeof WS_MARKET !== "undefined" && WS_MARKET) || "").toUpperCase();
  return _AMZ_TLD[m] || "co.uk";
}
// market is optional: omit it and the workspace's own marketplace is used. Pass
// it where a row carries its own (the ASIN monitor watches several at once).
function _dpUrl(asin, market){
  // "amazon." belongs here. The old table held whole domains ("amazon.co.uk");
  // this one holds TLDs ("co.uk") so the ASIN monitor can reuse it for seller
  // links, and when it was swapped in the prefix was left as "https://www." --
  // which built https://www.co.uk/dp/B0... A link that goes somewhere plausible
  // and wrong is worse than one that fails.
  return "https://www.amazon." + _amzTld(market) + "/dp/" + encodeURIComponent(asin || "");
}
async function batchSecondaryImages(){
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  // Detect whether the selected SKUs are LIVE Amazon listings (not in the draft
  // sheet). Live listings aren't rows in our sheet, so we generate the images
  // and hand them back for download (upload via Amazon Manage Images), using
  // each live listing's own Amazon photo as the visual reference.
  const liveSel = (LIST_SOURCE==='live' || LIST_SOURCE==='all');
  const liveRefs = {};
  if(liveSel){
    (LIVE_ITEMS||[]).forEach(it=>{ if(it.sku && skus.includes(String(it.sku)) && it.img) liveRefs[it.sku]=it.img; });
  }
  const brief=await uiPrompt("Describe the secondary images to generate (one shared set applied to all "+skus.length+" selected SKUs).\nSeparate each image idea with a comma or new line — e.g. 'lifestyle shot in a modern bathroom, infographic of key ingredients, clean packaging shot, how-to-use steps'.\n\nTip: keep text minimal and premium.");
  if(brief===null) return;
  toast("Generating secondary images for "+skus.length+" SKU(s)…");
  try{
    const res=await fetch("/genimage/secondary",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({skus:skus, brief:brief, live:liveSel, live_refs:liveRefs})});
    const j=await res.json();
    if(!j.ok){ toast("Failed: "+(j.error||"unknown")); return; }
    if(j.images && j.images.length){
      // show the generated set in a panel so the user can download each one
      showSecondaryResults(j.images, skus, liveSel);
    }
    toast(liveSel ? ("Generated "+ (j.images? j.images.length:0) +" image(s) — download below")
                  : ("Secondary images applied to "+skus.length+" SKU(s)"));
    if(!liveSel) loadRows();
  }catch(e){ toast("Error: "+e); }
}
function showSecondaryResults(images, skus, live){
  let host=document.getElementById("secresults");
  if(!host){
    host=document.createElement("div"); host.id="secresults";
    host.style.cssText="position:fixed;right:18px;bottom:18px;width:340px;max-height:70vh;overflow:auto;background:var(--card,var(--panel2));border:1px solid var(--line,var(--accent-line));border-radius:12px;padding:14px;z-index:9999;box-shadow:0 10px 40px rgba(0,0,0,.5)";
    document.body.appendChild(host);
  }
  const note = live
    ? "These are generated as a shared set. Download each, then upload to your live listings via Amazon → Manage Images (live listings can't be image-updated automatically)."
    : "Applied to the selected draft SKUs and saved to "+storeName()+".";
  host.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
    + '<b style="font-size:13px">Secondary images ('+images.length+')</b>'
    + '<button onclick="document.getElementById(\'secresults\').remove()" style="background:none;border:none;color:var(--accent2);cursor:pointer;font-size:16px">✕</button></div>'
    + '<div style="font-size:11px;color:var(--ink2);margin-bottom:10px">'+note+'</div>'
    + images.map((u,i)=>'<div style="margin-bottom:10px"><img src="'+u+'" style="width:100%;border-radius:8px;border:1px solid var(--line,var(--accent-line))"><a href="#" onclick="_downloadAsJpeg(' + jsArg(u) + ',\'secondary_'+(i+1)+'\');return false;" style="display:inline-block;margin-top:4px;font-size:12px;color:var(--accent2)">⬇ Download image '+(i+1)+'</a></div>').join("");
}
async function loadBrandPanel(){
  const host=document.getElementById('brandpanel');
  if(!host.dataset.loaded){
    host.innerHTML = await (await fetch('/brand/panel')).text();
    host.dataset.loaded='1';
    host.querySelectorAll('script').forEach(old=>{const s=document.createElement('script'); s.textContent=old.textContent; document.body.appendChild(s);});
    if(window.brandInit) window.brandInit();
  } else if(window.brandRefresh){
    window.brandRefresh();   // re-lock to the current workspace's brand
  }
}
function iBtnEntry(p){
  if(!p) return '';
  const verified = p.verified ? 'code-verified' : 'AI-reported';
  const tip = ((p.source||'') + (p.note? ' \u2014 '+p.note : '') + ' ('+verified+')');
  const warn = (String(p.source||'').startsWith('INFERRED') && !p.verified);
  return '<i class="ibtn '+(warn?'iwarn':'iok')+'" title="'+tip.replace(/"/g,'&quot;')+'">i</i>';
}
function iBtn(prov, key){ return (prov&&prov[key])?iBtnEntry(prov[key]):''; }
// Small source badge for an attribute value: where the data came from.
function srcBadge(src){
  if(!src) return '';
  const s=String(src).toLowerCase();
  let cls='', label='';
  if(s==='ebay'){ cls='src-ebay'; label='eBay'; }
  else if(s==='amazon'){ cls='src-amazon'; label='Amazon'; }
  else if(s==='ai'){ cls='src-ai'; label='AI'; }
  else return '';
  const tip = (s==='ebay') ? 'Value sourced from the eBay listing'
            : (s==='amazon') ? 'Value sourced from Amazon catalogue data'
            : 'Value written by AI from product knowledge — please verify';
  return '<span class="srcbadge '+cls+'" title="'+tip+'">'+label+'</span>';
}
function rowProvenance(r){ try{ return (JSON.parse(r.attrs||'{}')._provenance)||null; }catch(e){ return null; } }
// ---------------------------------------------------------------------------
// RE-CHECK FLAGS
// A wrong flag rule leaves every already-generated row carrying the wrong flag.
// Regenerating to clear one costs ~50s and Claude credits for copy that was
// never the problem. This re-runs the checks against the copy already in the
// sheet. Always previews first: it writes to the live sheet, so nothing changes
// until you have seen the list and said yes.
async function rescanFlags(){
  let r;
  try{
    toast("Re-checking flags on stored rows…");
    r = await (await fetch("/rescan/preview",{cache:"no-store"})).json();
  }catch(e){ toast("Re-check failed: "+e); return; }
  if(!r.ok){ toast("Re-check failed: "+(r.error||"unknown")); return; }
  if(!r.changes){ toast(`Scanned ${r.scanned} rows — no flags need changing`); return; }

  const lines = r.rows.slice(0,40).map(x=>{
    const bits=[];
    if(x.old_status!==x.new_status) bits.push(`${x.old_status} → ${x.new_status}`);
    if(x.old_ip!==x.new_ip)   bits.push(`IP ${x.old_ip||"none"} → ${x.new_ip||"none"}`);
    if(x.old_comp!==x.new_comp) bits.push(`Compliance ${x.old_comp||"none"} → ${x.new_comp||"none"}`);
    // Say which rows keep their status, rather than leaving somebody to wonder
    // why a LIVE listing still reads LIVE after a re-check.
    if(x.status_owned === false) bits.push(`(${x.old_status} kept)`);
    return `• ${x.sku}  ${bits.join("   ")}`;
  }).join("\n");
  const more = r.changes>40 ? `\n…and ${r.changes-40} more` : "";
  const _kept = r.rows.filter(x=>x.status_owned === false).length;

  const ok = await uiConfirm(
    `Re-check flags\n\n`+
    `Scanned ${r.scanned} rows. ${r.changes} would change.\n\n`+
    `${lines}${more}\n\n`+
    `Only Status, Notes, Compliance Risk and IP Risk are written.\n`+
    `Your copy, prices and SKUs are NOT touched.\n\n`+
    (_kept
      ? `${_kept} of these are APPROVED / LIVE / SUBMITTED / API_* rows. Their\n`+
        `STATUS is left exactly as it is — that is Amazon's state or your own\n`+
        `decision. Only the badge and the note are corrected, because those are\n`+
        `this app's verdict about its own copy.\n\n`
      : "")+
    `Apply these changes to ${storeName()}?`);
  if(!ok){ toast("Nothing written"); return; }

  try{
    const a = await (await fetch("/rescan/apply",{method:"POST"})).json();
    if(!a.ok){ toast("Apply failed: "+(a.error||"unknown")); return; }
    toast(`Updated ${a.updated} row(s)`);
    if(typeof loadRows==="function") loadRows();
  }catch(e){ toast("Apply failed: "+e); }
}

function locateFlags(sku, btn){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r) return;
  const out=document.getElementById('loc_'+sid(sku)); if(!out) return;
  // Pull flagged terms out of the note. Three shapes, and BOTH wordings of the
  // brand-word note must be accepted: rows generated before the IP-scanner fix
  // say "suspected brand words:", rows after it say "possible brand words
  // (unconfirmed):". Matching only one silently finds nothing on half your sheet.
  const notes=String(r.notes||'')+' '+String(r.comp_notes||'');
  let terms=[];
  let m=notes.match(/phrases?:\s*([^|]+)/i); if(m) terms=terms.concat(m[1].split(',').map(s=>s.trim()));
  m=notes.match(/(?:suspected|possible) brand words?(?:\s*\(unconfirmed\))?:\s*([^|]+)/i);
  if(m) terms=terms.concat(m[1].split(',').map(s=>s.trim()));
  m=notes.match(/COMPETITOR BRAND in copy:\s*([^|]+)/i);
  if(m) terms=terms.concat(m[1].split(',').map(s=>s.trim()));
  terms=terms.filter(t=>t&&t.length>1);
  if(!terms.length){ out.innerHTML='<div class="cc" style="margin-top:6px">No specific terms parsed from the note — the flag may be a category/compliance signal, not a word match.</div>'; return; }
  // search each content field for each term
  const fields={'Title':r.title,'Bullet 1':(r.bullets||[])[0],'Bullet 2':(r.bullets||[])[1],
    'Bullet 3':(r.bullets||[])[2],'Bullet 4':(r.bullets||[])[3],'Bullet 5':(r.bullets||[])[4],
    'Description':r.description,'Search terms':r.search_terms};
  let html='<div style="margin-top:8px;border-top:1px solid var(--line);padding-top:6px">';
  let any=false;
  terms.forEach(t=>{
    const re=new RegExp('('+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig');
    Object.keys(fields).forEach(fn=>{
      const v=String(fields[fn]||'');
      if(v && re.test(v)){
        any=true;
        const hl=esc(v).replace(re,'<mark style="background:var(--warn-line);color:var(--warn)">$1</mark>');
        html+='<div style="margin:4px 0"><b style="color:var(--warn)">'+esc(t)+'</b> in <b>'+fn+'</b>: <span style="color:var(--ink)">'+hl+'</span></div>';
      }
    });
  });
  if(!any) html+='<div class="cc">None of the flagged terms were found in the current copy — they may have already been edited out. Safe to re-check.</div>';
  html+='</div>';
  out.innerHTML=html;
}
(function(){
  document.querySelectorAll('header .pill[data-f]').forEach(p=>{
    p.addEventListener('click',()=>{
      document.getElementById('brandpanel').style.display='none';
      document.getElementById('grid').style.display='';
      document.getElementById('summary').style.display='';
    });
  });
})();

// tabPass ... ensureCardTab: moved to static/js/listings_search.js (Milestone 4), loaded right after this file.
// DUP_INDEX ... delDuplicate: moved to static/js/listings_dups.js (Milestone 4), loaded right after this file.
// isActuallyLive ... summary: moved to static/js/listings_summary.js (Milestone 4), loaded right after this file.
// Pull a LIVE listing's real data (every Amazon image: main + all secondary) into the row, so
// the product card, the drawer and Image Studio show the ACTUAL live photos instead of the
// eBay/competitor ones captured at generation time -- and so A+ finally has a reference image.
async function pullLiveRow(sku, btn){
  const _old = btn ? btn.innerHTML : "";
  if(btn){ btn.disabled=true; btn.innerHTML='<span class="genspin"></span> Pulling from Amazon…'; }
  try{
    const j = await (await fetch("/live/pull_row",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(acctBody({sku:sku}))})).json();
    if(!j || !j.ok){ toast("Couldn't pull from Amazon: "+((j&&j.error)||"unknown")); return; }
    toast("Pulled "+j.count+" live image(s) from Amazon");
    try{
      const r = await (await fetch(acctUrl("/row?sku="+encodeURIComponent(sku)))).json();
      if(r && r.ok && r.row){
        const i = ROWS.findIndex(x=>String(x.sku)===String(sku));
        if(i>=0) ROWS[i] = Object.assign({}, ROWS[i], r.row);
      }
    }catch(e){}
    try{ render(); }catch(e){}
    if(typeof DRAWER_SKU!=="undefined" && String(DRAWER_SKU)===String(sku)){ try{ openDrawer(sku); }catch(e){} }
    // The product page too -- the "..." menu there is where this is pressed.
    if(typeof pdpAfterAction === "function") pdpAfterAction(sku);
  }catch(e){
    toast("Pull failed: "+((e&&e.message)||e));
  }finally{
    if(btn){ btn.disabled=false; btn.innerHTML=_old; }
  }
}
function _rowImages(r){
  var a={};try{a=JSON.parse(r.attrs||'{}');}catch(e){a={};}
  var IMGRE=/^(main_product_image_locator|other_product_image_locator_\d+)$/;
  var urls=Object.keys(a).filter(k=>IMGRE.test(k)).sort().map(k=>a[k]).filter(Boolean);
  if(!urls.length) urls=Object.keys(a).filter(k=>/image_locator/i.test(k)).map(k=>a[k]).filter(Boolean);
  return urls;
}

// WHAT AMAZON IS ACTUALLY SHOWING FOR THIS LISTING, if we know.
//
// LIVE_ITEMS is the catalogue Amazon returned, and fetchLiveImages() fills each
// entry's .img from getListingsItem -- the real main image on the real listing.
// Matched by SKU first and only then by ASIN: two of your SKUs can sit on one
// ASIN, and in that case the SKU is the one that identifies the listing.
function _liveImageFor(r){
  if(typeof LIVE_ITEMS === "undefined" || !LIVE_ITEMS || !LIVE_ITEMS.length) return "";
  const norm = v => String(v == null ? "" : v).trim().toUpperCase();
  // The ASIN leg excludes the competitor reference (see _matchableAsin). A hit
  // on it would put the COMPETITOR'S photograph on our card as though Amazon
  // were showing it for our listing -- the exact thing the main-image guard in
  // the generator exists to prevent, arriving by a different door. The SKU leg
  // below is the one that normally answers, and it is authoritative.
  const s = norm(r && r.sku), a = _matchableAsin(r);
  let byAsin = "";
  for(const it of LIVE_ITEMS){
    if(!it) continue;
    const url = it.img || it.image || "";
    if(!url) continue;
    if(s && norm(it.sku) === s) return url;
    if(a && !byAsin && norm(it.asin) === a) byAsin = url;
  }
  return byAsin;
}

// THE PICTURE A CARD OR ROW SHOWS.
//
// "the images on the cards should reflect the images which are on amazon,
//  atleast the live listings section should follow this rule"
//
// A listing that is live on Amazon AND has a draft here was drawn from the
// DRAFT's attributes -- which hold whatever the generator put there, often the
// competitor or eBay photo the listing was built from. So the card showed the
// picture the listing came from rather than the one customers are looking at,
// and the two are frequently not the same product angle at all. Only the
// draft-less tiles used Amazon's own image.
//
// Deliberately NOT done by changing _rowImages(): that feeds the AI reference
// picker and the image studio, where the SOURCE photo is the right answer --
// eBay is the truth of what the item is, which is not the same question as what
// Amazon is currently displaying.
function _cardImages(r){
  const live = _liveImageFor(r);
  const own = _rowImages(r) || [];
  if(!live) return own;
  return [live].concat(own.filter(u => u !== live));
}
// The tile's corner dot. Returns CSS VARIABLES, not literal hex, so the dot and
// the status pill for the same row can never drift apart -- they now read from
// one set of tokens. LIVE is neutral grey here for the same reason .b-LIVE is:
// live is the resting state, not an achievement, and a grid of green dots made
// every finished listing look like it wanted attention.
// THE DOT IS ABOUT A PROBLEM, NOT ABOUT A STORED WORD.
//
// "i see that my every live listing shows a red or orange dots on them, donot
//  set the status to review when there is no problem in it ... if there is no
//  flag no need to highlight, if there is a api error than it should show that
//  dot"
//
// It coloured straight off r.status, which is what the app STORED at some point
// -- so a listing that went live on Amazon months ago, but whose row still says
// API_ERROR from a failed attempt before that, showed a red dot for ever. The
// counts along the top already reclassify those as LIVE (see summary()); the dot
// did not, so the tiles and the counts disagreed and every live listing looked
// like it needed attention.
//
// Now: a listing Amazon confirms is live has no problem to report unless
// something actually flags it -- a compliance document demand, an IP risk, a
// claim risk. Those checks already run; the dot follows them instead of
// second-guessing with a stale status.
// ============ THREE FACTS EVERY CARD SHOWS, WRITTEN ONCE ============
//
// The tile and the table row are two views of ONE listing, and they had drifted
// into disagreeing about it: the row showed a handling time and the tile showed
// none; both showed a brand only when the row happened to carry one; and the
// price was read-only in both, editable only through a separate button.
//
// These three build the price, brand and handling cells for BOTH views, so a
// listing cannot read differently depending on which button you last pressed.

/* THE PRICE IS THE CONTROL.
 *
 *     "make the selling price being able to be changed by just clicking on it
 *      and then on save"
 *
 * Clicking the price opens the price panel (priceedit.js) with the figure
 * selected and the caret in it -- type, press the button, done.
 *
 * WHY THE PANEL AND NOT AN EDITABLE BOX IN THE CARD. That panel is not a
 * wrapper around "send this number to Amazon". It is the only place that knows
 * the floor price, that shows what the sale would actually leave once fees are
 * out, and -- the one that matters -- that names the account and marketplace on
 * the request. Without that name the server falls back to a process-wide "which
 * account is open" variable, and the comment above _peScope() records where
 * that went: a price could be sent to the WRONG SELLER ACCOUNT, a real change on
 * a real shopfront. An in-card input would be a second, thinner path to the same
 * endpoint with none of that (rule 12). So the click is the shortcut; the panel
 * is still the thing that sends.
 *
 * Only live listings can be repriced -- a draft has no price on Amazon to
 * change -- so a draft's price is shown plain. */
/* liveOverride: a tile built straight from Amazon's catalogue is live by
   definition and has no app row for isAmazonLive() to read -- the same reason
   rowActions takes {live:true}. */
function _priceCell(r, cls, liveOverride){
  const raw = r && r.price ? String(r.price) : "";
  const txt = raw ? `${CUR_SYMBOL}${esc(raw.replace(/^[A-Z]{3}\s?/,''))}` : "";
  const live = liveOverride === undefined ? isAmazonLive(r) : !!liveOverride;
  if(!txt) return live
    ? `<span class="${cls} cc" title="No price recorded for this listing">—</span>`
    : `<span></span>`;
  if(!live) return `<span class="${cls}" title="This listing is not live on Amazon, so there is no selling price to change yet">${txt}</span>`;
  const n = Number(raw.replace(/[^0-9.]/g,'')) || 0;
  return `<span class="${cls} pricehot" title="Click to change this selling price on Amazon"
      onclick="event.stopPropagation();priceEdit(${jsArg(r.sku)},${n},${jsArg(r.title||'')})">${txt}<i class="ti ti-pencil"></i></span>`;
}

/* THE BRAND, ALWAYS.
 *
 *     "some shows the brand name and some do not show the brand name, i want
 *      the brand name to be displayed in all"
 *
 * A blank used to mean "the row does not name a brand", which reads as "this
 * listing has no brand" -- and no listing this app makes is unbranded. rowBrand()
 * (brand.js) falls back to the account's own brand, which is what the server
 * will actually send, and says which of the two it gave us so the card can show
 * a fallback as a fallback.
 *
 * The third case is the one worth seeing: the row names a brand this account is
 * not registered for. That is not hidden and not silently corrected here -- it
 * is marked, and the server decides on submit. */
function _brandCell(r){
  const b = (typeof rowBrand === "function") ? rowBrand(r) : {name:(r&&r.brand)||"", from:"row", ours:true};
  if(!b.name) return `<span class="tilefact cc" title="No brand on this row and no brand set on this account. Set one in Account settings — Amazon will not take a listing without it.">no brand</span>`;
  if(b.from === "account")
    return `<span class="tilefact brandfact cc" title="This row does not name a brand, so this account's own brand is what will be sent."><i class="ti ti-tag"></i> ${esc(b.name)} <span class="cc">(account default)</span></span>`;
  if(!b.ours)
    return `<span class="tilefact brandfact" style="color:var(--warn)" title="This account is not registered for &quot;${esc(b.name)}&quot;. If Amazon has approved it, add it in Account settings — otherwise the account's own brand will be sent instead."><i class="ti ti-tag"></i> ${esc(b.name)} <i class="ti ti-alert-triangle"></i></span>`;
  return `<span class="tilefact brandfact"><i class="ti ti-tag"></i> ${esc(b.name)}</span>`;
}

/* THE HANDLING TIME THE BUYER IS ACTUALLY PROMISED.
 *
 *     "reflect true handling time in front of the listings"
 *
 * Two different numbers have lived in these rows. handling_days is what the app
 * holds for a draft -- what we INTEND to promise. handling_time comes back from
 * Amazon on a live listing -- what the shopfront is promising RIGHT NOW. When a
 * listing is live, Amazon's number is the true one and ours is a plan, so the
 * live number wins and the card says where it came from. The old code took
 * whichever was set first (handling_days || handling_time) and labelled neither,
 * so a stale draft value could sit in front of a live listing looking like fact.
 */
function _handCell(r, liveOverride){
  if(!r) return "";
  const live  = liveOverride === undefined ? isAmazonLive(r) : !!liveOverride;
  // WHERE AMAZON'S NUMBER ACTUALLY LIVES.
  //
  // Measured on jack_uk: all 47 live rows printed "2d (ours)". The app row
  // carries handling_days (what we hold) and almost never handling_time --
  // Amazon's figure arrives on the CATALOGUE item, which is a different object.
  // So the honest-but-useless answer "ours" was the only one this could ever
  // give for a draft row, even with Amazon's real number already in memory two
  // objects away.
  //
  // liveItemForRow() is the existing SKU-then-ASIN match between an app row and
  // its catalogue entry -- the same one the status tiles use, so the handling
  // time and the live/not-live badge are decided from the same pairing (rule
  // 12). liveOverride means the caller already IS a catalogue item, so there is
  // nothing to look up.
  let fromAmazon = r.handling_time;
  if(live && (fromAmazon === undefined || fromAmazon === null || fromAmazon === "")
     && liveOverride === undefined && typeof liveItemForRow === "function"){
    const _it = liveItemForRow(r);
    if(_it && _it.handling !== undefined && _it.handling !== null && _it.handling !== "")
      fromAmazon = _it.handling;
  }
  const ours = r.handling_days;
  const n = live ? (fromAmazon != null && fromAmazon !== "" ? fromAmazon : ours)
                 : (ours != null && ours !== "" ? ours : fromAmazon);
  if(n === null || n === undefined || n === "")
    return `<span class="tilefact cc" title="No handling time recorded. Amazon falls back to the account's default.">no handling time</span>`;
  const isAmazons = live && fromAmazon != null && fromAmazon !== "";
  // WHEN THE TWO NUMBERS DISAGREE, SAY SO.
  //
  // This is the case worth seeing, and it is real: sampled three live SKUs
  // through getListingsItem and Amazon held lead_time_to_ship_max_days = 2 on
  // all three -- including one whose SKU is named 5Days and one named 3Days.
  // The SKU's day label records what was INTENDED when it was created; it is
  // not what the shopfront promises, and nothing had ever compared them. A
  // listing promising buyers two days while the plan says five is a late
  // dispatch and a metric hit, and it was invisible.
  const _mine = (ours === null || ours === undefined || ours === "") ? null : Number(ours);
  const _amz  = isAmazons ? Number(fromAmazon) : null;
  const clash = _mine !== null && _amz !== null && !isNaN(_mine) && !isNaN(_amz) && _mine !== _amz;
  if(clash)
    return `<span class="tilefact" style="color:var(--warn)"
      title="Amazon is promising buyers ${esc(String(_amz))} day(s) for this listing, but this app holds ${esc(String(_mine))}. Amazon's number is what buyers see and what late-dispatch is measured against. Change it on the listing, or correct it here, so the two agree."
      ><i class="ti ti-clock"></i> ${esc(String(_amz))}d <i class="ti ti-alert-triangle"></i> <span class="cc">(we hold ${esc(String(_mine))}d)</span></span>`;
  const tip = isAmazons
    ? "Amazon's own handling time for this live listing — what buyers are being promised now."
    : (live ? "This account's recorded handling time. Amazon did not report one for this listing."
            : "The handling time this draft will be sent with.");
  return `<span class="tilefact${isAmazons?' handlive':''}" title="${tip}"><i class="ti ti-clock"></i> ${esc(String(n))}d${isAmazons?'':' <span class="cc">(ours)</span>'}</span>`;
}

// PPC_BY_ASIN ... _econLine: moved to static/js/listings_ppc.js (Milestone 4), loaded right after this file.
// _queuedChip ... card: moved to static/js/listings_grid.js (Milestone 4), loaded right after this file.
// _marketIsUS ... _dwVerdictTag: moved to static/js/listings_drawer_build.js (Milestone 4), loaded right after this file.
/* WHERE THE OLD DRAWER HEADER WENT.
 *
 * The .dwhead / .dwbar / .dwseg / .dwactions block that used to be built here
 * has been replaced by _dwShell above. Nothing it offered was removed -- it
 * was redistributed:
 *
 *   Preview, Auto-fix, Submit   the sticky FOOTER, and the first three icons
 *                               in the sticky header.
 *   Approve / Hold              two header icons that LIGHT UP to show which
 *                               value is already set. The old segmented
 *                               control existed for the same reason and said
 *                               the same thing; the status pill it sat beside
 *                               is now the badge at the far left of the bar,
 *                               so the real status is still always on screen
 *                               even when it is one of the 89 rows that is
 *                               neither APPROVED nor NEEDS_REVIEW.
 *   More                        unchanged, still opens drawerMore().
 *   Image Studio, Optimize,     the foot of the scrolling body -- they are
 *   Ask Claude                  things you go and do, not things you reach
 *                               for mid-edit.
 *   Minimal mode                its own labelled setting row under the
 *                               metrics. It is a SETTING, and it was the one
 *                               control nobody could find among the buttons.
 *   A+ content, the Amazon      folded, each with its verdict on the closed
 *   mirror, restricted, docs,   summary (see dwFold).
 *   claims, Amazon feedback
 *   The blocking banners        NOT folded. identifierPanel() and
 *                               complianceBanner() are drawn open, above the
 *                               hero -- a barcode clash has to be reported
 *                               (CLAUDE.md Rule 1), not filed.
 */

// Clicking a metric tile filters the list. It also moves the status dropdown to
// match: two controls driving one filter that disagree about its value is worse
// than having only one of them.
function metricFilter(v){
  // CLICKING THE LIT TILE PUTS IT OUT.
  //
  //     "Clicking an active filter should deselect it and show all items.
  //      Currently clicking a filter works but clicking it again doesn't
  //      clear it."
  //
  // It only ever SET the filter, so pressing the tile you were already on
  // re-set the same value: the list did not change and the border stayed on,
  // leaving the dropdown as the only way back to everything. A tile that
  // lights up is reporting a state, and a control that reports a state has to
  // be able to leave it.
  //
  // Pressing a DIFFERENT tile still just switches, which is why this tests the
  // clicked value against the current one rather than toggling blindly.
  const cur = (typeof FILTER !== "undefined") ? FILTER : "all";
  const next = (String(v) === String(cur)) ? neutralFilter() : v;
  const sel = document.getElementById("statussel");
  if(sel) sel.value = next;
  if(typeof setFilterVal === "function") setFilterVal(next);
}

// ===================== TABLE VIEW =====================================
// Orbit shows listings as a data table, not a card grid. Both exist: table is
// the default, the tile grid is one click away, and card() is untouched.
//
// The preference is per-browser (localStorage), not per-account: it is a
// preference about how YOU read a list, not a property of the workspace.

let LIST_VIEW = "table";
try{ LIST_VIEW = localStorage.getItem("alta_list_view") || "table"; }catch(e){}

/* WHICH VIEW IS ACTUALLY DRAWABLE RIGHT NOW.
 *
 * "detailed" needs listrow_detailed.js, which is a separate file. Checked HERE,
 * at render time, rather than where LIST_VIEW is read on load: that runs while
 * listings.js is still evaluating and the other file has not been parsed yet,
 * so a load-time check would downgrade every session to the table view.
 *
 * The stored preference is left alone -- a failed script load should not also
 * erase what the person chose. */
function listViewNow(){
  if(LIST_VIEW === "detailed" && typeof detailedBlock !== "function") return "table";
  return LIST_VIEW;
}

// Sync the DOM to whatever LIST_VIEW currently is. Separate from setListView()
// so it can run on page load without triggering a render before there are any
// rows to draw.
function applyListView(){
  const view = listViewNow();
  document.querySelectorAll("#viewtoggle button").forEach(function(b){
    b.classList.toggle("on", b.dataset.view === view);
  });
  const g = document.getElementById("grid");
  // `tableview` is the card grid's OFF switch, so the detailed view -- which is
  // also not a grid of cards -- needs it too. Without this the detailed rows
  // would be laid out by the tile grid's CSS and stack into columns.
  if(g){
    g.classList.toggle("tableview", view === "table" || view === "detailed");
    g.classList.toggle("detailedview", view === "detailed");
  }
}

// THREE VIEWS NOW. "detailed" is the Amazon Manage-All-Inventory row
// (static/js/listrow_detailed.js) -- an ADDITIONAL view, not a replacement:
// table stays the default and the card grid is untouched.
//
// An unknown value falls back to "table" rather than being stored, so a
// localStorage entry left by an older build (or a typo in a link) cannot
// strand somebody on a view that does not draw.
function setListView(v){
  LIST_VIEW = (v === "grid") ? "grid"
            : (v === "detailed" && typeof detailedBlock === "function") ? "detailed"
            : "table";
  try{ localStorage.setItem("alta_list_view", LIST_VIEW); }catch(e){}
  applyListView();
  if(typeof render === "function") render();
}

// The top-bar health badge. Wired to /healthz so it reports something REAL --
// can the browser still reach the server? A badge that always reads "healthy"
// is decoration, and worse than nothing, because it looks like a check.
async function pollHealth(){
  const el = document.getElementById("healthbadge");
  const t  = document.getElementById("healthtxt");
  if(!el) return;
  try{
    const r = await fetch("/healthz", {cache:"no-store"});
    const ok = r.ok;
    el.classList.toggle("bad", !ok);
    // "App running", NOT "System healthy". What this measures is one thing:
    // /healthz answered, so this Flask process is alive. It says nothing about
    // whether Amazon is answering -- and on the day this was written Amazon was
    // refusing both the Orders API and the A+ Content API for jack_uk while the
    // badge sat in the corner of every screen saying the system was healthy.
    //
    // A badge that overstates what it checked is worse than no badge, because
    // it is consulted exactly when somebody suspects something is wrong.
    if(t) t.textContent = ok ? "App running" : "Server error";
  }catch(e){
    el.classList.add("bad");
    if(t) t.textContent = "Server unreachable";
  }
}

window.addEventListener("DOMContentLoaded", function(){
  applyListView();
  pollHealth();
  // Not while the tab is hidden (poller.js altaEvery, Milestone 11).
  (typeof altaEvery === "function" ? altaEvery : setInterval)(pollHealth, 60000);
});

// rowSelectBox ... liveTableRow: moved to static/js/listings_rows.js (Milestone 4), loaded right after this file.
// identifierPanel ... applyRewrite: moved to static/js/listings_panels.js (Milestone 4), loaded right after this file.
// openListing ... uploadRef: moved to static/js/listings_open.js (Milestone 4), loaded right after this file.