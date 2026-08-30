/* ============================================================================
   THE LISTING DRAWER'S PRESENTATION HELPERS
   ============================================================================

   Everything in this file BUILDS MARKUP. Nothing in it decides anything about
   a listing, talks to Amazon, or writes to a sheet. The data still comes from
   the same row object, and every save still goes through the same saveEdit() /
   clearField() / moveBullet() the app already had -- this file only changes
   what those controls LOOK like.

   It exists as its own file because CLAUDE.md Rule 7 asks for new work in a
   new file rather than another few hundred lines inside listings.js or
   autofix.js, both of which are already the biggest files in static/js.

   Styling lives in static/css/drawer.css. Class names are all dw2-*.

   ONE THING MOVED HERE RATHER THAN BEING COPIED: bulletMeter(). It used to
   live in autofix.js and draw a single progress bar. It now draws the
   segmented budget bar AND keeps every bullet card's byte count, preview line
   and indexed dot in step -- but it is still ONE function with ONE definition
   (Rule 12), called from exactly the places it was called from before.
   ========================================================================= */

/* ---- the element that actually scrolls --------------------------------
   The drawer used to be one scrolling box. It is now a fixed header, a
   scrolling middle and a fixed footer, so anything that wants to scroll the
   drawer must scroll the middle. Written once, here, because three separate
   places used to do `document.getElementById("drawer").scrollTop = 0`. */
function dwScroller(){
  return document.querySelector("#drawerbody .dw2-body")
      || document.getElementById("drawer");
}

/* ---- small shared bits ------------------------------------------------ */
function _dwId(p){ return p + "_" + Math.random().toString(36).slice(2,8); }

// Where a value came from, as one coloured dot. The full provenance tooltip
// is still available on the existing panels; this is the at-a-glance version
// the design asks for. Anything we can't attribute gets NO dot -- an
// unexplained grey dot would imply we know something we don't.
function dwSrcDot(prov){
  if(!prov) return "";
  const p = String(typeof prov === "string" ? prov : (prov.source||prov.by||"")).toLowerCase();
  if(/amazon|catalog|sp-?api|live/.test(p))
    return '<span class="dw2-srcdot amz" title="From Amazon’s catalogue"></span>';
  if(/ai|claude|gpt|model|generat/.test(p))
    return '<span class="dw2-srcdot ai" title="Written by AI — check it"></span>';
  return "";
}

// Paste as PLAIN TEXT. A contenteditable will happily swallow the font,
// colour and <span> soup from a Word document or a Seller Central page, and
// then textContent hands the visible words to Amazon while the markup sits
// invisibly in the cell. Strip it at the door.
function dwPastePlain(ev){
  ev.preventDefault();
  const t = (ev.clipboardData || window.clipboardData).getData("text/plain");
  document.execCommand("insertText", false, t);
}

// Enter commits a single-line field instead of opening a second line.
function dwEnterBlur(ev){
  if(ev.key === "Enter" && !ev.shiftKey){ ev.preventDefault(); ev.target.blur(); }
}

/* SAVE ONLY WHAT CHANGED.
 *
 * An <input> fires `change` only when the value is different. A
 * contenteditable has no such event -- the only reliable moment is blur, and
 * blur fires every time you click away, changed or not. Wiring saveEdit()
 * straight to blur would fire a write at the sheet each time the pointer
 * passed through a field, which on a 69-attribute listing is a lot of writes
 * that all say what the row already said.
 *
 * So the value the cell was drawn with is kept on the element, and the save
 * runs only when the text actually differs from it. saveEdit() itself is
 * untouched and is still the one and only save path. */
function dwBlurSave(el, sku, target, key){
  const v = (el.textContent == null ? "" : el.textContent);
  if(v === (el.getAttribute("data-orig") || "")) return;
  el.setAttribute("data-orig", v);
  saveEdit(el, sku, target, key);
}

/* THE TITLE EDITOR, WRITTEN ONCE.
 *
 * The drawer puts it in the hero beside the image; the full-screen product page
 * (pdp.js) puts it at the top of its content card. It is the same editor in
 * both, because everything attached to it is load-bearing and none of it is
 * obvious from looking at a box with words in it:
 *
 *   claimMarkField   the <mark> highlights over risky claims
 *   dwBlurSave       saves to the Title COLUMN, only when the text changed
 *   textContent      so the <mark> markup can never reach Amazon
 *   TITLE_OPTS       200 system max, the 75-char hard cap landing 27 Jul 2026
 *
 * A second title box saving to the same cell is how two editors end up
 * disagreeing about what you typed -- which is the exact reason the attribute
 * grid does not draw a Brand box (see renderAttr in autofix.js). Same rule.
 *
 * Returns the pieces rather than one blob so each screen can place the counter
 * and the cap warning where its own layout wants them.
 */
function dwTitleParts(r, cid){
  const tval = String(r.title || "");
  const n = tval.length;
  const over = n > TITLE_OPTS.limit;
  const warn = n > TITLE_OPTS.warnAt && !over;
  return {
    cid: cid,
    editor:
        '<div class="dw2-h3" contenteditable="true" spellcheck="false"'
      + ' data-orig="' + esc(tval) + '"'
      + ' oninput="dwCount(this,\'' + cid + '\',' + TITLE_OPTS.limit + ',0,' + TITLE_OPTS.warnAt + ')"'
      + ' onpaste="dwPastePlain(event)"'
      + ' onblur="dwBlurSave(this,\'' + esc(r.sku) + '\',\'col\',\'Title\')"'
      + '>' + (claimMarkField(r, 'title', r.title) || '') + '</div>',
    count:
        '<span class="dw2-count' + (over ? ' over' : (warn ? ' warn' : '')) + '" id="' + cid + '">'
      + n + ' / ' + TITLE_OPTS.limit + '</span>',
    indexTag:
        '<span class="dw2-tag info" title="' + esc(TITLE_OPTS.indexTip) + '">'
      + esc(TITLE_OPTS.indexNote) + '</span>',
    warnNote: (warn || over)
      ? '<div class="dw2-note" style="color:#EF9F27">⚠ ' + esc(TITLE_OPTS.warnMsg) + '</div>'
      : ""
  };
}

/* ---- counters ---------------------------------------------------------
   The contenteditable twin of ccount(). Same rules, same classes: `over`
   past the hard limit, `warn` past a soft threshold. */
function dwCount(el, cid, limit, bytes, warnAt){
  const c = document.getElementById(cid);
  if(!c) return;
  const v = (el.textContent == null ? "" : el.textContent);
  const n = bytes ? byteLen(v) : v.length;
  c.textContent = n + (limit ? (" / " + limit) : "") + (bytes ? " bytes" : "");
  const over = !!(limit && n > limit);
  c.classList.toggle("over", over);
  c.classList.toggle("warn", !!(warnAt && n > warnAt && !over));
}

/* ---- section / fold wrappers ----------------------------------------- */
function dwSection(title, right, body){
  return '<div class="dw2-sec"><div class="dw2-sechead"><span>' + esc(title) + '</span>'
       + '<span class="dw2-secright">' + (right || "") + '</span></div>'
       + (body || "") + '</div>';
}

/* EVERYTHING THE DESIGN DOESN'T SHOW IS KEPT, AND STARTS CLOSED.
 *
 * The design file has eight sections. The real drawer has closer to twenty --
 * A+ content, the Amazon mirror, restricted products, compliance documents,
 * the run log, the image generator, the Miles template panel, raw JSON. None
 * of it was invented for decoration and none of it is removed here; it opens
 * with one click instead of standing between you and the copy.
 *
 * `right` is the point of the closed state: a fold that says nothing about
 * what is inside it is just a thing to click. Pass the count, the verdict,
 * the tag -- whatever makes it possible to decide NOT to open it. */
function dwFold(title, right, body, open){
  if(!body) return "";
  return '<details class="dw2-fold"' + (open ? " open" : "") + '>'
       + '<summary><i class="ti ti-chevron-right chev"></i>'
       + '<span class="grow">' + esc(title) + '</span>'
       + (right || "") + '</summary>'
       + '<div class="dw2-foldbody">' + body + '</div></details>';
}

/* ---- editable text block (highlights / search terms / description) ---- */
/* o = {label, sku, target, key, value, limit, bytes, warnAt, tag, note,
        placeholder, sm} */
function dwEditBlock(o){
  const cur = (o.value == null ? "" : String(o.value));
  const cid = _dwId("dwc");
  const n   = o.bytes ? byteLen(cur) : cur.length;
  const over = !!(o.limit && n > o.limit);
  const warn = !!(o.warnAt && n > o.warnAt && !over);
  const counter = '<span class="dw2-count' + (over ? " over" : (warn ? " warn" : "")) + '" id="' + cid + '">'
                + n + (o.limit ? (" / " + o.limit) : "") + (o.bytes ? " bytes" : "") + '</span>';
  const right = counter + (o.tag || "");
  const tgt = o.target || "col";
  // The warning only appears once you are near or past the limit -- the same
  // rule contentRow() used. Backend search terms are the one that matters:
  // one byte over 249 silently de-indexes the WHOLE field.
  const warnmsg = (o.warnMsg && (warn || over))
    ? '<div class="dw2-note" style="color:#EF9F27">⚠ ' + esc(o.warnMsg) + "</div>" : "";
  const block = warnmsg +
      '<div class="dw2-edit' + (o.sm ? " sm" : "") + ' empty" contenteditable="true" spellcheck="false"'
    + ' data-ph="' + esc(o.placeholder || "empty") + '"'
    + ' data-orig="' + esc(cur) + '"'
    + ' oninput="dwCount(this,\'' + cid + '\',' + (o.limit || 0) + ',' + (o.bytes ? 1 : 0) + ',' + (o.warnAt || 0) + ')"'
    + ' onpaste="dwPastePlain(event)"'
    + ' onblur="dwBlurSave(this,\'' + esc(o.sku) + '\',\'' + tgt + '\',\'' + esc(o.key) + '\')">'
    + esc(cur) + '</div>'
    + (o.note ? '<div class="dw2-note">' + o.note + '</div>' : "");
  return dwSection(o.label, right, block);
}

/* ---- BULLET CARDS -----------------------------------------------------
   Collapsed, a bullet is its number, its first line, its byte count and
   whether Amazon indexes it. Expanded, it is the textarea it always was --
   same data-bkt hooks, same ccount, same saveEdit on change, so nothing
   about how a bullet is stored has changed.

   There is no drag handle. The design file draws one, but nothing behind it
   drags; move up / move down are the reorder that actually works, and they
   are the app's existing moveBullet(). A grip that does not grip is worse
   than no grip. */
function dwBulletCards(sku, bullets){
  const bl = (bullets || []);
  const total = bl.length;
  const cards = bl.map(function(b, i){
    const val = (b == null ? "" : String(b));
    const cid = _dwId("bcc");
    const n   = i + 1;
    return '<div class="dw2-bul" data-bi="' + i + '">'
      + '<div class="dw2-brow" onclick="dwToggleBullet(this.parentNode)">'
      +   '<span class="dw2-bnum">' + n + '</span>'
      +   '<span class="dw2-bprev">' + esc(val || "(empty)") + '</span>'
      +   '<span class="dw2-bchars">0</span>'
      +   '<span class="dw2-bdot ix"></span>'
      + '</div>'
      + '<div class="dw2-bedit" onclick="event.stopPropagation()">'
      +   '<textarea data-bkt="bullet' + n + '" data-bytes="0" data-warn="0" data-lim="500"'
      +   ' oninput="ccount(this,\'' + cid + '\',500);bulletMeter()"'
      +   ' onchange="saveEdit(this,\'' + esc(sku) + '\',\'col\',\'Bullet ' + n + '\')">' + esc(val) + '</textarea>'
      +   '<div class="dw2-bfoot"><div class="dw2-bfl">'
      +     '<button title="Move up"' + (i > 0 ? ' onclick="moveBullet(\'' + esc(sku) + '\',' + i + ',-1)"' : " disabled") + '><i class="ti ti-arrow-up"></i></button>'
      +     '<button title="Move down"' + (i < total - 1 ? ' onclick="moveBullet(\'' + esc(sku) + '\',' + i + ',1)"' : " disabled") + '><i class="ti ti-arrow-down"></i></button>'
      +     '<button class="del" title="Delete this bullet" onclick="removeBullet(\'' + esc(sku) + '\',' + i + ')"><i class="ti ti-x"></i></button>'
      +     '<span class="dw2-count" id="' + cid + '"></span>'
      +   '</div><span class="dw2-bstat"></span></div>'
      + '</div></div>';
  }).join("");
  const add = (total < MAX_BULLETS)
    ? '<button class="dw2-addbul" onclick="addBullet(\'' + esc(sku) + '\')">+ Add bullet (' + total + '/' + MAX_BULLETS + ')</button>'
    : "";
  return '<div class="dw2-bb" id="bulletIdxMeter"></div>' + cards + add;
}

// One card open at a time -- five open textareas in a 520px column is the
// wall of text the cards exist to replace.
function dwToggleBullet(el){
  const was = el.classList.contains("expanded");
  const box = el.closest(".dw2-sec") || document;
  box.querySelectorAll(".dw2-bul").forEach(function(b){ b.classList.remove("expanded"); });
  if(!was){
    el.classList.add("expanded");
    const ta = el.querySelector("textarea");
    if(ta) setTimeout(function(){ ta.focus(); }, 0);
  }
}

/* THE BULLET BYTE BUDGET, AND EVERYTHING THAT DEPENDS ON IT.
 *
 * Amazon indexes only the first ~1,000 BYTES across ALL FIVE bullets
 * COMBINED -- not 1,000 per bullet. Five 440-byte bullets is 2,200 bytes of
 * copy of which rather less than half is searchable, and nothing on the old
 * screen said which half.
 *
 * One segment per bullet, sized by its share of the total, and a red line
 * where the budget runs out. A bullet whose last byte falls past that line is
 * marked not-indexed -- it is still shown to shoppers, it just cannot be
 * found by the words in it.
 *
 * This is also the only place the per-card count, preview line, dot and
 * status text are written, so they cannot drift away from the bar (Rule 12).
 * It is called from every keystroke in a bullet, and after any render.
 */
const DW_IX_COLORS  = ["#1D9E75","#0F6E56","#0B5544","#094437","#07362C"];
const DW_NIX_COLORS = ["#993C1D","#791F1F","#501313","#3E0F0F","#2C0B0B"];
function bulletMeter(){
  const host = document.getElementById("bulletIdxMeter");
  const cap  = 1000;
  const segs = [];
  let run = 0;
  for(let i = 1; i <= MAX_BULLETS; i++){
    const ta = document.querySelector('textarea[data-bkt="bullet' + i + '"]');
    if(!ta) continue;
    const bytes = byteLen(ta.value);
    const start = run; run += bytes;
    segs.push({i: i, el: ta, bytes: bytes, start: start, end: run,
               indexed: run <= cap, text: ta.value});
  }
  const total = run;

  // Keep every card in step with the bar.
  let ixN = 0, nixN = 0;
  segs.forEach(function(s){
    s.color = s.indexed ? DW_IX_COLORS[ixN++ % DW_IX_COLORS.length]
                        : DW_NIX_COLORS[nixN++ % DW_NIX_COLORS.length];
    const card = s.el.closest(".dw2-bul");
    if(!card) return;
    const prev = card.querySelector(".dw2-bprev");
    const chars = card.querySelector(".dw2-bchars");
    const dot = card.querySelector(".dw2-bdot");
    const stat = card.querySelector(".dw2-bstat");
    if(prev) prev.textContent = s.text.replace(/\s+/g, " ").trim() || "(empty)";
    if(chars) chars.textContent = s.bytes;
    if(dot) dot.className = "dw2-bdot " + (s.indexed ? "ix" : "nix");
    if(stat){
      stat.className = "dw2-bstat" + (s.indexed ? "" : " nix");
      stat.textContent = (s.indexed ? "Indexed" : "Not indexed")
                       + " · " + s.bytes + " / 500";
    }
  });

  // The section header's own verdict.
  const tag = document.getElementById("bulletBudgetTag");
  if(tag){
    const bad = total > cap;
    tag.className = "dw2-tag " + (bad ? "danger" : "ok");
    tag.innerHTML = '<i class="ti ti-' + (bad ? "alert-triangle" : "check") + '"></i> '
                  + total + " / " + cap + " bytes indexed";
  }

  if(!host) return;
  if(!segs.length){ host.innerHTML = ""; return; }
  if(!total){
    host.innerHTML = '<div class="dw2-note">No bullet copy yet — Amazon indexes the '
                   + 'first 1,000 bytes across all five bullets combined.</div>';
    return;
  }
  const bar = segs.map(function(s){
    return '<div class="dw2-bb-seg" style="width:' + (s.bytes / total * 100).toFixed(2) + '%;'
         + 'background:' + s.color + '" title="Bullet ' + s.i + ': ' + s.bytes + ' bytes"></div>';
  }).join("");
  const limit = (total > cap)
    ? '<div class="dw2-bb-limit" style="left:' + (cap / total * 100).toFixed(2)
      + '%" title="Amazon stops indexing here — 1,000 bytes"></div>'
    : "";
  const legend = segs.map(function(s){
    return '<div class="dw2-bl"><div class="dw2-bl-dot" style="background:' + s.color + '"></div>'
         + "B" + s.i + " · " + s.bytes + "b"
         + (s.indexed ? "" : ' <span class="x" title="past the 1,000-byte index cap">✕</span>')
         + "</div>";
  }).join("");
  host.innerHTML = '<div class="dw2-bb-wrap"><div class="dw2-bb-bar">' + bar + "</div>" + limit + "</div>"
                 + '<div class="dw2-bb-legend">' + legend + "</div>"
                 + (total > cap
                     ? '<div class="dw2-note">Everything right of the red line is shown to shoppers '
                       + "but is NOT searchable. Move the words you want found into the earlier bullets.</div>"
                     : "");
}

/* ---- FIELD ROWS (identity and offer) ---------------------------------- */
/* o = {label, hint, prov, cls} */
function dwFieldRow(label, ctrl, o){
  o = o || {};
  return '<div class="dw2-fr"><span class="dw2-fl">' + esc(_cleanLabel(label))
       + dwSrcDot(o.prov)
       + (o.req ? '<span class="dw2-req" title="Required by Amazon">*</span>' : "")
       + '</span><span class="dw2-frv">' + ctrl + "</span></div>"
       + (o.hint ? '<div class="dw2-note" style="color:#EF9F27">⚠ ' + esc(o.hint) + "</div>" : "");
}
function dwRo(v, cls){
  const s = (v == null ? "" : String(v)).trim();
  return '<span class="' + ["dw2-fv", cls, (s ? "" : "dim")].filter(Boolean).join(" ") + '">'
       + esc(s || "—") + "</span>";
}

/* ---- ATTRIBUTE GRID ---------------------------------------------------
   Two columns of cells instead of a two-hundred-row table. Everything the
   table row carried is still on the cell: the required star, the softer
   "schema-listed" marker, Amazon's own hint, where the value came from, and
   the delete control (disabled, with the reason, when Amazon requires the
   field).

   `tag` and `below` arrive as READY-MADE HTML, for the same reason dwNestCell
   takes reqMark that way: they are drawer_attributes.js's live-vs-app markers,
   tooltips and all, and rebuilding them here from a flag would be a second,
   poorer copy of sentences that were written once (Rule 12). Both are empty
   strings when that file has not loaded, so the cell is exactly what it was.

   o = {label, ctrl, prov, req, softReq, hint, full, flagged, del, tag, below} */
function dwCell(o){
  o = o || {};
  const del = !o.del ? ""
    : (o.del.locked
        ? '<button class="dw2-celldel" disabled title="Amazon requires this field — deleting it would fail on Preview/Submit">✕</button>'
        : '<button class="dw2-celldel" title="Delete this field from the listing" onclick="clearField(\''
          + esc(o.del.sku) + "','" + o.del.target + "','" + esc(o.del.key) + '\')">✕</button>');
  return '<div class="dw2-cell' + (o.full ? " full" : "") + (o.flagged ? " flagged" : "") + '">'
    + '<div class="dw2-cl">' + esc(_cleanLabel(o.label))
    +   (o.req ? '<span class="dw2-req" title="Required by Amazon">★</span>' : "")
    +   (o.softReq ? '<span class="dw2-reqsoft" title="The schema lists this as required, but Amazon’s last Preview accepted the listing WITHOUT it. Fill it only if a later Preview flags it.">☆</span>' : "")
    +   dwSrcDot(o.prov)
    +   (o.hint ? '<span class="dw2-hint" title="' + esc(o.hint) + '">⚠</span>' : "")
    +   (o.tag || "")
    +   del
    + "</div>"
    + '<div class="dw2-cv">' + (o.ctrl || "") + "</div>"
    + (o.below || "") + "</div>";
}

// A nested Amazon field (battery, hazmat, item_dimensions) takes the full
// width and puts its sub-fields in their own grid, so you can still see that
// they belong together -- and so the "filling this makes its sub-fields
// required" warning has somewhere to sit.
//
// `reqMark` and `note` arrive as READY-MADE HTML from the caller, not as flags.
// They are the app's existing .reqstar / .reqsoft / .nesthint spans, tooltips
// and all -- the ones that explain the difference between "Amazon flagged
// this" and "the schema lists it but Amazon's last Preview didn't ask for it",
// and the warning that filling an optional parent makes all its sub-fields
// required. Those sentences were argued over; rebuilding them here from a
// boolean would be a second, poorer copy of them (Rule 12).
function dwNestCell(o){
  return '<div class="dw2-cell full">'
    + '<div class="dw2-nesthead">' + esc(_cleanLabel(o.label))
    +   (o.reqMark || "")
    +   (o.hint ? '<span class="dw2-hint">⚠ ' + esc(o.hint) + "</span>" : "")
    +   (o.note || "")
    + "</div>"
    + '<div class="dw2-subgrid">' + (o.cells || "") + "</div></div>";
}
function dwGrid(cells){
  return cells ? '<div class="dw2-grid">' + cells + "</div>" : "";
}
