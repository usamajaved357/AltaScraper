// static/js/overview.js — every account, month by month.
//
//   Orbit's Brand Overview.
//
// The one screen in this app that is NOT scoped to the account you are standing
// in. Every other screen answers a question about one account, which is right —
// it is what stopped one account's orders appearing on another's. But "how is
// the business doing" is not a question about one account, and until now the
// only way to see six together was to open each in turn and add up by hand.
//
// CURRENCIES ARE NEVER ADDED. £500 + $500 is not 1000 of anything. Totals are
// grouped by currency and the screen says why, rather than putting an invented
// combined figure at the top of the most-read page.

let OVW = { data: null, loading: false, note: "", months: 13 };

function ovwFmt(v, cur) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  const sym = (typeof curSymbol === "function") ? curSymbol(cur) : "";
  if (Math.abs(n) >= 10000) return sym + (n / 1000).toFixed(1) + "k";
  return sym + n.toLocaleString(undefined, { minimumFractionDigits: 0,
                                             maximumFractionDigits: 0 });
}

function ovwMonthName(k) {
  const M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const p = String(k || "").split("-");
  if (p.length < 2) return String(k || "");
  return (M[Number(p[1]) - 1] || "?") + " " + p[0].slice(2);
}

function ovwRender() {
  const box = document.getElementById("ovw_body");
  if (!box) return;
  if (OVW.loading) { box.innerHTML = '<div class="cc" style="padding:14px">Reading every account…</div>'; return; }
  if (OVW.note) { box.innerHTML = '<div class="sresfail">' + esc(OVW.note) + "</div>"; return; }
  const d = OVW.data;
  if (!d) { box.innerHTML = ""; return; }

  let html = "";
  // Which accounts this is, when it is not all of them. A restricted user
  // seeing three of six must not be left thinking that is the whole business.
  if (d.access_note) {
    html += '<div class="cc" style="font-size:11.5px;margin:0 0 10px">' +
            esc(d.access_note) + "</div>";
  }
  if (d.note) {
    html += '<div class="issuesbox" style="background:#241f10;border:1px solid #3a3320;' +
            'color:#e6d9b8;margin-bottom:12px">' + esc(d.note) + "</div>";
  }

  // ---- totals, per currency ----------------------------------------------
  if ((d.totals || []).length) {
    html += '<div class="ovw-totals">';
    d.totals.forEach(function (t) {
      html += '<div class="ovw-total">' +
        '<div class="catp-k">' + esc(t.currency || "unknown currency") + "</div>" +
        '<div class="catp-v">' + ovwFmt(t.sales, t.currency) + "</div>" +
        '<div class="catp-s">' + Math.round(t.units).toLocaleString() +
        " units · " + t.accounts + " account" + (t.accounts === 1 ? "" : "s") +
        "</div></div>";
    });
    html += "</div>";
  }
  // Said plainly rather than left to be worked out from two cards.
  if (d.currency_note) {
    html += '<div class="cc" style="font-size:11.5px;max-width:760px;margin:0 0 12px;' +
            'line-height:1.5">' + esc(d.currency_note) + "</div>";
  }

  // ---- the grid -----------------------------------------------------------
  const labels = d.labels || [];
  if (!(d.blocks || []).length) { box.innerHTML = html; return; }

  html += '<div class="card" style="overflow-x:auto"><table class="stk-table ovw-grid">' +
    "<thead><tr><th>Account</th>";
  labels.forEach(function (k) {
    html += "<th>" + esc(ovwMonthName(k)) + "</th>";
  });
  html += "<th>Total</th></tr></thead><tbody>";

  d.blocks.forEach(function (b) {
    const byMonth = {};
    b.months.forEach(function (m) { byMonth[m.month] = m; });
    html += "<tr><td><div style=\"font-weight:600\">" + esc(b.label) + "</div>" +
      '<div class="cc" style="font-size:11px">' + esc(b.marketplace) +
      (b.currency ? " · " + esc(b.currency) : "") + "</div></td>";
    labels.forEach(function (k) {
      const m = byMonth[k];
      // NOTHING STORED IS NOT ZERO SALES. The server returns a row for every
      // month in the window whether or not anything was synced, and an unsynced
      // month carries stored:false. Drawing "0" there would show a business
      // trading nothing when the truth is nobody has looked.
      if (!m || !m.stored) {
        html += '<td class="cc ovw-none" title="nothing stored for this month — ' +
                'not the same as no sales">·</td>';
        return;
      }
      html += '<td' + (m.partial ? ' class="ovw-partial" title="this month is not finished"' : "") +
        ">" + ovwFmt(m.sales, b.currency) +
        (m.partial ? '<span class="ovw-star">*</span>' : "") + "</td>";
    });
    html += '<td style="font-weight:600">' +
      (b.has_data ? ovwFmt(b.sales, b.currency)
                  : '<span class="cc" title="nothing synced for this account">not synced</span>') +
      "</td></tr>";
  });
  html += "</tbody></table></div>";

  html += '<div class="cc" style="font-size:11px;margin-top:8px">' +
    "<b>·</b> means nothing stored for that month, which is not the same as no sales. " +
    "<b>*</b> marks the current month, which is not finished." + "</div>";

  if (d.unsynced_note) {
    html += '<div class="issuesbox" style="background:#241f10;border:1px solid #3a3320;' +
            'color:#e6d9b8;margin-top:10px">' + esc(d.unsynced_note) + "</div>";
  }

  if ((d.problems || []).length) {
    html += '<div class="issuesbox" style="background:#241f10;border:1px solid #3a3320;' +
            'color:#e6d9b8;margin-top:12px"><b>Some accounts could not be read:</b><br>' +
            d.problems.map(esc).join("<br>") + "</div>";
  }

  box.innerHTML = html;
}

async function ovwLoad() {
  OVW.loading = true; OVW.note = ""; ovwRender();
  try {
    const j = await (await fetch("/overview?months=" + OVW.months)).json();
    if (j && j.ok) OVW.data = j;
    else OVW.note = (j && j.error) || "Could not build the overview.";
  } catch (e) {
    OVW.note = "Could not build the overview: " + e;
  }
  OVW.loading = false;
  ovwRender();
}
