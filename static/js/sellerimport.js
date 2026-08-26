// ===================== IMPORT AN eBAY SELLER =====================
// Find a seller's catalogue, look at it, screen it, draft what you want.
//
// The review grid shows the MAIN IMAGE of every item, because a list of titles
// gets ticked through without being read and you cannot tell from a title
// whether you want to sell something. Everything starts ticked -- the usual case
// is wanting most of a range and rejecting a few -- and the count is confirmed
// before anything is written.
//
// Nothing here reaches Amazon. Drafting writes rows into this app; publishing is
// the approve-and-submit path you already have.

let SIMP = {seller: "", rows: [], meta: null, screened: false, busy: false};

function _siEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function _siBody(o){
  const b = Object.assign({}, o || {});
  if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id) b.id = CUR_ACCOUNT.id;
  if(typeof WS_MARKET !== "undefined" && WS_MARKET) b.marketplace = WS_MARKET;
  return JSON.stringify(b);
}

function sellerImportOnOpen(){ sellerImportRender(); }

function sellerImportRender(){
  const host = document.getElementById("simpbody");
  if(!host) return;
  let h = '<div class="cc" style="font-size:12px;margin:2px 0 12px;padding:9px 11px;'
    + 'border:1px solid #26303f;border-radius:6px">'
    + 'Find everything an eBay seller lists, look through it with the pictures, '
    + 'and draft the ones you want. <b>Nothing is sent to Amazon</b> — the ones '
    + 'you keep become drafts here, and you publish them the usual way.</div>';

  h += '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px">'
    + '<input id="simp_seller" placeholder="eBay username, or a link to any of their items" '
    + 'value="'+_siEsc(SIMP.seller)+'" '
    + 'style="font-size:13px;padding:6px 10px;min-width:320px;flex:1;max-width:520px" '
    + 'onkeydown="if(event.key===\'Enter\')sellerFind()">'
    + '<button class="db-chip" onclick="sellerFind()"><i class="ti ti-search"></i> Find their items</button>'
    + '</div>';
  // The shopfront name and the username are DIFFERENT things and eBay's API only
  // knows the second. Said here rather than left to be discovered, because when
  // it is wrong eBay does not say so -- it answers with its whole catalogue.
  h += '<div class="cc" style="font-size:11.5px;margin:0 0 12px">'
    + 'The <b>username</b>, not the shop name — they are often different. '
    + 'A shop at <code>ebay.co.uk/str/…</code> shows the shop name; the username '
    + 'is on any of their listings under “Sold by”. '
    + 'Easiest: <b>paste a link to anything they are selling</b> and the username '
    + 'is read off it.</div>';

  h += '<div id="simp_results"></div>';
  host.innerHTML = h;
  if(SIMP.rows.length) sellerImportResults();
}

async function sellerFind(){
  const el = document.getElementById("simp_seller");
  const seller = (el && el.value || "").trim();
  if(!seller){ toast("Type an eBay seller name first."); return; }
  const out = document.getElementById("simp_results");
  if(out) out.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> '
    + 'Searching eBay for this seller — several passes, so give it a moment…</div>';
  SIMP.seller = seller; SIMP.screened = false;
  try{
    const j = await (await fetch("/seller/find",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_siBody({seller:seller})})).json();
    if(!j.ok){ if(out) out.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'
        +_siEsc(j.error||"Could not search")+'</div>'; return; }
    SIMP.rows = j.rows || []; SIMP.meta = j;
    // A pasted link comes back resolved to the username. Put it in the box so
    // it is visible, reusable, and obviously what was actually searched for.
    if(j.seller && j.seller !== seller){
      SIMP.seller = j.seller;
      const box = document.getElementById("simp_seller");
      if(box) box.value = j.seller;
      toast("That link belongs to " + j.seller + " — searched for them.");
    }
    sellerImportResults();
  }catch(e){
    if(out) out.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'+_siEsc(String(e))+'</div>';
  }
}

function _siCount(){ return SIMP.rows.filter(r => r.selected).length; }

const _SI_VERDICT = {
  blocked: {c:"#e88a8a", t:"Amazon will not let you list this"},
  docs:    {c:"#e8c66a", t:"listable, but paperwork will be demanded"},
  caution: {c:"#e8c66a", t:"worth a look before you spend on it"},
  unknown: {c:"#8b949e", t:"could not be checked — not the same as fine"},
  clear:   {c:"#8fd694", t:"nothing against it"},
};

function sellerImportResults(){
  const out = document.getElementById("simp_results");
  if(!out) return;
  const m = SIMP.meta || {};
  let h = '';

  // What "found" means. Said plainly, every time, because it is a floor and not
  // a total and the difference is how items go missing unnoticed.
  h += '<div class="cc" style="font-size:12px;margin-bottom:10px;padding:9px 11px;'
    + 'border:1px solid #3a3320;background:#241f10;border-radius:6px">'
    + '<i class="ti ti-info-circle"></i> '+_siEsc(m.note||"")+'</div>';

  // THE SCREENING RESULT, STANDING. Stays until the next check replaces it.
  const _ss = SIMP.screenSummary;
  if(_ss){
    const c = _ss.counts || {};
    const bits = [
      {k:"blocked", t:"blocked by Amazon", col:"#e88a8a"},
      {k:"docs",    t:"need documents",    col:"#e8c66a"},
      {k:"caution", t:"worth a look",      col:"#e8c66a"},
      {k:"unknown", t:"could not be checked", col:"#8b949e"},
      {k:"clear",   t:"nothing against them", col:"#8fd694"},
    ].filter(x => c[x.k]);
    h += '<div style="border:1px solid #26303f;border-radius:8px;padding:10px 12px;'
      +  'margin-bottom:10px;background:var(--panel2,rgba(255,255,255,.02))">'
      +  '<div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">'
      +  '<b style="font-size:12.5px"><i class="ti ti-shield-check"></i> '
      +  'Checked ' + _ss.checked + ' of ' + _ss.of + '</b>'
      +  '<span class="cc" style="font-size:11px">' + _siEsc(_ss.when) + '</span>'
      +  (_ss.failed ? '<span style="color:var(--warn);font-size:11px">'
                       + _ss.failed + ' could not be sent — press the button '
                       + 'again to retry those</span>' : '')
      +  '</div>'
      +  '<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:6px;font-size:11.5px">'
      +  bits.map(x => '<span style="color:'+x.col+'"><b>'+c[x.k]+'</b> '
                       + _siEsc(x.t)+'</span>').join("")
      +  '</div>'
      +  '<div class="cc" style="font-size:11px;margin-top:6px">'
      +  'Click any tile below to read exactly why — the reasons are carried onto '
      +  'the draft, so they are still there when you come back to it.</div>'
      +  '</div>';
  }

  h += '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">'
    + '<button class="db-chip" onclick="sellerAll(true)">Select all</button>'
    + '<button class="db-chip" onclick="sellerAll(false)">Select none</button>'
    + '<span class="cc" style="font-size:11.5px" id="simp_count">'
    + _siCount()+' of '+SIMP.rows.length+' selected</span>'
    + '<span style="flex:1"></span>'
    + '<button class="db-chip" onclick="sellerScreen(this)">'
    + '<i class="ti ti-shield-check"></i> Check what Amazon allows</button>'
    + '<button class="db-chip btn-primary" '
    + 'onclick="sellerDraft()">Draft the selected</button>'
    + '</div>'
    // Where the count moves while a long check runs. Outside the button, because
    // the button is re-rendered as results come in and would lose its own text.
    + '<div id="simp_progress" class="cc" style="display:none;font-size:11.5px;'
    + 'margin:-4px 0 10px;padding:7px 10px;border:1px solid #26303f;'
    + 'border-radius:6px"></div>';

  if(!SIMP.rows.length){
    h += '<div class="cc" style="padding:20px;border:1px dashed #2a3446;border-radius:6px">'
      + 'Nothing found for that seller. Check the username — it is the eBay '
      + 'user id, not their shop name.</div>';
    out.innerHTML = h; return;
  }

  h += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px">';
  SIMP.rows.forEach(function(r, i){
    const v = (r.screen||{}).verdict;
    const meta = _SI_VERDICT[v];
    h += '<label style="border:1px solid '+(r.selected?'var(--accent)':'var(--line)')
      + ';border-radius:8px;overflow:hidden;background:var(--panel);cursor:pointer;'
      + 'display:flex;flex-direction:column">'
      + '<div style="position:relative">'
      + '<img src="'+_siEsc(r.image)+'" loading="lazy" '
      + 'style="width:100%;height:130px;object-fit:contain;background:#0d1220;display:block">'
      + '<input type="checkbox" '+(r.selected?'checked':'')
      + ' onchange="sellerPick('+i+',this.checked)" '
      + 'style="position:absolute;top:7px;left:7px;width:17px;height:17px">'
      + (r.is_group ? '<span class="db-chip" style="position:absolute;top:6px;right:6px;'
                    + 'font-size:9.5px" title="eBay lists this as a variation family">'
                    + 'variations</span>' : '')
      + '</div>'
      + '<div style="padding:7px 8px;flex:1;display:flex;flex-direction:column;gap:3px">'
      + '<div style="font-size:11.5px;line-height:1.3;max-height:44px;overflow:hidden" '
      + 'title="'+_siEsc(r.title)+'">'+_siEsc(r.title)+'</div>'
      + '<div class="cc" style="font-size:11px">'
      + (r.price==null?'—':Number(r.price).toFixed(2))
      + (r.shipping!=null && r.shipping>0 ? ' + '+Number(r.shipping).toFixed(2)+' post' : '')
      + (r.category ? ' · '+_siEsc(r.category) : '')+'</div>'
      // THE VERDICT, AND A WAY TO READ IT. A tooltip is not a record: it needs a
      // steady hand, disappears on the way to anything else, and does not exist
      // at all on a phone. The reasons -- which documents Amazon will demand,
      // which rule flagged it, why it could not be checked -- are the whole
      // point of running the check, so they open in place and stay open.
      + (meta
          ? '<div onclick="event.preventDefault();event.stopPropagation();sellerWhy('+i+')" '
            + 'style="font-size:10.5px;color:'+meta.c+';cursor:pointer;'
            + 'text-decoration:underline dotted;text-underline-offset:2px" '
            + 'title="Click to read the full reasons">'
            + _siEsc(v)+' — '+_siEsc(meta.t)
            + (((r.screen||{}).notes||[]).length
                ? ' <b>(' + (r.screen.notes.length) + ')</b>' : '')
            + '</div>'
            + '<div id="siwhy_'+i+'" style="display:none;font-size:10.5px;'
            + 'border-top:1px solid #26303f;margin-top:4px;padding-top:4px;'
            + 'line-height:1.5">'
            + (((r.screen||{}).notes||[]).length
                ? r.screen.notes.map(function(n){
                    return '<div style="margin-bottom:3px">• '+_siEsc(n)+'</div>'; }).join("")
                : '<div class="cc">Nothing was recorded against this one.</div>')
            + '</div>'
          : '')
      + '<a href="'+_siEsc(r.url)+'" target="_blank" rel="noopener" '
      + 'onclick="event.stopPropagation()" class="cc" style="font-size:10.5px">on eBay ↗</a>'
      + '</div></label>';
  });
  h += '</div>';
  out.innerHTML = h;
}

// Open one item's reasons in place. Toggles, so several can be read at once and
// compared -- which is what you are actually doing when deciding what to draft.
function sellerWhy(i){
  const el = document.getElementById("siwhy_" + i);
  if(el) el.style.display = (el.style.display === "none") ? "" : "none";
}

function sellerPick(i, on){
  if(SIMP.rows[i]) SIMP.rows[i].selected = !!on;
  const c = document.getElementById("simp_count");
  if(c) c.textContent = _siCount()+' of '+SIMP.rows.length+' selected';
}
function sellerAll(on){
  SIMP.rows.forEach(function(r){ r.selected = !!on; });
  sellerImportResults();
}

// Screened in batches, with the count moving.
//
// It used to be ONE request carrying every selected row. Measured against the
// real endpoint: 200 rows 2.2s, 1000 rows 12s, 5000 rows 59s on a 2.85MB POST.
// A minute of a disabled button with no number changing is indistinguishable
// from a dead button -- which is exactly what it was reported as -- and behind a
// hosting proxy that request does not slowly succeed, it times out and the whole
// check is lost. Batches of 200 come back in about two seconds each, so
// something moves on screen continuously and one failure costs one batch.
const SI_BATCH = 200;

async function sellerScreen(btn){
  const sel = SIMP.rows.filter(r => r.selected);
  if(!sel.length){ toast("Nothing selected — tick at least one item first."); return; }
  const label = '<i class="ti ti-shield-check"></i> Check what Amazon allows';
  if(btn) btn.disabled = true;
  const bar = document.getElementById("simp_progress");
  const say = function(msg){
    if(bar){ bar.style.display = ""; bar.innerHTML = msg; }
    if(btn) btn.innerHTML = '<span class="genspin"></span> ' + msg.replace(/<[^>]+>/g, "");
  };

  const totals = {blocked: 0, docs: 0, caution: 0, unknown: 0, clear: 0};
  let done = 0, failed = 0;
  try{
    for(let i = 0; i < sel.length; i += SI_BATCH){
      const chunk = sel.slice(i, i + SI_BATCH);
      say("Checking " + (done + 1) + "–" + Math.min(done + chunk.length, sel.length)
          + " of " + sel.length + "…");
      let j;
      try{
        j = await (await fetch("/seller/screen",{method:"POST",
          headers:{"Content-Type":"application/json"},
          body:_siBody({rows:chunk})})).json();
      }catch(err){ j = null; }
      if(!j || !j.ok){
        // One batch failing does not throw away the ones that worked.
        failed += chunk.length;
        done += chunk.length;
        continue;
      }
      const by = {};
      (j.rows||[]).forEach(function(r){ by[r.item_id] = r.screen; });
      SIMP.rows.forEach(function(r){ if(by[r.item_id]) r.screen = by[r.item_id]; });
      const c = (j.summary || {}).counts || {};
      Object.keys(totals).forEach(function(k){ totals[k] += (c[k] || 0); });
      done += chunk.length;
      // Redrawn as it goes, so the verdicts appear while the rest is still running.
      sellerImportResults();
    }
    SIMP.screened = true;
    // KEPT ON SCREEN, not announced and lost.
    //
    // The result arrived as a toast, which fades after a few seconds. Click
    // anywhere and the answer to "which of these needs documents, and which
    // documents" was gone with no way back to it -- on the one screen whose
    // whole purpose is deciding what is safe to spend generation credits on.
    // The summary now stays until the next check, and every verdict is
    // openable on its own tile.
    SIMP.screenSummary = {
      counts: totals, checked: done - failed, of: sel.length, failed: failed,
      when: new Date().toLocaleString(),
    };
    if(bar){ bar.style.display = "none"; }
    sellerImportResults();
  }catch(e){
    toast(String(e));
    if(bar){ bar.style.display = "none"; }
  }
  finally{ if(btn){ btn.disabled = false; btn.innerHTML = label; } }
}

async function sellerDraft(){
  const sel = SIMP.rows.filter(r => r.selected);
  if(!sel.length){ toast("Nothing selected."); return; }
  const blocked = sel.filter(r => (r.screen||{}).verdict === "blocked").length;
  const fams = sel.filter(r => r.is_group).length;
  let msg = "Draft "+sel.length+" item"+(sel.length===1?"":"s")+" into this app?\n\n"
          + "They arrive as drafts to review — nothing is sent to Amazon.";
  // A family is not one product. eBay lists up to a few hundred variations under
  // one listing, so "12 items" can mean 400 drafts -- and each of those costs
  // generation spend later. Said BEFORE the click; the exact number comes back
  // from the server, which is the only side that can count them.
  if(fams){
    msg += "\n\n" + fams + " of these " + (fams===1?"is a":"are") + " variation "
         + "listing" + (fams===1?"":"s") + " on eBay. Each becomes a parent plus "
         + "one draft per variation — so the real total will be higher, and you "
         + "will be told the number before anything more is written.";
  }
  if(!SIMP.screened){
    msg += "\n\nYou have not checked what Amazon allows yet. Drafting something "
         + "blocked spends generation credits on a listing that can never be "
         + "published.";
  }
  if(blocked){
    msg += "\n\n" + blocked + " of these are BLOCKED by Amazon and will be refused.";
  }
  if(!await uiConfirm(msg)) return;
  await _siDraft(sel, {});
}

// Separated so the "that is more drafts than you thought" answer can retry with
// a raised ceiling WITHOUT re-asking the first question.
async function _siDraft(sel, extra){
  try{
    const body = Object.assign({confirmed:true, rows:sel}, extra||{});
    const j = await (await fetch("/seller/draft",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_siBody(body)})).json();
    if(!j.ok){
      // The server counted the expanded families and it is over the ceiling.
      // A real number, asked about once, rather than a silent cap.
      if(j.would_draft){
        if(await uiConfirm(j.error + "\n\nDraft all " + j.would_draft + "?")){
          return _siDraft(sel, Object.assign({}, extra||{},
                                             {max_drafts: j.would_draft}));
        }
        return;
      }
      toast(j.error||"Could not draft"); return;
    }
    (j.families||[]).forEach(function(n){ console.log("[seller import] "+n); });
    let m = "Drafted "+j.drafted;
    if(j.enrolled) m += ", "+j.enrolled+" now watched by the repricer";
    toast(m+" — "+(j.note||""));
    if((j.errors||[]).length){
      toast((j.errors||[]).length+" could not be drafted: "
            + (j.errors[0].error||""));
    }
    if(typeof loadRows === "function") loadRows();
  }catch(e){ toast(String(e)); }
}
