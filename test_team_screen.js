/* The Team screen (read.txt Priority 3, 29 Sep 2026).
 *
 * Team is the one place team members are managed. It is NOT a second user
 * editor: users.js draws the list, the add form and the editor into #teambody,
 * and team.js adds only the summary and the filter. This loads the REAL
 * users.js and team.js with a small fake page and pins:
 *   - each person's row says their state, the accounts they can open, the
 *     marketplaces those accounts cover, and when they last signed in;
 *   - the editor can now change name and role (the server always accepted
 *     both), and picking a role presets that role's permissions;
 *   - the filter and summary agree with the rows;
 *   - the wiring: nav item, section, onOpen, the manage_users gate.
 */
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const R = __dirname;
const USERS = fs.readFileSync(path.join(R, "static/js/users.js"), "utf8");
const TEAM = fs.readFileSync(path.join(R, "static/js/team.js"), "utf8");

let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(62), ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}

// A tiny DOM: elements by id, rows found by attribute from the drawn HTML.
function page(listJson) {
  const html = {}, els = {};
  const el = (id) => els[id] || (els[id] = {
    id, style: {}, value: "", textContent: "", attrs: {},
    // Redrawing the list drops the row cache, as a real DOM would.
    get innerHTML() { return html[id] || ""; }, set innerHTML(v) { html[id] = v; if (id === "teambody") rowCache = null; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    removeAttribute(k) { delete this.attrs[k]; }, classList: { add() {}, remove() {} },
  });
  const rows = () => {
    const out = [], re = /<tr data-team-id="([^"]*)" data-team-state="([^"]*)" data-team-search="([^"]*)"/g;
    let m; const h = html["teambody"] || "";
    while ((m = re.exec(h))) {
      const r = { style: {}, a: { "data-team-id": m[1], "data-team-state": m[2], "data-team-search": m[3] } };
      r.getAttribute = (k) => r.a[k];
      out.push(r);
    }
    return out;
  };
  let rowCache = null;
  const s = {
    document: {
      getElementById: (id) => (id === "usersbody" ? null : el(id)),
      querySelectorAll: (sel) => (sel.indexOf("tr[data-team-id]") >= 0 ? (rowCache = rowCache || rows()) : []),
      addEventListener() {},
    },
    window: { addEventListener() {} },
    fetch: () => Promise.resolve({ json: () => Promise.resolve(listJson) }),
    toast() {}, console,
    ACCOUNTS: [{ id: "jack_uk", label: "Jack Reacherd", marketplaces: ["UK"], default_marketplace: "UK" },
               { id: "sheelady_us", label: "Sheelady", marketplaces: ["US", "CA"], default_marketplace: "US" }],
  };
  s.window.document = s.document;
  vm.createContext(s);
  vm.runInContext(USERS, s);
  vm.runInContext(TEAM, s);
  s._resetRows = () => { rowCache = null; };
  return { s, html, el };
}

const META = {
  ok: true, all_permissions: { edit: "Edit", manage_users: "Manage users" },
  all_features: { listings: "Listings" }, levels: ["none", "view", "edit"],
  role_features: { lister: { listings: "edit" }, viewer: { listings: "view" } },
  feature_parent: {}, feature_groups: [{ title: "Listings", features: ["listings"] }],
  roles: { owner: ["edit", "manage_users"], lister: ["edit"], viewer: [] },
};
const now = Math.floor(Date.now() / 1000);
const LIST = Object.assign({}, META, { users: [
  { id: "u_ali", name: "Ali", email: "ali@example.com", role: "lister", permissions: ["edit"],
    features: {}, workspaces: ["jack_uk"], active: true, last_login: now, pending_invite: false },
  { id: "u_sara", name: "Sara", email: "sara@example.com", role: "viewer", permissions: [],
    features: {}, workspaces: ["*"], active: true, pending_invite: true },
  { id: "u_old", name: "Old", email: "old@example.com", role: "lister", permissions: [],
    features: {}, workspaces: [], active: false },
  // An expired invite, on an account the viewer's ACCOUNTS list does not hold.
  { id: "u_exp", name: "Exp", email: "exp@example.com", role: "lister", permissions: [],
    features: {}, workspaces: ["jack_uk", "gone_acct"], active: true, pending_invite: true, invite_expired: true },
] });

(async () => {
  const { s, html, el } = page(LIST);
  s.J = LIST;
  vm.runInContext("_setMeta(J)", s);
  await vm.runInContext("renderUsers()", s);
  const h = html["teambody"] || "";

  console.log("=== the list, drawn into Team ===");
  check("drawn into #teambody", h.indexOf("Ali") > 0, true);
  check("one row per person, with their state",
        (h.match(/data-team-state="(\w+)"/g) || []).map((x) => x.split('"')[1]), ["active", "invited", "disabled", "expired"]);
  check("Ali: the accounts and marketplaces they can reach",
        h.indexOf("Accounts: Jack Reacherd · Marketplaces: UK") > 0, true);
  check("Sara (all accounts): every marketplace those cover",
        h.indexOf("Accounts: all accounts (including any added later) · Marketplaces: CA, UK, US") > 0, true);
  check("Old (no accounts): says none", h.indexOf("Accounts: none · Marketplaces: —") > 0, true);
  check("never signed in says so", h.indexOf("Last signed in: never") > 0, true);
  // REVIEW FIX (29 Sep): ACCOUNTS is only what the VIEWER may open. An account id
  // it does not hold is shown raw, never dropped, and the line says it is partial.
  check("an account the viewer cannot see is named, not dropped",
        h.indexOf("Accounts: Jack Reacherd, gone_acct · Marketplaces: UK, plus any on accounts you cannot open") > 0, true);

  console.log("=== a manager limited to one account ===");
  {
    const p2 = page(LIST);
    p2.s.J = LIST;
    vm.runInContext("_setMeta(J); ME = {permissions:['manage_users'], features:{}, workspaces:['jack_uk']};", p2.s);
    p2.s.ACCOUNTS = [{ id: "jack_uk", label: "Jack Reacherd", marketplaces: ["UK"] }];
    await vm.runInContext("renderUsers()", p2.s);
    const h2 = p2.html["teambody"] || "";
    check("someone on another account is named, not shown as 'none'",
          h2.indexOf("Accounts: Jack Reacherd, gone_acct · Marketplaces: UK, plus any on accounts you cannot open") > 0, true);
    check("an all-accounts person: marketplaces say they are partial",
          h2.indexOf("Accounts: all accounts (including any added later) · Marketplaces: UK, plus any on accounts you cannot open") > 0, true);
  }

  console.log("=== summary and filter ===");
  const sum = () => el("team_summary").textContent;
  check("summary counts the drawn rows",
        sum(), "4 people · 1 active · 1 not yet accepted their invite · 1 with an expired invite · 1 disabled");
  el("team_state").value = "active"; s._resetRows();
  vm.runInContext("teamFilter()", s);
  check("filter says what it shows", /1 of 4 shown$/.test(sum()), true);
  el("team_state").value = "expired"; s._resetRows();
  vm.runInContext("teamFilter()", s);
  check("expired invites can be filtered to", /1 of 4 shown$/.test(sum()), true);
  el("team_state").value = ""; el("team_q").value = "sara"; s._resetRows();
  vm.runInContext("teamFilter()", s);
  check("search by name", /1 of 4 shown$/.test(sum()), true);
  check("a match hides the 'nobody matches' line", el("team_nomatch").hidden, true);
  el("team_q").value = "nobody-called-this"; s._resetRows();
  vm.runInContext("teamFilter()", s);
  check("no match says so where the list was", el("team_nomatch").hidden, false);
  el("team_q").value = ""; s._resetRows();
  vm.runInContext("teamFilter()", s);
  const tpl = fs.readFileSync(path.join(R, "templates/screens/sec_team.html"), "utf8");
  check("the status filter offers every state a row can have",
        ["active", "invited", "expired", "disabled"].every((v) => tpl.indexOf('<option value="' + v + '">') > 0), true);

  console.log("=== loading and error never sit under old counts ===");
  {
    const p3 = page(LIST);
    p3.s.J = LIST;
    vm.runInContext("_setMeta(J)", p3.s);
    await vm.runInContext("renderUsers()", p3.s);
    check("counts after a good load", /^4 people/.test(p3.el("team_summary").textContent), true);
    p3.s.fetch = () => Promise.resolve({ json: () => Promise.resolve({ ok: false, error: "refused" }) });
    p3.s._resetRows();
    await vm.runInContext("renderUsers()", p3.s);
    check("after a failed Reload the summary is empty", p3.el("team_summary").textContent, "");
  }

  console.log("=== the editor: name and role ===");
  el("uedit_u_ali").innerHTML = "";
  vm.runInContext("userEdit('u_ali')", s);
  await new Promise((r) => setTimeout(r, 20));
  const ed = el("uedit_u_ali").innerHTML;
  check("name box with the current name", /id="uename_u_ali" value="Ali"/.test(ed), true);
  check("role picker with the current role selected", /<option value="lister" selected>lister<\/option>/.test(ed), true);
  // Picking a role presets that role's boxes -- through the ONE helper the add
  // form uses too (Rule 12).
  {
    const boxes = [{ checked: false, getAttribute: () => "edit" }, { checked: true, getAttribute: () => "manage_users" }];
    const sels = [{ value: "none", getAttribute: () => "listings" }];
    const qsa = s.document.querySelectorAll;
    s.document.querySelectorAll = (sel) => sel === ".ueu_ali_perm" ? boxes : sel === ".ueu_ali_feat" ? sels : qsa(sel);
    el("uerole_u_ali").value = "lister";
    vm.runInContext("userEditRolePreset('u_ali')", s);
    s.document.querySelectorAll = qsa;
    check("role preset ticks that role's permissions", boxes.map((b) => b.checked), [true, false]);
    check("role preset sets that role's page access", sels[0].value, "edit");
    check("one preset helper for both forms",
          /function userRolePreset\(\)\{ _rolePreset\(/.test(USERS) && /function userEditRolePreset\(id\)\{ _rolePreset\(/.test(USERS), true);
  }
  let sent = null;
  s.fetch = (url, opt) => { sent = { url, body: JSON.parse(opt.body) }; return Promise.resolve({ json: () => Promise.resolve({ ok: true }) }); };
  el("uename_u_ali").value = "  Ali Khan "; el("uerole_u_ali").value = "viewer";
  s.renderUsers = () => {};
  await vm.runInContext("userSave('u_ali')", s);
  check("save sends the trimmed name and the role",
        [sent && sent.url, sent && sent.body.name, sent && sent.body.role], ["/users/update", "Ali Khan", "viewer"]);

  console.log("=== wiring ===");
  const shell = fs.readFileSync(path.join(R, "static/js/shell.js"), "utf8");
  const dash = fs.readFileSync(path.join(R, "templates/dashboard.html"), "utf8");
  check("a real section", /"permissions","team"/.test(shell) && fs.existsSync(path.join(R, "templates/screens/sec_team.html")), true);
  check("opening it draws the list", shell.indexOf('if(sec==="team"){ if(typeof teamOnOpen==="function") teamOnOpen(); }') >= 0, true);
  check("nav item and script on the page",
        dash.indexOf('data-sec="team"') > 0 && dash.indexOf("/static/js/team.js") > 0 && dash.indexOf('screens/sec_team.html') > 0, true);
  check("mapped for page access", /team:"permissions"/.test(USERS), true);
  // REVIEW FIX (29 Sep): Team follows the SERVER's gate for /users/*, which is
  // manage_users alone. A lister given "manage users" has accounts="none" and
  // used to be refused at the door by the Users button that was shown to them.
  vm.runInContext("ME = {permissions:['edit','manage_users'], features:{permissions:'none', accounts:'none'}}", s);
  check("manage_users opens Team whatever the page levels say",
        [vm.runInContext("sectionLevel('team')", s), vm.runInContext("maySeeSection('team')", s)], ["edit", true]);
  vm.runInContext("ME = {permissions:['edit'], features:{permissions:'edit'}}", s);
  check("without manage_users Team is refused at the door",
        [vm.runInContext("sectionLevel('team')", s), vm.runInContext("maySeeSection('team')", s)], ["none", false]);
  check("other screens still follow their page level",
        vm.runInContext("sectionLevel('permissions')", s), "edit");
  check("the Users button opens Team", /if\(document\.getElementById\("sec_team"\) && typeof navTo === "function"\)\{ navTo\("team"\); return; \}/.test(USERS), true);

  console.log("\nFAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})();
