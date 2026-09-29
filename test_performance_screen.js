/* The Employee Performance screen (29 Sep 2026).
 *
 *   "show me what meaningful work each employee did today or during another
 *    selected period" -- "Do NOT invent an arbitrary employee performance score"
 *
 * Loads the REAL performance.js, pageui.js and users.js's jsArg with a small fake
 * page and pins:
 *   - the periods are the viewer's own local days; a custom range includes its
 *     last day and says what is wrong with an unusable one;
 *   - the summary lists every member the server sent, a quiet one as 0, plain
 *     counts only -- no score -- in the shared stk-table;
 *   - the filters reach the request; the Employee filter and the timeline are
 *     one choice; the Marketplace filter follows the chosen Account;
 *   - loading, error (never "nobody did anything"), empty (says why), a reply
 *     that is not JSON, and a slower earlier reply never overwriting a newer
 *     view -- including when Custom stops early (UI review);
 *   - focus goes back where it was after each redraw; each Timeline button
 *     names its person;
 *   - the wiring: nav item, section, onOpen, the view_activity gate.
 */
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const R = __dirname;
const PERFJS = fs.readFileSync(path.join(R, "static/js/performance.js"), "utf8");
const PAGEUI = fs.readFileSync(path.join(R, "static/js/pageui.js"), "utf8");
const USERSJS = fs.readFileSync(path.join(R, "static/js/users.js"), "utf8");

let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(66), ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}

function page() {
  const els = {};
  const s = {
    console, calls: [], fetchReplies: [], focused: null,
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"),
    ACCOUNTS: [{ id: "acct_a", label: "A Ltd", marketplaces: ["UK", "DE"] },
               { id: "acct_c", label: "C Ltd", marketplaces: ["US"] }],
    setTimeout,
  };
  const el = (id) => els[id] || (els[id] = { id, value: "", hidden: false, options: [], style: {},
    _h: "", get innerHTML() { return this._h; },
    set innerHTML(v) {
      this._h = v;
      // a <select>'s options, as a real DOM would expose them
      this.options = []; const re = /<option value="([^"]*)"[^>]*>([^<]*)<\/option>/g; let m;
      while ((m = re.exec(v))) this.options.push({ value: m[1], textContent: m[2] });
    } });
  s.document = {
    getElementById: (id) => el(id),
    // data-fk lookups for focus: found when any drawn markup carries it
    querySelector: (sel) => {
      const m = /data-fk="([^"]+)"/.exec(sel);
      if (!m) return null;
      const hit = Object.values(els).some((e) => (e._h || "").indexOf('data-fk="' + m[1] + '"') >= 0);
      return hit ? { focus: () => { s.focused = m[1]; } } : null;
    },
  };
  s.fetch = (url) => { s.calls.push(url); const r = s.fetchReplies.shift();
    if (r && r.then) return r;
    if (r === "not-json") return Promise.resolve({ json: () => Promise.reject(new SyntaxError("Unexpected token <")) });
    return Promise.resolve({ json: () => Promise.resolve(r) }); };
  vm.createContext(s);
  vm.runInContext(USERSJS.match(/function jsArg\(s\)\{[\s\S]*?\n\}/)[0], s);   // the REAL jsArg
  vm.runInContext(PAGEUI, s);
  vm.runInContext(PERFJS, s);
  return { s, el };
}

const CATS = { listings: "Listings and drafts", images: "Images", amazon: "Sent to Amazon" };
const SUMMARY = {
  ok: true, categories: CATS,
  people: [{ user_id: "u_ali", label: "Ali", total: 5, failed: 1, items: 9,
             by_category: { listings: { actions: 3, failed: 1, items: 3 }, images: { actions: 2, failed: 0, items: 6 } },
             first_ts: 1, last_ts: 1800000000 }],
  team: [{ user_id: "u_ali", label: "Ali", active: true }, { user_id: "u_sara", label: "Sara", active: true },
         { user_id: "u_gone", label: "Gone", active: false }],
};
const TL = (rows) => ({ ok: true, categories: CATS, total: rows.length, rows });

(async () => {
  console.log("=== periods are the viewer's own days ===");
  {
    const { s } = page();
    const now = new Date(2026, 8, 29, 15, 30).getTime();
    const d0 = new Date(2026, 8, 29).getTime() / 1000;
    const b = (p, f, t) => vm.runInContext(`perfBounds(${JSON.stringify(p)}, ${now}, ${JSON.stringify(f || "")}, ${JSON.stringify(t || "")})`, s);
    check("today starts at local midnight", b("today").from, d0);
    check("yesterday is the whole previous day", [b("yesterday").from, b("yesterday").to], [d0 - 86400, d0]);
    check("7 days includes today", b("7d").from, new Date(2026, 8, 23).getTime() / 1000);
    check("30 days includes today", b("30d").from, new Date(2026, 7, 31).getTime() / 1000);
    check("custom includes its last day",
          [b("custom", "2026-09-01", "2026-09-02").from, b("custom", "2026-09-01", "2026-09-02").to],
          [new Date(2026, 8, 1).getTime() / 1000, new Date(2026, 8, 3).getTime() / 1000]);
    check("custom with a missing date asks for both", b("custom", "", "2026-09-02").error, "Pick both dates");
    check("custom backwards says so", b("custom", "2026-09-05", "2026-09-01").error, "The To date is before the From date");
  }

  console.log("=== summary: everyone the server sent, counts, no score ===");
  {
    const { s, el } = page();
    s.fetchReplies.push(SUMMARY);
    await vm.runInContext("perfOnOpen()", s);
    const h = el("perf_body").innerHTML;
    check("asks the summary for the period", /^\/activity\/summary\?from=\d+&to=\d+$/.test(s.calls[0]), true);
    check("the shared data table (stk-table), numbers right-aligned", /<table class="stk-table"/.test(h) && /<th class="r">Actions<\/th>/.test(h), true);
    check("Ali's counts are drawn", /Ali<\/td><td class="r">5<\/td>/.test(h), true);
    check("items touched shown beside the count", h.indexOf('2 <span class="cc" title="things touched">(6)</span>') > 0, true);
    check("a quiet active member shows as 0", /Sara<\/td><td class="r">0<\/td>/.test(h), true);
    check("a disabled member with no work is left out", h.indexOf("Gone") < 0, true);
    check("only kinds of work that happened get a column", [h.indexOf("Sent to Amazon") < 0, h.indexOf("Images") > 0], [true, true]);
    check("failures and refusals are counted", /Failed or refused/.test(h), true);
    check("no score anywhere", /score|rating|rank/i.test(h), false);
    check("each Timeline button names its person", h.indexOf('aria-label="Timeline for Ali"') > 0, true);
    check("the employee filter lists only who the server sent",
          el("perf_user").options.map((o) => o.value), ["__all", "u_ali", "u_sara", "u_gone"]);
    check("period buttons say which is pressed", /data-fk="period:today" aria-pressed="true"/.test(el("perf_periods").innerHTML), true);
    check("From/To hidden unless Custom", [el("perf_custom").hidden, el("perf_custom").style.display], [true, "none"]);
    check("account filter offers only the viewer's accounts", el("perf_account").options.map((o) => o.value), ["", "acct_a", "acct_c"]);
    check("marketplaces of every account when none is chosen", el("perf_mkt").options.map((o) => o.value), ["", "DE", "UK", "US"]);
    el("perf_account").value = "acct_c";
    s.fetchReplies.push(SUMMARY);
    await vm.runInContext("perfAccountChanged()", s);
    check("marketplaces follow the chosen account", el("perf_mkt").options.map((o) => o.value), ["", "US"]);
    s.fetchReplies.push(SUMMARY);
    await vm.runInContext("perfPick('7d')", s);
    check("a period click keeps focus on the period buttons", s.focused, "period:7d");
  }

  console.log("=== filters and the timeline ===");
  {
    const { s, el } = page();
    el("perf_user").value = "u_ali"; el("perf_account").value = "acct_a"; el("perf_mkt").value = "UK";
    el("perf_cat").value = "images"; el("perf_ok").value = "0";
    s.fetchReplies.push(SUMMARY);
    await vm.runInContext("perfLoad()", s);
    check("every filter reaches the request",
          /user=u_ali&account=acct_a&marketplace=UK&category=images&ok=0$/.test(s.calls[0]), true);
    el("perf_user").value = "__all"; el("perf_account").value = ""; el("perf_mkt").value = "";
    el("perf_cat").value = ""; el("perf_ok").value = "";
    s.fetchReplies.push(TL([{ ts: 1800000000, user_label: "Ali", category: "listings", action: "listing.edit",
      summary: "Edited a listing SKU-1", workspace_id: "acct_a", marketplace: "UK", ok: false,
      detail: { values: { field: "item_name" } } },
      { ts: 1800000001, user_label: "Ali", category: "listings", action: "listing.status",
        summary: "Refused: changed a listing's approval status", workspace_id: "acct_a", ok: false, detail: { refused: true } }]));
    await vm.runInContext("perfOpenTimeline('u_ali', 'Ali')", s);
    const h = el("perf_body").innerHTML;
    check("a timeline is one person's list", /^\/activity\/list\?limit=200&from=\d+&to=\d+&user=u_ali$/.test(s.calls[1]), true);
    check("  the Employee filter follows it", el("perf_user").value, "u_ali");
    check("  each action with the field it changed", h.indexOf("field: item_name") > 0, true);
    check("  failed and refused told apart", [h.indexOf(">failed</td>") > 0, h.indexOf(">refused</td>") > 0], [true, true]);
    check("  focus moves to the way back", s.focused, "tl-back");
    s.fetchReplies.push(TL([]));
    el("perf_user").value = "u_sara";
    el("perf_user").innerHTML = '<option value="__all">Everyone</option><option value="u_ali">Ali</option><option value="u_sara">Sara</option>';
    el("perf_user").value = "u_sara";
    await vm.runInContext("perfUserChanged()", s);
    check("changing Employee with a timeline open opens THAT person's", /&user=u_sara$/.test(s.calls[2]), true);
    check("  named in the header even with no rows", el("perf_body").innerHTML.indexOf("<b>Sara</b>") > 0, true);
    s.fetchReplies.push(SUMMARY);
    el("perf_user").value = "__all";
    await vm.runInContext("perfUserChanged()", s);
    check("'Everyone' goes back to the summary", s.calls[3].indexOf("/activity/summary?") === 0, true);
    s.fetchReplies.push(TL([]));
    await vm.runInContext("perfOpenTimeline('u_ali', 'Ali')", s);
    s.fetchReplies.push(SUMMARY);
    await vm.runInContext("perfCloseTimeline()", s);
    check("back to everyone: focus on that person's Timeline button", s.focused, "tl:u_ali");
    s.fetchReplies.push(TL([]));
    await vm.runInContext("perfOpenTimeline('__shared', 'Owner (shared password)')", s);
    check("the shared-password owner is asked for as an empty id", /&user=$/.test(s.calls[s.calls.length - 1]), true);
  }

  console.log("=== loading, error, empty, stale replies ===");
  {
    const { s, el } = page();
    let release;
    s.fetchReplies.push(new Promise((r) => { release = r; }));
    const p1 = vm.runInContext("perfLoad()", s);
    check("loading says so", /Loading/.test(el("perf_body").innerHTML), true);
    s.fetchReplies.push({ ok: false, error: "You do not have permission" });
    await vm.runInContext("perfLoad()", s);
    check("an error is drawn as an error, with the reason",
          [/ui-error/.test(el("perf_body").innerHTML), /do not have permission/.test(el("perf_body").innerHTML)], [true, true]);
    check("  and never as 'no recorded work'", /No recorded work/.test(el("perf_body").innerHTML), false);
    release({ json: () => Promise.resolve(SUMMARY) });
    await p1;
    check("a slower earlier reply does not overwrite the newer one", /ui-error/.test(el("perf_body").innerHTML), true);

    let rel2;
    s.fetchReplies.push(new Promise((r) => { rel2 = r; }));
    const p2 = vm.runInContext("perfPick('30d')", s);
    await vm.runInContext("perfPick('custom')", s);
    rel2({ json: () => Promise.resolve(SUMMARY) });
    await p2;
    check("30 days then Custom at once: the late 30-day reply is dropped",
          /Pick both dates/.test(el("perf_body").innerHTML), true);
    el("perf_from").value = "2026-09-05"; el("perf_to").value = "2026-09-01";
    await vm.runInContext("perfLoad()", s);
    check("a backwards range says what is wrong", /To date is before the From date/.test(el("perf_body").innerHTML), true);

    await vm.runInContext("PERF.period = 'today'", s);
    s.fetchReplies.push("not-json");
    await vm.runInContext("perfLoad()", s);
    check("a reply that is not JSON reads as a plain error",
          [/session may have ended/.test(el("perf_body").innerHTML), /Unexpected token/.test(el("perf_body").innerHTML)], [true, false]);

    s.fetchReplies.push({ ok: true, categories: CATS, people: [], team: [] });
    await vm.runInContext("perfLoad()", s);
    check("empty, no filters: says the record starts at install",
          /No recorded work in this period/.test(el("perf_body").innerHTML), true);
    el("perf_ok").value = "0";
    s.fetchReplies.push({ ok: true, categories: CATS, people: [], team: [] });
    await vm.runInContext("perfLoad()", s);
    check("empty with a filter: suggests clearing it", /Nothing matches these filters/.test(el("perf_body").innerHTML), true);
  }

  console.log("=== wiring ===");
  const shell = fs.readFileSync(path.join(R, "static/js/shell.js"), "utf8");
  const dash = fs.readFileSync(path.join(R, "templates/dashboard.html"), "utf8");
  const tpl = fs.readFileSync(path.join(R, "templates/screens/sec_performance.html"), "utf8");
  check("a real section", /"team","performance"/.test(shell), true);
  check("opening it loads", shell.indexOf('if(sec==="performance"){ if(typeof perfOnOpen==="function") perfOnOpen(); }') >= 0, true);
  check("nav item, include and script",
        [dash.indexOf('data-sec="performance"') > 0, dash.indexOf("screens/sec_performance.html") > 0,
         dash.indexOf("/static/js/performance.js") > 0], [true, true, true]);
  check("gated by view_activity, like /activity on the server",
        /SECTION_PERMISSION = \{[^}]*performance: "view_activity"/.test(USERSJS), true);
  check("the whole table is not a live region (read once, not on every filter)", /id="perf_body"[^>]*aria-live/.test(tpl), false);

  console.log("\nFAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})();
