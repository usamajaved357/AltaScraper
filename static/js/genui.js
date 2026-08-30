// static/js/genui.js -- the generator's progress, rendered instead of streamed raw.
//
// Layout is genui-mockup.html's, structure for structure. This file owns only
// the RENDERING: submit.js keeps the EventSource and hands each line here
// (CLAUDE.md Rule 12), so there is still exactly one place that opens a stream.
//
// THE PATTERNS BELOW COME FROM THE GENERATOR'S ACTUAL OUTPUT, not from a guess
// at it. That distinction is the whole risk in this file: a parser matched
// against strings the generator does not print produces a screen that sits at
// "0 of 0" through a twenty-minute run, and looks exactly like a hung app.
//
// What amazon_listing_generator.py really prints per product:
//
//     [3/50] Expandable Garden Hose 50ft            <- index, total AND name
//       ASIN: B0... | SKU: 12.99_3Days_B0... | UPC: ...
//       PRE-FLIGHT 1/3: Fetching eBay source data (primary)
//       PRE-FLIGHT 2/3: Market pricing + fees
//       PRE-FLIGHT 3/3: Attribute schema
//       STEP 1/3: Keywords
//       STEP 2/3: Claude listing generation
//       STEP 3/3: Writing to Google Sheet
//       Done (12.4s)
//
// so the count, the total, the product name and the elapsed time are all
// already in the stream and none of them has to be inferred.
//
// FIVE BADGES, as mocked -- but labelled for what the generator actually does.
// The mockup's "eBay data / Category / AI copy / Fields / Checks" were a
// sketch; "Category" and "Fields" are not steps it reports, while pricing is.
// Badges nobody can light are worse than none, so each of these is driven by a
// line that genuinely appears.

const GU_STEPS = [
  {key: "source",  label: "Source data", re: /PRE-FLIGHT 1\/3/i},
  {key: "pricing", label: "Pricing",     re: /PRE-FLIGHT 2\/3/i},
  {key: "fields",  label: "Fields",      re: /PRE-FLIGHT 3\/3/i},
  {key: "copy",    label: "AI copy",     re: /STEP [12]\/3/i},
  {key: "checks",  label: "Checks",      re: /STEP 3\/3|Compliance:/i},
];

// A product header: "[3/50] Some Product Name".
const GU_HEAD = /^\s*\[(\d+)\/(\d+)\]\s+(.*?)\s*$/;
const GU_DONE = /^\s*Done \(([\d.]+)s\)/i;
const GU_SKIP = /^\s*SKIP\s*--\s*(.*)$/i;
// Errors and warnings, from the same vocabulary _logLineEl already used, so the
// two views agree about what counts as bad.
const GU_ERR  = /\[E\]|Claude failed|could not|failed|traceback|error\b/i;
const GU_WARN = /\[W\]|WARN\b|warning/i;
// Stream-level markers the ROUTE emits, not the generator.
const GU_META = /^\s*\[(start|done|input|warnings|busy|error)\]/i;

let GU = null;

function _guNew(){
  return {total: 0, done: 0, warnings: 0, index: 0,
          name: "", steps: {}, rows: [], started: 0, finished: false,
          rowWarn: 0, raw: []};
}

function _guEl(id){ return document.getElementById(id); }
function _guEsc(s){
  return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];
  });
}

/* The whole panel, drawn once. Re-render is cheap and keeps one source of
 * truth for the markup rather than a dozen partial DOM pokes. */
function genuiRender(){
  const host = _guEl("genui");
  if(!host || !GU) return;
  const s = GU;
  const running = Math.max(0, (s.name && !s.finished) ? 1 : 0);
  const shown = s.total ? (s.done + " of " + s.total)
                        : (s.done + (s.done === 1 ? " listing" : " listings"));
  const sub = s.finished
    ? ("Done — " + s.done + " generated"
       + (s.warnings ? ", " + s.warnings + " with warnings" : ""))
    : "Generating listings...";

  const steps = GU_STEPS.map(function(st){
    const state = s.steps[st.key] || "";
    const mark = state === "done" ? "✓ " : (state === "active" ? "⟳ " : "");
    return '<span class="gu-step ' + state + '">' + mark + _guEsc(st.label) + '</span>';
  }).join("");

  const rows = s.rows.length
    ? s.rows.map(function(r){
        return '<div class="gu-row">'
          + '<span class="gu-n">' + _guEsc(r.n) + '</span>'
          + '<span class="gu-name" title="' + _guEsc(r.name) + '">' + _guEsc(r.name) + '</span>'
          + '<span class="gu-badge ' + r.cls + '">' + _guEsc(r.badge) + '</span>'
          + '<span class="gu-time">' + _guEsc(r.time || "") + '</span>'
          + '</div>';
      }).join("")
    : '<div class="gu-empty">Nothing has finished yet.</div>';

  const openAttr = host.dataset.open === "1" ? "" : " hidden";
  host.innerHTML =
      '<div class="gu' + (s.finished ? " is-done" : "") + '">'
    +   '<div class="gu-min">'
    +     '<div class="gu-spin"></div>'
    +     '<div class="gu-count">' + _guEsc(shown) + '</div>'
    +     '<div class="gu-sub">' + _guEsc(sub) + '</div>'
    +     '<div class="gu-pills">'
    +       '<span class="gu-pill ok"><b>' + s.done + '</b> done</span>'
    +       '<span class="gu-pill warn"><b>' + s.warnings + '</b> warnings</span>'
    +       '<span class="gu-pill run"><b>' + running + '</b> in progress</span>'
    +     '</div>'
    +   '</div>'
    +   '<button class="gu-toggle" onclick="genuiToggle()">'
    +     (host.dataset.open === "1" ? "Hide details" : "Show details") + '</button>'
    +   (s.finished
        ? '<button class="gu-go" onclick="navTo(\'listings\')">View listings</button>'
        : "")
    +   '<div class="gu-details"' + openAttr + '>'
    +     '<div class="gu-now">'
    +       '<div class="gu-nowlbl">Now processing</div>'
    +       '<div class="gu-nowname">'
    +         (s.name ? _guEsc(s.name) : '<span class="gu-nowlbl">waiting…</span>')
    +       '</div>'
    +       '<div class="gu-steps">' + steps + '</div>'
    +     '</div>'
    +     '<div class="gu-list">' + rows + '</div>'
    +   '</div>'
    +   '<details class="gu-raw"><summary>Raw log</summary>'
    +     '<div class="gu-rawbody">' + s.raw.join("") + '</div></details>'
    + '</div>';
}

function genuiToggle(){
  const host = _guEl("genui");
  if(!host) return;
  host.dataset.open = host.dataset.open === "1" ? "0" : "1";
  genuiRender();
}

function genuiStart(){
  GU = _guNew();
  GU.started = Date.now();
  const host = _guEl("genui");
  if(host && !host.dataset.open) host.dataset.open = "0";
  genuiRender();
}

/* Close off whatever product is open, and file it in the completed list. */
function _guCloseCurrent(time, badge, cls){
  if(!GU || !GU.name) return;
  GU.rows.unshift({n: GU.index || GU.rows.length + 1, name: GU.name,
                   badge: badge, cls: cls, time: time || ""});
  if(cls !== "skip") GU.done++;
  if(GU.rowWarn) GU.warnings++;
  GU.name = ""; GU.steps = {}; GU.rowWarn = 0;
}

/* ONE LINE IN. Returns nothing; the panel redraws itself. */
function genuiLine(text){
  if(!GU) genuiStart();
  const s = String(text == null ? "" : text);
  const bare = s.replace(/\[[0-9;]*m/g, "");

  // The raw log keeps EVERYTHING, matched or not. It is the only place an
  // unrecognised failure can still be read.
  const cls = GU_ERR.test(bare) ? "e" : (GU_WARN.test(bare) ? "w" : "");
  GU.raw.push('<div class="' + cls + '">' + _guEsc(bare) + "</div>");
  if(GU.raw.length > 800) GU.raw.splice(0, GU.raw.length - 800);

  if(GU_META.test(bare)){ genuiRender(); return; }

  const head = bare.match(GU_HEAD);
  if(head){
    // A new product starts: file the previous one if the generator never said
    // "Done" for it (a crash mid-product, which would otherwise vanish).
    if(GU.name) _guCloseCurrent("", "unfinished", "bad");
    GU.index = parseInt(head[1], 10) || 0;
    GU.total = parseInt(head[2], 10) || GU.total;
    GU.name  = head[3] || "";
    GU.steps = {}; GU.rowWarn = 0;
    genuiRender();
    return;
  }

  const skip = bare.match(GU_SKIP);
  if(skip){
    _guCloseCurrent("", "skipped", "skip");
    genuiRender();
    return;
  }

  const fin = bare.match(GU_DONE);
  if(fin){
    const secs = Math.round(parseFloat(fin[1]) || 0);
    const warned = GU.rowWarn > 0;
    _guCloseCurrent(secs + "s",
                    warned ? (GU.rowWarn + " warning" + (GU.rowWarn === 1 ? "" : "s"))
                           : "done",
                    warned ? "warn" : "");
    genuiRender();
    return;
  }

  // Step badges: the matched one goes active, everything before it is done.
  for(let i = 0; i < GU_STEPS.length; i++){
    if(GU_STEPS[i].re.test(bare)){
      for(let j = 0; j < i; j++) GU.steps[GU_STEPS[j].key] = "done";
      GU.steps[GU_STEPS[i].key] = "active";
      genuiRender();
      return;
    }
  }

  // Anything else only matters if it is bad. An unrecognised INFO line is
  // noise; an unrecognised ERROR is the thing you opened this screen for.
  if(GU_ERR.test(bare) || GU_WARN.test(bare)){
    GU.rowWarn++;
    genuiRender();
  }
}

function genuiEnd(){
  if(!GU) return;
  if(GU.name) _guCloseCurrent("", "unfinished", "bad");
  GU.finished = true;
  genuiRender();
}
