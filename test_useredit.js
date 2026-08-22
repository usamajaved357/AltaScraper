/* Does the Edit panel actually render its controls?
 *
 * Loads the REAL static/js/users.js, feeds it the REAL JSON that /users/list
 * and /users/me return, and asks what each screen would contain.
 *
 * The bug this pins down: USERS_META was assembled by hand in two places and
 * both listed only all_permissions and roles, so all_features/role_features
 * were discarded on arrival and the "What may they SEE?" section rendered as
 * an empty string -- in the Edit panel AND the Add form.
 */
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const { execFileSync } = require("child_process");

// Overridable so a regression can be demonstrated against a patched copy --
// a test nobody has ever seen fail is not yet known to test anything.
const src = fs.readFileSync(
  process.env.USERS_JS || "D:/AltaScraper/static/js/users.js", "utf8");

/* THE FIXTURES ARE BUILT, NOT STORED.
 *
 * These two came from process.argv[2] and [3] -- JSON files a person was
 * expected to save by hand from a running server and pass in. The suite runs
 * every test_*.js bare, so both were `undefined`, readFileSync threw
 * ERR_INVALID_ARG_TYPE, and the file died before its first assertion. A test
 * that cannot run on its own is not in the suite, whatever the folder says.
 *
 * Worse than not running: a saved fixture is a photograph. auth/users.py has
 * grown from 17 features to 42 since these were written, and a stored copy
 * would still be describing seventeen -- so the panel could stop rendering
 * twenty-five of them with every assertion green.
 *
 * So the vocabulary is read from auth/users.py itself, which is the same source
 * routes/users_routes._vocabulary() serves to the browser. Not a second copy of
 * a rule (rule 12) -- the same constants, read directly, so a feature added
 * there turns up here without anyone remembering to re-export anything.
 */
function _fixtures() {
  const py = process.env.PYTHON || "python";
  const out = execFileSync(py, ["-c", [
    "import json, sys",
    "sys.path.insert(0, r'" + __dirname + "')",
    "from auth import users as u",
    "voc = {'ok': True,",
    " 'all_permissions': u.PERMISSIONS, 'all_features': u.FEATURES,",
    " 'levels': list(u.LEVELS), 'role_features': u.ROLE_FEATURES,",
    " 'feature_parent': u.FEATURE_PARENT,",
    " 'feature_groups': [{'title': t, 'features': fs} for t, fs in u.FEATURE_GROUPS],",
    " 'roles': list(getattr(u, 'ROLES', u.ROLE_FEATURES.keys()))}",
    // One user is enough: every assertion below reads users[0]. Given a real
    // role so role_features has something to say about it.
    // permissions is a LIST of the keys this person holds (users.py builds it
    // with list(user.get('permissions') or [])), and features is a map of
    // feature -> level. Getting those the wrong way round makes the panel throw
    // rather than render, which is how this fixture was first written.
    "voc['users'] = [{'id': 'u_test_1', 'name': 'Test Person',",
    "                 'email': 'test@example.com', 'role': list(u.ROLE_FEATURES)[-1],",
    "                 'permissions': list(u.PERMISSIONS)[:1],",
    "                 'features': {f: 'view' for f in list(u.FEATURES)[:1]}}]",
    "print(json.dumps(voc))",
  ].join("\n")], { cwd: __dirname, encoding: "utf8", maxBuffer: 32 * 1024 * 1024 });
  return JSON.parse(out);
}

const LIST = process.argv[2]
  ? JSON.parse(fs.readFileSync(process.argv[2], "utf8"))
  : _fixtures();
// /users/me is the same vocabulary plus who you are -- that is the whole point
// of _vocabulary() existing once, and the bug this file was written for was the
// two endpoints describing the app differently.
const ME = process.argv[3]
  ? JSON.parse(fs.readFileSync(process.argv[3], "utf8"))
  : Object.assign({}, LIST, { user: LIST.users[0] });

function freshSandbox() {
  const s = {
    document: { getElementById: () => null, querySelectorAll: () => [], addEventListener: () => {} },
    window: { addEventListener: () => {} },
    fetch: () => Promise.reject(new Error("no network in this test")),
    console,
  };
  s.window.document = s.document;
  vm.createContext(s);
  vm.runInContext(src, s);
  return s;
}

let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(58),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}

const NFEAT = Object.keys(LIST.all_features).length;
const NPERM = Object.keys(LIST.all_permissions).length;

console.log("=== the server describes the app the same way on both endpoints ===");
for (const k of ["all_permissions", "all_features", "role_features", "levels", "roles"]) {
  check("/users/me and /users/list agree on " + k,
        JSON.stringify(ME[k]) === JSON.stringify(LIST[k]), true);
}

console.log("\n=== nothing is discarded on arrival ===");
let s = freshSandbox();
s.J = LIST;
vm.runInContext("_setMeta(J)", s);
check("all_features kept", vm.runInContext("!!USERS_META.all_features", s), true);
check("role_features kept", vm.runInContext("!!USERS_META.role_features", s), true);
check("levels kept", vm.runInContext("!!USERS_META.levels", s), true);
check("all_permissions kept", vm.runInContext("!!USERS_META.all_permissions", s), true);
check("roles kept", vm.runInContext("!!USERS_META.roles", s), true);

console.log("\n=== a narrower response cannot erase what is already known ===");
// This is the failure mode that made the bug possible. /users/me runs first on
// page load; if it ever omits a key, the Edit panel must not lose it.
s = freshSandbox();
s.FULL = LIST;
s.THIN = { ok: true, all_permissions: LIST.all_permissions, roles: LIST.roles };
vm.runInContext("_setMeta(FULL); _setMeta(THIN)", s);
check("all_features survives a thin follow-up",
      vm.runInContext("!!USERS_META.all_features", s), true);
check("role_features survives a thin follow-up",
      vm.runInContext("!!USERS_META.role_features", s), true);

console.log("\n=== the Edit panel's three sections ===");
s = freshSandbox();
s.J = LIST;
vm.runInContext("_setMeta(J)", s);
s.U = LIST.users[0];
const feat = vm.runInContext('featureRows("ueX", U.features||{})', s);
const perm = vm.runInContext('permissionCheckboxes("ueX", U.permissions||[])', s);
const ws = vm.runInContext('workspaceCheckboxes("ueX", U.workspaces||[])', s);
check('"What may they SEE?" renders', feat.length > 0, true);
check("  one dropdown per area", (feat.match(/<select/g) || []).length, NFEAT);
// CHANGED DELIBERATELY. Permissions are now settable per PAGE as well as per
// area, and a page offers a FOURTH choice: Inherit, which is what it does until
// somebody pins it. So the option count is three per area plus four per page,
// not three per feature. Counting the selects above already proves every
// feature is drawn; this proves each one offers the choices it should.
const _children = Object.keys(LIST.feature_parent || {})
                        .filter(function(k){ return (LIST.all_features||{})[k]; }).length;
check("  every area offers three levels, every page four",
      (feat.match(/<option/g) || []).length, (NFEAT * 3) + _children);
check("  and Inherit is offered only on a page",
      (feat.match(/value=""/g) || []).length, _children);
check('"What may they do?" renders', (perm.match(/type="checkbox"/g) || []).length, NPERM);
check('"Which workspaces?" renders', ws.length > 0, true);

console.log("\n=== it shows what is ACTUALLY in force, not a blank ===");
const u0 = LIST.users[0];
Object.keys(u0.features).forEach(function (k) {
  const re = new RegExp('data-feat="' + k + '"[\\s\\S]*?<\\/select>');
  const block = (feat.match(re) || [""])[0];
  const sel = (block.match(/<option value="([a-z]+)" selected>/) || [])[1];
  check("  " + k + " shows the level on the record", sel, u0.features[k]);
});

console.log("\n=== the Add form presets from the chosen role ===");
s = freshSandbox();
s.J = LIST;
vm.runInContext("_setMeta(J)", s);
const add = vm.runInContext('featureRows("nu", (USERS_META.role_features||{})["lister"])', s);
check("Add form renders its area dropdowns", (add.match(/<select/g) || []).length, NFEAT);
const listerPpc = (add.match(/data-feat="ppc"[\s\S]*?<\/select>/) || [""])[0];
check("  a lister is preset to no PPC access",
      /<option value="none" selected>/.test(listerPpc), true);

console.log("\n=== every button's onclick is actually runnable JavaScript ===");
// The bug this pins down: the handlers were built with JSON.stringify(id),
// which returns a DOUBLE-quoted string -- the same character that closes the
// onclick="..." attribute it was pasted into. The browser read the handler as
// `userSave(` and stopped, so Edit, Invite, Enable/Disable, Delete and Save
// changes all did nothing at all: no error, no request, no clue. Only "Add",
// which passes no id, kept working, which made the screen look alive.
//
// Rendering the REAL markup and parsing every handler out of it is the only
// check that would have caught it -- the JS is valid, the HTML is valid, and
// only their combination is broken.
function handlersIn(html) {
  const out = [];
  const re = /onclick="([^"]*)"/g;
  let m;
  while ((m = re.exec(html))) {
    out.push(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, "&")
                 .replace(/&lt;/g, "<").replace(/&gt;/g, ">"));
  }
  return out;
}

function domSandbox(listJson) {
  const captured = {};
  const el = (id) => ({
    get innerHTML() { return captured[id] || ""; },
    set innerHTML(v) { captured[id] = v; },
    style: {}, textContent: "", classList: { add() {}, remove() {} },
    scrollIntoView() {}, setAttribute() {}, getAttribute: () => null,
  });
  const nodes = {};
  const s = {
    document: {
      getElementById: (id) => (nodes[id] = nodes[id] || el(id)),
      querySelectorAll: () => [],
      addEventListener: () => {},
    },
    window: { addEventListener: () => {} },
    fetch: () => Promise.resolve({ json: () => Promise.resolve(listJson) }),
    toast: () => {},
    console,
  };
  s.window.document = s.document;
  vm.createContext(s);
  vm.runInContext(src, s);
  return { s, nodes };
}

(async () => {
  const { s, nodes } = domSandbox(LIST);
  s.J = LIST;
  vm.runInContext("_setMeta(J)", s);

  // --- the list of people, with its four buttons per row ---
  await vm.runInContext("renderUsers()", s);
  const listHtml = nodes["usersbody"].innerHTML;
  const rowHandlers = handlersIn(listHtml);
  check("the user list drew its buttons", rowHandlers.length > 0, true);
  rowHandlers.forEach(function (h) {
    let ok = true, why = "";
    try { new Function(h); } catch (e) { ok = false; why = e.message; }
    check("  runs: " + h.slice(0, 46), ok ? true : why, true);
  });
  ["userEdit", "userInvite", "userToggle", "userDelete"].forEach(function (fn) {
    check("  " + fn + " is wired to a row",
          rowHandlers.some((h) => h.indexOf(fn + "(") === 0), true);
  });
  check("  and the id survives into the call",
        rowHandlers.some((h) => h.indexOf(LIST.users[0].id) > 0), true);

  // --- the Edit panel's Save button ---
  await vm.runInContext('userEdit(' + JSON.stringify(LIST.users[0].id) + ')', s);
  await new Promise((r) => setImmediate(r));      // let the fetch().then settle
  const panel = nodes["uedit_" + LIST.users[0].id].innerHTML;
  const saveHandlers = handlersIn(panel).filter((h) => h.indexOf("userSave") === 0);
  check("the Edit panel drew a Save button", saveHandlers.length, 1);
  let saveOk = true, saveWhy = "";
  try { new Function(saveHandlers[0] || ""); } catch (e) { saveOk = false; saveWhy = e.message; }
  check("  Save changes runs", saveOk ? true : saveWhy, true);
  check("  and carries the user id", (saveHandlers[0] || "").indexOf(LIST.users[0].id) > 0, true);

  // --- the escaping helper itself ---
  const awkward = vm.runInContext("_uarg(\"a'b\\\\c&d\\\"e\")", s);
  check("_uarg never emits a bare double quote", /"/.test(awkward), false);
  check("  and escapes a single quote for JS", awkward.indexOf("\\'") > 0, true);

  console.log("\n=== no other screen builds a handler the same broken way ===");
  // The Users screen was not the only place: "Use as main" in the image library
  // had it too, and rendered perfectly while doing nothing. A double-quoted
  // onclick with JSON.stringify inside it is always this bug, so the whole
  // static/js tree is scanned rather than trusting that the two known cases were
  // all of them. onclick='...' with SINGLE quotes is fine and is left alone.
  const dir = "D:/AltaScraper/static/js";
  const offenders = [];
  for (const fn of fs.readdirSync(dir).filter((f) => f.endsWith(".js"))) {
    const text = fs.readFileSync(dir + "/" + fn, "utf8");
    text.split(/\r?\n/).forEach((line, i) => {
      if (/onclick="[^"]*JSON\.stringify/.test(line)) offenders.push(fn + ":" + (i + 1));
    });
  }
  check("no double-quoted onclick uses JSON.stringify", offenders, []);

  console.log("\n=== every Amazon link actually points at Amazon ===");
  // _dpUrl was refactored from whole domains ("amazon.co.uk") to TLDs ("co.uk")
  // so the ASIN monitor could reuse the table for seller links -- and the
  // "amazon." was left out of the prefix, so every link became
  // https://www.co.uk/dp/B0... It rendered, it was blue, it was clickable, and
  // it went somewhere else entirely. A link that is plausibly wrong is worse
  // than one that fails.
  const ls = fs.readFileSync("D:/AltaScraper/static/js/listings.js", "utf8");
  const box = {
    WS_MARKET: "UK", console,
    document: { getElementById: () => null, querySelectorAll: () => [], addEventListener: () => {} },
    window: { addEventListener: () => {} },
    fetch: () => Promise.reject(new Error("no network")),
  };
  box.window.document = box.document;
  vm.createContext(box);
  try { vm.runInContext(ls, box); } catch (e) { /* only _dpUrl is needed */ }
  const dp = (m, a) =>
    vm.runInContext("_dpUrl(" + JSON.stringify(a) + "," + JSON.stringify(m) + ")", box);

  check("UK", dp("UK", "B0H66K5QWX"), "https://www.amazon.co.uk/dp/B0H66K5QWX");
  check("US", dp("US", "B0X"), "https://www.amazon.com/dp/B0X");
  check("DE", dp("DE", "B0X"), "https://www.amazon.de/dp/B0X");
  check("JP", dp("JP", "B0X"), "https://www.amazon.co.jp/dp/B0X");
  check("an unknown market falls back to the UK, not to nowhere",
        dp("ZZ", "B0X"), "https://www.amazon.co.uk/dp/B0X");
  check("no market given uses the workspace's own",
        dp("", "B0X"), "https://www.amazon.co.uk/dp/B0X");
  ["UK", "US", "DE", "FR", "IT", "ES", "CA", "AU", "JP", "IN", "SE", "PL"].forEach(
    function (m) {
      const u = dp(m, "B0TEST");
      check("  " + m + " goes to an amazon domain", /^https:\/\/www\.amazon\.[a-z.]+\/dp\//.test(u), true);
    });

  console.log("\nFAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})();
