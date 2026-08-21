/* static/js/palette.js -- go to any screen by typing its name. Ctrl+K.
 *
 * WHY THIS EXISTS
 * There are 43 screens in 8 collapsible groups. Every one of them is reachable,
 * and reaching a particular one means remembering which group somebody filed it
 * under: "Category Explorer" is under Manage catalogue, "Keyword Spy" is under
 * Analytics, "Money back" is under Inventory. The bookmark bar solved the four
 * or five you use every day. This is for the other thirty-eight.
 *
 * IT READS THE MENU, IT DOES NOT KEEP A LIST
 * Every entry is taken from the sidebar's own markup at the moment the palette
 * opens -- the section id from data-sec, the words from the link, the sentence
 * from its title, the icon from its <i>, and the group name from the master row
 * above it. A hand-written copy would be a second list of what this app can do,
 * and the first thing to go stale (rule 12). It also means a screen added to the
 * menu is searchable the same day, with no edit here.
 *
 * IT SHOWS ONLY WHAT YOU MAY SEE
 * Through maySeeSection(), the same function the sidebar itself uses, so the
 * palette cannot become a way around the permission table. And a nav item the
 * app has deliberately hidden -- Supplier Import, which only appears for
 * accounts that have one -- stays hidden here too.
 *
 * ACCOUNTS ARE IN IT AS WELL
 * Switching workspace is the other thing done many times a day, and it lives in
 * a menu that has to be found with the mouse. Typing part of a company name and
 * pressing Enter switches to it.
 *
 * THE SHORTCUT
 * Ctrl+K (Cmd+K on a Mac), which is what every editor, Slack, Linear and GitHub
 * use for exactly this. Not "/" -- this app is full of search boxes and a bare
 * slash would fight them. Ignored while typing, for the same reason Ctrl+B is.
 */

let _PAL = {open: false, items: [], hits: [], sel: 0};

function _palEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* Everything you can go to, read off the sidebar as it stands right now. */
function _palCollect(){
  const out = [];
  const seen = {};
  let groups;
  try{ groups = document.querySelectorAll(".navgroup"); }
  catch(e){ return out; }
  Array.prototype.forEach.call(groups || [], function(g){
    const master = g.querySelector(".nmlbl");
    const gname = master ? String(master.textContent || "").trim() : "";
    const kids = g.querySelectorAll(".navitem[data-sec]");
    Array.prototype.forEach.call(kids || [], function(a){
      const sec = a.getAttribute("data-sec");
      if(!sec || seen[sec]) return;
      // Hidden BY THE APP (Supplier Import on an account with no supplier
      // feed), not merely inside a collapsed group -- a collapsed group is
      // still somewhere you can go.
      if(a.style && a.style.display === "none") return;
      if(typeof maySeeSection === "function" && !maySeeSection(sec)) return;
      seen[sec] = 1;
      const icon = a.querySelector("i.ti");
      // The link's own words, minus the icon.
      let label = "";
      Array.prototype.forEach.call(a.childNodes, function(n){
        if(n.nodeType === 3) label += n.textContent;
        else if(n.nodeType === 1 && n.tagName !== "I") label += n.textContent || "";
      });
      out.push({
        kind: "sec", id: sec,
        label: label.replace(/\s+/g, " ").trim() || sec,
        group: gname,
        note: String(a.getAttribute("title") || "").trim(),
        icon: icon ? icon.className : "ti ti-arrow-right",
      });
    });
  });
  // Sections in the menu but outside any group (the top-level rows).
  try{
    Array.prototype.forEach.call(
      document.querySelectorAll(".navitem[data-sec]"), function(a){
        const sec = a.getAttribute("data-sec");
        if(!sec || seen[sec]) return;
        if(a.style && a.style.display === "none") return;
        if(typeof maySeeSection === "function" && !maySeeSection(sec)) return;
        seen[sec] = 1;
        const icon = a.querySelector("i.ti");
        out.push({kind: "sec", id: sec,
                  label: String(a.textContent || sec).replace(/\s+/g, " ").trim(),
                  group: "", note: String(a.getAttribute("title") || "").trim(),
                  icon: icon ? icon.className : "ti ti-arrow-right"});
      });
  }catch(e){}

  // And the workspaces.
  try{
    const cur = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT)
      ? CUR_ACCOUNT.id : "";
    (typeof ACCOUNTS !== "undefined" ? (ACCOUNTS || []) : []).forEach(function(a){
      if(!a || !a.id) return;
      out.push({kind: "acct", id: a.id, label: a.label || a.id,
                group: "Switch account",
                note: (a.id === cur ? "open now"
                       : (a.has_creds ? "" : "draft-only")),
                icon: "ti ti-building-store"});
    });
  }catch(e){}
  return out;
}

/* How well `q` matches `s`. 0 means not at all.
 *
 * Four tiers rather than one substring test, so "cat" puts "Category Explorer"
 * and "Product Catalog" above "Duplicates", and so "ce" still finds "Category
 * Explorer" by its initials. Anything that reorders results has to be
 * predictable or it is worse than alphabetical. */
function _palScore(q, s){
  if(!q) return 1;
  const a = String(s || "").toLowerCase();
  const n = a.indexOf(q);
  if(n === 0) return 1000;                            // starts with it
  if(n > 0){
    // A match at the start of a word beats one buried inside one.
    return /[\s\-(/]/.test(a.charAt(n - 1)) ? 700 - n : 400 - n;
  }
  // Initials: "ce" -> "Category Explorer".
  const initials = a.split(/[\s\-(/]+/).map(function(w){ return w.charAt(0); }).join("");
  if(initials.indexOf(q) === 0) return 600;
  // Letters in order, anywhere -- the last resort, and scored lowest so it
  // never outranks a real match.
  let i = 0;
  for(let k = 0; k < a.length && i < q.length; k++){
    if(a.charAt(k) === q.charAt(i)) i++;
  }
  return i === q.length ? 100 : 0;
}

function _palRank(q){
  const query = String(q || "").trim().toLowerCase();
  const scored = [];
  _PAL.items.forEach(function(it){
    const s = Math.max(_palScore(query, it.label),
                       _palScore(query, it.id) - 50,
                       _palScore(query, it.group) - 200,
                       _palScore(query, it.note) - 300);
    if(s > 0) scored.push({it: it, s: s});
  });
  scored.sort(function(x, y){
    if(y.s !== x.s) return y.s - x.s;
    return x.it.label.localeCompare(y.it.label);
  });
  return scored.slice(0, 40).map(function(x){ return x.it; });
}

function _palDraw(){
  const list = document.getElementById("pal_list");
  if(!list) return;
  if(!_PAL.hits.length){
    list.innerHTML = '<div class="palempty">Nothing matches that. '
      + 'Try part of a screen name, or a company.</div>';
    return;
  }
  list.innerHTML = _PAL.hits.map(function(it, i){
    return '<button class="palrow' + (i === _PAL.sel ? " on" : "") + '" '
      +  'data-i="' + i + '">'
      +  '<i class="' + _palEsc(it.icon) + '"></i>'
      +  '<span class="pallbl">' + _palEsc(it.label) + '</span>'
      // The sentence next, muted and truncated -- it is what tells two
      // similarly named screens apart. The group is last and right-aligned so
      // the eye can run down one column of them.
      +  (it.note ? '<span class="palnote">' + _palEsc(it.note) + '</span>' : '')
      +  (it.group ? '<span class="palgrp">' + _palEsc(it.group) + '</span>' : '')
      +  '</button>';
  }).join("");
  const on = list.querySelector(".palrow.on");
  if(on && on.scrollIntoView) on.scrollIntoView({block: "nearest"});
}

function _palFilter(){
  const box = document.getElementById("pal_q");
  _PAL.hits = _palRank(box ? box.value : "");
  _PAL.sel = 0;
  _palDraw();
}

function _palGo(i){
  const it = _PAL.hits[i === undefined ? _PAL.sel : i];
  palClose();
  if(!it) return;
  if(it.kind === "acct"){
    if(typeof enterAccount === "function") enterAccount(it.id);
    return;
  }
  // navTo is the one way in: it owns the URL, the active highlight and the
  // permission gate. Going around it would give the palette its own opinion
  // about what "being on a screen" means.
  if(typeof navTo === "function") navTo(it.id);
}

function palOpen(){
  if(_PAL.open) return;
  _PAL.items = _palCollect();
  let host = document.getElementById("palette");
  if(!host){
    host = document.createElement("div");
    host.id = "palette";
    host.innerHTML =
        '<div class="palbox" role="dialog" aria-label="Go to">'
      + '<div class="palhead"><i class="ti ti-search"></i>'
      + '<input id="pal_q" autocomplete="off" spellcheck="false" '
      + 'placeholder="Go to a screen, or an account…" aria-label="Go to">'
      + '<span class="palhint">Esc</span></div>'
      + '<div id="pal_list" class="pallist"></div>'
      + '<div class="palfoot"><span>&uarr;&darr; to move</span>'
      + '<span>&crarr; to open</span><span>Ctrl+K anywhere</span></div>'
      + '</div>';
    document.body.appendChild(host);
    host.addEventListener("mousedown", function(ev){
      if(ev.target === host) palClose();          // the backdrop
    });
    host.addEventListener("click", function(ev){
      const b = ev.target.closest ? ev.target.closest(".palrow") : null;
      if(b) _palGo(Number(b.dataset.i));
    });
    const box = host.querySelector("#pal_q");
    box.addEventListener("input", _palFilter);
    box.addEventListener("keydown", function(ev){
      if(ev.key === "ArrowDown"){
        ev.preventDefault();
        _PAL.sel = Math.min(_PAL.sel + 1, _PAL.hits.length - 1); _palDraw();
      }else if(ev.key === "ArrowUp"){
        ev.preventDefault();
        _PAL.sel = Math.max(_PAL.sel - 1, 0); _palDraw();
      }else if(ev.key === "Enter"){
        ev.preventDefault(); _palGo();
      }else if(ev.key === "Escape"){
        ev.preventDefault(); palClose();
      }
    });
  }
  host.classList.add("show");
  _PAL.open = true;
  const box = document.getElementById("pal_q");
  if(box){ box.value = ""; box.focus(); }
  _palFilter();
}

function palClose(){
  const host = document.getElementById("palette");
  if(host) host.classList.remove("show");
  _PAL.open = false;
}

function palToggle(){ _PAL.open ? palClose() : palOpen(); }

/* Ctrl+K / Cmd+K. Ignored while typing, exactly as Ctrl+B is in sidebar.js --
 * otherwise a search box would open the palette instead of taking the letter. */
document.addEventListener("keydown", function(ev){
  if(!(ev.ctrlKey || ev.metaKey) || ev.altKey || ev.shiftKey) return;
  if(String(ev.key).toLowerCase() !== "k") return;
  const t = ev.target;
  const tag = t && t.tagName ? t.tagName.toUpperCase() : "";
  // The palette's own box is the exception: Ctrl+K there closes it again.
  if(t && t.id !== "pal_q"
     && (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"
         || t.isContentEditable)) return;
  ev.preventDefault();
  palToggle();
});
