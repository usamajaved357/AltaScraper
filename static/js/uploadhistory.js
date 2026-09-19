// static/js/uploadhistory.js — the Upload history page.
//
//     "i want to track which files were uploaded recently for creating listings
//      like amazon has it it stores file which were used to create or make any
//      changes in the listings using the files or templates"
//     "all 7, keep forever, new sidebar item"
//
// Seller Central's "Spreadsheet upload status", for this app: one row per file
// that changed data, the original file to download, and the processing report
// saying what happened to each row. Recording happens on the server
// (domain/upload_log.py); this page only reads /uploads/*.
//
// Every address carries the account (acctUrl), so the doorman checks it and an
// upload is only ever served to the account it belongs to.

let UPH = { uploads: [], kinds: {}, open: null, detail: {}, loading: false, error: "" };

const UPH_STATUS = {
  done:             {label: "Done",              color: "var(--ok, #1a7f37)"},
  done_with_errors: {label: "Done, with errors", color: "var(--warn, #b26a00)"},
  failed:           {label: "Failed",            color: "var(--red, #c62828)"},
};

function _uphFmtBytes(n){
  n = Number(n || 0);
  if(n < 1024) return n + " B";
  if(n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

/* The result in words: what the file did, not a row of zeros. Pure. */
function uphResultText(u){
  const parts = [];
  if(u.rows_ok) parts.push(u.rows_ok + " done");
  if(u.rows_skipped) parts.push(u.rows_skipped + " skipped");
  if(u.rows_error) parts.push(u.rows_error + " with errors");
  if(!parts.length) parts.push(u.status === "failed" ? "nothing applied" : "no rows changed");
  return parts.join(" · ");
}

function _uphLink(path, id){
  return (typeof acctUrl === "function") ? acctUrl(path + id) : (path + id);
}

function uploadsRender(){
  const box = document.getElementById("uph_body");
  if(!box) return;
  const sel = document.getElementById("uph_kind");
  if(sel && sel.options.length <= 1){
    Object.keys(UPH.kinds || {}).forEach(function(k){
      const o = document.createElement("option");
      o.value = k; o.textContent = UPH.kinds[k];
      sel.appendChild(o);
    });
  }
  if(UPH.error){
    box.innerHTML = '<div class="sresfail">' + esc(UPH.error) + '</div>';
    return;
  }
  if(UPH.loading && !UPH.uploads.length){
    box.innerHTML = '<div class="cc" style="padding:14px">Loading uploads…</div>';
    return;
  }
  if(!UPH.uploads.length){
    box.innerHTML = '<div class="empty">No uploads recorded for this account yet. '
      + 'Every file you upload from now on — product templates, cost sheets, order costs, '
      + 'tracking, supplier links, min prices and Miles item lists — is kept here with what it did.</div>';
    return;
  }
  let html = '<div style="overflow-x:auto"><table class="uph-table" style="width:100%;border-collapse:collapse;font-size:12.5px">'
    + '<thead><tr style="text-align:left;border-bottom:1px solid var(--line2)">'
    + '<th style="padding:6px">Uploaded</th><th style="padding:6px">Type</th>'
    + '<th style="padding:6px">File</th><th style="padding:6px">Status</th>'
    + '<th style="padding:6px">Result</th><th style="padding:6px">By</th>'
    + '<th style="padding:6px"></th></tr></thead><tbody>';
  UPH.uploads.forEach(function(u){
    const st = UPH_STATUS[u.status] || {label: u.status || "", color: "inherit"};
    const isOpen = UPH.open === u.id;
    html += '<tr style="border-bottom:1px solid var(--line2);vertical-align:top">'
      + '<td style="padding:6px;white-space:nowrap">' + esc(u.uploaded_at || "") + '</td>'
      + '<td style="padding:6px">' + esc(u.kind_label || u.kind || "") + '</td>'
      + '<td style="padding:6px;word-break:break-all">' + esc(u.filename || "")
      +   '<div class="cc" style="font-size:11px">' + _uphFmtBytes(u.bytes)
      +   (u.marketplace ? " · " + esc(u.marketplace) : "") + '</div></td>'
      + '<td style="padding:6px;white-space:nowrap"><span style="font-weight:600;color:' + st.color + '">' + esc(st.label) + '</span></td>'
      + '<td style="padding:6px">' + esc(uphResultText(u))
      +   (u.sku_count ? '<div class="cc" style="font-size:11px">' + u.sku_count + ' SKU(s)</div>' : "") + '</td>'
      + '<td style="padding:6px">' + esc(u.uploaded_by || "owner") + '</td>'
      + '<td style="padding:6px;white-space:nowrap">'
      +   (u.has_file ? '<a class="db-chip" href="' + esc(_uphLink("/uploads/file/", u.id)) + '" title="Download the file exactly as it was uploaded"><i class="ti ti-download"></i> File</a> ' : "")
      +   '<a class="db-chip" href="' + esc(_uphLink("/uploads/report/", u.id)) + '" title="Download what happened to every row"><i class="ti ti-report"></i> Report</a> '
      +   '<button class="db-chip" onclick="uploadsToggle(' + Number(u.id) + ')">' + (isOpen ? "Hide" : "Details") + '</button>'
      + '</td></tr>';
    if(isOpen){
      html += '<tr><td colspan="7" style="padding:8px 6px 14px">'
        + _uphDetailHtml(u) + '</td></tr>';
    }
  });
  html += '</tbody></table></div>';
  box.innerHTML = html;
}

function _uphDetailHtml(u){
  const d = UPH.detail[u.id];
  let out = '<div style="font-size:12.5px;margin-bottom:6px">' + esc(u.error || u.summary || "") + '</div>';
  if((u.skus || []).length){
    out += '<div class="cc" style="font-size:11.5px;margin-bottom:6px"><b>SKUs:</b> '
      + u.skus.slice(0, 60).map(esc).join(", ")
      + (u.sku_count > 60 ? " … and " + (u.sku_count - 60) + " more (in the report)" : "") + '</div>';
  }
  if(!d) return out + '<div class="cc">Loading rows…</div>';
  const rows = d.report || [];
  if(!rows.length) return out + '<div class="cc">This upload reported no per-row detail.</div>';
  const cols = [];
  rows.forEach(function(r){ Object.keys(r || {}).forEach(function(k){ if(cols.indexOf(k) < 0) cols.push(k); }); });
  out += '<div style="max-height:320px;overflow:auto"><table style="border-collapse:collapse;font-size:11.5px">'
    + '<tr>' + cols.map(function(c){ return '<th style="text-align:left;padding:3px 6px;border-bottom:1px solid var(--line2)">' + esc(c) + '</th>'; }).join("") + '</tr>'
    + rows.slice(0, 200).map(function(r){
        return '<tr>' + cols.map(function(c){
          let v = (r || {})[c];
          if(Array.isArray(v)) v = v.join("; ");
          else if(v && typeof v === "object") v = JSON.stringify(v);
          return '<td style="padding:3px 6px;border-bottom:1px solid var(--line2);word-break:break-word">' + esc(v == null ? "" : String(v)) + '</td>';
        }).join("") + '</tr>';
      }).join("")
    + '</table></div>'
    + (rows.length > 200 ? '<div class="cc" style="font-size:11px">Showing 200 of ' + rows.length + ' rows — download the report for all of them.</div>' : "");
  return out;
}

async function uploadsToggle(id){
  UPH.open = (UPH.open === id) ? null : id;
  uploadsRender();
  if(UPH.open !== id || UPH.detail[id]) return;
  try{
    const j = await (await fetch(_uphLink("/uploads/detail/", id))).json();
    UPH.detail[id] = (j && j.ok) ? j.upload : {report: []};
  }catch(e){
    UPH.detail[id] = {report: []};
  }
  uploadsRender();
}

async function uploadsLoad(){
  UPH.loading = true; UPH.error = ""; uploadsRender();
  const sel = document.getElementById("uph_kind");
  const kind = sel ? sel.value : "";
  try{
    const url = "/uploads/list" + (kind ? "?kind=" + encodeURIComponent(kind) : "");
    const j = await (await fetch((typeof acctUrl === "function") ? acctUrl(url) : url)).json();
    if(!j || !j.ok) throw new Error((j && j.error) || "could not read the upload history");
    UPH.uploads = j.uploads || [];
    UPH.kinds = j.kinds || {};
  }catch(e){
    UPH.error = String((e && e.message) || e);
  }
  UPH.loading = false;
  uploadsRender();
}

function uploadsOnOpen(){
  UPH.open = null; UPH.detail = {};
  uploadsLoad();
}

/* A file the browser reads itself (min prices, Miles), sent along so it can be
 * kept. {name, data} with data as a data: URL. Resolves null on failure: the
 * upload must still go through if the file cannot be attached. */
async function uphFileForUpload(file){
  if(!file || typeof _fileToDataURL !== "function") return null;
  try{
    // The app's one file-to-data-URL reader (listings.js), not a second copy.
    const data = await _fileToDataURL(file);
    return {name: file.name || "upload", data: data};
  }catch(e){
    return null;
  }
}
