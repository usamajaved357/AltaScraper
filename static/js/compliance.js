// static/js/compliance.js — scan a live listing for compliance.
//
// The checks are this app's own, each written after a real listing was refused
// or taken down. Until now they only ran at GENERATION time, on copy about to
// be submitted — so a listing written before a rule existed, edited in Seller
// Central afterwards, or inherited from a supplier had never been looked at.
//
// THE SCORE IS FOR SORTING; THE FINDINGS ARE THE ANSWER. A number out of 100 is
// what makes forty ASINs rankable and nothing more, so every point lost is
// traceable to a named finding on the same screen, and what the scan COULD NOT
// check is shown as prominently as what it did.

let CMP = { scans: [], current: null, loading: false, note: "" };

function _cmpQs() { return (typeof scopeQs === "function") ? scopeQs() : ""; }

function cmpBand(score) {
  if (score >= 90) return "ok";
  if (score >= 70) return "warn";
  return "off";
}

function cmpSev(s) {
  if (s === "critical") return '<span class="ld-pill off">Critical</span>';
  if (s === "major") return '<span class="ld-pill warn">Major</span>';
  return '<span class="ld-pill unk">Minor</span>';
}

function cmpRender() {
  const box = document.getElementById("cmp_body");
  if (!box) return;

  let html = uiToolbar(
    '<div><label class="cc" style="display:block;font-size:11px">ASIN to scan</label>' +
    '<input id="cmp_asin" class="ed" style="width:160px" placeholder="B0XXXXXXXX"></div>' +
    '<button class="primary" onclick="cmpScan()"' + (CMP.loading ? " disabled" : "") + '>' +
    '<i class="ti ti-shield-search"></i> ' + (CMP.loading ? "Scanning…" : "Scan it") + "</button>",
    '<div class="cc" style="font-size:11.5px;max-width:460px;text-align:right">Reads what is ' +
    "actually LIVE on Amazon, not the draft this app holds. Nothing is changed — editing a " +
    "live listing is a submission, and that stays your decision.</div>");

  if (CMP.note) {
    html += '<div class="sresfail" style="margin-bottom:12px">' + esc(CMP.note) + "</div>";
  }

  // ---- how the account stands, before any single scan is read -------------
  // Four numbers at the top say how things ARE. A screen that opens with a
  // table makes you do the reading first, and mostly nobody does.
  if (CMP.scans.length) {
    const scored = CMP.scans.filter(function (s) { return typeof s.score === "number"; });
    const avg = scored.length
      ? Math.round(scored.reduce(function (a, s) { return a + s.score; }, 0) / scored.length)
      : null;
    let crit = 0, maj = 0;
    CMP.scans.forEach(function (s) {
      crit += (s.counts && s.counts.critical) || 0;
      maj += (s.counts && s.counts.major) || 0;
    });
    const seen = {};
    CMP.scans.forEach(function (s) { seen[s.asin] = 1; });
    html += uiStats([
      { label: "Listings scanned", value: Object.keys(seen).length,
        note: CMP.scans.length + " scan" + (CMP.scans.length === 1 ? "" : "s") + " in total" },
      { label: "Average score", value: avg === null ? "" : avg,
        tone: avg === null ? "" : (avg >= 90 ? "" : (avg >= 70 ? "warn" : "bad")),
        note: "across every scan, out of 100" },
      { label: "Critical findings", value: crit, tone: crit ? "bad" : "",
        note: crit ? "a refusal or takedown risk" : "none found" },
      { label: "Major findings", value: maj, tone: maj ? "warn" : "",
        note: maj ? "worth fixing before the next edit" : "none found" }
    ]);
  }

  // ---- the scan just run --------------------------------------------------
  const r = CMP.current;
  if (r) {
    html += '<div class="card" style="margin-bottom:12px">' +
      '<div class="cmp-head">' +
      '<div class="cmp-score ' + cmpBand(r.score) + '">' + r.score + "</div>" +
      "<div><div style=\"font-weight:650;font-size:15px\">" + esc(r.status) + "</div>" +
      '<div class="cc" style="font-size:12px">' + esc(r.asin) +
      (r.brand ? " · " + esc(r.brand) : "") +
      (r.product_type ? " · " + esc(r.product_type) : "") + "</div>" +
      '<div class="cc" style="font-size:11.5px;max-width:640px;margin-top:3px">' +
      esc((r.title || "").slice(0, 130)) + "</div></div>" +
      '<div class="cmp-counts">' +
      '<span class="ld-pill off">' + (r.counts.critical || 0) + " critical</span>" +
      '<span class="ld-pill warn">' + (r.counts.major || 0) + " major</span>" +
      '<span class="ld-pill unk">' + (r.counts.minor || 0) + " minor</span>" +
      "</div></div>";

    // WHAT COULD NOT BE CHECKED, ABOVE the findings rather than under them. A
    // scan that skipped half its checks and scored 96 is not a listing in good
    // order, and burying that at the bottom is how the number becomes a lie.
    if ((r.notes || []).length) {
      html += '<div class="cmp-gaps"><div class="cmp-gapsk">' +
        '<i class="ti ti-alert-triangle"></i> What this scan did NOT cover</div>';
      r.notes.forEach(function (n) {
        html += '<div class="cmp-gap">' + esc(n) + "</div>";
      });
      html += "</div>";
    }

    if (!(r.findings || []).length) {
      html += '<div class="cc" style="padding:10px 2px;font-size:12.5px">' +
        "No findings from the checks that ran." + "</div>";
    } else {
      html += '<div class="panelhead" style="padding-left:0"><div>' +
        '<div class="paneltitle">Every finding, worst first</div>' +
        '<div class="panelsub">Every point off the score above is one of these rows — ' +
        "the number is for sorting, the rows are the answer.</div></div></div>" +
        '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
        "<th>Severity</th><th>What</th><th>Where</th><th>Why it matters</th>" +
        "<th>What to do</th></tr></thead><tbody>";
      r.findings.forEach(function (f) {
        html += "<tr>" +
          "<td>" + cmpSev(f.severity) + "</td>" +
          '<td style="font-weight:600">' + esc(f.what || "") + "</td>" +
          '<td class="cc" style="font-size:11px">' + esc(f.where || "—") + "</td>" +
          '<td class="cc" style="font-size:11.5px;max-width:320px">' + esc(f.why || "") + "</td>" +
          '<td class="cc" style="font-size:11.5px;max-width:280px">' + esc(f.fix || "") + "</td>" +
          "</tr>";
      });
      html += "</tbody></table></div>";
    }
    html += "</div>";
  }

  // ---- history ------------------------------------------------------------
  if (!CMP.scans.length) {
    html += uiEmpty("Nothing scanned yet",
      "These checks were written after real listings were refused or taken down, and " +
      "until now they only ran on copy this app was about to submit. A listing written " +
      "before a rule existed, or edited in Seller Central afterwards, has never been " +
      "looked at. Put an ASIN in the box above to look at one.");
    box.innerHTML = html;
    return;
  }
  {
    let t = '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
      "<th>When</th><th>ASIN</th><th>Product</th><th>Score</th><th>Status</th>" +
      "<th>Findings</th></tr></thead><tbody>";
    CMP.scans.forEach(function (s) {
      t += "<tr>" +
        '<td class="cc" style="font-size:11px">' + esc(s.at || "") + "</td>" +
        '<td style="font-weight:600">' + esc(s.asin) + "</td>" +
        '<td class="cc" style="font-size:11px;max-width:280px;overflow:hidden;' +
        'text-overflow:ellipsis;white-space:nowrap">' + esc(s.title || "") + "</td>" +
        '<td><span class="cmp-mini ' + cmpBand(s.score) + '">' + s.score + "</span></td>" +
        "<td>" + esc(s.status || "") + "</td>" +
        '<td class="cc">' + ((s.counts && (s.counts.critical || 0) + (s.counts.major || 0) +
                              (s.counts.minor || 0)) || 0) + "</td>" +
        "</tr>";
    });
    t += "</tbody></table></div>";
    html += uiPanel("Earlier scans", "Newest first. A score moving down between two " +
      "scans of the same ASIN means the live listing changed, not that the rules did.", t);
  }

  box.innerHTML = html;
}

async function cmpLoad() {
  try {
    const j = await (await fetch("/compliance/scans" + _cmpQs())).json();
    if (j && j.ok) CMP.scans = j.scans || [];
  } catch (e) { /* the history is not worth an error banner */ }
  cmpRender();
}

async function cmpScan() {
  const el = document.getElementById("cmp_asin");
  const asin = ((el && el.value) || "").trim().toUpperCase();
  if (!asin) { toast("Enter an ASIN first."); return; }
  CMP.loading = true; CMP.note = ""; cmpRender();
  try {
    const j = await (await fetch("/compliance/scan" + _cmpQs(), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asin: asin })
    })).json();
    if (j && j.ok) { CMP.current = j; }
    else { CMP.note = (j && j.error) || "Could not scan that ASIN."; }
  } catch (e) {
    CMP.note = "Could not scan that ASIN: " + e;
  }
  CMP.loading = false;
  await cmpLoad();
}
