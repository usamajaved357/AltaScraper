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
  let j;
  try {
    const r = await fetch((timeline ? "/activity/list?limit=200&" : "/activity/summary?") + perfQuery(b));
    try { j = await r.json(); }
    catch (e) { j = { ok: false, error: "The server did not send the activity record (your session may have ended — reload the page)." }; }
  } catch (e) { j = { ok: false, error: "Could not reach the server: " + String(e && e.message || e) }; }
  if (my !== PERF.seq) return;
  if (!j || !j.ok) {
    const why = (j && j.error) || "No reply from the server.";
    body.innerHTML = uiError("Could not load the activity record", why, "perfLoad", "performance");
    return;
  }
  perfFillCategories(j.categories || {});
  if (timeline) perfDrawTimeline(j);
  else { perfFillPeople(j.team || [], j.people || []); perfDrawSummary(j); }
  perfRefocus();
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

function perfDrawSummary(j) {
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
  if (!total && !people.length) {
    body.innerHTML = perfFiltered()
      ? uiEmpty("Nothing matches these filters", "Try a longer period or clear the filters.")
      : uiEmpty("No recorded work in this period",
                "Work is recorded from the day this screen was installed; anything earlier is not in the record.");
    return;
  }
  let h = uiStats([
    { label: "Actions recorded", value: String(total) },
    { label: "People active", value: String(active) },
    { label: "Failed or refused", value: String(failed) },
  ]);
  let t = '<div style="overflow-x:auto"><table class="stk-table" style="min-width:' + (360 + used.length * 100) + 'px"><thead><tr>'
    + '<th>Person</th><th class="r">Actions</th>'
    + used.map(function (k) { return '<th class="r">' + esc(cats[k]) + "</th>"; }).join("")
    + '<th class="r">Failed</th><th>Last action</th><th><span class="visually-hidden">Timeline</span></th></tr></thead><tbody>';
  people.forEach(function (p) {
    const id = p.user_id === "" ? "__shared" : p.user_id;
    const name = p.label || "Owner (shared password)";
    t += "<tr><td>" + esc(name) + '</td><td class="r">' + (p.total || 0) + "</td>"
      + used.map(function (k) {
          const c = (p.by_category || {})[k];
          if (!c) return '<td class="r">0</td>';
          const more = c.items > c.actions ? ' <span class="cc" title="things touched">(' + c.items + ")</span>" : "";
          return '<td class="r">' + c.actions + more + "</td>";
        }).join("")
      + '<td class="r"' + (p.failed ? ' style="color:var(--red)"' : "") + ">" + (p.failed || 0) + "</td>"
      + "<td>" + esc(perfWhen(p.last_ts)) + "</td>"
      + "<td>" + (p.total ? '<button class="db-chip" data-fk="tl:' + esc(id) + '" aria-label="Timeline for ' + esc(name)
                  + '" onclick="perfOpenTimeline(' + jsArg(id) + "," + jsArg(name) + ')">Timeline</button>' : "") + "</td></tr>";
  });
  t += "</tbody></table></div>";
  h += uiPanel("By person", "Counts of recorded actions. A number in brackets is how many products, files or orders those actions touched.", t);
  body.innerHTML = h;
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

function perfDrawTimeline(j) {
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
  h += '<div style="overflow-x:auto"><table class="stk-table" style="min-width:560px;table-layout:fixed"><thead><tr>'
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
      + "<td>" + esc([r.workspace_id, r.marketplace].filter(Boolean).join(" · ") || "—") + "</td>"
      + '<td style="color:var(' + (r.ok ? "--ok" : "--red") + ')">' + res + "</td></tr>";
  });
  h += "</tbody></table></div>";
  document.getElementById("perf_body").innerHTML = h;
}
