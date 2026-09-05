/* static/js/ordertracking.js -- where each parcel is, on the Orders page.
 *
 *     "i want the orders page to show tracking ids put in the account which have
 *      tracking ids uploaded and track them with the carrier and show me the
 *      status of the trackings, is it delivered, out for delivery, dropped off,
 *      in transit, whatever is on the website."
 *
 * WHY THE NUMBERS ARE UPLOADED RATHER THAN FETCHED
 * Amazon does not give back the tracking a seller uploads. That was measured
 * against every endpoint that could carry it -- getOrder, getOrderItems, the
 * 33-column All Orders report and MerchantFulfillment -- and none of them does.
 * So the numbers come in on a sheet, in the same shape as the per-order costs
 * beside them, because it is the same act and somebody who has done that once
 * already knows how to do this.
 *
 * TWO BUTTONS, TWO DIFFERENT COSTS. Uploading is free and touches nothing
 * outside this app. Checking contacts a tracking service, so it is a separate,
 * deliberate press -- and it refuses in words when no service is set up rather
 * than filling the column with a status nobody asked anyone about.
 */

function _otQS(){
  const q = [];
  const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
            ? CUR_ACCOUNT.id : "";
  const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
  // ONE NAME: `account`, the spelling every route reads now.
  if(a) q.push("account=" + encodeURIComponent(a));
  if(m && m !== "__all__") q.push("marketplace=" + encodeURIComponent(m));
  return q.join("&");
}

function _otNote(html, tone){
  const el = document.getElementById("ordtrack_result");
  if(!el){ if(typeof toast === "function") toast(String(html).replace(/<[^>]+>/g, "")); return; }
  if(!html){ el.innerHTML = ""; return; }
  const border = tone === "bad" ? "var(--red-line)"
               : tone === "warn" ? "var(--warn-line)" : "var(--line2)";
  el.innerHTML = '<div style="padding:9px 11px;border:1px solid ' + border
    + ';border-radius:6px;font-size:12px;line-height:1.55">' + html + '</div>';
}

/* A parcel belongs to one order of one account, so both have to be settled
 * before either button does anything -- a sheet downloaded without them would
 * be full of somebody else's orders. */
function _otReady(){
  const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
            ? CUR_ACCOUNT.id : "";
  const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
  if(!a){ _otNote("Open an account first — tracking is recorded against one "
                  + "order of one account.", "warn"); return false; }
  if(!m || m === "__all__"){
    _otNote("Pick a single marketplace first. An order and its parcel belong to "
            + "one marketplace, and \"all marketplaces\" cannot say which.", "warn");
    return false;
  }
  return true;
}

function trackingTemplate(untrackedOnly){
  if(!_otReady()) return;
  const qs = _otQS() + (untrackedOnly ? "&untracked=1" : "");
  // A plain navigation, not fetch(): this is a file download and the browser
  // already knows how to save one.
  window.location = "/tracking/template.csv?" + qs;
  _otNote(untrackedOnly
    ? "Downloading the orders with no tracking recorded yet. Fill in "
      + "<b>tracking</b>, and <b>carrier</b> if you know it, then upload it back."
    : "Downloading every order in this window. <b>tracking now</b> shows what is "
      + "already recorded; fill in <b>tracking</b> only where it is missing or "
      + "wrong. Rows left blank are skipped, so an unedited file changes nothing.");
}

function trackingUploadOpen(){
  if(!_otReady()) return;
  const el = document.getElementById("ordtrack_file");
  if(el){ el.value = ""; el.click(); }
}

async function trackingUpload(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  _otNote('<span class="genspin"></span> Reading ' + String(f.name) + '…');
  try{
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch("/tracking/upload?" + _otQS(), {method: "POST", body: fd});
    const j = await r.json();
    if(!j || !j.ok){
      _otNote("<b>Nothing was changed.</b> "
              + (j && j.error ? String(j.error) : "That file could not be read."),
              "bad");
      return;
    }

    // EVERY OUTCOME, NOT JUST THE GOOD ONE. "47 recorded" beside 30 silently
    // dropped rows is the version of this that gets trusted and should not be.
    let h = "<b>" + (j.note || "Done.") + "</b>";
    const problems = (j.rows || []).filter(function(x){ return x.result !== "recorded"; });
    if(problems.length){
      h += '<div style="margin-top:6px">These rows were not applied:</div>'
        + '<ul style="margin:4px 0 0 16px">';
      problems.slice(0, 12).forEach(function(x){
        h += "<li>" + String(x.order_id || "(no order number)")
          + (x.tracking ? " — " + String(x.tracking) : "")
          + " — " + String(x.result) + "</li>";
      });
      h += "</ul>";
      if(problems.length > 12)
        h += '<div class="cc">…and ' + (problems.length - 12) + " more.</div>";
    }
    // WHICH CARRIERS IT READ. A column of carriers that all came out blank, or
    // all came out as one carrier, is the sort of mistake that is invisible in
    // a success message and obvious in a count.
    const cs = j.carriers || {};
    const names = Object.keys(cs);
    if(names.length){
      h += '<div class="cc" style="margin-top:6px">Carriers read: '
        + names.map(function(n){ return String(n) + " × " + cs[n]; }).join(", ")
        + ".</div>";
    }
    _otNote(h, problems.length ? "warn" : "");
    if(j.set && typeof ordersLoad === "function") ordersLoad();
  }catch(e){
    _otNote("<b>Nothing was changed.</b> That file could not be uploaded.", "bad");
  }
}

async function trackingCheck(){
  if(!_otReady()) return;
  const b = document.getElementById("ord_trackcheck");
  if(b) b.disabled = true;
  _otNote('<span class="genspin"></span> Asking the carriers where these are…');
  try{
    const r = await fetch("/tracking/refresh?" + _otQS(),
      {method: "POST", headers: {"Content-Type": "application/json"},
       body: JSON.stringify({limit: 100})});
    const j = await r.json();
    if(!j || !j.ok){
      // NOT AN ERROR IN RED WHEN IT IS A SETTING THAT IS MISSING. The usual
      // reason is that no tracking service is set up, which is a thing to go
      // and do rather than a fault to report.
      _otNote("<b>Nothing was checked.</b> "
              + (j && j.error ? String(j.error) : "The check could not be run."),
              "warn");
      return;
    }
    let h = "<b>Checked " + (j.checked || 0) + " parcel"
          + ((j.checked === 1) ? "" : "s") + ".</b>";
    if(j.failed) h += " " + j.failed + " could not be read — the reason is on the row.";
    if(j.left)   h += " " + j.left + " still to do; press again.";
    if(!j.checked && !j.failed)
      h += " Nothing needed checking — every parcel here is already delivered, "
         + "or none has a tracking number yet.";
    _otNote(h, j.failed ? "warn" : "");
    if(typeof ordersLoad === "function") ordersLoad();
  }catch(e){
    _otNote("<b>Nothing was checked.</b> The check could not be run.", "bad");
  }finally{
    if(b) b.disabled = false;
  }
}
