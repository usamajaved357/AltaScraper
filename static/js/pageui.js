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
  return '<div class="ui-stat' + (o.tone ? " " + o.tone : "") + '"' +
    (o.title ? ' title="' + esc(o.title) + '"' : "") + ">" +
    '<div class="ui-stat-k">' + esc(o.label || "") + "</div>" +
    '<div class="ui-stat-v">' + v + "</div>" + d + "</div>";
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

// An empty state that says what to DO. Every screen has one and most of them
// said "nothing here", which is indistinguishable from broken.
function uiEmpty(title, body, action) {
  return '<div class="ui-empty">' +
    '<div class="ui-empty-t">' + esc(title) + "</div>" +
    '<div class="ui-empty-b">' + (body || "") + "</div>" +
    (action ? '<div style="margin-top:11px">' + action + "</div>" : "") +
    "</div>";
}
