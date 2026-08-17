// ===================== CHANGE A LIVE SELLING PRICE =====================
//
// ONE PANEL, NOT THREE BROWSER DIALOGS.
//
//     "whenever i try to change the price of a sku through the app it gives me
//      3 warnings and i dont like this white appearing messages over the window.
//      modern apps do not behave like this."
//
// It used to be prompt() -> confirm() -> confirm(): a native box asking for the
// number, a second reciting the preview, and a third asking again about the
// floor. Three white system dialogs stacked over a dark app, each one throwing
// away what the last had shown. Screenshots 85, 86 and 87.
//
// Now: one panel in the app's own skin. Type the price, and what it would do
// appears underneath as you type -- the current price, the floor, what the sale
// would actually leave. Nothing is sent until the button is pressed, and the
// button says what it will do.
//
// THE FLOOR IS STILL NOT A VETO. Clearance is real, and an app that refuses
// outright gets worked around. What it will not let you do is walk into it
// unaware: below the floor the button turns red and a tickbox has to be ticked,
// which is a deliberate act rather than a third dialog to click through. The
// server checks it again on apply, because a control the browser enforces is not
// a control.

function _peEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function _peMoney(v){
  return (v===null||v===undefined||v==="") ? "—" : Number(v).toFixed(2);
}
function _peSym(){
  try{ return (typeof CUR_SYMBOL !== "undefined" && CUR_SYMBOL) || ""; }
  catch(e){ return ""; }
}

/* WHICH ACCOUNT AND MARKETPLACE THIS PRICE BELONGS TO, said on every request.
 *
 * These two calls used to send only {sku, price}, so the server fell back to
 * its process-wide "which account is open" variable -- the same variable that
 * was showing one company's sales under another's name. Two consequences, and
 * the second is worse than the first:
 *
 *   with the global unset, the request failed outright with "Credentials are
 *   missing: lwa_app_id, lwa_client_secret", surfacing as "Amazon would not
 *   return that SKU" -- which is why the price could not be changed at all;
 *
 *   with the global pointing somewhere else, a price could have been sent to
 *   the WRONG SELLER ACCOUNT, which is a real listing on a real shopfront.
 *
 * The page knows which listing it is showing. It says so. */
function _peScope(body){
  const b = body || {};
  try{
    if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id){
      b.id = CUR_ACCOUNT.id;
      b.account_id = CUR_ACCOUNT.id;
    }
  }catch(e){}
  try{
    if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__"){
      b.marketplace = WS_MARKET;
    }
  }catch(e){}
  return b;
}

let _PE = null;      // {sku, current, title, preview, busy}

function _peHost(){
  let el = document.getElementById("pricemodal");
  if(!el){
    el = document.createElement("div");
    el.id = "pricemodal";
    el.className = "modalwrap";
    document.body.appendChild(el);
    // Clicking the dark surround closes it, as every other panel in the app
    // does. Only the surround -- a click inside must not close the thing you
    // are typing into.
    el.addEventListener("click", function(ev){
      if(ev.target === el) priceEditClose();
    });
  }
  return el;
}

function priceEditClose(){
  const el = document.getElementById("pricemodal");
  if(el) el.classList.remove("open");
  _PE = null;
  document.removeEventListener("keydown", _peKey);
}

function _peKey(ev){
  if(ev.key === "Escape"){ ev.preventDefault(); priceEditClose(); }
}

async function priceEdit(sku, current, title){
  if(!sku){ toast("No SKU for that row."); return; }
  _PE = {sku: sku, current: (current === undefined ? null : current),
         title: title || "", preview: null, busy: false};
  _peDraw();
  _peHost().classList.add("open");
  document.addEventListener("keydown", _peKey);
  const inp = document.getElementById("pe_price");
  if(inp){ inp.focus(); inp.select(); }
}

// WHAT THE PANEL SHOWS. Redrawn whenever the preview lands, never rebuilt while
// somebody is mid-keystroke -- the input is left alone and only the result area
// under it is replaced, or the caret jumps to the end on every character.
function _peDraw(){
  const el = _peHost();
  if(!_PE) return;
  const sym = _peSym();
  el.innerHTML =
      '<div class="modal" style="max-width:520px">'
    + '<button class="x" onclick="priceEditClose()">&times;</button>'
    + '<h3>Change the selling price</h3>'
    + '<div class="cc" style="margin-bottom:14px">'
    +   (_PE.title ? '<div style="color:var(--ink);font-size:13px;margin-bottom:3px">'
                     + _peEsc(_PE.title) + '</div>' : '')
    +   '<span style="font-family:ui-monospace,Consolas,monospace;font-size:11px">'
    +   _peEsc(_PE.sku) + '</span></div>'

    + '<div style="display:flex;gap:14px;align-items:flex-end;margin-bottom:4px">'
    +   '<div><div class="cc" style="font-size:11px;margin-bottom:4px">Sells for now</div>'
    +   '<div style="font-size:19px;font-variant-numeric:tabular-nums">'
    +   _peEsc(sym) + _peMoney(_PE.current) + '</div></div>'
    +   '<div style="color:var(--ink3);font-size:19px;padding-bottom:2px">&rarr;</div>'
    +   '<div style="flex:1"><label class="cc" for="pe_price" '
    +     'style="font-size:11px;display:block;margin-bottom:4px">New price</label>'
    +   '<input id="pe_price" type="text" inputmode="decimal" autocomplete="off" '
    +     'value="' + (_PE.current !== null ? Number(_PE.current).toFixed(2) : "") + '" '
    +     'style="width:100%;padding:8px 10px;font-size:17px;text-align:right;'
    +     'font-variant-numeric:tabular-nums;border:1px solid var(--accent);'
    +     'border-radius:8px;background:var(--bg);color:var(--ink)"></div>'
    + '</div>'

    + '<div id="pe_result" style="min-height:74px;margin:12px 0 0"></div>'

    + '<div style="display:flex;gap:8px;align-items:center;margin-top:16px">'
    +   '<span class="cc" style="flex:1;font-size:11px">Nothing is sent until you '
    +   'press the button.</span>'
    +   '<button class="db-chip" onclick="priceEditClose()">Cancel</button>'
    +   '<button class="db-chip" id="pe_send" onclick="priceEditSend()" '
    +     'style="border-color:var(--accent);color:var(--accent)" disabled>Send to Amazon</button>'
    + '</div>'
    + '</div>';

  const inp = document.getElementById("pe_price");
  if(inp){
    let t = null;
    inp.addEventListener("input", function(){
      // Debounced: the preview reads the listing live from Amazon, so one call
      // per keystroke would be a call per keystroke to a rate-limited API.
      clearTimeout(t);
      t = setTimeout(_pePreview, 450);
      _peResult('<span class="cc">…</span>', true);
    });
    inp.addEventListener("keydown", function(ev){
      if(ev.key === "Enter"){
        ev.preventDefault();
        if(_PE && _PE.preview) priceEditSend(); else _pePreview();
      }
    });
  }
  _pePreview();
}

function _peResult(html, disable){
  const r = document.getElementById("pe_result");
  if(r) r.innerHTML = html;
  const b = document.getElementById("pe_send");
  if(b) b.disabled = !!disable;
}

function _peTyped(){
  const inp = document.getElementById("pe_price");
  const v = Number(String((inp && inp.value) || "").replace(/[^0-9.]/g, ""));
  return (v && v > 0) ? v : null;
}

async function _pePreview(){
  if(!_PE) return;
  const price = _peTyped();
  if(price === null){
    _PE.preview = null;
    _peResult('<span class="cc">Type a price above.</span>', true);
    return;
  }
  let j;
  try{
    j = await (await fetch("/listing/price/preview",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(_peScope({sku:_PE.sku, price:price}))})).json();
  }catch(e){
    _PE.preview = null;
    _peResult('<span style="color:var(--red)">' + _peEsc(String(e)) + '</span>', true);
    return;
  }
  if(!_PE) return;                       // closed while we were waiting
  if(!j || !j.ok){
    _PE.preview = null;
    _peResult('<span style="color:var(--red)">'
              + _peEsc((j && j.error) || "Could not check that price")
              + '</span>', true);
    return;
  }
  _PE.preview = j;
  _peResult(_peResultHtml(j), false);
}

function _peResultHtml(j){
  const sym = _peSym();
  const below = (j.floor !== null && j.floor !== undefined && j.new < j.floor);
  let h = "";

  // THE FLOOR, AS A FACT RATHER THAN AS AN ALARM. It is shown whether or not it
  // is breached, so the number is familiar by the time it matters -- and it is
  // named, because "which floor is it talking about" was a fair question when
  // it appeared only inside a warning.
  if(j.floor !== null && j.floor !== undefined){
    h += '<div style="display:flex;gap:6px;align-items:baseline;font-size:12px;'
       + 'margin-bottom:8px">'
       + '<span class="cc">Your floor for this product</span>'
       + '<b style="font-variant-numeric:tabular-nums;color:'
       + (below ? "var(--red)" : "var(--ok)") + '">' + _peEsc(sym)
       + _peMoney(j.floor) + '</b>'
       + '<span class="cc" style="font-size:11px">— the least it can sell for and '
       + 'still meet your profit rule, once the stock and Amazon\'s fees are paid</span>'
       + '</div>';
  }

  (j.warnings || []).forEach(function(w){
    h += '<div style="display:flex;gap:7px;background:var(--warn-bg,rgba(227,183,104,.12));'
       + 'border:1px solid var(--warn-line,rgba(227,183,104,.35));border-radius:8px;'
       + 'padding:8px 10px;margin-bottom:6px;font-size:12px;line-height:1.5">'
       + '<i class="ti ti-alert-triangle" style="color:var(--warn)"></i>'
       + '<span>' + _peEsc(w) + '</span></div>';
  });
  (j.notes || []).forEach(function(n){
    h += '<div class="cc" style="font-size:11.5px;line-height:1.5;margin-bottom:4px">'
       + '<i class="ti ti-info-circle"></i> ' + _peEsc(n) + '</div>';
  });

  // BELOW THE FLOOR NEEDS A DELIBERATE ACT, not a third dialog. A tickbox that
  // has to be ticked is harder to click through than a confirm() and leaves the
  // reason on screen while you decide.
  if(below){
    h += '<label style="display:flex;gap:8px;align-items:flex-start;margin-top:8px;'
       + 'font-size:12px;cursor:pointer;color:var(--red)">'
       + '<input type="checkbox" id="pe_below" onchange="_peArm()" '
       + 'style="margin-top:2px;accent-color:var(--red)">'
       + '<span>Yes — sell below the floor. Every unit gives up about '
       + _peEsc(sym) + _peMoney(j.floor - j.new) + ' against your profit rule.</span>'
       + '</label>';
  }
  setTimeout(_peArm, 0);
  return h;
}

// The button reflects what pressing it would do. Red and explicit below the
// floor, and refused until the tickbox agrees.
function _peArm(){
  const b = document.getElementById("pe_send");
  const j = _PE && _PE.preview;
  if(!b || !j) return;
  const below = (j.floor !== null && j.floor !== undefined && j.new < j.floor);
  const box = document.getElementById("pe_below");
  if(below){
    b.style.borderColor = "var(--red)";
    b.style.color = "var(--red)";
    b.textContent = "Send anyway — below the floor";
    b.disabled = !(box && box.checked);
  }else{
    b.style.borderColor = "var(--accent)";
    b.style.color = "var(--accent)";
    b.textContent = "Send to Amazon";
    b.disabled = false;
  }
}

async function priceEditSend(){
  if(!_PE || !_PE.preview || _PE.busy) return;
  const j = _PE.preview;
  const below = (j.floor !== null && j.floor !== undefined && j.new < j.floor);
  const box = document.getElementById("pe_below");
  if(below && !(box && box.checked)) return;

  _PE.busy = true;
  const b = document.getElementById("pe_send");
  if(b){ b.disabled = true; b.textContent = "Sending…"; }
  const sku = _PE.sku, price = j.new;
  try{
    const r = await (await fetch("/listing/price/apply",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(_peScope({sku:sku, price:price, confirmed:true,
                                    below_floor_ok:below}))})).json();
    if(!r || !r.ok){
      toast((r&&r.error)||"Amazon refused it");
      if(_PE){ _PE.busy = false; _peArm(); }
      return;
    }
    priceEditClose();
    toast("Price sent for " + sku + " — " + _peMoney(r.was) + " → "
          + _peMoney(r.now) + ". " + (r.note||""));
    if(typeof loadRows === "function") loadRows();
  }catch(e){
    toast(String(e));
    if(_PE){ _PE.busy = false; _peArm(); }
  }
}
