// static/js/pageui.js — the pieces every screen is built from.
//
//     "i see there are some pages that looks very good and nice like sales page
//      hourly sales traffic but almost every other page do not look attractive
//      and nice looking ... apply that same graphical and visual logic to the
//      pages which are not present in the orbit"
//
// Sales, Traffic and Hourly look right because they were built to Orbit's
// measured design: a row of stat cards with the number large and the movement
// beside it, then titled panels holding the detail. Everything since has been a
// bare table in a plain box, and a bare table is a spreadsheet, not a screen.
//
// The difference was never talent or effort — those three pages had a
// VOCABULARY and nothing else did. So this is that vocabulary, extracted from
// what they already do, as functions any page can call (CLAUDE.md Rule 12).
// Nothing here is new design; it is the existing design made reachable.
//
// THE STAT CARD IS THE IMPORTANT ONE. A screen that opens with four numbers
// tells you how things are before you read anything. A screen that opens with a
// table makes you do the reading first, and most of the time nobody does.

// One stat card. `delta` is optional and signed so that POSITIVE IS BETTER --
// the caller decides that, because for ACOS and cost down is the good direction
// and an arrow alone reads backwards on half the rows.
function uiStat(o) {
  const v = (o.value === null || o.value === undefined || o.value === "")
    ? '<span class="cc">—</span>' : o.value;
  let d = "";
  if (o.delta !== null && o.delta !== undefined && o.delta !== "") {
    const n = Number(o.delta);
    const good = o.better === undefined ? (n > 0) : !!o.better;
    const arrow = n > 0 ? "↑" : (n < 0 ? "↓" : "");
    d = '<div class="ui-delta ' + (n === 0 ? "flat" : (good ? "up" : "down")) + '">' +
        arrow + " " + (o.deltaText || (Math.abs(n).toFixed(1) + " %")) + "</div>";
  } else if (o.note) {
    d = '<div class="ui-note">' + esc(o.note) + "</div>";
  }
  // THE NUMBER FIRST, THE LABEL UNDER IT.
  //
  //     "the sizing and the theme of the repricer page is nice, i want this to
  //      be applied on all listings page and the catalog page"
  //
  // This built label-then-value, so a row of cards read as a row of WORDS with
  // numbers attached rather than a row of numbers. The Repricer's read the
  // other way round and that is the half of the difference that is structural
  // rather than a size -- the rest is in static/css/datatable.css.
  //
  // Changed here, once, so every screen that opens with four numbers gets it
  // (CLAUDE.md Rule 12): Listings, the Catalog, Keywords, Stock, PPC and the
  // rest all call this.
  //
  // `share` is optional, 0..1: the bar along the bottom that says what the
  // count is a share OF. "5 held" means one thing out of 8 and another out of
  // 80, and a bare number cannot say which. Drawn only when the caller knows
  // the whole -- an invented denominator would be worse than no bar.
  let bar = "";
  if (o.share !== null && o.share !== undefined && o.share !== "") {
    const pc = Math.max(0, Math.min(100, Number(o.share) * 100));
    if (isFinite(pc)) {
      bar = '<div class="ui-stat-bar" style="width:' + pc.toFixed(1) + "%;" +
        "background:" + (o.barColor || "var(--line2)") + '"></div>';
    }
  }
  return '<div class="ui-stat' + (o.tone ? " " + o.tone : "") +
    (o.on ? " on" : "") + '"' +
    (o.onclick ? ' onclick="' + o.onclick + '"' : "") +
    (o.title ? ' title="' + esc(o.title) + '"' : "") + ">" +
    '<div class="ui-stat-v">' + v + "</div>" +
    '<div class="ui-stat-k">' + esc(o.label || "") + "</div>" +
    d + bar + "</div>";
}

// A row of them. Wraps and reflows on its own; the caller never sets a width.
function uiStats(cards) {
  const shown = (cards || []).filter(Boolean);
  if (!shown.length) return "";
  return '<div class="ui-stats">' + shown.map(uiStat).join("") + "</div>";
}

/* A titled panel — the thing Sales and Traffic put every chart and table in.
 * The title and the one line under it are what turn a box of numbers into a
 * statement about the business. */
function uiPanel(title, sub, body, opts) {
  const o = opts || {};
  return '<div class="salespanel' + (o.cls ? " " + o.cls : "") + '">' +
    (title || sub || o.right
      ? '<div class="panelhead">' +
        "<div>" +
        (title ? '<div class="paneltitle">' + esc(title) + "</div>" : "") +
        (sub ? '<div class="panelsub">' + esc(sub) + "</div>" : "") +
        "</div>" +
        (o.right ? '<span class="spacer"></span>' + o.right : "") +
        "</div>"
      : "") +
    (body || "") + "</div>";
}

// A segmented control, as the period presets on Sales and Traffic. One tray,
// buttons inside it, the chosen one filled.
function uiSeg(items, current, onPickName) {
  return '<div class="seg">' + (items || []).map(function (it) {
    const v = it.v === undefined ? it : it.v;
    const l = it.label === undefined ? String(it) : it.label;
    return '<button class="segbtn' + (String(v) === String(current) ? " on" : "") +
      '" onclick="' + onPickName + "(" + jsArg(String(v)) + ')">' + esc(l) + "</button>";
  }).join("") + "</div>";
}

/* The bar that sits under a page heading: a label, controls, and whatever the
 * page wants on the right. Sales and Traffic both have one and it is most of
 * what makes them read as a considered screen rather than a dump. */
function uiToolbar(left, right) {
  return '<div class="ui-toolbar">' + (left || "") +
    '<span class="spacer"></span>' + (right || "") + "</div>";
}

/* WHERE THIS NUMBER CAME FROM.
 *
 * Orbit's brand agent cites every figure it gives:
 *
 *     "DE 3P revenue EUR 124,312 MTD (Aug 1-19) vs EUR 198,450 last month full
 *      month -- source: get_brand_snapshot 2026-08-19, marketplace
 *      A1PA6795UKMFR9, 3P side."
 *
 * Our screens show the figure and not the provenance, which is fine right up
 * until somebody asks "why does this not match Seller Central" -- and then the
 * first twenty minutes go on working out which feed, which dates, and how
 * stale. Amazon has two feeds that describe the same trade and they disagree
 * for days at a time, so a number without its source is a number you cannot
 * act on.
 *
 * `parts` is an ordered list of {k, v} -- feed, dates, account, marketplace,
 * currency, as-of. Anything null or empty is dropped rather than printed as a
 * blank, because "Marketplace: —" is worse than no line at all.
 */
function uiSource(parts, note) {
  const shown = (parts || []).filter(function (p) {
    return p && p.v !== null && p.v !== undefined && String(p.v).trim() !== "";
  });
  if (!shown.length && !note) return "";
  return '<div class="ui-source">' +
    shown.map(function (p) {
      return '<span class="ui-source-i"><b>' + esc(p.k) + '</b> ' +
             esc(String(p.v)) + "</span>";
    }).join("") +
    (note ? '<span class="ui-source-n">' + esc(note) + "</span>" : "") +
    "</div>";
}

// An empty state that says what to DO. Every screen has one and most of them
// said "nothing here", which is indistinguishable from broken.
function uiEmpty(title, body, action) {
  return '<div class="ui-empty">' +
    '<div class="ui-empty-t">' + esc(title) + "</div>" +
    '<div class="ui-empty-b">' + (body || "") + "</div>" +
    (action ? '<div style="margin-top:11px">' + action + "</div>" : "") +
    "</div>";
}
