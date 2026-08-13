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

const src = fs.readFileSync("D:/AltaScraper/static/js/users.js", "utf8");
const LIST = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const ME = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

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
check("  each offers all three levels",
      (feat.match(/<option/g) || []).length, NFEAT * 3);
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

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
