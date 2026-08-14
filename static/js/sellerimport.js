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

  h += '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px">'
    + '<input id="simp_seller" placeholder="eBay seller username" value="'+_siEsc(SIMP.seller)+'" '
    + 'style="font-size:13px;padding:6px 10px;min-width:220px" '
    + 'onkeydown="if(event.key===\'Enter\')sellerFind()">'
    + '<button class="db-chip" onclick="sellerFind()"><i class="ti ti-search"></i> Find their items</button>'
    + '</div>';

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

  h += '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">'
    + '<button class="db-chip" onclick="sellerAll(true)">Select all</button>'
    + '<button class="db-chip" onclick="sellerAll(false)">Select none</button>'
    + '<span class="cc" style="font-size:11.5px" id="simp_count">'
    + _siCount()+' of '+SIMP.rows.length+' selected</span>'
    + '<span style="flex:1"></span>'
    + '<button class="db-chip" onclick="sellerScreen(this)">'
    + '<i class="ti ti-shield-check"></i> Check what Amazon allows</button>'
    + '<button class="db-chip" style="background:var(--accent);color:#fff;border-color:var(--accent)" '
    + 'onclick="sellerDraft()">Draft the selected</button>'
    + '</div>';

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
      + (meta
          ? '<div style="font-size:10.5px;color:'+meta.c+'" title="'+_siEsc(
              ((r.screen||{}).notes||[]).join(' | '))+'">'
            + _siEsc(v)+' — '+_siEsc(meta.t)+'</div>'
          : '')
      + '<a href="'+_siEsc(r.url)+'" target="_blank" rel="noopener" '
      + 'onclick="event.stopPropagation()" class="cc" style="font-size:10.5px">on eBay ↗</a>'
      + '</div></label>';
  });
  h += '</div>';
  out.innerHTML = h;
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

async function sellerScreen(btn){
  const sel = SIMP.rows.filter(r => r.selected);
  if(!sel.length){ toast("Nothing selected."); return; }
  if(btn){ btn.disabled = true; btn.innerHTML = '<span class="genspin"></span> checking…'; }
  try{
    const j = await (await fetch("/seller/screen",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_siBody({rows:sel})})).json();
    if(!j.ok){ toast(j.error||"Could not check"); return; }
    // Merge verdicts back by item id -- the reply only covers what was sent.
    const by = {};
    (j.rows||[]).forEach(function(r){ by[r.item_id] = r.screen; });
    SIMP.rows.forEach(function(r){ if(by[r.item_id]) r.screen = by[r.item_id]; });
    SIMP.screened = true;
    const s = j.summary || {}, c = s.counts || {};
    toast("Checked "+(s.total||0)+" — "+(c.blocked||0)+" blocked, "
          +(c.docs||0)+" need documents, "+(c.unknown||0)+" could not be checked");
    sellerImportResults();
  }catch(e){ toast(String(e)); }
  finally{ if(btn){ btn.disabled=false; btn.innerHTML='<i class="ti ti-shield-check"></i> Check what Amazon allows'; } }
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
  if(!confirm(msg)) return;
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
        if(confirm(j.error + "\n\nDraft all " + j.would_draft + "?")){
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
