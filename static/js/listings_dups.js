// static/js/listings_dups.js -- duplicate SKUs. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

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
// Delete ONE duplicate copy from this app (leaving the other copies untouched).
//
// app_only IS THE WHOLE FIX. Without it /delete asks Amazon about the SKU and
// deletes the LIVE LISTING if Amazon has it -- while this dialog promised that
// only a copy was going. The server removes only the copy spelled exactly like
// this one, and refuses if it is the last copy (see _delete_one_copy in
// routes/listing_routes.py).
async function delDuplicate(sku, row, tab, btn){
  // The account this was opened for, noted BEFORE the dialog below: if it
  // changed meanwhile (back/forward), nothing is sent (confirm-then-write audit).
  const _pinAcct = (typeof acctId === "function") ? acctId() : "";
  const _others=dupCopies({sku:sku}).map(c=>String(c.sku)).filter(s=>s!==String(sku));
  if(!await uiConfirm("Delete this DUPLICATE copy of "+sku+" from this app?\n\n"
             +"Only this copy is removed"
             +(_others.length?" — "+_others.join(", ")+" stays":" — the other copy stays")
             +". Nothing is sent to Amazon, and the listing on Amazon is not touched."
             +"\n\nThis cannot be undone.")) return;
  if(btn) btn.disabled=true;
  try{
    if(typeof ensureCardTab==="function"){ await ensureCardTab(sku); }
    if(typeof acctId === "function" && acctId() !== _pinAcct){
        if(typeof toast === "function") toast("The account changed while this was open, so nothing was done."); if(btn) btn.disabled=false;
        return;
      }
    const res=await fetch("/delete",{method:"POST",headers:{"Content-Type":"application/json"},
                body:JSON.stringify(acctBody({sku:sku, row:row, app_only:true}))});
    const j=await res.json();
    if(j.ok){ toast("Duplicate copy removed from this app. Amazon was not touched."); loadRows(); }
    else{ toast("Delete failed: "+(j.error||"")); if(btn) btn.disabled=false; }
  }catch(e){ toast("Delete failed"); if(btn) btn.disabled=false; }
}
