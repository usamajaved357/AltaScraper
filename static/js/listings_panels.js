// static/js/listings_panels.js -- identifier, compliance, restricted, viability and claims panels. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

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
  // ONE SMALL TICK BOX, the owner's PDP redesign (26 Sep 2026): the three-line
  // explanation under it became its hover text. The words did not go -- ticking
  // it is still a DECLARATION to Amazon (CLAUDE.md Rule 1), and the tooltip says
  // so in full; they just stopped taking three lines on every listing.
  const box =
    '<label class="idexempt" title="Apply for GTIN exemption. Tells Amazon this '
    + 'product has no barcode. Only tick it if that is true &mdash; '
    + 'it is a declaration, not a workaround.">'
    + '<input type="checkbox" ' + (id.exemption ? "checked" : "")
    + ' onchange="setGtinExemption(' + _sarg2(r.sku) + ', this.checked)">'
    + ' GTIN exempt</label>';

  // Every other listing carrying this barcode -- drafts as well as live ones.
  // Shown on both banners: a draft clash used to get no list at all.
  const clashes = (id.clash && id.clash.length) ? id.clash : [];
  const alsoOn = clashes.length
    ? '<span class="cc" style="display:block;margin-top:5px">Also on: '
      + clashes.map(function(c){
          return '<code>' + esc(c.workspace_id) + ' / ' + esc(c.sku)
               + '</code>' + (c.live ? ' <b>(live)</b>' : ' (not live yet)');
        }).join(", ") + '</span>'
    : '';

  if(id.blocking){
    return '<div class="compbanner blocked"><i class="ti ti-barcode-off"></i><div>'
      + '<b>This cannot be created on Amazon yet</b>'
      + '<span class="cc">' + esc(id.note) + '</span>'
      + alsoOn + box + '</div></div>';
  }
  if(id.note || clashes.length){
    return '<div class="compbanner warn"><i class="ti ti-barcode"></i><div>'
      + '<b>Product identifier</b><span class="cc">'
      + esc(id.note || id.clash_note || "This barcode is on another listing too.")
      + '</span>' + alsoOn + box + '</div></div>';
  }
  // A usable barcode nobody else has: ONE LINE, as the redesign drew it --
  // "[barcode] 4545383792648 — unique, not used elsewhere  ☐ GTIN exempt". The
  // tick box stays reachable so it can be UNticked. Only reached when `clashes`
  // is empty, so it cannot say this about a shared barcode.
  return '<div class="idline"><i class="ti ti-barcode"></i>'
    + '<span><b>' + esc(id.barcode) + '</b> &mdash; '
    + '<span class="idunique" title="Not used by any other listing in this app.">'
    + 'unique, not used elsewhere</span></span>'
    + '<span class="idline-sp"></span>' + box + '</div>';
}

// The SKU as a JS string argument. listings.js has no _sarg of its own; the
// repricer's is in sourcing.js and this file must not depend on that one.
// ONE escaper for a value inside an inline handler: jsArg, in users.js (Rule 12,
// Milestone 2). This name is kept for its callers.
function _sarg2(s){ return jsArg(s || ""); }

/* setGtinExemption MOVED TO static/js/gtin.js.
 *
 * The tick box above still calls it by name (the onchange is resolved when it
 * is clicked, so which file it lives in does not matter). It moved because the
 * owner asked for a second way to claim the exemption -- several selected
 * drafts at once -- and two ways of writing the same declaration to Amazon,
 * living in two files, is exactly the duplication Rule 12 forbids. gtin.js
 * holds the single write and both routes into it. */

function complianceBanner(r){
  const rr = r.restricted, v = r.viability, claims = r.claim_flags || [];
  if(!rr && !v && !claims.length) return "";      // nothing ran -- say nothing

  const prohibited = !!(rr && rr.matched && (rr.matches||[]).some(m=>m.tier==="PROHIBITED"));
  const gated      = !!(rr && rr.matched && !prohibited);
  const docs       = !!(v && v.matched);
  const redClaim   = claims.some(x=>x.severity==="RED");

  // ONE LINE EACH, the owner's PDP redesign (26 Sep 2026). What the second
  // line used to say is on hover, not deleted -- in particular that a clear
  // result is a KEYWORD check and not a clearance.
  if(prohibited){
    return `<div class="compline bad" title="There is no compliance path for this product type. See the restricted-products panel in Safety &amp; Compliance.">
      <i class="ti ti-shield-x"></i><span><b>Prohibited</b> — blocked on this marketplace</span></div>`;
  }

  if(gated || docs || redClaim){
    const parts = [];
    if(gated)    parts.push("restricted");
    if(docs)     parts.push((v.risks||[]).length === 1
                            ? "1 document demand" : `${(v.risks||[]).length} document demands`);
    if(claims.length) parts.push(`${claims.length} claim risk${claims.length>1?"s":""}`);
    const flags = (gated ? 1 : 0) + (docs ? (v.risks||[]).length : 0) + claims.length;
    return `<div class="compline ${gated ? "bad" : "warn"}" title="${esc(parts.join(" · "))}. None of this blocks publishing. Safety &amp; Compliance says exactly which documents and which wording.">
      <i class="ti ti-shield-half"></i><span><b>${gated ? "Restricted" : "Needs attention"}</b> — ${flags} flag${flags === 1 ? "" : "s"}</span></div>`;
  }

  // Clear. Worded as "no restrictions or claims", never "safe" -- these are
  // keyword checks, and the line must not read as a clearance it is not in a
  // position to give. The hover says so.
  return `<div class="compline ok" title="Keyword-based checks. A clean result is not a guarantee — a disguised product can still slip past.">
    <i class="ti ti-shield-check"></i><span><b>Clear</b> — no restrictions or claims</span></div>`;
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
  return `<span class="tiledocs ${high?'red':'amber'}" title="Compliance: ${esc(names)} — ${docs} document(s) Amazon can request. Click to see the list." onclick="event.stopPropagation();openListingAt(${jsArg(r.sku)},'compliance')"><i class="ti ti-file-text"></i>${docs}</span>`;
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
  return `<span class="tilecopy" title="This draft has its source title and link but no copy yet — no bullets, no description, no product type. That is how Import Seller leaves things, so you can pick what is worth generating. Select it and press Regenerate copy, or open it and use Suggest." onclick="event.stopPropagation();openListingAt(${jsArg(r.sku)},'details')"><i class="ti ti-pencil-off"></i></span>`;
}
// The same fact, as a sentence with the action attached, inside the drawer.
function needsCopyPanel(r){
  if(!needsCopy(r)) return "";
  return `<div class="restclear" style="border-color:var(--warn-line);background:var(--warn-bg)">`
    + `<i class="ti ti-pencil-off"></i> <b>The copy has not been written yet.</b> `
    + `This draft carries the title and the link it was imported with, and nothing `
    + `else — no bullets, no description, no product type. That is deliberate: `
    + `Import Seller leaves the writing until you have decided the item is worth `
    + `it. <button class="db-chip" style="margin-left:6px" `
    + `onclick="event.stopPropagation();batchGenerateOne(${jsArg(r.sku)})">`
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
  return `<span class="tileclaim ${lvl}" title="${esc(tip)}" onclick="event.stopPropagation();openListingAt(${jsArg(r.sku)},'compliance')"><i class="ti ti-alert-hexagon"></i>${f.length}</span>`;
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
      ${h.swap?`<button class="linkbtn" onclick="toggleRewrite(${jsArg(r.sku)},${i})">✎ Show safe rewrite</button>
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
    <div class="rwacts"><button class="linkbtn ok" onclick="applyRewrite(${jsArg(sku)},${i})">Apply this rewrite</button>
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
