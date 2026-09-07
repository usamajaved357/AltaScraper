/* static/js/gtin.js -- the GTIN exemption, and the only two ways to claim it.
 *
 *     "REMOVE THE GTIN EXEMPTION OPTION ENTIRELY I ALWAYS HAVE A BARCODE SO
 *      DONOT AUTOMATICALLY EXEMPT AUTOMATICALLY, ONLY EXEMPT WHEN USER SELECTS
 *      MULTIPLE DRAFTS AND CLICK ON APPLY FOR GTIN EXEMPTION OR DO IT INSIDE
 *      THE PDP ONE BY ONE."
 *
 * WHAT THE EXEMPTION IS. Ticking it sends Amazon
 * supplier_declared_has_product_identifier_exemption: true -- a DECLARATION that
 * this product has no barcode at all. It is not a way past a barcode Amazon
 * refused, and the app must never make that declaration on the owner's behalf
 * (CLAUDE.md Rule 1). The generator used to claim it automatically whenever the
 * barcode box was empty; that is gone, in the one place it lived and in the
 * dead copy of it that could have brought it back.
 *
 * SO THERE ARE EXACTLY TWO WAYS, AND THEY ARE BOTH A DELIBERATE CLICK:
 *   * one listing at a time, from the tick box on the listing itself
 *     (identifierPanel in listings.js draws it; setGtinExemption below saves it)
 *   * several at once, from the selection toolbar (bulkGtinExemption below)
 *
 * WHY ITS OWN FILE. Both ways write the same column, and a second copy of "how
 * the exemption is set" is exactly the duplication Rule 12 is about -- the bulk
 * path is a loop over the single path, not a reimplementation of it. Rule 7:
 * new logic goes in a new file rather than into listings.js.
 *
 * NOTHING HERE TALKS TO AMAZON. It writes the "GTIN Exemption" column through
 * /edit, the app's one write path for a column. What is sent to Amazon is
 * decided at submit time, in the single authoritative pass in
 * amazon_listing_generator.py.
 */

function _gtinAccount(){
  try{
    return (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT)
      ? String(CUR_ACCOUNT.id || "") : "";
  }catch(e){ return ""; }
}

/* ONE LISTING. The tick box on the listing calls this.
 *
 * Lives here rather than in listings.js so that the single and the bulk route
 * cannot drift apart -- they write the same column, the same value, through the
 * same endpoint.
 */
async function setGtinExemption(sku, on){
  try{
    const j = await _gtinWrite(sku, on);
    if(!j || !j.ok){ toast((j && j.error) || "Could not save that"); return; }
    toast(on ? "GTIN exemption will be claimed for this listing"
             : "GTIN exemption is off for this listing");
    if(typeof refreshRow === "function") refreshRow(sku);
    else if(typeof loadRows === "function") loadRows();
  }catch(e){ toast(String(e)); }
}

/* The write itself, shared by both routes. Returns the parsed reply. */
async function _gtinWrite(sku, on){
  const res = await fetch("/edit", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({sku: sku, target: "col", key: "GTIN Exemption",
                          value: on ? "yes" : "",
                          account: _gtinAccount()})
  });
  return res.json();
}

/* SEVERAL AT ONCE, from the selection toolbar.
 *
 * DRAFTS ONLY. The column lives on a draft row in this app; a listing that
 * exists only in Amazon's catalogue has no row here to tick, and posting one to
 * /edit comes back "row not found" and is counted as a failure. splitByDraft
 * (listings.js) is the same split Approve and Hold already use.
 *
 * IT ASKS FIRST, AND IT SAYS WHAT IS BEING DECLARED. This is the one action in
 * the toolbar that makes a statement to Amazon about the products rather than
 * changing a number, so the confirmation names the count and the meaning.
 */
async function bulkGtinExemption(on){
  const claim = (on !== false);
  const sel = (typeof selectedSkus === "function") ? selectedSkus() : [];
  if(!sel.length){ toast("Select some listings first"); return; }

  const split = (typeof splitByDraft === "function")
    ? splitByDraft(sel) : {drafts: sel, live: []};
  const skus = split.drafts || [];
  if(!skus.length){
    await uiAlert("None of the " + sel.length + " selected listing(s) has a draft "
      + "here, so there is no GTIN Exemption box to tick.\n\nThey are live on "
      + "Amazon and were never generated in this app.");
    return;
  }

  const msg = claim
    ? ("Apply for GTIN exemption on " + skus.length + " listing(s)?\n\n"
       + "This tells Amazon these products HAVE NO BARCODE. It is a declaration "
       + "about the products, not a way past a barcode Amazon refused — and it "
       + "needs GTIN-exemption approval for the brand and category.\n\n"
       + "Nothing is sent to Amazon now. It is claimed on the next submit.")
    : ("Turn the GTIN exemption OFF on " + skus.length + " listing(s)?\n\n"
       + "They will need a real barcode in the Barcode / GTIN box, or Amazon "
       + "will refuse them for want of an identifier.");
  // A DECLARATION TO AMAZON, so the scope of it is worth being sure of. The
  // selection survives a change of tab and of filter; see selectionScopeNote.
  const _scope = (typeof selectionScopeNote === "function")
    ? selectionScopeNote("declaring this") : "";
  if(!await uiConfirm(msg + (_scope ? ("\n\n" + _scope.trim()) : ""))) return;

  const btn = document.getElementById("gtinexemptbtn");
  if(btn){ btn.disabled = true; btn.dataset._t = btn.textContent; btn.textContent = "Saving…"; }

  let ok = 0;
  const failed = [];
  try{
    // Serial, like the other bulk writes here: /edit locates the row and writes
    // a cell, and firing fifty at one store at once is how two of them read the
    // same row and one write is lost.
    for(const sku of skus){
      try{
        const j = await _gtinWrite(sku, claim);
        if(j && j.ok) ok++;
        else failed.push(sku + ": " + ((j && j.error) || "failed"));
      }catch(e){ failed.push(sku + ": " + e); }
    }
    let out = claim
      ? ("GTIN exemption applied to " + ok + " listing(s).")
      : ("GTIN exemption removed from " + ok + " listing(s).");
    if(failed.length){
      out += "\n\nNot saved (" + failed.length + "):\n"
           + failed.slice(0, 8).map(x => "  – " + x).join("\n");
    }
    await uiAlert(out);
    toast(claim ? ("Exemption applied to " + ok) : ("Exemption cleared on " + ok));
    if(typeof loadRows === "function"){ try{ await loadRows(); }catch(_){} }
  } finally {
    if(btn){ btn.disabled = false; btn.textContent = btn.dataset._t || "Apply for GTIN exemption"; }
  }
}
