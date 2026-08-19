// static/js/drppc.js — the Dr PPC console.
//
// Built before the Advertising API is connected, so the FIRST thing this screen
// has to do well is explain that it is not connected — and what to do about it.
// "Not connected" and "connected and there are no problems" look identical on an
// empty page, and only one of them is good news.
//
// IT RECOMMENDS AND STOPS. Every finding names the exact change it would make
// and leaves it to you (CLAUDE.md Rule 8). Nothing in this app can write a bid:
// the advertising module whitelists its only POST to the reporting paths, so
// the guarantee is enforced rather than promised.

let DRP = { status: null, data: null, loading: false, note: "", days: 30, target: "" };

function _drpQs(extra) {
  return (typeof scopeQs === "function") ? scopeQs(extra) : "";
}

function drpSev(s) {
  if (s === "critical") return '<span class="ld-pill off">Costing you</span>';
  if (s === "warn") return '<span class="ld-pill warn">Worth a look</span>';
  return '<span class="ld-pill ok">Opportunity</span>';
}

function drpMoney(v) {
  if (v === null || v === undefined) return "—";
  const sym = (typeof curSymbol === "function") ? curSymbol("") : "";
  return sym + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2,
                                                     maximumFractionDigits: 2 });
}

function drpRender() {
  const box = document.getElementById("drp_body");
  if (!box) return;
  if (DRP.loading) {
    box.innerHTML = '<div class="cc" style="padding:14px">Asking Amazon to build ' +
      "the reports — this takes up to a couple of minutes…</div>";
    return;
  }

  const st = DRP.status;

  // ---- not connected: the most likely state for a while ------------------
  if (st && !st.connected) {
    // The four values, drawn as the same stat row every other screen opens
    // with — so "three of four in place" is readable at a glance instead of
    // being a sentence in a paragraph.
    const need = st.missing || [];
    const total = 4;
    let html = uiStats([
      { label: "Connection", value: "Not yet",
        tone: "warn", note: "no advertising data can be read" },
      { label: "Values in place", value: (total - need.length) + " of " + total,
        tone: need.length ? "warn" : "",
        note: need.length
          ? "still needed: " + need.map(function (m) {
              return m.replace("ads_", "").replace(/_/g, " ");
            }).join(", ")
          : "all four are set" },
      { label: "Rules ready", value: "6",
        note: "built and tested, waiting only on the connection" },
      { label: "Bids this app can change", value: "0",
        note: "enforced, not promised — Rule 8" }
    ]);

    let body = '<div class="cc" style="font-size:12.5px;line-height:1.6;max-width:700px">' +
      esc(st.error || "") + "</div>";
    if ((st.how || []).length) {
      body += '<ol class="drp-how">';
      st.how.forEach(function (h) { body += "<li>" + esc(h) + "</li>"; });
      body += "</ol>";
    }
    body += '<div style="margin-top:12px"><button class="db-chip" onclick="drpStatus()">' +
      '<i class="ti ti-refresh"></i> Check again</button></div>';
    html += uiPanel("How to connect it",
      "Everything on this page is built and tested — it is waiting only for the " +
      "connection. The moment those values are in, press Run and it works.", body);
    box.innerHTML = html;
    return;
  }

  // ---- connected ----------------------------------------------------------
  let html = uiToolbar(
    '<div><label class="cc" style="display:block;font-size:11px">Look back</label>' +
    '<select id="drp_days" class="ed" style="width:120px">' +
    ["7", "14", "30", "60", "90"].map(function (d) {
      return '<option value="' + d + '"' + (String(DRP.days) === d ? " selected" : "") +
             ">" + d + " days</option>";
    }).join("") + "</select></div>" +
    '<div><label class="cc" style="display:block;font-size:11px">ACOS target %</label>' +
    '<input id="drp_target" class="ed" style="width:110px" placeholder="optional" ' +
    'value="' + esc(DRP.target) + '"></div>' +
    '<button class="primary" onclick="drpRun()"><i class="ti ti-stethoscope"></i> Run</button>',
    '<div class="cc" style="font-size:11.5px;max-width:420px;text-align:right">Without a ' +
    "target, nothing here judges whether an ACOS is good or bad — a guessed target is " +
    "confident advice about a number nobody chose.</div>");

  if (DRP.note) {
    html += '<div class="sresfail" style="margin-bottom:12px">' + esc(DRP.note) + "</div>";
  }

  const d = DRP.data;
  if (!d) {
    html += uiEmpty("Press Run",
      "Amazon builds the campaign and search-term reports when they are asked for, which " +
      "takes up to a couple of minutes — so opening this page deliberately does not fetch " +
      "them.");
    box.innerHTML = html;
    return;
  }

  // ---- headline -----------------------------------------------------------
  const t = d.totals || {};
  html += uiStats([
    { label: "Spend", value: drpMoney(t.spend),
      note: (d.start || "") + " → " + (d.end || "") },
    { label: "Sales from ads", value: drpMoney(t.sales),
      note: (t.acos === null || t.acos === undefined ? "ACOS unknown"
             : "ACOS " + (t.acos * 100).toFixed(0) + "%") },
    { label: "Spent with no sales", value: drpMoney(t.wasted),
      tone: t.wasted ? "warn" : "",
      note: "on terms with enough clicks to judge" },
    { label: "Things to look at", value: (d.findings || []).length,
      tone: (d.findings || []).some(function (f) { return f.severity === "critical"; })
        ? "bad" : "",
      note: "each one names the exact change — none is applied" }
  ]);

  // What was NOT judged, above the findings — same rule as the compliance
  // screen. A console that skipped half its checks and found nothing is not an
  // account in good order.
  if ((d.notes || []).length) {
    html += '<div class="cmp-gaps"><div class="cmp-gapsk">' +
      '<i class="ti ti-alert-triangle"></i> What this did NOT judge</div>';
    d.notes.forEach(function (n) { html += '<div class="cmp-gap">' + esc(n) + "</div>"; });
    html += "</div>";
  }

  if (!(d.findings || []).length) {
    html += uiEmpty("Nothing to flag",
      "None of the rules that ran found anything over the window above. Check what was " +
      "not judged, above — a console that skipped half its checks and found nothing is " +
      "not an account in good order.");
    box.innerHTML = html;
    return;
  }

  let tb = '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
    "<th>Verdict</th><th>What</th><th>The finding</th><th>Why</th>" +
    "<th>What to do</th></tr></thead><tbody>";
  d.findings.forEach(function (f) {
    tb += "<tr>" +
      "<td>" + drpSev(f.severity) + "</td>" +
      '<td style="font-weight:600;max-width:200px;overflow:hidden;' +
      'text-overflow:ellipsis">' + esc(f.subject || "") + "</td>" +
      '<td style="max-width:230px">' + esc(f.what || "") + "</td>" +
      '<td class="cc" style="font-size:11.5px;max-width:290px">' + esc(f.why || "") + "</td>" +
      '<td class="cc" style="font-size:11.5px;max-width:300px">' + esc(f.do || "") + "</td>" +
      "</tr>";
  });
  tb += "</tbody></table></div>";
  html += uiPanel("What to change, worst first",
    "Every row names the exact change and stops there. Nothing in this app can write a " +
    "bid — the advertising module whitelists its only POST to the reporting paths.", tb);
  box.innerHTML = html;
}

async function drpStatus() {
  DRP.note = "";
  try {
    const j = await (await fetch("/drppc/status" + _drpQs())).json();
    DRP.status = j;
  } catch (e) {
    DRP.note = "Could not check the connection: " + e;
  }
  drpRender();
}

async function drpRun() {
  const dEl = document.getElementById("drp_days");
  const tEl = document.getElementById("drp_target");
  DRP.days = (dEl && dEl.value) || 30;
  DRP.target = (tEl && tEl.value) || "";
  DRP.loading = true; DRP.note = ""; drpRender();
  try {
    const j = await (await fetch("/drppc/run" + _drpQs(), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days: Number(DRP.days),
                             target_acos: DRP.target || null })
    })).json();
    if (j && j.ok) { DRP.data = j; }
    else {
      DRP.note = (j && j.error) || "Could not run.";
      if (j && j.connected === false) { DRP.status = j; DRP.data = null; }
    }
  } catch (e) {
    DRP.note = "Could not run: " + e;
  }
  DRP.loading = false;
  drpRender();
}

function drpOnOpen() {
  // Checks the CONNECTION on open, never the reports — those are two Amazon
  // report builds and belong behind the button.
  if (!DRP.status) drpStatus();
  else drpRender();
}
