// static/js/performance.js -- the Employee Performance screen (29 Sep 2026).
//
//     "As an owner/manager, show me what meaningful work each employee did today
//      or during another selected period."
//     "Present objective work/activity/productivity evidence only."
//
// It reads the ONE activity log (domain/activity.py) through /activity/summary
// and /activity/list. Nothing here records anything: the server's after-request
// hook does that for every catalogued action (domain/activity_catalog.py).
//
// TEAM-WIDE, NOT ONE ACCOUNT. Like AI spend, this screen compares people across
// the accounts the viewer may open, so switching the open account does not
// change it; the Account filter narrows it on purpose. The server limits every
// row, and the team list, to the viewer's accounts whatever the page asks.
//
// STATES: loading (spinner), error (uiError, never shown as "nobody did
// anything"), empty (says why: nothing recorded, or the filters), a person with
// no work in the period (listed with 0, so silence is visible too). A redraw
// puts keyboard focus back where it was (design-system §8).

let PERF = { period: "today", timeline: null, timelineName: "", seq: 0, focus: "" };

const PERF_PERIODS = [
  { v: "today", label: "Today" }, { v: "yesterday", label: "Yesterday" },
  { v: "7d", label: "7 days" }, { v: "30d", label: "30 days" }, { v: "custom", label: "Custom" },
];

// THE PERIOD, IN THE VIEWER'S OWN DAYS. "Today" is midnight to now where the
// owner is sitting, so the bounds are computed here and sent as epoch seconds.
// -> {from, to}, or {error} for a custom range that cannot be used.
function perfBounds(period, now, fromStr, toStr) {
  const d = new Date(now);
  const day0 = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const DAY = 86400000;
  const end = now + 60000;
  const back = function (days) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() - days).getTime(); };
  let f, t;
  if (period === "yesterday") { f = back(1); t = day0; }
  else if (period === "7d") { f = back(6); t = end; }
  else if (period === "30d") { f = back(29); t = end; }
  else if (period === "custom") {
    const p = function (s) { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || "")); return m ? new Date(+m[1], +m[2] - 1, +m[3]).getTime() : null; };
    f = p(fromStr); const tt = p(toStr);
    if (f === null || tt === null) return { error: "Pick both dates", why: "Choose a From and a To date for the custom period." };
    if (tt < f) return { error: "The To date is before the From date", why: "Swap them, or pick a To date on or after the From date." };
    t = tt + DAY;                                     // the "to" day is included
  } else { f = day0; t = end; }
  return { from: Math.floor(f / 1000), to: Math.floor(t / 1000) };
}

function perfPick(v) {
  PERF.period = v;
  PERF.focus = "period:" + v;
  perfDrawPeriods();
  return perfLoad();
}

// The period buttons, and the From/To boxes shown only while Custom is chosen.
// `hidden` alone loses to any display rule, so the display is set as well.
function perfDrawPeriods() {
  const host = document.getElementById("perf_periods");
  if (host && typeof uiSeg === "function") {
    host.innerHTML = uiSeg(PERF_PERIODS, PERF.period, "perfPick")
      .replace(/<button class="segbtn( on)?" onclick="perfPick\((?:'|&quot;)(\w+)(?:'|&quot;)\)"/g,
               function (m, on, v) { return m + ' data-fk="period:' + v + '" aria-pressed="' + (on ? "true" : "false") + '"'; });
  }
  const c = document.getElementById("perf_custom");
  if (c) {
    c.hidden = PERF.period !== "custom";
    c.style.display = PERF.period === "custom" ? "inline-flex" : "none";
  }
  // No future dates in the custom range.
  const today = new Date(), iso = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0") + "-" + String(today.getDate()).padStart(2, "0");
  ["perf_from", "perf_to"].forEach(function (id) { const e = document.getElementById(id); if (e) e.max = iso; });
  perfRefocus();
}

function perfOnOpen() {
  perfDrawPeriods();
  perfFillAccounts();
  return perfLoad();
}

// The account filter comes from the accounts the viewer may open (ACCOUNTS),
// so it can never offer one the server would refuse.
function perfFillAccounts() {
  const accs = (typeof ACCOUNTS !== "undefined" && ACCOUNTS) ? ACCOUNTS : [];
  const sa = document.getElementById("perf_account");
  if (sa) {
    const keep = sa.value;
    sa.innerHTML = '<option value="">All my accounts</option>' + accs.map(function (a) {
      return '<option value="' + esc(a.id) + '">' + esc(a.label || a.id) + "</option>";
    }).join("");
    sa.value = accs.some(function (a) { return a.id === keep; }) ? keep : "";
  }
  perfFillMarkets();
}

// Marketplaces of the chosen account (or of all of them), so the filter never
// offers a pairing that can only show zeros.
function perfFillMarkets() {
  const accs = (typeof ACCOUNTS !== "undefined" && ACCOUNTS) ? ACCOUNTS : [];
  const chosen = (document.getElementById("perf_account") || {}).value || "";
  const sm = document.getElementById("perf_mkt");
  if (!sm) return;
  const keep = sm.value, mk = {};
  accs.forEach(function (a) {
    if (chosen && a.id !== chosen) return;
    (a.marketplaces || []).forEach(function (m) { if (m) mk[String(m).toUpperCase()] = 1; });
  });
  sm.innerHTML = '<option value="">All marketplaces</option>' + Object.keys(mk).sort().map(function (m) {
    return '<option value="' + esc(m) + '">' + esc(m) + "</option>";
  }).join("");
  sm.value = mk[keep] ? keep : "";
}

function perfAccountChanged() {
  perfFillMarkets();
  return perfLoad();
}

// The Employee filter and the timeline are one choice: with a timeline open,
// picking another person opens theirs; "Everyone" goes back to the summary.
function perfUserChanged() {
  const s = document.getElementById("perf_user");
  const v = (s || {}).value || "__all";
  if (PERF.timeline !== null) {
    if (v === "__all") { PERF.timeline = null; PERF.timelineName = ""; }
    else {
      PERF.timeline = v;
      const o = s && s.options ? Array.prototype.find.call(s.options, function (x) { return x.value === v; }) : null;
      PERF.timelineName = o ? o.textContent : "";
    }
  }
  return perfLoad();
}

function perfFiltered() {
  const v = function (id) { return ((document.getElementById(id) || {}).value || ""); };
  return !!(v("perf_account") || v("perf_mkt") || v("perf_cat") || v("perf_ok")
            || (v("perf_user") && v("perf_user") !== "__all"));
}

function perfQuery(b) {
  const v = function (id) { return ((document.getElementById(id) || {}).value || ""); };
  const q = ["from=" + b.from, "to=" + b.to];
  const u = PERF.timeline !== null ? PERF.timeline : v("perf_user");
  // "__shared" is the shared-password owner, stored with an empty user id.
  if (u && u !== "__all") q.push("user=" + encodeURIComponent(u === "__shared" ? "" : u));
  if (v("perf_account")) q.push("account=" + encodeURIComponent(v("perf_account")));
  if (v("perf_mkt")) q.push("marketplace=" + encodeURIComponent(v("perf_mkt")));
  if (v("perf_cat")) q.push("category=" + encodeURIComponent(v("perf_cat")));
  if (v("perf_ok")) q.push("ok=" + encodeURIComponent(v("perf_ok")));
  return q.join("&");
}

async function perfLoad() {
  const body = document.getElementById("perf_body");
  if (!body) return;
  // Every load, even one that stops early, cancels any reply still on its way.
  const my = ++PERF.seq;
  const b = perfBounds(PERF.period, Date.now(),
                       (document.getElementById("perf_from") || {}).value,
                       (document.getElementById("perf_to") || {}).value);
  if (b.error) {
    body.innerHTML = uiEmpty(b.error, esc(b.why));
    return;
  }
  body.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> Loading…</div>';
  const timeline = PERF.timeline !== null;
  const q = perfQuery(b);
  // The list/summary and the overview's shapes, asked at once. The shapes are
  // optional: if they fail, the counts still draw -- only the main reply
  // decides between the screen and an error.
  const get = function (url, fallback) {
    let p;
    try { p = Promise.resolve(fetch(url)); } catch (e) { p = Promise.reject(e); }
    return p.then(function (r) {
      return Promise.resolve().then(function () { return r.json(); }).catch(function () { return fallback; });
    }, function (e) { return { ok: false, error: "Could not reach the server: " + String(e && e.message || e) }; });
  };
  const [j, bd] = await Promise.all([
    get((timeline ? "/activity/list?limit=200&" : "/activity/summary?") + q,
        { ok: false, error: "The server did not send the activity record (your session may have ended — reload the page)." }),
    get("/activity/breakdown?" + q + "&tz=" + new Date().getTimezoneOffset(), null),
  ]);
  if (my !== PERF.seq) return;
  if (!j || !j.ok) {
    const why = (j && j.error) || "No reply from the server.";
    body.innerHTML = uiError("Could not load the activity record", why, "perfLoad", "performance");
    return;
  }
  const more = (bd && bd.ok) ? bd : null;
  perfFillCategories(j.categories || {});
  if (timeline) perfDrawTimeline(j, more, b);
  else { perfFillPeople(j.team || [], j.people || []); perfDrawSummary(j, more, b); }
  perfRefocus();
}

// ---- the pictures (30 Sep 2026: "less text, more visual") ----------------
//
// One colour per kind of work, from the palette tokens, so a person's mix bar,
// the legend and the kinds-of-work list all agree. Never a score: every shape
// here is a count the record holds.
const PERF_COLOURS = {
  listings: "var(--as-info)", images: "var(--as-lit-bc8cff)", files: "var(--as-lit-8b949e-fg)",
  amazon: "var(--as-lit-c9a84c)", pricing: "var(--as-lit-3fb950)", repricer: "var(--as-lit-39d2c0)",
  ppc: "var(--as-lit-e570ff)", orders: "var(--as-lit-d29922)", costs: "var(--as-lit-e87a1e)",
  inventory: "var(--as-lit-2ea043)", team: "var(--as-lit-6e7681-fg)",
};
function perfColour(k) { return PERF_COLOURS[k] || "var(--line2)"; }

// Every day of the period, in the viewer's calendar -- the same days the
// server bucketed with ?tz= -- so a day with nothing recorded is a 0 on the
// chart, not a missing column.
function perfDays(b) {
  const out = [];
  if (!b || !b.from) return out;
  const d = new Date(b.from * 1000);
  const end = b.to * 1000;
  const p2 = function (n) { return String(n).padStart(2, "0"); };
  while (d.getTime() < end && out.length < 400) {
    out.push(d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate()));
    d.setDate(d.getDate() + 1);
  }
  return out;
}

// Actions and failures per day, on the shared dotted-axis chart (salesCombo).
// One day has no shape, so a one-day period draws no chart.
function perfDayChart(id, days, rows) {
  if (days.length < 2 || typeof salesCombo !== "function") return "";
  const by = {};
  (rows || []).forEach(function (r) { by[r.day] = r; });
  // Drawn at the width it will be shown at: a phone got the desktop drawing
  // scaled down to a sliver.
  const w = (typeof scChartWidth === "function") ? scChartWidth("perf_body", 1365) : 1365;
  return salesCombo({ id: id, columns: days, kind: "count", width: w, height: w < 700 ? 300 : 260,
    lines: [
      { key: "perf_actions", label: "Actions", color: "#6ac7e8",
        values: days.map(function (d) { return (by[d] || {}).actions || 0; }) },
      { key: "perf_failed", label: "Failed or refused", color: "#f85149",
        values: days.map(function (d) { return (by[d] || {}).failed || 0; }) },
    ] });
}

// One person's kinds of work as a single stacked bar; the counts are in its
// tooltip and screen-reader label rather than in eleven columns.
function perfMix(byCat, cats) {
  const keys = Object.keys(byCat || {}).filter(function (k) { return (byCat[k] || {}).actions; });
  const tot = keys.reduce(function (s, k) { return s + byCat[k].actions; }, 0);
  if (!tot) return '<span class="cc">—</span>';
  const words = keys.map(function (k) {
    const c = byCat[k];
    return (cats[k] || k) + " " + c.actions + (c.items > c.actions ? " (" + c.items + " things touched)" : "");
  }).join(" · ");
  return '<div class="perf-mix" role="img" aria-label="' + esc(words) + '" title="' + esc(words) + '">'
    + keys.map(function (k) {
        return '<span style="width:' + (100 * byCat[k].actions / tot).toFixed(1) + "%;background:" + perfColour(k) + '"></span>';
      }).join("") + "</div>";
}

function perfLegend(keys, cats) {
  return '<div class="perf-legend">' + keys.map(function (k) {
    return '<span><i style="background:' + perfColour(k) + '"></i>' + esc(cats[k] || k) + "</span>";
  }).join("") + "</div>";
}

// A labelled bar list (account · marketplace, kinds of work). The failed part
// of each bar is drawn in red inside it, so where things go wrong is visible
// without reading a number. Drawn by the shared uiBars (pageui.js) since the
// graph audit (30 Sep 2026); this only says which numbers of a row are which.
function perfBars(rows, label, colour, hint) {
  return uiBars(rows || [], {
    label: label, colour: colour, hint: hint,
    value: function (r) { return r.actions || 0; },
    bad: function (r) { return r.failed || 0; },
    text: function (r) {
      return (r.actions || 0)
        + (r.failed ? ' <span style="color:var(--red)">· ' + r.failed + " failed</span>" : "");
    },
  });
}

function perfPlace(r) {
  const a = (typeof ACCOUNTS !== "undefined" && ACCOUNTS || []).find(function (x) { return x.id === r.workspace_id; });
  return [(a && (a.label || a.id)) || r.workspace_id || "No account", r.marketplace].filter(Boolean).join(" · ");
}

// The two side-by-side panels both views share: where, and what kind.
function perfWhereWhat(bd, cats) {
  if (!bd) return "";
  const acts = (bd.actions || []).slice(0, 12);
  return '<div class="perf-two">'
    + uiPanel("Where", "", perfBars(bd.places || [], perfPlace, function () { return "var(--as-info)"; }))
    + uiPanel("What", "", perfBars(acts, function (r) { return r.label || r.action; },
        function (r) { return perfColour(r.category); },
        function (r) { return r.last_error ? uiHint("Latest failure: " + r.last_error) : ""; }))
    + "</div>";
}

// "Changed after it was sent to Amazon": a fact, not a verdict (see
// domain/activity.breakdown). Shown only when the record has any.
function perfAfterSent(bd) {
  const a = bd && bd.after_sent;
  if (!a || !a.edits) return null;
  return { label: "Changed after sending", value: String(a.edits),
           note: a.skus + (a.skus === 1 ? " product" : " products"),
           // Honest about its reach (review, 30 Sep 2026): a batch submit is
           // recorded as a count, not a list of products, so only products
           // submitted one at a time can be matched.
           title: "Edits or re-pushes to a product this account had already submitted to Amazon — products submitted one at a time only (a batch submit does not record which products it held). Normal work after a launch, shown so it can be seen, not judged." };
}

function perfFillCategories(cats) {
  const s = document.getElementById("perf_cat");
  if (!s || s.options.length > 1) return;
  s.innerHTML = '<option value="">All kinds of work</option>' + Object.keys(cats).map(function (k) {
    return '<option value="' + esc(k) + '">' + esc(cats[k]) + "</option>";
  }).join("");
}

function perfFillPeople(team, people) {
  const s = document.getElementById("perf_user");
  if (!s) return;
  const keep = s.value || "__all";
  const seen = {}, opts = [];
  team.forEach(function (t) { seen[t.user_id] = 1; opts.push([t.user_id, t.label || t.user_id]); });
  people.forEach(function (p) {
    const id = p.user_id === "" ? "__shared" : p.user_id;
    if (seen[p.user_id] || seen[id]) return;
    seen[id] = 1;
    opts.push([id, p.label || "Owner (shared password)"]);
  });
  s.innerHTML = '<option value="__all">Everyone</option>' + opts.map(function (o) {
    return '<option value="' + esc(o[0]) + '">' + esc(o[1]) + "</option>";
  }).join("");
  s.value = opts.some(function (o) { return o[0] === keep; }) ? keep : "__all";
}

function perfWhen(ts) {
  if (!ts) return "—";
  try { return new Date(Number(ts) * 1000).toLocaleString(); } catch (e) { return "—"; }
}

// Focus back on the control that caused the redraw (design-system §8).
function perfRefocus() {
  if (!PERF.focus) return;
  const want = PERF.focus;
  let el = null;
  try {
    el = document.querySelector('[data-fk="' + want.replace(/["\\]/g, "") + '"]');
  } catch (e) { el = null; }
  if (el && typeof el.focus === "function") { el.focus(); PERF.focus = ""; }
}

function perfDrawSummary(j, bd, b) {
  const body = document.getElementById("perf_body");
  const cats = j.categories || {};
  const people = (j.people || []).slice();
  const u = (document.getElementById("perf_user") || {}).value || "__all";
  // Everyone the server listed appears, so someone with no recorded work
  // shows as 0 rather than being absent. Filtered to one person, only them.
  const have = {};
  people.forEach(function (p) { have[p.user_id] = 1; });
  if (u === "__all") {
    (j.team || []).forEach(function (t) {
      if (!have[t.user_id] && t.active)
        people.push({ user_id: t.user_id, label: t.label, total: 0, failed: 0, items: 0, by_category: {}, last_ts: null });
    });
  }
  const used = Object.keys(cats).filter(function (k) {
    return people.some(function (p) { return p.by_category && p.by_category[k]; });
  });
  const total = people.reduce(function (s, p) { return s + (p.total || 0); }, 0);
  const failed = people.reduce(function (s, p) { return s + (p.failed || 0); }, 0);
  const active = people.filter(function (p) { return p.total > 0; }).length;
  // ON THE TOTAL, not the list: the list above is padded with every active
  // team member at 0, so it is never empty and "no recorded work" could never
  // show -- a period with nothing in it drew a table of zeros instead
  // (admin bug round, 30 Sep 2026).
  if (!total) {
    body.innerHTML = perfFiltered()
      ? uiEmpty("Nothing matches these filters", "Try a longer period or clear the filters.")
      : uiEmpty("No recorded work in this period",
                "Work is recorded from the day this screen was installed; anything earlier is not in the record.");
    return;
  }
  const byDay = (bd && bd.by_day) || {};
  const nDays = perfDays(b).length;
  let h = uiStats([
    { label: "Actions recorded", value: String(total) },
    { label: "People active", value: String(active),
      share: people.length ? active / people.length : null, note: "of " + people.length },
    { label: "Failed or refused", value: String(failed), tone: failed ? "bad" : "",
      share: total ? failed / total : null, barColor: "var(--red)",
      note: total ? (100 * failed / total).toFixed(1) + " %" : "" },
    perfAfterSent(bd),
  ]);
  const chart = bd ? perfDayChart("perf_days", perfDays(b), bd.days) : "";
  if (chart) h += uiPanel("Per day", "", chart);
  const maxT = Math.max.apply(null, people.map(function (p) { return p.total || 0; })) || 1;
  let t = '<div style="overflow-x:auto"><table class="stk-table" style="min-width:640px"><thead><tr>'
    + '<th>Person</th><th class="r">Actions</th><th style="min-width:160px">Work mix</th>'
    + '<th class="r">Failed</th>' + (bd && nDays > 1 ? '<th class="r">Days active</th>' : "")
    + '<th>Last action</th><th><span class="visually-hidden">Timeline</span></th></tr></thead><tbody>';
  people.forEach(function (p) {
    const id = p.user_id === "" ? "__shared" : p.user_id;
    const name = p.label || "Owner (shared password)";
    const days = Object.keys(byDay[p.user_id] || {}).length;
    t += "<tr><td>" + esc(name) + '</td><td class="r">' + (p.total || 0) + "</td>"
      + '<td><div class="perf-share"><span style="width:' + (100 * (p.total || 0) / maxT).toFixed(1) + '%"></span></div>'
      + perfMix(p.by_category, cats) + "</td>"
      + '<td class="r"' + (p.failed ? ' style="color:var(--red)"' : "") + ">" + (p.failed || 0)
      + (p.failed && p.total ? ' <span class="cc">(' + Math.round(100 * p.failed / p.total) + "%)</span>" : "") + "</td>"
      + (bd && nDays > 1 ? '<td class="r">' + days + '<span class="cc">/' + nDays + "</span></td>" : "")
      + "<td>" + esc(perfWhen(p.last_ts)) + "</td>"
      + "<td>" + (p.total ? '<button class="db-chip" data-fk="tl:' + esc(id) + '" aria-label="Timeline for ' + esc(name)
                  + '" onclick="perfOpenTimeline(' + jsArg(id) + "," + jsArg(name) + ')">Open</button>' : "") + "</td></tr>";
  });
  t += "</tbody></table></div>";
  h += uiPanel("By person", "", t, { right: perfLegend(used, cats) });
  h += perfWhereWhat(bd, cats);
  body.innerHTML = h;
  if (chart && typeof scRearm === "function") scRearm("perf_days");
}

function perfOpenTimeline(uid, name) {
  PERF.timeline = uid;
  PERF.timelineName = name || "";
  PERF.focus = "tl-back";
  const s = document.getElementById("perf_user");
  if (s) s.value = uid;                    // the Employee filter follows
  return perfLoad();
}

function perfCloseTimeline() {
  const uid = PERF.timeline;
  PERF.timeline = null;
  PERF.timelineName = "";
  PERF.focus = uid !== null ? "tl:" + uid : "";
  const s = document.getElementById("perf_user");
  if (s) s.value = "__all";
  return perfLoad();
}

function perfDrawTimeline(j, bd, b) {
  const cats = j.categories || {};
  const rows = j.rows || [];
  const who = PERF.timelineName || (rows.length ? rows[0].user_label : "") || "Owner (shared password)";
  let h = '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">'
    + '<button class="db-chip" data-fk="tl-back" onclick="perfCloseTimeline()"><i class="ti ti-arrow-left"></i> Everyone</button>'
    + "<b>" + esc(who) + '</b><span class="cc">' + j.total + (j.total === 1 ? " action" : " actions")
    + (j.total > rows.length ? " — showing the latest " + rows.length : "") + "</span></div>";
  if (!rows.length) {
    h += uiEmpty("Nothing recorded for this person in this period", "Try a longer period or clear the filters.");
    document.getElementById("perf_body").innerHTML = h;
    return;
  }
  // THE DRILL-DOWN: the same shapes as the overview, for this one person (the
  // server applied ?user= to them), then every action in order.
  if (bd) {
    const failedN = (bd.days || []).reduce(function (s, d) { return s + (d.failed || 0); }, 0);
    const nDays = perfDays(b).length;
    h += uiStats([
      { label: "Actions", value: String(j.total) },
      { label: "Failed or refused", value: String(failedN), tone: failedN ? "bad" : "",
        share: j.total ? failedN / j.total : null, barColor: "var(--red)",
        note: j.total ? (100 * failedN / j.total).toFixed(1) + " %" : "" },
      nDays > 1 ? { label: "Days active", value: String((bd.days || []).length), note: "of " + nDays,
                    share: (bd.days || []).length / nDays } : null,
      perfAfterSent(bd),
    ]);
    const chart = perfDayChart("perf_days_one", perfDays(b), bd.days);
    if (chart) h += uiPanel("Per day", "", chart);
    h += perfWhereWhat(bd, cats);
  }
  h += '<div class="salespanel perf-list"><div style="overflow-x:auto"><table class="stk-table" style="min-width:560px;table-layout:fixed"><thead><tr>'
    + '<th style="width:150px">When</th><th style="width:130px">Kind</th>'
    + '<th>What</th><th style="width:120px">Account</th><th style="width:70px">Result</th></tr></thead><tbody>';
  rows.forEach(function (r) {
    const d = r.detail || {};
    const extra = [];
    if (d.values && d.values.field) {
      // "field: 'old' → 'new'" when the old value was recorded; else just the field.
      const short = function (x) { const s = String(x); return s.length > 60 ? s.slice(0, 60) + "…" : s; };
      extra.push("field: " + d.values.field
        + ("old_value" in d.values ? " ('" + short(d.values.old_value) + "' → '" + short(d.values.new_value) + "')" : ""));
    }
    if (d.files && d.files.length) extra.push("file: " + d.files.join(", "));
    if (d.fields && d.fields.length && !(d.values && d.values.field)) extra.push("sent: " + d.fields.slice(0, 6).join(", "));
    const res = d.refused ? "refused" : (r.ok ? "worked" : "failed");
    h += "<tr><td>" + esc(perfWhen(r.ts)) + "</td><td>" + esc(cats[r.category] || r.category) + "</td>"
      + '<td style="overflow-wrap:anywhere">' + esc(r.summary || r.action)
      + (extra.length ? '<div class="cc" style="font-size:11px">' + esc(extra.join(" · ")) + "</div>" : "") + "</td>"
      + "<td>" + esc(r.workspace_id || r.marketplace ? perfPlace(r) : "—") + "</td>"
      + '<td style="color:var(' + (r.ok ? "--ok" : "--red") + ')">' + res + "</td></tr>";
  });
  h += "</tbody></table></div></div>";
  document.getElementById("perf_body").innerHTML = h;
  if (bd && typeof scRearm === "function") scRearm("perf_days_one");
}
