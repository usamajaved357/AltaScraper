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

function toggleSelect(sku, on){
  if(on) SELECTED.add(String(sku)); else SELECTED.delete(String(sku));
  // EVERY ELEMENT FOR THIS SKU, in whichever view is on screen. Both the card
  // and the table row carry data-sku, so one lookup serves both and a tick
  // looks like a tick either way.
  //
  // This looked for '.lcard', a class that does not exist anywhere in the app
  // -- cards are '.tile' -- so it had never matched and ticking a card only
  // appeared to work because something else redrew the list afterwards.
  document.querySelectorAll('[data-sku="' + CSS.escape(String(sku)) + '"]')
    .forEach(function(el){
      if(el.classList.contains("tile")) el.classList.toggle("sel", on);
      if(el.tagName === "TR") el.classList.toggle("rowon", on);
      const box = el.querySelector('input[type=checkbox]');
      if(box) box.checked = on;
    });
  updateSelBar();
}
/* WHAT IS ACTUALLY ON SCREEN, asked of the screen.
 *
 *     "i am not able to select all the listings by clicking on that white
 *      button ... only 2 listings are allowed to be selected when i select the
 *      live on amazon tab"
 *
 * Both of those are one bug. selectAllVisible walked ROWS -- the listings this
 * app holds -- while the Live on Amazon tab draws TWO collections: the app rows
 * Amazon confirmed, and LIVE_ITEMS, which is Amazon's own catalogue and is most
 * of that view. On the account this was reported from, two rows were in both
 * and everything else existed only in the catalogue, so "Select all" ticked
 * two listings out of a screenful and looked broken.
 *
 * Re-deriving the list here is what caused it: render() decides what to draw
 * from LIST_SOURCE, the filter, the dedupe between the two collections and the
 * live/claimed/gone split, and any second attempt at that answer is a copy that
 * can disagree -- and did. So this ASKS THE GRID. Every selectable listing is
 * drawn with a data-sku, whichever collection it came from, so reading them
 * back cannot drift from what a person can see.
 */
function visibleSelectableSkus(){
  const out = [], seen = new Set();
  document.querySelectorAll('#grid [data-sku]').forEach(function(el){
    // Only things that offer a tick. A container may carry data-sku for the
    // drawer without being selectable.
    if(!el.querySelector('input[type=checkbox]')) return;
    const s = String(el.getAttribute('data-sku') || "").trim();
    if(s && !seen.has(s)){ seen.add(s); out.push(s); }
  });
  return out;
}

function selectAllVisible(on){
  const skus = visibleSelectableSkus();
  // NOTHING DRAWN YET is not the same as nothing to select, and silently doing
  // nothing is exactly how this read as a dead button before.
  if(!skus.length){
    if(on && typeof toast === "function"){
      toast("Nothing on screen to select yet — let the list finish loading.");
    }
    return;
  }
  skus.forEach(function(s){
    if(on) SELECTED.add(s); else SELECTED.delete(s);
  });
  render(); updateSelBar();
}
function clearSelection(){ SELECTED.clear(); render(); updateSelBar(); }
function updateSelBar(){
  const bar=document.getElementById('selbar'); if(!bar) return;
  const n=SELECTED.size;
  bar.style.display = n? 'flex':'none';
  const cnt=document.getElementById('selcount'); if(cnt) cnt.textContent=n+' selected';
}
function selectedSkus(){ return Array.from(SELECTED); }

/* WHICH OF THESE HAS A DRAFT HERE, AND WHICH IS ONLY ON AMAZON.
 *
 * The Live view mixes two kinds of listing and always has: rows this app holds
 * a draft of, and rows that exist only in Amazon's catalogue. Until now only
 * the first kind could be ticked, so the question never came up.
 *
 * It comes up the moment both can be ticked. The bulk bar holds two families of
 * action and they want opposite halves of the selection:
 *
 *   about the DRAFT      Approve, Hold, Delete, Auto-fix, Regenerate copy
 *   about the LISTING    handling time, stock, price -- Amazon is the only place
 *                        these exist, so an Amazon-only row is a fine target
 *
 * Without this split a draft action posts every catalogue SKU to a route that
 * cannot find it and reports "46 failed" -- which reads as a broken app rather
 * than as forty-six listings that were never drafts. Nothing is destroyed by it
 * (/approve and /delete both answer "row not found"), but the message is a lie
 * about what happened.
 *
 * ONE DEFINITION, called by all of them (CLAUDE.md Rule 12). ROWS is the app's
 * own list, which is exactly what "holds a draft of" means.
 */
function splitByDraft(skus){
  const have = new Set((typeof ROWS !== "undefined" && ROWS ? ROWS : [])
                       .map(r => String(r.sku || "").trim()).filter(Boolean));
  const drafts = [], amazonOnly = [];
  (skus || []).forEach(function(s){
    (have.has(String(s).trim()) ? drafts : amazonOnly).push(s);
  });
  return {drafts: drafts, amazonOnly: amazonOnly};
}

/* The sentence a draft action shows when part of the selection was not a draft.
 * Written once so all four say the same thing, and returns "" when there is
 * nothing to say -- the ordinary all-drafts case stays silent.
 */
function _draftOnlyNote(amazonOnly, verb){
  if(!amazonOnly.length) return "";
  return `\n\n${amazonOnly.length} of them are on Amazon but have no draft here, `
       + `so there is nothing to ${verb}. They will be left alone.\n`
       + `(Press Sync to pull a listing in as a draft first.)`;
}

async function batchGenerate(kind){
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  // Batch COPY regeneration runs through the generator with a --skus filter.
  // If your generator build doesn't have --skus yet, it will report that.
  if(!await uiConfirm("Regenerate listing copy for "+skus.length+" selected SKU(s)?\nThis reruns the generator scoped to just these SKUs.")) return;
  navTo("generate");
  const log=document.getElementById("log"); if(log){ log.style.display="block"; log.textContent="Starting regeneration for "+skus.length+" SKU(s)…\n"; }
  try{
    const es=new EventSource("/run/regen?skus="+encodeURIComponent(skus.join(",")));
    es.onmessage=e=>{ if(log){ log.textContent+=e.data+"\n"; log.scrollTop=log.scrollHeight; } };
    es.addEventListener("end",()=>{ es.close(); showStop(false); loadRows(); toast("Regeneration finished"); });
    showStop(true);
  }catch(e){ toast("Could not start: "+e); }
}

async function batchAutoGenerate(kind){
  // Bulk one-click: strategize + generate in the BACKGROUND. Does NOT open the
  // studio — the floating status bar shows progress, results auto-save to each
  // product's media library, and it keeps running on any page. kind defaults to
  // 'secondary'; pass 'aplus' for the A+ button.
  kind=kind||"secondary";
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  const per=(kind==="aplus")?7:7; // 7 secondary or up to 7 A+ modules
  const n=skus.length;
  if(!await uiConfirm("Auto-generate "+(kind==="aplus"?"A+ modules":"secondary images")+" for "+n+
              " product"+(n>1?"s":"")+" (~"+(n*per)+" images). The strategist proposes ideas and "+
              "generates them all in the background. You can keep working. Continue?")) return;

  const liveSel = (LIST_SOURCE==='live' || LIST_SOURCE==='all');
  toast("Designing concepts for each product…");
  // Strategize SEPARATELY for EACH product using its own reference image, so
  // every product gets concepts tailored to ITSELF — no shared/mixed set.
  let jobs=[];
  let skipped=[];
  for(let si=0; si<skus.length; si++){
    const sku=skus[si];
    const it=_itemForSku(sku);
    const ref=_refImgForItem(it);
    if(!ref){ skipped.push(sku); continue; }
    let concepts=[];
    try{
      const sj=await (await fetch("/genimage/strategize",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({product_image:ref,
          product_images:(typeof _refCandidates==="function"?_refCandidates(it):[ref]),
          title:(it&&it.title)||"", kind:kind,
          n:per, text_provider:(window.AI_TEXT||null)})})).json();
      if(!sj.ok){ toast("Strategist failed for "+sku+": "+(sj.error||"unknown")); continue; }
      concepts=sj.concepts||[];
    }catch(e){ toast("Strategist error for "+sku+": "+e); continue; }
    if(!concepts.length){ continue; }
    const asin=liveSel?_asinForSku(sku):"";
    concepts.forEach((c,ci)=>{
      const code=(kind==="aplus")
        ? ("APLUS"+String(ci+1).padStart(2,"0"))
        : ("PT"+String(ci+1).padStart(2,"0"));
      jobs.push({sku:sku, ref:ref, label:sku+" · "+(c.title||code),
        asin:asin, img_code:code,
        payload:{ product_image:ref, title:(it&&it.title)||"", kind:kind,
          concept:c.concept||"", art_direction:c.art_direction||"",
          fidelity:"high", tier:"basic",
          text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null) }});
    });
  }
  if(skipped.length){ toast(skipped.length+" product(s) skipped — no reference image: "+skipped.join(", ")); }
  if(!jobs.length){ toast("Nothing to generate — no products had reference images or concepts."); return; }

  // 3) submit as a background batch — no studio window, status bar tracks it
  try{
    const r=await (await fetch("/genimage/start_batch",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kind:"concept", jobs:jobs, label:(kind==="aplus"?"A+ ":"Secondary ")+"× "+n+" product"+(n>1?"s":"")})})).json();
    if(!r.ok){ toast("Could not start: "+(r.error||"unknown")); return; }
    GEN_ACTIVE_JOB=r.job;
    toast("Started "+jobs.length+" image(s) in the background.");
    openGenPanel();
    startGenStatusPoll();
  }catch(e){ toast("Error: "+e); }
}
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
    host.style.cssText="position:fixed;right:18px;bottom:18px;width:340px;max-height:70vh;overflow:auto;background:var(--card,#0f1722);border:1px solid var(--line,#22304a);border-radius:12px;padding:14px;z-index:9999;box-shadow:0 10px 40px rgba(0,0,0,.5)";
    document.body.appendChild(host);
  }
  const note = live
    ? "These are generated as a shared set. Download each, then upload to your live listings via Amazon → Manage Images (live listings can't be image-updated automatically)."
    : "Applied to the selected draft SKUs and saved to "+storeName()+".";
  host.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
    + '<b style="font-size:13px">Secondary images ('+images.length+')</b>'
    + '<button onclick="document.getElementById(\'secresults\').remove()" style="background:none;border:none;color:var(--accent2);cursor:pointer;font-size:16px">✕</button></div>'
    + '<div style="font-size:11px;color:var(--ink2);margin-bottom:10px">'+note+'</div>'
    + images.map((u,i)=>'<div style="margin-bottom:10px"><img src="'+u+'" style="width:100%;border-radius:8px;border:1px solid var(--line,#22304a)"><a href="#" onclick="_downloadAsJpeg(\''+u+'\',\'secondary_'+(i+1)+'\');return false;" style="display:inline-block;margin-top:4px;font-size:12px;color:var(--accent2)">⬇ Download image '+(i+1)+'</a></div>').join("");
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
        const hl=esc(v).replace(re,'<mark style="background:var(--warn-line);color:#ffe9a8">$1</mark>');
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

function esc(s){return (s==null?"":String(s)).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}

/* A stored cell that reads exactly "None" is a Python None that was written
   out as four characters, not something anyone typed. There are 361 of them in
   this database -- 193 in compliance notes, 168 in the VOC source -- and every
   one of them gets shown, concatenated, or searched as though it meant
   something. It is what made the IP panel say "forbidden phrase — compatible
   with None".
   ONLY when it is the whole value: a note that genuinely reads "None — operates
   at 240 V AC mains" is a real sentence and must survive. */
function _noneless(v){
  const s = String(v == null ? "" : v).trim();
  return /^(none|null|nan|undefined)$/i.test(s) ? "" : String(v == null ? "" : v);
}
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");
  clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove("show"),1800);}

function badgeClass(s){return ["APPROVED","NEEDS_REVIEW","IP_HOLD","COMPLIANCE_HOLD","ERROR","API_READY","API_ERROR","LIVE","PARENT"].includes(s)?("b-"+s):"b-none";}
/* TWO DIFFERENT THINGS STOP A LISTING, and they are not fixed the same way.
 *
 *   BLOCKED  -- this app's own IP or compliance check stopped it BEFORE
 *               anything was sent. Nothing has reached Amazon. You fix it by
 *               changing a rule or the listing, then re-scanning.
 *   REFUSED  -- it WAS sent and Amazon rejected it. Amazon has said something
 *               specific about it, and that message is what you act on.
 *
 * The screen already tells them apart in words ("held by a compliance or IP
 * check" vs "listings Amazon refused") and then sent BOTH counts to the same
 * filter, which is isHold -- the union. So clicking "3 listings Amazon
 * refused" showed those 3 plus all 25 compliance holds: a number you click
 * that does not show you that number, which is the same complaint that got the
 * live tiles fixed ("clicking only 1 button draws a border on all 3").
 *
 * isHold stays as the union, because the "Blocked or errored" tile genuinely
 * wants both and several callers rely on it. The two halves are now nameable
 * separately, from one definition each (rule 12). */
function isRefusedByAmazon(s){ return s==="ERROR"||s==="API_ERROR"; }
function isBlockedByOurChecks(s){ return s==="IP_HOLD"||s==="COMPLIANCE_HOLD"; }
function isHold(s){ return isBlockedByOurChecks(s) || isRefusedByAmazon(s); }

// GONE: the sheet-tab filter. A spreadsheet had tabs and this let you look at
// one of them; the app's own database does not, and there is nothing left for
// this to filter. Reported twice -- "why do i still see tabs in the listings
// page when i am not using any sheets", then "i still see tabs displayed at the
// header of the screen in listings".
//
// It was already hidden whenever fewer than two tabs came back, which is why it
// did not show on a clean account -- but any row still carrying a tab_gid from
// the spreadsheet era brought the whole strip back. Hidden-unless is not gone.
function tabPass(r){ return true; }             // kept: still called from a card path
// FIND ONE LISTING BY WHAT IS PRINTED ON IT.
//
//     "let me search the listing using the sku, asin, or a ean used in it in
//      the app"
//
// There was a status filter and no way to find a single product at all. On an
// account with 85 listings the only way to reach one was to scroll, and the
// three things you actually have in your hand when you go looking are its SKU
// (off a label), its ASIN (off Seller Central) or its barcode (off the box).
//
// The SKU carries the competitor ASIN inside it (price_days_ASIN), so searching
// an ASIN finds both the listing whose own ASIN it is AND any listing built
// from it as a reference. That is a feature, not a collision: they are both
// answers to "show me the thing to do with B0XXXXXXXX".
let SEARCH_Q = "";

function _sq(v){ return String(v == null ? "" : v).toLowerCase(); }

function matchesSearch(r){
  const q = SEARCH_Q.trim().toLowerCase();
  if(!q) return true;
  // Digits only for the barcode, so "5060 5415 10005" off a box finds the
  // listing that stores it as 5060541510005.
  const qDigits = q.replace(/\D/g, "");
  const fields = [r.sku, r.asin, r.competitor_asin, r.upc, r.title,
                  r.model_number, r.source_url];
  for(const f of fields){
    if(!f) continue;
    const s = _sq(f);
    if(s.indexOf(q) >= 0) return true;
    if(qDigits.length >= 6 && s.replace(/\D/g, "").indexOf(qDigits) >= 0) return true;
  }
  // EVERY WORD SOMEWHERE, IN ANY ORDER.
  //
  // The title search above is a strict substring, so it finds a product only
  // if you type the words in the order Amazon happens to have them in. "garden
  // hose 50ft" finds the hose; "50ft garden hose" finds nothing, and there is
  // no way to tell from the outside which one you guessed.
  //
  // Nobody remembers a title word for word. They remember two or three words
  // about the thing. So a multi-word search matches when EVERY word appears
  // somewhere in the listing -- which is strict enough that two words still
  // narrow 85 listings to one or two, and forgiving enough that the order does
  // not have to be right.
  //
  // Single words are left to the substring pass above, deliberately: it
  // already matches inside a word ("fol" finds Folding and Foldable), and this
  // pass would not add anything.
  const words = q.split(/\s+/).filter(w => w.length > 1);
  if(words.length > 1){
    const hay = fields.map(_sq).join(" ");
    if(words.every(w => hay.indexOf(w) >= 0)) return true;
  }
  // The attributes blob, so an EAN stored only inside the payload is still
  // findable -- that is where a barcode ends up once a listing is built.
  if(qDigits.length >= 6){
    try{
      const blob = String(r.attributes_json || r["Attributes JSON"] || "");
      if(blob && blob.replace(/\D/g, "").indexOf(qDigits) >= 0) return true;
    }catch(e){}
  }
  return false;
}

function setSearch(v){
  SEARCH_Q = v || "";
  render();
}

/* WHAT A LIVE TILE MEANS, in one place.
 *
 * Read by the tile that COUNTS them and by the filter that HIDES the rest, so
 * a tile saying 9 cannot then show 40. Takes an item from the Amazon catalogue
 * (LIVE_ITEMS), which is where status, quantity and cost actually live -- a
 * draft row does not know whether Amazon is showing the listing. */
function liveItemIs(it, filter){
  if(!it) return false;
  if(filter === "live_all") return true;
  if(filter === "live_notshowing"){
    // "inactive" contains "active", so the negative has to be tested for
    // rather than inferred from the absence of the positive.
    const s = String(it.status || "").toLowerCase();
    return s.indexOf("inactive") >= 0 || s.indexOf("suppress") >= 0
        || s.indexOf("incomplete") >= 0;
  }
  if(filter === "live_nocost") return !(it.cogs || (it.profit && it.profit.cogs));
  if(filter === "live_oos"){
    const q = it.qty;
    // Unknown is not zero. A listing whose quantity Amazon did not report is
    // not out of stock, and counting it as such is how a "9 out of stock"
    // tile becomes a reorder decision.
    return q !== undefined && q !== null && q !== "" && Number(q) === 0;
  }
  return true;
}

/* The catalogue item behind an app row, matched by SKU first and only then by
 * ASIN -- two SKUs can share an ASIN, and there the SKU is the listing. */
function liveItemForRow(r){
  if(typeof LIVE_ITEMS === "undefined" || !LIVE_ITEMS) return null;
  const n = v => String(v == null ? "" : v).trim().toUpperCase();
  // Competitor reference excluded -- see _matchableAsin. This pairs an app row
  // with Amazon's own entry for it, and the pairing feeds the handling time and
  // the status tiles, so matching on the competitor's ASIN would attach another
  // seller's listing data to our row.
  const s = n(r && r.sku), a = _matchableAsin(r);
  let byAsin = null;
  for(const it of LIVE_ITEMS){
    if(!it) continue;
    if(s && n(it.sku) === s) return it;
    if(a && !byAsin && n(it.asin) === a) byAsin = it;
  }
  return byAsin;
}

/* SHOW A CHANGE THAT HAS ALREADY HAPPENED, without refetching the list.
 *
 *     "After any bulk action completes, optimistically update the affected
 *      rows immediately. If handling time was set to 2d, the column shows 2d
 *      right away -- no manual refresh needed."
 *
 * The bulk actions used to end with loadRows(), which re-reads every listing in
 * the account plus Amazon's catalogue -- seconds of skeletons to redraw a
 * column that already knew its own answer, and on a slow account it looked
 * like the change had not been made.
 *
 * THIS IS NOT A GUESS AT WHAT THE SERVER WILL SAY. Callers pass only the SKUs
 * the server reported as done, so what is written here is what already
 * happened, not what was requested. A refresh or a Sync still refetches and
 * still wins -- see loadRows -- so if any of this is ever wrong, it is wrong
 * until the next read and no further.
 *
 * The two patches are separate because the row and the catalogue item are
 * separate objects holding separate facts: the row is what WE record, the item
 * is what AMAZON holds. _handlingCell compares them and warns when they
 * disagree, which only works if a caller can write one without the other.
 */
function applyPushedLocally(skus, rowPatch, itemPatch){
  const n = v => String(v == null ? "" : v).trim().toUpperCase();
  const want = new Set((skus||[]).map(n).filter(Boolean));
  if(!want.size) return;
  if(rowPatch && typeof ROWS !== "undefined" && ROWS)
    ROWS.forEach(r => { if(r && want.has(n(r.sku))) Object.assign(r, rowPatch); });
  if(itemPatch && typeof LIVE_ITEMS !== "undefined" && LIVE_ITEMS)
    LIVE_ITEMS.forEach(it => { if(it && want.has(n(it.sku))) Object.assign(it, itemPatch); });
  if(typeof render === "function") render();
}

/* WHICH OF THE TWO TILE SETS IS ON SCREEN, and what "no filter" means in it.
 *
 * Written out twice before -- once in summary() to choose the tiles, and
 * nowhere at all in metricFilter(), which is how the toggle below came to have
 * no idea what to fall back TO. The Drafts view's "show everything" is "all";
 * the Live view's is "live_all", because passFilter treats any FILTER starting
 * "live_" as a question about the catalogue item behind the row. Using "all"
 * there would clear the highlight off the Live tile as well, which is not what
 * clearing a sub-filter means.
 *
 * One definition, both callers (CLAUDE.md Rule 12).
 */
function draftsView(){
  return (LIST_SOURCE !== "live" && LIST_SOURCE !== "all");
}
function neutralFilter(){
  return draftsView() ? "all" : "live_all";
}

function passFilter(r){
  if(!matchesSearch(r)) return false;
  if(DUP_ONLY && !isDuplicate(r)) return false; // "Duplicates only" toggle
  if(FILTER==="all")return true;
  if(FILTER==="review")return r.status==="NEEDS_REVIEW";
  if(FILTER==="holds")return isHold(r.status);          // both, for the tile
  // ...and each half on its own, so the two counts that are worded differently
  // can be clicked separately. See isHold above.
  if(FILTER==="refused")return isRefusedByAmazon(r.status);
  if(FILTER==="blocked")return isBlockedByOurChecks(r.status);
  if(FILTER==="approved")return r.status==="APPROVED"||r.status==="API_READY";
  if(FILTER==="live")return r.status==="LIVE";
  // THE FOUR STATUSES. Asked of liststatus.js, not tested here, so the tile
  // that COUNTS them and the filter that HIDES the rest cannot disagree.
  if(FILTER==="queued")return (typeof lsIsQueued==="function") && lsIsQueued(r);
  if(FILTER==="submitted")return (typeof lsSaysSubmitted==="function")
                                 && lsSaysSubmitted(r);
  if(FILTER==="generated"){
    // The old statuses count as generated too, so an unmigrated database still
    // shows its rows under the tile that claims to be counting them.
    if((typeof lsIsGenerated==="function") && lsIsGenerated(r)) return true;
    return ["NEEDS_REVIEW","APPROVED","API_READY","IP_HOLD","COMPLIANCE_HOLD",
            "ERROR","API_ERROR"].indexOf(String(r.status||"").toUpperCase()) >= 0;
  }
  // Listings carrying at least one warning, whatever their status.
  if(FILTER==="warned")return (typeof lsWarnings==="function")
                              && lsWarnings(r).n > 0;
  // The live-view tiles. An app row is judged by the CATALOGUE item behind it,
  // for the same reason the tiles count catalogue items: whether Amazon is
  // showing a listing, and how many it has, are facts about the listing rather
  // than about our draft of it. A row with no catalogue item behind it cannot
  // satisfy a question about the live listing, so it is hidden rather than
  // shown on the grounds that nothing is known.
  if(String(FILTER).indexOf("live_") === 0){
    if(FILTER === "live_all") return true;
    return liveItemIs(liveItemForRow(r), FILTER);
  }
  return true;
}

// The strip under the toolbar. It used to be the sheet's tabs plus a duplicates
// toggle; the tabs are gone with the spreadsheet, and the duplicates toggle --
// which has nothing to do with sheets and is how you find the extra copies of a
// SKU to delete -- stays. Called from summary() each render.
function renderTabFilter(){
  const host=document.getElementById("tabfilter");
  if(!host) return;
  const _dupN=(typeof countDuplicateSkus==="function")?countDuplicateSkus():0;
  // THE SEARCH BOX STAYS WHATEVER ELSE IS IN HERE.
  //
  // This strip used to hide itself entirely when there were no duplicates,
  // which is right for a duplicates toggle and wrong for the only way to find a
  // listing. The box is drawn first and unconditionally; the duplicates pill
  // joins it when there is something to toggle.
  //
  // The value is read back from SEARCH_Q rather than left in the DOM, because
  // render() rebuilds this strip and a box that empties itself as you type is
  // worse than no box.
  const _hits = (SEARCH_Q.trim() && Array.isArray(ROWS))
    ? ROWS.filter(matchesSearch).length : -1;
  host.style.display="";
  host.innerHTML =
    `<div class="lsearch">
       <i class="ti ti-search"></i>
       <!-- THE BOX DID THIS ALREADY AND NEVER SAID SO.
            "i have an option to search listings with identifiers but i do not
             have an option to find the listings with their name"
            Measured on jack_uk's 67 listings: "fol" found 10, "camping chair"
            found 1, "grill" found 2. The name search worked the whole time --
            the placeholder said "SKU, ASIN or barcode", so nobody tried it. -->
       <input id="lsearch_in" class="ed" placeholder="Find by name, SKU, ASIN or barcode…"
              value="${esc(SEARCH_Q)}" oninput="setSearch(this.value)">
       ${SEARCH_Q.trim()
          ? `<button class="ib" title="Clear" onclick="setSearch('')"><i class="ti ti-x"></i></button>
             <span class="cc" style="font-size:11.5px;white-space:nowrap">${_hits} match${_hits===1?'':'es'}</span>`
          : ""}
     </div>` +
    (_dupN
      ? `<button class="tabpill dup ${DUP_ONLY?'active':''}" onclick="toggleDupOnly()" title="Show only duplicate copies so you can delete the extras"><i class="ti ti-copy"></i> Duplicates <span class="tabcount">${_dupN}</span></button>`
      : "");
  // Typing rebuilds the strip, so the caret has to be put back or every
  // keystroke would drop focus after the first one.
  if(SEARCH_Q){
    const el=document.getElementById("lsearch_in");
    if(el){ el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
  }
}
// Switch the tab filter. When a SPECIFIC tab is chosen we also point the workspace's
// active tab at it (server-side), so edits / approvals / image pushes land on the tab
// you're viewing rather than a stale one — Miles has the same SKU on several tabs.
function setTabFilter(gid){
  TAB_FILTER=gid;
  if(gid!=="__all__"){
    const t=(TABS||[]).find(x=>String(x.tab_gid)===String(gid));
    if(t){ syncActiveTab(t.tab_gid, t.tab); }
  }
  render();
}
// Tell the server which tab is active, so single-tab-targeting write routes are correct.
// _ACTIVE_SYNC_GID remembers the last tab we synced so we don't re-POST needlessly.
let _ACTIVE_SYNC_GID = "";
async function syncActiveTab(gid, tab){
  try{
    await fetch("/view/set_active_tab",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({gid:String(gid||""), tab:String(tab||"")})});
    _ACTIVE_SYNC_GID=String(gid||"");
  }catch(e){ /* non-fatal: edits just target the previous active tab */ }
}
// Before ANY write on a card (approve, edit, delete, push), make the server's active
// tab match that card's tab. No-op for single-tab sheets, and only POSTs when the tab
// actually changes — so a bulk action over one tab syncs once, not once per SKU.
async function ensureCardTab(sku){
  if(!(TABS && TABS.length>1)) return;
  const r=ROWS.find(x=>String(x.sku)===String(sku));
  if(r && r.tab_gid && String(r.tab_gid)!==String(_ACTIVE_SYNC_GID)){
    await syncActiveTab(r.tab_gid, r.tab);
  }
}

// ---- Cross-tab duplicate SKUs -------------------------------------------------
// The same SKU on more than one card (usually on different tabs) means the same
// product is listed twice. We index every SKU -> all its copies so each copy can be
// flagged and the extras deleted. Built once per data load (buildDupIndex), and any
// delete triggers loadRows() which rebuilds it.
let DUP_INDEX = new Map();   // skuUpper -> [{sku,tab,tab_gid,row}]
let DUP_ONLY  = false;       // filter toggle: show ONLY duplicate copies
function buildDupIndex(){
  DUP_INDEX = new Map();
  (ROWS||[]).forEach(r=>{
    if(typeof isEmptyRow==="function" && isEmptyRow(r)) return;   // ignore blank rows
    const k=String(r.sku||"").trim().toUpperCase();
    if(!k) return;
    if(!DUP_INDEX.has(k)) DUP_INDEX.set(k, []);
    DUP_INDEX.get(k).push({sku:r.sku, tab:r.tab||"", tab_gid:String(r.tab_gid||""), row:r.row});
  });
}
function dupCopies(r){                       // every copy of this SKU (incl. itself)
  const k=String(r.sku||"").trim().toUpperCase();
  if(!k) return [];
  return DUP_INDEX.get(k) || [];
}
function isDuplicate(r){ return dupCopies(r).length>1; }
function dupOtherTabs(r){                     // distinct OTHER tabs the SKU also lives on
  const mine=String(r.tab_gid||""), seen=new Set(), out=[];
  dupCopies(r).forEach(c=>{ if(String(c.tab_gid)!==mine && c.tab && !seen.has(c.tab)){ seen.add(c.tab); out.push(c.tab); } });
  return out;
}
function countDuplicateSkus(){ let n=0; DUP_INDEX.forEach(v=>{ if(v.length>1) n++; }); return n; }
function toggleDupOnly(){ DUP_ONLY=!DUP_ONLY; render(); }
// Delete ONE duplicate copy from its own tab (leaving the other copies untouched).
// ensureCardTab syncs the active tab first, so /delete removes the right row on the
// right tab -- never a same-numbered row on another tab.
async function delDuplicate(sku, row, tab, btn){
  if(!await uiConfirm("Delete this DUPLICATE copy of "+sku+" from the '"+tab+"' tab?\n\n"
             +"Only this copy is removed — copies on other tabs stay. This cannot be undone.")) return;
  if(btn) btn.disabled=true;
  try{
    if(typeof ensureCardTab==="function"){ await ensureCardTab(sku); }
    const res=await fetch("/delete",{method:"POST",headers:{"Content-Type":"application/json"},
                body:JSON.stringify(acctBody({sku:sku, row:row}))});
    const j=await res.json();
    if(j.ok){ toast("Duplicate removed from "+tab); loadRows(); }
    else{ toast("Delete failed: "+(j.error||"")); if(btn) btn.disabled=false; }
  }catch(e){ toast("Delete failed"); if(btn) btn.disabled=false; }
}

// Is this row live ON AMAZON? Amazon's catalog is the ONLY authority whenever we
// have it. A "LIVE" in the sheet is a claim, not proof: the sheet is written by
// this app, it is never re-read from Amazon, and a misrouted tab once put another
// account's "LIVE" rows straight into the Live on Amazon group. So when the live
// catalog is loaded, a row counts as live only if Amazon returned its SKU or ASIN.
//
// Without the catalog (the Drafts view never fetches it) we fall back to the
// sheet's own claim -- and render() labels that group as unverified, rather than
// captioning it "Live on Amazon".
//
// Must return the SAME answer for render() (grouping) and summary() (counting),
// or the top bar disagrees with the grid.
/* Has AMAZON confirmed this row is live?
 *
 * THE GATE IS WHETHER WE HAVE AMAZON'S ANSWER, NOT WHICH TAB IS OPEN.
 *
 *     "when i go to live on amazon section i see the asin B0HCVFW53Y and
 *      B0HCVTDFNW as live and when i go to drafts it showed me the both as
 *      drafts; ready to send"
 *
 * This used to read:
 *
 *     if(liveGroupShown) return <does Amazon list it?>
 *     return norm(r.status)==="LIVE"
 *
 * -- so on the Drafts view it stopped asking Amazon and answered from the
 * stored status word instead. The same listing was therefore live on one tab
 * and a ready-to-send draft on the other, and the app was confident about both.
 * Two answers to one question, decided by which button you last pressed.
 *
 * The gate made sense once, because the catalogue was only ever fetched for the
 * Live and All views. It is fetched on every view now (see shell.js), so the
 * honest condition is simply: if Amazon's catalogue is loaded, Amazon decides.
 * The stored word is the fallback for BEFORE the first sync only -- which is
 * the one case where the app genuinely has nothing better, and where calling a
 * row not-live would slander a listing nobody has asked Amazon about yet.
 *
 * A row whose stored word says LIVE while the loaded catalogue does not list it
 * is deliberately NOT live here. That state has its own name and its own
 * display -- isClaimedLiveOnly(), "not confirmed by Amazon" -- and folding it
 * into "live" is what hid it.
 *
 * liveGroupShown is kept because callers still pass it and one passes an
 * explicit true; it now forces the catalogue answer rather than selecting it.
 */
function isActuallyLive(r, liveCatSkus, liveCatAsins, liveGroupShown){
  const norm = v => String(v||"").trim().toUpperCase();
  // _matchableAsin, not r.asin: on an app row that field is the COMPETITOR
  // reference from the SKU, and matching it against our own catalogue can only
  // produce a false positive -- declaring our draft live because somebody
  // else's listing exists. The SKU match below is the authoritative one.
  const s=norm(r.sku), a=_matchableAsin(r);
  const haveAmazon = liveGroupShown
                  || (typeof _liveCatalogLoaded==="function" && _liveCatalogLoaded())
                  || (liveCatSkus && liveCatSkus.size) || (liveCatAsins && liveCatAsins.size);
  if(haveAmazon) return !!((s && liveCatSkus.has(s)) || (a && liveCatAsins.has(a)));
  return norm(r.status)==="LIVE";
}

// Has Amazon's live catalog actually been fetched for the account+marketplace in view?
// LIVE_STORE holds a cache entry (even an empty one) only AFTER a Sync completes for
// that key. Before that, LIVE_ITEMS is empty simply because we never asked -- which is
// NOT the same as "Amazon returned nothing". Callers that draw a negative conclusion
// ("not confirmed by Amazon") must gate on this, or they slander live listings as dead
// before the first Sync.
function _liveCatalogLoaded(){
  try{
    return (typeof LIVE_STORE!=="undefined") && (typeof _liveKey==="function")
           && (LIVE_STORE[_liveKey()]!==undefined);
  }catch(e){ return false; }
}

// The sheet SAYS this row is live, but Amazon's catalog does not list it.
// Only meaningful once the catalog is loaded -- we cannot call a LIVE row "not
// confirmed by Amazon" until we have actually asked Amazon (i.e. a Sync has run).
// Before that, this returns false so those rows fall back to the sheet's own claim
// and the alarming "Not confirmed by Amazon" group never appears pre-Sync.
function isClaimedLiveOnly(r, liveCatSkus, liveCatAsins, liveGroupShown){
  const norm = v => String(v||"").trim().toUpperCase();
  if(!liveGroupShown) return false;
  if(!_liveCatalogLoaded()) return false;
  return norm(r.status)==="LIVE" && !isActuallyLive(r, liveCatSkus, liveCatAsins, liveGroupShown);
}

// Is this row published on Amazon, and therefore NOT a draft?
//
// The Drafts view hides these, so the counters above the list have to agree
// about which they are -- they did not, which is what made the top of the
// screen describe a different set of listings from the list underneath it.
// Reported as: "it shows total listings 86 ... and live 12, what do it mean by
// live, in drafts". The list was showing 74 and the tiles were counting 86.
//
// Published means the store says LIVE, or a Sync has loaded Amazon's catalogue
// and Amazon itself lists the SKU or ASIN.
//
// THE BODY NOW LIVES IN static/js/liststatus.js (CLAUDE.md Rule 12). It was one of
// THREE separate answers to "is this published" -- this one counting only LIVE,
// miles_template.js's _PUBLISHED_STATES counting LIVE and SUBMITTED, and
// barcode_clash.py counting LIVE, SUBMITTED and ACTIVE. A row Amazon had accepted
// was therefore "published" to one of them and "a draft" to another, which is how
// a submitted listing came to sit in Drafts reading as if it had never been sent.
// The name stays here because everything on this screen calls it; the rule it
// applies is defined once, next to the two questions it had been confused with
// (lsWasSentToAmazon vs lsIsPublished).
function isPublishedRow(r){ return lsIsPublished(r); }

// Build the SKU/ASIN sets once per render -- reused by summary()
function _liveCatSetsForCurrentView(){
  const norm = v => String(v||"").trim().toUpperCase();
  return {
    skus:  new Set((LIVE_ITEMS||[]).map(it=>norm(it.sku)).filter(Boolean)),
    asins: new Set((LIVE_ITEMS||[]).map(it=>norm(it.asin)).filter(Boolean)),
    liveGroupShown: (LIST_SOURCE==="live" || LIST_SOURCE==="all"),
  };
}

function summary(){
  renderTabFilter();                             // keep the tab filter row in sync
  const c={QUEUED:0,GENERATED:0,SUBMITTED:0,
           APPROVED:0,API_READY:0,NEEDS_REVIEW:0,HOLD:0,ERROR:0,LIVE:0};
  const sets = _liveCatSetsForCurrentView();
  // Counts reflect the ACTIVE tab filter: "All tabs" counts everything, a specific
  // tab counts only that tab's rows. Blank placeholder rows are excluded so the
  // "N listings" total agrees with the grid (which hides them) and the tab pills.
  const _allTabRows = ROWS.filter(tabPass)
                       .filter(r=> (typeof isEmptyRow!=="function") || !isEmptyRow(r))
                       .filter(r=> !DUP_ONLY || isDuplicate(r));
  // COUNT WHAT THE LIST BELOW ACTUALLY SHOWS.
  //
  // On the Drafts view the list hides published rows, but these tiles counted
  // every row -- so the screen said "86 listings" and "12 live" above a list of
  // 74 drafts, and a "Live" tile on a screen that shows no live listings. It
  // was reported, fairly, as making no sense.
  //
  // The published rows are not forgotten: they are named underneath, with a way
  // to go and see them.
  const _draftsView = draftsView();
  const _hiddenLive = _draftsView ? _allTabRows.filter(isPublishedRow) : [];
  const _tabRows = _draftsView
                 ? _allTabRows.filter(r=>!isPublishedRow(r))
                 : _allTabRows;
  _tabRows.forEach(r=>{
    // FIX: reclassify HOLD/NEEDS_REVIEW/etc. as LIVE if the row's SKU/ASIN
    // matches the Amazon catalog. Without this the top-bar shows a stale
    // "N on hold" count for rows that already went live on Amazon but never
    // had their stored status updated from a pre-submit HOLD.
    if(isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown)){
      c.LIVE++;
      return;
    }
    // THE FOUR STATUSES. QUEUED and GENERATED are what the flow uses now; the
    // rest are kept because a database that has not been migrated yet still
    // holds them, and a row counted into nothing disappears off the screen
    // without saying so.
    if(r.status==="QUEUED")c.QUEUED++;
    else if(r.status==="GENERATED")c.GENERATED++;
    else if(r.status==="SUBMITTED")c.SUBMITTED++;
    else if(r.status==="APPROVED")c.APPROVED++;
    else if(r.status==="API_READY")c.API_READY++;
    else if(r.status==="LIVE")c.LIVE++;
    else if(r.status==="NEEDS_REVIEW")c.NEEDS_REVIEW++;
    else if(r.status==="IP_HOLD"||r.status==="COMPLIANCE_HOLD")c.HOLD++;
    else if(r.status==="ERROR"||r.status==="API_ERROR")c.ERROR++;
  });
  // include live Amazon listings in the counts when they're part of the view.
  // Deduplicate: a catalog tile whose SKU/ASIN already matched an app row above
  // has already been counted as LIVE -- don't count it twice.
  const norm = v => String(v||"").trim().toUpperCase();
  // Worked out ONCE. It was filtered twice with the same predicate to build the
  // two sets, and the count of it was then not taken at all -- which is how the
  // total below came to leave these rows out.
  const _liveAppRows = _tabRows.filter(r=>isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown));
  const alreadyCountedSkus  = new Set(_liveAppRows.map(r=>norm(r.sku)).filter(Boolean));
  // _matchableAsin, not r.asin: this set EXCLUDES catalogue items from the
  // count, so seeding it with competitor ASINs risks dropping a genuinely live
  // listing out of the total -- the undercount version of the same mistake.
  const alreadyCountedAsins = new Set(_liveAppRows.map(_matchableAsin).filter(Boolean));
  const liveCount = ((LIST_SOURCE==='live'||LIST_SOURCE==='all')
                     ? (LIVE_ITEMS||[]).filter(it=>{
                         const s=norm(it.sku), a=norm(it.asin);
                         if(s && alreadyCountedSkus.has(s))  return false;
                         if(a && alreadyCountedAsins.has(a)) return false;
                         return true;
                       }).length
                     : 0);
  c.LIVE += liveCount;
  // TOTAL IS WHAT THE LIST BELOW IT ACTUALLY CONTAINS.
  //
  // In the Live view this was liveCount -- the catalogue items left AFTER the
  // ones matching an app row were removed. But the list shows both: the app's
  // own rows that Amazon confirmed live, and then the catalogue-only ones. So
  // the total counted the second group and not the first, and on nestwell_goods
  // read "TOTAL LISTINGS 43" directly above "LIVE 55" -- a total smaller than
  // one of its own parts, which is how it was noticed.
  let total = _tabRows.length;
  if(LIST_SOURCE==='live'){
    total = _liveAppRows.length + liveCount;
    // In the Live view every row IS live, so the LIVE tile counts the same set
    // the total does. It was counting app rows whose STATUS says LIVE across the
    // whole tab -- including ones this view is not showing -- so it could exceed
    // the total sitting next to it, which is the pair of numbers that got
    // reported ("43 total listings and 55 live listings").
    c.LIVE = total;
  }
  else if(LIST_SOURCE==='all') total = _tabRows.length + liveCount;
  // Orbit's four metric tiles replace the old one-line text summary. Each is
  // clickable and filters the list to that status -- the count was always the
  // question "which ones need me?", and it now answers it in one click instead
  // of sending you to the dropdown.
  //
  // The counts below the tiles (errors, preview-ready, duplicates) are kept as a
  // quiet line: they matter, but not enough to spend one of four tiles on, and
  // dropping them would lose information the old summary gave you.
  const _cur = (typeof FILTER !== "undefined") ? FILTER : "all";
  // ONE CARD, DEFINED ONCE (CLAUDE.md Rule 12).
  //
  //     "the sizing and the theme of the repricer page is nice, i want this to
  //      be applied on all listings page and the catalog page"
  //
  // This used to build its own .metric -- centred, 22px, no bar -- while the
  // Catalog built .ui-stat and the Repricer built .rp-mc. Three cards, three
  // sizes, three alignments, on three screens that do the same job. It now
  // calls the shared uiStat() in pageui.js, and the look lives in
  // static/css/datatable.css. Nothing about WHAT the tiles count has changed.
  //
  // `share` draws the bar along the bottom: the count as a fraction of the
  // total beside it. "12 blocked" reads differently out of 20 than out of 400,
  // and the number alone cannot say which. Passed only for the subsets -- the
  // total is the whole, and a permanently full bar states nothing.
  const tile = (n, label, filter, tone) => {
    const whole = Number(total) || 0;
    const cnt = Number(n);
    const sub = tone !== undefined;
    return uiStat({
      value: n,
      label: label,
      on: _cur === filter,
      onclick: "metricFilter('" + filter + "')",
      title: "Show only these",
      share: (sub && !_pending && whole > 0 && isFinite(cnt))
        ? Math.min(1, cnt / whole) : null,
      barColor: tone,
    });
  };
  const extras = [];
  // A COUNT WITH NO NOUN IS NOT A FACT.
  //
  //     "i see a text is written 25 on hold, what is this and why is it
  //      written like this"
  //
  // Fair. "25 on hold" named no thing, gave no reason, and could not be
  // clicked -- so it was a number you could neither understand nor act on.
  // Both now say what they are counting, why those rows are stopped, and take
  // you to them.
  // EACH COUNT GOES TO ITS OWN LIST. Both of these used to pass 'holds', which
  // is the UNION -- so clicking a count of 3 showed 28 rows. See isHold.
  if(c.ERROR){
    extras.push(`<button class="linkbtn" style="color:var(--red)"
        onclick="metricFilter('refused')"
        title="Sent to Amazon, and Amazon rejected it. Open one to see what Amazon said.">${c.ERROR}
        listing${c.ERROR>1?'s':''} Amazon refused</button>`);
  }
  if(c.HOLD){
    extras.push(`<button class="linkbtn" style="color:var(--red)"
        onclick="metricFilter('blocked')"
        title="Held by this app's own IP or compliance check BEFORE anything was sent to Amazon — open one to see which rule, or re-scan after fixing a rule.">${c.HOLD}
        held by a compliance or IP check</button>`);
  }
  // The published rows the Drafts list is deliberately not showing. Said in
  // words rather than counted into a tile above a list they are not in, and
  // with the way to go and look at them.
  if(_hiddenLive.length){
    extras.push(`<span class="cc">${_hiddenLive.length} already live on Amazon, not shown here — `
      + `<button class="linkbtn" onclick="setListSource('live')">see them</button></span>`);
  }
  if(countDuplicateSkus()>0){
    extras.push(`<span class="dupsum" onclick="toggleDupOnly()" title="Show only the duplicate copies so you can delete the extras"><i class="ti ti-copy"></i> ${countDuplicateSkus()} duplicate SKU${countDuplicateSkus()>1?'s':''} across tabs</span>`);
  }
  const _sumHost = document.getElementById("summary");

  // THE TILES ANSWER WHAT THE VIEW CAN ANSWER.
  //
  // On the LIVE view three of the four said nothing. "Total listings 45" and
  // "Live 45" are the same number by definition -- everything in this list is
  // live -- and "Ready to submit 0" cannot ever be anything else, because a
  // listing that is already on Amazon has been submitted. Reported as: "45
  // total listings and 45 live listings and 0 ready to send listings, do it
  // makess sense?"
  //
  // It does not, so the live view gets tiles about LIVE listings: how many
  // Amazon is not currently showing, how many have no cost (which is what makes
  // every profit figure wrong), and how many have run out.
  // A COUNT OF ZERO IS A CLAIM. While the drafts are still in flight, ROWS is
  // empty and every one of these tiles confidently reports 0 -- four wrong
  // numbers above a grid that is about to fill. An em-dash says "not yet",
  // which is the truth for the second it lasts.
  //
  //     "selvora dont have zero drafts but why was that error message
  //      appearing ... why that 1 sec gap is there"
  const _pending = (typeof _rowsStillComing === "function") && _rowsStillComing();
  const _n = v => _pending ? "—" : v;
  let tiles;
  if(_draftsView){
    // THE FOUR STATUSES, in the order a listing passes through them.
    //
    // "Needs review", "Ready to submit" and "Blocked or errored" are gone with
    // the statuses behind them. There is no blocked tile any more BECAUSE
    // NOTHING BLOCKS: what used to stop a listing is a warning on it now, and
    // that is counted separately below rather than as a status, because a
    // listing with a warning is not in a different state -- it is generated,
    // and someone should look at it.
    //
    // APPROVED, API_READY and NEEDS_REVIEW are folded into Generated so a
    // database that has not been migrated yet still shows its rows somewhere
    // rather than counting them into nothing.
    const _gen = c.GENERATED + c.NEEDS_REVIEW + c.APPROVED + c.API_READY
               + c.HOLD + c.ERROR;
    tiles = tile(_n(c.QUEUED), "Queued", "queued", "var(--ink3)")
          + tile(_n(_gen), "Generated", "generated", "var(--gold)")
          + tile(_n(c.SUBMITTED), "Submitted", "submitted", "var(--ok)")
          + tile(_n(c.LIVE), "Live", "live", "var(--ok)");
  }else{
    // THREE OF THESE FOUR TILES USED TO SEND THE SAME FILTER.
    //
    //     "when i click on not showing status button a green border appears
    //      around only this button but when i click on any one of the button
    //      from no cost set, out of stock or live listings button. clicking
    //      only 1 button draws a border on all 3"
    //
    // Live listings, No cost set and Out of stock all passed "all". The tile
    // lights up when its filter equals the current one, so pressing any of the
    // three lit all three -- and since "all" means no filter, none of them
    // hid anything either. One defect, both symptoms.
    //
    // Each has its own filter now, and the COUNT and the FILTER read the same
    // predicate (liveItemIs), so a tile can never say 9 and then show 40.
    const live = (typeof LIVE_ITEMS !== "undefined" && LIVE_ITEMS) ? LIVE_ITEMS : [];
    tiles = tile(total, "Live listings", "live_all")
          + tile(live.filter(it => liveItemIs(it, "live_notshowing")).length,
                 "Not showing", "live_notshowing", "var(--red)")
          + tile(live.filter(it => liveItemIs(it, "live_nocost")).length,
                 "No cost set", "live_nocost", "var(--gold)")
          + tile(live.filter(it => liveItemIs(it, "live_oos")).length,
                 "Out of stock", "live_oos", "var(--red)");
  }

  _sumHost.innerHTML =
    `<div class="ui-stats">` + tiles + `</div>`
    + (extras.length ? `<div class="cc" style="margin:-6px 0 12px">${extras.join(" &nbsp;·&nbsp; ")}</div>` : "");
  // NO MIGRATION NOTICE HERE, AND NEVER AGAIN.
  //
  //     "Bring in whatever is left automatically right now, then remove this
  //      banner entirely. It should never appear again. ... We are fully on the
  //      database now."
  //
  // A notice used to sit here whenever ROWS_SOURCE.from_sheet was above zero:
  // "N of these listings are still only in the Google Sheet", with a button to
  // check what would be brought in. The listings read now performs that import
  // itself when it finds such rows -- see the auto-import in /rows_all and
  // domain/sheet_migration.py -- so by the time this screen draws, there is
  // nothing left for a person to authorise.
  //
  // Numbers count into place, but only the ones that actually changed --
  // see altaCountMetrics. This runs on every render, including a filter click,
  // and animating an unchanged figure would say "this just moved" about
  // something that did not.
  if(typeof altaCountMetrics === "function") altaCountMetrics(_sumHost);
}

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
      onclick="event.stopPropagation();priceEdit('${esc(r.sku)}',${n},'${esc(r.title||'')}')">${txt}<i class="ti ti-pencil"></i></span>`;
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

/* HOW MANY WARNINGS, on the card, so you can see which listings want attention
 * without opening every drawer.
 *
 * Coloured by the worst one it carries: a listing with four low warnings is
 * not the one to look at first, and a single "this barcode is already live on
 * Amazon" is.
 */
function _warnChip(r){
  if(typeof lsWarnings !== "function") return "";
  const w = lsWarnings(r);
  if(!w.n) return "";
  const tone = w.high ? "var(--red)" : (w.medium ? "var(--warn)" : "var(--ink3)");
  const worst = w.high ? "high" : (w.medium ? "medium" : "low");
  const tip = w.list.slice(0, 4).map(function(x){
    return "• " + String((x && x.message) || "");
  }).join("\n");
  return `<span class="tilefact" style="color:${tone}" title="${esc(tip)}">`
       + `<i class="ti ti-alert-triangle"></i> ${w.n} warning`
       + `${w.n === 1 ? "" : "s"}<span class="cc"> (${worst})</span></span>`;
}

/* THE SAME COUNT, IN THE TABLE.
 *
 * The badge was only on the tile, and the table is the DEFAULT view -- so on the
 * screen almost everyone actually looks at, nothing showed which listings had
 * warnings, and the only way to find out was to open all of them. Which is the
 * problem the badge exists to solve.
 *
 * Sits under the status pill because that is the cell about the listing's state,
 * and a warning is part of that state.
 */
function _warnCell(r){
  if(typeof lsWarnings !== "function") return "";
  const w = lsWarnings(r);
  if(!w.n) return "";
  const tone = w.high ? "var(--red)" : (w.medium ? "var(--warn)" : "var(--ink3)");
  const tip = w.list.slice(0, 5).map(function(x){
    return "• " + String((x && x.message) || "");
  }).join("\n");
  return `<div style="font-size:9.5px;margin-top:3px;color:${tone}" `
       + `title="${esc(tip)}"><i class="ti ti-alert-triangle"></i> `
       + `${w.n} warning${w.n === 1 ? "" : "s"}</div>`;
}

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
    + (denied
        ? ' Amazon is refusing this app’s requests for this account. Press '
          + '<b>Diagnose SP-API</b> at the top of this page — it checks each '
          + 'permission in turn and names the ones that are missing.'
        : '')
    + '<div class="cc" style="margin-top:6px">Amazon said: '
    + esc(APLUS_ERROR) + '</div></div>';
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
  const _st = String(r.status||"").toUpperCase();
  const _blocker = (_st==="IP_HOLD" || _st==="ERROR");
  const realIssue = _restFlag || _blocker;
  const flagRed = _restProhibited || _blocker;   // gated-only -> amber
  const urls=_cardImages(r);
  const thumb = (urls&&urls.length)
    ? `<img src="${esc(thumbUrl(urls[0],120))}" loading="lazy" decoding="async" onerror="this.style.display='none';this.parentNode.classList.add('noimg');this.parentNode.innerHTML='<i class=\\'ti ti-photo\\'></i>'">`
    : `<i class="ti ti-photo"></i>`;
  const selected = SELECTED.has(String(r.sku));
  const skuId=sid(r.sku);
  const ownAsin=ownLiveAsin(r);   // your OWN live ASIN (from the live catalogue), or "" if not live/not loaded
  const _isDup=(typeof isDuplicate==="function") && isDuplicate(r);   // same SKU on another card/tab
  const _dupOther=_isDup?dupOtherTabs(r):[];
  return `<div class="tile ${selected?'sel':''} ${_isDup?'dup':''} ${flagRed?'flag':(realIssue?'flagamber':'')}" data-sku="${esc(r.sku)}">
    <div class="tileimg pii-img ${(urls&&urls.length)?'':'noimg'}" onclick="openDrawer('${esc(r.sku)}')">
      ${thumb}
      <span class="tiledot" style="background:${_statusDot(r)}" title="${esc(r.status||'')}"></span>
      ${rowSelectBox(r, "tilesel")}
      ${realIssue?`<span class="tileflag ${flagRed?'red':'amber'}" title="${flagRed?'Restricted / blocked — open to see why':'Restricted — docs required'}"><i class="ti ti-alert-triangle"></i></span>`:''}
      ${claimBadge(r)}
      ${viabilityBadge(r)}
      ${needsCopyBadge(r)}
      ${aplusImages(r).length?`<span class="tileaplus" title="A+ content live on Amazon — ${aplusImages(r).length} image(s). Open the listing to see them.">A+</span>`:''}
      ${_inactiveChip(r)}
      ${_queuedChip(r)}
      ${_warnChip(r)}
      <button class="peek" title="Reveal this listing" onclick="event.stopPropagation();peekTile(this)"><i class="ti ti-eye"></i></button>
    </div>
    <div class="tilebody" onclick="openDrawer('${esc(r.sku)}')">
      <div class="tiletitle pii">${esc(r.title)||'<span class="cc">(no title)</span>'}</div>
      <div class="tilemeta">
        ${_priceCell(r, "tileprice pii")}
        <span class="tilesku pii">${esc(r.sku)||''}</span>
      </div>
      <div class="tilefacts">${_brandCell(r)}${_handCell(r)}</div>
      <!-- the "lives on the X tab" badge went with the spreadsheet -->

      ${_isDup?`<div class="tiledup" onclick="event.stopPropagation()">
        <span class="tiledup-lbl"><i class="ti ti-copy"></i> Duplicate SKU${_dupOther.length?` — also on ${esc(_dupOther.join(', '))}`:` — appears ${dupCopies(r).length}×`}</span>
        <button class="tiledup-del" title="Delete this copy from ${esc(r.tab||'this tab')} (other copies stay)" onclick="event.stopPropagation();delDuplicate('${esc(String(r.sku))}',${r.row||0},'${esc(String(r.tab||''))}',this)"><i class="ti ti-trash"></i> Delete this copy</button>
      </div>`:''}
      ${ownAsin?`<div class="tileasin" title="Your own live ASIN on Amazon (from the live catalogue)"><i class="ti ti-brand-amazon"></i> <a href="${_dpUrl(ownAsin)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${esc(ownAsin)}</a></div>`:''}
    </div>
    <!-- Built by rowActions so the table row offers exactly the same set. The
         two used to be written out separately and had drifted: the table had
         no Approve, no Auto-fix and no More menu, and no checkbox at all. -->
    <div class="tileacts">${rowActions(r, "ib")}</div>
  </div>`;
}

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
    <summary class="mirsum"><i class="ti ti-brand-amazon"></i> Actual on Amazon <span class="cc">(read-only — pulled by Sync, ${imgs.length} image(s))</span></summary>
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
        <button class="linkbtn" style="margin-top:6px" onclick="locateFlags('${esc(r.sku)}',this)">\ud83d\udd0d Locate flagged terms</button>
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
          <span class="livestatus" style="background:#123021;color:var(--ok)">${esc(d.status||'')}</span>
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
  const bar = `<div class="dw2-bar">
      <span class="badge ${badgeClass(r.status)}">${esc(r.status||'\u2014')}</span>
      ${risks.join("")}
      ${asinBit}
      <span class="dw2-spacer"></span>
      <button class="dw2-ib" onclick="previewOne('${esc(r.sku)}')" title="Preview \u2014 check this listing against Amazon. Nothing is sent."><i class="ti ti-eye"></i></button>
      <button class="dw2-ib accent" onclick="autoFixLoop('${esc(r.sku)}')" title="Auto-fix \u2014 suggest, apply, preview, repeatedly, until there are no errors left (max 8 rounds)"><i class="ti ti-wand"></i></button>
      ${ro ? `<button class="dw2-ib" disabled title="Read-only workspace \u2014 cannot publish"><i class="ti ti-lock"></i></button>`
           : `<button class="dw2-ib success" onclick="submitOne('${esc(r.sku)}')" title="Submit \u2014 publish ONLY this listing live"><i class="ti ti-upload"></i></button>`}
      <button class="dw2-ib ${st==='APPROVED'?'on-approve':''}" onclick="setStatus('${esc(r.sku)}','APPROVED',this)" title="${st==='APPROVED'?'Already approved':'Approve \u2014 mark ready to send'}"><i class="ti ti-check"></i></button>
      <button class="dw2-ib ${st==='NEEDS_REVIEW'?'on-hold':''}" onclick="setStatus('${esc(r.sku)}','NEEDS_REVIEW',this)" title="${st==='NEEDS_REVIEW'?'Already held':'Hold \u2014 keep it back'}"><i class="ti ti-hand-stop"></i></button>
      <button class="dw2-ib" onclick="drawerMore(event,'${esc(r.sku)}',${r.row||0},${live?'true':'false'})" title="Everything else"><i class="ti ti-dots"></i></button>
      <button class="dw2-ib bare" onclick="closeDrawer()" title="Close"><i class="ti ti-x" style="font-size:16px"></i></button>
    </div>`;

  // ---- hero -----------------------------------------------------------
  // The title is edited HERE and nowhere else. It keeps its claim-risk
  // highlights, and saveEdit reads textContent, so the <mark> markup can
  // never reach Amazon. Its counter and the 27 Jul 2026 cap warning sit
  // under it -- the same TITLE_OPTS every other title check uses.
  const tcid = "dwtitlec_" + sv;
  const tval = String(r.title || "");
  const tn = tval.length;
  const tover = tn > TITLE_OPTS.limit, twarn = tn > TITLE_OPTS.warnAt && !tover;
  const heroImg = (urls && urls.length)
    ? `<div class="dw2-heroimg"><i class="ti ti-photo"></i><img src="${esc(urls[0])}" loading="lazy" onerror="this.remove()"></div>`
    : `<div class="dw2-heroimg"><i class="ti ti-photo"></i></div>`;
  const cost = _dwCost(r);
  const heroBlock = `<div class="dw2-hero">
      ${heroImg}
      <div class="dw2-heroinfo">
        <div class="dw2-h3" contenteditable="true" spellcheck="false"
             data-orig="${esc(tval)}"
             oninput="dwCount(this,'${tcid}',${TITLE_OPTS.limit},0,${TITLE_OPTS.warnAt})"
             onpaste="dwPastePlain(event)"
             onblur="dwBlurSave(this,'${esc(r.sku)}','col','Title')"
             >${claimMarkField(r,'title',r.title)||''}</div>
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
        <span class="dw2-count${tover?' over':(twarn?' warn':'')}" id="${tcid}">${tn} / ${TITLE_OPTS.limit}</span>
        <span class="dw2-tag info" title="${esc(TITLE_OPTS.indexTip)}">${esc(TITLE_OPTS.indexNote)}</span>
      </span></div>
      ${(twarn||tover)?`<div class="dw2-note" style="color:#EF9F27">\u26a0 ${esc(TITLE_OPTS.warnMsg)}</div>`:''}
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
      <button onclick="previewOne('${esc(r.sku)}')" title="Check this listing against Amazon. Nothing is sent."><i class="ti ti-eye"></i> Preview</button>
      <button class="primary" onclick="autoFixLoop('${esc(r.sku)}')" title="Suggest, apply, preview -- repeatedly, until there are no errors left or it stops making progress (max 8 rounds)."><i class="ti ti-wand"></i> Auto-fix</button>
      ${ro ? `<span class="ro"><i class="ti ti-lock"></i> Read-only workspace</span>`
           : `<button class="success" onclick="submitOne('${esc(r.sku)}')" title="Publish ONLY this listing live"><i class="ti ti-upload"></i> Submit</button>`}
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
        <button onclick="openStudioSingle('${esc(r.sku)}')"><i class="ti ti-photo"></i> Image Studio</button>
        ${live ? `<button onclick="optimizeLive('${esc(ownAsin)}','${esc(r.sku)}')"><i class="ti ti-sparkles"></i> Optimize live copy</button>` : ""}
        <button onclick="askAbout('${esc(r.sku)}')"><i class="ti ti-message-circle"></i> Ask Claude about this listing</button>
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

/* WHAT THE STOCK COST, IF WE ACTUALLY KNOW.
 * The SKU carries it in the price_days_ASIN form (8.00_3Days_B0...), and the
 * row may carry a typed COGS that overrides it. Returns "" when neither is
 * there -- a made-up cost would make the profit beside it a lie. */
function _dwCost(r){
  const typed = String(r.cogs == null ? "" : r.cogs).replace(/[^0-9.]/g, "");
  if(typed) return CUR_SYMBOL + typed;
  const m = /^([0-9]+(?:\.[0-9]+)?)_/.exec(String(r.sku || ""));
  return m ? (CUR_SYMBOL + m[1]) : "";
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
  const statusBlock = (typeof _dwStatusBlock === "function") ? _dwStatusBlock(r) : "";
  return dwFold("Restricted products check", _dwVerdictTag(r.restricted && r.restricted.matched, "checked"), restrictedPanel(r))
    + dwFold("Compliance requirements", _dwVerdictTag(r.viability && r.viability.matched, "no demand"), viabilityPanel(r))
    + dwFold("Claim risks", (r.claim_flags||[]).length ? `<span class="dw2-tag warn">${(r.claim_flags||[]).length}</span>` : "", claimBox(r))
    + dwFold("Amazon feedback", statusBlock ? '<span class="dw2-tag warn">see inside</span>' : "", statusBlock)
    + dwFold("Actual on Amazon", '<span class="dw2-tag info">read-only mirror</span>', liveMirrorPanel(r))
    + dwFold("A+ content", '<span class="dw2-tag info">live on Amazon</span>', _dwAplus(r));
}

// A closed fold has to say enough that you can decide not to open it.
function _dwVerdictTag(matched, clearWord){
  return matched
    ? '<span class="dw2-tag warn"><i class="ti ti-alert-triangle"></i> attention</span>'
    : '<span class="dw2-tag ok"><i class="ti ti-check"></i> ' + esc(clearWord) + "</span>";
}

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

// Sync the DOM to whatever LIST_VIEW currently is. Separate from setListView()
// so it can run on page load without triggering a render before there are any
// rows to draw.
function applyListView(){
  document.querySelectorAll("#viewtoggle button").forEach(function(b){
    b.classList.toggle("on", b.dataset.view === LIST_VIEW);
  });
  const g = document.getElementById("grid");
  if(g) g.classList.toggle("tableview", LIST_VIEW === "table");
}

function setListView(v){
  LIST_VIEW = (v === "grid") ? "grid" : "table";
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
  setInterval(pollHealth, 60000);
});

/* WHAT YOU CAN DO TO A ROW -- built once, used by BOTH views.
 *
 * The grid and the table each drew their own set of buttons, and they had
 * drifted badly: the table had no checkbox at all, so nothing could be SELECTED
 * in it -- and every batch action on the screen works off that selection. Tick
 * three products in the grid, switch to the list, and there was nowhere for
 * the selection to live. Approve, Auto-fix and the More menu were missing too.
 * Reported as "the grid view listings and list view listings donot talk to each
 * other", which is exactly what it looked like.
 *
 * Neither view now owns the answer. Both call these, so a button added here
 * appears in both and the two cannot come apart again (CLAUDE.md Rule 12).
 *
 * `cls` is the only difference: the grid's round icon buttons and the table's
 * smaller ones are the same actions wearing the styling of the view they sit in.
 */
function rowSelectBox(r, cls){
  // `cls` is the only difference between the views, exactly as in rowActions:
  // the card's checkbox sits on the image and the table's in its own column,
  // so they are styled apart -- but WHAT the box does is one behaviour and is
  // written once. It was written twice, and the two spelled the SKU into the
  // handler separately, which is how one of them came to be looked up by a
  // class that does not exist.
  const on = SELECTED.has(String(r.sku)) ? "checked" : "";
  return `<input type="checkbox" class="${cls || "rowsel"}" ${on}
      title="Select for batch actions"
      onclick="event.stopPropagation()"
      onchange="toggleSelect('${esc(r.sku)}', this.checked)">`;
}

/* THE ONE ACTION ROW, for every card in the app.
 *
 *     "i see two types of cards style dont make them different make them same
 *      and also remove the unnecessary buttons from the cards"
 *
 * There were two: this icon row on the drafts cards, and a separate set of
 * text-labelled buttons written out by hand inside liveTile() in
 * miles_template.js. Same screen, same grid, two designs -- visible side by side
 * in his screenshot 84, and inevitable once the same list is drawn by two
 * renderers that each build their own buttons.
 *
 * liveTile calls this now, so there is one definition (Rule 12) and adding a
 * button to the app adds it to both kinds of card or to neither.
 *
 * `opts.live` forces the live branch on: a tile from Amazon's catalogue IS live
 * by definition, but it has no app row for isAmazonLive() to read.
 */
function rowActions(r, cls, opts){
  cls = cls || "ib";
  opts = opts || {};
  const sku = esc(r.sku);
  const live = opts.live === undefined ? isAmazonLive(r) : !!opts.live;
  return `
    ${live ? "" : `<button class="${cls}" title="Approve — mark this draft ready to send to Amazon"
            onclick="event.stopPropagation();setStatus('${sku}','APPROVED',this)"><i class="ti ti-check"></i></button>`}
    ${/* APPROVE IS FOR DRAFTS. It set the row's status to APPROVED, meaning
        * "ready to send". On a listing Amazon has already published there is
        * nothing to approve -- and on a catalogue-only card there is not even a
        * row to set it on, so the button either did nothing or wrote a status
        * onto a draft that does not exist. Live cards get Sync and Add variant
        * in its place, below, which is what you actually do to a live listing.
        */""}
    <button class="${cls} gen" title="Image Studio (creative ideas, prompt &amp; image AI)"
            onclick="event.stopPropagation();openStudioSingle('${sku}')"><i class="ti ti-photo"></i></button>
    <button class="${cls}" title="This listing's images — upload your own, pick one from the library, or set the main image"
            onclick="event.stopPropagation();openImageLibrary('${sku}', ${live ? "true" : "false"})"><i class="ti ti-library-photo"></i></button>
    ${/* OUR asin, not the competitor reference in the SKU (see rowAsin). The
        * fetch keys off the SKU so this argument was not doing damage, but
        * passing a competitor ASIN into a function about OUR live listing is
        * how the next person to use that argument inherits the bug. */""}
    ${live ? `<button class="${cls}" title="Optimize this live listing's copy — pulls it live from Amazon so you can rewrite &amp; push" style="color:var(--ai)"
            onclick="event.stopPropagation();optimizeLive('${esc(rowAsin(r).own||'')}','${sku}')"><i class="ti ti-sparkles"></i></button>` : ""}
    ${/* THESE TWO EXISTED ONLY IN THE LIVE TABLE ROW. The live TILE and the
        * live TABLE ROW are the same listing seen two ways, and they offered
        * different things to do to it -- exactly the drift that put two card
        * designs in one grid ("i see two types of cards style dont make them
        * different"). Both come from here now, so the grid and the list cannot
        * disagree again. Live-only because there is nothing to compare a draft
        * against and no live listing to hang a variant off. */""}
    ${live ? `<button class="${cls}" title="Compare this listing with Amazon's live copy, field by field"
            onclick="event.stopPropagation();syncForSku('${sku}')"><i class="ti ti-arrows-exchange"></i></button>` : ""}
    ${live ? `<button class="${cls}" title="Add another colour or size of this product, from an eBay link"
            onclick="event.stopPropagation();addVariant('${sku}')"><i class="ti ti-binary-tree"></i></button>` : ""}
    ${/* FOUR BUTTONS REMOVED FROM THE CARD (they all still exist, elsewhere):
        *
        *   Edit      -- "we can directly edit the listing by clicking on the
        *                 product card". The card and the table row both call
        *                 openDrawer already, and the table row also keeps its
        *                 Review button.
        *   Auto-fix  -- "the user can click on the box to select the item and
        *                 then click on auto fix button from the top. we dont
        *                 need the autofix button on the product card in both
        *                 grid and listing view". autoFixLoop is unchanged.
        *   Price     -- "remove that change the listings selling price button
        *                 which is already there on the product card". The price
        *                 is edited by clicking the price itself now (priceEdit
        *                 is still the one function that does it -- rule 12).
        *   Open on Amazon -- "we should be able to open the listing by clicking
        *                 on the green asin". The ASIN is the link now.
        */""}
    <button class="${cls} more" title="More"
            onclick="event.stopPropagation();tileMenu(event,'${sku}',${r.row||0})"><i class="ti ti-dots"></i></button>`;
}
/* PULL LIVE IMAGES: REMOVED.
 *
 *     "live pulling live images from amazon, i believe the app automatically
 *      fetches fresh data now. so we dont need that button also check other
 *      buttons from this logic and delete the un necessary ones"
 *
 * He is right. The button called pullLiveRow(), which fetches a listing's real
 * Amazon images into that one row. Sync already does exactly that for the whole
 * account, and the live tiles show Amazon's own images regardless of whether the
 * app holds a copy -- so it was a per-row repeat of a job that is already done
 * in bulk, sitting on the busiest row of buttons on the screen.
 *
 * pullLiveRow() itself is deliberately KEPT. It is still called from the drawer
 * and from the batch actions, where pulling images for one chosen listing is the
 * point rather than a duplicate of Sync.
 *
 * EVERY OTHER BUTTON WAS PUT TO THE SAME TEST -- "does something else already do
 * this?" -- and every one survived it:
 *
 *   Approve       sets the status. Nothing else does.
 *   Image Studio  GENERATES images. Different job from the library below.
 *   Library       shows what exists, uploads, and pushes one live.
 *   Edit          opens the full editor.
 *   Auto-fix      the suggest/apply/preview loop.
 *   Optimize      rewrites the live copy. Live only.
 *   Price         changes the live price. Live only.
 *   Open on Amazon a link, not an action.
 *   More          holds the rest.
 */

// One block of listings, drawn the way the user has chosen. Every place that
// used to say rows.map(card).join("") calls this instead, so the two views can
// never drift apart into "the table forgot about claimed rows".
function listBlock(rows, fn){
  fn = fn || card;
  if(!rows || !rows.length) return "";
  if(LIST_VIEW !== "table") return rows.map(fn).join("");
  const rowFn = (fn === (typeof liveTile === "function" ? liveTile : null))
                ? liveTableRow : tableRow;
  // COGS gets its own column, and it is EDITABLE. What a thing cost is the one
  // number every profit figure on every other screen is built from, and it was
  // only visible by opening a listing. Click the cell, type, done.
  const head = `<div class="card ltwrap"><table class="lt"><thead><tr>
      <th class="selcol" title="Select every row shown">
        <input type="checkbox" class="rowsel"
               ${rows.length && rows.every(x => SELECTED.has(String(x.sku))) ? "checked" : ""}
               onchange="selectAllVisible(this.checked)"></th>
      <th style="width:52px">Image</th><th>ASIN</th><th>Title</th>
      <th>Price</th><th title="What the stock cost you. Read from the SKU where the SKU carries it; click to type your own.">COGS</th>
      <th>Handling</th><th>Status</th><th>Compliance</th>
      <th style="width:150px">Actions</th></tr></thead><tbody>`;
  const body = rows.map(rowFn).join("");
  // THE HEADER AND THE ROWS MUST HAVE THE SAME NUMBER OF COLUMNS.
  //
  // liveTableRow shipped with nine cells against this ten-column header, and the
  // whole live view was shifted one place left -- pictures under the checkbox,
  // actions under "Compliance". Nothing caught it, because HTML does not
  // complain: a short row just draws short.
  //
  // So it is checked, once per draw, and said out loud in the console rather than
  // left to be noticed by eye. Cheap: one count of one string.
  if(body){
    const want = (head.match(/<th\b/g) || []).length;
    const first = body.slice(0, body.indexOf("</tr>") + 5);
    const got = (first.match(/<td\b/g) || []).length;
    if(got && got !== want){
      console.error("listings table: header has " + want + " columns and a row "
        + "has " + got + " — the columns will not line up. Fix the row builder ("
        + (rowFn === liveTableRow ? "liveTableRow" : "tableRow") + ").");
    }
  }
  return head + body + `</tbody></table></div>`;
}

/* SEVERAL GROUPS OF ROWS, ONE BOX.
 *
 *     "why do i have two separate boxes/borders containing the listings?"
 *
 * The live view is built as listBlock(liveRows) + listBlock(liveCatalog), and
 * every listBlock opens its own <div class="card ltwrap"> with its own header
 * row. So the screen drew two bordered cards, one after the other, with a
 * repeated Image/ASIN/Title/... header in the middle of the list and nothing to
 * say why. Measured on jack_uk: 40 rows in the first, 7 in the second.
 *
 * The intent was already ONE group -- the comment in miles_template.js says so
 * in capitals, and the captions between them were removed when the owner said
 * "i dont like that separation". Only the captions went; the two cards stayed.
 *
 * The difference between the groups is real and is marked ON THE ROW that has
 * it, which is what that same note asked for: a listing this app holds no draft
 * of is a fact about that listing, not a category of listing.
 */
function listBlocks(groups){
  const use = (groups || []).filter(g => g && g.rows && g.rows.length);
  if(!use.length) return "";
  // Tiles have no header and no table, so there is nothing to merge -- each
  // group is already just a run of cards.
  if(LIST_VIEW !== "table"){
    return use.map(g => listBlock(g.rows, g.fn)).join("");
  }
  // One header, built from every row that will be under it, so "select all"
  // means all of them and not just the first group's.
  const all = use.reduce((a, g) => a.concat(g.rows), []);
  const head = listBlock(all, use[0].fn);
  const open = head.slice(0, head.indexOf("<tbody>") + 7);
  const body = use.map(g => (g.rows || []).map(
                 g.fn === liveTile ? liveTableRow : (g.fn || tableRow)).join("")).join("");
  return open + body + `</tbody></table></div>`;
}

// The compliance cell: one icon and two words, from the SAME data the drawer's
// banner reads, so a row cannot say "clear" while its detail says "prohibited".
function _compCell(r){
  const rr = r.restricted, v = r.viability;
  if(!rr && !v) return `<span class="comp cc">—</span>`;
  if(rr && rr.matched && (rr.matches||[]).some(m=>m.tier==="PROHIBITED")){
    return `<span class="comp" style="color:var(--red)"><i class="ti ti-shield-x"></i> prohibited</span>`;
  }
  if(rr && rr.matched){
    return `<span class="comp" style="color:var(--warn)"><i class="ti ti-shield-half"></i> gated</span>`;
  }
  if(v && v.matched){
    const n = (v.risks||[]).length;
    return `<span class="comp" style="color:var(--warn)"><i class="ti ti-file-text"></i> needs docs${n?` (${n})`:""}</span>`;
  }
  return `<span class="comp" style="color:var(--ok)"><i class="ti ti-shield-check"></i> clear</span>`;
}

function _statusPill(s){
  return `<span class="badge ${badgeClass(s)}">${esc(s||"—")}</span>`;
}

// THE STATUS AS IT IS TODAY, not as it was stored.
//
// Same reason as _statusDot: a listing Amazon confirms is live is LIVE, whatever
// word the row was left with by an attempt that failed before it went up. The
// counts along the top already do this; the pill did not, so a live listing sat
// under a red API_ERROR badge and its own account said 47 were live.
function _shownStatus(r){
  try{
    const sets = _liveCatSetsForCurrentView();
    if(isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown)) return "LIVE";
  }catch(e){}
  return r.status || "";
}

function tableRow(r){
  // Same image source the tile uses, so the two views cannot disagree about
  // which picture belongs to a listing.
  const urls = (typeof _cardImages === "function") ? (_cardImages(r) || []) : [];
  const thumb = urls.length
    ? `<div class="thumb"><img src="${esc(thumbUrl(urls[0],44))}" loading="lazy" decoding="async" onerror="this.parentNode.innerHTML='<i class=&quot;ti ti-photo&quot;></i>'"></div>`
    : `<div class="thumb"><i class="ti ti-photo"></i></div>`;
  // Same three cells the tile uses, for the same reason as the image above.
  const price = _priceCell(r, "");
  const hand  = _handCell(r);
  // THE ASIN IS THE LINK. It always carried an external-link icon and was a
  // plain <span> -- an icon promising something the element could not do:
  //
  //     "no asin in the screenshot opens a product"
  //     "we should be able to open the listing by clicking on the green asin"
  //
  // stopPropagation because the row itself opens the editor; without it a
  // click would do both.
  // THE LINK MUST BE **OUR** ASIN.
  //
  //     "we should be able to open the listing by clicking on the green asin"
  //
  // -- meaning HIS listing. This linked r.asin, which on an app row is the
  // COMPETITOR ASIN out of the SKU, so the green ASIN opened the competitor's
  // product page while looking exactly like our own. Measured: 56 of 56 rows
  // with an ASIN carried the competitor's, and where we are live our real ASIN
  // is a different code entirely (B07NT77GT8 vs B0H66Q1XFK).
  //
  // A draft that is not live has no ASIN of its own, and saying so is the
  // honest answer. The competitor reference is still shown, because it is
  // genuinely useful -- it is the product this was built from -- but it is
  // labelled as such and is NOT dressed up as our listing.
  const _a = rowAsin(r);
  const asin = _a.own
    ? `<a class="asin" href="${esc(_dpUrl(_a.own))}" target="_blank" rel="noopener"
          onclick="event.stopPropagation()" style="text-decoration:none"
          title="Open your listing ${esc(_a.own)} on Amazon">${esc(_a.own)} <i class="ti ti-external-link" style="font-size:10px"></i></a>`
    : (_a.source
        ? `<span class="cc" title="This listing is not live on Amazon yet, so it has no ASIN of its own. ${esc(_a.source)} is the competitor product it was researched from — not your listing.">not live yet <span class="srcasin">· from ${esc(_a.source)}</span></span>`
        : `<span class="cc">no ASIN</span>`);
  return `<tr onclick="openDrawer('${esc(r.sku)}')" title="${esc(r.title||'')}"
              data-sku="${esc(r.sku)}"
              class="${SELECTED.has(String(r.sku)) ? 'rowon' : ''}">
    <td class="selcol">${rowSelectBox(r)}</td>
    <td class="pii-img">${thumb}</td>
    <td>${asin}<br><span class="sku pii">${esc(r.sku||'')}</span></td>
    <td><span class="ttl pii">${esc(r.title||'(no title)')}</span>
        <span class="brand pii">${_brandCell(r)}</span></td>
    <td class="price">${price}</td>
    ${cogsCell(r)}
    <td>${hand}</td>
    <td>${_statusPill(_shownStatus(r))}${needsCopy(r)
        ? `<div class="cc" style="font-size:9.5px;margin-top:3px;color:var(--warn)" `
          + `title="No bullets, no description, no product type yet. Select it and `
          + `press Regenerate copy, or open it and press Write it now.">no copy yet</div>`
        : ''}${_warnCell(r)}</td>
    <td>${_compCell(r)}</td>
    <td><div class="acts">
      <button class="btn primary" onclick="event.stopPropagation();openDrawer('${esc(r.sku)}')">Review</button>
      ${rowActions(r, "dotb")}
    </div></td></tr>`;
}

// Amazon-catalog rows: listings Amazon holds that this app has no draft of.
// They open the live editor rather than the drawer -- see _open below.
function liveTableRow(it){
  const img = it.image || it.img || "";
  const thumb = img
    ? `<div class="thumb"><img src="${esc(thumbUrl(img,44))}" loading="lazy" decoding="async" onerror="this.parentNode.innerHTML='<i class=&quot;ti ti-photo&quot;></i>'"></div>`
    : `<div class="thumb"><i class="ti ti-photo"></i></div>`;
  // Same cells the draft row and both tiles use. A catalogue row is live by
  // definition, hence the explicit true -- there is no app row to read it from.
  const _r = {sku: it.sku, asin: it.asin, title: it.title, brand: it.brand,
              handling_time: it.handling, handling_days: it.handling_days,
              price: String(it.price || "").replace(/^[A-Z]{3}\s?/, ""), row: 0};
  const price = _priceCell(_r, "", true);
  const c = it.compliance;
  const comp = (c && (c.risks||[]).length)
    ? `<span class="comp" style="color:${(c.risks||[]).some(x=>x.risk==="HIGH")?"var(--red)":"var(--warn)"}"><i class="ti ti-file-text"></i> ${c.doc_count} docs</span>`
    : `<span class="comp cc">—</span>`;
  // TEN CELLS, BECAUSE THE HEADER HAS TEN COLUMNS.
  //
  // This row had nine. It was missing the select cell that every header row
  // starts with, so in the LIVE view every column was shifted one place to the
  // left: the picture sat under the checkbox, the ASIN under "Image", the title
  // under "ASIN", and the actions under "Compliance". Reported as "in the
  // listings section i see that the header and the details under it do not
  // match".
  //
  // THE SELECT CELL WAS DELIBERATELY LEFT EMPTY, AND THAT IS NOW THE BUG.
  //
  //     "i am still not able to see the option to select all products on the
  //      page"  (reported again after the tile view was fixed)
  //
  // The reason written here was true when it was written: the bulk bar held
  // Approve and Hold, which are about DRAFTS, and offering them on a listing
  // Amazon has already published would be offering to un-approve it.
  //
  // The bar has since grown three actions that are the OPPOSITE -- set handling
  // time, set stock, change price by a percentage. Every one of those is a live
  // Amazon change, and a listing with no draft here is the purest case of it.
  // So the cell that was empty for a good reason went on being empty for none,
  // and on this account that is 46 of the 48 rows in the Live view: "Select all"
  // ticked two and looked broken, because two was genuinely all the screen
  // offered.
  //
  // A tick is offered here now, as the TILE already does. What must not follow
  // is a draft action running against a listing that has no draft -- so Approve,
  // Hold, Delete and Auto-fix split the selection first (splitByDraft) and say
  // which ones they left alone, rather than reporting them as failures.
  //
  // THE ROW STILL OPENS THE LISTING, like every other row on this screen:
  // optimizeLive pulls the live listing down from Amazon into the editor.
  //     "we can directly edit the listing by clicking on the product card"
  const _open = `optimizeLive('${esc(it.asin||'')}','${esc(it.sku||'')}')`;
  return `<tr style="cursor:pointer" title="${esc(it.title||'')}"
              data-sku="${esc(it.sku||'')}"
              class="${SELECTED.has(String(it.sku||'')) ? 'rowon' : ''}"
              onclick="${_open}">
    <td class="selcol">${rowSelectBox({sku: it.sku||''})}</td>
    <td class="pii-img">${thumb}</td>
    <td>${it.asin
        ? `<a class="asin" href="${esc(_dpUrl(it.asin))}" target="_blank" rel="noopener"
              onclick="event.stopPropagation()" style="text-decoration:none"
              title="Open ${esc(it.asin)} on Amazon">${esc(it.asin)} <i class="ti ti-external-link" style="font-size:10px"></i></a>`
        : `<span class="cc">no ASIN</span>`}<br><span class="sku pii">${esc(it.sku||'')}</span></td>
    <td><span class="ttl pii">${esc(it.title||'(no title in report)')}</span>
        <span class="brand pii">${_brandCell(it)}</span></td>
    <td class="price">${price}</td>
    ${cogsCell(it)}
    <td>${_handCell(_r, true)}</td>
    <!-- WHY THIS ROW HAS FEWER BUTTONS THAN THE ONE ABOVE IT.
         "two different types on buttons, some have review option some dont".
         Review opens the draft this app holds, and this listing has no draft --
         it is on Amazon and was never generated here. Same for the compliance
         column: there is no stored verdict to show, so it reads "—", which
         looks like a blank rather than an answer.
         The row says so now. It is one word next to LIVE, and it is the fact
         that explains every difference a reader can see. -->
    <td><span class="badge b-LIVE">LIVE</span>
        <span class="badge b-NODRAFT" title="On Amazon, but this app holds no draft of it — so there is nothing to Review and no compliance check of our own. Press Sync to pull the full listing in; price, images and Optimize work either way.">no draft here</span></td>
    <td>${comp}</td>
    <!-- ONE ACTION ROW. These seven buttons were written out here by hand, so
         the live TABLE offered Sync and Add-variant that the live TILE did not,
         and the two drifted apart the same way the two card designs had.
         rowActions is the one definition (rule 12). -->
    <td><div class="acts">${rowActions(_r, "dotb", {live: true})}</div></td></tr>`;
}

// ---- COMPLIANCE BANNER (detail view) ------------------------------------
// One full-width line at the top of the drawer giving the overall verdict, with
// the detailed panels below it. It summarises three checks that already ran --
// restricted products, document demand, and claim risks -- rather than running
// anything new, so it can never disagree with the panels underneath it.
//
// It returns NOTHING when the checks did not run. Showing "compliance clear"
// because no data arrived would be the worst possible failure here: a green
// banner asserting a check passed when it never happened. Silence is honest;
// a false all-clear is not.
/* THE ONE THING AMAZON WILL NOT CREATE A LISTING WITHOUT.
 *
 *     "i submitted a listing on amazon from the app but it shows submitted and
 *      i dont know if it is live on amazon ... where is the error message"
 *
 * It was not live, and Amazon had said why the whole time -- the barcode
 * already named another of his own listings, so it matched the submission to
 * that ASIN and refused to create a second product. The app never asked, so the
 * row sat on SUBMITTED and the reason went unread.
 *
 * This says it BEFORE the submit, from what the app already holds. Three
 * states, and only two of them can become a listing:
 *
 *   a usable barcode nobody else is using   -> quiet, nothing drawn
 *   a barcode another listing already has   -> named, with which listing
 *   no barcode and no exemption ticked      -> cannot be created
 *
 * The tick box is the owner's decision, deliberately:
 *     "i dont want to use the gtin exemption until the user wants to, he can
 *      check the button under the box apply for gtin exemption"
 * Claiming an exemption is a declaration to Amazon that a product has no
 * barcode. The app used to make it silently whenever the box was empty.
 */
function identifierPanel(r){
  const id = r.identifier;
  if(!id) return "";
  const box =
    '<label class="idexempt" style="display:flex;gap:8px;align-items:flex-start;'
    + 'margin-top:9px;font-size:12px;cursor:pointer">'
    + '<input type="checkbox" ' + (id.exemption ? "checked" : "")
    + ' onchange="setGtinExemption(' + _sarg2(r.sku) + ', this.checked)">'
    + '<span>Apply for GTIN exemption'
    + '<span class="cc" style="display:block;font-size:11px;margin-top:2px">'
    + 'Tells Amazon this product has no barcode. Only tick it if that is true '
    + '&mdash; it is a declaration, not a workaround.</span></span></label>';

  if(id.blocking){
    return '<div class="compbanner blocked"><i class="ti ti-barcode-off"></i><div>'
      + '<b>This cannot be created on Amazon yet</b>'
      + '<span class="cc">' + esc(id.note) + '</span>'
      + (id.clash && id.clash.length
          ? '<span class="cc" style="display:block;margin-top:5px">Also on: '
            + id.clash.map(function(c){
                return '<code>' + esc(c.workspace_id) + ' / ' + esc(c.sku)
                     + '</code>' + (c.live ? ' <b>(live)</b>' : '');
              }).join(", ") + '</span>'
          : '')
      + box + '</div></div>';
  }
  if(id.note){
    return '<div class="compbanner warn"><i class="ti ti-barcode"></i><div>'
      + '<b>Product identifier</b><span class="cc">' + esc(id.note) + '</span>'
      + box + '</div></div>';
  }
  // A usable barcode nobody else has needs no panel -- but the tick box still
  // has to be reachable to be UNticked, so it is shown quietly.
  return '<div class="cc" style="font-size:11.5px;margin:6px 0 2px">'
    + 'Barcode <code>' + esc(id.barcode) + '</code> &mdash; not used by any '
    + 'other listing.' + box + '</div>';
}

// The SKU as a JS string argument. listings.js has no _sarg of its own; the
// repricer's is in sourcing.js and this file must not depend on that one.
function _sarg2(s){ return "'" + String(s || "").replace(/'/g, "\\'") + "'"; }

async function setGtinExemption(sku, on){
  try{
    const j = await (await fetch("/edit", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({sku: sku, target: "col", key: "GTIN Exemption",
                            value: on ? "yes" : "",
                            account: (typeof CUR_ACCOUNT !== "undefined"
                                      && CUR_ACCOUNT) ? CUR_ACCOUNT.id : ""})
      })).json();
    if(!j || !j.ok){ toast((j && j.error) || "Could not save that"); return; }
    toast(on ? "GTIN exemption will be claimed for this listing"
             : "GTIN exemption is off for this listing");
    if(typeof refreshRow === "function") refreshRow(sku);
    else if(typeof loadRows === "function") loadRows();
  }catch(e){ toast(String(e)); }
}

function complianceBanner(r){
  const rr = r.restricted, v = r.viability, claims = r.claim_flags || [];
  if(!rr && !v && !claims.length) return "";      // nothing ran -- say nothing

  const prohibited = !!(rr && rr.matched && (rr.matches||[]).some(m=>m.tier==="PROHIBITED"));
  const gated      = !!(rr && rr.matched && !prohibited);
  const docs       = !!(v && v.matched);
  const redClaim   = claims.some(x=>x.severity==="RED");

  if(prohibited){
    return `<div class="compbanner blocked"><i class="ti ti-shield-x"></i><div>
      <b>Blocked — prohibited on this marketplace</b>
      <span class="cc">There is no compliance path for this product type. See the
      restricted-products panel below.</span></div></div>`;
  }

  if(gated || docs || redClaim){
    const parts = [];
    if(gated)    parts.push("restricted — documents required to list");
    if(docs)     parts.push(v.risks && v.risks.length === 1
                            ? "1 document demand Amazon can make later"
                            : `${(v.risks||[]).length} document demands Amazon can make later`);
    if(claims.length) parts.push(`${claims.length} claim risk${claims.length>1?"s":""}`);
    return `<div class="compbanner warn"><i class="ti ti-alert-triangle"></i><div>
      <b>Needs attention — ${esc(parts.join(" · "))}</b>
      <span class="cc">None of this blocks publishing. The panels below say
      exactly which documents and which wording.</span></div></div>`;
  }

  // Clear. Worded as "no flags", never "safe" -- these are keyword checks, and
  // the banner must not read as a clearance it is not in a position to give.
  return `<div class="compbanner clear"><i class="ti ti-shield-check"></i><div>
    <b>Compliance clear — no restricted-product or claim flags</b>
    <span class="cc">Keyword-based checks. A clean result is not a guarantee —
    a disguised product can still slip past.</span></div></div>`;
}

// ---- RESTRICTED PRODUCTS CHECK (Shape 2) -- its own panel, separate from Amazon feedback
// and from the claims-risk warning. Runs the tuned restricted-products library per listing
// (read-only, WARN only, never blocks). Clean products stay SILENT (a small quiet line) --
// no false docs warning (the doormat rule). r.restricted is attached server-side.
function _restrictedConfidence(src){
  if(src==="amazon_notice") return "verified · from your history";
  if(src==="amazon_notice_pending") return "verified · notice text pending";
  return "unverified · educated guess, confirm";
}
function restrictedPanel(r){
  const rr = r.restricted;
  if(!rr) return "";
  if(!rr.matched){
    // CLEAN: quiet, never a red/amber panel. Honest "not a clearance", not a docs warning.
    return `<div class="restclear"><i class="ti ti-shield-check"></i> Restricted products check: no known restriction matched <span class="cc">— not a clearance</span></div>`;
  }
  const anyProhibited = rr.matches.some(m=>m.tier==="PROHIBITED");
  const head = anyProhibited ? "Restricted products check — PROHIBITED"
                             : "Restricted products check — gated (docs required)";
  const rows = rr.matches.map(function(m){
    const red = m.tier==="PROHIBITED";
    const tierLbl = red ? "PROHIBITED" : (m.tier==="GATED" ? "GATED" : "RESTRICTED");
    const docs = (!red && m.docs && m.docs.length)
      ? `<div class="cc" style="margin-top:4px"><b>Docs required:</b> ${esc(m.docs.join("; "))}</div>`
      : (red ? `<div class="cc" style="margin-top:4px">No compliance path — prohibited on this marketplace.</div>` : "");
    const meta = [m.reason, m.regulator, rr.marketplace].filter(Boolean).map(esc).join(" · ");
    return `<div class="restrow ${red?'red':'amber'}">
      <div><span class="risk ${red?'hi':'med'}">${tierLbl}</span> <b>${esc(m.label)}</b>
        <span class="cc restconf">${esc(_restrictedConfidence(m.source))}</span></div>
      <div class="cc" style="margin-top:3px">${meta}</div>${docs}</div>`;
  }).join("");
  return `<details class="findingsbox" open><summary class="findsum ${anyProhibited?'bad':'info'}">${anyProhibited?'⛔':'⚠'} ${esc(head)}</summary>
    <div class="cc" style="margin:2px 0 6px;font-size:11.5px;color:var(--muted)">Your restricted-products library (SP-API-independent). Warning only — publishing is never blocked here.</div>
    <div class="restlist">${rows}</div>
    <div class="cc" style="margin-top:6px;font-size:11px;font-style:italic">${esc(rr.caveat||"")}</div></details>`;
}

// ---- COMPLIANCE REQUIREMENTS (sourcing viability) -------------------------------
// A DIFFERENT question from the restricted panel above. That one answers "may I list
// this at all?"; this one answers "which safety documents will Amazon demand later?".
// The patio heater passed every restriction check, listed freely, and cost the ASIN
// months later when Amazon asked for a BS EN 60335 test report — so a clean panel
// above is NOT evidence that nothing is owed. Server attaches r.viability.
// WARN only: nothing here blocks publishing.
function _viabRiskClass(lvl){ return lvl==="HIGH" ? "hi" : "med"; }
// Tile badge: the document count, visible WITHOUT opening the listing. The whole
// failure this fixes was a requirement nobody saw until Amazon asked.
function viabilityBadge(r){
  const v=r.viability; if(!v || !v.matched || !(v.risks||[]).length) return "";
  const high=(v.risks||[]).some(x=>x.risk==="HIGH");
  const docs=(v.risks||[]).reduce((n,x)=>n+((x.docs||[]).length),0);
  const names=(v.risks||[]).map(x=>x.label).join(", ");
  // Own class/position: .tileflag sits bottom-RIGHT (restricted) and .tileclaim
  // bottom-LEFT (claims), so a third badge reusing either would land on top of it.
  return `<span class="tiledocs ${high?'red':'amber'}" title="Compliance: ${esc(names)} — ${docs} document(s) Amazon can request. Click to see the list." onclick="event.stopPropagation();openDrawer('${esc(r.sku)}')"><i class="ti ti-file-text"></i>${docs}</span>`;
}
function viabilityPanel(r){
  const v = r.viability;
  if(!v) return "";
  if(!v.matched){
    // Clean stays quiet — same doormat rule as the restricted panel.
    return `<div class="restclear"><i class="ti ti-file-check"></i> Compliance requirements: no document demand detected <span class="cc">— not a clearance</span></div>`;
  }
  const anyHigh = (v.risks||[]).some(x=>x.risk==="HIGH");
  const head = anyHigh ? "Compliance requirements — documents Amazon will likely request"
                       : "Compliance requirements — documents Amazon may request";
  const rows = (v.risks||[]).map(function(x){
    const docs = (x.docs&&x.docs.length)
      ? `<div class="cc" style="margin-top:4px"><b>Docs required:</b><ul style="margin:4px 0 0 16px;padding:0">`
        + x.docs.map(d=>`<li>${esc(d)}</li>`).join("") + `</ul></div>`
      : "";
    const sig = (x.signals&&x.signals.length)
      ? `<div class="cc" style="margin-top:3px;color:var(--muted)">Detected: ${esc(x.signals.join("; "))}</div>` : "";
    // THE REGULATOR IS KEYED BY MARKETPLACE, not a string. It arrives as
    // {"UK": "OPSS / UKCA (BS EN 60335 series)", "US": "CPSC / UL / ETL"}, and
    // putting that through esc() printed the literal "[object Object]" beside
    // every rule on the panel. Pick the one for the marketplace being looked
    // at; fall back to naming them all rather than showing nothing, since
    // WHICH regulator can demand the paperwork is the point of the line.
    const _reg = (function(){
      const g = x.regulator;
      if(!g) return "";
      if(typeof g === "string") return g;
      const mkt = String(v.marketplace || "").toUpperCase();
      if(g[mkt]) return g[mkt];
      return Object.keys(g).map(function(k){ return k + ": " + g[k]; }).join(" · ");
    })();
    const meta = [x.reason, _reg, v.marketplace].filter(Boolean).map(esc).join(" · ");
    return `<div class="restrow ${x.risk==="HIGH"?'red':'amber'}">
      <div><span class="risk ${_viabRiskClass(x.risk)}">${esc(x.risk||"")} RISK</span> <b>${esc(x.label)}</b>
        <span class="cc restconf">${esc(x.id||"")}</span></div>
      <div class="cc" style="margin-top:3px">${meta}</div>${sig}${docs}
      <div class="cc" style="margin-top:5px;font-style:italic">As a reseller you probably cannot provide these — confirm before committing to stock.</div></div>`;
  }).join("");
  return `<details class="findingsbox" open><summary class="findsum ${anyHigh?'bad':'info'}">${anyHigh?'📄':'📄'} ${esc(head)}</summary>
    <div class="cc" style="margin:2px 0 6px;font-size:11.5px;color:var(--muted)">Not a listing restriction — this is the paperwork Amazon can demand after the listing goes live. Warning only; publishing is never blocked here.</div>
    <div class="restlist">${rows}</div>
    <div class="cc" style="margin-top:6px;font-size:11px;font-style:italic">${esc(v.caveat||"")}</div></details>`;
}

// ---- CATEGORY-AWARE CLAIM RISK (task #18 UI) -----------------------------------
// Surfaces the backend's per-hit flags (phrase/field/severity/category/rule/swap/col):
// a tile badge, in-copy highlighting, and a one-click safe rewrite the USER accepts.
// NEVER blocks publishing -- it's a loud, specific, actionable warning only. A listing
// with zero hits renders exactly as before (claimBadge/claimBox return "").
const _CLAIM_FLABEL = {title:"title", item_highlights:"highlights",
  bullet_1:"bullet 1", bullet_2:"bullet 2", bullet_3:"bullet 3", bullet_4:"bullet 4",
  bullet_5:"bullet 5", description:"description"};
function _claimFieldText(r, field){
  if(field==="title") return r.title||"";
  if(field==="item_highlights") return r.item_highlights||"";
  if(field==="description") return String(r.description||"").replace(/<[^>]+>/g," ").replace(/\s+/g," ").trim();
  const m=/^bullet_([1-5])$/.exec(field);
  if(m){ const b=r.bullets||[]; return b[(+m[1])-1]||""; }
  return "";
}
function _claimWholeWordRe(phrase){
  const p=String(phrase).replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
  return new RegExp("(?<![A-Za-z0-9])("+p+")(?![A-Za-z0-9])","gi");
}
// Escape text, THEN wrap any flagged phrase for `field` in a severity-coloured <mark>.
function claimMarkField(r, field, rawText){
  let out=esc(rawText||"");
  const hits=(r.claim_flags||[]).filter(x=>x.field===field);
  hits.forEach(h=>{
    const lvl=h.severity==="RED"?"red":"amber";
    try{ out=out.replace(_claimWholeWordRe(esc(h.phrase)),'<mark class="claimhit '+lvl+'">$1</mark>'); }catch(e){}
  });
  return out;
}
// A DRAFT WHOSE COPY HAS NOT BEEN WRITTEN YET, said out loud.
//
// "import from supplier button is drafting the listings as empty in the drafts
//  section, and no content is written in them"
//
// That is what Import Seller is meant to produce -- a skeleton carrying the
// source title, the link and the handling time, so you can decide what is worth
// spending generation credits on before spending them. domain/seller_import.py
// says so at length.
//
// But it arrives as NEEDS_REVIEW, which is the SAME status a fully written draft
// gets, so nothing on the screen told the two apart. A row with a title and
// nothing else, filed under the same label as a finished one, does not look like
// a deliberate stage of a pipeline. It looks broken.
//
// Derived from the row rather than stored as a new status: a status would have to
// be kept in step with the filters, the counts, the badge classes and the CSS,
// and "has no bullets and no description" is a fact about the row that needs no
// bookkeeping.
function needsCopy(r){
  if(!r) return false;
  if(r.status === "LIVE" || r.status === "PARENT") return false;
  const hasBullets = !!(r.bullet_1 || r.bullet_2 || r.bullet_3);
  const hasBody = !!(r.description_html || r.description);
  return !hasBullets && !hasBody;
}
function needsCopyBadge(r){
  if(!needsCopy(r)) return "";
  return `<span class="tilecopy" title="This draft has its source title and link but no copy yet — no bullets, no description, no product type. That is how Import Seller leaves things, so you can pick what is worth generating. Select it and press Regenerate copy, or open it and use Suggest." onclick="event.stopPropagation();openDrawer('${esc(r.sku)}')"><i class="ti ti-pencil-off"></i></span>`;
}
// The same fact, as a sentence with the action attached, inside the drawer.
function needsCopyPanel(r){
  if(!needsCopy(r)) return "";
  return `<div class="restclear" style="border-color:#4a3a23;background:#2a2112">`
    + `<i class="ti ti-pencil-off"></i> <b>The copy has not been written yet.</b> `
    + `This draft carries the title and the link it was imported with, and nothing `
    + `else — no bullets, no description, no product type. That is deliberate: `
    + `Import Seller leaves the writing until you have decided the item is worth `
    + `it. <button class="db-chip" style="margin-left:6px" `
    + `onclick="event.stopPropagation();batchGenerateOne('${esc(r.sku)}')">`
    + `<i class="ti ti-wand"></i> Write it now</button></div>`;
}
// One SKU through the same path the bulk button uses, so there is one way copy
// gets written and not two.
function batchGenerateOne(sku){
  SELECTED.clear(); SELECTED.add(sku);
  batchGenerate("copy");
}

function claimBadge(r){
  const f=r.claim_flags||[]; if(!f.length) return "";
  const red=f.some(x=>x.severity==="RED"); const lvl=red?"red":"amber";
  const rules=[...new Set(f.map(x=>x.rule+" ("+x.category+" category)"))].join("; ");
  const tip=f.length+" claim risk"+(f.length>1?"s":"")+": "+rules+" — click to review";
  return `<span class="tileclaim ${lvl}" title="${esc(tip)}" onclick="event.stopPropagation();openDrawer('${esc(r.sku)}')"><i class="ti ti-alert-hexagon"></i>${f.length}</span>`;
}
function claimBox(r){
  const f=r.claim_flags||[]; if(!f.length) return "";
  const red=f.some(x=>x.severity==="RED");
  const head=`<summary class="findsum ${red?'bad':'info'}">⚠ ${f.length} claim risk${f.length>1?'s':''} — ${red?'action recommended':'review'} (never blocks publishing)</summary>`;
  const rows=f.map((h,i)=>{
    const lvl=h.severity==="RED"?"red":"amber";
    const marked=claimMarkField(r,h.field,_claimFieldText(r,h.field));
    return `<div class="claimrow ${lvl}">
      <div class="claimhead">
        <span class="claimsev ${lvl}">${esc(h.severity)}</span>
        <b>${esc(h.rule)}</b> <span class="cc">(${esc(h.category)} category) · in ${esc(_CLAIM_FLABEL[h.field]||h.field)}</span>
      </div>
      <div class="claimtext">${marked}</div>
      ${h.swap?`<button class="linkbtn" onclick="toggleRewrite('${esc(r.sku)}',${i})">✎ Show safe rewrite</button>
        <div class="rewrite" id="rw_${sid(r.sku)}_${i}" style="display:none"></div>`
        :`<div class="cc" style="margin-top:4px">No direct swap — rephrase or remove this wording.</div>`}
    </div>`;
  }).join("");
  return `<details class="findingsbox claimsbox" open>${head}<div class="claimlist">${rows}</div></details>`;
}
function toggleRewrite(sku, i){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r) return;
  const box=document.getElementById("rw_"+sid(sku)+"_"+i); if(!box) return;
  if(box.style.display!=="none"){ box.style.display="none"; box.innerHTML=""; return; }
  const h=(r.claim_flags||[])[i]; if(!h||!h.swap){ return; }
  const before=_claimFieldText(r,h.field);
  let after; try{ after=before.replace(_claimWholeWordRe(h.phrase), h.swap); }catch(e){ after=before; }
  box.style.display="block";
  box.innerHTML=`<div class="rwrow"><span class="rwlbl">Before</span><div class="rwbefore">${claimMarkField(r,h.field,before)}</div></div>
    <div class="rwrow"><span class="rwlbl">After</span><div class="rwafter">${esc(after)}</div></div>
    <div class="rwacts"><button class="linkbtn ok" onclick="applyRewrite('${esc(sku)}',${i})">Apply this rewrite</button>
      <span class="cc">You accept it — nothing is changed until you click.</span></div>`;
}
async function applyRewrite(sku, i){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r) return;
  const h=(r.claim_flags||[])[i]; if(!h||!h.swap||!h.col){ toast("No target column for this field"); return; }
  const raw=(h.field==="description") ? String(r.description||"") : _claimFieldText(r,h.field);
  let val; try{ val=raw.replace(_claimWholeWordRe(h.phrase), h.swap); }catch(e){ val=raw; }
  try{
    const j=await (await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(acctBody({sku:sku, target:"col", key:h.col, value:val}))})).json();
    if(!j.ok){ toast("Save failed: "+(j.error||"")); return; }
    toast("Rewrite applied ✓ — re-screening");
    // pull the fresh row so flags recompute against the new copy
    try{
      const rr=await (await fetch(acctUrl("/row?sku="+encodeURIComponent(sku)))).json();
      if(rr&&rr.ok&&rr.row){ const k=ROWS.findIndex(x=>String(x.sku)===String(sku));
        if(k>=0) ROWS[k]=Object.assign({},ROWS[k],rr.row); }
    }catch(e){}
    try{ render(); }catch(e){}
    if(typeof DRAWER_SKU!=="undefined" && String(DRAWER_SKU)===String(sku)){ try{ openDrawer(sku); }catch(e){} }
  }catch(e){ toast("Apply failed: "+((e&&e.message)||e)); }
}

function openDrawer(sku, jumpGen){
  const r=ROWS.find(x=>String(x.sku)===String(sku));
  if(!r) return;
  // Multi-tab: make sure the workspace's active tab matches THIS card's tab before any
  // edit/approve/push (all of which target the active tab). Without this, editing a card
  // from a non-active tab could hit a duplicate SKU on the wrong tab.
  ensureCardTab(sku);
  DRAWER_SKU=sku;
  const dw=document.getElementById("drawer");
  const body=document.getElementById("drawerbody");
  body.innerHTML=drawerContent(r);
  dw.classList.add("open");
  document.getElementById("drawerscrim").classList.add("open");
  // THE DRAWER ITSELF NO LONGER SCROLLS -- its middle section does, so that the
  // header and the footer can stay put. dwScroller() is the one place that
  // answers "which element scrolls", so this and the jump below cannot drift.
  { const s=dwScroller(); if(s) s.scrollTop=0; }
  // Re-attach to any BACKGROUND Preview/Submit job for this SKU: replays its log into
  // the run panel and resumes polling if still running. This is what makes progress
  // survive navigating away and coming back (and a full page refresh).
  if(typeof rqAttach==="function"){ setTimeout(function(){ if(DRAWER_SKU===sku) rqAttach(sku); }, 60); }
  // If this product type's schema (allowed values + nested sub-fields like ghs /
  // battery) isn't loaded yet, fetch it then re-render -- otherwise required
  // nested fields render as flat boxes (or not at all) and you can't see the
  // dropdowns Amazon needs. This is what made flagged fields invisible.
  if(r.product_type && typeof loadSchemas==="function" && !(SCHEMAS[r.product_type] && (SCHEMAS[r.product_type].attrs||[]).length)){
    loadSchemas([r.product_type], false, rowMkt(r)).then(()=>{
      if(DRAWER_SKU===sku){ body.innerHTML=drawerContent(r); var sv=sid(sku);
        if(typeof rqAttach==="function"){ setTimeout(function(){ if(DRAWER_SKU===sku) rqAttach(sku); }, 60); }
        setTimeout(function(){ if(typeof bulletMeter==='function') bulletMeter(); }, 60); }
    }).catch(()=>{});
  }
  // ASK AMAZON WHAT IT HOLDS FOR THIS SKU, for a listing that is actually on
  // Amazon. One call, cached per SKU for the life of the page, so reopening the
  // same drawer costs nothing; drawer_attributes.js redraws the attribute block
  // itself when the answer lands (and only if this drawer is still open).
  // Deliberately NOT awaited: the drawer is already on screen, and a slow
  // SP-API call must never be what the person is waiting for.
  if(typeof lvEnsure==="function") lvEnsure(r);
  // populate the (always-visible) image panel's model dropdowns + run the
  // connection check, once the drawer is in place
  var sidv=sid(sku);
  setTimeout(function(){ initGenPanel(sidv); if(typeof initMilesPanel==='function') initMilesPanel(sidv); if(typeof bulletMeter==='function') bulletMeter(); }, 120);
  if(jumpGen){ setTimeout(function(){ _dwJumpToGen(sidv); }, 280); }
}

/* SCROLL TO THE IMAGE GENERATOR, OPENING ITS FOLD FIRST.
 *
 * The generator now lives inside a collapsed <details>. A closed details has
 * no laid-out height, so offsetTop reads 0 and the drawer scrolls to the top
 * instead of to the panel -- which looks exactly like the button doing
 * nothing. Open it, then measure.
 *
 * Written once because two callers want it: openDrawer(sku, jumpGen) and
 * openGenPanelInDrawer(). */
function _dwJumpToGen(sidv){
  var anchor=document.getElementById('genimg_'+sidv);
  if(!anchor) return false;
  var fold=anchor.closest('details');
  if(fold && !fold.open) fold.open=true;
  var sc=dwScroller();
  if(sc){
    var top=anchor.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop;
    sc.scrollTo({top: Math.max(0, top - 12), behavior:'smooth'});
  }
  return true;
}
// Shared OpenRouter connection tester: NEVER hangs (12s timeout) and writes a
// clear, specific status into the given diag element so the user knows exactly
// what's wrong (missing key / bad key / discovery / network / app unreachable).
async function _orTestInto(diag){
  if(!diag) return null;
  diag.className='gendiag'; diag.textContent='Checking OpenRouter connection…';
  let t=null;
  try{
    const ctrl=new AbortController();
    const timer=setTimeout(()=>ctrl.abort(), 12000);   // 12s hard cap, no infinite hang
    let resp;
    try{ resp=await fetch('/ai/test',{signal:ctrl.signal}); }
    finally{ clearTimeout(timer); }
    t=await resp.json();
  }catch(e){
    diag.className='gendiag bad';
    diag.textContent = (e&&e.name==='AbortError')
      ? '\u2717 OpenRouter check timed out (12s). Likely a slow or blocked connection to openrouter.ai — check your internet/VPN, then reopen this panel.'
      : '\u2717 Could not reach the app to test OpenRouter (is the app still running?).';
    return null;
  }
  if(t&&t.ok){
    diag.className='gendiag ok';
    diag.textContent='\u2713 OpenRouter ready \u2014 image model: '+(t.image_model||'?')+' ('+(t.image_count||0)+' image models available)';
  } else {
    diag.className='gendiag bad';
    const stage=(t&&t.stage)||'';
    const base='\u2717 '+((t&&t.error)||'OpenRouter not ready');
    const tip = stage==='key'     ? ' \u2014 add your real openrouter_api_key to config.json and restart the app.'
              : stage==='discover'? ' \u2014 the key was found but OpenRouter rejected it or returned no models. Check the key is valid/active at openrouter.ai/keys.'
              :                     ' \u2014 reopen this panel to retry.';
    diag.textContent=base+tip;
  }
  return t;
}
async function initGenPanel(sidv){
  var s=await loadAISettings();
  // If the cached settings have no image models yet (discovery hadn't finished
  // on first page load), force a fresh discovery so the dropdowns populate.
  if(!s || !s.ok || !(s.image_models && s.image_models.length)){
    try{
      AISET=null;
      s=await (await fetch('/ai/settings?refresh=1')).json();
      AISET=s;
    }catch(e){}
  }
  if(s&&s.ok){
    fillModelSelect(document.getElementById('gentai_'+sidv), s.text_models, s.select.prompt_enhance);
    fillModelSelect(document.getElementById('geniai_'+sidv), s.image_models, s.select.image_generate);
  }
  var diag=document.getElementById('gendiag_'+sidv);
  await _orTestInto(diag);
}
function closeDrawer(){
  DRAWER_SKU=null;
  window.RUN_STREAMING=false;
  if(ES){ try{ES.close();}catch(e){} ES=null; }
  // Stop WATCHING any background Preview/Submit job -- but DON'T stop the job itself.
  // It keeps running on the server; reopening the drawer re-attaches to its progress.
  if(typeof rqStopWatch==="function") rqStopWatch();
  document.getElementById("drawer").classList.remove("open");
  document.getElementById("drawerscrim").classList.remove("open");
}
function tileMenu(ev, sku, row){
  ev.stopPropagation();
  // simple context menu
  closeTileMenu();
  const m=document.createElement("div"); m.className="tilemenu"; m.id="tilemenu";
  m.innerHTML=`
    <button onclick="setStatus('${esc(sku)}','NEEDS_REVIEW',this);closeTileMenu()"><i class="ti ti-player-pause"></i> Hold</button>
    <button onclick="askAbout('${esc(sku)}');closeTileMenu()"><i class="ti ti-message-circle"></i> Ask Claude</button>
    <button onclick="openDrawer('${esc(sku)}');closeTileMenu()"><i class="ti ti-edit"></i> Edit details</button>
    <button class="danger" onclick="delRow('${esc(sku)}',${row},this);closeTileMenu()"><i class="ti ti-trash"></i> Delete</button>`;
  document.body.appendChild(m);
  const rect=ev.target.closest("button").getBoundingClientRect();
  m.style.top=(rect.bottom+4)+"px";
  m.style.left=Math.min(rect.left, window.innerWidth-180)+"px";
  setTimeout(()=>document.addEventListener("click",closeTileMenu,{once:true}),0);
}
function closeTileMenu(){ const m=document.getElementById("tilemenu"); if(m) m.remove(); }

/* THE DRAWER'S OVERFLOW: everything that was demoted off the action bar.
 *
 * Same .tilemenu component the card already uses, so this is one menu style in
 * the app rather than a second one invented for the drawer.
 *
 * None of these was deleted. Each failed the "does something else already do
 * this?" test as a FRONT-ROW control, not as a capability:
 *
 *   Refresh dropdowns   openDrawer fetches a missing schema by itself. This is
 *                       for the rarer case where Amazon CHANGED the type, and it
 *                       is the only way to clear a stale one.
 *   Pull live images    Sync does the whole account; this does one row.
 *   Push image to live  the Image Library does this, and shows you what you are
 *   Upload main image   pushing first.
 *   Delete              destructive, and it sat between Ask Claude and the edge.
 */
function drawerMore(ev, sku, row, isLive){
  ev.stopPropagation();
  closeTileMenu();
  const m = document.createElement("div");
  m.className = "tilemenu"; m.id = "tilemenu";
  m.innerHTML =
    `<button onclick="refreshSchemaFor('${esc(sku)}');closeTileMenu()" title="Re-fetch Amazon's allowed values for this product type. Use it when a dropdown is missing an option you know exists — it does NOT touch your listing's own data."><i class="ti ti-refresh"></i> Refresh dropdown options</button>`
    + `<button onclick="openImageLibrary('${esc(sku)}', ${isLive ? "true" : "false"});closeTileMenu()" title="Every image this listing has: upload your own, pick the main one, push one live"><i class="ti ti-library-photo"></i> Image library</button>`
    + (isLive
        ? `<button onclick="pullLiveRow('${esc(sku)}',this);closeTileMenu()" title="Fetch this listing's real images from Amazon and replace the generation-time ones. Sync does this for every listing at once."><i class="ti ti-cloud-download"></i> Pull live images</button>`
        + `<button onclick="pushImageLive('${esc(sku)}',this);closeTileMenu()" title="Send the current main image to the live Amazon listing — the image only, no resubmit"><i class="ti ti-cloud-upload"></i> Push main image live</button>`
        : "")
    + `<button class="danger" onclick="delRow('${esc(sku)}',${row||0},this);closeTileMenu()"><i class="ti ti-trash"></i> Delete listing</button>`;
  document.body.appendChild(m);
  const btn = ev.target.closest("button");
  const rect = btn.getBoundingClientRect();
  m.style.top = (rect.bottom + 4) + "px";
  // RIGHT-ALIGNED TO THE BUTTON. The drawer is pinned to the right edge, so a
  // menu laid out leftwards from here would open off the screen.
  m.style.left = Math.max(8, Math.min(rect.right - 232,
                                      window.innerWidth - 240)) + "px";
  setTimeout(() => document.addEventListener("click", closeTileMenu, {once: true}), 0);
}
function openGenPanelInDrawer(sku){
  try{
    var sidv=sid(sku);
    if(!_dwJumpToGen(sidv)){ toast("Image panel not found \u2014 try reopening the drawer"); return; }
    initGenPanel(sidv);
  }catch(e){ toast("Could not open image panel: "+e); }
}
function openGenFromHead(sku){ openStudioSingle(sku); }

function _fileToDataURL(file){
  return new Promise(function(res,rej){
    var fr=new FileReader(); fr.onload=function(){res(fr.result);}; fr.onerror=rej; fr.readAsDataURL(file);
  });
}
async function uploadRef(input, sku, sidv){
  var file=input.files&&input.files[0]; if(!file) return;
  var st=document.getElementById('genstatus_'+sidv); if(st) st.textContent='Uploading reference…';
  try{
    var dataUrl=await _fileToDataURL(file);
    var res=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,data:dataUrl,name:file.name,kind:'ref'})});
    var j=await res.json();
    if(!j.ok){ if(st) st.textContent='Upload failed: '+(j.error||''); return; }
    var fld=document.getElementById('genraw_'+sidv); if(fld) fld.value=j.url;
    if(st) st.innerHTML='<span style="color:var(--ok)">\u2713 Reference uploaded \u2014 saved to this SKU\u2019s media folder.</span>';
  }catch(e){ if(st) st.textContent='Upload error: '+e; }
}

