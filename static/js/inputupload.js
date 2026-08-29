// ===================== A FILE, INTO THE PRODUCT QUEUE =====================
//
// Drag a .csv, .tsv or .xlsx onto the zone, or browse for one, and its rows
// join the queue that the Google import and the hand-add form already fill.
// The same queue, so the generator neither knows nor cares which of the three
// put a row there.
//
// WHAT THIS SCREEN HAS TO GET RIGHT, and why each piece is here:
//
//   * A FILE THAT IMPORTED NOTHING MUST SAY WHY. The failure is almost always
//     column names, so the error card lists the headers the file actually
//     had. "No columns matched" on its own leaves you guessing at spelling;
//     seeing your own "Buy Price" next to what was expected ends it.
//   * WHAT WAS UNDERSTOOD IS AS IMPORTANT AS WHAT WAS ADDED. A file can import
//     200 rows and quietly drop the cost column. The matched columns are shown
//     as tags, and the ignored ones beside them in grey.
//   * A BIG FILE MUST NOT LOOK FROZEN. The uploading state names the file and
//     its size, so a 4 MB spreadsheet reads as working rather than hung.
//
// Uploads ADD. A second file adds to the first; nothing here can empty the
// queue. Nothing here reaches Amazon, eBay or Google either -- this writes to
// the local queue and stops.
//
// Self-contained by design (Rule 7): one state object, no new shared globals,
// and its own escaper rather than a dependency on listings.js being loaded.

let IUP = {busy: false, last: null};

function _iupEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function _iupSize(n){
  n = Number(n) || 0;
  if(n < 1024) return n + " B";
  if(n < 1024 * 1024) return (n / 1024).toFixed(0) + " KB";
  return (n / (1024 * 1024)).toFixed(1) + " MB";
}

// Column keys are stored names; these are what a person calls them.
const IUP_LABELS = {
  ebay_url: "Source link", amazon_url: "Amazon link", competitor_asin: "ASIN",
  item_name: "Name", source_cost: "Cost", selling_price: "Sell at",
  handling_time: "Handling days", upc: "Barcode",
};
function _iupLabel(k){ return IUP_LABELS[k] || String(k || ""); }

/* The drop zone. Rendered into whatever container the Generate screen gives it. */
function inputUploadPanel(){
  return ''
  + '<div class="iup-wrap">'
  +   '<div class="iup-zone" id="iup_zone"'
  +     ' ondragover="iupDragOver(event)" ondragleave="iupDragLeave(event)"'
  +     ' ondrop="iupDrop(event)" onclick="iupBrowse()">'
  +     '<input type="file" id="iup_file" accept=".csv,.tsv,.txt,.xlsx"'
  +       ' style="display:none" onchange="iupPicked(this)">'
  +     '<div class="iup-ico"><i class="ti ti-file-spreadsheet"></i></div>'
  +     '<div class="iup-big">Drop a spreadsheet here</div>'
  +     '<div class="iup-sub">.csv, .tsv or .xlsx — or click to browse.'
  +       ' Rows are <b>added</b> to the queue; nothing is replaced.</div>'
  +   '</div>'
  +   '<div class="iup-foot">'
  +     '<a href="/input/upload/template" class="iup-link"'
  +       ' title="A blank CSV with the column names this understands, and one example row">'
  +       '<i class="ti ti-download"></i> Download blank template</a>'
  +     '<span class="iup-hint">Only a source link <b>or</b> an Amazon link is'
  +       ' needed — not both.</span>'
  +   '</div>'
  +   '<div id="iup_result"></div>'
  + '</div>';
}

// ---- picking a file --------------------------------------------------------

function iupBrowse(){
  if(IUP.busy) return;
  const el = document.getElementById("iup_file");
  if(el) el.click();
}
function iupPicked(el){
  const f = el && el.files && el.files[0];
  // Cleared so choosing the SAME file twice fires change again -- re-uploading
  // after fixing the column names is the common second action.
  if(el) el.value = "";
  if(f) iupUpload(f);
}
function iupDragOver(ev){
  ev.preventDefault();
  const z = document.getElementById("iup_zone");
  if(z && !IUP.busy) z.classList.add("iup-over");
}
function iupDragLeave(ev){
  ev.preventDefault();
  const z = document.getElementById("iup_zone");
  if(z) z.classList.remove("iup-over");
}
function iupDrop(ev){
  ev.preventDefault();
  iupDragLeave(ev);
  if(IUP.busy) return;
  const dt = ev.dataTransfer;
  const f = dt && dt.files && dt.files[0];
  if(f) iupUpload(f);
}

// ---- the upload ------------------------------------------------------------

async function iupUpload(file){
  if(IUP.busy || !file) return;
  const host = document.getElementById("iup_result");
  IUP.busy = true;
  if(host){
    host.innerHTML = '<div class="iup-card iup-working">'
      + '<span class="genspin"></span> Reading <b>' + _iupEsc(file.name) + '</b>'
      + ' <span class="iup-dim">(' + _iupSize(file.size) + ')</span>…'
      + '</div>';
  }
  try{
    const fd = new FormData();
    fd.append("file", file, file.name);
    const res = await fetch("/input/upload", {method: "POST", body: fd});
    let j = null;
    try{ j = await res.json(); }catch(e){ j = null; }
    if(!j){
      _iupError({error: "The server did not answer with a result ("
                        + res.status + ")."}, file);
      return;
    }
    IUP.last = j;
    if(!j.ok){ _iupError(j, file); return; }
    _iupSuccess(j, file);
    // The queue count and the table below it are now out of date.
    if(typeof inputQueueLoad === "function"){ try{ await inputQueueLoad(); }catch(e){} }
  }catch(e){
    _iupError({error: String(e)}, file);
  }finally{
    IUP.busy = false;
  }
}

function _iupTags(j){
  const ok = (j.mapped_columns || []).map(function(c){
    return '<span class="iup-tag iup-tag-on">' + _iupEsc(_iupLabel(c)) + '</span>';
  }).join("");
  const no = (j.ignored_columns || []).map(function(c){
    return '<span class="iup-tag iup-tag-off" title="This column was not '
         + 'recognised, so its values were not stored">' + _iupEsc(c) + '</span>';
  }).join("");
  let h = '<div class="iup-tags"><span class="iup-dim">Understood:</span> '
        + (ok || '<span class="iup-dim">none</span>') + '</div>';
  if(no){
    h += '<div class="iup-tags"><span class="iup-dim">Ignored:</span> ' + no
       + '</div>';
  }
  return h;
}

function _iupPreview(j){
  const rows = j.preview || [];
  if(!rows.length) return "";
  const cols = (j.mapped_columns || []).slice(0, 5);
  if(!cols.length) return "";
  let h = '<div class="iup-prev"><div class="iup-dim" style="margin-bottom:5px">'
        + 'First ' + rows.length + ' of what was added:</div>'
        + '<table class="iup-table"><thead><tr>';
  cols.forEach(function(c){ h += '<th>' + _iupEsc(_iupLabel(c)) + '</th>'; });
  h += '</tr></thead><tbody>';
  rows.forEach(function(r){
    h += '<tr>';
    cols.forEach(function(c){
      const v = String(r[c] == null ? "" : r[c]);
      h += '<td title="' + _iupEsc(v) + '">'
         + _iupEsc(v.length > 46 ? v.slice(0, 45) + "…" : v) + '</td>';
    });
    h += '</tr>';
  });
  return h + '</tbody></table></div>';
}

function _iupSuccess(j, file){
  const host = document.getElementById("iup_result");
  if(!host) return;
  const added = Number(j.added || 0);
  const skipped = Number(j.skipped || 0);
  const errs = j.errors || [];
  // NOTHING ADDED IS NOT A SUCCESS, whatever the status code said. The file
  // parsed; it just had nothing usable in it, and a green tick over "0 added"
  // is the most misleading thing this screen could show.
  const bad = added === 0;

  let h = '<div class="iup-card ' + (bad ? "iup-warn" : "iup-ok") + '">'
    + '<div class="iup-head">'
    +   '<i class="ti ' + (bad ? "ti-alert-triangle" : "ti-check") + '"></i> '
    +   (bad ? 'Nothing was added from ' : 'Added ' + added + ' product'
             + (added === 1 ? '' : 's') + ' from ')
    +   '<b>' + _iupEsc(file ? file.name : j.filename) + '</b>'
    + '</div>';

  if(skipped){
    h += '<div class="iup-line">' + skipped + ' row' + (skipped === 1 ? '' : 's')
       + ' had no source link, Amazon link, ASIN or name, so '
       + (skipped === 1 ? 'it was' : 'they were') + ' left out. Heading rows,'
       + ' totals and notes usually land here.</div>';
  }
  h += _iupTags(j);
  if(bad && !skipped){
    h += '<div class="iup-line">The columns were understood but every row was '
       + 'empty.</div>';
  }
  h += _iupPreview(j);

  if(errs.length){
    h += '<div class="iup-errs"><div class="iup-dim">Rows that could not be '
       + 'read:</div>';
    errs.forEach(function(e){ h += '<div>' + _iupEsc(e) + '</div>'; });
    h += '</div>';
  }

  h += '<div class="iup-line iup-dim">The queue now holds <b>'
     + Number(j.count || 0) + '</b>.</div>';
  h += '<div class="iup-actions">'
    +   '<button class="mktbtn on" onclick="navTo(\'generate\')">'
    +     '<i class="ti ti-player-play"></i> Generate listings now</button>'
    // REVIEW BEFORE GENERATING. The queue table is on this screen already, so
    // this scrolls to it rather than navigating somewhere -- a "review" button
    // that leaves the page you are reviewing on is a strange thing to press.
    +   '<button class="mktbtn" onclick="iupReview()">'
    +     '<i class="ti ti-list-check"></i> Review the queue</button>'
    +   '<button class="mktbtn" onclick="iupReset()">'
    +     '<i class="ti ti-upload"></i> Upload another</button>'
    + '</div>'
    + '</div>';
  host.innerHTML = h;
}

function _iupError(j, file){
  const host = document.getElementById("iup_result");
  if(!host) return;
  const found = j.found_columns || [];
  let h = '<div class="iup-card iup-bad">'
    + '<div class="iup-head"><i class="ti ti-alert-circle"></i> '
    + _iupEsc(file ? file.name : (j.filename || "That file")) + ' was not imported'
    + '</div>'
    + '<div class="iup-line">' + _iupEsc(j.error || "Unknown error") + '</div>';
  if(found.length){
    // THE WHOLE DIAGNOSIS. Their spelling, in their file, next to a template
    // that names ours.
    h += '<div class="iup-tags"><span class="iup-dim">Columns found in your '
       + 'file:</span> '
       + found.map(function(c){
           return '<span class="iup-tag iup-tag-off">' + _iupEsc(c) + '</span>';
         }).join("")
       + '</div>';
  }
  h += '<div class="iup-actions">'
    +   '<a class="mktbtn" href="/input/upload/template">'
    +     '<i class="ti ti-download"></i> Download the template</a>'
    +   '<button class="mktbtn" onclick="iupReset()">'
    +     '<i class="ti ti-upload"></i> Try another file</button>'
    + '</div></div>';
  host.innerHTML = h;
}

function iupReset(){
  const host = document.getElementById("iup_result");
  if(host) host.innerHTML = "";
}

function iupReview(){
  const t = document.getElementById("inputsheet_body")
         || document.getElementById("inputsheetwrap");
  if(t && t.scrollIntoView) t.scrollIntoView({behavior: "smooth", block: "start"});
}
