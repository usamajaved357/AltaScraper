// ============ THE DAILY ROUND ============
//
//   "i want to design a page where all of these metrics results are being shown
//    and it highlights the things which are off track"
//
// Replaces a Fillout checklist of fourteen things somebody opens every morning,
// works through in Seller Central and ticks off. A checklist is a way of
// remembering to LOOK; the looking is what a computer should do, and the only
// output that matters is the short list of things that are wrong today.
//
// So the page opens with that list. Everything that is fine is folded away
// underneath, and everything that COULD NOT BE CHECKED is its own group with
// the reason on every row — never a green tick, because a check that cannot run
// and renders as fine is the paper form's exact failure: ticked without the
// looking.

const DAILY = {data: null, loading: false, showOk: false, note: ""};

function dailyOnOpen(){ if(!DAILY.data) dailyLoad(); else dailyRender(); }

function _dyQs(){
  const a = (typeof WS_ID !== "undefined" && WS_ID) ? WS_ID : "";
  const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
  return "?id=" + encodeURIComponent(a) + "&marketplace=" + encodeURIComponent(m);
}

async function dailyLoad(){
  DAILY.loading = true; DAILY.note = ""; dailyRender();
  try{
    const j = await (await fetch("/daily/check" + _dyQs())).json();
    if(j && j.ok) DAILY.data = j;
    else DAILY.note = (j && j.error) || "Could not run the round.";
  }catch(e){ DAILY.note = "Could not run the round: " + e; }
  DAILY.loading = false; dailyRender();
}

function dailyToggleOk(){ DAILY.showOk = !DAILY.showOk; dailyRender(); }

function _dyEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function _dyRow(c){
  const icon = c.status === "off" ? "ti-alert-triangle"
             : c.status === "unknown" ? "ti-help-circle" : "ti-check";
  return '<div class="dy-row ' + c.status + '">'
    + '<i class="ti ' + icon + ' dy-ico"></i>'
    + '<div class="dy-main">'
    +   '<div class="dy-t">' + _dyEsc(c.title)
    +     (c.value ? ' <span class="dy-v">' + _dyEsc(c.value) + '</span>' : '')
    +   '</div>'
    +   (c.detail ? '<div class="dy-d">' + _dyEsc(c.detail) + '</div>' : '')
    // WHAT IS MISSING, on the row. Not a tooltip: the whole point of showing a
    // check that could not run is that somebody still has to go and look, and
    // they need to know where.
    +   (c.needs ? '<div class="dy-needs">Cannot check &mdash; ' + _dyEsc(c.needs)
                 + '</div>' : '')
    +   (c.action ? '<div class="dy-act">' + _dyEsc(c.action) + '</div>' : '')
    + '</div>'
    + '<span class="dy-g cc">' + _dyEsc(c.group) + '</span>'
    + '</div>';
}

function dailyRender(){
  const host = document.getElementById("dy_body");
  if(!host) return;
  if(DAILY.loading && !DAILY.data){
    host.innerHTML = '<div class="cc" style="padding:14px">Running the round…</div>';
    return;
  }
  if(DAILY.note && !DAILY.data){
    host.innerHTML = '<div class="odp-note warn" style="padding:14px">'
      + _dyEsc(DAILY.note) + '</div>';
    return;
  }
  if(!DAILY.data){ host.innerHTML = ""; return; }

  const d = DAILY.data;
  const all = d.checks || [];
  const off = all.filter(c => c.status === "off");
  const unk = all.filter(c => c.status === "unknown");
  const ok  = all.filter(c => c.status === "ok");

  // THE HEADLINE NEVER SAYS ALL CLEAR WHILE SOMETHING COULD NOT BE LOOKED AT.
  let h = '<div class="dy-head ' + (off.length ? "bad" : unk.length ? "part" : "good") + '">'
    + '<div class="dy-eyebrow">Daily round</div>'
    + '<div class="dy-headline">' + _dyEsc(d.headline || "") + '</div>'
    + '<div class="dy-sub cc">' + off.length
    + (off.length === 1 ? ' needs' : ' need') + ' attention · ' + ok.length
    + ' checked and fine · ' + unk.length + ' could not be checked'
    + (d.ran_at ? ' · run ' + _dyEsc(d.ran_at) : '') + '</div></div>';

  if(off.length){
    h += '<div class="dy-group"><div class="dy-gh">Needs attention today</div>'
      + off.map(_dyRow).join("") + '</div>';
  }

  if(unk.length){
    h += '<div class="dy-group"><div class="dy-gh">Could not be checked'
      + '<span class="infodot" title="These are shown rather than left off. A '
      + 'round that silently drops what it cannot do looks complete and is not, '
      + 'and somebody still has to go and look at these by hand.">i</span>'
      + '</div>' + unk.map(_dyRow).join("") + '</div>';
  }

  if(ok.length){
    h += '<div class="dy-group">'
      + '<div class="dy-gh" style="cursor:pointer" onclick="dailyToggleOk()">'
      + '<i class="ti ti-chevron-' + (DAILY.showOk ? "down" : "right") + '"></i> '
      + 'Checked and fine (' + ok.length + ')</div>'
      + (DAILY.showOk ? ok.map(_dyRow).join("") : "")
      + '</div>';
  }

  // Anything that threw while gathering. Shown quietly rather than swallowed:
  // a feed that failed is why a check above says it could not run.
  if((d.notes || []).length){
    h += '<details class="foldgroup" style="margin-top:12px"><summary>'
      + (d.notes.length) + ' source(s) could not be read</summary>'
      + '<div style="padding:0 12px 12px">'
      + d.notes.map(n => '<div class="cc" style="font-size:11px;padding:2px 0">'
          + _dyEsc(n) + '</div>').join("")
      + '</div></details>';
  }
  host.innerHTML = h;
}
