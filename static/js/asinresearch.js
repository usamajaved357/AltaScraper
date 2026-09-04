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
    // PREFILLED, NOT LOCKED. The account's own brand is the usual answer, so it
    // is put in the box -- but the box is free text and a datalist of this
    // account's other brands sits behind it, because writing copy for a brand
    // you do not own yet is exactly what this tool is for.
    try{
      var bi=document.getElementById("asin_brand");
      if(bi && !bi.value && typeof accountBrand==="function") bi.value=accountBrand()||"";
      var dl=document.getElementById("asin_brandlist");
      if(dl && typeof accountBrands==="function"){
        dl.innerHTML=(accountBrands()||[]).map(function(b){
          return '<option value="'+_esc(b)+'">'; }).join("");
      }
    }catch(e){}
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
          return '<a href="'+_esc(u)+'" target="_blank" rel="noopener" title="Open full size on Amazon’s CDN"><img src="'+_esc(u)+'" style="width:74px;height:74px;object-fit:cover;border-radius:8px;border:1px solid var(--line);background:var(--paper)"></a>';
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
    // THE BRAND IS A PROPERTY OF THE PRODUCT, NOT OF ONE IMAGE KIND.
    //
    // Reported: the brand could only be given while making a MAIN image, and
    // not for secondary or A+ images -- yet it is the same brand on the same
    // ASIN in every one of them. It is asked for once, here, at the point the
    // ASIN is researched, and travels into the studio for every kind.
    //
    // accountBrand() stays as the fallback for the case where this modal was
    // never used, but a brand TYPED for this ASIN beats the account default:
    // researching someone else's ASIN to build your own listing is the whole
    // purpose of the tool, and the account's brand is often not the answer.
    var brand=_brandInput() || (typeof accountBrand==="function" ? accountBrand() : "");
    if(!brand){
      var bi=document.getElementById("asin_brand");
      if(bi) bi.focus();
      _toast("Enter the brand first — the images are built to carry it.");
      return;
    }
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
               brand:brand,            // typed for THIS ASIN, or the account's
               manualRef:main, recipes:[], results:{} };
      _studioShow();   // its own screen now, not a modal over Listings
      asinClose();
      if(typeof loadRecipes==="function"){ loadRecipes().then(function(){ try{ renderStudio(); }catch(e){} }); }
      else { try{ renderStudio(); }catch(e){} }
      if(typeof studioLoadModels==="function") studioLoadModels();
      if(typeof loadStudioInstructions==="function") loadStudioInstructions();
    }catch(e){ _toast("Could not open Image Studio: "+e); }
  };

  /* ---- write the copy, then make it a product card ------------------------
   *
   * REPORTED: "i tried writing the listing copy for an asin using the research
   * an asin tool but it wrote a listing copy but did not created a product card
   * in the workspace, i want it to writ the listing copy in the product card.
   * and when writing content there should be an option to put the brand name."
   *
   * Both were true. This used to post a hand-rolled prompt to /ask -- the
   * generic chat endpoint -- and drop the reply into a textarea. Nothing was
   * saved anywhere; reloading the page lost it. And the prompt asked for copy
   * under "a GENERIC own brand ... do NOT use any brand name anywhere", so
   * there was no brand to put in and no way to supply one.
   *
   * THIS NOW USES THE PIPELINE THAT ALREADY EXISTS. ASIN Studio has done
   * exactly this job all along: /asin-studio/generate writes branded, scrubbed,
   * STRUCTURED copy (title, bullets, description, search terms) and
   * /asin-studio/create-draft turns it into an ordinary draft row with a SKU,
   * so the compliance hold, the IP hold, Auto-fix, Preview and Submit all work
   * on it with no special case.
   *
   * Reusing it rather than writing a second copy-generator and a second row
   * writer is the whole point (CLAUDE.md rule 12): a second one would need its
   * own brand scrub, its own SKU format and its own guards, and they would
   * drift from these.
   */
  function _brandInput(){
    return ((document.getElementById("asin_brand")||{}).value||"").trim();
  }

  window.asinGenerate=function(){
    if(!LAST){ return; }
    var box=document.getElementById("asin_copy");
    var brand=_brandInput();
    // ASKED FOR, NOT INFERRED. accountBrand() is a reasonable default and it is
    // prefilled into the box -- but a workspace with no brand set, which is the
    // case a reviewer will be in, would silently get "" and the server would
    // refuse. Better to say which field is empty.
    if(!brand){
      box.innerHTML='<div class="db-warn-amber">Enter the brand this listing '
        +'goes out under, above. The copy is written to carry it — that is what '
        +'makes it your listing rather than a generic rewrite of someone '
        +'else’s.</div>';
      var bi=document.getElementById("asin_brand"); if(bi) bi.focus();
      return;
    }
    if(box) box.innerHTML='<div class="cc" style="color:var(--muted)">Writing '
      +_esc(brand)+' copy from ASIN '+_esc(LAST.asin)+'…</div>';
    fetch("/asin-studio/generate",{method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          id:(typeof CUR_ACCOUNT!=="undefined"&&CUR_ACCOUNT)?CUR_ACCOUNT.id:"",
          marketplace:LAST.marketplace||"",
          brand:brand,
          source:{title:LAST.title, attributes:LAST.attributes||{},
                  bullets:LAST.bullets||[]},
          competitors:[]})})
      .then(function(r){return r.json();}).then(function(j){
        if(!j||!j.ok){ box.innerHTML='<div class="db-warn-red">Could not generate: '+_esc((j&&j.error)||"unknown")+'</div>'; return; }
        COPY=j.copy||j;
        renderCopy(COPY, brand, j.ip_notes||[], j.brand_note||"");
      }).catch(function(e){ box.innerHTML='<div class="db-warn-red">Could not generate: '+_esc(String(e))+'</div>'; });
  };

  var COPY=null;

  function renderCopy(c, brand, ipNotes, brandNote){
    var box=document.getElementById("asin_copy");
    if(!box) return;
    var bullets=(c.bullets||[]).slice(0,5);
    box.innerHTML=
      '<div class="cc" style="margin-bottom:6px;color:var(--muted)">'
      +'Draft copy for <b>'+_esc(brand)+'</b> — review and edit before it goes '
      +'anywhere. Nothing has been sent to Amazon.</div>'
      // WHAT THE SCRUB TOOK OUT, said rather than done silently. The generator
      // removes competitor brands and comparison phrasing; seeing that it fired
      // is how you learn the source listing was leaning on someone else's name.
      +((ipNotes&&ipNotes.length)
          ? '<div class="db-warn-amber" style="margin-bottom:8px;font-size:11.5px">'
            +'<b>Removed before you saw it:</b> '
            +ipNotes.map(function(n){return _esc(n);}).join(" · ")+'</div>' : '')
      +(brandNote ? '<div class="cc" style="font-size:11px;margin-bottom:8px">'
                    +_esc(brandNote)+'</div>' : '')
      +'<label class="cc" style="font-size:11px">Title</label>'
      +'<input class="rc-in" id="asin_c_title" value="'+_esc(c.title||"")+'">'
      +'<label class="cc" style="font-size:11px;margin-top:6px;display:block">Bullets</label>'
      +bullets.map(function(b,i){
         return '<input class="rc-in" id="asin_c_b'+i+'" style="margin-top:3px" value="'+_esc(b)+'">';
       }).join("")
      +'<label class="cc" style="font-size:11px;margin-top:6px;display:block">Description</label>'
      +'<textarea class="rc-in" id="asin_c_desc" style="min-height:110px">'+_esc(c.description||"")+'</textarea>'
      +'<div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;align-items:center">'
      +'<span class="cc" style="font-size:11px">Price</span>'
      +'<input class="rc-in" id="asin_c_price" style="width:90px" placeholder="0.00" value="">'
      +'<span class="cc" style="font-size:11px">Handling days</span>'
      +'<input class="rc-in" id="asin_c_days" style="width:64px" value="3">'
      +'<button class="db-chip btn-primary" onclick="asinCreateCard()">'
      +'<i class="ti ti-cards"></i> Create product card</button>'
      +'</div>'
      +'<div class="cc" style="font-size:10.5px;margin-top:6px">The card lands '
      +'in Listings as a draft with the compliance and IP checks still to run. '
      +'The ASIN is kept only as the source of the product facts.</div>'
      +'<div id="asin_made" style="margin-top:8px"></div>';
  }

  /* Turn the reviewed copy into an ordinary draft row, through the same route
     ASIN Studio uses. Same SKU format, same guards, same everything. */
  window.asinCreateCard=function(){
    if(!LAST||!COPY){ return; }
    var out=document.getElementById("asin_made");
    var brand=_brandInput();
    var bullets=[];
    for(var i=0;i<5;i++){
      var el=document.getElementById("asin_c_b"+i);
      if(el && el.value.trim()) bullets.push(el.value.trim());
    }
    var copy={
      title:((document.getElementById("asin_c_title")||{}).value||"").trim(),
      bullets:bullets,
      description:((document.getElementById("asin_c_desc")||{}).value||"").trim(),
      search_terms:COPY.search_terms||""
    };
    if(out) out.innerHTML='<div class="cc" style="color:var(--muted)">Creating the card…</div>';
    fetch("/asin-studio/create-draft",{method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          id:(typeof CUR_ACCOUNT!=="undefined"&&CUR_ACCOUNT)?CUR_ACCOUNT.id:"",
          marketplace:LAST.marketplace||"",
          copy:copy, brand:brand, source_asin:LAST.asin,
          price:((document.getElementById("asin_c_price")||{}).value||"").trim(),
          handling_days:((document.getElementById("asin_c_days")||{}).value||"3").trim(),
          attributes:LAST.attributes||{}})})
      .then(function(r){return r.json();}).then(function(j){
        if(!j||!j.ok){
          out.innerHTML='<div class="db-warn-red">'+_esc((j&&j.error)||"Could not create the card")+'</div>';
          return;
        }
        out.innerHTML='<div class="db-warn-green">Created <b>'+_esc(j.sku)+'</b>. '
          +_esc(j.message||"")+'</div>';
        _toast("Product card created: "+j.sku);
        // Show it. A card you are told about but cannot see is a card you have
        // to go hunting for.
        try{ if(typeof loadRows==="function") loadRows(); }catch(e){}
      }).catch(function(e){ out.innerHTML='<div class="db-warn-red">Could not create the card: '+_esc(String(e))+'</div>'; });
  };
})();
