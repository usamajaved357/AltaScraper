/* static/js/ordercosts.js -- set the cost of many orders from one sheet.
 *
 *     "i will upload a sheet containing amazon order numbers and the source
 *      price on which this order was fulfilled ... give me a bulk upload
 *      button in the app, from where i can download the template and then fill
 *      back to update the cogs per order in the orders page"
 *
 * DOWNLOAD FIRST, ALWAYS. The template arrives with the order, the date, the
 * product and the cost the app CURRENTLY believes already filled in, and one
 * empty column to complete. That makes filling it in a matter of correcting
 * what is wrong rather than retyping what is already right -- and it is what
 * makes an unedited upload harmless, because a row with the cost left blank is
 * skipped rather than zeroed.
 *
 * A COST SET THIS WAY IS YOURS AND STAYS YOURS. The server writes it as
 * 'manual-order', which is the top of the trust order in domain/order_cogs.py:
 * a re-sync, a supplier price change or switching costing mode cannot overwrite
 * it. That is the whole reason this is per ORDER and not per product -- the same
 * item bought at 7.00 in July and 9.50 in August has two true costs, and a
 * per-product cost can only hold one of them.
 */

function _ocQS(){
  const q = [];
  const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
            ? CUR_ACCOUNT.id : "";
  const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
  // account_id AND id: the app reads both spellings depending on the screen,
  // and sending both costs nothing and removes a whole class of "it answered
  // for the wrong account" bug. Measured once already: a template downloaded
  // for one account arrived full of another's orders.
  if(a){ q.push("account_id=" + encodeURIComponent(a));
         q.push("id=" + encodeURIComponent(a)); }
  if(m && m !== "__all__") q.push("marketplace=" + encodeURIComponent(m));
  return q.join("&");
}

function _ocNote(html, tone){
  const el = document.getElementById("ordcost_result");
  if(!el){ if(typeof toast === "function") toast(String(html).replace(/<[^>]+>/g, "")); return; }
  if(!html){ el.innerHTML = ""; return; }
  const border = tone === "bad" ? "var(--red-line)"
               : tone === "warn" ? "var(--warn-line)" : "var(--line2)";
  el.innerHTML = '<div style="padding:9px 11px;border:1px solid ' + border
    + ';border-radius:6px;font-size:12px;line-height:1.55">' + html + '</div>';
}

/* The account and marketplace have to be settled before either button works: a
 * cost is written against one order OF ONE ACCOUNT, and a sheet downloaded
 * without them would be full of somebody else's orders. */
function _ocReady(){
  const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
            ? CUR_ACCOUNT.id : "";
  const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
  if(!a){ _ocNote("Open an account first — a cost is written against one "
                  + "order of one account.", "warn"); return false; }
  if(!m || m === "__all__"){
    _ocNote("Pick a single marketplace first. Orders and their costs belong to "
            + "one marketplace, and \"all marketplaces\" cannot say which.", "warn");
    return false;
  }
  return true;
}

function orderCostsTemplate(uncostedOnly){
  if(!_ocReady()) return;
  const qs = _ocQS() + (uncostedOnly ? "&uncosted=1" : "");
  // A plain navigation, not fetch(): this is a file download and the browser
  // already knows how to save one. Going through fetch would mean holding the
  // whole sheet in memory to hand it straight back to the browser.
  window.location = "/cogs/orders/template.csv?" + qs;
  _ocNote(uncostedOnly
    ? "Downloading the orders that have no cost yet. Fill in the <b>cost</b> "
      + "column — the price you actually paid for that order — and upload it back."
    : "Downloading every order in this window. The <b>cost now</b> column shows "
      + "what the app currently believes; fill in <b>cost</b> only where that is "
      + "wrong or missing. Rows left blank are skipped.");
}

function orderCostsUploadOpen(){
  if(!_ocReady()) return;
  const el = document.getElementById("ordcost_file");
  if(el){ el.value = ""; el.click(); }
}

async function orderCostsUpload(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  _ocNote('<span class="genspin"></span> Reading ' + String(f.name) + '…');
  try{
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch("/cogs/orders/upload?" + _ocQS(),
                          {method: "POST", body: fd});
    const j = await r.json();
    if(!j || !j.ok){
      _ocNote("<b>Nothing was changed.</b> "
              + (j && j.error ? String(j.error) : "That file could not be read."),
              "bad");
      return;
    }

    // EVERY OUTCOME, NOT JUST THE GOOD ONE. A bulk action that reports only
    // what worked hides exactly the rows worth looking at -- and "47 costs
    // set" beside 30 silently dropped rows is the version of this that gets
    // trusted and should not be.
    let h = "<b>" + (j.note || "Done.") + "</b>";
    const problems = (j.rows || []).filter(function(x){ return x.result !== "set"; });
    if(problems.length){
      h += '<div style="margin-top:6px">These rows were not applied:</div>'
        + '<ul style="margin:4px 0 0 16px">';
      problems.slice(0, 12).forEach(function(x){
        h += "<li>" + String(x.order_id || "(no order number)")
          + " — " + String(x.result) + "</li>";
      });
      h += "</ul>";
      if(problems.length > 12)
        h += '<div class="cc">…and ' + (problems.length - 12) + " more.</div>";
    }
    if(j.set){
      h += '<div class="cc" style="margin-top:6px">These costs are marked as '
        + 'yours. Nothing later overwrites them — not a re-sync, not a supplier '
        + 'price change, not switching costing mode.</div>';
    }
    _ocNote(h, problems.length ? "warn" : "");

    // The profit column on this page is worked out from these costs, so it is
    // wrong until the list is re-read. Only when something actually changed.
    if(j.set && typeof ordersLoad === "function") ordersLoad();
  }catch(e){
    _ocNote("<b>Nothing was changed.</b> That file could not be uploaded.", "bad");
  }
}
