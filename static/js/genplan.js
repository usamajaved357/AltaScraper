// static/js/genplan.js — what Generate would do, shown before you press it.
//
//     "check and let me know if the current workflow of listing generation works
//      while preventing the already created listing copies to be created again"
//
// The generator has always skipped products it has already made. The problem was
// never the rule — it was that the only way to SEE the rule working was to press
// Generate and watch the log scroll, by which point the AI spend has started.
//
// So this asks first. It calls the generator's own duplicate check through
// /run/plan, which costs nothing: no AI call, no Amazon call, no write.
//
// THE STATE THIS EXISTS TO CATCH is a full queue with nothing on record. That is
// exactly what a broken duplicate check looks like, and it is indistinguishable
// from a genuine first run — so it is called out in words rather than left as
// two numbers to compare.

let GENPLAN = { data: null, loading: false };

function _gpQs() { return (typeof scopeQs === "function") ? scopeQs() : ""; }

function genplanRender() {
  const box = document.getElementById("genplan");
  if (!box) return;
  if (GENPLAN.loading) {
    box.innerHTML = '<div class="cc" style="padding:10px 12px">Checking what has ' +
      "already been made…</div>";
    return;
  }
  const d = GENPLAN.data;
  if (!d) { box.innerHTML = ""; return; }
  if (!d.ok) {
    box.innerHTML = '<div class="genplan-bad">Could not work out what a run ' +
      "would do: " + esc(d.error || "") + "</div>";
    return;
  }
  const c = d.counts || {};
  // The one state that needs shouting about: a queue with nothing on record.
  const risky = c.queued > 0 && !c.already_made;

  let html = '<div class="genplan-in' + (risky ? " bad" : "") + '">' +
    '<div class="genplan-nums">' +
    '<span class="genplan-n go"><b>' + (c.generate || 0) + "</b> to generate</span>" +
    '<span class="genplan-n"><b>' + (c.skip || 0) + "</b> already made — skipped</span>" +
    (c.repeat ? '<span class="genplan-n"><b>' + c.repeat +
                "</b> repeated in the queue</span>" : "") +
    (c.no_asin ? '<span class="genplan-n warn"><b>' + c.no_asin +
                 "</b> with no ASIN</span>" : "") +
    '<span class="genplan-n cc">' + (c.queued || 0) + " queued · " +
    (c.already_made || 0) + " on record</span>" +
    "</div>" +
    '<div class="genplan-say">' + esc(d.verdict || "") + "</div>";
  if (d.imported_at) {
    // A queue with no date on it is indistinguishable from a fresh one, which
    // is how last month's list gets generated.
    html += '<div class="cc" style="font-size:11px">Queue imported ' +
      esc(d.imported_at) + "</div>";
  }
  html += '<div style="margin-top:7px"><button class="db-chip" onclick="genplanLoad()">' +
    '<i class="ti ti-refresh"></i> Check again</button>' +
    ((d.generate || []).length
      ? ' <button class="db-chip" onclick="genplanToggle()">' +
        '<i class="ti ti-list"></i> ' +
        (GENPLAN.show ? "Hide" : "Show") + " the " + d.generate.length +
        " it would make</button>"
      : "") +
    "</div>";
  if (GENPLAN.show && (d.generate || []).length) {
    html += '<div class="genplan-list">' +
      d.generate.map(function (a) { return "<span>" + esc(a) + "</span>"; }).join("") +
      "</div>";
  }
  html += "</div>";
  box.innerHTML = html;
}

function genplanToggle() {
  GENPLAN.show = !GENPLAN.show;
  genplanRender();
}

async function genplanLoad() {
  GENPLAN.loading = true; genplanRender();
  try {
    GENPLAN.data = await (await fetch("/run/plan" + _gpQs())).json();
  } catch (e) {
    GENPLAN.data = { ok: false, error: String(e) };
  }
  GENPLAN.loading = false;
  genplanRender();
}
