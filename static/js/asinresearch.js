/* ASIN research: look up any ASIN (read-only Catalog Items), show its data + images, and
   hand off to the existing Image Studio (seeded with the real image) + copy generator (/ask).
   Nothing is ever published. Reuses classic modal styles (rc-*) + genimage.js STUDIO. */
(function(){ "use strict";
  function _esc(s){ return (typeof esc==="function")?esc(s):String(s==null?"":s); }
  function _toast(m){ if(typeof toast==="function") toast(m); }
  var LAST=null;

  window.asinOpen=function(){
    var m=document.getElementById("asin_modal"); if(!m) return;
    m.classList.add("show");
    try{ var mk=document.getElementById("asin_mkt"); var w=(typeof WS_MARKET!=="undefined"&&WS_MARKET)||"";
         if(mk&&(w==="US"||w==="UK")) mk.value=w; }catch(e){}
    var i=document.getElementById("asin_input"); if(i) i.focus();
  };
  window.asinClose=function(){ var m=document.getElementById("asin_modal"); if(m) m.classList.remove("show"); };

  window.asinLookup=function(){
    var asin=((document.getElementById("asin_input")||{}).value||"").trim().toUpperCase();
    var mkt=(document.getElementById("asin_mkt")||{}).value||"UK";
    var res=document.getElementById("asin_res");
    if(!asin){ res.innerHTML='<div class="cc db-warn-amber">Paste an ASIN first.</div>'; return; }
    res.innerHTML='<div class="cc" style="color:var(--muted)">Looking up '+_esc(asin)+' on Amazon '+_esc(mkt)+'…</div>';
    fetch("/catalog/lookup",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({asin:asin,marketplace:mkt})})
      .then(function(r){return r.json();}).then(function(d){
        if(!d||!d.ok){ res.innerHTML='<div class="db-warn-red">'+_esc((d&&d.error)||"Lookup failed")+'</div>'; return; }
        LAST=d; renderResult(d);
      }).catch(function(e){ res.innerHTML='<div class="db-warn-red">Lookup failed: '+_esc(String(e))+'</div>'; });
  };

  function renderResult(d){
    var res=document.getElementById("asin_res");
    var imgs=(d.images||[]);
    var imgHtml = imgs.length
      ? '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0">'+imgs.slice(0,8).map(function(u){
          return '<a href="'+_esc(u)+'" target="_blank" rel="noopener" title="Open full size on Amazon’s CDN"><img src="'+_esc(u)+'" style="width:74px;height:74px;object-fit:cover;border-radius:8px;border:1px solid var(--line);background:#fff"></a>';
        }).join("")+'</div>'
      : '<div class="cc" style="margin:8px 0;color:var(--muted)">No images returned for this ASIN.</div>';
    var specs=Object.keys(d.attributes||{});
    var specHtml = specs.length
      ? '<details style="margin-top:6px"><summary class="cc" style="cursor:pointer">Specs / attributes ('+specs.length+')</summary>'+
        '<div style="max-height:220px;overflow:auto;margin-top:6px;font-size:12px">'+specs.map(function(k){
          return '<div style="display:flex;gap:8px;border-bottom:1px solid var(--line);padding:3px 0"><span class="cc" style="min-width:150px;color:var(--muted)">'+_esc(k)+'</span><span>'+_esc(d.attributes[k])+'</span></div>';
        }).join("")+'</div></details>'
      : '';
    var meta=[d.brand&&("Brand: "+d.brand), d.product_type&&("Type: "+d.product_type),
              "ASIN "+d.asin, d.marketplace, d.account&&("via "+d.account)].filter(Boolean).join("  ·  ");
    res.innerHTML =
      '<div style="font-weight:600">'+_esc(d.title||"(no title returned)")+'</div>'+
      '<div class="cc" style="color:var(--muted);margin-top:2px">'+_esc(meta)+'</div>'+
      imgHtml + specHtml +
      '<div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">'+
        (imgs.length?'<button class="db-chip btn-primary" onclick="asinToStudio()"><i class="ti ti-photo"></i> Open Image Studio</button>':'')+
        '<button class="db-chip" onclick="asinGenerate()"><i class="ti ti-wand"></i> Generate content</button>'+
      '</div>'+
      '<div id="asin_copy" style="margin-top:12px"></div>';
  }

  // Hand off to the existing Image Studio, seeded with the ASIN's real main image as the
  // AI reference (STUDIO.manualRef, which the studio already supports).
  window.asinToStudio=function(){
    if(!LAST){ return; }
    if(typeof STUDIO==="undefined" || typeof renderStudio!=="function"){ _toast("Image Studio isn't available here."); return; }
    var main=(LAST.images&&LAST.images[0])||"";
    try{
      // THE SPECS TRAVEL WITH IT.
      //
      // This handed over the SKU, the title and the pictures and dropped the
      // attributes on the floor -- and the attributes are the FACTS. A+ modules
      // and secondary images are built from them: without them the generator
      // has a layout to fill and nothing true to put in it, which is exactly
      // how a panel headed "28 ingredients" ended up listing invented ones.
      //
      // The research lookup already has them (LAST.attributes) and the studio
      // already reads item.attributes, so this was a gap between two things
      // that both worked.
      STUDIO={ skus:[LAST.asin],
               items:[{sku:LAST.asin, title:LAST.title, source_image:main,
                       images:LAST.images||[],
                       asin:LAST.asin,
                       product_type:LAST.product_type||"",
                       attributes:LAST.attributes||{}}],
               brand:accountBrand(),   // brand.js -- one copy of this rule
               manualRef:main, recipes:[], results:{} };
      _studioShow();   // its own screen now, not a modal over Listings
      asinClose();
      if(typeof loadRecipes==="function"){ loadRecipes().then(function(){ try{ renderStudio(); }catch(e){} }); }
      else { try{ renderStudio(); }catch(e){} }
      if(typeof studioLoadModels==="function") studioLoadModels();
      if(typeof loadStudioInstructions==="function") loadStudioInstructions();
    }catch(e){ _toast("Could not open Image Studio: "+e); }
  };

  // Generate draft copy from the ASIN's data via the existing /ask endpoint. Draft only.
  window.asinGenerate=function(){
    if(!LAST){ return; }
    var box=document.getElementById("asin_copy");
    if(box) box.innerHTML='<div class="cc" style="color:var(--muted)">Generating draft copy…</div>';
    var specs=Object.keys(LAST.attributes||{}).slice(0,25).map(function(k){return k+": "+LAST.attributes[k];}).join("; ");
    var prompt="Write a fresh Amazon "+(LAST.marketplace||"UK")+" listing for this product under a GENERIC own brand — do NOT use any brand or competitor name anywhere. Reference product (ASIN "+LAST.asin+").\n"+
      "Title seen: "+(LAST.title||"")+"\nType: "+(LAST.product_type||"")+"\nSpecs: "+specs+"\n\n"+
      "Produce:\n1) A title up to 200 characters, no brand names.\n2) Five benefit-led bullet points.\n3) A short HTML description.\n"+
      "Keep every claim factual and grounded in the specs above. Avoid medical, pesticide, or unqualified superiority ('best'/'#1') claims.";
    fetch("/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({messages:[{role:"user",text:prompt}]})})
      .then(function(r){return r.json();}).then(function(j){
        if(!j||!j.ok){ box.innerHTML='<div class="db-warn-red">Could not generate: '+_esc((j&&j.error)||"unknown")+'</div>'; return; }
        box.innerHTML='<div class="cc" style="margin-bottom:4px;color:var(--muted)">Draft copy — review + edit before use, nothing is published:</div>'+
          '<textarea class="rc-in" style="min-height:220px;white-space:pre-wrap">'+_esc(j.reply||"(no text)")+'</textarea>';
      }).catch(function(e){ box.innerHTML='<div class="db-warn-red">Could not generate: '+_esc(String(e))+'</div>'; });
  };
})();
