// ============== ADD A COLOUR OR SIZE TO SOMETHING ALREADY LISTED ==============
// "The ceiling fan is live in white. I want the black one, which is only on
// eBay, showing as a colour choice on the same product."
//
// WHY THIS SAYS THREE STEPS RATHER THAN DOING IT IN ONE
// Amazon has no "add a variant to this ASIN" operation. A variation family is a
// PARENT listing -- a real listing with its own code that nobody can buy -- with
// BOTH products underneath it as children. So the white fan does not gain a
// variant: the white fan and the black fan both become children of a new parent,
// and that can only be built over listings that already exist on Amazon.
//
// So this queues the new product, and the family is joined afterwards on the
// Variations screen. Doing it in one click would mean building a parent over a
// child that does not exist yet -- which Amazon accepts without complaint, after
// which the products quietly stop appearing.

function _avEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

async function addVariant(sku){
  if(!sku){ toast("No SKU for that row."); return; }
  const url = await uiPrompt(
    "Add a colour or size to\n" + sku
    + "\n\nPaste the eBay link for the NEW one — where you would buy it.\n"
    + "Nothing is queued or sent yet.", "");
  if(url === null) return;
  if(!url.trim()){ toast("No link given."); return; }

  const what = await uiPrompt(
    "What is different about this one?\n\n"
    + "For example:  colour: Black\n"
    + "          or  size: XL",
    "colour: ");
  if(what === null) return;

  // "colour: Black" -> {colour: "Black"}. Free text on purpose: the exact
  // attribute Amazon wants is a per-product-type enum and is checked against
  // the live schema when the family is joined, not guessed here.
  const differs = {};
  String(what || "").split(/[,;\n]/).forEach(function(part){
    const bits = part.split(":");
    if(bits.length >= 2 && bits[0].trim() && bits.slice(1).join(":").trim()){
      differs[bits[0].trim().toLowerCase()] = bits.slice(1).join(":").trim();
    }
  });

  toast("Reading the eBay listing…");
  let j;
  try{
    j = await (await fetch("/variant/plan",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, ebay_url:url.trim(), differs:differs})})).json();
  }catch(e){ toast(String(e)); return; }
  if(!j || !j.ok){ toast((j&&j.error)||"Could not work that out"); return; }

  const p = j.plan || {};
  const s = p.source || {};
  let msg = "Add a variant of\n" + sku + "\n\n"
          + "New product: " + (s.title || "(no title from eBay)") + "\n"
          + (s.cost != null ? "Costs you:   " + Number(s.cost).toFixed(2)
                              + "  (" + Number(s.price).toFixed(2) + " + "
                              + Number(s.shipping).toFixed(2) + " postage)\n"
                            : "Costs you:   unknown\n");
  const d = p.differs || {};
  const keys = Object.keys(d);
  msg += "Different by: " + (keys.length
          ? keys.map(k => k + " " + d[k]).join(", ") : "(not said)") + "\n";
  const sh = p.shared || {};
  msg += "\nIt will inherit from " + sku + ":\n"
       + "  type:  " + (sh.product_type || "(unknown)") + "\n"
       + "  brand: " + (sh.brand || "(unknown)") + "\n";

  if((p.warnings||[]).length){
    msg += "\n" + p.warnings.map(w => "! " + w).join("\n\n") + "\n";
  }
  msg += "\nWhat happens next:\n"
       + (p.steps||[]).map((t,i) => "  " + (i+1) + ". " + t).join("\n")
       + "\n\nQueue it?";
  if(!await uiConfirm(msg)) return;

  try{
    const r = await (await fetch("/variant/queue",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, ebay_url:url.trim(), differs:differs,
                           confirmed:true})})).json();
    if(!r || !r.ok){ toast((r&&r.error)||"Could not queue it"); return; }
    toast("Queued: " + (r.queued_as||"") + " — " + (r.note||""));
    if(typeof inputQueueLoad === "function") inputQueueLoad();
  }catch(e){ toast(String(e)); }
}
