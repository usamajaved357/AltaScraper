// static/js/listings_rows.js -- table rows, row checkbox and the Review + ... actions. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* WHAT YOU CAN DO TO A ROW -- built once, used by BOTH views.
 *
 * The grid and the table each drew their own set of buttons, and they had
 * drifted badly: the table had no checkbox at all, so nothing could be SELECTED
 * in it -- and every batch action on the screen works off that selection. Tick
 * three products in the grid, switch to the list, and there was nowhere for
 * the selection to live. Approve, Auto-fix and the More menu were missing too.
 * Reported as "the grid view listings and list view listings donot talk to each
 * other", which is exactly what it looked like.
 *
 * Neither view now owns the answer. Both call these, so a button added here
 * appears in both and the two cannot come apart again (CLAUDE.md Rule 12).
 *
 * `cls` is the only difference: the grid's round icon buttons and the table's
 * smaller ones are the same actions wearing the styling of the view they sit in.
 */
function rowSelectBox(r, cls){
  // `cls` is the only difference between the views, exactly as in rowActions:
  // the card's checkbox sits on the image and the table's in its own column,
  // so they are styled apart -- but WHAT the box does is one behaviour and is
  // written once. It was written twice, and the two spelled the SKU into the
  // handler separately, which is how one of them came to be looked up by a
  // class that does not exist.
  const on = SELECTED.has(String(r.sku)) ? "checked" : "";
  return `<input type="checkbox" class="${cls || "rowsel"}" ${on}
      title="Select for batch actions"
      onclick="event.stopPropagation()"
      onchange="toggleSelect(${jsArg(r.sku)}, this.checked)">`;
}

/* THE ONE ACTION ROW, for every card in the app.
 *
 *     "i see two types of cards style dont make them different make them same
 *      and also remove the unnecessary buttons from the cards"
 *
 * There were two: this icon row on the drafts cards, and a separate set of
 * text-labelled buttons written out by hand inside liveTile() in
 * miles_template.js. Same screen, same grid, two designs -- visible side by side
 * in his screenshot 84, and inevitable once the same list is drawn by two
 * renderers that each build their own buttons.
 *
 * liveTile calls this now, so there is one definition (Rule 12) and adding a
 * button to the app adds it to both kinds of card or to neither.
 *
 * `opts.live` forces the live branch on: a tile from Amazon's catalogue IS live
 * by definition, but it has no app row for isAmazonLive() to read.
 */
function rowActions(r, cls, opts){
  cls = cls || "ib";
  opts = opts || {};
  // (No pre-escaped `sku` here any more: every handler below takes the RAW
  //  r.sku through jsArg, and an escaped copy passed to jsArg is escaped
  //  twice -- UI review, Milestone 6.)
  const live = opts.live === undefined ? isAmazonLive(r) : !!opts.live;
  // REVIEW + "···", AND NOTHING ELSE (design package, owner-approved: "the same
  // actions: Review (primary, opens the product page) + ···. Before, there were
  // 5 icon buttons"). Every action those icons carried -- Approve, Image Studio,
  // Images, and on a live listing Optimize, Compare and Add variant -- is in the
  // "···" menu now (tileMenu), so nothing is lost; it is one click further and
  // it has a name instead of an icon to guess.
  //
  // Review is drawn here for a DRAFT CARD only. The table row writes its own
  // Review beside this, and a catalogue-only live listing has no draft to
  // review -- the owner's reason, kept on liveTableRow: "Review opens the draft
  // this app holds, and this listing has no draft". Clicking such a row or card
  // still opens it.
  const review = (cls === "ib" && !opts.live)
    ? `<button class="${cls} review" title="Open this listing's product page"
            onclick="event.stopPropagation();openListing(${jsArg(r.sku)})">Review</button>`
    : "";
  return review + `
    <button class="${cls} more" title="More actions" aria-label="More actions for ${esc(String(r.sku || ""))}"
            onclick="event.stopPropagation();tileMenu(event,${jsArg(r.sku)},${r.row||0},${live ? "true" : "false"},${jsArg(rowAsin(r).own||"")})"><i class="ti ti-dots" aria-hidden="true"></i></button>`;
}
/* PULL LIVE IMAGES: REMOVED.
 *
 *     "live pulling live images from amazon, i believe the app automatically
 *      fetches fresh data now. so we dont need that button also check other
 *      buttons from this logic and delete the un necessary ones"
 *
 * He is right. The button called pullLiveRow(), which fetches a listing's real
 * Amazon images into that one row. Sync already does exactly that for the whole
 * account, and the live tiles show Amazon's own images regardless of whether the
 * app holds a copy -- so it was a per-row repeat of a job that is already done
 * in bulk, sitting on the busiest row of buttons on the screen.
 *
 * pullLiveRow() itself is deliberately KEPT. It is still called from the drawer
 * and from the batch actions, where pulling images for one chosen listing is the
 * point rather than a duplicate of Sync.
 *
 * EVERY OTHER BUTTON WAS PUT TO THE SAME TEST -- "does something else already do
 * this?" -- and every one survived it:
 *
 *   Approve       sets the status. Nothing else does.
 *   Image Studio  GENERATES images. Different job from the library below.
 *   Library       shows what exists, uploads, and pushes one live.
 *   Edit          opens the full editor.
 *   Auto-fix      the suggest/apply/preview loop.
 *   Optimize      rewrites the live copy. Live only.
 *   Price         changes the live price. Live only.
 *   Open on Amazon a link, not an action.
 *   More          holds the rest.
 */

// One block of listings, drawn the way the user has chosen. Every place that
// used to say rows.map(card).join("") calls this instead, so the two views can
// never drift apart into "the table forgot about claimed rows".
function listBlock(rows, fn){
  fn = fn || card;
  if(!rows || !rows.length) return "";
  const view = listViewNow();
  // The detailed view brings its own header and its own row builder, so it
  // does not go through the table's <th>/<td> path at all.
  if(view === "detailed") return detailedBlock(rows);
  if(view !== "table") return rows.map(fn).join("");
  const rowFn = (fn === (typeof liveTile === "function" ? liveTile : null))
                ? liveTableRow : tableRow;
  // COGS gets its own column, and it is EDITABLE. What a thing cost is the one
  // number every profit figure on every other screen is built from, and it was
  // only visible by opening a listing. Click the cell, type, done.
  const head = `<div class="card ltwrap"><table class="lt"><thead><tr>
      <th class="selcol" title="Select every row shown">
        <input type="checkbox" class="rowsel"
               ${rows.length && rows.every(x => SELECTED.has(String(x.sku))) ? "checked" : ""}
               aria-label="Select all visible listings" onchange="selectAllVisible(this.checked)"></th>
      <th style="width:52px">Image</th><th>ASIN</th><th>Title</th>
      <th>Price</th><th title="What the stock cost you — a figure you set, by typing it here or uploading a cost sheet. Nothing is read out of the SKU name any more; a plain number with no mark is an old cost from before that changed. Click to set or replace one.">COGS</th>
      <th>Handling</th><th>Status</th><th>Compliance</th>
      <th style="width:150px">Actions</th></tr></thead><tbody>`;
  const body = rows.map(rowFn).join("");
  // THE HEADER AND THE ROWS MUST HAVE THE SAME NUMBER OF COLUMNS.
  //
  // liveTableRow shipped with nine cells against this ten-column header, and the
  // whole live view was shifted one place left -- pictures under the checkbox,
  // actions under "Compliance". Nothing caught it, because HTML does not
  // complain: a short row just draws short.
  //
  // So it is checked, once per draw, and said out loud in the console rather than
  // left to be noticed by eye. Cheap: one count of one string.
  if(body){
    const want = (head.match(/<th\b/g) || []).length;
    const first = body.slice(0, body.indexOf("</tr>") + 5);
    const got = (first.match(/<td\b/g) || []).length;
    if(got && got !== want){
      console.error("listings table: header has " + want + " columns and a row "
        + "has " + got + " — the columns will not line up. Fix the row builder ("
        + (rowFn === liveTableRow ? "liveTableRow" : "tableRow") + ").");
    }
  }
  return head + body + `</tbody></table></div>`;
}

/* SEVERAL GROUPS OF ROWS, ONE BOX.
 *
 *     "why do i have two separate boxes/borders containing the listings?"
 *
 * The live view is built as listBlock(liveRows) + listBlock(liveCatalog), and
 * every listBlock opens its own <div class="card ltwrap"> with its own header
 * row. So the screen drew two bordered cards, one after the other, with a
 * repeated Image/ASIN/Title/... header in the middle of the list and nothing to
 * say why. Measured on jack_uk: 40 rows in the first, 7 in the second.
 *
 * The intent was already ONE group -- the comment in miles_template.js says so
 * in capitals, and the captions between them were removed when the owner said
 * "i dont like that separation". Only the captions went; the two cards stayed.
 *
 * The difference between the groups is real and is marked ON THE ROW that has
 * it, which is what that same note asked for: a listing this app holds no draft
 * of is a fact about that listing, not a category of listing.
 */
function listBlocks(groups){
  const use = (groups || []).filter(g => g && g.rows && g.rows.length);
  if(!use.length) return "";
  const view = listViewNow();
  // ONE header over every group, for the same reason the table has one: two
  // bordered cards with a repeated header in the middle is what the owner
  // objected to. Every row goes into a single detailed block.
  if(view === "detailed"){
    return detailedBlock(use.reduce((a, g) => a.concat(g.rows), []));
  }
  // Tiles have no header and no table, so there is nothing to merge -- each
  // group is already just a run of cards.
  if(view !== "table"){
    return use.map(g => listBlock(g.rows, g.fn)).join("");
  }
  // One header, built from every row that will be under it, so "select all"
  // means all of them and not just the first group's.
  const all = use.reduce((a, g) => a.concat(g.rows), []);
  const head = listBlock(all, use[0].fn);
  const open = head.slice(0, head.indexOf("<tbody>") + 7);
  const body = use.map(g => (g.rows || []).map(
                 g.fn === liveTile ? liveTableRow : (g.fn || tableRow)).join("")).join("");
  return open + body + `</tbody></table></div>`;
}

// The compliance cell: one icon and two words, from the SAME data the drawer's
// banner reads, so a row cannot say "clear" while its detail says "prohibited".
function _compCell(r){
  const rr = r.restricted, v = r.viability;
  if(!rr && !v) return `<span class="comp cc">—</span>`;
  if(rr && rr.matched && (rr.matches||[]).some(m=>m.tier==="PROHIBITED")){
    return `<span class="comp" style="color:var(--red)"><i class="ti ti-shield-x"></i> prohibited</span>`;
  }
  if(rr && rr.matched){
    return `<span class="comp" style="color:var(--warn)"><i class="ti ti-shield-half"></i> gated</span>`;
  }
  if(v && v.matched){
    const n = (v.risks||[]).length;
    return `<span class="comp" style="color:var(--warn)"><i class="ti ti-file-text"></i> needs docs${n?` (${n})`:""}</span>`;
  }
  return `<span class="comp" style="color:var(--ok)"><i class="ti ti-shield-check"></i> clear</span>`;
}

function _statusPill(s){
  // Same split as the detailed view's badge: the WORD comes from liststatus.js
  // (SUBMITTED -> WAITING, API_ERROR -> ISSUE) and the COLOUR still comes from
  // the stored status, so the two views cannot show one listing as two different
  // things (Rule 12) and nothing changes about which rows look urgent.
  const word = (typeof lsBadgeWord === "function") ? lsBadgeWord(s) : s;
  return `<span class="badge ${badgeClass(s)}">${esc(word||"—")}</span>`;
}

// THE STATUS AS IT IS TODAY, not as it was stored.
//
// Same reason as _statusDot: a listing Amazon confirms is live is LIVE, whatever
// word the row was left with by an attempt that failed before it went up. The
// counts along the top already do this; the pill did not, so a live listing sat
// under a red API_ERROR badge and its own account said 47 were live.
function _shownStatus(r){
  try{
    const sets = _liveCatSetsForCurrentView();
    if(isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown)) return "LIVE";
  }catch(e){}
  return r.status || "";
}

function tableRow(r){
  // Same image source the tile uses, so the two views cannot disagree about
  // which picture belongs to a listing.
  const urls = (typeof _cardImages === "function") ? (_cardImages(r) || []) : [];
  const thumb = urls.length
    ? `<div class="thumb"><img src="${esc(thumbUrl(urls[0],44))}" loading="lazy" decoding="async" onerror="this.parentNode.innerHTML='<i class=&quot;ti ti-photo&quot;></i>'"></div>`
    : `<div class="thumb"><i class="ti ti-photo"></i></div>`;
  // Same three cells the tile uses, for the same reason as the image above.
  const price = _priceCell(r, "");
  const hand  = _handCell(r);
  // THE ASIN IS THE LINK. It always carried an external-link icon and was a
  // plain <span> -- an icon promising something the element could not do:
  //
  //     "no asin in the screenshot opens a product"
  //     "we should be able to open the listing by clicking on the green asin"
  //
  // stopPropagation because the row itself opens the editor; without it a
  // click would do both.
  // THE LINK MUST BE **OUR** ASIN.
  //
  //     "we should be able to open the listing by clicking on the green asin"
  //
  // -- meaning HIS listing. This linked r.asin, which on an app row is the
  // COMPETITOR ASIN out of the SKU, so the green ASIN opened the competitor's
  // product page while looking exactly like our own. Measured: 56 of 56 rows
  // with an ASIN carried the competitor's, and where we are live our real ASIN
  // is a different code entirely (B07NT77GT8 vs B0H66Q1XFK).
  //
  // A draft that is not live has no ASIN of its own, and saying so is the
  // honest answer. The competitor reference is still shown, because it is
  // genuinely useful -- it is the product this was built from -- but it is
  // labelled as such and is NOT dressed up as our listing.
  const _a = rowAsin(r);
  const asin = _a.own
    ? `<a class="asin" href="${esc(_dpUrl(_a.own))}" target="_blank" rel="noopener"
          onclick="event.stopPropagation()" style="text-decoration:none"
          title="Open your listing ${esc(_a.own)} on Amazon">${esc(_a.own)} <i class="ti ti-external-link" style="font-size:10px"></i></a>`
    : (_a.source
        ? `<span class="cc" title="This listing is not live on Amazon yet, so it has no ASIN of its own. ${esc(_a.source)} is the competitor product it was researched from — not your listing.">not live yet <span class="srcasin">· from ${esc(_a.source)}</span></span>`
        : `<span class="cc">no ASIN</span>`);
  return `<tr onclick="openListing(${jsArg(r.sku)})" title="${esc(r.title||'')}"
              data-sku="${esc(r.sku)}"
              class="${SELECTED.has(String(r.sku)) ? 'rowon' : ''}">
    <td class="selcol">${rowSelectBox(r)}</td>
    <td class="pii-img">${thumb}</td>
    <td>${asin}<br><span class="sku pii">${esc(r.sku||'')}</span></td>
    <td><span class="ttl pii">${esc(r.title||'(no title)')}</span>
        <span class="brand pii">${_brandCell(r)}</span></td>
    <td class="price">${price}</td>
    ${cogsCell(r)}
    <td>${hand}</td>
    <td>${_statusPill(_shownStatus(r))}${needsCopy(r)
        ? `<div class="cc" style="font-size:9.5px;margin-top:3px;color:var(--warn)" `
          + `title="No bullets, no description, no product type yet. Select it and `
          + `press Regenerate copy, or open it and press Write it now.">no copy yet</div>`
        : ''}</td>
    <td>${_compCell(r)}</td>
    <td><div class="acts">
      <button class="btn primary" onclick="event.stopPropagation();openListing(${jsArg(r.sku)})">Review</button>
      ${rowActions(r, "dotb")}
    </div></td></tr>`;
}

// Amazon-catalog rows: listings Amazon holds that this app has no draft of.
// They open the live editor rather than the drawer -- see _open below.
function liveTableRow(it){
  const img = it.image || it.img || "";
  const thumb = img
    ? `<div class="thumb"><img src="${esc(thumbUrl(img,44))}" loading="lazy" decoding="async" onerror="this.parentNode.innerHTML='<i class=&quot;ti ti-photo&quot;></i>'"></div>`
    : `<div class="thumb"><i class="ti ti-photo"></i></div>`;
  // Same cells the draft row and both tiles use. A catalogue row is live by
  // definition, hence the explicit true -- there is no app row to read it from.
  const _r = {sku: it.sku, asin: it.asin, title: it.title, brand: it.brand,
              handling_time: it.handling, handling_days: it.handling_days,
              price: String(it.price || "").replace(/^[A-Z]{3}\s?/, ""), row: 0};
  const price = _priceCell(_r, "", true);
  const c = it.compliance;
  const comp = (c && (c.risks||[]).length)
    ? `<span class="comp" style="color:${(c.risks||[]).some(x=>x.risk==="HIGH")?"var(--red)":"var(--warn)"}"><i class="ti ti-file-text"></i> ${c.doc_count} docs</span>`
    : `<span class="comp cc">—</span>`;
  // TEN CELLS, BECAUSE THE HEADER HAS TEN COLUMNS.
  //
  // This row had nine. It was missing the select cell that every header row
  // starts with, so in the LIVE view every column was shifted one place to the
  // left: the picture sat under the checkbox, the ASIN under "Image", the title
  // under "ASIN", and the actions under "Compliance". Reported as "in the
  // listings section i see that the header and the details under it do not
  // match".
  //
  // THE SELECT CELL WAS DELIBERATELY LEFT EMPTY, AND THAT IS NOW THE BUG.
  //
  //     "i am still not able to see the option to select all products on the
  //      page"  (reported again after the tile view was fixed)
  //
  // The reason written here was true when it was written: the bulk bar held
  // Approve and Hold, which are about DRAFTS, and offering them on a listing
  // Amazon has already published would be offering to un-approve it.
  //
  // The bar has since grown three actions that are the OPPOSITE -- set handling
  // time, set stock, change price by a percentage. Every one of those is a live
  // Amazon change, and a listing with no draft here is the purest case of it.
  // So the cell that was empty for a good reason went on being empty for none,
  // and on this account that is 46 of the 48 rows in the Live view: "Select all"
  // ticked two and looked broken, because two was genuinely all the screen
  // offered.
  //
  // A tick is offered here now, as the TILE already does. What must not follow
  // is a draft action running against a listing that has no draft -- so Approve,
  // Hold, Delete and Auto-fix split the selection first (splitByDraft) and say
  // which ones they left alone, rather than reporting them as failures.
  //
  // THE ROW STILL OPENS THE LISTING, like every other row on this screen.
  //     "we can directly edit the listing by clicking on the product card"
  // openLiveListing sends it to the full-screen product page when this app has
  // a row for the SKU, and to optimizeLive when it does not -- see that
  // function for why both are needed.
  const _open = `openLiveListing(${jsArg(it.asin||'')},${jsArg(it.sku||'')})`;
  return `<tr style="cursor:pointer" title="${esc(it.title||'')}"
              data-sku="${esc(it.sku||'')}"
              class="${SELECTED.has(String(it.sku||'')) ? 'rowon' : ''}"
              onclick="${_open}">
    <td class="selcol">${rowSelectBox({sku: it.sku||''})}</td>
    <td class="pii-img">${thumb}</td>
    <td>${it.asin
        ? `<a class="asin" href="${esc(_dpUrl(it.asin))}" target="_blank" rel="noopener"
              onclick="event.stopPropagation()" style="text-decoration:none"
              title="Open ${esc(it.asin)} on Amazon">${esc(it.asin)} <i class="ti ti-external-link" style="font-size:10px"></i></a>`
        : `<span class="cc">no ASIN</span>`}<br><span class="sku pii">${esc(it.sku||'')}</span></td>
    <td><span class="ttl pii">${esc(it.title||'(no title in report)')}</span>
        <span class="brand pii">${_brandCell(it)}</span></td>
    <td class="price">${price}</td>
    ${cogsCell(it)}
    <td>${_handCell(_r, true)}</td>
    <!-- WHY THIS ROW HAS FEWER BUTTONS THAN THE ONE ABOVE IT.
         "two different types on buttons, some have review option some dont".
         Review opens the draft this app holds, and this listing has no draft --
         it is on Amazon and was never generated here. Same for the compliance
         column: there is no stored verdict to show, so it reads "—", which
         looks like a blank rather than an answer.
         The row says so now. It is one word next to LIVE, and it is the fact
         that explains every difference a reader can see. -->
    <td><span class="badge b-LIVE">LIVE</span>
        <span class="badge b-NODRAFT" title="On Amazon, but this app holds no draft of it — so there is nothing to Review and no compliance check of our own. Press Sync to pull the full listing in; price, images and Optimize work either way.">no draft here</span></td>
    <td>${comp}</td>
    <!-- ONE ACTION ROW. These seven buttons were written out here by hand, so
         the live TABLE offered Sync and Add-variant that the live TILE did not,
         and the two drifted apart the same way the two card designs had.
         rowActions is the one definition (rule 12). -->
    <td><div class="acts">${rowActions(_r, "dotb", {live: true})}</div></td></tr>`;
}
