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
    let html = '<div class="card" style="padding:18px">' +
      '<div style="font-weight:650;font-size:15px;margin-bottom:6px">' +
      "The Amazon Advertising API is not connected yet</div>" +
      '<div class="cc" style="font-size:12.5px;line-height:1.6;max-width:700px">' +
      esc(st.error || "") + "</div>";
    if ((st.missing || []).length) {
      html += '<div class="cc" style="font-size:12px;margin-top:10px">' +
        "<b>Still needed:</b> " +
        st.missing.map(function (m) {
          return esc(m.replace("ads_", "").replace(/_/g, " "));
        }).join(", ") + "</div>";
    }
    if ((st.how || []).length) {
      html += '<ol class="drp-how">';
      st.how.forEach(function (h) { html += "<li>" + esc(h) + "</li>"; });
      html += "</ol>";
    }
    // Everything else on this screen is built and waiting. Said plainly, so it
    // does not look like a screen that has not been made yet.
    html += '<div class="cc" style="font-size:11.5px;margin-top:12px;max-width:700px">' +
      "Everything on this page is built and tested — it is waiting only for the " +
      "connection. The moment those four values are in, press Run and it works." +
      "</div>";
    html += '<div style="margin-top:12px"><button class="db-chip" onclick="drpStatus()">' +
      '<i class="ti ti-refresh"></i> Check again</button></div>';
    html += "</div>";
    box.innerHTML = html;
    return;
  }

  // ---- connected ----------------------------------------------------------
  let html =
    '<div class="card" style="padding:13px;margin-bottom:12px;display:flex;' +
    'gap:8px;align-items:flex-end;flex-wrap:wrap">' +
    '<div><label class="cc" style="display:block;font-size:11px">Look back</label>' +
    '<select id="drp_days" class="ed" style="width:120px">' +
    ["7", "14", "30", "60", "90"].map(function (d) {
      return '<option value="' + d + '"' + (String(DRP.days) === d ? " selected" : "") +
             ">" + d + " days</option>";
    }).join("") + "</select></div>" +
    '<div><label class="cc" style="display:block;font-size:11px">ACOS target %</label>' +
    '<input id="drp_target" class="ed" style="width:110px" placeholder="optional" ' +
    'value="' + esc(DRP.target) + '"></div>' +
    '<button class="primary" onclick="drpRun()"><i class="ti ti-stethoscope"></i> Run</button>' +
    '<div class="cc" style="font-size:11.5px;max-width:420px">Without a target, ' +
    "nothing here judges whether an ACOS is good or bad — a guessed target is " +
    "confident advice about a number nobody chose." +
    "</div></div>";

  if (DRP.note) {
    html += '<div class="sresfail" style="margin-bottom:12px">' + esc(DRP.note) + "</div>";
  }

  const d = DRP.data;
  if (!d) {
    html += '<div class="card" style="padding:18px"><div class="cc">' +
      "Press Run to pull the campaign and search-term reports." + "</div></div>";
    box.innerHTML = html;
    return;
  }

  // ---- headline -----------------------------------------------------------
  const t = d.totals || {};
  html += '<div class="catp-cards">' +
    '<div class="catp-card"><div class="catp-k">Spend</div>' +
    '<div class="catp-v">' + drpMoney(t.spend) + "</div>" +
    '<div class="catp-s">' + esc(d.start || "") + " → " + esc(d.end || "") + "</div></div>" +
    '<div class="catp-card"><div class="catp-k">Sales from ads</div>' +
    '<div class="catp-v">' + drpMoney(t.sales) + "</div>" +
    '<div class="catp-s">' + (t.acos === null || t.acos === undefined ? "ACOS unknown"
      : "ACOS " + (t.acos * 100).toFixed(0) + "%") + "</div></div>" +
    '<div class="catp-card' + (t.wasted ? " warn" : "") + '">' +
    '<div class="catp-k">Spent with no sales</div>' +
    '<div class="catp-v">' + drpMoney(t.wasted) + "</div>" +
    '<div class="catp-s">on terms with enough clicks to judge</div></div>' +
    "</div>";

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
    html += '<div class="card" style="padding:18px"><div class="cc">' +
      "Nothing to flag from the rules that ran." + "</div></div>";
    box.innerHTML = html;
    return;
  }

  html += '<div class="card" style="overflow-x:auto"><table class="stk-table"><thead><tr>' +
    "<th>Verdict</th><th>What</th><th>The finding</th><th>Why</th>" +
    "<th>What to do</th></tr></thead><tbody>";
  d.findings.forEach(function (f) {
    html += "<tr>" +
      "<td>" + drpSev(f.severity) + "</td>" +
      '<td style="font-weight:600;max-width:200px;overflow:hidden;' +
      'text-overflow:ellipsis">' + esc(f.subject || "") + "</td>" +
      '<td style="max-width:230px">' + esc(f.what || "") + "</td>" +
      '<td class="cc" style="font-size:11.5px;max-width:290px">' + esc(f.why || "") + "</td>" +
      '<td class="cc" style="font-size:11.5px;max-width:300px">' + esc(f.do || "") + "</td>" +
      "</tr>";
  });
  html += "</tbody></table></div>";
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
