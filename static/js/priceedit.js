// ===================== CHANGE A LIVE SELLING PRICE =====================
// Two steps, always: ask what would happen, then do exactly that.
//
// The preview sends nothing to Amazon. It reads the listing live -- never a
// cached copy, because the patch is built by editing the offer Amazon returned
// rather than by inventing one -- and reports the current price, the floor
// beneath which the product stops making money, and anything that looks like a
// typo. Only then is there something to confirm.
//
// The floor is not a veto. Clearance is real, and an app that refuses outright
// gets worked around. What it will not let you do is walk into it unaware: the
// warning is explicit about how much each unit loses, and the server refuses a
// below-floor price again unless the confirmation says so, because a dialog
// somebody clicked through is not a control.

function _peEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function _peMoney(v){
  return (v===null||v===undefined||v==="") ? "—" : Number(v).toFixed(2);
}

async function priceEdit(sku, current){
  if(!sku){ toast("No SKU for that row."); return; }
  const asked = prompt(
    "New selling price for\n" + sku
    + (current ? "\n\nIt currently sells for " + Number(current).toFixed(2) : "")
    + "\n\nNothing is sent yet — you will see what would change first.",
    current ? Number(current).toFixed(2) : "");
  if(asked === null) return;
  const price = Number(String(asked).replace(/[^0-9.]/g, ""));
  if(!price || price <= 0){ toast("That is not a price."); return; }

  toast("Checking…");
  let j;
  try{
    j = await (await fetch("/listing/price/preview",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, price:price})})).json();
  }catch(e){ toast(String(e)); return; }
  if(!j || !j.ok){ toast((j&&j.error)||"Could not check that price"); return; }

  let msg = "Change the price of\n" + sku + "\n\n"
          + "  now:  " + _peMoney(j.current) + "\n"
          + "  new:  " + _peMoney(j.new) + "\n";
  if(j.floor !== null && j.floor !== undefined){
    msg += "  floor: " + _peMoney(j.floor)
         + "  (below this it stops making money)\n";
  }
  if((j.warnings||[]).length){
    msg += "\n" + j.warnings.map(w => "! " + w).join("\n\n") + "\n";
  }
  msg += "\nThis changes what buyers pay on Amazon. Send it?";
  if(!confirm(msg)) return;

  const belowFloor = (j.floor !== null && j.floor !== undefined && j.new < j.floor);
  if(belowFloor){
    // Asked a second time, on its own, with the number. The first dialog carried
    // several facts; this one carries the one that costs money.
    if(!confirm("Confirm selling BELOW cost.\n\n"
                + _peMoney(j.new) + " is under the " + _peMoney(j.floor)
                + " floor — about " + _peMoney(j.floor - j.new)
                + " lost on every unit sold.\n\nGo ahead?")) return;
  }

  try{
    const r = await (await fetch("/listing/price/apply",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, price:price, confirmed:true,
                           below_floor_ok:belowFloor})})).json();
    if(!r || !r.ok){ toast((r&&r.error)||"Amazon refused it"); return; }
    toast("Price sent for " + sku + " — " + _peMoney(r.was) + " → "
          + _peMoney(r.now) + ". " + (r.note||""));
    if(typeof loadRows === "function") loadRows();
  }catch(e){ toast(String(e)); }
}
