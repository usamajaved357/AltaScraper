// static/js/reimbursements.js — money Amazon owes back, as its own page.
//
// The CHECK already existed: domain/money_back.py, reached at
// /inventory/money-back, reading settled orders out of order_fees. What it did
// not have was a place of its own — it was the fourth tab inside Inventory,
// which is where you go to think about stock, not about money you are owed.
//
// So this is the page, and the renderer is SHARED (CLAUDE.md Rule 12): the
// Inventory tab calls rbHtml() too, so there is one table, one arithmetic and
// one set of words. A second copy would disagree with the first the day either
// was corrected.
//
// IT FILES NOTHING. Not a claim, not a case, not a message. It finds the money
// and shows the whole sum so it can be checked rather than believed, and then
// typed into Seller Central by a person who has decided to. Every row is a
// CANDIDATE for that reason — Amazon has exceptions this cannot see, and
// calling a candidate a certainty is how a page like this stops being trusted.

let RB = {data: null, loading: false, asked: false, error: ""};

function _rbEsc(s) {
  return (typeof esc === "function") ? esc(s)
    : String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
        return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c];
      });
}

function _rbMoney(v, cur) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof curMoney === "function") return curMoney(v, cur);
  return String(v);
}

function _rbNum(v) {
  const n = Number(v || 0);
  return isNaN(n) ? "0" : n.toLocaleString();
}

function _rbQs() { return (typeof scopeQs === "function") ? scopeQs() : ""; }

/* THE ONE RENDERER. Returns the whole block: the figures, then the table, then
   the scope line. Called by this page and by the Inventory tab. */
function rbHtml() {
  const m = RB.data;
  if (RB.error) {
    return '<div class="sresfail">' + _rbEsc(RB.error) + "</div>";
  }
  if (!m) {
    return '<div class="cc" style="padding:16px">Checking the settled orders…</div>';
  }

  // A ZERO WITH NO DENOMINATOR IS NOT AN ANSWER. "Nothing owed" means one thing
  // when two hundred refunds were examined and something else entirely when
  // none were, so the count of what was checked is a headline figure and not a
  // footnote.
  const owedPairs = Object.keys(m.owed_by_currency || {});
  const owedText = owedPairs.length
    ? owedPairs.map(function (cc) { return _rbMoney(m.owed_by_currency[cc], cc); }).join(" + ")
    : _rbMoney(0, (m.currency || ""));

  let h = "";
  if (typeof uiSource === "function") {
    h += uiSource([
      {k: "Source", v: "Amazon Finances, per settled order"},
      {k: "Checked", v: _rbNum(m.orders_checked || 0) + " settled, "
                        + _rbNum(m.refunds_checked || 0) + " refunded"},
      {k: "Rule", v: "Amazon's published refund administration fee"},
    ], "Only orders Amazon has SETTLED can be checked — a refund it has not "
     + "finished processing has no fee figures yet.");
  }
  if (typeof uiStats === "function") {
    h += uiStats([
      {label: "Owed back", value: owedText,
       tone: m.count ? "warn" : "good",
       note: m.count ? "across " + _rbNum(m.count) + " order"
                       + (m.count === 1 ? "" : "s")
                     : "nothing found on what has settled"},
      {label: "Candidates", value: _rbNum(m.count || 0),
       tone: m.count ? "warn" : "",
       note: m.count ? "each one shows its own arithmetic" : "none"},
      {label: "Refunds checked", value: _rbNum(m.refunds_checked || 0),
       tone: (m.refunds_checked ? "" : "warn"),
       note: m.refunds_checked ? "every refund Amazon has settled"
                               : "none have settled yet — nothing to check"},
      {label: "Orders settled", value: _rbNum(m.orders_checked || 0),
       note: "the pool the refunds came from"},
    ]);
  }

  const rule = '<div class="cc" style="font-size:11.5px;line-height:1.55;max-width:760px;'
    + 'margin:0 0 12px">' + _rbEsc(m.rule || "") + " <b>Nothing here is filed for "
    + "you</b> — this finds the money and shows the sum; raising the case stays "
    + "your decision.</div>";

  if (!m.count) {
    const body = m.refunds_checked
      ? "Amazon kept less than its own cap on every refund it has settled for "
        + "this account. That is the right answer today, and the reason to keep "
        + "the page is that it will say something different on the day it is not."
      : "No refunds have settled yet, so there is nothing to check. This fills "
        + "in as Amazon settles orders.";
    h += (typeof uiEmpty === "function")
      ? uiEmpty(m.refunds_checked ? "Nothing owed" : "Nothing to check yet", body)
      : '<div class="card" style="padding:18px">' + body + "</div>";
    return h + rule;
  }

  let t = '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>'
    + "<th>Order</th><th>Settled</th><th>Sale</th><th>Refunded</th>"
    + "<th>Fee taken</th><th>Given back</th><th>May keep</th><th>Owed</th>"
    + "</tr></thead><tbody>";
  (m.candidates || []).forEach(function (c) {
    t += '<tr title="' + _rbEsc(c.why) + '">'
      + "<td><b>" + _rbEsc(c.order_id) + "</b>"
      + (c.marketplace ? '<div class="cc" style="font-size:10.5px">'
                         + _rbEsc(c.marketplace) + "</div>" : "")
      + "</td>"
      + '<td class="cc" style="font-size:11px">' + _rbEsc(c.posted_date || "") + "</td>"
      + "<td>" + _rbMoney(c.principal, c.currency) + "</td>"
      + "<td>" + _rbMoney(c.refunded, c.currency)
      // A partial refund returns a proportional share of the fee, so the share
      // is shown -- otherwise the arithmetic below cannot be followed.
      + (c.share_pct < 99.5 ? '<div class="cc" style="font-size:10.5px">'
                              + c.share_pct + "% of it</div>" : "")
      + "</td>"
      + "<td>" + _rbMoney(c.fee_on_refunded_part, c.currency) + "</td>"
      + "<td>" + _rbMoney(c.returned, c.currency) + "</td>"
      + "<td>" + _rbMoney(c.allowed_to_keep, c.currency) + "</td>"
      + '<td><b style="color:var(--warn)">' + _rbMoney(c.owed, c.currency)
      + "</b></td></tr>";
  });
  t += "</tbody></table></div>";

  h += (typeof uiPanel === "function")
    ? uiPanel("Every candidate, and the sum behind it",
        "Called candidates on purpose. Amazon has exceptions this cannot see — a "
        + "promotional fee, a category minimum, a refund settled across two "
        + "events — so check the arithmetic before raising a case.", t)
    : t;
  return h + rule;
}

async function rbLoad(force) {
  if (RB.loading) return;
  if (RB.data && !force) { rbRender(); return; }
  RB.loading = true; RB.error = "";
  rbRender();
  try {
    const j = await (await fetch("/inventory/money-back" + _rbQs())).json();
    if (j && j.ok) { RB.data = j; }
    else { RB.error = (j && j.error) || "Could not read the settled orders."; }
  } catch (e) {
    RB.error = "Could not read the settled orders: " + e;
  }
  RB.loading = false;
  rbRender();
}

function rbRender() {
  const box = document.getElementById("rb_body");
  if (box) box.innerHTML = rbHtml();
  // The Inventory tab, when it happens to be the thing on screen.
  if (typeof stockRender === "function" && typeof STOCK !== "undefined"
      && STOCK && STOCK.tab === "money") {
    try { stockRender(); } catch (e) {}
  }
}

function reimbursementsOnOpen() {
  RB.asked = true;
  rbLoad();
}
