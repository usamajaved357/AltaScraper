/* Shared helpers for the three design prototypes. Nothing here talks to a
 * server: every "Amazon" reply is simulated, after a short delay, from
 * shared/data.js. */

const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/* Money, or "not known". A missing figure is never drawn as 0.00. */
function money(v, cur, opts){
  if(v === null || v === undefined || !isFinite(v))
    return '<span class="unknown" title="Not known -- no figure recorded">not known</span>';
  const n = Number(v), s = Math.abs(n).toLocaleString(undefined,
    {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const sign = n < 0 ? "−" : ((opts && opts.plus && n > 0) ? "+" : "");
  return sign + (cur || "") + s;
}
const wait = ms => new Promise(r => setTimeout(r, ms));

/* A confirmation that always NAMES the account, seller and marketplace it acts
 * on (an existing AltaScraper principle, kept in all three directions). */
function confirmBox(o){
  return new Promise(resolve => {
    const w = document.createElement("div");
    w.className = "modal-wrap";
    w.innerHTML = '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="mdh">'
      + '<h3 id="mdh">' + esc(o.title) + '</h3><div class="mb">' + (o.html || esc(o.body || ""))
      + (o.acct ? '<div class="who"><span>Account</span><span><b>' + esc(o.acct.name)
          + '</b></span><span>Seller</span><span>' + esc(o.acct.seller) + '</span>'
          + '<span>Marketplace</span><span>' + esc(o.mkt || o.acct.mkts[0]) + '</span></div>' : "")
      + (o.foot ? '<div class="muted" style="font-size:12.5px">' + o.foot + '</div>' : "")
      + '</div><div class="mf"><button class="btn" data-v="0">' + esc(o.cancel || "Cancel")
      + '</button><button class="btn ' + (o.danger ? "danger" : "primary") + '" data-v="1">'
      + esc(o.ok || "Confirm") + '</button></div></div>';
    const prev = document.activeElement;
    const done = v => { w.remove(); document.removeEventListener("keydown", key, true);
                        if(prev && prev.focus) prev.focus(); resolve(v); };
    const key = e => { if(e.key === "Escape"){ e.preventDefault(); done(false); } };
    w.addEventListener("click", e => {
      if(e.target === w) done(false);
      const b = e.target.closest("[data-v]"); if(b) done(b.dataset.v === "1");
    });
    document.addEventListener("keydown", key, true);
    document.body.appendChild(w);
    w.querySelector('[data-v="1"]').focus();
  });
}

/* ---- design notes ----
 * Any element with data-piece="A2" data-why="Title|Explanation" gets a yellow
 * tag in notes mode; clicking it explains the decision. The list at the
 * bottom-right collects every piece on the page, so a direction can be read as
 * a set of named, swappable parts ("use A's navigation", "C's home"). */
function notesInit(){
  const list = document.createElement("div");
  list.className = "notes-list"; list.id = "notes_list";
  document.body.appendChild(list);
  notesRefresh();
}
function notesToggle(){
  document.body.classList.toggle("notes");
  notesRefresh();
}
function notesRefresh(){
  const seen = {};
  document.querySelectorAll("[data-piece]").forEach(el => {
    let tag = el.querySelector(":scope > .piece-tag");
    const piece = el.dataset.piece;
    if(!tag){
      tag = document.createElement("span");
      tag.className = "piece-tag"; tag.textContent = piece;
      tag.addEventListener("click", ev => { ev.stopPropagation(); whyShow(el, ev); });
      el.prepend(tag);
    }
    const [t] = (el.dataset.why || "").split("|");
    (seen[piece] = seen[piece] || new Set()).add(t);
  });
  const list = document.getElementById("notes_list");
  if(list){
    list.innerHTML = '<h3>Design pieces on this screen (click a yellow tag for the why)</h3><ul style="padding-left:18px;margin:0">'
      + Object.keys(seen).sort().map(k => '<li><b>' + esc(k) + '</b> — ' + [...seen[k]].map(esc).join("; ") + '</li>').join("")
      + '</ul>';
  }
}
function whyShow(el, ev){
  document.querySelectorAll(".why-pop").forEach(p => p.remove());
  const [t, ...rest] = (el.dataset.why || "No note|").split("|");
  const p = document.createElement("div");
  p.className = "why-pop";
  p.innerHTML = '<button class="x" aria-label="Close">×</button><h4>' + esc(el.dataset.piece)
    + ' · ' + esc(t) + '</h4>' + rest.join("|").split("\n").map(x => '<p>' + esc(x) + '</p>').join("");
  p.querySelector(".x").onclick = () => p.remove();
  document.body.appendChild(p);
  const r = p.getBoundingClientRect();
  p.style.left = Math.max(8, Math.min(ev.clientX, innerWidth - r.width - 8)) + "px";
  p.style.top = Math.max(8, Math.min(ev.clientY + 12, innerHeight - r.height - 8)) + "px";
}

/* The banner every prototype carries: it is a prototype, the data is fake,
 * and the switches that simulate slow loads and Amazon refusals. */
function protoBanner(label){
  const b = document.createElement("div");
  b.className = "proto-banner";
  b.innerHTML = '<span>⚠ <b>PROTOTYPE ' + esc(label) + '</b> — fake data, not connected to anything. '
    + 'Not the real AltaScraper.</span><span class="sp"></span>'
    + '<label>Simulate: <select id="sim"><option value="">normal</option>'
    + '<option value="slow">slow loading</option><option value="fail">Amazon refuses the next action</option>'
    + '</select></label>'
    + '<button onclick="notesToggle()" title="Show why each part is designed this way">Design notes</button>'
    + '<a href="index.html">↩ Compare all three</a>';
  document.body.prepend(b);
}
const sim = () => (document.getElementById("sim") || {}).value || "";
